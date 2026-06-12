"""Unit tests for WiFi dongle transport."""

from __future__ import annotations

import asyncio
import contextlib
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.registers import PV4_6_INPUT_REGISTER_GROUP
from pylxpweb.transports.dongle import (
    DEFAULT_PORT,
    MODBUS_READ_HOLDING,
    MODBUS_READ_INPUT,
    MODBUS_WRITE_MULTI,
    MODBUS_WRITE_SINGLE,
    PACKET_PREFIX,
    PROTOCOL_VERSION,
    TCP_FUNC_TRANSLATED,
    DongleTransport,
    compute_crc16,
)
from pylxpweb.transports.exceptions import (
    TransportConnectionError,
    TransportError,
    TransportReadError,
    TransportTimeoutError,
    TransportWriteError,
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


def _build_write_ack_frame(
    modbus_func: int,
    start_register: int,
    payload: int,
    inverter_serial: str = "CE12345678",
    dongle_serial: str = "BA12345678",
) -> bytes:
    """Build a REAL-layout write ACK packet (FC06/FC16).

    Unlike ``_build_mock_response`` (read layout: byte_count + data), a real
    write ACK data frame is exactly 16 bytes:
    action(1) + func(1) + serial(10) + register(2) + payload(2),
    where payload is the echoed value (FC06) or register count (FC16).
    """
    inverter_bytes = inverter_serial.encode("ascii").ljust(10, b"\x00")[:10]
    data_frame = bytes([0x00, modbus_func]) + inverter_bytes
    data_frame += struct.pack("<H", start_register)
    data_frame += struct.pack("<H", payload)
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
        """Test that _send_receive auto-reconnects on next call after disconnect.

        Simulates: previous call left _connected=False, next _send_receive
        reconnects before attempting the transaction.  Every empty response
        (EOF) now tears the connection down, so each retry attempt dials a
        fresh connection — three attempts, three connects.
        """
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )
        # Simulate a prior disconnect (e.g. previous call failed)
        transport._connected = False
        transport._reader = None
        transport._writer = None

        # Mock connect to succeed and set up fresh reader/writer
        async def mock_connect() -> None:
            transport._connected = True
            transport._reader = AsyncMock()
            writer = AsyncMock()
            writer.write = MagicMock()
            writer.close = MagicMock()
            transport._writer = writer
            # Return empty response (will fail, but proves connect was called)
            transport._reader.read = AsyncMock(return_value=b"")

        transport.connect = AsyncMock(side_effect=mock_connect)

        # This should call connect() before attempting the transaction
        with patch("asyncio.sleep", AsyncMock()), pytest.raises(TransportReadError):
            await transport._send_receive(b"\x00" * 10)

        # One reconnect per attempt: EOF tears down, each retry dials fresh.
        assert transport.connect.call_count == 3
        # Final EOF also tore down, so the NEXT request reconnects too.
        assert transport.is_connected is False

    @pytest.mark.asyncio
    async def test_oserror_reconnect_retry_succeeds(self) -> None:
        """Test that OSError triggers reconnect+retry within _send_receive.

        Simulates: first attempt hits OSError (connection drop), reconnects,
        second attempt succeeds with valid response.
        """
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )
        transport._connected = True

        valid_response = _build_mock_response(
            modbus_func=MODBUS_READ_HOLDING,
            start_register=105,
            register_values=[42],
        )

        # First attempt: reader raises OSError
        first_reader = AsyncMock()
        first_reader.read = AsyncMock(side_effect=OSError("Connection lost"))
        first_writer = AsyncMock()
        first_writer.write = MagicMock()
        first_writer.close = MagicMock()
        transport._reader = first_reader
        transport._writer = first_writer

        # After reconnect: fresh reader returns valid response
        second_reader = AsyncMock()
        # First read is _drain_buffer (empty), second is the actual response
        second_reader.read = AsyncMock(side_effect=[b"", valid_response])
        second_writer = AsyncMock()
        second_writer.write = MagicMock()
        second_writer.close = MagicMock()

        async def mock_connect() -> None:
            transport._connected = True
            transport._reader = second_reader
            transport._writer = second_writer

        transport.connect = AsyncMock(side_effect=mock_connect)

        result = await transport._send_receive(
            b"\x00" * 10,
            expected_func=MODBUS_READ_HOLDING,
            expected_register=105,
        )

        assert result == [42]
        transport.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_oserror_all_retries_exhausted(self) -> None:
        """Test that OSError on all attempts raises after exhausting retries."""
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )
        transport._connected = True

        async def mock_connect() -> None:
            transport._connected = True
            reader = AsyncMock()
            reader.read = AsyncMock(side_effect=OSError("Connection lost"))
            writer = AsyncMock()
            writer.write = MagicMock()
            writer.close = MagicMock()
            transport._reader = reader
            transport._writer = writer

        # Initial reader also fails
        transport._reader = AsyncMock()
        transport._reader.read = AsyncMock(side_effect=OSError("Connection lost"))
        transport._writer = AsyncMock()
        transport._writer.write = MagicMock()
        transport._writer.close = MagicMock()

        transport.connect = AsyncMock(side_effect=mock_connect)

        with pytest.raises(TransportReadError, match="Socket error"):
            await transport._send_receive(b"\x00" * 10, max_retries=2)

        # Should have reconnected for attempts 1 and 2 (attempt 0 fails,
        # reconnects for attempt 1, fails, reconnects for attempt 2, fails)
        assert transport.connect.call_count == 2

    @pytest.mark.asyncio
    async def test_oserror_reconnect_failure_fails_fast(self) -> None:
        """A failed in-loop reconnect aborts the request immediately.

        connect() already retries internally with backoff — if a full
        connect cycle fails there is no connectivity, so burning the
        remaining request attempts on more connect cycles only multiplies
        dead-endpoint latency (bad for link-down probe cadence, #226).

        With max_retries=2:
        - Attempt 0: OSError → teardown → sleep → continue
        - Attempt 1: top-of-loop reconnect → fails → raise immediately
        """
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )
        transport._connected = True
        transport._reader = AsyncMock()
        transport._reader.read = AsyncMock(side_effect=OSError("Connection lost"))
        transport._writer = AsyncMock()
        transport._writer.write = MagicMock()
        transport._writer.close = MagicMock()

        # Reconnect fails — the request must fail fast with the real error
        transport.connect = AsyncMock(side_effect=TransportConnectionError("Cannot connect"))

        with (
            patch("asyncio.sleep", AsyncMock()),
            pytest.raises(TransportConnectionError, match="Cannot connect"),
        ):
            await transport._send_receive(b"\x00" * 10, max_retries=2)

        # Exactly ONE reconnect cycle — no repeat connect() per attempt
        assert transport.connect.call_count == 1

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


