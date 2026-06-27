"""Unit tests for the grid peak shaving register family (eg4-gfu5).

The family was located 2026-06-12 by READ-ONLY single-register cloud window
reads on an 18kPV and a FlexBOSS21 (both devices agree):

    206 = _12K_HOLD_GRID_PEAK_SHAVING_POWER   (PS1)
    207 = _12K_HOLD_GRID_PEAK_SHAVING_SOC     (%, raw 1:1)
    208 = _12K_HOLD_GRID_PEAK_SHAVING_VOLT    (decivolts)
    218 = _12K_HOLD_GRID_PEAK_SHAVING_SOC_2   (%, raw 1:1)
    219 = _12K_HOLD_GRID_PEAK_SHAVING_VOLT_2  (decivolts)
    232 = _12K_HOLD_GRID_PEAK_SHAVING_POWER_2 (PS2)

Register 231 (the old, WRONG PS1 mapping) returns zero named parameters on
both inverters and must stay unmapped until identified.  The power members'
raw encodings are unverified (live setpoints were 0), so none of the family
may appear in REGISTER_TO_PARAM_KEYS yet — the local parameter refresh would
surface raw values as engineering units, and local name-writes would write
unscaled values.
"""

from __future__ import annotations

from unittest.mock import Mock

from pylxpweb.client import LuxpowerClient
from pylxpweb.constants.registers import (
    PARAM_KEY_TO_REGISTER,
    REGISTER_TO_PARAM_KEYS,
    get_param_to_register_mapping,
)
from pylxpweb.devices.inverters.base import BaseInverter
from pylxpweb.devices.models import Entity
from pylxpweb.registers.inverter_holding import (
    BY_ADDRESS,
    BY_NAME,
    HoldingCategory,
    ScaleFactor,
)

PEAK_SHAVING_FAMILY: dict[str, tuple[int, str]] = {
    "grid_peak_shaving_power": (206, "_12K_HOLD_GRID_PEAK_SHAVING_POWER"),
    "grid_peak_shaving_soc": (207, "_12K_HOLD_GRID_PEAK_SHAVING_SOC"),
    "grid_peak_shaving_volt": (208, "_12K_HOLD_GRID_PEAK_SHAVING_VOLT"),
    "grid_peak_shaving_soc_2": (218, "_12K_HOLD_GRID_PEAK_SHAVING_SOC_2"),
    "grid_peak_shaving_volt_2": (219, "_12K_HOLD_GRID_PEAK_SHAVING_VOLT_2"),
    "grid_peak_shaving_power_2": (232, "_12K_HOLD_GRID_PEAK_SHAVING_POWER_2"),
}


class TestPeakShavingCanonicalRows:
    """Canonical table rows match the 2026-06-12 sweep evidence."""

    def test_family_addresses_and_api_keys(self) -> None:
        for canonical, (address, api_key) in PEAK_SHAVING_FAMILY.items():
            reg = BY_NAME[canonical]
            assert reg.address == address, (
                f"{canonical}: canonical table says reg {reg.address}, "
                f"sweep evidence says reg {address}"
            )
            assert reg.api_param_key == api_key
            assert reg.bit_position is None  # value registers, not bitfields
            assert reg.category == HoldingCategory.GRID

    def test_ps1_is_not_at_231(self) -> None:
        """The old 231 mapping was disproved: (231,1) names nothing on either
        inverter while (206,1) names PS1 on both."""
        reg = BY_NAME["grid_peak_shaving_power"]
        assert reg.address == 206
        assert reg.address != 231

    def test_ps1_is_single_register_not_32_bit(self) -> None:
        """(232,1) names PS2 — register 232 is NOT a PS1 high word."""
        reg = BY_NAME["grid_peak_shaving_power"]
        assert reg.bit_width == 16

    def test_power_members_use_cloud_kw_range(self) -> None:
        for canonical in ("grid_peak_shaving_power", "grid_peak_shaving_power_2"):
            reg = BY_NAME[canonical]
            assert reg.unit == "kW"
            assert reg.min_value == 0
            assert reg.max_value == 25.5

    def test_volt_members_are_decivolt_scaled(self) -> None:
        """Raw-vs-named cross-check in the sweep responses: raw 520 -> '52' V
        on both devices, for both time periods."""
        for canonical in ("grid_peak_shaving_volt", "grid_peak_shaving_volt_2"):
            reg = BY_NAME[canonical]
            assert reg.scale == ScaleFactor.DIV_10
            assert reg.unit == "V"

    def test_soc_members_are_unscaled_percent(self) -> None:
        """Raw-vs-named cross-check: raw 80 -> '80' and raw 50 -> '50'."""
        for canonical in ("grid_peak_shaving_soc", "grid_peak_shaving_soc_2"):
            reg = BY_NAME[canonical]
            assert reg.scale == ScaleFactor.NONE
            assert reg.unit == "%"

    def test_register_231_has_no_canonical_row(self) -> None:
        """231 is a real but unknown field (even-quantized writes, raw 0);
        it must stay unmapped until identified."""
        assert 231 not in BY_ADDRESS


