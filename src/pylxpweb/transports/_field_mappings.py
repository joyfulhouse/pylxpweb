"""Canonical register name → data-model field name mappings.

Each dict maps ``RegisterDefinition.canonical_name`` to the corresponding
field on the transport-agnostic dataclass in ``data.py``.

A value of ``None`` means the register exists in the canonical map but has
no direct dataclass field (it's either handled specially like packed
registers, or not exposed on that data model).
"""

from __future__ import annotations

# =========================================================================
# InverterRuntimeData  (from RegisterCategory.RUNTIME and related)
# =========================================================================

RUNTIME_FIELD: dict[str, str | None] = {
    # Device Status
    "device_status": "device_status",
    # PV Input
    "pv1_voltage": "pv1_voltage",
    "pv2_voltage": "pv2_voltage",
    "pv3_voltage": "pv3_voltage",
    "pv1_power": "pv1_power",
    "pv2_power": "pv2_power",
    "pv3_power": "pv3_power",
    "pv1_current": "pv1_current",
    "pv2_current": "pv2_current",
    "pv3_current": "pv3_current",
    # Battery
    "battery_voltage": "battery_voltage",
    "soc_soh_packed": None,  # → battery_soc, battery_soh (unpacked)
    "charge_power": "battery_charge_power",
    "discharge_power": "battery_discharge_power",
    "battery_current_bms": "battery_current",
    # Grid / AC Input
    "grid_voltage_r": "grid_voltage_r",
    "grid_voltage_s": "grid_voltage_s",
    "grid_voltage_t": "grid_voltage_t",
    "grid_l1_voltage": "grid_l1_voltage",
    "grid_l2_voltage": "grid_l2_voltage",
    "grid_frequency": "grid_frequency",
    "inverter_power": "inverter_power",
    "rectifier_power": "grid_power",
    "power_factor": "power_factor",
    # EPS / Off-Grid
    "eps_voltage_r": "eps_voltage_r",
    "eps_voltage_s": "eps_voltage_s",
    "eps_voltage_t": "eps_voltage_t",
    "eps_l1_voltage": "eps_l1_voltage",
    "eps_l2_voltage": "eps_l2_voltage",
    "eps_frequency": "eps_frequency",
    "eps_power": "eps_power",
    "eps_apparent_power": "eps_apparent_power",
    "power_to_grid": "power_to_grid",
    "power_to_user": "power_from_grid",
    # Load
    "output_power": "output_power",
    # Internal
    "bus_voltage_1": "bus_voltage_1",
    "bus_voltage_2": "bus_voltage_2",
    # Temperatures
    "internal_temperature": "internal_temperature",
    "radiator_temperature_1": "radiator_temperature_1",
    "radiator_temperature_2": "radiator_temperature_2",
    "battery_temperature": "battery_temperature",
    "temperature_t1": "temperature_t1",
    "temperature_t2": "temperature_t2",
    "temperature_t3": "temperature_t3",
    "temperature_t4": "temperature_t4",
    "temperature_t5": "temperature_t5",
    # Fault / Warning (inverter-level)
    "fault_code": None,  # Combined with bms_fault_code
    "warning_code": None,  # Combined with bms_warning_code
    "bms_fault_code": None,  # Combined with fault_code
    "bms_warning_code": None,  # Combined with warning_code
    # BMS
    "bms_charge_current_limit": "bms_charge_current_limit",
    "bms_discharge_current_limit": "bms_discharge_current_limit",
    "bms_charge_voltage_ref": "bms_charge_voltage_ref",
    "bms_discharge_cutoff": "bms_discharge_cutoff",
    "bms_max_cell_voltage": "bms_max_cell_voltage",
    "bms_min_cell_voltage": "bms_min_cell_voltage",
    "bms_max_cell_temperature": "bms_max_cell_temperature",
    "bms_min_cell_temperature": "bms_min_cell_temperature",
    "bms_cycle_count": "bms_cycle_count",
    "battery_parallel_count": "battery_parallel_num",
    "battery_capacity_ah": "battery_capacity_ah",
    # Inverter RMS Current
    "inverter_rms_current_r": "inverter_rms_current_r",
    "inverter_rms_current_s": "inverter_rms_current_s",
    "inverter_rms_current_t": "inverter_rms_current_t",
    # EPS per-leg power (split-phase, regs 129-132)
    "eps_l1_power": "eps_l1_power",
    "eps_l2_power": "eps_l2_power",
    "eps_l1_apparent_power": "eps_l1_apparent_power",
    "eps_l2_apparent_power": "eps_l2_apparent_power",
    # Generator
    "generator_voltage": "generator_voltage",
    "generator_frequency": "generator_frequency",
    "generator_power": "generator_power",
    "ac_couple_power": "ac_couple_power",
    # Operational
    "running_time": "inverter_on_time",
    "ac_input_type": "ac_input_type",
    # US split-phase per-leg grid power (regs 195-204)
    "generator_l1_voltage": "generator_l1_voltage",
    "generator_l2_voltage": "generator_l2_voltage",
    "inverter_power_l1": "inverter_power_l1",
    "inverter_power_l2": "inverter_power_l2",
    "rectifier_power_l1": "rectifier_power_l1",
    "rectifier_power_l2": "rectifier_power_l2",
    "grid_export_power_l1": "grid_export_power_l1",
    "grid_export_power_l2": "grid_export_power_l2",
    "grid_import_power_l1": "grid_import_power_l1",
    "grid_import_power_l2": "grid_import_power_l2",
    # Parallel
    "parallel_config": None,  # → parallel_master_slave, parallel_phase, parallel_number
}

