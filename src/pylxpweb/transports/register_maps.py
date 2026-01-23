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

    For 32-bit values, the address is the high word and address+1 is the low word.

    Example:
        # 16-bit voltage at register 16, scale by /10
        grid_voltage = RegisterField(16, 16, ScaleFactor.SCALE_10)

        # 32-bit power at registers 6-7, no scaling
        pv1_power = RegisterField(6, 32, ScaleFactor.SCALE_NONE)
    """

    address: int
    bit_width: Literal[16, 32] = 16
    scale_factor: ScaleFactor = ScaleFactor.SCALE_NONE
    signed: bool = False


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


# =============================================================================
# PV SERIES REGISTER MAP (EG4-18KPV)
# =============================================================================
# Source: EG4-18KPV-12LV Modbus Protocol specification
# Source: eg4-modbus-monitor project (https://github.com/galets/eg4-modbus-monitor)

PV_SERIES_RUNTIME_MAP = RuntimeRegisterMap(
    # Status
    device_status=RegisterField(0, 16, ScaleFactor.SCALE_NONE),
    # PV Input - voltages at regs 1-3, power as 32-bit pairs at regs 6-11
    pv1_voltage=RegisterField(1, 16, ScaleFactor.SCALE_10),
    pv2_voltage=RegisterField(2, 16, ScaleFactor.SCALE_10),
    pv3_voltage=RegisterField(3, 16, ScaleFactor.SCALE_10),
    pv1_power=RegisterField(6, 32, ScaleFactor.SCALE_NONE),  # Regs 6-7
    pv2_power=RegisterField(8, 32, ScaleFactor.SCALE_NONE),  # Regs 8-9
    pv3_power=RegisterField(10, 32, ScaleFactor.SCALE_NONE),  # Regs 10-11
    # Battery
    battery_voltage=RegisterField(4, 16, ScaleFactor.SCALE_100),
    battery_current=RegisterField(75, 16, ScaleFactor.SCALE_100, signed=True),  # Reg 75
    soc_soh_packed=RegisterField(5, 16, ScaleFactor.SCALE_NONE),  # SOC=low, SOH=high
    charge_power=RegisterField(12, 32, ScaleFactor.SCALE_NONE),  # Regs 12-13
    discharge_power=RegisterField(14, 32, ScaleFactor.SCALE_NONE),  # Regs 14-15
    # Grid
    grid_voltage_r=RegisterField(16, 16, ScaleFactor.SCALE_10),
    grid_voltage_s=RegisterField(17, 16, ScaleFactor.SCALE_10),
    grid_voltage_t=RegisterField(18, 16, ScaleFactor.SCALE_10),
    grid_frequency=RegisterField(19, 16, ScaleFactor.SCALE_100),
    inverter_power=RegisterField(20, 32, ScaleFactor.SCALE_NONE),  # Regs 20-21
    grid_power=RegisterField(22, 32, ScaleFactor.SCALE_NONE),  # Regs 22-23
    power_factor=RegisterField(24, 32, ScaleFactor.SCALE_1000),  # Regs 24-25
    # EPS
    eps_voltage_r=RegisterField(26, 16, ScaleFactor.SCALE_10),
    eps_voltage_s=RegisterField(27, 16, ScaleFactor.SCALE_10),
    eps_voltage_t=RegisterField(28, 16, ScaleFactor.SCALE_10),
    eps_frequency=RegisterField(29, 16, ScaleFactor.SCALE_100),
    eps_power=RegisterField(30, 32, ScaleFactor.SCALE_NONE),  # Regs 30-31
    eps_status=RegisterField(32, 16, ScaleFactor.SCALE_NONE),
    power_to_grid=RegisterField(33, 16, ScaleFactor.SCALE_NONE),
    # Load
    load_power=RegisterField(34, 32, ScaleFactor.SCALE_NONE),  # Regs 34-35
    # Internal
    bus_voltage_1=RegisterField(43, 16, ScaleFactor.SCALE_10),
    bus_voltage_2=RegisterField(44, 16, ScaleFactor.SCALE_10),
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
)

PV_SERIES_ENERGY_MAP = EnergyRegisterMap(
    # Daily energy - 32-bit pairs
    inverter_energy_today=RegisterField(45, 32, ScaleFactor.SCALE_10),  # Regs 45-46
    grid_import_today=RegisterField(47, 32, ScaleFactor.SCALE_10),  # Regs 47-48
    charge_energy_today=RegisterField(49, 32, ScaleFactor.SCALE_10),  # Regs 49-50
    discharge_energy_today=RegisterField(51, 32, ScaleFactor.SCALE_10),  # Regs 51-52
    eps_energy_today=RegisterField(53, 32, ScaleFactor.SCALE_10),  # Regs 53-54
    grid_export_today=RegisterField(55, 32, ScaleFactor.SCALE_10),  # Regs 55-56
    load_energy_today=RegisterField(57, 32, ScaleFactor.SCALE_10),  # Regs 57-58
    # Per-PV string energy not available via Modbus (regs 91-102 are BMS data)
    pv1_energy_today=None,
    pv2_energy_today=None,
    pv3_energy_today=None,
    # Lifetime energy - single registers (value * 1000 for Wh)
    # Note: These are in kWh, need special handling
    inverter_energy_total=RegisterField(36, 16, ScaleFactor.SCALE_NONE),
    grid_import_total=RegisterField(37, 16, ScaleFactor.SCALE_NONE),
    charge_energy_total=RegisterField(38, 16, ScaleFactor.SCALE_NONE),
    discharge_energy_total=RegisterField(39, 16, ScaleFactor.SCALE_NONE),
    eps_energy_total=RegisterField(40, 16, ScaleFactor.SCALE_NONE),
    grid_export_total=RegisterField(41, 16, ScaleFactor.SCALE_NONE),
    load_energy_total=RegisterField(42, 16, ScaleFactor.SCALE_NONE),
    # Per-PV string lifetime energy not available via Modbus (regs 91-96 are BMS status)
    pv1_energy_total=None,
    pv2_energy_total=None,
    pv3_energy_total=None,
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
    # Battery
    battery_voltage=RegisterField(4, 16, ScaleFactor.SCALE_100),
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
    # Fault/Warning codes - same as PV_SERIES
    inverter_fault_code=RegisterField(60, 32, ScaleFactor.SCALE_NONE),
    inverter_warning_code=RegisterField(62, 32, ScaleFactor.SCALE_NONE),
    bms_fault_code=RegisterField(99, 16, ScaleFactor.SCALE_NONE),
    bms_warning_code=RegisterField(100, 16, ScaleFactor.SCALE_NONE),
)

LXP_EU_ENERGY_MAP = EnergyRegisterMap(
    # Daily energy - 16-bit singles (regs 28-37 per LXP-EU spec)
    inverter_energy_today=RegisterField(28, 16, ScaleFactor.SCALE_10),
    grid_import_today=RegisterField(29, 16, ScaleFactor.SCALE_10),
    charge_energy_today=RegisterField(30, 16, ScaleFactor.SCALE_10),
    discharge_energy_today=RegisterField(31, 16, ScaleFactor.SCALE_10),
    eps_energy_today=RegisterField(32, 16, ScaleFactor.SCALE_10),
    grid_export_today=RegisterField(33, 16, ScaleFactor.SCALE_10),
    load_energy_today=RegisterField(34, 16, ScaleFactor.SCALE_10),
    # Per-PV string daily energy not available in same locations
    pv1_energy_today=None,
    pv2_energy_today=None,
    pv3_energy_today=None,
    # Lifetime energy - 32-bit pairs (regs 40-59 per LXP-EU spec)
    inverter_energy_total=RegisterField(40, 32, ScaleFactor.SCALE_10),  # Regs 40-41
    grid_import_total=RegisterField(42, 32, ScaleFactor.SCALE_10),  # Regs 42-43
    charge_energy_total=RegisterField(44, 32, ScaleFactor.SCALE_10),  # Regs 44-45
    discharge_energy_total=RegisterField(46, 32, ScaleFactor.SCALE_10),  # Regs 46-47
    eps_energy_total=RegisterField(48, 32, ScaleFactor.SCALE_10),  # Regs 48-49
    grid_export_total=RegisterField(50, 32, ScaleFactor.SCALE_10),  # Regs 50-51
    load_energy_total=RegisterField(52, 32, ScaleFactor.SCALE_10),  # Regs 52-53
    # Per-PV string lifetime energy not available
    pv1_energy_total=None,
    pv2_energy_total=None,
    pv3_energy_total=None,
)


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


__all__ = [
    "RegisterField",
    "RuntimeRegisterMap",
    "EnergyRegisterMap",
    "PV_SERIES_RUNTIME_MAP",
    "PV_SERIES_ENERGY_MAP",
    "LXP_EU_RUNTIME_MAP",
    "LXP_EU_ENERGY_MAP",
    "get_runtime_map",
    "get_energy_map",
]
