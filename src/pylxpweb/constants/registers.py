"""Inverter parameter register definitions and mappings.

This module contains all hold register (configuration) and input register
(runtime data) definitions for Luxpower/EG4 inverters, plus GridBOSS/MID
device parameters.

Source: EG4-18KPV-12LV Modbus Protocol specification
"""

from __future__ import annotations

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

# AC Charge Parameters
HOLD_AC_CHARGE_POWER_CMD = 66  # AC charge power (0.0-15.0 kW)
HOLD_AC_CHARGE_SOC_LIMIT = 67  # AC charge SOC limit (0-100%)
HOLD_AC_CHARGE_START_HOUR_1 = 68  # Time period 1 start hour (0-23)
HOLD_AC_CHARGE_START_MIN_1 = 69  # Time period 1 start minute (0-59)
HOLD_AC_CHARGE_END_HOUR_1 = 70  # Time period 1 end hour (0-23)
HOLD_AC_CHARGE_END_MIN_1 = 71  # Time period 1 end minute (0-59)
HOLD_AC_CHARGE_ENABLE_1 = 72  # Time period 1 enable (0=Off, 1=On)
HOLD_AC_CHARGE_ENABLE_2 = 73  # Time period 2 enable (0=Off, 1=On)

# Discharge Parameters
HOLD_DISCHG_POWER_CMD = 74  # Discharge power command (0-100%)
HOLD_DISCHG_START_HOUR_1 = 75  # Discharge start hour 1 (0-23)
HOLD_DISCHG_START_MIN_1 = 76  # Discharge start minute 1 (0-59)
HOLD_DISCHG_END_HOUR_1 = 77  # Discharge end hour 1 (0-23)
HOLD_DISCHG_END_MIN_1 = 78  # Discharge end minute 1 (0-59)
HOLD_DISCHG_ENABLE_1 = 79  # Discharge enable 1 (0=Off, 1=On)

# Battery Protection Parameters
HOLD_BAT_VOLT_MAX_CHG = 99  # Battery max charge voltage (V, /100)
HOLD_BAT_VOLT_MIN_CHG = 100  # Battery min charge voltage (V, /100)
HOLD_BAT_VOLT_MAX_DISCHG = 101  # Battery max discharge voltage (V, /100)
HOLD_BAT_VOLT_MIN_DISCHG = 102  # Battery min discharge voltage (V, /100)
HOLD_MAX_CHG_CURR = 103  # Max charge current (A, /10)
HOLD_MAX_DISCHG_CURR = 104  # Max discharge current (A, /10)
HOLD_DISCHG_CUT_OFF_SOC_EOD = 105  # On-grid discharge cutoff SOC (10-90%)
HOLD_SOC_LOW_LIMIT_EPS_DISCHG = 106  # Off-grid SOC low limit (0-100%)

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
INPUT_STATUS = 0  # Device status code
INPUT_V_PV1 = 1  # PV1 voltage (V, /10)
INPUT_V_PV2 = 2  # PV2 voltage (V, /10)
INPUT_V_PV3 = 3  # PV3 voltage (V, /10)
INPUT_V_BAT = 4  # Battery voltage (V, /100)
INPUT_SOC = 5  # State of Charge (%)
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

# System Status (Addresses 32-60)
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
INPUT_I_BAT_LIMIT = 60  # Max charge current (A, /10)

# Temperature Sensors (Addresses 61-75)
INPUT_T_INNER = 61  # Internal temperature (°C)
INPUT_T_RADIATOR_1 = 62  # Radiator 1 temperature (°C)
INPUT_T_RADIATOR_2 = 63  # Radiator 2 temperature (°C)
INPUT_T_BAT = 64  # Battery temperature (°C)
INPUT_T_BAT_CONTROL = 65  # Battery control temp (°C)
INPUT_I_REC_R = 66  # Grid R-phase current (A, /100)
INPUT_I_REC_S = 67  # Grid S-phase current (A, /100)
INPUT_I_REC_T = 68  # Grid T-phase current (A, /100)
INPUT_I_INV_R = 69  # Inverter R-phase current (A, /100)
INPUT_I_INV_S = 70  # Inverter S-phase current (A, /100)
INPUT_I_INV_T = 71  # Inverter T-phase current (A, /100)
INPUT_I_PV1 = 72  # PV1 current (A, /100)
INPUT_I_PV2 = 73  # PV2 current (A, /100)
INPUT_I_PV3 = 74  # PV3 current (A, /100)
INPUT_I_BAT = 75  # Battery current (A, /100)

