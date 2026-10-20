"""Exercise units returned by the installed Home Assistant Modbus integration."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from modbus_connection import ModbusTcpParams

from pylxpweb.transports.modbus import ModbusTransport

from .test_link_down_fake_server import FakeModbusServer

ha = pytest.importorskip("homeassistant", reason="Installed HA compatibility job only")
from homeassistant.components import modbus  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402


async def test_async_get_unit_preserves_host_ownership(tmp_path: Path) -> None:
    """Two real HA acquisitions share a link until the last entry unloads."""
    if not hasattr(modbus, "async_get_unit"):
        pytest.skip("Home Assistant 2026.8 predates the shared-unit API")
    from homeassistant.components.modbus.connection import async_get_connection_info

    hass = HomeAssistant(str(tmp_path))
    releases: list[Callable[[], Awaitable[None]]] = []
    entries = []
    for entry_id in ("pylxpweb", "other-consumer"):
        entry = MagicMock()
        entry.entry_id = entry_id
        entry.async_on_unload.side_effect = releases.append
        entries.append(entry)
    server = FakeModbusServer()
    await server.start()
    params = ModbusTcpParams(host="127.0.0.1", port=server.port)
    unit = modbus.async_get_unit(hass, entries[0], params, 1)
    other = modbus.async_get_unit(hass, entries[1], params, 2)
    transport = ModbusTransport(
        host="127.0.0.1", port=server.port, serial="HA-TEST", unit=unit, retries=0
    )
    try:
        await transport.connect()
        assert not unit.connected
        assert server.request_count == 0
        assert await transport.read_parameters(0, 2) == {0: 0, 1: 0}
        assert unit.connected and other.connected
        assert len(async_get_connection_info(hass)) == 1
        await transport.disconnect()
        assert unit.connected and other.connected
        await releases.pop(0)()
        assert other.connected
        assert await other.read_holding_registers(0, 1) == [0]
        await releases.pop(0)()
        assert not other.connected
        assert async_get_connection_info(hass) == []
    finally:
        await transport.disconnect()
        for release in releases:
            await release()
        await server.stop()
