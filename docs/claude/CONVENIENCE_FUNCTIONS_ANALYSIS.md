# Convenience Functions Analysis & Recommendations

**Date**: 2025-11-20
**Source**: EG4 Web Monitor HA Integration v2.2.7 Number Entities
**Purpose**: Identify useful convenience methods based on real-world usage patterns

---

## Executive Summary

Based on analysis of the production HA integration, we've identified **9 number entity types** that represent common user operations. This document analyzes which deserve dedicated convenience methods in pylxpweb.

**Recommendation**: Add **5 HIGH-value convenience methods** (4-6 hours implementation)

---

## Current Implementation Status

### ✅ Already Implemented in pylxpweb

| Function | Implementation | Source | Status |
|----------|---------------|---------|---------|
| **Battery SOC Limits** | `set_battery_soc_limits(on_grid, off_grid)` | `devices/inverters/base.py:289` | ✅ Complete |
| **AC Charge Config** | `set_ac_charge(enabled, power, soc_limit)` | `devices/inverters/hybrid.py:98` | ✅ Complete |
| **All Control Functions** | `control.write_parameter(serial, param, value)` | `endpoints/control.py:116` | ✅ Generic method |
| **Parameter Reading** | `control.read_device_parameters_ranges(serial)` | `endpoints/control.py:527` | ✅ Complete |

### ⚠️ Available via Generic Methods

All number entity operations can be performed using:
```python
await client.control.write_parameter(serial, "PARAM_NAME", "value")
```

**Question**: Do we need convenience wrappers for common operations?

---

## HA Integration Number Entities Analysis

### Complete Entity List (9 Total)

| Entity | Parameter | Range | Unit | Use Case | Priority |
|--------|-----------|-------|------|----------|----------|
| **System Charge SOC Limit** | HOLD_SYSTEM_CHARGE_SOC_LIMIT | 0-100 | % | Target SOC for solar/AC charging | ⚠️ MEDIUM |
| **AC Charge Power** | HOLD_AC_CHARGE_POWER_CMD | 0-15 | kW | Max AC grid charge power | ⚠️ MEDIUM |
| **PV Charge Power** | HOLD_FORCED_CHG_POWER_CMD | 0-15 | kW | Forced PV charge power limit | ⚠️ MEDIUM |
| **Grid Peak Shaving Power** | _12K_HOLD_GRID_PEAK_SHAVING_POWER | 0-12 | kW | Grid import limit during peak shaving | ⚠️ MEDIUM |
| **AC Charge SOC Limit** | HOLD_AC_CHARGE_SOC_LIMIT | 0-100 | % | Stop AC charge at this SOC | ✅ **HIGH** |
| **On-Grid SOC Cutoff** | HOLD_DISCHG_CUT_OFF_SOC_EOD | 0-100 | % | Min SOC before stopping discharge (grid) | ✅ **HIGH** |
| **Off-Grid SOC Cutoff** | HOLD_SOC_LOW_LIMIT_EPS_DISCHG | 0-100 | % | Min SOC before stopping discharge (off-grid) | ✅ **HIGH** |
| **Battery Charge Current** | HOLD_LEAD_ACID_CHARGE_RATE | 0-250 | A | Max battery charge current | ✅ **HIGH** |
| **Battery Discharge Current** | HOLD_LEAD_ACID_DISCHARGE_RATE | 0-250 | A | Max battery discharge current | ✅ **HIGH** |

---

## Priority Analysis

### ✅ HIGH Priority (5 entities)

These are **frequently used** in automations and have **safety implications**:

1. **Battery Charge/Discharge Current** (NEW in v2.2.6)
   - Critical for preventing inverter throttling
   - Used in weather-based automations
   - TOU optimization
   - Battery health management

2. **SOC Limits** (AC Charge, On-Grid, Off-Grid)
   - Battery protection settings
   - Frequently adjusted based on season/usage
   - Critical safety parameters

**Recommendation**: ✅ **Add convenience methods** (HIGH value, HIGH usage)

### ⚠️ MEDIUM Priority (4 entities)

These are **less frequently changed** after initial setup:

1. **Power Limits** (AC Charge, PV Charge, Grid Peak Shaving)
   - Usually set once during installation
   - Occasionally adjusted for seasonal optimization
   - Less critical than SOC limits

2. **System Charge SOC Limit**
   - General charge target
   - Modified less frequently than safety limits

**Recommendation**: ⚠️ **Optional** - Generic `write_parameter()` is adequate

---