# Advanced Status (Addresses 76-106)
INPUT_INTERNAL_FAULT = (76, 77)  # Internal fault code (2 registers)
INPUT_FAULT_HISTORY_1 = (78, 79)  # Fault history 1 (2 registers)
INPUT_FAULT_HISTORY_2 = (80, 81)  # Fault history 2 (2 registers)
INPUT_FAULT_HISTORY_3 = (82, 83)  # Fault history 3 (2 registers)
INPUT_FAULT_HISTORY_4 = (84, 85)  # Fault history 4 (2 registers)
INPUT_FAULT_HISTORY_5 = (86, 87)  # Fault history 5 (2 registers)
INPUT_SOH = 88  # State of Health (%)
INPUT_BMS_FAULT = 89  # BMS fault code
INPUT_BMS_WARNING = 90  # BMS warning code
INPUT_E_PV1_ALL = (91, 92)  # Total PV1 energy (kWh, /10, 2 registers)
INPUT_E_PV2_ALL = (93, 94)  # Total PV2 energy (kWh, /10, 2 registers)
INPUT_E_PV3_ALL = (95, 96)  # Total PV3 energy (kWh, /10, 2 registers)
INPUT_E_PV1_DAY = (97, 98)  # Daily PV1 energy (kWh, /10, 2 registers)
INPUT_E_PV2_DAY = (99, 100)  # Daily PV2 energy (kWh, /10, 2 registers)
INPUT_E_PV3_DAY = (101, 102)  # Daily PV3 energy (kWh, /10, 2 registers)
INPUT_MAX_CHG_CURR = 103  # Max charge current (A, /10)
INPUT_MAX_DISCHG_CURR = 104  # Max discharge current (A, /10)
INPUT_CHARGE_VOLT_REF = 105  # Charge voltage reference (V, /100)
INPUT_DISCHARGE_VOLT_REF = 106  # Discharge voltage ref (V, /100)

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
    "discharge": (74, 89),  # Discharge configuration
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