class TestDongleReadRuntimeSerialization:
    """Tests that DongleTransport.read_runtime is serialised under _op_lock.

    The dongle has a single TCP connection and processes one request at a
    time.  The inherited ``RegisterDataMixin.read_runtime`` issues a
    multi-register runtime read PLUS the supplementary pv4-6 read, releasing
    the per-transaction lock between calls.  Without op-level serialisation,
    concurrent operations can interleave and misroute responses.  This mirrors
    the serialisation already applied to ``read_all_input_data``.
    """

    @pytest.mark.asyncio
    async def test_read_runtime_holds_op_lock(self) -> None:
        """read_runtime must hold _op_lock while issuing register reads."""
        from pylxpweb.devices.inverters._features import InverterFamily

        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
            inverter_family=InverterFamily.EG4_HYBRID,
        )

        lock_held_during_reads: list[bool] = []

        async def fake_read_input(start: int, count: int) -> list[int]:
            # Record whether the op_lock is held (owner set) during each read.
            lock_held_during_reads.append(transport._op_lock._owner is not None)
            return [0] * count

        with patch.object(transport, "_read_input_registers", side_effect=fake_read_input):
            await transport.read_runtime()

        assert lock_held_during_reads, "expected at least one register read"
        assert all(lock_held_during_reads), (
            "read_runtime issued register reads without holding _op_lock; "
            "the dongle runtime read is not serialised"
        )

    @pytest.mark.asyncio
    async def test_read_runtime_serialises_pv4_6_read(self) -> None:
        """The supplementary pv4-6 read must also occur under the lock."""
        from pylxpweb.devices.inverters._features import InverterFamily

        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
            inverter_family=InverterFamily.EG4_HYBRID,
        )
        # Force pv4-6 path (models with >=4 strings issue the extra read).
        transport._pv_string_count = 6

        reads: list[tuple[int, bool]] = []

        async def fake_read_input(start: int, count: int) -> list[int]:
            reads.append((start, transport._op_lock._owner is not None))
            return [0] * count

        with patch.object(transport, "_read_input_registers", side_effect=fake_read_input):
            await transport.read_runtime()

        # The pv4-6 supplementary read (start 217) must have occurred...
        read_starts = [start for start, _ in reads]
        assert PV4_6_INPUT_REGISTER_GROUP[0] in read_starts, (
            "pv4-6 supplementary read did not occur for a >=4-string model"
        )
        # ...and every read (including pv4-6) must hold the lock.
        assert all(held for _, held in reads), (
            "pv4-6 supplementary read was not serialised under _op_lock"
        )


def _make_write_test_transport(**kwargs: object) -> DongleTransport:
    """Build a dongle transport suitable for write-sequence tests.

    Uses EG4_HYBRID family (FUNC_EPS_EN -> reg 21 bit 0,
    FUNC_GREEN_EN -> reg 110 bit 8, HOLD_AC_CHARGE_SOC_LIMIT -> reg 67)
    and disables the inter-step delay so tests run fast.
    """
    from pylxpweb.devices.inverters._features import InverterFamily

    defaults: dict[str, object] = {
        "host": "192.168.1.100",
        "dongle_serial": "BA12345678",
        "inverter_serial": "CE12345678",
        "inverter_family": InverterFamily.EG4_HYBRID,
        "write_step_delay": 0.0,
    }
    defaults.update(kwargs)
    transport = DongleTransport(**defaults)  # type: ignore[arg-type]
    transport._connected = True
    return transport


