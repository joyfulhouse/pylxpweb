"""Unit tests for BaseInverter caching functionality."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.inverters.base import BaseInverter
from pylxpweb.devices.models import Entity
from pylxpweb.models import BatteryInfo, EnergyInfo, InverterRuntime


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


@pytest.fixture
def sample_runtime() -> InverterRuntime:
    """Create sample runtime data."""
    return InverterRuntime.model_construct(
        success=True,
        serialNum="1234567890",
        status=1,
        statusText="Online",
        pinv=1000,
        soc=75,
        fwCode="TEST-1.0",
    )


@pytest.fixture
def sample_energy() -> EnergyInfo:
    """Create sample energy data."""
    return EnergyInfo(
        success=True,
        serialNum="1234567890",
        soc=75,
        todayYielding=10000,
        todayCharging=5000,
        todayDischarging=4000,
        todayImport=2000,
        todayExport=1000,
        todayUsage=8000,
        totalYielding=1000000,
        totalCharging=500000,
        totalDischarging=400000,
        totalImport=200000,
        totalExport=100000,
        totalUsage=800000,
    )


@pytest.fixture
def sample_battery_info() -> BatteryInfo:
    """Create sample battery info."""
    return BatteryInfo.model_construct(
        success=True,
        serialNum="1234567890",
        status=1,
        soc=75,
        voltage=539,  # 53.9V (÷10)
        chargePower=0,
        dischargePower=0,
        maxCapacity=200,
        currentCapacity=150,
        batteryCount=2,
        batteryArray=[],
    )


class TestParameterCaching:
    """Test parameter caching functionality.

    Note: Per-range caching was removed in favor of simpler invalidation.
    These tests verify cache invalidation behavior.
    """

    @pytest.mark.asyncio
    async def test_write_parameters_invalidates_cache(self, mock_client: LuxpowerClient) -> None:
        """Test that write_parameters invalidates parameters cache."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Set cache time to simulate cached parameters
        inverter._parameters_cache_time = datetime.now()
        assert inverter._parameters_cache_time is not None

        # Mock write response
        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        # Write to register - should invalidate cache
        await inverter.write_parameters({21: 256})

        # Verify cache was invalidated
        assert inverter._parameters_cache_time is None


class TestDataCaching:
    """Test runtime, energy, and battery data caching."""

    @pytest.mark.asyncio
    async def test_refresh_caches_runtime_data(
        self,
        mock_client: LuxpowerClient,
        sample_runtime: InverterRuntime,
        sample_energy: EnergyInfo,
        sample_battery_info: BatteryInfo,
    ) -> None:
        """Test that refresh() caches runtime data."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock API responses
        mock_client.api.devices.get_inverter_runtime = AsyncMock(return_value=sample_runtime)
        mock_client.api.devices.get_inverter_energy = AsyncMock(return_value=sample_energy)
        mock_client.api.devices.get_battery_info = AsyncMock(return_value=sample_battery_info)

        # First refresh - should fetch all data
        await inverter.refresh()
        assert mock_client.api.devices.get_inverter_runtime.call_count == 1
        assert mock_client.api.devices.get_inverter_energy.call_count == 1
        assert mock_client.api.devices.get_battery_info.call_count == 1

        # Second refresh immediately - should use cache (30s TTL for runtime/battery)
        await inverter.refresh()
        assert mock_client.api.devices.get_inverter_runtime.call_count == 1  # No additional call
        assert mock_client.api.devices.get_inverter_energy.call_count == 1  # No additional call
        assert mock_client.api.devices.get_battery_info.call_count == 1  # No additional call

    @pytest.mark.asyncio
    async def test_refresh_force_bypasses_cache(
        self,
        mock_client: LuxpowerClient,
        sample_runtime: InverterRuntime,
        sample_energy: EnergyInfo,
        sample_battery_info: BatteryInfo,
    ) -> None:
        """Test that refresh(force=True) bypasses cache."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock API responses
        mock_client.api.devices.get_inverter_runtime = AsyncMock(return_value=sample_runtime)
        mock_client.api.devices.get_inverter_energy = AsyncMock(return_value=sample_energy)
        mock_client.api.devices.get_battery_info = AsyncMock(return_value=sample_battery_info)

        # First refresh
        await inverter.refresh()
        assert mock_client.api.devices.get_inverter_runtime.call_count == 1

        # Force refresh - should bypass cache
        await inverter.refresh(force=True)
        assert mock_client.api.devices.get_inverter_runtime.call_count == 2

    @pytest.mark.asyncio
    async def test_refresh_respects_different_ttls(
        self,
        mock_client: LuxpowerClient,
        sample_runtime: InverterRuntime,
        sample_energy: EnergyInfo,
        sample_battery_info: BatteryInfo,
    ) -> None:
        """Test that runtime (30s TTL) and energy (5min TTL) have different refresh rates."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Shorten TTLs for testing
        inverter._runtime_cache_ttl = timedelta(seconds=0.5)
        inverter._energy_cache_ttl = timedelta(seconds=2)

        # Mock API responses
        mock_client.api.devices.get_inverter_runtime = AsyncMock(return_value=sample_runtime)
        mock_client.api.devices.get_inverter_energy = AsyncMock(return_value=sample_energy)
        mock_client.api.devices.get_battery_info = AsyncMock(return_value=sample_battery_info)

        # First refresh
        await inverter.refresh()
        assert mock_client.api.devices.get_inverter_runtime.call_count == 1
        assert mock_client.api.devices.get_inverter_energy.call_count == 1

        # Wait for runtime cache to expire (but not energy)
        await asyncio.sleep(0.6)

        # Second refresh - only runtime should be fetched
        await inverter.refresh()
        assert mock_client.api.devices.get_inverter_runtime.call_count == 2  # Refreshed
        assert mock_client.api.devices.get_inverter_energy.call_count == 1  # Still cached

    @pytest.mark.asyncio
    async def test_refresh_handles_errors_gracefully(
        self,
        mock_client: LuxpowerClient,
        sample_runtime: InverterRuntime,
        sample_energy: EnergyInfo,
        sample_battery_info: BatteryInfo,
    ) -> None:
        """Test that errors don't clear cached data."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Mock API responses - success first, then error
        mock_client.api.devices.get_inverter_runtime = AsyncMock(
            side_effect=[sample_runtime, Exception("API Error")]
        )
        mock_client.api.devices.get_inverter_energy = AsyncMock(return_value=sample_energy)
        mock_client.api.devices.get_battery_info = AsyncMock(return_value=sample_battery_info)

        # First refresh - success
        await inverter.refresh()
        assert inverter._runtime == sample_runtime

        # Force refresh with error - should keep old data
        await inverter.refresh(force=True)
        assert inverter._runtime == sample_runtime  # Old data preserved
