"""Cloud API collector for register reading.

Collects register data via the Luxpower/EG4 cloud API for comparison
with local Modbus/dongle reads.
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
    from pylxpweb.client import LuxpowerClient
    from pylxpweb.devices.inverters._features import InverterFamily

_LOGGER = logging.getLogger(__name__)

# Maximum registers per API read call
API_MAX_REGISTERS = 127

# Default API base URL
DEFAULT_BASE_URL = "https://monitor.eg4electronics.com"

# Standard parameter ranges per device type
INVERTER_PARAMETER_RANGES = [
    (0, 127),  # Base parameters
    (127, 127),  # Extended 1
    (240, 127),  # Extended 2
]

GRIDBOSS_PARAMETER_RANGES = [
    (0, 127),
    (127, 127),
    (240, 141),
    (2032, 127),
]


class CloudCollector:
    """Collect register data via Luxpower/EG4 cloud API.

    Connects to the cloud monitoring portal and reads holding registers
    (parameters) via the remoteRead endpoint.

    Note:
        Input registers are NOT available via the cloud API.
        Only holding registers (parameters) can be read this way.

    Example:
        collector = CloudCollector(
            username="user@example.com",
            password="secret",
            serial="CE12345678",
        )
        await collector.connect()
        result = await collector.collect(
            input_ranges=[],  # Not supported via cloud
            holding_ranges=[(0, 127), (127, 127), (240, 127)],
        )
        await collector.disconnect()
    """

    def __init__(
        self,
        username: str,
        password: str,
        serial: str,
        base_url: str = DEFAULT_BASE_URL,
        inverter_family: InverterFamily | None = None,
    ) -> None:
        """Initialize cloud API collector.

        Args:
            username: Luxpower/EG4 portal username
            password: Luxpower/EG4 portal password
            serial: Inverter serial number (required for API calls)
            base_url: API base URL (default: EG4 US)
            inverter_family: Inverter family for register mapping
        """
        self._username = username
        self._password = password
        self._serial = serial
        self._base_url = base_url.rstrip("/")
        self._inverter_family = inverter_family
        self._client: LuxpowerClient | None = None
        self._connected = False

    @property
    def source_name(self) -> str:
        """Return identifier for this data source."""
        return "cloud"

    async def connect(self) -> None:
        """Establish cloud API connection (login)."""
        from pylxpweb.client import LuxpowerClient

        self._client = LuxpowerClient(
            username=self._username,
            password=self._password,
            base_url=self._base_url,
        )

        # Login happens automatically on first request, but we can trigger it
        await self._client.__aenter__()
        self._connected = True
        _LOGGER.info("Cloud collector connected to %s", self._base_url)

    async def disconnect(self) -> None:
        """Close cloud API connection."""
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None
        self._connected = False
        _LOGGER.debug("Cloud collector disconnected")

    async def detect_serial(self) -> str | None:
        """Return the configured serial number.

        Cloud collector requires serial to be provided upfront.
        """
        return self._serial if self._serial else None

    async def detect_firmware(self) -> str | None:
        """Detect firmware by reading runtime data.

        Returns:
            Firmware version string if available, None otherwise
        """
        if not self._client or not self._serial:
            return None

        try:
            # Get runtime data which includes firmware info
            runtime = await self._client.api.devices.get_inverter_runtime(self._serial)
            return runtime.fwCode if hasattr(runtime, "fwCode") else None
        except Exception as e:
            _LOGGER.warning("Failed to detect firmware: %s", e)
            return None

    async def collect(
        self,
        input_ranges: list[tuple[int, int]],
        holding_ranges: list[tuple[int, int]],
        progress_callback: Callable[[str], None] | None = None,
    ) -> CollectionResult:
        """Collect register data via cloud API.

        Note: Input registers are NOT available via cloud API.
        Only holding registers (parameters) can be read.

        Args:
            input_ranges: Ignored - input registers not available via cloud
            holding_ranges: List of (start, count) tuples for holding registers
            progress_callback: Optional callback for progress updates

        Returns:
            CollectionResult with collected data
        """
        if not self._client or not self._connected:
            raise RuntimeError("Not connected - call connect() first")

        if not self._serial:
            raise ValueError("Serial number required for cloud API")

        start_time = time.monotonic()
        errors: list[str] = []
        holding_registers: dict[int, int] = {}

        # Warn about input registers
        if input_ranges:
            warning = "Input registers not available via cloud API - skipping"
            _LOGGER.warning(warning)
            errors.append(warning)

        # Detect firmware
        firmware = await self.detect_firmware() or ""

        # Read holding registers (parameters) via API
        for range_start, range_count in holding_ranges:
            await self._read_parameter_range(
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
            serial_number=self._serial,
            firmware_version=firmware,
            inverter_family=self._inverter_family,
            input_registers={},  # Not available via cloud
            holding_registers=holding_registers,
            connection_params={
                "base_url": self._base_url,
                "username": _mask_username(self._username),
            },
            errors=errors,
            duration_seconds=duration,
        )

    async def _read_parameter_range(
        self,
        range_start: int,
        range_count: int,
        output: dict[int, int],
        errors: list[str],
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        """Read a range of parameters via API.

        Args:
            range_start: Starting register address
            range_count: Number of registers to read
            output: Dict to store results (address -> value)
            errors: List to append errors to
            progress_callback: Optional progress callback
        """
        if not self._client:
            return

        current = range_start
        end = range_start + range_count

        while current < end:
            chunk_size = min(API_MAX_REGISTERS, end - current)
            chunk_end = current + chunk_size - 1

            if progress_callback:
                progress_callback(f"Reading cloud parameters {current}-{chunk_end}")

            try:
                response = await self._client.api.control.read_parameters(
                    self._serial,
                    start_register=current,
                    point_number=chunk_size,
                )

                if response.success and response.parameters:
                    # Map parameter values back to register addresses
                    # The API returns named parameters, we need to reverse-map
                    await self._map_parameters_to_registers(
                        response.parameters,
                        current,
                        chunk_size,
                        output,
                    )
                else:
                    error_msg = f"API returned no data for registers {current}-{chunk_end}"
                    _LOGGER.warning(error_msg)
                    errors.append(error_msg)

            except Exception as e:
                error_msg = f"Error reading cloud parameters {current}-{chunk_end}: {e}"
                _LOGGER.warning(error_msg)
                errors.append(error_msg)

            current += chunk_size

            # Small delay between API calls to be nice to the server
            await asyncio.sleep(0.5)

    async def _map_parameters_to_registers(
        self,
        parameters: dict[str, int | bool | str],
        start_register: int,
        count: int,
        output: dict[int, int],
    ) -> None:
        """Map parameter names back to register addresses.

        The API returns named parameters, but we want raw register values
        for comparison with Modbus reads.

        Args:
            parameters: Dict of parameter name -> value
            start_register: Starting register address for this block
            count: Number of registers in this block
            output: Dict to store results (address -> value)
        """
        # For now, we can't reverse-map parameter names to exact register addresses
        # without the register mapping tables. Instead, store the raw values
        # at their declared positions.

        # The API returns values that correspond to the requested range,
        # but with named keys. We need to filter out non-integer values
        # and store them sequentially.
        idx = 0
        for _key, value in parameters.items():
            int_value: int
            if isinstance(value, bool):
                int_value = 1 if value else 0
            elif isinstance(value, int):
                int_value = value
            else:
                continue
            output[start_register + idx] = int_value
            idx += 1
            if idx >= count:
                break


def _mask_username(username: str) -> str:
    """Mask username for logging (keep first 3 and last 2 chars)."""
    if len(username) <= 5:
        return "***"
    return f"{username[:3]}***{username[-2:]}"
