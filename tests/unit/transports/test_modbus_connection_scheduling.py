"""Keep the host scheduling boundary accurate for the real shared-unit adapter."""

from __future__ import annotations

import asyncio

import pytest
from modbus_connection import ModbusTcpParams
from modbus_connection.tmodbus import ModbusConnection

from pylxpweb.transports._modbus_client import ModbusConnectionUnit


class GatedWire:
    """Hold fake wire requests until the test explicitly completes them."""

    def __init__(self) -> None:
        self.entered = [asyncio.Event(), asyncio.Event()]
        self.release = asyncio.Event()
        self.requests = 0

    async def send_and_receive(self, unit_id: int, pdu: object) -> list[int]:
        index = self.requests
        self.requests += 1
        self.entered[index].set()
        await self.release.wait()
        return [index]


@pytest.mark.parametrize("shared_connection", [True, False])
@pytest.mark.parametrize("second_unit_id", [1, 2])
async def test_request_serialization_scope(
    monkeypatch: pytest.MonkeyPatch, shared_connection: bool, second_unit_id: int
) -> None:
    """Zero spacing serializes one connection, but not two at one endpoint."""
    params = ModbusTcpParams(host="gateway.invalid")
    first_connection = ModbusConnection(params, message_spacing=0)
    second_connection = (
        first_connection if shared_connection else ModbusConnection(params, message_spacing=0)
    )
    wire = GatedWire()
    connections = [first_connection] if shared_connection else [first_connection, second_connection]
    for connection in connections:
        client = await connection._create_client()
        # Keep both upstream lock layers; stub only the wire beneath tmodbus's
        # smart wrapper. Creating a client does not connect it.
        monkeypatch.setattr(
            client.transport.base_transport, "send_and_receive", wire.send_and_receive
        )
        monkeypatch.setattr(connection, "_client", client)
    first = ModbusConnectionUnit(first_connection.for_unit(1))
    second = ModbusConnectionUnit(second_connection.for_unit(second_unit_id))
    second_started = asyncio.Event()

    async def second_read() -> list[int]:
        second_started.set()
        return await second.read_input_registers(1, 1)

    tasks: list[asyncio.Task[list[int]]] = []
    try:
        async with asyncio.timeout(5):
            tasks.append(asyncio.create_task(first.read_input_registers(0, 1)))
            await wire.entered[0].wait()
            tasks.append(asyncio.create_task(second_read()))
            # The second task runs until it blocks on the connection lock or
            # fake wire. No wall-clock delay is needed to observe that choice.
            await second_started.wait()
            assert wire.entered[1].is_set() is not shared_connection
            wire.release.set()
            assert await asyncio.gather(*tasks) == [[0], [1]]
    finally:
        wire.release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
