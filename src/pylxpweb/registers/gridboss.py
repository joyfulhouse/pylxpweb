"""Canonical register map for GridBOSS / MID (Microgrid Interconnect Device).

Source: eg4-modbus-monitor registers-gridboss.yaml.
Cross-validated against Web API getMidboxRuntime endpoint.

GridBOSS devices (device type code 50) manage grid interconnection, UPS output,
smart load ports (4), and AC coupling. All registers are INPUT registers
(function code 0x04, read-only).

Register space layout:
    1-9      Voltage (V, raw ÷10)
    10-17    Current (A, raw ÷10)
    18-25    Unused / unknown
    26-33    Power (W, signed, no scaling)
    34-41    Smart load power (W, signed, no scaling)
    42-49    Daily energy: load, UPS, grid export/import (kWh, raw ÷10)
    50-51    Unused / unknown
    52-59    Daily energy: smart load ports 1-4 (kWh, raw ÷10)
    60-67    Daily energy: AC couple ports 1-4 (kWh, raw ÷10)
    68-87    Lifetime energy 32-bit: load, UPS, grid export/import (kWh, raw ÷10)
    88-103   Lifetime energy 32-bit: smart load ports 1-4 (kWh, raw ÷10)
    104-118  AC couple lifetime energy 32-bit (kWh, raw ÷10)
    105-108  Smart port status (overlaps energy — read in separate operation)
    128-130  Frequency (Hz, raw ÷100)

Important: Registers 105-108 serve dual purpose depending on read context:
  - In the RUNTIME read group: smart port status (0=off, 1=smart_load, 2=ac_couple)
  - In the ENERGY read group: high words of AC couple lifetime energy 32-bit values
These are read in separate Modbus operations so there is no conflict in practice.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pylxpweb.registers.inverter_input import ScaleFactor

# =============================================================================
# CATEGORY ENUM
# =============================================================================


class GridBossCategory(StrEnum):
    """Category for GridBOSS/MID device registers."""

    VOLTAGE = "voltage"
    """Grid, UPS, and generator voltage sensors."""

    CURRENT = "current"
    """Per-phase current sensors."""

    POWER = "power"
    """Per-phase active power (grid, load, UPS, generator)."""

    SMART_LOAD = "smart_load"
    """Smart load port power (also shows AC couple when port status=2)."""

    SMART_PORT = "smart_port"
    """Smart port configuration status registers."""

    FREQUENCY = "frequency"
    """Grid, generator, and phase-lock frequency sensors."""

    ENERGY_DAILY = "energy_daily"
    """Daily accumulated energy (resets at midnight)."""

    ENERGY_LIFETIME = "energy_lifetime"
    """Lifetime accumulated energy (32-bit, never resets)."""


# =============================================================================
# REGISTER DEFINITION
# =============================================================================


@dataclass(frozen=True)
class GridBossRegisterDefinition:
    """Single register definition for a GridBOSS/MID device.

    All registers are INPUT registers (Modbus function code 0x04).
    The ``address`` field is an absolute register address.
    """

    address: int
    """Absolute Modbus INPUT register address."""

    canonical_name: str
    """Unique, stable identifier used across all layers."""

    cloud_api_field: str | None = None
    """Matching field name in the cloud MidboxData model, or None."""

    ha_sensor_key: str | None = None
    """HA sensor key used in coordinator_mappings.py, or None."""

    bit_width: int = 16
    """Register width: 16 for single register, 32 for two consecutive."""

    scale: ScaleFactor = ScaleFactor.NONE
    """Divisor applied to the raw register value."""

    signed: bool = False
    """Whether the raw value uses two's-complement signed representation."""

    unit: str | None = None
    """Engineering unit after scaling (V, A, W, Hz, kWh, etc.)."""

    category: GridBossCategory = GridBossCategory.POWER
    """Logical grouping for documentation and filtering."""

    description: str = ""
    """Human-readable explanation of the register."""


# =============================================================================
# REGISTER DEFINITIONS
# =============================================================================

