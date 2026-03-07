"""Tests for energy validation (monotonicity + daily bounds)."""

from __future__ import annotations

from unittest.mock import MagicMock

from pylxpweb.devices.base import WARMUP_READS, BaseDevice
from pylxpweb.devices.models import DeviceInfo, Entity
from pylxpweb.validation import (
    DAILY_ENERGY_MARGIN,
    DEFAULT_RATED_POWER_KW,
    MAX_ELAPSED_HOURS,
    MAX_ENERGY_DELTA,
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
    """Warm-up period bypasses energy validation for first N reads."""

    def test_first_reads_accepted_during_warmup(self) -> None:
        """First WARMUP_READS calls accept data regardless of delta."""
        dev = _make_device()
        prev = {"grid_import_total": 2700.0}
        # Huge jump that would normally be rejected
        curr = {"grid_import_total": 202_000_000.0}
        for i in range(WARMUP_READS):
            assert dev._is_energy_valid(prev, curr), f"Read {i + 1} should pass during warm-up"

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

    def test_daily_energy_bypassed_during_warmup(self) -> None:
        """_is_daily_energy_valid also bypassed during warm-up."""
        dev = _make_device()
        corrupt_daily = {"charge_energy_today": 6549.2}
        # Call _is_energy_valid first to increment counter
        dev._is_energy_valid({}, {})
        assert dev._is_daily_energy_valid(corrupt_daily, None, None)


class TestBaseDeviceValidateDataGating:
    """validate_data=False disables all energy validation."""

    def test_energy_valid_when_disabled(self) -> None:
        """_is_energy_valid returns True when validate_data=False."""
        dev = _make_device(validate=False)
        # Exhaust warm-up
        for _ in range(WARMUP_READS + 1):
            dev._is_energy_valid({}, {})
        prev = {"grid_import_total": 2700.0}
        curr = {"grid_import_total": 202_000_000.0}
        assert dev._is_energy_valid(prev, curr)

    def test_daily_energy_valid_when_disabled(self) -> None:
        """_is_daily_energy_valid returns True when validate_data=False."""
        dev = _make_device(validate=False)
        # Exhaust warm-up
        for _ in range(WARMUP_READS + 1):
            dev._is_energy_valid({}, {})
        corrupt = {"charge_energy_today": 6549.2}
        assert dev._is_daily_energy_valid(corrupt, None, None)
