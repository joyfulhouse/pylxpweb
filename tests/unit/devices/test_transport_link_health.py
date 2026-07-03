"""Unit tests for transport link health tracking (eg4-57g / integration #226).

When a local transport (Modbus TCP / WiFi dongle) is attached but the link
dies mid-run, device refreshes used to fail silently (debug-logged) and keep
serving cached transport data forever.  These tests cover the consecutive
failure counter, the link-down threshold, the clear-on-transition behavior,
the degraded HTTP fallback (hybrid), and recovery on both BaseInverter and
MIDDevice.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.base import (
    LINK_PROBE_MIN_INTERVAL_SECONDS,
    TRANSPORT_LINK_DOWN_THRESHOLD,
)
from pylxpweb.devices.inverters.generic import GenericInverter
from pylxpweb.devices.mid_device import MIDDevice
from pylxpweb.models import EnergyInfo, InverterRuntime, MidboxRuntime
from pylxpweb.transports.data import (
    BatteryBankData,
    InverterEnergyData,
    InverterRuntimeData,
)

_SAMPLES = Path(__file__).parent


def _make_inverter(client: LuxpowerClient | None = None) -> GenericInverter:
    """Create a GenericInverter (local-only when client is None)."""
    return GenericInverter(client=client, serial_number="1234567890", model="TestModel")


def _make_combined_data() -> tuple[Mock, Mock, Mock]:
    """Create mock (runtime, energy, battery) for read_all_input_data."""
    runtime = Mock(spec=InverterRuntimeData)
    energy = Mock(spec=InverterEnergyData)
    energy.lifetime_energy_values.return_value = {}
    energy.daily_energy_values.return_value = {}
    battery = Mock(spec=BatteryBankData)
    battery.battery_count = 0
    return runtime, energy, battery


def _attach_failing_combined_transport(inverter: GenericInverter) -> AsyncMock:
    """Attach a transport whose reads always fail.

    Both the combined read (used while the link is healthy, to trip the
    counter down) and the runtime probe (the single cheap read used once the
    link is down) fail, so the failure counter keeps climbing through both the
    trip-down and the degraded-probe phases.
    """
    transport = AsyncMock()
    transport.read_all_input_data = AsyncMock(side_effect=OSError("link dead"))
    transport.read_runtime = AsyncMock(side_effect=OSError("link dead"))
    inverter._transport = transport
    return transport


@pytest.fixture
def mock_client() -> LuxpowerClient:
    """Create a mock cloud client with credentials (hybrid mode)."""
    client = Mock(spec=LuxpowerClient)
    client.username = "user@example.com"
    client.api = Mock()
    client.api.devices = Mock()
    return client


@pytest.fixture
def sample_runtime() -> InverterRuntime:
    """Load sample HTTP runtime data."""
    with open(_SAMPLES / "inverters" / "samples" / "runtime_44300E0585.json") as f:
        return InverterRuntime.model_validate(json.load(f))


@pytest.fixture
def sample_energy() -> EnergyInfo:
    """Create sample HTTP energy data."""
    return EnergyInfo(
        success=True,
        serialNum="1234567890",
        soc=85,
        todayYielding=255,
        todayCharging=100,
        todayDischarging=80,
        todayImport=50,
        todayExport=30,
        todayUsage=150,
        totalYielding=50000,
        totalCharging=20000,
        totalDischarging=18000,
        totalImport=10000,
        totalExport=8000,
        totalUsage=30000,
    )


@pytest.fixture
def sample_midbox_runtime() -> MidboxRuntime:
    """Load sample midbox runtime data."""
    with open(_SAMPLES / "mid" / "samples" / "midbox_4524850115.json") as f:
        return MidboxRuntime.model_validate(json.load(f))


class TestInverterFailureCounter:
    """Failure counter / threshold semantics on BaseInverter."""

    @pytest.mark.asyncio
    async def test_combined_read_failures_trip_threshold(self) -> None:
        """N consecutive combined-read failures declare the link down."""
        inverter = _make_inverter()
        _attach_failing_combined_transport(inverter)

        for i in range(TRANSPORT_LINK_DOWN_THRESHOLD):
            assert inverter.transport_link_down is False
            await inverter.refresh(force=True)
            assert inverter.transport_consecutive_failures == i + 1

        assert inverter.transport_link_down is True

    @pytest.mark.asyncio
    async def test_below_threshold_keeps_cached_transport_data(self) -> None:
        """Failures below the threshold do NOT clear cached transport data."""
        inverter = _make_inverter()
        runtime, energy, battery = _make_combined_data()
        transport = AsyncMock()
        transport.read_all_input_data = AsyncMock(return_value=(runtime, energy, battery))
        inverter._transport = transport

        await inverter.refresh(force=True)
        assert inverter._transport_runtime is runtime

        transport.read_all_input_data.side_effect = OSError("blip")
        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD - 1):
            await inverter.refresh(force=True)

        # Transient blips: stale-but-recent cache still served
        assert inverter.transport_link_down is False
        assert inverter._transport_runtime is runtime

    @pytest.mark.asyncio
    async def test_transition_clears_transport_data(self) -> None:
        """Crossing the threshold clears runtime/energy/battery caches."""
        inverter = _make_inverter()
        runtime, energy, battery = _make_combined_data()
        battery.battery_count = 2
        transport = AsyncMock()
        transport.read_all_input_data = AsyncMock(return_value=(runtime, energy, battery))
        inverter._transport = transport

        await inverter.refresh(force=True)
        assert inverter._transport_runtime is runtime
        assert inverter._transport_energy is energy
        assert inverter._transport_battery is battery

        transport.read_all_input_data.side_effect = OSError("link dead")
        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD):
            await inverter.refresh(force=True)

        assert inverter.transport_link_down is True
        assert inverter._transport_runtime is None
        assert inverter._transport_energy is None
        assert inverter._transport_battery is None

    @pytest.mark.asyncio
    async def test_success_resets_counter_before_threshold(self) -> None:
        """A successful read wipes accumulated failures."""
        inverter = _make_inverter()
        runtime, energy, battery = _make_combined_data()
        transport = AsyncMock()
        transport.read_all_input_data = AsyncMock(side_effect=OSError("blip"))
        inverter._transport = transport

        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD - 1):
            await inverter.refresh(force=True)
        assert inverter.transport_consecutive_failures == TRANSPORT_LINK_DOWN_THRESHOLD - 1

        transport.read_all_input_data.side_effect = None
        transport.read_all_input_data.return_value = (runtime, energy, battery)
        await inverter.refresh(force=True)

        assert inverter.transport_consecutive_failures == 0
        assert inverter.transport_link_down is False

    @pytest.mark.asyncio
    async def test_recovery_repopulates_transport_data(self) -> None:
        """Recovery is detected by the cheap runtime probe; the next healthy
        refresh repopulates energy/battery via the combined read."""
        inverter = _make_inverter()
        transport = _attach_failing_combined_transport(inverter)

        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD):
            await inverter.refresh(force=True)
        assert inverter.transport_link_down is True

        runtime, energy, battery = _make_combined_data()
        # While down, only the runtime probe runs — recovery is detected there.
        transport.read_runtime.side_effect = None
        transport.read_runtime.return_value = runtime
        await inverter.refresh(force=True)
        assert inverter.transport_link_down is False
        assert inverter._transport_runtime is runtime

        # Link healthy again: the combined read resumes and repopulates energy.
        transport.read_all_input_data.side_effect = None
        transport.read_all_input_data.return_value = (runtime, energy, battery)
        await inverter.refresh(force=True)
        assert inverter._transport_energy is energy

    @pytest.mark.asyncio
    async def test_individual_read_path_tracks_failures(self) -> None:
        """Transports without combined read still feed the counter."""
        inverter = _make_inverter()
        transport = AsyncMock(spec=["read_runtime", "read_energy", "read_battery"])
        transport.read_runtime = AsyncMock(side_effect=OSError("dead"))
        transport.read_energy = AsyncMock(side_effect=OSError("dead"))
        transport.read_battery = AsyncMock(side_effect=OSError("dead"))
        inverter._transport = transport

        # One refresh = 3 failed reads (runtime + energy + battery), so a
        # single fully-failed cycle already crosses the threshold.
        await inverter.refresh(force=True)

        assert inverter.transport_consecutive_failures >= TRANSPORT_LINK_DOWN_THRESHOLD
        assert inverter.transport_link_down is True

    @pytest.mark.asyncio
    async def test_same_tick_duplicate_refresh_collapses_to_one_probe(self) -> None:
        """While down, probes rate-limit to one per LINK_PROBE_MIN_INTERVAL_SECONDS.

        Coordinator paths call refresh() twice per tick (group refresh +
        device processing); without the throttle each call would hit the
        dead transport (review MEDIUM).  After the interval elapses (the
        next real coordinator tick) the probe fires again.
        """
        inverter = _make_inverter()
        transport = _attach_failing_combined_transport(inverter)

        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD):
            await inverter.refresh(force=True)
        assert inverter.transport_link_down is True
        # While down the probe is the cheap runtime read, never the full
        # combined read (Bug 2 fix).
        combined_after_down = transport.read_all_input_data.await_count
        probe_calls = transport.read_runtime.await_count

        # First post-down refresh probes (no force, no expired cache needed)
        await inverter.refresh()
        assert transport.read_runtime.await_count == probe_calls + 1
        assert transport.read_all_input_data.await_count == combined_after_down

        # Same-tick duplicates collapse — no second dead-link read, even
        # with force=True (force cannot exceed the probe rate while down).
        await inverter.refresh()
        await inverter.refresh(force=True)
        assert transport.read_runtime.await_count == probe_calls + 1

        # Next coordinator tick (interval elapsed): probes again.
        inverter._last_link_probe_monotonic = time.monotonic() - LINK_PROBE_MIN_INTERVAL_SECONDS
        await inverter.refresh()
        assert transport.read_runtime.await_count == probe_calls + 2
        assert transport.read_all_input_data.await_count == combined_after_down

    @pytest.mark.asyncio
    async def test_probe_throttle_resets_on_recovery(self) -> None:
        """A successful read clears the probe stamp so a future outage
        probes immediately on its first post-transition cycle."""
        inverter = _make_inverter()
        transport = _attach_failing_combined_transport(inverter)

        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD):
            await inverter.refresh(force=True)
        await inverter.refresh()  # engages the probe gate
        assert inverter._last_link_probe_monotonic is not None

        runtime, _energy, _battery = _make_combined_data()
        # Recovery is detected by the runtime probe while the link is down.
        transport.read_runtime.side_effect = None
        transport.read_runtime.return_value = runtime
        inverter._last_link_probe_monotonic = time.monotonic() - LINK_PROBE_MIN_INTERVAL_SECONDS
        await inverter.refresh()

        assert inverter.transport_link_down is False
        assert inverter._last_link_probe_monotonic is None

    @pytest.mark.asyncio
    async def test_link_down_probe_skips_combined_read(self) -> None:
        """Bug 2: while down, the probe is a single runtime read.

        Even when the transport exposes ``read_all_input_data``, the link-down
        probe must NOT run the full combined input read — it issues only the
        cheap runtime read, and link recovery is still detected from it.
        """
        inverter = _make_inverter()
        transport = _attach_failing_combined_transport(inverter)

        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD):
            await inverter.refresh(force=True)
        assert inverter.transport_link_down is True
        combined_after_down = transport.read_all_input_data.await_count

        # Probe recovers via the runtime read; the combined read is untouched.
        runtime, _energy, _battery = _make_combined_data()
        transport.read_runtime.side_effect = None
        transport.read_runtime.return_value = runtime
        await inverter.refresh(force=True)

        transport.read_runtime.assert_awaited()
        assert transport.read_all_input_data.await_count == combined_after_down
        assert inverter.transport_link_down is False

    @pytest.mark.asyncio
    async def test_cloud_only_device_never_link_down(self, mock_client: LuxpowerClient) -> None:
        """HTTP failures on cloud-only devices never touch the counter."""
        inverter = _make_inverter(client=mock_client)
        mock_client.api.devices.get_inverter_runtime = AsyncMock(side_effect=OSError("API down"))
        mock_client.api.devices.get_inverter_energy = AsyncMock(side_effect=OSError("API down"))
        mock_client.api.devices.get_battery_info = AsyncMock(side_effect=OSError("API down"))

        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD + 1):
            await inverter.refresh(force=True)

        assert inverter.transport_consecutive_failures == 0
        assert inverter.transport_link_down is False


class TestInverterLinkDownLogging:
    """One-shot warning on transition, one-shot info on recovery."""

    @pytest.mark.asyncio
    async def test_single_warning_and_single_info(self, caplog: pytest.LogCaptureFixture) -> None:
        """The transition warns once; extra failures stay at debug; recovery infos once."""
        inverter = _make_inverter()
        transport = _attach_failing_combined_transport(inverter)

        with caplog.at_level(logging.DEBUG, logger="pylxpweb.devices.base"):
            # Two cycles past the threshold — still only ONE warning
            for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD + 2):
                await inverter.refresh(force=True)

            warnings = [
                r
                for r in caplog.records
                if r.levelno == logging.WARNING and "link down" in r.getMessage()
            ]
            assert len(warnings) == 1

            runtime, _energy, _battery = _make_combined_data()
            # Recovery is detected by the runtime probe while down.
            transport.read_runtime.side_effect = None
            transport.read_runtime.return_value = runtime
            # Age the probe gate: recovery happens on a later coordinator
            # tick, not within the same-tick throttle window.
            inverter._last_link_probe_monotonic = time.monotonic() - LINK_PROBE_MIN_INTERVAL_SECONDS
            await inverter.refresh(force=True)
            await inverter.refresh(force=True)

            infos = [
                r
                for r in caplog.records
                if r.levelno == logging.INFO and "link restored" in r.getMessage()
            ]
            assert len(infos) == 1

    @pytest.mark.asyncio
    async def test_per_failure_logs_stay_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        """Individual read failures log at debug, not warning."""
        inverter = _make_inverter()
        _attach_failing_combined_transport(inverter)

        with caplog.at_level(logging.DEBUG):
            await inverter.refresh(force=True)  # first failure — below threshold

        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


class TestInverterHttpFallback:
    """Degraded cloud fallback while the link is down (hybrid mode)."""

    @pytest.mark.asyncio
    async def test_http_fallback_when_link_down(
        self,
        mock_client: LuxpowerClient,
        sample_runtime: InverterRuntime,
        sample_energy: EnergyInfo,
    ) -> None:
        """Once down, refresh() probes the transport AND fetches cloud data."""
        inverter = _make_inverter(client=mock_client)
        transport = _attach_failing_combined_transport(inverter)
        mock_client.api.devices.get_inverter_runtime = AsyncMock(return_value=sample_runtime)
        mock_client.api.devices.get_inverter_energy = AsyncMock(return_value=sample_energy)
        mock_client.api.devices.get_battery_info = AsyncMock(side_effect=OSError("no batteries"))

        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD):
            await inverter.refresh(force=True)
        assert inverter.transport_link_down is True

        # The transition cycle itself already ran the fallback
        assert inverter._runtime is sample_runtime
        assert inverter._energy is sample_energy
        # Transport data cleared -> properties now serve the HTTP values
        assert inverter._transport_runtime is None

        # Next cycle: probe still attempted, fallback keeps fetching.  The
        # probe is the single cheap runtime read, not the full combined read
        # (Bug 2 fix) — degraded-HYBRID polls must not spend the extra
        # local read/timeout work before the cloud fallback runs.
        combined_after_down = transport.read_all_input_data.await_count
        probe_calls = transport.read_runtime.await_count
        await inverter.refresh()
        assert transport.read_runtime.await_count == probe_calls + 1
        assert transport.read_all_input_data.await_count == combined_after_down
        assert mock_client.api.devices.get_inverter_runtime.await_count >= 2

    @pytest.mark.asyncio
    async def test_no_http_fallback_without_credentials(self) -> None:
        """Local-only devices (client=None) cannot fall back to cloud."""
        inverter = _make_inverter(client=None)
        _attach_failing_combined_transport(inverter)

        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD + 1):
            await inverter.refresh(force=True)

        assert inverter.transport_link_down is True
        assert inverter._runtime is None
        assert inverter._transport_runtime is None

    @pytest.mark.asyncio
    async def test_no_fallback_while_link_healthy(self, mock_client: LuxpowerClient) -> None:
        """Healthy local link never triggers cloud runtime/energy fetches."""
        inverter = _make_inverter(client=mock_client)
        runtime, energy, battery = _make_combined_data()
        transport = AsyncMock()
        transport.read_all_input_data = AsyncMock(return_value=(runtime, energy, battery))
        inverter._transport = transport
        mock_client.api.devices.get_inverter_runtime = AsyncMock()
        mock_client.api.devices.get_inverter_energy = AsyncMock()

        await inverter.refresh(force=True)

        mock_client.api.devices.get_inverter_runtime.assert_not_awaited()
        mock_client.api.devices.get_inverter_energy.assert_not_awaited()


class TestHybridSupplementalRuntime:
    """Cloud-only smart-load fields stay fresh in healthy hybrid (GH #222).

    The EG4 Off-Grid smart-load split (smartLoadPower/gridLoadPower) exists
    only in the cloud runtime.  With a healthy transport the regular refresh
    paths never touch ``_runtime``, so refresh() schedules a supplemental
    ``_fetch_runtime_http()`` for EG4_OFFGRID devices — and ONLY for them —
    riding the runtime TTL (cloud call rate == pure-cloud mode).
    """

    @staticmethod
    def _healthy_transport(inverter: GenericInverter) -> AsyncMock:
        runtime, energy, battery = _make_combined_data()
        transport = AsyncMock()
        transport.read_all_input_data = AsyncMock(return_value=(runtime, energy, battery))
        inverter._transport = transport
        return transport

    @staticmethod
    def _offgrid_features():
        from pylxpweb.devices.inverters._features import InverterFeatures

        return InverterFeatures.from_device_type_code(38)  # 6000XP variant

    @pytest.mark.asyncio
    async def test_offgrid_healthy_hybrid_refreshes_cloud_runtime(
        self, mock_client: LuxpowerClient, sample_runtime: InverterRuntime
    ) -> None:
        """OFFGRID + healthy transport + credentials → cloud runtime refreshed.

        This is the reporter's configuration (6000XP, dongle, HYBRID): without
        the supplemental fetch the smart-load sensors freeze at the setup-time
        cloud snapshot (codex review HIGH on eg4-1d0).
        """
        inverter = _make_inverter(client=mock_client)
        inverter._features = self._offgrid_features()
        transport = self._healthy_transport(inverter)
        mock_client.api.devices.get_inverter_runtime = AsyncMock(return_value=sample_runtime)

        await inverter.refresh(force=True)

        transport.read_all_input_data.assert_awaited()  # local read still primary
        mock_client.api.devices.get_inverter_runtime.assert_awaited_once()
        assert inverter._runtime is sample_runtime
        assert inverter.transport_link_down is False

    @pytest.mark.asyncio
    async def test_non_offgrid_family_stays_purely_local(self, mock_client: LuxpowerClient) -> None:
        """EG4_HYBRID family has no cloud-only live fields → no cloud call."""
        from pylxpweb.devices.inverters._features import InverterFeatures

        inverter = _make_inverter(client=mock_client)
        inverter._features = InverterFeatures.from_device_type_code(2092)
        self._healthy_transport(inverter)
        mock_client.api.devices.get_inverter_runtime = AsyncMock()

        await inverter.refresh(force=True)

        mock_client.api.devices.get_inverter_runtime.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_family_stays_purely_local(self, mock_client: LuxpowerClient) -> None:
        """No detected features → conservative: no supplemental cloud call."""
        inverter = _make_inverter(client=mock_client)
        self._healthy_transport(inverter)
        mock_client.api.devices.get_inverter_runtime = AsyncMock()

        await inverter.refresh(force=True)

        mock_client.api.devices.get_inverter_runtime.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_offgrid_local_only_makes_no_cloud_call(self) -> None:
        """OFFGRID without credentials (pure LOCAL) cannot fetch cloud data."""
        inverter = _make_inverter(client=None)
        inverter._features = self._offgrid_features()
        self._healthy_transport(inverter)

        await inverter.refresh(force=True)

        assert inverter._runtime is None  # nothing fetched, nothing raised

    @pytest.mark.asyncio
    async def test_transition_cycle_fetches_cloud_runtime_once(
        self, mock_client: LuxpowerClient, sample_runtime: InverterRuntime
    ) -> None:
        """The link-down TRANSITION cycle must not double-fetch the runtime.

        Entry state: link still healthy (threshold-1 failures) → the
        supplemental fetch is scheduled.  The transport read fails and
        crosses the threshold during the same cycle → the post-read
        fallback fires; it must skip the runtime leg the supplemental
        already performed (codex r2 MEDIUM on eg4-1d0).
        """
        inverter = _make_inverter(client=mock_client)
        inverter._features = self._offgrid_features()
        _attach_failing_combined_transport(inverter)
        mock_client.api.devices.get_inverter_runtime = AsyncMock(return_value=sample_runtime)
        mock_client.api.devices.get_inverter_energy = AsyncMock(side_effect=OSError("cloud"))
        mock_client.api.devices.get_battery_info = AsyncMock(side_effect=OSError("cloud"))

        inverter._transport_consecutive_failures = TRANSPORT_LINK_DOWN_THRESHOLD - 1

        await inverter.refresh(force=True)

        assert inverter.transport_link_down is True
        mock_client.api.devices.get_inverter_runtime.assert_awaited_once()
        assert inverter._runtime is sample_runtime
        # Energy/battery fallback legs still ran on the transition cycle
        mock_client.api.devices.get_inverter_energy.assert_awaited_once()
        mock_client.api.devices.get_battery_info.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_offgrid_rides_runtime_ttl_not_every_call(
        self, mock_client: LuxpowerClient, sample_runtime: InverterRuntime
    ) -> None:
        """Within the runtime TTL a second refresh() makes no extra call."""
        inverter = _make_inverter(client=mock_client)
        inverter._features = self._offgrid_features()
        self._healthy_transport(inverter)
        mock_client.api.devices.get_inverter_runtime = AsyncMock(return_value=sample_runtime)

        await inverter.refresh(force=True)
        await inverter.refresh()  # cache fresh → runtime_expired False

        mock_client.api.devices.get_inverter_runtime.assert_awaited_once()


class TestHybridSupplementalBattery:
    """Cloud batteries the local registers never surface stay fresh in hybrid (#258).

    Some firmware pins <=4 batteries to the 4 Modbus slots and never rotates the
    rest into view, so a healthy transport-only refresh freezes the extra
    batteries at their setup-time cloud snapshot.  refresh() schedules a
    supplemental ``_fetch_battery_http()`` ONLY when the cloud reports more
    batteries than the transport surfaces, riding the battery TTL on a dedicated
    clock (the combined read keeps ``_battery_cache_time`` fresh on its own).
    """

    @staticmethod
    def _healthy_transport(inverter: GenericInverter) -> AsyncMock:
        runtime, energy, battery = _make_combined_data()
        transport = AsyncMock()
        transport.read_all_input_data = AsyncMock(return_value=(runtime, energy, battery))
        inverter._transport = transport
        return transport

    @staticmethod
    def _seed_battery_state(inverter: GenericInverter, *, cloud_count: int, surfaced: int) -> None:
        """Seed cloud ``_battery_bank`` and the live ``_transport_battery`` slots."""
        bank = Mock()
        bank.battery_count = cloud_count
        inverter._battery_bank = bank
        # In-slot batteries are stamped together each read, so they share a
        # fresh last_seen (the never-evict frozen-battery case is covered by its
        # own test).  Relative to now: the gate also has an absolute-staleness
        # backstop that must not trip for genuinely fresh batteries.
        stamp = datetime.now(UTC)
        transport_battery = Mock(spec=BatteryBankData)
        transport_battery.batteries = [
            Mock(voltage=53.0, soc=80, last_seen=stamp) for _ in range(surfaced)
        ]
        inverter._transport_battery = transport_battery

    @pytest.mark.asyncio
    async def test_cloud_more_than_transport_refreshes_cloud_battery(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Cloud reports 5, transport surfaces 4 → supplemental cloud battery fetch.

        This is the #258 reporter's case (18kPV, dongle, HYBRID): the firmware
        pins 4 batteries to the slots and never rotates the 5th in, so without
        this fetch the 5th freezes at its setup-time cloud snapshot.
        """
        inverter = _make_inverter(client=mock_client)
        self._healthy_transport(inverter)
        self._seed_battery_state(inverter, cloud_count=5, surfaced=4)
        inverter._fetch_battery_http = AsyncMock()  # type: ignore[method-assign]

        await inverter.refresh(force=True)

        inverter._fetch_battery_http.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_transport_surfaces_all_makes_no_cloud_battery_call(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Transport surfaces all 5 → no supplemental call (no frozen battery)."""
        inverter = _make_inverter(client=mock_client)
        self._healthy_transport(inverter)
        self._seed_battery_state(inverter, cloud_count=5, surfaced=5)
        inverter._fetch_battery_http = AsyncMock()  # type: ignore[method-assign]

        await inverter.refresh(force=True)

        inverter._fetch_battery_http.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_battery_bank_makes_no_cloud_battery_call(
        self, mock_client: LuxpowerClient
    ) -> None:
        """No cloud battery bank yet → nothing to supplement."""
        inverter = _make_inverter(client=mock_client)
        self._healthy_transport(inverter)
        inverter._battery_bank = None
        inverter._transport_battery = None
        inverter._fetch_battery_http = AsyncMock()  # type: ignore[method-assign]

        await inverter.refresh(force=True)

        inverter._fetch_battery_http.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_local_only_makes_no_cloud_battery_call(self) -> None:
        """Pure LOCAL (no client) cannot fetch cloud battery data."""
        inverter = _make_inverter(client=None)
        self._healthy_transport(inverter)
        self._seed_battery_state(inverter, cloud_count=5, surfaced=4)
        inverter._fetch_battery_http = AsyncMock()  # type: ignore[method-assign]

        await inverter.refresh(force=True)

        inverter._fetch_battery_http.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_frozen_cached_battery_does_not_count_as_surfaced(
        self, mock_client: LuxpowerClient
    ) -> None:
        """A never-evict frozen battery must not silence the supplement (#258 firestormo).

        Non-rotating firmware places battery 5 into a Modbus slot exactly once,
        then never again.  pylxpweb's accumulator never evicts, so it re-presents
        that frozen block forever with its stale ``last_seen``.  If the frozen
        block counted toward "surfaced", surfaced would equal cloud_count and the
        supplemental cloud fetch — the only thing keeping battery 5 live — would
        stop, freezing battery 5 at its last value (the observed regression).  A
        battery materially older than its freshest sibling was not refreshed this
        cycle and must not count as surfaced.
        """
        inverter = _make_inverter(client=mock_client)
        self._healthy_transport(inverter)

        bank = Mock()
        bank.battery_count = 5
        inverter._battery_bank = bank

        fresh = datetime.now(UTC)
        frozen = fresh - timedelta(minutes=5, seconds=11)  # ~5 min stale
        batteries = [Mock(voltage=53.0, soc=80, last_seen=fresh) for _ in range(4)]
        batteries.append(Mock(voltage=53.0, soc=80, last_seen=frozen))
        transport_battery = Mock(spec=BatteryBankData)
        transport_battery.batteries = batteries
        inverter._transport_battery = transport_battery
        inverter._fetch_battery_http = AsyncMock()  # type: ignore[method-assign]

        await inverter.refresh(force=True)

        inverter._fetch_battery_http.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rotating_system_fetches_cloud_for_lagging_batteries(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Rotating HYBRID >4-battery systems keep rotated-out batteries fresh via cloud.

        Only the (up to 4) batteries in this read's physical slots are co-stamped
        fresh; the rest lag by at least a rotation period.  In HYBRID those lagging
        batteries would otherwise drift, so the gate fires the supplemental cloud
        fetch whenever any battery lags the freshest sibling by more than the
        window.  (Real cloud traffic is bounded by the client's battery_info
        response cache; pure-LOCAL systems never reach here.)
        """
        inverter = _make_inverter(client=mock_client)
        self._healthy_transport(inverter)

        bank = Mock()
        bank.battery_count = 8
        inverter._battery_bank = bank

        fresh = datetime.now(UTC)
        lagging = fresh - timedelta(minutes=6, seconds=39)  # > 2 min behind
        batteries = [Mock(voltage=53.0, soc=80, last_seen=fresh) for _ in range(4)]
        batteries += [Mock(voltage=53.0, soc=80, last_seen=lagging) for _ in range(4)]
        transport_battery = Mock(spec=BatteryBankData)
        transport_battery.batteries = batteries
        inverter._transport_battery = transport_battery
        inverter._fetch_battery_http = AsyncMock()  # type: ignore[method-assign]

        await inverter.refresh(force=True)

        inverter._fetch_battery_http.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_all_batteries_co_frozen_still_fires_cloud_refresh(
        self, mock_client: LuxpowerClient
    ) -> None:
        """A fully frozen local battery feed must not silence the supplement (#258).

        When block reads fail for a stretch (or every page is pinned), ALL
        transport batteries share old, co-stamped ``last_seen`` values.  The
        relative check alone would call them all "surfaced" — the newest stamp
        IS the frozen stamp — silencing the cloud supplement during exactly the
        outage it exists for.  Nothing locally fresh means nothing is surfaced.
        """
        inverter = _make_inverter(client=mock_client)
        self._healthy_transport(inverter)

        bank = Mock()
        bank.battery_count = 8
        inverter._battery_bank = bank

        # All 8 co-stamped (within the relative window of each other) but the
        # whole feed is stale: newest stamp is ~10 minutes old — far past the
        # scaled backstop for the default 30 s TTL (max(2 min, 75 s) = 2 min).
        frozen = datetime.now(UTC) - timedelta(minutes=10)
        batteries = [Mock(voltage=53.0, soc=80, last_seen=frozen) for _ in range(8)]
        transport_battery = Mock(spec=BatteryBankData)
        transport_battery.batteries = batteries
        inverter._transport_battery = transport_battery
        inverter._fetch_battery_http = AsyncMock()  # type: ignore[method-assign]

        await inverter.refresh(force=True)

        inverter._fetch_battery_http.assert_awaited_once()

    @staticmethod
    def _stamped_transport(
        inverter: GenericInverter, *, count: int, frozen_stamp: datetime | None
    ) -> AsyncMock:
        """Attach a combined-read transport with controllable battery stamps.

        ``frozen_stamp=None`` re-stamps every battery ``now`` on each read (a
        healthy feed, as the real transport stamps in-page batteries); a fixed
        stamp models a frozen feed (pinned page / block reads served from the
        accumulator), where ``last_seen`` never advances.
        """

        def _combined(*_args: object, **_kwargs: object) -> tuple[Mock, Mock, Mock]:
            runtime, energy, battery = _make_combined_data()
            stamp = frozen_stamp if frozen_stamp is not None else datetime.now(UTC)
            battery.batteries = [Mock(voltage=53.0, soc=80, last_seen=stamp) for _ in range(count)]
            return runtime, energy, battery

        transport = AsyncMock()
        transport.read_all_input_data = AsyncMock(side_effect=_combined)
        inverter._transport = transport
        return transport

    def _seed_costamped_bank(
        self, inverter: GenericInverter, *, count: int, stamp: datetime
    ) -> None:
        """Seed the cloud bank and a previous-cycle transport battery snapshot."""
        bank = Mock()
        bank.battery_count = count
        inverter._battery_bank = bank
        seed = Mock(spec=BatteryBankData)
        seed.batteries = [Mock(voltage=53.0, soc=80, last_seen=stamp) for _ in range(count)]
        inverter._transport_battery = seed

    @pytest.mark.asyncio
    async def test_slow_poll_healthy_cycles_do_not_fire_supplemental(
        self, mock_client: LuxpowerClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A poll interval above the 2-min floor must NOT fire the supplement.

        The gate is evaluated while refresh() BUILDS its task list — BEFORE
        this cycle's transport read — so the newest ``last_seen`` is always
        ~one poll interval old at evaluation time.  A fixed absolute cutoff
        below the poll interval would therefore fire on EVERY healthy cycle
        (intervals are UI-configurable up to 300 s and the integration pins
        the battery cache TTL to them via set_cache_ttls) — a permanent,
        silent every-poll cloud fetch.  The backstop must scale with the TTL.

        Scaled-down clock: floor 0.2 s, TTL 0.4 s → threshold max(0.2 s,
        2.5 x 0.4 s) = 1.0 s.  The 0.5 s inter-cycle gap is one healthy
        "poll interval" that the unscaled floor (0.5 > 0.2) mistook for a
        frozen feed.  Two REAL refresh cycles across real elapsed gaps.
        """
        from pylxpweb.devices.inverters import base as base_module

        monkeypatch.setattr(
            base_module,
            "_SUPPLEMENTAL_BATTERY_STALE_AFTER",
            timedelta(seconds=0.2),
        )
        inverter = _make_inverter(client=mock_client)
        inverter.set_cache_ttls(battery=timedelta(seconds=0.4))
        self._stamped_transport(inverter, count=2, frozen_stamp=None)
        self._seed_costamped_bank(inverter, count=2, stamp=datetime.now(UTC))
        inverter._fetch_battery_http = AsyncMock()  # type: ignore[method-assign]

        await asyncio.sleep(0.5)  # one healthy poll interval elapses
        await inverter.refresh(force=True)
        await asyncio.sleep(0.5)  # next healthy interval
        await inverter.refresh(force=True)

        assert inverter._fetch_battery_http.await_count == 0

    @pytest.mark.asyncio
    async def test_slow_poll_co_frozen_feed_still_fires(
        self, mock_client: LuxpowerClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A feed frozen past the scaled threshold still fires the supplement.

        Same scaled clock as the healthy test (threshold 1.0 s), but the
        transport keeps serving batteries whose ``last_seen`` never advances
        (pinned page / accumulator-served failed reads).  Once the elapsed
        gap exceeds the scaled threshold, nothing counts as surfaced and the
        cloud supplement fires.
        """
        from pylxpweb.devices.inverters import base as base_module

        monkeypatch.setattr(
            base_module,
            "_SUPPLEMENTAL_BATTERY_STALE_AFTER",
            timedelta(seconds=0.2),
        )
        inverter = _make_inverter(client=mock_client)
        inverter.set_cache_ttls(battery=timedelta(seconds=0.4))
        frozen_stamp = datetime.now(UTC)
        self._stamped_transport(inverter, count=2, frozen_stamp=frozen_stamp)
        self._seed_costamped_bank(inverter, count=2, stamp=frozen_stamp)
        inverter._fetch_battery_http = AsyncMock()  # type: ignore[method-assign]

        await asyncio.sleep(1.1)  # beyond the 1.0 s scaled threshold
        await inverter.refresh(force=True)

        inverter._fetch_battery_http.assert_awaited_once()


class TestMIDDeviceLinkHealth:
    """Failure counter, fallback, and recovery on MIDDevice."""

    @staticmethod
    def _make_mid(client: LuxpowerClient | None = None) -> MIDDevice:
        return MIDDevice(client=client, serial_number="4524850115", model="GridBOSS")

    @staticmethod
    def _attach_failing_transport(mid: MIDDevice) -> AsyncMock:
        transport = AsyncMock(spec=["read_midbox_runtime"])
        transport.read_midbox_runtime = AsyncMock(side_effect=OSError("link dead"))
        mid._transport = transport
        return transport

    @pytest.mark.asyncio
    async def test_failures_trip_threshold_and_clear_runtime(self) -> None:
        """MID runtime fetch failures count up and clear cached data at the threshold."""
        mid = self._make_mid()
        from pylxpweb.transports.data import MidboxRuntimeData

        mid._transport_runtime = Mock(spec=MidboxRuntimeData)
        transport = self._attach_failing_transport(mid)

        for i in range(TRANSPORT_LINK_DOWN_THRESHOLD):
            await mid.refresh()
            assert mid.transport_consecutive_failures == i + 1

        assert mid.transport_link_down is True
        assert mid._transport_runtime is None
        assert transport.read_midbox_runtime.await_count == TRANSPORT_LINK_DOWN_THRESHOLD

    @pytest.mark.asyncio
    async def test_recovery_resets_counter_and_restores_data(self) -> None:
        """A successful probe after link-down resumes local data."""
        from pylxpweb.transports.data import MidboxRuntimeData

        mid = self._make_mid()
        transport = self._attach_failing_transport(mid)

        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD):
            await mid.refresh()
        assert mid.transport_link_down is True

        runtime = Mock(spec=MidboxRuntimeData)
        runtime.lifetime_energy_values.return_value = {}
        runtime.daily_energy_values.return_value = {}
        transport.read_midbox_runtime.side_effect = None
        transport.read_midbox_runtime.return_value = runtime
        await mid.refresh()

        assert mid.transport_link_down is False
        assert mid._transport_runtime is runtime

    @pytest.mark.asyncio
    async def test_http_fallback_when_down(
        self, mock_client: LuxpowerClient, sample_midbox_runtime: MidboxRuntime
    ) -> None:
        """A link-down MID with cloud credentials refreshes via HTTP."""
        mid = self._make_mid(client=mock_client)
        transport = self._attach_failing_transport(mid)
        mock_client.api.devices.get_midbox_runtime = AsyncMock(return_value=sample_midbox_runtime)

        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD):
            await mid.refresh()

        assert mid.transport_link_down is True
        # The transition cycle fell through to HTTP — data keeps moving
        assert mid._runtime is sample_midbox_runtime
        assert mid._transport_runtime is not None
        # And the transport probe keeps running on later cycles
        probe_calls = transport.read_midbox_runtime.await_count
        await mid.refresh()
        assert transport.read_midbox_runtime.await_count == probe_calls + 1
        assert mock_client.api.devices.get_midbox_runtime.await_count >= 2

    @pytest.mark.asyncio
    async def test_no_fallback_below_threshold(
        self, mock_client: LuxpowerClient, sample_midbox_runtime: MidboxRuntime
    ) -> None:
        """Transient blips below the threshold never hit the cloud."""
        mid = self._make_mid(client=mock_client)
        self._attach_failing_transport(mid)
        mock_client.api.devices.get_midbox_runtime = AsyncMock(return_value=sample_midbox_runtime)

        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD - 1):
            await mid.refresh()

        mock_client.api.devices.get_midbox_runtime.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_local_only_mid_no_fallback(self) -> None:
        """A local-only MID (client=None) goes data-less instead of crashing."""
        mid = self._make_mid(client=None)
        self._attach_failing_transport(mid)

        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD + 1):
            await mid.refresh()

        assert mid.transport_link_down is True
        assert mid._transport_runtime is None
        assert mid.has_data is False

    @pytest.mark.asyncio
    async def test_mid_same_tick_duplicate_skips_probe_keeps_fallback(
        self, mock_client: LuxpowerClient, sample_midbox_runtime: MidboxRuntime
    ) -> None:
        """Same-tick duplicate refresh while down: one dead-link probe per
        interval, but the HTTP fallback still serves data every call."""
        mid = self._make_mid(client=mock_client)
        transport = self._attach_failing_transport(mid)
        mock_client.api.devices.get_midbox_runtime = AsyncMock(return_value=sample_midbox_runtime)

        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD):
            await mid.refresh()
        assert mid.transport_link_down is True

        # First post-down refresh engages the probe gate
        await mid.refresh()
        probe_calls = transport.read_midbox_runtime.await_count
        http_calls = mock_client.api.devices.get_midbox_runtime.await_count

        # Same-tick duplicate: no dead-link read, HTTP fallback still runs
        await mid.refresh()
        assert transport.read_midbox_runtime.await_count == probe_calls
        assert mock_client.api.devices.get_midbox_runtime.await_count == http_calls + 1

        # Next coordinator tick (interval elapsed): probes again
        mid._last_link_probe_monotonic = time.monotonic() - LINK_PROBE_MIN_INTERVAL_SECONDS
        await mid.refresh()
        assert transport.read_midbox_runtime.await_count == probe_calls + 1
