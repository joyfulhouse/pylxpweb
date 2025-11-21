# Data Scaling, Date Boundaries, and Monotonic Values Guide

**Version**: 2.0.0
**Last Updated**: 2025-11-21
**Purpose**: Comprehensive guide to data scaling, date boundary handling, and monotonically increasing values in pylxpweb

## Overview

The Luxpower/EG4 API exhibits three critical behaviors that require special handling:

1. **Variable Scaling Factors**: Raw integer values must be scaled with different divisors (÷10, ÷100, ÷1000)
2. **Date Boundary Resets**: Daily energy values reset to 0 at midnight (station timezone)
3. **API Rounding Issues**: Cached data can cause apparent backwards movement near boundaries

This guide explains:
- The centralized scaling system in `src/pylxpweb/constants.py`
- Date boundary detection and handling strategies (from EG4 Web Monitor integration)
- Monotonic value enforcement to prevent backwards movement

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

### get_scaling_for_field()

Get the scaling factor for a specific field and data type.

```python
def get_scaling_for_field(
    field_name: str,
    data_type: Literal["runtime", "energy", "battery_bank",
                       "battery_module", "gridboss", "overview", "parameter"]
) -> ScaleFactor:
    """Get the appropriate scaling factor for a field."""

# Example
scale = get_scaling_for_field("vpv1", "runtime")
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

## Date Boundary Handling

### Problem Statement

At midnight (station timezone), daily energy values reset to 0. However:

1. **API Caching**: API may return stale data for several minutes after midnight
2. **Timezone Awareness**: Must use station timezone, not UTC or system timezone
3. **Monotonic Enforcement**: Home Assistant expects `total_increasing` sensors never to decrease

### Implementation from WebMonitor Integration

The EG4 Web Monitor integration successfully implements a **two-tier approach**:

#### Tier 1: Timezone-Aware Date Detection

From `research/eg4_web_monitor/custom_components/eg4_web_monitor/sensor.py:52-81`:

```python
def _get_current_date(coordinator) -> Optional[str]:
    """Get current date in station's timezone as YYYY-MM-DD string."""
    try:
        # Get timezone from station data
        if coordinator.data and "station" in coordinator.data:
            tz_str = coordinator.data["station"].get("timezone")  # e.g., "GMT -8"
            if tz_str and "GMT" in tz_str:
                offset_str = tz_str.replace("GMT", "").strip()
                offset_hours = int(offset_str)
                tz = timezone(timedelta(hours=offset_hours))
                return datetime.now(tz).strftime("%Y-%m-%d")

        # Fallback to UTC
        return datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d")
    except Exception:
        return None  # Allow resets when we can't determine date
```

#### Tier 2: Lifetime vs Daily Sensor Classification

```python
# Sensors that should never decrease (lifetime values)
LIFETIME_SENSORS = {
    "total_energy",         # Lifetime production
    "yield_lifetime",       # Lifetime yield
    "discharging_lifetime", # Lifetime discharge
    "charging_lifetime",    # Lifetime charge
    "consumption_lifetime", # Lifetime consumption
    "grid_export_lifetime", # Lifetime export
    "grid_import_lifetime", # Lifetime import
    "cycle_count",          # Battery cycle count
}

