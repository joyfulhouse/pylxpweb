"""Backend-neutral register-client seam for the Modbus transports.

``BaseModbusTransport`` talks to the wire through a :class:`RegisterClient`
rather than a pymodbus client. The seam mirrors the ``ModbusUnit`` protocol
that Home Assistant's shared-connection library (``modbus-connection``)
hands out, so the same transport code can run on:

- :class:`PymodbusUnit` — the historical backend, wrapping a pymodbus async
  client and carrying the Waveshare transaction-ID workaround; or
- :class:`ModbusConnectionUnit` — a ``modbus_connection.ModbusUnit`` (tmodbus
  + serialx), either owned by the transport or shared/injected by a host
  such as Home Assistant.

Both adapters translate backend-specific failures into the three
:class:`RegisterClientError` subclasses the transport branches on, so the
retry, link-health, and reconnect logic in ``_modbus_base.py`` stays
backend-agnostic.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal, Protocol, runtime_checkable

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "BACKENDS",
    "ModbusBackend",
    "ModbusConnectionUnit",
    "ModbusUnitLike",
    "PymodbusUnit",
    "RegisterClient",
    "RegisterClientError",
    "RegisterExceptionResponse",
    "RegisterLinkError",
    "RegisterTimeoutError",
    "normalize_backend",
    "patch_pymodbus_tid_validation",
    "resolve_backend",
]

type ModbusBackend = Literal["pymodbus", "modbus_connection"]
"""Concrete wire backend for a Modbus transport."""

BACKENDS: tuple[str, ...] = ("auto", "pymodbus", "modbus_connection")
"""Accepted ``backend`` spellings: the two backends plus ``auto``."""

# Serial URL schemes only serialx can open; pyserial (pymodbus) cannot.
_SERIALX_ONLY_SCHEMES: tuple[str, ...] = ("esphome://",)


# ----------------------------------------------------------------------
# Errors the transports branch on
# ----------------------------------------------------------------------


class RegisterClientError(Exception):
    """Base class for failures raised by a :class:`RegisterClient`."""


class RegisterExceptionResponse(RegisterClientError):
    """The device answered with a Modbus exception response.

    The link is alive — the device decoded the request and refused it — so
    callers must not count this against link health.
    """

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class RegisterTimeoutError(RegisterClientError, TimeoutError):
    """No response arrived within the backend's timeout."""


class RegisterLinkError(RegisterClientError):
    """The link is down or the response was unusable (connection/protocol)."""


# ----------------------------------------------------------------------
# Protocols
# ----------------------------------------------------------------------


@runtime_checkable
class ModbusUnitLike(Protocol):
    """Structural subset of ``modbus_connection.ModbusUnit`` the transports use.

    Any object with this shape — including a unit obtained from Home
    Assistant's ``async_get_unit`` — can be injected into a Modbus transport.
    """

    @property
    def connected(self) -> bool: ...

    async def read_holding_registers(self, address: int, count: int) -> list[int]: ...

    async def read_input_registers(self, address: int, count: int) -> list[int]: ...

    async def write_register(self, address: int, value: int) -> None: ...

    async def write_registers(self, address: int, values: list[int]) -> None: ...

    async def disconnect(self) -> None: ...


class RegisterClient(Protocol):
    """What ``BaseModbusTransport`` requires of its wire client.

    Same call shape as :class:`ModbusUnitLike`; the difference is the error
    contract: implementations raise only :class:`RegisterClientError`
    subclasses (plus ``asyncio.CancelledError``), never backend exceptions.
    """

    @property
    def connected(self) -> bool: ...

    @property
    def owns_link(self) -> bool:
        """Whether closing this client tears down the underlying link.

        ``False`` for units shared by a host (Home Assistant); the transport
        must then never close the link, only recycle it via :meth:`recycle`.
        """
        ...

    async def read_holding_registers(self, address: int, count: int) -> list[int]: ...

    async def read_input_registers(self, address: int, count: int) -> list[int]: ...

    async def write_register(self, address: int, value: int) -> None: ...

    async def write_registers(self, address: int, values: list[int]) -> None: ...

    async def recycle(self) -> None:
        """Drop a wedged link so the next request re-dials (error recycle)."""
        ...

    def close(self) -> None:
        """Release the client synchronously; safe to call more than once."""
        ...

    async def aclose(self) -> None:
        """Release the client and wait for the underlying close to finish."""
        ...


# ----------------------------------------------------------------------
# Backend selection
# ----------------------------------------------------------------------


def normalize_backend(backend: str) -> str:
    """Validate a ``backend`` spelling, returning it lower-cased."""
    value = str(backend).strip().lower().replace("-", "_")
    if value not in BACKENDS:
        raise ValueError(
            f"Unsupported Modbus backend {backend!r}; expected one of {', '.join(BACKENDS)}"
        )
    return value


