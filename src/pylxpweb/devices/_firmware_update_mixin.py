"""Firmware update detection mixin for devices.

This module provides the FirmwareUpdateMixin class that can be mixed into
any device class (BaseInverter, MIDDevice, etc.) to add firmware update
detection capabilities with caching and Home Assistant compatibility.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

_LOGGER = logging.getLogger(__name__)

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
            needs_run_steps=self._firmware_update_info.needs_run_steps,
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
                    needs_run_steps=self._firmware_update_info.needs_run_steps,
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

    async def _update_step_reported_failed(self) -> bool:
        """Whether ``remoteUpdate/info`` reports this device's update as FAILED.

        Consulted by the run-to-completion orchestrator after each step ends:
        the aggregated progress conversion collapses every non-installing
        state to ``in_progress=False``, so the terminal FAILED status must be
        read from the raw status row.
        """
        client: LuxpowerClient = self._client
        serial: str = self.serial_number
        status = await client.api.firmware.get_firmware_update_status()
        row = next(
            (item for item in status.deviceInfos if item.inverterSn == serial),
            None,
        )
        return row is not None and row.is_failed

    async def run_firmware_update_to_completion(
        self,
        *,
        try_fast_mode: bool = False,
        poll_interval: float = 30.0,
        max_steps: int = 5,
        step_timeout: float = 3600.0,
        start_grace: float = 300.0,
        settle_checks: int = 3,
        settle_interval: float = 30.0,
        no_progress_grace: int = 1,
        busy_grace: float = 900.0,
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
        re-check, until no update remains, the no-progress grace is spent
        (fail-safe against server-side loops), the step budget is exhausted,
        or a step times out. Each iteration re-verifies eligibility before
        issuing the next run.

        A component that is ALREADY at the target version still flashes when
        the server selects it — ``standardUpdate/run`` takes no step/component
        parameter, so which component a run installs is the server's choice.
        Such a run completes normally and cannot move the version string,
        which is exactly how a partially-upgraded 6000XP got stuck: step 1
        re-flashed the already-current component, and aborting on the first
        unchanged version meant the component that actually needed upgrading
        never ran (eg4_web_monitor#353). ``no_progress_grace`` therefore
        tolerates a bounded number of *consecutive* steps that ran without
        changing the version before declaring the chain dead.

        Busy handling is deliberately asymmetric. Before this invocation has
        started anything, a busy device means "not now" and fails fast — the
        server has accepted no update start from us, and making the user wait out
        a multi-minute retry budget only to fail is worse than saying so
        immediately.
        Once a component HAS been started, busy means the chain we started is
        still settling, and the bounded retry budget applies.

        Args:
            try_fast_mode: Attempt fast update mode on each run.
            poll_interval: Seconds between progress polls while a step is
                installing.
            max_steps: Upper bound on ACCEPTED update steps (the API defines
                steps 2-5, so 5 covers every known chain). Busy retries can
                issue additional ``standardUpdate/run`` POSTs beyond this,
                but a refused call installs nothing.
            step_timeout: Seconds to wait for a single step to finish
                installing before aborting.
            start_grace: Seconds to keep polling for the update to become
                visible (``in_progress=True``) after an accepted start. The
                server registers an accepted run in ``remoteUpdate/info``
                asynchronously — without this grace, an early poll seeing
                idle status would be mistaken for instant completion.
            settle_checks: Extra post-step version re-checks before an
                unchanged version is declared "no progress" (the check
                endpoint can lag the status endpoint's terminal state).
            settle_interval: Seconds between those settle re-checks.
            no_progress_grace: How many *consecutive* steps may complete
                without moving the version before the chain is abandoned.
                Only steps that were actually observed installing are
                excused (see the loop body); 0 restores the pre-#353
                abort-on-first-unchanged-version behaviour.
            busy_grace: Seconds to keep re-polling a busy device BETWEEN
                components before giving up on the chain (bounded by
                ``step_timeout``). Only applies once a step has been started:
                a device that is busy before the first step fails fast. A
                component reboot/settle can outlast ``start_grace``, and
                giving up there strands the device mid-chain, so this budget
                is deliberately wider than the post-start visibility grace.

        Returns:
            FirmwareUpdateRunResult describing convergence, steps run, and a
            human-readable outcome message.

        Raises:
            LuxpowerAuthError: If authentication fails.
            LuxpowerAPIError: If an API call fails outright.
            LuxpowerConnectionError: If connection fails.
        """
        # Import here to avoid circular imports
        from pylxpweb.endpoints.firmware import FIRMWARE_UP_TO_DATE_MESSAGES
        from pylxpweb.exceptions import LuxpowerAPIError
        from pylxpweb.models import FirmwareUpdateRunResult

        def _progress_key(
            info: FirmwareUpdateInfo,
        ) -> tuple[str | None, int | None, int | None]:
            # The full installed code is the primary progress signal: it
            # also captures prefix-byte movement (ccaa-1D.. -> ccaa-1E..)
            # that the trailing v1/v2 pair cannot see (lastV3 does not
            # exist in the API). The pair rides along for layouts where
            # the code string is empty.
            return (
                info.installed_version or None,
                info.app_version_current,
                info.param_version_current,
            )

        def _is_device_busy_error(err: LuxpowerAPIError) -> bool:
            # A start/eligibility call can lose a TOCTOU race and come back busy
            # under any of the API's busy-ish codes, not just the observed
            # ``deviceBusy``. Match on two stems that cover the whole family:
            #   - ``busy``: ``deviceBusy`` / ``device_busy`` / ``DEVICE_BUSY`` /
            #     bare ``BUSY`` (the transport transient code).
            #   - ``updating``: the eligibility enum codes ``deviceUpdating`` /
            #     ``parallelGroupUpdating`` AND the ``standardUpdate/run`` prose
            #     variants ("Device is already updating", "Another device in the
            #     parallel group is updating"). A non-busy start error ("no
            #     update available", bad serial, etc.) does not contain either
            #     stem, so it still propagates.
            # Treat all busy-ish responses as transient so the bounded
            # busy-retry tolerates the race instead of escaping raw.
            message = str(err).casefold()
            return "busy" in message or "updating" in message

        def _is_already_latest_error(err: LuxpowerAPIError) -> bool:
            # ``standardUpdate/run`` refuses a device it considers converged
            # with the same "already the latest version" prose the check
            # endpoint uses. Reachable when the check endpoint lags a
            # successful final step past the settle window and the
            # no-progress grace lets the loop ask for one step too many.
            # The refusal alone does NOT establish convergence — the caller
            # confirms with a forced re-check before reporting success.
            message = str(err).casefold()
            return any(stem in message for stem in FIRMWARE_UP_TO_DATE_MESSAGES)

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
        # Consecutive steps that completed without moving the version. Reset
        # on any version movement; compared against no_progress_grace.
        consecutive_no_progress = 0
        # The converged version to report: once the device is up to date the
        # check endpoint answers with the bare "already latest" sentinel
        # (empty fwCodeBeforeUpload), so remember the target we converged to.
        last_target = info.latest_version or None
        loop = asyncio.get_running_loop()
        # Smallest wait between busy/eligibility re-polls. Floors poll_interval
        # so a degenerate poll_interval=0 cannot hot-loop eligibility/start
        # calls at the API; never exceeds the time left in the budget.
        retry_backoff = poll_interval if poll_interval > 0 else 0.05

        def _budget_spent(
            step_index: int, installed_version: str | None
        ) -> FirmwareUpdateRunResult:
            return FirmwareUpdateRunResult(
                success=False,
                converged=False,
                steps_run=step_index,
                message=(
                    "Device remained busy; firmware update step "
                    f"{step_index + 1} could not start within the retry budget"
                ),
                final_version=installed_version,
            )

        def _busy_before_any_step(installed_version: str | None) -> FirmwareUpdateRunResult:
            # Nothing has been written yet, so there is no chain of ours to
            # protect: report immediately instead of holding the caller (and
            # the HA install action) for the whole retry budget only to fail.
            return FirmwareUpdateRunResult(
                success=False,
                converged=False,
                steps_run=0,
                message=(
                    "Device is busy and cannot start a firmware update right now "
                    "(it may still be installing, or recovering from a previous "
                    "update); wait a few minutes and try again"
                ),
                final_version=installed_version,
            )

        for _ in range(max_steps):
            before = _progress_key(info)
            _LOGGER.debug(
                "Firmware chain for %s: step %d, installed=%s, target=%s, needRunStep flags=%s",
                self.serial_number,
                steps_run + 1,
                info.installed_version,
                info.latest_version,
                info.needs_run_steps,
            )

            # Become eligible and start the next component. Busy handling is
            # split by whether THIS invocation has already started something:
            #
            #   steps_run == 0 (pre-flight): the device was busy before we
            #     had a start accepted — someone/something else is using it, or it is
            #     still recovering from an earlier update. Fail fast on both
            #     not-eligible and any busy-family error, from the eligibility
            #     probe or the start call. Burning the whole retry budget here
            #     only to fail is strictly worse UX than saying so immediately
            #     (eg4_web_monitor#353: a user watched "Installing" for five
            #     minutes before being told the device was busy the whole time).
            #
            #   steps_run > 0 (mid-chain): the device is settling/rebooting
            #     between components of a chain WE started, so both the
            #     eligibility gate and the start call may briefly report busy —
            #     the multi-step chain must not abort in that window. Re-poll
            #     within a bounded budget of min(busy_grace, step_timeout).
            #
            # A non-busy API error still propagates in both cases.
            busy_deadline = loop.time() + min(busy_grace, step_timeout)

            started = False
            attempted = False
            while True:
                # Never issue a RETRY start write once the budget is spent
                # (checked before the attempt; the first genuine try is exempt
                # so a zero/expired busy_grace still gets one shot).
                if attempted and loop.time() >= busy_deadline:
                    return _budget_spent(steps_run, info.installed_version)
                first_attempt = not attempted
                attempted = True

                # The eligibility probe is itself a network call that can come
                # back busy (transport BUSY / deviceUpdating / parallelGroup).
                try:
                    eligible = await self.check_update_eligibility()
                except LuxpowerAPIError as err:
                    if not _is_device_busy_error(err):
                        raise
                    if steps_run == 0:
                        return _busy_before_any_step(info.installed_version)
                    # Mid-chain: still working — fall through to the bounded
                    # retry below rather than letting it escape raw.
                    eligible = False

                if eligible:
                    # The eligibility call can straddle the deadline; never fire
                    # a RETRY write past it (the first genuine try is exempt).
                    if not first_attempt and loop.time() >= busy_deadline:
                        return _budget_spent(steps_run, info.installed_version)
                    try:
                        started = await self.start_firmware_update(try_fast_mode=try_fast_mode)
                        break
                    except LuxpowerAPIError as err:
                        if steps_run > 0 and _is_already_latest_error(err):
                            # The run endpoint says there is nothing left to
                            # install while the check endpoint still advertises
                            # an update. That is expected when the check lagged
                            # a successful final step past the settle window and
                            # the loop asked for one step too many — but it is
                            # NOT self-evidently convergence: the two endpoints
                            # can genuinely disagree about a partially upgraded
                            # device, and reporting success there would hide the
                            # exact partial-upgrade failure this issue is about.
                            # Re-check and let the check endpoint confirm; never
                            # declare convergence on the refusal alone.
                            # (Pre-flight, this still propagates untouched.)
                            info = await self.check_firmware_updates(force=True)
                            if info.latest_version:
                                last_target = info.latest_version
                            if not info.update_available:
                                return FirmwareUpdateRunResult(
                                    success=True,
                                    converged=True,
                                    steps_run=steps_run,
                                    message=(f"Firmware update complete after {steps_run} step(s)"),
                                    final_version=info.installed_version or last_target,
                                )
                            return FirmwareUpdateRunResult(
                                success=False,
                                converged=False,
                                steps_run=steps_run,
                                message=(
                                    "Server refused a further update step as "
                                    "'already the latest version', but the update "
                                    "check still reports one available — the device "
                                    "may be partially upgraded; re-check in a few "
                                    "minutes before retrying"
                                ),
                                final_version=info.installed_version,
                            )
                        if not _is_device_busy_error(err):
                            raise
                        if steps_run == 0:
                            return _busy_before_any_step(info.installed_version)
                elif steps_run == 0:
                    # Genuine pre-flight rejection on the very first step.
                    return FirmwareUpdateRunResult(
                        success=False,
                        converged=False,
                        steps_run=steps_run,
                        message=(
                            "Device not eligible for update (another update may be in progress)"
                        ),
                        final_version=info.installed_version,
                    )
                await asyncio.sleep(min(retry_backoff, max(0.0, busy_deadline - loop.time())))

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
            # EVERY poll is forced: get_firmware_update_progress caches a
            # not-in-progress snapshot for 5 MINUTES, so unforced polls
            # would replay the pre-registration idle snapshot for the whole
            # grace window and the loop would abandon a genuinely running
            # step as "no progress" (~2 API calls/min while installing —
            # comparable to the portal's own polling).
            deadline = loop.time() + step_timeout
            grace_deadline = loop.time() + start_grace
            saw_in_progress = False
            while True:
                progress = await self.get_firmware_update_progress(force=True)
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

            # A step that ended in FAILED must stop the chain: firing another
            # run against a device whose previous step failed is exactly the
            # class of blind write this orchestrator exists to prevent.
            if await self._update_step_reported_failed():
                # Re-check so the reported version reflects any partial
                # advance the failed step made before stopping.
                info = await self.check_firmware_updates(force=True)
                if info.latest_version:
                    last_target = info.latest_version
                return FirmwareUpdateRunResult(
                    success=False,
                    converged=False,
                    steps_run=steps_run,
                    message=(
                        f"Firmware update step {steps_run} reported FAILED by "
                        "the server; not issuing further update commands"
                    ),
                    final_version=info.installed_version,
                )

            # Post-step re-check with a bounded settle window: the check
            # endpoint's version data can lag the status endpoint's terminal
            # state (cloud eventual consistency), and a single immediate
            # re-check could mistake that lag for a dead chain.
            for settle in range(settle_checks + 1):
                if settle:
                    await asyncio.sleep(settle_interval)
                info = await self.check_firmware_updates(force=True)
                if info.latest_version:
                    last_target = info.latest_version
                if not info.update_available:
                    return FirmwareUpdateRunResult(
                        success=True,
                        converged=True,
                        steps_run=steps_run,
                        message=(f"Firmware update complete after {steps_run} step(s)"),
                        final_version=info.installed_version or last_target,
                    )
                if _progress_key(info) != before:
                    consecutive_no_progress = 0
                    break  # component advanced — continue the chain
            else:
                # No version movement across the settle window. This is NOT
                # automatically a dead chain: standardUpdate/run takes no
                # component selector, so the server can pick a component that
                # is already at the target version, which flashes normally and
                # cannot move the version string (eg4_web_monitor#353 — the
                # 6000XP stuck at ccaa-1E1415 re-flashed its already-current
                # component as step 1 and the remaining one never ran).
                #
                # Excuse such a step only with positive evidence that it really
                # ran: `saw_in_progress` means the status endpoint reported the
                # device installing, and the FAILED check above already passed.
                # A terminal SUCCESS/COMPLETE row would be stronger evidence,
                # but it is not reliably observable on the reporting hardware —
                # the poll loop exits as soon as in_progress goes false — so
                # "was seen installing and did not report FAILED" is the
                # deliberately weaker signal used here, because a stronger one
                # risks a fix that never fires in the field.
                #
                # Consecutive excuses are capped by no_progress_grace, and
                # accepted update steps by max_steps (busy retries can issue
                # more standardUpdate/run POSTs than that, but a refused one
                # installs nothing), so a stuck device still stops.
                if saw_in_progress and consecutive_no_progress < no_progress_grace:
                    consecutive_no_progress += 1
                    _LOGGER.info(
                        "Firmware step %d for %s completed without changing the "
                        "version (%s) — a component already at the target flashes "
                        "as a no-op; continuing the chain (needRunStep flags=%s)",
                        steps_run,
                        self.serial_number,
                        info.installed_version,
                        info.needs_run_steps,
                    )
                    continue
                # Do not keep issuing writes against an unresponsive chain.
                return FirmwareUpdateRunResult(
                    success=False,
                    converged=False,
                    steps_run=steps_run,
                    message=(
                        f"No firmware version progress after step {steps_run} "
                        f"(needRunStep flags: {info.needs_run_steps or 'none'}); "
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
