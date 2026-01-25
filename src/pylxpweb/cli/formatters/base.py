"""Base classes and protocols for output formatters.

Defines the common interface for all formatters and the data structures
used to represent diagnostic data for formatting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable

from pylxpweb.cli.collectors.base import CollectionResult, ComparisonResult


class OutputFormat(str, Enum):
    """Available output formats."""

    JSON = "json"
    MARKDOWN = "md"
    CSV = "csv"
    BINARY = "bin"
    ALL = "all"

    @classmethod
    def all_formats(cls) -> list[OutputFormat]:
        """Return all concrete formats (excluding ALL)."""
        return [cls.JSON, cls.MARKDOWN, cls.CSV, cls.BINARY]


@dataclass
class DiagnosticData:
    """Diagnostic data to be formatted.

    Aggregates all collection results and comparison data for output generation.

    Attributes:
        collections: List of collection results from various sources
        comparison: Optional comparison result (if multiple collections)
        metadata: Additional metadata (tool version, options used, etc.)
        timestamp: When the diagnostic was run
    """

    collections: list[CollectionResult]
    comparison: ComparisonResult | None = None
    metadata: dict[str, str | int | bool] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now().astimezone())

    @property
    def primary_collection(self) -> CollectionResult | None:
        """Return the first (primary) collection result."""
        return self.collections[0] if self.collections else None

    @property
    def serial_number(self) -> str:
        """Return serial number from primary collection."""
        if self.primary_collection:
            return self.primary_collection.serial_number
        return "UNKNOWN"

    @property
    def firmware_version(self) -> str:
        """Return firmware version from primary collection."""
        if self.primary_collection:
            return self.primary_collection.firmware_version
        return ""

    def total_input_registers(self) -> int:
        """Return total unique input registers across all collections."""
        all_addrs: set[int] = set()
        for c in self.collections:
            all_addrs.update(c.input_registers.keys())
        return len(all_addrs)

    def total_holding_registers(self) -> int:
        """Return total unique holding registers across all collections."""
        all_addrs: set[int] = set()
        for c in self.collections:
            all_addrs.update(c.holding_registers.keys())
        return len(all_addrs)


@runtime_checkable
class BaseFormatter(Protocol):
    """Protocol defining the interface for output formatters.

    All formatters must implement this interface to be used with the
    diagnostic CLI tool.
    """

    def format(self, data: DiagnosticData) -> bytes | str:
        """Generate formatted output.

        Args:
            data: Diagnostic data to format

        Returns:
            Formatted output as bytes (for binary) or str (for text)
        """
        ...

    @property
    def file_extension(self) -> str:
        """Return file extension for this format (without leading dot)."""
        ...

    @property
    def is_binary(self) -> bool:
        """Return True if this formatter produces binary output."""
        ...
