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
    from pylxpweb.models import FirmwareUpdateInfo, FirmwareUpdateRunResult

    class _FirmwareMixinBase:
        """Typed stubs so mypy sees attributes provided by the host class."""

        _client: LuxpowerClient
        serial_number: str

        @property
        def model(self) -> str: ...
else:
    _FirmwareMixinBase = object


class FirmwareUpdateMixin(_FirmwareMixinBase):
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

        # Fetch from API (requires cloud client)
        client: LuxpowerClient = self._client
        serial: str = self.serial_number
        model: str = self.model

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

        client: LuxpowerClient = self._client
        serial: str = self.serial_number

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

        client: LuxpowerClient = self._client
        serial: str = self.serial_number

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
        client: LuxpowerClient = self._client
        serial: str = self.serial_number

        eligibility = await client.api.firmware.check_update_eligibility(serial)
        return eligibility.is_allowed

    async def run_firmware_update_to_completion(
        self,
        *,
        try_fast_mode: bool = False,
        poll_interval: float = 30.0,
        max_steps: int = 5,
        step_timeout: float = 3600.0,
        start_grace: float = 300.0,
    ) -> FirmwareUpdateRunResult:
        """Run firmware updates until the device converges on the latest version.

        ⚠️ CRITICAL WARNING - WRITE OPERATION (potentially long-running)

        Some devices require ``standardUpdate/run`` once per firmware
        component: the portal and mobile app chain these calls automatically,
        but a single :meth:`start_firmware_update` call leaves such a device
        on a partial version — e.g. a 6000XP asked to go to ``ccaa-1E1515``
        lands on ``ccaa-1E1415`` (eg4_web_monitor#353). The check response
        advertises the chain via ``needRunStep2``..``needRunStep5``.

        This orchestrator loops: check → start → poll to completion →
        re-check, until no update remains, a step makes no version progress
        (fail-safe against server-side loops), the step budget is exhausted,
        or a step times out. Each iteration re-verifies eligibility before
        issuing the next run.

        Args:
            try_fast_mode: Attempt fast update mode on each run.
            poll_interval: Seconds between progress polls while a step is
                installing.
            max_steps: Upper bound on ``standardUpdate/run`` invocations
                (the API defines steps 2-5, so 5 covers every known chain).
            step_timeout: Seconds to wait for a single step to finish
                installing before aborting.
            start_grace: Seconds to keep polling for the update to become
                visible (``in_progress=True``) after an accepted start. The
                server registers an accepted run in ``remoteUpdate/info``
                asynchronously — without this grace, an early poll seeing
                idle status would be mistaken for instant completion.

        Returns:
            FirmwareUpdateRunResult describing convergence, steps run, and a
            human-readable outcome message.

        Raises:
            LuxpowerAuthError: If authentication fails.
            LuxpowerAPIError: If an API call fails outright.
            LuxpowerConnectionError: If connection fails.
        """
        # Import here to avoid circular imports
        from pylxpweb.models import FirmwareUpdateRunResult

        def _versions(info: FirmwareUpdateInfo) -> tuple[int | None, int | None]:
            return (info.app_version_current, info.param_version_current)

        info = await self.check_firmware_updates(force=True)
        if not info.update_available:
            return FirmwareUpdateRunResult(
                success=True,
                converged=True,
                steps_run=0,
                message="Firmware already up to date",
                final_version=info.installed_version,
            )

        steps_run = 0
        loop = asyncio.get_running_loop()
        for _ in range(max_steps):
            before = _versions(info)

            if not await self.check_update_eligibility():
                return FirmwareUpdateRunResult(
                    success=False,
                    converged=False,
                    steps_run=steps_run,
                    message=("Device not eligible for update (another update may be in progress)"),
                    final_version=info.installed_version,
                )

            started = await self.start_firmware_update(try_fast_mode=try_fast_mode)
            steps_run += 1
            if not started:
                return FirmwareUpdateRunResult(
                    success=False,
                    converged=False,
                    steps_run=steps_run,
                    message="API refused to start the firmware update",
                    final_version=info.installed_version,
                )

            # Poll the step to completion in two phases. The server registers
            # an accepted run in remoteUpdate/info asynchronously, so an idle
            # status straight after start does NOT mean the step finished —
            # keep polling within start_grace until the update becomes
            # visible (or grace expires: fast steps can genuinely complete
            # between polls, which the post-step version re-check resolves).
            # The first poll is forced so a stale not-in-progress cache entry
            # cannot end the wait early.
            deadline = loop.time() + step_timeout
            grace_deadline = loop.time() + start_grace
            saw_in_progress = False
            force_poll = True
            while True:
                progress = await self.get_firmware_update_progress(force=force_poll)
                force_poll = False
                if progress.in_progress:
                    saw_in_progress = True
                elif saw_in_progress or loop.time() >= grace_deadline:
                    break
                if loop.time() >= deadline:
                    return FirmwareUpdateRunResult(
                        success=False,
                        converged=False,
                        steps_run=steps_run,
                        message=(
                            f"Firmware update step {steps_run} did not finish "
                            f"within {int(step_timeout)}s"
                        ),
                        final_version=info.installed_version,
                    )
                await asyncio.sleep(poll_interval)

            info = await self.check_firmware_updates(force=True)
            if not info.update_available:
                return FirmwareUpdateRunResult(
                    success=True,
                    converged=True,
                    steps_run=steps_run,
                    message=(f"Firmware update complete after {steps_run} step(s)"),
                    final_version=info.installed_version,
                )

            if _versions(info) == before:
                # A run completed but neither component advanced — do not
                # keep issuing writes against an unresponsive chain.
                return FirmwareUpdateRunResult(
                    success=False,
                    converged=False,
                    steps_run=steps_run,
                    message=(
                        f"No firmware version progress after step {steps_run}; "
                        "stopping to avoid repeated update commands (if the "
                        "device is still installing, wait for it to finish "
                        "before retrying)"
                    ),
                    final_version=info.installed_version,
                )

        return FirmwareUpdateRunResult(
            success=False,
            converged=False,
            steps_run=steps_run,
            message=(f"Update still available after {steps_run} steps; stopping at step budget"),
            final_version=info.installed_version,
        )
