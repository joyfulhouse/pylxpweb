"""Exercise provenance against the actual EG4 daily guard; see companion docs.

The reference adapter here is harness-only. It is not integration adoption.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock
from zoneinfo import ZoneInfo


def reference_sample_times(snapshot, zone):
    """Apply the harness's explicit local-calendar policy to the PV counter."""

    def local_leaves(record):
        if record is None:
            return None
        if record.source == "derived":
            if not record.components:
                return None
            result = []
            for component in record.components:
                leaves = local_leaves(component)
                if leaves is None:
                    return None
                result.extend(leaves)
            return result
        if record.source != "local" or record.acquired_at is None:
            return None
        return [record.acquired_at]

    times = local_leaves(snapshot.provenance.get("pv_energy_today"))
    if not times or len({at.astimezone(zone).date() for at in times}) != 1:
        return {}
    return {"yield": min(times)}


def run(integration_source: Path, *, audit_legacy: bool) -> int:
    library_source = Path(__file__).resolve().parents[1] / "src"
    sys.path[:0] = [str(library_source), str(integration_source)]

    from custom_components.eg4_web_monitor.coordinator_mappings import (
        _build_energy_sensor_mapping,
    )
    from custom_components.eg4_web_monitor.energy_provenance import local_daily_sample_times
    from custom_components.eg4_web_monitor.sensor import EG4InverterSensor
    from freezegun import freeze_time
    from homeassistant.util import dt as dt_util

    from pylxpweb.devices.inverters.generic import GenericInverter
    from pylxpweb.devices.parallel_group import ParallelGroup
    from pylxpweb.models import EnergyInfo
    from pylxpweb.provenance import EnergyProvenance, derived_provenance
    from pylxpweb.transports.data import InverterEnergyData

    for module_name, expected_root in (
        ("pylxpweb.provenance", library_source),
        ("custom_components.eg4_web_monitor.base_entity", integration_source),
    ):
        origin = Path(importlib.import_module(module_name).__file__).resolve()
        if not origin.is_relative_to(expected_root.resolve()):
            raise RuntimeError(f"Wrong source for {module_name}: {origin}")
        print(f"SOURCE {module_name}: {origin}")

    print("MODE legacy adapter audit" if audit_legacy else "MODE harness-only reference adapter")

    def local(at, serial="A"):
        return EnergyProvenance(source="local", source_id=f"modbus:{serial}", acquired_at=at)

    def snapshot(value, record, timestamp):
        return InverterEnergyData(
            pv_energy_today=value,
            timestamp=timestamp,
            provenance={} if record is None else {"pv_energy_today": record},
        )

    def aggregate(records, timestamp):
        group = ParallelGroup(client=Mock(), station=Mock(), name="A", first_device_serial="A")
        for index, record in enumerate(records):
            inverter = GenericInverter(client=None, serial_number=str(index), model="Test")
            value = 13.5 / len(records)
            inverter._transport_energy = snapshot(value, record, timestamp)
            group.inverters.append(inverter)
        group._energy = group._compute_energy_from_inverters()
        return InverterEnergyData.from_http_response(group._energy)

    failures = []
    total = 0
    original_zone = dt_util.DEFAULT_TIME_ZONE
    try:
        for zone_name in ("UTC", "America/Los_Angeles", "Asia/Kolkata"):
            zone = ZoneInfo(zone_name)
            dt_util.set_default_time_zone(zone)
            before = datetime(2026, 10, 19, 23, 50, tzinfo=zone).astimezone(UTC)
            after = datetime(2026, 10, 20, 0, 10, tzinfo=zone).astimezone(UTC)
            cloud_record = EnergyProvenance(source="http", source_id="cloud:A", acquired_at=after)
            with freeze_time(after):
                cloud = EnergyInfo(
                    success=True,
                    **{
                        f"{period}{field}": 135
                        for period in ("today", "total")
                        for field in (
                            "Yielding",
                            "Charging",
                            "Discharging",
                            "Import",
                            "Export",
                            "Usage",
                        )
                    },
                    provenance={"todayYielding": cloud_record},
                )
                cases = (
                    ("fresh local next day", snapshot(13.5, local(after), after), 13.5),
                    (
                        "same day local dip",
                        snapshot(14.2, local(before + timedelta(minutes=5)), before),
                        14.3,
                    ),
                    ("HTTP next day receipt", InverterEnergyData.from_http_response(cloud), 14.3),
                    ("unknown with new legacy timestamp", snapshot(13.5, None, after), 14.3),
                    (
                        "cached local with new legacy timestamp",
                        snapshot(13.5, local(before), after),
                        14.3,
                    ),
                    (
                        "mixed local and HTTP aggregate",
                        aggregate([local(after), cloud_record], after),
                        14.3,
                    ),
                    (
                        "mixed local days aggregate",
                        aggregate([local(before), local(after)], after),
                        14.3,
                    ),
                    (
                        "fresh all-local aggregate",
                        aggregate([local(after), local(after, "B")], after),
                        13.5,
                    ),
                    ("unknown aggregate contributor", aggregate([local(after), None], after), 14.3),
                    (
                        "empty derived evidence",
                        snapshot(13.5, derived_provenance("empty", []), after),
                        14.3,
                    ),
                )
                for name, candidate, expected in cases:
                    coordinator = MagicMock()
                    device = {"sensors": {}, "energy_sample_times": {}}
                    coordinator.data = {"devices": {"serial": device}}
                    entity = EG4InverterSensor(coordinator, "serial", "yield")

                    def publish(value, device=device, entity=entity, zone=zone):
                        device["sensors"] = _build_energy_sensor_mapping(value)
                        device["energy_sample_times"] = (
                            local_daily_sample_times(device["sensors"], value)
                            if audit_legacy
                            else reference_sample_times(value, zone)
                        )
                        return entity.native_value

                    baseline = publish(snapshot(14.3, local(before), before))
                    actual = publish(candidate)
                    total += 1
                    if baseline != 14.3 or actual != expected:
                        failures.append(
                            f"{zone_name}: {name}: baseline={baseline}, "
                            f"expected={expected}, actual={actual}"
                        )
                        print(f"FAIL {failures[-1]}")
                    else:
                        print(f"PASS {zone_name}: {name}")
    finally:
        dt_util.set_default_time_zone(original_zone)
    print(f"RESULT {total - len(failures)}/{total} passed; {len(failures)} failed")
    return int(bool(failures))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integration-source", type=Path, required=True)
    parser.add_argument(
        "--audit-legacy", action="store_true", help="Audit the consumer's current timestamp adapter"
    )
    args = parser.parse_args()
    raise SystemExit(run(args.integration_source.resolve(), audit_legacy=args.audit_legacy))
