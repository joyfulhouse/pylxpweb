# Luxpower/EG4 API Parameter Reference

**Last Updated**: 2025-11-20
**Source**: EG4 Web Monitor HA Integration v2.2.7
**API Base**: `https://monitor.eg4electronics.com`

This document provides a comprehensive reference for parameter IDs used in the Luxpower/EG4 inverter API, extracted from the production EG4 Web Monitor Home Assistant integration.

---

## Overview

The Luxpower/EG4 API supports two primary parameter operations:

1. **Read Parameters**: `/WManage/web/maintain/inverter/param/read` (POST)
2. **Write Parameters**: `/WManage/web/maintain/inverter/param/write` (POST)

### Read Parameters Request

```json
{
  "serialNum": "1234567890",
  "paramIds": [0, 1, 2, 3]
}
```

### Write Parameters Request

```json
{
  "serialNum": "1234567890",
  "holdParam": "HOLD_SYSTEM_CHARGE_SOC_LIMIT",
  "valueText": "95",
  "clientType": "WEB",
  "remoteSetType": "NORMAL"
}
```

---

## Parameter Categories

### 1. Battery Charge/Discharge Control

#### Battery Charge Current
- **Parameter Name**: `HOLD_LEAD_ACID_CHARGE_RATE`
- **Type**: Write
- **Range**: 0-250 A (Amperes)
- **Unit**: Amperes
- **Purpose**: Controls maximum current allowed to charge batteries
- **Added**: v2.2.6 (November 2025)
- **Use Cases**:
  - Prevent inverter throttling during high solar production
  - Maximize grid export during peak rate periods
  - Battery health management with gentle charging
  - Time-of-use rate optimization

**Example**:
```python
response = await client.write_parameter(
    inverter_sn="1234567890",
    hold_param="HOLD_LEAD_ACID_CHARGE_RATE",
    value_text="80"  # 80A = ~4kW at 48V nominal
)
```

**Power Calculation** (48V nominal system):
- 50A = ~2.4kW
- 100A = ~4.8kW
- 150A = ~7.2kW
- 200A = ~9.6kW
- 250A = ~12kW

#### Battery Discharge Current
- **Parameter Name**: `HOLD_LEAD_ACID_DISCHARGE_RATE`
- **Type**: Write
- **Range**: 0-250 A (Amperes)
- **Unit**: Amperes
- **Purpose**: Controls maximum current allowed to discharge from batteries
- **Added**: v2.2.6 (November 2025)
- **Use Cases**:
  - Preserve battery capacity during grid outages
  - Extend battery lifespan with conservative discharge
  - Manage peak load scenarios
  - Emergency power management

**Example**:
```python
response = await client.write_parameter(
    inverter_sn="1234567890",
    hold_param="HOLD_LEAD_ACID_DISCHARGE_RATE",
    value_text="150"  # 150A = ~7.2kW at 48V nominal
)
```

---

### 2. State of Charge (SOC) Control

#### System Charge SOC Limit
- **Parameter Name**: `HOLD_SYSTEM_CHARGE_SOC_LIMIT`
- **Type**: Write
- **Range**: 0-100 %
- **Unit**: Percent
- **Purpose**: Sets the target SOC for battery charging from solar/AC
- **Default**: Typically 95-100%

**Example**:
```python
response = await client.write_parameter(
    inverter_sn="1234567890",
    hold_param="HOLD_SYSTEM_CHARGE_SOC_LIMIT",
    value_text="95"
)
```

#### AC Charge SOC Limit
- **Parameter Name**: `HOLD_AC_CHARGE_SOC_LIMIT`
- **Type**: Write
- **Range**: 0-100 %
- **Unit**: Percent
- **Purpose**: Maximum SOC when charging from AC grid
- **Use Case**: Prevent full charge from grid during TOU high-rate periods

#### On-Grid SOC Cut-Off
- **Parameter Name**: `HOLD_ON_GRID_DISCHG_CUT_OFF_SOC_EOD`
- **Type**: Write
- **Range**: 0-100 %
- **Unit**: Percent
- **Purpose**: Minimum SOC before stopping discharge when grid is available
- **Default**: Typically 10-20%

#### Off-Grid SOC Cut-Off
- **Parameter Name**: `HOLD_OFF_GRID_DISCHG_CUT_OFF_SOC_EOD`
- **Type**: Write
- **Range**: 0-100 %
- **Unit**: Percent
- **Purpose**: Minimum SOC before stopping discharge during grid outage
- **Default**: Typically 5-10%

---

### 3. Power Control

