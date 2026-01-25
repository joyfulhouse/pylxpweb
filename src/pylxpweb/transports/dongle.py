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
import logging
import struct
from typing import TYPE_CHECKING

from .capabilities import MODBUS_CAPABILITIES, TransportCapabilities
from .data import (
    BatteryBankData,
    InverterEnergyData,
    InverterRuntimeData,
)
from .exceptions import (
    TransportConnectionError,
    TransportReadError,
    TransportTimeoutError,
    TransportWriteError,
)
from .protocol import BaseTransport

if TYPE_CHECKING:
    from pylxpweb.devices.inverters._features import InverterFamily
    from pylxpweb.transports.register_maps import (
        EnergyRegisterMap,
        RuntimeRegisterMap,
    )

# Device type codes read from register 19
DEVICE_TYPE_REGISTER = 19
DEVICE_TYPE_MIDBOX = 50  # GridBOSS / MID device

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

# Register group definitions (same as ModbusTransport for compatibility)
INPUT_REGISTER_GROUPS = {
    "power_energy": (0, 32),  # Registers 0-31: Power, voltage, SOC/SOH, current
    "status_energy": (32, 32),  # Registers 32-63: Status, energy, fault/warning codes
    "temperatures": (64, 16),  # Registers 64-79: Temperatures, currents, fault history
    "bms_data": (80, 33),  # Registers 80-112: BMS passthrough data
}


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


