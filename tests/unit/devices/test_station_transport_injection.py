"""Public transport-capability injection and lifecycle tests."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pylxpweb.devices.inverters.generic import GenericInverter
from pylxpweb.devices.mid_device import MIDDevice
from pylxpweb.devices.station import Location, Station
from pylxpweb.transports import (
    TerminalInverterTransport,
    TransportConfig,
    TransportFactory,
    TransportType,
)


class RecordingTransport:
    """Minimal caller-owned capability that records attachment-boundary calls."""

    def __init__(
        self,
        serial: str,
        events: list[str],
        *,
        label: str = "",
        connect_error: BaseException | None = None,
        close_error: BaseException | None = None,
    ) -> None:
        self.serial = serial
        self.transport_type = "modbus_tcp"
        self.is_connected = False
        self.events = events
        self.label = label
        self.connect_error = connect_error
        self.close_error = close_error
        self.connect_started: asyncio.Event | None = None
        self.connect_release: asyncio.Event | None = None
        self.close_started: asyncio.Event | None = None
        self.close_release: asyncio.Event | None = None
        self.connect_callback: Callable[[], Awaitable[None]] | None = None
        self.close_callback: Callable[[], Awaitable[None]] | None = None

    def _event(self, name: str) -> str:
        """Prefix an event when a test needs to distinguish capabilities."""
        return f"{self.label}:{name}" if self.label else name

    @property
    def capabilities(self) -> Any:
        """Expose the typed capability member without invoking protocol I/O."""
        return None

    async def connect(self) -> None:
        self.events.append(self._event("connect"))
        await asyncio.sleep(0)
        if self.connect_started is not None:
            self.connect_started.set()
        if self.connect_release is not None:
            await self.connect_release.wait()
        if self.connect_callback is not None:
            await self.connect_callback()
        if self.connect_error is not None:
            raise self.connect_error
        self.is_connected = True

    async def disconnect(self) -> None:
        self.events.append(self._event("disconnect"))
        self.is_connected = False

    async def async_shutdown(self) -> None:
        self.events.append(self._event("shutdown"))
        if self.close_started is not None:
            self.close_started.set()
        if self.close_release is not None:
            await self.close_release.wait()
        if self.close_callback is not None:
            await self.close_callback()
        if self.close_error is not None:
            raise self.close_error
        self.is_connected = False

    async def read_runtime(self) -> Any:
        raise AssertionError("attachment invoked forbidden operation read_runtime")

    async def read_energy(self) -> Any:
        raise AssertionError("attachment invoked forbidden operation read_energy")

    async def read_battery(self) -> Any:
        raise AssertionError("attachment invoked forbidden operation read_battery")

    async def read_parameters(self, start_address: int, count: int) -> dict[int, int]:
        raise AssertionError("attachment invoked forbidden operation read_parameters")

    async def write_parameters(self, parameters: dict[int, int]) -> bool:
        raise AssertionError("attachment invoked forbidden operation write_parameters")

    async def read_named_parameters(self, start_address: int, count: int) -> dict[str, Any]:
        raise AssertionError("attachment invoked forbidden operation read_named_parameters")

    async def write_named_parameters(self, parameters: dict[str, Any]) -> bool:
        raise AssertionError("attachment invoked forbidden operation write_named_parameters")

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


class ShutdownOnlyTransport(DisconnectOnlyTransport):
    """Terminal lifecycle without the required inverter-operation capability."""

    async def async_shutdown(self) -> None:
        self.events.append("shutdown")
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


def exception_leaves(error: BaseException) -> list[BaseException]:
    """Return exception-group leaves in deterministic traversal order."""
    if isinstance(error, BaseExceptionGroup):
        return [leaf for child in error.exceptions for leaf in exception_leaves(child)]
    return [error]


async def cancel_repeatedly(task: asyncio.Task[Any], count: int = 100) -> None:
    """Deliver repeated cancellation at distinct event-loop opportunities."""
    for _ in range(count):
        task.cancel()
        await asyncio.sleep(0)


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
    """The config-only Station path retains legacy disconnect compatibility."""
    events: list[str] = []
    capability = DisconnectOnlyTransport("INV0000001", events)
    inverter = station.all_inverters[0]
    with patch(
        "pylxpweb.transports.create_modbus_transport",
        return_value=capability,
    ):
        result = await station.attach_local_transports([config("INV0000001")])

    detached = await inverter.detach_local_transport()

    assert result.matched == 1
    assert detached is capability
    assert inverter.transport is None
    assert events == ["connect", "disconnect"]


def test_public_attachment_has_no_terminal_contract_downgrade() -> None:
    """Caller-owned attachment exposes only the terminal capability contract."""
    signature = inspect.signature(GenericInverter.attach_local_transport)
    capability = RecordingTransport("INV0000001", [])

    assert list(signature.parameters) == ["self", "transport"]
    assert "TerminalInverterTransport" in str(signature.parameters["transport"].annotation)
    assert isinstance(capability, TerminalInverterTransport)


@pytest.mark.asyncio
async def test_public_attachment_rejects_shutdown_only_capability(station: Station) -> None:
    """Terminal shutdown alone cannot satisfy the inverter capability contract."""
    events: list[str] = []
    capability = ShutdownOnlyTransport("INV0000001", events)

    with pytest.raises(TypeError, match="TerminalInverterTransport"):
        await station.all_inverters[0].attach_local_transport(capability)

    assert events == []
    assert station.all_inverters[0].transport is None


@pytest.mark.asyncio
async def test_injected_factory_rejects_disconnect_only_capability(station: Station) -> None:
    """Caller-owned injection requires an explicit terminal-close capability."""
    events: list[str] = []
    capability = DisconnectOnlyTransport("INV0000001", events)

    result = await station.attach_local_transports(
        [config("INV0000001")], transport_factory=lambda _: capability
    )

    assert (result.matched, result.failed) == (0, 1)
    assert station.all_inverters[0].transport is None
    assert events == []


@pytest.mark.asyncio
async def test_connect_and_cleanup_failures_are_combined(station: Station) -> None:
    """Both failures remain visible when a failed connect cannot be cleaned up."""
    events: list[str] = []
    capability = RecordingTransport(
        "INV0000001",
        events,
        connect_error=ConnectionError("connect failed"),
        close_error=RuntimeError("cleanup failed"),
    )

    with pytest.raises(BaseExceptionGroup) as raised:
        await station.all_inverters[0].attach_local_transport(capability)

    assert [type(error) for error in raised.value.exceptions] == [
        ConnectionError,
        RuntimeError,
    ]
    assert events == ["connect", "shutdown"]
    assert station.all_inverters[0].transport is None


@pytest.mark.asyncio
async def test_nested_cancellation_only_connect_preserves_native_cancellation(
    station: Station,
) -> None:
    """A cancellation-only connect group becomes native after successful cleanup."""
    events: list[str] = []
    connect_error = BaseExceptionGroup(
        "nested connect cancellation",
        [
            asyncio.CancelledError(),
            BaseExceptionGroup("deeper cancellation", [asyncio.CancelledError()]),
        ],
    )
    capability = RecordingTransport("INV0000001", events, connect_error=connect_error)
    task = asyncio.create_task(station.all_inverters[0].attach_local_transport(capability))

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1)

    assert task.cancelled()
    assert events == ["connect", "shutdown"]
    assert station.all_inverters[0].transport is None


@pytest.mark.asyncio
async def test_cancellation_and_cleanup_failure_are_combined(station: Station) -> None:
    """Cancellation and terminal-cleanup failure are reported deterministically."""
    events: list[str] = []
    capability = RecordingTransport(
        "INV0000001", events, close_error=RuntimeError("cleanup failed")
    )
    capability.connect_started = asyncio.Event()
    capability.connect_release = asyncio.Event()
    task = asyncio.create_task(station.all_inverters[0].attach_local_transport(capability))
    await capability.connect_started.wait()

    task.cancel()
    with pytest.raises(BaseExceptionGroup) as raised:
        await task

    assert [type(error) for error in raised.value.exceptions] == [
        asyncio.CancelledError,
        RuntimeError,
    ]
    assert events == ["connect", "shutdown"]
    assert station.all_inverters[0].transport is None


@pytest.mark.asyncio
async def test_many_repeated_cancellations_coalesce_to_native_cancellation(
    station: Station,
) -> None:
    """Unretained cleanup keeps constant cancellation state and native semantics."""
    events: list[str] = []
    capability = RecordingTransport("INV0000001", events)
    capability.connect_started = asyncio.Event()
    capability.connect_release = asyncio.Event()
    capability.close_started = asyncio.Event()
    capability.close_release = asyncio.Event()
    task = asyncio.create_task(station.all_inverters[0].attach_local_transport(capability))
    await capability.connect_started.wait()

    task.cancel()
    await capability.close_started.wait()
    await cancel_repeatedly(task)
    assert not task.done()

    capability.close_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert task.cancelled()
    assert events == ["connect", "shutdown"]
    assert station.all_inverters[0].transport is None


@pytest.mark.asyncio
async def test_wait_for_preserves_native_timeout_when_terminal_cleanup_cancels(
    station: Station,
) -> None:
    """Cancellation-only cleanup remains a timeout through asyncio.wait_for()."""
    events: list[str] = []
    capability = RecordingTransport("INV0000001", events, close_error=asyncio.CancelledError())
    capability.connect_release = asyncio.Event()

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            station.all_inverters[0].attach_local_transport(capability),
            timeout=0.05,
        )

    assert events == ["connect", "shutdown"]
    assert station.all_inverters[0].transport is None


@pytest.mark.asyncio
async def test_timeout_context_preserves_native_timeout_when_cleanup_cancels(
    station: Station,
) -> None:
    """Cancellation-only cleanup remains a timeout through asyncio.timeout()."""
    events: list[str] = []
    capability = RecordingTransport("INV0000001", events, close_error=asyncio.CancelledError())
    capability.connect_release = asyncio.Event()

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.05):
            await station.all_inverters[0].attach_local_transport(capability)

    assert events == ["connect", "shutdown"]
    assert station.all_inverters[0].transport is None


@pytest.mark.asyncio
async def test_task_group_treats_cancellation_only_cleanup_as_cancelled(
    station: Station,
) -> None:
    """A child with cancellation-only cleanup remains cancelled to TaskGroup."""
    events: list[str] = []
    capability = RecordingTransport("INV0000001", events, close_error=asyncio.CancelledError())
    capability.connect_started = asyncio.Event()
    capability.connect_release = asyncio.Event()

    async with asyncio.TaskGroup() as group:
        task = group.create_task(station.all_inverters[0].attach_local_transport(capability))
        await capability.connect_started.wait()
        task.cancel()

    assert task.cancelled()
    assert events == ["connect", "shutdown"]
    assert station.all_inverters[0].transport is None


@pytest.mark.asyncio
async def test_nested_cancellation_only_cleanup_preserves_native_cancellation(
    station: Station,
) -> None:
    """Nested cancellation-only cleanup errors collapse to one cancellation."""
    events: list[str] = []
    cleanup_error = BaseExceptionGroup(
        "nested cancellation",
        [
            asyncio.CancelledError(),
            BaseExceptionGroup("deeper cancellation", [asyncio.CancelledError()]),
        ],
    )
    capability = RecordingTransport("INV0000001", events, close_error=cleanup_error)
    capability.connect_started = asyncio.Event()
    capability.connect_release = asyncio.Event()
    task = asyncio.create_task(station.all_inverters[0].attach_local_transport(capability))
    await capability.connect_started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert task.cancelled()
    assert events == ["connect", "shutdown"]
    assert station.all_inverters[0].transport is None


@pytest.mark.asyncio
async def test_nested_mixed_cleanup_preserves_every_failure(station: Station) -> None:
    """A nested non-cancellation leaf keeps the complete mixed failure group."""
    events: list[str] = []
    cleanup_error = BaseExceptionGroup(
        "nested mixed cleanup",
        [asyncio.CancelledError(), RuntimeError("cleanup failed")],
    )
    capability = RecordingTransport("INV0000001", events, close_error=cleanup_error)
    capability.connect_started = asyncio.Event()
    capability.connect_release = asyncio.Event()
    task = asyncio.create_task(station.all_inverters[0].attach_local_transport(capability))
    await capability.connect_started.wait()

    task.cancel()
    with pytest.raises(BaseExceptionGroup) as raised:
        await task

    assert [type(error) for error in exception_leaves(raised.value)] == [
        asyncio.CancelledError,
        asyncio.CancelledError,
        RuntimeError,
    ]
    assert events == ["connect", "shutdown"]
    assert station.all_inverters[0].transport is None


@pytest.mark.asyncio
async def test_later_cleanup_cancellation_is_combined_with_connect_failure(
    station: Station,
) -> None:
    """Cancellation reported during cleanup remains visible with the primary failure."""
    events: list[str] = []
    capability = RecordingTransport(
        "INV0000001", events, connect_error=ConnectionError("connect failed")
    )
    capability.close_started = asyncio.Event()
    capability.close_release = asyncio.Event()
    task = asyncio.create_task(station.all_inverters[0].attach_local_transport(capability))
    await capability.close_started.wait()

    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    capability.close_release.set()

    with pytest.raises(BaseExceptionGroup) as raised:
        await task

    assert [type(error) for error in exception_leaves(raised.value)] == [
        ConnectionError,
        asyncio.CancelledError,
    ]
    assert events == ["connect", "shutdown"]


@pytest.mark.asyncio
async def test_primary_cleanup_failure_and_later_cancellation_are_all_preserved(
    station: Station,
) -> None:
    """Primary failure, cleanup failure, and later cancellation all remain visible."""
    events: list[str] = []
    capability = RecordingTransport(
        "INV0000001",
        events,
        connect_error=ConnectionError("connect failed"),
        close_error=RuntimeError("cleanup failed"),
    )
    capability.close_started = asyncio.Event()
    capability.close_release = asyncio.Event()
    task = asyncio.create_task(station.all_inverters[0].attach_local_transport(capability))
    await capability.close_started.wait()

    task.cancel()
    capability.close_release.set()

    with pytest.raises(BaseExceptionGroup) as raised:
        await task

    assert [type(error) for error in exception_leaves(raised.value)] == [
        ConnectionError,
        asyncio.CancelledError,
        RuntimeError,
    ]
    assert events == ["connect", "shutdown"]


@pytest.mark.asyncio
async def test_detach_failure_retains_current_capability(station: Station) -> None:
    """A failed terminal detach retains the current owner for a later retry."""
    events: list[str] = []
    capability = RecordingTransport("INV0000001", events, close_error=RuntimeError("close failed"))
    inverter = station.all_inverters[0]
    await inverter.attach_local_transport(capability)

    with pytest.raises(RuntimeError, match="close failed"):
        await inverter.detach_local_transport()

    assert inverter.transport is capability
    assert events == ["connect", "shutdown"]


@pytest.mark.asyncio
async def test_detach_cancellation_and_cleanup_failure_are_combined(
    station: Station,
) -> None:
    """Detach preserves cancellation when the completed close attempt also fails."""
    events: list[str] = []
    capability = RecordingTransport("INV0000001", events)
    inverter = station.all_inverters[0]
    await inverter.attach_local_transport(capability)
    capability.close_error = RuntimeError("close failed")
    capability.close_started = asyncio.Event()
    capability.close_release = asyncio.Event()
    task = asyncio.create_task(inverter.detach_local_transport())
    await capability.close_started.wait()

    task.cancel()
    capability.close_release.set()
    with pytest.raises(BaseExceptionGroup) as raised:
        await task

    assert [type(error) for error in raised.value.exceptions] == [
        asyncio.CancelledError,
        RuntimeError,
    ]
    assert inverter.transport is capability


@pytest.mark.asyncio
async def test_concurrent_attachments_are_serialized(station: Station) -> None:
    """A second attachment cannot connect or publish during the first transition."""
    events: list[str] = []
    first = RecordingTransport("INV0000001", events, label="first")
    second = RecordingTransport("INV0000001", events, label="second")
    first.connect_started = asyncio.Event()
    first.connect_release = asyncio.Event()
    second.connect_started = asyncio.Event()
    second.connect_release = asyncio.Event()
    inverter = station.all_inverters[0]

    first_task = asyncio.create_task(inverter.attach_local_transport(first))
    await first.connect_started.wait()
    second_task = asyncio.create_task(inverter.attach_local_transport(second))
    await asyncio.sleep(0)
    assert not second.connect_started.is_set()

    first.connect_release.set()
    await first_task
    await second.connect_started.wait()
    second.connect_release.set()
    await second_task

    assert events == ["first:connect", "second:connect", "first:shutdown"]
    assert inverter.transport is second


@pytest.mark.asyncio
async def test_cancellation_while_waiting_for_lifecycle_closes_new_capability(
    station: Station,
) -> None:
    """Cancellation while waiting for another transition cleans the unpublished input."""
    events: list[str] = []
    first = RecordingTransport("INV0000001", events, label="first")
    waiting = RecordingTransport("INV0000001", events, label="waiting")
    first.connect_started = asyncio.Event()
    first.connect_release = asyncio.Event()
    inverter = station.all_inverters[0]

    first_task = asyncio.create_task(inverter.attach_local_transport(first))
    await first.connect_started.wait()
    waiting_task = asyncio.create_task(inverter.attach_local_transport(waiting))
    await asyncio.sleep(0)
    waiting_task.cancel()
    await asyncio.sleep(0)
    assert not waiting_task.done()

    first.connect_release.set()
    await first_task
    with pytest.raises(asyncio.CancelledError):
        await waiting_task

    assert events == ["first:connect", "waiting:shutdown"]
    assert inverter.transport is first


@pytest.mark.asyncio
async def test_cancelled_same_capability_waiter_cannot_close_holder_input(
    station: Station,
) -> None:
    """A cancelled waiter defers ownership cleanup until the holder publishes."""
    events: list[str] = []
    capability = RecordingTransport("INV0000001", events)
    capability.connect_started = asyncio.Event()
    capability.connect_release = asyncio.Event()
    inverter = station.all_inverters[0]

    holder = asyncio.create_task(inverter.attach_local_transport(capability))
    await capability.connect_started.wait()
    waiter = asyncio.create_task(inverter.attach_local_transport(capability))
    await asyncio.sleep(0)
    await cancel_repeatedly(waiter)

    assert not waiter.done()
    assert events == ["connect"]
    capability.connect_release.set()
    await holder
    with pytest.raises(asyncio.CancelledError):
        await waiter

    assert waiter.cancelled()
    assert events == ["connect"]
    assert inverter.transport is capability


@pytest.mark.asyncio
async def test_cancelled_waiter_coalesces_repeats_with_cleanup_failure(
    station: Station,
) -> None:
    """A mixed waiter outcome keeps one primary and one later cancellation marker."""
    events: list[str] = []
    holder_capability = RecordingTransport("INV0000001", events, label="holder")
    waiting_capability = RecordingTransport(
        "INV0000001",
        events,
        label="waiting",
        close_error=RuntimeError("cleanup failed"),
    )
    holder_capability.connect_started = asyncio.Event()
    holder_capability.connect_release = asyncio.Event()
    inverter = station.all_inverters[0]

    holder = asyncio.create_task(inverter.attach_local_transport(holder_capability))
    await holder_capability.connect_started.wait()
    waiter = asyncio.create_task(inverter.attach_local_transport(waiting_capability))
    await asyncio.sleep(0)
    await cancel_repeatedly(waiter)
    assert not waiter.done()

    holder_capability.connect_release.set()
    await holder
    with pytest.raises(BaseExceptionGroup) as raised:
        await waiter

    assert [type(error) for error in exception_leaves(raised.value)] == [
        asyncio.CancelledError,
        asyncio.CancelledError,
        RuntimeError,
    ]
    assert events == ["holder:connect", "waiting:shutdown"]
    assert inverter.transport is holder_capability


@pytest.mark.asyncio
async def test_connect_callback_lifecycle_reentry_fails_fast(station: Station) -> None:
    """A connect callback cannot deadlock by nesting a lifecycle transition."""
    events: list[str] = []
    capability = RecordingTransport("INV0000001", events)
    inverter = station.all_inverters[0]
    nested_errors: list[BaseException] = []

    async def nested_detach() -> None:
        try:
            async with asyncio.timeout(0.1):
                await inverter.detach_local_transport()
        except BaseException as error:
            nested_errors.append(error)

    capability.connect_callback = nested_detach
    await inverter.attach_local_transport(capability)

    assert len(nested_errors) == 1
    assert isinstance(nested_errors[0], RuntimeError)
    assert "re-entry" in str(nested_errors[0])
    assert inverter.transport is capability


@pytest.mark.asyncio
async def test_shutdown_callback_lifecycle_reentry_fails_fast(station: Station) -> None:
    """A shutdown callback cannot deadlock by nesting a lifecycle transition."""
    events: list[str] = []
    capability = RecordingTransport("INV0000001", events)
    replacement = RecordingTransport("INV0000001", events, label="nested")
    inverter = station.all_inverters[0]
    await inverter.attach_local_transport(capability)
    nested_errors: list[BaseException] = []

    async def nested_attach() -> None:
        try:
            async with asyncio.timeout(0.1):
                await inverter.attach_local_transport(replacement)
        except BaseException as error:
            nested_errors.append(error)

    capability.close_callback = nested_attach
    detached = await inverter.detach_local_transport()

    assert detached is capability
    assert len(nested_errors) == 1
    assert isinstance(nested_errors[0], RuntimeError)
    assert "re-entry" in str(nested_errors[0])
    assert inverter.transport is None


@pytest.mark.asyncio
async def test_concurrent_detach_and_replacement_close_once(station: Station) -> None:
    """Detach owns the old close while a replacement waits for the transition."""
    events: list[str] = []
    old = RecordingTransport("INV0000001", events, label="old")
    replacement = RecordingTransport("INV0000001", events, label="new")
    inverter = station.all_inverters[0]
    await inverter.attach_local_transport(old)
    events.clear()
    old.close_started = asyncio.Event()
    old.close_release = asyncio.Event()
    replacement.connect_started = asyncio.Event()

    detach_task = asyncio.create_task(inverter.detach_local_transport())
    await old.close_started.wait()
    replacement_task = asyncio.create_task(inverter.attach_local_transport(replacement))
    await asyncio.sleep(0)
    assert not replacement.connect_started.is_set()

    old.close_release.set()
    await detach_task
    await replacement_task

    assert events == ["old:shutdown", "new:connect"]
    assert inverter.transport is replacement


@pytest.mark.asyncio
async def test_cancelled_replacement_closes_both_without_publishing_new(
    station: Station,
) -> None:
    """Cancellation during old-owner close cannot publish or leak the replacement."""
    events: list[str] = []
    old = RecordingTransport("INV0000001", events, label="old")
    replacement = RecordingTransport("INV0000001", events, label="new")
    inverter = station.all_inverters[0]
    await inverter.attach_local_transport(old)
    events.clear()
    old.close_started = asyncio.Event()
    old.close_release = asyncio.Event()

    task = asyncio.create_task(inverter.attach_local_transport(replacement))
    await old.close_started.wait()
    task.cancel()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()

    old.close_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert events == ["new:connect", "old:shutdown", "new:shutdown"]
    assert inverter.transport is None


@pytest.mark.asyncio
async def test_same_object_attachment_validates_serial_first(station: Station) -> None:
    """Identity cannot bypass serial validation on an already-owned capability."""
    events: list[str] = []
    capability = RecordingTransport("INV0000001", events)
    inverter = station.all_inverters[0]
    await inverter.attach_local_transport(capability)
    capability.serial = "OTHER00001"

    with pytest.raises(ValueError, match="does not match"):
        await inverter.attach_local_transport(capability)

    assert inverter.transport is capability


@pytest.mark.asyncio
async def test_same_object_attachment_applies_cache_ttl_hook(station: Station) -> None:
    """Idempotent public attachment establishes transport cache invariants."""
    events: list[str] = []
    capability = RecordingTransport("INV0000001", events)
    capability.is_connected = True
    client = MagicMock()
    client.username = "test-user"
    inverter = GenericInverter(
        client,
        "INV0000001",
        "Test Inverter",
        transport=capability,
    )

    await inverter.attach_local_transport(capability)

    assert inverter._runtime_cache_ttl == timedelta(seconds=5)
    assert inverter._energy_cache_ttl == timedelta(seconds=5)
    assert inverter._battery_cache_ttl == timedelta(seconds=5)


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
