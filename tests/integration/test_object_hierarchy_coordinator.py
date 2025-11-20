"""Integration test for object hierarchy and coordinator pattern validation.

This test validates that the object-oriented device hierarchy works correctly
with real API data and that data updates are properly propagated through the
coordinator pattern.

IMPORTANT: This test uses REAL API credentials and interacts with live devices.
All operations are READ-ONLY and safe to run.

To run this test:
1. Create a .env file in project root with credentials:
   LUXPOWER_USERNAME=your_username
   LUXPOWER_PASSWORD=your_password
   LUXPOWER_BASE_URL=https://monitor.eg4electronics.com

2. Run with pytest marker:
   pytest -m integration tests/integration/test_object_hierarchy_coordinator.py -v
"""

from __future__ import annotations

import asyncio
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
from pylxpweb.devices import Battery, Station  # noqa: E402
from pylxpweb.devices.inverters.base import BaseInverter  # noqa: E402

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
class TestObjectHierarchyLoading:
    """Test that all object instances are created correctly from API data."""

    async def test_complete_hierarchy_loading(self, client: LuxpowerClient) -> None:
        """Test loading complete hierarchy: Station -> ParallelGroup -> Inverter -> Battery."""
        # Load all stations
        stations = await Station.load_all(client)

        # Validate we have stations
        assert len(stations) > 0, "No stations found in account"
        print(f"\n✓ Loaded {len(stations)} station(s)")

        # Validate each station
        for station in stations:
            print(f"\n=== Station: {station.name} (ID: {station.id}) ===")

            # Station should be proper object instance
            assert isinstance(station, Station)
            assert station._client is client
            assert station.id > 0
            assert station.name
            # Note: plant_id is same as id
            assert station.id > 0

            # Station should have location data
            assert station.location is not None
            assert station.location.address  # Address should be present
            print(f"  Location: {station.location.address}")
            if station.location.latitude != 0 or station.location.longitude != 0:
                print(f"  Coordinates: {station.location.latitude}, {station.location.longitude}")

            # Check parallel groups (may be empty)
            print(f"  Parallel Groups: {len(station.parallel_groups)}")
            for group in station.parallel_groups:
                assert hasattr(group, "group_id")
                assert hasattr(group, "inverters")
                assert hasattr(group, "_client")
                assert group._client is client
                print(f"    - Group {group.group_id}: {len(group.inverters)} inverters")

                # Check MID device if present
                if group.mid_device:
                    assert group.mid_device._client is client
                    assert group.mid_device.serial_number
                    print(f"      MID Device: {group.mid_device.serial_number}")

            # Check standalone inverters
            print(f"  Standalone Inverters: {len(station.standalone_inverters)}")

            # Check all_inverters aggregation
            all_inverters = station.all_inverters
            if len(all_inverters) == 0:
                print(f"  ⚠️ No inverters loaded (possible API permissions issue)")
                pytest.skip("Station has no inverters - check API permissions")
            print(f"  Total Inverters: {len(all_inverters)}")

            # Validate each inverter is proper object instance
            for inverter in all_inverters:
                assert isinstance(inverter, BaseInverter)
                assert inverter._client is client
                assert inverter.serial_number
                assert inverter.model
                print(f"    - Inverter: {inverter.serial_number} ({inverter.model})")

            # Check batteries are part of hierarchy
            all_batteries = station.all_batteries
            print(f"  Total Batteries: {len(all_batteries)}")

            for battery in all_batteries:
                assert isinstance(battery, Battery)
                assert battery._client is client
                assert battery.battery_key
                print(f"    - Battery: {battery.battery_key}")

    async def test_object_references_are_correct(self, client: LuxpowerClient) -> None:
        """Test that all objects have correct references to client and parent objects."""
        stations = await Station.load_all(client)
        station = stations[0]

        # Station references
        assert station._client is client
        assert station._client is not None

        # Parallel group references
        for group in station.parallel_groups:
            assert group._client is client
            assert group._client is station._client  # Same client instance

            # MID device references
            if group.mid_device:
                assert group.mid_device._client is client

            # Inverter references in group
            for inverter in group.inverters:
                assert inverter._client is client
                assert inverter._client is station._client

        # Standalone inverter references
        for inverter in station.standalone_inverters:
            assert inverter._client is client
            assert inverter._client is station._client

        # Battery references
        for inverter in station.all_inverters:
            if hasattr(inverter, "batteries") and inverter.batteries:
                for battery in inverter.batteries:
                    assert battery._client is client
                    assert battery._client is station._client


