"""Battery RS485 protocol definitions.

Each protocol defines register maps as pure data structures.
No I/O code --- decoding only.
"""

from __future__ import annotations

from .base import BatteryProtocol, BatteryRegister, BatteryRegisterBlock
from .detection import detect_protocol
from .eg4_master import EG4MasterProtocol
from .eg4_slave import EG4SlaveProtocol

__all__ = [
    "BatteryProtocol",
    "BatteryRegister",
    "BatteryRegisterBlock",
    "EG4MasterProtocol",
    "EG4SlaveProtocol",
    "detect_protocol",
]
