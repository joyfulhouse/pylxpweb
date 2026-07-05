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
The WiFi dongle supports only ONE concurrent TCP connection.
Running multiple clients causes connection errors and data loss.

Ensure only ONE integration/script connects to each dongle at a time.
Disable other integrations (Solar Assistant, lxp-bridge) before using.

IMPORTANT: Firmware Compatibility
---------------------------------
Recent firmware updates may block port 8000 access for security.
If connection fails, check if your dongle firmware has been updated.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import struct
from typing import TYPE_CHECKING, Any

from ._register_data import (
    DEFAULT_INPUT_BLOCK_SIZE,
    RegisterDataMixin,
    validate_input_block_size,
)
from .capabilities import MODBUS_CAPABILITIES, TransportCapabilities
from .exceptions import (
    TransportConnectionError,
    TransportError,
    TransportReadError,
    TransportResponseMismatchError,
    TransportTimeoutError,
    TransportWriteError,
)
from .protocol import BaseTransport

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

# Write resilience settings (joyfulhouse/eg4_web_monitor#201)
# The dongle drops its TCP connection mid-sequence during parameter writes
# (firmware timeout / cloud-connection priority), so the read-modify-write
# cycle is retried at the sequence level with a fresh register read.
DEFAULT_WRITE_RETRIES = 2  # sequence-level retries (3 attempts total)
DEFAULT_WRITE_STEP_DELAY = 0.2  # settle delay before write/verify steps (s)
WRITE_RETRY_DELAY = 0.5  # base backoff between sequence attempts (s)
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


