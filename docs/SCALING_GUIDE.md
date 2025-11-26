# Data Scaling Guide

**Last Updated**: 2025-11-26
**Purpose**: Comprehensive guide to data scaling in pylxpweb

## Overview

The Luxpower/EG4 API returns raw integer values that must be scaled with different divisors (÷10, ÷100, ÷1000). This guide explains the centralized scaling system in `src/pylxpweb/constants/scaling.py`.

**Note on Energy Values**: pylxpweb does NOT implement monotonic enforcement for energy sensors. Home Assistant's `SensorStateClass.TOTAL_INCREASING` handles daily resets and monotonic behavior automatically. The library simply returns the scaled API values.

## Quick Start

```python
from pylxpweb.constants import (
    scale_runtime_value,
    scale_battery_value,
    scale_energy_value,
    apply_scale,
    ScaleFactor,
)

# Scale inverter runtime values
voltage = scale_runtime_value("vpv1", 5100)  # 510.0V
frequency = scale_runtime_value("fac", 5998)  # 59.98Hz

# Scale battery values
bat_voltage = scale_battery_value("totalVoltage", 5305)  # 53.05V
bat_current = scale_battery_value("current", 60)  # 6.0A

# Scale energy values
energy_kwh = scale_energy_value("todayYielding", 90, to_kwh=True)  # 0.009 kWh
energy_wh = scale_energy_value("todayYielding", 90, to_kwh=False)  # 9.0 Wh

# Direct scaling
scaled = apply_scale(3317, ScaleFactor.SCALE_1000)  # 3.317V (cell voltage)
```

## Scaling Factor Reference

### ScaleFactor Enum

```python
class ScaleFactor(int, Enum):
    SCALE_NONE = 1      # No scaling (direct value)
    SCALE_10 = 10       # Divide by 10
    SCALE_100 = 100     # Divide by 100
    SCALE_1000 = 1000   # Divide by 1000
```

### When to Use Each Scale Factor

| Scale Factor | Use Cases | Example |
|--------------|-----------|---------|
| `SCALE_10` | Most voltages, some currents, temperatures | `5100 → 510.0V` |
| `SCALE_100` | Frequency, bus voltages, most currents | `5998 → 59.98Hz` |
| `SCALE_1000` | Cell voltages (millivolts) | `3317 → 3.317V` |
| `SCALE_NONE` | Power, percentages, counts | `1030 → 1030W` |

## Data Type Scaling Maps

### 1. Inverter Runtime Data

**Source**: `getInverterRuntime` endpoint
**Constant**: `INVERTER_RUNTIME_SCALING`

#### Voltages

```python
# PV Input Voltages (÷10)
"vpv1": ScaleFactor.SCALE_10,    # 5100 → 510.0V
"vpv2": ScaleFactor.SCALE_10,
"vpv3": ScaleFactor.SCALE_10,

# AC Voltages (÷10)
"vacr": ScaleFactor.SCALE_10,    # 2411 → 241.1V
"vacs": ScaleFactor.SCALE_10,
"vact": ScaleFactor.SCALE_10,

# EPS Voltages (÷10)
"vepsr": ScaleFactor.SCALE_10,
"vepss": ScaleFactor.SCALE_10,
"vepst": ScaleFactor.SCALE_10,

# Battery Voltage (÷10)
"vBat": ScaleFactor.SCALE_10,    # 530 → 53.0V

# Bus Voltages (÷100) - Different!
"vBus1": ScaleFactor.SCALE_100,  # 3703 → 37.03V
"vBus2": ScaleFactor.SCALE_100,
```

#### Frequency

```python
# AC Frequency (÷100)
"fac": ScaleFactor.SCALE_100,    # 5998 → 59.98Hz
"feps": ScaleFactor.SCALE_100,

# Generator Frequency (÷100)
"genFreq": ScaleFactor.SCALE_100,
```

#### Currents

```python
# Inverter Currents (÷100)
"maxChgCurr": ScaleFactor.SCALE_100,      # 6000 → 60.00A
"maxDischgCurr": ScaleFactor.SCALE_100,
```

