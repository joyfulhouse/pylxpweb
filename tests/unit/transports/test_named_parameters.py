"""Tests for named parameter methods (read_named_parameters, write_named_parameters)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.devices.inverters._features import InverterFamily
from pylxpweb.models import SuccessResponse
from pylxpweb.transports.http import HTTPTransport
from pylxpweb.transports.hybrid import HybridTransport
from pylxpweb.transports.modbus import ModbusTransport

# The two register-110 values the 18kPV reported either side of a
# take-load-together toggle driven through EG4's OWN cloud functionControl
# (2026-08-01, serial 45XXXXXX18, pylxpweb #242). Their XOR is exactly bit 10,
# which is the entire evidence for the mapping this module pins. Defined once
# so a fixture cannot be corrupted in one test and stay consistent elsewhere.
CAPTURE_BASELINE_RAW = 0x0420  # bits 5 + 10 — flag ON
CAPTURE_TOGGLED_OFF_RAW = 0x0020  # bit 5 only — flag OFF


class TestReadNamedParametersModbus:
    """Tests for Modbus transport read_named_parameters."""

    @pytest.fixture
    def mock_modbus_transport(self) -> ModbusTransport:
        """Create a ModbusTransport with mocked read_parameters."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )
        transport._connected = True
        return transport

    @pytest.mark.asyncio
    async def test_read_named_parameters_single_register(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test reading a single-param register returns named parameter."""
        # Mock read_parameters to return register 66 (HOLD_AC_CHARGE_POWER_CMD)
        mock_modbus_transport.read_parameters = AsyncMock(return_value={66: 50})

        result = await mock_modbus_transport.read_named_parameters(66, 1)

        assert "HOLD_AC_CHARGE_POWER_CMD" in result
        assert result["HOLD_AC_CHARGE_POWER_CMD"] == 50

    @pytest.mark.asyncio
    async def test_read_named_parameters_bit_field_register(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test reading register 21 expands bit fields to individual booleans."""
        # Register 21 value with bits 0 and 7 set (FUNC_EPS_EN, FUNC_AC_CHARGE)
        # Bit 0 = 1, Bit 7 = 128 = 0x81
        mock_modbus_transport.read_parameters = AsyncMock(return_value={21: 0x81})

        result = await mock_modbus_transport.read_named_parameters(21, 1)

        # Bit 0 should be True (FUNC_EPS_EN)
        assert result.get("FUNC_EPS_EN") is True
        # Bit 7 should be True (FUNC_AC_CHARGE)
        assert result.get("FUNC_AC_CHARGE") is True
        # Bit 1 should be False (FUNC_OVF_LOAD_DERATE_EN)
        assert result.get("FUNC_OVF_LOAD_DERATE_EN") is False

    @pytest.mark.asyncio
    async def test_read_ac_coupling_both_polarities_preserves_sibling_decode(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Register 179 bit 11 decodes under the cloud parameter name.

        The two raw words differ by exactly bit 11, so every sibling must
        decode identically while AC coupling changes polarity.
        """
        mock_modbus_transport.read_parameters = AsyncMock(
            side_effect=[{179: 0xAA55}, {179: 0xA255}]
        )

        enabled = await mock_modbus_transport.read_named_parameters(179, 1)
        disabled = await mock_modbus_transport.read_named_parameters(179, 1)

        assert enabled["FUNC_AC_COUPLING_FUNCTION"] is True
        assert disabled["FUNC_AC_COUPLING_FUNCTION"] is False
        assert {
            key: value for key, value in enabled.items() if key != "FUNC_AC_COUPLING_FUNCTION"
        } == {key: value for key, value in disabled.items() if key != "FUNC_AC_COUPLING_FUNCTION"}

    @pytest.mark.asyncio
    async def test_read_named_parameters_unknown_register(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test reading unmapped register uses address as key."""
        # Register 999 is not in the mapping
        mock_modbus_transport.read_parameters = AsyncMock(return_value={999: 12345})

        result = await mock_modbus_transport.read_named_parameters(999, 1)

        assert result.get("999") == 12345

    @pytest.mark.asyncio
    async def test_read_named_parameters_multiple_registers(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test reading multiple registers returns all named parameters."""
        mock_modbus_transport.read_parameters = AsyncMock(
            return_value={
                15: 1,  # HOLD_COM_ADDR
                16: 0,  # HOLD_LANGUAGE
            }
        )

        result = await mock_modbus_transport.read_named_parameters(15, 2)

        assert result.get("HOLD_COM_ADDR") == 1
        assert result.get("HOLD_LANGUAGE") == 0

    @pytest.mark.asyncio
    async def test_read_named_parameters_forced_chg_power(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Register 74 (HOLD_FORCED_CHG_POWER_CMD) decodes to its named param.

        Reg 74 is the forced/PV charge power command in 100W units
        (0-150 = 0-15 kW), e.g. raw 120 -> 12.0 kW.
        """
        mock_modbus_transport.read_parameters = AsyncMock(return_value={74: 120})

        result = await mock_modbus_transport.read_named_parameters(74, 1)

        assert "HOLD_FORCED_CHG_POWER_CMD" in result
        assert result["HOLD_FORCED_CHG_POWER_CMD"] == 120

    @pytest.mark.asyncio
    async def test_read_named_parameters_ac_charge_end_soc(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Register 161 (HOLD_AC_CHARGE_END_BATTERY_SOC) decodes to its named
        param, raw 1:1 percent like its reg-160 window-start sibling.

        Regression: reg 161 was the only member of the AC-charge-window family
        missing from the local register map (eg4_web_monitor#331/#332).
        """
        mock_modbus_transport.read_parameters = AsyncMock(return_value={161: 85})

        result = await mock_modbus_transport.read_named_parameters(161, 1)

        assert "HOLD_AC_CHARGE_END_BATTERY_SOC" in result
        assert result["HOLD_AC_CHARGE_END_BATTERY_SOC"] == 85


class TestWriteNamedParametersModbus:
    """Tests for Modbus transport write_named_parameters."""

    @pytest.fixture
    def mock_modbus_transport(self) -> ModbusTransport:
        """Create a ModbusTransport with mocked write_parameters."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )
        transport._connected = True
        transport.read_parameters = AsyncMock(return_value={21: 0})
        transport.write_parameters = AsyncMock(return_value=True)
        return transport

    @pytest.mark.asyncio
    async def test_write_named_parameters_simple(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test writing a simple named parameter."""
        result = await mock_modbus_transport.write_named_parameters(
            {"HOLD_AC_CHARGE_POWER_CMD": 75}
        )

        assert result is True
        mock_modbus_transport.write_parameters.assert_called_once_with({66: 75})

    @pytest.mark.asyncio
    async def test_write_named_parameters_forced_chg_power(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Writing HOLD_FORCED_CHG_POWER_CMD resolves to register 74.

        100W units: 1 kW -> raw 10. Local path must be able to address reg 74
        by name (regression: it was missing from the local register map, which
        forced the integration onto the wrong register 64).
        """
        result = await mock_modbus_transport.write_named_parameters(
            {"HOLD_FORCED_CHG_POWER_CMD": 10}
        )

        assert result is True
        mock_modbus_transport.write_parameters.assert_called_once_with({74: 10})

    @pytest.mark.asyncio
    async def test_write_named_parameters_ac_charge_end_soc(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Writing HOLD_AC_CHARGE_END_BATTERY_SOC resolves to register 161.

        Symmetric raw 1:1 passthrough with the read path (SCALE_NONE), mirroring
        the reg-160 window-start sibling (eg4_web_monitor#331/#332).
        """
        result = await mock_modbus_transport.write_named_parameters(
            {"HOLD_AC_CHARGE_END_BATTERY_SOC": 85}
        )

        assert result is True
        mock_modbus_transport.write_parameters.assert_called_once_with({161: 85})

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("enabled", "current_word", "expected_word"),
        [
            (True, 0xA255, 0xAA55),
            (False, 0xAA55, 0xA255),
        ],
    )
    async def test_write_ac_coupling_rmw_preserves_every_sibling_bit(
        self,
        mock_modbus_transport: ModbusTransport,
        enabled: bool,
        current_word: int,
        expected_word: int,
    ) -> None:
        """The named write changes bit 11 and no other register-179 bit."""
        mock_modbus_transport.read_parameters = AsyncMock(return_value={179: current_word})

        result = await mock_modbus_transport.write_named_parameters(
            {"FUNC_AC_COUPLING_FUNCTION": enabled}
        )

        assert result is True
        mock_modbus_transport.write_parameters.assert_called_once_with({179: expected_word})
        written_word = mock_modbus_transport.write_parameters.call_args.args[0][179]
        assert written_word ^ current_word == 1 << 11
        sibling_mask = 0xFFFF ^ (1 << 11)
        assert written_word & sibling_mask == current_word & sibling_mask

    @pytest.mark.asyncio
    async def test_write_named_parameters_bit_field_single(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test writing a bit field parameter performs read-modify-write."""
        # Current value is 0, set FUNC_EPS_EN (bit 0) to True
        mock_modbus_transport.read_parameters = AsyncMock(return_value={21: 0})

        result = await mock_modbus_transport.write_named_parameters({"FUNC_EPS_EN": True})

        assert result is True
        # Should read register 21 first, then write with bit 0 set
        mock_modbus_transport.read_parameters.assert_called_once_with(21, 1)
        mock_modbus_transport.write_parameters.assert_called_once_with({21: 0x01})

    @pytest.mark.asyncio
    async def test_write_named_parameters_bit_field_preserve_others(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test bit field write preserves other bits."""
        # Current value has bit 7 set (FUNC_AC_CHARGE)
        mock_modbus_transport.read_parameters = AsyncMock(return_value={21: 0x80})

        # Set bit 0 (FUNC_EPS_EN) while preserving bit 7
        result = await mock_modbus_transport.write_named_parameters({"FUNC_EPS_EN": True})

        assert result is True
        # Should have both bit 0 and bit 7 set: 0x81
        mock_modbus_transport.write_parameters.assert_called_once_with({21: 0x81})

    @pytest.mark.asyncio
    async def test_write_named_parameters_bit_field_clear(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test clearing a bit field parameter."""
        # Current value has bit 0 set
        mock_modbus_transport.read_parameters = AsyncMock(return_value={21: 0x01})

        result = await mock_modbus_transport.write_named_parameters({"FUNC_EPS_EN": False})

        assert result is True
        # Should clear bit 0: 0x00
        mock_modbus_transport.write_parameters.assert_called_once_with({21: 0x00})

    @pytest.mark.asyncio
    async def test_write_named_parameters_pv_start_voltage(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test writing HOLD_START_PV_VOLT writes register 22 as scalar."""
        result = await mock_modbus_transport.write_named_parameters({"HOLD_START_PV_VOLT": 1500})

        assert result is True
        mock_modbus_transport.write_parameters.assert_called_once_with({22: 1500})

    @pytest.mark.asyncio
    async def test_write_named_parameters_unknown_raises(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test writing unknown parameter raises ValueError."""
        with pytest.raises(ValueError, match="Unknown parameter name"):
            await mock_modbus_transport.write_named_parameters({"UNKNOWN_PARAM": 123})


class TestRegister120CompoundFields:
    """Register 120 is one bit, two compound fields, then two sparse bits."""

    @pytest.fixture
    def mock_modbus_transport(self) -> ModbusTransport:
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )
        transport._connected = True
        transport.read_parameters = AsyncMock(return_value={120: 0})
        transport.write_parameters = AsyncMock(return_value=True)
        return transport

    @pytest.mark.asyncio
    async def test_read_field_matrix_uses_documented_offsets_and_widths(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Every low-byte combination decodes without overlapping fake bits."""
        for half_hour in (False, True):
            for ac_charge_type in range(8):
                for discharge_type in range(4):
                    for on_grid_eod in (False, True):
                        for generator_charge in (False, True):
                            raw = (
                                0xA500
                                | int(half_hour)
                                | (ac_charge_type << 1)
                                | (discharge_type << 4)
                                | (int(on_grid_eod) << 6)
                                | (int(generator_charge) << 7)
                            )
                            mock_modbus_transport.read_parameters = AsyncMock(
                                return_value={120: raw}
                            )

                            result = await mock_modbus_transport.read_named_parameters(120, 1)

                            assert result == {
                                "FUNC_HALF_HOUR_AC_CHG_START_EN": half_hour,
                                "BIT_AC_CHARGE_TYPE": ac_charge_type,
                                "BIT_DISCHG_CONTROL_TYPE": discharge_type,
                                "BIT_ON_GRID_EOD_TYPE": on_grid_eod,
                                "BIT_GENERATOR_CHARGE_TYPE": generator_charge,
                            }

    @pytest.mark.asyncio
    async def test_write_all_fields_preserves_unmapped_upper_bits(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """A combined RMW changes only H120's documented low-byte fields."""
        mock_modbus_transport.read_parameters = AsyncMock(return_value={120: 0xA555})

        result = await mock_modbus_transport.write_named_parameters(
            {
                "FUNC_HALF_HOUR_AC_CHG_START_EN": True,
                "BIT_AC_CHARGE_TYPE": 5,
                "BIT_DISCHG_CONTROL_TYPE": 2,
                "BIT_ON_GRID_EOD_TYPE": False,
                "BIT_GENERATOR_CHARGE_TYPE": True,
            }
        )

        assert result is True
        mock_modbus_transport.write_parameters.assert_awaited_once_with({120: 0xA5AB})

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("parameter", "value"),
        [
            ("BIT_AC_CHARGE_TYPE", -1),
            ("BIT_AC_CHARGE_TYPE", 8),
            ("BIT_DISCHG_CONTROL_TYPE", -1),
            ("BIT_DISCHG_CONTROL_TYPE", 4),
        ],
    )
    async def test_write_compound_field_rejects_values_outside_width(
        self,
        mock_modbus_transport: ModbusTransport,
        parameter: str,
        value: int,
    ) -> None:
        mock_modbus_transport.read_parameters = AsyncMock(return_value={120: 0})

        with pytest.raises(ValueError, match="out of range"):
            await mock_modbus_transport.write_named_parameters({parameter: value})

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "unsupported_parameter",
        [
            "FUNC_SNA_BAT_DISCHARGE_CONTROL",
            "FUNC_PHASE_INDEPEND_COMPENSATE_EN",
        ],
    )
    async def test_overlapping_legacy_names_are_not_locally_writable(
        self,
        mock_modbus_transport: ModbusTransport,
        unsupported_parameter: str,
    ) -> None:
        """Names that overlap ACChargeType bits must not imply safe local writes."""
        with pytest.raises(ValueError, match="Unknown parameter name"):
            await mock_modbus_transport.write_named_parameters({unsupported_parameter: True})


class TestReadNamedParametersHTTP:
    """Tests for HTTP transport read_named_parameters."""

    @pytest.fixture
    def mock_http_transport(self) -> HTTPTransport:
        """Create HTTPTransport with mocked client."""
        mock_client = MagicMock()
        transport = HTTPTransport(mock_client, "CE12345678")
        transport._connected = True
        return transport

    @pytest.mark.asyncio
    async def test_read_named_parameters_returns_server_response(
        self, mock_http_transport: HTTPTransport
    ) -> None:
        """Test HTTP transport returns server's named parameters directly."""
        # Mock the API response
        mock_response = MagicMock()
        mock_response.parameters = {
            "FUNC_EPS_EN": True,
            "FUNC_AC_CHARGE": False,
            "HOLD_START_PV_VOLT": 150,
        }
        mock_http_transport._client.api.control.read_parameters = AsyncMock(
            return_value=mock_response
        )

        result = await mock_http_transport.read_named_parameters(21, 1)

        assert result["FUNC_EPS_EN"] is True
        assert result["FUNC_AC_CHARGE"] is False
        assert result["HOLD_START_PV_VOLT"] == 150


class TestNamedParametersHybrid:
    """Tests for HybridTransport named parameter methods."""

    @pytest.fixture
    def mock_local_transport(self) -> MagicMock:
        """Create mock local transport."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.is_connected = True
        transport.capabilities = MagicMock()
        transport.read_named_parameters = AsyncMock(
            return_value={"FUNC_EPS_EN": True, "LOCAL": True}
        )
        transport.write_named_parameters = AsyncMock(return_value=True)
        return transport

    @pytest.fixture
    def mock_http_transport(self) -> MagicMock:
        """Create mock HTTP transport."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.is_connected = True
        transport.capabilities = MagicMock()
        transport.read_named_parameters = AsyncMock(
            return_value={"FUNC_EPS_EN": False, "HTTP": True}
        )
        transport.write_named_parameters = AsyncMock(return_value=True)
        return transport

    @pytest.mark.asyncio
    async def test_read_named_parameters_uses_local_first(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test HybridTransport uses local transport first."""
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        transport._connected = True

        result = await transport.read_named_parameters(21, 1)

        assert result.get("LOCAL") is True  # Came from local
        mock_local_transport.read_named_parameters.assert_called_once_with(21, 1)
        mock_http_transport.read_named_parameters.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_named_parameters_falls_back_to_http(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test HybridTransport falls back to HTTP on local failure."""
        from pylxpweb.transports.exceptions import TransportReadError

        mock_local_transport.read_named_parameters.side_effect = TransportReadError("Local failed")
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        transport._connected = True

        result = await transport.read_named_parameters(21, 1)

        assert result.get("HTTP") is True  # Came from HTTP
        mock_http_transport.read_named_parameters.assert_called_once_with(21, 1)

    @pytest.mark.asyncio
    async def test_write_named_parameters_uses_local_first(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test HybridTransport write uses local first."""
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        transport._connected = True

        result = await transport.write_named_parameters({"FUNC_EPS_EN": True})

        assert result is True
        mock_local_transport.write_named_parameters.assert_called_once_with({"FUNC_EPS_EN": True})
        mock_http_transport.write_named_parameters.assert_not_called()

    @pytest.mark.asyncio
    async def test_write_named_parameters_falls_back_to_http(
        self, mock_local_transport: MagicMock
    ) -> None:
        """Hybrid fallback exercises HTTPTransport's real named cloud write."""
        from pylxpweb.transports.exceptions import TransportWriteError

        mock_local_transport.write_named_parameters.side_effect = TransportWriteError(
            "Local failed"
        )
        client = MagicMock()
        client.api.control.control_function = AsyncMock(return_value=SuccessResponse(success=True))
        http_transport = HTTPTransport(client, "CE12345678")
        http_transport._connected = True
        transport = HybridTransport(mock_local_transport, http_transport)
        transport._connected = True

        result = await transport.write_named_parameters({"FUNC_EPS_EN": True})

        assert result is True
        client.api.control.control_function.assert_awaited_once_with(
            "CE12345678", "FUNC_EPS_EN", True
        )


class TestInverterFamilySupport:
    """Tests for inverter family-aware parameter mapping."""

    @pytest.fixture
    def modbus_transport_pv_series(self) -> ModbusTransport:
        """Create ModbusTransport with EG4_HYBRID family."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
            inverter_family=InverterFamily.EG4_HYBRID,
        )
        transport._connected = True
        return transport

    @pytest.fixture
    def modbus_transport_sna(self) -> ModbusTransport:
        """Create ModbusTransport with EG4_OFFGRID family."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
            inverter_family=InverterFamily.EG4_OFFGRID,
        )
        transport._connected = True
        return transport

    @pytest.fixture
    def modbus_transport_no_family(self) -> ModbusTransport:
        """Create ModbusTransport without specifying family."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )
        transport._connected = True
        return transport

    @pytest.mark.asyncio
    async def test_read_named_parameters_with_pv_series_family(
        self, modbus_transport_pv_series: ModbusTransport
    ) -> None:
        """Test reading named parameters with EG4_HYBRID family uses correct mapping."""
        # Register 66 = HOLD_AC_CHARGE_POWER_CMD in EG4_HYBRID
        modbus_transport_pv_series.read_parameters = AsyncMock(return_value={66: 75})

        result = await modbus_transport_pv_series.read_named_parameters(66, 1)

        assert "HOLD_AC_CHARGE_POWER_CMD" in result
        assert result["HOLD_AC_CHARGE_POWER_CMD"] == 75

    @pytest.mark.asyncio
    async def test_read_named_parameters_with_sna_family(
        self, modbus_transport_sna: ModbusTransport
    ) -> None:
        """Test reading named parameters with EG4_OFFGRID family uses correct mapping."""
        # Currently EG4_OFFGRID uses same mapping as EG4_HYBRID (fallback)
        # This test ensures family is passed through correctly
        modbus_transport_sna.read_parameters = AsyncMock(return_value={66: 50})

        result = await modbus_transport_sna.read_named_parameters(66, 1)

        assert "HOLD_AC_CHARGE_POWER_CMD" in result
        assert result["HOLD_AC_CHARGE_POWER_CMD"] == 50

    @pytest.mark.asyncio
    async def test_read_named_parameters_without_family_uses_default(
        self, modbus_transport_no_family: ModbusTransport
    ) -> None:
        """Test reading named parameters without family uses default mapping."""
        modbus_transport_no_family.read_parameters = AsyncMock(return_value={66: 100})

        result = await modbus_transport_no_family.read_named_parameters(66, 1)

        # Should still work with default mapping
        assert "HOLD_AC_CHARGE_POWER_CMD" in result
        assert result["HOLD_AC_CHARGE_POWER_CMD"] == 100

    @pytest.mark.asyncio
    async def test_write_named_parameters_with_family(
        self, modbus_transport_pv_series: ModbusTransport
    ) -> None:
        """Test writing named parameters uses family-specific mapping."""
        modbus_transport_pv_series.read_parameters = AsyncMock(return_value={21: 0})
        modbus_transport_pv_series.write_parameters = AsyncMock(return_value=True)

        result = await modbus_transport_pv_series.write_named_parameters({"FUNC_EPS_EN": True})

        assert result is True
        # FUNC_EPS_EN is bit 0 of register 21
        modbus_transport_pv_series.write_parameters.assert_called_once_with({21: 0x01})

    def test_get_inverter_family_returns_enum_value(
        self, modbus_transport_pv_series: ModbusTransport
    ) -> None:
        """Test _get_inverter_family returns string value from enum."""
        family = modbus_transport_pv_series._get_inverter_family()
        assert family == "EG4_HYBRID"

    def test_get_inverter_family_returns_none_when_not_set(
        self, modbus_transport_no_family: ModbusTransport
    ) -> None:
        """Test _get_inverter_family returns None when family not set."""
        family = modbus_transport_no_family._get_inverter_family()
        assert family is None


class TestMultiBitFieldReadWrite:
    """Tests for multi-bit field read/write (GridBOSS smart port modes)."""

    @pytest.fixture
    def mock_modbus_transport(self) -> ModbusTransport:
        """Create a ModbusTransport with mocked read/write for MIDBOX testing."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )
        transport._connected = True
        # Set device type to MIDBOX so register 20 maps to smart port modes
        transport._device_type = "MIDBOX"
        transport.write_parameters = AsyncMock(return_value=True)
        return transport

    @pytest.mark.asyncio
    async def test_read_multi_bit_fields_decodes_as_int(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test reading register 20 decodes 2-bit fields as integers."""
        # Register 20: port1=2 (AC Couple), port2=1 (Smart Load), port3=0, port4=0
        # Binary: 00_00_01_10 = 0x06
        mock_modbus_transport.read_parameters = AsyncMock(return_value={20: 0x06})

        result = await mock_modbus_transport.read_named_parameters(20, 1)

        assert result["BIT_MIDBOX_SP_MODE_1"] == 2  # bits 0-1 = 10 = 2
        assert result["BIT_MIDBOX_SP_MODE_2"] == 1  # bits 2-3 = 01 = 1
        assert result["BIT_MIDBOX_SP_MODE_3"] == 0  # bits 4-5 = 00 = 0
        assert result["BIT_MIDBOX_SP_MODE_4"] == 0  # bits 6-7 = 00 = 0

    @pytest.mark.asyncio
    async def test_read_multi_bit_fields_all_ports_ac_couple(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test reading all ports set to AC Couple (value 2 = 0b10)."""
        # All four ports = 2: 10_10_10_10 = 0xAA
        mock_modbus_transport.read_parameters = AsyncMock(return_value={20: 0xAA})

        result = await mock_modbus_transport.read_named_parameters(20, 1)

        assert result["BIT_MIDBOX_SP_MODE_1"] == 2
        assert result["BIT_MIDBOX_SP_MODE_2"] == 2
        assert result["BIT_MIDBOX_SP_MODE_3"] == 2
        assert result["BIT_MIDBOX_SP_MODE_4"] == 2

    @pytest.mark.asyncio
    async def test_write_multi_bit_field_single_port(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test writing a single smart port mode performs correct read-modify-write."""
        # Current: port1=1 (Smart Load), port2=0, port3=0, port4=0 = 0x01
        mock_modbus_transport.read_parameters = AsyncMock(return_value={20: 0x01})

        result = await mock_modbus_transport.write_named_parameters(
            {"BIT_MIDBOX_SP_MODE_1": 2}  # Change port 1 to AC Couple
        )

        assert result is True
        # Expected: port1=2 (bits 0-1 = 10), rest unchanged = 0x02
        mock_modbus_transport.write_parameters.assert_called_once_with({20: 0x02})

    @pytest.mark.asyncio
    async def test_write_multi_bit_field_preserves_other_ports(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test writing one port preserves other ports' values."""
        # Current: port1=2, port2=1, port3=0, port4=0 = 0b00_00_01_10 = 0x06
        mock_modbus_transport.read_parameters = AsyncMock(return_value={20: 0x06})

        # Set port 3 to Smart Load (1)
        result = await mock_modbus_transport.write_named_parameters({"BIT_MIDBOX_SP_MODE_3": 1})

        assert result is True
        # Expected: port1=2, port2=1, port3=1, port4=0 = 0b00_01_01_10 = 0x16
        mock_modbus_transport.write_parameters.assert_called_once_with({20: 0x16})

    @pytest.mark.asyncio
    async def test_write_multi_bit_field_clear_to_off(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test setting a port to Off (0) clears the bits."""
        # Current: all ports AC Couple (2) = 0xAA
        mock_modbus_transport.read_parameters = AsyncMock(return_value={20: 0xAA})

        # Set port 2 to Off (0)
        result = await mock_modbus_transport.write_named_parameters({"BIT_MIDBOX_SP_MODE_2": 0})

        assert result is True
        # Expected: port1=2, port2=0, port3=2, port4=2 = 0b10_10_00_10 = 0xA2
        mock_modbus_transport.write_parameters.assert_called_once_with({20: 0xA2})

    @pytest.mark.asyncio
    async def test_write_multiple_multi_bit_fields(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test writing multiple port modes in one call."""
        # Current: all off = 0x00
        mock_modbus_transport.read_parameters = AsyncMock(return_value={20: 0x00})

        result = await mock_modbus_transport.write_named_parameters(
            {
                "BIT_MIDBOX_SP_MODE_1": 2,  # AC Couple
                "BIT_MIDBOX_SP_MODE_4": 1,  # Smart Load
            }
        )

        assert result is True
        # Expected: port1=2, port2=0, port3=0, port4=1 = 0b01_00_00_10 = 0x42
        mock_modbus_transport.write_parameters.assert_called_once_with({20: 0x42})

    @pytest.mark.asyncio
    async def test_write_multi_bit_without_device_type_uses_param_detection(
        self,
    ) -> None:
        """Test that multi-bit fields work even without _device_type set.

        The _resolve_register_mappings method auto-detects MIDBOX params
        from the MIDBOX-only field layout.
        """
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )
        transport._connected = True
        transport.read_parameters = AsyncMock(return_value={20: 0x00})
        transport.write_parameters = AsyncMock(return_value=True)

        result = await transport.write_named_parameters({"BIT_MIDBOX_SP_MODE_1": 1})

        assert result is True
        # Port 1 = 1 (Smart Load) in bits 0-1 = 0x01
        transport.write_parameters.assert_called_once_with({20: 0x01})

    @pytest.mark.asyncio
    async def test_write_multi_bit_field_rejects_out_of_range(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test writing an out-of-range value raises ValueError."""
        mock_modbus_transport.read_parameters = AsyncMock(return_value={20: 0x00})

        # Value 5 exceeds 2-bit max (0-3)
        with pytest.raises(ValueError, match="out of range"):
            await mock_modbus_transport.write_named_parameters({"BIT_MIDBOX_SP_MODE_1": 5})

    @pytest.mark.asyncio
    async def test_write_multi_bit_field_rejects_negative(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test writing a negative value raises ValueError."""
        mock_modbus_transport.read_parameters = AsyncMock(return_value={20: 0x00})

        with pytest.raises(ValueError, match="out of range"):
            await mock_modbus_transport.write_named_parameters({"BIT_MIDBOX_SP_MODE_2": -1})


class TestStandardBitFieldsUnchanged:
    """Verify standard 1-bit fields still work after multi-bit support."""

    @pytest.fixture
    def mock_modbus_transport(self) -> ModbusTransport:
        """Create a ModbusTransport with standard config."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )
        transport._connected = True
        transport.write_parameters = AsyncMock(return_value=True)
        return transport

    @pytest.mark.asyncio
    async def test_standard_bit_field_read_still_returns_bool(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test register 21 still returns booleans for standard bit fields."""
        mock_modbus_transport.read_parameters = AsyncMock(return_value={21: 0x81})

        result = await mock_modbus_transport.read_named_parameters(21, 1)

        # Standard 1-bit fields should be bool, not int
        assert result["FUNC_EPS_EN"] is True
        assert isinstance(result["FUNC_EPS_EN"], bool)
        assert result["FUNC_AC_CHARGE"] is True
        assert result["FUNC_OVF_LOAD_DERATE_EN"] is False

    @pytest.mark.asyncio
    async def test_standard_bit_field_write_still_works(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test standard 1-bit field write is not affected by multi-bit support."""
        mock_modbus_transport.read_parameters = AsyncMock(return_value={21: 0x80})

        await mock_modbus_transport.write_named_parameters({"FUNC_EPS_EN": True})

        mock_modbus_transport.write_parameters.assert_called_once_with({21: 0x81})


class TestRegisterMappingFunctions:
    """Tests for the register mapping helper functions."""

    def test_get_register_to_param_mapping_returns_dict(self) -> None:
        """Test get_register_to_param_mapping returns a dictionary."""
        from pylxpweb.constants.registers import get_register_to_param_mapping

        mapping = get_register_to_param_mapping()
        assert isinstance(mapping, dict)
        assert len(mapping) > 0

    def test_get_register_to_param_mapping_with_family(self) -> None:
        """Test get_register_to_param_mapping accepts family parameter."""
        from pylxpweb.constants.registers import get_register_to_param_mapping

        mapping_eg4_hybrid = get_register_to_param_mapping("EG4_HYBRID")
        mapping_eg4_offgrid = get_register_to_param_mapping("EG4_OFFGRID")
        mapping_none = get_register_to_param_mapping(None)

        # Hybrid and the no-family default share the 18kPV mapping.
        assert mapping_eg4_hybrid == mapping_none
        # Since eg4_web_monitor #476 pinned green at bit 14 on 18kPV (the
        # same position SNA evidence + lxp_modbus already indicated),
        # register 110 is one lineage-wide layout — EG4_OFFGRID no longer
        # diverges from the base mapping.
        assert mapping_eg4_offgrid == mapping_none

    def test_get_param_to_register_mapping_returns_dict(self) -> None:
        """Test get_param_to_register_mapping returns reverse mapping."""
        from pylxpweb.constants.registers import get_param_to_register_mapping

        mapping = get_param_to_register_mapping()
        assert isinstance(mapping, dict)
        assert len(mapping) > 0
        # Check a known parameter
        assert mapping.get("HOLD_AC_CHARGE_POWER_CMD") == 66
        assert mapping.get("FUNC_EPS_EN") == 21

    def test_get_param_to_register_mapping_includes_pv_start_voltage(self) -> None:
        """Test HOLD_START_PV_VOLT maps to register 22."""
        from pylxpweb.constants.registers import get_param_to_register_mapping

        mapping = get_param_to_register_mapping()
        assert mapping.get("HOLD_START_PV_VOLT") == 22

    def test_get_param_to_register_mapping_with_family(self) -> None:
        """Test get_param_to_register_mapping accepts family parameter."""
        from pylxpweb.constants.registers import get_param_to_register_mapping

        mapping = get_param_to_register_mapping("EG4_HYBRID")
        assert "HOLD_AC_CHARGE_POWER_CMD" in mapping
        assert "FUNC_EPS_EN" in mapping

    def test_get_register_to_param_mapping_midbox(self) -> None:
        """Test MIDBOX device_type returns GridBOSS-specific mapping."""
        from pylxpweb.constants.registers import get_register_to_param_mapping

        mapping = get_register_to_param_mapping(device_type="MIDBOX")
        assert 20 in mapping
        assert "BIT_MIDBOX_SP_MODE_1" in mapping[20]
        assert "BIT_MIDBOX_SP_MODE_4" in mapping[20]
        # Should NOT contain inverter registers
        assert 21 not in mapping

    def test_get_param_to_register_mapping_midbox(self) -> None:
        """Test MIDBOX device_type returns GridBOSS param-to-register mapping."""
        from pylxpweb.constants.registers import get_param_to_register_mapping

        mapping = get_param_to_register_mapping(device_type="MIDBOX")
        assert mapping["BIT_MIDBOX_SP_MODE_1"] == 20
        assert mapping["BIT_MIDBOX_SP_MODE_2"] == 20
        assert mapping["BIT_MIDBOX_SP_MODE_3"] == 20
        assert mapping["BIT_MIDBOX_SP_MODE_4"] == 20

    def test_midbox_register_20_does_not_conflict_with_inverter(self) -> None:
        """Test that inverter register 20 (HOLD_PV_INPUT_MODE) is separate from MIDBOX."""
        from pylxpweb.constants.registers import get_register_to_param_mapping

        inverter_mapping = get_register_to_param_mapping()
        midbox_mapping = get_register_to_param_mapping(device_type="MIDBOX")

        # Inverter register 20 = HOLD_PV_INPUT_MODE (scalar)
        assert inverter_mapping[20] == ["HOLD_PV_INPUT_MODE"]
        # MIDBOX register 20 = smart port modes (multi-bit)
        assert midbox_mapping[20][0] == "BIT_MIDBOX_SP_MODE_1"


class TestRegister110UnifiedLayout:
    """Register 110 lineage-wide bit layout (PR #220 + eg4_web_monitor #476).

    Hardware evidence:
    - 12000XP (SNA): raw reg 110 toggles 0x0080 <-> 0x8080 with Battery ECO
      (bit 15), and the stock SNA cloud decode reports FUNC_BUZZER_EN as
      the only set function while raw reads show only bit 7 set (PR #220).
    - 18kPV: cloud green-mode enable flips raw 1056 <-> 17440, a single
      bit-14 delta, with the EG4 cloud decode changing in lockstep
      (2026-07-21, eg4_web_monitor #476) — disproving the historic bit-8
      green mapping whose local writes landed in the PVCT-sample region.

    Both tested families match the lxp_modbus H_FUNCTION_ENABLE_3 layout,
    so hybrid and EG4_OFFGRID share one table.
    """

    @pytest.fixture
    def offgrid_transport(self) -> ModbusTransport:
        """ModbusTransport with EG4_OFFGRID family."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="5200000068",
            inverter_family=InverterFamily.EG4_OFFGRID,
        )
        transport._connected = True
        transport.write_parameters = AsyncMock(return_value=True)
        return transport

    @pytest.fixture
    def hybrid_transport(self) -> ModbusTransport:
        """ModbusTransport with EG4_HYBRID family (regression reference)."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
            inverter_family=InverterFamily.EG4_HYBRID,
        )
        transport._connected = True
        transport.write_parameters = AsyncMock(return_value=True)
        return transport

    # ------------------------------------------------------------------
    # Mapping-level checks
    # ------------------------------------------------------------------

    def test_register_110_layout(self) -> None:
        """Every family maps green to 14, ECO to 15, buzzer to 7, TLT to 10."""
        from pylxpweb.constants.registers import get_register_to_param_mapping

        for family in (None, "EG4_HYBRID", "EG4_OFFGRID", "LXP", "UNKNOWN"):
            layout = get_register_to_param_mapping(family)[110]

            assert len(layout) == 16
            assert layout.index("FUNC_GREEN_EN") == 14
            assert layout.index("FUNC_BATTERY_ECO_EN") == 15
            assert layout.index("FUNC_BUZZER_EN") == 7
            # Toggle-verified on an 18kPV and applied lineage-wide, same as
            # green at 14 — a per-family divergence has to be deliberate (#242).
            assert layout.index("FUNC_TAKE_LOAD_TOGETHER") == 10
            # Displaced/unproven 18kPV names are placeholders, not silent
            # reuse — a wrong slot writes an unrelated config bit (#476).
            assert layout[5] == "FUNC_110_BIT5"  # old TLT slot, disproven (#242)
            assert layout[6] == "FUNC_110_BIT6"
            assert layout[8] == "FUNC_110_BIT8"  # old green slot, disproven
            assert layout[9] == "FUNC_110_BIT9"  # old ECO slot
            assert layout[11] == "FUNC_110_BIT11"
            assert layout[12] == "FUNC_110_BIT12"
            assert layout[13] == "FUNC_110_BIT13"
            for removed in (
                "FUNC_GO_TO_OFFGRID",
                "BIT_WORKING_MODE",
                "BIT_PVCT_SAMPLE_TYPE",
                "BIT_PVCT_SAMPLE_RATIO",
                "BIT_CT_SAMPLE_RATIO",
            ):
                assert removed not in layout

    def test_register_110_canonical_registry_agrees_with_decode_table(self) -> None:
        """The canonical holding registry and the decode table must not drift.

        Register 110's bit positions live in two places: the transport decode
        list (REGISTER_110_PARAM_KEYS, indexed by bit) and the canonical
        HoldingRegisterDefinition rows. Nothing forces them to agree, so a
        position fix applied to only one — exactly what #242 and #476 each
        had to correct — would leave the two silently contradicting each
        other, with reads and writes disagreeing about the same flag.
        """
        from pylxpweb.constants.registers import get_register_to_param_mapping
        from pylxpweb.registers.inverter_holding import BY_ADDRESS

        layout = get_register_to_param_mapping()[110]

        definitions = [
            definition
            for definition in BY_ADDRESS.get(110, ())
            if definition.bit_position is not None
        ]
        assert definitions, "register 110 must have canonical bit definitions"

        for definition in definitions:
            assert definition.api_param_key is not None
            assert layout[definition.bit_position] == definition.api_param_key, (
                f"{definition.api_param_key} is bit {definition.bit_position} in the "
                f"canonical registry but bit {layout.index(definition.api_param_key)} "
                "in the decode table"
            )

        # The #242 result specifically, pinned by name rather than by scan.
        take_load_together = next(
            definition
            for definition in definitions
            if definition.api_param_key == "FUNC_TAKE_LOAD_TOGETHER"
        )
        assert take_load_together.address == 110
        assert take_load_together.bit_position == 10

    def test_register_110_agreed_low_bits_unchanged(self) -> None:
        """Bits 0-4 agree across all sources and stay identical.

        Bit 5 used to be in this set on the strength of EG4's decode naming
        TAKE_LOAD_TOGETHER; the #242 toggle capture moved that flag to bit 10
        and left 5 unidentified, so the agreed run now stops at 4.
        """
        from pylxpweb.constants.registers import get_register_to_param_mapping

        layout = get_register_to_param_mapping()[110]
        assert layout[:5] == [
            "FUNC_PV_GRID_OFF_EN",
            "FUNC_RUN_WITHOUT_GRID",
            "FUNC_MICRO_GRID_EN",
            "FUNC_BAT_SHARED",
            "FUNC_CHARGE_LAST",
        ]

    def test_offgrid_alias_is_the_shared_layout(self) -> None:
        """The back-compat OFFGRID export aliases the unified list."""
        from pylxpweb.constants.registers import (
            OFFGRID_REGISTER_110_PARAM_KEYS,
            REGISTER_110_PARAM_KEYS,
            REGISTER_TO_PARAM_KEYS,
        )

        assert OFFGRID_REGISTER_110_PARAM_KEYS is REGISTER_110_PARAM_KEYS
        assert REGISTER_TO_PARAM_KEYS[110] is REGISTER_110_PARAM_KEYS

    def test_offgrid_mapping_does_not_mutate_base_table(self) -> None:
        """The family getter returns a copy; the shared table stays intact."""
        from pylxpweb.constants.registers import (
            REGISTER_TO_PARAM_KEYS,
            get_register_to_param_mapping,
        )

        offgrid = get_register_to_param_mapping("EG4_OFFGRID")
        assert offgrid is not REGISTER_TO_PARAM_KEYS
        offgrid[9999] = ["FAKE_PARAM"]
        assert 9999 not in REGISTER_TO_PARAM_KEYS

        # The per-register lists must be copies too: a shallow dict() copy
        # shares them, so mutating one here would corrupt register 110's
        # layout process-wide for every family.
        original = list(REGISTER_TO_PARAM_KEYS[110])
        offgrid[110].append("FAKE_BIT")
        offgrid[110][0] = "CLOBBERED"
        assert REGISTER_TO_PARAM_KEYS[110] == original

    @pytest.mark.parametrize(
        ("family", "device_type"),
        [
            ("EG4_OFFGRID", None),
            ("EG4_HYBRID", None),
            ("LXP", None),
            ("UNKNOWN", None),
            (None, None),
            (None, "MIDBOX"),
        ],
        ids=["offgrid", "hybrid", "lxp", "unknown", "no-family", "midbox"],
    )
    def test_every_mapping_branch_returns_an_isolated_copy(
        self, family: str | None, device_type: str | None
    ) -> None:
        """No branch hands back the live module table (pylxpweb #245).

        Only EG4_OFFGRID used to copy; every other branch returned the
        shared dict AND its inner lists. Bit positions are list indices, so
        one caller mutating a returned list reorders bits process-wide for
        every subsequent read and write — #476's failure mode via another
        door.

        There are only three real branches (MIDBOX, EG4_OFFGRID, default),
        so the four default-family cases are deliberately redundant: they
        pin that no family string quietly acquires an override that skips
        the copy. Against the pre-fix code all six fail, but not all six
        for their own sake — the leaked table lets one case's mutation
        corrupt the next, which is the process-wide damage this guards.
        """
        from pylxpweb.constants.registers import (
            MIDBOX_REGISTER_TO_PARAM_KEYS,
            REGISTER_TO_PARAM_KEYS,
            get_register_to_param_mapping,
        )

        source = (
            MIDBOX_REGISTER_TO_PARAM_KEYS if device_type == "MIDBOX" else REGISTER_TO_PARAM_KEYS
        )
        before = {register: list(keys) for register, keys in source.items()}

        mapping = get_register_to_param_mapping(family, device_type=device_type)
        assert mapping is not source, "returned the live module dict"

        a_register = next(iter(mapping))
        mapping[a_register].append("FAKE_BIT")
        mapping[a_register].insert(0, "CLOBBERED")
        mapping[123456] = ["FAKE_REGISTER"]

        assert source == before, "caller mutation reached the module table"
        assert 123456 not in source

    def test_param_to_register_resolves_green_eco_buzzer(self) -> None:
        """Reverse mapping resolves the pinned bits to register 110."""
        from pylxpweb.constants.registers import get_param_to_register_mapping

        for family in (None, "EG4_OFFGRID"):
            mapping = get_param_to_register_mapping(family)
            assert mapping["FUNC_GREEN_EN"] == 110
            assert mapping["FUNC_BATTERY_ECO_EN"] == 110
            assert mapping["FUNC_BUZZER_EN"] == 110

    # ------------------------------------------------------------------
    # Write path (read-modify-write) — the PR #220 hardware scenario
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_offgrid_eco_enable_writes_bit_15(
        self, offgrid_transport: ModbusTransport
    ) -> None:
        """Enabling ECO from the stock state writes 0x0080 -> 0x8080."""
        offgrid_transport.read_parameters = AsyncMock(return_value={110: 0x0080})

        result = await offgrid_transport.write_named_parameters({"FUNC_BATTERY_ECO_EN": True})

        assert result is True
        offgrid_transport.write_parameters.assert_called_once_with({110: 0x8080})

    @pytest.mark.asyncio
    async def test_offgrid_eco_disable_writes_bit_15(
        self, offgrid_transport: ModbusTransport
    ) -> None:
        """Disabling ECO writes 0x8080 -> 0x0080 (buzzer bit preserved)."""
        offgrid_transport.read_parameters = AsyncMock(return_value={110: 0x8080})

        result = await offgrid_transport.write_named_parameters({"FUNC_BATTERY_ECO_EN": False})

        assert result is True
        offgrid_transport.write_parameters.assert_called_once_with({110: 0x0080})

    @pytest.mark.asyncio
    async def test_hybrid_eco_writes_bit_15(self, hybrid_transport: ModbusTransport) -> None:
        """EG4_HYBRID uses the lineage-wide ECO bit 15 (was the wrong 9)."""
        hybrid_transport.read_parameters = AsyncMock(return_value={110: 0x0000})

        result = await hybrid_transport.write_named_parameters({"FUNC_BATTERY_ECO_EN": True})

        assert result is True
        hybrid_transport.write_parameters.assert_called_once_with({110: 0x8000})

    @pytest.mark.asyncio
    async def test_offgrid_charge_last_unaffected(self, offgrid_transport: ModbusTransport) -> None:
        """Bit 4 (charge last) is in the agreed range and stays put."""
        offgrid_transport.read_parameters = AsyncMock(return_value={110: 0x0080})

        result = await offgrid_transport.write_named_parameters({"FUNC_CHARGE_LAST": True})

        assert result is True
        offgrid_transport.write_parameters.assert_called_once_with({110: 0x0090})

    @pytest.mark.asyncio
    async def test_hybrid_green_enable_writes_bit_14(
        self, hybrid_transport: ModbusTransport
    ) -> None:
        """#476 regression: the exact 18kPV hardware scenario, 1056 -> 17440.

        The cloud toggle test (2026-07-21) observed raw reg 110 go
        1056 -> 17440 when green mode was enabled; a local named write must
        produce the identical register value — NOT the historic bit-8 write
        (1056 -> 1312) that landed in the PVCT-sample region and left green
        mode unchanged (eg4_web_monitor #476/#194).
        """
        hybrid_transport.read_parameters = AsyncMock(return_value={110: 1056})

        result = await hybrid_transport.write_named_parameters({"FUNC_GREEN_EN": True})

        assert result is True
        hybrid_transport.write_parameters.assert_called_once_with({110: 17440})

    @pytest.mark.asyncio
    async def test_hybrid_green_disable_writes_bit_14(
        self, hybrid_transport: ModbusTransport
    ) -> None:
        """#476 regression, restore direction: 17440 -> 1056."""
        hybrid_transport.read_parameters = AsyncMock(return_value={110: 17440})

        result = await hybrid_transport.write_named_parameters({"FUNC_GREEN_EN": False})

        assert result is True
        hybrid_transport.write_parameters.assert_called_once_with({110: 1056})

    @pytest.mark.asyncio
    async def test_offgrid_green_write_targets_bit_14(
        self, offgrid_transport: ModbusTransport
    ) -> None:
        """Offgrid green writes hit bit 14, not the disproven bit 8.

        Two different prior behaviours converge here. On the base layout
        (18kPV and friends) green was mapped to bit 8, so the write went
        out and silently flipped the PVCT-sampling region. On the offgrid
        layout `FUNC_GREEN_EN` was absent entirely, so the write was
        rejected — fail-closed, cloud-routed by the HA integration. With
        bit 14 pinned by the 18kPV toggle test the layouts are unified and
        both paths write bit 14. Bit 8 must never be touched.
        """
        offgrid_transport.read_parameters = AsyncMock(return_value={110: 0x0080})

        result = await offgrid_transport.write_named_parameters({"FUNC_GREEN_EN": True})

        assert result is True
        offgrid_transport.write_parameters.assert_called_once_with({110: 0x4080})
        written = offgrid_transport.write_parameters.call_args[0][0][110]
        assert not written & (1 << 8), "bit 8 (old green slot) must stay untouched"

    @pytest.mark.asyncio
    async def test_take_load_together_writes_bit_10(
        self, offgrid_transport: ModbusTransport
    ) -> None:
        """Once settled, the flag is writable and lands on bit 10 (#242).

        This inverts the old disputed-write guard: the toggle capture proved
        the position, so the write is allowed — and it must go to bit 10 with
        read-modify-write leaving every sibling bit alone, including bit 5,
        which the capture showed is some other setting (lxp_modbus assigns
        it to a CT-sample-ratio field; unconfirmed here).
        """
        # The captured baseline: bits 5 and 10 set.
        offgrid_transport.read_parameters = AsyncMock(return_value={110: CAPTURE_BASELINE_RAW})

        result = await offgrid_transport.write_named_parameters({"FUNC_TAKE_LOAD_TOGETHER": False})

        assert result is True
        # Exactly the raw value the live capture produced when EG4's own
        # server cleared this flag: 0x0420 -> 0x0020.
        offgrid_transport.write_parameters.assert_called_once_with({110: CAPTURE_TOGGLED_OFF_RAW})
        written = offgrid_transport.write_parameters.call_args[0][0][110]
        assert written & (1 << 5), "bit 5 (a different, unidentified setting) must survive"

    @pytest.mark.asyncio
    async def test_disputed_write_guard_has_no_entries_but_still_works(
        self, offgrid_transport: ModbusTransport
    ) -> None:
        """The guard mechanism outlives the dispute that motivated it.

        DISPUTED_WRITE_BLOCKED_PARAMS is empty now that #242 is settled, but
        register 110 alone has produced two disputes, so the machinery stays.
        Pin that it is empty *and* that it would still bite, so a future
        "unused, delete it" cleanup has to argue with a failing test.
        """
        from pylxpweb.constants.registers import DISPUTED_WRITE_BLOCKED_PARAMS

        assert frozenset() == DISPUTED_WRITE_BLOCKED_PARAMS

        offgrid_transport.read_parameters = AsyncMock(return_value={110: CAPTURE_BASELINE_RAW})
        with (
            patch(
                "pylxpweb.constants.registers.DISPUTED_WRITE_BLOCKED_PARAMS",
                frozenset({"FUNC_TAKE_LOAD_TOGETHER"}),
            ),
            pytest.raises(ValueError, match="disagree"),
        ):
            await offgrid_transport.write_named_parameters({"FUNC_TAKE_LOAD_TOGETHER": False})

        offgrid_transport.write_parameters.assert_not_called()

    def test_capture_constants_match_the_recorded_evidence(self) -> None:
        """Pin the recorded numbers themselves, not just what they decode to.

        The decode assertions below are insensitive to small corruptions of the
        fixtures — 0x0421 still has bit 10 set and still has bit 5 set, so it
        decodes identically while no longer being the value the 18kPV actually
        reported. The PR claims byte-perfect evidence, so the bytes are pinned
        here: mutating a captured value fails CI instead of quietly
        invalidating the claim.
        """
        # As printed by the capture script on 2026-08-01 (18kPV 45XXXXXX18).
        assert CAPTURE_BASELINE_RAW == 1056
        assert CAPTURE_TOGGLED_OFF_RAW == 32
        # The whole argument in one line: EG4's own server clearing
        # take-load-together moved exactly one bit, and that bit is 10.
        assert CAPTURE_BASELINE_RAW ^ CAPTURE_TOGGLED_OFF_RAW == 1 << 10
        # ...and bit 5, the position we used to claim, did not move.
        assert CAPTURE_BASELINE_RAW & (1 << 5)
        assert CAPTURE_TOGGLED_OFF_RAW & (1 << 5)

    @pytest.mark.parametrize(
        ("raw", "expected_true_keys"),
        [
            # Captured baseline: flag on (bits 5 + 10 set).
            (CAPTURE_BASELINE_RAW, {"FUNC_110_BIT5", "FUNC_TAKE_LOAD_TOGETHER"}),
            # Captured after EG4 cleared it: only bit 5 left.
            (CAPTURE_TOGGLED_OFF_RAW, {"FUNC_110_BIT5"}),
        ],
    )
    @pytest.mark.asyncio
    async def test_take_load_together_capture_evidence(
        self,
        hybrid_transport: ModbusTransport,
        raw: int,
        expected_true_keys: set[str],
    ) -> None:
        """Pin the two raw values from the 2026-08-01 18kPV capture (#242).

        These are the actual register reads either side of a take-load-together
        toggle driven through EG4's own cloud functionControl. Under the old
        bit-5 mapping the second value decoded True — i.e. the decode could not
        see the change EG4 had just made.

        The assertion is on the EXACT set of set flags, not just this one key,
        so a corrupted fixture (an extra or missing bit) fails rather than
        decoding the same way by luck.
        """
        hybrid_transport.read_parameters = AsyncMock(return_value={110: raw})

        result = await hybrid_transport.read_named_parameters(110, 1)

        assert {key for key, value in result.items() if value is True} == expected_true_keys
        # Bit 5 is set in BOTH captures, so it cannot be this flag.
        assert result["FUNC_110_BIT5"] is True

    @pytest.mark.asyncio
    async def test_placeholder_bits_are_not_writable(
        self, offgrid_transport: ModbusTransport
    ) -> None:
        """Unverified bit placeholders decode but refuse to be written.

        Writing one would flip a device setting nobody has identified —
        exactly the #476 failure mode, under a new name.
        """
        offgrid_transport.read_parameters = AsyncMock(return_value={110: 0x0080})

        with pytest.raises(ValueError, match="placeholder"):
            await offgrid_transport.write_named_parameters({"FUNC_110_BIT8": True})

        offgrid_transport.write_parameters.assert_not_called()

    # ------------------------------------------------------------------
    # Read path (decode)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_offgrid_decode_eco_on(self, offgrid_transport: ModbusTransport) -> None:
        """Raw 0x8080 decodes as ECO on + buzzer on for offgrid."""
        offgrid_transport.read_parameters = AsyncMock(return_value={110: 0x8080})

        result = await offgrid_transport.read_named_parameters(110, 1)

        assert result["FUNC_BATTERY_ECO_EN"] is True
        assert result["FUNC_BUZZER_EN"] is True
        # Green now decodes from the pinned bit 14 on every family.
        assert result["FUNC_GREEN_EN"] is False

    @pytest.mark.asyncio
    async def test_offgrid_decode_eco_off(self, offgrid_transport: ModbusTransport) -> None:
        """Raw 0x0080 (stock 12000XP) decodes as buzzer-only for offgrid."""
        offgrid_transport.read_parameters = AsyncMock(return_value={110: 0x0080})

        result = await offgrid_transport.read_named_parameters(110, 1)

        assert result["FUNC_BATTERY_ECO_EN"] is False
        assert result["FUNC_BUZZER_EN"] is True

    @pytest.mark.asyncio
    async def test_hybrid_decode_green_on(self, hybrid_transport: ModbusTransport) -> None:
        """#476 regression: raw 17440 (green enabled on 18kPV) decodes green True.

        This is the exact register value observed on hardware with green
        mode on; the historic bit-8 decode read it as green OFF, so the
        HYBRID switch never reflected the real state.
        """
        hybrid_transport.read_parameters = AsyncMock(return_value={110: 17440})

        result = await hybrid_transport.read_named_parameters(110, 1)

        assert result["FUNC_GREEN_EN"] is True
        assert result["FUNC_TAKE_LOAD_TOGETHER"] is True
        assert result["FUNC_BATTERY_ECO_EN"] is False

    @pytest.mark.asyncio
    async def test_hybrid_decode_bit8_is_not_green(self, hybrid_transport: ModbusTransport) -> None:
        """Anti-regression: a set bit 8 decodes as the placeholder, not green."""
        hybrid_transport.read_parameters = AsyncMock(return_value={110: 0x0100})

        result = await hybrid_transport.read_named_parameters(110, 1)

        assert result["FUNC_GREEN_EN"] is False
        assert result["FUNC_110_BIT8"] is True