GRIDBOSS_REGISTERS: tuple[GridBossRegisterDefinition, ...] = (
    # =========================================================================
    # VOLTAGE (regs 1-9, ÷10 → V)
    # =========================================================================
    GridBossRegisterDefinition(
        address=1,
        canonical_name="grid_voltage",
        cloud_api_field="gridRmsVolt",
        ha_sensor_key="grid_voltage",
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=GridBossCategory.VOLTAGE,
        description="Grid aggregate RMS voltage.",
    ),
    GridBossRegisterDefinition(
        address=2,
        canonical_name="ups_voltage",
        cloud_api_field="upsRmsVolt",
        ha_sensor_key="ups_voltage",
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=GridBossCategory.VOLTAGE,
        description="UPS (inverter output) aggregate RMS voltage.",
    ),
    GridBossRegisterDefinition(
        address=3,
        canonical_name="gen_voltage",
        cloud_api_field="genRmsVolt",
        ha_sensor_key="generator_voltage",
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=GridBossCategory.VOLTAGE,
        description="Generator aggregate RMS voltage.",
    ),
    GridBossRegisterDefinition(
        address=4,
        canonical_name="grid_l1_voltage",
        cloud_api_field="gridL1RmsVolt",
        ha_sensor_key="grid_voltage_l1",
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=GridBossCategory.VOLTAGE,
        description="Grid L1 (leg 1) RMS voltage.",
    ),
    GridBossRegisterDefinition(
        address=5,
        canonical_name="grid_l2_voltage",
        cloud_api_field="gridL2RmsVolt",
        ha_sensor_key="grid_voltage_l2",
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=GridBossCategory.VOLTAGE,
        description="Grid L2 (leg 2) RMS voltage.",
    ),
    GridBossRegisterDefinition(
        address=6,
        canonical_name="ups_l1_voltage",
        cloud_api_field="upsL1RmsVolt",
        ha_sensor_key="load_voltage_l1",
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=GridBossCategory.VOLTAGE,
        description="UPS L1 output voltage (= load L1 voltage).",
    ),
    GridBossRegisterDefinition(
        address=7,
        canonical_name="ups_l2_voltage",
        cloud_api_field="upsL2RmsVolt",
        ha_sensor_key="load_voltage_l2",
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=GridBossCategory.VOLTAGE,
        description="UPS L2 output voltage (= load L2 voltage).",
    ),
    GridBossRegisterDefinition(
        address=8,
        canonical_name="gen_l1_voltage",
        cloud_api_field="genL1RmsVolt",
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=GridBossCategory.VOLTAGE,
        description="Generator L1 RMS voltage.",
    ),
    GridBossRegisterDefinition(
        address=9,
        canonical_name="gen_l2_voltage",
        cloud_api_field="genL2RmsVolt",
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=GridBossCategory.VOLTAGE,
        description="Generator L2 RMS voltage.",
    ),
    # =========================================================================
    # CURRENT (regs 10-17, ÷10 → A)
    # =========================================================================
    GridBossRegisterDefinition(
        address=10,
        canonical_name="grid_l1_current",
        cloud_api_field="gridL1RmsCurr",
        ha_sensor_key="grid_current_l1",
        scale=ScaleFactor.DIV_10,
        unit="A",
        category=GridBossCategory.CURRENT,
        description="Grid L1 RMS current.",
    ),
    GridBossRegisterDefinition(
        address=11,
        canonical_name="grid_l2_current",
        cloud_api_field="gridL2RmsCurr",
        ha_sensor_key="grid_current_l2",
        scale=ScaleFactor.DIV_10,
        unit="A",
        category=GridBossCategory.CURRENT,
        description="Grid L2 RMS current.",
    ),
    GridBossRegisterDefinition(
        address=12,
        canonical_name="load_l1_current",
        cloud_api_field="loadL1RmsCurr",
        ha_sensor_key="load_current_l1",
        scale=ScaleFactor.DIV_10,
        unit="A",
        category=GridBossCategory.CURRENT,
        description="Load L1 RMS current.",
    ),
    GridBossRegisterDefinition(
        address=13,
        canonical_name="load_l2_current",
        cloud_api_field="loadL2RmsCurr",
        ha_sensor_key="load_current_l2",
        scale=ScaleFactor.DIV_10,
        unit="A",
        category=GridBossCategory.CURRENT,
        description="Load L2 RMS current.",
    ),
    GridBossRegisterDefinition(
        address=14,
        canonical_name="gen_l1_current",
        cloud_api_field="genL1RmsCurr",
        ha_sensor_key="generator_current_l1",
        scale=ScaleFactor.DIV_10,
        unit="A",
        category=GridBossCategory.CURRENT,
        description="Generator L1 RMS current.",
    ),
    GridBossRegisterDefinition(
        address=15,
        canonical_name="gen_l2_current",
        cloud_api_field="genL2RmsCurr",
        ha_sensor_key="generator_current_l2",
        scale=ScaleFactor.DIV_10,
        unit="A",
        category=GridBossCategory.CURRENT,
        description="Generator L2 RMS current.",
    ),
    GridBossRegisterDefinition(
        address=16,
        canonical_name="ups_l1_current",
        cloud_api_field="upsL1RmsCurr",
        ha_sensor_key="ups_current_l1",
        scale=ScaleFactor.DIV_10,
        unit="A",
        category=GridBossCategory.CURRENT,
        description="UPS L1 output RMS current.",
    ),
    GridBossRegisterDefinition(
        address=17,
        canonical_name="ups_l2_current",
        cloud_api_field="upsL2RmsCurr",
        ha_sensor_key="ups_current_l2",
        scale=ScaleFactor.DIV_10,
        unit="A",
        category=GridBossCategory.CURRENT,
        description="UPS L2 output RMS current.",
    ),
    # =========================================================================
    # POWER (regs 26-33, signed, W — no scaling)
    # =========================================================================
    GridBossRegisterDefinition(
        address=26,
        canonical_name="grid_l1_power",
        cloud_api_field="gridL1ActivePower",
        ha_sensor_key="grid_power_l1",
        signed=True,
        unit="W",
        category=GridBossCategory.POWER,
        description="Grid L1 active power (signed: + import, - export).",
    ),
    GridBossRegisterDefinition(
        address=27,
        canonical_name="grid_l2_power",
        cloud_api_field="gridL2ActivePower",
        ha_sensor_key="grid_power_l2",
        signed=True,
        unit="W",
        category=GridBossCategory.POWER,
        description="Grid L2 active power (signed: + import, - export).",
    ),
    GridBossRegisterDefinition(
        address=28,
        canonical_name="load_l1_power",
        cloud_api_field="loadL1ActivePower",
        ha_sensor_key="load_power_l1",
        signed=True,
        unit="W",
        category=GridBossCategory.POWER,
        description="Load L1 active power.",
    ),
    GridBossRegisterDefinition(
        address=29,
        canonical_name="load_l2_power",
        cloud_api_field="loadL2ActivePower",
        ha_sensor_key="load_power_l2",
        signed=True,
        unit="W",
        category=GridBossCategory.POWER,
        description="Load L2 active power.",
    ),
    GridBossRegisterDefinition(
        address=30,
        canonical_name="gen_l1_power",
        cloud_api_field="genL1ActivePower",
        ha_sensor_key="generator_power_l1",
        signed=True,
        unit="W",
        category=GridBossCategory.POWER,
        description="Generator L1 active power.",
    ),
    GridBossRegisterDefinition(
        address=31,
        canonical_name="gen_l2_power",
        cloud_api_field="genL2ActivePower",
        ha_sensor_key="generator_power_l2",
        signed=True,
        unit="W",
        category=GridBossCategory.POWER,
        description="Generator L2 active power.",
    ),
    GridBossRegisterDefinition(
        address=32,
        canonical_name="ups_l1_power",
        cloud_api_field="upsL1ActivePower",
        ha_sensor_key="ups_power_l1",
        signed=True,
        unit="W",
        category=GridBossCategory.POWER,
        description="UPS L1 output active power.",
    ),
    GridBossRegisterDefinition(
        address=33,
        canonical_name="ups_l2_power",
        cloud_api_field="upsL2ActivePower",
        ha_sensor_key="ups_power_l2",
        signed=True,
        unit="W",
        category=GridBossCategory.POWER,
        description="UPS L2 output active power.",
    ),
    # =========================================================================
    # SMART LOAD POWER (regs 34-41, signed, W — no scaling)
    # When smart port status = 2 (AC Couple), these show AC couple power.
    # =========================================================================
    GridBossRegisterDefinition(
        address=34,
        canonical_name="smart_load1_l1_power",
        cloud_api_field="smartLoad1L1ActivePower",
        ha_sensor_key="smart_load1_power_l1",
        signed=True,
        unit="W",
        category=GridBossCategory.SMART_LOAD,
        description="Smart load port 1, L1 active power.",
    ),
    GridBossRegisterDefinition(
        address=35,
        canonical_name="smart_load1_l2_power",
        cloud_api_field="smartLoad1L2ActivePower",
        ha_sensor_key="smart_load1_power_l2",
        signed=True,
        unit="W",
        category=GridBossCategory.SMART_LOAD,
        description="Smart load port 1, L2 active power.",
    ),
    GridBossRegisterDefinition(
        address=36,
        canonical_name="smart_load2_l1_power",
        cloud_api_field="smartLoad2L1ActivePower",
        ha_sensor_key="smart_load2_power_l1",
        signed=True,
        unit="W",
        category=GridBossCategory.SMART_LOAD,
        description="Smart load port 2, L1 active power.",
    ),
    GridBossRegisterDefinition(
        address=37,
        canonical_name="smart_load2_l2_power",
        cloud_api_field="smartLoad2L2ActivePower",
        ha_sensor_key="smart_load2_power_l2",
        signed=True,
        unit="W",
        category=GridBossCategory.SMART_LOAD,
        description="Smart load port 2, L2 active power.",
    ),
    GridBossRegisterDefinition(
        address=38,
        canonical_name="smart_load3_l1_power",
        cloud_api_field="smartLoad3L1ActivePower",
        ha_sensor_key="smart_load3_power_l1",
        signed=True,
        unit="W",
        category=GridBossCategory.SMART_LOAD,
        description="Smart load port 3, L1 active power.",
    ),
    GridBossRegisterDefinition(
        address=39,
        canonical_name="smart_load3_l2_power",
        cloud_api_field="smartLoad3L2ActivePower",
        ha_sensor_key="smart_load3_power_l2",
        signed=True,
        unit="W",
        category=GridBossCategory.SMART_LOAD,
        description="Smart load port 3, L2 active power.",
    ),
    GridBossRegisterDefinition(
        address=40,
        canonical_name="smart_load4_l1_power",
        cloud_api_field="smartLoad4L1ActivePower",
        ha_sensor_key="smart_load4_power_l1",
        signed=True,
        unit="W",
        category=GridBossCategory.SMART_LOAD,
        description="Smart load port 4, L1 active power.",
    ),
    GridBossRegisterDefinition(
        address=41,
        canonical_name="smart_load4_l2_power",
        cloud_api_field="smartLoad4L2ActivePower",
        ha_sensor_key="smart_load4_power_l2",
        signed=True,
        unit="W",
        category=GridBossCategory.SMART_LOAD,
        description="Smart load port 4, L2 active power.",
    ),
    # =========================================================================
    # DAILY ENERGY (regs 42-67, 16-bit, ÷10 → kWh)
    # =========================================================================
    # Load
    GridBossRegisterDefinition(
        address=42,
        canonical_name="load_energy_today_l1",
        cloud_api_field="eLoadTodayL1",
        ha_sensor_key="load_l1",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="Load L1 energy today.",
    ),
    GridBossRegisterDefinition(
        address=43,
        canonical_name="load_energy_today_l2",
        cloud_api_field="eLoadTodayL2",
        ha_sensor_key="load_l2",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="Load L2 energy today.",
    ),
    # UPS
    GridBossRegisterDefinition(
        address=44,
        canonical_name="ups_energy_today_l1",
        cloud_api_field="eUpsTodayL1",
        ha_sensor_key="ups_l1",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="UPS L1 energy today.",
    ),
    GridBossRegisterDefinition(
        address=45,
        canonical_name="ups_energy_today_l2",
        cloud_api_field="eUpsTodayL2",
        ha_sensor_key="ups_l2",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="UPS L2 energy today.",
    ),
    # Grid export
    GridBossRegisterDefinition(
        address=46,
        canonical_name="grid_export_today_l1",
        cloud_api_field="eToGridTodayL1",
        ha_sensor_key="grid_export_l1",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="Grid export L1 energy today.",
    ),
    GridBossRegisterDefinition(
        address=47,
        canonical_name="grid_export_today_l2",
        cloud_api_field="eToGridTodayL2",
        ha_sensor_key="grid_export_l2",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="Grid export L2 energy today.",
    ),
    # Grid import
    GridBossRegisterDefinition(
        address=48,
        canonical_name="grid_import_today_l1",
        cloud_api_field="eToUserTodayL1",
        ha_sensor_key="grid_import_l1",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="Grid import L1 energy today.",
    ),
    GridBossRegisterDefinition(
        address=49,
        canonical_name="grid_import_today_l2",
        cloud_api_field="eToUserTodayL2",
        ha_sensor_key="grid_import_l2",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="Grid import L2 energy today.",
    ),
    # Smart load daily (regs 52-59)
    # Note: regs 50-51 are unused/unknown — the smart load daily block starts
    # at reg 52, NOT 50.  Confirmed by Cloud API ↔ Modbus comparison (#146).
    GridBossRegisterDefinition(
        address=52,
        canonical_name="smart_load1_energy_today_l1",
        cloud_api_field="eSmartLoad1TodayL1",
        ha_sensor_key="smart_load1_l1",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="Smart load port 1, L1 energy today.",
    ),
    GridBossRegisterDefinition(
        address=53,
        canonical_name="smart_load1_energy_today_l2",
        cloud_api_field="eSmartLoad1TodayL2",
        ha_sensor_key="smart_load1_l2",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="Smart load port 1, L2 energy today.",
    ),
    GridBossRegisterDefinition(
        address=54,
        canonical_name="smart_load2_energy_today_l1",
        cloud_api_field="eSmartLoad2TodayL1",
        ha_sensor_key="smart_load2_l1",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="Smart load port 2, L1 energy today.",
    ),
    GridBossRegisterDefinition(
        address=55,
        canonical_name="smart_load2_energy_today_l2",
        cloud_api_field="eSmartLoad2TodayL2",
        ha_sensor_key="smart_load2_l2",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="Smart load port 2, L2 energy today.",
    ),
    GridBossRegisterDefinition(
        address=56,
        canonical_name="smart_load3_energy_today_l1",
        cloud_api_field="eSmartLoad3TodayL1",
        ha_sensor_key="smart_load3_l1",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="Smart load port 3, L1 energy today.",
    ),
    GridBossRegisterDefinition(
        address=57,
        canonical_name="smart_load3_energy_today_l2",
        cloud_api_field="eSmartLoad3TodayL2",
        ha_sensor_key="smart_load3_l2",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="Smart load port 3, L2 energy today.",
    ),
    GridBossRegisterDefinition(
        address=58,
        canonical_name="smart_load4_energy_today_l1",
        cloud_api_field="eSmartLoad4TodayL1",
        ha_sensor_key="smart_load4_l1",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="Smart load port 4, L1 energy today.",
    ),
    GridBossRegisterDefinition(
        address=59,
        canonical_name="smart_load4_energy_today_l2",
        cloud_api_field="eSmartLoad4TodayL2",
        ha_sensor_key="smart_load4_l2",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="Smart load port 4, L2 energy today.",
    ),
    # AC couple daily (regs 60-67)
    GridBossRegisterDefinition(
        address=60,
        canonical_name="ac_couple1_energy_today_l1",
        cloud_api_field="eACcouple1TodayL1",
        ha_sensor_key="ac_couple1_l1",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="AC couple port 1, L1 energy today.",
    ),
    GridBossRegisterDefinition(
        address=61,
        canonical_name="ac_couple1_energy_today_l2",
        cloud_api_field="eACcouple1TodayL2",
        ha_sensor_key="ac_couple1_l2",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="AC couple port 1, L2 energy today.",
    ),
    GridBossRegisterDefinition(
        address=62,
        canonical_name="ac_couple2_energy_today_l1",
        cloud_api_field="eACcouple2TodayL1",
        ha_sensor_key="ac_couple2_l1",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="AC couple port 2, L1 energy today.",
    ),
    GridBossRegisterDefinition(
        address=63,
        canonical_name="ac_couple2_energy_today_l2",
        cloud_api_field="eACcouple2TodayL2",
        ha_sensor_key="ac_couple2_l2",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="AC couple port 2, L2 energy today.",
    ),
    GridBossRegisterDefinition(
        address=64,
        canonical_name="ac_couple3_energy_today_l1",
        cloud_api_field="eACcouple3TodayL1",
        ha_sensor_key="ac_couple3_l1",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="AC couple port 3, L1 energy today.",
    ),
    GridBossRegisterDefinition(
        address=65,
        canonical_name="ac_couple3_energy_today_l2",
        cloud_api_field="eACcouple3TodayL2",
        ha_sensor_key="ac_couple3_l2",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="AC couple port 3, L2 energy today.",
    ),
    GridBossRegisterDefinition(
        address=66,
        canonical_name="ac_couple4_energy_today_l1",
        cloud_api_field="eACcouple4TodayL1",
        ha_sensor_key="ac_couple4_l1",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="AC couple port 4, L1 energy today.",
    ),
    GridBossRegisterDefinition(
        address=67,
        canonical_name="ac_couple4_energy_today_l2",
        cloud_api_field="eACcouple4TodayL2",
        ha_sensor_key="ac_couple4_l2",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_DAILY,
        description="AC couple port 4, L2 energy today.",
    ),
    # =========================================================================
    # LIFETIME ENERGY (regs 68-118, 32-bit, ÷10 → kWh)
    # =========================================================================
    # Load lifetime
    GridBossRegisterDefinition(
        address=68,
        canonical_name="load_energy_total_l1",
        cloud_api_field="eLoadTotalL1",
        ha_sensor_key="load_lifetime_l1",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="Load L1 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=70,
        canonical_name="load_energy_total_l2",
        cloud_api_field="eLoadTotalL2",
        ha_sensor_key="load_lifetime_l2",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="Load L2 lifetime energy (32-bit).",
    ),
    # UPS lifetime
    GridBossRegisterDefinition(
        address=72,
        canonical_name="ups_energy_total_l1",
        cloud_api_field="eUpsTotalL1",
        ha_sensor_key="ups_lifetime_l1",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="UPS L1 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=74,
        canonical_name="ups_energy_total_l2",
        cloud_api_field="eUpsTotalL2",
        ha_sensor_key="ups_lifetime_l2",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="UPS L2 lifetime energy (32-bit).",
    ),
    # Grid export lifetime
    GridBossRegisterDefinition(
        address=76,
        canonical_name="grid_export_total_l1",
        cloud_api_field="eToGridTotalL1",
        ha_sensor_key="grid_export_lifetime_l1",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="Grid export L1 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=78,
        canonical_name="grid_export_total_l2",
        cloud_api_field="eToGridTotalL2",
        ha_sensor_key="grid_export_lifetime_l2",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="Grid export L2 lifetime energy (32-bit).",
    ),
    # Grid import lifetime
    GridBossRegisterDefinition(
        address=80,
        canonical_name="grid_import_total_l1",
        cloud_api_field="eToUserTotalL1",
        ha_sensor_key="grid_import_lifetime_l1",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="Grid import L1 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=82,
        canonical_name="grid_import_total_l2",
        cloud_api_field="eToUserTotalL2",
        ha_sensor_key="grid_import_lifetime_l2",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="Grid import L2 lifetime energy (32-bit).",
    ),
    # Smart load lifetime (regs 88-103)
    # Note: regs 84-87 are unused/unknown — the smart load lifetime block
    # starts at reg 88, NOT 84.  Confirmed by Cloud API ↔ Modbus comparison (#146).
    GridBossRegisterDefinition(
        address=88,
        canonical_name="smart_load1_energy_total_l1",
        cloud_api_field="eSmartLoad1TotalL1",
        ha_sensor_key="smart_load1_lifetime_l1",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="Smart load port 1, L1 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=90,
        canonical_name="smart_load1_energy_total_l2",
        cloud_api_field="eSmartLoad1TotalL2",
        ha_sensor_key="smart_load1_lifetime_l2",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="Smart load port 1, L2 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=92,
        canonical_name="smart_load2_energy_total_l1",
        cloud_api_field="eSmartLoad2TotalL1",
        ha_sensor_key="smart_load2_lifetime_l1",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="Smart load port 2, L1 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=94,
        canonical_name="smart_load2_energy_total_l2",
        cloud_api_field="eSmartLoad2TotalL2",
        ha_sensor_key="smart_load2_lifetime_l2",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="Smart load port 2, L2 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=96,
        canonical_name="smart_load3_energy_total_l1",
        cloud_api_field="eSmartLoad3TotalL1",
        ha_sensor_key="smart_load3_lifetime_l1",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="Smart load port 3, L1 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=98,
        canonical_name="smart_load3_energy_total_l2",
        cloud_api_field="eSmartLoad3TotalL2",
        ha_sensor_key="smart_load3_lifetime_l2",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="Smart load port 3, L2 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=100,
        canonical_name="smart_load4_energy_total_l1",
        cloud_api_field="eSmartLoad4TotalL1",
        ha_sensor_key="smart_load4_lifetime_l1",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="Smart load port 4, L1 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=102,
        canonical_name="smart_load4_energy_total_l2",
        cloud_api_field="eSmartLoad4TotalL2",
        ha_sensor_key="smart_load4_lifetime_l2",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="Smart load port 4, L2 lifetime energy (32-bit).",
    ),
    # AC couple lifetime (regs 104-118)
    # Note: regs 104-108 overlap with smart_port_status in the runtime read group.
    GridBossRegisterDefinition(
        address=104,
        canonical_name="ac_couple1_energy_total_l1",
        cloud_api_field="eACcouple1TotalL1",
        ha_sensor_key="ac_couple1_lifetime_l1",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="AC couple port 1, L1 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=106,
        canonical_name="ac_couple1_energy_total_l2",
        cloud_api_field="eACcouple1TotalL2",
        ha_sensor_key="ac_couple1_lifetime_l2",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="AC couple port 1, L2 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=108,
        canonical_name="ac_couple2_energy_total_l1",
        cloud_api_field="eACcouple2TotalL1",
        ha_sensor_key="ac_couple2_lifetime_l1",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="AC couple port 2, L1 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=110,
        canonical_name="ac_couple2_energy_total_l2",
        cloud_api_field="eACcouple2TotalL2",
        ha_sensor_key="ac_couple2_lifetime_l2",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="AC couple port 2, L2 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=112,
        canonical_name="ac_couple3_energy_total_l1",
        cloud_api_field="eACcouple3TotalL1",
        ha_sensor_key="ac_couple3_lifetime_l1",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="AC couple port 3, L1 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=114,
        canonical_name="ac_couple3_energy_total_l2",
        cloud_api_field="eACcouple3TotalL2",
        ha_sensor_key="ac_couple3_lifetime_l2",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="AC couple port 3, L2 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=116,
        canonical_name="ac_couple4_energy_total_l1",
        cloud_api_field="eACcouple4TotalL1",
        ha_sensor_key="ac_couple4_lifetime_l1",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="AC couple port 4, L1 lifetime energy (32-bit).",
    ),
    GridBossRegisterDefinition(
        address=118,
        canonical_name="ac_couple4_energy_total_l2",
        cloud_api_field="eACcouple4TotalL2",
        ha_sensor_key="ac_couple4_lifetime_l2",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=GridBossCategory.ENERGY_LIFETIME,
        description="AC couple port 4, L2 lifetime energy (32-bit).",
    ),
    # =========================================================================
    # SMART PORT STATUS
    # NOT stored in individual input registers. The 4 port modes are
    # bit-packed in HOLDING register 20 (2 bits per port, LSB-first):
    #   bits 0-1 = port 1, bits 2-3 = port 2, bits 4-5 = port 3, bits 6-7 = port 4
    #   Values: 0 = off, 1 = smart_load, 2 = ac_couple
    # Decoded in MidboxRuntimeData.from_modbus_registers() via the
    # smart_port_mode_reg parameter.
    #
    # Input registers 105-108 are the HIGH words of 32-bit AC couple
    # lifetime energy counters (ac_couple1..4), NOT smart port status.
    # =========================================================================
    # =========================================================================
    # FREQUENCY (regs 128-130, ÷100 → Hz)
    # =========================================================================
    GridBossRegisterDefinition(
        address=128,
        canonical_name="phase_lock_frequency",
        cloud_api_field="phaseLockFreq",
        ha_sensor_key="phase_lock_frequency",
        scale=ScaleFactor.DIV_100,
        unit="Hz",
        category=GridBossCategory.FREQUENCY,
        description="Phase lock loop frequency.",
    ),
    GridBossRegisterDefinition(
        address=129,
        canonical_name="grid_frequency",
        cloud_api_field="gridFreq",
        ha_sensor_key="frequency",
        scale=ScaleFactor.DIV_100,
        unit="Hz",
        category=GridBossCategory.FREQUENCY,
        description="Grid frequency.",
    ),
    GridBossRegisterDefinition(
        address=130,
        canonical_name="gen_frequency",
        cloud_api_field="genFreq",
        ha_sensor_key="generator_frequency",
        scale=ScaleFactor.DIV_100,
        unit="Hz",
        category=GridBossCategory.FREQUENCY,
        description="Generator frequency.",
    ),
)


