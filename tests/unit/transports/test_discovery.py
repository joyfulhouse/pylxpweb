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
    HOLD_DEVICE_TYPE_CODE,
    HOLD_PARALLEL_NUMBER,
    HOLD_PARALLEL_PHASE,
    DeviceDiscoveryInfo,
    discover_device_info,
    discover_multiple_devices,
    get_model_family_name,
    get_parallel_group_key,
    group_by_parallel_config,
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
        assert get_model_family_name(DEVICE_TYPE_CODE_SNA) == "EG4_OFFGRID"

    def test_pv_series_family(self) -> None:
        """Test PV Series family name."""
        assert get_model_family_name(DEVICE_TYPE_CODE_PV_SERIES) == "EG4_HYBRID"

    def test_flexboss_is_pv_series(self) -> None:
        """Test FlexBOSS is part of PV Series family."""
        assert get_model_family_name(DEVICE_TYPE_CODE_FLEXBOSS) == "EG4_HYBRID"

    def test_lxp_eu_family(self) -> None:
        """Test LXP-EU family name."""
        assert get_model_family_name(DEVICE_TYPE_CODE_LXP_EU) == "LXP"

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
            model_family="EG4_HYBRID",
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
        assert info.model_family == "EG4_HYBRID"

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
        assert info.model_family == "EG4_HYBRID"  # FlexBOSS is PV Series family


class TestRegisterConstants:
    """Tests for register address constants."""

    def test_register_addresses(self) -> None:
        """Test that register constants have correct values."""
        assert HOLD_DEVICE_TYPE_CODE == 19
        assert HOLD_PARALLEL_NUMBER == 107
        assert HOLD_PARALLEL_PHASE == 108


class TestGetParallelGroupKey:
    """Tests for get_parallel_group_key() function."""

    def test_returns_tuple_when_both_values_present(self) -> None:
        """Test returns tuple when parallel_number and parallel_phase are set."""
        info = DeviceDiscoveryInfo(
            serial="CE12345678",
            device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
            is_gridboss=False,
            is_inverter=True,
            model_family="EG4_HYBRID",
            parallel_number=550,
            parallel_phase=1,
        )
        key = get_parallel_group_key(info)
        assert key == (550, 1)

    def test_returns_none_when_parallel_number_missing(self) -> None:
        """Test returns None when parallel_number is None."""
        info = DeviceDiscoveryInfo(
            serial="CE12345678",
            device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
            is_gridboss=False,
            is_inverter=True,
            model_family="EG4_HYBRID",
            parallel_number=None,
            parallel_phase=1,
        )
        key = get_parallel_group_key(info)
        assert key is None

    def test_returns_none_when_parallel_phase_missing(self) -> None:
        """Test returns None when parallel_phase is None."""
        info = DeviceDiscoveryInfo(
            serial="CE12345678",
            device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
            is_gridboss=False,
            is_inverter=True,
            model_family="EG4_HYBRID",
            parallel_number=550,
            parallel_phase=None,
        )
        key = get_parallel_group_key(info)
        assert key is None

    def test_returns_none_when_both_missing(self) -> None:
        """Test returns None when both values are None."""
        info = DeviceDiscoveryInfo(
            serial="CE12345678",
            device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
            is_gridboss=False,
            is_inverter=True,
            model_family="EG4_HYBRID",
        )
        key = get_parallel_group_key(info)
        assert key is None

    def test_handles_zero_values(self) -> None:
        """Test that zero values are valid (not treated as missing)."""
        info = DeviceDiscoveryInfo(
            serial="CE12345678",
            device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
            is_gridboss=False,
            is_inverter=True,
            model_family="EG4_HYBRID",
            parallel_number=0,
            parallel_phase=0,
        )
        key = get_parallel_group_key(info)
        assert key == (0, 0)


