"""Constants and mappings for Luxpower/EG4 API.

This package contains constants, mappings, and helper functions for working
with the Luxpower/EG4 inverter API. The constants are organized into modules
for maintainability:

- locations: Timezone, country, continent, region mappings
- registers: Hold/input register definitions and bit manipulation
- scaling: Data scaling factors and conversion functions
- api: HTTP constants, backoff/retry configuration
- devices: Device types, limits, and parsing helpers

All symbols are re-exported from this package for backward compatibility,
so you can import from pylxpweb.constants directly:

    from pylxpweb.constants import HOLD_AC_CHARGE_POWER_CMD, ScaleFactor

Note: This package was refactored from a single large file (v0.3.x) into
      a modular structure (v0.4.0+) for better maintainability.
"""

from __future__ import annotations

# ============================================================================
# API MODULE
# ============================================================================
from .api import (
    # Backoff and retry
    BACKOFF_BASE_DELAY_SECONDS,
    BACKOFF_MAX_DELAY_SECONDS,
    DEVICE_TYPE_GRIDBOSS,
    # Device type constants
    DEVICE_TYPE_INVERTER,
    HTTP_FORBIDDEN,
    # HTTP status codes
    HTTP_OK,
    HTTP_UNAUTHORIZED,
    MAX_LOGIN_RETRIES,
    MAX_TRANSIENT_ERROR_RETRIES,
    TRANSIENT_ERROR_MESSAGES,
)

# ============================================================================
# DEVICES MODULE
# ============================================================================
from .devices import (
    # Register limits
    MAX_REGISTERS_PER_READ,
    SCALE_MID_FREQUENCY,
    # MID device scaling
    SCALE_MID_VOLTAGE,
    SOC_MAX_PERCENT,
    # SOC limits
    SOC_MIN_PERCENT,
    # Timezone parsing
    TIMEZONE_HHMM_HOURS_FACTOR,
    TIMEZONE_HHMM_MINUTES_FACTOR,
    parse_hhmm_timezone,
    scale_mid_current,
    scale_mid_frequency,
    scale_mid_voltage,
)

# Re-export all symbols from submodules for backward compatibility
# This ensures that existing code using `from pylxpweb.constants import X` continues to work
# ============================================================================
# LOCATIONS MODULE
# ============================================================================
from .locations import (
    # Continent mappings
    CONTINENT_MAP,
    CONTINENT_REVERSE_MAP,
    # Country mappings
    COUNTRY_MAP,
    COUNTRY_REVERSE_MAP,
    # Static country-to-location mapping
    COUNTRY_TO_LOCATION_STATIC,
    # Region mappings
    REGION_MAP,
    REGION_REVERSE_MAP,
    # Timezone mappings
    TIMEZONE_MAP,
    TIMEZONE_REVERSE_MAP,
    get_continent_enum,
    get_continent_region_from_country,
    get_country_enum,
    get_region_enum,
    # Helper functions
    get_timezone_enum,
)

