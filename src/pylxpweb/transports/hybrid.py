"""Hybrid transport implementation.

This module provides the HybridTransport class that combines a local transport
(Modbus or Dongle) with an HTTP transport for fallback capability.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar

from .capabilities import TransportCapabilities
from .data import BatteryBankData, InverterEnergyData, InverterRuntimeData
from .exceptions import (
    TransportConnectionError,
    TransportReadError,
    TransportTimeoutError,
    TransportWriteError,
)
from .protocol import BaseTransport

if TYPE_CHECKING:
    from .dongle import DongleTransport
    from .http import HTTPTransport
    from .modbus import ModbusTransport

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


class HybridTransport(BaseTransport):
    """Transport that tries local first, falls back to HTTP on failure.

    This transport wraps both a local transport (Modbus or Dongle) and an
    HTTP transport. It attempts all operations on the local transport first,
    and automatically falls back to HTTP if the local operation fails.

    Benefits:
        - Fast local polling when inverter is reachable
        - Reliable fallback when local connection fails
        - Automatic recovery when local becomes available after retry interval

    Session Management:
        The HTTPTransport wraps a LuxpowerClient which may be shared across
        multiple transports. The LuxpowerClient session lifecycle must be
        managed separately via its context manager - HybridTransport.disconnect()
        only marks the transport as disconnected, not the underlying client.

    Example:
        from pylxpweb.transports import (
            create_modbus_transport,
            create_http_transport,
            HybridTransport,
        )

        # LuxpowerClient context manager manages the session
        async with LuxpowerClient(username, password) as client:
            local = create_modbus_transport(host="192.168.1.100", serial="CE12345678")
            http = create_http_transport(client, "CE12345678")

            transport = HybridTransport(local, http)
            async with transport:
                # Tries local first, falls back to HTTP
                runtime = await transport.read_runtime()
            # LuxpowerClient session closed when exiting client context manager
    """

    def __init__(
        self,
        local_transport: ModbusTransport | DongleTransport,
        http_transport: HTTPTransport,
        *,
        prefer_local: bool = True,
        local_retry_interval: float = 60.0,
    ) -> None:
        """Initialize hybrid transport.

        Args:
            local_transport: Primary local transport (Modbus or Dongle)
            http_transport: Fallback HTTP transport
            prefer_local: If True, always try local first (default: True)
            local_retry_interval: Seconds before retrying local after failure
                (default: 60.0)
        """
        super().__init__(local_transport.serial)
        self._local = local_transport
        self._http = http_transport
        self._prefer_local = prefer_local
        self._local_retry_interval = local_retry_interval
        self._local_failed_at: float | None = None
        self._using_local: bool = True

    @property
    def capabilities(self) -> TransportCapabilities:
        """Get combined capabilities (prefers local capabilities)."""
        # Local typically has more capabilities (direct register access)
        return self._local.capabilities

    @property
    def is_using_local(self) -> bool:
        """Check if currently using local transport."""
        if not self._prefer_local:
            return False
        if self._local_failed_at is None:
            return True
        # Check if retry interval has passed
        return time.monotonic() - self._local_failed_at >= self._local_retry_interval

    @property
    def local_transport(self) -> ModbusTransport | DongleTransport:
        """Get the underlying local transport."""
        return self._local

    @property
    def http_transport(self) -> HTTPTransport:
        """Get the underlying HTTP transport."""
        return self._http

    @property
    def register_observation_error_count(self) -> int:
        """Return the local transport's redacted observer-error count."""
        return self._local.register_observation_error_count

    def _mark_local_failed(self) -> None:
        """Mark local transport as failed, enabling HTTP fallback."""
        self._local_failed_at = time.monotonic()
        self._using_local = False
        _LOGGER.warning(
            "Local transport failed for %s, using HTTP fallback for %.0f seconds",
            self._serial,
            self._local_retry_interval,
        )

    def _check_local_recovery(self) -> None:
        """Check if local transport should be retried."""
        if self._local_failed_at is not None and self.is_using_local:
            _LOGGER.info(
                "Retry interval passed, attempting local transport for %s",
                self._serial,
            )
            self._local_failed_at = None
            self._using_local = True

    async def _with_fallback(
        self,
        local_op: Callable[[], Awaitable[T]],
        http_op: Callable[[], Awaitable[T]],
        operation_name: str,
    ) -> T:
        """Execute operation with local-first, HTTP-fallback pattern.

        Args:
            local_op: Async callable for local transport operation
            http_op: Async callable for HTTP transport operation
            operation_name: Name of operation for logging

        Returns:
            Result from whichever transport succeeds
        """
        self._ensure_connected()
        self._check_local_recovery()

        if self._using_local and self._local.is_connected:
            try:
                return await local_op()
            except (
                TransportReadError,
                TransportWriteError,
                TransportTimeoutError,
                TransportConnectionError,
            ) as err:
                self._mark_local_failed()
                _LOGGER.debug("Local %s failed: %s", operation_name, err)

        return await http_op()

    async def connect(self) -> None:
        """Connect both transports.

        HTTP is connected first (more reliable), then local is attempted.
        If local fails, HTTP fallback will be used until retry interval passes.

        Raises:
            TransportConnectionError: If HTTP connection fails (critical)
        """
        # Connect HTTP first (more reliable, required for fallback)
        await self._http.connect()

        # Try to connect local (don't fail if local is unavailable)
        try:
            await self._local.connect()
            self._using_local = True
            _LOGGER.debug(
                "Hybrid transport connected for %s (local: active)",
                self._serial,
            )
        except TransportConnectionError as err:
            self._mark_local_failed()
            _LOGGER.warning(
                "Local transport unavailable for %s: %s - using HTTP fallback",
                self._serial,
                err,
            )

        self._connected = True

    async def disconnect(self) -> None:
        """Disconnect both transports."""
        try:
            await self._local.disconnect()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Error disconnecting local transport: %s", err)

        try:
            await self._http.disconnect()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Error disconnecting HTTP transport: %s", err)

        self._connected = False
        _LOGGER.debug("Hybrid transport disconnected for %s", self._serial)

    async def async_shutdown(self) -> None:
        """Terminally shut down both sides, preferring their fast paths.

        ``DongleTransport.async_shutdown()`` interrupts in-flight
        transactions instead of queueing behind the transaction lock (whose
        worst case spans the whole retry loop). Without this forwarder a
        hybrid caller could only reach the blocking ``disconnect()`` on the
        local side. Sides without an ``async_shutdown`` fall back to their
        ordinary ``disconnect()``. Like the dongle's, this is terminal —
        discard the transport afterwards.
        """
        for side in (self._local, self._http):
            shutdown = getattr(type(side), "async_shutdown", None)
            try:
                if shutdown is not None:
                    await shutdown(side)
                else:
                    await side.disconnect()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Error shutting down %s transport: %s", type(side).__name__, err)

        self._connected = False
        _LOGGER.debug("Hybrid transport shut down for %s", self._serial)

    async def read_runtime(self) -> InverterRuntimeData:
        """Read runtime data, preferring local transport.

        Returns:
            Runtime data with all values properly scaled

        Raises:
            TransportReadError: If both local and HTTP fail
            TransportTimeoutError: If request times out
        """
        return await self._with_fallback(
            self._local.read_runtime,
            self._http.read_runtime,
            "read_runtime",
        )

    async def read_energy(self) -> InverterEnergyData:
        """Read energy statistics, preferring local transport.

        Returns:
            Energy data with all values in kWh

        Raises:
            TransportReadError: If both local and HTTP fail
            TransportTimeoutError: If request times out
        """
        return await self._with_fallback(
            self._local.read_energy,
            self._http.read_energy,
            "read_energy",
        )

    async def read_battery(self) -> BatteryBankData | None:
        """Read battery information, preferring local transport.

        Returns:
            Battery bank data if batteries present, None otherwise

        Raises:
            TransportReadError: If both local and HTTP fail
        """
        return await self._with_fallback(
            self._local.read_battery,
            self._http.read_battery,
            "read_battery",
        )

    async def read_parameters(
        self,
        start_address: int,
        count: int,
    ) -> dict[int, int]:
        """Read configuration parameters, preferring local transport.

        Args:
            start_address: Starting register address
            count: Number of registers to read

        Returns:
            Dict mapping register address to raw integer value

        Raises:
            TransportReadError: If both local and HTTP fail
            TransportTimeoutError: If request times out
        """
        return await self._with_fallback(
            lambda: self._local.read_parameters(start_address, count),
            lambda: self._http.read_parameters(start_address, count),
            "read_parameters",
        )

    async def write_parameters(
        self,
        parameters: dict[int, int],
    ) -> bool:
        """Write configuration parameters, preferring local transport.

        Args:
            parameters: Dict mapping register address to value to write

        Returns:
            True if write succeeded

        Raises:
            TransportWriteError: If both local and HTTP fail
            TransportTimeoutError: If request times out
        """
        return await self._with_fallback(
            lambda: self._local.write_parameters(parameters),
            lambda: self._http.write_parameters(parameters),
            "write_parameters",
        )

    async def read_named_parameters(
        self,
        start_address: int,
        count: int,
    ) -> dict[str, Any]:
        """Read configuration parameters as named key-value pairs, preferring local.

        Args:
            start_address: Starting register address
            count: Number of registers to read

        Returns:
            Dict mapping parameter name to value

        Raises:
            TransportReadError: If both local and HTTP fail
            TransportTimeoutError: If request times out
        """
        return await self._with_fallback(
            lambda: self._local.read_named_parameters(start_address, count),
            lambda: self._http.read_named_parameters(start_address, count),
            "read_named_parameters",
        )

    async def write_named_parameters(
        self,
        parameters: dict[str, Any],
    ) -> bool:
        """Write configuration parameters using named keys, preferring local.

        Args:
            parameters: Dict mapping parameter name to value

        Returns:
            True if write succeeded

        Raises:
            TransportWriteError: If both local and HTTP fail
            TransportTimeoutError: If request times out
        """
        return await self._with_fallback(
            lambda: self._local.write_named_parameters(parameters),
            lambda: self._http.write_named_parameters(parameters),
            "write_named_parameters",
        )
