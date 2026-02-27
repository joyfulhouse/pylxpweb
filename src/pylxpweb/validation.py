"""Energy validation for pylxpweb device data.

Two validation layers:

1. **Lifetime monotonicity** — detects corrupt lifetime kWh counters using
   bidirectional spike detection with counter-based self-healing.

2. **Daily energy bounds** — detects corrupt daily kWh values by computing
   the maximum plausible increase from elapsed time and rated device power.
   Daily values can legitimately decrease (midnight reset), so only upward
   spikes are checked.

Both are used internally by device ``refresh()`` methods so that corrupt
data is rejected before it reaches any consumer.
"""

from __future__ import annotations

import logging
from typing import Literal

_LOGGER = logging.getLogger(__name__)

# Minimum plausible lifetime energy value (kWh).  Values below this are
# clearly corrupt and must not be accepted even after repeated rejections.
MIN_LIFETIME_KWH = 1000.0

# Default maximum plausible energy increase per poll cycle (kWh).
# Used as fallback when the device's rated power is unknown.
# Derived from 2-inverter system: 300A × 240V = 72kW × 1.5 margin = 108 kWh/hour.
# Devices override this with their own rated_power_kw * 1.5.
MAX_ENERGY_DELTA = 108.0

# Number of consecutive downward-drop rejections before accepting the
# "new" value as a self-healing baseline reset.
SELF_HEAL_THRESHOLD = 3

EnergyValidationResult = Literal["valid", "reject", "self_healed"]


def validate_energy_monotonicity(
    prev_values: dict[str, float | None],
    curr_values: dict[str, float | None],
    reject_count: int,
    device_id: str,
    max_delta: float = MAX_ENERGY_DELTA,
) -> tuple[EnergyValidationResult, int]:
    """Validate lifetime energy counters with bidirectional spike detection.

    Checks for both impossibly large increases (upward spikes) and
    decreases (register corruption).  Includes counter-based self-healing
    to recover from stuck corrupt baselines after repeated rejections.

    Args:
        prev_values: Previous cycle's lifetime energy dict (key -> kWh).
        curr_values: Current cycle's lifetime energy dict (key -> kWh).
        reject_count: Number of consecutive prior rejections for this device.
        device_id: Device identifier for logging.
        max_delta: Maximum plausible kWh increase per cycle.  Devices pass
            their own ``rated_power_kw * 1.5`` to scale the threshold to
            their actual capacity.  Defaults to ``MAX_ENERGY_DELTA``.

    Returns:
        Tuple of (result, updated_reject_count):
        - ``"valid"``  — all checks passed, data is good.  Count reset to 0.
        - ``"reject"`` — corrupt data detected, caller should keep cached data.
        - ``"self_healed"`` — corrupt baseline recovered, accept current data.
          Count reset to 0.
    """
    for key, curr in curr_values.items():
        if curr is None:
            continue
        prev = prev_values.get(key)
        if prev is None:
            continue

        # Upward spike: impossibly large increase
        if curr > prev and (curr - prev) > max_delta:
            _LOGGER.warning(
                "%s corrupt spike rejected: %s jumped %.1f -> %.1f "
                "(delta %.1f > %.0f max) — keeping previous data",
                device_id,
                key,
                prev,
                curr,
                curr - prev,
                max_delta,
            )
            return "reject", 0

        # Downward drop: monotonicity violation
        if curr < prev:
            count = reject_count + 1

            if count >= SELF_HEAL_THRESHOLD and curr >= MIN_LIFETIME_KWH:
                _LOGGER.warning(
                    "%s corrupt baseline detected after %d consecutive "
                    "rejections: %s was %.1f, resetting to %.1f",
                    device_id,
                    count,
                    key,
                    prev,
                    curr,
                )
                return "self_healed", 0

            _LOGGER.warning(
                "%s energy monotonicity violation (%d/%d): %s decreased %.1f -> %.1f",
                device_id,
                count,
                SELF_HEAL_THRESHOLD,
                key,
                prev,
                curr,
            )
            return "reject", count

    # All keys passed — reset counter.
    return "valid", 0


