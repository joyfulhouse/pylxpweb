"""Tests for device discovery helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pylxpweb.devices.discovery import (
    HOLD_PARALLEL_NUMBER,
    HOLD_PARALLEL_PHASE,
    DeviceDiscoveryInfo,
    discover_device_info,
)


class TestDeviceDiscoveryInfo:
    """Tests for DeviceDiscoveryInfo dataclass."""

    def test_standalone_device(self) -> None:
        """Test a standalone device (not in parallel group)."""
        info = DeviceDiscoveryInfo(
            serial="CE12345678",
            device_type_code=2092,
            is_gridboss=False,
            parallel_master_slave=0,
            parallel_number=0,
            parallel_phase=0,
            firmware_version="FAAB-2525",
        )

        assert info.serial == "CE12345678"
        assert info.device_type_code == 2092
        assert info.is_gridboss is False
        assert info.parallel_master_slave == 0
        assert info.parallel_number == 0
        assert info.parallel_phase == 0
        assert info.is_standalone is True
        assert info.parallel_group_name is None
        assert info.parallel_role_name == "standalone"
        assert info.is_master is False

    def test_parallel_group_device(self) -> None:
        """Test a device in parallel group A as master."""
        info = DeviceDiscoveryInfo(
            serial="CE12345678",
            device_type_code=10284,
            is_gridboss=False,
            parallel_master_slave=1,  # Master
            parallel_number=1,
            parallel_phase=0,
            firmware_version="FAAB-2525",
        )

        assert info.parallel_number == 1
        assert info.parallel_master_slave == 1
        assert info.is_standalone is False
        assert info.parallel_group_name == "A"
        assert info.parallel_role_name == "master"
        assert info.parallel_phase_name == "R"
        assert info.is_master is True

    def test_parallel_group_b(self) -> None:
        """Test a device in parallel group B as slave."""
        info = DeviceDiscoveryInfo(
            serial="CE12345678",
            device_type_code=10284,
            is_gridboss=False,
            parallel_master_slave=2,  # Slave
            parallel_number=2,
            parallel_phase=1,
            firmware_version="FAAB-2525",
        )

        assert info.parallel_group_name == "B"
        assert info.parallel_role_name == "slave"
        assert info.parallel_phase_name == "S"
        assert info.is_master is False

    def test_gridboss_device(self) -> None:
        """Test a GridBOSS/MID device."""
        info = DeviceDiscoveryInfo(
            serial="CE12345678",
            device_type_code=50,
            is_gridboss=True,
            parallel_master_slave=0,  # GridBOSS typically standalone
            parallel_number=1,
            parallel_phase=0,
            firmware_version="GB-1234",
        )

        assert info.is_gridboss is True
        assert info.device_type_code == 50

    def test_3phase_master(self) -> None:
        """Test a 3-phase master device."""
        info = DeviceDiscoveryInfo(
            serial="CE12345678",
            device_type_code=10284,
            is_gridboss=False,
            parallel_master_slave=3,  # 3-phase master
            parallel_number=1,
            parallel_phase=2,
            firmware_version="FAAB-2525",
        )

        assert info.parallel_role_name == "3-phase master"
        assert info.parallel_phase_name == "T"


class TestDiscoverDeviceInfo:
    """Tests for discover_device_info function."""

    @pytest.mark.asyncio
    async def test_discovers_standalone_inverter(self) -> None:
        """Test discovering a standalone inverter."""
        # Create mock transport
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.read_device_type = AsyncMock(return_value=2092)
        transport.is_midbox_device = MagicMock(return_value=False)
        # Register 113 returns 0 for standalone (no parallel config)
        transport.read_parallel_config = AsyncMock(return_value=0)
        transport.read_parameters = AsyncMock(
            return_value={
                HOLD_PARALLEL_NUMBER: 0,
                HOLD_PARALLEL_PHASE: 0,
            }
        )
        transport.read_firmware_version = AsyncMock(return_value="FAAB-2525")

        info = await discover_device_info(transport)

        assert info.serial == "CE12345678"
        assert info.device_type_code == 2092
        assert info.is_gridboss is False
        assert info.parallel_master_slave == 0
        assert info.parallel_number == 0
        assert info.parallel_phase == 0
        assert info.is_standalone is True
        assert info.firmware_version == "FAAB-2525"

    @pytest.mark.asyncio
    async def test_discovers_parallel_group_device(self) -> None:
        """Test discovering a device in parallel group using register 113."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.read_device_type = AsyncMock(return_value=10284)
        transport.is_midbox_device = MagicMock(return_value=False)
        # Register 113 packed value: master_slave=1, phase=2, number=1
        # bits 0-1 = 1 (master), bits 2-3 = 2 (T), bits 8-15 = 1 (group A)
        # 0x0109 = (1 << 8) | (2 << 2) | 1 = 256 + 8 + 1 = 265
        transport.read_parallel_config = AsyncMock(return_value=0x0109)
        transport.read_parameters = AsyncMock(
            return_value={
                HOLD_PARALLEL_NUMBER: 1,
                HOLD_PARALLEL_PHASE: 2,
            }
        )
        transport.read_firmware_version = AsyncMock(return_value="FAAB-2525")

        info = await discover_device_info(transport)

        assert info.parallel_master_slave == 1  # Master
        assert info.parallel_number == 1
        assert info.parallel_phase == 2  # T
        assert info.parallel_group_name == "A"
        assert info.is_standalone is False
        assert info.is_master is True

    @pytest.mark.asyncio
    async def test_discovers_gridboss(self) -> None:
        """Test discovering a GridBOSS/MID device."""
        transport = MagicMock()
        transport.serial = "GB12345678"
        transport.read_device_type = AsyncMock(return_value=50)
        transport.is_midbox_device = MagicMock(return_value=True)
        # Register 113 = 0x0101: master=1, phase=0, number=1
        transport.read_parallel_config = AsyncMock(return_value=0x0101)
        transport.read_parameters = AsyncMock(
            return_value={
                HOLD_PARALLEL_NUMBER: 1,
                HOLD_PARALLEL_PHASE: 0,
            }
        )
        transport.read_firmware_version = AsyncMock(return_value="GB-1234")

        info = await discover_device_info(transport)

        assert info.device_type_code == 50
        assert info.is_gridboss is True
        assert info.parallel_master_slave == 1

    @pytest.mark.asyncio
    async def test_handles_firmware_read_failure(self) -> None:
        """Test graceful handling of firmware version read failure."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.read_device_type = AsyncMock(return_value=2092)
        transport.is_midbox_device = MagicMock(return_value=False)
        transport.read_parallel_config = AsyncMock(return_value=0)
        transport.read_parameters = AsyncMock(
            return_value={
                HOLD_PARALLEL_NUMBER: 0,
                HOLD_PARALLEL_PHASE: 0,
            }
        )
        transport.read_firmware_version = AsyncMock(side_effect=Exception("Firmware read failed"))

        info = await discover_device_info(transport)

        # Should still succeed with empty firmware version
        assert info.serial == "CE12345678"
        assert info.firmware_version == ""

    @pytest.mark.asyncio
    async def test_handles_missing_parallel_registers(self) -> None:
        """Test fallback to holding registers when register 113 fails."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.read_device_type = AsyncMock(return_value=2092)
        transport.is_midbox_device = MagicMock(return_value=False)
        # Register 113 read fails, should fallback to holding registers
        transport.read_parallel_config = AsyncMock(
            side_effect=Exception("Register 113 not supported")
        )
        transport.read_parameters = AsyncMock(return_value={})  # Empty response
        transport.read_firmware_version = AsyncMock(return_value="FAAB-2525")

        info = await discover_device_info(transport)

        # Should default to standalone (parallel_number=0)
        assert info.parallel_master_slave == 0
        assert info.parallel_number == 0
        assert info.parallel_phase == 0
        assert info.is_standalone is True

    @pytest.mark.asyncio
    async def test_handles_parallel_register_read_exception(self) -> None:
        """Test graceful handling when both register 113 and holding registers fail."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.read_device_type = AsyncMock(return_value=2092)
        transport.is_midbox_device = MagicMock(return_value=False)
        # Both register 113 and holding registers fail
        transport.read_parallel_config = AsyncMock(
            side_effect=Exception("Register 113 read failed")
        )
        transport.read_parameters = AsyncMock(side_effect=Exception("Modbus read failed"))
        transport.read_firmware_version = AsyncMock(return_value="FAAB-2525")

        info = await discover_device_info(transport)

        # Should default to standalone on exception
        assert info.parallel_master_slave == 0
        assert info.parallel_number == 0
        assert info.parallel_phase == 0
        assert info.is_standalone is True
        assert info.serial == "CE12345678"

    @pytest.mark.asyncio
    async def test_register_113_parsing(self) -> None:
        """Test correct parsing of register 113 packed value."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.read_device_type = AsyncMock(return_value=10284)
        transport.is_midbox_device = MagicMock(return_value=False)
        # Register 113 = 0x0205: master_slave=1 (master), phase=1 (S), number=2 (group B)
        # bits 0-1 = 1, bits 2-3 = 1, bits 8-15 = 2
        # 0x0205 = (2 << 8) | (1 << 2) | 1 = 512 + 4 + 1 = 517
        transport.read_parallel_config = AsyncMock(return_value=0x0205)
        transport.read_parameters = AsyncMock(return_value={})
        transport.read_firmware_version = AsyncMock(return_value="FAAB-2525")

        info = await discover_device_info(transport)

        assert info.parallel_master_slave == 1  # Master
        assert info.parallel_phase == 1  # S
        assert info.parallel_number == 2  # Group B
        assert info.parallel_role_name == "master"
        assert info.parallel_phase_name == "S"
        assert info.parallel_group_name == "B"
        assert info.is_master is True


class TestParallelGroupConstants:
    """Tests for parallel group register constants."""

    def test_parallel_number_register(self) -> None:
        """Test parallel number register address."""
        assert HOLD_PARALLEL_NUMBER == 107

    def test_parallel_phase_register(self) -> None:
        """Test parallel phase register address."""
        assert HOLD_PARALLEL_PHASE == 108
