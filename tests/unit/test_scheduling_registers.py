"""Unit tests for 7-day scheduling register definitions (regs 500-723)."""

from __future__ import annotations

from pylxpweb.registers.inverter_holding import HoldingCategory
from pylxpweb.registers.scheduling import (
    DAYS,
    SCHEDULE_BY_ADDRESS,
    SCHEDULE_BY_API_KEY,
    SCHEDULE_BY_NAME,
    SCHEDULE_REGISTERS,
    SCHEDULE_TYPES,
)


class TestScheduleTypeConfig:
    def test_four_schedule_types(self) -> None:
        assert len(SCHEDULE_TYPES) == 4

    def test_ac_charge_config(self) -> None:
        assert SCHEDULE_TYPES[0].name == "ac_charge"
        assert SCHEDULE_TYPES[0].base_address == 500

    def test_forced_charge_config(self) -> None:
        assert SCHEDULE_TYPES[1].name == "forced_charge"
        assert SCHEDULE_TYPES[1].base_address == 556

    def test_forced_discharge_config(self) -> None:
        assert SCHEDULE_TYPES[2].name == "forced_discharge"
        assert SCHEDULE_TYPES[2].base_address == 612

    def test_peak_shaving_config(self) -> None:
        assert SCHEDULE_TYPES[3].name == "peak_shaving"
        assert SCHEDULE_TYPES[3].base_address == 668

    def test_seven_days(self) -> None:
        assert len(DAYS) == 7
        assert DAYS[0] == "mon"
        assert DAYS[6] == "sun"


class TestScheduleRegisterGeneration:
    def test_total_register_count(self) -> None:
        assert len(SCHEDULE_REGISTERS) == 224

    def test_address_range(self) -> None:
        addresses = {r.address for r in SCHEDULE_REGISTERS}
        assert min(addresses) == 500
        assert max(addresses) == 723

    def test_no_duplicate_addresses(self) -> None:
        addresses = [r.address for r in SCHEDULE_REGISTERS]
        assert len(addresses) == len(set(addresses))

    def test_no_duplicate_names(self) -> None:
        names = [r.canonical_name for r in SCHEDULE_REGISTERS]
        assert len(names) == len(set(names))

    def test_all_writable(self) -> None:
        for reg in SCHEDULE_REGISTERS:
            assert reg.writable is True

    def test_all_schedule_category(self) -> None:
        for reg in SCHEDULE_REGISTERS:
            assert reg.category == HoldingCategory.SCHEDULE


class TestScheduleRegisterNaming:
    def test_first_register_name(self) -> None:
        reg = SCHEDULE_REGISTERS[0]
        assert reg.canonical_name == "ac_charge_power_cmd_1_mon"
        assert reg.address == 500

    def test_slot2_name(self) -> None:
        reg = SCHEDULE_BY_NAME["ac_charge_power_cmd_2_mon"]
        assert reg.address == 504

    def test_tuesday_name(self) -> None:
        reg = SCHEDULE_BY_NAME["ac_charge_power_cmd_1_tue"]
        assert reg.address == 508

    def test_last_register(self) -> None:
        last = SCHEDULE_REGISTERS[-1]
        assert last.canonical_name == "peak_shaving_time_end_2_sun"
        assert last.address == 723


class TestScheduleLookupIndexes:
    def test_by_address_complete(self) -> None:
        assert len(SCHEDULE_BY_ADDRESS) == 224

    def test_by_name_complete(self) -> None:
        assert len(SCHEDULE_BY_NAME) == 224

    def test_by_api_key_complete(self) -> None:
        assert len(SCHEDULE_BY_API_KEY) == 224

    def test_address_lookup(self) -> None:
        reg = SCHEDULE_BY_ADDRESS[500]
        assert reg.canonical_name == "ac_charge_power_cmd_1_mon"

    def test_api_key_pattern(self) -> None:
        reg = SCHEDULE_BY_NAME["ac_charge_power_cmd_1_mon"]
        assert reg.api_param_key == "ubACChgPowerCMD1_Day_1"

    def test_forced_discharge_api_key(self) -> None:
        reg = SCHEDULE_BY_NAME["forced_discharge_power_cmd_1_wed"]
        assert reg.api_param_key == "ubForcedDischgPowerCMD1_Day_3"

    def test_peak_shaving_api_key(self) -> None:
        reg = SCHEDULE_BY_NAME["peak_shaving_time_end_2_sun"]
        assert reg.api_param_key == "ubGridPeakShavEndHour2_Day_7"
