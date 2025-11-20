# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**pylxpweb** is a Python client library for Luxpower/EG4 inverters and solar equipment, enabling programmatic access to the web monitoring API at `https://monitor.eg4electronics.com`.

This project is based on extensive research from:
- **EG4 Web Monitor Home Assistant Integration** (`research/eg4_web_monitor/`) - Production-quality reference implementation
- **EG4 Inverter HA Integration** (`research/eg4_inverter_ha/`) - Earlier implementation for comparison

**CRITICAL**: The `research/` directory contains **REFERENCE MATERIALS ONLY** and should **NEVER** be included in:
- Test execution or test discovery
- Code evaluation or linting
- Documentation generation
- Package building or distribution
- Any production code imports

The research materials are for understanding existing implementations and API behavior only.

## Project Goals

1. Create a standalone Python library (`pylxpweb`) for Luxpower/EG4 API access
2. Document the complete Luxpower API based on `monitor.eg4electronics.com` endpoints
3. Provide comprehensive documentation in `docs/` directory
4. Enable integration with Home Assistant and other automation platforms

## Repository Structure

```
pylxpweb/
├── docs/                        # Project documentation (PRIORITY 1)
│   ├── api/                     # API endpoint documentation
│   │   └── LUXPOWER_API.md     # Complete API reference (to be created)
│   ├── architecture/            # System design documentation
│   └── examples/                # Usage examples
│
├── research/                    # RESEARCH ONLY - DO NOT USE IN PRODUCTION
│   ├── *.py                     # Research/testing scripts (test_endpoints.py, etc.)
│   ├── eg4_web_monitor/         # Complete HA integration (primary reference)
│   │   ├── custom_components/   # Production integration code
│   │   │   └── eg4_web_monitor/
│   │   │       ├── eg4_inverter_api/  # API client implementation
│   │   │       │   ├── client.py       # Reference API client
│   │   │       │   └── samples/        # Sample API responses
│   │   │       ├── coordinator.py      # Data coordinator pattern
│   │   │       ├── sensor.py           # Sensor implementations
│   │   │       ├── switch.py           # Switch entities
│   │   │       ├── number.py           # Number entities (SOC limits, power)
│   │   │       ├── select.py           # Select entities (operating mode)
│   │   │       └── button.py           # Button entities (refresh)
│   │   └── tests/               # Comprehensive test suite
│   ├── eg4_inverter_ha/         # Earlier HA implementation
│   └── com.thermacell.liv/      # Unrelated project (ignore)
│
├── pylxpweb/                    # Main Python package (to be created)
│   ├── __init__.py
│   ├── client.py                # API client class
│   ├── auth.py                  # Authentication handler
│   ├── devices.py               # Device management
│   ├── models.py                # Data models
│   └── exceptions.py            # Custom exceptions
│
└── tests/                       # Test suite (to be created)
    ├── unit/                    # Unit tests
    └── integration/             # Integration tests
```

## API Architecture

### Base Configuration
- **Base URLs**: Multiple regional endpoints available
  - `https://us.luxpowertek.com` - US region (Luxpower)
  - `https://eu.luxpowertek.com` - EU region (Luxpower)
  - `https://monitor.eg4electronics.com` - US region (EG4 Electronics)
  - Additional regional endpoints may exist
- **Authentication**: `/WManage/api/login` (POST)
- **Session Management**: Cookie-based with 2-hour expiration
- **Protocol**: HTTPS REST API with JSON payloads
- **Default**: Use `https://monitor.eg4electronics.com` for EG4 devices in North America

### Key API Endpoints

From the research materials, the following endpoints are validated:

**Authentication**:
- `POST /WManage/api/login` - Authenticate and establish session
  - Request: `{"account": str, "password": str}`
  - Response: Sets `JSESSIONID` cookie
  - Session duration: ~2 hours

**Station/Plant Discovery**:
- `POST /WManage/web/config/plant/list/viewer` - List available stations
  - Returns: Array of plant objects with `plantId`, `name`, location info
  - Example response in `research/eg4_web_monitor/custom_components/eg4_web_monitor/eg4_inverter_api/samples/plants.json`

