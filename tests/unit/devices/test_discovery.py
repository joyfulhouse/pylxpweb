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
            parallel_number=0,
            parallel_phase=0,
            firmware_version="FAAB-2525",
        )

        assert info.serial == "CE12345678"
        assert info.device_type_code == 2092
        assert info.is_gridboss is False
        assert info.parallel_number == 0
        assert info.parallel_phase == 0
        assert info.is_standalone is True
        assert info.parallel_group_name is None

    def test_parallel_group_device(self) -> None:
        """Test a device in parallel group A."""
        info = DeviceDiscoveryInfo(
            serial="CE12345678",
            device_type_code=10284,
            is_gridboss=False,
            parallel_number=1,
            parallel_phase=0,
            firmware_version="FAAB-2525",
        )

        assert info.parallel_number == 1
        assert info.is_standalone is False
        assert info.parallel_group_name == "A"

    def test_parallel_group_b(self) -> None:
        """Test a device in parallel group B."""
        info = DeviceDiscoveryInfo(
            serial="CE12345678",
            device_type_code=10284,
            is_gridboss=False,
            parallel_number=2,
            parallel_phase=1,
            firmware_version="FAAB-2525",
        )

        assert info.parallel_group_name == "B"

    def test_gridboss_device(self) -> None:
        """Test a GridBOSS/MID device."""
        info = DeviceDiscoveryInfo(
            serial="CE12345678",
            device_type_code=50,
            is_gridboss=True,
            parallel_number=1,
            parallel_phase=0,
            firmware_version="GB-1234",
        )

        assert info.is_gridboss is True
        assert info.device_type_code == 50


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
        assert info.parallel_number == 0
        assert info.parallel_phase == 0
        assert info.is_standalone is True
        assert info.firmware_version == "FAAB-2525"

    @pytest.mark.asyncio
    async def test_discovers_parallel_group_device(self) -> None:
        """Test discovering a device in parallel group."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.read_device_type = AsyncMock(return_value=10284)
        transport.is_midbox_device = MagicMock(return_value=False)
        transport.read_parameters = AsyncMock(
            return_value={
                HOLD_PARALLEL_NUMBER: 1,
                HOLD_PARALLEL_PHASE: 2,
            }
        )
        transport.read_firmware_version = AsyncMock(return_value="FAAB-2525")

        info = await discover_device_info(transport)

        assert info.parallel_number == 1
        assert info.parallel_phase == 2
        assert info.parallel_group_name == "A"
        assert info.is_standalone is False

    @pytest.mark.asyncio
    async def test_discovers_gridboss(self) -> None:
        """Test discovering a GridBOSS/MID device."""
        transport = MagicMock()
        transport.serial = "GB12345678"
        transport.read_device_type = AsyncMock(return_value=50)
        transport.is_midbox_device = MagicMock(return_value=True)
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

    @pytest.mark.asyncio
    async def test_handles_firmware_read_failure(self) -> None:
        """Test graceful handling of firmware version read failure."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.read_device_type = AsyncMock(return_value=2092)
        transport.is_midbox_device = MagicMock(return_value=False)
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
        """Test handling when parallel registers are not present."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.read_device_type = AsyncMock(return_value=2092)
        transport.is_midbox_device = MagicMock(return_value=False)
        transport.read_parameters = AsyncMock(return_value={})  # Empty response
        transport.read_firmware_version = AsyncMock(return_value="FAAB-2525")

        info = await discover_device_info(transport)

        # Should default to standalone (parallel_number=0)
        assert info.parallel_number == 0
        assert info.parallel_phase == 0
        assert info.is_standalone is True

    @pytest.mark.asyncio
    async def test_handles_parallel_register_read_exception(self) -> None:
        """Test graceful handling when read_parameters raises an exception."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.read_device_type = AsyncMock(return_value=2092)
        transport.is_midbox_device = MagicMock(return_value=False)
        transport.read_parameters = AsyncMock(side_effect=Exception("Modbus read failed"))
        transport.read_firmware_version = AsyncMock(return_value="FAAB-2525")

        info = await discover_device_info(transport)

        # Should default to standalone on exception
        assert info.parallel_number == 0
        assert info.parallel_phase == 0
        assert info.is_standalone is True
        assert info.serial == "CE12345678"


class TestParallelGroupConstants:
    """Tests for parallel group register constants."""

    def test_parallel_number_register(self) -> None:
        """Test parallel number register address."""
        assert HOLD_PARALLEL_NUMBER == 107

    def test_parallel_phase_register(self) -> None:
        """Test parallel phase register address."""
        assert HOLD_PARALLEL_PHASE == 108