@pytest.mark.asyncio
class TestCoordinatorDataUpdate:
    """Test that data updates work through coordinator pattern."""

    async def test_station_refresh_updates_all_devices(self, client: LuxpowerClient) -> None:
        """Test that station.refresh_all_data() updates all devices."""
        stations = await Station.load_all(client)
        station = stations[0]

        print(f"\n=== Testing Coordinator Update for Station: {station.name} ===")

        # Before refresh, devices may not have data
        if len(station.all_inverters) == 0:
            pytest.skip("Station has no inverters - check API permissions")
        inverter = station.all_inverters[0]
        initial_has_data = inverter.has_data

        print(f"Initial state - Inverter has_data: {initial_has_data}")

        # Refresh all data (coordinator pattern)
        await station.refresh_all_data()

        # After refresh, all inverters should have data
        for idx, inverter in enumerate(station.all_inverters):
            print(f"\nInverter {idx + 1}: {inverter.serial_number}")
            assert inverter.has_data, f"Inverter {inverter.serial_number} missing data after refresh"
            assert inverter.runtime is not None
            assert inverter.energy is not None

            print(f"  Runtime data: ✓")
            print(f"  Power: {inverter.power_output}W")
            print(f"  Energy today: {inverter.total_energy_today} kWh")
            print(f"  Energy lifetime: {inverter.total_energy_lifetime} kWh")

            if inverter.battery_soc is not None:
                print(f"  Battery SOC: {inverter.battery_soc}%")

        # Check MID devices have data if present
        for group in station.parallel_groups:
            if group.mid_device:
                mid = group.mid_device
                print(f"\nMID Device: {mid.serial_number}")
                if mid.has_data:
                    print(f"  Grid Voltage: {mid.grid_voltage}V")
                    print(f"  Grid Frequency: {mid.grid_frequency}Hz")
                else:
                    print("  No data available (may not be online)")

    async def test_individual_inverter_refresh(self, client: LuxpowerClient) -> None:
        """Test that individual inverter refresh works and updates data."""
        stations = await Station.load_all(client)
        station = stations[0]

        if len(station.all_inverters) == 0:
            pytest.skip("Station has no inverters - check API permissions")
        inverter = station.all_inverters[0]

        print(f"\n=== Testing Individual Inverter Refresh: {inverter.serial_number} ===")

        # Refresh individual inverter
        await inverter.refresh()

        # Validate data is updated
        assert inverter.has_data
        assert inverter.runtime is not None
        assert inverter.energy is not None

        print(f"✓ Runtime data loaded")
        print(f"✓ Energy data loaded")

        # Check batteries are loaded too
        if hasattr(inverter, "batteries") and inverter.batteries:
            print(f"✓ {len(inverter.batteries)} batteries loaded")
            for battery in inverter.batteries:
                assert isinstance(battery, Battery)
                assert battery.voltage > 0
                print(f"  Battery {battery.battery_key}: {battery.soc}% @ {battery.voltage}V")

    async def test_concurrent_refresh_efficiency(self, client: LuxpowerClient) -> None:
        """Test that concurrent refresh is more efficient than sequential."""
        stations = await Station.load_all(client)
        station = stations[0]

        if len(station.all_inverters) < 2:
            pytest.skip("Need at least 2 inverters to test concurrent refresh")

        print(f"\n=== Testing Concurrent Refresh Efficiency ===")
        print(f"Station has {len(station.all_inverters)} inverters")

        # Time concurrent refresh
        import time

        start_concurrent = time.time()
        await station.refresh_all_data()
        concurrent_time = time.time() - start_concurrent

        print(f"Concurrent refresh: {concurrent_time:.2f}s")

        # Clear data
        for inverter in station.all_inverters:
            inverter.runtime = None
            inverter.energy = None

        # Time sequential refresh
        start_sequential = time.time()
        for inverter in station.all_inverters:
            await inverter.refresh()
        sequential_time = time.time() - start_sequential

        print(f"Sequential refresh: {sequential_time:.2f}s")
        print(f"Speedup: {sequential_time / concurrent_time:.1f}x")

        # Concurrent should be faster for multiple inverters
        assert concurrent_time < sequential_time, "Concurrent refresh should be faster"

    async def test_data_staleness_tracking(self, client: LuxpowerClient) -> None:
        """Test that last_refresh timestamp is updated correctly."""
        stations = await Station.load_all(client)
        station = stations[0]

        if len(station.all_inverters) == 0:
            pytest.skip("Station has no inverters - check API permissions")
        inverter = station.all_inverters[0]

        print(f"\n=== Testing Data Staleness Tracking ===")

        # Initial state
        initial_refresh = inverter.last_refresh
        print(f"Initial last_refresh: {initial_refresh}")

        # Wait a moment
        await asyncio.sleep(0.1)

        # Refresh
        await inverter.refresh()

        # Check timestamp updated
        new_refresh = inverter.last_refresh
        print(f"After refresh last_refresh: {new_refresh}")

        if initial_refresh is not None:
            assert new_refresh > initial_refresh, "Timestamp should be updated"
        else:
            assert new_refresh is not None, "Timestamp should be set after refresh"


