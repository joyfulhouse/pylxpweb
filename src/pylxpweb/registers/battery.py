"""Canonical register map for individual battery modules (5000+ range).

Source: Empirical testing on FlexBOSS21, 18KPV via Modbus TCP.
Cross-validated against Web API getBatteryInfo response.

Individual battery data uses INPUT registers (function code 0x04) in an
extended address range starting at base address 5002. Each battery module
occupies a contiguous block of 30 registers, and up to 4 slots are
supported (addresses 5002–5121).

Absolute address for a field:
    addr = BATTERY_BASE_ADDRESS + (battery_index * BATTERY_REGISTER_COUNT) + offset

The battery count is available from inverter input register 96
(canonical_name="battery_parallel_count" in inverter_input.py).

Battery model string (e.g. "WP-16/280-1AWLL") is NOT available via
Modbus registers. It travels over CAN bus → WiFi dongle → cloud API and
is only available via the HTTP getBatteryInfo endpoint (batBmsModelText
field in BatteryModule).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pylxpweb.registers.inverter_input import ScaleFactor

# =============================================================================
# ADDRESSING CONSTANTS
# =============================================================================

BATTERY_BASE_ADDRESS: int = 5002
"""First register of battery slot 0."""

BATTERY_REGISTER_COUNT: int = 30
"""Number of registers per battery module."""

BATTERY_MAX_COUNT: int = 4
"""Maximum number of battery register slots (addresses 5002–5121).

The 18kPV firmware implements exactly 4 CAN-mapped battery register slots.
Slot 4 (address 5122+) returns ExceptionResponse code 3 (Illegal Data
Address).  Batteries rotate through these 4 slots via round-robin when
more than 4 physical modules are connected.
"""


# =============================================================================
# CATEGORY ENUM
# =============================================================================


class BatteryCategory(StrEnum):
    """Category for individual battery registers."""

    STATE = "state"
    """Core state: voltage, current, SOC, SOH, cycle count."""

    CELL = "cell"
    """Per-cell data: min/max voltage, min/max temperature, cell numbers."""

    LIMITS = "limits"
    """BMS charge/discharge limits and cutoff values."""

    CAPACITY = "capacity"
    """Capacity-related: full capacity (Ah)."""

    IDENTITY = "identity"
    """Non-sensor metadata: serial number, firmware, status header."""


# =============================================================================
# REGISTER DEFINITION
# =============================================================================


@dataclass(frozen=True)
class BatteryRegisterDefinition:
    """Single register (or packed byte) within a battery module's 30-register block.

    The ``offset`` field is a 0-based index into the 30-register block.
    Compute the absolute Modbus address as:
        BATTERY_BASE_ADDRESS + (battery_index * BATTERY_REGISTER_COUNT) + offset

    For packed registers (SOC/SOH, cell numbers, firmware version) multiple
    definitions share the same offset but have different ``packed`` annotations.
    """

    offset: int
    """Offset within the 30-register block (0–29)."""

    canonical_name: str
    """Unique, stable identifier used across all layers."""

    cloud_api_field: str | None = None
    """Matching field name in the cloud BatteryModule model, or None."""

    ha_sensor_key: str | None = None
    """HA sensor key suffix used in coordinator_mappings.py, or None."""

    scale: ScaleFactor = ScaleFactor.NONE
    """Divisor applied to the raw 16-bit register value."""

    signed: bool = False
    """Whether the raw value uses two's-complement signed representation."""

    unit: str | None = None
    """Engineering unit after scaling (V, A, °C, Ah, etc.)."""

    category: BatteryCategory = BatteryCategory.STATE
    """Logical grouping for documentation and filtering."""

    description: str = ""
    """Human-readable explanation of the register."""

    packed: str | None = None
    """Byte-packing annotation for shared registers (e.g. 'low_byte', 'high_byte')."""


