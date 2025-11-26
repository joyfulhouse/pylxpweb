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
    # AC charge parameters
    HOLD_AC_CHARGE_POWER_CMD,
    HOLD_AC_CHARGE_SOC_LIMIT,
    HOLD_AC_CHARGE_START_HOUR_1,
    HOLD_AC_CHARGE_START_MIN_1,
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
    INPUT_BMS_FAULT,
    INPUT_BMS_WARNING,
    INPUT_CHARGE_VOLT_REF,
    INPUT_DISCHARGE_VOLT_REF,
    INPUT_E_CHG_ALL,
    INPUT_E_CHG_DAY,
    INPUT_E_DISCHG_ALL,
    INPUT_E_DISCHG_DAY,
    INPUT_E_EPS_ALL,
    INPUT_E_EPS_DAY,
    INPUT_E_INV_ALL,
    INPUT_E_INV_DAY,
    INPUT_E_PV1_ALL,
    INPUT_E_PV1_DAY,
    INPUT_E_PV2_ALL,
    INPUT_E_PV2_DAY,
    INPUT_E_PV3_ALL,
    INPUT_E_PV3_DAY,
    INPUT_E_REC_ALL,
    INPUT_E_REC_DAY,
    INPUT_E_TO_GRID_ALL,
    INPUT_E_TO_GRID_DAY,
    INPUT_E_TO_USER_ALL,
    INPUT_E_TO_USER_DAY,
    INPUT_F_AC,
    INPUT_F_EPS,
    INPUT_FAULT_HISTORY_1,
    INPUT_FAULT_HISTORY_2,
    INPUT_FAULT_HISTORY_3,
    INPUT_FAULT_HISTORY_4,
    INPUT_FAULT_HISTORY_5,
    INPUT_I_BAT,
    INPUT_I_BAT_LIMIT,
    INPUT_I_INV_R,
    INPUT_I_INV_S,
    INPUT_I_INV_T,
    INPUT_I_PV1,
    INPUT_I_PV2,
    INPUT_I_PV3,
    INPUT_I_REC_R,
    INPUT_I_REC_S,
    INPUT_I_REC_T,
    INPUT_INTERNAL_FAULT,
    INPUT_MAX_CHG_CURR,
    INPUT_MAX_DISCHG_CURR,
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
    INPUT_S_EPS,
    INPUT_SOC,
    INPUT_SOH,
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
    PARAM_KEY_TO_REGISTER_18KPV,
    REGISTER_STATS_18KPV,
    # Verified register mappings
    REGISTER_TO_PARAM_KEYS_18KPV,
    # Web parameter mappings
    WEB_PARAM_TO_HOLD_REGISTER,
    get_func_en_bit,
    # Bit manipulation functions
    get_func_en_bit_mask,
    set_func_en_bit,
)

# ============================================================================
# SCALING MODULE
# ============================================================================
from .scaling import (
    BATTERY_BANK_SCALING,
    BATTERY_LIFETIME_SENSORS,
    BATTERY_MODULE_SCALING,
    DAILY_ENERGY_SENSORS,
    ENERGY_INFO_SCALING,
    GRIDBOSS_RUNTIME_SCALING,
    INVERTER_OVERVIEW_SCALING,
    # Scaling dictionaries
    INVERTER_RUNTIME_SCALING,
    # Energy sensor classification
    LIFETIME_ENERGY_SENSORS,
    MONTHLY_ENERGY_SENSORS,
    PARAMETER_SCALING,
    # Scaling factor enum
    ScaleFactor,
    # Private but tested function (exported for backward compatibility)
    _get_scaling_for_field,
    # Scaling functions
    apply_scale,
    get_battery_field_precision,
    get_precision,
    scale_battery_value,
    scale_energy_value,
    scale_runtime_value,
)

# ============================================================================
# __all__ DEFINITION
# ============================================================================
# Explicitly list all exported symbols for better IDE support and documentation