# Canonical names that map to InverterRuntimeData.load_power.
# The legacy code read "load_power" from register_map.load_power (reg 27 = Ptouser).
# In the canonical defs, reg 27 is "power_to_user". The legacy code also aliased
# register_map.load_power for power_from_grid.
RUNTIME_LOAD_POWER_CANONICAL = "power_to_user"

# =========================================================================
# InverterEnergyData
# =========================================================================

ENERGY_FIELD: dict[str, str | None] = {
    "pv1_energy_today": "pv1_energy_today",
    "pv2_energy_today": "pv2_energy_today",
    "pv3_energy_today": "pv3_energy_today",
    "inverter_energy_today": "inverter_energy_today",
    "charge_energy_today": "charge_energy_today",
    "discharge_energy_today": "discharge_energy_today",
    "eps_energy_today": "eps_energy_today",
    "grid_export_energy_today": "grid_export_today",
    "grid_import_energy_today": "grid_import_today",
    # Legacy mapped reg 32 (Erec_day = AC charge rectifier energy) to load_energy_today.
    # Canonical defs have the real load_energy_today at reg 171, but the legacy behavior
    # used ac_charge_energy_today for this field. Preserve backward compatibility.
    "ac_charge_energy_today": "load_energy_today",
    "pv1_energy_total": "pv1_energy_total",
    "pv2_energy_total": "pv2_energy_total",
    "pv3_energy_total": "pv3_energy_total",
    "inverter_energy_total": "inverter_energy_total",
    "charge_energy_total": "charge_energy_total",
    "discharge_energy_total": "discharge_energy_total",
    "eps_energy_total": "eps_energy_total",
    "grid_export_energy_total": "grid_export_total",
    "grid_import_energy_total": "grid_import_total",
    # Legacy mapped regs 48-49 (Erec_all = AC charge rectifier energy total) to load_energy_total.
    # Same backward-compat mapping as load_energy_today above.
    "ac_charge_energy_total": "load_energy_total",
    "generator_energy_today": "generator_energy_today",
    "generator_energy_total": "generator_energy_total",
    # EPS per-leg energy (split-phase, regs 133-138)
    "eps_l1_energy_today": "eps_l1_energy_today",
    "eps_l2_energy_today": "eps_l2_energy_today",
    "eps_l1_energy_total": "eps_l1_energy_total",
    "eps_l2_energy_total": "eps_l2_energy_total",
}

# =========================================================================
# BatteryData  (from BatteryRegisterDefinition)
# =========================================================================