# ============================================================================
# REGISTERS MODULE
# ============================================================================
from .registers import (
    AC_CHARGE_TYPE_MASK,
    AC_CHARGE_TYPE_SHIFT,
    AC_CHARGE_TYPE_SOC_VOLT,
    AC_CHARGE_TYPE_TIME,
    AC_CHARGE_TYPE_TIME_SOC_VOLT,
    BATTERY_STATUS_MAP,
    DEVICE_TYPE_CODE_FLEXBOSS,
    DEVICE_TYPE_CODE_GRIDBOSS,
    DEVICE_TYPE_CODE_LXP_EU,
    DEVICE_TYPE_CODE_LXP_LB,
    DEVICE_TYPE_CODE_PV_SERIES,
    DEVICE_TYPE_CODE_SNA,
    FUNC_EN_2_BIT_SPORADIC_CHARGE,
    # Extended function enable register 2
    FUNC_EN_2_REGISTER,
    FUNC_EN_BIT_AC_CHARGE_EN,
    FUNC_EN_BIT_EPS_EN,
    FUNC_EN_BIT_FORCED_CHG_EN,
    FUNC_EN_BIT_FORCED_DISCHG_EN,
    FUNC_EN_BIT_SET_TO_STANDBY,
    # Critical control register
    FUNC_EN_REGISTER,
    # GridBOSS parameters
    GRIDBOSS_PARAMETERS,
    GRIDBOSS_STATS,
    HOLD_AC_CHARGE_ENABLE_1,
    HOLD_AC_CHARGE_ENABLE_2,
    HOLD_AC_CHARGE_END_HOUR_1,
    HOLD_AC_CHARGE_END_MIN_1,
    HOLD_AC_CHARGE_END_VOLTAGE,
    # AC charge parameters
    HOLD_AC_CHARGE_POWER_CMD,
    HOLD_AC_CHARGE_SOC_LIMIT,
    HOLD_AC_CHARGE_START_HOUR_1,
    HOLD_AC_CHARGE_START_MIN_1,
    HOLD_AC_CHARGE_START_SOC,
    # AC Charge SOC/Voltage thresholds
    HOLD_AC_CHARGE_START_VOLTAGE,
    # AC Charge time schedule (packed time format)
    HOLD_AC_CHARGE_TIME_0_END,
    HOLD_AC_CHARGE_TIME_0_START,
    HOLD_AC_CHARGE_TIME_1_END,
    HOLD_AC_CHARGE_TIME_1_START,
    HOLD_AC_CHARGE_TIME_2_END,
    HOLD_AC_CHARGE_TIME_2_START,
    HOLD_AC_CHARGE_TYPE_REGISTER,
    # Battery protection parameters
    HOLD_BAT_VOLT_MAX_CHG,
    HOLD_BAT_VOLT_MAX_DISCHG,
    HOLD_BAT_VOLT_MIN_CHG,
    HOLD_BAT_VOLT_MIN_DISCHG,
    HOLD_BAUD_RATE,
    HOLD_DAY,
    HOLD_DISCHG_CUT_OFF_SOC_EOD,
    HOLD_DISCHG_ENABLE_1,
    HOLD_DISCHG_END_HOUR_1,
    HOLD_DISCHG_END_MIN_1,
    # Discharge parameters
    HOLD_DISCHG_POWER_CMD,
    HOLD_DISCHG_START_HOUR_1,
    HOLD_DISCHG_START_MIN_1,
    HOLD_GRID_FREQ_HIGH_1,
    HOLD_GRID_FREQ_LOW_1,
    # Grid protection parameters
    HOLD_GRID_VOLT_HIGH_1,
    HOLD_GRID_VOLT_LOW_1,
    HOLD_HOUR,
    HOLD_LANGUAGE,
    HOLD_MAX_CHG_CURR,
    HOLD_MAX_DISCHG_CURR,
    HOLD_MINUTE,
    HOLD_MODBUS_ADDRESS,
    HOLD_MONTH,
    # Reactive power control
    HOLD_Q_MODE,
    HOLD_Q_POWER,
    HOLD_Q_PV_MODE,
    HOLD_Q_PV_POWER,
    # Register groups
    HOLD_REGISTER_GROUPS,
    HOLD_SECOND,
    # System configuration
    HOLD_SERIAL_NUMBER_H,
    HOLD_SERIAL_NUMBER_L,
    HOLD_SOC_LOW_LIMIT_EPS_DISCHG,
    HOLD_YEAR,
    INPUT_BMS_CAPACITY,
    INPUT_BMS_CHARGE_VOLT_REF,
    INPUT_BMS_CURRENT,
    INPUT_BMS_CYCLE_COUNT,
    INPUT_BMS_DISCHG_CUT_VOLT,
    # BMS registers (renamed in v0.4.x for Yippy's documentation)
    INPUT_BMS_FAULT_CODE,
    INPUT_BMS_MAX_CELL_TEMP,
    INPUT_BMS_MAX_CELL_VOLT,
    INPUT_BMS_MAX_CHG_CURR,
    INPUT_BMS_MAX_DISCHG_CURR,
    INPUT_BMS_MIN_CELL_TEMP,
    INPUT_BMS_MIN_CELL_VOLT,
    INPUT_BMS_PARALLEL_NUM,
    INPUT_BMS_WARNING_CODE,
    INPUT_E_CHG_ALL,
    INPUT_E_CHG_DAY,
    INPUT_E_DISCHG_ALL,
    INPUT_E_DISCHG_DAY,
    INPUT_E_EPS_ALL,
    INPUT_E_EPS_DAY,
    INPUT_E_INV_ALL,
    INPUT_E_INV_DAY,
    INPUT_E_REC_ALL,
    INPUT_E_REC_DAY,
    INPUT_E_TO_GRID_ALL,
    INPUT_E_TO_GRID_DAY,
    INPUT_E_TO_USER_ALL,
    INPUT_E_TO_USER_DAY,
    INPUT_F_AC,
    INPUT_F_EPS,
    INPUT_FAULT_CODE,
    INPUT_FAULT_HISTORY_1,
    INPUT_I_BAT,
    INPUT_I_PV1,
    INPUT_I_PV2,
    INPUT_I_PV3,
    INPUT_INTERNAL_FAULT,
    INPUT_P_CHARGE,
    INPUT_P_DISCHARGE,
    INPUT_P_EPS,
    INPUT_P_INV,
    INPUT_P_PV1,
    INPUT_P_PV2,
    INPUT_P_PV3,
    INPUT_P_REC,
    INPUT_P_TO_GRID,
    INPUT_P_TO_USER,
    INPUT_PF,
    INPUT_REGISTER_GROUPS,
    INPUT_RUNNING_TIME,
    INPUT_S_EPS,
    INPUT_SOC_SOH,  # Packed: SOC (low byte) + SOH (high byte)
    # Input registers (runtime data)
    INPUT_STATUS,
    INPUT_T_BAT,
    INPUT_T_BAT_CONTROL,
    INPUT_T_INNER,
    INPUT_T_RADIATOR_1,
    INPUT_T_RADIATOR_2,
    INPUT_V_AC_R,
    INPUT_V_AC_S,
    INPUT_V_AC_T,
    INPUT_V_BAT,
    INPUT_V_BAT_LIMIT,
    INPUT_V_BUS1,
    INPUT_V_BUS2,
    INPUT_V_EPS_R,
    INPUT_V_EPS_S,
    INPUT_V_EPS_T,
    INPUT_V_PV1,
    INPUT_V_PV2,
    INPUT_V_PV3,
    INPUT_WARNING_CODE,
    LXP_EU_PARAMETERS,
    # Parameter aliases
    PARAM_ALIASES,
    PARAM_ALIASES_REVERSE,
    PARAM_KEY_TO_REGISTER,
    PV_SERIES_PARAMETERS,
    REGISTER_STATS,
    # Verified register mappings
    REGISTER_TO_PARAM_KEYS,
    # Model-specific parameters
    SNA_PARAMETERS,
    # Web parameter mappings
    WEB_PARAM_TO_HOLD_REGISTER,
    get_func_en_bit,
    # Bit manipulation functions
    get_func_en_bit_mask,
    # Family-specific parameter mappings
    get_param_to_register_mapping,
    get_register_to_param_mapping,
    resolve_param_alias,
    set_func_en_bit,
)

