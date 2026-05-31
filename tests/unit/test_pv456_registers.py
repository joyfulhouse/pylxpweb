"""Unit tests for PV4-6 input register definitions (V23, regs 217-231).

PV4-6 are the V23-extended PV strings.  Their registers are defined for ALL
families (so ``from_modbus_registers`` CAN parse them), but reading and parsing
are gated entirely by the inverter MODEL's ``pv_string_count`` — not the family.
A 3-string model (the residential norm) never reads regs 217-222 and leaves
pv4-6 None; a model declaring ``pv_string_count >= 4`` populates them.
"""

from __future__ import annotations

import pytest

from pylxpweb.constants import ScaleFactor as RuntimeScaleFactor
from pylxpweb.constants.scaling import scale_runtime_value
from pylxpweb.models import InverterRuntime
from pylxpweb.registers.inverter_input import (
    BY_CLOUD_FIELD,
    BY_NAME,
    PV4_6_ENERGY_INPUT_REGISTER_GROUP,
    PV4_6_EXTENDED_NAMES,
    PV4_6_INPUT_REGISTER_GROUP,
    RegisterCategory,
    ScaleFactor,
    pv_string_count_for_model,
    registers_for_model,
    sensor_keys_for_model,
)
from pylxpweb.transports._field_mappings import ENERGY_FIELD
from pylxpweb.transports.data import InverterEnergyData, InverterRuntimeData

_PV4_6_CANONICAL = (
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
)


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
        for name in _PV4_6_CANONICAL:
            assert name in BY_NAME, f"{name} missing from BY_NAME"

    def test_cloud_field_lookups(self) -> None:
        # PV4-6 RUNTIME (voltage/power) cloud fields are wired (E1).
        expected_fields = (
            "vpv4",
            "vpv5",
            "vpv6",
            "ppv4",
            "ppv5",
            "ppv6",
        )
        for cf in expected_fields:
            assert cf in BY_CLOUD_FIELD, f"{cf} missing from BY_CLOUD_FIELD"

    def test_pv456_energy_cloud_fields_deferred(self) -> None:
        # PV4-6 ENERGY: the LOCAL (modbus) path is now fully wired (eg4-478) —
        # read group 223-231, pv_string_count gate, dataclass fields.  The CLOUD
        # path stays deferred: there is no cloud EnergyInfo field for pv4-6
        # energy, so the epvNToday cloud fields remain absent from the register
        # table and the cloud↔modbus scale contract is not falsely asserted.
        # When real >3-string cloud data appears, add the cloud fields + scaling.
        for cf in ("epv4Today", "epv5Today", "epv6Today"):
            assert cf not in BY_CLOUD_FIELD, (
                f"{cf} is back in BY_CLOUD_FIELD; if pv4-6 cloud energy is now "
                f"wired, add its scaling and a parity proof"
            )

    def test_input_register_group_span(self) -> None:
        # The conditional read groups must cover exactly regs 217-222 (V+P) and
        # regs 223-231 (daily + lifetime energy).
        assert PV4_6_INPUT_REGISTER_GROUP == (217, 6)
        assert PV4_6_ENERGY_INPUT_REGISTER_GROUP == (223, 9)


class TestPV456CountGating:
    """PV4-6 registers are defined for ALL families; gating is by count."""

    def test_extended_names_marker(self) -> None:
        assert frozenset(_PV4_6_CANONICAL) == PV4_6_EXTENDED_NAMES

    @pytest.mark.parametrize("name", _PV4_6_CANONICAL)
    def test_register_available_to_all_families(self, name: str) -> None:
        # pv4-6 registers carry models=ALL so from_modbus_registers CAN parse
        # them; the runtime gate is pv_string_count, not the family.
        assert BY_NAME[name].models == frozenset({"EG4_HYBRID", "EG4_OFFGRID", "LXP"})

    @pytest.mark.parametrize("family", ["EG4_HYBRID", "EG4_OFFGRID", "LXP"])
    def test_pv4_6_present_in_register_set(self, family: str) -> None:
        names = {r.canonical_name for r in registers_for_model(family)}
        for pv in _PV4_6_CANONICAL:
            assert pv in names, f"{pv} should be present for {family}"

    @pytest.mark.parametrize("family", ["EG4_HYBRID", "EG4_OFFGRID", "LXP"])
    def test_pv4_6_sensor_keys_present(self, family: str) -> None:
        keys = sensor_keys_for_model(family)
        for pv in ("pv4_voltage", "pv5_voltage", "pv6_voltage", "pv4_power"):
            assert pv in keys

    def test_pv1_3_still_present_for_all_families(self) -> None:
        for family in ("EG4_HYBRID", "EG4_OFFGRID", "LXP"):
            names = {r.canonical_name for r in registers_for_model(family)}
            for pv in ("pv1_voltage", "pv2_voltage", "pv3_voltage"):
                assert pv in names


