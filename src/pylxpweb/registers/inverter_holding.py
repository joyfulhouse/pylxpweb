"""Canonical inverter holding register map.

Single source of truth for ALL inverter holding registers (function code 0x03).
These are configuration parameters that can be read and written via Modbus.

Cross-validated against:
  - EG4-18KPV-12LV Modbus Protocol specification (holding registers 0-202)
  - Luxpower Modbus RTU Protocol (Table 8 Holding Register Mapping)
  - Live API testing on 18KPV hardware (REGISTER_TO_PARAM_KEYS, 2026-01-27)
  - EG4-Inverter-Modbus project (poldim) and eg4-modbus-monitor (galets)

Each HoldingRegisterDefinition carries:
  register address → scale/signed/min/max → canonical name → API param key → HA entity key

Two types of entries:
  - Value registers: bit_position=None, full 16-bit (or 32-bit) value with scale/min/max.
  - Bitfield entries: bit_position=0-15, single boolean bit within a bitfield register.
    Multiple bitfield entries share the same address.

The `api_param_key` field matches the HOLD_* or FUNC_* strings returned by the
cloud API and local Modbus parameter reads.  These are the keys used by pylxpweb's
parameter dict and the HA integration's number/switch entities.

Verified API param keys are from live 18KPV testing.  Unverified keys are derived
from documentation and follow the same HOLD_* naming convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pylxpweb.registers.inverter_input import ALL, ScaleFactor


class HoldingCategory(StrEnum):
    """Logical grouping for holding register parameters."""

    SYSTEM = "system"
    FUNCTION = "function"
    GRID = "grid"
    POWER = "power"
    BATTERY = "battery"
    SCHEDULE = "schedule"
    GENERATOR = "generator"
    REACTIVE = "reactive"
    OUTPUT = "output"


@dataclass(frozen=True)
class HoldingRegisterDefinition:
    """Single holding register parameter definition.

    For value registers: bit_position is None, address is the Modbus register.
    For bitfield entries: bit_position is 0-15 within the register at address.
      Multiple bitfield entries share the same address.

    Attributes:
        address: Modbus holding register address (function code 0x03).
        canonical_name: Stable API name.  Once published, MUST NOT change.
        api_param_key: The HOLD_* or FUNC_* key used by the cloud/local API.
            This is the key in pylxpweb's parameter dict.
        ha_entity_key: Home Assistant entity key (number/switch/select).
            None if not exposed as an HA entity.
        bit_position: For bitfield entries, the bit index (0-15).
            None for value registers.
        bit_width: 16 (single register) or 32 (register pair, low word first).
        scale: Divisor to convert raw value to engineering units.
        signed: True for two's-complement signed values.
        unit: Engineering unit string.
        min_value: Minimum allowed value (after scaling).  None if unconstrained.
        max_value: Maximum allowed value (after scaling).  None if unconstrained.
        writable: False for read-only holding registers (versions, serial).
        category: Logical grouping for UI organisation and read scheduling.
        models: Which InverterFamily values support this register.
        description: Human-readable description.
    """

    address: int
    canonical_name: str
    api_param_key: str
    ha_entity_key: str | None = None
    bit_position: int | None = None
    bit_width: int = 16
    scale: ScaleFactor = ScaleFactor.NONE
    signed: bool = False
    unit: str = ""
    min_value: float | None = None
    max_value: float | None = None
    writable: bool = True
    category: HoldingCategory = HoldingCategory.POWER
    models: frozenset[str] = ALL
    description: str = ""


# =============================================================================
# INVERTER HOLDING REGISTERS (Function Code 0x03, Read/Write)
# =============================================================================
# Organised by logical section.  Bitfield registers list every verified bit.
# API param keys marked (verified) were confirmed via live 18KPV testing.

INVERTER_HOLDING_REGISTERS: tuple[HoldingRegisterDefinition, ...] = (
    # =========================================================================
    # SYSTEM INFORMATION (regs 9-10, read-only)
    # =========================================================================
    HoldingRegisterDefinition(
        address=9,
        canonical_name="com_protocol_version",
        api_param_key="HOLD_COM_VERSION",
        writable=False,
        category=HoldingCategory.SYSTEM,
        description="Communication protocol version.",
    ),
    HoldingRegisterDefinition(
        address=10,
        canonical_name="controller_version",
        api_param_key="HOLD_CONTROLLER_VERSION",
        writable=False,
        category=HoldingCategory.SYSTEM,
        description="Controller firmware version.",
    ),
    # =========================================================================
    # COMMUNICATION (regs 15-16, 19)
    # =========================================================================
    HoldingRegisterDefinition(
        address=15,
        canonical_name="modbus_address",
        api_param_key="HOLD_COM_ADDR",  # verified
        min_value=1,
        max_value=247,
        category=HoldingCategory.SYSTEM,
        description="Modbus RTU slave address.",
    ),
    HoldingRegisterDefinition(
        address=16,
        canonical_name="language",
        api_param_key="HOLD_LANGUAGE",  # verified
        min_value=0,
        max_value=1,
        category=HoldingCategory.SYSTEM,
        description="Display language. 0=English, 1=German/Chinese.",
    ),
    HoldingRegisterDefinition(
        address=19,
        canonical_name="device_type_code",
        api_param_key="HOLD_DEVICE_TYPE_CODE",  # verified
        writable=False,
        category=HoldingCategory.SYSTEM,
        description="Device type identification code. MID/GridBOSS=50.",
    ),
    # =========================================================================
    # PV CONFIGURATION (reg 20, reg 22 value interpretation)
    # =========================================================================
    HoldingRegisterDefinition(
        address=20,
        canonical_name="pv_input_mode",
        api_param_key="HOLD_PV_INPUT_MODE",  # verified
        min_value=0,
        max_value=7,
        category=HoldingCategory.OUTPUT,
        description="PV input connection model (0-7, model-dependent).",
    ),
    HoldingRegisterDefinition(
        address=22,
        canonical_name="pv_start_voltage",
        api_param_key="HOLD_START_PV_VOLT",
        scale=ScaleFactor.DIV_10,
        unit="V",
        min_value=90.0,
        max_value=500.0,
        category=HoldingCategory.OUTPUT,
        description="PV start-up voltage.  Note: reg 22 also carries LSP function bits.",
    ),
    # =========================================================================
    # FUNCTION ENABLE BITFIELD — Register 21 (16 bits, verified 100%)
    # =========================================================================
    # Critical control register for EPS, AC charge, forced charge/discharge.
    HoldingRegisterDefinition(
        address=21,
        bit_position=0,
        canonical_name="eps_enable",
        api_param_key="FUNC_EPS_EN",  # verified
        ha_entity_key="battery_backup",
        category=HoldingCategory.FUNCTION,
        description="EPS/off-grid mode enable (Battery Backup).",
    ),
    HoldingRegisterDefinition(
        address=21,
        bit_position=1,
        canonical_name="overload_derate_enable",
        api_param_key="FUNC_OVF_LOAD_DERATE_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="Overload/overfrequency load derate enable.",
    ),
    HoldingRegisterDefinition(
        address=21,
        bit_position=2,
        canonical_name="drms_enable",
        api_param_key="FUNC_DRMS_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="Demand Response Management System enable.",
    ),
    HoldingRegisterDefinition(
        address=21,
        bit_position=3,
        canonical_name="lvrt_enable",
        api_param_key="FUNC_LVRT_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="Low voltage ride-through enable.",
    ),
    HoldingRegisterDefinition(
        address=21,
        bit_position=4,
        canonical_name="anti_island_enable",
        api_param_key="FUNC_ANTI_ISLAND_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="Anti-islanding protection enable.",
    ),
    HoldingRegisterDefinition(
        address=21,
        bit_position=5,
        canonical_name="neutral_detect_enable",
        api_param_key="FUNC_NEUTRAL_DETECT_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="Neutral line detection enable.",
    ),
    HoldingRegisterDefinition(
        address=21,
        bit_position=6,
        canonical_name="grid_on_power_soft_start",
        api_param_key="FUNC_GRID_ON_POWER_SS_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="Grid-on power soft start enable.",
    ),
    HoldingRegisterDefinition(
        address=21,
        bit_position=7,
        canonical_name="ac_charge_enable",
        api_param_key="FUNC_AC_CHARGE",  # verified
        ha_entity_key="ac_charge",
        category=HoldingCategory.FUNCTION,
        description="AC (grid) charging enable.",
    ),
    HoldingRegisterDefinition(
        address=21,
        bit_position=8,
        canonical_name="seamless_switching_enable",
        api_param_key="FUNC_SW_SEAMLESSLY_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="Seamless grid/off-grid switching enable.",
    ),
    HoldingRegisterDefinition(
        address=21,
        bit_position=9,
        canonical_name="power_on",
        api_param_key="FUNC_SET_TO_STANDBY",  # verified
        category=HoldingCategory.FUNCTION,
        description="Power on control. 0=Standby, 1=Power On.",
    ),
    HoldingRegisterDefinition(
        address=21,
        bit_position=10,
        canonical_name="forced_discharge_enable",
        api_param_key="FUNC_FORCED_DISCHG_EN",  # verified
        ha_entity_key="forced_discharge",
        category=HoldingCategory.FUNCTION,
        description="Forced battery discharge enable.",
    ),
    HoldingRegisterDefinition(
        address=21,
        bit_position=11,
        canonical_name="forced_charge_enable",
        api_param_key="FUNC_FORCED_CHG_EN",  # verified
        ha_entity_key="pv_charge_priority",
        category=HoldingCategory.FUNCTION,
        description="Forced PV charge enable (PV Charge Priority in HA).",
    ),
    HoldingRegisterDefinition(
        address=21,
        bit_position=12,
        canonical_name="isolation_detect_enable",
        api_param_key="FUNC_ISO_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="PV isolation detection enable.",
    ),
    HoldingRegisterDefinition(
        address=21,
        bit_position=13,
        canonical_name="gfci_enable",
        api_param_key="FUNC_GFCI_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="Ground fault circuit interrupter enable.",
    ),
    HoldingRegisterDefinition(
        address=21,
        bit_position=14,
        canonical_name="dci_enable",
        api_param_key="FUNC_DCI_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="DC injection detection enable.",
    ),
    HoldingRegisterDefinition(
        address=21,
        bit_position=15,
        canonical_name="feed_in_grid_enable",
        api_param_key="FUNC_FEED_IN_GRID_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="Feed-in (export) to grid enable.",
    ),
    # =========================================================================
    # LSP FUNCTION BITFIELD — Register 22 (11 bits, verified 9/11)
    # =========================================================================
    # Note: Register 22 also carries the PV start voltage as a value.
    # These bits may overlay voltage bits on some firmware versions.
    HoldingRegisterDefinition(
        address=22,
        bit_position=0,
        canonical_name="lsp_standby",
        api_param_key="FUNC_LSP_SET_TO_STANDBY",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP standby mode enable.",
    ),
    HoldingRegisterDefinition(
        address=22,
        bit_position=1,
        canonical_name="lsp_isolation_enable",
        api_param_key="FUNC_LSP_ISO_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP isolation detection enable.",
    ),
    HoldingRegisterDefinition(
        address=22,
        bit_position=2,
        canonical_name="lsp_fan_check_enable",
        api_param_key="FUNC_LSP_FAN_CHECK_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP fan check enable.",
    ),
    HoldingRegisterDefinition(
        address=22,
        bit_position=3,
        canonical_name="lsp_whole_day_schedule_enable",
        api_param_key="FUNC_LSP_WHOLE_DAY_SCHEDULE_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP whole-day time-of-use schedule enable.",
    ),
    HoldingRegisterDefinition(
        address=22,
        bit_position=4,
        canonical_name="lsp_lcd_remote_discharge_enable",
        api_param_key="FUNC_LSP_LCD_REMOTE_DIS_CHG_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP LCD remote discharge control enable.",
    ),
    HoldingRegisterDefinition(
        address=22,
        bit_position=5,
        canonical_name="lsp_self_consumption_enable",
        api_param_key="FUNC_LSP_SELF_CONSUMPTION_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP self-consumption mode enable.",
    ),
    HoldingRegisterDefinition(
        address=22,
        bit_position=6,
        canonical_name="lsp_ac_charge_enable",
        api_param_key="FUNC_LSP_AC_CHARGE",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP AC charge enable (separate from FUNC_AC_CHARGE in reg 21).",
    ),
    HoldingRegisterDefinition(
        address=22,
        bit_position=7,
        canonical_name="lsp_battery_activation_enable",
        api_param_key="FUNC_LSP_BAT_ACTIVATION_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP battery activation enable.",
    ),
    HoldingRegisterDefinition(
        address=22,
        bit_position=8,
        canonical_name="lsp_bypass_mode_enable",
        api_param_key="FUNC_LSP_BYPASS_MODE_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP bypass mode enable.",
    ),
    HoldingRegisterDefinition(
        address=22,
        bit_position=9,
        canonical_name="lsp_bypass_enable",
        api_param_key="FUNC_LSP_BYPASS_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP bypass enable.",
    ),
    HoldingRegisterDefinition(
        address=22,
        bit_position=10,
        canonical_name="lsp_charge_priority_enable",
        api_param_key="FUNC_LSP_CHARGE_PRIORITY_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP charge priority enable.",
    ),
    # =========================================================================
    # GRID CONNECTION TIMING (regs 23-24)
    # =========================================================================
    HoldingRegisterDefinition(
        address=23,
        canonical_name="grid_connection_wait_time",
        api_param_key="HOLD_CONNECT_TIME",  # verified
        unit="s",
        min_value=30,
        max_value=600,
        category=HoldingCategory.GRID,
        description="Grid connection wait time after power-up.",
    ),
    HoldingRegisterDefinition(
        address=24,
        canonical_name="grid_reconnection_wait_time",
        api_param_key="HOLD_RECONNECT_TIME",  # verified
        unit="s",
        min_value=0,
        max_value=900,
        category=HoldingCategory.GRID,
        description="Grid reconnection wait time after fault.",
    ),
    # =========================================================================
    # GRID VOLTAGE / FREQUENCY PROTECTION (regs 25, 27-28)
    # =========================================================================
    HoldingRegisterDefinition(
        address=25,
        canonical_name="grid_voltage_connection_low",
        api_param_key="HOLD_GRID_VOLT_CONN_LOW",  # verified
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=HoldingCategory.GRID,
        description="Grid voltage connection low limit.",
    ),
    HoldingRegisterDefinition(
        address=27,
        canonical_name="grid_frequency_connection_low",
        api_param_key="HOLD_GRID_FREQ_CONN_LOW",  # verified
        scale=ScaleFactor.DIV_100,
        unit="Hz",
        category=HoldingCategory.GRID,
        description="Grid frequency connection low limit.",
    ),
    HoldingRegisterDefinition(
        address=28,
        canonical_name="grid_frequency_connection_high",
        api_param_key="HOLD_GRID_FREQ_CONN_HIGH",  # verified
        scale=ScaleFactor.DIV_100,
        unit="Hz",
        category=HoldingCategory.GRID,
        description="Grid frequency connection high limit.",
    ),
    # =========================================================================
    # LSP WHOLE-DAY SCHEDULE BITFIELD — Register 26 (10 bits, verified)
    # =========================================================================
    HoldingRegisterDefinition(
        address=26,
        bit_position=0,
        canonical_name="lsp_whole_bypass_1_enable",
        api_param_key="FUNC_LSP_WHOLE_BYPASS_1_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP whole-day bypass period 1 enable.",
    ),
    HoldingRegisterDefinition(
        address=26,
        bit_position=1,
        canonical_name="lsp_whole_bypass_2_enable",
        api_param_key="FUNC_LSP_WHOLE_BYPASS_2_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP whole-day bypass period 2 enable.",
    ),
    HoldingRegisterDefinition(
        address=26,
        bit_position=2,
        canonical_name="lsp_whole_bypass_3_enable",
        api_param_key="FUNC_LSP_WHOLE_BYPASS_3_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP whole-day bypass period 3 enable.",
    ),
    HoldingRegisterDefinition(
        address=26,
        bit_position=3,
        canonical_name="lsp_whole_battery_first_1_enable",
        api_param_key="FUNC_LSP_WHOLE_BAT_FIRST_1_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP whole-day battery-first period 1 enable.",
    ),
    HoldingRegisterDefinition(
        address=26,
        bit_position=4,
        canonical_name="lsp_whole_battery_first_2_enable",
        api_param_key="FUNC_LSP_WHOLE_BAT_FIRST_2_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP whole-day battery-first period 2 enable.",
    ),
    HoldingRegisterDefinition(
        address=26,
        bit_position=5,
        canonical_name="lsp_whole_battery_first_3_enable",
        api_param_key="FUNC_LSP_WHOLE_BAT_FIRST_3_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP whole-day battery-first period 3 enable.",
    ),
    HoldingRegisterDefinition(
        address=26,
        bit_position=6,
        canonical_name="lsp_whole_self_consumption_1_enable",
        api_param_key="FUNC_LSP_WHOLE_SELF_CONSUMPTION_1_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP whole-day self-consumption period 1 enable.",
    ),
    HoldingRegisterDefinition(
        address=26,
        bit_position=7,
        canonical_name="lsp_whole_self_consumption_2_enable",
        api_param_key="FUNC_LSP_WHOLE_SELF_CONSUMPTION_2_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP whole-day self-consumption period 2 enable.",
    ),
    HoldingRegisterDefinition(
        address=26,
        bit_position=8,
        canonical_name="lsp_whole_self_consumption_3_enable",
        api_param_key="FUNC_LSP_WHOLE_SELF_CONSUMPTION_3_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP whole-day self-consumption period 3 enable.",
    ),
    HoldingRegisterDefinition(
        address=26,
        bit_position=9,
        canonical_name="lsp_battery_volt_or_soc",
        api_param_key="FUNC_LSP_BATT_VOLT_OR_SOC",  # verified
        category=HoldingCategory.FUNCTION,
        description="LSP battery control mode. 0=voltage, 1=SOC.",
    ),
    # =========================================================================
    # REACTIVE POWER CONTROL (regs 59-62)
    # =========================================================================
    HoldingRegisterDefinition(
        address=59,
        canonical_name="reactive_power_mode",
        api_param_key="HOLD_Q_MODE",
        min_value=0,
        max_value=4,
        category=HoldingCategory.REACTIVE,
        description="Reactive power control mode (0-4).",
    ),
    HoldingRegisterDefinition(
        address=60,
        canonical_name="reactive_power_pv_mode",
        api_param_key="HOLD_Q_PV_MODE",
        min_value=0,
        max_value=4,
        category=HoldingCategory.REACTIVE,
        description="PV reactive power control mode (0-4).",
    ),
    HoldingRegisterDefinition(
        address=61,
        canonical_name="reactive_power_setting",
        api_param_key="HOLD_Q_POWER",
        signed=True,
        unit="%",
        min_value=-100,
        max_value=100,
        category=HoldingCategory.REACTIVE,
        description="Reactive power percentage setting.",
    ),
    HoldingRegisterDefinition(
        address=62,
        canonical_name="reactive_power_pv_setting",
        api_param_key="HOLD_Q_PV_POWER",
        signed=True,
        unit="%",
        min_value=-100,
        max_value=100,
        category=HoldingCategory.REACTIVE,
        description="PV reactive power percentage setting.",
    ),
    # =========================================================================
    # POWER CONTROL (regs 64-67)
    # =========================================================================
    HoldingRegisterDefinition(
        address=64,
        canonical_name="charge_power_percent",
        api_param_key="HOLD_CHG_POWER_PERCENT_CMD",  # verified
        ha_entity_key="pv_charge_power",
        unit="%",
        min_value=0,
        max_value=100,
        category=HoldingCategory.POWER,
        description="PV/battery charge power percentage.",
    ),
    HoldingRegisterDefinition(
        address=65,
        canonical_name="discharge_power_percent",
        api_param_key="HOLD_DISCHG_POWER_PERCENT_CMD",  # verified
        unit="%",
        min_value=0,
        max_value=100,
        category=HoldingCategory.POWER,
        description="Battery discharge power percentage.",
    ),
    HoldingRegisterDefinition(
        address=66,
        canonical_name="ac_charge_power",
        api_param_key="HOLD_AC_CHARGE_POWER_CMD",  # verified
        ha_entity_key="ac_charge_power",
        unit="W",
        min_value=0,
        max_value=15000,
        category=HoldingCategory.POWER,
        description="AC charge power. Raw value in 100W units (0-150 = 0-15kW).",
    ),
    HoldingRegisterDefinition(
        address=67,
        canonical_name="ac_charge_soc_limit",
        api_param_key="HOLD_AC_CHARGE_SOC_LIMIT",  # verified
        ha_entity_key="ac_charge_soc_limit",
        unit="%",
        min_value=0,
        max_value=100,
        category=HoldingCategory.POWER,
        description="AC charge SOC limit — stop AC charging when SOC reaches this.",
    ),
    # =========================================================================
    # AC CHARGE SCHEDULE (regs 68-73)
    # =========================================================================
    HoldingRegisterDefinition(
        address=68,
        canonical_name="ac_charge_start_hour_1",
        api_param_key="HOLD_AC_CHARGE_START_HOUR_1",
        min_value=0,
        max_value=23,
        category=HoldingCategory.SCHEDULE,
        description="AC charge time period 1 start hour.",
    ),
    HoldingRegisterDefinition(
        address=69,
        canonical_name="ac_charge_start_minute_1",
        api_param_key="HOLD_AC_CHARGE_START_MINUTE_1",
        min_value=0,
        max_value=59,
        category=HoldingCategory.SCHEDULE,
        description="AC charge time period 1 start minute.",
    ),
    HoldingRegisterDefinition(
        address=70,
        canonical_name="ac_charge_end_hour_1",
        api_param_key="HOLD_AC_CHARGE_END_HOUR_1",
        min_value=0,
        max_value=23,
        category=HoldingCategory.SCHEDULE,
        description="AC charge time period 1 end hour.",
    ),
    HoldingRegisterDefinition(
        address=71,
        canonical_name="ac_charge_end_minute_1",
        api_param_key="HOLD_AC_CHARGE_END_MINUTE_1",
        min_value=0,
        max_value=59,
        category=HoldingCategory.SCHEDULE,
        description="AC charge time period 1 end minute.",
    ),
    HoldingRegisterDefinition(
        address=72,
        canonical_name="ac_charge_enable_period_1",
        api_param_key="HOLD_AC_CHARGE_ENABLE_1",
        min_value=0,
        max_value=1,
        category=HoldingCategory.SCHEDULE,
        description="AC charge time period 1 enable. 0=Off, 1=On.",
    ),
    HoldingRegisterDefinition(
        address=73,
        canonical_name="ac_charge_enable_period_2",
        api_param_key="HOLD_AC_CHARGE_ENABLE_2",
        min_value=0,
        max_value=1,
        category=HoldingCategory.SCHEDULE,
        description="AC charge time period 2 enable. 0=Off, 1=On.",
    ),
    # =========================================================================
    # FORCED CHARGE (ChgFirst / PV Charge Priority) (regs 74-81)
    # Per EG4-18KPV Modbus PDF, regs 74-81 are "Charging Priority" (ChgFirst).
    # =========================================================================
    HoldingRegisterDefinition(
        address=74,
        canonical_name="forced_charge_power_command",
        api_param_key="HOLD_FORCED_CHG_POWER_CMD",
        unit="%",
        min_value=0,
        max_value=100,
        category=HoldingCategory.SCHEDULE,
        description="Forced charge power command percentage.",
    ),
    HoldingRegisterDefinition(
        address=75,
        canonical_name="forced_charge_soc_limit",
        api_param_key="HOLD_FORCED_CHG_SOC_LIMIT",
        unit="%",
        min_value=0,
        max_value=100,
        category=HoldingCategory.SCHEDULE,
        description="Forced charge SOC limit.",
    ),
    HoldingRegisterDefinition(
        address=76,
        canonical_name="forced_charge_time_0_start",
        api_param_key="HOLD_FORCED_CHARGE_TIME_0_START",
        category=HoldingCategory.SCHEDULE,
        description="Forced charge period 0 start (packed hour|minute).",
    ),
    HoldingRegisterDefinition(
        address=77,
        canonical_name="forced_charge_time_0_end",
        api_param_key="HOLD_FORCED_CHARGE_TIME_0_END",
        category=HoldingCategory.SCHEDULE,
        description="Forced charge period 0 end (packed hour|minute).",
    ),
    HoldingRegisterDefinition(
        address=78,
        canonical_name="forced_charge_time_1_start",
        api_param_key="HOLD_FORCED_CHARGE_TIME_1_START",
        category=HoldingCategory.SCHEDULE,
        description="Forced charge period 1 start (packed hour|minute).",
    ),
    HoldingRegisterDefinition(
        address=79,
        canonical_name="forced_charge_time_1_end",
        api_param_key="HOLD_FORCED_CHARGE_TIME_1_END",
        category=HoldingCategory.SCHEDULE,
        description="Forced charge period 1 end (packed hour|minute).",
    ),
    HoldingRegisterDefinition(
        address=80,
        canonical_name="forced_charge_time_2_start",
        api_param_key="HOLD_FORCED_CHARGE_TIME_2_START",
        category=HoldingCategory.SCHEDULE,
        description="Forced charge period 2 start (packed hour|minute).",
    ),
    HoldingRegisterDefinition(
        address=81,
        canonical_name="forced_charge_time_2_end",
        api_param_key="HOLD_FORCED_CHARGE_TIME_2_END",
        category=HoldingCategory.SCHEDULE,
        description="Forced charge period 2 end (packed hour|minute).",
    ),
    # =========================================================================
    # FORCED DISCHARGE (regs 82-89)
    # =========================================================================
    HoldingRegisterDefinition(
        address=82,
        canonical_name="forced_discharge_power_command",
        api_param_key="HOLD_FORCED_DISCHG_POWER_CMD",
        unit="%",
        min_value=0,
        max_value=100,
        category=HoldingCategory.SCHEDULE,
        description="Forced discharge power command percentage.",
    ),
    HoldingRegisterDefinition(
        address=83,
        canonical_name="forced_discharge_soc_limit",
        api_param_key="HOLD_FORCED_DISCHG_SOC_LIMIT",
        unit="%",
        min_value=0,
        max_value=100,
        category=HoldingCategory.SCHEDULE,
        description="Forced discharge SOC limit.",
    ),
    HoldingRegisterDefinition(
        address=84,
        canonical_name="forced_discharge_time_0_start",
        api_param_key="HOLD_FORCED_DISCHARGE_TIME_0_START",
        category=HoldingCategory.SCHEDULE,
        description="Forced discharge period 0 start (packed hour|minute).",
    ),
    HoldingRegisterDefinition(
        address=85,
        canonical_name="forced_discharge_time_0_end",
        api_param_key="HOLD_FORCED_DISCHARGE_TIME_0_END",
        category=HoldingCategory.SCHEDULE,
        description="Forced discharge period 0 end (packed hour|minute).",
    ),
    HoldingRegisterDefinition(
        address=86,
        canonical_name="forced_discharge_time_1_start",
        api_param_key="HOLD_FORCED_DISCHARGE_TIME_1_START",
        category=HoldingCategory.SCHEDULE,
        description="Forced discharge period 1 start (packed hour|minute).",
    ),
    HoldingRegisterDefinition(
        address=87,
        canonical_name="forced_discharge_time_1_end",
        api_param_key="HOLD_FORCED_DISCHARGE_TIME_1_END",
        category=HoldingCategory.SCHEDULE,
        description="Forced discharge period 1 end (packed hour|minute).",
    ),
    HoldingRegisterDefinition(
        address=88,
        canonical_name="forced_discharge_time_2_start",
        api_param_key="HOLD_FORCED_DISCHARGE_TIME_2_START",
        category=HoldingCategory.SCHEDULE,
        description="Forced discharge period 2 start (packed hour|minute).",
    ),
    HoldingRegisterDefinition(
        address=89,
        canonical_name="forced_discharge_time_2_end",
        api_param_key="HOLD_FORCED_DISCHARGE_TIME_2_END",
        category=HoldingCategory.SCHEDULE,
        description="Forced discharge period 2 end (packed hour|minute).",
    ),
    # =========================================================================
    # INVERTER OUTPUT CONFIGURATION (regs 90-91)
    # =========================================================================
    HoldingRegisterDefinition(
        address=90,
        canonical_name="output_voltage_select",
        api_param_key="HOLD_INVERTER_OUTPUT_VOLTAGE",
        min_value=0,
        max_value=3,
        category=HoldingCategory.OUTPUT,
        description="Inverter output voltage. 0=230V, 1=240V, 2=277V, 3=208V.",
    ),
    HoldingRegisterDefinition(
        address=91,
        canonical_name="output_frequency_select",
        api_param_key="HOLD_INVERTER_OUTPUT_FREQUENCY",
        min_value=0,
        max_value=1,
        category=HoldingCategory.OUTPUT,
        description="Inverter output frequency. 0=50Hz, 1=60Hz.",
    ),
    # =========================================================================
    # BATTERY VOLTAGE / CURRENT LIMITS (regs 99-102)
    # =========================================================================
    HoldingRegisterDefinition(
        address=99,
        canonical_name="charge_voltage_ref",
        api_param_key="HOLD_LEAD_ACID_CHARGE_VOLTAGE_REF",
        scale=ScaleFactor.DIV_10,
        unit="V",
        min_value=50.0,
        max_value=59.0,
        category=HoldingCategory.BATTERY,
        description="Battery charge voltage reference (max charge voltage).",
    ),
    HoldingRegisterDefinition(
        address=100,
        canonical_name="discharge_cutoff_voltage",
        api_param_key="HOLD_LEAD_ACID_DISCHARGE_CUT_OFF_VOLT",  # verified
        scale=ScaleFactor.DIV_10,
        unit="V",
        min_value=40.0,
        max_value=50.0,
        category=HoldingCategory.BATTERY,
        description="Battery discharge cutoff voltage.",
    ),
    HoldingRegisterDefinition(
        address=101,
        canonical_name="charge_current_limit",
        api_param_key="HOLD_LEAD_ACID_CHARGE_RATE",  # verified
        ha_entity_key="charge_current",
        unit="A",
        min_value=0,
        max_value=140,
        category=HoldingCategory.BATTERY,
        description="Maximum battery charge current.",
    ),
    HoldingRegisterDefinition(
        address=102,
        canonical_name="discharge_current_limit",
        api_param_key="HOLD_LEAD_ACID_DISCHARGE_RATE",  # verified
        ha_entity_key="discharge_current",
        unit="A",
        min_value=0,
        max_value=140,
        category=HoldingCategory.BATTERY,
        description="Maximum battery discharge current.",
    ),
    # =========================================================================
    # BACKFLOW / POWER SETTINGS (regs 103, 116, 118-119)
    # =========================================================================
    HoldingRegisterDefinition(
        address=103,
        canonical_name="max_backflow_power_percent",
        api_param_key="HOLD_MAX_BACKFLOW_POWER_PERCENT",
        unit="%",
        min_value=0,
        max_value=100,
        category=HoldingCategory.POWER,
        description="Maximum export (backflow) power percentage.",
    ),
    HoldingRegisterDefinition(
        address=116,
        canonical_name="ptouser_start_discharge",
        api_param_key="HOLD_PTOUSER_START_DISCHARGE",
        unit="W",
        min_value=50,
        max_value=10000,
        category=HoldingCategory.POWER,
        description="Power-to-user threshold to start battery discharge.",
    ),
    HoldingRegisterDefinition(
        address=118,
        canonical_name="voltage_start_derating",
        api_param_key="HOLD_VOLTAGE_START_DERATING",
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=HoldingCategory.POWER,
        description="Voltage threshold to start power derating.",
    ),
    HoldingRegisterDefinition(
        address=119,
        canonical_name="power_offset_wct",
        api_param_key="HOLD_POWER_OFFSET_WCT",
        signed=True,
        unit="W",
        min_value=-1000,
        max_value=1000,
        category=HoldingCategory.POWER,
        description="CT power offset calibration (signed).",
    ),
    # =========================================================================
    # SOC LIMITS (regs 105, 125)
    # =========================================================================
    HoldingRegisterDefinition(
        address=105,
        canonical_name="ongrid_discharge_cutoff_soc",
        api_param_key="HOLD_DISCHG_CUT_OFF_SOC_EOD",  # verified
        ha_entity_key="ongrid_discharge_soc",
        unit="%",
        min_value=10,
        max_value=90,
        category=HoldingCategory.BATTERY,
        description="On-grid end-of-discharge SOC cutoff.",
    ),
    HoldingRegisterDefinition(
        address=125,
        canonical_name="offgrid_discharge_cutoff_soc",
        api_param_key="HOLD_SOC_LOW_LIMIT_EPS_DISCHG",  # verified
        ha_entity_key="offgrid_discharge_soc",
        unit="%",
        min_value=0,
        max_value=100,
        category=HoldingCategory.BATTERY,
        description="Off-grid/EPS discharge SOC low limit.",
    ),
    # =========================================================================
    # SYSTEM FUNCTION BITFIELD — Register 110 (14 bits, verified)
    # =========================================================================
    HoldingRegisterDefinition(
        address=110,
        bit_position=0,
        canonical_name="pv_grid_off_enable",
        api_param_key="FUNC_PV_GRID_OFF_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="PV grid-off enable (disconnect PV when grid lost).",
    ),
    HoldingRegisterDefinition(
        address=110,
        bit_position=1,
        canonical_name="run_without_grid",
        api_param_key="FUNC_RUN_WITHOUT_GRID",  # verified
        category=HoldingCategory.FUNCTION,
        description="Run without grid enable (off-grid capable).",
    ),
    HoldingRegisterDefinition(
        address=110,
        bit_position=2,
        canonical_name="micro_grid_enable",
        api_param_key="FUNC_MICRO_GRID_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="Micro-grid mode enable.",
    ),
    HoldingRegisterDefinition(
        address=110,
        bit_position=3,
        canonical_name="battery_shared",
        api_param_key="FUNC_BAT_SHARED",  # verified
        category=HoldingCategory.FUNCTION,
        description="Battery shared mode (parallel systems).",
    ),
    HoldingRegisterDefinition(
        address=110,
        bit_position=4,
        canonical_name="charge_last",
        api_param_key="FUNC_CHARGE_LAST",  # verified
        category=HoldingCategory.FUNCTION,
        description="Charge last mode — charge battery after loads satisfied.",
    ),
    HoldingRegisterDefinition(
        address=110,
        bit_position=5,
        canonical_name="take_load_together",
        api_param_key="FUNC_TAKE_LOAD_TOGETHER",  # verified
        category=HoldingCategory.FUNCTION,
        description="Take load together mode (parallel load sharing).",
    ),
    HoldingRegisterDefinition(
        address=110,
        bit_position=6,
        canonical_name="buzzer_enable",
        api_param_key="FUNC_BUZZER_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="Audible buzzer enable for alarms.",
    ),
    HoldingRegisterDefinition(
        address=110,
        bit_position=7,
        canonical_name="go_to_offgrid",
        api_param_key="FUNC_GO_TO_OFFGRID",  # verified
        category=HoldingCategory.FUNCTION,
        description="Force transition to off-grid mode.",
    ),
    HoldingRegisterDefinition(
        address=110,
        bit_position=8,
        canonical_name="green_mode_enable",
        api_param_key="FUNC_GREEN_EN",  # verified
        ha_entity_key="green_mode",
        category=HoldingCategory.FUNCTION,
        description="Green/off-grid mode enable (independent from EPS in reg 21).",
    ),
    HoldingRegisterDefinition(
        address=110,
        bit_position=9,
        canonical_name="battery_eco_enable",
        api_param_key="FUNC_BATTERY_ECO_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="Battery eco mode — reduce battery cycling for longevity.",
    ),
    HoldingRegisterDefinition(
        address=110,
        bit_position=10,
        canonical_name="working_mode",
        api_param_key="BIT_WORKING_MODE",  # verified
        category=HoldingCategory.FUNCTION,
        description="Working mode bit (multi-bit field).",
    ),
    HoldingRegisterDefinition(
        address=110,
        bit_position=11,
        canonical_name="pvct_sample_type",
        api_param_key="BIT_PVCT_SAMPLE_TYPE",  # verified
        category=HoldingCategory.FUNCTION,
        description="PV CT sample type selection.",
    ),
    HoldingRegisterDefinition(
        address=110,
        bit_position=12,
        canonical_name="pvct_sample_ratio",
        api_param_key="BIT_PVCT_SAMPLE_RATIO",  # verified
        category=HoldingCategory.FUNCTION,
        description="PV CT sample ratio setting.",
    ),
    HoldingRegisterDefinition(
        address=110,
        bit_position=13,
        canonical_name="ct_sample_ratio",
        api_param_key="BIT_CT_SAMPLE_RATIO",  # verified
        category=HoldingCategory.FUNCTION,
        description="Grid CT sample ratio setting (multi-bit field).",
    ),
    # =========================================================================
    # SYSTEM TYPE / PARALLEL CONFIGURATION (reg 112)
    # =========================================================================
    HoldingRegisterDefinition(
        address=112,
        canonical_name="system_type",
        api_param_key="HOLD_SYSTEM_TYPE",
        min_value=0,
        max_value=3,
        category=HoldingCategory.SYSTEM,
        description="Parallel system type. 0=Single, 1=Master, 2=Slave, 3=3-Phase Master.",
    ),
    # =========================================================================
    # SYSTEM ENABLE BITFIELD — Register 120 (7 bits, verified)
    # =========================================================================
    HoldingRegisterDefinition(
        address=120,
        bit_position=0,
        canonical_name="half_hour_ac_charge_start_enable",
        api_param_key="FUNC_HALF_HOUR_AC_CHG_START_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="Half-hour AC charge start enable.",
    ),
    HoldingRegisterDefinition(
        address=120,
        bit_position=1,
        canonical_name="sna_battery_discharge_control",
        api_param_key="FUNC_SNA_BAT_DISCHARGE_CONTROL",  # verified
        category=HoldingCategory.FUNCTION,
        description="SNA battery discharge control enable.",
    ),
    HoldingRegisterDefinition(
        address=120,
        bit_position=2,
        canonical_name="phase_independent_compensate_enable",
        api_param_key="FUNC_PHASE_INDEPEND_COMPENSATE_EN",  # verified
        category=HoldingCategory.FUNCTION,
        description="Phase-independent power compensation enable.",
    ),
    HoldingRegisterDefinition(
        address=120,
        bit_position=3,
        canonical_name="ac_charge_type",
        api_param_key="BIT_AC_CHARGE_TYPE",  # verified
        category=HoldingCategory.FUNCTION,
        description="AC charge type selection bit.",
    ),
    HoldingRegisterDefinition(
        address=120,
        bit_position=4,
        canonical_name="discharge_control_type",
        api_param_key="BIT_DISCHG_CONTROL_TYPE",  # verified
        category=HoldingCategory.FUNCTION,
        description="Discharge control type selection bit.",
    ),
    HoldingRegisterDefinition(
        address=120,
        bit_position=5,
        canonical_name="ongrid_eod_type",
        api_param_key="BIT_ON_GRID_EOD_TYPE",  # verified
        category=HoldingCategory.FUNCTION,
        description="On-grid end-of-discharge type. 0=voltage, 1=SOC.",
    ),
    HoldingRegisterDefinition(
        address=120,
        bit_position=6,
        canonical_name="generator_charge_type",
        api_param_key="BIT_GENERATOR_CHARGE_TYPE",  # verified
        category=HoldingCategory.FUNCTION,
        description="Generator charge type selection bit.",
    ),
    # =========================================================================
    # FLOAT CHARGE / EQUALIZATION / BATTERY CAPACITY (regs 144, 147-151)
    # =========================================================================
    HoldingRegisterDefinition(
        address=144,
        canonical_name="float_charge_voltage",
        api_param_key="HOLD_FLOAT_CHARGE_VOLTAGE",
        scale=ScaleFactor.DIV_10,
        unit="V",
        min_value=50.0,
        max_value=56.0,
        category=HoldingCategory.BATTERY,
        description="Float (maintenance) charge voltage.",
    ),
    HoldingRegisterDefinition(
        address=147,
        canonical_name="battery_capacity",
        api_param_key="HOLD_BATTERY_CAPACITY",
        unit="Ah",
        min_value=0,
        max_value=10000,
        category=HoldingCategory.BATTERY,
        description="Battery bank total capacity.",
    ),
    HoldingRegisterDefinition(
        address=148,
        canonical_name="battery_nominal_voltage",
        api_param_key="HOLD_BATTERY_NOMINAL_VOLTAGE",
        scale=ScaleFactor.DIV_10,
        unit="V",
        min_value=40.0,
        max_value=59.0,
        category=HoldingCategory.BATTERY,
        description="Battery bank nominal voltage.",
    ),
    HoldingRegisterDefinition(
        address=149,
        canonical_name="equalization_voltage",
        api_param_key="HOLD_EQUALIZATION_VOLTAGE",
        scale=ScaleFactor.DIV_10,
        unit="V",
        min_value=50.0,
        max_value=59.0,
        category=HoldingCategory.BATTERY,
        description="Equalization charge voltage.",
    ),
    HoldingRegisterDefinition(
        address=150,
        canonical_name="equalization_interval",
        api_param_key="HOLD_EQUALIZATION_PERIOD",  # verified
        unit="days",
        min_value=0,
        max_value=365,
        category=HoldingCategory.BATTERY,
        description="Equalization charge interval in days. 0=disabled.",
    ),
    HoldingRegisterDefinition(
        address=151,
        canonical_name="equalization_time",
        api_param_key="HOLD_EQUALIZATION_TIME",
        unit="h",
        min_value=0,
        max_value=24,
        category=HoldingCategory.BATTERY,
        description="Equalization charge duration in hours.",
    ),
    # =========================================================================
    # OUTPUT PRIORITY / LINE MODE (regs 145-146)
    # =========================================================================
    HoldingRegisterDefinition(
        address=145,
        canonical_name="output_priority",
        api_param_key="HOLD_OUTPUT_PRIORITY",
        min_value=0,
        max_value=2,
        category=HoldingCategory.OUTPUT,
        description="Output source priority. 0=Battery First, 1=PV First, 2=AC First.",
    ),
    HoldingRegisterDefinition(
        address=146,
        canonical_name="line_mode",
        api_param_key="HOLD_LINE_MODE",
        min_value=0,
        max_value=2,
        category=HoldingCategory.OUTPUT,
        description="AC input line mode. 0=APL (normal), 1=UPS, 2=GEN (generator).",
    ),
    # =========================================================================
    # AC CHARGE VOLTAGE / SOC TRIGGERS (regs 158-161)
    # =========================================================================
    HoldingRegisterDefinition(
        address=158,
        canonical_name="ac_charge_start_voltage",
        api_param_key="HOLD_AC_CHARGE_START_VOLTAGE",
        scale=ScaleFactor.DIV_10,
        unit="V",
        min_value=38.4,
        max_value=52.0,
        category=HoldingCategory.BATTERY,
        description="Battery voltage to start AC charging.",
    ),
    HoldingRegisterDefinition(
        address=159,
        canonical_name="ac_charge_end_voltage",
        api_param_key="HOLD_AC_CHARGE_END_VOLTAGE",
        scale=ScaleFactor.DIV_10,
        unit="V",
        min_value=48.0,
        max_value=59.0,
        category=HoldingCategory.BATTERY,
        description="Battery voltage to stop AC charging.",
    ),
    HoldingRegisterDefinition(
        address=160,
        canonical_name="ac_charge_start_soc",
        api_param_key="HOLD_AC_CHARGE_START_BATTERY_SOC",  # verified
        unit="%",
        min_value=0,
        max_value=90,
        category=HoldingCategory.BATTERY,
        description="Battery SOC to start AC charging.",
    ),
    HoldingRegisterDefinition(
        address=161,
        canonical_name="ac_charge_end_soc",
        api_param_key="HOLD_AC_CHARGE_END_BATTERY_SOC",
        unit="%",
        min_value=20,
        max_value=100,
        category=HoldingCategory.BATTERY,
        description="Battery SOC to stop AC charging.",
    ),
    # =========================================================================
    # BATTERY LOW SETTINGS (regs 162-165, 167)
    # =========================================================================
    HoldingRegisterDefinition(
        address=162,
        canonical_name="battery_low_voltage",
        api_param_key="HOLD_BATTERY_LOW_VOLTAGE",
        scale=ScaleFactor.DIV_10,
        unit="V",
        min_value=40.0,
        max_value=50.0,
        category=HoldingCategory.BATTERY,
        description="Battery low voltage alarm threshold.",
    ),
    HoldingRegisterDefinition(
        address=163,
        canonical_name="battery_low_back_voltage",
        api_param_key="HOLD_BATTERY_LOW_BACK_VOLTAGE",
        scale=ScaleFactor.DIV_10,
        unit="V",
        min_value=42.0,
        max_value=52.0,
        category=HoldingCategory.BATTERY,
        description="Battery low-back (recovery) voltage.",
    ),
    HoldingRegisterDefinition(
        address=164,
        canonical_name="battery_low_soc",
        api_param_key="HOLD_BATTERY_LOW_SOC",
        unit="%",
        min_value=0,
        max_value=90,
        category=HoldingCategory.BATTERY,
        description="Battery low SOC alarm threshold.",
    ),
    HoldingRegisterDefinition(
        address=165,
        canonical_name="battery_low_back_soc",
        api_param_key="HOLD_BATTERY_LOW_BACK_SOC",
        unit="%",
        min_value=20,
        max_value=100,
        category=HoldingCategory.BATTERY,
        description="Battery low-back (recovery) SOC.",
    ),
    HoldingRegisterDefinition(
        address=167,
        canonical_name="battery_low_to_utility_soc",
        api_param_key="HOLD_BATTERY_LOW_TO_UTILITY_SOC",
        unit="%",
        min_value=0,
        max_value=100,
        category=HoldingCategory.BATTERY,
        description="Battery SOC to switch from battery to utility.",
    ),
    # =========================================================================
    # BATTERY LOW / EOD VOLTAGE (regs 166, 169)
    # =========================================================================
    HoldingRegisterDefinition(
        address=166,
        canonical_name="battery_low_to_utility_voltage",
        api_param_key="HOLD_BATTERY_LOW_TO_UTILITY_VOLTAGE",
        scale=ScaleFactor.DIV_10,
        unit="V",
        min_value=44.4,
        max_value=51.4,
        category=HoldingCategory.BATTERY,
        description="Battery voltage to switch from battery to utility.",
    ),
    HoldingRegisterDefinition(
        address=168,
        canonical_name="ac_charge_battery_current",
        api_param_key="HOLD_AC_CHARGE_BATTERY_CURRENT",
        unit="A",
        min_value=0,
        max_value=140,
        category=HoldingCategory.BATTERY,
        description="Maximum AC charge battery current.",
    ),
    HoldingRegisterDefinition(
        address=169,
        canonical_name="ongrid_eod_voltage",
        api_param_key="HOLD_ONGRID_EOD_VOLTAGE",
        scale=ScaleFactor.DIV_10,
        unit="V",
        min_value=40.0,
        max_value=56.0,
        category=HoldingCategory.BATTERY,
        description="On-grid end-of-discharge voltage.",
    ),
    # =========================================================================
    # MAX GRID INPUT / GENERATOR RATED POWER (regs 176-177)
    # =========================================================================
    HoldingRegisterDefinition(
        address=176,
        canonical_name="max_grid_input_power",
        api_param_key="HOLD_MAX_GRID_INPUT_POWER",
        unit="W",
        category=HoldingCategory.GRID,
        description="Maximum grid input power limit.",
    ),
    HoldingRegisterDefinition(
        address=177,
        canonical_name="generator_rated_power",
        api_param_key="HOLD_GEN_RATED_POWER",
        unit="W",
        category=HoldingCategory.GENERATOR,
        description="Generator rated power for charge control.",
    ),
    # =========================================================================
    # HOLD_P2 (reg 190) — purpose unclear, may be parallel-related
    # =========================================================================
    HoldingRegisterDefinition(
        address=190,
        canonical_name="hold_p2",
        api_param_key="HOLD_P2",  # verified
        category=HoldingCategory.SYSTEM,
        description="Hold register P2 (purpose under investigation).",
    ),
    # =========================================================================
    # GENERATOR CHARGE SETTINGS (regs 194-198)
    # =========================================================================
    HoldingRegisterDefinition(
        address=194,
        canonical_name="gen_charge_start_voltage",
        api_param_key="HOLD_GEN_CHARGE_START_VOLTAGE",
        scale=ScaleFactor.DIV_10,
        unit="V",
        min_value=38.4,
        max_value=52.0,
        category=HoldingCategory.GENERATOR,
        description="Generator charge start voltage.",
    ),
    HoldingRegisterDefinition(
        address=195,
        canonical_name="gen_charge_end_voltage",
        api_param_key="HOLD_GEN_CHARGE_END_VOLTAGE",
        scale=ScaleFactor.DIV_10,
        unit="V",
        min_value=48.0,
        max_value=59.0,
        category=HoldingCategory.GENERATOR,
        description="Generator charge end voltage.",
    ),
    HoldingRegisterDefinition(
        address=196,
        canonical_name="gen_charge_start_soc",
        api_param_key="HOLD_GEN_CHARGE_START_SOC",
        unit="%",
        min_value=0,
        max_value=90,
        category=HoldingCategory.GENERATOR,
        description="Generator charge start SOC.",
    ),
    HoldingRegisterDefinition(
        address=197,
        canonical_name="gen_charge_end_soc",
        api_param_key="HOLD_GEN_CHARGE_END_SOC",
        unit="%",
        min_value=20,
        max_value=100,
        category=HoldingCategory.GENERATOR,
        description="Generator charge end SOC.",
    ),
    HoldingRegisterDefinition(
        address=198,
        canonical_name="max_gen_charge_battery_current",
        api_param_key="HOLD_MAX_GEN_CHARGE_BATTERY_CURRENT",
        unit="A",
        min_value=0,
        max_value=60,
        category=HoldingCategory.GENERATOR,
        description="Maximum generator charge battery current.",
    ),
    # =========================================================================
    # SYSTEM CHARGE SOC LIMIT (reg 227, verified)
    # =========================================================================
    HoldingRegisterDefinition(
        address=227,
        canonical_name="system_charge_soc_limit",
        api_param_key="HOLD_SYSTEM_CHARGE_SOC_LIMIT",  # verified
        ha_entity_key="system_charge_soc_limit",
        unit="%",
        min_value=0,
        max_value=100,
        category=HoldingCategory.BATTERY,
        description="System-level charge SOC limit (stops all charging at this SOC).",
    ),
    # =========================================================================
    # GRID PEAK SHAVING (reg 231, 32-bit)
    # =========================================================================
    HoldingRegisterDefinition(
        address=231,
        canonical_name="grid_peak_shaving_power",
        api_param_key="_12K_HOLD_GRID_PEAK_SHAVING_POWER",  # verified
        ha_entity_key="grid_peak_shaving_power",
        bit_width=32,
        unit="kW",
        category=HoldingCategory.GRID,
        description="Grid peak shaving power limit (32-bit, kW).",
    ),
    # =========================================================================
    # EXTENDED FUNCTION ENABLE 4 (reg 179) — 16-bit bitfield
    # =========================================================================
    HoldingRegisterDefinition(
        address=179,
        bit_position=0,
        canonical_name="ac_ct_direction",
        api_param_key="FUNC_AC_CT_DIRECTION",
        category=HoldingCategory.FUNCTION,
        description="AC CT direction (0=Normal, 1=Reversed).",
    ),
    HoldingRegisterDefinition(
        address=179,
        bit_position=1,
        canonical_name="pv_ct_direction",
        api_param_key="FUNC_PV_CT_DIRECTION",
        category=HoldingCategory.FUNCTION,
        description="PV CT direction (0=Normal, 1=Reversed).",
    ),
    HoldingRegisterDefinition(
        address=179,
        bit_position=2,
        canonical_name="afci_alarm_clear",
        api_param_key="FUNC_AFCI_ALARM_CLR",
        category=HoldingCategory.FUNCTION,
        description="AFCI alarm clear.",
    ),
    HoldingRegisterDefinition(
        address=179,
        bit_position=3,
        canonical_name="battery_wakeup_enable",
        api_param_key="FUNC_BAT_WAKEUP_EN",
        category=HoldingCategory.FUNCTION,
        description="Battery wakeup / PV sell first enable.",
    ),
    HoldingRegisterDefinition(
        address=179,
        bit_position=4,
        canonical_name="volt_watt_enable",
        api_param_key="FUNC_VOLT_WATT_EN",
        category=HoldingCategory.FUNCTION,
        description="Volt-Watt response mode enable.",
    ),
    HoldingRegisterDefinition(
        address=179,
        bit_position=5,
        canonical_name="trip_time_unit",
        api_param_key="FUNC_TRIP_TIME_UNIT",
        category=HoldingCategory.FUNCTION,
        description="Trip time unit selection.",
    ),
    HoldingRegisterDefinition(
        address=179,
        bit_position=6,
        canonical_name="active_power_cmd_enable",
        api_param_key="FUNC_ACT_POWER_CMD_EN",
        category=HoldingCategory.FUNCTION,
        description="Active power command enable.",
    ),
    HoldingRegisterDefinition(
        address=179,
        bit_position=7,
        canonical_name="grid_peak_shaving_enable",
        api_param_key="FUNC_GRID_PEAK_SHAVING",
        category=HoldingCategory.FUNCTION,
        description="Grid peak shaving enable.",
    ),
    HoldingRegisterDefinition(
        address=179,
        bit_position=8,
        canonical_name="gen_peak_shaving_enable",
        api_param_key="FUNC_GEN_PEAK_SHAVING",
        category=HoldingCategory.FUNCTION,
        description="Generator peak shaving enable.",
    ),
    HoldingRegisterDefinition(
        address=179,
        bit_position=9,
        canonical_name="battery_charge_control",
        api_param_key="FUNC_BAT_CHG_CONTROL",
        ha_entity_key="battery_charge_control",
        category=HoldingCategory.FUNCTION,
        description="Battery charge control mode (0=SOC, 1=Voltage).",
    ),
    HoldingRegisterDefinition(
        address=179,
        bit_position=10,
        canonical_name="battery_discharge_control",
        api_param_key="FUNC_BAT_DISCHG_CONTROL",
        ha_entity_key="battery_discharge_control",
        category=HoldingCategory.FUNCTION,
        description="Battery discharge control mode (0=SOC, 1=Voltage).",
    ),
    HoldingRegisterDefinition(
        address=179,
        bit_position=11,
        canonical_name="ac_coupling_enable",
        api_param_key="FUNC_AC_COUPLING",
        ha_entity_key="ac_coupling",
        category=HoldingCategory.FUNCTION,
        description="AC coupling enable.",
    ),
    HoldingRegisterDefinition(
        address=179,
        bit_position=12,
        canonical_name="pv_arc_enable",
        api_param_key="FUNC_PV_ARC_EN",
        category=HoldingCategory.FUNCTION,
        description="PV arc detection enable.",
    ),
    HoldingRegisterDefinition(
        address=179,
        bit_position=13,
        canonical_name="smart_load_enable",
        api_param_key="FUNC_SMART_LOAD_EN",
        ha_entity_key="smart_load",
        category=HoldingCategory.FUNCTION,
        description="Smart load enable (0=Generator, 1=Smart Load).",
    ),
    HoldingRegisterDefinition(
        address=179,
        bit_position=14,
        canonical_name="rsd_disable",
        api_param_key="FUNC_RSD_DISABLE",
        category=HoldingCategory.FUNCTION,
        description="Rapid shutdown disable (0=RSD enabled, 1=RSD disabled).",
    ),
    HoldingRegisterDefinition(
        address=179,
        bit_position=15,
        canonical_name="ongrid_always_on",
        api_param_key="FUNC_ONGRID_ALWAYS_ON",
        category=HoldingCategory.FUNCTION,
        description="On-grid always on.",
    ),
    # =========================================================================
    # EXTENDED FUNCTION ENABLE 5 (reg 233) — partial bitfield
    # =========================================================================
    HoldingRegisterDefinition(
        address=233,
        bit_position=0,
        canonical_name="quick_charge_start_enable",
        api_param_key="FUNC_QUICK_CHG_START_EN",
        category=HoldingCategory.FUNCTION,
        description="Quick charge start enable.",
    ),
    HoldingRegisterDefinition(
        address=233,
        bit_position=1,
        canonical_name="battery_backup_enable",
        api_param_key="FUNC_BATT_BACKUP_EN",
        category=HoldingCategory.FUNCTION,
        description="Battery backup enable.",
    ),
    HoldingRegisterDefinition(
        address=233,
        bit_position=2,
        canonical_name="maintenance_enable",
        api_param_key="FUNC_MAINTENANCE_EN",
        category=HoldingCategory.FUNCTION,
        description="Maintenance mode enable.",
    ),
    HoldingRegisterDefinition(
        address=233,
        bit_position=3,
        canonical_name="weekly_schedule_enable",
        api_param_key="FUNC_ENERTEK_WORKING_MODE",
        ha_entity_key="weekly_schedule",
        category=HoldingCategory.FUNCTION,
        description="7-day scheduling mode (0=daily regs 68-89, 1=weekly regs 500-723).",
    ),
    HoldingRegisterDefinition(
        address=233,
        bit_position=10,
        canonical_name="over_freq_fast_stop",
        api_param_key="FUNC_OVER_FREQ_FSTOP",
        category=HoldingCategory.FUNCTION,
        description="Over-frequency fast stop enable.",
    ),
    HoldingRegisterDefinition(
        address=233,
        bit_position=12,
        canonical_name="sporadic_charge_enable",
        api_param_key="FUNC_SPORADIC_CHARGE",
        ha_entity_key="sporadic_charge",
        category=HoldingCategory.FUNCTION,
        description="Sporadic charge enable.",
    ),
)


# =============================================================================
# LOOKUP INDEXES (built once at import time)
# =============================================================================

# canonical_name → HoldingRegisterDefinition
BY_NAME: dict[str, HoldingRegisterDefinition] = {
    r.canonical_name: r for r in INVERTER_HOLDING_REGISTERS
}

# address → tuple of HoldingRegisterDefinitions (multiple for bitfield registers)
BY_ADDRESS: dict[int, tuple[HoldingRegisterDefinition, ...]] = {}
for _reg in INVERTER_HOLDING_REGISTERS:
    BY_ADDRESS.setdefault(_reg.address, ())
    BY_ADDRESS[_reg.address] = (*BY_ADDRESS[_reg.address], _reg)

# api_param_key → HoldingRegisterDefinition
BY_API_KEY: dict[str, HoldingRegisterDefinition] = {
    r.api_param_key: r for r in INVERTER_HOLDING_REGISTERS
}

# ha_entity_key → HoldingRegisterDefinition (only entries with HA mapping)
BY_ENTITY_KEY: dict[str, HoldingRegisterDefinition] = {
    r.ha_entity_key: r for r in INVERTER_HOLDING_REGISTERS if r.ha_entity_key is not None
}

# Category → tuple of HoldingRegisterDefinitions
BY_CATEGORY: dict[HoldingCategory, tuple[HoldingRegisterDefinition, ...]] = {}
for _reg in INVERTER_HOLDING_REGISTERS:
    BY_CATEGORY.setdefault(_reg.category, ())
    BY_CATEGORY[_reg.category] = (*BY_CATEGORY[_reg.category], _reg)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def registers_for_model(family: str) -> tuple[HoldingRegisterDefinition, ...]:
    """Return only registers supported by the given InverterFamily value."""
    return tuple(r for r in INVERTER_HOLDING_REGISTERS if family in r.models)


def value_registers() -> tuple[HoldingRegisterDefinition, ...]:
    """Return only value registers (non-bitfield entries)."""
    return tuple(r for r in INVERTER_HOLDING_REGISTERS if r.bit_position is None)


def bitfield_registers() -> tuple[HoldingRegisterDefinition, ...]:
    """Return only bitfield entries (individual bits within bitfield registers)."""
    return tuple(r for r in INVERTER_HOLDING_REGISTERS if r.bit_position is not None)


def bitfield_entries_for_address(address: int) -> tuple[HoldingRegisterDefinition, ...]:
    """Return all bitfield entries for a specific register address."""
    return tuple(r for r in BY_ADDRESS.get(address, ()) if r.bit_position is not None)


def entity_keys_for_model(family: str) -> frozenset[str]:
    """Return the set of HA entity keys available for the given model family."""
    return frozenset(
        r.ha_entity_key
        for r in INVERTER_HOLDING_REGISTERS
        if r.ha_entity_key is not None and family in r.models
    )