class DongleTransport(RegisterDataMixin, BaseTransport):
    """WiFi Dongle TCP transport for local inverter communication.

    This transport connects directly to the inverter's WiFi dongle
    via TCP port 8000 using the LuxPower/EG4 proprietary protocol.

    IMPORTANT: Single-Client Limitation
    ------------------------------------
    The WiFi dongle supports only ONE concurrent TCP connection.
    Disable other integrations before using this transport.

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
        inverter_family: InverterFamily | None = None,
        connection_retries: int = 3,
        write_retries: int = DEFAULT_WRITE_RETRIES,
        write_step_delay: float = DEFAULT_WRITE_STEP_DELAY,
        verify_writes: bool = True,
        max_input_block_size: int = DEFAULT_INPUT_BLOCK_SIZE,
    ) -> None:
        """Initialize WiFi Dongle transport.

        Args:
            host: IP address or hostname of the WiFi dongle
            dongle_serial: 10-character dongle serial number (e.g., "BA12345678")
            inverter_serial: 10-character inverter serial number (e.g., "CE12345678")
            port: TCP port (default 8000)
            timeout: Connection and operation timeout in seconds
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
        """
        super().__init__(inverter_serial)
        self._host = host
        self._port = port
        self._dongle_serial = dongle_serial
        self._timeout = timeout
        self._inverter_family = inverter_family
        self._split_phase: bool = False
        self._pv_string_count: int = 3
        self._connection_retries = connection_retries
        self._inter_register_delay = 0.5  # Dongle needs slower pace than Modbus
        self._max_input_block_size = validate_input_block_size(max_input_block_size)
        self._input_coalescing_latched_off: bool = False
        self._write_retries = write_retries
        self._write_step_delay = write_step_delay
        self._verify_writes = verify_writes
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        # Serialises connect() itself: _send_receive reconnects under
        # self._lock, but external callers (e.g. a coordinator write path
        # doing "if not is_connected: connect()") can race it — and the
        # dongle has exactly ONE TCP slot, so two parallel dials corrupt
        # each other.  Lock order is always _lock -> _connect_lock; nothing
        # under _connect_lock ever takes _lock, so no cycle.
        self._connect_lock = asyncio.Lock()
        self._transaction_id = 0

    @property
    def capabilities(self) -> TransportCapabilities:
        """Get dongle transport capabilities (same as Modbus)."""
        return MODBUS_CAPABILITIES

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

    async def connect(self) -> None:
        """Establish TCP connection to the WiFi dongle with retry and backoff.

        The dongle only allows one TCP connection at a time. If connection fails,
        retries with exponential backoff (1s, 2s, 4s, ...) to handle cases where
        a previous connection wasn't properly released.

        State guarantee: ``_connected`` is set True only after the connection
        is fully usable (socket open AND initial data discarded).  Every
        failure path — including a partially-succeeded attempt where the
        socket opened but the initial-data read errored — tears the
        connection down, so connect() can never exit with ``_connected``
        True on a dead socket (#226 state-corruption guard).

        Concurrency: serialised on ``_connect_lock`` (the dongle has ONE
        TCP slot — two parallel dials corrupt each other).  A caller that
        lost the race to another task's successful connect returns
        immediately instead of tearing down the fresh connection.

        Raises:
            TransportConnectionError: If all connection attempts fail
        """
        async with self._connect_lock:
            if self._connected:
                return  # another task already (re)connected

            last_error: Exception | None = None
            retry_delay = 1.0  # Start with 1 second delay

            # Clean slate: drop any stale half-open socket from a previous
            # session before dialing a new one (the dongle has ONE TCP slot).
            self._teardown_connection()

            for attempt in range(self._connection_retries):
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
                        retry_delay *= 2  # Exponential backoff

                    self._reader, self._writer = await asyncio.wait_for(
                        asyncio.open_connection(self._host, self._port),
                        timeout=self._timeout,
                    )

                    # Discard any initial data the dongle sends after
                    # connection (some dongles send unsolicited packets that
                    # can confuse subsequent reads) BEFORE declaring the
                    # connection usable — an OSError here fails this attempt
                    # instead of leaking a connected-looking transport with
                    # a broken socket.
                    await self._discard_initial_data()

                    self._connected = True
                    _LOGGER.info(
                        "Dongle transport connected to %s:%s (dongle=%s, inverter=%s)%s",
                        self._host,
                        self._port,
                        self._dongle_serial,
                        self._serial,
                        f" after {attempt} retries" if attempt > 0 else "",
                    )
                    return  # Success!

                except TimeoutError as err:
                    last_error = err
                    self._teardown_connection()
                    _LOGGER.warning(
                        "Timeout connecting to dongle at %s:%s (attempt %d/%d)",
                        self._host,
                        self._port,
                        attempt + 1,
                        self._connection_retries,
                    )
                except OSError as err:
                    last_error = err
                    self._teardown_connection()
                    _LOGGER.warning(
                        "Connection failed to %s:%s: %s (attempt %d/%d)",
                        self._host,
                        self._port,
                        err,
                        attempt + 1,
                        self._connection_retries,
                    )

            # All retries exhausted
            self._teardown_connection()
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
        """Close TCP connection to the dongle.

        Uses timeout on wait_closed() to prevent hanging if the connection
        is in a bad state. The dongle only supports one connection at a time,
        so proper cleanup is essential.
        """
        if self._writer:
            try:
                self._writer.close()
                # Use timeout to prevent indefinite hang if connection is stuck
                await asyncio.wait_for(self._writer.wait_closed(), timeout=5.0)
            except TimeoutError:
                _LOGGER.warning(
                    "Timeout waiting for connection close to %s:%s",
                    self._host,
                    self._port,
                )
            except Exception:  # noqa: BLE001
                pass  # Ignore other errors during disconnect

        self._reader = None
        self._writer = None
        self._connected = False
        _LOGGER.debug("Dongle transport disconnected for %s", self._serial)

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

    def _teardown_connection(self) -> None:
        """Mark the connection broken and close the socket without handshake.

        Used after socket errors and suspected-dead connections so the next
        request (or retry attempt) re-establishes a fresh TCP connection.
        """
        self._connected = False
        self._reader = None
        if self._writer is not None:
            with contextlib.suppress(Exception):
                self._writer.close()
        self._writer = None

    async def _force_reconnect(self) -> None:
        """Tear down the (possibly broken) connection for a fresh start.

        Acquires the per-transaction lock so an in-flight request on another
        task is never yanked mid-transaction.  Reconnection itself is lazy —
        ``_send_receive`` re-establishes the connection on the next request.
        """
        async with self._lock:
            self._teardown_connection()

    async def _send_receive(
        self,
        packet: bytes,
        max_retries: int = 2,
        expected_func: int | None = None,
        expected_register: int | None = None,
        expected_count: int | None = None,
        retry_on_timeout: bool = False,
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

        Returns:
            List of register values from response

        Raises:
            TransportReadError: If send/receive fails after retries
            TransportTimeoutError: If operation times out
            TransportConnectionError: If connecting (or reconnecting) fails
        """
        last_error: TransportReadError | None = None

        async with self._lock:
            for attempt in range(max_retries + 1):
                try:
                    # (Re)connect when there is no live connection: first
                    # use, after _teardown_connection(), or an external
                    # disconnect().  Serialised under self._lock so two
                    # concurrent requests can never race parallel connect()
                    # calls at the dongle's single TCP slot.  connect()
                    # already retries internally with backoff — if it still
                    # fails there is no connectivity, so fail this request
                    # fast instead of burning the remaining attempts on
                    # more connect cycles (keeps link-down probe cycles
                    # bounded to ONE connect sequence).
                    if self._writer is None or self._reader is None or not self._connected:
                        _LOGGER.info(
                            "[%s] Dongle %s:%s disconnected, attempting reconnect",
                            self._serial,
                            self._host,
                            self._port,
                        )
                        await self.connect()
                    if self._writer is None or self._reader is None:
                        raise TransportConnectionError("Socket not initialized")

                    # Drain any pending data before sending (handles unsolicited packets)
                    await self._drain_buffer()

                    # Send packet
                    self._writer.write(packet)
                    await self._writer.drain()

                    # Receive response with slightly longer timeout for dongles
                    response = await asyncio.wait_for(
                        self._reader.read(RECV_BUFFER_SIZE),
                        timeout=self._timeout,
                    )

                    if not response:
                        # recv returned b'' = EOF: the dongle closed the
                        # connection (or the transport died locally).  This
                        # socket can never yield a response again — tear it
                        # down so the retry below (or the next request)
                        # reconnects instead of re-reading a dead socket.
                        self._teardown_connection()
                        if attempt < max_retries:
                            _LOGGER.debug(
                                "[%s] Empty response from dongle (attempt %d/%d), retrying...",
                                self._serial,
                                attempt + 1,
                                max_retries + 1,
                            )
                            # Small delay before retry
                            await asyncio.sleep(0.5)
                            continue
                        # Final attempt failed
                        raise TransportReadError(
                            f"[{self._serial}] Empty response from dongle. This may indicate: "
                            "(1) Dongle firmware is blocking local Modbus access, "
                            "(2) Connection was closed by dongle, or "
                            "(3) Dongle requires more time to respond. "
                            "Try increasing timeout or check dongle firmware version."
                        )

                    # Parse response with cross-request validation.  The
                    # request's own TCP function (packet byte 7) is the
                    # expected response function, so an unsolicited heartbeat
                    # or proxied param frame is rejected as a mismatch rather
                    # than mis-parsed as this reply (#320).
                    return self._parse_response(
                        response,
                        expected_func,
                        expected_register,
                        expected_count,
                        expected_tcp_func=packet[7],
                    )

                except TimeoutError as err:
                    # The connection is suspect after ANY response timeout:
                    # the dongle went mute, or the path dropped silently
                    # (VPN break, NAT/conntrack flush) — half-open TCP
                    # delivers no RST, so writes keep "succeeding" into a
                    # black hole and reads only ever time out.  Tear down
                    # unconditionally so the next request — or the resend
                    # below — dials a fresh connection instead of polling
                    # the dead flow forever (#226).
                    self._teardown_connection()
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
                    self._teardown_connection()

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

        # Minimum response: prefix(2) + version(2) + length(2) + addr(1) + func(1)
        # + dongle(10) + data_len(2) + some data
        if len(response) < 20:
            raise TransportReadError(f"[{self._serial}] Response too short: {len(response)} bytes")

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
                _LOGGER.debug(
                    "[%s] Response TCP function mismatch (%s): %s — misrouted or unsolicited frame",
                    self._serial,
                    label,
                    context,
                )
                raise TransportResponseMismatchError(
                    f"[{self._serial}] Unexpected TCP function "
                    f"0x{response_tcp_func:02x} ({label}): {context} "
                    "— misrouted/unsolicited frame"
                )

        # Extract data length (frame_length and tcp_func available at bytes 4-6 and 7 if needed)
        data_length = struct.unpack("<H", response[18:20])[0]

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

        def _expected_fields() -> str:
            return _format_frame_fields(
                tcp_func=expected_tcp_func,
                func=expected_func,
                register=expected_register,
                count=expected_count,
            )

        # 1. Inverter serial must match (always checked)
        response_serial = data_frame[2:12]
        expected_serial = self._serial.encode("ascii").ljust(10, b"\x00")[:10]
        if response_serial != expected_serial:
            resp_serial_str = response_serial.decode("ascii", errors="replace").rstrip("\x00")
            context = _mismatch_context(
                _expected_fields(),
                _format_frame_fields(func=modbus_func, register=response_register),
            )
            _LOGGER.debug(
                "[%s] Response serial mismatch: expected %s, got %s (%s) "
                "— likely a misrouted cloud response",
                self._serial,
                self._serial,
                resp_serial_str,
                context,
            )
            raise TransportResponseMismatchError(
                f"[{self._serial}] Response serial mismatch: expected {self._serial}, "
                f"got {resp_serial_str} ({context})"
            )

        # 2. Function code must match (mask high bit for exception responses)
        if expected_func is not None:
            response_base_func = modbus_func & 0x7F
            if response_base_func != expected_func:
                context = _mismatch_context(
                    _expected_fields(),
                    _format_frame_fields(func=modbus_func, register=response_register),
                )
                _LOGGER.debug(
                    "[%s] Response function mismatch: %s — likely a misrouted cloud response",
                    self._serial,
                    context,
                )
                raise TransportResponseMismatchError(
                    f"[{self._serial}] Response function mismatch: {context}"
                )

        # 3. Start register must match
        if expected_register is not None and response_register != expected_register:
            context = _mismatch_context(
                _expected_fields(),
                _format_frame_fields(func=modbus_func, register=response_register),
            )
            _LOGGER.debug(
                "[%s] Response register mismatch: %s — likely a misrouted cloud response",
                self._serial,
                context,
            )
            raise TransportResponseMismatchError(
                f"[{self._serial}] Response register mismatch: {context}"
            )

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
            if ack and ack[0] != values[0]:
                raise TransportWriteError(
                    f"Write ACK echo mismatch for register {address}: wrote "
                    f"{values[0]}, ACK echoed {ack[0]} — possible misrouted "
                    "response"
                )
        elif ack and len(ack) == 1 and ack[0] != len(values):
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
    # Operation-level serialisation (self._op_lock)
    # ------------------------------------------------------------------
    # The WiFi dongle processes ONE request at a time over its single TCP
    # connection.  High-level operations that issue multiple sequential
    # register reads release self._lock (per-transaction) between calls,
    # allowing concurrent writes to interleave and confuse the protocol.
    #
    # self._op_lock (a task-reentrant lock from BaseTransport) serialises
    # entire multi-step operations so that writes wait until a read
    # sequence is fully complete — and vice-versa.
    #
    # Re-entrancy is required because write_named_parameters (BaseTransport)
    # calls self.read_parameters + self.write_parameters internally, which
    # also acquire self._op_lock.

    async def read_midbox_runtime(self) -> MidboxRuntimeData:
        """Serialised read of MID/GridBOSS runtime data (5 INPUT + 1 HOLD read)."""
        async with self._op_lock:
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
        async with self._op_lock:
            return await super().read_runtime()

    async def read_all_input_data(
        self,
    ) -> tuple[InverterRuntimeData, InverterEnergyData, BatteryBankData | None]:
        """Serialised combined read of all input register groups."""
        async with self._op_lock:
            return await super().read_all_input_data()

    async def read_parameters(
        self,
        start_address: int,
        count: int,
    ) -> dict[int, int]:
        """Serialised read of holding (configuration) registers."""
        async with self._op_lock:
            return await super().read_parameters(start_address, count)

    async def read_quick_charge_remaining_seconds(self) -> int | None:
        """Serialised read of quick-charge remaining seconds (input reg 210)."""
        async with self._op_lock:
            return await super().read_quick_charge_remaining_seconds()

    async def write_parameters(
        self,
        parameters: dict[int, int],
    ) -> bool:
        """Serialised write of holding (configuration) registers."""
        async with self._op_lock:
            return await super().write_parameters(parameters)

    # Remaining inherited multi-request reads (review): without these
    # overrides a coordinator poll could interleave with a write retry /
    # reconnect teardown on the dongle's single TCP connection.

    async def read_energy(self) -> InverterEnergyData:
        """Serialised energy read (multi-group input read)."""
        async with self._op_lock:
            return await super().read_energy()

    async def read_battery(self, *args: Any, **kwargs: Any) -> Any:
        """Serialised battery read (atomic 120-register input read)."""
        async with self._op_lock:
            return await super().read_battery(*args, **kwargs)

    async def read_serial_number(self) -> str:
        """Serialised device-info read."""
        async with self._op_lock:
            return await super().read_serial_number()

    async def read_firmware_version(self) -> str:
        """Serialised device-info read."""
        async with self._op_lock:
            return await super().read_firmware_version()

    async def read_device_type(self) -> int:
        """Serialised device-info read."""
        async with self._op_lock:
            return await super().read_device_type()

    async def read_parallel_config(self) -> int:
        """Serialised device-info read."""
        async with self._op_lock:
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
            TransportWriteError: If the write sequence fails after all
                attempts.  A ``TransportError`` subclass, so HYBRID-mode
                consumers can still dispatch their cloud API fallback.
            ValueError: If a parameter name is not recognized (not retried).
        """
        async with self._op_lock:
            attempts = self._write_retries + 1
            last_error: TransportError | None = None

            for attempt in range(1, attempts + 1):
                try:
                    result = await super().write_named_parameters(parameters)
                except (
                    TransportConnectionError,
                    TransportReadError,
                    TransportTimeoutError,
                    TransportWriteError,
                ) as err:
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
                        await self._force_reconnect()
                        await asyncio.sleep(WRITE_RETRY_DELAY * attempt)
                    continue

                if not self._verify_writes:
                    return result

                try:
                    mismatches = await self._verify_named_parameters(parameters)
                except TransportError as err:
                    # The write itself was acknowledged by the inverter; a
                    # failed verification READ must not fail the operation.
                    _LOGGER.debug(
                        "Post-write verification read failed for %s (%s); "
                        "write was acknowledged — accepting",
                        sorted(parameters),
                        err,
                    )
                    return result

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
        from pylxpweb.constants.registers import LOCAL_PARAM_SCALE_DIV10, MULTI_BIT_FIELDS

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
                if name in MULTI_BIT_FIELDS:
                    offset, width = MULTI_BIT_FIELDS[name]
                    got_field = (raw >> offset) & ((1 << width) - 1)
                    if got_field != int(value):
                        mismatches.append(f"{name}: wrote {int(value)}, read back {got_field}")
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