class TestPV456DataModelFields:
    """Test that InverterRuntimeData has PV4-6 fields."""

    def test_pv4_voltage_field(self) -> None:
        assert InverterRuntimeData(pv4_voltage=300.0).pv4_voltage == 300.0

    def test_pv5_voltage_field(self) -> None:
        assert InverterRuntimeData(pv5_voltage=310.0).pv5_voltage == 310.0

    def test_pv6_voltage_field(self) -> None:
        assert InverterRuntimeData(pv6_voltage=320.0).pv6_voltage == 320.0

    def test_pv4_power_field(self) -> None:
        assert InverterRuntimeData(pv4_power=2400.0).pv4_power == 2400.0

    def test_pv5_power_field(self) -> None:
        assert InverterRuntimeData(pv5_power=2500.0).pv5_power == 2500.0

    def test_pv6_power_field(self) -> None:
        assert InverterRuntimeData(pv6_power=2600.0).pv6_power == 2600.0


class TestPVStringCountFallback:
    """``pv_string_count_for_model`` is the register-derived FALLBACK count.

    It deliberately ignores the extended pv4-6 registers, so it stays at the
    conservative base of 3 for all current residential families even though
    those registers are now defined for all families.
    """

    @pytest.mark.parametrize("family", ["EG4_HYBRID", "EG4_OFFGRID", "LXP"])
    def test_three_string_families(self, family: str) -> None:
        assert pv_string_count_for_model(family) == 3

    def test_unknown_family_has_no_pv_registers(self) -> None:
        assert pv_string_count_for_model("UNKNOWN") == 0

    def test_fallback_never_exceeds_three(self) -> None:
        # The extended pv4-6 voltage registers must NOT inflate the base count.
        for family in ("EG4_HYBRID", "EG4_OFFGRID", "LXP"):
            assert pv_string_count_for_model(family) == 3


class TestPV456ModbusPopulationGating:
    """from_modbus_registers gates pv4-6 on pv_string_count, not family."""

    @pytest.mark.parametrize("family", ["EG4_HYBRID", "EG4_OFFGRID", "LXP"])
    def test_pv4_6_not_populated_for_3string_count(self, family: str) -> None:
        # Raw values present at 217-222 but model is 3-string (default) -> None.
        input_registers = {
            217: 3000,  # pv4_voltage raw (would be 300.0V)
            218: 3100,  # pv5_voltage raw
            219: 3200,  # pv6_voltage raw
            220: 2400,  # pv4_power raw
            221: 2500,  # pv5_power raw
            222: 2600,  # pv6_power raw
        }
        runtime = InverterRuntimeData.from_modbus_registers(input_registers, family)
        assert runtime.pv4_voltage is None
        assert runtime.pv5_voltage is None
        assert runtime.pv6_voltage is None
        assert runtime.pv4_power is None
        assert runtime.pv5_power is None
        assert runtime.pv6_power is None

    @pytest.mark.parametrize("family", ["EG4_HYBRID", "EG4_OFFGRID", "LXP"])
    def test_pv4_6_not_populated_explicit_count_3(self, family: str) -> None:
        input_registers = {217: 3000, 220: 2400}
        runtime = InverterRuntimeData.from_modbus_registers(
            input_registers, family, pv_string_count=3
        )
        assert runtime.pv4_voltage is None
        assert runtime.pv4_power is None