## Recommended Convenience Methods

### Category 1: Battery Current Control (NEW)

**Value Proposition**:
- **NEW feature** in v2.2.6 (November 2025)
- **High usage** in automations (weather, TOU, throttling prevention)
- **Complex validation** (0-250 A, battery safety limits)
- **Frequent adjustments** (daily or hourly in advanced setups)

**Recommendation**: ✅ **HIGH PRIORITY** - Add convenience methods

```python
# Add to ControlEndpoints class

async def set_battery_charge_current(
    self,
    inverter_sn: str,
    amperes: int,
    *,
    validate_battery_limits: bool = True,
) -> SuccessResponse:
    """Set battery charge current limit.

    Controls the maximum current allowed to charge batteries.
    Common use cases:
    - Prevent inverter throttling during high solar production
    - Time-of-use optimization (reduce charge during peak rates)
    - Battery health management (gentle charging)
    - Weather-based automation (reduce on sunny days, maximize on cloudy)

    Args:
        inverter_sn: Inverter serial number
        amperes: Charge current limit (0-250 A)
        validate_battery_limits: Warn if value exceeds typical battery limits

    Returns:
        SuccessResponse: Operation result

    Raises:
        ValueError: If amperes not in valid range (0-250 A)

    Example:
        # Prevent throttling on sunny days (limit to ~4kW charge at 48V)
        >>> await client.control.set_battery_charge_current("1234567890", 80)

        # Maximum charge on cloudy days
        >>> await client.control.set_battery_charge_current("1234567890", 200)

    Power Calculation (48V nominal):
    - 50A = ~2.4kW
    - 100A = ~4.8kW
    - 150A = ~7.2kW
    - 200A = ~9.6kW
    - 250A = ~12kW

    Safety:
        CRITICAL: Never exceed your battery's maximum charge current rating.
        Check battery manufacturer specifications before setting high values.
        Monitor battery temperature during high current operations.
    """
    if not (0 <= amperes <= 250):
        raise ValueError(
            f"Battery charge current must be between 0-250 A, got {amperes}"
        )

    if validate_battery_limits and amperes > 200:
        import logging
        logging.warning(
            "Setting battery charge current to %d A. "
            "Ensure this does not exceed your battery's maximum rating. "
            "Typical limits: 200A for 10kWh, 150A for 7.5kWh, 100A for 5kWh.",
            amperes
        )

    return await self.write_parameter(
        inverter_sn,
        "HOLD_LEAD_ACID_CHARGE_RATE",
        str(amperes)
    )

async def set_battery_discharge_current(
    self,
    inverter_sn: str,
    amperes: int,
    *,
    validate_battery_limits: bool = True,
) -> SuccessResponse:
    """Set battery discharge current limit.

    Controls the maximum current allowed to discharge from batteries.
    Common use cases:
    - Preserve battery capacity during grid outages
    - Extend battery lifespan (conservative discharge)
    - Emergency power management

    Args:
        inverter_sn: Inverter serial number
        amperes: Discharge current limit (0-250 A)
        validate_battery_limits: Warn if value exceeds typical battery limits

    Returns:
        SuccessResponse: Operation result

    Raises:
        ValueError: If amperes not in valid range (0-250 A)

    Example:
        # Conservative discharge for battery longevity
        >>> await client.control.set_battery_discharge_current("1234567890", 150)

        # Minimal discharge during grid outage
        >>> await client.control.set_battery_discharge_current("1234567890", 50)
    """
    if not (0 <= amperes <= 250):
        raise ValueError(
            f"Battery discharge current must be between 0-250 A, got {amperes}"
        )

    if validate_battery_limits and amperes > 200:
        import logging
        logging.warning(
            "Setting battery discharge current to %d A. "
            "Ensure this does not exceed your battery's maximum rating.",
            amperes
        )

    return await self.write_parameter(
        inverter_sn,
        "HOLD_LEAD_ACID_DISCHARGE_RATE",
        str(amperes)
    )

async def get_battery_charge_current(self, inverter_sn: str) -> int:
    """Get current battery charge current limit.

    Args:
        inverter_sn: Inverter serial number

    Returns:
        int: Current charge current limit in Amperes (0-250 A)

    Example:
        >>> current = await client.control.get_battery_charge_current("1234567890")
        >>> print(f"Charge limit: {current} A (~{current * 0.048:.1f} kW at 48V)")
    """
    params = await self.read_device_parameters_ranges(inverter_sn)
    return int(params.get("HOLD_LEAD_ACID_CHARGE_RATE", 200))

async def get_battery_discharge_current(self, inverter_sn: str) -> int:
    """Get current battery discharge current limit.

    Args:
        inverter_sn: Inverter serial number

    Returns:
        int: Current discharge current limit in Amperes (0-250 A)

    Example:
        >>> current = await client.control.get_battery_discharge_current("1234567890")
        >>> print(f"Discharge limit: {current} A")
    """
    params = await self.read_device_parameters_ranges(inverter_sn)
    return int(params.get("HOLD_LEAD_ACID_DISCHARGE_RATE", 200))
```

