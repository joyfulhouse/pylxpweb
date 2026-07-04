"""Unit tests for the grid peak shaving register family (eg4-gfu5, eg4#328).

The family was located 2026-06-12 by READ-ONLY single-register cloud window
reads on an 18kPV and a FlexBOSS21 (both devices agree):

    206 = _12K_HOLD_GRID_PEAK_SHAVING_POWER   (PS1; deci-kW)
    207 = _12K_HOLD_GRID_PEAK_SHAVING_SOC     (%, raw 1:1)
    208 = _12K_HOLD_GRID_PEAK_SHAVING_VOLT    (decivolts)
    218 = _12K_HOLD_GRID_PEAK_SHAVING_SOC_2   (%, raw 1:1)
    219 = _12K_HOLD_GRID_PEAK_SHAVING_VOLT_2  (decivolts)
    232 = _12K_HOLD_GRID_PEAK_SHAVING_POWER_2 (PS2; deci-kW)

The power (206/232) and voltage (208/219) raw encodings are now VERIFIED
deci-units (pylxpweb#158 DoubleDoc wrote raw 41 -> 4.1 kW on the portal/LCD; a
2026-07-04 live cloud write of "12" read back "12" = raw 120; the SOC/volt
raw-vs-named cross-checks came from the 2026-06-12 sweep).  The whole family is
therefore mapped in REGISTER_TO_PARAM_KEYS for local reads, with the four
power/voltage members scaled to the cloud's engineering string by the transport
decode.  Register 231 (the old, WRONG PS1 mapping) stays unmapped.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb.client import LuxpowerClient
from pylxpweb.constants.registers import (
    LOCAL_PARAM_SCALE_DIV10,
    PARAM_KEY_TO_REGISTER,
    REGISTER_TO_PARAM_KEYS,
    format_deci_as_cloud_string,
    get_param_to_register_mapping,
)
from pylxpweb.devices.inverters.base import BaseInverter
from pylxpweb.devices.models import Entity
from pylxpweb.registers.inverter_holding import (
    BY_ADDRESS,
    BY_NAME,
    HoldingCategory,
    ScaleFactor,
)

PEAK_SHAVING_FAMILY: dict[str, tuple[int, str]] = {
    "grid_peak_shaving_power": (206, "_12K_HOLD_GRID_PEAK_SHAVING_POWER"),
    "grid_peak_shaving_soc": (207, "_12K_HOLD_GRID_PEAK_SHAVING_SOC"),
    "grid_peak_shaving_volt": (208, "_12K_HOLD_GRID_PEAK_SHAVING_VOLT"),
    "grid_peak_shaving_soc_2": (218, "_12K_HOLD_GRID_PEAK_SHAVING_SOC_2"),
    "grid_peak_shaving_volt_2": (219, "_12K_HOLD_GRID_PEAK_SHAVING_VOLT_2"),
    "grid_peak_shaving_power_2": (232, "_12K_HOLD_GRID_PEAK_SHAVING_POWER_2"),
}

# The four members carrying a DIV_10 raw encoding (power in deci-kW, voltage in
# decivolts). The two SOC members are raw 1:1 and are deliberately excluded.
SCALED_MEMBERS = frozenset(
    {
        "_12K_HOLD_GRID_PEAK_SHAVING_POWER",
        "_12K_HOLD_GRID_PEAK_SHAVING_POWER_2",
        "_12K_HOLD_GRID_PEAK_SHAVING_VOLT",
        "_12K_HOLD_GRID_PEAK_SHAVING_VOLT_2",
    }
)


class TestPeakShavingCanonicalRows:
    """Canonical table rows match the 2026-06-12 sweep evidence."""

    def test_family_addresses_and_api_keys(self) -> None:
        for canonical, (address, api_key) in PEAK_SHAVING_FAMILY.items():
            reg = BY_NAME[canonical]
            assert reg.address == address, (
                f"{canonical}: canonical table says reg {reg.address}, "
                f"sweep evidence says reg {address}"
            )
            assert reg.api_param_key == api_key
            assert reg.bit_position is None  # value registers, not bitfields
            assert reg.category == HoldingCategory.GRID

    def test_ps1_is_not_at_231(self) -> None:
        """The old 231 mapping was disproved: (231,1) names nothing on either
        inverter while (206,1) names PS1 on both."""
        reg = BY_NAME["grid_peak_shaving_power"]
        assert reg.address == 206
        assert reg.address != 231

    def test_ps1_is_single_register_not_32_bit(self) -> None:
        """(232,1) names PS2 — register 232 is NOT a PS1 high word."""
        reg = BY_NAME["grid_peak_shaving_power"]
        assert reg.bit_width == 16

    def test_power_members_use_cloud_kw_range(self) -> None:
        for canonical in ("grid_peak_shaving_power", "grid_peak_shaving_power_2"):
            reg = BY_NAME[canonical]
            assert reg.unit == "kW"
            assert reg.min_value == 0
            assert reg.max_value == 25.5

    def test_volt_members_are_decivolt_scaled(self) -> None:
        """Raw-vs-named cross-check in the sweep responses: raw 520 -> '52' V
        on both devices, for both time periods."""
        for canonical in ("grid_peak_shaving_volt", "grid_peak_shaving_volt_2"):
            reg = BY_NAME[canonical]
            assert reg.scale == ScaleFactor.DIV_10
            assert reg.unit == "V"

    def test_soc_members_are_unscaled_percent(self) -> None:
        """Raw-vs-named cross-check: raw 80 -> '80' and raw 50 -> '50'."""
        for canonical in ("grid_peak_shaving_soc", "grid_peak_shaving_soc_2"):
            reg = BY_NAME[canonical]
            assert reg.scale == ScaleFactor.NONE
            assert reg.unit == "%"

    def test_register_231_has_no_canonical_row(self) -> None:
        """231 is a real but unknown field (even-quantized writes, raw 0);
        it must stay unmapped until identified."""
        assert 231 not in BY_ADDRESS


class TestPeakShavingTransportMap:
    """The family is now mapped for local reads; register 231 stays out."""

    def test_register_231_not_in_transport_map(self) -> None:
        assert 231 not in REGISTER_TO_PARAM_KEYS

    def test_family_registers_named_in_transport_map(self) -> None:
        for _canonical, (address, api_key) in PEAK_SHAVING_FAMILY.items():
            assert REGISTER_TO_PARAM_KEYS.get(address) == [api_key]

    def test_family_api_keys_locally_resolvable(self) -> None:
        """Now that the encodings are verified, the family resolves for local
        name-writes (the reverse map is populated)."""
        param_to_reg = get_param_to_register_mapping()
        for _canonical, (address, api_key) in PEAK_SHAVING_FAMILY.items():
            assert param_to_reg[api_key] == address
            assert PARAM_KEY_TO_REGISTER[api_key] == address

    def test_scaled_members_are_the_power_and_volt_registers(self) -> None:
        assert LOCAL_PARAM_SCALE_DIV10 == SCALED_MEMBERS
        # SOC members must NOT be scaled (raw 1:1).
        assert "_12K_HOLD_GRID_PEAK_SHAVING_SOC" not in LOCAL_PARAM_SCALE_DIV10
        assert "_12K_HOLD_GRID_PEAK_SHAVING_SOC_2" not in LOCAL_PARAM_SCALE_DIV10


class TestFormatDeciAsCloudString:
    """Cloud renders deci-units as a decimal string with no trailing '.0'."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (120, "12"),  # 12.0 kW -> "12"
            (41, "4.1"),  # 4.1 kW
            (520, "52"),  # 52.0 V
            (0, "0"),
            (255, "25.5"),  # max power
            (5, "0.5"),
        ],
    )
    def test_formatting(self, raw: int, expected: str) -> None:
        assert format_deci_as_cloud_string(raw) == expected