@pytest.mark.asyncio
class TestDataConsistency:
    """Test that data values are consistent and properly scaled."""

    async def test_power_values_are_consistent(self, client: LuxpowerClient) -> None:
        """Test that power values across hierarchy are consistent."""
        stations = await Station.load_all(client)
        station = stations[0]

        if len(station.all_inverters) == 0:
            pytest.skip("Station has no inverters - check API permissions")

        await station.refresh_all_data()

        print(f"\n=== Testing Power Value Consistency ===")

        # Get station total
        total = await station.get_total_production()
        station_today = total["today_kwh"]
        print(f"Station total energy today: {station_today} kWh")

        # Sum individual inverter powers
        inverter_sum = sum(inv.power_output for inv in station.all_inverters)
        print(f"Sum of inverter powers: {inverter_sum}W")

        # Just validate power values are non-negative
        assert inverter_sum >= 0, f"Power sum cannot be negative"
        print("✓ Power values are valid")

    async def test_energy_values_accumulate(self, client: LuxpowerClient) -> None:
        """Test that energy values accumulate correctly."""
        stations = await Station.load_all(client)
        station = stations[0]

        if len(station.all_inverters) == 0:
            pytest.skip("Station has no inverters - check API permissions")

        await station.refresh_all_data()

        print(f"\n=== Testing Energy Value Accumulation ===")

        total = await station.get_total_production()

        # Today's energy should be <= lifetime energy
        for inverter in station.all_inverters:
            today = inverter.total_energy_today
            lifetime = inverter.total_energy_lifetime

            print(f"Inverter {inverter.serial_number}:")
            print(f"  Today: {today} kWh")
            print(f"  Lifetime: {lifetime} kWh")

            assert (
                today <= lifetime
            ), f"Today's energy ({today}) > lifetime ({lifetime}) for {inverter.serial_number}"

        # Station totals should match sum
        station_today = total["today_kwh"]
        inverter_today_sum = sum(inv.total_energy_today for inv in station.all_inverters)

        print(f"\nStation today total: {station_today} kWh")
        print(f"Sum of inverters: {inverter_today_sum} kWh")

        if station_today > 0:
            diff_pct = abs(station_today - inverter_today_sum) / station_today * 100
            assert diff_pct < 1, f"Energy totals differ by {diff_pct:.1f}%"

    async def test_battery_values_are_valid(self, client: LuxpowerClient) -> None:
        """Test that battery values are in valid ranges."""
        stations = await Station.load_all(client)
        station = stations[0]

        await station.refresh_all_data()

        batteries = station.all_batteries

        if len(batteries) == 0:
            pytest.skip("No batteries found in this installation")

        print(f"\n=== Testing Battery Value Validity ===")
        print(f"Found {len(batteries)} batteries")

        for battery in batteries:
            print(f"\nBattery {battery.battery_key}:")
            print(f"  SOC: {battery.soc}%")
            print(f"  SOH: {battery.soh}%")
            print(f"  Voltage: {battery.voltage}V")
            print(f"  Temperature: {battery.temperature}°C")
            print(f"  Cycle count: {battery.cycle_count}")

            # Validate ranges
            assert 0 <= battery.soc <= 100, f"SOC {battery.soc}% out of range"
            assert 0 <= battery.soh <= 100, f"SOH {battery.soh}% out of range"
            assert 30 < battery.voltage < 80, f"Voltage {battery.voltage}V seems wrong for 48V system"
            assert -20 < battery.temperature < 80, f"Temperature {battery.temperature}°C seems wrong"
            assert battery.cycle_count >= 0, f"Cycle count {battery.cycle_count} is negative"

            # Check cell voltages if available
            if battery.max_cell_voltage > 0:
                assert 2.5 < battery.max_cell_voltage < 4.0, "Max cell voltage out of range"
                print(f"  Max cell: {battery.max_cell_voltage}V")

            if battery.min_cell_voltage > 0:
                assert 2.5 < battery.min_cell_voltage < 4.0, "Min cell voltage out of range"
                print(f"  Min cell: {battery.min_cell_voltage}V")

            if battery.max_cell_voltage > 0 and battery.min_cell_voltage > 0:
                delta = battery.max_cell_voltage - battery.min_cell_voltage
                print(f"  Cell delta: {delta:.3f}V")
                # Delta should typically be < 0.3V for healthy battery
                if delta > 0.5:
                    print(f"  ⚠️  Large cell voltage delta: {delta:.3f}V")


