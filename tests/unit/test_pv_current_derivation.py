"""PV string current is DERIVED (I = P / V), not read from a register.

EG4 hybrid inverters expose no PV-current Modbus register — input registers
72-74 (historically labelled ``pvN_current``) read 0 even while the strings
produce, verified live on an 18kPV and a FlexBOSS21, and the firmware
decompilation defines no PV-current register.  The cloud API likewise has no
PV-current field.  These tests lock in the derivation across the Modbus path,
the HTTP path, and the inverter runtime properties so regs 72-74 can never
silently feed a wrong value again (eg4_web_monitor issue #243).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pylxpweb.constants.scaling import derive_pv_current
from pylxpweb.devices.inverters._runtime_properties import (
    InverterRuntimePropertiesMixin,
)
from pylxpweb.models import InverterRuntime
from pylxpweb.transports._field_mappings import RUNTIME_FIELD
from pylxpweb.transports.data import InverterRuntimeData


class TestDerivePVCurrentHelper:
    """Unit tests for the ``derive_pv_current`` helper."""

    @pytest.mark.parametrize(
        ("power", "voltage", "expected"),
        [
            (935, 265.4, 3.52),  # producing string
            (1485.0, 434.6, 3.42),
            (0, 120.0, 0.0),  # idle but energised string
            (100, 0, 0.0),  # voltage ~0 -> no divide-by-zero
            (100, -1, 0.0),  # negative/garbage voltage -> 0
            (None, 250.0, None),  # absent string stays absent
            (500, None, None),
            (None, None, None),
        ],
    )
    def test_derivation(
        self, power: float | None, voltage: float | None, expected: float | None
    ) -> None:
        assert derive_pv_current(power, voltage) == expected


class TestModbusPVCurrentDerived:
    """The Modbus path derives PV current and ignores registers 72-74."""

    def _producing_regs(self) -> dict[int, int]:
        return {
            1: 2764,  # PV1 voltage ×10 = 276.4 V
            2: 3600,  # PV2 voltage ×10 = 360.0 V
            3: 0,  # PV3 voltage (idle)
            7: 574,  # PV1 power = 574 W -> I = 574/276.4 = 2.08 A
            8: 1050,  # PV2 power = 1050 W -> I = 1050/360.0 = 2.92 A
            9: 0,  # PV3 power
        }

    def test_pv_current_computed_from_power_and_voltage(self) -> None:
        data = InverterRuntimeData.from_modbus_registers(self._producing_regs())
        assert data.pv1_current == round(574 / 276.4, 2)
        assert data.pv2_current == round(1050 / 360.0, 2)
        # PV3 energised at 0 V reads 0 power -> 0.0 A (not None: register present)
        assert data.pv3_current == 0.0

    def test_registers_72_74_are_ignored(self) -> None:
        """Regs 72-74 carry NONZERO garbage but must not feed pv*_current.

        This is the issue #243 guard: the value comes from power/voltage, never
        from the registers historically mislabelled ``pvN_current``.
        """
        regs = self._producing_regs()
        regs.update({72: 9999, 73: 8888, 74: 7777})  # bogus nonzero
        data = InverterRuntimeData.from_modbus_registers(regs)
        assert data.pv1_current == round(574 / 276.4, 2)
        assert data.pv2_current == round(1050 / 360.0, 2)
        # If regs 72-74 leaked in, these would be 99.99 / 88.88 / 77.77.
        assert data.pv1_current != 99.99
        assert data.pv2_current != 88.88

    def test_runtime_field_does_not_route_regs_72_74(self) -> None:
        """The runtime-field contract acknowledges 72-74 but routes them nowhere."""
        assert RUNTIME_FIELD["pv1_current"] is None
        assert RUNTIME_FIELD["pv2_current"] is None
        assert RUNTIME_FIELD["pv3_current"] is None

    def test_absent_strings_stay_none(self) -> None:
        # 3-string model: pv4-6 registers absent -> current None, not 0.
        data = InverterRuntimeData.from_modbus_registers(self._producing_regs())
        assert data.pv4_current is None
        assert data.pv5_current is None
        assert data.pv6_current is None

    def test_pv4_5_current_for_multistring_model(self) -> None:
        regs = {
            217: 3000,  # pv4 voltage ×10 = 300.0 V
            218: 2500,  # pv5 voltage ×10 = 250.0 V
            220: 1500,  # pv4 power = 1500 W
            221: 1000,  # pv5 power = 1000 W
        }
        data = InverterRuntimeData.from_modbus_registers(regs, "EG4_HYBRID", pv_string_count=5)
        assert data.pv4_current == round(1500 / 300.0, 2)
        assert data.pv5_current == round(1000 / 250.0, 2)
        assert data.pv6_current is None  # string 6 absent for a 5-string model


class TestHttpPVCurrentDerived:
    """The HTTP/cloud path derives PV current the same way."""

    def test_pv_current_from_cloud_fields(self) -> None:
        runtime = MagicMock(spec=InverterRuntime)
        # Directly-scaled fields need real numerics (production scales them
        # unconditionally); guarded power/extended fields may be None.
        runtime.vBat = 530
        runtime.vacr = runtime.vacs = runtime.vact = 2410
        runtime.fac = runtime.feps = 5998
        runtime.vepsr = runtime.vepss = runtime.vepst = 2400
        runtime.vBus1 = runtime.vBus2 = 3700
        runtime.vpv4 = runtime.vpv5 = runtime.vpv6 = None
        runtime.ppv3 = runtime.ppv4 = runtime.ppv5 = runtime.ppv6 = None
        for attr in [
            "soc",
            "pCharge",
            "pDisCharge",
            "tBat",
            "prec",
            "pToGrid",
            "pinv",
            "peps",
            "seps",
            "pToUser",
            "tinner",
            "tradiator1",
            "tradiator2",
            "status",
        ]:
            setattr(runtime, attr, 0)
        runtime.vpv1 = 2500  # 250.0 V after /10
        runtime.vpv2 = 3000  # 300.0 V
        runtime.vpv3 = 0
        runtime.ppv1 = 1000
        runtime.ppv2 = 1500
        runtime.ppv = 2500

        data = InverterRuntimeData.from_http_response(runtime)

        assert data.pv1_current == round(1000 / 250.0, 2)
        assert data.pv2_current == round(1500 / 300.0, 2)


class _PropsObj(InverterRuntimePropertiesMixin):
    """Minimal carrier exposing the runtime-property mixin for direct testing."""

    def __init__(
        self,
        runtime: object | None = None,
        transport_runtime: object | None = None,
    ) -> None:
        self._runtime = runtime  # type: ignore[assignment]
        self._transport_runtime = transport_runtime  # type: ignore[assignment]


class TestInverterPropertyPVCurrent:
    """The inverter ``pvN_current`` property derives from its own power/voltage."""

    def test_transport_path(self) -> None:
        # Hybrid/local: properties resolve the Modbus transport runtime.
        tr = InverterRuntimeData(pv1_voltage=276.4, pv1_power=574.0)
        obj = _PropsObj(transport_runtime=tr)
        assert obj.pv1_current == round(574.0 / 276.4, 2)

    def test_cloud_path(self) -> None:
        # Cloud: no transport runtime, properties fall back to the HTTP model.
        runtime = MagicMock(spec=InverterRuntime)
        runtime.vpv1 = 2500  # 250.0 V after /10
        runtime.ppv1 = 1000
        obj = _PropsObj(runtime=runtime)
        assert obj.pv1_current == round(1000 / 250.0, 2)

    def test_absent_string_is_none(self) -> None:
        obj = _PropsObj(transport_runtime=InverterRuntimeData())
        assert obj.pv1_current is None
