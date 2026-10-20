"""Accepted values keep their acquisition evidence across selection and aggregation."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb.devices.inverters.generic import GenericInverter
from pylxpweb.devices.parallel_group import ParallelGroup
from pylxpweb.exceptions import LuxpowerConnectionError
from pylxpweb.models import EnergyInfo
from pylxpweb.provenance import EnergyProvenance
from pylxpweb.transports.data import InverterEnergyData
from pylxpweb.transports.exceptions import TransportReadError
from pylxpweb.transports.hybrid import HybridTransport

BEFORE_MIDNIGHT = datetime(2026, 10, 19, 23, 59, tzinfo=UTC)
AFTER_MIDNIGHT = datetime(2026, 10, 20, 0, 1, tzinfo=UTC)


def _cloud_energy() -> EnergyInfo:
    return EnergyInfo(
        success=True,
        todayYielding=80,
        todayCharging=20,
        todayDischarging=10,
        todayImport=10,
        todayExport=20,
        todayUsage=60,
        totalYielding=800,
        totalCharging=200,
        totalDischarging=100,
        totalImport=100,
        totalExport=200,
        totalUsage=600,
        provenance={
            "todayYielding": EnergyProvenance(
                source="http", source_id="cloud:A", acquired_at=BEFORE_MIDNIGHT
            ),
            "todayCharging": EnergyProvenance(
                source="http", source_id="cloud:A", acquired_at=BEFORE_MIDNIGHT
            ),
        },
    )


def _inverter(serial: str = "A") -> GenericInverter:
    return GenericInverter(client=None, serial_number=serial, model="Test")


def _group() -> ParallelGroup:
    return ParallelGroup(client=Mock(), station=Mock(), name="A", first_device_serial="A")


def test_inverter_provenance_follows_numeric_slot_selection() -> None:
    inverter = _inverter()
    inverter._energy = _cloud_energy()
    local = EnergyProvenance(source="local", source_id="modbus:A", acquired_at=AFTER_MIDNIGHT)
    inverter._transport_energy = InverterEnergyData(
        pv_energy_today=1.0, provenance={"pv_energy_today": local}
    )

    assert inverter.total_energy_today == 1.0
    assert inverter.energy_provenance["total_energy_today"] == local
    assert inverter.energy_today_charging is None
    assert "energy_today_charging" not in inverter.energy_provenance

    inverter._transport_energy = None
    assert inverter.total_energy_today == 8.0
    assert inverter.energy_today_charging == 2.0
    assert (
        inverter.energy_provenance["total_energy_today"]
        == (inverter._energy.provenance["todayYielding"])
    )
    assert inverter.energy_provenance["energy_today_charging"].acquired_at == BEFORE_MIDNIGHT


def test_http_fallback_in_transport_slot_is_not_relabeled_local() -> None:
    inverter = _inverter()
    cloud = _cloud_energy()
    inverter._transport_energy = InverterEnergyData.from_http_response(cloud)
    inverter._energy_cache_time = AFTER_MIDNIGHT

    first = inverter.energy_provenance
    assert inverter.total_energy_today == 8.0
    assert first["total_energy_today"].source == "http"
    assert first["total_energy_today"].acquired_at == BEFORE_MIDNIGHT
    assert first["total_energy_today"].counter_day is None
    assert first == inverter.energy_provenance
    first.clear()
    assert inverter.energy_provenance["total_energy_today"].acquired_at == BEFORE_MIDNIGHT


async def test_real_hybrid_fallback_and_recovery_preserve_each_source() -> None:
    cloud = InverterEnergyData.from_http_response(_cloud_energy())
    local = InverterEnergyData(
        pv_energy_today=1,
        provenance={
            "pv_energy_today": EnergyProvenance(
                source="local", source_id="modbus:A", acquired_at=AFTER_MIDNIGHT
            )
        },
    )
    local_transport = Mock(serial="A")
    local_transport.connect = AsyncMock()
    local_transport.read_energy = AsyncMock(side_effect=[TransportReadError("offline"), local])
    http_transport = Mock()
    http_transport.connect = AsyncMock()
    http_transport.read_energy = AsyncMock(return_value=cloud)
    hybrid = HybridTransport(local_transport, http_transport, local_retry_interval=0)
    await hybrid.connect()

    fallback = await hybrid.read_energy()
    assert fallback is cloud
    assert fallback.provenance["pv_energy_today"].source == "http"
    assert fallback.provenance["pv_energy_today"].acquired_at == BEFORE_MIDNIGHT
    recovered = await hybrid.read_energy()
    assert recovered is local
    assert recovered.provenance["pv_energy_today"].source == "local"
    assert recovered.provenance["pv_energy_today"].acquired_at == AFTER_MIDNIGHT
    assert cloud.provenance["pv_energy_today"].acquired_at == BEFORE_MIDNIGHT


def test_legacy_snapshot_timestamp_is_not_promoted_to_acquisition() -> None:
    inverter = _inverter()
    assert inverter.energy_provenance == {}
    inverter._transport_energy = InverterEnergyData(
        timestamp=AFTER_MIDNIGHT, charge_energy_today=2.0
    )

    provenance = inverter.energy_provenance["energy_today_charging"]
    assert provenance.source == "unknown"
    assert provenance.acquired_at is None
    assert provenance.measured_at is None
    assert provenance.counter_day is None


@pytest.mark.parametrize("rejection", ["failure", "corrupt", "lifetime", "daily"])
async def test_rejected_read_keeps_accepted_value_and_provenance(
    rejection: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    inverter = _inverter()
    inverter.validate_data = True
    old = EnergyProvenance(source="local", source_id="modbus:A", acquired_at=BEFORE_MIDNIGHT)
    accepted = InverterEnergyData(
        pv_energy_today=8.0, pv_energy_total=80.0, provenance={"pv_energy_today": old}
    )
    inverter._transport_energy = accepted
    inverter._energy_cache_time = BEFORE_MIDNIGHT
    candidate = InverterEnergyData(
        pv_energy_today=1.0,
        pv_energy_total=81.0,
        provenance={
            "pv_energy_today": EnergyProvenance(
                source="local", source_id="modbus:A", acquired_at=AFTER_MIDNIGHT
            )
        },
    )
    monkeypatch.setattr(candidate, "is_corrupt", lambda: rejection == "corrupt")
    monkeypatch.setattr(inverter, "_is_energy_valid", lambda *_args: rejection != "lifetime")
    monkeypatch.setattr(inverter, "_is_daily_energy_valid", lambda *_args: rejection != "daily")
    transport = Mock()
    transport.read_energy = AsyncMock(
        return_value=candidate,
        side_effect=TransportReadError("unavailable") if rejection == "failure" else None,
    )
    inverter._transport = transport

    await inverter._fetch_energy()

    assert inverter._transport_energy is accepted
    assert inverter.total_energy_today == 8.0
    assert inverter.energy_provenance["total_energy_today"] == old
    assert inverter._energy_cache_time == BEFORE_MIDNIGHT


def test_parallel_aggregate_retains_mixed_age_sources_and_missing_contributors() -> None:
    group = _group()
    local = EnergyProvenance(source="local", source_id="modbus:A", acquired_at=AFTER_MIDNIGHT)
    cloud = EnergyProvenance(source="http", source_id="cloud:B", acquired_at=BEFORE_MIDNIGHT)
    first, second, missing = (_inverter(serial) for serial in ("A", "B", "C"))
    first._transport_energy = InverterEnergyData(
        pv_energy_today=2.0, provenance={"pv_energy_today": local}
    )
    second._transport_energy = InverterEnergyData(
        pv_energy_today=3.0, provenance={"pv_energy_today": cloud}
    )
    missing._transport_energy = InverterEnergyData()
    group.inverters = [first, second, missing]

    group._energy = group._compute_energy_from_inverters()
    provenance = group.energy_provenance["today_yielding"]

    assert group.today_yielding == 5.0
    assert provenance.source == "derived"
    assert provenance.acquired_at is None
    assert provenance.counter_day is None
    assert provenance.components[:2] == (local, cloud)
    assert provenance.components[2].source == "unknown"
    assert provenance.components[2].source_id == "inverter:C"
    usage = group.energy_provenance["today_usage"]
    assert usage.acquired_at is None
    assert len(usage.components) == 5
    assert usage.components[0] == provenance
    assert all(len(component.components) == 3 for component in usage.components)

    first._transport_energy = InverterEnergyData(pv_energy_today=99.0)
    assert group.today_yielding == 5.0
    assert group.energy_provenance["today_yielding"] == provenance


async def test_parallel_cloud_failure_preserves_previous_provenance() -> None:
    group = _group()
    accepted = _cloud_energy()
    group._energy = accepted
    group._client.api.devices.get_parallel_energy = AsyncMock(
        side_effect=LuxpowerConnectionError("unavailable")
    )
    before = group.energy_provenance

    await group._fetch_energy_data("A")

    assert group._energy is accepted
    assert group.today_yielding == 8.0
    assert group.energy_provenance == before
    assert before["today_yielding"].acquired_at == BEFORE_MIDNIGHT


def test_parallel_legacy_values_have_unknown_provenance() -> None:
    group = _group()
    assert group.energy_provenance == {}
    group._energy = _cloud_energy()
    group._energy.provenance.clear()

    assert len(group.energy_provenance) == 12
    assert all(value.source == "unknown" for value in group.energy_provenance.values())
    assert all(value.acquired_at is None for value in group.energy_provenance.values())
