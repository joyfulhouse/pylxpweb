# Release Notes: pylxpweb v0.2.1

**Date**: 2025-11-20
**Type**: Feature Release
**Breaking Changes**: None

---

## Overview

This release adds convenience methods for battery charge/discharge current control, tracking the new functionality added to the EG4 Web Monitor Home Assistant integration in v2.2.6 (November 2025).

---

## New Features

### Battery Current Control Convenience Methods

Added 4 new convenience methods to `ControlEndpoints` for managing battery charge and discharge current limits:

#### 1. `set_battery_charge_current(inverter_sn, amperes)`

Set battery charge current limit (0-250 A).

**Features**:
- ✅ Input validation (0-250 A range)
- ✅ Safety warnings for high values (>200 A)
- ✅ Type hints (int parameter)
- ✅ Comprehensive docstring with examples
- ✅ Power calculation reference (50A = ~2.4kW at 48V)

**Use Cases**:
- Prevent inverter throttling during high solar production
- Time-of-use (TOU) rate optimization
- Battery health management (gentle charging)
- Weather-based automation

**Example**:
```python
from pylxpweb import LuxpowerClient

async def prevent_throttling():
    async with LuxpowerClient(username, password) as client:
        # Prevent throttling on sunny days (limit to ~4kW charge at 48V)
        await client.control.set_battery_charge_current("1234567890", 80)

        # Maximum charge on cloudy days
        await client.control.set_battery_charge_current("1234567890", 200)
```

#### 2. `set_battery_discharge_current(inverter_sn, amperes)`

Set battery discharge current limit (0-250 A).

**Features**:
- ✅ Input validation (0-250 A range)
- ✅ Safety warnings for high values
- ✅ Type hints (int parameter)
- ✅ Comprehensive docstring with examples

**Use Cases**:
- Preserve battery capacity during grid outages
- Extend battery lifespan (conservative discharge)
- Emergency power management
- Peak load management

**Example**:
```python
async def extend_battery_runtime():
    async with LuxpowerClient(username, password) as client:
        # Conservative discharge for battery longevity
        await client.control.set_battery_discharge_current("1234567890", 150)

        # Minimal discharge during grid outage
        await client.control.set_battery_discharge_current("1234567890", 50)
```

#### 3. `get_battery_charge_current(inverter_sn)`

Get current battery charge current limit.

**Returns**: `int` (0-250 A)

**Example**:
```python
async def check_limits():
    async with LuxpowerClient(username, password) as client:
        current = await client.control.get_battery_charge_current("1234567890")
        print(f"Charge limit: {current} A (~{current * 0.048:.1f} kW at 48V)")
        # Output: Charge limit: 200 A (~9.6 kW at 48V)
```

#### 4. `get_battery_discharge_current(inverter_sn)`

Get current battery discharge current limit.

**Returns**: `int` (0-250 A)

**Example**:
```python
async def check_discharge_limit():
    async with LuxpowerClient(username, password) as client:
        current = await client.control.get_battery_discharge_current("1234567890")
        print(f"Discharge limit: {current} A")
```

---

## Implementation Details

### File Changes

**Modified**:
- `src/pylxpweb/endpoints/control.py` (+165 lines)
  - Added 4 new methods to ControlEndpoints class
  - Comprehensive docstrings with examples
  - Input validation and safety warnings
  - Power calculation references

**Constants** (Already present in v0.2):
- `HOLD_LEAD_ACID_CHARGE_RATE` (constants.py:919)
- `HOLD_LEAD_ACID_DISCHARGE_RATE` (constants.py:922)

### Safety Features

All setter methods include:

1. **Range Validation**: Raises `ValueError` if amperes not in 0-250 range
2. **Safety Warnings**: Logs warning if value > 200 A (typical battery limit)
3. **Optional Validation**: `validate_battery_limits=True` parameter (default)
4. **Typical Battery Limits Reference**:
   - 200A for 10kWh battery bank
   - 150A for 7.5kWh battery bank
   - 100A for 5kWh battery bank

