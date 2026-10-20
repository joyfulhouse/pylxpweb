"""Energy acquisition comes from reads, never decoder or aggregate access."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb.devices.mid_device import MIDDevice
from pylxpweb.models import MidboxRuntime
from pylxpweb.provenance import EnergyProvenance
from pylxpweb.transports._register_data import RegisterDataMixin
from pylxpweb.transports.data import InverterEnergyData, MidboxRuntimeData
from pylxpweb.transports.protocol import BaseTransport


def _mid_runtime(**energy: Any) -> MidboxRuntime:
    path = Path(__file__).parents[1] / "devices/mid/samples/midbox_4524850115.json"
    data = json.loads(path.read_text())
    data["midboxData"].update(energy)
    return MidboxRuntime.model_validate(data)


class PhysicalReadTransport(RegisterDataMixin, BaseTransport):
    """Keep the production register readers, replacing only wire reads."""

    def __init__(self) -> None:
        super().__init__("inverter-A")
        self._init_input_coalescing(40)
        self._inter_register_delay = 0
        self._inverter_family = None
        self._split_phase = False
        self._pv_string_count = 3

    async def _read_input_registers(self, start: int, count: int) -> list[int]:
        return [0] * count

    async def _read_holding_registers(self, start: int, count: int) -> list[int]:
        return [0] * count


@pytest.mark.parametrize("method", ["read_energy", "read_all_input_data", "read_midbox_runtime"])
async def test_physical_reads_attach_utc_provenance(method: str) -> None:
    transport = PhysicalReadTransport()
    before = datetime.now(UTC)
    result = await getattr(transport, method)()
    after = datetime.now(UTC)
    snapshot = result[1] if isinstance(result, tuple) else result
    key = "load_energy_today_l1" if method == "read_midbox_runtime" else "charge_energy_today"
    evidence = snapshot.provenance[key]

    assert evidence.source == "local"
    assert evidence.source_id == "PhysicalReadTransport:inverter-A"
    assert evidence.field_name == key
    assert before <= evidence.acquired_at <= after
    assert evidence.acquired_at.tzinfo is UTC
    assert evidence.measured_at is None
    assert evidence.counter_day is None
    assert evidence.reset_timezone is None
    if method != "read_midbox_runtime":
        pv = snapshot.provenance["pv_energy_today"]
        assert pv.source == "derived"
        assert pv.acquired_at is None
        assert {leaf.field_name for leaf in pv.components} == {
            "pv1_energy_today",
            "pv2_energy_today",
            "pv3_energy_today",
        }
        assert all(leaf.acquired_at == evidence.acquired_at for leaf in pv.components)


def test_decoding_registers_does_not_manufacture_acquisition() -> None:
    assert InverterEnergyData.from_modbus_registers({}).provenance == {}
    assert MidboxRuntimeData.from_modbus_registers({}).provenance == {}


def test_pv_provenance_includes_every_numeric_contributor_on_two_string_model() -> None:
    transport = PhysicalReadTransport()
    transport._pv_string_count = 2
    energy = InverterEnergyData.from_modbus_registers({28: 10, 29: 20, 30: 30}, pv_string_count=2)
    transport._stamp_energy_provenance(energy)

    assert energy.pv_energy_today == 6.0
    assert {item.field_name for item in energy.provenance["pv_energy_today"].components} == {
        "pv1_energy_today",
        "pv2_energy_today",
        "pv3_energy_today",
    }


def test_mid_conversion_and_partial_phase_sum_preserve_sources() -> None:
    old = EnergyProvenance(
        source="http", source_id="cloud:mid", acquired_at=datetime(2026, 10, 19, 23, 59, tzinfo=UTC)
    )
    new = EnergyProvenance(
        source="local", source_id="local:mid", acquired_at=datetime(2026, 10, 20, 0, 1, tzinfo=UTC)
    )
    runtime = _mid_runtime(eLoadTodayL1=10, eLoadTodayL2=20, provenance={"eLoadTodayL2": old})
    http = runtime.midboxData
    converted = MidboxRuntimeData.from_http_response(http)
    assert converted.provenance["load_energy_today_l2"] is old

    mid = MIDDevice(client=Mock(), serial_number="mid")
    mid._runtime = runtime
    mid._transport_runtime = MidboxRuntimeData(
        load_energy_today_l1=1, provenance={"load_energy_today_l1": new}
    )
    evidence = mid.energy_provenance
    assert evidence["e_load_today_l1"] is new
    assert evidence["e_load_today_l2"] is old
    assert evidence["e_load_today"].components == (new, old)
    assert evidence["e_load_today"].acquired_at is None
    assert evidence["e_load_today"].counter_day is None

    mid._runtime = None
    partial = mid.energy_provenance["e_load_today"]
    assert partial.components[0] is new
    assert partial.components[1].source == "unknown"
    assert partial.components[1].source_id == "mid:mid"
    assert partial.components[1].field_name == "e_load_today_l2"
    assert partial.source_id == "mid:mid"
    assert partial.field_name == "e_load_today"
    assert mid.e_load_today == 1
    assert partial == mid.energy_provenance["e_load_today"]


async def test_mid_rejection_keeps_http_fallback_and_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = EnergyProvenance(
        source="http", source_id="cloud:mid", acquired_at=datetime(2026, 10, 19, 23, 59, tzinfo=UTC)
    )
    accepted = _mid_runtime(eLoadTodayL2=20, provenance={"eLoadTodayL2": old})
    rejected = _mid_runtime(eLoadTodayL2=999999)
    client = Mock()
    client.api.devices.get_midbox_runtime = AsyncMock(return_value=rejected)
    mid = MIDDevice(client=client, serial_number="mid")
    mid._runtime = accepted
    mid._transport_runtime = MidboxRuntimeData(load_energy_today_l1=1)
    monkeypatch.setattr(mid, "_validate_runtime_energy", lambda _candidate: False)

    await mid._refresh_via_http()

    assert mid._runtime is accepted
    assert mid.e_load_today_l2 == 20
    assert mid.energy_provenance["e_load_today_l2"] is old
