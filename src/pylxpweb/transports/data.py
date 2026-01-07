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

_LOGGER = logging.getLogger(__name__)


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
    battery_control_temperature: float = 0.0  # °C

    # Status
    device_status: int = 0  # Status code
    fault_code: int = 0  # Fault code
    warning_code: int = 0  # Warning code

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
    ) -> InverterRuntimeData:
        """Create from Modbus input register values.

        Args:
            input_registers: Dict mapping register address to raw value

        Returns:
            Transport-agnostic runtime data with scaling applied
        """
        from pylxpweb.constants.scaling import ScaleFactor, apply_scale

        def get_reg(addr: int, default: int = 0) -> int:
            """Get register value with default."""
            return input_registers.get(addr, default)

        def get_reg_pair(high_addr: int, low_addr: int) -> int:
            """Get 32-bit value from register pair (high, low)."""
            high = get_reg(high_addr)
            low = get_reg(low_addr)
            return (high << 16) | low

        # Get power values from register pairs
        pv1_power = get_reg_pair(6, 7)
        pv2_power = get_reg_pair(8, 9)
        pv3_power = get_reg_pair(10, 11)
        charge_power = get_reg_pair(12, 13)
        discharge_power = get_reg_pair(14, 15)
        inverter_power = get_reg_pair(20, 21)
        grid_power = get_reg_pair(22, 23)
        eps_power = get_reg_pair(30, 31)
        load_power = get_reg_pair(34, 35)

        return cls(
            timestamp=datetime.now(),
            # PV
            pv1_voltage=apply_scale(get_reg(1), ScaleFactor.SCALE_10),
            pv1_power=float(pv1_power),
            pv2_voltage=apply_scale(get_reg(2), ScaleFactor.SCALE_10),
            pv2_power=float(pv2_power),
            pv3_voltage=apply_scale(get_reg(3), ScaleFactor.SCALE_10),
            pv3_power=float(pv3_power),
            pv_total_power=float(pv1_power + pv2_power + pv3_power),
            # Battery
            battery_voltage=apply_scale(get_reg(4), ScaleFactor.SCALE_100),
            battery_soc=get_reg(5),
            battery_charge_power=float(charge_power),
            battery_discharge_power=float(discharge_power),
            battery_temperature=float(get_reg(64)),
            # Grid
            grid_voltage_r=apply_scale(get_reg(16), ScaleFactor.SCALE_10),
            grid_voltage_s=apply_scale(get_reg(17), ScaleFactor.SCALE_10),
            grid_voltage_t=apply_scale(get_reg(18), ScaleFactor.SCALE_10),
            grid_frequency=apply_scale(get_reg(19), ScaleFactor.SCALE_100),
            grid_power=float(grid_power),
            power_to_grid=float(get_reg(33)),
            power_from_grid=float(grid_power),
            # Inverter
            inverter_power=float(inverter_power),
            # EPS
            eps_voltage_r=apply_scale(get_reg(26), ScaleFactor.SCALE_10),
            eps_voltage_s=apply_scale(get_reg(27), ScaleFactor.SCALE_10),
            eps_voltage_t=apply_scale(get_reg(28), ScaleFactor.SCALE_10),
            eps_frequency=apply_scale(get_reg(29), ScaleFactor.SCALE_100),
            eps_power=float(eps_power),
            eps_status=get_reg(32),
            # Load
            load_power=float(load_power),
            # Internal
            bus_voltage_1=apply_scale(get_reg(43), ScaleFactor.SCALE_10),
            bus_voltage_2=apply_scale(get_reg(44), ScaleFactor.SCALE_10),
            # Temperatures
            internal_temperature=float(get_reg(61)),
            radiator_temperature_1=float(get_reg(62)),
            radiator_temperature_2=float(get_reg(63)),
            # Status
            device_status=get_reg(0),
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
    ) -> InverterEnergyData:
        """Create from Modbus input register values.

        Args:
            input_registers: Dict mapping register address to raw value

        Returns:
            Transport-agnostic energy data with scaling applied
        """
        from pylxpweb.constants.scaling import ScaleFactor, apply_scale

        def get_reg(addr: int, default: int = 0) -> int:
            """Get register value with default."""
            return input_registers.get(addr, default)

        def get_reg_pair(high_addr: int, low_addr: int) -> int:
            """Get 32-bit value from register pair."""
            high = get_reg(high_addr)
            low = get_reg(low_addr)
            return (high << 16) | low

        # Modbus energy values are in 0.1 Wh, convert to kWh
        def to_kwh(raw_value: int) -> float:
            """Convert raw register value (0.1 Wh units) to kWh.

            Conversion: raw / 10 = Wh, then / 1000 = kWh
            Example: 184000 -> 18400 Wh -> 18.4 kWh
            """
            return apply_scale(raw_value, ScaleFactor.SCALE_10) / 1000.0

        return cls(
            timestamp=datetime.now(),
            # Daily energy from register pairs
            inverter_energy_today=to_kwh(get_reg_pair(45, 46)),
            grid_import_today=to_kwh(get_reg_pair(47, 48)),
            charge_energy_today=to_kwh(get_reg_pair(49, 50)),
            discharge_energy_today=to_kwh(get_reg_pair(51, 52)),
            eps_energy_today=to_kwh(get_reg_pair(53, 54)),
            grid_export_today=to_kwh(get_reg_pair(55, 56)),
            load_energy_today=to_kwh(get_reg_pair(57, 58)),
            pv1_energy_today=to_kwh(get_reg_pair(97, 98)),
            pv2_energy_today=to_kwh(get_reg_pair(99, 100)),
            pv3_energy_today=to_kwh(get_reg_pair(101, 102)),
            # Lifetime energy
            inverter_energy_total=to_kwh(get_reg(36) * 1000),
            grid_import_total=to_kwh(get_reg(37) * 1000),
            charge_energy_total=to_kwh(get_reg(38) * 1000),
            discharge_energy_total=to_kwh(get_reg(39) * 1000),
            eps_energy_total=to_kwh(get_reg(40) * 1000),
            grid_export_total=to_kwh(get_reg(41) * 1000),
            load_energy_total=to_kwh(get_reg(42) * 1000),
            pv1_energy_total=to_kwh(get_reg_pair(91, 92)),
            pv2_energy_total=to_kwh(get_reg_pair(93, 94)),
            pv3_energy_total=to_kwh(get_reg_pair(95, 96)),
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