__all__ = [
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
    # Registers
    "FUNC_EN_REGISTER",
    "FUNC_EN_BIT_EPS_EN",
    "FUNC_EN_BIT_AC_CHARGE_EN",
    "FUNC_EN_BIT_SET_TO_STANDBY",
    "FUNC_EN_BIT_FORCED_DISCHG_EN",
    "FUNC_EN_BIT_FORCED_CHG_EN",
    "HOLD_AC_CHARGE_POWER_CMD",
    "HOLD_AC_CHARGE_SOC_LIMIT",
    "HOLD_AC_CHARGE_START_HOUR_1",
    "HOLD_AC_CHARGE_START_MIN_1",
    "HOLD_AC_CHARGE_END_HOUR_1",
    "HOLD_AC_CHARGE_END_MIN_1",
    "HOLD_AC_CHARGE_ENABLE_1",
    "HOLD_AC_CHARGE_ENABLE_2",
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
    "INPUT_SOC",
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
    "INPUT_I_BAT_LIMIT",
    "INPUT_T_INNER",
    "INPUT_T_RADIATOR_1",
    "INPUT_T_RADIATOR_2",
    "INPUT_T_BAT",
    "INPUT_T_BAT_CONTROL",
    "INPUT_I_REC_R",
    "INPUT_I_REC_S",
    "INPUT_I_REC_T",
    "INPUT_I_INV_R",
    "INPUT_I_INV_S",
    "INPUT_I_INV_T",
    "INPUT_I_PV1",
    "INPUT_I_PV2",
    "INPUT_I_PV3",
    "INPUT_I_BAT",
    "INPUT_INTERNAL_FAULT",
    "INPUT_FAULT_HISTORY_1",
    "INPUT_FAULT_HISTORY_2",
    "INPUT_FAULT_HISTORY_3",
    "INPUT_FAULT_HISTORY_4",
    "INPUT_FAULT_HISTORY_5",
    "INPUT_SOH",
    "INPUT_BMS_FAULT",
    "INPUT_BMS_WARNING",
    "INPUT_E_PV1_ALL",
    "INPUT_E_PV2_ALL",
    "INPUT_E_PV3_ALL",
    "INPUT_E_PV1_DAY",
    "INPUT_E_PV2_DAY",
    "INPUT_E_PV3_DAY",
    "INPUT_MAX_CHG_CURR",
    "INPUT_MAX_DISCHG_CURR",
    "INPUT_CHARGE_VOLT_REF",
    "INPUT_DISCHARGE_VOLT_REF",
    "HOLD_REGISTER_GROUPS",
    "INPUT_REGISTER_GROUPS",
    "WEB_PARAM_TO_HOLD_REGISTER",
    "REGISTER_TO_PARAM_KEYS_18KPV",
    "PARAM_KEY_TO_REGISTER_18KPV",
    "REGISTER_STATS_18KPV",
    "GRIDBOSS_PARAMETERS",
    "GRIDBOSS_STATS",
    "get_func_en_bit_mask",
    "set_func_en_bit",
    "get_func_en_bit",
    # Scaling
    "ScaleFactor",
    "INVERTER_RUNTIME_SCALING",
    "ENERGY_INFO_SCALING",
    "BATTERY_BANK_SCALING",
    "BATTERY_MODULE_SCALING",
    "GRIDBOSS_RUNTIME_SCALING",
    "INVERTER_OVERVIEW_SCALING",
    "PARAMETER_SCALING",
    "LIFETIME_ENERGY_SENSORS",
    "DAILY_ENERGY_SENSORS",
    "MONTHLY_ENERGY_SENSORS",
    "BATTERY_LIFETIME_SENSORS",
    "apply_scale",
    "get_precision",
    "get_battery_field_precision",
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
    "MAX_TRANSIENT_ERROR_RETRIES",
    "TRANSIENT_ERROR_MESSAGES",
    # Devices
    "DEVICE_TYPE_INVERTER",
    "DEVICE_TYPE_GRIDBOSS",
    "TIMEZONE_HHMM_HOURS_FACTOR",
    "TIMEZONE_HHMM_MINUTES_FACTOR",
    "parse_hhmm_timezone",
    "SCALE_MID_VOLTAGE",
    "SCALE_MID_FREQUENCY",
    "scale_mid_voltage",
    "scale_mid_frequency",
    "SOC_MIN_PERCENT",
    "SOC_MAX_PERCENT",
    "MAX_REGISTERS_PER_READ",
]
