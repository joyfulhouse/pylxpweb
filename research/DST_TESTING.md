# DST Auto-Detection and Synchronization Testing

**Version**: 1.0.0
**Last Updated**: 2025-11-21

## Overview

This document describes the comprehensive testing strategy for the DST (Daylight Saving Time) auto-detection and synchronization feature implemented in pylxpweb.

## Feature Summary

The DST auto-detection feature automatically:
1. Detects the actual DST status by comparing base timezone with current timezone offset
2. Identifies when the API's `daylightSavingTime` flag is incorrect
3. Auto-corrects the API flag during `Station.load()`
4. Uses `currentTimezoneWithMinute` as the source of truth for timezone calculations

## Test Coverage

### Unit Tests (`tests/unit/test_date_boundaries.py`)

#### 1. `TestStationDateDetection` (5 tests)

Tests the `Station.get_current_date()` method for timezone-aware date detection:

- **test_timezone_gmt_minus_8**: Verifies GMT -8 (PST) parsing
- **test_timezone_gmt_plus_9**: Verifies GMT +9 (JST) parsing with date boundary crossing
- **test_timezone_invalid_format**: Tests graceful fallback to UTC with invalid timezone
- **test_timezone_missing**: Tests UTC fallback when timezone is empty
- **test_timezone_uses_current_timezone_with_minute**: Verifies `currentTimezoneWithMinute` takes priority

#### 2. `TestStationDSTDetection` (7 tests)

Tests the `Station.detect_dst_status()` method for DST detection:

- **test_dst_active_pacific_time**: PDT detection (base=-8, current=-420 min = -7 hours)
- **test_dst_inactive_pacific_time**: PST detection (base=-8, current=-480 min = -8 hours)
- **test_dst_active_eastern_time**: EDT detection (base=-5, current=-240 min = -4 hours)
- **test_dst_inactive_eastern_time**: EST detection (base=-5, current=-300 min = -5 hours)
- **test_dst_europe_summer_time**: CEST detection (base=+1, current=+120 min = +2 hours)
- **test_dst_no_current_timezone_with_minute**: Graceful handling when offset unavailable
- **test_dst_invalid_timezone_format**: Graceful handling with invalid timezone string

#### 3. `TestStationDSTSync` (4 tests)

Tests the `Station.sync_dst_setting()` method for API synchronization:

- **test_sync_corrects_wrong_dst_flag**: Verifies API update when DST flag is wrong
- **test_sync_skips_when_correct**: Verifies no API call when DST is already correct
- **test_sync_handles_api_failure**: Tests graceful handling of API update failures
- **test_sync_cannot_determine_dst**: Verifies skip when DST cannot be determined

**Total Unit Tests**: 29 tests (includes 17 monotonic/cache tests from original implementation)

### Integration Tests (`tests/integration/test_dst_control.py`)

#### 1. Existing Tests (5 tests)

- **test_get_plant_details**: Verifies plant details include DST fields
- **test_dst_toggle**: Tests manual DST toggle functionality
- **test_update_plant_config**: Tests DST update via hybrid approach
- **test_hybrid_mapping_static_path**: Tests static mapping for common countries
- **test_invalid_plant_id**: Tests handling of invalid plant IDs

#### 2. New Auto-Detection Tests (2 tests)

##### **test_dst_auto_detection_and_sync**

**Purpose**: Validates the complete auto-detection and synchronization workflow

**Test Flow**:
1. Gets current API DST flag (original state)
2. Calculates expected DST status from timezone offset:
   - Parses base timezone (e.g., "GMT -8" = PST)
   - Reads `currentTimezoneWithMinute` (e.g., -420 = PDT)
   - Computes difference: `current_hours - base_hours`
   - DST active if `difference >= 0.5`
3. Deliberately sets API DST flag to **WRONG** value (opposite of expected)
4. Loads station via `Station.load()` (triggers auto-detection)
5. Verifies:
   - Station's internal `daylight_saving_time` flag was corrected
   - API's `daylightSavingTime` flag was updated to correct value
   - `detect_dst_status()` returns correct value
6. Restores original state

**Expected Behavior**:
- Los Angeles (Pacific Time) currently NOT in DST:
  - Base: GMT -8 (PST)
  - Current: -480 minutes = -8 hours (PST)
  - Difference: 0 hours
  - Expected DST: False
  - If API reports True, should auto-correct to False

**Test Output Example**:
```
Timezone Analysis:
  Base timezone: GMT -8 (-8 hours)
  Current offset: -480 minutes (-8.0 hours)
  Difference: 0.0 hours
  Expected DST: False
  API reports DST: True

Setting API DST flag to WRONG value: True

Loading station (should auto-correct DST to False)...

Station loaded:
  Station DST flag: False
  Station detected DST: False
  API DST flag after sync: False

✅ DST auto-correction successful!
```

##### **test_dst_sync_when_already_correct**

**Purpose**: Verifies that DST sync is a no-op when API flag is already correct

