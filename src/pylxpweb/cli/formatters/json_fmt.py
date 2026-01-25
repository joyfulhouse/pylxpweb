"""JSON formatter for diagnostic output.

Generates structured JSON output with all collection data, metadata,
and comparison results.
"""

from __future__ import annotations

import json
from datetime import datetime

from pylxpweb import __version__
from pylxpweb.cli.collectors.base import CollectionResult, ComparisonResult

from .base import DiagnosticData


class JSONFormatter:
    """Format diagnostic data as JSON.

    Produces a structured JSON document containing:
    - Metadata (tool version, timestamp, options)
    - Collections (register data from each source)
    - Comparison (mismatches between sources)
    - Statistics (register counts, durations)

    Example output:
        {
            "metadata": {
                "tool_version": "0.5.23",
                "timestamp": "2026-01-25T14:30:22-08:00",
                ...
            },
            "collections": [
                {
                    "source": "modbus",
                    "serial_number": "CE12345678",
                    "input_registers": {"0": 1234, ...},
                    "holding_registers": {"0": 5678, ...}
                }
            ],
            "comparison": { ... },
            "statistics": { ... }
        }
    """

    def __init__(
        self,
        indent: int = 2,
        sanitize: bool = True,
    ) -> None:
        """Initialize JSON formatter.

        Args:
            indent: JSON indentation level
            sanitize: Whether to mask sensitive data
        """
        self._indent = indent
        self._sanitize = sanitize

    @property
    def file_extension(self) -> str:
        """Return file extension."""
        return "json"

    @property
    def is_binary(self) -> bool:
        """Return False - JSON is text."""
        return False

    def format(self, data: DiagnosticData) -> str:
        """Generate JSON output.

        Args:
            data: Diagnostic data to format

        Returns:
            JSON string
        """
        output = {
            "metadata": self._format_metadata(data),
            "collections": [self._format_collection(c) for c in data.collections],
            "comparison": self._format_comparison(data.comparison) if data.comparison else None,
            "statistics": self._format_statistics(data),
        }

        return json.dumps(output, indent=self._indent, default=self._json_serializer)

    def _format_metadata(self, data: DiagnosticData) -> dict[str, str | int | bool | None]:
        """Format metadata section."""
        return {
            "tool_version": __version__,
            "timestamp": data.timestamp.isoformat(),
            "serial_number": self._sanitize_serial(data.serial_number),
            "firmware_version": data.firmware_version,
            "sanitized": self._sanitize,
            **data.metadata,
        }

    def _format_collection(self, collection: CollectionResult) -> dict[str, object]:
        """Format a single collection result."""
        return {
            "source": collection.source,
            "timestamp": collection.timestamp.isoformat(),
            "serial_number": self._sanitize_serial(collection.serial_number),
            "firmware_version": collection.firmware_version,
            "inverter_family": (
                collection.inverter_family.value if collection.inverter_family else None
            ),
            "connection_params": self._sanitize_params(collection.connection_params),
            "input_registers": {
                str(addr): val for addr, val in sorted(collection.input_registers.items())
            },
            "holding_registers": {
                str(addr): val for addr, val in sorted(collection.holding_registers.items())
            },
            "errors": collection.errors,
            "duration_seconds": round(collection.duration_seconds, 2),
            "statistics": {
                "input_count": collection.input_register_count(),
                "input_nonzero": collection.input_nonzero_count(),
                "holding_count": collection.holding_register_count(),
                "holding_nonzero": collection.holding_nonzero_count(),
            },
        }

    def _format_comparison(self, comparison: ComparisonResult) -> dict[str, object]:
        """Format comparison result."""
        return {
            "sources": comparison.sources,
            "timestamp": comparison.timestamp.isoformat(),
            "is_match": comparison.is_match(),
            "input_mismatches": [
                {
                    "address": m.address,
                    "source_a": m.source_a,
                    "value_a": m.value_a,
                    "source_b": m.source_b,
                    "value_b": m.value_b,
                }
                for m in comparison.input_mismatches
            ],
            "holding_mismatches": [
                {
                    "address": m.address,
                    "source_a": m.source_a,
                    "value_a": m.value_a,
                    "source_b": m.source_b,
                    "value_b": m.value_b,
                }
                for m in comparison.holding_mismatches
            ],
            "statistics": {
                "input_match_count": comparison.input_match_count,
                "holding_match_count": comparison.holding_match_count,
                "input_mismatch_count": len(comparison.input_mismatches),
                "holding_mismatch_count": len(comparison.holding_mismatches),
            },
        }

    def _format_statistics(self, data: DiagnosticData) -> dict[str, int | float]:
        """Format statistics section."""
        total_duration = sum(c.duration_seconds for c in data.collections)
        return {
            "total_input_registers": data.total_input_registers(),
            "total_holding_registers": data.total_holding_registers(),
            "collection_count": len(data.collections),
            "total_duration_seconds": round(total_duration, 2),
        }

    def _sanitize_serial(self, serial: str) -> str:
        """Mask serial number if sanitization is enabled."""
        if not self._sanitize or not serial or len(serial) < 4:
            return serial
        return f"{serial[:2]}{'*' * (len(serial) - 4)}{serial[-2:]}"

    def _sanitize_params(self, params: dict[str, str | int]) -> dict[str, str | int]:
        """Sanitize connection parameters."""
        if not self._sanitize:
            return params

        result = {}
        for key, value in params.items():
            if key in ("password", "dongle_serial"):
                result[key] = "***"
            elif key == "username":
                result[key] = self._sanitize_username(str(value))
            elif "serial" in key.lower():
                result[key] = self._sanitize_serial(str(value))
            else:
                result[key] = value
        return result

    def _sanitize_username(self, username: str) -> str:
        """Mask username if sanitization is enabled."""
        if not self._sanitize or len(username) <= 5:
            return "***"
        return f"{username[:3]}***{username[-2:]}"

    def _json_serializer(self, obj: object) -> str:
        """Custom JSON serializer for unsupported types."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