# ============================================================================
# Daily energy bounds validation
# ============================================================================

# Margin factor applied to rated power when computing max plausible daily
# energy increase.  2x allows for measurement jitter and slight over-rating
# without accepting obviously corrupt values (e.g. 6549 kWh in 30 seconds).
DAILY_ENERGY_MARGIN = 2.0

# Fallback rated power (kW) when device rating is unknown.  Conservative
# upper bound — covers the largest residential inverter systems.
DEFAULT_RATED_POWER_KW = 108.0

# Maximum hours used for elapsed-time calculation.  Caps the window at 24h
# so that very long outages don't produce absurdly large bounds.
MAX_ELAPSED_HOURS = 24.0


def validate_daily_energy_bounds(
    curr_values: dict[str, float | None],
    device_id: str,
    rated_power_kw: float = 0.0,
    elapsed_seconds: float | None = None,
    prev_values: dict[str, float | None] | None = None,
) -> bool:
    """Validate daily energy values against physically plausible bounds.

    Two checks are applied in order:

    1. **Absolute cap** (always) — no daily counter can exceed
       ``rated_power * 24h * margin``.  Catches first-read corruption
       when no previous data exists.
    2. **Time-based delta** (when ``prev_values`` provided) — an increase
       larger than ``rated_power * elapsed_hours * margin`` is rejected.
       Decreases are allowed (legitimate midnight resets).

    Args:
        curr_values: Current daily energy dict (key -> kWh).
        device_id: Device identifier for logging.
        rated_power_kw: Device rated power in kW.  Zero means unknown,
            in which case ``DEFAULT_RATED_POWER_KW`` is used.
        elapsed_seconds: Seconds since last successful energy read.
            ``None`` when no previous timestamp exists (startup), which
            falls back to the absolute cap only.
        prev_values: Previous cycle's daily energy dict.  ``None`` on
            first read (only absolute cap is applied).

    Returns:
        True if all daily values are plausible, False if any should be
        rejected.
    """
    power = rated_power_kw if rated_power_kw > 0 else DEFAULT_RATED_POWER_KW
    abs_cap = power * MAX_ELAPSED_HOURS * DAILY_ENERGY_MARGIN

    # Compute time-based delta bound when we have elapsed time.
    # Cap at MAX_ELAPSED_HOURS so long outages don't weaken the bound.
    delta_bound: float | None = None
    if elapsed_seconds is not None and prev_values is not None:
        elapsed_hours = min(elapsed_seconds / 3600.0, MAX_ELAPSED_HOURS)
        delta_bound = power * elapsed_hours * DAILY_ENERGY_MARGIN

    for key, curr in curr_values.items():
        if curr is None:
            continue

        # Check 1: absolute cap — always applied
        if curr > abs_cap:
            _LOGGER.warning(
                "%s daily energy rejected: %s = %.1f kWh exceeds "
                "absolute cap %.0f kWh (%.0f kW × %dh × %.0fx)",
                device_id,
                key,
                curr,
                abs_cap,
                power,
                int(MAX_ELAPSED_HOURS),
                DAILY_ENERGY_MARGIN,
            )
            return False

        # Check 2: time-based delta — only when we have previous data
        if delta_bound is not None and prev_values is not None:
            prev = prev_values.get(key)
            if prev is not None and curr > prev:
                delta = curr - prev
                if delta > delta_bound:
                    _LOGGER.warning(
                        "%s daily energy spike rejected: %s jumped "
                        "%.1f -> %.1f (delta %.1f > %.1f max, "
                        "%.0f kW × %.1fs elapsed × %.0fx margin)",
                        device_id,
                        key,
                        prev,
                        curr,
                        delta,
                        delta_bound,
                        power,
                        elapsed_seconds,
                        DAILY_ENERGY_MARGIN,
                    )
                    return False

    return True
