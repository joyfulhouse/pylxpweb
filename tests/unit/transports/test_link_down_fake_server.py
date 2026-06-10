"""Live-ish link-down test against a minimal fake Modbus TCP server.

Exercises the full stack — pymodbus client -> ModbusTransport ->
BaseInverter.refresh() — through an attach / read-OK / server-killed /
link-down / server-restarted / recovered lifecycle (eg4-57g).

The fake server speaks just enough Modbus TCP (MBAP framing, FC 03/04)
to satisfy the combined input read, answering every request with
zero-filled registers.
"""

from __future__ import annotations

import asyncio
import contextlib
import struct

import pytest

from pylxpweb.devices.base import TRANSPORT_LINK_DOWN_THRESHOLD
from pylxpweb.devices.inverters.generic import GenericInverter
from pylxpweb.transports.modbus import ModbusTransport


class FakeModbusServer:
    """Minimal Modbus TCP server answering FC 03/04 with zero registers."""

    def __init__(self) -> None:
        self._server: asyncio.AbstractServer | None = None
        self._writers: set[asyncio.StreamWriter] = set()
        self.port: int = 0
        self.request_count: int = 0

    async def start(self, port: int = 0) -> None:
        """Start listening on 127.0.0.1 (ephemeral port unless given)."""
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", port)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Stop listening and sever every live client connection.

        Writers are closed BEFORE awaiting ``wait_closed()``: on Python
        3.12+ ``Server.wait_closed()`` blocks until all connection
        handlers finish, and the handlers only exit once their reader
        hits EOF.
        """
        if self._server is not None:
            self._server.close()
        for writer in list(self._writers):
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
        self._writers.clear()
        if self._server is not None:
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writers.add(writer)
        try:
            while True:
                # MBAP header: transaction(2) protocol(2) length(2) unit(1)
                header = await reader.readexactly(7)
                tid, pid, length, uid = struct.unpack(">HHHB", header)
                pdu = await reader.readexactly(length - 1)
                fc = pdu[0]
                if fc in (3, 4) and len(pdu) >= 5:
                    (count,) = struct.unpack(">H", pdu[3:5])
                    self.request_count += 1
                    data = b"\x00\x00" * count
                    resp_pdu = bytes([fc, len(data)]) + data
                else:
                    # Illegal function exception for anything else
                    resp_pdu = bytes([fc | 0x80, 0x01])
                resp = struct.pack(">HHHB", tid, pid, len(resp_pdu) + 1, uid) + resp_pdu
                writer.write(resp)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError, OSError):
            pass
        finally:
            self._writers.discard(writer)
            with contextlib.suppress(Exception):
                writer.close()


@pytest.mark.asyncio
async def test_link_down_and_recovery_against_fake_server() -> None:
    """Attach, read OK, kill server, N polls fail -> link down, restart -> recover."""
    server = FakeModbusServer()
    await server.start()
    port = server.port

    transport = ModbusTransport(
        host="127.0.0.1",
        serial="1234567890",
        port=port,
        timeout=1.0,
        retries=0,
        retry_delay=0.01,
        inter_register_delay=0.0,
        pymodbus_retries=0,
    )
    inverter = GenericInverter(client=None, serial_number="1234567890", model="TestModel")
    inverter._transport = transport

    try:
        # Phase 1: healthy — combined read succeeds, counter stays at zero
        await transport.connect()
        await inverter.refresh(force=True)
        assert inverter.transport_link_down is False
        assert inverter.transport_consecutive_failures == 0
        assert inverter._transport_runtime is not None
        assert server.request_count > 0

        # Phase 2: server dies mid-run (VPN drop / network break)
        await server.stop()
        for _ in range(TRANSPORT_LINK_DOWN_THRESHOLD):
            await inverter.refresh(force=True)

        assert inverter.transport_link_down is True
        assert inverter.transport_consecutive_failures >= TRANSPORT_LINK_DOWN_THRESHOLD
        # Stale local data is no longer served as fresh
        assert inverter._transport_runtime is None

        # Phase 3: server comes back on the same port.  Production parity:
        # the coordinator keeps polling every cycle — the transport's own
        # reconnect gate (3 consecutive errors -> fresh pymodbus client)
        # heals the connection within a few polls, and the first successful
        # read clears the link-down flag.
        await server.start(port=port)
        for _ in range(6):
            if not transport.is_connected:
                with contextlib.suppress(Exception):
                    await transport.connect()
            await inverter.refresh(force=True)
            if not inverter.transport_link_down:
                break

        assert inverter.transport_link_down is False
        assert inverter.transport_consecutive_failures == 0
        assert inverter._transport_runtime is not None
        assert server.request_count > 0
    finally:
        with contextlib.suppress(Exception):
            await transport.disconnect()
        await server.stop()