class _FakeParamTransport:
    """Minimal transport exercising the shared read/write_named_parameters
    decode via BaseTransport, backed by an in-memory raw register store."""

    def __init__(self, registers: dict[int, int]) -> None:
        self._store = dict(registers)
        # BaseTransport family resolution reads this attribute; EG4_HYBRID uses
        # the base (18kPV) register map that carries the peak-shaving family.
        self._inverter_family = "EG4_HYBRID"

    async def read_parameters(self, start_address: int, count: int) -> dict[int, int]:
        return {
            addr: self._store.get(addr, 0)
            for addr in range(start_address, start_address + count)
            if addr in self._store
        }

    async def write_parameters(self, parameters: dict[int, int]) -> bool:
        self._store.update(parameters)
        return True


def _decode_transport(registers: dict[int, int]) -> _FakeParamTransport:
    from pylxpweb.transports.protocol import BaseTransport

    class _T(_FakeParamTransport, BaseTransport):
        def __init__(self, regs: dict[int, int]) -> None:
            BaseTransport.__init__(self, "4512670118")
            _FakeParamTransport.__init__(self, regs)

    return _T(registers)


class TestLocalReadScaling:
    """read_named_parameters surfaces the family scaled to cloud units."""

    async def test_power_and_volt_scaled_soc_passthrough(self) -> None:
        transport = _decode_transport(
            {
                206: 120,  # PS1 power raw -> "12" kW
                207: 80,  # PS1 SOC raw 1:1 -> 80
                208: 520,  # PS1 volt raw -> "52" V
                218: 50,  # PS2 SOC raw 1:1 -> 50
                219: 512,  # PS2 volt raw -> "51.2" V
                232: 41,  # PS2 power raw -> "4.1" kW
            }
        )
        params = await transport.read_named_parameters(206, 27)

        assert params["_12K_HOLD_GRID_PEAK_SHAVING_POWER"] == "12"
        assert params["_12K_HOLD_GRID_PEAK_SHAVING_VOLT"] == "52"
        assert params["_12K_HOLD_GRID_PEAK_SHAVING_POWER_2"] == "4.1"
        assert params["_12K_HOLD_GRID_PEAK_SHAVING_VOLT_2"] == "51.2"
        # SOC members are raw 1:1 — unchanged integers, matching every other
        # unscaled single-value register in the decode.
        assert params["_12K_HOLD_GRID_PEAK_SHAVING_SOC"] == 80
        assert params["_12K_HOLD_GRID_PEAK_SHAVING_SOC_2"] == 50

    async def test_scaled_read_feeds_float_consumers(self) -> None:
        transport = _decode_transport({206: 41})
        params = await transport.read_named_parameters(206, 1)
        # The property does float(value); the scaled string must round-trip.
        assert float(params["_12K_HOLD_GRID_PEAK_SHAVING_POWER"]) == 4.1


