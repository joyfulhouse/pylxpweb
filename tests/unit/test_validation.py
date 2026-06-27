"""Tests for energy validation (monotonicity + daily bounds)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from pylxpweb.devices.base import WARMUP_READS, BaseDevice
from pylxpweb.devices.models import DeviceInfo, Entity
from pylxpweb.validation import (
    DAILY_ENERGY_MARGIN,
    DEFAULT_RATED_POWER_KW,
    MAX_ELAPSED_HOURS,
    MAX_ENERGY_DELTA,
    MIN_DAILY_DELTA,
    MIN_LIFETIME_KWH,
    SELF_HEAL_THRESHOLD,
    UPWARD_SELF_HEAL_THRESHOLD,
    validate_daily_energy_bounds,
    validate_energy_monotonicity,
)


class TestValidateEnergyMonotonicity:
    """Test validate_energy_monotonicity function."""

    def test_valid_increase_accepted(self) -> None:
        """Normal kWh growth passes validation."""
        prev = {"grid_import_total": 2700.0, "grid_export_total": 4300.0}
        curr = {"grid_import_total": 2700.5, "grid_export_total": 4300.2}
        result, count = validate_energy_monotonicity(prev, curr, 0, "test_dev")
        assert result == "valid"
        assert count == 0

    def test_upward_spike_rejected(self) -> None:
        """Delta > MAX_ENERGY_DELTA rejected as corrupt spike."""
        prev = {"grid_import_total": 2700.0}
        curr = {"grid_import_total": 202_000_000.0}
        result, count = validate_energy_monotonicity(prev, curr, 0, "test_dev")
        assert result == "reject"
        assert count == 1  # upward spike increments count

    def test_upward_spike_increments_count(self) -> None:
        """Upward spike increments reject count instead of resetting."""
        prev = {"grid_import_total": 2700.0}
        curr = {"grid_import_total": 202_000_000.0}
        result, count = validate_energy_monotonicity(prev, curr, 3, "test_dev")
        assert result == "reject"
        assert count == 4

    def test_upward_spike_self_heals_after_threshold(self) -> None:
        """5 consecutive upward spike rejections → accept as new baseline."""
        prev = {"grid_import_total": 2700.0}
        curr = {"grid_import_total": 5000.0}  # > MIN_LIFETIME_KWH
        result, count = validate_energy_monotonicity(
            prev, curr, UPWARD_SELF_HEAL_THRESHOLD - 1, "test_dev"
        )
        assert result == "self_healed"
        assert count == 0

    def test_upward_spike_low_value_blocks_self_heal(self) -> None:
        """Upward spike value < MIN_LIFETIME_KWH won't self-heal."""
        prev = {"grid_import_total": 50.0}
        curr = {"grid_import_total": 999.0}  # Below MIN_LIFETIME_KWH
        result, count = validate_energy_monotonicity(
            prev, curr, UPWARD_SELF_HEAL_THRESHOLD - 1, "test_dev"
        )
        assert result == "reject"
        assert count == UPWARD_SELF_HEAL_THRESHOLD

    def test_downward_drop_rejected(self) -> None:
        """Decrease in lifetime counter is rejected."""
        prev = {"grid_import_total": 2700.0}
        curr = {"grid_import_total": 2699.0}
        result, count = validate_energy_monotonicity(prev, curr, 0, "test_dev")
        assert result == "reject"
        assert count == 1

    def test_self_heals_after_threshold(self) -> None:
        """3 consecutive downward rejections → accept as new baseline."""
        prev = {"grid_import_total": 124520.9}
        curr = {"grid_import_total": 2732.6}  # > MIN_LIFETIME_KWH

        # Simulate SELF_HEAL_THRESHOLD - 1 prior rejections
        result, count = validate_energy_monotonicity(
            prev, curr, SELF_HEAL_THRESHOLD - 1, "test_dev"
        )
        assert result == "self_healed"
        assert count == 0

    def test_low_value_blocks_self_heal(self) -> None:
        """Value < MIN_LIFETIME_KWH won't self-heal — keeps rejecting."""
        prev = {"grid_import_total": 25000.0}
        curr = {"grid_import_total": 12.9}  # Below MIN_LIFETIME_KWH

        # Even at SELF_HEAL_THRESHOLD, low value prevents self-heal
        result, count = validate_energy_monotonicity(
            prev, curr, SELF_HEAL_THRESHOLD - 1, "test_dev"
        )
        assert result == "reject"
        assert count == SELF_HEAL_THRESHOLD

        # And again — still rejecting
        result, count = validate_energy_monotonicity(prev, curr, count, "test_dev")
        assert result == "reject"
        assert count == SELF_HEAL_THRESHOLD + 1

    def test_counter_resets_on_valid(self) -> None:
        """Valid data resets reject count to 0."""
        prev = {"grid_import_total": 2700.0}
        curr = {"grid_import_total": 2701.0}
        result, count = validate_energy_monotonicity(prev, curr, 5, "test_dev")
        assert result == "valid"
        assert count == 0

    def test_none_values_skipped(self) -> None:
        """None fields are ignored during validation."""
        prev = {"grid_import_total": 2700.0, "grid_export_total": None}
        curr = {"grid_import_total": 2701.0, "grid_export_total": None}
        result, count = validate_energy_monotonicity(prev, curr, 0, "test_dev")
        assert result == "valid"
        assert count == 0

    def test_prev_none_key_skipped(self) -> None:
        """Key present in curr but None in prev is skipped."""
        prev = {"grid_import_total": None}
        curr = {"grid_import_total": 2700.0}
        result, count = validate_energy_monotonicity(prev, curr, 0, "test_dev")
        assert result == "valid"
        assert count == 0

    def test_prev_missing_key_skipped(self) -> None:
        """Key present in curr but absent in prev is skipped."""
        prev: dict[str, float | None] = {}
        curr = {"grid_import_total": 2700.0}
        result, count = validate_energy_monotonicity(prev, curr, 0, "test_dev")
        assert result == "valid"
        assert count == 0

    def test_exact_delta_boundary_passes(self) -> None:
        """Increase exactly equal to MAX_ENERGY_DELTA passes."""
        prev = {"grid_import_total": 2700.0}
        curr = {"grid_import_total": 2700.0 + MAX_ENERGY_DELTA}
        result, count = validate_energy_monotonicity(prev, curr, 0, "test_dev")
        assert result == "valid"
        assert count == 0

    def test_just_over_delta_boundary_rejected(self) -> None:
        """Increase just over MAX_ENERGY_DELTA is rejected."""
        prev = {"grid_import_total": 2700.0}
        curr = {"grid_import_total": 2700.0 + MAX_ENERGY_DELTA + 0.1}
        result, count = validate_energy_monotonicity(prev, curr, 0, "test_dev")
        assert result == "reject"
        assert count == 1

    def test_self_heal_exactly_at_min_threshold(self) -> None:
        """Value exactly at MIN_LIFETIME_KWH allows self-heal."""
        prev = {"grid_import_total": 50000.0}
        curr = {"grid_import_total": MIN_LIFETIME_KWH}
        result, count = validate_energy_monotonicity(
            prev, curr, SELF_HEAL_THRESHOLD - 1, "test_dev"
        )
        assert result == "self_healed"
        assert count == 0


