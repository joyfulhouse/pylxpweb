"""Register-derived contract-validation harness.

The canonical register tables in ``pylxpweb.registers`` are the single source
of truth for the cloud↔modbus data contract.  These tests assert that the rest
of the library stays faithful to them, so drift fails per-commit instead of
shipping as a silent regression (the failure mode behind issues #91, #172 and
the PV4-6 string-count gaps).

Three contracts are enforced:

1. **Scale parity** — for every register with a ``cloud_api_field`` whose cloud
   path is data-driven (inverter input + battery), the modbus scale equals the
   cloud scale, so identical raw units decode to the same physical value.  A
   small allow-list covers fields whose cloud/modbus *raw units legitimately
   differ* (e.g. ``maxChgCurr``); each allow-list entry carries a concrete
   numeric proof that both paths still recover the same physical value.  This
   is the lesson of the ``maxChgCurr`` false positive: matching scale *symbols*
   is necessary-not-sufficient — what matters is the decoded physical value.

   GridBOSS scaling is asserted by *category consistency* instead, because its
   cloud path applies hard-coded divisors (the ``GRIDBOSS_RUNTIME_SCALING`` dict
   is dead and its keys do not match real cloud fields).

2. **Field-mapping completeness** — every register in a category that
   ``from_modbus_registers`` parses has its ``canonical_name`` present as a key
   in the corresponding ``*_FIELD`` mapping.  A ``None`` value is an explicit
   acknowledgement that the register is intentionally not surfaced; a *missing*
   key is a silent drop and fails CI.  This is what catches a future PV4-6-style
   register added without a mapping.

3. **HA-sensor-key reachability** — every register that advertises an
   ``ha_sensor_key`` actually resolves end-to-end (register → field mapping →
   real dataclass attribute, or a documented special-handled path).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from pylxpweb.constants.scaling import (
    BATTERY_MODULE_SCALING,
    ENERGY_INFO_SCALING,
    INVERTER_RUNTIME_SCALING,
    ScaleFactor,
    apply_scale,
)
from pylxpweb.models import MidboxRuntime
from pylxpweb.registers.battery import BATTERY_REGISTERS
from pylxpweb.registers.gridboss import GRIDBOSS_REGISTERS, GridBossCategory
from pylxpweb.registers.inverter_input import (
    INVERTER_INPUT_REGISTERS,
    RegisterCategory,
)
from pylxpweb.transports._field_mappings import (
    BATTERY_FIELD,
    ENERGY_CATEGORIES,
    ENERGY_FIELD,
    GRIDBOSS_FIELD,
    RUNTIME_CATEGORIES,
    RUNTIME_FIELD,
)
from pylxpweb.transports.data import (
    BatteryData,
    InverterEnergyData,
    InverterRuntimeData,
    MidboxRuntimeData,
)

_SAMPLES = Path(__file__).resolve().parents[1] / "samples"

_ENERGY_CATS = {RegisterCategory.ENERGY_DAILY, RegisterCategory.ENERGY_LIFETIME}


# =========================================================================
# Allow-list: cloud_api_fields whose cloud and modbus raw units legitimately
# DIFFER.  Each entry MUST prove the two paths still decode to the same
# physical value.  Validated against the real cloud sample
# runtime_44300E0585.json and docs/api/LUXPOWER_API.md (see scaling.py).
# =========================================================================
KNOWN_RAW_UNIT_DIFFERENCES: dict[str, dict[str, float]] = {
    # Cloud reports the BMS charge-current limit in 0.01A units (÷100), modbus
    # input reg 81 reports it in 0.1A units (÷10).  6000/100 == 600/10 == 60.0A.
    "maxChgCurr": {"cloud_raw": 6000.0, "modbus_raw": 600.0, "physical": 60.0},
    "maxDischgCurr": {"cloud_raw": 6000.0, "modbus_raw": 600.0, "physical": 60.0},
}


# =========================================================================
# Allow-list: registers that advertise an ha_sensor_key but are not yet
# reachable end-to-end.  Each MUST carry a justification.  Keep this list
# SHRINKING — entries are debt, not design.
# =========================================================================
KNOWN_UNREACHABLE_HA_KEYS: dict[str, str] = {
    # (empty) — all previously-deferred registers are now wired end-to-end.
    # battery_status_inv / bms_fault_code / bms_warning_code had their
    # aspirational ha_sensor_keys dropped (eg4-mu0, eg4-5c5); pv4-6 energy
    # (epv4-6 day/all) is now fully wired with a read group + pv_string_count
    # gate + dataclass fields (eg4-478).  Keep this dict EMPTY unless a new,
    # justified debt entry is genuinely required.
}


# Runtime registers handled specially by from_modbus_registers whose value
# genuinely flows into a real dataclass field even though RUNTIME_FIELD maps
# them to None:
#   soc_soh_packed -> battery_soc/battery_soh
#   parallel_config -> parallel_master_slave/parallel_phase/parallel_number
#   fault_code     -> fault_code (real field)
#   warning_code   -> warning_code (real field)
# NOTE: bms_fault_code/bms_warning_code merge lossily into fault_code/
# warning_code (fallback when the inverter code is 0) and no longer advertise
# ha_sensor_keys, so the reachability test does not flag them (eg4-5c5).
_RUNTIME_SPECIAL_REACHABLE = {
    "soc_soh_packed",
    "parallel_config",
    "fault_code",
    "warning_code",
}

# Battery registers handled specially (packed / multi-register reads) that still
# populate a BatteryData field.
_BATTERY_SPECIAL_REACHABLE = {
    "battery_soc",
    "battery_soh",
    "battery_firmware_version",
    "battery_serial_number",
}


def _dataclass_fields(cls: type) -> set[str]:
    return {f.name for f in dataclasses.fields(cls)}


# =========================================================================
# 1. SCALE PARITY  (eg4-1ch.1)
# =========================================================================


def _scale_parity_offenders(regs: object, scaling_for: object) -> list[str]:
    """Compare each register's modbus scale to its cloud scale.

    Two distinct failure modes (both fail CI):
      * DRIFT — cloud field is present in the scaling dict but its factor
        differs from the register's modbus scale.
      * MASKING GAP — the register applies a real scale (≠ NONE) but its cloud
        field is ABSENT from the scaling dict, so the cloud path silently falls
        back to no-scaling (``scale_*_value`` returns ``float(value)``).  This
        would 10×/100× the cloud value relative to modbus, so absence is NOT a
        free pass — it is exactly the kind of gap this harness must catch.

    Fields in KNOWN_RAW_UNIT_DIFFERENCES are skipped (proven separately).
    """
    offenders: list[str] = []
    for reg in regs:  # type: ignore[attr-defined]
        if not reg.cloud_api_field:
            continue
        if reg.cloud_api_field in KNOWN_RAW_UNIT_DIFFERENCES:
            continue
        scaling = scaling_for(reg)  # type: ignore[operator]
        if reg.cloud_api_field not in scaling:
            if reg.scale.value != ScaleFactor.SCALE_NONE.value:
                offenders.append(
                    f"{reg.canonical_name} (cloud={reg.cloud_api_field}): modbus÷"
                    f"{reg.scale.value} but cloud field ABSENT from scaling dict "
                    f"(cloud would not scale → masking gap)"
                )
            continue
        cloud = scaling[reg.cloud_api_field].value
        if reg.scale.value != cloud:
            offenders.append(
                f"{reg.canonical_name} (cloud={reg.cloud_api_field}): "
                f"modbus÷{reg.scale.value} vs cloud÷{cloud}"
            )
    return offenders


def test_inverter_cloud_modbus_scale_parity() -> None:
    """Every inverter-input register's cloud scale == modbus scale.

    Exceptions are only those in KNOWN_RAW_UNIT_DIFFERENCES (proven separately).
    A new drift OR a masking gap between scaling.py and the register table fails
    here.
    """
    offenders = _scale_parity_offenders(
        INVERTER_INPUT_REGISTERS,
        lambda reg: (
            ENERGY_INFO_SCALING if reg.category in _ENERGY_CATS else INVERTER_RUNTIME_SCALING
        ),
    )
    assert not offenders, "Cloud/modbus scale drift:\n  " + "\n  ".join(offenders)


def test_battery_cloud_modbus_scale_parity() -> None:
    """Every battery register's cloud scale == modbus scale (the #172 guard)."""
    offenders = _scale_parity_offenders(BATTERY_REGISTERS, lambda reg: BATTERY_MODULE_SCALING)
    assert not offenders, "Battery cloud/modbus scale drift:\n  " + "\n  ".join(offenders)