# Register → API Parameter Key Mappings (18KPV, Verified)
REGISTER_TO_PARAM_KEYS_18KPV: dict[int, list[str]] = {
    15: ["HOLD_COM_ADDR"],
    16: ["HOLD_LANGUAGE"],
    19: ["HOLD_DEVICE_TYPE_CODE", "BIT_DEVICE_TYPE_ODM", "BIT_MACHINE_TYPE"],
    20: ["HOLD_PV_INPUT_MODE"],
    # Register 21: Critical function enable register (27 bit fields!)
    21: [
        "FUNC_EPS_EN",  # Bit 0: Off-grid mode
        "FUNC_OVF_LOAD_DERATE_EN",
        "FUNC_DRMS_EN",
        "FUNC_LVRT_EN",
        "FUNC_ANTI_ISLAND_EN",
        "FUNC_NEUTRAL_DETECT_EN",
        "FUNC_GRID_ON_POWER_SS_EN",
        "FUNC_AC_CHARGE",  # Bit 7: AC charge enable
        "FUNC_SW_SEAMLESSLY_EN",
        "FUNC_SET_TO_STANDBY",  # Bit 9: Standby mode (0=Standby, 1=On)
        "FUNC_FORCED_DISCHG_EN",  # Bit 10: Forced discharge
        "FUNC_FORCED_CHG_EN",  # Bit 11: Force charge
        "FUNC_ISO_EN",
        "FUNC_GFCI_EN",
        "FUNC_DCI_EN",
        "FUNC_FEED_IN_GRID_EN",
        "FUNC_LSP_SET_TO_STANDBY",
        "FUNC_LSP_ISO_EN",
        "FUNC_LSP_FAN_CHECK_EN",
        "FUNC_LSP_WHOLE_DAY_SCHEDULE_EN",
        "FUNC_LSP_LCD_REMOTE_DIS_CHG_EN",
        "FUNC_LSP_SELF_CONSUMPTION_EN",
        "FUNC_LSP_AC_CHARGE",
        "FUNC_LSP_BAT_ACTIVATION_EN",
        "FUNC_LSP_BYPASS_MODE_EN",
        "FUNC_LSP_BYPASS_EN",
        "FUNC_LSP_CHARGE_PRIORITY_EN",
    ],
    22: ["HOLD_START_PV_VOLT"],
    23: ["HOLD_CONNECT_TIME"],
    24: ["HOLD_RECONNECT_TIME"],
    25: ["HOLD_GRID_VOLT_CONN_LOW"],
    26: [
        "HOLD_GRID_VOLT_CONN_HIGH",
        "FUNC_LSP_WHOLE_BYPASS_1_EN",
        "FUNC_LSP_WHOLE_BYPASS_2_EN",
        "FUNC_LSP_WHOLE_BYPASS_3_EN",
        "FUNC_LSP_WHOLE_BAT_FIRST_1_EN",
        "FUNC_LSP_WHOLE_BAT_FIRST_2_EN",
        "FUNC_LSP_WHOLE_BAT_FIRST_3_EN",
        "FUNC_LSP_WHOLE_SELF_CONSUMPTION_1_EN",
        "FUNC_LSP_WHOLE_SELF_CONSUMPTION_2_EN",
        "FUNC_LSP_WHOLE_SELF_CONSUMPTION_3_EN",
        "FUNC_LSP_BATT_VOLT_OR_SOC",
    ],
    27: ["HOLD_GRID_FREQ_CONN_LOW"],
    28: ["HOLD_GRID_FREQ_CONN_HIGH"],
    # AC Charge registers
    66: ["HOLD_AC_CHARGE_POWER_CMD"],
    67: ["HOLD_AC_CHARGE_SOC_LIMIT"],
    70: ["HOLD_AC_CHARGE_START_HOUR_1", "HOLD_AC_CHARGE_START_MINUTE_1"],
    # Battery protection
    100: ["HOLD_LEAD_ACID_DISCHARGE_CUT_OFF_VOLT"],
    # System functions (Register 110: 14 bit fields)
    110: [
        "FUNC_PV_GRID_OFF_EN",
        "FUNC_RUN_WITHOUT_GRID",
        "FUNC_MICRO_GRID_EN",
        "FUNC_BAT_SHARED",
        "FUNC_CHARGE_LAST",
        "FUNC_BUZZER_EN",
        "FUNC_TAKE_LOAD_TOGETHER",
        "FUNC_GO_TO_OFFGRID",
        "FUNC_GREEN_EN",
        "FUNC_BATTERY_ECO_EN",
        "BIT_WORKING_MODE",
        "BIT_PVCT_SAMPLE_TYPE",
        "BIT_PVCT_SAMPLE_RATIO",
        "BIT_CT_SAMPLE_RATIO",
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
    150: ["HOLD_EQUALIZATION_PERIOD"],
    160: ["HOLD_AC_CHARGE_START_BATTERY_SOC"],
    190: ["HOLD_P2"],
}

# Reverse mapping: API Parameter Key → Register (for 18KPV)
# Note: Some parameters appear in multiple registers (bit fields)
PARAM_KEY_TO_REGISTER_18KPV: dict[str, int] = {
    param: reg for reg, params in REGISTER_TO_PARAM_KEYS_18KPV.items() for param in params
}

# Statistics (18KPV verified via live API testing)
REGISTER_STATS_18KPV = {
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
