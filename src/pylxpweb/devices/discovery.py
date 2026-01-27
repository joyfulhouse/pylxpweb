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

# Parallel group register addresses
# Input register 113 contains packed parallel config (preferred source):
#   bits 0-1: master/slave (0=standalone, 1=master, 2=slave, 3=3-phase master)
#   bits 2-3: phase (0=R, 1=S, 2=T)
#   bits 8-15: parallel number (unit ID in group)
INPUT_PARALLEL_CONFIG = 113

# Legacy holding registers (less reliable, kept for fallback)
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

    async def read_parallel_config(self) -> int:
        """Read parallel configuration from input register 113.

        Returns:
            Raw 16-bit value with packed parallel config, or 0 if read fails.
            Format: bits 0-1 = master/slave, bits 2-3 = phase, bits 8-15 = number
        """
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
        parallel_master_slave: Role in parallel group
            - 0: Standalone (not in parallel group)
            - 1: Master (primary inverter)
            - 2: Slave (subordinate inverter)
            - 3: 3-phase master
        parallel_number: Parallel group number (0 = standalone, 1-n = group)
        parallel_phase: Phase assignment in parallel group (0=R, 1=S, 2=T)
        firmware_version: Firmware version string (if readable)

    Example:
        info = DeviceDiscoveryInfo(
            serial="CE12345678",
            device_type_code=10284,
            is_gridboss=False,
            parallel_master_slave=1,
            parallel_number=2,
            parallel_phase=1,
            firmware_version="FAAB-2525",
        )

        if info.is_standalone:
            print("Standalone device")
        else:
            print(f"Part of parallel group {info.parallel_group_name}")
            print(f"Role: {info.parallel_role_name}")
    """

    serial: str
    device_type_code: int
    is_gridboss: bool
    parallel_master_slave: int
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
    def parallel_role_name(self) -> str:
        """Get human-readable parallel role name.

        Returns:
            Role name: 'standalone', 'master', 'slave', or '3-phase master'
        """
        role_names = {0: "standalone", 1: "master", 2: "slave", 3: "3-phase master"}
        return role_names.get(self.parallel_master_slave, "unknown")

    @property
    def parallel_phase_name(self) -> str:
        """Get phase name (R, S, or T).

        Returns:
            Phase letter: 'R', 'S', or 'T'
        """
        phase_names = {0: "R", 1: "S", 2: "T"}
        return phase_names.get(self.parallel_phase, "?")

    @property
    def is_standalone(self) -> bool:
        """Check if device is standalone (not in parallel group).

        Returns:
            True if device is standalone, False if in a parallel group.
        """
        # Check both parallel_number and parallel_master_slave
        # Device is standalone if parallel_number is 0 or master_slave is 0
        return self.parallel_number == 0 or self.parallel_master_slave == 0

    @property
    def is_master(self) -> bool:
        """Check if device is the master in a parallel group.

        Returns:
            True if device is the master (primary) inverter.
        """
        return self.parallel_master_slave == 1


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

    # Read parallel config from input register 113 (preferred source)
    # Format: bits 0-1 = master/slave, bits 2-3 = phase, bits 8-15 = parallel number
    parallel_master_slave = 0
    parallel_number = 0
    parallel_phase = 0

    try:
        reg113_raw = await transport.read_parallel_config()
        if reg113_raw > 0:
            # Parse packed parallel config
            parallel_master_slave = reg113_raw & 0x03
            parallel_phase = (reg113_raw >> 2) & 0x03
            parallel_number = (reg113_raw >> 8) & 0xFF
            _LOGGER.debug(
                "Parsed register 113 for %s: raw=0x%04X, master_slave=%d, phase=%d, number=%d",
                transport.serial,
                reg113_raw,
                parallel_master_slave,
                parallel_phase,
                parallel_number,
            )
    except Exception as e:
        _LOGGER.debug(
            "Failed to read parallel config register 113 for %s: %s, trying fallback",
            transport.serial,
            e,
        )
        # Fallback to holding registers 107-108 (less reliable)
        try:
            parallel_regs = await transport.read_parameters(HOLD_PARALLEL_NUMBER, 2)
            parallel_number = parallel_regs.get(HOLD_PARALLEL_NUMBER, 0) & 0xFF
            parallel_phase = parallel_regs.get(HOLD_PARALLEL_PHASE, 0) & 0xFF
        except Exception as e2:
            _LOGGER.debug(
                "Failed to read fallback parallel registers for %s: %s",
                transport.serial,
                e2,
            )
        # Default to standalone if both fail

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
        "Discovered device %s: type=%d, gridboss=%s, role=%d, parallel=%d, phase=%d",
        transport.serial,
        device_type_code,
        is_gridboss,
        parallel_master_slave,
        parallel_number,
        parallel_phase,
    )

    return DeviceDiscoveryInfo(
        serial=transport.serial,
        device_type_code=device_type_code,
        is_gridboss=is_gridboss,
        parallel_master_slave=parallel_master_slave,
        parallel_number=parallel_number,
        parallel_phase=parallel_phase,
        firmware_version=firmware_version,
    )


__all__ = [
    "DeviceDiscoveryInfo",
    "discover_device_info",
    "INPUT_PARALLEL_CONFIG",
    "HOLD_PARALLEL_NUMBER",
    "HOLD_PARALLEL_PHASE",
]
