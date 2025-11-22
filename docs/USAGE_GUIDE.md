# pylxpweb Usage Guide

Complete guide to using the pylxpweb library for EG4/Luxpower solar inverter monitoring and control.

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Device Hierarchy](#device-hierarchy)
- [Working with Inverters](#working-with-inverters)
- [Working with Batteries](#working-with-batteries)
- [Working with GridBOSS (MID) Devices](#working-with-gridboss-mid-devices)
- [Working with Parallel Groups](#working-with-parallel-groups)
- [Control Operations](#control-operations)
- [Error Handling](#error-handling)
- [Best Practices](#best-practices)

## Installation

```bash
pip install pylxpweb
```

For development:

```bash
git clone https://github.com/joyfulhouse/pylxpweb.git
cd pylxpweb
uv sync --all-extras --dev
```

## Quick Start

```python
import asyncio
from pylxpweb import LuxpowerClient
from pylxpweb.devices.station import Station

async def main():
    async with LuxpowerClient(
        username="your_username",
        password="your_password"
    ) as client:
        # Load all stations
        stations = await Station.load_all(client)

        for station in stations:
            print(f"Station: {station.name}")

            # Access all inverters
            for inverter in station.all_inverters:
                await inverter.refresh()
                print(f"  {inverter.serial_number}: {inverter.pv_total_power}W")

asyncio.run(main())
```

## Device Hierarchy

The library uses an object-oriented hierarchy that mirrors the physical system:

```
Station (Plant)
├── Parallel Groups (0-N)
│   ├── MID Device (GridBOSS) - Optional
│   └── Inverters (1-N)
│       └── Battery Bank
│           └── Individual Batteries (0-N)
└── Standalone Inverters (0-N)
    └── Battery Bank
        └── Individual Batteries (0-N)
```

### Loading the Device Hierarchy

```python
# Load all stations with complete device hierarchy
stations = await Station.load_all(client)

# Load specific station
station = await Station.load(client, plant_id=12345)

# Access devices
print(f"Parallel groups: {len(station.parallel_groups)}")
print(f"Standalone inverters: {len(station.standalone_inverters)}")
print(f"All inverters: {len(station.all_inverters)}")
```

## Working with Inverters

All inverter types (`GenericInverter`, `HybridInverter`) inherit from `BaseInverter` and provide the same property interface.

### Basic Inverter Monitoring

```python
# Get inverter
inverter = station.all_inverters[0]

# Refresh data (fetches runtime, energy, and battery data concurrently)
await inverter.refresh()

# === PV (Solar Panel) Properties ===
print(f"PV1 Voltage: {inverter.pv1_voltage}V")
print(f"PV2 Voltage: {inverter.pv2_voltage}V")
print(f"PV1 Power: {inverter.pv1_power}W")
print(f"PV2 Power: {inverter.pv2_power}W")
print(f"Total PV Power: {inverter.pv_total_power}W")

# === AC Grid Properties ===
print(f"Grid Voltage R: {inverter.grid_voltage_r}V")
print(f"Grid Voltage S: {inverter.grid_voltage_s}V")
print(f"Grid Voltage T: {inverter.grid_voltage_t}V")
print(f"Grid Frequency: {inverter.grid_frequency}Hz")
print(f"Power Factor: {inverter.power_factor}")

# === Power Flow Properties ===
print(f"Inverter Power: {inverter.inverter_power}W")
print(f"Power to Grid: {inverter.power_to_grid}W")
print(f"Power to User: {inverter.power_to_user}W")
print(f"Rectifier Power: {inverter.rectifier_power}W")

# === Battery Properties ===
print(f"Battery Voltage: {inverter.battery_voltage}V")
print(f"Battery SOC: {inverter.battery_soc}%")
print(f"Battery Charge Power: {inverter.battery_charge_power}W")
print(f"Battery Discharge Power: {inverter.battery_discharge_power}W")
print(f"Battery Temperature: {inverter.battery_temperature}°C")
print(f"Max Charge Current: {inverter.max_charge_current}A")
print(f"Max Discharge Current: {inverter.max_discharge_current}A")

# === Temperature Properties ===
print(f"Inverter Temperature: {inverter.inverter_temperature}°C")
print(f"Radiator 1: {inverter.radiator1_temperature}°C")
print(f"Radiator 2: {inverter.radiator2_temperature}°C")

# === Energy Properties ===
print(f"Today's Energy: {inverter.total_energy_today}kWh")
print(f"Lifetime Energy: {inverter.total_energy_lifetime}kWh")

# === Status Properties ===
print(f"Firmware: {inverter.firmware_version}")
print(f"Status: {inverter.status_text}")
print(f"Is Lost: {inverter.is_lost}")
print(f"Power Rating: {inverter.power_rating}")
```

### EPS (Emergency Power Supply) Properties

For inverters with EPS capability:

```python
print(f"EPS Voltage R: {inverter.eps_voltage_r}V")
print(f"EPS Voltage S: {inverter.eps_voltage_s}V")
print(f"EPS Frequency: {inverter.eps_frequency}Hz")
print(f"EPS Power: {inverter.eps_power}W")
print(f"EPS L1 Power: {inverter.eps_power_l1}W")
print(f"EPS L2 Power: {inverter.eps_power_l2}W")
```

### Generator & AC Coupling Properties

For systems with generator or AC coupling:

```python
print(f"Generator Voltage: {inverter.generator_voltage}V")
print(f"Generator Frequency: {inverter.generator_frequency}Hz")
print(f"Generator Power: {inverter.generator_power}W")
print(f"Using Generator: {inverter.is_using_generator}")
print(f"AC Couple Power: {inverter.ac_couple_power}W")
```

### Advanced Properties

```python
# Bus voltages (internal DC bus)
print(f"Bus 1 Voltage: {inverter.bus1_voltage}V")
print(f"Bus 2 Voltage: {inverter.bus2_voltage}V")

# Consumption tracking
print(f"Consumption Power: {inverter.consumption_power}W")
```

## Working with Batteries

### Battery Bank (Aggregate Data)

```python
if inverter.battery_bank:
    bank = inverter.battery_bank

    # Aggregate battery data
    print(f"Voltage: {bank.voltage}V")
    print(f"SOC: {bank.soc}%")
    print(f"SOH: {bank.soh}%")
    print(f"Charge Power: {bank.charge_power}W")
    print(f"Discharge Power: {bank.discharge_power}W")
    print(f"Current Capacity: {bank.current_capacity} Ah")
    print(f"Max Capacity: {bank.max_capacity} Ah")
    print(f"Battery Count: {bank.battery_count}")
    print(f"Status: {bank.status}")
```

### Individual Battery Modules

```python
if inverter.battery_bank:
    for battery in inverter.battery_bank.batteries:
        print(f"\nBattery {battery.battery_index + 1}:")

        # Basic properties
        print(f"  Voltage: {battery.voltage}V")
        print(f"  Current: {battery.current}A")
        print(f"  Power: {battery.power}W")
        print(f"  SOC: {battery.soc}%")
        print(f"  SOH: {battery.soh}%")

        # Temperature
        print(f"  Max Cell Temp: {battery.max_cell_temp}°C")
        print(f"  Min Cell Temp: {battery.min_cell_temp}°C")
        print(f"  Temp Delta: {battery.cell_temp_delta}°C")

        # Cell voltages
        print(f"  Max Cell Voltage: {battery.max_cell_voltage}V")
        print(f"  Min Cell Voltage: {battery.min_cell_voltage}V")
        print(f"  Voltage Delta: {battery.cell_voltage_delta}V")

        # Cell numbers
        print(f"  Max Voltage Cell: #{battery.max_voltage_cell_number}")
        print(f"  Min Voltage Cell: #{battery.min_voltage_cell_number}")
        print(f"  Max Temp Cell: #{battery.max_temp_cell_number}")
        print(f"  Min Temp Cell: #{battery.min_temp_cell_number}")

        # Capacity and cycles
        print(f"  Current Capacity: {battery.current_capacity} Ah")
        print(f"  Max Capacity: {battery.max_capacity} Ah")
        print(f"  Cycle Count: {battery.cycle_count}")

        # Advanced properties
        print(f"  Battery Type: {battery.battery_type}")
        print(f"  BMS Model: {battery.bms_model}")
        print(f"  Firmware: {battery.firmware_version}")
        print(f"  Is Lost: {battery.is_lost}")
```

## Working with GridBOSS (MID) Devices

GridBOSS devices provide comprehensive grid monitoring and load management.

```python
for group in station.parallel_groups:
    if group.mid_device:
        mid = group.mid_device
        await mid.refresh()

        print(f"\nGridBOSS {mid.serial_number}:")

        # === Aggregate Voltages ===
        print(f"Grid Voltage: {mid.grid_voltage}V")
        print(f"UPS Voltage: {mid.ups_voltage}V")
        print(f"Generator Voltage: {mid.generator_voltage}V")

        # === Per-Phase Grid Voltages ===
        print(f"Grid L1: {mid.grid_l1_voltage}V")
        print(f"Grid L2: {mid.grid_l2_voltage}V")

        # === Per-Phase Currents ===
        print(f"Grid L1 Current: {mid.grid_l1_current}A")
        print(f"Grid L2 Current: {mid.grid_l2_current}A")
        print(f"Load L1 Current: {mid.load_l1_current}A")
        print(f"Load L2 Current: {mid.load_l2_current}A")

        # === Power Properties ===
        print(f"Grid Power: {mid.grid_power}W")
        print(f"Grid L1 Power: {mid.grid_l1_power}W")
        print(f"Grid L2 Power: {mid.grid_l2_power}W")

        print(f"Load Power: {mid.load_power}W")
        print(f"Load L1 Power: {mid.load_l1_power}W")
        print(f"Load L2 Power: {mid.load_l2_power}W")

        print(f"UPS Power: {mid.ups_power}W")
        print(f"UPS L1 Power: {mid.ups_l1_power}W")
        print(f"UPS L2 Power: {mid.ups_l2_power}W")

        print(f"Generator Power: {mid.generator_power}W")
        print(f"Hybrid Power: {mid.hybrid_power}W")

        # === Frequency ===
        print(f"Grid Frequency: {mid.grid_frequency}Hz")

        # === Smart Ports ===
        print(f"Smart Port 1: {mid.smart_port1_status}")
        print(f"Smart Port 2: {mid.smart_port2_status}")
        print(f"Smart Port 3: {mid.smart_port3_status}")
        print(f"Smart Port 4: {mid.smart_port4_status}")

        # === System Info ===
        print(f"Status: {mid.status}")
        print(f"Firmware: {mid.firmware_version}")
        print(f"Server Time: {mid.server_time}")
        print(f"Device Time: {mid.device_time}")
```

## Working with Parallel Groups

Parallel groups represent multiple inverters operating in parallel.

### Basic Parallel Group Operations

```python
for group in station.parallel_groups:
    print(f"\nParallel Group {group.name}:")
    print(f"  Inverters: {len(group.inverters)}")
    print(f"  First Device: {group.first_device_serial}")

    # Refresh all devices in group concurrently
    await group.refresh()

    # Access individual inverters
    for inverter in group.inverters:
        print(f"  {inverter.serial_number}: {inverter.pv_total_power}W")

    # Access GridBOSS if present
    if group.mid_device:
        print(f"  GridBOSS: {group.mid_device.serial_number}")
```

### Parallel Group Energy Data

Parallel groups automatically fetch aggregate energy data:

```python
await group.refresh()  # Fetches parallel energy data

# === Today's Energy ===
print(f"Today PV: {group.today_yielding} kWh")
print(f"Today Charging: {group.today_charging} kWh")
print(f"Today Discharging: {group.today_discharging} kWh")
print(f"Today Import: {group.today_import} kWh")
print(f"Today Export: {group.today_export} kWh")
print(f"Today Usage: {group.today_usage} kWh")

# === Lifetime Energy ===
print(f"Total PV: {group.total_yielding} kWh")
print(f"Total Charging: {group.total_charging} kWh")
print(f"Total Discharging: {group.total_discharging} kWh")
print(f"Total Import: {group.total_import} kWh")
print(f"Total Export: {group.total_export} kWh")
print(f"Total Usage: {group.total_usage} kWh")
```

## Control Operations

### Battery Charge Limits

```python
# Set on-grid charge limit to 90%
await inverter.set_battery_soc_limits(on_grid_soc=90)

# Set off-grid discharge limit to 20%
await inverter.set_battery_soc_limits(off_grid_soc=20)

# Set both limits
await inverter.set_battery_soc_limits(on_grid_soc=90, off_grid_soc=20)

# Get current limits
limits = await inverter.get_battery_soc_limits()
print(f"On-Grid: {limits['on_grid_soc']}%")
print(f"Off-Grid: {limits['off_grid_soc']}%")
```

### Operating Modes

```python
from pylxpweb.models import OperatingMode

# Set standby mode
await inverter.set_standby_mode(OperatingMode.STANDBY)

# Power on
await inverter.set_standby_mode(OperatingMode.POWER_ON)
```

### AC Charge Mode (for HybridInverter)

```python
# Enable AC charging
await inverter.enable_ac_charge_mode()

# Disable AC charging
await inverter.disable_ac_charge_mode()

# Check status
is_enabled = await inverter.get_ac_charge_mode_status()
print(f"AC Charge: {'Enabled' if is_enabled else 'Disabled'}")
```

### Reading and Writing Parameters

```python
# Read specific parameters
params = await inverter.read_parameters(start_register=21, count=10)
for register, value in params.items():
    print(f"Register {register}: {value}")

# Write parameters
await inverter.write_parameters({21: 90})  # Set SOC limit to 90%
```

## Error Handling

```python
from pylxpweb.exceptions import (
    LuxpowerAuthenticationError,
    LuxpowerConnectionError,
    LuxpowerAPIError,
    LuxpowerDeviceError
)

try:
    async with LuxpowerClient(username, password) as client:
        stations = await Station.load_all(client)

except LuxpowerAuthenticationError as e:
    print(f"Authentication failed: {e}")
    # Invalid credentials

except LuxpowerConnectionError as e:
    print(f"Connection error: {e}")
    # Network issue or wrong base URL

except LuxpowerDeviceError as e:
    print(f"Device error: {e}")
    # Device offline or not responding

except LuxpowerAPIError as e:
    print(f"API error: {e}")
    # General API error
```

### Graceful Error Handling

All `refresh()` methods handle errors gracefully:

```python
# If refresh fails, cached data is retained
await inverter.refresh()  # May fail, but won't raise exception

# Check if data is available
if inverter.has_data:
    print(f"Power: {inverter.pv_total_power}W")
else:
    print("No data available")
```

## Best Practices

### 1. Use Device Objects (Not Raw API)

✅ **Recommended**:
```python
# Device objects handle scaling automatically
await inverter.refresh()
voltage = inverter.grid_voltage_r  # 241.8V (properly scaled)
```

❌ **Not Recommended**:
```python
# Raw API requires manual scaling
runtime = await client.api.devices.get_inverter_runtime(serial)
voltage = runtime.vacr / 10  # Easy to forget or get wrong
```

### 2. Refresh Data Before Accessing Properties

```python
# Always refresh before reading properties
await inverter.refresh()
print(f"Power: {inverter.pv_total_power}W")

# For stations, refresh all devices
await station.refresh_all_data()
```

### 3. Use Concurrent Operations

```python
# Station refresh is concurrent
await station.refresh_all_data()  # Refreshes all devices in parallel

# Parallel group refresh is concurrent
await group.refresh()  # Refreshes all inverters and MID device in parallel
```

### 4. Check for None/Empty Data

```python
# Check if inverter has data
if inverter.has_data:
    print(f"Power: {inverter.pv_total_power}W")

# Check for battery bank
if inverter.battery_bank:
    print(f"SOC: {inverter.battery_bank.soc}%")

# Properties return sensible defaults (0, 0.0, "", False) when no data
power = inverter.pv_total_power  # Returns 0 if no data
```

### 5. Use Context Manager for Client

```python
# ✅ Use async context manager (handles cleanup)
async with LuxpowerClient(username, password) as client:
    stations = await Station.load_all(client)

# ❌ Manual management (error-prone)
client = LuxpowerClient(username, password)
await client.login()
# ... code ...
await client.close()  # Easy to forget
```

### 6. Cache-Aware Design

The client automatically manages caching with TTL and hour-boundary invalidation:

```python
# Inverter refresh caches data with TTL:
# - Runtime data: 20 seconds
# - Energy data: 20 seconds
# - Battery data: 5 minutes
# - Parameters: 2 minutes

await inverter.refresh()  # Fetches data
await inverter.refresh()  # Uses cache (if within TTL)
await inverter.refresh(force=True)  # Bypasses cache

# Cache automatically cleared on hour boundaries (e.g., midnight)
# to ensure fresh data for daily energy resets
```

**Important: Daily Energy Values**

Properties like `today_yielding`, `today_charging`, etc. reset at midnight (API server time):

```python
# These values accumulate throughout the day and reset at midnight:
print(f"Today's PV: {inverter.today_yielding} kWh")  # Resets daily
print(f"Today's Charging: {inverter.today_charging} kWh")  # Resets daily

# Lifetime values never reset:
print(f"Lifetime PV: {inverter.lifetime_yielding} kWh")  # Monotonically increasing
```

**Note**: The API controls reset timing, which may not align exactly with midnight in your timezone. The client invalidates cache on hour boundaries to minimize stale data, but values shortly after midnight may temporarily reflect the previous day's total until the API backend resets.

**For Home Assistant integrations**: Use `SensorStateClass.TOTAL_INCREASING` for daily energy sensors. Home Assistant's statistics system automatically detects value decreases and handles them as resets, providing accurate long-term statistics.

### 7. Use Type Hints

```python
from pylxpweb.devices.inverters.base import BaseInverter
from pylxpweb.devices.station import Station

async def monitor_inverter(inverter: BaseInverter) -> None:
    await inverter.refresh()
    print(f"Power: {inverter.pv_total_power}W")

async def main() -> None:
    stations: list[Station] = await Station.load_all(client)
```

### 8. Regional Endpoint Selection

```python
# Choose the correct regional endpoint
endpoints = {
    "US (EG4)": "https://monitor.eg4electronics.com",  # Default
    "US (Luxpower)": "https://us.luxpowertek.com",
    "EU (Luxpower)": "https://eu.luxpowertek.com",
}

client = LuxpowerClient(
    username=username,
    password=password,
    base_url=endpoints["US (EG4)"]
)
```

## Complete Example

```python
import asyncio
from pylxpweb import LuxpowerClient
from pylxpweb.devices.station import Station

async def monitor_system():
    """Complete monitoring example."""
    async with LuxpowerClient(
        username="your_username",
        password="your_password"
    ) as client:
        # Load all stations
        stations = await Station.load_all(client)

        for station in stations:
            print(f"\n{'='*60}")
            print(f"Station: {station.name} (ID: {station.id})")
            print(f"{'='*60}")

            # Refresh all data concurrently
            await station.refresh_all_data()

            # Monitor inverters
            for inverter in station.all_inverters:
                if not inverter.has_data:
                    continue

                print(f"\n{inverter.model} ({inverter.serial_number}):")
                print(f"  PV: {inverter.pv_total_power}W")
                print(f"  Battery: {inverter.battery_soc}% @ {inverter.battery_voltage}V")
                print(f"  Grid: {inverter.power_to_grid}W")
                print(f"  Load: {inverter.power_to_user}W")
                print(f"  Today: {inverter.total_energy_today} kWh")

                # Battery details
                if inverter.battery_bank:
                    bank = inverter.battery_bank
                    print(f"  Battery Bank: {bank.current_capacity}/{bank.max_capacity} Ah")
                    print(f"  Modules: {len(bank.batteries)}")

            # Monitor GridBOSS devices
            for group in station.parallel_groups:
                if group.mid_device and group.mid_device.has_data:
                    mid = group.mid_device
                    print(f"\nGridBOSS {mid.serial_number}:")
                    print(f"  Grid: {mid.grid_power}W @ {mid.grid_frequency}Hz")
                    print(f"  Load: {mid.load_power}W")
                    print(f"  UPS: {mid.ups_power}W")

                # Parallel group energy
                print(f"\nParallel Group {group.name}:")
                print(f"  Today: {group.today_yielding} kWh")
                print(f"  Lifetime: {group.total_yielding} kWh")

if __name__ == "__main__":
    asyncio.run(monitor_system())
```

## Next Steps

- **[Property Reference](PROPERTY_REFERENCE.md)** - Complete list of all available properties
- **[API Reference](api/LUXPOWER_API.md)** - Low-level API documentation
- **[Scaling Guide](SCALING_GUIDE.md)** - Detailed scaling information
- **[Control Operations Guide](CONTROL_GUIDE.md)** - Advanced control operations *(coming soon)*

## Support

For issues, questions, or contributions:
- **GitHub Issues**: https://github.com/joyfulhouse/pylxpweb/issues
- **Documentation**: https://github.com/joyfulhouse/pylxpweb/tree/main/docs
