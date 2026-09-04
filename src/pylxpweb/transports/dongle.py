"""WiFi Dongle TCP transport implementation.

This module provides the DongleTransport class for direct local
communication with inverters via the WiFi dongle's TCP interface
(typically port 8000).

The WiFi dongle uses a custom protocol that wraps Modbus RTU frames
in an 18-byte TCP header. This is NOT standard Modbus TCP - it uses
the LuxPower/EG4 proprietary protocol documented at:
https://github.com/celsworth/lxp-bridge/wiki/TCP-Packet-Spec

IMPORTANT: Single-Client Limitation
------------------------------------
The WiFi dongle sustains only ONE TCP client.  A second client is accepted
but repeatedly evicted, sees cross-routed replies, and degrades the first
client's poll cadence (live probe, pylxpweb#329).

Within one process this is handled for you: every DongleTransport that
targets the same physical dongle (host:port + dongle serial) shares ONE
serialized socket through an endpoint-scoped DongleChannel (see
``dongle_channel.py``), default-on.  Pass ``shared_channel=False`` for a
private socket.  Across processes the limitation still applies: disable
other integrations (Solar Assistant, lxp-bridge) before using.

IMPORTANT: Firmware Compatibility
---------------------------------
Recent firmware updates may block port 8000 access for security.
If connection fails, check if your dongle firmware has been updated.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import logging
import ssl
import struct
import sys
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, NoReturn

from ._register_data import (
    DEFAULT_INPUT_BLOCK_SIZE,
    RegisterDataMixin,
)
from .capabilities import DONGLE_CAPABILITIES, TransportCapabilities
from .dongle_channel import DongleChannel, make_channel_key, resolve_shared_channel
from .exceptions import (
    TransportConnectionError,
    TransportError,
    TransportReadError,
    TransportResponseMismatchError,
    TransportTimeoutError,
    TransportWriteError,
)
from .observation import RegisterObserver
from .protocol import LINK_PROBE_TIMEOUT_SECONDS, BaseTransport, _ReentrantAsyncLock

if TYPE_CHECKING:
    from pylxpweb.devices.inverters._features import InverterFamily

    from .data import BatteryBankData, InverterEnergyData, InverterRuntimeData, MidboxRuntimeData

_LOGGER = logging.getLogger(__name__)

# Protocol constants
PACKET_PREFIX = bytes([0xA1, 0x1A])  # Magic prefix for all packets
PROTOCOL_VERSION = 1  # Protocol version (little-endian uint16)
TCP_FUNC_HEARTBEAT = 0xC1  # Heartbeat/keepalive
TCP_FUNC_TRANSLATED = 0xC2  # Translated Modbus data
TCP_FUNC_READ_PARAM = 0xC3  # Read parameters
TCP_FUNC_WRITE_PARAM = 0xC4  # Write parameters

# Human-readable labels for TCP function bytes, used when rejecting a frame
# whose TCP function doesn't match the request's (misrouted/unsolicited).
_TCP_FUNC_NAMES = {
    TCP_FUNC_HEARTBEAT: "heartbeat",
    TCP_FUNC_TRANSLATED: "translated",
    TCP_FUNC_READ_PARAM: "read_param",
    TCP_FUNC_WRITE_PARAM: "write_param",
}

# Modbus function codes (embedded in TCP_FUNC_TRANSLATED)
MODBUS_READ_HOLDING = 0x03  # Read holding registers
MODBUS_READ_INPUT = 0x04  # Read input registers
MODBUS_WRITE_SINGLE = 0x06  # Write single holding register
MODBUS_WRITE_MULTI = 0x10  # Write multiple holding registers

# Default connection settings
DEFAULT_PORT = 8000
DEFAULT_TIMEOUT = 10.0
RECV_BUFFER_SIZE = 4096
_FRAME_HEADER_SIZE = 6
_FRAME_FIXED_FIELDS_SIZE = 14
_FRAME_CRC_SIZE = 2
_MIN_ADVERTISED_FRAME_LENGTH = _FRAME_FIXED_FIELDS_SIZE + _FRAME_CRC_SIZE
_MAX_PACKET_SIZE = RECV_BUFFER_SIZE
_MAX_PREFIX_SCAN_BYTES = RECV_BUFFER_SIZE
_SHUTDOWN_CLOSE_TIMEOUT = 0.25
_SSL_HANDSHAKE_TIMEOUT = 3.0
_SSL_UNSUPPORTED_TTL = 86400.0

# Write resilience settings (joyfulhouse/eg4_web_monitor#201)
# The dongle drops its TCP connection mid-sequence during parameter writes
# (firmware timeout / cloud-connection priority), so the read-modify-write
# cycle is retried at the sequence level with a fresh register read.
DEFAULT_WRITE_RETRIES = 2  # sequence-level retries (3 attempts total)
DEFAULT_WRITE_STEP_DELAY = 0.2  # settle delay before write/verify steps (s)
WRITE_RETRY_DELAY = 0.5  # base backoff between sequence attempts (s)
# Connect allowance on top of the probe response budget: covers the connect
# retry ladder for refused/unreachable endpoints without paying the full dial
# sequence (check_link outer bound).
_LINK_PROBE_CONNECT_GRACE_SECONDS = 3.0
VERIFY_MAX_REGISTERS = 3  # skip readback verification above this many registers


def compute_crc16(data: bytes) -> int:
    """Compute CRC-16/Modbus checksum.

    Args:
        data: Bytes to compute CRC for

    Returns:
        16-bit CRC value
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def _format_frame_fields(
    *,
    tcp_func: int | None = None,
    func: int | None = None,
    register: int | None = None,
    count: int | None = None,
) -> str:
    """Format the known fields of a request or response frame for logging.

    Fields left as ``None`` are omitted, so the same helper builds both the
    full "expected" block (the request knows everything) and the partial
    "received" block (a misrouted frame is only trusted for what parses).
    """
    parts: list[str] = []
    if tcp_func is not None:
        parts.append(f"tcp_func=0x{tcp_func:02x}")
    if func is not None:
        parts.append(f"func=0x{func:02x}")
    if register is not None:
        parts.append(f"register={register}")
    if count is not None:
        parts.append(f"count={count}")
    return " ".join(parts)


def _mismatch_context(expected: str, received: str) -> str:
    """Build a uniform ``expected [...], received [...]`` context block.

    Used for every cross-request validation failure so multi-device logs
    share one grep-able shape (joyfulhouse/pylxpweb#213).
    """
    return f"expected [{expected}], received [{received}]"


class _DongleFrameError(TransportReadError):
    """A stream-framing failure that makes the current socket unusable."""


