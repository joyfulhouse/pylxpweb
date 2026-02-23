"""WiFi Dongle TCP transport implementation.

This module provides the DongleTransport class for direct local
communication with inverters via the WiFi dongle's TCP interface
(typically port 8000).

The WiFi dongle uses a custom protocol that wraps Modbus RTU frames
in an 18-byte TCP header. This is NOT standard Modbus TCP - it uses
the LuxPower/EG4 proprietary protocol documented at:
https://github.com/celsworth/lxp-bridge/wiki/TCP-Packet-Spec

IMPORTANT: Single-Client Limitation
------------------------------------
The WiFi dongle supports only ONE concurrent TCP connection.
Running multiple clients causes connection errors and data loss.

Ensure only ONE integration/script connects to each dongle at a time.
Disable other integrations (Solar Assistant, lxp-bridge) before using.

IMPORTANT: Firmware Compatibility
---------------------------------
Recent firmware updates may block port 8000 access for security.
If connection fails, check if your dongle firmware has been updated.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import struct
from typing import TYPE_CHECKING

from ._register_data import RegisterDataMixin
from .capabilities import MODBUS_CAPABILITIES, TransportCapabilities
from .exceptions import (
    TransportConnectionError,
    TransportReadError,
    TransportTimeoutError,
    TransportWriteError,
)
from .protocol import BaseTransport

if TYPE_CHECKING:
    from pylxpweb.devices.inverters._features import InverterFamily

_LOGGER = logging.getLogger(__name__)

# Protocol constants
PACKET_PREFIX = bytes([0xA1, 0x1A])  # Magic prefix for all packets
PROTOCOL_VERSION = 1  # Protocol version (little-endian uint16)
TCP_FUNC_HEARTBEAT = 0xC1  # Heartbeat/keepalive
TCP_FUNC_TRANSLATED = 0xC2  # Translated Modbus data
TCP_FUNC_READ_PARAM = 0xC3  # Read parameters
TCP_FUNC_WRITE_PARAM = 0xC4  # Write parameters

# Modbus function codes (embedded in TCP_FUNC_TRANSLATED)
MODBUS_READ_HOLDING = 0x03  # Read holding registers
MODBUS_READ_INPUT = 0x04  # Read input registers
MODBUS_WRITE_SINGLE = 0x06  # Write single holding register
MODBUS_WRITE_MULTI = 0x10  # Write multiple holding registers

# Default connection settings
DEFAULT_PORT = 8000
DEFAULT_TIMEOUT = 10.0
RECV_BUFFER_SIZE = 4096


def compute_crc16(data: bytes) -> int:
    """Compute CRC-16/Modbus checksum.

    Args:
        data: Bytes to compute CRC for

    Returns:
        16-bit CRC value
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


