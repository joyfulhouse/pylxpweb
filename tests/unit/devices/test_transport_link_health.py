"""Unit tests for transport link health tracking (eg4-57g / integration #226).

When a local transport (Modbus TCP / WiFi dongle) is attached but the link
dies mid-run, device refreshes used to fail silently (debug-logged) and keep
serving cached transport data forever.  These tests cover the consecutive
failure counter, the link-down threshold, the clear-on-transition behavior,
the degraded HTTP fallback (hybrid), and recovery on both BaseInverter and
MIDDevice.
"""

from __future__ import annotations

import json
import logging
import time
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
    """Attach a transport whose combined read always fails."""
    transport = AsyncMock()
    transport.read_all_input_data = AsyncMock(side_effect=OSError("link dead"))
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
        """A successful probe after link-down restores local data serving."""
        inverter = _make_inverter()
        transport = _attach_failing_combined_transport(inverter)

        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD):
            await inverter.refresh(force=True)
        assert inverter.transport_link_down is True

        runtime, energy, battery = _make_combined_data()
        transport.read_all_input_data.side_effect = None
        transport.read_all_input_data.return_value = (runtime, energy, battery)
        await inverter.refresh(force=True)

        assert inverter.transport_link_down is False
        assert inverter._transport_runtime is runtime
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
        calls_after_down = transport.read_all_input_data.await_count

        # First post-down refresh probes (no force, no expired cache needed)
        await inverter.refresh()
        assert transport.read_all_input_data.await_count == calls_after_down + 1

        # Same-tick duplicates collapse — no second dead-link read, even
        # with force=True (force cannot exceed the probe rate while down).
        await inverter.refresh()
        await inverter.refresh(force=True)
        assert transport.read_all_input_data.await_count == calls_after_down + 1

        # Next coordinator tick (interval elapsed): probes again.
        inverter._last_link_probe_monotonic = time.monotonic() - LINK_PROBE_MIN_INTERVAL_SECONDS
        await inverter.refresh()
        assert transport.read_all_input_data.await_count == calls_after_down + 2

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

        runtime, energy, battery = _make_combined_data()
        transport.read_all_input_data.side_effect = None
        transport.read_all_input_data.return_value = (runtime, energy, battery)
        inverter._last_link_probe_monotonic = time.monotonic() - LINK_PROBE_MIN_INTERVAL_SECONDS
        await inverter.refresh()

        assert inverter.transport_link_down is False
        assert inverter._last_link_probe_monotonic is None

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

            runtime, energy, battery = _make_combined_data()
            transport.read_all_input_data.side_effect = None
            transport.read_all_input_data.return_value = (runtime, energy, battery)
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

        # Next cycle: probe still attempted, fallback keeps fetching
        probe_calls = transport.read_all_input_data.await_count
        await inverter.refresh()
        assert transport.read_all_input_data.await_count == probe_calls + 1
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
