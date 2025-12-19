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
| **54** | SNA Series | SNA12K-US |
| **2092** | PV Series | 18KPV |
| **10284** | FlexBOSS Series | FlexBOSS21, FlexBOSS18 |
| **12** | LXP-EU Series | LXP-EU 12K |
| **50** | GridBOSS (MID) | GridBOSS |

## Model Families

### SNA Series (Split-Phase, North America)

**Device Type Code:** 54

**Target Market:** US residential (split-phase 120V/240V)

**Key Features:**
- Split-phase grid support (L1/L2/N)
- Discharge recovery hysteresis (SOC and voltage lag)
- Quick charge minute setting
- Off-grid capable

**Unique Parameters:**
- `HOLD_DISCHG_RECOVERY_LAG_SOC` - SOC hysteresis percentage
- `HOLD_DISCHG_RECOVERY_LAG_VOLT` - Voltage hysteresis (V, scaled ÷10)
- `SNA_HOLD_QUICK_CHARGE_MINUTE` - Quick charge duration
- `OFF_GRID_HOLD_EPS_VOLT_SET` - EPS output voltage
- `OFF_GRID_HOLD_EPS_FREQ_SET` - EPS output frequency

**Sample Models:**
- SNA12K-US: 12kW, device type code 54, HOLD_MODEL 0x90AC1

### PV Series (High-Voltage DC, US)

**Device Type Code:** 2092

**Target Market:** US commercial/residential with high DC voltage

**Key Features:**
- Three-phase grid capable
- Parallel operation support
- Volt-Watt curve control
- Grid peak shaving
- DRMS (Demand Response Management) support

**Unique Parameters:**
- `HOLD_VW_V1` through `HOLD_VW_V4` - Volt-Watt curve voltage points
- `HOLD_VW_P1` through `HOLD_VW_P4` - Volt-Watt curve power points
- `_12K_HOLD_GRID_PEAK_SHAVING_POWER` - Peak shaving power limit
- `HOLD_PARALLEL_REGISTER` - Parallel operation settings

**Sample Models:**
- 18KPV: 18kW, device type code 2092, HOLD_MODEL 0x986C0

### LXP-EU Series (European)

**Device Type Code:** 12

**Target Market:** European market (230V/400V, 50Hz)

**Key Features:**
- EU grid compliance
- Three-phase capable
- Parallel operation support
- Volt-Watt curve control
- DRMS support

**Unique Parameters:**
- `HOLD_EU_GRID_CODE` - EU grid compliance code
- `HOLD_EU_COUNTRY_CODE` - Country-specific settings

**Sample Models:**
- LXP-EU 12K: 12kW, device type code 12, HOLD_MODEL 0x19AC0

### LXP-LV Series (Low-Voltage DC)

**Device Type Code:** Varies (no single known code mapped yet)

**Target Market:** Low-voltage DC battery systems (48V nominal)

**Key Features:**
- Low-voltage DC bus (48V nominal)
- Single-phase grid
- Parallel operation support
- Off-grid capable

**Unique Parameters:**
- Similar to SNA series but with low-voltage DC configuration

**Sample Models:**
- LXP-LV 6048: 6kW, 48V DC

> **Note**: The LXP-LV family exists in the implementation but no specific device type code has been mapped yet. Devices will show as `UNKNOWN` family until a code mapping is added.

### FlexBOSS Series (High-Power Hybrid)

**Device Type Code:** 10284

**Target Market:** US residential/commercial high-power installations

**Key Features:**
- High-power hybrid inverter (18kW/21kW)
- Split-phase grid support (L1/L2/N)
- Parallel operation support
- Volt-Watt curve control
- Grid peak shaving
- Green Mode (off-grid mode toggle)
- DRMS support