#### AC Charge Power
- **Parameter Name**: `HOLD_AC_CHARGE_POWER_CMD`
- **Type**: Write
- **Range**: 0-12000 W (device dependent)
- **Unit**: Watts
- **Purpose**: Maximum power draw from AC grid for battery charging
- **Precision**: Supports decimal values (0.1 kW increments) as of v2.2.4

**Example**:
```python
response = await client.write_parameter(
    inverter_sn="1234567890",
    hold_param="HOLD_AC_CHARGE_POWER_CMD",
    value_text="5000"  # 5kW AC charge power
)
```

#### PV Charge Power (Forced Charge)
- **Parameter Name**: `HOLD_FORCED_CHG_POWER_CMD`
- **Type**: Write
- **Range**: 0-18000 W (device dependent)
- **Unit**: Watts
- **Purpose**: Maximum power from PV for battery charging

#### Grid Peak Shaving Power
- **Parameter Name**: `_12K_HOLD_GRID_PEAK_SHAVING_POWER`
- **Type**: Write
- **Range**: 0-12000 W (device dependent)
- **Unit**: Watts
- **Purpose**: Maximum power allowed from grid during peak shaving mode

---

### 4. Function Control Parameters

Function parameters use `control_function_parameter()` API method instead of `write_parameter()`.

#### Battery Backup (EPS) Enable
- **Function Name**: `FUNC_EPS_EN`
- **Type**: Boolean Function
- **Values**: True (enable) / False (disable)
- **Purpose**: Enable/disable battery backup (EPS) mode
- **Note**: Not supported on XP series inverters

**Example**:
```python
response = await client.control_function_parameter(
    serial_number="1234567890",
    function_param="FUNC_EPS_EN",
    enable=True
)
```

#### Set to Standby
- **Function Name**: `FUNC_SET_TO_STANDBY`
- **Type**: Boolean Function
- **Values**: True (standby) / False (normal)
- **Purpose**: Switch between Normal and Standby operating modes

#### Grid Peak Shaving Enable
- **Function Name**: `FUNC_GRID_PEAK_SHAVING`
- **Type**: Boolean Function
- **Values**: True (enable) / False (disable)
- **Purpose**: Enable/disable grid peak shaving mode

#### Microgrid Mode
- **Function Name**: `FUNC_MICROGRID_MODE`
- **Type**: Boolean Function
- **Values**: True (enable) / False (disable)
- **Purpose**: Enable/disable microgrid operation mode

#### Battery Lock Mode
- **Function Name**: `FUNC_BAT_LOCK_MODE`
- **Type**: Boolean Function
- **Values**: True (enable) / False (disable)
- **Purpose**: Lock battery to prevent charging/discharging

#### Power Limit Mode
- **Function Name**: `FUNC_POWER_LIMIT_MODE`
- **Type**: Boolean Function
- **Values**: True (enable) / False (disable)
- **Purpose**: Enable power limiting mode

---

## Parameter Register Ranges

The API supports reading parameters in ranges. The EG4 Web Monitor integration uses these standard ranges:

### Standard Ranges
- **Range 1**: Registers 0-126 (base parameters)
- **Range 2**: Registers 127-253 (extended parameters)
- **Range 3**: Registers 240-366 (advanced parameters - overlaps with Range 2)

### Usage Pattern

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

---

## Response Formats

### Successful Write Response

```json
{
  "success": true,
  "message": null
}
```

### Failed Write Response

```json
{
  "success": false,
  "message": "Parameter value out of range"
}
```

### Read Response

```json
{
  "success": true,
  "HOLD_LEAD_ACID_CHARGE_RATE": 200,
  "HOLD_LEAD_ACID_DISCHARGE_RATE": 200,
  "HOLD_SYSTEM_CHARGE_SOC_LIMIT": 95,
  ...
}
```

---

## Data Validation

### Battery Current Parameters
- **Minimum**: 0 A
- **Maximum**: 250 A
- **Type**: Integer only (no decimals)
- **Validation**: Must check against battery manufacturer specifications

### SOC Parameters
- **Minimum**: 0 %
- **Maximum**: 100 %
- **Type**: Integer
- **Validation**: Logical checks (e.g., discharge cut-off < charge target)

### Power Parameters
- **Minimum**: 0 W
- **Maximum**: Device dependent (12kW, 18kW, etc.)
- **Type**: Integer (some support decimals as of v2.2.4)
- **Validation**: Must not exceed inverter rating

---

## Safety Considerations

### Battery Current Limits

⚠️ **CRITICAL**: Never exceed battery manufacturer's maximum charge/discharge current ratings.

**Considerations**:
- Check battery datasheet specifications
- Account for multiple battery banks in parallel
- Monitor battery temperature during high current operations
- Some batteries have lower limits in cold weather
- API maximum (250A) may exceed battery safe limits

