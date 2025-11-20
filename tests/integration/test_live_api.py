"""Integration tests for live API access.

 IMPORTANT: These tests interact with a real electrical system and should be run
with extreme caution. All write operations use a read-then-write pattern to ensure
we only set existing values, preventing unintended changes to the system.

To run these tests:
1. Create a .env file in the project root with credentials:
   LUXPOWER_USERNAME=your_username
   LUXPOWER_PASSWORD=your_password
   LUXPOWER_BASE_URL=https://monitor.eg4electronics.com

2. Run with pytest marker:
   pytest -m integration tests/integration/

 DO NOT run these tests without understanding what they do!
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

from conftest import redact_sensitive  # noqa: E402

from pylxpweb import LuxpowerClient  # noqa: E402

# Load credentials from environment (after .env is loaded)
LUXPOWER_USERNAME = os.getenv("LUXPOWER_USERNAME")
LUXPOWER_PASSWORD = os.getenv("LUXPOWER_PASSWORD")
LUXPOWER_BASE_URL = os.getenv("LUXPOWER_BASE_URL", "https://monitor.eg4electronics.com")

# Skip all tests if credentials are not provided
pytestmark = pytest.mark.skipif(
    not LUXPOWER_USERNAME or not LUXPOWER_PASSWORD,
    reason=(
        "Integration tests require LUXPOWER_USERNAME and LUXPOWER_PASSWORD environment variables"
    ),
)


@pytest.fixture
async def live_client() -> AsyncGenerator[LuxpowerClient, None]:
    """Create a client for live API testing."""
    client = LuxpowerClient(
        username=LUXPOWER_USERNAME,  # type: ignore
        password=LUXPOWER_PASSWORD,  # type: ignore
        base_url=LUXPOWER_BASE_URL,
    )
    yield client
    await client.close()


class TestLiveAuthentication:
    """Test authentication with live API."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_login(self, live_client: LuxpowerClient) -> None:
        """Test login with live API."""
        response = await live_client.login()
        assert response.success is True
        assert response.userId > 0
        assert len(response.plants) > 0
        print(f"Logged in as {response.username}, found {len(response.plants)} plant(s)")


class TestLivePlantDiscovery:
    """Test plant discovery with live API."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_plants(self, live_client: LuxpowerClient) -> None:
        """Test getting plants from live API."""
        async with live_client:
            plants = await live_client.plants.get_plants()
            assert plants.total > 0
            assert len(plants.rows) > 0

            for plant in plants.rows:
                plant_name_display = redact_sensitive(plant.name, "name")
                print(f"Plant: {plant_name_display} (ID: {plant.plantId})")


class TestLiveDeviceDiscovery:
    """Test device discovery with live API."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_devices(self, live_client: LuxpowerClient) -> None:
        """Test getting devices from live API."""
        async with live_client:
            # Get first plant
            plants = await live_client.plants.get_plants()
            plant_id = plants.rows[0].plantId

            # Get devices
            devices = await live_client.devices.get_devices(plant_id)
            assert devices.success is True
            assert len(devices.rows) > 0

            for device in devices.rows:
                serial_masked = f"{device.serialNum[:2]}****{device.serialNum[-2:]}"
                print(f"Device: {device.deviceTypeText4APP} (SN: {serial_masked})")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_parallel_groups(self, live_client: LuxpowerClient) -> None:
        """Test getting parallel groups from live API."""
        async with live_client:
            # Get first plant
            plants = await live_client.plants.get_plants()
            plant_id = plants.rows[0].plantId

            # Get parallel groups
            groups = await live_client.devices.get_parallel_group_details(plant_id)
            assert groups.success is True

            if len(groups.parallelGroups) > 0:
                for group in groups.parallelGroups:
                    print(f"Parallel Group: {group.parallelGroup}, {len(group.devices)} device(s)")


