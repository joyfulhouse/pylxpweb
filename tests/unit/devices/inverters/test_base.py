"""Unit tests for BaseInverter abstract class."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.inverters.base import BaseInverter
from pylxpweb.devices.models import DeviceInfo, Entity
from pylxpweb.models import EnergyInfo, InverterRuntime, SuccessResponse


class ConcreteInverter(BaseInverter):
    """Concrete implementation for testing."""

    def to_entities(self) -> list[Entity]:
        """Generate test entities."""
        return [
            Entity(
                unique_id=f"{self.serial_number}_test",
                name=f"{self.model} Test",
                value=42,
            )
        ]


@pytest.fixture
def mock_client() -> LuxpowerClient:
    """Create a mock client for testing."""
    client = Mock(spec=LuxpowerClient)
    client.api = Mock()
    client.api.inverters = Mock()
    client.api.batteries = Mock()
    return client


@pytest.fixture
def sample_runtime() -> InverterRuntime:
    """Create sample runtime data from actual API response."""
    import json
    from pathlib import Path

    # Load sample runtime data from test samples
    sample_path = Path(__file__).parent / "samples" / "runtime_44300E0585.json"
    with open(sample_path) as f:
        data = json.load(f)
    return InverterRuntime.model_validate(data)


@pytest.fixture
def sample_energy() -> EnergyInfo:
    """Create sample energy data."""
    return EnergyInfo(
        success=True,
        serialNum="1234567890",
        soc=85,
        todayYielding=255,  # 25.5 kWh (raw API value in 0.1 kWh units)
        todayCharging=100,
        todayDischarging=80,
        todayImport=50,
        todayExport=30,
        todayUsage=150,
        totalYielding=50000,  # 5000 kWh (raw API value in 0.1 kWh units)
        totalCharging=20000,
        totalDischarging=18000,
        totalImport=10000,
        totalExport=8000,
        totalUsage=30000,
    )


@pytest.fixture
def sample_battery_info():
    """Load sample battery info data."""
    import json
    from pathlib import Path

    from pylxpweb.models import BatteryInfo

    sample_path = Path(__file__).parents[1] / "batteries" / "samples" / "battery_44300E0585.json"
    with open(sample_path) as f:
        data = json.load(f)
    return BatteryInfo.model_validate(data)


class TestBaseInverterInitialization:
    """Test BaseInverter initialization."""

    def test_inverter_initialization(self, mock_client: LuxpowerClient) -> None:
        """Test inverter constructor."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        assert inverter.serial_number == "1234567890"
        assert inverter.model == "TestModel"
        assert inverter._client is mock_client
        assert inverter._runtime is None
        assert inverter._energy is None
        assert inverter._battery_bank is None

    def test_cannot_instantiate_base_inverter_directly(self, mock_client: LuxpowerClient) -> None:
        """Test that BaseInverter cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            BaseInverter(  # type: ignore
                client=mock_client, serial_number="1234567890", model="TestModel"
            )


class TestInverterRefresh:
    """Test inverter refresh functionality."""

    @pytest.mark.asyncio
    async def test_refresh_fetches_runtime_and_energy(
        self,
        mock_client: LuxpowerClient,
        sample_runtime: InverterRuntime,
        sample_energy: EnergyInfo,
        sample_battery_info,
    ) -> None:
        """Test refresh fetches runtime, energy, and battery data."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock API responses
        mock_client.api.devices.get_inverter_runtime = AsyncMock(return_value=sample_runtime)
        mock_client.api.devices.get_inverter_energy = AsyncMock(return_value=sample_energy)
        mock_client.api.devices.get_battery_info = AsyncMock(return_value=sample_battery_info)

        # Refresh
        await inverter.refresh()

        # Verify API calls
        mock_client.api.devices.get_inverter_runtime.assert_called_once_with("1234567890")
        mock_client.api.devices.get_inverter_energy.assert_called_once_with("1234567890")
        mock_client.api.devices.get_battery_info.assert_called_once_with("1234567890")

        # Verify data stored
        assert inverter._runtime is sample_runtime
        assert inverter._energy is sample_energy
        assert inverter._battery_bank is not None
        assert len(inverter._battery_bank.batteries) == 3  # Sample has 3 batteries
        assert inverter._last_refresh is not None

    @pytest.mark.asyncio
    async def test_refresh_handles_runtime_error(
        self, mock_client: LuxpowerClient, sample_energy: EnergyInfo, sample_battery_info
    ) -> None:
        """Test refresh handles runtime API error gracefully."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock runtime error, energy and battery success
        mock_client.api.devices.get_inverter_runtime = AsyncMock(side_effect=Exception("API Error"))
        mock_client.api.devices.get_inverter_energy = AsyncMock(return_value=sample_energy)
        mock_client.api.devices.get_battery_info = AsyncMock(return_value=sample_battery_info)

        await inverter.refresh()

        # Runtime should be None (error), energy and batteries should be set
        assert inverter._runtime is None
        assert inverter._energy is sample_energy
        assert inverter._battery_bank is not None
        assert len(inverter._battery_bank.batteries) == 3

    @pytest.mark.asyncio
    async def test_refresh_handles_energy_error(
        self, mock_client: LuxpowerClient, sample_runtime: InverterRuntime, sample_battery_info
    ) -> None:
        """Test refresh handles energy API error gracefully."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock runtime success, energy error, battery success
        mock_client.api.devices.get_inverter_runtime = AsyncMock(return_value=sample_runtime)
        mock_client.api.devices.get_inverter_energy = AsyncMock(side_effect=Exception("API Error"))
        mock_client.api.devices.get_battery_info = AsyncMock(return_value=sample_battery_info)

        await inverter.refresh()

        # Runtime and batteries should be set, energy should be None (error)
        assert inverter._runtime is sample_runtime
        assert inverter._energy is None
        assert inverter._battery_bank is not None
        assert len(inverter._battery_bank.batteries) == 3


