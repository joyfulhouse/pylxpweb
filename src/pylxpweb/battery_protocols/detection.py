"""Auto-detection of battery protocol from raw register values.

The master battery (unit ID 1) has registers 0-18 all zeros, with data
starting at register 19. Slave batteries (unit ID 2+) have voltage at
register 0 and current at register 1.
"""

from __future__ import annotations

from .base import BatteryProtocol
from .eg4_master import EG4MasterProtocol
from .eg4_slave import EG4SlaveProtocol

_DETECTION_RANGE_START = 0
_DETECTION_RANGE_END = 19  # exclusive: checks registers 0-18
_NOISE_TOLERANCE = 2  # up to 2 non-zero registers still count as master


def detect_protocol(raw_regs: dict[int, int]) -> BatteryProtocol:
    """Detect battery protocol from raw register values.

    Checks registers 0-18: if mostly zeros, it's a master battery.
    If 3+ registers are non-zero, it's a slave battery.

    Args:
        raw_regs: Dict mapping register address to raw 16-bit value.
            Should contain at least registers 0-18 for reliable detection.

    Returns:
        Appropriate BatteryProtocol instance.
    """
    early_non_zero = sum(
        1 for r in range(_DETECTION_RANGE_START, _DETECTION_RANGE_END) if raw_regs.get(r, 0) != 0
    )
    if early_non_zero <= _NOISE_TOLERANCE:
        return EG4MasterProtocol()
    return EG4SlaveProtocol()
