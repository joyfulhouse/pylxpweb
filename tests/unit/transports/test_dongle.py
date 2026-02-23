"""Unit tests for WiFi dongle transport."""

from __future__ import annotations

import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.transports.dongle import (
    DEFAULT_PORT,
    MODBUS_READ_HOLDING,
    MODBUS_READ_INPUT,
    MODBUS_WRITE_SINGLE,
    PACKET_PREFIX,
    PROTOCOL_VERSION,
    TCP_FUNC_TRANSLATED,
    DongleTransport,
    compute_crc16,
)
from pylxpweb.transports.exceptions import (
    TransportConnectionError,
    TransportReadError,
)


class TestComputeCRC16:
    """Tests for CRC-16/Modbus computation."""

    def test_empty_data(self) -> None:
        """Test CRC of empty data."""
        assert compute_crc16(b"") == 0xFFFF

    def test_known_value(self) -> None:
        """Test CRC of known data."""
        # Known CRC for "123456789"
        data = b"123456789"
        crc = compute_crc16(data)
        assert crc == 0x4B37  # Standard Modbus CRC for this test string

    def test_single_byte(self) -> None:
        """Test CRC of single byte."""
        crc = compute_crc16(b"\x01")
        assert isinstance(crc, int)
        assert 0 <= crc <= 0xFFFF


class TestDongleTransport:
    """Tests for DongleTransport initialization and properties."""

    def test_init_default_values(self) -> None:
        """Test initialization with default values."""
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        assert transport.host == "192.168.1.100"
        assert transport.port == DEFAULT_PORT
        assert transport.dongle_serial == "BA12345678"
        assert transport.serial == "CE12345678"
        assert transport.inverter_family is None
        assert transport.is_connected is False

    def test_init_custom_values(self) -> None:
        """Test initialization with custom values."""
        from pylxpweb.devices.inverters._features import InverterFamily

        transport = DongleTransport(
            host="192.168.1.200",
            dongle_serial="BA87654321",
            inverter_serial="CE87654321",
            port=9000,
            timeout=15.0,
            inverter_family=InverterFamily.LXP,
        )

        assert transport.host == "192.168.1.200"
        assert transport.port == 9000
        assert transport.dongle_serial == "BA87654321"
        assert transport.serial == "CE87654321"
        assert transport.inverter_family == InverterFamily.LXP

    def test_capabilities(self) -> None:
        """Test that dongle transport has correct capabilities."""
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        caps = transport.capabilities
        assert caps.can_read_runtime is True
        assert caps.can_read_energy is True
        assert caps.can_read_battery is True
        assert caps.can_read_parameters is True
        assert caps.can_write_parameters is True
        assert caps.can_discover_devices is False
        assert caps.is_local is True


class TestDongleConnection:
    """Tests for dongle connection handling."""

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        """Test successful connection."""
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        mock_reader = AsyncMock()
        # Simulate no initial data (returns empty bytes)
        mock_reader.read = AsyncMock(return_value=b"")
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            await transport.connect()

        assert transport.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_timeout(self) -> None:
        """Test connection timeout."""
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
            timeout=1.0,
        )

        with (
            patch("asyncio.open_connection", side_effect=TimeoutError("Connection timed out")),
            pytest.raises(TransportConnectionError) as exc_info,
        ):
            await transport.connect()

        assert "Timeout" in str(exc_info.value)
        assert transport.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_refused(self) -> None:
        """Test connection refused."""
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        with (
            patch("asyncio.open_connection", side_effect=ConnectionRefusedError()),
            pytest.raises(TransportConnectionError) as exc_info,
        ):
            await transport.connect()

        assert "Failed to connect" in str(exc_info.value)
        assert transport.is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        """Test disconnection."""
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        mock_reader = AsyncMock()
        mock_reader.read = AsyncMock(return_value=b"")
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            await transport.connect()
            assert transport.is_connected is True

            await transport.disconnect()
            assert transport.is_connected is False

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        """Test async context manager."""
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        mock_reader = AsyncMock()
        mock_reader.read = AsyncMock(return_value=b"")
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            async with transport:
                assert transport.is_connected is True
            assert transport.is_connected is False


