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
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pylxpweb.transports._canonical_reader import (
    clamp_percentage as _clamp_percentage,
)
from pylxpweb.transports._canonical_reader import (
    read_raw,
    read_scaled,
    unpack_parallel_config,
)
from pylxpweb.transports._canonical_reader import (
    sum_optional as _sum_optional,
)
from pylxpweb.transports._field_mappings import (
    BATTERY_FIELD,
    ENERGY_CATEGORIES,
    ENERGY_FIELD,
    GRIDBOSS_FIELD,
    RUNTIME_CATEGORIES,
    RUNTIME_FIELD,
)

if TYPE_CHECKING:
    from pylxpweb.models import EnergyInfo, InverterRuntime, MidboxData

_LOGGER = logging.getLogger(__name__)


# Legacy helper aliases are now imported from _canonical_reader.py:
# _clamp_percentage = clamp_percentage
# _sum_optional = sum_optional


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
    # Extended Sensors - Inverter RMS Current & Power (3-phase R/S/T)
    # -------------------------------------------------------------------------
    inverter_rms_current_r: float | None = None  # A (Inverter RMS current R-phase)
    inverter_rms_current_s: float | None = None  # A (Inverter RMS current S-phase)
    inverter_rms_current_t: float | None = None  # A (Inverter RMS current T-phase)
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

    # Pre-clamp raw values for corruption detection (populated by __post_init__)
    _raw_soc: int | None = field(default=None, repr=False)
    _raw_soh: int | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Validate and clamp percentage values (if not None)."""
        self._raw_soc = self.battery_soc
        self._raw_soh = self.battery_soh
        self.battery_soc = _clamp_percentage(self.battery_soc, "battery_soc")
        self.battery_soh = _clamp_percentage(self.battery_soh, "battery_soh")

    def is_corrupt(self, max_power_watts: float = 0.0) -> bool:
        """Check if runtime data contains physically impossible values.

        Returns True if any canary field indicates corrupted register data.
        Canaries are deliberately conservative to avoid false positives:
        - SoC/SoH > 100 (pre-clamp raw value)
        - Grid frequency > 0 but outside 30-90 Hz (0 is valid in off-grid/EPS mode)
        - Power fields exceeding max_power_watts (when > 0, i.e. rated power known)

        Args:
            max_power_watts: Maximum plausible power in watts, computed as
                ``rated_power_kw * 2000`` (2x margin).  When 0, power checks
                are skipped (rated power not yet known).
        """
        if self._raw_soc is not None and self._raw_soc > 100:
            _LOGGER.warning("Canary: raw_soc=%d > 100", self._raw_soc)
            return True
        if self._raw_soh is not None and self._raw_soh > 100:
            _LOGGER.warning("Canary: raw_soh=%d > 100", self._raw_soh)
            return True
        # Allow frequency=0 (off-grid/EPS mode) and None (not read yet).
        # Wide 30-90 Hz band: corrupt reads produce wildly wrong values (e.g.
        # 6553 Hz from 0xFFFF), not borderline deviations.
        if (
            self.grid_frequency is not None
            and self.grid_frequency > 0
            and (self.grid_frequency < 30 or self.grid_frequency > 90)
        ):
            _LOGGER.warning("Canary: grid_frequency=%.1f outside 30-90", self.grid_frequency)
            return True
        # Power bounds: only checked when rated power is known (max_power_watts > 0).
        # Corrupt 16-bit reads produce 0xFFFF = 65535W, which exceeds 2x rated
        # for all EG4 models (6-21 kW → 12000-42000W threshold).
        if max_power_watts > 0:
            for label, val in (
                ("pv_total_power", self.pv_total_power),
                ("battery_charge_power", self.battery_charge_power),
                ("battery_discharge_power", self.battery_discharge_power),
                ("inverter_power", self.inverter_power),
                ("eps_power", self.eps_power),
            ):
                if val is not None and abs(val) > max_power_watts:
                    _LOGGER.warning(
                        "Canary: %s=%.0f exceeds max %.0fW",
                        label,
                        val,
                        max_power_watts,
                    )
                    return True
        return False

    @property
    def fault_messages(self) -> list[str]:
        """Active inverter fault descriptions decoded from bitfield."""
        from pylxpweb.constants.fault_codes import INVERTER_FAULT_CODES, decode_fault_bits

        if self.fault_code is None or self.fault_code == 0:
            return []
        return decode_fault_bits(self.fault_code, INVERTER_FAULT_CODES)

    @property
    def warning_messages(self) -> list[str]:
        """Active inverter warning descriptions decoded from bitfield."""
        from pylxpweb.constants.fault_codes import INVERTER_WARNING_CODES, decode_fault_bits

        if self.warning_code is None or self.warning_code == 0:
            return []
        return decode_fault_bits(self.warning_code, INVERTER_WARNING_CODES)

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
        model_family: str = "EG4_HYBRID",
    ) -> InverterRuntimeData:
        """Create from Modbus input register values.

        Uses canonical register definitions from ``registers/inverter_input.py``
        to read and scale values.  The ``model_family`` parameter controls
        which registers are included (e.g. ``"EG4_HYBRID"`` vs ``"LXP"``).

        Args:
            input_registers: Dict mapping register address to raw value
            model_family: Inverter family string (``"EG4_HYBRID"``,
                ``"EG4_OFFGRID"``, or ``"LXP"``).

        Returns:
            Transport-agnostic runtime data with scaling applied
        """
        from pylxpweb.registers.inverter_input import BY_NAME, registers_for_model

        # Get registers applicable to this model, filtered to runtime categories
        model_regs = registers_for_model(model_family)
        runtime_regs = [r for r in model_regs if r.category.value in RUNTIME_CATEGORIES]

        # Build kwargs dict from canonical definitions
        kwargs: dict[str, Any] = {}
        # Track special values for post-processing
        inverter_fault_code: int | None = None
        bms_fault_code: int | None = None
        inverter_warning_code: int | None = None
        bms_warning_code: int | None = None

        for reg in runtime_regs:
            field_name = RUNTIME_FIELD.get(reg.canonical_name)
            if field_name is None:
                # Special handling: packed registers, fault/warning codes
                if reg.canonical_name == "soc_soh_packed":
                    raw = read_raw(input_registers, reg)
                    if raw is not None:
                        soc = raw & 0xFF
                        soh = (raw >> 8) & 0xFF
                        if soh == 0:
                            soh = 100  # Default to 100% if not reported
                        kwargs["battery_soc"] = soc
                        kwargs["battery_soh"] = soh
                elif reg.canonical_name == "parallel_config":
                    ms, phase, number = unpack_parallel_config(input_registers, reg)
                    kwargs["parallel_master_slave"] = ms
                    kwargs["parallel_phase"] = phase
                    kwargs["parallel_number"] = number
                elif reg.canonical_name == "fault_code":
                    inverter_fault_code = read_raw(input_registers, reg)
                elif reg.canonical_name == "bms_fault_code":
                    bms_fault_code = read_raw(input_registers, reg)
                elif reg.canonical_name == "warning_code":
                    inverter_warning_code = read_raw(input_registers, reg)
                elif reg.canonical_name == "bms_warning_code":
                    bms_warning_code = read_raw(input_registers, reg)
                continue

            # Fields that need raw int values (no scaling)
            int_fields = {
                "device_status",
                "eps_status",
                "bms_cycle_count",
                "battery_parallel_num",
                "inverter_on_time",
                "ac_input_type",
            }
            if field_name in int_fields:
                kwargs[field_name] = read_raw(input_registers, reg)
            else:
                kwargs[field_name] = read_scaled(input_registers, reg)

        # Combine fault/warning codes (inverter + BMS) — prefer non-zero
        kwargs["fault_code"] = inverter_fault_code if inverter_fault_code else bms_fault_code
        kwargs["warning_code"] = (
            inverter_warning_code if inverter_warning_code else bms_warning_code
        )

        # Compute derived fields
        kwargs["pv_total_power"] = _sum_optional(
            kwargs.get("pv1_power"), kwargs.get("pv2_power"), kwargs.get("pv3_power")
        )

        # load_power comes from power_to_user (reg 27), power_from_grid also
        # maps to the same register in the legacy code
        load_power_reg = BY_NAME.get("power_to_user")
        if load_power_reg is not None:
            load_val = read_scaled(input_registers, load_power_reg)
            kwargs.setdefault("load_power", load_val)
            kwargs.setdefault("power_from_grid", load_val)

        return cls(timestamp=datetime.now(), **kwargs)


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

    def lifetime_energy_values(self) -> dict[str, float | None]:
        """Return all lifetime energy fields as a dict for monotonicity validation.

        Only includes ``*_total`` fields (not daily or per-string totals)
        that should never decrease between poll cycles.
        """
        return {
            "pv_energy_total": self.pv_energy_total,
            "charge_energy_total": self.charge_energy_total,
            "discharge_energy_total": self.discharge_energy_total,
            "grid_import_total": self.grid_import_total,
            "grid_export_total": self.grid_export_total,
            "load_energy_total": self.load_energy_total,
            "inverter_energy_total": self.inverter_energy_total,
            "eps_energy_total": self.eps_energy_total,
        }

    def is_corrupt(self) -> bool:
        """Check if energy data contains physically impossible values.

        Energy registers have no strong physical-bounds canaries (all values
        are monotonic counters or daily accumulations). Temporal validation
        (monotonicity checks) occurs in the device refresh layer via
        ``_is_energy_valid()``.
        """
        return False

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
        model_family: str = "EG4_HYBRID",
    ) -> InverterEnergyData:
        """Create from Modbus input register values.

        Uses canonical register definitions from ``registers/inverter_input.py``.

        Args:
            input_registers: Dict mapping register address to raw value
            model_family: Inverter family string for model filtering.

        Returns:
            Transport-agnostic energy data with scaling applied
        """
        from pylxpweb.registers.inverter_input import registers_for_model

        model_regs = registers_for_model(model_family)
        energy_regs = [r for r in model_regs if r.category.value in ENERGY_CATEGORIES]

        kwargs: dict[str, float | None] = {}
        for reg in energy_regs:
            field_name = ENERGY_FIELD.get(reg.canonical_name)
            if field_name is None:
                continue
            kwargs[field_name] = read_scaled(input_registers, reg)

        # Compute PV totals from per-string values
        kwargs["pv_energy_today"] = _sum_optional(
            kwargs.get("pv1_energy_today"),
            kwargs.get("pv2_energy_today"),
            kwargs.get("pv3_energy_today"),
        )
        kwargs["pv_energy_total"] = _sum_optional(
            kwargs.get("pv1_energy_total"),
            kwargs.get("pv2_energy_total"),
            kwargs.get("pv3_energy_total"),
        )

        return cls(timestamp=datetime.now(), **kwargs)


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
    current_capacity: float | None = None  # Ah (computed from max_capacity * soc / 100)
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
    # Note: Model and battery type are only available via Web API.
    # Not accessible via direct Modbus - the BMS sends this info via CAN bus
    # which the dongle forwards to the cloud, but doesn't expose via Modbus.
    # In hybrid mode, these are supplemented from cloud API with hourly TTL.
    model: str = ""  # Battery model (e.g., "WP-16/280-1AWLL") - Web API only
    battery_type: str = ""  # Battery type code (e.g., "LITHIUM") - Web API only
    battery_type_text: str = ""  # Battery type display (e.g., "Lithium") - Web API only
    firmware_version: str = ""  # Firmware version string (e.g., "2.17") - Modbus available

    # Status
    status: int = 0
    fault_code: int = 0
    warning_code: int = 0

    # Pre-clamp raw values for corruption detection (populated by __post_init__)
    _raw_soc: int = field(default=0, repr=False)
    _raw_soh: int = field(default=100, repr=False)

    def __post_init__(self) -> None:
        """Validate and clamp percentage values."""
        self._raw_soc = self.soc
        self._raw_soh = self.soh
        # soc/soh are non-nullable (defaults 0/100), so _clamp_percentage
        # always returns a non-None int here.
        self.soc = _clamp_percentage(self.soc, "battery_soc") or 0
        self.soh = _clamp_percentage(self.soh, "battery_soh") or 100

    def is_corrupt(self) -> bool:
        """Check if battery data contains physically impossible values.

        Returns True if any canary field indicates corrupted register data.
        Canaries: SoC/SoH > 100 (raw pre-clamp), voltage > 100V (scaled;
        catches catastrophic corruption like 0xFFFF → ~6553V).
        Batteries with voltage=0 (no CAN data) are NOT corrupt — just absent.
        """
        if self._raw_soc > 100:
            _LOGGER.warning(
                "Battery %d canary: raw_soc=%d > 100",
                self.battery_index,
                self._raw_soc,
            )
            return True
        if self._raw_soh > 100:
            _LOGGER.warning(
                "Battery %d canary: raw_soh=%d > 100",
                self.battery_index,
                self._raw_soh,
            )
            return True
        if self.voltage > 100.0:
            _LOGGER.warning(
                "Battery %d canary: voltage=%.1f > 100V",
                self.battery_index,
                self.voltage,
            )
            return True
        # Cell voltage bounds: LFP cells operate 2.5-3.65V, generous range
        # 1.0-5.0V.  Zero means no data (valid).  Corrupt reads produce
        # 65.535V (0xFFFF/1000) or sub-1V partial register values.
        for label, v in (
            ("max_cell_voltage", self.max_cell_voltage),
            ("min_cell_voltage", self.min_cell_voltage),
        ):
            if v > 0 and (v < 1.0 or v > 5.0):
                _LOGGER.warning(
                    "Battery %d canary: %s=%.3f outside 1.0-5.0V",
                    self.battery_index,
                    label,
                    v,
                )
                return True
        # Inversion: min_cell_voltage must not exceed max_cell_voltage.
        # Skip when either is 0.0 (no data from BMS).
        if (
            self.max_cell_voltage > 0
            and self.min_cell_voltage > 0
            and self.min_cell_voltage > self.max_cell_voltage
        ):
            _LOGGER.warning(
                "Battery %d canary: min_cell_voltage=%.3f > max_cell_voltage=%.3f",
                self.battery_index,
                self.min_cell_voltage,
                self.max_cell_voltage,
            )
            return True
        return False

    @property
    def remaining_capacity(self) -> float | None:
        """Calculate remaining capacity in Ah from max_capacity and SOC.

        Returns:
            Remaining capacity in Ah (max_capacity * soc / 100), or None if unavailable
        """
        if self.max_capacity > 0 and self.soc > 0:
            return self.max_capacity * self.soc / 100
        return None

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
            Capacity percentage (0-100), or SOC if current_capacity unavailable.
        """
        current_cap = self.current_capacity
        if self.max_capacity > 0 and current_cap is not None and current_cap > 0:
            return round((current_cap / self.max_capacity) * 100)
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

        Uses canonical definitions from ``registers/battery.py``.  The
        *registers* dict should contain the 30-register block for this
        battery with keys as absolute register addresses (5002-5031 for
        battery 0, etc.).

        Args:
            battery_index: 0-based battery index
            registers: Dict mapping register address to raw value

        Returns:
            BatteryData with all values properly scaled, or None if battery not present
        """
        from pylxpweb.registers.battery import (
            BATTERY_BASE_ADDRESS,
            BATTERY_REGISTER_COUNT,
            BATTERY_REGISTERS,
        )
        from pylxpweb.registers.battery import (
            BY_NAME as BAT_BY_NAME,
        )
        from pylxpweb.transports._canonical_reader import (
            read_battery_firmware,
            read_battery_serial,
        )

        base = BATTERY_BASE_ADDRESS + (battery_index * BATTERY_REGISTER_COUNT)

        # Check if battery is present via status header (offset 0)
        status_reg = BAT_BY_NAME["battery_status_header"]
        status_raw = read_raw(registers, status_reg, base_address=base)
        if not status_raw:
            return None  # Battery slot is empty

        # Build kwargs from canonical definitions using BATTERY_FIELD mapping
        kwargs: dict[str, float | int] = {}
        soc: int = 0
        soh: int = 100

        for reg in BATTERY_REGISTERS:
            cname = reg.canonical_name

            # Handle packed SOC/SOH
            if cname == "battery_soc":
                raw = read_raw(registers, reg, base_address=base)
                soc = raw if raw is not None else 0
                continue
            if cname == "battery_soh":
                raw = read_raw(registers, reg, base_address=base)
                soh = raw if raw is not None else 0
                continue

            # Handle packed cell number registers
            if cname in (
                "battery_max_cell_num_voltage",
                "battery_min_cell_num_voltage",
                "battery_max_cell_num_temp",
                "battery_min_cell_num_temp",
            ):
                field_name = BATTERY_FIELD.get(cname)
                if field_name is not None:
                    raw = read_raw(registers, reg, base_address=base)
                    kwargs[field_name] = raw if raw is not None else 0
                continue

            # Handle firmware and serial (special multi-register reads)
            if cname == "battery_firmware_version":
                continue  # handled below
            if cname == "battery_serial_number":
                continue  # handled below
            if cname == "battery_status_header":
                continue  # already checked

            field_name = BATTERY_FIELD.get(cname)
            if field_name is None:
                continue

            # Cycle count is an int field (no scaling)
            if cname == "battery_cycle_count":
                raw = read_raw(registers, reg, base_address=base)
                kwargs[field_name] = raw if raw is not None else 0
            else:
                val = read_scaled(registers, reg, base_address=base)
                kwargs[field_name] = val if val is not None else 0.0

        # Firmware version (packed: high byte = major, low byte = minor)
        fw_reg = BAT_BY_NAME["battery_firmware_version"]
        firmware_version = read_battery_firmware(registers, fw_reg, base_address=base)

        # Serial number (7 consecutive registers, 2 ASCII chars each)
        serial_number = read_battery_serial(registers, base_address=base)

        # Compute current_capacity from max_capacity and SOC
        max_capacity = float(kwargs.get("max_capacity", 0.0))
        current_capacity = max_capacity * soc / 100 if max_capacity and soc else None

        # Temperature: use max_cell_temperature as the primary temperature
        max_cell_temp = float(kwargs.get("max_cell_temperature", 0.0))

        return cls(
            battery_index=battery_index,
            serial_number=serial_number,
            voltage=float(kwargs.get("voltage", 0.0)),
            current=float(kwargs.get("current", 0.0)),
            soc=soc,
            soh=soh if soh > 0 else 100,
            temperature=max_cell_temp,
            max_capacity=max_capacity,
            current_capacity=current_capacity,
            cycle_count=int(kwargs.get("cycle_count", 0)),
            min_cell_voltage=float(kwargs.get("min_cell_voltage", 0.0)),
            max_cell_voltage=float(kwargs.get("max_cell_voltage", 0.0)),
            min_cell_temperature=float(kwargs.get("min_cell_temperature", 0.0)),
            max_cell_temperature=max_cell_temp,
            max_cell_num_voltage=int(kwargs.get("max_cell_num_voltage", 0)),
            min_cell_num_voltage=int(kwargs.get("min_cell_num_voltage", 0)),
            max_cell_num_temp=int(kwargs.get("max_cell_num_temp", 0)),
            min_cell_num_temp=int(kwargs.get("min_cell_num_temp", 0)),
            charge_voltage_ref=float(kwargs.get("charge_voltage_ref", 0.0)),
            charge_current_limit=float(kwargs.get("charge_current_limit", 0.0)),
            discharge_current_limit=float(kwargs.get("discharge_current_limit", 0.0)),
            discharge_voltage_cutoff=float(kwargs.get("discharge_voltage_cutoff", 0.0)),
            firmware_version=firmware_version,
            status=status_raw,
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
    status: str | None = None  # "Idle", "Charging", "StandBy", "Discharging"
    fault_code: int | None = None
    warning_code: int | None = None

    # Individual batteries
    battery_count: int | None = None
    batteries: list[BatteryData] = field(default_factory=list)

    # Pre-clamp raw values for corruption detection (populated by __post_init__)
    _raw_soc: int | None = field(default=None, repr=False)
    _raw_soh: int | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Validate and clamp percentage values."""
        self._raw_soc = self.soc
        self._raw_soh = self.soh
        if self.soc is not None:
            self.soc = _clamp_percentage(self.soc, "battery_bank_soc")
        if self.soh is not None:
            self.soh = _clamp_percentage(self.soh, "battery_bank_soh")

    def is_corrupt(self) -> bool:
        """Check if battery bank data contains physically impossible values.

        Returns True if aggregate SoC/SoH > 100, battery count exceeds
        physical maximum, current is impossibly high, or any *present*
        individual battery is corrupt.  Batteries with voltage=0 (no CAN
        bus data) are skipped — they have no real data to validate.
        """
        if self._raw_soc is not None and self._raw_soc > 100:
            _LOGGER.warning("Bank canary: raw_soc=%d > 100", self._raw_soc)
            return True
        if self._raw_soh is not None and self._raw_soh > 100:
            _LOGGER.warning("Bank canary: raw_soh=%d > 100", self._raw_soh)
            return True
        # Battery count: register 96 can return garbage (e.g. 5421) on
        # Modbus desync.  Physical max is BATTERY_MAX_COUNT (4 slots).
        # Use a generous upper bound of 20 to allow for future hardware.
        if self.battery_count is not None and self.battery_count > 20:
            _LOGGER.warning("Bank canary: battery_count=%d > 20", self.battery_count)
            return True
        # Battery current: 500A is well beyond any residential battery
        # system (5 batteries * 100A max each).  Corrupt reads produce
        # values like 2996A from register desync.
        if self.current is not None and abs(self.current) > 500:
            _LOGGER.warning("Bank canary: current=%.1f exceeds 500A", self.current)
            return True
        # Only cascade to batteries that actually have CAN bus data.
        # Ghost batteries (voltage=0, soc=0) from 5002+ register failures
        # are not corrupt — just absent.
        for b in self.batteries:
            if b.voltage == 0 and b.soc == 0:
                continue
            if b.is_corrupt():
                return True
        return False

    @property
    def battery_power(self) -> float | None:
        """Calculate net battery power in watts (V * I).

        Positive = charging, Negative = discharging.

        Returns:
            Battery power in watts, or None if voltage/current unavailable.
        """
        if self.voltage is not None and self.current is not None:
            return round(self.voltage * self.current, 1)
        return None

    @property
    def full_capacity(self) -> float | None:
        """Alias for max_capacity, matching BatteryBank API property name."""
        return self.max_capacity

    @property
    def remain_capacity(self) -> float | None:
        """Alias for current_capacity, matching BatteryBank API property name."""
        return self.current_capacity

    @property
    def capacity_percent(self) -> float | None:
        """Calculate capacity percentage (current / max * 100).

        Returns:
            Capacity percentage (0-100), or None if data unavailable.
        """
        if self.max_capacity and self.current_capacity is not None:
            return round(self.current_capacity / self.max_capacity * 100, 1)
        return None

    # ── Cross-battery diagnostics (mirrors BatteryBank OOP properties) ──

    @property
    def min_soh(self) -> int | None:
        """Minimum SOH across all batteries."""
        vals = [b.soh for b in self.batteries if b.soh is not None]
        return min(vals) if vals else None

    @property
    def soc_delta(self) -> int | None:
        """SOC spread across batteries (max - min)."""
        vals = [b.soc for b in self.batteries if b.soc is not None]
        return max(vals) - min(vals) if len(vals) >= 2 else None

    @property
    def soh_delta(self) -> int | None:
        """SOH spread across batteries (max - min)."""
        vals = [b.soh for b in self.batteries if b.soh is not None]
        return max(vals) - min(vals) if len(vals) >= 2 else None

    @property
    def voltage_delta(self) -> float | None:
        """Voltage spread across batteries (max - min)."""
        vals = [b.voltage for b in self.batteries if b.voltage is not None]
        return round(max(vals) - min(vals), 2) if len(vals) >= 2 else None

    @property
    def cell_voltage_delta_max(self) -> float | None:
        """Worst-case cell imbalance across all batteries."""
        deltas = []
        for b in self.batteries:
            if b.max_cell_voltage and b.min_cell_voltage:
                deltas.append(round(b.max_cell_voltage - b.min_cell_voltage, 3))
        if deltas:
            return max(deltas)
        # Fallback to bank-level BMS registers when individual batteries absent
        if self.max_cell_voltage is not None and self.min_cell_voltage is not None:
            return round(self.max_cell_voltage - self.min_cell_voltage, 3)
        return None

    @property
    def cycle_count_delta(self) -> int | None:
        """Cycle count spread across batteries (max - min)."""
        vals = [b.cycle_count for b in self.batteries if b.cycle_count is not None]
        return max(vals) - min(vals) if len(vals) >= 2 else None

    @property
    def max_cell_temp(self) -> float | None:
        """Highest cell temperature across all batteries."""
        vals = [
            b.max_cell_temperature for b in self.batteries if b.max_cell_temperature is not None
        ]
        if vals:
            return max(vals)
        # Fallback to bank-level BMS register when individual batteries absent
        return self.max_cell_temperature

    @property
    def temp_delta(self) -> float | None:
        """Temperature spread across all batteries (max_cell - min_cell)."""
        max_temps = [
            b.max_cell_temperature for b in self.batteries if b.max_cell_temperature is not None
        ]
        min_temps = [
            b.min_cell_temperature for b in self.batteries if b.min_cell_temperature is not None
        ]
        if max_temps and min_temps:
            return round(max(max_temps) - min(min_temps), 1)
        # Fallback to bank-level BMS registers when individual batteries absent
        if self.max_cell_temperature is not None and self.min_cell_temperature is not None:
            return round(self.max_cell_temperature - self.min_cell_temperature, 1)
        return None

    @classmethod
    def from_modbus_registers(
        cls,
        input_registers: dict[int, int],
        individual_battery_registers: dict[int, int] | None = None,
    ) -> BatteryBankData | None:
        """Create from Modbus input register values.

        Uses canonical register definitions from ``registers/inverter_input.py``
        for the aggregate battery data read from the main input register space,
        and ``registers/battery.py`` for individual battery modules in the
        5000+ range.

        Args:
            input_registers: Dict mapping register address to raw value (0-127)
            individual_battery_registers: Optional dict with extended register
                range (5000+) containing individual battery data. If provided,
                individual batteries will be populated in the batteries list.

        Returns:
            BatteryBankData with all values properly scaled, or None if no battery
        """
        from pylxpweb.registers.battery import BATTERY_MAX_COUNT
        from pylxpweb.registers.inverter_input import BY_NAME

        # Battery voltage from canonical register def
        bat_volt_reg = BY_NAME["battery_voltage"]
        battery_voltage = read_scaled(input_registers, bat_volt_reg)

        # If voltage is too low or None, assume no battery present
        if battery_voltage is None or battery_voltage < 1.0:
            return None

        # SOC/SOH from packed register (low byte = SOC, high byte = SOH)
        soc_soh_reg = BY_NAME["soc_soh_packed"]
        soc_soh_raw = read_raw(input_registers, soc_soh_reg)
        battery_soc: int | None = None
        battery_soh: int | None = None
        if soc_soh_raw is not None:
            battery_soc = soc_soh_raw & 0xFF
            battery_soh = (soc_soh_raw >> 8) & 0xFF

        # Charge/discharge power
        charge_power = read_scaled(input_registers, BY_NAME["charge_power"])
        discharge_power = read_scaled(input_registers, BY_NAME["discharge_power"])

        # Battery current
        battery_current = read_scaled(input_registers, BY_NAME["battery_current_bms"])

        # Battery temperature
        battery_temp = read_scaled(input_registers, BY_NAME["battery_temperature"])

        # BMS data
        bms_fault_code = read_raw(input_registers, BY_NAME["bms_fault_code"])
        bms_warning_code = read_raw(input_registers, BY_NAME["bms_warning_code"])
        battery_count = read_raw(input_registers, BY_NAME["battery_parallel_count"])

        # Derive battery status from charge/discharge power
        battery_status: str | None = None
        if discharge_power is not None and discharge_power > 0:
            battery_status = "Discharging"
        elif charge_power is not None and charge_power > 0:
            battery_status = "Charging"
        elif charge_power is not None or discharge_power is not None:
            battery_status = "Idle"

        # Cell data
        max_cell_voltage = read_scaled(input_registers, BY_NAME["bms_max_cell_voltage"])
        min_cell_voltage = read_scaled(input_registers, BY_NAME["bms_min_cell_voltage"])
        max_cell_temp = read_scaled(input_registers, BY_NAME["bms_max_cell_temperature"])
        min_cell_temp = read_scaled(input_registers, BY_NAME["bms_min_cell_temperature"])
        cycle_count = read_raw(input_registers, BY_NAME["bms_cycle_count"])
        max_capacity = read_scaled(input_registers, BY_NAME["battery_capacity_ah"])

        # Compute current capacity from max_capacity and SOC
        current_capacity: float | None = None
        if max_capacity is not None and battery_soc is not None:
            current_capacity = round(max_capacity * battery_soc / 100)

        # Parse individual battery data if extended registers provided
        batteries: list[BatteryData] = []
        if individual_battery_registers:
            if battery_count is not None and battery_count > 0:
                count_to_use = battery_count
            else:
                count_to_use = BATTERY_MAX_COUNT
            max_to_check = min(count_to_use, BATTERY_MAX_COUNT)
            for idx in range(max_to_check):
                battery_data = BatteryData.from_modbus_registers(
                    battery_index=idx,
                    registers=individual_battery_registers,
                )
                if battery_data is not None:
                    batteries.append(battery_data)

        # Sensible defaults
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
            status=battery_status,
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
    # HTTP: individual API fields (smartPort1Status, etc.)
    # Modbus: bit-packed in HOLDING register 20 (2 bits per port, LSB-first)
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
    ac_couple_2_energy_today_l1: float | None = None  # eACcouple2TodayL1
    ac_couple_2_energy_today_l2: float | None = None  # eACcouple2TodayL2
    ac_couple_3_energy_today_l1: float | None = None  # eACcouple3TodayL1
    ac_couple_3_energy_today_l2: float | None = None  # eACcouple3TodayL2
    ac_couple_4_energy_today_l1: float | None = None  # eACcouple4TodayL1
    ac_couple_4_energy_today_l2: float | None = None  # eACcouple4TodayL2
    smart_load_1_energy_today_l1: float | None = None  # eSmartLoad1TodayL1
    smart_load_1_energy_today_l2: float | None = None  # eSmartLoad1TodayL2
    smart_load_2_energy_today_l1: float | None = None  # eSmartLoad2TodayL1
    smart_load_2_energy_today_l2: float | None = None  # eSmartLoad2TodayL2
    smart_load_3_energy_today_l1: float | None = None  # eSmartLoad3TodayL1
    smart_load_3_energy_today_l2: float | None = None  # eSmartLoad3TodayL2
    smart_load_4_energy_today_l1: float | None = None  # eSmartLoad4TodayL1
    smart_load_4_energy_today_l2: float | None = None  # eSmartLoad4TodayL2

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
    ac_couple_2_energy_total_l1: float | None = None  # eACcouple2TotalL1
    ac_couple_2_energy_total_l2: float | None = None  # eACcouple2TotalL2
    ac_couple_3_energy_total_l1: float | None = None  # eACcouple3TotalL1
    ac_couple_3_energy_total_l2: float | None = None  # eACcouple3TotalL2
    ac_couple_4_energy_total_l1: float | None = None  # eACcouple4TotalL1
    ac_couple_4_energy_total_l2: float | None = None  # eACcouple4TotalL2
    smart_load_1_energy_total_l1: float | None = None  # eSmartLoad1TotalL1
    smart_load_1_energy_total_l2: float | None = None  # eSmartLoad1TotalL2
    smart_load_2_energy_total_l1: float | None = None  # eSmartLoad2TotalL1
    smart_load_2_energy_total_l2: float | None = None  # eSmartLoad2TotalL2
    smart_load_3_energy_total_l1: float | None = None  # eSmartLoad3TotalL1
    smart_load_3_energy_total_l2: float | None = None  # eSmartLoad3TotalL2
    smart_load_4_energy_total_l1: float | None = None  # eSmartLoad4TotalL1
    smart_load_4_energy_total_l2: float | None = None  # eSmartLoad4TotalL2

    def lifetime_energy_values(self) -> dict[str, float | None]:
        """Return all lifetime energy fields as a dict for monotonicity validation.

        Auto-discovers fields matching ``*_energy_total_*`` (not daily)
        that should never decrease between poll cycles.
        """
        return {f.name: getattr(self, f.name) for f in fields(self) if "energy_total" in f.name}

    def is_corrupt(self, max_power_watts: float = 0.0) -> bool:
        """Check if MID runtime data contains physically impossible values.

        Returns True if any canary field indicates corrupted register data.
        Canaries:
        - Grid frequency > 0 but outside 30-90 Hz
        - Smart port status > 2
        - Grid voltage per leg > 300V (register corruption gives ~6553V)
        - Per-leg power fields exceeding max_power_watts (when > 0)

        Args:
            max_power_watts: Maximum plausible power in watts, computed as
                ``system_total_kw * 2000`` (2x margin).  When 0, power checks
                are skipped (system power not yet known).
        """
        if (
            self.grid_frequency is not None
            and self.grid_frequency > 0
            and (self.grid_frequency < 30 or self.grid_frequency > 90)
        ):
            _LOGGER.warning("MID canary: grid_frequency=%.1f outside 30-90", self.grid_frequency)
            return True
        for i, sp in enumerate(
            (
                self.smart_port_1_status,
                self.smart_port_2_status,
                self.smart_port_3_status,
                self.smart_port_4_status,
            ),
            start=1,
        ):
            if sp is not None and sp > 2:
                _LOGGER.warning("MID canary: smart_port_%d_status=%d > 2", i, sp)
                return True
        # Grid voltage: 0V is valid (grid down), but nonzero values below
        # 50V or above 300V indicate register corruption.  Corrupt reads
        # typically produce 0.1-0.3V (partial register) or 6553.5V (0xFFFF/10).
        for label, v in (
            ("grid_l1_voltage", self.grid_l1_voltage),
            ("grid_l2_voltage", self.grid_l2_voltage),
        ):
            if v is not None and ((0 < v < 50) or v > 300):
                _LOGGER.warning("MID canary: %s=%.1f outside valid range", label, v)
                return True
        # Per-leg power bounds: only checked when system power is known.
        # GridBOSS per-leg max = system_total / 2 (split-phase), so
        # max_power_watts already accounts for the full system with margin.
        if max_power_watts > 0:
            for label, val in (
                ("grid_l1_power", self.grid_l1_power),
                ("grid_l2_power", self.grid_l2_power),
                ("load_l1_power", self.load_l1_power),
                ("load_l2_power", self.load_l2_power),
                ("ups_l1_power", self.ups_l1_power),
                ("ups_l2_power", self.ups_l2_power),
            ):
                if val is not None and abs(val) > max_power_watts:
                    _LOGGER.warning(
                        "MID canary: %s=%.0f exceeds max %.0fW",
                        label,
                        val,
                        max_power_watts,
                    )
                    return True
        return False

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

        def _f(v: int | None) -> float | None:
            return float(v) if v is not None else None

        def _f_div(v: int | None, divisor: float) -> float | None:
            return float(v) / divisor if v is not None else None

        return cls(
            timestamp=datetime.now(),
            # Voltages (API returns decivolts, divide by 10)
            grid_voltage=_f_div(midbox_data.gridRmsVolt, 10.0),
            ups_voltage=_f_div(midbox_data.upsRmsVolt, 10.0),
            gen_voltage=_f_div(midbox_data.genRmsVolt, 10.0),
            grid_l1_voltage=_f_div(midbox_data.gridL1RmsVolt, 10.0),
            grid_l2_voltage=_f_div(midbox_data.gridL2RmsVolt, 10.0),
            ups_l1_voltage=_f_div(midbox_data.upsL1RmsVolt, 10.0),
            ups_l2_voltage=_f_div(midbox_data.upsL2RmsVolt, 10.0),
            gen_l1_voltage=_f_div(midbox_data.genL1RmsVolt, 10.0),
            gen_l2_voltage=_f_div(midbox_data.genL2RmsVolt, 10.0),
            # Currents (API returns deciamps, divide by 10)
            grid_l1_current=_f_div(midbox_data.gridL1RmsCurr, 10.0),
            grid_l2_current=_f_div(midbox_data.gridL2RmsCurr, 10.0),
            load_l1_current=_f_div(midbox_data.loadL1RmsCurr, 10.0),
            load_l2_current=_f_div(midbox_data.loadL2RmsCurr, 10.0),
            gen_l1_current=_f_div(midbox_data.genL1RmsCurr, 10.0),
            gen_l2_current=_f_div(midbox_data.genL2RmsCurr, 10.0),
            ups_l1_current=_f_div(midbox_data.upsL1RmsCurr, 10.0),
            ups_l2_current=_f_div(midbox_data.upsL2RmsCurr, 10.0),
            # Power (raw watts, no scaling)
            grid_l1_power=_f(midbox_data.gridL1ActivePower),
            grid_l2_power=_f(midbox_data.gridL2ActivePower),
            load_l1_power=_f(midbox_data.loadL1ActivePower),
            load_l2_power=_f(midbox_data.loadL2ActivePower),
            gen_l1_power=_f(midbox_data.genL1ActivePower),
            gen_l2_power=_f(midbox_data.genL2ActivePower),
            ups_l1_power=_f(midbox_data.upsL1ActivePower),
            ups_l2_power=_f(midbox_data.upsL2ActivePower),
            hybrid_power=_f(midbox_data.hybridPower),
            # Smart Load Power
            smart_load_1_l1_power=_f(midbox_data.smartLoad1L1ActivePower),
            smart_load_1_l2_power=_f(midbox_data.smartLoad1L2ActivePower),
            smart_load_2_l1_power=_f(midbox_data.smartLoad2L1ActivePower),
            smart_load_2_l2_power=_f(midbox_data.smartLoad2L2ActivePower),
            smart_load_3_l1_power=_f(midbox_data.smartLoad3L1ActivePower),
            smart_load_3_l2_power=_f(midbox_data.smartLoad3L2ActivePower),
            smart_load_4_l1_power=_f(midbox_data.smartLoad4L1ActivePower),
            smart_load_4_l2_power=_f(midbox_data.smartLoad4L2ActivePower),
            # Smart Port Status (only available via HTTP API)
            smart_port_1_status=midbox_data.smartPort1Status,
            smart_port_2_status=midbox_data.smartPort2Status,
            smart_port_3_status=midbox_data.smartPort3Status,
            smart_port_4_status=midbox_data.smartPort4Status,
            # Frequency (API returns centihertz, divide by 100)
            phase_lock_freq=_f_div(midbox_data.phaseLockFreq, 100.0),
            grid_frequency=_f_div(midbox_data.gridFreq, 100.0),
            gen_frequency=_f_div(midbox_data.genFreq, 100.0),
            # Energy Today (API returns 0.1 kWh units, scale to kWh)
            load_energy_today_l1=_f_div(midbox_data.eLoadTodayL1, 10.0),
            load_energy_today_l2=_f_div(midbox_data.eLoadTodayL2, 10.0),
            ups_energy_today_l1=_f_div(midbox_data.eUpsTodayL1, 10.0),
            ups_energy_today_l2=_f_div(midbox_data.eUpsTodayL2, 10.0),
            to_grid_energy_today_l1=_f_div(midbox_data.eToGridTodayL1, 10.0),
            to_grid_energy_today_l2=_f_div(midbox_data.eToGridTodayL2, 10.0),
            to_user_energy_today_l1=_f_div(midbox_data.eToUserTodayL1, 10.0),
            to_user_energy_today_l2=_f_div(midbox_data.eToUserTodayL2, 10.0),
            ac_couple_1_energy_today_l1=_f_div(midbox_data.eACcouple1TodayL1, 10.0),
            ac_couple_1_energy_today_l2=_f_div(midbox_data.eACcouple1TodayL2, 10.0),
            ac_couple_2_energy_today_l1=_f_div(midbox_data.eACcouple2TodayL1, 10.0),
            ac_couple_2_energy_today_l2=_f_div(midbox_data.eACcouple2TodayL2, 10.0),
            ac_couple_3_energy_today_l1=_f_div(midbox_data.eACcouple3TodayL1, 10.0),
            ac_couple_3_energy_today_l2=_f_div(midbox_data.eACcouple3TodayL2, 10.0),
            ac_couple_4_energy_today_l1=_f_div(midbox_data.eACcouple4TodayL1, 10.0),
            ac_couple_4_energy_today_l2=_f_div(midbox_data.eACcouple4TodayL2, 10.0),
            smart_load_1_energy_today_l1=_f_div(midbox_data.eSmartLoad1TodayL1, 10.0),
            smart_load_1_energy_today_l2=_f_div(midbox_data.eSmartLoad1TodayL2, 10.0),
            smart_load_2_energy_today_l1=_f_div(midbox_data.eSmartLoad2TodayL1, 10.0),
            smart_load_2_energy_today_l2=_f_div(midbox_data.eSmartLoad2TodayL2, 10.0),
            smart_load_3_energy_today_l1=_f_div(midbox_data.eSmartLoad3TodayL1, 10.0),
            smart_load_3_energy_today_l2=_f_div(midbox_data.eSmartLoad3TodayL2, 10.0),
            smart_load_4_energy_today_l1=_f_div(midbox_data.eSmartLoad4TodayL1, 10.0),
            smart_load_4_energy_today_l2=_f_div(midbox_data.eSmartLoad4TodayL2, 10.0),
            # Energy Total (API returns 0.1 kWh units, scale to kWh)
            load_energy_total_l1=_f_div(midbox_data.eLoadTotalL1, 10.0),
            load_energy_total_l2=_f_div(midbox_data.eLoadTotalL2, 10.0),
            ups_energy_total_l1=_f_div(midbox_data.eUpsTotalL1, 10.0),
            ups_energy_total_l2=_f_div(midbox_data.eUpsTotalL2, 10.0),
            to_grid_energy_total_l1=_f_div(midbox_data.eToGridTotalL1, 10.0),
            to_grid_energy_total_l2=_f_div(midbox_data.eToGridTotalL2, 10.0),
            to_user_energy_total_l1=_f_div(midbox_data.eToUserTotalL1, 10.0),
            to_user_energy_total_l2=_f_div(midbox_data.eToUserTotalL2, 10.0),
            ac_couple_1_energy_total_l1=_f_div(midbox_data.eACcouple1TotalL1, 10.0),
            ac_couple_1_energy_total_l2=_f_div(midbox_data.eACcouple1TotalL2, 10.0),
            ac_couple_2_energy_total_l1=_f_div(midbox_data.eACcouple2TotalL1, 10.0),
            ac_couple_2_energy_total_l2=_f_div(midbox_data.eACcouple2TotalL2, 10.0),
            ac_couple_3_energy_total_l1=_f_div(midbox_data.eACcouple3TotalL1, 10.0),
            ac_couple_3_energy_total_l2=_f_div(midbox_data.eACcouple3TotalL2, 10.0),
            ac_couple_4_energy_total_l1=_f_div(midbox_data.eACcouple4TotalL1, 10.0),
            ac_couple_4_energy_total_l2=_f_div(midbox_data.eACcouple4TotalL2, 10.0),
            smart_load_1_energy_total_l1=_f_div(midbox_data.eSmartLoad1TotalL1, 10.0),
            smart_load_1_energy_total_l2=_f_div(midbox_data.eSmartLoad1TotalL2, 10.0),
            smart_load_2_energy_total_l1=_f_div(midbox_data.eSmartLoad2TotalL1, 10.0),
            smart_load_2_energy_total_l2=_f_div(midbox_data.eSmartLoad2TotalL2, 10.0),
            smart_load_3_energy_total_l1=_f_div(midbox_data.eSmartLoad3TotalL1, 10.0),
            smart_load_3_energy_total_l2=_f_div(midbox_data.eSmartLoad3TotalL2, 10.0),
            smart_load_4_energy_total_l1=_f_div(midbox_data.eSmartLoad4TotalL1, 10.0),
            smart_load_4_energy_total_l2=_f_div(midbox_data.eSmartLoad4TotalL2, 10.0),
        )

    @classmethod
    def from_modbus_registers(
        cls,
        input_registers: dict[int, int],
        *,
        smart_port_mode_reg: int | None = None,
    ) -> MidboxRuntimeData:
        """Create from Modbus input register values.

        Uses canonical register definitions from ``registers/gridboss.py``.
        GridBOSS only has one register layout so no model filtering is needed.

        Args:
            input_registers: Dict mapping register address to raw value
            smart_port_mode_reg: Raw value of holding register 20, which
                contains all 4 smart port modes bit-packed (2 bits each,
                LSB-first). ``None`` if the read failed.

        Returns:
            Transport-agnostic runtime data with scaling applied
        """
        from pylxpweb.registers.gridboss import GRIDBOSS_REGISTERS

        kwargs: dict[str, Any] = {}

        for reg in GRIDBOSS_REGISTERS:
            field_name = GRIDBOSS_FIELD.get(reg.canonical_name)
            if field_name is None:
                continue

            kwargs[field_name] = read_scaled(input_registers, reg)

        # Decode smart port modes from holding register 20 (bit-packed).
        # Each port uses 2 bits: 0=off, 1=smart_load, 2=ac_couple.
        # Bits 0-1 = port 1, bits 2-3 = port 2, bits 4-5 = port 3, bits 6-7 = port 4.
        if smart_port_mode_reg is not None:
            for port in range(1, 5):
                mode = (smart_port_mode_reg >> ((port - 1) * 2)) & 0x03
                kwargs[f"smart_port_{port}_status"] = mode

        return cls(timestamp=datetime.now(), **kwargs)

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
            "eACcouple2TodayL1": self.ac_couple_2_energy_today_l1,
            "eACcouple2TodayL2": self.ac_couple_2_energy_today_l2,
            "eACcouple3TodayL1": self.ac_couple_3_energy_today_l1,
            "eACcouple3TodayL2": self.ac_couple_3_energy_today_l2,
            "eACcouple4TodayL1": self.ac_couple_4_energy_today_l1,
            "eACcouple4TodayL2": self.ac_couple_4_energy_today_l2,
            "eSmartLoad1TodayL1": self.smart_load_1_energy_today_l1,
            "eSmartLoad1TodayL2": self.smart_load_1_energy_today_l2,
            "eSmartLoad2TodayL1": self.smart_load_2_energy_today_l1,
            "eSmartLoad2TodayL2": self.smart_load_2_energy_today_l2,
            "eSmartLoad3TodayL1": self.smart_load_3_energy_today_l1,
            "eSmartLoad3TodayL2": self.smart_load_3_energy_today_l2,
            "eSmartLoad4TodayL1": self.smart_load_4_energy_today_l1,
            "eSmartLoad4TodayL2": self.smart_load_4_energy_today_l2,
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
            "eACcouple2TotalL1": self.ac_couple_2_energy_total_l1,
            "eACcouple2TotalL2": self.ac_couple_2_energy_total_l2,
            "eACcouple3TotalL1": self.ac_couple_3_energy_total_l1,
            "eACcouple3TotalL2": self.ac_couple_3_energy_total_l2,
            "eACcouple4TotalL1": self.ac_couple_4_energy_total_l1,
            "eACcouple4TotalL2": self.ac_couple_4_energy_total_l2,
            "eSmartLoad1TotalL1": self.smart_load_1_energy_total_l1,
            "eSmartLoad1TotalL2": self.smart_load_1_energy_total_l2,
            "eSmartLoad2TotalL1": self.smart_load_2_energy_total_l1,
            "eSmartLoad2TotalL2": self.smart_load_2_energy_total_l2,
            "eSmartLoad3TotalL1": self.smart_load_3_energy_total_l1,
            "eSmartLoad3TotalL2": self.smart_load_3_energy_total_l2,
            "eSmartLoad4TotalL1": self.smart_load_4_energy_total_l1,
            "eSmartLoad4TotalL2": self.smart_load_4_energy_total_l2,
        }
