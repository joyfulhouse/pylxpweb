# Register Parity & Fault Code Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close all register coverage gaps between pylxpweb and lxp_modbus, add fault/warning code interpretation, and implement 7-day scheduling register definitions.

**Architecture:** Five independent work items (fault codes, PV4-6 input regs, reg 179 bitfield, reg 233 bitfield, scheduling registers), each following the existing `RegisterDefinition`/`HoldingRegisterDefinition` dataclass patterns with module-level lookup indexes. Two new files, three modified files.

**Tech Stack:** Python 3.13, pytest, mypy strict, ruff, dataclasses, uv

---

### Task 1: Fault & Warning Code Catalogs

**Files:**
- Create: `src/pylxpweb/constants/fault_codes.py`
- Test: `tests/unit/test_fault_codes.py`

**Step 1: Write the failing tests**

Create `tests/unit/test_fault_codes.py`:

```python
"""Unit tests for fault and warning code catalogs."""

from __future__ import annotations

import pytest

from pylxpweb.constants.fault_codes import (
    BMS_FAULT_CODES,
    BMS_WARNING_CODES,
    INVERTER_FAULT_CODES,
    INVERTER_WARNING_CODES,
    decode_bms_code,
    decode_fault_bits,
)


class TestInverterFaultCodes:
    """Test inverter fault code bitfield catalog."""

    def test_catalog_exists_and_nonempty(self) -> None:
        assert isinstance(INVERTER_FAULT_CODES, dict)
        assert len(INVERTER_FAULT_CODES) >= 21

    def test_all_keys_are_bit_positions(self) -> None:
        for bit in INVERTER_FAULT_CODES:
            assert isinstance(bit, int)
            assert 0 <= bit <= 31

    def test_all_values_are_descriptions(self) -> None:
        for desc in INVERTER_FAULT_CODES.values():
            assert isinstance(desc, str)
            assert len(desc) > 0

    def test_known_entries(self) -> None:
        assert INVERTER_FAULT_CODES[0] == "Internal communication failure 1"
        assert INVERTER_FAULT_CODES[21] == "PV overvoltage"
        assert INVERTER_FAULT_CODES[22] == "Overcurrent protection"


class TestInverterWarningCodes:
    """Test inverter warning code bitfield catalog."""

    def test_catalog_exists_and_nonempty(self) -> None:
        assert isinstance(INVERTER_WARNING_CODES, dict)
        assert len(INVERTER_WARNING_CODES) >= 30

    def test_all_keys_are_bit_positions(self) -> None:
        for bit in INVERTER_WARNING_CODES:
            assert isinstance(bit, int)
            assert 0 <= bit <= 31

    def test_known_entries(self) -> None:
        assert INVERTER_WARNING_CODES[0] == "Battery communication failed"
        assert INVERTER_WARNING_CODES[30] == "Meter reversed"


class TestBmsFaultCodes:
    """Test BMS fault code enum catalog."""

    def test_catalog_exists_and_nonempty(self) -> None:
        assert isinstance(BMS_FAULT_CODES, dict)
        assert len(BMS_FAULT_CODES) >= 15

    def test_keys_are_enum_values(self) -> None:
        for code in BMS_FAULT_CODES:
            assert isinstance(code, int)
            assert 0x00 <= code <= 0x0E

    def test_normal_is_zero(self) -> None:
        assert 0x00 in BMS_FAULT_CODES
        assert "Normal" in BMS_FAULT_CODES[0x00]


class TestBmsWarningCodes:
    """Test BMS warning code enum catalog."""

    def test_catalog_exists_and_nonempty(self) -> None:
        assert isinstance(BMS_WARNING_CODES, dict)
        assert len(BMS_WARNING_CODES) >= 15


class TestDecodeFaultBits:
    """Test bitfield decoder function."""

    def test_no_faults(self) -> None:
        assert decode_fault_bits(0, INVERTER_FAULT_CODES) == []

    def test_single_fault(self) -> None:
        result = decode_fault_bits(1 << 21, INVERTER_FAULT_CODES)
        assert result == ["PV overvoltage"]

    def test_multiple_faults(self) -> None:
        raw = (1 << 0) | (1 << 1)
        result = decode_fault_bits(raw, INVERTER_FAULT_CODES)
        assert len(result) == 2
        assert result[0] == "Internal communication failure 1"
        assert result[1] == "Model fault"

    def test_unknown_bit_ignored(self) -> None:
        # Bit 2 is not in INVERTER_FAULT_CODES
        result = decode_fault_bits(1 << 2, INVERTER_FAULT_CODES)
        assert result == []

    def test_all_bits_set(self) -> None:
        result = decode_fault_bits(0xFFFFFFFF, INVERTER_FAULT_CODES)
        assert len(result) == len(INVERTER_FAULT_CODES)


class TestDecodeBmsCode:
    """Test BMS enum decoder function."""

    def test_normal(self) -> None:
        result = decode_bms_code(0x00, BMS_FAULT_CODES)
        assert "Normal" in result

    def test_known_code(self) -> None:
        result = decode_bms_code(0x01, BMS_FAULT_CODES)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_unknown_code(self) -> None:
        result = decode_bms_code(0xFF, BMS_FAULT_CODES)
        assert "Unknown" in result
        assert "0xFF" in result
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/unit/test_fault_codes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pylxpweb.constants.fault_codes'`

**Step 3: Write the implementation**

Create `src/pylxpweb/constants/fault_codes.py`:

