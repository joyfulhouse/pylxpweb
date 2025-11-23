"""Unit tests for FirmwareUpdateInfo model."""

from __future__ import annotations

from pylxpweb.models import (
    FirmwareUpdateCheck,
    FirmwareUpdateDetails,
    FirmwareUpdateInfo,
)


def _create_firmware_details(
    fw_code: str = "IAAB",
    v1: int = 13,
    v2: int = 0,
    last_v1: int | None = None,
    last_v2: int | None = None,
) -> FirmwareUpdateDetails:
    """Helper to create FirmwareUpdateDetails for testing.

    Note: v1 and v2 are decimal values from API, but fwCodeBeforeUpload uses hex format.
    Example: v1=13, v2=0 → "IAAB-0D00" (13=0x0D, 0=0x00)
    """
    return FirmwareUpdateDetails.model_construct(
        serialNum="1234567890",
        deviceType=6,
        standard="",
        firmwareType="",
        fwCodeBeforeUpload=f"{fw_code}-{v1:02X}{v2:02X}",  # Hex format
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


def _create_firmware_check(
    fw_code: str = "IAAB",
    v1: int = 13,
    v2: int = 0,
    last_v1: int | None = None,
    last_v2: int | None = None,
    info_url: str | None = None,
) -> FirmwareUpdateCheck:
    """Helper to create FirmwareUpdateCheck for testing."""
    details = _create_firmware_details(fw_code, v1, v2, last_v1, last_v2)
    return FirmwareUpdateCheck(
        success=True,
        details=details,
        infoForwardUrl=info_url,
    )


class TestFirmwareUpdateInfoModel:
    """Tests for FirmwareUpdateInfo model."""

    def test_create_firmware_update_info_with_all_fields(self) -> None:
        """Test creating FirmwareUpdateInfo with all fields."""
        info = FirmwareUpdateInfo(
            installed_version="IAAB-1300",
            latest_version="IAAB-1400",
            title="Test Inverter Firmware",
            release_summary="Bug fixes and improvements",
            release_url="https://example.com/release-notes",
            in_progress=False,
            update_percentage=None,
            device_class="firmware",
            supported_features=["install", "progress", "release_notes"],
            app_version_current=13,
            app_version_latest=14,
            param_version_current=0,
            param_version_latest=0,
        )

        assert info.installed_version == "IAAB-1300"
        assert info.latest_version == "IAAB-1400"
        assert info.title == "Test Inverter Firmware"
        assert info.release_summary == "Bug fixes and improvements"
        assert info.release_url == "https://example.com/release-notes"
        assert info.in_progress is False
        assert info.update_percentage is None
        assert info.device_class == "firmware"
        assert info.supported_features == ["install", "progress", "release_notes"]
        assert info.app_version_current == 13
        assert info.app_version_latest == 14

    def test_create_firmware_update_info_minimal_fields(self) -> None:
        """Test creating FirmwareUpdateInfo with minimal required fields."""
        info = FirmwareUpdateInfo(
            installed_version="IAAB-1300",
            latest_version="IAAB-1300",
            title="Test Firmware",
        )

        assert info.installed_version == "IAAB-1300"
        assert info.latest_version == "IAAB-1300"
        assert info.title == "Test Firmware"
        assert info.release_summary is None
        assert info.release_url is None
        assert info.in_progress is False
        assert info.update_percentage is None
        assert info.device_class == "firmware"
        assert info.supported_features == []

    def test_update_available_property_when_update_exists(self) -> None:
        """Test update_available property returns True when update exists."""
        info = FirmwareUpdateInfo(
            installed_version="IAAB-1300",
            latest_version="IAAB-1400",
            title="Test Firmware",
        )

        assert info.update_available is True

    def test_update_available_property_when_up_to_date(self) -> None:
        """Test update_available property returns False when up to date."""
        info = FirmwareUpdateInfo(
            installed_version="IAAB-1300",
            latest_version="IAAB-1300",
            title="Test Firmware",
        )

        assert info.update_available is False


class TestFirmwareUpdateInfoFromAPIResponse:
    """Tests for FirmwareUpdateInfo.from_api_response() class method."""

    def test_from_api_response_with_update_available(self) -> None:
        """Test creating FirmwareUpdateInfo from API response with update."""
        api_check = _create_firmware_check(
            v1=13, v2=0, last_v1=14, last_v2=None, info_url="https://example.com/release"
        )

        info = FirmwareUpdateInfo.from_api_response(
            check=api_check,
            title="EG4 18kPV Firmware",
        )

        assert info.installed_version == "IAAB-0D00"  # v1=13(0x0D), v2=0(0x00)
        assert info.latest_version == "IAAB-0E00"  # v1=14(0x0E), v2=0(0x00)
        assert info.title == "EG4 18kPV Firmware"
        assert info.update_available is True
        assert info.release_url == "https://example.com/release"
        assert info.device_class == "firmware"
        assert "install" in info.supported_features
        assert "release_notes" in info.supported_features

    def test_from_api_response_no_update_available(self) -> None:
        """Test creating FirmwareUpdateInfo when no update available."""
        api_check = _create_firmware_check(v1=14, v2=0, last_v1=None, last_v2=None)

        info = FirmwareUpdateInfo.from_api_response(
            check=api_check,
            title="Test Firmware",
        )

        assert info.installed_version == "IAAB-0E00"  # v1=14(0x0E), v2=0(0x00)
        assert info.latest_version == "IAAB-0E00"
        assert info.update_available is False
        assert info.release_url is None

    def test_from_api_response_with_parameter_update(self) -> None:
        """Test creating FirmwareUpdateInfo with parameter update."""
        api_check = _create_firmware_check(v1=13, v2=5, last_v1=None, last_v2=6)

        info = FirmwareUpdateInfo.from_api_response(
            check=api_check,
            title="Test Firmware",
        )

        assert info.installed_version == "IAAB-0D05"  # v1=13(0x0D), v2=5(0x05)
        assert info.latest_version == "IAAB-0D06"  # v1=13(0x0D), v2=6(0x06)
        assert info.update_available is True
        assert info.app_version_current == 13
        assert info.app_version_latest is None
        assert info.param_version_current == 5
        assert info.param_version_latest == 6

    def test_from_api_response_with_both_updates(self) -> None:
        """Test creating FirmwareUpdateInfo with both app and param updates."""
        api_check = _create_firmware_check(
            v1=13, v2=5, last_v1=14, last_v2=6, info_url="https://example.com/changelog"
        )

        info = FirmwareUpdateInfo.from_api_response(
            check=api_check,
            title="Test Firmware",
        )

        assert info.installed_version == "IAAB-0D05"  # v1=13(0x0D), v2=5(0x05)
        assert info.latest_version == "IAAB-0E06"  # v1=14(0x0E), v2=6(0x06)
        assert info.update_available is True
        assert info.release_url == "https://example.com/changelog"

    def test_from_api_response_with_in_progress_flag(self) -> None:
        """Test creating FirmwareUpdateInfo with in_progress flag."""
        api_check = _create_firmware_check(v1=13, v2=0, last_v1=14, last_v2=None)

        info = FirmwareUpdateInfo.from_api_response(
            check=api_check,
            title="Test Firmware",
            in_progress=True,
            update_percentage=45,
        )

        assert info.in_progress is True
        assert info.update_percentage == 45
        assert "progress" in info.supported_features

    def test_from_api_response_generates_correct_features_list(self) -> None:
        """Test that from_api_response generates correct supported_features."""
        # With release URL
        api_check_with_url = _create_firmware_check(
            v1=13, v2=0, last_v1=14, last_v2=None, info_url="https://example.com/release"
        )

        info_with_url = FirmwareUpdateInfo.from_api_response(
            check=api_check_with_url,
            title="Test",
        )

        assert "install" in info_with_url.supported_features
        assert "release_notes" in info_with_url.supported_features

        # Without release URL
        api_check_no_url = _create_firmware_check(v1=13, v2=0, last_v1=14, last_v2=None)

        info_no_url = FirmwareUpdateInfo.from_api_response(
            check=api_check_no_url,
            title="Test",
        )

        assert "install" in info_no_url.supported_features
        assert "release_notes" not in info_no_url.supported_features

    def test_from_api_response_with_zero_versions(self) -> None:
        """Test from_api_response handles zero versions correctly."""
        api_check = _create_firmware_check(v1=0, v2=0, last_v1=None, last_v2=None)

        info = FirmwareUpdateInfo.from_api_response(
            check=api_check,
            title="Test Firmware",
        )

        assert info.installed_version == "IAAB-0000"  # v1=0(0x00), v2=0(0x00)
        assert info.latest_version == "IAAB-0000"
        assert info.update_available is False