# =============================================================================
# REGISTER DEFINITIONS — 30-register block per battery module
# =============================================================================
#
# Offset │ Name                       │ Scale  │ Signed │ Unit │ Cloud API Field
# ───────┼────────────────────────────┼────────┼────────┼──────┼────────────────
#   0    │ status_header              │ —      │ no     │ —    │ —
#   1    │ full_capacity_ah           │ —      │ no     │ Ah   │ currentFullCapacity
#   2    │ charge_voltage_ref         │ ÷10    │ no     │ V    │ batChargeVoltRef
#   3    │ charge_current_limit       │ ÷100   │ no     │ A    │ batChargeMaxCur
#   4    │ discharge_current_limit    │ ÷100   │ no     │ A    │ —
#   5    │ discharge_voltage_cutoff   │ ÷10    │ no     │ V    │ —
#   6    │ voltage                    │ ÷100   │ no     │ V    │ totalVoltage
#   7    │ current                    │ ÷10    │ yes    │ A    │ current
#   8    │ soc (low) / soh (high)     │ —      │ no     │ %    │ soc / soh
#   9    │ cycle_count                │ —      │ no     │ —    │ cycleCnt
#  10    │ max_cell_temp              │ ÷10    │ yes    │ °C   │ batMaxCellTemp
#  11    │ min_cell_temp              │ ÷10    │ yes    │ °C   │ batMinCellTemp
#  12    │ max_cell_voltage           │ ÷1000  │ no     │ V    │ batMaxCellVoltage
#  13    │ min_cell_voltage           │ ÷1000  │ no     │ V    │ batMinCellVoltage
#  14    │ max_cell_num_v (lo) / min_cell_num_v (hi) │ — │ — │ — │ packed
#  15    │ max_cell_num_t (lo) / min_cell_num_t (hi) │ — │ — │ — │ packed
#  16    │ firmware_version           │ —      │ no     │ —    │ fwVersionText
# 17-23  │ serial_number (ASCII)      │ —      │ no     │ —    │ batterySn
# 24-29  │ reserved                   │ —      │ —      │ —    │ —