```python
"""Fault and warning code catalogs for inverter and BMS diagnostics.

Inverter codes are BITFIELDS — multiple faults/warnings active simultaneously.
Source registers: Input 60-61 (fault, 32-bit), Input 62-63 (warning, 32-bit).
Sourced from lxp_modbus fault_codes.py / warning_codes.py (Luxpower protocol PDF).

BMS codes are ENUMERATED values (0x00-0x0E) — one active code at a time.
Source registers: Input 99 (fault), Input 100 (warning).
Sourced from EG4 LL battery manual. Marked provisional pending hardware verification.
"""

from __future__ import annotations

# =============================================================================
# INVERTER FAULT CODES (Input regs 60-61, 32-bit bitfield)
# =============================================================================
# Each key is a bit position (0-31). Multiple bits can be set simultaneously.

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

# =============================================================================
# INVERTER WARNING CODES (Input regs 62-63, 32-bit bitfield)
# =============================================================================

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

# =============================================================================
# BMS FAULT CODES (Input reg 99, enumerated 0x00-0x0E)
# =============================================================================
# Provisional — sourced from EG4 LL battery manual + community forums.
# Pending hardware verification.

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

# =============================================================================
# BMS WARNING CODES (Input reg 100, enumerated 0x00-0x0E)
# =============================================================================
# Uses same code space as fault codes but for warning-level severity.
# Provisional — pending hardware verification.

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


# =============================================================================
# DECODER FUNCTIONS
# =============================================================================


def decode_fault_bits(raw_value: int, code_map: dict[int, str]) -> list[str]:
    """Extract active fault/warning descriptions from a bitfield value.

    Args:
        raw_value: Raw 32-bit register value (from input regs 60-63).
        code_map: Bit-position-to-description mapping
            (INVERTER_FAULT_CODES or INVERTER_WARNING_CODES).

    Returns:
        List of active fault/warning descriptions, sorted by bit position.
        Empty list if no faults/warnings active (raw_value == 0).
    """
    return [desc for bit, desc in sorted(code_map.items()) if raw_value & (1 << bit)]


def decode_bms_code(raw_value: int, code_map: dict[int, str]) -> str:
    """Look up a single BMS fault/warning code by enum value.

    Args:
        raw_value: Raw register value (from input reg 99 or 100).
        code_map: Enum-value-to-description mapping
            (BMS_FAULT_CODES or BMS_WARNING_CODES).

    Returns:
        Description string. If code is unknown, returns "Unknown code: 0xNN".
    """
    return code_map.get(raw_value, f"Unknown code: 0x{raw_value:02X}")
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/unit/test_fault_codes.py -v`
Expected: All PASS

**Step 5: Run lint + type check**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run ruff check src/pylxpweb/constants/fault_codes.py tests/unit/test_fault_codes.py --fix && uv run ruff format src/pylxpweb/constants/fault_codes.py tests/unit/test_fault_codes.py`
Expected: Clean

**Step 6: Commit**

```bash
cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb
git add src/pylxpweb/constants/fault_codes.py tests/unit/test_fault_codes.py
git commit -m "feat: add fault/warning code catalogs with bitfield and enum decoders

Four code-to-description dictionaries:
- INVERTER_FAULT_CODES (21 entries, 32-bit bitfield, input regs 60-61)
- INVERTER_WARNING_CODES (30 entries, 32-bit bitfield, input regs 62-63)
- BMS_FAULT_CODES (15 entries, enum 0x00-0x0E, input reg 99)
- BMS_WARNING_CODES (15 entries, enum 0x00-0x0E, input reg 100)

Two decoder functions:
- decode_fault_bits(): bitfield → list of active descriptions
- decode_bms_code(): enum value → single description

Inverter codes sourced from lxp_modbus (Luxpower protocol PDF).
BMS codes provisional, pending hardware verification."
```

---

### Task 2: Set ha_sensor_key on Fault/Warning Registers

**Files:**
- Modify: `src/pylxpweb/registers/inverter_input.py` (lines 589-605 — regs 60-63, 99-100)

**Step 1: Write the failing test**

Add to `tests/unit/test_fault_codes.py`:

```python
class TestFaultRegisterSensorKeys:
    """Verify fault/warning registers have ha_sensor_key for HA diagnostics."""

    def test_fault_code_has_sensor_key(self) -> None:
        from pylxpweb.registers.inverter_input import BY_NAME
        reg = BY_NAME["fault_code"]
        assert reg.ha_sensor_key == "fault_code"

    def test_warning_code_has_sensor_key(self) -> None:
        from pylxpweb.registers.inverter_input import BY_NAME
        reg = BY_NAME["warning_code"]
        assert reg.ha_sensor_key == "warning_code"

    def test_bms_fault_code_has_sensor_key(self) -> None:
        from pylxpweb.registers.inverter_input import BY_NAME
        reg = BY_NAME["bms_fault_code"]
        assert reg.ha_sensor_key == "bms_fault_code"

    def test_bms_warning_code_has_sensor_key(self) -> None:
        from pylxpweb.registers.inverter_input import BY_NAME
        reg = BY_NAME["bms_warning_code"]
        assert reg.ha_sensor_key == "bms_warning_code"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/unit/test_fault_codes.py::TestFaultRegisterSensorKeys -v`
Expected: FAIL — `assert None == "fault_code"`

**Step 3: Modify inverter_input.py**

In `src/pylxpweb/registers/inverter_input.py`, update the four fault/warning register definitions:

- Line ~591: `ha_sensor_key=None` → `ha_sensor_key="fault_code"` (address=60)
- Line ~600: `ha_sensor_key=None` → `ha_sensor_key="warning_code"` (address=62)
- Line ~870: `ha_sensor_key=None` → `ha_sensor_key="bms_fault_code"` (address=99)
- Line ~878: `ha_sensor_key=None` → `ha_sensor_key="bms_warning_code"` (address=100)

**Step 4: Run tests to verify they pass**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/unit/test_fault_codes.py -v`
Expected: All PASS

**Step 5: Run full test suite to check for regressions**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/ -x --tb=short`
Expected: All PASS (no existing tests depend on these keys being None)

**Step 6: Commit**

```bash
cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb
git add src/pylxpweb/registers/inverter_input.py tests/unit/test_fault_codes.py
git commit -m "feat: set ha_sensor_key on fault/warning registers (60-63, 99-100)