class TestInverterDeviceInfo:
    """Test inverter device info generation."""

    def test_to_device_info(
        self, mock_client: LuxpowerClient, sample_runtime: InverterRuntime
    ) -> None:
        """Test device info generation."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter._runtime = sample_runtime

        device_info = inverter.to_device_info()

        assert isinstance(device_info, DeviceInfo)
        assert device_info.name == "TestModel 1234567890"
        assert device_info.manufacturer == "EG4/Luxpower"
        assert device_info.model == "TestModel"
        # Sample data has fwCode="FAAB-2122"
        assert device_info.sw_version == "FAAB-2122"
        assert ("pylxpweb", "inverter_1234567890") in device_info.identifiers

    def test_to_device_info_without_runtime(self, mock_client: LuxpowerClient) -> None:
        """Test device info without runtime data."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        device_info = inverter.to_device_info()

        assert device_info.sw_version is None


class TestInverterProperties:
    """Test inverter convenience properties."""

    def test_model_property_with_valid_model(self, mock_client: LuxpowerClient) -> None:
        """Test model property returns the model set during initialization."""
        inverter = ConcreteInverter(client=mock_client, serial_number="1234567890", model="18KPV")
        assert inverter.model == "18KPV"

    def test_model_property_with_flexboss_model(self, mock_client: LuxpowerClient) -> None:
        """Test model property with FlexBOSS model name."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        assert inverter.model == "FlexBOSS21"

    def test_model_property_with_empty_string(self, mock_client: LuxpowerClient) -> None:
        """Test model property returns 'Unknown' when model is empty string."""
        inverter = ConcreteInverter(client=mock_client, serial_number="1234567890", model="")
        assert inverter.model == "Unknown"

    def test_model_property_with_unknown(self, mock_client: LuxpowerClient) -> None:
        """Test model property with 'Unknown' model."""
        inverter = ConcreteInverter(client=mock_client, serial_number="1234567890", model="Unknown")
        # Should return "Unknown" as-is since it's a valid string
        assert inverter.model == "Unknown"

    def test_model_property_not_affected_by_runtime(
        self, mock_client: LuxpowerClient, sample_runtime: InverterRuntime
    ) -> None:
        """Test model property is not affected by runtime.modelText (which is hex code)."""
        inverter = ConcreteInverter(client=mock_client, serial_number="1234567890", model="18KPV")
        inverter._runtime = sample_runtime

        # Model should remain "18KPV" regardless of runtime.modelText (which is "0x1098600")
        assert inverter.model == "18KPV"
        # Verify runtime has modelText (just to confirm test setup)
        assert sample_runtime.modelText == "0x1098600"

    def test_has_data_with_runtime(
        self, mock_client: LuxpowerClient, sample_runtime: InverterRuntime
    ) -> None:
        """Test has_data returns True when runtime available."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter._runtime = sample_runtime

        assert inverter.has_data is True

    def test_has_data_without_runtime(self, mock_client: LuxpowerClient) -> None:
        """Test has_data returns False when no runtime."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        assert inverter.has_data is False

    def test_power_output(
        self, mock_client: LuxpowerClient, sample_runtime: InverterRuntime
    ) -> None:
        """Test power_output property."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter._runtime = sample_runtime

        # Sample data has pinv=0
        assert inverter.power_output == 0.0

    def test_power_output_without_data(self, mock_client: LuxpowerClient) -> None:
        """Test power_output returns 0 without data."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        assert inverter.power_output == 0.0

    def test_total_energy_today(
        self, mock_client: LuxpowerClient, sample_energy: EnergyInfo
    ) -> None:
        """Test total_energy_today property."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter._energy = sample_energy

        assert inverter.total_energy_today == 25.5

    def test_total_energy_today_without_data(self, mock_client: LuxpowerClient) -> None:
        """Test total_energy_today returns 0 without data."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        assert inverter.total_energy_today == 0.0

    def test_total_energy_lifetime(
        self, mock_client: LuxpowerClient, sample_energy: EnergyInfo
    ) -> None:
        """Test total_energy_lifetime property."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter._energy = sample_energy

        assert inverter.total_energy_lifetime == 5000.0

    def test_total_energy_lifetime_without_data(self, mock_client: LuxpowerClient) -> None:
        """Test total_energy_lifetime returns 0 without data."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        assert inverter.total_energy_lifetime == 0.0

    def test_battery_soc(
        self, mock_client: LuxpowerClient, sample_runtime: InverterRuntime
    ) -> None:
        """Test battery_soc property."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter._runtime = sample_runtime

        # Sample data has soc=73
        assert inverter.battery_soc == 73

    def test_battery_soc_without_data(self, mock_client: LuxpowerClient) -> None:
        """Test battery_soc returns None without data."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        assert inverter.battery_soc is None

    def test_energy_today_charging(
        self, mock_client: LuxpowerClient, sample_energy: EnergyInfo
    ) -> None:
        """Test energy_today_charging property."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter._energy = sample_energy

        # todayCharging=100 → 10.0 kWh (÷10)
        assert inverter.energy_today_charging == 10.0

    def test_energy_today_discharging(
        self, mock_client: LuxpowerClient, sample_energy: EnergyInfo
    ) -> None:
        """Test energy_today_discharging property."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter._energy = sample_energy

        # todayDischarging=80 → 8.0 kWh (÷10)
        assert inverter.energy_today_discharging == 8.0

    def test_energy_today_import(
        self, mock_client: LuxpowerClient, sample_energy: EnergyInfo
    ) -> None:
        """Test energy_today_import property."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter._energy = sample_energy

        # todayImport=50 → 5.0 kWh (÷10)
        assert inverter.energy_today_import == 5.0

    def test_energy_today_export(
        self, mock_client: LuxpowerClient, sample_energy: EnergyInfo
    ) -> None:
        """Test energy_today_export property."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter._energy = sample_energy

        # todayExport=30 → 3.0 kWh (÷10)
        assert inverter.energy_today_export == 3.0

    def test_energy_today_usage(
        self, mock_client: LuxpowerClient, sample_energy: EnergyInfo
    ) -> None:
        """Test energy_today_usage property."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter._energy = sample_energy

        # todayUsage=150 → 15.0 kWh (÷10)
        assert inverter.energy_today_usage == 15.0

    def test_energy_lifetime_charging(
        self, mock_client: LuxpowerClient, sample_energy: EnergyInfo
    ) -> None:
        """Test energy_lifetime_charging property."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter._energy = sample_energy

        # totalCharging=20000 → 2000.0 kWh (÷10)
        assert inverter.energy_lifetime_charging == 2000.0

    def test_energy_lifetime_discharging(
        self, mock_client: LuxpowerClient, sample_energy: EnergyInfo
    ) -> None:
        """Test energy_lifetime_discharging property."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter._energy = sample_energy

        # totalDischarging=18000 → 1800.0 kWh (÷10)
        assert inverter.energy_lifetime_discharging == 1800.0

    def test_energy_lifetime_import(
        self, mock_client: LuxpowerClient, sample_energy: EnergyInfo
    ) -> None:
        """Test energy_lifetime_import property."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter._energy = sample_energy

        # totalImport=10000 → 1000.0 kWh (÷10)
        assert inverter.energy_lifetime_import == 1000.0

    def test_energy_lifetime_export(
        self, mock_client: LuxpowerClient, sample_energy: EnergyInfo
    ) -> None:
        """Test energy_lifetime_export property."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter._energy = sample_energy

        # totalExport=8000 → 800.0 kWh (÷10)
        assert inverter.energy_lifetime_export == 800.0

    def test_energy_lifetime_usage(
        self, mock_client: LuxpowerClient, sample_energy: EnergyInfo
    ) -> None:
        """Test energy_lifetime_usage property."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter._energy = sample_energy

        # totalUsage=30000 → 3000.0 kWh (÷10)
        assert inverter.energy_lifetime_usage == 3000.0

    def test_all_energy_properties_without_data(self, mock_client: LuxpowerClient) -> None:
        """Test all energy properties return 0.0 without data."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Today's energy
        assert inverter.energy_today_charging == 0.0
        assert inverter.energy_today_discharging == 0.0
        assert inverter.energy_today_import == 0.0
        assert inverter.energy_today_export == 0.0
        assert inverter.energy_today_usage == 0.0

        # Lifetime energy
        assert inverter.energy_lifetime_charging == 0.0
        assert inverter.energy_lifetime_discharging == 0.0
        assert inverter.energy_lifetime_import == 0.0
        assert inverter.energy_lifetime_export == 0.0
        assert inverter.energy_lifetime_usage == 0.0


