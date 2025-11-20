# Battery Charge/Discharge Current Control - Implementation Tracking

**Date**: 2025-11-20
**Feature**: Battery Charge/Discharge Current Control
**Source**: EG4 Web Monitor v2.2.6-v2.2.7
**Status**: Research Complete - Ready for Implementation

---

## Overview

The EG4 Web Monitor Home Assistant integration added comprehensive battery charge/discharge current control in version 2.2.6 (November 2025). This feature enables advanced power management scenarios including:

- Preventing inverter throttling during high solar production
- Time-of-use rate optimization
- Battery health management
- Emergency power management

---

## Feature Specifications

### Battery Charge Current Control

**Parameter**: `HOLD_LEAD_ACID_CHARGE_RATE`
- **Type**: Integer
- **Range**: 0-250 Amperes
- **Unit**: A (Amperes)
- **Purpose**: Control maximum current to charge batteries
- **API Method**: `write_parameter()`

### Battery Discharge Current Control

**Parameter**: `HOLD_LEAD_ACID_DISCHARGE_RATE`
- **Type**: Integer
- **Range**: 0-250 Amperes
- **Unit**: A (Amperes)
- **Purpose**: Control maximum current to discharge from batteries
- **API Method**: `write_parameter()`

---

## API Implementation

### Write Parameter

```python
# From: research/eg4_web_monitor/.../client.py:818
async def write_parameter(
    self,
    inverter_sn: str,
    hold_param: str,
    value_text: str,
    *,
    client_type: str = "WEB",
    remote_set_type: str = "NORMAL",
) -> Dict[str, Any]:
    """Write a parameter to an inverter using the remote write endpoint.

    Args:
        inverter_sn: The inverter serial number
        hold_param: The parameter name (e.g., "HOLD_LEAD_ACID_CHARGE_RATE")
        value_text: The value to write as string
        client_type: Client type (default: "WEB")
        remote_set_type: Remote set type (default: "NORMAL")

    Returns:
        Dict containing the parameter write response
    """
    return await self._request_with_inverter_sn(
        "parameter_write",
        inverter_sn,
        f"parameter write ({hold_param}={value_text})",
        holdParam=hold_param,
        valueText=value_text,
        clientType=client_type,
        remoteSetType=remote_set_type,
    )
```

### API Endpoint

**Endpoint**: `/WManage/web/maintain/inverter/param/write`
**Method**: POST

**Request Payload**:
```json
{
  "serialNum": "1234567890",
  "holdParam": "HOLD_LEAD_ACID_CHARGE_RATE",
  "valueText": "80",
  "clientType": "WEB",
  "remoteSetType": "NORMAL"
}
```

**Response Format**:
```json
{
  "success": true,
  "message": null
}
```

**Error Response**:
```json
{
  "success": false,
  "message": "Parameter value out of range"
}
```

---

## Home Assistant Entity Implementation

### BatteryChargeCurrentNumber

**Source**: `research/eg4_web_monitor/.../number.py:2150`

**Key Features**:
1. **Entity Configuration**:
   - Platform: `number`
   - Mode: `NumberMode.BOX`
   - Icon: `mdi:battery-plus`
   - Category: `EntityCategory.CONFIG`
   - Has Entity Name: `True`

2. **Value Management**:
   - Native min: 0 A
   - Native max: 250 A
   - Native step: 1 A
   - Precision: 0 (integer only)
   - Unit: A (Amperes)

3. **Data Flow**:
   ```
   User Input → async_set_native_value()
              → write_parameter()
              → _refresh_all_parameters_and_entities()
              → refresh_all_device_parameters()
              → async_request_refresh()
   ```

4. **Validation**:
   - Range check: 0-250 A
   - Integer enforcement: No decimal values
   - Response validation: Check `success` field

5. **State Synchronization**:
   - Read from coordinator's parameter cache
   - Fallback to last known value
   - Periodic refresh via `async_update()`
   - Initial read on `async_added_to_hass()`

### BatteryDischargeCurrentNumber

**Source**: `research/eg4_web_monitor/.../number.py:2436`

**Key Features**:
- Identical implementation to BatteryChargeCurrentNumber
- Different parameter: `HOLD_LEAD_ACID_DISCHARGE_RATE`
- Different icon: `mdi:battery-minus`
- Same validation and synchronization logic

---

## Implementation Architecture

### Class Structure

