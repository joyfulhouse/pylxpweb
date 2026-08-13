"""Firmware-verified boundary tests for inverter holding registers."""

from pylxpweb.registers.inverter_holding import BY_NAME, HoldingRegisterDefinition


def _accepts_value(register: HoldingRegisterDefinition, value: int) -> bool:
    """Return whether an engineering-unit value is within the register bounds."""
    assert register.min_value is not None
    assert register.max_value is not None
    return register.min_value <= value <= register.max_value


def test_h66_accepts_raw_100_and_rejects_raw_101() -> None:
    """H66 firmware accepts 100 W units from raw 0 through raw 100 only."""
    register = BY_NAME["ac_charge_power"]

    assert _accepts_value(register, 100 * 100)
    assert not _accepts_value(register, 101 * 100)


def test_h160_accepts_raw_1_through_90_only() -> None:
    """H160 firmware rejects zero and values at or above 91."""
    register = BY_NAME["ac_charge_start_soc"]

    assert not _accepts_value(register, 0)
    assert _accepts_value(register, 1)
    assert _accepts_value(register, 90)
    assert not _accepts_value(register, 91)
