# pylxpweb

A Python client library for Luxpower/EG4 solar inverters and energy storage systems.

[![PyPI Version][pypi-shield]][pypi]
[![Python Versions][pyversions-shield]][pypi]
[![License][license-shield]](LICENSE)
[![CI][ci-shield]][ci]
[![GitHub Sponsors][sponsors-shield]][sponsors]
[![Ko-fi][kofi-shield]][kofi]

## What It Does

pylxpweb provides programmatic access to the Luxpower/EG4 web monitoring API, 
and also local connection, enabling Python applications and Home Assistant integrations 
to read real-time inverter data, energy statistics, battery information, and GridBOSS 
metrics. It is the library backing the [EG4 Web Monitor][crosslink] Home Assistant integration.

## Features

- **Complete API Coverage**: Inverter runtime, energy statistics, battery BMS, and GridBOSS data
- **Device Object Hierarchy**: High-level `Station` → `ParallelGroup` → `BaseInverter` / `MIDDevice` / `BatteryBank` → `Battery` objects with auto-scaled properties
- **Async/Await**: Built on `aiohttp` for efficient async I/O
- **Session Management**: Automatic authentication and session renewal
- **Smart Caching**: Configurable TTL caching to minimise API calls
- **Type Safe**: Comprehensive type hints and Pydantic models throughout
- **Error Handling**: Robust error handling with automatic retry and backoff
- **Regional Endpoints**: Supports all global Luxpower and EG4 endpoints
- **Control Operations**: Read and write inverter parameters, enable quick charge, set SOC limits
- **Multiple connection/transport types**: can be used with cloud API and also with local connection 
 

## Supported Devices

- **Inverters**: FlexBOSS21, FlexBOSS18, 18KPV, 12KPV, XP series, and LXP variants
- **GridBOSS**: Microgrid interconnection devices (MID)
- **Batteries**: All EG4-compatible battery modules with BMS integration

## Supported Regional Endpoints

| Region | Endpoint |
|--------|----------|
| US (EG4 Electronics) | `https://monitor.eg4electronics.com` (default) |
| US (Luxpower) | `https://us.luxpowertek.com` |
| Americas (Luxpower) | `https://na.luxpowertek.com` |
| Europe (Luxpower) | `https://eu.luxpowertek.com` |
| Asia Pacific (Luxpower) | `https://sea.luxpowertek.com` |
| Middle East & Africa (Luxpower) | `https://af.luxpowertek.com` |
| China (Luxpower) | `https://server.luxpowertek.com` |

The base URL is fully configurable to support regional variations and future endpoints.

## Supported Transports
- **cloud / web API** - original supported method
- **dongle** - connect to the dongle of inverter which is used to send data to cloud
  - the dongle allow to communicate with cloud and locally at same time
  - but it does not control clearly which one requested data
  - this will raise some "Response mismatch" messages on log, 
    when the library get an response that does not match what was requested
  - the dongle uses modbus encapsulated on proprietary protocol
  - it will not work with dongles that have encription enabled (**E-WIFI   ENC**), 
    if you have a dongle with this description ask Luxpower Support to downgrade it 
- **modbus** - direct modbus connection which needs an connection to the RS-485 port of the inverter
- **hybrid** - allow to combine one local connection with cloud

Local connections should be used by single apps, using same type of connection by multiple
 apps can result in data corruption, intermitent errors.

You can't use the same local connection by multiple clients like Home Assistant + script, 
or multiple Home Assistant instances.


## Installation

See **[INSTALL.md](INSTALL.md)** for the complete guide.

```bash
pip install pylxpweb
# or
uv add pylxpweb
```

Requires Python 3.13+.

## Quick Start

### Using Device Objects (Recommended)

```python
import asyncio
from pylxpweb import LuxpowerClient
from pylxpweb.devices.station import Station

async def main():
    async with LuxpowerClient(
        username="your_username",
        password="your_password",
        base_url="https://monitor.eg4electronics.com"
    ) as client:
        stations = await Station.load_all(client)
        station = stations[0]

        for inverter in station.all_inverters:
            await inverter.refresh()
            print(f"{inverter.model} {inverter.serial_number}:")
            print(f"  PV Power: {inverter.pv_total_power}W")
            print(f"  Battery: {inverter.battery_soc}% @ {inverter.battery_voltage}V")
            print(f"  Grid: {inverter.grid_voltage_r}V @ {inverter.grid_frequency}Hz")
            print(f"  Today: {inverter.total_energy_today}kWh")

asyncio.run(main())
```

Device objects handle all value scaling automatically — no manual division required.

## Usage

### Low-Level API Access

For direct endpoint calls without the device-object layer:

