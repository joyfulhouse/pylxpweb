# Gap Analysis: pylxpweb vs Home Assistant EG4 Web Monitor Integration

**Date**: 2025-01-20 (Updated: 2025-11-20)
**Analyzed**: pylxpweb 0.2 vs research/eg4_web_monitor HA integration (v2.2.7)
**Status**: Core library at ~33% completeness for full HA integration support

---

## Executive Summary

The Home Assistant EG4 Web Monitor integration in `research/eg4_web_monitor/` is a mature, production-ready custom component with 250+ entities across 7 platforms. Our pylxpweb library has successfully implemented the core API methods and device hierarchy but requires additional convenience methods, station configuration support, and enhanced caching to fully support a Home Assistant integration.

**Recent Updates** (v2.2.6-v2.2.7, November 2025):
- ✅ Battery Charge/Discharge Current Control (HOLD_LEAD_ACID_CHARGE_RATE / DISCHARGE_RATE)
- ✅ Advanced power management for throttling prevention
- ✅ Comprehensive documentation with automation examples
- ✅ EntityCategory.CONFIG support for configuration entities

**Key Findings**:
- ✅ All critical API endpoints implemented
- ✅ Device hierarchy working (Station → ParallelGroup → Inverters → Batteries)
- ✅ Control operations functional (via HybridInverter)
- ✅ Battery charge/discharge current control (NEW in v2.2.6)
- ⚠️ Missing convenience wrapper methods (can use generic methods)
- ⚠️ Missing station configuration methods (DST, plant settings)
- ⚠️ Cache management needs enhancement (device-specific invalidation)

**Recommendation**: Implement Phase 1-3 enhancements (~20 hours) before building HA integration.

---

## 1. Entity Platforms Comparison

### Home Assistant Integration (250+ Entities)

| Platform | Entity Count | Examples |
|----------|-------------|----------|
| **Sensor** | 231+ | Power, voltage, energy, SOC, temperature, status codes |
| **Switch** | 7 | Quick charge, EPS, working modes, DST |
| **Number** | 9 | SOC limits, AC charge power, PV charge power, battery charge/discharge current |
| **Select** | 1 | Operating mode (Normal/Standby) |
| **Button** | 3 | Device refresh, battery refresh, station refresh |

**Sensor Breakdown**:
- Inverter metrics: 30-40 per device
- Energy data: 6-10 per inverter
- Battery pack: 8-12 per inverter
- Individual batteries: 15 per battery module
- GridBOSS: 30-40 per MID device
- Parallel groups: 20-30 aggregated
- Station: 5 plant-level
- Diagnostic: 10-15 (firmware, status codes)

### pylxpweb (Library Only)

- **Entity Platforms**: None (library provides data, not UI)
- **Device Classes**: Station, ParallelGroup, Inverter, Battery, MIDDevice
- **Entity Generation**: `to_entities()` method returns Entity objects
- **Device Info**: `to_device_info()` method returns DeviceInfo objects

**Assessment**: pylxpweb provides the foundation. HA integration would build entity platforms on top.

---

## 2. API Method Comparison

### ✅ Implemented in Both

| Method Category | pylxpweb | HA Integration |
|----------------|----------|----------------|
| **Plant Discovery** | ✅ `plants.get_plants()` | ✅ `get_plants()` |
| **Device Discovery** | ✅ `devices.get_devices()` | ✅ `get_inverter_overview()` |
| **Parallel Groups** | ✅ `devices.get_parallel_group_details()` | ✅ `get_parallel_group_details()` |
| **Inverter Runtime** | ✅ `inverters.get_inverter_runtime()` | ✅ `get_inverter_runtime()` |
| **Inverter Energy** | ✅ `inverters.get_inverter_energy()` | ✅ `get_inverter_energy_info()` |
| **Parallel Energy** | ✅ `inverters.get_inverter_energy_parallel()` | ✅ `get_inverter_energy_info_parallel()` |
| **Battery Info** | ✅ `batteries.get_battery_info()` | ✅ `get_battery_info()` |
| **GridBOSS Runtime** | ✅ `devices.get_midbox_runtime()` | ✅ `get_midbox_runtime()` |
| **Read Parameters** | ✅ `control.read_parameters()` | ✅ `read_parameters()` |
| **Write Parameters** | ✅ `control.write_parameter()` | ✅ `write_parameter()` |
| **Control Function** | ✅ `control.control_function()` | ✅ `control_function_parameter()` |
| **Quick Charge Start** | ✅ `control.start_quick_charge()` | ✅ `start_quick_charge()` |
| **Quick Charge Stop** | ✅ `control.stop_quick_charge()` | ✅ `stop_quick_charge()` |
| **Quick Charge Status** | ✅ `control.get_quick_charge_status()` | ✅ `get_quick_charge_status()` |