class DongleTransport(RegisterDataMixin, BaseTransport):
    """WiFi Dongle TCP transport for local inverter communication.

    This transport connects directly to the inverter's WiFi dongle
    via TCP port 8000 using the LuxPower/EG4 proprietary protocol.

    The dongle sustains only ONE TCP client (see the module docstring), so
    transports in this process that target the same dongle share one
    serialized socket owned by a :class:`~.dongle_channel.DongleChannel`:
    ``connect()`` takes a lease, ``disconnect()`` / ``async_shutdown()``
    release it, and the last release closes the socket.

    Example:
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )
        await transport.connect()

        runtime = await transport.read_runtime()
        print(f"PV Power: {runtime.pv_total_power}W")

    Note:
        Unlike ModbusTransport, this does NOT require pymodbus.
        The protocol is implemented using pure asyncio sockets.
    """

    transport_type: str = "wifi_dongle"

    def __init__(
        self,
        host: str,
        dongle_serial: str,
        inverter_serial: str,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
        use_ssl: bool | None = None,
        inverter_family: InverterFamily | None = None,
        connection_retries: int = 3,
        write_retries: int = DEFAULT_WRITE_RETRIES,
        write_step_delay: float = DEFAULT_WRITE_STEP_DELAY,
        verify_writes: bool = True,
        max_input_block_size: int = DEFAULT_INPUT_BLOCK_SIZE,
        register_observer: RegisterObserver | None = None,
        *,
        shared_channel: bool = True,
    ) -> None:
        """Initialize WiFi Dongle transport.

        Args:
            host: IP address or hostname of the WiFi dongle
            dongle_serial: 10-character dongle serial number (e.g., "BA12345678")
            inverter_serial: 10-character inverter serial number (e.g., "CE12345678")
            port: TCP port (default 8000)
            timeout: Connection and operation timeout in seconds
            use_ssl: TLS-PSK policy: True forces TLS, False disables it, and
                None auto-detects support (default).

                SECURITY: the dongle's TLS-PSK uses a fixed key that is
                published in this source tree (and in the vendor firmware),
                mixed with the dongle serial — which is printed on the
                device and broadcast in plaintext frames — and performs no
                certificate validation. It hides register traffic from
                passive on-path observers ONLY: it does not authenticate
                the peer, does not resist an active man-in-the-middle, and
                the key cannot be rotated. Do not treat ``use_ssl=True`` as
                making the link trustworthy or the credentials secret.
            inverter_family: Inverter model family for correct register mapping.
                If None, defaults to PV_SERIES (EG4-18KPV) for backward
                compatibility.
            connection_retries: Number of connection retry attempts with backoff
            write_retries: Sequence-level retries for named parameter writes.
                On a connection drop mid read-modify-write, the transport
                reconnects, re-reads the register, and retries the write.
            write_step_delay: Settle delay (seconds) before write requests and
                verification reads.  Reduces connection pressure on dongles
                that drop the TCP link on rapid function-code changes.
            verify_writes: Read back written registers to confirm the values
                were applied (named parameter writes only, when cheap).
            max_input_block_size: Maximum registers per coalesced input-register
                read, 40..125 (default 40 = no coalescing, the plain per-group
                reads).  Larger values (multiples of 40 recommended; 120 is
                field-proven on DG dongle firmware 2.04-2.09) consolidate
                adjacent register groups into fewer reads; dongles that reject
                large reads automatically fall back to the plain grouped reads
                (eg4_web_monitor#254).
            register_observer: Optional callback for terminal raw-register segments.
            shared_channel: Share one serialized TCP socket with every other
                transport in this process that targets the same dongle
                (``host:port`` + ``dongle_serial``) — the default, because a
                dongle cannot sustain two clients (pylxpweb#329).  ``False``
                gives this transport a private socket that is never
                registered for sharing.  Per-operation knobs (timeouts, block
                size, write retries, family) stay per-transport either way;
                ``use_ssl`` and ``dongle_serial`` are per-socket facts and
                must agree across every transport sharing an endpoint.
        """
        # Per-socket state lives on the DongleChannel; the endpoint facts that
        # identify it must exist before BaseTransport.__init__ assigns the
        # forwarded ``_connected`` / ``_op_lock`` attributes.
        self._host = host
        self._port = port
        self._dongle_serial = dongle_serial
        self._ssl_mode = use_ssl
        self._shared_channel = shared_channel
        self._channel: DongleChannel | None = None
        super().__init__(inverter_serial, register_observer=register_observer)
        self._timeout = timeout
        self._inverter_family = inverter_family
        self._split_phase: bool = False
        self._pv_string_count: int = 3
        self._connection_retries = connection_retries
        self._inter_register_delay = 0.5  # Dongle needs slower pace than Modbus
        self._init_input_coalescing(max_input_block_size)
        self._write_retries = write_retries
        self._write_step_delay = write_step_delay
        self._verify_writes = verify_writes
        self._link_probe_active = False
        self._transaction_id = 0
        self._shutdown_requested = False

    @property
    def capabilities(self) -> TransportCapabilities:
        """Get capabilities for the dongle's serialized TCP connection."""
        return DONGLE_CAPABILITIES

    @property
    def host(self) -> str:
        """Get the dongle host address."""
        return self._host

    @property
    def port(self) -> int:
        """Get the dongle TCP port."""
        return self._port

    @property
    def dongle_serial(self) -> str:
        """Get the dongle serial number."""
        return self._dongle_serial

    @property
    def inverter_family(self) -> InverterFamily | None:
        """Get the inverter family for register mapping."""
        return self._inverter_family

    @inverter_family.setter
    def inverter_family(self, value: InverterFamily | None) -> None:
        """Set the inverter family for register mapping.

        This allows updating the family after auto-detection from device type code,
        ensuring the correct register map is used even if the initial family was
        wrong or defaulted.

        Args:
            value: The detected or configured inverter family
        """
        if value != self._inverter_family:
            _LOGGER.debug(
                "Updating inverter family from %s to %s for %s",
                self._inverter_family,
                value,
                self._serial,
            )
        self._inverter_family = value

    @property
    def split_phase(self) -> bool:
        """Whether this inverter uses split-phase (L1/L2) output."""
        return self._split_phase

    @split_phase.setter
    def split_phase(self, value: bool) -> None:
        """Set the split-phase flag for per-leg power fallback."""
        self._split_phase = value

    @property
    def pv_string_count(self) -> int:
        """Number of PV (MPPT) strings the inverter model exposes (0..n)."""
        return self._pv_string_count

    @pv_string_count.setter
    def pv_string_count(self, value: int) -> None:
        """Set the PV string count (gates pv4-6 register reads/parsing)."""
        self._pv_string_count = int(value)

    # ------------------------------------------------------------------
    # Channel binding (pylxpweb#329)
    # ------------------------------------------------------------------
    # Everything per-socket lives on the DongleChannel; the ``_reader`` /
    # ``_writer`` / ``_connected`` / ``_lock`` / ``_connect_lock`` /
    # ``_op_lock`` / ``_ssl_*`` / ``_receive_buffer`` accessors below forward
    # to it so the channel stays the single owner of that state.

    @property
    def channel(self) -> DongleChannel | None:
        """The channel this transport is bound to (``None`` before first use)."""
        return self._channel

    def _resolve_channel(self) -> DongleChannel:
        """Bind to the live channel for this endpoint, creating it if needed.

        Never suspends, so the registry's check-then-create is atomic on the
        loop.  A transport re-resolves when its channel was retired (last
        lease released) or its endpoint changed; a private
        (``shared_channel=False``) channel is created once and never
        registered.

        Raises:
            DongleChannelMismatchError: The endpoint already has a channel
                with a different ``use_ssl`` or ``dongle_serial``.
            DongleChannelLoopError: The endpoint's channel belongs to a
                different running event loop.
        """
        channel = self._channel
        key = make_channel_key(self._host, self._port, self._dongle_serial)
        if not self._shared_channel:
            if channel is None or channel.loop_is_dead():
                channel = DongleChannel(key, ssl_mode=self._ssl_mode, shared=False)
                self._channel = channel
            channel.bind_loop()
            return channel
        if (
            channel is not None
            and not channel.retired
            and channel.key == key
            and not channel.loop_is_dead()
        ):
            channel.bind_loop()
            return channel
        channel = resolve_shared_channel(key, ssl_mode=self._ssl_mode)
        self._channel = channel
        return channel

    @contextlib.asynccontextmanager
    async def _operation(self) -> AsyncIterator[None]:
        """Serialise one multi-step operation on the channel's operation lock.

        Binding happens here, *before* the lock is awaited, and the caller is
        counted as a channel user from that point, so an operation runs
        start-to-finish on one channel.  Like ``connect()``, the channel is
        re-checked once the lock is held and re-resolved if it was retired
        or its loop died in the meantime.
        """
        while True:
            channel = self._resolve_channel()
            async with channel.operation():
                if channel.retired or channel.loop_is_dead():
                    continue
                yield
                return

    @contextlib.asynccontextmanager
    async def _transaction(self) -> AsyncIterator[DongleChannel]:
        """Hold the channel transaction lock as its owner (same re-check as above)."""
        while True:
            channel = self._resolve_channel()
            async with channel.transaction(self):
                if channel.retired or channel.loop_is_dead():
                    continue
                yield channel
                return

    @property
    def is_connected(self) -> bool:
        """Whether THIS transport holds a lease on a live shared socket.

        A sibling's live socket does not make an un-leased transport
        connected: callers that gate ``connect()`` on this property must take
        their own lease, or the last leased sibling's release would close the
        socket underneath them.  A terminally shut-down transport is never
        connected.
        """
        channel = self._channel
        return (
            not self._shutdown_requested
            and channel is not None
            and channel.connected
            and channel.holds_lease(self)
        )

    @property
    def _connected(self) -> bool:
        channel = self._channel
        return channel is not None and channel.connected

    @_connected.setter
    def _connected(self, value: bool) -> None:
        # BaseTransport.__init__ assigns False before any channel exists; an
        # unbound transport is not connected, so that assignment is a no-op.
        # This seam only flips the channel's socket-live flag; it never
        # touches the lease set (leases change in connect(), disconnect()
        # and async_shutdown() only).
        if value:
            self._resolve_channel().connected = True
        elif self._channel is not None:
            self._channel.connected = False

    @property
    def _op_lock(self) -> _ReentrantAsyncLock:
        return self._resolve_channel().op_lock

    @_op_lock.setter
    def _op_lock(self, _value: _ReentrantAsyncLock) -> None:
        # BaseTransport.__init__ installs a per-instance lock; the dongle
        # serialises operations per channel instead, so it is not kept.
        return

    @property
    def _lock(self) -> asyncio.Lock:
        return self._resolve_channel().transaction_lock

    @property
    def _connect_lock(self) -> asyncio.Lock:
        return self._resolve_channel().connect_lock

    @property
    def _reader(self) -> asyncio.StreamReader | None:
        channel = self._channel
        return channel.reader if channel is not None else None

    @_reader.setter
    def _reader(self, value: asyncio.StreamReader | None) -> None:
        if value is None and self._channel is None:
            return
        self._resolve_channel().reader = value

    @property
    def _writer(self) -> asyncio.StreamWriter | None:
        channel = self._channel
        return channel.writer if channel is not None else None

    @_writer.setter
    def _writer(self, value: asyncio.StreamWriter | None) -> None:
        if value is None and self._channel is None:
            return
        self._resolve_channel().writer = value

    @property
    def _receive_buffer(self) -> bytearray:
        return self._resolve_channel().receive_buffer

    @property
    def _ssl_active(self) -> bool:
        return self._resolve_channel().ssl_active

    @_ssl_active.setter
    def _ssl_active(self, value: bool) -> None:
        self._resolve_channel().ssl_active = value

    @property
    def _ssl_proven(self) -> bool:
        return self._resolve_channel().ssl_proven

    @_ssl_proven.setter
    def _ssl_proven(self, value: bool) -> None:
        self._resolve_channel().ssl_proven = value

    @property
    def _ssl_unsupported_until(self) -> float | None:
        return self._resolve_channel().ssl_unsupported_until

    @_ssl_unsupported_until.setter
    def _ssl_unsupported_until(self, value: float | None) -> None:
        self._resolve_channel().ssl_unsupported_until = value

    @property
    def _ssl_unavailable_logged(self) -> bool:
        return self._resolve_channel().ssl_unavailable_logged

    @_ssl_unavailable_logged.setter
    def _ssl_unavailable_logged(self, value: bool) -> None:
        self._resolve_channel().ssl_unavailable_logged = value

    async def _discard_initial_data(self) -> None:
        """Discard any initial data sent by the dongle after connection.

        Some dongles send unsolicited packets immediately after connection.
        This data must be discarded to avoid confusing subsequent protocol
        exchanges. We wait up to 1 second for any initial data.

        Raises:
            ConnectionResetError: If the dongle closed the connection during
                the initial-data window (``read`` returned EOF).  Treated as
                a failed connect attempt so the retry/backoff cycle dials
                again — typically the dongle's single client slot was still
                held by a previous session (codex review: without this,
                ``connect()`` declared an accept-then-close socket usable).
        """
        if not self._reader:
            return

        try:
            # Wait up to 1 second for any initial data and discard it
            initial_data = await asyncio.wait_for(
                self._reader.read(512),
                timeout=1.0,
            )
        except TimeoutError:
            # No initial data - this is fine
            _LOGGER.debug("No initial data from dongle (expected for some models)")
            return

        if not initial_data:
            # read(n>0) returns b'' only at EOF: the dongle accepted the
            # TCP connection and immediately closed it.
            raise ConnectionResetError(
                "Dongle closed the connection during the initial-data window"
            )

        _LOGGER.debug(
            "Discarded %d bytes of initial data from dongle: %s",
            len(initial_data),
            initial_data.hex()[:100],  # Log first 50 bytes
        )

    def _ssl_ctx(self) -> ssl.SSLContext | None:
        """Create the SSL context for TLS-PSK encrypted channels.

        Security: the PSK uses the fixed, source-committed key
        ``4c7578506f77657254656b21`` HMAC'd with the non-secret dongle serial,
        which is printed on the device and broadcast in plaintext frames.
        With ``CERT_NONE`` and no certificate validation, this provides only
        confidentiality from passive on-path observers; it does not
        authenticate the peer or resist an active MITM.
        """

        if self._ssl_mode is False:
            return None

        if sys.version_info < (3, 13) or not getattr(ssl, "HAS_PSK", False):
            # ssl.SSLContext.set_psk_client_callback requires Python 3.13+
            # (ssl.HAS_PSK) and an OpenSSL build with PSK support; the
            # version check also lets mypy see the 3.13-only API below.
            if self._ssl_mode is True:
                raise NotImplementedError("SSL was requested but PSK support is missing")
            if not self._ssl_unavailable_logged:
                _LOGGER.debug("TLS-PSK auto-detection skipped: Python lacks PSK support")
                self._ssl_unavailable_logged = True
            return None

        # Compute PSK from the key and the dongle serial
        psk = hmac.digest(
            bytes.fromhex("4c7578506f77657254656b21"),
            self._dongle_serial.encode("utf-8"),
            digest=hashlib.sha256,
        )

        def get_psk(_hint: str | None) -> tuple[str, bytes]:
            # Only the first 16 bytes are used for the PSK
            return ("Client_identity", psk[:16])

        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        # PSK client callbacks only apply to TLS <= 1.2 (CPython docs), so a
        # TLS 1.3 negotiation would bypass the PSK entirely — cap it.
        ssl_ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        ssl_ctx.options |= ssl.OP_NO_TLSv1
        ssl_ctx.options |= ssl.OP_NO_TLSv1_1
        ssl_ctx.set_psk_client_callback(get_psk)
        ssl_ctx.set_ciphers("DHE-PSK-AES128-GCM-SHA256")

        return ssl_ctx

    def _auto_ssl_context(self) -> ssl.SSLContext | None:
        """Return a probe context unless AUTO has a cached negative verdict."""
        if self._ssl_mode is None:
            if self._link_probe_active and not self._ssl_proven:
                # The cheap link-down probe (check_link) runs on a ~5s
                # budget: never spend it TLS-probing an undetermined
                # channel.  Reuse the last-known state — plaintext until
                # TLS has proven — and let a real connect() resolve
                # capability under its full budget.
                return None
            if (
                self._ssl_unsupported_until is not None
                and time.monotonic() < self._ssl_unsupported_until
            ):
                return None
        return self._ssl_ctx()

    async def _open_connection(
        self, ssl_context: ssl.SSLContext | None
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Dial once, applying the short timeout only to TLS handshakes."""
        kwargs: dict[str, Any] = {}
        if ssl_context is not None:
            kwargs = {
                "ssl": ssl_context,
                "ssl_handshake_timeout": min(self._timeout, _SSL_HANDSHAKE_TIMEOUT),
            }
        return await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port, **kwargs),
            timeout=self._timeout,
        )

    async def connect(self) -> None:
        """Take a lease on the endpoint's channel, dialing it if nobody has.

        The dongle only allows one TCP connection at a time. If connection fails,
        retries with exponential backoff (1s, 2s, 4s, ...) to handle cases where
        a previous connection wasn't properly released.

        State guarantee: the channel is marked connected only after the socket
        is fully usable (open AND initial data discarded).  Every failure
        path — including a partially-succeeded attempt where the socket
        opened but the initial-data read errored — tears the connection
        down, so connect() can never exit connected on a dead socket (#226
        state-corruption guard).

        Concurrency: the dial runs behind the channel's connection lock with
        a re-check after acquire (the dongle has ONE TCP slot — two parallel
        dials corrupt each other).  A caller that lost the race to another
        lease's successful connect just takes its lease and returns.

        Leases: idempotent per transport — the lease is recorded once the
        channel is usable, so a failed connect leaves none behind.

        Raises:
            TransportConnectionError: If all connection attempts fail
            DongleChannelMismatchError: Another transport already holds this
                endpoint with a different ``use_ssl`` or ``dongle_serial``.
        """
        self._raise_if_shutdown()
        while True:
            channel = self._resolve_channel()
            try:
                channel.connect_waiters.append(self)
                acquired = False
                try:
                    async with channel.connect_lock:
                        channel.connect_waiters.remove(self)
                        acquired = True
                        channel.connect_owner = self
                        try:
                            self._raise_if_shutdown()
                            if channel.retired:
                                # The last lease released between resolve and
                                # acquire: re-resolve to the live channel.
                                continue
                            if not channel.connected:
                                await self._dial(channel)
                            channel.acquire_lease(self)
                            return
                        finally:
                            channel.connect_owner = None
                finally:
                    if not acquired:
                        # Cancelled (or shut down) while queued for the lock.
                        channel.connect_waiters.remove(self)
            except BaseException:
                # A failed (or cancelled / shut-down) dial must not leave a
                # disconnected, lease-less channel registered: it would
                # answer every later resolve for this endpoint and turn a
                # transient dial failure into config lock-in (mismatch
                # errors from a channel nobody uses).
                channel.retire_if_idle()
                raise

    async def _dial(self, channel: DongleChannel) -> None:
        """Run the connect ladder into ``channel``; caller holds its connect lock."""
        last_error: Exception | None = None
        retry_delay = 1.0  # Start with 1 second delay

        # Clean slate: drop any stale half-open socket from a previous
        # session before dialing a new one (the dongle has ONE TCP slot).
        await channel.close()

        for attempt in range(self._connection_retries):
            self._raise_if_shutdown()
            try:
                if attempt > 0:
                    _LOGGER.info(
                        "Connection retry %d/%d to %s:%s (waiting %.1fs)...",
                        attempt,
                        self._connection_retries - 1,
                        self._host,
                        self._port,
                        retry_delay,
                    )
                    await asyncio.sleep(retry_delay)
                    # Shutdown may arrive while this task is parked in the
                    # retry backoff. Never start a new TCP dial afterward.
                    self._raise_if_shutdown()
                    retry_delay *= 2  # Exponential backoff

                using_ssl = False
                ssl_context = self._auto_ssl_context()
                while True:
                    using_ssl = ssl_context is not None
                    try:
                        channel.reader, channel.writer = await self._open_connection(ssl_context)
                        if self._shutdown_requested:
                            await channel.close()
                            self._raise_if_shutdown()

                        # The first read can surface a deferred TLS error,
                        # so it is part of capability detection.
                        await self._discard_initial_data()
                        break
                    except ssl.SSLError:
                        await channel.close()
                        if not using_ssl:
                            # An SSLError off a plaintext socket is not
                            # TLS capability evidence — ordinary failure.
                            raise
                        if self._ssl_mode is not None or channel.ssl_proven:
                            # Forced TLS fails fast (outer handler wraps
                            # it); a proven-TLS instance retries TLS-only
                            # on the outer ladder — neither ever falls
                            # back to plaintext.
                            raise
                        # First AUTO probe: a rejected handshake is a
                        # definitive negative — plaintext for the rest of
                        # this attempt, cached for future connects (the
                        # TTL re-probe also picks up a later firmware
                        # upgrade that adds TLS). Every other probe
                        # failure — timeout, abort, reset, refused — is
                        # inconclusive and propagates to the outer retry
                        # ladder uncached: never treat a disrupted
                        # handshake as capability evidence, or an on-path
                        # attacker could force a plaintext downgrade by
                        # stalling it.
                        channel.ssl_unsupported_until = time.monotonic() + _SSL_UNSUPPORTED_TTL
                        _LOGGER.info(
                            "Dongle/firmware does not support TLS-PSK on port %s; "
                            "will retry SSL detection in 24h",
                            self._port,
                        )
                        ssl_context = None
                self._raise_if_shutdown()

                channel.ssl_active = using_ssl
                if using_ssl:
                    channel.ssl_proven = True
                    channel.ssl_unsupported_until = None
                elif (
                    self._link_probe_active
                    and self._ssl_mode is None
                    and not channel.ssl_proven
                    and channel.ssl_unsupported_until is None
                ):
                    # A link probe forced this plaintext dial before TLS
                    # auto-detection ever ran; the connection may be kept
                    # past the health check, so leave a trail. Detection
                    # runs on the next fresh (non-probe) dial.
                    _LOGGER.info(
                        "Link probe connected to %s:%s in plaintext before TLS "
                        "auto-detection ran; TLS will be probed on the next "
                        "fresh connection",
                        self._host,
                        self._port,
                    )
                channel.connected = True
                _LOGGER.info(
                    "Dongle transport connected to %s:%s (dongle=%s, inverter=%s)%s",
                    self._host,
                    self._port,
                    self._dongle_serial,
                    self._serial,
                    f" after {attempt} retries" if attempt > 0 else "",
                )
                return  # Success!

            except ssl.SSLError as err:
                last_error = err
                await channel.close()
                self._raise_if_shutdown()
                if using_ssl and self._ssl_mode is True:
                    # Forced TLS: a handshake rejection is deterministic —
                    # fail fast, wrapped to connect()'s documented type.
                    raise TransportConnectionError(
                        f"TLS connection to {self._host}:{self._port} failed: {err}"
                    ) from err
                if using_ssl:
                    # Proven-TLS regression: retry TLS-only on the ladder,
                    # never falling back to plaintext; exhaustion wraps in
                    # TransportConnectionError below.
                    _LOGGER.warning(
                        "TLS regression on %s:%s (previously negotiated "
                        "successfully): %s — retrying TLS, never plaintext "
                        "(attempt %d/%d)",
                        self._host,
                        self._port,
                        err,
                        attempt + 1,
                        self._connection_retries,
                    )
                else:
                    _LOGGER.warning(
                        "Connection failed to %s:%s: %s (attempt %d/%d)",
                        self._host,
                        self._port,
                        err,
                        attempt + 1,
                        self._connection_retries,
                    )
            except TimeoutError as err:
                last_error = err
                await channel.close()
                self._raise_if_shutdown()
                _LOGGER.warning(
                    "Timeout connecting to dongle at %s:%s (attempt %d/%d)",
                    self._host,
                    self._port,
                    attempt + 1,
                    self._connection_retries,
                )
            except OSError as err:
                last_error = err
                await channel.close()
                self._raise_if_shutdown()
                _LOGGER.warning(
                    "Connection failed to %s:%s: %s (attempt %d/%d)",
                    self._host,
                    self._port,
                    err,
                    attempt + 1,
                    self._connection_retries,
                )
            except BaseException:
                # CancelledError (or any unexpected error) raised between
                # installing the reader/writer and setting _connected would
                # otherwise leave an orphaned open socket occupying the
                # dongle's single TCP slot — invisible to later cleanup
                # because _connected stays False. Close before propagating;
                # shutdown-triggered TransportConnectionError takes the
                # same path (an extra close on an already-closed socket is
                # a no-op).
                await channel.close()
                raise

        # All retries exhausted
        await channel.close()
        if isinstance(last_error, TimeoutError):
            raise TransportConnectionError(
                f"Timeout connecting to {self._host}:{self._port} after "
                f"{self._connection_retries} attempts. "
                "Verify: (1) IP address is correct, (2) dongle is on network, "
                "(3) port 8000 is not blocked by firmware."
            ) from last_error
        else:
            raise TransportConnectionError(
                f"Failed to connect to {self._host}:{self._port} after "
                f"{self._connection_retries} attempts: {last_error}. "
                "Verify: (1) IP address is correct, (2) dongle is accessible, "
                "(3) no other client is connected (dongle allows only ONE connection)."
            ) from last_error

    async def disconnect(self) -> None:
        """Release this transport's lease; close the socket if it was the last.

        Serialises with in-flight transactions and connection lifecycle
        changes.  If a connect is already establishing a socket, disconnect
        waits and closes that result; if disconnect starts first, a later
        connect waits until the old socket is fully closed before dialing.
        While sibling leases remain the shared socket stays open for them.
        Idempotent: a second call releases nothing.
        """
        channel = self._channel
        if channel is not None:
            async with channel.transaction_lock:
                channel.release_lease(self)
                if channel.lease_count == 0:
                    async with channel.connect_lock:
                        # A dial that was in flight has finished by now and
                        # leased its caller.  If that caller was THIS
                        # transport (connect() racing this disconnect),
                        # disconnect wins: drop that lease and close.  If it
                        # was a sibling, the socket is theirs — leave it.
                        channel.release_lease(self)
                        if channel.lease_count == 0:
                            await channel.close()
            channel.retire_if_idle()
        _LOGGER.debug("Dongle transport disconnected for %s", self._serial)

    async def async_shutdown(self) -> None:
        """Terminally release this transport without waiting for a held transaction lock.

        Home Assistant unloads must close the stream before cancelling the task
        that owns the transaction lock; otherwise a muted dongle can hold
        shutdown behind the full response timeout.  This method is
        deliberately terminal and bounded (``min(timeout, 0.25s)`` on the
        close): it marks the transport first, releases its lease, and makes an
        in-flight or later ``connect()`` close its result instead of
        resurrecting the socket.  Retry and I/O boundaries re-check the
        terminal flag after awaited backoffs, drains, writes, and reads, so
        shutdown does not permit another dial or sequence retry.

        Shared socket: the stream is torn down (generation bumped, siblings'
        next transaction reconnects) only when THIS transport owns the active
        dial, or owns the in-flight transaction while no sibling holds or is
        queued for the connect lock (then under that lock, held through the
        bounded close), or when nothing is in flight, no lease remains and no
        sibling is dialing.  If a sibling owns the in-flight
        transaction, holds the connect lock, or is queued for it, this lease
        is just released and the socket (or the dongle's single slot) is
        theirs — shutdown never blocks behind a sibling's dial.  Owning the
        transaction is not owning the dial: this transport's inner
        ``connect()`` can be queued behind a sibling's dial, and that
        sibling's fresh socket must survive.  Either close under the connect
        lock happens only when the lock is provably uncontended, which needs
        two checks: the owner/waiter bookkeeping (it covers ``connect()``,
        including a woken waiter that will capture the lock even while
        ``locked()`` reads False) AND ``locked()`` itself (it covers every
        other holder — ``teardown()`` / ``disconnect()`` closing the stream
        with an ordinary 5 s bound).  If either says otherwise the lease is
        released and shutdown returns at once: the stream is already being
        closed (or the slot is a sibling's), and the terminal flag interrupts
        this transport at its next ``_raise_if_shutdown()``.  Held through
        the bounded ``wait_closed()``, the lock orders any later dial after
        the old socket has actually gone.
        Ordinary reusable disconnects retain the fully serialised
        :meth:`disconnect` contract.
        """
        self._shutdown_requested = True
        channel = self._channel
        if channel is not None:
            channel.release_lease(self)
            owner = channel.transaction_owner
            close_timeout = min(self._timeout, _SHUTDOWN_CLOSE_TIMEOUT)
            if channel.connect_owner is self:
                # Interrupt this transport's own active dial: lock-free on
                # purpose (the lock is held by the very task being unblocked;
                # its post-open terminal check closes whatever it opens).
                await channel.close(timeout=close_timeout)
            elif owner is self:
                # Interrupt this transport's own in-flight transaction —
                # unless a sibling holds or is queued for the connect lock,
                # in which case the stream is (or is about to be) theirs and
                # our queued connect() raises on resume instead.
                # With no sibling holding or queued, the connect lock is
                # taken and held through the bounded close so a sibling that
                # sees the stream go down cannot dial before the old socket
                # is gone; the only possible waiter is our own queued
                # connect(), which raises on resume within one loop turn.
                # Owner/waiter bookkeeping only covers connect(); teardown()
                # and disconnect() hold the lock without it, with an ordinary
                # (up to 5 s) close inside — so locked() is checked too.  If
                # they hold it, the stream is already being closed: release
                # the lease and return without waiting; the terminal flag
                # interrupts this transport at its next _raise_if_shutdown().
                # If this transport's OWN connect() is the queued waiter there
                # is no in-flight I/O on the stream to interrupt (it raises on
                # resume) — and the live stream belongs to whoever just
                # finished dialing, so it must not be closed either.
                if (
                    not channel.sibling_dialing(self)
                    and self not in channel.connect_waiters
                    and not channel.connect_lock.locked()
                ):
                    async with channel.connect_lock:
                        await channel.close(timeout=close_timeout)
            elif (
                owner is None
                and channel.lease_count == 0
                and channel.connect_owner is None
                and not channel.connect_waiters
                and not channel.connect_lock.locked()
            ):
                # Last lease, nothing in flight, no dialer, no queued dialer
                # and no other holder (a sibling's disconnect() or teardown()
                # closing the stream): the connect lock is genuinely
                # uncontended, so the acquire below cannot suspend.  Holding
                # it across the bounded close orders any later dial after the
                # old socket has actually gone; the re-check guards a future
                # suspension point, not a live race.  When another holder is
                # closing, this lease is released and the closer's own exit
                # retires the channel.
                async with channel.connect_lock:
                    if channel.lease_count == 0 and channel.transaction_owner is None:
                        await channel.close(timeout=close_timeout)
            channel.retire_if_idle()
        _LOGGER.debug("Dongle transport shut down for %s", self._serial)

    def _raise_if_shutdown(self) -> None:
        """Reject socket creation or use after terminal shutdown."""
        if self._shutdown_requested:
            raise TransportConnectionError(
                f"Dongle transport for {self._serial} has been shut down"
            )

    def _build_packet(
        self,
        tcp_func: int,
        modbus_func: int,
        start_register: int,
        register_count: int = 0,
        values: list[int] | None = None,
    ) -> bytes:
        """Build a LuxPower protocol packet.

        Packet structure (38 bytes for read, varies for write):
        - Bytes 0-1: Prefix (0xA1, 0x1A)
        - Bytes 2-3: Protocol version (1, little-endian)
        - Bytes 4-5: Frame length (little-endian)
        - Byte 6: Address (0x01)
        - Byte 7: TCP function code
        - Bytes 8-17: Dongle serial (10 bytes ASCII)
        - Bytes 18-19: Data length (little-endian)
        - Bytes 20+: Data frame (16+ bytes)
        - Last 2 bytes: CRC-16 of data frame

        Args:
            tcp_func: TCP function code (0xC2 for translated Modbus)
            modbus_func: Modbus function code (0x03, 0x04, 0x06, 0x10)
            start_register: Starting register address
            register_count: Number of registers (for read operations)
            values: Values to write (for write operations)

        Returns:
            Complete packet bytes
        """
        # Encode serial numbers as bytes
        dongle_bytes = self._dongle_serial.encode("ascii").ljust(10, b"\x00")[:10]
        inverter_bytes = self._serial.encode("ascii").ljust(10, b"\x00")[:10]

        # Build data frame (varies by operation)
        if modbus_func == MODBUS_WRITE_SINGLE:
            # Write single: action(1) + func(1) + serial(10) + reg(2) + value(2)
            # action=0x00 for request (client to inverter), 0x01 for response
            value = values[0] if values else 0
            data_frame = bytes([0x00, modbus_func]) + inverter_bytes
            data_frame += struct.pack("<H", start_register)
            data_frame += struct.pack("<H", value)
        elif modbus_func == MODBUS_WRITE_MULTI:
            # Write multi: action(1) + func(1) + serial(10) + reg(2) + count(2) + bytes(1) + data
            # action=0x00 for request (client to inverter), 0x01 for response
            data_count = len(values) if values else 0
            byte_count = data_count * 2
            data_frame = bytes([0x00, modbus_func]) + inverter_bytes
            data_frame += struct.pack("<H", start_register)
            data_frame += struct.pack("<H", data_count)
            data_frame += bytes([byte_count])
            for value in values or []:
                data_frame += struct.pack("<H", value)
        else:
            # Read: action(1) + func(1) + serial(10) + reg(2) + count(2)
            # action=0x00 for request (client to inverter), 0x01 for response
            data_frame = bytes([0x00, modbus_func]) + inverter_bytes
            data_frame += struct.pack("<H", start_register)
            data_frame += struct.pack("<H", register_count)

        # Calculate CRC of data frame
        crc = compute_crc16(data_frame)

        # Build complete packet
        # data_length = data_frame bytes + CRC (2 bytes)
        data_length = len(data_frame) + 2
        # frame_length = bytes after the frame_length field itself
        # = addr(1) + tcp_func(1) + dongle(10) + data_length(2) + data_frame + crc
        # = 14 + data_length
        frame_length = 14 + data_length

        packet = PACKET_PREFIX
        packet += struct.pack("<H", PROTOCOL_VERSION)
        packet += struct.pack("<H", frame_length)
        packet += bytes([0x01, tcp_func])
        packet += dongle_bytes
        packet += struct.pack("<H", data_length)
        packet += data_frame
        packet += struct.pack("<H", crc)

        return packet

    async def _drain_buffer(self) -> None:
        """Drain any pending data from the receive buffer.

        The dongle may send unsolicited heartbeat packets or there may be
        stale data from previous requests. This method clears the buffer
        before sending a new request to ensure clean communication.
        """
        # Any bytes retained after extracting a previous frame are stale at
        # this request boundary (typically an unsolicited heartbeat or a
        # coalesced late reply), just like bytes waiting in StreamReader.
        self._receive_buffer.clear()

        if not self._reader:
            return

        try:
            # Non-blocking read to drain any pending data
            while True:
                try:
                    # Very short timeout - just check if data is available
                    junk = await asyncio.wait_for(
                        self._reader.read(512),
                        timeout=0.05,  # 50ms - just check for immediate data
                    )
                    if not junk:
                        break
                    _LOGGER.debug(
                        "Drained %d bytes of pending data: %s",
                        len(junk),
                        junk.hex()[:50],
                    )
                except TimeoutError:
                    # No pending data - good!
                    break
        except Exception as err:
            _LOGGER.debug("Error draining buffer: %s", err)

    async def _receive_frame(self) -> bytes:
        """Read one complete packet from the TCP byte stream.

        TCP reads do not preserve protocol-message boundaries: the two-byte
        prefix, six-byte outer header, and body may all arrive separately.
        Locate the prefix with a bounded junk scan, validate the advertised
        packet size before reading its body, and retain any over-read bytes
        for the next request-boundary drain.

        The caller owns the single overall response timeout.  This helper
        deliberately does not start a new timeout per fragment.
        """
        reader = self._reader
        if reader is None:
            raise TransportConnectionError("Socket not initialized")

        discarded = 0

        async def read_more(expected_size: int | None = None) -> None:
            chunk = await reader.read(RECV_BUFFER_SIZE)
            if chunk:
                self._receive_buffer.extend(chunk)
                return

            if not self._receive_buffer and discarded == 0:
                raise _DongleFrameError(
                    f"[{self._serial}] Empty response from dongle. This may indicate: "
                    "(1) Dongle firmware is blocking local Modbus access, "
                    "(2) Connection was closed by dongle, or "
                    "(3) Dongle requires more time to respond. "
                    "Try increasing timeout or check dongle firmware version."
                )

            expected = f" of {expected_size} advertised bytes" if expected_size is not None else ""
            raise _DongleFrameError(
                f"[{self._serial}] Connection closed before complete frame: "
                f"received {len(self._receive_buffer)} bytes{expected}"
            )

        # Locate a prefix without allowing a peer to grow the retained junk
        # indefinitely.  Preserve one trailing 0xA1 because the 0xA1 0x1A
        # prefix itself may straddle two TCP reads.
        while True:
            packet_start = self._receive_buffer.find(PACKET_PREFIX)
            if packet_start >= 0:
                if packet_start:
                    discarded += packet_start
                    if discarded > _MAX_PREFIX_SCAN_BYTES:
                        raise _DongleFrameError(
                            f"[{self._serial}] Packet prefix scan exceeded "
                            f"{_MAX_PREFIX_SCAN_BYTES} bytes"
                        )
                    _LOGGER.debug(
                        "Found packet start after discarding %d bytes of junk data",
                        discarded,
                    )
                    del self._receive_buffer[:packet_start]
                break

            preserve = int(
                bool(self._receive_buffer) and self._receive_buffer[-1] == PACKET_PREFIX[0]
            )
            junk_size = len(self._receive_buffer) - preserve
            if junk_size:
                discarded += junk_size
                if discarded > _MAX_PREFIX_SCAN_BYTES:
                    raise _DongleFrameError(
                        f"[{self._serial}] Packet prefix scan exceeded "
                        f"{_MAX_PREFIX_SCAN_BYTES} bytes"
                    )
                del self._receive_buffer[:junk_size]
            await read_more()

        while len(self._receive_buffer) < _FRAME_HEADER_SIZE:
            await read_more()

        advertised_length = struct.unpack("<H", self._receive_buffer[4:6])[0]
        if advertised_length < _MIN_ADVERTISED_FRAME_LENGTH:
            raise _DongleFrameError(
                f"[{self._serial}] Invalid advertised frame length "
                f"{advertised_length}; minimum is {_MIN_ADVERTISED_FRAME_LENGTH}"
            )

        packet_size = _FRAME_HEADER_SIZE + advertised_length
        if packet_size > _MAX_PACKET_SIZE:
            raise _DongleFrameError(
                f"[{self._serial}] Advertised packet size {packet_size} exceeds maximum "
                f"{_MAX_PACKET_SIZE}"
            )

        while len(self._receive_buffer) < packet_size:
            await read_more(packet_size)

        packet = bytes(self._receive_buffer[:packet_size])
        del self._receive_buffer[:packet_size]
        return packet

    async def _teardown_connection(self, *, expected_generation: int | None = None) -> None:
        """Tear down the shared socket, serialised on the channel's connect lock.

        For callers that do NOT already hold the connect lock (``_send_receive``
        and ``_force_reconnect``, which hold the per-transaction lock).
        Holding the connect lock for the whole close — including the awaited
        ``wait_closed()`` — prevents a concurrent ``connect()`` from dialing the
        dongle's single TCP slot while this socket is still closing (the async
        ``wait_closed()`` yields control, so without the lock ``connect()`` could
        interleave and hit the very reconnect failure this teardown prevents).
        ``_dial()`` already holds the connect lock and calls ``channel.close()``
        directly to avoid re-entrant acquisition.  Bumps the channel generation,
        so every lease sees the loss.

        ``expected_generation`` scopes the teardown to the stream the caller
        ran on: if the generation already advanced (a sibling re-dialed while
        the caller waited for the connect lock) nothing is closed — a
        transaction never tears down a stream it did not run on.  ``None``
        (``_force_reconnect``, direct callers) keeps the unconditional
        semantics.
        """
        channel = self._channel
        if channel is not None:
            await channel.teardown(expected_generation=expected_generation)

    async def _force_reconnect(self, *, expected_generation: int | None = None) -> None:
        """Tear down the (possibly broken) connection for a fresh start.

        Acquires the per-transaction lock so an in-flight request on another
        task is never yanked mid-transaction.  Reconnection itself is lazy —
        ``_send_receive`` re-establishes the connection on the next request.
        With ``expected_generation`` only the stream of that generation is
        torn down (see :meth:`_teardown_connection`).
        """
        async with self._lock:
            await self._teardown_connection(expected_generation=expected_generation)

    async def _send_receive(
        self,
        packet: bytes,
        max_retries: int = 2,
        expected_func: int | None = None,
        expected_register: int | None = None,
        expected_count: int | None = None,
        retry_on_timeout: bool = False,
        timeout_override: float | None = None,
    ) -> list[int]:
        """Send a packet and receive response with retry logic.

        Auto-reconnects if the TCP connection was lost (e.g. dongle reboot,
        network glitch).  On socket error, tears down the connection,
        reconnects, and retries — up to ``max_retries`` times.

        Connection-health invariant (#226): EVERY failure that makes the
        socket suspect — response timeout, empty read (EOF), socket error —
        tears the connection down, so the next request (or in-call retry)
        dials a FRESH TCP connection.  Silent path loss (VPN drop, NAT/
        conntrack flush) delivers no RST: the old socket stays ESTABLISHED,
        writes buffer into a black hole, and reads only ever time out.
        Recovery is only possible on a new connection, never on the old one.

        Args:
            packet: Packet bytes to send
            max_retries: Number of retry attempts for transient errors
                (empty responses, socket errors, validation mismatches)
            expected_func: Expected Modbus function code (0x03, 0x04, 0x06, 0x10).
                When provided, rejects responses with a different function code.
                Handles exception responses (high bit set) by masking to base code.
            expected_register: Expected starting register address.
                When provided, rejects responses for a different register range.
            expected_count: Expected number of registers.  When provided,
                rejects a response carrying fewer registers than requested
                (short read) so it retries and, on exhaustion, raises.
            retry_on_timeout: Resend the request in-call after a response
                timeout (the connection is torn down on every timeout
                regardless of this flag).  Safe for idempotent requests
                (register writes resend the same absolute values).  Reads
                keep fail-fast behavior: raise on the first timeout and let
                the caller's next poll reconnect.
            timeout_override: Response-wait budget for this request only,
                replacing the transport's default ``timeout`` (used by the
                cheap ``check_link`` probe).

        Returns:
            List of register values from response

        Raises:
            TransportReadError: If send/receive fails after retries
            TransportTimeoutError: If operation times out
            TransportConnectionError: If connecting (or reconnecting) fails
        """
        last_error: TransportReadError | None = None

        self._raise_if_shutdown()
        async with self._transaction() as channel:
            self._raise_if_shutdown()
            # Generation of the stream this attempt ran on (None until a
            # stream was in use); error handlers scope their teardown to it.
            generation: int | None = None
            for attempt in range(max_retries + 1):
                self._raise_if_shutdown()
                try:
                    # (Re)connect when there is no live connection — first
                    # use, after _teardown_connection(), or an external
                    # disconnect() — or when this transport has no lease on
                    # the live shared socket yet (a sibling brought it up):
                    # connect() then just records the lease, no dial.
                    # Serialised under the channel transaction lock so two
                    # concurrent requests can never race parallel connect()
                    # calls at the dongle's single TCP slot.  connect()
                    # already retries internally with backoff — if it still
                    # fails there is no connectivity, so fail this request
                    # fast instead of burning the remaining attempts on
                    # more connect cycles (keeps link-down probe cycles
                    # bounded to ONE connect sequence).
                    if (
                        self._writer is None
                        or self._reader is None
                        or not self._connected
                        or not channel.holds_lease(self)
                    ):
                        _LOGGER.info(
                            "[%s] Dongle %s:%s disconnected, attempting reconnect",
                            self._serial,
                            self._host,
                            self._port,
                        )
                        await self.connect()
                        if self._channel is not channel:
                            # Unreachable while this transaction counts as a
                            # channel user (the channel cannot be retired),
                            # but never do I/O on a channel whose transaction
                            # lock this task does not hold.
                            raise TransportConnectionError(
                                f"[{self._serial}] Dongle channel was replaced during "
                                "reconnect; retry the request"
                            )
                    if self._writer is None or self._reader is None:
                        raise TransportConnectionError("Socket not initialized")
                    # The stream this transaction runs on.  If the channel is
                    # torn down and re-dialed underneath us, the reply we are
                    # waiting for belongs to a dead socket: fail coherently
                    # (retry on the fresh one) rather than parse a stale frame.
                    generation = channel.generation

                    # Drain any pending data before sending (handles unsolicited packets)
                    await self._drain_buffer()
                    self._raise_if_shutdown()

                    # Send packet
                    writer = self._writer
                    if writer is None:
                        raise TransportConnectionError("Socket not initialized")
                    writer.write(packet)
                    await writer.drain()
                    self._raise_if_shutdown()

                    # Assemble one complete protocol frame.  The single
                    # wait_for bounds the entire prefix/header/body sequence;
                    # fragmented reads do not each restart the timeout.
                    response = await asyncio.wait_for(
                        self._receive_frame(),
                        timeout=timeout_override if timeout_override is not None else self._timeout,
                    )
                    self._raise_if_shutdown()
                    if channel.generation != generation:
                        raise _DongleFrameError(
                            f"[{self._serial}] Connection replaced mid-transaction "
                            f"(generation {generation} -> {channel.generation}); "
                            "discarding the stale frame"
                        )

                    # Parse response with cross-request validation.  The
                    # request's own TCP function (packet byte 7) is the
                    # expected response function, so an unsolicited heartbeat
                    # or proxied param frame is rejected as a mismatch rather
                    # than mis-parsed as this reply (#320).

                    # If TLS-PSK is used, the dongle does not respond with the
                    # tcp_func header, so the expected tcp_func is only set if
                    # we are not using TLS-PSK.
                    return self._parse_response(
                        response,
                        expected_func,
                        expected_register,
                        expected_count,
                        expected_tcp_func=None if self._ssl_active else packet[7],
                    )

                except _DongleFrameError as err:
                    # EOF, invalid/oversized advertised lengths, or an
                    # exhausted prefix scan leaves stream alignment unusable.
                    # Retry only after a fresh connection.
                    last_error = err
                    # A shut-down transport exits here instead of repairing:
                    # its own shutdown closed the stream and a sibling may
                    # already be dialing the replacement — never tear down a
                    # stream this transaction did not run on.
                    self._raise_if_shutdown()
                    await self._teardown_connection(expected_generation=generation)
                    self._raise_if_shutdown()
                    if attempt < max_retries:
                        _LOGGER.debug(
                            "[%s] Frame error (attempt %d/%d): %s, reconnecting...",
                            self._serial,
                            attempt + 1,
                            max_retries + 1,
                            err,
                        )
                        await asyncio.sleep(0.5)
                        continue
                    raise
                except TimeoutError as err:
                    # The connection is suspect after ANY response timeout:
                    # the dongle went mute, or the path dropped silently
                    # (VPN break, NAT/conntrack flush) — half-open TCP
                    # delivers no RST, so writes keep "succeeding" into a
                    # black hole and reads only ever time out.  Tear down
                    # unconditionally so the next request — or the resend
                    # below — dials a fresh connection instead of polling
                    # the dead flow forever (#226).
                    # A shut-down transport exits here instead of repairing:
                    # its own shutdown closed the stream and a sibling may
                    # already be dialing the replacement — never tear down a
                    # stream this transaction did not run on.
                    self._raise_if_shutdown()
                    await self._teardown_connection(expected_generation=generation)
                    self._raise_if_shutdown()
                    if retry_on_timeout and attempt < max_retries:
                        _LOGGER.warning(
                            "[%s] Timeout on attempt %d/%d, will reconnect and resend",
                            self._serial,
                            attempt + 1,
                            max_retries + 1,
                        )
                        await asyncio.sleep(0.5)
                        continue

                    _LOGGER.error("[%s] Timeout waiting for dongle response", self._serial)
                    raise TransportTimeoutError(
                        f"[{self._serial}] Timeout waiting for dongle response. "
                        "Recent dongle firmware may block port 8000 for security. "
                        "Consider using Modbus TCP with RS485 adapter instead."
                    ) from err
                except OSError as err:
                    # Tear down the broken connection; next iteration
                    # will reconnect via the top-of-loop guard.
                    # A shut-down transport exits here instead of repairing:
                    # its own shutdown closed the stream and a sibling may
                    # already be dialing the replacement — never tear down a
                    # stream this transaction did not run on.
                    self._raise_if_shutdown()
                    await self._teardown_connection(expected_generation=generation)
                    self._raise_if_shutdown()

                    if attempt < max_retries:
                        _LOGGER.warning(
                            "[%s] Socket error on attempt %d/%d: %s, will reconnect on next retry",
                            self._serial,
                            attempt + 1,
                            max_retries + 1,
                            err,
                        )
                        await asyncio.sleep(0.5)
                        continue

                    _LOGGER.error(
                        "[%s] Socket error communicating with dongle: %s", self._serial, err
                    )
                    raise TransportReadError(f"[{self._serial}] Socket error: {err}") from err
                except TransportReadError as err:
                    last_error = err
                    self._raise_if_shutdown()
                    if attempt < max_retries:
                        _LOGGER.debug(
                            "[%s] Read error (attempt %d/%d): %s, retrying...",
                            self._serial,
                            attempt + 1,
                            max_retries + 1,
                            err,
                        )
                        await asyncio.sleep(0.5)
                        continue
                    raise

        # Should not reach here, but satisfy type checker
        if last_error:
            raise last_error
        raise TransportReadError("Unexpected error in send/receive")

    def _find_packet_start(self, data: bytes) -> int:
        """Find the start of a valid packet in the buffer.

        The dongle may send unsolicited heartbeat packets or there may be
        leftover data from previous responses. This method searches for
        the packet prefix (0xA1, 0x1A) to find where the actual response starts.

        Args:
            data: Buffer containing received data

        Returns:
            Index where packet starts, or -1 if not found
        """
        # Search for the packet prefix
        idx = data.find(PACKET_PREFIX)
        if idx > 0:
            _LOGGER.debug(
                "Found packet start at offset %d, discarding %d bytes of junk data: %s",
                idx,
                idx,
                data[:idx].hex()[:50],
            )
        return idx

    def _parse_response(
        self,
        response: bytes,
        expected_func: int | None = None,
        expected_register: int | None = None,
        expected_count: int | None = None,
        expected_tcp_func: int | None = None,
    ) -> list[int]:
        """Parse a dongle response packet with cross-request validation.

        Validates that the response matches the original request by checking
        the TCP function code, inverter serial, Modbus function code, and
        starting register address.  This prevents accepting misrouted
        responses from the cloud server — or unsolicited heartbeat frames —
        that pass through (or originate from) the WiFi dongle.

        Args:
            response: Raw response bytes
            expected_tcp_func: Expected LuxPower TCP function byte (the
                request's own ``tcp_func``, e.g. ``TCP_FUNC_TRANSLATED``).
                When provided, rejects a frame carrying a different TCP
                function — an unsolicited heartbeat (0xC1) or a proxied
                param frame (0xC3/0xC4) that shares the 0xA1 0x1A prefix and
                would otherwise be mis-parsed as this request's response.
            expected_func: Expected Modbus function code (e.g., 0x04 for
                input register read).  When provided, rejects responses
                with a different base function code.
            expected_register: Expected starting register address.  When
                provided, rejects responses for a different register range.
            expected_count: Expected number of registers.  When provided,
                rejects a response carrying FEWER registers than requested.
                Serial/function/register validation all pass on a truncated
                frame (correct header, valid CRC over the short payload), so
                without this a short read would return a partial register
                list — on the holding/parameter path that silently drops
                registers from the parameter dict, skipping the #282 sticky
                merge and blanking HA entities for the full cache TTL.

        Returns:
            List of register values

        Raises:
            TransportReadError: If the response is invalid (junk, truncated,
                CRC failure, Modbus exception, or short read).
            TransportResponseMismatchError: If the response doesn't match the
                original request (serial/function/register mismatch), i.e. a
                misrouted or interleaved frame.  A subclass of
                ``TransportReadError`` so existing ``except`` handlers still
                catch it; callers that care can distinguish it (#320).
        """
        # Find the packet start (handle junk data before the response)
        packet_start = self._find_packet_start(response)
        if packet_start < 0:
            raise TransportReadError(
                f"[{self._serial}] No valid packet found in response "
                f"({len(response)} bytes): "
                f"{response[:40].hex() if response else 'empty'}"
            )

        # Adjust response to start at the packet
        response = response[packet_start:]

        if len(response) < _FRAME_HEADER_SIZE:
            raise TransportReadError(f"[{self._serial}] Response too short: {len(response)} bytes")

        advertised_length = struct.unpack("<H", response[4:6])[0]
        if advertised_length < _MIN_ADVERTISED_FRAME_LENGTH:
            raise TransportReadError(
                f"[{self._serial}] Invalid advertised frame length "
                f"{advertised_length}; minimum is {_MIN_ADVERTISED_FRAME_LENGTH}"
            )

        packet_size = _FRAME_HEADER_SIZE + advertised_length
        if packet_size > _MAX_PACKET_SIZE:
            raise TransportReadError(
                f"[{self._serial}] Advertised packet size {packet_size} exceeds maximum "
                f"{_MAX_PACKET_SIZE}"
            )
        if packet_size > len(response):
            raise TransportReadError(
                f"[{self._serial}] Response truncated: advertised {packet_size} bytes, "
                f"got {len(response)}"
            )

        # The outer length covers fixed address/function/serial/data-length
        # fields plus the inner data and CRC.  Requiring both length fields
        # to agree prevents accepting a CRC-valid prefix of a malformed frame.
        data_length = struct.unpack("<H", response[18:20])[0]
        expected_advertised_length = _FRAME_FIXED_FIELDS_SIZE + data_length
        if advertised_length != expected_advertised_length:
            raise TransportReadError(
                f"[{self._serial}] Frame length mismatch: outer advertises "
                f"{advertised_length}, inner requires {expected_advertised_length}"
            )
        if data_length < _FRAME_CRC_SIZE:
            raise TransportReadError(
                f"[{self._serial}] Invalid data length {data_length}; minimum is {_FRAME_CRC_SIZE}"
            )

        # Ignore bytes following the advertised frame.  Stream reads extract
        # exactly one packet before this parser, while direct parser callers
        # may supply a buffer containing trailing data.
        response = response[:packet_size]

        # --- TCP function validation (must precede the data-frame checks) ---
        # The dongle shares the 0xA1 0x1A prefix across ALL its frames — the
        # translated-Modbus reply we want (0xC2), unsolicited heartbeats
        # (0xC1), and proxied param frames (0xC3/0xC4).  A heartbeat racing in
        # after _drain_buffer carries a short data frame, so without this
        # check it would trip the generic "Data frame too short" path below —
        # a plain TransportReadError that latches coalescing off on a coalesced
        # read (#320).  Rejecting the wrong TCP function as a mismatch instead
        # both keeps the latch for genuine refusals only and lets the retry
        # loop recover the real reply.  The expectation is the REQUEST's own
        # tcp_func (byte 7), so a future path expecting 0xC3/0xC4 stays correct
        # without hardcoding 0xC2 here.
        if expected_tcp_func is not None:
            response_tcp_func = response[7]
            if response_tcp_func != expected_tcp_func:
                label = _TCP_FUNC_NAMES.get(response_tcp_func, "unknown")
                context = _mismatch_context(
                    _format_frame_fields(
                        tcp_func=expected_tcp_func,
                        func=expected_func,
                        register=expected_register,
                        count=expected_count,
                    ),
                    _format_frame_fields(tcp_func=response_tcp_func),
                )
                raise TransportResponseMismatchError(
                    f"[{self._serial}] Unexpected TCP function "
                    f"0x{response_tcp_func:02x} ({label}): {context} "
                    "— misrouted/unsolicited frame"
                )

        # Data starts at offset 20
        data_start = 20
        data_end = data_start + data_length - 2  # -2 for CRC
        crc_start = data_end
        crc_end = crc_start + 2

        if crc_end > len(response):
            raise TransportReadError(
                f"[{self._serial}] Response truncated: expected {crc_end} bytes, "
                f"got {len(response)}"
            )

        # Extract data frame and CRC
        data_frame = response[data_start:data_end]
        received_crc = struct.unpack("<H", response[crc_start:crc_end])[0]

        # Verify CRC to ensure data integrity
        computed_crc = compute_crc16(data_frame)
        if computed_crc != received_crc:
            _LOGGER.warning(
                "[%s] CRC mismatch: computed 0x%04X, received 0x%04X. "
                "Data may be corrupted. Raw response: %s",
                self._serial,
                computed_crc,
                received_crc,
                response[:60].hex(),
            )
            raise TransportReadError(
                f"[{self._serial}] CRC verification failed: computed 0x{computed_crc:04X}, "
                f"received 0x{received_crc:04X}"
            )

        # For read responses, data frame contains:
        # - action (1 byte)
        # - modbus_func (1 byte)
        # - inverter_serial (10 bytes)
        # - start_register (2 bytes, LE)
        # - byte_count (1 byte)
        # - register_data (N bytes)
        # Total header before data: 1 + 1 + 10 + 2 + 1 = 15 bytes
        if len(data_frame) < 15:
            raise TransportReadError(
                f"[{self._serial}] Data frame too short: {len(data_frame)} bytes"
            )

        modbus_func = data_frame[1]

        # --- Cross-request validation ---
        # The WiFi dongle proxies between the cloud server and the inverter.
        # Responses meant for the cloud can be misrouted to us.  These have
        # valid CRC but wrong serial/function/register.  Reject them so the
        # retry logic can resend and get the correct response.

        # The received register is parseable on any read-layout data frame
        # (offset 12-13), so include it in every "received" context block.
        response_register = struct.unpack("<H", data_frame[12:14])[0]

        # The expected/received framing is identical for every cross-request
        # mismatch below (same modbus_func + response_register), so build the
        # context once and raise through one helper to keep the three messages
        # byte-for-byte consistent (joyfulhouse/pylxpweb#213).
        expected_fields = _format_frame_fields(
            tcp_func=expected_tcp_func,
            func=expected_func,
            register=expected_register,
            count=expected_count,
        )
        mismatch_context = _mismatch_context(
            expected_fields,
            _format_frame_fields(func=modbus_func, register=response_register),
        )

        def _raise_mismatch(detail: str) -> NoReturn:
            raise TransportResponseMismatchError(
                f"[{self._serial}] {detail} — likely a misrouted cloud response"
            )

        # 1. Inverter serial must match (always checked)
        response_serial = data_frame[2:12]
        if self._serial:
            expected_serial = self._serial.encode("ascii").ljust(10, b"\x00")[:10]
            if response_serial != expected_serial:
                resp_serial_str = response_serial.decode("ascii", errors="replace").rstrip("\x00")
                _raise_mismatch(
                    f"Response serial mismatch: expected {self._serial}, "
                    f"got {resp_serial_str} ({mismatch_context})"
                )
        else:
            # A garbage frame must reject through the mismatch path, not
            # crash with UnicodeDecodeError, and NUL padding must not leak
            # into logs or outbound frames via the stored serial.
            detected = response_serial.decode("ascii", errors="replace").rstrip("\x00")
            if len(detected) != 10 or not detected.isascii() or not detected.isprintable():
                _raise_mismatch(f"Unparseable response serial {detected!r} ({mismatch_context})")
            self._serial = detected
            _LOGGER.debug("Detected inverter serial: %s", self._serial)

        # 2. Function code must match (mask high bit for exception responses)
        if expected_func is not None:
            response_base_func = modbus_func & 0x7F
            if response_base_func != expected_func:
                _raise_mismatch(f"Response function mismatch: {mismatch_context}")

        # 3. Start register must match
        if expected_register is not None and response_register != expected_register:
            _raise_mismatch(f"Response register mismatch: {mismatch_context}")

        # Check for Modbus exception (function code with high bit set)
        if modbus_func & 0x80:
            exception_code = data_frame[14] if len(data_frame) > 14 else 0
            raise TransportReadError(
                f"[{self._serial}] Modbus exception: function=0x{modbus_func:02x}, "
                f"code={exception_code}"
            )

        # Write ACKs (FC06/FC16) are not read frames: the dongle echoes
        # action + func + serial + register + payload, where payload is the
        # echoed value (FC06) or the written register count (FC16) — there
        # is no byte_count header.  Parse the strict 16-byte ACK layout
        # explicitly so ACK echo validation sees the real payload; any other
        # length falls through to the read-layout parser below, covering
        # firmwares that echo write ACKs read-style (byte_count + data).
        if modbus_func in (MODBUS_WRITE_SINGLE, MODBUS_WRITE_MULTI) and len(data_frame) == 16:
            return [int(struct.unpack("<H", data_frame[14:16])[0])]

        # byte_count is at offset 14 (after action + func + serial + start_reg)
        byte_count = data_frame[14]

        # Extract register values (little-endian uint16)
        # Register data starts at offset 15
        register_data = data_frame[15 : 15 + byte_count]
        registers: list[int] = []

        for i in range(0, len(register_data), 2):
            if i + 1 < len(register_data):
                value = struct.unpack("<H", register_data[i : i + 2])[0]
                registers.append(value)

        # Reject a short read: the frame is well-formed (matching serial /
        # function / register, valid CRC) but carries fewer registers than
        # requested.  Raising here — inside the _send_receive retry loop —
        # lets a transient truncation recover on retry and, once retries are
        # exhausted, surfaces as a failed range instead of a partial result.
        if expected_count is not None and len(registers) < expected_count:
            raise TransportReadError(
                f"[{self._serial}] Short read: expected {expected_count} registers, "
                f"got {len(registers)}"
            )

        return registers

    async def check_link(self) -> bool:
        """Cheap link-down probe: one read, single attempt, short timeout.

        The production failure mode this bounds: the dongle accepts TCP but
        never answers (wedged firmware, blocked port 8000), so a normal read
        pays the full response timeout (default 10 s) inside every
        coordinator refresh while the link is down — Home Assistant absorbs
        that into the effective poll interval (eg4_web_monitor#587).

        The outer bound also caps the connect retry ladder for
        connection-refused endpoints.  Any exception — including the outer
        cancellation — reports the link as down; ``_send_receive`` already
        tears the connection down on response timeouts, and the explicit
        teardown after an outer cancellation guarantees the next probe
        dials fresh.

        The outer budget is not a strict wall-clock bound: ``wait_for``
        awaits cancellation cleanup, and a cancel landing inside
        ``connect()`` awaits the channel close (itself bounded).  Worst
        case the probe approaches ~2x the budget — still far below the
        default 10s response timeout it replaces.

        Shared socket: the probe is one more wire-touching operation, so it
        runs under the channel operation lock like every read and write —
        it can wait for a sibling's in-flight multi-step operation, but it
        can never slip a transaction between that operation's steps.  The
        budget bounds the probe itself, not that wait.  The teardown after
        an exhausted budget is scoped to the stream the probe started on: a
        stream dialed since (by the probe's own reconnect, which closes
        itself on cancellation, or by a sibling) is left alone.
        """
        packet = self._build_packet(
            tcp_func=TCP_FUNC_TRANSLATED,
            modbus_func=MODBUS_READ_INPUT,
            start_register=0,
            register_count=1,
        )
        async with self._operation():
            generation = self._resolve_channel().generation
            try:
                # A probe dial must reuse the last-known channel state instead
                # of AUTO TLS-probing (see _auto_ssl_context): a TLS-silent
                # peer would otherwise burn the handshake timeout inside this
                # budget and report a working plaintext dongle as down.
                self._link_probe_active = True
                await asyncio.wait_for(
                    self._send_receive(
                        packet,
                        max_retries=0,
                        expected_func=MODBUS_READ_INPUT,
                        expected_register=0,
                        timeout_override=LINK_PROBE_TIMEOUT_SECONDS,
                    ),
                    timeout=LINK_PROBE_TIMEOUT_SECONDS + _LINK_PROBE_CONNECT_GRACE_SECONDS,
                )
            except TimeoutError:
                # Outer budget hit (e.g. connect stalled): the cancellation
                # may have left a half-established connection on the stream
                # the probe started on — tear that one down so the next
                # probe dials fresh.
                await self._force_reconnect(expected_generation=generation)
                _LOGGER.debug("[%s] Link probe exceeded its budget", self._serial)
                return False
            except (TransportError, OSError) as err:
                _LOGGER.debug("[%s] Link probe failed: %s", self._serial, err)
                return False
            finally:
                self._link_probe_active = False
        return True

    async def _read_input_registers(
        self,
        address: int,
        count: int,
    ) -> list[int]:
        """Read input registers (read-only runtime data).

        Args:
            address: Starting register address
            count: Number of registers to read

        Returns:
            List of register values

        Raises:
            TransportReadError: If read fails
            TransportTimeoutError: If operation times out
        """
        packet = self._build_packet(
            tcp_func=TCP_FUNC_TRANSLATED,
            modbus_func=MODBUS_READ_INPUT,
            start_register=address,
            register_count=count,
        )

        return await self._send_receive(
            packet,
            expected_func=MODBUS_READ_INPUT,
            expected_register=address,
        )

    async def _read_holding_registers(
        self,
        address: int,
        count: int,
    ) -> list[int]:
        """Read holding registers (configuration parameters).

        Args:
            address: Starting register address
            count: Number of registers to read

        Returns:
            List of register values

        Raises:
            TransportReadError: If read fails
            TransportTimeoutError: If operation times out
        """
        packet = self._build_packet(
            tcp_func=TCP_FUNC_TRANSLATED,
            modbus_func=MODBUS_READ_HOLDING,
            start_register=address,
            register_count=count,
        )

        return await self._send_receive(
            packet,
            expected_func=MODBUS_READ_HOLDING,
            expected_register=address,
            expected_count=count,
        )

    async def _write_holding_registers(
        self,
        address: int,
        values: list[int],
    ) -> bool:
        """Write holding registers.

        Args:
            address: Starting register address
            values: List of values to write

        Returns:
            True if write succeeded

        Raises:
            TransportWriteError: If write fails
            TransportTimeoutError: If operation times out
        """
        modbus_func = MODBUS_WRITE_SINGLE if len(values) == 1 else MODBUS_WRITE_MULTI
        packet = self._build_packet(
            tcp_func=TCP_FUNC_TRANSLATED,
            modbus_func=modbus_func,
            start_register=address,
            values=values,
        )

        # Settle delay before the write: dongles can drop the TCP link on
        # rapid function-code changes (e.g. the read step of a
        # read-modify-write cycle immediately followed by the write).
        if self._write_step_delay > 0:
            await asyncio.sleep(self._write_step_delay)

        try:
            # No request-level resend AT ALL for writes (review + codex):
            # after ANY ACK loss — mute timeout, EOF before the reply, or a
            # socket error — the inverter may have already applied the
            # write, and resending the same pre-built packet could replay
            # STALE bit-field values over a concurrent writer's change.
            # max_retries=0 disables the empty-response/OSError resend
            # paths; every failure tears down inside _send_receive and
            # propagates to write_named_parameters' sequence-level retry,
            # which RE-READS before re-writing.
            ack = await self._send_receive(
                packet,
                max_retries=0,
                expected_func=modbus_func,
                expected_register=address,
            )
        except TransportReadError as err:
            raise TransportWriteError(str(err)) from err

        # ACK echo validation (review): serial/function/register are already
        # cross-checked in _parse_response; additionally pin the echoed
        # payload so a misrouted ACK for the same register cannot pass as a
        # confirmation of OUR value.
        if modbus_func == MODBUS_WRITE_SINGLE:
            if not ack:
                # An empty/short ACK carries no echoed value to confirm the
                # write landed — treat it as a failure rather than silently
                # reporting success.
                raise TransportWriteError(
                    f"Write ACK empty/short for register {address}: no echoed "
                    "value to confirm the write"
                )
            if ack[0] != values[0]:
                raise TransportWriteError(
                    f"Write ACK echo mismatch for register {address}: wrote "
                    f"{values[0]}, ACK echoed {ack[0]} — possible misrouted "
                    "response"
                )
        else:
            if not ack:
                # FC16 ACK must echo the written register count; an empty/short
                # ACK cannot confirm the multi-register write.
                raise TransportWriteError(
                    f"Write ACK empty/short for register {address}: no echoed "
                    "register count to confirm the write"
                )
            if len(ack) != 1:
                # The supported read-layout fallback still has exactly one
                # count value.  Two or more parsed values are a read payload,
                # not an unambiguous FC16 acknowledgement.
                raise TransportWriteError(
                    f"Write ACK malformed for register {address}: expected one "
                    f"echoed register count, got {len(ack)} values"
                )
            if ack[0] != len(values):
                # FC16 ACK echoes the written register count.
                raise TransportWriteError(
                    f"Write ACK count mismatch for register {address}: wrote "
                    f"{len(values)} registers, ACK echoed {ack[0]}"
                )
        return True

    # Data reading/writing methods (read_runtime, read_energy, read_battery,
    # read_midbox_runtime, read_parameters, write_parameters, device info)
    # are inherited from RegisterDataMixin via _register_data.py.

    # ------------------------------------------------------------------
    # Operation-level serialisation (channel op lock via self._operation())
    # ------------------------------------------------------------------
    # The WiFi dongle processes ONE request at a time over its single TCP
    # connection.  High-level operations that issue multiple sequential
    # register reads release the per-transaction lock between calls,
    # allowing concurrent writes to interleave and confuse the protocol.
    #
    # The channel's task-reentrant op lock serialises entire multi-step
    # operations so that writes wait until a read sequence is fully
    # complete — and vice-versa.  It is per CHANNEL, not per transport:
    # with several devices on one socket, correlation is positional, so a
    # same-register reply landing on a sibling's step would go undetected
    # (pylxpweb#329).
    #
    # Re-entrancy is required because write_named_parameters (BaseTransport)
    # calls self.read_parameters + self.write_parameters internally, which
    # also acquire the op lock.

    async def read_midbox_runtime(self) -> MidboxRuntimeData:
        """Serialised read of MID/GridBOSS runtime data (5 INPUT + 1 HOLD read)."""
        async with self._operation():
            return await super().read_midbox_runtime()

    async def read_runtime(self) -> InverterRuntimeData:
        """Serialised runtime read (multi-group input read + pv4-6 extra read).

        The inherited ``RegisterDataMixin.read_runtime`` issues the runtime
        register groups plus the supplementary pv4-6 read, releasing the
        per-transaction lock between each call.  On the dongle's single TCP
        connection that allows concurrent operations to interleave and
        misroute responses, so the whole sequence is wrapped in ``_op_lock``
        — consistent with ``read_all_input_data``.  The pv4-6 read itself
        remains non-fatal (handled inside ``RegisterDataMixin``).
        """
        async with self._operation():
            return await super().read_runtime()

    async def read_all_input_data(
        self,
    ) -> tuple[InverterRuntimeData, InverterEnergyData, BatteryBankData | None]:
        """Serialised combined read of all input register groups."""
        async with self._operation():
            return await super().read_all_input_data()

    async def read_parameters(
        self,
        start_address: int,
        count: int,
    ) -> dict[int, int]:
        """Serialised read of holding (configuration) registers."""
        async with self._operation():
            return await super().read_parameters(start_address, count)

    async def read_quick_charge_remaining_seconds(self) -> int | None:
        """Serialised read of quick-charge remaining seconds (input reg 210)."""
        async with self._operation():
            return await super().read_quick_charge_remaining_seconds()

    async def write_parameters(
        self,
        parameters: dict[int, int],
    ) -> bool:
        """Serialised write of holding (configuration) registers."""
        async with self._operation():
            return await super().write_parameters(parameters)

    # Remaining inherited multi-request reads (review): without these
    # overrides a coordinator poll could interleave with a write retry /
    # reconnect teardown on the dongle's single TCP connection.

    async def read_energy(self) -> InverterEnergyData:
        """Serialised energy read (multi-group input read)."""
        async with self._operation():
            return await super().read_energy()

    async def read_battery(self, *args: Any, **kwargs: Any) -> Any:
        """Serialised battery read (atomic 120-register input read)."""
        async with self._operation():
            return await super().read_battery(*args, **kwargs)

    async def read_serial_number(self) -> str:
        """Serialised device-info read."""
        async with self._operation():
            return await super().read_serial_number()

    async def read_firmware_version(self) -> str:
        """Serialised device-info read."""
        async with self._operation():
            return await super().read_firmware_version()

    async def read_device_type(self) -> int:
        """Serialised device-info read."""
        async with self._operation():
            return await super().read_device_type()

    async def read_parallel_config(self) -> int:
        """Serialised device-info read."""
        async with self._operation():
            return await super().read_parallel_config()

    async def write_named_parameters(
        self,
        parameters: dict[str, Any],
    ) -> bool:
        """Resilient, serialised read-modify-write of named parameters.

        Acquires op_lock for the full call so the RMW is atomic relative to
        concurrent reads.  The internal calls to read_parameters /
        write_parameters re-enter the reentrant lock without blocking.

        The WiFi dongle drops its TCP connection mid-sequence during
        parameter writes (firmware timeout / cloud-connection priority),
        which previously failed the whole write in LOCAL-only mode
        (joyfulhouse/eg4_web_monitor#201).  This method retries the ENTIRE
        sequence on transport errors:

        1. Tear down the broken connection (reconnect happens lazily on
           the next request).
        2. RE-READ the register — the modify step never reuses a stale
           pre-drop value (the register may have changed while we were
           disconnected, e.g. a concurrent cloud write).
        3. Re-apply the bit/field modification and retry the write.
        4. After a successful write, read the register back as a DIAGNOSTIC
           (when cheap; see ``verify_writes``).  A readback difference is
           logged but never re-written: the inverter may legitimately clamp
           or round values, and a concurrent writer (cloud server,
           parallel-group propagation) must not be fought.

        Retries are bounded by ``write_retries`` with a short backoff.
        Worst case with defaults (timeout=10, write_retries=2): roughly
        3 × (timeout + backoff + step delay) ≈ 35 s holding the op lock —
        there is no inner request-level resend multiplying this.

        Raises:
            TransportConnectionError: If terminal shutdown is requested. This
                is never retried or recast as a generic write failure.
            TransportWriteError: If the write sequence fails after all
                attempts.  A ``TransportError`` subclass, so HYBRID-mode
                consumers can still dispatch their cloud API fallback.
            ValueError: If a parameter name is not recognized (not retried).
        """
        async with self._operation():
            attempts = self._write_retries + 1
            last_error: TransportError | None = None

            for attempt in range(1, attempts + 1):
                self._raise_if_shutdown()
                try:
                    result = await super().write_named_parameters(parameters)
                except (
                    TransportConnectionError,
                    TransportReadError,
                    TransportTimeoutError,
                    TransportWriteError,
                ) as err:
                    # A terminal close is not a transient link failure. Preserve
                    # its connection-error contract instead of entering the
                    # sequence retry/backoff and eventually recasting it.
                    self._raise_if_shutdown()
                    last_error = err
                    if attempt < attempts:
                        _LOGGER.warning(
                            "Parameter write sequence failed (attempt %d/%d) for %s: %s "
                            "— reconnecting and retrying with a fresh register read",
                            attempt,
                            attempts,
                            sorted(parameters),
                            err,
                        )
                        # Deliberately unconditional: the failed sequence may
                        # have reconnected mid-way, so no single generation
                        # names "the stream the failure happened on"; the
                        # retry contract is a fresh start.  Under the op lock
                        # no sibling operation is in flight — at worst a
                        # sibling's idle, just-dialed socket costs one redial.
                        await self._force_reconnect()
                        self._raise_if_shutdown()
                        await asyncio.sleep(WRITE_RETRY_DELAY * attempt)
                        self._raise_if_shutdown()
                    continue

                self._raise_if_shutdown()
                if not self._verify_writes:
                    return result

                try:
                    mismatches = await self._verify_named_parameters(parameters)
                except TransportError as err:
                    self._raise_if_shutdown()
                    # The write itself was acknowledged by the inverter; a
                    # failed verification READ must not fail the operation.
                    _LOGGER.debug(
                        "Post-write verification read failed for %s (%s); "
                        "write was acknowledged — accepting",
                        sorted(parameters),
                        err,
                    )
                    return result

                self._raise_if_shutdown()
                if not mismatches:
                    return result

                # Verification is DIAGNOSTIC-ONLY (review): the inverter
                # ACKed the write (echo-validated in _write_holding_registers).
                # A readback difference can be legitimate — firmware
                # clamping/rounding (SOC bounds, scaled voltages) or a
                # CONCURRENT writer (cloud server, parallel-group register
                # propagation à la reg 179). Re-writing would fight that
                # writer in a loop; never do it.
                _LOGGER.warning(
                    "Post-write readback differs for %s: %s — accepting the "
                    "ACKed write (firmware clamp or concurrent writer)",
                    sorted(parameters),
                    "; ".join(mismatches),
                )
                return result

            raise TransportWriteError(
                f"Parameter write failed after {attempts} attempts for "
                f"{sorted(parameters)}: {last_error}"
            ) from last_error

    async def _verify_named_parameters(
        self,
        parameters: dict[str, Any],
    ) -> list[str]:
        """Read back written registers and compare against requested values.

        Decodes bit fields, multi-bit fields, and plain values using the same
        register mappings the write path used, so a write that the inverter
        acknowledged but silently dropped (or that a concurrent cloud write
        clobbered) is detected.

        Args:
            parameters: The named parameters that were just written.

        Returns:
            List of human-readable mismatch descriptions (empty = verified).
            Returns an empty list without reading when verification would
            not be cheap (more than ``VERIFY_MAX_REGISTERS`` registers).

        Raises:
            TransportReadError: If the readback read fails.
            TransportTimeoutError: If the readback read times out.
            TransportConnectionError: If reconnecting for the readback fails.
        """
        from pylxpweb.constants.registers import BIT_FIELD_LAYOUT, LOCAL_PARAM_SCALE_DIV10

        register_to_params, param_to_register = self._resolve_register_mappings(
            param_names=list(parameters.keys()),
        )

        registers = sorted({param_to_register[p] for p in parameters if p in param_to_register})
        if not registers or len(registers) > VERIFY_MAX_REGISTERS:
            return []

        # Settle delay before switching from write back to read function codes.
        if self._write_step_delay > 0:
            await asyncio.sleep(self._write_step_delay)

        readback: dict[int, int] = {}
        for register in registers:
            readback.update(await self.read_parameters(register, 1))

        mismatches: list[str] = []
        for name, value in parameters.items():
            param_register = param_to_register.get(name)
            if param_register is None:
                continue
            if param_register not in readback:
                mismatches.append(f"{name}: register {param_register} missing from readback")
                continue

            raw = readback[param_register]
            param_keys = register_to_params.get(param_register, [])

            if self._is_bit_field_register(param_keys):
                explicit_layout = BIT_FIELD_LAYOUT.get(name)
                if explicit_layout is not None:
                    offset, width = explicit_layout
                    got_field = (raw >> offset) & ((1 << width) - 1)
                    expected_field = int(value) if width > 1 else int(bool(value))
                    if got_field != expected_field:
                        mismatches.append(f"{name}: wrote {expected_field}, read back {got_field}")
                elif name in param_keys:
                    got_bit = bool((raw >> param_keys.index(name)) & 1)
                    if got_bit is not bool(value):
                        mismatches.append(f"{name}: wrote {bool(value)}, read back {got_bit}")
            elif name in LOCAL_PARAM_SCALE_DIV10:
                # Deci-unit params: the request is in cloud units (kW / V),
                # the readback register is raw deci-units. Compare in raw.
                wrote_raw = round(float(value) * 10) & 0xFFFF
                if wrote_raw != raw:
                    mismatches.append(f"{name}: wrote {wrote_raw} (raw), read back {raw}")
            elif (int(value) & 0xFFFF) != raw:
                mismatches.append(f"{name}: wrote {int(value)}, read back {raw}")

        return mismatches
