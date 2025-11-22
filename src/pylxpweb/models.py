"""Data models for Luxpower/EG4 API client.

All models use Pydantic for validation and serialization.
Field names match the API response format for easier parsing.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_serializer


class OperatingMode(str, Enum):
    """Inverter operating modes.

    These are the two valid operating states for an inverter:
    - NORMAL: Normal operation (power on)
    - STANDBY: Standby mode (power off)

    Note: Quick Charge and Quick Discharge are not operating modes,
    they are function controls (enable/disable) that work alongside
    the operating mode.
    """

    NORMAL = "normal"
    STANDBY = "standby"


def _obfuscate_serial(serial: str) -> str:
    """Obfuscate serial number, showing only first 2 and last 2 digits."""
    if len(serial) <= 4:
        return "****"
    return f"{serial[:2]}{'*' * (len(serial) - 4)}{serial[-2:]}"


def _obfuscate_email(email: str) -> str:
    """Obfuscate email address."""
    if "@" not in email:
        return "***@***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"**@{domain}"
    return f"{local[0]}{'*' * (len(local) - 1)}@{domain}"


def _obfuscate_coordinate(coord: str | float) -> str:
    """Obfuscate latitude/longitude to 1 decimal place."""
    try:
        val = float(coord)
        return f"{val:.1f}"
    except (ValueError, TypeError):
        return "***"


class BatteryType(str, Enum):
    """Battery type enumeration."""

    LITHIUM = "LITHIUM"
    LEAD_ACID = "LEAD_ACID"


class UserRole(str, Enum):
    """User role enumeration."""

    VIEWER = "VIEWER"
    INSTALLER = "INSTALLER"
    ADMIN = "ADMIN"


# Login Response Models


class RegionInfo(BaseModel):
    """Region information."""

    value: str
    text: str


class CountryInfo(BaseModel):
    """Country information."""

    value: str
    text: str


class UserVisitRecord(BaseModel):
    """User visit record."""

    plantId: int
    serialNum: str
    phase: int
    phaseValue: int
    deviceType: int
    deviceTypeValue: int
    subDeviceTypeValue: int
    dtc: int
    dtcValue: int
    powerRating: int
    batteryType: BatteryType
    protocolVersion: int

    @field_serializer("serialNum")
    def serialize_serial(self, value: str) -> str:
        """Obfuscate serial number in serialized output."""
        return _obfuscate_serial(value)


class InverterBasic(BaseModel):
    """Basic inverter information from login response."""

    serialNum: str
    phase: int
    lost: bool
    dtc: int
    deviceType: int
    subDeviceType: int | None = None
    allowExport2Grid: bool | None = None
    powerRating: int
    deviceTypeText4APP: str
    deviceTypeText: str
    batteryType: BatteryType
    batteryTypeText: str
    standard: str
    slaveVersion: int
    fwVersion: int
    allowGenExercise: bool
    withbatteryData: bool
    hardwareVersion: int
    voltClass: int
    machineType: int
    odm: int
    protocolVersion: int
    parallelMidboxSn: str | None = None
    parallelMidboxDeviceText: str | None = None
    parallelMidboxLost: bool | None = None

    @field_serializer("serialNum", "parallelMidboxSn")
    def serialize_serial(self, value: str | None) -> str | None:
        """Obfuscate serial numbers in serialized output."""
        return _obfuscate_serial(value) if value else value


class ParallelGroupBasic(BaseModel):
    """Parallel group information."""

    parallelGroup: str
    parallelFirstDeviceSn: str


class PlantBasic(BaseModel):
    """Plant information from login response."""

    plantId: int
    name: str
    timezoneHourOffset: int
    timezoneMinuteOffset: int
    inverters: list[InverterBasic]
    parallelGroups: list[ParallelGroupBasic]


class TechInfo(BaseModel):
    """Technical support information."""

    techInfoType1: str
    techInfo1: str
    techInfoType2: str
    techInfo2: str
    techInfoCount: int


class LoginResponse(BaseModel):
    """Login API response."""

    success: bool
    userId: int
    parentUserId: int | None = None
    username: str
    readonly: bool
    role: UserRole
    realName: str
    email: str
    countryText: str
    currentContinentIndex: int
    currentRegionIndex: int
    regions: list[RegionInfo]
    currentCountryIndex: int
    countrys: list[CountryInfo]
    timezone: str
    timezoneText: str
    language: str
    telNumber: str
    address: str
    platform: str
    userVisitRecord: UserVisitRecord
    plants: list[PlantBasic]
    clusterId: int
    needHideDisChgEnergy: bool
    allowRemoteSupport: bool
    allowViewerVisitOptimalSet: bool
    allowViewerVisitWeatherSet: bool
    chartColorValues: str
    tempUnit: str
    tempUnitText: str
    dateFormat: str
    userChartRecord: str
    firewallNotificationEnable: str
    userCreateDate: str
    userCreatedDays: int
    techInfo: TechInfo | None = None

    @field_serializer("email")
    def serialize_email(self, value: str) -> str:
        """Obfuscate email address in serialized output."""
        return _obfuscate_email(value)

    @field_serializer("telNumber")
    def serialize_phone(self, value: str) -> str:
        """Obfuscate phone number in serialized output."""
        return "***-***-" + value[-4:] if len(value) >= 4 else "***"

    @field_serializer("address")
    def serialize_address(self, _value: str) -> str:
        """Obfuscate address in serialized output."""
        return "***"


# Plant List Response Models


class PlantInfo(BaseModel):
    """Detailed plant information."""

    id: int
    plantId: int
    name: str
    nominalPower: int
    country: str
    currentTimezoneWithMinute: int
    timezone: str
    daylightSavingTime: bool
    createDate: str
    noticeFault: bool
    noticeWarn: bool
    noticeEmail: str
    noticeEmail2: str
    contactPerson: str
    contactPhone: str
    address: str

    @field_serializer("noticeEmail", "noticeEmail2")
    def serialize_email(self, value: str) -> str:
        """Obfuscate email addresses in serialized output."""
        return _obfuscate_email(value) if value else value

    @field_serializer("contactPhone")
    def serialize_phone(self, value: str) -> str:
        """Obfuscate phone number in serialized output."""
        return "***-***-" + value[-4:] if len(value) >= 4 else "***"

    @field_serializer("address")
    def serialize_address(self, _value: str) -> str:
        """Obfuscate address in serialized output."""
        return "***"


class PlantListResponse(BaseModel):
    """Plant list API response."""

    total: int
    rows: list[PlantInfo]


# Device Discovery Models


class InverterDevice(BaseModel):
    """Detailed inverter device information."""

    serialNum: str
    phase: int
    lost: bool
    deviceType: int
    subDeviceType: int | None = None
    deviceTypeText4APP: str
    powerRating: int
    batteryType: BatteryType
    allowGenExercise: bool
    withbatteryData: bool

    @field_serializer("serialNum")
    def serialize_serial(self, value: str) -> str:
        """Obfuscate serial number in serialized output."""
        return _obfuscate_serial(value)


class ParallelGroupDeviceItem(BaseModel):
    """Device in a parallel group from getParallelGroupDetails endpoint."""

    serialNum: str
    deviceType: int
    subDeviceType: int
    phase: int
    dtc: int
    machineType: int
    parallelIndex: str
    parallelNumText: str
    lost: bool
    roleText: str
    # Optional runtime data fields (present for inverters, not for GridBOSS)
    vpv1: int | None = None
    ppv1: int | None = None
    vpv2: int | None = None
    ppv2: int | None = None
    vpv3: int | None = None
    ppv3: int | None = None
    soc: int | None = None
    vBat: int | None = None
    pCharge: int | None = None
    pDisCharge: int | None = None
    peps: int | None = None

    @field_serializer("serialNum")
    def serialize_serial(self, value: str) -> str:
        """Obfuscate serial number in serialized output."""
        return _obfuscate_serial(value)


class ParallelGroupDetailsResponse(BaseModel):
    """Parallel group details API response.

    Returns devices in a parallel group including GridBOSS (if present) and inverters.
    """

    success: bool
    deviceType: int
    parallelMidboxSn: str | None = None
    total: int
    devices: list[ParallelGroupDeviceItem]


class InverterListResponse(BaseModel):
    """Inverter list API response (deprecated - use login response instead)."""

    success: bool
    rows: list[InverterDevice]


class InverterOverviewItem(BaseModel):
    """Inverter overview/status from inverterOverview/list endpoint."""

    serialNum: str
    statusText: str
    deviceType: int
    deviceTypeText: str
    phase: int
    plantId: int
    plantName: str
    ppv: int  # PV power in watts
    ppvText: str
    pCharge: int  # Charge power in watts
    pChargeText: str
    pDisCharge: int  # Discharge power in watts
    pDisChargeText: str
    pConsumption: int  # Consumption power in watts
    pConsumptionText: str
    soc: str  # State of charge (e.g., "58 %")
    vBat: int  # Battery voltage (scaled: divide by 10 for actual volts)
    vBatText: str
    totalYielding: int  # Total energy generated (raw: divide by 10 for kWh)
    totalYieldingText: str
    totalDischarging: int  # Total energy discharged (raw: divide by 10 for kWh)
    totalDischargingText: str
    totalExport: int  # Total energy exported (raw: divide by 10 for kWh)
    totalExportText: str
    totalUsage: int  # Total energy consumed (raw: divide by 10 for kWh)
    totalUsageText: str
    parallelGroup: str
    parallelIndex: str
    parallelInfo: str
    parallelModel: str
    endUser: str | None = None  # Account type: "guest", owner username, or installer name

    @field_serializer("serialNum")
    def serialize_serial(self, value: str) -> str:
        """Obfuscate serial number in serialized output."""
        return _obfuscate_serial(value)


class InverterOverviewResponse(BaseModel):
    """Response from inverterOverview/list endpoint."""

    success: bool
    total: int
    rows: list[InverterOverviewItem]


# Runtime Data Models


class InverterRuntime(BaseModel):
    """Inverter runtime data.

    Raw values from API. Use property methods for scaled values.

    Scaling applied by property methods:
    - Most voltages: ÷10 (vpv1-3, vacr/s/t, vepsr/s/t, vBat)
    - Bus voltages: ÷100 (vBus1, vBus2)
    - Frequency: ÷100 (fac, feps, genFreq)
    - Currents: ÷100 (maxChgCurr, maxDischgCurr)
    - Power: no scaling (direct watts)
    - Temperature: no scaling (direct Celsius)

    See: constants.INVERTER_RUNTIME_SCALING for complete mapping
    """

    success: bool
    serialNum: str
    fwCode: str
    powerRatingText: str
    lost: bool
    hasRuntimeData: bool = True
    statusText: str
    batShared: bool = False
    isParallelEnabled: bool = False
    allowGenExercise: bool = False
    batteryType: BatteryType
    batParallelNum: str | None = None
    batCapacity: str | None = None
    model: int | None = None
    modelText: str | None = None
    serverTime: str
    deviceTime: str
    # PV inputs (voltage requires �100)
    vpv1: int
    vpv2: int
    vpv3: int | None = None
    remainTime: int = 0
    # PV power (watts, no scaling)
    ppv1: int
    ppv2: int
    ppv3: int | None = None
    ppv: int
    # AC voltages (�100 for volts)
    vacr: int
    vacs: int
    vact: int
    # AC frequency (�100 for Hz)
    fac: int
    pf: str
    # EPS voltages and frequency
    vepsr: int
    vepss: int
    vepst: int
    feps: int
    seps: int
    # Grid and user power (watts)
    pToGrid: int
    pToUser: int
    # Temperatures (Celsius, no scaling)
    tinner: int
    tradiator1: int
    tradiator2: int
    tBat: int
    # Bus voltages
    vBus1: int
    vBus2: int
    status: int
    # Battery data
    pCharge: int
    pDisCharge: int
    batPower: int
    batteryColor: str
    soc: int
    vBat: int
    # Inverter/rectifier power
    pinv: int
    prec: int
    peps: int
    # AC couple
    _12KAcCoupleInverterFlow: bool = False
    _12KAcCoupleInverterData: bool = False
    acCouplePower: int = 0
    # Other fields
    hasEpsOverloadRecoveryTime: bool = False
    maxChgCurr: int
    maxDischgCurr: int
    maxChgCurrValue: int | None = None
    maxDischgCurrValue: int | None = None
    bmsCharge: bool
    bmsDischarge: bool
    bmsForceCharge: bool = False
    # Generator
    _12KUsingGenerator: bool = False
    genVolt: int = 0
    genFreq: int = 0
    genPower: int = 0
    genDryContact: str = "OFF"
    # Consumption
    consumptionPower114: int = 0
    consumptionPower: int = 0
    pEpsL1N: int = 0
    pEpsL2N: int = 0
    haspEpsLNValue: bool = False
    # Directions
    directions: dict[str, str] = Field(default_factory=dict)

    @property
    def pac(self) -> int:
        """AC output power (alias for pToUser for convenience).

        Returns:
            Power in watts flowing to user loads
        """
        return self.pToUser

    # Quick charge/discharge status
    hasUnclosedQuickChargeTask: bool = False
    hasUnclosedQuickDischargeTask: bool = False


# Energy Statistics Models


class EnergyInfo(BaseModel):
    """Energy statistics data.

    Raw energy values from API are in units of 0.1 kWh:
    - Divide by 10 to get kWh directly
    - Example: 184 → 18.4 kWh

    Note: serialNum and soc are not present in parallel group energy responses.
    """

    success: bool
    serialNum: str | None = None
    soc: int | None = None
    # Today's energy
    todayYielding: int
    todayCharging: int
    todayDischarging: int
    todayImport: int
    todayExport: int
    todayUsage: int
    # Lifetime energy
    totalYielding: int
    totalCharging: int
    totalDischarging: int
    totalImport: int
    totalExport: int
    totalUsage: int


# Battery Information Models


class BatteryModule(BaseModel):
    """Individual battery module information.

    Raw values from API. Use Battery class properties for scaled values.

    Scaling (applied by Battery class):
    - totalVoltage: ÷100 (5305 → 53.05V)
    - current: ÷10 (60 → 6.0A) **CRITICAL: Not ÷100**
    - batMaxCellVoltage/batMinCellVoltage: ÷1000 (3317 → 3.317V)
    - batMaxCellTemp/batMinCellTemp: ÷10 (240 → 24.0°C)

    See: constants.BATTERY_MODULE_SCALING for complete mapping
    """

    # Identification
    batteryKey: str
    batterySn: str
    batIndex: int
    batteryType: str | None = None
    batteryTypeText: str | None = None
    batBmsModelText: str | None = None

    # Status
    lost: bool
    lastUpdateTime: str | None = None

    # Voltage and Current (÷100 for volts, ÷10 for amps)
    totalVoltage: int
    current: int

    # State of Charge/Health
    soc: int
    soh: int

    # Capacity
    currentRemainCapacity: int
    currentFullCapacity: int
    currentCapacityPercent: int | None = None
    maxBatteryCharge: int | None = None

    # Temperatures (÷10 for Celsius)
    batMaxCellTemp: int
    batMinCellTemp: int
    batMaxCellNumTemp: int | None = None
    batMinCellNumTemp: int | None = None

    # Cell Voltages (÷1000 for volts)
    batMaxCellVoltage: int
    batMinCellVoltage: int
    batMaxCellNumVolt: int | None = None
    batMinCellNumVolt: int | None = None

    # Charge Parameters
    batChargeMaxCur: int | None = None
    batChargeVoltRef: int | None = None

    # Cycle Count and Firmware
    cycleCnt: int
    fwVersionText: str

    # Additional Metrics (may be empty strings)
    chgCapacity: str | None = None
    disChgCapacity: str | None = None
    ambientTemp: str | None = None
    mosTemp: str | None = None
    noticeInfo: str | None = None


class BatteryInfo(BaseModel):
    """Battery information including individual modules.

    This represents the aggregate battery system data from getBatteryInfo endpoint.
    """

    success: bool
    serialNum: str

    # Status
    lost: bool | None = None
    hasRuntimeData: bool | None = None
    statusText: str | None = None
    batStatus: str

    # State of Charge
    soc: int

    # Voltage (÷10 for volts at aggregate level)
    vBat: int
    totalVoltageText: str | None = None

    # Power (direct watts)
    ppv: int | None = None  # PV power
    pCharge: int
    pDisCharge: int
    batPower: int | None = None  # Battery power
    pinv: int | None = None  # Inverter power
    prec: int | None = None  # Grid power
    peps: int | None = None  # EPS/backup power

    # Capacity (Ah)
    maxBatteryCharge: int
    currentBatteryCharge: float
    remainCapacity: int | None = None
    fullCapacity: int | None = None
    capacityPercent: int | None = None

    # Current
    currentText: str | None = None
    currentType: str | None = None  # "charge" or "discharge"

    # Individual Battery Modules
    batteryArray: list[BatteryModule]
    totalNumber: int | None = None  # Total battery count


class BatteryListItem(BaseModel):
    """Simplified battery item from getBatteryInfoForSet endpoint."""

    batteryKey: str
    batterySn: str
    batIndex: int
    lost: bool


class BatteryListResponse(BaseModel):
    """Response from getBatteryInfoForSet endpoint.

    This endpoint returns a simplified list of batteries without detailed metrics.
    Use get_battery_info() for full battery metrics.
    """

    success: bool
    serialNum: str
    totalNumber: int
    batteryArray: list[BatteryListItem]


class InverterDetail(BaseModel):
    """Inverter detail information."""

    deviceText: str
    fwCode: str
    fwCodeText: str


class InverterInfo(BaseModel):
    """Detailed inverter configuration and device information.

    This endpoint returns static device configuration details,
    not runtime data. Use get_inverter_runtime() for real-time metrics.
    """

    success: bool
    lost: bool
    datalogSn: str
    serialNum: str
    deviceType: int
    phase: int
    dtc: int
    voltClass: int
    fwVersion: int
    hardwareVersion: int
    subDeviceType: int
    allowExport2Grid: bool
    powerRating: int
    machineType: int
    deviceTypeText: str
    inverterDetail: InverterDetail
    deviceInfo: str
    address: int
    powerRatingText: str
    batteryType: BatteryType
    status: int
    statusText: str

    @field_serializer("serialNum", "datalogSn")
    def serialize_serial(self, value: str) -> str:
        """Obfuscate serial numbers in serialized output."""
        return _obfuscate_serial(value)


# GridBOSS/MID Device Models


class MidboxData(BaseModel):
    """GridBOSS/MID device runtime data.

    Note: Voltages are in decivolts (÷10), currents in centiamps (÷100),
    frequency in centihertz (÷100). Power values are in watts (no scaling).
    """

    status: int
    serverTime: str
    deviceTime: str
    # Grid voltages (�10 for volts, e.g., 2418 = 241.8V)
    gridRmsVolt: int
    upsRmsVolt: int
    genRmsVolt: int
    gridL1RmsVolt: int
    gridL2RmsVolt: int
    upsL1RmsVolt: int
    upsL2RmsVolt: int
    genL1RmsVolt: int
    genL2RmsVolt: int
    # Currents (�100 for amps)
    gridL1RmsCurr: int
    gridL2RmsCurr: int
    loadL1RmsCurr: int
    loadL2RmsCurr: int
    genL1RmsCurr: int
    genL2RmsCurr: int
    upsL1RmsCurr: int
    upsL2RmsCurr: int
    # Power (watts, no scaling)
    gridL1ActivePower: int
    gridL2ActivePower: int
    loadL1ActivePower: int
    loadL2ActivePower: int
    genL1ActivePower: int
    genL2ActivePower: int
    upsL1ActivePower: int
    upsL2ActivePower: int
    hybridPower: int
    # Smart port status
    smartPort1Status: int
    smartPort2Status: int
    smartPort3Status: int
    smartPort4Status: int
    # Grid frequency (�100 for Hz)
    gridFreq: int


class MidboxRuntime(BaseModel):
    """GridBOSS/MID device runtime response."""

    success: bool
    serialNum: str
    fwCode: str
    midboxData: MidboxData


# Parameter Control Models


class ParameterReadResponse(BaseModel):
    """Parameter read response.

    The API returns parameter keys directly in the response dict,
    not nested under a 'parameters' or 'valueFields' key.
    """

    success: bool
    inverterSn: str
    deviceType: int
    startRegister: int
    pointNumber: int
    valueFrame: str
    inverterRuntimeDeviceTime: str | None = None

    # Allow extra fields for all the parameter keys
    model_config = {"extra": "allow"}

    @property
    def serialNum(self) -> str:
        """Alias for inverterSn for backwards compatibility."""
        return self.inverterSn

    @property
    def parameters(self) -> dict[str, Any]:
        """Extract all parameter fields (excluding metadata fields)."""
        metadata_fields = {
            "success",
            "inverterSn",
            "deviceType",
            "startRegister",
            "pointNumber",
            "valueFrame",
            "inverterRuntimeDeviceTime",
        }
        return {k: v for k, v in self.model_dump().items() if k not in metadata_fields}


class QuickChargeStatus(BaseModel):
    """Quick charge/discharge status response.

    Note: The quickCharge/getStatusInfo endpoint returns status for BOTH
    quick charge and quick discharge operations.
    """

    success: bool
    hasUnclosedQuickChargeTask: bool
    hasUnclosedQuickDischargeTask: bool = False  # May not be present in older API versions


class SuccessResponse(BaseModel):
    """Generic success response."""

    success: bool
    message: str | None = None


class ErrorResponse(BaseModel):
    """Error response."""

    success: bool
    message: str


# Scaling Helper Functions


def scale_voltage(value: int) -> float:
    """Scale voltage value (�100)."""
    return value / 100.0


def scale_current(value: int) -> float:
    """Scale current value (�100)."""
    return value / 100.0


def scale_frequency(value: int) -> float:
    """Scale frequency value (�100)."""
    return value / 100.0


def scale_cell_voltage(value: int) -> float:
    """Scale cell voltage value (�1000)."""
    return value / 1000.0


def scale_temperature(value: int, divisor: int = 10) -> float:
    """Scale temperature value (�10 or �1 depending on field)."""
    return value / divisor


def energy_to_kwh(value: int) -> float:
    """Convert energy from Wh to kWh."""
    return value / 1000.0


# Firmware Update Models


class UpdateStatus(str, Enum):
    """Firmware update status enumeration."""

    READY = "READY"
    UPLOADING = "UPLOADING"
    COMPLETE = "COMPLETE"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class UpdateEligibilityMessage(str, Enum):
    """Update eligibility status messages."""

    ALLOW_TO_UPDATE = "allowToUpdate"
    DEVICE_UPDATING = "deviceUpdating"
    PARALLEL_GROUP_UPDATING = "parallelGroupUpdating"
    NOT_ALLOWED_IN_PARALLEL = "notAllowedInParallel"


class FirmwareUpdateDetails(BaseModel):
    """Detailed firmware update information."""

    serialNum: str
    deviceType: int
    standard: str
    firmwareType: str
    fwCodeBeforeUpload: str
    # Current firmware versions
    v1: int  # Application firmware version
    v2: int  # Parameter firmware version
    v3Value: int
    # Latest available versions (optional - only present when updates are available)
    lastV1: int | None = None
    lastV1FileName: str | None = None
    lastV2: int | None = None
    lastV2FileName: str | None = None
    # Master controller version
    m3Version: int
    # Update compatibility flags
    pcs1UpdateMatch: bool
    pcs2UpdateMatch: bool
    pcs3UpdateMatch: bool
    # Multi-step update flags
    needRunStep2: bool
    needRunStep3: bool
    needRunStep4: bool
    needRunStep5: bool
    # Device type flags
    midbox: bool
    lowVoltBattery: bool
    type6: bool

    @field_serializer("serialNum")
    def serialize_serial(self, value: str) -> str:
        """Obfuscate serial number in serialized output."""
        return _obfuscate_serial(value)

    @property
    def has_app_update(self) -> bool:
        """Check if application firmware update is available."""
        return self.lastV1 is not None and self.v1 < self.lastV1 and self.pcs1UpdateMatch

    @property
    def has_parameter_update(self) -> bool:
        """Check if parameter firmware update is available."""
        return self.lastV2 is not None and self.v2 < self.lastV2 and self.pcs2UpdateMatch

    @property
    def has_update(self) -> bool:
        """Check if any firmware update is available."""
        return self.has_app_update or self.has_parameter_update


class FirmwareUpdateCheck(BaseModel):
    """Firmware update check response."""

    success: bool
    details: FirmwareUpdateDetails
    infoForwardUrl: str | None = None


class FirmwareDeviceInfo(BaseModel):
    """Individual device firmware update information."""

    inverterSn: str
    startTime: str
    stopTime: str
    standardUpdate: bool
    firmware: str
    firmwareType: str
    updateStatus: UpdateStatus
    isSendStartUpdate: bool
    isSendEndUpdate: bool
    packageIndex: int
    updateRate: str

    @field_serializer("inverterSn")
    def serialize_serial(self, value: str) -> str:
        """Obfuscate serial number in serialized output."""
        return _obfuscate_serial(value)

    @property
    def is_in_progress(self) -> bool:
        """Check if update is currently in progress."""
        return (
            self.updateStatus == UpdateStatus.UPLOADING or self.updateStatus == UpdateStatus.READY
        )

    @property
    def is_complete(self) -> bool:
        """Check if update completed successfully."""
        return (
            self.updateStatus == UpdateStatus.COMPLETE or self.updateStatus == UpdateStatus.SUCCESS
        )

    @property
    def is_failed(self) -> bool:
        """Check if update failed."""
        return self.updateStatus == UpdateStatus.FAILED


class FirmwareUpdateStatus(BaseModel):
    """Firmware update status response."""

    receiving: bool
    progressing: bool
    fileReady: bool
    deviceInfos: list[FirmwareDeviceInfo]

    @property
    def has_active_updates(self) -> bool:
        """Check if any device has an active update."""
        return any(device.is_in_progress for device in self.deviceInfos)


class UpdateEligibilityStatus(BaseModel):
    """Update eligibility status response."""

    success: bool
    msg: UpdateEligibilityMessage

    @property
    def is_allowed(self) -> bool:
        """Check if device is allowed to update."""
        return self.msg == UpdateEligibilityMessage.ALLOW_TO_UPDATE
