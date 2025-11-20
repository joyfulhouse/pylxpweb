"""Unit tests for ParallelGroup class.

This module tests the ParallelGroup class that represents a group of
inverters operating in parallel.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.parallel_group import ParallelGroup


@pytest.fixture
def mock_client() -> LuxpowerClient:
    """Create a mock client for testing."""
    client = Mock(spec=LuxpowerClient)
    client.api = Mock()
    return client


@pytest.fixture
def mock_station() -> Mock:
    """Create a mock station for testing."""
    station = Mock()
    station.id = 12345
    station.name = "Test Station"
    return station


class TestParallelGroupInitialization:
    """Test ParallelGroup initialization."""

    def test_parallel_group_initialization(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test ParallelGroup constructor."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        assert group.name == "Group A"
        assert group.first_device_serial == "1234567890"
        assert group.station is mock_station
        assert group.inverters == []
        assert group.mid_device is None

    def test_parallel_group_has_client_reference(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test ParallelGroup stores reference to client."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        assert group._client is mock_client


class TestParallelGroupWithMIDDevice:
    """Test parallel group with MID device."""

    def test_parallel_group_with_mid_device(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test group with GridBOSS/MID device."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        # Add mock MID device
        mid_device = Mock()
        mid_device.serial_number = "9999999999"
        group.mid_device = mid_device

        assert group.mid_device is mid_device
        assert group.mid_device.serial_number == "9999999999"


class TestParallelGroupWithoutMIDDevice:
    """Test parallel group without MID device."""

    def test_parallel_group_without_mid_device(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test group without GridBOSS (standalone parallel)."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        assert group.mid_device is None


class TestParallelGroupWithMultipleInverters:
    """Test parallel group with multiple inverters."""

    def test_parallel_group_multiple_inverters(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test group with 2+ inverters in parallel."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        # Add mock inverters
        inv1 = Mock()
        inv1.serial_number = "1111111111"
        inv2 = Mock()
        inv2.serial_number = "2222222222"
        inv3 = Mock()
        inv3.serial_number = "3333333333"

        group.inverters = [inv1, inv2, inv3]

        assert len(group.inverters) == 3
        assert inv1 in group.inverters
        assert inv2 in group.inverters
        assert inv3 in group.inverters


class TestParallelGroupRefresh:
    """Test parallel group refresh operation."""

    @pytest.mark.asyncio
    async def test_parallel_group_refresh_all_devices(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test refreshing all devices in group."""
        from unittest.mock import AsyncMock

        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        # Add mock inverters with async refresh methods
        inv1 = Mock()
        inv1.refresh = AsyncMock()
        inv2 = Mock()
        inv2.refresh = AsyncMock()

        group.inverters = [inv1, inv2]

        # Add mock MID device with async refresh method
        mid_device = Mock()
        mid_device.refresh = AsyncMock()
        group.mid_device = mid_device

        # Refresh should call all device refresh methods
        await group.refresh()

        # Verify all refresh methods were called
        inv1.refresh.assert_called_once()
        inv2.refresh.assert_called_once()
        mid_device.refresh.assert_called_once()


class TestParallelGroupName:
    """Test parallel group naming."""

    def test_parallel_group_name_format(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test group name follows expected format."""
        group_a = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="A",
            first_device_serial="1234567890",
        )

        group_b = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="B",
            first_device_serial="9876543210",
        )

        assert group_a.name == "A"
        assert group_b.name == "B"


class TestParallelGroupCombinedEnergy:
    """Test parallel group combined energy calculations."""

    @pytest.mark.asyncio
    async def test_get_combined_energy_empty_group(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test combined energy with no inverters."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        result = await group.get_combined_energy()

        assert result["today_kwh"] == 0.0
        assert result["lifetime_kwh"] == 0.0

    @pytest.mark.asyncio
    async def test_get_combined_energy_multiple_inverters(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test combined energy sums all inverters."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        # Mock inverters with energy data
        inv1 = Mock()
        inv1.needs_refresh = False
        inv1.energy = Mock()
        inv1.energy.eToday = 10.5
        inv1.energy.eTotal = 1000.0

        inv2 = Mock()
        inv2.needs_refresh = False
        inv2.energy = Mock()
        inv2.energy.eToday = 15.3
        inv2.energy.eTotal = 1500.0

        group.inverters = [inv1, inv2]

        result = await group.get_combined_energy()

        assert result["today_kwh"] == 25.8
        assert result["lifetime_kwh"] == 2500.0

    @pytest.mark.asyncio
    async def test_get_combined_energy_with_missing_energy_data(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test combined energy handles inverters without energy data."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        # One inverter with energy, one without
        inv1 = Mock()
        inv1.needs_refresh = False
        inv1.energy = Mock()
        inv1.energy.eToday = 10.5
        inv1.energy.eTotal = 1000.0

        inv2 = Mock()
        inv2.needs_refresh = False
        inv2.energy = None

        group.inverters = [inv1, inv2]

        result = await group.get_combined_energy()

        assert result["today_kwh"] == 10.5
        assert result["lifetime_kwh"] == 1000.0


class TestParallelGroupFactory:
    """Test parallel group factory methods."""

    @pytest.mark.asyncio
    async def test_from_api_data(self, mock_client: LuxpowerClient, mock_station: Mock) -> None:
        """Test creating group from API response."""
        api_data = {
            "parallelGroup": "A",
            "parallelFirstDeviceSn": "1234567890",
        }

        group = await ParallelGroup.from_api_data(
            client=mock_client, station=mock_station, group_data=api_data
        )

        assert group.name == "A"
        assert group.first_device_serial == "1234567890"
        assert group.station is mock_station
        assert group._client is mock_client
        assert group.inverters == []
        assert group.mid_device is None

    @pytest.mark.asyncio
    async def test_from_api_data_with_defaults(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test creating group from minimal API data uses defaults."""
        api_data = {}

        group = await ParallelGroup.from_api_data(
            client=mock_client, station=mock_station, group_data=api_data
        )

        assert group.name == "A"  # Default
        assert group.first_device_serial == ""  # Default
        assert group.station is mock_station
