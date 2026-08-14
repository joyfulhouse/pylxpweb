"""Base device classes for pylxpweb.

This module provides abstract base classes for all device types,
implementing common functionality like refresh intervals, caching,
and Home Assistant integration.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Never, TypeVar

from pylxpweb.validation import (
    MAX_ELAPSED_HOURS,
    MAX_ENERGY_DELTA,
    validate_daily_energy_bounds,
    validate_energy_monotonicity,
)

from .models import DeviceInfo, Entity

_LOGGER = logging.getLogger(__name__)

# Number of initial energy reads that bypass validation to establish
# baseline values.  Prevents false rejections at startup when the first
# real data arrives with no previous values to compare against.
WARMUP_READS = 2

# Consecutive transport-read failures after which the local link is
# considered down (``transport_link_down`` becomes True).  Reads keep
# being attempted every cycle — the transports' own reconnect logic
# (Modbus ``_reconnect()``, dongle reconnect-on-timeout) handles
# recovery, and any successful read resets the counter.
TRANSPORT_LINK_DOWN_THRESHOLD = 3

# Minimum seconds between link-down probes.  Coordinator code paths can
# call refresh() more than once within the same update tick (e.g. a group
# refresh followed by per-device processing); while the link is down every
# transport read is a probe against a dead endpoint, so same-tick
# duplicates collapse to one.  Just under the fastest 5s coordinator tick
# so every real cycle still probes.
LINK_PROBE_MIN_INTERVAL_SECONDS = 4.0

_T = TypeVar("_T")


def _cancellation_only(error: BaseException) -> asyncio.CancelledError | None:
    """Return one cancellation when every leaf is cancellation-only."""
    if isinstance(error, asyncio.CancelledError):
        return error
    if isinstance(error, BaseExceptionGroup):
        cancellation: asyncio.CancelledError | None = None
        for nested_error in error.exceptions:
            nested_cancellation = _cancellation_only(nested_error)
            if nested_cancellation is None:
                return None
            if cancellation is None:
                cancellation = nested_cancellation
        return cancellation
    return None


def _raise_transport_errors(
    message: str,
    errors: list[BaseException],
    *,
    cause: BaseException,
) -> Never:
    """Raise one native cancellation or a group containing mixed failures."""
    cancellation = _cancellation_only(errors[0])
    if cancellation is None:
        raise BaseExceptionGroup(message, errors) from cause
    for error in errors[1:]:
        nested_cancellation = _cancellation_only(error)
        if nested_cancellation is None:
            raise BaseExceptionGroup(message, errors) from cause
    raise cancellation


if TYPE_CHECKING:
    from collections.abc import Awaitable

    from pylxpweb import LuxpowerClient
    from pylxpweb.transports.protocol import InverterTransport, TerminalInverterTransport


class BaseDevice(ABC):
    """Abstract base class for all device types.

    This class provides common functionality for inverters, batteries,
    MID devices, and stations, including:
    - Refresh interval management with TTL
    - Client reference for API access
    - Home Assistant integration methods

    Subclasses must implement:
    - refresh(): Load/reload device data from API
    - to_device_info(): Convert to device info model
    - to_entities(): Generate entity list

    Example:
        ```python
        class MyDevice(BaseDevice):
            async def refresh(self) -> None:
                data = await self._client.api.devices.get_data(self.serial_number)
                self._process_data(data)
                self._last_refresh = datetime.now()

            def to_device_info(self) -> DeviceInfo:
                return DeviceInfo(
                    identifiers={("pylxpweb", f"device_{self.serial_number}")},
                    name=f"My Device {self.serial_number}",
                    manufacturer="EG4",
                    model=self.model,
                )

            def to_entities(self) -> list[Entity]:
                return [
                    Entity(unique_id=f"{self.serial_number}_power", ...)
                ]
        ```
    """

    def __init__(
        self,
        client: LuxpowerClient,
        serial_number: str,
        model: str,
    ) -> None:
        """Initialize base device.

        Args:
            client: LuxpowerClient instance for API access.  Local-only
                (transport-backed) devices pass ``None`` via
                ``type: ignore[arg-type]`` since they never call cloud API
                methods.
            serial_number: Device serial number (unique identifier)
            model: Device model name
        """
        self._client = client
        self.serial_number = serial_number
        self._model = model
        self._last_refresh: datetime | None = None
        self._refresh_interval = timedelta(seconds=30)

        # Local transport (Modbus/Dongle) - None means HTTP-only mode
        self._local_transport: InverterTransport | None = None
        self._local_transport_requires_terminal = False
        self._transport_lifecycle_lock = asyncio.Lock()
        self._transport_lifecycle_owner: asyncio.Task[object] | None = None
        self._transport_lifecycle_delegate: asyncio.Task[object] | None = None

        # Data validation: when True, corrupt transport reads are rejected
        # and the previous cached value is kept instead. Set by coordinator
        # from the CONF_DATA_VALIDATION option.
        self.validate_data: bool = False

        # Energy monotonicity validation counter (consecutive rejections).
        # Shared by BaseInverter and MIDDevice for lifetime energy checks.
        self._energy_reject_count: int = 0

        # Warm-up counter: first N energy reads establish baseline without
        # validation.  Prevents false rejections on startup when prev=None
        # transitions to real data with large deltas.
        self._energy_validation_calls: int = 0

        # Max energy delta (kWh) for spike detection.  Subclasses override
        # with rated_power_kw * 1.5 once device capabilities are known.
        self._max_energy_delta: float = MAX_ENERGY_DELTA

        # Max power (watts) for canary checks.  Zero means "not yet known",
        # so power checks are skipped until detect_features() or
        # set_max_system_power() populates this.  Computed as rated_kw * 2000
        # (2x margin) to catch 0xFFFF (65535W) corrupt register reads.
        self._max_power_watts: float = 0.0

        # Rated power (kW) for daily energy bounds validation.  Set by
        # detect_features() (inverters) or set_max_system_power() (MID).
        # Zero means unknown — validation falls back to DEFAULT_RATED_POWER_KW.
        self._rated_power_kw: float = 0.0

        # Tracks when daily energy values last *increased* (not just last read).
        # Used for elapsed_seconds in daily bounds validation so the window
        # reflects the actual accumulation period, not the polling interval.
        # Only updated when an accepted read contains a daily value increase.
        # Monotonic clock — wall-clock (DST/NTP) steps must not move the window.
        self._daily_energy_change_monotonic: float | None = None

        # Tracks when a lifetime energy counter last *increased* on a
        # COMMITTED read (_note_energy_accepted).  Used by _is_energy_valid
        # to widen the per-cycle monotonicity spike cap after an outage:
        # while a device is offline the cloud serves its counters frozen,
        # so on reconnect the true value arrives as one large — but
        # legitimate — catch-up delta (eg4_web_monitor#479).  Monotonic
        # clock; None until the first validated read seeds it.
        self._lifetime_energy_change_monotonic: float | None = None
        # Outage evidence gate for that widening: armed by a cloud payload
        # flagged lost or a transport link-down transition, disarmed when a
        # committed read shows a counter increase.  Without this gate a
        # merely-idle device (every counter flat overnight) would widen its
        # own spike cap and weaken the always-on corruption canary.
        self._energy_source_stale: bool = False

        # ===== Transport link health (eg4-57g / integration #226) =====
        # Consecutive transport-read failures and last-success timestamp.
        # When the counter crosses TRANSPORT_LINK_DOWN_THRESHOLD, the link
        # is declared down: cached transport data stops being served (see
        # _on_transport_link_down) so consumers don't mistake stale local
        # reads for fresh data.  Reads keep being attempted every cycle;
        # any success resets the counter.
        self._transport_consecutive_failures: int = 0
        self._transport_last_success_monotonic: float | None = None
        # One-shot logging guard: warn once on the down transition, info
        # once on recovery — per-failure logs stay at debug level.
        self._transport_link_down_logged: bool = False
        # Rate limit for link-down probes (see _link_probe_due): collapses
        # same-tick duplicate refresh() calls into one dead-link read.
        self._last_link_probe_monotonic: float | None = None

    @property
    def model(self) -> str:
        """Get device model name.

        Returns:
            Device model name, or "Unknown" if not available.
        """
        return self._model if self._model else "Unknown"

    @property
    def needs_refresh(self) -> bool:
        """Check if device data needs refreshing based on TTL.

        Returns:
            True if device has never been refreshed or TTL has expired,
            False if data is still fresh.
        """
        if self._last_refresh is None:
            return True
        return datetime.now() - self._last_refresh > self._refresh_interval

    @property
    def has_local_transport(self) -> bool:
        """Check if device has an attached local transport.

        Returns:
            True if a local transport (Modbus or Dongle) is attached,
            False if only HTTP API is available.
        """
        return self._local_transport is not None

    @property
    def transport(self) -> InverterTransport | None:
        """Return the attached local transport capability, if any."""
        return self._local_transport

    @property
    def _transport(self) -> InverterTransport | None:
        """Compatibility alias for internal transport-backed device code."""
        return self._local_transport

    @_transport.setter
    def _transport(self, transport: InverterTransport | None) -> None:
        self._local_transport = transport
        self._local_transport_requires_terminal = False

    async def _close_transport_capability(
        self,
        transport: InverterTransport,
        *,
        require_terminal: bool,
    ) -> asyncio.CancelledError | None:
        """Finish one close attempt despite cancellation, then report cancellation."""
        from pylxpweb.transports.protocol import TerminalTransport

        async def close() -> None:
            task = asyncio.current_task()
            self._transport_lifecycle_delegate = task
            try:
                if isinstance(transport, TerminalTransport):
                    await transport.async_shutdown()
                elif not require_terminal:
                    await transport.disconnect()
                else:
                    raise TypeError(
                        "Caller-owned transport capabilities must implement TerminalTransport"
                    )
            finally:
                if self._transport_lifecycle_delegate is task:
                    self._transport_lifecycle_delegate = None

        close_task = asyncio.create_task(close())
        cancellation: asyncio.CancelledError | None = None
        while True:
            try:
                await asyncio.shield(close_task)
            except asyncio.CancelledError as error:
                if close_task.cancelled():
                    if cancellation is not None:
                        _raise_transport_errors(
                            "Local transport cleanup was cancelled and failed",
                            [cancellation, error],
                            cause=error,
                        )
                    raise
                if cancellation is None:
                    cancellation = error
            except BaseException as cleanup_error:
                if cancellation is not None:
                    _raise_transport_errors(
                        "Local transport cleanup was cancelled and failed",
                        [cancellation, cleanup_error],
                        cause=cleanup_error,
                    )
                cleanup_cancellation = _cancellation_only(cleanup_error)
                if cleanup_cancellation is not None:
                    raise cleanup_cancellation from cleanup_error
                raise
            else:
                return cancellation

    def _check_transport_lifecycle_reentry(self) -> None:
        """Reject nested lifecycle calls made by the active transition."""
        task = asyncio.current_task()
        if task in (
            self._transport_lifecycle_owner,
            self._transport_lifecycle_delegate,
        ):
            raise RuntimeError("Local transport lifecycle re-entry is not supported")

    async def _acquire_transport_lifecycle(self) -> None:
        """Acquire lifecycle ownership after rejecting same-transition re-entry."""
        self._check_transport_lifecycle_reentry()
        await self._transport_lifecycle_lock.acquire()
        self._transport_lifecycle_owner = asyncio.current_task()

    def _release_transport_lifecycle(self) -> None:
        """Release lifecycle ownership held by the current task."""
        self._transport_lifecycle_owner = None
        self._transport_lifecycle_lock.release()

    async def attach_local_transport(
        self,
        transport: TerminalInverterTransport,
    ) -> None:
        """Connect and publicly retain a caller-supplied local capability.

        A replacement is not published until the new capability is connected
        and the old capability has reached terminal closure. Any failure or
        cancellation closes the unretained new capability before propagating.
        Already-connected capabilities are retained without another connect.

        Args:
            transport: Terminal capability whose serial must match this device.

        Raises:
            ValueError: If the capability serial does not match this device.
            BaseExceptionGroup: If attachment and cleanup both fail.
        """
        from pylxpweb.transports.protocol import TerminalInverterTransport

        if not isinstance(transport, TerminalInverterTransport):
            raise TypeError(
                "Caller-owned transport capabilities must implement TerminalInverterTransport"
            )
        await self._attach_transport_capability(transport, require_terminal=True)

    async def _attach_legacy_local_transport(self, transport: InverterTransport) -> None:
        """Attach a pylxpweb-created transport with disconnect compatibility."""
        await self._attach_transport_capability(transport, require_terminal=False)

    async def _attach_transport_capability(
        self,
        transport: InverterTransport,
        *,
        require_terminal: bool,
    ) -> None:
        """Serialize attachment for public terminal and private legacy paths."""

        self._check_transport_lifecycle_reentry()
        try:
            await self._transport_lifecycle_lock.acquire()
        except BaseException as acquire_error:
            await self._cleanup_cancelled_lifecycle_waiter(
                transport,
                require_terminal=require_terminal,
                primary_error=acquire_error,
            )
            raise acquire_error
        self._transport_lifecycle_owner = asyncio.current_task()

        try:
            await self._attach_local_transport_locked(
                transport,
                require_terminal=require_terminal,
            )
        finally:
            self._release_transport_lifecycle()

    async def _cleanup_cancelled_lifecycle_waiter(
        self,
        transport: InverterTransport,
        *,
        require_terminal: bool,
        primary_error: BaseException,
    ) -> None:
        """Serialize ownership resolution for an input whose waiter was cancelled."""

        async def cleanup() -> None:
            await self._acquire_transport_lifecycle()
            try:
                if self._local_transport is not transport:
                    cancellation = await self._close_transport_capability(
                        transport,
                        require_terminal=require_terminal,
                    )
                    if cancellation is not None:
                        raise cancellation
            finally:
                self._release_transport_lifecycle()

        cleanup_task = asyncio.create_task(cleanup())
        later_cancellation: asyncio.CancelledError | None = None
        cleanup_error: BaseException | None = None
        while True:
            try:
                await asyncio.shield(cleanup_task)
            except asyncio.CancelledError as error:
                if cleanup_task.cancelled():
                    cleanup_error = error
                    break
                if later_cancellation is None:
                    later_cancellation = error
            except BaseException as error:
                cleanup_error = error
                break
            else:
                break

        errors = [primary_error]
        if later_cancellation is not None:
            errors.append(later_cancellation)
        if cleanup_error is not None:
            errors.append(cleanup_error)
        if len(errors) > 1:
            _raise_transport_errors(
                "Local transport lifecycle wait and cleanup failed",
                errors,
                cause=primary_error,
            )

    async def _cleanup_unretained_transport(
        self,
        transport: InverterTransport,
        *,
        require_terminal: bool,
        primary_error: BaseException,
    ) -> None:
        """Close an unpublished input and combine a cleanup failure."""
        try:
            cancellation = await self._close_transport_capability(
                transport,
                require_terminal=require_terminal,
            )
        except BaseException as cleanup_error:
            _raise_transport_errors(
                "Local transport attachment and cleanup both failed",
                [primary_error, cleanup_error],
                cause=primary_error,
            )
        if cancellation is not None:
            _raise_transport_errors(
                "Local transport attachment and cleanup were interrupted",
                [primary_error, cancellation],
                cause=primary_error,
            )
        primary_cancellation = _cancellation_only(primary_error)
        if primary_cancellation is not None:
            raise primary_cancellation

    async def _attach_local_transport_locked(
        self,
        transport: InverterTransport,
        *,
        require_terminal: bool,
    ) -> None:
        """Perform one attachment transition while holding the lifecycle lock."""
        current = self._local_transport
        if transport.serial != self.serial_number:
            serial_error = ValueError(
                f"Transport serial {transport.serial!r} does not match "
                f"device {self.serial_number!r}"
            )
            if current is transport:
                raise serial_error
            await self._cleanup_unretained_transport(
                transport,
                require_terminal=require_terminal,
                primary_error=serial_error,
            )
            raise serial_error
        if current is transport:
            if not transport.is_connected:
                await transport.connect()
            self._local_transport_requires_terminal = require_terminal
            self._on_local_transport_attached()
            return

        try:
            if not transport.is_connected:
                await transport.connect()
            if current is not None:
                cancellation = await self._close_transport_capability(
                    current,
                    require_terminal=self._local_transport_requires_terminal,
                )
                if cancellation is not None:
                    self._local_transport = None
                    self._local_transport_requires_terminal = False
                    self._on_local_transport_detached()
                    raise cancellation
        except BaseException as attach_error:
            await self._cleanup_unretained_transport(
                transport,
                require_terminal=require_terminal,
                primary_error=attach_error,
            )
            raise

        self._local_transport = transport
        self._local_transport_requires_terminal = require_terminal
        self._on_local_transport_attached()

    async def detach_local_transport(self) -> InverterTransport | None:
        """Terminally close and detach the current local capability.

        Capabilities implementing ``TerminalTransport`` receive
        ``async_shutdown()``; other capabilities receive ``disconnect()``.
        The capability remains retained if closure raises. Cancellation is delayed
        until the close attempt completes; a successful close detaches before the
        cancellation propagates.

        Returns:
            The detached capability, or None when no capability was attached.
        """
        await self._acquire_transport_lifecycle()
        try:
            transport = self._local_transport
            if transport is None:
                return None
            cancellation = await self._close_transport_capability(
                transport,
                require_terminal=self._local_transport_requires_terminal,
            )
            self._local_transport = None
            self._local_transport_requires_terminal = False
            self._on_local_transport_detached()
            if cancellation is not None:
                raise cancellation
            return transport
        finally:
            self._release_transport_lifecycle()

    def _on_local_transport_attached(self) -> None:
        """Apply subclass state changes after a capability is published."""
        return

    def _on_local_transport_detached(self) -> None:
        """Apply subclass state changes after a capability is detached."""
        return

    @property
    def is_local_only(self) -> bool:
        """Check if device is local-only (no HTTP client credentials).

        Returns:
            True if the device was created from local transport without
            cloud API credentials, False otherwise.
        """
        return self._local_transport is not None and not self._client.username

    # ------------------------------------------------------------------
    # Transport link health (eg4-57g / integration #226)
    # ------------------------------------------------------------------

    @property
    def transport_consecutive_failures(self) -> int:
        """Number of consecutive failed transport reads for this device."""
        return self._transport_consecutive_failures

    @property
    def transport_link_down(self) -> bool:
        """True when the local transport link is considered down.

        The link is declared down after TRANSPORT_LINK_DOWN_THRESHOLD
        consecutive transport-read failures.  The transport stays attached
        and reads keep being attempted every refresh cycle — any successful
        read clears this flag.  Always False for devices that have never
        had a transport read fail (including cloud-only devices).
        """
        return self._transport_consecutive_failures >= TRANSPORT_LINK_DOWN_THRESHOLD

    @property
    def _cloud_fallback_available(self) -> bool:
        """True when a usable cloud client exists for degraded HTTP fallback.

        Local-only devices are constructed with ``client=None`` (or a
        credential-less placeholder), so they can never fall back to HTTP.
        """
        return self._client is not None and bool(getattr(self._client, "username", ""))

    def _link_probe_due(self) -> bool:
        """Check-and-stamp the link-down probe rate limit.

        While the link is down every transport read is a probe against a
        dead endpoint, and coordinator code paths can call refresh() more
        than once within the same update tick (e.g. a group refresh
        followed by per-device processing).  Returns True — and stamps the
        monotonic clock — at most once per LINK_PROBE_MIN_INTERVAL_SECONDS;
        within the interval callers behave as if caches were fresh.  The
        stamp resets on any successful read so a future outage probes
        immediately.
        """
        now = time.monotonic()
        if (
            self._last_link_probe_monotonic is not None
            and now - self._last_link_probe_monotonic < LINK_PROBE_MIN_INTERVAL_SECONDS
        ):
            return False
        self._last_link_probe_monotonic = now
        return True

    def _record_transport_read_success(self) -> None:
        """Reset the failure counter after a successful transport read."""
        self._transport_last_success_monotonic = time.monotonic()
        # A healthy link needs no probe rate limit — reset so a future
        # outage probes immediately on its first post-transition cycle.
        self._last_link_probe_monotonic = None
        if self._transport_link_down_logged:
            _LOGGER.info(
                "Local transport link restored for %s after %d consecutive read failures",
                self.serial_number,
                self._transport_consecutive_failures,
            )
            self._transport_link_down_logged = False
        self._transport_consecutive_failures = 0

    def _record_transport_read_failure(self) -> None:
        """Count a failed transport read; escalate once on the down transition."""
        self._transport_consecutive_failures += 1
        if self.transport_link_down and not self._transport_link_down_logged:
            self._transport_link_down_logged = True
            _LOGGER.warning(
                "Local transport link down for %s after %d consecutive read "
                "failures; reads keep retrying every cycle and cached local "
                "data is no longer served",
                self.serial_number,
                self._transport_consecutive_failures,
            )
            # Sustained outage evidence: the recovery read may carry a large
            # legitimate catch-up energy delta (eg4_web_monitor#479).
            self._note_energy_source_stale()
            self._on_transport_link_down()

    def _on_transport_link_down(self) -> None:
        """Hook invoked exactly once when the link transitions to down.

        Subclasses clear their cached transport data here so properties
        stop serving stale local reads (and, in hybrid mode, fall back to
        HTTP data instead).  The base implementation only records the
        transition at debug level.
        """
        _LOGGER.debug(
            "Transport link down for %s: no transport data caches to clear",
            self.serial_number,
        )

    async def _tracked_transport_read(self, coro: Awaitable[_T]) -> _T:
        """Await a transport read, recording link health.

        Any exception increments the consecutive-failure counter (the
        transition past the threshold logs one warning); a successful
        return resets it (recovery logs one info).  The exception is
        re-raised for the caller's existing error handling.
        """
        try:
            result = await coro
        except Exception:
            self._record_transport_read_failure()
            raise
        self._record_transport_read_success()
        return result

    def _is_energy_valid(
        self,
        prev_values: dict[str, float | None],
        curr_values: dict[str, float | None],
    ) -> bool:
        """Check whether new lifetime energy values pass monotonicity validation.

        Always active — lifetime kWh counters physically cannot decrease,
        so a decrease is always corruption regardless of the validate_data
        toggle.  The validate_data flag controls canary-based is_corrupt()
        checks which can have edge-case false positives; monotonicity
        cannot false-positive at startup because first reads have no
        previous values to compare against, so no warm-up bypass applies
        here either.

        Updates ``_energy_reject_count`` and ``_energy_validation_calls``
        (the warm-up counter consumed by ``_is_daily_energy_valid``) as
        side-effects.

        When outage evidence is armed (``_energy_source_stale``), the spike
        cap is widened by the time since a lifetime counter last increased
        on a committed read (``_lifetime_energy_change_monotonic``, capped
        at ``MAX_ELAPSED_HOURS``).  ``_max_energy_delta`` is
        ``rated_power_kw * 1.5`` — an hour of full rated output with the
        50% safety margin — so ``max_delta * elapsed_hours`` preserves that
        margin across the whole catch-up window, and the legitimate
        reconnect delta is accepted on the first read instead of stalling
        on the 5-strike self-heal (eg4_web_monitor#479).  Without armed
        evidence the cap never widens: a merely-idle device keeps the tight
        per-cycle canary, and gross corruption (0xFFFF-scale jumps) exceeds
        even the widened cap.

        Args:
            prev_values: Previous cycle's lifetime energy dict.
            curr_values: Current cycle's lifetime energy dict.

        Returns:
            True if the data should be accepted, False if it should be rejected.
        """
        self._energy_validation_calls += 1

        max_delta = self._max_energy_delta
        if self._lifetime_energy_change_monotonic is None:
            # Seed on the first validated read so restarts never grant a
            # spuriously wide window (first reads pass trivially anyway —
            # there is no previous value to compare against).
            self._lifetime_energy_change_monotonic = time.monotonic()
        elif self._energy_source_stale:
            elapsed_hours = min(
                (time.monotonic() - self._lifetime_energy_change_monotonic) / 3600.0,
                MAX_ELAPSED_HOURS,
            )
            max_delta = max(max_delta, self._max_energy_delta * elapsed_hours)

        result, self._energy_reject_count = validate_energy_monotonicity(
            prev_values,
            curr_values,
            self._energy_reject_count,
            self.serial_number,
            max_delta=max_delta,
        )
        return result != "reject"

    def _note_energy_source_stale(self) -> None:
        """Arm the catch-up widening: served energy data is known stale.

        Called on outage evidence only — a cloud runtime payload flagged
        ``lost`` or a transport link-down transition.  A plain failed fetch
        deliberately does NOT arm it: transient blips fall back to the
        pre-existing 5-strike self-heal, keeping the always-on corruption
        canary tight (an armed gate plus an idle window would let moderate
        corruption through immediately).

        Disarmed only by ``_note_energy_accepted`` observing a committed
        counter increase — a recovery cannot disarm it earlier, because the
        catch-up delta arrives before any increase can commit.
        """
        self._energy_source_stale = True

    def _note_energy_accepted(
        self,
        prev_values: dict[str, float | None] | None,
        curr_values: dict[str, float | None],
    ) -> None:
        """Re-arm the widening window after a snapshot is COMMITTED.

        Called by the fetch paths after BOTH lifetime and daily validation
        pass and the new snapshot replaces the cache — never from
        ``_is_energy_valid`` itself, so a snapshot that later fails daily
        bounds does not consume the widening window (the identical catch-up
        delta must still be accepted on the next read).  Frozen outage
        reads (``curr == prev``) never re-arm, so the window keeps growing
        until real accumulation lands.

        Also seeds the window on the very first committed snapshot: the
        production fetch paths skip lifetime validation entirely when no
        previous snapshot exists, so without this seed a restart during an
        outage would leave the clock None until the second read.
        """
        if self._lifetime_energy_change_monotonic is None:
            self._lifetime_energy_change_monotonic = time.monotonic()
        if prev_values is None:
            return
        for key, curr in curr_values.items():
            if curr is None:
                continue
            prev = prev_values.get(key)
            if prev is not None and curr > prev:
                self._lifetime_energy_change_monotonic = time.monotonic()
                self._energy_source_stale = False
                return

    def _is_daily_energy_valid(
        self,
        curr_values: dict[str, float | None],
        prev_values: dict[str, float | None] | None,
    ) -> bool:
        """Check whether daily energy values are within plausible bounds.

        Computes elapsed time from ``_daily_energy_change_monotonic`` — the
        last time a daily energy value *increased* — rather than from the
        last accepted read.  This prevents false rejections when a register
        sits unchanged for several polls and then ticks by the minimum
        resolution (0.1 kWh).

        On acceptance, updates ``_daily_energy_change_monotonic`` if any
        daily value increased so the next window starts from this point.

        Gated by ``validate_data`` toggle and warm-up period (counter
        incremented by ``_is_energy_valid``).  Warm-up and first post-gate
        reads seed the change clock so the first real delta check always
        has a bounded window instead of falling back to the lenient
        absolute cap.
        """
        if not self.validate_data:
            return True

        # Warm-up reads and the first gated read with no window yet: skip
        # the time-based delta check (its short windows were the false-
        # rejection source — static-data transitions and unknown elapsed),
        # but still enforce the absolute daily cap so a corrupt spike can
        # never slip through unchecked.  Seeds the change clock so the
        # next read gets a real elapsed window.
        if (
            self._energy_validation_calls <= WARMUP_READS
            or self._daily_energy_change_monotonic is None
        ):
            if self._daily_energy_change_monotonic is None:
                self._daily_energy_change_monotonic = time.monotonic()
            return validate_daily_energy_bounds(
                curr_values=curr_values,
                device_id=self.serial_number,
                rated_power_kw=self._rated_power_kw,
                elapsed_seconds=None,
                prev_values=None,
            )

        # Compute elapsed from last value change, not last read.
        elapsed = time.monotonic() - self._daily_energy_change_monotonic

        valid = validate_daily_energy_bounds(
            curr_values=curr_values,
            device_id=self.serial_number,
            rated_power_kw=self._rated_power_kw,
            elapsed_seconds=elapsed,
            prev_values=prev_values,
        )

        if valid and prev_values is not None:
            # Update change time only when a daily value actually increased.
            for key, curr in curr_values.items():
                if curr is None:
                    continue
                prev = prev_values.get(key)
                if prev is not None and curr > prev:
                    self._daily_energy_change_monotonic = time.monotonic()
                    break

        return valid

    @abstractmethod
    async def refresh(self) -> None:
        """Refresh device data from API.

        Subclasses must implement this to load/reload device-specific data.
        Should update self._last_refresh on success.
        """
        ...

    @abstractmethod
    def to_device_info(self) -> DeviceInfo:
        """Convert device to generic device info model.

        Returns:
            DeviceInfo instance with device metadata.
        """
        ...

    @abstractmethod
    def to_entities(self) -> list[Entity]:
        """Generate entities for this device.

        Returns:
            List of Entity instances (sensors, switches, etc.)
        """
        ...
