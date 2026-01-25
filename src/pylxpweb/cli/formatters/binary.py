"""Binary formatter for diagnostic output.

Generates raw binary register dumps with a header containing metadata.
Useful for debugging 16-bit vs 32-bit register interpretation and endianness.
"""

from __future__ import annotations

import struct
from datetime import datetime

from pylxpweb.cli.collectors.base import CollectionResult

from .base import DiagnosticData


class BinaryFormatter:
    """Format diagnostic data as raw binary.

    Produces a binary file with structure:
    - Magic header (4 bytes): "LXPD" (Luxpower Diagnostic)
    - Version (1 byte): File format version
    - Flags (1 byte): Bit flags for options
    - Timestamp (8 bytes): Unix timestamp (double)
    - Serial length (1 byte): Length of serial number
    - Serial (N bytes): ASCII serial number
    - Input register count (2 bytes): Number of input registers
    - Input registers (N * 4 bytes): address (2) + value (2) pairs
    - Holding register count (2 bytes): Number of holding registers
    - Holding registers (N * 4 bytes): address (2) + value (2) pairs

    This format preserves the exact 16-bit register values for debugging
    endianness and 32-bit register reconstruction issues.
    """

    MAGIC = b"LXPD"
    VERSION = 1
    FLAG_SANITIZED = 0x01
    FLAG_MULTI_SOURCE = 0x02

    def __init__(
        self,
        sanitize: bool = True,
        include_all_sources: bool = True,
    ) -> None:
        """Initialize binary formatter.

        Args:
            sanitize: Whether to mask sensitive data
            include_all_sources: Include data from all collection sources
        """
        self._sanitize = sanitize
        self._include_all_sources = include_all_sources

    @property
    def file_extension(self) -> str:
        """Return file extension."""
        return "bin"

    @property
    def is_binary(self) -> bool:
        """Return True - this is binary output."""
        return True

    def format(self, data: DiagnosticData) -> bytes:
        """Generate binary output.

        Args:
            data: Diagnostic data to format

        Returns:
            Binary bytes
        """
        output = bytearray()

        # Magic header
        output.extend(self.MAGIC)

        # Version
        output.append(self.VERSION)

        # Flags
        flags = 0
        if self._sanitize:
            flags |= self.FLAG_SANITIZED
        if len(data.collections) > 1:
            flags |= self.FLAG_MULTI_SOURCE
        output.append(flags)

        # Timestamp (8 bytes, double)
        timestamp = data.timestamp.timestamp()
        output.extend(struct.pack("<d", timestamp))

        # Serial number
        serial = self._sanitize_serial(data.serial_number)
        serial_bytes = serial.encode("ascii", errors="replace")
        output.append(len(serial_bytes))
        output.extend(serial_bytes)

        # For each collection, write registers
        # First byte: number of collections
        if self._include_all_sources:
            output.append(len(data.collections))
            for collection in data.collections:
                output.extend(self._format_collection(collection))
        else:
            # Just primary collection
            output.append(1)
            if data.primary_collection:
                output.extend(self._format_collection(data.primary_collection))

        return bytes(output)

    def _format_collection(self, collection: CollectionResult) -> bytes:
        """Format a single collection as binary."""
        output = bytearray()

        # Source name (1 byte length + N bytes)
        source_bytes = collection.source.encode("ascii", errors="replace")[:255]
        output.append(len(source_bytes))
        output.extend(source_bytes)

        # Collection timestamp
        output.extend(struct.pack("<d", collection.timestamp.timestamp()))

        # Input registers
        input_regs = collection.input_registers
        output.extend(struct.pack("<H", len(input_regs)))
        for addr in sorted(input_regs.keys()):
            val = input_regs[addr]
            output.extend(struct.pack("<HH", addr, val & 0xFFFF))

        # Holding registers
        holding_regs = collection.holding_registers
        output.extend(struct.pack("<H", len(holding_regs)))
        for addr in sorted(holding_regs.keys()):
            val = holding_regs[addr]
            output.extend(struct.pack("<HH", addr, val & 0xFFFF))

        return bytes(output)

    def _sanitize_serial(self, serial: str) -> str:
        """Mask serial number if sanitization is enabled."""
        if not self._sanitize or not serial or len(serial) < 4:
            return serial
        return f"{serial[:2]}{'*' * (len(serial) - 4)}{serial[-2:]}"


class BinaryReader:
    """Read and parse binary diagnostic files.

    Companion class to BinaryFormatter for parsing dumped files.
    """

    MAGIC = BinaryFormatter.MAGIC
    FLAG_SANITIZED = BinaryFormatter.FLAG_SANITIZED
    FLAG_MULTI_SOURCE = BinaryFormatter.FLAG_MULTI_SOURCE

    def parse(self, data: bytes) -> dict[str, object]:
        """Parse binary diagnostic file.

        Args:
            data: Binary data to parse

        Returns:
            Dictionary with parsed data

        Raises:
            ValueError: If data format is invalid
        """
        if len(data) < 14:
            raise ValueError("Data too short for valid diagnostic file")

        pos = 0

        # Magic header
        magic = data[pos : pos + 4]
        if magic != self.MAGIC:
            raise ValueError(f"Invalid magic header: expected {self.MAGIC!r}, got {magic!r}")
        pos += 4

        # Version
        version = data[pos]
        if version != 1:
            raise ValueError(f"Unsupported version: {version}")
        pos += 1

        # Flags
        flags = data[pos]
        pos += 1
        is_sanitized = bool(flags & self.FLAG_SANITIZED)
        is_multi_source = bool(flags & self.FLAG_MULTI_SOURCE)

        # Timestamp
        (timestamp,) = struct.unpack("<d", data[pos : pos + 8])
        pos += 8

        # Serial number
        serial_len = data[pos]
        pos += 1
        serial = data[pos : pos + serial_len].decode("ascii", errors="replace")
        pos += serial_len

        # Collections
        num_collections = data[pos]
        pos += 1

        collections = []
        for _ in range(num_collections):
            collection, pos = self._parse_collection(data, pos)
            collections.append(collection)

        return {
            "version": version,
            "is_sanitized": is_sanitized,
            "is_multi_source": is_multi_source,
            "timestamp": datetime.fromtimestamp(timestamp),
            "serial_number": serial,
            "collections": collections,
        }

    def _parse_collection(self, data: bytes, pos: int) -> tuple[dict[str, object], int]:
        """Parse a single collection from binary data."""
        # Source name
        source_len = data[pos]
        pos += 1
        source = data[pos : pos + source_len].decode("ascii", errors="replace")
        pos += source_len

        # Timestamp
        (timestamp,) = struct.unpack("<d", data[pos : pos + 8])
        pos += 8

        # Input registers
        (input_count,) = struct.unpack("<H", data[pos : pos + 2])
        pos += 2
        input_registers: dict[int, int] = {}
        for _ in range(input_count):
            addr, val = struct.unpack("<HH", data[pos : pos + 4])
            pos += 4
            input_registers[addr] = val

        # Holding registers
        (holding_count,) = struct.unpack("<H", data[pos : pos + 2])
        pos += 2
        holding_registers: dict[int, int] = {}
        for _ in range(holding_count):
            addr, val = struct.unpack("<HH", data[pos : pos + 4])
            pos += 4
            holding_registers[addr] = val

        return {
            "source": source,
            "timestamp": datetime.fromtimestamp(timestamp),
            "input_registers": input_registers,
            "holding_registers": holding_registers,
        }, pos