class TestDongleWriteSequenceResilience:
    """Sequence-level retry for the read-modify-write parameter write cycle.

    The WiFi dongle drops its TCP connection mid-sequence during parameter
    writes (firmware timeout / cloud-connection priority).  The write path
    must reconnect, RE-READ the register (never reuse a stale pre-drop value
    for the modify step), re-apply the modification, and retry the write —
    bounded retries with a clear typed error on permanent failure.

    Regression tests for joyfulhouse/eg4_web_monitor#201.
    """

    @pytest.mark.asyncio
    async def test_drop_on_read_rereads_and_writes(self) -> None:
        """Connection drop on the RMW read step: reconnect, re-read, write."""
        transport = _make_write_test_transport()

        read_results: list[object] = [
            TransportReadError("Socket error: Connection lost"),  # RMW read drops
            [0x0000],  # fresh re-read after reconnect
            [0x0001],  # post-write verification read
        ]
        mock_read = AsyncMock(side_effect=read_results)
        mock_write = AsyncMock(return_value=True)
        transport._force_reconnect = AsyncMock()  # type: ignore[method-assign]

        with (
            patch.object(transport, "_read_holding_registers", mock_read),
            patch.object(transport, "_write_holding_registers", mock_write),
            patch("asyncio.sleep", AsyncMock()),
        ):
            result = await transport.write_named_parameters({"FUNC_EPS_EN": True})

        assert result is True
        mock_write.assert_called_once_with(21, [0x0001])
        transport._force_reconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_drop_on_write_never_reuses_stale_read(self) -> None:
        """Connection drop on the write step: the retry must RE-READ the register.

        The register value changes between the first read and the retry
        (e.g. the cloud server wrote concurrently while we reconnected).
        The retried write must be based on the FRESH value, not the stale
        pre-drop value.
        """
        transport = _make_write_test_transport()

        read_results: list[object] = [
            [0x0000],  # first RMW read (becomes stale)
            [0x0100],  # fresh re-read: bit 8 was set concurrently
            [0x0101],  # post-write verification read
        ]
        write_results: list[object] = [
            TransportWriteError("Socket error: Connection lost"),  # write drops
            True,  # retried write succeeds
        ]
        mock_read = AsyncMock(side_effect=read_results)
        mock_write = AsyncMock(side_effect=write_results)
        transport._force_reconnect = AsyncMock()  # type: ignore[method-assign]

        with (
            patch.object(transport, "_read_holding_registers", mock_read),
            patch.object(transport, "_write_holding_registers", mock_write),
            patch("asyncio.sleep", AsyncMock()),
        ):
            result = await transport.write_named_parameters({"FUNC_EPS_EN": True})

        assert result is True
        assert mock_read.call_count == 3
        # Stale write used 0x0001; the retried write MUST use 0x0101.
        assert mock_write.call_args_list[0].args == (21, [0x0001])
        assert mock_write.call_args_list[1].args == (21, [0x0101])
        transport._force_reconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_drop_twice_then_succeed(self) -> None:
        """Two consecutive drops (read then timeout) recover on third attempt."""
        transport = _make_write_test_transport()

        read_results: list[object] = [
            TransportReadError("Socket error: Connection lost"),  # attempt 1
            TransportTimeoutError("Timeout waiting for dongle response"),  # attempt 2
            [0x0010],  # attempt 3: fresh read
            [0x0011],  # verification read
        ]
        mock_read = AsyncMock(side_effect=read_results)
        mock_write = AsyncMock(return_value=True)
        transport._force_reconnect = AsyncMock()  # type: ignore[method-assign]

        with (
            patch.object(transport, "_read_holding_registers", mock_read),
            patch.object(transport, "_write_holding_registers", mock_write),
            patch("asyncio.sleep", AsyncMock()),
        ):
            result = await transport.write_named_parameters({"FUNC_EPS_EN": True})

        assert result is True
        mock_write.assert_called_once_with(21, [0x0011])
        assert transport._force_reconnect.await_count == 2

    @pytest.mark.asyncio
    async def test_permanent_read_failure_raises_typed_error(self) -> None:
        """Permanent connection failure raises TransportWriteError, bounded."""
        transport = _make_write_test_transport()

        mock_read = AsyncMock(side_effect=TransportReadError("Socket error: Connection lost"))
        mock_write = AsyncMock(return_value=True)
        transport._force_reconnect = AsyncMock()  # type: ignore[method-assign]

        with (
            patch.object(transport, "_read_holding_registers", mock_read),
            patch.object(transport, "_write_holding_registers", mock_write),
            patch("asyncio.sleep", AsyncMock()),
            pytest.raises(TransportWriteError) as exc_info,
        ):
            await transport.write_named_parameters({"FUNC_GREEN_EN": True})

        # Bounded: default write_retries=2 -> 3 sequence attempts
        assert mock_read.call_count == 3
        mock_write.assert_not_called()
        assert "FUNC_GREEN_EN" in str(exc_info.value)
        assert "3 attempts" in str(exc_info.value)
        # Chained for diagnostics, and still a TransportError so the hybrid
        # transport's cloud fallback dispatch keeps working.
        assert isinstance(exc_info.value.__cause__, TransportReadError)
        assert isinstance(exc_info.value, TransportError)

    @pytest.mark.asyncio
    async def test_permanent_write_failure_rereads_each_attempt(self) -> None:
        """Write step fails permanently: each retry re-reads, then typed error."""
        transport = _make_write_test_transport()

        mock_read = AsyncMock(return_value=[0x0000])
        mock_write = AsyncMock(side_effect=TransportWriteError("Socket error: Connection lost"))
        transport._force_reconnect = AsyncMock()  # type: ignore[method-assign]

        with (
            patch.object(transport, "_read_holding_registers", mock_read),
            patch.object(transport, "_write_holding_registers", mock_write),
            patch("asyncio.sleep", AsyncMock()),
            pytest.raises(TransportWriteError),
        ):
            await transport.write_named_parameters({"FUNC_EPS_EN": True})

        # Every sequence attempt must re-read before re-writing.
        assert mock_read.call_count == 3
        assert mock_write.call_count == 3

    @pytest.mark.asyncio
    async def test_reconnect_failure_counts_as_attempt(self) -> None:
        """TransportConnectionError from a failed reconnect is retried too."""
        transport = _make_write_test_transport()

        read_results: list[object] = [
            TransportConnectionError("Failed to connect after 3 attempts"),
            [0x0000],  # fresh read after successful reconnect
            [0x0001],  # verification read
        ]
        mock_read = AsyncMock(side_effect=read_results)
        mock_write = AsyncMock(return_value=True)
        transport._force_reconnect = AsyncMock()  # type: ignore[method-assign]

        with (
            patch.object(transport, "_read_holding_registers", mock_read),
            patch.object(transport, "_write_holding_registers", mock_write),
            patch("asyncio.sleep", AsyncMock()),
        ):
            result = await transport.write_named_parameters({"FUNC_EPS_EN": True})

        assert result is True
        mock_write.assert_called_once_with(21, [0x0001])

    @pytest.mark.asyncio
    async def test_plain_value_parameter_drop_on_write(self) -> None:
        """Non-bit-field parameter (no RMW read) retries the write after a drop."""
        transport = _make_write_test_transport()

        write_results: list[object] = [
            TransportWriteError("Socket error: Connection lost"),
            True,
        ]
        mock_read = AsyncMock(return_value=[80])  # verification read
        mock_write = AsyncMock(side_effect=write_results)
        transport._force_reconnect = AsyncMock()  # type: ignore[method-assign]

        with (
            patch.object(transport, "_read_holding_registers", mock_read),
            patch.object(transport, "_write_holding_registers", mock_write),
            patch("asyncio.sleep", AsyncMock()),
        ):
            result = await transport.write_named_parameters({"HOLD_AC_CHARGE_SOC_LIMIT": 80})

        assert result is True
        assert mock_write.call_args_list[0].args == (67, [80])
        assert mock_write.call_args_list[1].args == (67, [80])

    @pytest.mark.asyncio
    async def test_unknown_parameter_raises_immediately_no_retry(self) -> None:
        """ValueError for an unknown parameter is not retried or wrapped."""
        transport = _make_write_test_transport()

        mock_read = AsyncMock(return_value=[0x0000])
        mock_write = AsyncMock(return_value=True)
        transport._force_reconnect = AsyncMock()  # type: ignore[method-assign]

        with (
            patch.object(transport, "_read_holding_registers", mock_read),
            patch.object(transport, "_write_holding_registers", mock_write),
            pytest.raises(ValueError, match="Unknown parameter name"),
        ):
            await transport.write_named_parameters({"FUNC_DOES_NOT_EXIST": True})

        mock_read.assert_not_called()
        mock_write.assert_not_called()
        transport._force_reconnect.assert_not_awaited()


