"""Unit tests for performance optimizations (cache warming, lazy loading)."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.inverters.base import BaseInverter
from pylxpweb.devices.inverters.generic import GenericInverter
from pylxpweb.devices.models import Entity
from pylxpweb.devices.station import Station
from pylxpweb.models import BatteryInfo


class ConcreteInverter(BaseInverter):
    """Concrete implementation for testing."""

    def to_entities(self) -> list[Entity]:
        """Generate test entities."""
        return []


@pytest.fixture
def mock_client() -> LuxpowerClient:
    """Create a mock client for testing."""
    client = Mock(spec=LuxpowerClient)
    client.api = Mock()
    client.api.devices = Mock()
    client.api.control = Mock()
    return client


class TestSmartParameterCacheWarming:
    """Tests for smart parameter cache warming optimization."""

    @pytest.mark.asyncio
    async def test_warm_parameter_cache_calls_refresh_with_parameters(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test cache warming calls refresh(include_parameters=True) for inverters."""
        # Create station
        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Test Station",
            location=Mock(),
            timezone="UTC",
            created_date=Mock(),
        )

        # Add mock inverters
        inverter1 = Mock(spec=GenericInverter)
        inverter1.refresh = AsyncMock()
        inverter2 = Mock(spec=GenericInverter)
        inverter2.refresh = AsyncMock()

        station.standalone_inverters = [inverter1, inverter2]

        # Call cache warming
        await station._warm_parameter_cache()

        # Verify refresh was called with include_parameters=True for all inverters
        inverter1.refresh.assert_called_once_with(include_parameters=True)
        inverter2.refresh.assert_called_once_with(include_parameters=True)

    @pytest.mark.asyncio
    async def test_warm_parameter_cache_handles_exceptions_gracefully(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test that _warm_parameter_cache continues even if one inverter fails."""
        # Create station
        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Test Station",
            location=Mock(),
            timezone="UTC",
            created_date=Mock(),
        )

        # Add mock inverters - one that fails, one that succeeds
        inverter1 = Mock(spec=GenericInverter)
        inverter1.refresh = AsyncMock(side_effect=Exception("Network error"))
        inverter2 = Mock(spec=GenericInverter)
        inverter2.refresh = AsyncMock()

        station.standalone_inverters = [inverter1, inverter2]

        # Call cache warming - should not raise exception
        await station._warm_parameter_cache()

        # Both should have been called despite first one failing
        inverter1.refresh.assert_called_once_with(include_parameters=True)
        inverter2.refresh.assert_called_once_with(include_parameters=True)

    @pytest.mark.asyncio
    async def test_warm_parameter_cache_with_no_inverters(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test that _warm_parameter_cache handles empty inverter list."""
        # Create station with no inverters
        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Test Station",
            location=Mock(),
            timezone="UTC",
            created_date=Mock(),
        )

        # Call cache warming - should not raise exception
        await station._warm_parameter_cache()

        # Should complete without errors
        assert len(station.all_inverters) == 0


