"""Shared-battery context in the battery_count (reg 96) debug log (eg4#288).

On a multi-inverter system sharing one battery bank, only the primary
inverter sits on the battery CAN bus — a *secondary* legitimately reads
``battery_count`` (reg 96) = 0.  That reading looked like a bug in the
eg4_web_monitor #282/#258 investigations, so the reg96 debug lines now
append "(shared-battery secondary — reg96=0 expected)" when the last-seen
HOLD 110 has FUNC_BAT_SHARED (bit 3) set.

HOLD 110 is stashed opportunistically when it passes through an existing
``read_parameters()`` / ``write_parameters()`` call — the annotation never
triggers a holding-register read of its own.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from pylxpweb.transports.modbus import ModbusTransport

_BAT_SHARED_BIT = 0x8  # HOLD 110 bit 3 = FUNC_BAT_SHARED
_NOTE = "shared-battery secondary — reg96=0 expected"

_POWER_GROUP_START = 0
_BMS_GROUP_START = 80
_VOLTAGE_RAW = 534  # reg 4, DIV_10 -> 53.4 V


def _transport() -> ModbusTransport:
    t = ModbusTransport(host="192.168.1.100", serial="CE12345678")
    t.pv_string_count = 3  # skip the pv4-6 extended read
    return t


async def _fake_input_read(start: int, count: int) -> list[int]:
    """All input groups read zeros (reg 96 = 0, no battery slots)."""
    vals = [0] * count
    if start == _POWER_GROUP_START:
        vals[4] = _VOLTAGE_RAW
    return vals


class TestSharedBatteryNoteHelper:
    """_shared_battery_note(): only bit 3 + reg96==0 produce the note."""

    def test_note_when_bit3_set_and_count_zero(self) -> None:
        transport = _transport()
        transport._last_hold_110 = _BAT_SHARED_BIT
        assert _NOTE in transport._shared_battery_note(0)

    def test_no_note_when_bit3_clear(self) -> None:
        transport = _transport()
        transport._last_hold_110 = 0xFFF7  # everything except bit 3
        assert transport._shared_battery_note(0) == ""

    def test_no_note_when_count_nonzero(self) -> None:
        """A primary (on the battery CAN bus) with sharing enabled still
        reports its bank — reg96>0 needs no excuse."""
        transport = _transport()
        transport._last_hold_110 = _BAT_SHARED_BIT
        assert transport._shared_battery_note(4) == ""

    def test_no_note_before_hold_110_seen(self) -> None:
        """No HOLD 110 has passed through yet -> stay silent (never guess,
        never read)."""
        transport = _transport()
        assert transport._last_hold_110 is None
        assert transport._shared_battery_note(0) == ""


class TestHold110OpportunisticStash:
    """read/write_parameters stash reg 110 when it passes through."""

    @pytest.mark.asyncio
    async def test_read_parameters_covering_110_stashes_value(self) -> None:
        transport = _transport()

        async def fake_holding(start: int, count: int) -> list[int]:
            vals = [0] * count
            if start <= 110 < start + count:
                vals[110 - start] = _BAT_SHARED_BIT | 0x100
            return vals

        with patch.object(transport, "_read_holding_registers", side_effect=fake_holding):
            await transport.read_parameters(80, 40)

        assert transport._last_hold_110 == _BAT_SHARED_BIT | 0x100

    @pytest.mark.asyncio
    async def test_read_parameters_not_covering_110_leaves_stash(self) -> None:
        transport = _transport()
        transport._last_hold_110 = _BAT_SHARED_BIT

        async def fake_holding(start: int, count: int) -> list[int]:
            return [0] * count

        with patch.object(transport, "_read_holding_registers", side_effect=fake_holding):
            await transport.read_parameters(0, 40)

        assert transport._last_hold_110 == _BAT_SHARED_BIT

    @pytest.mark.asyncio
    async def test_write_parameters_updates_stash(self) -> None:
        """A local FUNC_BAT_SHARED bit flip (RMW of reg 110) keeps the
        stash coherent without waiting for the next parameter read."""
        transport = _transport()
        transport._last_hold_110 = _BAT_SHARED_BIT

        with patch.object(transport, "_write_holding_registers", new=AsyncMock(return_value=True)):
            await transport.write_parameters({110: 0})

        assert transport._last_hold_110 == 0


class TestRegNinetySixDebugLineAnnotation:
    """End to end: the combined-path reg96 debug line carries the note."""

    @pytest.mark.asyncio
    async def test_combined_path_notes_shared_secondary(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        transport = _transport()
        transport._last_hold_110 = _BAT_SHARED_BIT

        with (
            patch.object(transport, "_read_input_registers", side_effect=_fake_input_read),
            caplog.at_level(logging.DEBUG),
        ):
            await transport.read_all_input_data()

        line = next(
            r.getMessage() for r in caplog.records if "battery_count (reg 96)" in r.getMessage()
        )
        assert "= 0" in line
        assert _NOTE in line

    @pytest.mark.asyncio
    async def test_combined_path_silent_without_sharing(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        transport = _transport()
        transport._last_hold_110 = 0

        with (
            patch.object(transport, "_read_input_registers", side_effect=_fake_input_read),
            caplog.at_level(logging.DEBUG),
        ):
            await transport.read_all_input_data()

        assert _NOTE not in caplog.text