**Warning Messages**:
```
Setting battery charge current to 250 A.
Ensure this does not exceed your battery's maximum rating.
Typical limits: 200A for 10kWh, 150A for 7.5kWh, 100A for 5kWh.
```

### Power Calculation Reference

For 48V nominal battery systems:

| Current (A) | Power (kW) | Use Case |
|-------------|------------|----------|
| 50A | ~2.4kW | Minimal charge (TOU peak hours) |
| 100A | ~4.8kW | Moderate charge |
| 150A | ~7.2kW | High charge |
| 200A | ~9.6kW | Maximum charge (typical) |
| 250A | ~12kW | Maximum API limit |

**Note**: Actual voltage varies with SOC (typically 48-58V), so power will vary.

---

## Testing

### Test Results

✅ **All existing tests pass** (11/11 in test_control_helpers.py)

**Verified**:
- No regressions in existing functionality
- All control helper methods work correctly
- Parameter reading functions correctly
- Linting passes (ruff check)
- Code formatting applied (ruff format)

### Manual Testing Required

Integration testing with real inverter:
1. Set charge current to various values (50A, 100A, 150A, 200A)
2. Verify actual charge current matches set value
3. Check battery temperature during high current operations
4. Verify safety warnings appear in logs for >200A

---

## Migration Guide

### From Generic write_parameter()

**Before** (v0.2):
```python
# Using generic method
await client.control.write_parameter(
    "1234567890",
    "HOLD_LEAD_ACID_CHARGE_RATE",  # Must look up parameter name
    "80"  # String value, no validation
)
```

**After** (v0.2.1):
```python
# Using convenience method
await client.control.set_battery_charge_current(
    "1234567890",
    80  # Integer, validated, with safety warnings
)
```

**Benefits**:
- ✅ Self-documenting API
- ✅ No need to know parameter names
- ✅ Built-in validation
- ✅ Type hints (IDE autocomplete)
- ✅ Safety warnings
- ✅ Usage examples in docstring

### Backward Compatibility

✅ **100% Backward Compatible**

- All existing code continues to work
- Generic `write_parameter()` method still available
- New methods are additions, no changes to existing APIs
- No breaking changes

---

## Use Case Examples

### 1. Prevent Inverter Throttling

**Problem**: 18kPV inverter with 20kW PV array. When batteries are full, system throttles to 12kW AC limit, wasting potential production.

**Solution**: Reduce charge current during high production to force grid export.

```python
async def prevent_throttling_automation(serial: str, weather: str):
    async with LuxpowerClient(username, password) as client:
        if weather == "sunny":
            # Limit charge to ~4kW, allowing 14kW grid export
            await client.control.set_battery_charge_current(serial, 80)
        else:
            # Maximize charge on cloudy days
            await client.control.set_battery_charge_current(serial, 200)
```

### 2. Time-of-Use Optimization

**Problem**: Peak grid export rates 2pm-7pm. Want to maximize export during peak.

**Solution**: Dynamic charge rate based on TOU period.

```python
from datetime import datetime

async def tou_optimization(serial: str):
    async with LuxpowerClient(username, password) as client:
        hour = datetime.now().hour

        if 14 <= hour < 19:  # Peak hours (2pm-7pm)
            # Minimal charge, maximum export
            await client.control.set_battery_charge_current(serial, 50)
        else:  # Off-peak hours
            # Maximum charge rate
            await client.control.set_battery_charge_current(serial, 200)
```

### 3. Battery Health Management

**Problem**: Want to extend battery lifespan with gentle charging.

**Solution**: Conservative charge/discharge rates based on battery C-rating.

```python
async def battery_preservation(serial: str, battery_capacity_ah: int):
    async with LuxpowerClient(username, password) as client:
        # 0.2C charge rate for longevity
        charge_rate = int(battery_capacity_ah * 0.2)
        await client.control.set_battery_charge_current(serial, charge_rate)

        # 0.5C discharge rate for moderate use
        discharge_rate = int(battery_capacity_ah * 0.5)
        await client.control.set_battery_discharge_current(serial, discharge_rate)
```

