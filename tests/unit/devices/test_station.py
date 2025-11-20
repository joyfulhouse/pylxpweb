"""Unit tests for Station class.

This module tests the Station class that represents a complete solar
installation with device hierarchy.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.models import DeviceInfo, Entity
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

    def test_to_device_info(
        self, mock_client: LuxpowerClient, sample_location: Location
    ) -> None:
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

    def test_to_entities(
        self, mock_client: LuxpowerClient, sample_location: Location
    ) -> None:
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
