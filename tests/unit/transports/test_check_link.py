"""Unit tests for the cheap ``check_link()`` transport probe (eg4#587 follow-up).

A deaf endpoint — TCP accepts but never answers (the classic wedged
dongle / Waveshare gateway failure mode) — must be detectable with a
single-attempt, short-timeout probe instead of the transport's full read
timeout chain.  Devices call ``check_link()`` while the link is down so a
coordinator refresh against a dead endpoint stays cheap.
"""

from __future__ import annotations

import asyncio
import contextlib
import time

import pytest

from pylxpweb.transports.dongle import DongleTransport
from pylxpweb.transports.modbus import ModbusTransport
from pylxpweb.transports.protocol import LINK_PROBE_TIMEOUT_SECONDS

from .test_link_down_fake_server import FakeModbusServer

# A deaf probe must resolve well below the transports' full read timeout
# chain (10s dongle response timeout; ~16-30s Modbus retry chain).
_PROBE_WALL_CLOCK_BUDGET = LINK_PROBE_TIMEOUT_SECONDS + 4.0


class MuteServer:
    """TCP server that accepts connections but never responds (deaf endpoint)."""

    def __init__(self) -> None:
        self._server: asyncio.AbstractServer | None = None
        self._writers: set[asyncio.StreamWriter] = set()
        self.port: int = 0
        self.connection_count: int = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
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
        self.connection_count += 1
        self._writers.add(writer)
        try:
            while await reader.read(4096):
                pass  # swallow requests, never answer
        except (ConnectionResetError, OSError):
            pass
        finally:
            self._writers.discard(writer)
            with contextlib.suppress(Exception):
                writer.close()


class TestModbusCheckLink:
    """check_link() on the Modbus TCP transport."""

    @staticmethod
    def _make_transport(port: int, timeout: float = 5.0) -> ModbusTransport:
        return ModbusTransport(
            host="127.0.0.1",
            serial="1234567890",
            port=port,
            timeout=timeout,
            retries=2,
            retry_delay=0.5,
            inter_register_delay=0.0,
            pymodbus_retries=0,
        )

    @pytest.mark.asyncio
    async def test_healthy_server_returns_true(self) -> None:
        server = FakeModbusServer()
        await server.start()
        transport = self._make_transport(server.port)
        try:
            await transport.connect()
            assert await transport.check_link() is True
        finally:
            await transport.disconnect()
            await server.stop()

    @pytest.mark.asyncio
    async def test_mute_server_returns_false_within_budget(self) -> None:
        """A deaf endpoint costs the short probe timeout, not the retry chain."""
        server = MuteServer()
        await server.start()
        transport = self._make_transport(server.port, timeout=5.0)
        try:
            await transport.connect()
            start = time.monotonic()
            assert await transport.check_link() is False
            assert time.monotonic() - start < _PROBE_WALL_CLOCK_BUDGET
        finally:
            await transport.disconnect()
            await server.stop()

    @pytest.mark.asyncio
    async def test_dead_server_returns_false(self) -> None:
        """Connection-refused endpoints also probe cheap."""
        server = FakeModbusServer()
        await server.start()
        port = server.port
        await server.stop()
        transport = self._make_transport(port, timeout=2.0)
        start = time.monotonic()
        assert await transport.check_link() is False
        assert time.monotonic() - start < _PROBE_WALL_CLOCK_BUDGET


class TestDongleCheckLink:
    """check_link() on the WiFi dongle transport."""

    @staticmethod
    def _make_transport(port: int, timeout: float = 10.0) -> DongleTransport:
        return DongleTransport(
            host="127.0.0.1",
            dongle_serial="BA12345678",
            inverter_serial="1234567890",
            port=port,
            timeout=timeout,
        )

    @pytest.mark.asyncio
    async def test_mute_dongle_returns_false_within_budget(self) -> None:
        """The production failure mode: dongle accepts TCP, never answers.

        Default timeout is 10s — the probe must not pay it.
        """
        server = MuteServer()
        await server.start()
        transport = self._make_transport(server.port, timeout=10.0)
        try:
            start = time.monotonic()
            assert await transport.check_link() is False
            elapsed = time.monotonic() - start
            assert elapsed < _PROBE_WALL_CLOCK_BUDGET
            # Single attempt: one connection, no retry storm
            assert server.connection_count == 1
        finally:
            await transport.async_shutdown()
            await server.stop()

    @pytest.mark.asyncio
    async def test_dead_dongle_returns_false_within_budget(self) -> None:
        """Connection-refused endpoints must not pay the connect retry ladder."""
        server = MuteServer()
        await server.start()
        port = server.port
        await server.stop()
        transport = self._make_transport(port, timeout=10.0)
        try:
            start = time.monotonic()
            assert await transport.check_link() is False
            assert time.monotonic() - start < _PROBE_WALL_CLOCK_BUDGET
        finally:
            await transport.async_shutdown()


class TestHybridCheckLink:
    """HybridTransport must NOT expose check_link (codex review HIGH).

    Devices built from a HybridTransport have no cloud client of their own —
    the transport IS the HTTP fallback.  If check_link existed and reported
    the (deaf) local side down, devices would skip read_runtime() and with it
    the internal ``_with_fallback`` HTTP path, freezing data indefinitely.
    Absent check_link, devices keep the full-read probe, which the hybrid's
    own local-failure gating already keeps cheap.
    """

    def test_hybrid_has_no_check_link(self) -> None:
        from pylxpweb.transports.hybrid import HybridTransport

        assert not hasattr(HybridTransport, "check_link")
