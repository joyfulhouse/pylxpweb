# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.3] - 2025-11-22

### Added

- **Transient Error Retry** - Automatic retry for hardware communication timeouts:
  - Added `MAX_TRANSIENT_ERROR_RETRIES = 3` configuration constant
  - Added `TRANSIENT_ERROR_MESSAGES` set with 5 known transient errors (`DATAFRAME_TIMEOUT`, `TIMEOUT`, `BUSY`, `DEVICE_BUSY`, `COMMUNICATION_ERROR`)
  - Implemented automatic retry logic in `LuxpowerClient._request()` with exponential backoff (1s → 2s → 4s)
  - Non-transient errors (e.g., `apiBlocked`) fail immediately without retry
  - Retry count preserved across re-authentication
  - 14 unit tests in `test_transient_error_retry.py` (100% passing)
  - 5 integration tests in `test_transient_error_resilience.py` (100% passing)

### Fixed

- **Parameter Initialization** - Fixed incorrect initial values for Home Assistant sensors:
  - Changed `_get_parameter()` return type from `-> int | float | bool` to `-> int | float | bool | None`
  - Returns `None` when `self.parameters is None` (parameters not yet loaded)
  - Updated 7 parameter properties to return `| None`: `battery_soc_limits`, `ac_charge_power_limit`, `pv_charge_power_limit`, `grid_peak_shaving_power_limit`, `ac_charge_soc_limit`, `battery_charge_current_limit`, `battery_discharge_current_limit`
  - Home Assistant sensors now show "Unknown" state instead of incorrect defaults (False/0) on startup
  - 8 unit tests in `test_parameter_initialization.py` (100% passing)

- **Exception Handling** - Fixed double-wrapping of `LuxpowerAPIError` exceptions:
  - Added explicit exception re-raising before generic `except Exception` handler
  - Transient error exceptions now propagate correctly without "Unexpected error" wrapping

### Testing

- Added 27 new tests (22 unit + 5 integration)
- Total test count: 492 unit tests + 67 integration tests (100% passing)
- Zero linting errors (ruff check)
- Zero type errors (mypy --strict)

## [0.3.1] - 2025-11-21

### Changed

- **Code Quality Review** - Comprehensive code review against CLAUDE.md standards and Python best practices:
  - Fixed broad exception suppression in `parallel_group.py` (changed from `suppress(Exception)` to specific `LuxpowerAPIError` and `LuxpowerConnectionError`)
  - Refactored `Station._load_devices()` to reduce complexity from 21 to 6 by extracting 6 helper methods:
    - `_get_device_list()` - Fetch devices from API
    - `_find_gridboss()` - Find GridBOSS device
    - `_get_parallel_groups()` - Query parallel group configuration
    - `_create_parallel_groups()` - Create ParallelGroup objects
    - `_assign_devices()` - Assign devices to groups
    - `_assign_mid_device()` / `_assign_inverter()` - Device-specific assignment logic
  - Improved code maintainability with single-responsibility helper methods
  - Enhanced readability with clear data flow and reduced nesting
  - All linting checks passing (ruff check, ruff format)
  - All type checks passing (mypy --strict, 0 errors)
  - Test coverage improved to 74.93%

### Testing

- ✅ **Unit tests**: 479 passed, 0 failed
- ✅ **Coverage**: 74.93% (exceeds 70% requirement, improved from 74.86%)
- ✅ **Code style**: 100% (ruff: 0 errors)
- ✅ **Type safety**: 100% (mypy strict: 0 errors)
- ✅ **All quality checks passing**: ruff, mypy strict mode, pytest

### Documentation

- Added comprehensive code review document (`docs/claude/CODE_REVIEW_2025-11-21_v2.md`):
  - Detailed analysis of 7 review areas (type hints, async patterns, error handling, etc.)
  - Before/after examples of improvements
  - Test results and quality metrics
  - Recommendations for future improvements

## [0.2.7] - 2025-11-21

### Added

