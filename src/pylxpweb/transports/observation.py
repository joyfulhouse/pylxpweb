"""Public raw-register observation types for local transport reads."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class RegisterSpace(StrEnum):
    """Modbus register space for an observed raw-register read."""

    INPUT = "input"
    HOLDING = "holding"


@dataclass(frozen=True, slots=True, repr=False)
class RegisterSegment:
    """One immutable raw-register segment from a successful public read."""

    start_address: int
    """First register address covered by ``words``."""

    words: tuple[int, ...]
    """Exact raw 16-bit register words in observation order."""

    def __repr__(self) -> str:
        """Return provenance without exposing raw register words."""
        return (
            f"{type(self).__name__}(start_address={self.start_address!r}, "
            f"word_count={len(self.words)}, words=<redacted>)"
        )


@dataclass(frozen=True, slots=True)
class RegisterObservation:
    """Observed raw-register segments for one register space."""

    register_space: RegisterSpace
    """Register space shared by every segment in ``segments``."""

    segments: tuple[RegisterSegment, ...]
    """Ordered, immutable, non-overlapping raw-register segments."""


type RegisterObserver = Callable[[tuple[RegisterObservation, ...]], None]
"""Observer callback for successful local raw-register reads."""


__all__ = [
    "RegisterObservation",
    "RegisterObserver",
    "RegisterSegment",
    "RegisterSpace",
]