class DongleTransport(RegisterDataMixin, BaseTransport):
    """WiFi Dongle TCP transport for local inverter communication.

    This transport connects directly to the inverter's WiFi dongle
    via TCP port 8000 using the LuxPower/EG4 proprietary protocol.

    IMPORTANT: Single-Client Limitation
    ------------------------------------
    The WiFi dongle supports only ONE concurrent TCP connection.
    Disable other integrations before using this transport.

    Example:
        transport = DongleTransport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )
        await transport.connect()

        runtime = await transport.read_runtime()
        print(f"PV Power: {runtime.pv_total_power}W")

    Note:
        Unlike ModbusTransport, this does NOT require pymodbus.
        The protocol is implemented using pure asyncio sockets.
    """

    transport_type: str = "wifi_dongle"

    def __init__(
        self,
        host: str,
        dongle_serial: str,
        inverter_serial: str,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
        inverter_family: InverterFamily | None = None,
        connection_retries: int = 3,
    ) -> None:
        """Initialize WiFi Dongle transport.

        Args:
            host: IP address or hostname of the WiFi dongle
            dongle_serial: 10-character dongle serial number (e.g., "BA12345678")
            inverter_serial: 10-character inverter serial number (e.g., "CE12345678")
            port: TCP port (default 8000)
            timeout: Connection and operation timeout in seconds
            inverter_family: Inverter model family for correct register mapping.
                If None, defaults to PV_SERIES (EG4-18KPV) for backward
                compatibility.
            connection_retries: Number of connection retry attempts with backoff
        """
        super().__init__(inverter_serial)
        self._host = host
        self._port = port
        self._dongle_serial = dongle_serial
        self._timeout = timeout
        self._inverter_family = inverter_family
        self._connection_retries = connection_retries
        self._inter_register_delay = 0.5  # Dongle needs slower pace than Modbus
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._transaction_id = 0

    @property
    def capabilities(self) -> TransportCapabilities:
        """Get dongle transport capabilities (same as Modbus)."""
        return MODBUS_CAPABILITIES

    @property
    def host(self) -> str:
        """Get the dongle host address."""
        return self._host

    @property
    def port(self) -> int:
        """Get the dongle TCP port."""
        return self._port

    @property
    def dongle_serial(self) -> str:
        """Get the dongle serial number."""
        return self._dongle_serial

    @property
    def inverter_family(self) -> InverterFamily | None:
        """Get the inverter family for register mapping."""
        return self._inverter_family

    @inverter_family.setter
    def inverter_family(self, value: InverterFamily | None) -> None:
        """Set the inverter family for register mapping.

        This allows updating the family after auto-detection from device type code,
        ensuring the correct register map is used even if the initial family was
        wrong or defaulted.

        Args:
            value: The detected or configured inverter family
        """
        if value != self._inverter_family:
            _LOGGER.debug(
                "Updating inverter family from %s to %s for %s",
                self._inverter_family,
                value,
                self._serial,
            )
        self._inverter_family = value

    async def _discard_initial_data(self) -> None:
        """Discard any initial data sent by the dongle after connection.

        Some dongles send unsolicited packets immediately after connection.
        This data must be discarded to avoid confusing subsequent protocol
        exchanges. We wait up to 1 second for any initial data.
        """
        if not self._reader:
            return

        try:
            # Wait up to 1 second for any initial data and discard it
            initial_data = await asyncio.wait_for(
                self._reader.read(512),
                timeout=1.0,
            )
            if initial_data:
                _LOGGER.debug(
                    "Discarded %d bytes of initial data from dongle: %s",
                    len(initial_data),
                    initial_data.hex()[:100],  # Log first 50 bytes
                )
        except TimeoutError:
            # No initial data - this is fine
            _LOGGER.debug("No initial data from dongle (expected for some models)")

    async def connect(self) -> None:
        """Establish TCP connection to the WiFi dongle with retry and backoff.

        The dongle only allows one TCP connection at a time. If connection fails,
        retries with exponential backoff (1s, 2s, 4s, ...) to handle cases where
        a previous connection wasn't properly released.

        Raises:
            TransportConnectionError: If all connection attempts fail
        """
        last_error: Exception | None = None
        retry_delay = 1.0  # Start with 1 second delay

        for attempt in range(self._connection_retries):
            try:
                if attempt > 0:
                    _LOGGER.info(
                        "Connection retry %d/%d to %s:%s (waiting %.1fs)...",
                        attempt,
                        self._connection_retries - 1,
                        self._host,
                        self._port,
                        retry_delay,
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff

                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port),
                    timeout=self._timeout,
                )

                self._connected = True
                _LOGGER.info(
                    "Dongle transport connected to %s:%s (dongle=%s, inverter=%s)%s",
                    self._host,
                    self._port,
                    self._dongle_serial,
                    self._serial,
                    f" after {attempt} retries" if attempt > 0 else "",
                )

                # Discard any initial data the dongle sends after connection
                # Some dongles send unsolicited packets that can confuse subsequent reads
                # This is a known behavior documented in luxpower-ha-integration
                await self._discard_initial_data()
                return  # Success!

            except TimeoutError as err:
                last_error = err
                _LOGGER.warning(
                    "Timeout connecting to dongle at %s:%s (attempt %d/%d)",
                    self._host,
                    self._port,
                    attempt + 1,
                    self._connection_retries,
                )
            except (OSError, ConnectionRefusedError) as err:
                last_error = err
                _LOGGER.warning(
                    "Connection failed to %s:%s: %s (attempt %d/%d)",
                    self._host,
                    self._port,
                    err,
                    attempt + 1,
                    self._connection_retries,
                )

        # All retries exhausted
        if isinstance(last_error, TimeoutError):
            raise TransportConnectionError(
                f"Timeout connecting to {self._host}:{self._port} after "
                f"{self._connection_retries} attempts. "
                "Verify: (1) IP address is correct, (2) dongle is on network, "
                "(3) port 8000 is not blocked by firmware."
            ) from last_error
        else:
            raise TransportConnectionError(
                f"Failed to connect to {self._host}:{self._port} after "
                f"{self._connection_retries} attempts: {last_error}. "
                "Verify: (1) IP address is correct, (2) dongle is accessible, "
                "(3) no other client is connected (dongle allows only ONE connection)."
            ) from last_error

    async def disconnect(self) -> None:
        """Close TCP connection to the dongle.

        Uses timeout on wait_closed() to prevent hanging if the connection
        is in a bad state. The dongle only supports one connection at a time,
        so proper cleanup is essential.
        """
        if self._writer:
            try:
                self._writer.close()
                # Use timeout to prevent indefinite hang if connection is stuck
                await asyncio.wait_for(self._writer.wait_closed(), timeout=5.0)
            except TimeoutError:
                _LOGGER.warning(
                    "Timeout waiting for connection close to %s:%s",
                    self._host,
                    self._port,
                )
            except Exception:  # noqa: BLE001
                pass  # Ignore other errors during disconnect

        self._reader = None
        self._writer = None
        self._connected = False
        _LOGGER.debug("Dongle transport disconnected for %s", self._serial)

    def _build_packet(
        self,
        tcp_func: int,
        modbus_func: int,
        start_register: int,
        register_count: int = 0,
        values: list[int] | None = None,
    ) -> bytes:
        """Build a LuxPower protocol packet.

        Packet structure (38 bytes for read, varies for write):
        - Bytes 0-1: Prefix (0xA1, 0x1A)
        - Bytes 2-3: Protocol version (1, little-endian)
        - Bytes 4-5: Frame length (little-endian)
        - Byte 6: Address (0x01)
        - Byte 7: TCP function code
        - Bytes 8-17: Dongle serial (10 bytes ASCII)
        - Bytes 18-19: Data length (little-endian)
        - Bytes 20+: Data frame (16+ bytes)
        - Last 2 bytes: CRC-16 of data frame

        Args:
            tcp_func: TCP function code (0xC2 for translated Modbus)
            modbus_func: Modbus function code (0x03, 0x04, 0x06, 0x10)
            start_register: Starting register address
            register_count: Number of registers (for read operations)
            values: Values to write (for write operations)

        Returns:
            Complete packet bytes
        """
        # Encode serial numbers as bytes
        dongle_bytes = self._dongle_serial.encode("ascii").ljust(10, b"\x00")[:10]
        inverter_bytes = self._serial.encode("ascii").ljust(10, b"\x00")[:10]

        # Build data frame (varies by operation)
        if modbus_func == MODBUS_WRITE_SINGLE:
            # Write single: action(1) + func(1) + serial(10) + reg(2) + value(2)
            # action=0x00 for request (client to inverter), 0x01 for response
            value = values[0] if values else 0
            data_frame = bytes([0x00, modbus_func]) + inverter_bytes
            data_frame += struct.pack("<H", start_register)
            data_frame += struct.pack("<H", value)
        elif modbus_func == MODBUS_WRITE_MULTI:
            # Write multi: action(1) + func(1) + serial(10) + reg(2) + count(2) + bytes(1) + data
            # action=0x00 for request (client to inverter), 0x01 for response
            data_count = len(values) if values else 0
            byte_count = data_count * 2
            data_frame = bytes([0x00, modbus_func]) + inverter_bytes
            data_frame += struct.pack("<H", start_register)
            data_frame += struct.pack("<H", data_count)
            data_frame += bytes([byte_count])
            for value in values or []:
                data_frame += struct.pack("<H", value)
        else:
            # Read: action(1) + func(1) + serial(10) + reg(2) + count(2)
            # action=0x00 for request (client to inverter), 0x01 for response
            data_frame = bytes([0x00, modbus_func]) + inverter_bytes
            data_frame += struct.pack("<H", start_register)
            data_frame += struct.pack("<H", register_count)

        # Calculate CRC of data frame
        crc = compute_crc16(data_frame)

        # Build complete packet
        # data_length = data_frame bytes + CRC (2 bytes)
        data_length = len(data_frame) + 2
        # frame_length = bytes after the frame_length field itself
        # = addr(1) + tcp_func(1) + dongle(10) + data_length(2) + data_frame + crc
        # = 14 + data_length
        frame_length = 14 + data_length

        packet = PACKET_PREFIX
        packet += struct.pack("<H", PROTOCOL_VERSION)
        packet += struct.pack("<H", frame_length)
        packet += bytes([0x01, tcp_func])
        packet += dongle_bytes
        packet += struct.pack("<H", data_length)
        packet += data_frame
        packet += struct.pack("<H", crc)

        return packet

    async def _drain_buffer(self) -> None:
        """Drain any pending data from the receive buffer.

        The dongle may send unsolicited heartbeat packets or there may be
        stale data from previous requests. This method clears the buffer
        before sending a new request to ensure clean communication.
        """
        if not self._reader:
            return

        try:
            # Non-blocking read to drain any pending data
            while True:
                try:
                    # Very short timeout - just check if data is available
                    junk = await asyncio.wait_for(
                        self._reader.read(512),
                        timeout=0.05,  # 50ms - just check for immediate data
                    )
                    if not junk:
                        break
                    _LOGGER.debug(
                        "Drained %d bytes of pending data: %s",
                        len(junk),
                        junk.hex()[:50],
                    )
                except TimeoutError:
                    # No pending data - good!
                    break
        except Exception as err:
            _LOGGER.debug("Error draining buffer: %s", err)

    async def _send_receive(
        self,
        packet: bytes,
        max_retries: int = 2,
        expected_func: int | None = None,
        expected_register: int | None = None,
    ) -> list[int]:
        """Send a packet and receive response with retry logic.

        Auto-reconnects if the TCP connection was lost (e.g. dongle reboot,
        network glitch).  The reconnect happens once per call; if the fresh
        connection also fails the error propagates normally.

        Args:
            packet: Packet bytes to send
            max_retries: Number of retry attempts for empty responses
            expected_func: Expected Modbus function code (0x03, 0x04, 0x06, 0x10).
                When provided, rejects responses with a different function code.
                Handles exception responses (high bit set) by masking to base code.
            expected_register: Expected starting register address.
                When provided, rejects responses for a different register range.

        Returns:
            List of register values from response

        Raises:
            TransportReadError: If send/receive fails after retries
            TransportTimeoutError: If operation times out
            TransportConnectionError: If reconnection also fails
        """
        if not self._connected:
            _LOGGER.info(
                "Dongle %s:%s disconnected, attempting reconnect",
                self._host,
                self._port,
            )
            await self.connect()

        if self._writer is None or self._reader is None:
            raise TransportConnectionError("Socket not initialized")

        last_error: TransportReadError | None = None

        async with self._lock:
            for attempt in range(max_retries + 1):
                try:
                    # Drain any pending data before sending (handles unsolicited packets)
                    await self._drain_buffer()

                    # Send packet
                    self._writer.write(packet)
                    await self._writer.drain()

                    # Receive response with slightly longer timeout for dongles
                    response = await asyncio.wait_for(
                        self._reader.read(RECV_BUFFER_SIZE),
                        timeout=self._timeout,
                    )

                    if not response:
                        # Empty response - dongle may be slow or blocking requests
                        if attempt < max_retries:
                            _LOGGER.debug(
                                "Empty response from dongle (attempt %d/%d), retrying...",
                                attempt + 1,
                                max_retries + 1,
                            )
                            # Small delay before retry
                            await asyncio.sleep(0.5)
                            continue
                        # Final attempt failed
                        raise TransportReadError(
                            "Empty response from dongle. This may indicate: "
                            "(1) Dongle firmware is blocking local Modbus access, "
                            "(2) Connection was closed by dongle, or "
                            "(3) Dongle requires more time to respond. "
                            "Try increasing timeout or check dongle firmware version."
                        )

                    # Parse response with cross-request validation
                    return self._parse_response(response, expected_func, expected_register)

                except TimeoutError as err:
                    _LOGGER.error("Timeout waiting for dongle response")
                    raise TransportTimeoutError(
                        "Timeout waiting for dongle response. "
                        "Recent dongle firmware may block port 8000 for security. "
                        "Consider using Modbus TCP with RS485 adapter instead."
                    ) from err
                except OSError as err:
                    _LOGGER.error("Socket error communicating with dongle: %s", err)
                    # Mark as disconnected so next poll triggers reconnect
                    self._connected = False
                    self._reader = None
                    if self._writer:
                        with contextlib.suppress(Exception):
                            self._writer.close()
                    self._writer = None
                    raise TransportReadError(f"Socket error: {err}") from err
                except TransportReadError as err:
                    last_error = err
                    if attempt < max_retries:
                        _LOGGER.debug(
                            "Read error (attempt %d/%d): %s, retrying...",
                            attempt + 1,
                            max_retries + 1,
                            err,
                        )
                        await asyncio.sleep(0.5)
                        continue
                    raise

        # Should not reach here, but satisfy type checker
        if last_error:
            raise last_error
        raise TransportReadError("Unexpected error in send/receive")

    def _find_packet_start(self, data: bytes) -> int:
        """Find the start of a valid packet in the buffer.

        The dongle may send unsolicited heartbeat packets or there may be
        leftover data from previous responses. This method searches for
        the packet prefix (0xA1, 0x1A) to find where the actual response starts.

        Args:
            data: Buffer containing received data

        Returns:
            Index where packet starts, or -1 if not found
        """
        # Search for the packet prefix
        idx = data.find(PACKET_PREFIX)
        if idx > 0:
            _LOGGER.debug(
                "Found packet start at offset %d, discarding %d bytes of junk data: %s",
                idx,
                idx,
                data[:idx].hex()[:50],
            )
        return idx

    def _parse_response(
        self,
        response: bytes,
        expected_func: int | None = None,
        expected_register: int | None = None,
    ) -> list[int]:
        """Parse a dongle response packet with cross-request validation.

        Validates that the response matches the original request by checking
        the inverter serial, function code, and starting register address.
        This prevents accepting misrouted responses from the cloud server
        that pass through the WiFi dongle.

        Args:
            response: Raw response bytes
            expected_func: Expected Modbus function code (e.g., 0x04 for
                input register read).  When provided, rejects responses
                with a different base function code.
            expected_register: Expected starting register address.  When
                provided, rejects responses for a different register range.

        Returns:
            List of register values

        Raises:
            TransportReadError: If response is invalid or doesn't match
                the original request (serial/function/register mismatch).
        """
        # Find the packet start (handle junk data before the response)
        packet_start = self._find_packet_start(response)
        if packet_start < 0:
            raise TransportReadError(
                f"No valid packet found in response ({len(response)} bytes): "
                f"{response[:40].hex() if response else 'empty'}"
            )

        # Adjust response to start at the packet
        response = response[packet_start:]

        # Minimum response: prefix(2) + version(2) + length(2) + addr(1) + func(1)
        # + dongle(10) + data_len(2) + some data
        if len(response) < 20:
            raise TransportReadError(f"Response too short: {len(response)} bytes")

        # Extract data length (frame_length and tcp_func available at bytes 4-6 and 7 if needed)
        data_length = struct.unpack("<H", response[18:20])[0]

        # Data starts at offset 20
        data_start = 20
        data_end = data_start + data_length - 2  # -2 for CRC
        crc_start = data_end
        crc_end = crc_start + 2

        if crc_end > len(response):
            raise TransportReadError(
                f"Response truncated: expected {crc_end} bytes, got {len(response)}"
            )

        # Extract data frame and CRC
        data_frame = response[data_start:data_end]
        received_crc = struct.unpack("<H", response[crc_start:crc_end])[0]

        # Verify CRC to ensure data integrity
        computed_crc = compute_crc16(data_frame)
        if computed_crc != received_crc:
            _LOGGER.warning(
                "CRC mismatch: computed 0x%04X, received 0x%04X. "
                "Data may be corrupted. Raw response: %s",
                computed_crc,
                received_crc,
                response[:60].hex(),
            )
            raise TransportReadError(
                f"CRC verification failed: computed 0x{computed_crc:04X}, "
                f"received 0x{received_crc:04X}"
            )

        # For read responses, data frame contains:
        # - action (1 byte)
        # - modbus_func (1 byte)
        # - inverter_serial (10 bytes)
        # - start_register (2 bytes, LE)
        # - byte_count (1 byte)
        # - register_data (N bytes)
        # Total header before data: 1 + 1 + 10 + 2 + 1 = 15 bytes
        if len(data_frame) < 15:
            raise TransportReadError(f"Data frame too short: {len(data_frame)} bytes")

        modbus_func = data_frame[1]

        # --- Cross-request validation ---
        # The WiFi dongle proxies between the cloud server and the inverter.
        # Responses meant for the cloud can be misrouted to us.  These have
        # valid CRC but wrong serial/function/register.  Reject them so the
        # retry logic can resend and get the correct response.

        # 1. Inverter serial must match (always checked)
        response_serial = data_frame[2:12]
        expected_serial = self._serial.encode("ascii").ljust(10, b"\x00")[:10]
        if response_serial != expected_serial:
            resp_serial_str = response_serial.decode("ascii", errors="replace").rstrip("\x00")
            _LOGGER.debug(
                "Response serial mismatch: expected %s, got %s — likely a misrouted cloud response",
                self._serial,
                resp_serial_str,
            )
            raise TransportReadError(
                f"Response serial mismatch: expected {self._serial}, got {resp_serial_str}"
            )

        # 2. Function code must match (mask high bit for exception responses)
        if expected_func is not None:
            response_base_func = modbus_func & 0x7F
            if response_base_func != expected_func:
                _LOGGER.debug(
                    "Response function mismatch: expected 0x%02x, got 0x%02x — "
                    "likely a misrouted cloud response",
                    expected_func,
                    modbus_func,
                )
                raise TransportReadError(
                    f"Response function mismatch: expected 0x{expected_func:02x}, "
                    f"got 0x{modbus_func:02x}"
                )

        # 3. Start register must match
        if expected_register is not None:
            response_register = struct.unpack("<H", data_frame[12:14])[0]
            if response_register != expected_register:
                _LOGGER.debug(
                    "Response register mismatch: expected %d, got %d — "
                    "likely a misrouted cloud response",
                    expected_register,
                    response_register,
                )
                raise TransportReadError(
                    f"Response register mismatch: expected {expected_register}, "
                    f"got {response_register}"
                )

        # Check for Modbus exception (function code with high bit set)
        if modbus_func & 0x80:
            exception_code = data_frame[14] if len(data_frame) > 14 else 0
            raise TransportReadError(
                f"Modbus exception: function=0x{modbus_func:02x}, code={exception_code}"
            )

        # byte_count is at offset 14 (after action + func + serial + start_reg)
        byte_count = data_frame[14]

        # Extract register values (little-endian uint16)
        # Register data starts at offset 15
        register_data = data_frame[15 : 15 + byte_count]
        registers: list[int] = []

        for i in range(0, len(register_data), 2):
            if i + 1 < len(register_data):
                value = struct.unpack("<H", register_data[i : i + 2])[0]
                registers.append(value)

        return registers

    async def _read_input_registers(
        self,
        address: int,
        count: int,
    ) -> list[int]:
        """Read input registers (read-only runtime data).

        Args:
            address: Starting register address
            count: Number of registers to read (max 40)

        Returns:
            List of register values

        Raises:
            TransportReadError: If read fails
            TransportTimeoutError: If operation times out
        """
        packet = self._build_packet(
            tcp_func=TCP_FUNC_TRANSLATED,
            modbus_func=MODBUS_READ_INPUT,
            start_register=address,
            register_count=min(count, 40),
        )

        return await self._send_receive(
            packet,
            expected_func=MODBUS_READ_INPUT,
            expected_register=address,
        )

    async def _read_holding_registers(
        self,
        address: int,
        count: int,
    ) -> list[int]:
        """Read holding registers (configuration parameters).

        Args:
            address: Starting register address
            count: Number of registers to read (max 40)

        Returns:
            List of register values

        Raises:
            TransportReadError: If read fails
            TransportTimeoutError: If operation times out
        """
        packet = self._build_packet(
            tcp_func=TCP_FUNC_TRANSLATED,
            modbus_func=MODBUS_READ_HOLDING,
            start_register=address,
            register_count=min(count, 40),
        )

        return await self._send_receive(
            packet,
            expected_func=MODBUS_READ_HOLDING,
            expected_register=address,
        )

    async def _write_holding_registers(
        self,
        address: int,
        values: list[int],
    ) -> bool:
        """Write holding registers.

        Args:
            address: Starting register address
            values: List of values to write

        Returns:
            True if write succeeded

        Raises:
            TransportWriteError: If write fails
            TransportTimeoutError: If operation times out
        """
        modbus_func = MODBUS_WRITE_SINGLE if len(values) == 1 else MODBUS_WRITE_MULTI
        packet = self._build_packet(
            tcp_func=TCP_FUNC_TRANSLATED,
            modbus_func=modbus_func,
            start_register=address,
            values=values,
        )

        try:
            await self._send_receive(
                packet,
                expected_func=modbus_func,
                expected_register=address,
            )
            return True
        except TransportReadError as err:
            raise TransportWriteError(str(err)) from err

    # Data reading/writing methods (read_runtime, read_energy, read_battery,
    # read_midbox_runtime, read_parameters, write_parameters, device info)
    # are inherited from RegisterDataMixin via _register_data.py.
