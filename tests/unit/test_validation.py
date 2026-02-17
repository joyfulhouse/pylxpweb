"""Tests for energy monotonicity validation."""

from __future__ import annotations

from pylxpweb.validation import (
    MAX_ENERGY_DELTA,
    MIN_LIFETIME_KWH,
    SELF_HEAL_THRESHOLD,
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
        assert count == 0  # upward spike resets count

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
        assert count == 0

    def test_self_heal_exactly_at_min_threshold(self) -> None:
        """Value exactly at MIN_LIFETIME_KWH allows self-heal."""
        prev = {"grid_import_total": 50000.0}
        curr = {"grid_import_total": MIN_LIFETIME_KWH}
        result, count = validate_energy_monotonicity(
            prev, curr, SELF_HEAL_THRESHOLD - 1, "test_dev"
        )
        assert result == "self_healed"
        assert count == 0
