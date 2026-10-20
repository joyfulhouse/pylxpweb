"""Discovery caching without losing batteries during transient outages."""

from unittest.mock import AsyncMock, call

import pytest

from pylxpweb.transports.battery_modbus import BatteryModbusTransport


@pytest.fixture
def bus(monkeypatch: pytest.MonkeyPatch) -> BatteryModbusTransport:
    transport = BatteryModbusTransport("bridge", max_units=3)
    monkeypatch.setattr("pylxpweb.transports.battery_modbus.asyncio.sleep", AsyncMock())
    monkeypatch.setattr(transport, "_read_unit_raw", AsyncMock(return_value=({}, None)))
    return transport


async def test_repeated_polls_probe_absent_ids_only_once(
    bus: BatteryModbusTransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = AsyncMock(side_effect=[[100], None, [100]])
    monkeypatch.setattr(bus, "_read_registers", probe)

    await bus.read_all()
    await bus.read_all()

    assert probe.await_args_list == [
        call(0, 1, 1, probe=True),
        call(0, 1, 2, probe=True),
        call(0, 1, 3, probe=True),
    ]
    assert bus._read_unit_raw.await_args_list == [call(1), call(3), call(1), call(3)]
    assert bus.unit_ids is None


async def test_empty_initial_discovery_retries_on_next_poll(
    bus: BatteryModbusTransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = AsyncMock(side_effect=[None, None, None, None, [100], None])
    monkeypatch.setattr(bus, "_read_registers", probe)

    assert await bus.read_all() == []
    await bus.read_all()
    await bus.read_all()

    assert probe.await_count == 6
    assert bus._read_unit_raw.await_args_list == [call(2), call(2)]


async def test_explicit_rescan_updates_polling_but_retains_topology(
    bus: BatteryModbusTransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = AsyncMock(side_effect=[[100], None, None, None, [100], None])
    monkeypatch.setattr(bus, "_read_registers", probe)

    discovered = await bus.scan_units()
    discovered.append(3)
    await bus.read_all()
    assert await bus.scan_units() == [2]
    await bus.read_all()

    assert bus._read_unit_raw.await_args_list == [call(1), call(2)]
    assert bus._remembered_unit_ids() == {1, 2}


async def test_empty_rescan_does_not_erase_previously_discovered_units(
    bus: BatteryModbusTransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = AsyncMock(side_effect=[[100], None, None, None, None, None])
    monkeypatch.setattr(bus, "_read_registers", probe)

    await bus.read_all()
    assert await bus.scan_units() == []
    await bus.read_all()

    assert probe.await_count == 6
    assert bus._read_unit_raw.await_args_list == [call(1), call(1)]


async def test_explicit_empty_configuration_never_probes(
    bus: BatteryModbusTransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    bus.unit_ids = []
    probe = AsyncMock()
    monkeypatch.setattr(bus, "_read_registers", probe)

    assert await bus.read_all() == []
    probe.assert_not_awaited()
    bus._read_unit_raw.assert_not_awaited()
