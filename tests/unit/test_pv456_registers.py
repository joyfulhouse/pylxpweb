"""Unit tests for PV4-6 input register definitions (V23, regs 217-231)."""

from __future__ import annotations

from pylxpweb.registers.inverter_input import (
    BY_CLOUD_FIELD,
    BY_NAME,
    RegisterCategory,
    ScaleFactor,
)
from pylxpweb.transports.data import InverterRuntimeData


class TestPV456Registers:
    """Test PV4-6 voltage, power, and energy register definitions."""

    def test_pv4_voltage_exists(self) -> None:
        reg = BY_NAME["pv4_voltage"]
        assert reg.address == 217
        assert reg.cloud_api_field == "vpv4"
        assert reg.ha_sensor_key == "pv4_voltage"
        assert reg.scale == ScaleFactor.DIV_10
        assert reg.unit == "V"
        assert reg.category == RegisterCategory.RUNTIME

    def test_pv5_voltage_exists(self) -> None:
        reg = BY_NAME["pv5_voltage"]
        assert reg.address == 218
        assert reg.cloud_api_field == "vpv5"
        assert reg.scale == ScaleFactor.DIV_10

    def test_pv6_voltage_exists(self) -> None:
        reg = BY_NAME["pv6_voltage"]
        assert reg.address == 219
        assert reg.cloud_api_field == "vpv6"
        assert reg.scale == ScaleFactor.DIV_10

    def test_pv4_power_exists(self) -> None:
        reg = BY_NAME["pv4_power"]
        assert reg.address == 220
        assert reg.cloud_api_field == "ppv4"
        assert reg.ha_sensor_key == "pv4_power"
        assert reg.unit == "W"

    def test_pv5_power_exists(self) -> None:
        reg = BY_NAME["pv5_power"]
        assert reg.address == 221
        assert reg.cloud_api_field == "ppv5"

    def test_pv6_power_exists(self) -> None:
        reg = BY_NAME["pv6_power"]
        assert reg.address == 222
        assert reg.cloud_api_field == "ppv6"

    def test_epv4_day_exists(self) -> None:
        reg = BY_NAME["epv4_day"]
        assert reg.address == 223
        assert reg.scale == ScaleFactor.DIV_10
        assert reg.unit == "kWh"
        assert reg.category == RegisterCategory.ENERGY_DAILY

    def test_epv4_all_is_32bit(self) -> None:
        reg = BY_NAME["epv4_all"]
        assert reg.address == 224
        assert reg.bit_width == 32
        assert reg.category == RegisterCategory.ENERGY_LIFETIME

    def test_epv5_day_exists(self) -> None:
        reg = BY_NAME["epv5_day"]
        assert reg.address == 226

    def test_epv5_all_is_32bit(self) -> None:
        reg = BY_NAME["epv5_all"]
        assert reg.address == 227
        assert reg.bit_width == 32

    def test_epv6_day_exists(self) -> None:
        reg = BY_NAME["epv6_day"]
        assert reg.address == 229

    def test_epv6_all_is_32bit(self) -> None:
        reg = BY_NAME["epv6_all"]
        assert reg.address == 230
        assert reg.bit_width == 32

    def test_all_12_registers_in_by_name(self) -> None:
        expected = [
            "pv4_voltage",
            "pv5_voltage",
            "pv6_voltage",
            "pv4_power",
            "pv5_power",
            "pv6_power",
            "epv4_day",
            "epv4_all",
            "epv5_day",
            "epv5_all",
            "epv6_day",
            "epv6_all",
        ]
        for name in expected:
            assert name in BY_NAME, f"{name} missing from BY_NAME"

    def test_cloud_field_lookups(self) -> None:
        expected_fields = (
            "vpv4",
            "vpv5",
            "vpv6",
            "ppv4",
            "ppv5",
            "ppv6",
            "epv4Today",
            "epv5Today",
            "epv6Today",
        )
        for cf in expected_fields:
            assert cf in BY_CLOUD_FIELD, f"{cf} missing from BY_CLOUD_FIELD"


class TestPV456DataModelFields:
    """Test that InverterRuntimeData has PV4-6 fields."""

    def test_pv4_voltage_field(self) -> None:
        data = InverterRuntimeData(pv4_voltage=300.0)
        assert data.pv4_voltage == 300.0

    def test_pv5_voltage_field(self) -> None:
        data = InverterRuntimeData(pv5_voltage=310.0)
        assert data.pv5_voltage == 310.0

    def test_pv6_voltage_field(self) -> None:
        data = InverterRuntimeData(pv6_voltage=320.0)
        assert data.pv6_voltage == 320.0

    def test_pv4_power_field(self) -> None:
        data = InverterRuntimeData(pv4_power=2400.0)
        assert data.pv4_power == 2400.0

    def test_pv5_power_field(self) -> None:
        data = InverterRuntimeData(pv5_power=2500.0)
        assert data.pv5_power == 2500.0

    def test_pv6_power_field(self) -> None:
        data = InverterRuntimeData(pv6_power=2600.0)
        assert data.pv6_power == 2600.0
