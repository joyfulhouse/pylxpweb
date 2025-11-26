"""Data scaling constants and functions for API values.

This module contains all scaling factors and helper functions for converting
raw API values to properly scaled units (volts, amps, watts, etc.).

Source: Analysis of EG4 Web Monitor and actual API responses.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

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
# All energy values from API are in 0.1 kWh units, need ÷10 to get kWh directly
# Example: API returns 184 → 184 ÷ 10 = 18.4 kWh

ENERGY_INFO_SCALING: dict[str, ScaleFactor] = {
    # Daily Energy (÷10 to get kWh: 184 → 18.4 kWh)
    "todayYielding": ScaleFactor.SCALE_10,
    "todayCharging": ScaleFactor.SCALE_10,
    "todayDischarging": ScaleFactor.SCALE_10,
    "todayGridImport": ScaleFactor.SCALE_10,
    "todayImport": ScaleFactor.SCALE_10,  # Alternative field name for todayGridImport
    "todayUsage": ScaleFactor.SCALE_10,
    "todayExport": ScaleFactor.SCALE_10,
    # Monthly Energy (÷10 to get kWh)
    "monthYielding": ScaleFactor.SCALE_10,
    "monthCharging": ScaleFactor.SCALE_10,
    "monthDischarging": ScaleFactor.SCALE_10,
    "monthGridImport": ScaleFactor.SCALE_10,
    "monthImport": ScaleFactor.SCALE_10,  # Alternative field name for monthGridImport
    "monthUsage": ScaleFactor.SCALE_10,
    "monthExport": ScaleFactor.SCALE_10,
    # Yearly Energy (÷10 to get kWh)
    "yearYielding": ScaleFactor.SCALE_10,
    "yearCharging": ScaleFactor.SCALE_10,
    "yearDischarging": ScaleFactor.SCALE_10,
    "yearGridImport": ScaleFactor.SCALE_10,
    "yearImport": ScaleFactor.SCALE_10,  # Alternative field name for yearGridImport
    "yearUsage": ScaleFactor.SCALE_10,
    "yearExport": ScaleFactor.SCALE_10,
    # Lifetime Total Energy (÷10 to get kWh)
    "totalYielding": ScaleFactor.SCALE_10,
    "totalCharging": ScaleFactor.SCALE_10,
    "totalDischarging": ScaleFactor.SCALE_10,
    "totalGridImport": ScaleFactor.SCALE_10,
    "totalImport": ScaleFactor.SCALE_10,  # Alternative field name for totalGridImport
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
    # Charge/Discharge Reference Values (÷10, consistent with battery current scaling)
    "batChargeMaxCur": ScaleFactor.SCALE_10,  # 2000 → 200.0A
    "batChargeVoltRef": ScaleFactor.SCALE_10,  # 560 → 56.0V
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


def get_precision(scale_factor: ScaleFactor) -> int:
    """Get decimal precision from a scale factor.

    Args:
        scale_factor: ScaleFactor enum

    Returns:
        Number of decimal places (0 for SCALE_NONE, 1 for SCALE_10, etc.)

    Example:
        >>> get_precision(ScaleFactor.SCALE_10)
        1
        >>> get_precision(ScaleFactor.SCALE_1000)
        3
    """
    if scale_factor == ScaleFactor.SCALE_NONE:
        return 0
    # log10 of scale factor gives decimal places
    import math

    return int(math.log10(scale_factor.value))


def get_battery_field_precision(field_name: str) -> int:
    """Get decimal precision for a battery module field.

    Args:
        field_name: Field name from BatteryModule model

    Returns:
        Number of decimal places for that field

    Example:
        >>> get_battery_field_precision("batMaxCellVoltage")
        3
        >>> get_battery_field_precision("current")
        1
    """
    if field_name not in BATTERY_MODULE_SCALING:
        return 0
    return get_precision(BATTERY_MODULE_SCALING[field_name])


def _get_scaling_for_field(
    field_name: str,
    data_type: Literal[
        "runtime", "energy", "battery_bank", "battery_module", "gridboss", "overview", "parameter"
    ],
) -> ScaleFactor:
    """Get the appropriate scaling factor for a field.

    This is an internal function. External users should use the data type-specific
    convenience functions instead (e.g., scale_runtime_value, scale_battery_value).

    Args:
        field_name: Name of the field (e.g., "vpv1", "totalVoltage")
        data_type: Type of data source

    Returns:
        ScaleFactor enum indicating how to scale the value

    Raises:
        KeyError: If field_name not found in the specified data type

    Example:
        >>> scale = _get_scaling_for_field("vpv1", "runtime")
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
        value: Raw API value (in 0.1 kWh units)
        to_kwh: If True, return kWh; if False, return Wh

    Returns:
        Scaled value in kWh (if to_kwh=True) or Wh

    Example:
        >>> scale_energy_value("todayYielding", 184, to_kwh=True)
        18.4  # kWh
        >>> scale_energy_value("todayYielding", 184, to_kwh=False)
        18400.0  # Wh
    """
    if field_name not in ENERGY_INFO_SCALING:
        return float(value)

    # Apply API scaling (÷10 to get kWh directly - API uses 0.1 kWh units)
    kwh_value = apply_scale(value, ENERGY_INFO_SCALING[field_name])

    # Convert to Wh if requested
    if not to_kwh:
        return kwh_value * 1000.0
    return kwh_value
