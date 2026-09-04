"""Unit tests for the endpoint-scoped shared dongle channel (pylxpweb#329).

Every ``DongleTransport`` targeting the same physical dongle (host:port +
dongle serial) must share ONE serialized TCP socket: the live probe showed a
dongle accepts a second client but evicts it, cross-routes replies, and
degrades the first client's cadence.  These tests drive real
``DongleTransport`` instances against a loopback fake dongle that counts
accepted connections and records the order of request frames.
"""

from __future__ import annotations

import asyncio
import contextlib
import ssl
import struct
import threading
import time
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.transports import create_dongle_transport
from pylxpweb.transports.dongle import (
    MODBUS_READ_HOLDING,
    MODBUS_READ_INPUT,
    MODBUS_WRITE_MULTI,
    MODBUS_WRITE_SINGLE,
    PACKET_PREFIX,
    PROTOCOL_VERSION,
    TCP_FUNC_TRANSLATED,
    DongleTransport,
    compute_crc16,
)
from pylxpweb.transports.dongle_channel import (
    _REGISTRY,
    _REGISTRY_LOCK,
    DongleChannel,
    make_channel_key,
    resolve_shared_channel,
)
from pylxpweb.transports.exceptions import (
    DongleChannelLoopError,
    DongleChannelMismatchError,
    TransportConnectionError,
    TransportReadError,
    TransportTimeoutError,
)

DONGLE = "BA12345678"
SERIAL_A = "CE00000001"
SERIAL_B = "CE00000002"

_FRAME_HEADER = 6


def _build_response(
    inverter_serial: str, modbus_func: int, start_register: int, values: list[int]
) -> bytes:
    """Build a response frame: read layout for FC03/FC04, 16-byte ACK for FC06/FC16."""
    data_frame = bytes([0x01, modbus_func]) + inverter_serial.encode("ascii").ljust(10, b"\x00")
    data_frame += struct.pack("<H", start_register)
    if modbus_func in (MODBUS_WRITE_SINGLE, MODBUS_WRITE_MULTI):
        data_frame += struct.pack("<H", values[0] & 0xFFFF)  # echoed value / register count
    else:
        data_frame += bytes([len(values) * 2])
        for value in values:
            data_frame += struct.pack("<H", value & 0xFFFF)
    packet = PACKET_PREFIX + struct.pack("<H", PROTOCOL_VERSION)
    packet += struct.pack("<H", 14 + len(data_frame) + 2)
    packet += bytes([0x01, TCP_FUNC_TRANSLATED])
    packet += DONGLE.encode("ascii")
    packet += struct.pack("<H", len(data_frame) + 2)
    packet += data_frame + struct.pack("<H", compute_crc16(data_frame))
    return packet


class FakeDongleServer:
    """Loopback dongle: counts dials, records request frames in wire order.

    ``hold`` parks every reply until :meth:`release` so a test can freeze a
    transaction mid-flight; :meth:`drop_all` closes every client socket
    (EOF from the dongle's side).
    """

    def __init__(self) -> None:
        self.dials = 0
        self.open_connections = 0
        self.frames: list[tuple[str, int, int]] = []
        self.hold = False
        self.frame_received = asyncio.Event()
        self._release = asyncio.Event()
        self._writers: set[asyncio.StreamWriter] = set()
        self._server: asyncio.Server | None = None

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return int(self._server.sockets[0].getsockname()[1])

    async def stop(self) -> None:
        await self.drop_all()
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()

    def release(self) -> None:
        self.hold = False
        self._release.set()

    async def drop_all(self) -> None:
        for writer in list(self._writers):
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def wait_for_connections(self, count: int, timeout: float = 2.0) -> None:
        async with asyncio.timeout(timeout):
            while self.open_connections != count:
                await asyncio.sleep(0.005)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.dials += 1
        self.open_connections += 1
        self._writers.add(writer)
        buffer = bytearray()
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                buffer += data
                while len(buffer) >= _FRAME_HEADER:
                    size = _FRAME_HEADER + struct.unpack("<H", buffer[4:6])[0]
                    if len(buffer) < size:
                        break
                    packet = bytes(buffer[:size])
                    del buffer[:size]
                    serial = packet[22:32].decode("ascii").rstrip("\x00")
                    func = packet[21]
                    register, count = struct.unpack("<HH", packet[32:36])
                    self.frames.append((serial, func, register))
                    self.frame_received.set()
                    if self.hold:
                        await self._release.wait()
                    if func == MODBUS_WRITE_SINGLE:
                        values = [count]  # FC06 carries the value where a read carries count
                    elif func == MODBUS_WRITE_MULTI:
                        values = [count]  # FC16 ACK echoes the register count
                    else:
                        values = [register + i for i in range(count)]
                    writer.write(_build_response(serial, func, register, values))
                    await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            self.open_connections -= 1
            self._writers.discard(writer)
            with contextlib.suppress(Exception):
                writer.close()


@pytest.fixture
async def server() -> AsyncIterator[tuple[FakeDongleServer, int]]:
    fake = FakeDongleServer()
    port = await fake.start()
    try:
        yield fake, port
    finally:
        await fake.stop()


def _make(
    port: int,
    inverter_serial: str = SERIAL_A,
    *,
    host: str = "127.0.0.1",
    dongle_serial: str = DONGLE,
    use_ssl: bool | None = False,
    timeout: float = 1.0,
    **kwargs: Any,
) -> DongleTransport:
    return DongleTransport(
        host=host,
        dongle_serial=dongle_serial,
        inverter_serial=inverter_serial,
        port=port,
        timeout=timeout,
        connection_retries=1,
        use_ssl=use_ssl,
        **kwargs,
    )


