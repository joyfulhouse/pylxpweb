"""Unit tests for MIDDevice class."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.mid_device import MIDDevice
from pylxpweb.devices.models import Entity
from pylxpweb.exceptions import LuxpowerAPIError
from pylxpweb.models import MidboxRuntime


@pytest.fixture
def mock_client() -> LuxpowerClient:
    """Create a mock client for testing."""
    client = Mock(spec=LuxpowerClient)
    client.api = Mock()
    client.api.devices = Mock()
    return client


@pytest.fixture
def sample_midbox_runtime() -> MidboxRuntime:
    """Load sample midbox runtime data."""
    sample_path = Path(__file__).parent / "samples" / "midbox_4524850115.json"
    with open(sample_path) as f:
        data = json.load(f)
    return MidboxRuntime.model_validate(data)


class TestMIDDeviceInitialization:
    """Test MIDDevice initialization."""

    def test_mid_device_initialization(self, mock_client: LuxpowerClient) -> None:
        """Test MIDDevice can be instantiated."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890", model="GridBOSS")

        assert mid.serial_number == "1234567890"
        assert mid.model == "GridBOSS"
        assert mid._runtime is None

    def test_mid_device_default_model(self, mock_client: LuxpowerClient) -> None:
        """Test MIDDevice uses GridBOSS as default model."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")

        assert mid.model == "GridBOSS"


class TestMIDDeviceRefresh:
    """Test MIDDevice refresh functionality."""

    @pytest.mark.asyncio
    async def test_refresh_fetches_midbox_runtime(
        self, mock_client: LuxpowerClient, sample_midbox_runtime: MidboxRuntime
    ) -> None:
        """Test refresh fetches midbox runtime data."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")

        # Mock API response
        mock_client.api.devices.get_midbox_runtime = AsyncMock(return_value=sample_midbox_runtime)

        # Refresh
        await mid.refresh()

        # Verify API call
        mock_client.api.devices.get_midbox_runtime.assert_called_once_with("1234567890")

        # Verify data stored
        assert mid._runtime is sample_midbox_runtime
        assert mid._last_refresh is not None

    @pytest.mark.asyncio
    async def test_refresh_handles_api_error(self, mock_client: LuxpowerClient) -> None:
        """Test refresh handles API error gracefully."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")

        # Mock API error
        mock_client.api.devices.get_midbox_runtime = AsyncMock(
            side_effect=LuxpowerAPIError("API Error")
        )

        await mid.refresh()

        # Runtime should be None (error)
        assert mid._runtime is None


class TestMIDDeviceProperties:
    """Test MIDDevice convenience properties."""

    def test_has_data_with_runtime(
        self, mock_client: LuxpowerClient, sample_midbox_runtime: MidboxRuntime
    ) -> None:
        """Test has_data returns True when runtime available."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")
        mid._runtime = sample_midbox_runtime

        assert mid.has_data is True

    def test_has_data_without_runtime(self, mock_client: LuxpowerClient) -> None:
        """Test has_data returns False when no runtime."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")

        assert mid.has_data is False

    def test_grid_voltage_property(
        self, mock_client: LuxpowerClient, sample_midbox_runtime: MidboxRuntime
    ) -> None:
        """Test grid_voltage property with scaling."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")
        mid._runtime = sample_midbox_runtime

        # Sample has gridRmsVolt=2418, should be 241.8V
        assert mid.grid_voltage == pytest.approx(241.8, rel=0.01)

    def test_ups_voltage_property(
        self, mock_client: LuxpowerClient, sample_midbox_runtime: MidboxRuntime
    ) -> None:
        """Test ups_voltage property with scaling."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")
        mid._runtime = sample_midbox_runtime

        # Sample has upsRmsVolt=2403, should be 240.3V
        assert mid.ups_voltage == pytest.approx(240.3, rel=0.01)

    def test_grid_power_property(
        self, mock_client: LuxpowerClient, sample_midbox_runtime: MidboxRuntime
    ) -> None:
        """Test grid_power property (L1 + L2)."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")
        mid._runtime = sample_midbox_runtime

        # Sample has gridL1ActivePower=872, gridL2ActivePower=1169
        # Total = 2041W
        assert mid.grid_power == 2041

    def test_ups_power_property(
        self, mock_client: LuxpowerClient, sample_midbox_runtime: MidboxRuntime
    ) -> None:
        """Test ups_power property (L1 + L2)."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")
        mid._runtime = sample_midbox_runtime

        # Sample has upsL1ActivePower=827, upsL2ActivePower=1211
        # Total = 2038W
        assert mid.ups_power == 2038

    def test_hybrid_power_property(
        self, mock_client: LuxpowerClient, sample_midbox_runtime: MidboxRuntime
    ) -> None:
        """Test hybrid_power property."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")
        mid._runtime = sample_midbox_runtime

        # Sample has hybridPower=-2042
        assert mid.hybrid_power == -2042

    def test_grid_frequency_property(
        self, mock_client: LuxpowerClient, sample_midbox_runtime: MidboxRuntime
    ) -> None:
        """Test grid_frequency property with scaling."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")
        mid._runtime = sample_midbox_runtime

        # Sample has gridFreq=5998, should be 59.98Hz
        assert mid.grid_frequency == pytest.approx(59.98, rel=0.01)

    def test_firmware_version_property(
        self, mock_client: LuxpowerClient, sample_midbox_runtime: MidboxRuntime
    ) -> None:
        """Test firmware_version property."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")
        mid._runtime = sample_midbox_runtime

        assert mid.firmware_version == "IAAB-1300"


