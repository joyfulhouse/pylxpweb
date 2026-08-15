"""Terminal raw-register observer contract."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence

import pytest

from pylxpweb.transports import RegisterObservation, RegisterSegment, RegisterSpace
from pylxpweb.transports import _register_data as register_data_module
from pylxpweb.transports._register_data import (
    DEFAULT_INPUT_BLOCK_SIZE,
    INPUT_REGISTER_GROUPS,
    RegisterDataMixin,
    _ReadBlock,
)
from pylxpweb.transports.exceptions import TransportReadError
from pylxpweb.transports.protocol import BaseTransport

type ObservationBatch = tuple[RegisterObservation, ...]
type PublicRead = Callable[[_FakeRegisterTransport], Awaitable[object]]


class _FakeRegisterTransport(RegisterDataMixin, BaseTransport):
    """Deterministic transport exercising the real public read paths."""

    def __init__(
        self,
        *,
        observer: Callable[[ObservationBatch], None] | None = None,
        max_input_block_size: int = DEFAULT_INPUT_BLOCK_SIZE,
        fail_reads: set[tuple[RegisterSpace, int, int]] | None = None,
    ) -> None:
        super().__init__("test-serial", register_observer=observer)
        self._init_input_coalescing(max_input_block_size)
        self._inter_register_delay = 0.0
        self._inverter_family = None
        self._split_phase = False
        self._pv_string_count = 3
        self._fail_reads = fail_reads or set()
        self.reads: list[tuple[RegisterSpace, int, int]] = []

    async def _read_input_registers(self, start: int, count: int) -> list[int]:
        return self._read(RegisterSpace.INPUT, start, count)

    async def _read_holding_registers(self, start: int, count: int) -> list[int]:
        return self._read(RegisterSpace.HOLDING, start, count)

    async def _write_holding_registers(self, start: int, values: list[int]) -> bool:
        return True

    def _read(self, space: RegisterSpace, start: int, count: int) -> list[int]:
        request = (space, start, count)
        self.reads.append(request)
        if request in self._fail_reads:
            self._fail_reads.remove(request)
            raise TransportReadError("simulated read failure")
        if request == (RegisterSpace.INPUT, 140, 3):
            return [7] * count
        return [0] * count


class _BlockingRegisterTransport(_FakeRegisterTransport):
    """Transport that exposes cancellation while a real public read awaits I/O."""

    def __init__(self, *, observer: Callable[[ObservationBatch], None]) -> None:
        super().__init__(observer=observer)
        self.read_started = asyncio.Event()
        self.release_read = asyncio.Event()

    async def _read_holding_registers(self, start: int, count: int) -> list[int]:
        self.reads.append((RegisterSpace.HOLDING, start, count))
        self.read_started.set()
        await self.release_read.wait()
        return [0] * count


class _PreCancelledRegisterTransport(_FakeRegisterTransport):
    """Transport with cancellation already pending before observer dispatch."""

    async def _read_holding_registers(self, start: int, count: int) -> list[int]:
        task = asyncio.current_task()
        assert task is not None
        task.cancel()
        return await super()._read_holding_registers(start, count)


class _GroupFallbackProbeTransport(_FakeRegisterTransport):
    """Transport recording capture state at each real group-plan attempt."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.attempt_segment_counts: list[int | None] = []

    async def _read_group_plan(
        self,
        plan: list[_ReadBlock],
        segments: list[RegisterSegment] | None = None,
    ) -> dict[int, int]:
        self.attempt_segment_counts.append(None if segments is None else len(segments))
        return await super()._read_group_plan(plan, segments)


class _CountingAddress(int):
    """Integer address counting segment-boundary arithmetic for complexity proof."""

    additions_of_chunk_size = 0

    def __new__(cls, value: int) -> _CountingAddress:
        return super().__new__(cls, value)

    def __add__(self, other: int) -> _CountingAddress:
        if other == 40:
            type(self).additions_of_chunk_size += 1
        return type(self)(int(self) + other)


