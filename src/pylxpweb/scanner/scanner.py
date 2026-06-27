"""Async network scanner for discovering EG4 devices on a local network.

Scans TCP ports to find Modbus TCP (502) and WiFi dongle (8000) devices,
optionally verifying Modbus devices by reading EG4-specific registers.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import AsyncIterator, Callable

from pylxpweb.scanner.mac_lookup import get_oui_vendor, lookup_mac_address
from pylxpweb.scanner.types import DeviceType, ScanConfig, ScanProgress, ScanResult
from pylxpweb.scanner.utils import parse_ip_range

_LOGGER = logging.getLogger(__name__)

# Default ports for EG4 devices
PORT_MODBUS = 502
PORT_DONGLE = 8000

# Progress reporting: report at each N% increment
_PROGRESS_PERCENT_STEP = 5


class NetworkScanner:
    """Scan a local network for EG4 Modbus TCP and WiFi dongle devices.

    Usage::

        from pylxpweb.scanner import NetworkScanner, ScanConfig

        config = ScanConfig(ip_range="192.168.1.0/24")
        scanner = NetworkScanner(config)

        async for result in scanner.scan():
            print(result.display_label)

    Args:
        config: Scan configuration (IP range, ports, timeouts, etc.).
        progress_callback: Optional callback invoked with ScanProgress updates.
    """

    def __init__(
        self,
        config: ScanConfig,
        progress_callback: Callable[[ScanProgress], None] | None = None,
    ) -> None:
        self._config = config
        self._progress_callback = progress_callback
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation of an in-progress scan."""
        self._cancelled = True

    async def scan(self) -> AsyncIterator[ScanResult]:
        """Scan the configured IP range and yield discovered devices.

        Yields:
            ScanResult for each device found (Modbus verified, unverified,
            or dongle candidate).
        """
        hosts = parse_ip_range(self._config.ip_range)
        if not hosts:
            return

        self._cancelled = False
        total = len(hosts)
        semaphore = asyncio.Semaphore(self._config.concurrency)
        results_queue: asyncio.Queue[ScanResult] = asyncio.Queue()
        scanned_count = 0
        found_count = 0
        last_reported_pct = -1

        async def scan_host(ip: str) -> None:
            nonlocal scanned_count, found_count, last_reported_pct
            if self._cancelled:
                return
            async with semaphore:
                if self._cancelled:
                    return
                for port in self._config.ports:
                    result = await self._probe_port(ip, port)
                    if result is not None:
                        found_count += 1
                        await results_queue.put(result)

                scanned_count += 1
                if self._progress_callback:
                    pct = math.floor(scanned_count * 100 / total)
                    if pct >= last_reported_pct + _PROGRESS_PERCENT_STEP:
                        last_reported_pct = pct
                        self._progress_callback(
                            ScanProgress(
                                total_hosts=total,
                                scanned=scanned_count,
                                found=found_count,
                            )
                        )

        # Launch all host scans as tasks
        tasks = [asyncio.create_task(scan_host(ip)) for ip in hosts]

        # Yield results as they arrive while tasks run
        pending_tasks = set(tasks)

        try:
            while pending_tasks or not results_queue.empty():
                if self._cancelled:
                    break

                # Check for completed tasks
                newly_done = {t for t in pending_tasks if t.done()}
                pending_tasks -= newly_done

                # Log any task exceptions
                for t in newly_done:
                    exc = t.exception()
                    if exc is not None:
                        _LOGGER.warning("Scan task failed: %s: %s", type(exc).__name__, exc)

                # Drain available results
                while not results_queue.empty():
                    yield results_queue.get_nowait()

                if pending_tasks:
                    await asyncio.sleep(0.05)
        finally:
            # Cancel remaining tasks on cancellation or generator close
            for t in pending_tasks:
                t.cancel()
            if pending_tasks:
                await asyncio.gather(*pending_tasks, return_exceptions=True)

        # Final progress update
        if self._progress_callback:
            self._progress_callback(
                ScanProgress(
                    total_hosts=total,
                    scanned=scanned_count,
                    found=found_count,
                )
            )

    async def _probe_port(self, ip: str, port: int) -> ScanResult | None:
        """Probe a single IP:port and optionally verify the device.

        Returns:
            ScanResult if the port is open, None if closed/unreachable.
        """
        start = time.monotonic()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=self._config.timeout,
            )
            elapsed_ms = (time.monotonic() - start) * 1000
            writer.close()
            await writer.wait_closed()
        except (TimeoutError, ConnectionRefusedError, OSError):
            return None

        _LOGGER.debug("Port %d open on %s (%.1fms)", port, ip, elapsed_ms)

        # MAC lookup if enabled
        mac_address: str | None = None
        mac_vendor: str | None = None
        if self._config.lookup_mac:
            mac_address = await lookup_mac_address(ip)
            if mac_address:
                mac_vendor = get_oui_vendor(mac_address)

        if port == PORT_MODBUS and self._config.verify_modbus:
            return await self._verify_modbus(ip, port, elapsed_ms, mac_address, mac_vendor)

        if port == PORT_DONGLE:
            return ScanResult(
                ip=ip,
                port=port,
                device_type=DeviceType.DONGLE_CANDIDATE,
                mac_address=mac_address,
                mac_vendor=mac_vendor,
                response_time_ms=elapsed_ms,
            )

        # Non-standard port, Modbus without verification
        return ScanResult(
            ip=ip,
            port=port,
            device_type=DeviceType.MODBUS_UNVERIFIED,
            response_time_ms=elapsed_ms,
            mac_address=mac_address,
            mac_vendor=mac_vendor,
        )

    async def _verify_modbus(
        self,
        ip: str,
        port: int,
        response_time_ms: float,
        mac_address: str | None,
        mac_vendor: str | None,
    ) -> ScanResult:
        """Connect via Modbus and verify this is an EG4 device."""
        from pylxpweb.constants import (
            DEVICE_TYPE_CODE_FLEXBOSS,
            DEVICE_TYPE_CODE_GRIDBOSS,
            DEVICE_TYPE_CODE_LXP_EU,
            DEVICE_TYPE_CODE_PV_SERIES,
            DEVICE_TYPE_CODE_SNA,
            DEVICE_TYPE_CODE_SNA_6000XP,
        )
        from pylxpweb.transports.discovery import discover_device_info, get_model_family_name
        from pylxpweb.transports.factory import create_modbus_transport

        known_codes = {
            DEVICE_TYPE_CODE_GRIDBOSS,
            DEVICE_TYPE_CODE_SNA,
            DEVICE_TYPE_CODE_SNA_6000XP,  # 6000XP variant (GH eg4_web_monitor#222)
            DEVICE_TYPE_CODE_PV_SERIES,
            DEVICE_TYPE_CODE_FLEXBOSS,
            DEVICE_TYPE_CODE_LXP_EU,
        }

        try:
            transport = create_modbus_transport(
                host=ip,
                port=port,
                serial="",
                timeout=max(self._config.timeout, 2.0),
            )
            await transport.connect()
            try:
                info = await discover_device_info(transport)
            finally:
                await transport.disconnect()

            if info.device_type_code in known_codes:
                return ScanResult(
                    ip=ip,
                    port=port,
                    device_type=DeviceType.MODBUS_VERIFIED,
                    serial=info.serial or None,
                    model_family=get_model_family_name(info.device_type_code),
                    device_type_code=info.device_type_code,
                    firmware_version=info.firmware_version,
                    mac_address=mac_address,
                    mac_vendor=mac_vendor,
                    response_time_ms=response_time_ms,
                )
            _LOGGER.debug(
                "Device at %s:%d has unknown type code %d",
                ip,
                port,
                info.device_type_code,
            )
            return ScanResult(
                ip=ip,
                port=port,
                device_type=DeviceType.MODBUS_UNVERIFIED,
                device_type_code=info.device_type_code,
                mac_address=mac_address,
                mac_vendor=mac_vendor,
                response_time_ms=response_time_ms,
                error=f"Unknown device type code: {info.device_type_code}",
            )

        except Exception as err:
            _LOGGER.debug("Modbus verification failed for %s:%d: %s", ip, port, err)
            return ScanResult(
                ip=ip,
                port=port,
                device_type=DeviceType.MODBUS_UNVERIFIED,
                mac_address=mac_address,
                mac_vendor=mac_vendor,
                response_time_ms=response_time_ms,
                error=str(err),
            )
