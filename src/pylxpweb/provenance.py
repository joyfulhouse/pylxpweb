"""Evidence attached to energy values, without inferring measurement or reset time."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Any, Literal


@dataclass(frozen=True)
class EnergyProvenance:
    """Origin of one field or a derived value's individual contributors.

    ``acquired_at`` is when the library received a response, not when the
    device measured it. Cloud responses can contain stale device readings.
    ``measured_at``, ``counter_day`` and ``reset_timezone`` remain unknown
    unless supported by an explicit upstream contract. Derived nodes retain
    every component and do not assign a new acquisition time to their values.
    """

    source: Literal["local", "http", "unknown", "derived"]
    source_id: str
    acquired_at: datetime | None = None
    measured_at: datetime | None = None
    counter_day: date | None = None
    reset_timezone: str | None = None
    components: tuple[EnergyProvenance, ...] = ()
    field_name: str | None = None

    def __post_init__(self) -> None:
        for name in ("acquired_at", "measured_at"):
            value = getattr(self, name)
            if value is not None:
                if value.tzinfo is None or value.utcoffset() is None:
                    raise ValueError(f"{name} must be timezone-aware")
                object.__setattr__(self, name, value.astimezone(UTC))


def unknown_provenance(source_id: str, *, field_name: str | None = None) -> EnergyProvenance:
    """Represent a contributor whose acquisition evidence is unavailable."""
    return EnergyProvenance(source="unknown", source_id=source_id, field_name=field_name)


def derived_provenance(
    source_id: str,
    components: Iterable[EnergyProvenance | None],
    *,
    field_name: str | None = None,
) -> EnergyProvenance:
    """Preserve mixed-age and unknown components without dating the aggregate."""
    return EnergyProvenance(
        source="derived",
        source_id=source_id,
        field_name=field_name,
        components=tuple(
            component if component is not None else unknown_provenance("unknown")
            for component in components
        ),
    )


def _utc_now() -> datetime:
    """Read the UTC reception clock separately from cache expiry bookkeeping."""
    return datetime.now(UTC)


class _HTTPResponse(dict[str, Any]):
    """Keep receive evidence with its exact payload through caches and retries."""

    def __init__(self, payload: dict[str, Any], *, source_id: str, acquired_at: datetime) -> None:
        super().__init__(payload)
        self._acquisition = EnergyProvenance(
            source="http", source_id=source_id, acquired_at=acquired_at
        )


def _http_field_provenance(
    response: dict[str, Any],
    fields: Iterable[str],
    *,
    values: Mapping[str, Any] | None = None,
) -> dict[str, EnergyProvenance]:
    """Trust only locally captured response metadata, never server JSON fields."""
    if not isinstance(response, _HTTPResponse):
        return {}
    payload = response if values is None else values
    return {
        name: replace(response._acquisition, field_name=name)
        for name in fields
        if payload.get(name) is not None
    }