class TestDongleWriteVerification:
    """Post-write readback verification of named parameter writes."""

    @pytest.mark.asyncio
    async def test_verification_mismatch_accepts_with_warning(self) -> None:
        """Readback difference is DIAGNOSTIC-only: accept, never re-write.

        The inverter may clamp/round values, or a concurrent writer (cloud
        server, parallel-group register propagation) may have changed the
        register between ACK and readback. Re-writing would fight that
        writer in a loop (review) — exactly one write, warn, accept.
        """
        transport = _make_write_test_transport()

        # RMW read -> [0], verification read -> [0] (bit 0 "didn't stick").
        mock_read = AsyncMock(return_value=[0x0000])
        mock_write = AsyncMock(return_value=True)
        transport._force_reconnect = AsyncMock()  # type: ignore[method-assign]

        with (
            patch.object(transport, "_read_holding_registers", mock_read),
            patch.object(transport, "_write_holding_registers", mock_write),
            patch("asyncio.sleep", AsyncMock()),
        ):
            result = await transport.write_named_parameters({"FUNC_EPS_EN": True})

        assert result is True
        # Exactly ONE write — no rewrite war against a concurrent writer.
        mock_write.assert_awaited_once()
        # Healthy connection: a readback difference must NOT force reconnect.
        transport._force_reconnect.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_verification_read_failure_is_lenient(self) -> None:
        """If the verification read itself fails, the ACKed write is accepted."""
        transport = _make_write_test_transport()

        read_results: list[object] = [
            [0x0000],  # RMW read
            TransportReadError("Socket error: Connection lost"),  # verify read fails
        ]
        mock_read = AsyncMock(side_effect=read_results)
        mock_write = AsyncMock(return_value=True)

        with (
            patch.object(transport, "_read_holding_registers", mock_read),
            patch.object(transport, "_write_holding_registers", mock_write),
            patch("asyncio.sleep", AsyncMock()),
        ):
            result = await transport.write_named_parameters({"FUNC_EPS_EN": True})

        assert result is True
        mock_write.assert_called_once_with(21, [0x0001])

    @pytest.mark.asyncio
    async def test_verification_disabled(self) -> None:
        """verify_writes=False skips the readback entirely."""
        transport = _make_write_test_transport(verify_writes=False)

        mock_read = AsyncMock(return_value=[0x0000])
        mock_write = AsyncMock(return_value=True)

        with (
            patch.object(transport, "_read_holding_registers", mock_read),
            patch.object(transport, "_write_holding_registers", mock_write),
        ):
            result = await transport.write_named_parameters({"FUNC_EPS_EN": True})

        assert result is True
        # Only the RMW read — no verification read.
        assert mock_read.call_count == 1

    @pytest.mark.asyncio
    async def test_verification_passes_multibit_field(self) -> None:
        """Multi-bit MIDBOX field (2 bits/port) verifies via masked compare."""
        transport = _make_write_test_transport()
        transport._device_type = "MIDBOX"  # type: ignore[attr-defined]

        # Reg 20 current value 0b0100 (port 2 = smart_load); set port 1 = 2
        # (ac_couple) -> expect write of 0b0110.
        read_results: list[object] = [
            [0b0100],  # RMW read
            [0b0110],  # verification read
        ]
        mock_read = AsyncMock(side_effect=read_results)
        mock_write = AsyncMock(return_value=True)

        with (
            patch.object(transport, "_read_holding_registers", mock_read),
            patch.object(transport, "_write_holding_registers", mock_write),
            patch("asyncio.sleep", AsyncMock()),
        ):
            result = await transport.write_named_parameters({"BIT_MIDBOX_SP_MODE_1": 2})

        assert result is True
        mock_write.assert_called_once_with(20, [0b0110])

    @pytest.mark.asyncio
    async def test_verification_skipped_when_not_cheap(self) -> None:
        """Writes spanning many registers skip the readback (not cheap)."""
        transport = _make_write_test_transport()

        mock_read = AsyncMock(return_value=[0x0000])
        mock_write = AsyncMock(return_value=True)

        with (
            patch.object(transport, "_read_holding_registers", mock_read),
            patch.object(transport, "_write_holding_registers", mock_write),
        ):
            result = await transport.write_named_parameters(
                {
                    "HOLD_AC_CHARGE_SOC_LIMIT": 80,  # reg 67
                    "HOLD_DISCHG_CUT_OFF_SOC_EOD": 20,  # reg 105
                    "HOLD_SOC_LOW_LIMIT_EPS_DISCHG": 10,  # reg 125
                    "HOLD_FORCED_CHG_POWER_CMD": 50,  # reg 74
                }
            )

        assert result is True
        # No RMW reads (plain values) and no verification reads.
        mock_read.assert_not_called()