class TestDonglePacketBuilding:
    """Tests for packet building."""

    def test_build_read_input_packet(self) -> None:
        """Test building a read input registers packet."""
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        packet = transport._build_packet(
            tcp_func=TCP_FUNC_TRANSLATED,
            modbus_func=MODBUS_READ_INPUT,
            start_register=0,
            register_count=32,
        )

        # Verify packet prefix
        assert packet[:2] == PACKET_PREFIX

        # Verify protocol version
        version = struct.unpack("<H", packet[2:4])[0]
        assert version == PROTOCOL_VERSION

        # Verify TCP function code
        assert packet[7] == TCP_FUNC_TRANSLATED

        # Verify dongle serial is in the packet
        dongle_serial_in_packet = packet[8:18].decode("ascii").rstrip("\x00")
        assert dongle_serial_in_packet == "BA12345678"

    def test_build_write_single_packet(self) -> None:
        """Test building a write single register packet."""
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        packet = transport._build_packet(
            tcp_func=TCP_FUNC_TRANSLATED,
            modbus_func=MODBUS_WRITE_SINGLE,
            start_register=105,
            values=[50],  # Write value 50 to register 105
        )

        # Verify prefix
        assert packet[:2] == PACKET_PREFIX

        # Verify TCP function code
        assert packet[7] == TCP_FUNC_TRANSLATED


def _build_mock_response(
    inverter_serial: str = "CE12345678",
    dongle_serial: str = "BA12345678",
    modbus_func: int = MODBUS_READ_INPUT,
    start_register: int = 0,
    register_values: list[int] | None = None,
    exception_code: int | None = None,
) -> bytes:
    """Build a complete mock dongle response packet for testing.

    Args:
        inverter_serial: Inverter serial in the response data frame.
        dongle_serial: Dongle serial in the packet header.
        modbus_func: Modbus function code in the response.
        start_register: Starting register address in the response.
        register_values: Register values to include.  Defaults to [100, 200].
        exception_code: If set, builds an exception response (short frame
            with only the exception code byte after the start register).

    Returns:
        Complete response packet bytes.
    """
    inverter_bytes = inverter_serial.encode("ascii").ljust(10, b"\x00")[:10]

    data_frame = bytes([0x00, modbus_func]) + inverter_bytes
    data_frame += struct.pack("<H", start_register)

    if exception_code is not None:
        data_frame += bytes([exception_code])
    else:
        if register_values is None:
            register_values = [100, 200]
        byte_count = len(register_values) * 2
        data_frame += bytes([byte_count])
        for val in register_values:
            data_frame += struct.pack("<H", val)

    crc = compute_crc16(data_frame)

    response = PACKET_PREFIX
    response += struct.pack("<H", PROTOCOL_VERSION)
    response += struct.pack("<H", 14 + len(data_frame) + 2)
    response += bytes([0x01, TCP_FUNC_TRANSLATED])
    response += dongle_serial.encode("ascii").ljust(10, b"\x00")[:10]
    response += struct.pack("<H", len(data_frame) + 2)
    response += data_frame
    response += struct.pack("<H", crc)
    return response


class TestDongleResponseParsing:
    """Tests for response parsing."""

    def test_parse_response_too_short(self) -> None:
        """Test parsing a response that's too short."""
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        with pytest.raises(TransportReadError, match="too short"):
            transport._parse_response(b"\xa1\x1a\x01\x00")

    def test_parse_response_invalid_prefix(self) -> None:
        """Test parsing a response with invalid prefix."""
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        response = b"\x00\x00" + b"\x00" * 30

        with pytest.raises(TransportReadError, match="No valid packet found"):
            transport._parse_response(response)

    def test_parse_valid_response(self) -> None:
        """Test parsing a valid response."""
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        response = _build_mock_response(register_values=[100, 200])
        registers = transport._parse_response(response)

        assert registers == [100, 200]

    def test_parse_modbus_exception(self) -> None:
        """Test parsing a Modbus exception response."""
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        response = _build_mock_response(modbus_func=0x84, exception_code=2)

        with pytest.raises(TransportReadError, match="Modbus exception"):
            transport._parse_response(response)


