# Register Parity & Fault Code Support

**Date**: 2026-02-24
**Status**: Approved
**Scope**: pylxpweb library only (no eg4_web_monitor changes)

## Motivation

Comparison with [ant0nkr/luxpower-ha-integration](https://github.com/ant0nkr/luxpower-ha-integration)
revealed coverage gaps in pylxpweb's register definitions and a complete absence of
fault/warning code interpretation. This design closes those gaps.

## Work Items

### 1. Fault & Warning Code Catalogs

**New file**: `src/pylxpweb/constants/fault_codes.py`

Four code-to-description dictionaries:

| Dict | Type | Entries | Source Registers |
|------|------|---------|------------------|
| `INVERTER_FAULT_CODES` | Bitfield (bit → desc) | 21 | Input 60-61 (32-bit) |
| `INVERTER_WARNING_CODES` | Bitfield (bit → desc) | 30 | Input 62-63 (32-bit) |
| `BMS_FAULT_CODES` | Enum (value → desc) | 15 | Input 99 |
| `BMS_WARNING_CODES` | Enum (value → desc) | 15 | Input 100 |

**Inverter codes** are bitfields — multiple faults/warnings active simultaneously.
Sourced from lxp_modbus `fault_codes.py` and `warning_codes.py` (Luxpower protocol PDF).

**BMS codes** are enumerated values (0x00-0x0E) — one active code at a time.
Sourced from EG4 LL battery manual and community forums. Marked **provisional**
pending hardware verification.

**Decoder functions**:

```python
def decode_fault_bits(raw_value: int, code_map: dict[int, str]) -> list[str]:
    """Extract active fault/warning descriptions from a bitfield value."""
    return [desc for bit, desc in sorted(code_map.items()) if raw_value & (1 << bit)]

def decode_bms_code(raw_value: int, code_map: dict[int, str]) -> str:
    """Look up a single BMS fault/warning code by enum value."""
    return code_map.get(raw_value, f"Unknown code: 0x{raw_value:02X}")
```

**Data model integration**:
- Add `fault_messages` and `warning_messages` properties to `InverterRuntimeData`
- These call `decode_fault_bits()` on the stored raw `fault_code`/`warning_code` values
- Set `ha_sensor_key` on fault/warning register definitions (regs 60-63, 99-100)
  so they can be surfaced as HA diagnostic sensors by the integration

### 2. V23 Input Registers (PV4-6)

**File**: `src/pylxpweb/registers/inverter_input.py` — add 15 `RegisterDefinition` entries

| Address | canonical_name | cloud_api_field | Unit | Category |
|---------|---------------|-----------------|------|----------|
| 217 | pv4_voltage | vpv4 | 0.1V | RUNTIME |
| 218 | pv5_voltage | vpv5 | 0.1V | RUNTIME |
| 219 | pv6_voltage | vpv6 | 0.1V | RUNTIME |
| 220 | pv4_power | ppv4 | W | RUNTIME |
| 221 | pv5_power | ppv5 | W | RUNTIME |
| 222 | pv6_power | ppv6 | W | RUNTIME |
| 223 | epv4_day | epv4Today | 0.1kWh | ENERGY_DAILY |
| 224 | epv4_all_l | (32-bit low) | 0.1kWh | ENERGY_LIFETIME |
| 225 | epv4_all_h | (32-bit high) | 0.1kWh | ENERGY_LIFETIME |
| 226 | epv5_day | epv5Today | 0.1kWh | ENERGY_DAILY |
| 227 | epv5_all_l | (32-bit low) | 0.1kWh | ENERGY_LIFETIME |
| 228 | epv5_all_h | (32-bit high) | 0.1kWh | ENERGY_LIFETIME |
| 229 | epv6_day | epv6Today | 0.1kWh | ENERGY_DAILY |
| 230 | epv6_all_l | (32-bit low) | 0.1kWh | ENERGY_LIFETIME |
| 231 | epv6_all_h | (32-bit high) | 0.1kWh | ENERGY_LIFETIME |

Cloud API field names follow existing pattern (vpv1→vpv4, ppv1→ppv4, etc.).
Need to verify exact cloud field names against live API response.

**Data model**: Extend `InverterRuntimeData` with `vpv5`, `vpv6`, `ppv5`, `ppv6`,
and corresponding energy fields. `vpv4`/`ppv4` already exist.

### 3. Register 179 Bitfield (FUNC_EN_4)

**File**: `src/pylxpweb/registers/inverter_holding.py` — add 16 `HoldingRegisterDefinition` entries

Currently **completely unmapped** in the canonical register system.

| Bit | canonical_name | api_param_key | Description |
|-----|---------------|---------------|-------------|
| 0 | ac_ct_direction | FUNC_AC_CT_DIRECTION | AC CT direction (0=Normal, 1=Reversed) |
| 1 | pv_ct_direction | FUNC_PV_CT_DIRECTION | PV CT direction |
| 2 | afci_alarm_clear | FUNC_AFCI_ALARM_CLR | AFCI alarm clear |
| 3 | battery_wakeup_enable | FUNC_BAT_WAKEUP_EN | Battery wakeup / PV sell first |
| 4 | volt_watt_enable | FUNC_VOLT_WATT_EN | Volt-Watt enable |
| 5 | trip_time_unit | FUNC_TRIP_TIME_UNIT | Trip time unit |
| 6 | active_power_cmd_enable | FUNC_ACT_POWER_CMD_EN | Active power command enable |
| 7 | grid_peak_shaving_enable | FUNC_GRID_PEAK_SHAVING | Grid peak shaving enable |
| 8 | gen_peak_shaving_enable | FUNC_GEN_PEAK_SHAVING | Generator peak shaving enable |
| 9 | battery_charge_control | FUNC_BAT_CHG_CONTROL | Battery charge control (0=SOC, 1=Volt) |
| 10 | battery_discharge_control | FUNC_BAT_DISCHG_CONTROL | Battery discharge control (0=SOC, 1=Volt) |
| 11 | ac_coupling_enable | FUNC_AC_COUPLING | AC coupling enable |
| 12 | pv_arc_enable | FUNC_PV_ARC_EN | PV arc detection enable |
| 13 | smart_load_enable | FUNC_SMART_LOAD_EN | Smart load enable (0=Generator, 1=Smart Load) |
| 14 | rsd_disable | FUNC_RSD_DISABLE | Rapid shutdown disable (0=Enable, 1=Disable) |
| 15 | ongrid_always_on | FUNC_ONGRID_ALWAYS_ON | On-grid always on |

**Note**: pylxpweb's legacy `constants/registers.py` has partial definitions for reg 179
(bits 9, 10, 11, 13) used by existing switch entities. The canonical definitions must
match those api_param_key values to avoid breaking changes.

### 4. Register 233 Bitfield (FUNC_EN_5)

**File**: `src/pylxpweb/registers/inverter_holding.py` — add ~11 `HoldingRegisterDefinition` entries

Currently only a legacy constant (`FUNC_EN_2_REGISTER = 233`, `FUNC_EN_2_BIT_SPORADIC_CHARGE = 12`).

| Bit | canonical_name | api_param_key | Description |
|-----|---------------|---------------|-------------|
| 0 | quick_charge_start_enable | FUNC_QUICK_CHG_START_EN | Quick charge start |
| 1 | battery_backup_enable | FUNC_BATT_BACKUP_EN | Battery backup enable |
| 2 | maintenance_enable | FUNC_MAINTENANCE_EN | Maintenance mode |
| 3 | weekly_schedule_enable | FUNC_ENERTEK_WORKING_MODE | 7-day scheduling mode toggle |
| 4-7 | dry_contactor_multiplex | FUNC_DRY_CONTACTOR_MULTI | Dry contactor multiplex (4 bits) |
| 8-9 | external_ct_position | FUNC_EX_CT_POSITION | External CT position (2 bits) |
| 10 | over_freq_fast_stop | FUNC_OVER_FREQ_FSTOP | Over-frequency fast stop |
| 12 | sporadic_charge_enable | FUNC_SPORADIC_CHARGE | Sporadic charge (existing) |

**Bit 3** is the prerequisite for 7-day scheduling registers 500-723.
When disabled (0), daily schedule registers 68-89 are in effect.
When enabled (1), weekly schedule registers 500-723 override.

### 5. 7-Day Scheduling Registers (500-723)

**New file**: `src/pylxpweb/registers/scheduling.py`

224 registers generated parametrically from a compact template.

#### Schedule Types

| Type | Base Address | Range | Cloud Write Key Pattern | Cloud Read Prefix |
|------|-------------|-------|------------------------|-------------------|
| AC Charge | 500 | 500-555 | `_12K_HOLD_WEEK_{day}_WRITE_AC_CHARGE` | `ubACChg` |
| Forced Charge | 556 | 556-611 | `_12K_HOLD_WEEK_{day}_WRITE_FORCED_CHARGE` | `ubForcedChg` |
| Forced Discharge | 612 | 612-667 | `_12K_HOLD_WEEK_{day}_WRITE_FORCED_DISCHARGE` | `ubForcedDischg` |
| Peak Shaving | 668 | 668-723 | `_12K_HOLD_WEEK_{day}_WRITE_GRID_PEAK_SHAVING` | `ubGridPeakShav` |

#### Per-Day Structure (8 registers = 2 slots)

Each day has 2 time slots, each with 4 registers:

| Offset | Field | Unit | Description |
|--------|-------|------|-------------|
| +0 | power_cmd | % | Power level / SOC limit (packed) |
| +1 | volt_limit | V | Battery voltage limit |
| +2 | time_start | packed | Start hour + minute |
| +3 | time_end | packed | End hour + minute |

Per schedule type: 7 days x 2 slots x 4 regs = 56 registers.

#### Cloud API

**Read**: `POST /web/maintain/remoteWeeklyOperation/readValues`
- Parameters: `inverterSn`, `startRegister`, `pointNumber`
- Read sequence: regs 200 (non-weekly params), then 500-611 (112 regs), then 612-723 (112 regs)
- Response fields: `ubACChgStartHour1_Day_1`, `ubForcedDischgSOCLimit2_Day_7`, etc.

**Write**: `POST /web/maintain/remoteWeeklyOperation/setValues`
- Parameters: `inverterSn`, `holdParam` (day key), plus 14 field values per day:
  `powerCMD1`, `voltLimit1`, `socLimit1`, `startHour1`, `startMinute1`, `endHour1`, `endMinute1`,
  `powerCMD2`, `voltLimit2`, `socLimit2`, `startHour2`, `startMinute2`, `endHour2`, `endMinute2`

**Toggle**: `POST /web/maintain/remoteSet/functionControl`
- `functionParam=FUNC_ENERTEK_WORKING_MODE`, `enable=true/false`
- Maps to register 233, bit 3

#### Parametric Generation

```python
@dataclass(frozen=True)
class ScheduleTypeConfig:
    name: str               # "ac_charge"
    base_address: int       # 500
    api_write_suffix: str   # "AC_CHARGE"
    api_read_prefix: str    # "ubACChg"

SCHEDULE_TYPES: tuple[ScheduleTypeConfig, ...] = (...)
DAYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

def _generate_schedule_registers() -> tuple[HoldingRegisterDefinition, ...]:
    """Generate all 224 schedule register definitions from templates."""
    ...
```

The generator produces real `HoldingRegisterDefinition` objects with:
- `address`: computed from base + day_index*8 + slot*4 + field_offset
- `canonical_name`: e.g., `ac_charge_power_cmd_1_mon`
- `api_param_key`: e.g., `ubACChgPowerCMD1_Day_1`
- `category`: `HoldingCategory.SCHEDULE`
- `writable`: True

Lookup dicts `BY_ADDRESS`, `BY_NAME`, `BY_API_KEY` populated at module level.

## File Layout

```
src/pylxpweb/
├── constants/
│   ├── fault_codes.py          ← NEW: 4 code dicts + decode helpers
│   └── scaling.py              (unchanged)
├── registers/
│   ├── __init__.py             (add scheduling + fault code exports)
│   ├── inverter_input.py       (add V23 PV4-6 regs 217-231)
│   ├── inverter_holding.py     (add reg 179 bits, reg 233 bits)
│   ├── scheduling.py           ← NEW: parametric 224-reg generation
│   ├── battery.py              (unchanged)
│   └── gridboss.py             (unchanged)
├── transports/
│   └── data.py                 (extend InverterRuntimeData)
└── __init__.py                 (export new public APIs)
```

## Public API Additions

```python
# Fault code infrastructure
from pylxpweb.constants.fault_codes import (
    INVERTER_FAULT_CODES,
    INVERTER_WARNING_CODES,
    BMS_FAULT_CODES,
    BMS_WARNING_CODES,
    decode_fault_bits,
    decode_bms_code,
)

# Scheduling registers
from pylxpweb.registers.scheduling import (
    ScheduleTypeConfig,
    SCHEDULE_TYPES,
    SCHEDULE_REGISTERS,
    SCHEDULE_BY_ADDRESS,
    SCHEDULE_BY_API_KEY,
)
```

## Out of Scope

- No HA entity creation for scheduling (eg4_web_monitor concern, separate PR)
- No schedule read/write methods on `LuxpowerClient` (separate PR)
- No transport layer changes (scheduling is cloud-API-only for now)
- No changes to `BaseInverter.refresh()` flow
- No Modbus register group changes for scheduling

## Summary Table

| Work Item | New Definitions | Files Modified/Created |
|-----------|----------------|----------------------|
| Fault/warning code catalogs | 4 dicts + 2 functions | constants/fault_codes.py (new) |
| V23 PV4-6 input registers | 15 RegisterDefinitions | registers/inverter_input.py |
| Register 179 full bitfield | 16 HoldingRegisterDefs | registers/inverter_holding.py |
| Register 233 full bitfield | ~11 HoldingRegisterDefs | registers/inverter_holding.py |
| 7-day scheduling (500-723) | 224 HoldingRegisterDefs | registers/scheduling.py (new) |
| Data model extensions | PV5/6 fields + fault props | transports/data.py |
| **Total** | **~270 new definitions** | **3 modified, 2 new files** |