def test_battery_cell_number_offsets_not_crossed() -> None:
    """Cell-number registers: offset 14 = TEMP numbers, offset 15 = VOLTAGE numbers.

    Pins the eg4-4yg fix.  Proven by live cross-mode capture (2026-02-26):
    cloud batMaxCellNumTemp/batMaxCellNumVolt vs local registers of the same
    batteries showed the original map (14=voltage, 15=temp) was crossed.
    Byte packing (low byte = max, high byte = min) was and remains correct.
    """
    by_name = {r.canonical_name: r for r in BATTERY_REGISTERS}

    assert by_name["battery_max_cell_num_temp"].offset == 14
    assert by_name["battery_min_cell_num_temp"].offset == 14
    assert by_name["battery_max_cell_num_voltage"].offset == 15
    assert by_name["battery_min_cell_num_voltage"].offset == 15

    for max_name, min_name in (
        ("battery_max_cell_num_temp", "battery_min_cell_num_temp"),
        ("battery_max_cell_num_voltage", "battery_min_cell_num_voltage"),
    ):
        assert by_name[max_name].packed == "low_byte"
        assert by_name[min_name].packed == "high_byte"


def test_known_raw_unit_differences_yield_same_physical_value() -> None:
    """Each allow-listed field proves cloud_raw and modbus_raw decode equal.

    This is the maxChgCurr lesson made executable: the scales DIFFER on purpose,
    but the decoded physical value MUST match.  If someone collapses the scales
    so they agree, the difference-assertion below forces removal of the entry.
    """
    # Resolve each allow-listed cloud field to its register + both scales.
    runtime_by_cloud = {r.cloud_api_field: r for r in INVERTER_INPUT_REGISTERS if r.cloud_api_field}
    for cloud_field, proof in KNOWN_RAW_UNIT_DIFFERENCES.items():
        reg = runtime_by_cloud.get(cloud_field)
        assert reg is not None, f"{cloud_field} no longer maps to a register"
        cloud_scale = INVERTER_RUNTIME_SCALING.get(cloud_field, ScaleFactor.SCALE_NONE)
        modbus_scale = reg.scale
        # The scales must genuinely differ — otherwise this is not a raw-unit
        # exception and the entry should be deleted (the parity test covers it).
        assert cloud_scale.value != modbus_scale.value, (
            f"{cloud_field} cloud and modbus scales now agree "
            f"(÷{cloud_scale.value}); remove it from KNOWN_RAW_UNIT_DIFFERENCES"
        )
        cloud_physical = apply_scale(proof["cloud_raw"], cloud_scale)
        modbus_physical = apply_scale(proof["modbus_raw"], modbus_scale)
        assert cloud_physical == proof["physical"], (
            f"{cloud_field}: cloud {proof['cloud_raw']}÷{cloud_scale.value}="
            f"{cloud_physical}, expected {proof['physical']}"
        )
        assert modbus_physical == proof["physical"], (
            f"{cloud_field}: modbus {proof['modbus_raw']}÷{modbus_scale.value}="
            f"{modbus_physical}, expected {proof['physical']}"
        )