BATTERY_REGISTERS: tuple[BatteryRegisterDefinition, ...] = (
    # =========================================================================
    # STATUS (offset 0) — 0xC003 = connected
    # =========================================================================
    BatteryRegisterDefinition(
        offset=0,
        canonical_name="battery_status_header",
        category=BatteryCategory.IDENTITY,
        description="Status header. 0xC003 = connected, 0 = slot empty.",
    ),
    # =========================================================================
    # CAPACITY (offset 1)
    # =========================================================================
    BatteryRegisterDefinition(
        offset=1,
        canonical_name="battery_full_capacity",
        cloud_api_field="currentFullCapacity",
        ha_sensor_key="battery_full_capacity",
        unit="Ah",
        category=BatteryCategory.CAPACITY,
        description="Full (rated) capacity in amp-hours.",
    ),
    # =========================================================================
    # BMS LIMITS (offsets 2-5)
    # =========================================================================
    BatteryRegisterDefinition(
        offset=2,
        canonical_name="battery_charge_voltage_ref",
        cloud_api_field="batChargeVoltRef",
        ha_sensor_key="battery_charge_voltage_ref",
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=BatteryCategory.LIMITS,
        description="BMS recommended charge voltage reference.",
    ),
    BatteryRegisterDefinition(
        offset=3,
        canonical_name="battery_charge_current_limit",
        cloud_api_field="batChargeMaxCur",
        ha_sensor_key="battery_max_charge_current",
        scale=ScaleFactor.DIV_100,
        unit="A",
        category=BatteryCategory.LIMITS,
        description="BMS maximum charge current limit.",
    ),
    BatteryRegisterDefinition(
        offset=4,
        canonical_name="battery_discharge_current_limit",
        scale=ScaleFactor.DIV_100,
        unit="A",
        category=BatteryCategory.LIMITS,
        description="BMS maximum discharge current limit.",
    ),
    BatteryRegisterDefinition(
        offset=5,
        canonical_name="battery_discharge_voltage_cutoff",
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=BatteryCategory.LIMITS,
        description="BMS discharge cutoff voltage.",
    ),
    # =========================================================================
    # CORE STATE (offsets 6-9)
    # =========================================================================
    BatteryRegisterDefinition(
        offset=6,
        canonical_name="battery_voltage",
        cloud_api_field="totalVoltage",
        ha_sensor_key="battery_real_voltage",
        scale=ScaleFactor.DIV_100,
        unit="V",
        category=BatteryCategory.STATE,
        description="Battery module total voltage.",
    ),
    BatteryRegisterDefinition(
        offset=7,
        canonical_name="battery_current",
        cloud_api_field="current",
        ha_sensor_key="battery_real_current",
        scale=ScaleFactor.DIV_10,
        signed=True,
        unit="A",
        category=BatteryCategory.STATE,
        description="Battery module current. Positive = charging, negative = discharging.",
    ),
    # Offset 8: SOC/SOH packed — low byte = SOC%, high byte = SOH%
    BatteryRegisterDefinition(
        offset=8,
        canonical_name="battery_soc",
        cloud_api_field="soc",
        ha_sensor_key="battery_rsoc",
        unit="%",
        category=BatteryCategory.STATE,
        description="State of charge (low byte of packed SOC/SOH register).",
        packed="low_byte",
    ),
    BatteryRegisterDefinition(
        offset=8,
        canonical_name="battery_soh",
        cloud_api_field="soh",
        ha_sensor_key="state_of_health",
        unit="%",
        category=BatteryCategory.STATE,
        description="State of health (high byte of packed SOC/SOH register).",
        packed="high_byte",
    ),
    BatteryRegisterDefinition(
        offset=9,
        canonical_name="battery_cycle_count",
        cloud_api_field="cycleCnt",
        ha_sensor_key="cycle_count",
        category=BatteryCategory.STATE,
        description="Charge/discharge cycle count.",
    ),
    # =========================================================================
    # CELL TEMPERATURE (offsets 10-11)
    # =========================================================================
    BatteryRegisterDefinition(
        offset=10,
        canonical_name="battery_max_cell_temp",
        cloud_api_field="batMaxCellTemp",
        ha_sensor_key="battery_max_cell_temp",
        scale=ScaleFactor.DIV_10,
        signed=True,
        unit="°C",
        category=BatteryCategory.CELL,
        description="Maximum cell temperature across all cells in this module.",
    ),
    BatteryRegisterDefinition(
        offset=11,
        canonical_name="battery_min_cell_temp",
        cloud_api_field="batMinCellTemp",
        ha_sensor_key="battery_min_cell_temp",
        scale=ScaleFactor.DIV_10,
        signed=True,
        unit="°C",
        category=BatteryCategory.CELL,
        description="Minimum cell temperature across all cells in this module.",
    ),
    # =========================================================================
    # CELL VOLTAGE (offsets 12-13)
    # =========================================================================
    BatteryRegisterDefinition(
        offset=12,
        canonical_name="battery_max_cell_voltage",
        cloud_api_field="batMaxCellVoltage",
        ha_sensor_key="battery_max_cell_voltage",
        scale=ScaleFactor.DIV_1000,
        unit="V",
        category=BatteryCategory.CELL,
        description="Maximum individual cell voltage (raw value in millivolts).",
    ),
    BatteryRegisterDefinition(
        offset=13,
        canonical_name="battery_min_cell_voltage",
        cloud_api_field="batMinCellVoltage",
        ha_sensor_key="battery_min_cell_voltage",
        scale=ScaleFactor.DIV_1000,
        unit="V",
        category=BatteryCategory.CELL,
        description="Minimum individual cell voltage (raw value in millivolts).",
    ),
    # =========================================================================
    # CELL NUMBER (offsets 14-15) — packed: low byte = max, high byte = min
    # =========================================================================
    BatteryRegisterDefinition(
        offset=14,
        canonical_name="battery_max_cell_num_voltage",
        cloud_api_field="batMaxCellNumVolt",
        ha_sensor_key="battery_max_cell_voltage_num",
        category=BatteryCategory.CELL,
        description="Cell number with highest voltage (low byte).",
        packed="low_byte",
    ),
    BatteryRegisterDefinition(
        offset=14,
        canonical_name="battery_min_cell_num_voltage",
        cloud_api_field="batMinCellNumVolt",
        ha_sensor_key="battery_min_cell_voltage_num",
        category=BatteryCategory.CELL,
        description="Cell number with lowest voltage (high byte).",
        packed="high_byte",
    ),
    BatteryRegisterDefinition(
        offset=15,
        canonical_name="battery_max_cell_num_temp",
        cloud_api_field="batMaxCellNumTemp",
        ha_sensor_key="battery_max_cell_temp_num",
        category=BatteryCategory.CELL,
        description="Cell number with highest temperature (low byte).",
        packed="low_byte",
    ),
    BatteryRegisterDefinition(
        offset=15,
        canonical_name="battery_min_cell_num_temp",
        cloud_api_field="batMinCellNumTemp",
        ha_sensor_key="battery_min_cell_temp_num",
        category=BatteryCategory.CELL,
        description="Cell number with lowest temperature (high byte).",
        packed="high_byte",
    ),
    # =========================================================================
    # IDENTITY (offsets 16, 17-23)
    # =========================================================================
    BatteryRegisterDefinition(
        offset=16,
        canonical_name="battery_firmware_version",
        cloud_api_field="fwVersionText",
        ha_sensor_key="battery_firmware_version",
        category=BatteryCategory.IDENTITY,
        description="Firmware version. Packed: high byte = major, low byte = minor.",
        packed="high_byte=major,low_byte=minor",
    ),
    # Serial number spans 7 registers (offsets 17-23), each holding 2 ASCII chars.
    # Low byte first, high byte second. Up to 14 characters total.
    # This is represented as a single definition with a special packed annotation.
    BatteryRegisterDefinition(
        offset=17,
        canonical_name="battery_serial_number",
        cloud_api_field="batterySn",
        ha_sensor_key="battery_serial_number",
        category=BatteryCategory.IDENTITY,
        description="Serial number. 7 registers (offsets 17-23), 2 ASCII chars each.",
        packed="ascii_7reg",
    ),
)