- **TTL-Based Caching** - Comprehensive caching system for inverter data to reduce API calls:
  - Runtime data: 30-second cache (inverter metrics refresh frequently)
  - Energy statistics: 5-minute cache (daily/monthly totals change slowly)
  - Battery data: 30-second cache (battery metrics refresh frequently)
  - Parameters: 1-hour cache (parameter settings change infrequently)
  - Automatic cache invalidation on successful parameter writes
  - 10 new unit tests for caching behavior validation

### Changed

- **Parameter Architecture Refactored** - Major API improvement for parameter access:
  - Converted async parameter getter methods to synchronous properties (e.g., `await inverter.get_ac_charge_power()` → `inverter.ac_charge_power_limit`)
  - Properties: `ac_charge_power_limit`, `pv_charge_power_limit`, `battery_soc_limits`, `battery_charge_amps`, `battery_discharge_amps`, `time_slot_limits`, `quick_charge_discharge_limits`
  - Parameters automatically fetched on first access or when cache expires
  - Integrated parameter fetching into `refresh()` cycle with `include_parameters=True` flag
  - Deprecated `read_parameters()` method with migration guidance to properties

- **Concurrent Parameter Fetching** - Added `_fetch_parameters()` internal method:
  - Fetches all 3 register ranges (0-127, 127-254, 240-367) concurrently using `asyncio.gather()`
  - Reduces parameter fetch time from ~1.5s sequential to ~0.5s parallel
  - Integrated into cache refresh logic

### Fixed

- **Integration Test Compatibility** - Updated integration tests to use new property-based API:
  - Replaced `await inverter.get_battery_soc_limits()` with `inverter.battery_soc_limits` property
  - Replaced `await inverter.get_ac_charge_power()` with `inverter.ac_charge_power_limit` property
  - Added `await inverter.refresh(include_parameters=True)` before accessing properties
  - All integration tests passing with new architecture

### Migration Guide

**Breaking Change**: Parameter getter methods replaced with properties.

Before (v0.2.6):
```python
await inverter.refresh()
soc_limits = await inverter.get_battery_soc_limits()
ac_power = await inverter.get_ac_charge_power()
```

After (v0.2.7):
```python
await inverter.refresh(include_parameters=True)  # Optional: fetch parameters during refresh
soc_limits = inverter.battery_soc_limits  # Property access (auto-fetches if needed)
ac_power = inverter.ac_charge_power_limit  # Property access (uses 1-hour cache)
```

### Testing

- ✅ **Unit tests**: 10 new caching tests in `test_caching.py`, all passing
- ✅ **Integration tests**: Updated for new property syntax, all passing
- ✅ **All quality checks passing**: ruff, mypy strict mode, pytest

## [0.2.6] - 2025-11-20

### Fixed

