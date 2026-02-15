"""Shared register data operations for Modbus-based transports.

Provides ``RegisterDataMixin`` which implements all register-level data
reading/writing methods shared between ``BaseModbusTransport`` and
``DongleTransport``.  The mixin assumes the host class exposes:

- ``_read_input_registers(start, count) -> list[int]``
- ``_read_holding_registers(start, count) -> list[int]``
- ``_write_holding_registers(start, values) -> None``
- ``_serial: str``
- ``_inter_register_delay: float``
- ``_inverter_family: InverterFamily | None``

At *runtime* ``_DataMixinBase`` resolves to ``object`` so the MRO is
unchanged.  Under ``TYPE_CHECKING`` it supplies typed stubs for mypy.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from pylxpweb.registers import (
    BATTERY_BASE_ADDRESS,
    BATTERY_MAX_COUNT,
    BATTERY_REGISTER_COUNT,
)

from ._register_readers import (
    is_midbox_device,
    read_device_type_async,
    read_firmware_version_async,
    read_parallel_config_async,
    read_serial_number_async,
)
from .data import (
    BatteryBankData,
    InverterEnergyData,
    InverterRuntimeData,
    MidboxRuntimeData,
)
from .exceptions import TransportReadError, TransportTimeoutError

if TYPE_CHECKING:
    from pylxpweb.devices.inverters._features import InverterFamily

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Register group constants (unified across Modbus and Dongle transports)
# ---------------------------------------------------------------------------
# Based on the 40-register-per-call hardware limit shared by both pymodbus
# and the WiFi dongle protocol.
#
# Source: EG4-18KPV-12LV Modbus Protocol + eg4-modbus-monitor + Yippy's BMS docs

INPUT_REGISTER_GROUPS: dict[str, tuple[int, int]] = {
    "power_energy": (0, 32),  # Registers 0-31: Power, voltage, SOC/SOH, current
    "status_energy": (32, 32),  # Registers 32-63: Status, energy, fault/warning codes
    "temperatures": (64, 16),  # Registers 64-79: Temps, currents, fault history
    "bms_data": (80, 33),  # Registers 80-112: BMS passthrough data
    "extended_data": (113, 18),  # Registers 113-130: Parallel config, generator, EPS
    "eps_split_phase": (140, 3),  # Registers 140-142: EPS L1/L2 voltages
    "output_power": (170, 2),  # Registers 170-171: Output power
    "split_phase_grid": (193, 4),  # Registers 193-196: Split-phase grid L1/L2 voltages
}

# GridBOSS/MID register groups for ``read_midbox_runtime``
MIDBOX_REGISTER_GROUPS: list[tuple[int, int]] = [
    (0, 40),  # Voltages, currents, power, smart loads 1-3
    (40, 28),  # Smart load 4 power + energy today
    (68, 40),  # Energy totals
    (108, 12),  # AC couple port 3-4 totals
    (128, 4),  # Frequencies
]

# ---------------------------------------------------------------------------
# TYPE_CHECKING-only base class for mixin attribute stubs
# ---------------------------------------------------------------------------

if TYPE_CHECKING:

    class _DataMixinBase:
        """Typed stubs so mypy sees attributes provided by the host class."""

        _serial: str
        _inter_register_delay: float
        _inverter_family: InverterFamily | None

        async def _read_input_registers(self, start: int, count: int) -> list[int]: ...

        async def _read_holding_registers(self, start: int, count: int) -> list[int]: ...

        async def _write_holding_registers(self, start: int, values: list[int]) -> bool: ...

else:
    _DataMixinBase = object


# ---------------------------------------------------------------------------
# Mixin
# ---------------------------------------------------------------------------


class RegisterDataMixin(_DataMixinBase):
    """Shared register data reading/writing for Modbus-based transports.

    Concrete transports must provide the low-level register I/O methods
    (``_read_input_registers``, ``_read_holding_registers``,
    ``_write_holding_registers``) and set ``_inter_register_delay``
    in their ``__init__``.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _registers_from_values(start: int, values: list[int]) -> dict[int, int]:
        """Build address-to-value dict from a contiguous register read."""
        return {start + offset: value for offset, value in enumerate(values)}

    # ------------------------------------------------------------------
    # Register group reading
    # ------------------------------------------------------------------

    async def _read_register_groups(
        self,
        group_names: list[str] | None = None,
    ) -> dict[int, int]:
        """Read multiple register groups sequentially with inter-group delays.

        Subclasses (e.g. BaseModbusTransport) may override this to add
        adaptive delay or auto-reconnect logic.

        Args:
            group_names: Specific group names from ``INPUT_REGISTER_GROUPS``.
                If *None*, reads all groups.

        Returns:
            Dict mapping register address to value.

        Raises:
            TransportReadError: If any group read fails.
        """
        if group_names is None:
            groups = list(INPUT_REGISTER_GROUPS.items())
        else:
            groups = [
                (name, INPUT_REGISTER_GROUPS[name])
                for name in group_names
                if name in INPUT_REGISTER_GROUPS
            ]

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

            if i < len(groups) - 1:
                await asyncio.sleep(self._inter_register_delay)

        return registers

    # ------------------------------------------------------------------
    # Device data methods
    # ------------------------------------------------------------------

    async def read_runtime(self) -> InverterRuntimeData:
        """Read runtime data via input registers.

        Returns:
            Runtime data with all values properly scaled.

        Raises:
            TransportReadError: If read operation fails.
        """
        input_registers = await self._read_register_groups()
        family = self._inverter_family.value if self._inverter_family else "EG4_HYBRID"
        return InverterRuntimeData.from_modbus_registers(input_registers, family)

    async def read_energy(self) -> InverterEnergyData:
        """Read energy statistics via input registers.

        Returns:
            Energy data with all values in kWh.

        Raises:
            TransportReadError: If read operation fails.
        """
        input_registers = await self._read_register_groups(["power_energy", "status_energy"])

        # bms_data is supplementary — don't fail the entire energy read
        # if these registers time out
        try:
            bms_registers = await self._read_register_groups(["bms_data"])
            input_registers.update(bms_registers)
        except (TransportReadError, TransportTimeoutError):
            _LOGGER.debug(
                "bms_data registers unavailable for %s, continuing without them",
                self._serial,
            )

        family = self._inverter_family.value if self._inverter_family else "EG4_HYBRID"
        return InverterEnergyData.from_modbus_registers(input_registers, family)

    async def read_battery(
        self,
        include_individual: bool = True,
    ) -> BatteryBankData | None:
        """Read battery information via registers.

        Args:
            include_individual: If True, also reads extended registers (5000+)
                for individual battery module data.

        Returns:
            Battery bank data, or *None* if no battery detected.

        Raises:
            TransportReadError: If read operation fails.
        """
        all_registers: dict[int, int] = {}

        # Read core battery registers (power + BMS).
        # Registers 0-31 contain power/voltage/SOC; 80-112 contain BMS data.
        try:
            power_regs = await self._read_input_registers(0, 32)
            all_registers.update(self._registers_from_values(0, power_regs))
        except Exception as e:
            _LOGGER.warning("Failed to read power registers 0-31: %s", e)

        try:
            bms_regs = await self._read_input_registers(80, 33)
            all_registers.update(self._registers_from_values(80, bms_regs))
        except Exception as e:
            _LOGGER.warning("Failed to read BMS registers 80-112: %s", e)

        # Read individual battery registers (5000+) if requested
        battery_count = all_registers.get(96, 0)
        individual_registers: dict[int, int] | None = None

        if include_individual and battery_count > 0:
            individual_registers = {}
            batteries_to_read = min(battery_count, BATTERY_MAX_COUNT)
            total_registers = batteries_to_read * BATTERY_REGISTER_COUNT

            try:
                current_addr = BATTERY_BASE_ADDRESS
                remaining = total_registers

                while remaining > 0:
                    chunk_size = min(remaining, 40)
                    values = await self._read_input_registers(current_addr, chunk_size)
                    individual_registers.update(self._registers_from_values(current_addr, values))
                    current_addr += chunk_size
                    remaining -= chunk_size

                _LOGGER.debug(
                    "Read individual battery data for %d batteries from registers %d-%d",
                    batteries_to_read,
                    BATTERY_BASE_ADDRESS,
                    current_addr - 1,
                )
            except Exception as e:
                _LOGGER.warning(
                    "Failed to read individual battery registers (5000+): %s",
                    e,
                )
                individual_registers = None

        result = BatteryBankData.from_modbus_registers(
            all_registers,
            individual_registers,
        )

        if result is None:
            _LOGGER.debug("Battery voltage below threshold, assuming no battery present")
        elif result.batteries:
            _LOGGER.debug(
                "Loaded %d individual batteries via registers",
                len(result.batteries),
            )

        return result

    async def read_all_input_data(
        self,
    ) -> tuple[InverterRuntimeData, InverterEnergyData, BatteryBankData | None]:
        """Read all input register groups once, returning runtime + energy + battery.

        Reduces Modbus transactions by reading each register group exactly once
        and constructing all three data types from the shared snapshot.

        BMS data failure is non-fatal to match ``read_energy()`` resilience.

        Returns:
            Tuple of (runtime_data, energy_data, battery_data_or_none).
        """
        input_registers: dict[int, int] = {}

        for i, (group_name, (start, count)) in enumerate(INPUT_REGISTER_GROUPS.items()):
            try:
                values = await self._read_input_registers(start, count)
                for offset, value in enumerate(values):
                    input_registers[start + offset] = value
            except Exception:
                if group_name == "bms_data":
                    _LOGGER.debug(
                        "bms_data registers unavailable for %s, continuing",
                        self._serial,
                    )
                    continue
                raise

            if i < len(INPUT_REGISTER_GROUPS) - 1:
                await asyncio.sleep(self._inter_register_delay)

        family = self._inverter_family.value if self._inverter_family else "EG4_HYBRID"

        # Construct all three data types from the shared snapshot
        runtime = InverterRuntimeData.from_modbus_registers(input_registers, family)
        energy = InverterEnergyData.from_modbus_registers(input_registers, family)

        # Read individual battery registers (5000+) if present
        battery_count = input_registers.get(96, 0)
        individual_registers: dict[int, int] | None = None

        if battery_count > 0:
            individual_registers = {}
            batteries_to_read = min(battery_count, BATTERY_MAX_COUNT)
            total_registers = batteries_to_read * BATTERY_REGISTER_COUNT

            try:
                current_addr = BATTERY_BASE_ADDRESS
                remaining = total_registers

                while remaining > 0:
                    chunk_size = min(remaining, 40)
                    values = await self._read_input_registers(current_addr, chunk_size)
                    individual_registers.update(self._registers_from_values(current_addr, values))
                    current_addr += chunk_size
                    remaining -= chunk_size
            except Exception as e:
                _LOGGER.warning("Failed to read individual battery registers: %s", e)
                individual_registers = None

        battery = BatteryBankData.from_modbus_registers(
            input_registers,
            individual_registers,
        )

        return runtime, energy, battery

    async def read_midbox_runtime(self) -> MidboxRuntimeData:
        """Read runtime data from a MID/GridBOSS device.

        Returns:
            MidboxRuntimeData with all values properly scaled.

        Raises:
            TransportReadError: If read operation fails.
        """
        input_registers: dict[int, int] = {}

        try:
            for i, (start, count) in enumerate(MIDBOX_REGISTER_GROUPS):
                values = await self._read_input_registers(start, count)
                input_registers.update(self._registers_from_values(start, values))

                if i < len(MIDBOX_REGISTER_GROUPS) - 1:
                    await asyncio.sleep(self._inter_register_delay)

        except Exception as e:
            _LOGGER.error("Failed to read MID input registers: %s", e)
            raise TransportReadError(f"Failed to read MID registers: {e}") from e

        # Smart port mode is stored as a bit-packed value in holding register 20
        # (2 bits per port, LSB-first: bits 0-1 = port 1, bits 2-3 = port 2, etc.)
        # Values: 0 = off, 1 = smart_load, 2 = ac_couple
        # Delay before switching from input (FC 04) to holding (FC 03) registers —
        # WiFi dongles need time between function code changes to avoid corrupt reads.
        await asyncio.sleep(self._inter_register_delay)
        smart_port_mode_reg: int | None = None
        try:
            holding_vals = await self._read_holding_registers(20, 1)
            smart_port_mode_reg = holding_vals[0]
        except Exception:
            _LOGGER.debug("Failed to read smart port mode register 20")

        return MidboxRuntimeData.from_modbus_registers(
            input_registers, smart_port_mode_reg=smart_port_mode_reg
        )

    async def read_parameters(
        self,
        start_address: int,
        count: int,
    ) -> dict[int, int]:
        """Read configuration parameters via holding registers.

        Args:
            start_address: Starting register address.
            count: Number of registers to read (chunked at 40 per call).

        Returns:
            Dict mapping register address to raw integer value.

        Raises:
            TransportReadError: If read operation fails.
        """
        result: dict[int, int] = {}
        remaining = count
        current_address = start_address

        while remaining > 0:
            chunk_size = min(remaining, 40)
            values = await self._read_holding_registers(current_address, chunk_size)
            result.update(self._registers_from_values(current_address, values))
            current_address += chunk_size
            remaining -= chunk_size

        return result

    async def write_parameters(
        self,
        parameters: dict[int, int],
    ) -> bool:
        """Write configuration parameters via holding registers.

        Groups consecutive addresses into batch writes for efficiency.

        Args:
            parameters: Dict mapping register address to value.

        Returns:
            True if all writes succeeded.

        Raises:
            TransportWriteError: If any write fails.
        """
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
                current_values.append(value)
            else:
                groups.append((current_start, current_values))
                current_start = address
                current_values = [value]

        if current_start is not None and current_values:
            groups.append((current_start, current_values))

        for start_address, values in groups:
            await self._write_holding_registers(start_address, values)

        return True

    # ------------------------------------------------------------------
    # Device info / discovery (delegates to _register_readers.py)
    # ------------------------------------------------------------------

    async def read_serial_number(self) -> str:
        """Read inverter serial number from input registers 115-119."""
        return await read_serial_number_async(self._read_input_registers, self._serial)

    async def read_firmware_version(self) -> str:
        """Read firmware version from holding registers 7-10."""
        return await read_firmware_version_async(self._read_holding_registers)

    async def read_device_type(self) -> int:
        """Read device type code from holding register 19."""
        return await read_device_type_async(self._read_holding_registers)

    def is_midbox_device(self, device_type_code: int) -> bool:
        """Check if device type code indicates a MID/GridBOSS device."""
        return is_midbox_device(device_type_code)

    async def read_parallel_config(self) -> int:
        """Read parallel configuration from input register 113."""
        return await read_parallel_config_async(self._read_input_registers, self._serial)

    async def validate_serial(self, expected_serial: str) -> bool:
        """Validate that the connected inverter matches the expected serial."""
        actual_serial = await self.read_serial_number()
        matches = actual_serial == expected_serial

        if not matches:
            _LOGGER.warning(
                "Serial mismatch: expected %s, got %s",
                expected_serial,
                actual_serial,
            )

        return matches