class TestMIDDeviceEntities:
    """Test MIDDevice entity generation."""

    def test_to_entities_with_no_data(self, mock_client: LuxpowerClient) -> None:
        """Test entity generation with no data returns empty list."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")

        entities = mid.to_entities()

        assert isinstance(entities, list)
        assert len(entities) == 0

    def test_to_entities_with_runtime_data(
        self, mock_client: LuxpowerClient, sample_midbox_runtime: MidboxRuntime
    ) -> None:
        """Test entity generation with runtime data."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")
        mid._runtime = sample_midbox_runtime

        entities = mid.to_entities()

        assert isinstance(entities, list)
        assert len(entities) > 0

        # Check for key entities
        entity_ids = [e.unique_id for e in entities]
        assert "1234567890_grid_voltage" in entity_ids
        assert "1234567890_grid_power" in entity_ids
        assert "1234567890_ups_voltage" in entity_ids
        assert "1234567890_ups_power" in entity_ids
        assert "1234567890_grid_frequency" in entity_ids

    def test_to_entities_creates_entity_objects(
        self, mock_client: LuxpowerClient, sample_midbox_runtime: MidboxRuntime
    ) -> None:
        """Test all entities are Entity objects."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")
        mid._runtime = sample_midbox_runtime

        entities = mid.to_entities()

        assert all(isinstance(e, Entity) for e in entities)

    def test_to_entities_has_proper_device_classes(
        self, mock_client: LuxpowerClient, sample_midbox_runtime: MidboxRuntime
    ) -> None:
        """Test entities have correct device classes and units."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")
        mid._runtime = sample_midbox_runtime

        entities = mid.to_entities()
        entities_by_id = {e.unique_id: e for e in entities}

        # Check voltage entity
        voltage_entity = entities_by_id["1234567890_grid_voltage"]
        assert voltage_entity.device_class == "voltage"
        assert voltage_entity.unit_of_measurement == "V"

        # Check power entity
        power_entity = entities_by_id["1234567890_grid_power"]
        assert power_entity.device_class == "power"
        assert power_entity.unit_of_measurement == "W"

        # Check frequency entity
        freq_entity = entities_by_id["1234567890_grid_frequency"]
        assert freq_entity.device_class == "frequency"
        assert freq_entity.unit_of_measurement == "Hz"


class TestMIDDeviceDeviceInfo:
    """Test MIDDevice device info generation."""

    def test_to_device_info(
        self, mock_client: LuxpowerClient, sample_midbox_runtime: MidboxRuntime
    ) -> None:
        """Test device info generation."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")
        mid._runtime = sample_midbox_runtime

        device_info = mid.to_device_info()

        assert device_info.name == "GridBOSS 1234567890"
        assert device_info.manufacturer == "EG4/Luxpower"
        assert device_info.model == "GridBOSS"
        assert device_info.sw_version == "IAAB-1300"
        assert ("pylxpweb", "mid_1234567890") in device_info.identifiers

    def test_to_device_info_without_runtime(self, mock_client: LuxpowerClient) -> None:
        """Test device info without runtime data."""
        mid = MIDDevice(client=mock_client, serial_number="1234567890")

        device_info = mid.to_device_info()

        assert device_info.sw_version is None