Enables HA integration to surface fault/warning codes as diagnostic sensors.
Previously ha_sensor_key was None on these four register definitions."
```

---

### Task 3: Data Model — Fault Message Properties

**Files:**
- Modify: `src/pylxpweb/transports/data.py`
- Test: `tests/unit/test_fault_codes.py` (append)

**Step 1: Write the failing tests**

Append to `tests/unit/test_fault_codes.py`:

```python
class TestInverterRuntimeDataFaultProperties:
    """Test fault/warning message properties on InverterRuntimeData."""

    def test_fault_messages_no_fault(self) -> None:
        from pylxpweb.transports.data import InverterRuntimeData
        data = InverterRuntimeData(fault_code=0)
        assert data.fault_messages == []

    def test_fault_messages_single(self) -> None:
        from pylxpweb.transports.data import InverterRuntimeData
        data = InverterRuntimeData(fault_code=(1 << 21))
        assert data.fault_messages == ["PV overvoltage"]

    def test_fault_messages_none_value(self) -> None:
        from pylxpweb.transports.data import InverterRuntimeData
        data = InverterRuntimeData(fault_code=None)
        assert data.fault_messages == []

    def test_warning_messages_multiple(self) -> None:
        from pylxpweb.transports.data import InverterRuntimeData
        data = InverterRuntimeData(warning_code=(1 << 0) | (1 << 9))
        assert len(data.warning_messages) == 2

    def test_warning_messages_none_value(self) -> None:
        from pylxpweb.transports.data import InverterRuntimeData
        data = InverterRuntimeData(warning_code=None)
        assert data.warning_messages == []
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/unit/test_fault_codes.py::TestInverterRuntimeDataFaultProperties -v`
Expected: FAIL — `AttributeError: 'InverterRuntimeData' object has no attribute 'fault_messages'`

**Step 3: Add properties to InverterRuntimeData**

In `src/pylxpweb/transports/data.py`, add after the `is_corrupt()` method (before `from_http_response`):

```python
    @property
    def fault_messages(self) -> list[str]:
        """Active inverter fault descriptions decoded from bitfield."""
        from pylxpweb.constants.fault_codes import INVERTER_FAULT_CODES, decode_fault_bits

        if self.fault_code is None or self.fault_code == 0:
            return []
        return decode_fault_bits(self.fault_code, INVERTER_FAULT_CODES)

    @property
    def warning_messages(self) -> list[str]:
        """Active inverter warning descriptions decoded from bitfield."""
        from pylxpweb.constants.fault_codes import INVERTER_WARNING_CODES, decode_fault_bits

        if self.warning_code is None or self.warning_code == 0:
            return []
        return decode_fault_bits(self.warning_code, INVERTER_WARNING_CODES)
```

Note: Uses lazy imports to avoid circular dependency issues.

**Step 4: Run tests to verify they pass**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/unit/test_fault_codes.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb
git add src/pylxpweb/transports/data.py tests/unit/test_fault_codes.py
git commit -m "feat: add fault_messages/warning_messages properties to InverterRuntimeData

Decodes raw fault_code/warning_code bitfield values into human-readable
description lists using the new fault code catalogs."
```

---

### Task 4: V23 PV4-6 Input Registers (217-231)

**Files:**
- Modify: `src/pylxpweb/registers/inverter_input.py`
- Modify: `src/pylxpweb/transports/data.py`
- Test: `tests/unit/test_pv456_registers.py` (new)

**Step 1: Write the failing tests**

Create `tests/unit/test_pv456_registers.py`:

```python
"""Unit tests for PV4-6 input register definitions (V23, regs 217-231)."""

from __future__ import annotations

from pylxpweb.registers.inverter_input import (
    BY_ADDRESS,
    BY_CLOUD_FIELD,
    BY_NAME,
    BY_SENSOR_KEY,
    RegisterCategory,
    ScaleFactor,
)


class TestPV456Registers:
    """Test PV4-6 voltage, power, and energy register definitions."""

    def test_pv4_voltage_exists(self) -> None:
        reg = BY_NAME["pv4_voltage"]
        assert reg.address == 217
        assert reg.cloud_api_field == "vpv4"
        assert reg.ha_sensor_key == "pv4_voltage"
        assert reg.scale == ScaleFactor.DIV_10
        assert reg.unit == "V"
        assert reg.category == RegisterCategory.RUNTIME

    def test_pv5_voltage_exists(self) -> None:
        reg = BY_NAME["pv5_voltage"]
        assert reg.address == 218
        assert reg.cloud_api_field == "vpv5"
        assert reg.scale == ScaleFactor.DIV_10

    def test_pv6_voltage_exists(self) -> None:
        reg = BY_NAME["pv6_voltage"]
        assert reg.address == 219
        assert reg.cloud_api_field == "vpv6"
        assert reg.scale == ScaleFactor.DIV_10

    def test_pv4_power_exists(self) -> None:
        reg = BY_NAME["pv4_power"]
        assert reg.address == 220
        assert reg.cloud_api_field == "ppv4"
        assert reg.ha_sensor_key == "pv4_power"
        assert reg.unit == "W"

    def test_pv5_power_exists(self) -> None:
        reg = BY_NAME["pv5_power"]
        assert reg.address == 221
        assert reg.cloud_api_field == "ppv5"

    def test_pv6_power_exists(self) -> None:
        reg = BY_NAME["pv6_power"]
        assert reg.address == 222
        assert reg.cloud_api_field == "ppv6"

    def test_epv4_day_exists(self) -> None:
        reg = BY_NAME["epv4_day"]
        assert reg.address == 223
        assert reg.scale == ScaleFactor.DIV_10
        assert reg.unit == "kWh"
        assert reg.category == RegisterCategory.ENERGY_DAILY

    def test_epv4_all_is_32bit(self) -> None:
        reg = BY_NAME["epv4_all"]
        assert reg.address == 224
        assert reg.bit_width == 32
        assert reg.category == RegisterCategory.ENERGY_LIFETIME

    def test_epv5_day_exists(self) -> None:
        reg = BY_NAME["epv5_day"]
        assert reg.address == 226

    def test_epv5_all_is_32bit(self) -> None:
        reg = BY_NAME["epv5_all"]
        assert reg.address == 227
        assert reg.bit_width == 32

    def test_epv6_day_exists(self) -> None:
        reg = BY_NAME["epv6_day"]
        assert reg.address == 229

    def test_epv6_all_is_32bit(self) -> None:
        reg = BY_NAME["epv6_all"]
        assert reg.address == 230
        assert reg.bit_width == 32

    def test_all_15_registers_addressable(self) -> None:
        """All 15 PV4-6 registers (217-231) should be in BY_ADDRESS."""
        for addr in range(217, 232):
            assert addr in BY_ADDRESS, f"Address {addr} missing from BY_ADDRESS"

    def test_cloud_field_lookups(self) -> None:
        assert "vpv4" in BY_CLOUD_FIELD
        assert "vpv5" in BY_CLOUD_FIELD
        assert "vpv6" in BY_CLOUD_FIELD
        assert "ppv4" in BY_CLOUD_FIELD
        assert "ppv5" in BY_CLOUD_FIELD
        assert "ppv6" in BY_CLOUD_FIELD


class TestPV456DataModelFields:
    """Test that InverterRuntimeData has PV5/6 fields."""

    def test_pv5_voltage_field(self) -> None:
        from pylxpweb.transports.data import InverterRuntimeData
        data = InverterRuntimeData(pv5_voltage=300.0)
        assert data.pv5_voltage == 300.0

    def test_pv6_voltage_field(self) -> None:
        from pylxpweb.transports.data import InverterRuntimeData
        data = InverterRuntimeData(pv6_voltage=310.0)
        assert data.pv6_voltage == 310.0

    def test_pv5_power_field(self) -> None:
        from pylxpweb.transports.data import InverterRuntimeData
        data = InverterRuntimeData(pv5_power=2500.0)
        assert data.pv5_power == 2500.0

    def test_pv6_power_field(self) -> None:
        from pylxpweb.transports.data import InverterRuntimeData
        data = InverterRuntimeData(pv6_power=2600.0)
        assert data.pv6_power == 2600.0
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/unit/test_pv456_registers.py -v`
Expected: FAIL — `KeyError: 'pv4_voltage'`