# All other total_increasing sensors reset at date boundaries
```

#### Tier 3: Monotonic State Tracking

```python
class EG4InverterSensor:
    def __init__(self, ...):
        # Instance-level state tracking
        self._last_valid_state: Optional[float] = None
        self._last_update_date: Optional[str] = None

    @property
    def native_value(self) -> Any:
        current_value = float(raw_value)
        current_date = _get_current_date(self.coordinator)

        # Check if lifetime sensor
        is_lifetime = self._sensor_key in LIFETIME_SENSORS

        # Detect date boundary crossing
        date_changed = False
        if not is_lifetime and current_date and self._last_update_date:
            date_changed = current_date != self._last_update_date

        # Force reset to 0 on date boundary
        if date_changed:
            logger.info(
                "Date boundary crossed from %s to %s, "
                "forcing reset from %.2f to 0.0 (API reported %.2f)",
                self._last_update_date, current_date,
                self._last_valid_state, current_value
            )
            self._last_valid_state = 0.0
            self._last_update_date = current_date
            return 0.0

        # Prevent decrease within same day
        if self._last_valid_state is not None:
            if current_value < self._last_valid_state:
                # Allow reset to 0 for non-lifetime sensors
                if not is_lifetime and current_value == 0:
                    self._last_valid_state = current_value
                    self._last_update_date = current_date
                    return current_value

                # Maintain previous value
                return self._last_valid_state

        # Update and return
        self._last_valid_state = current_value
        self._last_update_date = current_date
        return current_value