PUBLIC_OBSERVATION_READS: tuple[object, ...] = (
    pytest.param(lambda transport: transport.read_quick_charge_remaining_seconds(), id="quick"),
    pytest.param(lambda transport: transport.read_runtime(), id="runtime"),
    pytest.param(lambda transport: transport.read_energy(), id="energy"),
    pytest.param(lambda transport: transport.read_battery(), id="battery"),
    pytest.param(lambda transport: transport.read_all_input_data(), id="combined"),
    pytest.param(lambda transport: transport.read_midbox_runtime(), id="midbox"),
    pytest.param(lambda transport: transport.read_parameters(10, 85), id="parameters"),
    pytest.param(lambda transport: transport.read_serial_number(), id="serial"),
    pytest.param(lambda transport: transport.read_firmware_version(), id="firmware"),
    pytest.param(lambda transport: transport.read_device_type(), id="device-type"),
    pytest.param(lambda transport: transport.read_parallel_config(), id="parallel"),
    pytest.param(lambda transport: transport.validate_serial(""), id="validate-serial"),
)

CANONICAL_OBSERVATION_READS: tuple[object, ...] = (
    pytest.param(
        lambda transport: transport.read_serial_number(),
        (RegisterSpace.INPUT, 115, 5),
        id="serial",
    ),
    pytest.param(
        lambda transport: transport.read_firmware_version(),
        (RegisterSpace.HOLDING, 7, 4),
        id="firmware",
    ),
    pytest.param(
        lambda transport: transport.read_device_type(),
        (RegisterSpace.HOLDING, 19, 1),
        id="device-type",
    ),
    pytest.param(
        lambda transport: transport.read_parallel_config(),
        (RegisterSpace.INPUT, 113, 1),
        id="parallel",
    ),
)

TERMINAL_GROUP_OBSERVATION: ObservationBatch = (
    RegisterObservation(
        RegisterSpace.INPUT,
        (
            RegisterSegment(0, (0,) * 32),
            RegisterSegment(32, (0,) * 32),
            RegisterSegment(64, (0,) * 16),
            RegisterSegment(80, (0,) * 33),
            RegisterSegment(113, (0,) * 27),
            RegisterSegment(140, (7,) * 3),
            RegisterSegment(143, (0,) * 11),
            RegisterSegment(170, (0,) * 4),
            RegisterSegment(193, (0,) * 12),
        ),
    ),
)


def _observed_addresses(observed: list[ObservationBatch]) -> list[int]:
    return [
        address
        for observation in observed[0]
        for segment in observation.segments
        for address in range(segment.start_address, segment.start_address + len(segment.words))
    ]


def test_register_observation_repr_redacts_raw_words_from_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_sentinel = 57005
    segment = RegisterSegment(123, (raw_sentinel, 48879))
    observation = RegisterObservation(RegisterSpace.INPUT, (segment,))

    with pytest.raises(AssertionError) as assertion:
        assert observation == RegisterObservation(RegisterSpace.INPUT, ())
    logging.getLogger(__name__).warning("synthetic observation: %r", observation)

    rendered = (
        repr(segment),
        repr(observation),
        str(RuntimeError(observation)),
        str(assertion.value),
        caplog.text,
    )
    assert all(str(raw_sentinel) not in diagnostic for diagnostic in rendered)
    assert all("123" in diagnostic for diagnostic in rendered[:3])
    assert all("word_count=2" in diagnostic for diagnostic in rendered[:3])
    assert "word_count=2" in str(assertion.value)
    assert "word_count=2" in caplog.text


@pytest.mark.asyncio
async def test_coalesced_fallback_observes_only_terminal_winning_segments() -> None:
    observed: list[ObservationBatch] = []
    successful_discarded_probe = (RegisterSpace.INPUT, 0, 113)
    failed_probe = (RegisterSpace.INPUT, 113, 41)
    transport = _FakeRegisterTransport(
        observer=observed.append,
        max_input_block_size=120,
        fail_reads={failed_probe},
    )

    await transport.read_all_input_data()

    grouped_reads = [
        (RegisterSpace.INPUT, start, count) for start, count in INPUT_REGISTER_GROUPS.values()
    ]
    assert transport.reads == [successful_discarded_probe, failed_probe, *grouped_reads]
    assert observed == [TERMINAL_GROUP_OBSERVATION]
    addresses = _observed_addresses(observed)
    assert len(addresses) == len(set(addresses))


