"""Modbus TCP transport implementation.

This module provides the ModbusTransport class for direct local
communication with inverters via Modbus TCP (typically through
a Waveshare RS485-to-Ethernet adapter).

IMPORTANT: Single-Client Limitation
------------------------------------
Modbus TCP supports only ONE concurrent connection per gateway/inverter.
Running multiple clients (e.g., Home Assistant + custom script) causes:
- Transaction ID desynchronization
- "Request cancelled outside pymodbus" errors
- Intermittent timeouts and data corruption

Ensure only ONE integration/script connects to each inverter at a time.
Disable other Modbus integrations before using this transport.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from pymodbus.exceptions import ModbusIOException

from ._register_readers import (
    is_midbox_device,
    read_device_type_async,
    read_firmware_version_async,
    read_parallel_config_async,
    read_serial_number_async,
)
from .capabilities import MODBUS_CAPABILITIES, TransportCapabilities
from .data import (
    BatteryBankData,
    InverterEnergyData,
    InverterRuntimeData,
    MidboxRuntimeData,
)
from .exceptions import (
    TransportConnectionError,
    TransportReadError,
    TransportTimeoutError,
    TransportWriteError,
)
from .protocol import BaseTransport

if TYPE_CHECKING:
    from pymodbus.client import AsyncModbusTcpClient

    from pylxpweb.devices.inverters._features import InverterFamily
    from pylxpweb.transports.register_maps import (
        EnergyRegisterMap,
        RuntimeRegisterMap,
    )

_LOGGER = logging.getLogger(__name__)

# Register group definitions for efficient reading
# Based on Modbus 40-register per call limit
# Source: EG4-18KPV-12LV Modbus Protocol + eg4-modbus-monitor + Yippy's BMS docs
INPUT_REGISTER_GROUPS = {
    "power_energy": (0, 32),  # Registers 0-31: Power, voltage, SOC/SOH, current
    "status_energy": (32, 32),  # Registers 32-63: Status, energy, fault/warning codes
    "temperatures": (64, 16),  # Registers 64-79: Temperatures, currents, fault history
    "bms_data": (80, 33),  # Registers 80-112: BMS passthrough data (Yippy's docs)
    "extended_data": (113, 18),  # Registers 113-130: Parallel config, generator, grid L1/L2
    "eps_split_phase": (140, 3),  # Registers 140-142: EPS L1/L2 voltages
    "output_power": (170, 2),  # Registers 170-171: Output power
}


class ModbusTransport(BaseTransport):
    """Modbus TCP transport for local inverter communication.

    This transport connects directly to the inverter via a Modbus TCP
    gateway (e.g., Waveshare RS485-to-Ethernet adapter).

    IMPORTANT: Single-Client Limitation
    ------------------------------------
    Modbus TCP supports only ONE concurrent connection per gateway/inverter.
    Running multiple clients (e.g., Home Assistant + custom script) causes:
    - Transaction ID desynchronization
    - "Request cancelled outside pymodbus" errors
    - Intermittent timeouts and data corruption

    Ensure only ONE integration/script connects to each inverter at a time.
    Disable other Modbus integrations before using this transport.

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
        inverter_family: InverterFamily | None = None,
    ) -> None:
        """Initialize Modbus transport.

        Args:
            host: IP address or hostname of Modbus TCP gateway
            port: TCP port (default 502 for Modbus)
            unit_id: Modbus unit/slave ID (default 1)
            serial: Inverter serial number (for identification)
            timeout: Connection and operation timeout in seconds
            inverter_family: Inverter model family for correct register mapping.
                If None, defaults to PV_SERIES (EG4-18KPV) for backward
                compatibility. Use InverterFamily.LXP_EU for LXP-EU models.
        """
        import asyncio

        super().__init__(serial)
        self._host = host
        self._port = port
        self._unit_id = unit_id
        self._timeout = timeout
        self._inverter_family = inverter_family
        self._client: AsyncModbusTcpClient | None = None
        self._lock = asyncio.Lock()
        self._consecutive_errors: int = 0
        self._max_consecutive_errors: int = 3

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

    @property
    def inverter_family(self) -> InverterFamily | None:
        """Get the inverter family for register mapping."""
        return self._inverter_family

    @inverter_family.setter
    def inverter_family(self, value: InverterFamily | None) -> None:
        """Set the inverter family for register mapping.

        This allows updating the family after auto-detection from device type code,
        ensuring the correct register map is used even if the initial family was
        wrong or defaulted.

        Args:
            value: The detected or configured inverter family
        """
        if value != self._inverter_family:
            _LOGGER.debug(
                "Updating inverter family from %s to %s for %s",
                self._inverter_family,
                value,
                self._serial,
            )
        self._inverter_family = value

    @property
    def runtime_register_map(self) -> RuntimeRegisterMap:
        """Get the runtime register map for this inverter family."""
        from pylxpweb.transports.register_maps import get_runtime_map

        return get_runtime_map(self._inverter_family)

    @property
    def energy_register_map(self) -> EnergyRegisterMap:
        """Get the energy register map for this inverter family."""
        from pylxpweb.transports.register_maps import get_energy_map

        return get_energy_map(self._inverter_family)

    async def connect(self) -> None:
        """Establish Modbus TCP connection.

        After connecting, performs a synchronization read to drain any stale
        responses from the gateway's TCP buffer. This prevents transaction ID
        desynchronization that occurs after integration reload/reconfigure,
        where the gateway still has buffered responses from the old connection.

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
            self._consecutive_errors = 0
            _LOGGER.info(
                "Modbus transport connected to %s:%s (unit %s) for %s",
                self._host,
                self._port,
                self._unit_id,
                self._serial,
            )

            # Drain stale gateway responses to synchronize transaction IDs.
            # After reconfigure/reload, the gateway may have buffered responses
            # from the old connection that cause TID mismatches.
            await self._sync_transaction_ids()

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

    async def _sync_transaction_ids(self) -> None:
        """Drain stale responses and synchronize pymodbus transaction IDs.

        After a reconnect or reconfigure, the Modbus gateway may still have
        buffered responses from the old session queued in its TCP send buffer.
        These arrive with old transaction IDs that pymodbus rejects, causing
        cascading "request ask for transaction_id=X but got id=Y" errors.

        This method:
        1. Waits briefly for the gateway to flush stale data
        2. Performs a probe read (register 0, single register) to establish
           the correct TID baseline
        3. Ignores any errors — the goal is just to drain the buffer
        """
        await asyncio.sleep(0.5)

        if self._client is None:
            return

        try:
            result = await self._client.read_input_registers(
                address=0, count=1, device_id=self._unit_id
            )
            if not result.isError():
                _LOGGER.debug("Transaction ID sync successful for %s", self._serial)
            else:
                _LOGGER.debug(
                    "Transaction ID sync probe returned error for %s (expected "
                    "after reconfigure, stale data drained)",
                    self._serial,
                )
        except Exception:
            _LOGGER.debug(
                "Transaction ID sync probe failed for %s (expected after "
                "reconfigure, stale data drained)",
                self._serial,
            )

    async def disconnect(self) -> None:
        """Close Modbus TCP connection."""
        if self._client:
            self._client.close()
            self._client = None

        self._connected = False
        _LOGGER.debug("Modbus transport disconnected for %s", self._serial)

    async def _reconnect(self) -> None:
        """Reconnect Modbus client to reset transaction ID state.

        Called when consecutive read errors exceed the threshold, which
        typically indicates transaction ID desynchronization (pymodbus
        responses arriving for stale requests).

        Uses lock with double-check to prevent concurrent reconnection
        from multiple callers.
        """
        async with self._lock:
            # Double-check after acquiring lock - another caller may have
            # already reconnected while we were waiting
            if self._consecutive_errors < self._max_consecutive_errors:
                return

            _LOGGER.warning(
                "Reconnecting Modbus client for %s after %d consecutive errors "
                "(likely transaction ID desync)",
                self._serial,
                self._consecutive_errors,
            )
            await self.disconnect()
            await self.connect()
            self._consecutive_errors = 0

    async def _read_registers(
        self,
        address: int,
        count: int,
        *,
        input_registers: bool,
    ) -> list[int]:
        """Read Modbus registers with error tracking and reconnect support.

        Args:
            address: Starting register address
            count: Number of registers to read (max 40)
            input_registers: True for input registers (FC4), False for holding (FC3)

        Returns:
            List of register values

        Raises:
            TransportReadError: If read fails
            TransportTimeoutError: If operation times out

        Note:
            Timeout handling is delegated to pymodbus internally. We don't use
            asyncio.wait_for() because the double-timeout causes transaction ID
            desynchronization issues with pymodbus when timeouts occur.
        """
        self._ensure_connected()

        if self._client is None:
            raise TransportConnectionError("Modbus client not initialized")

        reg_type = "input" if input_registers else "holding"

        async with self._lock:
            try:
                read_fn = (
                    self._client.read_input_registers
                    if input_registers
                    else self._client.read_holding_registers
                )
                result = await read_fn(
                    address=address,
                    count=min(count, 40),
                    device_id=self._unit_id,
                )

                if result.isError():
                    _LOGGER.error(
                        "Modbus error reading %s registers at %d: %s",
                        reg_type,
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

                self._consecutive_errors = 0
                return list(result.registers)

            except ModbusIOException as err:
                self._consecutive_errors += 1
                if "timeout" in str(err).lower():
                    _LOGGER.error("Timeout reading %s registers at %d", reg_type, address)
                    raise TransportTimeoutError(
                        f"Timeout reading {reg_type} registers at {address}"
                    ) from err
                _LOGGER.error("Failed to read %s registers at %d: %s", reg_type, address, err)
                raise TransportReadError(
                    f"Failed to read {reg_type} registers at {address}: {err}"
                ) from err
            except TimeoutError as err:
                self._consecutive_errors += 1
                _LOGGER.error("Timeout reading %s registers at %d", reg_type, address)
                raise TransportTimeoutError(
                    f"Timeout reading {reg_type} registers at {address}"
                ) from err
            except OSError as err:
                self._consecutive_errors += 1
                _LOGGER.error("Failed to read %s registers at %d: %s", reg_type, address, err)
                raise TransportReadError(
                    f"Failed to read {reg_type} registers at {address}: {err}"
                ) from err

    async def _read_input_registers(
        self,
        address: int,
        count: int,
    ) -> list[int]:
        """Read input registers (read-only runtime data)."""
        return await self._read_registers(address, count, input_registers=True)

    async def _read_holding_registers(
        self,
        address: int,
        count: int,
    ) -> list[int]:
        """Read holding registers (configuration parameters)."""
        return await self._read_registers(address, count, input_registers=False)

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
            TransportTimeoutError: If operation times out
        """
        self._ensure_connected()

        if self._client is None:
            raise TransportConnectionError("Modbus client not initialized")

        async with self._lock:
            try:
                # Use FC6 (write_register) for single register, FC16 (write_registers) for multiple
                # EG4/LuxPower inverters only support FC6 for single register writes
                if len(values) == 1:
                    result = await self._client.write_register(
                        address=address,
                        value=values[0],
                        device_id=self._unit_id,
                    )
                else:
                    result = await self._client.write_registers(
                        address=address,
                        values=values,
                        device_id=self._unit_id,
                    )

                if result.isError():
                    _LOGGER.error(
                        "Modbus error writing registers at %d: %s",
                        address,
                        result,
                    )
                    raise TransportWriteError(f"Modbus write error at address {address}: {result}")

                return True

            except ModbusIOException as err:
                error_msg = str(err)
                if "timeout" in error_msg.lower():
                    _LOGGER.error("Timeout writing registers at %d", address)
                    raise TransportTimeoutError(f"Timeout writing registers at {address}") from err
                _LOGGER.error("Failed to write registers at %d: %s", address, err)
                raise TransportWriteError(f"Failed to write registers at {address}: {err}") from err
            except TimeoutError as err:
                _LOGGER.error("Timeout writing registers at %d", address)
                raise TransportTimeoutError(f"Timeout writing registers at {address}") from err
            except OSError as err:
                _LOGGER.error("Failed to write registers at %d: %s", address, err)
                raise TransportWriteError(f"Failed to write registers at {address}: {err}") from err

    async def _read_register_groups(
        self,
        group_names: list[str] | None = None,
    ) -> dict[int, int]:
        """Read multiple register groups sequentially with inter-group delays.

        Groups are read one at a time with a 50ms delay between each to prevent
        RS485 gateway overload and transaction ID desynchronization.

        Args:
            group_names: Specific group names to read from INPUT_REGISTER_GROUPS.
                If None, reads all groups.

        Returns:
            Dict mapping register address to value

        Raises:
            TransportReadError: If any group read fails
        """
        if group_names is None:
            groups = list(INPUT_REGISTER_GROUPS.items())
        else:
            groups = [
                (name, INPUT_REGISTER_GROUPS[name])
                for name in group_names
                if name in INPUT_REGISTER_GROUPS
            ]

        # Reconnect if too many consecutive errors (transaction ID desync recovery)
        if self._consecutive_errors >= self._max_consecutive_errors:
            await self._reconnect()

        registers: dict[int, int] = {}

        for i, (group_name, (start, count)) in enumerate(groups):
            try:
                values = await self._read_input_registers(start, count)
                for offset, value in enumerate(values):
                    registers[start + offset] = value
            except Exception as e:
                _LOGGER.error(
                    "Failed to read register group '%s': %s",
                    group_name,
                    e,
                )
                raise TransportReadError(
                    f"Failed to read register group '{group_name}': {e}"
                ) from e

            # Brief delay between groups to prevent RS485 gateway overload
            if i < len(groups) - 1:
                await asyncio.sleep(0.05)

        return registers

    async def read_runtime(self) -> InverterRuntimeData:
        """Read runtime data via Modbus input registers.

        Uses the appropriate register map based on the inverter_family parameter
        set during transport initialization. Different inverter families have
        different register layouts (e.g., PV_SERIES uses 32-bit power values,
        LXP_EU uses 16-bit power values with offset addresses).

        Note: Register reads are serialized (not concurrent) to prevent
        transaction ID desynchronization issues with pymodbus and some
        Modbus TCP gateways (e.g., Waveshare RS485-to-Ethernet adapters).

        Returns:
            Runtime data with all values properly scaled

        Raises:
            TransportReadError: If read operation fails
        """
        input_registers = await self._read_register_groups()
        return InverterRuntimeData.from_modbus_registers(input_registers, self.runtime_register_map)

    async def read_energy(self) -> InverterEnergyData:
        """Read energy statistics via Modbus input registers.

        Uses the appropriate energy register map based on the inverter_family
        parameter. Different models have different register layouts for energy
        data (e.g., LXP_EU uses 16-bit daily values vs 32-bit for PV_SERIES).

        Note: Register reads are serialized to prevent transaction ID issues.

        Returns:
            Energy data with all values in kWh

        Raises:
            TransportReadError: If read operation fails
        """
        # power_energy (0-31) contains PV daily energy at registers 28-30
        # status_energy (32-63) contains daily/lifetime energy counters
        input_registers = await self._read_register_groups(["power_energy", "status_energy"])

        # bms_data (80-112) is supplementary — don't fail the entire energy read
        # if these registers time out (e.g., on some firmware versions)
        try:
            bms_registers = await self._read_register_groups(["bms_data"])
            input_registers.update(bms_registers)
        except (TransportReadError, TransportTimeoutError):
            _LOGGER.debug(
                "bms_data registers (80-112) unavailable for %s, continuing without them",
                self._serial,
            )

        return InverterEnergyData.from_modbus_registers(input_registers, self.energy_register_map)

    async def read_battery(
        self,
        include_individual: bool = True,
    ) -> BatteryBankData | None:
        """Read battery information via Modbus.

        Reads core battery data (registers 0-31), BMS passthrough data
        (registers 80-112), and optionally individual battery data from
        extended registers (5000+) for comprehensive battery monitoring.

        Uses the register map for correct register addresses and scaling,
        ensuring extensibility for different inverter families.

        Args:
            include_individual: If True (default), also reads extended registers
                (5000+) for individual battery module data. Set to False if you
                only need aggregate battery bank data.

        Returns:
            Battery bank data with available information, None if no battery

        Raises:
            TransportReadError: If read operation fails
        """
        from pylxpweb.transports.register_maps import (
            INDIVIDUAL_BATTERY_BASE_ADDRESS,
            INDIVIDUAL_BATTERY_MAX_COUNT,
            INDIVIDUAL_BATTERY_REGISTER_COUNT,
        )

        # Reconnect if too many consecutive errors (transaction ID desync recovery)
        if self._consecutive_errors >= self._max_consecutive_errors:
            await self._reconnect()

        # Read power/energy registers (0-31) and BMS registers (80-112)
        # Combine into single dict for factory method
        all_registers: dict[int, int] = {}

        # Read core battery registers (0-31)
        power_regs = await self._read_input_registers(0, 32)
        for i, value in enumerate(power_regs):
            all_registers[i] = value

        # Read BMS registers (80-112)
        try:
            bms_values = await self._read_input_registers(80, 33)
            for offset, value in enumerate(bms_values):
                all_registers[80 + offset] = value
        except Exception as e:
            _LOGGER.warning("Failed to read BMS registers 80-112: %s", e)
            # Continue with basic battery data even if BMS read fails

        # Get battery count from register 96 to optimize reads
        battery_count = all_registers.get(96, 0)

        # Read individual battery registers (5000+) if requested
        individual_registers: dict[int, int] | None = None
        if include_individual and battery_count > 0:
            individual_registers = {}
            # Calculate how many batteries to read (min of count and max supported)
            batteries_to_read = min(battery_count, INDIVIDUAL_BATTERY_MAX_COUNT)
            # Calculate total registers needed
            total_registers = batteries_to_read * INDIVIDUAL_BATTERY_REGISTER_COUNT

            try:
                # Read in chunks of 40 registers (Modbus limit)
                start_addr = INDIVIDUAL_BATTERY_BASE_ADDRESS
                remaining = total_registers
                current_addr = start_addr

                while remaining > 0:
                    chunk_size = min(remaining, 40)
                    values = await self._read_input_registers(current_addr, chunk_size)
                    for offset, value in enumerate(values):
                        individual_registers[current_addr + offset] = value
                    current_addr += chunk_size
                    remaining -= chunk_size

                _LOGGER.debug(
                    "Read individual battery data for %d batteries from registers %d-%d",
                    batteries_to_read,
                    INDIVIDUAL_BATTERY_BASE_ADDRESS,
                    current_addr - 1,
                )
            except Exception as e:
                _LOGGER.warning(
                    "Failed to read individual battery registers (5000+): %s. "
                    "Individual battery data will not be available.",
                    e,
                )
                individual_registers = None

        # Use factory method with register map and individual battery data
        result = BatteryBankData.from_modbus_registers(
            all_registers,
            self.runtime_register_map,
            individual_registers,
        )

        if result is None:
            _LOGGER.debug(
                "Battery voltage below threshold, assuming no battery present. "
                "If batteries are installed, check Modbus register mapping."
            )
        elif result.batteries:
            _LOGGER.debug(
                "Loaded %d individual batteries via Modbus",
                len(result.batteries),
            )

        return result

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

        Returns:
            10-character serial number string (e.g., "BA12345678")

        Raises:
            TransportReadError: If read operation fails
        """
        return await read_serial_number_async(self._read_input_registers, self._serial)

    async def read_firmware_version(self) -> str:
        """Read full firmware version code from holding registers 7-10.

        Returns:
            Full firmware code string (e.g., "FAAB-2525") or empty string
        """
        return await read_firmware_version_async(self._read_holding_registers)

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

    async def read_device_type(self) -> int:
        """Read device type code from register 19.

        Known device type codes:
        - 50: MID/GridBOSS (Microgrid Interconnect Device)
        - 54: SNA Series
        - 2092: PV Series (18KPV)
        - 10284: FlexBOSS21/FlexBOSS18

        Returns:
            Device type code integer

        Raises:
            TransportReadError: If read operation fails
        """
        return await read_device_type_async(self._read_holding_registers)

    def is_midbox_device(self, device_type_code: int) -> bool:
        """Check if device type code indicates a MID/GridBOSS device."""
        return is_midbox_device(device_type_code)

    async def read_parallel_config(self) -> int:
        """Read parallel configuration from input register 113.

        Returns:
            Raw 16-bit value with packed parallel config, or 0 if read fails.

        Raises:
            TransportReadError: If read operation fails
        """
        return await read_parallel_config_async(self._read_input_registers, self._serial)

    async def read_midbox_runtime(self) -> MidboxRuntimeData:
        """Read runtime data from a MID/GridBOSS device.

        GridBOSS devices use INPUT registers (function 0x04) for runtime data,
        with the same register layout as inverters.

        Returns:
            MidboxRuntimeData with all values properly scaled:
            - Voltages in V (no scaling)
            - Currents in A (scaled /100)
            - Power in W (no scaling, signed)
            - Frequency in Hz (scaled /100)

        Raises:
            TransportReadError: If read operation fails
        """
        from pylxpweb.transports.register_maps import GRIDBOSS_RUNTIME_MAP

        # Read INPUT registers (same as inverters)
        # Group 1: Registers 0-41 (voltages, currents, power, smart load power)
        # Group 2: Registers 128-131 (frequencies)
        input_registers: dict[int, int] = {}

        try:
            # Read voltages, currents, power, and smart load power (registers 0-41)
            values = await self._read_input_registers(0, 42)
            for offset, value in enumerate(values):
                input_registers[offset] = value

            # Read frequencies (registers 128-131)
            freq_values = await self._read_input_registers(128, 4)
            for offset, value in enumerate(freq_values):
                input_registers[128 + offset] = value

        except Exception as e:
            _LOGGER.error("Failed to read MID input registers: %s", e)
            raise TransportReadError(f"Failed to read MID registers: {e}") from e

        return MidboxRuntimeData.from_modbus_registers(input_registers, GRIDBOSS_RUNTIME_MAP)