**Unique Parameters:**
- `_12K_HOLD_*` registers for 12K/18K/21K series configuration
- `HOLD_VOLT_WATT_V1/V2` - Volt-Watt curve voltage points
- `HOLD_VOLT_WATT_DELAY_TIME` - Volt-Watt response delay
- `FUNC_GREEN_EN` - Green Mode (off-grid mode) in register 110
- `FUNC_MIDBOX_EN` - GridBOSS/MID controller integration
- `FUNC_PARALLEL_DATA_SYNC_EN` - Parallel data synchronization
- `FUNC_LSP_BAT_FIRST_*_EN` - Battery-first scheduling (48 time slots)
- `FUNC_LSP_BYPASS_*_EN` - Bypass mode scheduling (48 time slots)

**Firmware Prefix:** `FAAB-` (e.g., FAAB-2525)

**Sample Models:**
- FlexBOSS21: 21kW, device type code 10284, HOLD_MODEL 0x1098200
- FlexBOSS18: 18kW, device type code 10284

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

| Bits | Field | Description |
|------|-------|-------------|
| 0-3 | `battery_type` | 0=Lead-acid, 1=Lithium primary, 2=Hybrid |
| 4-7 | `lead_acid_type` | Lead-acid battery subtype |
| 8-11 | `lithium_type` | Lithium protocol (1=Standard, 2=EG4, 6=EU) |
| 12-15 | `power_rating` | Power code (6=12K, 7=15K, 8=18K) |
| 16 | `us_version` | 1=US market, 0=EU/other |
| 17 | `measurement` | Measurement unit type |
| 18 | `wireless_meter` | Wireless CT meter flag |
| 19-21 | `meter_type` | CT meter type |
| 22-24 | `meter_brand` | CT meter brand |
| 25-27 | `rule` | Grid compliance rule |
| 28 | `rule_mask` | Grid compliance mask |

### Example Decoding

**SNA12K-US (0x90AC1 = 592577):**
```
battery_type = 1 (Lithium primary → Hybrid)
lithium_type = 2 (EG4 protocol)
power_rating = 6 (12kW)
us_version = 1 (US market)
```

**18KPV (0x986C0 = 624320):**
```
battery_type = 0 (Lead-acid → Hybrid capable)
lithium_type = 1 (Standard)
power_rating = 6 (mapped to 18kW for this model)
us_version = 1 (US market)
```

**LXP-EU 12K (0x19AC0 = 105152):**
```
battery_type = 0 (Hybrid capable)
lithium_type = 6 (EU protocol)
power_rating = 6 (12kW)
us_version = 0 (EU market)
```

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

| Feature | SNA | PV Series | FlexBOSS | LXP-EU | LXP-LV | GridBOSS |
|---------|-----|-----------|----------|--------|--------|----------|
| Split-Phase Grid | Yes | No | Yes | No | No | N/A |
| Three-Phase Capable* | No | Yes | Yes | Yes | No | N/A |
| Off-Grid/EPS | Yes | Yes | Yes | Yes | Yes | N/A |
| Parallel Operation | No | Yes | Yes | Yes | Yes | Controller |
| Discharge Recovery Hysteresis | Yes | No | No | No | No | N/A |
| Quick Charge Minute | Yes | No | No | No | No | N/A |
| Volt-Watt Curve | No | Yes | Yes | Yes | No | N/A |
| Grid Peak Shaving | Yes | Yes | Yes | Yes | Yes | N/A |
| DRMS Support | No | Yes | Yes | Yes | No | N/A |
| EU Grid Compliance | No | No | No | Yes | No | N/A |
| Green Mode | Yes | Yes | Yes | Yes | Yes | N/A |
| Smart Load Ports | No | No | No | No | No | Yes (4) |
| AC Coupling Ports | No | No | No | No | No | Yes (4) |
| Load Shedding | No | No | No | No | No | Yes (4) |

> **Note**: *"Three-Phase Capable" indicates hardware capability. PV Series, FlexBOSS, and LXP-EU default to single-phase but can support three-phase configurations depending on installation. GridBOSS is a MID controller that manages parallel groups rather than generating power directly.

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

- `InverterFamily` - Enum of model families (SNA, PV_SERIES, LXP_EU, LXP_LV, UNKNOWN)
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
