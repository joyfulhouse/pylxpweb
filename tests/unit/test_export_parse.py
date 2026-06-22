"""Tests for parsing the .xls data export into per-day sheets."""

from __future__ import annotations

import io

import pytest

from pylxpweb.endpoints.export import ExportDaySheet, parse_export

xlwt = pytest.importorskip("xlwt")


def _build_xls(sheets: dict[str, list[list[object]]]) -> bytes:
    """Build a minimal legacy .xls workbook from {sheet_name: rows}."""
    workbook = xlwt.Workbook()
    for name, rows in sheets.items():
        sheet = workbook.add_sheet(name)
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                sheet.write(r, c, value)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_parse_export_one_sheet_per_day_in_order() -> None:
    content = _build_xls(
        {
            "2025-11-18": [["Time", "SOC"], ["2025-11-18 00:00:00", "95"]],
            "2025-11-19": [
                ["Time", "SOC"],
                ["2025-11-19 00:00:00", "90"],
                ["2025-11-19 00:05:00", "91"],
            ],
        }
    )

    sheets = parse_export(content)

    assert [s.day for s in sheets] == ["2025-11-18", "2025-11-19"]
    assert isinstance(sheets[0], ExportDaySheet)
    assert sheets[0].rows == [{"Time": "2025-11-18 00:00:00", "SOC": "95"}]
    assert len(sheets[1].rows) == 2
    assert sheets[1].rows[1] == {"Time": "2025-11-19 00:05:00", "SOC": "91"}


def test_parse_export_integer_cells_render_without_decimal() -> None:
    # xlwt stores numbers as floats; integer-valued cells must stringify cleanly.
    content = _build_xls({"2025-11-19": [["SOC"], [95]]})

    sheets = parse_export(content)

    assert sheets[0].rows == [{"SOC": "95"}]


def test_parse_export_header_only_sheet_has_no_rows() -> None:
    content = _build_xls({"2025-11-19": [["Time", "SOC"]]})

    sheets = parse_export(content)

    assert sheets[0].day == "2025-11-19"
    assert sheets[0].rows == []