class TestValidateDailyEnergyBounds:
    """Test validate_daily_energy_bounds function."""

    # -- Absolute cap (no previous data, startup scenario) --

    def test_startup_normal_value_accepted(self) -> None:
        """First read with plausible daily value passes."""
        curr = {"charge_energy_today": 8.8}
        assert validate_daily_energy_bounds(curr, "test_dev", rated_power_kw=18.0)

    def test_startup_corrupt_value_rejected(self) -> None:
        """First read with impossibly high daily value is rejected."""
        # 6549.2 kWh for an 18kW inverter → exceeds 18 * 24 * 2 = 864
        curr = {"charge_energy_today": 6549.2}
        assert not validate_daily_energy_bounds(curr, "test_dev", rated_power_kw=18.0)

    def test_startup_at_absolute_cap_accepted(self) -> None:
        """Value exactly at absolute cap passes."""
        cap = 18.0 * MAX_ELAPSED_HOURS * DAILY_ENERGY_MARGIN
        curr = {"charge_energy_today": cap}
        assert validate_daily_energy_bounds(curr, "test_dev", rated_power_kw=18.0)

    def test_startup_just_over_absolute_cap_rejected(self) -> None:
        """Value just over absolute cap is rejected."""
        cap = 18.0 * MAX_ELAPSED_HOURS * DAILY_ENERGY_MARGIN
        curr = {"charge_energy_today": cap + 0.1}
        assert not validate_daily_energy_bounds(curr, "test_dev", rated_power_kw=18.0)

    def test_startup_unknown_rated_power_uses_default(self) -> None:
        """Unknown rated power falls back to DEFAULT_RATED_POWER_KW."""
        cap = DEFAULT_RATED_POWER_KW * MAX_ELAPSED_HOURS * DAILY_ENERGY_MARGIN
        curr = {"charge_energy_today": cap}
        assert validate_daily_energy_bounds(curr, "test_dev", rated_power_kw=0.0)

    def test_startup_none_values_skipped(self) -> None:
        """None values in current data are ignored."""
        curr: dict[str, float | None] = {"charge_energy_today": None}
        assert validate_daily_energy_bounds(curr, "test_dev", rated_power_kw=18.0)

    # -- Time-based delta (normal operation) --

    def test_normal_poll_plausible_increase_accepted(self) -> None:
        """Normal 30s poll with small increase passes."""
        prev = {"charge_energy_today": 5.0}
        curr = {"charge_energy_today": 5.1}
        assert validate_daily_energy_bounds(
            curr,
            "test_dev",
            rated_power_kw=18.0,
            elapsed_seconds=30.0,
            prev_values=prev,
        )

    def test_normal_poll_corrupt_spike_rejected(self) -> None:
        """30s poll with 6549.2 kWh spike is rejected."""
        prev = {"charge_energy_today": 0.0}
        curr = {"charge_energy_today": 6549.2}
        assert not validate_daily_energy_bounds(
            curr,
            "test_dev",
            rated_power_kw=18.0,
            elapsed_seconds=30.0,
            prev_values=prev,
        )

    def test_normal_poll_exact_delta_bound_accepted(self) -> None:
        """Increase exactly at time-based delta bound passes."""
        # 18kW * (30s / 3600) * 2.0 = 0.3 kWh
        delta = 18.0 * (30.0 / 3600.0) * DAILY_ENERGY_MARGIN
        prev = {"charge_energy_today": 5.0}
        curr = {"charge_energy_today": 5.0 + delta}
        assert validate_daily_energy_bounds(
            curr,
            "test_dev",
            rated_power_kw=18.0,
            elapsed_seconds=30.0,
            prev_values=prev,
        )

    def test_normal_poll_just_over_delta_rejected(self) -> None:
        """Increase just over time-based delta bound is rejected."""
        delta = 18.0 * (30.0 / 3600.0) * DAILY_ENERGY_MARGIN
        prev = {"charge_energy_today": 5.0}
        curr = {"charge_energy_today": 5.0 + delta + 0.01}
        assert not validate_daily_energy_bounds(
            curr,
            "test_dev",
            rated_power_kw=18.0,
            elapsed_seconds=30.0,
            prev_values=prev,
        )

    # -- Midnight reset (decrease is allowed) --

    def test_midnight_reset_decrease_accepted(self) -> None:
        """Daily counter decreasing (midnight reset) is allowed."""
        prev = {"charge_energy_today": 12.9}
        curr = {"charge_energy_today": 0.0}
        assert validate_daily_energy_bounds(
            curr,
            "test_dev",
            rated_power_kw=18.0,
            elapsed_seconds=60.0,
            prev_values=prev,
        )

    def test_midnight_reset_to_small_value_accepted(self) -> None:
        """Reset + some accumulation in new day is allowed."""
        prev = {"charge_energy_today": 12.9}
        curr = {"charge_energy_today": 3.0}
        assert validate_daily_energy_bounds(
            curr,
            "test_dev",
            rated_power_kw=18.0,
            elapsed_seconds=3600.0,
            prev_values=prev,
        )

    # -- Long outage recovery --

    def test_long_outage_elapsed_capped_at_24h(self) -> None:
        """72-hour outage: elapsed capped at 24h, so bound = rated * 24 * margin."""
        prev = {"charge_energy_today": 0.0}
        curr = {"charge_energy_today": 400.0}
        # 72 hours elapsed but capped to 24h → max = 18 * 24 * 2 = 864
        assert validate_daily_energy_bounds(
            curr,
            "test_dev",
            rated_power_kw=18.0,
            elapsed_seconds=72 * 3600,
            prev_values=prev,
        )

    def test_long_outage_corrupt_value_still_rejected(self) -> None:
        """Even after 72h outage, 6549.2 exceeds abs cap and is rejected."""
        prev = {"charge_energy_today": 0.0}
        curr = {"charge_energy_today": 6549.2}
        assert not validate_daily_energy_bounds(
            curr,
            "test_dev",
            rated_power_kw=18.0,
            elapsed_seconds=72 * 3600,
            prev_values=prev,
        )

    # -- No elapsed time (cache_time was None) --

    def test_no_elapsed_time_with_prev_only_checks_absolute(self) -> None:
        """When elapsed_seconds is None, only absolute cap applies."""
        prev = {"charge_energy_today": 0.0}
        curr = {"charge_energy_today": 400.0}
        # No elapsed → no delta check, but 400 < 864 abs cap → pass
        assert validate_daily_energy_bounds(
            curr,
            "test_dev",
            rated_power_kw=18.0,
            elapsed_seconds=None,
            prev_values=prev,
        )

    # -- Multiple keys: one bad key rejects all --

    def test_multiple_keys_one_corrupt_rejects_all(self) -> None:
        """If any daily key is corrupt, entire read is rejected."""
        prev = {"charge_energy_today": 5.0, "discharge_energy_today": 3.0}
        curr = {"charge_energy_today": 5.1, "discharge_energy_today": 6000.0}
        assert not validate_daily_energy_bounds(
            curr,
            "test_dev",
            rated_power_kw=18.0,
            elapsed_seconds=30.0,
            prev_values=prev,
        )

    def test_multiple_keys_all_valid_accepted(self) -> None:
        """All keys plausible → accepted."""
        prev = {"charge_energy_today": 5.0, "discharge_energy_today": 3.0}
        curr = {"charge_energy_today": 5.1, "discharge_energy_today": 3.1}
        assert validate_daily_energy_bounds(
            curr,
            "test_dev",
            rated_power_kw=18.0,
            elapsed_seconds=30.0,
            prev_values=prev,
        )


