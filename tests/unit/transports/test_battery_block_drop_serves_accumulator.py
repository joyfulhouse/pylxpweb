"""A failed 5002+ battery block read must serve the accumulator, not wipe batteries.

Regression for eg4_web_monitor#258 (ivanfmartinez, 2026-06-28, beta.16 +
pylxpweb 0.9.36b17): a WiFi-dongle glitch failed ONE battery block read
(``Failed to read battery registers 5002-5121, will retry next poll``).
``_read_individual_battery_registers`` returned ``None``, but the bms_data
group had succeeded, so ``read_all_input_data`` built a bank with
``batteries=[]`` that REPLACED the cached ``_transport_battery`` — wiping
every individual battery for the cycle even though the never-evict
accumulator still held all of them. Downstream, every individual battery
entity flipped unavailable at that exact second.

The fix: on a failed block read, serve the accumulator's last-known blocks
(with their honest, stale ``last_seen`` stamps — the signal the hybrid
supplemental gate and the integration's freshness overlay key off) instead
of dropping the batteries. Only a failure with an EMPTY accumulator (first
poll after startup) still returns ``None``.

The same incident exposed a 9-hour silently-pinned rotation (the firmware
kept serving one page; reads succeeded, so no warnings fired while half the
accumulated batteries froze). ``_log_battery_rotation_stall`` now emits one
latched WARNING when accumulated batteries stop being surfaced, and an INFO
when rotation resumes.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from pylxpweb.registers import (
    BATTERY_BASE_ADDRESS,
    BATTERY_MAX_COUNT,
    BATTERY_REGISTER_COUNT,
)
from pylxpweb.transports._register_data import BATTERY_ROTATION_STALL_WARN_AFTER
from pylxpweb.transports.modbus import ModbusTransport

_VOLTAGE_RAW = 534  # reg 4, DIV_10 -> 53.4 V (above the 1.0 V no-battery gate)
_SOC_SOH_PACKED = (100 << 8) | 82  # reg 5: SOC=82, SOH=100
_POWER_GROUP_START = 0
_BMS_GROUP_START = 80
_BATTERY_COUNT_OFFSET = 16  # reg 96 within the bms_data group (80 + 16)


def _page(positions: list[int]) -> list[int]:
    """Build a 120-register battery block with batteries at ``positions``.

    Each of the 4 physical slots gets status=0xC003, a voltage, packed
    SOC/SOH, and its position index in offset 24's high byte (the identity
    fallback used when the BMS reports no serial).
    """
    vals = [0] * (BATTERY_MAX_COUNT * BATTERY_REGISTER_COUNT)
    for slot_idx, pos in enumerate(positions):
        base = slot_idx * BATTERY_REGISTER_COUNT
        vals[base] = 0xC003
        vals[base + 6] = 5246  # 52.46 V after DIV_100
        vals[base + 8] = _SOC_SOH_PACKED
        vals[base + 24] = pos << 8
    return vals


def _transport() -> ModbusTransport:
    t = ModbusTransport(host="192.168.1.100", serial="CE12345678")
    t.pv_string_count = 3  # skip the pv4-6 extended read
    return t


def _make_fake_read(block_pages: list[list[int] | Exception], battery_count: int = 8):
    """Fake ``_read_input_registers`` with scripted 5002+ block responses.

    Register groups succeed with zeros, except the power group (valid battery
    voltage + SOC) and the bms group (reg 96 = ``battery_count``). Each read of
    the 120-register block at 5002 consumes the next entry of ``block_pages``;
    an Exception entry raises (a dropped request), a list entry is returned.
    The last entry repeats once the script is exhausted.
    """
    call_idx = [0]

    async def fake_read(start: int, count: int) -> list[int]:
        if start == BATTERY_BASE_ADDRESS:
            idx = min(call_idx[0], len(block_pages) - 1)
            call_idx[0] += 1
            entry = block_pages[idx]
            if isinstance(entry, Exception):
                raise entry
            return entry
        vals = [0] * count
        if start == _POWER_GROUP_START:
            vals[4] = _VOLTAGE_RAW
            vals[5] = _SOC_SOH_PACKED
        if start == _BMS_GROUP_START:
            vals[_BATTERY_COUNT_OFFSET] = battery_count
        return vals

    return fake_read


class TestFailedBlockReadServesAccumulator:
    """A dropped 5002+ read serves last-known batteries instead of none."""

    @pytest.mark.asyncio
    async def test_failed_block_read_returns_accumulated_batteries(self) -> None:
        """Fail after two-page accumulation -> all 8 blocks still returned."""
        transport = _transport()
        fake = _make_fake_read(
            [
                _page([0, 1, 2, 3]),
                _page([4, 5, 6, 7]),
                OSError("simulated dropped block read"),
            ]
        )
        with patch.object(transport, "_read_input_registers", side_effect=fake):
            await transport._read_individual_battery_registers(8)
            await transport._read_individual_battery_registers(8)
            result = await transport._read_individual_battery_registers(8)

        assert result is not None
        assert len(result) == 8 * BATTERY_REGISTER_COUNT
        for virtual_slot in range(8):
            base = BATTERY_BASE_ADDRESS + virtual_slot * BATTERY_REGISTER_COUNT
            assert result.get(base) == 0xC003, f"virtual slot {virtual_slot} lost"

    @pytest.mark.asyncio
    async def test_failed_block_read_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """The failure still warns every time (no silent retry loop)."""
        transport = _transport()
        fake = _make_fake_read([_page([0, 1, 2, 3]), OSError("boom"), OSError("boom")])
        with (
            patch.object(transport, "_read_input_registers", side_effect=fake),
            caplog.at_level(logging.WARNING),
        ):
            await transport._read_individual_battery_registers(8)
            await transport._read_individual_battery_registers(8)
            await transport._read_individual_battery_registers(8)

        warnings = [r for r in caplog.records if "Failed to read battery registers" in r.message]
        assert len(warnings) == 2  # one per actual failure — never deduplicated

    @pytest.mark.asyncio
    async def test_failed_block_read_with_empty_accumulator_returns_none(self) -> None:
        """First-poll failure (nothing accumulated yet) keeps returning None."""
        transport = _transport()
        fake = _make_fake_read([OSError("boom")])
        with patch.object(transport, "_read_input_registers", side_effect=fake):
            result = await transport._read_individual_battery_registers(8)

        assert result is None

    @pytest.mark.asyncio
    async def test_failed_block_read_preserves_stale_last_seen(self) -> None:
        """The served blocks keep their old stamps — staleness stays honest.

        ``last_seen`` is the signal the hybrid supplemental gate (pylxpweb) and
        the integration's HYBRID freshness overlay use to prefer cloud data, so
        a failed read must NOT refresh it.
        """
        transport = _transport()
        fake = _make_fake_read([_page([0, 1, 2, 3]), OSError("boom")])
        with patch.object(transport, "_read_input_registers", side_effect=fake):
            await transport._read_individual_battery_registers(8)
            stamps_before = dict(transport._battery_last_seen)
            result = await transport._read_individual_battery_registers(8)

        assert result is not None
        assert transport._battery_last_seen == stamps_before


class TestCombinedReadKeepsBatteriesOnBlockDrop:
    """read_all_input_data: block drop -> bank keeps accumulated batteries.

    This is the exact 2026-06-28 incident shape: the bms group (reg 96 = 8)
    succeeded, only the 5002-5121 block read failed. Before the fix the
    returned bank had ``batteries=[]`` and replaced the last-good cache.
    """

    @pytest.mark.asyncio
    async def test_block_drop_after_accumulation_keeps_batteries(self) -> None:
        transport = _transport()
        fake = _make_fake_read(
            [
                _page([0, 1, 2, 3]),
                _page([4, 5, 6, 7]),
                OSError("simulated dropped block read"),
            ]
        )
        with patch.object(transport, "_read_input_registers", side_effect=fake):
            _, _, battery_ok = await transport.read_all_input_data()
            _, _, battery_full = await transport.read_all_input_data()
            runtime, _, battery_dropped = await transport.read_all_input_data()

        assert battery_ok is not None and len(battery_ok.batteries) == 4
        assert battery_full is not None and len(battery_full.batteries) == 8
        # The failed cycle still presents every accumulated battery...
        assert runtime is not None
        assert battery_dropped is not None
        assert len(battery_dropped.batteries) == 8
        # ...with fresh bank-level data (the bms group succeeded)
        assert battery_dropped.soc == 82

    @pytest.mark.asyncio
    async def test_first_poll_block_drop_yields_bank_without_individuals(self) -> None:
        """Startup edge: nothing accumulated yet -> bank-level only (as before)."""
        transport = _transport()
        fake = _make_fake_read([OSError("boom")])
        with patch.object(transport, "_read_input_registers", side_effect=fake):
            _, _, battery = await transport.read_all_input_data()

        assert battery is not None  # bms group OK -> bank-level data valid
        assert battery.batteries == []


class TestBatteryRotationStallWarning:
    """One latched WARNING per stall episode; INFO + re-arm on recovery.

    The 2026-06-28 incident produced ZERO non-debug logs for ~9 hours while
    the firmware kept serving one pinned page and half the accumulated
    batteries silently froze.
    """

    @staticmethod
    def _backdate(transport: ModbusTransport, slots: list[int]) -> None:
        stale_stamp = datetime.now(UTC) - BATTERY_ROTATION_STALL_WARN_AFTER * 2
        for slot in slots:
            transport._battery_last_seen[slot] = stale_stamp

    @pytest.mark.asyncio
    async def test_pinned_page_warns_once(self, caplog: pytest.LogCaptureFixture) -> None:
        transport = _transport()
        fake = _make_fake_read(
            [_page([0, 1, 2, 3]), _page([4, 5, 6, 7])] + [_page([0, 1, 2, 3])] * 3
        )
        with (
            patch.object(transport, "_read_input_registers", side_effect=fake),
            caplog.at_level(logging.INFO),
        ):
            await transport._read_individual_battery_registers(8)
            await transport._read_individual_battery_registers(8)
            self._backdate(transport, [4, 5, 6, 7])  # page B never comes back
            await transport._read_individual_battery_registers(8)
            await transport._read_individual_battery_registers(8)

        warnings = [r for r in caplog.records if "Battery rotation stalled" in r.message]
        assert len(warnings) == 1
        assert "4 of 8" in warnings[0].message

    @pytest.mark.asyncio
    async def test_recovery_logs_info_and_rearms(self, caplog: pytest.LogCaptureFixture) -> None:
        transport = _transport()
        pages: list[list[int] | Exception] = [
            _page([0, 1, 2, 3]),  # accumulate page A
            _page([4, 5, 6, 7]),  # accumulate page B
            _page([0, 1, 2, 3]),  # stall detected (B backdated below)
            _page([4, 5, 6, 7]),  # rotation resumes -> recovery INFO
            _page([0, 1, 2, 3]),  # second stall episode (B backdated again)
        ]
        fake = _make_fake_read(pages)
        with (
            patch.object(transport, "_read_input_registers", side_effect=fake),
            caplog.at_level(logging.INFO),
        ):
            await transport._read_individual_battery_registers(8)
            await transport._read_individual_battery_registers(8)
            self._backdate(transport, [4, 5, 6, 7])
            await transport._read_individual_battery_registers(8)  # warn #1
            await transport._read_individual_battery_registers(8)  # recovery
            self._backdate(transport, [4, 5, 6, 7])
            await transport._read_individual_battery_registers(8)  # warn #2

        warnings = [r for r in caplog.records if "Battery rotation stalled" in r.message]
        infos = [r for r in caplog.records if "Battery rotation resumed" in r.message]
        assert len(warnings) == 2
        assert len(infos) == 1

    @pytest.mark.asyncio
    async def test_healthy_rotation_never_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """Normal alternation (all stamps fresh) stays silent."""
        transport = _transport()
        fake = _make_fake_read(
            [
                _page([0, 1, 2, 3]),
                _page([4, 5, 6, 7]),
                _page([0, 1, 2, 3]),
                _page([4, 5, 6, 7]),
            ]
        )
        with (
            patch.object(transport, "_read_input_registers", side_effect=fake),
            caplog.at_level(logging.WARNING),
        ):
            for _ in range(4):
                await transport._read_individual_battery_registers(8)

        assert "Battery rotation stalled" not in caplog.text

    @pytest.mark.asyncio
    async def test_straggler_does_not_mask_new_stall(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A permanent straggler must not latch away warnings for NEW stalls.

        A physically removed/replaced battery is never evicted by design, so it
        stays stale forever.  With a single global latch its one warning would
        stick (re-arming required ALL identities fresh), and a later, unrelated
        battery stall would log NOTHING — silently reproducing the exact blind
        spot the watchdog exists to close.  Latching is per identity: each
        battery warns once per ITS OWN stall episode.
        """
        transport = _transport()
        pages: list[list[int] | Exception] = [
            _page([0, 1, 2, 3]),  # accumulate page A
            _page([4, 5, 6, 7]),  # accumulate page B
            _page([0, 1, 2, 3]),  # pos:7 backdated below -> warn #1
            _page([0, 1, 3]),  # pos:2 not refreshed; backdated below -> warn #2
        ]
        fake = _make_fake_read(pages)
        with (
            patch.object(transport, "_read_input_registers", side_effect=fake),
            caplog.at_level(logging.INFO),
        ):
            await transport._read_individual_battery_registers(8)
            await transport._read_individual_battery_registers(8)
            self._backdate(transport, [7])  # straggler (e.g. removed battery)
            await transport._read_individual_battery_registers(8)
            self._backdate(transport, [2])  # NEW, unrelated stall
            await transport._read_individual_battery_registers(8)

        warnings = [r for r in caplog.records if "Battery rotation stalled" in r.message]
        assert len(warnings) == 2
        assert "pos:7" in warnings[0].message
        assert "pos:2" in warnings[1].message

    @pytest.mark.asyncio
    async def test_threshold_scales_with_battery_count(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Large arrays get a proportionally longer stall threshold.

        The 45-min floor is calibrated on #170's 12-battery (3-page) system
        (~30 min worst-case reappearance).  A 24-battery array rotates 6
        pages, so a fixed 45-min cutoff would warn on perfectly healthy
        rotation lag.  The threshold scales at 15 min/page: 6 pages → 90 min.
        """
        transport = _transport()
        pages: list[list[int] | Exception] = [
            _page(list(range(p * 4, p * 4 + 4))) for p in range(6)
        ]
        fake = _make_fake_read(pages + [_page([0, 1, 2, 3])] * 2, battery_count=24)
        with (
            patch.object(transport, "_read_input_registers", side_effect=fake),
            caplog.at_level(logging.WARNING),
        ):
            for _ in range(6):
                await transport._read_individual_battery_registers(24)
            # 60 min behind: past the 45-min floor but inside the scaled
            # 90-min threshold -> healthy rotation lag on a big array, silent.
            transport._battery_last_seen[23] = datetime.now(UTC) - timedelta(minutes=60)
            await transport._read_individual_battery_registers(24)
            assert "Battery rotation stalled" not in caplog.text
            # 100 min behind: beyond the scaled threshold -> stalled, warns.
            transport._battery_last_seen[23] = datetime.now(UTC) - timedelta(minutes=100)
            await transport._read_individual_battery_registers(24)

        assert "Battery rotation stalled" in caplog.text
