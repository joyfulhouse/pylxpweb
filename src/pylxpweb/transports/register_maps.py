"""Model-specific Modbus register maps for different inverter families.

This module provides register map definitions that account for the different
Modbus register layouts between inverter model families:
- PV_SERIES (EG4-18KPV): 32-bit power values, standard register addresses
- LXP_EU (LXP-EU 12K): 16-bit power values, 4-register offset for grid/EPS

The key differences are:
| Field | PV_SERIES (18KPV) | LXP_EU (12K) |
|-------|-------------------|--------------|
| pv1_power | 32-bit: regs 6-7 | 16-bit: reg 7 |
| pv2_power | 32-bit: regs 8-9 | 16-bit: reg 8 |
| pv3_power | 32-bit: regs 10-11 | 16-bit: reg 9 |
| charge_power | 32-bit: regs 12-13 | 16-bit: reg 10 |
| discharge_power | 32-bit: regs 14-15 | 16-bit: reg 11 |
| grid_voltage_r | reg 16 | reg 12 |
| grid_frequency | reg 19 | reg 15 |
| inverter_power | 32-bit: regs 20-21 | 16-bit: reg 16 |
| eps_voltage_r | reg 26 | reg 20 |
| eps_power | 32-bit: regs 30-31 | 16-bit: reg 24 |
| load_power | 32-bit: regs 34-35 | 16-bit: reg 27 |

Reference: Yippy's LXP-EU 12K corrections from issue #52
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pylxpweb.constants.scaling import ScaleFactor

if TYPE_CHECKING:
    from pylxpweb.devices.inverters._features import InverterFamily


@dataclass(frozen=True)
class RegisterField:
    """Definition of a single register field.

    Defines how to read a value from Modbus registers, including:
    - Address: The starting register address
    - Bit width: 16-bit (single register) or 32-bit (register pair)
    - Scale factor: How to scale the raw value
    - Signed: Whether the value is signed (two's complement)
    - Little endian: Word order for 32-bit values

    For 32-bit values:
    - little_endian=False (default): high word at address, low word at address+1
    - little_endian=True: low word at address, high word at address+1

    Example:
        # 16-bit voltage at register 16, scale by /10
        grid_voltage = RegisterField(16, 16, ScaleFactor.SCALE_10)

        # 32-bit power at registers 6-7, no scaling (big-endian)
        pv1_power = RegisterField(6, 32, ScaleFactor.SCALE_NONE)

        # 32-bit energy at registers 46-47, little-endian (LuxPower style)
        energy_total = RegisterField(46, 32, ScaleFactor.SCALE_10, little_endian=True)
    """

    address: int
    bit_width: Literal[16, 32] = 16
    scale_factor: ScaleFactor = ScaleFactor.SCALE_NONE
    signed: bool = False
    little_endian: bool = False  # Word order for 32-bit: low word first if True


@dataclass(frozen=True)
class RuntimeRegisterMap:
    """Register map for inverter runtime data extraction.

    Maps all runtime data fields to their register locations for a specific
    inverter model family. Each field is defined as a RegisterField that
    specifies the address, bit width, and scaling.

    Fields set to None are not available for that model family.
    """

    # -------------------------------------------------------------------------
    # Device Status
    # -------------------------------------------------------------------------
    device_status: RegisterField | None = None

    # -------------------------------------------------------------------------
    # PV Input
    # -------------------------------------------------------------------------
    pv1_voltage: RegisterField | None = None
    pv2_voltage: RegisterField | None = None
    pv3_voltage: RegisterField | None = None
    pv1_power: RegisterField | None = None
    pv2_power: RegisterField | None = None
    pv3_power: RegisterField | None = None

    # -------------------------------------------------------------------------
    # Battery
    # -------------------------------------------------------------------------
    battery_voltage: RegisterField | None = None
    battery_current: RegisterField | None = None  # Battery current in A
    soc_soh_packed: RegisterField | None = None  # SOC in low byte, SOH in high byte

    # -------------------------------------------------------------------------
    # Battery Power
    # -------------------------------------------------------------------------
    charge_power: RegisterField | None = None
    discharge_power: RegisterField | None = None

    # -------------------------------------------------------------------------
    # Grid (AC Input)
    # -------------------------------------------------------------------------
    grid_voltage_r: RegisterField | None = None
    grid_voltage_s: RegisterField | None = None
    grid_voltage_t: RegisterField | None = None
    grid_frequency: RegisterField | None = None
    inverter_power: RegisterField | None = None
    grid_power: RegisterField | None = None
    power_factor: RegisterField | None = None

    # -------------------------------------------------------------------------
    # EPS/Off-Grid Output
    # -------------------------------------------------------------------------
    eps_voltage_r: RegisterField | None = None
    eps_voltage_s: RegisterField | None = None
    eps_voltage_t: RegisterField | None = None
    eps_frequency: RegisterField | None = None
    eps_power: RegisterField | None = None
    eps_status: RegisterField | None = None
    power_to_grid: RegisterField | None = None

    # -------------------------------------------------------------------------
    # Load
    # -------------------------------------------------------------------------
    load_power: RegisterField | None = None

    # -------------------------------------------------------------------------
    # Internal Bus
    # -------------------------------------------------------------------------
    bus_voltage_1: RegisterField | None = None
    bus_voltage_2: RegisterField | None = None

    # -------------------------------------------------------------------------
    # Temperatures
    # -------------------------------------------------------------------------
    internal_temperature: RegisterField | None = None
    radiator_temperature_1: RegisterField | None = None
    radiator_temperature_2: RegisterField | None = None
    battery_temperature: RegisterField | None = None

    # -------------------------------------------------------------------------
    # Fault/Warning Codes
    # -------------------------------------------------------------------------
    inverter_fault_code: RegisterField | None = None
    inverter_warning_code: RegisterField | None = None
    bms_fault_code: RegisterField | None = None
    bms_warning_code: RegisterField | None = None

    # -------------------------------------------------------------------------
    # Extended Sensors - Inverter RMS Current & Power Factor
    # -------------------------------------------------------------------------
    inverter_rms_current: RegisterField | None = None  # A (scale 0.01)
    inverter_apparent_power: RegisterField | None = None  # VA

    # -------------------------------------------------------------------------
    # Generator Input (if connected)
    # -------------------------------------------------------------------------
    generator_voltage: RegisterField | None = None  # V (scale 0.1)
    generator_frequency: RegisterField | None = None  # Hz (scale 0.01)
    generator_power: RegisterField | None = None  # W

    # -------------------------------------------------------------------------
    # BMS Limits and Cell Data
    # -------------------------------------------------------------------------
    bms_charge_current_limit: RegisterField | None = None  # A
    bms_discharge_current_limit: RegisterField | None = None  # A
    bms_charge_voltage_ref: RegisterField | None = None  # V (scale 0.1)
    bms_discharge_cutoff: RegisterField | None = None  # V (scale 0.1)
    bms_max_cell_voltage: RegisterField | None = None  # mV
    bms_min_cell_voltage: RegisterField | None = None  # mV
    bms_max_cell_temperature: RegisterField | None = None  # °C
    bms_min_cell_temperature: RegisterField | None = None  # °C
    bms_cycle_count: RegisterField | None = None  # count
    battery_parallel_num: RegisterField | None = None  # count
    battery_capacity_ah: RegisterField | None = None  # Ah

    # -------------------------------------------------------------------------
    # Additional Temperatures
    # -------------------------------------------------------------------------
    temperature_t1: RegisterField | None = None  # °C
    temperature_t2: RegisterField | None = None  # °C
    temperature_t3: RegisterField | None = None  # °C
    temperature_t4: RegisterField | None = None  # °C
    temperature_t5: RegisterField | None = None  # °C

    # -------------------------------------------------------------------------
    # Inverter Operational
    # -------------------------------------------------------------------------
    inverter_on_time: RegisterField | None = None  # hours (32-bit)
    ac_input_type: RegisterField | None = None  # type code

    # -------------------------------------------------------------------------
    # Parallel Configuration (reg 113)
    # Packed format: bits 0-1 = master/slave, bits 2-3 = phase, bits 8-15 = number
    # -------------------------------------------------------------------------
    parallel_config: RegisterField | None = None  # packed parallel status


@dataclass(frozen=True)
class HoldingRegisterField:
    """Definition of a writable holding register field.

    Extends RegisterField with min/max validation and write support.
    """

    address: int
    bit_width: Literal[16, 32] = 16
    scale_factor: ScaleFactor = ScaleFactor.SCALE_NONE
    signed: bool = False
    min_value: float | None = None  # Minimum allowed value (after scaling)
    max_value: float | None = None  # Maximum allowed value (after scaling)


@dataclass(frozen=True)
class HoldingRegisterMap:
    """Register map for writable inverter parameters (holding registers).

    These are configuration parameters that can be read and written via Modbus.
    Based on poldim's EG4-Inverter-Modbus implementation.

    Source: https://github.com/poldim/EG4-Inverter-Modbus
    """

    # -------------------------------------------------------------------------
    # System Information (read-only holding registers)
    # -------------------------------------------------------------------------
    com_version: HoldingRegisterField | None = None  # reg 9
    controller_version: HoldingRegisterField | None = None  # reg 10

    # -------------------------------------------------------------------------
    # PV Configuration
    # -------------------------------------------------------------------------
    pv_start_voltage: HoldingRegisterField | None = None  # reg 22, 0.1V, 90-500V
    pv_input_model: HoldingRegisterField | None = None  # reg 20, select 0-7

    # -------------------------------------------------------------------------
    # Grid Connection Timing
    # -------------------------------------------------------------------------
    grid_connection_wait_time: HoldingRegisterField | None = None  # reg 23, 30-600s
    reconnection_wait_time: HoldingRegisterField | None = None  # reg 24, 0-900s

    # -------------------------------------------------------------------------
    # Power Percentages
    # -------------------------------------------------------------------------
    charge_power_percent: HoldingRegisterField | None = None  # reg 64, 0-100%
    discharge_power_percent: HoldingRegisterField | None = None  # reg 65, 0-100%
    ac_charge_power_percent: HoldingRegisterField | None = None  # reg 66, 0-100%
    ac_charge_soc_limit: HoldingRegisterField | None = None  # reg 67, 0-100%

    # -------------------------------------------------------------------------
    # Inverter Output Configuration
    # -------------------------------------------------------------------------
    inverter_output_voltage: HoldingRegisterField | None = None  # reg 90, select
    inverter_output_frequency: HoldingRegisterField | None = None  # reg 91, select

    # -------------------------------------------------------------------------
    # Battery Voltage Settings
    # -------------------------------------------------------------------------
    charge_voltage_ref: HoldingRegisterField | None = None  # reg 99, 0.1V, 50-59V
    discharge_cutoff_voltage: HoldingRegisterField | None = None  # reg 100, 0.1V, 40-50V
    float_charge_voltage: HoldingRegisterField | None = None  # reg 144, 0.1V, 50-56V
    equalization_voltage: HoldingRegisterField | None = None  # reg 149, 0.1V, 50-59V
    battery_nominal_voltage: HoldingRegisterField | None = None  # reg 148, 0.1V, 40-59V

    # -------------------------------------------------------------------------
    # Battery Current Settings
    # -------------------------------------------------------------------------
    charge_current: HoldingRegisterField | None = None  # reg 101, 0-140A
    discharge_current: HoldingRegisterField | None = None  # reg 102, 0-140A
    ac_charge_battery_current: HoldingRegisterField | None = None  # reg 168, 0-140A

    # -------------------------------------------------------------------------
    # Battery Capacity & Equalization
    # -------------------------------------------------------------------------
    battery_capacity: HoldingRegisterField | None = None  # reg 147, 0-10000Ah
    equalization_interval: HoldingRegisterField | None = None  # reg 150, 0-365 days
    equalization_time: HoldingRegisterField | None = None  # reg 151, 0-24 hours

    # -------------------------------------------------------------------------
    # SOC Limits
    # -------------------------------------------------------------------------
    eod_soc: HoldingRegisterField | None = None  # reg 105, 10-90%
    soc_low_limit_discharge: HoldingRegisterField | None = None  # reg 125, 0-100%
    battery_low_soc: HoldingRegisterField | None = None  # reg 164, 0-90%
    battery_low_back_soc: HoldingRegisterField | None = None  # reg 165, 20-100%
    battery_low_to_utility_soc: HoldingRegisterField | None = None  # reg 167, 0-100%

    # -------------------------------------------------------------------------
    # AC Charge Settings
    # -------------------------------------------------------------------------
    ac_charge_start_voltage: HoldingRegisterField | None = None  # reg 158, 0.1V
    ac_charge_end_voltage: HoldingRegisterField | None = None  # reg 159, 0.1V
    ac_charge_start_soc: HoldingRegisterField | None = None  # reg 160, 0-90%
    ac_charge_end_soc: HoldingRegisterField | None = None  # reg 161, 20-100%

    # -------------------------------------------------------------------------
    # Battery Low Voltage Settings
    # -------------------------------------------------------------------------
    battery_low_voltage: HoldingRegisterField | None = None  # reg 162, 0.1V
    battery_low_back_voltage: HoldingRegisterField | None = None  # reg 163, 0.1V
    battery_low_to_utility_voltage: HoldingRegisterField | None = None  # reg 166, 0.1V
    ongrid_eod_voltage: HoldingRegisterField | None = None  # reg 169, 0.1V

    # -------------------------------------------------------------------------
    # Power Settings
    # -------------------------------------------------------------------------
    max_backflow_power_percent: HoldingRegisterField | None = None  # reg 103, 0-100%
    ptouser_start_discharge: HoldingRegisterField | None = None  # reg 116, 50-10000W
    voltage_start_derating: HoldingRegisterField | None = None  # reg 118, 0.1V
    power_offset_wct: HoldingRegisterField | None = None  # reg 119, -1000 to 1000W
    max_grid_input_power: HoldingRegisterField | None = None  # reg 176, W

    # -------------------------------------------------------------------------
    # Generator Settings
    # -------------------------------------------------------------------------
    gen_rated_power: HoldingRegisterField | None = None  # reg 177, W
    gen_charge_start_voltage: HoldingRegisterField | None = None  # reg 194, 0.1V
    gen_charge_end_voltage: HoldingRegisterField | None = None  # reg 195, 0.1V
    gen_charge_start_soc: HoldingRegisterField | None = None  # reg 196, 0-90%
    gen_charge_end_soc: HoldingRegisterField | None = None  # reg 197, 20-100%
    max_gen_charge_battery_current: HoldingRegisterField | None = None  # reg 198, 0-60A

    # -------------------------------------------------------------------------
    # System Configuration
    # -------------------------------------------------------------------------
    system_type: HoldingRegisterField | None = None  # reg 112, parallel config
    output_priority: HoldingRegisterField | None = None  # reg 145, select
    line_mode: HoldingRegisterField | None = None  # reg 146, select
    language: HoldingRegisterField | None = None  # reg 16, select


@dataclass(frozen=True)
class EnergyRegisterMap:
    """Register map for inverter energy data extraction.

    Maps energy counters to their register locations. Energy values are
    typically in 0.1 Wh units.

    Key differences between models:
    - PV_SERIES: 32-bit daily values, single-register lifetime
    - LXP_EU: 16-bit daily values (regs 28-37), 32-bit lifetime (regs 40-59)
    """

    # -------------------------------------------------------------------------
    # Daily Energy (typically 32-bit pairs)
    # -------------------------------------------------------------------------
    inverter_energy_today: RegisterField | None = None
    grid_import_today: RegisterField | None = None
    charge_energy_today: RegisterField | None = None
    discharge_energy_today: RegisterField | None = None
    eps_energy_today: RegisterField | None = None
    grid_export_today: RegisterField | None = None
    load_energy_today: RegisterField | None = None

    # Per-PV string daily energy
    pv1_energy_today: RegisterField | None = None
    pv2_energy_today: RegisterField | None = None
    pv3_energy_today: RegisterField | None = None

    # -------------------------------------------------------------------------
    # Lifetime Energy
    # -------------------------------------------------------------------------
    inverter_energy_total: RegisterField | None = None
    grid_import_total: RegisterField | None = None
    charge_energy_total: RegisterField | None = None
    discharge_energy_total: RegisterField | None = None
    eps_energy_total: RegisterField | None = None
    grid_export_total: RegisterField | None = None
    load_energy_total: RegisterField | None = None

    # Per-PV string lifetime energy
    pv1_energy_total: RegisterField | None = None
    pv2_energy_total: RegisterField | None = None
    pv3_energy_total: RegisterField | None = None

    # -------------------------------------------------------------------------
    # Generator Energy (if connected)
    # -------------------------------------------------------------------------
    generator_energy_today: RegisterField | None = None  # kWh (scale 0.1)
    generator_energy_total: RegisterField | None = None  # kWh (32-bit, scale 0.1)


# =============================================================================
# PV SERIES REGISTER MAP (EG4-18KPV / FlexBOSS21)
# =============================================================================
# Source: EG4-18KPV-12LV Modbus Protocol specification
# Source: eg4-modbus-monitor project (https://github.com/galets/eg4-modbus-monitor)
# Source: EG4-Inverter-Modbus project (https://github.com/poldim/EG4-Inverter-Modbus)
#
# CRITICAL: Power values are 16-bit SINGLE registers, NOT 32-bit pairs!
# This was the root cause of "skewed watts" - the old implementation combined
# two adjacent registers incorrectly.
#
# Register layout for EG4-18KPV (validated against galets/poldim):
#   Reg 0:     State (status code)
#   Reg 1-3:   Vpv1/2/3 (V, scale=0.1)
#   Reg 4:     Vbat (V, scale=0.1)
#   Reg 5:     SOC/SOH packed (LSB=SOC%, MSB=SOH%)
#   Reg 7-9:   Ppv1/2/3 (W, 16-bit, no scale)
#   Reg 10:    Pcharge (W, 16-bit)
#   Reg 11:    Pdischarge (W, 16-bit)
#   Reg 12-14: Grid voltages L1-L2, L2-L3, L3-L1 (V, scale=0.1)
#   Reg 15:    Fac - Grid frequency (Hz, scale=0.01)
#   Reg 16:    Pinv - Inverter output power (W, 16-bit)
#   Reg 17:    Prec - AC charge power / Grid power (W, 16-bit)
#   Reg 18:    IinvRMS - Inverter RMS current (A, scale=0.01)
#   Reg 19:    PF - Power factor (scale=0.001)
#   Reg 20-22: Inverter output voltages L1-L2, L2-L3, L3-L1 (V, scale=0.1)
#   Reg 23:    Inverter frequency (Hz, scale=0.01)
#   Reg 24:    Peps - EPS output power (W, 16-bit)
#   Reg 25:    Seps - EPS apparent power (VA, 16-bit)
#   Reg 26:    Ptogrid - Power exported to grid (W, 16-bit)
#   Reg 27:    Ptouser - Load power / Power from grid (W, 16-bit)
#   Reg 38-39: Bus voltages (V, scale=0.1)
#   Reg 60-61: Fault code (32-bit)
#   Reg 62-63: Warning code (32-bit)
#   Reg 64-67: Temperatures (°C, signed)

PV_SERIES_RUNTIME_MAP = RuntimeRegisterMap(
    # Status
    device_status=RegisterField(0, 16, ScaleFactor.SCALE_NONE),
    # PV Input - voltages at regs 1-3, power as 16-bit at regs 7-9
    pv1_voltage=RegisterField(1, 16, ScaleFactor.SCALE_10),
    pv2_voltage=RegisterField(2, 16, ScaleFactor.SCALE_10),
    pv3_voltage=RegisterField(3, 16, ScaleFactor.SCALE_10),
    pv1_power=RegisterField(7, 16, ScaleFactor.SCALE_NONE),  # 16-bit at reg 7
    pv2_power=RegisterField(8, 16, ScaleFactor.SCALE_NONE),  # 16-bit at reg 8
    pv3_power=RegisterField(9, 16, ScaleFactor.SCALE_NONE),  # 16-bit at reg 9
    # Battery - Vbat at reg 4 with scale 0.1
    battery_voltage=RegisterField(4, 16, ScaleFactor.SCALE_10),  # galets: scale=0.1
    battery_current=RegisterField(75, 16, ScaleFactor.SCALE_100, signed=True),  # Reg 75
    soc_soh_packed=RegisterField(5, 16, ScaleFactor.SCALE_NONE),  # SOC=low, SOH=high
    charge_power=RegisterField(10, 16, ScaleFactor.SCALE_NONE),  # 16-bit at reg 10
    discharge_power=RegisterField(11, 16, ScaleFactor.SCALE_NONE),  # 16-bit at reg 11
    # Grid - voltages at regs 12-14, frequency at reg 15
    grid_voltage_r=RegisterField(12, 16, ScaleFactor.SCALE_10),  # L1-L2
    grid_voltage_s=RegisterField(13, 16, ScaleFactor.SCALE_10),  # L2-L3
    grid_voltage_t=RegisterField(14, 16, ScaleFactor.SCALE_10),  # L3-L1
    grid_frequency=RegisterField(15, 16, ScaleFactor.SCALE_100),
    inverter_power=RegisterField(16, 16, ScaleFactor.SCALE_NONE),  # 16-bit at reg 16
    grid_power=RegisterField(17, 16, ScaleFactor.SCALE_NONE),  # AC charge/Prec at reg 17
    power_factor=RegisterField(19, 16, ScaleFactor.SCALE_1000),  # 16-bit at reg 19
    # EPS - voltages at regs 20-22, frequency at reg 23, power at reg 24
    eps_voltage_r=RegisterField(20, 16, ScaleFactor.SCALE_10),  # L1-L2
    eps_voltage_s=RegisterField(21, 16, ScaleFactor.SCALE_10),  # L2-L3
    eps_voltage_t=RegisterField(22, 16, ScaleFactor.SCALE_10),  # L3-L1
    eps_frequency=RegisterField(23, 16, ScaleFactor.SCALE_100),
    eps_power=RegisterField(24, 16, ScaleFactor.SCALE_NONE),  # 16-bit at reg 24
    eps_status=RegisterField(25, 16, ScaleFactor.SCALE_NONE),  # Seps at reg 25
    power_to_grid=RegisterField(26, 16, ScaleFactor.SCALE_NONE),  # Ptogrid at reg 26
    # Load
    load_power=RegisterField(27, 16, ScaleFactor.SCALE_NONE),  # Ptouser at reg 27
    # Internal - bus voltages at regs 38-39
    bus_voltage_1=RegisterField(38, 16, ScaleFactor.SCALE_10),
    bus_voltage_2=RegisterField(39, 16, ScaleFactor.SCALE_10),
    # Temperatures
    internal_temperature=RegisterField(64, 16, ScaleFactor.SCALE_NONE, signed=True),
    radiator_temperature_1=RegisterField(65, 16, ScaleFactor.SCALE_NONE),
    radiator_temperature_2=RegisterField(66, 16, ScaleFactor.SCALE_NONE),
    battery_temperature=RegisterField(67, 16, ScaleFactor.SCALE_NONE),
    # Fault/Warning codes
    inverter_fault_code=RegisterField(60, 32, ScaleFactor.SCALE_NONE),  # Regs 60-61
    inverter_warning_code=RegisterField(62, 32, ScaleFactor.SCALE_NONE),  # Regs 62-63
    bms_fault_code=RegisterField(99, 16, ScaleFactor.SCALE_NONE),
    bms_warning_code=RegisterField(100, 16, ScaleFactor.SCALE_NONE),
    # Extended sensors - Inverter RMS Current
    inverter_rms_current=RegisterField(18, 16, ScaleFactor.SCALE_100),  # 0.01A resolution
    inverter_apparent_power=RegisterField(25, 16, ScaleFactor.SCALE_NONE),  # VA (Seps)
    # Generator input (regs 121-125)
    generator_voltage=RegisterField(121, 16, ScaleFactor.SCALE_10),  # V
    generator_frequency=RegisterField(122, 16, ScaleFactor.SCALE_100),  # Hz
    generator_power=RegisterField(123, 16, ScaleFactor.SCALE_NONE),  # W
    # BMS limits and cell data (regs 81-106)
    # Per Yippy's LuxPower docs: 81-82 use 0.01A scale, 103-104 use 0.1°C scale (signed)
    bms_charge_current_limit=RegisterField(81, 16, ScaleFactor.SCALE_100),  # 0.01A
    bms_discharge_current_limit=RegisterField(82, 16, ScaleFactor.SCALE_100),  # 0.01A
    bms_charge_voltage_ref=RegisterField(83, 16, ScaleFactor.SCALE_10),  # 0.1V
    bms_discharge_cutoff=RegisterField(84, 16, ScaleFactor.SCALE_10),  # 0.1V
    bms_max_cell_voltage=RegisterField(101, 16, ScaleFactor.SCALE_NONE),  # mV (0.001V)
    bms_min_cell_voltage=RegisterField(102, 16, ScaleFactor.SCALE_NONE),  # mV (0.001V)
    bms_max_cell_temperature=RegisterField(103, 16, ScaleFactor.SCALE_10, signed=True),  # 0.1°C
    bms_min_cell_temperature=RegisterField(104, 16, ScaleFactor.SCALE_10, signed=True),  # 0.1°C
    bms_cycle_count=RegisterField(106, 16, ScaleFactor.SCALE_NONE),  # count
    battery_parallel_num=RegisterField(96, 16, ScaleFactor.SCALE_NONE),  # count
    battery_capacity_ah=RegisterField(97, 16, ScaleFactor.SCALE_NONE),  # Ah
    # Additional temperatures (regs 108-112) - 0.1°C scale per Yippy's docs
    temperature_t1=RegisterField(108, 16, ScaleFactor.SCALE_10),  # 0.1°C
    temperature_t2=RegisterField(109, 16, ScaleFactor.SCALE_10),  # 0.1°C
    temperature_t3=RegisterField(110, 16, ScaleFactor.SCALE_10),  # 0.1°C
    temperature_t4=RegisterField(111, 16, ScaleFactor.SCALE_10),  # 0.1°C
    temperature_t5=RegisterField(112, 16, ScaleFactor.SCALE_10),  # 0.1°C
    # Inverter operational
    inverter_on_time=RegisterField(69, 32, ScaleFactor.SCALE_NONE),  # hours (regs 69-70)
    ac_input_type=RegisterField(77, 16, ScaleFactor.SCALE_NONE),  # type code
    # Parallel configuration (reg 113)
    # bits 0-1: master/slave (0=no parallel, 1=master, 2=slave, 3=3-phase master)
    # bits 2-3: phase (0=R, 1=S, 2=T)
    # bits 8-15: parallel number (unit ID in parallel system)
    parallel_config=RegisterField(113, 16, ScaleFactor.SCALE_NONE),
)

PV_SERIES_ENERGY_MAP = EnergyRegisterMap(
    # Daily energy - 16-bit single registers, scale 0.1 kWh
    # Source: galets/eg4-modbus-monitor registers-18kpv.yaml
    pv1_energy_today=RegisterField(28, 16, ScaleFactor.SCALE_10),  # Epv1_day
    pv2_energy_today=RegisterField(29, 16, ScaleFactor.SCALE_10),  # Epv2_day
    pv3_energy_today=RegisterField(30, 16, ScaleFactor.SCALE_10),  # Epv3_day
    inverter_energy_today=RegisterField(31, 16, ScaleFactor.SCALE_10),  # Einv_day
    # NOTE: Swapped grid_import and load_energy to match HTTP API naming convention.
    # HTTP API 'todayImport' = Modbus 'Etouser' (reg 37), not 'Erec' (reg 32).
    # This ensures Modbus sensors show same values as HTTP API sensors.
    grid_import_today=RegisterField(37, 16, ScaleFactor.SCALE_10),  # Etouser_day (HTTP todayImport)
    charge_energy_today=RegisterField(33, 16, ScaleFactor.SCALE_10),  # Echg_day
    discharge_energy_today=RegisterField(34, 16, ScaleFactor.SCALE_10),  # Edischg_day
    eps_energy_today=RegisterField(35, 16, ScaleFactor.SCALE_10),  # Eeps_day
    grid_export_today=RegisterField(36, 16, ScaleFactor.SCALE_10),  # Etogrid_day
    load_energy_today=RegisterField(32, 16, ScaleFactor.SCALE_10),  # Erec_day - AC charge from grid
    # Lifetime energy - 16-bit single registers, scale 0.1 kWh
    # NOTE: galets/eg4-modbus-monitor claims 32-bit pairs, but empirical testing shows
    # these are 16-bit registers. The "odd" registers (41, 43, etc.) are always 0,
    # and the "even" registers (40, 42, etc.) match HTTP API values exactly.
    # Max value: 65535 * 0.1 = 6553.5 kWh per register.
    pv1_energy_total=RegisterField(40, 16, ScaleFactor.SCALE_10),  # Epv1_all
    pv2_energy_total=RegisterField(42, 16, ScaleFactor.SCALE_10),  # Epv2_all
    pv3_energy_total=RegisterField(44, 16, ScaleFactor.SCALE_10),  # Epv3_all
    inverter_energy_total=RegisterField(46, 16, ScaleFactor.SCALE_10),  # Einv_all
    # Swapped to match HTTP API (see daily energy note above)
    grid_import_total=RegisterField(58, 16, ScaleFactor.SCALE_10),  # Etouser_all (HTTP totalImport)
    charge_energy_total=RegisterField(50, 16, ScaleFactor.SCALE_10),  # Echg_all
    discharge_energy_total=RegisterField(52, 16, ScaleFactor.SCALE_10),  # Edischg_all
    eps_energy_total=RegisterField(54, 16, ScaleFactor.SCALE_10),  # Eeps_all
    grid_export_total=RegisterField(56, 16, ScaleFactor.SCALE_10),  # Etogrid_all
    load_energy_total=RegisterField(48, 16, ScaleFactor.SCALE_10),  # Erec_all - AC charge from grid
    # Generator energy
    generator_energy_today=RegisterField(124, 16, ScaleFactor.SCALE_10),  # kWh
    generator_energy_total=RegisterField(125, 16, ScaleFactor.SCALE_10),  # kWh
)


# =============================================================================
# LXP-EU REGISTER MAP (LXP-EU 12K)
# =============================================================================
# Source: Yippy's LXP-EU 12K corrections from issue #52
# Key differences: 16-bit power values, 4-register offset for grid/EPS

LXP_EU_RUNTIME_MAP = RuntimeRegisterMap(
    # Status
    device_status=RegisterField(0, 16, ScaleFactor.SCALE_NONE),
    # PV Input - voltages same, but power is 16-bit (not 32-bit)
    pv1_voltage=RegisterField(1, 16, ScaleFactor.SCALE_10),
    pv2_voltage=RegisterField(2, 16, ScaleFactor.SCALE_10),
    pv3_voltage=RegisterField(3, 16, ScaleFactor.SCALE_10),
    pv1_power=RegisterField(7, 16, ScaleFactor.SCALE_NONE),  # 16-bit at reg 7
    pv2_power=RegisterField(8, 16, ScaleFactor.SCALE_NONE),  # 16-bit at reg 8
    pv3_power=RegisterField(9, 16, ScaleFactor.SCALE_NONE),  # 16-bit at reg 9
    # Battery - 0.1V scale per luxpower-ha-integration (I_VBAT)
    battery_voltage=RegisterField(4, 16, ScaleFactor.SCALE_10),
    battery_current=RegisterField(75, 16, ScaleFactor.SCALE_100, signed=True),  # Same as PV_SERIES
    soc_soh_packed=RegisterField(5, 16, ScaleFactor.SCALE_NONE),
    charge_power=RegisterField(10, 16, ScaleFactor.SCALE_NONE),  # 16-bit at reg 10
    discharge_power=RegisterField(11, 16, ScaleFactor.SCALE_NONE),  # 16-bit at reg 11
    # Grid - 4 register offset from PV_SERIES
    grid_voltage_r=RegisterField(12, 16, ScaleFactor.SCALE_10),  # Was reg 16
    grid_voltage_s=RegisterField(13, 16, ScaleFactor.SCALE_10),  # Was reg 17
    grid_voltage_t=RegisterField(14, 16, ScaleFactor.SCALE_10),  # Was reg 18
    grid_frequency=RegisterField(15, 16, ScaleFactor.SCALE_100),  # Was reg 19
    inverter_power=RegisterField(16, 16, ScaleFactor.SCALE_NONE),  # 16-bit at reg 16
    grid_power=RegisterField(17, 16, ScaleFactor.SCALE_NONE),  # 16-bit at reg 17
    power_factor=RegisterField(18, 16, ScaleFactor.SCALE_1000),  # 16-bit at reg 18
    # EPS - offset continues
    eps_voltage_r=RegisterField(20, 16, ScaleFactor.SCALE_10),  # Was reg 26
    eps_voltage_s=RegisterField(21, 16, ScaleFactor.SCALE_10),  # Was reg 27
    eps_voltage_t=RegisterField(22, 16, ScaleFactor.SCALE_10),  # Was reg 28
    eps_frequency=RegisterField(23, 16, ScaleFactor.SCALE_100),  # Was reg 29
    eps_power=RegisterField(24, 16, ScaleFactor.SCALE_NONE),  # 16-bit at reg 24
    eps_status=RegisterField(25, 16, ScaleFactor.SCALE_NONE),
    power_to_grid=RegisterField(26, 16, ScaleFactor.SCALE_NONE),
    # Load
    load_power=RegisterField(27, 16, ScaleFactor.SCALE_NONE),  # 16-bit at reg 27
    # Internal - different locations
    bus_voltage_1=RegisterField(38, 16, ScaleFactor.SCALE_10),  # Was reg 43
    bus_voltage_2=RegisterField(39, 16, ScaleFactor.SCALE_10),  # Was reg 44
    # Temperatures - same as PV_SERIES
    internal_temperature=RegisterField(64, 16, ScaleFactor.SCALE_NONE, signed=True),
    radiator_temperature_1=RegisterField(65, 16, ScaleFactor.SCALE_NONE),
    radiator_temperature_2=RegisterField(66, 16, ScaleFactor.SCALE_NONE),
    battery_temperature=RegisterField(67, 16, ScaleFactor.SCALE_NONE),
    # Fault/Warning codes - 32-bit little-endian (L/H word pairs)
    inverter_fault_code=RegisterField(60, 32, ScaleFactor.SCALE_NONE, little_endian=True),
    inverter_warning_code=RegisterField(62, 32, ScaleFactor.SCALE_NONE, little_endian=True),
    bms_fault_code=RegisterField(99, 16, ScaleFactor.SCALE_NONE),
    bms_warning_code=RegisterField(100, 16, ScaleFactor.SCALE_NONE),
    # Extended sensors - same as PV_SERIES
    inverter_rms_current=RegisterField(18, 16, ScaleFactor.SCALE_100),
    inverter_apparent_power=RegisterField(25, 16, ScaleFactor.SCALE_NONE),
    generator_voltage=RegisterField(121, 16, ScaleFactor.SCALE_10),
    generator_frequency=RegisterField(122, 16, ScaleFactor.SCALE_100),
    generator_power=RegisterField(123, 16, ScaleFactor.SCALE_NONE),
    bms_charge_current_limit=RegisterField(81, 16, ScaleFactor.SCALE_100),  # 0.01A
    bms_discharge_current_limit=RegisterField(82, 16, ScaleFactor.SCALE_100),  # 0.01A
    bms_charge_voltage_ref=RegisterField(83, 16, ScaleFactor.SCALE_10),  # 0.1V
    bms_discharge_cutoff=RegisterField(84, 16, ScaleFactor.SCALE_10),  # 0.1V
    bms_max_cell_voltage=RegisterField(101, 16, ScaleFactor.SCALE_NONE),  # mV
    bms_min_cell_voltage=RegisterField(102, 16, ScaleFactor.SCALE_NONE),  # mV
    bms_max_cell_temperature=RegisterField(103, 16, ScaleFactor.SCALE_10, signed=True),  # 0.1°C
    bms_min_cell_temperature=RegisterField(104, 16, ScaleFactor.SCALE_10, signed=True),  # 0.1°C
    bms_cycle_count=RegisterField(106, 16, ScaleFactor.SCALE_NONE),
    battery_parallel_num=RegisterField(96, 16, ScaleFactor.SCALE_NONE),
    battery_capacity_ah=RegisterField(97, 16, ScaleFactor.SCALE_NONE),
    temperature_t1=RegisterField(108, 16, ScaleFactor.SCALE_10),  # 0.1°C
    temperature_t2=RegisterField(109, 16, ScaleFactor.SCALE_10),  # 0.1°C
    temperature_t3=RegisterField(110, 16, ScaleFactor.SCALE_10),  # 0.1°C
    temperature_t4=RegisterField(111, 16, ScaleFactor.SCALE_10),  # 0.1°C
    temperature_t5=RegisterField(112, 16, ScaleFactor.SCALE_10),  # 0.1°C
    inverter_on_time=RegisterField(69, 32, ScaleFactor.SCALE_NONE, little_endian=True),
    ac_input_type=RegisterField(77, 16, ScaleFactor.SCALE_NONE),
    parallel_config=RegisterField(113, 16, ScaleFactor.SCALE_NONE),
)

LXP_EU_ENERGY_MAP = EnergyRegisterMap(
    # Daily energy - same as PV_SERIES per luxpower-ha-integration
    # Source: https://github.com/ant0nkr/luxpower-ha-integration/blob/main/custom_components/lxp_modbus/constants/input_registers.py
    pv1_energy_today=RegisterField(28, 16, ScaleFactor.SCALE_10),  # I_EPV1_DAY
    pv2_energy_today=RegisterField(29, 16, ScaleFactor.SCALE_10),  # I_EPV2_DAY
    pv3_energy_today=RegisterField(30, 16, ScaleFactor.SCALE_10),  # I_EPV3_DAY
    inverter_energy_today=RegisterField(31, 16, ScaleFactor.SCALE_10),  # I_EINV_DAY
    # NOTE: Swapped grid_import and load_energy to match HTTP API naming convention.
    # HTTP API 'todayImport' = Modbus 'Etouser' (reg 37), not 'Erec' (reg 32).
    grid_import_today=RegisterField(37, 16, ScaleFactor.SCALE_10),  # I_ETOUSER_DAY
    charge_energy_today=RegisterField(33, 16, ScaleFactor.SCALE_10),  # I_ECHG_DAY
    discharge_energy_today=RegisterField(34, 16, ScaleFactor.SCALE_10),  # I_EDISCHG_DAY
    eps_energy_today=RegisterField(35, 16, ScaleFactor.SCALE_10),  # I_EEPS_DAY
    grid_export_today=RegisterField(36, 16, ScaleFactor.SCALE_10),  # I_ETOGRID_DAY
    load_energy_today=RegisterField(32, 16, ScaleFactor.SCALE_10),  # I_EREC_DAY (AC charge)
    # Lifetime energy - 32-bit pairs per luxpower-ha-integration
    # NOTE: LuxPower uses little-endian word order (Low word at base address)
    # The _L/_H suffix in luxpower-ha-integration indicates: _L=Low word, _H=High word
    pv1_energy_total=RegisterField(40, 32, ScaleFactor.SCALE_10, little_endian=True),
    pv2_energy_total=RegisterField(42, 32, ScaleFactor.SCALE_10, little_endian=True),
    pv3_energy_total=RegisterField(44, 32, ScaleFactor.SCALE_10, little_endian=True),
    inverter_energy_total=RegisterField(46, 32, ScaleFactor.SCALE_10, little_endian=True),
    # Swapped to match HTTP API (see daily energy note above)
    grid_import_total=RegisterField(58, 32, ScaleFactor.SCALE_10, little_endian=True),
    charge_energy_total=RegisterField(50, 32, ScaleFactor.SCALE_10, little_endian=True),
    discharge_energy_total=RegisterField(52, 32, ScaleFactor.SCALE_10, little_endian=True),
    eps_energy_total=RegisterField(54, 32, ScaleFactor.SCALE_10, little_endian=True),
    grid_export_total=RegisterField(56, 32, ScaleFactor.SCALE_10, little_endian=True),
    load_energy_total=RegisterField(48, 32, ScaleFactor.SCALE_10, little_endian=True),
    # Generator energy
    generator_energy_today=RegisterField(124, 16, ScaleFactor.SCALE_10),  # I_EGEN_DAY
    generator_energy_total=RegisterField(125, 32, ScaleFactor.SCALE_10, little_endian=True),
)


# =============================================================================
# PV SERIES HOLDING REGISTER MAP (Writable Parameters)
# =============================================================================
# Source: poldim's EG4-Inverter-Modbus and EG4-18KPV-12LV Modbus Protocol
# https://github.com/poldim/EG4-Inverter-Modbus

PV_SERIES_HOLDING_MAP = HoldingRegisterMap(
    # System Information (read-only)
    com_version=HoldingRegisterField(9, 16, ScaleFactor.SCALE_NONE),
    controller_version=HoldingRegisterField(10, 16, ScaleFactor.SCALE_NONE),
    # PV Configuration
    pv_start_voltage=HoldingRegisterField(
        22, 16, ScaleFactor.SCALE_10, min_value=90.0, max_value=500.0
    ),
    pv_input_model=HoldingRegisterField(20, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=7),
    # Grid Connection Timing
    grid_connection_wait_time=HoldingRegisterField(
        23, 16, ScaleFactor.SCALE_NONE, min_value=30, max_value=600
    ),
    reconnection_wait_time=HoldingRegisterField(
        24, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=900
    ),
    # Power Percentages
    charge_power_percent=HoldingRegisterField(
        64, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=100
    ),
    discharge_power_percent=HoldingRegisterField(
        65, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=100
    ),
    ac_charge_power_percent=HoldingRegisterField(
        66, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=100
    ),
    ac_charge_soc_limit=HoldingRegisterField(
        67, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=100
    ),
    # Inverter Output Configuration
    inverter_output_voltage=HoldingRegisterField(
        90, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=3
    ),  # 0=230, 1=240, 2=277, 3=208
    inverter_output_frequency=HoldingRegisterField(
        91, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=1
    ),  # 0=50Hz, 1=60Hz
    # Battery Voltage Settings
    charge_voltage_ref=HoldingRegisterField(
        99, 16, ScaleFactor.SCALE_10, min_value=50.0, max_value=59.0
    ),
    discharge_cutoff_voltage=HoldingRegisterField(
        100, 16, ScaleFactor.SCALE_10, min_value=40.0, max_value=50.0
    ),
    float_charge_voltage=HoldingRegisterField(
        144, 16, ScaleFactor.SCALE_10, min_value=50.0, max_value=56.0
    ),
    equalization_voltage=HoldingRegisterField(
        149, 16, ScaleFactor.SCALE_10, min_value=50.0, max_value=59.0
    ),
    battery_nominal_voltage=HoldingRegisterField(
        148, 16, ScaleFactor.SCALE_10, min_value=40.0, max_value=59.0
    ),
    # Battery Current Settings
    charge_current=HoldingRegisterField(
        101, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=140
    ),
    discharge_current=HoldingRegisterField(
        102, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=140
    ),
    ac_charge_battery_current=HoldingRegisterField(
        168, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=140
    ),
    # Battery Capacity & Equalization
    battery_capacity=HoldingRegisterField(
        147, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=10000
    ),
    equalization_interval=HoldingRegisterField(
        150, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=365
    ),
    equalization_time=HoldingRegisterField(
        151, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=24
    ),
    # SOC Limits
    eod_soc=HoldingRegisterField(105, 16, ScaleFactor.SCALE_NONE, min_value=10, max_value=90),
    soc_low_limit_discharge=HoldingRegisterField(
        125, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=100
    ),
    battery_low_soc=HoldingRegisterField(
        164, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=90
    ),
    battery_low_back_soc=HoldingRegisterField(
        165, 16, ScaleFactor.SCALE_NONE, min_value=20, max_value=100
    ),
    battery_low_to_utility_soc=HoldingRegisterField(
        167, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=100
    ),
    # AC Charge Settings
    ac_charge_start_voltage=HoldingRegisterField(
        158, 16, ScaleFactor.SCALE_10, min_value=38.4, max_value=52.0
    ),
    ac_charge_end_voltage=HoldingRegisterField(
        159, 16, ScaleFactor.SCALE_10, min_value=48.0, max_value=59.0
    ),
    ac_charge_start_soc=HoldingRegisterField(
        160, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=90
    ),
    ac_charge_end_soc=HoldingRegisterField(
        161, 16, ScaleFactor.SCALE_NONE, min_value=20, max_value=100
    ),
    # Battery Low Voltage Settings
    battery_low_voltage=HoldingRegisterField(
        162, 16, ScaleFactor.SCALE_10, min_value=40.0, max_value=50.0
    ),
    battery_low_back_voltage=HoldingRegisterField(
        163, 16, ScaleFactor.SCALE_10, min_value=42.0, max_value=52.0
    ),
    battery_low_to_utility_voltage=HoldingRegisterField(
        166, 16, ScaleFactor.SCALE_10, min_value=44.4, max_value=51.4
    ),
    ongrid_eod_voltage=HoldingRegisterField(
        169, 16, ScaleFactor.SCALE_10, min_value=40.0, max_value=56.0
    ),
    # Power Settings
    max_backflow_power_percent=HoldingRegisterField(
        103, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=100
    ),
    ptouser_start_discharge=HoldingRegisterField(
        116, 16, ScaleFactor.SCALE_NONE, min_value=50, max_value=10000
    ),
    voltage_start_derating=HoldingRegisterField(118, 16, ScaleFactor.SCALE_10),
    power_offset_wct=HoldingRegisterField(
        119, 16, ScaleFactor.SCALE_NONE, signed=True, min_value=-1000, max_value=1000
    ),
    max_grid_input_power=HoldingRegisterField(176, 16, ScaleFactor.SCALE_NONE),
    # Generator Settings
    gen_rated_power=HoldingRegisterField(177, 16, ScaleFactor.SCALE_NONE),
    gen_charge_start_voltage=HoldingRegisterField(
        194, 16, ScaleFactor.SCALE_10, min_value=38.4, max_value=52.0
    ),
    gen_charge_end_voltage=HoldingRegisterField(
        195, 16, ScaleFactor.SCALE_10, min_value=48.0, max_value=59.0
    ),
    gen_charge_start_soc=HoldingRegisterField(
        196, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=90
    ),
    gen_charge_end_soc=HoldingRegisterField(
        197, 16, ScaleFactor.SCALE_NONE, min_value=20, max_value=100
    ),
    max_gen_charge_battery_current=HoldingRegisterField(
        198, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=60
    ),
    # System Configuration
    system_type=HoldingRegisterField(
        112, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=3
    ),  # 0=No Parallel, 1=Master, 2=Slave, 3=3-Phase Master
    output_priority=HoldingRegisterField(
        145, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=2
    ),  # 0=Battery, 1=PV, 2=AC
    line_mode=HoldingRegisterField(
        146, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=2
    ),  # 0=APL, 1=UPS, 2=GEN
    language=HoldingRegisterField(
        16, 16, ScaleFactor.SCALE_NONE, min_value=0, max_value=1
    ),  # 0=English, 1=German
)

# LXP_EU uses same holding register layout as PV_SERIES
LXP_EU_HOLDING_MAP = PV_SERIES_HOLDING_MAP


# =============================================================================
# FAMILY TO REGISTER MAP LOOKUP
# =============================================================================


# Import here to avoid circular import at module load time
def _get_family_runtime_maps() -> dict[InverterFamily, RuntimeRegisterMap]:
    """Get mapping from InverterFamily to RuntimeRegisterMap.

    This is a function to avoid circular imports at module load time.
    """
    from pylxpweb.devices.inverters._features import InverterFamily

    return {
        InverterFamily.PV_SERIES: PV_SERIES_RUNTIME_MAP,
        InverterFamily.LXP_EU: LXP_EU_RUNTIME_MAP,
        # SNA uses same layout as PV_SERIES (US market)
        InverterFamily.SNA: PV_SERIES_RUNTIME_MAP,
        # LXP_LV uses same layout as LXP_EU (similar architecture)
        InverterFamily.LXP_LV: LXP_EU_RUNTIME_MAP,
        # Unknown defaults to PV_SERIES (backward compatible)
        InverterFamily.UNKNOWN: PV_SERIES_RUNTIME_MAP,
    }


def _get_family_energy_maps() -> dict[InverterFamily, EnergyRegisterMap]:
    """Get mapping from InverterFamily to EnergyRegisterMap."""
    from pylxpweb.devices.inverters._features import InverterFamily

    return {
        InverterFamily.PV_SERIES: PV_SERIES_ENERGY_MAP,
        InverterFamily.LXP_EU: LXP_EU_ENERGY_MAP,
        InverterFamily.SNA: PV_SERIES_ENERGY_MAP,
        InverterFamily.LXP_LV: LXP_EU_ENERGY_MAP,
        InverterFamily.UNKNOWN: PV_SERIES_ENERGY_MAP,
    }


def get_runtime_map(family: InverterFamily | None = None) -> RuntimeRegisterMap:
    """Get the runtime register map for an inverter family.

    Args:
        family: InverterFamily enum value, or None for default (PV_SERIES)

    Returns:
        RuntimeRegisterMap for the specified family
    """
    if family is None:
        return PV_SERIES_RUNTIME_MAP

    family_maps = _get_family_runtime_maps()
    return family_maps.get(family, PV_SERIES_RUNTIME_MAP)


def get_energy_map(family: InverterFamily | None = None) -> EnergyRegisterMap:
    """Get the energy register map for an inverter family.

    Args:
        family: InverterFamily enum value, or None for default (PV_SERIES)

    Returns:
        EnergyRegisterMap for the specified family
    """
    if family is None:
        return PV_SERIES_ENERGY_MAP

    family_maps = _get_family_energy_maps()
    return family_maps.get(family, PV_SERIES_ENERGY_MAP)


def _get_family_holding_maps() -> dict[InverterFamily, HoldingRegisterMap]:
    """Get mapping from InverterFamily to HoldingRegisterMap."""
    from pylxpweb.devices.inverters._features import InverterFamily

    return {
        InverterFamily.PV_SERIES: PV_SERIES_HOLDING_MAP,
        InverterFamily.LXP_EU: LXP_EU_HOLDING_MAP,
        InverterFamily.SNA: PV_SERIES_HOLDING_MAP,
        InverterFamily.LXP_LV: LXP_EU_HOLDING_MAP,
        InverterFamily.UNKNOWN: PV_SERIES_HOLDING_MAP,
    }


def get_holding_map(family: InverterFamily | None = None) -> HoldingRegisterMap:
    """Get the holding (writable) register map for an inverter family.

    Args:
        family: InverterFamily enum value, or None for default (PV_SERIES)

    Returns:
        HoldingRegisterMap for the specified family
    """
    if family is None:
        return PV_SERIES_HOLDING_MAP

    family_maps = _get_family_holding_maps()
    return family_maps.get(family, PV_SERIES_HOLDING_MAP)


__all__ = [
    "RegisterField",
    "HoldingRegisterField",
    "RuntimeRegisterMap",
    "EnergyRegisterMap",
    "PV_SERIES_RUNTIME_MAP",
    "PV_SERIES_ENERGY_MAP",
    "LXP_EU_RUNTIME_MAP",
    "LXP_EU_ENERGY_MAP",
    "HoldingRegisterMap",
    "PV_SERIES_HOLDING_MAP",
    "LXP_EU_HOLDING_MAP",
    "get_runtime_map",
    "get_energy_map",
    "get_holding_map",
]