# ---------------------------------------------------------------------------
# Helpers for BaseDevice warm-up / validate_data tests
# ---------------------------------------------------------------------------


class _StubDevice(BaseDevice):
    """Minimal concrete BaseDevice for testing warm-up and gating."""

    async def refresh(self) -> None:  # pragma: no cover
        pass

    def to_device_info(self) -> DeviceInfo:  # pragma: no cover
        return DeviceInfo(identifiers=set(), name="stub", manufacturer="test", model="stub")

    def to_entities(self) -> list[Entity]:  # pragma: no cover
        return []


def _make_device(*, validate: bool = True) -> _StubDevice:
    client = MagicMock()
    client.username = "test"
    dev = _StubDevice(client, "STUB123", "StubModel")
    dev.validate_data = validate
    return dev


class TestBaseDeviceWarmUp:
    """Warm-up applies to daily bounds only; monotonicity is always-on.

    Lifetime monotonicity cannot false-positive at startup (first reads
    have no previous values), so it gets no warm-up bypass.  The warm-up
    counter exists for the daily-bounds check, where the LOCAL static
    first refresh can transition None/0 -> real mid-day values.
    """

    def test_monotonicity_active_during_warmup(self) -> None:
        """Lifetime spike rejected even on the very first reads."""
        dev = _make_device()
        prev = {"grid_import_total": 2700.0}
        # Huge jump — corrupt regardless of how early it happens
        curr = {"grid_import_total": 202_000_000.0}
        for i in range(WARMUP_READS):
            assert not dev._is_energy_valid(prev, curr), (
                f"Read {i + 1}: corrupt lifetime spike must be rejected during warm-up"
            )

    def test_first_read_with_no_prev_passes(self) -> None:
        """Genuine first reads (no previous values) always pass."""
        dev = _make_device()
        curr = {"grid_import_total": 2700.0}
        assert dev._is_energy_valid({}, curr)

    def test_validation_enforced_after_warmup(self) -> None:
        """After warm-up period, validation rejects corrupt data."""
        dev = _make_device()
        prev = {"grid_import_total": 2700.0}
        good = {"grid_import_total": 2701.0}
        corrupt = {"grid_import_total": 202_000_000.0}
        # Exhaust warm-up
        for _ in range(WARMUP_READS):
            dev._is_energy_valid(prev, good)
        # Now corrupt data should be rejected
        assert not dev._is_energy_valid(prev, corrupt)

    def test_counter_resets_on_device_recreation(self) -> None:
        """New device instance starts with fresh warm-up counter."""
        dev = _make_device()
        assert dev._energy_validation_calls == 0

    def test_daily_warmup_skips_delta_but_enforces_cap(self) -> None:
        """Warm-up skips the delta check but keeps the absolute cap.

        The short-window delta check was the false-rejection source, so
        warm-up bypasses it — but an impossibly large daily value (above
        rated*24h*2) is corrupt on any read and stays rejected.
        """
        dev = _make_device()
        dev._rated_power_kw = 18.0
        # Call _is_energy_valid first to increment counter
        dev._is_energy_valid({}, {})
        plausible = {"charge_energy_today": 8.8}
        assert dev._is_daily_energy_valid(plausible, None)
        # Warm-up seeds the change clock so the first gated read has a
        # bounded window instead of the lenient absolute cap.
        assert dev._daily_energy_change_monotonic is not None
        corrupt_daily = {"charge_energy_today": 6549.2}  # > 18*24*2 = 864
        assert not dev._is_daily_energy_valid(corrupt_daily, None)