#### Power & Temperature

```python
# Power (NO SCALING)
"ppv1": ScaleFactor.SCALE_NONE,   # 1030 → 1030W
"pCharge": ScaleFactor.SCALE_NONE,
"pinv": ScaleFactor.SCALE_NONE,

# Temperature (NO SCALING)
"tinner": ScaleFactor.SCALE_NONE,  # 39 → 39°C
"tradiator1": ScaleFactor.SCALE_NONE,
```

### 2. Energy Data

**Source**: `getInverterEnergyInfo` endpoint
**Constant**: `ENERGY_INFO_SCALING`

All energy fields use `SCALE_10` to convert API values (Wh×10) to Wh:

```python
"todayYielding": ScaleFactor.SCALE_10,    # 90 → 9.0 Wh
"monthYielding": ScaleFactor.SCALE_10,
"totalYielding": ScaleFactor.SCALE_10,    # 1500 → 150.0 Wh → 0.15 kWh

# Use scale_energy_value() for automatic kWh conversion
energy_kwh = scale_energy_value("todayYielding", 90, to_kwh=True)  # 0.009 kWh
energy_wh = scale_energy_value("todayYielding", 90, to_kwh=False)  # 9.0 Wh
```

### 3. Battery Data

#### Battery Bank Aggregate

**Source**: `getBatteryInfo` header
**Constant**: `BATTERY_BANK_SCALING`

```python
# Aggregate voltage (÷10)
"vBat": ScaleFactor.SCALE_10,     # 530 → 53.0V

# Power (NO SCALING)
"pCharge": ScaleFactor.SCALE_NONE,    # 1045 → 1045W
"batPower": ScaleFactor.SCALE_NONE,

# Capacity (NO SCALING)
"maxBatteryCharge": ScaleFactor.SCALE_NONE,  # 840 → 840Ah
"remainCapacity": ScaleFactor.SCALE_NONE,
```

#### Individual Battery Module

**Source**: `getBatteryInfo.batteryArray`
**Constant**: `BATTERY_MODULE_SCALING`

```python
# Total voltage (÷100) - Different from aggregate!
"totalVoltage": ScaleFactor.SCALE_100,  # 5305 → 53.05V

# Current (÷10) - **CRITICAL: Not ÷100**
"current": ScaleFactor.SCALE_10,        # 60 → 6.0A

# Cell Voltages (÷1000) - Millivolts
"batMaxCellVoltage": ScaleFactor.SCALE_1000,  # 3317 → 3.317V
"batMinCellVoltage": ScaleFactor.SCALE_1000,  # 3315 → 3.315V

# Cell Temperatures (÷10)
"batMaxCellTemp": ScaleFactor.SCALE_10,  # 240 → 24.0°C
"batMinCellTemp": ScaleFactor.SCALE_10,  # 240 → 24.0°C

# Percentages (NO SCALING)
"soc": ScaleFactor.SCALE_NONE,   # 67 → 67%
"soh": ScaleFactor.SCALE_NONE,   # 100 → 100%
```

### 4. GridBOSS (MIDBOX) Data

**Source**: `getMidboxRuntime` endpoint
**Constant**: `GRIDBOSS_RUNTIME_SCALING`

**NOTE**: GridBOSS uses different scaling than standard inverters!

```python
# Voltages (÷10)
"gridVoltageR": ScaleFactor.SCALE_10,

# Currents (÷10) - Different from standard inverter!
"gridCurrentR": ScaleFactor.SCALE_10,   # NOT ÷100!

# Frequency (÷100)
"gridFrequency": ScaleFactor.SCALE_100,

# Power (NO SCALING)
"gridPower": ScaleFactor.SCALE_NONE,
```

### 5. Parameter Data

**Source**: `remoteRead` endpoint
**Constant**: `PARAMETER_SCALING`