# =============================================================================
# COMPUTED SENSOR KEYS (derived from L1+L2, not backed by single register)
# =============================================================================

COMPUTED_SENSOR_KEYS: frozenset[str] = frozenset(
    {
        # Aggregate power (L1 + L2)
        "grid_power",
        "load_power",
        "generator_power",
        "ups_power",
        "consumption_power",  # alias for load_power (CT measurement)
        "hybrid_power",  # ups_power - grid_power fallback
        # Per-port aggregates
        "smart_load1_power",
        "smart_load2_power",
        "smart_load3_power",
        "smart_load4_power",
        # AC couple power (from smart load regs when port status=2)
        "ac_couple1_power_l1",
        "ac_couple1_power_l2",
        "ac_couple1_power",
        "ac_couple2_power_l1",
        "ac_couple2_power_l2",
        "ac_couple2_power",
        "ac_couple3_power_l1",
        "ac_couple3_power_l2",
        "ac_couple3_power",
        "ac_couple4_power_l1",
        "ac_couple4_power_l2",
        "ac_couple4_power",
        # Aggregate energy (L1 + L2)
        "ups_today",
        "ups_lifetime",
        "grid_export_today",
        "grid_export_total",
        "grid_import_today",
        "grid_import_total",
        "load_today",
        "load_total",
        "ac_couple1_today",
        "ac_couple1_total",
        "ac_couple2_today",
        "ac_couple2_total",
        "ac_couple3_today",
        "ac_couple3_total",
        "ac_couple4_today",
        "ac_couple4_total",
        "smart_load1_today",
        "smart_load1_total",
        "smart_load2_today",
        "smart_load2_total",
        "smart_load3_today",
        "smart_load3_total",
        "smart_load4_today",
        "smart_load4_total",
        # Boolean / status
        "off_grid",
    }
)

