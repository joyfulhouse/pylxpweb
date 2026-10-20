# Device Types and Feature Detection

This document describes the device type identification system in pylxpweb and how features are detected and exposed based on the inverter model.

## Device Type Concepts

There are two different "device type" identifiers in the Luxpower/EG4 ecosystem:

### 1. API `deviceType` (Web API Category)

The web API uses `deviceType` to categorize devices for routing data requests:

| `deviceType` | Category | Description |
|--------------|----------|-------------|
| **6** | Inverter | Standard inverters (all models) |
| **9** | GridBOSS | MID device / parallel group controller |

This value is returned in API responses like `inverterOverview/list` and determines which data endpoints to use.

### 2. `HOLD_DEVICE_TYPE_CODE` (Register 19)

This is the firmware-level model identifier stored in register 19. It identifies the specific inverter model/variant:

| Code | Model Family | Example Models |
|------|--------------|----------------|
| **54** | EG4 Off-Grid | 12000XP, 6000XP |
| **38** | EG4 Off-Grid | 6000XP variant |
| **2102** | EG4 Off-Grid | Reported 12000XP variant (#659) |
| **2092** | EG4 Hybrid (PV Series) | 18kPV, 12kPV |
| **10284** | EG4 Hybrid (FlexBOSS Series) | FlexBOSS21, FlexBOSS18 |
| **12** | Luxpower | LXP-EU 12K |
| **20** | Luxpower | GEN-LB-EU 3.6K (#612) |
| **44** | Luxpower | LXP-LB-BR 10K |
| **50** | GridBOSS (MID) | GridBOSS |

Codes 20 and 2102 are exact identifications from
[eg4_web_monitor #612](https://github.com/joyfulhouse/eg4_web_monitor/issues/612)
and [#659](https://github.com/joyfulhouse/eg4_web_monitor/issues/659). The raw
register word is retained; these reports do not establish a general high-byte
mask. In particular, 2092 (`0x082c`, EG4 Hybrid) and 44 (`0x002c`, Luxpower)
share a low byte but belong to different families. Unknown variants stay unknown.
The code-20 power-rating encoding is unverified, so no numeric rating is inferred.
Identification reuses existing family behavior and is not new local-write validation.

### 3. `HOLD_MODEL_powerRating` (from HOLD_MODEL register)

Within each device type code family, the `powerRating` field differentiates specific models:

| Device Type Code | powerRating | Model |
|------------------|-------------|-------|
| 2092 | 2 | 12KPV |
| 2092 | 6 | 18KPV |
| 10284 | 9 | FlexBOSS18 |
| 10284 | 8 | FlexBOSS21 |

### 4. Other Register Fields

| Field | Description |
|-------|-------------|
| `BIT_DEVICE_TYPE_ODM` | OEM/ODM branding (4 = EG4 branded) |
| `BIT_MACHINE_TYPE` | Unknown purpose (0 on PV Series, 1 on FlexBOSS) |
| `FUNC_MIDBOX_EN` | User config: GridBOSS enabled in parallel settings |
| `HOLD_SET_COMPOSED_PHASE` | User config: System type (1-phase, 3-phase, 2x208, slave) |

> **Note**: `BIT_MACHINE_TYPE` and `FUNC_MIDBOX_EN` are NOT reliable model differentiators.
> Phase configuration is a user setting, not a hardware limitation.

## Model Families

### EG4 Off-Grid Series (EG4_OFFGRID)

**Device Type Code:** 54

**Target Market:** US residential off-grid (split-phase 120V/240V)

**Key Features:**
- Split-phase grid support (L1/L2/N)
- Off-grid capable (no grid sellback)
- Discharge recovery hysteresis (SOC and voltage lag)
- Quick charge minute setting

**Models:** 12000XP, 6000XP

**Unique Parameters:**
- `HOLD_DISCHG_RECOVERY_LAG_SOC` - SOC hysteresis percentage
- `HOLD_DISCHG_RECOVERY_LAG_VOLT` - Voltage hysteresis (V, scaled ÷10)
- `SNA_HOLD_QUICK_CHARGE_MINUTE` - Quick charge duration
- `OFF_GRID_HOLD_EPS_VOLT_SET` - EPS output voltage
- `OFF_GRID_HOLD_EPS_FREQ_SET` - EPS output frequency

**Sample Models:**
- 12000XP: 12kW, device type code 54, HOLD_MODEL 0x90AC1

### EG4 Hybrid Series (EG4_HYBRID)

**Device Type Codes:** 2092 (PV Series), 10284 (FlexBOSS Series)

**Target Market:** US residential/commercial grid-tied hybrid

**Key Features:**
- Grid sellback capable
- Split-phase grid support (L1/L2) - default configuration
- Configurable system types: 1 Phase Master, 3 Phase Master, 2x208 Master, Slave
- Parallel operation support (with optional GridBOSS)
- Volt-Watt curve control
- Grid peak shaving
- DRMS (Demand Response Management) support

#### PV Series (Device Type Code: 2092)

| powerRating | Model | Power | Firmware Prefix |
|-------------|-------|-------|-----------------|
| 2 | 12KPV | 12kW | EAAB-* |
| 6 | 18KPV | 18kW | EAAB-* |

#### FlexBOSS Series (Device Type Code: 10284)

| powerRating | Model | Power | Firmware Prefix |
|-------------|-------|-------|-----------------|
| 9 | FlexBOSS18 | 18kW | FAAB-* |
| 8 | FlexBOSS21 | 21kW | FAAB-* |

**Unique Parameters:**
- `HOLD_VW_V1` through `HOLD_VW_V4` - Volt-Watt curve voltage points
- `HOLD_VW_P1` through `HOLD_VW_P4` - Volt-Watt curve power points
- `_12K_HOLD_GRID_PEAK_SHAVING_POWER` - Peak shaving power limit
- `HOLD_PARALLEL_REGISTER` - Parallel operation settings
- `HOLD_SET_COMPOSED_PHASE` - System type configuration

**Sample Data:**
| Model | Device Type Code | powerRating | HOLD_MODEL | reg0 | reg1 | Firmware |
|-------|------------------|-------------|------------|------|------|----------|
| 12KPV | 2092 | 2 | 0x98640 | 0x8640 | 0x0009 | EAAB-2525 |
| 18KPV | 2092 | 6 | 0x986C0 | 0x86C0 | 0x0009 | EAAB-2525 |
| FlexBOSS21 | 10284 | 8 | 0x1098600 | 0x8600 | 0x0109 | FAAB-2525 |
| FlexBOSS21 | 10284 | 8 | 0x1098200 | 0x8200 | 0x0109 | FAAB-2525 |
| FlexBOSS18 | 10284 | 9 | 0x1098620 | 0x8620 | 0x0109 | FAAB-2525 |

> **Note**: FlexBOSS21 has multiple HOLD_MODEL values (0x1098200 vs 0x1098600)
> due to different `lithiumType` configurations. The powerRating extraction is
> consistent across all variants because it uses only bits 5-7 of the low byte.

### Luxpower Series (LXP)

**Device Type Codes:** 12, 44, and others

**Target Markets:** Europe (LXP-EU), Brazil (LXP-LB-BR), Low-voltage DC (LXP-LV)

All Luxpower-branded inverters share the same register layout and are grouped into a single `LXP` family.

**Key Features:**
- EU grid compliance (some models)
- Three-phase capable (some models)
- Parallel operation support
- Volt-Watt curve control (some models)
- DRMS support (some models)
- Off-grid capable

**Unique Parameters:**
- `HOLD_EU_GRID_CODE` - EU grid compliance code
- `HOLD_EU_COUNTRY_CODE` - Country-specific settings

**Models:**

| Model | Device Type Code | Target Market | Notes |
|-------|------------------|---------------|-------|
| LXP-EU 12K | 12 | Europe | 230V/400V, 50Hz |
| LXP-LB-BR 10K | 44 | Brazil | 48V battery bus, firmware `EAAB-*` |
| LXP-LV 6048 | TBD | Global | Low-voltage DC (48V nominal) |

**Sample Models:**
- LXP-EU 12K: 12kW, device type code 12, HOLD_MODEL 0x19AC0 (reg0=0x9AC0, reg1=0x0001)
- LXP-US 10K: 10kW, device type code 44, HOLD_MODEL 0x99A85 (reg0=0x9A85, reg1=0x0009)

> **Note**: The LXP-LV 6048 and similar low-voltage models have not had their device type code discovered yet. When connected, they will use `LXP` family register maps but may show as `UNKNOWN` family until mapped.

### GridBOSS (MID Controller)

**Device Type Code:** 50

**API Device Type:** 9 (separate from standard inverters which use deviceType=6)

**Target Market:** Parallel group management and grid interconnection

**Key Features:**
- Main Interconnect Device (MID) controller
- Parallel group coordination
- Smart load port management (4 ports)
- AC coupling support
- Load shedding control
- UPS functionality
- Generator integration

**Unique Parameters:**
- `MIDBOX_HOLD_SMART_PORT_MODE` - Smart port configuration
- `BIT_MIDBOX_SP_MODE_1/2/3/4` - Individual port mode settings
- `FUNC_SMART_LOAD_EN_1/2/3/4` - Smart load enables per port
- `FUNC_SHEDDING_MODE_EN_1/2/3/4` - Load shedding per port
- `FUNC_AC_COUPLE_EN_1/2/3/4` - AC coupling per port
- `MIDBOX_HOLD_UPS_*` registers - UPS configuration
- `MIDBOX_HOLD_LOAD_*` registers - Load management

**Firmware Prefix:** `IAAB-` (e.g., IAAB-1600)

**Sample Models:**
- GridBOSS: device type code 50, HOLD_MODEL 0x400902C0

> **Note**: GridBOSS devices are handled separately from standard inverters in the API. They use `deviceType=9` for API routing and have their own runtime endpoint (`getMidboxRuntime`).

## HOLD_MODEL Register Decoding

The `HOLD_MODEL` register (registers 0-1) contains a 32-bit bitfield with hardware configuration:

### Register Layout

The 32-bit value spans two 16-bit Modbus holding registers:

- **reg0** (address 0): Low word
- **reg1** (address 1): High word
- Combined: `(reg1 << 16) | reg0`

### Power Rating Extraction (Verified)

The `power_rating` field is extracted using a two-register formula:

```python
# Base rating: bits 5-7 of the low byte of reg0
power_rating = ((reg0 & 0xFF) >> 5) & 0x7

# FlexBOSS family offset: bit 8 of reg1 adds 8
if reg1 & 0x100:
    power_rating += 8
```

This produces values that exactly match the Cloud API's `HOLD_MODEL_powerRating`
decomposition. Verified against 13 devices across all families.

### Other Fields (from Cloud API Decomposition)

The Cloud API decomposes the 32-bit HOLD_MODEL into named fields. The
following are derived from Cloud API diagnostic data; approximate bit
positions are shown for reference:

| Field | Cloud API Name | Description |
|-------|----------------|-------------|
| `battery_type` | `HOLD_MODEL_batteryType` | 0=Lead-acid, 1=Lithium primary, 2=Hybrid |
| `lithium_type` | `HOLD_MODEL_lithiumType` | Lithium protocol (1=Standard, 2=EG4, 6=EU) |
| `power_rating` | `HOLD_MODEL_powerRating` | Power code (see extraction above) |
| `us_version` | `HOLD_MODEL_usVersion` | 1=US market, 0=EU/other (bit 0 of reg1) |
| `measurement` | `HOLD_MODEL_measurement` | Measurement unit type |
| `wireless_meter` | `HOLD_MODEL_wirelessMeter` | Wireless CT meter flag |
| `meter_type` | `HOLD_MODEL_meterType` | CT meter type |
| `meter_brand` | `HOLD_MODEL_meterBrand` | CT meter brand |
| `rule` | `HOLD_MODEL_rule` | Grid compliance rule |

> **Note**: Only `power_rating` and `us_version` bit positions have been
> verified against raw register data. Other field bit positions are inferred
> from Cloud API values and may not be exact.

### Power Rating Code Mapping

The `power_rating` field is an internal code that varies by device family:

**EG4 Off-Grid Series (device type 54):**
| Code | kW | Model |
|------|-----|-------|
| 6 | 12 | 12000XP |
| 8 | 18 | 18000XP |

**EG4 PV Series (device type 2092):**
| Code | kW | Model |
|------|-----|-------|
| 2 | 12 | 12KPV |
| 6 | 18 | 18KPV |

**EG4 FlexBOSS Series (device type 10284):**
| Code | kW | Model |
|------|-----|-------|
| 8 | 21 | FlexBOSS21 |
| 9 | 18 | FlexBOSS18 |

> **Note**: FlexBOSS power ratings are 8+ because bit 8 of reg1 is set for this
> family, adding an offset of 8 to the base value (0→8 for FB21, 1→9 for FB18).

> **Important**: Use `InverterModelInfo.get_power_rating_kw(device_type_code)` for accurate
> family-aware power rating. The `power_rating_kw` property only works for EG4 Off-Grid series.

### Example Decoding

Power rating extraction: `base = ((reg0 & 0xFF) >> 5) & 0x7`, then `+8 if reg1 & 0x100`.

**12KPV (reg0=0x8640, reg1=0x0009):**
```
HOLD_MODEL = 0x98640
power_rating = ((0x40 >> 5) & 0x7) = 2, reg1 bit 8 = 0 → 2 (12kW)
us_version = 1 (US market)
HOLD_DEVICE_TYPE_CODE = 2092 (PV Series)
Cloud API: batteryType=2, lithiumType=1
```

**18KPV (reg0=0x86C0, reg1=0x0009):**
```
HOLD_MODEL = 0x986C0
power_rating = ((0xC0 >> 5) & 0x7) = 6, reg1 bit 8 = 0 → 6 (18kW)
us_version = 1 (US market)
HOLD_DEVICE_TYPE_CODE = 2092 (PV Series)
Cloud API: batteryType=2, lithiumType=1
```

**FlexBOSS21 (reg0=0x8600, reg1=0x0109):**
```
HOLD_MODEL = 0x1098600
power_rating = ((0x00 >> 5) & 0x7) = 0, reg1 bit 8 = 1 → 0+8 = 8 (21kW)
us_version = 1 (US market)
HOLD_DEVICE_TYPE_CODE = 10284 (FlexBOSS Series)
Cloud API: batteryType=2, lithiumType=1
```

**FlexBOSS18 (reg0=0x8620, reg1=0x0109):**
```
HOLD_MODEL = 0x1098620
power_rating = ((0x20 >> 5) & 0x7) = 1, reg1 bit 8 = 1 → 1+8 = 9 (18kW)
us_version = 1 (US market)
HOLD_DEVICE_TYPE_CODE = 10284 (FlexBOSS Series)
Cloud API: batteryType=2, lithiumType=1
```

**SNA 12KUS (reg0=0x0AC1, reg1=0x0009):**
```
HOLD_MODEL = 0x90AC1
power_rating = ((0xC1 >> 5) & 0x7) = 6, reg1 bit 8 = 0 → 6
us_version = 1 (US market)
HOLD_DEVICE_TYPE_CODE = 54 (EG4 Off-Grid)
Cloud API: batteryType=1, lithiumType=2
```

**LXP-EU 12K (reg0=0x9AC0, reg1=0x0001):**
```
HOLD_MODEL = 0x19AC0
power_rating = ((0xC0 >> 5) & 0x7) = 6, reg1 bit 8 = 0 → 6
us_version = 0 (EU market)
HOLD_DEVICE_TYPE_CODE = 12 (Luxpower)
Cloud API: batteryType=0, lithiumType=6
```

**LXP-US 10K (reg0=0x9A85, reg1=0x0009):**
```
HOLD_MODEL = 0x99A85
power_rating = ((0x85 >> 5) & 0x7) = 4, reg1 bit 8 = 0 → 4
us_version = 1 (US market)
HOLD_DEVICE_TYPE_CODE = 44 (Luxpower)
Cloud API: batteryType=1, lithiumType=2
```

### Validated Device Summary

All 13 known device samples produce correct `powerRating` values using the
two-register extraction formula:

| Model | Device Type | reg0 | reg1 | Base | +8? | Rating | Cloud Match |
|-------|-------------|------|------|------|-----|--------|-------------|
| 12KPV | 2092 | 0x8640 | 0x0009 | 2 | No | 2 | Yes |
| 18KPV | 2092 | 0x86C0 | 0x0009 | 6 | No | 6 | Yes |
| FlexBOSS21 | 10284 | 0x8600 | 0x0109 | 0 | Yes | 8 | Yes |
| FlexBOSS21 | 10284 | 0x8200 | 0x0109 | 0 | Yes | 8 | Yes |
| FlexBOSS18 | 10284 | 0x8620 | 0x0109 | 1 | Yes | 9 | Yes |
| SNA 12KUS | 54 | 0x0AC1 | 0x0009 | 6 | No | 6 | Yes |
| LXP-EU 12K | 12 | 0x9AC0 | 0x0001 | 6 | No | 6 | Yes |
| LXP-EU 12K | 12 | 0x9AC0 | 0x0001 | 6 | No | 6 | Yes |
| LXP-US 10K | 44 | 0x9A85 | 0x0009 | 4 | No | 4 | Yes |
| GridBOSS | 50 | 0x02C0 | 0x4009 | 6 | No | 6 | N/A |
| GridBOSS | 50 | 0x02C0 | 0x4009 | 6 | No | 6 | N/A |
| GridBOSS | 50 | 0x02C0 | 0x4009 | 6 | No | 6 | N/A |

## Feature Detection System

The feature detection system uses a multi-layer approach:

### Layer 1: Device Type Code Mapping

The `HOLD_DEVICE_TYPE_CODE` value maps to a model family with known default features:

```python
from pylxpweb.devices.inverters import get_inverter_family, InverterFamily

family = get_inverter_family(54)  # Returns InverterFamily.SNA
```

### Layer 2: Model Info Decoding

The `HOLD_MODEL` register is decoded to extract hardware configuration:

```python
from pylxpweb.devices.inverters import InverterModelInfo

model_info = InverterModelInfo.from_raw(0x90AC1)
print(model_info.power_rating_kw)  # 12
print(model_info.us_version)  # True
print(model_info.lithium_protocol_name)  # "EG4"
```

### Layer 3: Runtime Probing

Optional features are detected by checking for specific parameters:

```python
# After detect_features() call
if "HOLD_DISCHG_RECOVERY_LAG_SOC" in inverter.parameters:
    # SNA discharge recovery hysteresis is available
    pass
```

### Layer 4: Property-Based API

Clean, type-safe access to detected features:

```python
await inverter.detect_features()

# Check capabilities
if inverter.supports_split_phase:
    print("Split-phase grid configuration")

if inverter.supports_discharge_recovery_hysteresis:
    lag_soc = inverter.discharge_recovery_lag_soc
    print(f"Discharge recovery SOC lag: {lag_soc}%")

# Access model info
print(f"Power rating: {inverter.power_rating_kw}kW")
print(f"US version: {inverter.is_us_version}")
print(f"Model family: {inverter.model_family.value}")
```

## Usage Examples

### Basic Feature Detection

```python
from pylxpweb import LuxpowerClient
from pylxpweb.devices import Station

async def check_features():
    client = LuxpowerClient(username, password)
    await client.login()

    stations = await Station.load_all(client)
    for station in stations:
        for inverter in station.all_inverters:
            # Detect features
            features = await inverter.detect_features()

            print(f"Inverter: {inverter.serial_number}")
            print(f"  Model Family: {features.model_family.value}")
            print(f"  Device Type Code: {features.device_type_code}")
            print(f"  Grid Type: {features.grid_type.value}")
            print(f"  Power Rating: {features.model_info.power_rating_kw}kW")
            print(f"  US Version: {features.model_info.us_version}")
            print(f"  Split-Phase: {features.split_phase}")
            print(f"  Parallel Support: {features.parallel_support}")
            print(f"  Volt-Watt Curve: {features.volt_watt_curve}")
```

### Conditional Feature Access

```python
async def configure_inverter(inverter):
    await inverter.detect_features()

    # Only access SNA-specific features if supported
    if inverter.supports_discharge_recovery_hysteresis:
        print(f"Recovery SOC lag: {inverter.discharge_recovery_lag_soc}%")
        print(f"Recovery voltage lag: {inverter.discharge_recovery_lag_volt}V")

    # Only access PV series features if supported
    if inverter.supports_volt_watt_curve:
        print("Volt-Watt curve is supported")

    # Universal features (all inverters)
    if inverter.supports_off_grid:
        await inverter.enable_battery_backup()
```

## Feature Availability Matrix

| Feature | EG4 Off-Grid | EG4 Hybrid | Luxpower (LXP) | GridBOSS |
|---------|--------------|------------|----------------|----------|
| Split-Phase Grid | Yes | Yes | No | N/A |
| Configurable System Type* | No | Yes | Yes | N/A |
| Off-Grid/EPS | Yes | Yes | Yes | N/A |
| Parallel Operation | No | Yes | Yes | Controller |
| Discharge Recovery Hysteresis | Yes | No | No | N/A |
| Quick Charge Minute | Yes | No | No | N/A |
| Volt-Watt Curve | No | Yes | Yes | N/A |
| Grid Peak Shaving | Yes | Yes | Yes | N/A |
| DRMS Support | No | Yes | Yes | N/A |
| EU Grid Compliance | No | No | Yes | N/A |
| Green Mode | Yes | Yes | Yes | N/A |
| Smart Load Ports | No | No | No | Yes (4) |
| AC Coupling Ports | No | No | No | Yes (4) |
| Load Shedding | No | No | No | Yes (4) |

> **Note**: *"Configurable System Type" means the inverter can be configured as 1 Phase Master, 3 Phase Master, 2x208 Master, or Slave via `HOLD_SET_COMPOSED_PHASE`. This is a software configuration, not a hardware limitation. EG4 Hybrid models (12kPV, 18kPV, FlexBOSS18, FlexBOSS21) all support these configurations when used in parallel setups with GridBOSS.

## Adding New Device Types

When a new inverter model is discovered:

1. **Collect Register Data**
   - Use the register dump utility to capture all parameters
   - Note the `HOLD_DEVICE_TYPE_CODE` value from register 19
   - Record `HOLD_MODEL` value from registers 0-1

2. **Update Device Type Mapping**
   - Add the device type code to `DEVICE_TYPE_CODE_TO_FAMILY` in `_features.py`
   - Create a new `InverterFamily` enum value if needed
   - Define default features in `FAMILY_DEFAULT_FEATURES`

3. **Add Model-Specific Parameters**
   - Add parameter lists to `constants/registers.py`
   - Update feature probing in `BaseInverter._probe_optional_features()`

4. **Update Documentation**
   - Add the new model to this document
   - Update the feature availability matrix

## API Reference

### Classes

- `InverterFamily` - Enum of model families (EG4_OFFGRID, EG4_HYBRID, LXP, UNKNOWN)
- `GridType` - Enum of grid types (SPLIT_PHASE, SINGLE_PHASE, THREE_PHASE)
- `InverterModelInfo` - Decoded HOLD_MODEL register data
- `InverterFeatures` - Detected feature capabilities

### Functions

- `get_inverter_family(device_type_code)` - Get family from device type code
- `get_family_features(family)` - Get default features for a family

### BaseInverter Methods

- `detect_features(force=False)` - Detect and cache features
- `features` - Property returning `InverterFeatures`
- `model_family` - Property returning `InverterFamily`
- `device_type_code` - Property returning device type code integer
- `grid_type` - Property returning `GridType`
- `power_rating_kw` - Property returning power rating in kW
- `is_us_version` - Property returning US market flag
- `supports_*` - Boolean properties for feature checks
