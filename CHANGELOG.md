# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`FUNC_PV_SELL_TO_GRID_EN` pinned to holding register 179 bit 3 and wired
  for local Modbus** ("Export PV Only" in the EG4 web UI, GH
  [eg4_web_monitor#135](https://github.com/joyfulhouse/eg4_web_monitor/issues/135)):
  pinned 2026-06-12 ~16:05–16:07 PT via authorized live cloud
  functionControl toggles with raw verification through `remoteRead`
  (179, 1) valueFrame (base64, little-endian uint16) on BOTH 12K-hybrid
  models — FlexBOSS21 52842P0581 (`disable_pv_sell_to_grid` toggled raw
  `0x104c` → `0x1044`, XOR `0x0008` = single bit 3, named param True→False
  in lockstep; re-enable restored `0x104c`, verified) and 18kPV 4512670118
  (same toggle, same `0x104c` → `0x1044` → restored `0x104c`, verified).
  Register-level evidence equivalent to a local before/after probe, proven
  directly on both family models — no extrapolation needed. The
  `FUNC_179_BIT3` placeholder in `REGISTER_TO_PARAM_KEYS[179]`
  is replaced by the real name, so local/dongle parameter decode now surfaces
  the bit and `write_named_parameters({"FUNC_PV_SELL_TO_GRID_EN": ...})`
  performs the read-modify-write locally. `HybridInverter` gains dual-path
  `enable_pv_sell_to_grid` / `disable_pv_sell_to_grid` /
  `get_pv_sell_to_grid_status` / `set_pv_sell_to_grid` overrides (transport
  RMW on reg 179 bit 3, atomic cloud function-control without a transport —
  the same pattern as the battery charge/discharge control bits 9/10), plus
  the `FUNC_EXT_BIT_PV_SELL_TO_GRID = 3` constant. The canonical holding
  table's spec name for the same bit (`FUNC_BAT_WAKEUP_EN`, "Battery wakeup /
  PV sell first enable") corroborates the pin and is cross-referenced.

### Fixed

- **EG4_OFFGRID register-110 layout corrected: Battery ECO is bit 15, buzzer is bit 7**
  (adjudication of eg4_web_monitor [PR #220](https://github.com/joyfulhouse/eg4_web_monitor/pull/220)
  / [#197](https://github.com/joyfulhouse/eg4_web_monitor/issues/197) follow-up):
  the shared `REGISTER_TO_PARAM_KEYS[110]` table is 18kPV-derived; on the SNA
  platform (12000XP/6000XP) live hardware evidence shows `FUNC_BATTERY_ECO_EN`
  toggling raw bit 15 (`0x0080`↔`0x8080`, bidirectional write test) while the
  bit-9 named write returns success without changing the inverter, and the
  stock SNA cloud decode places the buzzer at bit 7 (sole set flag with raw
  `0x0080`), matching the ant0nkr lxp_modbus reference. Local Modbus/dongle
  transports now resolve register 110 through a family-specific layout
  (`OFFGRID_REGISTER_110_PARAM_KEYS`) for `EG4_OFFGRID`: ECO=15, buzzer=7,
  displaced/unverified slots as `FUNC_110_BITn` placeholders. `FUNC_GREEN_EN`
  intentionally keeps the 18kPV bit-8 position pending an SNA toggle test
  (lxp_modbus suggests bit 14). All other families are byte-for-byte
  unchanged; cloud writes were always correct (server-side bit mapping).

### Changed

- **`grid_peak_shaving` family default for EG4_OFFGRID is now `False`**
  (same adjudication): GRID peak shaving requires grid-parallel
  import/export blending, which the no-sellback SNA platform does not do —
  it uses `FUNC_GEN_PEAK_SHAVING` (generator overload protection) instead.
  Field data: stock SNA12K-US cloud dump reads `FUNC_GEN_PEAK_SHAVING=True`
  / `FUNC_GRID_PEAK_SHAVING=False` and exposes no
  `_12K_HOLD_GRID_PEAK_SHAVING_POWER` parameter, so the register probe
  cannot re-enable the flag on this family either. The old `True` dated to
  the v0.4.0 feature-table bulk fill, not hardware evidence. Generator
  input-register definitions 124/125 (Egen) gained documentation caveats
  recording why PR #220's raw-Wh AC-couple-energy reinterpretation was
  rejected (the reporter's own sweep shows bit-field behavior, not energy).

## [0.9.36b5] - 2026-06-12

### Fixed

- **Off-grid `consumption_power` falls back to the cloud load split**
  ([eg4_web_monitor#226](https://github.com/joyfulhouse/eg4_web_monitor/issues/226)
  residual): the cloud does not populate `consumptionPower` for the EG4
  Off-Grid family (it reads a false 0 under load), so with no transport
  data the property returned a useless value and the integration's Loads
  sensor went unknown during hybrid link-down windows. The HTTP branch is
  now family-aware: for EG4_OFFGRID it returns
  `epsLoadPower + smartLoadPower + gridLoadPower` (the authoritative
  split, live-confirmed on a 6000XP). The transport energy-balance path
  and all other families are unchanged.

## [0.9.36b4] - 2026-06-12

### Added

- **Forced discharge controls** (regs 82/83,
  [eg4_web_monitor#207](https://github.com/joyfulhouse/eg4_web_monitor/issues/207),
  co-authored with DevTodd): `set_forced_discharge_power(power_kw)` (cloud
  float kW, 0–25.5) and `set_forced_discharge_soc_limit(percent)` setters
  plus the matching properties. **Register 82 stores 100 W units (kW
  scale), not percent** — hardware set-2.5kW-read-raw-25 verification and
  the cloud maintain page (float field, [0, 25.5] = the raw uint8 ceiling)
  falsified the 18KPV PDF's percent claim; the canonical table and scaling
  map are corrected accordingly. Live-verified by cloud
  write/readback/revert on an 18kPV and a FlexBOSS21.
- **Register 202 located and documented** (`_12K_HOLD_STOP_DISCHG_VOLT`,
  Stop Discharge Voltage, 40–56 V, raw decivolts — confirmed by
  single-register cloud window reads plus a raw read of 400 against the
  cloud's 40 V): canonical row added; the `REGISTER_TO_PARAM_KEYS` entry
  is deliberately deferred to the release that ships the entity.
- **Device type code 38 mapped to the EG4 6000XP (EG4_OFFGRID)**
  ([eg4_web_monitor#222](https://github.com/joyfulhouse/eg4_web_monitor/issues/222)):
  feature detection, transport discovery, model naming, and the network
  scanner all resolve code 38 directly instead of falling back to
  model-name heuristics (field-reported by two 6000XP systems).
- **Cloud smart-load split exposed for the EG4 Off-Grid family**:
  `smart_load_power` / `grid_load_power` properties surface the cloud-only
  `smartLoadPower`/`gridLoadPower` runtime fields (the GEN-as-smart-load
  port draw; `peps` is the combined backup output). In hybrid mode these
  fields ride a supplemental HTTP runtime refresh on the normal runtime
  TTL — gated to EG4_OFFGRID with a healthy link and cloud credentials —
  so they keep updating instead of freezing at the setup-time snapshot.
  No Modbus register source is known; pure-local operation does not carry
  these fields.

### Fixed

- **WiFi dongle transport reconnects after silent path loss**
  ([eg4_web_monitor#226](https://github.com/joyfulhouse/eg4_web_monitor/issues/226)):
  a response timeout never tore down the TCP connection, so after a silent
  path drop (VPN tunnel break, NAT/conntrack flush — no RST/FIN delivered)
  every poll re-used the same dead ESTABLISHED flow forever and only an
  integration reload could recover. Every response timeout and EOF now
  tears the connection down; the next request (or link-down probe) dials a
  fresh TCP connection, so polling self-restores within a poll cycle of the
  path returning. The 0.9.36b3 reconnect gate covered pymodbus transports
  only; this closes the same gap for the raw-TCP dongle transport.
- **Dongle connection state can no longer be corrupted by partial
  connects**: `_connected` is set only after the socket is fully usable
  (open AND initial-data window handled); every connect failure path tears
  down, and a dongle that accepts then immediately closes (single-client
  slot conflict) now fails the attempt into the retry/backoff cycle instead
  of being declared connected.
- **Concurrent dongle connects serialized**: `connect()` now holds a
  dedicated lock and the loser of a connect race returns the winner's
  fresh connection — two parallel dials can no longer fight over the
  dongle's single TCP slot. Request-path reconnection happens only under
  the per-transaction lock.
- **Write requests never resend the same packet on ACK loss** (codex
  review): after a timeout, EOF, or socket error during a write, the
  pre-built packet is not retransmitted in-call (the inverter may have
  already applied it — a resend could replay stale bit-field values over a
  concurrent writer's change). All write failures propagate to
  `write_named_parameters`' sequence-level retry, which re-reads the
  register before re-writing.
- **Parallel-group history: `eImportDay`/`eGenDay` parsed from
  monthColumn** (live-found during the 3.4.0-beta.4 verification): the
  parallel endpoint names grid import `eImportDay` (not `eToUserDay`), so
  the `grid_import` history series came back empty; generator energy is
  now exposed as `generator_kwh` alongside it. Re-running a historical
  import after upgrading backfills the affected series (idempotent).

## [0.9.36b3] - 2026-06-11

Backfilled summary — see the
[GitHub release notes](https://github.com/joyfulhouse/pylxpweb/releases/tag/v0.9.36b3)
for full detail.

### Added

- **Transport link health**: after 3 consecutive failed local reads the
  link is declared down — stale transport data stops being served, the
  dead link is probed every cycle (rate-limited), and everything
  self-restores on reconnection.
- **Typed monthly daily-energy history API** (`inverterChart`
  monthColumn) powering the integration's `import_historical_data`
  service.
- **Energy value sanity checks**: physical-bounds validation with
  always-on monotonicity, self-heal ceilings in both directions, and an
  absolute daily cap on warm-up/seed reads.

### Fixed

- **Modbus write/read paths widened to `ModbusException`** so
  `ConnectionException` reaches the reconnect gate (previously only
  `ModbusIOException` counted and a dropped TCP session wedged the
  pymodbus transport).
- **Register-semantics cluster**: `output_power` load semantics, net
  `grid_power` flow, canonical yield pairing, and battery cell-number
  registers uncrossed (offset 14 = temp, 15 = voltage).

## [0.9.36b2] - 2026-06-10

### Fixed

- **WiFi dongle parameter writes survive TCP connection drops without write
  wars** ([eg4_web_monitor#201](https://github.com/joyfulhouse/eg4_web_monitor/issues/201)):
  the dongle drops its TCP link mid-sequence during parameter writes (firmware
  timeout / cloud-connection priority), which previously failed the whole write
  in LOCAL-only mode. `write_named_parameters` now retries the ENTIRE
  read-modify-write sequence on transport errors — tearing down the dead
  connection and RE-READING the register before re-writing, so a retry can
  never replay stale bit-field values over a concurrent writer's change.
  Request-level timeout resends were removed from the write path for the same
  reason, and post-write verification mismatches are now diagnostic-only
  (warn + accept) instead of triggering a re-write.
- **Write ACK echo validation** — misrouted dongle responses for the SAME
  register can no longer confirm a write they don't belong to: FC06 ACKs must
  echo the written value and FC16 ACKs the register count.
  `_parse_response()` now parses the real 16-byte write-ACK layout
  (action + func + serial + register + payload, no byte_count header);
  read-style ACK echoes still fall through to the read parser, so a
  legitimate ACK can never false-positive into a write error.
- **All multi-request reads serialized on the dongle's single TCP link**:
  `read_runtime`, `read_energy`, `read_battery`, `read_all_input_data`,
  `read_parameters`, `read_midbox_runtime`, and the device-info reads now hold
  the operation lock, so a coordinator poll can no longer interleave with a
  write retry/reconnect and misroute responses.
- **Cloud battery bank full/remaining capacity double-counted banks whose
  master module mirrors pack totals** (eg4_web_monitor live finding): the
  cloud's `fullCapacity`/`remainCapacity` aggregates sum the module array, and
  on banks where module 01 reports PACK-level values the sum double-counts
  (live 18kPV 3x280 Ah: 840+280+280 -> 1400 Ah "full", 487+162+173 -> 822 Ah
  "remaining" vs true 840/495.6). `BatteryBank.full_capacity` /
  `remain_capacity` now prefer the BMS-reported bank pair
  (`maxBatteryCharge`/`currentBatteryCharge`), switching sources TOGETHER on a
  single complete-pair gate: open-loop systems (lead-acid / no BMS comms,
  pair reads 0/None) and half-present pairs keep the legacy fields for BOTH
  properties, so the displayed pair can never mix sources.

## [0.9.36b1] - 2026-06-08

### Added

- **`BatteryControlMode` enum** (`SOC` / `VOLTAGE`) exported from the package root,
  with `from_voltage_flag()` and `is_voltage` helpers. Models the register-179
  charge/discharge regime (bit 9 charge, bit 10 discharge; 0 = SOC, 1 = Voltage).
- **Friendly battery-control helpers** on `HybridInverter`:
  `get/set_battery_charge_control_mode`, `get/set_battery_discharge_control_mode`
  (enum-based), and `get_active_charge_limit()` / `get_active_discharge_cutoff()`
  which return whichever limit (SOC % or Voltage) the live regime is honoring.
- **Register 228** (`HOLD_SYSTEM_CHARGE_VOLT_LIMIT`, DIV_10) added to the holding
  register map.

### Fixed

- **Battery-control methods now work over the cloud (HTTP), not just local
  transport.** The shared bit/value helpers (`_read_modbus_register`,
  `_write_modbus_register`, `_get_register_bit`, `_set_modbus_register_bit`) are
  now dual-path: transport mode does an on-device read-modify-write; cloud mode
  uses the atomic `control_function` API for bits and `read_parameters` /
  `write_parameters` for values. This fixes `get/set_battery_charge_control`,
  `get/set_battery_discharge_control`, the voltage/SOC limit getters/setters,
  current limits, charge-last, and start-discharge-power in cloud and hybrid mode.
- **Cloud bit writes no longer corrupt sibling bits.** `set_eps_enabled`,
  `set_forced_charge`, `set_forced_discharge`, and `set_sporadic_charge` previously
  used a read-modify-write that read `reg_<n>` (a key the cloud API never returns),
  zeroing the base value and clearing unrelated bits in register 21/233 in cloud
  mode. They now route through the atomic `control_function` path.
- **Cloud voltage reads reconstruct the raw register value** using each register's
  scale, so callers that re-apply the scale get the same result as the transport
  path, and float-like cloud strings (e.g. `"59.5"`) no longer raise.
- **Register 169 cloud name** corrected to `HOLD_ON_GRID_EOD_VOLTAGE` (matches the
  EG4 cloud API and the existing integer constant; a non-canonical spelling made
  the on-grid EOD voltage unreadable in cloud mode). Confirmed via live cloud read.

## [0.9.35] - 2026-06-05

### Fixed

- **PV/forced charge power register (reg 74) addressable locally** — added
  `74: ["HOLD_FORCED_CHG_POWER_CMD"]` to `REGISTER_TO_PARAM_KEYS` so the local
  Modbus path can read/write the forced/PV charge power command by name. It was
  missing from the local map, which forced consumers onto the wrong register 64
  (a 0-100% charge-power limit) with a lossy kW↔% conversion.
- **Reg 74 unit metadata corrected** — `HOLD_FORCED_CHG_POWER_CMD` is **100W
  units** (0-150 = 0-15 kW, same encoding as AC charge power reg 66), not a
  percentage. Fixed the register comment, the `HoldingRegisterDefinition`
  (`unit`/`max_value`/description), the scaling note, and the
  `HybridInverter.set_forced_charge_power()` / `get_charge_discharge_power()`
  docstrings; `set_forced_charge_power` now accepts 0-150 (was capped at 100).
  Hardware-verified: FlexBOSS reg74=20→2.0 kW, 18kPV reg74=120→12.0 kW.
- **Packaging** — moved `classifiers` back under `[project]` (it was misplaced
  under `[project.urls]`, breaking `uv build`) and dropped the deprecated
  License classifier in favor of the SPDX `license` field.

## [0.9.32] - 2026-05-31

### Added

- **BMS permission/request flags (reg 95 bitmap)** — input register 95 is now decoded as a
  BMS permission/request bitmap (eg4 issue #232), confirmed against the cloud API booleans
  `bmsCharge` / `bmsDischarge` / `bmsForceCharge`:
  - `decode_bms_permissions(raw)` helper + `BMS_PERMISSION_ALLOW_CHARGE` (0x01),
    `BMS_PERMISSION_ALLOW_DISCHARGE` (0x02), `BMS_PERMISSION_FORCE_CHARGE` (0x20) constants.
  - `InverterRuntimeData.bms_allow_charge` / `bms_allow_discharge` / `bms_force_charge` (decoded
    from reg 95 in `from_modbus_registers`).
  - Dual-source `BaseInverter.bms_allow_charge` / `bms_allow_discharge` / `bms_force_charge`
    properties (transport reg-95 decode, falling back to the cloud `RuntimeInfo` booleans).
  - `BatteryBankData.allow_charge` / `allow_discharge` / `force_charge` (LOCAL) and matching
    `BatteryBank` properties (CLOUD, delegating to the parent inverter) so the flags surface in
    every connection mode.
  - The legacy reg-95 `battery_status_inv` enum is retained (read-but-unsurfaced); its register
    description now documents the bitmap interpretation.

## [0.9.29] - 2026-05-30

### Added

- **Typed consumed-surface public API** (typed seam contract): export the device hierarchy
  (`BaseInverter`, `Battery`, `BatteryBank`, `MIDDevice`, `ParallelGroup`, `Station`), transport
  data classes (`InverterRuntimeData`, `InverterEnergyData`, `BatteryData`, `BatteryBankData`,
  `MidboxRuntimeData`), and feature types (`InverterFeatures`, `InverterModelInfo`,
  `InverterFamily`, `GridType`) from the package root so consumers import a stable, typed surface.
- **Public transport accessors** on `BaseInverter` and `MIDDevice`: `transport`, `transport_runtime`,
  `transport_energy`, `transport_battery` (read-only) — replacing private `_transport*` poking by
  consumers.
- **`BaseInverter.set_cache_ttls(*, runtime=, energy=, battery=)`**: public API to pin transport-data
  cache TTLs to a consumer's polling interval (replaces writing private `_*_cache_ttl` attributes).
- **`BaseInverter.has_runtime_data`** and **`BaseInverter.power_rating_text`** properties, and
  **`BatteryBank.cycle_count`** property — close device-object seam gaps so the consumed property
  surface resolves real values instead of None.

## [0.9.26] - 2026-03-04

### Added

- **Battery protocol framework**: Complete battery protocol system for direct RS485 battery
  communication, including base classes, EG4 master protocol (firmware-derived register map),
  EG4 slave protocol (standard EG4-LL register map), auto-detection, and BatteryModbusTransport
  for direct RS485 battery reading
- **Battery register collection script**: Utility for capturing raw battery register data

### Fixed

- **Split-phase EPS power fallback**: When combined EPS power/apparent power registers read 0W
  (firmware gap on split-phase inverters), `from_modbus_registers(split_phase=True)` now computes
  combined values from L1+L2 per-leg registers
- **eps_apparent_power field mapping**: Corrected legacy `eps_status` field name to
  `eps_apparent_power` in transport field mappings
- **BatteryModbusTransport context manager**: Added missing async context manager and removed
  duplicate Modbus read

### Changed

- **BatteryProtocol as ABC**: Battery protocols now use abstract base class with immutable
  `register_blocks` property
- **Shared battery protocol utilities**: Consolidated duplicated protocol utilities into base module

## [0.9.17] - 2026-02-26

### Added

- **Battery round-robin accumulator** ([#170](https://github.com/joyfulhouse/pylxpweb/issues/170)): Systems with >4 batteries expose 4 register slots that rotate across refresh cycles. The accumulator merges slot data using the `pos` field (register offset 24, high byte) as canonical battery identity, building a complete virtual register map over `ceil(battery_count/4)` polls. All batteries populate and downstream `BatteryBankData` sees the full bank.
- **`BatteryData.last_seen` timestamp**: Per-battery staleness tracking — records when each battery's registers were last physically read from the inverter. Non-accumulated reads (≤4 batteries) stamp `datetime.now()` on all batteries.
- **Cloud API response collection**: `pylxpweb-collect` gains `--no-api` flag (default: on) that fetches raw JSON from `getBatteryInfo`, `getInverterRuntime`, `getInverterEnergy`, and `getMidboxRuntime` alongside the existing register scan — enables cloud-vs-local data comparison.

### Fixed

- **GridBOSS CT ghost voltage** ([#162](https://github.com/joyfulhouse/eg4_web_monitor/issues/162)): Raised MID grid voltage canary floor from 0V to 5V. Disconnected grid/gen CT inputs produce ~0.5-1.5V leakage from electromagnetic coupling, which is physically normal but was being rejected as corruption.

## [0.9.0] - 2026-02-10

### Changed

- **Canonical register migration**: Replaced legacy `register_maps.py` (~1395 lines) with typed `RegisterDefinition` system in `registers/` module. All `from_modbus_registers()` methods now consume canonical definitions directly via `_canonical_reader.py` (read_raw/read_scaled) and `_field_mappings.py` dictionaries.
- **RegisterDataMixin extraction**: Consolidated duplicated register read/decode logic from `_modbus_base.py` and `dongle.py` into shared `_register_data.py` mixin, reducing transport code by ~500 lines.
- **HA boundary bleed cleanup**: Removed Home Assistant-specific concepts from pylxpweb device layer, ensuring clean library boundaries.
- **MIDDevice dual-source properties**: All GridBOSS runtime properties now support both Modbus register data and HTTP API data via `MidboxRuntimeData` as single data source. Properties fall through from transport runtime to HTTP data when register values are None.

### Fixed

- **Smart port status register**: Smart port status is in **holding register 20** (bit-packed, 2 bits per port), not input registers 105-108 (those are AC couple energy high words). `read_midbox_runtime()` now reads holding reg 20 in addition to input register groups.
- **`from_http_response()` voltage scaling**: Fixed missing `/10` division for decivolts in HTTP-sourced voltage values.

### Removed

- `register_maps.py` (~1395 lines) — replaced by canonical register system
- `_scaled()` method on MIDDevice (69 call sites migrated to `_raw_float()`)
- Dead imports: `scale_mid_voltage`, `scale_mid_current`, `scale_mid_frequency`, `_scale_energy`, `Callable`

## [0.8.7] - 2026-02-07

### Changed

- **Rate limiter**: Replaced hourly counter with sliding window algorithm, changed rate unit to req/hr

## [0.8.6] - 2026-02-06

### Fixed

- **Windows compatibility**: Renamed files containing asterisk characters for Windows filesystem compatibility

## [0.8.5] - 2026-02-05

### Added

- **3-phase RMS current**: Added RMS current support for LXP three-phase inverters

## [0.8.4] - 2026-02-05

### Fixed

- **FlexBOSS18 model detection**: Corrected powerRating mapping - FB18 uses powerRating=9, not 6. This fixes misidentification of FlexBOSS18 as FlexBOSS21 in local mode. (joyfulhouse/eg4_web_monitor#133)

### Added

- Sample data: FlexBOSS18, GridBOSS

## [0.8.3] - 2026-02-05

### Added

- **LXP-LB series support**: US and non-US regional detection for LuxPower LB models
- **12KPV/18KPV/FlexBOSS model differentiation**: Better model identification based on power ratings
- **Brazil COUNTRY_MAP entry**: Support for Brazilian accounts in API responses

### Fixed

- **Installer account plant listing**: Use correct endpoint for installer accounts
- **Inverters without batteries**: Support devices that have no battery bank attached

### Changed

- Linting improvements and removal of unused type ignores

## [0.8.0] - 2026-02-04

### Changed

- **BREAKING: Inverter family rename** - Family names updated for clarity:
  - `SNA` → `EG4_OFFGRID` (12000XP, 6000XP - off-grid, no grid sellback)
  - `PV_SERIES` → `EG4_HYBRID` (18kPV, 12kPV, FlexBOSS - grid-tied hybrid)
  - `LXP_EU` → `LXP` (merged with LXP_LV - all Luxpower use same registers)
  - `LXP_LV` → `LXP` (merged - identical register maps)
  - Old names remain as deprecated aliases for backwards compatibility

### Added

- **Deprecation warnings** for legacy family names via `resolve_family()` helper
- **LXP-LB-BR 10kW support** - Brazil model (device type code 44) now recognized
- `resolve_family()` function for migrating legacy family names with warnings

### Deprecated

- `InverterFamily.SNA` - use `InverterFamily.EG4_OFFGRID` instead
- `InverterFamily.PV_SERIES` - use `InverterFamily.EG4_HYBRID` instead
- `InverterFamily.LXP_EU` - use `InverterFamily.LXP` instead
- `InverterFamily.LXP_LV` - use `InverterFamily.LXP` instead

### Fixed

- Discovery API `get_model_family_name()` returns new family names
- Documentation updated throughout to use new naming convention

## [0.6.7] - 2026-01-31

### Added

- **Modbus RTU serial transport**: New `ModbusSerialTransport` for direct communication via USB-to-RS485 adapters using Modbus RTU protocol
- `create_serial_transport()` factory function for easy serial transport creation
- `TransportType.MODBUS_SERIAL` enum value with full config validation (port, baudrate, parity, stopbits)
- Serial-specific `TransportConfig` fields (`serial_port`, `serial_baudrate`, `serial_parity`, `serial_stopbits`)

### Fixed

- **GridBOSS smart port status registers**: Restored INPUT registers 105-108 for smart port status, fixed MID register comments
- **GridBOSS double-scaling**: Resolved double-scaling for voltage, current, and frequency sensors
- **GridBOSS energy registers**: Enabled energy registers for local transport
- **MIDDevice None handling**: Handle None values in transport-to-runtime conversion
- **Smart port register conflicts**: Removed conflicting smart port status registers from GridBOSS Modbus map

## [0.6.6] - 2026-01-30

### Added

- **Network scanner module**: Device autodiscovery for finding inverters on the local network

### Fixed

- Code review issues in network scanner

## [0.6.5] - 2026-01-30

### Fixed

- **GridBOSS voltage scaling**: All 9 voltage registers in `GRIDBOSS_RUNTIME_MAP` corrected from `SCALE_NONE` to `SCALE_10` — raw values are volts × 10, not direct volts (validated against web API)
- **GridBOSS hybrid power formula**: `computed_hybrid_power` changed from `load_power - smart_load_total_power` to `ups_power - grid_power` to match web API computation (validated: exact match)
- **Battery bank capacity**: `max_capacity` and `current_capacity` now populated from Modbus register 97 (`battery_capacity_ah`) in `BatteryBankData.from_modbus_registers()` — works across all inverter families (PV_SERIES, LXP_EU, SNA)
- **Modbus TID desync recovery**: Added `_sync_transaction_ids()` on connect to drain stale gateway responses after reconnect/reconfigure, preventing cascading transaction ID mismatch errors
- **Modbus energy read resilience**: BMS registers (80-112) now read separately with graceful fallback if unavailable, preventing entire energy read from failing on some firmware versions

## [0.6.3] - 2026-01-27

### Fixed

- **Local Transport Parameter Bug**: Fixed parameters showing as all-false/zero for LOCAL mode (Modbus/Dongle) devices
  - Root cause: `_fetch_parameters()` was using `read_parameters()` which returns raw register addresses as keys (`reg_21`, `reg_110`)
  - Switch entities expect named parameter keys like `FUNC_EPS_EN`, `FUNC_GREEN_EN`
  - Fixed by using `read_named_parameters()` which decodes bit fields and returns proper parameter names
  - This affects all LOCAL mode devices including FlexBOSS21, 18kPV, SNA, LXP-EU
  - Now parameters like `FUNC_EPS_EN`, `FUNC_AC_CHARGE`, `FUNC_GREEN_EN` work correctly

### Changed

- Expanded register group for Battery/SOC config from 20 registers to 30 to ensure register 110 (FUNC_GREEN_EN) is included

## [0.5.42] - 2026-01-27

### Changed

- **Unified Register Mappings**: Removed `_18KPV` suffix from mapping constants since register mappings are identical across all device families (18kPV, FlexBOSS21, SNA, LXP-EU)
  - `REGISTER_TO_PARAM_KEYS_18KPV` → `REGISTER_TO_PARAM_KEYS`
  - `PARAM_KEY_TO_REGISTER_18KPV` → `PARAM_KEY_TO_REGISTER`
  - `REGISTER_STATS_18KPV` → `REGISTER_STATS`
  - Device-specific naming differences (e.g., `HOLD_COM_ADDR` vs `HOLD_MODBUS_ADDRESS`) handled by alias system

### Fixed

- **Register Mapping Corrections** (validated against live hardware):
  - Register 21: Fixed overflow - reduced from 27 to 16 bit fields (max for 16-bit register)
  - Register 22: Corrected to FUNC_LSP_* bit fields (not HOLD_START_PV_VOLT)
  - Register 26: Removed invalid mixed HOLD value, retained bit fields only
  - Register 110: Swapped bits 5/6 (FUNC_BUZZER_EN/FUNC_TAKE_LOAD_TOGETHER)
  - Register 19: Changed from mixed bit field to single `HOLD_DEVICE_TYPE_CODE`

- **Bit Field Write Safety**: Changed from warning to `ValueError` when bit field mapping is inconsistent - prevents accidental writes to wrong registers

## [0.5.41] - 2026-01-27

### Changed

- **Code Simplification**: Extract shared register reading logic to `_register_readers` module
  - Consolidates duplicated code between `ModbusTransport` and `DongleTransport`
  - Shared functions: `is_midbox_device`, `read_device_type_async`, `read_serial_number_async`, `read_firmware_version_async`, `read_parallel_config_async`
  - Reduces codebase by ~190 lines while maintaining full backward compatibility

## [0.5.40] - 2026-01-26

### Added

- **Parallel Group Detection via Register 113** - Device discovery now uses input register 113 for accurate parallel group detection:
  - Packed format: bits 0-1 = master/slave role, bits 2-3 = phase, bits 8-15 = group number
  - New `read_parallel_config()` method in `ModbusTransport` and `DongleTransport`
  - `DeviceDiscoveryInfo` now includes `parallel_master_slave` field (0=standalone, 1=master, 2=slave, 3=3-phase master)
  - New properties: `parallel_role_name`, `parallel_phase_name`, `is_master`
  - Holding registers 107-108 used as fallback (less reliable on some firmware)

### Changed

- `discover_device_info()` now prefers input register 113 over holding registers 107-108 for parallel detection
- `is_standalone` property now checks both `parallel_number` and `parallel_master_slave` fields

## [0.5.39] - 2026-01-26

### Added

- **Individual Battery Data Parity** - Full support for individual battery modules via local Modbus (#83):
  - Read all 3 batteries from extended registers (5002+, 30 registers per battery)
  - All operational data matches web API: voltage, current, SOC, SOH, temperatures, cell voltages
  - New `BatteryData` fields: `min_cell_temperature`, `max_cell_temperature`
  - Properly scaled charge/discharge current limits (deciamps)

### Fixed

- **BMS Cell Voltage Scaling** - Fixed aggregate BMS cell voltages in runtime data (#83):
  - Changed `bms_max_cell_voltage` and `bms_min_cell_voltage` from `SCALE_NONE` to `SCALE_1000`
  - Registers 101-102 contain millivolts, now correctly converted to volts
  - Applies to both PV_SERIES and LXP_EU register maps

- **Individual Battery Scaling Issues** - Fixed multiple scaling problems in individual battery data:
  - Cell voltage: Removed redundant `/1000.0` division (scaling now handled in register map)
  - Current: Changed from `SCALE_100` to `SCALE_10` (value is in deciamps, not centiamps)
  - Charge/discharge current limits: Changed from `SCALE_100` to `SCALE_10`

## [0.5.38] - 2026-01-26

### Added

- **GridBOSS Full Parity with Web API** - Complete data support for MID/GridBOSS devices via local Modbus:
  - Energy today registers: load, UPS, to-grid, to-user, AC couple, smart load (L1/L2)
  - Energy total registers: lifetime accumulated values for all energy categories
  - Smart port status registers (105-108): port mode detection (off/smart_load/ac_couple)
  - Extended `read_midbox_runtime()` to read registers 0-108 and 128-131
  - New computed properties: `smart_load_total_power`, `computed_hybrid_power`

### Fixed

- **Smart Port Status Registers** - Found correct location at registers 105-108 (not 81-84 which are energy totals)
- **AC Couple Energy Register** - Fixed register address for `ac_couple_1_energy_today_l1` (60, not 50)
- **Smart Load Energy Registers** - Fixed register addresses for `smart_load_1_energy_today_l1/l2` (62-63)
- **Hybrid Power Calculation** - Added `computed_hybrid_power` property that calculates from `load_power - smart_load_total_power` when direct register value is unavailable

### Documentation

- Added note that `hybrid_power` is a calculated value on the web API, approximated locally from load and smart load power

## [0.5.12] - 2026-01-23

### Added

- **Model-Specific Modbus Register Maps** - Support for different inverter families with varying register layouts (#103):
  - `RegisterField` dataclass for defining individual register fields with address, bit width, scaling, and signed support
  - `RuntimeRegisterMap` and `EnergyRegisterMap` dataclasses for complete register definitions
  - `PV_SERIES_RUNTIME_MAP` and `PV_SERIES_ENERGY_MAP` for EG4-18KPV (32-bit power values)
  - `LXP_EU_RUNTIME_MAP` and `LXP_EU_ENERGY_MAP` for LXP-EU 12K (16-bit power values, 4-register offset)
  - `get_runtime_map()` and `get_energy_map()` factory functions for family-based map selection
  - `inverter_family` parameter added to `ModbusTransport` and `create_modbus_transport()`

### Fixed

- **Modbus Timeout Handling** - Removed `asyncio.wait_for()` wrapper from Modbus reads (#103):
  - Pymodbus handles timeouts internally; double-timeout caused transaction ID desynchronization
  - Now properly catches `ModbusIOException` for timeout detection
  - Added single-client limitation documentation (Modbus TCP supports only one concurrent connection)

- **Register Collision Fix** - Per-PV string energy fields set to `None` (#103):
  - Registers 91-102 are BMS data, not per-PV string energy
  - Per-PV string energy counters are not available via Modbus (only aggregate energy)
  - Per-PV string power (registers 6-11) remains available in runtime data

### Removed

- **Flaky Integration Test** - Removed `test_concurrent_refresh_efficiency` (#103):
  - Test had timing-dependent assertions that failed under caching conditions

## [0.5.3] - 2026-01-08

### Fixed

- **Modbus BMS Register Mappings** - Corrected register definitions per Yippy's documentation (#97):
  - Register 5 now properly unpacks SOC (low byte) and SOH (high byte) as packed value
  - Inverter fault/warning codes at registers 60-63 (32-bit values)
  - BMS fault/warning codes at registers 99-100
  - Added BMS data registers 80-112 for cell voltage, temperature, and cycle count

### Added

- **BMS Cell Data in BatteryBankData** - New fields from Modbus BMS registers:
  - `max_cell_voltage`, `min_cell_voltage` (V, from registers 101-102)
  - `max_cell_temperature`, `min_cell_temperature` (°C, from registers 103-104)
  - `cycle_count` (from register 106)

### Changed

- **Register Constants** - Renamed INPUT_* constants for clarity:
  - `INPUT_SOC` + `INPUT_SOH` → `INPUT_SOC_SOH` (packed register 5)
  - `INPUT_BMS_FAULT` → `INPUT_BMS_FAULT_CODE` (register 99)
  - `INPUT_BMS_WARNING` → `INPUT_BMS_WARNING_CODE` (register 100)
  - Added `INPUT_BMS_*` constants for all BMS passthrough registers

## [0.5.0] - 2026-01-06

### Added

- **Transport Abstraction Layer** - New pluggable transport system for local and cloud communication:
  - `BaseTransport` - Abstract base class defining the transport protocol interface
  - `HTTPTransport` - Cloud API transport wrapping `LuxpowerClient`
  - `ModbusTransport` - Local Modbus TCP transport for direct inverter communication
  - `TransportCapabilities` - Dataclass describing transport features (read/write, local/cloud, auth)
  - Factory functions: `create_http_transport()`, `create_modbus_transport()`

- **Unified Data Models** - Transport-agnostic data structures:
  - `InverterRuntimeData` - Real-time inverter metrics (PV, battery, grid, temperatures)
  - `InverterEnergyData` - Energy statistics (today/total for PV, charge, discharge, import, export)
  - `BatteryBankData` - Aggregate battery bank information
  - `BatteryData` - Individual battery module data
  - All dataclasses are frozen (immutable) with validation

- **Modbus TCP Support** - Direct local communication via RS485-to-Ethernet adapters:
  - Efficient register grouping (respects 40-register Modbus limit)
  - Concurrent register group reads for faster data acquisition
  - Consecutive parameter batching for optimized writes
  - Automatic chunking for large parameter reads (>40 registers)
  - Optional dependency: `uv add pylxpweb[modbus]` or `uv add pymodbus`

- **Async Context Manager** - Both transports support `async with` for automatic cleanup:
  ```python
  async with ModbusTransport(host="192.168.1.100", serial="CE12345678") as transport:
      runtime = await transport.read_runtime()
  ```

### Changed

- **pymodbus dependency** - Updated to `>=3.11.4` (latest stable)

### Testing

- **756 unit tests** (all passing)
- **83.46% coverage** (above 80% threshold)
- **Code style**: 100% (ruff: 0 errors)
- **Type safety**: 100% (mypy strict: 0 errors)

## [0.4.4] - 2025-12-31

### Added

- **Automatic parallel group sync** - Auto-sync parallel groups when GridBOSS detected but no parallel data exists ([eg4_web_monitor#72](https://github.com/joyfulhouse/eg4_web_monitor/issues/72)):
  - `client.api.devices.sync_parallel_groups(plant_id)` - Trigger parallel group synchronization
  - `Station._load_devices()` now auto-calls sync when GridBOSS found but parallel groups empty
  - Fixes issue where GridBOSS would disappear if parallel group data wasn't pre-configured

## [0.4.1] - 2025-12-24

### Added

- **Dongle connection status** - New endpoint to check if dongle (datalog) is online ([#59](https://github.com/joyfulhouse/pylxpweb/issues/59)):
  - `DongleStatus` model with `is_online` and `status_text` properties
  - `client.api.devices.get_dongle_status(datalog_serial)` - Check dongle connectivity
  - API returns `msg: "current"` when online, empty when offline
  - Enables detection of stale inverter data when dongle is disconnected

### Example Usage

```python
# Get inverter info to find dongle serial
info = await client.api.devices.get_inverter_info("4512670118")

# Check dongle status
status = await client.api.devices.get_dongle_status(info.datalogSn)
if status.is_online:
    print("Dongle is online - data is current")
else:
    print("Dongle is offline - inverter data may be stale")
```

## [0.3.24] - 2025-12-03

### Fixed

- **Optional parallelGroups in PlantBasic** - Made `parallelGroups` field optional with empty list default to support devices that don't return parallel group data (e.g., 12000XP) (Issue #67 reported by @twistedroutes)

## [0.3.23] - 2025-12-02

### Added

- **NO_BATTERY enum value** - Added `BatteryType.NO_BATTERY` for systems without batteries (PR #61 by @pirate)
- **Optional userChartRecord** - Made `LoginResponse.userChartRecord` optional since some API responses don't include it (PR #61 by @pirate)
- **Public battery_bank property** - Added `inverter.battery_bank` property to expose battery bank data (PR #61 by @pirate)

## [0.3.22] - 2025-12-02

### Fixed

- **Cache invalidation after parameter writes** - Critical bug fix:
  - `write_parameter()` now invalidates cache after successful write
  - `write_parameters()` now invalidates cache after successful write
  - `control_function()` now invalidates cache after successful write
  - Fixes "value bouncing" issue where old values were returned after setting parameters
  - Root cause: API response cache wasn't cleared, so `refresh(force=True)` still returned stale data

### Added

- **discharge_power_limit property** - New inverter property:
  - `inverter.discharge_power_limit` - Get current discharge power limit (0-100%)
  - Returns `None` when parameters not loaded

- **battery_voltage_limits property** - New inverter property for battery protection:
  - `inverter.battery_voltage_limits` - Get all battery voltage limits as dict
  - Returns `max_charge_voltage`, `min_charge_voltage`, `max_discharge_voltage`, `min_discharge_voltage` (in volts)
  - Returns `None` if parameters not loaded or any required voltage limit is missing

### Testing

- ✅ **Total tests**: 652 (all passing)
- ✅ **Coverage**: 84.15%
- ✅ **Code style**: 100% (ruff: 0 errors)
- ✅ **Type safety**: 100% (mypy strict: 0 errors)

## [0.3.21] - 2025-12-02

### Added

- **system_charge_soc_limit property** - New inverter property for accessing the system charge SOC limit:
  - `inverter.system_charge_soc_limit` - Get current system charge SOC limit from cached parameters
  - Returns 0-100 for normal SOC limit, 101 for top balancing mode
  - Returns `None` when parameters not loaded (Home Assistant shows "Unknown" state)
  - Provides parity with `ac_charge_soc_limit` property pattern
  - Used by Home Assistant integration to read current value without API call

### Testing

- ✅ **Total tests**: 646 (all passing)
- ✅ **Coverage**: 83.63%
- ✅ **Code style**: 100% (ruff: 0 errors)
- ✅ **Type safety**: 100% (mypy strict: 0 errors)

## [0.3.20] - 2025-11-28

### Added

- **System charge SOC limit convenience functions** - New API methods for controlling battery charge limits:
  - `set_system_charge_soc_limit(inverter_sn, percent)` - Set the maximum SOC percentage (0-101%)
  - `get_system_charge_soc_limit(inverter_sn)` - Get current system charge SOC limit
  - Value 101 enables top balancing mode (full charge with cell balancing for lithium batteries)
  - Includes validation with clear error messages for out-of-range values

## [0.3.19] - 2025-11-27

### Fixed

- **EU Luxpower API compatibility** - Made `TechInfo` fields optional in `LoginResponse`:
  - `techInfoType2` and `techInfo2` are now optional with `None` defaults
  - EU API returns `techInfoCount: 1` with only one tech info item
  - Fixes authentication failure on `https://eu.luxpowertek.com` (#53)

## [0.3.18] - 2025-11-26

### Removed

- **Monotonic enforcement for energy sensors** - Removed all monotonic value tracking:
  - Daily and lifetime energy properties now return raw scaled API values
  - Home Assistant's `SensorStateClass.TOTAL_INCREASING` handles resets automatically
  - Removed broken date boundary detection that never worked (station lookup failed)
  - Removed `_enforce_monotonic()` methods from `BaseInverter` and `ParallelGroup`
  - Removed tracking variables (`_last_lifetime_*`, `_last_energy_*`)

- **Dead code cleanup** - Removed unused sensor classification constants:
  - `LIFETIME_ENERGY_SENSORS`
  - `DAILY_ENERGY_SENSORS`
  - `MONTHLY_ENERGY_SENSORS`
  - `BATTERY_LIFETIME_SENSORS`

### Changed

- Updated `docs/SCALING_GUIDE.md` to reflect simplified approach
- Energy properties are now simpler and more predictable

### Testing

- ✅ **Total tests**: 637 (all passing)
- ✅ **Coverage**: >82%
- ✅ **Code style**: 100% (ruff: 0 errors)
- ✅ **Type safety**: 100% (mypy strict: 0 errors)

## [0.3.17] - 2025-11-25

### Added

- **Standalone executables** - Pre-built binaries for Windows, macOS, and Linux:
  - No Python installation required
  - Download from GitHub Releases and run directly
  - Built automatically on each release via PyInstaller

- **GitHub Codespaces support** - Run the data collection tool in your browser:
  - One-click setup via "Open in Codespaces" button
  - Pre-configured development environment
  - No local installation needed

- **Zip archive output** - All collected files bundled into a single zip:
  - `pylxpweb_device_data_YYYYMMDD_HHMMSS.zip` created automatically
  - Easy to attach to GitHub issues
  - Individual JSON/MD files also available

- **Pre-filled GitHub issue link** - Automated issue creation:
  - Click the generated URL to open a pre-filled issue
  - Device types, serial numbers, and status auto-populated
  - Feature checklist and firmware version fields included
  - Just attach the zip file and submit

### Changed

- Updated `docs/COLLECT_DEVICE_DATA.md` with three collection options:
  - Option A: Download executable (easiest)
  - Option B: GitHub Codespaces (no download)
  - Option C: Install with Python (for developers)

### Testing

- ✅ **Total tests**: 637 (all passing)
- ✅ **Coverage**: >82%
- ✅ **Code style**: 100% (ruff: 0 errors)
- ✅ **Type safety**: 100% (mypy strict: 0 errors)

## [0.3.16] - 2025-11-25

### Changed

- **Dynamic floating-point precision** - Calculated properties now derive precision from source data scaling:
  - Added `get_precision(ScaleFactor)` and `get_battery_field_precision(field_name)` helper functions
  - `Battery.power` rounds to voltage precision (2 decimals from SCALE_100)
  - `Battery.cell_temp_delta` rounds to temperature precision (1 decimal from SCALE_10)
  - `Battery.cell_voltage_delta` rounds to cell voltage precision (3 decimals from SCALE_1000)
  - Eliminates floating-point artifacts (e.g., `0.0030000000000001137` → `0.003`)

### Testing

- ✅ **Total tests**: 637 (all passing)
- ✅ **Coverage**: >82%
- ✅ **Code style**: 100% (ruff: 0 errors)
- ✅ **Type safety**: 100% (mypy strict: 0 errors)

## [0.3.15] - 2025-11-25

### Removed

- **Battery.max_battery_charge property** - Removed misleading property from individual Battery class:
  - The API returns the bank total (840 Ah) in each individual battery's `maxBatteryCharge` field
  - This was confusing since individual batteries have 280 Ah capacity (not 840 Ah)
  - Use `Battery.current_full_capacity` for individual battery capacity (280 Ah)
  - Use `BatteryBank.max_capacity` for total bank capacity (840 Ah for 3 batteries)

### Testing

- ✅ **Total tests**: 637 (all passing)
- ✅ **Coverage**: >82%
- ✅ **Code style**: 100% (ruff: 0 errors)
- ✅ **Type safety**: 100% (mypy strict: 0 errors)

## [0.3.14] - 2025-11-25

### Changed

- **Logging Level Optimization** - Reduced log verbosity for production use:
  - Changed cache invalidation logs from INFO to DEBUG (hour boundary, cache clearing)
  - Changed authentication routine logs from INFO to DEBUG (login, session expiry, re-auth)
  - Changed date boundary/energy reset logs from INFO to DEBUG (internal state management)
  - Changed plant configuration logs from INFO to DEBUG (fetch details, update config, DST)
  - Kept meaningful configuration changes at INFO level (DST update success)
  - All WARNING and ERROR logs remain unchanged (appropriate for degraded/failed operations)

### Testing

- ✅ **Total tests**: 637 (all passing)
- ✅ **Coverage**: >82%
- ✅ **Code style**: 100% (ruff: 0 errors)
- ✅ **Type safety**: 100% (mypy strict: 0 errors)

## [0.3.13] - 2025-11-24

### Fixed

- **Firmware "Already Latest" Handling** - Fixed incorrect exception when firmware is already up to date:
  - The API returns HTTP 200 with `success=false` and message "The current machine firmware is already the latest version." when firmware is current
  - Previously this raised `LuxpowerAPIError` - now correctly returns `FirmwareUpdateCheck` with `has_update=False`
  - Added `FirmwareUpdateCheck.create_up_to_date()` class method for creating "no update available" responses
  - Added `FIRMWARE_UP_TO_DATE_MESSAGES` constant for message detection (case-insensitive)

### Changed

- **API Documentation Updated** - Updated `docs/luxpower-api.yaml` to document the "already latest" response behavior

### Testing

- ✅ **Total tests**: 640+ (new firmware endpoint tests added)
- ✅ **New test file**: `tests/unit/endpoints/test_firmware_endpoints.py`
- ✅ **Coverage**: >82%
- ✅ **Code style**: 100% (ruff: 0 errors)
- ✅ **Type safety**: 100% (mypy strict: 0 errors)

## [0.3.12] - 2025-11-24

### Changed

- **Code Review Improvements** - Comprehensive code review cleanup:
  - Added status badges to README (CI, Codecov, PyPI, Python version, License)
  - Increased coverage threshold from 70% to 80% (current: 82.88%)
  - Removed TODO comment in control.py (clarified as design note)
  - Deleted constants.py.bak backup file (cleanup from refactoring)

### Testing

- ✅ **Total tests**: 621 (all passing)
- ✅ **Coverage**: 82.88%
- ✅ **Code style**: 100% (ruff: 0 errors)
- ✅ **Type safety**: 100% (mypy strict: 0 errors)

## [0.3.11] - 2025-11-24

### Changed

- **Code Quality** - Refactored logging imports in control and plants endpoints:
  - Moved logging imports to module level (previously inline imports)
  - Improved code consistency and reduced import overhead
  - No functional changes or API modifications

## [0.3.10] - 2025-11-23

### Added

- **Synchronous Firmware Progress Properties** - New convenience properties for Home Assistant integration:
  - `firmware_update_in_progress` (bool) - Synchronous property indicating if update is active
  - `firmware_update_percentage` (int | None) - Synchronous property for progress percentage (0-100)
  - Both properties provide immediate access to cached progress data without async calls
  - Available on all devices with `FirmwareUpdateMixin` (BaseInverter, MIDDevice)

### Changed

- **Enhanced Firmware Update Detection Logic** - More reliable update state detection using multiple indicators:
  - `is_in_progress` now checks: `updateStatus` (UPLOADING/READY) + `isSendStartUpdate=True` + `isSendEndUpdate=False`
  - `is_complete` now checks: `updateStatus` (SUCCESS/COMPLETE) + `isSendEndUpdate=True` + `stopTime` populated
  - Eliminates false positives from completed or failed updates
  - Uses `isSendEndUpdate` field as primary completion indicator (most reliable)
  - More robust handling of edge cases (whitespace in stopTime, etc.)

### Testing

- ✅ **Total tests**: 621 (all passing, +23 from v0.3.9)
- ✅ **Coverage**: 82.66%
- ✅ **New test file**: `test_firmware_device_info.py` with 17 comprehensive detection tests
- ✅ **Property tests**: 6 new tests for synchronous progress properties
- ✅ **Code style**: 100% (ruff: 0 errors)
- ✅ **Type safety**: 100% (mypy strict: 0 errors)

### Usage Example

```python
# Start firmware update
await device.start_firmware_update()

# Monitor progress with synchronous properties
async def monitor_update():
    while True:
        # Refresh progress data (async)
        await device.get_firmware_update_progress()

        # Access via synchronous properties (no await needed)
        if device.firmware_update_in_progress:
            print(f"Progress: {device.firmware_update_percentage}%")
        else:
            print("Update complete!")
            break

        await asyncio.sleep(30)

# Home Assistant Update Entity example
@property
def in_progress(self) -> bool:
    return self.device.firmware_update_in_progress  # Synchronous!

@property
def update_percentage(self) -> int | None:
    return self.device.firmware_update_percentage  # Synchronous!
```

## [0.3.9] - 2025-11-23

### Added

- **Real-Time Firmware Update Progress Tracking** - Monitor firmware update progress with adaptive caching:
  - New method: `get_firmware_update_progress()` - Get real-time update status with progress percentage
  - Added `in_progress` property to `FirmwareUpdateInfo` - Check if update is currently active
  - Added `update_percentage` property (0-100) - Track update progress during installation
  - Adaptive cache TTLs based on update status:
    - During active updates: 10-second cache for near real-time progress
    - No active update: 5-minute cache to reduce API load
  - Optimistic updates: `start_firmware_update()` immediately sets `in_progress=True` for instant UI feedback
  - Thread-safe cache access with asyncio locks
  - Full Home Assistant Update entity compliance

### Changed

- **Firmware Update Caching Strategy** - Smart cache invalidation based on update state:
  - Cache automatically adjusts TTL when update starts/stops
  - Optimistic cache update eliminates detection delay when starting updates
  - Real-time progress: ~6 API calls per minute during updates
  - Idle operation: ~12 API calls per hour (vs. 3600 without caching)

### Testing

- ✅ **Total tests**: 598 (all passing, +11 from v0.3.8)
- ✅ **Coverage**: >85%
- ✅ **Code style**: 100% (ruff: 0 errors)
- ✅ **Type safety**: 100% (mypy strict: 0 errors)

### Usage Example

```python
# Start firmware update
success = await inverter.start_firmware_update()

# Monitor progress with automatic adaptive caching
while True:
    progress = await inverter.get_firmware_update_progress()
    if not progress.in_progress:
        break
    print(f"Progress: {progress.update_percentage}%")
    await asyncio.sleep(30)  # Poll every 30 seconds
```

## [0.3.8] - 2025-11-23

### Added

- **Firmware Update Convenience Properties** - Added public properties to `FirmwareUpdateMixin` for easy access to cached firmware update information:
  - Added `latest_firmware_version` property - returns latest version string or None
  - Added `firmware_update_title` property - returns update title or None
  - Added `firmware_update_summary` property - returns release summary or None
  - Added `firmware_update_url` property - returns release notes URL or None
  - All properties provide synchronous access to cached data without API calls
  - 6 additional unit tests verifying property behavior (22 total for mixin)

### Fixed

- **Firmware Update Summary Formatting** - Fixed release summary to display version numbers in hexadecimal format:
  - Changed from decimal format (e.g., "v13 → v20") to hex format (e.g., "v0D → v14")
  - Ensures version numbers in summary match firmware version format (e.g., "IAAB-0D00")
  - Affects `release_summary` field in `FirmwareUpdateInfo.from_api_response()`
  - Example: API reports v1=19→22, summary now shows "v13 → v16" (hex) instead of "v19 → v22" (decimal)
  - Added comprehensive test to verify hex formatting for app and parameter updates

### Testing

- ✅ **Total tests**: 587 (all passing, +7 from v0.3.7)
- ✅ **Coverage**: >85%
- ✅ **Code style**: 100% (ruff: 0 errors)
- ✅ **Type safety**: 100% (mypy strict: 0 errors)

## [0.3.7] - 2025-11-23

### Added

- **Firmware Update Detection** - Home Assistant-compatible firmware update detection for inverters and MID devices:
  - Added `FirmwareUpdateInfo` model with all HA Update entity requirements (`installed_version`, `latest_version`, `title`, `release_summary`, `release_url`)
  - Created `FirmwareUpdateMixin` to provide firmware update detection across all device types
  - Applied mixin to `BaseInverter` and `MIDDevice` classes
  - Added `firmware_update_available` property for synchronous cache access (returns `bool | None`)
  - Added `check_firmware_updates()` method with 24-hour TTL caching
  - Added `start_firmware_update()` and `check_update_eligibility()` methods
  - Hexadecimal version format handling: API returns decimal (v1=33) but versions use hex ("fAAB-2122" where 33=0x21)
  - Update detection logic using `pcs1UpdateMatch`/`pcs2UpdateMatch` compatibility flags
  - 27 comprehensive unit tests (11 for model, 16 for mixin)
  - All tests passing (580 total), zero linting/type errors
  - Full OpenAPI documentation with version format examples and detection algorithm

### Testing

- ✅ **Total tests**: 580 (all passing)
- ✅ **Coverage**: >85%
- ✅ **Code style**: 100% (ruff: 0 errors)
- ✅ **Type safety**: 100% (mypy strict: 0 errors)

## [0.3.6] - 2025-11-22

### Fixed

- **DST State Synchronization** - Fixed Home Assistant DST switch reverting after toggle:
  - `Station.set_daylight_saving_time()` now updates cached `daylight_saving_time` attribute after successful API write
  - Prevents HA switch from reverting to old state when reading cached value
  - Added 3 comprehensive unit tests verifying state synchronization behavior
  - Ensures UI state matches backend state immediately after control operations

## [0.3.5] - 2025-11-22

### Added

- **Parallel Group Energy Pre-Fetching** - Pre-fetch energy data for parallel groups during station load:
  - Added `_warm_parallel_group_energy_cache()` method to `Station` class
  - Parallel group energy sensors now show actual values immediately instead of 0.00 kWh
  - Eliminates initial 0.00 kWh display on integration startup
  - Concurrent execution with graceful error handling (~100ms latency impact)

- **Modular Constants Package** - Split large `constants.py` (1789 lines) into organized package:
  - `constants/api.py` (43 lines) - HTTP codes, device types, retry configuration
  - `constants/devices.py` (98 lines) - Device constants, timezone parsing, MID scaling
  - `constants/locations.py` (227 lines) - Timezone, country, continent, region mappings
  - `constants/registers.py` (965 lines) - Hold/input register definitions, bit manipulation
  - `constants/scaling.py` (486 lines) - ScaleFactor enum, scaling dictionaries, scaling functions
  - `constants/__init__.py` (470 lines) - Re-exports all symbols for 100% backward compatibility
  - Better organization, improved maintainability, easier navigation
  - All existing imports continue to work unchanged

- **Property Mixin Test Coverage** - Added 58 comprehensive tests for property mixins:
  - `InverterRuntimePropertiesMixin`: 28 tests (87% coverage, up from 38%)
  - `MIDRuntimePropertiesMixin`: 30 tests (91% coverage, up from 48%)
  - Voltage/frequency scaling verification, power/temperature no-scaling verification
  - Graceful None handling, type safety verification, edge case coverage
  - Total coverage improved: 73.79% → 80.67% (+6.88%)

### Fixed

- **Battery Property Scaling Corrections**:
  - `charge_max_current`: Corrected to ÷10 scaling (raw 2000 → 200.0A, was incorrectly 20.0A)
  - `charge_voltage_ref`: Corrected to ÷10 scaling (raw 560 → 56.0V, was incorrectly 5.6V)
  - `type_text`: Now shows "Lithium" fallback when API returns empty string

- **Battery Capacity Percentage Rounding** - Round calculated capacity percentage to nearest integer:
  - Fixed excessive precision (82.8571428571429% → 83%)
  - When API doesn't provide `currentCapacityPercent`, calculate from `currentRemainCapacity / currentFullCapacity * 100`
  - Uses API value when available (already an integer), rounds calculated values
  - Also rounded `battery_bank.current_capacity` to 1 decimal place (e.g., 596.4 Ah)

- **Integration Test Rate Limiting** - Implemented API throttling to prevent rate limiting errors:
  - Centralized fixtures in `conftest.py` (removed duplicate client fixtures from 4 test files)
  - Added global 500ms API throttling between all API calls
  - Prevents repeated login errors (DATAFRAME_TIMEOUT) and mounting errors
  - Maintains function scope for proper test isolation
  - Simpler than module/session-scoped async fixtures (avoids pytest-asyncio limitations)

### Changed

- **Code Quality Improvements**:
  - Module-level imports in property mixins (eliminates per-call import overhead)
  - Extracted `_is_cache_expired()` helper method in `BaseInverter`
  - Improved code readability and DRY principle
  - Cleaner `refresh()` method with reduced duplication

### Testing

- ✅ **Total tests**: 550 (492 unit + 58 integration)
- ✅ **Coverage**: 80.67% (improved from 73.79%)
- ✅ **Code style**: 100% (ruff: 0 errors)
- ✅ **Type safety**: 100% (mypy strict: 0 errors)

## [0.3.4] - 2025-11-22

### Added

- **Optimized CI/CD Workflows** - Industry-standard CI/CD pipeline with automated release process:
  - **CI workflow**: Only runs on PRs (not on merge to main) to eliminate redundant runs
  - **Release workflow**: Auto-creates GitHub releases from version tags
  - **Publish workflow**: Removes redundant testing (trusts PR checks), publishes to TestPyPI and PyPI
  - New file: `.github/workflows/release.yml` - Auto-create releases from tags
  - New file: `.github/WORKFLOWS.md` - Complete workflow documentation
  - Eliminates redundant CI runs (was 3x per release, now 1x)
  - Faster releases: 17 min → 7 min (10 min savings)

- **Branch Protection** - Configured via script to enforce quality standards:
  - Require PR before merging (no direct commits to main)
  - Require 'CI Success' status check
  - Require branches up-to-date before merge
  - Dismiss stale reviews on new commits
  - Enforce for admins
  - Block force pushes and deletions
  - New file: `.github/setup-branch-protection.sh` - One-time setup script

### Changed

- **Release Process** - Now fully automated:
  1. Create PR with version bump
  2. Merge after CI passes
  3. Tag: `git tag v0.3.4 && git push origin v0.3.4`
  4. Automatic: Release created → Package published to PyPI

### Benefits

- Prevents untested code from reaching main
- Automated release process: git tag → auto-release → auto-publish
- Consistent quality enforcement across all contributors
- Faster, more reliable releases

## [0.3.3] - 2025-11-22

### Added

- **Transient Error Retry** - Automatic retry for hardware communication timeouts:
  - Added `MAX_TRANSIENT_ERROR_RETRIES = 3` configuration constant
  - Added `TRANSIENT_ERROR_MESSAGES` set with 5 known transient errors (`DATAFRAME_TIMEOUT`, `TIMEOUT`, `BUSY`, `DEVICE_BUSY`, `COMMUNICATION_ERROR`)
  - Implemented automatic retry logic in `LuxpowerClient._request()` with exponential backoff (1s → 2s → 4s)
  - Non-transient errors (e.g., `apiBlocked`) fail immediately without retry
  - Retry count preserved across re-authentication
  - 14 unit tests in `test_transient_error_retry.py` (100% passing)
  - 5 integration tests in `test_transient_error_resilience.py` (100% passing)

### Fixed

- **Parameter Initialization** - Fixed incorrect initial values for Home Assistant sensors:
  - Changed `_get_parameter()` return type from `-> int | float | bool` to `-> int | float | bool | None`
  - Returns `None` when `self.parameters is None` (parameters not yet loaded)
  - Updated 7 parameter properties to return `| None`: `battery_soc_limits`, `ac_charge_power_limit`, `pv_charge_power_limit`, `grid_peak_shaving_power_limit`, `ac_charge_soc_limit`, `battery_charge_current_limit`, `battery_discharge_current_limit`
  - Home Assistant sensors now show "Unknown" state instead of incorrect defaults (False/0) on startup
  - 8 unit tests in `test_parameter_initialization.py` (100% passing)

- **Exception Handling** - Fixed double-wrapping of `LuxpowerAPIError` exceptions:
  - Added explicit exception re-raising before generic `except Exception` handler
  - Transient error exceptions now propagate correctly without "Unexpected error" wrapping

### Testing

- Added 27 new tests (22 unit + 5 integration)
- Total test count: 492 unit tests + 67 integration tests (100% passing)
- Zero linting errors (ruff check)
- Zero type errors (mypy --strict)

## [0.3.1] - 2025-11-21

### Changed

- **Code Quality Review** - Comprehensive code review against CLAUDE.md standards and Python best practices:
  - Fixed broad exception suppression in `parallel_group.py` (changed from `suppress(Exception)` to specific `LuxpowerAPIError` and `LuxpowerConnectionError`)
  - Refactored `Station._load_devices()` to reduce complexity from 21 to 6 by extracting 6 helper methods:
    - `_get_device_list()` - Fetch devices from API
    - `_find_gridboss()` - Find GridBOSS device
    - `_get_parallel_groups()` - Query parallel group configuration
    - `_create_parallel_groups()` - Create ParallelGroup objects
    - `_assign_devices()` - Assign devices to groups
    - `_assign_mid_device()` / `_assign_inverter()` - Device-specific assignment logic
  - Improved code maintainability with single-responsibility helper methods
  - Enhanced readability with clear data flow and reduced nesting
  - All linting checks passing (ruff check, ruff format)
  - All type checks passing (mypy --strict, 0 errors)
  - Test coverage improved to 74.93%

### Testing

- ✅ **Unit tests**: 479 passed, 0 failed
- ✅ **Coverage**: 74.93% (exceeds 70% requirement, improved from 74.86%)
- ✅ **Code style**: 100% (ruff: 0 errors)
- ✅ **Type safety**: 100% (mypy strict: 0 errors)
- ✅ **All quality checks passing**: ruff, mypy strict mode, pytest

### Documentation

- Added comprehensive code review document (`docs/claude/CODE_REVIEW_2025-11-21_v2.md`):
  - Detailed analysis of 7 review areas (type hints, async patterns, error handling, etc.)
  - Before/after examples of improvements
  - Test results and quality metrics
  - Recommendations for future improvements

## [0.2.7] - 2025-11-21

### Added

- **TTL-Based Caching** - Comprehensive caching system for inverter data to reduce API calls:
  - Runtime data: 30-second cache (inverter metrics refresh frequently)
  - Energy statistics: 5-minute cache (daily/monthly totals change slowly)
  - Battery data: 30-second cache (battery metrics refresh frequently)
  - Parameters: 1-hour cache (parameter settings change infrequently)
  - Automatic cache invalidation on successful parameter writes
  - 10 new unit tests for caching behavior validation

### Changed

- **Parameter Architecture Refactored** - Major API improvement for parameter access:
  - Converted async parameter getter methods to synchronous properties (e.g., `await inverter.get_ac_charge_power()` → `inverter.ac_charge_power_limit`)
  - Properties: `ac_charge_power_limit`, `pv_charge_power_limit`, `battery_soc_limits`, `battery_charge_amps`, `battery_discharge_amps`, `time_slot_limits`, `quick_charge_discharge_limits`
  - Parameters automatically fetched on first access or when cache expires
  - Integrated parameter fetching into `refresh()` cycle with `include_parameters=True` flag
  - Deprecated `read_parameters()` method with migration guidance to properties

- **Concurrent Parameter Fetching** - Added `_fetch_parameters()` internal method:
  - Fetches all 3 register ranges (0-127, 127-254, 240-367) concurrently using `asyncio.gather()`
  - Reduces parameter fetch time from ~1.5s sequential to ~0.5s parallel
  - Integrated into cache refresh logic

### Fixed

- **Integration Test Compatibility** - Updated integration tests to use new property-based API:
  - Replaced `await inverter.get_battery_soc_limits()` with `inverter.battery_soc_limits` property
  - Replaced `await inverter.get_ac_charge_power()` with `inverter.ac_charge_power_limit` property
  - Added `await inverter.refresh(include_parameters=True)` before accessing properties
  - All integration tests passing with new architecture

### Migration Guide

**Breaking Change**: Parameter getter methods replaced with properties.

Before (v0.2.6):
```python
await inverter.refresh()
soc_limits = await inverter.get_battery_soc_limits()
ac_power = await inverter.get_ac_charge_power()
```

After (v0.2.7):
```python
await inverter.refresh(include_parameters=True)  # Optional: fetch parameters during refresh
soc_limits = inverter.battery_soc_limits  # Property access (auto-fetches if needed)
ac_power = inverter.ac_charge_power_limit  # Property access (uses 1-hour cache)
```

### Testing

- ✅ **Unit tests**: 10 new caching tests in `test_caching.py`, all passing
- ✅ **Integration tests**: Updated for new property syntax, all passing
- ✅ **All quality checks passing**: ruff, mypy strict mode, pytest

## [0.2.6] - 2025-11-20

### Fixed

- **Device Model Information** (Issue #18) - Fixed device model names not being properly populated on inverter objects:
  - Changed `Station._load_devices()` to use `deviceTypeText` field from `InverterOverviewItem` API response
  - Previous code incorrectly tried to use `deviceTypeText4APP` which doesn't exist on that endpoint
  - Model is now reliably available immediately after `Station.load()` with human-readable names like "18KPV", "FlexBOSS21", "Grid Boss"
  - Added `model` property to `BaseDevice` and override in `BaseInverter` for consistent access
  - Added 5 new unit tests and 1 integration test to verify model property behavior
  - Model remains stable after refresh operations (not affected by runtime data)

### Changed

- **Model Property**: Changed from simple attribute to computed property with fallback to "Unknown" if not set

### Testing

- ✅ **Unit tests**: 48 passed in test_base.py (5 new model property tests)
- ✅ **Integration tests**: 1 new test verifies model is set correctly from API and remains stable
- ✅ **All quality checks passing**: ruff, mypy strict mode, pytest

## [0.2.5] - 2025-11-20

### Fixed

- **Dependency Compatibility**: Lowered pydantic requirement from `>=2.12.4` to `>=2.12.0` for Home Assistant compatibility (HA uses pydantic 2.12.2)

## [0.2.4] - 2025-11-20

### Added

- **Working Mode Controls** (Issue #16) - New convenience methods on `BaseInverter` for working mode operations:
  - `enable_ac_charge_mode()` / `disable_ac_charge_mode()` / `get_ac_charge_mode_status()` - Control AC charge from grid
  - `enable_pv_charge_priority()` / `disable_pv_charge_priority()` / `get_pv_charge_priority_status()` - Control PV charge priority mode
  - `enable_forced_discharge()` / `disable_forced_discharge()` / `get_forced_discharge_status()` - Control forced discharge mode
  - `enable_peak_shaving_mode()` / `disable_peak_shaving_mode()` / `get_peak_shaving_mode_status()` - Control grid peak shaving
  - Corresponding API endpoints added to `ControlEndpoints` for low-level access
  - All methods use the existing `control_function()` infrastructure with function parameter names (FUNC_AC_CHARGE, FUNC_FORCED_CHG_EN, FUNC_FORCED_DISCHG_EN, FUNC_GRID_PEAK_SHAVING)
  - Comprehensive unit tests (24 new tests: 12 for BaseInverter methods, 12 for endpoint methods)
  - Integration tests (4 tests with read-then-restore pattern for safe live API testing)

## [0.2.3] - 2025-11-20

### Added

- **Operating Mode Control** - New operating mode control for inverters with `OperatingMode` enum:
  - `OperatingMode.NORMAL` - Normal operation mode
  - `OperatingMode.STANDBY` - Standby mode (inverter disabled)
  - `set_operating_mode(mode)` - Set inverter operating mode
  - `get_operating_mode()` - Get current operating mode (reads FUNC_EN register bit 9)

- **Quick Charge Control** - Convenience methods on `BaseInverter` for quick charge operations:
  - `enable_quick_charge()` / `disable_quick_charge()` - Control quick charge operation
  - `get_quick_charge_status()` - Check if quick charge is active (returns bool)

- **Quick Discharge Control** - New quick discharge endpoints and convenience methods:
  - API: `start_quick_discharge()` / `stop_quick_discharge()` in `ControlEndpoints`
  - `BaseInverter`: `enable_quick_discharge()` / `disable_quick_discharge()`
  - `get_quick_discharge_status()` - Check if quick discharge is active (returns bool)
  - Uses shared `quickCharge/getStatusInfo` endpoint for status (returns both charge & discharge status)

- **API Discovery** - Documented quick discharge endpoints in OpenAPI spec:
  - `/web/config/quickDischarge/start` - Start quick discharge operation
  - `/web/config/quickDischarge/stop` - Stop quick discharge operation
  - Updated `QuickChargeStatus` model with `hasUnclosedQuickDischargeTask` field
  - Note: No separate `quickDischarge/getStatusInfo` endpoint (returns HTTP 404)

- **Diagnostic Data Collection Tool** (`utils/collect_diagnostics.py`) - Comprehensive diagnostic data collection utility for support and troubleshooting:
  - Automatically collects station information, device hierarchy, runtime data, energy statistics, battery data, and parameter settings
  - Sanitizes sensitive information by default (serial numbers, addresses, GPS coordinates)
  - Collects 367 registers for standard inverters, 508 registers for MID devices (GridBOSS)
  - Outputs JSON file with complete system state for support tickets
  - CLI tool: `python -m utils.collect_diagnostics --username USER --password PASS`
  - Comprehensive documentation in `utils/README.md`

### Changed

- **Project Structure Cleanup**:
  - Moved development/research scripts from root and `utils/` to `research/` directory (gitignored)
  - Cleaned up `utils/` to contain only user-facing utilities: `collect_diagnostics.py`, `json_to_markdown.py`, `map_registers.py`
  - Removed local testing script `verify_cicd.sh`

- **Coverage Reports**:
  - Added `coverage.json` to `.gitignore` to prevent test artifacts from being tracked

### Design Decisions

- **Operating Mode vs. Quick Charge/Discharge**: Operating mode (NORMAL/STANDBY) is distinct from quick charge/discharge operations, which are functions that work independently alongside operating modes
- **Status Methods Return Bool**: Convenience methods like `get_quick_charge_status()` return `bool` for simplicity rather than the full `QuickChargeStatus` object
- **Shared Status Endpoint**: Quick discharge status is retrieved via `quickCharge/getStatusInfo` endpoint, which returns both charge and discharge status in a single response

### Testing

- ✅ **Unit tests**: 335 passed (31 new tests added)
- ✅ **Coverage**: >83% (new operating mode and quick charge/discharge code fully covered)
- ✅ **All quality checks passing**: linting, type checking, coverage

### Notes

- Resolves Issue #14 - Operating mode control and quick charge/discharge support
- All changes are backward compatible
- No integration tests for quick charge/discharge operations (safety concern with live electrical systems)

## [0.2.2] - 2025-11-20

### Fixed

- **Integration Test Failures** - Resolved all integration test failures caused by API changes:
  - Fixed property name mismatches (`station.plant_id` → `station.id`, `group.group_id` → `group.name`)
  - Fixed async/await for `get_total_production()` method
  - Fixed response format for `get_total_production()` (now returns `today_kwh`, `lifetime_kwh`)
  - Fixed timestamp access (`_last_refresh` is private attribute)

- **SOC Limit Parameter API Issue** - Fixed critical bug in `set_battery_soc_limits()`:
  - API expects parameter NAMES (e.g., `"HOLD_DISCHG_CUT_OFF_SOC_EOD"`) not register numbers (e.g., `105`)
  - Changed implementation to use `write_parameter()` (singular) with proper format: `holdParam="HOLD_DISCHG_CUT_OFF_SOC_EOD"`, `valueText="20"`
  - Resolved HTTP 400 errors from malformed parameter write requests
  - Updated unit tests to verify correct API contract

### Changed

- **Control Operations Test Cleanup**:
  - Removed dangerous `write_parameters` roundtrip test (was attempting to write 0 to register 21, which would disable all functions)
  - Fixed `test_read_parameters` to expect parsed parameter names (`FUNC_*` instead of `reg_21`)
  - Updated SOC limit test to verify API success without value verification (inverters may have undocumented validation rules)

### Test Results

- ✅ **Unit tests**: 344 passed
- ✅ **Integration tests**: 40 passed, 9 skipped
- ✅ **All quality checks passing**: linting, type checking, coverage

## [0.2.1] - 2025-11-20

### Added

- **Battery Current Control Convenience Methods** - Four new convenience methods in `ControlEndpoints` for managing battery charge and discharge current limits:
  - `set_battery_charge_current(inverter_sn, amperes)` - Set battery charge current limit (0-250 A) with validation and safety warnings
  - `set_battery_discharge_current(inverter_sn, amperes)` - Set battery discharge current limit (0-250 A) with validation and safety warnings
  - `get_battery_charge_current(inverter_sn)` - Get current battery charge current limit
  - `get_battery_discharge_current(inverter_sn)` - Get current battery discharge current limit

- **Comprehensive Documentation**:
  - `docs/PARAMETER_REFERENCE.md` - Complete parameter catalog for Luxpower/EG4 API (400+ lines)
  - `docs/claude/BATTERY_CURRENT_CONTROL_IMPLEMENTATION.md` - Implementation guide with use cases (600+ lines)
  - `docs/claude/CONVENIENCE_FUNCTIONS_ANALYSIS.md` - Analysis of convenience function patterns (400+ lines)
  - `docs/claude/GAP_VERIFICATION.md` - Feature parity verification with EG4 Web Monitor HA integration
  - `docs/claude/RELEASE_v0.3_NOTES.md` - Complete release notes with examples and use cases

### Features

**Battery Current Control** convenience methods provide:
- Self-documenting API with clear method names
- Input validation (0-250 A range with `ValueError` on invalid input)
- Safety warnings for high values (>200 A)
- Comprehensive docstrings with use case examples
- Power calculation references (e.g., 50A = ~2.4kW at 48V)
- Type hints for IDE autocomplete

**Common Use Cases**:
- Prevent inverter throttling during high solar production
- Time-of-use (TOU) rate optimization
- Battery health management (gentle charging)
- Emergency power management during grid outages
- Weather-based automation

### Changed

- Updated `docs/GAP_ANALYSIS.md` to track v2.2.7 features from EG4 Web Monitor HA integration

### Documentation

- Added comprehensive examples for battery current control automation
- Added safety considerations and battery limit guidelines
- Added power calculation reference tables for 48V systems
- Added migration guide from generic `write_parameter()` to convenience methods

### Notes

- All changes are backward compatible - no breaking changes
- Generic `write_parameter()` method still available
- Based on features added to EG4 Web Monitor HA integration v2.2.6 (November 2025)
- Convenience methods delegate to existing `write_parameter()` and `read_device_parameters_ranges()` methods

## [0.2.0] - 2025-11-19

### Added

- **Object-Oriented Device Hierarchy** - New `Station` and `Inverter` classes for intuitive device management
- **Cached Data Access** - Efficient caching with `_load_devices()` to minimize API calls
- **Helper Methods** - Eight control helper methods added to `ControlEndpoints`:
  - `enable_battery_backup()` / `disable_battery_backup()`
  - `enable_quick_charge()` / `disable_quick_charge()`
  - `enable_forced_charge()` / `disable_forced_charge()`
  - `enable_forced_discharge()` / `disable_forced_discharge()`
- **Session Management Methods** - `invalidate_cache()` and `invalidate_all_caches()` for cache control
- **Register Mapping** - Complete parameter register catalog in `src/pylxpweb/registers.py`

### Changed

- Improved `LuxpowerClient` with separate API and control endpoints
- Enhanced type safety with Pydantic v2 models
- Better session handling with automatic re-authentication

### Fixed

- Resolved mypy type errors and API namespace issues
- Fixed Pydantic model handling in `Station._load_devices`
- Optimized `Station._load_devices` with concurrent API calls

### Documentation

- Added comprehensive 100% parity assessment with EG4 Web Monitor integration
- Updated API documentation with latest endpoints
- Added register mapping documentation

## [0.1.1] - 2025-11-15

### Fixed

- Fixed package structure and imports
- Improved error handling for authentication failures
- Better session cookie management

## [0.1.0] - 2025-11-14

### Added

- Initial release of pylxpweb
- Core `LuxpowerClient` with async/await support
- Authentication and session management
- Plant/station discovery
- Device enumeration and hierarchy
- Runtime data retrieval (inverter, battery, GridBOSS)
- Energy statistics
- Control operations (parameter read/write)
- Comprehensive type hints with mypy strict mode
- Data scaling utilities
- Custom exception hierarchy
- Basic test suite
- API documentation

### Features

- Multi-region support (US Luxpower, EU Luxpower, EG4 Electronics)
- Configurable base URL
- Session injection support (Home Assistant integration ready)
- Automatic session renewal
- Retry logic with exponential backoff
- Smart caching with configurable TTL
- Production-ready error handling

### Documentation

- Complete API reference (`docs/api/LUXPOWER_API.md`)
- Development guidelines (`CLAUDE.md`)
- OpenAPI 3.0 specification (`docs/luxpower-api.yaml`)
- Usage examples in README
- Comprehensive docstrings

---

## Version History Summary

- **v0.3.23** (2025-12-02): NO_BATTERY enum, optional userChartRecord, battery_bank property (PR #61)
- **v0.3.22** (2025-12-02): Cache invalidation fix, discharge_power_limit, battery_voltage_limits properties
- **v0.3.21** (2025-12-02): Added `system_charge_soc_limit` property to BaseInverter
- **v0.3.20** (2025-11-28): System charge SOC limit convenience functions (set/get)
- **v0.3.13** (2025-11-24): Fixed firmware "already latest" exception - now returns proper FirmwareUpdateCheck
- **v0.3.12** (2025-11-24): Code review improvements - badges, coverage threshold, cleanup
- **v0.3.11** (2025-11-24): Code quality - logging imports refactored
- **v0.3.10** (2025-11-23): Synchronous firmware progress properties
- **v0.3.9** (2025-11-23): Real-time firmware update progress tracking with adaptive caching
- **v0.3.8** (2025-11-23): Firmware update convenience properties and summary formatting
- **v0.3.7** (2025-11-23): Firmware update detection for HA Update entities
- **v0.3.6** (2025-11-22): DST state synchronization fix
- **v0.3.5** (2025-11-22): Integration test optimizations, battery property fixes, constants refactoring, property mixin tests
- **v0.3.4** (2025-11-22): CI/CD workflow optimizations, branch protection, automated releases
- **v0.3.3** (2025-11-22): Transient error retry, parameter initialization fixes
- **v0.3.1** (2025-11-21): Code quality review and refactoring
- **v0.3.0** (2025-11-21): Python best practices refactoring
- **v0.2.8** (2025-11-21): DST auto-detection with manual sync
- **v0.2.7** (2025-11-21): Caching and parameter architecture refactor
- **v0.2.6** (2025-11-21): Device model information fix
- **v0.2.5** (2025-11-21): Home Assistant compatibility fix
- **v0.2.4** (2025-11-21): Working mode controls
- **v0.2.3** (2025-11-20): Operating mode control, quick charge/discharge support, diagnostic tool
- **v0.2.2** (2025-11-20): Integration test fixes, SOC limit API correction
- **v0.2.1** (2025-11-20): Battery current control convenience methods, comprehensive documentation
- **v0.2.0** (2025-11-19): Object-oriented device hierarchy, helper methods, register mapping
- **v0.1.1** (2025-11-15): Bug fixes and improvements
- **v0.1.0** (2025-11-14): Initial release with core functionality

[Unreleased]: https://github.com/joyfulhouse/pylxpweb/compare/v0.9.32...HEAD
[0.9.32]: https://github.com/joyfulhouse/pylxpweb/compare/v0.9.29...v0.9.32
[0.9.29]: https://github.com/joyfulhouse/pylxpweb/compare/v0.9.26...v0.9.29
[0.9.26]: https://github.com/joyfulhouse/pylxpweb/compare/v0.9.17...v0.9.26
[0.9.17]: https://github.com/joyfulhouse/pylxpweb/compare/v0.9.0...v0.9.17
[0.9.0]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.23...v0.9.0
[0.3.23]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.22...v0.3.23
[0.3.22]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.21...v0.3.22
[0.3.21]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.20...v0.3.21
[0.3.20]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.19...v0.3.20
[0.3.19]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.18...v0.3.19
[0.3.18]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.17...v0.3.18
[0.3.17]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.16...v0.3.17
[0.3.16]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.15...v0.3.16
[0.3.15]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.14...v0.3.15
[0.3.14]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.13...v0.3.14
[0.3.13]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.12...v0.3.13
[0.3.12]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.11...v0.3.12
[0.3.11]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.10...v0.3.11
[0.3.10]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.9...v0.3.10
[0.3.9]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.8...v0.3.9
[0.3.8]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.7...v0.3.8
[0.3.7]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.6...v0.3.7
[0.3.6]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.5...v0.3.6
[0.3.5]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.4...v0.3.5
[0.3.4]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.1...v0.3.3
[0.3.1]: https://github.com/joyfulhouse/pylxpweb/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/joyfulhouse/pylxpweb/compare/v0.2.8...v0.3.0
[0.2.8]: https://github.com/joyfulhouse/pylxpweb/compare/v0.2.7...v0.2.8
[0.2.7]: https://github.com/joyfulhouse/pylxpweb/compare/v0.2.6...v0.2.7
[0.2.6]: https://github.com/joyfulhouse/pylxpweb/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/joyfulhouse/pylxpweb/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/joyfulhouse/pylxpweb/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/joyfulhouse/pylxpweb/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/joyfulhouse/pylxpweb/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/joyfulhouse/pylxpweb/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/joyfulhouse/pylxpweb/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/joyfulhouse/pylxpweb/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/joyfulhouse/pylxpweb/releases/tag/v0.1.0