# GridBOSS modbus scale is canonical per category; the cloud path applies the
# matching hard-coded divisor in MidboxRuntimeData.from_http_response
# (voltage ÷10, current ÷10, frequency ÷100, power/smart_load ÷1, energy ÷10).
_EXPECTED_GRIDBOSS_SCALE: dict[GridBossCategory, int] = {
    GridBossCategory.VOLTAGE: 10,
    GridBossCategory.CURRENT: 10,
    GridBossCategory.POWER: 1,
    GridBossCategory.SMART_LOAD: 1,
    GridBossCategory.SMART_PORT: 1,
    GridBossCategory.FREQUENCY: 100,
    GridBossCategory.ENERGY_DAILY: 10,
    GridBossCategory.ENERGY_LIFETIME: 10,
}


def test_gridboss_scale_is_consistent_per_category() -> None:
    """Every GridBOSS register's scale matches its category's canonical scale.

    GridBOSS cloud scaling is hard-coded per quantity type, so a register whose
    modbus scale diverges from its category norm would silently disagree with
    the cloud path.  This asserts the register table cannot drift apart.
    """
    offenders: list[str] = []
    for reg in GRIDBOSS_REGISTERS:
        expected = _EXPECTED_GRIDBOSS_SCALE.get(reg.category)
        assert expected is not None, f"Unhandled GridBOSS category {reg.category}"
        if reg.scale.value != expected:
            offenders.append(
                f"{reg.canonical_name} ({reg.category.value}): "
                f"÷{reg.scale.value}, category norm ÷{expected}"
            )
    assert not offenders, "GridBOSS scale inconsistency:\n  " + "\n  ".join(offenders)


