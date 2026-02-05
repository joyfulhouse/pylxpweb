"""Modbus RTU serial transport implementation.

This module provides the ModbusSerialTransport class for direct local
communication with inverters via Modbus RTU over USB-to-RS485 serial adapters.

IMPORTANT: Single-Client Limitation
------------------------------------
Serial ports support only ONE concurrent connection.
Running multiple clients causes communication errors and data corruption.

Ensure only ONE integration/script connects to each serial port at a time.

Example:
    transport = ModbusSerialTransport(
        port="/dev/ttyUSB0",
        baudrate=19200,
        serial="CE12345678",
    )
    await transport.connect()

    runtime = await transport.read_runtime()
    print(f"PV Power: {runtime.pv_total_power}W")
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ._modbus_base import BaseModbusTransport
from .capabilities import MODBUS_CAPABILITIES, TransportCapabilities
from .exceptions import TransportConnectionError

if TYPE_CHECKING:
    from pymodbus.client import AsyncModbusSerialClient

    from pylxpweb.devices.inverters._features import InverterFamily

_LOGGER = logging.getLogger(__name__)


class ModbusSerialTransport(BaseModbusTransport):
    """Modbus RTU serial transport for local inverter communication.

    This transport connects directly to the inverter via a USB-to-RS485
    serial adapter using Modbus RTU protocol.

    IMPORTANT: Single-Client Limitation
    ------------------------------------
    Serial ports support only ONE concurrent connection.
    Running multiple clients causes communication errors and data corruption.

    Ensure only ONE integration/script connects to each serial port at a time.

    Example:
        transport = ModbusSerialTransport(
            port="/dev/ttyUSB0",
            baudrate=19200,
            serial="CE12345678",
        )
        await transport.connect()

        runtime = await transport.read_runtime()
        print(f"PV Power: {runtime.pv_total_power}W")

    Note:
        Requires the `pymodbus` and `pyserial` packages to be installed:
        uv add pymodbus pyserial
    """

    transport_type: str = "modbus_serial"

    def __init__(
        self,
        port: str,
        baudrate: int = 19200,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: int = 1,
        unit_id: int = 1,
        serial: str = "",
        timeout: float = 10.0,
        inverter_family: InverterFamily | None = None,
        retries: int = 2,
        retry_delay: float = 0.5,
        inter_register_delay: float = 0.05,
        pymodbus_retries: int = 3,
    ) -> None:
        """Initialize Modbus serial transport.

        Args:
            port: Serial port path (e.g., /dev/ttyUSB0, COM3, /dev/tty.usbserial)
            baudrate: Serial baud rate (default 19200 for EG4 inverters)
            bytesize: Data bits per byte (default 8)
            parity: Parity setting - 'N' (none), 'E' (even), 'O' (odd)
            stopbits: Number of stop bits (default 1)
            unit_id: Modbus unit/slave ID (default 1)
            serial: Inverter serial number (for identification)
            timeout: Connection and operation timeout in seconds
            inverter_family: Inverter model family for correct register mapping.
                If None, defaults to PV_SERIES (EG4-18KPV) for backward
                compatibility.
            retries: Application-level retries per register read (default 2)
            retry_delay: Initial delay between retries in seconds, doubles each
                attempt (default 0.5)
            inter_register_delay: Delay between register group reads in seconds
                (default 0.05)
            pymodbus_retries: Number of retries passed to pymodbus client
                (default 3)
        """
        super().__init__(
            serial,
            unit_id=unit_id,
            timeout=timeout,
            inverter_family=inverter_family,
            retries=retries,
            retry_delay=retry_delay,
            inter_register_delay=inter_register_delay,
            pymodbus_retries=pymodbus_retries,
        )
        self._port = port
        self._baudrate = baudrate
        self._bytesize = bytesize
        self._parity = parity
        self._stopbits = stopbits
        # Narrow type for serial client
        self._client: AsyncModbusSerialClient | None = None

    @property
    def capabilities(self) -> TransportCapabilities:
        """Get Modbus transport capabilities."""
        return MODBUS_CAPABILITIES

    @property
    def port(self) -> str:
        """Get the serial port path."""
        return self._port

    @property
    def baudrate(self) -> int:
        """Get the serial baud rate."""
        return self._baudrate

    async def connect(self) -> None:
        """Establish Modbus RTU serial connection.

        Raises:
            TransportConnectionError: If connection fails
        """
        try:
            from pymodbus.client import AsyncModbusSerialClient

            self._client = AsyncModbusSerialClient(
                port=self._port,
                baudrate=self._baudrate,
                bytesize=self._bytesize,
                parity=self._parity,
                stopbits=self._stopbits,
                timeout=self._timeout,
                retries=self._pymodbus_retries,
            )

            connected = await self._client.connect()
            if not connected:
                raise TransportConnectionError(f"Failed to connect to serial port {self._port}")

            self._connected = True
            self._consecutive_errors = 0
            _LOGGER.info(
                "Modbus serial transport connected to %s @ %d baud (unit %s) for %s",
                self._port,
                self._baudrate,
                self._unit_id,
                self._serial,
            )

            # Brief delay to allow serial port to stabilize
            await asyncio.sleep(0.2)

        except ImportError as err:
            raise TransportConnectionError(
                "pymodbus or pyserial package not installed. Install with: uv add pymodbus pyserial"
            ) from err
        except PermissionError as err:
            _LOGGER.error(
                "Permission denied opening serial port %s: %s",
                self._port,
                err,
            )
            raise TransportConnectionError(
                f"Permission denied for {self._port}. "
                "On Linux, add user to 'dialout' group: "
                "sudo usermod -a -G dialout $USER"
            ) from err
        except (TimeoutError, OSError) as err:
            _LOGGER.error(
                "Failed to connect to serial port %s: %s",
                self._port,
                err,
            )
            raise TransportConnectionError(
                f"Failed to connect to {self._port}: {err}. "
                "Verify: (1) serial port exists, (2) device is connected, "
                "(3) correct permissions, (4) port is not in use by "
                "another application."
            ) from err

    async def disconnect(self) -> None:
        """Close Modbus serial connection."""
        if self._client:
            self._client.close()
            self._client = None

        self._connected = False
        _LOGGER.debug("Modbus serial transport disconnected for %s", self._serial)

    async def _reconnect(self) -> None:
        """Reconnect Modbus serial client to reset state."""
        async with self._lock:
            if self._consecutive_errors < self._max_consecutive_errors:
                return

            _LOGGER.warning(
                "Reconnecting Modbus serial client for %s after %d consecutive errors",
                self._serial,
                self._consecutive_errors,
            )
            await self.disconnect()
            await self.connect()
            self._consecutive_errors = 0