**Test Flow**:
1. Calculates expected DST status
2. Sets API DST flag to **CORRECT** value
3. Loads station
4. Verifies:
   - No API update call was made (efficiency check)
   - DST flag remains correct

**Expected Behavior**:
- Should NOT make API call to `set_daylight_saving_time()`
- DST flag should remain unchanged

**Total Integration Tests**: 7 tests

## DST Detection Algorithm

### Formula

```python
base_hours = int(timezone.replace("GMT", "").strip())  # e.g., -8 for PST
current_hours = current_timezone_with_minute / 60.0    # e.g., -420 / 60 = -7 for PDT
difference = current_hours - base_hours                # e.g., -7 - (-8) = 1
dst_active = difference >= 0.5                         # True if DST active
```

### Examples

| Location | Base (Standard) | Current Offset | Difference | DST Active |
|----------|----------------|----------------|------------|------------|
| Pacific (PST) | GMT -8 | -480 min (-8h) | 0 | ❌ False |
| Pacific (PDT) | GMT -8 | -420 min (-7h) | +1 | ✅ True |
| Eastern (EST) | GMT -5 | -300 min (-5h) | 0 | ❌ False |
| Eastern (EDT) | GMT -5 | -240 min (-4h) | +1 | ✅ True |
| Central EU (CET) | GMT +1 | +60 min (+1h) | 0 | ❌ False |
| Central EU (CEST) | GMT +1 | +120 min (+2h) | +1 | ✅ True |

## Running the Tests

### Unit Tests Only

```bash
# All date boundary tests (29 tests)
uv run pytest tests/unit/test_date_boundaries.py -v

# DST detection tests only (7 tests)
uv run pytest tests/unit/test_date_boundaries.py::TestStationDSTDetection -v

# DST sync tests only (4 tests)
uv run pytest tests/unit/test_date_boundaries.py::TestStationDSTSync -v
```

### Integration Tests Only

```bash
# All DST control tests (7 tests)
uv run pytest tests/integration/test_dst_control.py -v -m integration

# Auto-detection test only
uv run pytest tests/integration/test_dst_control.py::test_dst_auto_detection_and_sync -v -m integration

# No-op test only
uv run pytest tests/integration/test_dst_control.py::test_dst_sync_when_already_correct -v -m integration
```

### All Tests

```bash
# All unit tests (463 tests)
uv run pytest tests/unit/ -v

# All integration tests (requires .env with credentials)
uv run pytest tests/integration/ -v -m integration
```

## Test Environment Requirements

### Unit Tests
- No external dependencies
- Mocked API calls
- Fast execution (<1 second for all DST tests)

### Integration Tests
- Requires `.env` file with:
  ```
  LUXPOWER_USERNAME=your_username
  LUXPOWER_PASSWORD=your_password
  LUXPOWER_BASE_URL=https://monitor.eg4electronics.com
  ```
- Live API access required
- Tests restore original state on completion
- Safe to run multiple times (idempotent)

## Test Assertions

### Critical Assertions

1. **DST Detection Accuracy**:
   - `assert station.detect_dst_status() == expected_dst`
   - Must correctly identify DST based on offset comparison

2. **API Synchronization**:
   - `assert station.daylight_saving_time == expected_dst`
   - Station's internal flag must match detected status

3. **API Update Verification**:
   - `assert api_details["daylightSavingTime"] == expected_dst`
   - API's flag must be updated when wrong

4. **No-Op Verification**:
   - `client.api.plants.set_daylight_saving_time.assert_not_called()`
   - No API call when DST is already correct

## Known Edge Cases

### Handled
- Invalid timezone format → Falls back to UTC
- Missing `currentTimezoneWithMinute` → Cannot determine DST (returns None)
- API update failure → Logs warning, keeps old value
- API already correct → Skips update (no-op)

### Not Handled (By Design)
- Timezones without DST (e.g., Arizona, Hawaii) → Algorithm works correctly (difference=0)
- Half-hour offsets (e.g., Newfoundland, India) → Not common for solar installations
- Southern Hemisphere DST → Algorithm works (DST shifts in opposite direction)

## Related Documentation

- **Implementation**: `src/pylxpweb/devices/station.py` (lines 121-230)
- **Date Boundaries**: `docs/SCALING_GUIDE.md` (v2.0.0)
- **API Reference**: `docs/api/LUXPOWER_API.md`

## Future Enhancements

1. **Timezone Library Integration**:
   - Use `pytz` or `zoneinfo` for robust timezone handling
   - Support IANA timezone names (e.g., "America/Los_Angeles")

2. **DST Schedule Validation**:
   - Validate DST transitions match expected schedules
   - Warn on unexpected DST changes

3. **Multi-Station Testing**:
   - Test stations in different timezones simultaneously
   - Verify DST detection across global locations

4. **Performance Metrics**:
   - Track API call reduction from no-op optimization
   - Measure impact on station load time