def test_gridboss_expected_scale_matches_real_http_parser() -> None:
    """Tie _EXPECTED_GRIDBOSS_SCALE to the REAL from_http_response parser.

    The category-consistency test above is only meaningful if its per-category
    constants actually equal the divisors MidboxRuntimeData.from_http_response
    applies.  This loads the real GridBOSS cloud sample, runs the actual parser,
    and asserts that for every cloud field the sample carries, the parsed
    physical value equals ``raw / _EXPECTED_GRIDBOSS_SCALE[category]`` — so a
    future change to the hard-coded ``_f_div`` divisors fails CI here.
    """
    data = json.loads((_SAMPLES / "midbox_0987654321.json").read_text())
    midbox_data = MidboxRuntime.model_validate(data).midboxData
    assert midbox_data is not None, "sample has no midboxData"
    runtime = MidboxRuntimeData.from_http_response(midbox_data)

    runtime_fields = _dataclass_fields(MidboxRuntimeData)
    checked = 0
    categories_seen: set[GridBossCategory] = set()
    scale_offenders: list[str] = []
    unpopulated: list[str] = []
    for reg in GRIDBOSS_REGISTERS:
        if not reg.cloud_api_field:
            continue
        target = GRIDBOSS_FIELD.get(reg.canonical_name)
        if target is None or target not in runtime_fields:
            continue
        raw = getattr(midbox_data, reg.cloud_api_field, None)
        if raw is None:
            continue
        physical = getattr(runtime, target)
        if physical is None:
            # Cloud field present in the sample but the GRIDBOSS_FIELD target was
            # not populated by from_http_response → the modbus-side mapping names
            # a different field than the cloud path uses (a seam mismatch).
            unpopulated.append(f"{reg.canonical_name} (cloud={reg.cloud_api_field}) -> {target}")
            continue
        div = _EXPECTED_GRIDBOSS_SCALE[reg.category]
        expected = raw / div
        if physical != pytest.approx(expected):
            scale_offenders.append(
                f"{reg.canonical_name} (cloud={reg.cloud_api_field}, {reg.category.value}): "
                f"parser={physical} but raw {raw} ÷{div}={expected}"
            )
        checked += 1
        categories_seen.add(reg.category)

    assert not scale_offenders, (
        "from_http_response divisor disagrees with _EXPECTED_GRIDBOSS_SCALE:\n  "
        + "\n  ".join(scale_offenders)
    )
    assert not unpopulated, (
        "GRIDBOSS_FIELD names a field the cloud parser does not populate:\n  "
        + "\n  ".join(unpopulated)
    )
    # Guard against a vacuous pass: the sample must exercise multiple categories.
    assert checked >= 10, f"only {checked} GridBOSS fields verified against parser"
    assert {
        GridBossCategory.VOLTAGE,
        GridBossCategory.CURRENT,
        GridBossCategory.FREQUENCY,
    } <= categories_seen, f"sample did not cover key categories: {categories_seen}"