**Implementation Effort**: 3-4 hours
**Value**: ✅ **HIGH** - Enables key use cases from v2.2.6

---

### Category 2: SOC Limit Convenience Methods

**Value Proposition**:
- **Already partially implemented** in `HybridInverter.set_ac_charge()`
- **Safety-critical** settings
- **Moderate usage** (set during install, adjusted seasonally)

**Current Status**:
- ✅ `set_battery_soc_limits()` exists in BaseInverter
- ✅ `set_ac_charge(soc_limit=X)` exists in HybridInverter
- ⚠️ No dedicated getters

**Recommendation**: ⚠️ **OPTIONAL** - Add getters for completeness

```python
# Add to ControlEndpoints class (if we want control-level access)

async def set_system_charge_soc_limit(
    self, inverter_sn: str, soc_percent: int
) -> SuccessResponse:
    """Set system charge SOC limit (target SOC for charging).

    This is the target SOC that the system will charge to from solar/AC.

    Args:
        inverter_sn: Inverter serial number
        soc_percent: Target SOC (0-100%)

    Returns:
        SuccessResponse: Operation result

    Example:
        # Set target charge to 95%
        >>> await client.control.set_system_charge_soc_limit("1234567890", 95)
    """
    if not (0 <= soc_percent <= 100):
        raise ValueError(f"SOC must be between 0-100%, got {soc_percent}")

    return await self.write_parameter(
        inverter_sn,
        "HOLD_SYSTEM_CHARGE_SOC_LIMIT",
        str(soc_percent)
    )

async def get_system_charge_soc_limit(self, inverter_sn: str) -> int:
    """Get system charge SOC limit.

    Returns:
        int: Target charge SOC (0-100%)
    """
    params = await self.read_device_parameters_ranges(inverter_sn)
    return int(params.get("HOLD_SYSTEM_CHARGE_SOC_LIMIT", 100))
```

**Implementation Effort**: 1-2 hours
**Value**: ⚠️ **MEDIUM** - Nice to have, but generic method works fine

---

### Category 3: Power Limit Methods (Lower Priority)

**Value Proposition**:
- Set-and-forget parameters
- Less frequent adjustment
- Generic `write_parameter()` is adequate

**Recommendation**: ❌ **LOW PRIORITY** - Skip for now

If needed later:
```python
async def set_ac_charge_power(self, inverter_sn: str, kilowatts: float) -> SuccessResponse:
    """Set AC charge power limit."""
    # Implementation similar to above
    ...

async def set_pv_charge_power(self, inverter_sn: str, kilowatts: float) -> SuccessResponse:
    """Set PV/forced charge power limit."""
    ...

async def set_grid_peak_shaving_power(self, inverter_sn: str, kilowatts: float) -> SuccessResponse:
    """Set grid peak shaving power limit."""
    ...
```

**Implementation Effort**: 2-3 hours
**Value**: ❌ **LOW** - Generic method is fine

---

## Usage Pattern Analysis

### From HA Integration Automations

**High-Frequency Operations** (Daily/Hourly):
1. ✅ Battery charge/discharge current adjustment
   - Weather-based automations
   - TOU optimization
   - Real-time throttling prevention

2. ⚠️ SOC limit adjustments
   - Seasonal changes
   - Usage pattern changes
   - Less frequent than current control

**Low-Frequency Operations** (Setup/Occasional):
1. ❌ Power limits (AC charge, PV charge, peak shaving)
   - Set during installation
   - Rarely changed
   - Generic method is adequate

---

## Comparison: Generic vs Convenience

### Generic Method Approach

**Pros**:
- ✅ Works for everything
- ✅ Minimal code to maintain
- ✅ Maximum flexibility

**Cons**:
- ❌ Requires knowing parameter names
- ❌ No validation
- ❌ No safety warnings
- ❌ No usage examples in method signature