# =============================================================================
# CLOUD-ONLY SENSOR KEYS (HTTP API only, no Modbus register)
# =============================================================================

CLOUD_ONLY_SENSOR_KEYS: frozenset[str] = frozenset(
    {
        "energy_to_user",  # eEnergyToUser aggregate
        "ups_energy",  # eUpsEnergy aggregate
        "inverter_lost_status",  # device connectivity
    }
)


# =============================================================================
# LOOKUP INDEXES
# =============================================================================

BY_NAME: dict[str, GridBossRegisterDefinition] = {r.canonical_name: r for r in GRIDBOSS_REGISTERS}
"""Lookup by canonical_name → definition."""

BY_ADDRESS: dict[int, GridBossRegisterDefinition | tuple[GridBossRegisterDefinition, ...]] = {}
"""Lookup by register address → definition."""
_addr_groups: dict[int, list[GridBossRegisterDefinition]] = {}
for _r in GRIDBOSS_REGISTERS:
    _addr_groups.setdefault(_r.address, []).append(_r)
BY_ADDRESS = {
    addr: defs[0] if len(defs) == 1 else tuple(defs) for addr, defs in _addr_groups.items()
}

BY_CLOUD_FIELD: dict[str, GridBossRegisterDefinition] = {
    r.cloud_api_field: r for r in GRIDBOSS_REGISTERS if r.cloud_api_field is not None
}
"""Lookup by cloud API field name → definition."""

