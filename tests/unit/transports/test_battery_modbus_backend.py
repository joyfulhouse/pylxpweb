"""Owned-link battery backend compatibility and lifecycle tests (#348)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from modbus_connection import ModbusTcpParams
from modbus_connection import exceptions as mc_exc
from modbus_connection.tmodbus import ModbusConnection
from tmodbus.exceptions import HeaderMismatchError

from pylxpweb.transports import _modbus_client, battery_modbus
from pylxpweb.transports._modbus_client import (
    ModbusConnectionUnit,
    PymodbusUnit,
)
from pylxpweb.transports.battery_modbus import BatteryModbusTransport
from pylxpweb.transports.exceptions import TransportConnectionError

from .test_link_down_fake_server import FakeModbusServer
from .test_modbus_client_seam import _LinkFactory


@pytest.mark.parametrize("backend", [None, "auto", " PyModbus "])
async def test_pymodbus_construction_and_single_owner(backend: str | None) -> None:
    """Default TCP construction has no retry/TID changes; units share one socket."""
    transport = (
        BatteryModbusTransport("127.0.0.1", port=1502, timeout=2.0)
        if backend is None
        else BatteryModbusTransport("127.0.0.1", port=1502, timeout=2.0, backend=backend)
    )
    client = MagicMock(connected=True)
    client.connect = AsyncMock()
    result = MagicMock(registers=[7, 8])
    result.isError.return_value = False
    client.read_holding_registers = AsyncMock(return_value=result)
    with (
        patch(
            "pylxpweb.transports.battery_modbus.AsyncModbusTcpClient", return_value=client
        ) as dial,
    ):
        await transport.connect()
        dial.assert_called_once_with("127.0.0.1", port=1502, timeout=2.0)
        assert not hasattr(battery_modbus, "patch_pymodbus_tid_validation")
        assert transport.is_connected
        for uid in (1, 2, 2):
            assert await transport._read_registers(4, 2, uid) == [7, 8]
        assert all(isinstance(unit, PymodbusUnit) for unit in transport._units.values())
        assert len(transport._units) == 2
        assert client.read_holding_registers.await_args_list == [
            ((), {"address": 4, "count": 2, "device_id": uid}) for uid in (1, 2, 2)
        ]
        await transport.disconnect()
        await transport.disconnect()
        client.close.assert_called_once()
        assert not transport.is_connected


@pytest.mark.parametrize("backend", ["bad", "", "serial"])
def test_invalid_backend(backend: str) -> None:
    with pytest.raises(ValueError, match="Unsupported Modbus backend"):
        BatteryModbusTransport("127.0.0.1", backend=backend)


async def test_modbus_connection_dial_multi_unit_and_single_close() -> None:
    """Real tmodbus handles for multiple IDs use one owned TCP connection."""
    server = FakeModbusServer()
    await server.start()
    transport = BatteryModbusTransport(
        "127.0.0.1", port=server.port, timeout=1.0, backend=" Modbus-Connection "
    )
    try:
        await transport.connect()
        connection = transport._client
        assert isinstance(connection, ModbusConnection)
        assert transport.is_connected
        with (
            patch.object(connection, "for_unit", wraps=connection.for_unit) as for_unit,
            patch.object(connection, "close", wraps=connection.close) as close,
        ):
            for uid in (1, 2, 3, 2):
                assert await transport._read_registers(0, 2, uid) == [0, 0]
            assert for_unit.call_args_list == [((2,), {}), ((3,), {})]
            assert len(transport._units) == 3
            assert all(isinstance(unit, ModbusConnectionUnit) for unit in transport._units.values())
            assert sum(unit.owns_link for unit in transport._units.values()) == 1
            assert server.request_count == 4
            assert len(server._writers) == 1
            await transport.disconnect()
            await transport.disconnect()
            close.assert_awaited_once()
            assert not connection.connected
            assert not transport.is_connected
    finally:
        await transport.disconnect()
        await server.stop()


@pytest.mark.parametrize(
    "failure",
    [
        mc_exc.ModbusExceptionError.from_code(2, "illegal address"),
        mc_exc.ModbusConnectionError("down"),
        TimeoutError("slow"),
        [],
    ],
    ids=["exception-response", "link-error", "timeout", "short-read"],
)
async def test_modbus_connection_owned_error_gate_reconnect(failure: Exception | list[int]) -> None:
    """Owned links retain probe exclusion and the existing three-error reconnect."""
    connections = []
    for _ in range(2):
        connection = MagicMock(connected=True)
        connection.connect = AsyncMock()
        connection.close = AsyncMock()
        connection.for_unit.return_value.read_holding_registers = AsyncMock(return_value=[0] * 42)
        connections.append(connection)
    first, replacement = connections
    first.for_unit.return_value.read_holding_registers.side_effect = (
        failure if isinstance(failure, Exception) else [failure] * 4
    )
    transport = BatteryModbusTransport("127.0.0.1", backend="modbus_connection")
    with patch(
        "pylxpweb.transports.battery_modbus.owned_modbus_connection", side_effect=connections
    ) as dial:
        await transport.connect()
        dial.assert_called_once_with(ModbusTcpParams(host="127.0.0.1", port=502), timeout=3.0)
        assert await transport._read_registers(0, 42, 2, probe=True) is None
        assert transport._consecutive_errors == 0
        for expected in (1, 2, 3):
            assert await transport.read_unit(2) is None
            assert transport._consecutive_errors == expected
            assert dial.call_count == 1
        with patch("pylxpweb.transports.battery_modbus.asyncio.sleep", new_callable=AsyncMock):
            assert await transport.read_unit(2) is not None
        assert dial.call_count == 2
        first.close.assert_awaited_once()
        replacement.connect.assert_awaited_once()
        assert transport._consecutive_errors == 0
        assert transport._units[2]._unit is replacement.for_unit.return_value
        await transport.disconnect()
        replacement.close.assert_awaited_once()


@pytest.fixture
def battery_links(monkeypatch: pytest.MonkeyPatch) -> _LinkFactory:
    """Reuse the seam's controlled links beneath the real owned connection."""
    factory = _LinkFactory()

    async def connect_client(self: ModbusConnection) -> object:
        return await factory.connect_client()

    monkeypatch.setattr(ModbusConnection, "_connect_client", connect_client)
    monkeypatch.setattr(_modbus_client, "LINK_RELEASE_TIMEOUT_SECONDS", 0.01)
    return factory