BATTERY_FIELD: dict[str, str | None] = {
    "battery_status_header": None,  # Checked for presence, not a field
    "battery_full_capacity": "max_capacity",
    "battery_charge_voltage_ref": "charge_voltage_ref",
    "battery_charge_current_limit": "charge_current_limit",
    "battery_discharge_current_limit": "discharge_current_limit",
    "battery_discharge_voltage_cutoff": "discharge_voltage_cutoff",
    "battery_voltage": "voltage",
    "battery_current": "current",
    "battery_soc": "soc",
    "battery_soh": "soh",
    "battery_cycle_count": "cycle_count",
    "battery_max_cell_temp": "max_cell_temperature",
    "battery_min_cell_temp": "min_cell_temperature",
    "battery_max_cell_voltage": "max_cell_voltage",
    "battery_min_cell_voltage": "min_cell_voltage",
    "battery_max_cell_num_voltage": "max_cell_num_voltage",
    "battery_min_cell_num_voltage": "min_cell_num_voltage",
    "battery_max_cell_num_temp": "max_cell_num_temp",
    "battery_min_cell_num_temp": "min_cell_num_temp",
    "battery_firmware_version": None,  # Special packed handling
    "battery_serial_number": None,  # Special multi-register read
}

# =========================================================================
# MidboxRuntimeData  (from GridBossRegisterDefinition)
# =========================================================================

