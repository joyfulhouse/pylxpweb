"""Firmware-verified ranges for inverter holding registers."""

from pylxpweb.registers.inverter_holding import BY_NAME


def test_h66_firmware_range() -> None:
    register = BY_NAME["ac_charge_power"]

    assert register.min_value == 0
    assert register.max_value == 10000


def test_h160_firmware_range() -> None:
    register = BY_NAME["ac_charge_start_soc"]

    assert register.min_value == 1
    assert register.max_value == 90
