"""Base classes for battery protocol definitions."""

from __future__ import annotations

import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass

from pylxpweb.constants.scaling import ScaleFactor, apply_scale
from pylxpweb.transports.data import BatteryData


def signed_int16(raw: int) -> int:
    """Interpret a raw unsigned 16-bit value as signed int16.

    Args:
        raw: Unsigned 16-bit register value.

    Returns:
        Signed integer in range [-32768, 32767].
    """
    result: int = struct.unpack("h", struct.pack("H", raw & 0xFFFF))[0]
    return result


def decode_ascii(registers: dict[int, int], start: int, count: int) -> str:
    """Decode register values as ASCII (high byte, low byte per register).

    Args:
        registers: Dict mapping register address to raw 16-bit value.
        start: First register address to decode.
        count: Number of registers to decode.

    Returns:
        Decoded ASCII string with null bytes and whitespace stripped.
    """
    raw_bytes = bytearray()
    for i in range(count):
        val = registers.get(start + i, 0)
        raw_bytes.append((val >> 8) & 0xFF)
        raw_bytes.append(val & 0xFF)
    return raw_bytes.decode("ascii", errors="replace").replace("\x00", "").strip()


@dataclass(frozen=True)
class BatteryRegister:
    """Single register field definition.

    Attributes:
        address: Modbus register address.
        name: Canonical field name (e.g. "voltage", "current").
        scale: How to convert raw 16-bit value to real units.
        signed: If True, interpret raw value as signed int16.
        unit: Display unit string ("V", "A", "deg-C", "%").
    """

    address: int
    name: str
    scale: ScaleFactor
    signed: bool = False
    unit: str = ""


@dataclass(frozen=True)
class BatteryRegisterBlock:
    """Contiguous block of registers to read in one Modbus call.

    Attributes:
        start: First register address in the block.
        count: Number of contiguous registers to read.
        registers: Field definitions for registers within this block.
    """

    start: int
    count: int
    registers: tuple[BatteryRegister, ...]


class BatteryProtocol(ABC):
    """Abstract base class for battery protocol definitions.

    Subclasses define register_blocks and override decode() to produce
    BatteryData from raw register values.
    """

    name: str = "base"
    register_blocks: tuple[BatteryRegisterBlock, ...] = ()

    @staticmethod
    def decode_register(reg: BatteryRegister, raw_value: int) -> float:
        """Decode a single raw register value using the register definition.

        Args:
            reg: Register definition with scaling and sign info.
            raw_value: Raw unsigned 16-bit value from Modbus.

        Returns:
            Scaled float value in proper units.
        """
        if reg.signed:
            raw_value = signed_int16(raw_value)
        return apply_scale(raw_value, reg.scale)

    @staticmethod
    def decode_cell_voltages(
        raw_regs: dict[int, int],
        start_address: int,
        num_cells: int,
    ) -> tuple[list[float], float, float]:
        """Decode cell voltages from contiguous registers at /1000 scaling.

        Args:
            raw_regs: Dict mapping register address to raw 16-bit value.
            start_address: Register address of the first cell voltage.
            num_cells: Number of cells to decode.

        Returns:
            Tuple of (cell_voltages, min_cell_voltage, max_cell_voltage).
            Min/max are 0.0 if no non-zero cells exist.
        """
        cell_voltages = [raw_regs.get(start_address + i, 0) / 1000.0 for i in range(num_cells)]
        non_zero_cells = [v for v in cell_voltages if v > 0]
        min_v = min(non_zero_cells) if non_zero_cells else 0.0
        max_v = max(non_zero_cells) if non_zero_cells else 0.0
        return cell_voltages, min_v, max_v

    def _reg(self, name: str) -> BatteryRegister:
        """Look up a register definition by name across all blocks.

        Args:
            name: Canonical register name (e.g. "voltage", "current").

        Returns:
            The matching BatteryRegister.

        Raises:
            KeyError: If no register with that name is found.
        """
        for block in self.register_blocks:
            for reg in block.registers:
                if reg.name == name:
                    return reg
        raise KeyError(f"No register named '{name}' in {self.name} protocol")

    @abstractmethod
    def decode(self, raw_regs: dict[int, int], battery_index: int = 0) -> BatteryData:
        """Decode raw registers into a BatteryData object.

        Args:
            raw_regs: Dict mapping register address to raw 16-bit value.
            battery_index: 0-based index of the battery in the bank.

        Returns:
            BatteryData with all values properly scaled.
        """
