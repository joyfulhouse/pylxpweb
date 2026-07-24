"""Wiring tests for the #479 outage catch-up widening (eg4_web_monitor#479).

TestLifetimeCatchupWidening (test_validation.py) covers the isolated
BaseDevice logic; these tests pin the integration points — the arming
triggers and a commit site — so a refactor cannot silently detach them.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.base import TRANSPORT_LINK_DOWN_THRESHOLD
from pylxpweb.devices.inverters.base import BaseInverter
from pylxpweb.devices.mid_device import MIDDevice
from pylxpweb.devices.models import Entity
from pylxpweb.models import EnergyInfo, InverterRuntime, MidboxRuntime


class ConcreteInverter(BaseInverter):
    """Concrete implementation for testing."""

    def to_entities(self) -> list[Entity]:
        return []


@pytest.fixture
def mock_client() -> LuxpowerClient:
    client = Mock(spec=LuxpowerClient)
    client.api = Mock()
    client.api.devices = Mock()
    client.api.control = Mock()
    return client


def _runtime(*, lost: bool) -> InverterRuntime:
    return InverterRuntime.model_construct(
        success=True,
        serialNum="1234567890",
        statusText="offline" if lost else "normal",
        lost=lost,
        fwCode="TEST-1.0",
    )


def _energy(total_yielding_raw: int) -> EnergyInfo:
    """EnergyInfo with a controllable pv lifetime counter (raw 0.1 kWh)."""
    return EnergyInfo(
        success=True,
        serialNum="1234567890",
        soc=75,
        todayYielding=100,
        todayCharging=50,
        todayDischarging=40,
        todayImport=20,
        todayExport=10,
        todayUsage=80,
        totalYielding=total_yielding_raw,
        totalCharging=500000,
        totalDischarging=400000,
        totalImport=200000,
        totalExport=100000,
        totalUsage=800000,
    )


class TestArmingTriggers:
    """The two outage-evidence triggers must arm _energy_source_stale."""

    @pytest.mark.asyncio
    async def test_lost_cloud_runtime_arms_stale(self, mock_client) -> None:
        inverter = ConcreteInverter(mock_client, "1234567890", "TestModel")
        mock_client.api.devices.get_inverter_runtime = AsyncMock(return_value=_runtime(lost=True))
        assert inverter._energy_source_stale is False
        await inverter._fetch_runtime_http()
        assert inverter._energy_source_stale is True

    @pytest.mark.asyncio
    async def test_online_cloud_runtime_does_not_arm(self, mock_client) -> None:
        inverter = ConcreteInverter(mock_client, "1234567890", "TestModel")
        mock_client.api.devices.get_inverter_runtime = AsyncMock(return_value=_runtime(lost=False))
        await inverter._fetch_runtime_http()
        assert inverter._energy_source_stale is False

    def test_link_down_transition_arms_stale(self, mock_client) -> None:
        inverter = ConcreteInverter(mock_client, "1234567890", "TestModel")
        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD):
            inverter._record_transport_read_failure()
        assert inverter.transport_link_down is True
        assert inverter._energy_source_stale is True

    def test_single_transport_failure_does_not_arm(self, mock_client) -> None:
        """Transient blips deliberately fall back to the 5-strike self-heal."""
        inverter = ConcreteInverter(mock_client, "1234567890", "TestModel")
        inverter._record_transport_read_failure()
        assert inverter._energy_source_stale is False

    @pytest.mark.asyncio
    async def test_lost_midbox_runtime_arms_stale(self, mock_client) -> None:
        mid = MIDDevice(mock_client, "0987654321", "GridBOSS")
        runtime = MidboxRuntime.model_construct(
            success=True,
            serialNum="0987654321",
            fwCode="TEST-1.0",
            lost=True,
            midboxData=Mock(),
        )
        mock_client.api.devices.get_midbox_runtime = AsyncMock(return_value=runtime)
        assert mid._energy_source_stale is False
        # from_http_response on the Mock midboxData raises inside the guarded
        # try — the arming must already have happened before conversion.
        await mid._refresh_via_http()
        assert mid._energy_source_stale is True


class TestCommitSiteEndToEnd:
    """Outage → reconnect through the real _fetch_energy_http path."""

    @pytest.mark.asyncio
    async def test_catchup_delta_accepted_on_reconnect(self, mock_client) -> None:
        """The #479 log line, end to end: 4188.0 -> 4215.7 with 15 kWh cap."""
        inverter = ConcreteInverter(mock_client, "1234567890", "TestModel")
        inverter._max_energy_delta = 15.0

        baseline = _energy(41880)  # 4188.0 kWh
        mock_client.api.devices.get_inverter_energy = AsyncMock(return_value=baseline)
        await inverter._fetch_energy_http()
        assert inverter._energy is baseline

        # 5h cloud outage: lost runtime arms the evidence; the counters sat
        # frozen so the change window is 5h old.
        mock_client.api.devices.get_inverter_runtime = AsyncMock(return_value=_runtime(lost=True))
        await inverter._fetch_runtime_http()
        inverter._lifetime_energy_change_monotonic = time.monotonic() - 5 * 3600

        # Reconnect: +27.7 kWh catch-up accepted on the FIRST read.
        recovery = _energy(42157)  # 4215.7 kWh
        inverter._energy_cache_time = None  # bypass fetch throttle
        mock_client.api.devices.get_inverter_energy = AsyncMock(return_value=recovery)
        await inverter._fetch_energy_http()
        assert inverter._energy is recovery
        assert inverter._energy_reject_count == 0
        # The commit disarmed the evidence and re-armed the window.
        assert inverter._energy_source_stale is False

    @pytest.mark.asyncio
    async def test_same_delta_without_evidence_rejected(self, mock_client) -> None:
        """Control: no outage evidence → the tight cap still rejects 27.7."""
        inverter = ConcreteInverter(mock_client, "1234567890", "TestModel")
        inverter._max_energy_delta = 15.0

        baseline = _energy(41880)
        mock_client.api.devices.get_inverter_energy = AsyncMock(return_value=baseline)
        await inverter._fetch_energy_http()

        inverter._lifetime_energy_change_monotonic = time.monotonic() - 5 * 3600
        spike = _energy(42157)
        inverter._energy_cache_time = None
        mock_client.api.devices.get_inverter_energy = AsyncMock(return_value=spike)
        await inverter._fetch_energy_http()
        assert inverter._energy is baseline  # cached data kept
        assert inverter._energy_reject_count == 1