### ⚠️ Missing from pylxpweb (Can be Added)

#### Station Configuration (Not Implemented)
```python
# HA has these methods:
get_plant_details(plant_id)           # Load station configuration
set_daylight_saving_time(plant_id, enabled)  # Toggle DST
update_plant_config(plant_id, **kwargs)      # Update settings
```

**Impact**: Cannot configure station settings (DST, location, etc.)
**Workaround**: None - these require API endpoint implementation
**Priority**: MEDIUM (needed for full HA integration)

#### Control Helper Wrappers (Not Implemented)
```python
# HA has convenience methods:
enable_battery_backup()      # vs control_function(..., "FUNC_EPS_EN", True)
disable_battery_backup()     # vs control_function(..., "FUNC_EPS_EN", False)
enable_normal_mode()         # vs control_function(..., "FUNC_SET_TO_STANDBY", True)
enable_standby_mode()        # vs control_function(..., "FUNC_SET_TO_STANDBY", False)
enable_grid_peak_shaving()   # vs control_function(..., "FUNC_GRID_PEAK_SHAVING", True)
disable_grid_peak_shaving()  # vs control_function(..., "FUNC_GRID_PEAK_SHAVING", False)
```

**Impact**: Less convenient API, more verbose code
**Workaround**: Use generic `control_function()` method
**Priority**: HIGH (developer experience)

#### Convenience Methods (Not Implemented)
```python
# HA combines multiple calls:
get_all_device_data(plant_id)         # Single call for all discovery + runtime
read_device_parameters_ranges(serial) # Auto-read 0-126, 127-253, 240-366
get_battery_backup_status()           # Extract EPS status from parameters
```

**Impact**: More API calls needed, more complex code
**Workaround**: Call individual methods and combine results
**Priority**: MEDIUM (performance optimization)

#### Cache Management Enhancements (Partially Implemented)
```python
# HA has additional cache methods:
clear_cache()                         # Full manual invalidation
_invalidate_cache_for_device(serial)  # Device-specific clearing
get_cache_stats()                     # Cache hit/miss statistics
# Plus: Pre-hour boundary cache clearing (anticipate midnight resets)
```

**Impact**: Less efficient caching, potential stale data
**Workaround**: Use existing TTL-based caching
**Priority**: MEDIUM (production quality)

---

## 3. Control Features Implementation

| Control Feature | HA Platform | pylxpweb Method | Status |
|----------------|-------------|-----------------|--------|
| **Quick Charge** | Switch | `start_quick_charge()` / `stop_quick_charge()` | ✅ Implemented |
| **Battery Backup (EPS)** | Switch | `control_function(..., "FUNC_EPS_EN", bool)` | ⚠️ Generic method |
| **Operating Mode** | Select | `control_function(..., "FUNC_SET_TO_STANDBY", bool)` | ⚠️ Generic method |
| **System Charge SOC** | Number | `write_parameter(..., HOLD_SYSTEM_CHARGE_SOC_LIMIT, val)` | ✅ Can implement |
| **AC Charge Power** | Number | `write_parameter(..., HOLD_AC_CHARGE_POWER_CMD, val)` | ✅ Can implement |
| **PV Charge Power** | Number | `write_parameter(..., HOLD_FORCED_CHG_POWER_CMD, val)` | ✅ Can implement |
| **Grid Peak Shaving** | Number | `write_parameter(..., _12K_HOLD_GRID_PEAK_SHAVING_POWER, val)` | ✅ Can implement |
| **AC Charge SOC Limit** | Number | HybridInverter.`set_ac_charge(soc_limit=val)` | ✅ Implemented |
| **On-Grid SOC Cut-Off** | Number | BaseInverter.`set_battery_soc_limits(on_grid=val)` | ✅ Implemented |
| **Off-Grid SOC Cut-Off** | Number | BaseInverter.`set_battery_soc_limits(off_grid=val)` | ✅ Implemented |
| **Battery Charge Current** | Number | `write_parameter(..., HOLD_LEAD_ACID_CHARGE_RATE, val)` | ✅ Can implement |
| **Battery Discharge Current** | Number | `write_parameter(..., HOLD_LEAD_ACID_DISCHARGE_RATE, val)` | ✅ Can implement |
| **DST Configuration** | Switch | Not implemented | ❌ Missing |
| **Microgrid Mode** | Switch | `control_function(..., "FUNC_MICROGRID_MODE", bool)` | ⚠️ Generic method |
| **Battery Lock Mode** | Switch | `control_function(..., "FUNC_BAT_LOCK_MODE", bool)` | ⚠️ Generic method |
| **Power Limit Mode** | Switch | `control_function(..., "FUNC_POWER_LIMIT_MODE", bool)` | ⚠️ Generic method |

