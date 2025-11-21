"""Constants and mappings for Luxpower/EG4 API.

This module contains mapping tables extracted from the EG4 web interface
to convert between human-readable API values and the enum values required
for configuration updates.

These mappings were discovered by analyzing the HTML form at:
/WManage/web/config/plant/edit/{plant_id}
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

# Timezone mappings: Human-readable (from API) → Form enum (for POST)
# Source: Analyzed all 28 timezone options from the HTML form
TIMEZONE_MAP: dict[str, str] = {
    "GMT -12": "WEST12",
    "GMT -11": "WEST11",
    "GMT -10": "WEST10",
    "GMT -9": "WEST9",
    "GMT -8": "WEST8",
    "GMT -7": "WEST7",
    "GMT -6": "WEST6",
    "GMT -5": "WEST5",
    "GMT -4": "WEST4",
    "GMT -3": "WEST3",
    "GMT -2": "WEST2",
    "GMT -1": "WEST1",
    "GMT 0": "ZERO",
    "GMT +1": "EAST1",
    "GMT +2": "EAST2",
    "GMT +3": "EAST3",
    "GMT +3:30": "EAST3_30",
    "GMT +4": "EAST4",
    "GMT +5": "EAST5",
    "GMT +5:30": "EAST5_30",
    "GMT +6": "EAST6",
    "GMT +6:30": "EAST6_30",
    "GMT +7": "EAST7",
    "GMT +8": "EAST8",
    "GMT +9": "EAST9",
    "GMT +10": "EAST10",
    "GMT +11": "EAST11",
    "GMT +12": "EAST12",
}

# Reverse mapping: Form enum → Human-readable
TIMEZONE_REVERSE_MAP: dict[str, str] = {v: k for k, v in TIMEZONE_MAP.items()}

# Country mappings: Human-readable (from API) → Form enum (for POST)
# Source: Analyzed country options from HTML form (North America region shown)
# NOTE: This list is incomplete - only shows North American countries
# Additional countries would appear based on selected continent/region
COUNTRY_MAP: dict[str, str] = {
    "Canada": "CANADA",
    "United States of America": "UNITED_STATES_OF_AMERICA",
    "Mexico": "MEXICO",
    "Greenland": "GREENLAND",
}

# Reverse mapping: Form enum → Human-readable
COUNTRY_REVERSE_MAP: dict[str, str] = {v: k for k, v in COUNTRY_MAP.items()}

# Continent mappings: Human-readable → Form enum
# Source: All 6 continent options from HTML form
CONTINENT_MAP: dict[str, str] = {
    "Africa": "AFRICA",
    "Asia": "ASIA",
    "Europe": "EUROPE",
    "North America": "NORTH_AMERICA",
    "Oceania": "OCEANIA",
    "South America": "SOUTH_AMERICA",
}

CONTINENT_REVERSE_MAP: dict[str, str] = {v: k for k, v in CONTINENT_MAP.items()}

# Region mappings: Human-readable → Form enum
# Source: Region options from HTML form (context: North America continent)
# NOTE: Region options are hierarchical and depend on selected continent
REGION_MAP: dict[str, str] = {
    # North America regions (when continent = NORTH_AMERICA)
    "Caribbean": "CARIBBEAN",
    "Central America": "CENTRAL_AMERICA",
    "North America": "NORTH_AMERICA",
    # Additional regions would be discovered when exploring other continents
}

REGION_REVERSE_MAP: dict[str, str] = {v: k for k, v in REGION_MAP.items()}


def get_timezone_enum(human_readable: str) -> str:
    """Convert human-readable timezone to API enum.

    Args:
        human_readable: Timezone string like "GMT -8"

    Returns:
        API enum like "WEST8"

    Raises:
        ValueError: If timezone is not recognized
    """
    if human_readable in TIMEZONE_MAP:
        return TIMEZONE_MAP[human_readable]
    raise ValueError(f"Unknown timezone: {human_readable}")


def get_country_enum(human_readable: str) -> str:
    """Convert human-readable country to API enum.

    Args:
        human_readable: Country string like "United States of America"

    Returns:
        API enum like "UNITED_STATES_OF_AMERICA"

    Raises:
        ValueError: If country is not recognized
    """
    if human_readable in COUNTRY_MAP:
        return COUNTRY_MAP[human_readable]
    raise ValueError(f"Unknown country: {human_readable}")


def get_region_enum(human_readable: str) -> str:
    """Convert human-readable region to API enum.

    Args:
        human_readable: Region string like "North America"

    Returns:
        API enum like "NORTH_AMERICA"

    Raises:
        ValueError: If region is not recognized
    """
    if human_readable in REGION_MAP:
        return REGION_MAP[human_readable]
    raise ValueError(f"Unknown region: {human_readable}")


def get_continent_enum(human_readable: str) -> str:
    """Convert human-readable continent to API enum.

    Args:
        human_readable: Continent string like "North America"

    Returns:
        API enum like "NORTH_AMERICA"

    Raises:
        ValueError: If continent is not recognized
    """
    if human_readable in CONTINENT_MAP:
        return CONTINENT_MAP[human_readable]
    raise ValueError(f"Unknown continent: {human_readable}")


# Static mapping for common countries (fast path)
# This covers the most frequently used countries to avoid API calls
COUNTRY_TO_LOCATION_STATIC: dict[str, tuple[str, str]] = {
    # North America
    "United States of America": ("NORTH_AMERICA", "NORTH_AMERICA"),
    "Canada": ("NORTH_AMERICA", "NORTH_AMERICA"),
    "Mexico": ("NORTH_AMERICA", "CENTRAL_AMERICA"),
    "Greenland": ("NORTH_AMERICA", "NORTH_AMERICA"),
    # Europe (common)
    "United Kingdom": ("EUROPE", "WESTERN_EUROPE"),
    "Germany": ("EUROPE", "CENTRAL_EUROPE"),
    "France": ("EUROPE", "WESTERN_EUROPE"),
    "Spain": ("EUROPE", "SOUTHERN_EUROPE"),
    "Italy": ("EUROPE", "SOUTHERN_EUROPE"),
    "The Netherlands": ("EUROPE", "WESTERN_EUROPE"),
    "Belgium": ("EUROPE", "WESTERN_EUROPE"),
    "Switzerland": ("EUROPE", "CENTRAL_EUROPE"),
    "Austria": ("EUROPE", "CENTRAL_EUROPE"),
    "Poland": ("EUROPE", "CENTRAL_EUROPE"),
    "Sweden": ("EUROPE", "NORDIC_EUROPE"),
    "Norway": ("EUROPE", "NORDIC_EUROPE"),
    "Denmark": ("EUROPE", "NORDIC_EUROPE"),
    # Asia (common)
    "China": ("ASIA", "EAST_ASIA"),
    "Japan": ("ASIA", "EAST_ASIA"),
    "South korea": ("ASIA", "EAST_ASIA"),
    "India": ("ASIA", "SOUTH_ASIA"),
    "Singapore": ("ASIA", "SOUTHEAST_ASIA"),
    "Thailand": ("ASIA", "SOUTHEAST_ASIA"),
    "Malaysia": ("ASIA", "SOUTHEAST_ASIA"),
    "Indonesia": ("ASIA", "SOUTHEAST_ASIA"),
    "Philippines": ("ASIA", "SOUTHEAST_ASIA"),
    "Vietnam": ("ASIA", "SOUTHEAST_ASIA"),
    # Oceania
    "Australia": ("OCEANIA", "OCEANIA"),
    "New Zealand": ("OCEANIA", "OCEANIA"),
    # South America
    "Brazil": ("SOUTH_AMERICA", "SA_EAST"),
    "Argentina": ("SOUTH_AMERICA", "SA_SOUTHERN_PART"),  # Note: API has "Aregntine" typo
    "Chile": ("SOUTH_AMERICA", "SA_SOUTHERN_PART"),
    # Africa (common)
    "South Africa": ("AFRICA", "SOUTH_AFRICA"),
    "Egypt": ("AFRICA", "NORTH_AFRICA"),
}


def get_continent_region_from_country(country_human: str) -> tuple[str, str]:
    """Derive continent and region enums from country name.

    Uses static mapping for common countries (fast path).
    For unknown countries, requires dynamic fetching from locale API.

    Args:
        country_human: Human-readable country name from API

    Returns:
        Tuple of (continent_enum, region_enum)

    Raises:
        ValueError: If country is not in static mapping (requires dynamic fetch)
    """
    # Fast path: check static mapping
    if country_human in COUNTRY_TO_LOCATION_STATIC:
        return COUNTRY_TO_LOCATION_STATIC[country_human]

    # Country not in static mapping - requires dynamic fetch
    raise ValueError(
        f"Country '{country_human}' not in static mapping. "
        "Dynamic fetching from locale API required."
    )


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
INPUT_E_INV_ALL = 36  # Total inverter energy (kWh, /10)
INPUT_E_REC_ALL = 37  # Total grid import energy (kWh, /10)
INPUT_E_CHG_ALL = 38  # Total charge energy (kWh, /10)
INPUT_E_DISCHG_ALL = 39  # Total discharge energy (kWh, /10)
INPUT_E_EPS_ALL = 40  # Total EPS energy (kWh, /10)
INPUT_E_TO_GRID_ALL = 41  # Total export energy (kWh, /10)
INPUT_E_TO_USER_ALL = 42  # Total load energy (kWh, /10)
INPUT_V_BUS1 = 43  # Bus 1 voltage (V, /10)
INPUT_V_BUS2 = 44  # Bus 2 voltage (V, /10)
INPUT_E_INV_DAY = (45, 46)  # Daily inverter energy (kWh, /10, 2 registers)
INPUT_E_REC_DAY = (47, 48)  # Daily grid import (kWh, /10, 2 registers)
INPUT_E_CHG_DAY = (49, 50)  # Daily charge energy (kWh, /10, 2 registers)
INPUT_E_DISCHG_DAY = (51, 52)  # Daily discharge energy (kWh, /10, 2 registers)
INPUT_E_EPS_DAY = (53, 54)  # Daily EPS energy (kWh, /10, 2 registers)
INPUT_E_TO_GRID_DAY = (55, 56)  # Daily export energy (kWh, /10, 2 registers)
INPUT_E_TO_USER_DAY = (57, 58)  # Daily load energy (kWh, /10, 2 registers)
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


# ============================================================================
# DATA SCALING CONSTANTS
# ============================================================================
# Centralized scaling configuration for all API data types.
# Source: Analysis of EG4 Web Monitor and actual API responses.
# Reference: docs/claude/PARAMETER_MAPPING_ANALYSIS.md
#
# **Design Rationale**:
# - Use dictionaries for O(1) lookup performance
# - Group by data source (runtime, energy, battery, etc.)
# - Include documentation for maintainability
# - Support both field-based and frozenset-based lookups


class ScaleFactor(int, Enum):
    """Enumeration of scaling factors used in API data.

    Values represent the divisor to apply to raw API values.
    Example: SCALE_10 means divide by 10 (e.g., 5300 → 530.0)
    """

    SCALE_10 = 10  # Divide by 10
    SCALE_100 = 100  # Divide by 100
    SCALE_1000 = 1000  # Divide by 1000
    SCALE_NONE = 1  # No scaling (direct value)


# ============================================================================
# INVERTER RUNTIME DATA SCALING
# ============================================================================
# Source: InverterRuntime model from getInverterRuntime endpoint
# Verified against: research/.../runtime_4512670118.json

INVERTER_RUNTIME_SCALING: dict[str, ScaleFactor] = {
    # PV Input Voltages (÷10: 5100 → 510.0V)
    "vpv1": ScaleFactor.SCALE_10,
    "vpv2": ScaleFactor.SCALE_10,
    "vpv3": ScaleFactor.SCALE_10,
    # AC Voltages (÷10: 2411 → 241.1V)
    "vacr": ScaleFactor.SCALE_10,
    "vacs": ScaleFactor.SCALE_10,
    "vact": ScaleFactor.SCALE_10,
    # EPS Voltages (÷10)
    "vepsr": ScaleFactor.SCALE_10,
    "vepss": ScaleFactor.SCALE_10,
    "vepst": ScaleFactor.SCALE_10,
    # Battery Voltage in Runtime (÷10: 530 → 53.0V)
    "vBat": ScaleFactor.SCALE_10,
    # Bus Voltages (÷100: 3703 → 37.03V)
    "vBus1": ScaleFactor.SCALE_100,
    "vBus2": ScaleFactor.SCALE_100,
    # AC Frequency (÷100: 5998 → 59.98Hz)
    "fac": ScaleFactor.SCALE_100,
    "feps": ScaleFactor.SCALE_100,
    # Generator Frequency (÷100)
    "genFreq": ScaleFactor.SCALE_100,
    # Generator Voltage (÷10)
    "genVolt": ScaleFactor.SCALE_10,
    # Currents (÷100: 1500 → 15.00A)
    "maxChgCurr": ScaleFactor.SCALE_100,
    "maxDischgCurr": ScaleFactor.SCALE_100,
    "maxChgCurrValue": ScaleFactor.SCALE_100,
    "maxDischgCurrValue": ScaleFactor.SCALE_100,
    # Power values - NO SCALING (direct Watts)
    "ppv1": ScaleFactor.SCALE_NONE,
    "ppv2": ScaleFactor.SCALE_NONE,
    "ppv3": ScaleFactor.SCALE_NONE,
    "ppv": ScaleFactor.SCALE_NONE,
    "pCharge": ScaleFactor.SCALE_NONE,
    "pDisCharge": ScaleFactor.SCALE_NONE,
    "batPower": ScaleFactor.SCALE_NONE,
    "pToGrid": ScaleFactor.SCALE_NONE,
    "pToUser": ScaleFactor.SCALE_NONE,
    "pinv": ScaleFactor.SCALE_NONE,
    "prec": ScaleFactor.SCALE_NONE,
    "peps": ScaleFactor.SCALE_NONE,
    "acCouplePower": ScaleFactor.SCALE_NONE,
    "genPower": ScaleFactor.SCALE_NONE,
    "consumptionPower114": ScaleFactor.SCALE_NONE,
    "consumptionPower": ScaleFactor.SCALE_NONE,
    "pEpsL1N": ScaleFactor.SCALE_NONE,
    "pEpsL2N": ScaleFactor.SCALE_NONE,
    # Temperature - NO SCALING (direct Celsius)
    "tinner": ScaleFactor.SCALE_NONE,
    "tradiator1": ScaleFactor.SCALE_NONE,
    "tradiator2": ScaleFactor.SCALE_NONE,
    "tBat": ScaleFactor.SCALE_NONE,
    # Percentages - NO SCALING
    "soc": ScaleFactor.SCALE_NONE,
    "seps": ScaleFactor.SCALE_NONE,
}


# ============================================================================
# ENERGY DATA SCALING
# ============================================================================
# Source: EnergyInfo model from getInverterEnergyInfo endpoint
# All energy values from API are in Wh×10, need ÷10 to get Wh, then ÷1000 for kWh

ENERGY_INFO_SCALING: dict[str, ScaleFactor] = {
    # Daily Energy (÷10 to get Wh: 90 → 9.0 Wh → 0.009 kWh)
    "todayYielding": ScaleFactor.SCALE_10,
    "todayCharging": ScaleFactor.SCALE_10,
    "todayDischarging": ScaleFactor.SCALE_10,
    "todayGridImport": ScaleFactor.SCALE_10,
    "todayUsage": ScaleFactor.SCALE_10,
    "todayExport": ScaleFactor.SCALE_10,
    # Monthly Energy (÷10 to get Wh)
    "monthYielding": ScaleFactor.SCALE_10,
    "monthCharging": ScaleFactor.SCALE_10,
    "monthDischarging": ScaleFactor.SCALE_10,
    "monthGridImport": ScaleFactor.SCALE_10,
    "monthUsage": ScaleFactor.SCALE_10,
    "monthExport": ScaleFactor.SCALE_10,
    # Yearly Energy (÷10 to get Wh)
    "yearYielding": ScaleFactor.SCALE_10,
    "yearCharging": ScaleFactor.SCALE_10,
    "yearDischarging": ScaleFactor.SCALE_10,
    "yearGridImport": ScaleFactor.SCALE_10,
    "yearUsage": ScaleFactor.SCALE_10,
    "yearExport": ScaleFactor.SCALE_10,
    # Lifetime Total Energy (÷10 to get Wh)
    "totalYielding": ScaleFactor.SCALE_10,
    "totalCharging": ScaleFactor.SCALE_10,
    "totalDischarging": ScaleFactor.SCALE_10,
    "totalGridImport": ScaleFactor.SCALE_10,
    "totalUsage": ScaleFactor.SCALE_10,
    "totalExport": ScaleFactor.SCALE_10,
}


# ============================================================================
# BATTERY DATA SCALING
# ============================================================================

# Battery Bank Aggregate (from BatteryInfo header)
BATTERY_BANK_SCALING: dict[str, ScaleFactor] = {
    # Aggregate voltage (÷10: 530 → 53.0V)
    "vBat": ScaleFactor.SCALE_10,
    # Power - NO SCALING (direct Watts)
    "pCharge": ScaleFactor.SCALE_NONE,
    "pDisCharge": ScaleFactor.SCALE_NONE,
    "batPower": ScaleFactor.SCALE_NONE,
    # Capacity (direct Ah)
    "maxBatteryCharge": ScaleFactor.SCALE_NONE,
    "currentBatteryCharge": ScaleFactor.SCALE_NONE,
    "remainCapacity": ScaleFactor.SCALE_NONE,
    "fullCapacity": ScaleFactor.SCALE_NONE,
    # Percentage - NO SCALING
    "soc": ScaleFactor.SCALE_NONE,
    "capacityPercent": ScaleFactor.SCALE_NONE,
}

# Individual Battery Module (from batteryArray)
BATTERY_MODULE_SCALING: dict[str, ScaleFactor] = {
    # Total voltage (÷100: 5305 → 53.05V)
    "totalVoltage": ScaleFactor.SCALE_100,
    # Current (÷10: 60 → 6.0A) **CRITICAL: Not ÷100**
    "current": ScaleFactor.SCALE_10,
    # Cell Voltages (÷1000: 3317 → 3.317V - millivolts)
    "batMaxCellVoltage": ScaleFactor.SCALE_1000,
    "batMinCellVoltage": ScaleFactor.SCALE_1000,
    # Cell Temperatures (÷10: 240 → 24.0°C)
    "batMaxCellTemp": ScaleFactor.SCALE_10,
    "batMinCellTemp": ScaleFactor.SCALE_10,
    "ambientTemp": ScaleFactor.SCALE_10,
    "mosTemp": ScaleFactor.SCALE_10,
    # Charge/Discharge Reference Values (÷100)
    "batChargeMaxCur": ScaleFactor.SCALE_100,
    "batChargeVoltRef": ScaleFactor.SCALE_100,
    # Percentages - NO SCALING
    "soc": ScaleFactor.SCALE_NONE,
    "soh": ScaleFactor.SCALE_NONE,
    "currentCapacityPercent": ScaleFactor.SCALE_NONE,
    # Capacity (direct Ah)
    "currentRemainCapacity": ScaleFactor.SCALE_NONE,
    "currentFullCapacity": ScaleFactor.SCALE_NONE,
    "maxBatteryCharge": ScaleFactor.SCALE_NONE,
    # Cycle Count - NO SCALING
    "cycleCnt": ScaleFactor.SCALE_NONE,
    # Cell Numbers - NO SCALING (integer indices)
    "batMaxCellNumTemp": ScaleFactor.SCALE_NONE,
    "batMinCellNumTemp": ScaleFactor.SCALE_NONE,
    "batMaxCellNumVolt": ScaleFactor.SCALE_NONE,
    "batMinCellNumVolt": ScaleFactor.SCALE_NONE,
}


# ============================================================================
# GRIDBOSS (MIDBOX) RUNTIME DATA SCALING
# ============================================================================
# Source: MIDBoxRuntime model from getMidboxRuntime endpoint
# NOTE: GridBOSS has different scaling than standard inverters

GRIDBOSS_RUNTIME_SCALING: dict[str, ScaleFactor] = {
    # Voltages (÷10)
    "gridVoltageR": ScaleFactor.SCALE_10,
    "gridVoltageS": ScaleFactor.SCALE_10,
    "gridVoltageT": ScaleFactor.SCALE_10,
    "loadVoltageR": ScaleFactor.SCALE_10,
    "loadVoltageS": ScaleFactor.SCALE_10,
    "loadVoltageT": ScaleFactor.SCALE_10,
    "genVoltageR": ScaleFactor.SCALE_10,
    "genVoltageS": ScaleFactor.SCALE_10,
    "genVoltageT": ScaleFactor.SCALE_10,
    # Currents (÷10: Different from standard inverter!)
    "gridCurrentR": ScaleFactor.SCALE_10,
    "gridCurrentS": ScaleFactor.SCALE_10,
    "gridCurrentT": ScaleFactor.SCALE_10,
    "loadCurrentR": ScaleFactor.SCALE_10,
    "loadCurrentS": ScaleFactor.SCALE_10,
    "loadCurrentT": ScaleFactor.SCALE_10,
    # Frequency (÷100)
    "gridFrequency": ScaleFactor.SCALE_100,
    "loadFrequency": ScaleFactor.SCALE_100,
    "genFrequency": ScaleFactor.SCALE_100,
    # Power - NO SCALING (direct Watts)
    "gridPower": ScaleFactor.SCALE_NONE,
    "loadPower": ScaleFactor.SCALE_NONE,
    "smartLoadPower": ScaleFactor.SCALE_NONE,
    "generatorPower": ScaleFactor.SCALE_NONE,
    # Energy (÷10 for Wh)
    "todayGridEnergy": ScaleFactor.SCALE_10,
    "todayLoadEnergy": ScaleFactor.SCALE_10,
    "totalGridEnergy": ScaleFactor.SCALE_10,
    "totalLoadEnergy": ScaleFactor.SCALE_10,
}


# ============================================================================
# INVERTER OVERVIEW DATA SCALING
# ============================================================================
# Source: InverterOverviewItem from inverterOverview/list endpoint

INVERTER_OVERVIEW_SCALING: dict[str, ScaleFactor] = {
    # Battery voltage (÷10: 530 → 53.0V)
    "vBat": ScaleFactor.SCALE_10,
    # Power - NO SCALING (direct Watts)
    "ppv": ScaleFactor.SCALE_NONE,
    "pCharge": ScaleFactor.SCALE_NONE,
    "pDisCharge": ScaleFactor.SCALE_NONE,
    "pConsumption": ScaleFactor.SCALE_NONE,
    # Energy totals (÷10 for Wh)
    "totalYielding": ScaleFactor.SCALE_10,
    "totalDischarging": ScaleFactor.SCALE_10,
    "totalExport": ScaleFactor.SCALE_10,
    "totalUsage": ScaleFactor.SCALE_10,
}


# ============================================================================
# PARAMETER DATA SCALING (Hold Registers)
# ============================================================================
# Scaling for parameter values read via remoteRead endpoint

PARAMETER_SCALING: dict[str, ScaleFactor] = {
    # Voltage Parameters (÷100)
    "HOLD_BAT_VOLT_MAX_CHG": ScaleFactor.SCALE_100,
    "HOLD_BAT_VOLT_MIN_CHG": ScaleFactor.SCALE_100,
    "HOLD_BAT_VOLT_MAX_DISCHG": ScaleFactor.SCALE_100,
    "HOLD_BAT_VOLT_MIN_DISCHG": ScaleFactor.SCALE_100,
    "HOLD_GRID_VOLT_HIGH_1": ScaleFactor.SCALE_10,
    "HOLD_GRID_VOLT_LOW_1": ScaleFactor.SCALE_10,
    "HOLD_LEAD_ACID_CHARGE_VOLT_REF": ScaleFactor.SCALE_100,
    "HOLD_LEAD_ACID_DISCHARGE_CUT_OFF_VOLT": ScaleFactor.SCALE_100,
    "HOLD_EQUALIZATION_VOLTAGE": ScaleFactor.SCALE_100,
    "HOLD_FLOATING_VOLTAGE": ScaleFactor.SCALE_100,
    "HOLD_EPS_VOLT_SET": ScaleFactor.SCALE_10,
    # Current Parameters (÷10)
    "HOLD_MAX_CHG_CURR": ScaleFactor.SCALE_10,
    "HOLD_MAX_DISCHG_CURR": ScaleFactor.SCALE_10,
    "HOLD_AC_CHARGE_BATTERY_CURRENT": ScaleFactor.SCALE_10,
    "OFF_GRID_HOLD_MAX_GEN_CHG_BAT_CURR": ScaleFactor.SCALE_10,
    # Frequency Parameters (÷100)
    "HOLD_GRID_FREQ_HIGH_1": ScaleFactor.SCALE_100,
    "HOLD_GRID_FREQ_LOW_1": ScaleFactor.SCALE_100,
    "HOLD_EPS_FREQ_SET": ScaleFactor.SCALE_100,
    # Power Parameters (direct Watts or percentage)
    "HOLD_AC_CHARGE_POWER_CMD": ScaleFactor.SCALE_NONE,  # Watts
    "HOLD_DISCHG_POWER_CMD": ScaleFactor.SCALE_NONE,  # Percentage (0-100)
    "HOLD_FEED_IN_GRID_POWER_PERCENT": ScaleFactor.SCALE_NONE,  # Percentage
    # SOC Parameters (percentage, no scaling)
    "HOLD_AC_CHARGE_SOC_LIMIT": ScaleFactor.SCALE_NONE,
    "HOLD_DISCHG_CUT_OFF_SOC_EOD": ScaleFactor.SCALE_NONE,
    "HOLD_SOC_LOW_LIMIT_EPS_DISCHG": ScaleFactor.SCALE_NONE,
    "HOLD_AC_CHARGE_START_BATTERY_SOC": ScaleFactor.SCALE_NONE,
    "HOLD_AC_CHARGE_END_BATTERY_SOC": ScaleFactor.SCALE_NONE,
    # Time Parameters (no scaling - hours/minutes)
    "HOLD_AC_CHARGE_START_HOUR_1": ScaleFactor.SCALE_NONE,
    "HOLD_AC_CHARGE_START_MIN_1": ScaleFactor.SCALE_NONE,
    "HOLD_AC_CHARGE_END_HOUR_1": ScaleFactor.SCALE_NONE,
    "HOLD_AC_CHARGE_END_MIN_1": ScaleFactor.SCALE_NONE,
}


# ============================================================================
# SCALING HELPER FUNCTIONS
# ============================================================================


def apply_scale(value: int | float, scale_factor: ScaleFactor) -> float:
    """Apply scaling factor to a value.

    Args:
        value: Raw value from API
        scale_factor: ScaleFactor enum indicating how to scale

    Returns:
        Scaled floating-point value

    Example:
        >>> apply_scale(5300, ScaleFactor.SCALE_10)
        530.0
        >>> apply_scale(3317, ScaleFactor.SCALE_1000)
        3.317
    """
    if scale_factor == ScaleFactor.SCALE_NONE:
        return float(value)
    return float(value) / float(scale_factor.value)


def get_scaling_for_field(
    field_name: str,
    data_type: Literal[
        "runtime", "energy", "battery_bank", "battery_module", "gridboss", "overview", "parameter"
    ],
) -> ScaleFactor:
    """Get the appropriate scaling factor for a field.

    Args:
        field_name: Name of the field (e.g., "vpv1", "totalVoltage")
        data_type: Type of data source

    Returns:
        ScaleFactor enum indicating how to scale the value

    Raises:
        KeyError: If field_name not found in the specified data type

    Example:
        >>> scale = get_scaling_for_field("vpv1", "runtime")
        >>> apply_scale(5100, scale)
        510.0
    """
    scaling_map = {
        "runtime": INVERTER_RUNTIME_SCALING,
        "energy": ENERGY_INFO_SCALING,
        "battery_bank": BATTERY_BANK_SCALING,
        "battery_module": BATTERY_MODULE_SCALING,
        "gridboss": GRIDBOSS_RUNTIME_SCALING,
        "overview": INVERTER_OVERVIEW_SCALING,
        "parameter": PARAMETER_SCALING,
    }

    return scaling_map[data_type][field_name]


def scale_runtime_value(field_name: str, value: int | float) -> float:
    """Convenience function to scale inverter runtime values.

    Args:
        field_name: Field name from InverterRuntime model
        value: Raw API value

    Returns:
        Scaled value
    """
    if field_name not in INVERTER_RUNTIME_SCALING:
        # Field doesn't need scaling (or unknown field)
        return float(value)
    return apply_scale(value, INVERTER_RUNTIME_SCALING[field_name])


def scale_battery_value(field_name: str, value: int | float) -> float:
    """Convenience function to scale battery module values.

    Args:
        field_name: Field name from BatteryModule model
        value: Raw API value

    Returns:
        Scaled value
    """
    if field_name not in BATTERY_MODULE_SCALING:
        return float(value)
    return apply_scale(value, BATTERY_MODULE_SCALING[field_name])


def scale_energy_value(field_name: str, value: int | float, to_kwh: bool = True) -> float:
    """Convenience function to scale energy values.

    Args:
        field_name: Field name from EnergyInfo model
        value: Raw API value
        to_kwh: If True, convert to kWh; if False, return Wh

    Returns:
        Scaled value in kWh (if to_kwh=True) or Wh

    Example:
        >>> scale_energy_value("todayYielding", 90, to_kwh=True)
        0.009  # kWh
        >>> scale_energy_value("todayYielding", 90, to_kwh=False)
        9.0  # Wh
    """
    if field_name not in ENERGY_INFO_SCALING:
        return float(value)

    # Apply API scaling (÷10 to get Wh)
    wh_value = apply_scale(value, ENERGY_INFO_SCALING[field_name])

    # Convert to kWh if requested
    if to_kwh:
        return wh_value / 1000.0
    return wh_value


# ==============================================================================
# Energy Sensor Classification
# ==============================================================================
# These constants classify energy sensors based on their reset behavior.
# This is critical for monotonic value enforcement and date boundary handling.
#
# Reference: EG4 Web Monitor integration sensor.py:38-49
# See: docs/SCALING_GUIDE.md for implementation details

# Sensors that should NEVER decrease (truly monotonic, lifetime values)
# These values accumulate over the device's entire lifetime and should never reset
LIFETIME_ENERGY_SENSORS: set[str] = {
    "totalYielding",  # Lifetime production (from InverterEnergyInfo)
    "eTotal",  # Total energy lifetime (alternative field name)
    "totalDischarging",  # Lifetime discharge energy
    "totalCharging",  # Lifetime charge energy
    "totalConsumption",  # Lifetime consumption energy
    "totalGridExport",  # Lifetime grid export
    "totalGridImport",  # Lifetime grid import
}

# Sensors that reset at date boundaries (midnight in station timezone)
# These values are cumulative within a day but reset to 0 at midnight
DAILY_ENERGY_SENSORS: set[str] = {
    "todayYielding",  # Today's production (from InverterEnergyInfo)
    "eToday",  # Today's energy (alternative field name)
    "todayDischarging",  # Today's discharge energy
    "todayCharging",  # Today's charge energy
    "todayConsumption",  # Today's consumption
    "todayGridExport",  # Today's grid export
    "todayGridImport",  # Today's grid import
}

# Sensors that reset at monthly boundaries
# These values accumulate over a month and reset on the 1st of each month
MONTHLY_ENERGY_SENSORS: set[str] = {
    "monthYielding",  # This month's production
    "monthDischarging",  # This month's discharge
    "monthCharging",  # This month's charge
    "monthConsumption",  # This month's consumption
    "monthGridExport",  # This month's grid export
    "monthGridImport",  # This month's grid import
}

# Battery-specific lifetime sensors (never reset)
BATTERY_LIFETIME_SENSORS: set[str] = {
    "cycleCount",  # Battery cycle count - monotonically increasing
}

# ==============================================================================
# HTTP Status Codes
# ==============================================================================
# Standard HTTP status codes used throughout the library
HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403

# ==============================================================================
# Device Type Constants
# ==============================================================================
# Device type identifiers from the Luxpower API
DEVICE_TYPE_INVERTER = 6  # Standard inverter
DEVICE_TYPE_GRIDBOSS = 9  # GridBOSS/MID device (parallel group controller)

# ==============================================================================
# Cache Configuration Constants
# ==============================================================================
# Time window (in minutes) before hour boundary to invalidate cache
# This ensures fresh data is fetched near the hour mark when energy values reset
CACHE_INVALIDATION_WINDOW_MINUTES = 5

# Minimum interval (in minutes) between cache invalidations
# Prevents excessive cache clearing during rapid refresh cycles
MIN_CACHE_INVALIDATION_INTERVAL_MINUTES = 10

# ==============================================================================
# Backoff and Retry Constants
# ==============================================================================
# Base delay (in seconds) for exponential backoff on API errors
BACKOFF_BASE_DELAY_SECONDS = 1.0

# Maximum delay (in seconds) for exponential backoff
BACKOFF_MAX_DELAY_SECONDS = 60.0

# ==============================================================================
# Timezone Parsing Constants
# ==============================================================================
# Factor to convert HHMM format timezone offset to hours/minutes
# Example: timezone offset 800 → 8 hours, 0 minutes (800 // 100 = 8, 800 % 100 = 0)
TIMEZONE_HHMM_HOURS_FACTOR = 100
TIMEZONE_HHMM_MINUTES_FACTOR = 100

# ==============================================================================
# MID Device Scaling Constants
# ==============================================================================
# Scaling factors for MID device (GridBOSS) values
# Note: These differ from standard inverter scaling factors
SCALE_MID_VOLTAGE = 10  # MID device voltages are scaled by 10
SCALE_MID_FREQUENCY = 100  # Frequency values are scaled by 100

# ==============================================================================
# SOC (State of Charge) Limits
# ==============================================================================
# Minimum and maximum allowed SOC percentage values
SOC_MIN_PERCENT = 0
SOC_MAX_PERCENT = 100

# ==============================================================================
# Register Reading Limits
# ==============================================================================
# Maximum number of registers that can be read in a single API call
# API limitation: Cannot read more than 127 registers at once
MAX_REGISTERS_PER_READ = 127


# ==============================================================================
# Helper Functions
# ==============================================================================


def parse_hhmm_timezone(value: int) -> tuple[int, int]:
    """Parse HHMM format timezone offset into hours and minutes.

    Args:
        value: Timezone offset in HHMM format (e.g., 800 for +8:00, -530 for -5:30)

    Returns:
        Tuple of (hours, minutes) with appropriate sign

    Examples:
        >>> parse_hhmm_timezone(800)
        (8, 0)
        >>> parse_hhmm_timezone(-530)
        (-5, 30)
        >>> parse_hhmm_timezone(-800)
        (-8, 0)
    """
    hours = abs(value) // TIMEZONE_HHMM_HOURS_FACTOR
    minutes = abs(value) % TIMEZONE_HHMM_MINUTES_FACTOR
    if value < 0:
        hours = -hours
    return hours, minutes


def scale_mid_voltage(raw_value: int | float) -> float:
    """Scale MID device voltage value from API format to volts.

    Args:
        raw_value: Raw voltage value from MID device API (scaled by 10)

    Returns:
        Voltage in volts (V)

    Example:
        >>> scale_mid_voltage(2400)
        240.0
    """
    return float(raw_value) / SCALE_MID_VOLTAGE


def scale_mid_frequency(raw_value: int | float) -> float:
    """Scale MID device frequency value from API format to Hz.

    Args:
        raw_value: Raw frequency value from MID device API (scaled by 100)

    Returns:
        Frequency in Hz

    Example:
        >>> scale_mid_frequency(5998)
        59.98
    """
    return float(raw_value) / SCALE_MID_FREQUENCY