def _read_packet(transport: DongleTransport, register: int = 0, count: int = 1) -> bytes:
    return transport._build_packet(
        tcp_func=TCP_FUNC_TRANSLATED,
        modbus_func=MODBUS_READ_INPUT,
        start_register=register,
        register_count=count,
    )


async def _shutdown_all(*transports: DongleTransport) -> None:
    for transport in transports:
        await transport.async_shutdown()


# ----------------------------------------------------------------------
# 1 / 2 / 3 — sharing, isolation, opt-out
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_endpoint_shares_one_dial(server: tuple[FakeDongleServer, int]) -> None:
    """Two transports on one host:port:serial dial exactly once and share a channel."""
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    try:
        await asyncio.gather(a.connect(), b.connect())

        assert fake.dials == 1
        assert a.is_connected is True and b.is_connected is True
        assert a.channel is b.channel
        assert a.channel is not None and a.channel.lease_count == 2
        assert _REGISTRY.get(make_channel_key("127.0.0.1", port, DONGLE)) is a.channel

        # Both devices actually talk over the shared socket, addressed by serial.
        assert await a._read_input_registers(0, 2) == [0, 1]
        assert await b._read_input_registers(10, 1) == [10]
        assert fake.frames == [(SERIAL_A, MODBUS_READ_INPUT, 0), (SERIAL_B, MODBUS_READ_INPUT, 10)]
        assert fake.dials == 1
    finally:
        await _shutdown_all(a, b)


@pytest.mark.asyncio
async def test_distinct_endpoints_get_distinct_channels(
    server: tuple[FakeDongleServer, int],
) -> None:
    """A different port is a different dongle: two dials, two channels.

    Host normalization is strip + lowercase only, so a padded host string
    still resolves to the same channel (no third dial).
    """
    fake_one, port_one = server
    fake_two = FakeDongleServer()
    port_two = await fake_two.start()
    a, b, c = _make(port_one), _make(port_two), _make(port_one, SERIAL_B, host=" 127.0.0.1 ")
    try:
        await a.connect()
        await b.connect()
        await c.connect()

        assert fake_one.dials == 1 and fake_two.dials == 1
        assert a.channel is not b.channel
        assert c.channel is a.channel
        assert len([k for k in _REGISTRY if k[2] == DONGLE]) == 2
    finally:
        await _shutdown_all(a, b, c)
        await fake_two.stop()


@pytest.mark.asyncio
async def test_private_channel_opt_out(server: tuple[FakeDongleServer, int]) -> None:
    """``shared_channel=False`` dials its own socket and is never registered."""
    fake, port = server
    shared = _make(port, SERIAL_A)
    private = _make(port, SERIAL_B, shared_channel=False)
    try:
        await shared.connect()
        await private.connect()

        assert fake.dials == 2
        assert private.channel is not shared.channel
        assert private.channel is not None and private.channel.shared is False
        assert _REGISTRY.get(make_channel_key("127.0.0.1", port, DONGLE)) is shared.channel
        assert private.is_connected is True

        await private.disconnect()
        await fake.wait_for_connections(1)
        assert shared.is_connected is True
    finally:
        await _shutdown_all(shared, private)


# ----------------------------------------------------------------------
# 4 — config compatibility
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_incompatible_config_on_same_endpoint_is_rejected(
    server: tuple[FakeDongleServer, int],
) -> None:
    """TLS-mode or dongle-serial mismatch on one host:port is a hard error."""
    fake, port = server
    a = _make(port, SERIAL_A, use_ssl=False)
    tls_mismatch = _make(port, SERIAL_B, use_ssl=None)
    serial_mismatch = _make(port, SERIAL_B, dongle_serial="BA99999999", use_ssl=False)
    try:
        await a.connect()

        with pytest.raises(DongleChannelMismatchError, match="use_ssl"):
            await tls_mismatch.connect()
        with pytest.raises(DongleChannelMismatchError, match="dongle_serial"):
            await serial_mismatch.connect()

        # The existing channel is untouched: still connected, one dial, one lease.
        assert fake.dials == 1
        assert a.is_connected is True
        assert a.channel is not None and a.channel.lease_count == 1
        assert tls_mismatch.is_connected is False and serial_mismatch.is_connected is False
        assert await a._read_input_registers(0, 1) == [0]
    finally:
        await _shutdown_all(a, tls_mismatch, serial_mismatch)


# ----------------------------------------------------------------------
# 5 / 6 — lease lifecycle
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_last_lease_release_closes_and_retires(
    server: tuple[FakeDongleServer, int],
) -> None:
    """A's release keeps the socket for B; B's release closes it and retires the channel."""
    fake, port = server
    key = make_channel_key("127.0.0.1", port, DONGLE)
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    try:
        await a.connect()
        await b.connect()
        first_channel = a.channel
        assert first_channel is not None

        await a.disconnect()
        assert b.is_connected is True
        assert fake.open_connections == 1
        assert _REGISTRY.get(key) is first_channel
        assert first_channel.lease_count == 1

        await b.disconnect()
        await fake.wait_for_connections(0)
        assert b.is_connected is False
        assert _REGISTRY.get(key) is None
        assert first_channel.retired is True

        await a.connect()
        assert fake.dials == 2
        assert a.channel is not first_channel
        assert _REGISTRY.get(key) is a.channel
        assert await a._read_input_registers(3, 1) == [3]
    finally:
        await _shutdown_all(a, b)