**Step 3: Add 15 RegisterDefinition entries to inverter_input.py**

In `src/pylxpweb/registers/inverter_input.py`, add before the closing `)` of `INVERTER_INPUT_REGISTERS` (after the `smart_load_power` entry at address 232):

```python
    # =========================================================================
    # PV4-6 INPUT (V23 Extended, regs 217-231)
    # =========================================================================
    RegisterDefinition(
        address=217,
        canonical_name="pv4_voltage",
        cloud_api_field="vpv4",
        ha_sensor_key="pv4_voltage",
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=RegisterCategory.RUNTIME,
        description="PV4 voltage (V23 extended).",
    ),
    RegisterDefinition(
        address=218,
        canonical_name="pv5_voltage",
        cloud_api_field="vpv5",
        ha_sensor_key="pv5_voltage",
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=RegisterCategory.RUNTIME,
        description="PV5 voltage (V23 extended).",
    ),
    RegisterDefinition(
        address=219,
        canonical_name="pv6_voltage",
        cloud_api_field="vpv6",
        ha_sensor_key="pv6_voltage",
        scale=ScaleFactor.DIV_10,
        unit="V",
        category=RegisterCategory.RUNTIME,
        description="PV6 voltage (V23 extended).",
    ),
    RegisterDefinition(
        address=220,
        canonical_name="pv4_power",
        cloud_api_field="ppv4",
        ha_sensor_key="pv4_power",
        unit="W",
        category=RegisterCategory.RUNTIME,
        description="PV4 power (V23 extended).",
    ),
    RegisterDefinition(
        address=221,
        canonical_name="pv5_power",
        cloud_api_field="ppv5",
        ha_sensor_key="pv5_power",
        unit="W",
        category=RegisterCategory.RUNTIME,
        description="PV5 power (V23 extended).",
    ),
    RegisterDefinition(
        address=222,
        canonical_name="pv6_power",
        cloud_api_field="ppv6",
        ha_sensor_key="pv6_power",
        unit="W",
        category=RegisterCategory.RUNTIME,
        description="PV6 power (V23 extended).",
    ),
    RegisterDefinition(
        address=223,
        canonical_name="epv4_day",
        cloud_api_field="epv4Today",
        ha_sensor_key="epv4_day",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_DAILY,
        description="PV4 daily energy yield.",
    ),
    RegisterDefinition(
        address=224,
        canonical_name="epv4_all",
        cloud_api_field=None,
        ha_sensor_key="epv4_all",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_LIFETIME,
        description="PV4 cumulative energy yield (32-bit, low word).",
    ),
    RegisterDefinition(
        address=226,
        canonical_name="epv5_day",
        cloud_api_field="epv5Today",
        ha_sensor_key="epv5_day",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_DAILY,
        description="PV5 daily energy yield.",
    ),
    RegisterDefinition(
        address=227,
        canonical_name="epv5_all",
        cloud_api_field=None,
        ha_sensor_key="epv5_all",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_LIFETIME,
        description="PV5 cumulative energy yield (32-bit, low word).",
    ),
    RegisterDefinition(
        address=229,
        canonical_name="epv6_day",
        cloud_api_field="epv6Today",
        ha_sensor_key="epv6_day",
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_DAILY,
        description="PV6 daily energy yield.",
    ),
    RegisterDefinition(
        address=230,
        canonical_name="epv6_all",
        cloud_api_field=None,
        ha_sensor_key="epv6_all",
        bit_width=32,
        scale=ScaleFactor.DIV_10,
        unit="kWh",
        category=RegisterCategory.ENERGY_LIFETIME,
        description="PV6 cumulative energy yield (32-bit, low word).",
    ),
```

**Important**: The `smart_load_power` entry (address 232) should remain AFTER these new PV entries. Reorder so entries are sorted by address (217-231 before 232).

**Step 4: Add PV5/6 fields to InverterRuntimeData**

In `src/pylxpweb/transports/data.py`, add after `pv3_power` field (line ~89):

```python
    pv4_voltage: float | None = None  # V (V23 extended)
    pv4_power: float | None = None  # W (V23 extended)
    pv5_voltage: float | None = None  # V (V23 extended)
    pv5_power: float | None = None  # W (V23 extended)
    pv6_voltage: float | None = None  # V (V23 extended)
    pv6_power: float | None = None  # W (V23 extended)
```

Note: `vpv4`/`ppv4` already exist in `models.py` but NOT in `InverterRuntimeData`. PV4 voltage/power are added here alongside PV5/6 for completeness.

**Step 5: Run tests to verify they pass**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/unit/test_pv456_registers.py -v`
Expected: All PASS

**Step 6: Run full test suite**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/ -x --tb=short`
Expected: All PASS

**Step 7: Commit**

```bash
cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb
git add src/pylxpweb/registers/inverter_input.py src/pylxpweb/transports/data.py tests/unit/test_pv456_registers.py
git commit -m "feat: add V23 PV4-6 input registers (217-231) and data model fields

15 new RegisterDefinitions for PV4-6 voltage, power, and energy.
Cloud API fields follow existing pattern (vpv4-6, ppv4-6, epv4-6Today).
InverterRuntimeData extended with pv4-6 voltage/power fields."
```

