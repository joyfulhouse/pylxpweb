# Energy sample provenance

Energy values now carry acquisition evidence independently of cache expiry and
conversion timestamps. This supports consumers that must distinguish an old
accepted sample from a new response after an outage or midnight.

## Public contract

`pylxpweb.provenance.EnergyProvenance` is an immutable record with:

- `source`: `local`, `http`, `derived`, or `unknown`.
- `source_id`: the originating device/transport or HTTP endpoint and device.
- `field_name`: the original numeric field when known.
- `acquired_at`: aware UTC acquisition time, or `None`.
- `measured_at`: device-reported measurement time, or `None`.
- `counter_day` and `reset_timezone`: verified device counter-day evidence, or
  `None`. Current supported endpoints do not establish these values.
- `components`: immutable component records for a derived value. These preserve
  source identity, different ages, and missing evidence individually.

Naive acquisition/measurement times are rejected. Aware times normalize to UTC.
No timezone or date is inferred from a serial number, HTTP reception, formatting,
host wall clock, or a group's processing time.

`EnergyInfo.provenance` and `MidboxData.provenance` use raw HTTP field names.
`InverterEnergyData.provenance` and `MidboxRuntimeData.provenance` use their
transport field names. `BaseInverter.energy_provenance`,
`MIDDevice.energy_provenance`, and `ParallelGroup.energy_provenance` use public
numeric property names. These getters follow the same source selection as the
numeric properties and return a new mapping. Numeric values without metadata
have `unknown` provenance; unavailable numeric properties have no entry.

```python
value = inverter.energy_today_charging
evidence = inverter.energy_provenance.get("energy_today_charging")
if evidence is not None:
    print(value, evidence.source, evidence.acquired_at, evidence.counter_day)
```

## Acquisition and caching

HTTP acquisition is recorded once when the client successfully receives and
decodes a response. Evidence travels with that exact response through the client
cache, endpoint validation, and transport scaling. A repeated endpoint call or
conversion does not update it. HTTP receive time is **not device measurement
time**: a newly received cloud response may itself contain stale device data.
Server-provided fields named `provenance` are not accepted as library evidence.

Local acquisition is recorded at completion of the physical register snapshot
read. A snapshot can require several register transactions; the completion time
does not claim atomic sampling of every register or establish the device's reset
timezone. Decoding a supplied register dictionary alone supplies no acquisition
evidence. Rejected and failed refreshes retain the last accepted numeric values
and their evidence together. HTTP fallback in a hybrid transport remains `http`.

The older `timestamp` attributes and private cache clocks retain their existing
compatibility behavior. They are not the provenance contract and must not be used
to infer the age of HTTP or derived values.

## Derived and battery values

PV totals retain per-string components. Parallel-group totals retain each
inverter's contribution, and consumption retains all five terms of the energy
balance. GridBOSS phase sums preserve the selected per-phase sources, including
HTTP fallback. A missing component that the existing numeric formula treats as
zero remains explicitly unknown in the evidence. Numeric formulas are unchanged.

Derived records have no new acquisition time. Use `derived_provenance` when a
consumer builds additional values, including battery-bank charge/discharge sums:

```python
from pylxpweb.provenance import derived_provenance

evidence = derived_provenance(
    "battery-bank:charging",
    (inv.energy_provenance.get("energy_today_charging") for inv in inverters),
    field_name="charge_energy_today",
)
```

`BatteryBank` has no energy counters of its own. A consumer-derived battery total
must preserve its inverter contributors instead of borrowing a bank refresh time.
Legacy `ParallelGroup.get_combined_energy()` returns only numbers; consumers that
need evidence should use the accepted group energy properties and their mapping.

## Daily guard limits

A consumer must inspect every derived leaf and explicitly handle unknown or
mixed-age components. It must not promote HTTP reception to the device's counter
day, or use the newest contributor to date an entire aggregate. Converting an
aware UTC timestamp into a configured timezone is a consumer policy; it does not
prove that the inverter resets its counters in that timezone.

This API provides the software evidence requested by pylxpweb #383. It does not
by itself resolve the cloud/mixed-source counter-day uncertainty in
eg4_web_monitor #666. That integration must consume a published library version
containing this change, and retain unknown behavior where device evidence is
unavailable. No package release is implied by this change.