**Summary**: All controls are *technically* possible with pylxpweb's current methods, but HA provides more convenient wrapper methods.

### New Battery Charge/Discharge Control (v2.2.6+)

The EG4 Web Monitor integration added comprehensive battery charge/discharge current control in version 2.2.6 (November 2025). This enables advanced power management scenarios:

**Battery Charge Current Control**:
- Parameter: `HOLD_LEAD_ACID_CHARGE_RATE`
- Range: 0-250 Amperes (A)
- Purpose: Control maximum current to charge batteries
- Use Cases:
  - Prevent inverter throttling during high solar production
  - Maximize grid export during peak rate periods
  - Manage battery health with gentle charging
  - Time-of-use rate optimization

**Battery Discharge Current Control**:
- Parameter: `HOLD_LEAD_ACID_DISCHARGE_RATE`
- Range: 0-250 Amperes (A)
- Purpose: Control maximum current to discharge from batteries
- Use Cases:
  - Preserve battery capacity during grid outages
  - Extend battery lifespan with conservative discharge
  - Manage peak load scenarios
  - Emergency power management

**Implementation Pattern**:
```python
# Write parameter via API
response = await client.api.write_parameter(
    inverter_sn=serial,
    hold_param="HOLD_LEAD_ACID_CHARGE_RATE",
    value_text=str(80),  # 80A = ~4kW at 48V nominal
)

# Response format
{
    "success": True/False,
    "message": "Error message if failed"
}
```

**Key Features**:
- Integer values only (0-250 A)
- Real-time parameter synchronization across all inverters
- EntityCategory.CONFIG for configuration-type entities
- Comprehensive validation and error handling
- Integration with parameter refresh system

**Documentation Reference**: `research/eg4_web_monitor/docs/BATTERY_CURRENT_CONTROL.md`

---

## 4. Device Hierarchy Comparison

### Home Assistant Approach

```python
# Flat dictionary structure with device grouping
{
    "device_info": {...},  # Separate storage
    "sensors": {
        "serial_123_pac": 1234,
        "serial_123_soc": 85,
        "serial_123_bat_BAT_A1_voltage": 52.3,
        ...
    }
}
```

**Characteristics**:
- Flat key-value storage for coordinator
- Device relationships via Home Assistant device registry
- Individual batteries as separate devices with `via_device` parent link
- Uses `batteryKey` from API for unique identification

### pylxpweb Approach

```python
# Object-oriented hierarchy
Station(
    plant_id=123,
    name="My Station",
    parallel_groups=[
        ParallelGroup(
            inverters=[
                HybridInverter(
                    serial_number="123",
                    runtime=InverterRuntime(...),
                    energy=EnergyInfo(...),
                    batteries=[
                        Battery(data=BatteryModule(...)),
                        Battery(data=BatteryModule(...)),
                    ]
                )
            ],
            mid_device=MIDDevice(...)
        )
    ]
)
```

**Characteristics**:
- Nested object hierarchy
- Type-safe with Pydantic models
- Batteries in list, require iteration
- Device relationships via object references

**Assessment**: Both approaches are valid. HA's flat structure optimizes for UI updates; pylxpweb's object model optimizes for programmatic access.

---

## 5. Advanced HA Features (Not Applicable to Library)

