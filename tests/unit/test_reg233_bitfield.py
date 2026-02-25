"""Unit tests for register 233 (FUNC_EN_5) bitfield mapping."""

from __future__ import annotations

from pylxpweb.registers.inverter_holding import (
    BY_API_KEY,
    BY_NAME,
    HoldingCategory,
    bitfield_entries_for_address,
)


class TestReg233Bitfield:
    """Test register 233 bitfield entries."""

    def test_expected_bits_mapped(self) -> None:
        entries = bitfield_entries_for_address(233)
        bits = {e.bit_position for e in entries}
        expected = {0, 1, 2, 3, 10, 12}
        assert expected.issubset(bits), f"Missing bits: {expected - bits}"

    def test_quick_charge_start_bit0(self) -> None:
        reg = BY_NAME["quick_charge_start_enable"]
        assert reg.address == 233
        assert reg.bit_position == 0
        assert reg.api_param_key == "FUNC_QUICK_CHG_START_EN"

    def test_battery_backup_bit1(self) -> None:
        reg = BY_NAME["battery_backup_enable"]
        assert reg.address == 233
        assert reg.bit_position == 1
        assert reg.api_param_key == "FUNC_BATT_BACKUP_EN"

    def test_maintenance_bit2(self) -> None:
        reg = BY_NAME["maintenance_enable"]
        assert reg.address == 233
        assert reg.bit_position == 2

    def test_weekly_schedule_bit3(self) -> None:
        reg = BY_NAME["weekly_schedule_enable"]
        assert reg.address == 233
        assert reg.bit_position == 3
        assert reg.api_param_key == "FUNC_ENERTEK_WORKING_MODE"
        assert reg.ha_entity_key == "weekly_schedule"

    def test_over_freq_fast_stop_bit10(self) -> None:
        reg = BY_NAME["over_freq_fast_stop"]
        assert reg.address == 233
        assert reg.bit_position == 10

    def test_sporadic_charge_bit12(self) -> None:
        reg = BY_NAME["sporadic_charge_enable"]
        assert reg.address == 233
        assert reg.bit_position == 12
        assert reg.api_param_key == "FUNC_SPORADIC_CHARGE"
        assert reg.ha_entity_key == "sporadic_charge"

    def test_all_are_function_category(self) -> None:
        for entry in bitfield_entries_for_address(233):
            assert entry.category == HoldingCategory.FUNCTION

    def test_api_key_lookups(self) -> None:
        for key in (
            "FUNC_ENERTEK_WORKING_MODE",
            "FUNC_SPORADIC_CHARGE",
            "FUNC_QUICK_CHG_START_EN",
        ):
            assert key in BY_API_KEY, f"{key} missing from BY_API_KEY"