BY_SENSOR_KEY: dict[str, GridBossRegisterDefinition] = {
    r.ha_sensor_key: r for r in GRIDBOSS_REGISTERS if r.ha_sensor_key is not None
}
"""Lookup by HA sensor key → definition."""

_cat_groups: dict[GridBossCategory, list[GridBossRegisterDefinition]] = {}
for _r in GRIDBOSS_REGISTERS:
    _cat_groups.setdefault(_r.category, []).append(_r)
BY_CATEGORY: dict[GridBossCategory, tuple[GridBossRegisterDefinition, ...]] = {
    cat: tuple(defs) for cat, defs in _cat_groups.items()
}
"""Lookup by category → tuple of definitions."""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def runtime_registers() -> tuple[GridBossRegisterDefinition, ...]:
    """Return registers in the runtime read group (voltage, current, power, freq, status).

    These are read in a single Modbus operation.
    """
    runtime_cats = {
        GridBossCategory.VOLTAGE,
        GridBossCategory.CURRENT,
        GridBossCategory.POWER,
        GridBossCategory.SMART_LOAD,
        GridBossCategory.SMART_PORT,
        GridBossCategory.FREQUENCY,
    }
    return tuple(r for r in GRIDBOSS_REGISTERS if r.category in runtime_cats)


