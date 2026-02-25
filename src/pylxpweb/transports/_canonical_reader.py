"""Generic register reading using canonical RegisterDefinition objects.

Replaces the legacy ``_read_register_field`` / ``_read_and_scale_field``
helpers in ``data.py`` that operated on ``RegisterField`` objects from
``register_maps.py``.

All definition types share ``address``/``bit_width``/``scale``/``signed``,
so the same reader works for inverter, battery, and GridBOSS registers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

# Union-like protocol: all three def types share these attrs
_RegDef = Any  # RegisterDefinition | BatteryRegisterDefinition | GridBossRegisterDefinition


def _resolve_address(reg: _RegDef, base_address: int) -> int:
    """Resolve the absolute Modbus address for a register definition."""
    if base_address:
        offset: int = getattr(reg, "offset", 0)
        return base_address + offset
    addr: int = reg.address
    return addr


def read_raw(
    registers: dict[int, int],
    reg: _RegDef,
    *,
    base_address: int = 0,
) -> int | None:
    """Read a raw integer value from *registers* using a canonical definition.

    For battery registers, *base_address* should be
    ``BATTERY_BASE_ADDRESS + (battery_index * BATTERY_REGISTER_COUNT)``.
    The definition's ``offset`` is added to *base_address* to get the
    absolute Modbus address.

    For inverter / GridBOSS registers, *base_address* is 0 and the
    definition's ``address`` is the absolute Modbus address.

    Handles packed register formats via the ``packed`` attribute:
    - ``"low_byte"``: returns low byte of 16-bit register
    - ``"high_byte"``: returns high byte of 16-bit register

    Returns:
        Raw integer (no scaling), or ``None`` if the required register(s)
        are missing from *registers*.
    """
    addr = _resolve_address(reg, base_address)
    bit_width: int = getattr(reg, "bit_width", 16)

    if bit_width == 32:
        if addr not in registers or addr + 1 not in registers:
            return None
        # All LuxPower/EG4 32-bit are little-endian (low word first)
        low = registers[addr]
        high = registers[addr + 1]
        value = (high << 16) | low
    else:
        if addr not in registers:
            return None
        value = registers[addr]

    # Handle packed byte extraction before sign handling
    packed: str | None = getattr(reg, "packed", None)
    if packed == "low_byte":
        return value & 0xFF
    if packed == "high_byte":
        return (value >> 8) & 0xFF

    if reg.signed:
        if bit_width == 16 and value > 32767:
            value = value - 65536
        elif bit_width == 32 and value > 2147483647:
            value = value - 4294967296

    return value


def read_battery_firmware(
    registers: dict[int, int],
    reg: _RegDef,
    *,
    base_address: int,
) -> str:
    """Read packed firmware version: high byte = major, low byte = minor."""
    raw = read_raw(registers, reg, base_address=base_address)
    if not raw:
        return ""
    major = (raw >> 8) & 0xFF
    minor = raw & 0xFF
    return f"{major}.{minor}"


def read_battery_serial(
    registers: dict[int, int],
    *,
    base_address: int,
    start_offset: int = 17,
    count: int = 8,
) -> str:
    """Read serial number from consecutive 16-bit registers (2 ASCII chars each)."""
    chars: list[str] = []
    for i in range(count):
        addr = base_address + start_offset + i
        value = registers.get(addr, 0)
        low_byte = value & 0xFF
        high_byte = (value >> 8) & 0xFF
        if 32 <= low_byte <= 126:
            chars.append(chr(low_byte))
        if 32 <= high_byte <= 126:
            chars.append(chr(high_byte))
    return "".join(chars).strip()


def read_scaled(
    registers: dict[int, int],
    reg: _RegDef,
    *,
    base_address: int = 0,
) -> float | None:
    """Read and scale a register value.

    Combines ``read_raw`` with the definition's ``scale`` factor.
    Returns ``None`` when the register is absent (preserving the
    "unavailable" semantic for Home Assistant).
    """
    raw = read_raw(registers, reg, base_address=base_address)
    if raw is None:
        return None
    divisor = int(reg.scale.value)
    if divisor == 1:
        return float(raw)
    return float(raw) / divisor


def unpack_low_high_bytes(
    registers: dict[int, int],
    reg: _RegDef,
    *,
    base_address: int = 0,
) -> tuple[int | None, int | None]:
    """Unpack a 16-bit register into (low_byte, high_byte).

    Used for SOC/SOH packed registers where low byte = SOC%,
    high byte = SOH%.

    Returns:
        (low_byte, high_byte) or (None, None) if register missing.
    """
    raw = read_raw(registers, reg, base_address=base_address)
    if raw is None:
        return None, None
    return raw & 0xFF, (raw >> 8) & 0xFF


def unpack_parallel_config(
    registers: dict[int, int],
    reg: _RegDef,
) -> tuple[int | None, int | None, int | None]:
    """Unpack parallel configuration register (reg 113).

    Bits 0-1: master_slave (0=no parallel, 1=master, 2=slave, 3=3-phase master)
    Bits 2-3: phase (0=R, 1=S, 2=T)
    Bits 8-15: parallel_number (unit ID)

    Returns:
        (master_slave, phase, number) or (None, None, None) if absent.
    """
    raw = read_raw(registers, reg)
    if raw is None:
        return None, None, None
    master_slave = raw & 0x03
    phase = (raw >> 2) & 0x03
    number = (raw >> 8) & 0xFF
    return master_slave, phase, number


# ── Helpers moved from data.py ──────────────────────────────────────────


def clamp_percentage(value: int | None, name: str) -> int | None:
    """Clamp percentage value to 0-100 range, logging if out of bounds."""
    if value is None:
        return None
    if value < 0:
        _LOGGER.warning("%s value %d is negative, clamping to 0", name, value)
        return 0
    if value > 100:
        _LOGGER.warning("%s value %d exceeds 100%%, clamping to 100", name, value)
        return 100
    return value


def sum_optional(*values: float | None) -> float | None:
    """Sum multiple optional float values.

    Returns sum of all non-None values, or None if all are None.
    """
    non_none = [v for v in values if v is not None]
    return sum(non_none) if non_none else None
