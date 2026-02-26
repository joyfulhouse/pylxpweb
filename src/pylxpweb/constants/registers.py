"""Inverter parameter register definitions and mappings.

This module contains all hold register (configuration) and input register
(runtime data) definitions for Luxpower/EG4 inverters, plus GridBOSS/MID
device parameters.

Source: EG4-18KPV-12LV Modbus Protocol specification
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# ============================================================================
# SCHEDULE TYPE INFRASTRUCTURE
# ============================================================================
# Three schedule types share identical register patterns: a power cmd register,
# a SOC limit register, and 6 packed-time registers (3 periods × 2 regs each).


class ScheduleType(StrEnum):
    """Inverter time schedule types.

    Each type controls a different operating mode via time-based schedules
    with up to 3 periods per day.
    """

    AC_CHARGE = "ac_charge"
    FORCED_CHARGE = "forced_charge"
    FORCED_DISCHARGE = "forced_discharge"


@dataclass(frozen=True)
class ScheduleConfig:
    """Configuration for a schedule type's cloud API prefix and Modbus registers.

    Attributes:
        cloud_prefix: Cloud API parameter prefix (e.g. "HOLD_AC_CHARGE").
            Schedule params follow the pattern: ``{cloud_prefix}_START_HOUR{suffix}``
            where suffix is "" for period 0, "_1" for period 1, "_2" for period 2.
        base_register: First packed-time register address (Modbus).
            Each schedule occupies 6 consecutive registers (3 periods × 2 regs).
    """

    cloud_prefix: str
    base_register: int


# Mapping from schedule type to its configuration.
# Used by both cloud API (control.py) and Modbus (hybrid.py) code paths.
SCHEDULE_CONFIGS: dict[ScheduleType, ScheduleConfig] = {
    ScheduleType.AC_CHARGE: ScheduleConfig("HOLD_AC_CHARGE", 68),
    ScheduleType.FORCED_CHARGE: ScheduleConfig("HOLD_FORCED_CHARGE", 76),
    ScheduleType.FORCED_DISCHARGE: ScheduleConfig("HOLD_FORCED_DISCHARGE", 84),
}


# ============================================================================
# INVERTER PARAMETER MAPPINGS (Hold Registers)
# ============================================================================
# Source: EG4-18KPV-12LV Modbus Protocol specification
# Complete documentation: docs/api/PARAMETER_MAPPING.md

# Critical Control Register (Address 21) - Function Enable Bit Field
FUNC_EN_REGISTER = 21
FUNC_EN_BIT_EPS_EN = 0  # Off-grid mode enable
FUNC_EN_BIT_AC_CHARGE_EN = 7  # AC charge enable
FUNC_EN_BIT_SET_TO_STANDBY = 9  # 0=Standby, 1=Power On
FUNC_EN_BIT_FORCED_DISCHG_EN = 10  # Forced discharge enable
FUNC_EN_BIT_FORCED_CHG_EN = 11  # Force charge enable

# System Function Register (Address 110) - Bit Field
FUNC_SYS_REGISTER = 110
FUNC_SYS_BIT_CHARGE_LAST = 4  # Charge last: charge battery after loads satisfied

# Extended Function Enable Register (Address 179) - Bit Field
FUNC_EXT_REGISTER = 179
FUNC_EXT_BIT_BAT_CHARGE_CONTROL = 9  # 0=SOC, 1=Voltage (confirmed 2026-02-18)
FUNC_EXT_BIT_BAT_DISCHARGE_CONTROL = 10  # 0=SOC, 1=Voltage (confirmed 2026-02-18)

# Extended Function Enable Register 2 (Address 233) - Bit Field
FUNC_EN_2_REGISTER = 233
FUNC_EN_2_BIT_SPORADIC_CHARGE = 12  # Sporadic charge enable (confirmed via Modbus)

# AC Charge Parameters
HOLD_AC_CHARGE_POWER_CMD = 66  # AC charge power in 100W units (0-150 = 0.0-15.0 kW)
HOLD_AC_CHARGE_SOC_LIMIT = 67  # AC charge SOC limit (0-100%)
# AC Charge Time Schedule (regs 68-73) - packed time format (Modbus)
# Format: value = (hour & 0xFF) | ((minute & 0xFF) << 8)
# Each register stores hour (low byte) + minute (high byte)
HOLD_AC_CHARGE_TIME_0_START = 68  # Period 0 start (packed hour|minute)
HOLD_AC_CHARGE_TIME_0_END = 69  # Period 0 end
HOLD_AC_CHARGE_TIME_1_START = 70  # Period 1 start
HOLD_AC_CHARGE_TIME_1_END = 71  # Period 1 end
HOLD_AC_CHARGE_TIME_2_START = 72  # Period 2 start
HOLD_AC_CHARGE_TIME_2_END = 73  # Period 2 end

# AC Charge Type (register 120, bits 1-3)
# Controls what the AC charge schedule is based on.
# Verified via Modbus probe on FlexBOSS21 (FAAB-2525): bit field at (reg120 >> 1) & 0x07
#
# EG4 web UI presents 3 options, mapped to these values:
#   0 = Time         (reg 120 = 0)
#   1 = SOC/Volt     (reg 120 = 2)
#   2 = Time+SOC/Volt (reg 120 = 4)
#
# Reference docs (MODBUS_WRITABLE_REGISTERS_ANALYSIS.md) indicate bits 1-3 support
# up to 6 modes: 0=Disable, 1=By Time, 2=By Voltage, 3=By SOC, 4=Voltage+Time,
# 5=SOC+Time. Only the 3 values above have been empirically verified; the inverter
# may support additional modes not exposed by the EG4 web interface.
HOLD_AC_CHARGE_TYPE_REGISTER = 120
AC_CHARGE_TYPE_SHIFT = 1  # 3-bit field starting at bit 1
AC_CHARGE_TYPE_MASK = 0x0E  # Bits 1-3 (0b00001110)
AC_CHARGE_TYPE_TIME = 0  # Time-based schedule only
AC_CHARGE_TYPE_SOC_VOLT = 1  # SOC/Voltage-based only
AC_CHARGE_TYPE_TIME_SOC_VOLT = 2  # Time + SOC/Voltage combined

# AC Charge SOC/Voltage Thresholds (regs 158-161)
# These control when AC charging starts/stops based on battery SOC or voltage.
# Used when AC charge type is set to SOC/Volt or Time+SOC/Volt.
# Verified via Modbus probe 2026-02-13.
HOLD_AC_CHARGE_START_VOLTAGE = 158  # Start AC charge voltage (÷10, whole volts only)
HOLD_AC_CHARGE_END_VOLTAGE = 159  # Stop AC charge voltage (÷10, whole volts only)
HOLD_AC_CHARGE_START_SOC = 160  # Battery SOC to start AC charging (0-90%)
# Note: Stop AC Charge SOC is register 67 (HOLD_AC_CHARGE_SOC_LIMIT), NOT register 161.
# Register 161 is read-only via Modbus and not used for this purpose.
# Verified on FlexBOSS21 firmware FAAB-2525.

# Forced Charge (ChgFirst / PV Charge Priority) Parameters
# Per EG4-18KPV-12LV Modbus PDF, regs 74-81 are "Charging Priority" (ChgFirst).
# Cloud API names: HOLD_FORCED_CHG_POWER_CMD, HOLD_FORCED_CHG_SOC_LIMIT
HOLD_FORCED_CHG_POWER_CMD = 74  # Forced charge power command (0-100%)
HOLD_FORCED_CHG_SOC_LIMIT = 75  # Forced charge SOC limit (0-100%)

# Forced Charge Time Schedule (regs 76-81) - packed time format (Modbus)
# Format: value = (hour & 0xFF) | ((minute & 0xFF) << 8)
# Cloud API names: HOLD_FORCED_CHARGE_START_HOUR{suffix}, etc.
HOLD_FORCED_CHARGE_TIME_0_START = 76  # Period 0 start (packed hour|minute)
HOLD_FORCED_CHARGE_TIME_0_END = 77  # Period 0 end
HOLD_FORCED_CHARGE_TIME_1_START = 78  # Period 1 start
HOLD_FORCED_CHARGE_TIME_1_END = 79  # Period 1 end
HOLD_FORCED_CHARGE_TIME_2_START = 80  # Period 2 start
HOLD_FORCED_CHARGE_TIME_2_END = 81  # Period 2 end

# Forced Discharge Parameters
# Cloud API names: HOLD_FORCED_DISCHG_POWER_CMD, HOLD_FORCED_DISCHG_SOC_LIMIT
HOLD_FORCED_DISCHG_POWER_CMD = 82  # Forced discharge power command (0-100%)
HOLD_FORCED_DISCHG_SOC_LIMIT = 83  # Forced discharge SOC limit (0-100%)

# Forced Discharge Time Schedule (regs 84-89) - packed time format (Modbus)
# Cloud API names: HOLD_FORCED_DISCHARGE_START_HOUR{suffix}, etc.
HOLD_FORCED_DISCHARGE_TIME_0_START = 84  # Period 0 start (packed hour|minute)
HOLD_FORCED_DISCHARGE_TIME_0_END = 85  # Period 0 end
HOLD_FORCED_DISCHARGE_TIME_1_START = 86  # Period 1 start
HOLD_FORCED_DISCHARGE_TIME_1_END = 87  # Period 1 end
HOLD_FORCED_DISCHARGE_TIME_2_START = 88  # Period 2 start
HOLD_FORCED_DISCHARGE_TIME_2_END = 89  # Period 2 end

# Battery Protection Parameters
HOLD_BAT_VOLT_MAX_CHG = 99  # Battery max charge voltage (V, ×10 decivolts)
# NOTE: Reg 100 was previously mapped as HOLD_BAT_VOLT_MIN_CHG ("battery min charge voltage")
# but live Modbus testing (2026-02-18) confirmed it is the off-grid discharge cutoff voltage
# (matching API name HOLD_LEAD_ACID_DISCHARGE_CUT_OFF_VOLT). Same mismapping pattern as 101/102.
# Off-grid discharge cutoff voltage (V, ×10 decivolts, confirmed 2026-02-18)
HOLD_OFF_GRID_EOD_VOLTAGE = 100
# Deprecated alias — not actually "min charge voltage"
HOLD_BAT_VOLT_MIN_CHG = HOLD_OFF_GRID_EOD_VOLTAGE
# NOTE: Regs 101/102 were previously mapped as voltage params (HOLD_BAT_VOLT_MAX/MIN_DISCHG)
# but live Modbus testing (2026-02-18) confirmed they are charge/discharge current limits
# in raw amps (no scaling). The API also returns them as HOLD_LEAD_ACID_CHARGE/DISCHARGE_RATE.
HOLD_LEAD_ACID_CHARGE_RATE = 101  # Battery charge current limit (A, confirmed 2026-02-18)
HOLD_LEAD_ACID_DISCHARGE_RATE = 102  # Battery discharge current limit (A, confirmed 2026-02-18)
# deprecated aliases — actually charge/discharge current, not voltage
HOLD_BAT_VOLT_MAX_DISCHG = HOLD_LEAD_ACID_CHARGE_RATE
HOLD_BAT_VOLT_MIN_DISCHG = HOLD_LEAD_ACID_DISCHARGE_RATE
HOLD_MAX_CHG_CURR = 103  # Max charge current (A, /10)
HOLD_MAX_DISCHG_CURR = 104  # Max discharge current (A, /10)
HOLD_DISCHG_CUT_OFF_SOC_EOD = 105  # On-grid discharge cutoff SOC (10-90%)
HOLD_SOC_LOW_LIMIT_EPS_DISCHG = 125  # Off-grid SOC low limit (0-100%) - verified 2026-01-27

# On-Grid Discharge Cutoff Voltage
HOLD_ON_GRID_EOD_VOLTAGE = 169  # On-grid discharge cutoff voltage (V, ×10, confirmed 2026-02-18)

# Discharge Start Threshold (W, confirmed 2026-02-18)
HOLD_P_TO_USER_START_DISCHG = 116  # Start discharge when import exceeds this

# System Charge Limits (regs 227-228)
HOLD_SYSTEM_CHARGE_SOC_LIMIT = 227  # System charge SOC limit (0-100%, verified 2026-01-27)
HOLD_SYSTEM_CHARGE_VOLT_LIMIT = 228  # System charge voltage limit (V, ×10, confirmed 2026-02-18)

# Grid Protection Parameters
HOLD_GRID_VOLT_HIGH_1 = 25  # Grid voltage high limit 1 (V, /10)
HOLD_GRID_VOLT_LOW_1 = 26  # Grid voltage low limit 1 (V, /10)
HOLD_GRID_FREQ_HIGH_1 = 27  # Grid frequency high 1 (Hz, /100)
HOLD_GRID_FREQ_LOW_1 = 28  # Grid frequency low 1 (Hz, /100)

# Reactive Power Control
HOLD_Q_MODE = 59  # Reactive power mode (0-4)
HOLD_Q_PV_MODE = 60  # PV reactive power mode (0-4)
HOLD_Q_POWER = 61  # Reactive power setting (-100 to 100%)
HOLD_Q_PV_POWER = 62  # PV reactive power (-100 to 100%)

# System Configuration
HOLD_SERIAL_NUMBER_H = 0  # Serial number (high word)
HOLD_SERIAL_NUMBER_L = 1  # Serial number (low word)
HOLD_YEAR = 2  # System year (2000-2099)
HOLD_MONTH = 3  # System month (1-12)
HOLD_DAY = 4  # System day (1-31)
HOLD_HOUR = 5  # System hour (0-23)
HOLD_MINUTE = 6  # System minute (0-59)
HOLD_SECOND = 7  # System second (0-59)
HOLD_LANGUAGE = 8  # Language (0=EN, 1=CN)
HOLD_MODBUS_ADDRESS = 9  # Modbus RTU address (1-247)
HOLD_BAUD_RATE = 10  # Baud rate index (0-6)

# ============================================================================
# INPUT REGISTERS (Runtime Data - Read Only)
# ============================================================================

# Power & Energy (Addresses 0-31)
# Source: EG4-18KPV-12LV Modbus Protocol + eg4-modbus-monitor project
INPUT_STATUS = 0  # Device status code
INPUT_V_PV1 = 1  # PV1 voltage (V, /10)
INPUT_V_PV2 = 2  # PV2 voltage (V, /10)
INPUT_V_PV3 = 3  # PV3 voltage (V, /10)
INPUT_V_BAT = 4  # Battery voltage (V, /100)
INPUT_SOC_SOH = 5  # Packed: SOC (low byte, %), SOH (high byte, %)
INPUT_P_PV1 = (6, 7)  # PV1 power (W, 2 registers)
INPUT_P_PV2 = (8, 9)  # PV2 power (W, 2 registers)
INPUT_P_PV3 = (10, 11)  # PV3 power (W, 2 registers)
INPUT_P_CHARGE = (12, 13)  # Battery charge power (W, 2 registers)
INPUT_P_DISCHARGE = (14, 15)  # Battery discharge power (W, 2 registers)
INPUT_V_AC_R = 16  # AC R-phase voltage (V, /10)
INPUT_V_AC_S = 17  # AC S-phase voltage (V, /10)
INPUT_V_AC_T = 18  # AC T-phase voltage (V, /10)
INPUT_F_AC = 19  # AC frequency (Hz, /100)
INPUT_P_INV = (20, 21)  # Inverter output power (W, 2 registers)
INPUT_P_REC = (22, 23)  # Grid import power (W, 2 registers)
INPUT_PF = (24, 25)  # Power factor (/1000, 2 registers)
INPUT_V_EPS_R = 26  # EPS R-phase voltage (V, /10)
INPUT_V_EPS_S = 27  # EPS S-phase voltage (V, /10)
INPUT_V_EPS_T = 28  # EPS T-phase voltage (V, /10)
INPUT_F_EPS = 29  # EPS frequency (Hz, /100)
INPUT_P_EPS = (30, 31)  # EPS output power (W, 2 registers)

# System Status (Addresses 32-59)
INPUT_S_EPS = 32  # EPS status
INPUT_P_TO_GRID = 33  # Export to grid power (W)
INPUT_P_TO_USER = (34, 35)  # Load consumption power (W, 2 registers)
INPUT_E_INV_ALL = 36  # Total inverter energy (Wh after /10, divide by 10 for Wh)
INPUT_E_REC_ALL = 37  # Total grid import energy (Wh after /10, divide by 10 for Wh)
INPUT_E_CHG_ALL = 38  # Total charge energy (Wh after /10, divide by 10 for Wh)
INPUT_E_DISCHG_ALL = 39  # Total discharge energy (Wh after /10, divide by 10 for Wh)
INPUT_E_EPS_ALL = 40  # Total EPS energy (Wh after /10, divide by 10 for Wh)
INPUT_E_TO_GRID_ALL = 41  # Total export energy (Wh after /10, divide by 10 for Wh)
INPUT_E_TO_USER_ALL = 42  # Total load energy (Wh after /10, divide by 10 for Wh)
INPUT_V_BUS1 = 43  # Bus 1 voltage (V, /10)
INPUT_V_BUS2 = 44  # Bus 2 voltage (V, /10)
INPUT_E_INV_DAY = (45, 46)  # Daily inverter energy (Wh after /10, 2 registers)
INPUT_E_REC_DAY = (47, 48)  # Daily grid import (Wh after /10, 2 registers)
INPUT_E_CHG_DAY = (49, 50)  # Daily charge energy (Wh after /10, 2 registers)
INPUT_E_DISCHG_DAY = (51, 52)  # Daily discharge energy (Wh after /10, 2 registers)
INPUT_E_EPS_DAY = (53, 54)  # Daily EPS energy (Wh after /10, 2 registers)
INPUT_E_TO_GRID_DAY = (55, 56)  # Daily export energy (Wh after /10, 2 registers)
INPUT_E_TO_USER_DAY = (57, 58)  # Daily load energy (Wh after /10, 2 registers)
INPUT_V_BAT_LIMIT = 59  # Max charge voltage (V, /100)

# Inverter Fault/Warning Codes (Addresses 60-63)
# Source: eg4-modbus-monitor project
INPUT_FAULT_CODE = (60, 61)  # Inverter fault code (32-bit, 2 registers)
INPUT_WARNING_CODE = (62, 63)  # Inverter warning code (32-bit, 2 registers)

# Temperature Sensors & Currents (Addresses 64-75)
# Source: eg4-modbus-monitor project
INPUT_T_INNER = 64  # Internal temperature (°C, signed)
INPUT_T_RADIATOR_1 = 65  # Radiator 1 temperature (°C)
INPUT_T_RADIATOR_2 = 66  # Radiator 2 temperature (°C)
INPUT_T_BAT = 67  # Battery temperature (°C)
INPUT_T_BAT_CONTROL = 68  # Battery control temp (°C)
INPUT_RUNNING_TIME = (69, 70)  # Running time (seconds, 32-bit)
INPUT_I_PV1 = 72  # PV1 current (A, /100)
INPUT_I_PV2 = 73  # PV2 current (A, /100)
INPUT_I_PV3 = 74  # PV3 current (A, /100)
INPUT_I_BAT = 75  # Battery current (A, /100)

# Internal Fault History (Addresses 76-79)
INPUT_INTERNAL_FAULT = (76, 77)  # Internal fault code (2 registers)
INPUT_FAULT_HISTORY_1 = (78, 79)  # Fault history 1 (2 registers)

# ============================================================================
# BMS DATA REGISTERS (Addresses 80-112)
# ============================================================================
# Source: Yippy's documentation from issue #97
# https://github.com/joyfulhouse/pylxpweb/issues/97
# These registers contain BMS passthrough data from the battery management system.

# BMS Configuration Limits (Addresses 80-84)
INPUT_BMS_BAT_TYPE = 80  # Battery type/brand and communication type (CAN=0, 485=1)
INPUT_BMS_MAX_CHG_CURR = 81  # BMS max charging current (A, /100)
INPUT_BMS_MAX_DISCHG_CURR = 82  # BMS max discharging current (A, /100)
INPUT_BMS_CHARGE_VOLT_REF = 83  # BMS recommended charge voltage (V, /10)
INPUT_BMS_DISCHG_CUT_VOLT = 84  # BMS discharge cutoff voltage (V, /10)

# BMS Status Registers (Addresses 85-95)
INPUT_BMS_STATUS_0 = 85  # BMS status register 0
INPUT_BMS_STATUS_1 = 86  # BMS status register 1
INPUT_BMS_STATUS_2 = 87  # BMS status register 2
INPUT_BMS_STATUS_3 = 88  # BMS status register 3
INPUT_BMS_STATUS_4 = 89  # BMS status register 4
INPUT_BMS_STATUS_5 = 90  # BMS status register 5
INPUT_BMS_STATUS_6 = 91  # BMS status register 6
INPUT_BMS_STATUS_7 = 92  # BMS status register 7
INPUT_BMS_STATUS_8 = 93  # BMS status register 8
INPUT_BMS_STATUS_9 = 94  # BMS status register 9
INPUT_BMS_STATUS_INV = 95  # Inverter-aggregated battery status

# Register 95 raw status codes. Note: value 3 means "Active" (battery in use)
# and does NOT indicate charge vs discharge direction. The actual battery status
# (Charging/Discharging/Idle) is derived from Pcharge/Pdischarge registers instead.
BATTERY_STATUS_MAP: dict[int, str] = {
    0: "Idle",
    1: "Unknown(1)",
    2: "StandBy",
    3: "Active",
}

# BMS Battery Info (Addresses 96-100)
INPUT_BMS_PARALLEL_NUM = 96  # Number of batteries in parallel
INPUT_BMS_CAPACITY = 97  # Battery capacity (Ah)
INPUT_BMS_CURRENT = 98  # BMS battery current (A, /100, signed)
INPUT_BMS_FAULT_CODE = 99  # BMS fault code
INPUT_BMS_WARNING_CODE = 100  # BMS warning code

# BMS Cell Data (Addresses 101-107)
INPUT_BMS_MAX_CELL_VOLT = 101  # Maximum cell voltage (V, /1000)
INPUT_BMS_MIN_CELL_VOLT = 102  # Minimum cell voltage (V, /1000)
INPUT_BMS_MAX_CELL_TEMP = 103  # Maximum cell temperature (°C, /10, signed)
INPUT_BMS_MIN_CELL_TEMP = 104  # Minimum cell temperature (°C, /10, signed)
INPUT_BMS_FW_STATE = 105  # BMS firmware update state (bits 0-2), GenDryContact (bit 4)
INPUT_BMS_CYCLE_COUNT = 106  # Charge/discharge cycle count
INPUT_BMS_INV_VOLT_SAMPLE = 107  # Inverter-sampled battery voltage (V, /10)

# Additional Temperature Sensors (Addresses 108-112)
# Source: Yippy's documentation - may be BMS temperature sensors
INPUT_T1 = 108  # Temperature sensor 1 (°C, /10) - 12K BT temperature
INPUT_T2 = 109  # Temperature sensor 2 (°C, /10) - reserved
INPUT_T3 = 110  # Temperature sensor 3 (°C, /10) - reserved
INPUT_T4 = 111  # Temperature sensor 4 (°C, /10) - reserved
INPUT_T5 = 112  # Temperature sensor 5 (°C, /10) - reserved

# ============================================================================
# PARAMETER GROUPS FOR EFFICIENT READING
# ============================================================================
# Based on Modbus 40-register limitation and logical grouping

# Hold Register Groups (Configuration Parameters)
HOLD_REGISTER_GROUPS = {
    "system_config": (0, 20),  # System time, serial, communication
    "func_enable": (21, 21),  # Critical function enable register
    "grid_protection": (25, 58),  # Grid voltage/frequency limits
    "reactive_power": (59, 62),  # Reactive power control
    "ac_charge": (66, 73),  # AC charging configuration
    "forced_charge": (74, 81),  # Forced charge (ChgFirst) configuration
    "forced_discharge": (82, 89),  # Forced discharge configuration
    "battery_protection": (99, 109),  # Battery limits and protection
}

# Input Register Groups (Runtime Data)
INPUT_REGISTER_GROUPS = {
    "power_energy": (0, 31),  # Power metrics and voltages
    "energy_counters": (32, 60),  # Daily and lifetime energy
    "temperatures": (61, 75),  # Temperature and current sensors
    "advanced_status": (76, 106),  # Faults, SOH, PV energy breakdown
}

# ============================================================================
# WEB API PARAMETER NAME MAPPINGS
# ============================================================================
# Mapping between web frontend parameter names and Hold register addresses

WEB_PARAM_TO_HOLD_REGISTER = {
    "acChargePower": HOLD_AC_CHARGE_POWER_CMD,
    "acChargeSocLimit": HOLD_AC_CHARGE_SOC_LIMIT,
    "dischargeCutoffSoc": HOLD_DISCHG_CUT_OFF_SOC_EOD,
    "epsDischargeLimit": HOLD_SOC_LOW_LIMIT_EPS_DISCHG,
    "funcAcCharge": (FUNC_EN_REGISTER, FUNC_EN_BIT_AC_CHARGE_EN),
    "funcForcedCharge": (FUNC_EN_REGISTER, FUNC_EN_BIT_FORCED_CHG_EN),
    "funcForcedDischarge": (FUNC_EN_REGISTER, FUNC_EN_BIT_FORCED_DISCHG_EN),
    "operatingMode": (FUNC_EN_REGISTER, FUNC_EN_BIT_SET_TO_STANDBY),
}

# ============================================================================
# VERIFIED API REGISTER MAPPINGS (Live Testing)
# ============================================================================
# Source: Live API testing with 18KPV inverter (research/register_number_mapping.json)
# These mappings confirmed by querying individual registers (startRegister=N, pointNumber=1)
#
# NOTE: Parameter keys returned by API are DIFFERENT from register addresses!
#       Example: Register 66 returns "HOLD_AC_CHARGE_POWER_CMD", not "66"
#
# Parameter Key Prefixes:
#   HOLD_*   - Hold registers (configuration, read/write)
#   INPUT_*  - Input registers (runtime data, read-only)
#   FUNC_*   - Function enable bits (typically from register 21)
#   BIT_*    - Bit field values
#   MIDBOX_* - GridBOSS-specific parameters

# Register → API Parameter Key Mappings (18KPV, Verified via live testing)
# IMPORTANT: Each register is 16 bits. Bit field registers can have max 16 params.
REGISTER_TO_PARAM_KEYS: dict[int, list[str]] = {
    15: ["HOLD_COM_ADDR"],
    16: ["HOLD_LANGUAGE"],
    # Register 19: Device type code (single value, not bit fields)
    19: ["HOLD_DEVICE_TYPE_CODE"],
    20: ["HOLD_PV_INPUT_MODE"],
    # Register 21: Function enable bit field (16 bits, verified 100% match)
    21: [
        "FUNC_EPS_EN",  # Bit 0: Off-grid mode
        "FUNC_OVF_LOAD_DERATE_EN",  # Bit 1
        "FUNC_DRMS_EN",  # Bit 2
        "FUNC_LVRT_EN",  # Bit 3
        "FUNC_ANTI_ISLAND_EN",  # Bit 4
        "FUNC_NEUTRAL_DETECT_EN",  # Bit 5
        "FUNC_GRID_ON_POWER_SS_EN",  # Bit 6
        "FUNC_AC_CHARGE",  # Bit 7: AC charge enable
        "FUNC_SW_SEAMLESSLY_EN",  # Bit 8
        "FUNC_SET_TO_STANDBY",  # Bit 9: Standby mode (0=Standby, 1=On)
        "FUNC_FORCED_DISCHG_EN",  # Bit 10: Forced discharge
        "FUNC_FORCED_CHG_EN",  # Bit 11: Force charge
        "FUNC_ISO_EN",  # Bit 12
        "FUNC_GFCI_EN",  # Bit 13
        "FUNC_DCI_EN",  # Bit 14
        "FUNC_FEED_IN_GRID_EN",  # Bit 15
    ],
    # Register 22: PV start voltage (scalar, 0.1V units)
    # lxp_modbus ref: bits 0-14 = StartPVVolt, bit 15 = FeedInGridEn (but on EG4
    # hardware FeedInGridEn is register 21 bit 15, confirmed via live Modbus read).
    # Cloud API returns FUNC_LSP_* by reinterpreting this register's bits server-side;
    # those are NOT real Modbus bit fields for local writes.
    22: ["HOLD_START_PV_VOLT"],
    23: ["HOLD_CONNECT_TIME"],
    24: ["HOLD_RECONNECT_TIME"],
    25: ["HOLD_GRID_VOLT_CONN_LOW"],
    # Register 26: LSP whole-day schedule bit field
    26: [
        "FUNC_LSP_WHOLE_BYPASS_1_EN",  # Bit 0
        "FUNC_LSP_WHOLE_BYPASS_2_EN",  # Bit 1
        "FUNC_LSP_WHOLE_BYPASS_3_EN",  # Bit 2
        "FUNC_LSP_WHOLE_BAT_FIRST_1_EN",  # Bit 3
        "FUNC_LSP_WHOLE_BAT_FIRST_2_EN",  # Bit 4
        "FUNC_LSP_WHOLE_BAT_FIRST_3_EN",  # Bit 5
        "FUNC_LSP_WHOLE_SELF_CONSUMPTION_1_EN",  # Bit 6
        "FUNC_LSP_WHOLE_SELF_CONSUMPTION_2_EN",  # Bit 7
        "FUNC_LSP_WHOLE_SELF_CONSUMPTION_3_EN",  # Bit 8
        "FUNC_LSP_BATT_VOLT_OR_SOC",  # Bit 9
    ],
    27: ["HOLD_GRID_FREQ_CONN_LOW"],
    28: ["HOLD_GRID_FREQ_CONN_HIGH"],
    # Charge/Discharge power percent registers
    64: ["HOLD_CHG_POWER_PERCENT_CMD"],  # PV/Battery charge power (0-100%)
    65: ["HOLD_DISCHG_POWER_PERCENT_CMD"],  # Discharge power (0-100%)
    # AC Charge registers
    66: ["HOLD_AC_CHARGE_POWER_CMD"],  # AC charge power in 100W units (0-150 = 0.0-15.0 kW)
    67: ["HOLD_AC_CHARGE_SOC_LIMIT"],
    # AC charge schedule period-1 fields (validated against local Modbus entities)
    68: ["HOLD_AC_CHARGE_START_HOUR_1"],
    69: ["HOLD_AC_CHARGE_START_MINUTE_1"],
    70: ["HOLD_AC_CHARGE_END_HOUR_1"],
    71: ["HOLD_AC_CHARGE_END_MINUTE_1"],
    72: ["HOLD_AC_CHARGE_ENABLE_1"],
    73: ["HOLD_AC_CHARGE_ENABLE_2"],
    # Battery protection
    100: ["HOLD_LEAD_ACID_DISCHARGE_CUT_OFF_VOLT"],
    # Battery charge/discharge current limits (A, confirmed 2026-02-18)
    101: ["HOLD_LEAD_ACID_CHARGE_RATE"],
    102: ["HOLD_LEAD_ACID_DISCHARGE_RATE"],
    # SOC limits
    105: ["HOLD_DISCHG_CUT_OFF_SOC_EOD"],  # On-grid discharge cutoff SOC (10-90%)
    # System functions (Register 110: 14 bit fields, verified)
    110: [
        "FUNC_PV_GRID_OFF_EN",  # Bit 0
        "FUNC_RUN_WITHOUT_GRID",  # Bit 1
        "FUNC_MICRO_GRID_EN",  # Bit 2
        "FUNC_BAT_SHARED",  # Bit 3
        "FUNC_CHARGE_LAST",  # Bit 4
        "FUNC_TAKE_LOAD_TOGETHER",  # Bit 5 (swapped with bit 6)
        "FUNC_BUZZER_EN",  # Bit 6 (swapped with bit 5)
        "FUNC_GO_TO_OFFGRID",  # Bit 7
        "FUNC_GREEN_EN",  # Bit 8
        "FUNC_BATTERY_ECO_EN",  # Bit 9
        "BIT_WORKING_MODE",  # Bit 10 (multi-bit field?)
        "BIT_PVCT_SAMPLE_TYPE",  # Bit 11
        "BIT_PVCT_SAMPLE_RATIO",  # Bit 12
        "BIT_CT_SAMPLE_RATIO",  # Bit 13 (multi-bit field?)
    ],
    120: [
        "FUNC_HALF_HOUR_AC_CHG_START_EN",
        "FUNC_SNA_BAT_DISCHARGE_CONTROL",
        "FUNC_PHASE_INDEPEND_COMPENSATE_EN",
        "BIT_AC_CHARGE_TYPE",
        "BIT_DISCHG_CONTROL_TYPE",
        "BIT_ON_GRID_EOD_TYPE",
        "BIT_GENERATOR_CHARGE_TYPE",
    ],
    # Additional verified registers
    125: ["HOLD_SOC_LOW_LIMIT_EPS_DISCHG"],  # Off-grid SOC limit (verified 2026-01-27)
    150: ["HOLD_EQUALIZATION_PERIOD"],
    158: ["HOLD_AC_CHARGE_START_BATTERY_VOLTAGE"],
    159: ["HOLD_AC_CHARGE_END_BATTERY_VOLTAGE"],
    160: ["HOLD_AC_CHARGE_START_BATTERY_SOC"],
    190: ["HOLD_P2"],
    # Register 179: Extended function enable bit field (verified via Modbus probe 2026-02-13)
    # API returns 16 FUNC_* params for this register (alphabetical, NOT bit order).
    # Bit 7 (FUNC_GRID_PEAK_SHAVING) confirmed via live toggle test.
    # Bits 9,10 (FUNC_BAT_CHARGE/DISCHARGE_CONTROL) confirmed 2026-02-18 (SOC↔Voltage).
    # Other known params: FUNC_ACTIVE_POWER_LIMIT_MODE, FUNC_AC_COUPLING_FUNCTION,
    # FUNC_CT_DIRECTION_REVERSED,
    # FUNC_GEN_PEAK_SHAVING, FUNC_ON_GRID_ALWAYS_ON, FUNC_PV_ARC, FUNC_PV_ARC_FAULT_CLEAR,
    # FUNC_PV_SELL_TO_GRID_EN, FUNC_RSD_DISABLE, FUNC_SMART_LOAD_ENABLE,
    # FUNC_TOTAL_LOAD_COMPENSATION_EN, FUNC_TRIP_TIME_UNIT, FUNC_WATT_VOLT_EN
    179: [
        "FUNC_179_BIT0",  # Bit 0: unknown
        "FUNC_179_BIT1",  # Bit 1: unknown
        "FUNC_179_BIT2",  # Bit 2: unknown
        "FUNC_179_BIT3",  # Bit 3: unknown (set on FlexBOSS21)
        "FUNC_179_BIT4",  # Bit 4: unknown
        "FUNC_179_BIT5",  # Bit 5: unknown
        "FUNC_179_BIT6",  # Bit 6: unknown (set on FlexBOSS21)
        "FUNC_GRID_PEAK_SHAVING",  # Bit 7: Grid peak shaving (confirmed)
        "FUNC_179_BIT8",  # Bit 8: unknown
        "FUNC_BAT_CHARGE_CONTROL",  # Bit 9: 0=SOC, 1=Voltage (confirmed 2026-02-18)
        "FUNC_BAT_DISCHARGE_CONTROL",  # Bit 10: 0=SOC, 1=Voltage (confirmed 2026-02-18)
        "FUNC_179_BIT11",  # Bit 11: unknown
        "FUNC_179_BIT12",  # Bit 12: unknown
        "FUNC_179_BIT13",  # Bit 13: unknown
        "FUNC_179_BIT14",  # Bit 14: unknown
        "FUNC_179_BIT15",  # Bit 15: unknown
    ],
    # System charge limit (verified via live testing 2026-01-27)
    227: ["HOLD_SYSTEM_CHARGE_SOC_LIMIT"],
    # System charge voltage limit (V, ×10, confirmed 2026-02-18)
    228: ["HOLD_SYSTEM_CHARGE_VOLT_LIMIT"],
    # Grid peak shaving power (2 registers, 32-bit value in kW)
    231: ["_12K_HOLD_GRID_PEAK_SHAVING_POWER"],
    # Register 233: Extended function enable 2 bit field (verified via Modbus probe 2026-02-13)
    # API returns 9 params for this register (alphabetical, NOT bit order).
    # Bit 1 (FUNC_BATTERY_BACKUP_CTRL) confirmed via live toggle test.
    # Bit 12 (FUNC_SPORADIC_CHARGE) confirmed via web UI toggle + Modbus read (0→4096, 4096→0).
    # Other known params: BIT_DRY_CONTRACTOR_MULTIPLEX, BIT_LCD_TYPE, BIT_OUT_CT_POSITION,
    # FUNC_BATTERY_CALIBRATION_EN, FUNC_ENERTEK_WORKING_MODE, FUNC_FAN_DC3
    233: [
        "FUNC_233_BIT0",  # Bit 0: unknown
        "FUNC_BATTERY_BACKUP_CTRL",  # Bit 1: Battery backup control (confirmed)
        "FUNC_233_BIT2",  # Bit 2: unknown
        "FUNC_233_BIT3",  # Bit 3: unknown
        "FUNC_233_BIT4",  # Bit 4: unknown
        "FUNC_233_BIT5",  # Bit 5: unknown
        "FUNC_233_BIT6",  # Bit 6: unknown
        "FUNC_233_BIT7",  # Bit 7: unknown
        "FUNC_233_BIT8",  # Bit 8: unknown
        "FUNC_233_BIT9",  # Bit 9: unknown
        "FUNC_233_BIT10",  # Bit 10: unknown
        "FUNC_233_BIT11",  # Bit 11: unknown
        "FUNC_SPORADIC_CHARGE",  # Bit 12: Sporadic charge enable (confirmed)
        "FUNC_233_BIT13",  # Bit 13: unknown
        "FUNC_233_BIT14",  # Bit 14: unknown
        "FUNC_233_BIT15",  # Bit 15: unknown
    ],
}

# Reverse mapping: API Parameter Key → Register (for 18KPV)
# Note: Some parameters appear in multiple registers (bit fields)
PARAM_KEY_TO_REGISTER: dict[str, int] = {
    param: reg for reg, params in REGISTER_TO_PARAM_KEYS.items() for param in params
}

# Statistics (18KPV verified via live API testing)
REGISTER_STATS = {
    "total_registers_queried": 200,  # Registers 0-199
    "registers_with_parameters": 147,  # Registers that returned parameter keys
    "empty_registers": 49,  # Registers with no parameters
    "error_registers": 4,  # Registers that returned errors
    "total_unique_parameters": 488,  # From all 3 ranges combined
}

# ============================================================================
# GRIDBOSS PARAMETER MAPPINGS (Range-based, Read via Web Interface)
# ============================================================================
# Source: Live GridBOSS testing using 3-range approach (research/register_mapping_complete.json)
# GridBOSS devices do NOT support individual register reads (pointNumber=1)
# Must use range reads: (0,127), (127,127), (240,127)
#
# Total: 557 unique parameters across 3 ranges
# - Range 1 (0-126): 189 parameters
# - Range 2 (127-253): 252 parameters
# - Range 3 (240-366): 144 parameters (134 MIDBOX-specific)
#
# MIDBOX Parameters: 159 unique parameters specific to GridBOSS
# - Smart Load control (SL_*)
# - AC Coupling (AC_COUPLE_*)
# - Generator control (GEN_*)

# All GridBOSS parameters (alphabetically sorted)
GRIDBOSS_PARAMETERS = [
    "BIT_AC_CHARGE_TYPE",
    "BIT_CT_SAMPLE_RATIO",
    "BIT_DEVICE_TYPE_ODM",
    "BIT_DISCHG_CONTROL_TYPE",
    "BIT_DRY_CONTRACTOR_MULTIPLEX",
    "BIT_FAN_1_MAX_SPEED",
    "BIT_FAN_2_MAX_SPEED",
    "BIT_FAN_3_MAX_SPEED",
    "BIT_FAN_4_MAX_SPEED",
    "BIT_FAN_5_MAX_SPEED",
    "BIT_GENERATOR_CHARGE_TYPE",
    "BIT_LCD_TYPE",
    "BIT_MACHINE_TYPE",
    "BIT_METER_NUMBER",
    "BIT_METER_PHASE",
    "BIT_MIDBOX_SP_MODE_1",
    "BIT_MIDBOX_SP_MODE_2",
    "BIT_MIDBOX_SP_MODE_3",
    "BIT_MIDBOX_SP_MODE_4",
    "BIT_ON_GRID_EOD_TYPE",
    "BIT_OUT_CT_POSITION",
    "BIT_PVCT_SAMPLE_RATIO",
    "BIT_PVCT_SAMPLE_TYPE",
    "BIT_WATT_NODE_UPDATE_FREQUENCY",
    "BIT_WORKING_MODE",
    "FUNC_ACTIVE_POWER_LIMIT_MODE",
    "FUNC_AC_CHARGE",
    "FUNC_AC_COUPLE_DARK_START_EN",
    "FUNC_AC_COUPLE_EN_1",
    "FUNC_AC_COUPLE_EN_2",
    "FUNC_AC_COUPLE_EN_3",
    "FUNC_AC_COUPLE_EN_4",
    "FUNC_AC_COUPLE_ON_EPS_PORT_EN",
    "FUNC_AC_COUPLING_FUNCTION",
    "FUNC_ANTI_ISLAND_EN",
    "FUNC_BATTERY_BACKUP_CTRL",
    "FUNC_BATTERY_CALIBRATION_EN",
    "FUNC_BATTERY_ECO_EN",
    "FUNC_BAT_CHARGE_CONTROL",
    "FUNC_BAT_DISCHARGE_CONTROL",
    "FUNC_BAT_SHARED",
    "FUNC_BUZZER_EN",
    "FUNC_CHARGE_LAST",
    "FUNC_CT_DIRECTION_REVERSED",
    "FUNC_DCI_EN",
    "FUNC_DRMS_EN",
    "FUNC_ENERTEK_WORKING_MODE",
    "FUNC_EPS_EN",
    "FUNC_FAN_SPEED_SLOPE_CTRL_1",
    "FUNC_FAN_SPEED_SLOPE_CTRL_2",
    "FUNC_FAN_SPEED_SLOPE_CTRL_3",
    "FUNC_FAN_SPEED_SLOPE_CTRL_4",
    "FUNC_FAN_SPEED_SLOPE_CTRL_5",
    "FUNC_FEED_IN_GRID_EN",
    "FUNC_FORCED_CHG_EN",
    "FUNC_FORCED_DISCHG_EN",
    "FUNC_GEN_CTRL",
    "FUNC_GEN_PEAK_SHAVING",
    "FUNC_GFCI_EN",
    "FUNC_GO_TO_OFFGRID",
    "FUNC_GREEN_EN",
    "FUNC_GRID_CT_CONNECTION_EN",
    "FUNC_GRID_ON_POWER_SS_EN",
    "FUNC_GRID_PEAK_SHAVING",
    "FUNC_HALF_HOUR_AC_CHG_START_EN",
    "FUNC_ISO_EN",
    "FUNC_LSP_AC_CHARGE",
    "FUNC_LSP_BATT_VOLT_OR_SOC",
    "FUNC_LSP_BAT_ACTIVATION_EN",
    "FUNC_LSP_BAT_FIRST_10_EN",
    "FUNC_LSP_BAT_FIRST_11_EN",
    "FUNC_LSP_BAT_FIRST_12_EN",
    "FUNC_LSP_BAT_FIRST_13_EN",
    "FUNC_LSP_BAT_FIRST_14_EN",
    "FUNC_LSP_BAT_FIRST_15_EN",
    "FUNC_LSP_BAT_FIRST_16_EN",
    "FUNC_LSP_BAT_FIRST_17_EN",
    "FUNC_LSP_BAT_FIRST_18_EN",
    "FUNC_LSP_BAT_FIRST_19_EN",
    "FUNC_LSP_BAT_FIRST_1_EN",
    "FUNC_LSP_BAT_FIRST_20_EN",
    "FUNC_LSP_BAT_FIRST_21_EN",
    "FUNC_LSP_BAT_FIRST_22_EN",
    "FUNC_LSP_BAT_FIRST_23_EN",
    "FUNC_LSP_BAT_FIRST_24_EN",
    "FUNC_LSP_BAT_FIRST_25_EN",
    "FUNC_LSP_BAT_FIRST_26_EN",
    "FUNC_LSP_BAT_FIRST_27_EN",
    "FUNC_LSP_BAT_FIRST_28_EN",
    "FUNC_LSP_BAT_FIRST_29_EN",
    "FUNC_LSP_BAT_FIRST_2_EN",
    "FUNC_LSP_BAT_FIRST_30_EN",
    "FUNC_LSP_BAT_FIRST_31_EN",
    "FUNC_LSP_BAT_FIRST_32_EN",
    "FUNC_LSP_BAT_FIRST_33_EN",
    "FUNC_LSP_BAT_FIRST_34_EN",
    "FUNC_LSP_BAT_FIRST_35_EN",
    "FUNC_LSP_BAT_FIRST_36_EN",
    "FUNC_LSP_BAT_FIRST_37_EN",
    "FUNC_LSP_BAT_FIRST_38_EN",
    "FUNC_LSP_BAT_FIRST_39_EN",
    "FUNC_LSP_BAT_FIRST_3_EN",
    "FUNC_LSP_BAT_FIRST_40_EN",
    "FUNC_LSP_BAT_FIRST_41_EN",
    "FUNC_LSP_BAT_FIRST_42_EN",
    "FUNC_LSP_BAT_FIRST_43_EN",
    "FUNC_LSP_BAT_FIRST_44_EN",
    "FUNC_LSP_BAT_FIRST_45_EN",
    "FUNC_LSP_BAT_FIRST_46_EN",
    "FUNC_LSP_BAT_FIRST_47_EN",
    "FUNC_LSP_BAT_FIRST_48_EN",
    "FUNC_LSP_BAT_FIRST_4_EN",
    "FUNC_LSP_BAT_FIRST_5_EN",
    "FUNC_LSP_BAT_FIRST_6_EN",
    "FUNC_LSP_BAT_FIRST_7_EN",
    "FUNC_LSP_BAT_FIRST_8_EN",
    "FUNC_LSP_BAT_FIRST_9_EN",
    "FUNC_LSP_BYPASS_10_EN",
    "FUNC_LSP_BYPASS_11_EN",
    "FUNC_LSP_BYPASS_12_EN",
    "FUNC_LSP_BYPASS_13_EN",
    "FUNC_LSP_BYPASS_14_EN",
    "FUNC_LSP_BYPASS_15_EN",
    "FUNC_LSP_BYPASS_16_EN",
    "FUNC_LSP_BYPASS_17_EN",
    "FUNC_LSP_BYPASS_18_EN",
    "FUNC_LSP_BYPASS_19_EN",
    "FUNC_LSP_BYPASS_1_EN",
    "FUNC_LSP_BYPASS_20_EN",
    "FUNC_LSP_BYPASS_21_EN",
    "FUNC_LSP_BYPASS_22_EN",
    "FUNC_LSP_BYPASS_23_EN",
    "FUNC_LSP_BYPASS_24_EN",
    "FUNC_LSP_BYPASS_25_EN",
    "FUNC_LSP_BYPASS_26_EN",
    "FUNC_LSP_BYPASS_27_EN",
    "FUNC_LSP_BYPASS_28_EN",
    "FUNC_LSP_BYPASS_29_EN",
    "FUNC_LSP_BYPASS_2_EN",
    "FUNC_LSP_BYPASS_30_EN",
    "FUNC_LSP_BYPASS_31_EN",
    "FUNC_LSP_BYPASS_32_EN",
    "FUNC_LSP_BYPASS_33_EN",
    "FUNC_LSP_BYPASS_34_EN",
    "FUNC_LSP_BYPASS_35_EN",
    "FUNC_LSP_BYPASS_36_EN",
    "FUNC_LSP_BYPASS_37_EN",
    "FUNC_LSP_BYPASS_38_EN",
    "FUNC_LSP_BYPASS_39_EN",
    "FUNC_LSP_BYPASS_3_EN",
    "FUNC_LSP_BYPASS_40_EN",
    "FUNC_LSP_BYPASS_41_EN",
    "FUNC_LSP_BYPASS_42_EN",
    "FUNC_LSP_BYPASS_43_EN",
    "FUNC_LSP_BYPASS_44_EN",
    "FUNC_LSP_BYPASS_45_EN",
    "FUNC_LSP_BYPASS_46_EN",
    "FUNC_LSP_BYPASS_47_EN",
    "FUNC_LSP_BYPASS_48_EN",
    "FUNC_LSP_BYPASS_4_EN",
    "FUNC_LSP_BYPASS_5_EN",
    "FUNC_LSP_BYPASS_6_EN",
    "FUNC_LSP_BYPASS_7_EN",
    "FUNC_LSP_BYPASS_8_EN",
    "FUNC_LSP_BYPASS_9_EN",
    "FUNC_LSP_BYPASS_EN",
    "FUNC_LSP_BYPASS_MODE_EN",
    "FUNC_LSP_CHARGE_PRIORITY_EN",
    "FUNC_LSP_FAN_CHECK_EN",
    "FUNC_LSP_ISO_EN",
    "FUNC_LSP_LCD_REMOTE_DIS_CHG_EN",
    "FUNC_LSP_OUTPUT_10_EN",
    "FUNC_LSP_OUTPUT_11_EN",
    "FUNC_LSP_OUTPUT_12_EN",
    "FUNC_LSP_OUTPUT_1_EN",
    "FUNC_LSP_OUTPUT_2_EN",
    "FUNC_LSP_OUTPUT_3_EN",
    "FUNC_LSP_OUTPUT_4_EN",
    "FUNC_LSP_OUTPUT_5_EN",
    "FUNC_LSP_OUTPUT_6_EN",
    "FUNC_LSP_OUTPUT_7_EN",
    "FUNC_LSP_OUTPUT_8_EN",
    "FUNC_LSP_OUTPUT_9_EN",
    "FUNC_LSP_SELF_CONSUMPTION_EN",
    "FUNC_LSP_SET_TO_STANDBY",
    "FUNC_LSP_WHOLE_BAT_FIRST_1_EN",
    "FUNC_LSP_WHOLE_BAT_FIRST_2_EN",
    "FUNC_LSP_WHOLE_BAT_FIRST_3_EN",
    "FUNC_LSP_WHOLE_BYPASS_1_EN",
    "FUNC_LSP_WHOLE_BYPASS_2_EN",
    "FUNC_LSP_WHOLE_BYPASS_3_EN",
    "FUNC_LSP_WHOLE_DAY_SCHEDULE_EN",
    "FUNC_LSP_WHOLE_SELF_CONSUMPTION_1_EN",
    "FUNC_LSP_WHOLE_SELF_CONSUMPTION_2_EN",
    "FUNC_LSP_WHOLE_SELF_CONSUMPTION_3_EN",
    "FUNC_LVRT_EN",
    "FUNC_MICRO_GRID_EN",
    "FUNC_MIDBOX_EN",
    "FUNC_NEUTRAL_DETECT_EN",
    "FUNC_N_PE_CONNECT_INNER_EN",
    "FUNC_ON_GRID_ALWAYS_ON",
    "FUNC_OVF_LOAD_DERATE_EN",
    "FUNC_PARALLEL_DATA_SYNC_EN",
    "FUNC_PHASE_INDEPEND_COMPENSATE_EN",
    "FUNC_PV_ARC",
    "FUNC_PV_ARC_FAULT_CLEAR",
    "FUNC_PV_GRID_OFF_EN",
    "FUNC_PV_SELL_TO_GRID_EN",
    "FUNC_QUICK_CHARGE_CTRL",
    "FUNC_RETAIN_SHUTDOWN",
    "FUNC_RETAIN_STANDBY",
    "FUNC_RSD_DISABLE",
    "FUNC_RUN_WITHOUT_GRID",
    "FUNC_RUN_WITHOUT_GRID_12K",
    "FUNC_SET_TO_STANDBY",
    "FUNC_SHEDDING_MODE_EN_1",
    "FUNC_SHEDDING_MODE_EN_2",
    "FUNC_SHEDDING_MODE_EN_3",
    "FUNC_SHEDDING_MODE_EN_4",
    "FUNC_SMART_LOAD_ENABLE",
    "FUNC_SMART_LOAD_EN_1",
    "FUNC_SMART_LOAD_EN_2",
    "FUNC_SMART_LOAD_EN_3",
    "FUNC_SMART_LOAD_EN_4",
    "FUNC_SMART_LOAD_GRID_ON_1",
    "FUNC_SMART_LOAD_GRID_ON_2",
    "FUNC_SMART_LOAD_GRID_ON_3",
    "FUNC_SMART_LOAD_GRID_ON_4",
    "FUNC_SNA_BAT_DISCHARGE_CONTROL",
    "FUNC_SPORADIC_CHARGE",
    "FUNC_SW_SEAMLESSLY_EN",
    "FUNC_TAKE_LOAD_TOGETHER",
    "FUNC_TOTAL_LOAD_COMPENSATION_EN",
    "FUNC_TRIP_TIME_UNIT",
    "FUNC_WATT_NODE_CT_DIRECTION_A",
    "FUNC_WATT_NODE_CT_DIRECTION_B",
    "FUNC_WATT_NODE_CT_DIRECTION_C",
    "FUNC_WATT_VOLT_EN",
    "HOLD_ACTIVE_POWER_PERCENT_CMD",
    "HOLD_AC_CHARGE_BATTERY_CURRENT",
    "HOLD_AC_CHARGE_END_BATTERY_SOC",
    "HOLD_AC_CHARGE_END_BATTERY_VOLTAGE",
    "HOLD_AC_CHARGE_END_HOUR",
    "HOLD_AC_CHARGE_END_HOUR_1",
    "HOLD_AC_CHARGE_END_HOUR_2",
    "HOLD_AC_CHARGE_END_MINUTE",
    "HOLD_AC_CHARGE_END_MINUTE_1",
    "HOLD_AC_CHARGE_END_MINUTE_2",
    "HOLD_AC_CHARGE_POWER_CMD",
    "HOLD_AC_CHARGE_SOC_LIMIT",
    "HOLD_AC_CHARGE_START_BATTERY_SOC",
    "HOLD_AC_CHARGE_START_BATTERY_VOLTAGE",
    "HOLD_AC_CHARGE_START_HOUR",
    "HOLD_AC_CHARGE_START_HOUR_1",
    "HOLD_AC_CHARGE_START_HOUR_2",
    "HOLD_AC_CHARGE_START_MINUTE",
    "HOLD_AC_CHARGE_START_MINUTE_1",
    "HOLD_AC_CHARGE_START_MINUTE_2",
    "HOLD_AC_FIRST_END_HOUR",
    "HOLD_AC_FIRST_END_HOUR_1",
    "HOLD_AC_FIRST_END_HOUR_2",
    "HOLD_AC_FIRST_END_MINUTE",
    "HOLD_AC_FIRST_END_MINUTE_1",
    "HOLD_AC_FIRST_END_MINUTE_2",
    "HOLD_AC_FIRST_START_HOUR",
    "HOLD_AC_FIRST_START_HOUR_1",
    "HOLD_AC_FIRST_START_HOUR_2",
    "HOLD_AC_FIRST_START_MINUTE",
    "HOLD_AC_FIRST_START_MINUTE_1",
    "HOLD_AC_FIRST_START_MINUTE_2",
    "HOLD_BATTERY_LOW_TO_UTILITY_SOC",
    "HOLD_BATTERY_LOW_TO_UTILITY_VOLTAGE",
    "HOLD_BATTERY_WARNING_RECOVERY_SOC",
    "HOLD_BATTERY_WARNING_RECOVERY_VOLTAGE",
    "HOLD_BATTERY_WARNING_SOC",
    "HOLD_BATTERY_WARNING_VOLTAGE",
    "HOLD_CHARGE_POWER_PERCENT_CMD",
    "HOLD_COM_ADDR",
    "HOLD_CONNECT_TIME",
    "HOLD_CT_POWER_OFFSET",
    "HOLD_DEVICE_TYPE_CODE",
    "HOLD_DISCHG_CUT_OFF_SOC_EOD",
    "HOLD_DISCHG_POWER_PERCENT_CMD",
    "HOLD_EPS_FREQ_SET",
    "HOLD_EPS_VOLT_SET",
    "HOLD_EQUALIZATION_PERIOD",
    "HOLD_EQUALIZATION_TIME",
    "HOLD_EQUALIZATION_VOLTAGE",
    "HOLD_FEED_IN_GRID_POWER_PERCENT",
    "HOLD_FLOATING_VOLTAGE",
    "HOLD_FORCED_CHARGE_END_HOUR",
    "HOLD_FORCED_CHARGE_END_HOUR_1",
    "HOLD_FORCED_CHARGE_END_HOUR_2",
    "HOLD_FORCED_CHARGE_END_MINUTE",
    "HOLD_FORCED_CHARGE_END_MINUTE_1",
    "HOLD_FORCED_CHARGE_END_MINUTE_2",
    "HOLD_FORCED_CHARGE_START_HOUR",
    "HOLD_FORCED_CHARGE_START_HOUR_1",
    "HOLD_FORCED_CHARGE_START_HOUR_2",
    "HOLD_FORCED_CHARGE_START_MINUTE",
    "HOLD_FORCED_CHARGE_START_MINUTE_1",
    "HOLD_FORCED_CHARGE_START_MINUTE_2",
    "HOLD_FORCED_CHG_POWER_CMD",
    "HOLD_FORCED_CHG_SOC_LIMIT",
    "HOLD_FORCED_DISCHARGE_END_HOUR",
    "HOLD_FORCED_DISCHARGE_END_HOUR_1",
    "HOLD_FORCED_DISCHARGE_END_HOUR_2",
    "HOLD_FORCED_DISCHARGE_END_MINUTE",
    "HOLD_FORCED_DISCHARGE_END_MINUTE_1",
    "HOLD_FORCED_DISCHARGE_END_MINUTE_2",
    "HOLD_FORCED_DISCHARGE_START_HOUR",
    "HOLD_FORCED_DISCHARGE_START_HOUR_1",
    "HOLD_FORCED_DISCHARGE_START_HOUR_2",
    "HOLD_FORCED_DISCHARGE_START_MINUTE",
    "HOLD_FORCED_DISCHARGE_START_MINUTE_1",
    "HOLD_FORCED_DISCHARGE_START_MINUTE_2",
    "HOLD_FORCED_DISCHG_POWER_CMD",
    "HOLD_FORCED_DISCHG_SOC_LIMIT",
    "HOLD_FW_CODE",
    "HOLD_GRID_FREQ_CONN_HIGH",
    "HOLD_GRID_FREQ_CONN_LOW",
    "HOLD_GRID_FREQ_LIMIT1_HIGH",
    "HOLD_GRID_FREQ_LIMIT1_HIGH_TIME",
    "HOLD_GRID_FREQ_LIMIT1_LOW",
    "HOLD_GRID_FREQ_LIMIT1_LOW_TIME",
    "HOLD_GRID_FREQ_LIMIT2_HIGH",
    "HOLD_GRID_FREQ_LIMIT2_HIGH_TIME",
    "HOLD_GRID_FREQ_LIMIT2_LOW",
    "HOLD_GRID_FREQ_LIMIT2_LOW_TIME",
    "HOLD_GRID_FREQ_LIMIT3_HIGH",
    "HOLD_GRID_FREQ_LIMIT3_HIGH_TIME",
    "HOLD_GRID_FREQ_LIMIT3_LOW",
    "HOLD_GRID_FREQ_LIMIT3_LOW_TIME",
    "HOLD_GRID_VOLT_CONN_HIGH",
    "HOLD_GRID_VOLT_CONN_LOW",
    "HOLD_GRID_VOLT_LIMIT1_HIGH",
    "HOLD_GRID_VOLT_LIMIT1_HIGH_TIME",
    "HOLD_GRID_VOLT_LIMIT1_LOW",
    "HOLD_GRID_VOLT_LIMIT1_LOW_TIME",
    "HOLD_GRID_VOLT_LIMIT2_HIGH",
    "HOLD_GRID_VOLT_LIMIT2_HIGH_TIME",
    "HOLD_GRID_VOLT_LIMIT2_LOW",
    "HOLD_GRID_VOLT_LIMIT2_LOW_TIME",
    "HOLD_GRID_VOLT_LIMIT3_HIGH",
    "HOLD_GRID_VOLT_LIMIT3_HIGH_TIME",
    "HOLD_GRID_VOLT_LIMIT3_LOW",
    "HOLD_GRID_VOLT_LIMIT3_LOW_TIME",
    "HOLD_GRID_VOLT_MOV_AVG_HIGH",
    "HOLD_LANGUAGE",
    "HOLD_LEAD_ACID_CHARGE_RATE",
    "HOLD_LEAD_ACID_CHARGE_VOLT_REF",
    "HOLD_LEAD_ACID_DISCHARGE_CUT_OFF_VOLT",
    "HOLD_LEAD_ACID_DISCHARGE_RATE",
    "HOLD_LEAD_ACID_TEMPR_LOWER_LIMIT_CHG",
    "HOLD_LEAD_ACID_TEMPR_LOWER_LIMIT_DISCHG",
    "HOLD_LEAD_ACID_TEMPR_UPPER_LIMIT_CHG",
    "HOLD_LEAD_ACID_TEMPR_UPPER_LIMIT_DISCHG",
    "HOLD_LINE_MODE_INPUT",
    "HOLD_MAINTENANCE_COUNT",
    "HOLD_MAX_AC_INPUT_POWER",
    "HOLD_MAX_GENERATOR_INPUT_POWER",
    "HOLD_MAX_Q_PERCENT_FOR_QV",
    "HOLD_MIDBOX_AC_COUPLE_1_END_HOUR_1",
    "HOLD_MIDBOX_AC_COUPLE_1_END_HOUR_2",
    "HOLD_MIDBOX_AC_COUPLE_1_END_HOUR_3",
    "HOLD_MIDBOX_AC_COUPLE_1_END_MINUTE_1",
    "HOLD_MIDBOX_AC_COUPLE_1_END_MINUTE_2",
    "HOLD_MIDBOX_AC_COUPLE_1_END_MINUTE_3",
    "HOLD_MIDBOX_AC_COUPLE_1_START_HOUR_1",
    "HOLD_MIDBOX_AC_COUPLE_1_START_HOUR_2",
    "HOLD_MIDBOX_AC_COUPLE_1_START_HOUR_3",
    "HOLD_MIDBOX_AC_COUPLE_1_START_MINUTE_1",
    "HOLD_MIDBOX_AC_COUPLE_1_START_MINUTE_2",
    "HOLD_MIDBOX_AC_COUPLE_1_START_MINUTE_3",
    "HOLD_MIDBOX_AC_COUPLE_2_END_HOUR_1",
    "HOLD_MIDBOX_AC_COUPLE_2_END_HOUR_2",
    "HOLD_MIDBOX_AC_COUPLE_2_END_HOUR_3",
    "HOLD_MIDBOX_AC_COUPLE_2_END_MINUTE_1",
    "HOLD_MIDBOX_AC_COUPLE_2_END_MINUTE_2",
    "HOLD_MIDBOX_AC_COUPLE_2_END_MINUTE_3",
    "HOLD_MIDBOX_AC_COUPLE_2_START_HOUR_1",
    "HOLD_MIDBOX_AC_COUPLE_2_START_HOUR_2",
    "HOLD_MIDBOX_AC_COUPLE_2_START_HOUR_3",
    "HOLD_MIDBOX_AC_COUPLE_2_START_MINUTE_1",
    "HOLD_MIDBOX_AC_COUPLE_2_START_MINUTE_2",
    "HOLD_MIDBOX_AC_COUPLE_2_START_MINUTE_3",
    "HOLD_MIDBOX_AC_COUPLE_3_END_HOUR_1",
    "HOLD_MIDBOX_AC_COUPLE_3_END_HOUR_2",
    "HOLD_MIDBOX_AC_COUPLE_3_END_HOUR_3",
    "HOLD_MIDBOX_AC_COUPLE_3_END_MINUTE_1",
    "HOLD_MIDBOX_AC_COUPLE_3_END_MINUTE_2",
    "HOLD_MIDBOX_AC_COUPLE_3_END_MINUTE_3",
    "HOLD_MIDBOX_AC_COUPLE_3_START_HOUR_1",
    "HOLD_MIDBOX_AC_COUPLE_3_START_HOUR_2",
    "HOLD_MIDBOX_AC_COUPLE_3_START_HOUR_3",
    "HOLD_MIDBOX_AC_COUPLE_3_START_MINUTE_1",
    "HOLD_MIDBOX_AC_COUPLE_3_START_MINUTE_2",
    "HOLD_MIDBOX_AC_COUPLE_3_START_MINUTE_3",
    "HOLD_MIDBOX_AC_COUPLE_4_END_HOUR_1",
    "HOLD_MIDBOX_AC_COUPLE_4_END_HOUR_2",
    "HOLD_MIDBOX_AC_COUPLE_4_END_HOUR_3",
    "HOLD_MIDBOX_AC_COUPLE_4_END_MINUTE_1",
    "HOLD_MIDBOX_AC_COUPLE_4_END_MINUTE_2",
    "HOLD_MIDBOX_AC_COUPLE_4_END_MINUTE_3",
    "HOLD_MIDBOX_AC_COUPLE_4_START_HOUR_1",
    "HOLD_MIDBOX_AC_COUPLE_4_START_HOUR_2",
    "HOLD_MIDBOX_AC_COUPLE_4_START_HOUR_3",
    "HOLD_MIDBOX_AC_COUPLE_4_START_MINUTE_1",
    "HOLD_MIDBOX_AC_COUPLE_4_START_MINUTE_2",
    "HOLD_MIDBOX_AC_COUPLE_4_START_MINUTE_3",
    "HOLD_MIDBOX_SL_1_END_HOUR_1",
    "HOLD_MIDBOX_SL_1_END_HOUR_2",
    "HOLD_MIDBOX_SL_1_END_HOUR_3",
    "HOLD_MIDBOX_SL_1_END_MINUTE_1",
    "HOLD_MIDBOX_SL_1_END_MINUTE_2",
    "HOLD_MIDBOX_SL_1_END_MINUTE_3",
    "HOLD_MIDBOX_SL_1_START_HOUR_1",
    "HOLD_MIDBOX_SL_1_START_HOUR_2",
    "HOLD_MIDBOX_SL_1_START_HOUR_3",
    "HOLD_MIDBOX_SL_1_START_MINUTE_1",
    "HOLD_MIDBOX_SL_1_START_MINUTE_2",
    "HOLD_MIDBOX_SL_1_START_MINUTE_3",
    "HOLD_MIDBOX_SL_2_END_HOUR_1",
    "HOLD_MIDBOX_SL_2_END_HOUR_2",
    "HOLD_MIDBOX_SL_2_END_HOUR_3",
    "HOLD_MIDBOX_SL_2_END_MINUTE_1",
    "HOLD_MIDBOX_SL_2_END_MINUTE_2",
    "HOLD_MIDBOX_SL_2_END_MINUTE_3",
    "HOLD_MIDBOX_SL_2_START_HOUR_1",
    "HOLD_MIDBOX_SL_2_START_HOUR_2",
    "HOLD_MIDBOX_SL_2_START_HOUR_3",
    "HOLD_MIDBOX_SL_2_START_MINUTE_1",
    "HOLD_MIDBOX_SL_2_START_MINUTE_2",
    "HOLD_MIDBOX_SL_2_START_MINUTE_3",
    "HOLD_MIDBOX_SL_3_END_HOUR_1",
    "HOLD_MIDBOX_SL_3_END_HOUR_2",
    "HOLD_MIDBOX_SL_3_END_HOUR_3",
    "HOLD_MIDBOX_SL_3_END_MINUTE_1",
    "HOLD_MIDBOX_SL_3_END_MINUTE_2",
    "HOLD_MIDBOX_SL_3_END_MINUTE_3",
    "HOLD_MIDBOX_SL_3_START_HOUR_1",
    "HOLD_MIDBOX_SL_3_START_HOUR_2",
    "HOLD_MIDBOX_SL_3_START_HOUR_3",
    "HOLD_MIDBOX_SL_3_START_MINUTE_1",
    "HOLD_MIDBOX_SL_3_START_MINUTE_2",
    "HOLD_MIDBOX_SL_3_START_MINUTE_3",
    "HOLD_MIDBOX_SL_4_END_HOUR_1",
    "HOLD_MIDBOX_SL_4_END_HOUR_2",
    "HOLD_MIDBOX_SL_4_END_HOUR_3",
    "HOLD_MIDBOX_SL_4_END_MINUTE_1",
    "HOLD_MIDBOX_SL_4_END_MINUTE_2",
    "HOLD_MIDBOX_SL_4_END_MINUTE_3",
    "HOLD_MIDBOX_SL_4_START_HOUR_1",
    "HOLD_MIDBOX_SL_4_START_HOUR_2",
    "HOLD_MIDBOX_SL_4_START_HOUR_3",
    "HOLD_MIDBOX_SL_4_START_MINUTE_1",
    "HOLD_MIDBOX_SL_4_START_MINUTE_2",
    "HOLD_MIDBOX_SL_4_START_MINUTE_3",
    "HOLD_MODEL",
    "HOLD_MODEL_batteryType",
    "HOLD_MODEL_leadAcidType",
    "HOLD_MODEL_lithiumType",
    "HOLD_MODEL_measurement",
    "HOLD_MODEL_meterBrand",
    "HOLD_MODEL_meterType",
    "HOLD_MODEL_powerRating",
    "HOLD_MODEL_rule",
    "HOLD_MODEL_ruleMask",
    "HOLD_MODEL_usVersion",
    "HOLD_MODEL_wirelessMeter",
    "HOLD_NOMINAL_BATTERY_VOLTAGE",
    "HOLD_OFFLINE_TIMEOUT",
    "HOLD_ON_GRID_EOD_VOLTAGE",
    "HOLD_OUTPUT_CONFIGURATION",
    "HOLD_PF_CMD",
    "HOLD_PF_CMD_TEXT",
    "HOLD_POWER_SOFT_START_SLOPE",
    "HOLD_P_TO_USER_START_DISCHG",
    "HOLD_REACTIVE_POWER_CMD_TYPE",
    "HOLD_REACTIVE_POWER_PERCENT_CMD",
    "HOLD_RECONNECT_TIME",
    "HOLD_SERIAL_NUM",
    "HOLD_SET_COMPOSED_PHASE",
    "HOLD_SET_MASTER_OR_SLAVE",
    "HOLD_SOC_LOW_LIMIT_EPS_DISCHG",
    "HOLD_SPEC_LOAD_COMPENSATE",
    "HOLD_START_PV_VOLT",
    "HOLD_TIME",
    "HOLD_V1H",
    "HOLD_V1L",
    "HOLD_V2H",
    "HOLD_V2L",
    "HOLD_VBAT_START_DERATING",
    "MIDBOX_HOLD_AC_END_SOC_1",
    "MIDBOX_HOLD_AC_END_SOC_2",
    "MIDBOX_HOLD_AC_END_SOC_3",
    "MIDBOX_HOLD_AC_END_SOC_4",
    "MIDBOX_HOLD_AC_END_VOLT_1",
    "MIDBOX_HOLD_AC_END_VOLT_2",
    "MIDBOX_HOLD_AC_END_VOLT_3",
    "MIDBOX_HOLD_AC_END_VOLT_4",
    "MIDBOX_HOLD_AC_START_SOC_1",
    "MIDBOX_HOLD_AC_START_SOC_2",
    "MIDBOX_HOLD_AC_START_SOC_3",
    "MIDBOX_HOLD_AC_START_SOC_4",
    "MIDBOX_HOLD_AC_START_VOLT_1",
    "MIDBOX_HOLD_AC_START_VOLT_2",
    "MIDBOX_HOLD_AC_START_VOLT_3",
    "MIDBOX_HOLD_AC_START_VOLT_4",
    "MIDBOX_HOLD_GEN_COOL_DOWN_TIME",
    "MIDBOX_HOLD_GEN_REMOTE_CTRL",
    "MIDBOX_HOLD_GEN_REMOTE_TURN_OFF_TIME",
    "MIDBOX_HOLD_GEN_VOLT_SOC_ENABLE",
    "MIDBOX_HOLD_GEN_WARN_UP_TIME",
    "MIDBOX_HOLD_SL_END_SOC_1",
    "MIDBOX_HOLD_SL_END_SOC_2",
    "MIDBOX_HOLD_SL_END_SOC_3",
    "MIDBOX_HOLD_SL_END_SOC_4",
    "MIDBOX_HOLD_SL_END_VOLT_1",
    "MIDBOX_HOLD_SL_END_VOLT_2",
    "MIDBOX_HOLD_SL_END_VOLT_3",
    "MIDBOX_HOLD_SL_END_VOLT_4",
    "MIDBOX_HOLD_SL_PS_END_SOC_1",
    "MIDBOX_HOLD_SL_PS_END_SOC_2",
    "MIDBOX_HOLD_SL_PS_END_SOC_3",
    "MIDBOX_HOLD_SL_PS_END_SOC_4",
    "MIDBOX_HOLD_SL_PS_END_VOLT_1",
    "MIDBOX_HOLD_SL_PS_END_VOLT_2",
    "MIDBOX_HOLD_SL_PS_END_VOLT_3",
    "MIDBOX_HOLD_SL_PS_END_VOLT_4",
    "MIDBOX_HOLD_SL_PS_START_SOC_1",
    "MIDBOX_HOLD_SL_PS_START_SOC_2",
    "MIDBOX_HOLD_SL_PS_START_SOC_3",
    "MIDBOX_HOLD_SL_PS_START_SOC_4",
    "MIDBOX_HOLD_SL_PS_START_VOLT_1",
    "MIDBOX_HOLD_SL_PS_START_VOLT_2",
    "MIDBOX_HOLD_SL_PS_START_VOLT_3",
    "MIDBOX_HOLD_SL_PS_START_VOLT_4",
    "MIDBOX_HOLD_SL_START_PV_P_1",
    "MIDBOX_HOLD_SL_START_PV_P_2",
    "MIDBOX_HOLD_SL_START_PV_P_3",
    "MIDBOX_HOLD_SL_START_PV_P_4",
    "MIDBOX_HOLD_SL_START_SOC_1",
    "MIDBOX_HOLD_SL_START_SOC_2",
    "MIDBOX_HOLD_SL_START_SOC_3",
    "MIDBOX_HOLD_SL_START_SOC_4",
    "MIDBOX_HOLD_SL_START_VOLT_1",
    "MIDBOX_HOLD_SL_START_VOLT_2",
    "MIDBOX_HOLD_SL_START_VOLT_3",
    "MIDBOX_HOLD_SL_START_VOLT_4",
    "MIDBOX_HOLD_SMART_PORT_MODE",
    "OFF_GRID_HOLD_GEN_CHG_END_SOC",
    "OFF_GRID_HOLD_GEN_CHG_END_VOLT",
    "OFF_GRID_HOLD_GEN_CHG_START_SOC",
    "OFF_GRID_HOLD_GEN_CHG_START_VOLT",
    "OFF_GRID_HOLD_MAX_GEN_CHG_BAT_CURR",
    "_12K_HOLD_LEAD_CAPACITY",
]

# Statistics (GridBOSS verified via live API testing with range reads)
GRIDBOSS_STATS = {
    "total_unique_parameters": 557,
    "range_1_parameters": 189,  # startRegister=0, pointNumber=127
    "range_2_parameters": 252,  # startRegister=127, pointNumber=127
    "range_3_parameters": 144,  # startRegister=240, pointNumber=127 (mostly MIDBOX)
    "midbox_specific_parameters": 159,  # Smart Load, AC Coupling, Generator control
}

# ============================================================================
# MODEL-SPECIFIC PARAMETER KEYS
# ============================================================================
# These parameters are only available on specific inverter model families.
# The feature detection system uses these to identify model capabilities.

# SNA Series (Split-phase, North America) - Device Type Code: 54
# These parameters are unique to SNA models like SNA12K-US
SNA_PARAMETERS = [
    # Discharge recovery hysteresis (prevents oscillation at SOC cutoff)
    "HOLD_DISCHG_RECOVERY_LAG_SOC",  # SOC hysteresis percentage
    "HOLD_DISCHG_RECOVERY_LAG_VOLT",  # Voltage hysteresis (÷10)
    # Quick charge configuration
    "SNA_HOLD_QUICK_CHARGE_MINUTE",  # Quick charge duration in minutes
    # Off-grid specific
    "OFF_GRID_HOLD_EPS_VOLT_SET",
    "OFF_GRID_HOLD_EPS_FREQ_SET",
]

# PV Series (High-voltage DC, US) - Device Type Code: 2092
# These parameters are available on 18KPV and similar models
PV_SERIES_PARAMETERS = [
    # Volt-Watt curve parameters
    "HOLD_VW_V1",
    "HOLD_VW_V2",
    "HOLD_VW_V3",
    "HOLD_VW_V4",
    "HOLD_VW_P1",
    "HOLD_VW_P2",
    "HOLD_VW_P3",
    "HOLD_VW_P4",
    # Grid peak shaving
    "_12K_HOLD_GRID_PEAK_SHAVING_POWER",
    # Parallel operation
    "HOLD_PARALLEL_REGISTER",
]

# LXP-EU Series (European) - Device Type Code: 12
# These parameters are available on LXP-EU 12K and similar models
LXP_EU_PARAMETERS = [
    # EU grid compliance
    "HOLD_EU_GRID_CODE",
    "HOLD_EU_COUNTRY_CODE",
]

# Device Type Code Constants (HOLD_DEVICE_TYPE_CODE register 19)
# These identify the specific inverter model/variant
DEVICE_TYPE_CODE_SNA = 54  # SNA Series (e.g., SNA12K-US, 12000XP, 6000XP)
DEVICE_TYPE_CODE_PV_SERIES = 2092  # PV Series (e.g., 12KPV, 18KPV)
DEVICE_TYPE_CODE_LXP_EU = 12  # LXP-EU Series (e.g., LXP-EU 12K)
DEVICE_TYPE_CODE_LXP_LB = 44  # LXP-LB Low-voltage Battery (LXP-US 8-10K)
DEVICE_TYPE_CODE_FLEXBOSS = 10284  # FlexBOSS Series (e.g., FlexBOSS21, FlexBOSS18)
DEVICE_TYPE_CODE_GRIDBOSS = 50  # GridBOSS/MIDbox (parallel group controller)


# ============================================================================
# HELPER FUNCTIONS FOR PARAMETER OPERATIONS
# ============================================================================


def get_func_en_bit_mask(bit_number: int) -> int:
    """Get bit mask for FuncEn register (address 21).

    Args:
        bit_number: Bit number (0-15)

    Returns:
        Bit mask (e.g., bit 7 returns 0x0080)
    """
    return 1 << bit_number


def set_func_en_bit(current_value: int, bit_number: int, enable: bool) -> int:
    """Set or clear a bit in FuncEn register.

    Args:
        current_value: Current register value
        bit_number: Bit number to modify
        enable: True to set bit, False to clear

    Returns:
        New register value
    """
    mask = get_func_en_bit_mask(bit_number)
    if enable:
        return current_value | mask
    return current_value & ~mask


def get_func_en_bit(value: int, bit_number: int) -> bool:
    """Get state of a specific bit in FuncEn register.

    Args:
        value: Register value
        bit_number: Bit number to check

    Returns:
        True if bit is set, False otherwise
    """
    mask = get_func_en_bit_mask(bit_number)
    return bool(value & mask)


# ============================================================================
# FAMILY-SPECIFIC PARAMETER MAPPINGS
# ============================================================================
# Different inverter families have different register-to-parameter mappings.
# The HTTP server handles this automatically, but local transports (Modbus/Dongle)
# need to map registers to parameter names locally.
#
# Known differences between families:
# - Register 15: SNA uses "HOLD_MODBUS_ADDRESS", PV_SERIES uses "HOLD_COM_ADDR"
# - Some registers exist in one family but not another (e.g., VOLT_WATT in PV_SERIES)
#
# The 18KPV (PV_SERIES) mapping is used as the default since it's the most complete.
# Parameter aliases are supported to handle naming differences across families.

# Parameter name aliases - maps alternative names to canonical names
# This allows users to use either name when reading/writing parameters
PARAM_ALIASES: dict[str, str] = {
    # Register 15 naming difference
    "HOLD_MODBUS_ADDRESS": "HOLD_COM_ADDR",  # SNA → PV_SERIES canonical name
    # Legacy AC charge voltage aliases
    "HOLD_AC_CHARGE_START_VOLTAGE": "HOLD_AC_CHARGE_START_BATTERY_VOLTAGE",
    "HOLD_AC_CHARGE_END_VOLTAGE": "HOLD_AC_CHARGE_END_BATTERY_VOLTAGE",
}

# Reverse alias mapping (canonical → alternatives)
PARAM_ALIASES_REVERSE: dict[str, list[str]] = {
    "HOLD_COM_ADDR": ["HOLD_MODBUS_ADDRESS"],
    "HOLD_AC_CHARGE_START_BATTERY_VOLTAGE": ["HOLD_AC_CHARGE_START_VOLTAGE"],
    "HOLD_AC_CHARGE_END_BATTERY_VOLTAGE": ["HOLD_AC_CHARGE_END_VOLTAGE"],
}


def resolve_param_alias(param_name: str) -> str:
    """Resolve a parameter name alias to its canonical name.

    Some parameters have different names across inverter families.
    This function normalizes to the canonical (PV_SERIES/18KPV) name.

    Args:
        param_name: Parameter name (may be an alias)

    Returns:
        Canonical parameter name

    Example:
        resolve_param_alias("HOLD_MODBUS_ADDRESS")  # Returns "HOLD_COM_ADDR"
        resolve_param_alias("HOLD_COM_ADDR")  # Returns "HOLD_COM_ADDR"
    """
    return PARAM_ALIASES.get(param_name, param_name)


def get_register_to_param_mapping(
    family: str | None = None,
) -> dict[int, list[str]]:
    """Get the register-to-parameter mapping for an inverter family.

    Currently all families share the same 18KPV-based mapping.  The *family*
    parameter is accepted for forward compatibility but has no effect yet.

    Args:
        family: Inverter family string (from InverterFamily enum value).
            Currently unused — all families return the same mapping.

    Returns:
        Dict mapping register address to list of parameter key names.
        For single-value registers, the list has one element.
        For bit-field registers (FUNC_*, BIT_*), the list has multiple elements
        representing each bit position.

    Example:
        mapping = get_register_to_param_mapping()
        param_keys = mapping.get(21)  # ["FUNC_EPS_EN", "FUNC_OVF_LOAD_DERATE_EN", ...]
    """
    # Currently all families use the 18KPV mapping as the base
    # The HTTP transport handles family-specific differences on the server side
    # For local transports, the 18KPV mapping covers most common parameters
    #
    # Future: Add family-specific overrides when they are documented
    # For SNA devices, the server returns "HOLD_MODBUS_ADDRESS" instead of
    # "HOLD_COM_ADDR" for register 15 - use PARAM_ALIASES to handle this
    _ = family  # Reserved for future family-specific mappings
    return REGISTER_TO_PARAM_KEYS


def get_param_to_register_mapping(
    family: str | None = None,
) -> dict[str, int]:
    """Get the parameter-to-register mapping for an inverter family.

    Reverse of :func:`get_register_to_param_mapping`, useful for converting
    parameter names back to register addresses when writing.

    Includes alias support: both canonical names and their aliases will map
    to the same register address.

    Args:
        family: Inverter family string (from InverterFamily enum value).
            Currently unused — all families return the same mapping.

    Returns:
        Dict mapping parameter key name to register address.
        Includes both canonical names and their aliases.

    Example:
        mapping = get_param_to_register_mapping("PV_SERIES")
        mapping.get("FUNC_EPS_EN")  # 21
        mapping.get("HOLD_MODBUS_ADDRESS")  # 15 (via alias)
    """
    # Build reverse mapping from the register-to-param mapping
    register_mapping = get_register_to_param_mapping(family)
    result = {param: reg for reg, params in register_mapping.items() for param in params}

    # Add aliases to the mapping so both names work
    for alias, canonical in PARAM_ALIASES.items():
        if canonical in result:
            result[alias] = result[canonical]

    return result