class TestDongleSendReceiveTimeoutRetry:
    """Request-level timeout retry for write operations in _send_receive."""

    def _connected_transport(self) -> DongleTransport:
        transport = _make_write_test_transport()
        transport._reader = AsyncMock()
        writer = AsyncMock()
        writer.write = MagicMock()
        writer.close = MagicMock()
        transport._writer = writer
        return transport

    @pytest.mark.asyncio
    async def test_write_timeout_reconnects_and_retries(self) -> None:
        """A write request that times out tears down, reconnects, and retries."""
        transport = self._connected_transport()
        assert transport._reader is not None
        transport._reader.read = AsyncMock(side_effect=TimeoutError())

        write_echo = _build_mock_response(
            modbus_func=MODBUS_WRITE_SINGLE,
            start_register=110,
            register_values=[0x0100],
        )

        second_reader = AsyncMock()
        second_reader.read = AsyncMock(side_effect=[b"", write_echo])
        second_writer = AsyncMock()
        second_writer.write = MagicMock()
        second_writer.close = MagicMock()

        async def mock_connect() -> None:
            transport._connected = True
            transport._reader = second_reader
            transport._writer = second_writer

        transport.connect = AsyncMock(side_effect=mock_connect)  # type: ignore[method-assign]

        with patch("asyncio.sleep", AsyncMock()):
            result = await transport._send_receive(
                b"\x00" * 10,
                expected_func=MODBUS_WRITE_SINGLE,
                expected_register=110,
                retry_on_timeout=True,
            )

        assert result  # parsed echo
        transport.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_write_timeout_exhausted_raises_timeout_error(self) -> None:
        """Persistent timeouts still raise TransportTimeoutError after retries."""
        transport = self._connected_transport()
        assert transport._reader is not None
        transport._reader.read = AsyncMock(side_effect=TimeoutError())

        async def mock_connect() -> None:
            transport._connected = True
            reader = AsyncMock()
            reader.read = AsyncMock(side_effect=TimeoutError())
            transport._reader = reader
            writer = AsyncMock()
            writer.write = MagicMock()
            writer.close = MagicMock()
            transport._writer = writer

        transport.connect = AsyncMock(side_effect=mock_connect)  # type: ignore[method-assign]

        with (
            patch("asyncio.sleep", AsyncMock()),
            pytest.raises(TransportTimeoutError),
        ):
            await transport._send_receive(
                b"\x00" * 10,
                max_retries=2,
                retry_on_timeout=True,
            )

        assert transport.connect.await_count == 2

    @pytest.mark.asyncio
    async def test_read_timeout_still_fails_fast(self) -> None:
        """Read requests keep fail-fast timeout behavior (no in-call retry).

        The connection must still be torn down (#226): the next request —
        not this one — reconnects on a fresh socket.
        """
        transport = self._connected_transport()
        assert transport._reader is not None
        transport._reader.read = AsyncMock(side_effect=TimeoutError())
        transport.connect = AsyncMock()  # type: ignore[method-assign]

        with pytest.raises(TransportTimeoutError):
            await transport._send_receive(b"\x00" * 10)

        transport.connect.assert_not_awaited()
        # Timeout tears down even without in-call retry: the socket is
        # suspect (half-open path loss delivers no RST) and must never be
        # reused by the next request.
        assert transport.is_connected is False
        assert transport._writer is None
        assert transport._reader is None