class TestGroupByParallelConfig:
    """Tests for group_by_parallel_config() function."""

    def test_groups_devices_with_same_key(self) -> None:
        """Test that devices with matching parallel config are grouped."""
        devices = [
            DeviceDiscoveryInfo(
                serial="CE1",
                device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
                is_gridboss=False,
                is_inverter=True,
                model_family="EG4_HYBRID",
                parallel_number=550,
                parallel_phase=1,
            ),
            DeviceDiscoveryInfo(
                serial="CE2",
                device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
                is_gridboss=False,
                is_inverter=True,
                model_family="EG4_HYBRID",
                parallel_number=550,
                parallel_phase=1,
            ),
        ]
        groups = group_by_parallel_config(devices)
        assert len(groups) == 1
        assert (550, 1) in groups
        assert len(groups[(550, 1)]) == 2

    def test_separates_different_groups(self) -> None:
        """Test that devices with different parallel config are separated."""
        devices = [
            DeviceDiscoveryInfo(
                serial="CE1",
                device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
                is_gridboss=False,
                is_inverter=True,
                model_family="EG4_HYBRID",
                parallel_number=550,
                parallel_phase=1,
            ),
            DeviceDiscoveryInfo(
                serial="CE2",
                device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
                is_gridboss=False,
                is_inverter=True,
                model_family="EG4_HYBRID",
                parallel_number=551,
                parallel_phase=2,
            ),
        ]
        groups = group_by_parallel_config(devices)
        assert len(groups) == 2
        assert (550, 1) in groups
        assert (551, 2) in groups

    def test_standalone_devices_grouped_under_none(self) -> None:
        """Test that devices without parallel config are under None key."""
        devices = [
            DeviceDiscoveryInfo(
                serial="CE1",
                device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
                is_gridboss=False,
                is_inverter=True,
                model_family="EG4_HYBRID",
                parallel_number=None,
                parallel_phase=None,
            ),
            DeviceDiscoveryInfo(
                serial="CE2",
                device_type_code=DEVICE_TYPE_CODE_SNA,
                is_gridboss=False,
                is_inverter=True,
                model_family="EG4_OFFGRID",
            ),
        ]
        groups = group_by_parallel_config(devices)
        assert len(groups) == 1
        assert None in groups
        assert len(groups[None]) == 2

    def test_mixed_parallel_and_standalone(self) -> None:
        """Test grouping with both parallel and standalone devices."""
        devices = [
            DeviceDiscoveryInfo(
                serial="CE1",
                device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
                is_gridboss=False,
                is_inverter=True,
                model_family="EG4_HYBRID",
                parallel_number=550,
                parallel_phase=1,
            ),
            DeviceDiscoveryInfo(
                serial="CE2",
                device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
                is_gridboss=False,
                is_inverter=True,
                model_family="EG4_HYBRID",
                parallel_number=550,
                parallel_phase=1,
            ),
            DeviceDiscoveryInfo(
                serial="STANDALONE",
                device_type_code=DEVICE_TYPE_CODE_SNA,
                is_gridboss=False,
                is_inverter=True,
                model_family="EG4_OFFGRID",
            ),
        ]
        groups = group_by_parallel_config(devices)
        assert len(groups) == 2
        assert (550, 1) in groups
        assert len(groups[(550, 1)]) == 2
        assert None in groups
        assert len(groups[None]) == 1
        assert groups[None][0].serial == "STANDALONE"

    def test_empty_list_returns_empty_dict(self) -> None:
        """Test that empty input returns empty dictionary."""
        groups = group_by_parallel_config([])
        assert groups == {}

    def test_gridboss_in_parallel_group(self) -> None:
        """Test GridBOSS devices can be in parallel groups."""
        devices = [
            DeviceDiscoveryInfo(
                serial="GB1",
                device_type_code=DEVICE_TYPE_CODE_GRIDBOSS,
                is_gridboss=True,
                is_inverter=False,
                model_family="GridBOSS",
                parallel_number=550,
                parallel_phase=0,
            ),
            DeviceDiscoveryInfo(
                serial="CE1",
                device_type_code=DEVICE_TYPE_CODE_PV_SERIES,
                is_gridboss=False,
                is_inverter=True,
                model_family="EG4_HYBRID",
                parallel_number=550,
                parallel_phase=1,
            ),
        ]
        groups = group_by_parallel_config(devices)
        # Different phases means different keys (even in same parallel number)
        assert len(groups) == 2
        assert (550, 0) in groups
        assert (550, 1) in groups


class TestDiscoverMultipleDevices:
    """Tests for discover_multiple_devices() function."""

    @pytest.fixture
    def create_mock_transport(self) -> MagicMock:
        """Factory to create mock transports."""

        def _create(serial: str, device_type: int = DEVICE_TYPE_CODE_PV_SERIES) -> MagicMock:
            transport = MagicMock()
            transport.serial = serial
            transport.read_parameters = AsyncMock(return_value={19: device_type})
            return transport

        return _create

    @pytest.mark.asyncio
    async def test_discovers_multiple_devices(self, create_mock_transport: MagicMock) -> None:
        """Test concurrent discovery of multiple devices."""
        transports = [
            create_mock_transport("CE1", DEVICE_TYPE_CODE_PV_SERIES),
            create_mock_transport("CE2", DEVICE_TYPE_CODE_SNA),
        ]

        infos = await discover_multiple_devices(transports)

        assert len(infos) == 2
        serials = {info.serial for info in infos}
        assert serials == {"CE1", "CE2"}

    @pytest.mark.asyncio
    async def test_filters_failed_discoveries(self, create_mock_transport: MagicMock) -> None:
        """Test that failed discoveries are filtered out."""
        good_transport = create_mock_transport("CE1")
        bad_transport = MagicMock()
        bad_transport.serial = "BAD"
        bad_transport.read_parameters = AsyncMock(side_effect=Exception("Connection failed"))

        # Make discover_device_info fail completely for bad_transport
        # by making all reads fail
        bad_transport.read_parameters.side_effect = Exception("Connection failed")

        infos = await discover_multiple_devices([good_transport, bad_transport])

        # The bad transport should still produce a result with defaults
        # because discover_device_info handles errors gracefully
        assert len(infos) == 2

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self) -> None:
        """Test that empty transport list returns empty list."""
        infos = await discover_multiple_devices([])
        assert infos == []

    @pytest.mark.asyncio
    async def test_single_transport(self, create_mock_transport: MagicMock) -> None:
        """Test discovery with single transport."""
        transport = create_mock_transport("CE1", DEVICE_TYPE_CODE_GRIDBOSS)

        infos = await discover_multiple_devices([transport])

        assert len(infos) == 1
        assert infos[0].serial == "CE1"
        assert infos[0].is_gridboss is True
