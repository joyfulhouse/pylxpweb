# Plant Overview Endpoint

**Endpoint**: `POST /WManage/api/plantOverview/list/viewer`
**Discovery Date**: 2025-11-18
**Purpose**: Get comprehensive plant overview with real-time power metrics and inverter details

---

## Overview

This endpoint provides **rich overview data** for all plants, including:
- Real-time power metrics (PV, charge, discharge, consumption)
- Energy totals (daily, lifetime)
- Inverter details (serial numbers, device types, firmware versions)
- Parallel group configuration
- Battery information

This is significantly more comprehensive than `/WManage/web/config/plant/list/viewer` which only provides basic plant configuration.

---

## Request

**Method**: POST
**Content-Type**: `application/x-www-form-urlencoded; charset=UTF-8`
**Authentication**: Required (JSESSIONID cookie)

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `searchText` | string | No | Search filter for plant name/address (empty string returns all) |

### Example Request

```bash
curl 'https://monitor.eg4electronics.com/WManage/api/plantOverview/list/viewer' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  -H 'Cookie: JSESSIONID=...' \
  --data-raw 'searchText='
```

---

## Response

**Status**: 200
**Content-Type**: `application/json`

### Response Structure

```json
{
  "success": true,
  "total": 1,
  "rows": [
    {
      "plantId": 19147,
      "name": "123 Main St",
      "createDateText": "2025-05-05",
      "address": "123 Example Street",
      "timezoneHourOffset": -8,
      "timezoneMinuteOffset": 0,
      "statusText": "normal",
      "statusLocaleText": "Normal",

      // Real-time Power Metrics (watts)
      "ppv": 2642,                    // PV production power
      "ppvText": "2 kW",
      "pCharge": 2039,                // Battery charging power
      "pChargeText": "2 kW",
      "pDisCharge": 0,                // Battery discharging power
      "pDisChargeText": "0 W",
      "pConsumption": -5799,          // Home consumption (negative = importing)
      "pConsumptionText": "-5799 W",

      // Energy Totals
      "todayYielding": 79,            // Today's PV production (×0.1 kWh)
      "todayYieldingTextUnitLess": "7.9",
      "totalYielding": 14295,         // Lifetime PV production (×0.1 kWh)
      "totalYieldingText": "1429.5 kWh",
      "totalYieldingTextUnitLess": "1429.5",
      "totalDischarging": 27718,      // Lifetime battery discharge (×0.1 kWh)
      "totalDischargingText": "2771.8 kWh",
      "totalExport": 61271,           // Lifetime grid export (×0.1 kWh)
      "totalExportText": "6127.1 kWh",
      "totalUsage": 36367,            // Lifetime consumption (×0.1 kWh)
      "totalUsageText": "3636.7 kWh",

      // User Information
      "userId": 411,
      "ownerUser": "EG4 Tech",
      "endUserId": 15415,
      "endUser": "bryanli",

      // Inverter Details
      "inverters": [
        {
          "serialNum": "1234567890",
          "phase": 1,
          "lost": false,
          "dtc": 1,
          "odm": 4,
          "deviceType": 6,
          "subDeviceType": 164,
          "allowExport2Grid": true,
          "powerRating": 6,
          "deviceTypeText4APP": "18KPV",
          "deviceTypeText": "18KPV",
          "batteryType": "LITHIUM",
          "batteryTypeText": "Lithium battery",
          "standard": "fAAB",
          "slaveVersion": 33,
          "fwVersion": 34,
          "allowGenExercise": true,
          "withbatteryData": true,
          "hardwareVersion": -1,
          "voltClass": 0,
          "machineType": 0,
          "protocolVersion": 5
        },
        {
          "serialNum": "0987654321",
          "phase": 1,
          "lost": false,
          "dtc": 1,
          "odm": 0,
          "deviceType": 9,
          "subDeviceType": -1,
          "allowExport2Grid": true,
          "powerRating": 6,
          "parallelMidboxSn": "0987654321",
          "parallelMidboxDeviceText": "Grid Boss",
          "parallelMidboxLost": false,
          "deviceTypeText4APP": "Grid Boss",
          "deviceTypeText": "Grid Boss",
          "batteryType": "LITHIUM",
          "batteryTypeText": "Lithium battery",
          "standard": "IAAB",
          "slaveVersion": 19,
          "fwVersion": 0,
          "allowGenExercise": false,
          "withbatteryData": false,
          "hardwareVersion": -1,
          "voltClass": 0,
          "machineType": 0,
          "protocolVersion": 5
        }
      ],

      // Parallel Group Configuration
      "parallelGroups": [
        {
          "parallelGroup": "A",
          "parallelFirstDeviceSn": "1234567890"
        }
      ]
    }
  ]
}
```