# Number of defined register entries (including packed duplicates)
BATTERY_REGISTER_COUNT_DEFINED: int = len(BATTERY_REGISTERS)


# =============================================================================
# COMPUTED SENSOR KEYS (not backed by a single register)
# =============================================================================
# These HA sensor keys are derived from register values but do not correspond
# to a single Modbus register read. They are computed in the Battery class or
# coordinator_mappings.py.

COMPUTED_SENSOR_KEYS: frozenset[str] = frozenset(
    {
        "battery_real_power",  # voltage * current
        "battery_cell_voltage_delta",  # max_cell_voltage - min_cell_voltage
        "battery_cell_temp_delta",  # max_cell_temp - min_cell_temp
        "battery_remaining_capacity",  # full_capacity * soc / 100
        "battery_capacity_percentage",  # remaining / full * 100
    }
)


# =============================================================================
# METADATA SENSOR KEYS (cloud-only, not available via Modbus)
# =============================================================================
# These sensor keys require HTTP API data and cannot be read from registers.

CLOUD_ONLY_SENSOR_KEYS: frozenset[str] = frozenset(
    {
        "battery_type",  # batteryType from BatteryModule
        "battery_type_text",  # batteryTypeText from BatteryModule
        "battery_model",  # batBmsModelText from BatteryModule
    }
)


# =============================================================================
# LOOKUP INDEXES
# =============================================================================

BY_NAME: dict[str, BatteryRegisterDefinition] = {r.canonical_name: r for r in BATTERY_REGISTERS}
"""Lookup by canonical_name → definition."""