class TestPV456PositiveLocalEndToEnd:
    """POSITIVE: a >3-string model populates pv4/pv5 from raw modbus registers.

    This proves the LOCAL path end-to-end: feed raw input registers through
    ``from_modbus_registers`` for a model whose pv_string_count >= 5 and assert
    pv4/pv5 voltage AND power resolve (scaled), not None.
    """

    def test_pv4_pv5_populated_for_5string_model(self) -> None:
        input_registers = {
            217: 3000,  # pv4_voltage raw -> 300.0V (DIV_10)
            218: 3100,  # pv5_voltage raw -> 310.0V
            219: 3200,  # pv6_voltage raw -> 320.0V
            220: 2400,  # pv4_power raw -> 2400W (no scale)
            221: 2500,  # pv5_power raw -> 2500W
            222: 2600,  # pv6_power raw -> 2600W
        }
        runtime = InverterRuntimeData.from_modbus_registers(
            input_registers, "EG4_HYBRID", pv_string_count=5
        )
        # pv4 and pv5 are within the count -> populated and scaled.
        assert runtime.pv4_voltage == 300.0
        assert runtime.pv5_voltage == 310.0
        assert runtime.pv4_power == 2400
        assert runtime.pv5_power == 2500
        # pv6 is beyond the 5-string count -> left None.
        assert runtime.pv6_voltage is None
        assert runtime.pv6_power is None

    def test_pv4_6_all_populated_for_6string_model(self) -> None:
        input_registers = {
            217: 3000,
            218: 3100,
            219: 3200,
            220: 2400,
            221: 2500,
            222: 2600,
        }
        runtime = InverterRuntimeData.from_modbus_registers(
            input_registers, "EG4_HYBRID", pv_string_count=6
        )
        assert runtime.pv4_voltage == 300.0
        assert runtime.pv5_voltage == 310.0
        assert runtime.pv6_voltage == 320.0
        assert runtime.pv4_power == 2400
        assert runtime.pv5_power == 2500
        assert runtime.pv6_power == 2600


class TestPV456PositiveCloudEndToEnd:
    """POSITIVE: cloud InverterRuntime payload with vpv5/ppv5 resolves scaled.

    Proves the CLOUD path: build an InverterRuntime from a payload containing
    vpv4/vpv5/ppv4/ppv5 and assert the runtime properties resolve correctly
    (voltage scaled by /10, power unscaled).
    """

    def test_cloud_scaling_constants_present(self) -> None:
        # The cloud scaling table must scale vpv4-6 by /10 (voltage) and leave
        # ppv4-6 unscaled (watts).
        assert scale_runtime_value("vpv4", 3000) == 300.0
        assert scale_runtime_value("vpv5", 3100) == 310.0
        assert scale_runtime_value("vpv6", 3200) == 320.0
        assert scale_runtime_value("ppv4", 2400) == 2400.0
        assert scale_runtime_value("ppv5", 2500) == 2500.0
        # sanity: ensure the enum is the runtime ScaleFactor (import used)
        assert RuntimeScaleFactor.SCALE_10 == 10

    def test_cloud_runtime_properties_resolve(self) -> None:
        from unittest.mock import MagicMock

        from pylxpweb.devices.inverters.generic import GenericInverter

        runtime = InverterRuntime.model_construct(
            serialNum="1234567890",
            vpv1=5100,
            vpv2=4800,
            vpv3=3000,
            vpv4=3000,  # -> 300.0V
            vpv5=3100,  # -> 310.0V
            vpv6=3200,  # -> 320.0V
            ppv1=1500,
            ppv2=1200,
            ppv3=900,
            ppv4=2400,  # -> 2400W
            ppv5=2500,  # -> 2500W
            ppv6=2600,  # -> 2600W
            ppv=2700,
        )
        inverter = GenericInverter(
            client=MagicMock(),
            serial_number="1234567890",
            model="LSP-12K",
        )
        inverter._runtime = runtime
        inverter._transport_runtime = None

        assert inverter.pv4_voltage == 300.0
        assert inverter.pv5_voltage == 310.0
        assert inverter.pv6_voltage == 320.0
        assert inverter.pv4_power == 2400
        assert inverter.pv5_power == 2500
        assert inverter.pv6_power == 2600


