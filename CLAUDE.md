# CLAUDE.md - Development Guidelines for pylxpweb

**Last Updated**: 2025-11-20
**Version**: 0.2.1
**Purpose**: Guide Claude Code development in this repository

## Project Overview

**pylxpweb** is a Python client library for Luxpower/EG4 solar inverters and energy storage systems. It provides programmatic access to the Luxpower/EG4 web monitoring API with a focus on type safety, async operations, and Home Assistant integration readiness.

**Key Features**:
- Complete API coverage (authentication, discovery, runtime data, energy stats, control operations)
- Object-oriented device hierarchy (Station → ParallelGroup → Inverter → BatteryBank → Battery)
- 100% feature parity with EG4 Web Monitor HA integration
- Async/await throughout with concurrent operations
- Type-safe with mypy strict mode (Pydantic v2 models)
- Production-ready: 288+ tests, >81% coverage, zero linting errors

**Repository**: `joyfulhouse/pylxpweb`

## Quick Reference

### Device Hierarchy
```
Station (Plant)
├── Parallel Group (0-N) - Multi-inverter configurations
│   ├── MID Device (GridBOSS) - Optional, 0-1 per group
│   └── Inverters (1-N)
│       └── Battery Bank - Aggregate battery data
│           └── Batteries (0-N) - Individual battery modules
└── Standalone Inverters (0-N) - Single inverter setups
```

### Regional API Endpoints
| Region | Base URL | Use For |
|--------|----------|---------|
| US (EG4) | `https://monitor.eg4electronics.com` | EG4-branded devices (default) |
| US (Luxpower) | `https://us.luxpowertek.com` | Luxpower-branded devices (US) |
| EU (Luxpower) | `https://eu.luxpowertek.com` | Luxpower-branded devices (EU) |

### Data Scaling (CRITICAL)
| Type | Scaling | Example |
|------|---------|---------|
| Voltage (Inverter) | ÷100 | 5100 → 51.00V |
| Voltage (Battery Bank) | ÷10 | 539 → 53.9V |
| Voltage (Individual Battery) | ÷100 | 5394 → 53.94V |
| Voltage (Cell) | ÷1000 | 3364 → 3.364V |
| Current | ÷100 | 1500 → 15.00A |
| Frequency | ÷100 | 5998 → 59.98Hz |
| Temperature | Direct | 39 → 39°C |
| Power | Direct | 1030 → 1030W |
| Energy (API) | ÷10 | 184 → 18.4 kWh |

**WARNING**: Note different voltage scaling for battery bank vs individual batteries!

## Development Standards

### Code Quality Requirements
1. **Type Hints**: All functions must have complete type annotations
   - Use `from __future__ import annotations` for forward references
   - mypy strict mode enforced (`mypy src/pylxpweb/ --strict`)

2. **Async/Await**: All I/O operations must be async
   - Use `aiohttp` for HTTP requests
   - Use `asyncio.gather()` for concurrent operations
   - No blocking operations in async code

3. **Error Handling**:
   - Custom exceptions in `src/pylxpweb/exceptions.py`
   - Specific types: `AuthenticationError`, `ConnectionError`, `LuxpowerAPIError`
   - Proper exception hierarchy with contextual error messages

4. **Testing**:
   - Target: >90% code coverage (currently >81%)
   - Use `pytest` with `pytest-asyncio`
   - Mock external API calls in unit tests (`tests/unit/`)
   - Real API tests in `tests/integration/` (requires credentials)

5. **Code Style**:
   - Format: `ruff check --fix && ruff format`
   - Lint: `ruff check src/ tests/`
   - Google-style docstrings for all public APIs

### Pre-Commit Workflow (REQUIRED)
Before any commit, automatically run:
```bash
# 1. Format and lint
ruff check --fix && ruff format

# 2. Type checking
mypy src/pylxpweb/ --strict

# 3. Tests with coverage
pytest tests/unit/ --cov=pylxpweb --cov-report=term-missing

# All checks must pass before committing
```

## API Architecture

### Key Endpoints (Complete List)
**Authentication**:
- `POST /WManage/api/login` - Session duration: ~2 hours

**Discovery**:
- `POST /WManage/web/config/plant/list/viewer` - List stations
- `POST /WManage/api/inverterOverview/getParallelGroupDetails` - Device hierarchy (requires GridBOSS serial)
- `POST /WManage/api/inverterOverview/list` - Flat device list