**Example**:
```python
# Generic approach - works but verbose
await client.control.write_parameter(
    "1234567890",
    "HOLD_LEAD_ACID_CHARGE_RATE",
    "80"
)
```

### Convenience Method Approach

**Pros**:
- ✅ Self-documenting API
- ✅ Built-in validation
- ✅ Safety warnings
- ✅ Usage examples in docstring
- ✅ Type hints (int vs str)
- ✅ Better developer experience

**Cons**:
- ❌ More code to maintain
- ❌ Potential for duplication

**Example**:
```python
# Convenience approach - clear and safe
await client.control.set_battery_charge_current(
    "1234567890",
    80  # Integer, with validation and warnings
)
```

---

## Recommended Implementation Plan

### Phase 1: Battery Current Control (HIGH PRIORITY)

**Add to `ControlEndpoints` class**:
1. `set_battery_charge_current(serial, amperes)` - With validation & safety warnings
2. `set_battery_discharge_current(serial, amperes)` - With validation & safety warnings
3. `get_battery_charge_current(serial)` - Read current limit
4. `get_battery_discharge_current(serial)` - Read current limit

**Effort**: 3-4 hours
**Value**: ✅ **HIGH**
**Priority**: ✅ **Implement Now**

**Justification**:
- NEW critical feature from v2.2.6
- High usage in real-world automations
- Complex validation requirements
- Safety-critical (battery protection)
- Enables key use cases (throttling prevention, TOU optimization)

---

### Phase 2: SOC Limit Convenience (OPTIONAL)

**Add to `ControlEndpoints` class**:
1. `set_system_charge_soc_limit(serial, percent)` - Set charge target
2. `get_system_charge_soc_limit(serial)` - Get charge target

**Effort**: 1-2 hours
**Value**: ⚠️ **MEDIUM**
**Priority**: ⚠️ **Optional Enhancement**

**Justification**:
- Already have `set_battery_soc_limits()` in device classes
- Moderate usage frequency
- Generic method works fine
- Can add later if needed

---

### Phase 3: Power Limits (SKIP FOR NOW)

**Skip**:
- AC charge power
- PV charge power
- Grid peak shaving power

**Reason**: Low-frequency operations, generic method is adequate

---

## Developer Experience Comparison

### Scenario: Set battery charge current to prevent throttling

**Without Convenience Methods** (Current):
```python
from pylxpweb import LuxpowerClient

async def prevent_throttling(serial: str):
    async with LuxpowerClient(username, password) as client:
        # Need to know exact parameter name
        await client.control.write_parameter(
            serial,
            "HOLD_LEAD_ACID_CHARGE_RATE",  # Must look this up
            "80"  # String value, no validation
        )
```

**With Convenience Methods** (Proposed):
```python
from pylxpweb import LuxpowerClient

async def prevent_throttling(serial: str):
    async with LuxpowerClient(username, password) as client:
        # Clear, self-documenting, with validation
        await client.control.set_battery_charge_current(
            serial,
            80  # Integer, validated 0-250, safety warnings
        )
```

**Impact**: ✅ Significantly better developer experience for HIGH-usage operations

---

## Final Recommendation Summary

### ✅ IMPLEMENT (Phase 1)

**Battery Current Control Convenience Methods** - 3-4 hours

**Reason**:
- NEW critical feature (v2.2.6)
- HIGH usage frequency
- Complex validation
- Safety warnings needed
- Developer experience improvement

**Methods to Add**:
1. `set_battery_charge_current(serial, amperes)` ✅
2. `set_battery_discharge_current(serial, amperes)` ✅
3. `get_battery_charge_current(serial)` ✅
4. `get_battery_discharge_current(serial)` ✅

---

### ⚠️ OPTIONAL (Phase 2)

**SOC Limit Convenience Methods** - 1-2 hours

**Reason**:
- Already have device-level methods
- Moderate usage
- Generic method is adequate
- Can add later if requested

---

### ❌ SKIP (Phase 3)

**Power Limit Methods**

**Reason**:
- Low usage frequency
- Set-and-forget parameters
- Generic method works fine
- Not worth maintenance burden

---

## Conclusion

**Recommendation**: ✅ **Add 4 battery current control methods** (Phase 1)

These provide the highest value for the lowest maintenance cost, enabling the most important new feature from v2.2.6 with excellent developer experience.

**Total Effort**: 3-4 hours
**Value**: ✅ **HIGH**
**Priority**: ✅ **Recommended for v0.3**

All other operations can continue using the generic `write_parameter()` method, which works perfectly for less frequent operations.
