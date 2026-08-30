"""Shared register reading utilities for Modbus-based transports.

This module provides common functionality for reading device information
from Modbus registers, shared between ModbusTransport and DongleTransport.

The utilities extract common patterns to reduce code duplication while
maintaining clear, explicit implementations.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

_LOGGER = logging.getLogger(__name__)

# Device type code for MID/GridBOSS devices
DEVICE_TYPE_MIDBOX = 50
DEVICE_TYPE_REGISTER = 19

# Serial number is stored in input registers 115-119 (5 registers, 10 ASCII chars)
# on inverter-family devices. On MID/GridBOSS devices those input registers are
# AC-couple lifetime-energy counters (see registers/gridboss.py), so when the
# input decode is not a plausible serial the read falls back to holding
# registers 2-6 (HOLD_SERIAL_NUM), which hold the serial on every documented
# family (eg4_web_monitor#593).
SERIAL_NUMBER_START_REGISTER = 115
SERIAL_NUMBER_REGISTER_COUNT = 5
SERIAL_NUMBER_HOLDING_START_REGISTER = 2
SERIAL_NUMBER_LENGTH = 10

# Firmware version is in holding registers 7-10
FIRMWARE_REGISTER_START = 7
FIRMWARE_REGISTER_COUNT = 4

# Parallel config is in input register 113
PARALLEL_CONFIG_REGISTER = 113


class RegisterReader(Protocol):
    """Protocol for transports that support register reading."""

    @property
    def serial(self) -> str:
        """Get the device serial number."""
        ...

    async def _read_input_registers(
        self,
        address: int,
        count: int,
    ) -> list[int]:
        """Read input registers."""
        ...

    async def _read_holding_registers(
        self,
        address: int,
        count: int,
    ) -> list[int]:
        """Read holding registers."""
        ...


def is_midbox_device(device_type_code: int) -> bool:
    """Check if device type code indicates a MID/GridBOSS device.

    Args:
        device_type_code: Device type code from read_device_type()

    Returns:
        True if device is a MID/GridBOSS, False for inverters
    """
    return device_type_code == DEVICE_TYPE_MIDBOX


def _is_plausible_serial(candidate: str) -> bool:
    """Return True when candidate looks like a genuine device serial.

    Serials across every documented family are exactly 10 ASCII alphanumeric
    characters — letters can appear anywhere (e.g. "BA12345678",
    "52842P0581"), so digits-only must not be assumed.
    decode_serial_from_registers only emits printable ASCII, so a decode of
    non-serial data (e.g. GridBOSS AC-couple energy counters at input
    115-119) is rejected here as too short or as containing punctuation.
    """
    return len(candidate) == SERIAL_NUMBER_LENGTH and candidate.isascii() and candidate.isalnum()


def decode_serial_from_registers(values: list[int]) -> str:
    """Decode ASCII serial number from register values.

    The serial number is stored as 10 ASCII characters across 5 registers.
    Each register contains 2 characters: low byte = char[0], high byte = char[1].

    Args:
        values: List of 5 register values

    Returns:
        Decoded serial number string
    """
    chars: list[str] = []
    for value in values:
        low_byte = value & 0xFF
        high_byte = (value >> 8) & 0xFF
        if 32 <= low_byte <= 126:
            chars.append(chr(low_byte))
        if 32 <= high_byte <= 126:
            chars.append(chr(high_byte))
    return "".join(chars)


def decode_firmware_from_registers(regs: list[int]) -> str:
    """Decode firmware version from register values.

    The firmware information is stored in a specific format:
    - Registers 7-8: Firmware prefix as byte-swapped ASCII (e.g., "FAAB")
    - Registers 9-10: Version bytes with special encoding

    Byte layout:
    - Reg 7: 0x4146 -> low byte 'F', high byte 'A' -> "FA"
    - Reg 8: 0x4241 -> low byte 'A', high byte 'B' -> "AB"
    - Reg 9: v1 is in high byte (e.g., 0x2503 -> v1 = 0x25 = 37)
    - Reg 10: v2 is in low byte (e.g., 0x0125 -> v2 = 0x25 = 37)

    Args:
        regs: List of 4 register values (registers 7-10)

    Returns:
        Full firmware code string (e.g., "FAAB-2525") or empty string
    """
    if len(regs) < 4:
        return ""

    prefix_chars = [
        chr(regs[0] & 0xFF),
        chr((regs[0] >> 8) & 0xFF),
        chr(regs[1] & 0xFF),
        chr((regs[1] >> 8) & 0xFF),
    ]
    prefix = "".join(prefix_chars)

    v1 = (regs[2] >> 8) & 0xFF
    v2 = regs[3] & 0xFF

    return f"{prefix}-{v1:02X}{v2:02X}"


async def read_device_type_async(
    read_holding: Callable[[int, int], Coroutine[None, None, list[int]]],
) -> int:
    """Read device type code from register 19.

    Known device type codes:
    - 50: MID/GridBOSS (Microgrid Interconnect Device)
    - 54: SNA Series
    - 2092: PV Series (18KPV)
    - 10284: FlexBOSS21/FlexBOSS18

    Args:
        read_holding: Async function to read holding registers

    Returns:
        Device type code integer

    Raises:
        TransportReadError: If read operation fails
    """
    from .exceptions import TransportReadError

    values = await read_holding(DEVICE_TYPE_REGISTER, 1)
    if not values:
        raise TransportReadError("Failed to read device type register")
    return values[0]


async def read_serial_number_async(
    read_input: Callable[[int, int], Coroutine[None, None, list[int]]],
    serial: str,
    read_holding: Callable[[int, int], Coroutine[None, None, list[int]]] | None = None,
) -> str:
    """Read device serial number.

    Tries input registers 115-119 first (inverter-family layout). If the
    decoded result is not a plausible 10-character alphanumeric serial —
    GridBOSS units keep AC-couple energy counters there, which decode to
    an empty, truncated, or garbage-punctuation string — falls back to
    holding registers 2-6 (HOLD_SERIAL_NUM), the canonical location shared
    by all families. A holding decode that is itself not plausible is not
    adopted, and a holding read that fails outright is swallowed — either
    way the input-register result is returned unchanged, so a device with
    a restricted register map degrades exactly as it did before the
    fallback existed instead of turning discovery into a hard failure.

    Args:
        read_input: Async function to read input registers
        serial: Device serial for logging
        read_holding: Optional async function to read holding registers,
            enabling the holding-register fallback

    Returns:
        10-character serial number string (e.g., "BA12345678")
    """
    values = await read_input(SERIAL_NUMBER_START_REGISTER, SERIAL_NUMBER_REGISTER_COUNT)
    result = decode_serial_from_registers(values)
    if _is_plausible_serial(result) or read_holding is None:
        _LOGGER.debug("Read serial number from device %s: %s", serial, result)
        return result

    _LOGGER.debug(
        "Input registers 115-119 decoded to %r for %s, not a plausible serial; "
        "falling back to holding registers 2-6",
        result,
        serial,
    )
    try:
        holding_values = await read_holding(
            SERIAL_NUMBER_HOLDING_START_REGISTER, SERIAL_NUMBER_REGISTER_COUNT
        )
    except Exception as err:
        _LOGGER.debug(
            "Holding-register serial fallback failed for %s, keeping input-register result: %s",
            serial,
            err,
        )
        return result
    holding_result = decode_serial_from_registers(holding_values)
    if _is_plausible_serial(holding_result):
        _LOGGER.debug(
            "Read serial number from holding registers for device %s: %s",
            serial,
            holding_result,
        )
        return holding_result
    _LOGGER.debug(
        "Holding registers 2-6 decoded to %r for %s, not a plausible serial; "
        "keeping input-register result",
        holding_result,
        serial,
    )
    return result


async def read_firmware_version_async(
    read_holding: Callable[[int, int], Coroutine[None, None, list[int]]],
) -> str:
    """Read full firmware version code from holding registers 7-10.

    Args:
        read_holding: Async function to read holding registers

    Returns:
        Full firmware code string (e.g., "FAAB-2525") or empty string
    """
    try:
        regs = await read_holding(FIRMWARE_REGISTER_START, FIRMWARE_REGISTER_COUNT)
        firmware = decode_firmware_from_registers(regs)
        if firmware:
            _LOGGER.debug("Read firmware version: %s", firmware)
        return firmware
    except Exception as err:
        _LOGGER.debug("Failed to read firmware version: %s", err)
        return ""


async def read_parallel_config_async(
    read_input: Callable[[int, int], Coroutine[None, None, list[int]]],
    serial: str,
) -> int:
    """Read parallel configuration from input register 113.

    The parallel config register contains packed information:
    - Bits 0-1: Master/slave role (0=standalone, 1=master, 2=slave, 3=3-phase master)
    - Bits 2-3: Phase assignment (0=R, 1=S, 2=T)
    - Bits 8-15: Parallel group number (0=standalone, 1-255=group number)

    Example: Value 0x0205 (517 decimal) means:
    - Master/slave = 1 (master)
    - Phase = 1 (S)
    - Parallel number = 2 (group B)

    Args:
        read_input: Async function to read input registers
        serial: Device serial for logging

    Returns:
        Raw 16-bit value with packed parallel config, or 0 if read fails.

    Raises:
        TransportReadError: If read operation fails
    """
    from .exceptions import TransportReadError

    try:
        values = await read_input(PARALLEL_CONFIG_REGISTER, 1)
        if values:
            return values[0]
    except Exception as e:
        _LOGGER.debug(
            "Failed to read parallel config register 113 for %s: %s",
            serial,
            e,
        )
        raise TransportReadError(f"Failed to read parallel config: {e}") from e
    return 0
