"""Data export endpoints for the Luxpower API.

This module provides data export functionality for downloading
historical runtime data in CSV or Excel formats.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import aiohttp

from pylxpweb.endpoints.base import BaseEndpoint
from pylxpweb.exceptions import LuxpowerAPIError, LuxpowerConnectionError

if TYPE_CHECKING:
    from xlrd.sheet import Cell

    from pylxpweb.client import LuxpowerClient


@dataclass
class ExportDaySheet:
    """One day of exported rows from the .xls data export.

    The export workbook holds one worksheet per day (named ``YYYY-MM-DD``), each
    with a header row followed by one row per logging interval. Cell values are
    already in display units.

    Attributes:
        day: The worksheet name, a ``YYYY-MM-DD`` date.
        rows: Header -> cell value as text (date-typed cells rendered ISO
            ``YYYY-MM-DD HH:MM:SS``), one dict per logging interval.
    """

    day: str
    rows: list[dict[str, str]] = field(default_factory=list)


def parse_export(content: bytes) -> list[ExportDaySheet]:
    """Parse the bytes from :meth:`ExportEndpoints.export_data` into day sheets.

    The data export is a legacy BIFF (``.xls``) workbook with one worksheet per
    day. The server caps it at 10 day-sheets anchored at ``start_date`` going
    forward, so request windows of 10 days or fewer and parse every sheet (the
    later days past the cap are dropped, not the earlier ones).

    Cell values are returned as text. A date-typed cell is rendered with the
    workbook's date mode as ``YYYY-MM-DD HH:MM:SS`` so a date-typed ``Time``
    column can never leak an Excel serial number; on the live server that column
    is plain text, but handling both keeps the parser correct across firmware.

    Args:
        content: Raw ``.xls`` bytes from ``export_data``.

    Returns:
        One :class:`ExportDaySheet` per worksheet, in workbook order.

    Raises:
        ImportError: If the optional ``xlrd`` dependency is not installed.
        LuxpowerAPIError: If ``content`` is empty or not a valid ``.xls`` workbook.
    """
    try:
        import xlrd
        from xlrd.xldate import xldate_as_datetime
    except ImportError as err:
        raise ImportError(
            "Parsing the .xls export requires xlrd; install it with 'pip install pylxpweb[parse]'."
        ) from err

    if not content:
        raise LuxpowerAPIError("Cannot parse an empty .xls export.")

    # The bytes come straight off the wire, and xlrd surfaces malformed input as
    # a grab-bag of types: XLRDError, CompDocError, BadZipFile for an .xlsx, and
    # bare IndexError/struct.error/OverflowError on a truncated or corrupt file.
    # Convert the whole parse at this boundary so a caller never sees a
    # third-party exception type leak through.
    try:
        workbook = xlrd.open_workbook(file_contents=content)
        datemode = workbook.datemode

        def cell_text(cell: Cell) -> str:
            if cell.ctype == xlrd.XL_CELL_DATE:
                return xldate_as_datetime(float(cell.value), datemode).isoformat(sep=" ")
            value = cell.value
            if isinstance(value, float) and value.is_integer():
                return str(int(value))
            return str(value).strip()

        sheets: list[ExportDaySheet] = []
        for index in range(workbook.nsheets):
            sheet = workbook.sheet_by_index(index)
            if sheet.nrows < 2:
                sheets.append(ExportDaySheet(day=sheet.name))
                continue
            headers = [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
            rows = [
                {header: cell_text(sheet.cell(row, col)) for col, header in enumerate(headers)}
                for row in range(1, sheet.nrows)
            ]
            sheets.append(ExportDaySheet(day=sheet.name, rows=rows))
        return sheets
    except Exception as err:
        raise LuxpowerAPIError(f"Could not parse the .xls export: {err}") from err


class ExportEndpoints(BaseEndpoint):
    """Data export endpoints for downloading historical data."""

    def __init__(self, client: LuxpowerClient) -> None:
        """Initialize export endpoints.

        Args:
            client: The parent LuxpowerClient instance
        """
        super().__init__(client)

    async def export_data(
        self,
        serial_num: str,
        start_date: str,
        end_date: str | None = None,
    ) -> bytes:
        """Export historical data to CSV/Excel.

        Downloads historical runtime data for the specified date range.
        Returns binary data (CSV or Excel format) for external analysis.

        Args:
            serial_num: Device serial number
            start_date: Start date in YYYY-MM-DD format
            end_date: Optional end date (if None, exports single day)

        Returns:
            bytes: CSV/Excel file content

        Raises:
            LuxpowerConnectionError: If the export download fails.

        Example:
            # Export single day
            csv_data = await client.export.export_data("1234567890", "2025-11-19")
            with open("data.csv", "wb") as f:
                f.write(csv_data)

            # Export date range
            csv_data = await client.export.export_data(
                "1234567890",
                "2025-11-01",
                "2025-11-19"
            )

        Note:
            This is a GET request that returns binary data, not JSON.
        """
        await self.client._ensure_authenticated()

        session = await self.client._get_session()
        url_path = f"/WManage/web/analyze/data/export/{serial_num}/{start_date}"

        if end_date:
            url_path += f"?endDateText={end_date}"

        url = urljoin(self.client.base_url, url_path)

        try:
            async with session.get(url) as response:
                response.raise_for_status()
                return await response.read()

        except aiohttp.ClientError as err:
            raise LuxpowerConnectionError(f"Export failed: {err}") from err

    async def export_and_parse(
        self,
        serial_num: str,
        start_date: str,
        end_date: str | None = None,
    ) -> list[ExportDaySheet]:
        """Download and parse the data export in one call.

        Convenience wrapper over :meth:`export_data` and :func:`parse_export`.
        The synchronous parse runs in a worker thread (``asyncio.to_thread``) so
        it never blocks the event loop while xlrd decodes a large export.

        Args:
            serial_num: Device serial number
            start_date: Start date in YYYY-MM-DD format
            end_date: Optional end date. Keep the window to 10 days or fewer
                (see :func:`parse_export`).

        Returns:
            list[ExportDaySheet]: One day sheet per worksheet in the export.

        Raises:
            ImportError: If the optional ``xlrd`` dependency is not installed.
            LuxpowerConnectionError: If the export download fails.
            LuxpowerAPIError: If the downloaded export is empty or not a valid ``.xls``.
        """
        content = await self.export_data(serial_num, start_date, end_date)
        return await asyncio.to_thread(parse_export, content)
