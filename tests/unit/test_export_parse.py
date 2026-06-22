"""Tests for parsing the .xls data export into per-day sheets."""

from __future__ import annotations

import datetime
import io

import pytest

from pylxpweb.endpoints.export import ExportDaySheet, ExportEndpoints, parse_export
from pylxpweb.exceptions import LuxpowerAPIError

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


def test_parse_export_duplicate_headers_are_disambiguated_not_dropped() -> None:
    # Two columns sharing a header would collapse in a {header: value} dict,
    # silently losing the first column. Repeated names must be suffixed so every
    # column survives.
    content = _build_xls({"2025-11-19": [["SOC", "Time", "SOC"], ["95", "00:00:00", "96"]]})

    sheets = parse_export(content)

    assert sheets[0].rows == [{"SOC": "95", "Time": "00:00:00", "SOC.1": "96"}]


def test_parse_export_duplicate_header_collides_with_literal_suffix() -> None:
    # A generated suffix must not collide with a literal one already present:
    # ["SOC", "SOC.1", "SOC"] must become three distinct keys, not drop a column.
    content = _build_xls({"2025-11-19": [["SOC", "SOC.1", "SOC"], ["a", "b", "c"]]})

    sheets = parse_export(content)

    assert sheets[0].rows == [{"SOC": "a", "SOC.1": "b", "SOC.2": "c"}]
    assert len(sheets[0].rows[0]) == 3  # no column silently lost


def test_parse_export_header_only_sheet_has_no_rows() -> None:
    content = _build_xls({"2025-11-19": [["Time", "SOC"]]})

    sheets = parse_export(content)

    assert sheets[0].day == "2025-11-19"
    assert sheets[0].rows == []


def test_parse_export_date_typed_time_cell_renders_iso() -> None:
    # A date-TYPED Time cell is an Excel serial under the hood; it must come back
    # as an ISO string, not "45980.003". The all-string fixtures above can't
    # exercise this — a real export's Time column may be either type by firmware.
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("2026-06-19")
    sheet.write(0, 0, "Time")
    sheet.write(0, 1, "SOC")
    date_style = xlwt.XFStyle()
    date_style.num_format_str = "YYYY-MM-DD HH:MM:SS"
    sheet.write(1, 0, datetime.datetime(2026, 6, 19, 0, 1, 1), date_style)
    sheet.write(1, 1, "60%")
    buffer = io.BytesIO()
    workbook.save(buffer)

    sheets = parse_export(buffer.getvalue())

    assert sheets[0].rows == [{"Time": "2026-06-19 00:01:01", "SOC": "60%"}]


def test_parse_export_empty_bytes_raises_library_error() -> None:
    with pytest.raises(LuxpowerAPIError):
        parse_export(b"")


def test_parse_export_non_xls_bytes_raises_library_error() -> None:
    with pytest.raises(LuxpowerAPIError):
        parse_export(b"this is plainly not a BIFF workbook")


def test_parse_export_xlsx_bytes_raise_library_error() -> None:
    # A modern .xlsx (ZIP/PK magic), not legacy BIFF .xls, must surface as a
    # library exception rather than leaking zipfile.BadZipFile / XLRDError.
    with pytest.raises(LuxpowerAPIError):
        parse_export(b"PK\x03\x04" + b"\x00" * 64)


def test_parse_export_truncated_xls_raises_library_error() -> None:
    # A truncated download opens partway, then dies inside xlrd with a bare
    # IndexError / struct.error; that must surface as a library exception.
    full = _build_xls({"2025-11-19": [["Time", "SOC"], ["2025-11-19 00:00:00", "95"]]})
    with pytest.raises(LuxpowerAPIError):
        parse_export(full[: len(full) // 2])


def test_parse_export_out_of_range_date_serial_raises_library_error() -> None:
    # A date-typed cell with an out-of-range serial makes xldate_as_datetime
    # raise OverflowError mid-parse; that must surface as a library exception.
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("2025-11-19")
    sheet.write(0, 0, "Time")
    date_style = xlwt.XFStyle()
    date_style.num_format_str = "YYYY-MM-DD HH:MM:SS"
    sheet.write(1, 0, 9_000_000, date_style)  # date-typed, serial far out of range
    buffer = io.BytesIO()
    workbook.save(buffer)
    with pytest.raises(LuxpowerAPIError):
        parse_export(buffer.getvalue())


class _StubExport(ExportEndpoints):
    """ExportEndpoints with the network download stubbed out."""

    def __init__(self, content: bytes) -> None:
        self._content = content

    async def export_data(
        self, serial_num: str, start_date: str, end_date: str | None = None
    ) -> bytes:
        return self._content


async def test_export_and_parse_offloads_parse_to_a_worker_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Guards the asyncio.to_thread offload itself: a regression back to a direct
    # `return parse_export(content)` would run on the event-loop thread and fail
    # the thread-id assertion, not just pass on the parsed result.
    import threading

    from pylxpweb.endpoints import export as export_mod

    content = _build_xls({"2026-06-19": [["Time", "SOC"], ["2026-06-19 00:00:00", "95"]]})
    main_thread = threading.get_ident()
    parse_thread: dict[str, int] = {}
    real_parse = export_mod.parse_export

    def spy(data: bytes) -> list[ExportDaySheet]:
        parse_thread["id"] = threading.get_ident()
        return real_parse(data)

    monkeypatch.setattr(export_mod, "parse_export", spy)

    sheets = await _StubExport(content).export_and_parse("SN", "2026-06-19")

    assert parse_thread["id"] != main_thread  # parse ran off the event loop
    assert sheets[0].rows == [{"Time": "2026-06-19 00:00:00", "SOC": "95"}]