class TestDongleResponseValidation:
    """Tests for cross-request response validation (serial/func/register match)."""

    def _make_transport(self) -> DongleTransport:
        return DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

    def test_serial_mismatch_rejected(self) -> None:
        """Response with wrong inverter serial is rejected."""
        transport = self._make_transport()
        response = _build_mock_response(inverter_serial="XX99999999")

        with pytest.raises(TransportReadError, match="serial mismatch"):
            transport._parse_response(response)

    def test_serial_always_checked(self) -> None:
        """Serial is validated even when expected_func/expected_register are None."""
        transport = self._make_transport()
        response = _build_mock_response(inverter_serial="XX99999999")

        with pytest.raises(TransportReadError, match="serial mismatch"):
            transport._parse_response(response, expected_func=None, expected_register=None)

    def test_function_code_mismatch_rejected(self) -> None:
        """Response with wrong function code (holding vs input) is rejected."""
        transport = self._make_transport()
        # Response says holding read (0x03) but we expected input read (0x04)
        response = _build_mock_response(modbus_func=MODBUS_READ_HOLDING)

        with pytest.raises(TransportReadError, match="function mismatch"):
            transport._parse_response(
                response, expected_func=MODBUS_READ_INPUT, expected_register=0
            )

    def test_register_mismatch_rejected(self) -> None:
        """Response for wrong starting register is rejected."""
        transport = self._make_transport()
        # Response is for register 80 but we expected register 0
        response = _build_mock_response(start_register=80)

        with pytest.raises(TransportReadError, match="register mismatch"):
            transport._parse_response(
                response, expected_func=MODBUS_READ_INPUT, expected_register=0
            )

    def test_all_matching_accepted(self) -> None:
        """Response matching serial, func, and register is accepted."""
        transport = self._make_transport()
        response = _build_mock_response(
            modbus_func=MODBUS_READ_INPUT,
            start_register=32,
            register_values=[500, 600, 700],
        )

        registers = transport._parse_response(
            response, expected_func=MODBUS_READ_INPUT, expected_register=32
        )

        assert registers == [500, 600, 700]

    def test_exception_func_matches_base(self) -> None:
        """Exception response (0x84) matches expected func (0x04) via masking."""
        transport = self._make_transport()
        response = _build_mock_response(modbus_func=0x84, exception_code=2)

        # Should pass serial+func validation but raise Modbus exception
        with pytest.raises(TransportReadError, match="Modbus exception"):
            transport._parse_response(
                response, expected_func=MODBUS_READ_INPUT, expected_register=0
            )

    def test_exception_func_mismatch_rejected(self) -> None:
        """Exception for wrong func (0x83) rejected when expecting 0x04."""
        transport = self._make_transport()
        response = _build_mock_response(modbus_func=0x83, exception_code=2)

        # Should fail on function mismatch (0x03 != 0x04)
        with pytest.raises(TransportReadError, match="function mismatch"):
            transport._parse_response(
                response, expected_func=MODBUS_READ_INPUT, expected_register=0
            )

    def test_no_validation_when_not_specified(self) -> None:
        """Without expected_func/expected_register, only serial is checked."""
        transport = self._make_transport()
        # Correct serial but "wrong" func/register — should pass since not checked
        response = _build_mock_response(modbus_func=MODBUS_READ_HOLDING, start_register=99)

        registers = transport._parse_response(response)
        assert registers == [100, 200]


