"""Energy monotonicity validation for lifetime energy counters.

Detects corrupt lifetime kWh values using bidirectional spike detection
with counter-based self-healing.  Used internally by device ``refresh()``
methods so that corrupt data is rejected before it reaches any consumer.

Validation checks:
- **Upward spike**: A jump larger than the device's ``max_delta`` (computed
  as ``rated_power_kw * 1.5``) is rejected.  Catches corrupt register reads
  like 25K -> 202M.
- **Downward drop**: Any decrease in a lifetime counter violates
  monotonicity and is rejected.
- **Self-healing**: After ``SELF_HEAL_THRESHOLD`` consecutive rejections of
  the *same* direction (downward only), accept the new value as a baseline
  reset — but only if it exceeds ``MIN_LIFETIME_KWH`` (to avoid accepting
  obviously wrong near-zero values).
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