**Runtime Data**:
- `POST /WManage/api/inverter/getInverterRuntime` - Real-time inverter data
- `POST /WManage/api/inverter/getInverterEnergyInfo` - Energy statistics
- `POST /WManage/api/battery/getBatteryInfo` - Battery bank + `batteryArray` with individual modules
- `POST /WManage/api/midbox/getMidboxRuntime` - GridBOSS data

**Control**:
- `POST /WManage/web/maintain/remoteRead/read` - Read parameters (127 registers max per call)
- `POST /WManage/web/maintain/remoteSet/write` - Write parameters

### API Call Pattern (Per Refresh Cycle)

**Station Discovery** (once per session): 4 calls
- 2x `/WManage/web/config/plant/list/viewer`
- 1x `/WManage/api/inverterOverview/list`
- 1x `/WManage/api/inverterOverview/getParallelGroupDetails` (if GridBOSS present)

**Data Refresh** (every 30 seconds): 3-4 calls per inverter
- 1x `/WManage/api/inverter/getInverterRuntime`
- 1x `/WManage/api/inverter/getInverterEnergyInfo`
- 1x `/WManage/api/battery/getBatteryInfo`
- 1x `/WManage/api/midbox/getMidboxRuntime` (if MID device present)

**Parameter Refresh** (hourly): 3 calls per inverter
- 1x read registers 0-127
- 1x read registers 127-254
- 1x read registers 240-367

**Total API calls for 1 inverter + 1 MID device**:
- Discovery: 4 calls (once)
- Per cycle: 7 calls (4 data + 3 parameters)
- Per hour: ~487 calls (4 + 120×4 + 3)

### Session Management & Error Handling
- **Session**: Cookie-based (`JSESSIONID`), ~2 hour expiration
- **Auto-reauthentication**: Automatic on 401/403 responses
- **Transient Error Retry**: Automatic retry with exponential backoff
  - Errors: `DATAFRAME_TIMEOUT`, `TIMEOUT`, `BUSY`, `DEVICE_BUSY`, `COMMUNICATION_ERROR`
  - Max retries: 3 attempts (configurable via `MAX_TRANSIENT_ERROR_RETRIES`)
  - Backoff: 1s → 2s → 4s → 8s (exponential with jitter, max 60s)
  - Non-transient errors (e.g., `apiBlocked`) fail immediately
- **Session injection**: Supported (Platinum tier requirement)

## Implementation Patterns

### Property-Based API (CRITICAL)

**ALL raw Pydantic models are private** - users must access data via properly-scaled properties:

```python
# ✅ CORRECT: Use properties (automatically scaled)
await inverter.refresh()
voltage = inverter.grid_voltage_r  # Returns 241.8V (÷10 applied)
frequency = inverter.grid_frequency  # Returns 59.98Hz (÷100 applied)
power = inverter.pv_total_power  # Returns 1500W (no scaling)

# ❌ WRONG: Access raw data (private, not scaled)
voltage = inverter._runtime.vacr / 10  # Private attribute, manual scaling
```

**Benefits**:
- **Clear API**: Only ONE way to access data (via properties)
- **Type Safety**: All properties return properly typed values (`float`, `int`, `str`, `bool`)
- **Defensive**: All properties handle `None` gracefully with sensible defaults
- **No Confusion**: Users can't accidentally use wrong scaling factors

**Property Organization**:
- `BaseInverter`: ~40 properties via `InverterRuntimePropertiesMixin` (PV, grid, battery, temps, etc.)
- `MIDDevice`: ~50 properties via `MIDRuntimePropertiesMixin` (grid, UPS, loads, smart ports, etc.)
- `Battery`: ~20 properties (voltage, current, temps, cell data, etc.)
- `BatteryBank`: ~10 properties (aggregate bank data)
- `ParallelGroup`: ~12 properties (today/lifetime energy data)

See [Property Reference](docs/PROPERTY_REFERENCE.md) for complete list.

### Factory Pattern (Device Loading)
```python
# Load all stations
stations = await Station.load_all(client)

# Load specific station
station = await Station.load(client, plant_id=12345)

# Access devices - ALL properties properly scaled
for inverter in station.all_inverters:
    await inverter.refresh()  # Concurrent: runtime + energy + battery

    # Use properties (automatically scaled)
    print(f"PV: {inverter.pv_total_power}W")
    print(f"Battery: {inverter.battery_soc}% @ {inverter.battery_voltage}V")
    print(f"Grid: {inverter.grid_voltage_r}V @ {inverter.grid_frequency}Hz")

    # Access battery bank aggregate data
    if inverter.battery_bank:
        print(f"Capacity: {inverter.battery_bank.max_capacity} Ah")
        print(f"SOC: {inverter.battery_bank.soc}%")

        # Access individual batteries
        for battery in inverter.battery_bank.batteries:
            print(f"Battery {battery.battery_index + 1}:")
            print(f"  Voltage: {battery.voltage}V")  # Properly scaled
            print(f"  Current: {battery.current}A")  # Properly scaled
            print(f"  SOC: {battery.soc}%")
```

