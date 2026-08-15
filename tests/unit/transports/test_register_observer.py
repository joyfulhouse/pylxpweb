"""Terminal raw-register observer contract."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from pylxpweb.transports import RegisterObservation, RegisterSegment, RegisterSpace
from pylxpweb.transports._register_data import (
    DEFAULT_INPUT_BLOCK_SIZE,
    INPUT_REGISTER_GROUPS,
    RegisterDataMixin,
)
from pylxpweb.transports.exceptions import TransportReadError
from pylxpweb.transports.protocol import BaseTransport

type ObservationBatch = tuple[RegisterObservation, ...]


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
    assert observed == [
        (
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
    ]
    addresses = [
        address
        for observation in observed[0]
        for segment in observation.segments
        for address in range(segment.start_address, segment.start_address + len(segment.words))
    ]
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