These features are HA integration-specific and don't need implementation in pylxpweb:

### Optimistic State Updates
- Switch entities show "on" immediately while API request executes
- Improves UI responsiveness
- **Status**: Not applicable - library doesn't manage UI state

### Entity Categories & Diagnostic Tagging
- Marks certain entities as "diagnostic" (hidden by default)
- Improves UI organization
- **Status**: Not applicable - library doesn't create entities

### Device Grouping & Parent-Child Relationships
- Batteries nested under inverters in device registry
- Uses `via_device` parameter
- **Status**: Not applicable - HA integration would handle this

### Modern Entity Naming
- Uses `_attr_has_entity_name = True` pattern
- Combines device + entity names automatically
- **Status**: Not applicable - library provides raw data

---

## 6. Missing Features Priority Matrix

### HIGH Priority (Essential for HA Integration)

**Effort**: 10-14 hours | **Impact**: Critical

1. **Control Helper Methods** (4-6 hours)
   ```python
   # Add to ControlEndpoints
   async def enable_battery_backup(self, serial: str) -> bool
   async def disable_battery_backup(self, serial: str) -> bool
   async def enable_normal_mode(self, serial: str) -> bool
   async def enable_standby_mode(self, serial: str) -> bool
   async def enable_grid_peak_shaving(self, serial: str) -> bool
   async def disable_grid_peak_shaving(self, serial: str) -> bool
   ```

2. **Convenience Methods** (4-6 hours)
   ```python
   # Add to DeviceEndpoints
   async def get_all_device_data(self, plant_id: int) -> dict
   async def read_device_parameters_ranges(self, serial: str) -> dict

   # Add to ControlEndpoints
   async def get_battery_backup_status(self, serial: str) -> bool
   ```

3. **Parameter Constants Documentation** (2 hours)
   - Document all HOLD_* register addresses
   - Document all FUNC_* function IDs
   - Create reference table in docs/

### MEDIUM Priority (Production Quality)

**Effort**: 10-14 hours | **Impact**: Important

4. **Station Configuration** (6-8 hours)
   ```python
   # Add to PlantEndpoints
   async def get_plant_details(self, plant_id: int) -> PlantDetails
   async def set_daylight_saving_time(self, plant_id: int, enabled: bool) -> bool
   async def update_plant_config(self, plant_id: int, **kwargs) -> bool
   ```

5. **Cache Management Enhancements** (4-6 hours)
   ```python
   # Add to LuxpowerClient
   def clear_cache(self) -> None
   def _invalidate_cache_for_device(self, serial: str) -> None
   def get_cache_stats(self) -> dict
   # Plus: Pre-hour boundary cache clearing logic
   ```

### LOW Priority (Nice to Have)

**Effort**: 2-4 hours | **Impact**: Marginal

6. **Status Code Enumerations** (2 hours)
   - Create `StatusCode` enum
   - Document common codes and meanings

7. **Error Recovery Documentation** (2 hours)
   - Document API error codes
   - Provide recovery strategies

---

## 7. Implementation Recommendations

### Phase 1: Control Helpers (Week 1)
**Goal**: Improve developer experience with convenient wrapper methods

```python
# New methods in ControlEndpoints
await client.api.control.enable_battery_backup(serial)
await client.api.control.enable_normal_mode(serial)
await client.api.control.enable_grid_peak_shaving(serial)
```

**Deliverables**:
- 6 new control helper methods
- Unit tests for each method
- Updated documentation
- Usage examples

**Effort**: 4-6 hours

### Phase 2: Convenience & Station Config (Week 2)
**Goal**: Add missing configuration and convenience methods

```python
# Station configuration
await client.api.plants.get_plant_details(plant_id)
await client.api.plants.set_daylight_saving_time(plant_id, True)

# Convenience methods
all_data = await client.api.devices.get_all_device_data(plant_id)
params = await client.api.devices.read_device_parameters_ranges(serial)
```

**Deliverables**:
- Station configuration methods
- Convenience aggregation methods
- Integration tests
- API documentation updates

**Effort**: 10-14 hours

### Phase 3: Cache Enhancements (Week 3)
**Goal**: Production-grade caching with device-specific invalidation

