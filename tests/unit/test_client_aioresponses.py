"""Unit tests for LuxpowerClient using aioresponses for HTTP mocking.

This approach is faster and more reliable than using TestServer.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import aiohttp
import pytest
from aioresponses import aioresponses

from pylxpweb import LuxpowerClient
from pylxpweb.exceptions import LuxpowerConnectionError

# Import fixtures

# Base URL for all tests
BASE_URL = "https://monitor.eg4electronics.com"


class _ReactiveAuthResponse:
    """Minimal response context used to stage concurrent stale sessions."""

    def __init__(
        self,
        session: _ConcurrentReactiveSession,
        *,
        stale: bool,
        stale_index: int | None,
    ) -> None:
        self._session = session
        self._stale = stale
        self._stale_index = stale_index
        self.status = 401 if stale and session.response_kind == "401" else 200

    async def __aenter__(self) -> _ReactiveAuthResponse:
        if self._stale:
            self._session.stale_requests_started += 1
            if self._session.stale_requests_started == self._session.expected_stale_requests:
                self._session.all_stale_requests_started.set()

            await self._session.all_stale_requests_started.wait()
            if self._stale_index is not None and self._stale_index >= self._session.early_count:
                await self._session.release_late_stale_responses.wait()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        return None

    def raise_for_status(self) -> None:
        if self._stale and self._session.response_kind == "401":
            raise aiohttp.ClientResponseError(
                SimpleNamespace(real_url="https://example.test/stale"),
                (),
                status=401,
                message="expired session",
            )

    async def json(self) -> dict[str, Any]:
        if self._stale:
            if self._session.response_kind == "html":
                raise aiohttp.ContentTypeError(
                    SimpleNamespace(real_url="https://example.test/stale"),
                    (),
                    status=200,
                    message="unexpected text/html response",
                )
            raise AssertionError("401 response should fail before JSON decoding")

        return {
            "success": True,
            "cookie_generation": self._session.cookie_generation,
        }


class _ConcurrentReactiveSession:
    """Injected session whose initial requests all use one stale cookie."""

    def __init__(
        self,
        response_kind: str,
        *,
        expected_stale_requests: int,
        early_count: int,
    ) -> None:
        self.response_kind = response_kind
        self.expected_stale_requests = expected_stale_requests
        self.early_count = early_count
        self.closed = False
        self.cookie_generation = 0
        self.cookie_mutations = 0
        self.stale_requests_started = 0
        self.all_stale_requests_started = asyncio.Event()
        self.release_late_stale_responses = asyncio.Event()

    def request(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> _ReactiveAuthResponse:
        stale = self.cookie_generation == 0
        stale_index = self.stale_requests_started if stale else None
        return _ReactiveAuthResponse(self, stale=stale, stale_index=stale_index)


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
    async def test_expired_session_authentication_is_single_flight(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Concurrent expired-session checks share one login attempt."""
        client = LuxpowerClient("testuser", "testpass")
        client._session_expires = datetime.now() - timedelta(seconds=1)
        start = asyncio.Event()
        login_started = asyncio.Event()
        release_login = asyncio.Event()
        login_calls = 0

        async def fake_login(_retry_count: int = 0) -> None:
            nonlocal login_calls
            login_calls += 1
            login_started.set()
            await release_login.wait()
            client._session_expires = datetime.now() + timedelta(hours=2)

        async def authenticate_after_start() -> None:
            await start.wait()
            await client._ensure_authenticated()

        monkeypatch.setattr(client, "login", fake_login)
        tasks = [asyncio.create_task(authenticate_after_start()) for _ in range(10)]
        start.set()
        await asyncio.wait_for(login_started.wait(), timeout=1)
        for _ in range(3):
            await asyncio.sleep(0)

        try:
            assert login_calls == 1
        finally:
            release_login.set()
            await asyncio.gather(*tasks)
            await client.close()

    @pytest.mark.asyncio
    async def test_cancelled_waiter_does_not_cancel_shared_authentication(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cancelling one waiter leaves the shared login running for others."""
        client = LuxpowerClient("testuser", "testpass")
        client._session_expires = datetime.now() - timedelta(seconds=1)
        login_started = asyncio.Event()
        release_login = asyncio.Event()
        login_calls = 0

        async def fake_login(_retry_count: int = 0) -> None:
            nonlocal login_calls
            login_calls += 1
            login_started.set()
            await release_login.wait()
            client._session_expires = datetime.now() + timedelta(hours=2)

        monkeypatch.setattr(client, "login", fake_login)
        cancelled_waiter = asyncio.create_task(client._ensure_authenticated())
        await asyncio.wait_for(login_started.wait(), timeout=1)
        surviving_waiter = asyncio.create_task(client._ensure_authenticated())
        await asyncio.sleep(0)

        try:
            cancelled_waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await cancelled_waiter
            release_login.set()
            await surviving_waiter
            assert login_calls == 1
        finally:
            release_login.set()
            for task in (cancelled_waiter, surviving_waiter):
                if not task.done():
                    task.cancel()
            await asyncio.gather(cancelled_waiter, surviving_waiter, return_exceptions=True)
            await client.close()

    @pytest.mark.asyncio
    async def test_failed_authentication_is_shared_and_later_call_retries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Waiters share one failure, while a later caller starts a new login."""
        client = LuxpowerClient("testuser", "testpass")
        client._session_expires = datetime.now() - timedelta(seconds=1)
        start = asyncio.Event()
        login_started = asyncio.Event()
        release_login = asyncio.Event()
        first_error = LuxpowerConnectionError("renewal failed")
        login_calls = 0

        async def fake_login(_retry_count: int = 0) -> None:
            nonlocal login_calls
            login_calls += 1
            if login_calls == 1:
                login_started.set()
                await release_login.wait()
                raise first_error
            client._session_expires = datetime.now() + timedelta(hours=2)

        async def authenticate_after_start() -> None:
            await start.wait()
            await client._ensure_authenticated()

        monkeypatch.setattr(client, "login", fake_login)
        tasks = [asyncio.create_task(authenticate_after_start()) for _ in range(10)]
        start.set()
        await asyncio.wait_for(login_started.wait(), timeout=1)
        for _ in range(3):
            await asyncio.sleep(0)
        release_login.set()

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            assert login_calls == 1
            assert all(result is first_error for result in results)

            await client._ensure_authenticated()
            assert login_calls == 2
        finally:
            release_login.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            await client.close()

    @pytest.mark.asyncio
    async def test_cancelled_only_waiter_does_not_pin_failed_authentication(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A background login failure is cleared even after its waiter cancels."""
        client = LuxpowerClient("testuser", "testpass")
        client._session_expires = datetime.now() - timedelta(seconds=1)
        login_started = asyncio.Event()
        release_login = asyncio.Event()
        login_finished = asyncio.Event()
        first_error = LuxpowerConnectionError("renewal failed after cancellation")
        login_calls = 0

        async def fake_login(_retry_count: int = 0) -> None:
            nonlocal login_calls
            login_calls += 1
            if login_calls == 1:
                login_started.set()
                try:
                    await release_login.wait()
                    raise first_error
                finally:
                    login_finished.set()
            client._session_expires = datetime.now() + timedelta(hours=2)

        monkeypatch.setattr(client, "login", fake_login)
        waiter = asyncio.create_task(client._ensure_authenticated())
        await asyncio.wait_for(login_started.wait(), timeout=1)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter

        release_login.set()
        await asyncio.wait_for(login_finished.wait(), timeout=1)
        await asyncio.sleep(0)

        try:
            await client._ensure_authenticated()
            assert login_calls == 2
        finally:
            release_login.set()
            await client.close()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("response_kind", ["401", "html"])
    async def test_concurrent_reactive_expiry_uses_one_cookie_renewal(
        self,
        monkeypatch: pytest.MonkeyPatch,
        response_kind: str,
    ) -> None:
        """Stale responses share renewal, including responses observed after it."""
        request_count = 10
        session = _ConcurrentReactiveSession(
            response_kind,
            expected_stale_requests=request_count,
            early_count=request_count // 2,
        )
        client = LuxpowerClient(
            "testuser",
            "testpass",
            session=session,  # type: ignore[arg-type]
        )
        client._session_expires = datetime.now() + timedelta(hours=1)
        client._backoff_config.update({"base_delay": 0.0, "max_delay": 0.0, "jitter": 0.0})
        login_started = asyncio.Event()
        release_login = asyncio.Event()
        cookie_mutated = asyncio.Event()
        login_calls = 0

        async def fake_login(_retry_count: int = 0) -> None:
            nonlocal login_calls
            login_calls += 1
            login_started.set()
            await release_login.wait()
            session.cookie_generation += 1
            session.cookie_mutations += 1
            client._session_expires = datetime.now() + timedelta(hours=2)
            cookie_mutated.set()

        monkeypatch.setattr(client, "login", fake_login)
        requests = [
            asyncio.create_task(client._request("POST", f"/test/{index}"))
            for index in range(request_count)
        ]

        try:
            await asyncio.wait_for(session.all_stale_requests_started.wait(), timeout=1)
            await asyncio.wait_for(login_started.wait(), timeout=1)
            for _ in range(3):
                await asyncio.sleep(0)
            assert login_calls == 1

            release_login.set()
            await asyncio.wait_for(cookie_mutated.wait(), timeout=1)
            for _ in range(3):
                await asyncio.sleep(0)
            session.release_late_stale_responses.set()

            results = await asyncio.wait_for(asyncio.gather(*requests), timeout=1)
            assert all(result["success"] is True for result in results)
            assert all(result["cookie_generation"] == 1 for result in results)
            assert login_calls == 1
            assert session.cookie_mutations == 1
        finally:
            release_login.set()
            session.release_late_stale_responses.set()
            for request in requests:
                if not request.done():
                    request.cancel()
            await asyncio.gather(*requests, return_exceptions=True)
            await client.close()

    @pytest.mark.asyncio
    async def test_proactive_and_reactive_expiry_share_one_renewal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A reactive 401 joins a proactive expired-session renewal."""
        session = _ConcurrentReactiveSession(
            "401",
            expected_stale_requests=1,
            early_count=1,
        )
        client = LuxpowerClient(
            "testuser",
            "testpass",
            session=session,  # type: ignore[arg-type]
        )
        client._session_expires = datetime.now() - timedelta(seconds=1)
        client._backoff_config.update({"base_delay": 0.0, "max_delay": 0.0, "jitter": 0.0})
        login_started = asyncio.Event()
        release_login = asyncio.Event()
        login_calls = 0

        async def fake_login(_retry_count: int = 0) -> None:
            nonlocal login_calls
            login_calls += 1
            login_started.set()
            await release_login.wait()
            session.cookie_generation += 1
            session.cookie_mutations += 1
            client._session_expires = datetime.now() + timedelta(hours=2)

        monkeypatch.setattr(client, "login", fake_login)
        proactive = asyncio.create_task(client._ensure_authenticated())
        await asyncio.wait_for(login_started.wait(), timeout=1)
        reactive = asyncio.create_task(client._request("POST", "/test/reactive"))

        try:
            await asyncio.wait_for(session.all_stale_requests_started.wait(), timeout=1)
            for _ in range(3):
                await asyncio.sleep(0)
            assert login_calls == 1

            release_login.set()
            await asyncio.wait_for(asyncio.gather(proactive, reactive), timeout=1)
            assert login_calls == 1
            assert session.cookie_mutations == 1
        finally:
            release_login.set()
            session.release_late_stale_responses.set()
            for task in (proactive, reactive):
                if not task.done():
                    task.cancel()
            await asyncio.gather(proactive, reactive, return_exceptions=True)
            await client.close()

    @pytest.mark.asyncio
    async def test_close_cancels_owned_auth_task_with_injected_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Closing always drains client-owned auth work, not the injected session."""
        auth_started = asyncio.Event()
        auth_finished = asyncio.Event()
        never_release = asyncio.Event()

        async with aiohttp.ClientSession() as injected_session:
            client = LuxpowerClient(
                "testuser",
                "testpass",
                session=injected_session,
            )
            client._session_expires = datetime.now() - timedelta(seconds=1)

            async def fake_login(_retry_count: int = 0) -> None:
                auth_started.set()
                try:
                    await never_release.wait()
                finally:
                    auth_finished.set()

            monkeypatch.setattr(client, "login", fake_login)
            waiter = asyncio.create_task(client._ensure_authenticated())
            await asyncio.wait_for(auth_started.wait(), timeout=1)
            owned_auth_task = client._authentication_task
            assert owned_auth_task is not None

            try:
                await client.close()

                assert auth_finished.is_set()
                assert owned_auth_task.done()
                assert owned_auth_task.cancelled()
                assert client._authentication_task is None
                assert not injected_session.closed
            finally:
                never_release.set()
                if not owned_auth_task.done():
                    owned_auth_task.cancel()
                if not waiter.done():
                    waiter.cancel()
                await asyncio.gather(owned_auth_task, waiter, return_exceptions=True)

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