# =========================================================================
# 2. FIELD-MAPPING COMPLETENESS  (eg4-1ch.2)
# =========================================================================


def test_runtime_field_mapping_completeness() -> None:
    """Every runtime-category register has a RUNTIME_FIELD key (None ok)."""
    missing = [
        r.canonical_name
        for r in INVERTER_INPUT_REGISTERS
        if r.category.value in RUNTIME_CATEGORIES and r.canonical_name not in RUNTIME_FIELD
    ]
    assert not missing, (
        "Runtime registers parsed by from_modbus_registers but absent from "
        "RUNTIME_FIELD (silent drop):\n  " + "\n  ".join(missing)
    )


def test_energy_field_mapping_completeness() -> None:
    """Every energy-category register has an ENERGY_FIELD key (None ok)."""
    missing = [
        r.canonical_name
        for r in INVERTER_INPUT_REGISTERS
        if r.category.value in ENERGY_CATEGORIES and r.canonical_name not in ENERGY_FIELD
    ]
    assert not missing, (
        "Energy registers parsed by from_modbus_registers but absent from "
        "ENERGY_FIELD (silent drop):\n  " + "\n  ".join(missing)
    )


def test_battery_field_mapping_completeness() -> None:
    """Every battery register has a BATTERY_FIELD key (None ok)."""
    missing = [r.canonical_name for r in BATTERY_REGISTERS if r.canonical_name not in BATTERY_FIELD]
    assert not missing, (
        "Battery registers absent from BATTERY_FIELD (silent drop):\n  " + "\n  ".join(missing)
    )


def test_gridboss_field_mapping_completeness() -> None:
    """Every GridBOSS register has a GRIDBOSS_FIELD key (None ok)."""
    missing = [
        r.canonical_name for r in GRIDBOSS_REGISTERS if r.canonical_name not in GRIDBOSS_FIELD
    ]
    assert not missing, (
        "GridBOSS registers absent from GRIDBOSS_FIELD (silent drop):\n  " + "\n  ".join(missing)
    )


def test_field_mappings_point_to_real_dataclass_fields() -> None:
    """Non-None FIELD-dict values name an attribute that exists on the dataclass."""
    checks = (
        ("RUNTIME_FIELD", RUNTIME_FIELD, _dataclass_fields(InverterRuntimeData)),
        ("ENERGY_FIELD", ENERGY_FIELD, _dataclass_fields(InverterEnergyData)),
        ("BATTERY_FIELD", BATTERY_FIELD, _dataclass_fields(BatteryData)),
        ("GRIDBOSS_FIELD", GRIDBOSS_FIELD, _dataclass_fields(MidboxRuntimeData)),
    )
    offenders: list[str] = []
    for name, mapping, fields in checks:
        for canonical, target in mapping.items():
            if target is not None and target not in fields:
                offenders.append(f"{name}[{canonical}] -> {target} (no such dataclass field)")
    assert not offenders, "Field mappings point to missing dataclass fields:\n  " + "\n  ".join(
        offenders
    )


# =========================================================================
# 3. HA-SENSOR-KEY REACHABILITY  (eg4-1ch.3)
# =========================================================================