@pytest.mark.asyncio
async def test_lease_acquire_and_release_are_idempotent(
    server: tuple[FakeDongleServer, int],
) -> None:
    """connect() twice = one lease; disconnect() twice = one release; shutdown after = no-op."""
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    try:
        await a.connect()
        await a.connect()
        channel = a.channel
        assert channel is not None and channel.lease_count == 1

        await b.connect()
        assert channel.lease_count == 2

        await a.disconnect()
        await a.disconnect()
        assert channel.lease_count == 1
        assert b.is_connected is True
        assert fake.open_connections == 1

        await a.async_shutdown()
        assert channel.lease_count == 1
        assert b.is_connected is True
        assert fake.open_connections == 1
        assert await b._read_input_registers(0, 1) == [0]

        await b.disconnect()
        await fake.wait_for_connections(0)
        assert channel.lease_count == 0
        assert fake.dials == 1
    finally:
        await _shutdown_all(a, b)


# ----------------------------------------------------------------------
# 7 — failure propagation
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_server_eof_propagates_to_every_lease(
    server: tuple[FakeDongleServer, int],
) -> None:
    """EOF mid-transaction: both leases see disconnected, generation bumps, next call redials."""
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    try:
        await a.connect()
        await b.connect()
        channel = a.channel
        assert channel is not None
        generation = channel.generation

        fake.hold = True
        pending = asyncio.create_task(
            b._send_receive(
                _read_packet(b),
                max_retries=0,
                expected_func=MODBUS_READ_INPUT,
                expected_register=0,
            )
        )
        await asyncio.wait_for(fake.frame_received.wait(), timeout=1.0)
        await fake.drop_all()

        with pytest.raises(TransportReadError):
            await pending
        fake.release()

        assert a.is_connected is False and b.is_connected is False
        assert channel.generation > generation
        assert channel.lease_count == 2

        # The next transaction on any lease redials the shared socket.
        assert await a._read_input_registers(0, 1) == [0]
        assert fake.dials == 2
        assert a.is_connected is True and b.is_connected is True
    finally:
        await _shutdown_all(a, b)


# ----------------------------------------------------------------------
# 8 — operation-level serialisation across devices
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_step_operations_do_not_interleave_across_devices(
    server: tuple[FakeDongleServer, int],
) -> None:
    """Every step of one device's operation reaches the wire before the other's first."""
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    try:
        await a.connect()
        await b.connect()

        # read_parameters(0, 80) is two FC03 transactions (0/40, 40/40).
        result_a, result_b = await asyncio.gather(
            a.read_parameters(0, 80), b.read_parameters(0, 80)
        )

        assert result_a == {i: i for i in range(80)}
        assert result_b == {i: i for i in range(80)}
        serials = [frame[0] for frame in fake.frames]
        assert len(serials) == 4
        assert serials[0] == serials[1] and serials[2] == serials[3], serials
        assert serials[0] != serials[2], serials
    finally:
        await _shutdown_all(a, b)


# ----------------------------------------------------------------------
# 9 — bounded shutdown while a sibling owns the transaction
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_is_bounded_and_leaves_sibling_transaction_intact(
    server: tuple[FakeDongleServer, int],
) -> None:
    """A's shutdown returns fast; B's in-flight transaction still completes on the same stream."""
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    try:
        await a.connect()
        await b.connect()

        fake.hold = True
        pending = asyncio.create_task(b._read_input_registers(5, 2))
        await asyncio.wait_for(fake.frame_received.wait(), timeout=1.0)

        await asyncio.wait_for(a.async_shutdown(), timeout=0.5)
        assert a.is_connected is False
        assert not pending.done()

        fake.release()
        assert await pending == [5, 6]
        assert await b._read_input_registers(7, 1) == [7]
        assert fake.dials == 1
        assert b.is_connected is True
    finally:
        await _shutdown_all(a, b)


# ----------------------------------------------------------------------
# 10 — single event loop
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_from_another_running_loop_raises(
    server: tuple[FakeDongleServer, int],
) -> None:
    """A channel is single-loop: attaching from a second live loop is refused."""
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    try:
        await a.connect()

        def connect_on_other_loop() -> None:
            asyncio.run(b.connect())

        with pytest.raises(DongleChannelLoopError, match="different running event loop"):
            await asyncio.to_thread(connect_on_other_loop)

        assert fake.dials == 1
        assert a.is_connected is True
        assert a.channel is not None and a.channel.lease_count == 1
    finally:
        await _shutdown_all(a)


# ----------------------------------------------------------------------
# 11 — TLS-PSK detection memo is per socket
# ----------------------------------------------------------------------


def _mock_socket() -> tuple[AsyncMock, MagicMock]:
    reader = AsyncMock()
    reader.read = AsyncMock(side_effect=TimeoutError())
    writer = MagicMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    return reader, writer


@pytest.mark.asyncio
async def test_tls_unsupported_memo_is_shared_between_leases() -> None:
    """Once one lease records 'no TLS-PSK', a sibling's later dial goes straight to plaintext."""
    a = DongleTransport("host", DONGLE, SERIAL_A)
    b = DongleTransport("host", DONGLE, SERIAL_B)
    context = MagicMock()
    open_connection = AsyncMock(
        side_effect=[ssl.SSLError("wrong version"), _mock_socket(), _mock_socket()]
    )
    try:
        with (
            patch.object(DongleTransport, "_ssl_ctx", return_value=context),
            patch("asyncio.open_connection", open_connection),
            patch("asyncio.sleep", AsyncMock()),
            patch("pylxpweb.transports.dongle.time.monotonic", return_value=10.0),
        ):
            await a.connect()
            assert a.channel is not None and a.channel.ssl_unsupported_until == 86410.0

            # Lose the socket but keep A's lease: the channel (and its memo) survive.
            await a._force_reconnect()
            assert a.is_connected is False

            await b.connect()

        assert b.channel is a.channel
        assert [call.kwargs.get("ssl") for call in open_connection.await_args_list] == [
            context,
            None,
            None,
        ]
    finally:
        await _shutdown_all(a, b)