### 4. Emergency Power Management

**Problem**: Grid outage with limited solar. Need to extend battery runtime.

**Solution**: Limit discharge current to reduce power consumption.

```python
async def grid_outage_mode(serial: str, grid_available: bool):
    async with LuxpowerClient(username, password) as client:
        if not grid_available:
            # Minimal discharge to extend runtime
            await client.control.set_battery_discharge_current(serial, 50)
        else:
            # Normal discharge rate
            await client.control.set_battery_discharge_current(serial, 200)
```

---

## API Reference

### Method Signatures

```python
# ControlEndpoints class

async def set_battery_charge_current(
    self,
    inverter_sn: str,
    amperes: int,
    *,
    validate_battery_limits: bool = True,
) -> SuccessResponse:
    """Set battery charge current limit (0-250 A)."""

async def set_battery_discharge_current(
    self,
    inverter_sn: str,
    amperes: int,
    *,
    validate_battery_limits: bool = True,
) -> SuccessResponse:
    """Set battery discharge current limit (0-250 A)."""

async def get_battery_charge_current(
    self,
    inverter_sn: str,
) -> int:
    """Get current battery charge current limit."""

async def get_battery_discharge_current(
    self,
    inverter_sn: str,
) -> int:
    """Get current battery discharge current limit."""
```

### Parameters

**inverter_sn** (`str`):
- Inverter serial number (10-digit)
- Example: `"1234567890"`

**amperes** (`int`):
- Current limit in Amperes
- Range: 0-250 A
- Raises `ValueError` if out of range

**validate_battery_limits** (`bool`, optional):
- Enable safety warnings for high values
- Default: `True`
- Warnings triggered when `amperes > 200`

### Returns

**Setters** (`SuccessResponse`):
```python
SuccessResponse(
    success=True,  # or False if operation failed
    message=None   # or error message
)
```

**Getters** (`int`):
- Current limit in Amperes (0-250)
- Default: 200 A (if parameter not set)

### Exceptions

**ValueError**:
- Raised if `amperes` not in valid range (0-250 A)
- Message: `"Battery charge current must be between 0-250 A, got {amperes}"`

---

## Documentation Updates

**New Files**:
1. `docs/PARAMETER_REFERENCE.md` - Complete parameter catalog (400+ lines)
2. `docs/claude/BATTERY_CURRENT_CONTROL_IMPLEMENTATION.md` - Implementation guide (600+ lines)
3. `docs/claude/CONVENIENCE_FUNCTIONS_ANALYSIS.md` - Use case analysis (400+ lines)
4. `docs/claude/GAP_VERIFICATION.md` - Feature parity verification
5. `docs/claude/RELEASE_v0.2.1_NOTES.md` - This file

**Updated Files**:
1. `docs/GAP_ANALYSIS.md` - Added v2.2.7 features and battery current control
2. `src/pylxpweb/endpoints/control.py` - Added 4 convenience methods

---

## Feature Comparison

### pylxpweb v0.2.1 vs EG4 Web Monitor v2.2.7

| Feature | HA Integration | pylxpweb v0.2.1 | Status |
|---------|---------------|---------------|--------|
| **Battery Charge Current Control** | ✅ Number entity | ✅ Convenience method | ✅ Complete |
| **Battery Discharge Current Control** | ✅ Number entity | ✅ Convenience method | ✅ Complete |
| **Parameter Reading** | ✅ Multi-range | ✅ `read_device_parameters_ranges()` | ✅ Complete |
| **Input Validation** | ✅ 0-250 A | ✅ 0-250 A | ✅ Complete |
| **Safety Warnings** | ✅ EntityCategory.CONFIG | ✅ Logging warnings | ✅ Complete |
| **State Verification** | ✅ Getter methods | ✅ Getter methods | ✅ Complete |

**Result**: ✅ **100% Feature Parity** for battery current control