def resolve_backend(backend: str, *, serial_port: str | None = None) -> ModbusBackend:
    """Resolve ``auto`` to a concrete backend.

    ``auto`` keeps pymodbus — the historical default, carrying the Waveshare
    transaction-ID workaround — unless the serial port is a URL only serialx
    can open (``esphome://``), where pymodbus cannot work at all.
    """
    value = normalize_backend(backend)
    if value == "auto":
        if serial_port is not None and serial_port.lower().startswith(_SERIALX_ONLY_SCHEMES):
            return "modbus_connection"
        return "pymodbus"
    if value == "modbus_connection":
        return "modbus_connection"
    return "pymodbus"


# ----------------------------------------------------------------------
# pymodbus adapter
# ----------------------------------------------------------------------


def patch_pymodbus_tid_validation(client: Any, *, label: str) -> bool:
    """Disable MBAP transaction-ID validation on a pymodbus client.

    Some RS485-to-Ethernet gateways were observed (2026-02, pylxpweb 0.6.9)
    to use MBAP framing on the TCP side without echoing the request's
    transaction ID, which makes pymodbus reject every response at two
    validation points:

    1. ``framer.handleFrame``: ``if exp_tid and tid != exp_tid``
    2. ``execute``: ``if response.transaction_id != request.transaction_id``

    ``handleFrame`` is patched to pass ``exp_tid=0`` (disabling check 1) and
    to stamp the decoded PDU with the expected TID (satisfying check 2).
    Stale responses arriving after a future is resolved are dropped to
    prevent log spam. Safe because the transport serialises one in-flight
    request per link.

    Returns ``True`` when the patch was applied; ``False`` when the client
    layout is unknown (fakes, future pymodbus) and it was left untouched.
    """
    ctx = getattr(client, "ctx", None)
    if ctx is None or not hasattr(ctx, "framer"):
        return False

    framer = ctx.framer
    original_handle_frame = framer.handleFrame

    def _patched_handle_frame(
        data: bytes,
        exp_devid: int,
        exp_tid: int,
    ) -> tuple[int, object | None]:
        used_len, pdu = original_handle_frame(data, exp_devid, 0)
        if pdu is not None:
            # Drop stale responses whose future is already resolved.
            future = getattr(ctx, "response_future", None)
            if future is not None and future.done():
                return used_len, None
            if exp_tid:
                pdu.transaction_id = exp_tid
        return used_len, pdu

    framer.handleFrame = _patched_handle_frame
    _LOGGER.debug("Patched TID validation for Modbus gateway %s", label)
    return True


class PymodbusUnit:
    """:class:`RegisterClient` over a pymodbus async client bound to one unit ID.

    Owns the client: :meth:`close` closes the socket/port. Calls use the
    keyword form ``read_*(address=..., count=..., device_id=...)`` that
    pymodbus 3.6 through 3.15 share.
    """

    owns_link: bool = True

    def __init__(self, client: Any, unit_id: int) -> None:
        self._client = client
        self._unit_id = unit_id
        self._closed = False

    @property
    def client(self) -> Any:
        """The wrapped pymodbus client."""
        return self._client

    @property
    def unit_id(self) -> int:
        """The Modbus unit ID every request is addressed to."""
        return self._unit_id

    @property
    def connected(self) -> bool:
        return bool(getattr(self._client, "connected", False))

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        result = await self._call(
            self._client.read_holding_registers,
            address=address,
            count=count,
            device_id=self._unit_id,
        )
        return self._registers(result, address)

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        result = await self._call(
            self._client.read_input_registers,
            address=address,
            count=count,
            device_id=self._unit_id,
        )
        return self._registers(result, address)

    async def write_register(self, address: int, value: int) -> None:
        result = await self._call(
            self._client.write_register,
            address=address,
            value=value,
            device_id=self._unit_id,
        )
        self._check_write(result, address)

    async def write_registers(self, address: int, values: list[int]) -> None:
        result = await self._call(
            self._client.write_registers,
            address=address,
            values=values,
            device_id=self._unit_id,
        )
        self._check_write(result, address)

    async def recycle(self) -> None:
        """pymodbus links are owned: the transport recycles by close + dial."""
        return None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._client.close()

    async def aclose(self) -> None:
        self.close()

    # -- helpers -------------------------------------------------------------

    @staticmethod
    async def _call(func: Any, **kwargs: Any) -> Any:
        from pymodbus.exceptions import ModbusException

        try:
            return await func(**kwargs)
        except ModbusException as err:
            # Catch the pymodbus BASE class: ConnectionException ("Not
            # connected") is a SIBLING of ModbusIOException, not a subclass
            # (eg4-57g, eg4-1cxn).
            if "timeout" in str(err).lower():
                raise RegisterTimeoutError(str(err)) from err
            raise RegisterLinkError(str(err)) from err
        except TimeoutError as err:
            raise RegisterTimeoutError(str(err) or "timeout") from err
        except OSError as err:
            raise RegisterLinkError(str(err)) from err

    @staticmethod
    def _registers(result: Any, address: int) -> list[int]:
        if result.isError():
            raise RegisterExceptionResponse(
                f"Modbus read error at address {address}: {result}",
                code=getattr(result, "exception_code", None),
            )
        registers = getattr(result, "registers", None)
        if registers is None:
            raise RegisterLinkError(
                f"Invalid Modbus response at address {address}: no registers in response"
            )
        # pymodbus decodes registers from the response's own byte_count and
        # never checks it against the requested count, so this can be short;
        # the transport decides what a short read means per register space.
        return list(registers)

    @staticmethod
    def _check_write(result: Any, address: int) -> None:
        if result.isError():
            raise RegisterExceptionResponse(
                f"Modbus write error at address {address}: {result}",
                code=getattr(result, "exception_code", None),
            )


