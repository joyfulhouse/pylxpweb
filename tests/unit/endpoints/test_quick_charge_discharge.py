"""Unit tests for quick charge/discharge endpoints."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from aioresponses import aioresponses

from pylxpweb import LuxpowerClient
from pylxpweb.endpoints.control import ControlEndpoints
from pylxpweb.models import QuickChargeStatus, SuccessResponse

# Base URL for all tests
BASE_URL = "https://monitor.eg4electronics.com"


@pytest.fixture
def mock_client() -> Mock:
    """Create a mocked LuxpowerClient with an async _request."""
    client = Mock(spec=LuxpowerClient)
    client._request = AsyncMock(return_value={"success": True})
    client._ensure_authenticated = AsyncMock()
    return client


class TestQuickChargeEndpoints:
    """Test quick charge control endpoints."""

    @pytest.mark.asyncio
    async def test_start_quick_charge(
        self, mocked_api: aioresponses, login_response: dict[str, Any]
    ):
        """Test starting quick charge operation."""
        # Mock login
        mocked_api.post(f"{BASE_URL}/WManage/api/login", payload=login_response)

        # Mock start quick charge
        mocked_api.post(
            f"{BASE_URL}/WManage/web/config/quickCharge/start",
            payload={"success": True, "msg": ""},
        )

        client = LuxpowerClient("testuser", "testpass")
        async with client:
            result = await client.api.control.start_quick_charge("1234567890")

            assert isinstance(result, SuccessResponse)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_stop_quick_charge(
        self, mocked_api: aioresponses, login_response: dict[str, Any]
    ):
        """Test stopping quick charge operation."""
        # Mock login
        mocked_api.post(f"{BASE_URL}/WManage/api/login", payload=login_response)

        # Mock stop quick charge - success case
        mocked_api.post(
            f"{BASE_URL}/WManage/web/config/quickCharge/stop",
            payload={"success": True, "msg": ""},
        )

        client = LuxpowerClient("testuser", "testpass")
        async with client:
            result = await client.api.control.stop_quick_charge("1234567890")

            assert isinstance(result, SuccessResponse)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_get_quick_charge_status(
        self, mocked_api: aioresponses, login_response: dict[str, Any]
    ):
        """Test getting quick charge status."""
        # Mock login
        mocked_api.post(f"{BASE_URL}/WManage/api/login", payload=login_response)

        # Mock get status
        mocked_api.post(
            f"{BASE_URL}/WManage/web/config/quickCharge/getStatusInfo",
            payload={
                "success": True,
                "hasUnclosedQuickChargeTask": False,
                "hasUnclosedQuickDischargeTask": False,
            },
        )

        client = LuxpowerClient("testuser", "testpass")
        async with client:
            result = await client.api.control.get_quick_charge_status("1234567890")

            assert isinstance(result, QuickChargeStatus)
            assert result.success is True
            assert result.hasUnclosedQuickChargeTask is False
            assert result.hasUnclosedQuickDischargeTask is False

    @pytest.mark.asyncio
    async def test_get_quick_charge_status_active(
        self, mocked_api: aioresponses, login_response: dict[str, Any]
    ):
        """Test getting quick charge status when active."""
        # Mock login
        mocked_api.post(f"{BASE_URL}/WManage/api/login", payload=login_response)

        # Mock get status - charge active
        mocked_api.post(
            f"{BASE_URL}/WManage/web/config/quickCharge/getStatusInfo",
            payload={
                "success": True,
                "hasUnclosedQuickChargeTask": True,
                "hasUnclosedQuickDischargeTask": False,
            },
        )

        client = LuxpowerClient("testuser", "testpass")
        async with client:
            result = await client.api.control.get_quick_charge_status("1234567890")

            assert result.hasUnclosedQuickChargeTask is True
            assert result.hasUnclosedQuickDischargeTask is False


class TestStartQuickChargeMinute:
    """Test the minute-based duration support on start_quick_charge."""

    @pytest.mark.asyncio
    async def test_start_quick_charge_with_minute_sends_minute(self, mock_client: Mock) -> None:
        """A provided minute is sent in the POST body."""
        control = ControlEndpoints(mock_client)

        result = await control.start_quick_charge("1234567890", minute=10)

        assert result.success is True
        call_data = mock_client._request.call_args[1]["data"]
        assert call_data["minute"] == 10
        assert call_data["inverterSn"] == "1234567890"

    @pytest.mark.asyncio
    async def test_start_quick_charge_without_minute_omits_minute(self, mock_client: Mock) -> None:
        """Omitting minute preserves the legacy body (no minute key)."""
        control = ControlEndpoints(mock_client)

        result = await control.start_quick_charge("1234567890")

        assert result.success is True
        call_data = mock_client._request.call_args[1]["data"]
        assert "minute" not in call_data

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_minute", [0, -1, -30])
    async def test_start_quick_charge_rejects_non_positive_minute(
        self, mock_client: Mock, bad_minute: int
    ) -> None:
        """A non-positive minute raises ValueError before any request."""
        control = ControlEndpoints(mock_client)

        with pytest.raises(ValueError, match="minute must be a positive integer"):
            await control.start_quick_charge("1234567890", minute=bad_minute)

        # Guard fires before any network/auth side effect.
        mock_client._request.assert_not_called()
        mock_client._ensure_authenticated.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_minute", [1.5, True, "10"])
    async def test_start_quick_charge_rejects_non_integer_minute(
        self, mock_client: Mock, bad_minute: Any
    ) -> None:
        """Non-integer minute (float/bool/str) raises ValueError before any request."""
        control = ControlEndpoints(mock_client)

        with pytest.raises(ValueError, match="minute must be a positive integer"):
            await control.start_quick_charge("1234567890", minute=bad_minute)

        mock_client._request.assert_not_called()
        mock_client._ensure_authenticated.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_quick_charge_invalidates_cache_on_success(self, mock_client: Mock) -> None:
        """A successful start invalidates the cached status for that device."""
        control = ControlEndpoints(mock_client)

        await control.start_quick_charge("1234567890", minute=10)

        mock_client.invalidate_cache_for_device.assert_called_once_with("1234567890")

    @pytest.mark.asyncio
    async def test_start_quick_charge_no_invalidate_on_failure(self, mock_client: Mock) -> None:
        """A failed start does not invalidate the cache."""
        mock_client._request = AsyncMock(return_value={"success": False})
        control = ControlEndpoints(mock_client)

        await control.start_quick_charge("1234567890", minute=10)

        mock_client.invalidate_cache_for_device.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_quick_charge_invalidates_cache_on_success(self, mock_client: Mock) -> None:
        """A successful stop invalidates the cached status for that device."""
        control = ControlEndpoints(mock_client)

        await control.stop_quick_charge("1234567890")

        mock_client.invalidate_cache_for_device.assert_called_once_with("1234567890")


class TestQuickDischargeEndpoints:
    """Test quick discharge control endpoints."""

    @pytest.mark.asyncio
    async def test_start_quick_discharge(
        self, mocked_api: aioresponses, login_response: dict[str, Any]
    ):
        """Test starting quick discharge operation."""
        # Mock login
        mocked_api.post(f"{BASE_URL}/WManage/api/login", payload=login_response)

        # Mock start quick discharge
        mocked_api.post(
            f"{BASE_URL}/WManage/web/config/quickDischarge/start",
            payload={"success": True, "msg": ""},
        )

        client = LuxpowerClient("testuser", "testpass")
        async with client:
            result = await client.api.control.start_quick_discharge("1234567890")

            assert isinstance(result, SuccessResponse)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_stop_quick_discharge(
        self, mocked_api: aioresponses, login_response: dict[str, Any]
    ):
        """Test stopping quick discharge operation."""
        # Mock login
        mocked_api.post(f"{BASE_URL}/WManage/api/login", payload=login_response)

        # Mock stop quick discharge
        mocked_api.post(
            f"{BASE_URL}/WManage/web/config/quickDischarge/stop",
            payload={"success": True, "msg": ""},
        )

        client = LuxpowerClient("testuser", "testpass")
        async with client:
            result = await client.api.control.stop_quick_discharge("1234567890")

            assert isinstance(result, SuccessResponse)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_get_quick_discharge_status_via_charge_endpoint(
        self, mocked_api: aioresponses, login_response: dict[str, Any]
    ):
        """Test getting quick discharge status via quickCharge/getStatusInfo endpoint."""
        # Mock login
        mocked_api.post(f"{BASE_URL}/WManage/api/login", payload=login_response)

        # Mock get status - discharge active
        mocked_api.post(
            f"{BASE_URL}/WManage/web/config/quickCharge/getStatusInfo",
            payload={
                "success": True,
                "hasUnclosedQuickChargeTask": False,
                "hasUnclosedQuickDischargeTask": True,
            },
        )

        client = LuxpowerClient("testuser", "testpass")
        async with client:
            result = await client.api.control.get_quick_charge_status("1234567890")

            # Verify the shared endpoint returns discharge status
            assert result.hasUnclosedQuickChargeTask is False
            assert result.hasUnclosedQuickDischargeTask is True


class TestQuickChargeStatusModel:
    """Test QuickChargeStatus model with both charge and discharge fields."""

    def test_model_with_both_fields(self):
        """Test model with both charge and discharge status."""
        status = QuickChargeStatus(
            success=True,
            hasUnclosedQuickChargeTask=True,
            hasUnclosedQuickDischargeTask=False,
        )

        assert status.success is True
        assert status.hasUnclosedQuickChargeTask is True
        assert status.hasUnclosedQuickDischargeTask is False

    def test_model_with_default_discharge_field(self):
        """Test model with discharge field defaulting to False."""
        status = QuickChargeStatus(
            success=True,
            hasUnclosedQuickChargeTask=False,
        )

        # Should default to False if not provided (for older API versions)
        assert status.hasUnclosedQuickDischargeTask is False

    def test_model_both_active(self):
        """Test model with both charge and discharge active (unlikely but valid)."""
        status = QuickChargeStatus(
            success=True,
            hasUnclosedQuickChargeTask=True,
            hasUnclosedQuickDischargeTask=True,
        )

        assert status.hasUnclosedQuickChargeTask is True
        assert status.hasUnclosedQuickDischargeTask is True

    def test_model_parses_rich_minute_fields(self):
        """New firmware fields parse from the API payload."""
        status = QuickChargeStatus.model_validate(
            {
                "success": True,
                "hasUnclosedQuickChargeTask": True,
                "hasUnclosedQuickDischargeTask": False,
                "remainTimeBeforeQuickChargeStop": 598,
                "unclosedQuickChargeTaskId": 42,
                "unclosedQuickChargeTaskStatus": "WAIT_CHARGE",
                "lowVoltProtect": True,
            }
        )

        assert status.remainTimeBeforeQuickChargeStop == 598
        assert status.unclosedQuickChargeTaskId == 42
        assert status.unclosedQuickChargeTaskStatus == "WAIT_CHARGE"
        assert status.lowVoltProtect is True

    def test_model_rich_fields_default_for_old_api(self):
        """Older API payloads (no minute fields) get safe defaults."""
        status = QuickChargeStatus(
            success=True,
            hasUnclosedQuickChargeTask=False,
        )

        assert status.remainTimeBeforeQuickChargeStop == 0
        assert status.unclosedQuickChargeTaskId is None
        assert status.unclosedQuickChargeTaskStatus is None
        assert status.lowVoltProtect is False

    @pytest.mark.parametrize(
        ("remain_seconds", "expected_minutes"),
        [(598, 10), (0, 0), (61, 2), (60, 1), (1, 1)],
    )
    def test_remaining_minutes_rounds_up(self, remain_seconds: int, expected_minutes: int) -> None:
        """remaining_minutes rounds seconds up to whole minutes."""
        status = QuickChargeStatus(
            success=True,
            hasUnclosedQuickChargeTask=True,
            remainTimeBeforeQuickChargeStop=remain_seconds,
        )

        assert status.remaining_minutes == expected_minutes