@pytest.mark.asyncio
async def test_raising_observer_preserves_read_and_advances_redacted_error_count() -> None:
    def raise_from_observer(observations: ObservationBatch) -> None:
        raise RuntimeError("secret observer detail")

    transport = _FakeRegisterTransport(observer=raise_from_observer)

    runtime, energy, _battery = await transport.read_all_input_data()

    assert runtime is not None
    assert energy is not None
    assert transport.register_observation_error_count == 1


@pytest.mark.asyncio
async def test_callback_cancelled_error_preserves_read_and_advances_error_count() -> None:
    def cancel_from_observer(observations: ObservationBatch) -> None:
        raise asyncio.CancelledError("synthetic callback detail")

    transport = _FakeRegisterTransport(observer=cancel_from_observer)

    result = await transport.read_parameters(10, 1)

    assert result == {10: 0}
    assert transport.register_observation_error_count == 1


@pytest.mark.parametrize("raise_after_cancel", [False, True])
@pytest.mark.asyncio
async def test_callback_task_cancellation_is_isolated(
    raise_after_cancel: bool,
) -> None:
    def cancel_from_observer(observations: ObservationBatch) -> None:
        task = asyncio.current_task()
        assert task is not None
        task.cancel()
        if raise_after_cancel:
            raise RuntimeError("synthetic callback detail")

    transport = _FakeRegisterTransport(observer=cancel_from_observer)

    result = await transport.read_parameters(10, 1)
    await asyncio.sleep(0)

    assert result == {10: 0}
    assert transport.register_observation_error_count == 1


@pytest.mark.asyncio
async def test_external_task_cancellation_remains_cancelled() -> None:
    observed: list[ObservationBatch] = []
    transport = _BlockingRegisterTransport(observer=observed.append)
    task = asyncio.create_task(transport.read_parameters(10, 1))
    await transport.read_started.wait()

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert observed == []
    assert transport.register_observation_error_count == 0


@pytest.mark.asyncio
async def test_cancellation_pending_before_callback_remains_cancelled() -> None:
    observed: list[ObservationBatch] = []
    transport = _PreCancelledRegisterTransport(observer=observed.append)

    with pytest.raises(asyncio.CancelledError):
        await transport.read_parameters(10, 1)

    assert observed == []
    assert transport.register_observation_error_count == 0


@pytest.mark.asyncio
async def test_runtime_group_fallback_discards_failed_attempt_segments() -> None:
    observed: list[ObservationBatch] = []
    successful_discarded_probe = (RegisterSpace.INPUT, 0, 113)
    failed_probe = (RegisterSpace.INPUT, 113, 41)
    transport = _GroupFallbackProbeTransport(
        observer=observed.append,
        max_input_block_size=120,
        fail_reads={failed_probe},
    )

    await transport.read_runtime()

    grouped_reads = [
        (RegisterSpace.INPUT, start, count) for start, count in INPUT_REGISTER_GROUPS.values()
    ]
    assert transport.reads == [successful_discarded_probe, failed_probe, *grouped_reads]
    assert transport.attempt_segment_counts == [0, 0]
    assert observed == [TERMINAL_GROUP_OBSERVATION]
    addresses = _observed_addresses(observed)
    assert len(addresses) == len(set(addresses))


@pytest.mark.asyncio
async def test_failed_public_read_emits_no_partial_observation() -> None:
    observed: list[ObservationBatch] = []
    transport = _FakeRegisterTransport(
        observer=observed.append,
        fail_reads={(RegisterSpace.INPUT, 32, 32)},
    )

    with pytest.raises(TransportReadError):
        await transport.read_runtime()

    assert observed == []
    assert transport.register_observation_error_count == 0