### Concurrent Operations
```python
# Station refresh - all devices concurrently
await station.refresh_all_data()

# Inverter refresh - runtime, energy, battery concurrently
await inverter.refresh()

# ParallelGroup refresh - all inverters + MID device + energy concurrently
await group.refresh()
```

## Critical Implementation Notes

### 1. Parallel Group Detection
The `getParallelGroupDetails` endpoint requires a **GridBOSS serial number** (not station ID):
```python
# WRONG: Using station ID
await client.api.devices.get_parallel_group_details(str(station.id))  # ❌ userSnDismatch

# CORRECT: Using GridBOSS serial
gridboss_serial = "4524850115"  # deviceType == 9
await client.api.devices.get_parallel_group_details(gridboss_serial)  # ✅
```

**Graceful Handling**: If no GridBOSS found, devices treated as standalone (no errors).

### 2. Battery Voltage Scaling (CRITICAL!)
Different scaling factors for different battery data:
- **Battery Bank aggregate**: ÷10 (e.g., 539 → 53.9V)
- **Individual Battery**: ÷100 (e.g., 5394 → 53.94V)
- **Cell Voltage**: ÷1000 (e.g., 3364 → 3.364V)

**Rationale**: API returns different precision for aggregate vs individual data.

### 3. BatteryBank Design Decision
- **Purpose**: Represents aggregate battery system data (total capacity, charge/discharge power, overall SOC)
- **Data Source**: Created from `getBatteryInfo` response header
- **Structure**: Contains `batteries[]` list of individual Battery objects
- **Home Assistant**: Entities not currently generated (aggregate data available via inverter sensors)
- **Properties**: `status`, `soc`, `voltage`, `charge_power`, `discharge_power`, `max_capacity`, `current_capacity`, `battery_count`

### 4. GridBOSS/MID Devices
- Device type: `deviceType == 9`
- Use separate endpoint: `getMidboxRuntime` (not `getInverterRuntime`)
- Assigned to `parallel_group.mid_device` property
- Standard inverter endpoints return no data for GridBOSS

### 5. Parameter Reading
API limit: **127 registers per call**. For full parameter range, make 3 calls:
```python
# Standard 3-range approach (per HA integration)
params1 = await inverter.read_parameters(0, 127)    # Base parameters
params2 = await inverter.read_parameters(127, 127)  # Extended 1
params3 = await inverter.read_parameters(240, 127)  # Extended 2
```

## Testing Strategy

### Test Organization
```
tests/
├── unit/ (288 tests)
│   ├── endpoints/ - API endpoint tests
│   ├── devices/ - Device hierarchy tests
│   │   ├── inverters/ - BaseInverter, GenericInverter, HybridInverter
│   │   ├── batteries/ - Battery class
│   │   ├── mid/ - MIDDevice
│   │   ├── test_battery_bank.py - BatteryBank (13 tests)
│   │   └── test_station.py, test_parallel_group.py
│   └── samples/ - Real API responses (committed)
└── integration/ - Live API tests (requires credentials in .env)
```

### Sample Data Strategy
- Real API samples copied from `research/` directory to `tests/unit/*/samples/`
- Samples committed (not gitignored)
- Pydantic model validation ensures correctness
- **CRITICAL**: Do not reference `research/` in production code

### Integration Test Credentials
```bash
# .env file (gitignored)
LUXPOWER_USERNAME=your_username
LUXPOWER_PASSWORD=your_password
LUXPOWER_BASE_URL=https://monitor.eg4electronics.com

# Run integration tests
pytest tests/integration/ -v -m integration
```

### Test Fixtures (Pydantic Models)
Use `model_construct()` to bypass validation for test data:
```python
# Correct approach for test fixtures
device = InverterOverviewItem.model_construct(
    serialNum="1234567890",
    statusText="Online",
    deviceType=6,
    # ... all required fields
)
```

## Research Materials (REFERENCE ONLY)

The `research/` directory contains reference materials and should **NEVER** be:
- Included in test execution or discovery
- Referenced by production code imports
- Included in documentation generation
- Included in package building/distribution