---

### Task 5: Register 179 Full Bitfield (FUNC_EN_4)

**Files:**
- Modify: `src/pylxpweb/registers/inverter_holding.py`
- Test: `tests/unit/test_reg179_bitfield.py` (new)

**Step 1: Write the failing tests**

Create `tests/unit/test_reg179_bitfield.py`:

```python
"""Unit tests for register 179 (FUNC_EN_4) complete bitfield mapping."""

from __future__ import annotations

from pylxpweb.registers.inverter_holding import (
    BY_ADDRESS,
    BY_API_KEY,
    BY_NAME,
    HoldingCategory,
    bitfield_entries_for_address,
)


class TestReg179Bitfield:
    """Test all 16 bits of register 179 are mapped."""

    def test_all_16_bits_mapped(self) -> None:
        entries = bitfield_entries_for_address(179)
        bits = {e.bit_position for e in entries}
        assert bits == set(range(16)), f"Missing bits: {set(range(16)) - bits}"

    def test_all_entries_are_function_category(self) -> None:
        for entry in bitfield_entries_for_address(179):
            assert entry.category == HoldingCategory.FUNCTION

    def test_ac_ct_direction_bit0(self) -> None:
        reg = BY_NAME["ac_ct_direction"]
        assert reg.address == 179
        assert reg.bit_position == 0
        assert reg.api_param_key == "FUNC_AC_CT_DIRECTION"

    def test_battery_charge_control_bit9(self) -> None:
        """Bit 9 must match existing legacy constant FUNC_EXT_BIT_BAT_CHARGE_CONTROL."""
        reg = BY_NAME["battery_charge_control"]
        assert reg.address == 179
        assert reg.bit_position == 9
        assert reg.api_param_key == "FUNC_BAT_CHG_CONTROL"

    def test_battery_discharge_control_bit10(self) -> None:
        """Bit 10 must match existing legacy constant FUNC_EXT_BIT_BAT_DISCHARGE_CONTROL."""
        reg = BY_NAME["battery_discharge_control"]
        assert reg.address == 179
        assert reg.bit_position == 10
        assert reg.api_param_key == "FUNC_BAT_DISCHG_CONTROL"

    def test_ac_coupling_bit11(self) -> None:
        reg = BY_NAME["ac_coupling_enable"]
        assert reg.address == 179
        assert reg.bit_position == 11
        assert reg.api_param_key == "FUNC_AC_COUPLING"

    def test_smart_load_bit13(self) -> None:
        reg = BY_NAME["smart_load_enable"]
        assert reg.address == 179
        assert reg.bit_position == 13
        assert reg.api_param_key == "FUNC_SMART_LOAD_EN"

    def test_rsd_disable_bit14(self) -> None:
        reg = BY_NAME["rsd_disable"]
        assert reg.address == 179
        assert reg.bit_position == 14

    def test_ongrid_always_on_bit15(self) -> None:
        reg = BY_NAME["ongrid_always_on"]
        assert reg.address == 179
        assert reg.bit_position == 15

    def test_api_key_lookups(self) -> None:
        assert "FUNC_AC_CT_DIRECTION" in BY_API_KEY
        assert "FUNC_BAT_CHG_CONTROL" in BY_API_KEY
        assert "FUNC_BAT_DISCHG_CONTROL" in BY_API_KEY
        assert "FUNC_AC_COUPLING" in BY_API_KEY
        assert "FUNC_SMART_LOAD_EN" in BY_API_KEY
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/unit/test_reg179_bitfield.py -v`
Expected: FAIL — `KeyError: 'ac_ct_direction'`

**Step 3: Add 16 HoldingRegisterDefinition entries**

In `src/pylxpweb/registers/inverter_holding.py`, add a new section before the lookup indexes:

```python
    # =========================================================================
    # EXTENDED FUNCTION ENABLE 4 (reg 179) — 16-bit bitfield
    # =========================================================================
    # Source: lxp_modbus H_FUNCTION_ENABLE_4 and EG4 firmware analysis.
    # Bits 9, 10, 11, 13 match existing legacy constants in constants/registers.py.
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
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/unit/test_reg179_bitfield.py -v`
Expected: All PASS

**Step 5: Run full test suite**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/ -x --tb=short`
Expected: All PASS

**Step 6: Commit**

```bash
cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb
git add src/pylxpweb/registers/inverter_holding.py tests/unit/test_reg179_bitfield.py
git commit -m "feat: map all 16 bits of register 179 (FUNC_EN_4) in canonical system

Previously completely unmapped. All 16 bits now have HoldingRegisterDefinition
entries with api_param_key values from lxp_modbus H_FUNCTION_ENABLE_4.
Bits 9/10/11/13 have ha_entity_key for existing HA switch entities."
```

---

### Task 6: Register 233 Full Bitfield (FUNC_EN_5)

**Files:**
- Modify: `src/pylxpweb/registers/inverter_holding.py`
- Test: `tests/unit/test_reg233_bitfield.py` (new)

**Step 1: Write the failing tests**

Create `tests/unit/test_reg233_bitfield.py`:

```python
"""Unit tests for register 233 (FUNC_EN_5) bitfield mapping."""

from __future__ import annotations

from pylxpweb.registers.inverter_holding import (
    BY_API_KEY,
    BY_NAME,
    HoldingCategory,
    bitfield_entries_for_address,
)


