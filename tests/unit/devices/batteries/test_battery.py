"""Unit tests for Battery class."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.battery import Battery
from pylxpweb.devices.models import Entity
from pylxpweb.models import BatteryModule


@pytest.fixture
def mock_client() -> LuxpowerClient:
    """Create a mock client for testing."""
    client = Mock(spec=LuxpowerClient)
    client.api = Mock()
    return client


@pytest.fixture
def sample_battery_module() -> BatteryModule:
    """Load sample battery module data."""
    sample_path = Path(__file__).parent / "samples" / "battery_44300E0585.json"
    with open(sample_path) as f:
        data = json.load(f)
    # Get first battery from batteryArray
    return BatteryModule.model_validate(data["batteryArray"][0])


class TestBatteryInitialization:
    """Test Battery initialization."""

    def test_battery_initialization(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test Battery can be instantiated."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        assert battery.battery_key == sample_battery_module.batteryKey
        assert battery.battery_sn == sample_battery_module.batterySn
        assert battery.battery_index == sample_battery_module.batIndex
        assert battery._data is sample_battery_module


class TestBatteryProperties:
    """Test Battery convenience properties."""

    def test_voltage_property(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test voltage property returns scaled value."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        # Sample data has totalVoltage=5381, should be 53.81V
        assert battery.voltage == pytest.approx(53.81, rel=0.01)

    def test_current_property(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test current property returns scaled value."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        # Sample data has current=147, should be 14.7A (÷10, not ÷100!)
        assert battery.current == pytest.approx(14.7, rel=0.01)

    def test_power_property(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test power property calculates V * I."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        # Power = 53.81V * 14.7A = ~791.0W (corrected with ÷10 scaling)
        assert battery.power == pytest.approx(791.0, abs=1.0)

    def test_soc_property(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test SOC property."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        # Sample data has soc=73
        assert battery.soc == 73

    def test_soh_property(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test SOH property."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        # Sample data has soh=100
        assert battery.soh == 100

    def test_max_cell_temp_property(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test max cell temperature property with scaling."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        # Sample data has batMaxCellTemp=250, should be 25.0°C
        assert battery.max_cell_temp == pytest.approx(25.0, rel=0.01)

    def test_min_cell_temp_property(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test min cell temperature property with scaling."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        # Sample data has batMinCellTemp=240, should be 24.0°C
        assert battery.min_cell_temp == pytest.approx(24.0, rel=0.01)

    def test_max_cell_voltage_property(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test max cell voltage property with millivolt scaling."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        # Sample data has batMaxCellVoltage=3364, should be 3.364V
        assert battery.max_cell_voltage == pytest.approx(3.364, rel=0.001)

    def test_min_cell_voltage_property(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test min cell voltage property with millivolt scaling."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        # Sample data has batMinCellVoltage=3361, should be 3.361V
        assert battery.min_cell_voltage == pytest.approx(3.361, rel=0.001)

    def test_cell_voltage_delta_property(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test cell voltage delta calculates imbalance."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        # Delta = 3.364V - 3.361V = 0.003V = 3mV
        assert battery.cell_voltage_delta == pytest.approx(0.003, abs=0.001)

    def test_cycle_count_property(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test cycle count property."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        # Sample data has cycleCnt=40
        assert battery.cycle_count == 40

    def test_firmware_version_property(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test firmware version property."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        # Sample data has fwVersionText="2.17"
        assert battery.firmware_version == "2.17"


class TestBatteryEntities:
    """Test Battery entity generation."""

    def test_to_entities_generates_all_sensors(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test entity generation creates all expected sensors."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        entities = battery.to_entities()

        assert isinstance(entities, list)
        assert len(entities) >= 10  # At least 10 sensors

        # Check for key entity IDs
        entity_ids = [e.unique_id for e in entities]
        battery_key = sample_battery_module.batteryKey

        assert f"{battery_key}_voltage" in entity_ids
        assert f"{battery_key}_current" in entity_ids
        assert f"{battery_key}_power" in entity_ids
        assert f"{battery_key}_soc" in entity_ids
        assert f"{battery_key}_soh" in entity_ids
        assert f"{battery_key}_max_cell_temp" in entity_ids
        assert f"{battery_key}_min_cell_temp" in entity_ids
        assert f"{battery_key}_max_cell_voltage" in entity_ids
        assert f"{battery_key}_min_cell_voltage" in entity_ids
        assert f"{battery_key}_cell_voltage_delta" in entity_ids
        assert f"{battery_key}_cycle_count" in entity_ids

    def test_to_entities_creates_entity_objects(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test all entities are Entity objects."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        entities = battery.to_entities()

        assert all(isinstance(e, Entity) for e in entities)

    def test_to_entities_has_proper_device_classes(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test entities have correct device classes and units."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        entities = battery.to_entities()
        entities_by_id = {e.unique_id: e for e in entities}

        battery_key = sample_battery_module.batteryKey

        # Check voltage entity
        voltage_entity = entities_by_id[f"{battery_key}_voltage"]
        assert voltage_entity.device_class == "voltage"
        assert voltage_entity.unit_of_measurement == "V"

        # Check current entity
        current_entity = entities_by_id[f"{battery_key}_current"]
        assert current_entity.device_class == "current"
        assert current_entity.unit_of_measurement == "A"

        # Check power entity
        power_entity = entities_by_id[f"{battery_key}_power"]
        assert power_entity.device_class == "power"
        assert power_entity.unit_of_measurement == "W"

        # Check SOC entity
        soc_entity = entities_by_id[f"{battery_key}_soc"]
        assert soc_entity.device_class == "battery"
        assert soc_entity.unit_of_measurement == "%"


class TestBatteryDeviceInfo:
    """Test Battery device info generation."""

    def test_to_device_info(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test device info generation."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        device_info = battery.to_device_info()

        assert device_info.name.startswith("Battery")
        assert device_info.manufacturer == "EG4/Luxpower"
        assert device_info.model == "Battery Module"
        assert device_info.sw_version == "2.17"
        expected_identifier = ("pylxpweb", f"battery_{sample_battery_module.batteryKey}")
        assert expected_identifier in device_info.identifiers


class TestBatteryStatus:
    """Test Battery status properties."""

    def test_is_lost_property(
        self, mock_client: LuxpowerClient, sample_battery_module: BatteryModule
    ) -> None:
        """Test is_lost property."""
        battery = Battery(client=mock_client, battery_data=sample_battery_module)

        # Sample data has lost=false
        assert battery.is_lost is False