class TestBaseDeviceValidateDataGating:
    """validate_data gates daily bounds, NOT lifetime monotonicity."""

    def test_monotonicity_not_gated_by_validate_data(self) -> None:
        """Lifetime monotonicity stays active with validate_data=False.

        Lifetime counters feed HA total_increasing statistics; a corrupt
        rollback or spike corrupts long-term stats permanently.  Users who
        disable canary validation (which can false-positive) must not lose
        this protection — monotonicity cannot false-positive.
        """
        dev = _make_device(validate=False)
        for _ in range(WARMUP_READS + 1):
            dev._is_energy_valid({}, {})
        prev = {"grid_import_total": 2700.0}
        curr = {"grid_import_total": 202_000_000.0}
        assert not dev._is_energy_valid(prev, curr)

    def test_daily_energy_valid_when_disabled(self) -> None:
        """_is_daily_energy_valid returns True when validate_data=False."""
        dev = _make_device(validate=False)
        # Exhaust warm-up
        for _ in range(WARMUP_READS + 1):
            dev._is_energy_valid({}, {})
        corrupt = {"charge_energy_today": 6549.2}
        assert dev._is_daily_energy_valid(corrupt, None)


class TestMinDailyDelta:
    """Test MIN_DAILY_DELTA floor on delta_bound."""

    def test_floor_prevents_false_rejection(self) -> None:
        """Delta bound never drops below MIN_DAILY_DELTA (register resolution).

        With a very short elapsed (5s), the computed bound would be
        18 * (5/3600) * 2 = 0.05 kWh, below the 0.1 register resolution.
        The floor ensures 0.1 is still accepted.
        """
        prev = {"charge_energy_today": 5.0}
        curr = {"charge_energy_today": 5.1}  # +0.1 (minimum register tick)
        assert validate_daily_energy_bounds(
            curr,
            "test_dev",
            rated_power_kw=18.0,
            elapsed_seconds=5.0,
            prev_values=prev,
        )

    def test_floor_value(self) -> None:
        """MIN_DAILY_DELTA matches energy register resolution (0.1 kWh)."""
        assert MIN_DAILY_DELTA == 0.1

    def test_corrupt_spike_still_rejected(self) -> None:
        """Floor doesn't weaken protection against large corrupt spikes."""
        prev = {"charge_energy_today": 0.0}
        curr = {"charge_energy_today": 6549.2}
        assert not validate_daily_energy_bounds(
            curr,
            "test_dev",
            rated_power_kw=18.0,
            elapsed_seconds=5.0,
            prev_values=prev,
        )