@pytest.mark.asyncio
async def test_observer_adds_zero_reads_and_preserves_request_order() -> None:
    baseline = _FakeRegisterTransport()
    observed: list[ObservationBatch] = []
    with_observer = _FakeRegisterTransport(observer=observed.append)

    baseline_result = await baseline.read_parameters(10, 85)
    observed_result = await with_observer.read_parameters(10, 85)

    expected_reads = [
        (RegisterSpace.HOLDING, 10, 40),
        (RegisterSpace.HOLDING, 50, 40),
        (RegisterSpace.HOLDING, 90, 5),
    ]
    assert baseline_result == observed_result
    assert baseline.reads == expected_reads
    assert with_observer.reads == expected_reads
    assert observed == [
        (
            RegisterObservation(
                RegisterSpace.HOLDING,
                (
                    RegisterSegment(10, (0,) * 40),
                    RegisterSegment(50, (0,) * 40),
                    RegisterSegment(90, (0,) * 5),
                ),
            ),
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("public_read", "expected_read"),
    CANONICAL_OBSERVATION_READS,
)
async def test_canonical_readers_observe_enabled_terminal_segment_without_extra_reads(
    public_read: PublicRead,
    expected_read: tuple[RegisterSpace, int, int],
) -> None:
    baseline = _FakeRegisterTransport()
    observed: list[ObservationBatch] = []
    enabled = _FakeRegisterTransport(observer=observed.append)

    baseline_result = await public_read(baseline)
    enabled_result = await public_read(enabled)

    space, start, count = expected_read
    assert enabled_result == baseline_result
    assert baseline.reads == [expected_read]
    assert enabled.reads == [expected_read]
    assert observed == [
        (
            RegisterObservation(
                space,
                (RegisterSegment(start, (0,) * count),),
            ),
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("public_read", PUBLIC_OBSERVATION_READS)
async def test_default_observer_skips_capture_on_every_public_read(
    monkeypatch: pytest.MonkeyPatch,
    public_read: PublicRead,
) -> None:
    baseline = _FakeRegisterTransport()
    await public_read(baseline)
    capture_calls = 0
    publication_calls = 0
    capture_states: list[list[RegisterSegment] | None] = []
    original_append = register_data_module._append_observed_segment
    original_new = RegisterDataMixin._new_observed_segments
    original_notify = RegisterDataMixin._notify_observed_segments

    def count_capture_calls(
        segments: list[RegisterSegment],
        start: int,
        values: Sequence[int],
    ) -> None:
        nonlocal capture_calls
        capture_calls += 1
        original_append(segments, start, values)

    def record_capture_state(self: RegisterDataMixin) -> list[RegisterSegment] | None:
        state = original_new(self)
        capture_states.append(state)
        return state

    async def count_publication_calls(
        self: RegisterDataMixin,
        *observed: tuple[RegisterSpace, Sequence[RegisterSegment] | None],
    ) -> None:
        nonlocal publication_calls
        publication_calls += 1
        await original_notify(self, *observed)

    monkeypatch.setattr(register_data_module, "_append_observed_segment", count_capture_calls)
    monkeypatch.setattr(RegisterDataMixin, "_new_observed_segments", record_capture_state)
    monkeypatch.setattr(RegisterDataMixin, "_notify_observed_segments", count_publication_calls)
    disabled = _FakeRegisterTransport()

    await public_read(disabled)

    assert disabled.reads == baseline.reads
    assert capture_states and all(state is None for state in capture_states)
    assert capture_calls == 0
    assert publication_calls == 0


@pytest.mark.asyncio
async def test_large_sequential_parameter_capture_is_linear() -> None:
    observed: list[ObservationBatch] = []
    transport = _FakeRegisterTransport(observer=observed.append)
    register_count = 4000
    chunk_count = register_count // 40
    _CountingAddress.additions_of_chunk_size = 0

    await transport.read_parameters(_CountingAddress(0), register_count)

    assert len(transport.reads) == chunk_count
    assert len(observed[0][0].segments) == chunk_count
    assert _CountingAddress.additions_of_chunk_size <= chunk_count * 3
