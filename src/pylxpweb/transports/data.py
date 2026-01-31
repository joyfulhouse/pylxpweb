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
    from pylxpweb.models import EnergyInfo, InverterRuntime, MidboxData
    from pylxpweb.transports.register_maps import (
        EnergyRegisterMap,
        MidboxEnergyRegisterMap,
        MidboxRuntimeRegisterMap,
        RegisterField,
        RuntimeRegisterMap,
    )

_LOGGER = logging.getLogger(__name__)


def _read_register_field(
    registers: dict[int, int],
    field_def: RegisterField | None,
    default: int | None = None,
) -> int | None:
    """Read a value from registers using a RegisterField definition.

    Args:
        registers: Dict mapping register address to raw value
        field_def: RegisterField defining how to read the value, or None
        default: Default value if field is None or register not found.
            Use None to indicate unavailable data (recommended for Modbus reads).

    Returns:
        Raw integer value (no scaling applied yet), or None if unavailable.
        Returns None when:
        - field_def is None (field not defined for this device/map)
        - Required register(s) not present in registers dict (read failed)
    """
    if field_def is None:
        return default

    if field_def.bit_width == 32:
        # 32-bit value from two consecutive registers
        # Both registers must be present for valid data
        if field_def.address not in registers or field_def.address + 1 not in registers:
            return default

        if field_def.little_endian:
            # Little-endian: low word at address, high word at address+1 (LuxPower style)
            low = registers[field_def.address]
            high = registers[field_def.address + 1]
        else:
            # Big-endian: high word at address, low word at address+1 (EG4 style)
            high = registers[field_def.address]
            low = registers[field_def.address + 1]
        value = (high << 16) | low
    else:
        # 16-bit value - register must be present
        if field_def.address not in registers:
            return default
        value = registers[field_def.address]

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
) -> float | None:
    """Read a value from registers and apply scaling.

    Args:
        registers: Dict mapping register address to raw value
        field_def: RegisterField defining how to read and scale the value

    Returns:
        Scaled floating-point value, or None if unavailable.
        Returns None when:
        - field_def is None (field not defined for this device/map)
        - Required register(s) not present (read failed, flaky connectivity)

    Note:
        Returning None instead of 0.0 for missing data allows Home Assistant
        to show "unavailable" state rather than recording false zero values
        in history graphs. See: eg4_web_monitor issue #91
    """
    if field_def is None:
        return None

    from pylxpweb.constants.scaling import apply_scale

    raw_value = _read_register_field(registers, field_def)
    if raw_value is None:
        return None
    return apply_scale(raw_value, field_def.scale_factor)


def _clamp_percentage(value: int | None, name: str) -> int | None:
    """Clamp percentage value to 0-100 range, logging if out of bounds.

    Args:
        value: Percentage value to clamp, or None if unavailable
        name: Field name for logging

    Returns:
        Clamped value (0-100), or None if input was None
    """
    if value is None:
        return None
    if value < 0:
        _LOGGER.warning("%s value %d is negative, clamping to 0", name, value)
        return 0
    if value > 100:
        _LOGGER.warning("%s value %d exceeds 100%%, clamping to 100", name, value)
        return 100
    return value


def _decode_parallel_config(value: int | None, bits: int, shift: int) -> int | None:
    """Decode parallel configuration from register value.

    Args:
        value: Raw register value, or None if unavailable
        bits: Bitmask to apply after shifting
        shift: Number of bits to shift right

    Returns:
        Decoded value, or None if input was None
    """
    if value is None:
        return None
    return (value >> shift) & bits


def _sum_optional(*values: float | None) -> float | None:
    """Sum multiple optional float values.

    Args:
        *values: Float values that may be None

    Returns:
        Sum of all non-None values, or None if all values are None.
        If some values are None but not all, returns sum of available values.
    """
    non_none = [v for v in values if v is not None]
    return sum(non_none) if non_none else None