```python
# Voltage Parameters (÷100)
"HOLD_BAT_VOLT_MAX_CHG": ScaleFactor.SCALE_100,

# Current Parameters (÷10)
"HOLD_MAX_CHG_CURR": ScaleFactor.SCALE_10,

# Frequency Parameters (÷100)
"HOLD_GRID_FREQ_HIGH_1": ScaleFactor.SCALE_100,

# Power/SOC Parameters (NO SCALING)
"HOLD_AC_CHARGE_POWER_CMD": ScaleFactor.SCALE_NONE,  # Watts
"HOLD_AC_CHARGE_SOC_LIMIT": ScaleFactor.SCALE_NONE,  # Percentage
```

## Helper Functions

### apply_scale()

Apply any scaling factor to a value.

```python
def apply_scale(value: int | float, scale_factor: ScaleFactor) -> float:
    """Apply scaling factor to a value."""

# Example
voltage = apply_scale(5100, ScaleFactor.SCALE_10)  # 510.0
```

### _get_scaling_for_field() (Internal)

**INTERNAL FUNCTION** - External users should use the convenience functions below.

Get the scaling factor for a specific field and data type.

```python
def _get_scaling_for_field(
    field_name: str,
    data_type: Literal["runtime", "energy", "battery_bank",
                       "battery_module", "gridboss", "overview", "parameter"]
) -> ScaleFactor:
    """Get the appropriate scaling factor for a field.

    This is an internal function. External users should use the data type-specific
    convenience functions instead (e.g., scale_runtime_value, scale_battery_value).
    """

# Example (internal use only)
scale = _get_scaling_for_field("vpv1", "runtime")
voltage = apply_scale(5100, scale)  # 510.0
```

### scale_runtime_value()

Convenience function for inverter runtime values.

```python
def scale_runtime_value(field_name: str, value: int | float) -> float:
    """Scale inverter runtime values."""

# Example
voltage = scale_runtime_value("vacr", 2411)  # 241.1
frequency = scale_runtime_value("fac", 5998)  # 59.98
power = scale_runtime_value("pinv", 1030)    # 1030.0 (no scaling)
```

### scale_battery_value()

Convenience function for battery module values.

```python
def scale_battery_value(field_name: str, value: int | float) -> float:
    """Scale battery module values."""

# Example
voltage = scale_battery_value("totalVoltage", 5305)         # 53.05
current = scale_battery_value("current", 60)                # 6.0
cell_v = scale_battery_value("batMaxCellVoltage", 3317)    # 3.317
temp = scale_battery_value("batMaxCellTemp", 240)          # 24.0
```

### scale_energy_value()

Convenience function for energy values with automatic kWh conversion.

```python
def scale_energy_value(
    field_name: str,
    value: int | float,
    to_kwh: bool = True
) -> float:
    """Scale energy values with optional kWh conversion."""

# Examples
kwh = scale_energy_value("todayYielding", 90, to_kwh=True)   # 0.009 kWh
wh = scale_energy_value("todayYielding", 90, to_kwh=False)   # 9.0 Wh
```

## Integration with Pydantic Models

### Using @property Decorators

**Recommended approach** for clean API:

```python
from pydantic import BaseModel
from pylxpweb.constants import scale_runtime_value

class InverterRuntime(BaseModel):
    """Runtime data with raw API values."""
    vpv1: int  # Raw value from API
    vacr: int
    fac: int

    @property
    def pv1_voltage(self) -> float:
        """PV1 voltage in volts."""
        return scale_runtime_value("vpv1", self.vpv1)

    @property
    def ac_voltage(self) -> float:
        """AC voltage in volts."""
        return scale_runtime_value("vacr", self.vacr)

    @property
    def frequency(self) -> float:
        """AC frequency in Hz."""
        return scale_runtime_value("fac", self.fac)

# Usage
runtime = InverterRuntime(vpv1=5100, vacr=2411, fac=5998)
print(f"PV1: {runtime.pv1_voltage}V")     # 510.0V
print(f"AC: {runtime.ac_voltage}V")       # 241.1V
print(f"Freq: {runtime.frequency}Hz")     # 59.98Hz
```

