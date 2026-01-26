"""Unit tests for Station class.

This module tests the Station class that represents a complete solar
installation with device hierarchy.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.models import DeviceInfo
from pylxpweb.devices.station import Location, Station
from pylxpweb.exceptions import LuxpowerAPIError


@pytest.fixture
def mock_client() -> LuxpowerClient:
    """Create a mock client for testing."""
    client = Mock(spec=LuxpowerClient)
    client.api = Mock()
    client.api.plants = Mock()
    client.api.devices = Mock()
    return client


@pytest.fixture
def sample_location() -> Location:
    """Create a sample location."""
    return Location(
        address="123 Solar St, City, State 12345",
        country="United States",
    )


@pytest.fixture
def sample_plant_data() -> dict:
    """Sample plant data for testing.

    Note: API does not include lat/lng fields - coordinates are not provided.
    """
    return {
        "plantId": 12345,
        "name": "Test Solar Station",
        "timezone": "America/New_York",
        "createDate": "2024-01-01T00:00:00",
        "address": "123 Solar St",
        "country": "US",
        "currentTimezoneWithMinute": -300,
        "daylightSavingTime": False,
    }


class TestStationInitialization:
    """Test Station initialization."""

    def test_station_initialization(
        self, mock_client: LuxpowerClient, sample_location: Location
    ) -> None:
        """Test Station constructor."""
        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Test Station",
            location=sample_location,
            timezone="America/New_York",
            created_date=datetime(2024, 1, 1),
        )

        assert station.id == 12345
        assert station.name == "Test Station"
        assert station.location == sample_location
        assert station.timezone == "America/New_York"
        assert station.created_date == datetime(2024, 1, 1)
        assert station.parallel_groups == []
        assert station.standalone_inverters == []
        assert station.weather is None

    def test_station_has_client_reference(
        self, mock_client: LuxpowerClient, sample_location: Location
    ) -> None:
        """Test Station stores reference to client."""
        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Test Station",
            location=sample_location,
            timezone="America/New_York",
            created_date=datetime(2024, 1, 1),
        )

        assert station._client is mock_client


class TestLocationClass:
    """Test Location dataclass."""

    def test_location_creation(self) -> None:
        """Test creating a Location."""
        location = Location(
            address="123 Main St",
            country="USA",
        )

        assert location.address == "123 Main St"
        assert location.country == "USA"


class TestAllInvertersProperty:
    """Test all_inverters property aggregation."""

    def test_all_inverters_empty(
        self, mock_client: LuxpowerClient, sample_location: Location
    ) -> None:
        """Test all_inverters returns empty list when no inverters."""
        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Test Station",
            location=sample_location,
            timezone="America/New_York",
            created_date=datetime(2024, 1, 1),
        )

        assert station.all_inverters == []

    def test_all_inverters_standalone_only(
        self, mock_client: LuxpowerClient, sample_location: Location
    ) -> None:
        """Test all_inverters with standalone inverters."""
        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Test Station",
            location=sample_location,
            timezone="America/New_York",
            created_date=datetime(2024, 1, 1),
        )

        # Add mock standalone inverters
        inv1 = Mock()
        inv1.serial_number = "1111111111"
        inv2 = Mock()
        inv2.serial_number = "2222222222"

        station.standalone_inverters = [inv1, inv2]

        assert len(station.all_inverters) == 2
        assert inv1 in station.all_inverters
        assert inv2 in station.all_inverters


class TestAllBatteriesProperty:
    """Test all_batteries property aggregation."""

    def test_all_batteries_empty(
        self, mock_client: LuxpowerClient, sample_location: Location
    ) -> None:
        """Test all_batteries returns empty list when no batteries."""
        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Test Station",
            location=sample_location,
            timezone="America/New_York",
            created_date=datetime(2024, 1, 1),
        )

        assert station.all_batteries == []


class TestStationHAIntegration:
    """Test Home Assistant integration methods."""

    def test_to_device_info(self, mock_client: LuxpowerClient, sample_location: Location) -> None:
        """Test Station device info generation."""
        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Test Station",
            location=sample_location,
            timezone="America/New_York",
            created_date=datetime(2024, 1, 1),
        )

        device_info = station.to_device_info()

        assert isinstance(device_info, DeviceInfo)
        assert device_info.name == "Station: Test Station"
        assert device_info.manufacturer == "EG4/Luxpower"
        assert device_info.model == "Solar Station"
        assert ("pylxpweb", "station_12345") in device_info.identifiers

    def test_to_entities(self, mock_client: LuxpowerClient, sample_location: Location) -> None:
        """Test Station entity generation."""
        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Test Station",
            location=sample_location,
            timezone="America/New_York",
            created_date=datetime(2024, 1, 1),
        )

        entities = station.to_entities()

        assert isinstance(entities, list)
        # Station should generate at least total production and total power entities
        assert len(entities) >= 2

        # Check for expected entity types
        entity_ids = [e.unique_id for e in entities]
        assert any("total_production_today" in uid for uid in entity_ids)
        assert any("total_power" in uid for uid in entity_ids)


class TestStationFactoryMethods:
    """Test Station factory methods for loading from API."""

    @pytest.mark.asyncio
    async def test_load_station(self, mock_client: LuxpowerClient) -> None:
        """Test loading a station from API."""
        from pylxpweb.models import InverterOverviewResponse

        # Mock API responses (matching actual API format - no lat/lng)
        plant_data = {
            "plantId": 12345,
            "name": "Test Station",
            "address": "123 Solar St",
            "country": "USA",
            "timezone": "America/New_York",
            "createDate": "2024-01-01T00:00:00Z",
            "currentTimezoneWithMinute": -300,
            "daylightSavingTime": False,
        }

        # Mock devices response (no devices)
        devices_response = InverterOverviewResponse(success=True, total=0, rows=[])

        # Mock the API calls
        mock_client.api.plants.get_plant_details = AsyncMock(return_value=plant_data)
        mock_client.api.devices.get_devices = AsyncMock(return_value=devices_response)
        mock_client.api.plants.set_daylight_saving_time = AsyncMock(return_value={"success": True})

        # Load station
        station = await Station.load(mock_client, 12345)

        # Verify station was created correctly
        assert station.id == 12345
        assert station.name == "Test Station"
        assert station.location.address == "123 Solar St"
        assert station.location.country == "USA"
        assert station.timezone == "America/New_York"

        # Verify API was called
        mock_client.api.plants.get_plant_details.assert_called_once_with(12345)
        mock_client.api.devices.get_devices.assert_called_once_with(12345)

    @pytest.mark.asyncio
    async def test_load_all_stations(self, mock_client: LuxpowerClient) -> None:
        """Test loading all stations from API."""
        from pylxpweb.models import PlantInfo, PlantListResponse

        # Mock plant list response with all required fields
        plants = [
            PlantInfo(
                id=1,
                plantId=1,
                name="Station 1",
                address="Address 1",
                createDate="2024-01-01",
                nominalPower=10000,
                country="USA",
                currentTimezoneWithMinute=-480,
                timezone="America/Los_Angeles",
                daylightSavingTime=True,
                noticeFault=True,
                noticeWarn=True,
                noticeEmail="test@example.com",
                noticeEmail2="",
                contactPerson="John Doe",
                contactPhone="555-1234",
            ),
            PlantInfo(
                id=2,
                plantId=2,
                name="Station 2",
                address="Address 2",
                createDate="2024-01-01",
                nominalPower=15000,
                country="USA",
                currentTimezoneWithMinute=-480,
                timezone="America/Los_Angeles",
                daylightSavingTime=True,
                noticeFault=True,
                noticeWarn=True,
                noticeEmail="test2@example.com",
                noticeEmail2="",
                contactPerson="Jane Doe",
                contactPhone="555-5678",
            ),
        ]
        plants_response = PlantListResponse(rows=plants, total=2)

        # Mock API calls
        mock_client.api.plants.get_plants = AsyncMock(return_value=plants_response)

        # Mock load for each station
        async def mock_load(client: LuxpowerClient, plant_id: int) -> Station:
            location = Location(
                address=f"Address {plant_id}",
                country="USA",
            )
            return Station(
                client=client,
                plant_id=plant_id,
                name=f"Station {plant_id}",
                location=location,
                timezone="UTC",
                created_date=datetime(2024, 1, 1),
            )

        with patch.object(Station, "load", side_effect=mock_load):
            stations = await Station.load_all(mock_client)

        # Verify all stations loaded
        assert len(stations) == 2
        assert stations[0].id == 1
        assert stations[0].name == "Station 1"
        assert stations[1].id == 2
        assert stations[1].name == "Station 2"

    @pytest.mark.asyncio
    async def test_load_devices_with_parallel_groups(
        self, mock_client: LuxpowerClient, sample_location: Location
    ) -> None:
        """Test _load_devices creates parallel groups."""
        from pylxpweb.models import (
            InverterOverviewItem,
            InverterOverviewResponse,
            ParallelGroupDetailsResponse,
            ParallelGroupDeviceItem,
        )

        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Test Station",
            location=sample_location,
            timezone="America/New_York",
            created_date=datetime(2024, 1, 1),
        )

        # Mock devices response with GridBOSS and inverters
        # Use model_construct to bypass validation for test data
        devices_response = InverterOverviewResponse(
            success=True,
            total=3,
            rows=[
                InverterOverviewItem.model_construct(
                    serialNum="9999999999",
                    statusText="Online",
                    deviceType=9,  # GridBOSS
                    subDeviceType=0,
                    parallelGroup="",
                    deviceTypeText="GridBOSS",
                    phase=1,
                    plantId=12345,
                    plantName="Test Station",
                    ppv=0,
                    ppvText="0 W",
                    pCharge=0,
                    pChargeText="0 W",
                    pDisCharge=0,
                    pDisChargeText="0 W",
                    pConsumption=0,
                    pConsumptionText="0 W",
                    soc="0 %",
                    vBat=0,
                    vBatText="0 V",
                    totalYielding=0,
                    totalYieldingText="0 kWh",
                    totalDischarging=0,
                    totalDischargingText="0 kWh",
                    totalExport=0,
                    totalExportText="0 kWh",
                    totalUsage=0,
                    totalUsageText="0 kWh",
                    parallelIndex="",
                ),
                InverterOverviewItem.model_construct(
                    serialNum="1111111111",
                    statusText="Online",
                    deviceType=6,  # Inverter
                    subDeviceType=0,
                    parallelGroup="A",
                    deviceTypeText="18KPV",
                    phase=1,
                    plantId=12345,
                    plantName="Test Station",
                    ppv=0,
                    ppvText="0 W",
                    pCharge=0,
                    pChargeText="0 W",
                    pDisCharge=0,
                    pDisChargeText="0 W",
                    pConsumption=0,
                    pConsumptionText="0 W",
                    soc="0 %",
                    vBat=0,
                    vBatText="0 V",
                    totalYielding=0,
                    totalYieldingText="0 kWh",
                    totalDischarging=0,
                    totalDischargingText="0 kWh",
                    totalExport=0,
                    totalExportText="0 kWh",
                    totalUsage=0,
                    totalUsageText="0 kWh",
                    parallelIndex="1",
                ),
                InverterOverviewItem.model_construct(
                    serialNum="2222222222",
                    statusText="Online",
                    deviceType=6,  # Inverter
                    subDeviceType=0,
                    parallelGroup="B",
                    deviceTypeText="18KPV",
                    phase=1,
                    plantId=12345,
                    plantName="Test Station",
                    ppv=0,
                    ppvText="0 W",
                    pCharge=0,
                    pChargeText="0 W",
                    pDisCharge=0,
                    pDisChargeText="0 W",
                    pConsumption=0,
                    pConsumptionText="0 W",
                    soc="0 %",
                    vBat=0,
                    vBatText="0 V",
                    totalYielding=0,
                    totalYieldingText="0 kWh",
                    totalDischarging=0,
                    totalDischargingText="0 kWh",
                    totalExport=0,
                    totalExportText="0 kWh",
                    totalUsage=0,
                    totalUsageText="0 kWh",
                    parallelIndex="1",
                ),
            ],
        )

        # Mock parallel group details response
        # Use model_construct to bypass validation for test data
        group_data = ParallelGroupDetailsResponse.model_construct(
            success=True,
            deviceType=6,
            total=2,
            devices=[
                ParallelGroupDeviceItem.model_construct(
                    serialNum="1111111111",
                    deviceType=6,
                    subDeviceType=0,
                    phase=1,
                    dtc="2024-01-01 00:00:00",
                    machineType="18KPV",
                    parallelIndex="1",
                    parallelNumText="1",
                    lost=False,
                    roleText="Primary",
                ),
                ParallelGroupDeviceItem.model_construct(
                    serialNum="2222222222",
                    deviceType=6,
                    subDeviceType=0,
                    phase=1,
                    dtc="2024-01-01 00:00:00",
                    machineType="18KPV",
                    parallelIndex="1",
                    parallelNumText="1",
                    lost=False,
                    roleText="Primary",
                ),
            ],
        )

        mock_client.api.devices.get_devices = AsyncMock(return_value=devices_response)
        mock_client.api.devices.get_parallel_group_details = AsyncMock(return_value=group_data)

        # Load devices
        await station._load_devices()

        # Verify parallel groups created
        assert len(station.parallel_groups) == 2
        assert station.parallel_groups[0].name == "A"
        assert station.parallel_groups[0].first_device_serial == "1111111111"
        assert station.parallel_groups[1].name == "B"
        assert station.parallel_groups[1].first_device_serial == "2222222222"

    @pytest.mark.asyncio
    async def test_load_devices_handles_api_errors(
        self, mock_client: LuxpowerClient, sample_location: Location
    ) -> None:
        """Test _load_devices handles API errors gracefully."""
        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Test Station",
            location=sample_location,
            timezone="America/New_York",
            created_date=datetime(2024, 1, 1),
        )

        # Mock API error - error happens at the get_devices call
        mock_client.api.devices.get_devices = AsyncMock(side_effect=LuxpowerAPIError("API Error"))

        # Should not raise, just log warning
        await station._load_devices()

        # Station should still be usable with empty device lists
        assert station.parallel_groups == []
        assert station.standalone_inverters == []


class TestStationDaylightSavingTime:
    """Test Station daylight saving time control."""

    @pytest.mark.asyncio
    async def test_set_daylight_saving_time_updates_cached_state(
        self, mock_client: LuxpowerClient, sample_location: Location
    ) -> None:
        """Test that set_daylight_saving_time() updates cached daylight_saving_time."""
        # Create station with DST initially disabled
        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Test Station",
            location=sample_location,
            timezone="America/New_York",
            created_date=datetime(2024, 1, 1),
            daylight_saving_time=False,
        )

        # Mock successful API call
        mock_client.api.plants.set_daylight_saving_time = AsyncMock(return_value={"success": True})

        # Verify initial state
        assert station.daylight_saving_time is False

        # Enable DST
        result = await station.set_daylight_saving_time(True)

        # Verify success and state update
        assert result is True
        assert station.daylight_saving_time is True
        mock_client.api.plants.set_daylight_saving_time.assert_called_once_with(12345, True)

    @pytest.mark.asyncio
    async def test_set_daylight_saving_time_does_not_update_on_failure(
        self, mock_client: LuxpowerClient, sample_location: Location
    ) -> None:
        """Test that cached state is NOT updated when API call fails."""
        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Test Station",
            location=sample_location,
            timezone="America/New_York",
            created_date=datetime(2024, 1, 1),
            daylight_saving_time=False,
        )

        # Mock failed API call
        mock_client.api.plants.set_daylight_saving_time = AsyncMock(
            return_value={"success": False, "msg": "API Error"}
        )

        # Verify initial state
        assert station.daylight_saving_time is False

        # Attempt to enable DST (will fail)
        result = await station.set_daylight_saving_time(True)

        # Verify failure and state NOT updated
        assert result is False
        assert station.daylight_saving_time is False  # Should remain False

    @pytest.mark.asyncio
    async def test_set_daylight_saving_time_disable(
        self, mock_client: LuxpowerClient, sample_location: Location
    ) -> None:
        """Test disabling DST also updates cached state."""
        # Create station with DST initially enabled
        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Test Station",
            location=sample_location,
            timezone="America/New_York",
            created_date=datetime(2024, 1, 1),
            daylight_saving_time=True,
        )

        # Mock successful API call
        mock_client.api.plants.set_daylight_saving_time = AsyncMock(return_value={"success": True})

        # Verify initial state
        assert station.daylight_saving_time is True

        # Disable DST
        result = await station.set_daylight_saving_time(False)

        # Verify success and state update
        assert result is True
        assert station.daylight_saving_time is False
        mock_client.api.plants.set_daylight_saving_time.assert_called_once_with(12345, False)


class TestStationFromLocalDiscovery:
    """Test Station.from_local_discovery() factory method."""

    @pytest.fixture
    def mock_modbus_transport(self) -> Mock:
        """Create a mock Modbus transport."""
        transport = Mock()
        transport.serial = "CE12345678"
        transport.connect = AsyncMock()
        transport.read_parameters = AsyncMock(
            side_effect=[
                {19: 2092},  # Device type (PV Series)
                {107: 550, 108: 1},  # Parallel config
            ]
        )
        return transport

    @pytest.mark.asyncio
    async def test_from_local_discovery_empty_configs_raises_error(self) -> None:
        """Test that empty configs list raises ValueError."""
        with pytest.raises(ValueError, match="At least one TransportConfig"):
            await Station.from_local_discovery([])

    @pytest.mark.asyncio
    async def test_from_local_discovery_single_inverter(self) -> None:
        """Test discovering a single standalone inverter."""
        from pylxpweb.constants import DEVICE_TYPE_CODE_PV_SERIES
        from pylxpweb.transports.config import TransportConfig, TransportType

        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
        )

        # Mock transport and discovery - patch at the transports module level
        with (
            patch("pylxpweb.transports.create_modbus_transport") as mock_create,
            patch("pylxpweb.transports.discover_device_info") as mock_discover,
        ):
            mock_transport = Mock()
            mock_transport.connect = AsyncMock()
            mock_create.return_value = mock_transport

            # Return discovery info with no parallel config (standalone)
            from pylxpweb.transports import DeviceDiscoveryInfo

            mock_discover.return_value = DeviceDiscoveryInfo(
                serial="CE12345678",
                device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
                is_gridboss=False,
                is_inverter=True,
                model_family="PV_SERIES",
                parallel_number=None,
                parallel_phase=None,
            )

            station = await Station.from_local_discovery(
                [config],
                station_name="Test Station",
                plant_id=1,
            )

            assert station.name == "Test Station"
            assert station.id == 1
            assert len(station.standalone_inverters) == 1
            assert len(station.parallel_groups) == 0
            assert station.standalone_inverters[0].serial_number == "CE12345678"

    @pytest.mark.asyncio
    async def test_from_local_discovery_parallel_group(self) -> None:
        """Test discovering inverters in a parallel group."""
        from pylxpweb.constants import DEVICE_TYPE_CODE_PV_SERIES
        from pylxpweb.transports.config import TransportConfig, TransportType

        configs = [
            TransportConfig(
                host="192.168.1.100",
                port=502,
                serial="CE1",
                transport_type=TransportType.MODBUS_TCP,
            ),
            TransportConfig(
                host="192.168.1.101",
                port=502,
                serial="CE2",
                transport_type=TransportType.MODBUS_TCP,
            ),
        ]

        with (
            patch("pylxpweb.transports.create_modbus_transport") as mock_create,
            patch("pylxpweb.transports.discover_device_info") as mock_discover,
        ):
            mock_transport1 = Mock()
            mock_transport1.connect = AsyncMock()
            mock_transport2 = Mock()
            mock_transport2.connect = AsyncMock()
            mock_create.side_effect = [mock_transport1, mock_transport2]

            # Both devices have same parallel config
            from pylxpweb.transports import DeviceDiscoveryInfo

            mock_discover.side_effect = [
                DeviceDiscoveryInfo(
                    serial="CE1",
                    device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
                    is_gridboss=False,
                    is_inverter=True,
                    model_family="PV_SERIES",
                    parallel_number=550,
                    parallel_phase=1,
                ),
                DeviceDiscoveryInfo(
                    serial="CE2",
                    device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
                    is_gridboss=False,
                    is_inverter=True,
                    model_family="PV_SERIES",
                    parallel_number=550,
                    parallel_phase=1,
                ),
            ]

            station = await Station.from_local_discovery(configs)

            assert len(station.parallel_groups) == 1
            assert len(station.standalone_inverters) == 0
            assert len(station.parallel_groups[0].inverters) == 2

    @pytest.mark.asyncio
    async def test_from_local_discovery_with_gridboss(self) -> None:
        """Test discovering a GridBOSS with inverters."""
        from pylxpweb.constants import DEVICE_TYPE_CODE_GRIDBOSS, DEVICE_TYPE_CODE_PV_SERIES
        from pylxpweb.transports.config import TransportConfig, TransportType

        configs = [
            TransportConfig(
                host="192.168.1.100",
                port=502,
                serial="GB1",
                transport_type=TransportType.MODBUS_TCP,
            ),
            TransportConfig(
                host="192.168.1.101",
                port=502,
                serial="CE1",
                transport_type=TransportType.MODBUS_TCP,
            ),
        ]

        with (
            patch("pylxpweb.transports.create_modbus_transport") as mock_create,
            patch("pylxpweb.transports.discover_device_info") as mock_discover,
        ):
            mock_transport_gb = Mock()
            mock_transport_gb.connect = AsyncMock()
            mock_transport_inv = Mock()
            mock_transport_inv.connect = AsyncMock()
            mock_create.side_effect = [mock_transport_gb, mock_transport_inv]

            from pylxpweb.transports import DeviceDiscoveryInfo

            mock_discover.side_effect = [
                DeviceDiscoveryInfo(
                    serial="GB1",
                    device_type_code=DEVICE_TYPE_CODE_GRIDBOSS,
                    is_gridboss=True,
                    is_inverter=False,
                    model_family="GridBOSS",
                    parallel_number=550,
                    parallel_phase=0,
                ),
                DeviceDiscoveryInfo(
                    serial="CE1",
                    device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
                    is_gridboss=False,
                    is_inverter=True,
                    model_family="PV_SERIES",
                    parallel_number=550,
                    parallel_phase=1,
                ),
            ]

            station = await Station.from_local_discovery(configs)

            # GridBOSS has different parallel_phase (0 vs 1), so they're in different groups
            assert len(station.parallel_groups) == 2

    @pytest.mark.asyncio
    async def test_from_local_discovery_all_connections_fail(self) -> None:
        """Test that all connection failures raises TransportConnectionError."""
        from pylxpweb.transports.config import TransportConfig, TransportType
        from pylxpweb.transports.exceptions import TransportConnectionError

        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE1",
            transport_type=TransportType.MODBUS_TCP,
        )

        with patch("pylxpweb.transports.create_modbus_transport") as mock_create:
            mock_transport = Mock()
            mock_transport.connect = AsyncMock(side_effect=Exception("Connection failed"))
            mock_create.return_value = mock_transport

            with pytest.raises(TransportConnectionError, match="All transports failed"):
                await Station.from_local_discovery([config])

    @pytest.mark.asyncio
    async def test_from_local_discovery_partial_failure(self) -> None:
        """Test that partial connection failures still create station."""
        from pylxpweb.constants import DEVICE_TYPE_CODE_PV_SERIES
        from pylxpweb.transports.config import TransportConfig, TransportType

        configs = [
            TransportConfig(
                host="192.168.1.100",
                port=502,
                serial="CE1",
                transport_type=TransportType.MODBUS_TCP,
            ),
            TransportConfig(
                host="192.168.1.101",
                port=502,
                serial="CE2",
                transport_type=TransportType.MODBUS_TCP,
            ),
        ]

        with (
            patch("pylxpweb.transports.create_modbus_transport") as mock_create,
            patch("pylxpweb.transports.discover_device_info") as mock_discover,
        ):
            mock_transport1 = Mock()
            mock_transport1.connect = AsyncMock()
            mock_transport2 = Mock()
            mock_transport2.connect = AsyncMock(side_effect=Exception("Connection failed"))
            mock_create.side_effect = [mock_transport1, mock_transport2]

            from pylxpweb.transports import DeviceDiscoveryInfo

            mock_discover.return_value = DeviceDiscoveryInfo(
                serial="CE1",
                device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
                is_gridboss=False,
                is_inverter=True,
                model_family="PV_SERIES",
            )

            station = await Station.from_local_discovery(configs)

            # Only one device should be discovered
            assert len(station.standalone_inverters) == 1
            assert station.standalone_inverters[0].serial_number == "CE1"

    @pytest.mark.asyncio
    async def test_from_local_discovery_wifi_dongle_success(self) -> None:
        """Test successful WiFi dongle discovery."""
        from pylxpweb.constants import DEVICE_TYPE_CODE_PV_SERIES
        from pylxpweb.transports.config import TransportConfig, TransportType

        config = TransportConfig(
            host="192.168.1.100",
            port=8000,
            serial="CE1",
            transport_type=TransportType.WIFI_DONGLE,
            dongle_serial="DJ12345678",
        )

        with (
            patch("pylxpweb.transports.create_dongle_transport") as mock_create,
            patch("pylxpweb.transports.discover_device_info") as mock_discover,
        ):
            mock_transport = Mock()
            mock_transport.connect = AsyncMock()
            mock_create.return_value = mock_transport

            from pylxpweb.transports import DeviceDiscoveryInfo

            mock_discover.return_value = DeviceDiscoveryInfo(
                serial="CE1",
                device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
                is_gridboss=False,
                is_inverter=True,
                model_family="PV_SERIES",
            )

            station = await Station.from_local_discovery([config])

            assert len(station.standalone_inverters) == 1
            assert station.standalone_inverters[0].serial_number == "CE1"
            mock_create.assert_called_once()