**Device Discovery**:
- `POST /WManage/api/inverterOverview/getParallelGroupDetails` - Get device hierarchy
  - Request: `{"plantId": int}`
  - Returns: Parallel groups, inverters, GridBOSS devices

- `POST /WManage/api/inverterOverview/list` - List all devices in station
  - Request: `{"plantId": int}`
  - Returns: Device list with serial numbers, models, status

**Runtime Data**:
- `POST /WManage/api/inverter/getInverterRuntime` - Inverter real-time data
  - Request: `{"serialNum": str}`
  - Returns: Power, voltage, current, temperature, frequency, SOC
  - Example: `research/.../samples/runtime_*.json`
  - **Data Scaling**: Values are scaled (e.g., 5100 = 51.00V, divide by 100)

- `POST /WManage/api/inverter/getInverterEnergyInfo` - Energy statistics
  - Request: `{"serialNum": str}`
  - Returns: Daily, monthly, lifetime energy production

- `POST /WManage/api/battery/getBatteryInfo` - Battery information
  - Request: `{"serialNum": str}`
  - Returns: Battery status + `batteryArray` with individual batteries
  - Each battery has `batteryKey` for unique identification

- `POST /WManage/api/midbox/getMidboxRuntime` - GridBOSS/MID device data
  - Request: `{"serialNum": str}`
  - Returns: Grid management, load, smart ports, generator status

**Control Endpoints**:
- `POST /WManage/web/maintain/inverter/param/read` - Read parameters
  - Request: `{"serialNum": str, "paramIds": [int]}`
  - Returns: Current parameter values

- `POST /WManage/web/maintain/inverter/param/write` - Write parameters
  - Request: `{"serialNum": str, "data": {paramId: value}}`
  - Controls: Quick charge, EPS mode, SOC limits, operating mode

### Device Hierarchy

```
Station/Plant (plantId)
└── Parallel Group
    ├── MID Device (GridBOSS) - Optional, 0 or 1
    └── Inverters (1 to N)
        └── Batteries (0 to N) - Individual battery modules
```

### Device Types

**Standard Inverters** (FlexBOSS21, FlexBOSS18, 18KPV, 12KPV, XP):
- Runtime data: power, voltage, current, temperature
- Energy data: daily, monthly, lifetime production
- Battery data: SOC, charge/discharge power
- Control: Quick charge, EPS mode, SOC limits

**GridBOSS/MID Devices**:
- Grid management and interconnection
- Smart load ports (configurable outputs)
- AC coupling support
- Generator monitoring
- UPS functionality

**Individual Batteries**:
- Accessed via `batteryArray` in battery info response
- Unique `batteryKey` for identification
- Metrics: Voltage, current, SOC, SoH, temperature, cycles
- Cell voltage monitoring and delta calculation

### Data Scaling

The API returns scaled integer values that must be divided to get actual values:

- **Voltage**: Divide by 100 (e.g., 5100 → 51.00V)
- **Current**: Divide by 100 (e.g., 1500 → 15.00A)
- **Power**: Already in watts (e.g., 1030 → 1030W)
- **Frequency**: Divide by 100 (e.g., 5998 → 59.98Hz)
- **Temperature**: Direct value in Celsius
- **Cell Voltage**: Divide by 1000 (e.g., 3300 → 3.300V)

## Development Commands

### Endpoint Discovery
```bash
# Test which API endpoint works with your credentials
# Configure .env first (see .env.example)
python research/test_endpoints.py
```

### Testing
```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=pylxpweb --cov-report=term-missing

# Run specific test file
pytest tests/test_client.py -v

# Run integration tests (requires credentials in .env)
pytest tests/integration/ -v
```

### Code Quality
```bash
# Format code
ruff check --fix && ruff format

# Type checking (strict mode)
mypy pylxpweb/ --strict

# Lint code
ruff check pylxpweb/ tests/
```

### Building
```bash
# Install in development mode
pip install -e .

# Build package
python -m build

# Install from built package
pip install dist/pylxpweb-*.whl
```

## Code Standards

This project follows strict quality standards similar to Home Assistant's Platinum tier:

1. **Type Hints**: All functions must have complete type annotations
   - Use `from __future__ import annotations` for forward references
   - Enable mypy strict mode

