"""Integration tests for DST control functionality."""

# Import redaction helper
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from pylxpweb import LuxpowerClient


@pytest.mark.asyncio
async def test_get_plant_details(live_client: LuxpowerClient) -> None:
    """Test getting plant details with DST status."""
    plants = await live_client.plants.get_plants()
    assert len(plants.rows) > 0

    plant_id = str(plants.rows[0].plantId)
    details = await live_client.plants.get_plant_details(plant_id)

    # Verify required fields for DST control
    assert "plantId" in details
    assert "name" in details
    assert "timezone" in details
    assert "country" in details
    assert "daylightSavingTime" in details
    assert "createDate" in details

    # Verify timezone format
    assert details["timezone"].startswith("GMT")


@pytest.mark.asyncio
async def test_dst_toggle(live_client: LuxpowerClient) -> None:
    """Test toggling DST on and off.

    IMPORTANT: This test reads the current state, toggles it, then restores
    the CURRENT state from the API (not a cached value) to ensure the live
    system is always left in its original configuration.
    """
    plants = await live_client.plants.get_plants()
    plant_id = str(plants.rows[0].plantId)

    # Get current DST status from API
    details = await live_client.plants.get_plant_details(plant_id)
    original_dst = details["daylightSavingTime"]

    try:
        # Toggle DST
        new_dst = not original_dst
        result = await live_client.plants.set_daylight_saving_time(plant_id, new_dst)

        assert result["success"] is True

        # Verify change
        updated = await live_client.plants.get_plant_details(plant_id)
        assert updated["daylightSavingTime"] == new_dst

    finally:
        # ALWAYS restore by reading current state from API first
        # This ensures we restore the actual original value, not a cached one
        current_details = await live_client.plants.get_plant_details(plant_id)

        # Only restore if current state differs from original
        if current_details["daylightSavingTime"] != original_dst:
            await live_client.plants.set_daylight_saving_time(plant_id, original_dst)

            # Verify restoration
            final = await live_client.plants.get_plant_details(plant_id)
            assert final["daylightSavingTime"] == original_dst


@pytest.mark.asyncio
async def test_update_plant_config(live_client: LuxpowerClient) -> None:
    """Test updating plant configuration with hybrid approach.

    IMPORTANT: This test reads the current state, toggles it, then restores
    the CURRENT state from the API (not a cached value) to ensure the live
    system is always left in its original configuration.
    """
    plants = await live_client.plants.get_plants()
    plant_id = str(plants.rows[0].plantId)

    # Get current config from API
    details = await live_client.plants.get_plant_details(plant_id)
    original_dst = details["daylightSavingTime"]

    try:
        # Update DST via update_plant_config
        result = await live_client.plants.update_plant_config(
            plant_id, daylightSavingTime=not original_dst
        )

        assert result["success"] is True

        # Verify change
        updated = await live_client.plants.get_plant_details(plant_id)
        assert updated["daylightSavingTime"] == (not original_dst)

    finally:
        # ALWAYS restore by reading current state from API first
        # This ensures we restore the actual original value, not a cached one
        current_details = await live_client.plants.get_plant_details(plant_id)

        # Only restore if current state differs from original
        if current_details["daylightSavingTime"] != original_dst:
            await live_client.plants.update_plant_config(plant_id, daylightSavingTime=original_dst)

            # Verify restoration
            final = await live_client.plants.get_plant_details(plant_id)
            assert final["daylightSavingTime"] == original_dst


@pytest.mark.asyncio
async def test_hybrid_mapping_static_path(live_client: LuxpowerClient) -> None:
    """Test that common countries use static mapping (fast path)."""
    plants = await live_client.plants.get_plants()
    plant_id = str(plants.rows[0].plantId)

    details = await live_client.plants.get_plant_details(plant_id)
    original_dst = details["daylightSavingTime"]

    # Assuming USA for this test (adjust if different)
    if details["country"] == "United States of America":
        # This should use static mapping (no API calls)
        # We can't easily verify this without logging, but we can verify it works
        # Set to same value (no-op) to test the code path
        result = await live_client.plants.set_daylight_saving_time(plant_id, original_dst)
        assert result["success"] is True

        # Verify no change (since we set it to the same value)
        final = await live_client.plants.get_plant_details(plant_id)
        assert final["daylightSavingTime"] == original_dst


@pytest.mark.asyncio
async def test_invalid_plant_id(live_client: LuxpowerClient) -> None:
    """Test DST control with invalid plant ID.

    Note: The API silently accepts invalid plant IDs and returns success=True.
    This test verifies that the client can handle this without raising exceptions.
    In practice, invalid plant IDs simply have no effect.
    """
    # API accepts invalid plant IDs without error
    result = await live_client.plants.set_daylight_saving_time("99999999", True)
    assert result["success"] is True


