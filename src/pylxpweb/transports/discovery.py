"""Device discovery utilities for local transports.

This module provides utilities for detecting device types and gathering
device information from Modbus TCP and WiFi dongle transports.

The device type is determined by reading HOLD_DEVICE_TYPE_CODE (register 19)
which contains a unique code identifying the hardware:
- 50: GridBOSS/MIDbox (parallel group controller)
- 54: SNA Series (12000XP, 6000XP)
- 2092: PV Series (18KPV)
- 10284: FlexBOSS Series (FlexBOSS21, FlexBOSS18)
- 12: LXP-EU Series

Example:
    >>> transport = create_modbus_transport(host="192.168.1.100", serial="CE12345678")
    >>> await transport.connect()
    >>> info = await discover_device_info(transport)
    >>> if info.is_gridboss:
    ...     mid_device = await MIDDevice.from_transport(transport)
    ... else:
    ...     inverter = await BaseInverter.from_modbus_transport(transport)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pylxpweb.constants import (
    DEVICE_TYPE_CODE_FLEXBOSS,
    DEVICE_TYPE_CODE_GRIDBOSS,
    DEVICE_TYPE_CODE_LXP_EU,
    DEVICE_TYPE_CODE_PV_SERIES,
    DEVICE_TYPE_CODE_SNA,
)

if TYPE_CHECKING:
    from pylxpweb.transports.protocol import InverterTransport

_LOGGER = logging.getLogger(__name__)

# Register addresses for device discovery
HOLD_DEVICE_TYPE_CODE = 19
HOLD_PARALLEL_NUMBER = 107
HOLD_PARALLEL_PHASE = 108


@dataclass
class DeviceDiscoveryInfo:
    """Information discovered from a local transport.

    This dataclass contains device identification and configuration
    information read from the device's Modbus registers.

    Attributes:
        serial: Device serial number (from transport or auto-detected)
        device_type_code: Raw value from HOLD_DEVICE_TYPE_CODE (register 19)
        is_gridboss: True if device is a GridBOSS/MIDbox
        is_inverter: True if device is an inverter (any family)
        model_family: String name of the inverter family (or "GridBOSS")
        parallel_number: Parallel group identifier (register 107)
        parallel_phase: Parallel phase within group (register 108)
        firmware_version: Firmware version string (if available)
    """

    serial: str
    device_type_code: int
    is_gridboss: bool
    is_inverter: bool
    model_family: str
    parallel_number: int | None = None
    parallel_phase: int | None = None
    firmware_version: str | None = None


def get_model_family_name(device_type_code: int) -> str:
    """Get the model family name from a device type code.

    Args:
        device_type_code: Value from HOLD_DEVICE_TYPE_CODE (register 19)

    Returns:
        String name of the model family

    Example:
        >>> get_model_family_name(50)
        'GridBOSS'
        >>> get_model_family_name(2092)
        'PV_SERIES'
    """
    family_map = {
        DEVICE_TYPE_CODE_GRIDBOSS: "GridBOSS",
        DEVICE_TYPE_CODE_SNA: "SNA",
        DEVICE_TYPE_CODE_PV_SERIES: "PV_SERIES",
        DEVICE_TYPE_CODE_FLEXBOSS: "PV_SERIES",  # FlexBOSS is part of PV Series family
        DEVICE_TYPE_CODE_LXP_EU: "LXP_EU",
    }
    return family_map.get(device_type_code, "UNKNOWN")


def is_gridboss_device(device_type_code: int) -> bool:
    """Check if a device type code indicates a GridBOSS/MIDbox.

    Args:
        device_type_code: Value from HOLD_DEVICE_TYPE_CODE (register 19)

    Returns:
        True if the device is a GridBOSS/MIDbox, False otherwise

    Example:
        >>> is_gridboss_device(50)
        True
        >>> is_gridboss_device(2092)
        False
    """
    return device_type_code == DEVICE_TYPE_CODE_GRIDBOSS


async def discover_device_info(transport: InverterTransport) -> DeviceDiscoveryInfo:
    """Discover device information from a connected transport.

    This function reads key registers from the device to determine:
    - Device type (GridBOSS vs inverter)
    - Model family (SNA, PV Series, LXP-EU, etc.)
    - Parallel group configuration

    Args:
        transport: Connected Modbus or dongle transport

    Returns:
        DeviceDiscoveryInfo with all discovered information

    Raises:
        TransportReadError: If device type cannot be read

    Example:
        >>> transport = create_modbus_transport(host="192.168.1.100", serial="")
        >>> await transport.connect()
        >>> info = await discover_device_info(transport)
        >>> print(f"Device: {info.model_family}, GridBOSS: {info.is_gridboss}")
    """
    # Read device type code from register 19
    device_type_code = 0
    try:
        params = await transport.read_parameters(HOLD_DEVICE_TYPE_CODE, 1)
        if HOLD_DEVICE_TYPE_CODE in params:
            device_type_code = params[HOLD_DEVICE_TYPE_CODE]
    except Exception as err:
        _LOGGER.warning("Failed to read device type code: %s", err)
        # Continue with default (0 = unknown)

    # Read parallel group configuration (registers 107-108)
    parallel_number = None
    parallel_phase = None
    try:
        params = await transport.read_parameters(HOLD_PARALLEL_NUMBER, 2)
        parallel_number = params.get(HOLD_PARALLEL_NUMBER)
        parallel_phase = params.get(HOLD_PARALLEL_PHASE)
    except Exception as err:
        _LOGGER.debug("Could not read parallel group registers: %s", err)

    # Read firmware version if available
    firmware_version = None
    try:
        if hasattr(transport, "read_firmware_version"):
            firmware_version = await transport.read_firmware_version()
    except Exception as err:
        _LOGGER.debug("Could not read firmware version: %s", err)

    # Determine device type
    is_gridboss = is_gridboss_device(device_type_code)
    is_inverter = not is_gridboss and device_type_code != 0
    model_family = get_model_family_name(device_type_code)

    info = DeviceDiscoveryInfo(
        serial=transport.serial,
        device_type_code=device_type_code,
        is_gridboss=is_gridboss,
        is_inverter=is_inverter,
        model_family=model_family,
        parallel_number=parallel_number,
        parallel_phase=parallel_phase,
        firmware_version=firmware_version,
    )

    _LOGGER.info(
        "Discovered device %s: type=%d (%s), parallel=%s/%s",
        transport.serial,
        device_type_code,
        model_family,
        parallel_number,
        parallel_phase,
    )

    return info


__all__ = [
    "DeviceDiscoveryInfo",
    "discover_device_info",
    "get_model_family_name",
    "is_gridboss_device",
    "HOLD_DEVICE_TYPE_CODE",
    "HOLD_PARALLEL_NUMBER",
    "HOLD_PARALLEL_PHASE",
]