class TestLocalWriteScaling:
    """write_named_parameters inverse-scales the family to raw deci-units."""

    async def test_named_write_converts_kw_to_raw(self) -> None:
        transport = _decode_transport({206: 0})
        await transport.write_named_parameters({"_12K_HOLD_GRID_PEAK_SHAVING_POWER": 12.0})
        assert transport._store[206] == 120  # 12.0 kW -> raw 120

    async def test_named_write_fractional_kw(self) -> None:
        transport = _decode_transport({232: 0})
        await transport.write_named_parameters({"_12K_HOLD_GRID_PEAK_SHAVING_POWER_2": 4.1})
        assert transport._store[232] == 41

    async def test_named_write_volt(self) -> None:
        transport = _decode_transport({208: 0})
        await transport.write_named_parameters({"_12K_HOLD_GRID_PEAK_SHAVING_VOLT": 52})
        assert transport._store[208] == 520

    async def test_write_read_round_trip(self) -> None:
        transport = _decode_transport({206: 0})
        await transport.write_named_parameters({"_12K_HOLD_GRID_PEAK_SHAVING_POWER": 7.0})
        params = await transport.read_named_parameters(206, 1)
        assert params["_12K_HOLD_GRID_PEAK_SHAVING_POWER"] == "7"


class _PropertyTestInverter(BaseInverter):
    """Concrete BaseInverter for property / setter unit tests."""

    def to_entities(self) -> list[Entity]:
        return []


def _make_inverter(client: object | None = None) -> _PropertyTestInverter:
    return _PropertyTestInverter(
        client=client if client is not None else Mock(spec=LuxpowerClient),
        serial_number="4512670118",
        model="18KPV",
    )


