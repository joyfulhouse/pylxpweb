"""Canonical inverter input register map.

Single source of truth for ALL inverter input registers (0-232).
Cross-validated against:
  - Luxpower Modbus RTU Protocol (Table 7 Input Register Mapping)
  - EG4-18KPV-12LV Modbus Protocol specification
  - Live hardware testing (18kPV, FlexBOSS21, LXP-EU 12K)
  - eg4-modbus-monitor project (galets/poldim)

Each RegisterDefinition carries the full identity chain:
  register address → scale/signed → canonical name → cloud API field → HA sensor key

The `models` field controls which inverter families support each register.
ALL = every family.  Use specific frozensets to restrict.

Register layout follows Luxpower convention (SOC/SOH packed in reg 5).
EG4 18KPV documentation shows separate regs but actual hardware uses packed format.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# Model sets for the `models` field on RegisterDefinition
# ---------------------------------------------------------------------------
ALL: frozenset[str] = frozenset({"EG4_HYBRID", "EG4_OFFGRID", "LXP"})
EG4: frozenset[str] = frozenset({"EG4_HYBRID", "EG4_OFFGRID"})
LXP_ONLY: frozenset[str] = frozenset({"LXP"})


class ScaleFactor(int, Enum):
    """Divisor applied to raw register value."""

    NONE = 1
    DIV_10 = 10
    DIV_100 = 100
    DIV_1000 = 1000


class RegisterCategory(str, Enum):
    """Logical grouping for read scheduling and entity creation."""

    RUNTIME = "runtime"
    ENERGY_DAILY = "energy_daily"
    ENERGY_LIFETIME = "energy_lifetime"
    BMS = "bms"
    TEMPERATURE = "temperature"
    FAULT = "fault"
    STATUS = "status"
    GENERATOR = "generator"
    PARALLEL = "parallel"


@dataclass(frozen=True)
class RegisterDefinition:
    """Single register definition — the atomic unit of the register map.

    Attributes:
        address: Modbus input register address (function code 0x04).
        canonical_name: Stable API field name.  This is the contract boundary
            between pylxpweb and consumers (e.g. the HA integration).
            Once published, canonical names MUST NOT change.
        cloud_api_field: HTTP JSON field name returned by the EG4 cloud API.
            None if this register has no cloud equivalent (local-only).
        ha_sensor_key: Home Assistant sensor key used in coordinator data dict.
            None if this register does not map to a user-visible sensor.
        bit_width: 16 (single register) or 32 (register pair, low word first).
        scale: Divisor to convert raw value to engineering units.
        signed: True for two's-complement signed values.
        unit: Engineering unit string ("V", "W", "kWh", "A", "%", "Hz", "°C").
        category: Logical grouping for read scheduling.
        models: Which InverterFamily values support this register.
        description: Human-readable description from protocol documentation.
        packed: If set, describes bit packing (e.g. "low=SOC,high=SOH").
    """

    address: int
    canonical_name: str
    cloud_api_field: str | None = None
    ha_sensor_key: str | None = None
    bit_width: int = 16
    scale: ScaleFactor = ScaleFactor.NONE
    signed: bool = False
    unit: str = ""
    category: RegisterCategory = RegisterCategory.RUNTIME
    models: frozenset[str] = ALL
    description: str = ""
    packed: str | None = None


# =============================================================================
# INVERTER INPUT REGISTERS (Function Code 0x04, Read-Only)
# =============================================================================
# Register addresses follow the Luxpower convention.
# EG4 18KPV documentation uses a +1 offset starting at reg 6 (SOH separate),
# but actual firmware matches Luxpower layout (SOC/SOH packed at reg 5).
#
# Power values are 16-bit on ALL models (EG4 Hybrid, EG4 Offgrid, LXP).
# The old pylxpweb code incorrectly assumed 32-bit power for some models.

INVERTER_INPUT_REGISTERS: tuple[RegisterDefinition, ...] = (
    # =========================================================================
    # DEVICE STATUS (reg 0)
    # =========================================================================
    RegisterDefinition(
        address=0,
        canonical_name="device_status",
        cloud_api_field="status",
        ha_sensor_key="status_code",
        category=RegisterCategory.STATUS,
        description="Operating mode code (see working modes table).",
    ),
    # =========================================================================
    # PV INPUT (regs 1-3: voltage, regs 7-9: power)
    # =========================================================================
    RegisterDefinition(
        address=1,
        canonical_name="pv1_voltage",
        cloud_api_field="vpv1",
        ha_sensor_key="pv1_voltage",
        scale=ScaleFactor.DIV_10,
        unit="V",
        description="PV string 1 voltage.",
    ),
    RegisterDefinition(
        address=2,
        canonical_name="pv2_voltage",
        cloud_api_field="vpv2",
        ha_sensor_key="pv2_voltage",
        scale=ScaleFactor.DIV_10,
        unit="V",
        description="PV string 2 voltage.",
    ),
    RegisterDefinition(
        address=3,
        canonical_name="pv3_voltage",
        cloud_api_field="vpv3",
        ha_sensor_key="pv3_voltage",
        scale=ScaleFactor.DIV_10,
        unit="V",
        description="PV string 3 voltage.",
    ),
    RegisterDefinition(
        address=7,
        canonical_name="pv1_power",
        cloud_api_field="ppv1",
        ha_sensor_key="pv1_power",
        unit="W",
        description="PV string 1 power.",
    ),
    RegisterDefinition(
        address=8,
        canonical_name="pv2_power",
        cloud_api_field="ppv2",
        ha_sensor_key="pv2_power",
        unit="W",
        description="PV string 2 power.",
    ),
    RegisterDefinition(
        address=9,
        canonical_name="pv3_power",
        cloud_api_field="ppv3",
        ha_sensor_key="pv3_power",
        unit="W",
        description="PV string 3 power.",
    ),
    # =========================================================================
    # BATTERY CORE (regs 4-5, 10-11)
    # =========================================================================
    RegisterDefinition(
        address=4,
        canonical_name="battery_voltage",
        cloud_api_field="vBat",
        ha_sensor_key="battery_voltage",
        scale=ScaleFactor.DIV_10,
        unit="V",
        description="Battery pack voltage.",
    ),
    RegisterDefinition(
        address=5,
        canonical_name="soc_soh_packed",
        cloud_api_field=None,
        ha_sensor_key=None,
        category=RegisterCategory.BMS,
        description="Packed: low byte = SOC (%), high byte = SOH (%).",
        packed="low=SOC,high=SOH",
    ),
    RegisterDefinition(
        address=10,
        canonical_name="charge_power",
        cloud_api_field="pCharge",
        ha_sensor_key="battery_charge_power",
        unit="W",
        description="Battery charging power (power flowing into battery).",
    ),
    RegisterDefinition(
        address=11,
        canonical_name="discharge_power",
        cloud_api_field="pDisCharge",
        ha_sensor_key="battery_discharge_power",
        unit="W",
        description="Battery discharging power (power flowing out of battery).",
    ),
    # =========================================================================
    # GRID / AC INPUT (regs 12-19)
    # =========================================================================
    RegisterDefinition(
        address=12,
        canonical_name="grid_voltage_r",
        cloud_api_field="vacr",
        ha_sensor_key="grid_voltage_r",
        scale=ScaleFactor.DIV_10,
        unit="V",
        description="Grid R-phase voltage (L1-L2 on split-phase).",
    ),
    RegisterDefinition(
        address=13,
        canonical_name="grid_voltage_s",
        cloud_api_field="vacs",
        ha_sensor_key="grid_voltage_s",
        scale=ScaleFactor.DIV_10,
        unit="V",
        description="Grid S-phase voltage (L2-L3 on split-phase).",
    ),
    RegisterDefinition(
        address=14,
        canonical_name="grid_voltage_t",
        cloud_api_field="vact",
        ha_sensor_key="grid_voltage_t",
        scale=ScaleFactor.DIV_10,
        unit="V",
        description="Grid T-phase voltage (L3-L1 on split-phase).",
    ),
    RegisterDefinition(
        address=15,
        canonical_name="grid_frequency",
        cloud_api_field="fac",
        ha_sensor_key="grid_frequency",
        scale=ScaleFactor.DIV_100,
        unit="Hz",
        description="Grid/mains frequency.",
    ),
    RegisterDefinition(
        address=16,
        canonical_name="inverter_power",
        cloud_api_field="pinv",
        ha_sensor_key="ac_power",
        unit="W",
        description="Inverter output power (Pinv). On-grid inverting power.",
    ),
    RegisterDefinition(
        address=17,
        canonical_name="rectifier_power",
        cloud_api_field="prec",
        ha_sensor_key="rectifier_power",
        unit="W",
        description="AC charging rectifier power (Prec). Grid-to-battery power.",
    ),
    RegisterDefinition(
        address=18,
        canonical_name="inverter_rms_current_r",
        cloud_api_field=None,
        ha_sensor_key="grid_current_l1",
        scale=ScaleFactor.DIV_100,
        unit="A",
        description="Inverter RMS current output, R/L1 phase.",
    ),
    RegisterDefinition(
        address=19,
        canonical_name="power_factor",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_1000,
        description="Power factor. x in (0,1000] => x/1000; x in (1000,2000) => (1000-x)/1000.",
    ),
    # =========================================================================
    # EPS / OFF-GRID OUTPUT (regs 20-27)
    # =========================================================================
    RegisterDefinition(
        address=20,
        canonical_name="eps_voltage_r",
        cloud_api_field="vepsr",
        ha_sensor_key="eps_voltage_r",
        scale=ScaleFactor.DIV_10,
        unit="V",
        description="EPS R-phase output voltage.",
    ),
    RegisterDefinition(
        address=21,
        canonical_name="eps_voltage_s",
        cloud_api_field="vepss",
        ha_sensor_key="eps_voltage_s",
        scale=ScaleFactor.DIV_10,
        unit="V",
        description="EPS S-phase output voltage.",
    ),
    RegisterDefinition(
        address=22,
        canonical_name="eps_voltage_t",
        cloud_api_field="vepst",
        ha_sensor_key="eps_voltage_t",
        scale=ScaleFactor.DIV_10,
        unit="V",
        description="EPS T-phase output voltage.",
    ),
    RegisterDefinition(
        address=23,
        canonical_name="eps_frequency",
        cloud_api_field="feps",
        ha_sensor_key="eps_frequency",
        scale=ScaleFactor.DIV_100,
        unit="Hz",
        description="EPS/off-grid output frequency.",
    ),
    RegisterDefinition(
        address=24,
        canonical_name="eps_power",
        cloud_api_field="peps",
        ha_sensor_key="eps_power",
        unit="W",
        description="EPS/off-grid inverter output power.",
    ),
    RegisterDefinition(
        address=25,
        canonical_name="eps_apparent_power",
        cloud_api_field="seps",
        ha_sensor_key=None,
        unit="VA",
        description="EPS/off-grid apparent power.",
    ),
    RegisterDefinition(
        address=26,
        canonical_name="power_to_grid",
        cloud_api_field="pToGrid",
        ha_sensor_key="grid_export_power",
        unit="W",
        description="Power exported to grid (Ptogrid).",
    ),
    RegisterDefinition(
        address=27,
        canonical_name="power_to_user",
        cloud_api_field="pToUser",
        ha_sensor_key="grid_import_power",
        unit="W",
        description="Power imported from grid (Ptouser).",
    ),
    # =========================================================================
    # DAILY ENERGY (regs 28-37) — 16-bit, 0.1 kWh
    # =========================================================================
    RegisterDefinition(
        address=28,
        canonical_name="pv1_energy_today",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_DAILY,
        description="PV1 generation today (Epv1_day).",
    ),
    RegisterDefinition(
        address=29,
        canonical_name="pv2_energy_today",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_DAILY,
        description="PV2 generation today (Epv2_day).",
    ),
    RegisterDefinition(
        address=30,
        canonical_name="pv3_energy_today",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_DAILY,
        description="PV3 generation today (Epv3_day).",
    ),
    RegisterDefinition(
        address=31,
        canonical_name="inverter_energy_today",
        cloud_api_field="todayYielding",
        ha_sensor_key="yield",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_DAILY,
        description="On-grid inverter output energy today (Einv_day).",
    ),
    RegisterDefinition(
        address=32,
        canonical_name="ac_charge_energy_today",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_DAILY,
        description="AC charging rectifier energy today (Erec_day).",
    ),
    RegisterDefinition(
        address=33,
        canonical_name="charge_energy_today",
        cloud_api_field="todayCharging",
        ha_sensor_key="charging",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_DAILY,
        description="Battery charge energy today (Echg_day).",
    ),
    RegisterDefinition(
        address=34,
        canonical_name="discharge_energy_today",
        cloud_api_field="todayDischarging",
        ha_sensor_key="discharging",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_DAILY,
        description="Battery discharge energy today (Edischg_day).",
    ),
    RegisterDefinition(
        address=35,
        canonical_name="eps_energy_today",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_DAILY,
        description="Off-grid output energy today (Eeps_day).",
    ),
    RegisterDefinition(
        address=36,
        canonical_name="grid_export_energy_today",
        cloud_api_field="todayExport",
        ha_sensor_key="grid_export",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_DAILY,
        description="Export to grid energy today (Etogrid_day).",
    ),
    RegisterDefinition(
        address=37,
        canonical_name="grid_import_energy_today",
        cloud_api_field="todayImport",
        ha_sensor_key="grid_import",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_DAILY,
        description="Import from grid energy today (Etouser_day).",
    ),
    # =========================================================================
    # BUS VOLTAGES (regs 38-39)
    # =========================================================================
    RegisterDefinition(
        address=38,
        canonical_name="bus_voltage_1",
        cloud_api_field="vBus1",
        ha_sensor_key="bus1_voltage",
        scale=ScaleFactor.DIV_10,
        unit="V",
        description="DC bus 1 voltage.",
    ),
    RegisterDefinition(
        address=39,
        canonical_name="bus_voltage_2",
        cloud_api_field="vBus2",
        ha_sensor_key="bus2_voltage",
        scale=ScaleFactor.DIV_10,
        unit="V",
        description="DC bus 2 voltage.",
    ),
    # =========================================================================
    # LIFETIME ENERGY (regs 40-59) — 32-bit low/high pairs, 0.1 kWh
    # =========================================================================
    RegisterDefinition(
        address=40,
        canonical_name="pv1_energy_total",
        cloud_api_field=None,
        ha_sensor_key=None,
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_LIFETIME,
        description="PV1 cumulative generation (Epv1_all).",
    ),
    RegisterDefinition(
        address=42,
        canonical_name="pv2_energy_total",
        cloud_api_field=None,
        ha_sensor_key=None,
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_LIFETIME,
        description="PV2 cumulative generation (Epv2_all).",
    ),
    RegisterDefinition(
        address=44,
        canonical_name="pv3_energy_total",
        cloud_api_field=None,
        ha_sensor_key=None,
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_LIFETIME,
        description="PV3 cumulative generation (Epv3_all).",
    ),
    RegisterDefinition(
        address=46,
        canonical_name="inverter_energy_total",
        cloud_api_field="totalYielding",
        ha_sensor_key="yield_lifetime",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_LIFETIME,
        description="Cumulative inverter output energy (Einv_all).",
    ),
    RegisterDefinition(
        address=48,
        canonical_name="ac_charge_energy_total",
        cloud_api_field=None,
        ha_sensor_key=None,
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_LIFETIME,
        description="Cumulative AC charging rectified energy (Erec_all).",
    ),
    RegisterDefinition(
        address=50,
        canonical_name="charge_energy_total",
        cloud_api_field="totalCharging",
        ha_sensor_key="charging_lifetime",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_LIFETIME,
        description="Cumulative battery charge energy (Echg_all).",
    ),
    RegisterDefinition(
        address=52,
        canonical_name="discharge_energy_total",
        cloud_api_field="totalDischarging",
        ha_sensor_key="discharging_lifetime",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_LIFETIME,
        description="Cumulative battery discharge energy (Edischg_all).",
    ),
    RegisterDefinition(
        address=54,
        canonical_name="eps_energy_total",
        cloud_api_field=None,
        ha_sensor_key=None,
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_LIFETIME,
        description="Cumulative off-grid output energy (Eeps_all).",
    ),
    RegisterDefinition(
        address=56,
        canonical_name="grid_export_energy_total",
        cloud_api_field="totalExport",
        ha_sensor_key="grid_export_lifetime",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_LIFETIME,
        description="Cumulative export to grid energy (Etogrid_all).",
    ),
    RegisterDefinition(
        address=58,
        canonical_name="grid_import_energy_total",
        cloud_api_field="totalImport",
        ha_sensor_key="grid_import_lifetime",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_LIFETIME,
        description="Cumulative import from grid energy (Etouser_all).",
    ),
    # =========================================================================
    # FAULT / WARNING CODES (regs 60-63) — 32-bit pairs
    # =========================================================================
    RegisterDefinition(
        address=60,
        canonical_name="fault_code",
        cloud_api_field=None,
        ha_sensor_key=None,
        bit_width=32,
        category=RegisterCategory.FAULT,
        description="Inverter fault code (32-bit bitfield).",
    ),
    RegisterDefinition(
        address=62,
        canonical_name="warning_code",
        cloud_api_field=None,
        ha_sensor_key=None,
        bit_width=32,
        category=RegisterCategory.FAULT,
        description="Inverter warning code (32-bit bitfield).",
    ),
    # =========================================================================
    # TEMPERATURES (regs 64-68)
    # =========================================================================
    RegisterDefinition(
        address=64,
        canonical_name="internal_temperature",
        cloud_api_field="tinner",
        ha_sensor_key="internal_temperature",
        signed=True,
        unit="°C",
        category=RegisterCategory.TEMPERATURE,
        description="Internal/ring temperature.",
    ),
    RegisterDefinition(
        address=65,
        canonical_name="radiator_temperature_1",
        cloud_api_field="tradiator1",
        ha_sensor_key="radiator1_temperature",
        unit="°C",
        category=RegisterCategory.TEMPERATURE,
        description="Radiator temperature 1.",
    ),
    RegisterDefinition(
        address=66,
        canonical_name="radiator_temperature_2",
        cloud_api_field="tradiator2",
        ha_sensor_key="radiator2_temperature",
        unit="°C",
        category=RegisterCategory.TEMPERATURE,
        description="Radiator temperature 2.",
    ),
    RegisterDefinition(
        address=67,
        canonical_name="battery_temperature",
        cloud_api_field="tBat",
        ha_sensor_key="battery_temperature",
        unit="°C",
        category=RegisterCategory.TEMPERATURE,
        description="Battery temperature.",
    ),
    RegisterDefinition(
        address=68,
        canonical_name="battery_control_temperature",
        cloud_api_field=None,
        ha_sensor_key=None,
        unit="°C",
        category=RegisterCategory.TEMPERATURE,
        description="Battery control temperature.",
    ),
    # =========================================================================
    # RUNNING TIME (regs 69-70) — 32-bit
    # =========================================================================
    RegisterDefinition(
        address=69,
        canonical_name="running_time",
        cloud_api_field=None,
        ha_sensor_key=None,
        bit_width=32,
        unit="s",
        description="Total running time in seconds.",
    ),
    # =========================================================================
    # PV CURRENTS (regs 72-75)
    # =========================================================================
    RegisterDefinition(
        address=72,
        canonical_name="pv1_current",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_100,
        unit="A",
        description="PV string 1 current.",
    ),
    RegisterDefinition(
        address=73,
        canonical_name="pv2_current",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_100,
        unit="A",
        description="PV string 2 current.",
    ),
    RegisterDefinition(
        address=74,
        canonical_name="pv3_current",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_100,
        unit="A",
        description="PV string 3 current.",
    ),
    RegisterDefinition(
        address=75,
        canonical_name="battery_current_inv",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_100,
        unit="A",
        description="Battery current (inverter-measured).",
    ),
    # =========================================================================
    # AC INPUT TYPE & STATUS (reg 77)
    # =========================================================================
    RegisterDefinition(
        address=77,
        canonical_name="ac_input_type",
        cloud_api_field=None,
        ha_sensor_key=None,
        category=RegisterCategory.STATUS,
        description="AC input type bitfield. Bit0: 0=Grid, 1=Generator.",
    ),
    # =========================================================================
    # BMS DATA (regs 80-107)
    # =========================================================================
    RegisterDefinition(
        address=80,
        canonical_name="bms_battery_type",
        cloud_api_field=None,
        ha_sensor_key=None,
        category=RegisterCategory.BMS,
        description="Battery type/brand and communication type (0=CAN, 1=RS485).",
    ),
    RegisterDefinition(
        address=81,
        canonical_name="bms_charge_current_limit",
        cloud_api_field="maxChgCurr",
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        unit="A",
        category=RegisterCategory.BMS,
        description="BMS max charging current (empirical: 0.1A scale, doc says 0.01A).",
    ),
    RegisterDefinition(
        address=82,
        canonical_name="bms_discharge_current_limit",
        cloud_api_field="maxDischgCurr",
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        unit="A",
        category=RegisterCategory.BMS,
        description="BMS max discharging current.",
    ),
    RegisterDefinition(
        address=83,
        canonical_name="bms_charge_voltage_ref",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=RegisterCategory.BMS,
        description="BMS recommended charging voltage.",
    ),
    RegisterDefinition(
        address=84,
        canonical_name="bms_discharge_cutoff",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=RegisterCategory.BMS,
        description="BMS recommended discharge cutoff voltage.",
    ),
    # BMS status registers 85-94 (10 registers, opaque status words)
    RegisterDefinition(
        address=85,
        canonical_name="bms_status_0",
        category=RegisterCategory.BMS,
        description="BMS status register 0.",
    ),
    RegisterDefinition(
        address=86,
        canonical_name="bms_status_1",
        category=RegisterCategory.BMS,
        description="BMS status register 1.",
    ),
    RegisterDefinition(
        address=87,
        canonical_name="bms_status_2",
        category=RegisterCategory.BMS,
        description="BMS status register 2.",
    ),
    RegisterDefinition(
        address=88,
        canonical_name="bms_status_3",
        category=RegisterCategory.BMS,
        description="BMS status register 3.",
    ),
    RegisterDefinition(
        address=89,
        canonical_name="bms_status_4",
        category=RegisterCategory.BMS,
        description="BMS status register 4.",
    ),
    RegisterDefinition(
        address=90,
        canonical_name="bms_status_5",
        category=RegisterCategory.BMS,
        description="BMS status register 5.",
    ),
    RegisterDefinition(
        address=91,
        canonical_name="bms_status_6",
        category=RegisterCategory.BMS,
        description="BMS status register 6.",
    ),
    RegisterDefinition(
        address=92,
        canonical_name="bms_status_7",
        category=RegisterCategory.BMS,
        description="BMS status register 7.",
    ),
    RegisterDefinition(
        address=93,
        canonical_name="bms_status_8",
        category=RegisterCategory.BMS,
        description="BMS status register 8.",
    ),
    RegisterDefinition(
        address=94,
        canonical_name="bms_status_9",
        category=RegisterCategory.BMS,
        description="BMS status register 9.",
    ),
    RegisterDefinition(
        address=95,
        canonical_name="battery_status_inv",
        cloud_api_field=None,
        ha_sensor_key="battery_status",
        category=RegisterCategory.BMS,
        description="Inverter-aggregated lithium battery status. 0=Idle, 2=StandBy, 3=Active.",
    ),
    RegisterDefinition(
        address=96,
        canonical_name="battery_parallel_count",
        cloud_api_field=None,
        ha_sensor_key="battery_bank_count",
        category=RegisterCategory.BMS,
        description="Number of batteries in parallel.",
    ),
    RegisterDefinition(
        address=97,
        canonical_name="battery_capacity_ah",
        cloud_api_field=None,
        ha_sensor_key=None,
        unit="Ah",
        category=RegisterCategory.BMS,
        description="Battery capacity.",
    ),
    RegisterDefinition(
        address=98,
        canonical_name="battery_current_bms",
        cloud_api_field=None,
        ha_sensor_key="battery_current",
        scale=ScaleFactor.DIV_10,
        signed=True,
        unit="A",
        category=RegisterCategory.BMS,
        description="Battery current from BMS (signed, 0.1A resolution).",
    ),
    RegisterDefinition(
        address=99,
        canonical_name="bms_fault_code",
        cloud_api_field=None,
        ha_sensor_key=None,
        category=RegisterCategory.FAULT,
        description="BMS fault code.",
    ),
    RegisterDefinition(
        address=100,
        canonical_name="bms_warning_code",
        cloud_api_field=None,
        ha_sensor_key=None,
        category=RegisterCategory.FAULT,
        description="BMS warning code.",
    ),
    RegisterDefinition(
        address=101,
        canonical_name="bms_max_cell_voltage",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_1000,
        unit="V",
        category=RegisterCategory.BMS,
        description="Maximum cell voltage (millivolts).",
    ),
    RegisterDefinition(
        address=102,
        canonical_name="bms_min_cell_voltage",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_1000,
        unit="V",
        category=RegisterCategory.BMS,
        description="Minimum cell voltage (millivolts).",
    ),
    RegisterDefinition(
        address=103,
        canonical_name="bms_max_cell_temperature",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        signed=True,
        unit="°C",
        category=RegisterCategory.BMS,
        description="Maximum cell temperature (signed, 0.1°C).",
    ),
    RegisterDefinition(
        address=104,
        canonical_name="bms_min_cell_temperature",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        signed=True,
        unit="°C",
        category=RegisterCategory.BMS,
        description="Minimum cell temperature (signed, 0.1°C).",
    ),
    RegisterDefinition(
        address=105,
        canonical_name="bms_fw_update_state",
        cloud_api_field=None,
        ha_sensor_key=None,
        category=RegisterCategory.BMS,
        description="Bits 0-2: BMS FW update (1=upgrading, 2=ok, 3=fail). Bit 4: Gen dry contact.",
    ),
    RegisterDefinition(
        address=106,
        canonical_name="bms_cycle_count",
        cloud_api_field=None,
        ha_sensor_key=None,
        category=RegisterCategory.BMS,
        description="Charge/discharge cycle count.",
    ),
    RegisterDefinition(
        address=107,
        canonical_name="battery_voltage_inv_sample",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=RegisterCategory.BMS,
        description="Inverter-sampled battery voltage.",
    ),
    # =========================================================================
    # ADDITIONAL TEMPERATURE SENSORS (regs 108-112)
    # =========================================================================
    RegisterDefinition(
        address=108,
        canonical_name="temperature_t1",
        cloud_api_field=None,
        ha_sensor_key="bt_temperature",
        scale=ScaleFactor.DIV_10,
        unit="°C",
        category=RegisterCategory.TEMPERATURE,
        description="Temperature sensor T1 (BT/board temp on 12K models).",
    ),
    RegisterDefinition(
        address=109,
        canonical_name="temperature_t2",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        unit="°C",
        category=RegisterCategory.TEMPERATURE,
        description="Temperature sensor T2 (reserved).",
    ),
    RegisterDefinition(
        address=110,
        canonical_name="temperature_t3",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        unit="°C",
        category=RegisterCategory.TEMPERATURE,
        description="Temperature sensor T3 (reserved).",
    ),
    RegisterDefinition(
        address=111,
        canonical_name="temperature_t4",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        unit="°C",
        category=RegisterCategory.TEMPERATURE,
        description="Temperature sensor T4 (reserved).",
    ),
    RegisterDefinition(
        address=112,
        canonical_name="temperature_t5",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        unit="°C",
        category=RegisterCategory.TEMPERATURE,
        description="Temperature sensor T5 (reserved).",
    ),
    # =========================================================================
    # PARALLEL CONFIGURATION (reg 113)
    # =========================================================================
    RegisterDefinition(
        address=113,
        canonical_name="parallel_config",
        cloud_api_field=None,
        ha_sensor_key=None,
        category=RegisterCategory.PARALLEL,
        description="Packed: bits 0-1 master/slave, bits 2-3 phase, bits 8-15 parallel num.",
        packed="b0-1=role,b2-3=phase,b8-15=parallel_num",
    ),
    # =========================================================================
    # GENERATOR INPUT (regs 121-126)
    # =========================================================================
    RegisterDefinition(
        address=121,
        canonical_name="generator_voltage",
        cloud_api_field="genVolt",
        ha_sensor_key="generator_voltage",
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=RegisterCategory.GENERATOR,
        description="Generator voltage.",
    ),
    RegisterDefinition(
        address=122,
        canonical_name="generator_frequency",
        cloud_api_field="genFreq",
        ha_sensor_key="generator_frequency",
        scale=ScaleFactor.DIV_100,
        unit="Hz",
        category=RegisterCategory.GENERATOR,
        description="Generator frequency.",
    ),
    RegisterDefinition(
        address=123,
        canonical_name="generator_power",
        cloud_api_field="genPower",
        ha_sensor_key="generator_power",
        unit="W",
        category=RegisterCategory.GENERATOR,
        description="Generator power.",
    ),
    RegisterDefinition(
        address=124,
        canonical_name="generator_energy_today",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_DAILY,
        description="Generator energy today (Egen_day).",
    ),
    RegisterDefinition(
        address=125,
        canonical_name="generator_energy_total",
        cloud_api_field=None,
        ha_sensor_key=None,
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_LIFETIME,
        description="Generator cumulative energy (Egen_all, 32-bit).",
    ),
    # =========================================================================
    # SPLIT-PHASE EPS L1/L2 (regs 127-138) — US models
    # =========================================================================
    RegisterDefinition(
        address=127,
        canonical_name="eps_l1_voltage",
        cloud_api_field=None,
        ha_sensor_key="eps_voltage_l1",
        scale=ScaleFactor.DIV_10,
        unit="V",
        models=ALL,
        description="EPS L1-N voltage (~120V leg). 3-phase: S-phase gen voltage.",
    ),
    RegisterDefinition(
        address=128,
        canonical_name="eps_l2_voltage",
        cloud_api_field=None,
        ha_sensor_key="eps_voltage_l2",
        scale=ScaleFactor.DIV_10,
        unit="V",
        models=ALL,
        description="EPS L2-N voltage (~120V leg). 3-phase: T-phase gen voltage.",
    ),
    RegisterDefinition(
        address=129,
        canonical_name="eps_l1_power",
        cloud_api_field="pEpsL1N",
        ha_sensor_key=None,
        unit="W",
        models=ALL,
        description="EPS L1N active power. 3-phase: S-phase off-grid active.",
    ),
    RegisterDefinition(
        address=130,
        canonical_name="eps_l2_power",
        cloud_api_field="pEpsL2N",
        ha_sensor_key=None,
        unit="W",
        models=ALL,
        description="EPS L2N active power. 3-phase: T-phase off-grid active.",
    ),
    RegisterDefinition(
        address=131,
        canonical_name="eps_l1_apparent_power",
        cloud_api_field=None,
        ha_sensor_key=None,
        unit="VA",
        models=ALL,
        description="EPS L1N apparent power.",
    ),
    RegisterDefinition(
        address=132,
        canonical_name="eps_l2_apparent_power",
        cloud_api_field=None,
        ha_sensor_key=None,
        unit="VA",
        models=ALL,
        description="EPS L2N apparent power.",
    ),
    # =========================================================================
    # OUTPUT POWER (reg 170) — split-phase total
    # =========================================================================
    RegisterDefinition(
        address=170,
        canonical_name="output_power",
        cloud_api_field="consumptionPower114",
        ha_sensor_key="output_power",
        signed=True,
        unit="W",
        description="Total output power (on-grid load, split-phase systems).",
    ),
    # =========================================================================
    # LOAD ENERGY (regs 171-173) — from Luxpower extended regs
    # =========================================================================
    RegisterDefinition(
        address=171,
        canonical_name="load_energy_today",
        cloud_api_field=None,
        ha_sensor_key=None,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_DAILY,
        description="Load energy today (Eload_day).",
    ),
    RegisterDefinition(
        address=172,
        canonical_name="load_energy_total",
        cloud_api_field=None,
        ha_sensor_key=None,
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_LIFETIME,
        description="Load cumulative energy (Eload_all, 32-bit).",
    ),
    # =========================================================================
    # THREE-PHASE S/T CURRENTS (regs 190-191) — LXP only
    # =========================================================================
    RegisterDefinition(
        address=190,
        canonical_name="inverter_rms_current_s",
        cloud_api_field=None,
        ha_sensor_key="grid_current_l2",
        scale=ScaleFactor.DIV_100,
        unit="A",
        models=LXP_ONLY,
        description="Inverter RMS current, S/L2 phase (LXP three-phase only).",
    ),
    RegisterDefinition(
        address=191,
        canonical_name="inverter_rms_current_t",
        cloud_api_field=None,
        ha_sensor_key="grid_current_l3",
        scale=ScaleFactor.DIV_100,
        unit="A",
        models=LXP_ONLY,
        description="Inverter RMS current, T/L3 phase (LXP three-phase only).",
    ),
    # =========================================================================
    # US SPLIT-PHASE GRID VOLTAGES (regs 193-196) — all models
    # =========================================================================
    RegisterDefinition(
        address=193,
        canonical_name="grid_l1_voltage",
        cloud_api_field=None,
        ha_sensor_key="grid_voltage_l1",
        scale=ScaleFactor.DIV_10,
        unit="V",
        models=ALL,
        description="Grid L1-N voltage (~120V, US split-phase).",
    ),
    RegisterDefinition(
        address=194,
        canonical_name="grid_l2_voltage",
        cloud_api_field=None,
        ha_sensor_key="grid_voltage_l2",
        scale=ScaleFactor.DIV_10,
        unit="V",
        models=ALL,
        description="Grid L2-N voltage (~120V, US split-phase).",
    ),
    # =========================================================================
    # QUICK CHARGE REMAINING (reg 210)
    # =========================================================================
    RegisterDefinition(
        address=210,
        canonical_name="quick_charge_remaining_seconds",
        cloud_api_field=None,
        ha_sensor_key=None,
        unit="s",
        description="Quick charge remaining time in seconds.",
    ),
    # =========================================================================
    # SMART LOAD POWER (reg 232) — Luxpower extended
    # =========================================================================
    RegisterDefinition(
        address=232,
        canonical_name="smart_load_power",
        cloud_api_field=None,
        ha_sensor_key=None,
        unit="W",
        description="Smart load output power.",
    ),
)


# =============================================================================
# LOOKUP INDEXES (built once at import time)
# =============================================================================

# canonical_name → RegisterDefinition
BY_NAME: dict[str, RegisterDefinition] = {r.canonical_name: r for r in INVERTER_INPUT_REGISTERS}

# address → RegisterDefinition
BY_ADDRESS: dict[int, RegisterDefinition] = {r.address: r for r in INVERTER_INPUT_REGISTERS}

# cloud_api_field → RegisterDefinition (only entries with cloud mapping)
BY_CLOUD_FIELD: dict[str, RegisterDefinition] = {
    r.cloud_api_field: r for r in INVERTER_INPUT_REGISTERS if r.cloud_api_field is not None
}

# ha_sensor_key → RegisterDefinition (only entries with HA mapping)
BY_SENSOR_KEY: dict[str, RegisterDefinition] = {
    r.ha_sensor_key: r for r in INVERTER_INPUT_REGISTERS if r.ha_sensor_key is not None
}

# Category → tuple of RegisterDefinitions
BY_CATEGORY: dict[RegisterCategory, tuple[RegisterDefinition, ...]] = {}
for _reg in INVERTER_INPUT_REGISTERS:
    BY_CATEGORY.setdefault(_reg.category, ())
    BY_CATEGORY[_reg.category] = (*BY_CATEGORY[_reg.category], _reg)


def registers_for_model(family: str) -> tuple[RegisterDefinition, ...]:
    """Return only registers supported by the given InverterFamily value."""
    return tuple(r for r in INVERTER_INPUT_REGISTERS if family in r.models)


def sensor_keys_for_model(family: str) -> frozenset[str]:
    """Return the set of HA sensor keys available for the given model family."""
    return frozenset(
        r.ha_sensor_key
        for r in INVERTER_INPUT_REGISTERS
        if r.ha_sensor_key is not None and family in r.models
    )