@pytest.fixture
async def connected_battery(battery_links: _LinkFactory) -> AsyncIterator[BatteryModbusTransport]:
    transport = BatteryModbusTransport("127.0.0.1", backend="modbus_connection")
    try:
        await transport.connect()
        yield transport
    finally:
        for client in battery_links.clients:
            client.link.release.set()
        await transport.disconnect()


async def test_owned_release_blocks_replacement_until_released(
    battery_links: _LinkFactory, connected_battery: BatteryModbusTransport
) -> None:
    """A bounded disconnect keeps the held owner; repeated connects cannot redial."""
    assert len(battery_links.clients) == 1
    await connected_battery.disconnect()
    assert not connected_battery.is_connected
    for _ in range(2):
        with pytest.raises(TransportConnectionError, match="still being released"):
            await connected_battery.connect()
    assert len(battery_links.clients) == 1
    battery_links.clients[0].link.release.set()
    await asyncio.sleep(0)
    await connected_battery.connect()
    assert len(battery_links.clients) == 2
    assert connected_battery.is_connected


async def test_cancelled_owned_connect_closes_late_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Context entry cancellation closes a shielded dial even after the wait expires."""
    server = FakeModbusServer()
    await server.start()
    connection = _modbus_client.owned_modbus_connection(
        ModbusTcpParams(host="127.0.0.1", port=server.port), timeout=1.0
    )
    transport = BatteryModbusTransport("127.0.0.1", backend="modbus_connection")
    dial_started = asyncio.Event()
    finish_dial = asyncio.Event()
    dial_finished = asyncio.Event()
    close_finished = asyncio.Event()
    real_dial = connection._connect_client
    real_close = connection.close

    async def delayed_dial() -> object:
        dial_started.set()
        await finish_dial.wait()
        client = await real_dial()
        dial_finished.set()
        return client

    async def close() -> None:
        await real_close()
        close_finished.set()

    monkeypatch.setattr(_modbus_client, "LINK_RELEASE_TIMEOUT_SECONDS", 0.0)
    with (
        patch.object(battery_modbus, "owned_modbus_connection", return_value=connection) as dial,
        patch.object(connection, "_connect_client", side_effect=delayed_dial),
        patch.object(connection, "_close_client", wraps=connection._close_client) as close_client,
        patch.object(connection, "close", side_effect=close) as close_connection,
    ):
        entering = asyncio.create_task(transport.__aenter__())
        try:
            await asyncio.wait_for(dial_started.wait(), 1.0)
            entering.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(entering, 1.0)
            assert not transport.is_connected
            assert transport._client is None
            assert transport._link_owner is None
            assert transport._units == {}
            with pytest.raises(TransportConnectionError, match="still being released"):
                await transport.connect()
            dial.assert_called_once()
            finish_dial.set()
            await asyncio.wait_for(close_finished.wait(), 1.0)
            close_connection.assert_awaited_once()
            close_client.assert_awaited_once()
            assert not connection.connected
            assert not transport.is_connected
            await transport.disconnect()
            close_connection.assert_awaited_once()
        finally:
            finish_dial.set()
            await asyncio.wait_for(dial_finished.wait(), 1.0)
            await transport.disconnect()
            await asyncio.wait_for(close_finished.wait(), 1.0)
            await server.stop()


@pytest.mark.parametrize(
    "failure",
    [mc_exc.ModbusConnectionError("refused"), OSError("refused"), RuntimeError("dial failed")],
    ids=["backend-error", "os-error", "unexpected-error"],
)
async def test_failed_owned_connect_matches_pymodbus_contract(
    failure: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    """Failed owned setup logs and returns; later reads cannot auto-dial the failed link."""
    connection = MagicMock(connected=False)
    connection.connect = AsyncMock(side_effect=failure)
    connection.close = AsyncMock()
    connection.for_unit.return_value.read_holding_registers = AsyncMock(return_value=[0])
    transport = BatteryModbusTransport("127.0.0.1", backend="modbus_connection")
    with (
        patch.object(battery_modbus, "owned_modbus_connection", return_value=connection) as dial,
        caplog.at_level(logging.ERROR),
    ):
        try:
            await transport.connect()
            assert not transport.is_connected
            assert transport._client is None
            assert transport._link_owner is None
            assert transport._units == {}
            assert [(r.levelno, r.getMessage()) for r in caplog.records] == [
                (logging.ERROR, "Failed to connect to battery RS485 bridge at 127.0.0.1:502")
            ]
            assert await transport._read_registers(0, 1, 1) is None
            connection.for_unit.return_value.read_holding_registers.assert_not_awaited()
            connection.connect.assert_awaited_once()
            dial.assert_called_once()
            connection.close.assert_awaited_once()
        finally:
            await transport.disconnect()


async def test_refused_owned_dial_cannot_autodial_on_read(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A real refused connection stays detached even when the server comes back."""
    server = FakeModbusServer()
    await server.start()
    port = server.port
    await server.stop()
    connection = _modbus_client.owned_modbus_connection(
        ModbusTcpParams(host="127.0.0.1", port=port), timeout=1.0
    )
    transport = BatteryModbusTransport(
        "127.0.0.1", port=port, timeout=1.0, backend="modbus_connection"
    )
    with (
        patch.object(battery_modbus, "owned_modbus_connection", return_value=connection),
        patch.object(connection, "connect", wraps=connection.connect) as connect,
        patch.object(connection, "close", wraps=connection.close) as close,
        caplog.at_level(logging.ERROR),
    ):
        try:
            await transport.connect()
            assert not transport.is_connected
            assert transport._link_owner is None
            assert transport._client is None
            assert transport._units == {}
            assert caplog.messages == [
                f"Failed to connect to battery RS485 bridge at 127.0.0.1:{port}"
            ]
            await server.start(port)
            assert await transport._read_registers(0, 1, 2) is None
            assert server.request_count == 0
            connect.assert_awaited_once()
            close.assert_awaited_once()
        finally:
            await transport.disconnect()
            await server.stop()


async def test_owned_connection_automatic_redial_honors_release(
    battery_links: _LinkFactory, connected_battery: BatteryModbusTransport
) -> None:
    """Backend desync recovery also passes through owned_modbus_connection's gate."""
    first = battery_links.clients[0]
    first.error = HeaderMismatchError("desync", response_bytes=b"")
    assert await connected_battery._read_registers(0, 1, 1) is None
    assert await connected_battery._read_registers(0, 1, 2) is None
    assert len(battery_links.clients) == 1
    first.link.release.set()
    await asyncio.sleep(0)
    assert await connected_battery._read_registers(0, 1, 2) == [0]
    assert len(battery_links.clients) == 2
