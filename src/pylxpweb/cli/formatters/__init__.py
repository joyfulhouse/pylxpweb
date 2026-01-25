"""Output formatters for Modbus diagnostic tool.

This module provides formatters for generating diagnostic output in various formats:
- JSONFormatter: Structured JSON output
- MarkdownFormatter: Human-readable Markdown tables
- CSVFormatter: Spreadsheet-compatible CSV
- BinaryFormatter: Raw binary register dump
- ArchiveCreator: ZIP archive bundling all formats
"""

from .archive import ArchiveCreator, generate_filename
from .base import BaseFormatter, DiagnosticData, OutputFormat
from .binary import BinaryFormatter, BinaryReader
from .csv_fmt import CSVFormatter
from .json_fmt import JSONFormatter
from .markdown import MarkdownFormatter

__all__ = [
    "BaseFormatter",
    "DiagnosticData",
    "OutputFormat",
    "JSONFormatter",
    "MarkdownFormatter",
    "CSVFormatter",
    "BinaryFormatter",
    "BinaryReader",
    "ArchiveCreator",
    "generate_filename",
]