class TestDailyEnergyChangeTracking:
    """Test BaseDevice._is_daily_energy_valid() change-time tracking.

    Verifies that elapsed time is computed from the last value *change*
    (not last read), preventing false rejections when registers sit
    unchanged for several polls before ticking.
    """

    def _make(self) -> _StubDevice:
        dev = _make_device()
        dev._rated_power_kw = 18.0
        # Exhaust warm-up so validation is active
        for _ in range(WARMUP_READS + 1):
            dev._is_energy_valid({}, {})
        return dev

    def test_first_gated_read_seeds_clock_and_accepts(self) -> None:
        """First gated read with no window yet seeds the clock.

        When warm-up never reached the daily helper, the first gated read
        establishes the baseline window instead of falling back to the
        lenient 24h absolute cap (review finding: a corrupt spike below
        rated_kw*24h*2 would have been accepted on that read).
        """
        dev = self._make()
        curr = {"charge_energy_today": 8.8}
        assert dev._is_daily_energy_valid(curr, None)
        assert dev._daily_energy_change_monotonic is not None

    def test_spike_after_seeding_rejected(self) -> None:
        """A corrupt spike right after the seeding read is rejected.

        The seed gives the next read a real (short) window, so the old
        elapsed=None leniency no longer applies.
        """
        dev = self._make()
        prev = {"charge_energy_today": 5.0}
        assert dev._is_daily_energy_valid(prev, None)  # seeds clock
        curr = {"charge_energy_today": 500.0}  # below 18*24*2=864 abs cap
        assert not dev._is_daily_energy_valid(curr, prev)

    def test_unchanged_values_do_not_update_change_time(self) -> None:
        """Unchanged daily values leave the change clock untouched."""
        dev = self._make()
        values = {"charge_energy_today": 5.0}
        assert dev._is_daily_energy_valid(values, values)  # seeds clock
        seeded = dev._daily_energy_change_monotonic
        assert dev._is_daily_energy_valid(values, values)
        assert dev._daily_energy_change_monotonic == seeded

    def test_increase_stamps_change_time(self) -> None:
        """An accepted daily increase advances the change clock."""
        dev = self._make()
        prev = {"charge_energy_today": 5.0}
        assert dev._is_daily_energy_valid(prev, None)  # seeds clock
        seeded = dev._daily_energy_change_monotonic
        assert seeded is not None
        curr = {"charge_energy_today": 5.1}
        assert dev._is_daily_energy_valid(curr, prev)
        assert dev._daily_energy_change_monotonic is not None
        assert dev._daily_energy_change_monotonic >= seeded

    def test_decrease_does_not_stamp_change_time(self) -> None:
        """Midnight reset (decrease) does not advance the change clock."""
        dev = self._make()
        prev = {"charge_energy_today": 12.0}
        assert dev._is_daily_energy_valid(prev, None)  # seeds clock
        seeded = dev._daily_energy_change_monotonic
        curr = {"charge_energy_today": 0.0}
        assert dev._is_daily_energy_valid(curr, prev)
        assert dev._daily_energy_change_monotonic == seeded

    def test_elapsed_from_last_change_not_last_read(self) -> None:
        """Elapsed is computed from the change clock, not read time.

        Simulates: register unchanged for 60s (6 polls), then ticks +0.1.
        The elapsed window should cover all 60s.
        """
        dev = self._make()
        dev._daily_energy_change_monotonic = time.monotonic() - 60

        prev = {"charge_energy_today": 5.0}
        curr = {"charge_energy_today": 5.1}
        # delta_bound = max(18 * (60/3600) * 2.0, 0.1) = max(0.6, 0.1) = 0.6
        # 0.1 < 0.6 → accepted
        assert dev._is_daily_energy_valid(curr, prev)

    def test_unchanged_polls_then_tick_through_helper(self) -> None:
        """Production scenario: N unchanged polls, then a +0.1 tick.

        Live on prod (v3.4.0-beta.3, 21 kW system at 8s polls):
        'inverter_energy_today jumped 5.5 -> 5.6 (delta 0.1 > 0.1 max,
        21 kW × 8.1s elapsed × 2x margin)' fired on every register tick.
        With change-clock elapsed, the unchanged polls accumulate window
        and the tick is accepted.
        """
        dev = self._make()
        values = {"charge_energy_today": 5.5}
        assert dev._is_daily_energy_valid(values, None)  # seeds clock
        # Several polls with no change — window keeps growing
        for _ in range(6):
            assert dev._is_daily_energy_valid(values, values)
        # Simulate 60s having passed since the seed
        dev._daily_energy_change_monotonic = time.monotonic() - 60
        tick = {"charge_energy_today": 5.6}
        assert dev._is_daily_energy_valid(tick, values)

    def test_short_elapsed_with_min_delta_floor(self) -> None:
        """Very short elapsed (1s) still accepts 0.1 kWh due to floor."""
        dev = self._make()
        dev._daily_energy_change_monotonic = time.monotonic() - 1

        prev = {"charge_energy_today": 5.0}
        curr = {"charge_energy_today": 5.1}
        # Computed bound = 18 * (1/3600) * 2.0 = 0.01
        # Floor at 0.1 → delta_bound = 0.1
        # 0.1 <= 0.1 → accepted
        assert dev._is_daily_energy_valid(curr, prev)

    def test_corrupt_spike_rejected_despite_long_elapsed(self) -> None:
        """Large corrupt spike still rejected even with generous elapsed."""
        dev = self._make()
        dev._daily_energy_change_monotonic = time.monotonic() - 60

        prev = {"charge_energy_today": 0.0}
        curr = {"charge_energy_today": 6549.2}
        assert not dev._is_daily_energy_valid(curr, prev)


