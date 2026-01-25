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
from datetime import datetime
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
    from pylxpweb.transports.register_maps import EnergyRegisterMap, RuntimeRegisterMap

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
        """
        super().__init__(inverter_serial)
        self._host = host
        self._port = port
        self._dongle_serial = dongle_serial
        self._timeout = timeout
        self._inverter_family = inverter_family
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

    async def connect(self) -> None:
        """Establish TCP connection to the WiFi dongle.

        Raises:
            TransportConnectionError: If connection fails
        """
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=self._timeout,
            )

            self._connected = True
            _LOGGER.info(
                "Dongle transport connected to %s:%s (dongle=%s, inverter=%s)",
                self._host,
                self._port,
                self._dongle_serial,
                self._serial,
            )

        except TimeoutError as err:
            _LOGGER.error(
                "Timeout connecting to dongle at %s:%s",
                self._host,
                self._port,
            )
            raise TransportConnectionError(
                f"Timeout connecting to {self._host}:{self._port}. "
                "Verify: (1) IP address is correct, (2) dongle is on network, "
                "(3) port 8000 is not blocked by firmware."
            ) from err
        except OSError as err:
            _LOGGER.error(
                "Failed to connect to dongle at %s:%s: %s",
                self._host,
                self._port,
                err,
            )
            raise TransportConnectionError(
                f"Failed to connect to {self._host}:{self._port}: {err}. "
                "Verify: (1) IP address is correct, (2) dongle is accessible, "
                "(3) no other client is connected."
            ) from err

    async def disconnect(self) -> None:
        """Close TCP connection to the dongle."""
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass  # Ignore errors during disconnect

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
            # Write single: address(1) + func(1) + serial(10) + reg(2) + value(2)
            value = values[0] if values else 0
            data_frame = bytes([0x01, modbus_func]) + inverter_bytes
            data_frame += struct.pack("<H", start_register)
            data_frame += struct.pack("<H", value)
        elif modbus_func == MODBUS_WRITE_MULTI:
            # Write multi: address(1) + func(1) + serial(10) + reg(2) + count(2) + bytes(1) + data
            data_count = len(values) if values else 0
            byte_count = data_count * 2
            data_frame = bytes([0x01, modbus_func]) + inverter_bytes
            data_frame += struct.pack("<H", start_register)
            data_frame += struct.pack("<H", data_count)
            data_frame += bytes([byte_count])
            for value in values or []:
                data_frame += struct.pack("<H", value)
        else:
            # Read: address(1) + func(1) + serial(10) + reg(2) + count(2)
            data_frame = bytes([0x01, modbus_func]) + inverter_bytes
            data_frame += struct.pack("<H", start_register)
            data_frame += struct.pack("<H", register_count)

        # Calculate CRC of data frame
        crc = compute_crc16(data_frame)

        # Build complete packet
        data_length = len(data_frame) + 2  # +2 for CRC
        frame_length = 12 + data_length  # 12 = header after length field

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

        # For read responses, data frame contains: addr(1) + func(1) + byte_count(1) + data
        if len(data_frame) < 3:
            raise TransportReadError(f"Data frame too short: {len(data_frame)} bytes")

        modbus_func = data_frame[1]
        byte_count = data_frame[2]

        # Check for Modbus exception (function code with high bit set)
        if modbus_func & 0x80:
            exception_code = data_frame[2] if len(data_frame) > 2 else 0
            raise TransportReadError(
                f"Modbus exception: function=0x{modbus_func:02x}, code={exception_code}"
            )

        # Extract register values (little-endian uint16)
        register_data = data_frame[3 : 3 + byte_count]
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

    async def read_battery(self) -> BatteryBankData | None:
        """Read battery information via dongle.

        Returns:
            Battery bank data with available information, None if no battery

        Raises:
            TransportReadError: If read operation fails
        """
        from pylxpweb.constants.scaling import ScaleFactor, apply_scale

        # Read power/energy registers (0-31)
        power_regs = await self._read_input_registers(0, 32)

        # Extract battery data
        battery_voltage = apply_scale(power_regs[4], ScaleFactor.SCALE_100)

        # Register 5: packed SOC (low byte) and SOH (high byte)
        soc_soh_packed = power_regs[5]
        battery_soc = soc_soh_packed & 0xFF
        battery_soh = (soc_soh_packed >> 8) & 0xFF

        # Battery charge/discharge power (2-register values)
        charge_power = (power_regs[12] << 16) | power_regs[13]
        discharge_power = (power_regs[14] << 16) | power_regs[15]

        if battery_voltage < 1.0:
            _LOGGER.debug(
                "Battery voltage %.2fV below threshold, assuming no battery",
                battery_voltage,
            )
            return None

        # Read BMS registers (80-112)
        bms_regs: dict[int, int] = {}
        try:
            bms_values = await self._read_input_registers(80, 33)
            for offset, value in enumerate(bms_values):
                bms_regs[80 + offset] = value
        except Exception as e:
            _LOGGER.warning("Failed to read BMS registers: %s", e)

        # Extract BMS data
        bms_fault_code = bms_regs.get(99, 0)
        bms_warning_code = bms_regs.get(100, 0)
        battery_count = bms_regs.get(96, 1)

        max_cell_voltage = apply_scale(bms_regs.get(101, 0), ScaleFactor.SCALE_1000)
        min_cell_voltage = apply_scale(bms_regs.get(102, 0), ScaleFactor.SCALE_1000)

        max_cell_temp_raw = bms_regs.get(103, 0)
        min_cell_temp_raw = bms_regs.get(104, 0)
        if max_cell_temp_raw > 32767:
            max_cell_temp_raw = max_cell_temp_raw - 65536
        if min_cell_temp_raw > 32767:
            min_cell_temp_raw = min_cell_temp_raw - 65536
        max_cell_temperature = apply_scale(max_cell_temp_raw, ScaleFactor.SCALE_10)
        min_cell_temperature = apply_scale(min_cell_temp_raw, ScaleFactor.SCALE_10)

        cycle_count = bms_regs.get(106, 0)

        return BatteryBankData(
            timestamp=datetime.now(),
            voltage=battery_voltage,
            soc=battery_soc,
            soh=battery_soh,
            charge_power=float(charge_power),
            discharge_power=float(discharge_power),
            fault_code=bms_fault_code,
            warning_code=bms_warning_code,
            battery_count=battery_count if battery_count > 0 else 1,
            max_cell_voltage=max_cell_voltage,
            min_cell_voltage=min_cell_voltage,
            max_cell_temperature=max_cell_temperature,
            min_cell_temperature=min_cell_temperature,
            cycle_count=cycle_count,
            batteries=[],
        )

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
