"""Luxpower/EG4 Inverter API Client.

This module provides a comprehensive async client for interacting with the
Luxpower/EG4 inverter web monitoring API.

Key Features:
- Async/await support with aiohttp
- Session management with auto-reauthentication
- Request caching with configurable TTL
- Exponential backoff for rate limiting
- Automatic retry for transient errors (DATAFRAME_TIMEOUT, BUSY, etc.)
- Support for injected aiohttp.ClientSession (Platinum tier requirement)
- Comprehensive error handling

Retry Behavior:
- Transient errors (hardware communication timeouts) are automatically retried
  up to MAX_TRANSIENT_ERROR_RETRIES times with exponential backoff
- Non-transient errors (permissions, invalid parameters) fail immediately
- Session expiration triggers automatic re-authentication and retry
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
from .constants import (
    BACKOFF_BASE_DELAY_SECONDS,
    BACKOFF_MAX_DELAY_SECONDS,
    HTTP_UNAUTHORIZED,
    MAX_LOGIN_RETRIES,
    MAX_TRANSIENT_ERROR_RETRIES,
    TRANSIENT_ERROR_MESSAGES,
)
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
        # Account level: "guest", "viewer", "operator", "owner", "installer"
        self._account_level: str | None = None

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
            "base_delay": BACKOFF_BASE_DELAY_SECONDS,
            "max_delay": BACKOFF_MAX_DELAY_SECONDS,
            "exponential_factor": 2.0,
            "jitter": 0.1,
        }
        self._current_backoff_delay: float = 0.0
        self._consecutive_errors: int = 0

        # Hour tracking for automatic cache invalidation at boundaries
        # Invalidates cache on first request after hour changes to ensure
        # fresh data at date boundaries (especially midnight for daily energy values)
        self._last_request_hour: int | None = None

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

    @property
    def account_level(self) -> str | None:
        """Get detected account permission level.

        Returns:
            Account level: "guest", "viewer", "operator", "owner", "installer",
            or None if not detected.

        Note:
            This is automatically detected after login by checking device endUser fields.
            - "guest": Read-only access, parameter read/write blocked
            - "viewer"/"operator": Limited access, control operations may be blocked
            - "owner"/"installer": Full access to all operations

        Example:
            >>> async with LuxpowerClient(username, password) as client:
            >>>     print(f"Account level: {client.account_level}")
            >>>     if client.account_level in ("guest", "viewer", "operator"):
            >>>         print("Control operations may be restricted")
        """
        return self._account_level

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

    @property
    def cache_stats(self) -> dict[str, int | dict[str, int]]:
        """Get cache statistics.

        Returns:
            dict with statistics:
                - total_entries: Number of cached responses
                - endpoints: Dict of endpoint types to entry counts

        Example:
            >>> stats = client.cache_stats
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

    def _is_transient_error(self, error_msg: str) -> bool:
        """Check if an error message indicates a transient error.

        Args:
            error_msg: The error message to check

        Returns:
            bool: True if the error is transient and should be retried
        """
        return any(transient in error_msg for transient in TRANSIENT_ERROR_MESSAGES)

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        data: dict[str, Any] | None = None,
        cache_key: str | None = None,
        cache_endpoint: str | None = None,
        _retry_count: int = 0,
    ) -> dict[str, Any]:
        """Make an HTTP request to the API.

        Automatically invalidates cache on first request after hour boundary
        to ensure fresh data at date rollovers (especially midnight for daily
        energy values).

        Automatically retries transient errors (e.g., DATAFRAME_TIMEOUT, BUSY)
        with exponential backoff up to MAX_TRANSIENT_ERROR_RETRIES attempts.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (will be joined with base_url)
            data: Request data (will be form-encoded for POST)
            cache_key: Optional cache key for response caching
            cache_endpoint: Optional endpoint key for cache TTL lookup
            _retry_count: Internal retry counter (do not set manually)

        Returns:
            dict: JSON response from the API

        Raises:
            LuxpowerAuthError: If authentication fails
            LuxpowerConnectionError: If connection fails
            LuxpowerAPIError: If API returns an error (non-transient or max retries exceeded)
        """
        # Auto-invalidate cache on first request after hour change
        # This ensures fresh data after boundaries, especially midnight
        current_hour = datetime.now().hour
        if self._last_request_hour is not None and current_hour != self._last_request_hour:
            _LOGGER.debug(
                "Hour boundary crossed (hour %d → %d), invalidating all caches",
                self._last_request_hour,
                current_hour,
            )
            self.clear_cache()

        self._last_request_hour = current_hour

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

                    # Check if this is a transient error that should be retried
                    is_transient = self._is_transient_error(error_msg)
                    can_retry = _retry_count < MAX_TRANSIENT_ERROR_RETRIES
                    if is_transient and can_retry:
                        self._handle_request_error()
                        _LOGGER.warning(
                            "Transient API error '%s' (attempt %d/%d), retrying with backoff...",
                            error_msg,
                            _retry_count + 1,
                            MAX_TRANSIENT_ERROR_RETRIES,
                        )
                        # Retry with incremented counter
                        return await self._request(
                            method,
                            endpoint,
                            data=data,
                            cache_key=cache_key,
                            cache_endpoint=cache_endpoint,
                            _retry_count=_retry_count + 1,
                        )

                    # Non-transient error or max retries exceeded
                    raise LuxpowerAPIError(f"API error (HTTP {response.status}): {error_msg}")

                # Cache successful response
                if cache_key and cache_endpoint:
                    self._cache_response(cache_key, json_data)

                self._handle_request_success()
                return json_data

        except aiohttp.ContentTypeError as err:
            # Session expired and API returned HTML login page instead of JSON
            self._handle_request_error(err)
            _LOGGER.warning(
                "Got HTML response instead of JSON (session expired), attempting to re-authenticate"
            )
            try:
                await self.login()
                _LOGGER.debug("Re-authentication successful, retrying request")
                # Retry the request with the new session
                return await self._request(
                    method,
                    endpoint,
                    data=data,
                    cache_key=cache_key,
                    cache_endpoint=cache_endpoint,
                    _retry_count=_retry_count,  # Preserve retry count
                )
            except LuxpowerAuthError:
                # True authentication failure (wrong credentials, account locked)
                _LOGGER.error("Re-authentication failed: invalid credentials")
                raise
            except LuxpowerConnectionError as login_err:
                # Transient connection issue during re-auth - don't treat as auth failure
                # This allows Home Assistant to retry automatically instead of requiring
                # manual re-authentication (fixes issue #70)
                _LOGGER.warning("Re-authentication failed due to connection issue: %s", login_err)
                raise
            except Exception as login_err:
                # Other unexpected errors during re-auth - treat as connection issue
                # to allow automatic retry rather than requiring manual intervention
                _LOGGER.error("Re-authentication failed unexpectedly: %s", login_err)
                raise LuxpowerConnectionError(
                    f"Re-authentication failed: {login_err}"
                ) from login_err

        except aiohttp.ClientResponseError as err:
            self._handle_request_error(err)
            if err.status == HTTP_UNAUTHORIZED:
                # Session expired - try to re-authenticate once
                _LOGGER.warning("Got 401 Unauthorized, attempting to re-authenticate")
                try:
                    await self.login()
                    _LOGGER.debug("Re-authentication successful, retrying request")
                    # Retry the request with the new session
                    return await self._request(
                        method,
                        endpoint,
                        data=data,
                        cache_key=cache_key,
                        cache_endpoint=cache_endpoint,
                        _retry_count=_retry_count,  # Preserve retry count
                    )
                except LuxpowerAuthError:
                    # True authentication failure (wrong credentials, account locked)
                    _LOGGER.error("Re-authentication failed: invalid credentials")
                    raise
                except LuxpowerConnectionError as login_err:
                    # Transient connection issue during re-auth - don't treat as auth failure
                    # This allows Home Assistant to retry automatically instead of requiring
                    # manual re-authentication (fixes issue #70)
                    _LOGGER.warning(
                        "Re-authentication failed due to connection issue: %s", login_err
                    )
                    raise
                except Exception as login_err:
                    # Other unexpected errors during re-auth - treat as connection issue
                    # to allow automatic retry rather than requiring manual intervention
                    _LOGGER.error("Re-authentication failed unexpectedly: %s", login_err)
                    raise LuxpowerConnectionError(
                        f"Re-authentication failed: {login_err}"
                    ) from login_err
            raise LuxpowerAPIError(f"HTTP {err.status}: {err.message}") from err

        except LuxpowerAPIError:
            # Re-raise our own exceptions (from transient error handling, etc)
            raise

        except aiohttp.ClientError as err:
            self._handle_request_error(err)
            raise LuxpowerConnectionError(f"Connection error: {err}") from err

        except Exception as err:
            self._handle_request_error(err)
            raise LuxpowerAPIError(f"Unexpected error: {err}") from err

    # Authentication

    async def login(self, _retry_count: int = 0) -> LoginResponse:
        """Authenticate with the API and establish a session.

        This method includes automatic retry logic for transient failures
        (network issues, temporary server errors) with exponential backoff.
        This allows recovery from temporary issues without requiring manual
        user intervention (fixes issue #70).

        Args:
            _retry_count: Internal retry counter (do not set manually)

        Returns:
            LoginResponse: Login response with user and plant information

        Raises:
            LuxpowerAuthError: If authentication fails due to invalid credentials
            LuxpowerConnectionError: If connection fails after all retries
        """
        _LOGGER.debug(
            "Logging in as %s (attempt %d/%d)",
            self.username,
            _retry_count + 1,
            MAX_LOGIN_RETRIES,
        )

        data = {
            "account": self.username,
            "password": self.password,
            "language": "ENGLISH",
        }

        try:
            response = await self._request("POST", "/WManage/api/login", data=data)
            login_data = LoginResponse.model_validate(response)

            # Store session info (session cookie is automatically handled by aiohttp)
            self._session_expires = datetime.now() + timedelta(hours=2)
            self._user_id = login_data.userId
            _LOGGER.debug("Login successful, session expires at %s", self._session_expires)

            # Detect account level from endUser field
            await self._detect_account_level()

            return login_data

        except LuxpowerAuthError:
            # True authentication failure (wrong password, account locked)
            # Don't retry - re-raise immediately
            raise

        except LuxpowerAPIError:
            # API-level error (not transient) - don't retry
            raise

        except LuxpowerConnectionError as err:
            # Transient connection issue - retry with backoff
            if _retry_count < MAX_LOGIN_RETRIES - 1:
                delay = self._backoff_config["base_delay"] * (2**_retry_count)
                _LOGGER.warning(
                    "Login failed due to connection error (attempt %d/%d): %s. "
                    "Retrying in %.1f seconds...",
                    _retry_count + 1,
                    MAX_LOGIN_RETRIES,
                    err,
                    delay,
                )
                await asyncio.sleep(delay)
                return await self.login(_retry_count=_retry_count + 1)
            # Max retries exceeded
            _LOGGER.error(
                "Login failed after %d attempts due to connection errors: %s",
                MAX_LOGIN_RETRIES,
                err,
            )
            raise

    async def _ensure_authenticated(self) -> None:
        """Ensure we have a valid session, re-authenticating if needed."""
        if not self._session_expires or datetime.now() >= self._session_expires:
            _LOGGER.debug("Session expired or missing, re-authenticating")
            await self.login()

    async def _detect_account_level(self) -> None:
        """Detect account permission level from device list endUser field.

        This checks the endUser field from the first available device to determine
        the account type. The detection is done once after login and cached.

        Account levels:
        - "guest": Read-only access, parameter read/write blocked
        - "viewer" or username: Limited access, control operations may be blocked
        - "installer": Full access to all operations

        Note:
            If endUser is a username (not "guest"), we classify it as "viewer/operator"
            level since it's neither guest nor installer. This may indicate limited
            control permissions.
        """
        if self._account_level is not None:
            return  # Already detected

        try:
            # Get plants to find a valid plant ID
            plants_response = await self.api.plants.get_plants()
            if not plants_response.rows:
                _LOGGER.warning("No plants found, cannot detect account level")
                return

            # Get devices for first plant
            devices_response = await self.api.devices.get_devices(plants_response.rows[0].plantId)
            if not devices_response.rows:
                _LOGGER.warning("No devices found, cannot detect account level")
                return

            # Check endUser field from first device
            end_user = devices_response.rows[0].endUser
            if end_user == "guest":
                self._account_level = "guest"
            elif end_user and ("installer" in end_user.lower()):
                self._account_level = "installer"
            elif end_user and end_user != "":
                # Has endUser value but not guest or installer - likely viewer/operator
                self._account_level = "viewer"
            else:
                # No endUser field or empty - assume owner (backward compatibility)
                self._account_level = "owner"

            _LOGGER.debug("Detected account level: %s (endUser=%s)", self._account_level, end_user)

        except Exception as err:
            _LOGGER.warning("Failed to detect account level: %s", err)