**Proper Usage**:
- Copy sample data to `tests/unit/*/samples/` for fixtures
- Reference for understanding API behavior
- Compare implementation approaches

## Package Structure

```
pylxpweb/
├── docs/                   # Project documentation
│   ├── api/                # API endpoint documentation
│   ├── claude/             # Claude Code session notes (gitignored)
│   └── inverters/          # Device-specific documentation
├── src/pylxpweb/           # Main package
│   ├── __init__.py
│   ├── client.py           # LuxpowerClient
│   ├── endpoints/          # API endpoints (plants, devices, control)
│   ├── devices/            # Device hierarchy
│   │   ├── station.py      # Station (top-level)
│   │   ├── parallel_group.py  # ParallelGroup
│   │   ├── battery_bank.py    # BatteryBank (aggregate)
│   │   ├── battery.py         # Battery (individual)
│   │   ├── mid_device.py      # MIDDevice (GridBOSS)
│   │   └── inverters/         # BaseInverter, GenericInverter, HybridInverter
│   ├── models.py           # Pydantic data models
│   ├── constants.py        # Constants and register definitions
│   └── exceptions.py       # Custom exceptions
├── tests/                  # Test suite (288+ tests)
│   ├── unit/               # Unit tests (mock API)
│   └── integration/        # Integration tests (live API)
├── research/               # REFERENCE ONLY (not in package)
└── pyproject.toml          # Package config (uv-based)
```

## CI/CD Pipeline

### GitHub Actions Workflows

**CI Workflow** (`.github/workflows/ci.yml`):
- Triggers: Push to main/master, PRs, manual dispatch
- Jobs: Lint & Type Check (parallel), Unit Tests (parallel) → Integration Tests → CI Success
- Python: 3.13 via `uv python install 3.13`
- Integration tests skip for Dependabot PRs (no secret access)

**Publish Workflow** (`.github/workflows/publish.yml`):
- Triggers: GitHub releases (`published`), manual dispatch
- Flow: Lint → Test → Integration → Build → TestPyPI → PyPI
- OIDC authentication (no API tokens required)
- Trusted publishers configured on PyPI/TestPyPI

**Dependabot** (`.github/dependabot.yml`):
- GitHub Actions: Weekly updates (Mondays), max 5 PRs
- Python (uv): Weekly updates (Mondays), max 10 PRs
- Groups: `development-dependencies` and `production-dependencies`

### GitHub Secrets Required
- `LUXPOWER_USERNAME` - API username for integration tests
- `LUXPOWER_PASSWORD` - API password
- `LUXPOWER_BASE_URL` - API base URL

## Current Implementation Status (v0.2.2)

### Completed Features ✅
- **API Coverage**: Complete endpoint coverage (auth, discovery, runtime, control)
- **Device Hierarchy**: Station, ParallelGroup, Inverter, BatteryBank, Battery, MIDDevice
- **Property-Based API**: ALL raw data private, ~150+ properly-scaled properties across all device types
- **Parallel Groups**: Proper detection using GridBOSS serial number + aggregate energy data
- **BatteryBank**: Aggregate battery data with individual battery array
- **Control Operations**: Read/write parameters, control functions
- **Concurrent Operations**: Station, Inverter, ParallelGroup refresh
- **Type Safety**: mypy strict mode, Pydantic v2 models
- **Test Coverage**: 479 tests, >85% coverage
- **Documentation**: Comprehensive usage guide, property reference, examples

### Recent Changes (2025-11-21)
**Major API Refactoring**:
- Made ALL raw Pydantic models private (`_runtime`, `_energy`, etc.)
- Added ~40 properties to `BaseInverter` via `InverterRuntimePropertiesMixin`
- Added ~50 properties to `MIDDevice` via `MIDRuntimePropertiesMixin`
- Added ~12 energy properties to `ParallelGroup` (today/lifetime energy data)
- Updated all 479 tests to use private attributes
- Created comprehensive documentation (USAGE_GUIDE.md, PROPERTY_REFERENCE.md)
- Updated README with property-based examples
- Zero linting/type errors, all tests passing

**Benefits**:
- Clear API: Only ONE way to access data (via properties)
- No manual scaling required
- Type-safe with graceful None handling
- Eliminated confusion about which properties to use

### Known Limitations
- **Low-Level API**: Direct API access still returns raw scaled integers (use device objects instead)
- **Parallel Groups**: May not be detected if no GridBOSS present (graceful degradation)
- **Parameter Ranges**: Requires 3 separate API calls (127 register limit per call)

