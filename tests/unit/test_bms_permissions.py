"""BMS permission/request flags from register 95 (eg4 issue #232).

Register 95 is a BMS permission/request bitmap, validated against the cloud API
booleans ``bmsCharge`` / ``bmsDischarge`` / ``bmsForceCharge``:

* ``0x01`` — charge allowed
* ``0x02`` — discharge allowed
* ``0x20`` — force-charge request

These tests lock the bit layout, the LOCAL Modbus decode (onto both
``InverterRuntimeData`` and ``BatteryBankData``), and the dual-source
``BaseInverter`` / ``BatteryBank`` accessors.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.constants.registers import (
    BMS_PERMISSION_ALLOW_CHARGE,
    BMS_PERMISSION_ALLOW_DISCHARGE,
    BMS_PERMISSION_FORCE_CHARGE,
    decode_bms_permissions,
)
from pylxpweb.devices.battery_bank import BatteryBank
from pylxpweb.devices.inverters.base import BaseInverter
from pylxpweb.devices.inverters.generic import GenericInverter
from pylxpweb.models import BatteryInfo
from pylxpweb.transports.data import BatteryBankData, InverterRuntimeData


class TestDecodeBmsPermissions:
    """The pure bit-decode helper — the single source of the reg-95 layout."""

    def test_bit_masks(self) -> None:
        assert BMS_PERMISSION_ALLOW_CHARGE == 0x01
        assert BMS_PERMISSION_ALLOW_DISCHARGE == 0x02
        assert BMS_PERMISSION_FORCE_CHARGE == 0x20

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (0x00, (False, False, False)),  # Idle
            (0x01, (True, False, False)),  # charge-only (legacy "Unknown(1)")
            (0x02, (False, True, False)),  # discharge-only (legacy "StandBy")
            (0x03, (True, True, False)),  # both (legacy "Active")
            (0x20, (False, False, True)),  # force-charge request only
            (0x21, (True, False, True)),  # charge + force
            (0x22, (False, True, True)),  # discharge + force
            (0x23, (True, True, True)),  # all three
        ],
    )
    def test_decode(self, raw: int, expected: tuple[bool, bool, bool]) -> None:
        assert decode_bms_permissions(raw) == expected

    def test_ignores_unrelated_bits(self) -> None:
        """Unknown high bits must not bleed into the three decoded flags."""
        # 0x1C = bits 2,3,4 set (none of ours) → all False.
        assert decode_bms_permissions(0x1C) == (False, False, False)
        # Our bits set alongside noise still decode cleanly.
        assert decode_bms_permissions(0x01 | 0x40) == (True, False, False)


# Minimal valid battery register set (battery_voltage >= 1.0 so the bank parses).
_BASE_BATTERY_REGS: dict[int, int] = {
    4: 530,  # battery voltage ×10 = 53.0V
    5: (100 << 8) | 85,  # SOC=85, SOH=100
}


class TestRuntimeDataDecode:
    """InverterRuntimeData.from_modbus_registers decodes reg 95."""

    def test_absent_register_leaves_flags_none(self) -> None:
        data = InverterRuntimeData.from_modbus_registers({4: 530})
        assert data.bms_allow_charge is None
        assert data.bms_allow_discharge is None
        assert data.bms_force_charge is None

    @pytest.mark.parametrize(
        ("raw", "charge", "discharge", "force"),
        [
            (0x03, True, True, False),
            (0x01, True, False, False),
            (0x02, False, True, False),
            (0x20, False, False, True),
            (0x00, False, False, False),
        ],
    )
    def test_decoded_from_reg95(self, raw: int, charge: bool, discharge: bool, force: bool) -> None:
        data = InverterRuntimeData.from_modbus_registers({4: 530, 95: raw})
        assert data.bms_allow_charge is charge
        assert data.bms_allow_discharge is discharge
        assert data.bms_force_charge is force


class TestBatteryBankDataDecode:
    """BatteryBankData.from_modbus_registers decodes reg 95."""

    def test_decoded_from_reg95(self) -> None:
        regs = {**_BASE_BATTERY_REGS, 95: 0x21}
        bank = BatteryBankData.from_modbus_registers(regs)
        assert bank is not None
        assert bank.allow_charge is True
        assert bank.allow_discharge is False
        assert bank.force_charge is True

    def test_absent_register_leaves_flags_none(self) -> None:
        bank = BatteryBankData.from_modbus_registers(dict(_BASE_BATTERY_REGS))
        assert bank is not None
        assert bank.allow_charge is None
        assert bank.allow_discharge is None
        assert bank.force_charge is None


class TestBatteryBankDelegation:
    """Cloud BatteryBank delegates the flags to its parent inverter.

    Uses a real GenericInverter with transport-decoded flags so the full chain
    (reg 95 -> InverterRuntimeData -> inverter property -> bank property) is
    exercised end to end.
    """

    def _bank(self, inverter: BaseInverter | None) -> BatteryBank:
        client = Mock(spec=LuxpowerClient)
        info = BatteryInfo.model_construct(batStatus="Charging", batteryArray=[])
        return BatteryBank(
            client=client,
            inverter_serial="1234567890",
            battery_info=info,
            inverter=inverter,
        )

    def test_delegates_to_parent_inverter(self) -> None:
        client = Mock(spec=LuxpowerClient)
        inverter = GenericInverter(client=client, serial_number="1234567890", model="18KPV")
        inverter._transport_runtime = InverterRuntimeData(
            bms_allow_charge=True, bms_allow_discharge=False, bms_force_charge=True
        )
        bank = self._bank(inverter)
        assert bank.allow_charge is True
        assert bank.allow_discharge is False
        assert bank.force_charge is True

    def test_none_when_no_parent_inverter(self) -> None:
        bank = self._bank(None)
        assert bank.allow_charge is None
        assert bank.allow_discharge is None
        assert bank.force_charge is None