class TestPV456TransportConditionalRead:
    """The transport reads regs 217-222 ONLY for models with pv_string_count>=4.

    Proves the LOCAL read path is safe for residential 3-string models (no
    extra/wasteful modbus read of 217-222) and active for >3-string models.
    """

    @staticmethod
    def _make_transport(pv_string_count: int):
        from pylxpweb.transports.modbus import ModbusTransport

        transport = ModbusTransport(host="192.168.1.100", serial="CE12345678")
        transport.pv_string_count = pv_string_count
        return transport

    @pytest.mark.asyncio
    async def test_three_string_model_does_not_read_pv4_6(self) -> None:
        from unittest.mock import AsyncMock, patch

        transport = self._make_transport(pv_string_count=3)
        requested_starts: list[int] = []

        async def fake_read(start: int, count: int) -> list[int]:
            requested_starts.append(start)
            return [0] * count

        with (
            patch.object(transport, "_read_input_registers", side_effect=fake_read),
            patch.object(transport, "_read_register_groups", new=AsyncMock(return_value={})),
        ):
            result = await transport._read_pv4_6_registers()

        # No read issued for the pv4-6 group on a 3-string model.
        assert result == {}
        assert 217 not in requested_starts

    @pytest.mark.asyncio
    async def test_five_string_model_reads_and_populates_pv4_6(self) -> None:
        from unittest.mock import patch

        transport = self._make_transport(pv_string_count=5)
        requested: list[tuple[int, int]] = []

        async def fake_read(start: int, count: int) -> list[int]:
            requested.append((start, count))
            # Return ascending sentinels so each address gets a distinct value.
            return [start + offset for offset in range(count)]

        with patch.object(transport, "_read_input_registers", side_effect=fake_read):
            regs = await transport._read_pv4_6_registers()

        # Both the voltage/power group AND the energy group are read for a
        # >3-string model.
        assert (217, 6) in requested
        assert (223, 9) in requested
        assert regs[217] == 217  # pv4_voltage raw
        assert regs[222] == 222  # pv6_power raw
        assert regs[223] == 223  # epv4_day raw
        assert regs[231] == 231  # epv6_all high word

    @pytest.mark.asyncio
    async def test_pv4_6_read_failure_is_non_fatal(self) -> None:
        from unittest.mock import patch

        from pylxpweb.transports.exceptions import TransportReadError

        transport = self._make_transport(pv_string_count=5)

        async def boom(start: int, count: int) -> list[int]:
            raise TransportReadError("simulated timeout on extended regs")

        with patch.object(transport, "_read_input_registers", side_effect=boom):
            regs = await transport._read_pv4_6_registers()

        # Failure leaves pv4-6 unpopulated rather than failing the whole read.
        assert regs == {}


class TestPV456EnergyDataModelFields:
    """InverterEnergyData has PV4-6 daily + lifetime energy fields (eg4-478)."""

    def test_pv4_energy_today_field(self) -> None:
        assert InverterEnergyData(pv4_energy_today=12.5).pv4_energy_today == 12.5

    def test_pv5_energy_today_field(self) -> None:
        assert InverterEnergyData(pv5_energy_today=13.5).pv5_energy_today == 13.5

    def test_pv6_energy_today_field(self) -> None:
        assert InverterEnergyData(pv6_energy_today=14.5).pv6_energy_today == 14.5

    def test_pv4_energy_total_field(self) -> None:
        assert InverterEnergyData(pv4_energy_total=1200.0).pv4_energy_total == 1200.0

    def test_pv5_energy_total_field(self) -> None:
        assert InverterEnergyData(pv5_energy_total=1300.0).pv5_energy_total == 1300.0

    def test_pv6_energy_total_field(self) -> None:
        assert InverterEnergyData(pv6_energy_total=1400.0).pv6_energy_total == 1400.0