### Using Field Validators

Alternative approach for automatic scaling:

```python
from pydantic import BaseModel, field_validator
from pylxpweb.constants import scale_runtime_value

class InverterRuntime(BaseModel):
    """Runtime data with automatic scaling."""
    vpv1: float
    vacr: float
    fac: float

    @field_validator("vpv1", "vacr", mode="before")
    @classmethod
    def scale_voltage(cls, v: int, info) -> float:
        """Scale voltage fields."""
        return scale_runtime_value(info.field_name, v)

    @field_validator("fac", mode="before")
    @classmethod
    def scale_frequency(cls, v: int) -> float:
        """Scale frequency field."""
        return scale_runtime_value("fac", v)
```

## Common Pitfalls

### ❌ Pitfall 1: Wrong Voltage Scaling

```python
# WRONG - Using ÷100 for runtime voltages
voltage = raw_vpv1 / 100.0  # 5100 → 51.0V ❌

# CORRECT - Use ÷10
voltage = scale_runtime_value("vpv1", raw_vpv1)  # 5100 → 510.0V ✅
```

### ❌ Pitfall 2: Wrong Battery Current Scaling

```python
# WRONG - Using ÷100 for battery current
current = raw_current / 100.0  # 60 → 0.6A ❌

# CORRECT - Use ÷10
current = scale_battery_value("current", raw_current)  # 60 → 6.0A ✅
```

### ❌ Pitfall 3: Confusing Battery Voltage Scales

```python
# Battery BANK voltage (÷10)
bank_voltage = scale_battery_value("vBat", 530)  # 53.0V ✅

# Individual battery voltage (÷100)
battery_voltage = scale_battery_value("totalVoltage", 5305)  # 53.05V ✅

# Don't mix them up!
```

### ❌ Pitfall 4: GridBOSS vs Standard Inverter

```python
# Standard inverter current (÷100)
inv_current = scale_runtime_value("maxChgCurr", 6000)  # 60.0A

# GridBOSS current (÷10) - Different!
gb_current = get_scaling_for_field("gridCurrentR", "gridboss")
# Returns ScaleFactor.SCALE_10
```

## Testing Scaling

### Unit Test Example

```python
import pytest
from pylxpweb.constants import (
    scale_runtime_value,
    scale_battery_value,
    scale_energy_value,
    ScaleFactor,
)

def test_voltage_scaling():
    """Test voltage scaling correctness."""
    # PV voltage (÷10)
    assert scale_runtime_value("vpv1", 5100) == 510.0

    # AC voltage (÷10)
    assert scale_runtime_value("vacr", 2411) == 241.1

    # Battery voltage in runtime (÷10)
    assert scale_runtime_value("vBat", 530) == 53.0

    # Individual battery voltage (÷100)
    assert scale_battery_value("totalVoltage", 5305) == 53.05

def test_current_scaling():
    """Test current scaling correctness."""
    # Inverter current (÷100)
    assert scale_runtime_value("maxChgCurr", 6000) == 60.0

    # Battery current (÷10) - Critical difference!
    assert scale_battery_value("current", 60) == 6.0

def test_frequency_scaling():
    """Test frequency scaling correctness."""
    assert scale_runtime_value("fac", 5998) == 59.98
    assert scale_runtime_value("feps", 6001) == 60.01

def test_cell_voltage_scaling():
    """Test cell voltage scaling (millivolts)."""
    assert scale_battery_value("batMaxCellVoltage", 3317) == 3.317
    assert scale_battery_value("batMinCellVoltage", 3315) == 3.315

def test_energy_scaling():
    """Test energy scaling with kWh conversion."""
    # To kWh
    assert scale_energy_value("todayYielding", 90, to_kwh=True) == 0.009

    # To Wh
    assert scale_energy_value("todayYielding", 90, to_kwh=False) == 9.0

def test_no_scaling():
    """Test fields that don't need scaling."""
    assert scale_runtime_value("ppv1", 1030) == 1030.0  # Power
    assert scale_runtime_value("tinner", 39) == 39.0     # Temperature
    assert scale_runtime_value("soc", 71) == 71.0        # Percentage
```