```

### Key Behaviors

| Sensor Type | Date Change | API Reports Lower | API Reports 0 | API Reports Higher |
|-------------|-------------|-------------------|---------------|-------------------|
| **Lifetime** | Maintain | Maintain previous | Maintain previous | Accept new value |
| **Daily** | Force reset to 0 | Maintain previous | Accept reset | Accept new value |

**Critical Insight**: The integration **forces a reset to 0** on date boundary detection, regardless of what the API reports. This prevents:
- Stale cached data showing yesterday's final value
- API rounding issues causing small backwards movements
- Timezone-related edge cases

### Example Failure Scenario

```
23:58:00 - API returns 895 (÷10 = 89.5 kWh) - Cache hit
23:59:30 - API returns 895 (÷10 = 89.5 kWh) - Cache hit
00:00:30 - API returns 2 (÷10 = 0.2 kWh)   - New day starts
00:01:00 - API returns 895 (÷10 = 89.5 kWh) - Cache stale! Shows yesterday's data
```

With date boundary detection:
```
00:00:30 - Date boundary detected → Force 0.0 kWh (ignore API's 0.2)
00:01:00 - API reports 89.5 kWh → Reject (< previous 0.0 is impossible)
00:02:00 - API reports 0.5 kWh → Accept (new fresh data)
```

---

## Cache Invalidation Strategy

### Problem: Hour and Date Boundaries

The API uses **aggressive caching** with TTLs that don't align with natural boundaries:
- **Runtime data**: ~20 seconds
- **Energy data**: ~2-5 minutes
- **Parameter data**: ~2 minutes

### WebMonitor Solution: Proactive Cache Invalidation

From `coordinator.py:1525-1573`:

```python
def _should_invalidate_cache(self) -> bool:
    """Check if cache invalidation is needed before top of hour."""
    now = dt_util.utcnow()

    # First run - invalidate if within 5 minutes of top of hour
    if self._last_cache_invalidation is None:
        minutes_to_hour = 60 - now.minute
        return bool(minutes_to_hour <= 5)

    # Check if we've crossed into a new hour
    last_hour = self._last_cache_invalidation.hour
    current_hour = now.hour
    if current_hour != last_hour:
        return True

    # If within 5 minutes of next hour and haven't invalidated recently
    minutes_to_hour = 60 - now.minute
    time_since_last = now - self._last_cache_invalidation
    return bool(minutes_to_hour <= 5 and time_since_last >= timedelta(minutes=10))

def _invalidate_all_caches(self) -> None:
    """Invalidate all caches to ensure fresh data when date changes."""
    if hasattr(self.api, "clear_cache"):
        self.api.clear_cache()
    if hasattr(self.api, "_device_cache"):
        self.api._device_cache.clear()

    self._last_cache_invalidation = dt_util.utcnow()
    logger.info("Successfully invalidated all caches to prevent date rollover issues")
```

**When Cache Invalidation Runs**:

| Scenario | Minutes to Hour | Last Invalidation | Action |
|----------|----------------|-------------------|--------|
| First run | 3 | None | **Invalidate** |
| First run | 7 | None | Skip |
| Hour change | Any | < 1 hour ago | **Invalidate** |
| Within 5 min | 3 | 11 minutes ago | **Invalidate** |
| Within 5 min | 4 | 3 minutes ago | Skip (too recent) |

**Why 5 Minutes Before Hour?**:
- Gives time for multiple refresh cycles
- Ensures fresh data at 00:00 when daily reset happens
- Accounts for coordinator update interval (30 seconds)

---

## Implementation Recommendations for pylxpweb

### 1. Add Date Boundary Detection

Add to `Station` class:

```python
from datetime import datetime, timezone, timedelta
from typing import Optional

class Station:
    def __init__(self, ...):
        self.timezone: str = timezone  # "GMT -8"

    def get_current_date(self) -> Optional[str]:
        """Get current date in station's timezone (YYYY-MM-DD)."""
        try:
            if self.timezone and "GMT" in self.timezone:
                offset_str = self.timezone.replace("GMT", "").strip()
                offset_hours = int(offset_str)
                tz = timezone(timedelta(hours=offset_hours))
                return datetime.now(tz).strftime("%Y-%m-%d")
            return datetime.utcnow().strftime("%Y-%m-%d")
        except Exception:
            return None
```

### 2. Add Lifetime Sensor Classification

Add to `constants.py`:

```python
# Sensors that should never decrease (truly monotonic)
LIFETIME_ENERGY_SENSORS = {
    "totalYielding",        # Lifetime production
    "eTotal",               # Total energy lifetime
    "totalDischarging",     # Lifetime discharge
    "totalCharging",        # Lifetime charge
}

# Sensors that reset at date boundaries
DAILY_ENERGY_SENSORS = {
    "todayYielding",        # Today's production
    "eToday",               # Today's energy
    "todayDischarging",     # Today's discharge
    "todayCharging",        # Today's charge
}
```

### 3. Apply Monotonic Logic to Energy Properties

Modify `BaseInverter`:

```python
class BaseInverter:
    def __init__(self, ...):
        self._last_today_energy: Optional[float] = None
        self._last_energy_date: Optional[str] = None

    def _should_reset_daily_energy(self) -> bool:
        """Check if daily energy should reset based on date boundary."""
        if not hasattr(self, '_client') or not self._client.station:
            return False

        current_date = self._client.station.get_current_date()
        if current_date is None:
            return False

        if self._last_energy_date is None:
            self._last_energy_date = current_date
            return False

        if current_date != self._last_energy_date:
            self._last_energy_date = current_date
            return True

        return False

    @property
    def total_energy_today(self) -> float:
        """Get total energy produced today in kWh with monotonic enforcement."""
        if self.energy is None:
            return 0.0

        raw_value = float(getattr(self.energy, "todayYielding", 0))
        current_value_kwh = raw_value / 1000.0  # Wh to kWh

        # Check for date boundary reset
        if self._should_reset_daily_energy():
            _LOGGER.info(
                "Inverter %s: Date boundary detected, resetting daily energy",
                self.serial_number
            )
            self._last_today_energy = 0.0
            return 0.0

        # Enforce monotonic behavior within same day
        if hasattr(self, '_last_today_energy') and self._last_today_energy is not None:
            if current_value_kwh < self._last_today_energy:
                _LOGGER.debug(
                    "Inverter %s: Rejecting energy decrease (%.2f -> %.2f), maintaining %.2f",
                    self.serial_number,
                    self._last_today_energy,
                    current_value_kwh,
                    self._last_today_energy
                )
                return self._last_today_energy

        self._last_today_energy = current_value_kwh
        return current_value_kwh
```

### 4. Add Cache Invalidation to LuxpowerClient

```python
class LuxpowerClient:
    def __init__(self, ...):
        self._last_cache_clear: Optional[datetime] = None

    def should_clear_cache_for_boundary(self) -> bool:
        """Check if cache should be cleared for hour/date boundary."""
        now = datetime.utcnow()
        minutes_to_hour = 60 - now.minute

        if minutes_to_hour > 5:
            return False

        if self._last_cache_clear is None:
            return True

        time_since_clear = now - self._last_cache_clear
        return time_since_clear >= timedelta(minutes=10)

    def clear_all_caches(self) -> None:
        """Clear all API response caches."""
        # Clear endpoint caches
        self.api.devices._response_cache.clear()
        self.api.plants._response_cache.clear()

        self._last_cache_clear = datetime.utcnow()
        _LOGGER.info("Cleared all API caches at hour boundary")
```

---

## Testing Recommendations

### Unit Tests for Date Boundary Logic

```python
def test_date_boundary_reset():
    """Test that daily energy resets at midnight."""
    inverter = GenericInverter(client, "1234567890", "18KPV")
    inverter._last_energy_date = "2025-11-20"
    inverter._last_today_energy = 45.5

    # Simulate date change
    inverter._last_energy_date = "2025-11-21"
    assert inverter.total_energy_today == 0.0

def test_monotonic_within_day():
    """Test that energy never decreases within same day."""
    inverter = GenericInverter(client, "1234567890", "18KPV")
    inverter._last_energy_date = "2025-11-20"
    inverter._last_today_energy = 45.5

    # API returns lower value (cache issue)
    inverter.energy = EnergyInfo(todayYielding=450)  # 45.0 kWh
    assert inverter.total_energy_today == 45.5  # Maintains previous

def test_lifetime_never_decreases():
    """Test that lifetime energy never decreases."""
    inverter = GenericInverter(client, "1234567890", "18KPV")
    inverter._last_lifetime_energy = 12345.6

    # API returns lower value
    inverter.energy = EnergyInfo(totalYielding=123000)  # 12300.0 kWh
    assert inverter.total_energy_lifetime == 12345.6  # Maintains
```

---

## Summary of Key Takeaways

### Critical Patterns from WebMonitor

| Feature | Implementation | Benefit |
|---------|---------------|---------|
| **Date Detection** | Station timezone parsing | Accurate midnight detection |
| **Forced Reset** | Override API on date boundary | Prevents stale data issues |
| **Monotonic Tracking** | Per-sensor instance state | Prevents backwards movement |
| **Cache Clearing** | 5-min pre-hour invalidation | Fresh data at boundaries |
| **Lifetime Classification** | Explicit sensor categorization | Correct reset behavior |

### For pylxpweb v0.3.0

1. **Scaling**: Already implemented with centralized constants ✅
2. **Date Boundaries**: Implement timezone-aware date detection 🔨
3. **Monotonic Values**: Track last valid state, prevent decreases 🔨
4. **Cache Invalidation**: Clear caches proactively at hour boundaries 🔨
5. **Lifetime Classification**: Distinguish lifetime vs daily sensors 🔨

### References

- **WebMonitor Coordinator**: `research/eg4_web_monitor/custom_components/eg4_web_monitor/coordinator.py`
- **WebMonitor Sensor**: `research/eg4_web_monitor/custom_components/eg4_web_monitor/sensor.py`
- **WebMonitor Constants**: `research/eg4_web_monitor/custom_components/eg4_web_monitor/const.py`
- **API Documentation**: `docs/api/LUXPOWER_API.md`

---

## Version History

- **2.0.0** (2025-11-21): Added date boundary and monotonic value handling
  - Date boundary detection with timezone awareness
  - Monotonic value enforcement patterns
  - Cache invalidation strategies
  - Implementation recommendations from WebMonitor integration
- **1.0.0** (2025-11-21): Initial centralized scaling system
  - Comprehensive scaling dictionaries for all data types
  - Helper functions for common operations
  - Full documentation and test examples
