"""Unit tests for firmware endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb.endpoints.firmware import FIRMWARE_UP_TO_DATE_MESSAGES, FirmwareEndpoints
from pylxpweb.exceptions import LuxpowerAPIError
from pylxpweb.models import (
    FirmwareUpdateCheck,
)


@pytest.fixture
def mock_client() -> Mock:
    """Create mock LuxpowerClient."""
    client = Mock()
    client._ensure_authenticated = AsyncMock()
    client._request = AsyncMock()
    client._user_id = 12345
    return client


@pytest.fixture
def firmware_endpoints(mock_client: Mock) -> FirmwareEndpoints:
    """Create FirmwareEndpoints instance with mock client."""
    return FirmwareEndpoints(mock_client)


def _create_firmware_check_response(
    serial_num: str = "1234567890",
    v1: int = 33,
    v2: int = 34,
    last_v1: int | None = 37,
    last_v2: int | None = 37,
) -> dict:
    """Create a firmware check API response."""
    return {
        "success": True,
        "details": {
            "serialNum": serial_num,
            "deviceType": 6,
            "standard": "fAAB",
            "firmwareType": "PCS",
            "fwCodeBeforeUpload": f"fAAB-{v1:02X}{v2:02X}",
            "v1": v1,
            "v2": v2,
            "v3Value": 0,
            "lastV1": last_v1,
            "lastV1FileName": f"FAAB-{last_v1:02X}xx_App.hex" if last_v1 else None,
            "lastV2": last_v2,
            "lastV2FileName": f"fAAB-xx{last_v2:02X}_Para.hex" if last_v2 else None,
            "m3Version": 33,
            "pcs1UpdateMatch": last_v1 is not None and v1 < last_v1,
            "pcs2UpdateMatch": last_v2 is not None and v2 < last_v2,
            "pcs3UpdateMatch": False,
            "needRunStep2": False,
            "needRunStep3": False,
            "needRunStep4": False,
            "needRunStep5": False,
            "midbox": False,
            "lowVoltBattery": True,
            "type6": True,
        },
        "infoForwardUrl": "https://example.com/release-notes",
    }


class TestCheckFirmwareUpdates:
    """Tests for check_firmware_updates endpoint."""

    @pytest.mark.asyncio
    async def test_check_firmware_updates_with_update_available(
        self, firmware_endpoints: FirmwareEndpoints, mock_client: Mock
    ) -> None:
        """Test check_firmware_updates when update is available."""
        response = _create_firmware_check_response(v1=33, v2=34, last_v1=37, last_v2=37)
        mock_client._request.return_value = response

        result = await firmware_endpoints.check_firmware_updates("1234567890")

        mock_client._ensure_authenticated.assert_called_once()
        mock_client._request.assert_called_once_with(
            "POST",
            "/WManage/web/maintain/standardUpdate/checkUpdates",
            data={"serialNum": "1234567890"},
        )

        assert isinstance(result, FirmwareUpdateCheck)
        assert result.success is True
        assert result.details.has_update is True
        assert result.details.v1 == 33
        assert result.details.lastV1 == 37

    @pytest.mark.asyncio
    async def test_check_firmware_updates_no_update_available(
        self, firmware_endpoints: FirmwareEndpoints, mock_client: Mock
    ) -> None:
        """Test check_firmware_updates when no update available (same version)."""
        response = _create_firmware_check_response(v1=37, v2=37, last_v1=37, last_v2=37)
        mock_client._request.return_value = response

        result = await firmware_endpoints.check_firmware_updates("1234567890")

        assert isinstance(result, FirmwareUpdateCheck)
        assert result.success is True
        assert result.details.has_update is False

    @pytest.mark.asyncio
    async def test_check_firmware_updates_already_latest_version(
        self, firmware_endpoints: FirmwareEndpoints, mock_client: Mock
    ) -> None:
        """Test check_firmware_updates handles 'already the latest version' message gracefully.

        The API returns success=false with a message when firmware is already up to date.
        This should NOT raise an exception - it should return a FirmwareUpdateCheck
        indicating no update is available.
        """
        # Mock the API raising an error with the "already latest" message
        mock_client._request.side_effect = LuxpowerAPIError(
            "API error (HTTP 200): The current machine firmware is already the latest version."
        )

        result = await firmware_endpoints.check_firmware_updates("1234567890")

        # Should return a valid result, not raise an exception
        assert isinstance(result, FirmwareUpdateCheck)
        assert result.success is True
        assert result.details.has_update is False
        assert result.details.serialNum == "1234567890"
        assert result.details.lastV1 is None
        assert result.details.lastV2 is None

    @pytest.mark.asyncio
    async def test_check_firmware_updates_already_latest_version_case_insensitive(
        self, firmware_endpoints: FirmwareEndpoints, mock_client: Mock
    ) -> None:
        """Test that 'already latest' detection is case-insensitive."""
        # Test with uppercase message
        mock_client._request.side_effect = LuxpowerAPIError(
            "API error (HTTP 200): THE CURRENT MACHINE FIRMWARE IS ALREADY THE LATEST VERSION."
        )

        result = await firmware_endpoints.check_firmware_updates("1234567890")

        assert isinstance(result, FirmwareUpdateCheck)
        assert result.success is True
        assert result.details.has_update is False

    @pytest.mark.asyncio
    async def test_check_firmware_updates_real_error_is_raised(
        self, firmware_endpoints: FirmwareEndpoints, mock_client: Mock
    ) -> None:
        """Test that real API errors (not 'already latest') are still raised."""
        mock_client._request.side_effect = LuxpowerAPIError(
            "API error (HTTP 200): Device not found."
        )

        with pytest.raises(LuxpowerAPIError) as exc_info:
            await firmware_endpoints.check_firmware_updates("1234567890")

        assert "Device not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_check_firmware_updates_connection_error_is_raised(
        self, firmware_endpoints: FirmwareEndpoints, mock_client: Mock
    ) -> None:
        """Test that connection errors are still raised."""
        from pylxpweb.exceptions import LuxpowerConnectionError

        mock_client._request.side_effect = LuxpowerConnectionError("Connection failed")

        with pytest.raises(LuxpowerConnectionError):
            await firmware_endpoints.check_firmware_updates("1234567890")


class TestFirmwareUpToDateMessages:
    """Tests for FIRMWARE_UP_TO_DATE_MESSAGES constant."""

    def test_firmware_up_to_date_messages_defined(self) -> None:
        """Test that FIRMWARE_UP_TO_DATE_MESSAGES is properly defined."""
        assert isinstance(FIRMWARE_UP_TO_DATE_MESSAGES, tuple)
        assert len(FIRMWARE_UP_TO_DATE_MESSAGES) > 0
        assert "already the latest version" in FIRMWARE_UP_TO_DATE_MESSAGES

    @pytest.mark.parametrize(
        "message",
        [
            "The current machine firmware is already the latest version.",
            "Device firmware is already the latest version",
            "Firmware is already up to date",
            "This device is already up to date.",
        ],
    )
    def test_various_already_latest_message_formats(self, message: str) -> None:
        """Test that various message formats are detected as 'already latest'."""
        message_lower = message.lower()
        is_up_to_date = any(msg in message_lower for msg in FIRMWARE_UP_TO_DATE_MESSAGES)
        assert is_up_to_date, f"Message '{message}' should be detected as 'already up to date'"


class TestFirmwareUpdateCheckCreateUpToDate:
    """Tests for FirmwareUpdateCheck.create_up_to_date class method."""

    def test_create_up_to_date_returns_valid_object(self) -> None:
        """Test that create_up_to_date returns a valid FirmwareUpdateCheck."""
        result = FirmwareUpdateCheck.create_up_to_date("1234567890")

        assert isinstance(result, FirmwareUpdateCheck)
        assert result.success is True
        assert result.details.serialNum == "1234567890"
        assert result.infoForwardUrl is None

    def test_create_up_to_date_has_no_update_available(self) -> None:
        """Test that create_up_to_date indicates no update available."""
        result = FirmwareUpdateCheck.create_up_to_date("1234567890")

        assert result.details.has_update is False
        assert result.details.has_app_update is False
        assert result.details.has_parameter_update is False

    def test_create_up_to_date_has_no_latest_versions(self) -> None:
        """Test that create_up_to_date has no latest version info."""
        result = FirmwareUpdateCheck.create_up_to_date("1234567890")

        assert result.details.lastV1 is None
        assert result.details.lastV2 is None
        assert result.details.lastV1FileName is None
        assert result.details.lastV2FileName is None

    def test_create_up_to_date_has_zero_current_versions(self) -> None:
        """Test that create_up_to_date has zero current versions (unknown)."""
        result = FirmwareUpdateCheck.create_up_to_date("1234567890")

        # Current versions are unknown when API returns "already latest"
        assert result.details.v1 == 0
        assert result.details.v2 == 0
        assert result.details.v3Value == 0

    def test_create_up_to_date_has_no_update_match_flags(self) -> None:
        """Test that create_up_to_date has no update match flags set."""
        result = FirmwareUpdateCheck.create_up_to_date("1234567890")

        assert result.details.pcs1UpdateMatch is False
        assert result.details.pcs2UpdateMatch is False
        assert result.details.pcs3UpdateMatch is False