### Integration Test with Real Data

```python
async def test_real_runtime_data():
    """Test scaling with actual API response."""
    runtime_data = {
        "vpv1": 5100,
        "vacr": 2411,
        "vBat": 530,
        "fac": 5998,
        "ppv1": 1030,
    }

    # Scale and verify
    assert scale_runtime_value("vpv1", runtime_data["vpv1"]) == 510.0
    assert scale_runtime_value("vacr", runtime_data["vacr"]) == 241.1
    assert scale_runtime_value("vBat", runtime_data["vBat"]) == 53.0
    assert scale_runtime_value("fac", runtime_data["fac"]) == 59.98
    assert scale_runtime_value("ppv1", runtime_data["ppv1"]) == 1030.0
```

## Performance Considerations

### Efficient Lookups

The scaling system uses dictionary lookups with O(1) complexity:

```python
# Fast - single dictionary lookup
voltage = scale_runtime_value("vpv1", 5100)

# Also fast - direct scaling
voltage = apply_scale(5100, ScaleFactor.SCALE_10)
```

### Caching (if needed)

For high-frequency operations, consider caching scaled values:

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def cached_scale(field_name: str, value: int, data_type: str) -> float:
    """Cached scaling function."""
    return get_scaling_for_field(field_name, data_type)
```

## Maintenance Guide

### Adding New Fields

1. Identify the data source (runtime, energy, battery, etc.)
2. Determine the scaling factor from API documentation or samples
3. Add to appropriate scaling dictionary in `constants.py`
4. Add tests

Example:

```python
# 1. Check API response
# raw_value: 4200, expected: 42.0V → divide by 100

# 2. Add to INVERTER_RUNTIME_SCALING
"newVoltageField": ScaleFactor.SCALE_100,

# 3. Add test
def test_new_voltage_field():
    assert scale_runtime_value("newVoltageField", 4200) == 42.0
```

### Updating Scaling Factors

If API scaling changes (rare):

1. Update the scaling constant
2. Update affected tests
3. Document the change in CHANGELOG
4. Add migration notes if needed

## Reference

- **Source Code**: `src/pylxpweb/constants.py` (lines 1186-1637)
- **Analysis**: `docs/claude/PARAMETER_MAPPING_ANALYSIS.md`
- **EG4 Monitor**: `research/eg4_web_monitor/custom_components/eg4_web_monitor/utils.py`
- **Sample Data**: `research/eg4_web_monitor/.../samples/`

---

## Cache Invalidation

The `LuxpowerClient` automatically invalidates its response cache when the hour changes. This helps ensure fresh data is fetched around midnight when daily values reset.

```python
# Cache is automatically cleared when hour boundary is crossed
# This is handled internally by the client
```

---

## Energy Value Handling

### Daily vs Lifetime Sensors

| Type | Example Properties | Reset Behavior |
|------|-------------------|----------------|
| **Daily** | `total_energy_today`, `energy_today_charging` | Resets at midnight (API-controlled) |
| **Lifetime** | `total_energy_lifetime`, `energy_lifetime_charging` | Never resets |

### Home Assistant Integration

For Home Assistant integrations using pylxpweb:

- Use `SensorStateClass.TOTAL_INCREASING` for all energy sensors
- Home Assistant automatically handles daily resets and monotonic tracking
- No additional logic needed in the integration

```python
# Example Home Assistant sensor definition
@property
def state_class(self) -> SensorStateClass:
    return SensorStateClass.TOTAL_INCREASING
```

---

## References

- **Source Code**: `src/pylxpweb/constants/scaling.py`
- **API Documentation**: `docs/api/LUXPOWER_API.md`

---

## Changelog

- **2025-11-26**: Removed monotonic enforcement documentation
  - pylxpweb no longer implements monotonic enforcement
  - Home Assistant's TOTAL_INCREASING handles resets automatically
- **2025-11-21**: Initial scaling guide