# ============================================================================
# SCALING MODULE
# ============================================================================
from .scaling import (
    BATTERY_BANK_SCALING,
    BATTERY_MODULE_SCALING,
    ENERGY_INFO_SCALING,
    GRIDBOSS_RUNTIME_SCALING,
    INVERTER_OVERVIEW_SCALING,
    # Scaling dictionaries
    INVERTER_RUNTIME_SCALING,
    PARAMETER_SCALING,
    # Scaling factor enum
    ScaleFactor,
    # Private but tested function (exported for backward compatibility)
    _get_scaling_for_field,
    # Scaling functions
    apply_scale,
    get_battery_field_precision,
    get_precision,
    # Packed time helpers (Modbus register format)
    pack_time,
    scale_battery_value,
    scale_energy_value,
    scale_runtime_value,
    unpack_time,
)

# ============================================================================
# __all__ DEFINITION
# ============================================================================
# Explicitly list all exported symbols for better IDE support and documentation

__all__ = [
    # Battery status
    "BATTERY_STATUS_MAP",
    # Locations
    "TIMEZONE_MAP",
    "TIMEZONE_REVERSE_MAP",
    "COUNTRY_MAP",
    "COUNTRY_REVERSE_MAP",
    "CONTINENT_MAP",
    "CONTINENT_REVERSE_MAP",
    "REGION_MAP",
    "REGION_REVERSE_MAP",
    "COUNTRY_TO_LOCATION_STATIC",
    "get_timezone_enum",
    "get_country_enum",
    "get_region_enum",
    "get_continent_enum",
    "get_continent_region_from_country",
    # AC charge type
    "AC_CHARGE_TYPE_SHIFT",
    "AC_CHARGE_TYPE_MASK",
    "AC_CHARGE_TYPE_TIME",
    "AC_CHARGE_TYPE_SOC_VOLT",
    "AC_CHARGE_TYPE_TIME_SOC_VOLT",
    "HOLD_AC_CHARGE_TYPE_REGISTER",
    # AC charge SOC/voltage thresholds
    "HOLD_AC_CHARGE_START_VOLTAGE",
    "HOLD_AC_CHARGE_END_VOLTAGE",
    "HOLD_AC_CHARGE_START_SOC",
    # Registers
    "FUNC_EN_REGISTER",
    "FUNC_EN_BIT_EPS_EN",
    "FUNC_EN_BIT_AC_CHARGE_EN",
    "FUNC_EN_BIT_SET_TO_STANDBY",
    "FUNC_EN_BIT_FORCED_DISCHG_EN",
    "FUNC_EN_BIT_FORCED_CHG_EN",
    "FUNC_EN_2_REGISTER",
    "FUNC_EN_2_BIT_SPORADIC_CHARGE",
    "HOLD_AC_CHARGE_POWER_CMD",
    "HOLD_AC_CHARGE_SOC_LIMIT",
    "HOLD_AC_CHARGE_START_HOUR_1",
    "HOLD_AC_CHARGE_START_MIN_1",
    "HOLD_AC_CHARGE_END_HOUR_1",
    "HOLD_AC_CHARGE_END_MIN_1",
    "HOLD_AC_CHARGE_ENABLE_1",
    "HOLD_AC_CHARGE_ENABLE_2",
    "HOLD_AC_CHARGE_TIME_0_START",
    "HOLD_AC_CHARGE_TIME_0_END",
    "HOLD_AC_CHARGE_TIME_1_START",
    "HOLD_AC_CHARGE_TIME_1_END",
    "HOLD_AC_CHARGE_TIME_2_START",
    "HOLD_AC_CHARGE_TIME_2_END",
    "HOLD_DISCHG_POWER_CMD",
    "HOLD_DISCHG_START_HOUR_1",
    "HOLD_DISCHG_START_MIN_1",
    "HOLD_DISCHG_END_HOUR_1",
    "HOLD_DISCHG_END_MIN_1",
    "HOLD_DISCHG_ENABLE_1",
    "HOLD_BAT_VOLT_MAX_CHG",
    "HOLD_BAT_VOLT_MIN_CHG",
    "HOLD_BAT_VOLT_MAX_DISCHG",
    "HOLD_BAT_VOLT_MIN_DISCHG",
    "HOLD_MAX_CHG_CURR",
    "HOLD_MAX_DISCHG_CURR",
    "HOLD_DISCHG_CUT_OFF_SOC_EOD",
    "HOLD_SOC_LOW_LIMIT_EPS_DISCHG",
    "HOLD_GRID_VOLT_HIGH_1",
    "HOLD_GRID_VOLT_LOW_1",
    "HOLD_GRID_FREQ_HIGH_1",
    "HOLD_GRID_FREQ_LOW_1",
    "HOLD_Q_MODE",
    "HOLD_Q_PV_MODE",
    "HOLD_Q_POWER",
    "HOLD_Q_PV_POWER",
    "HOLD_SERIAL_NUMBER_H",
    "HOLD_SERIAL_NUMBER_L",
    "HOLD_YEAR",
    "HOLD_MONTH",
    "HOLD_DAY",
    "HOLD_HOUR",
    "HOLD_MINUTE",
    "HOLD_SECOND",
    "HOLD_LANGUAGE",
    "HOLD_MODBUS_ADDRESS",
    "HOLD_BAUD_RATE",
    "INPUT_STATUS",
    "INPUT_V_PV1",
    "INPUT_V_PV2",
    "INPUT_V_PV3",
    "INPUT_V_BAT",
    "INPUT_SOC_SOH",  # Packed: SOC (low byte) + SOH (high byte)
    "INPUT_P_PV1",
    "INPUT_P_PV2",
    "INPUT_P_PV3",
    "INPUT_P_CHARGE",
    "INPUT_P_DISCHARGE",
    "INPUT_V_AC_R",
    "INPUT_V_AC_S",
    "INPUT_V_AC_T",
    "INPUT_F_AC",
    "INPUT_P_INV",
    "INPUT_P_REC",
    "INPUT_PF",
    "INPUT_V_EPS_R",
    "INPUT_V_EPS_S",
    "INPUT_V_EPS_T",
    "INPUT_F_EPS",
    "INPUT_P_EPS",
    "INPUT_S_EPS",
    "INPUT_P_TO_GRID",
    "INPUT_P_TO_USER",
    "INPUT_E_INV_ALL",
    "INPUT_E_REC_ALL",
    "INPUT_E_CHG_ALL",
    "INPUT_E_DISCHG_ALL",
    "INPUT_E_EPS_ALL",
    "INPUT_E_TO_GRID_ALL",
    "INPUT_E_TO_USER_ALL",
    "INPUT_V_BUS1",
    "INPUT_V_BUS2",
    "INPUT_E_INV_DAY",
    "INPUT_E_REC_DAY",
    "INPUT_E_CHG_DAY",
    "INPUT_E_DISCHG_DAY",
    "INPUT_E_EPS_DAY",
    "INPUT_E_TO_GRID_DAY",
    "INPUT_E_TO_USER_DAY",
    "INPUT_V_BAT_LIMIT",
    "INPUT_T_INNER",
    "INPUT_T_RADIATOR_1",
    "INPUT_T_RADIATOR_2",
    "INPUT_T_BAT",
    "INPUT_T_BAT_CONTROL",
    "INPUT_RUNNING_TIME",
    "INPUT_I_PV1",
    "INPUT_I_PV2",
    "INPUT_I_PV3",
    "INPUT_I_BAT",
    "INPUT_INTERNAL_FAULT",
    "INPUT_FAULT_HISTORY_1",
    "INPUT_FAULT_CODE",
    "INPUT_WARNING_CODE",
    # BMS registers (renamed in v0.4.x)
    "INPUT_BMS_FAULT_CODE",
    "INPUT_BMS_WARNING_CODE",
    "INPUT_BMS_MAX_CHG_CURR",
    "INPUT_BMS_MAX_DISCHG_CURR",
    "INPUT_BMS_CHARGE_VOLT_REF",
    "INPUT_BMS_DISCHG_CUT_VOLT",
    "INPUT_BMS_MAX_CELL_VOLT",
    "INPUT_BMS_MIN_CELL_VOLT",
    "INPUT_BMS_MAX_CELL_TEMP",
    "INPUT_BMS_MIN_CELL_TEMP",
    "INPUT_BMS_CYCLE_COUNT",
    "INPUT_BMS_PARALLEL_NUM",
    "INPUT_BMS_CAPACITY",
    "INPUT_BMS_CURRENT",
    "HOLD_REGISTER_GROUPS",
    "INPUT_REGISTER_GROUPS",
    "WEB_PARAM_TO_HOLD_REGISTER",
    "REGISTER_TO_PARAM_KEYS",
    "PARAM_KEY_TO_REGISTER",
    "REGISTER_STATS",
    "GRIDBOSS_PARAMETERS",
    "GRIDBOSS_STATS",
    # Model-specific parameters
    "SNA_PARAMETERS",
    "PV_SERIES_PARAMETERS",
    "LXP_EU_PARAMETERS",
    "DEVICE_TYPE_CODE_SNA",
    "DEVICE_TYPE_CODE_PV_SERIES",
    "DEVICE_TYPE_CODE_LXP_EU",
    "DEVICE_TYPE_CODE_LXP_LB",
    "DEVICE_TYPE_CODE_FLEXBOSS",
    "DEVICE_TYPE_CODE_GRIDBOSS",
    "get_func_en_bit_mask",
    "set_func_en_bit",
    "get_func_en_bit",
    # Family-specific parameter mappings
    "get_register_to_param_mapping",
    "get_param_to_register_mapping",
    # Parameter aliases
    "PARAM_ALIASES",
    "PARAM_ALIASES_REVERSE",
    "resolve_param_alias",
    # Scaling
    "ScaleFactor",
    "INVERTER_RUNTIME_SCALING",
    "ENERGY_INFO_SCALING",
    "BATTERY_BANK_SCALING",
    "BATTERY_MODULE_SCALING",
    "GRIDBOSS_RUNTIME_SCALING",
    "INVERTER_OVERVIEW_SCALING",
    "PARAMETER_SCALING",
    "apply_scale",
    "get_precision",
    "get_battery_field_precision",
    "pack_time",
    "unpack_time",
    "scale_runtime_value",
    "scale_battery_value",
    "scale_energy_value",
    "_get_scaling_for_field",
    # API
    "HTTP_OK",
    "HTTP_UNAUTHORIZED",
    "HTTP_FORBIDDEN",
    "BACKOFF_BASE_DELAY_SECONDS",
    "BACKOFF_MAX_DELAY_SECONDS",
    "MAX_LOGIN_RETRIES",
    "MAX_TRANSIENT_ERROR_RETRIES",
    "TRANSIENT_ERROR_MESSAGES",
    # Devices
    "DEVICE_TYPE_INVERTER",
    "DEVICE_TYPE_GRIDBOSS",
    "TIMEZONE_HHMM_HOURS_FACTOR",
    "TIMEZONE_HHMM_MINUTES_FACTOR",
    "parse_hhmm_timezone",
    "SCALE_MID_VOLTAGE",
    "SCALE_MID_CURRENT",
    "SCALE_MID_FREQUENCY",
    "scale_mid_voltage",
    "scale_mid_current",
    "scale_mid_frequency",
    "SOC_MIN_PERCENT",
    "SOC_MAX_PERCENT",
    "MAX_REGISTERS_PER_READ",
]
