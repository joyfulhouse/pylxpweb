"""Tests for Modbus RTU serial transport implementation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.transports.config import TransportConfig, TransportType
from pylxpweb.transports.exceptions import (
    TransportConnectionError,
    TransportReadError,
    TransportWriteError,
)
from pylxpweb.transports.factory import (
    create_serial_transport,
    create_transport,
    create_transport_from_config,
)
from pylxpweb.transports.modbus_serial import ModbusSerialTransport


class TestModbusSerialTransportInit:
    """Tests for ModbusSerialTransport initialization."""

    def test_init_default_values(self) -> None:
        """Test serial transport initialization with defaults."""
        transport = ModbusSerialTransport(
            port="/dev/ttyUSB0",
            serial="CE12345678",
        )

        assert transport.serial == "CE12345678"
        assert transport.port == "/dev/ttyUSB0"
        assert transport.baudrate == 19200
        assert transport.unit_id == 1
        assert transport.is_connected is False

    def test_init_custom_values(self) -> None:
        """Test serial transport initialization with custom values."""
        transport = ModbusSerialTransport(
            port="/dev/ttyUSB1",
            serial="CE12345678",
            baudrate=9600,
            parity="E",
            stopbits=2,
            unit_id=3,
            timeout=30.0,
        )

        assert transport.port == "/dev/ttyUSB1"
        assert transport.baudrate == 9600
        assert transport.unit_id == 3

    def test_capabilities(self) -> None:
        """Test serial transport capabilities match Modbus TCP."""
        transport = ModbusSerialTransport(
            port="/dev/ttyUSB0",
            serial="CE12345678",
        )

        caps = transport.capabilities
        assert caps.can_read_runtime is True
        assert caps.can_read_energy is True
        assert caps.can_read_battery is True
        assert caps.is_local is True
        assert caps.requires_authentication is False

    def test_inverter_family_setter(self) -> None:
        """Test inverter family property setter."""
        from pylxpweb.devices.inverters._features import InverterFamily

        transport = ModbusSerialTransport(
            port="/dev/ttyUSB0",
            serial="CE12345678",
        )

        assert transport.inverter_family is None
        transport.inverter_family = InverterFamily.EG4_HYBRID
        assert transport.inverter_family == InverterFamily.EG4_HYBRID


class TestModbusSerialConnection:
    """Tests for serial connect/disconnect."""

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        """Test successful serial connection."""
        transport = ModbusSerialTransport(
            port="/dev/ttyUSB0",
            serial="CE12345678",
        )

        with (
            patch(
                "pylxpweb.transports.modbus_serial.AsyncModbusSerialClient",
                create=True,
            ),
            patch("pymodbus.client.AsyncModbusSerialClient") as mock_cls,
        ):
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_cls.return_value = mock_client

            await transport.connect()
            assert transport.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_failure(self) -> None:
        """Test serial connection failure."""
        transport = ModbusSerialTransport(
            port="/dev/ttyUSB0",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusSerialClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with pytest.raises(TransportConnectionError, match="Failed to connect"):
                await transport.connect()

    @pytest.mark.asyncio
    async def test_connect_permission_error(self) -> None:
        """Test serial port permission error."""
        transport = ModbusSerialTransport(
            port="/dev/ttyUSB0",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusSerialClient") as mock_cls:
            mock_cls.side_effect = PermissionError("Permission denied")

            with pytest.raises(TransportConnectionError, match="Permission denied"):
                await transport.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        """Test serial disconnection."""
        transport = ModbusSerialTransport(
            port="/dev/ttyUSB0",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusSerialClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()
            mock_cls.return_value = mock_client

            await transport.connect()
            assert transport.is_connected is True

            await transport.disconnect()
            assert transport.is_connected is False
            mock_client.close.assert_called_once()


class TestModbusSerialRegisterReading:
    """Tests for serial register read/write operations."""

    @pytest.mark.asyncio
    async def test_read_parameters(self) -> None:
        """Test reading holding registers."""
        transport = ModbusSerialTransport(
            port="/dev/ttyUSB0",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusSerialClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)

            mock_response = MagicMock()
            mock_response.isError.return_value = False
            mock_response.registers = [100, 200, 300]

            mock_client.read_holding_registers = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            await transport.connect()
            params = await transport.read_parameters(0, 3)

            assert params == {0: 100, 1: 200, 2: 300}

    @pytest.mark.asyncio
    async def test_read_parameters_not_connected(self) -> None:
        """Test parameter read when not connected."""
        transport = ModbusSerialTransport(
            port="/dev/ttyUSB0",
            serial="CE12345678",
        )

        with pytest.raises(TransportConnectionError, match="Transport not connected"):
            await transport.read_parameters(0, 10)

    @pytest.mark.asyncio
    async def test_read_parameters_modbus_error(self) -> None:
        """Test parameter read with Modbus error response."""
        transport = ModbusSerialTransport(
            port="/dev/ttyUSB0",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusSerialClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)

            mock_response = MagicMock()
            mock_response.isError.return_value = True

            mock_client.read_holding_registers = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            await transport.connect()
            with pytest.raises(TransportReadError, match="Modbus read error"):
                await transport.read_parameters(0, 5)

    @pytest.mark.asyncio
    async def test_write_parameters_success(self) -> None:
        """Test successful parameter write."""
        transport = ModbusSerialTransport(
            port="/dev/ttyUSB0",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusSerialClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)

            mock_response = MagicMock()
            mock_response.isError.return_value = False

            mock_client.write_register = AsyncMock(return_value=mock_response)
            mock_client.write_registers = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            await transport.connect()
            result = await transport.write_parameters({0: 100, 1: 200})

            assert result is True
            mock_client.write_registers.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_write_parameters_not_connected(self) -> None:
        """Test parameter write when not connected."""
        transport = ModbusSerialTransport(
            port="/dev/ttyUSB0",
            serial="CE12345678",
        )

        with pytest.raises(TransportConnectionError, match="Transport not connected"):
            await transport.write_parameters({0: 100})

    @pytest.mark.asyncio
    async def test_write_parameters_error(self) -> None:
        """Test parameter write with Modbus error."""
        transport = ModbusSerialTransport(
            port="/dev/ttyUSB0",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusSerialClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)

            mock_response = MagicMock()
            mock_response.isError.return_value = True

            mock_client.write_register = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            await transport.connect()
            with pytest.raises(TransportWriteError, match="Modbus write error"):
                await transport.write_parameters({0: 100})

    @pytest.mark.asyncio
    async def test_read_runtime_success(self) -> None:
        """Test successful runtime read via serial Modbus."""
        transport = ModbusSerialTransport(
            port="/dev/ttyUSB0",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusSerialClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)

            mock_response = MagicMock()
            mock_response.isError.return_value = False
            mock_response.registers = [
                0,  # 0: Status
                5100,  # 1: PV1 voltage (×10 = 510V)
                5050,  # 2: PV2 voltage
                0,  # 3: PV3 voltage
                530,  # 4: Battery voltage (×10 = 53V)
                (100 << 8) | 85,  # 5: SOC=85 (low), SOH=100 (high)
                0,  # 6
                1000,  # 7: PV1 power
                1500,  # 8: PV2 power
                0,  # 9: PV3 power
                500,  # 10: Charge power
                0,  # 11: Discharge power
                2410,  # 12: Grid voltage R (×10)
                2415,  # 13: Grid voltage S
                2420,  # 14: Grid voltage T
                5998,  # 15: Grid frequency (×100)
                2300,  # 16: Inverter power
                100,  # 17: Grid power
                50,  # 18: IinvRMS
                990,  # 19: Power factor
                2400,  # 20: EPS voltage R
                2405,  # 21: EPS voltage S
                2410,  # 22: EPS voltage T
                5999,  # 23: EPS frequency
                300,  # 24: EPS power
                1,  # 25: EPS status
                200,  # 26: Power to grid
                1500,  # 27: Load power
            ] + [0] * 100

            mock_client.read_input_registers = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            await transport.connect()
            runtime = await transport.read_runtime()

            assert runtime.pv1_voltage == pytest.approx(510.0, rel=0.01)
            assert runtime.battery_soc == 85
            assert runtime.grid_frequency == pytest.approx(59.98, rel=0.01)


class TestSerialTransportConfig:
    """Tests for TransportConfig with MODBUS_SERIAL type."""

    def test_serial_config_valid(self) -> None:
        """Test valid serial transport config."""
        config = TransportConfig(
            host="",
            port=0,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_SERIAL,
            serial_port="/dev/ttyUSB0",
        )

        assert config.transport_type == TransportType.MODBUS_SERIAL
        assert config.serial_port == "/dev/ttyUSB0"
        assert config.serial_baudrate == 19200
        assert config.serial_parity == "N"
        assert config.serial_stopbits == 1

    def test_serial_config_missing_port(self) -> None:
        """Test serial config without serial_port raises."""
        with pytest.raises(ValueError, match="serial_port is required"):
            TransportConfig(
                host="",
                port=0,
                serial="CE12345678",
                transport_type=TransportType.MODBUS_SERIAL,
            )

    def test_serial_config_missing_serial(self) -> None:
        """Test serial config without serial raises."""
        with pytest.raises(ValueError, match="serial is required"):
            TransportConfig(
                host="",
                port=0,
                serial="",
                transport_type=TransportType.MODBUS_SERIAL,
                serial_port="/dev/ttyUSB0",
            )

    def test_serial_config_invalid_parity(self) -> None:
        """Test serial config with invalid parity raises."""
        with pytest.raises(ValueError, match="Invalid parity"):
            TransportConfig(
                host="",
                port=0,
                serial="CE12345678",
                transport_type=TransportType.MODBUS_SERIAL,
                serial_port="/dev/ttyUSB0",
                serial_parity="X",
            )

    def test_serial_config_invalid_stopbits(self) -> None:
        """Test serial config with invalid stopbits raises."""
        with pytest.raises(ValueError, match="Invalid stopbits"):
            TransportConfig(
                host="",
                port=0,
                serial="CE12345678",
                transport_type=TransportType.MODBUS_SERIAL,
                serial_port="/dev/ttyUSB0",
                serial_stopbits=3,
            )

    def test_serial_config_to_dict_roundtrip(self) -> None:
        """Test config serialization and deserialization."""
        config = TransportConfig(
            host="",
            port=0,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_SERIAL,
            serial_port="/dev/ttyUSB0",
            serial_baudrate=9600,
            serial_parity="E",
            serial_stopbits=2,
        )

        data = config.to_dict()
        restored = TransportConfig.from_dict(data)

        assert restored.transport_type == TransportType.MODBUS_SERIAL
        assert restored.serial_port == "/dev/ttyUSB0"
        assert restored.serial_baudrate == 9600
        assert restored.serial_parity == "E"
        assert restored.serial_stopbits == 2


class TestSerialTransportFactory:
    """Tests for serial transport factory functions."""

    def test_create_serial_transport(self) -> None:
        """Test create_serial_transport factory function."""
        transport = create_serial_transport(
            port="/dev/ttyUSB0",
            serial="CE12345678",
            baudrate=9600,
        )

        assert isinstance(transport, ModbusSerialTransport)
        assert transport.port == "/dev/ttyUSB0"
        assert transport.baudrate == 9600

    def test_create_transport_serial_type(self) -> None:
        """Test create_transport with 'serial' connection type."""
        transport = create_transport(
            "serial",
            port="/dev/ttyUSB0",
            serial="CE12345678",
        )

        assert isinstance(transport, ModbusSerialTransport)

    def test_create_transport_serial_missing_port(self) -> None:
        """Test create_transport serial without port raises."""
        with pytest.raises(ValueError, match="port is required"):
            create_transport("serial", serial="CE12345678")

    def test_create_transport_serial_missing_serial(self) -> None:
        """Test create_transport serial without serial raises."""
        with pytest.raises(ValueError, match="serial is required"):
            create_transport("serial", port="/dev/ttyUSB0")

    def test_create_transport_from_config(self) -> None:
        """Test create_transport_from_config with serial config."""
        config = TransportConfig(
            host="",
            port=0,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_SERIAL,
            serial_port="/dev/ttyUSB0",
            serial_baudrate=9600,
        )

        transport = create_transport_from_config(config)
        assert isinstance(transport, ModbusSerialTransport)
        assert transport.port == "/dev/ttyUSB0"
        assert transport.baudrate == 9600