# ----------------------------------------------------------------------
# modbus-connection adapter
# ----------------------------------------------------------------------


def _modbus_connection_exceptions() -> Any:
    """Import ``modbus_connection.exceptions`` lazily (optional extra)."""
    try:
        from modbus_connection import exceptions
    except ImportError as err:  # pragma: no cover - exercised without the extra
        raise RegisterLinkError(
            "modbus-connection package not installed. "
            "Install with: uv add 'pylxpweb[modbus-connection]'"
        ) from err
    return exceptions


class ModbusConnectionUnit:
    """:class:`RegisterClient` over a ``modbus_connection.ModbusUnit``.

    ``connection`` is the owning ``ModbusConnection`` when the transport
    created it, in which case :meth:`close` closes it permanently. When the
    unit was injected by a host (``connection=None``), the transport shares
    the link and must never close it; :meth:`recycle` drops a wedged link via
    the unit's own ``disconnect()`` so the host's connection re-dials on the
    next request, which is the documented recovery path for shared units.
    """

    def __init__(self, unit: ModbusUnitLike, *, connection: Any | None = None) -> None:
        self._unit = unit
        self._connection = connection
        self._close_task: asyncio.Task[None] | None = None

    @property
    def unit(self) -> ModbusUnitLike:
        """The wrapped ``ModbusUnit``."""
        return self._unit

    @property
    def connection(self) -> Any | None:
        """The owned ``ModbusConnection``, or ``None`` when shared."""
        return self._connection

    @property
    def owns_link(self) -> bool:
        return self._connection is not None

    @property
    def connected(self) -> bool:
        return bool(self._unit.connected)

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        return list(await self._call(self._unit.read_holding_registers, address, count))

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        return list(await self._call(self._unit.read_input_registers, address, count))

    async def write_register(self, address: int, value: int) -> None:
        await self._call(self._unit.write_register, address, value)

    async def write_registers(self, address: int, values: list[int]) -> None:
        await self._call(self._unit.write_registers, address, values)

    async def recycle(self) -> None:
        """Drop the link (shared or owned); the next request re-dials."""
        try:
            await self._unit.disconnect()
        except Exception as err:  # recycle is best-effort by contract
            _LOGGER.debug("Modbus unit recycle raised %s: %s", type(err).__name__, err)

    def close(self) -> None:
        """Release the client without blocking.

        Owned connections close asynchronously; the task is kept so
        :meth:`aclose` can await it and so it is not garbage-collected
        mid-flight. Shared units are never closed.
        """
        connection = self._connection
        if connection is None or self._close_task is not None:
            return
        self._close_task = asyncio.create_task(self._close_connection(connection))

    async def aclose(self) -> None:
        self.close()
        if self._close_task is not None:
            # Shielded: cancelling the waiter must not cancel the close itself.
            await asyncio.shield(self._close_task)

    async def _close_connection(self, connection: Any) -> None:
        try:
            await connection.close()
        except Exception as err:  # teardown must not raise
            _LOGGER.debug("Modbus connection close raised %s: %s", type(err).__name__, err)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    async def _call(func: Any, *args: Any) -> Any:
        exc = _modbus_connection_exceptions()
        try:
            return await func(*args)
        except exc.ModbusExceptionError as err:
            code = getattr(err, "exception_code", None)
            raise RegisterExceptionResponse(str(err), code=int(code) if code else None) from err
        except exc.ModbusTimeoutError as err:
            raise RegisterTimeoutError(str(err)) from err
        except exc.ModbusError as err:
            # ModbusConnectionError, ModbusProtocolError, ModbusDesyncError,
            # ClientClosedError: the link or the frame is unusable.
            raise RegisterLinkError(str(err)) from err
        except TimeoutError as err:
            raise RegisterTimeoutError(str(err) or "timeout") from err
        except OSError as err:
            raise RegisterLinkError(str(err)) from err