```python
async with LuxpowerClient(username, password) as client:
    plants = await client.api.plants.get_plants()
    plant_id = plants.rows[0].plantId
    devices = await client.api.devices.get_devices(str(plant_id))
    serial = devices.rows[0].serialNum

    runtime = await client.api.devices.get_inverter_runtime(serial)
    # Raw API returns scaled integers — divide as needed:
    print(f"Grid Voltage: {runtime.vacr / 10}V")
    print(f"Grid Frequency: {runtime.fac / 100}Hz")
    print(f"Battery Voltage: {runtime.vBat / 10}V")
```

### Control Operations

```python
async with LuxpowerClient(username, password) as client:
    serial = "1234567890"
    await client.set_quick_charge(serial, enabled=True)
    await client.set_charge_soc_limit(serial, limit=90)
    await client.set_operating_mode(serial, mode="standby")
    params = await client.read_parameters(serial, [21, 22, 23])
```

### Error Handling

```python
from pylxpweb import LuxpowerClient, AuthenticationError, ConnectionError, APIError

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

### Data Scaling

Device objects auto-scale all values. For raw API use, apply these factors manually:

| Data Type | Factor | Example raw | Scaled |
|-----------|--------|-------------|--------|
| Inverter Voltage | ÷10 | 2410 | 241.0 V |
| Battery Voltage (Bank) | ÷10 | 539 | 53.9 V |
| Battery Voltage (Module) | ÷100 | 5394 | 53.94 V |
| Cell Voltage | ÷1000 | 3364 | 3.364 V |
| Current | ÷100 | 1500 | 15.00 A |
| Frequency | ÷100 | 5998 | 59.98 Hz |
| Power | Direct | 1030 | 1030 W |
| Temperature | Direct | 39 | 39 °C |
| Energy | ÷10 | 184 | 18.4 kWh |

See [docs/SCALING_GUIDE.md](docs/SCALING_GUIDE.md) for the full reference.

## API Reference

Full reference documentation lives in [docs/](docs/). Key entry points:

| Document | Contents |
|----------|----------|
| [docs/api/LUXPOWER_API.md](docs/api/LUXPOWER_API.md) | Complete endpoint catalog, authentication, error codes |
| [docs/PROPERTY_REFERENCE.md](docs/PROPERTY_REFERENCE.md) | All device properties with types and scaling |
| [docs/PARAMETER_REFERENCE.md](docs/PARAMETER_REFERENCE.md) | Hold/input register definitions and control parameters |
| [docs/SCALING_GUIDE.md](docs/SCALING_GUIDE.md) | Scaling factors for raw API data |
| [docs/USAGE_GUIDE.md](docs/USAGE_GUIDE.md) | Comprehensive usage examples |
| [docs/DEVICE_TYPES.md](docs/DEVICE_TYPES.md) | Supported device types and capabilities |

The `docs/` index is at [docs/README.md](docs/README.md).

## Development

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). In short:

```bash
git clone https://github.com/joyfulhouse/pylxpweb.git
cd pylxpweb
uv sync
uv run pytest
uv run ruff check
uv run mypy
```

## Support

- **Issues:** <https://github.com/joyfulhouse/pylxpweb/issues>
- **PyPI:** <https://pypi.org/project/pylxpweb/>

## Support Development

If this library is useful to you, please consider supporting its development:

- [GitHub Sponsors][sponsors]
- [Ko-fi][kofi]

## License

This project is licensed under the **MIT** License — see [LICENSE](LICENSE) for details.

## Related Projects

- [EG4 Web Monitor][crosslink] — the Home Assistant integration built on this library.

## Credits

This project builds upon research and knowledge from the Home Assistant community.
Special thanks to the Home Assistant community for their pioneering work with EG4 and
Luxpower devices — API endpoint research, documentation, and best practices shaped this
library from the start.

**Disclaimer**: Unofficial library, not affiliated with Luxpower or EG4 Electronics.
Communicates with the official API using the same endpoints as the official web interface.

<!-- Badge links -->
[pypi-shield]: https://img.shields.io/pypi/v/pylxpweb.svg?style=for-the-badge
[pypi]: https://pypi.org/project/pylxpweb/
[pyversions-shield]: https://img.shields.io/pypi/pyversions/pylxpweb.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/joyfulhouse/pylxpweb.svg?style=for-the-badge
[ci-shield]: https://img.shields.io/github/actions/workflow/status/joyfulhouse/pylxpweb/ci.yml?style=for-the-badge&label=CI
[ci]: https://github.com/joyfulhouse/pylxpweb/actions
[sponsors-shield]: https://img.shields.io/badge/sponsor-GitHub-EA4AAA.svg?style=for-the-badge&logo=githubsponsors&logoColor=white
[sponsors]: https://github.com/sponsors/btli
[kofi-shield]: https://img.shields.io/badge/Ko--fi-donate-FF5E5B.svg?style=for-the-badge&logo=ko-fi&logoColor=white
[kofi]: https://ko-fi.com/bryanli
[crosslink]: https://github.com/joyfulhouse/eg4_web_monitor
