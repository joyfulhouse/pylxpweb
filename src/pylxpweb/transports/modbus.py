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
from typing import TYPE_CHECKING, Protocol, cast

from ._modbus_base import INPUT_REGISTER_GROUPS, BaseModbusTransport
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
        # Narrow type for TCP client
        self._client: AsyncModbusTcpClient | None = None
        self._session_started_at: float | None = None
        self._reconnect_retry_after: float | None = None
        self._session_reconnect_count = 0

    @property
    def capabilities(self) -> TransportCapabilities:
        """Get Modbus transport capabilities."""
        return MODBUS_CAPABILITIES

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
            # Import pymodbus here to make it optional
            from pymodbus.client import AsyncModbusTcpClient

            client = AsyncModbusTcpClient(
                host=self._host,
                port=self._port,
                timeout=self._timeout,
                retries=self._pymodbus_retries,
            )
            self._client = client

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
                        "Unable to resolve pymodbus closing state for %s; "
                        "attempting best-effort close",
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

            self._connected = True
            self._consecutive_errors = 0
            self._session_started_at = _monotonic()
            self._reconnect_retry_after = None

            # Waveshare "Modbus TCP to RTU" gateways use MBAP framing on
            # the TCP side but don't echo the request's transaction ID —
            # they substitute their own counter. Patch pymodbus to skip
            # TID validation and suppress stale response log spam.
            self._patch_tid_validation()

            _LOGGER.info(
                "Modbus transport connected to %s:%s (unit %s) for %s",
                self._host,
                self._port,
                self._unit_id,
                self._serial,
            )

        except asyncio.CancelledError:
            self._drop_session()
            self._reconnect_retry_after = _monotonic()
            raise
        except ImportError as err:
            raise TransportConnectionError(
                "pymodbus package not installed. Install with: uv add pymodbus"
            ) from err
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

    def _patch_tid_validation(self) -> None:
        """Disable MBAP transaction ID validation in pymodbus.

        Waveshare RS485-to-Ethernet gateways use MBAP framing on the TCP
        side but don't echo the request's transaction ID in responses --
        they use their own incrementing counter. This causes pymodbus to
        reject every response at two validation points:

        1. ``framer.handleFrame``: ``if exp_tid and tid != exp_tid``
        2. ``execute``: ``if response.transaction_id != request.transaction_id``

        We patch ``handleFrame`` to pass ``exp_tid=0`` (disabling check 1)
        and set the decoded PDU's TID to the expected value (fixing check 2).
        Stale responses arriving after a future is resolved are also
        silently dropped to prevent log spam.
        """
        if self._client is None:
            return

        ctx = getattr(self._client, "ctx", None)
        if ctx is None or not hasattr(ctx, "framer"):
            return

        framer = ctx.framer
        original_handle_frame = framer.handleFrame

        def _patched_handle_frame(
            data: bytes,
            exp_devid: int,
            exp_tid: int,
        ) -> tuple[int, object | None]:
            used_len, pdu = original_handle_frame(data, exp_devid, 0)
            if pdu is not None:
                # Drop stale responses whose future is already resolved.
                future = getattr(ctx, "response_future", None)
                if future is not None and future.done():
                    return used_len, None
                if exp_tid:
                    pdu.transaction_id = exp_tid
            return used_len, pdu

        framer.handleFrame = _patched_handle_frame
        _LOGGER.debug(
            "Patched TID validation for Modbus gateway %s:%s (%s)",
            self._host,
            self._port,
            self._serial,
        )

    def _drop_session(self) -> None:
        """Close and forget the client, marking the session as dead."""
        if self._client is not None:
            self._client.close()
            self._client = None
        self._connected = False
        self._session_started_at = None

    async def disconnect(self) -> None:
        """Close the Modbus TCP connection under the operation lock."""
        async with self._op_lock:
            self._drop_session()
            self._reconnect_retry_after = None
            _LOGGER.debug("Modbus transport disconnected for %s", self._serial)

    async def async_shutdown(self) -> None:
        """Terminally close the session without waiting for the operation lock."""
        self._shutdown_requested = True
        self._drop_session()
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
        """
        async with self._lock:
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