```python
class BatteryChargeCurrentNumber(CoordinatorEntity, NumberEntity):
    """Number entity for Battery Charge Current control."""

    def __init__(self, coordinator: EG4DataUpdateCoordinator, serial: str):
        # Entity configuration
        self._attr_has_entity_name = True
        self._attr_name = "Battery Charge Current"
        self._attr_unique_id = f"{model}_{serial}_battery_charge_current"

        # Number configuration
        self._attr_native_min_value = 0
        self._attr_native_max_value = 250
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = "A"
        self._attr_mode = NumberMode.BOX
        self._attr_icon = "mdi:battery-plus"
        self._attr_native_precision = 0
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def native_value(self) -> Optional[int]:
        """Return current value from coordinator."""
        coordinator_value = self._get_value_from_coordinator()
        if coordinator_value is not None:
            self._current_value = coordinator_value
            return int(round(coordinator_value))
        return int(round(self._current_value)) if self._current_value else None

    async def async_set_native_value(self, value: float) -> None:
        """Set the battery charge current value."""
        # 1. Validate input
        int_value = int(round(value))
        if not (0 <= int_value <= 250):
            raise ValueError("Value out of range")

        # 2. Write parameter
        response = await self.coordinator.api.write_parameter(
            inverter_sn=self.serial,
            hold_param="HOLD_LEAD_ACID_CHARGE_RATE",
            value_text=str(int_value),
        )

        # 3. Handle response
        if response.get("success", False):
            self._current_value = value
            self.async_write_ha_state()

            # 4. Refresh parameters across all inverters
            self.hass.async_create_task(
                self._refresh_all_parameters_and_entities()
            )
        else:
            raise HomeAssistantError(
                f"Failed to set value: {response.get('message')}"
            )

    def _get_value_from_coordinator(self) -> Optional[float]:
        """Get value from coordinator's parameter cache."""
        if "parameters" in self.coordinator.data:
            parameter_data = self.coordinator.data["parameters"].get(self.serial, {})
            if "HOLD_LEAD_ACID_CHARGE_RATE" in parameter_data:
                raw_value = parameter_data["HOLD_LEAD_ACID_CHARGE_RATE"]
                if raw_value is not None:
                    value = float(raw_value)
                    if 0 <= value <= 250:
                        return value
        return None

    async def _refresh_all_parameters_and_entities(self) -> None:
        """Refresh parameters for all inverters."""
        await self.coordinator.refresh_all_device_parameters()

        # Update all current limit entities
        platform = self.platform
        if platform is not None:
            current_entities = [
                entity for entity in platform.entities.values()
                if isinstance(entity, (BatteryChargeCurrentNumber, BatteryDischargeCurrentNumber))
            ]

            update_tasks = [entity.async_update() for entity in current_entities]
            await asyncio.gather(*update_tasks, return_exceptions=True)
            await self.coordinator.async_request_refresh()

    async def async_update(self) -> None:
        """Update the entity."""
        current_value = await self._read_current_battery_charge_current()
        if current_value is not None and current_value != self._current_value:
            self._current_value = current_value
        await self.coordinator.async_request_refresh()

    async def _read_current_battery_charge_current(self) -> Optional[float]:
        """Read the current value from device."""
        responses = await read_device_parameters_ranges(
            self.coordinator.api, self.serial
        )

        for _, response, start_register in process_parameter_responses(
            responses, self.serial, _LOGGER
        ):
            if response and response.get("success", False):
                value = self._extract_battery_charge_current(response, start_register)
                if value is not None:
                    return value
        return None

    def _extract_battery_charge_current(
        self, response: Dict[str, Any], start_register: int
    ) -> Optional[int]:
        """Extract HOLD_LEAD_ACID_CHARGE_RATE from parameter response."""
        if (
            "HOLD_LEAD_ACID_CHARGE_RATE" in response
            and response["HOLD_LEAD_ACID_CHARGE_RATE"] is not None
        ):
            try:
                raw_value = float(response["HOLD_LEAD_ACID_CHARGE_RATE"])
                int_value = int(round(raw_value))
                if 0 <= int_value <= 250:
                    return int_value
            except (ValueError, TypeError):
                pass
        return None

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

        # Initial read
        current_value = await self._read_current_battery_charge_current()
        if current_value is not None:
            self._current_value = current_value
            self.async_write_ha_state()
```

---

## Parameter Reading Strategy

### Multi-Range Reading

The integration reads parameters in three overlapping ranges to ensure all parameters are captured:

```python
async def read_device_parameters_ranges(api_client, serial_number):
    """Read all parameter ranges for a device."""
    responses = []

    # Range 1: Base parameters (0-126)
    response1 = await api_client.read_parameters(
        inverter_sn=serial_number,
        param_ids=list(range(0, 127))
    )
    responses.append((0, response1))

    # Range 2: Extended parameters (127-253)
    response2 = await api_client.read_parameters(
        inverter_sn=serial_number,
        param_ids=list(range(127, 254))
    )
    responses.append((127, response2))

    # Range 3: Advanced parameters (240-366)
    response3 = await api_client.read_parameters(
        inverter_sn=serial_number,
        param_ids=list(range(240, 367))
    )
    responses.append((240, response3))

    return responses
```

