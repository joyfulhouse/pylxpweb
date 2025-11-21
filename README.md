# pylxpweb

A Python client library for Luxpower/EG4 solar inverters and energy storage systems, providing programmatic access to the Luxpower/EG4 web monitoring API.

## Supported API Endpoints

This library supports multiple regional API endpoints:
- **US (Luxpower)**: `https://us.luxpowertek.com`
- **EU (Luxpower)**: `https://eu.luxpowertek.com`
- **US (EG4 Electronics)**: `https://monitor.eg4electronics.com`

The base URL is fully configurable to support regional variations and future endpoints.

## Features

- **Complete API Coverage**: Access all inverter, battery, and GridBOSS data
- **Async/Await**: Built with `aiohttp` for efficient async I/O operations
- **Session Management**: Automatic authentication and session renewal
- **Smart Caching**: Configurable caching with TTL to minimize API calls
- **Type Safe**: Comprehensive type hints throughout
- **Error Handling**: Robust error handling with automatic retry and backoff
- **Production Ready**: Based on battle-tested Home Assistant integration

## Supported Devices

- **Inverters**: FlexBOSS21, FlexBOSS18, 18KPV, 12KPV, XP series
- **GridBOSS**: Microgrid interconnection devices (MID)
- **Batteries**: All EG4-compatible battery modules with BMS integration

## Installation

```bash
# From PyPI (recommended)
pip install pylxpweb

# From source (development)
git clone https://github.com/joyfulhouse/pylxpweb.git
cd pylxpweb
uv sync --all-extras --dev
```

## Quick Start

```python
import asyncio
from pylxpweb import LuxpowerClient

async def main():
    # Create client with credentials
    # Default base_url is https://monitor.eg4electronics.com
    async with LuxpowerClient(
        username="your_username",
        password="your_password",
        base_url="https://monitor.eg4electronics.com"  # or us.luxpowertek.com, eu.luxpowertek.com
    ) as client:
        # Get all stations/plants using the API namespace
        plants = await client.api.plants.get_plants()
        print(f"Found {len(plants.rows)} stations")

        # Select first station
        plant = plants.rows[0]
        plant_id = plant.plantId

        # Get devices for this station
        devices = await client.api.devices.get_devices(str(plant_id))

        # Get runtime data for each inverter
        for device in devices.rows:
            if device.deviceType == 6:  # Inverter type
                serial = device.serialNum

                # Get real-time data using API namespace
                runtime = await client.api.devices.get_inverter_runtime(serial)
                energy = await client.api.devices.get_inverter_energy_info(serial)

                print(f"\nInverter {serial}:")
                print(f"  AC Power: {runtime.pac}W")
                print(f"  Battery SOC: {runtime.soc}%")
                print(f"  Daily Energy: {energy.eToday}kWh")
                print(f"  Grid Power: {runtime.pToGrid}W")

                # Get battery information
                batteries = await client.api.devices.get_battery_info(serial)
                for battery_module in batteries.batteryArray:
                    key = battery_module.batteryKey
                    soc = battery_module.soc
                    voltage = battery_module.totalVoltage / 100  # Scale voltage
                    print(f"  Battery {key}: {soc}% @ {voltage}V")

asyncio.run(main())
```

## Advanced Usage

### Regional Endpoints and Custom Session

```python
from aiohttp import ClientSession

async with ClientSession() as session:
    # Choose the appropriate regional endpoint
    # US (Luxpower): https://us.luxpowertek.com
    # EU (Luxpower): https://eu.luxpowertek.com
    # US (EG4): https://monitor.eg4electronics.com

    client = LuxpowerClient(
        username="user",
        password="pass",
        base_url="https://eu.luxpowertek.com",  # EU endpoint example
        verify_ssl=True,
        timeout=30,
        session=session  # Inject external session
    )

    await client.login()
    plants = await client.get_plants()
    await client.close()  # Only closes if we created the session
```

### Control Operations

