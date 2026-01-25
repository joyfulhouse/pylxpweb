"""Device discovery helpers for local transports.

This module provides utilities for auto-detecting device information
from Modbus/Dongle transports, including device type detection and
parallel group membership.

Example:
    transport = create_modbus_transport(host="192.168.1.100", serial="CE12345678")
    await transport.connect()

    info = await discover_device_info(transport)
    print(f"Device type: {info.device_type_code}")
    print(f"Is GridBOSS: {info.is_gridboss}")
    print(f"Parallel group: {info.parallel_group_name or 'standalone'}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

_LOGGER = logging.getLogger(__name__)

# Parallel group register addresses (holding registers)
HOLD_PARALLEL_NUMBER = 107  # 0 = standalone, 1-n = group number
HOLD_PARALLEL_PHASE = 108  # Phase assignment within group


class DiscoveryTransport(Protocol):
    """Protocol for transports supporting device discovery.

    Both ModbusTransport and DongleTransport implement these methods.
    """

    @property
    def serial(self) -> str:
        """Get the device serial number."""
        ...

    async def read_device_type(self) -> int:
        """Read device type code from register 19."""
        ...

    def is_midbox_device(self, device_type_code: int) -> bool:
        """Check if device type indicates a MID/GridBOSS."""
        ...

    async def read_parameters(
        self,
        start_address: int,
        count: int,
    ) -> dict[int, int]:
        """Read holding registers."""
        ...

    async def read_firmware_version(self) -> str:
        """Read firmware version from device."""
        ...


@dataclass
class DeviceDiscoveryInfo:
    """Auto-detected device information from registers.

    This dataclass contains device identification information gathered
    from Modbus/Dongle register reads during local discovery.

    Attributes:
        serial: Device serial number (from config, validated against device)
        device_type_code: Device type from register 19
            - 50: MID/GridBOSS
            - 54: SNA Series
            - 2092: PV Series (18KPV)
            - 10284: FlexBOSS21/FlexBOSS18
        is_gridboss: True if device is GridBOSS/MID controller
        parallel_number: Parallel group number (0 = standalone, 1-n = group)
        parallel_phase: Phase assignment in parallel group
        firmware_version: Firmware version string (if readable)

    Example:
        info = DeviceDiscoveryInfo(
            serial="CE12345678",
            device_type_code=10284,
            is_gridboss=False,
            parallel_number=1,
            parallel_phase=0,
            firmware_version="FAAB-2525",
        )

        if info.is_standalone:
            print("Standalone device")
        else:
            print(f"Part of parallel group {info.parallel_group_name}")
    """

    serial: str
    device_type_code: int
    is_gridboss: bool
    parallel_number: int
    parallel_phase: int
    firmware_version: str

    @property
    def parallel_group_name(self) -> str | None:
        """Get parallel group name (e.g., 'A', 'B') or None if standalone.

        Returns:
            Group name ('A' for group 1, 'B' for group 2, etc.) or None
            if the device is standalone.
        """
        if self.parallel_number == 0:
            return None
        # Group name: 'A' for group 1, 'B' for group 2, etc.
        return chr(ord("A") + self.parallel_number - 1)

    @property
    def is_standalone(self) -> bool:
        """Check if device is standalone (not in parallel group).

        Returns:
            True if device is standalone, False if in a parallel group.
        """
        return self.parallel_number == 0


async def discover_device_info(transport: DiscoveryTransport) -> DeviceDiscoveryInfo:
    """Auto-discover device information from Modbus/Dongle registers.

    This function reads key registers to identify the device type,
    parallel group membership, and firmware version.

    Args:
        transport: Connected transport instance (ModbusTransport or DongleTransport)

    Returns:
        DeviceDiscoveryInfo with auto-detected values

    Raises:
        TransportReadError: If critical register reads fail (device type)

    Note:
        Firmware version read failure is handled gracefully (returns empty string).
        Parallel group register read failure defaults to standalone (0).

    Example:
        transport = create_modbus_transport(host="192.168.1.100", serial="CE12345678")
        await transport.connect()

        info = await discover_device_info(transport)
        print(f"Device {info.serial}: type={info.device_type_code}")
    """
    # Read device type code from register 19
    device_type_code = await transport.read_device_type()
    is_gridboss = transport.is_midbox_device(device_type_code)

    # Read parallel group registers (holding registers 107-108)
    parallel_number = 0
    parallel_phase = 0
    try:
        parallel_regs = await transport.read_parameters(HOLD_PARALLEL_NUMBER, 2)
        parallel_number = parallel_regs.get(HOLD_PARALLEL_NUMBER, 0)
        parallel_phase = parallel_regs.get(HOLD_PARALLEL_PHASE, 0)
    except Exception as e:
        _LOGGER.debug(
            "Failed to read parallel group registers for %s: %s",
            transport.serial,
            e,
        )
        # Default to standalone

    # Read firmware version (best effort - may fail on some devices)
    firmware_version = ""
    try:
        firmware_version = await transport.read_firmware_version()
    except Exception as e:
        _LOGGER.debug(
            "Failed to read firmware version for %s: %s",
            transport.serial,
            e,
        )

    _LOGGER.info(
        "Discovered device %s: type=%d, gridboss=%s, parallel=%d, phase=%d",
        transport.serial,
        device_type_code,
        is_gridboss,
        parallel_number,
        parallel_phase,
    )

    return DeviceDiscoveryInfo(
        serial=transport.serial,
        device_type_code=device_type_code,
        is_gridboss=is_gridboss,
        parallel_number=parallel_number,
        parallel_phase=parallel_phase,
        firmware_version=firmware_version,
    )


__all__ = [
    "DeviceDiscoveryInfo",
    "DiscoveryTransport",
    "discover_device_info",
    "HOLD_PARALLEL_NUMBER",
    "HOLD_PARALLEL_PHASE",
]
