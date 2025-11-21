# Plant List Viewer Endpoint

**Endpoint**: `POST /WManage/web/config/plant/list/viewer`
**Purpose**: Get plant configuration details with pagination and filtering
**Status**: Already implemented in `client.get_plant_details()`

---

## Overview

This is the **primary endpoint** for retrieving plant configuration data. It provides:
- Plant identification and naming
- Location and timezone information
- Notification settings
- Contact information
- **Pagination support**
- **Targeted plant filtering** via `targetPlantId`

This endpoint is already used by `LuxpowerClient.get_plant_details()` but with extended parameters.

---

## Request

**Method**: POST
**Content-Type**: `application/x-www-form-urlencoded; charset=UTF-8`
**Authentication**: Required (JSESSIONID cookie)

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `page` | int | Yes | Page number (1-indexed) |
| `rows` | int | Yes | Number of rows per page |
| `searchText` | string | No | Search filter for plant name/address |
| `targetPlantId` | int | No | Specific plant ID to retrieve (optional) |
| `sort` | string | No | Sort field (e.g., "createDate") |
| `order` | string | No | Sort order ("asc" or "desc") |

### Example Requests

#### Get All Plants (Paginated)

```bash
curl 'https://monitor.eg4electronics.com/WManage/web/config/plant/list/viewer' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  -H 'Cookie: JSESSIONID=...' \
  --data-raw 'page=1&rows=10&searchText=&sort=createDate&order=desc'
```

#### Get Specific Plant by ID

```bash
curl 'https://monitor.eg4electronics.com/WManage/web/config/plant/list/viewer' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  -H 'Cookie: JSESSIONID=...' \
  --data-raw 'page=1&rows=10&searchText=&targetPlantId=19147&sort=createDate&order=desc'
```

---

## Response

**Status**: 200
**Content-Type**: `application/json`

### Response Structure

```json
{
  "total": 1,
  "rows": [
    {
      "id": 19147,
      "plantId": 19147,
      "name": "123 Main St",
      "nominalPower": 19000,
      "country": "United States of America",
      "currentTimezoneWithMinute": -800,
      "timezone": "GMT -8",
      "daylightSavingTime": false,
      "createDate": "2025-05-05",
      "noticeFault": false,
      "noticeWarn": false,
      "noticeEmail": "",
      "noticeEmail2": "",
      "contactPerson": "",
      "contactPhone": "",
      "address": "123 Example Street"
    }
  ]
}
```

---

## Field Descriptions

### Plant Identification

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Plant ID (same as plantId) |
| `plantId` | int | Unique plant identifier |
| `name` | string | Plant/station name |
| `createDate` | string | Creation date (YYYY-MM-DD format) |

### Location & Timezone

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `country` | string | - | Human-readable country name |
| `timezone` | string | - | Human-readable timezone (e.g., "GMT -8") |
| `currentTimezoneWithMinute` | int | minutes | Timezone offset in minutes (-800 = -8 hours) |
| `daylightSavingTime` | boolean | - | DST enabled status |
| `address` | string | - | Plant physical address |

### System Configuration

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `nominalPower` | int | W | Nominal power rating (system capacity) |

### Notification Settings

| Field | Type | Description |
|-------|------|-------------|
| `noticeFault` | boolean | Send fault notifications |
| `noticeWarn` | boolean | Send warning notifications |
| `noticeEmail` | string | Primary notification email |
| `noticeEmail2` | string | Secondary notification email |

### Contact Information

| Field | Type | Description |
|-------|------|-------------|
| `contactPerson` | string | Contact person name |
| `contactPhone` | string | Contact phone number |

---

## Parameter Details

### Pagination

**Basic Pagination**:
```json
{
  "page": 1,
  "rows": 10
}
```

**Calculate Total Pages**:
```python
total_pages = ceil(response["total"] / rows)
```

### Targeting Specific Plant

**Key Feature**: Use `targetPlantId` to retrieve a specific plant directly:

```json
{
  "page": 1,
  "rows": 10,
  "targetPlantId": "19147"  // Returns only this plant
}
```

This is **more efficient** than retrieving all plants and filtering client-side.

### Sorting

**Available Sort Fields**:
- `createDate` - Creation date
- `name` - Plant name
- `nominalPower` - System capacity

**Sort Orders**:
- `asc` - Ascending
- `desc` - Descending

**Example**:
```json
{
  "sort": "createDate",
  "order": "desc"  // Newest plants first
}
```

### Search Filter

**Search by Plant Name or Address**:
```json
{
  "searchText": "Example"  // Matches "Example Street"
}
```

---

## Current Implementation in pylxpweb

The `LuxpowerClient.get_plant_details()` method already uses this endpoint:

