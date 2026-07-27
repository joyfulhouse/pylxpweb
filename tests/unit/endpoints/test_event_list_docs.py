"""The event-list row shape is documented twice; keep the two copies honest.

``AnalyticsEndpoints.get_event_list``'s docstring and the
``EventListResponse`` row schema in ``docs/luxpower-api.yaml`` both enumerate
the fields of an event row.  Two exhaustive lists of the same open-ended API
shape drift apart the moment someone discovers another key and updates only
one of them -- which is how #236 happened in the first place.  This test
fails when they disagree.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from pylxpweb.endpoints.analytics import AnalyticsEndpoints

_SPEC = Path(__file__).resolve().parents[3] / "docs" / "luxpower-api.yaml"

# Rows are documented as "- fieldName: description", indented under
# "rows: List of event objects with:", with continuation lines indented
# further.  Only the "- name:" openers are field declarations.
#
# The name class and the trailing separator are deliberately permissive.  A
# field this regex fails to recognise is silently dropped from the extracted
# set, and if that field was added to the docstring ONLY, both the drift test
# and the guard-the-guard test still pass -- the guard would quietly stop
# guarding the one thing it exists to catch.  So underscores and digits are
# accepted anywhere after the first character, and the description may start
# on the next line (no space required after the colon).
_FIELD_LINE = re.compile(r"^\s*- (?P<name>[A-Za-z_][A-Za-z0-9_]*):(?: |$)")


def _documented_row_fields() -> set[str]:
    """Field names the get_event_list docstring declares for a row."""
    docstring = AnalyticsEndpoints.get_event_list.__doc__
    assert docstring is not None, "get_event_list lost its docstring"

    lines = docstring.splitlines()
    start = next(i for i, line in enumerate(lines) if "rows: List of event objects with:" in line)
    row_indent = len(lines[start]) - len(lines[start].lstrip())

    fields: set[str] = set()
    for line in lines[start + 1 :]:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        # Dedent back to the "rows:" level ends the row field list.
        if indent <= row_indent:
            break
        match = _FIELD_LINE.match(line)
        if match:
            fields.add(match.group("name"))
    return fields


def _spec_event_row() -> dict[str, Any]:
    """The event-row schema from docs/luxpower-api.yaml."""
    spec = yaml.safe_load(_SPEC.read_text())
    row: dict[str, Any] = spec["components"]["schemas"]["EventListResponse"]["properties"]["rows"][
        "items"
    ]
    return row


def test_docstring_and_spec_document_the_same_row_fields() -> None:
    """The two hand-maintained field lists must not drift apart."""
    documented = _documented_row_fields()
    spec_fields = set(_spec_event_row()["properties"])

    assert documented == spec_fields, (
        "get_event_list's docstring and docs/luxpower-api.yaml disagree on the "
        f"event row shape. Only in docstring: {sorted(documented - spec_fields)}; "
        f"only in spec: {sorted(spec_fields - documented)}"
    )


def test_the_field_extractor_actually_finds_fields() -> None:
    """Guard the guard: an extractor that finds nothing would pass vacuously."""
    documented = _documented_row_fields()
    # Anchor on fields whose names were the substance of #236 -- recordId and
    # status replaced the fictitious eventId and statusText.
    assert {"recordId", "status", "renormalTime"} <= documented
    assert len(documented) > 10


def test_row_shape_stays_open() -> None:
    """Rows carry undocumented keys; the spec must not forbid them."""
    row = _spec_event_row()
    assert row.get("additionalProperties") is True


def test_passthrough_fields_are_not_closed_enums() -> None:
    """Fields whose unknown values pass through cannot be modelled as enums.

    Consumers relay unrecognized ``eventType`` and ``status`` values verbatim
    rather than rejecting them, so a closed enum would contradict the
    documented behaviour.  Both are documented by observed value instead.
    """
    row = _spec_event_row()
    for field in ("eventType", "status"):
        assert "enum" not in row["properties"][field], (
            f"{field} is declared a closed enum, but unknown values are "
            "passed through — the enum would reject what the description "
            "promises to accept"
        )


def test_timestamps_are_not_declared_rfc3339() -> None:
    """Portal timestamps are naive local time, which format:date-time rejects."""
    row = _spec_event_row()
    for field in ("startTime", "renormalTime", "startSlashTime", "renormalSlashTime"):
        assert "format" not in row["properties"][field], (
            f"{field} carries an OpenAPI format; the portal sends naive "
            "'YYYY-MM-DD HH:MM:SS' with no offset, which fails RFC 3339 validation"
        )
