"""A dropped bms_data group read must NOT publish a degraded battery bank.

Regression for eg4_web_monitor#261. The combined / chunked battery reads fetch
register GROUPS as separate Modbus requests. reg 96 (battery_parallel_count) and
all BMS fields live in the bms_data group (80-112); battery voltage (reg 4) and
SOC (reg 5) live in the power_energy group (0-31). The bms_data group is the only
one allowed to fail non-fatally (a flaky dongle link drops single requests).

Before the fix, when ONLY bms_data dropped, ``from_modbus_registers`` still saw a
valid voltage (from the power group) so it returned a half-empty bank
(``battery_count=None``, current/cell data all None). That object overwrote the
last-good ``_transport_battery`` cache, making reg 96 read 0 downstream and the
battery_bank_* sensors flicker to unavailable.

The read must instead return ``battery=None`` when bms_data dropped, so the
caller (``_fetch_*`` in base.py, which both guard ``if battery is not None``)
keeps the last-good cache. A *genuine* reg 96 = 0 on a SUCCESSFUL bms_data read
still builds a bank (handled separately by the integration's cloud fallback).
"""

from unittest.mock import patch

import pytest

from pylxpweb.transports.modbus import ModbusTransport

_VOLTAGE_RAW = 534  # reg 4, DIV_10 -> 53.4 V (well above the 1.0 V no-battery gate)
_SOC_SOH_PACKED = (100 << 8) | 82  # reg 5: SOC=82, SOH=100
_POWER_GROUP_START = 0
_BMS_GROUP_START = 80


def _make_fake_read(fail_starts: set[int] = frozenset(), short_starts: set[int] = frozenset()):
    """Return a fake ``_read_input_registers``.

    ``fail_starts`` raise (a dropped request); ``short_starts`` return a
    truncated list WITHOUT raising (a partial/misrouted frame). The
    power_energy group (start 0) carries a valid battery voltage + SOC so the
    no-battery voltage gate does NOT short-circuit; that's what made a bms-only
    drop produce a degraded (not None) bank before the fix.
    """

    async def fake_read(start: int, count: int) -> list[int]:
        if start in fail_starts:
            raise OSError("simulated dropped Modbus request")
        n = 5 if start in short_starts else count  # truncated, non-raising frame
        vals = [0] * n
        if start == _POWER_GROUP_START and n > 5:
            vals[4] = _VOLTAGE_RAW
            vals[5] = _SOC_SOH_PACKED
        return vals

    return fake_read


def _transport() -> ModbusTransport:
    t = ModbusTransport(host="192.168.1.100", serial="CE12345678")
    t.pv_string_count = 3  # skip the pv4-6 extended read
    return t


@pytest.mark.asyncio
async def test_combined_read_returns_none_battery_when_bms_drops() -> None:
    """read_all_input_data: bms_data drop -> battery None (preserve cache)."""
    transport = _transport()
    with patch.object(
        transport, "_read_input_registers", side_effect=_make_fake_read({_BMS_GROUP_START})
    ):
        runtime, energy, battery = await transport.read_all_input_data()

    assert runtime is not None  # power/status groups still produced runtime
    assert energy is not None
    assert battery is None  # degraded bank suppressed -> caller keeps last-good


@pytest.mark.asyncio
async def test_combined_read_builds_bank_when_bms_ok_even_if_reg96_zero() -> None:
    """A genuine reg 96 = 0 on a SUCCESSFUL bms read still yields a bank."""
    transport = _transport()
    # No group fails: bms_data (80) returns zeros, so reg 96 = 0 genuinely while
    # voltage/SOC from the power group are valid.
    with patch.object(transport, "_read_input_registers", side_effect=_make_fake_read(set())):
        _runtime, _energy, battery = await transport.read_all_input_data()

    assert battery is not None  # bms read OK -> bank built, integration handles count=0
    assert battery.soc == 82


@pytest.mark.asyncio
async def test_chunked_read_battery_returns_none_when_bms_drops() -> None:
    """read_battery (chunked fallback): bms group drop -> None (preserve cache)."""
    transport = _transport()
    with patch.object(
        transport, "_read_input_registers", side_effect=_make_fake_read({_BMS_GROUP_START})
    ):
        result = await transport.read_battery()

    assert result is None


@pytest.mark.asyncio
async def test_chunked_read_battery_builds_bank_when_bms_ok() -> None:
    """read_battery: a successful bms read still builds the bank (no regression)."""
    transport = _transport()
    with patch.object(transport, "_read_input_registers", side_effect=_make_fake_read(set())):
        result = await transport.read_battery()

    assert result is not None
    assert result.soc == 82


@pytest.mark.asyncio
async def test_combined_read_returns_none_battery_when_bms_short() -> None:
    """A short (non-raising) bms_data frame is treated as unavailable too."""
    transport = _transport()
    with patch.object(
        transport,
        "_read_input_registers",
        side_effect=_make_fake_read(short_starts={_BMS_GROUP_START}),
    ):
        runtime, _energy, battery = await transport.read_all_input_data()

    assert runtime is not None
    assert battery is None


@pytest.mark.asyncio
async def test_chunked_read_battery_returns_none_when_bms_short() -> None:
    """read_battery: a short (non-raising) bms frame -> None (preserve cache)."""
    transport = _transport()
    with patch.object(
        transport,
        "_read_input_registers",
        side_effect=_make_fake_read(short_starts={_BMS_GROUP_START}),
    ):
        result = await transport.read_battery()

    assert result is None
