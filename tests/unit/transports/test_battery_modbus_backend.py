"""Owned-link battery backend compatibility and lifecycle tests (#348)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from modbus_connection import ModbusTcpParams
from modbus_connection import exceptions as mc_exc
from modbus_connection.tmodbus import ModbusConnection
from tmodbus.exceptions import HeaderMismatchError

from pylxpweb.transports import _modbus_client
from pylxpweb.transports._modbus_client import (
    ModbusConnectionUnit,
    PymodbusUnit,
    RegisterLinkError,
)
from pylxpweb.transports.battery_modbus import BatteryModbusTransport

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
        patch.object(_modbus_client, "patch_pymodbus_tid_validation") as tid_patch,
    ):
        await transport.connect()
        dial.assert_called_once_with("127.0.0.1", port=1502, timeout=2.0)
        tid_patch.assert_not_called()
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


async def test_owned_release_blocks_replacement_until_released(battery_links: _LinkFactory) -> None:
    """A bounded disconnect keeps the held owner; repeated connects cannot redial."""
    transport = BatteryModbusTransport("127.0.0.1", backend="modbus_connection")
    try:
        await transport.connect()
        assert len(battery_links.clients) == 1
        await transport.disconnect()
        assert not transport.is_connected
        for _ in range(2):
            with pytest.raises(RegisterLinkError, match="still being released"):
                await transport.connect()
        assert len(battery_links.clients) == 1
        battery_links.clients[0].link.release.set()
        await asyncio.sleep(0)
        await transport.connect()
        assert len(battery_links.clients) == 2
        assert transport.is_connected
    finally:
        for client in battery_links.clients:
            client.link.release.set()
        await transport.disconnect()


async def test_owned_connection_automatic_redial_honors_release(
    battery_links: _LinkFactory,
) -> None:
    """Backend desync recovery also passes through owned_modbus_connection's gate."""
    transport = BatteryModbusTransport("127.0.0.1", backend="modbus_connection")
    try:
        await transport.connect()
        first = battery_links.clients[0]
        first.error = HeaderMismatchError("desync", response_bytes=b"")
        assert await transport._read_registers(0, 1, 1) is None
        assert await transport._read_registers(0, 1, 2) is None
        assert len(battery_links.clients) == 1
        first.link.release.set()
        await asyncio.sleep(0)
        assert await transport._read_registers(0, 1, 2) == [0]
        assert len(battery_links.clients) == 2
    finally:
        for client in battery_links.clients:
            client.link.release.set()
        await transport.disconnect()
