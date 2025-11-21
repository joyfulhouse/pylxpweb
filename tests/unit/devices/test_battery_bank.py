"""Unit tests for BatteryBank class."""

from unittest.mock import Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.battery_bank import BatteryBank
from pylxpweb.models import BatteryInfo


@pytest.fixture
def mock_client() -> LuxpowerClient:
    """Create a mock LuxpowerClient."""
    client = Mock(spec=LuxpowerClient)
    client.api = Mock()
    client.api.devices = Mock()
    return client


@pytest.fixture
def sample_battery_info():
    """Create sample BatteryInfo data."""
    return BatteryInfo.model_construct(
        batStatus="Charging",
        soc=85,
        vBat=539,  # 53.9V (scaled by ÷10)
        pCharge=2500,  # 2500W charging
        pDisCharge=0,  # Not discharging
        maxBatteryCharge=200,  # 200Ah max capacity
        currentBatteryCharge=170.0,  # 170Ah current capacity
        batteryArray=[],  # Empty for basic tests
    )


class TestBatteryBankInit:
    """Test BatteryBank initialization."""

    def test_init_creates_battery_bank(self, mock_client, sample_battery_info):
        """Test BatteryBank initializes correctly."""
        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=sample_battery_info,
        )

        assert battery_bank.inverter_serial == "1234567890"
        assert battery_bank._data == sample_battery_info
        assert battery_bank.batteries == []
        assert battery_bank.serial_number == "1234567890_battery_bank"
        assert battery_bank.model == "Battery Bank"


class TestBatteryBankProperties:
    """Test BatteryBank property accessors."""

    def test_status_property(self, mock_client, sample_battery_info):
        """Test status property returns correct value."""
        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=sample_battery_info,
        )

        assert battery_bank.status == "Charging"

    def test_soc_property(self, mock_client, sample_battery_info):
        """Test SOC property returns correct value."""
        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=sample_battery_info,
        )

        assert battery_bank.soc == 85

    def test_voltage_property_scaling(self, mock_client, sample_battery_info):
        """Test voltage property uses correct scaling (÷10)."""
        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=sample_battery_info,
        )

        # vBat=539 should be 53.9V (÷10, not ÷100)
        assert battery_bank.voltage == 53.9

    def test_charge_power_property(self, mock_client, sample_battery_info):
        """Test charge power property returns correct value."""
        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=sample_battery_info,
        )

        assert battery_bank.charge_power == 2500

    def test_discharge_power_property(self, mock_client, sample_battery_info):
        """Test discharge power property returns correct value."""
        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=sample_battery_info,
        )

        assert battery_bank.discharge_power == 0

    def test_max_capacity_property(self, mock_client, sample_battery_info):
        """Test max capacity property returns correct value."""
        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=sample_battery_info,
        )

        assert battery_bank.max_capacity == 200

    def test_current_capacity_property(self, mock_client, sample_battery_info):
        """Test current capacity property returns correct value."""
        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=sample_battery_info,
        )

        assert battery_bank.current_capacity == 170.0

    def test_battery_count_property(self, mock_client):
        """Test battery count property returns correct count."""
        # Create battery info with 3 batteries in array
        battery_info = BatteryInfo.model_construct(
            batStatus="Idle",
            soc=50,
            vBat=520,
            pCharge=0,
            pDisCharge=0,
            maxBatteryCharge=150,
            currentBatteryCharge=75.0,
            batteryArray=[
                {"batteryKey": "bat1"},
                {"batteryKey": "bat2"},
                {"batteryKey": "bat3"},
            ],
        )

        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
        )

        assert battery_bank.battery_count == 3


class TestBatteryBankRefresh:
    """Test BatteryBank refresh behavior."""

    @pytest.mark.asyncio
    async def test_refresh_is_noop(self, mock_client, sample_battery_info):
        """Test refresh method is a no-op (data refreshed via parent inverter)."""
        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=sample_battery_info,
        )

        # Should not raise or make any API calls
        await battery_bank.refresh()

        # Verify no API calls were made
        mock_client.api.devices.get_battery_info.assert_not_called()


class TestBatteryBankDeviceInfo:
    """Test BatteryBank device info generation."""

    def test_to_device_info_returns_valid_info(self, mock_client):
        """Test to_device_info returns proper DeviceInfo structure."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Idle",
            soc=50,
            vBat=520,
            pCharge=0,
            pDisCharge=0,
            maxBatteryCharge=150,
            currentBatteryCharge=75.0,
            batteryArray=[{"batteryKey": "bat1"}],
        )

        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
        )

        device_info = battery_bank.to_device_info()

        assert device_info.identifiers == {("pylxpweb", "battery_bank_1234567890")}
        assert device_info.name == "Battery Bank (1234567890)"
        assert device_info.manufacturer == "EG4/Luxpower"
        assert device_info.model == "Battery Bank (1 modules)"
        assert device_info.via_device == ("pylxpweb", "inverter_1234567890")


class TestBatteryBankEntities:
    """Test BatteryBank entity generation."""

    def test_to_entities_returns_empty_list(self, mock_client, sample_battery_info):
        """Test to_entities returns empty list (entities not generated for HA)."""
        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=sample_battery_info,
        )

        entities = battery_bank.to_entities()

        # BatteryBank entities not generated to avoid HA entity proliferation
        assert entities == []


class TestBatteryBankDataUpdate:
    """Test BatteryBank data updates."""

    def test_data_can_be_updated(self, mock_client, sample_battery_info):
        """Test that battery bank data can be updated directly."""
        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=sample_battery_info,
        )

        # Initial state
        assert battery_bank.soc == 85
        assert battery_bank.status == "Charging"

        # Update data
        new_battery_info = BatteryInfo.model_construct(
            batStatus="Discharging",
            soc=75,
            vBat=530,
            pCharge=0,
            pDisCharge=1500,
            maxBatteryCharge=200,
            currentBatteryCharge=150.0,
            batteryArray=[],
        )

        battery_bank._data = new_battery_info

        # Verify updated state
        assert battery_bank.soc == 75
        assert battery_bank.status == "Discharging"
        assert battery_bank.voltage == 53.0
        assert battery_bank.charge_power == 0
        assert battery_bank.discharge_power == 1500
