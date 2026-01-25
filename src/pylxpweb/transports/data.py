"""Transport-agnostic data models.

This module provides data classes that represent inverter data
in a transport-agnostic way. Both HTTP and Modbus transports
produce these same data structures with scaling already applied.

All values are in standard units:
- Voltage: Volts (V)
- Current: Amperes (A)
- Power: Watts (W)
- Energy: Watt-hours (Wh) or Kilowatt-hours (kWh) as noted
- Temperature: Celsius (°C)
- Frequency: Hertz (Hz)
- Percentage: 0-100 (%)

Data classes include validation in __post_init__ to clamp percentage
values (SOC, SOH) to valid 0-100 range and log warnings for out-of-range values.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pylxpweb.models import EnergyInfo, InverterRuntime
    from pylxpweb.transports.register_maps import (
        EnergyRegisterMap,
        RegisterField,
        RuntimeRegisterMap,
    )

_LOGGER = logging.getLogger(__name__)


def _read_register_field(
    registers: dict[int, int],
    field_def: RegisterField | None,
    default: int = 0,
) -> int:
    """Read a value from registers using a RegisterField definition.

    Args:
        registers: Dict mapping register address to raw value
        field_def: RegisterField defining how to read the value, or None
        default: Default value if field is None or register not found

    Returns:
        Raw integer value (no scaling applied yet)
    """
    if field_def is None:
        return default

    if field_def.bit_width == 32:
        # 32-bit value: high word at address, low word at address+1
        high = registers.get(field_def.address, 0)
        low = registers.get(field_def.address + 1, 0)
        value = (high << 16) | low
    else:
        # 16-bit value
        value = registers.get(field_def.address, default)

    # Handle signed values
    if field_def.signed:
        if field_def.bit_width == 16 and value > 32767:
            value = value - 65536
        elif field_def.bit_width == 32 and value > 2147483647:
            value = value - 4294967296

    return value


def _read_and_scale_field(
    registers: dict[int, int],
    field_def: RegisterField | None,
    default: float = 0.0,
) -> float:
    """Read a value from registers and apply scaling.

    Args:
        registers: Dict mapping register address to raw value
        field_def: RegisterField defining how to read and scale the value
        default: Default value if field is None or register not found

    Returns:
        Scaled floating-point value
    """
    if field_def is None:
        return default

    from pylxpweb.constants.scaling import apply_scale

    raw_value = _read_register_field(registers, field_def, int(default))
    return apply_scale(raw_value, field_def.scale_factor)


def _clamp_percentage(value: int, name: str) -> int:
    """Clamp percentage value to 0-100 range, logging if out of bounds."""
    if value < 0:
        _LOGGER.warning("%s value %d is negative, clamping to 0", name, value)
        return 0
    if value > 100:
        _LOGGER.warning("%s value %d exceeds 100%%, clamping to 100", name, value)
        return 100
    return value


@dataclass
class InverterDeviceInfo:
    """Inverter device identification and version information.

    This data class holds static device information like serial number,
    firmware versions, and model identification. For Modbus, these come
    from holding registers 9-10 (com_version, controller_version).
    """

    # Serial number (10-digit string)
    serial_number: str = ""

    # Firmware versions from holding registers
    com_version: int = 0  # Communication firmware version (holding reg 9)
    controller_version: int = 0  # Controller firmware version (holding reg 10)

    # Derived/formatted version string
    firmware_version: str = ""

    def __post_init__(self) -> None:
        """Generate firmware version string from raw version numbers."""
        if not self.firmware_version and (self.com_version or self.controller_version):
            # Format as "COM:vXX CTRL:vXX" or similar
            self.firmware_version = f"v{self.controller_version}.{self.com_version}"

    @classmethod
    def from_modbus_registers(
        cls,
        holding_registers: dict[int, int],
        serial_number: str = "",
    ) -> InverterDeviceInfo:
        """Create InverterDeviceInfo from Modbus holding registers.

        Args:
            holding_registers: Dict mapping register address to raw value
            serial_number: Serial number (if already known)

        Returns:
            InverterDeviceInfo with values from registers
        """
        com_version = holding_registers.get(9, 0)
        controller_version = holding_registers.get(10, 0)

        return cls(
            serial_number=serial_number,
            com_version=com_version,
            controller_version=controller_version,
        )


@dataclass
class InverterRuntimeData:
    """Real-time inverter operating data.

    All values are already scaled to proper units.
    This is the transport-agnostic representation of runtime data.

    Validation:
        - battery_soc and battery_soh are clamped to 0-100 range
    """

    # Timestamp
    timestamp: datetime = field(default_factory=datetime.now)

    # PV Input
    pv1_voltage: float = 0.0  # V
    pv1_current: float = 0.0  # A
    pv1_power: float = 0.0  # W
    pv2_voltage: float = 0.0  # V
    pv2_current: float = 0.0  # A
    pv2_power: float = 0.0  # W
    pv3_voltage: float = 0.0  # V
    pv3_current: float = 0.0  # A
    pv3_power: float = 0.0  # W
    pv_total_power: float = 0.0  # W

    # Battery
    battery_voltage: float = 0.0  # V
    battery_current: float = 0.0  # A
    battery_soc: int = 0  # %
    battery_soh: int = 100  # %
    battery_charge_power: float = 0.0  # W
    battery_discharge_power: float = 0.0  # W
    battery_temperature: float = 0.0  # °C

    # Grid (AC Input)
    grid_voltage_r: float = 0.0  # V (Phase R/L1)
    grid_voltage_s: float = 0.0  # V (Phase S/L2)
    grid_voltage_t: float = 0.0  # V (Phase T/L3)
    grid_current_r: float = 0.0  # A
    grid_current_s: float = 0.0  # A
    grid_current_t: float = 0.0  # A
    grid_frequency: float = 0.0  # Hz
    grid_power: float = 0.0  # W (positive = import, negative = export)
    power_to_grid: float = 0.0  # W (export)
    power_from_grid: float = 0.0  # W (import)

    # Inverter Output
    inverter_power: float = 0.0  # W
    inverter_current_r: float = 0.0  # A
    inverter_current_s: float = 0.0  # A
    inverter_current_t: float = 0.0  # A
    power_factor: float = 1.0  # 0.0-1.0

    # EPS/Off-Grid Output
    eps_voltage_r: float = 0.0  # V
    eps_voltage_s: float = 0.0  # V
    eps_voltage_t: float = 0.0  # V
    eps_frequency: float = 0.0  # Hz
    eps_power: float = 0.0  # W
    eps_status: int = 0  # Status code

    # Load
    load_power: float = 0.0  # W

    # Internal
    bus_voltage_1: float = 0.0  # V
    bus_voltage_2: float = 0.0  # V

    # Temperatures
    internal_temperature: float = 0.0  # °C
    radiator_temperature_1: float = 0.0  # °C
    radiator_temperature_2: float = 0.0  # °C

    # Status
    device_status: int = 0  # Status code
    fault_code: int = 0  # Fault code
    warning_code: int = 0  # Warning code

    # -------------------------------------------------------------------------
    # Extended Sensors - Inverter RMS Current & Power
    # -------------------------------------------------------------------------
    inverter_rms_current: float = 0.0  # A (Inverter RMS current)
    inverter_apparent_power: float = 0.0  # VA (Inverter apparent power)

    # -------------------------------------------------------------------------
    # Generator Input (if connected)
    # -------------------------------------------------------------------------
    generator_voltage: float = 0.0  # V
    generator_frequency: float = 0.0  # Hz
    generator_power: float = 0.0  # W

    # -------------------------------------------------------------------------
    # BMS Limits and Cell Data
    # -------------------------------------------------------------------------
    bms_charge_current_limit: float = 0.0  # A (Max charge current from BMS)
    bms_discharge_current_limit: float = 0.0  # A (Max discharge current from BMS)
    bms_charge_voltage_ref: float = 0.0  # V (BMS charge voltage reference)
    bms_discharge_cutoff: float = 0.0  # V (BMS discharge cutoff voltage)
    bms_max_cell_voltage: float = 0.0  # V (Highest cell voltage)
    bms_min_cell_voltage: float = 0.0  # V (Lowest cell voltage)
    bms_max_cell_temperature: float = 0.0  # °C (Highest cell temp)
    bms_min_cell_temperature: float = 0.0  # °C (Lowest cell temp)
    bms_cycle_count: int = 0  # Charge/discharge cycle count
    battery_parallel_num: int = 0  # Number of parallel battery units
    battery_capacity_ah: float = 0.0  # Ah (Battery capacity)

    # -------------------------------------------------------------------------
    # Additional Temperatures
    # -------------------------------------------------------------------------
    temperature_t1: float = 0.0  # °C
    temperature_t2: float = 0.0  # °C
    temperature_t3: float = 0.0  # °C
    temperature_t4: float = 0.0  # °C
    temperature_t5: float = 0.0  # °C

    # -------------------------------------------------------------------------
    # Inverter Operational
    # -------------------------------------------------------------------------
    inverter_on_time: int = 0  # hours (total on time)
    ac_input_type: int = 0  # AC input type code

    # -------------------------------------------------------------------------
    # Parallel Configuration (decoded from register 113)
    # -------------------------------------------------------------------------
    parallel_master_slave: int = 0  # 0=no parallel, 1=master, 2=slave, 3=3-phase master
    parallel_phase: int = 0  # 0=R, 1=S, 2=T
    parallel_number: int = 0  # unit ID in parallel system (0-255)

    def __post_init__(self) -> None:
        """Validate and clamp percentage values."""
        self.battery_soc = _clamp_percentage(self.battery_soc, "battery_soc")
        self.battery_soh = _clamp_percentage(self.battery_soh, "battery_soh")

    @classmethod
    def from_http_response(cls, runtime: InverterRuntime) -> InverterRuntimeData:
        """Create from HTTP API InverterRuntime response.

        Args:
            runtime: Pydantic model from HTTP API

        Returns:
            Transport-agnostic runtime data with scaling applied
        """
        # Import scaling functions
        from pylxpweb.constants.scaling import scale_runtime_value

        return cls(
            timestamp=datetime.now(),
            # PV - API returns values needing /10 scaling
            pv1_voltage=scale_runtime_value("vpv1", runtime.vpv1),
            pv1_power=float(runtime.ppv1 or 0),
            pv2_voltage=scale_runtime_value("vpv2", runtime.vpv2),
            pv2_power=float(runtime.ppv2 or 0),
            pv3_voltage=scale_runtime_value("vpv3", runtime.vpv3 or 0),
            pv3_power=float(runtime.ppv3 or 0),
            pv_total_power=float(runtime.ppv or 0),
            # Battery
            battery_voltage=scale_runtime_value("vBat", runtime.vBat),
            battery_soc=runtime.soc or 0,
            battery_charge_power=float(runtime.pCharge or 0),
            battery_discharge_power=float(runtime.pDisCharge or 0),
            battery_temperature=float(runtime.tBat or 0),
            # Grid
            grid_voltage_r=scale_runtime_value("vacr", runtime.vacr),
            grid_voltage_s=scale_runtime_value("vacs", runtime.vacs),
            grid_voltage_t=scale_runtime_value("vact", runtime.vact),
            grid_frequency=scale_runtime_value("fac", runtime.fac),
            grid_power=float(runtime.prec or 0),
            power_to_grid=float(runtime.pToGrid or 0),
            power_from_grid=float(runtime.prec or 0),
            # Inverter
            inverter_power=float(runtime.pinv or 0),
            # EPS
            eps_voltage_r=scale_runtime_value("vepsr", runtime.vepsr),
            eps_voltage_s=scale_runtime_value("vepss", runtime.vepss),
            eps_voltage_t=scale_runtime_value("vepst", runtime.vepst),
            eps_frequency=scale_runtime_value("feps", runtime.feps),
            eps_power=float(runtime.peps or 0),
            eps_status=runtime.seps or 0,
            # Load
            load_power=float(runtime.pToUser or 0),
            # Internal
            bus_voltage_1=scale_runtime_value("vBus1", runtime.vBus1),
            bus_voltage_2=scale_runtime_value("vBus2", runtime.vBus2),
            # Temperatures
            internal_temperature=float(runtime.tinner or 0),
            radiator_temperature_1=float(runtime.tradiator1 or 0),
            radiator_temperature_2=float(runtime.tradiator2 or 0),
            # Status
            device_status=runtime.status or 0,
            # Note: InverterRuntime doesn't have faultCode/warningCode fields
        )

    @classmethod
    def from_modbus_registers(
        cls,
        input_registers: dict[int, int],
        register_map: RuntimeRegisterMap | None = None,
    ) -> InverterRuntimeData:
        """Create from Modbus input register values.

        Register mappings based on:
        - EG4-18KPV-12LV Modbus Protocol specification
        - eg4-modbus-monitor project (https://github.com/galets/eg4-modbus-monitor)
        - Yippy's BMS documentation (https://github.com/joyfulhouse/pylxpweb/issues/97)
        - Yippy's LXP-EU 12K corrections (https://github.com/joyfulhouse/pylxpweb/issues/52)

        Args:
            input_registers: Dict mapping register address to raw value
            register_map: Optional RuntimeRegisterMap for model-specific register
                locations. If None, defaults to PV_SERIES_RUNTIME_MAP for
                backward compatibility.

        Returns:
            Transport-agnostic runtime data with scaling applied
        """
        from pylxpweb.transports.register_maps import PV_SERIES_RUNTIME_MAP

        # Use default map if none provided (backward compatible)
        if register_map is None:
            register_map = PV_SERIES_RUNTIME_MAP

        # Read power values using register map
        pv1_power = _read_and_scale_field(input_registers, register_map.pv1_power)
        pv2_power = _read_and_scale_field(input_registers, register_map.pv2_power)
        pv3_power = _read_and_scale_field(input_registers, register_map.pv3_power)
        charge_power = _read_and_scale_field(input_registers, register_map.charge_power)
        discharge_power = _read_and_scale_field(input_registers, register_map.discharge_power)
        inverter_power = _read_and_scale_field(input_registers, register_map.inverter_power)
        grid_power = _read_and_scale_field(input_registers, register_map.grid_power)
        eps_power = _read_and_scale_field(input_registers, register_map.eps_power)
        load_power = _read_and_scale_field(input_registers, register_map.load_power)

        # SOC/SOH packed register (low byte = SOC, high byte = SOH)
        soc_soh_packed = _read_register_field(input_registers, register_map.soc_soh_packed)
        battery_soc = soc_soh_packed & 0xFF
        battery_soh = (soc_soh_packed >> 8) & 0xFF

        # Fault/warning codes
        inverter_fault_code = _read_register_field(
            input_registers, register_map.inverter_fault_code
        )
        inverter_warning_code = _read_register_field(
            input_registers, register_map.inverter_warning_code
        )
        bms_fault_code = _read_register_field(input_registers, register_map.bms_fault_code)
        bms_warning_code = _read_register_field(input_registers, register_map.bms_warning_code)

        # Combine fault/warning codes (inverter + BMS)
        fault_code = inverter_fault_code if inverter_fault_code else bms_fault_code
        warning_code = inverter_warning_code if inverter_warning_code else bms_warning_code

        return cls(
            timestamp=datetime.now(),
            # PV
            pv1_voltage=_read_and_scale_field(input_registers, register_map.pv1_voltage),
            pv1_power=pv1_power,
            pv2_voltage=_read_and_scale_field(input_registers, register_map.pv2_voltage),
            pv2_power=pv2_power,
            pv3_voltage=_read_and_scale_field(input_registers, register_map.pv3_voltage),
            pv3_power=pv3_power,
            pv_total_power=pv1_power + pv2_power + pv3_power,
            # Battery - SOC/SOH from packed register
            battery_voltage=_read_and_scale_field(input_registers, register_map.battery_voltage),
            battery_current=_read_and_scale_field(input_registers, register_map.battery_current),
            battery_soc=battery_soc,
            battery_soh=battery_soh if battery_soh > 0 else 100,
            battery_charge_power=charge_power,
            battery_discharge_power=discharge_power,
            battery_temperature=_read_and_scale_field(
                input_registers, register_map.battery_temperature
            ),
            # Grid
            grid_voltage_r=_read_and_scale_field(input_registers, register_map.grid_voltage_r),
            grid_voltage_s=_read_and_scale_field(input_registers, register_map.grid_voltage_s),
            grid_voltage_t=_read_and_scale_field(input_registers, register_map.grid_voltage_t),
            grid_frequency=_read_and_scale_field(input_registers, register_map.grid_frequency),
            grid_power=grid_power,
            power_to_grid=_read_and_scale_field(input_registers, register_map.power_to_grid),
            power_from_grid=grid_power,
            # Inverter
            inverter_power=inverter_power,
            # EPS
            eps_voltage_r=_read_and_scale_field(input_registers, register_map.eps_voltage_r),
            eps_voltage_s=_read_and_scale_field(input_registers, register_map.eps_voltage_s),
            eps_voltage_t=_read_and_scale_field(input_registers, register_map.eps_voltage_t),
            eps_frequency=_read_and_scale_field(input_registers, register_map.eps_frequency),
            eps_power=eps_power,
            eps_status=_read_register_field(input_registers, register_map.eps_status),
            # Load
            load_power=load_power,
            # Internal
            bus_voltage_1=_read_and_scale_field(input_registers, register_map.bus_voltage_1),
            bus_voltage_2=_read_and_scale_field(input_registers, register_map.bus_voltage_2),
            # Temperatures
            internal_temperature=_read_and_scale_field(
                input_registers, register_map.internal_temperature
            ),
            radiator_temperature_1=_read_and_scale_field(
                input_registers, register_map.radiator_temperature_1
            ),
            radiator_temperature_2=_read_and_scale_field(
                input_registers, register_map.radiator_temperature_2
            ),
            # Status and fault codes
            device_status=_read_register_field(input_registers, register_map.device_status),
            fault_code=fault_code,
            warning_code=warning_code,
            # Extended sensors - Inverter RMS Current & Power
            inverter_rms_current=_read_and_scale_field(
                input_registers, register_map.inverter_rms_current
            ),
            inverter_apparent_power=_read_and_scale_field(
                input_registers, register_map.inverter_apparent_power
            ),
            # Generator input
            generator_voltage=_read_and_scale_field(
                input_registers, register_map.generator_voltage
            ),
            generator_frequency=_read_and_scale_field(
                input_registers, register_map.generator_frequency
            ),
            generator_power=_read_and_scale_field(input_registers, register_map.generator_power),
            # BMS limits and cell data
            bms_charge_current_limit=_read_and_scale_field(
                input_registers, register_map.bms_charge_current_limit
            ),
            bms_discharge_current_limit=_read_and_scale_field(
                input_registers, register_map.bms_discharge_current_limit
            ),
            bms_charge_voltage_ref=_read_and_scale_field(
                input_registers, register_map.bms_charge_voltage_ref
            ),
            bms_discharge_cutoff=_read_and_scale_field(
                input_registers, register_map.bms_discharge_cutoff
            ),
            # BMS cell voltages - convert from mV to V
            bms_max_cell_voltage=_read_and_scale_field(
                input_registers, register_map.bms_max_cell_voltage
            )
            / 1000.0,
            bms_min_cell_voltage=_read_and_scale_field(
                input_registers, register_map.bms_min_cell_voltage
            )
            / 1000.0,
            bms_max_cell_temperature=_read_and_scale_field(
                input_registers, register_map.bms_max_cell_temperature
            ),
            bms_min_cell_temperature=_read_and_scale_field(
                input_registers, register_map.bms_min_cell_temperature
            ),
            bms_cycle_count=_read_register_field(input_registers, register_map.bms_cycle_count),
            battery_parallel_num=_read_register_field(
                input_registers, register_map.battery_parallel_num
            ),
            battery_capacity_ah=_read_and_scale_field(
                input_registers, register_map.battery_capacity_ah
            ),
            # Additional temperatures
            temperature_t1=_read_and_scale_field(input_registers, register_map.temperature_t1),
            temperature_t2=_read_and_scale_field(input_registers, register_map.temperature_t2),
            temperature_t3=_read_and_scale_field(input_registers, register_map.temperature_t3),
            temperature_t4=_read_and_scale_field(input_registers, register_map.temperature_t4),
            temperature_t5=_read_and_scale_field(input_registers, register_map.temperature_t5),
            # Inverter operational
            inverter_on_time=_read_register_field(input_registers, register_map.inverter_on_time),
            ac_input_type=_read_register_field(input_registers, register_map.ac_input_type),
            # Parallel configuration (decoded from register 113)
            # bits 0-1: master/slave, bits 2-3: phase, bits 8-15: number
            parallel_master_slave=(
                _read_register_field(input_registers, register_map.parallel_config) & 0x03
            ),
            parallel_phase=(
                _read_register_field(input_registers, register_map.parallel_config) >> 2
            )
            & 0x03,
            parallel_number=(
                _read_register_field(input_registers, register_map.parallel_config) >> 8
            ),
        )


@dataclass
class InverterEnergyData:
    """Energy production and consumption statistics.

    All values are already scaled to proper units.
    """

    # Timestamp
    timestamp: datetime = field(default_factory=datetime.now)

    # Daily energy (kWh)
    pv_energy_today: float = 0.0
    pv1_energy_today: float = 0.0
    pv2_energy_today: float = 0.0
    pv3_energy_today: float = 0.0
    charge_energy_today: float = 0.0
    discharge_energy_today: float = 0.0
    grid_import_today: float = 0.0
    grid_export_today: float = 0.0
    load_energy_today: float = 0.0
    eps_energy_today: float = 0.0

    # Lifetime energy (kWh)
    pv_energy_total: float = 0.0
    pv1_energy_total: float = 0.0
    pv2_energy_total: float = 0.0
    pv3_energy_total: float = 0.0
    charge_energy_total: float = 0.0
    discharge_energy_total: float = 0.0
    grid_import_total: float = 0.0
    grid_export_total: float = 0.0
    load_energy_total: float = 0.0
    eps_energy_total: float = 0.0

    # Inverter output energy
    inverter_energy_today: float = 0.0
    inverter_energy_total: float = 0.0

    # Generator energy (if connected)
    generator_energy_today: float = 0.0  # kWh
    generator_energy_total: float = 0.0  # kWh

    @classmethod
    def from_http_response(cls, energy: EnergyInfo) -> InverterEnergyData:
        """Create from HTTP API EnergyInfo response.

        Args:
            energy: Pydantic model from HTTP API

        Returns:
            Transport-agnostic energy data with scaling applied

        Note:
            EnergyInfo uses naming convention like todayYielding, todayCharging, etc.
            Values from API are in 0.1 kWh units, need /10 for kWh.
        """
        from pylxpweb.constants.scaling import scale_energy_value

        return cls(
            timestamp=datetime.now(),
            # Daily - API returns 0.1 kWh units, scale to kWh
            pv_energy_today=scale_energy_value("todayYielding", energy.todayYielding),
            charge_energy_today=scale_energy_value("todayCharging", energy.todayCharging),
            discharge_energy_today=scale_energy_value("todayDischarging", energy.todayDischarging),
            grid_import_today=scale_energy_value("todayImport", energy.todayImport),
            grid_export_today=scale_energy_value("todayExport", energy.todayExport),
            load_energy_today=scale_energy_value("todayUsage", energy.todayUsage),
            # Lifetime - API returns 0.1 kWh units, scale to kWh
            pv_energy_total=scale_energy_value("totalYielding", energy.totalYielding),
            charge_energy_total=scale_energy_value("totalCharging", energy.totalCharging),
            discharge_energy_total=scale_energy_value("totalDischarging", energy.totalDischarging),
            grid_import_total=scale_energy_value("totalImport", energy.totalImport),
            grid_export_total=scale_energy_value("totalExport", energy.totalExport),
            load_energy_total=scale_energy_value("totalUsage", energy.totalUsage),
            # Note: EnergyInfo doesn't have per-PV-string or inverter/EPS energy
            # fields - those would require different API endpoints
        )

    @classmethod
    def from_modbus_registers(
        cls,
        input_registers: dict[int, int],
        register_map: EnergyRegisterMap | None = None,
    ) -> InverterEnergyData:
        """Create from Modbus input register values.

        Args:
            input_registers: Dict mapping register address to raw value
            register_map: Optional EnergyRegisterMap for model-specific register
                locations. If None, defaults to PV_SERIES_ENERGY_MAP for
                backward compatibility.

        Returns:
            Transport-agnostic energy data with scaling applied
        """
        from pylxpweb.transports.register_maps import PV_SERIES_ENERGY_MAP

        # Use default map if none provided (backward compatible)
        if register_map is None:
            register_map = PV_SERIES_ENERGY_MAP

        def read_energy_field(
            field_def: RegisterField | None,
        ) -> float:
            """Read an energy field and return value in kWh.

            Args:
                field_def: RegisterField for the energy value

            Returns:
                Energy value in kWh

            Note:
                According to galets/eg4-modbus-monitor, energy register values
                are in 0.1 kWh units (not 0.1 Wh as previously assumed).
                After applying the scale factor (typically SCALE_10 = divide by 10),
                the result is directly in kWh.
            """
            if field_def is None:
                return 0.0

            raw_value = _read_register_field(input_registers, field_def)

            # Apply scale factor - result is in kWh directly
            # Energy values are in 0.1 kWh (scale=0.1), so raw/10 = kWh
            from pylxpweb.constants.scaling import apply_scale

            return apply_scale(raw_value, field_def.scale_factor)

        # Calculate total PV energy from per-string values
        pv1_today = read_energy_field(register_map.pv1_energy_today)
        pv2_today = read_energy_field(register_map.pv2_energy_today)
        pv3_today = read_energy_field(register_map.pv3_energy_today)
        pv1_total = read_energy_field(register_map.pv1_energy_total)
        pv2_total = read_energy_field(register_map.pv2_energy_total)
        pv3_total = read_energy_field(register_map.pv3_energy_total)

        return cls(
            timestamp=datetime.now(),
            # Daily energy
            inverter_energy_today=read_energy_field(register_map.inverter_energy_today),
            grid_import_today=read_energy_field(register_map.grid_import_today),
            charge_energy_today=read_energy_field(register_map.charge_energy_today),
            discharge_energy_today=read_energy_field(register_map.discharge_energy_today),
            eps_energy_today=read_energy_field(register_map.eps_energy_today),
            grid_export_today=read_energy_field(register_map.grid_export_today),
            load_energy_today=read_energy_field(register_map.load_energy_today),
            pv1_energy_today=pv1_today,
            pv2_energy_today=pv2_today,
            pv3_energy_today=pv3_today,
            pv_energy_today=pv1_today + pv2_today + pv3_today,
            # Lifetime energy
            inverter_energy_total=read_energy_field(register_map.inverter_energy_total),
            grid_import_total=read_energy_field(register_map.grid_import_total),
            charge_energy_total=read_energy_field(register_map.charge_energy_total),
            discharge_energy_total=read_energy_field(register_map.discharge_energy_total),
            eps_energy_total=read_energy_field(register_map.eps_energy_total),
            grid_export_total=read_energy_field(register_map.grid_export_total),
            load_energy_total=read_energy_field(register_map.load_energy_total),
            pv1_energy_total=pv1_total,
            pv2_energy_total=pv2_total,
            pv3_energy_total=pv3_total,
            pv_energy_total=pv1_total + pv2_total + pv3_total,
            # Generator energy
            generator_energy_today=read_energy_field(register_map.generator_energy_today),
            generator_energy_total=read_energy_field(register_map.generator_energy_total),
        )


@dataclass
class BatteryData:
    """Individual battery module data.

    All values are already scaled to proper units.

    Validation:
        - soc and soh are clamped to 0-100 range
    """

    # Identity
    battery_index: int = 0  # 0-based index in bank
    serial_number: str = ""

    # State
    voltage: float = 0.0  # V
    current: float = 0.0  # A
    soc: int = 0  # %
    soh: int = 100  # %
    temperature: float = 0.0  # °C

    # Capacity
    max_capacity: float = 0.0  # Ah
    current_capacity: float = 0.0  # Ah
    cycle_count: int = 0

    # Cell data (optional, if available)
    cell_count: int = 0
    cell_voltages: list[float] = field(default_factory=list)  # V per cell
    cell_temperatures: list[float] = field(default_factory=list)  # °C per cell
    min_cell_voltage: float = 0.0  # V
    max_cell_voltage: float = 0.0  # V

    # Status
    status: int = 0
    fault_code: int = 0
    warning_code: int = 0

    def __post_init__(self) -> None:
        """Validate and clamp percentage values."""
        self.soc = _clamp_percentage(self.soc, "battery_soc")
        self.soh = _clamp_percentage(self.soh, "battery_soh")


@dataclass
class BatteryBankData:
    """Aggregate battery bank data.

    All values are already scaled to proper units.

    Validation:
        - soc and soh are clamped to 0-100 range

    Note:
        battery_count reflects the API-reported count and may differ from
        len(batteries) if the API returns a different count than battery array size.
    """

    # Timestamp
    timestamp: datetime = field(default_factory=datetime.now)

    # Aggregate state
    voltage: float = 0.0  # V
    current: float = 0.0  # A
    soc: int = 0  # %
    soh: int = 100  # %
    temperature: float = 0.0  # °C

    # Power
    charge_power: float = 0.0  # W
    discharge_power: float = 0.0  # W

    # Capacity
    max_capacity: float = 0.0  # Ah
    current_capacity: float = 0.0  # Ah

    # Cell data (from BMS, Modbus registers 101-106)
    # Source: Yippy's documentation - https://github.com/joyfulhouse/pylxpweb/issues/97
    max_cell_voltage: float = 0.0  # V (highest cell voltage)
    min_cell_voltage: float = 0.0  # V (lowest cell voltage)
    max_cell_temperature: float = 0.0  # °C (highest cell temp)
    min_cell_temperature: float = 0.0  # °C (lowest cell temp)
    cycle_count: int = 0  # Charge/discharge cycle count

    # Status
    status: int = 0
    fault_code: int = 0
    warning_code: int = 0

    # Individual batteries
    battery_count: int = 0
    batteries: list[BatteryData] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate and clamp percentage values."""
        self.soc = _clamp_percentage(self.soc, "battery_bank_soc")
        self.soh = _clamp_percentage(self.soh, "battery_bank_soh")