### Monitoring

Always monitor these sensors when adjusting parameters:
- Battery temperature
- Battery voltage
- Battery current
- Individual cell voltages (if available)

**Warning Signs**:
- Battery temperature >45°C (113°F)
- Significant voltage drop during discharge
- Large voltage delta between cells
- Unusual error states

---

## Implementation Patterns

### Pattern 1: Write and Verify

```python
# Write parameter
response = await client.write_parameter(
    inverter_sn=serial,
    hold_param="HOLD_LEAD_ACID_CHARGE_RATE",
    value_text="100"
)

if not response.get("success", False):
    raise Exception(f"Write failed: {response.get('message')}")

# Wait for parameter to propagate
await asyncio.sleep(2)

# Read back to verify
params = await client.read_parameters(
    inverter_sn=serial,
    param_ids=[0, 1, 2]  # Include charge rate parameter
)

if params.get("HOLD_LEAD_ACID_CHARGE_RATE") != 100:
    raise Exception("Parameter verification failed")
```

### Pattern 2: Multi-Inverter Synchronization

```python
async def set_charge_rate_all_inverters(api_client, serials, rate):
    """Set charge rate across all inverters in parallel."""
    tasks = []
    for serial in serials:
        task = api_client.write_parameter(
            inverter_sn=serial,
            hold_param="HOLD_LEAD_ACID_CHARGE_RATE",
            value_text=str(rate)
        )
        tasks.append(task)

    responses = await asyncio.gather(*tasks, return_exceptions=True)

    # Check for failures
    for serial, response in zip(serials, responses):
        if isinstance(response, Exception):
            logger.error(f"Failed to set rate for {serial}: {response}")
        elif not response.get("success", False):
            logger.error(f"Failed to set rate for {serial}: {response.get('message')}")
```

### Pattern 3: Parameter Refresh After Write

```python
async def write_and_refresh(coordinator, serial, param, value):
    """Write parameter and trigger coordinator refresh."""
    # Write parameter
    response = await coordinator.api.write_parameter(
        inverter_sn=serial,
        hold_param=param,
        value_text=str(value)
    )

    if response.get("success", False):
        # Refresh all device parameters
        await coordinator.refresh_all_device_parameters()

        # Request coordinator refresh
        await coordinator.async_request_refresh()
    else:
        raise Exception(f"Parameter write failed: {response.get('message')}")
```

---

## Caching Strategy

The EG4 Web Monitor integration uses differentiated caching TTLs:

- **Device Discovery**: 15 minutes
- **Battery Info**: 5 minutes
- **Parameters**: 2 minutes (critical for control entity sync)
- **Quick Charge Status**: 1 minute
- **Runtime/Energy Data**: 20 seconds

### Cache Invalidation

Parameters should be re-read after:
1. Any write operation
2. Hourly automatic refresh (parameter drift protection)
3. Manual refresh button press
4. Integration reload

---

## Version History

- **v2.2.7** (November 2025): EntityCategory.CONFIG support
- **v2.2.6** (November 2025): Battery charge/discharge current control added
- **v2.2.4** (November 2025): Decimal support for AC Charge Power
- **v1.5.1** (January 2025): AC Charge SOC Limit and SOC Cut-Off controls
- **v1.4.9** (January 2025): Grid Peak Shaving control
- **v1.4.6** (January 2025): Charge rate controls initial implementation
- **v1.3.1** (September 2024): Battery Backup (EPS) control
- **v1.2.1** (September 2024): System Charge SOC Limit control

---

## References

- **EG4 Web Monitor Integration**: `research/eg4_web_monitor/`
- **API Client**: `research/eg4_web_monitor/custom_components/eg4_web_monitor/eg4_inverter_api/client.py`
- **Number Entities**: `research/eg4_web_monitor/custom_components/eg4_web_monitor/number.py`
- **Battery Current Documentation**: `research/eg4_web_monitor/docs/BATTERY_CURRENT_CONTROL.md`
- **Gap Analysis**: `docs/GAP_ANALYSIS.md`

---

## Future Parameters

Parameters identified but not yet fully documented:

- Individual battery cell voltage parameters
- Temperature sensor parameters
- Advanced GridBOSS/MID parameters
- Parallel group configuration parameters
- Time-based charge/discharge schedules

---

## Contributing

When adding new parameter documentation:

1. Include parameter name (exact string)
2. Specify type (read/write/function)
3. Document range and units
4. Provide use case examples
5. Add version when parameter was discovered
6. Include API request/response examples
7. Document any device-specific limitations