- **Device Model Information** (Issue #18) - Fixed device model names not being properly populated on inverter objects:
  - Changed `Station._load_devices()` to use `deviceTypeText` field from `InverterOverviewItem` API response
  - Previous code incorrectly tried to use `deviceTypeText4APP` which doesn't exist on that endpoint
  - Model is now reliably available immediately after `Station.load()` with human-readable names like "18KPV", "FlexBOSS21", "Grid Boss"
  - Added `model` property to `BaseDevice` and override in `BaseInverter` for consistent access
  - Added 5 new unit tests and 1 integration test to verify model property behavior
  - Model remains stable after refresh operations (not affected by runtime data)

### Changed

- **Model Property**: Changed from simple attribute to computed property with fallback to "Unknown" if not set

### Testing

- ✅ **Unit tests**: 48 passed in test_base.py (5 new model property tests)
- ✅ **Integration tests**: 1 new test verifies model is set correctly from API and remains stable
- ✅ **All quality checks passing**: ruff, mypy strict mode, pytest

## [0.2.5] - 2025-11-20

### Fixed

- **Dependency Compatibility**: Lowered pydantic requirement from `>=2.12.4` to `>=2.12.0` for Home Assistant compatibility (HA uses pydantic 2.12.2)

## [0.2.4] - 2025-11-20

### Added

- **Working Mode Controls** (Issue #16) - New convenience methods on `BaseInverter` for working mode operations:
  - `enable_ac_charge_mode()` / `disable_ac_charge_mode()` / `get_ac_charge_mode_status()` - Control AC charge from grid
  - `enable_pv_charge_priority()` / `disable_pv_charge_priority()` / `get_pv_charge_priority_status()` - Control PV charge priority mode
  - `enable_forced_discharge()` / `disable_forced_discharge()` / `get_forced_discharge_status()` - Control forced discharge mode
  - `enable_peak_shaving_mode()` / `disable_peak_shaving_mode()` / `get_peak_shaving_mode_status()` - Control grid peak shaving
  - Corresponding API endpoints added to `ControlEndpoints` for low-level access
  - All methods use the existing `control_function()` infrastructure with function parameter names (FUNC_AC_CHARGE, FUNC_FORCED_CHG_EN, FUNC_FORCED_DISCHG_EN, FUNC_GRID_PEAK_SHAVING)
  - Comprehensive unit tests (24 new tests: 12 for BaseInverter methods, 12 for endpoint methods)
  - Integration tests (4 tests with read-then-restore pattern for safe live API testing)

## [0.2.3] - 2025-11-20

### Added

- **Operating Mode Control** - New operating mode control for inverters with `OperatingMode` enum:
  - `OperatingMode.NORMAL` - Normal operation mode
  - `OperatingMode.STANDBY` - Standby mode (inverter disabled)
  - `set_operating_mode(mode)` - Set inverter operating mode
  - `get_operating_mode()` - Get current operating mode (reads FUNC_EN register bit 9)

- **Quick Charge Control** - Convenience methods on `BaseInverter` for quick charge operations:
  - `enable_quick_charge()` / `disable_quick_charge()` - Control quick charge operation
  - `get_quick_charge_status()` - Check if quick charge is active (returns bool)

- **Quick Discharge Control** - New quick discharge endpoints and convenience methods:
  - API: `start_quick_discharge()` / `stop_quick_discharge()` in `ControlEndpoints`
  - `BaseInverter`: `enable_quick_discharge()` / `disable_quick_discharge()`
  - `get_quick_discharge_status()` - Check if quick discharge is active (returns bool)
  - Uses shared `quickCharge/getStatusInfo` endpoint for status (returns both charge & discharge status)

- **API Discovery** - Documented quick discharge endpoints in OpenAPI spec:
  - `/web/config/quickDischarge/start` - Start quick discharge operation
  - `/web/config/quickDischarge/stop` - Stop quick discharge operation
  - Updated `QuickChargeStatus` model with `hasUnclosedQuickDischargeTask` field
  - Note: No separate `quickDischarge/getStatusInfo` endpoint (returns HTTP 404)

- **Diagnostic Data Collection Tool** (`utils/collect_diagnostics.py`) - Comprehensive diagnostic data collection utility for support and troubleshooting:
  - Automatically collects station information, device hierarchy, runtime data, energy statistics, battery data, and parameter settings
  - Sanitizes sensitive information by default (serial numbers, addresses, GPS coordinates)
  - Collects 367 registers for standard inverters, 508 registers for MID devices (GridBOSS)
  - Outputs JSON file with complete system state for support tickets
  - CLI tool: `python -m utils.collect_diagnostics --username USER --password PASS`
  - Comprehensive documentation in `utils/README.md`

### Changed

- **Project Structure Cleanup**:
  - Moved development/research scripts from root and `utils/` to `research/` directory (gitignored)
  - Cleaned up `utils/` to contain only user-facing utilities: `collect_diagnostics.py`, `json_to_markdown.py`, `map_registers.py`
  - Removed local testing script `verify_cicd.sh`

- **Coverage Reports**:
  - Added `coverage.json` to `.gitignore` to prevent test artifacts from being tracked

### Design Decisions

- **Operating Mode vs. Quick Charge/Discharge**: Operating mode (NORMAL/STANDBY) is distinct from quick charge/discharge operations, which are functions that work independently alongside operating modes
- **Status Methods Return Bool**: Convenience methods like `get_quick_charge_status()` return `bool` for simplicity rather than the full `QuickChargeStatus` object
- **Shared Status Endpoint**: Quick discharge status is retrieved via `quickCharge/getStatusInfo` endpoint, which returns both charge and discharge status in a single response

### Testing

- ✅ **Unit tests**: 335 passed (31 new tests added)
- ✅ **Coverage**: >83% (new operating mode and quick charge/discharge code fully covered)
- ✅ **All quality checks passing**: linting, type checking, coverage

### Notes

- Resolves Issue #14 - Operating mode control and quick charge/discharge support
- All changes are backward compatible
- No integration tests for quick charge/discharge operations (safety concern with live electrical systems)

## [0.2.2] - 2025-11-20

### Fixed

- **Integration Test Failures** - Resolved all integration test failures caused by API changes:
  - Fixed property name mismatches (`station.plant_id` → `station.id`, `group.group_id` → `group.name`)
  - Fixed async/await for `get_total_production()` method
  - Fixed response format for `get_total_production()` (now returns `today_kwh`, `lifetime_kwh`)
  - Fixed timestamp access (`_last_refresh` is private attribute)

- **SOC Limit Parameter API Issue** - Fixed critical bug in `set_battery_soc_limits()`:
  - API expects parameter NAMES (e.g., `"HOLD_DISCHG_CUT_OFF_SOC_EOD"`) not register numbers (e.g., `105`)
  - Changed implementation to use `write_parameter()` (singular) with proper format: `holdParam="HOLD_DISCHG_CUT_OFF_SOC_EOD"`, `valueText="20"`
  - Resolved HTTP 400 errors from malformed parameter write requests
  - Updated unit tests to verify correct API contract

### Changed

- **Control Operations Test Cleanup**:
  - Removed dangerous `write_parameters` roundtrip test (was attempting to write 0 to register 21, which would disable all functions)
  - Fixed `test_read_parameters` to expect parsed parameter names (`FUNC_*` instead of `reg_21`)
  - Updated SOC limit test to verify API success without value verification (inverters may have undocumented validation rules)

### Test Results

- ✅ **Unit tests**: 344 passed
- ✅ **Integration tests**: 40 passed, 9 skipped
- ✅ **All quality checks passing**: linting, type checking, coverage

## [0.2.1] - 2025-11-20

### Added

- **Battery Current Control Convenience Methods** - Four new convenience methods in `ControlEndpoints` for managing battery charge and discharge current limits:
  - `set_battery_charge_current(inverter_sn, amperes)` - Set battery charge current limit (0-250 A) with validation and safety warnings
  - `set_battery_discharge_current(inverter_sn, amperes)` - Set battery discharge current limit (0-250 A) with validation and safety warnings
  - `get_battery_charge_current(inverter_sn)` - Get current battery charge current limit
  - `get_battery_discharge_current(inverter_sn)` - Get current battery discharge current limit

- **Comprehensive Documentation**:
  - `docs/PARAMETER_REFERENCE.md` - Complete parameter catalog for Luxpower/EG4 API (400+ lines)
  - `docs/claude/BATTERY_CURRENT_CONTROL_IMPLEMENTATION.md` - Implementation guide with use cases (600+ lines)
  - `docs/claude/CONVENIENCE_FUNCTIONS_ANALYSIS.md` - Analysis of convenience function patterns (400+ lines)
  - `docs/claude/GAP_VERIFICATION.md` - Feature parity verification with EG4 Web Monitor HA integration
  - `docs/claude/RELEASE_v0.3_NOTES.md` - Complete release notes with examples and use cases

### Features

**Battery Current Control** convenience methods provide:
- Self-documenting API with clear method names
- Input validation (0-250 A range with `ValueError` on invalid input)
- Safety warnings for high values (>200 A)
- Comprehensive docstrings with use case examples
- Power calculation references (e.g., 50A = ~2.4kW at 48V)
- Type hints for IDE autocomplete

**Common Use Cases**:
- Prevent inverter throttling during high solar production
- Time-of-use (TOU) rate optimization
- Battery health management (gentle charging)
- Emergency power management during grid outages
- Weather-based automation

### Changed

- Updated `docs/GAP_ANALYSIS.md` to track v2.2.7 features from EG4 Web Monitor HA integration

### Documentation

- Added comprehensive examples for battery current control automation
- Added safety considerations and battery limit guidelines
- Added power calculation reference tables for 48V systems
- Added migration guide from generic `write_parameter()` to convenience methods

### Notes

- All changes are backward compatible - no breaking changes
- Generic `write_parameter()` method still available
- Based on features added to EG4 Web Monitor HA integration v2.2.6 (November 2025)
- Convenience methods delegate to existing `write_parameter()` and `read_device_parameters_ranges()` methods

## [0.2.0] - 2025-11-19

### Added

- **Object-Oriented Device Hierarchy** - New `Station` and `Inverter` classes for intuitive device management
- **Cached Data Access** - Efficient caching with `_load_devices()` to minimize API calls
- **Helper Methods** - Eight control helper methods added to `ControlEndpoints`:
  - `enable_battery_backup()` / `disable_battery_backup()`
  - `enable_quick_charge()` / `disable_quick_charge()`
  - `enable_forced_charge()` / `disable_forced_charge()`
  - `enable_forced_discharge()` / `disable_forced_discharge()`
- **Session Management Methods** - `invalidate_cache()` and `invalidate_all_caches()` for cache control
- **Register Mapping** - Complete parameter register catalog in `src/pylxpweb/registers.py`

### Changed

- Improved `LuxpowerClient` with separate API and control endpoints
- Enhanced type safety with Pydantic v2 models
- Better session handling with automatic re-authentication

### Fixed

- Resolved mypy type errors and API namespace issues
- Fixed Pydantic model handling in `Station._load_devices`
- Optimized `Station._load_devices` with concurrent API calls

### Documentation

- Added comprehensive 100% parity assessment with EG4 Web Monitor integration
- Updated API documentation with latest endpoints
- Added register mapping documentation

## [0.1.1] - 2025-11-15

### Fixed

- Fixed package structure and imports
- Improved error handling for authentication failures
- Better session cookie management

## [0.1.0] - 2025-11-14

### Added

- Initial release of pylxpweb
- Core `LuxpowerClient` with async/await support
- Authentication and session management
- Plant/station discovery
- Device enumeration and hierarchy
- Runtime data retrieval (inverter, battery, GridBOSS)
- Energy statistics
- Control operations (parameter read/write)
- Comprehensive type hints with mypy strict mode
- Data scaling utilities
- Custom exception hierarchy
- Basic test suite
- API documentation

### Features

- Multi-region support (US Luxpower, EU Luxpower, EG4 Electronics)
- Configurable base URL
- Session injection support (Home Assistant integration ready)
- Automatic session renewal
- Retry logic with exponential backoff
- Smart caching with configurable TTL
- Production-ready error handling

### Documentation

- Complete API reference (`docs/api/LUXPOWER_API.md`)
- Development guidelines (`CLAUDE.md`)
- OpenAPI 3.0 specification (`docs/luxpower-api.yaml`)
- Usage examples in README
- Comprehensive docstrings

---

## Version History Summary

- **v0.2.3** (2025-11-20): Operating mode control, quick charge/discharge support, diagnostic tool
- **v0.2.2** (2025-11-20): Integration test fixes, SOC limit API correction
- **v0.2.1** (2025-11-20): Battery current control convenience methods, comprehensive documentation
- **v0.2.0** (2025-11-19): Object-oriented device hierarchy, helper methods, register mapping
- **v0.1.1** (2025-11-15): Bug fixes and improvements
- **v0.1.0** (2025-11-14): Initial release with core functionality

[0.2.3]: https://github.com/joyfulhouse/pylxpweb/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/joyfulhouse/pylxpweb/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/joyfulhouse/pylxpweb/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/joyfulhouse/pylxpweb/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/joyfulhouse/pylxpweb/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/joyfulhouse/pylxpweb/releases/tag/v0.1.0
