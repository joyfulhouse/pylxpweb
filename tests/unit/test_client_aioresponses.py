"""Unit tests for LuxpowerClient using aioresponses for HTTP mocking.

This approach is faster and more reliable than using TestServer.
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest
from aioresponses import aioresponses

from pylxpweb import LuxpowerClient
from pylxpweb.exceptions import LuxpowerConnectionError

# Import fixtures

# Base URL for all tests
BASE_URL = "https://monitor.eg4electronics.com"


class TestAuthentication:
    """Test authentication functionality."""

    @pytest.mark.asyncio
    async def test_login_success(
        self,
        mocked_api: aioresponses,
        login_response: dict[str, Any],
        plants_response: dict[str, Any],
    ) -> None:
        """Test successful login."""
        # Mock the API endpoint
        mocked_api.post(
            f"{BASE_URL}/WManage/api/login",
            payload=login_response,
        )

        # Mock account level detection calls
        mocked_api.post(
            f"{BASE_URL}/WManage/web/config/plant/list/viewer",
            payload=plants_response,
        )
        mocked_api.post(
            f"{BASE_URL}/WManage/api/inverterOverview/list",
            payload={
                "success": True,
                "total": 1,
                "rows": [{"serialNum": "1234567890", "endUser": "owner"}],
            },
        )

        # Test the client
        client = LuxpowerClient("testuser", "testpass")
        response = await client.login()

        assert response.success is True
        assert response.username == "testuser"
        assert response.userId == 99999
        assert len(response.plants) > 0

        await client.close()

    @pytest.mark.asyncio
    async def test_login_failure(self, mocked_api: aioresponses) -> None:
        """Test login with invalid credentials.

        Note: The EG4 API returns HTTP 200 with success=false for auth failures,
        not HTTP 401. A 401 response indicates session expiration, which triggers
        re-authentication retry logic. Invalid credentials are reported as API errors.
        """
        from pylxpweb.exceptions import LuxpowerAPIError

        # Mock failed login - API returns 200 with success=false for invalid credentials
        mocked_api.post(
            f"{BASE_URL}/WManage/api/login",
            payload={"success": False, "message": "Invalid credentials"},
            status=200,
        )

        client = LuxpowerClient("wronguser", "wrongpass")

        with pytest.raises(LuxpowerAPIError, match="Invalid credentials"):
            await client.login()

        await client.close()

    @pytest.mark.asyncio
    async def test_context_manager(
        self,
        mocked_api: aioresponses,
        login_response: dict[str, Any],
        plants_response: dict[str, Any],
    ) -> None:
        """Test client as async context manager."""
        mocked_api.post(
            f"{BASE_URL}/WManage/api/login",
            payload=login_response,
        )

        # Mock account level detection calls
        mocked_api.post(
            f"{BASE_URL}/WManage/web/config/plant/list/viewer",
            payload=plants_response,
        )
        mocked_api.post(
            f"{BASE_URL}/WManage/api/inverterOverview/list",
            payload={
                "success": True,
                "total": 1,
                "rows": [{"serialNum": "1234567890", "endUser": "owner"}],
            },
        )

        async with LuxpowerClient("testuser", "testpass") as client:
            assert client._session_expires is not None


class TestPlantDiscovery:
    """Test plant/station discovery."""

    @pytest.mark.asyncio
    async def test_get_plants(
        self,
        mocked_api: aioresponses,
        login_response: dict[str, Any],
        plants_response: dict[str, Any],
    ) -> None:
        """Test getting list of plants."""
        # Mock login
        mocked_api.post(
            f"{BASE_URL}/WManage/api/login",
            payload=login_response,
        )

        # Mock account level detection calls (called during login)
        mocked_api.post(
            f"{BASE_URL}/WManage/web/config/plant/list/viewer",
            payload=plants_response,
        )
        mocked_api.post(
            f"{BASE_URL}/WManage/api/inverterOverview/list",
            payload={
                "success": True,
                "total": 1,
                "rows": [{"serialNum": "1234567890", "endUser": "owner"}],
            },
        )

        # Mock plants list (called by test explicitly)
        mocked_api.post(
            f"{BASE_URL}/WManage/web/config/plant/list/viewer",
            payload=plants_response,
        )

        async with LuxpowerClient("testuser", "testpass") as client:
            response = await client.api.plants.get_plants()
            assert response.total == 1
            assert len(response.rows) == 1
            plant = response.rows[0]
            assert plant.plantId == 99999
            assert plant.name == "Example Solar Station"


class TestDeviceDiscovery:
    """Test device discovery."""

    @pytest.mark.asyncio
    async def test_get_devices(
        self,
        mocked_api: aioresponses,
        login_response: dict[str, Any],
    ) -> None:
        """Test getting device list."""
        # Mock login
        mocked_api.post(f"{BASE_URL}/WManage/api/login", payload=login_response)

        # Mock devices list
        devices_response = {
            "success": True,
            "total": 3,
            "rows": [
                {
                    "serialNum": "1111111111",
                    "statusText": "normal",
                    "deviceType": 6,
                    "deviceTypeText": "18KPV",
                    "phase": 1,
                    "plantId": 99999,
                    "plantName": "Test Plant",
                    "ppv": 2500,
                    "ppvText": "2.5 kW",
                    "pCharge": 0,
                    "pChargeText": "0 W",
                    "pDisCharge": 1500,
                    "pDisChargeText": "1.5 kW",
                    "pConsumption": 3000,
                    "pConsumptionText": "3 kW",
                    "soc": "71 %",
                    "vBat": 523,
                    "vBatText": "52.3 V",
                    "totalYielding": 15000,
                    "totalYieldingText": "1500.0 kWh",
                    "totalDischarging": 28000,
                    "totalDischargingText": "2800.0 kWh",
                    "totalExport": 62000,
                    "totalExportText": "6200.0 kWh",
                    "totalUsage": 37000,
                    "totalUsageText": "3700.0 kWh",
                    "parallelGroup": "A",
                    "parallelIndex": "1",
                    "parallelInfo": "A1, Parallel",
                    "parallelModel": "PARALLEL",
                },
                {
                    "serialNum": "2222222222",
                    "statusText": "normal",
                    "deviceType": 6,
                    "deviceTypeText": "18KPV",
                    "phase": 1,
                    "plantId": 99999,
                    "plantName": "Test Plant",
                    "ppv": 2600,
                    "ppvText": "2.6 kW",
                    "pCharge": 0,
                    "pChargeText": "0 W",
                    "pDisCharge": 1600,
                    "pDisChargeText": "1.6 kW",
                    "pConsumption": 3100,
                    "pConsumptionText": "3.1 kW",
                    "soc": "72 %",
                    "vBat": 524,
                    "vBatText": "52.4 V",
                    "totalYielding": 15100,
                    "totalYieldingText": "1510.0 kWh",
                    "totalDischarging": 28100,
                    "totalDischargingText": "2810.0 kWh",
                    "totalExport": 62100,
                    "totalExportText": "6210.0 kWh",
                    "totalUsage": 37100,
                    "totalUsageText": "3710.0 kWh",
                    "parallelGroup": "A",
                    "parallelIndex": "2",
                    "parallelInfo": "A2, Parallel",
                    "parallelModel": "PARALLEL",
                },
                {
                    "serialNum": "3333333333",
                    "statusText": "normal",
                    "deviceType": 9,
                    "deviceTypeText": "Grid Boss",
                    "phase": 1,
                    "plantId": 99999,
                    "plantName": "Test Plant",
                    "ppv": 0,
                    "ppvText": "",
                    "pCharge": 0,
                    "pChargeText": "",
                    "pDisCharge": 0,
                    "pDisChargeText": "",
                    "pConsumption": 0,
                    "pConsumptionText": "",
                    "soc": "",
                    "vBat": 0,
                    "vBatText": "",
                    "totalYielding": 0,
                    "totalYieldingText": "0 kWh",
                    "totalDischarging": 0,
                    "totalDischargingText": "0 kWh",
                    "totalExport": 0,
                    "totalExportText": "0 kWh",
                    "totalUsage": 0,
                    "totalUsageText": "0 kWh",
                    "parallelGroup": "A",
                    "parallelIndex": "3",
                    "parallelInfo": "A3, Parallel",
                    "parallelModel": "PARALLEL",
                },
            ],
        }
        mocked_api.post(
            f"{BASE_URL}/WManage/api/inverterOverview/list",
            payload=devices_response,
        )

        async with LuxpowerClient("testuser", "testpass") as client:
            response = await client.api.devices.get_devices(99999)
            assert response.success is True
            assert len(response.rows) == 3  # 2 inverters + 1 GridBOSS


class TestRuntimeData:
    """Test runtime data retrieval."""

    @pytest.mark.asyncio
    async def test_get_inverter_runtime(
        self,
        mocked_api: aioresponses,
        login_response: dict[str, Any],
        runtime_response: dict[str, Any],
    ) -> None:
        """Test getting inverter runtime data."""
        # Mock login
        mocked_api.post(f"{BASE_URL}/WManage/api/login", payload=login_response)

        # Mock runtime data
        mocked_api.post(
            f"{BASE_URL}/WManage/api/inverter/getInverterRuntime",
            payload=runtime_response,
        )

        async with LuxpowerClient("testuser", "testpass") as client:
            response = await client.api.devices.get_inverter_runtime("1234567890")
            assert response.success is True
            assert response.serialNum == "1234567890"
            assert response.soc == 71
            assert response.ppv == 0  # PV power
            assert response.pToUser == 1030  # Power to user

    @pytest.mark.asyncio
    async def test_get_inverter_energy(
        self,
        mocked_api: aioresponses,
        login_response: dict[str, Any],
        energy_response: dict[str, Any],
    ) -> None:
        """Test getting inverter energy statistics."""
        # Mock login
        mocked_api.post(f"{BASE_URL}/WManage/api/login", payload=login_response)

        # Mock energy data
        mocked_api.post(
            f"{BASE_URL}/WManage/api/inverter/getInverterEnergyInfo",
            payload=energy_response,
        )

        async with LuxpowerClient("testuser", "testpass") as client:
            response = await client.api.devices.get_inverter_energy("1234567890")
            assert response.success is True
            assert response.serialNum == "1234567890"
            assert response.soc == 71

    @pytest.mark.asyncio
    async def test_get_battery_info(
        self,
        mocked_api: aioresponses,
        login_response: dict[str, Any],
        battery_response: dict[str, Any],
    ) -> None:
        """Test getting battery information."""
        # Mock login
        mocked_api.post(f"{BASE_URL}/WManage/api/login", payload=login_response)

        # Mock battery info
        mocked_api.post(
            f"{BASE_URL}/WManage/api/battery/getBatteryInfo",
            payload=battery_response,
        )

        async with LuxpowerClient("testuser", "testpass") as client:
            response = await client.api.devices.get_battery_info("1234567890")
            assert response.success is True
            assert response.serialNum == "1234567890"
            assert response.soc == 71
            assert len(response.batteryArray) > 0


class TestCaching:
    """Test response caching functionality."""

    @pytest.mark.asyncio
    async def test_runtime_data_caching(
        self,
        mocked_api: aioresponses,
        login_response: dict[str, Any],
        runtime_response: dict[str, Any],
    ) -> None:
        """Test that runtime data is cached appropriately."""
        # Mock login
        mocked_api.post(f"{BASE_URL}/WManage/api/login", payload=login_response)

        # Mock runtime data (only once - cache will be used for second call)
        mocked_api.post(
            f"{BASE_URL}/WManage/api/inverter/getInverterRuntime",
            payload=runtime_response,
        )

        async with LuxpowerClient("testuser", "testpass") as client:
            # First call
            response1 = await client.api.devices.get_inverter_runtime("1234567890")

            # Second call should use cache
            response2 = await client.api.devices.get_inverter_runtime("1234567890")

            assert response1.soc == response2.soc
            assert response1.serverTime == response2.serverTime


class TestErrorHandling:
    """Test error handling and retry logic."""

    @pytest.mark.asyncio
    async def test_backoff_on_error(
        self,
        mocked_api: aioresponses,
    ) -> None:
        """Test that backoff is applied on network/connection errors.

        Note: Backoff is applied for network errors (connection refused, timeout),
        not for API errors (success=false). This is intentional - backoff helps
        with transient network issues, not with logical API errors.
        """
        import aiohttp

        # Mock a network error (connection refused) on login
        mocked_api.post(
            f"{BASE_URL}/WManage/api/login",
            exception=aiohttp.ClientConnectionError("Connection refused"),
        )

        client = LuxpowerClient("testuser", "testpass")

        try:
            # Initial state
            assert client._consecutive_errors == 0
            assert client._current_backoff_delay == 0.0

            # Try to login - will fail with connection error
            with contextlib.suppress(LuxpowerConnectionError):
                await client.login()

            # Verify backoff was increased due to connection errors
            assert client._consecutive_errors >= 1
            assert client._current_backoff_delay > 0

        finally:
            await client.close()


class TestSessionManagement:
    """Test session management."""

    @pytest.mark.asyncio
    async def test_session_creation(
        self,
        mocked_api: aioresponses,
        login_response: dict[str, Any],
    ) -> None:
        """Test that client creates its own session."""
        # Mock login
        mocked_api.post(f"{BASE_URL}/WManage/api/login", payload=login_response)

        client = LuxpowerClient("testuser", "testpass")

        try:
            assert client._session is None
            assert client._owns_session is True

            await client.login()

            assert client._session is not None
            assert client._owns_session is True
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_session_injection(
        self,
        mocked_api: aioresponses,
        login_response: dict[str, Any],
    ) -> None:
        """Test that client can use injected session."""
        import aiohttp

        # Mock login
        mocked_api.post(f"{BASE_URL}/WManage/api/login", payload=login_response)

        async with aiohttp.ClientSession() as session:
            client = LuxpowerClient("testuser", "testpass", session=session)

            try:
                assert client._session is session
                assert client._owns_session is False

                await client.login()

                # Session should still be the injected one
                assert client._session is session
            finally:
                await client.close()

            # Injected session should not be closed
            assert not session.closed


class TestErrorHandlingExtended:
    """Extended error handling tests for better coverage."""

    @pytest.mark.asyncio
    async def test_login_with_missing_fields(
        self,
        mocked_api: aioresponses,
    ) -> None:
        """Test login response with missing required fields."""
        from pydantic import ValidationError

        # Mock incomplete login response
        mocked_api.post(
            f"{BASE_URL}/WManage/api/login",
            payload={"success": True},  # Missing all user data
            status=200,
        )

        client = LuxpowerClient("testuser", "testpass")
        try:
            # Should raise validation error
            with pytest.raises(ValidationError):
                await client.login()
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_request_with_network_error(
        self,
        mocked_api: aioresponses,
        login_response: dict[str, Any],
    ) -> None:
        """Test handling of network errors."""
        import aiohttp

        mocked_api.post(f"{BASE_URL}/WManage/api/login", payload=login_response)
        mocked_api.post(
            f"{BASE_URL}/WManage/api/plantOverview/list/viewer",
            exception=aiohttp.ClientConnectorError(
                connection_key=None, os_error=OSError("Connection refused")
            ),
        )

        async with LuxpowerClient("testuser", "testpass") as client:
            with pytest.raises(LuxpowerConnectionError):
                await client.api.plants.get_plants()

    @pytest.mark.asyncio
    async def test_cache_invalidation(
        self,
        mocked_api: aioresponses,
        login_response: dict[str, Any],
        runtime_response: dict[str, Any],
    ) -> None:
        """Test cache TTL behavior."""
        import asyncio
        from datetime import timedelta

        mocked_api.post(f"{BASE_URL}/WManage/api/login", payload=login_response)
        # Mock runtime endpoint twice
        mocked_api.post(
            f"{BASE_URL}/WManage/api/inverter/getInverterRuntime",
            payload=runtime_response,
        )
        mocked_api.post(
            f"{BASE_URL}/WManage/api/inverter/getInverterRuntime",
            payload={**runtime_response, "soc": 75},  # Different value
        )

        async with LuxpowerClient("testuser", "testpass") as client:
            # Reduce cache TTL for testing
            client._cache_ttl_config["inverter_runtime"] = timedelta(milliseconds=100)

            # First call - cache miss
            result1 = await client.api.devices.get_inverter_runtime("1234567890")
            assert result1.soc == 71

            # Second call - cache hit
            result2 = await client.api.devices.get_inverter_runtime("1234567890")
            assert result2.soc == 71  # Same as cached

            # Wait for cache to expire
            await asyncio.sleep(0.15)

            # Third call - cache miss (expired)
            result3 = await client.api.devices.get_inverter_runtime("1234567890")
            assert result3.soc == 75  # New value
