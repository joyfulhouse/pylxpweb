"""Unit tests for BatteryBank class."""

from unittest.mock import Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.battery import Battery
from pylxpweb.devices.battery_bank import BatteryBank
from pylxpweb.models import BatteryInfo, BatteryModule


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
        assert battery_bank.data == sample_battery_info
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

        battery_bank.data = new_battery_info

        # Verify updated state
        assert battery_bank.soc == 75
        assert battery_bank.status == "Discharging"
        assert battery_bank.voltage == 53.0
        assert battery_bank.charge_power == 0
        assert battery_bank.discharge_power == 1500


class TestBatteryBankEnhancedProperties:
    """Test newly added BatteryBank properties."""

    def test_status_text_property(self, mock_client):
        """Test status_text property returns detailed status."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Charging",
            statusText="normal",
            soc=85,
            vBat=539,
            pCharge=2500,
            pDisCharge=0,
            maxBatteryCharge=200,
            currentBatteryCharge=170.0,
            batteryArray=[],
        )

        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
        )

        assert battery_bank.status_text == "normal"

    def test_is_lost_property(self, mock_client):
        """Test is_lost property."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Idle",
            lost=False,
            soc=50,
            vBat=520,
            pCharge=0,
            pDisCharge=0,
            maxBatteryCharge=150,
            currentBatteryCharge=75.0,
            batteryArray=[],
        )

        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
        )

        assert battery_bank.is_lost is False

    def test_has_runtime_data_property(self, mock_client):
        """Test has_runtime_data property."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Charging",
            hasRuntimeData=True,
            soc=85,
            vBat=539,
            pCharge=2500,
            pDisCharge=0,
            maxBatteryCharge=200,
            currentBatteryCharge=170.0,
            batteryArray=[],
        )

        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
        )

        assert battery_bank.has_runtime_data is True

    def test_voltage_text_property(self, mock_client):
        """Test voltage_text property."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Charging",
            totalVoltageText="53.8",
            soc=85,
            vBat=538,
            pCharge=2500,
            pDisCharge=0,
            maxBatteryCharge=200,
            currentBatteryCharge=170.0,
            batteryArray=[],
        )

        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
        )

        assert battery_bank.voltage_text == "53.8"

    def test_power_properties(self, mock_client):
        """Test various power properties."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Charging",
            soc=85,
            vBat=538,
            pCharge=2500,
            pDisCharge=0,
            batPower=2500,
            ppv=3000,
            pinv=500,
            prec=0,
            peps=0,
            maxBatteryCharge=200,
            currentBatteryCharge=170.0,
            batteryArray=[],
        )

        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
        )

        assert battery_bank.battery_power == 2500
        assert battery_bank.pv_power == 3000
        assert battery_bank.inverter_power == 500
        assert battery_bank.grid_power == 0
        assert battery_bank.eps_power == 0

    def test_capacity_properties_extended(self, mock_client):
        """Test extended capacity properties."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Charging",
            soc=85,
            vBat=538,
            pCharge=2500,
            pDisCharge=0,
            maxBatteryCharge=200,
            currentBatteryCharge=170.0,
            remainCapacity=618,
            fullCapacity=840,
            capacityPercent=74,
            batteryArray=[],
        )

        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
        )

        assert battery_bank.remain_capacity == 618
        assert battery_bank.full_capacity == 840
        assert battery_bank.capacity_percent == 74

    def test_current_properties(self, mock_client):
        """Test current text and type properties."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Charging",
            currentText="49.8",
            currentType="charge",
            soc=85,
            vBat=538,
            pCharge=2500,
            pDisCharge=0,
            maxBatteryCharge=200,
            currentBatteryCharge=170.0,
            batteryArray=[],
        )

        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
        )

        assert battery_bank.current_text == "49.8"
        assert battery_bank.current_type == "charge"

    def test_current_charge(self, mock_client):
        """Test current property returns positive amps for charging."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Charging",
            currentText="49.8A",
            currentType="charge",
            soc=85,
            vBat=538,
            pCharge=2500,
            pDisCharge=0,
            maxBatteryCharge=200,
            currentBatteryCharge=170.0,
            batteryArray=[],
        )
        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
        )
        assert battery_bank.current == 49.8

    def test_current_discharge(self, mock_client):
        """Test current property returns negative amps for discharging."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Discharging",
            currentText="18.1A",
            currentType="discharge",
            soc=60,
            vBat=520,
            pCharge=0,
            pDisCharge=900,
            maxBatteryCharge=200,
            currentBatteryCharge=120.0,
            batteryArray=[],
        )
        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
        )
        assert battery_bank.current == -18.1

    def test_current_no_suffix(self, mock_client):
        """Test current property parses text without unit suffix."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Charging",
            currentText="49.8",
            currentType="charge",
            soc=85,
            vBat=538,
            pCharge=2500,
            pDisCharge=0,
            maxBatteryCharge=200,
            currentBatteryCharge=170.0,
            batteryArray=[],
        )
        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
        )
        assert battery_bank.current == 49.8

    def test_current_none_text(self, mock_client):
        """Test current property returns None when currentText is None."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Idle",
            currentText=None,
            currentType=None,
            soc=50,
            vBat=520,
            pCharge=0,
            pDisCharge=0,
            maxBatteryCharge=200,
            currentBatteryCharge=100.0,
            batteryArray=[],
        )
        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
        )
        assert battery_bank.current is None

    def test_current_empty_string(self, mock_client):
        """Test current property returns None for empty currentText."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Idle",
            currentText="",
            currentType=None,
            soc=50,
            vBat=520,
            pCharge=0,
            pDisCharge=0,
            maxBatteryCharge=200,
            currentBatteryCharge=100.0,
            batteryArray=[],
        )
        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
        )
        assert battery_bank.current is None

    def test_current_transport_precedence(self, mock_client):
        """Test current property prefers transport data over cloud API."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Charging",
            currentText="49.8A",
            currentType="charge",
            soc=85,
            vBat=538,
            pCharge=2500,
            pDisCharge=0,
            maxBatteryCharge=200,
            currentBatteryCharge=170.0,
            batteryArray=[],
        )
        mock_inverter = Mock()
        mock_inverter._transport_battery = None
        mock_inverter._transport_runtime = Mock()
        mock_inverter._transport_runtime.current = -22.5

        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
            inverter=mock_inverter,
        )
        # Transport value (-22.5) takes precedence over cloud (49.8)
        assert battery_bank.current == -22.5

    def test_current_transport_zero_is_valid(self, mock_client):
        """Test current property returns 0.0 from transport (falsy but valid)."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Idle",
            currentText="5.0A",
            currentType="charge",
            soc=50,
            vBat=520,
            pCharge=0,
            pDisCharge=0,
            maxBatteryCharge=200,
            currentBatteryCharge=100.0,
            batteryArray=[],
        )
        mock_inverter = Mock()
        mock_inverter._transport_battery = None
        mock_inverter._transport_runtime = Mock()
        mock_inverter._transport_runtime.current = 0

        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
            inverter=mock_inverter,
        )
        assert battery_bank.current == 0.0

    def test_battery_count_with_total_number(self, mock_client):
        """Test battery_count uses totalNumber when available."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Idle",
            soc=50,
            vBat=520,
            pCharge=0,
            pDisCharge=0,
            maxBatteryCharge=150,
            currentBatteryCharge=75.0,
            batteryArray=[{"batteryKey": "bat1"}, {"batteryKey": "bat2"}],
            totalNumber=3,  # totalNumber differs from array length (edge case)
        )

        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
        )

        # Should prefer totalNumber when available
        assert battery_bank.battery_count == 3


def _make_bank(
    mock_client: LuxpowerClient,
    sample_battery_info: BatteryInfo,
    batteries: list[Battery],
) -> BatteryBank:
    """Helper to create a BatteryBank with pre-populated batteries."""
    bank = BatteryBank(
        client=mock_client,
        inverter_serial="1234567890",
        battery_info=sample_battery_info,
    )
    bank.batteries = batteries
    return bank


def _make_battery(
    mock_client: LuxpowerClient,
    soc: int,
    *,
    soh: int = 100,
    total_voltage: int = 5394,
    max_cell_voltage: int = 3400,
    min_cell_voltage: int = 3350,
    max_cell_temp: int = 350,
    min_cell_temp: int = 340,
    cycle_count: int = 50,
) -> Battery:
    """Helper to create a Battery with configurable values."""
    module = BatteryModule.model_construct(
        batteryKey="test_bat",
        batterySn="test_sn",
        batIndex=0,
        lost=False,
        totalVoltage=total_voltage,
        current=100,
        soc=soc,
        soh=soh,
        currentRemainCapacity=100,
        currentFullCapacity=200,
        batMaxCellTemp=max_cell_temp,
        batMinCellTemp=min_cell_temp,
        batMaxCellVoltage=max_cell_voltage,
        batMinCellVoltage=min_cell_voltage,
        cycleCnt=cycle_count,
        fwVersionText="1.0",
    )
    return Battery(client=mock_client, battery_data=module)


class TestBatteryBankSocDelta:
    """Test BatteryBank soc_delta property."""

    def test_soc_delta_no_batteries(self, mock_client, sample_battery_info):
        """Test soc_delta returns None with no batteries."""
        bank = _make_bank(mock_client, sample_battery_info, [])
        assert bank.soc_delta is None

    def test_soc_delta_one_battery(self, mock_client, sample_battery_info):
        """Test soc_delta returns None with only one battery."""
        bank = _make_bank(mock_client, sample_battery_info, [_make_battery(mock_client, 85)])
        assert bank.soc_delta is None

    def test_soc_delta_two_batteries(self, mock_client, sample_battery_info):
        """Test soc_delta computes max - min across two batteries."""
        bank = _make_bank(
            mock_client,
            sample_battery_info,
            [_make_battery(mock_client, 90), _make_battery(mock_client, 85)],
        )
        assert bank.soc_delta == 5

    def test_soc_delta_three_batteries(self, mock_client, sample_battery_info):
        """Test soc_delta with three batteries picks correct extremes."""
        bank = _make_bank(
            mock_client,
            sample_battery_info,
            [
                _make_battery(mock_client, 82),
                _make_battery(mock_client, 90),
                _make_battery(mock_client, 85),
            ],
        )
        assert bank.soc_delta == 8

    def test_soc_delta_equal_soc(self, mock_client, sample_battery_info):
        """Test soc_delta is 0 when all batteries have equal SOC."""
        bank = _make_bank(
            mock_client,
            sample_battery_info,
            [
                _make_battery(mock_client, 85),
                _make_battery(mock_client, 85),
                _make_battery(mock_client, 85),
            ],
        )
        assert bank.soc_delta == 0


class TestBatteryBankSohMetrics:
    """Test BatteryBank SOH-related properties."""

    def test_min_soh_no_batteries(self, mock_client, sample_battery_info):
        """Test min_soh returns None with no batteries."""
        bank = _make_bank(mock_client, sample_battery_info, [])
        assert bank.min_soh is None

    def test_min_soh_returns_lowest(self, mock_client, sample_battery_info):
        """Test min_soh returns lowest SOH across batteries."""
        bank = _make_bank(
            mock_client,
            sample_battery_info,
            [
                _make_battery(mock_client, 85, soh=98),
                _make_battery(mock_client, 90, soh=92),
                _make_battery(mock_client, 80, soh=95),
            ],
        )
        assert bank.min_soh == 92

    def test_soh_delta_none_with_one_battery(self, mock_client, sample_battery_info):
        """Test soh_delta returns None with fewer than 2 batteries."""
        bank = _make_bank(
            mock_client,
            sample_battery_info,
            [_make_battery(mock_client, 85, soh=98)],
        )
        assert bank.soh_delta is None

    def test_soh_delta_computes_spread(self, mock_client, sample_battery_info):
        """Test soh_delta computes max - min SOH."""
        bank = _make_bank(
            mock_client,
            sample_battery_info,
            [
                _make_battery(mock_client, 85, soh=98),
                _make_battery(mock_client, 90, soh=92),
                _make_battery(mock_client, 80, soh=95),
            ],
        )
        assert bank.soh_delta == 6


class TestBatteryBankCrossBatteryDiagnostics:
    """Test BatteryBank cross-battery diagnostic properties."""

    def test_voltage_delta_none_with_one_battery(self, mock_client, sample_battery_info):
        """Test voltage_delta returns None with fewer than 2 batteries."""
        bank = _make_bank(
            mock_client,
            sample_battery_info,
            [_make_battery(mock_client, 85, total_voltage=5394)],
        )
        assert bank.voltage_delta is None

    def test_voltage_delta_computes_spread(self, mock_client, sample_battery_info):
        """Test voltage_delta computes max - min voltage."""
        bank = _make_bank(
            mock_client,
            sample_battery_info,
            [
                _make_battery(mock_client, 85, total_voltage=5400),  # 54.00V
                _make_battery(mock_client, 80, total_voltage=5350),  # 53.50V
            ],
        )
        assert bank.voltage_delta == 0.50

    def test_cell_voltage_delta_max_no_batteries(self, mock_client, sample_battery_info):
        """Test cell_voltage_delta_max returns None with no batteries."""
        bank = _make_bank(mock_client, sample_battery_info, [])
        assert bank.cell_voltage_delta_max is None

    def test_cell_voltage_delta_max_returns_worst(self, mock_client, sample_battery_info):
        """Test cell_voltage_delta_max returns highest cell delta."""
        bank = _make_bank(
            mock_client,
            sample_battery_info,
            [
                _make_battery(
                    mock_client, 85, max_cell_voltage=3400, min_cell_voltage=3380
                ),  # 0.020V
                _make_battery(
                    mock_client, 80, max_cell_voltage=3400, min_cell_voltage=3350
                ),  # 0.050V
            ],
        )
        assert bank.cell_voltage_delta_max == 0.050

    def test_cycle_count_delta_none_with_one(self, mock_client, sample_battery_info):
        """Test cycle_count_delta returns None with fewer than 2 batteries."""
        bank = _make_bank(
            mock_client,
            sample_battery_info,
            [_make_battery(mock_client, 85, cycle_count=100)],
        )
        assert bank.cycle_count_delta is None

    def test_cycle_count_delta_computes_spread(self, mock_client, sample_battery_info):
        """Test cycle_count_delta computes max - min cycles."""
        bank = _make_bank(
            mock_client,
            sample_battery_info,
            [
                _make_battery(mock_client, 85, cycle_count=120),
                _make_battery(mock_client, 80, cycle_count=95),
                _make_battery(mock_client, 82, cycle_count=110),
            ],
        )
        assert bank.cycle_count_delta == 25

    def test_max_cell_temp_no_batteries(self, mock_client, sample_battery_info):
        """Test max_cell_temp returns None with no batteries."""
        bank = _make_bank(mock_client, sample_battery_info, [])
        assert bank.max_cell_temp is None

    def test_max_cell_temp_returns_highest(self, mock_client, sample_battery_info):
        """Test max_cell_temp returns highest across all batteries."""
        bank = _make_bank(
            mock_client,
            sample_battery_info,
            [
                _make_battery(mock_client, 85, max_cell_temp=380),  # 38.0°C
                _make_battery(mock_client, 80, max_cell_temp=420),  # 42.0°C
            ],
        )
        assert bank.max_cell_temp == 42.0

    def test_temp_delta_no_batteries(self, mock_client, sample_battery_info):
        """Test temp_delta returns None with no batteries."""
        bank = _make_bank(mock_client, sample_battery_info, [])
        assert bank.temp_delta is None

    def test_temp_delta_computes_spread(self, mock_client, sample_battery_info):
        """Test temp_delta computes hottest max - coolest min across bank."""
        bank = _make_bank(
            mock_client,
            sample_battery_info,
            [
                _make_battery(mock_client, 85, max_cell_temp=400, min_cell_temp=370),
                _make_battery(mock_client, 80, max_cell_temp=420, min_cell_temp=350),
            ],
        )
        assert bank.temp_delta == 7.0


class TestBatteryBankBatParallelNum:
    """Test BatteryBank battery_count with batParallelNum from runtime.

    For LXP-EU devices, getBatteryInfo.totalNumber can return 0 when
    CAN bus communication with battery BMS isn't established.
    The batParallelNum from runtime is always correct.
    """

    def test_battery_count_uses_bat_parallel_num(self, mock_client):
        """Test battery_count prefers bat_parallel_num over totalNumber."""
        # totalNumber=0 simulates CAN bus communication failure
        battery_info = BatteryInfo.model_construct(
            batStatus="Idle",
            soc=50,
            vBat=520,
            pCharge=0,
            pDisCharge=0,
            maxBatteryCharge=150,
            currentBatteryCharge=75.0,
            batteryArray=[],  # Empty array
            totalNumber=0,  # BMS communication failed
        )

        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
            bat_parallel_num=3,  # Correct count from runtime
        )

        # Should use bat_parallel_num instead of totalNumber
        assert battery_bank.battery_count == 3

    def test_battery_count_fallback_to_total_number(self, mock_client):
        """Test battery_count falls back to totalNumber when no bat_parallel_num."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Idle",
            soc=50,
            vBat=520,
            pCharge=0,
            pDisCharge=0,
            maxBatteryCharge=150,
            currentBatteryCharge=75.0,
            batteryArray=[],
            totalNumber=2,
        )

        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
            # No bat_parallel_num
        )

        # Should fall back to totalNumber
        assert battery_bank.battery_count == 2

    def test_battery_count_fallback_to_array_length(self, mock_client):
        """Test battery_count falls back to array length when both are zero."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Idle",
            soc=50,
            vBat=520,
            pCharge=0,
            pDisCharge=0,
            maxBatteryCharge=150,
            currentBatteryCharge=75.0,
            batteryArray=[{"batteryKey": "bat1"}, {"batteryKey": "bat2"}],
            totalNumber=0,
        )

        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
            bat_parallel_num=0,  # Zero from runtime too
        )

        # Should fall back to len(batteryArray)
        assert battery_bank.battery_count == 2

    def test_battery_count_ignores_zero_bat_parallel_num(self, mock_client):
        """Test battery_count ignores bat_parallel_num=0."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Idle",
            soc=50,
            vBat=520,
            pCharge=0,
            pDisCharge=0,
            maxBatteryCharge=150,
            currentBatteryCharge=75.0,
            batteryArray=[],
            totalNumber=3,  # Valid totalNumber
        )

        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
            bat_parallel_num=0,  # Zero should be ignored
        )

        # Should fall back to totalNumber
        assert battery_bank.battery_count == 3

    def test_bat_parallel_num_can_be_updated(self, mock_client):
        """Test _bat_parallel_num can be updated after creation."""
        battery_info = BatteryInfo.model_construct(
            batStatus="Idle",
            soc=50,
            vBat=520,
            pCharge=0,
            pDisCharge=0,
            maxBatteryCharge=150,
            currentBatteryCharge=75.0,
            batteryArray=[],
            totalNumber=0,  # BMS communication failed
        )

        battery_bank = BatteryBank(
            client=mock_client,
            inverter_serial="1234567890",
            battery_info=battery_info,
            # No bat_parallel_num initially
        )

        # Initially uses fallback (array length)
        assert battery_bank.battery_count == 0

        # Update after runtime data becomes available
        battery_bank._bat_parallel_num = 3

        # Now should use the updated value
        assert battery_bank.battery_count == 3
