"""Firmware update endpoints for the Luxpower API.

This module provides firmware update functionality including:
- Checking for available updates
- Monitoring update status
- Checking update eligibility
- Starting firmware updates
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pylxpweb.endpoints.base import BaseEndpoint
from pylxpweb.exceptions import LuxpowerAPIError
from pylxpweb.models import (
    FirmwareUpdateCheck,
    FirmwareUpdateStatus,
    UpdateEligibilityStatus,
)

if TYPE_CHECKING:
    from pylxpweb.client import LuxpowerClient

_LOGGER = logging.getLogger(__name__)

# Messages that indicate firmware is already up to date (not an error)
FIRMWARE_UP_TO_DATE_MESSAGES = (
    "already the latest version",
    "firmware is already the latest",
    "already up to date",
)


class FirmwareEndpoints(BaseEndpoint):
    """Firmware update endpoints for checking and managing device firmware."""

    def __init__(self, client: LuxpowerClient) -> None:
        """Initialize firmware endpoints.

        Args:
            client: The parent LuxpowerClient instance
        """
        super().__init__(client)

    async def check_firmware_updates(self, serial_num: str) -> FirmwareUpdateCheck:
        """Check for available firmware updates for a device.

        This is a READ-ONLY operation that checks if firmware updates are available
        and returns information about the current and available firmware versions.

        When firmware is already up to date, the API returns success=false with a
        message like "The current machine firmware is already the latest version".
        This method handles that case gracefully by returning a FirmwareUpdateCheck
        with success=True and details indicating no update is available.

        Args:
            serial_num: Device serial number (10-digit string)

        Returns:
            FirmwareUpdateCheck object containing:
                - success: Boolean indicating the check completed successfully
                - details: Detailed firmware information including:
                    - Current firmware versions (v1, v2, v3)
                    - Latest available versions (lastV1, lastV2) - None if up to date
                    - Update compatibility flags
                    - Device type information
                - infoForwardUrl: URL to firmware changelog/release notes (optional)

        Raises:
            LuxpowerAuthError: If authentication fails
            LuxpowerAPIError: If API returns an actual error (not "up to date" message)
            LuxpowerConnectionError: If connection fails

        Example:
            update_info = await client.firmware.check_firmware_updates("1234567890")
            if update_info.details.has_update():
                print(f"Update available: {update_info.details.lastV1FileName}")
                print(f"Changelog: {update_info.infoForwardUrl}")
            else:
                print("Firmware is already up to date")
        """
        await self.client._ensure_authenticated()

        data = {"serialNum": serial_num}

        try:
            response = await self.client._request(
                "POST",
                "/WManage/web/maintain/standardUpdate/checkUpdates",
                data=data,
            )
            return FirmwareUpdateCheck.model_validate(response)

        except LuxpowerAPIError as err:
            # Check if this is an "already up to date" message (not a real error)
            error_msg = str(err).lower()
            if any(msg in error_msg for msg in FIRMWARE_UP_TO_DATE_MESSAGES):
                _LOGGER.debug(
                    "Firmware is already up to date for device %s",
                    serial_num,
                )
                # Return a FirmwareUpdateCheck indicating no update available
                # We create minimal details since we don't have full version info
                return FirmwareUpdateCheck.create_up_to_date(serial_num)

            # Re-raise if it's a different error
            raise

    async def get_firmware_update_status(self) -> FirmwareUpdateStatus:
        """Get firmware update status for all devices in user's account.

        This is a READ-ONLY operation that monitors active firmware updates.
        Use this to track update progress for devices that are currently updating.

        Returns:
            FirmwareUpdateStatus object containing:
                - receiving: Whether system is receiving firmware file
                - progressing: Whether any update is in progress
                - fileReady: Whether firmware file is ready
                - deviceInfos: List of devices with active or recent updates

        Raises:
            LuxpowerAuthError: If authentication fails
            LuxpowerAPIError: If API returns an error
            LuxpowerConnectionError: If connection fails

        Example:
            status = await client.firmware.get_firmware_update_status()
            if status.has_active_updates():
                for device in status.deviceInfos:
                    if device.is_in_progress():
                        print(f"{device.inverterSn}: {device.updateRate}")
        """
        await self.client._ensure_authenticated()

        from pylxpweb.exceptions import LuxpowerAuthError

        if not hasattr(self.client, "_user_id") or self.client._user_id is None:
            msg = "User ID not available. Please login first."
            raise LuxpowerAuthError(msg)

        data = {"userId": self.client._user_id}

        response = await self.client._request(
            "POST",
            "/WManage/web/maintain/remoteUpdate/info",
            data=data,
        )

        return FirmwareUpdateStatus.model_validate(response)

    async def check_update_eligibility(self, serial_num: str) -> UpdateEligibilityStatus:
        """Check if device is eligible for firmware update.

        This is a READ-ONLY operation that verifies if a device can be updated.
        Important: Despite the endpoint name, this works for ALL devices, not just
        12K parallel configurations.

        Args:
            serial_num: Device serial number (10-digit string)

        Returns:
            UpdateEligibilityStatus object containing:
                - success: Boolean indicating success
                - msg: Eligibility message ("allowToUpdate", "deviceUpdating", etc.)

        Raises:
            LuxpowerAuthError: If authentication fails
            LuxpowerAPIError: If API returns an error
            LuxpowerConnectionError: If connection fails

        Example:
            eligibility = await client.firmware.check_update_eligibility("1234567890")
            if eligibility.is_allowed():
                await client.firmware.start_firmware_update("1234567890")
            else:
                print(f"Cannot update: {eligibility.msg}")
        """
        await self.client._ensure_authenticated()

        from pylxpweb.exceptions import LuxpowerAuthError

        if not hasattr(self.client, "_user_id") or self.client._user_id is None:
            msg = "User ID not available. Please login first."
            raise LuxpowerAuthError(msg)

        data = {"userId": self.client._user_id, "serialNum": serial_num}

        response = await self.client._request(
            "POST",
            "/WManage/web/maintain/standardUpdate/check12KParallelStatus",
            data=data,
        )

        return UpdateEligibilityStatus.model_validate(response)

    async def start_firmware_update(self, serial_num: str, *, try_fast_mode: bool = False) -> bool:
        """Start firmware update for a device.

        ⚠️ CRITICAL WARNING - WRITE OPERATION
        This initiates an actual firmware update that:
        - Takes 20-40 minutes to complete
        - Makes device unavailable during update
        - Requires uninterrupted power and network
        - May brick device if interrupted

        Recommended workflow:
        1. Call check_firmware_updates() to verify update is available
        2. Call check_update_eligibility() to verify device is ready
        3. Get explicit user confirmation
        4. Call this method to start update
        5. Monitor progress with get_firmware_update_status()

        Args:
            serial_num: Device serial number (10-digit string)
            try_fast_mode: Attempt fast update mode (may reduce time by 20-30%)

        Returns:
            Boolean indicating if update was initiated successfully

        Raises:
            LuxpowerAuthError: If authentication fails
            LuxpowerAPIError: If update cannot be started (already updating,
                             no update available, parallel group updating)
            LuxpowerConnectionError: If connection fails

        Example:
            # Check for updates first
            update_info = await client.firmware.check_firmware_updates("1234567890")
            if not update_info.details.has_update():
                print("No update available")
                return

            # Check eligibility
            eligibility = await client.firmware.check_update_eligibility("1234567890")
            if not eligibility.is_allowed():
                print(f"Cannot update: {eligibility.msg}")
                return

            # Get user confirmation
            if confirm_with_user():
                success = await client.firmware.start_firmware_update("1234567890")
                if success:
                    print("Update started. Monitor with get_firmware_update_status()")
        """
        await self.client._ensure_authenticated()

        from pylxpweb.exceptions import LuxpowerAuthError

        if not hasattr(self.client, "_user_id") or self.client._user_id is None:
            msg = "User ID not available. Please login first."
            raise LuxpowerAuthError(msg)

        data = {
            "userId": self.client._user_id,
            "serialNum": serial_num,
            "tryFastMode": str(try_fast_mode).lower(),
        }

        response = await self.client._request(
            "POST",
            "/WManage/web/maintain/standardUpdate/run",
            data=data,
        )

        return bool(response.get("success", False))
