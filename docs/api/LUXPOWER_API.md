# Luxpower/EG4 Web Monitoring API Documentation

**API Base URLs**: Multiple regional endpoints available

- **US (EG4 Electronics)**: `https://monitor.eg4electronics.com` (default for EG4 devices)
- **US (Luxpower)**: `https://us.luxpowertek.com`
- **Americas (Luxpower)**: `https://na.luxpowertek.com` (Brazil, Latin America)
- **Europe (Luxpower)**: `https://eu.luxpowertek.com`
- **Asia Pacific (Luxpower)**: `https://sea.luxpowertek.com`
- **Middle East & Africa (Luxpower)**: `https://af.luxpowertek.com`
- **China (Luxpower)**: `https://server.luxpowertek.com`

**Default Recommendation**: Use `https://monitor.eg4electronics.com` for EG4-branded devices in North America. For Luxpower-branded devices, use the regional endpoint where your account was registered.

**Last Updated**: 2025-11-18

**Sources**: Based on comprehensive analysis of production EG4 Web Monitor Home Assistant integration and sample API responses.

## Table of Contents

1. [Choosing the Right Endpoint](#choosing-the-right-endpoint)
2. [Authentication](#authentication)
3. [Station/Plant Management](#stationplant-management)
4. [Device Discovery](#device-discovery)
5. [Runtime Data](#runtime-data)
6. [Energy Statistics](#energy-statistics)
7. [Battery Information](#battery-information)
8. [GridBOSS/MID Devices](#gridbossmid-devices)
9. [Control Operations](#control-operations)
10. [Firmware Management](#firmware-management)
11. [Data Scaling Reference](#data-scaling-reference)
12. [Error Handling](#error-handling)

---

## Choosing the Right Endpoint

### Available Endpoints

| Endpoint | Region | Brand | Description |
|----------|--------|-------|-------------|
| `https://monitor.eg4electronics.com` | North America | EG4 | EG4-branded devices (default) |
| `https://us.luxpowertek.com` | North America | Luxpower | Luxpower-branded devices in US/Canada |
| `https://na.luxpowertek.com` | Americas | Luxpower | Brazil, Latin America, other Americas |
| `https://eu.luxpowertek.com` | Europe | Luxpower | Luxpower-branded devices in Europe |
| `https://sea.luxpowertek.com` | Asia Pacific | Luxpower | Southeast Asia, Australia, etc. |
| `https://af.luxpowertek.com` | Middle East & Africa | Luxpower | Middle East and Africa region |
| `https://server.luxpowertek.com` | China | Luxpower | China mainland |

### Selection Guide

**1. By Device Brand**:
- If you have **EG4-branded devices** (FlexBOSS, 18KPV, 12KPV, GridBOSS): Use `https://monitor.eg4electronics.com`
- If you have **Luxpower-branded devices**: Use the regional Luxpower endpoint where your account was registered

**2. By Account Registration**:
- Use the endpoint where your monitoring account was originally created
- Accounts are typically region/brand-specific and won't work across endpoints
- If you can log in to the web portal or mobile app, use that same endpoint

**3. By Geographic Location**:
- **North America** (EG4): `https://monitor.eg4electronics.com`
- **North America** (Luxpower): `https://us.luxpowertek.com`
- **Americas** (Brazil, Latin America): `https://na.luxpowertek.com`
- **Europe**: `https://eu.luxpowertek.com`
- **Asia Pacific**: `https://sea.luxpowertek.com`
- **Middle East & Africa**: `https://af.luxpowertek.com`
- **China**: `https://server.luxpowertek.com`

### Testing Endpoint Connectivity

**Method 1: Manual Testing**

1. Try logging into the web portals:
   - https://us.luxpowertek.com
   - https://eu.luxpowertek.com
   - https://monitor.eg4electronics.com

2. Check which mobile app you use:
   - "Luxpower" app → Luxpower endpoint
   - "EG4 Monitor" app → EG4 endpoint

3. Test API login with each endpoint (see [Authentication](#authentication) section)

### Implementation

The library should default to `https://monitor.eg4electronics.com` but allow full customization:

```python
# Default (EG4 North America)
client = LuxpowerClient(username, password)

# Explicit EG4
client = LuxpowerClient(username, password, base_url="https://monitor.eg4electronics.com")

# Luxpower US
client = LuxpowerClient(username, password, base_url="https://us.luxpowertek.com")

# Luxpower EU
client = LuxpowerClient(username, password, base_url="https://eu.luxpowertek.com")
```

### Notes

- All endpoints use identical API structure and endpoints
- Only the base URL differs; all path endpoints remain the same
- Session cookies and authentication work the same across all endpoints
- Some features may be enabled/disabled based on regional regulations
- Future endpoints may be added as Luxpower/EG4 expand to new regions

---

## Authentication

### Login

**Endpoint**: `POST /WManage/api/login`

**Description**: Authenticate and establish a session. Session duration is approximately 2 hours.

**Request Headers**:
```
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Accept: application/json
User-Agent: Mozilla/5.0 (compatible; EG4InverterAPI/1.0)
```

**Request Body** (URL-encoded):
```
account={username}&password={password}
```

**Example Request**:
```http
POST /WManage/api/login HTTP/1.1
Host: monitor.eg4electronics.com
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

account=user@example.com&password=mypassword123
```

**Regional Endpoints**:
The same API endpoints and authentication flow apply to all regional base URLs:
- `https://us.luxpowertek.com/WManage/api/login`
- `https://eu.luxpowertek.com/WManage/api/login`
- `https://monitor.eg4electronics.com/WManage/api/login`

Choose the appropriate base URL based on:
- **Device Brand**: EG4 devices → `monitor.eg4electronics.com`, Luxpower devices → regional Luxpower endpoint
- **Geographic Region**: EU users → `eu.luxpowertek.com`, US users → `us.luxpowertek.com` or `monitor.eg4electronics.com`
- **Account Registration**: Use the endpoint where your account was created

**Response**:
```json
{
  "success": true,
  "plants": [...],
  "user": {...}
}
```

**Response Headers**:
```
Set-Cookie: JSESSIONID={session_id}; Path=/WManage; HttpOnly
```

**Session Management**:
- Extract `JSESSIONID` from response cookies
- Include in all subsequent requests: `Cookie: JSESSIONID={session_id}`
- Session expires after ~2 hours
- Implement proactive refresh when < 5 minutes remaining
- Handle 401 responses with automatic re-authentication

**Notes**:
- Session ID must be extracted from response cookies
- Some implementations also store session in response JSON
- Always clear cookie jar before re-authentication to prevent conflicts

---

## Station/Plant Management

### Get Plants List

**Endpoint**: `POST /WManage/web/config/plant/list/viewer`

**Description**: Retrieve list of all stations/plants associated with the authenticated account.

**Authentication**: Required (include JSESSIONID cookie)

**Request Body** (URL-encoded):
```
sort=createDate&order=desc&searchText=
```

**Response**:
```json
{
  "rows": [
    {
      "id": 12345,
      "plantId": 12345,
      "name": "My Solar Station",
      "nominalPower": 0,
      "country": "United States of America",
      "currentTimezoneWithMinute": -700,
      "timezone": "GMT -8",
      "daylightSavingTime": true,
      "createDate": "2025-05-05",
      "noticeFault": false,
      "noticeWarn": false,
      "noticeEmail": "",
      "noticeEmail2": "",
      "contactPerson": "",
      "contactPhone": "",
      "address": "123 Example Street"
    }
  ],
  "total": 1
}
```

**Key Fields**:
- `plantId`: Unique identifier for the station (used in subsequent API calls)
- `name`: Display name for the station
- `timezone`: Timezone string
- `currentTimezoneWithMinute`: Timezone offset in minutes (negative = west of GMT)

---

## Device Discovery

### Get Parallel Group Details

**Endpoint**: `POST /WManage/api/inverterOverview/getParallelGroupDetails`

**Description**: Retrieve device hierarchy including parallel groups, inverters, and GridBOSS devices.

**Authentication**: Required

**Request Body** (URL-encoded):
```
plantId={plantId}
```

**Response Structure**:
```json
{
  "success": true,
  "parallelGroups": [
    {
      "groupId": "group_1",
      "name": "Parallel Group 1",
      "inverters": [
        {
          "serialNum": "1234567890",
          "model": 624320,
          "modelText": "0x986C0",
          "deviceTypeText4APP": "FlexBOSS 12K",
          "status": "normal"
        }
      ],
      "midDevice": {
        "serialNum": "0987654321",
        "model": 624321,
        "modelText": "GridBOSS",
        "deviceTypeText4APP": "GridBOSS MID"
      }
    }
  ]
}
```

### Get Inverter Overview List

**Endpoint**: `POST /WManage/api/inverterOverview/list`

**Description**: Get flat list of all devices in a station.

**Authentication**: Required

**Request Body** (URL-encoded):
```
plantId={plantId}
```

**Response**:
```json
{
  "success": true,
  "devices": [
    {
      "serialNum": "1234567890",
      "model": 624320,
      "modelText": "0x986C0",
      "deviceTypeText4APP": "FlexBOSS 12K",
      "firmwareVersion": "fAAB-2122",
      "status": "normal",
      "lost": false,
      "isParallelEnabled": true
    }
  ]
}
```

**Device Types**:
- **Standard Inverters**: FlexBOSS21, FlexBOSS18, 18KPV, 12KPV, XP series
- **GridBOSS**: MID (Microgrid Interconnection Device) for grid management (only in parallel setups)
- **Batteries**: Individual battery modules (discovered via battery info endpoint)

**Device Hierarchy**:

*Single Inverter Setup* (most common):
```
Station/Plant (plantId)
└── Inverter (serialNum)
    └── Battery Modules (0 or more)
```

*Parallel Group Setup* (multi-inverter or GridBOSS):
```
Station/Plant (plantId)
└── Parallel Group (groupId)
    ├── GridBOSS / MID Device (optional)
    └── Inverters (1 or more)
        └── Battery Modules (0 or more per inverter)
```

**Important**:
- Parallel groups are **optional** - only present in multi-inverter or GridBOSS installations
- A parallel group can have 1+ inverters (typically 2+ for actual parallel operation)
- A parallel group with 1 inverter + GridBOSS is valid (GridBOSS manages grid interaction)
- Single inverters without GridBOSS are directly associated with plants (no parallel group)
- The login response includes all inverters under `plants[].inverters[]`
- The `parallelGroups[]` array is empty for single-inverter setups without GridBOSS

---

## Runtime Data

### Get Inverter Runtime

**Endpoint**: `POST /WManage/api/inverter/getInverterRuntime`

**Description**: Retrieve real-time operational data for an inverter.

**Authentication**: Required

**Request Body** (URL-encoded):
```
serialNum={serialNum}
```

**Response** (values scaled - see [Data Scaling Reference](#data-scaling-reference)):
```json
{
  "success": true,
  "serialNum": "1234567890",
  "fwCode": "fAAB-2122",
  "powerRatingText": "12kW",
  "lost": false,
  "hasRuntimeData": true,
  "statusText": "normal",
  "model": 624320,
  "modelText": "0x986C0",
  "serverTime": "2025-09-10 16:48:01",
  "deviceTime": "2025-09-10 09:48:01",

  "vpv1": 0,
  "vpv2": 1,
  "vpv3": 2,
  "ppv1": 0,
  "ppv2": 0,
  "ppv3": 0,
  "ppv": 0,

  "vacr": 2411,
  "vacs": 256,
  "vact": 0,
  "fac": 5998,
  "pf": "1",

  "vepsr": 2410,
  "vepss": 2560,
  "vepst": 64,
  "feps": 5998,
  "seps": 0,
  "peps": 0,

  "pToGrid": 0,
  "pToUser": 1030,
  "pinv": 0,
  "prec": 1067,

  "tinner": 39,
  "tradiator1": 45,
  "tradiator2": 43,
  "tBat": 2,

  "vBus1": 3703,
  "vBus2": 3228,
  "status": 32,

  "pCharge": 1045,
  "pDisCharge": 0,
  "batPower": 1045,
  "batteryColor": "green",
  "soc": 71,
  "vBat": 530,

  "batShared": false,
  "isParallelEnabled": true,
  "batteryType": "LITHIUM",
  "batParallelNum": "3",
  "batCapacity": "840",

  "maxChgCurr": 6000,
  "maxDischgCurr": 6000,
  "maxChgCurrValue": 600,
  "maxDischgCurrValue": 600,
  "bmsCharge": true,
  "bmsDischarge": true,
  "bmsForceCharge": false,

  "_12KAcCoupleInverterFlow": true,
  "_12KAcCoupleInverterData": false,
  "acCouplePower": 1066,

  "_12KUsingGenerator": false,
  "genVolt": 0,
  "genFreq": 0,
  "genPower": 1074,
  "genDryContact": "OFF",

  "consumptionPower114": 1090,
  "consumptionPower": 0,
  "pEpsL1N": 0,
  "pEpsL2N": 0,
  "haspEpsLNValue": true,

  "directions": {
    "inverterArrowDir": "toInverter"
  },

  "hasUnclosedQuickChargeTask": false,
  "hasUnclosedQuickDischargeTask": false,
  "hasEpsOverloadRecoveryTime": false,
  "allowGenExercise": true,
  "remainTime": 0
}
```

**Key Fields**:

| Field | Description | Scaling | Unit |
|-------|-------------|---------|------|
| `vpv1`, `vpv2`, `vpv3` | PV input voltages | ÷100 | V |
| `ppv1`, `ppv2`, `ppv3` | PV input power | none | W |
| `ppv` | Total PV power | none | W |
| `vacr`, `vacs`, `vact` | AC output voltage (R/S/T phases) | ÷100 | V |
| `fac` | AC frequency | ÷100 | Hz |
| `pf` | Power factor | string | - |
| `vepsr`, `vepss`, `vepst` | EPS voltage (R/S/T phases) | ÷100 | V |
| `feps` | EPS frequency | ÷100 | Hz |
| `seps` | EPS status | none | - |
| `peps` | EPS power | none | W |
| `pToGrid` | Power to grid (export) | none | W |
| `pToUser` | Power to load (consumption) | none | W |
| `pinv` | Inverter output power | none | W |
| `prec` | Rectifier power | none | W |
| `tinner` | Inner temperature | none | °C |
| `tradiator1`, `tradiator2` | Radiator temperatures | none | °C |
| `tBat` | Battery temperature | none | °C |
| `vBus1`, `vBus2` | DC bus voltages | ÷100 | V |
| `pCharge` | Battery charge power | none | W |
| `pDisCharge` | Battery discharge power | none | W |
| `batPower` | Net battery power (+ charge, - discharge) | none | W |
| `soc` | State of charge | none | % |
| `vBat` | Battery voltage | ÷100 | V |
| `maxChgCurr`, `maxDischgCurr` | Max charge/discharge current | ÷100 | A |
| `acCouplePower` | AC coupling power | none | W |
| `genVolt` | Generator voltage | ÷100 | V |
| `genFreq` | Generator frequency | ÷100 | Hz |
| `genPower` | Generator power | none | W |
| `consumptionPower` | Total consumption power | none | W |

**Caching**: Recommended TTL of 20 seconds for runtime data.

---

## Energy Statistics

### Get Inverter Energy Info

**Endpoint**: `POST /WManage/api/inverter/getInverterEnergyInfo`

**Description**: Retrieve energy production statistics for an inverter.

**Authentication**: Required

**Request Body** (URL-encoded):
```
serialNum={serialNum}
```

**Response**:
```json
{
  "success": true,
  "serialNum": "1234567890",
  "eToday": 12.5,
  "eMonth": 350.2,
  "eYear": 4200.8,
  "eTotal": 42000.0,
  "gridSellToday": 5.2,
  "gridSellMonth": 120.5,
  "gridSellYear": 1500.3,
  "gridBuyToday": 2.1,
  "gridBuyMonth": 45.3,
  "gridBuyYear": 520.7,
  "consumptionToday": 15.3,
  "consumptionMonth": 425.8,
  "consumptionYear": 5100.2,
  "chargeToday": 8.5,
  "chargeMonth": 245.6,
  "chargeYear": 2950.4,
  "dischargeToday": 6.2,
  "dischargeMonth": 180.4,
  "dischargeYear": 2100.8
}
```

**Units**: All energy values in kWh

**Caching**: Recommended TTL of 20 seconds.

### Get Parallel Group Energy Info

**Endpoint**: `POST /WManage/api/inverter/getInverterEnergyInfoParallel`

**Description**: Retrieve aggregated energy statistics for a parallel group of inverters.

**Authentication**: Required

**Request Body** (URL-encoded):
```
serialNum={serialNum}
```

**Response**: Similar structure to individual inverter energy info, but aggregated across all inverters in the parallel group.

**Caching**: Recommended TTL of 20 seconds.

---

## Battery Information

### Get Battery Info

**Endpoint**: `POST /WManage/api/battery/getBatteryInfo`

**Description**: Retrieve battery information including individual battery module details.

**Authentication**: Required

**Request Body** (URL-encoded):
```
serialNum={serialNum}
```

**Response**:
```json
{
  "success": true,
  "serialNum": "1234567890",
  "batteryType": "LITHIUM",
  "batParallelNum": 3,
  "batCapacity": 840,
  "soc": 71,
  "vBat": 530,
  "iBat": 1500,
  "pBat": 1045,
  "tBat": 25,
  "bmsCharge": true,
  "bmsDischarge": true,
  "bmsForceCharge": false,
  "batteryArray": [
    {
      "batteryKey": "01",
      "soc": 72,
      "voltage": 5300,
      "current": 500,
      "power": 265,
      "temperature": 24,
      "soh": 99,
      "cycleCount": 125,
      "cellVoltageMax": 3350,
      "cellVoltageMin": 3320,
      "cellVoltageDelta": 30,
      "cellVoltages": [3350, 3345, 3340, 3335, 3330, 3325, 3320, 3320, 3325, 3330, 3335, 3340, 3345, 3350, 3350, 3345]
    },
    {
      "batteryKey": "02",
      "soc": 71,
      "voltage": 5290,
      "current": 495,
      "power": 261,
      "temperature": 25,
      "soh": 99,
      "cycleCount": 128,
      "cellVoltageMax": 3345,
      "cellVoltageMin": 3315,
      "cellVoltageDelta": 30,
      "cellVoltages": [3345, 3340, 3335, 3330, 3325, 3320, 3315, 3315, 3320, 3325, 3330, 3335, 3340, 3345, 3345, 3340]
    },
    {
      "batteryKey": "03",
      "soc": 70,
      "voltage": 5280,
      "current": 505,
      "power": 266,
      "temperature": 26,
      "soh": 98,
      "cycleCount": 132,
      "cellVoltageMax": 3340,
      "cellVoltageMin": 3310,
      "cellVoltageDelta": 30,
      "cellVoltages": [3340, 3335, 3330, 3325, 3320, 3315, 3310, 3310, 3315, 3320, 3325, 3330, 3335, 3340, 3340, 3335]
    }
  ]
}
```

**Battery Array Field Scaling**:

| Field | Description | Scaling | Unit |
|-------|-------------|---------|------|
| `batteryKey` | Unique battery identifier | none | string |
| `soc` | State of charge | none | % |
| `voltage` | Battery voltage | ÷100 | V |
| `current` | Battery current | ÷100 | A |
| `power` | Battery power | none | W |
| `temperature` | Battery temperature | none | °C |
| `soh` | State of health | none | % |
| `cycleCount` | Charge/discharge cycles | none | count |
| `cellVoltageMax` | Highest cell voltage | ÷1000 | V |
| `cellVoltageMin` | Lowest cell voltage | ÷1000 | V |
| `cellVoltageDelta` | Cell imbalance (max - min) | ÷1000 | V |
| `cellVoltages` | Individual cell voltages | ÷1000 | V |

**Notes**:
- `batteryKey` is used to create unique entity IDs for individual batteries
- `batteryArray` contains detailed information for each battery module
- Cell voltage delta is useful for detecting battery imbalance issues
- Not all batteries report all fields

**Caching**: Recommended TTL of 5 minutes (battery info changes slowly).

---

## GridBOSS/MID Devices

### Get MidBox Runtime

**Endpoint**: `POST /WManage/api/midbox/getMidboxRuntime`

**Description**: Retrieve runtime data for GridBOSS/MID (Microgrid Interconnection Device).

**Authentication**: Required

**Request Body** (URL-encoded):
```
serialNum={serialNum}
```

**Response**:
```json
{
  "success": true,
  "serialNum": "0987654321",
  "gridVoltageL1": 12050,
  "gridVoltageL2": 12000,
  "gridVoltageL3": 0,
  "gridCurrentL1": 850,
  "gridCurrentL2": 820,
  "gridCurrentL3": 0,
  "gridPowerL1": 1024,
  "gridPowerL2": 984,
  "gridPowerL3": 0,
  "gridFrequency": 6000,
  "loadPower": 2500,
  "loadVoltage": 12025,
  "loadCurrent": 2080,
  "smartPort1Status": "ON",
  "smartPort1Power": 500,
  "smartPort2Status": "OFF",
  "smartPort2Power": 0,
  "smartPort3Status": "AUTO",
  "smartPort3Power": 300,
  "smartPort4Status": "OFF",
  "smartPort4Power": 0,
  "acCoupleEnabled": true,
  "acCouplePower": 1500,
  "upsMode": false,
  "generatorStatus": "IDLE",
  "generatorVoltage": 0,
  "generatorFrequency": 0,
  "generatorPower": 0
}
```

**Field Scaling**:

| Field | Description | Scaling | Unit |
|-------|-------------|---------|------|
| `gridVoltageL1/L2/L3` | Grid voltage per phase | ÷100 | V |
| `gridCurrentL1/L2/L3` | Grid current per phase | ÷100 | A |
| `gridPowerL1/L2/L3` | Grid power per phase | none | W |
| `gridFrequency` | Grid frequency | ÷100 | Hz |
| `loadPower` | Total load power | none | W |
| `loadVoltage` | Load voltage | ÷100 | V |
| `loadCurrent` | Load current | ÷100 | A |
| `smartPort[1-4]Power` | Smart port power | none | W |
| `acCouplePower` | AC coupling power | none | W |
| `generatorVoltage` | Generator voltage | ÷100 | V |
| `generatorFrequency` | Generator frequency | ÷100 | Hz |
| `generatorPower` | Generator power | none | W |

**Smart Port Status Values**:
- `"ON"` - Port enabled and active
- `"OFF"` - Port disabled
- `"AUTO"` - Port in automatic mode

**Generator Status Values**:
- `"IDLE"` - Generator not running
- `"RUNNING"` - Generator active
- `"EXERCISE"` - Generator exercise mode

**Error Handling**:
- Returns `DEVICE_ERROR_UNSUPPORT_DEVICE_TYPE` if serial number is not a GridBOSS device
- Standard inverters do not support MidBox operations

**Caching**: Recommended TTL of 20 seconds.

---

## Control Operations

### Read Parameters

**Endpoint**: `POST /WManage/web/maintain/remoteRead/read`

**Description**: Read inverter configuration parameters.

**Authentication**: Required

**Request Body** (URL-encoded):
```
serialNum={serialNum}&paramIds={paramId1},{paramId2},{paramId3}
```

**Example Request**:
```
serialNum=1234567890&paramIds=21,22,23
```

**Response**:
```json
{
  "success": true,
  "serialNum": "1234567890",
  "parameters": [
    {
      "paramId": 21,
      "paramName": "SYSTEM_CHARGE_SOC_LIMIT",
      "value": 100,
      "unit": "%"
    },
    {
      "paramId": 22,
      "paramName": "AC_CHARGE_POWER",
      "value": 3000,
      "unit": "W"
    },
    {
      "paramId": 23,
      "paramName": "PV_CHARGE_POWER",
      "value": 12000,
      "unit": "W"
    }
  ]
}
```

**Common Parameter IDs**:

| ID | Name | Description | Range | Unit |
|----|------|-------------|-------|------|
| 21 | System Charge SOC Limit | Maximum battery charge level | 0-100 | % |
| 22 | AC Charge Power | AC charging power limit | 0-max rated | W |
| 23 | PV Charge Power | PV charging power limit | 0-max rated | W |
| 64 | Operating Mode | 0=Normal, 1=Standby | 0-1 | enum |
| 65 | Quick Charge | 0=Off, 1=On | 0-1 | bool |
| 66 | Battery Backup (EPS) | 0=Off, 1=On | 0-1 | bool |

**Caching**: Recommended TTL of 2 minutes (parameters change with user controls).

### Write Parameters

**Endpoint**: `POST /WManage/web/maintain/remoteSet/write`

**Description**: Write inverter configuration parameters.

**Authentication**: Required

**Request Body** (URL-encoded):
```
serialNum={serialNum}&data={paramId1}:{value1},{paramId2}:{value2}
```

**Example Request**:
```
serialNum=1234567890&data=21:90,22:2500
```
This sets System Charge SOC Limit to 90% and AC Charge Power to 2500W.

**Response**:
```json
{
  "success": true,
  "serialNum": "1234567890",
  "message": "Parameters updated successfully"
}
```

**Notes**:
- Parameters are written immediately
- Inverter may take several seconds to apply changes
- Invalid values may be rejected with error response
- Some parameters may require specific operating modes

### Function Control

**Endpoint**: `POST /WManage/web/maintain/remoteSet/functionControl`

**Description**: Control inverter functions like quick charge and EPS mode.

**Authentication**: Required

**Request Body** (URL-encoded):
```
serialNum={serialNum}&function={functionName}&value={0|1}
```

**Example Request**:
```
serialNum=1234567890&function=quickCharge&value=1
```

**Supported Functions**:
- `quickCharge` - Enable/disable quick battery charging
- `batteryBackup` - Enable/disable EPS (Emergency Power Supply) mode
- `operatingMode` - Switch between Normal (0) and Standby (1) modes

**Response**:
```json
{
  "success": true,
  "serialNum": "1234567890",
  "function": "quickCharge",
  "value": 1,
  "message": "Function activated successfully"
}
```

### Get Quick Charge Status

**Endpoint**: `POST /WManage/web/config/quickCharge/getStatusInfo`

**Description**: Check if quick charge task is active.

**Authentication**: Required

**Request Body** (URL-encoded):
```
serialNum={serialNum}
```

**Response**:
```json
{
  "success": true,
  "serialNum": "1234567890",
  "hasUnclosedQuickChargeTask": true,
  "taskStartTime": "2025-09-10 14:00:00",
  "taskEndTime": "2025-09-10 18:00:00"
}
```

**Caching**: Recommended TTL of 1 minute (status changes during operations).

---

## Firmware Management

The API provides **read-only monitoring endpoints** to check firmware update availability and monitor update progress for inverters and GridBOSS devices.

**⚠️ IMPORTANT**: These endpoints are for **monitoring firmware status only**. The actual firmware update process (`standardUpdate/run`) is a write operation that should be used with extreme caution. This library focuses on providing firmware status information for monitoring and alerting purposes.

### Check Firmware Updates

**Endpoint**: `POST /WManage/web/maintain/standardUpdate/checkUpdates`

**Operation Type**: ✅ **READ-ONLY** - Safe to call, does not modify device state

**Description**: Check if firmware updates are available for a specific device. Returns current firmware versions, available updates, and update compatibility information.

**Authentication**: Required

**Request Body** (URL-encoded):
```
serialNum={serialNum}
```

**Response**:
```json
{
  "success": true,
  "details": {
    "serialNum": "1234567890",
    "deviceType": 6,
    "standard": "fAAB",
    "firmwareType": "PCS",
    "fwCodeBeforeUpload": "fAAB-2122",
    "v1": 33,
    "v1Value": 33,
    "v2": 34,
    "v2Value": 34,
    "v3Value": 0,
    "lastV1": 37,
    "lastV1FileName": "FAAB-25xx_20250925_App.hex",
    "lastV2": 37,
    "lastV2FileName": "fAAB-xx25_Para375_20250925.hex",
    "m3Version": 33,
    "pcs1UpdateMatch": true,
    "pcs2UpdateMatch": true,
    "pcs3UpdateMatch": false,
    "needRunStep2": false,
    "needRunStep3": false,
    "needRunStep4": false,
    "needRunStep5": false,
    "phase": 1,
    "dtc": 1,
    "midbox": false,
    "lowVoltBattery": true,
    "type6": true,
    "type6Series": true
  },
  "infoForwardUrl": "http://os.solarcloudsystem.com/#/apiLogin?..."
}
```

**Key Fields Explained**:

| Field | Description |
|-------|-------------|
| `fwCodeBeforeUpload` | Current firmware version code (e.g., "fAAB-2122" means v21 app, v22 parameters) |
| `standard` | Firmware standard/family (e.g., "fAAB" for 18KPV, "IAAB" for GridBOSS) |
| `v1`, `v1Value` | Current application firmware version |
| `v2`, `v2Value` | Current parameter firmware version |
| `v3Value` | Third firmware component version (device-specific) |
| `lastV1`, `lastV1FileName` | Latest available application firmware version and file |
| `lastV2`, `lastV2FileName` | Latest available parameter firmware version and file |
| `m3Version` | Master controller version |
| `pcs1UpdateMatch` | Whether PCS1 (app) update is available and compatible |
| `pcs2UpdateMatch` | Whether PCS2 (parameter) update is available and compatible |
| `pcs3UpdateMatch` | Whether PCS3 update is available and compatible |
| `needRunStepX` | Whether multi-step update process is required |
| `deviceType` | Device type code (6=Inverter, 9=GridBOSS) |
| `midbox` | Whether device is a GridBOSS/MID device |
| `infoForwardUrl` | URL to release notes and update information |

**Firmware Version Decoding**:

The `fwCodeBeforeUpload` field encodes multiple firmware versions:
- **Format**: `{standard}-{v1}{v2}{v3}` (e.g., "fAAB-2122")
- **Example**: "fAAB-2122" means:
  - Standard: fAAB (18KPV family)
  - Application version: 21 (v1)
  - Parameter version: 22 (v2)
  - Third component: (v3, if present)

**Update Interpretation**:

To determine if an update is available:
1. Compare `v1` with `lastV1` - if `lastV1` > `v1`, application update available
2. Compare `v2` with `lastV2` - if `lastV2` > `v2`, parameter update available
3. Check `pcs1UpdateMatch`, `pcs2UpdateMatch` for compatibility
4. If any `needRunStepX` is true, multi-step update required

**Example - Update Available**:
```
Current: fAAB-2122 (v1=21, v2=22)
Available: lastV1=25 (FAAB-25xx_20250925_App.hex)
           lastV2=25 (fAAB-xx25_Para375_20250925.hex)
Meaning: Update from v21→v25 (app) and v22→v25 (parameters)
```

**Example - GridBOSS Response**:
```json
{
  "success": true,
  "details": {
    "serialNum": "0987654321",
    "deviceType": 9,
    "standard": "IAAB",
    "fwCodeBeforeUpload": "IAAB-1300",
    "v1": 19,
    "v1Value": 19,
    "v2": 0,
    "v2Value": 0,
    "lastV1": 22,
    "lastV1FileName": "IAAB-16xx_20250925_APP_preENC.hex",
    "m3Version": 19,
    "pcs1UpdateMatch": true,
    "pcs2UpdateMatch": false,
    "midbox": true
  }
}
```

**Sample Files** (in research directory, not committed to repo):
- Inverter example: `research/firmware_check_1234567890.json`
- GridBOSS example: `research/firmware_check_0987654321.json`

**Caching**: Recommended TTL of 1 hour (firmware updates are infrequent).

---

### Get Firmware Update Status

**Endpoint**: `POST /WManage/web/maintain/remoteUpdate/info`

**Operation Type**: ✅ **READ-ONLY** - Safe to call, does not modify device state

**Description**: Get current firmware update progress for all devices associated with a user account. Shows active updates, progress percentage, and update status.

**Authentication**: Required

**Request Body** (URL-encoded):
```
userId={userId}
```

**Notes**:
- `userId` is obtained from the login response (`userId` field)
- Returns update status for all devices in user's account

**Response**:
```json
{
  "receiving": false,
  "progressing": true,
  "fileReady": false,
  "deviceInfos": [
    {
      "inverterSn": "1234567890",
      "startTime": "2025-11-18 19:16:59",
      "stopTime": "",
      "standardUpdate": true,
      "firmware": "FAAB-25xx",
      "firmwareType": "PCS",
      "updateStatus": "READY",
      "isSendStartUpdate": true,
      "isSendEndUpdate": false,
      "packageIndex": 439,
      "updateRate": "78% - 439 / 561"
    }
  ]
}
```

**Key Fields Explained**:

| Field | Description |
|-------|-------------|
| `receiving` | Whether system is receiving firmware file |
| `progressing` | Whether an update is currently in progress |
| `fileReady` | Whether firmware file is ready for installation |
| `deviceInfos` | Array of devices with active or recent updates |
| `inverterSn` | Serial number of device being updated |
| `startTime` | Update start timestamp |
| `stopTime` | Update completion timestamp (empty if in progress) |
| `standardUpdate` | Whether this is a standard update process |
| `firmware` | Firmware version being installed (e.g., "FAAB-25xx") |
| `firmwareType` | Type of firmware (typically "PCS" for inverters/GridBOSS) |
| `updateStatus` | Current status: "READY", "UPLOADING", "COMPLETE", "FAILED" |
| `isSendStartUpdate` | Whether start command has been sent to device |
| `isSendEndUpdate` | Whether completion command has been sent |
| `packageIndex` | Current package number being transferred |
| `updateRate` | Progress as percentage and package count (e.g., "78% - 439 / 561") |

**Update Status Values**:
- `READY` - Update initiated, device ready to receive
- `UPLOADING` - Actively transferring firmware packages
- `COMPLETE` - Update successfully completed
- `FAILED` - Update failed, check device logs

**Progress Calculation**:
```python
# From updateRate "78% - 439 / 561"
percentage = int(update_rate.split('%')[0])  # 78
current_package = int(update_rate.split('-')[1].split('/')[0].strip())  # 439
total_packages = int(update_rate.split('/')[1].strip())  # 561
```

**Polling Recommendations**:
- Poll every 5-10 seconds during active update (`progressing=true`)
- Poll every 1 minute when no updates active
- Stop polling when `stopTime` is populated and `isSendEndUpdate=true`

**Sample File** (in research directory, not committed to repo): `research/firmware_info_user_15415.json`

**Caching**: Do not cache - always fetch real-time status during updates.

---

### Check Update Eligibility

**Endpoint**: `POST /WManage/web/maintain/standardUpdate/check12KParallelStatus`

**Operation Type**: ✅ **READ-ONLY** - Safe to call, does not modify device state

**Description**: Check if a device is eligible for firmware update. Despite the endpoint name suggesting it's only for 12K parallel devices, this endpoint works for ALL devices and should be called before any firmware update to ensure safety.

**Behavior**:
- **Non-parallel devices**: Returns `"allowToUpdate"` if device is online and not currently updating
- **Parallel devices**: Checks if other inverters in the parallel group are updating and returns appropriate status

**Authentication**: Required

**Request Body** (URL-encoded):
```
userId={userId}&serialNum={serialNum}
```

**Response**:
```json
{
  "success": true,
  "msg": "allowToUpdate"
}
```

**Possible Response Messages**:
- `allowToUpdate` - Device is ready for firmware update
- `deviceUpdating` - Device or parallel group member is currently updating
- `parallelGroupUpdating` - Another device in the parallel group is updating
- `notAllowedInParallel` - Device configuration prevents parallel updates

**Use Cases**:
- **Required pre-update check for ALL devices** (not just parallel configurations)
- Prevents conflicts when multiple inverters are paralleled together
- Ensures only one device in a parallel group updates at a time
- Verifies device is online and ready to receive firmware

**Note**: The endpoint name `check12KParallelStatus` is a misnomer - it works for:
- Single inverters (no parallel)
- GridBOSS/MID devices
- 12K, 18K, and other inverter models
- Devices in parallel configurations

**Sample Files** (in research directory, not committed to repo):
- `research/firmware_parallel_status_1234567890.json`
- `research/firmware_parallel_status_0987654321.json`

**Caching**: Do not cache - check immediately before each update.

---

### Start Firmware Update

**Endpoint**: `POST /WManage/web/maintain/standardUpdate/run`

**Operation Type**: ⚠️ **WRITE OPERATION** - Initiates firmware update, modifies device state

**⚠️ CRITICAL WARNING**: This endpoint triggers an actual firmware update that:
- Takes 20-40 minutes to complete
- Makes the device unavailable during update
- Requires uninterrupted power and network connectivity
- Should NEVER be automated without explicit user confirmation
- May brick the device if interrupted or if incompatible firmware is applied

**Recommended Use**: This endpoint is documented for completeness. Most applications should focus on the read-only monitoring endpoints (`checkUpdates`, `remoteUpdate/info`, `check12KParallelStatus`) to provide firmware status information without the risk of initiating updates.

**Description**: Initiate a firmware update for a specific device. This triggers the update process after checking compatibility and availability.

**Authentication**: Required

**Request Body** (URL-encoded):
```
userId={userId}&serialNum={serialNum}&tryFastMode={boolean}
```

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `userId` | integer | Yes | User ID from login response |
| `serialNum` | string | Yes | Device serial number (10 digits) |
| `tryFastMode` | boolean | No | Whether to attempt fast update mode (default: false) |

**Success Response**:
```json
{
  "success": true,
  "msg": "Update initiated successfully"
}
```

**Error Response - Update Already in Progress**:
```json
{
  "success": false,
  "msg": "Device is already updating",
  "code": "UPDATE_IN_PROGRESS"
}
```

**Error Response - No Update Available**:
```json
{
  "success": false,
  "msg": "No firmware update available",
  "code": "NO_UPDATE_AVAILABLE"
}
```

**Error Response - Parallel Group Conflict**:
```json
{
  "success": false,
  "msg": "Another device in parallel group is updating",
  "code": "PARALLEL_GROUP_UPDATING"
}
```

**Pre-Update Checklist**:
1. Call `check12KParallelStatus` to verify device is eligible
2. Call `checkUpdates` to confirm update is available
3. Verify device is online and connected
4. Ensure no critical operations are in progress (e.g., grid charging)
5. Consider time of day (avoid peak solar production hours)

**Update Process**:
1. Call `/standardUpdate/run` to initiate update
2. Poll `/remoteUpdate/info` every 5-10 seconds for progress
3. Monitor `updateRate` for completion percentage
4. Wait for `isSendEndUpdate=true` and `stopTime` populated
5. Verify device comes back online after update

**Fast Mode**:
- `tryFastMode=true` attempts optimized update transfer
- May reduce update time by 20-30%
- Not supported by all device types/firmware versions
- Falls back to standard mode if fast mode unavailable

**Safety Considerations**:
- **⚠️ WARNING**: Firmware updates can take 20-40 minutes
- Do not interrupt power to device during update
- Ensure stable network connection
- Device will be unavailable during update process
- Consider backup battery SOC before updating

**Caching**: Not applicable - this is a write operation.

---

## Data Scaling Reference

### Summary Table

| Data Type | Scaling Factor | Example Input | Example Output | Unit |
|-----------|---------------|---------------|----------------|------|
| **Voltage** | ÷ 100 | 5100 | 51.00 | V |
| **Current** | ÷ 100 | 1500 | 15.00 | A |
| **Power** | none | 1030 | 1030 | W |
| **Frequency** | ÷ 100 | 5998 | 59.98 | Hz |
| **Temperature** | none | 39 | 39 | °C |
| **Cell Voltage** | ÷ 1000 | 3350 | 3.350 | V |
| **SOC/SOH** | none | 71 | 71 | % |
| **Energy** | none | 12.5 | 12.5 | kWh |

### Implementation Example

```python
def scale_voltage(raw_value: int) -> float:
    """Convert raw API voltage to actual voltage."""
    return raw_value / 100.0

def scale_current(raw_value: int) -> float:
    """Convert raw API current to actual current."""
    return raw_value / 100.0

def scale_frequency(raw_value: int) -> float:
    """Convert raw API frequency to actual frequency."""
    return raw_value / 100.0

def scale_cell_voltage(raw_value: int) -> float:
    """Convert raw cell voltage (mV) to volts."""
    return raw_value / 1000.0

# Power and temperature are already in correct units
def get_power(raw_value: int) -> int:
    """Power is already in watts."""
    return raw_value

def get_temperature(raw_value: int) -> int:
    """Temperature is already in Celsius."""
    return raw_value
```

---

## Error Handling

### HTTP Status Codes

| Status | Meaning | Action |
|--------|---------|--------|
| 200 | Success | Process response normally |
| 401 | Unauthorized | Re-authenticate and retry |
| 403 | Forbidden | Re-authenticate and retry |
| 404 | Not Found | Endpoint or resource doesn't exist |
| 500 | Internal Server Error | Retry with exponential backoff |
| 503 | Service Unavailable | Retry with exponential backoff |

### API Error Responses

**Authentication Error**:
```json
{
  "success": false,
  "message": "Invalid username or password"
}
```

**Device Not Found**:
```json
{
  "success": false,
  "message": "Device not found or not accessible"
}
```

**Unsupported Device Type**:
```json
{
  "success": false,
  "message": "DEVICE_ERROR_UNSUPPORT_DEVICE_TYPE"
}
```

**Invalid Parameter**:
```json
{
  "success": false,
  "message": "Invalid parameter value or out of range"
}
```

### Retry Strategy

**Recommended Implementation**:

1. **Exponential Backoff**:
   - Base delay: 1.0 second
   - Maximum delay: 60.0 seconds
   - Exponential factor: 2.0
   - Add random jitter: 0-0.1 seconds

2. **Circuit Breaker**:
   - Track consecutive errors
   - Increase backoff delay exponentially
   - Reset on successful request
   - Log warning for 3+ consecutive errors

3. **Re-authentication**:
   - On 401/403 responses
   - When session expires (< 5 minutes remaining)
   - Clear cookies before re-authentication
   - Retry original request after successful login

4. **Cache Invalidation**:
   - Clear parameter cache on new login
   - Invalidate stale cache entries
   - Pre-emptively clear cache before hour boundaries

**Example Implementation**:

```python
async def make_request_with_retry(self, endpoint, data, max_retries=3):
    """Make API request with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            # Apply backoff delay
            if self._consecutive_errors > 0:
                delay = min(
                    self._base_delay * (2 ** (self._consecutive_errors - 1)),
                    self._max_delay
                )
                delay += random.uniform(0, 0.1)  # Add jitter
                await asyncio.sleep(delay)

            # Make request
            response = await self._make_request(endpoint, data)

            # Success - reset error counter
            self._consecutive_errors = 0
            return response

        except AuthError:
            # Re-authenticate and retry
            if attempt < max_retries - 1:
                await self.login()
                continue
            raise

        except (ConnectionError, APIError) as e:
            # Track error and retry
            self._consecutive_errors += 1
            if attempt == max_retries - 1:
                raise
            logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
```

---

## Caching Strategy

### Recommended TTL by Endpoint

| Endpoint Category | TTL | Rationale |
|-------------------|-----|-----------|
| Device Discovery | 15 minutes | Static information |
| Battery Info | 5 minutes | Slow-changing data |
| Parameters | 2 minutes | User-configurable values |
| Quick Charge Status | 1 minute | Active operations |
| Runtime Data | 20 seconds | Frequently changing metrics |
| Energy Info | 20 seconds | Moderate update frequency |
| MidBox Runtime | 20 seconds | Real-time grid data |

### Cache Implementation Notes

1. **Cache Key Generation**:
   ```python
   cache_key = f"{endpoint_key}:{serialNum}:{extra_params}"
   ```

2. **Cache Entry Structure**:
   ```python
   {
       "timestamp": datetime.now(),
       "response": {...}
   }
   ```

3. **Cache Validation**:
   - Check if key exists
   - Verify timestamp is within TTL
   - Clear entries older than configured TTL

4. **Pre-emptive Invalidation**:
   - Clear cache when < 5 minutes before hour boundary
   - Prevents stale daily/monthly data on date rollover
   - Use UTC time for consistency

---

## Session Management Best Practices

1. **Session Duration**: ~2 hours from login
2. **Proactive Refresh**: Re-authenticate when < 5 minutes remaining
3. **Cookie Handling**: Clear cookie jar before re-authentication
4. **Session Injection**: Support external session (Home Assistant integration)
5. **Auto-Recovery**: Automatically re-authenticate on 401 responses
6. **Logging**: Log session lifecycle events for debugging

---

## Notes and Limitations

1. **Regional Endpoints**: Choose the correct base URL for your region and device brand
   - US (EG4): `https://monitor.eg4electronics.com`
   - US (Luxpower): `https://us.luxpowertek.com`
   - Americas (Luxpower): `https://na.luxpowertek.com`
   - EU (Luxpower): `https://eu.luxpowertek.com`
   - Asia Pacific (Luxpower): `https://sea.luxpowertek.com`
   - Middle East & Africa (Luxpower): `https://af.luxpowertek.com`
   - China (Luxpower): `https://server.luxpowertek.com`
2. **Serial Numbers**: 10-digit numeric strings (e.g., "1234567890")
3. **Model Codes**: Hexadecimal model identifiers (e.g., 0x986C0)
4. **Timezone Handling**: All timestamps in server time, convert as needed
5. **Null Values**: Some fields may be null or 0 if not applicable
6. **Device Capabilities**: Not all devices support all endpoints
7. **Rate Limiting**: No documented rate limits, use reasonable polling intervals
8. **Data Accuracy**: Values update every 5-30 seconds on device side
9. **Cross-Region Accounts**: Accounts are typically region-specific; use the endpoint where your account was registered

---

## Additional Resources

- **Sample Responses**: `research/eg4_web_monitor/custom_components/eg4_web_monitor/eg4_inverter_api/samples/`
- **Reference Implementation**: `research/eg4_web_monitor/custom_components/eg4_web_monitor/eg4_inverter_api/client.py`
- **Production Integration**: EG4 Web Monitor Home Assistant custom component

---

**Document Version**: 1.0
**API Version**: Undocumented (reverse-engineered)
**Last Verified**: November 2025