```python
async def get_plant_details(self, plant_id: int | str) -> dict[str, Any]:
    """Get detailed plant/station configuration information."""
    data = {
        "page": 1,
        "rows": 20,
        "searchText": "",
        "targetPlantId": str(plant_id),  # ✅ Uses targetPlantId
        "sort": "createDate",
        "order": "desc",
    }

    response = await self._request(
        "POST",
        "/WManage/web/config/plant/list/viewer",
        data=data
    )

    if isinstance(response, dict) and response.get("rows"):
        return dict(response["rows"][0])

    raise LuxpowerAPIError(f"Plant {plant_id} not found")
```

---

## Enhanced Usage Patterns

### 1. Get All Plants (Pagination)

```python
async def get_all_plants_paginated(client, page=1, rows=10):
    """Get plants with pagination."""
    response = await client._request(
        "POST",
        "/WManage/web/config/plant/list/viewer",
        data={
            "page": page,
            "rows": rows,
            "searchText": "",
            "sort": "createDate",
            "order": "desc"
        }
    )

    total = response["total"]
    plants = response["rows"]
    total_pages = (total + rows - 1) // rows

    return {
        "plants": plants,
        "total": total,
        "page": page,
        "pages": total_pages,
        "has_next": page < total_pages
    }
```

### 2. Search Plants

```python
async def search_plants(client, search_term):
    """Search plants by name or address."""
    response = await client._request(
        "POST",
        "/WManage/web/config/plant/list/viewer",
        data={
            "page": 1,
            "rows": 100,
            "searchText": search_term,
            "sort": "name",
            "order": "asc"
        }
    )

    return response["rows"]
```

### 3. Get Plant by ID (Optimized)

```python
async def get_plant_by_id(client, plant_id):
    """Get specific plant directly (no filtering)."""
    response = await client._request(
        "POST",
        "/WManage/web/config/plant/list/viewer",
        data={
            "page": 1,
            "rows": 1,  # Only need 1 result
            "searchText": "",
            "targetPlantId": str(plant_id),  # Direct targeting
            "sort": "createDate",
            "order": "desc"
        }
    )

    if response.get("rows"):
        return response["rows"][0]

    return None
```

### 4. List Plants by Capacity

```python
async def get_plants_by_capacity(client):
    """Get plants sorted by system capacity."""
    response = await client._request(
        "POST",
        "/WManage/web/config/plant/list/viewer",
        data={
            "page": 1,
            "rows": 100,
            "searchText": "",
            "sort": "nominalPower",
            "order": "desc"  # Largest first
        }
    )

    return response["rows"]
```

---

## Comparison with Other Endpoints

| Feature | `/web/config/plant/list/viewer` | `/api/plantOverview/list/viewer` |
|---------|--------------------------------|----------------------------------|
| **Purpose** | Plant configuration | Plant monitoring |
| **Pagination** | ✅ Yes | ❌ No |
| **Targeting** | ✅ targetPlantId | ❌ No |
| **Sorting** | ✅ Multiple fields | ❌ No |
| **Search** | ✅ Name/address | ✅ Name/address |
| **Config Data** | ✅ Complete (timezone, DST, notifications) | ❌ Limited |
| **Real-time Metrics** | ❌ No | ✅ Yes (power, energy) |
| **Best For** | Configuration, settings | Monitoring, dashboard |

---

## Use Case Selection

**Use `/web/config/plant/list/viewer` when**:
- Retrieving plant configuration for updates
- Accessing timezone or DST settings
- Getting notification settings
- Needing pagination for large plant lists
- Searching plants by name/address
- Sorting plants by capacity or date

**Use `/api/plantOverview/list/viewer` when**:
- Displaying real-time power metrics
- Showing energy statistics
- Building monitoring dashboards
- Need inverter details along with plant data

---

## Integration Notes

### Current pylxpweb Usage

The library currently uses this endpoint optimally:
- ✅ Uses `targetPlantId` for direct access
- ✅ Includes pagination parameters
- ✅ Uses sorting for consistency
- ❌ Doesn't expose pagination to users

### Potential Enhancements

```python
# Add pagination support to get_plants()
async def get_plants(
    self,
    page: int = 1,
    rows: int = 20,
    search_text: str = "",
    sort_by: str = "createDate",
    sort_order: str = "desc"
) -> PlantListResponse:
    """Get paginated list of plants with filtering and sorting."""
    # Implementation using full parameter set
```

---

## Notes

- **Pagination Required**: For users with many plants (>20), pagination is essential
- **Targeting Performance**: Using `targetPlantId` is more efficient than fetching all and filtering
- **Timezone Data**: Only source for timezone and DST settings
- **Empty Strings**: Optional fields (email, contact) return empty strings, not null
- **Timezone Format**: `currentTimezoneWithMinute` uses total minutes (e.g., -800 = -8 hours = -480 minutes would be wrong, it's actually -800 which represents the offset value)

---

## Related Documentation

- Plant Overview: `/WManage/api/plantOverview/list/viewer`
- Plant Configuration Update: `/WManage/web/config/plant/edit`
- Locale Endpoints: `/WManage/locale/region`, `/WManage/locale/country`
