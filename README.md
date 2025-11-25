# pylxpweb

[![CI](https://github.com/joyfulhouse/pylxpweb/actions/workflows/ci.yml/badge.svg)](https://github.com/joyfulhouse/pylxpweb/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/joyfulhouse/pylxpweb/branch/main/graph/badge.svg)](https://codecov.io/gh/joyfulhouse/pylxpweb)
[![PyPI version](https://badge.fury.io/py/pylxpweb.svg)](https://badge.fury.io/py/pylxpweb)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

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

### Basic Usage with Device Objects

```python
import asyncio
from pylxpweb import LuxpowerClient
from pylxpweb.devices.station import Station

async def main():
    # Create client with credentials
    # Default base_url is https://monitor.eg4electronics.com
    async with LuxpowerClient(
        username="your_username",
        password="your_password",
        base_url="https://monitor.eg4electronics.com"  # or us.luxpowertek.com, eu.luxpowertek.com
    ) as client:
        # Load all stations with device hierarchy
        stations = await Station.load_all(client)
        print(f"Found {len(stations)} stations")

        # Work with first station
        station = stations[0]
        print(f"\nStation: {station.name}")

        # Access inverters - all have properly-scaled properties
        for inverter in station.all_inverters:
            await inverter.refresh()  # Fetch latest data

            print(f"\n{inverter.model} {inverter.serial_number}:")

            # All properties return properly-scaled values
            print(f"  PV Power: {inverter.pv_total_power}W")
            print(f"  Battery: {inverter.battery_soc}% @ {inverter.battery_voltage}V")
            print(f"  Grid: {inverter.grid_voltage_r}V @ {inverter.grid_frequency}Hz")
            print(f"  Inverter Power: {inverter.inverter_power}W")
            print(f"  To Grid: {inverter.power_to_grid}W")
            print(f"  To User: {inverter.power_to_user}W")
            print(f"  Temperature: {inverter.inverter_temperature}°C")
            print(f"  Today: {inverter.total_energy_today}kWh")
            print(f"  Lifetime: {inverter.total_energy_lifetime}kWh")

            # Access battery bank if available
            if inverter.battery_bank:
                bank = inverter.battery_bank
                print(f"\n  Battery Bank:")
                print(f"    Voltage: {bank.voltage}V")
                print(f"    SOC: {bank.soc}%")
                print(f"    Charge Power: {bank.charge_power}W")
                print(f"    Discharge Power: {bank.discharge_power}W")
                print(f"    Capacity: {bank.current_capacity}/{bank.max_capacity} Ah")

                # Individual battery modules
                for battery in bank.batteries:
                    print(f"    Battery {battery.battery_index + 1}:")
                    print(f"      Voltage: {battery.voltage}V")
                    print(f"      Current: {battery.current}A")
                    print(f"      SOC: {battery.soc}%")
                    print(f"      Temp: {battery.max_cell_temp}°C")

        # Access GridBOSS (MID) devices if present
        for group in station.parallel_groups:
            if group.mid_device:
                mid = group.mid_device
                await mid.refresh()

                print(f"\nGridBOSS {mid.serial_number}:")
                print(f"  Grid: {mid.grid_voltage}V @ {mid.grid_frequency}Hz")
                print(f"  Grid Power: {mid.grid_power}W")
                print(f"  UPS Power: {mid.ups_power}W")
                print(f"  Load L1: {mid.load_l1_power}W @ {mid.load_l1_current}A")
                print(f"  Load L2: {mid.load_l2_power}W @ {mid.load_l2_current}A")

asyncio.run(main())
```

### Low-Level API Access

For direct API access without device objects:

```python
async with LuxpowerClient(username, password) as client:
    # Get stations
    plants = await client.api.plants.get_plants()
    plant_id = plants.rows[0].plantId

    # Get devices
    devices = await client.api.devices.get_devices(str(plant_id))

    # Get runtime data for first inverter
    inverter = devices.rows[0]
    serial = inverter.serialNum

    # Fetch data (returns Pydantic models)
    runtime = await client.api.devices.get_inverter_runtime(serial)
    energy = await client.api.devices.get_inverter_energy(serial)

    # NOTE: Raw API returns scaled integers - you must scale manually
    print(f"AC Power: {runtime.pac}W")  # No scaling needed for power
    print(f"Grid Voltage: {runtime.vacr / 10}V")  # Must divide by 10
    print(f"Grid Frequency: {runtime.fac / 100}Hz")  # Must divide by 100
    print(f"Battery Voltage: {runtime.vBat / 10}V")  # Must divide by 10
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

### Automatic Scaling with Device Properties (Recommended)

**Device objects automatically handle all scaling** - just use the properties:

```python
# ✅ RECOMMENDED: Use device properties (automatically scaled)
await inverter.refresh()
voltage = inverter.grid_voltage_r  # Returns 241.8 (already scaled)
frequency = inverter.grid_frequency  # Returns 59.98 (already scaled)
power = inverter.pv_total_power  # Returns 1500 (already scaled)
```

All device classes (`BaseInverter`, `MIDDevice`, `Battery`, `BatteryBank`, `ParallelGroup`) provide properly-scaled properties. **You never need to manually scale values when using device objects.**

### Manual Scaling for Raw API Data

If you use the low-level API directly (not recommended for most users), you must scale values manually:

| Data Type | Scaling | Raw API | Scaled | Property Name |
|-----------|---------|---------|--------|---------------|
| Inverter Voltage | ÷10 | 2410 | 241.0V | `grid_voltage_r` |
| Battery Voltage (Bank) | ÷10 | 539 | 53.9V | `battery_voltage` |
| Battery Voltage (Module) | ÷100 | 5394 | 53.94V | `voltage` |
| Cell Voltage | ÷1000 | 3364 | 3.364V | `max_cell_voltage` |
| Current | ÷100 | 1500 | 15.00A | `grid_l1_current` |
| Frequency | ÷100 | 5998 | 59.98Hz | `grid_frequency` |
| Bus Voltage | ÷100 | 3703 | 37.03V | `bus1_voltage` |
| Power | Direct | 1030 | 1030W | `inverter_power` |
| Temperature | Direct | 39 | 39°C | `inverter_temperature` |
| Energy | ÷10 | 184 | 18.4 kWh | `today_yielding` |

**Note**: Different voltage types use different scaling factors. Use device properties to avoid confusion.

See [Scaling Guide](docs/SCALING_GUIDE.md) and [API Reference](docs/api/LUXPOWER_API.md#data-scaling-reference) for complete details.

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

---

**Happy monitoring!** ☀️⚡🔋