class TestLazyBatteryLoading:
    """Tests for lazy battery loading optimization."""

    @pytest.mark.asyncio
    async def test_refresh_fetches_battery_on_first_call(self, mock_client: LuxpowerClient) -> None:
        """Test that refresh always fetches battery data on first call (battery_bank is None)."""
        # Create inverter
        inverter = ConcreteInverter(client=mock_client, serial_number="TEST123", model="TestModel")

        # Mock API calls
        mock_client.api.devices.get_inverter_runtime = AsyncMock(return_value=Mock())
        mock_client.api.devices.get_inverter_energy = AsyncMock(return_value=Mock())

        # Battery info with no batteries
        battery_info = BatteryInfo.model_construct(
            status=0,
            soc=0,
            voltage=0,
            chargePower=0,
            dischargePower=0,
            maxCapacity=0,
            currentCapacity=0,
            batteryCount=0,  # No batteries
            batteryArray=[],
        )
        mock_client.api.devices.get_battery_info = AsyncMock(return_value=battery_info)

        # Verify battery_bank is None initially
        assert inverter.battery_bank is None

        # First refresh should always fetch battery data
        await inverter.refresh(force=True)

        # Should have called get_battery_info
        assert mock_client.api.devices.get_battery_info.call_count == 1
        assert inverter.battery_bank is not None
        assert inverter.battery_bank.battery_count == 0

    @pytest.mark.asyncio
    async def test_refresh_skips_battery_when_no_batteries_present(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test that refresh skips battery fetch if battery_count == 0 (lazy loading)."""
        # Create inverter
        inverter = ConcreteInverter(client=mock_client, serial_number="TEST123", model="TestModel")

        # Mock API calls
        mock_client.api.devices.get_inverter_runtime = AsyncMock(return_value=Mock())
        mock_client.api.devices.get_inverter_energy = AsyncMock(return_value=Mock())

        # Battery info with no batteries
        battery_info = BatteryInfo.model_construct(
            status=0,
            soc=0,
            voltage=0,
            chargePower=0,
            dischargePower=0,
            maxCapacity=0,
            currentCapacity=0,
            batteryCount=0,  # No batteries
            batteryArray=[],
        )
        mock_client.api.devices.get_battery_info = AsyncMock(return_value=battery_info)

        # First refresh - should fetch battery data
        await inverter.refresh(force=True)
        assert mock_client.api.devices.get_battery_info.call_count == 1

        # Reset mock
        mock_client.api.devices.get_battery_info.reset_mock()

        # Second refresh - should NOT fetch battery data (lazy loading optimization)
        await inverter.refresh(force=True)

        # Should NOT have called get_battery_info
        assert mock_client.api.devices.get_battery_info.call_count == 0

    @pytest.mark.asyncio
    async def test_refresh_always_fetches_battery_when_batteries_present(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test that refresh always fetches battery data if battery_count > 0."""
        from pylxpweb.models import BatteryModule

        # Create inverter
        inverter = ConcreteInverter(client=mock_client, serial_number="TEST123", model="TestModel")

        # Mock API calls
        mock_client.api.devices.get_inverter_runtime = AsyncMock(return_value=Mock())
        mock_client.api.devices.get_inverter_energy = AsyncMock(return_value=Mock())

        # Battery info with batteries
        battery_module = BatteryModule.model_construct(
            batteryKey="BAT1",
            batterySn="BAT123",
            batIndex=0,
            soc=80,
            totalVoltage=5400,
            current=100,
            soh=95,
            cycleCnt=100,
            batMaxCellTemp=250,
            batMinCellTemp=240,
            batMaxCellVoltage=3400,
            batMinCellVoltage=3380,
            fwVersionText="1.0.0",
            lost=False,
        )
        battery_info = BatteryInfo.model_construct(
            status=0,
            soc=80,
            voltage=539,
            chargePower=2000,
            dischargePower=0,
            maxCapacity=200,
            currentCapacity=160,
            batteryCount=1,  # Has batteries
            batteryArray=[battery_module],
        )
        mock_client.api.devices.get_battery_info = AsyncMock(return_value=battery_info)

        # First refresh
        await inverter.refresh(force=True)
        assert mock_client.api.devices.get_battery_info.call_count == 1
        assert inverter.battery_bank.battery_count == 1

        # Reset mock
        mock_client.api.devices.get_battery_info.reset_mock()

        # Second refresh - should still fetch because has batteries
        await inverter.refresh(force=True)
        assert mock_client.api.devices.get_battery_info.call_count == 1

    @pytest.mark.asyncio
    async def test_refresh_respects_force_flag_for_battery(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test that force=True respects lazy loading (doesn't bypass optimization)."""
        # Create inverter
        inverter = ConcreteInverter(client=mock_client, serial_number="TEST123", model="TestModel")

        # Mock API calls
        mock_client.api.devices.get_inverter_runtime = AsyncMock(return_value=Mock())
        mock_client.api.devices.get_inverter_energy = AsyncMock(return_value=Mock())

        # Battery info with no batteries
        battery_info = BatteryInfo.model_construct(
            status=0,
            soc=0,
            voltage=0,
            chargePower=0,
            dischargePower=0,
            maxCapacity=0,
            currentCapacity=0,
            batteryCount=0,  # No batteries
            batteryArray=[],
        )
        mock_client.api.devices.get_battery_info = AsyncMock(return_value=battery_info)

        # First refresh
        await inverter.refresh(force=True)
        assert mock_client.api.devices.get_battery_info.call_count == 1

        # Reset mock
        mock_client.api.devices.get_battery_info.reset_mock()

        # Second refresh with force=True - lazy loading still applies (no fetch)
        # force=True forces cache expiration checks but respects lazy loading
        await inverter.refresh(force=True)
        assert mock_client.api.devices.get_battery_info.call_count == 0

    @pytest.mark.asyncio
    async def test_lazy_loading_api_call_reduction(self, mock_client: LuxpowerClient) -> None:
        """Test that lazy loading reduces API calls for battery-less inverters."""
        # Create inverter
        inverter = ConcreteInverter(client=mock_client, serial_number="TEST123", model="TestModel")

        # Mock API calls
        mock_client.api.devices.get_inverter_runtime = AsyncMock(return_value=Mock())
        mock_client.api.devices.get_inverter_energy = AsyncMock(return_value=Mock())

        # Battery info with no batteries
        battery_info = BatteryInfo.model_construct(
            status=0,
            soc=0,
            voltage=0,
            chargePower=0,
            dischargePower=0,
            maxCapacity=0,
            currentCapacity=0,
            batteryCount=0,  # No batteries
            batteryArray=[],
        )
        mock_client.api.devices.get_battery_info = AsyncMock(return_value=battery_info)

        # Simulate 10 refresh cycles (typical for a few minutes)
        for _ in range(10):
            await inverter.refresh(force=True)

        # First call fetches battery data, remaining 9 skip it (lazy loading)
        # Expected: 1 call (first check) + 0 calls (9 subsequent skips) = 1 call
        # Without lazy loading: 10 calls
        assert mock_client.api.devices.get_battery_info.call_count == 1

        # Verify API call reduction: 90% reduction (1 vs 10 calls)
        calls_without_optimization = 10
        calls_with_optimization = 1
        reduction_percent = (
            (calls_without_optimization - calls_with_optimization)
            / calls_without_optimization
            * 100
        )
        assert reduction_percent == 90.0  # 90% reduction