2. **Async/Await**: All I/O operations must be async
   - Use `aiohttp` for HTTP requests
   - Use `asyncio` for concurrent operations
   - No blocking operations in async code

3. **Error Handling**:
   - Define custom exceptions in `exceptions.py`
   - Use specific exception types (AuthError, ConnectionError, APIError)
   - Proper exception hierarchy

4. **Testing**:
   - Target >90% code coverage
   - Use `pytest` with `pytest-asyncio`
   - Mock external API calls in unit tests
   - Real API tests in `tests/integration/`

5. **Documentation**:
   - Google-style docstrings for all public classes/methods
   - Keep `docs/` updated with API findings
   - Document all discovered endpoints

## Documentation Requirements

### Priority 1: Luxpower API Documentation

Create `docs/api/LUXPOWER_API.md` with comprehensive documentation:

1. **Authentication Flow**
   - Login endpoint and request/response format
   - Session management (cookies, expiration)
   - Re-authentication handling

2. **Endpoint Catalog**
   - Complete list of all endpoints
   - Request/response schemas
   - Example requests and responses
   - Required headers and parameters

3. **Data Scaling Reference**
   - Document all scaling factors
   - Conversion formulas
   - Units for each metric

4. **Device Discovery Flow**
   - Station/plant enumeration
   - Device hierarchy traversal
   - Serial number formats

5. **Control Parameters**
   - Parameter IDs and meanings
   - Value ranges and validation
   - Write operation behavior

6. **Error Codes and Handling**
   - API error responses
   - HTTP status codes
   - Retry strategies

### Research Materials Usage

When documenting the API, reference:

1. **Sample API Responses**: `research/eg4_web_monitor/.../samples/*.json`
   - `runtime_*.json` - Real-time inverter data
   - `battery_*.json` - Battery information
   - `plants.json` - Station list
   - `midbox_*.json` - GridBOSS data

2. **Reference Implementation**: `research/eg4_web_monitor/.../client.py`
   - Authentication patterns
   - Session management
   - Caching strategies
   - Error handling

3. **Entity Implementations**: `research/eg4_web_monitor/.../sensor.py`
   - Data scaling examples
   - Field mappings
   - Unit conversions

## Example Client Interface

Based on research materials, the client should provide this interface:

```python
from pylxpweb import LuxpowerClient, AuthenticationError

async def main():
    # Support multiple regional endpoints
    # Default: https://monitor.eg4electronics.com
    # EU: https://eu.luxpowertek.com
    # US Luxpower: https://us.luxpowertek.com
    async with LuxpowerClient(
        username,
        password,
        base_url="https://monitor.eg4electronics.com"  # Configurable
    ) as client:
        # Authenticate automatically on first call
        plants = await client.get_plants()

        # Select a plant/station
        plant = plants[0]
        devices = await client.get_devices(plant["plantId"])

        # Get device data
        for device in devices:
            if device["type"] == "inverter":
                runtime = await client.get_inverter_runtime(device["serialNum"])
                energy = await client.get_inverter_energy(device["serialNum"])

                print(f"Inverter {device['serialNum']}")
                print(f"  Power: {runtime['pac']}W")
                print(f"  SOC: {runtime['soc']}%")
                print(f"  Daily Energy: {energy['eToday']}kWh")
```

## Architecture Principles

Follow these design patterns from the research implementation:

1. **Async-First**: All API calls use async/await
2. **Session Management**: Reuse aiohttp.ClientSession
3. **Session Injection**: Support injected session (Platinum tier requirement)
4. **Caching Strategy**:
   - Device discovery: 15 minutes
   - Battery info: 5 minutes
   - Parameters: 2 minutes
   - Runtime data: 20 seconds
5. **Retry Logic**: Exponential backoff with jitter
6. **Timeout Handling**: 30-second default timeout
7. **Error Granularity**: Specific exceptions for auth, network, API errors

## Important Notes

1. **Base URLs**: Multiple regional endpoints available:
   - US (Luxpower): `https://us.luxpowertek.com`
   - EU (Luxpower): `https://eu.luxpowertek.com`
   - US (EG4): `https://monitor.eg4electronics.com`
   - Base URL should be configurable by user
