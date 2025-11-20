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
        latitude=40.7128,
        longitude=-74.0060,
        country="United States",
    )


@pytest.fixture
def sample_plant_data() -> dict:
    """Sample plant data for testing."""
    return {
        "plantId": 12345,
        "name": "Test Solar Station",
        "timezone": "America/New_York",
        "createDate": "2024-01-01T00:00:00",
        "address": "123 Solar St",
        "lat": 40.7128,
        "lng": -74.0060,
        "country": "US",
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
            latitude=40.0,
            longitude=-74.0,
            country="USA",
        )

        assert location.address == "123 Main St"
        assert location.latitude == 40.0
        assert location.longitude == -74.0
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
        # Mock API responses
        plant_data = {
            "plantId": 12345,
            "name": "Test Station",
            "address": "123 Solar St",
            "lat": 40.7128,
            "lng": -74.0060,
            "country": "USA",
            "timezone": "America/New_York",
            "createDate": "2024-01-01T00:00:00Z",
        }

        # Mock the API calls
        mock_client.api.plants.get_plant_details = AsyncMock(return_value=plant_data)
        mock_client.api.devices.get_parallel_group_details = AsyncMock(return_value={"groups": []})

        # Load station
        station = await Station.load(mock_client, 12345)

        # Verify station was created correctly
        assert station.id == 12345
        assert station.name == "Test Station"
        assert station.location.address == "123 Solar St"
        assert station.location.latitude == 40.7128
        assert station.location.longitude == -74.0060
        assert station.location.country == "USA"
        assert station.timezone == "America/New_York"

        # Verify API was called
        mock_client.api.plants.get_plant_details.assert_called_once_with(12345)
        mock_client.api.devices.get_parallel_group_details.assert_called_once()

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
                latitude=0.0,
                longitude=0.0,
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
        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Test Station",
            location=sample_location,
            timezone="America/New_York",
            created_date=datetime(2024, 1, 1),
        )

        # Mock parallel group API response
        group_data = {
            "groups": [
                {"parallelGroup": "A", "parallelFirstDeviceSn": "1111111111"},
                {"parallelGroup": "B", "parallelFirstDeviceSn": "2222222222"},
            ]
        }
        mock_client.api.devices.get_parallel_group_details = AsyncMock(return_value=group_data)

        # Mock devices API response (required for optimized concurrent call)
        devices_data = {"success": True, "rows": []}
        mock_client.api.devices.get_devices = AsyncMock(return_value=devices_data)

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

        # Mock API error
        mock_client.api.devices.get_parallel_group_details = AsyncMock(
            side_effect=Exception("API Error")
        )

        # Should not raise, just log warning
        await station._load_devices()

        # Station should still be usable with empty device lists
        assert station.parallel_groups == []
        assert station.standalone_inverters == []