class TestPV456EnergyFieldMapping:
    """ENERGY_FIELD maps epv4-6 day/all to real dataclass fields (not None)."""

    @pytest.mark.parametrize(
        ("canonical", "field"),
        [
            ("epv4_day", "pv4_energy_today"),
            ("epv5_day", "pv5_energy_today"),
            ("epv6_day", "pv6_energy_today"),
            ("epv4_all", "pv4_energy_total"),
            ("epv5_all", "pv5_energy_total"),
            ("epv6_all", "pv6_energy_total"),
        ],
    )
    def test_energy_field_mapped(self, canonical: str, field: str) -> None:
        assert ENERGY_FIELD[canonical] == field


class TestPV456EnergyModbusGating:
    """from_modbus_registers gates pv4-6 ENERGY on pv_string_count, not family.

    Layout (all DIV_10, 0.1 kWh): epv4_day=223, epv4_all=224(32b), epv5_day=226,
    epv5_all=227(32b), epv6_day=229, epv6_all=230(32b).
    """

    @staticmethod
    def _energy_registers() -> dict[int, int]:
        return {
            223: 100,  # epv4_day raw -> 10.0
            224: 5000,  # epv4_all low word -> 500.0 (high word 225 = 0)
            225: 0,
            226: 110,  # epv5_day -> 11.0
            227: 5100,  # epv5_all -> 510.0
            228: 0,
            229: 120,  # epv6_day -> 12.0
            230: 5200,  # epv6_all -> 520.0
            231: 0,
        }

    @pytest.mark.parametrize("family", ["EG4_HYBRID", "EG4_OFFGRID", "LXP"])
    def test_pv4_6_energy_not_populated_for_3string(self, family: str) -> None:
        # Raw values present at 223-231 but model is 3-string (default) -> None.
        energy = InverterEnergyData.from_modbus_registers(self._energy_registers(), family)
        assert energy.pv4_energy_today is None
        assert energy.pv5_energy_today is None
        assert energy.pv6_energy_today is None
        assert energy.pv4_energy_total is None
        assert energy.pv5_energy_total is None
        assert energy.pv6_energy_total is None

    def test_pv4_5_populated_for_5string(self) -> None:
        energy = InverterEnergyData.from_modbus_registers(
            self._energy_registers(), "EG4_HYBRID", pv_string_count=5
        )
        assert energy.pv4_energy_today == 10.0
        assert energy.pv5_energy_today == 11.0
        assert energy.pv4_energy_total == 500.0
        assert energy.pv5_energy_total == 510.0
        # pv6 is beyond the 5-string count -> left None.
        assert energy.pv6_energy_today is None
        assert energy.pv6_energy_total is None

    def test_pv4_6_all_populated_for_6string(self) -> None:
        energy = InverterEnergyData.from_modbus_registers(
            self._energy_registers(), "EG4_HYBRID", pv_string_count=6
        )
        assert energy.pv6_energy_today == 12.0
        assert energy.pv6_energy_total == 520.0


class TestPV456EnergyTotalsCountAgnostic:
    """pv_energy_today aggregate includes pv4-6 only when the model exposes them.

    pv1-3 daily energy live at regs 28/29/30 (DIV_10); pv4-6 daily at 223/226/229.
    """

    @staticmethod
    def _registers() -> dict[int, int]:
        return {
            28: 100,  # pv1_energy_today -> 10.0
            29: 200,  # pv2_energy_today -> 20.0
            30: 300,  # pv3_energy_today -> 30.0
            223: 100,  # epv4_day -> 10.0
            226: 110,  # epv5_day -> 11.0
            229: 120,  # epv6_day -> 12.0
        }

    def test_3string_total_excludes_pv4_6(self) -> None:
        energy = InverterEnergyData.from_modbus_registers(self._registers(), "EG4_HYBRID")
        # 10 + 20 + 30 = 60.0; pv4-6 are None and excluded.
        assert energy.pv_energy_today == 60.0

    def test_6string_total_includes_pv4_6(self) -> None:
        energy = InverterEnergyData.from_modbus_registers(
            self._registers(), "EG4_HYBRID", pv_string_count=6
        )
        # 10 + 20 + 30 + 10 + 11 + 12 = 93.0.
        assert energy.pv_energy_today == 93.0
