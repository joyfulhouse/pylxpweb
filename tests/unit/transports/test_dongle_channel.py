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
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.transports import create_dongle_transport
from pylxpweb.transports.dongle import (
    MODBUS_READ_INPUT,
    PACKET_PREFIX,
    PROTOCOL_VERSION,
    TCP_FUNC_TRANSLATED,
    DongleTransport,
    compute_crc16,
)
from pylxpweb.transports.dongle_channel import (
    _REGISTRY,
    DongleChannel,
    make_channel_key,
    registered_channel,
)
from pylxpweb.transports.exceptions import (
    DongleChannelLoopError,
    DongleChannelMismatchError,
    TransportReadError,
)

DONGLE = "BA12345678"
SERIAL_A = "CE00000001"
SERIAL_B = "CE00000002"

_FRAME_HEADER = 6


def _build_response(
    inverter_serial: str, modbus_func: int, start_register: int, values: list[int]
) -> bytes:
    """Build a read-layout response frame (same layout as the dongle emits)."""
    data_frame = bytes([0x01, modbus_func]) + inverter_serial.encode("ascii").ljust(10, b"\x00")
    data_frame += struct.pack("<H", start_register)
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
    **kwargs: Any,
) -> DongleTransport:
    return DongleTransport(
        host=host,
        dongle_serial=dongle_serial,
        inverter_serial=inverter_serial,
        port=port,
        timeout=1.0,
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
        assert registered_channel(make_channel_key("127.0.0.1", port, DONGLE)) is a.channel

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
        assert registered_channel(make_channel_key("127.0.0.1", port, DONGLE)) is shared.channel
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
        assert registered_channel(key) is first_channel
        assert first_channel.lease_count == 1

        await b.disconnect()
        await fake.wait_for_connections(0)
        assert b.is_connected is False
        assert registered_channel(key) is None
        assert first_channel.retired is True

        await a.connect()
        assert fake.dials == 2
        assert a.channel is not first_channel
        assert registered_channel(key) is a.channel
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