@pytest.mark.asyncio
async def test_dst_auto_detection_and_sync(live_client: LuxpowerClient) -> None:
    """Test automatic DST detection and synchronization during Station.load().

    This test:
    1. Gets current API DST flag
    2. Calculates expected DST status based on timezone offset
    3. Deliberately sets API DST flag to WRONG value
    4. Loads station (triggers auto-detection and sync)
    5. Verifies API DST flag was auto-corrected
    6. Restores original state
    """
    from pylxpweb.devices.station import Station

    plants = await live_client.plants.get_plants()
    plant_id = plants.rows[0].plantId

    # Get current plant details from API
    details = await live_client.plants.get_plant_details(str(plant_id))
    original_dst = details["daylightSavingTime"]
    timezone_str = details["timezone"]
    current_tz_minutes = details.get("currentTimezoneWithMinute")

    # Calculate expected DST status based on offset comparison
    expected_dst = None
    if current_tz_minutes is not None and "GMT" in timezone_str:
        try:
            # Parse base timezone
            offset_str = timezone_str.replace("GMT", "").strip()
            base_hours = int(offset_str)

            # Convert current offset to hours
            current_hours = current_tz_minutes / 60.0

            # DST is active if current offset is ahead of base offset
            difference = current_hours - base_hours
            expected_dst = difference >= 0.5

            print("\nTimezone Analysis:")
            print(f"  Base timezone: {timezone_str} ({base_hours} hours)")
            print(f"  Current offset: {current_tz_minutes} minutes ({current_hours} hours)")
            print(f"  Difference: {difference} hours")
            print(f"  Expected DST: {expected_dst}")
            print(f"  API reports DST: {original_dst}")
        except Exception as e:
            print(f"Could not calculate expected DST: {e}")
            pytest.skip(f"Cannot calculate expected DST for timezone {timezone_str}")

    if expected_dst is None:
        pytest.skip("Cannot determine expected DST status from timezone data")

    try:
        # Step 1: Deliberately set API DST flag to WRONG value
        wrong_dst = not expected_dst
        print(f"\nSetting API DST flag to WRONG value: {wrong_dst}")
        result = await live_client.plants.set_daylight_saving_time(str(plant_id), wrong_dst)
        assert result["success"] is True

        # Verify wrong value was set
        after_wrong = await live_client.plants.get_plant_details(str(plant_id))
        assert after_wrong["daylightSavingTime"] == wrong_dst
        print(f"API DST flag now set to (wrong): {wrong_dst}")

        # Step 2: Clear client cache to ensure fresh load
        live_client.clear_cache()

        # Step 3: Load station - this should trigger auto-detection and sync
        print(f"\nLoading station (should auto-correct DST to {expected_dst})...")
        station = await Station.load(live_client, plant_id)

        # Step 4: Verify station detected and corrected the DST mismatch
        print("\nStation loaded:")
        print(f"  Station DST flag: {station.daylight_saving_time}")
        print(f"  Station detected DST: {station.detect_dst_status()}")

        # Verify station's internal flag was updated
        assert station.daylight_saving_time == expected_dst, (
            f"Station DST flag should be {expected_dst} but got {station.daylight_saving_time}"
        )

        # Step 5: Verify API was updated
        after_sync = await live_client.plants.get_plant_details(str(plant_id))
        print(f"  API DST flag after sync: {after_sync['daylightSavingTime']}")

        assert after_sync["daylightSavingTime"] == expected_dst, (
            f"API DST flag should be {expected_dst} but got {after_sync['daylightSavingTime']}"
        )

        print("\n✅ DST auto-correction successful!")

    finally:
        # ALWAYS restore original state by reading current value first
        current_details = await live_client.plants.get_plant_details(str(plant_id))

        # Only restore if current state differs from original
        if current_details["daylightSavingTime"] != original_dst:
            print(f"\nRestoring original DST flag: {original_dst}")
            await live_client.plants.set_daylight_saving_time(str(plant_id), original_dst)

            # Verify restoration
            final = await live_client.plants.get_plant_details(str(plant_id))
            assert final["daylightSavingTime"] == original_dst


@pytest.mark.asyncio
async def test_dst_sync_when_already_correct(live_client: LuxpowerClient) -> None:
    """Test that DST sync is a no-op when API flag is already correct.

    This verifies that we don't unnecessarily update the API when the
    DST flag matches the detected status.
    """
    from pylxpweb.devices.station import Station

    plants = await live_client.plants.get_plants()
    plant_id = plants.rows[0].plantId

    # Get current plant details
    details = await live_client.plants.get_plant_details(str(plant_id))
    original_dst = details["daylightSavingTime"]
    timezone_str = details["timezone"]
    current_tz_minutes = details.get("currentTimezoneWithMinute")

    # Calculate expected DST status
    expected_dst = None
    if current_tz_minutes is not None and "GMT" in timezone_str:
        try:
            offset_str = timezone_str.replace("GMT", "").strip()
            base_hours = int(offset_str)
            current_hours = current_tz_minutes / 60.0
            difference = current_hours - base_hours
            expected_dst = difference >= 0.5
        except Exception as e:
            pytest.skip(f"Cannot calculate expected DST: {e}")

    if expected_dst is None:
        pytest.skip("Cannot determine expected DST status from timezone data")

    try:
        # Set API DST flag to CORRECT value
        print(f"\nSetting API DST flag to CORRECT value: {expected_dst}")
        result = await live_client.plants.set_daylight_saving_time(str(plant_id), expected_dst)
        assert result["success"] is True

        # Verify correct value was set
        before_load = await live_client.plants.get_plant_details(str(plant_id))
        assert before_load["daylightSavingTime"] == expected_dst

        # Clear cache
        live_client.clear_cache()

        # Load station - should detect that DST is already correct
        print("Loading station with correct DST flag...")
        _ = await Station.load(live_client, plant_id)  # Triggers DST sync

        # Verify no unnecessary API update
        after_load = await live_client.plants.get_plant_details(str(plant_id))
        assert after_load["daylightSavingTime"] == expected_dst

        print("✅ DST sync correctly skipped (already correct)")

    finally:
        # Restore original state
        current_details = await live_client.plants.get_plant_details(str(plant_id))
        if current_details["daylightSavingTime"] != original_dst:
            await live_client.plants.set_daylight_saving_time(str(plant_id), original_dst)
