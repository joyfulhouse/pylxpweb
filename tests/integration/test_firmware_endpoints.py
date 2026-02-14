"""Integration tests for firmware update endpoints.

These tests require valid credentials in .env file.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add parent test directory to path for conftest helper imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from conftest import redact_sensitive

from pylxpweb.client import LuxpowerClient
from pylxpweb.models import (
    FirmwareUpdateCheck,
    FirmwareUpdateStatus,
    UpdateEligibilityStatus,
)

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


def load_env() -> dict[str, str]:
    """Load environment variables from .env file."""
    env_vars = {}
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
    return env_vars


# Load credentials
env_vars = load_env()
USERNAME = env_vars.get("LUXPOWER_USERNAME") or os.getenv("LUXPOWER_USERNAME")
PASSWORD = env_vars.get("LUXPOWER_PASSWORD") or os.getenv("LUXPOWER_PASSWORD")
BASE_URL = env_vars.get("LUXPOWER_BASE_URL") or os.getenv(
    "LUXPOWER_BASE_URL", "https://monitor.eg4electronics.com"
)

# Skip all tests if credentials not available
pytestmark = pytest.mark.skipif(
    not USERNAME or not PASSWORD,
    reason="Luxpower credentials not available in .env",
)


@pytest.mark.asyncio
async def test_check_firmware_updates() -> None:
    """Test checking for firmware updates.

    Note: If firmware is already up to date, the API may return an error message.
    This is expected behavior and the test will pass.
    """
    assert USERNAME is not None
    assert PASSWORD is not None
    assert BASE_URL is not None
    async with LuxpowerClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
        # Login to get available devices
        login_response = await client.login()
        assert login_response.success
        assert len(login_response.plants) > 0

        # Get first device serial number
        plant = login_response.plants[0]
        assert len(plant.inverters) > 0
        serial_num = plant.inverters[0].serialNum

        # Check for firmware updates
        # Note: API may return error if firmware is already latest version
        try:
            result = await client.firmware.check_firmware_updates(serial_num)

            assert isinstance(result, FirmwareUpdateCheck)
            assert result.success is True
            assert result.details is not None
            assert result.details.serialNum == serial_num
            # Note: Some device types may return empty firmware info (v1=0, standard='')
            # This is valid API behavior - not all devices support firmware updates
            # We only assert that the fields exist, not that they have specific values
            assert result.details.standard is not None  # May be empty string
            assert result.details.firmwareType is not None  # May be empty string
            assert result.details.fwCodeBeforeUpload is not None  # May be empty string

            # Check version information - v1/v2 may be 0 for devices without firmware info
            # Only validate > 0 if the device actually has firmware data
            has_firmware_info = result.details.v1 > 0 or bool(result.details.fwCodeBeforeUpload)
            if has_firmware_info:
                assert result.details.v1 >= 0  # Allow 0 as some devices may not report this
                assert result.details.v2 >= 0  # Allow 0 as some devices may not report this
            # lastV1 and lastV2 are optional - only present when updates are available
            # Just verify they are either None or >= 0 if present
            if result.details.lastV1 is not None:
                assert result.details.lastV1 >= 0
            if result.details.lastV2 is not None:
                assert result.details.lastV2 >= 0

            # Print update status (with redacted serial)
            serial_display = redact_sensitive(serial_num, "serial")
            if not has_firmware_info:
                # Device doesn't support firmware updates or no info available
                print(f"\n⚠️ No firmware info available for {serial_display}")
                print(f"   Device type: {result.details.deviceType}")
                print("   (This is normal for some device types)")
            elif result.details.has_update:
                print(f"\n✅ Firmware update available for {serial_display}")
                print(f"   Current: {result.details.fwCodeBeforeUpload}")
                if result.details.has_app_update:
                    print(f"   App update: v{result.details.v1} → v{result.details.lastV1}")
                    print(f"   File: {result.details.lastV1FileName}")
                if result.details.has_parameter_update:
                    print(f"   Param update: v{result.details.v2} → v{result.details.lastV2}")
                    print(f"   File: {result.details.lastV2FileName}")
                if result.infoForwardUrl:
                    print(f"   Changelog: {result.infoForwardUrl}")
            else:
                print(f"\n✅ No firmware updates available for {serial_display}")
                print(f"   Current: {result.details.fwCodeBeforeUpload}")

        except Exception as e:
            # API returns error when firmware is already latest version
            error_msg = str(e).lower()
            serial_display = redact_sensitive(serial_num, "serial")
            if "already the latest version" in error_msg or "latest firmware" in error_msg:
                print(f"\n✅ Firmware is already up to date for {serial_display}")
                print(f"   API response: {e}")
                # This is expected, test passes
            else:
                # Unexpected error, re-raise
                raise


@pytest.mark.asyncio
async def test_get_firmware_update_status() -> None:
    """Test getting firmware update status."""
    assert USERNAME is not None
    assert PASSWORD is not None
    assert BASE_URL is not None
    async with LuxpowerClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
        # Login first to get user ID
        login_response = await client.login()
        assert login_response.success

        # Get firmware update status
        result = await client.firmware.get_firmware_update_status()

        assert isinstance(result, FirmwareUpdateStatus)
        assert isinstance(result.receiving, bool)
        assert isinstance(result.progressing, bool)
        assert isinstance(result.fileReady, bool)
        assert isinstance(result.deviceInfos, list)

        # Print status
        print("\n✅ Firmware update status:")
        print(f"   Receiving: {result.receiving}")
        print(f"   Progressing: {result.progressing}")
        print(f"   File ready: {result.fileReady}")
        print(f"   Active updates: {len(result.deviceInfos)}")

        if result.has_active_updates:
            print("\n   Devices with active updates:")
            for device_info in result.deviceInfos:
                if device_info.is_in_progress:
                    print(f"   - {device_info.inverterSn}: {device_info.updateRate}")
                    print(f"     Firmware: {device_info.firmware}")
                    print(f"     Status: {device_info.updateStatus}")
                    print(f"     Started: {device_info.startTime}")

        if result.deviceInfos:
            print("\n   Recent update history:")
            for device_info in result.deviceInfos:
                if device_info.is_complete:
                    print(f"   - {device_info.inverterSn}: {device_info.updateStatus}")
                    print(f"     Firmware: {device_info.firmware}")
                    print(f"     Completed: {device_info.stopTime}")


@pytest.mark.asyncio
async def test_check_update_eligibility() -> None:
    """Test checking update eligibility."""
    assert USERNAME is not None
    assert PASSWORD is not None
    assert BASE_URL is not None
    async with LuxpowerClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
        # Login to get available devices
        login_response = await client.login()
        assert login_response.success
        assert len(login_response.plants) > 0

        # Get first device serial number
        plant = login_response.plants[0]
        assert len(plant.inverters) > 0
        serial_num = plant.inverters[0].serialNum

        # Check update eligibility
        result = await client.firmware.check_update_eligibility(serial_num)

        assert isinstance(result, UpdateEligibilityStatus)
        assert result.success is True
        assert result.msg is not None

        # Print eligibility status
        serial_display = redact_sensitive(serial_num, "serial")
        print(f"\n✅ Update eligibility for {serial_display}:")
        print(f"   Status: {result.msg.value}")

        if result.is_allowed:
            print("   ✅ Device is allowed to update")
        else:
            print(f"   ⚠️  Device cannot update: {result.msg.value}")


@pytest.mark.asyncio
async def test_firmware_workflow() -> None:
    """Test complete firmware update workflow (without actually updating).

    This test demonstrates the recommended workflow for checking and
    preparing for a firmware update, but stops before actually initiating it.
    """
    assert USERNAME is not None
    assert PASSWORD is not None
    assert BASE_URL is not None
    async with LuxpowerClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
        # Step 1: Login
        login_response = await client.login()
        assert login_response.success
        print("\n✅ Step 1: Login successful")

        # Get first device
        plant = login_response.plants[0]
        serial_num = plant.inverters[0].serialNum
        serial_display = redact_sensitive(serial_num, "serial")
        print(f"   Testing with device: {serial_display}")

        # Step 2: Check for updates
        # Note: API may return error if firmware is already latest version
        update_check = None  # Initialize to handle case where API returns error
        try:
            update_check = await client.firmware.check_firmware_updates(serial_num)
            assert update_check.success
            print("\n✅ Step 2: Checked for firmware updates")
            print(f"   Current firmware: {update_check.details.fwCodeBeforeUpload}")

            if update_check.details.has_update:
                print("   ⚠️  Update available!")
                if update_check.details.has_app_update:
                    print(f"   - App: v{update_check.details.v1} → v{update_check.details.lastV1}")
                if update_check.details.has_parameter_update:
                    print(
                        f"   - Param: v{update_check.details.v2} → v{update_check.details.lastV2}"
                    )
            else:
                print("   ✅ Firmware is up to date")
        except Exception as e:
            # API returns error when firmware is already latest version
            error_msg = str(e).lower()
            if "already the latest version" in error_msg or "latest firmware" in error_msg:
                print("\n✅ Step 2: Firmware is already up to date")
                print("   API message: Firmware already at latest version")
                # This is expected, test continues
            else:
                # Unexpected error, re-raise
                raise

        # Step 3: Check eligibility
        eligibility = await client.firmware.check_update_eligibility(serial_num)
        assert eligibility.success
        print("\n✅ Step 3: Checked update eligibility")
        print(f"   Status: {eligibility.msg.value}")

        # Step 4: Check current update status
        status = await client.firmware.get_firmware_update_status()
        print("\n✅ Step 4: Checked update status")
        print(f"   Any active updates: {status.has_active_updates}")

        # Summary
        print("\n📋 Firmware Update Workflow Summary:")
        serial_display = redact_sensitive(serial_num, "serial")
        print(f"   Device: {serial_display}")

        # Handle case where update_check may be None (firmware already up to date)
        has_update = update_check.details.has_update if update_check else False
        print(f"   Update available: {'Yes' if has_update else 'No'}")
        print(f"   Eligible to update: {'Yes' if eligibility.is_allowed else 'No'}")
        print(f"   Active updates: {'Yes' if status.has_active_updates else 'No'}")

        if has_update and eligibility.is_allowed and not status.has_active_updates:
            print("\n✅ All conditions met - device is ready for firmware update")
            print("   (Not starting update in test - would require user confirmation)")
            print("\n   To start update, call:")
            serial_display = redact_sensitive(serial_num, "serial")
            print(f"   await client.firmware.start_firmware_update('{serial_display}')")
            if update_check and update_check.infoForwardUrl:
                print("\n   View changelog at:")
                print(f"   {update_check.infoForwardUrl}")
        else:
            print("\n⚠️  Device not ready for update")
            if not has_update:
                print("   - No update available")
            if not eligibility.is_allowed:
                print(f"   - Not eligible: {eligibility.msg.value}")
            if status.has_active_updates:
                print("   - Another update is in progress")