# ----------------------------------------------------------------------
# 12 — no write replay on cancellation
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancelled_transaction_is_never_replayed(
    server: tuple[FakeDongleServer, int],
) -> None:
    """Cancelling a transaction mid-flight sends the request exactly once."""
    fake, port = server
    a = _make(port, SERIAL_A)
    try:
        await a.connect()

        fake.hold = True
        pending = asyncio.create_task(a._read_input_registers(0, 1))
        await asyncio.wait_for(fake.frame_received.wait(), timeout=1.0)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        fake.release()
        await asyncio.sleep(0.05)

        assert fake.frames == [(SERIAL_A, MODBUS_READ_INPUT, 0)]
        assert a.channel is not None and a.channel.transaction_owner is None

        # The stream is still usable: the next request is a fresh frame, not a replay.
        assert await a._read_input_registers(1, 1) == [1]
        assert fake.frames == [(SERIAL_A, MODBUS_READ_INPUT, 0), (SERIAL_A, MODBUS_READ_INPUT, 1)]
        assert fake.dials == 1
    finally:
        await _shutdown_all(a)


# ----------------------------------------------------------------------
# 13 — default-on through the public factory
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_factory_transports_share_by_default() -> None:
    """Two devices created via create_dongle_transport against one endpoint dial once."""
    open_connection = AsyncMock(return_value=_mock_socket())
    a = create_dongle_transport("192.168.1.50", DONGLE, SERIAL_A)
    b = create_dongle_transport("192.168.1.50", DONGLE, SERIAL_B)
    try:
        with (
            patch.object(DongleTransport, "_ssl_ctx", return_value=None),
            patch("asyncio.open_connection", open_connection),
        ):
            await asyncio.gather(a.connect(), b.connect())

        assert open_connection.await_count == 1
        assert a.channel is b.channel
        assert isinstance(a.channel, DongleChannel)
        assert a.is_connected is True and b.is_connected is True
    finally:
        await _shutdown_all(a, b)


# ----------------------------------------------------------------------
# Tribunal round 1 (PR #330): lease membership, retirement races, dials,
# zombie channels, registry thread-safety, write non-replay, generation.
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unleased_sibling_takes_a_lease_before_using_the_socket(
    server: tuple[FakeDongleServer, int],
) -> None:
    """A transport that never called connect() leases the live socket on first use.

    Without that lease the refcount would be 1 for two active devices and
    A's release would close the socket underneath B.
    """
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    try:
        await a.connect()
        channel = a.channel
        assert channel is not None

        assert await b._read_input_registers(0, 1) == [0]
        assert channel.holds_lease(b)
        assert channel.lease_count == 2

        await a.disconnect()
        assert fake.open_connections == 1
        assert b.is_connected is True
        assert await b._read_input_registers(1, 1) == [1]
        assert fake.dials == 1
    finally:
        await _shutdown_all(a, b)


@pytest.mark.asyncio
async def test_is_connected_requires_own_lease(server: tuple[FakeDongleServer, int]) -> None:
    """A sibling's live socket does not make an un-leased transport connected."""
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    try:
        await a.connect()
        assert b.is_connected is False  # bound or not, B holds no lease yet

        await b.connect()
        await a.disconnect()
        assert a.is_connected is False
        assert b.is_connected is True

        # A's next operation re-leases the still-open socket without a dial.
        assert await a._read_input_registers(2, 1) == [2]
        assert a.is_connected is True
        assert a.channel is not None and a.channel.holds_lease(a)
        assert fake.dials == 1
    finally:
        await _shutdown_all(a, b)


@pytest.mark.asyncio
async def test_queued_waiter_keeps_its_channel_across_last_lease_release(
    server: tuple[FakeDongleServer, int],
) -> None:
    """A waiter queued on the transaction lock is a user: the channel is not retired under it.

    Otherwise B wakes holding the OLD channel's lock, reconnects on a NEW
    channel, and does I/O unserialized against C on that new channel.
    """
    fake, port = server
    a, b, c = _make(port, SERIAL_A), _make(port, SERIAL_B), _make(port, "CE00000003")
    try:
        await a.connect()
        old = a.channel
        assert old is not None
        assert b._resolve_channel() is old

        release_a = asyncio.create_task(a.disconnect())  # last lease: closes the socket
        await asyncio.sleep(0)  # parked in wait_closed() holding the transaction lock
        assert old.transaction_lock.locked()

        read_b = asyncio.create_task(b._read_input_registers(0, 1))
        await asyncio.sleep(0)  # queued behind A on old.transaction_lock
        assert old._users == 1

        await release_a
        assert old.retired is False
        assert await read_b == [0]
        assert b.channel is old

        assert await c._read_input_registers(1, 1) == [1]
        assert c.channel is old
        assert c.channel.transaction_lock is b.channel.transaction_lock
        assert fake.dials == 2
    finally:
        await _shutdown_all(a, b, c)