class TestReg233Bitfield:
    """Test register 233 bitfield entries."""

    def test_expected_bits_mapped(self) -> None:
        entries = bitfield_entries_for_address(233)
        bits = {e.bit_position for e in entries}
        expected = {0, 1, 2, 3, 10, 12}
        assert expected.issubset(bits), f"Missing bits: {expected - bits}"

    def test_quick_charge_start_bit0(self) -> None:
        reg = BY_NAME["quick_charge_start_enable"]
        assert reg.address == 233
        assert reg.bit_position == 0
        assert reg.api_param_key == "FUNC_QUICK_CHG_START_EN"

    def test_battery_backup_bit1(self) -> None:
        reg = BY_NAME["battery_backup_enable"]
        assert reg.address == 233
        assert reg.bit_position == 1
        assert reg.api_param_key == "FUNC_BATT_BACKUP_EN"

    def test_maintenance_bit2(self) -> None:
        reg = BY_NAME["maintenance_enable"]
        assert reg.address == 233
        assert reg.bit_position == 2

    def test_weekly_schedule_bit3(self) -> None:
        """Bit 3 is the 7-day scheduling toggle (FUNC_ENERTEK_WORKING_MODE)."""
        reg = BY_NAME["weekly_schedule_enable"]
        assert reg.address == 233
        assert reg.bit_position == 3
        assert reg.api_param_key == "FUNC_ENERTEK_WORKING_MODE"

    def test_over_freq_fast_stop_bit10(self) -> None:
        reg = BY_NAME["over_freq_fast_stop"]
        assert reg.address == 233
        assert reg.bit_position == 10

    def test_sporadic_charge_bit12(self) -> None:
        """Bit 12 must match existing legacy constant FUNC_EN_2_BIT_SPORADIC_CHARGE."""
        reg = BY_NAME["sporadic_charge_enable"]
        assert reg.address == 233
        assert reg.bit_position == 12
        assert reg.api_param_key == "FUNC_SPORADIC_CHARGE"
        assert reg.ha_entity_key == "sporadic_charge"

    def test_api_key_lookups(self) -> None:
        assert "FUNC_ENERTEK_WORKING_MODE" in BY_API_KEY
        assert "FUNC_SPORADIC_CHARGE" in BY_API_KEY
        assert "FUNC_QUICK_CHG_START_EN" in BY_API_KEY
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/unit/test_reg233_bitfield.py -v`
Expected: FAIL — `KeyError: 'quick_charge_start_enable'`

**Step 3: Add HoldingRegisterDefinition entries**

In `src/pylxpweb/registers/inverter_holding.py`, add after the register 179 section:

```python
    # =========================================================================
    # EXTENDED FUNCTION ENABLE 5 (reg 233) — partial bitfield
    # =========================================================================
    # Source: lxp_modbus H_FUNCTION_ENABLE_5.
    # Bits 4-7 (dry contactor multiplex) and 8-9 (external CT position)
    # are multi-bit fields, mapped as value registers rather than individual bits.
    # Bit 12 matches existing legacy constant FUNC_EN_2_BIT_SPORADIC_CHARGE.
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
```

Note: Bits 4-7 (dry contactor multiplex, 4-bit value) and bits 8-9 (external CT position, 2-bit value) are multi-bit fields. They can be added later as value-type entries with masking if needed. For now, only single-bit boolean entries are mapped.

**Step 4: Run tests to verify they pass**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/unit/test_reg233_bitfield.py -v`
Expected: All PASS

**Step 5: Run full test suite**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/ -x --tb=short`
Expected: All PASS

**Step 6: Commit**

```bash
cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb
git add src/pylxpweb/registers/inverter_holding.py tests/unit/test_reg233_bitfield.py
git commit -m "feat: map register 233 (FUNC_EN_5) bitfield in canonical system

6 single-bit entries including:
- weekly_schedule_enable (bit 3): 7-day scheduling toggle
- sporadic_charge_enable (bit 12): matches existing legacy constant
Multi-bit fields (bits 4-9) deferred to separate PR."
```

---

### Task 7: 7-Day Scheduling Registers (500-723)

**Files:**
- Create: `src/pylxpweb/registers/scheduling.py`
- Test: `tests/unit/test_scheduling_registers.py` (new)

**Step 1: Write the failing tests**

Create `tests/unit/test_scheduling_registers.py`:

```python
"""Unit tests for 7-day scheduling register definitions (regs 500-723)."""

from __future__ import annotations

from pylxpweb.registers.scheduling import (
    DAYS,
    SCHEDULE_BY_ADDRESS,
    SCHEDULE_BY_API_KEY,
    SCHEDULE_BY_NAME,
    SCHEDULE_REGISTERS,
    SCHEDULE_TYPES,
    ScheduleTypeConfig,
)


class TestScheduleTypeConfig:
    """Test schedule type configuration."""

    def test_four_schedule_types(self) -> None:
        assert len(SCHEDULE_TYPES) == 4

    def test_ac_charge_config(self) -> None:
        ac = SCHEDULE_TYPES[0]
        assert ac.name == "ac_charge"
        assert ac.base_address == 500

    def test_forced_charge_config(self) -> None:
        fc = SCHEDULE_TYPES[1]
        assert fc.name == "forced_charge"
        assert fc.base_address == 556

    def test_forced_discharge_config(self) -> None:
        fd = SCHEDULE_TYPES[2]
        assert fd.name == "forced_discharge"
        assert fd.base_address == 612

    def test_peak_shaving_config(self) -> None:
        ps = SCHEDULE_TYPES[3]
        assert ps.name == "peak_shaving"
        assert ps.base_address == 668

    def test_seven_days(self) -> None:
        assert len(DAYS) == 7
        assert DAYS[0] == "mon"
        assert DAYS[6] == "sun"


class TestScheduleRegisterGeneration:
    """Test parametric register generation."""

    def test_total_register_count(self) -> None:
        """4 types x 7 days x 2 slots x 4 fields = 224 registers."""
        assert len(SCHEDULE_REGISTERS) == 224

    def test_address_range(self) -> None:
        addresses = {r.address for r in SCHEDULE_REGISTERS}
        assert min(addresses) == 500
        assert max(addresses) == 723

    def test_no_duplicate_addresses(self) -> None:
        addresses = [r.address for r in SCHEDULE_REGISTERS]
        assert len(addresses) == len(set(addresses))

    def test_no_duplicate_names(self) -> None:
        names = [r.canonical_name for r in SCHEDULE_REGISTERS]
        assert len(names) == len(set(names))

    def test_all_writable(self) -> None:
        for reg in SCHEDULE_REGISTERS:
            assert reg.writable is True

    def test_all_schedule_category(self) -> None:
        from pylxpweb.registers.inverter_holding import HoldingCategory
        for reg in SCHEDULE_REGISTERS:
            assert reg.category == HoldingCategory.SCHEDULE


