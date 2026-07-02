"""Unit tests for canonical battery register readers.

Regression coverage for eg4_web_monitor#287: the local battery firmware
version string must match the cloud API's ``fwVersionText`` rendering
(zero-padded two-digit minor), otherwise HYBRID mode flaps the entity
between two spellings of the same version ("1.3" vs "1.03").
"""

import pytest

from pylxpweb.registers.battery import BY_NAME
from pylxpweb.transports._canonical_reader import read_battery_firmware

FW_REG = BY_NAME["battery_firmware_version"]
BASE = 5002


def _registers(raw: int) -> dict[int, int]:
    return {BASE + FW_REG.offset: raw}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0x0103, "1.03"),  # eg4_web_monitor#287: cloud shows 1.03, local said 1.3
        (0x0211, "2.17"),  # already two digits, unchanged by the padding
        (0x011E, "1.30"),  # minor 30 keeps its trailing zero
        (0x0200, "2.00"),  # minor 0 pads to two digits
        (0x0A63, "10.99"),  # two-digit major passes through untouched
    ],
)
def test_firmware_version_matches_cloud_rendering(raw: int, expected: str) -> None:
    assert read_battery_firmware(_registers(raw), FW_REG, base_address=BASE) == expected


def test_firmware_version_zero_register_reads_empty() -> None:
    assert read_battery_firmware(_registers(0), FW_REG, base_address=BASE) == ""


def test_firmware_version_missing_register_reads_empty() -> None:
    assert read_battery_firmware({}, FW_REG, base_address=BASE) == ""