@pytest.mark.asyncio
async def test_shutdown_spares_a_sibling_dial(server: tuple[FakeDongleServer, int]) -> None:
    """A's terminal shutdown must not close the socket B is in the middle of dialing."""
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    try:
        await a.connect()
        channel = a.channel
        assert channel is not None
        await a._force_reconnect()  # socket torn down, A still leased

        connect_b = asyncio.create_task(b.connect())
        await asyncio.sleep(0.05)  # B is inside the dial (initial-data window)
        assert channel.connect_lock.locked()

        await asyncio.wait_for(a.async_shutdown(), timeout=0.5)
        await connect_b

        assert b.is_connected is True
        assert fake.open_connections == 1
        assert await b._read_input_registers(0, 1) == [0]
        assert fake.dials == 2
    finally:
        await _shutdown_all(a, b)


@pytest.mark.asyncio
async def test_disconnect_spares_a_sibling_dial(server: tuple[FakeDongleServer, int]) -> None:
    """A's last-lease disconnect re-checks under the connect lock: B's fresh socket survives."""
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    try:
        await a.connect()
        channel = a.channel
        assert channel is not None
        await a._force_reconnect()

        connect_b = asyncio.create_task(b.connect())
        await asyncio.sleep(0.05)
        assert channel.connect_lock.locked()

        await a.disconnect()
        await connect_b

        assert b.is_connected is True
        assert fake.open_connections == 1
        assert await b._read_input_registers(0, 1) == [0]
        assert fake.dials == 2
    finally:
        await _shutdown_all(a, b)


@pytest.mark.asyncio
async def test_disconnect_racing_own_connect_leaves_no_lease(
    server: tuple[FakeDongleServer, int],
) -> None:
    """disconnect() racing this transport's own connect() wins and drops the lease it took."""
    fake, port = server
    a = _make(port, SERIAL_A)
    key = make_channel_key("127.0.0.1", port, DONGLE)
    try:
        connect_a = asyncio.create_task(a.connect())
        await asyncio.sleep(0.05)  # inside the dial
        channel = a.channel
        assert channel is not None and channel.connect_lock.locked()

        await a.disconnect()
        await connect_a

        assert channel.lease_count == 0
        assert a.is_connected is False
        assert channel.retired is True
        assert _REGISTRY.get(key) is None
        await fake.wait_for_connections(0)
    finally:
        await _shutdown_all(a)


@pytest.mark.asyncio
async def test_failed_connect_does_not_pin_endpoint_config(
    server: tuple[FakeDongleServer, int],
) -> None:
    """A failed dial retires its lease-less channel; a corrected config attaches afterwards."""
    fake, port = server
    key = make_channel_key("127.0.0.1", port, DONGLE)
    a = _make(port, SERIAL_A, use_ssl=False)
    b = _make(port, SERIAL_B, use_ssl=None)
    try:
        with (
            patch("asyncio.open_connection", side_effect=ConnectionRefusedError("refused")),
            pytest.raises(TransportConnectionError),
        ):
            await a.connect()

        assert a.channel is not None and a.channel.retired is True
        assert _REGISTRY.get(key) is None

        with patch.object(DongleTransport, "_ssl_ctx", return_value=None):
            await b.connect()
        assert b.is_connected is True
        assert fake.dials == 1
    finally:
        await _shutdown_all(a, b)


def test_registry_lock_serialises_resolve_across_threads() -> None:
    """resolve_shared_channel() cannot run while another thread holds the registry lock."""
    key = make_channel_key("registry-lock-host", 8000, DONGLE)
    resolved = threading.Event()

    def resolve_in_thread() -> None:
        resolve_shared_channel(key, ssl_mode=False)
        resolved.set()

    worker = threading.Thread(target=resolve_in_thread, name="resolver")
    try:
        with _REGISTRY_LOCK:
            worker.start()
            assert resolved.wait(0.2) is False  # blocked behind the lock
            assert _REGISTRY.get(key) is None
        assert resolved.wait(2.0) is True
        assert _REGISTRY.get(key) is not None
    finally:
        worker.join(2.0)
        _REGISTRY.pop(key, None)


