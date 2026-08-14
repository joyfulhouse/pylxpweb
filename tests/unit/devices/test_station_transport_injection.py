"""Public transport-capability injection and lifecycle tests."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pylxpweb.devices.inverters.generic import GenericInverter
from pylxpweb.devices.mid_device import MIDDevice
from pylxpweb.devices.station import Location, Station
from pylxpweb.transports import TransportConfig, TransportFactory, TransportType


class RecordingTransport:
    """Minimal caller-owned capability that records attachment-boundary calls."""

    def __init__(
        self,
        serial: str,
        events: list[str],
        *,
        connect_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self.serial = serial
        self.transport_type = "modbus_tcp"
        self.is_connected = False
        self.events = events
        self.connect_error = connect_error
        self.close_error = close_error
        self.connect_started: asyncio.Event | None = None
        self.connect_release: asyncio.Event | None = None

    async def connect(self) -> None:
        self.events.append("connect")
        await asyncio.sleep(0)
        if self.connect_started is not None:
            self.connect_started.set()
        if self.connect_release is not None:
            await self.connect_release.wait()
        if self.connect_error is not None:
            raise self.connect_error
        self.is_connected = True

    async def disconnect(self) -> None:
        self.events.append("disconnect")
        self.is_connected = False

    async def async_shutdown(self) -> None:
        self.events.append("shutdown")
        if self.close_error is not None:
            raise self.close_error
        self.is_connected = False

    def __getattr__(self, name: str) -> Any:
        if name.startswith(("read", "write", "reconnect")):
            raise AssertionError(f"attachment invoked forbidden operation {name}")
        raise AttributeError(name)


class DisconnectOnlyTransport:
    """Capability that supports the required reusable disconnect lifecycle only."""

    def __init__(self, serial: str, events: list[str]) -> None:
        self.serial = serial
        self.is_connected = False
        self.events = events

    async def connect(self) -> None:
        self.events.append("connect")
        self.is_connected = True

    async def disconnect(self) -> None:
        self.events.append("disconnect")
        self.is_connected = False


@pytest.fixture
def station() -> Station:
    """Create a cloud-discovered station with one inverter and one MID."""
    client = MagicMock()
    client.username = "test-user"
    result = Station(
        client=client,
        plant_id=12345,
        name="Test Station",
        location=Location(address="", country="US"),
        timezone="UTC",
        created_date=datetime.now(),
    )
    result.standalone_inverters = [GenericInverter(client, "INV0000001", "Test Inverter")]
    result.standalone_mid_devices = [MIDDevice(client, "MID0000001")]
    return result


def config(serial: str) -> TransportConfig:
    """Build a sanitized local transport configuration."""
    return TransportConfig(
        host="example.invalid",
        port=502,
        serial=serial,
        transport_type=TransportType.MODBUS_TCP,
    )


@pytest.mark.asyncio
async def test_injected_factory_is_the_only_attachment_boundary(station: Station) -> None:
    """Injection constructs/connects only the supplied capability, with no I/O probe."""
    events: list[str] = []
    capability = RecordingTransport("INV0000001", events)

    def factory(item: TransportConfig) -> RecordingTransport:
        events.append(f"factory:{item.serial}")
        return capability

    typed_factory: TransportFactory = factory
    with (
        patch("pylxpweb.transports.create_modbus_transport") as default_modbus,
        patch("pylxpweb.transports.create_dongle_transport") as default_dongle,
    ):
        result = await station.attach_local_transports(
            [config("INV0000001")], transport_factory=typed_factory
        )

    assert events == ["factory:INV0000001", "connect"]
    assert result.matched == 1
    assert station.all_inverters[0].transport is capability
    default_modbus.assert_not_called()
    default_dongle.assert_not_called()


@pytest.mark.asyncio
async def test_injected_factory_attaches_mid_capability(station: Station) -> None:
    """The public seam retains a supplied capability on a matched MID."""
    events: list[str] = []
    capability = RecordingTransport("MID0000001", events)

    result = await station.attach_local_transports(
        [config("MID0000001")], transport_factory=lambda _: capability
    )

    assert result.matched == 1
    assert station.all_mid_devices[0].transport is capability
    assert events == ["connect"]


@pytest.mark.asyncio
async def test_mid_public_detach_uses_terminal_close(station: Station) -> None:
    """A MID capability has the same public terminal detach lifecycle."""
    events: list[str] = []
    capability = RecordingTransport("MID0000001", events)
    mid = station.all_mid_devices[0]
    await mid.attach_local_transport(capability)

    detached = await mid.detach_local_transport()

    assert detached is capability
    assert mid.transport is None
    assert events == ["connect", "shutdown"]


@pytest.mark.asyncio
async def test_partial_match_does_not_construct_unmatched_capability(station: Station) -> None:
    """Serial matching happens before the caller-owned factory is invoked."""
    events: list[str] = []
    capability = RecordingTransport("INV0000001", events)
    requested: list[str] = []

    def factory(item: TransportConfig) -> RecordingTransport:
        requested.append(item.serial)
        return capability

    result = await station.attach_local_transports(
        [config("MISSING001"), config("INV0000001")], transport_factory=factory
    )

    assert requested == ["INV0000001"]
    assert (result.matched, result.unmatched, result.failed) == (1, 1, 0)


@pytest.mark.asyncio
async def test_connect_failure_closes_capability_without_retaining_it(station: Station) -> None:
    """A failed injected connect is closed and reported through AttachResult."""
    events: list[str] = []
    capability = RecordingTransport(
        "INV0000001", events, connect_error=ConnectionError("unavailable")
    )

    result = await station.attach_local_transports(
        [config("INV0000001")], transport_factory=lambda _: capability
    )

    assert events == ["connect", "shutdown"]
    assert (result.matched, result.unmatched, result.failed) == (0, 0, 1)
    assert station.all_inverters[0].transport is None


@pytest.mark.asyncio
async def test_factory_capability_serial_mismatch_is_closed_and_failed(station: Station) -> None:
    """A factory cannot attach a capability to the wrong matched device."""
    events: list[str] = []
    capability = RecordingTransport("OTHER00001", events)

    result = await station.attach_local_transports(
        [config("INV0000001")], transport_factory=lambda _: capability
    )

    assert events == ["shutdown"]
    assert (result.matched, result.unmatched, result.failed) == (0, 0, 1)
    assert station.all_inverters[0].transport is None


@pytest.mark.asyncio
async def test_cancelled_connect_closes_capability_and_propagates(station: Station) -> None:
    """Cancellation during connect terminally closes without retaining the capability."""
    events: list[str] = []
    capability = RecordingTransport("INV0000001", events)
    capability.connect_started = asyncio.Event()
    capability.connect_release = asyncio.Event()
    task = asyncio.create_task(
        station.attach_local_transports(
            [config("INV0000001")], transport_factory=lambda _: capability
        )
    )
    await capability.connect_started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert events == ["connect", "shutdown"]
    assert station.all_inverters[0].transport is None


@pytest.mark.asyncio
async def test_precancelled_attachment_cleans_up_before_propagating(station: Station) -> None:
    """Cancellation already pending at connect still terminally closes the capability."""
    events: list[str] = []
    capability = RecordingTransport("INV0000001", events)

    async def run_cancelled() -> None:
        task = asyncio.current_task()
        assert task is not None
        task.cancel()
        await station.attach_local_transports(
            [config("INV0000001")], transport_factory=lambda _: capability
        )

    with pytest.raises(asyncio.CancelledError):
        await run_cancelled()

    assert events == ["connect", "shutdown"]
    assert station.all_inverters[0].transport is None


@pytest.mark.asyncio
async def test_public_detach_uses_terminal_close(station: Station) -> None:
    """Callers can terminally close and detach without private device access."""
    events: list[str] = []
    capability = RecordingTransport("INV0000001", events)
    inverter = station.all_inverters[0]
    await inverter.attach_local_transport(capability)

    detached = await inverter.detach_local_transport()

    assert detached is capability
    assert inverter.transport is None
    assert events == ["connect", "shutdown"]


@pytest.mark.asyncio
async def test_public_detach_falls_back_to_disconnect(station: Station) -> None:
    """Capabilities without terminal shutdown retain protocol-compatible cleanup."""
    events: list[str] = []
    capability = DisconnectOnlyTransport("INV0000001", events)
    inverter = station.all_inverters[0]
    await inverter.attach_local_transport(capability)

    detached = await inverter.detach_local_transport()

    assert detached is capability
    assert inverter.transport is None
    assert events == ["connect", "disconnect"]


@pytest.mark.asyncio
async def test_replacement_closes_old_before_retaining_new(station: Station) -> None:
    """Replacement connects new, drains old, then atomically publishes new."""
    events: list[str] = []
    old = RecordingTransport("INV0000001", events)
    new = RecordingTransport("INV0000001", events)
    inverter = station.all_inverters[0]
    await inverter.attach_local_transport(old)
    events.clear()

    await inverter.attach_local_transport(new)

    assert events == ["connect", "shutdown"]
    assert inverter.transport is new


@pytest.mark.asyncio
async def test_failed_replacement_keeps_old_and_closes_new(station: Station) -> None:
    """A close failure cannot publish a replacement or leak its capability."""
    events: list[str] = []
    old = RecordingTransport("INV0000001", events, close_error=RuntimeError("close failed"))
    new = RecordingTransport("INV0000001", events)
    inverter = station.all_inverters[0]
    await inverter.attach_local_transport(old)
    events.clear()

    with pytest.raises(RuntimeError, match="close failed"):
        await inverter.attach_local_transport(new)

    assert events == ["connect", "shutdown", "shutdown"]
    assert inverter.transport is old