@dataclass
class InverterRuntimeData:
    """Real-time inverter operating data.

    All values are already scaled to proper units.
    This is the transport-agnostic representation of runtime data.

    Field values:
        - None: Data unavailable (Modbus read failed, register not present)
        - Numeric value: Actual measured/calculated value

    Returning None for unavailable data allows Home Assistant to show
    "unavailable" state rather than recording false zero values in history.
    See: eg4_web_monitor issue #91

    Validation:
        - battery_soc and battery_soh are clamped to 0-100 range when not None
    """

    # Timestamp
    timestamp: datetime = field(default_factory=datetime.now)

    # PV Input
    pv1_voltage: float | None = None  # V
    pv1_current: float | None = None  # A
    pv1_power: float | None = None  # W
    pv2_voltage: float | None = None  # V
    pv2_current: float | None = None  # A
    pv2_power: float | None = None  # W
    pv3_voltage: float | None = None  # V
    pv3_current: float | None = None  # A
    pv3_power: float | None = None  # W
    pv_total_power: float | None = None  # W

    # Battery
    battery_voltage: float | None = None  # V
    battery_current: float | None = None  # A
    battery_soc: int | None = None  # %
    battery_soh: int | None = None  # %
    battery_charge_power: float | None = None  # W
    battery_discharge_power: float | None = None  # W
    battery_temperature: float | None = None  # °C

    # Grid (AC Input)
    grid_voltage_r: float | None = None  # V (Phase R/L1)
    grid_voltage_s: float | None = None  # V (Phase S/L2)
    grid_voltage_t: float | None = None  # V (Phase T/L3)
    grid_l1_voltage: float | None = None  # V (Split-phase L1, ~120V)
    grid_l2_voltage: float | None = None  # V (Split-phase L2, ~120V)
    grid_current_r: float | None = None  # A
    grid_current_s: float | None = None  # A
    grid_current_t: float | None = None  # A
    grid_frequency: float | None = None  # Hz
    grid_power: float | None = None  # W (positive = import, negative = export)
    power_to_grid: float | None = None  # W (export)
    power_from_grid: float | None = None  # W (import)

    # Inverter Output
    inverter_power: float | None = None  # W
    inverter_current_r: float | None = None  # A
    inverter_current_s: float | None = None  # A
    inverter_current_t: float | None = None  # A
    power_factor: float | None = None  # 0.0-1.0

    # EPS/Off-Grid Output
    eps_voltage_r: float | None = None  # V
    eps_voltage_s: float | None = None  # V
    eps_voltage_t: float | None = None  # V
    eps_l1_voltage: float | None = None  # V (Split-phase L1, ~120V)
    eps_l2_voltage: float | None = None  # V (Split-phase L2, ~120V)
    eps_frequency: float | None = None  # Hz
    eps_power: float | None = None  # W
    eps_status: int | None = None  # Status code

    # Load
    load_power: float | None = None  # W
    output_power: float | None = None  # W (Total output, split-phase systems)

    # Internal
    bus_voltage_1: float | None = None  # V
    bus_voltage_2: float | None = None  # V

    # Temperatures
    internal_temperature: float | None = None  # °C
    radiator_temperature_1: float | None = None  # °C
    radiator_temperature_2: float | None = None  # °C

    # Status
    device_status: int | None = None  # Status code
    fault_code: int | None = None  # Fault code
    warning_code: int | None = None  # Warning code

    # -------------------------------------------------------------------------
    # Extended Sensors - Inverter RMS Current & Power
    # -------------------------------------------------------------------------
    inverter_rms_current: float | None = None  # A (Inverter RMS current)
    inverter_apparent_power: float | None = None  # VA (Inverter apparent power)

    # -------------------------------------------------------------------------
    # Generator Input (if connected)
    # -------------------------------------------------------------------------
    generator_voltage: float | None = None  # V
    generator_frequency: float | None = None  # Hz
    generator_power: float | None = None  # W

    # -------------------------------------------------------------------------
    # BMS Limits and Cell Data
    # -------------------------------------------------------------------------
    bms_charge_current_limit: float | None = None  # A (Max charge current from BMS)
    bms_discharge_current_limit: float | None = None  # A (Max discharge current from BMS)
    bms_charge_voltage_ref: float | None = None  # V (BMS charge voltage reference)
    bms_discharge_cutoff: float | None = None  # V (BMS discharge cutoff voltage)
    bms_max_cell_voltage: float | None = None  # V (Highest cell voltage)
    bms_min_cell_voltage: float | None = None  # V (Lowest cell voltage)
    bms_max_cell_temperature: float | None = None  # °C (Highest cell temp)
    bms_min_cell_temperature: float | None = None  # °C (Lowest cell temp)
    bms_cycle_count: int | None = None  # Charge/discharge cycle count
    battery_parallel_num: int | None = None  # Number of parallel battery units
    battery_capacity_ah: float | None = None  # Ah (Battery capacity)

    # -------------------------------------------------------------------------
    # Additional Temperatures
    # -------------------------------------------------------------------------
    temperature_t1: float | None = None  # °C
    temperature_t2: float | None = None  # °C
    temperature_t3: float | None = None  # °C
    temperature_t4: float | None = None  # °C
    temperature_t5: float | None = None  # °C

    # -------------------------------------------------------------------------
    # Inverter Operational
    # -------------------------------------------------------------------------
    inverter_on_time: int | None = None  # hours (total on time)
    ac_input_type: int | None = None  # AC input type code

    # -------------------------------------------------------------------------
    # Parallel Configuration (decoded from register 113)
    # -------------------------------------------------------------------------
    parallel_master_slave: int | None = None  # 0=no parallel, 1=master, 2=slave, 3=3-phase master
    parallel_phase: int | None = None  # 0=R, 1=S, 2=T
    parallel_number: int | None = None  # unit ID in parallel system (0-255)

    def __post_init__(self) -> None:
        """Validate and clamp percentage values (if not None)."""
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
        battery_soc: int | None = None
        battery_soh: int | None = None
        if soc_soh_packed is not None:
            battery_soc = soc_soh_packed & 0xFF
            battery_soh = (soc_soh_packed >> 8) & 0xFF
            if battery_soh == 0:
                battery_soh = 100  # Default to 100% if not reported

        # Fault/warning codes
        inverter_fault_code = _read_register_field(
            input_registers, register_map.inverter_fault_code
        )
        inverter_warning_code = _read_register_field(
            input_registers, register_map.inverter_warning_code
        )
        bms_fault_code = _read_register_field(input_registers, register_map.bms_fault_code)
        bms_warning_code = _read_register_field(input_registers, register_map.bms_warning_code)

        # Combine fault/warning codes (inverter + BMS) - prefer non-None/non-zero values
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
            pv_total_power=_sum_optional(pv1_power, pv2_power, pv3_power),
            # Battery - SOC/SOH from packed register
            battery_voltage=_read_and_scale_field(input_registers, register_map.battery_voltage),
            battery_current=_read_and_scale_field(input_registers, register_map.battery_current),
            battery_soc=battery_soc,
            battery_soh=battery_soh,
            battery_charge_power=charge_power,
            battery_discharge_power=discharge_power,
            battery_temperature=_read_and_scale_field(
                input_registers, register_map.battery_temperature
            ),
            # Grid
            grid_voltage_r=_read_and_scale_field(input_registers, register_map.grid_voltage_r),
            grid_voltage_s=_read_and_scale_field(input_registers, register_map.grid_voltage_s),
            grid_voltage_t=_read_and_scale_field(input_registers, register_map.grid_voltage_t),
            grid_l1_voltage=_read_and_scale_field(input_registers, register_map.grid_l1_voltage),
            grid_l2_voltage=_read_and_scale_field(input_registers, register_map.grid_l2_voltage),
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
            eps_l1_voltage=_read_and_scale_field(input_registers, register_map.eps_l1_voltage),
            eps_l2_voltage=_read_and_scale_field(input_registers, register_map.eps_l2_voltage),
            eps_frequency=_read_and_scale_field(input_registers, register_map.eps_frequency),
            eps_power=eps_power,
            eps_status=_read_register_field(input_registers, register_map.eps_status),
            # Load
            load_power=load_power,
            output_power=_read_and_scale_field(input_registers, register_map.output_power),
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
            # BMS cell voltages - register map has SCALE_1000 for mV → V conversion
            bms_max_cell_voltage=_read_and_scale_field(
                input_registers, register_map.bms_max_cell_voltage
            ),
            bms_min_cell_voltage=_read_and_scale_field(
                input_registers, register_map.bms_min_cell_voltage
            ),
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
            parallel_master_slave=_decode_parallel_config(
                _read_register_field(input_registers, register_map.parallel_config),
                bits=0x03,
                shift=0,
            ),
            parallel_phase=_decode_parallel_config(
                _read_register_field(input_registers, register_map.parallel_config),
                bits=0x03,
                shift=2,
            ),
            parallel_number=_decode_parallel_config(
                _read_register_field(input_registers, register_map.parallel_config),
                bits=0xFF,
                shift=8,
            ),
        )