2. **Session Duration**: ~2 hours, implement auto-reauthentication
3. **Data Scaling**: Must divide voltage/current/frequency by 100
4. **Battery Keys**: Use `batteryKey` from API for unique battery identification
5. **Serial Numbers**: 10-digit numeric strings (e.g., "1234567890")
6. **GridBOSS Detection**: Different sensor sets for MID vs standard inverters

## Testing Strategy

### Unit Tests
- Mock all HTTP requests using `aiohttp.test_utils`
- Test authentication flow
- Test data parsing and scaling
- Test error handling

### Integration Tests
- Require real credentials in `tests/secrets.py`
- Test against live API
- Validate response formats
- Verify data accuracy

### Test Configuration

**Credentials**: Create `.env` file in project root:
```bash
# Copy example file
cp .env.example .env

# Edit .env with your credentials
LUXPOWER_USERNAME=your_username
LUXPOWER_PASSWORD=your_password
LUXPOWER_BASE_URL=https://monitor.eg4electronics.com
```

**Endpoint Discovery**: Use `scripts/test_endpoints.py` to find which endpoint works for your account.

**Note**: `.env` is in `.gitignore` - never commit credentials

## Pre-Commit Workflow

Before any commit, automatically run:
1. `ruff check --fix && ruff format`
2. `mypy --strict src/pylxpweb/`
3. `pytest tests/ --cov=pylxpweb`
4. All checks must pass before committing

## GitHub & CI/CD

### Repository
- **GitHub Repository**: `joyfulhouse/pylxpweb`
- **Package Manager**: `uv` (required for all dependency management)

### CI/CD Pipeline Structure

**CI Workflow** (`.github/workflows/ci.yml`):
```
Lint & Type Check (parallel) ─┐
Unit Tests (parallel)         ─┼─> Integration Tests ─> CI Success
                               │
                               └─> (all must pass)
```

Triggers: Push to main/master, Pull Requests, Manual Dispatch

1. **Lint & Type Check** (10 min timeout):
   - Uses: `actions/checkout@v5`, `astral-sh/setup-uv@v7`
   - Python: 3.13 (via `uv python install 3.13`)
   - `ruff check src/ tests/`
   - `ruff format --check src/ tests/`
   - `mypy --strict src/pylxpweb/`

2. **Unit Tests** (15 min timeout):
   - Uses: `actions/checkout@v5`, `astral-sh/setup-uv@v7`
   - Python: 3.13 (via `uv python install 3.13`)
   - `pytest tests/unit/ --cov=pylxpweb --cov-report=term-missing --cov-report=xml --cov-report=html -v`
   - Upload coverage to Codecov (`codecov/codecov-action@v5`)
   - Upload coverage HTML and pytest results (30-day retention via `upload-artifact@v5`)

3. **Integration Tests** (20 min timeout):
   - Depends on: Lint & Unit Tests passing
   - Uses: `actions/checkout@v5`, `astral-sh/setup-uv@v7`
   - Python: 3.13 (via `uv python install 3.13`)
   - Environment: `integration-test` (for secrets)
   - Skips for Dependabot PRs (no secret access)
   - `pytest tests/integration/ -v -m integration`
   - Environment variables: LUXPOWER_USERNAME, LUXPOWER_PASSWORD, LUXPOWER_BASE_URL

4. **CI Success**:
   - Final validation gate
   - Checks all upstream jobs passed

**Publish Workflow** (`.github/workflows/publish.yml`):
```
Lint ─┐
Test  ─┼─> Integration Tests ─> Build ─> TestPyPI ─> PyPI
       │
       └─> (all must pass)
```

Triggers: GitHub releases (`published`), Manual dispatch (choose testpypi/pypi)

1. **Lint & Type Check** (10 min timeout):
   - Uses: `actions/checkout@v5`, `astral-sh/setup-uv@v7`
   - Python: 3.13 (via `uv python install 3.13`)
   - Same checks as CI workflow

2. **Unit Tests** (15 min timeout):
   - Uses: `actions/checkout@v5`, `astral-sh/setup-uv@v7`
   - Python: 3.13 (via `uv python install 3.13`)
   - `pytest tests/unit/ --cov=pylxpweb --cov-report=term-missing --cov-report=xml --junitxml=pytest.xml`

