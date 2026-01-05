"""Tests for Modbus transport implementation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.transports.exceptions import (
    TransportConnectionError,
    TransportReadError,
)
from pylxpweb.transports.modbus import ModbusTransport


class TestModbusTransport:
    """Tests for ModbusTransport class."""

    def test_init_default_values(self) -> None:
        """Test Modbus transport initialization with defaults."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        assert transport.serial == "CE12345678"
        assert transport._host == "192.168.1.100"
        assert transport._port == 502
        assert transport._unit_id == 1
        assert transport._timeout == 10.0
        assert transport.is_connected is False

    def test_init_custom_values(self) -> None:
        """Test Modbus transport initialization with custom values."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
            port=8502,
            unit_id=2,
            timeout=30.0,
        )

        assert transport._port == 8502
        assert transport._unit_id == 2
        assert transport._timeout == 30.0

    def test_capabilities(self) -> None:
        """Test Modbus transport capabilities."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        caps = transport.capabilities
        assert caps.can_read_runtime is True
        assert caps.can_read_energy is True
        assert caps.can_read_battery is True
        assert caps.is_local is True
        assert caps.requires_authentication is False

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        """Test successful Modbus connection."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        # Mock the Modbus client - import is done inside connect()
        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client_class.return_value = mock_client

            await transport.connect()

            assert transport.is_connected is True
            mock_client.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self) -> None:
        """Test Modbus connection failure."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            with pytest.raises(TransportConnectionError, match="Failed to connect"):
                await transport.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        """Test Modbus disconnection."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()
            mock_client_class.return_value = mock_client

            await transport.connect()
            assert transport.is_connected is True

            await transport.disconnect()
            assert transport.is_connected is False
            mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_runtime_not_connected(self) -> None:
        """Test runtime read when not connected."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        # The ModbusTransport wraps TransportConnectionError in TransportReadError

        with pytest.raises(TransportReadError):
            await transport.read_runtime()

    @pytest.mark.asyncio
    async def test_read_runtime_success(self) -> None:
        """Test successful runtime read via Modbus."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()

            # Mock register read response - needs enough registers for the read
            mock_response = MagicMock()
            mock_response.isError.return_value = False
            # 128 registers for runtime data
            mock_response.registers = [
                0,  # 0: Status
                5100,  # 1: PV1 voltage (510V)
                5050,  # 2: PV2 voltage
                0,  # 3: PV3 voltage
                5300,  # 4: Battery voltage (×100 = 53V)
                85,  # 5: SOC
                0,
                1000,  # 6-7: PV1 power
                0,
                1500,  # 8-9: PV2 power
                0,
                0,  # 10-11: PV3 power
                0,
                500,  # 12-13: Charge power
                0,
                0,  # 14-15: Discharge power
                2410,  # 16: Grid voltage R (×10)
                2415,  # 17: Grid voltage S
                2420,  # 18: Grid voltage T
                5998,  # 19: Grid frequency (×100 = 59.98Hz)
                0,
                2300,  # 20-21: Inverter power
                0,
                100,  # 22-23: Grid power
                0,
                0,  # 24-25: padding
                2400,  # 26: EPS voltage R
                2405,  # 27: EPS voltage S
                2410,  # 28: EPS voltage T
                5999,  # 29: EPS frequency
                0,
                300,  # 30-31: EPS power
                1,  # 32: EPS status
                200,  # 33: Power to grid
                0,
                1500,  # 34-35: Load power
            ] + [0] * 100  # Fill remaining registers

            mock_client.read_input_registers = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await transport.connect()
            runtime = await transport.read_runtime()

            assert runtime.pv1_voltage == pytest.approx(510.0, rel=0.01)
            assert runtime.battery_soc == 85
            assert runtime.grid_frequency == pytest.approx(59.98, rel=0.01)

    @pytest.mark.asyncio
    async def test_manual_connect_disconnect(self) -> None:
        """Test manual connect and disconnect."""
        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()
            mock_client_class.return_value = mock_client

            transport = ModbusTransport(
                host="192.168.1.100",
                serial="CE12345678",
            )

            await transport.connect()
            assert transport.is_connected is True

            await transport.disconnect()
            assert transport.is_connected is False
            mock_client.close.assert_called_once()


class TestModbusRegisterReading:
    """Tests for Modbus register reading."""

    @pytest.mark.asyncio
    async def test_read_parameters(self) -> None:
        """Test reading holding registers (parameters)."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()

            # Mock holding register response
            mock_response = MagicMock()
            mock_response.isError.return_value = False
            mock_response.registers = [100, 200, 300, 400, 500]

            mock_client.read_holding_registers = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await transport.connect()
            params = await transport.read_parameters(0, 5)

            assert params[0] == 100
            assert params[1] == 200
            assert params[2] == 300
            assert params[3] == 400
            assert params[4] == 500

    @pytest.mark.asyncio
    async def test_read_parameters_chunked(self) -> None:
        """Test reading parameters in chunks (>40 registers)."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()

            # Each read returns 40 registers
            call_count = 0

            async def make_response(**kwargs: int) -> MagicMock:
                nonlocal call_count
                response = MagicMock()
                response.isError.return_value = False
                # Return different values for each chunk
                start = call_count * 40
                response.registers = list(range(start, start + 40))
                call_count += 1
                return response

            mock_client.read_holding_registers = make_response
            mock_client_class.return_value = mock_client

            await transport.connect()
            params = await transport.read_parameters(0, 80)

            # Verify we got 80 parameter values
            assert len(params) == 80

            # Check first chunk values (0-39)
            assert params[0] == 0
            assert params[39] == 39

            # Check second chunk values (40-79)
            assert params[40] == 40
            assert params[79] == 79

            # Verify call_count tracks the 2 calls
            assert call_count == 2
