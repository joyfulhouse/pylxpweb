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


def get_parallel_group_key(info: DeviceDiscoveryInfo) -> tuple[int, int] | None:
    """Get the parallel group key for a discovered device.

    Devices with the same (parallel_number, parallel_phase) tuple are in the
    same parallel group.

    Args:
        info: Device discovery information

    Returns:
        Tuple of (parallel_number, parallel_phase) or None if not in a group

    Example:
        >>> key = get_parallel_group_key(info)
        >>> if key:
        ...     print(f"Device is in parallel group {key}")
    """
    if info.parallel_number is not None and info.parallel_phase is not None:
        return (info.parallel_number, info.parallel_phase)
    return None


def group_by_parallel_config(
    devices: list[DeviceDiscoveryInfo],
) -> dict[tuple[int, int] | None, list[DeviceDiscoveryInfo]]:
    """Group discovered devices by their parallel configuration.

    Devices with matching (parallel_number, parallel_phase) values are
    considered to be in the same parallel group.

    Args:
        devices: List of discovered device information

    Returns:
        Dictionary mapping parallel group keys to lists of devices.
        Key is (parallel_number, parallel_phase) tuple, or None for
        standalone devices without parallel configuration.

    Example:
        >>> infos = [await discover_device_info(t) for t in transports]
        >>> groups = group_by_parallel_config(infos)
        >>> for key, members in groups.items():
        ...     if key:
        ...         print(f"Parallel group {key}: {len(members)} devices")
        ...     else:
        ...         print(f"Standalone devices: {len(members)}")
    """
    groups: dict[tuple[int, int] | None, list[DeviceDiscoveryInfo]] = {}

    for info in devices:
        key = get_parallel_group_key(info)
        groups.setdefault(key, []).append(info)

    return groups


async def discover_multiple_devices(
    transports: list[InverterTransport],
) -> list[DeviceDiscoveryInfo]:
    """Discover information from multiple transports concurrently.

    This function connects to multiple devices and discovers their
    information in parallel for faster discovery.

    Args:
        transports: List of transports (must be connected or connectable)

    Returns:
        List of DeviceDiscoveryInfo for each successfully discovered device

    Example:
        >>> transports = [
        ...     create_modbus_transport(host="192.168.1.100", serial="CE1"),
        ...     create_modbus_transport(host="192.168.1.101", serial="CE2"),
        ... ]
        >>> for t in transports:
        ...     await t.connect()
        >>> infos = await discover_multiple_devices(transports)
        >>> groups = group_by_parallel_config(infos)
    """
    import asyncio

    async def _discover_one(transport: InverterTransport) -> DeviceDiscoveryInfo | None:
        try:
            return await discover_device_info(transport)
        except Exception as err:
            _LOGGER.error("Failed to discover device %s: %s", transport.serial, err)
            return None

    results = await asyncio.gather(*[_discover_one(t) for t in transports])
    return [r for r in results if r is not None]


__all__ = [
    "DeviceDiscoveryInfo",
    "discover_device_info",
    "discover_multiple_devices",
    "get_model_family_name",
    "get_parallel_group_key",
    "group_by_parallel_config",
    "is_gridboss_device",
    "HOLD_DEVICE_TYPE_CODE",
    "HOLD_PARALLEL_NUMBER",
    "HOLD_PARALLEL_PHASE",
]