class TestWriteAckEchoValidation:
    """FC06/FC16 ACK payload validation in _write_holding_registers (review).

    Serial/function/register cross-checks already reject most misrouted
    responses; the echoed payload pin closes the residual hole where a
    misrouted ACK for the SAME register carries a different value.
    """

    def _connected_transport(self) -> DongleTransport:
        from pylxpweb.devices.inverters._features import InverterFamily

        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
            inverter_family=InverterFamily.EG4_HYBRID,
            write_step_delay=0,
        )
        transport._connected = True
        reader = AsyncMock()
        writer = AsyncMock()
        writer.write = MagicMock()
        writer.close = MagicMock()
        transport._reader = reader
        transport._writer = writer
        return transport

    @pytest.mark.asyncio
    async def test_fc06_echo_match_succeeds(self) -> None:
        transport = self._connected_transport()
        echo = _build_mock_response(
            modbus_func=MODBUS_WRITE_SINGLE,
            start_register=110,
            register_values=[0x0100],
        )
        # First read = drain (empty), second read = the actual ACK frame.
        transport._reader.read = AsyncMock(side_effect=[b"", echo])

        with patch("asyncio.sleep", AsyncMock()):
            assert await transport._write_holding_registers(110, [0x0100]) is True

    @pytest.mark.asyncio
    async def test_fc06_echo_mismatch_raises(self) -> None:
        """Misrouted same-register ACK with a different value is rejected."""
        transport = self._connected_transport()
        echo = _build_mock_response(
            modbus_func=MODBUS_WRITE_SINGLE,
            start_register=110,
            register_values=[0x0BAD],
        )
        # First read = drain (empty), second read = the actual ACK frame.
        transport._reader.read = AsyncMock(side_effect=[b"", echo])

        with (
            patch("asyncio.sleep", AsyncMock()),
            pytest.raises(TransportWriteError, match="echo mismatch"),
        ):
            await transport._write_holding_registers(110, [0x0100])

    @pytest.mark.asyncio
    async def test_fc16_count_mismatch_raises(self) -> None:
        """FC16 ACK echoing a wrong register count is rejected."""
        transport = self._connected_transport()
        echo = _build_mock_response(
            modbus_func=MODBUS_WRITE_MULTI,
            start_register=110,
            register_values=[5],
        )
        # First read = drain (empty), second read = the actual ACK frame.
        transport._reader.read = AsyncMock(side_effect=[b"", echo])

        with (
            patch("asyncio.sleep", AsyncMock()),
            pytest.raises(TransportWriteError, match="count mismatch"),
        ):
            await transport._write_holding_registers(110, [1, 2])

    @pytest.mark.asyncio
    async def test_real_ack_fc06_echo_match_succeeds(self) -> None:
        """Real-layout FC06 ACK (no byte_count header) echoing our value passes."""
        transport = self._connected_transport()
        ack = _build_write_ack_frame(MODBUS_WRITE_SINGLE, 110, 0x0100)
        transport._reader.read = AsyncMock(side_effect=[b"", ack])

        with patch("asyncio.sleep", AsyncMock()):
            assert await transport._write_holding_registers(110, [0x0100]) is True

    @pytest.mark.asyncio
    async def test_real_ack_fc06_echo_mismatch_raises(self) -> None:
        """Real-layout FC06 ACK with a different echoed value is rejected."""
        transport = self._connected_transport()
        ack = _build_write_ack_frame(MODBUS_WRITE_SINGLE, 110, 0x0BAD)
        transport._reader.read = AsyncMock(side_effect=[b"", ack])

        with (
            patch("asyncio.sleep", AsyncMock()),
            pytest.raises(TransportWriteError, match="echo mismatch"),
        ):
            await transport._write_holding_registers(110, [0x0100])

    @pytest.mark.asyncio
    async def test_real_ack_fc16_count_match_succeeds(self) -> None:
        """Real-layout FC16 ACK echoing the written register count passes."""
        transport = self._connected_transport()
        ack = _build_write_ack_frame(MODBUS_WRITE_MULTI, 110, 2)
        transport._reader.read = AsyncMock(side_effect=[b"", ack])

        with patch("asyncio.sleep", AsyncMock()):
            assert await transport._write_holding_registers(110, [1, 2]) is True

    @pytest.mark.asyncio
    async def test_real_ack_fc16_count_mismatch_raises(self) -> None:
        """Real-layout FC16 ACK echoing a wrong register count is rejected."""
        transport = self._connected_transport()
        ack = _build_write_ack_frame(MODBUS_WRITE_MULTI, 110, 5)
        transport._reader.read = AsyncMock(side_effect=[b"", ack])

        with (
            patch("asyncio.sleep", AsyncMock()),
            pytest.raises(TransportWriteError, match="count mismatch"),
        ):
            await transport._write_holding_registers(110, [1, 2])

    @pytest.mark.asyncio
    async def test_write_timeout_propagates_without_inner_resend(self) -> None:
        """Write timeout tears down and raises — NO request-level resend.

        Resending the same pre-built packet after a mute ACK could replay
        stale bit-field values over a concurrent writer's change (review);
        the sequence-level retry in write_named_parameters re-reads first.
        """
        transport = self._connected_transport()
        transport._reader.read = AsyncMock(side_effect=TimeoutError())
        transport.connect = AsyncMock()  # type: ignore[method-assign]

        with (
            patch("asyncio.sleep", AsyncMock()),
            pytest.raises(TransportTimeoutError),
        ):
            await transport._write_holding_registers(110, [0x0100])

        # No inner reconnect/resend — teardown only, sequence retry re-reads.
        transport.connect.assert_not_awaited()
        assert transport.is_connected is False


class TestInheritedReadsHoldOpLock:
    """Review: inherited multi-request reads must hold _op_lock too."""

    def _transport(self) -> DongleTransport:
        from pylxpweb.devices.inverters._features import InverterFamily

        return DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
            inverter_family=InverterFamily.EG4_HYBRID,
        )

    @pytest.mark.asyncio
    async def test_read_energy_holds_op_lock(self) -> None:
        transport = self._transport()
        held: list[bool] = []

        async def fake_read(start: int, count: int) -> list[int]:
            held.append(transport._op_lock._owner is not None)
            return [0] * count

        with patch.object(transport, "_read_input_registers", side_effect=fake_read):
            await transport.read_energy()

        assert held and all(held)

    @pytest.mark.asyncio
    async def test_read_serial_number_holds_op_lock(self) -> None:
        transport = self._transport()
        held: list[bool] = []

        async def fake_read(start: int, count: int) -> list[int]:
            held.append(transport._op_lock._owner is not None)
            return [0x4143] * count

        with patch.object(transport, "_read_input_registers", side_effect=fake_read):
            await transport.read_serial_number()

        assert held and all(held)