class TestDongleRegisterOperations:
    """Tests for register read/write operations."""

    @pytest.mark.asyncio
    async def test_read_input_registers_not_connected(self) -> None:
        """Test reading input registers when not connected."""
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        with pytest.raises(TransportConnectionError):
            await transport._read_input_registers(0, 32)

    @pytest.mark.asyncio
    async def test_read_runtime_not_connected(self) -> None:
        """Test reading runtime when disconnected triggers auto-reconnect.

        When the dongle is not connected, _send_receive attempts to reconnect.
        If reconnection also fails (e.g. unreachable host), the error propagates
        as a TransportReadError wrapping the connection failure.
        """
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        with pytest.raises(TransportReadError) as exc_info:
            await transport.read_runtime()

        error_msg = str(exc_info.value).lower()
        assert "timeout" in error_msg or "failed" in error_msg

    @pytest.mark.asyncio
    async def test_auto_reconnect_after_disconnect(self) -> None:
        """Test that _send_receive auto-reconnects after connection drops.

        Simulates a dropped connection (OSError during read) followed by
        a successful reconnect on the next call.
        """
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )
        # Simulate an established connection
        transport._connected = True
        transport._reader = AsyncMock()
        transport._writer = AsyncMock()
        transport._writer.close = MagicMock()

        # First call: OSError tears down the connection
        transport._reader.read = AsyncMock(side_effect=OSError("Connection reset"))
        with pytest.raises(TransportReadError, match="Socket error"):
            await transport._send_receive(b"\x00" * 10)

        assert not transport._connected

        # Next call: should attempt reconnect (not just raise "not connected")
        # Mock connect to succeed and set up fresh reader/writer
        async def mock_connect() -> None:
            transport._connected = True
            transport._reader = AsyncMock()
            transport._writer = AsyncMock()
            transport._writer.close = MagicMock()
            # Return a valid response on read
            transport._reader.read = AsyncMock(return_value=b"")

        transport.connect = AsyncMock(side_effect=mock_connect)

        # This should call connect(), not raise TransportConnectionError
        with pytest.raises(TransportReadError):
            # Will fail with empty response after reconnect, but the point
            # is that connect() was called
            await transport._send_receive(b"\x00" * 10)

        transport.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_parameters(self) -> None:
        """Test writing parameters."""
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        # Build a mock valid write response
        # Data frame: action(1) + modbus_func(1) + inverter_serial(10) + reg_addr(2) + value(2)
        data_frame = bytes([0x00, MODBUS_WRITE_SINGLE])  # action=0, func=6
        data_frame += b"CE12345678"  # inverter serial (10 bytes)
        data_frame += struct.pack("<H", 105)  # register address
        data_frame += struct.pack("<H", 50)  # value written
        crc = compute_crc16(data_frame)

        response = PACKET_PREFIX
        response += struct.pack("<H", PROTOCOL_VERSION)
        response += struct.pack("<H", 14 + len(data_frame) + 2)
        response += bytes([0x01, TCP_FUNC_TRANSLATED])
        response += b"BA12345678"
        response += struct.pack("<H", len(data_frame) + 2)
        response += data_frame
        response += struct.pack("<H", crc)

        mock_reader = AsyncMock()
        # First call returns empty (during connect's _discard_initial_data)
        # Second call is for _drain_buffer (returns empty to stop draining)
        # Third call returns the actual response
        mock_reader.read = AsyncMock(side_effect=[b"", b"", response])

        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            await transport.connect()
            result = await transport.write_parameters({105: 50})

        assert result is True


class TestDongleCapabilities:
    """Tests for dongle capabilities constant."""

    def test_dongle_capabilities_exported(self) -> None:
        """Test that DONGLE_CAPABILITIES is exported."""
        from pylxpweb.transports import DONGLE_CAPABILITIES

        assert DONGLE_CAPABILITIES.can_read_runtime is True
        assert DONGLE_CAPABILITIES.can_read_energy is True
        assert DONGLE_CAPABILITIES.can_read_battery is True
        assert DONGLE_CAPABILITIES.can_read_parameters is True
        assert DONGLE_CAPABILITIES.can_write_parameters is True
        assert DONGLE_CAPABILITIES.is_local is True
        assert DONGLE_CAPABILITIES.supports_concurrent_reads is False


class TestCreateDongleTransportFactory:
    """Tests for create_dongle_transport factory function."""

    def test_create_dongle_transport_defaults(self) -> None:
        """Test factory function with default values."""
        from pylxpweb.transports import create_dongle_transport

        transport = create_dongle_transport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        assert isinstance(transport, DongleTransport)
        assert transport.host == "192.168.1.100"
        assert transport.port == 8000
        assert transport.dongle_serial == "BA12345678"
        assert transport.serial == "CE12345678"
        assert transport.inverter_family is None

    def test_create_dongle_transport_custom(self) -> None:
        """Test factory function with custom values."""
        from pylxpweb.devices.inverters._features import InverterFamily
        from pylxpweb.transports import create_dongle_transport

        transport = create_dongle_transport(
            host="192.168.1.200",
            dongle_serial="BA87654321",
            inverter_serial="CE87654321",
            port=9000,
            timeout=15.0,
            inverter_family=InverterFamily.LXP,
        )

        assert isinstance(transport, DongleTransport)
        assert transport.host == "192.168.1.200"
        assert transport.port == 9000
        assert transport.dongle_serial == "BA87654321"
        assert transport.serial == "CE87654321"
        assert transport.inverter_family == InverterFamily.LXP