class DongleTransport(BaseTransport):
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

    @property
    def runtime_register_map(self) -> RuntimeRegisterMap:
        """Get the runtime register map for this inverter family."""
        from pylxpweb.transports.register_maps import get_runtime_map

        return get_runtime_map(self._inverter_family)

    @property
    def energy_register_map(self) -> EnergyRegisterMap:
        """Get the energy register map for this inverter family."""
        from pylxpweb.transports.register_maps import get_energy_map

        return get_energy_map(self._inverter_family)

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

    async def _send_receive(
        self,
        packet: bytes,
        max_retries: int = 2,
    ) -> list[int]:
        """Send a packet and receive response with retry logic.

        Args:
            packet: Packet bytes to send
            max_retries: Number of retry attempts for empty responses

        Returns:
            List of register values from response

        Raises:
            TransportReadError: If send/receive fails after retries
            TransportTimeoutError: If operation times out
        """
        self._ensure_connected()

        if self._writer is None or self._reader is None:
            raise TransportConnectionError("Socket not initialized")

        last_error: TransportReadError | None = None

        async with self._lock:
            for attempt in range(max_retries + 1):
                try:
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

                    # Parse response
                    return self._parse_response(response)

                except TimeoutError as err:
                    _LOGGER.error("Timeout waiting for dongle response")
                    raise TransportTimeoutError(
                        "Timeout waiting for dongle response. "
                        "Recent dongle firmware may block port 8000 for security. "
                        "Consider using Modbus TCP with RS485 adapter instead."
                    ) from err
                except OSError as err:
                    _LOGGER.error("Socket error communicating with dongle: %s", err)
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

    def _parse_response(self, response: bytes) -> list[int]:
        """Parse a dongle response packet.

        Args:
            response: Raw response bytes

        Returns:
            List of register values

        Raises:
            TransportReadError: If response is invalid
        """
        # Minimum response: prefix(2) + version(2) + length(2) + addr(1) + func(1)
        # + dongle(10) + data_len(2) + some data
        if len(response) < 20:
            raise TransportReadError(f"Response too short: {len(response)} bytes")

        # Verify prefix
        if response[:2] != PACKET_PREFIX:
            raise TransportReadError(
                f"Invalid response prefix: {response[:2].hex()}, expected a11a"
            )

        # Extract data length (frame_length and tcp_func available at bytes 4-6 and 7 if needed)
        data_length = struct.unpack("<H", response[18:20])[0]

        # Data starts at offset 20
        data_start = 20
        data_end = data_start + data_length - 2  # -2 for CRC

        if data_end > len(response):
            raise TransportReadError(
                f"Response truncated: expected {data_end} bytes, got {len(response)}"
            )

        # Extract data frame
        data_frame = response[data_start:data_end]

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

        return await self._send_receive(packet)

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

        return await self._send_receive(packet)

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
        if len(values) == 1:
            # Single register write
            packet = self._build_packet(
                tcp_func=TCP_FUNC_TRANSLATED,
                modbus_func=MODBUS_WRITE_SINGLE,
                start_register=address,
                values=values,
            )
        else:
            # Multiple register write
            packet = self._build_packet(
                tcp_func=TCP_FUNC_TRANSLATED,
                modbus_func=MODBUS_WRITE_MULTI,
                start_register=address,
                values=values,
            )

        try:
            await self._send_receive(packet)
            return True
        except TransportReadError as err:
            raise TransportWriteError(str(err)) from err

    async def read_runtime(self) -> InverterRuntimeData:
        """Read runtime data via dongle input registers.

        Uses the appropriate register map based on the inverter_family parameter.

        Returns:
            Runtime data with all values properly scaled

        Raises:
            TransportReadError: If read operation fails
        """
        # Read register groups sequentially
        input_registers: dict[int, int] = {}

        for group_name, (start, count) in INPUT_REGISTER_GROUPS.items():
            try:
                values = await self._read_input_registers(start, count)
                for offset, value in enumerate(values):
                    input_registers[start + offset] = value
                # Delay between register groups to prevent dongle overload
                # The dongle has limited processing power and can reset connection
                # if requests come too fast
                await asyncio.sleep(0.2)
            except Exception as e:
                _LOGGER.error(
                    "Failed to read register group '%s': %s",
                    group_name,
                    e,
                )
                raise TransportReadError(
                    f"Failed to read register group '{group_name}': {e}"
                ) from e

        return InverterRuntimeData.from_modbus_registers(input_registers, self.runtime_register_map)

    async def read_energy(self) -> InverterEnergyData:
        """Read energy statistics via dongle input registers.

        Returns:
            Energy data with all values in kWh

        Raises:
            TransportReadError: If read operation fails
        """
        groups_needed = ["status_energy", "bms_data"]
        input_registers: dict[int, int] = {}

        for group_name, (start, count) in INPUT_REGISTER_GROUPS.items():
            if group_name not in groups_needed:
                continue

            try:
                values = await self._read_input_registers(start, count)
                for offset, value in enumerate(values):
                    input_registers[start + offset] = value
                # Delay between register groups to prevent dongle overload
                # The dongle has limited processing power and can reset connection
                # if requests come too fast
                await asyncio.sleep(0.2)
            except Exception as e:
                _LOGGER.error(
                    "Failed to read energy register group '%s': %s",
                    group_name,
                    e,
                )
                raise TransportReadError(
                    f"Failed to read energy register group '{group_name}': {e}"
                ) from e

        return InverterEnergyData.from_modbus_registers(input_registers, self.energy_register_map)

    async def read_device_type(self) -> int:
        """Read device type code from register 19.

        This can be used to detect whether the connected device is an
        inverter or a MID/GridBOSS device.

        Known device type codes:
        - 50: MID/GridBOSS (Microgrid Interconnect Device)
        - 54: SNA Series
        - 2092: PV Series (18KPV)
        - 10284: FlexBOSS21/FlexBOSS18

        Returns:
            Device type code integer

        Raises:
            TransportReadError: If read operation fails
        """
        # Read register 19 which contains the device type code
        # Use holding register read (function 0x03) as this is a parameter
        values = await self._read_holding_registers(DEVICE_TYPE_REGISTER, 1)
        if not values:
            raise TransportReadError("Failed to read device type register")
        return values[0]

    def is_midbox_device(self, device_type_code: int) -> bool:
        """Check if device type code indicates a MID/GridBOSS device.

        Args:
            device_type_code: Device type code from read_device_type()

        Returns:
            True if device is a MID/GridBOSS, False for inverters
        """
        return device_type_code == DEVICE_TYPE_MIDBOX

    async def read_midbox_runtime(self) -> dict[str, float | int]:
        """Read runtime data from a MID/GridBOSS device.

        MID devices use HOLDING registers (function 0x03) for runtime data,
        unlike inverters which use INPUT registers (function 0x04).

        Returns:
            Dictionary with MidboxData-compatible field names and values:
            - gridRmsVolt, upsRmsVolt, genRmsVolt (V)
            - gridL1RmsVolt, gridL2RmsVolt, etc. (V)
            - gridL1RmsCurr, gridL2RmsCurr, etc. (A, scaled /100)
            - gridL1ActivePower, gridL2ActivePower, etc. (W)
            - gridFreq (Hz, scaled /100)

        Raises:
            TransportReadError: If read operation fails
        """
        from pylxpweb.transports.register_maps import GRIDBOSS_RUNTIME_MAP

        # Read holding registers in groups
        # Group 1: Registers 0-40 (voltages, currents, power)
        # Group 2: Registers 128-131 (frequencies)
        holding_registers: dict[int, int] = {}

        try:
            # Read voltages, currents, and power (registers 0-40)
            values = await self._read_holding_registers(0, 40)
            for offset, value in enumerate(values):
                holding_registers[offset] = value
            await asyncio.sleep(0.2)

            # Read frequencies (registers 128-131)
            freq_values = await self._read_holding_registers(128, 4)
            for offset, value in enumerate(freq_values):
                holding_registers[128 + offset] = value

        except Exception as e:
            _LOGGER.error("Failed to read MID holding registers: %s", e)
            raise TransportReadError(f"Failed to read MID registers: {e}") from e

        # Extract values using the GridBOSS register map
        # Map field names to MidboxData-compatible names
        reg_map = GRIDBOSS_RUNTIME_MAP

        def get_value(field_name: str, default: int = 0) -> float | int:
            """Extract and scale a register value."""
            field = getattr(reg_map, field_name, None)
            if field is None:
                return default
            raw = holding_registers.get(field.address, default)
            # Handle signed values
            if field.signed and raw > 32767:
                raw = raw - 65536
            # Apply scaling
            from pylxpweb.constants.scaling import ScaleFactor

            if field.scale_factor == ScaleFactor.SCALE_10:
                return raw / 10.0
            elif field.scale_factor == ScaleFactor.SCALE_100:
                return raw / 100.0
            return raw

        # Build MidboxData-compatible dictionary
        return {
            # Voltages (no scaling - raw volts)
            "gridRmsVolt": get_value("grid_voltage"),
            "upsRmsVolt": get_value("ups_voltage"),
            "genRmsVolt": get_value("gen_voltage"),
            "gridL1RmsVolt": get_value("grid_l1_voltage"),
            "gridL2RmsVolt": get_value("grid_l2_voltage"),
            "upsL1RmsVolt": get_value("ups_l1_voltage"),
            "upsL2RmsVolt": get_value("ups_l2_voltage"),
            "genL1RmsVolt": get_value("gen_l1_voltage"),
            "genL2RmsVolt": get_value("gen_l2_voltage"),
            # Currents (scaled /100)
            "gridL1RmsCurr": get_value("grid_l1_current"),
            "gridL2RmsCurr": get_value("grid_l2_current"),
            "loadL1RmsCurr": get_value("load_l1_current"),
            "loadL2RmsCurr": get_value("load_l2_current"),
            "genL1RmsCurr": get_value("gen_l1_current"),
            "genL2RmsCurr": get_value("gen_l2_current"),
            "upsL1RmsCurr": get_value("ups_l1_current"),
            "upsL2RmsCurr": get_value("ups_l2_current"),
            # Power (no scaling - raw watts)
            "gridL1ActivePower": get_value("grid_l1_power"),
            "gridL2ActivePower": get_value("grid_l2_power"),
            "loadL1ActivePower": get_value("load_l1_power"),
            "loadL2ActivePower": get_value("load_l2_power"),
            "genL1ActivePower": get_value("gen_l1_power"),
            "genL2ActivePower": get_value("gen_l2_power"),
            "upsL1ActivePower": get_value("ups_l1_power"),
            "upsL2ActivePower": get_value("ups_l2_power"),
            # Frequencies (scaled /100)
            "phaseLockFreq": get_value("phase_lock_freq"),
            "gridFreq": get_value("grid_frequency"),
            "genFreq": get_value("gen_frequency"),
        }

    async def read_battery(self) -> BatteryBankData | None:
        """Read battery information via dongle.

        Uses the register map for correct register addresses and scaling,
        ensuring extensibility for different inverter families.

        Returns:
            Battery bank data with available information, None if no battery

        Raises:
            TransportReadError: If read operation fails
        """
        # Read power/energy registers (0-31) and BMS registers (80-112)
        # Combine into single dict for factory method
        all_registers: dict[int, int] = {}

        # Read core battery registers (0-31)
        power_regs = await self._read_input_registers(0, 32)
        for i, value in enumerate(power_regs):
            all_registers[i] = value

        # Read BMS registers (80-112)
        try:
            bms_values = await self._read_input_registers(80, 33)
            for offset, value in enumerate(bms_values):
                all_registers[80 + offset] = value
        except Exception as e:
            _LOGGER.warning("Failed to read BMS registers: %s", e)

        # Use factory method with register map for proper extensibility
        result = BatteryBankData.from_modbus_registers(all_registers, self.runtime_register_map)

        if result is None:
            _LOGGER.debug("Battery voltage below threshold, assuming no battery present.")

        return result

    async def read_parameters(
        self,
        start_address: int,
        count: int,
    ) -> dict[int, int]:
        """Read configuration parameters via dongle holding registers.

        Args:
            start_address: Starting register address
            count: Number of registers to read

        Returns:
            Dict mapping register address to raw integer value

        Raises:
            TransportReadError: If read operation fails
        """
        result: dict[int, int] = {}

        # Read in chunks of 40 registers
        remaining = count
        current_address = start_address

        while remaining > 0:
            chunk_size = min(remaining, 40)
            values = await self._read_holding_registers(current_address, chunk_size)

            for offset, value in enumerate(values):
                result[current_address + offset] = value

            current_address += chunk_size
            remaining -= chunk_size

        return result

    async def write_parameters(
        self,
        parameters: dict[int, int],
    ) -> bool:
        """Write configuration parameters via dongle holding registers.

        Args:
            parameters: Dict mapping register address to value to write

        Returns:
            True if all writes succeeded

        Raises:
            TransportWriteError: If any write operation fails
        """
        # Sort and group consecutive addresses
        sorted_params = sorted(parameters.items())
        groups: list[tuple[int, list[int]]] = []
        current_start: int | None = None
        current_values: list[int] = []

        for address, value in sorted_params:
            if current_start is None:
                current_start = address
                current_values = [value]
            elif address == current_start + len(current_values):
                current_values.append(value)
            else:
                groups.append((current_start, current_values))
                current_start = address
                current_values = [value]

        if current_start is not None and current_values:
            groups.append((current_start, current_values))

        # Write each group
        for start_address, values in groups:
            await self._write_holding_registers(start_address, values)

        return True

    async def read_serial_number(self) -> str:
        """Read inverter serial number from input registers 115-119.

        The serial number is stored as 10 ASCII characters across 5 registers.
        Each register contains 2 characters: low byte = char[0], high byte = char[1].

        Returns:
            10-character serial number string (e.g., "BA12345678")
        """
        try:
            values = await self._read_input_registers(115, 5)

            # Decode ASCII characters from register values
            chars: list[str] = []
            for value in values:
                low_byte = value & 0xFF
                high_byte = (value >> 8) & 0xFF
                # Filter out non-printable characters
                if 32 <= low_byte <= 126:
                    chars.append(chr(low_byte))
                if 32 <= high_byte <= 126:
                    chars.append(chr(high_byte))

            serial = "".join(chars)
            _LOGGER.debug("Read serial number from dongle: %s", serial)
            return serial
        except Exception as err:
            _LOGGER.debug("Failed to read serial number: %s", err)
        return ""

    async def read_firmware_version(self) -> str:
        """Read full firmware version code from holding registers 7-10.

        The firmware information is stored in a specific format:
        - Registers 7-8: Firmware prefix as byte-swapped ASCII (e.g., "FAAB")
        - Registers 9-10: Version bytes with special encoding

        Byte layout discovered via diagnostic register reading:
        - Reg 7: 0x4146 → low byte 'F', high byte 'A' → byte-swapped = "FA"
        - Reg 8: 0x4241 → low byte 'A', high byte 'B' → byte-swapped = "AB"
        - Reg 9: v1 is in high byte (e.g., 0x2503 → v1 = 0x25 = 37)
        - Reg 10: v2 is in low byte (e.g., 0x0125 → v2 = 0x25 = 37)

        The web API returns fwCode like "FAAB-2525" where:
        - "FAAB" is the device standard/prefix from registers 7-8
        - "2525" is {v1:02X}{v2:02X} (hex-encoded version bytes)

        Returns:
            Full firmware code string (e.g., "FAAB-2525")
            Returns empty string if read fails.
        """
        try:
            # Read holding registers 7-10 (prefix + version)
            regs = await self._read_holding_registers(7, 4)
            if len(regs) >= 4:
                # Extract firmware prefix from registers 7-8 (byte-swapped ASCII)
                prefix_chars = [
                    chr(regs[0] & 0xFF),  # Reg 7 low byte
                    chr((regs[0] >> 8) & 0xFF),  # Reg 7 high byte
                    chr(regs[1] & 0xFF),  # Reg 8 low byte
                    chr((regs[1] >> 8) & 0xFF),  # Reg 8 high byte
                ]
                prefix = "".join(prefix_chars)

                # Extract version bytes with special encoding
                v1 = (regs[2] >> 8) & 0xFF  # High byte of register 9
                v2 = regs[3] & 0xFF  # Low byte of register 10

                firmware = f"{prefix}-{v1:02X}{v2:02X}"
                _LOGGER.debug("Read firmware version: %s", firmware)
                return firmware
        except Exception as err:
            _LOGGER.debug("Failed to read firmware version: %s", err)
        return ""
