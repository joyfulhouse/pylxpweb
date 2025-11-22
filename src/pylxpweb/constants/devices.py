"""Device-related constants and helper functions.

This module contains device type identifiers, limits, timezone parsing,
and other device-specific utility functions.
"""

from __future__ import annotations

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