def _reachability_offenders(
    regs: object,
    mapping: dict[str, str | None],
    fields: set[str],
    special_reachable: set[str],
) -> list[str]:
    offenders: list[str] = []
    for reg in regs:  # type: ignore[attr-defined]
        if not reg.ha_sensor_key:
            continue
        if reg.canonical_name in KNOWN_UNREACHABLE_HA_KEYS:
            continue
        if reg.canonical_name in special_reachable:
            continue
        target = mapping.get(reg.canonical_name, "__MISSING__")
        if target == "__MISSING__":
            offenders.append(f"{reg.canonical_name} (ha={reg.ha_sensor_key}): no mapping key")
        elif target is None:
            offenders.append(
                f"{reg.canonical_name} (ha={reg.ha_sensor_key}): mapping is None, not reachable"
            )
        elif target not in fields:
            offenders.append(
                f"{reg.canonical_name} (ha={reg.ha_sensor_key}): -> {target} (no dataclass field)"
            )
    return offenders


def test_runtime_ha_sensor_keys_reachable() -> None:
    regs = [r for r in INVERTER_INPUT_REGISTERS if r.category.value in RUNTIME_CATEGORIES]
    offenders = _reachability_offenders(
        regs, RUNTIME_FIELD, _dataclass_fields(InverterRuntimeData), _RUNTIME_SPECIAL_REACHABLE
    )
    assert not offenders, "Runtime ha_sensor_keys not reachable:\n  " + "\n  ".join(offenders)


def test_energy_ha_sensor_keys_reachable() -> None:
    regs = [r for r in INVERTER_INPUT_REGISTERS if r.category.value in ENERGY_CATEGORIES]
    offenders = _reachability_offenders(
        regs, ENERGY_FIELD, _dataclass_fields(InverterEnergyData), set()
    )
    assert not offenders, "Energy ha_sensor_keys not reachable:\n  " + "\n  ".join(offenders)


def test_battery_ha_sensor_keys_reachable() -> None:
    offenders = _reachability_offenders(
        BATTERY_REGISTERS, BATTERY_FIELD, _dataclass_fields(BatteryData), _BATTERY_SPECIAL_REACHABLE
    )
    assert not offenders, "Battery ha_sensor_keys not reachable:\n  " + "\n  ".join(offenders)


def test_gridboss_ha_sensor_keys_reachable() -> None:
    offenders = _reachability_offenders(
        GRIDBOSS_REGISTERS, GRIDBOSS_FIELD, _dataclass_fields(MidboxRuntimeData), set()
    )
    assert not offenders, "GridBOSS ha_sensor_keys not reachable:\n  " + "\n  ".join(offenders)


def test_known_unreachable_keys_are_actually_unreachable() -> None:
    """Keep the debt list honest: each KNOWN_UNREACHABLE entry must still be a
    real register with an ha_sensor_key that maps to None/MISSING.  Once wired,
    the entry must be removed."""
    by_name = {r.canonical_name: r for r in INVERTER_INPUT_REGISTERS}
    by_name.update({r.canonical_name: r for r in BATTERY_REGISTERS})
    by_name.update({r.canonical_name: r for r in GRIDBOSS_REGISTERS})
    all_maps: dict[str, str | None] = {
        **RUNTIME_FIELD,
        **ENERGY_FIELD,
        **BATTERY_FIELD,
        **GRIDBOSS_FIELD,
    }
    for canonical in KNOWN_UNREACHABLE_HA_KEYS:
        reg = by_name.get(canonical)
        assert reg is not None, f"{canonical} no longer exists; drop it"
        assert reg.ha_sensor_key, f"{canonical} no longer has an ha_sensor_key; drop it"
        assert all_maps.get(canonical) is None, (
            f"{canonical} is now mapped/reachable; remove it from KNOWN_UNREACHABLE_HA_KEYS"
        )