class TestGridPeakShavingPowerLimitProperty:
    """grid_peak_shaving_power_limit must never fabricate a 0.0 reading."""

    def test_none_when_parameters_not_loaded(self) -> None:
        inverter = _make_inverter()
        inverter.parameters = None
        assert inverter.grid_peak_shaving_power_limit is None

    def test_none_when_key_absent(self) -> None:
        """A partial local read that missed reg 206 leaves the key absent."""
        inverter = _make_inverter()
        inverter.parameters = {"HOLD_SYSTEM_CHARGE_SOC_LIMIT": 80, "206": 55}
        assert inverter.grid_peak_shaving_power_limit is None

    def test_value_when_cloud_named_key_present(self) -> None:
        inverter = _make_inverter()
        inverter.parameters = {"_12K_HOLD_GRID_PEAK_SHAVING_POWER": "7.0"}
        assert inverter.grid_peak_shaving_power_limit == 7.0

    def test_value_from_scaled_local_read(self) -> None:
        """The transport decode feeds the property the cloud-equivalent kW
        string (raw 120 -> "12"); float() yields the correct kW."""
        inverter = _make_inverter()
        inverter.parameters = {"_12K_HOLD_GRID_PEAK_SHAVING_POWER": "12"}
        assert inverter.grid_peak_shaving_power_limit == 12.0

    def test_real_zero_setpoint_still_reads_zero(self) -> None:
        """An actual cloud-reported 0 remains 0.0 — only key ABSENCE is None."""
        inverter = _make_inverter()
        inverter.parameters = {"_12K_HOLD_GRID_PEAK_SHAVING_POWER": "0"}
        assert inverter.grid_peak_shaving_power_limit == 0.0


class TestSetGridPeakShavingPower:
    """The setter writes raw locally when a transport is up, else cloud."""

    async def test_out_of_range_raises(self) -> None:
        inverter = _make_inverter()
        with pytest.raises(ValueError, match="between 0.0 and 25.5"):
            await inverter.set_grid_peak_shaving_power(30.0)

    async def test_local_write_uses_raw_register(self) -> None:
        """LOCAL/HYBRID: write raw deci-kW to register 206, no cloud call."""
        client = Mock(spec=LuxpowerClient)
        client.api = Mock()
        client.api.control = Mock()
        client.api.control.write_parameter = AsyncMock()
        inverter = _make_inverter(client=client)

        transport = Mock()
        transport.transport_type = "modbus"
        inverter._transport = transport
        inverter.write_transport_register = AsyncMock(return_value=True)
        # A fresh inverter has 0 consecutive failures, so transport_link_down
        # is False (link up).
        assert inverter.transport_link_down is False

        assert await inverter.set_grid_peak_shaving_power(12.0) is True
        inverter.write_transport_register.assert_awaited_once_with(206, 120)
        client.api.control.write_parameter.assert_not_called()

    async def test_cloud_fallback_when_no_transport(self) -> None:
        client = Mock(spec=LuxpowerClient)
        client.api = Mock()
        client.api.control = Mock()
        result = Mock()
        result.success = True
        client.api.control.write_parameter = AsyncMock(return_value=result)
        inverter = _make_inverter(client=client)
        inverter._transport = None

        assert await inverter.set_grid_peak_shaving_power(7.0) is True
        client.api.control.write_parameter.assert_awaited_once_with(
            "4512670118", "_12K_HOLD_GRID_PEAK_SHAVING_POWER", "7.0"
        )

    async def test_local_failure_falls_back_to_cloud(self) -> None:
        client = Mock(spec=LuxpowerClient)
        client.api = Mock()
        client.api.control = Mock()
        result = Mock()
        result.success = True
        client.api.control.write_parameter = AsyncMock(return_value=result)
        inverter = _make_inverter(client=client)

        transport = Mock()
        transport.transport_type = "modbus"
        inverter._transport = transport
        inverter.write_transport_register = AsyncMock(return_value=False)

        assert await inverter.set_grid_peak_shaving_power(7.0) is True
        client.api.control.write_parameter.assert_awaited_once()
