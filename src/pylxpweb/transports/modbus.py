"""Modbus TCP transport implementation.

This module provides the ModbusTransport class for direct local
communication with inverters via Modbus TCP (typically through
a Waveshare RS485-to-Ethernet adapter).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from .capabilities import MODBUS_CAPABILITIES, TransportCapabilities
from .data import BatteryBankData, InverterEnergyData, InverterRuntimeData
from .exceptions import (
    TransportConnectionError,
    TransportReadError,
    TransportTimeoutError,
    TransportWriteError,
)
from .protocol import BaseTransport

if TYPE_CHECKING:
    from pymodbus.client import AsyncModbusTcpClient

_LOGGER = logging.getLogger(__name__)

# Register group definitions for efficient reading
# Based on Modbus 40-register per call limit
# Source: EG4-18KPV-12LV Modbus Protocol + eg4-modbus-monitor + Yippy's BMS docs
INPUT_REGISTER_GROUPS = {
    "power_energy": (0, 32),  # Registers 0-31: Power, voltage, SOC/SOH, current
    "status_energy": (32, 32),  # Registers 32-63: Status, energy, fault/warning codes
    "temperatures": (64, 16),  # Registers 64-79: Temperatures, currents, fault history
    "bms_data": (80, 33),  # Registers 80-112: BMS passthrough data (Yippy's docs)
}

HOLD_REGISTER_GROUPS = {
    "system": (0, 25),  # Registers 0-24: System config
    "grid_protection": (25, 35),  # Registers 25-59: Grid protection
    "charging": (60, 30),  # Registers 60-89: Charging config
    "battery": (90, 40),  # Registers 90-129: Battery config
}

# Serial number is stored in input registers 115-119 (5 registers, 10 ASCII chars)
# Each register contains 2 ASCII characters: low byte = char[0], high byte = char[1]
SERIAL_NUMBER_START_REGISTER = 115
SERIAL_NUMBER_REGISTER_COUNT = 5


class ModbusTransport(BaseTransport):
    """Modbus TCP transport for local inverter communication.

    This transport connects directly to the inverter via a Modbus TCP
    gateway (e.g., Waveshare RS485-to-Ethernet adapter).

    Example:
        transport = ModbusTransport(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
        )
        await transport.connect()

        runtime = await transport.read_runtime()
        print(f"PV Power: {runtime.pv_total_power}W")

    Note:
        Requires the `pymodbus` package to be installed:
        uv add pymodbus
    """

    def __init__(
        self,
        host: str,
        port: int = 502,
        unit_id: int = 1,
        serial: str = "",
        timeout: float = 10.0,
    ) -> None:
        """Initialize Modbus transport.

        Args:
            host: IP address or hostname of Modbus TCP gateway
            port: TCP port (default 502 for Modbus)
            unit_id: Modbus unit/slave ID (default 1)
            serial: Inverter serial number (for identification)
            timeout: Connection and operation timeout in seconds
        """
        super().__init__(serial)
        self._host = host
        self._port = port
        self._unit_id = unit_id
        self._timeout = timeout
        self._client: AsyncModbusTcpClient | None = None
        self._lock = asyncio.Lock()

    @property
    def capabilities(self) -> TransportCapabilities:
        """Get Modbus transport capabilities."""
        return MODBUS_CAPABILITIES

    @property
    def host(self) -> str:
        """Get the Modbus gateway host."""
        return self._host

    @property
    def port(self) -> int:
        """Get the Modbus gateway port."""
        return self._port

    @property
    def unit_id(self) -> int:
        """Get the Modbus unit/slave ID."""
        return self._unit_id

    async def connect(self) -> None:
        """Establish Modbus TCP connection.

        Raises:
            TransportConnectionError: If connection fails
        """
        try:
            # Import pymodbus here to make it optional
            from pymodbus.client import AsyncModbusTcpClient

            self._client = AsyncModbusTcpClient(
                host=self._host,
                port=self._port,
                timeout=self._timeout,
            )

            connected = await self._client.connect()
            if not connected:
                raise TransportConnectionError(
                    f"Failed to connect to Modbus gateway at {self._host}:{self._port}"
                )

            self._connected = True
            _LOGGER.info(
                "Modbus transport connected to %s:%s (unit %s) for %s",
                self._host,
                self._port,
                self._unit_id,
                self._serial,
            )

        except ImportError as err:
            raise TransportConnectionError(
                "pymodbus package not installed. Install with: uv add pymodbus"
            ) from err
        except (TimeoutError, OSError) as err:
            _LOGGER.error(
                "Failed to connect to Modbus gateway at %s:%s: %s",
                self._host,
                self._port,
                err,
            )
            raise TransportConnectionError(
                f"Failed to connect to {self._host}:{self._port}: {err}. "
                "Verify: (1) IP address is correct, (2) port 502 is not blocked, "
                "(3) Modbus TCP is enabled on the inverter/datalogger."
            ) from err

    async def disconnect(self) -> None:
        """Close Modbus TCP connection."""
        if self._client:
            self._client.close()
            self._client = None

        self._connected = False
        _LOGGER.debug("Modbus transport disconnected for %s", self._serial)

    async def _read_input_registers(
        self,
        address: int,
        count: int,
    ) -> list[int]:
        """Read input registers (read-only runtime data).

        Args:
            address: Starting register address
            count: Number of registers to read (max 40)

        Returns:
            List of register values

        Raises:
            TransportReadError: If read fails
        """
        self._ensure_connected()

        if self._client is None:
            raise TransportConnectionError("Modbus client not initialized")

        async with self._lock:
            try:
                result = await asyncio.wait_for(
                    self._client.read_input_registers(
                        address=address,
                        count=min(count, 40),
                        device_id=self._unit_id,
                    ),
                    timeout=self._timeout,
                )

                if result.isError():
                    _LOGGER.error(
                        "Modbus error reading input registers at %d: %s",
                        address,
                        result,
                    )
                    raise TransportReadError(f"Modbus read error at address {address}: {result}")

                if not hasattr(result, "registers") or result.registers is None:
                    _LOGGER.error(
                        "Invalid Modbus response at address %d: no registers",
                        address,
                    )
                    raise TransportReadError(
                        f"Invalid Modbus response at address {address}: no registers in response"
                    )

                return list(result.registers)

            except TimeoutError as err:
                _LOGGER.error("Timeout reading input registers at %d", address)
                raise TransportTimeoutError(
                    f"Timeout reading input registers at {address}"
                ) from err
            except OSError as err:
                _LOGGER.error("Failed to read input registers at %d: %s", address, err)
                raise TransportReadError(
                    f"Failed to read input registers at {address}: {err}"
                ) from err

    async def _read_holding_registers(
        self,
        address: int,
        count: int,
    ) -> list[int]:
        """Read holding registers (configuration parameters).

        Args:
            address: Starting register address
            count: Number of registers to read (max 40)

        Returns:
            List of register values

        Raises:
            TransportReadError: If read fails
        """
        self._ensure_connected()

        if self._client is None:
            raise TransportConnectionError("Modbus client not initialized")

        async with self._lock:
            try:
                result = await asyncio.wait_for(
                    self._client.read_holding_registers(
                        address=address,
                        count=min(count, 40),
                        device_id=self._unit_id,
                    ),
                    timeout=self._timeout,
                )

                if result.isError():
                    _LOGGER.error(
                        "Modbus error reading holding registers at %d: %s",
                        address,
                        result,
                    )
                    raise TransportReadError(f"Modbus read error at address {address}: {result}")

                if not hasattr(result, "registers") or result.registers is None:
                    _LOGGER.error(
                        "Invalid Modbus response at address %d: no registers",
                        address,
                    )
                    raise TransportReadError(
                        f"Invalid Modbus response at address {address}: no registers in response"
                    )

                return list(result.registers)

            except TimeoutError as err:
                _LOGGER.error("Timeout reading holding registers at %d", address)
                raise TransportTimeoutError(
                    f"Timeout reading holding registers at {address}"
                ) from err
            except OSError as err:
                _LOGGER.error("Failed to read holding registers at %d: %s", address, err)
                raise TransportReadError(
                    f"Failed to read holding registers at {address}: {err}"
                ) from err

    async def _write_holding_registers(
        self,
        address: int,
        values: list[int],
    ) -> bool:
        """Write holding registers.

        Args:
            address: Starting register address
            values: List of values to write

        Returns:
            True if write succeeded

        Raises:
            TransportWriteError: If write fails
        """
        self._ensure_connected()

        if self._client is None:
            raise TransportConnectionError("Modbus client not initialized")

        async with self._lock:
            try:
                result = await asyncio.wait_for(
                    self._client.write_registers(
                        address=address,
                        values=values,
                        device_id=self._unit_id,
                    ),
                    timeout=self._timeout,
                )

                if result.isError():
                    _LOGGER.error(
                        "Modbus error writing registers at %d: %s",
                        address,
                        result,
                    )
                    raise TransportWriteError(f"Modbus write error at address {address}: {result}")

                return True

            except TimeoutError as err:
                _LOGGER.error("Timeout writing registers at %d", address)
                raise TransportTimeoutError(f"Timeout writing registers at {address}") from err
            except OSError as err:
                _LOGGER.error("Failed to write registers at %d: %s", address, err)
                raise TransportWriteError(f"Failed to write registers at {address}: {err}") from err

    async def read_runtime(self) -> InverterRuntimeData:
        """Read runtime data via Modbus input registers.

        Note: Register reads are serialized (not concurrent) to prevent
        transaction ID desynchronization issues with pymodbus and some
        Modbus TCP gateways (e.g., Waveshare RS485-to-Ethernet adapters).

        Returns:
            Runtime data with all values properly scaled

        Raises:
            TransportReadError: If read operation fails
        """
        # Read register groups sequentially to avoid transaction ID issues
        # See: https://github.com/joyfulhouse/pylxpweb/issues/95
        input_registers: dict[int, int] = {}

        for group_name, (start, count) in INPUT_REGISTER_GROUPS.items():
            try:
                values = await self._read_input_registers(start, count)
                for offset, value in enumerate(values):
                    input_registers[start + offset] = value
            except Exception as e:
                _LOGGER.error(
                    "Failed to read register group '%s': %s",
                    group_name,
                    e,
                )
                raise TransportReadError(
                    f"Failed to read register group '{group_name}': {e}"
                ) from e

        return InverterRuntimeData.from_modbus_registers(input_registers)

    async def read_energy(self) -> InverterEnergyData:
        """Read energy statistics via Modbus input registers.

        Energy data comes from the same input registers as runtime data,
        so we read the relevant groups.

        Note: Register reads are serialized to prevent transaction ID issues.

        Returns:
            Energy data with all values in kWh

        Raises:
            TransportReadError: If read operation fails
        """
        # Read energy-related register groups sequentially
        groups_needed = ["status_energy", "advanced"]
        input_registers: dict[int, int] = {}

        for group_name, (start, count) in INPUT_REGISTER_GROUPS.items():
            if group_name not in groups_needed:
                continue

            try:
                values = await self._read_input_registers(start, count)
                for offset, value in enumerate(values):
                    input_registers[start + offset] = value
            except Exception as e:
                _LOGGER.error(
                    "Failed to read energy register group '%s': %s",
                    group_name,
                    e,
                )
                raise TransportReadError(
                    f"Failed to read energy register group '{group_name}': {e}"
                ) from e

        return InverterEnergyData.from_modbus_registers(input_registers)

    async def read_battery(self) -> BatteryBankData | None:
        """Read battery information via Modbus.

        Reads both core battery data (registers 0-31) and BMS passthrough data
        (registers 80-112) for comprehensive battery monitoring.

        Note: Individual battery module data is not available via Modbus.

        Returns:
            Battery bank data with available information, None if no battery

        Raises:
            TransportReadError: If read operation fails
        """
        # Import scaling
        from pylxpweb.constants.scaling import ScaleFactor, apply_scale

        # Read power/energy registers (0-31) for core battery data
        power_regs = await self._read_input_registers(0, 32)

        # Extract battery data from registers
        battery_voltage = apply_scale(power_regs[4], ScaleFactor.SCALE_100)  # INPUT_V_BAT

        # Register 5 contains packed SOC (low byte) and SOH (high byte)
        # Source: eg4-modbus-monitor project
        soc_soh_packed = power_regs[5]
        battery_soc = soc_soh_packed & 0xFF  # Low byte = SOC
        battery_soh = (soc_soh_packed >> 8) & 0xFF  # High byte = SOH

        # Battery charge/discharge power (2-register values)
        charge_power = (power_regs[12] << 16) | power_regs[13]
        discharge_power = (power_regs[14] << 16) | power_regs[15]

        # If no battery voltage, assume no battery
        if battery_voltage < 1.0:
            _LOGGER.debug(
                "Battery voltage %.2fV is below 1.0V threshold, assuming no battery present. "
                "If batteries are installed, check Modbus register mapping.",
                battery_voltage,
            )
            return None

        # Read BMS registers (80-112) for additional battery data
        # These contain BMS passthrough data per Yippy's documentation
        bms_regs: dict[int, int] = {}
        try:
            bms_values = await self._read_input_registers(80, 33)
            for offset, value in enumerate(bms_values):
                bms_regs[80 + offset] = value
        except Exception as e:
            _LOGGER.warning("Failed to read BMS registers 80-112: %s", e)
            # Continue with basic battery data even if BMS read fails

        # Extract BMS data if available
        # Source: Yippy's documentation - https://github.com/joyfulhouse/pylxpweb/issues/97
        bms_fault_code = bms_regs.get(99, 0)
        bms_warning_code = bms_regs.get(100, 0)
        battery_count = bms_regs.get(96, 1)  # Number of batteries in parallel

        # Cell voltage data (registers 101-102, SCALE_1000: mV → V)
        max_cell_voltage = apply_scale(bms_regs.get(101, 0), ScaleFactor.SCALE_1000)
        min_cell_voltage = apply_scale(bms_regs.get(102, 0), ScaleFactor.SCALE_1000)

        # Cell temperature data (registers 103-104, SCALE_10: tenths °C → °C, signed)
        # Note: These are signed values, handle negative temperatures
        max_cell_temp_raw = bms_regs.get(103, 0)
        min_cell_temp_raw = bms_regs.get(104, 0)
        # Convert to signed if needed (values > 32767 are negative in 16-bit signed)
        if max_cell_temp_raw > 32767:
            max_cell_temp_raw = max_cell_temp_raw - 65536
        if min_cell_temp_raw > 32767:
            min_cell_temp_raw = min_cell_temp_raw - 65536
        max_cell_temperature = apply_scale(max_cell_temp_raw, ScaleFactor.SCALE_10)
        min_cell_temperature = apply_scale(min_cell_temp_raw, ScaleFactor.SCALE_10)

        # Cycle count (register 106, no scaling needed)
        cycle_count = bms_regs.get(106, 0)

        return BatteryBankData(
            timestamp=datetime.now(),
            voltage=battery_voltage,
            soc=battery_soc,
            soh=battery_soh,
            charge_power=float(charge_power),
            discharge_power=float(discharge_power),
            fault_code=bms_fault_code,
            warning_code=bms_warning_code,
            battery_count=battery_count if battery_count > 0 else 1,
            max_cell_voltage=max_cell_voltage,
            min_cell_voltage=min_cell_voltage,
            max_cell_temperature=max_cell_temperature,
            min_cell_temperature=min_cell_temperature,
            cycle_count=cycle_count,
            batteries=[],  # Individual battery data not available via Modbus
        )

    async def read_parameters(
        self,
        start_address: int,
        count: int,
    ) -> dict[int, int]:
        """Read configuration parameters via Modbus holding registers.

        Args:
            start_address: Starting register address
            count: Number of registers to read (max 40 per call)

        Returns:
            Dict mapping register address to raw integer value

        Raises:
            TransportReadError: If read operation fails
        """
        result: dict[int, int] = {}

        # Read in chunks of 40 registers (Modbus limit)
        remaining = count
        current_address = start_address

        while remaining > 0:
            chunk_size = min(remaining, 40)
            values = await self._read_holding_registers(current_address, chunk_size)

            for offset, value in enumerate(values):
                result[current_address + offset] = value

            current_address += chunk_size
            remaining -= chunk_size

        return result

    async def write_parameters(
        self,
        parameters: dict[int, int],
    ) -> bool:
        """Write configuration parameters via Modbus holding registers.

        Args:
            parameters: Dict mapping register address to value to write

        Returns:
            True if all writes succeeded

        Raises:
            TransportWriteError: If any write operation fails
        """
        # Sort parameters by address for efficient writing
        sorted_params = sorted(parameters.items())

        # Group consecutive addresses for batch writing
        groups: list[tuple[int, list[int]]] = []
        current_start: int | None = None
        current_values: list[int] = []

        for address, value in sorted_params:
            if current_start is None:
                current_start = address
                current_values = [value]
            elif address == current_start + len(current_values):
                # Consecutive address, add to current group
                current_values.append(value)
            else:
                # Non-consecutive, save current group and start new one
                groups.append((current_start, current_values))
                current_start = address
                current_values = [value]

        # Don't forget the last group
        if current_start is not None and current_values:
            groups.append((current_start, current_values))

        # Write each group
        for start_address, values in groups:
            await self._write_holding_registers(start_address, values)

        return True

    async def read_serial_number(self) -> str:
        """Read inverter serial number from input registers 115-119.

        The serial number is stored as 10 ASCII characters across 5 registers.
        Each register contains 2 characters: low byte = char[0], high byte = char[1].

        This can be used to:
        - Validate the user-entered serial matches the actual device
        - Auto-discover the serial during setup
        - Detect cable swaps in multi-inverter setups

        Returns:
            10-character serial number string (e.g., "BA12345678")

        Raises:
            TransportReadError: If read operation fails

        Example:
            >>> transport = ModbusTransport(host="192.168.1.100", serial="")
            >>> await transport.connect()
            >>> actual_serial = await transport.read_serial_number()
            >>> print(f"Connected to inverter: {actual_serial}")
        """
        values = await self._read_input_registers(
            SERIAL_NUMBER_START_REGISTER, SERIAL_NUMBER_REGISTER_COUNT
        )

        # Decode ASCII characters from register values
        chars: list[str] = []
        for value in values:
            low_byte = value & 0xFF
            high_byte = (value >> 8) & 0xFF
            # Filter out non-printable characters
            if 32 <= low_byte <= 126:
                chars.append(chr(low_byte))
            if 32 <= high_byte <= 126:
                chars.append(chr(high_byte))

        serial = "".join(chars)
        _LOGGER.debug("Read serial number from Modbus: %s", serial)
        return serial

    async def validate_serial(self, expected_serial: str) -> bool:
        """Validate that the connected inverter matches the expected serial.

        Args:
            expected_serial: The serial number the user expects to connect to

        Returns:
            True if serials match, False otherwise

        Raises:
            TransportReadError: If read operation fails
        """
        actual_serial = await self.read_serial_number()
        matches = actual_serial == expected_serial

        if not matches:
            _LOGGER.warning(
                "Serial mismatch: expected %s, got %s",
                expected_serial,
                actual_serial,
            )

        return matches