## Inter-Session Context

### Current Branch
- `feature/0.2-object-hierarchy`
- Status: ✅ Ready for merge (all tests passing, zero errors)

### Design Decisions & Rationale
1. **Property-Based API**: ALL raw Pydantic models private, users access via properties only. Eliminates scaling confusion, provides type safety, graceful None handling.
2. **Mixin Pattern**: Properties organized in separate mixin files (`InverterRuntimePropertiesMixin`, `MIDRuntimePropertiesMixin`) to keep code maintainable.
3. **BatteryBank as separate class**: Represents aggregate data from `getBatteryInfo` header, distinct from individual battery modules in `batteryArray`
4. **No BatteryBank HA entities**: Aggregate data accessible via inverter sensors, avoids excessive entity count
5. **Parallel Group detection**: Requires GridBOSS serial (deviceType == 9), graceful fallback if not found
6. **Voltage scaling differences**: API uses different precision for aggregate (÷10) vs individual (÷100) battery data - properties handle this automatically
7. **Session injection**: Supported for HA Platinum tier compliance

### Important Commands
```bash
# Development
uv sync --all-extras --dev
uv run pytest tests/unit/
uv run mypy src/pylxpweb/ --strict
uv run ruff check --fix && uv run ruff format

# Integration tests (requires .env)
uv run pytest tests/integration/ -v -m integration

# Coverage
uv run pytest tests/unit/ --cov=pylxpweb --cov-report=term-missing

# Package building
uv build
uv run twine check dist/*
```

## Documentation Requirements

### API Documentation
Keep `docs/api/LUXPOWER_API.md` updated with:
- New endpoint discoveries
- Request/response schemas
- Data scaling reference
- Error codes and handling
- Example requests/responses

### Session Notes
Store Claude Code session documentation in `docs/claude/` (gitignored):
- Implementation summaries
- Analysis reports
- Session histories
- Optimization recommendations

### Code Documentation
- Google-style docstrings for all public APIs
- Inline comments for complex logic
- Type hints throughout (enforced by mypy strict)

## Release Process

1. Update version in `src/pylxpweb/__init__.py` and `pyproject.toml`
2. Update `CHANGELOG.md` with version notes
3. Ensure all tests pass (`pytest tests/unit/`)
4. Ensure all quality checks pass (mypy, ruff)
5. Create GitHub release (triggers publish workflow)
6. Workflow: Build → TestPyPI → PyPI (OIDC authentication)

## Security & Privacy

### Sensitive Information Policy

**CRITICAL**: Never commit sensitive information to the repository unless it's in `.gitignore`.

**Prohibited in committed files**:
- Real street addresses or physical locations
- Actual serial numbers (use placeholder values like "1234567890", "0000000000")
- Passwords or credentials
- API keys or tokens
- Personal identifiable information (PII)

**Safe Practices**:
- Use `.env` file for credentials (gitignored)
- Use placeholder serial numbers in documentation
- Redact addresses in sample API responses (use "123 Example St" or similar)
- Use fake plant names (e.g., "Test Station", "Demo Plant")
- Sanitize all examples and test fixtures before committing

**Example - Safe Documentation**:
```python
# ✅ CORRECT: Placeholder values
serial_number = "1234567890"
plant_name = "Example Station"
location = "123 Main St, Anytown, USA"

# ❌ WRONG: Real values
serial_number = "4512670118"  # Actual device
plant_name = "6245 N WILLARD"  # Real address
```

**Before committing**:
1. Review all changes for sensitive data
2. Check documentation examples
3. Verify test fixtures are sanitized
4. Ensure `.env` and secrets are gitignored

## Best Practices

### When Adding New Features
1. Start with API endpoint discovery/testing
2. Add Pydantic model for response data
3. Implement endpoint method with type hints
4. Add comprehensive unit tests
5. Add integration test (if applicable)
6. Update documentation
7. Run full quality checks before commit

### When Fixing Bugs
1. Write failing test reproducing bug
2. Implement fix
3. Verify test now passes
4. Add regression test if needed
5. Update documentation if behavior changes

### When Reviewing Code
1. Check type hints completeness
2. Verify async/await usage
3. Confirm error handling
4. Review test coverage
5. Validate documentation updates

---

**Remember**: This is a standalone library usable beyond Home Assistant. Keep HA-specific features (entity platforms, config flow, data coordinators) in the HA integration, not in pylxpweb.
