"""Tests for device discovery utilities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pylxpweb.constants import (
    DEVICE_TYPE_CODE_FLEXBOSS,
    DEVICE_TYPE_CODE_GRIDBOSS,
    DEVICE_TYPE_CODE_LXP_EU,
    DEVICE_TYPE_CODE_PV_SERIES,
    DEVICE_TYPE_CODE_SNA,
)
from pylxpweb.transports.discovery import (
    DeviceDiscoveryInfo,
    discover_device_info,
    get_model_family_name,
    is_gridboss_device,
)


class TestIsGridbossDevice:
    """Tests for is_gridboss_device() function."""

    def test_gridboss_returns_true(self) -> None:
        """Test that GridBOSS device type code returns True."""
        assert is_gridboss_device(DEVICE_TYPE_CODE_GRIDBOSS) is True

    def test_pv_series_returns_false(self) -> None:
        """Test that PV Series device type code returns False."""
        assert is_gridboss_device(DEVICE_TYPE_CODE_PV_SERIES) is False

    def test_sna_returns_false(self) -> None:
        """Test that SNA device type code returns False."""
        assert is_gridboss_device(DEVICE_TYPE_CODE_SNA) is False

    def test_flexboss_returns_false(self) -> None:
        """Test that FlexBOSS device type code returns False."""
        assert is_gridboss_device(DEVICE_TYPE_CODE_FLEXBOSS) is False

    def test_lxp_eu_returns_false(self) -> None:
        """Test that LXP-EU device type code returns False."""
        assert is_gridboss_device(DEVICE_TYPE_CODE_LXP_EU) is False

    def test_unknown_returns_false(self) -> None:
        """Test that unknown device type code returns False."""
        assert is_gridboss_device(0) is False
        assert is_gridboss_device(9999) is False


class TestGetModelFamilyName:
    """Tests for get_model_family_name() function."""

    def test_gridboss_family(self) -> None:
        """Test GridBOSS family name."""
        assert get_model_family_name(DEVICE_TYPE_CODE_GRIDBOSS) == "GridBOSS"

    def test_sna_family(self) -> None:
        """Test SNA family name."""
        assert get_model_family_name(DEVICE_TYPE_CODE_SNA) == "SNA"

    def test_pv_series_family(self) -> None:
        """Test PV Series family name."""
        assert get_model_family_name(DEVICE_TYPE_CODE_PV_SERIES) == "PV_SERIES"

    def test_flexboss_is_pv_series(self) -> None:
        """Test FlexBOSS is part of PV Series family."""
        assert get_model_family_name(DEVICE_TYPE_CODE_FLEXBOSS) == "PV_SERIES"

    def test_lxp_eu_family(self) -> None:
        """Test LXP-EU family name."""
        assert get_model_family_name(DEVICE_TYPE_CODE_LXP_EU) == "LXP_EU"

    def test_unknown_family(self) -> None:
        """Test unknown device type returns UNKNOWN."""
        assert get_model_family_name(0) == "UNKNOWN"
        assert get_model_family_name(9999) == "UNKNOWN"


class TestDeviceDiscoveryInfo:
    """Tests for DeviceDiscoveryInfo dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic DeviceDiscoveryInfo creation."""
        info = DeviceDiscoveryInfo(
            serial="CE12345678",
            device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
            is_gridboss=False,
            is_inverter=True,
            model_family="PV_SERIES",
        )
        assert info.serial == "CE12345678"
        assert info.device_type_code == DEVICE_TYPE_CODE_PV_SERIES
        assert info.is_gridboss is False
        assert info.is_inverter is True
        assert info.parallel_number is None
        assert info.parallel_phase is None

    def test_gridboss_info(self) -> None:
        """Test DeviceDiscoveryInfo for GridBOSS."""
        info = DeviceDiscoveryInfo(
            serial="GB12345678",
            device_type_code=DEVICE_TYPE_CODE_GRIDBOSS,
            is_gridboss=True,
            is_inverter=False,
            model_family="GridBOSS",
            parallel_number=550,
            parallel_phase=0,
        )
        assert info.is_gridboss is True
        assert info.is_inverter is False
        assert info.parallel_number == 550
        assert info.parallel_phase == 0


class TestDiscoverDeviceInfo:
    """Tests for discover_device_info() function."""

    @pytest.fixture
    def mock_transport(self) -> MagicMock:
        """Create a mock transport."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.read_parameters = AsyncMock()
        return transport

    @pytest.mark.asyncio
    async def test_discover_pv_series(self, mock_transport: MagicMock) -> None:
        """Test discovering a PV Series inverter."""
        mock_transport.read_parameters.return_value = {
            19: DEVICE_TYPE_CODE_PV_SERIES,
        }

        info = await discover_device_info(mock_transport)

        assert info.serial == "CE12345678"
        assert info.device_type_code == DEVICE_TYPE_CODE_PV_SERIES
        assert info.is_gridboss is False
        assert info.is_inverter is True
        assert info.model_family == "PV_SERIES"

    @pytest.mark.asyncio
    async def test_discover_gridboss(self, mock_transport: MagicMock) -> None:
        """Test discovering a GridBOSS device."""
        mock_transport.serial = "GB12345678"
        mock_transport.read_parameters.return_value = {
            19: DEVICE_TYPE_CODE_GRIDBOSS,
        }

        info = await discover_device_info(mock_transport)

        assert info.serial == "GB12345678"
        assert info.device_type_code == DEVICE_TYPE_CODE_GRIDBOSS
        assert info.is_gridboss is True
        assert info.is_inverter is False
        assert info.model_family == "GridBOSS"

    @pytest.mark.asyncio
    async def test_discover_with_parallel_group(self, mock_transport: MagicMock) -> None:
        """Test discovering device with parallel group info."""
        # First call returns device type, second call returns parallel info
        mock_transport.read_parameters.side_effect = [
            {19: DEVICE_TYPE_CODE_PV_SERIES},
            {107: 550, 108: 0},
        ]

        info = await discover_device_info(mock_transport)

        assert info.parallel_number == 550
        assert info.parallel_phase == 0

    @pytest.mark.asyncio
    async def test_discover_with_firmware_version(self, mock_transport: MagicMock) -> None:
        """Test discovering device with firmware version."""
        mock_transport.read_parameters.return_value = {19: DEVICE_TYPE_CODE_PV_SERIES}
        mock_transport.read_firmware_version = AsyncMock(return_value="FAAB-2525")

        info = await discover_device_info(mock_transport)

        assert info.firmware_version == "FAAB-2525"

    @pytest.mark.asyncio
    async def test_discover_handles_read_failure(self, mock_transport: MagicMock) -> None:
        """Test that discovery handles read failures gracefully."""
        mock_transport.read_parameters.side_effect = Exception("Read error")

        info = await discover_device_info(mock_transport)

        # Should return default values, not raise
        assert info.device_type_code == 0
        assert info.is_gridboss is False
        assert info.is_inverter is False
        assert info.model_family == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_discover_flexboss(self, mock_transport: MagicMock) -> None:
        """Test discovering a FlexBOSS inverter."""
        mock_transport.read_parameters.return_value = {
            19: DEVICE_TYPE_CODE_FLEXBOSS,
        }

        info = await discover_device_info(mock_transport)

        assert info.device_type_code == DEVICE_TYPE_CODE_FLEXBOSS
        assert info.is_gridboss is False
        assert info.is_inverter is True
        assert info.model_family == "PV_SERIES"  # FlexBOSS is PV Series family
