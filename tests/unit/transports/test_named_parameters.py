"""Tests for named parameter methods (read_named_parameters, write_named_parameters)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pylxpweb.devices.inverters._features import InverterFamily
from pylxpweb.transports.http import HTTPTransport
from pylxpweb.transports.hybrid import HybridTransport
from pylxpweb.transports.modbus import ModbusTransport


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
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test HybridTransport write falls back to HTTP on local failure."""
        from pylxpweb.transports.exceptions import TransportWriteError

        mock_local_transport.write_named_parameters.side_effect = TransportWriteError(
            "Local failed"
        )
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        transport._connected = True

        result = await transport.write_named_parameters({"FUNC_EPS_EN": True})

        assert result is True
        mock_http_transport.write_named_parameters.assert_called_once_with({"FUNC_EPS_EN": True})


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
        result = await mock_modbus_transport.write_named_parameters(
            {"BIT_MIDBOX_SP_MODE_3": 1}
        )

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
        result = await mock_modbus_transport.write_named_parameters(
            {"BIT_MIDBOX_SP_MODE_2": 0}
        )

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

        result = await mock_modbus_transport.write_named_parameters({
            "BIT_MIDBOX_SP_MODE_1": 2,  # AC Couple
            "BIT_MIDBOX_SP_MODE_4": 1,  # Smart Load
        })

        assert result is True
        # Expected: port1=2, port2=0, port3=0, port4=1 = 0b01_00_00_10 = 0x42
        mock_modbus_transport.write_parameters.assert_called_once_with({20: 0x42})

    @pytest.mark.asyncio
    async def test_write_multi_bit_without_device_type_uses_param_detection(
        self,
    ) -> None:
        """Test that multi-bit fields work even without _device_type set.

        The _resolve_register_mappings method auto-detects MIDBOX params
        from MULTI_BIT_FIELDS.
        """
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )
        transport._connected = True
        transport.read_parameters = AsyncMock(return_value={20: 0x00})
        transport.write_parameters = AsyncMock(return_value=True)

        result = await transport.write_named_parameters(
            {"BIT_MIDBOX_SP_MODE_1": 1}
        )

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
            await mock_modbus_transport.write_named_parameters(
                {"BIT_MIDBOX_SP_MODE_1": 5}
            )

    @pytest.mark.asyncio
    async def test_write_multi_bit_field_rejects_negative(
        self, mock_modbus_transport: ModbusTransport
    ) -> None:
        """Test writing a negative value raises ValueError."""
        mock_modbus_transport.read_parameters = AsyncMock(return_value={20: 0x00})

        with pytest.raises(ValueError, match="out of range"):
            await mock_modbus_transport.write_named_parameters(
                {"BIT_MIDBOX_SP_MODE_2": -1}
            )


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

        # All families currently use the same mapping
        mapping_eg4_hybrid = get_register_to_param_mapping("EG4_HYBRID")
        mapping_eg4_offgrid = get_register_to_param_mapping("EG4_OFFGRID")
        mapping_none = get_register_to_param_mapping(None)

        # All should return the same mapping currently
        assert mapping_eg4_hybrid == mapping_eg4_offgrid == mapping_none

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