class TestScheduleRegisterNaming:
    """Test naming conventions for generated registers."""

    def test_first_register_name(self) -> None:
        """AC charge, Monday, slot 1, power_cmd."""
        reg = SCHEDULE_REGISTERS[0]
        assert reg.canonical_name == "ac_charge_power_cmd_1_mon"
        assert reg.address == 500

    def test_slot2_name(self) -> None:
        """AC charge, Monday, slot 2, power_cmd."""
        reg = SCHEDULE_BY_NAME["ac_charge_power_cmd_2_mon"]
        assert reg.address == 504

    def test_tuesday_name(self) -> None:
        """AC charge, Tuesday, slot 1, power_cmd."""
        reg = SCHEDULE_BY_NAME["ac_charge_power_cmd_1_tue"]
        assert reg.address == 508

    def test_last_register(self) -> None:
        """Peak shaving, Sunday, slot 2, time_end."""
        last = SCHEDULE_REGISTERS[-1]
        assert last.canonical_name == "peak_shaving_time_end_2_sun"
        assert last.address == 723


class TestScheduleLookupIndexes:
    """Test lookup dictionaries."""

    def test_by_address_complete(self) -> None:
        assert len(SCHEDULE_BY_ADDRESS) == 224

    def test_by_name_complete(self) -> None:
        assert len(SCHEDULE_BY_NAME) == 224

    def test_by_api_key_complete(self) -> None:
        assert len(SCHEDULE_BY_API_KEY) == 224

    def test_address_lookup(self) -> None:
        reg = SCHEDULE_BY_ADDRESS[500]
        assert reg.canonical_name == "ac_charge_power_cmd_1_mon"

    def test_api_key_pattern(self) -> None:
        """API keys follow cloud API naming pattern."""
        reg = SCHEDULE_BY_NAME["ac_charge_power_cmd_1_mon"]
        assert reg.api_param_key == "ubACChgPowerCMD1_Day_1"
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/unit/test_scheduling_registers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pylxpweb.registers.scheduling'`

**Step 3: Write the implementation**

Create `src/pylxpweb/registers/scheduling.py`:

```python
"""7-day scheduling register definitions (holding registers 500-723).

224 registers generated parametrically from schedule type templates.
Active only when register 233 bit 3 (FUNC_ENERTEK_WORKING_MODE) is enabled.
When disabled, daily schedule registers 68-89 are in effect instead.

Cloud API:
  Read:   POST /web/maintain/remoteWeeklyOperation/readValues
  Write:  POST /web/maintain/remoteWeeklyOperation/setValues
  Toggle: POST /web/maintain/remoteSet/functionControl (FUNC_ENERTEK_WORKING_MODE)

Structure per schedule type:
  7 days x 2 slots x 4 registers = 56 registers
  4 types x 56 = 224 total registers
"""

from __future__ import annotations

from dataclasses import dataclass

from pylxpweb.registers.inverter_holding import HoldingCategory, HoldingRegisterDefinition
from pylxpweb.registers.inverter_input import ALL, ScaleFactor


@dataclass(frozen=True)
class ScheduleTypeConfig:
    """Configuration for one schedule type (AC charge, forced charge, etc.)."""

    name: str  # "ac_charge"
    base_address: int  # 500
    api_write_suffix: str  # "AC_CHARGE"
    api_read_prefix: str  # "ubACChg"


SCHEDULE_TYPES: tuple[ScheduleTypeConfig, ...] = (
    ScheduleTypeConfig("ac_charge", 500, "AC_CHARGE", "ubACChg"),
    ScheduleTypeConfig("forced_charge", 556, "FORCED_CHARGE", "ubForcedChg"),
    ScheduleTypeConfig("forced_discharge", 612, "FORCED_DISCHARGE", "ubForcedDischg"),
    ScheduleTypeConfig("peak_shaving", 668, "GRID_PEAK_SHAVING", "ubGridPeakShav"),
)

DAYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# Per-slot field definitions: (offset, field_name, api_field_name)
_SLOT_FIELDS: tuple[tuple[int, str, str], ...] = (
    (0, "power_cmd", "PowerCMD"),
    (1, "volt_limit", "VoltLimit"),
    (2, "time_start", "StartHour"),  # Packed start time
    (3, "time_end", "EndHour"),  # Packed end time
)


def _generate_schedule_registers() -> tuple[HoldingRegisterDefinition, ...]:
    """Generate all 224 schedule register definitions from templates.

    Address formula:
        base + day_index*8 + slot*4 + field_offset

    Naming:
        canonical_name: {type}_{field}_{slot+1}_{day}
        api_param_key:  {prefix}{ApiField}{slot+1}_Day_{day_index+1}
    """
    regs: list[HoldingRegisterDefinition] = []

    for stype in SCHEDULE_TYPES:
        for day_idx, day in enumerate(DAYS):
            for slot in range(2):
                for offset, field, api_field in _SLOT_FIELDS:
                    address = stype.base_address + day_idx * 8 + slot * 4 + offset
                    canonical = f"{stype.name}_{field}_{slot + 1}_{day}"
                    api_key = f"{stype.api_read_prefix}{api_field}{slot + 1}_Day_{day_idx + 1}"

                    regs.append(
                        HoldingRegisterDefinition(
                            address=address,
                            canonical_name=canonical,
                            api_param_key=api_key,
                            writable=True,
                            category=HoldingCategory.SCHEDULE,
                            models=ALL,
                            description=(
                                f"{stype.name.replace('_', ' ').title()} "
                                f"{field.replace('_', ' ')} "
                                f"slot {slot + 1}, {day.title()}."
                            ),
                        ),
                    )

    return tuple(regs)


SCHEDULE_REGISTERS: tuple[HoldingRegisterDefinition, ...] = _generate_schedule_registers()

# =============================================================================
# LOOKUP INDEXES (built once at import time)
# =============================================================================

SCHEDULE_BY_ADDRESS: dict[int, HoldingRegisterDefinition] = {
    r.address: r for r in SCHEDULE_REGISTERS
}

SCHEDULE_BY_NAME: dict[str, HoldingRegisterDefinition] = {
    r.canonical_name: r for r in SCHEDULE_REGISTERS
}

SCHEDULE_BY_API_KEY: dict[str, HoldingRegisterDefinition] = {
    r.api_param_key: r for r in SCHEDULE_REGISTERS
}
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/unit/test_scheduling_registers.py -v`
Expected: All PASS

**Step 5: Run lint + type check**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run ruff check src/pylxpweb/registers/scheduling.py tests/unit/test_scheduling_registers.py --fix && uv run ruff format src/pylxpweb/registers/scheduling.py tests/unit/test_scheduling_registers.py`
Expected: Clean

**Step 6: Commit**

```bash
cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb
git add src/pylxpweb/registers/scheduling.py tests/unit/test_scheduling_registers.py
git commit -m "feat: add 7-day scheduling register definitions (500-723)