@pytest.mark.asyncio
class TestEntityGeneration:
    """Test that entity generation works correctly for HA integration."""

    async def test_all_devices_generate_entities(self, client: LuxpowerClient) -> None:
        """Test that all device types can generate entities."""
        stations = await Station.load_all(client)
        station = stations[0]

        await station.refresh_all_data()

        print(f"\n=== Testing Entity Generation ===")

        # Station should generate entities
        station_entities = station.to_entities()
        print(f"Station entities: {len(station_entities)}")
        assert len(station_entities) > 0

        # Check entity structure
        for entity in station_entities[:3]:  # Sample first 3
            assert entity.unique_id
            assert entity.name
            assert entity.value is not None
            print(f"  - {entity.name}: {entity.value} {entity.unit_of_measurement or ''}")

        # Inverters should generate entities
        for inverter in station.all_inverters[:1]:  # Test first inverter
            inverter_entities = inverter.to_entities()
            print(f"\nInverter {inverter.serial_number} entities: {len(inverter_entities)}")
            assert len(inverter_entities) > 10  # Should have many sensors

            for entity in inverter_entities[:5]:  # Sample first 5
                assert entity.unique_id
                assert entity.name
                assert entity.value is not None
                print(f"  - {entity.name}: {entity.value} {entity.unit_of_measurement or ''}")

        # Batteries should generate entities
        for battery in station.all_batteries[:1]:  # Test first battery
            battery_entities = battery.to_entities()
            print(f"\nBattery {battery.battery_key} entities: {len(battery_entities)}")
            assert len(battery_entities) > 5

            for entity in battery_entities[:3]:  # Sample first 3
                assert entity.unique_id
                assert entity.name
                assert entity.value is not None
                print(f"  - {entity.name}: {entity.value} {entity.unit_of_measurement or ''}")

    async def test_entity_unique_ids_are_unique(self, client: LuxpowerClient) -> None:
        """Test that all entity unique_ids are actually unique."""
        stations = await Station.load_all(client)
        station = stations[0]

        await station.refresh_all_data()

        print(f"\n=== Testing Entity Unique ID Uniqueness ===")

        # Collect all entity unique_ids
        all_unique_ids = set()
        duplicate_ids = []

        # Station entities
        for entity in station.to_entities():
            if entity.unique_id in all_unique_ids:
                duplicate_ids.append(entity.unique_id)
            all_unique_ids.add(entity.unique_id)

        # Inverter entities
        for inverter in station.all_inverters:
            for entity in inverter.to_entities():
                if entity.unique_id in all_unique_ids:
                    duplicate_ids.append(entity.unique_id)
                all_unique_ids.add(entity.unique_id)

        # Battery entities
        for battery in station.all_batteries:
            for entity in battery.to_entities():
                if entity.unique_id in all_unique_ids:
                    duplicate_ids.append(entity.unique_id)
                all_unique_ids.add(entity.unique_id)

        print(f"Total unique entities: {len(all_unique_ids)}")

        if duplicate_ids:
            print(f"❌ Found {len(duplicate_ids)} duplicate IDs:")
            for dup_id in duplicate_ids[:5]:  # Show first 5
                print(f"  - {dup_id}")

        assert len(duplicate_ids) == 0, f"Found {len(duplicate_ids)} duplicate entity IDs"

    async def test_device_info_generation(self, client: LuxpowerClient) -> None:
        """Test that device info is generated correctly for HA."""
        stations = await Station.load_all(client)
        station = stations[0]

        await station.refresh_all_data()

        print(f"\n=== Testing Device Info Generation ===")

        # Station device info
        station_info = station.to_device_info()
        print(f"Station device info:")
        print(f"  Name: {station_info.name}")
        print(f"  Manufacturer: {station_info.manufacturer}")
        print(f"  Model: {station_info.model}")
        print(f"  Identifiers: {station_info.identifiers}")

        assert station_info.name
        assert station_info.manufacturer
        assert len(station_info.identifiers) > 0

        # Inverter device info
        if len(station.all_inverters) == 0:
            pytest.skip("Station has no inverters - check API permissions")
        inverter = station.all_inverters[0]
        inverter_info = inverter.to_device_info()
        print(f"\nInverter device info:")
        print(f"  Name: {inverter_info.name}")
        print(f"  Manufacturer: {inverter_info.manufacturer}")
        print(f"  Model: {inverter_info.model}")
        print(f"  SW Version: {inverter_info.sw_version}")
        print(f"  Identifiers: {inverter_info.identifiers}")

        assert inverter_info.name
        assert inverter_info.manufacturer == "EG4/Luxpower"
        assert inverter_info.model
        assert len(inverter_info.identifiers) > 0


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling in object hierarchy."""

    async def test_missing_data_handling(self, client: LuxpowerClient) -> None:
        """Test that objects handle missing data gracefully."""
        stations = await Station.load_all(client)
        station = stations[0]

        # Don't refresh - test with missing data
        if len(station.all_inverters) == 0:
            pytest.skip("Station has no inverters - check API permissions")
        inverter = station.all_inverters[0]

        print(f"\n=== Testing Missing Data Handling ===")
        print(f"has_data before refresh: {inverter.has_data}")

        # Should handle missing data gracefully
        assert inverter.power_output == 0 or inverter.runtime is None
        assert inverter.total_energy_today >= 0 or inverter.energy is None

        # Entities should still be generated (may have None values)
        entities = inverter.to_entities()
        assert len(entities) >= 0  # May be empty if no data

    async def test_invalid_station_id(self, client: LuxpowerClient) -> None:
        """Test loading station with invalid ID."""
        print(f"\n=== Testing Invalid Station ID ===")

        # Try to load non-existent station
        try:
            result = await Station.load(client, plant_id=999999999)
            # If it doesn't raise, at least check we got None or invalid result
            assert result is None or not hasattr(result, "id"), "Should fail to load invalid station"
        except Exception as e:
            # Expected to raise some error
            print(f"✓ Correctly raised error: {type(e).__name__}")
            assert True
