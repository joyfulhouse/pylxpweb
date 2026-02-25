"""Unit tests for register 179 (FUNC_EN_4) complete bitfield mapping."""

from __future__ import annotations

from pylxpweb.registers.inverter_holding import (
    BY_API_KEY,
    BY_NAME,
    HoldingCategory,
    bitfield_entries_for_address,
)


class TestReg179Bitfield:
    """Test all 16 bits of register 179 are mapped."""

    def test_all_16_bits_mapped(self) -> None:
        entries = bitfield_entries_for_address(179)
        bits = {e.bit_position for e in entries}
        assert bits == set(range(16)), f"Missing bits: {set(range(16)) - bits}"

    def test_all_entries_are_function_category(self) -> None:
        for entry in bitfield_entries_for_address(179):
            assert entry.category == HoldingCategory.FUNCTION

    def test_ac_ct_direction_bit0(self) -> None:
        reg = BY_NAME["ac_ct_direction"]
        assert reg.address == 179
        assert reg.bit_position == 0
        assert reg.api_param_key == "FUNC_AC_CT_DIRECTION"

    def test_battery_charge_control_bit9(self) -> None:
        reg = BY_NAME["battery_charge_control"]
        assert reg.address == 179
        assert reg.bit_position == 9
        assert reg.api_param_key == "FUNC_BAT_CHARGE_CONTROL"
        assert reg.ha_entity_key == "battery_charge_control"

    def test_battery_discharge_control_bit10(self) -> None:
        reg = BY_NAME["battery_discharge_control"]
        assert reg.address == 179
        assert reg.bit_position == 10
        assert reg.api_param_key == "FUNC_BAT_DISCHARGE_CONTROL"
        assert reg.ha_entity_key == "battery_discharge_control"

    def test_ac_coupling_bit11(self) -> None:
        reg = BY_NAME["ac_coupling_enable"]
        assert reg.address == 179
        assert reg.bit_position == 11
        assert reg.api_param_key == "FUNC_AC_COUPLING"
        assert reg.ha_entity_key == "ac_coupling"

    def test_smart_load_bit13(self) -> None:
        reg = BY_NAME["smart_load_enable"]
        assert reg.address == 179
        assert reg.bit_position == 13
        assert reg.api_param_key == "FUNC_SMART_LOAD_EN"
        assert reg.ha_entity_key == "smart_load"

    def test_rsd_disable_bit14(self) -> None:
        reg = BY_NAME["rsd_disable"]
        assert reg.address == 179
        assert reg.bit_position == 14

    def test_ongrid_always_on_bit15(self) -> None:
        reg = BY_NAME["ongrid_always_on"]
        assert reg.address == 179
        assert reg.bit_position == 15

    def test_api_key_lookups(self) -> None:
        for key in (
            "FUNC_AC_CT_DIRECTION",
            "FUNC_BAT_CHARGE_CONTROL",
            "FUNC_BAT_DISCHARGE_CONTROL",
            "FUNC_AC_COUPLING",
            "FUNC_SMART_LOAD_EN",
        ):
            assert key in BY_API_KEY, f"{key} missing from BY_API_KEY"