class TestDongleForceReconnect:
    """Teardown semantics of _force_reconnect."""

    @pytest.mark.asyncio
    async def test_force_reconnect_tears_down_connection(self) -> None:
        """_force_reconnect closes the socket and marks disconnected."""
        transport = _make_write_test_transport()
        writer = MagicMock()
        writer.close = MagicMock()
        transport._writer = writer
        transport._reader = AsyncMock()

        await transport._force_reconnect()

        assert transport.is_connected is False
        assert transport._reader is None
        assert transport._writer is None
        writer.close.assert_called_once()

    def test_write_resilience_defaults(self) -> None:
        """Constructor exposes configurable write resilience knobs."""
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )
        assert transport._write_retries == 2
        assert transport._write_step_delay == pytest.approx(0.2)
        assert transport._verify_writes is True

    @pytest.mark.asyncio
    async def test_write_step_delay_applied_before_write(self) -> None:
        """The configurable inter-step delay runs before each write request."""
        transport = _make_write_test_transport(write_step_delay=0.05, verify_writes=False)

        mock_read = AsyncMock(return_value=[0x0000])
        mock_send = AsyncMock(return_value=[])
        sleep_mock = AsyncMock()

        with (
            patch.object(transport, "_read_holding_registers", mock_read),
            patch.object(transport, "_send_receive", mock_send),
            patch("pylxpweb.transports.dongle.asyncio.sleep", sleep_mock),
        ):
            result = await transport.write_named_parameters({"FUNC_EPS_EN": True})

        assert result is True
        assert any(call.args == (0.05,) for call in sleep_mock.await_args_list)


class _ScriptedDongleServer:
    """Local TCP server emulating a WiFi dongle for path-loss scenarios.

    Modes:
        "reply": respond to every request with a valid register frame.
        "mute":  swallow requests and never respond, keeping the socket
                 open — the application-level equivalent of silent path
                 loss (writes succeed, reads only ever time out; no RST
                 or FIN is ever delivered).
    """

    def __init__(self, response: bytes) -> None:
        self._response = response
        self._server: asyncio.Server | None = None
        self.mode = "reply"
        self.accepted = 0
        self.requests_received = 0

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        sockets = self._server.sockets
        assert sockets
        return int(sockets[0].getsockname()[1])

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.accepted += 1
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                self.requests_received += 1
                if self.mode == "reply":
                    writer.write(self._response)
                    await writer.drain()
                # mode == "mute": swallow the request, never respond
        except (ConnectionError, OSError):
            pass
        finally:
            with contextlib.suppress(Exception):
                writer.close()