GRIDBOSS_FIELD: dict[str, str | None] = {
    # Voltage
    "grid_voltage": "grid_voltage",
    "ups_voltage": "ups_voltage",
    "gen_voltage": "gen_voltage",
    "grid_l1_voltage": "grid_l1_voltage",
    "grid_l2_voltage": "grid_l2_voltage",
    "ups_l1_voltage": "ups_l1_voltage",
    "ups_l2_voltage": "ups_l2_voltage",
    "gen_l1_voltage": "gen_l1_voltage",
    "gen_l2_voltage": "gen_l2_voltage",
    # Current
    "grid_l1_current": "grid_l1_current",
    "grid_l2_current": "grid_l2_current",
    "load_l1_current": "load_l1_current",
    "load_l2_current": "load_l2_current",
    "gen_l1_current": "gen_l1_current",
    "gen_l2_current": "gen_l2_current",
    "ups_l1_current": "ups_l1_current",
    "ups_l2_current": "ups_l2_current",
    # Smart Port Current
    "smart_port1_l1_current": "smart_port_1_l1_current",
    "smart_port1_l2_current": "smart_port_1_l2_current",
    "smart_port2_l1_current": "smart_port_2_l1_current",
    "smart_port2_l2_current": "smart_port_2_l2_current",
    "smart_port3_l1_current": "smart_port_3_l1_current",
    "smart_port3_l2_current": "smart_port_3_l2_current",
    "smart_port4_l1_current": "smart_port_4_l1_current",
    "smart_port4_l2_current": "smart_port_4_l2_current",
    # Power
    "grid_l1_power": "grid_l1_power",
    "grid_l2_power": "grid_l2_power",
    "load_l1_power": "load_l1_power",
    "load_l2_power": "load_l2_power",
    "gen_l1_power": "gen_l1_power",
    "gen_l2_power": "gen_l2_power",
    "ups_l1_power": "ups_l1_power",
    "ups_l2_power": "ups_l2_power",
    # Smart Load Power (canonical omits underscore before number)
    "smart_load1_l1_power": "smart_load_1_l1_power",
    "smart_load1_l2_power": "smart_load_1_l2_power",
    "smart_load2_l1_power": "smart_load_2_l1_power",
    "smart_load2_l2_power": "smart_load_2_l2_power",
    "smart_load3_l1_power": "smart_load_3_l1_power",
    "smart_load3_l2_power": "smart_load_3_l2_power",
    "smart_load4_l1_power": "smart_load_4_l1_power",
    "smart_load4_l2_power": "smart_load_4_l2_power",
    # Smart Port Status — decoded from bit-packed holding register 20,
    # not from individual canonical register definitions.
    # Frequency
    "phase_lock_frequency": "phase_lock_freq",
    "grid_frequency": "grid_frequency",
    "gen_frequency": "gen_frequency",
    # Energy Today
    "load_energy_today_l1": "load_energy_today_l1",
    "load_energy_today_l2": "load_energy_today_l2",
    "ups_energy_today_l1": "ups_energy_today_l1",
    "ups_energy_today_l2": "ups_energy_today_l2",
    "grid_export_today_l1": "to_grid_energy_today_l1",
    "grid_export_today_l2": "to_grid_energy_today_l2",
    "grid_import_today_l1": "to_user_energy_today_l1",
    "grid_import_today_l2": "to_user_energy_today_l2",
    "smart_load1_energy_today_l1": "smart_load_1_energy_today_l1",
    "smart_load1_energy_today_l2": "smart_load_1_energy_today_l2",
    "smart_load2_energy_today_l1": "smart_load_2_energy_today_l1",
    "smart_load2_energy_today_l2": "smart_load_2_energy_today_l2",
    "smart_load3_energy_today_l1": "smart_load_3_energy_today_l1",
    "smart_load3_energy_today_l2": "smart_load_3_energy_today_l2",
    "smart_load4_energy_today_l1": "smart_load_4_energy_today_l1",
    "smart_load4_energy_today_l2": "smart_load_4_energy_today_l2",
    "ac_couple1_energy_today_l1": "ac_couple_1_energy_today_l1",
    "ac_couple1_energy_today_l2": "ac_couple_1_energy_today_l2",
    "ac_couple2_energy_today_l1": "ac_couple_2_energy_today_l1",
    "ac_couple2_energy_today_l2": "ac_couple_2_energy_today_l2",
    "ac_couple3_energy_today_l1": "ac_couple_3_energy_today_l1",
    "ac_couple3_energy_today_l2": "ac_couple_3_energy_today_l2",
    "ac_couple4_energy_today_l1": "ac_couple_4_energy_today_l1",
    "ac_couple4_energy_today_l2": "ac_couple_4_energy_today_l2",
    # Energy Total
    "load_energy_total_l1": "load_energy_total_l1",
    "load_energy_total_l2": "load_energy_total_l2",
    "ups_energy_total_l1": "ups_energy_total_l1",
    "ups_energy_total_l2": "ups_energy_total_l2",
    "grid_export_total_l1": "to_grid_energy_total_l1",
    "grid_export_total_l2": "to_grid_energy_total_l2",
    "grid_import_total_l1": "to_user_energy_total_l1",
    "grid_import_total_l2": "to_user_energy_total_l2",
    "smart_load1_energy_total_l1": "smart_load_1_energy_total_l1",
    "smart_load1_energy_total_l2": "smart_load_1_energy_total_l2",
    "smart_load2_energy_total_l1": "smart_load_2_energy_total_l1",
    "smart_load2_energy_total_l2": "smart_load_2_energy_total_l2",
    "smart_load3_energy_total_l1": "smart_load_3_energy_total_l1",
    "smart_load3_energy_total_l2": "smart_load_3_energy_total_l2",
    "smart_load4_energy_total_l1": "smart_load_4_energy_total_l1",
    "smart_load4_energy_total_l2": "smart_load_4_energy_total_l2",
    "ac_couple1_energy_total_l1": "ac_couple_1_energy_total_l1",
    "ac_couple1_energy_total_l2": "ac_couple_1_energy_total_l2",
    "ac_couple2_energy_total_l1": "ac_couple_2_energy_total_l1",
    "ac_couple2_energy_total_l2": "ac_couple_2_energy_total_l2",
    "ac_couple3_energy_total_l1": "ac_couple_3_energy_total_l1",
    "ac_couple3_energy_total_l2": "ac_couple_3_energy_total_l2",
    "ac_couple4_energy_total_l1": "ac_couple_4_energy_total_l1",
    "ac_couple4_energy_total_l2": "ac_couple_4_energy_total_l2",
}

# Categories from RegisterCategory used for Runtime readings
# Values must match RegisterCategory enum values (lowercase)
RUNTIME_CATEGORIES: frozenset[str] = frozenset(
    {
        "runtime",
        "bms",
        "temperature",
        "status",
        "fault",
        "generator",
        "parallel",
    }
)

# Categories used for Energy readings
ENERGY_CATEGORIES: frozenset[str] = frozenset(
    {
        "energy_daily",
        "energy_lifetime",
    }
)
