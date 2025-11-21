"""Luxpower/EG4 Inverter API Client.

This module provides a comprehensive async client for interacting with the
Luxpower/EG4 inverter web monitoring API.

Key Features:
- Async/await support with aiohttp
- Session management with auto-reauthentication
- Request caching with configurable TTL
- Exponential backoff for rate limiting
- Support for injected aiohttp.ClientSession (Platinum tier requirement)
- Comprehensive error handling
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import aiohttp
from aiohttp import ClientTimeout

from .api_namespace import APINamespace
from .endpoints import (
    AnalyticsEndpoints,
    ControlEndpoints,
    DeviceEndpoints,
    ExportEndpoints,
    FirmwareEndpoints,
    ForecastingEndpoints,
    PlantEndpoints,
)
from .exceptions import (
    LuxpowerAPIError,
    LuxpowerAuthError,
    LuxpowerConnectionError,
)
from .models import LoginResponse

_LOGGER = logging.getLogger(__name__)


class LuxpowerClient:
    """Luxpower/EG4 Inverter API Client.

    This client provides async access to the Luxpower/EG4 inverter web monitoring API.

    Example:
        ```python
        async with LuxpowerClient(username, password) as client:
            plants = await client.get_plants()
            for plant in plants.rows:
                devices = await client.get_devices(plant.plantId)
                for device in devices.rows:
                    runtime = await client.get_inverter_runtime(device.serialNum)
                    print(f"Power: {runtime.ppv}W, SOC: {runtime.soc}%")
        ```
    """

    def __init__(
        self,
        username: str,
        password: str,
        *,
        base_url: str = "https://monitor.eg4electronics.com",
        verify_ssl: bool = True,
        timeout: int = 30,
        session: aiohttp.ClientSession | None = None,
        iana_timezone: str | None = None,
    ) -> None:
        """Initialize the Luxpower API client.

        Args:
            username: API username for authentication
            password: API password for authentication
            base_url: Base URL for the API (default: EG4 Electronics endpoint)
            verify_ssl: Whether to verify SSL certificates
            timeout: Request timeout in seconds (default: 30)
            session: Optional aiohttp ClientSession for session injection
            iana_timezone: Optional IANA timezone (e.g., "America/Los_Angeles")
                for DST auto-detection. If not provided, DST auto-detection
                will be disabled. This is required because the API doesn't
                provide sufficient location data to reliably determine timezone.
        """
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.verify_ssl = verify_ssl
        self.timeout = ClientTimeout(total=timeout)
        self.iana_timezone = iana_timezone

        # Session management
        self._session: aiohttp.ClientSession | None = session
        self._owns_session: bool = session is None
        self._session_id: str | None = None
        self._session_expires: datetime | None = None
        self._user_id: int | None = None

        # Response cache with TTL configuration
        self._response_cache: dict[str, dict[str, Any]] = {}
        self._cache_ttl_config: dict[str, timedelta] = {
            "device_discovery": timedelta(minutes=15),
            "battery_info": timedelta(minutes=5),
            "parameter_read": timedelta(minutes=2),
            "quick_charge_status": timedelta(minutes=1),
            "inverter_runtime": timedelta(seconds=20),
            "inverter_energy": timedelta(seconds=20),
            "midbox_runtime": timedelta(seconds=20),
        }

        # Backoff configuration
        self._backoff_config: dict[str, float] = {
            "base_delay": 1.0,
            "max_delay": 60.0,
            "exponential_factor": 2.0,
            "jitter": 0.1,
        }
        self._current_backoff_delay: float = 0.0
        self._consecutive_errors: int = 0

        # Cache invalidation for boundary handling
        self._last_cache_invalidation: datetime | None = None

        # API namespace (new v0.2.0 interface)
        self._api_namespace: APINamespace | None = None

        # Endpoint modules (lazy-loaded) - kept for backward compatibility during transition
        self._plants_endpoints: PlantEndpoints | None = None
        self._devices_endpoints: DeviceEndpoints | None = None
        self._control_endpoints: ControlEndpoints | None = None
        self._analytics_endpoints: AnalyticsEndpoints | None = None
        self._forecasting_endpoints: ForecastingEndpoints | None = None
        self._export_endpoints: ExportEndpoints | None = None
        self._firmware_endpoints: FirmwareEndpoints | None = None

    async def __aenter__(self) -> LuxpowerClient:
        """Async context manager entry."""
        await self.login()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session.

        Returns:
            aiohttp.ClientSession: The session to use for requests.
        """
        if self._session is not None and not self._owns_session:
            return self._session

        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(ssl=self.verify_ssl)
            self._session = aiohttp.ClientSession(connector=connector, timeout=self.timeout)
            self._owns_session = True

        return self._session

    async def close(self) -> None:
        """Close the session if we own it.

        Only closes the session if it was created by this client,
        not if it was injected.
        """
        if self._session and not self._session.closed and self._owns_session:
            await self._session.close()

    # API Namespace (v0.2.0+)

    @property
    def api(self) -> APINamespace:
        """Access all API endpoints through the api namespace.

        This is the recommended way to access API endpoints in v0.2.0+.
        It provides a clear separation between:
        - Low-level API calls: `client.api.plants.get_plants()`
        - High-level object interface: `client.get_station(plant_id)` (coming in Phase 1)

        Returns:
            APINamespace: The API namespace providing access to all endpoint groups.

        Example:
            ```python
            async with LuxpowerClient(username, password) as client:
                # Access plants endpoint
                plants = await client.api.plants.get_plants()

                # Access devices endpoint
                runtime = await client.api.devices.get_inverter_runtime(serial)

                # Access control endpoint
                await client.api.control.start_quick_charge(serial)
            ```
        """
        if self._api_namespace is None:
            self._api_namespace = APINamespace(self)
        return self._api_namespace

    # Endpoint Module Properties (Deprecated - use client.api.* instead)

    @property
    def plants(self) -> PlantEndpoints:
        """Access plant/station management endpoints."""
        if self._plants_endpoints is None:
            self._plants_endpoints = PlantEndpoints(self)
        return self._plants_endpoints

    @property
    def devices(self) -> DeviceEndpoints:
        """Access device discovery and runtime data endpoints."""
        if self._devices_endpoints is None:
            self._devices_endpoints = DeviceEndpoints(self)
        return self._devices_endpoints

    @property
    def control(self) -> ControlEndpoints:
        """Access parameter control and device function endpoints."""
        if self._control_endpoints is None:
            self._control_endpoints = ControlEndpoints(self)
        return self._control_endpoints

    @property
    def analytics(self) -> AnalyticsEndpoints:
        """Access analytics, charts, and event log endpoints."""
        if self._analytics_endpoints is None:
            self._analytics_endpoints = AnalyticsEndpoints(self)
        return self._analytics_endpoints

    @property
    def forecasting(self) -> ForecastingEndpoints:
        """Access solar and weather forecasting endpoints."""
        if self._forecasting_endpoints is None:
            self._forecasting_endpoints = ForecastingEndpoints(self)
        return self._forecasting_endpoints

    @property
    def export(self) -> ExportEndpoints:
        """Access data export endpoints."""
        if self._export_endpoints is None:
            self._export_endpoints = ExportEndpoints(self)
        return self._export_endpoints

    @property
    def firmware(self) -> FirmwareEndpoints:
        """Access firmware update endpoints."""
        if self._firmware_endpoints is None:
            self._firmware_endpoints = FirmwareEndpoints(self)
        return self._firmware_endpoints

    async def _apply_backoff(self) -> None:
        """Apply exponential backoff delay before API requests."""
        if self._current_backoff_delay > 0:
            jitter = random.uniform(0, self._backoff_config["jitter"])
            delay = self._current_backoff_delay + jitter
            _LOGGER.debug("Applying backoff delay: %.2f seconds", delay)
            await asyncio.sleep(delay)

    def _handle_request_success(self) -> None:
        """Reset backoff on successful request."""
        if self._consecutive_errors > 0:
            _LOGGER.debug(
                "Request successful, resetting backoff after %d errors",
                self._consecutive_errors,
            )
        self._consecutive_errors = 0
        self._current_backoff_delay = 0.0

    def _handle_request_error(self, error: Exception | None = None) -> None:
        """Increase backoff delay on request error.

        Args:
            error: The exception that caused the error (for logging)
        """
        self._consecutive_errors += 1
        base_delay = self._backoff_config["base_delay"]
        max_delay = self._backoff_config["max_delay"]
        factor = self._backoff_config["exponential_factor"]

        self._current_backoff_delay = min(
            base_delay * (factor ** (self._consecutive_errors - 1)), max_delay
        )

        error_msg = f": {error}" if error else ""
        _LOGGER.warning(
            "API request error #%d%s, next backoff delay: %.2f seconds",
            self._consecutive_errors,
            error_msg,
            self._current_backoff_delay,
        )

    def _get_cache_key(self, endpoint_key: str, **params: Any) -> str:
        """Generate a cache key for an endpoint and parameters."""
        param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        return f"{endpoint_key}:{param_str}"

    def _is_cache_valid(self, cache_key: str, endpoint_key: str) -> bool:
        """Check if cached response is still valid."""
        if cache_key not in self._response_cache:
            return False

        cache_entry = self._response_cache[cache_key]
        cache_time = cache_entry.get("timestamp")
        if not isinstance(cache_time, datetime):
            return False

        ttl = self._cache_ttl_config.get(endpoint_key, timedelta(seconds=30))
        return datetime.now() < cache_time + ttl

    def _cache_response(self, cache_key: str, response: dict[str, Any]) -> None:
        """Cache a response with timestamp."""
        self._response_cache[cache_key] = {
            "timestamp": datetime.now(),
            "response": response,
        }

    def _get_cached_response(self, cache_key: str) -> dict[str, Any] | None:
        """Get cached response if valid."""
        if cache_key in self._response_cache:
            return self._response_cache[cache_key].get("response")
        return None

    # ============================================================================
    # Public Cache Management Methods
    # ============================================================================

    def clear_cache(self) -> None:
        """Clear all cached API responses.

        This forces fresh data retrieval on the next API calls.
        Useful when you know data has changed and need immediate updates.

        Example:
            >>> client.clear_cache()
            >>> # Next API calls will fetch fresh data
        """
        self._response_cache.clear()
        _LOGGER.debug("Cache cleared (%d entries removed)", len(self._response_cache))

    def invalidate_cache_for_device(self, serial_num: str) -> None:
        """Invalidate all cached responses for a specific device.

        Args:
            serial_num: Device serial number (inverter, battery, or GridBOSS)

        Example:
            >>> # After changing device settings
            >>> client.invalidate_cache_for_device("1234567890")
            >>> # Next calls for this device will fetch fresh data
        """
        keys_to_remove = [key for key in self._response_cache if serial_num in key]

        for key in keys_to_remove:
            del self._response_cache[key]

        _LOGGER.debug(
            "Cache invalidated for device %s (%d entries removed)",
            serial_num,
            len(keys_to_remove),
        )

    def get_cache_stats(self) -> dict[str, int | dict[str, int]]:
        """Get cache statistics.

        Returns:
            dict with statistics:
                - total_entries: Number of cached responses
                - endpoints: Dict of endpoint types to entry counts

        Example:
            >>> stats = client.get_cache_stats()
            >>> print(f"Cache size: {stats['total_entries']}")
            >>> for endpoint, count in stats['endpoints'].items():
            >>>     print(f"  {endpoint}: {count} entries")
        """
        endpoints: dict[str, int] = {}

        for key in self._response_cache:
            # Extract endpoint type from cache key (format: "endpoint:params")
            endpoint = key.split(":")[0] if ":" in key else key
            endpoints[endpoint] = endpoints.get(endpoint, 0) + 1

        return {
            "total_entries": len(self._response_cache),
            "endpoints": endpoints,
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        data: dict[str, Any] | None = None,
        cache_key: str | None = None,
        cache_endpoint: str | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (will be joined with base_url)
            data: Request data (will be form-encoded for POST)
            cache_key: Optional cache key for response caching
            cache_endpoint: Optional endpoint key for cache TTL lookup

        Returns:
            dict: JSON response from the API

        Raises:
            LuxpowerAuthError: If authentication fails
            LuxpowerConnectionError: If connection fails
            LuxpowerAPIError: If API returns an error
        """
        # Check cache if enabled
        if cache_key and cache_endpoint and self._is_cache_valid(cache_key, cache_endpoint):
            cached = self._get_cached_response(cache_key)
            if cached:
                _LOGGER.debug("Using cached response for %s", cache_key)
                return cached

        # Apply backoff if needed
        await self._apply_backoff()

        session = await self._get_session()
        url = urljoin(self.base_url, endpoint)

        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json",
        }

        try:
            async with session.request(method, url, data=data, headers=headers) as response:
                response.raise_for_status()
                json_data: dict[str, Any] = await response.json()

                # Handle API-level errors (HTTP 200 but success=false in JSON)
                if isinstance(json_data, dict) and not json_data.get("success", True):
                    error_msg = json_data.get("message") or json_data.get("msg")
                    if not error_msg:
                        # No standard error message, show entire response
                        error_msg = f"No error message. Full response: {json_data}"
                    raise LuxpowerAPIError(f"API error (HTTP {response.status}): {error_msg}")

                # Cache successful response
                if cache_key and cache_endpoint:
                    self._cache_response(cache_key, json_data)

                self._handle_request_success()
                return json_data

        except aiohttp.ClientResponseError as err:
            self._handle_request_error(err)
            if err.status == 401:
                # Session expired - try to re-authenticate once
                _LOGGER.warning("Got 401 Unauthorized, attempting to re-authenticate")
                try:
                    await self.login()
                    _LOGGER.info("Re-authentication successful, retrying request")
                    # Retry the request with the new session
                    return await self._request(
                        method,
                        endpoint,
                        data=data,
                        cache_key=cache_key,
                        cache_endpoint=cache_endpoint,
                    )
                except Exception as login_err:
                    _LOGGER.error("Re-authentication failed: %s", login_err)
                    raise LuxpowerAuthError("Authentication failed") from err
            raise LuxpowerAPIError(f"HTTP {err.status}: {err.message}") from err

        except aiohttp.ClientError as err:
            self._handle_request_error(err)
            raise LuxpowerConnectionError(f"Connection error: {err}") from err

        except Exception as err:
            self._handle_request_error(err)
            raise LuxpowerAPIError(f"Unexpected error: {err}") from err

    # Authentication

    async def login(self) -> LoginResponse:
        """Authenticate with the API and establish a session.

        Returns:
            LoginResponse: Login response with user and plant information

        Raises:
            LuxpowerAuthError: If authentication fails
        """
        _LOGGER.info("Logging in as %s", self.username)

        data = {
            "account": self.username,
            "password": self.password,
            "language": "ENGLISH",
        }

        response = await self._request("POST", "/WManage/api/login", data=data)
        login_data = LoginResponse.model_validate(response)

        # Store session info (session cookie is automatically handled by aiohttp)
        self._session_expires = datetime.now() + timedelta(hours=2)
        self._user_id = login_data.userId
        _LOGGER.info("Login successful, session expires at %s", self._session_expires)

        return login_data

    async def _ensure_authenticated(self) -> None:
        """Ensure we have a valid session, re-authenticating if needed."""
        if not self._session_expires or datetime.now() >= self._session_expires:
            _LOGGER.info("Session expired or missing, re-authenticating")
            await self.login()

    # Cache Invalidation for Date/Hour Boundaries

    def should_invalidate_cache(self) -> bool:
        """Check if cache should be invalidated for hour/date boundaries.

        This implements proactive cache clearing within 5 minutes of the top
        of each hour to ensure fresh data at date boundaries (midnight).

        Returns:
            True if cache should be cleared now, False otherwise.

        Algorithm:
            1. Within 5 minutes of hour boundary (XX:55-XX:59): Consider invalidation
            2. First run: Invalidate immediately if within window
            3. Hour crossed: Always invalidate
            4. Rate limit: Minimum 10 minutes between invalidations

        See Also:
            docs/SCALING_GUIDE.md - Cache invalidation strategy
        """
        now = datetime.now()
        minutes_to_hour = 60 - now.minute

        # Outside the 5-minute window before hour boundary
        if minutes_to_hour > 5:
            return False

        # First run - invalidate if within window
        if self._last_cache_invalidation is None:
            _LOGGER.debug(
                "First run within %d minutes of hour boundary, will invalidate cache",
                minutes_to_hour,
            )
            return True

        # Check if we've crossed into a new hour
        last_hour = self._last_cache_invalidation.hour
        current_hour = now.hour
        if current_hour != last_hour:
            _LOGGER.debug(
                "Hour boundary crossed from %d:xx to %d:xx, will invalidate cache",
                last_hour,
                current_hour,
            )
            return True

        # Within 5-minute window but haven't invalidated recently
        time_since_last = now - self._last_cache_invalidation
        min_interval = timedelta(minutes=10)
        should_invalidate = time_since_last >= min_interval

        if should_invalidate:
            _LOGGER.debug(
                "Within %d minutes of hour boundary and %s since last invalidation, "
                "will invalidate cache",
                minutes_to_hour,
                time_since_last,
            )

        return should_invalidate

    def clear_all_caches(self) -> None:
        """Clear all API response caches.

        This method clears:
        - Response cache (runtime, energy, battery data)
        - Endpoint-specific caches (if accessible)

        Call this before hour boundaries to ensure fresh data at date rollover.

        See Also:
            should_invalidate_cache() - Determines when to call this method
        """
        # Clear main response cache
        self._response_cache.clear()

        # Clear endpoint caches if available
        if self._api_namespace:
            if hasattr(self.api.devices, "_response_cache"):
                self.api.devices._response_cache.clear()
            if hasattr(self.api.plants, "_response_cache"):
                self.api.plants._response_cache.clear()

        self._last_cache_invalidation = datetime.now()

        _LOGGER.info(
            "Cleared all API caches at %s to prevent date rollover issues",
            self._last_cache_invalidation.strftime("%Y-%m-%d %H:%M:%S"),
        )
