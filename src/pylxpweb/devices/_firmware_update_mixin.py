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
    - Real-time progress tracking with adaptive caching
    - Synchronous property access to cached update status
    - Methods to start updates and check eligibility
    - Full Home Assistant Update entity compatibility

    Available properties (synchronous, cached):
    - firmware_update_available: bool | None - Update availability
    - firmware_update_in_progress: bool - Update currently in progress
    - firmware_update_percentage: int | None - Progress percentage (0-100)
    - latest_firmware_version: str | None - Latest version available
    - firmware_update_title: str | None - Update title
    - firmware_update_summary: str | None - Release summary
    - firmware_update_url: str | None - Release notes URL

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

    @property
    def firmware_update_in_progress(self) -> bool:
        """Check if firmware update is currently in progress (from cache).

        This property provides synchronous access to cached firmware update progress status.
        Returns False if no progress data available or if no update is in progress.

        To get real-time progress, call `get_firmware_update_progress()` first.

        Returns:
            True if update is in progress, False otherwise.

        Example:
            >>> # Check progress
            >>> await device.get_firmware_update_progress()
            >>> # Access cached status
            >>> if device.firmware_update_in_progress:
            ...     print(f"Update at {device.firmware_update_percentage}%")
        """
        if self._firmware_update_info is None:
            return False
        return self._firmware_update_info.in_progress

    @property
    def firmware_update_percentage(self) -> int | None:
        """Get firmware update progress percentage (from cache).

        This property provides synchronous access to cached firmware update progress percentage.
        Returns None if no progress data available.

        To get real-time progress, call `get_firmware_update_progress()` first.

        Returns:
            Progress percentage (0-100), or None if not available.

        Example:
            >>> # Check progress
            >>> await device.get_firmware_update_progress()
            >>> # Access cached percentage
            >>> if device.firmware_update_percentage is not None:
            ...     print(f"Progress: {device.firmware_update_percentage}%")
        """
        if self._firmware_update_info is None:
            return None
        return self._firmware_update_info.update_percentage

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

    async def get_firmware_update_progress(self, force: bool = False) -> FirmwareUpdateInfo:
        """Get real-time firmware update progress for this device.

        This method queries the API for current firmware update status and returns
        updated FirmwareUpdateInfo with real-time progress data.

        Caching behavior (adaptive based on update status):
        - During active updates (in_progress=True): 10-second cache for near real-time progress
        - No active update (in_progress=False): 5-minute cache to reduce API load
        - force=True: Always bypasses cache regardless of status

        The short 10-second cache during updates provides fresh progress data while
        preventing excessive API calls if multiple components poll simultaneously.

        Use this method when:
        - Monitoring active firmware update progress
        - Checking if update is in progress
        - Getting current update percentage during installation

        The returned FirmwareUpdateInfo will have:
        - in_progress: True if update is currently active (UPLOADING/READY)
        - update_percentage: Current progress (0-100) parsed from API
        - All other fields from cached firmware check

        Args:
            force: If True, bypass cache and force fresh check from API

        Returns:
            FirmwareUpdateInfo with real-time progress data

        Raises:
            LuxpowerAPIError: If API check fails
            LuxpowerConnectionError: If network connection fails

        Example:
            >>> # Start monitoring after initiating update
            >>> await device.start_firmware_update()
            >>>
            >>> # Poll for progress
            >>> while True:
            ...     progress = await device.get_firmware_update_progress()
            ...     if not progress.in_progress:
            ...         break
            ...     print(f"Progress: {progress.update_percentage}%")
            ...     await asyncio.sleep(30)  # Poll every 30 seconds
        """
        # Import here to avoid circular imports
        import re

        from pylxpweb.models import FirmwareUpdateInfo

        client: LuxpowerClient = self._client  # type: ignore[attr-defined]
        serial: str = self.serial_number  # type: ignore[attr-defined]

        # Check cache (only if not forced)
        # Note: We check cache age first, but if there's an active update,
        # we need fresh data regardless of cache age. However, we can only
        # know if there's an active update by checking the API, so we use
        # a shorter TTL (30 seconds) to ensure we detect updates quickly
        # while still reducing API load during normal operation.
        if not force:
            async with self._firmware_update_cache_lock:
                if (
                    self._firmware_update_info is not None
                    and self._firmware_update_cache_time is not None
                ):
                    cache_age = datetime.now() - self._firmware_update_cache_time

                    # Use different cache TTLs based on update status
                    if self._firmware_update_info.in_progress:
                        # During active update: use very short cache (10 seconds)
                        # to get near real-time progress
                        cache_ttl = timedelta(seconds=10)
                    else:
                        # No active update: use longer cache (5 minutes)
                        # to reduce API load
                        cache_ttl = timedelta(minutes=5)

                    if cache_age < cache_ttl:
                        return self._firmware_update_info

        # Get current update status from API
        status = await client.api.firmware.get_firmware_update_status()

        # Find this device's progress info
        device_info = next(
            (info for info in status.deviceInfos if info.inverterSn == serial),
            None,
        )

        # Determine progress state
        in_progress = False
        update_percentage: int | None = None

        if device_info is not None:
            # Check if update is in progress
            in_progress = device_info.is_in_progress

            # Parse percentage from updateRate string (e.g., "50% - 280 / 561")
            if device_info.updateRate:
                match = re.match(r"^(\d+)%", device_info.updateRate)
                if match:
                    update_percentage = int(match.group(1))

        # Get cached firmware check data (required for version info)
        # If not cached, fetch it now
        if self._firmware_update_info is None:
            await self.check_firmware_updates()
            assert self._firmware_update_info is not None

        # Create updated FirmwareUpdateInfo with progress data
        update_info = FirmwareUpdateInfo(
            installed_version=self._firmware_update_info.installed_version,
            latest_version=self._firmware_update_info.latest_version,
            title=self._firmware_update_info.title,
            release_summary=self._firmware_update_info.release_summary,
            release_url=self._firmware_update_info.release_url,
            in_progress=in_progress,
            update_percentage=update_percentage,
            device_class=self._firmware_update_info.device_class,
            supported_features=self._firmware_update_info.supported_features,
            app_version_current=self._firmware_update_info.app_version_current,
            app_version_latest=self._firmware_update_info.app_version_latest,
            param_version_current=self._firmware_update_info.param_version_current,
            param_version_latest=self._firmware_update_info.param_version_latest,
        )

        # Update cache with progress data
        async with self._firmware_update_cache_lock:
            self._firmware_update_info = update_info
            # Update timestamp: allows caching when no active update
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
        # Import here to avoid circular imports
        from pylxpweb.models import FirmwareUpdateInfo

        client: LuxpowerClient = self._client  # type: ignore[attr-defined]
        serial: str = self.serial_number  # type: ignore[attr-defined]

        # Start the firmware update
        success = await client.api.firmware.start_firmware_update(
            serial, try_fast_mode=try_fast_mode
        )

        # Optimistic update: If successful, immediately set in_progress=True
        # This ensures cache bypass logic activates right away for progress tracking
        if success and self._firmware_update_info is not None:
            async with self._firmware_update_cache_lock:
                # Create updated info with in_progress=True and initial 0% progress
                self._firmware_update_info = FirmwareUpdateInfo(
                    installed_version=self._firmware_update_info.installed_version,
                    latest_version=self._firmware_update_info.latest_version,
                    title=self._firmware_update_info.title,
                    release_summary=self._firmware_update_info.release_summary,
                    release_url=self._firmware_update_info.release_url,
                    in_progress=True,  # Optimistically set to True
                    update_percentage=0,  # Start at 0%
                    device_class=self._firmware_update_info.device_class,
                    supported_features=self._firmware_update_info.supported_features,
                    app_version_current=self._firmware_update_info.app_version_current,
                    app_version_latest=self._firmware_update_info.app_version_latest,
                    param_version_current=self._firmware_update_info.param_version_current,
                    param_version_latest=self._firmware_update_info.param_version_latest,
                )
                # Update timestamp so next progress call uses 10-second cache
                self._firmware_update_cache_time = datetime.now()

        return success

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