@dataclass
class InverterEnergyData:
    """Energy production and consumption statistics.

    All values are already scaled to proper units.

    Field values:
        - None: Data unavailable (Modbus read failed, register not present)
        - Numeric value: Actual measured/calculated value

    See: eg4_web_monitor issue #91
    """

    # Timestamp
    timestamp: datetime = field(default_factory=datetime.now)

    # Daily energy (kWh)
    pv_energy_today: float | None = None
    pv1_energy_today: float | None = None
    pv2_energy_today: float | None = None
    pv3_energy_today: float | None = None
    charge_energy_today: float | None = None
    discharge_energy_today: float | None = None
    grid_import_today: float | None = None
    grid_export_today: float | None = None
    load_energy_today: float | None = None
    eps_energy_today: float | None = None

    # Lifetime energy (kWh)
    pv_energy_total: float | None = None
    pv1_energy_total: float | None = None
    pv2_energy_total: float | None = None
    pv3_energy_total: float | None = None
    charge_energy_total: float | None = None
    discharge_energy_total: float | None = None
    grid_import_total: float | None = None
    grid_export_total: float | None = None
    load_energy_total: float | None = None
    eps_energy_total: float | None = None

    # Inverter output energy
    inverter_energy_today: float | None = None
    inverter_energy_total: float | None = None

    # Generator energy (if connected)
    generator_energy_today: float | None = None  # kWh
    generator_energy_total: float | None = None  # kWh

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
        ) -> float | None:
            """Read an energy field and return value in kWh.

            Args:
                field_def: RegisterField for the energy value

            Returns:
                Energy value in kWh, or None if field not defined or register missing

            Note:
                According to galets/eg4-modbus-monitor, energy register values
                are in 0.1 kWh units (not 0.1 Wh as previously assumed).
                After applying the scale factor (typically SCALE_10 = divide by 10),
                the result is directly in kWh.
            """
            if field_def is None:
                return None

            raw_value = _read_register_field(input_registers, field_def)
            if raw_value is None:
                return None

            # Apply scale factor - result is in kWh directly
            # Energy values are in 0.1 kWh (scale=0.1), so raw/10 = kWh
            from pylxpweb.constants.scaling import apply_scale

            return apply_scale(raw_value, field_def.scale_factor)

        def sum_pv_energy(pv1: float | None, pv2: float | None, pv3: float | None) -> float | None:
            """Sum PV energy values, returning None if all components are None."""
            values = [v for v in [pv1, pv2, pv3] if v is not None]
            return sum(values) if values else None

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
            pv_energy_today=sum_pv_energy(pv1_today, pv2_today, pv3_today),
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
            pv_energy_total=sum_pv_energy(pv1_total, pv2_total, pv3_total),
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
    min_cell_temperature: float = 0.0  # °C
    max_cell_temperature: float = 0.0  # °C
    # Cell numbers (1-indexed, which cell has the max/min value)
    max_cell_num_voltage: int = 0  # Cell number with max voltage
    min_cell_num_voltage: int = 0  # Cell number with min voltage
    max_cell_num_temp: int = 0  # Cell number with max temperature
    min_cell_num_temp: int = 0  # Cell number with min temperature

    # BMS limits (optional, from extended Modbus registers)
    charge_voltage_ref: float = 0.0  # V (BMS charge voltage reference)
    charge_current_limit: float = 0.0  # A (Max charge current from BMS)
    discharge_current_limit: float = 0.0  # A (Max discharge current from BMS)
    discharge_voltage_cutoff: float = 0.0  # V (BMS discharge cutoff voltage)

    # Model/firmware info
    # Note: Model is only available via Web API (batBmsModelText field).
    # Not accessible via direct Modbus - the BMS sends model info via CAN bus
    # which the dongle forwards to the cloud, but doesn't expose via Modbus.
    model: str = ""  # Battery model (e.g., "WP-16/280-1AWLL") - Web API only
    firmware_version: str = ""  # Firmware version string (e.g., "2.17") - Modbus available

    # Status
    status: int = 0
    fault_code: int = 0
    warning_code: int = 0

    def __post_init__(self) -> None:
        """Validate and clamp percentage values."""
        # BatteryData uses non-nullable soc/soh (0 and 100 defaults)
        # _clamp_percentage accepts int|None, so we need to explicitly handle the result
        clamped_soc = _clamp_percentage(self.soc, "battery_soc")
        if clamped_soc is not None:
            self.soc = clamped_soc
        clamped_soh = _clamp_percentage(self.soh, "battery_soh")
        if clamped_soh is not None:
            self.soh = clamped_soh

    @property
    def remaining_capacity(self) -> float:
        """Calculate remaining capacity in Ah from max_capacity and SOC.

        Returns:
            Remaining capacity in Ah (max_capacity * soc / 100)
        """
        if self.max_capacity > 0 and self.soc > 0:
            return self.max_capacity * self.soc / 100
        return 0.0

    @property
    def power(self) -> float:
        """Calculate battery power in watts (V * I).

        Positive = charging, Negative = discharging.

        Returns:
            Battery power in watts, rounded to 2 decimal places.
        """
        return round(self.voltage * self.current, 2)

    @property
    def capacity_percent(self) -> int:
        """Calculate capacity percentage (remaining / full * 100).

        This is different from SOC - it represents the battery's actual
        capacity relative to its rated full capacity.

        Returns:
            Capacity percentage (0-100), or 0 if full capacity is 0.
        """
        if self.max_capacity > 0 and self.current_capacity > 0:
            return round((self.current_capacity / self.max_capacity) * 100)
        # Fall back to SOC if current_capacity not available
        return self.soc

    @property
    def cell_voltage_delta(self) -> float:
        """Calculate cell voltage delta (max - min).

        A healthy battery pack should have a small delta (<0.05V).
        Large deltas may indicate cell imbalance.

        Returns:
            Voltage difference in volts, rounded to 3 decimal places (mV precision).
        """
        return round(self.max_cell_voltage - self.min_cell_voltage, 3)

    @property
    def cell_temp_delta(self) -> float:
        """Calculate cell temperature delta (max - min).

        A healthy battery pack should have minimal temperature variation.
        Large deltas may indicate cooling issues or cell problems.

        Returns:
            Temperature difference in °C, rounded to 1 decimal place.
        """
        return round(self.max_cell_temperature - self.min_cell_temperature, 1)

    @classmethod
    def from_modbus_registers(
        cls,
        battery_index: int,
        registers: dict[int, int],
    ) -> BatteryData | None:
        """Create BatteryData from Modbus registers for a single battery.

        The registers dict should contain the 30-register block for this battery
        with keys as absolute register addresses (e.g., 5002-5031 for battery 0).

        Args:
            battery_index: 0-based battery index
            registers: Dict mapping register address to raw value

        Returns:
            BatteryData with all values properly scaled, or None if battery not present
        """
        from pylxpweb.transports.register_maps import (
            INDIVIDUAL_BATTERY_BASE_ADDRESS,
            INDIVIDUAL_BATTERY_MAP,
            INDIVIDUAL_BATTERY_REGISTER_COUNT,
        )

        base = INDIVIDUAL_BATTERY_BASE_ADDRESS + (battery_index * INDIVIDUAL_BATTERY_REGISTER_COUNT)
        battery_map = INDIVIDUAL_BATTERY_MAP

        # Check if battery is present by reading status header
        # 0xC003 indicates a connected battery
        status_addr = base + (battery_map.status_header.address if battery_map.status_header else 0)
        status = registers.get(status_addr, 0)
        if status == 0:
            return None  # Battery slot is empty

        # Helper to read a field at base + offset
        def read_field(field_def: RegisterField | None, default: float = 0.0) -> float:
            if field_def is None:
                return default
            addr = base + field_def.address
            raw_value = registers.get(addr, int(default))
            # Handle signed values
            if field_def.signed and raw_value > 32767:
                raw_value = raw_value - 65536
            # Apply scaling
            from pylxpweb.constants.scaling import apply_scale

            return apply_scale(raw_value, field_def.scale_factor)

        def read_int_field(field_def: RegisterField | None, default: int = 0) -> int:
            if field_def is None:
                return default
            addr = base + field_def.address
            return registers.get(addr, default)

        # Read serial number from 7 registers (up to 14 ASCII chars)
        serial_chars: list[str] = []
        for i in range(battery_map.serial_number_count):
            addr = base + battery_map.serial_number_start + i
            value = registers.get(addr, 0)
            low_byte = value & 0xFF
            high_byte = (value >> 8) & 0xFF
            if 32 <= low_byte <= 126:
                serial_chars.append(chr(low_byte))
            if 32 <= high_byte <= 126:
                serial_chars.append(chr(high_byte))
        serial_number = "".join(serial_chars).strip()

        # Read cell voltage data (scaling handled in register map - SCALE_1000)
        max_cell_voltage = read_field(battery_map.max_cell_voltage)
        min_cell_voltage = read_field(battery_map.min_cell_voltage)

        # Read temperature data
        max_cell_temp = read_field(battery_map.max_cell_temp)
        min_cell_temp = read_field(battery_map.min_cell_temp)

        # Parse cell number packed registers (low byte = max cell#, high byte = min cell#)
        cell_num_voltage_packed = read_int_field(battery_map.cell_num_voltage_packed)
        max_cell_num_voltage = cell_num_voltage_packed & 0xFF
        min_cell_num_voltage = (cell_num_voltage_packed >> 8) & 0xFF

        cell_num_temp_packed = read_int_field(battery_map.cell_num_temp_packed)
        max_cell_num_temp = cell_num_temp_packed & 0xFF
        min_cell_num_temp = (cell_num_temp_packed >> 8) & 0xFF

        # Parse SOC/SOH from packed register (low byte = SOC, high byte = SOH)
        soc_soh_packed = read_int_field(battery_map.soc_soh_packed)
        soc = soc_soh_packed & 0xFF  # Low byte = SOC%
        soh = (soc_soh_packed >> 8) & 0xFF  # High byte = SOH%

        # Parse firmware version from packed register (high byte = major, low byte = minor)
        fw_raw = read_int_field(battery_map.firmware_version)
        fw_major = (fw_raw >> 8) & 0xFF
        fw_minor = fw_raw & 0xFF
        firmware_version = f"{fw_major}.{fw_minor}" if fw_raw else ""

        return cls(
            battery_index=battery_index,
            serial_number=serial_number,
            voltage=read_field(battery_map.voltage),
            current=read_field(battery_map.current),
            soc=soc,
            soh=soh if soh > 0 else 100,
            temperature=max_cell_temp,
            max_capacity=read_field(battery_map.full_capacity_ah),
            cycle_count=read_int_field(battery_map.cycle_count),
            min_cell_voltage=min_cell_voltage,
            max_cell_voltage=max_cell_voltage,
            min_cell_temperature=min_cell_temp,
            max_cell_temperature=max_cell_temp,
            max_cell_num_voltage=max_cell_num_voltage,
            min_cell_num_voltage=min_cell_num_voltage,
            max_cell_num_temp=max_cell_num_temp,
            min_cell_num_temp=min_cell_num_temp,
            charge_voltage_ref=read_field(battery_map.charge_voltage_ref),
            charge_current_limit=read_field(battery_map.charge_current_limit),
            discharge_current_limit=read_field(battery_map.discharge_current_limit),
            discharge_voltage_cutoff=read_field(battery_map.discharge_voltage_cutoff),
            firmware_version=firmware_version,
            status=status,
        )


