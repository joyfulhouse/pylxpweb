"""Tests for transport-aware (LOCAL/HYBRID) Quick Charge control.

The cloud path stays HTTP; with a local transport, Quick Charge is driven by
holding registers: reg 233 bit 0 (enable) and reg 234 (duration minutes, which
also reads as the live remaining-minutes countdown).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.inverters.base import BaseInverter
from pylxpweb.models import QuickChargeStatus, SuccessResponse


class _Inverter(BaseInverter):
    """Minimal concrete inverter for control-method tests."""

    def to_entities(self) -> list[Any]:
        return []


@pytest.fixture
def mock_client() -> LuxpowerClient:
    client = Mock(spec=LuxpowerClient)
    client.api = Mock()
    client.api.control = Mock()
    client.api.control.start_quick_charge = AsyncMock(return_value=SuccessResponse(success=True))
    client.api.control.stop_quick_charge = AsyncMock(return_value=SuccessResponse(success=True))
    client.api.control.get_quick_charge_status = AsyncMock(
        return_value=QuickChargeStatus(success=True, hasUnclosedQuickChargeTask=True)
    )
    return client


def _inverter(mock_client: LuxpowerClient, *, with_transport: bool) -> _Inverter:
    inv = _Inverter(client=mock_client, serial_number="1234567890", model="18kPV")
    if with_transport:
        transport = AsyncMock()
        transport.read_parameters = AsyncMock(return_value={233: 0})
        transport.write_parameters = AsyncMock(return_value=True)
        # Input reg 210 unavailable by default (older firmware / no value) so the
        # remaining time falls back to the holding-reg 234 derivation; tests that
        # exercise the seconds path override this.
        transport.read_quick_charge_remaining_seconds = AsyncMock(return_value=None)
        inv._transport = transport
    return inv


# ── LOCAL enable / disable ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_enable_local_with_minute_only_sets_bit_ignores_duration(mock_client):
    """LOCAL enable sets only reg 233 bit 0; the firmware rejects reg 234 writes
    while quick charge is off, so `minute` is ignored on the local path (the
    duration is adjusted live via set_quick_charge_minute afterwards)."""
    inv = _inverter(mock_client, with_transport=True)

    ok = await inv.enable_quick_charge(minute=30)

    assert ok is True
    writes = [c.args[0] for c in inv._transport.write_parameters.call_args_list]
    assert {233: 1} in writes  # enable bit set (RMW on 0x0000)
    assert all(234 not in w for w in writes)  # duration NOT pre-written
    mock_client.api.control.start_quick_charge.assert_not_called()


@pytest.mark.asyncio
async def test_enable_local_without_minute_only_sets_bit(mock_client):
    inv = _inverter(mock_client, with_transport=True)

    ok = await inv.enable_quick_charge()

    assert ok is True
    writes = [c.args[0] for c in inv._transport.write_parameters.call_args_list]
    assert {233: 1} in writes
    assert all(234 not in w for w in writes)  # no duration write


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [0, -5, 1.5, True, "10"])
async def test_enable_local_rejects_bad_minute(mock_client, bad):
    inv = _inverter(mock_client, with_transport=True)

    with pytest.raises(ValueError, match="minute must be a positive integer"):
        await inv.enable_quick_charge(minute=bad)

    inv._transport.write_parameters.assert_not_called()


@pytest.mark.asyncio
async def test_disable_local_clears_enable_bit(mock_client):
    inv = _inverter(mock_client, with_transport=True)
    inv._transport.read_parameters = AsyncMock(return_value={233: 0x1})

    ok = await inv.disable_quick_charge()

    assert ok is True
    writes = [c.args[0] for c in inv._transport.write_parameters.call_args_list]
    assert {233: 0} in writes  # bit cleared
    mock_client.api.control.stop_quick_charge.assert_not_called()


# ── HYBRID fallback (local write fails, real cloud client present) ───


@pytest.mark.asyncio
async def test_enable_hybrid_falls_back_to_cloud_on_local_failure(mock_client):
    inv = _inverter(mock_client, with_transport=True)
    inv._transport.write_parameters = AsyncMock(return_value=False)  # local write fails

    ok = await inv.enable_quick_charge(minute=20)

    assert ok is True
    mock_client.api.control.start_quick_charge.assert_awaited_once_with("1234567890", minute=20)


@pytest.mark.asyncio
async def test_disable_hybrid_falls_back_to_cloud_on_local_failure(mock_client):
    inv = _inverter(mock_client, with_transport=True)
    inv._transport.read_parameters = AsyncMock(return_value={233: 0x1})
    inv._transport.write_parameters = AsyncMock(return_value=False)

    ok = await inv.disable_quick_charge()

    assert ok is True
    mock_client.api.control.stop_quick_charge.assert_awaited_once_with("1234567890")


@pytest.mark.asyncio
async def test_enable_local_only_failure_returns_false_no_cloud(mock_client):
    """Local-only (client is None) fails honestly without a cloud attempt."""
    inv = _inverter(mock_client, with_transport=True)
    inv._client = None  # local-only: no cloud client
    inv._transport.write_parameters = AsyncMock(return_value=False)

    ok = await inv.enable_quick_charge(minute=20)

    assert ok is False
    mock_client.api.control.start_quick_charge.assert_not_called()


# ── CLOUD fallback (no transport) ────────────────────────────────────


@pytest.mark.asyncio
async def test_enable_cloud_when_no_transport(mock_client):
    inv = _inverter(mock_client, with_transport=False)

    ok = await inv.enable_quick_charge(minute=15)

    assert ok is True
    mock_client.api.control.start_quick_charge.assert_awaited_once_with("1234567890", minute=15)


@pytest.mark.asyncio
async def test_disable_cloud_when_no_transport(mock_client):
    inv = _inverter(mock_client, with_transport=False)

    ok = await inv.disable_quick_charge()

    assert ok is True
    mock_client.api.control.stop_quick_charge.assert_awaited_once_with("1234567890")


# ── set_quick_charge_minute ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_minute_writes_reg234(mock_client):
    inv = _inverter(mock_client, with_transport=True)

    ok = await inv.set_quick_charge_minute(45)

    assert ok is True
    inv._transport.write_parameters.assert_awaited_once_with({234: 45})


@pytest.mark.asyncio
async def test_set_minute_no_transport_returns_false(mock_client):
    inv = _inverter(mock_client, with_transport=False)

    assert await inv.set_quick_charge_minute(45) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [0, -1, 1.5, True])
async def test_set_minute_rejects_bad(mock_client, bad):
    inv = _inverter(mock_client, with_transport=True)

    with pytest.raises(ValueError, match="minute must be a positive integer"):
        await inv.set_quick_charge_minute(bad)


# ── status / detail ──────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("reg,expected", [(0x0, False), (0x1, True), (0x4097, True)])
async def test_status_local_reads_bit0(mock_client, reg, expected):
    inv = _inverter(mock_client, with_transport=True)
    inv._transport.read_parameters = AsyncMock(return_value={233: reg})

    assert await inv.get_quick_charge_status() is expected


@pytest.mark.asyncio
async def test_status_cloud_when_no_transport(mock_client):
    inv = _inverter(mock_client, with_transport=False)

    assert await inv.get_quick_charge_status() is True
    mock_client.api.control.get_quick_charge_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_detail_local_falls_back_to_reg234_when_input210_unavailable(mock_client):
    inv = _inverter(mock_client, with_transport=True)
    # Both regs read LIVE in one read_parameters(233, 2) — reg 234 must come
    # from the transport, NOT the (stale) cached parameter dict.
    inv._transport.read_parameters = AsyncMock(return_value={233: 0x1, 234: 8})
    # Input reg 210 unavailable (older firmware) -> fall back to reg 234 * 60.
    inv._transport.read_quick_charge_remaining_seconds = AsyncMock(return_value=None)
    inv.parameters = {"SNA_HOLD_QUICK_CHARGE_MINUTE": 999}  # stale; must be ignored

    detail = await inv.get_quick_charge_detail()

    inv._transport.read_parameters.assert_awaited_once_with(233, 2)
    assert detail.hasUnclosedQuickChargeTask is True
    assert detail.remainTimeBeforeQuickChargeStop == 8 * 60
    assert detail.remaining_minutes == 8
    # Raw holding reg 234 surfaced for the duration number to mirror.
    assert detail.quickChargeMinute == 8


@pytest.mark.asyncio
async def test_detail_local_prefers_input210_seconds(mock_client):
    """When input reg 210 reports a positive value (newer firmware), it is the
    remaining-time source, overriding the minute-resolution reg 234 derivation."""
    inv = _inverter(mock_client, with_transport=True)
    inv._transport.read_parameters = AsyncMock(return_value={233: 0x1, 234: 8})
    # Reg 210 = 320s (5m20s) — finer-grained than reg 234's 8 minutes.
    inv._transport.read_quick_charge_remaining_seconds = AsyncMock(return_value=320)

    detail = await inv.get_quick_charge_detail()

    inv._transport.read_quick_charge_remaining_seconds.assert_awaited_once_with()
    assert detail.hasUnclosedQuickChargeTask is True
    assert detail.remainTimeBeforeQuickChargeStop == 320
    assert detail.remaining_minutes == 6  # ceil(320 / 60)
    # remaining uses input reg 210 (seconds); quickChargeMinute still mirrors
    # the holding reg 234 value (the duration setpoint register).
    assert detail.quickChargeMinute == 8


@pytest.mark.asyncio
async def test_detail_local_idle_surfaces_reg234_zero_remaining(mock_client):
    """Idle: remaining is 0, but the raw holding reg 234 value is still surfaced
    as quickChargeMinute so the duration number mirrors the register faithfully
    (e.g. the last value the firmware retains) rather than a stored preference."""
    inv = _inverter(mock_client, with_transport=True)
    inv._transport.read_parameters = AsyncMock(return_value={233: 0x0, 234: 2})  # idle, reg=2
    inv._transport.read_quick_charge_remaining_seconds = AsyncMock(return_value=320)

    detail = await inv.get_quick_charge_detail()

    assert detail.hasUnclosedQuickChargeTask is False
    assert detail.remainTimeBeforeQuickChargeStop == 0
    assert detail.remaining_minutes == 0
    # Idle: remaining is always 0, so input reg 210 is not read.
    inv._transport.read_quick_charge_remaining_seconds.assert_not_awaited()
    # ...but the raw reg 234 value IS surfaced (faithful register mirror).
    assert detail.quickChargeMinute == 2


@pytest.mark.asyncio
async def test_detail_cloud_when_no_transport(mock_client):
    inv = _inverter(mock_client, with_transport=False)

    detail = await inv.get_quick_charge_detail()

    assert detail.hasUnclosedQuickChargeTask is True
    # Cloud has no holding register 234 to mirror.
    assert detail.quickChargeMinute is None
    mock_client.api.control.get_quick_charge_status.assert_awaited_once()


# ── transport: read_quick_charge_remaining_seconds (input reg 210) ────


class TestReadQuickChargeRemainingSeconds:
    """The transport reads input register 210 (remaining seconds) non-fatally,
    returning None when unavailable so callers fall back to holding reg 234."""

    @staticmethod
    def _transport():
        from pylxpweb.transports.modbus import ModbusTransport

        return ModbusTransport(host="192.168.1.100", serial="CE12345678")

    @pytest.mark.asyncio
    async def test_reads_address_210_returns_seconds(self):
        from unittest.mock import patch

        transport = self._transport()
        requested: list[tuple[int, int]] = []

        async def fake_read(start: int, count: int) -> list[int]:
            requested.append((start, count))
            return [420]

        with patch.object(transport, "_read_input_registers", side_effect=fake_read):
            secs = await transport.read_quick_charge_remaining_seconds()

        assert (210, 1) in requested
        assert secs == 420

    @pytest.mark.asyncio
    async def test_zero_value_returns_none(self):
        """Older firmware reports 0 -> None so the caller uses reg 234."""
        from unittest.mock import patch

        transport = self._transport()

        async def fake_read(start: int, count: int) -> list[int]:
            return [0]

        with patch.object(transport, "_read_input_registers", side_effect=fake_read):
            assert await transport.read_quick_charge_remaining_seconds() is None

    @pytest.mark.asyncio
    async def test_read_failure_is_non_fatal_returns_none(self):
        from unittest.mock import patch

        from pylxpweb.transports.exceptions import TransportReadError

        transport = self._transport()

        async def boom(start: int, count: int) -> list[int]:
            raise TransportReadError("simulated timeout on input reg 210")

        with patch.object(transport, "_read_input_registers", side_effect=boom):
            assert await transport.read_quick_charge_remaining_seconds() is None