def energy_registers() -> tuple[GridBossRegisterDefinition, ...]:
    """Return registers in the energy read group (daily + lifetime)."""
    energy_cats = {GridBossCategory.ENERGY_DAILY, GridBossCategory.ENERGY_LIFETIME}
    return tuple(r for r in GRIDBOSS_REGISTERS if r.category in energy_cats)


def all_ha_sensor_keys() -> frozenset[str]:
    """Return all HA sensor keys (register-backed + computed + cloud-only)."""
    register_keys = frozenset(r.ha_sensor_key for r in GRIDBOSS_REGISTERS if r.ha_sensor_key)
    return register_keys | COMPUTED_SENSOR_KEYS | CLOUD_ONLY_SENSOR_KEYS


__all__ = [
    # Types
    "GridBossCategory",
    "GridBossRegisterDefinition",
    # Data
    "GRIDBOSS_REGISTERS",
    "COMPUTED_SENSOR_KEYS",
    "CLOUD_ONLY_SENSOR_KEYS",
    # Indexes
    "BY_ADDRESS",
    "BY_CATEGORY",
    "BY_CLOUD_FIELD",
    "BY_NAME",
    "BY_SENSOR_KEY",
    # Helpers
    "ScaleFactor",
    "all_ha_sensor_keys",
    "energy_registers",
    "runtime_registers",
]