class TestPeakShavingTransportMapExclusion:
    """The family must stay OUT of the transport name maps until the power
    members' raw encodings are write-verified (reg-202 discipline)."""

    def test_register_231_not_in_transport_map(self) -> None:
        assert 231 not in REGISTER_TO_PARAM_KEYS

    def test_family_api_keys_not_locally_resolvable(self) -> None:
        """write_named_parameters() must raise 'Unknown parameter name' for
        the family instead of writing an unverified raw encoding (or, as the
        old 231 entry did, writing an unrelated register entirely)."""
        param_to_reg = get_param_to_register_mapping()
        for _canonical, (_address, api_key) in PEAK_SHAVING_FAMILY.items():
            assert api_key not in param_to_reg, (
                f"{api_key} resolves to reg {param_to_reg.get(api_key)} for "
                "local name-writes, but its raw encoding is unverified"
            )
            assert api_key not in PARAM_KEY_TO_REGISTER

    def test_family_registers_not_named_in_transport_map(self) -> None:
        for _canonical, (address, _api_key) in PEAK_SHAVING_FAMILY.items():
            assert address not in REGISTER_TO_PARAM_KEYS, (
                f"reg {address} is named in REGISTER_TO_PARAM_KEYS — the local "
                "parameter refresh would surface raw values as engineering "
                "units before scaling support exists"
            )


class _PropertyTestInverter(BaseInverter):
    """Concrete BaseInverter for property unit tests."""

    def to_entities(self) -> list[Entity]:
        return []


def _make_inverter() -> _PropertyTestInverter:
    return _PropertyTestInverter(
        client=Mock(spec=LuxpowerClient),
        serial_number="4512670118",
        model="18KPV",
    )


class TestGridPeakShavingPowerLimitProperty:
    """grid_peak_shaving_power_limit must never fabricate a 0.0 reading.

    In HYBRID mode parameters are refreshed through the local transport,
    whose name map deliberately omits the PS1 key — a key-miss means
    "unavailable locally", not "setpoint is 0 kW" (eg4-gfu5 codex HIGH).
    """

    def test_none_when_parameters_not_loaded(self) -> None:
        inverter = _make_inverter()
        inverter.parameters = None
        assert inverter.grid_peak_shaving_power_limit is None

    def test_none_when_key_absent(self) -> None:
        """Transport-named parameter dicts lack the cloud-only PS1 key."""
        inverter = _make_inverter()
        inverter.parameters = {"HOLD_SYSTEM_CHARGE_SOC_LIMIT": 80, "206": 55}
        assert inverter.grid_peak_shaving_power_limit is None

    def test_value_when_cloud_named_key_present(self) -> None:
        inverter = _make_inverter()
        inverter.parameters = {"_12K_HOLD_GRID_PEAK_SHAVING_POWER": "7.0"}
        assert inverter.grid_peak_shaving_power_limit == 7.0

    def test_real_zero_setpoint_still_reads_zero(self) -> None:
        """An actual cloud-reported 0 remains 0.0 — only key ABSENCE is None."""
        inverter = _make_inverter()
        inverter.parameters = {"_12K_HOLD_GRID_PEAK_SHAVING_POWER": "0"}
        assert inverter.grid_peak_shaving_power_limit == 0.0