---

## Field Descriptions

### Plant-Level Fields

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `plantId` | int | - | Unique plant identifier |
| `name` | string | - | Plant name |
| `createDateText` | string | - | Creation date (YYYY-MM-DD) |
| `address` | string | - | Plant address |
| `timezoneHourOffset` | int | hours | Timezone offset from UTC |
| `timezoneMinuteOffset` | int | minutes | Minute offset (for half-hour zones) |
| `statusText` | string | - | Plant status ("normal", "fault", etc.) |
| `statusLocaleText` | string | - | Localized status text |

### Power Metrics (Real-Time)

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `ppv` | int | W | Current PV production power |
| `pCharge` | int | W | Current battery charging power |
| `pDisCharge` | int | W | Current battery discharging power |
| `pConsumption` | int | W | Current home consumption (negative = importing from grid) |

### Energy Totals (Cumulative)

| Field | Type | Scaling | Unit | Description |
|-------|------|---------|------|-------------|
| `todayYielding` | int | ÷10 | kWh | Today's PV production |
| `totalYielding` | int | ÷10 | kWh | Lifetime PV production |
| `totalDischarging` | int | ÷10 | kWh | Lifetime battery discharge |
| `totalExport` | int | ÷10 | kWh | Lifetime grid export |
| `totalUsage` | int | ÷10 | kWh | Lifetime consumption |

### Inverter Details

| Field | Type | Description |
|-------|------|-------------|
| `serialNum` | string | Inverter serial number |
| `phase` | int | Phase number (1, 2, or 3) |
| `lost` | boolean | Communication lost status |
| `deviceType` | int | Device type code |
| `deviceTypeText` | string | Human-readable device type |
| `powerRating` | int | Power rating in kW |
| `batteryType` | string | Battery chemistry ("LITHIUM", "LEAD_ACID") |
| `fwVersion` | int | Firmware version |
| `allowExport2Grid` | boolean | Grid export allowed |
| `withbatteryData` | boolean | Has battery data |

---

## Comparison with Other Endpoints

### vs `/WManage/web/config/plant/list/viewer`

| Feature | `/api/plantOverview/list/viewer` | `/web/config/plant/list/viewer` |
|---------|----------------------------------|--------------------------------|
| **Purpose** | Real-time overview + device details | Plant configuration only |
| **Power Metrics** | ✅ Yes (ppv, pCharge, pDisCharge, pConsumption) | ❌ No |
| **Energy Totals** | ✅ Yes (daily, lifetime) | ❌ No |
| **Inverter Details** | ✅ Yes (full device info) | ❌ No |
| **Parallel Groups** | ✅ Yes | ❌ No |
| **Plant Config** | ❌ Limited (no country, timezone details) | ✅ Yes (complete) |
| **Best For** | Dashboard, monitoring, real-time data | Configuration, settings |

### When to Use Each

**Use `/api/plantOverview/list/viewer` for**:
- Dashboard displays
- Real-time monitoring
- Power flow visualization
- Energy statistics
- Device inventory
- System health checks

**Use `/web/config/plant/list/viewer` for**:
- Plant configuration updates
- Timezone/DST management
- Location information
- Notification settings

