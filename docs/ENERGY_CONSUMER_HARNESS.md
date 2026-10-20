# Real consumer contract harness

`scripts/check_energy_consumer.py` loads the library source from this checkout
and an explicit EG4 integration checkout. It verifies both module locations,
uses the integration's actual numeric mapper and `EG4InverterSensor` daily
guard, and uses real Home Assistant timezone conversion. Only the coordinator
data container is mocked. It performs no network or hardware operations.

Run it in an environment containing the integration's Home Assistant and test
dependencies, including `freezegun`:

```sh
python scripts/check_energy_consumer.py --integration-source /path/to/eg4_web_monitor
```

The adapter inside this script is **harness-only**. It maps the PV counter's
library provenance to the integration's existing `energy_sample_times` input.
It accepts only nonempty, entirely local evidence whose leaves all fall on one
configured Home Assistant calendar day, and uses the earliest acquisition time.
Unknown, HTTP, empty, and mixed-day evidence supply no expiration timestamp.
This explicit software policy does not prove the inverter's reset timezone or
the device counter day. Snapshot completion is not atomic register sampling.

The cases exercise a next-day local sample, a same-day dip, a new HTTP receipt,
unknown evidence, cached evidence with a misleading legacy timestamp, mixed
sources, mixed days, current local aggregates, missing contributor evidence,
and empty derived evidence in UTC, Los Angeles, and Kolkata. Aggregate cases
run the actual `ParallelGroup` calculation and HTTP-shaped transport conversion.
Positive next-day controls ensure an adapter that always omits metadata fails.

To audit the integration's existing adapter against the same expectations:

```sh
python scripts/check_energy_consumer.py --integration-source /path/to/eg4_web_monitor --audit-legacy
```

The audit returns a nonzero exit status for unsafe cases. An integration still
using legacy `snapshot.timestamp` will fail cases where conversion or processing
time differs from the trusted acquisition evidence. This audit directly invokes
that adapter with the snapshots; it does not claim every snapshot is reachable
through the integration's deployed coordinator path.

Passing the reference-adapter harness demonstrates that the new API supplies
evidence usable by the real daily guard. It does **not** demonstrate shipped
integration adoption, publication of a new library package, or resolution of
cloud counter-day uncertainty in eg4_web_monitor #666.