```python
async with LuxpowerClient(username, password) as client:
    serial = "1234567890"

    # Enable quick charge
    await client.set_quick_charge(serial, enabled=True)

    # Set battery charge limit to 90%
    await client.set_charge_soc_limit(serial, limit=90)

    # Set operating mode to standby
    await client.set_operating_mode(serial, mode="standby")

    # Read current parameters
    params = await client.read_parameters(serial, [21, 22, 23])
    print(f"SOC Limit: {params[0]['value']}%")
```

### Error Handling

```python
from pylxpweb import (
    LuxpowerClient,
    AuthenticationError,
    ConnectionError,
    APIError
)

try:
    async with LuxpowerClient(username, password) as client:
        runtime = await client.get_inverter_runtime(serial)

except AuthenticationError as e:
    print(f"Login failed: {e}")

except ConnectionError as e:
    print(f"Network error: {e}")

except APIError as e:
    print(f"API error: {e}")
```

## Documentation

- **[API Reference](docs/api/LUXPOWER_API.md)** - Complete API endpoint documentation
- **[Architecture](docs/architecture/)** - System design and patterns *(coming soon)*
- **[Examples](docs/examples/)** - Usage examples and patterns *(coming soon)*
- **[CLAUDE.md](CLAUDE.md)** - Development guidelines for Claude Code

## Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/joyfulhouse/pylxpweb.git
cd pylxpweb

# Install development dependencies
pip install -e ".[dev]"

# Install test dependencies
pip install pytest pytest-asyncio pytest-cov aiohttp
```

### Running Tests

```bash
# Run all tests
uv run pytest tests/

# Run with coverage
uv run pytest tests/ --cov=pylxpweb --cov-report=term-missing

# Run unit tests only
uv run pytest tests/unit/ -v

# Run integration tests (requires credentials in .env)
uv run pytest tests/integration/ -v -m integration
```

### Code Quality

```bash
# Format code
uv run ruff check --fix && uv run ruff format

# Type checking
uv run mypy src/pylxpweb/ --strict

# Lint code
uv run ruff check src/ tests/
```

## Project Structure

```
pylxpweb/
├── docs/                        # Documentation
│   ├── api/                     # API endpoint documentation
│   │   └── LUXPOWER_API.md      # Complete API reference
│   └── luxpower-api.yaml        # OpenAPI 3.0 specification
│
├── src/pylxpweb/                # Main package
│   ├── __init__.py              # Package exports
│   ├── client.py                # LuxpowerClient (async API client)
│   ├── endpoints/               # Endpoint-specific implementations
│   │   ├── devices.py           # Device and runtime data
│   │   ├── plants.py            # Station/plant management
│   │   ├── control.py           # Control operations
│   │   ├── firmware.py          # Firmware management
│   │   └── ...                  # Additional endpoints
│   ├── models.py                # Pydantic data models
│   ├── constants.py             # Constants and register definitions
│   └── exceptions.py            # Custom exception classes
│
├── tests/                       # Test suite (90%+ coverage)
│   ├── conftest.py              # Pytest fixtures and aiohttp mock server
│   ├── unit/                    # Unit tests (136 tests)
│   │   ├── test_client.py       # Client tests
│   │   ├── test_models.py       # Model tests
│   │   └── test_*.py            # Additional unit tests
│   ├── integration/             # Integration tests (requires credentials)
│   │   └── test_live_api.py     # Live API integration tests
│   └── samples/                 # Sample API responses for testing
│
├── .env.example                 # Environment variable template
├── .github/                     # GitHub Actions workflows
│   ├── workflows/               # CI/CD pipelines
│   └── dependabot.yml          # Dependency updates
├── CLAUDE.md                    # Claude Code development guidelines
├── README.md                    # This file
└── pyproject.toml              # Package configuration (uv-based)
```

## Data Scaling

The API returns scaled integer values that must be converted:

| Data Type | Scaling | Example |
|-----------|---------|---------|
| Voltage | ÷ 100 | 5100 → 51.00V |
| Current | ÷ 100 | 1500 → 15.00A |
| Frequency | ÷ 100 | 5998 → 59.98Hz |
| Cell Voltage | ÷ 1000 | 3350 → 3.350V |
| Power | none | 1030 → 1030W |
| Temperature | none | 39 → 39°C |

See [API Reference](docs/api/LUXPOWER_API.md#data-scaling-reference) for complete details.

## API Endpoints

**Authentication**:
- `POST /WManage/api/login` - Authenticate and establish session

**Discovery**:
- `POST /WManage/web/config/plant/list/viewer` - List stations/plants
- `POST /WManage/api/inverterOverview/getParallelGroupDetails` - Device hierarchy
- `POST /WManage/api/inverterOverview/list` - All devices in station

**Runtime Data**:
- `POST /WManage/api/inverter/getInverterRuntime` - Real-time inverter data
- `POST /WManage/api/inverter/getInverterEnergyInfo` - Energy statistics
- `POST /WManage/api/battery/getBatteryInfo` - Battery information
- `POST /WManage/api/midbox/getMidboxRuntime` - GridBOSS data

**Control**:
- `POST /WManage/web/maintain/remoteRead/read` - Read parameters
- `POST /WManage/web/maintain/remoteSet/write` - Write parameters
- `POST /WManage/web/maintain/remoteSet/functionControl` - Control functions

See [API Reference](docs/api/LUXPOWER_API.md) for complete endpoint documentation.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and code quality checks
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Development Standards

- All code must have type hints
- Maintain >90% test coverage
- Follow PEP 8 style guide
- Use async/await for all I/O operations
- Document all public APIs with Google-style docstrings

## Credits

This project builds upon research and knowledge from the Home Assistant community:
- Inspired by production Home Assistant integrations for EG4/Luxpower devices
- API endpoint research and documentation
- Best practices for async Python libraries

Special thanks to the Home Assistant community for their pioneering work with these devices.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Endpoint Discovery

### Finding Your Endpoint

Most EG4 users in North America should use `https://monitor.eg4electronics.com` (the default).