```python
# Enhanced cache management
client.clear_cache()
client._invalidate_cache_for_device(serial)
stats = client.get_cache_stats()
```

**Deliverables**:
- Cache management methods
- Pre-hour boundary logic
- Cache statistics tracking
- Performance documentation

**Effort**: 4-6 hours

### Phase 4: Documentation (Ongoing)
**Goal**: Comprehensive parameter and register documentation

**Deliverables**:
- Parameter ID reference table
- Register mapping documentation
- Function parameter IDs
- Status code enumerations
- Error code documentation

**Effort**: 2-3 hours

**Total Estimated Effort**: ~20-25 hours

---

## 8. Comparison Table: Feature Completeness

| Feature Category | HA Integration | pylxpweb | Gap |
|-----------------|---------------|----------|-----|
| **Device Discovery** | ✅ Complete | ✅ Complete | None |
| **Runtime Data** | ✅ Complete | ✅ Complete | None |
| **Energy Data** | ✅ Complete | ✅ Complete | None |
| **Battery Data** | ✅ Complete | ✅ Complete | None |
| **GridBOSS Data** | ✅ Complete | ✅ Complete | None |
| **Parameter Read** | ✅ Complete | ✅ Complete | None |
| **Parameter Write** | ✅ Complete | ✅ Complete | None |
| **Quick Charge** | ✅ Complete | ✅ Complete | None |
| **Control Helpers** | ✅ 6 methods | ⚠️ Generic only | Medium |
| **Station Config** | ✅ Complete | ❌ Missing | High |
| **Convenience Methods** | ✅ Complete | ❌ Missing | Medium |
| **Cache Management** | ✅ Advanced | ⚠️ Basic | Medium |
| **Documentation** | ✅ Complete | ⚠️ Partial | Low |
| **Entity Platforms** | ✅ 7 platforms | ❌ N/A (library) | N/A |
| **HA UI Features** | ✅ Full | ❌ N/A (library) | N/A |

**Overall Assessment**: pylxpweb has ~75% of required API methods. Missing 25% consists of convenience wrappers and station configuration.

---

## 9. Code Size Comparison

| Component | HA Integration | pylxpweb | Ratio |
|-----------|---------------|----------|-------|
| **API Client** | 1,346 LOC | 452 LOC | 33% |
| **Device Models** | N/A | 800+ LOC | - |
| **Entity Platforms** | 2,500+ LOC | N/A | - |
| **Coordinator** | 400 LOC | N/A | - |
| **Config Flow** | 300 LOC | N/A | - |
| **Tests** | 1,000+ LOC | 5,400 LOC | 540% |

**Notes**:
- pylxpweb has comprehensive test coverage (260 tests)
- HA integration includes UI/entity code not needed in library
- pylxpweb API client is 1/3 size but covers same functionality

---

## 10. Recommendations Summary

### For Immediate Use
✅ **pylxpweb is ready for**:
- Programmatic device monitoring
- Data collection and logging
- Custom automation scripts
- Non-HA integrations

### For Home Assistant Integration

⚠️ **Recommended before building HA integration**:
1. Implement Phase 1 control helpers (4-6 hours)
2. Implement Phase 2 station config (10-14 hours)
3. Implement Phase 3 cache enhancements (4-6 hours)
4. Complete Phase 4 documentation (2-3 hours)

**Timeline**: ~20-25 hours to feature parity

### For Production Deployment
After implementing Phases 1-4, pylxpweb will be:
- ✅ Feature-complete for HA integration
- ✅ Production-grade caching
- ✅ Comprehensive documentation
- ✅ Full test coverage
- ✅ Ready for 0.3.0 release

---

## Conclusion

**Current Status**: pylxpweb 0.2 provides a solid foundation with all critical API endpoints implemented and excellent test coverage. The architecture is sound for both library use and HA integration.

**Gap Analysis**: Missing features are primarily convenience wrappers and station configuration methods. All gaps can be filled in ~20-25 hours of focused work.

**Path Forward**:
1. **Short-term**: Use pylxpweb 0.2 for monitoring and basic control
2. **Medium-term**: Implement Phases 1-4 enhancements for HA integration
3. **Long-term**: Build production HA integration on top of enhanced library

The existing HA integration in `research/eg4_web_monitor/` provides an excellent reference for entity platform design and user experience patterns.
