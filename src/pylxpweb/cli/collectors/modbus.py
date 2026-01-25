"""Modbus TCP collector for local register reading.

Collects register data directly from inverters via Modbus TCP connection
through an RS485-to-Ethernet adapter (e.g., Waveshare).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from .base import CollectionResult

if TYPE_CHECKING:
    from pylxpweb.devices.inverters._features import InverterFamily
    from pylxpweb.transports.modbus import ModbusTransport

_LOGGER = logging.getLogger(__name__)

# Maximum registers per Modbus read call
MODBUS_MAX_REGISTERS = 40


class ModbusCollector:
    """Collect register data via Modbus TCP transport.

    Connects to an inverter via RS485-to-Ethernet adapter and reads
    input and holding registers in chunks of 40 (Modbus limit).

    Example:
        collector = ModbusCollector(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",  # Optional, auto-detected if not provided
        )
        await collector.connect()
        result = await collector.collect(
            input_ranges=[(0, 400)],
            holding_ranges=[(0, 200)],
        )
        await collector.disconnect()
    """

    def __init__(
        self,
        host: str,
        port: int = 502,
        unit_id: int = 1,
        timeout: float = 10.0,
        serial: str = "",
        inverter_family: InverterFamily | None = None,
    ) -> None:
        """Initialize Modbus collector.

        Args:
            host: IP address or hostname of Modbus gateway
            port: TCP port (default 502)
            unit_id: Modbus unit/slave ID (default 1)
            timeout: Operation timeout in seconds
            serial: Inverter serial number (auto-detected if not provided)
            inverter_family: Inverter family for register mapping
        """
        self._host = host
        self._port = port
        self._unit_id = unit_id
        self._timeout = timeout
        self._serial = serial
        self._inverter_family = inverter_family
        self._transport: ModbusTransport | None = None
        self._connected = False

    @property
    def source_name(self) -> str:
        """Return identifier for this data source."""
        return "modbus"

    async def connect(self) -> None:
        """Establish Modbus TCP connection."""
        # Import here to make pymodbus optional
        from pylxpweb.transports.modbus import ModbusTransport

        self._transport = ModbusTransport(
            host=self._host,
            port=self._port,
            unit_id=self._unit_id,
            serial=self._serial,
            timeout=self._timeout,
            inverter_family=self._inverter_family,
        )

        await self._transport.connect()
        self._connected = True
        _LOGGER.info("Modbus collector connected to %s:%s", self._host, self._port)

    async def disconnect(self) -> None:
        """Close Modbus TCP connection."""
        if self._transport:
            await self._transport.disconnect()
            self._transport = None
        self._connected = False
        _LOGGER.debug("Modbus collector disconnected")

    async def detect_serial(self) -> str | None:
        """Auto-detect inverter serial number from registers 115-119.

        Returns:
            Serial number string if detected, None otherwise
        """
        if not self._transport:
            return None

        try:
            serial = await self._transport.read_serial_number()
            _LOGGER.info("Auto-detected serial: %s", serial)
            return serial
        except Exception as e:
            _LOGGER.warning("Failed to auto-detect serial: %s", e)
            return None

    async def detect_firmware(self) -> str | None:
        """Auto-detect firmware version from holding registers 7-10.

        Returns:
            Firmware version string if detected, None otherwise
        """
        if not self._transport:
            return None

        try:
            firmware = await self._transport.read_firmware_version()
            _LOGGER.info("Auto-detected firmware: %s", firmware)
            return firmware
        except Exception as e:
            _LOGGER.warning("Failed to auto-detect firmware: %s", e)
            return None

    async def collect(
        self,
        input_ranges: list[tuple[int, int]],
        holding_ranges: list[tuple[int, int]],
        progress_callback: Callable[[str], None] | None = None,
    ) -> CollectionResult:
        """Collect register data via Modbus.

        Reads input and holding registers in 40-register chunks.
        Handles errors gracefully, continuing with partial data.

        Args:
            input_ranges: List of (start, count) tuples for input registers
            holding_ranges: List of (start, count) tuples for holding registers
            progress_callback: Optional callback for progress updates

        Returns:
            CollectionResult with all collected data
        """
        if not self._transport or not self._connected:
            raise RuntimeError("Not connected - call connect() first")

        start_time = time.monotonic()
        errors: list[str] = []
        input_registers: dict[int, int] = {}
        holding_registers: dict[int, int] = {}

        # Auto-detect serial if not provided
        serial = self._serial
        if not serial:
            detected = await self.detect_serial()
            serial = detected or "UNKNOWN"

        # Auto-detect firmware
        firmware = await self.detect_firmware() or ""

        # Read input registers
        for range_start, range_count in input_ranges:
            await self._read_register_range(
                is_input=True,
                range_start=range_start,
                range_count=range_count,
                output=input_registers,
                errors=errors,
                progress_callback=progress_callback,
            )

        # Read holding registers
        for range_start, range_count in holding_ranges:
            await self._read_register_range(
                is_input=False,
                range_start=range_start,
                range_count=range_count,
                output=holding_registers,
                errors=errors,
                progress_callback=progress_callback,
            )

        duration = time.monotonic() - start_time

        return CollectionResult(
            source=self.source_name,
            timestamp=datetime.now().astimezone(),
            serial_number=serial,
            firmware_version=firmware,
            inverter_family=self._inverter_family,
            input_registers=input_registers,
            holding_registers=holding_registers,
            connection_params={
                "host": self._host,
                "port": self._port,
                "unit_id": self._unit_id,
            },
            errors=errors,
            duration_seconds=duration,
        )

    async def _read_register_range(
        self,
        is_input: bool,
        range_start: int,
        range_count: int,
        output: dict[int, int],
        errors: list[str],
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        """Read a range of registers in chunks.

        Args:
            is_input: True for input registers, False for holding
            range_start: Starting register address
            range_count: Number of registers to read
            output: Dict to store results (address -> value)
            errors: List to append errors to
            progress_callback: Optional progress callback
        """
        if not self._transport:
            return

        reg_type = "input" if is_input else "holding"
        current = range_start
        end = range_start + range_count

        while current < end:
            chunk_size = min(MODBUS_MAX_REGISTERS, end - current)
            chunk_end = current + chunk_size - 1

            if progress_callback:
                progress_callback(f"Reading {reg_type} registers {current}-{chunk_end}")

            try:
                if is_input:
                    values = await self._transport._read_input_registers(current, chunk_size)
                else:
                    values = await self._transport._read_holding_registers(current, chunk_size)

                for offset, value in enumerate(values):
                    output[current + offset] = value

            except Exception as e:
                error_msg = f"Error reading {reg_type} registers {current}-{chunk_end}: {e}"
                _LOGGER.warning(error_msg)
                errors.append(error_msg)

            current += chunk_size

            # Small delay between reads to prevent overwhelming the device
            await asyncio.sleep(0.05)
