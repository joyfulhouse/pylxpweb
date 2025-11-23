"""Unit tests for FirmwareUpdateMixin."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb.devices._firmware_update_mixin import FirmwareUpdateMixin
from pylxpweb.devices.base import BaseDevice
from pylxpweb.models import (
    FirmwareUpdateCheck,
    FirmwareUpdateDetails,
    FirmwareUpdateInfo,
    UpdateEligibilityMessage,
    UpdateEligibilityStatus,
)


def _create_firmware_check(
    v1: int = 13,
    v2: int = 0,
    last_v1: int | None = None,
    last_v2: int | None = None,
    info_url: str | None = None,
) -> FirmwareUpdateCheck:
    """Helper to create FirmwareUpdateCheck for testing.

    Note: v1 and v2 are decimal values from API, but fwCodeBeforeUpload uses hex format.
    Example: v1=13, v2=0 → "IAAB-0D00" (13=0x0D, 0=0x00)
    """
    details = FirmwareUpdateDetails.model_construct(
        serialNum="1234567890",
        deviceType=6,
        standard="",
        firmwareType="",
        fwCodeBeforeUpload=f"IAAB-{v1:02X}{v2:02X}",  # Hex format
        v1=v1,
        v2=v2,
        v3Value=0,
        lastV1=last_v1,
        lastV1FileName=None,  # Let from_api_response() construct the version
        lastV2=last_v2,
        lastV2FileName=None,  # Let from_api_response() construct the version
        m3Version=0,
        pcs1UpdateMatch=last_v1 is not None and last_v1 > v1,
        pcs2UpdateMatch=last_v2 is not None and last_v2 > v2,
        pcs3UpdateMatch=False,
        needRunStep2=False,
        needRunStep3=False,
        needRunStep4=False,
        needRunStep5=False,
        midbox=False,
        lowVoltBattery=True,
        type6=True,
    )
    return FirmwareUpdateCheck(
        success=True,
        details=details,
        info_url=info_url,
    )


# Device class that uses the mixin (renamed to avoid pytest collection)
class FirmwareTestDevice(FirmwareUpdateMixin, BaseDevice):
    """Test device class for FirmwareUpdateMixin testing."""

    def __init__(self, client: Mock, serial_number: str, model: str) -> None:
        """Initialize test device."""
        super().__init__(client, serial_number, model)
        self._init_firmware_update_cache()

    async def refresh(self) -> None:
        """Refresh device data."""
        pass

    def to_device_info(self) -> dict:
        """Return device info."""
        return {}

    def to_entities(self) -> list:
        """Return entities."""
        return []


@pytest.fixture
def mock_client() -> Mock:
    """Create mock LuxpowerClient."""
    client = Mock()
    client.api = Mock()
    client.api.firmware = Mock()
    return client


@pytest.fixture
def test_device(mock_client: Mock) -> FirmwareTestDevice:
    """Create test device with mixin."""
    return FirmwareTestDevice(client=mock_client, serial_number="1234567890", model="Test Model")


class TestFirmwareUpdateMixinInitialization:
    """Tests for FirmwareUpdateMixin initialization."""

    def test_init_firmware_update_cache(self, test_device: FirmwareTestDevice) -> None:
        """Test that _init_firmware_update_cache initializes all attributes."""
        assert test_device._firmware_update_info is None
        assert test_device._firmware_update_cache_time is None
        assert test_device._firmware_update_cache_ttl == timedelta(hours=24)
        assert test_device._firmware_update_cache_lock is not None


class TestFirmwareUpdateAvailableProperty:
    """Tests for firmware_update_available property."""

    def test_firmware_update_available_returns_none_when_never_checked(
        self, test_device: FirmwareTestDevice
    ) -> None:
        """Test property returns None when firmware has never been checked."""
        assert test_device.firmware_update_available is None

    def test_firmware_update_available_returns_true_when_update_exists(
        self, test_device: FirmwareTestDevice
    ) -> None:
        """Test property returns True when update is available."""
        # Manually set cache
        test_device._firmware_update_info = FirmwareUpdateInfo(
            installed_version="IAAB-1300",
            latest_version="IAAB-1400",
            title="Test Firmware",
        )

        assert test_device.firmware_update_available is True

    def test_firmware_update_available_returns_false_when_up_to_date(
        self, test_device: FirmwareTestDevice
    ) -> None:
        """Test property returns False when device is up to date."""
        # Manually set cache
        test_device._firmware_update_info = FirmwareUpdateInfo(
            installed_version="IAAB-1400",
            latest_version="IAAB-1400",
            title="Test Firmware",
        )

        assert test_device.firmware_update_available is False


class TestFirmwareUpdateCacheProperties:
    """Tests for cached firmware update info properties."""

    def test_properties_return_none_when_never_checked(
        self, test_device: FirmwareTestDevice
    ) -> None:
        """Test all properties return None when firmware has never been checked."""
        assert test_device.latest_firmware_version is None
        assert test_device.firmware_update_title is None
        assert test_device.firmware_update_summary is None
        assert test_device.firmware_update_url is None

    def test_latest_firmware_version_returns_cached_value(
        self, test_device: FirmwareTestDevice
    ) -> None:
        """Test latest_firmware_version property returns cached value."""
        test_device._firmware_update_info = FirmwareUpdateInfo(
            installed_version="IAAB-1300",
            latest_version="IAAB-1400",
            title="Test Firmware",
        )

        assert test_device.latest_firmware_version == "IAAB-1400"

    def test_firmware_update_title_returns_cached_value(
        self, test_device: FirmwareTestDevice
    ) -> None:
        """Test firmware_update_title property returns cached value."""
        test_device._firmware_update_info = FirmwareUpdateInfo(
            installed_version="IAAB-1300",
            latest_version="IAAB-1400",
            title="Test Firmware v1.4",
        )

        assert test_device.firmware_update_title == "Test Firmware v1.4"

    def test_firmware_update_summary_returns_cached_value(
        self, test_device: FirmwareTestDevice
    ) -> None:
        """Test firmware_update_summary property returns cached value."""
        test_device._firmware_update_info = FirmwareUpdateInfo(
            installed_version="IAAB-1300",
            latest_version="IAAB-1400",
            title="Test Firmware",
            release_summary="Bug fixes and performance improvements",
        )

        assert test_device.firmware_update_summary == "Bug fixes and performance improvements"

    def test_firmware_update_url_returns_cached_value(
        self, test_device: FirmwareTestDevice
    ) -> None:
        """Test firmware_update_url property returns cached value."""
        test_device._firmware_update_info = FirmwareUpdateInfo(
            installed_version="IAAB-1300",
            latest_version="IAAB-1400",
            title="Test Firmware",
            release_url="https://example.com/release-notes",
        )

        assert test_device.firmware_update_url == "https://example.com/release-notes"

    def test_properties_return_none_when_release_info_missing(
        self, test_device: FirmwareTestDevice
    ) -> None:
        """Test properties return None when optional release info is missing."""
        test_device._firmware_update_info = FirmwareUpdateInfo(
            installed_version="IAAB-1300",
            latest_version="IAAB-1400",
            title="Test Firmware",
        )

        # These are optional and should be None
        assert test_device.firmware_update_summary is None
        assert test_device.firmware_update_url is None


class TestCheckFirmwareUpdates:
    """Tests for check_firmware_updates() method."""

    @pytest.mark.asyncio
    async def test_check_firmware_updates_fetches_from_api(
        self, test_device: FirmwareTestDevice, mock_client: Mock
    ) -> None:
        """Test check_firmware_updates fetches data from API."""
        # Mock API response
        api_check = _create_firmware_check(
            v1=13, v2=0, last_v1=14, last_v2=None, info_url="https://example.com/release"
        )
        mock_client.api.firmware.check_firmware_updates = AsyncMock(return_value=api_check)

        # Call method
        result = await test_device.check_firmware_updates()

        # Verify API was called
        mock_client.api.firmware.check_firmware_updates.assert_called_once_with("1234567890")

        # Verify result
        assert isinstance(result, FirmwareUpdateInfo)
        assert result.installed_version == "IAAB-0D00"  # v1=13(0x0D), v2=0(0x00)
        assert result.latest_version == "IAAB-0E00"  # v1=14(0x0E), v2=0(0x00)
        assert result.update_available is True
        assert result.title == "Test Model Firmware"

    @pytest.mark.asyncio
    async def test_check_firmware_updates_caches_result(
        self, test_device: FirmwareTestDevice, mock_client: Mock
    ) -> None:
        """Test check_firmware_updates caches the result."""
        # Mock API response
        api_check = _create_firmware_check(v1=13, v2=0, last_v1=14, last_v2=0, info_url=None)
        mock_client.api.firmware.check_firmware_updates = AsyncMock(return_value=api_check)

        # First call
        await test_device.check_firmware_updates()

        # Verify cache was set
        assert test_device._firmware_update_info is not None
        assert test_device._firmware_update_cache_time is not None
        assert isinstance(test_device._firmware_update_cache_time, datetime)

    @pytest.mark.asyncio
    async def test_check_firmware_updates_uses_cache_when_valid(
        self, test_device: FirmwareTestDevice, mock_client: Mock
    ) -> None:
        """Test check_firmware_updates uses cache when TTL not expired."""
        # Mock API response
        api_check = _create_firmware_check(v1=13, v2=0, last_v1=14, last_v2=0, info_url=None)
        mock_client.api.firmware.check_firmware_updates = AsyncMock(return_value=api_check)

        # First call - should hit API
        result1 = await test_device.check_firmware_updates()

        # Second call - should use cache
        result2 = await test_device.check_firmware_updates()

        # API should only be called once
        assert mock_client.api.firmware.check_firmware_updates.call_count == 1

        # Results should be identical
        assert result1 == result2

    @pytest.mark.asyncio
    async def test_check_firmware_updates_force_bypasses_cache(
        self, test_device: FirmwareTestDevice, mock_client: Mock
    ) -> None:
        """Test check_firmware_updates with force=True bypasses cache."""
        # Mock API response
        api_check = _create_firmware_check(v1=13, v2=0, last_v1=14, last_v2=0, info_url=None)
        mock_client.api.firmware.check_firmware_updates = AsyncMock(return_value=api_check)

        # First call
        await test_device.check_firmware_updates()

        # Second call with force=True - should hit API again
        await test_device.check_firmware_updates(force=True)

        # API should be called twice
        assert mock_client.api.firmware.check_firmware_updates.call_count == 2

    @pytest.mark.asyncio
    async def test_check_firmware_updates_expired_cache_fetches_again(
        self, test_device: FirmwareTestDevice, mock_client: Mock
    ) -> None:
        """Test check_firmware_updates fetches again when cache expired."""
        # Mock API response
        api_check = _create_firmware_check(v1=13, v2=0, last_v1=14, last_v2=0, info_url=None)
        mock_client.api.firmware.check_firmware_updates = AsyncMock(return_value=api_check)

        # First call
        await test_device.check_firmware_updates()

        # Manually expire cache
        test_device._firmware_update_cache_time = datetime.now() - timedelta(hours=25)

        # Second call - should hit API again due to expired cache
        await test_device.check_firmware_updates()

        # API should be called twice
        assert mock_client.api.firmware.check_firmware_updates.call_count == 2


class TestStartFirmwareUpdate:
    """Tests for start_firmware_update() method."""

    @pytest.mark.asyncio
    async def test_start_firmware_update_calls_api(
        self, test_device: FirmwareTestDevice, mock_client: Mock
    ) -> None:
        """Test start_firmware_update calls firmware API."""
        mock_client.api.firmware.start_firmware_update = AsyncMock(return_value=True)

        result = await test_device.start_firmware_update()

        mock_client.api.firmware.start_firmware_update.assert_called_once_with(
            "1234567890", try_fast_mode=False
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_start_firmware_update_with_fast_mode(
        self, test_device: FirmwareTestDevice, mock_client: Mock
    ) -> None:
        """Test start_firmware_update with try_fast_mode=True."""
        mock_client.api.firmware.start_firmware_update = AsyncMock(return_value=True)

        result = await test_device.start_firmware_update(try_fast_mode=True)

        mock_client.api.firmware.start_firmware_update.assert_called_once_with(
            "1234567890", try_fast_mode=True
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_start_firmware_update_returns_false_on_failure(
        self, test_device: FirmwareTestDevice, mock_client: Mock
    ) -> None:
        """Test start_firmware_update returns False when API returns False."""
        mock_client.api.firmware.start_firmware_update = AsyncMock(return_value=False)

        result = await test_device.start_firmware_update()

        assert result is False


class TestCheckUpdateEligibility:
    """Tests for check_update_eligibility() method."""

    @pytest.mark.asyncio
    async def test_check_update_eligibility_calls_api(
        self, test_device: FirmwareTestDevice, mock_client: Mock
    ) -> None:
        """Test check_update_eligibility calls firmware API."""
        mock_eligibility = UpdateEligibilityStatus(
            success=True, msg=UpdateEligibilityMessage.ALLOW_TO_UPDATE
        )
        mock_client.api.firmware.check_update_eligibility = AsyncMock(return_value=mock_eligibility)

        result = await test_device.check_update_eligibility()

        mock_client.api.firmware.check_update_eligibility.assert_called_once_with("1234567890")
        assert result is True

    @pytest.mark.asyncio
    async def test_check_update_eligibility_returns_false_when_not_allowed(
        self, test_device: FirmwareTestDevice, mock_client: Mock
    ) -> None:
        """Test check_update_eligibility returns False when not allowed."""
        mock_eligibility = UpdateEligibilityStatus(
            success=True, msg=UpdateEligibilityMessage.DEVICE_UPDATING
        )
        mock_client.api.firmware.check_update_eligibility = AsyncMock(return_value=mock_eligibility)

        result = await test_device.check_update_eligibility()

        assert result is False


class TestFirmwareUpdateWorkflow:
    """Integration tests for complete firmware update workflow."""

    @pytest.mark.asyncio
    async def test_complete_firmware_update_workflow(
        self, test_device: FirmwareTestDevice, mock_client: Mock
    ) -> None:
        """Test complete firmware update workflow."""
        # Setup mocks
        api_check = _create_firmware_check(v1=13, v2=0, last_v1=14, last_v2=0, info_url=None)
        mock_client.api.firmware.check_firmware_updates = AsyncMock(return_value=api_check)
        mock_client.api.firmware.check_update_eligibility = AsyncMock(
            return_value=UpdateEligibilityStatus(
                success=True, msg=UpdateEligibilityMessage.ALLOW_TO_UPDATE
            )
        )
        mock_client.api.firmware.start_firmware_update = AsyncMock(return_value=True)

        # 1. Check for updates
        update_info = await test_device.check_firmware_updates()
        assert update_info.update_available is True

        # 2. Access cached property
        assert test_device.firmware_update_available is True

        # 3. Check eligibility
        eligible = await test_device.check_update_eligibility()
        assert eligible is True

        # 4. Start update
        started = await test_device.start_firmware_update()
        assert started is True

    @pytest.mark.asyncio
    async def test_workflow_when_no_update_available(
        self, test_device: FirmwareTestDevice, mock_client: Mock
    ) -> None:
        """Test workflow when no update is available."""
        # Setup mocks
        api_check = _create_firmware_check(v1=14, v2=0, last_v1=14, last_v2=0, info_url=None)
        mock_client.api.firmware.check_firmware_updates = AsyncMock(return_value=api_check)

        # Check for updates
        update_info = await test_device.check_firmware_updates()
        assert update_info.update_available is False

        # Cached property should reflect this
        assert test_device.firmware_update_available is False