class TestDongleSilentPathLoss:
    """Half-open / silent path loss scenarios (#226, eg4-mu7o).

    A VPN drop or NAT/conntrack flush kills the path WITHOUT delivering a
    RST or FIN: the established socket stays ESTABLISHED, writes buffer
    into a black hole, and reads only ever time out.  Recovery is only
    possible on a FRESH connection — the transport must tear down on
    timeout and reconnect on the next request, never reuse the dead flow.
    """

    def _transport(self, port: int, timeout: float = 0.2) -> DongleTransport:
        return DongleTransport(
            host="127.0.0.1",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
            port=port,
            timeout=timeout,
            connection_retries=1,
        )

    @pytest.mark.asyncio
    async def test_half_open_read_timeout_tears_down(self) -> None:
        """(a) Half-open socket: read times out, write succeeds.

        The request must fail fast with TransportTimeoutError AND tear the
        connection down (old code kept the dead socket installed forever).
        The per-transaction lock must be released.
        """
        response = _build_mock_response(start_register=0, register_values=[1, 2])
        server = _ScriptedDongleServer(response)
        port = await server.start()
        transport = self._transport(port)
        try:
            await transport.connect()
            assert transport.is_connected is True

            # Path loss: server goes mute (socket stays open, no RST/FIN)
            server.mode = "mute"

            with pytest.raises(TransportTimeoutError):
                await transport._read_input_registers(0, 2)

            # The write DID reach the socket (half-open: writes succeed)
            assert server.requests_received >= 1
            # Teardown: the dead flow must never be reused
            assert transport.is_connected is False
            assert transport._writer is None
            assert transport._reader is None
            # Lock released — no leak on the timeout exception path
            assert transport._lock.locked() is False
        finally:
            await transport.disconnect()
            await server.stop()

    @pytest.mark.asyncio
    async def test_recovery_after_path_restoration(self) -> None:
        """(d) After restoration the next poll dials a FRESH connection.

        Healthy poll → silent loss (timeout, teardown) → path restored →
        next poll reconnects (server sees a SECOND accept) and succeeds
        without any reload/external intervention.
        """
        response = _build_mock_response(start_register=0, register_values=[7, 8])
        server = _ScriptedDongleServer(response)
        port = await server.start()
        transport = self._transport(port)
        try:
            await transport.connect()
            assert await transport._read_input_registers(0, 2) == [7, 8]
            assert server.accepted == 1

            # Silent path loss
            server.mode = "mute"
            with pytest.raises(TransportTimeoutError):
                await transport._read_input_registers(0, 2)
            assert transport.is_connected is False

            # Path restored
            server.mode = "reply"

            # Next poll reconnects on a fresh socket and succeeds
            assert await transport._read_input_registers(0, 2) == [7, 8]
            assert server.accepted == 2
            assert transport.is_connected is True
        finally:
            await transport.disconnect()
            await server.stop()

    @pytest.mark.asyncio
    async def test_connect_hang_times_out_and_releases_lock(self) -> None:
        """(b) A hanging connect() (SYN black hole) is bounded by timeout.

        asyncio.open_connection never completes; the wait_for wrapper must
        bound each attempt, the failure must leave clean state, and the
        per-transaction lock must be released so a later request (after
        restoration) succeeds.
        """
        transport = DongleTransport(
            host="127.0.0.1",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
            port=1,
            timeout=0.05,
            connection_retries=2,
        )
        # Simulate a prior teardown (e.g. after a read timeout)
        transport._connected = False
        transport._reader = None
        transport._writer = None

        async def hang(*args: object, **kwargs: object) -> object:
            await asyncio.Event().wait()

        with (
            patch("asyncio.open_connection", side_effect=hang),
            patch("asyncio.sleep", AsyncMock()),
            pytest.raises(TransportConnectionError, match="Timeout"),
        ):
            await transport._send_receive(b"\x00" * 10)

        assert transport.is_connected is False
        assert transport._writer is None
        assert transport._lock.locked() is False

        # Restoration: a later request connects and completes normally
        response = _build_mock_response(start_register=0, register_values=[5])
        server = _ScriptedDongleServer(response)
        port = await server.start()
        transport._port = port
        try:
            assert await transport._read_input_registers(0, 1) == [5]
        finally:
            await transport.disconnect()
            await server.stop()

    @pytest.mark.asyncio
    async def test_connect_refused_fails_fast_with_clean_state(self) -> None:
        """(c) Connection refused: bounded fail-fast, clean state, no leak."""
        transport = DongleTransport(
            host="127.0.0.1",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
            port=1,
            timeout=0.05,
            connection_retries=2,
        )
        transport._connected = False

        open_mock = AsyncMock(side_effect=ConnectionRefusedError("refused"))
        with (
            patch("asyncio.open_connection", open_mock),
            patch("asyncio.sleep", AsyncMock()),
            pytest.raises(TransportConnectionError, match="Failed to connect"),
        ):
            await transport._send_receive(b"\x00" * 10)

        # connect() did its own bounded retries; the request failed fast
        # after ONE connect cycle (no outer retry multiplication).
        assert open_mock.await_count == 2
        assert transport.is_connected is False
        assert transport._lock.locked() is False

    @pytest.mark.asyncio
    async def test_partial_connect_failure_leaves_clean_state(self) -> None:
        """connect(): socket opens but initial-data discard hits OSError.

        Old code marked _connected=True BEFORE the initial-data read, so a
        partial failure could exit connect() via TransportConnectionError
        with _connected still True and a stale reader/writer installed —
        subsequent requests then skipped reconnection and used the dead
        socket.  Now every failure path tears down.
        """
        transport = DongleTransport(
            host="127.0.0.1",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
            timeout=0.05,
            connection_retries=2,
        )

        bad_reader = AsyncMock()
        bad_reader.read = AsyncMock(side_effect=OSError("reset during initial read"))
        bad_writer = MagicMock()
        bad_writer.close = MagicMock()

        open_mock = AsyncMock(
            side_effect=[(bad_reader, bad_writer), ConnectionRefusedError("refused")]
        )

        with (
            patch("asyncio.open_connection", open_mock),
            patch("asyncio.sleep", AsyncMock()),
            pytest.raises(TransportConnectionError),
        ):
            await transport.connect()

        assert transport.is_connected is False
        assert transport._reader is None
        assert transport._writer is None
        # The partially-opened socket was closed, not leaked
        bad_writer.close.assert_called()

    @pytest.mark.asyncio
    async def test_empty_response_reconnects_between_retries(self) -> None:
        """EOF (b'') tears down so every in-call retry dials fresh.

        recv returning b'' means the peer closed the connection — the old
        code re-read the same dead socket for all retries and left it
        installed on the final failure.
        """
        transport = DongleTransport(
            host="127.0.0.1",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )
        transport._connected = True
        eof_reader = AsyncMock()
        eof_reader.read = AsyncMock(return_value=b"")
        writer = AsyncMock()
        writer.write = MagicMock()
        writer.close = MagicMock()
        transport._reader = eof_reader
        transport._writer = writer

        reconnects = 0

        async def mock_connect() -> None:
            nonlocal reconnects
            reconnects += 1
            transport._connected = True
            fresh_reader = AsyncMock()
            fresh_reader.read = AsyncMock(return_value=b"")
            fresh_writer = AsyncMock()
            fresh_writer.write = MagicMock()
            fresh_writer.close = MagicMock()
            transport._reader = fresh_reader
            transport._writer = fresh_writer

        transport.connect = AsyncMock(side_effect=mock_connect)  # type: ignore[method-assign]

        with (
            patch("asyncio.sleep", AsyncMock()),
            pytest.raises(TransportReadError, match="Empty response"),
        ):
            await transport._send_receive(b"\x00" * 10, max_retries=2)

        # Attempt 0 used the initial socket; attempts 1 and 2 reconnected
        assert reconnects == 2
        # Final EOF tore down: the next request will reconnect
        assert transport.is_connected is False

    @pytest.mark.asyncio
    async def test_concurrent_connect_calls_dial_once(self) -> None:
        """Parallel connect() calls serialise on the dongle's single slot.

        _send_receive reconnects under the per-transaction lock, but
        external callers (coordinator write paths) can call connect()
        directly and concurrently.  The loser of the race must return
        the winner's fresh connection, not dial a second TCP connection
        (the dongle allows exactly ONE) and not tear the winner down.
        """
        response = _build_mock_response(start_register=0, register_values=[3])
        server = _ScriptedDongleServer(response)
        port = await server.start()
        transport = self._transport(port)
        try:
            await asyncio.gather(transport.connect(), transport.connect())
            # Give the server loop a turn to register accepts
            await asyncio.sleep(0.05)
            assert transport.is_connected is True
            assert server.accepted == 1

            # The surviving connection actually works
            assert await transport._read_input_registers(0, 1) == [3]
        finally:
            await transport.disconnect()
            await server.stop()
