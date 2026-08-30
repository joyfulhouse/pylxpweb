"""Unit tests for dead-link probe cost bounding (eg4_web_monitor#587 follow-up).

When a local transport endpoint goes deaf (TCP accepts, no response), every
coordinator refresh used to synchronously pay the transport's full read
timeout chain (10s dongle response timeout, up to ~30s Modbus retry chain)
as its link-down probe.  Home Assistant schedules the next poll as
``refresh_duration + interval``, so the user-visible poll interval degraded
toward ~30s.  Three fixes bound this cost:

1. The probe rate-limit window is measured from probe COMPLETION, not start,
   so a slow probe cannot expire its own window and let the same-tick
   duplicate refresh() probe again.
2. The probe interval backs off exponentially with consecutive failures
   (base x 2^(failures - threshold)), capped at LINK_PROBE_MAX_INTERVAL_SECONDS.
3. Devices probe via the transport's cheap single-attempt, short-timeout
   ``check_link()`` instead of a full data read, when the transport offers it.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

from pylxpweb.devices.base import (
    LINK_PROBE_MAX_INTERVAL_SECONDS,
    LINK_PROBE_MIN_INTERVAL_SECONDS,
    TRANSPORT_LINK_DOWN_THRESHOLD,
)
from pylxpweb.devices.inverters.generic import GenericInverter
from pylxpweb.devices.mid_device import MIDDevice


def _make_down_inverter(extra_failures: int = 0) -> GenericInverter:
    """Create a local-only inverter already past the link-down threshold."""
    inverter = GenericInverter(client=None, serial_number="1234567890", model="TestModel")
    inverter._transport = AsyncMock()
    inverter._transport_consecutive_failures = TRANSPORT_LINK_DOWN_THRESHOLD + extra_failures
    inverter._transport_link_down_logged = True
    return inverter


class TestProbeWindowCompletionStamp:
    """The rate-limit window must be measured from probe completion."""

    def test_failure_restamps_probe_window(self) -> None:
        """A probe that outlives its own window must not immediately re-arm.

        Simulates a slow probe: the start stamp is older than the window when
        the probe finally fails.  Recording the failure must re-stamp the
        clock so the same-tick duplicate refresh() sees the probe as NOT due.
        """
        inverter = _make_down_inverter()
        # Probe started long ago (longer than the base window)
        inverter._last_link_probe_monotonic = (
            time.monotonic() - LINK_PROBE_MIN_INTERVAL_SECONDS - 10.0
        )

        inverter._record_transport_read_failure()  # probe completes (failed)

        assert inverter._link_probe_due() is False

    def test_non_probe_failure_does_not_open_stamp(self) -> None:
        """Transition-refresh stragglers must not delay the first probe.

        On individual-read transports the energy/battery reads already in
        flight when the runtime read trips the threshold also fail while
        "down" — but no probe window was ever opened (stamp is None), so
        they must not stamp one and push the first recovery probe out
        (codex review MEDIUM).
        """
        inverter = _make_down_inverter()
        inverter._last_link_probe_monotonic = None

        inverter._record_transport_read_failure()  # straggler, not a probe

        assert inverter._last_link_probe_monotonic is None
        assert inverter._link_probe_due() is True

    def test_success_still_resets_stamp(self) -> None:
        """A successful read clears the stamp so a future outage probes at once."""
        inverter = _make_down_inverter()
        inverter._last_link_probe_monotonic = time.monotonic()

        inverter._record_transport_read_success()

        assert inverter._last_link_probe_monotonic is None


class TestProbeBackoff:
    """Probe interval grows exponentially with consecutive failures."""

    def test_interval_doubles_past_threshold(self) -> None:
        """At threshold+2 failures the window is base * 2^2."""
        inverter = _make_down_inverter(extra_failures=2)
        expected = LINK_PROBE_MIN_INTERVAL_SECONDS * 4

        inverter._last_link_probe_monotonic = time.monotonic() - (expected - 1.0)
        assert inverter._link_probe_due() is False

        inverter._last_link_probe_monotonic = time.monotonic() - (expected + 1.0)
        assert inverter._link_probe_due() is True

    def test_interval_capped(self) -> None:
        """Deep outages never push the probe interval past the cap."""
        inverter = _make_down_inverter(extra_failures=30)

        inverter._last_link_probe_monotonic = (
            time.monotonic() - LINK_PROBE_MAX_INTERVAL_SECONDS - 1.0
        )
        assert inverter._link_probe_due() is True

        inverter._last_link_probe_monotonic = (
            time.monotonic() - LINK_PROBE_MAX_INTERVAL_SECONDS + 2.0
        )
        assert inverter._link_probe_due() is False

    def test_base_interval_at_threshold(self) -> None:
        """Exactly at the threshold the window is the unscaled base."""
        inverter = _make_down_inverter(extra_failures=0)

        inverter._last_link_probe_monotonic = (
            time.monotonic() - LINK_PROBE_MIN_INTERVAL_SECONDS - 0.5
        )
        assert inverter._link_probe_due() is True


class TestMidCheapProbe:
    """MIDDevice probes via transport.check_link() when available."""

    @staticmethod
    def _make_down_mid(check_link_result: bool) -> tuple[MIDDevice, AsyncMock]:
        mid = MIDDevice(client=None, serial_number="4524850115", model="GridBOSS")
        transport = AsyncMock(spec=["read_midbox_runtime", "check_link"])
        transport.read_midbox_runtime = AsyncMock(side_effect=OSError("link dead"))
        transport.check_link = AsyncMock(return_value=check_link_result)
        mid._transport = transport
        mid._transport_consecutive_failures = TRANSPORT_LINK_DOWN_THRESHOLD
        mid._transport_link_down_logged = True
        return mid, transport

    @pytest.mark.asyncio
    async def test_failed_check_link_skips_full_read(self) -> None:
        """While down, a failed cheap probe must not run the full data read."""
        mid, transport = self._make_down_mid(check_link_result=False)

        await mid.refresh()

        transport.check_link.assert_awaited_once()
        transport.read_midbox_runtime.assert_not_awaited()
        assert mid.transport_consecutive_failures == TRANSPORT_LINK_DOWN_THRESHOLD + 1

    @pytest.mark.asyncio
    async def test_successful_check_link_runs_full_read(self) -> None:
        """A passing cheap probe falls through to the normal full read."""
        mid, transport = self._make_down_mid(check_link_result=True)

        await mid.refresh()

        transport.check_link.assert_awaited_once()
        transport.read_midbox_runtime.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failed_check_link_restamps_probe_window(self) -> None:
        """The failed cheap probe stamps completion — duplicate calls skip it."""
        mid, transport = self._make_down_mid(check_link_result=False)

        await mid.refresh()
        await mid.refresh()  # same-tick duplicate

        transport.check_link.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_transport_without_check_link_keeps_full_read_probe(self) -> None:
        """Transports lacking check_link keep the previous full-read probe."""
        mid = MIDDevice(client=None, serial_number="4524850115", model="GridBOSS")
        transport = AsyncMock(spec=["read_midbox_runtime"])
        transport.read_midbox_runtime = AsyncMock(side_effect=OSError("link dead"))
        mid._transport = transport
        mid._transport_consecutive_failures = TRANSPORT_LINK_DOWN_THRESHOLD
        mid._transport_link_down_logged = True

        await mid.refresh()

        transport.read_midbox_runtime.assert_awaited_once()


class TestInverterCheapProbe:
    """BaseInverter link-down probe uses transport.check_link() when available."""

    @staticmethod
    def _make_down_inverter_with_probe(
        check_link_result: bool,
    ) -> tuple[GenericInverter, AsyncMock]:
        inverter = GenericInverter(client=None, serial_number="1234567890", model="TestModel")
        transport = AsyncMock(spec=["read_runtime", "read_all_input_data", "check_link"])
        transport.read_runtime = AsyncMock(side_effect=OSError("link dead"))
        transport.read_all_input_data = AsyncMock(side_effect=OSError("link dead"))
        transport.check_link = AsyncMock(return_value=check_link_result)
        inverter._transport = transport
        inverter._transport_consecutive_failures = TRANSPORT_LINK_DOWN_THRESHOLD
        inverter._transport_link_down_logged = True
        return inverter, transport

    @pytest.mark.asyncio
    async def test_failed_check_link_skips_runtime_read(self) -> None:
        """While down, a failed cheap probe must not run the runtime read."""
        inverter, transport = self._make_down_inverter_with_probe(check_link_result=False)

        await inverter.refresh()

        transport.check_link.assert_awaited_once()
        transport.read_runtime.assert_not_awaited()
        transport.read_all_input_data.assert_not_awaited()
        assert inverter.transport_consecutive_failures == TRANSPORT_LINK_DOWN_THRESHOLD + 1

    @pytest.mark.asyncio
    async def test_successful_check_link_runs_runtime_probe(self) -> None:
        """A passing cheap probe falls through to the runtime probe read."""
        inverter, transport = self._make_down_inverter_with_probe(check_link_result=True)

        await inverter.refresh()

        transport.check_link.assert_awaited_once()
        transport.read_runtime.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failed_check_link_restamps_probe_window(self) -> None:
        """The failed cheap probe stamps completion — duplicate calls skip it."""
        inverter, transport = self._make_down_inverter_with_probe(check_link_result=False)

        await inverter.refresh()
        await inverter.refresh()  # same-tick duplicate

        transport.check_link.assert_awaited_once()