# BY_OFFSET maps offset → single definition OR tuple of definitions (for packed)
_offset_groups: dict[int, list[BatteryRegisterDefinition]] = {}
for _r in BATTERY_REGISTERS:
    _offset_groups.setdefault(_r.offset, []).append(_r)

BY_OFFSET: dict[int, BatteryRegisterDefinition | tuple[BatteryRegisterDefinition, ...]] = {
    offset: defs[0] if len(defs) == 1 else tuple(defs) for offset, defs in _offset_groups.items()
}
"""Lookup by offset → definition (single) or tuple (packed registers)."""

BY_CLOUD_FIELD: dict[str, BatteryRegisterDefinition] = {
    r.cloud_api_field: r for r in BATTERY_REGISTERS if r.cloud_api_field is not None
}
"""Lookup by cloud API field name → definition."""

BY_SENSOR_KEY: dict[str, BatteryRegisterDefinition] = {
    r.ha_sensor_key: r for r in BATTERY_REGISTERS if r.ha_sensor_key is not None
}
"""Lookup by HA sensor key → definition."""

_cat_groups: dict[BatteryCategory, list[BatteryRegisterDefinition]] = {}
for _r in BATTERY_REGISTERS:
    _cat_groups.setdefault(_r.category, []).append(_r)

BY_CATEGORY: dict[BatteryCategory, tuple[BatteryRegisterDefinition, ...]] = {
    cat: tuple(defs) for cat, defs in _cat_groups.items()
}
"""Lookup by category → tuple of definitions in that category."""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def absolute_address(battery_index: int, offset: int) -> int:
    """Compute the absolute Modbus register address for a battery field.

    Args:
        battery_index: 0-based battery index (0 to BATTERY_MAX_COUNT-1).
        offset: Register offset within the 30-register block (0-29).

    Returns:
        Absolute Modbus register address.

    Raises:
        ValueError: If battery_index or offset is out of range.
    """
    if not 0 <= battery_index < BATTERY_MAX_COUNT:
        msg = f"battery_index must be 0-{BATTERY_MAX_COUNT - 1}, got {battery_index}"
        raise ValueError(msg)
    if not 0 <= offset < BATTERY_REGISTER_COUNT:
        msg = f"offset must be 0-{BATTERY_REGISTER_COUNT - 1}, got {offset}"
        raise ValueError(msg)
    return BATTERY_BASE_ADDRESS + (battery_index * BATTERY_REGISTER_COUNT) + offset


def sensor_key_registers() -> tuple[BatteryRegisterDefinition, ...]:
    """Return only definitions that map to HA sensor keys.

    Returns:
        Tuple of BatteryRegisterDefinition with non-None ha_sensor_key.
    """
    return tuple(r for r in BATTERY_REGISTERS if r.ha_sensor_key is not None)


def all_ha_sensor_keys() -> frozenset[str]:
    """Return all HA sensor keys (register-backed + computed + cloud-only).

    Returns:
        Frozenset of all battery sensor keys used in the HA integration.
    """
    register_keys = frozenset(r.ha_sensor_key for r in BATTERY_REGISTERS if r.ha_sensor_key)
    return register_keys | COMPUTED_SENSOR_KEYS | CLOUD_ONLY_SENSOR_KEYS


__all__ = [
    # Constants
    "BATTERY_BASE_ADDRESS",
    "BATTERY_MAX_COUNT",
    "BATTERY_REGISTER_COUNT",
    "BATTERY_REGISTER_COUNT_DEFINED",
    # Types
    "BatteryCategory",
    "BatteryRegisterDefinition",
    # Data
    "BATTERY_REGISTERS",
    "COMPUTED_SENSOR_KEYS",
    "CLOUD_ONLY_SENSOR_KEYS",
    # Indexes
    "BY_CATEGORY",
    "BY_CLOUD_FIELD",
    "BY_NAME",
    "BY_OFFSET",
    "BY_SENSOR_KEY",
    # Helpers
    "ScaleFactor",
    "absolute_address",
    "all_ha_sensor_keys",
    "sensor_key_registers",
]
