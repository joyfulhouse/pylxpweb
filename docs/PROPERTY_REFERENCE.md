# Property Reference

Complete reference of all properties available on device objects. All properties return properly-scaled values and handle missing data gracefully.

## Table of Contents

- [BaseInverter Properties](#baseinverter-properties)
- [MIDDevice (GridBOSS) Properties](#middevice-gridboss-properties)
- [Battery Properties](#battery-properties)
- [BatteryBank Properties](#batterybank-properties)
- [ParallelGroup Properties](#parallelgroup-properties)

---

## BaseInverter Properties

All inverter types (`GenericInverter`, `HybridInverter`) inherit these properties from `BaseInverter`.

### PV (Solar Panel) Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `pv1_voltage` | `float` | V | PV string 1 voltage | 0.0 |
| `pv2_voltage` | `float` | V | PV string 2 voltage | 0.0 |
| `pv3_voltage` | `float` | V | PV string 3 voltage (if available) | 0.0 |
| `pv1_power` | `int` | W | PV string 1 power | 0 |
| `pv2_power` | `int` | W | PV string 2 power | 0 |
| `pv3_power` | `int` | W | PV string 3 power (if available) | 0 |
| `pv_total_power` | `int` | W | Total PV power from all strings | 0 |

**Example**:
```python
await inverter.refresh()
print(f"PV1: {inverter.pv1_voltage}V @ {inverter.pv1_power}W")
print(f"PV2: {inverter.pv2_voltage}V @ {inverter.pv2_power}W")
print(f"Total PV: {inverter.pv_total_power}W")
```

### AC Grid Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `grid_voltage_r` | `float` | V | Grid AC voltage phase R | 0.0 |
| `grid_voltage_s` | `float` | V | Grid AC voltage phase S | 0.0 |
| `grid_voltage_t` | `float` | V | Grid AC voltage phase T | 0.0 |
| `grid_frequency` | `float` | Hz | Grid AC frequency | 0.0 |
| `power_factor` | `str` | - | Power factor | "" |

**Example**:
```python
print(f"Grid R: {inverter.grid_voltage_r}V")
print(f"Grid S: {inverter.grid_voltage_s}V")
print(f"Grid T: {inverter.grid_voltage_t}V")
print(f"Frequency: {inverter.grid_frequency}Hz")
print(f"Power Factor: {inverter.power_factor}")
```

### EPS (Emergency Power Supply) Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `eps_voltage_r` | `float` | V | EPS voltage phase R | 0.0 |
| `eps_voltage_s` | `float` | V | EPS voltage phase S | 0.0 |
| `eps_voltage_t` | `float` | V | EPS voltage phase T | 0.0 |
| `eps_frequency` | `float` | Hz | EPS frequency | 0.0 |
| `eps_power` | `int` | W | Total EPS power | 0 |
| `eps_power_l1` | `int` | W | EPS L1 power | 0 |
| `eps_power_l2` | `int` | W | EPS L2 power | 0 |

**Example**:
```python
if inverter.eps_power > 0:
    print(f"EPS Active: {inverter.eps_power}W @ {inverter.eps_frequency}Hz")
```

### Power Flow Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `power_to_grid` | `int` | W | Power flowing to grid (export) | 0 |
| `power_to_user` | `int` | W | Power flowing to user loads | 0 |
| `inverter_power` | `int` | W | Inverter power output | 0 |
| `rectifier_power` | `int` | W | Rectifier power | 0 |
| `consumption_power` | `int` | W | Total consumption power | 0 |

**Example**:
```python
print(f"Solar → Grid: {inverter.power_to_grid}W")
print(f"Solar → House: {inverter.power_to_user}W")
print(f"Inverter Output: {inverter.inverter_power}W")
```

### Battery Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `battery_voltage` | `float` | V | Battery voltage | 0.0 |
| `battery_soc` | `int` | % | Battery state of charge | 0 |
| `battery_charge_power` | `int` | W | Battery charging power | 0 |
| `battery_discharge_power` | `int` | W | Battery discharging power | 0 |
| `battery_power` | `int` | W | Net battery power (+charge, -discharge) | 0 |
| `battery_temperature` | `int` | °C | Battery temperature | 0 |
| `max_charge_current` | `float` | A | Maximum charge current | 0.0 |
| `max_discharge_current` | `float` | A | Maximum discharge current | 0.0 |

**Example**:
```python
print(f"Battery: {inverter.battery_soc}% @ {inverter.battery_voltage}V")
if inverter.battery_charge_power > 0:
    print(f"Charging: {inverter.battery_charge_power}W")
elif inverter.battery_discharge_power > 0:
    print(f"Discharging: {inverter.battery_discharge_power}W")
```

### Temperature Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `inverter_temperature` | `int` | °C | Inverter internal temperature | 0 |
| `radiator1_temperature` | `int` | °C | Radiator 1 temperature | 0 |
| `radiator2_temperature` | `int` | °C | Radiator 2 temperature | 0 |

**Example**:
```python
print(f"Inverter: {inverter.inverter_temperature}°C")
print(f"Radiator 1: {inverter.radiator1_temperature}°C")
print(f"Radiator 2: {inverter.radiator2_temperature}°C")
```

### Bus Voltage Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `bus1_voltage` | `float` | V | DC bus 1 voltage | 0.0 |
| `bus2_voltage` | `float` | V | DC bus 2 voltage | 0.0 |

**Example**:
```python
print(f"Bus 1: {inverter.bus1_voltage}V")
print(f"Bus 2: {inverter.bus2_voltage}V")
```

### AC Couple & Generator Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `ac_couple_power` | `int` | W | AC coupled power | 0 |
| `generator_voltage` | `float` | V | Generator voltage | 0.0 |
| `generator_frequency` | `float` | Hz | Generator frequency | 0.0 |
| `generator_power` | `int` | W | Generator power | 0 |
| `is_using_generator` | `bool` | - | Whether generator is in use | False |

**Example**:
```python
if inverter.is_using_generator:
    print(f"Generator: {inverter.generator_power}W @ {inverter.generator_frequency}Hz")
if inverter.ac_couple_power > 0:
    print(f"AC Couple: {inverter.ac_couple_power}W")
```

### Status & Info Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `firmware_version` | `str` | - | Firmware version string | "" |
| `status` | `int` | - | Status code | 0 |
| `status_text` | `str` | - | Status text (e.g., "Online") | "" |
| `is_lost` | `bool` | - | Whether connection is lost | True |
| `power_rating` | `str` | - | Power rating text (e.g., "16kW") | "" |
| `model` | `str` | - | Inverter model | "" |
| `serial_number` | `str` | - | Serial number | "" |
| `has_data` | `bool` | - | Whether runtime data is available | False |

**Example**:
```python
print(f"{inverter.model} {inverter.serial_number}")
print(f"Firmware: {inverter.firmware_version}")
print(f"Status: {inverter.status_text}")
print(f"Rating: {inverter.power_rating}")
if inverter.is_lost:
    print("WARNING: Inverter offline")
```

### Energy Properties (Historical Data)

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `total_energy_today` | `float` | kWh | Today's total energy production | 0.0 |
| `total_energy_lifetime` | `float` | kWh | Lifetime total energy production | 0.0 |
| `power_output` | `float` | W | Load output power (reg 170 Pload / cloud `pLoad170`) | None |

**Example**:
```python
print(f"Today: {inverter.total_energy_today} kWh")
print(f"Lifetime: {inverter.total_energy_lifetime} kWh")
print(f"Current: {inverter.power_output}W")
```

---

## MIDDevice (GridBOSS) Properties

GridBOSS devices provide comprehensive grid monitoring and load management.

### Voltage Properties - Aggregate

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `grid_voltage` | `float` | V | Aggregate grid RMS voltage | 0.0 |
| `ups_voltage` | `float` | V | Aggregate UPS RMS voltage | 0.0 |
| `generator_voltage` | `float` | V | Aggregate generator RMS voltage | 0.0 |

**Example**:
```python
print(f"Grid: {mid.grid_voltage}V")
print(f"UPS: {mid.ups_voltage}V")
print(f"Generator: {mid.generator_voltage}V")
```

### Voltage Properties - Per-Phase

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `grid_l1_voltage` | `float` | V | Grid L1 RMS voltage | 0.0 |
| `grid_l2_voltage` | `float` | V | Grid L2 RMS voltage | 0.0 |
| `ups_l1_voltage` | `float` | V | UPS L1 RMS voltage | 0.0 |
| `ups_l2_voltage` | `float` | V | UPS L2 RMS voltage | 0.0 |
| `generator_l1_voltage` | `float` | V | Generator L1 RMS voltage | 0.0 |
| `generator_l2_voltage` | `float` | V | Generator L2 RMS voltage | 0.0 |

**Example**:
```python
print(f"Grid L1: {mid.grid_l1_voltage}V")
print(f"Grid L2: {mid.grid_l2_voltage}V")
```

### Current Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `grid_l1_current` | `float` | A | Grid L1 RMS current | 0.0 |
| `grid_l2_current` | `float` | A | Grid L2 RMS current | 0.0 |
| `load_l1_current` | `float` | A | Load L1 RMS current | 0.0 |
| `load_l2_current` | `float` | A | Load L2 RMS current | 0.0 |
| `generator_l1_current` | `float` | A | Generator L1 RMS current | 0.0 |
| `generator_l2_current` | `float` | A | Generator L2 RMS current | 0.0 |
| `ups_l1_current` | `float` | A | UPS L1 RMS current | 0.0 |
| `ups_l2_current` | `float` | A | UPS L2 RMS current | 0.0 |

**Example**:
```python
print(f"Grid L1: {mid.grid_l1_current}A")
print(f"Load L1: {mid.load_l1_current}A")
print(f"UPS L1: {mid.ups_l1_current}A")
```

### Power Properties - Grid

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `grid_l1_power` | `int` | W | Grid L1 active power | 0 |
| `grid_l2_power` | `int` | W | Grid L2 active power | 0 |
| `grid_power` | `int` | W | Total grid power (L1 + L2) | 0 |

**Example**:
```python
print(f"Grid Total: {mid.grid_power}W")
print(f"  L1: {mid.grid_l1_power}W")
print(f"  L2: {mid.grid_l2_power}W")
```

### Power Properties - Load

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `load_l1_power` | `int` | W | Load L1 active power | 0 |
| `load_l2_power` | `int` | W | Load L2 active power | 0 |
| `load_power` | `int` | W | Total load power (L1 + L2) | 0 |

**Example**:
```python
print(f"Load Total: {mid.load_power}W")
print(f"  L1: {mid.load_l1_power}W")
print(f"  L2: {mid.load_l2_power}W")
```

### Power Properties - UPS

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `ups_l1_power` | `int` | W | UPS L1 active power | 0 |
| `ups_l2_power` | `int` | W | UPS L2 active power | 0 |
| `ups_power` | `int` | W | Total UPS power (L1 + L2) | 0 |

**Example**:
```python
print(f"UPS Total: {mid.ups_power}W")
print(f"  L1: {mid.ups_l1_power}W")
print(f"  L2: {mid.ups_l2_power}W")
```

### Power Properties - Generator

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `generator_l1_power` | `int` | W | Generator L1 active power | 0 |
| `generator_l2_power` | `int` | W | Generator L2 active power | 0 |
| `generator_power` | `int` | W | Total generator power (L1 + L2) | 0 |

**Example**:
```python
if mid.generator_power > 0:
    print(f"Generator: {mid.generator_power}W")
```

### Power Properties - Hybrid System

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `hybrid_power` | `int` | W | Hybrid system power | 0 |

**Example**:
```python
print(f"Hybrid System: {mid.hybrid_power}W")
```

### Frequency Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `grid_frequency` | `float` | Hz | Grid frequency | 0.0 |

**Example**:
```python
print(f"Grid Frequency: {mid.grid_frequency}Hz")
```

### Smart Port Status

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `smart_port1_status` | `int` | - | Smart port 1 status code | 0 |
| `smart_port2_status` | `int` | - | Smart port 2 status code | 0 |
| `smart_port3_status` | `int` | - | Smart port 3 status code | 0 |
| `smart_port4_status` | `int` | - | Smart port 4 status code | 0 |

**Example**:
```python
print(f"Port 1: {mid.smart_port1_status}")
print(f"Port 2: {mid.smart_port2_status}")
```

### System Status & Info

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `status` | `int` | - | Device status code | 0 |
| `firmware_version` | `str` | - | Firmware version | "" |
| `server_time` | `str` | - | Server timestamp | "" |
| `device_time` | `str` | - | Device timestamp | "" |
| `has_data` | `bool` | - | Whether runtime data is available | False |
| `model` | `str` | - | Device model | "GridBOSS" |
| `serial_number` | `str` | - | Serial number | "" |

**Example**:
```python
print(f"{mid.model} {mid.serial_number}")
print(f"Firmware: {mid.firmware_version}")
print(f"Status: {mid.status}")
```

---

## Battery Properties

Individual battery module properties.

### Basic Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `voltage` | `float` | V | Battery voltage | 0.0 |
| `current` | `float` | A | Battery current | 0.0 |
| `power` | `int` | W | Battery power | 0 |
| `soc` | `int` | % | State of charge | 0 |
| `soh` | `int` | % | State of health | 0 |

**Example**:
```python
print(f"Battery {battery.battery_index + 1}:")
print(f"  Voltage: {battery.voltage}V")
print(f"  Current: {battery.current}A")
print(f"  SOC: {battery.soc}%")
print(f"  SOH: {battery.soh}%")
```

### Temperature Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `max_cell_temp` | `float` | °C | Maximum cell temperature | 0.0 |
| `min_cell_temp` | `float` | °C | Minimum cell temperature | 0.0 |
| `cell_temp_delta` | `float` | °C | Temperature delta (max - min) | 0.0 |

**Example**:
```python
print(f"Temperature: {battery.max_cell_temp}°C")
print(f"Delta: {battery.cell_temp_delta}°C")
```

### Cell Voltage Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `max_cell_voltage` | `float` | V | Maximum cell voltage | 0.0 |
| `min_cell_voltage` | `float` | V | Minimum cell voltage | 0.0 |
| `cell_voltage_delta` | `float` | V | Voltage delta (max - min) | 0.0 |

**Example**:
```python
print(f"Max Cell: {battery.max_cell_voltage}V")
print(f"Min Cell: {battery.min_cell_voltage}V")
print(f"Delta: {battery.cell_voltage_delta}V")
```

### Cell Number Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `max_voltage_cell_number` | `int` | - | Cell number with max voltage | 0 |
| `min_voltage_cell_number` | `int` | - | Cell number with min voltage | 0 |
| `max_temp_cell_number` | `int` | - | Cell number with max temperature | 0 |
| `min_temp_cell_number` | `int` | - | Cell number with min temperature | 0 |

**Example**:
```python
print(f"Max voltage in cell #{battery.max_voltage_cell_number}")
print(f"Max temp in cell #{battery.max_temp_cell_number}")
```

### Capacity Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `current_capacity` | `float` | Ah | Current capacity | 0.0 |
| `max_capacity` | `float` | Ah | Maximum capacity | 0.0 |
| `cycle_count` | `int` | - | Cycle count | 0 |

**Example**:
```python
print(f"Capacity: {battery.current_capacity}/{battery.max_capacity} Ah")
print(f"Cycles: {battery.cycle_count}")
```

### System Info Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `battery_type` | `str` | - | Battery type | "" |
| `bms_model` | `str` | - | BMS model | "" |
| `firmware_version` | `str` | - | Firmware version | "" |
| `is_lost` | `bool` | - | Whether battery is offline | True |
| `battery_index` | `int` | - | Battery index in array | 0 |
| `battery_key` | `str` | - | Battery unique key | "" |

**Example**:
```python
print(f"{battery.battery_type} (BMS: {battery.bms_model})")
print(f"Firmware: {battery.firmware_version}")
if battery.is_lost:
    print("WARNING: Battery offline")
```

---

## BatteryBank Properties

Aggregate battery bank data for all connected batteries.

### Basic Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `voltage` | `float` | V | Bank voltage | 0.0 |
| `soc` | `int` | % | State of charge | 0 |
| `soh` | `int` | % | State of health | 0 |
| `charge_power` | `int` | W | Charging power | 0 |
| `discharge_power` | `int` | W | Discharging power | 0 |

**Example**:
```python
print(f"Bank: {bank.soc}% @ {bank.voltage}V")
if bank.charge_power > 0:
    print(f"Charging: {bank.charge_power}W")
```

### Capacity Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `current_capacity` | `float` | Ah | Current total capacity | 0.0 |
| `max_capacity` | `float` | Ah | Maximum total capacity | 0.0 |
| `battery_count` | `int` | - | Number of battery modules | 0 |

**Example**:
```python
print(f"Capacity: {bank.current_capacity}/{bank.max_capacity} Ah")
print(f"Modules: {bank.battery_count}")
```

### System Properties

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `status` | `int` | - | Status code | 0 |
| `batteries` | `list[Battery]` | - | Individual battery modules | [] |

**Example**:
```python
print(f"Status: {bank.status}")
print(f"Individual batteries: {len(bank.batteries)}")
for battery in bank.batteries:
    print(f"  Battery {battery.battery_index + 1}: {battery.soc}%")
```

---

## ParallelGroup Properties

Parallel groups represent multiple inverters operating in parallel and provide aggregate energy data.

### Energy Properties - Today

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `today_yielding` | `float` | kWh | Today's PV generation | 0.0 |
| `today_charging` | `float` | kWh | Today's battery charging | 0.0 |
| `today_discharging` | `float` | kWh | Today's battery discharging | 0.0 |
| `today_import` | `float` | kWh | Today's grid import | 0.0 |
| `today_export` | `float` | kWh | Today's grid export | 0.0 |
| `today_usage` | `float` | kWh | Today's energy usage | 0.0 |

**Example**:
```python
print(f"Today:")
print(f"  Solar: {group.today_yielding} kWh")
print(f"  Import: {group.today_import} kWh")
print(f"  Export: {group.today_export} kWh")
print(f"  Usage: {group.today_usage} kWh")
```

### Energy Properties - Total (Lifetime)

| Property | Type | Unit | Description | Default if No Data |
|----------|------|------|-------------|-------------------|
| `total_yielding` | `float` | kWh | Total lifetime PV generation | 0.0 |
| `total_charging` | `float` | kWh | Total lifetime battery charging | 0.0 |
| `total_discharging` | `float` | kWh | Total lifetime battery discharging | 0.0 |
| `total_import` | `float` | kWh | Total lifetime grid import | 0.0 |
| `total_export` | `float` | kWh | Total lifetime grid export | 0.0 |
| `total_usage` | `float` | kWh | Total lifetime energy usage | 0.0 |

**Example**:
```python
print(f"Lifetime:")
print(f"  Solar: {group.total_yielding} kWh")
print(f"  Import: {group.total_import} kWh")
print(f"  Export: {group.total_export} kWh")
print(f"  Usage: {group.total_usage} kWh")
```

### System Properties

| Property | Type | Unit | Description |
|----------|------|------|-------------|
| `name` | `str` | - | Group identifier (e.g., "A", "B") |
| `first_device_serial` | `str` | - | Serial of first device in group |
| `inverters` | `list[BaseInverter]` | - | List of inverters in group |
| `mid_device` | `MIDDevice \| None` | - | Optional GridBOSS device |

**Example**:
```python
print(f"Group {group.name}:")
print(f"  Inverters: {len(group.inverters)}")
if group.mid_device:
    print(f"  GridBOSS: {group.mid_device.serial_number}")
```

---

## Common Patterns

### Checking for Data Availability

All device classes have a `has_data` property:

```python
if inverter.has_data:
    print(f"Power: {inverter.pv_total_power}W")
else:
    print("No data available (device offline or not yet refreshed)")
```

### Handling None/Missing Values

All properties return sensible defaults when data is not available:

```python
# Always safe to access - returns 0 if no data
power = inverter.pv_total_power  # Returns 0, not None
voltage = inverter.grid_voltage_r  # Returns 0.0, not None
status = inverter.status_text  # Returns "", not None
offline = inverter.is_lost  # Returns True, not None
```

### Working with Optional Properties

Some properties (like PV3, generator) may not be available on all devices:

```python
# PV3 returns 0 if not supported
if inverter.pv3_voltage > 0:
    print(f"PV3: {inverter.pv3_voltage}V @ {inverter.pv3_power}W")

# Generator returns 0 if not active
if inverter.generator_power > 0:
    print(f"Generator: {inverter.generator_power}W")
```

### Type Safety

All properties have explicit type annotations:

```python
from pylxpweb.devices.inverters.base import BaseInverter

def analyze_inverter(inverter: BaseInverter) -> None:
    voltage: float = inverter.grid_voltage_r  # Type-checked
    power: int = inverter.pv_total_power  # Type-checked
    status: str = inverter.status_text  # Type-checked
    lost: bool = inverter.is_lost  # Type-checked
```

## Next Steps

- **[Usage Guide](USAGE_GUIDE.md)** - Comprehensive usage examples
- **[Scaling Guide](SCALING_GUIDE.md)** - Data scaling details
- **[API Reference](api/LUXPOWER_API.md)** - Low-level API documentation