### Parameter Cache Structure

```python
coordinator.data = {
    "parameters": {
        "1234567890": {  # Serial number
            "HOLD_LEAD_ACID_CHARGE_RATE": 200,
            "HOLD_LEAD_ACID_DISCHARGE_RATE": 200,
            "HOLD_SYSTEM_CHARGE_SOC_LIMIT": 95,
            # ... other parameters
        }
    }
}
```

---

## Synchronization Strategy

### Multi-Inverter Coordination

When one inverter's parameter changes, all inverters should be refreshed:

```python
async def _refresh_all_parameters_and_entities(self) -> None:
    """Refresh parameters for all inverters and update all current limit entities."""
    try:
        # Step 1: Refresh all device parameters via coordinator
        await self.coordinator.refresh_all_device_parameters()

        # Step 2: Find all current limit entities
        platform = self.platform
        if platform is not None:
            current_entities = [
                entity
                for entity in platform.entities.values()
                if isinstance(
                    entity,
                    (BatteryChargeCurrentNumber, BatteryDischargeCurrentNumber),
                )
            ]

            # Step 3: Update all entities in parallel
            update_tasks = []
            for entity in current_entities:
                task = entity.async_update()
                update_tasks.append(task)

            await asyncio.gather(*update_tasks, return_exceptions=True)

            # Step 4: Request coordinator refresh
            await self.coordinator.async_request_refresh()

    except Exception as e:
        _LOGGER.error("Failed to refresh parameters and entities: %s", e)
```

### Debouncing Strategy

The coordinator implements debouncing for parameter refreshes:

```python
# From coordinator
async def refresh_all_device_parameters(self):
    """Refresh parameters for all devices with debouncing."""
    # Debounce: Wait at least 10 seconds between refreshes
    now = asyncio.get_event_loop().time()
    if self._last_param_refresh and (now - self._last_param_refresh) < 10:
        return

    self._last_param_refresh = now

    # Refresh all devices
    for serial in self.data.get("devices", {}).keys():
        await self._refresh_device_parameters(serial)
```

---

## Use Cases & Automation Examples

### Use Case 1: Prevent Inverter Throttling

**Problem**: 18kPV inverter with 20kW PV array. When batteries are full, system throttles to 12kW AC limit, wasting 6kW potential production.

**Solution**: Reduce charge current during high production to force grid export.

```yaml
automation:
  - alias: "Prevent Throttling - Sunny Day"
    trigger:
      - platform: state
        entity_id: weather.home
        to: "sunny"
    condition:
      - condition: sun
        after: sunrise
        before: sunset
      - condition: numeric_state
        entity_id: sensor.eg4_18kpv_1234567890_soc
        above: 80
    action:
      - service: number.set_value
        target:
          entity_id: number.eg4_18kpv_1234567890_battery_charge_current
        data:
          value: 80  # ~4kW charge = 14kW available for export
```

### Use Case 2: Time-of-Use Optimization

**Problem**: Peak grid export rates 2pm-7pm. Want to maximize export during peak, charge during off-peak.

**Solution**: Dynamic charge rate based on TOU period.

```yaml
automation:
  - alias: "TOU - Peak Export"
    trigger:
      - platform: time
        at: "14:00:00"
    action:
      - service: number.set_value
        target:
          entity_id: number.eg4_18kpv_1234567890_battery_charge_current
        data:
          value: 50  # Minimal charge, maximum export

  - alias: "TOU - Off-Peak Charge"
    trigger:
      - platform: time
        at: "19:00:00"
    action:
      - service: number.set_value
        target:
          entity_id: number.eg4_18kpv_1234567890_battery_charge_current
        data:
          value: 200  # Maximum charge rate
```

### Use Case 3: Weather-Based Optimization

**Problem**: Need different strategies for sunny vs cloudy days.

**Solution**: Adjust charge rate based on weather forecast and current production.

```yaml
automation:
  - alias: "Weather-Based Charge Control"
    trigger:
      - platform: time_pattern
        hours: "/1"  # Every hour
    condition:
      - condition: sun
        after: sunrise
        before: sunset
    action:
      - choose:
          # Sunny + high SOC = reduce charge
          - conditions:
              - condition: state
                entity_id: weather.home
                state: "sunny"
              - condition: numeric_state
                entity_id: sensor.eg4_18kpv_1234567890_soc
                above: 85
            sequence:
              - service: number.set_value
                data:
                  value: 80

          # Cloudy = maximize charge
          - conditions:
              - condition: state
                entity_id: weather.home
                state: ["cloudy", "partlycloudy"]
            sequence:
              - service: number.set_value
                data:
                  value: 200
```

