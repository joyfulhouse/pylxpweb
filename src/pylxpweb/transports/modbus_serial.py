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
from typing import TYPE_CHECKING, Any, Literal

from ._modbus_base import BaseModbusTransport
from ._modbus_client import (
    ModbusBackend,
    ModbusConnectionUnit,
    ModbusUnitLike,
    PymodbusUnit,
    RegisterClient,
    normalize_backend,
    resolve_backend,
)
from ._register_data import DEFAULT_INPUT_BLOCK_SIZE
from .capabilities import MODBUS_CAPABILITIES, TransportCapabilities
from .exceptions import TransportConnectionError
from .observation import RegisterObserver

if TYPE_CHECKING:
    from pymodbus.client import AsyncModbusSerialClient

    from pylxpweb.devices.inverters._features import InverterFamily

_LOGGER = logging.getLogger(__name__)


class ModbusSerialTransport(BaseModbusTransport):
    """Modbus RTU serial transport for local inverter communication.

    This transport connects directly to the inverter via a USB-to-RS485
    serial adapter using Modbus RTU protocol.

    Network Serial Bridges (Proxies)
    --------------------------------
    The ``port`` argument is passed straight through to the backend's serial
    layer, so URL-style ports reach a remote RS485 adapter over the network:

        # Raw TCP serial bridge (pyserial or serialx)
        transport = ModbusSerialTransport(port="socket://10.0.0.5:502", ...)

        # RFC 2217 proxy (ser2net etc.; pyserial or serialx)
        transport = ModbusSerialTransport(port="rfc2217://10.0.0.5:2217", ...)

        # Home Assistant / ESPHome serial proxy (serialx only, #180):
        # ``backend="auto"`` selects the modbus_connection backend for it.
        transport = ModbusSerialTransport(port="esphome://esp-node.local:6053", ...)

    Backends
    --------
    ``backend="pymodbus"`` (pyserial underneath) is the historical default.
    ``backend="modbus_connection"`` uses Home Assistant's shared-connection
    library (tmodbus + serialx) and needs the ``modbus-connection`` extra.
    ``backend="auto"`` keeps pymodbus unless the port is a URL only serialx
    can open.

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
        max_input_block_size: int = DEFAULT_INPUT_BLOCK_SIZE,
        register_observer: RegisterObserver | None = None,
        backend: str = "auto",
        unit: ModbusUnitLike | None = None,
    ) -> None:
        """Initialize Modbus serial transport.

        Args:
            port: Serial port path or pyserial URL. Local devices use a path
                (e.g., /dev/ttyUSB0, COM3, /dev/tty.usbserial). Network serial
                bridges use a pyserial URL that is passed through unchanged to
                ``serial.serial_for_url`` (e.g., ``socket://10.0.0.5:502`` for a
                raw TCP bridge, or ``rfc2217://10.0.0.5:2217`` for an RFC 2217
                proxy such as ESPHome or ser2net). See #180.
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
            max_input_block_size: Maximum registers per coalesced input-register
                read, 40..125 (default 40 = no coalescing, the plain per-group
                reads).  Larger values (multiples of 40 recommended; 120 is
                field-proven) consolidate adjacent register groups into fewer
                reads; hardware that rejects large reads automatically falls
                back to the plain grouped reads (eg4_web_monitor#254).
            register_observer: Optional callback for terminal raw-register segments.
            backend: ``"pymodbus"``, ``"modbus_connection"``, or ``"auto"``
                (pymodbus unless the port is a serialx-only URL such as
                ``esphome://``). See the class docstring.
            unit: A ``ModbusUnit``-shaped object supplied by a host (Home
                Assistant's ``async_get_unit()``) over a shared serial link.
                The transport then never opens or closes the port itself.
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
            max_input_block_size=max_input_block_size,
            register_observer=register_observer,
        )
        self._port = port
        self._baudrate = baudrate
        self._bytesize = bytesize
        self._parity = parity
        self._stopbits = stopbits
        self._backend_setting = normalize_backend(backend)
        self._backend: ModbusBackend = resolve_backend(self._backend_setting, serial_port=port)
        self._external_unit = unit
        if unit is not None:
            if self._backend_setting == "pymodbus":
                raise ValueError("An injected unit cannot be used with the pymodbus backend")
            self._backend = "modbus_connection"
        # Raw backend handle; I/O goes through ``self._unit`` (see _modbus_base).
        self._client: AsyncModbusSerialClient | Any | None = None
        # Adapters whose close is still settling (see ModbusTransport).
        self._draining_units: list[RegisterClient] = []

    @property
    def capabilities(self) -> TransportCapabilities:
        """Get Modbus transport capabilities."""
        return MODBUS_CAPABILITIES

    @property
    def backend(self) -> ModbusBackend:
        """The wire backend this transport opens the port with."""
        return self._backend

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
        # A previous dial (cancelled or failed) may still own a link: release
        # it first so a re-dial never orphans a connection.
        self._drop_session()
        try:
            if self._external_unit is not None:
                self._client = self._external_unit
                self._unit = ModbusConnectionUnit(self._external_unit)
            elif self._backend == "modbus_connection":
                await self._open_modbus_connection()
            else:
                await self._open_pymodbus()

            self._connected = True
            self._consecutive_errors = 0
            _LOGGER.info(
                "Modbus serial transport connected to %s @ %d baud (unit %s, backend %s) for %s",
                self._port,
                self._baudrate,
                self._unit_id,
                "shared" if self._external_unit is not None else self._backend,
                self._serial,
            )

            # Brief delay to allow serial port to stabilize
            await asyncio.sleep(0.2)

        except asyncio.CancelledError:
            # The backend's dial may still complete after we were cancelled;
            # releasing the adapter closes whatever it ends up owning.
            self._drop_session()
            raise
        except ImportError as err:
            hint = (
                "modbus-connection package not installed. "
                "Install with: uv add 'pylxpweb[modbus-connection]'"
                if self._backend == "modbus_connection"
                else "pymodbus or pyserial package not installed. "
                "Install with: uv add pymodbus pyserial"
            )
            raise TransportConnectionError(hint) from err
        except PermissionError as err:
            self._drop_session()
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
            self._drop_session()
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

    async def _open_pymodbus(self) -> None:
        """Open the port with pymodbus (pyserial underneath)."""
        from pymodbus.client import AsyncModbusSerialClient

        client = AsyncModbusSerialClient(
            port=self._port,
            baudrate=self._baudrate,
            bytesize=self._bytesize,
            parity=self._parity,
            stopbits=self._stopbits,
            timeout=self._timeout,
            retries=self._pymodbus_retries,
        )
        self._client = client
        self._unit = PymodbusUnit(client, self._unit_id)

        connected = await client.connect()
        if not connected:
            raise TransportConnectionError(f"Failed to connect to serial port {self._port}")

    async def _open_modbus_connection(self) -> None:
        """Open the port with modbus_connection (tmodbus + serialx)."""
        from modbus_connection import ModbusSerialParams
        from modbus_connection import exceptions as mc_exc
        from modbus_connection.tmodbus import ModbusConnection

        params = ModbusSerialParams(
            device=self._port,
            baudrate=self._baudrate,
            bytesize=_literal_bytesize(self._bytesize),
            parity=_literal_parity(self._parity),
            stopbits=_literal_stopbits(self._stopbits),
        )
        connection = ModbusConnection(params, timeout=self._timeout)
        self._client = connection
        self._unit = ModbusConnectionUnit(connection.for_unit(self._unit_id), connection=connection)
        try:
            await connection.connect()
        except mc_exc.ModbusError as err:
            # The library wraps the OS error; PermissionError detail survives
            # in the message only, so surface it as a plain connect failure.
            self._drop_session()
            raise TransportConnectionError(
                f"Failed to connect to {self._port}: {err}. "
                "Verify: (1) serial port exists, (2) device is connected, "
                "(3) correct permissions, (4) port is not in use by "
                "another application."
            ) from err

    def _drop_session(self) -> None:
        """Release the adapter and forget it; closes settle in :meth:`disconnect`."""
        unit = self._unit
        if unit is not None:
            unit.close()
            self._draining_units.append(unit)
        self._client = None
        self._unit = None
        self._connected = False

    async def disconnect(self) -> None:
        """Close Modbus serial connection (a host-shared unit is only detached)."""
        self._drop_session()
        while self._draining_units:
            await self._draining_units.pop(0).aclose()
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
            await self._recycle_link()
            self._consecutive_errors = 0


def _literal_bytesize(value: int) -> Literal[7, 8]:
    if value == 8:
        return 8
    if value == 7:
        return 7
    raise ValueError(f"Invalid bytesize for modbus_connection backend: {value}")


def _literal_parity(value: str) -> Literal["N", "E", "O"]:
    if value == "N":
        return "N"
    if value == "E":
        return "E"
    if value == "O":
        return "O"
    raise ValueError(f"Invalid parity for modbus_connection backend: {value}")


def _literal_stopbits(value: int) -> Literal[1, 2]:
    if value == 1:
        return 1
    if value == 2:
        return 2
    raise ValueError(f"Invalid stopbits for modbus_connection backend: {value}")