---

## Performance Impact

**Minimal Impact**:
- Methods delegate to existing `write_parameter()` and `read_device_parameters_ranges()`
- No additional API calls
- No performance degradation
- Same caching behavior as generic methods

---

## Security Considerations

### Battery Safety

⚠️ **CRITICAL WARNINGS**:

1. **Never exceed battery manufacturer's maximum current rating**
   - Check battery datasheet specifications
   - Account for multiple battery banks in parallel
   - Some batteries have lower limits in cold weather

2. **Monitor battery temperature**
   - High current = heat generation
   - Temperature >45°C (113°F) = potential danger
   - Reduce current if temperature rises

3. **Respect BMS limits**
   - Battery Management System (BMS) may enforce stricter limits
   - BMS limits override API settings
   - Actual current may be lower than set value

4. **API maximum ≠ Battery maximum**
   - API allows up to 250 A
   - Most batteries have lower safe limits
   - Users responsible for setting appropriate values

---

## Known Limitations

1. **No automatic battery capacity detection**
   - Cannot auto-calculate safe C-rating
   - Users must know their battery specifications
   - Future enhancement: battery capacity discovery

2. **No real-time current monitoring in method**
   - Methods set limit, don't monitor actual current
   - Users should check `sensor.battery_current` separately
   - Future enhancement: validation against actual limits

3. **Generic validation thresholds**
   - Warnings at >200 A for all battery types
   - Some batteries safe at 250 A, others limited to 150 A
   - Future enhancement: battery-specific profiles

---

## Future Enhancements

**Potential additions for v0.3**:

1. **Battery capacity detection**
   - Auto-calculate safe C-ratings
   - Personalized safety warnings

2. **Current monitoring integration**
   - Verify actual current vs set limit
   - Alert if BMS overrides setting

3. **Battery-specific profiles**
   - Pre-configured limits for common battery types
   - Enhanced safety validation

4. **Automation helpers**
   - Weather-based current adjustment
   - TOU schedule integration
   - SOC-based dynamic limits

---

## Credits

**Research Source**: EG4 Web Monitor HA Integration v2.2.6-v2.2.7
- Repository: `joyfulhouse/eg4_web_monitor`
- Feature addition: November 2025
- Implementation reference: `custom_components/eg4_web_monitor/number.py:2150-2700`

**Documentation**: `research/eg4_web_monitor/docs/BATTERY_CURRENT_CONTROL.md`

---

## Changelog Summary

### Added
- ✅ `set_battery_charge_current()` - Set charge current limit with validation
- ✅ `set_battery_discharge_current()` - Set discharge current limit with validation
- ✅ `get_battery_charge_current()` - Get current charge limit
- ✅ `get_battery_discharge_current()` - Get current discharge limit

### Changed
- None (all additions, no breaking changes)

### Fixed
- None (new feature, no bug fixes)

### Deprecated
- None

### Removed
- None

### Security
- Added safety warnings for high current values (>200 A)
- Input validation prevents invalid values
- Comprehensive safety documentation

---

## Upgrade Instructions

### Installation

**From PyPI**:
```bash
pip install --upgrade pylxpweb
```

**From source**:
```bash
git pull origin main
pip install -e .
```

### Version Verification

```python
import pylxpweb
print(pylxpweb.__version__)  # Should show 0.3.0
```

### Testing New Features

```python
from pylxpweb import LuxpowerClient

async def test_new_features():
    async with LuxpowerClient(username, password) as client:
        # Test setter
        result = await client.control.set_battery_charge_current(
            "1234567890", 100
        )
        print(f"Set result: {result.success}")

        # Test getter
        current = await client.control.get_battery_charge_current(
            "1234567890"
        )
        print(f"Current limit: {current} A")
```

---

## Support

**Issues**: https://github.com/joyfulhouse/pylxpweb/issues
**Documentation**: `/docs/`
**Examples**: See use case examples above

---

## License

MIT License - See LICENSE file for details
