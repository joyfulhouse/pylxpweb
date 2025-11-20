"""Unit tests for BaseInverter abstract class."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.inverters.base import BaseInverter
from pylxpweb.devices.models import DeviceInfo, Entity
from pylxpweb.models import EnergyInfo, InverterRuntime


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
        todayYielding=25500,  # 25.5 kWh in Wh
        todayCharging=10000,
        todayDischarging=8000,
        todayImport=5000,
        todayExport=3000,
        todayUsage=15000,
        totalYielding=5000000,  # 5000 kWh in Wh
        totalCharging=2000000,
        totalDischarging=1800000,
        totalImport=1000000,
        totalExport=800000,
        totalUsage=3000000,
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
        assert inverter.runtime is None
        assert inverter.energy is None
        assert inverter.batteries == []

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
        mock_client.api.inverters.get_inverter_runtime = AsyncMock(return_value=sample_runtime)
        mock_client.api.inverters.get_inverter_energy = AsyncMock(return_value=sample_energy)
        mock_client.api.batteries.get_battery_info = AsyncMock(return_value=sample_battery_info)

        # Refresh
        await inverter.refresh()

        # Verify API calls
        mock_client.api.inverters.get_inverter_runtime.assert_called_once_with("1234567890")
        mock_client.api.inverters.get_inverter_energy.assert_called_once_with("1234567890")
        mock_client.api.batteries.get_battery_info.assert_called_once_with("1234567890")

        # Verify data stored
        assert inverter.runtime is sample_runtime
        assert inverter.energy is sample_energy
        assert len(inverter.batteries) == 3  # Sample has 3 batteries
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
        mock_client.api.inverters.get_inverter_runtime = AsyncMock(
            side_effect=Exception("API Error")
        )
        mock_client.api.inverters.get_inverter_energy = AsyncMock(return_value=sample_energy)
        mock_client.api.batteries.get_battery_info = AsyncMock(return_value=sample_battery_info)

        await inverter.refresh()

        # Runtime should be None (error), energy and batteries should be set
        assert inverter.runtime is None
        assert inverter.energy is sample_energy
        assert len(inverter.batteries) == 3

    @pytest.mark.asyncio
    async def test_refresh_handles_energy_error(
        self, mock_client: LuxpowerClient, sample_runtime: InverterRuntime, sample_battery_info
    ) -> None:
        """Test refresh handles energy API error gracefully."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock runtime success, energy error, battery success
        mock_client.api.inverters.get_inverter_runtime = AsyncMock(return_value=sample_runtime)
        mock_client.api.inverters.get_inverter_energy = AsyncMock(
            side_effect=Exception("API Error")
        )
        mock_client.api.batteries.get_battery_info = AsyncMock(return_value=sample_battery_info)

        await inverter.refresh()

        # Runtime and batteries should be set, energy should be None (error)
        assert inverter.runtime is sample_runtime
        assert inverter.energy is None
        assert len(inverter.batteries) == 3


class TestInverterDeviceInfo:
    """Test inverter device info generation."""

    def test_to_device_info(
        self, mock_client: LuxpowerClient, sample_runtime: InverterRuntime
    ) -> None:
        """Test device info generation."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter.runtime = sample_runtime

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

    def test_has_data_with_runtime(
        self, mock_client: LuxpowerClient, sample_runtime: InverterRuntime
    ) -> None:
        """Test has_data returns True when runtime available."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )
        inverter.runtime = sample_runtime

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
        inverter.runtime = sample_runtime

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
        inverter.energy = sample_energy

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
        inverter.energy = sample_energy

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
        inverter.runtime = sample_runtime

        # Sample data has soc=73
        assert inverter.battery_soc == 73

    def test_battery_soc_without_data(self, mock_client: LuxpowerClient) -> None:
        """Test battery_soc returns None without data."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        assert inverter.battery_soc is None


class TestInverterBatteries:
    """Test inverter battery management."""

    def test_batteries_list_initialization(self, mock_client: LuxpowerClient) -> None:
        """Test batteries list is initialized empty."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        assert inverter.batteries == []
        assert isinstance(inverter.batteries, list)

    def test_batteries_can_be_populated(self, mock_client: LuxpowerClient) -> None:
        """Test batteries list can be populated."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Add mock batteries
        battery1 = Mock()
        battery2 = Mock()
        inverter.batteries = [battery1, battery2]

        assert len(inverter.batteries) == 2
        assert battery1 in inverter.batteries
        assert battery2 in inverter.batteries
