"""Modbus TCP transport implementation.

This module provides the ModbusTransport class for direct local
communication with inverters via Modbus TCP (typically through
a Waveshare RS485-to-Ethernet adapter).

IMPORTANT: Single-Client Limitation
------------------------------------
Modbus TCP supports only ONE concurrent connection per gateway/inverter.
Running multiple clients (e.g., Home Assistant + custom script) causes:
- Transaction ID desynchronization
- "Request cancelled outside pymodbus" errors
- Intermittent timeouts and data corruption

Ensure only ONE integration/script connects to each inverter at a time.
Disable other Modbus integrations before using this transport.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any, Protocol, cast

from ._modbus_base import INPUT_REGISTER_GROUPS, BaseModbusTransport
from ._modbus_client import (
    ModbusBackend,
    ModbusConnectionUnit,
    ModbusUnitLike,
    PymodbusUnit,
    RegisterClient,
    normalize_backend,
    patch_pymodbus_tid_validation,
    resolve_backend,
)
from ._register_data import DEFAULT_INPUT_BLOCK_SIZE
from .capabilities import MODBUS_CAPABILITIES, TransportCapabilities
from .exceptions import TransportConnectionError
from .observation import RegisterObserver

if TYPE_CHECKING:
    from pymodbus.client import AsyncModbusTcpClient

    from pylxpweb.devices.inverters._features import InverterFamily

_LOGGER = logging.getLogger(__name__)

_DEFAULT_SESSION_MAX_AGE = 3600.0
_FAILED_RECONNECT_COOLDOWN = 60.0

# Re-export for backward compatibility
__all__ = ["INPUT_REGISTER_GROUPS", "ModbusTransport"]


class _ClosingStateOwner(Protocol):
    """Object that owns pymodbus transport closing state."""

    is_closing: bool


def _closing_state_owner(client: object) -> _ClosingStateOwner | None:
    """Resolve closing state across supported pymodbus client layouts."""
    # Verified layouts: >=3.7 keeps is_closing on the TransactionManager at
    # client.ctx; 3.6.x keeps it on the client itself (ModbusProtocol).
    ctx = getattr(client, "ctx", None)
    if ctx is not None and hasattr(ctx, "is_closing"):
        return cast(_ClosingStateOwner, ctx)
    if hasattr(client, "is_closing"):
        return cast(_ClosingStateOwner, client)
    return None


def _monotonic() -> float:
    """Return monotonic time through a transport-local test seam."""
    return time.monotonic()


def _jittered_session_max_age(
    session_max_age: float | None,
    *,
    host: str,
    port: int,
    unit_id: int,
    serial: str,
) -> float | None:
    """Apply deterministic per-transport jitter of plus or minus ten percent."""
    if session_max_age is None:
        return None

    identity = f"{host}:{port}:{unit_id}:{serial}".encode()
    digest = hashlib.sha256(identity).digest()
    fraction = int.from_bytes(digest[:8], "big") / ((1 << 64) - 1)
    return session_max_age * (0.9 + 0.2 * fraction)


class ModbusTransport(BaseModbusTransport):
    """Modbus TCP transport for local inverter communication.

    This transport connects directly to the inverter via a Modbus TCP
    gateway (e.g., Waveshare RS485-to-Ethernet adapter).

    IMPORTANT: Single-Client Limitation
    ------------------------------------
    Modbus TCP supports only ONE concurrent connection per gateway/inverter.
    Running multiple clients (e.g., Home Assistant + custom script) causes:
    - Transaction ID desynchronization
    - "Request cancelled outside pymodbus" errors
    - Intermittent timeouts and data corruption

    Ensure only ONE integration/script connects to each inverter at a time.
    Disable other Modbus integrations before using this transport.

    Example:
        transport = ModbusTransport(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
        )
        await transport.connect()

        runtime = await transport.read_runtime()
        print(f"PV Power: {runtime.pv_total_power}W")

    Note:
        Requires the `pymodbus` package to be installed:
        uv add pymodbus
    """

    transport_type: str = "modbus_tcp"

    def __init__(
        self,
        host: str,
        port: int = 502,
        unit_id: int = 1,
        serial: str = "",
        timeout: float = 10.0,
        inverter_family: InverterFamily | None = None,
        retries: int = 2,
        retry_delay: float = 0.5,
        inter_register_delay: float = 0.05,
        pymodbus_retries: int = 3,
        max_input_block_size: int = DEFAULT_INPUT_BLOCK_SIZE,
        register_observer: RegisterObserver | None = None,
        session_max_age: float | None = _DEFAULT_SESSION_MAX_AGE,
        backend: str = "auto",
        unit: ModbusUnitLike | None = None,
    ) -> None:
        """Initialize Modbus transport.

        Args:
            host: IP address or hostname of Modbus TCP gateway
            port: TCP port (default 502 for Modbus)
            unit_id: Modbus unit/slave ID (default 1)
            serial: Inverter serial number (for identification)
            timeout: Connection and operation timeout in seconds
            inverter_family: Inverter model family for correct register mapping.
                If None, defaults to EG4_HYBRID (18kPV, FlexBOSS) for backward
                compatibility. Use InverterFamily.LXP for Luxpower models.
            retries: Application-level retries per register read (default 2)
            retry_delay: Initial delay between retries in seconds, doubles each
                attempt (default 0.5)
            inter_register_delay: Delay between register group reads in seconds
                (default 0.05)
            pymodbus_retries: Number of retries passed to pymodbus client
                (default 3)
            max_input_block_size: Maximum registers per coalesced input-register
                read, 40..125 (default 40 = no coalescing, the plain per-group
                reads).  Larger values (multiples of 40 recommended; 120 is
                field-proven) consolidate adjacent register groups into fewer
                reads; hardware that rejects large reads automatically falls
                back to the plain grouped reads (eg4_web_monitor#254).
            register_observer: Optional callback for terminal raw-register segments.
            session_max_age: Maximum TCP session age in seconds before a
                proactive reconnect (default 3600), with deterministic per-
                transport jitter of plus or minus ten percent. None disables
                proactive recycling.
            backend: Wire backend: ``"pymodbus"`` (the historical default,
                carrying the gateway transaction-ID workaround),
                ``"modbus_connection"`` (Home Assistant's shared-connection
                library, tmodbus-based; requires the ``modbus-connection``
                extra), or ``"auto"`` (pymodbus for TCP).
            unit: A ``ModbusUnit``-shaped object supplied by a host — for
                example Home Assistant's ``async_get_unit()`` — that already
                addresses this inverter's unit ID over a shared link. The
                transport then performs no dialing, never closes the link,
                and heals a wedged link through the unit's ``disconnect()``.
                Mutually exclusive with ``backend="pymodbus"``.
        """
        super().__init__(
            serial,
            unit_id=unit_id,
            timeout=timeout,
            inverter_family=inverter_family,
            retries=retries,
            retry_delay=retry_delay,
            inter_register_delay=inter_register_delay,
            pymodbus_retries=pymodbus_retries,
            max_input_block_size=max_input_block_size,
            register_observer=register_observer,
            session_max_age=_jittered_session_max_age(
                session_max_age,
                host=host,
                port=port,
                unit_id=unit_id,
                serial=serial,
            ),
        )
        self._host = host
        self._port = port
        self._backend_setting = normalize_backend(backend)
        self._backend: ModbusBackend = resolve_backend(self._backend_setting)
        self._external_unit = unit
        if unit is not None:
            if self._backend_setting == "pymodbus":
                raise ValueError("An injected unit cannot be used with the pymodbus backend")
            self._backend = "modbus_connection"
        # Raw backend handle: pymodbus client, owned ModbusConnection, or the
        # injected unit. I/O goes through ``self._unit`` (see _modbus_base).
        self._client: AsyncModbusTcpClient | Any | None = None
        self._session_started_at: float | None = None
        self._reconnect_retry_after: float | None = None
        self._session_reconnect_count = 0
        # Adapters whose (possibly asynchronous) close is still settling;
        # disconnect()/async_shutdown() await them so a released endpoint is
        # really closed before a replacement dials.
        self._draining_units: list[RegisterClient] = []

    @property
    def capabilities(self) -> TransportCapabilities:
        """Get Modbus transport capabilities."""
        return MODBUS_CAPABILITIES

    @property
    def backend(self) -> ModbusBackend:
        """The wire backend this transport dials with."""
        return self._backend

    @property
    def host(self) -> str:
        """Get the Modbus gateway host."""
        return self._host

    @property
    def port(self) -> int:
        """Get the Modbus gateway port."""
        return self._port

    async def connect(self) -> None:
        """Establish a Modbus TCP connection under the operation lock.

        This is a no-op when already connected. Call :meth:`disconnect` first
        to force a fresh session.
        """
        async with self._op_lock:
            await self._connect_locked()

    async def _connect_locked(self) -> None:
        """Establish a connection while the caller owns the operation lock.

        Raises:
            TransportConnectionError: If connection fails
        """
        self._raise_if_shutdown()
        if self._connected:
            return
        self._drop_session()

        try:
            if self._external_unit is not None:
                self._attach_external_unit(self._external_unit)
            elif self._backend == "modbus_connection":
                await self._dial_modbus_connection()
            else:
                await self._dial_pymodbus()
        except asyncio.CancelledError:
            self._drop_session()
            self._reconnect_retry_after = _monotonic()
            raise
        except ImportError as err:
            hint = (
                "modbus-connection package not installed. "
                "Install with: uv add 'pylxpweb[modbus-connection]'"
                if self._backend == "modbus_connection"
                else "pymodbus package not installed. Install with: uv add pymodbus"
            )
            raise TransportConnectionError(hint) from err
        except (TimeoutError, OSError) as err:
            self._drop_session()
            self._reconnect_retry_after = _monotonic() + _FAILED_RECONNECT_COOLDOWN
            _LOGGER.error(
                "Failed to connect to Modbus gateway at %s:%s: %s",
                self._host,
                self._port,
                err,
            )
            raise TransportConnectionError(
                f"Failed to connect to {self._host}:{self._port}: {err}. "
                "Verify: (1) IP address is correct, (2) port 502 is not blocked, "
                "(3) Modbus TCP is enabled on the inverter/datalogger."
            ) from err

        self._connected = True
        self._consecutive_errors = 0
        self._session_started_at = _monotonic()
        self._reconnect_retry_after = None
        _LOGGER.info(
            "Modbus transport connected to %s:%s (unit %s, backend %s) for %s",
            self._host,
            self._port,
            self._unit_id,
            "shared" if self._external_unit is not None else self._backend,
            self._serial,
        )

    def _attach_external_unit(self, unit: ModbusUnitLike) -> None:
        """Adopt a host-supplied shared unit; no I/O by that library's contract."""
        self._client = unit
        self._unit = ModbusConnectionUnit(unit)

    async def _dial_modbus_connection(self) -> None:
        """Open an owned ``modbus_connection`` (tmodbus) link."""
        from modbus_connection import ModbusTcpParams
        from modbus_connection import exceptions as mc_exc
        from modbus_connection.tmodbus import ModbusConnection

        connection = ModbusConnection(
            ModbusTcpParams(host=self._host, port=self._port),
            timeout=self._timeout,
        )
        self._client = connection
        self._unit = ModbusConnectionUnit(connection.for_unit(self._unit_id), connection=connection)
        try:
            await connection.connect()
        except (mc_exc.ModbusError, TimeoutError, OSError) as err:
            self._drop_session()
            self._reconnect_retry_after = _monotonic() + _FAILED_RECONNECT_COOLDOWN
            _LOGGER.error(
                "Failed to connect to Modbus gateway at %s:%s: %s",
                self._host,
                self._port,
                err,
            )
            raise TransportConnectionError(
                f"Failed to connect to Modbus gateway at {self._host}:{self._port}: {err}"
            ) from err
        if self._shutdown_requested:
            self._drop_session()
        self._raise_if_shutdown()

    async def _dial_pymodbus(self) -> None:
        """Open an owned pymodbus TCP client (with the gateway TID workaround)."""
        # Import pymodbus here to make it optional
        from pymodbus.client import AsyncModbusTcpClient

        client = AsyncModbusTcpClient(
            host=self._host,
            port=self._port,
            timeout=self._timeout,
            retries=self._pymodbus_retries,
        )
        self._client = client
        self._unit = PymodbusUnit(client, self._unit_id)

        connected = await client.connect()
        if self._shutdown_requested:
            # pymodbus close() becomes a no-op after the first call sets
            # is_closing, even if the in-flight dial later installs a
            # transport. Reset its version-dependent owner so this close
            # reclaims that socket.
            closing_owner = _closing_state_owner(client)
            if closing_owner is not None:
                closing_owner.is_closing = False
            else:
                _LOGGER.debug(
                    "Unable to resolve pymodbus closing state for %s; attempting best-effort close",
                    type(client).__name__,
                )
            client.close()
        self._raise_if_shutdown()
        if not connected:
            self._drop_session()
            self._reconnect_retry_after = _monotonic() + _FAILED_RECONNECT_COOLDOWN
            raise TransportConnectionError(
                f"Failed to connect to Modbus gateway at {self._host}:{self._port}"
            )

        # Some "Modbus TCP to RTU" gateways were observed to use MBAP framing
        # on the TCP side without echoing the request's transaction ID.
        # Patch pymodbus to skip TID validation and suppress stale response
        # log spam (see patch_pymodbus_tid_validation).
        self._patch_tid_validation()

    def _patch_tid_validation(self) -> None:
        """Apply the gateway transaction-ID workaround to the pymodbus client."""
        if self._client is None:
            return
        patch_pymodbus_tid_validation(
            self._client,
            label=f"{self._host}:{self._port} ({self._serial})",
        )

    def _drop_session(self) -> None:
        """Release the client and forget it, marking the session as dead.

        Owned links close (pymodbus synchronously, modbus_connection in a
        background task that :meth:`disconnect` awaits); a host-shared unit
        is only detached, never closed.
        """
        unit = self._unit
        if unit is not None:
            unit.close()
            self._draining_units.append(unit)
        elif self._client is not None and self._external_unit is None:
            # A raw client that never got its adapter (defensive; the dial
            # paths install both together).
            close = getattr(self._client, "close", None)
            if callable(close):
                close()
        self._client = None
        self._unit = None
        self._connected = False
        self._session_started_at = None

    async def _drain_closes(self) -> None:
        """Await every pending adapter close (idempotent, cancellation-safe)."""
        while self._draining_units:
            unit = self._draining_units.pop(0)
            await unit.aclose()

    async def disconnect(self) -> None:
        """Close the Modbus TCP connection under the operation lock."""
        async with self._op_lock:
            self._drop_session()
            await self._drain_closes()
            self._reconnect_retry_after = None
            _LOGGER.debug("Modbus transport disconnected for %s", self._serial)

    async def async_shutdown(self) -> None:
        """Terminally close the session without waiting for the operation lock.

        The close itself is awaited, so a caller releasing this endpoint may
        dial a replacement immediately afterwards.
        """
        self._shutdown_requested = True
        self._drop_session()
        await self._drain_closes()
        _LOGGER.debug("Modbus transport shut down for %s", self._serial)

    def _raise_if_shutdown(self) -> None:
        """Reject connection creation after terminal shutdown."""
        if self._shutdown_requested:
            raise TransportConnectionError(
                f"Modbus transport for {self._serial} has been shut down"
            )

    async def _reconnect(self) -> None:
        """Reconnect Modbus client to reset transaction ID state.

        Called at operation boundaries for absent, failed, or over-age sessions.

        On a host-shared link only the error-recycle applies, and it goes
        through the unit's own ``disconnect()`` so the host's connection
        re-dials on the next request; the link's age and lifecycle are the
        host's, not this transport's.
        """
        async with self._lock:
            if self.backend_shares_link:
                if not self._shared_link_needs_recycle():
                    return
                self._session_reconnect_count += 1
                _LOGGER.warning(
                    "Recycling shared Modbus link for %s: reason=error-recycle errors=%d count=%d",
                    self._serial,
                    self._consecutive_errors,
                    self._session_reconnect_count,
                )
                await self._recycle_link()
                self._consecutive_errors = 0
                self._consecutive_link_errors = 0
                return

            now = _monotonic()
            if self._reconnect_retry_after is not None and now < self._reconnect_retry_after:
                remaining = self._reconnect_retry_after - now
                raise TransportConnectionError(
                    f"Modbus reconnect cooldown active for {self._serial} "
                    f"({remaining:.1f}s remaining)"
                )

            reason: str | None = None
            if self._consecutive_errors >= self._max_consecutive_errors:
                reason = "error-recycle"
            elif self._reconnect_retry_after is not None and not self._connected:
                reason = "disconnected-reconnect"
            elif (
                self._session_max_age is not None
                and self._session_started_at is not None
                and now - self._session_started_at >= self._session_max_age
            ):
                reason = "age-recycle"

            if reason is None:
                return

            self._session_reconnect_count += 1
            _LOGGER.log(
                logging.WARNING if reason == "error-recycle" else logging.INFO,
                "Reconnecting Modbus client for %s: reason=%s errors=%d count=%d",
                self._serial,
                reason,
                self._consecutive_errors,
                self._session_reconnect_count,
            )

            await self.disconnect()
            try:
                await self.connect()
            except TransportConnectionError:
                _LOGGER.warning(
                    "Modbus reconnect failed for %s: reason=%s count=%d",
                    self._serial,
                    reason,
                    self._session_reconnect_count,
                )
                self._reconnect_retry_after = _monotonic() + _FAILED_RECONNECT_COOLDOWN
                raise
