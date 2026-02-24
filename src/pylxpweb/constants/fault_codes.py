"""Fault and warning code catalogs for inverters and BMS.

This module provides lookup dictionaries and decoder functions for interpreting
fault and warning codes reported by Luxpower/EG4 inverters and their battery
management systems (BMS).

**Inverter codes** (INVERTER_FAULT_CODES, INVERTER_WARNING_CODES) are BITFIELDS.
Each bit position in the 32-bit register value represents an independent
fault/warning condition, and multiple conditions can be active simultaneously.
Source registers: Input 60-61 (fault, 32-bit) and Input 62-63 (warning, 32-bit).

**BMS codes** (BMS_FAULT_CODES, BMS_WARNING_CODES) are ENUMERATED values.
The register holds a single integer that maps to exactly one condition at a time.
Source registers: Input 99 (fault) and Input 100 (warning).

Note: BMS code descriptions are provisional and pending full hardware
verification across all supported battery models.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Inverter fault codes — bitfield, Input registers 60-61 (32-bit combined)
# ---------------------------------------------------------------------------
INVERTER_FAULT_CODES: dict[int, str] = {
    0: "Internal communication failure 1",
    1: "Model fault",
    8: "Parallel CAN communication failure",
    9: "The host is missing",
    10: "Inconsistent rated power",
    11: "Inconsistent AC or safety settings",
    12: "UPS short circuit",
    13: "UPS reverse current",
    14: "BUS short circuit",
    15: "Abnormal phase in three-phase system",
    16: "Relay failure",
    17: "Internal communication failure 2",
    18: "Internal communication failure 3",
    19: "BUS overvoltage",
    20: "EPS connection fault",
    21: "PV overvoltage",
    22: "Overcurrent protection",
    23: "Neutral fault",
    24: "PV short circuit",
    25: "Heatsink temperature out of range",
    26: "Internal failure",
    27: "Consistency failure",
    28: "Inconsistent generator connection",
    29: "Parallel sync signal loss",
    31: "Internal communication failure 4",
}

# ---------------------------------------------------------------------------
# Inverter warning codes — bitfield, Input registers 62-63 (32-bit combined)
# ---------------------------------------------------------------------------
INVERTER_WARNING_CODES: dict[int, str] = {
    0: "Battery communication failed",
    1: "AFCI communication failure",
    2: "Battery low temperature",
    3: "Meter communication failed",
    4: "Battery cannot be charged/discharged",
    5: "Automated test failed",
    6: "RSD Active",
    7: "LCD communication failure",
    8: "Software version mismatch",
    9: "Fan is stuck",
    10: "Grid overload",
    11: "Number of parallel secondaries exceeds limit",
    12: "Battery reverse MOS abnormal",
    13: "Radiator temperature out of range",
    14: "Multiple primary units set in parallel system",
    15: "Battery reverse",
    16: "No grid connection",
    17: "Grid voltage out of range",
    18: "Grid frequency out of range",
    20: "Insulation resistance low",
    21: "Leakage current too high",
    22: "DCI exceeded standard",
    23: "PV short circuit",
    25: "Battery overvoltage",
    26: "Battery undervoltage",
    27: "Battery open circuit",
    28: "EPS overload",
    29: "EPS voltage high",
    30: "Meter reversed",
    31: "DCV exceeded standard",
}

# ---------------------------------------------------------------------------
# BMS fault codes — enumerated, Input register 99
# ---------------------------------------------------------------------------
BMS_FAULT_CODES: dict[int, str] = {
    0x00: "Normal / No Fault",
    0x01: "Cell Over-Voltage Protection (COVP)",
    0x02: "Cell Under-Voltage Protection (CUVP)",
    0x03: "Pack Overvoltage",
    0x04: "Pack Undervoltage",
    0x05: "Charging Over-Temperature Protection (COTP)",
    0x06: "Charging Under-Temperature Protection (CUTP)",
    0x07: "Discharging Over-Temperature Protection (DOTP)",
    0x08: "Low Temperature Protection",
    0x09: "Charging Overcurrent",
    0x0A: "Discharging Overcurrent",
    0x0B: "Short Circuit",
    0x0C: "MOSFET Over-Temperature",
    0x0D: "Cell Unbalance",
    0x0E: "Over-Capacity",
}

# ---------------------------------------------------------------------------
# BMS warning codes — enumerated, Input register 100
# ---------------------------------------------------------------------------
BMS_WARNING_CODES: dict[int, str] = {
    0x00: "Normal / No Warning",
    0x01: "Cell Over-Voltage Warning",
    0x02: "Cell Under-Voltage Warning",
    0x03: "Pack Overvoltage Warning",
    0x04: "Pack Undervoltage Warning",
    0x05: "Charging Over-Temperature Warning",
    0x06: "Charging Under-Temperature Warning",
    0x07: "Discharging Over-Temperature Warning",
    0x08: "Low Temperature Warning",
    0x09: "Charging Overcurrent Warning",
    0x0A: "Discharging Overcurrent Warning",
    0x0B: "Short Circuit Warning",
    0x0C: "MOSFET Over-Temperature Warning",
    0x0D: "Cell Unbalance Warning",
    0x0E: "Over-Capacity Warning",
}


# ---------------------------------------------------------------------------
# Decoder functions
# ---------------------------------------------------------------------------


def decode_fault_bits(raw_value: int, code_map: dict[int, str]) -> list[str]:
    """Extract active fault/warning descriptions from a bitfield value.

    Iterates over the code_map keys (bit positions) in ascending order and
    returns the descriptions for every bit that is set in *raw_value*.

    Args:
        raw_value: The raw 32-bit register value (e.g. from Input 60-61).
        code_map: A mapping of bit position to description string.

    Returns:
        A list of active fault/warning descriptions sorted by bit position.
    """
    return [desc for bit, desc in sorted(code_map.items()) if raw_value & (1 << bit)]


def decode_bms_code(raw_value: int, code_map: dict[int, str]) -> str:
    """Look up a single BMS fault/warning code by enum value.

    Args:
        raw_value: The raw register value (e.g. from Input 99 or 100).
        code_map: A mapping of enum value to description string.

    Returns:
        The description for the given code, or a formatted "Unknown code: 0xNN"
        string if the value is not in the catalog.
    """
    return code_map.get(raw_value, f"Unknown code: 0x{raw_value:02X}")
