"""Base classes and protocols for data collectors.

Defines the common interface for all data collectors and the data structures
used to represent collected register data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pylxpweb.devices.inverters._features import InverterFamily


@dataclass
class CollectionResult:
    """Result from a data collection operation.

    Contains all register data collected from a single source, along with
    metadata about the collection process.

    Attributes:
        source: Identifier for the data source ("modbus", "dongle", "cloud")
        timestamp: When the collection was performed
        serial_number: Inverter serial number (10 characters)
        firmware_version: Firmware version string (e.g., "FAAB-2525")
        inverter_family: Detected inverter family (PV_SERIES, LXP_EU, etc.)
        input_registers: Dict mapping input register address to raw value
        holding_registers: Dict mapping holding register address to raw value
        connection_params: Transport-specific connection parameters
        errors: List of non-fatal errors encountered during collection
        duration_seconds: Time taken for collection
    """

    source: str
    timestamp: datetime
    serial_number: str
    firmware_version: str = ""
    inverter_family: InverterFamily | None = None
    input_registers: dict[int, int] = field(default_factory=dict)
    holding_registers: dict[int, int] = field(default_factory=dict)
    connection_params: dict[str, str | int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def input_register_count(self) -> int:
        """Return count of input registers read."""
        return len(self.input_registers)

    def holding_register_count(self) -> int:
        """Return count of holding registers read."""
        return len(self.holding_registers)

    def input_nonzero_count(self) -> int:
        """Return count of non-zero input registers."""
        return sum(1 for v in self.input_registers.values() if v != 0)

    def holding_nonzero_count(self) -> int:
        """Return count of non-zero holding registers."""
        return sum(1 for v in self.holding_registers.values() if v != 0)


@dataclass
class RegisterMismatch:
    """Represents a mismatch between two register values.

    Attributes:
        address: Register address
        register_type: "input" or "holding"
        source_a: Name of first source
        value_a: Value from first source (None if not present)
        source_b: Name of second source
        value_b: Value from second source (None if not present)
    """

    address: int
    register_type: str  # "input" or "holding"
    source_a: str
    value_a: int | None
    source_b: str
    value_b: int | None

    def __str__(self) -> str:
        """Format mismatch for display."""
        return (
            f"{self.register_type}[{self.address}]: "
            f"{self.source_a}={self.value_a} vs {self.source_b}={self.value_b}"
        )


@dataclass
class ComparisonResult:
    """Result of comparing two or more CollectionResults.

    Attributes:
        sources: List of source names compared
        input_mismatches: Mismatches found in input registers
        holding_mismatches: Mismatches found in holding registers
        input_match_count: Number of input registers that matched
        holding_match_count: Number of holding registers that matched
        timestamp: When comparison was performed
    """

    sources: list[str]
    input_mismatches: list[RegisterMismatch] = field(default_factory=list)
    holding_mismatches: list[RegisterMismatch] = field(default_factory=list)
    input_match_count: int = 0
    holding_match_count: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    def total_mismatches(self) -> int:
        """Return total count of mismatches."""
        return len(self.input_mismatches) + len(self.holding_mismatches)

    def is_match(self) -> bool:
        """Return True if all compared registers matched."""
        return self.total_mismatches() == 0


def compare_collections(
    result_a: CollectionResult,
    result_b: CollectionResult,
) -> ComparisonResult:
    """Compare two collection results and identify mismatches.

    Args:
        result_a: First collection result
        result_b: Second collection result

    Returns:
        ComparisonResult with all mismatches identified
    """
    input_mismatches: list[RegisterMismatch] = []
    holding_mismatches: list[RegisterMismatch] = []
    input_match_count = 0
    holding_match_count = 0

    # Compare input registers
    all_input_addrs = set(result_a.input_registers.keys()) | set(result_b.input_registers.keys())
    for addr in sorted(all_input_addrs):
        val_a = result_a.input_registers.get(addr)
        val_b = result_b.input_registers.get(addr)

        if val_a == val_b:
            input_match_count += 1
        else:
            input_mismatches.append(
                RegisterMismatch(
                    address=addr,
                    register_type="input",
                    source_a=result_a.source,
                    value_a=val_a,
                    source_b=result_b.source,
                    value_b=val_b,
                )
            )

    # Compare holding registers
    all_hold_addrs = set(result_a.holding_registers.keys()) | set(result_b.holding_registers.keys())
    for addr in sorted(all_hold_addrs):
        val_a = result_a.holding_registers.get(addr)
        val_b = result_b.holding_registers.get(addr)

        if val_a == val_b:
            holding_match_count += 1
        else:
            holding_mismatches.append(
                RegisterMismatch(
                    address=addr,
                    register_type="holding",
                    source_a=result_a.source,
                    value_a=val_a,
                    source_b=result_b.source,
                    value_b=val_b,
                )
            )

    return ComparisonResult(
        sources=[result_a.source, result_b.source],
        input_mismatches=input_mismatches,
        holding_mismatches=holding_mismatches,
        input_match_count=input_match_count,
        holding_match_count=holding_match_count,
        timestamp=datetime.now(),
    )


@runtime_checkable
class BaseCollector(Protocol):
    """Protocol defining the interface for data collectors.

    All collectors must implement this interface to be used with the
    diagnostic CLI tool.
    """

    async def collect(
        self,
        input_ranges: list[tuple[int, int]],
        holding_ranges: list[tuple[int, int]],
    ) -> CollectionResult:
        """Collect register data from the source.

        Args:
            input_ranges: List of (start, count) tuples for input registers
            holding_ranges: List of (start, count) tuples for holding registers

        Returns:
            CollectionResult with all collected data
        """
        ...

    async def detect_serial(self) -> str | None:
        """Auto-detect inverter serial number.

        Returns:
            Serial number string if detected, None otherwise
        """
        ...

    async def detect_firmware(self) -> str | None:
        """Auto-detect firmware version.

        Returns:
            Firmware version string if detected, None otherwise
        """
        ...

    async def connect(self) -> None:
        """Establish connection to the data source."""
        ...

    async def disconnect(self) -> None:
        """Close connection to the data source."""
        ...

    @property
    def source_name(self) -> str:
        """Return identifier for this data source."""
        ...