---

## Use Cases

### 1. Real-Time Dashboard

```python
async def get_dashboard_data(client):
    """Get real-time dashboard data."""
    response = await client._request(
        "POST",
        "/WManage/api/plantOverview/list/viewer",
        data={"searchText": ""}
    )

    for plant in response["rows"]:
        print(f"Plant: {plant['name']}")
        print(f"  PV Production: {plant['ppvText']}")
        print(f"  Battery Charging: {plant['pChargeText']}")
        print(f"  Battery Discharging: {plant['pDisChargeText']}")
        print(f"  Consumption: {plant['pConsumptionText']}")
        print(f"  Today's Yield: {plant['todayYieldingTextUnitLess']} kWh")
```

### 2. Device Inventory

```python
async def list_inverters(client):
    """Get all inverters across all plants."""
    response = await client._request(
        "POST",
        "/WManage/api/plantOverview/list/viewer",
        data={"searchText": ""}
    )

    for plant in response["rows"]:
        print(f"\nPlant: {plant['name']}")
        for inverter in plant["inverters"]:
            print(f"  - {inverter['deviceTypeText']}: {inverter['serialNum']}")
            print(f"    Firmware: {inverter['fwVersion']}")
            print(f"    Battery: {inverter['batteryTypeText']}")
```

### 3. Energy Statistics

```python
async def get_energy_stats(client):
    """Get comprehensive energy statistics."""
    response = await client._request(
        "POST",
        "/WManage/api/plantOverview/list/viewer",
        data={"searchText": ""}
    )

    for plant in response["rows"]:
        total_yield = plant["totalYielding"] / 10  # Convert to kWh
        total_export = plant["totalExport"] / 10
        total_usage = plant["totalUsage"] / 10

        self_consumption = total_yield - total_export
        self_consumption_rate = (self_consumption / total_yield) * 100

        print(f"Plant: {plant['name']}")
        print(f"  Total Production: {total_yield:.1f} kWh")
        print(f"  Total Export: {total_export:.1f} kWh")
        print(f"  Total Usage: {total_usage:.1f} kWh")
        print(f"  Self-Consumption Rate: {self_consumption_rate:.1f}%")
```

---

## Integration Recommendations

### Add to pylxpweb Library

```python
async def get_plant_overview(self, search_text: str = "") -> dict[str, Any]:
    """Get comprehensive plant overview with real-time metrics.

    Args:
        search_text: Optional search filter for plant name/address

    Returns:
        Dict with success status, total count, and rows of plant data
    """
    await self._ensure_authenticated()

    data = {"searchText": search_text}
    return await self._request(
        "POST",
        "/WManage/api/plantOverview/list/viewer",
        data=data
    )
```

### Potential Data Models

```python
@dataclass
class PlantOverview:
    """Plant overview with real-time metrics."""
    plant_id: int
    name: str
    address: str
    status: str

    # Real-time power (W)
    pv_power: int
    charge_power: int
    discharge_power: int
    consumption: int

    # Energy totals (kWh)
    today_yield: float
    total_yield: float
    total_discharge: float
    total_export: float
    total_usage: float

    # Device information
    inverters: list[InverterInfo]
    parallel_groups: list[ParallelGroup]
```

---

## Notes

- **Refresh Rate**: This endpoint provides real-time data, suitable for frequent polling (e.g., every 5-10 seconds for live dashboards)
- **Scaling**: Energy values are scaled by 10 (divide by 10 to get kWh)
- **Negative Consumption**: `pConsumption` can be negative when importing from grid
- **Search Filter**: `searchText` parameter filters by plant name or address (substring match)
- **Multiple Plants**: Returns array of all plants user has access to

---

## Related Documentation

- Plant Configuration: `/WManage/web/config/plant/list/viewer`
- Inverter Runtime: `/WManage/api/inverter/getInverterRuntime`
- Device Discovery: `/WManage/api/inverterOverview/getParallelGroupDetails`