3. **Integration Tests** (20 min timeout):
   - Depends on: Lint & Unit Tests passing
   - Environment: `integration-tests`
   - Same setup as CI workflow

4. **Build Package** (10 min timeout):
   - Depends on: All quality checks passing
   - `uv build` - Creates wheel and sdist
   - `uv run twine check dist/*` - Validates package
   - Upload artifacts: `python-package-distributions` (7-day retention via `upload-artifact@v5`)

5. **Publish to TestPyPI** (10 min timeout):
   - Environment: `testpypi`
   - Permissions: `id-token: write` (OIDC authentication)
   - Uses: `pypa/gh-action-pypi-publish@release/v1`
   - Repository: `https://test.pypi.org/legacy/`
   - Creates summary with test install command

6. **Publish to PyPI** (10 min timeout):
   - Depends on: Build & TestPyPI success
   - Environment: `pypi`
   - Permissions: `id-token: write` (OIDC authentication)
   - Uses: `pypa/gh-action-pypi-publish@release/v1`
   - Creates summary with PyPI link and install command

**Dependabot** (`.github/dependabot.yml`):
- **GitHub Actions**: Weekly updates (Mondays), max 5 PRs, uses latest `@v5`/`@v6`/`@v7` versions
- **Python (uv ecosystem)**: Weekly updates (Mondays), max 10 PRs
  - Groups: `development-dependencies` and `production-dependencies`
  - Update types: Minor and patch updates grouped together
  - Reviewer: `bryanli` (ensures uv compatibility)
- Commit messages: `chore(deps): ...` format

### GitHub Secrets Configuration

Required secrets (stored in GitHub repository settings):
- `LUXPOWER_USERNAME` - API username for integration tests
- `LUXPOWER_PASSWORD` - API password for integration tests
- `LUXPOWER_BASE_URL` - API base URL (default: https://monitor.eg4electronics.com)

Configure via `gh` CLI:
```bash
gh secret set LUXPOWER_USERNAME --body "$LUXPOWER_USERNAME"
gh secret set LUXPOWER_PASSWORD --body "$LUXPOWER_PASSWORD"
gh secret set LUXPOWER_BASE_URL --body "$LUXPOWER_BASE_URL"
```

### PyPI Publishing

**Trusted Publishers** (recommended):
- Configure OIDC trusted publisher on PyPI/TestPyPI
- No API tokens required
- More secure than API tokens

**Publishing Flow**:
1. Create GitHub release
2. CI runs all quality checks
3. Build distribution artifacts
4. Publish to TestPyPI (test environment)
5. If successful, publish to PyPI (production)

### Best Practices

1. **Concurrency Control**: Cancel in-progress runs for duplicate workflow executions
2. **Dependency Caching**: Use uv's built-in cache with lock file tracking
3. **Artifact Preservation**: Test and coverage reports (30 days), build artifacts (7 days)
4. **Secret Masking**: GitHub automatically masks credentials in logs
5. **Staged Validation**: Integration tests only run after all other checks pass
6. **OIDC Authentication**: Use trusted publishers instead of API tokens
7. **Environment Protection**: Use GitHub environments for deployment protection rules

## Current Status

**Phase**: Initial Setup

**To Be Created**:
- [ ] Main package structure (`pylxpweb/`)
- [ ] Core client implementation
- [ ] Authentication handler
- [ ] Data models
- [ ] Test suite
- [ ] API documentation (`docs/api/LUXPOWER_API.md`)
- [ ] Usage examples
- [ ] README.md

**Available Resources**:
- ✅ Complete reference implementation in `research/eg4_web_monitor/`
- ✅ Sample API responses in `research/.../samples/`
- ✅ Production-quality code patterns
- ✅ Comprehensive test examples
- Our code repository is at joyfulhouse/pylxpweb
- Always verify that unit and integration tests run before pushing to code repository like github.
- code should not reference files or folders in `.gitignore` - for example `research` contains sample data, if it is required for creating test fixtures, copy the data into the codebase at the appropriate location, in this case, `tests/samples`