class TestLiveRuntimeData:
    """Test runtime data retrieval with live API."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_inverter_runtime(self, live_client: LuxpowerClient) -> None:
        """Test getting inverter runtime from live API."""
        async with live_client:
            # Get first plant
            plants = await live_client.plants.get_plants()
            plant_id = plants.rows[0].plantId

            # Get first device
            devices = await live_client.devices.get_devices(plant_id)
            device = devices.rows[0]

            # Get runtime data
            runtime = await live_client.devices.get_inverter_runtime(device.serialNum)
            assert runtime.success is True
            print(f"Runtime: SOC={runtime.soc}%, Power={runtime.ppv}W")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_inverter_energy(self, live_client: LuxpowerClient) -> None:
        """Test getting inverter energy from live API."""
        async with live_client:
            # Get first plant
            plants = await live_client.plants.get_plants()
            plant_id = plants.rows[0].plantId

            # Get first device
            devices = await live_client.devices.get_devices(plant_id)
            device = devices.rows[0]

            # Get energy data
            energy = await live_client.devices.get_inverter_energy(device.serialNum)
            assert energy.success is True
            print(f"Energy: Today={energy.todayYielding}Wh, Total={energy.totalYielding}Wh")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_battery_info(self, live_client: LuxpowerClient) -> None:
        """Test getting battery info from live API."""
        async with live_client:
            # Get first plant
            plants = await live_client.plants.get_plants()
            plant_id = plants.rows[0].plantId

            # Get first device with battery
            devices = await live_client.devices.get_devices(plant_id)
            for device in devices.rows:
                if device.withbatteryData:
                    battery = await live_client.devices.get_battery_info(device.serialNum)
                    assert battery.success is True
                    print(f"Battery: SOC={battery.soc}%, {len(battery.batteryArray)} module(s)")
                    break


class TestLiveDeviceControlSafe:
    """Test device control with live API using safe read-then-write pattern.

     CRITICAL SAFETY NOTICE:
    These tests read current device settings FIRST, then write the SAME values back.
    This ensures we don't change any settings while validating the API works correctly.
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_read_write_parameters_safe(self, live_client: LuxpowerClient) -> None:
        """Test reading and writing parameters safely (read-then-write pattern).

        This test:
        1. Reads the current parameter values
        2. Writes the SAME values back
        3. Verifies the write succeeded

        This ensures no actual changes are made to the device.
        """
        async with live_client:
            # Get first plant
            plants = await live_client.plants.get_plants()
            plant_id = plants.rows[0].plantId

            # Get first device
            devices = await live_client.devices.get_devices(plant_id)
            device = devices.rows[0]

            # STEP 1: Read current parameter values
            params = await live_client.control.read_parameters(
                device.serialNum, start_register=0, point_number=127
            )
            assert params.success is True

            # Store original values
            original_values = params.parameters.copy()

            # STEP 2: Pick a safe parameter to test (SOC limits are common)
            if "HOLD_SYSTEM_CHARGE_SOC_LIMIT" in original_values:
                param_name = "HOLD_SYSTEM_CHARGE_SOC_LIMIT"
                current_value = str(original_values[param_name])

                # STEP 3: Write the SAME value back
                print(f"Writing {param_name}={current_value} (same as current value)")
                result = await live_client.control.write_parameter(
                    device.serialNum, param_name, current_value
                )
                assert result.success is True
                print(f"Write successful: {result.message}")

                # STEP 4: Read again to verify it's still the same
                params_after = await live_client.control.read_parameters(
                    device.serialNum, start_register=0, point_number=127
                )
                assert params_after.parameters[param_name] == original_values[param_name]
                print(f"Verified: {param_name} remains {current_value}")
            else:
                pytest.skip("HOLD_SYSTEM_CHARGE_SOC_LIMIT parameter not available")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_quick_charge_status_safe(self, live_client: LuxpowerClient) -> None:
        """Test quick charge status (read-only, completely safe)."""
        async with live_client:
            # Get first plant
            plants = await live_client.plants.get_plants()
            plant_id = plants.rows[0].plantId

            # Get first device
            devices = await live_client.devices.get_devices(plant_id)
            device = devices.rows[0]

            # Get quick charge status (read-only)
            status = await live_client.control.get_quick_charge_status(device.serialNum)
            assert status.success is True
            print(f"Quick charge active: {status.hasUnclosedQuickChargeTask}")


class TestLiveCaching:
    """Test caching behavior with live API."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cache_behavior(self, live_client: LuxpowerClient) -> None:
        """Test that caching works correctly with live API."""
        async with live_client:
            # Get first plant
            plants = await live_client.plants.get_plants()
            plant_id = plants.rows[0].plantId

            # Get first device
            devices = await live_client.devices.get_devices(plant_id)
            device = devices.rows[0]

            # First call (should hit API)
            runtime1 = await live_client.devices.get_inverter_runtime(device.serialNum)

            # Second call (should use cache)
            runtime2 = await live_client.devices.get_inverter_runtime(device.serialNum)

            # Should have same server time (cached)
            assert runtime1.serverTime == runtime2.serverTime
            print("Cache working correctly")


# Add a warning when running integration tests
if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("   INTEGRATION TEST WARNING  ")
    print("=" * 80)
    print("\nYou are about to run integration tests against a LIVE electrical system.")
    print("\nWhile these tests are designed with safety in mind (read-then-write pattern),")
    print("you should understand what each test does before running it.")
    print("\nPress Ctrl+C to cancel, or Enter to continue...")
    print("=" * 80 + "\n")
    input()
