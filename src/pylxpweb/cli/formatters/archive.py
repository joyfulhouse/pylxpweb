"""Archive creator for diagnostic output.

Bundles all format outputs into a single ZIP file for easy sharing.
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime
from pathlib import Path

from .base import DiagnosticData, OutputFormat
from .binary import BinaryFormatter
from .csv_fmt import CSVFormatter
from .json_fmt import JSONFormatter
from .markdown import MarkdownFormatter


class ArchiveCreator:
    """Create ZIP archive containing all diagnostic output formats.

    Produces a ZIP file with:
    - diagnostic.json: Structured data
    - diagnostic.md: Human-readable report
    - diagnostic.csv: Spreadsheet data
    - diagnostic.bin: Raw binary dump
    - README.txt: Archive contents description
    """

    def __init__(
        self,
        sanitize: bool = True,
        base_filename: str = "modbus_diagnostic",
    ) -> None:
        """Initialize archive creator.

        Args:
            sanitize: Whether to mask sensitive data in outputs
            base_filename: Base name for files in archive
        """
        self._sanitize = sanitize
        self._base_filename = base_filename

        # Initialize formatters
        self._json_formatter = JSONFormatter(indent=2, sanitize=sanitize)
        self._markdown_formatter = MarkdownFormatter(sanitize=sanitize)
        self._csv_formatter = CSVFormatter(sanitize=sanitize)
        self._binary_formatter = BinaryFormatter(sanitize=sanitize)

    @property
    def file_extension(self) -> str:
        """Return file extension."""
        return "zip"

    @property
    def is_binary(self) -> bool:
        """Return True - ZIP is binary."""
        return True

    def create(
        self,
        data: DiagnosticData,
        formats: list[OutputFormat] | None = None,
    ) -> bytes:
        """Create ZIP archive with all formats.

        Args:
            data: Diagnostic data to format
            formats: List of formats to include (default: all)

        Returns:
            ZIP file as bytes
        """
        if formats is None:
            formats = OutputFormat.all_formats()

        # Create in-memory ZIP
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # Add README
            readme = self._create_readme(data)
            zf.writestr("README.txt", readme)

            # Add each requested format
            if OutputFormat.JSON in formats:
                json_content = self._json_formatter.format(data)
                zf.writestr(f"{self._base_filename}.json", json_content)

            if OutputFormat.MARKDOWN in formats:
                md_content = self._markdown_formatter.format(data)
                zf.writestr(f"{self._base_filename}.md", md_content)

            if OutputFormat.CSV in formats:
                csv_content = self._csv_formatter.format(data)
                zf.writestr(f"{self._base_filename}.csv", csv_content)

            if OutputFormat.BINARY in formats:
                bin_content = self._binary_formatter.format(data)
                zf.writestr(f"{self._base_filename}.bin", bin_content)

        return buffer.getvalue()

    def create_file(
        self,
        data: DiagnosticData,
        output_path: Path | str,
        formats: list[OutputFormat] | None = None,
    ) -> Path:
        """Create ZIP archive file.

        Args:
            data: Diagnostic data to format
            output_path: Path for output file
            formats: List of formats to include (default: all)

        Returns:
            Path to created file
        """
        output_path = Path(output_path)

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write archive
        archive_bytes = self.create(data, formats)
        output_path.write_bytes(archive_bytes)

        return output_path

    def _create_readme(self, data: DiagnosticData) -> str:
        """Create README file content."""
        lines = [
            "Modbus Diagnostic Archive",
            "=" * 50,
            "",
            f"Generated: {data.timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}",
            f"Serial: {self._sanitize_serial(data.serial_number)}",
            "",
            "Contents:",
            "---------",
            f"  {self._base_filename}.json  - Structured JSON data",
            f"  {self._base_filename}.md    - Human-readable Markdown report",
            f"  {self._base_filename}.csv   - Spreadsheet-compatible CSV",
            f"  {self._base_filename}.bin   - Raw binary register dump",
            "",
            "Data Sources:",
            "-------------",
        ]

        for collection in data.collections:
            lines.append(f"  - {collection.source.upper()}")
            lines.append(f"    Serial: {self._sanitize_serial(collection.serial_number)}")
            lines.append(f"    Input registers: {collection.input_register_count()}")
            lines.append(f"    Holding registers: {collection.holding_register_count()}")
            if collection.errors:
                lines.append(f"    Errors: {len(collection.errors)}")
            lines.append("")

        if data.comparison:
            lines.extend(
                [
                    "Comparison Summary:",
                    "-------------------",
                    f"  Status: {'Match' if data.comparison.is_match() else 'Mismatches Found'}",
                    f"  Input mismatches: {len(data.comparison.input_mismatches)}",
                    f"  Holding mismatches: {len(data.comparison.holding_mismatches)}",
                    "",
                ]
            )

        lines.extend(
            [
                "Binary Format (*.bin):",
                "----------------------",
                "The binary file contains raw 16-bit register values in little-endian",
                "format. This is useful for debugging 32-bit register reconstruction",
                "and endianness issues.",
                "",
                "Structure:",
                "  - Magic: 'LXPD' (4 bytes)",
                "  - Version: 1 (1 byte)",
                "  - Flags: bit field (1 byte)",
                "  - Timestamp: Unix time as double (8 bytes)",
                "  - Serial: length + ASCII bytes",
                "  - Collections: count + data per source",
                "",
                "Each collection contains:",
                "  - Source name: length + ASCII bytes",
                "  - Timestamp: Unix time as double (8 bytes)",
                "  - Input registers: count (2 bytes) + address/value pairs (4 bytes each)",
                "  - Holding registers: count (2 bytes) + address/value pairs (4 bytes each)",
                "",
                "Generated by pylxpweb modbus diagnostic tool",
            ]
        )

        return "\n".join(lines)

    def _sanitize_serial(self, serial: str) -> str:
        """Mask serial number if sanitization is enabled."""
        if not self._sanitize or not serial or len(serial) < 4:
            return serial
        return f"{serial[:2]}{'*' * (len(serial) - 4)}{serial[-2:]}"


def generate_filename(serial: str, sanitize: bool = True) -> str:
    """Generate a timestamped filename for the archive.

    Args:
        serial: Device serial number
        sanitize: Whether to mask serial in filename

    Returns:
        Filename like "modbus_diag_CE****78_20260125_143022.zip"
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if sanitize and serial and len(serial) >= 4:
        serial_part = f"{serial[:2]}{'*' * (len(serial) - 4)}{serial[-2:]}"
    else:
        serial_part = serial or "unknown"

    return f"modbus_diag_{serial_part}_{timestamp}.zip"