class TestInverterBatteries:
    """Test inverter battery bank management."""

    def test_battery_bank_initialization(self, mock_client: LuxpowerClient) -> None:
        """Test battery_bank is initialized as None."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        assert inverter._battery_bank is None

    def test_battery_bank_can_be_populated(self, mock_client: LuxpowerClient) -> None:
        """Test battery_bank can be populated."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Add mock battery bank
        battery_bank = Mock()
        battery_bank.batteries = [Mock(), Mock()]
        inverter._battery_bank = battery_bank

        assert inverter._battery_bank is battery_bank
        assert len(inverter._battery_bank.batteries) == 2


class TestInverterControlOperations:
    """Test inverter control operations (universal controls)."""

    @pytest.mark.asyncio
    async def test_read_parameters(self, mock_client: LuxpowerClient) -> None:
        """Test reading inverter parameters."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock control API
        mock_client.api.control = Mock()
        mock_response = Mock()
        mock_response.parameters = {"reg_21": 512, "FUNC_SET_TO_STANDBY": True}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_response)

        # Read parameters
        params = await inverter.read_parameters(21, 1)

        # Verify API call
        mock_client.api.control.read_parameters.assert_called_once_with("1234567890", 21, 1)

        # Verify returned data
        assert params == {"reg_21": 512, "FUNC_SET_TO_STANDBY": True}

    @pytest.mark.asyncio
    async def test_write_parameters(self, mock_client: LuxpowerClient) -> None:
        """Test writing inverter parameters."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock control API
        mock_client.api.control = Mock()
        mock_response = Mock()
        mock_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_response)

        # Write parameters
        result = await inverter.write_parameters({21: 512})

        # Verify API call
        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {21: 512})

        # Verify success
        assert result is True

    @pytest.mark.asyncio
    async def test_set_standby_mode_to_standby(self, mock_client: LuxpowerClient) -> None:
        """Test setting inverter to standby mode."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock control API
        mock_client.api.control = Mock()

        # Mock read response - bit 9 currently set (power on)
        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_21": 512}  # Bit 9 set (1 << 9 = 512)
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        # Mock write response
        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        # Set to standby (should clear bit 9)
        result = await inverter.set_standby_mode(True)

        # Verify read call
        mock_client.api.control.read_parameters.assert_called_once_with("1234567890", 21, 1)

        # Verify write call - bit 9 should be cleared (0)
        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {21: 0})

        assert result is True

    @pytest.mark.asyncio
    async def test_set_standby_mode_to_power_on(self, mock_client: LuxpowerClient) -> None:
        """Test powering on inverter from standby."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock control API
        mock_client.api.control = Mock()

        # Mock read response - bit 9 currently clear (standby)
        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_21": 0}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        # Mock write response
        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        # Power on (should set bit 9)
        result = await inverter.set_standby_mode(False)

        # Verify write call - bit 9 should be set (512)
        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {21: 512})

        assert result is True

    @pytest.mark.asyncio
    async def test_get_battery_soc_limits(self, mock_client: LuxpowerClient) -> None:
        """Test reading battery SOC limits."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Set cached parameters
        inverter.parameters = {
            "HOLD_DISCHG_CUT_OFF_SOC_EOD": 15,
            "HOLD_SOC_LOW_LIMIT_EPS_DISCHG": 20,
        }

        # Get SOC limits from property
        limits = inverter.battery_soc_limits

        # Verify returned data
        assert limits == {"on_grid_limit": 15, "off_grid_limit": 20}

    @pytest.mark.asyncio
    async def test_set_battery_soc_limits_both(self, mock_client: LuxpowerClient) -> None:
        """Test setting both SOC limits."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock control API
        mock_client.api.control = Mock()
        mock_response = Mock()
        mock_response.success = True
        mock_client.api.control.write_parameter = AsyncMock(return_value=mock_response)

        # Set both limits
        result = await inverter.set_battery_soc_limits(on_grid_limit=20, off_grid_limit=15)

        # Verify API calls (two separate calls for two parameters)
        assert mock_client.api.control.write_parameter.call_count == 2
        calls = mock_client.api.control.write_parameter.call_args_list
        assert calls[0][0] == ("1234567890", "HOLD_DISCHG_CUT_OFF_SOC_EOD", "20")
        assert calls[1][0] == ("1234567890", "HOLD_SOC_LOW_LIMIT_EPS_DISCHG", "15")

        assert result is True

    @pytest.mark.asyncio
    async def test_set_battery_soc_limits_on_grid_only(self, mock_client: LuxpowerClient) -> None:
        """Test setting only on-grid SOC limit."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock control API
        mock_client.api.control = Mock()
        mock_response = Mock()
        mock_response.success = True
        mock_client.api.control.write_parameter = AsyncMock(return_value=mock_response)

        # Set only on-grid limit
        result = await inverter.set_battery_soc_limits(on_grid_limit=25)

        # Verify API call with parameter name and string value
        mock_client.api.control.write_parameter.assert_called_once_with(
            "1234567890", "HOLD_DISCHG_CUT_OFF_SOC_EOD", "25"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_set_battery_soc_limits_off_grid_only(self, mock_client: LuxpowerClient) -> None:
        """Test setting only off-grid SOC limit."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock control API
        mock_client.api.control = Mock()
        mock_response = Mock()
        mock_response.success = True
        mock_client.api.control.write_parameter = AsyncMock(return_value=mock_response)

        # Set only off-grid limit
        result = await inverter.set_battery_soc_limits(off_grid_limit=10)

        # Verify API call with parameter name and string value
        mock_client.api.control.write_parameter.assert_called_once_with(
            "1234567890", "HOLD_SOC_LOW_LIMIT_EPS_DISCHG", "10"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_set_battery_soc_limits_validation_on_grid_too_low(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test on-grid SOC limit validation - too low."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Try to set on-grid limit below 10%
        with pytest.raises(ValueError, match="on_grid_limit must be between 10 and 90%"):
            await inverter.set_battery_soc_limits(on_grid_limit=5)

    @pytest.mark.asyncio
    async def test_set_battery_soc_limits_validation_on_grid_too_high(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test on-grid SOC limit validation - too high."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Try to set on-grid limit above 90%
        with pytest.raises(ValueError, match="on_grid_limit must be between 10 and 90%"):
            await inverter.set_battery_soc_limits(on_grid_limit=95)

    @pytest.mark.asyncio
    async def test_set_battery_soc_limits_validation_off_grid_too_low(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test off-grid SOC limit validation - too low."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Try to set off-grid limit below 0%
        with pytest.raises(ValueError, match="off_grid_limit must be between 0 and 100%"):
            await inverter.set_battery_soc_limits(off_grid_limit=-5)

    @pytest.mark.asyncio
    async def test_set_battery_soc_limits_validation_off_grid_too_high(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test off-grid SOC limit validation - too high."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Try to set off-grid limit above 100%
        with pytest.raises(ValueError, match="off_grid_limit must be between 0 and 100%"):
            await inverter.set_battery_soc_limits(off_grid_limit=105)


class TestWorkingModeControls:
    """Test working mode control methods (Issue #16)."""

    @pytest.mark.asyncio
    async def test_enable_ac_charge_mode(self, mock_client: LuxpowerClient) -> None:
        """Test enable_ac_charge_mode method."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock the control endpoint method
        mock_response = Mock(spec=SuccessResponse)
        mock_response.success = True
        mock_client.api.control.enable_ac_charge_mode = AsyncMock(return_value=mock_response)

        # Enable AC charge mode
        result = await inverter.enable_ac_charge_mode()

        # Verify correct endpoint call
        mock_client.api.control.enable_ac_charge_mode.assert_called_once_with("1234567890")
        assert result is True

    @pytest.mark.asyncio
    async def test_disable_ac_charge_mode(self, mock_client: LuxpowerClient) -> None:
        """Test disable_ac_charge_mode method."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock the control endpoint method
        mock_response = Mock(spec=SuccessResponse)
        mock_response.success = True
        mock_client.api.control.disable_ac_charge_mode = AsyncMock(return_value=mock_response)

        # Disable AC charge mode
        result = await inverter.disable_ac_charge_mode()

        # Verify correct endpoint call
        mock_client.api.control.disable_ac_charge_mode.assert_called_once_with("1234567890")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_ac_charge_mode_status(self, mock_client: LuxpowerClient) -> None:
        """Test get_ac_charge_mode_status method."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock the control endpoint method
        mock_client.api.control.get_ac_charge_mode_status = AsyncMock(return_value=True)

        # Get AC charge mode status
        status = await inverter.get_ac_charge_mode_status()

        # Verify correct endpoint call
        mock_client.api.control.get_ac_charge_mode_status.assert_called_once_with("1234567890")
        assert status is True

    @pytest.mark.asyncio
    async def test_enable_pv_charge_priority(self, mock_client: LuxpowerClient) -> None:
        """Test enable_pv_charge_priority method."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock the control endpoint method
        mock_response = Mock(spec=SuccessResponse)
        mock_response.success = True
        mock_client.api.control.enable_pv_charge_priority = AsyncMock(return_value=mock_response)

        # Enable PV charge priority
        result = await inverter.enable_pv_charge_priority()

        # Verify correct endpoint call
        mock_client.api.control.enable_pv_charge_priority.assert_called_once_with("1234567890")
        assert result is True

    @pytest.mark.asyncio
    async def test_disable_pv_charge_priority(self, mock_client: LuxpowerClient) -> None:
        """Test disable_pv_charge_priority method."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock the control endpoint method
        mock_response = Mock(spec=SuccessResponse)
        mock_response.success = True
        mock_client.api.control.disable_pv_charge_priority = AsyncMock(return_value=mock_response)

        # Disable PV charge priority
        result = await inverter.disable_pv_charge_priority()

        # Verify correct endpoint call
        mock_client.api.control.disable_pv_charge_priority.assert_called_once_with("1234567890")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_pv_charge_priority_status(self, mock_client: LuxpowerClient) -> None:
        """Test get_pv_charge_priority_status method."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock the control endpoint method
        mock_client.api.control.get_pv_charge_priority_status = AsyncMock(return_value=True)

        # Get PV charge priority status
        status = await inverter.get_pv_charge_priority_status()

        # Verify correct endpoint call
        mock_client.api.control.get_pv_charge_priority_status.assert_called_once_with("1234567890")
        assert status is True

    @pytest.mark.asyncio
    async def test_enable_forced_discharge(self, mock_client: LuxpowerClient) -> None:
        """Test enable_forced_discharge method."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock the control endpoint method
        mock_response = Mock(spec=SuccessResponse)
        mock_response.success = True
        mock_client.api.control.enable_forced_discharge = AsyncMock(return_value=mock_response)

        # Enable forced discharge
        result = await inverter.enable_forced_discharge()

        # Verify correct endpoint call
        mock_client.api.control.enable_forced_discharge.assert_called_once_with("1234567890")
        assert result is True

    @pytest.mark.asyncio
    async def test_disable_forced_discharge(self, mock_client: LuxpowerClient) -> None:
        """Test disable_forced_discharge method."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock the control endpoint method
        mock_response = Mock(spec=SuccessResponse)
        mock_response.success = True
        mock_client.api.control.disable_forced_discharge = AsyncMock(return_value=mock_response)

        # Disable forced discharge
        result = await inverter.disable_forced_discharge()

        # Verify correct endpoint call
        mock_client.api.control.disable_forced_discharge.assert_called_once_with("1234567890")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_forced_discharge_status(self, mock_client: LuxpowerClient) -> None:
        """Test get_forced_discharge_status method."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock the control endpoint method
        mock_client.api.control.get_forced_discharge_status = AsyncMock(return_value=True)

        # Get forced discharge status
        status = await inverter.get_forced_discharge_status()

        # Verify correct endpoint call
        mock_client.api.control.get_forced_discharge_status.assert_called_once_with("1234567890")
        assert status is True

    @pytest.mark.asyncio
    async def test_enable_peak_shaving_mode(self, mock_client: LuxpowerClient) -> None:
        """Test enable_peak_shaving_mode method."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock the control endpoint method
        mock_response = Mock(spec=SuccessResponse)
        mock_response.success = True
        mock_client.api.control.enable_peak_shaving_mode = AsyncMock(return_value=mock_response)

        # Enable peak shaving mode
        result = await inverter.enable_peak_shaving_mode()

        # Verify correct endpoint call
        mock_client.api.control.enable_peak_shaving_mode.assert_called_once_with("1234567890")
        assert result is True

    @pytest.mark.asyncio
    async def test_disable_peak_shaving_mode(self, mock_client: LuxpowerClient) -> None:
        """Test disable_peak_shaving_mode method."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock the control endpoint method
        mock_response = Mock(spec=SuccessResponse)
        mock_response.success = True
        mock_client.api.control.disable_peak_shaving_mode = AsyncMock(return_value=mock_response)

        # Disable peak shaving mode
        result = await inverter.disable_peak_shaving_mode()

        # Verify correct endpoint call
        mock_client.api.control.disable_peak_shaving_mode.assert_called_once_with("1234567890")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_peak_shaving_mode_status(self, mock_client: LuxpowerClient) -> None:
        """Test get_peak_shaving_mode_status method."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock the control endpoint method
        mock_client.api.control.get_peak_shaving_mode_status = AsyncMock(return_value=True)

        # Get peak shaving mode status
        status = await inverter.get_peak_shaving_mode_status()

        # Verify correct endpoint call
        mock_client.api.control.get_peak_shaving_mode_status.assert_called_once_with("1234567890")
        assert status is True
