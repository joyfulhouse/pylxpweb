"""Data export endpoints for the Luxpower API.

This module provides data export functionality for downloading
historical runtime data in CSV or Excel formats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import aiohttp

from pylxpweb.endpoints.base import BaseEndpoint
from pylxpweb.exceptions import LuxpowerConnectionError

if TYPE_CHECKING:
    from pylxpweb.client import LuxpowerClient


@dataclass
class ExportDaySheet:
    """One day of exported rows from the .xls data export.

    The export workbook holds one worksheet per day (named ``YYYY-MM-DD``), each
    with a header row followed by one row per logging interval. Cell values are
    already in display units.

    Attributes:
        day: The worksheet name, a ``YYYY-MM-DD`` date.
        rows: Header -> raw string cell value, one dict per interval.
    """

    day: str
    rows: list[dict[str, str]] = field(default_factory=list)


def parse_export(content: bytes) -> list[ExportDaySheet]:
    """Parse the bytes from :meth:`ExportEndpoints.export_data` into day sheets.

    The data export is a legacy BIFF (``.xls``) workbook with one worksheet per
    day. The server caps it at 10 day-sheets anchored at ``start_date`` going
    forward, so request windows of 10 days or fewer and parse every sheet (the
    later days past the cap are dropped, not the earlier ones).

    Args:
        content: Raw ``.xls`` bytes from ``export_data``.

    Returns:
        One :class:`ExportDaySheet` per worksheet, in workbook order.

    Raises:
        ImportError: If the optional ``xlrd`` dependency is not installed.
    """
    try:
        import xlrd  # type: ignore[import-untyped]
    except ImportError as err:
        raise ImportError(
            "Parsing the .xls export requires xlrd; install it with 'pip install pylxpweb[parse]'."
        ) from err

    workbook = xlrd.open_workbook(file_contents=content)
    sheets: list[ExportDaySheet] = []
    for index in range(workbook.nsheets):
        sheet = workbook.sheet_by_index(index)
        if sheet.nrows < 2:
            sheets.append(ExportDaySheet(day=sheet.name))
            continue
        headers = [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
        rows = [
            {header: _coerce_cell(sheet.cell_value(row, col)) for col, header in enumerate(headers)}
            for row in range(1, sheet.nrows)
        ]
        sheets.append(ExportDaySheet(day=sheet.name, rows=rows))
    return sheets


def _coerce_cell(value: object) -> str:
    """Render a cell as text, dropping the trailing ``.0`` xlrd gives integers."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


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
            LuxpowerAPIError: If export fails

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

        Args:
            serial_num: Device serial number
            start_date: Start date in YYYY-MM-DD format
            end_date: Optional end date. Keep the window to 10 days or fewer
                (see :func:`parse_export`).

        Returns:
            list[ExportDaySheet]: One day sheet per worksheet in the export.

        Raises:
            ImportError: If the optional ``xlrd`` dependency is not installed.
            LuxpowerAPIError: If the export download fails.
        """
        content = await self.export_data(serial_num, start_date, end_date)
        return parse_export(content)