@dataclass
class BatteryBankData:
    """Aggregate battery bank data.

    All values are already scaled to proper units.

    Field values:
        - None: Data unavailable (Modbus read failed, register not present)
        - Numeric value: Actual measured/calculated value

    Validation:
        - soc and soh are clamped to 0-100 range when non-None

    Note:
        battery_count reflects the API-reported count and may differ from
        len(batteries) if the API returns a different count than battery array size.
        See: eg4_web_monitor issue #91 for None/unavailable handling rationale.
    """

    # Timestamp
    timestamp: datetime = field(default_factory=datetime.now)

    # Aggregate state
    voltage: float | None = None  # V
    current: float | None = None  # A
    soc: int | None = None  # %
    soh: int | None = None  # %
    temperature: float | None = None  # °C

    # Power
    charge_power: float | None = None  # W
    discharge_power: float | None = None  # W

    # Capacity
    max_capacity: float | None = None  # Ah
    current_capacity: float | None = None  # Ah

    # Cell data (from BMS, Modbus registers 101-106)
    # Source: Yippy's documentation - https://github.com/joyfulhouse/pylxpweb/issues/97
    max_cell_voltage: float | None = None  # V (highest cell voltage)
    min_cell_voltage: float | None = None  # V (lowest cell voltage)
    max_cell_temperature: float | None = None  # °C (highest cell temp)
    min_cell_temperature: float | None = None  # °C (lowest cell temp)
    cycle_count: int | None = None  # Charge/discharge cycle count

    # Status
    status: int | None = None
    fault_code: int | None = None
    warning_code: int | None = None

    # Individual batteries
    battery_count: int | None = None
    batteries: list[BatteryData] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate and clamp percentage values."""
        if self.soc is not None:
            self.soc = _clamp_percentage(self.soc, "battery_bank_soc")
        if self.soh is not None:
            self.soh = _clamp_percentage(self.soh, "battery_bank_soh")

    @classmethod
    def from_modbus_registers(
        cls,
        input_registers: dict[int, int],
        register_map: RuntimeRegisterMap | None = None,
        individual_battery_registers: dict[int, int] | None = None,
    ) -> BatteryBankData | None:
        """Create from Modbus input register values.

        Uses the register map to determine correct register addresses and scaling
        for each inverter family. This ensures extensibility for future models.

        Args:
            input_registers: Dict mapping register address to raw value (0-127)
            register_map: RuntimeRegisterMap for model-specific register locations.
                If None, defaults to PV_SERIES_RUNTIME_MAP.
            individual_battery_registers: Optional dict with extended register
                range (5000+) containing individual battery data. If provided,
                individual batteries will be populated in the batteries list.

        Returns:
            BatteryBankData with all values properly scaled, or None if no battery
        """
        from pylxpweb.transports.register_maps import PV_SERIES_RUNTIME_MAP

        if register_map is None:
            register_map = PV_SERIES_RUNTIME_MAP

        # Battery voltage from register map
        battery_voltage = _read_and_scale_field(input_registers, register_map.battery_voltage)

        # If voltage is too low or None, assume no battery present
        if battery_voltage is None or battery_voltage < 1.0:
            return None

        # SOC/SOH from packed register (low byte = SOC, high byte = SOH)
        soc_soh_packed = _read_register_field(input_registers, register_map.soc_soh_packed)
        battery_soc: int | None = None
        battery_soh: int | None = None
        if soc_soh_packed is not None:
            battery_soc = soc_soh_packed & 0xFF
            battery_soh = (soc_soh_packed >> 8) & 0xFF

        # Charge/discharge power from register map (16-bit, no scaling)
        charge_power = _read_and_scale_field(input_registers, register_map.charge_power)
        discharge_power = _read_and_scale_field(input_registers, register_map.discharge_power)

        # Battery current from register map
        battery_current = _read_and_scale_field(input_registers, register_map.battery_current)

        # Battery temperature from register map
        battery_temp = _read_and_scale_field(input_registers, register_map.battery_temperature)

        # BMS data from register map
        bms_fault_code = _read_register_field(input_registers, register_map.bms_fault_code)
        bms_warning_code = _read_register_field(input_registers, register_map.bms_warning_code)
        battery_count = _read_register_field(input_registers, register_map.battery_parallel_num)

        # Cell voltage data from register map (mV -> V via SCALE_1000 in map)
        max_cell_voltage = _read_and_scale_field(input_registers, register_map.bms_max_cell_voltage)
        min_cell_voltage = _read_and_scale_field(input_registers, register_map.bms_min_cell_voltage)

        # Cell temperature data from register map (0.1°C -> °C via SCALE_10 in map)
        max_cell_temp = _read_and_scale_field(
            input_registers, register_map.bms_max_cell_temperature
        )
        min_cell_temp = _read_and_scale_field(
            input_registers, register_map.bms_min_cell_temperature
        )

        # Cycle count from register map
        cycle_count = _read_register_field(input_registers, register_map.bms_cycle_count)

        # Battery capacity from register map (Ah, no scaling)
        max_capacity = _read_and_scale_field(
            input_registers, register_map.battery_capacity_ah
        )

        # Compute current capacity from max_capacity and SOC
        current_capacity: float | None = None
        if max_capacity is not None and battery_soc is not None:
            current_capacity = round(max_capacity * battery_soc / 100)

        # Parse individual battery data if extended registers provided
        batteries: list[BatteryData] = []
        if individual_battery_registers:
            from pylxpweb.transports.register_maps import INDIVIDUAL_BATTERY_MAX_COUNT

            # Try to read each battery slot (up to max count or battery_count)
            # Use INDIVIDUAL_BATTERY_MAX_COUNT if battery_count is None or 0
            if battery_count is not None and battery_count > 0:
                count_to_use = battery_count
            else:
                count_to_use = INDIVIDUAL_BATTERY_MAX_COUNT
            max_to_check = min(count_to_use, INDIVIDUAL_BATTERY_MAX_COUNT)
            for idx in range(max_to_check):
                battery_data = BatteryData.from_modbus_registers(
                    battery_index=idx,
                    registers=individual_battery_registers,
                )
                if battery_data is not None:
                    batteries.append(battery_data)

        # Handle None values for battery_count and soh with sensible defaults
        # battery_count defaults to 1 if unavailable
        # soh defaults to 100 (assume healthy) if unavailable
        actual_battery_count: int | None = None
        if battery_count is not None and battery_count > 0:
            actual_battery_count = battery_count
        elif batteries:
            actual_battery_count = len(batteries)

        actual_soh: int | None = battery_soh
        if battery_soh is not None and battery_soh == 0:
            actual_soh = 100  # 0 is invalid, assume healthy

        return cls(
            timestamp=datetime.now(),
            voltage=battery_voltage,
            current=battery_current,
            soc=battery_soc,
            soh=actual_soh,
            temperature=battery_temp,
            charge_power=charge_power,
            discharge_power=discharge_power,
            max_capacity=max_capacity,
            current_capacity=current_capacity,
            fault_code=bms_fault_code,
            warning_code=bms_warning_code,
            battery_count=actual_battery_count,
            max_cell_voltage=max_cell_voltage,
            min_cell_voltage=min_cell_voltage,
            max_cell_temperature=max_cell_temp,
            min_cell_temperature=min_cell_temp,
            cycle_count=cycle_count,
            batteries=batteries,
        )


@dataclass
class MidboxRuntimeData:
    """Real-time GridBOSS/MID device operating data.

    All values are already scaled to proper units.
    This is the transport-agnostic representation of MID device runtime data.

    Field values:
        - None: Data unavailable (Modbus read failed, register not present)
        - Numeric value: Actual measured/calculated value

    See: eg4_web_monitor issue #91

    Note: MID devices use HOLDING registers (function 0x03) for runtime data,
    unlike inverters which use INPUT registers (function 0x04).
    """

    # Timestamp
    timestamp: datetime = field(default_factory=datetime.now)

    # -------------------------------------------------------------------------
    # Voltage (V)
    # -------------------------------------------------------------------------
    grid_voltage: float | None = None  # gridRmsVolt
    ups_voltage: float | None = None  # upsRmsVolt
    gen_voltage: float | None = None  # genRmsVolt
    grid_l1_voltage: float | None = None  # gridL1RmsVolt
    grid_l2_voltage: float | None = None  # gridL2RmsVolt
    ups_l1_voltage: float | None = None  # upsL1RmsVolt
    ups_l2_voltage: float | None = None  # upsL2RmsVolt
    gen_l1_voltage: float | None = None  # genL1RmsVolt
    gen_l2_voltage: float | None = None  # genL2RmsVolt

    # -------------------------------------------------------------------------
    # Current (A)
    # -------------------------------------------------------------------------
    grid_l1_current: float | None = None  # gridL1RmsCurr
    grid_l2_current: float | None = None  # gridL2RmsCurr
    load_l1_current: float | None = None  # loadL1RmsCurr
    load_l2_current: float | None = None  # loadL2RmsCurr
    gen_l1_current: float | None = None  # genL1RmsCurr
    gen_l2_current: float | None = None  # genL2RmsCurr
    ups_l1_current: float | None = None  # upsL1RmsCurr
    ups_l2_current: float | None = None  # upsL2RmsCurr

    # -------------------------------------------------------------------------
    # Power (W, signed)
    # -------------------------------------------------------------------------
    grid_l1_power: float | None = None  # gridL1ActivePower
    grid_l2_power: float | None = None  # gridL2ActivePower
    load_l1_power: float | None = None  # loadL1ActivePower
    load_l2_power: float | None = None  # loadL2ActivePower
    gen_l1_power: float | None = None  # genL1ActivePower
    gen_l2_power: float | None = None  # genL2ActivePower
    ups_l1_power: float | None = None  # upsL1ActivePower
    ups_l2_power: float | None = None  # upsL2ActivePower
    hybrid_power: float | None = None  # hybridPower (total AC couple power flow)

    # -------------------------------------------------------------------------
    # Smart Load Power (W, signed)
    # When port is in AC Couple mode (status=2), these show AC Couple power
    # -------------------------------------------------------------------------
    smart_load_1_l1_power: float | None = None  # smartLoad1L1ActivePower
    smart_load_1_l2_power: float | None = None  # smartLoad1L2ActivePower
    smart_load_2_l1_power: float | None = None  # smartLoad2L1ActivePower
    smart_load_2_l2_power: float | None = None  # smartLoad2L2ActivePower
    smart_load_3_l1_power: float | None = None  # smartLoad3L1ActivePower
    smart_load_3_l2_power: float | None = None  # smartLoad3L2ActivePower
    smart_load_4_l1_power: float | None = None  # smartLoad4L1ActivePower
    smart_load_4_l2_power: float | None = None  # smartLoad4L2ActivePower

    # -------------------------------------------------------------------------
    # Smart Port Status (0=off, 1=smart load, 2=ac_couple)
    # Note: Not available via Modbus, only via HTTP API
    # -------------------------------------------------------------------------
    smart_port_1_status: int | None = None  # smartPort1Status
    smart_port_2_status: int | None = None  # smartPort2Status
    smart_port_3_status: int | None = None  # smartPort3Status
    smart_port_4_status: int | None = None  # smartPort4Status

    # -------------------------------------------------------------------------
    # Frequency (Hz)
    # -------------------------------------------------------------------------
    phase_lock_freq: float | None = None  # phaseLockFreq
    grid_frequency: float | None = None  # gridFreq
    gen_frequency: float | None = None  # genFreq

    # -------------------------------------------------------------------------
    # Energy Today (kWh) - Daily accumulated energy
    # -------------------------------------------------------------------------
    load_energy_today_l1: float | None = None  # eLoadTodayL1
    load_energy_today_l2: float | None = None  # eLoadTodayL2
    ups_energy_today_l1: float | None = None  # eUpsTodayL1
    ups_energy_today_l2: float | None = None  # eUpsTodayL2
    to_grid_energy_today_l1: float | None = None  # eToGridTodayL1
    to_grid_energy_today_l2: float | None = None  # eToGridTodayL2
    to_user_energy_today_l1: float | None = None  # eToUserTodayL1
    to_user_energy_today_l2: float | None = None  # eToUserTodayL2
    ac_couple_1_energy_today_l1: float | None = None  # eACcouple1TodayL1
    ac_couple_1_energy_today_l2: float | None = None  # eACcouple1TodayL2
    smart_load_1_energy_today_l1: float | None = None  # eSmartLoad1TodayL1
    smart_load_1_energy_today_l2: float | None = None  # eSmartLoad1TodayL2

    # -------------------------------------------------------------------------
    # Energy Total (kWh) - Lifetime accumulated energy
    # -------------------------------------------------------------------------
    load_energy_total_l1: float | None = None  # eLoadTotalL1
    load_energy_total_l2: float | None = None  # eLoadTotalL2
    ups_energy_total_l1: float | None = None  # eUpsTotalL1
    ups_energy_total_l2: float | None = None  # eUpsTotalL2
    to_grid_energy_total_l1: float | None = None  # eToGridTotalL1
    to_grid_energy_total_l2: float | None = None  # eToGridTotalL2
    to_user_energy_total_l1: float | None = None  # eToUserTotalL1
    to_user_energy_total_l2: float | None = None  # eToUserTotalL2
    ac_couple_1_energy_total_l1: float | None = None  # eACcouple1TotalL1
    ac_couple_1_energy_total_l2: float | None = None  # eACcouple1TotalL2
    smart_load_1_energy_total_l1: float | None = None  # eSmartLoad1TotalL1
    smart_load_1_energy_total_l2: float | None = None  # eSmartLoad1TotalL2

    # -------------------------------------------------------------------------
    # Computed totals (convenience) - returns None if any component is None
    # -------------------------------------------------------------------------
    @property
    def grid_power(self) -> float | None:
        """Total grid power (L1 + L2). Returns None if any component unavailable."""
        if self.grid_l1_power is None or self.grid_l2_power is None:
            return None
        return self.grid_l1_power + self.grid_l2_power

    @property
    def load_power(self) -> float | None:
        """Total load power (L1 + L2). Returns None if any component unavailable."""
        if self.load_l1_power is None or self.load_l2_power is None:
            return None
        return self.load_l1_power + self.load_l2_power

    @property
    def gen_power(self) -> float | None:
        """Total generator power (L1 + L2). Returns None if any component unavailable."""
        if self.gen_l1_power is None or self.gen_l2_power is None:
            return None
        return self.gen_l1_power + self.gen_l2_power

    @property
    def ups_power(self) -> float | None:
        """Total UPS power (L1 + L2). Returns None if any component unavailable."""
        if self.ups_l1_power is None or self.ups_l2_power is None:
            return None
        return self.ups_l1_power + self.ups_l2_power

    @property
    def smart_load_total_power(self) -> float | None:
        """Total smart load power across all ports. Returns None if any unavailable."""
        values = [
            self.smart_load_1_l1_power,
            self.smart_load_1_l2_power,
            self.smart_load_2_l1_power,
            self.smart_load_2_l2_power,
            self.smart_load_3_l1_power,
            self.smart_load_3_l2_power,
            self.smart_load_4_l1_power,
            self.smart_load_4_l2_power,
        ]
        if any(v is None for v in values):
            return None
        return sum(v for v in values if v is not None)

    @property
    def computed_hybrid_power(self) -> float | None:
        """Computed hybrid power when not available from registers.

        For Modbus/dongle reads, hybrid_power is not available in registers.
        The web API computes it as: ups_power - grid_power

        This represents the total AC power flowing through the hybrid
        inverter system. When exporting (grid_power negative), hybrid_power
        equals UPS power plus export power.

        Falls back to ups_power alone if grid_power is unavailable (grid
        power registers are often zero via Modbus/dongle).

        Returns None if UPS power is unavailable.
        """
        if self.hybrid_power is not None and self.hybrid_power != 0.0:
            return self.hybrid_power
        if self.ups_power is None:
            return None
        grid = self.grid_power if self.grid_power is not None else 0.0
        return self.ups_power - grid

    @classmethod
    def from_http_response(cls, midbox_data: MidboxData) -> MidboxRuntimeData:
        """Create from HTTP API MidboxData response.

        Args:
            midbox_data: Pydantic model from HTTP API (nested in MidboxRuntime)

        Returns:
            Transport-agnostic runtime data with scaling applied
        """
        return cls(
            timestamp=datetime.now(),
            # Voltages (raw values are volts, no scaling needed)
            grid_voltage=float(midbox_data.gridRmsVolt),
            ups_voltage=float(midbox_data.upsRmsVolt),
            gen_voltage=float(midbox_data.genRmsVolt),
            grid_l1_voltage=float(midbox_data.gridL1RmsVolt),
            grid_l2_voltage=float(midbox_data.gridL2RmsVolt),
            ups_l1_voltage=float(midbox_data.upsL1RmsVolt),
            ups_l2_voltage=float(midbox_data.upsL2RmsVolt),
            gen_l1_voltage=float(midbox_data.genL1RmsVolt),
            gen_l2_voltage=float(midbox_data.genL2RmsVolt),
            # Currents (API returns centiamps, divide by 100)
            grid_l1_current=float(midbox_data.gridL1RmsCurr) / 100.0,
            grid_l2_current=float(midbox_data.gridL2RmsCurr) / 100.0,
            load_l1_current=float(midbox_data.loadL1RmsCurr) / 100.0,
            load_l2_current=float(midbox_data.loadL2RmsCurr) / 100.0,
            gen_l1_current=float(midbox_data.genL1RmsCurr) / 100.0,
            gen_l2_current=float(midbox_data.genL2RmsCurr) / 100.0,
            ups_l1_current=float(midbox_data.upsL1RmsCurr) / 100.0,
            ups_l2_current=float(midbox_data.upsL2RmsCurr) / 100.0,
            # Power (raw watts, no scaling)
            grid_l1_power=float(midbox_data.gridL1ActivePower),
            grid_l2_power=float(midbox_data.gridL2ActivePower),
            load_l1_power=float(midbox_data.loadL1ActivePower),
            load_l2_power=float(midbox_data.loadL2ActivePower),
            gen_l1_power=float(midbox_data.genL1ActivePower),
            gen_l2_power=float(midbox_data.genL2ActivePower),
            ups_l1_power=float(midbox_data.upsL1ActivePower),
            ups_l2_power=float(midbox_data.upsL2ActivePower),
            hybrid_power=float(midbox_data.hybridPower),
            # Smart Load Power
            smart_load_1_l1_power=float(midbox_data.smartLoad1L1ActivePower),
            smart_load_1_l2_power=float(midbox_data.smartLoad1L2ActivePower),
            smart_load_2_l1_power=float(midbox_data.smartLoad2L1ActivePower),
            smart_load_2_l2_power=float(midbox_data.smartLoad2L2ActivePower),
            smart_load_3_l1_power=float(midbox_data.smartLoad3L1ActivePower),
            smart_load_3_l2_power=float(midbox_data.smartLoad3L2ActivePower),
            smart_load_4_l1_power=float(midbox_data.smartLoad4L1ActivePower),
            smart_load_4_l2_power=float(midbox_data.smartLoad4L2ActivePower),
            # Smart Port Status (only available via HTTP API)
            smart_port_1_status=midbox_data.smartPort1Status,
            smart_port_2_status=midbox_data.smartPort2Status,
            smart_port_3_status=midbox_data.smartPort3Status,
            smart_port_4_status=midbox_data.smartPort4Status,
            # Frequency (API returns centihertz, divide by 100)
            grid_frequency=float(midbox_data.gridFreq) / 100.0,
            # Note: phaseLockFreq and genFreq not in MidboxData model
            # Energy Today (API returns 0.1 kWh units, scale to kWh)
            load_energy_today_l1=(
                float(midbox_data.eLoadTodayL1) / 10.0
                if midbox_data.eLoadTodayL1 is not None
                else 0.0
            ),
            load_energy_today_l2=(
                float(midbox_data.eLoadTodayL2) / 10.0
                if midbox_data.eLoadTodayL2 is not None
                else 0.0
            ),
            ups_energy_today_l1=(
                float(midbox_data.eUpsTodayL1) / 10.0
                if midbox_data.eUpsTodayL1 is not None
                else 0.0
            ),
            ups_energy_today_l2=(
                float(midbox_data.eUpsTodayL2) / 10.0
                if midbox_data.eUpsTodayL2 is not None
                else 0.0
            ),
            to_grid_energy_today_l1=(
                float(midbox_data.eToGridTodayL1) / 10.0
                if midbox_data.eToGridTodayL1 is not None
                else 0.0
            ),
            to_grid_energy_today_l2=(
                float(midbox_data.eToGridTodayL2) / 10.0
                if midbox_data.eToGridTodayL2 is not None
                else 0.0
            ),
            to_user_energy_today_l1=(
                float(midbox_data.eToUserTodayL1) / 10.0
                if midbox_data.eToUserTodayL1 is not None
                else 0.0
            ),
            to_user_energy_today_l2=(
                float(midbox_data.eToUserTodayL2) / 10.0
                if midbox_data.eToUserTodayL2 is not None
                else 0.0
            ),
            ac_couple_1_energy_today_l1=(
                float(midbox_data.eACcouple1TodayL1) / 10.0
                if midbox_data.eACcouple1TodayL1 is not None
                else 0.0
            ),
            ac_couple_1_energy_today_l2=(
                float(midbox_data.eACcouple1TodayL2) / 10.0
                if midbox_data.eACcouple1TodayL2 is not None
                else 0.0
            ),
            smart_load_1_energy_today_l1=(
                float(midbox_data.eSmartLoad1TodayL1) / 10.0
                if midbox_data.eSmartLoad1TodayL1 is not None
                else 0.0
            ),
            smart_load_1_energy_today_l2=(
                float(midbox_data.eSmartLoad1TodayL2) / 10.0
                if midbox_data.eSmartLoad1TodayL2 is not None
                else 0.0
            ),
            # Energy Total (API returns 0.1 kWh units, scale to kWh)
            load_energy_total_l1=(
                float(midbox_data.eLoadTotalL1) / 10.0
                if midbox_data.eLoadTotalL1 is not None
                else 0.0
            ),
            load_energy_total_l2=(
                float(midbox_data.eLoadTotalL2) / 10.0
                if midbox_data.eLoadTotalL2 is not None
                else 0.0
            ),
            ups_energy_total_l1=(
                float(midbox_data.eUpsTotalL1) / 10.0
                if midbox_data.eUpsTotalL1 is not None
                else 0.0
            ),
            ups_energy_total_l2=(
                float(midbox_data.eUpsTotalL2) / 10.0
                if midbox_data.eUpsTotalL2 is not None
                else 0.0
            ),
            to_grid_energy_total_l1=(
                float(midbox_data.eToGridTotalL1) / 10.0
                if midbox_data.eToGridTotalL1 is not None
                else 0.0
            ),
            to_grid_energy_total_l2=(
                float(midbox_data.eToGridTotalL2) / 10.0
                if midbox_data.eToGridTotalL2 is not None
                else 0.0
            ),
            to_user_energy_total_l1=(
                float(midbox_data.eToUserTotalL1) / 10.0
                if midbox_data.eToUserTotalL1 is not None
                else 0.0
            ),
            to_user_energy_total_l2=(
                float(midbox_data.eToUserTotalL2) / 10.0
                if midbox_data.eToUserTotalL2 is not None
                else 0.0
            ),
            ac_couple_1_energy_total_l1=(
                float(midbox_data.eACcouple1TotalL1) / 10.0
                if midbox_data.eACcouple1TotalL1 is not None
                else 0.0
            ),
            ac_couple_1_energy_total_l2=(
                float(midbox_data.eACcouple1TotalL2) / 10.0
                if midbox_data.eACcouple1TotalL2 is not None
                else 0.0
            ),
            smart_load_1_energy_total_l1=(
                float(midbox_data.eSmartLoad1TotalL1) / 10.0
                if midbox_data.eSmartLoad1TotalL1 is not None
                else 0.0
            ),
            smart_load_1_energy_total_l2=(
                float(midbox_data.eSmartLoad1TotalL2) / 10.0
                if midbox_data.eSmartLoad1TotalL2 is not None
                else 0.0
            ),
        )

    @classmethod
    def from_modbus_registers(
        cls,
        input_registers: dict[int, int],
        register_map: MidboxRuntimeRegisterMap | None = None,
        energy_map: MidboxEnergyRegisterMap | None = None,
    ) -> MidboxRuntimeData:
        """Create from Modbus input register values.

        Note: GridBOSS/MID devices use INPUT registers (function 0x04) for runtime data.

        Args:
            input_registers: Dict mapping register address to raw value
            register_map: Optional MidboxRuntimeRegisterMap for register locations.
                If None, defaults to GRIDBOSS_RUNTIME_MAP.
            energy_map: Optional MidboxEnergyRegisterMap for energy register locations.
                If None, defaults to GRIDBOSS_ENERGY_MAP. Pass None explicitly to skip
                energy field reading.

        Returns:
            Transport-agnostic runtime data with scaling applied
        """
        from pylxpweb.transports.register_maps import (
            GRIDBOSS_ENERGY_MAP,
            GRIDBOSS_RUNTIME_MAP,
        )

        if register_map is None:
            register_map = GRIDBOSS_RUNTIME_MAP

        if energy_map is None:
            energy_map = GRIDBOSS_ENERGY_MAP

        return cls(
            timestamp=datetime.now(),
            # Voltages (scale /10 - raw register value is volts × 10)
            grid_voltage=_read_and_scale_field(input_registers, register_map.grid_voltage),
            ups_voltage=_read_and_scale_field(input_registers, register_map.ups_voltage),
            gen_voltage=_read_and_scale_field(input_registers, register_map.gen_voltage),
            grid_l1_voltage=_read_and_scale_field(input_registers, register_map.grid_l1_voltage),
            grid_l2_voltage=_read_and_scale_field(input_registers, register_map.grid_l2_voltage),
            ups_l1_voltage=_read_and_scale_field(input_registers, register_map.ups_l1_voltage),
            ups_l2_voltage=_read_and_scale_field(input_registers, register_map.ups_l2_voltage),
            gen_l1_voltage=_read_and_scale_field(input_registers, register_map.gen_l1_voltage),
            gen_l2_voltage=_read_and_scale_field(input_registers, register_map.gen_l2_voltage),
            # Currents (scale /100 for amps)
            grid_l1_current=_read_and_scale_field(input_registers, register_map.grid_l1_current),
            grid_l2_current=_read_and_scale_field(input_registers, register_map.grid_l2_current),
            load_l1_current=_read_and_scale_field(input_registers, register_map.load_l1_current),
            load_l2_current=_read_and_scale_field(input_registers, register_map.load_l2_current),
            gen_l1_current=_read_and_scale_field(input_registers, register_map.gen_l1_current),
            gen_l2_current=_read_and_scale_field(input_registers, register_map.gen_l2_current),
            ups_l1_current=_read_and_scale_field(input_registers, register_map.ups_l1_current),
            ups_l2_current=_read_and_scale_field(input_registers, register_map.ups_l2_current),
            # Power (no scaling - raw watts, signed)
            grid_l1_power=_read_and_scale_field(input_registers, register_map.grid_l1_power),
            grid_l2_power=_read_and_scale_field(input_registers, register_map.grid_l2_power),
            load_l1_power=_read_and_scale_field(input_registers, register_map.load_l1_power),
            load_l2_power=_read_and_scale_field(input_registers, register_map.load_l2_power),
            gen_l1_power=_read_and_scale_field(input_registers, register_map.gen_l1_power),
            gen_l2_power=_read_and_scale_field(input_registers, register_map.gen_l2_power),
            ups_l1_power=_read_and_scale_field(input_registers, register_map.ups_l1_power),
            ups_l2_power=_read_and_scale_field(input_registers, register_map.ups_l2_power),
            hybrid_power=_read_and_scale_field(input_registers, register_map.hybrid_power),
            # Smart Load Power (watts, signed)
            smart_load_1_l1_power=_read_and_scale_field(
                input_registers, register_map.smart_load_1_l1_power
            ),
            smart_load_1_l2_power=_read_and_scale_field(
                input_registers, register_map.smart_load_1_l2_power
            ),
            smart_load_2_l1_power=_read_and_scale_field(
                input_registers, register_map.smart_load_2_l1_power
            ),
            smart_load_2_l2_power=_read_and_scale_field(
                input_registers, register_map.smart_load_2_l2_power
            ),
            smart_load_3_l1_power=_read_and_scale_field(
                input_registers, register_map.smart_load_3_l1_power
            ),
            smart_load_3_l2_power=_read_and_scale_field(
                input_registers, register_map.smart_load_3_l2_power
            ),
            smart_load_4_l1_power=_read_and_scale_field(
                input_registers, register_map.smart_load_4_l1_power
            ),
            smart_load_4_l2_power=_read_and_scale_field(
                input_registers, register_map.smart_load_4_l2_power
            ),
            # Smart Port Status (0=off, 1=smart_load, 2=ac_couple)
            # Note: Smart port status registers conflict with energy totals.
            # These are only available via HTTP API, will be 0 when reading from Modbus.
            smart_port_1_status=_read_register_field(
                input_registers, register_map.smart_port_1_status
            ),
            smart_port_2_status=_read_register_field(
                input_registers, register_map.smart_port_2_status
            ),
            smart_port_3_status=_read_register_field(
                input_registers, register_map.smart_port_3_status
            ),
            smart_port_4_status=_read_register_field(
                input_registers, register_map.smart_port_4_status
            ),
            # Frequency (scale /100 for Hz)
            phase_lock_freq=_read_and_scale_field(input_registers, register_map.phase_lock_freq),
            grid_frequency=_read_and_scale_field(input_registers, register_map.grid_frequency),
            gen_frequency=_read_and_scale_field(input_registers, register_map.gen_frequency),
            # Energy Today (kWh, scale /10)
            load_energy_today_l1=_read_and_scale_field(
                input_registers, energy_map.load_energy_today_l1
            ),
            load_energy_today_l2=_read_and_scale_field(
                input_registers, energy_map.load_energy_today_l2
            ),
            ups_energy_today_l1=_read_and_scale_field(
                input_registers, energy_map.ups_energy_today_l1
            ),
            ups_energy_today_l2=_read_and_scale_field(
                input_registers, energy_map.ups_energy_today_l2
            ),
            to_grid_energy_today_l1=_read_and_scale_field(
                input_registers, energy_map.to_grid_energy_today_l1
            ),
            to_grid_energy_today_l2=_read_and_scale_field(
                input_registers, energy_map.to_grid_energy_today_l2
            ),
            to_user_energy_today_l1=_read_and_scale_field(
                input_registers, energy_map.to_user_energy_today_l1
            ),
            to_user_energy_today_l2=_read_and_scale_field(
                input_registers, energy_map.to_user_energy_today_l2
            ),
            ac_couple_1_energy_today_l1=_read_and_scale_field(
                input_registers, energy_map.ac_couple_1_energy_today_l1
            ),
            ac_couple_1_energy_today_l2=_read_and_scale_field(
                input_registers, energy_map.ac_couple_1_energy_today_l2
            ),
            smart_load_1_energy_today_l1=_read_and_scale_field(
                input_registers, energy_map.smart_load_1_energy_today_l1
            ),
            smart_load_1_energy_today_l2=_read_and_scale_field(
                input_registers, energy_map.smart_load_1_energy_today_l2
            ),
            # Energy Total (kWh, 32-bit, scale /10)
            load_energy_total_l1=_read_and_scale_field(
                input_registers, energy_map.load_energy_total_l1
            ),
            load_energy_total_l2=_read_and_scale_field(
                input_registers, energy_map.load_energy_total_l2
            ),
            ups_energy_total_l1=_read_and_scale_field(
                input_registers, energy_map.ups_energy_total_l1
            ),
            ups_energy_total_l2=_read_and_scale_field(
                input_registers, energy_map.ups_energy_total_l2
            ),
            to_grid_energy_total_l1=_read_and_scale_field(
                input_registers, energy_map.to_grid_energy_total_l1
            ),
            to_grid_energy_total_l2=_read_and_scale_field(
                input_registers, energy_map.to_grid_energy_total_l2
            ),
            to_user_energy_total_l1=_read_and_scale_field(
                input_registers, energy_map.to_user_energy_total_l1
            ),
            to_user_energy_total_l2=_read_and_scale_field(
                input_registers, energy_map.to_user_energy_total_l2
            ),
            ac_couple_1_energy_total_l1=_read_and_scale_field(
                input_registers, energy_map.ac_couple_1_energy_total_l1
            ),
            ac_couple_1_energy_total_l2=_read_and_scale_field(
                input_registers, energy_map.ac_couple_1_energy_total_l2
            ),
            smart_load_1_energy_total_l1=_read_and_scale_field(
                input_registers, energy_map.smart_load_1_energy_total_l1
            ),
            smart_load_1_energy_total_l2=_read_and_scale_field(
                input_registers, energy_map.smart_load_1_energy_total_l2
            ),
        )

    def to_dict(self) -> dict[str, float | int | None]:
        """Convert to dictionary with MidboxData-compatible field names.

        This provides backward compatibility with code expecting the old
        dict[str, float | int] return type from read_midbox_runtime().

        Note:
            Values may be None if the corresponding register read failed.
            This allows Home Assistant to show "unavailable" state.
            See: eg4_web_monitor issue #91

        Returns:
            Dictionary with camelCase field names matching MidboxData model
        """
        return {
            # Voltages
            "gridRmsVolt": self.grid_voltage,
            "upsRmsVolt": self.ups_voltage,
            "genRmsVolt": self.gen_voltage,
            "gridL1RmsVolt": self.grid_l1_voltage,
            "gridL2RmsVolt": self.grid_l2_voltage,
            "upsL1RmsVolt": self.ups_l1_voltage,
            "upsL2RmsVolt": self.ups_l2_voltage,
            "genL1RmsVolt": self.gen_l1_voltage,
            "genL2RmsVolt": self.gen_l2_voltage,
            # Currents
            "gridL1RmsCurr": self.grid_l1_current,
            "gridL2RmsCurr": self.grid_l2_current,
            "loadL1RmsCurr": self.load_l1_current,
            "loadL2RmsCurr": self.load_l2_current,
            "genL1RmsCurr": self.gen_l1_current,
            "genL2RmsCurr": self.gen_l2_current,
            "upsL1RmsCurr": self.ups_l1_current,
            "upsL2RmsCurr": self.ups_l2_current,
            # Power
            "gridL1ActivePower": self.grid_l1_power,
            "gridL2ActivePower": self.grid_l2_power,
            "loadL1ActivePower": self.load_l1_power,
            "loadL2ActivePower": self.load_l2_power,
            "genL1ActivePower": self.gen_l1_power,
            "genL2ActivePower": self.gen_l2_power,
            "upsL1ActivePower": self.ups_l1_power,
            "upsL2ActivePower": self.ups_l2_power,
            "hybridPower": self.computed_hybrid_power,
            # Smart Load Power
            "smartLoad1L1ActivePower": self.smart_load_1_l1_power,
            "smartLoad1L2ActivePower": self.smart_load_1_l2_power,
            "smartLoad2L1ActivePower": self.smart_load_2_l1_power,
            "smartLoad2L2ActivePower": self.smart_load_2_l2_power,
            "smartLoad3L1ActivePower": self.smart_load_3_l1_power,
            "smartLoad3L2ActivePower": self.smart_load_3_l2_power,
            "smartLoad4L1ActivePower": self.smart_load_4_l1_power,
            "smartLoad4L2ActivePower": self.smart_load_4_l2_power,
            # Smart Port Status
            "smartPort1Status": self.smart_port_1_status,
            "smartPort2Status": self.smart_port_2_status,
            "smartPort3Status": self.smart_port_3_status,
            "smartPort4Status": self.smart_port_4_status,
            # Frequency
            "phaseLockFreq": self.phase_lock_freq,
            "gridFreq": self.grid_frequency,
            "genFreq": self.gen_frequency,
            # Energy Today (kWh)
            "eLoadTodayL1": self.load_energy_today_l1,
            "eLoadTodayL2": self.load_energy_today_l2,
            "eUpsTodayL1": self.ups_energy_today_l1,
            "eUpsTodayL2": self.ups_energy_today_l2,
            "eToGridTodayL1": self.to_grid_energy_today_l1,
            "eToGridTodayL2": self.to_grid_energy_today_l2,
            "eToUserTodayL1": self.to_user_energy_today_l1,
            "eToUserTodayL2": self.to_user_energy_today_l2,
            "eACcouple1TodayL1": self.ac_couple_1_energy_today_l1,
            "eACcouple1TodayL2": self.ac_couple_1_energy_today_l2,
            "eSmartLoad1TodayL1": self.smart_load_1_energy_today_l1,
            "eSmartLoad1TodayL2": self.smart_load_1_energy_today_l2,
            # Energy Total (kWh)
            "eLoadTotalL1": self.load_energy_total_l1,
            "eLoadTotalL2": self.load_energy_total_l2,
            "eUpsTotalL1": self.ups_energy_total_l1,
            "eUpsTotalL2": self.ups_energy_total_l2,
            "eToGridTotalL1": self.to_grid_energy_total_l1,
            "eToGridTotalL2": self.to_grid_energy_total_l2,
            "eToUserTotalL1": self.to_user_energy_total_l1,
            "eToUserTotalL2": self.to_user_energy_total_l2,
            "eACcouple1TotalL1": self.ac_couple_1_energy_total_l1,
            "eACcouple1TotalL2": self.ac_couple_1_energy_total_l2,
            "eSmartLoad1TotalL1": self.smart_load_1_energy_total_l1,
            "eSmartLoad1TotalL2": self.smart_load_1_energy_total_l2,
        }
