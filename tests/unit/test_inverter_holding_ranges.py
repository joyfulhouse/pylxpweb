"""Firmware-verified ranges for inverter holding registers."""

from pylxpweb.registers.inverter_holding import BY_NAME


def test_h66_firmware_range() -> None:
    """Issue #272: firmware rejects H66 raw >=101 with exception 03."""
    register = BY_NAME["ac_charge_power"]

    assert register.min_value == 0
    assert register.max_value == 10000


def test_h160_firmware_range() -> None:
    """Issue #271: firmware rejects H160 raw 0 and >=91 with exception 03."""
    register = BY_NAME["ac_charge_start_soc"]

    assert register.min_value == 1
    assert register.max_value == 90


def test_h105_range_ceiling_is_100() -> None:
    """eg4 #603: a portal-typed 95 is stored (LXP-LB-US 10K); >100 rejected.

    The ceiling is portal-correlated on one model, not firmware-proven. The 10
    floor is the portal hint, unproven either way — pinned so a drift is loud.
    """
    register = BY_NAME["ongrid_discharge_cutoff_soc"]

    assert register.address == 105
    assert register.min_value == 10
    assert register.max_value == 100
