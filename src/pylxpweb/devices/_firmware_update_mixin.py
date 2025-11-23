"""Firmware update detection mixin for devices.

This module provides the FirmwareUpdateMixin class that can be mixed into
any device class (BaseInverter, MIDDevice, etc.) to add firmware update
detection capabilities with caching and Home Assistant compatibility.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient
    from pylxpweb.models import FirmwareUpdateInfo


class FirmwareUpdateMixin:
    """Mixin class providing firmware update detection for devices.

    This mixin adds:
    - Firmware update checking with 24-hour caching
    - Synchronous property access to cached update status
    - Methods to start updates and check eligibility
    - Full Home Assistant Update entity compatibility

    The mixin expects the following attributes on the implementing class:
    - _client: LuxpowerClient instance
    - serial_number: Device serial number (str)
    - model: Device model name (str)

    Example:
        ```python
        class MyDevice(FirmwareUpdateMixin, BaseDevice):
            def __init__(self, client, serial_number, model):
                super().__init__(client, serial_number, model)
                self._init_firmware_update_cache()

            # ... rest of device implementation
        ```
    """

    def _init_firmware_update_cache(self) -> None:
        """Initialize firmware update cache attributes.

        This method must be called in the device's __init__ after super().__init__().
        It initializes the cache attributes needed for firmware update detection.
        """
        self._firmware_update_info: FirmwareUpdateInfo | None = None
        self._firmware_update_cache_time: datetime | None = None
        self._firmware_update_cache_ttl = timedelta(hours=24)  # 24-hour TTL
        self._firmware_update_cache_lock = asyncio.Lock()

    @property
    def firmware_update_available(self) -> bool | None:
        """Check if firmware update is available (from cache).

        This property provides synchronous access to cached firmware update status.
        Returns None if firmware check has never been performed.

        To check for updates, call `check_firmware_updates()` first.

        Returns:
            True if update available, False if up to date, None if not checked yet.

        Example:
            >>> # First check for updates
            >>> update_info = await device.check_firmware_updates()
            >>> # Then access cached status
            >>> if device.firmware_update_available:
            ...     print(f"Update available: {update_info.release_summary}")
        """
        if self._firmware_update_info is None:
            return None
        return self._firmware_update_info.update_available

    @property
    def latest_firmware_version(self) -> str | None:
        """Get latest firmware version from cache.

        Returns:
            Latest firmware version string, or None if not checked yet.

        Example:
            >>> await device.check_firmware_updates()
            >>> print(f"Latest version: {device.latest_firmware_version}")
        """
        if self._firmware_update_info is None:
            return None
        return self._firmware_update_info.latest_version

    @property
    def firmware_update_title(self) -> str | None:
        """Get firmware update title from cache.

        Returns:
            Firmware update title, or None if not checked yet.

        Example:
            >>> await device.check_firmware_updates()
            >>> print(f"Title: {device.firmware_update_title}")
        """
        if self._firmware_update_info is None:
            return None
        return self._firmware_update_info.title

    @property
    def firmware_update_summary(self) -> str | None:
        """Get firmware update summary from cache.

        Returns:
            Firmware update release summary, or None if not checked yet.

        Example:
            >>> await device.check_firmware_updates()
            >>> if device.firmware_update_summary:
            ...     print(f"Summary: {device.firmware_update_summary}")
        """
        if self._firmware_update_info is None:
            return None
        return self._firmware_update_info.release_summary

    @property
    def firmware_update_url(self) -> str | None:
        """Get firmware update URL from cache.

        Returns:
            Firmware update release URL, or None if not checked yet.

        Example:
            >>> await device.check_firmware_updates()
            >>> if device.firmware_update_url:
            ...     print(f"Release notes: {device.firmware_update_url}")
        """
        if self._firmware_update_info is None:
            return None
        return self._firmware_update_info.release_url

    async def check_firmware_updates(self, force: bool = False) -> FirmwareUpdateInfo:
        """Check for available firmware updates (cached with 24-hour TTL).

        This method checks the API for firmware updates and caches the result
        for 24 hours. Subsequent calls within the cache period will return
        cached data unless force=True.

        The returned FirmwareUpdateInfo contains all fields needed for Home
        Assistant Update entities, including installed_version, latest_version,
        release_summary, release_url, and supported_features.

        Args:
            force: If True, bypass cache and force fresh check from API

        Returns:
            FirmwareUpdateInfo instance with HA-compatible update information.

        Raises:
            LuxpowerAPIError: If API check fails
            LuxpowerConnectionError: If network connection fails

        Example:
            >>> # Check for updates (cached for 24 hours)
            >>> update_info = await device.check_firmware_updates()
            >>> if update_info.update_available:
            ...     print(f"New version: {update_info.latest_version}")
            ...     print(f"Summary: {update_info.release_summary}")
            ...     print(f"Release notes: {update_info.release_url}")
            ...
            >>> # Access cached status synchronously
            >>> if device.firmware_update_available:
            ...     print("Update available!")
        """
        # Import here to avoid circular imports
        from pylxpweb.models import FirmwareUpdateInfo

        # Check cache
        if not force:
            async with self._firmware_update_cache_lock:
                if (
                    self._firmware_update_cache_time is not None
                    and (datetime.now() - self._firmware_update_cache_time)
                    < self._firmware_update_cache_ttl
                ):
                    assert self._firmware_update_info is not None
                    return self._firmware_update_info

        # Fetch from API
        client: LuxpowerClient = self._client  # type: ignore[attr-defined]
        serial: str = self.serial_number  # type: ignore[attr-defined]
        model: str = self.model  # type: ignore[attr-defined]

        check = await client.api.firmware.check_firmware_updates(serial)

        # Create HA-friendly update info
        title = f"{model} Firmware"
        update_info = FirmwareUpdateInfo.from_api_response(check, title=title)

        # Update cache
        async with self._firmware_update_cache_lock:
            self._firmware_update_info = update_info
            self._firmware_update_cache_time = datetime.now()

        return update_info

    async def start_firmware_update(self, try_fast_mode: bool = False) -> bool:
        """Start firmware update for this device.

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
            try_fast_mode: Attempt fast update mode (may reduce time by 20-30%)

        Returns:
            Boolean indicating if update was initiated successfully

        Raises:
            LuxpowerAuthError: If authentication fails
            LuxpowerAPIError: If update cannot be started (already updating,
                             no update available, parallel group updating)
            LuxpowerConnectionError: If connection fails

        Example:
            >>> # Check for updates first
            >>> update_info = await device.check_firmware_updates()
            >>> if not update_info.update_available:
            ...     print("No update available")
            ...     return
            ...
            >>> # Check eligibility
            >>> eligible = await device.check_update_eligibility()
            >>> if not eligible:
            ...     print("Device not eligible for update")
            ...     return
            ...
            >>> # Get user confirmation
            >>> if confirm_with_user():
            ...     success = await device.start_firmware_update()
            ...     if success:
            ...         print("Update started successfully")
        """
        client: LuxpowerClient = self._client  # type: ignore[attr-defined]
        serial: str = self.serial_number  # type: ignore[attr-defined]

        return await client.api.firmware.start_firmware_update(serial, try_fast_mode=try_fast_mode)

    async def check_update_eligibility(self) -> bool:
        """Check if this device is eligible for firmware update.

        This is a READ-ONLY operation that verifies if the device can be updated.

        Returns:
            True if device is eligible for update, False otherwise

        Raises:
            LuxpowerAuthError: If authentication fails
            LuxpowerAPIError: If API check fails
            LuxpowerConnectionError: If connection fails

        Example:
            >>> eligible = await device.check_update_eligibility()
            >>> if eligible:
            ...     await device.start_firmware_update()
            >>> else:
            ...     print("Device is not eligible for update (may be updating already)")
        """
        client: LuxpowerClient = self._client  # type: ignore[attr-defined]
        serial: str = self.serial_number  # type: ignore[attr-defined]

        eligibility = await client.api.firmware.check_update_eligibility(serial)
        return eligibility.is_allowed