def test_simultaneous_first_attach_from_two_threads_creates_one_channel() -> None:
    """Two loops on two threads racing the first attach yield ONE channel, ONE socket.

    Channel creation is slowed so the second thread's lookup lands inside
    the check-then-create window, and the winner's dial is held until the
    other thread has resolved, so the winner's loop is provably alive when
    the loser looks.  The loser must get the single-loop rejection, never a
    second socket.
    """
    host = "two-threads-host"
    key = make_channel_key(host, 8000, DONGLE)
    transports = {
        "a": DongleTransport(host, DONGLE, SERIAL_A, use_ssl=False, connection_retries=1),
        "b": DongleTransport(host, DONGLE, SERIAL_B, use_ssl=False, connection_retries=1),
    }
    start = threading.Barrier(2)
    resolved = {name: threading.Event() for name in transports}
    original_init = DongleChannel.__init__
    original_resolve = DongleTransport._resolve_channel

    def slow_init(self: DongleChannel, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        time.sleep(0.05)  # widen the check-then-create window

    def resolve_then_signal(transport: DongleTransport) -> DongleChannel:
        try:
            return original_resolve(transport)
        finally:
            resolved[threading.current_thread().name].set()

    async def open_connection(*args: Any, **kwargs: Any) -> tuple[AsyncMock, MagicMock]:
        me = threading.current_thread().name
        for name, event in resolved.items():
            if name != me:
                event.wait(2.0)  # keep this loop alive until the other thread has looked
        return _mock_socket()

    results: dict[str, object] = {}

    def attach(name: str) -> None:
        start.wait(2.0)
        try:
            asyncio.run(transports[name].connect())
            results[name] = "ok"
        except Exception as err:
            results[name] = err

    threads = [threading.Thread(target=attach, args=(name,), name=name) for name in transports]
    try:
        with (
            patch.object(DongleChannel, "__init__", slow_init),
            patch.object(DongleTransport, "_resolve_channel", resolve_then_signal),
            patch.object(DongleTransport, "_ssl_ctx", return_value=None),
            patch("asyncio.open_connection", side_effect=open_connection) as opened,
        ):
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(5.0)

        outcomes = sorted(results.values(), key=lambda r: isinstance(r, str))
        assert outcomes[1] == "ok", results
        assert isinstance(outcomes[0], DongleChannelLoopError), results
        assert opened.await_count == 1
        assert len([k for k in _REGISTRY if k == key]) == 1
    finally:
        _REGISTRY.pop(key, None)


@pytest.mark.asyncio
async def test_cancelled_write_is_never_replayed(server: tuple[FakeDongleServer, int]) -> None:
    """Cancelling an FC06 write after the frame is on the wire sends it exactly once."""
    fake, port = server
    a = _make(port, SERIAL_A)
    try:
        await a.connect()

        fake.hold = True
        pending = asyncio.create_task(a._write_holding_registers(21, [1]))
        await asyncio.wait_for(fake.frame_received.wait(), timeout=2.0)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        fake.release()
        await asyncio.sleep(0.05)

        assert fake.frames == [(SERIAL_A, MODBUS_WRITE_SINGLE, 21)]
        assert await a._read_input_registers(1, 1) == [1]
        assert fake.frames == [
            (SERIAL_A, MODBUS_WRITE_SINGLE, 21),
            (SERIAL_A, MODBUS_READ_INPUT, 1),
        ]
    finally:
        await _shutdown_all(a)


@pytest.mark.asyncio
async def test_write_ack_timeout_is_never_resent(server: tuple[FakeDongleServer, int]) -> None:
    """An FC06 write whose ACK never arrives is torn down, never resent on the wire."""
    fake, port = server
    a = _make(port, SERIAL_A, timeout=0.3)
    try:
        await a.connect()

        fake.hold = True
        with pytest.raises(TransportTimeoutError):
            await a._write_holding_registers(21, [1])
        fake.release()
        await asyncio.sleep(0.05)

        assert fake.frames == [(SERIAL_A, MODBUS_WRITE_SINGLE, 21)]
        assert a.is_connected is False
        assert fake.dials == 1
    finally:
        await _shutdown_all(a)


@pytest.mark.asyncio
async def test_generation_change_mid_transaction_fails_coherently(
    server: tuple[FakeDongleServer, int],
) -> None:
    """A frame that arrives after the socket was replaced is discarded, not parsed."""
    fake, port = server
    a = _make(port, SERIAL_A)
    try:
        await a.connect()
        channel = a.channel
        assert channel is not None
        stale = _build_response(SERIAL_A, MODBUS_READ_INPUT, 0, [0])

        async def receive_after_replacement() -> bytes:
            await channel.teardown()  # socket replaced underneath the transaction
            return stale

        with (
            patch.object(a, "_receive_frame", receive_after_replacement),
            pytest.raises(TransportReadError, match="replaced mid-transaction"),
        ):
            await a._send_receive(
                _read_packet(a), max_retries=0, expected_func=MODBUS_READ_INPUT, expected_register=0
            )

        assert a.is_connected is False
        assert await a._read_input_registers(0, 1) == [0]  # next request redials cleanly
        assert fake.dials == 2
    finally:
        await _shutdown_all(a)


@pytest.mark.asyncio
async def test_last_lease_shutdown_holds_connect_lock_through_close(
    server: tuple[FakeDongleServer, int],
) -> None:
    """A sibling that dials while the last-lease shutdown is still closing waits for it.

    ``close()`` detaches the writer before ``wait_closed()`` yields; without
    the connect lock a sibling could resolve the still-registered channel,
    see it disconnected, and dial a second socket while the old one is
    still closing — the overlapping-client state the dongle punishes.
    """
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    release_close = asyncio.Event()
    try:
        await a.connect()
        channel = a.channel
        assert channel is not None and channel.writer is not None
        original_wait_closed = channel.writer.wait_closed

        async def blocked_wait_closed() -> None:
            await release_close.wait()
            await original_wait_closed()

        with patch.object(channel.writer, "wait_closed", blocked_wait_closed):
            shutdown_a = asyncio.create_task(a.async_shutdown())
            await asyncio.sleep(0)  # parked inside close(): writer detached, wait_closed blocked
            assert not shutdown_a.done()
            assert channel.connected is False

            connect_b = asyncio.create_task(b.connect())
            await asyncio.sleep(0.05)
            # The sibling's dial is ordered after the close, not overlapping it.
            assert fake.dials == 1
            assert not connect_b.done()

            release_close.set()
            await asyncio.wait_for(shutdown_a, timeout=0.5)
            await connect_b

        assert fake.dials == 2
        assert b.is_connected is True
        assert await b._read_input_registers(0, 1) == [0]
    finally:
        await _shutdown_all(a, b)


@pytest.mark.asyncio
async def test_shutdown_of_transaction_owner_spares_sibling_dial(
    server: tuple[FakeDongleServer, int],
) -> None:
    """Owning the transaction is not owning the dial: a queued connect must not close B's socket.

    A holds the transaction lock inside ``_send_receive`` while its inner
    ``connect()`` waits on the connect lock that B holds in a direct dial.
    A's terminal shutdown must release its lease and leave B's fresh socket
    alone; A's queued connect then raises on resume.
    """
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    try:
        await a.connect()
        channel = a.channel
        assert channel is not None
        await a._force_reconnect()  # A leased, socket torn down

        connect_b = asyncio.create_task(b.connect())
        await asyncio.sleep(0.05)  # B is inside the dial, holding the connect lock
        assert channel.connect_owner is b

        read_a = asyncio.create_task(a._read_input_registers(0, 1))
        await asyncio.sleep(0)  # A owns the transaction; its inner connect() is queued
        assert channel.transaction_owner is a
        assert a in channel.connect_waiters
        dials_before = fake.dials

        await asyncio.wait_for(a.async_shutdown(), timeout=0.5)

        await connect_b
        assert b.is_connected is True
        assert fake.dials == dials_before
        assert fake.open_connections == 1
        with pytest.raises(TransportConnectionError, match="shut down"):
            await read_a
        assert await b._read_input_registers(0, 1) == [0]
        assert fake.dials == dials_before
    finally:
        await _shutdown_all(a, b)


@pytest.mark.asyncio
async def test_last_lease_shutdown_does_not_queue_behind_a_woken_dialer(
    server: tuple[FakeDongleServer, int],
) -> None:
    """A woken-but-not-yet-running connect waiter must not capture the shutdown.

    ``asyncio.Lock.acquire()`` queues a new acquirer behind existing waiters
    even when ``locked()`` is False, so the last-lease branch must not take
    the connect lock while a sibling is queued on it — shutdown would wait
    out the sibling's whole dial.
    """
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    try:
        await a.connect()
        channel = a.channel
        assert channel is not None
        await a._force_reconnect()  # A leased, socket torn down

        await channel.connect_lock.acquire()  # stand-in for a holder about to release
        connect_b = asyncio.create_task(b.connect())
        await asyncio.sleep(0)  # B queued on the connect lock
        assert b in channel.connect_waiters
        channel.connect_lock.release()  # B is woken but has not run yet

        async with asyncio.timeout(0.5):
            await a.async_shutdown()  # awaited inline: runs before B resumes

        await connect_b
        assert b.is_connected is True
        assert fake.open_connections == 1
        assert fake.dials == 2
        assert await b._read_input_registers(0, 1) == [0]
    finally:
        await _shutdown_all(a, b)


@pytest.mark.asyncio
async def test_shutdown_error_path_does_not_tear_down_sibling_stream(
    server: tuple[FakeDongleServer, int],
) -> None:
    """A's own transaction, woken by A's shutdown, must not repair over B's new socket.

    Sequence: A owns an in-flight transaction; A's shutdown closes the
    stream (``wait_closed`` held open); B connects.  B must not dial until
    the close completes, A's transaction must exit promptly with the
    shutdown error instead of queuing a teardown behind B's dial, and B's
    socket must survive A's error path (no redial on B's next read).
    """
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    release_close = asyncio.Event()
    try:
        await a.connect()
        channel = a.channel
        assert channel is not None and channel.writer is not None
        original_wait_closed = channel.writer.wait_closed

        async def blocked_wait_closed() -> None:
            await release_close.wait()
            await original_wait_closed()

        fake.hold = True
        read_a = asyncio.create_task(a._read_input_registers(0, 1))
        await asyncio.wait_for(fake.frame_received.wait(), timeout=1.0)
        assert channel.transaction_owner is a

        with patch.object(channel.writer, "wait_closed", blocked_wait_closed):
            shutdown_a = asyncio.create_task(a.async_shutdown())
            await asyncio.sleep(0)  # parked inside close(): writer detached, wait_closed blocked
            assert not shutdown_a.done()

            connect_b = asyncio.create_task(b.connect())
            await asyncio.sleep(0.05)
            assert fake.dials == 1  # B is ordered after the close
            assert not connect_b.done()

            release_close.set()
            await asyncio.wait_for(shutdown_a, timeout=0.5)

        # B is now dialing (initial-data window).  A's transaction must exit
        # with the shutdown error NOW — not after queuing a teardown behind
        # B's dial and running it over B's fresh socket.
        with pytest.raises(TransportConnectionError, match="shut down"):
            await asyncio.wait_for(read_a, timeout=0.3)

        await connect_b
        fake.release()  # A's parked handler can now observe A's EOF
        await fake.wait_for_connections(1)
        assert b.is_connected is True
        assert fake.dials == 2
        assert await b._read_input_registers(0, 1) == [0]
        assert fake.dials == 2  # B's socket survived; no redial
    finally:
        await _shutdown_all(a, b)


@pytest.mark.asyncio
async def test_teardown_is_scoped_to_the_stream_it_ran_on(
    server: tuple[FakeDongleServer, int],
) -> None:
    """A teardown for a stale generation leaves the current stream alone."""
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    try:
        await a.connect()
        await b.connect()
        channel = a.channel
        assert channel is not None
        current = channel.generation

        await a._teardown_connection(expected_generation=current - 1)  # someone re-dialed since
        assert a.is_connected is True and b.is_connected is True
        assert fake.open_connections == 1
        assert channel.generation == current

        await a._teardown_connection(expected_generation=current)
        assert a.is_connected is False and b.is_connected is False
        await fake.wait_for_connections(0)
    finally:
        await _shutdown_all(a, b)


@pytest.mark.asyncio
async def test_shutdown_does_not_wait_behind_own_error_teardown(
    server: tuple[FakeDongleServer, int],
) -> None:
    """Own transaction already in error teardown holds the connect lock: no queuing on it."""
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    release_close = asyncio.Event()
    try:
        await a.connect()
        await b.connect()
        channel = a.channel
        assert channel is not None and channel.writer is not None
        original_wait_closed = channel.writer.wait_closed

        async def blocked_wait_closed() -> None:
            await release_close.wait()
            await original_wait_closed()

        with patch.object(channel.writer, "wait_closed", blocked_wait_closed):
            fake.hold = True
            read_a = asyncio.create_task(a._read_input_registers(0, 1))
            await asyncio.wait_for(fake.frame_received.wait(), timeout=1.0)
            await fake.drop_all()  # EOF -> A's handler enters teardown(), parked in wait_closed
            await asyncio.sleep(0.05)
            assert channel.transaction_owner is a
            assert channel.connect_lock.locked() and channel.connect_owner is None

            await asyncio.wait_for(a.async_shutdown(), timeout=0.3)
            assert channel.connect_lock.locked()  # the teardown is still the holder
            release_close.set()

        with pytest.raises(TransportConnectionError, match="shut down"):
            await read_a
        fake.release()

        assert b.is_connected is False
        await b.connect()
        assert b.is_connected is True
        assert await b._read_input_registers(0, 1) == [0]
        assert fake.dials == 2
    finally:
        await _shutdown_all(a, b)


@pytest.mark.asyncio
async def test_shutdown_does_not_wait_behind_sibling_disconnect_close(
    server: tuple[FakeDongleServer, int],
) -> None:
    """A sibling's last-lease disconnect holds the connect lock: return, never close again."""
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    key = make_channel_key("127.0.0.1", port, DONGLE)
    release_close = asyncio.Event()
    try:
        await a.connect()
        await b.connect()
        channel = a.channel
        assert channel is not None and channel.writer is not None
        await a.disconnect()  # B is the last lease; A stays bound, lease-less
        writer = channel.writer
        original_wait_closed = writer.wait_closed
        closes = 0

        async def blocked_wait_closed() -> None:
            nonlocal closes
            closes += 1
            await release_close.wait()
            await original_wait_closed()

        with patch.object(writer, "wait_closed", blocked_wait_closed):
            disconnect_b = asyncio.create_task(b.disconnect())
            await asyncio.sleep(0)  # inside B's lock-held close, parked in wait_closed
            assert channel.connect_lock.locked() and channel.connect_owner is None
            assert channel.lease_count == 0

            generation = channel.generation
            await asyncio.wait_for(a.async_shutdown(), timeout=0.3)
            assert channel.generation == generation  # no second close from A
            assert channel.retired is False  # B's disconnect still holds the lock
            release_close.set()
            await disconnect_b
            assert closes == 1

        assert channel.retired is True
        assert _REGISTRY.get(key) is None
        await fake.wait_for_connections(0)
    finally:
        await _shutdown_all(a, b)


@pytest.mark.asyncio
async def test_shutdown_with_own_connect_woken_spares_the_new_live_stream(
    server: tuple[FakeDongleServer, int],
) -> None:
    """A's queued connect() is woken (B just finished dialing): shutdown spares B's stream."""
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    try:
        await a.connect()
        await b.connect()
        channel = a.channel
        assert channel is not None
        await a.disconnect()  # A lease-less; B leased on the live socket

        await channel.connect_lock.acquire()  # stand-in for B's dial in progress
        read_a = asyncio.create_task(a._read_input_registers(0, 1))
        await asyncio.sleep(0)  # A owns the transaction; its inner connect() is queued
        assert channel.transaction_owner is a and a in channel.connect_waiters
        channel.connect_lock.release()  # "dial finished": A is woken but has not run

        async with asyncio.timeout(0.5):
            await a.async_shutdown()  # same turn, before A's connect() resumes

        with pytest.raises(TransportConnectionError, match="shut down"):
            await read_a
        assert b.is_connected is True
        assert fake.open_connections == 1
        assert await b._read_input_registers(0, 1) == [0]
        assert fake.dials == 1  # B's live stream survived; no redial
    finally:
        await _shutdown_all(a, b)


@pytest.mark.asyncio
async def test_check_link_is_serialised_with_sibling_operations(
    server: tuple[FakeDongleServer, int],
) -> None:
    """A link probe on A cannot slip between the steps of B's multi-step read."""
    fake, port = server
    a, b = _make(port, SERIAL_A), _make(port, SERIAL_B)
    try:
        await a.connect()
        await b.connect()
        channel = a.channel
        assert channel is not None
        generation = channel.generation

        # read_parameters(0, 80) is two FC03 steps; the probe is one FC04.
        result_b, link_up = await asyncio.gather(b.read_parameters(0, 80), a.check_link())

        assert link_up is True
        assert result_b == {i: i for i in range(80)}
        assert channel.generation == generation  # no mid-op teardown
        assert fake.dials == 1
        assert [frame[0] for frame in fake.frames].count(SERIAL_B) == 2
        b_steps = [i for i, frame in enumerate(fake.frames) if frame[0] == SERIAL_B]
        assert b_steps[1] == b_steps[0] + 1, fake.frames  # B's steps are adjacent on the wire
        assert (SERIAL_A, MODBUS_READ_INPUT, 0) in fake.frames
        assert all(frame[1] == MODBUS_READ_HOLDING for frame in fake.frames if frame[0] == SERIAL_B)
    finally:
        await _shutdown_all(a, b)