If you're unsure which endpoint to use:
1. Try the default first: `https://monitor.eg4electronics.com`
2. For Luxpower branded systems:
   - US: `https://us.luxpowertek.com`
   - EU: `https://eu.luxpowertek.com`
3. Check your official mobile app or web portal URL for the correct regional endpoint

### Contributing New Endpoints

If you discover additional regional endpoints, please contribute by:
1. Opening an issue with the endpoint URL
2. Confirming it uses the same `/WManage/api/` structure
3. Noting which region/brand it serves
4. Running `scripts/test_endpoints.py` to verify connectivity

Known endpoints are documented in [API Reference](docs/api/LUXPOWER_API.md#choosing-the-right-endpoint).

## Disclaimer

**Unofficial** library not affiliated with Luxpower or EG4 Electronics. Use at your own risk.

This library communicates with the official EG4/Luxpower API using the same endpoints as the official mobile app and web interface.

## Support

- **Documentation**: [docs/](docs/)
- **Issues**: [GitHub Issues](https://github.com/joyfulhouse/pylxpweb/issues)
- **API Reference**: [docs/api/LUXPOWER_API.md](docs/api/LUXPOWER_API.md)

## Status

**Current Phase**: Core Implementation Complete

- ✅ Research and API documentation complete
- ✅ CLAUDE.md development guidelines
- ✅ Comprehensive API reference documentation
- ✅ Core library implementation (async client with full API coverage)
- ✅ Test suite development (95% code coverage with 44 unit tests)
- ✅ Package configuration (uv + pyproject.toml)
- ✅ Type safety (mypy --strict passing)
- ✅ Code quality (ruff linting passing)
- ⏳ PyPI publication

## Roadmap

1. **Phase 1**: Core library implementation
   - Client class with authentication
   - Device discovery and management
   - Runtime data retrieval
   - Data models and scaling

2. **Phase 2**: Advanced features
   - Control operations
   - Caching with configurable TTL
   - Retry logic and error handling
   - Session injection support

3. **Phase 3**: Testing and polish
   - Comprehensive test suite (>90% coverage)
   - Integration tests
   - Documentation examples
   - Type checking with mypy strict mode

4. **Phase 4**: Distribution
   - Package configuration (pyproject.toml)
   - PyPI publication
   - CI/CD pipeline
   - Release automation

---

**Happy monitoring!** ☀️⚡🔋