---

## Safety & Validation

### Input Validation

```python
async def async_set_native_value(self, value: float) -> None:
    """Set the battery charge current value with validation."""
    # 1. Round to integer
    int_value = int(round(value))

    # 2. Range check
    if int_value < 0 or int_value > 250:
        raise ValueError(
            f"Battery charge current must be between 0-250 A, got {int_value}"
        )

    # 3. Enforce integer-only
    if abs(value - int_value) > 0.01:
        raise ValueError(
            f"Battery charge current must be an integer value, got {value}"
        )
```

### Battery Safety Limits

⚠️ **Critical Considerations**:

1. **Battery Manufacturer Limits**:
   - Check battery datasheet for max charge/discharge current
   - API maximum (250A) may exceed battery limits
   - Account for parallel battery banks

2. **Temperature Monitoring**:
   - Monitor battery temperature during high current
   - Reduce current if temperature exceeds 45°C
   - Some batteries have lower limits in cold weather

3. **Voltage Monitoring**:
   - Watch for voltage drop during discharge
   - Monitor cell voltage delta (imbalance)
   - Stop if voltage drops too quickly

4. **BMS Override**:
   - Battery BMS may impose stricter limits
   - BMS limits take precedence over API settings
   - Actual current may be lower than set value

---

## Implementation Checklist for pylxpweb

### Phase 1: Core API Methods (4-6 hours)

- [ ] Add `HOLD_LEAD_ACID_CHARGE_RATE` to parameter constants
- [ ] Add `HOLD_LEAD_ACID_DISCHARGE_RATE` to parameter constants
- [ ] Verify `write_parameter()` method supports these parameters
- [ ] Add integration tests for charge/discharge rate setting
- [ ] Document parameter ranges and validation

### Phase 2: Convenience Methods (2-3 hours)

- [ ] Add `set_battery_charge_current(serial, amperes)` method
- [ ] Add `set_battery_discharge_current(serial, amperes)` method
- [ ] Add `get_battery_charge_current(serial)` method
- [ ] Add `get_battery_discharge_current(serial)` method
- [ ] Implement input validation (0-250 A, integer only)

### Phase 3: Device Integration (3-4 hours)

- [ ] Add charge/discharge current to `Inverter` model
- [ ] Add methods to `HybridInverter` class
- [ ] Update parameter reading to include current rates
- [ ] Add to entity generation if building HA integration

### Phase 4: Documentation (2-3 hours)

- [ ] Document use cases in README
- [ ] Add automation examples
- [ ] Document safety considerations
- [ ] Add API reference for new parameters
- [ ] Create migration guide from generic methods

### Phase 5: Testing (4-5 hours)

- [ ] Unit tests for parameter validation
- [ ] Integration tests with real device
- [ ] Test multi-inverter synchronization
- [ ] Test error handling
- [ ] Test parameter refresh logic

**Total Estimated Effort**: 15-21 hours

---

## References

### Source Files

1. **API Client**:
   - File: `research/eg4_web_monitor/custom_components/eg4_web_monitor/eg4_inverter_api/client.py`
   - Method: `write_parameter()` (line 818)

2. **Number Entity Implementation**:
   - File: `research/eg4_web_monitor/custom_components/eg4_web_monitor/number.py`
   - Class: `BatteryChargeCurrentNumber` (line 2150)
   - Class: `BatteryDischargeCurrentNumber` (line 2436)

3. **Documentation**:
   - File: `research/eg4_web_monitor/docs/BATTERY_CURRENT_CONTROL.md`
   - Use cases, safety, automation examples

4. **Automation Examples**:
   - File: `research/eg4_web_monitor/examples/automations/battery_charge_control_weather.yaml`
   - 5 comprehensive automation scenarios

### Related Documentation

- `docs/GAP_ANALYSIS.md` - Gap analysis with v2.2.7 updates
- `docs/PARAMETER_REFERENCE.md` - Complete parameter reference
- `CLAUDE.md` - Project implementation guidelines

---

## Next Steps

1. **Review Implementation**: Review the complete implementation in research files
2. **Update API Client**: Add parameter constants to pylxpweb
3. **Add Convenience Methods**: Implement high-level methods for charge/discharge control
4. **Create Tests**: Comprehensive unit and integration tests
5. **Document**: Update pylxpweb documentation with new features
6. **Release**: Version 0.3.0 with charge/discharge control support
