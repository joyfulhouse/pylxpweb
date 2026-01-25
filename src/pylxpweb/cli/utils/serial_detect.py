"""Serial number detection utilities.

Functions for extracting serial numbers and firmware versions from register data.
"""

from __future__ import annotations


def detect_serial_from_registers(
    input_registers: dict[int, int],
    start_address: int = 115,
    length: int = 5,
) -> str | None:
    """Extract serial number from input registers.

    The serial number is stored as 10 ASCII characters across 5 consecutive
    16-bit input registers (2 chars per register, big-endian).

    Args:
        input_registers: Dictionary of register address -> value
        start_address: Starting register address (default: 115)
        length: Number of registers containing serial (default: 5)

    Returns:
        Serial number string or None if not available
    """
    try:
        chars = []
        for i in range(length):
            addr = start_address + i
            value = input_registers.get(addr)
            if value is None:
                return None

            # Each register contains 2 ASCII characters (big-endian)
            high_char = chr((value >> 8) & 0xFF)
            low_char = chr(value & 0xFF)
            chars.append(high_char)
            chars.append(low_char)

        serial = "".join(chars)

        # Validate: serial should be alphanumeric
        if serial.isalnum():
            return serial

        # Try stripping null bytes
        serial = serial.replace("\x00", "").strip()
        if serial and serial.isalnum():
            return serial

        return None
    except (ValueError, TypeError):
        return None


def parse_firmware_version(
    holding_registers: dict[int, int],
    start_address: int = 7,
    length: int = 4,
) -> str | None:
    """Extract firmware version from holding registers.

    The firmware version is stored as 8 ASCII characters across 4 consecutive
    16-bit holding registers (2 chars per register, big-endian).

    Args:
        holding_registers: Dictionary of register address -> value
        start_address: Starting register address (default: 7)
        length: Number of registers containing firmware (default: 4)

    Returns:
        Firmware version string or None if not available
    """
    try:
        chars = []
        for i in range(length):
            addr = start_address + i
            value = holding_registers.get(addr)
            if value is None:
                return None

            # Each register contains 2 ASCII characters (big-endian)
            high_char = chr((value >> 8) & 0xFF)
            low_char = chr(value & 0xFF)
            chars.append(high_char)
            chars.append(low_char)

        firmware = "".join(chars)

        # Clean up null bytes and whitespace
        firmware = firmware.replace("\x00", "").strip()

        if firmware:
            return firmware

        return None
    except (ValueError, TypeError):
        return None


def extract_model_code(
    holding_registers: dict[int, int],
    address: int = 19,
) -> int | None:
    """Extract device type/model code from holding registers.

    The device type code is stored in holding register 19
    (HOLD_DEVICE_TYPE_CODE).

    Args:
        holding_registers: Dictionary of register address -> value
        address: Register address (default: 19)

    Returns:
        Device type code or None if not available
    """
    return holding_registers.get(address)


def extract_arm_firmware(
    input_registers: dict[int, int],
    start_address: int = 110,
    length: int = 5,
) -> str | None:
    """Extract ARM firmware version from input registers.

    The ARM firmware version is stored as 10 ASCII characters across
    5 consecutive 16-bit input registers.

    Args:
        input_registers: Dictionary of register address -> value
        start_address: Starting register address (default: 110)
        length: Number of registers (default: 5)

    Returns:
        ARM firmware version string or None if not available
    """
    try:
        chars = []
        for i in range(length):
            addr = start_address + i
            value = input_registers.get(addr)
            if value is None:
                return None

            high_char = chr((value >> 8) & 0xFF)
            low_char = chr(value & 0xFF)
            chars.append(high_char)
            chars.append(low_char)

        firmware = "".join(chars)
        firmware = firmware.replace("\x00", "").strip()

        if firmware:
            return firmware

        return None
    except (ValueError, TypeError):
        return None


def format_device_info(
    serial: str | None,
    firmware: str | None,
    model_code: int | None,
    arm_firmware: str | None = None,
) -> str:
    """Format device information as a summary string.

    Args:
        serial: Device serial number
        firmware: DSP firmware version
        model_code: Device type code
        arm_firmware: ARM firmware version

    Returns:
        Formatted device info string
    """
    parts = []

    if serial:
        parts.append(f"Serial: {serial}")
    else:
        parts.append("Serial: Unknown")

    if firmware:
        parts.append(f"Firmware: {firmware}")

    if model_code is not None:
        parts.append(f"Model Code: {model_code}")

    if arm_firmware:
        parts.append(f"ARM: {arm_firmware}")

    return " | ".join(parts)