224 HoldingRegisterDefinitions generated parametrically from templates:
- 4 schedule types (AC charge, forced charge, forced discharge, peak shaving)
- 7 days x 2 slots x 4 fields per type
- Cloud API key pattern: ubACChgPowerCMD1_Day_1 etc.

Active when register 233 bit 3 (weekly_schedule_enable) is set."
```

---

### Task 8: Export New Modules from Package __init__.py

**Files:**
- Modify: `src/pylxpweb/registers/__init__.py`
- Modify: `src/pylxpweb/constants/__init__.py`

**Step 1: Write the failing test**

Append to `tests/unit/test_fault_codes.py`:

```python
class TestPackageExports:
    """Test new symbols are accessible from package-level imports."""

    def test_fault_codes_from_constants(self) -> None:
        from pylxpweb.constants.fault_codes import (
            BMS_FAULT_CODES,
            INVERTER_FAULT_CODES,
            decode_bms_code,
            decode_fault_bits,
        )
        assert len(INVERTER_FAULT_CODES) > 0

    def test_scheduling_from_registers(self) -> None:
        from pylxpweb.registers import (
            SCHEDULE_BY_ADDRESS,
            SCHEDULE_BY_API_KEY,
            SCHEDULE_BY_NAME,
            SCHEDULE_REGISTERS,
            ScheduleTypeConfig,
        )
        assert len(SCHEDULE_REGISTERS) == 224
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/unit/test_fault_codes.py::TestPackageExports -v`
Expected: FAIL — `ImportError: cannot import name 'SCHEDULE_REGISTERS' from 'pylxpweb.registers'`

**Step 3: Update registers/__init__.py**

In `src/pylxpweb/registers/__init__.py`, add imports and __all__ entries for the scheduling module:

Add to imports section:
```python
from pylxpweb.registers.scheduling import (
    SCHEDULE_REGISTERS,
    SCHEDULE_TYPES,
    ScheduleTypeConfig,
)
from pylxpweb.registers.scheduling import (
    SCHEDULE_BY_ADDRESS,
)
from pylxpweb.registers.scheduling import (
    SCHEDULE_BY_API_KEY,
)
from pylxpweb.registers.scheduling import (
    SCHEDULE_BY_NAME,
)
```

Add to `__all__` list:
```python
    # Scheduling registers
    "SCHEDULE_BY_ADDRESS",
    "SCHEDULE_BY_API_KEY",
    "SCHEDULE_BY_NAME",
    "SCHEDULE_REGISTERS",
    "SCHEDULE_TYPES",
    "ScheduleTypeConfig",
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/unit/test_fault_codes.py::TestPackageExports -v`
Expected: All PASS

**Step 5: Run full test suite**

Run: `cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb && uv run pytest tests/ -x --tb=short`
Expected: All PASS

**Step 6: Commit**

```bash
cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb
git add src/pylxpweb/registers/__init__.py tests/unit/test_fault_codes.py
git commit -m "feat: export scheduling registers and fault codes from package __init__

SCHEDULE_REGISTERS, SCHEDULE_BY_ADDRESS, SCHEDULE_BY_API_KEY,
SCHEDULE_BY_NAME, SCHEDULE_TYPES, ScheduleTypeConfig now importable
from pylxpweb.registers."
```

---

### Task 9: Final Validation

**Step 1: Run full lint + type check + tests**

```bash
cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb
uv run ruff check src/pylxpweb/ tests/ --fix && uv run ruff format src/pylxpweb/ tests/
uv run mypy --strict src/pylxpweb/constants/fault_codes.py src/pylxpweb/registers/scheduling.py
uv run pytest tests/ -x --tb=short -q
```

Expected: All clean, all tests pass.

**Step 2: Verify register counts**

```bash
cd /Users/bryanli/Projects/joyfulhouse/python/pylxpweb
uv run python -c "
from pylxpweb.registers.inverter_input import INVERTER_INPUT_REGISTERS
from pylxpweb.registers.inverter_holding import INVERTER_HOLDING_REGISTERS
from pylxpweb.registers.scheduling import SCHEDULE_REGISTERS
from pylxpweb.constants.fault_codes import INVERTER_FAULT_CODES, INVERTER_WARNING_CODES, BMS_FAULT_CODES, BMS_WARNING_CODES

print(f'Input registers: {len(INVERTER_INPUT_REGISTERS)}')
print(f'Holding registers: {len(INVERTER_HOLDING_REGISTERS)}')
print(f'Schedule registers: {len(SCHEDULE_REGISTERS)}')
print(f'Fault code dicts: {len(INVERTER_FAULT_CODES)}+{len(INVERTER_WARNING_CODES)}+{len(BMS_FAULT_CODES)}+{len(BMS_WARNING_CODES)}')
print(f'Total new definitions: ~{12 + 16 + 6 + 224}')
"
```

Expected output:
```
Input registers: ~100+ (12 more than before)
Holding registers: ~130+ (22 more than before)
Schedule registers: 224
Fault code dicts: 21+30+15+15
Total new definitions: ~258
```

**Step 3: Commit final summary (if needed)**

No additional commit needed — each task was committed individually.

---

## Summary

| Task | Description | New Defs | Files |
|------|-------------|----------|-------|
| 1 | Fault/warning code catalogs | 4 dicts + 2 funcs | `constants/fault_codes.py` (new) |
| 2 | Set ha_sensor_key on fault regs | 4 modifications | `registers/inverter_input.py` |
| 3 | Data model fault properties | 2 properties | `transports/data.py` |
| 4 | V23 PV4-6 input registers | 12 RegisterDefs + 6 fields | `registers/inverter_input.py`, `transports/data.py` |
| 5 | Register 179 full bitfield | 16 HoldingRegDefs | `registers/inverter_holding.py` |
| 6 | Register 233 bitfield | 6 HoldingRegDefs | `registers/inverter_holding.py` |
| 7 | 7-day scheduling (500-723) | 224 HoldingRegDefs | `registers/scheduling.py` (new) |
| 8 | Package exports | 0 | `registers/__init__.py` |
| 9 | Final validation | 0 | N/A |
| **Total** | | **~262 new definitions** | **3 modified, 2 new files** |
