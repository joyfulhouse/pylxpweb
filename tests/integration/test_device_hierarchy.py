"""Integration tests for device hierarchy with live API.

IMPORTANT: These tests interact with real devices. They are READ-ONLY and safe.
Control operation tests are in test_control_operations.py.

To run these tests:
1. Create a .env file in project root with credentials:
   LUXPOWER_USERNAME=your_username
   LUXPOWER_PASSWORD=your_password
   LUXPOWER_BASE_URL=https://monitor.eg4electronics.com

2. Run with pytest marker:
   pytest -m integration tests/integration/test_device_hierarchy.py
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load .env file before importing anything else
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Import after loading .env
sys.path.insert(0, str(Path(__file__).parent.parent))

from pylxpweb import LuxpowerClient  # noqa: E402
from pylxpweb.devices import Station  # noqa: E402

# Load credentials from environment
LUXPOWER_USERNAME = os.getenv("LUXPOWER_USERNAME")
LUXPOWER_PASSWORD = os.getenv("LUXPOWER_PASSWORD")
LUXPOWER_BASE_URL = os.getenv("LUXPOWER_BASE_URL", "https://monitor.eg4electronics.com")

# Skip all tests if credentials are not provided
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not LUXPOWER_USERNAME or not LUXPOWER_PASSWORD,
        reason="Integration tests require LUXPOWER_USERNAME and LUXPOWER_PASSWORD env vars",
    ),
]


@pytest.fixture
async def client() -> AsyncGenerator[LuxpowerClient, None]:
    """Create authenticated client for testing."""
    async with LuxpowerClient(
        username=LUXPOWER_USERNAME,
        password=LUXPOWER_PASSWORD,
        base_url=LUXPOWER_BASE_URL,
    ) as client:
        yield client


@pytest.mark.asyncio
class TestStationLoading:
    """Test Station loading from live API."""

    async def test_load_all_stations(self, client: LuxpowerClient) -> None:
        """Test loading all stations."""
        stations = await Station.load_all(client)

        # Should have at least one station
        assert len(stations) > 0
        assert all(isinstance(s, Station) for s in stations)

        # Each station should have required attributes
        for station in stations:
            assert station.id > 0
            assert station.name
            assert station._client is client

    async def test_load_single_station(self, client: LuxpowerClient) -> None:
        """Test loading a single station by ID."""
        # First get list of stations to find a valid ID
        stations = await Station.load_all(client)
        assert len(stations) > 0

        # Load first station by ID
        first_station = stations[0]
        loaded_station = await Station.load(client, first_station.id)

        assert loaded_station.id == first_station.id
        assert loaded_station.name == first_station.name


@pytest.mark.asyncio
class TestStationDeviceHierarchy:
    """Test complete device hierarchy loading."""

    async def test_station_has_devices(self, client: LuxpowerClient) -> None:
        """Test station loads devices (parallel groups and inverters)."""
        stations = await Station.load_all(client)
        assert len(stations) > 0

        station = stations[0]

        # Should have devices (at least one inverter)
        assert len(station.all_inverters) > 0

    async def test_parallel_groups(self, client: LuxpowerClient) -> None:
        """Test parallel group structure."""
        stations = await Station.load_all(client)
        station = stations[0]

        # If station has parallel groups, check structure
        if len(station.parallel_groups) > 0:
            for group in station.parallel_groups:
                assert group.name
                assert group._client is client
                assert len(group.inverters) > 0

                # Each group may have MID device
                if group.mid_device:
                    assert group.mid_device.serial_number
                    assert group.mid_device.model

    async def test_all_inverters_property(self, client: LuxpowerClient) -> None:
        """Test all_inverters aggregates both standalone and parallel group inverters."""
        stations = await Station.load_all(client)
        station = stations[0]

        all_inverters = station.all_inverters

        # Count inverters in parallel groups
        group_inverter_count = sum(len(g.inverters) for g in station.parallel_groups)

        # Total should match
        total_expected = group_inverter_count + len(station.standalone_inverters)
        assert len(all_inverters) == total_expected


@pytest.mark.asyncio
class TestInverterData:
    """Test inverter data refresh and properties."""

    async def test_inverter_refresh(self, client: LuxpowerClient) -> None:
        """Test refreshing inverter data."""
        stations = await Station.load_all(client)
        station = stations[0]
        inverters = station.all_inverters

        assert len(inverters) > 0
        inverter = inverters[0]

        # Refresh data
        await inverter.refresh()

        # Should have runtime data
        assert inverter.runtime is not None
        assert inverter.has_data

        # Should have energy data
        assert inverter.energy is not None

        # Check properties work
        assert inverter.power_output >= 0
        assert inverter.total_energy_today >= 0
        assert inverter.total_energy_lifetime >= 0

        # Battery SOC may be None if no battery
        if inverter.battery_soc is not None:
            assert 0 <= inverter.battery_soc <= 100

    async def test_inverter_entity_generation(self, client: LuxpowerClient) -> None:
        """Test inverter entity generation."""
        stations = await Station.load_all(client)
        station = stations[0]
        inverters = station.all_inverters

        assert len(inverters) > 0
        inverter = inverters[0]

        # Refresh to get data
        await inverter.refresh()

        # Generate entities
        entities = inverter.to_entities()

        # Should have multiple entities
        assert len(entities) > 0

        # Check entities have required fields
        for entity in entities:
            assert entity.unique_id
            assert entity.name
            assert entity.value is not None

    async def test_inverter_device_info(self, client: LuxpowerClient) -> None:
        """Test inverter device info generation."""
        stations = await Station.load_all(client)
        station = stations[0]
        inverters = station.all_inverters

        assert len(inverters) > 0
        inverter = inverters[0]

        # Refresh to get firmware version
        await inverter.refresh()

        # Generate device info
        device_info = inverter.to_device_info()

        assert device_info.name
        assert device_info.manufacturer == "EG4/Luxpower"
        assert device_info.model
        assert len(device_info.identifiers) > 0

        # Firmware version should be available after refresh
        if inverter.runtime:
            assert device_info.sw_version

    async def test_inverter_model_is_set_on_load(self, client: LuxpowerClient) -> None:
        """Test inverter model is properly set during Station.load() (Issue #18)."""
        stations = await Station.load_all(client)
        station = stations[0]
        inverters = station.all_inverters

        assert len(inverters) > 0

        for inverter in inverters:
            # Model should be set immediately after load (before refresh)
            assert inverter.model is not None
            assert inverter.model != ""
            assert inverter.model != "Unknown"

            # Model should be a human-readable name (not hex code)
            # Common models: "18KPV", "FlexBOSS21", "FlexBOSS 12K", etc.
            assert not inverter.model.startswith("0x"), (
                f"Model should be human-readable, got hex code: {inverter.model}"
            )

            # Model should remain the same after refresh
            model_before_refresh = inverter.model
            await inverter.refresh()
            assert inverter.model == model_before_refresh, "Model should not change after refresh"


@pytest.mark.asyncio
class TestBatteryData:
    """Test battery data loading and properties."""

    async def test_batteries_loaded_with_inverter(self, client: LuxpowerClient) -> None:
        """Test batteries are automatically loaded during inverter refresh."""
        stations = await Station.load_all(client)
        station = stations[0]

        # Refresh all data (loads batteries)
        await station.refresh_all_data()

        # Check if any inverter has batteries
        all_batteries = station.all_batteries

        if len(all_batteries) > 0:
            battery = all_batteries[0]

            # Check battery properties
            assert battery.voltage > 0
            assert battery.soc >= 0
            assert battery.soh >= 0
            assert battery.cycle_count >= 0

    async def test_battery_entity_generation(self, client: LuxpowerClient) -> None:
        """Test battery entity generation."""
        stations = await Station.load_all(client)
        station = stations[0]

        await station.refresh_all_data()

        all_batteries = station.all_batteries

        if len(all_batteries) > 0:
            battery = all_batteries[0]

            # Generate entities
            entities = battery.to_entities()

            # Should have multiple battery sensors
            assert len(entities) > 0

            # Check entity structure
            for entity in entities:
                assert entity.unique_id
                assert entity.name
                assert entity.value is not None


@pytest.mark.asyncio
class TestMIDDevice:
    """Test MID/GridBOSS device functionality."""

    async def test_mid_device_detection(self, client: LuxpowerClient) -> None:
        """Test MID device detection in parallel groups."""
        stations = await Station.load_all(client)

        # Look for a station with MID device
        mid_found = False
        for station in stations:
            for group in station.parallel_groups:
                if group.mid_device:
                    mid_found = True
                    mid = group.mid_device

                    # Refresh MID data
                    await mid.refresh()

                    if mid.has_data:
                        # Check MID properties
                        assert mid.grid_voltage >= 0
                        assert mid.grid_frequency > 0

                        # Generate entities
                        entities = mid.to_entities()
                        assert len(entities) > 0

                        break
            if mid_found:
                break

        # Note: Not all installations have MID devices, so this is informational
        if not mid_found:
            pytest.skip("No MID device found in this installation")


@pytest.mark.asyncio
class TestStationAggregation:
    """Test station-level aggregation methods."""

    async def test_get_total_production(self, client: LuxpowerClient) -> None:
        """Test station total production calculation."""
        stations = await Station.load_all(client)
        station = stations[0]

        # Refresh all data
        await station.refresh_all_data()

        # Get total production
        total = await station.get_total_production()

        # Should have production data
        assert "today_kwh" in total
        assert "lifetime_kwh" in total

        # Values should be non-negative
        assert total["today_kwh"] >= 0
        assert total["lifetime_kwh"] >= 0

    async def test_concurrent_refresh(self, client: LuxpowerClient) -> None:
        """Test concurrent refresh of all devices."""
        stations = await Station.load_all(client)
        station = stations[0]

        # This should refresh all devices concurrently
        await station.refresh_all_data()

        # Verify all inverters have data
        for inverter in station.all_inverters:
            assert inverter.has_data
            assert inverter.runtime is not None


@pytest.mark.asyncio
class TestDataScaling:
    """Test data scaling is correct (voltages, currents, etc.)."""

    async def test_inverter_voltage_scaling(self, client: LuxpowerClient) -> None:
        """Test inverter voltage values are properly scaled."""
        stations = await Station.load_all(client)
        station = stations[0]
        inverter = station.all_inverters[0]

        await inverter.refresh()

        if inverter.runtime and hasattr(inverter.runtime, "vac1"):
            # Voltages should be in reasonable ranges (not raw API values)
            # Grid voltage typically 100-300V
            vac1 = float(inverter.runtime.vac1) / 100.0  # Apply scaling
            assert 50 < vac1 < 400, f"Grid voltage {vac1}V seems incorrectly scaled"

    async def test_battery_voltage_scaling(self, client: LuxpowerClient) -> None:
        """Test battery voltage values are properly scaled."""
        stations = await Station.load_all(client)
        station = stations[0]

        await station.refresh_all_data()

        batteries = station.all_batteries
        if len(batteries) > 0:
            battery = batteries[0]

            # Battery voltage should be in reasonable range (e.g., 48V nominal)
            # Typically 40-60V for 48V systems
            assert 30 < battery.voltage < 80, f"Battery voltage {battery.voltage}V seems wrong"

            # Cell voltages should be in reasonable range (3.0-3.7V per cell)
            if battery.max_cell_voltage > 0:
                assert 2.5 < battery.max_cell_voltage < 4.0
            if battery.min_cell_voltage > 0:
                assert 2.5 < battery.min_cell_voltage < 4.0