class TestUpwardSelfHealCeiling:
    """Upward self-heal must never accept an absurd lifetime baseline."""

    def test_absurd_value_never_self_heals(self) -> None:
        """Values above MAX_LIFETIME_KWH stay rejected past the threshold.

        The HTTP path has no transport is_corrupt() canary in front of
        monotonicity, so a persistently corrupt huge value (e.g. high-word
        bit flip) must not become the baseline through repetition.
        """
        prev = {"grid_import_total": 2700.0}
        curr = {"grid_import_total": 2_000_000.0}
        count = 0
        for _ in range(10):
            result, count = validate_energy_monotonicity(prev, curr, count, "dev1")
            assert result == "reject"

    def test_downward_to_absurd_value_never_self_heals(self) -> None:
        """Downward self-heal also respects the ceiling.

        If the previous baseline was already absurd (e.g. accepted via an
        HTTP first read, which has no canary), a "drop" to a still-absurd
        value must keep rejecting rather than re-baseline.
        """
        prev = {"grid_import_total": 90_000_000.0}
        curr = {"grid_import_total": 5_000_000.0}  # lower, still absurd
        count = 0
        for _ in range(10):
            result, count = validate_energy_monotonicity(prev, curr, count, "dev1")
            assert result == "reject"

    def test_plausible_jump_self_heals_at_threshold(self) -> None:
        """A sub-ceiling stable jump re-baselines after 5 rejections.

        A device offline for a week comes back with a large but plausible
        jump — it must be able to re-baseline.  If the jump was actually
        corrupt, the downward self-heal (3 rejections) restores the true
        baseline once real values return.
        """
        prev = {"grid_import_total": 2700.0}
        curr = {"grid_import_total": 5000.0}  # +2300 kWh, > max_delta, < ceiling
        count = 0
        results = []
        for _ in range(5):
            result, count = validate_energy_monotonicity(prev, curr, count, "dev1")
            results.append(result)
        assert results[:4] == ["reject"] * 4
        assert results[4] == "self_healed"
