"""CSV formatter for diagnostic output.

Generates CSV output suitable for import into spreadsheets.
One row per register with values from each collection source.
"""

from __future__ import annotations

import csv
import io

from pylxpweb.cli.collectors.base import CollectionResult

from .base import DiagnosticData


class CSVFormatter:
    """Format diagnostic data as CSV.

    Produces a CSV file with columns:
    - register_type: "input" or "holding"
    - address: Register address
    - [source1_value, source2_value, ...]: Value from each collection
    - match: Whether all values match

    Suitable for import into Excel, Google Sheets, etc.
    """

    def __init__(
        self,
        sanitize: bool = True,
        include_metadata: bool = True,
    ) -> None:
        """Initialize CSV formatter.

        Args:
            sanitize: Whether to mask sensitive data in headers
            include_metadata: Include metadata rows at top
        """
        self._sanitize = sanitize
        self._include_metadata = include_metadata

    @property
    def file_extension(self) -> str:
        """Return file extension."""
        return "csv"

    @property
    def is_binary(self) -> bool:
        """Return False - CSV is text."""
        return False

    def format(self, data: DiagnosticData) -> str:
        """Generate CSV output.

        Args:
            data: Diagnostic data to format

        Returns:
            CSV string
        """
        output = io.StringIO()
        writer = csv.writer(output)

        # Metadata rows (if enabled)
        if self._include_metadata:
            writer.writerow(["# Modbus Diagnostic Report"])
            writer.writerow(["# Serial", self._sanitize_serial(data.serial_number)])
            if data.firmware_version:
                writer.writerow(["# Firmware", data.firmware_version])
            writer.writerow(["# Timestamp", data.timestamp.isoformat()])
            writer.writerow([])  # Empty row separator

        # Get all source names
        sources = [c.source for c in data.collections]

        # Header row
        header = ["register_type", "address"]
        for source in sources:
            header.append(f"{source}_value")
            header.append(f"{source}_hex")
        header.append("match")
        writer.writerow(header)

        # Input registers
        all_input_addrs = self._get_all_addresses(data.collections, "input")
        for addr in sorted(all_input_addrs):
            row = self._format_register_row(data.collections, "input", addr)
            writer.writerow(row)

        # Holding registers
        all_hold_addrs = self._get_all_addresses(data.collections, "holding")
        for addr in sorted(all_hold_addrs):
            row = self._format_register_row(data.collections, "holding", addr)
            writer.writerow(row)

        return output.getvalue()

    def _get_all_addresses(
        self,
        collections: list[CollectionResult],
        reg_type: str,
    ) -> set[int]:
        """Get all unique register addresses across collections."""
        addrs: set[int] = set()
        for c in collections:
            regs = c.input_registers if reg_type == "input" else c.holding_registers
            addrs.update(regs.keys())
        return addrs

    def _format_register_row(
        self,
        collections: list[CollectionResult],
        reg_type: str,
        address: int,
    ) -> list[str]:
        """Format a single register row."""
        row = [reg_type, str(address)]

        values: list[int | None] = []
        for c in collections:
            regs = c.input_registers if reg_type == "input" else c.holding_registers
            val = regs.get(address)
            values.append(val)

            # Add decimal and hex values
            if val is not None:
                row.append(str(val))
                row.append(f"0x{val:04X}")
            else:
                row.append("")
                row.append("")

        # Check match
        non_null = [v for v in values if v is not None]
        if len(non_null) <= 1:
            match = ""  # Not enough values to compare
        elif len(set(non_null)) == 1:
            match = "true"
        else:
            match = "false"

        row.append(match)
        return row

    def _sanitize_serial(self, serial: str) -> str:
        """Mask serial number if sanitization is enabled."""
        if not self._sanitize or not serial or len(serial) < 4:
            return serial
        return f"{serial[:2]}{'*' * (len(serial) - 4)}{serial[-2:]}"
