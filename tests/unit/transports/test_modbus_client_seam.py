"""Tests for the backend-neutral register-client seam (``_modbus_client``).

Covers backend selection, both adapters' error mapping, the
``modbus_connection`` (tmodbus) backend end-to-end against the loopback
fake server, and the host-shared-unit lifecycle Home Assistant's
``async_get_unit`` relies on: no dial on connect, no close on disconnect,
and error-recycle through the unit's own ``disconnect()``.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from modbus_connection import ModbusTcpParams
from modbus_connection import exceptions as mc_exc
from modbus_connection.tmodbus import ModbusConnection
from pymodbus.exceptions import ConnectionException, ModbusIOException

from pylxpweb.transports._modbus_client import (
    ModbusConnectionUnit,
    PymodbusUnit,
    RegisterExceptionResponse,
    RegisterLinkError,
    RegisterTimeoutError,
    normalize_backend,
    resolve_backend,
)
from pylxpweb.transports.config import TransportConfig, TransportType
from pylxpweb.transports.exceptions import (
    TransportConnectionError,
    TransportReadError,
    TransportWriteError,
)
from pylxpweb.transports.factory import create_transport_from_config
from pylxpweb.transports.modbus import ModbusTransport
from pylxpweb.transports.modbus_serial import ModbusSerialTransport

from .test_link_down_fake_server import FakeModbusServer

# ----------------------------------------------------------------------
# Backend selection
# ----------------------------------------------------------------------


class TestBackendSelection:
    def test_normalize_accepts_known_spellings(self) -> None:
        assert normalize_backend("AUTO") == "auto"
        assert normalize_backend("modbus-connection") == "modbus_connection"
        assert normalize_backend(" pymodbus ") == "pymodbus"

    def test_normalize_rejects_unknown(self) -> None:
        with pytest.raises(ValueError, match="Unsupported Modbus backend"):
            normalize_backend("tmodbus")

    def test_auto_is_pymodbus_for_tcp_and_plain_serial(self) -> None:
        assert resolve_backend("auto") == "pymodbus"
        assert resolve_backend("auto", serial_port="/dev/ttyUSB0") == "pymodbus"
        assert resolve_backend("auto", serial_port="rfc2217://10.0.0.5:2217") == "pymodbus"

    def test_auto_picks_modbus_connection_for_serialx_only_urls(self) -> None:
        """pyserial cannot open ``esphome://``; only serialx can (#180)."""
        assert resolve_backend("auto", serial_port="esphome://esp.local:6053") == (
            "modbus_connection"
        )
        assert resolve_backend("auto", serial_port="ESPHOME://esp.local") == "modbus_connection"

    def test_explicit_backends_win_over_auto_rules(self) -> None:
        assert resolve_backend("pymodbus", serial_port="esphome://x") == "pymodbus"
        assert resolve_backend("modbus_connection", serial_port="/dev/ttyUSB0") == (
            "modbus_connection"
        )

    def test_transports_expose_resolved_backend(self) -> None:
        assert ModbusTransport(host="10.0.0.1", serial="CE1").backend == "pymodbus"
        assert (
            ModbusTransport(host="10.0.0.1", serial="CE1", backend="modbus_connection").backend
            == "modbus_connection"
        )
        assert ModbusSerialTransport(port="/dev/ttyUSB0", serial="CE1").backend == "pymodbus"
        assert (
            ModbusSerialTransport(port="esphome://esp.local:6053", serial="CE1").backend
            == "modbus_connection"
        )

    def test_injected_unit_rejects_pymodbus_backend(self) -> None:
        unit = MagicMock()
        with pytest.raises(ValueError, match="injected unit"):
            ModbusTransport(host="10.0.0.1", serial="CE1", backend="pymodbus", unit=unit)
        with pytest.raises(ValueError, match="injected unit"):
            ModbusSerialTransport(port="/dev/ttyUSB0", serial="CE1", backend="pymodbus", unit=unit)

    def test_injected_unit_forces_modbus_connection_backend(self) -> None:
        unit = MagicMock()
        assert ModbusTransport(host="10.0.0.1", serial="CE1", unit=unit).backend == (
            "modbus_connection"
        )


class TestTransportConfigBackend:
    def test_default_and_roundtrip(self) -> None:
        config = TransportConfig(
            host="10.0.0.1", port=502, serial="CE1", transport_type=TransportType.MODBUS_TCP
        )
        assert config.backend == "auto"
        restored = TransportConfig.from_dict(config.to_dict())
        assert restored.backend == "auto"

        config = TransportConfig(
            host="10.0.0.1",
            port=502,
            serial="CE1",
            transport_type=TransportType.MODBUS_TCP,
            backend="Modbus-Connection",
        )
        assert config.backend == "modbus_connection"
        assert TransportConfig.from_dict(config.to_dict()).backend == "modbus_connection"

    def test_legacy_dict_without_backend_defaults_to_auto(self) -> None:
        config = TransportConfig.from_dict(
            {"host": "10.0.0.1", "port": 502, "serial": "CE1", "transport_type": "modbus_tcp"}
        )
        assert config.backend == "auto"

    def test_invalid_backend_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported Modbus backend"):
            TransportConfig(
                host="10.0.0.1",
                port=502,
                serial="CE1",
                transport_type=TransportType.MODBUS_TCP,
                backend="serialx",
            )

    def test_factory_passes_backend_through(self) -> None:
        tcp = create_transport_from_config(
            TransportConfig(
                host="10.0.0.1",
                port=502,
                serial="CE1",
                transport_type=TransportType.MODBUS_TCP,
                backend="modbus_connection",
            )
        )
        assert isinstance(tcp, ModbusTransport)
        assert tcp.backend == "modbus_connection"

        serial = create_transport_from_config(
            TransportConfig(
                host="",
                port=0,
                serial="CE1",
                transport_type=TransportType.MODBUS_SERIAL,
                serial_port="esphome://esp.local:6053",
            )
        )
        assert isinstance(serial, ModbusSerialTransport)
        assert serial.backend == "modbus_connection"


# ----------------------------------------------------------------------
# pymodbus adapter
# ----------------------------------------------------------------------


def _pymodbus_response(*, error: bool = False, registers: list[int] | None = None) -> MagicMock:
    response = MagicMock()
    response.isError.return_value = error
    response.registers = registers
    response.exception_code = 2 if error else None
    return response


class TestPymodbusUnit:
    @pytest.mark.asyncio
    async def test_reads_use_keyword_device_id_form(self) -> None:
        client = MagicMock()
        client.read_input_registers = AsyncMock(return_value=_pymodbus_response(registers=[1, 2]))
        unit = PymodbusUnit(client, 7)

        assert await unit.read_input_registers(10, 2) == [1, 2]
        client.read_input_registers.assert_awaited_once_with(address=10, count=2, device_id=7)

    @pytest.mark.asyncio
    async def test_exception_response_maps_with_code(self) -> None:
        client = MagicMock()
        client.read_holding_registers = AsyncMock(return_value=_pymodbus_response(error=True))
        unit = PymodbusUnit(client, 1)

        with pytest.raises(RegisterExceptionResponse, match="Modbus read error at address 5") as ei:
            await unit.read_holding_registers(5, 1)
        assert ei.value.code == 2

    @pytest.mark.asyncio
    async def test_missing_registers_is_link_error(self) -> None:
        client = MagicMock()
        client.read_holding_registers = AsyncMock(return_value=_pymodbus_response())
        unit = PymodbusUnit(client, 1)

        with pytest.raises(RegisterLinkError, match="no registers in response"):
            await unit.read_holding_registers(5, 1)

    @pytest.mark.asyncio
    async def test_timeout_and_connection_exceptions_map_and_chain(self) -> None:
        client = MagicMock()
        client.read_input_registers = AsyncMock(
            side_effect=ModbusIOException("Modbus Error: [Input/Output] timeout")
        )
        client.write_register = AsyncMock(side_effect=ConnectionException("Not connected"))
        unit = PymodbusUnit(client, 1)

        with pytest.raises(RegisterTimeoutError) as timeout_info:
            await unit.read_input_registers(0, 1)
        assert isinstance(timeout_info.value.__cause__, ModbusIOException)
        assert isinstance(timeout_info.value, TimeoutError)

        with pytest.raises(RegisterLinkError) as link_info:
            await unit.write_register(0, 1)
        assert isinstance(link_info.value.__cause__, ConnectionException)

    @pytest.mark.asyncio
    async def test_write_exception_response(self) -> None:
        client = MagicMock()
        client.write_registers = AsyncMock(return_value=_pymodbus_response(error=True))
        unit = PymodbusUnit(client, 1)

        with pytest.raises(RegisterExceptionResponse, match="Modbus write error at address 3"):
            await unit.write_registers(3, [1, 2])

    @pytest.mark.asyncio
    async def test_close_is_idempotent_and_owned(self) -> None:
        client = MagicMock()
        unit = PymodbusUnit(client, 1)
        assert unit.owns_link is True
        unit.close()
        await unit.aclose()
        client.close.assert_called_once()


# ----------------------------------------------------------------------
# modbus_connection adapter
# ----------------------------------------------------------------------


class _FakeUnit:
    """Minimal ``ModbusUnit``-shaped fake raising configurable errors."""

    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.connected = False
        self.disconnect_calls = 0

    async def _raise_or(self, value: Any) -> Any:
        if self.error is not None:
            raise self.error
        return value

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        return await self._raise_or([address] * count)

    async def read_input_registers(self, address: int, count: int) -> list[int]:
        return await self._raise_or([address + 1] * count)

    async def write_register(self, address: int, value: int) -> None:
        await self._raise_or(None)

    async def write_registers(self, address: int, values: list[int]) -> None:
        await self._raise_or(None)

    async def disconnect(self) -> None:
        self.disconnect_calls += 1
        self.connected = False


class TestModbusConnectionUnit:
    @pytest.mark.asyncio
    async def test_success_paths(self) -> None:
        unit = ModbusConnectionUnit(_FakeUnit())
        assert await unit.read_holding_registers(4, 2) == [4, 4]
        assert await unit.read_input_registers(4, 1) == [5]
        await unit.write_register(1, 1)
        await unit.write_registers(1, [1, 2])
        assert unit.owns_link is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (
                mc_exc.ModbusExceptionError.from_code(2, "illegal address"),
                RegisterExceptionResponse,
            ),
            (mc_exc.ModbusTimeoutError("slow"), RegisterTimeoutError),
            (mc_exc.ModbusConnectionError("down"), RegisterLinkError),
            (mc_exc.ModbusDesyncError("desync"), RegisterLinkError),
            (mc_exc.ClientClosedError("closed"), RegisterLinkError),
            (mc_exc.ModbusProtocolError("garbage"), RegisterLinkError),
            (TimeoutError(), RegisterTimeoutError),
            (OSError("eio"), RegisterLinkError),
        ],
    )
    async def test_error_mapping(self, error: BaseException, expected: type[Exception]) -> None:
        unit = ModbusConnectionUnit(_FakeUnit(error))
        with pytest.raises(expected) as ei:
            await unit.read_holding_registers(0, 1)
        assert ei.value.__cause__ is error

    @pytest.mark.asyncio
    async def test_exception_response_carries_code(self) -> None:
        unit = ModbusConnectionUnit(_FakeUnit(mc_exc.ModbusExceptionError.from_code(4, "fail")))
        with pytest.raises(RegisterExceptionResponse) as ei:
            await unit.write_register(0, 1)
        assert ei.value.code == 4

    @pytest.mark.asyncio
    async def test_shared_unit_is_never_closed_but_can_be_recycled(self) -> None:
        fake = _FakeUnit()
        unit = ModbusConnectionUnit(fake)
        unit.close()
        await unit.aclose()
        assert fake.disconnect_calls == 0
        await unit.recycle()
        assert fake.disconnect_calls == 1

    @pytest.mark.asyncio
    async def test_owned_connection_closes_once(self) -> None:
        connection = MagicMock()
        connection.close = AsyncMock()
        unit = ModbusConnectionUnit(_FakeUnit(), connection=connection)
        assert unit.owns_link is True
        unit.close()
        unit.close()
        await unit.aclose()
        connection.close.assert_awaited_once()


# ----------------------------------------------------------------------
# modbus_connection backend end-to-end over loopback (real tmodbus)
# ----------------------------------------------------------------------


def _mc_transport(port: int, **kwargs: Any) -> ModbusTransport:
    return ModbusTransport(
        host="127.0.0.1",
        port=port,
        serial="1234567890",
        timeout=1.0,
        retries=0,
        retry_delay=0.01,
        inter_register_delay=0.0,
        backend="modbus_connection",
        **kwargs,
    )


class TestModbusConnectionBackendTcp:
    @pytest.mark.asyncio
    async def test_connect_read_write_check_link_disconnect(self) -> None:
        server = FakeModbusServer()
        await server.start()
        transport = _mc_transport(server.port)
        try:
            await transport.connect()
            assert transport.is_connected is True
            assert transport.backend == "modbus_connection"
            assert isinstance(transport._client, ModbusConnection)
            assert transport.backend_shares_link is False

            assert await transport.read_parameters(0, 3) == {0: 0, 1: 0, 2: 0}
            assert await transport.write_parameters({66: 50}) is True
            assert await transport.write_parameters({66: 50, 67: 60}) is True
            assert await transport.check_link() is True
            assert server.request_count == 4

            runtime, energy, _bank = await transport.read_all_input_data()
            assert runtime is not None
            assert energy is not None
        finally:
            connection = transport._client
            await transport.disconnect()
            assert transport.is_connected is False
            assert transport._client is None
            assert connection is not None and connection.connected is False
            await server.stop()

    @pytest.mark.asyncio
    async def test_connect_refused_is_typed_with_cooldown(self) -> None:
        server = FakeModbusServer()
        await server.start()
        port = server.port
        await server.stop()

        transport = _mc_transport(port)
        with pytest.raises(TransportConnectionError, match="Failed to connect"):
            await transport.connect()
        assert transport.is_connected is False
        assert transport._client is None
        with pytest.raises(TransportConnectionError, match="cooldown"):
            await transport.read_parameters(0, 1)

    @pytest.mark.asyncio
    async def test_mute_peer_probe_and_error_recycle(self) -> None:
        """A wedged owned link recycles by close + re-dial, as with pymodbus."""
        server = FakeModbusServer()
        await server.start()
        port = server.port
        transport = _mc_transport(port)
        try:
            await transport.connect()
            first_connection = transport._client
            assert await transport.read_parameters(0, 1) == {0: 0}

            await server.stop()
            for _ in range(transport._max_consecutive_errors):
                with pytest.raises(TransportReadError):
                    await transport.read_parameters(0, 1)
            assert transport._consecutive_errors >= transport._max_consecutive_errors

            server = FakeModbusServer()
            await server.start(port)
            assert await transport.read_parameters(0, 1) == {0: 0}
            assert transport._client is not first_connection
            assert transport._consecutive_errors == 0
        finally:
            await transport.disconnect()
            await server.stop()


class TestSharedUnitLifecycle:
    """The Home Assistant ``async_get_unit`` contract on an injected unit."""

    @pytest.mark.asyncio
    async def test_no_dial_on_connect_and_no_close_on_disconnect(self) -> None:
        server = FakeModbusServer()
        await server.start()
        connection = ModbusConnection(
            ModbusTcpParams(host="127.0.0.1", port=server.port), timeout=1.0
        )
        unit = connection.for_unit(1)
        transport = _mc_transport(server.port, unit=unit)
        try:
            await transport.connect()
            assert transport.is_connected is True
            assert transport.backend_shares_link is True
            # Asking for a unit performs no I/O: the first read opens the link.
            assert connection.connected is False
            assert server.request_count == 0

            assert await transport.read_parameters(0, 2) == {0: 0, 1: 0}
            assert connection.connected is True
            assert await transport.write_parameters({66: 50}) is True

            await transport.disconnect()
            assert transport.is_connected is False
            # The host owns the link: still open after our disconnect.
            assert connection.connected is True

            # Re-attaching the same unit keeps working without a new dial.
            await transport.connect()
            assert await transport.read_parameters(0, 1) == {0: 0}
        finally:
            await transport.async_shutdown()
            assert connection.connected is True
            await connection.close()
            await server.stop()

    @pytest.mark.asyncio
    async def test_error_recycle_goes_through_unit_disconnect(self) -> None:
        server = FakeModbusServer()
        await server.start()
        port = server.port
        connection = ModbusConnection(ModbusTcpParams(host="127.0.0.1", port=port), timeout=1.0)
        unit = connection.for_unit(1)
        transport = _mc_transport(port, unit=unit)
        try:
            await transport.connect()
            assert await transport.read_parameters(0, 1) == {0: 0}
            assert connection.connected is True

            await server.stop()
            for _ in range(transport._max_consecutive_errors):
                with pytest.raises(TransportReadError):
                    await transport.read_parameters(0, 1)

            server = FakeModbusServer()
            await server.start(port)
            # The recycle drops the host's link via unit.disconnect(); the
            # next request re-dials on the host's connection object.
            assert await transport.read_parameters(0, 1) == {0: 0}
            assert transport._client is unit
            assert transport._consecutive_errors == 0
            assert transport._session_reconnect_count == 1
            assert connection.connected is True
        finally:
            await transport.disconnect()
            await connection.close()
            await server.stop()

    @pytest.mark.asyncio
    async def test_exception_response_keeps_link_healthy(self) -> None:
        """A device-refused probe proves the link alive; a refused write does
        not count against link health (mirrors the pymodbus contract)."""
        fake = _FakeUnit(mc_exc.ModbusExceptionError.from_code(2, "illegal address"))
        transport = ModbusTransport(host="10.0.0.1", serial="CE1", unit=fake, retries=0)
        await transport.connect()
        assert await transport.check_link() is True
        with pytest.raises(TransportWriteError):
            await transport.write_parameters({66: 50})
        assert transport._consecutive_errors == 0
        with pytest.raises(TransportReadError, match="illegal address"):
            await transport.read_parameters(0, 1)
        assert transport._consecutive_errors == 1


class TestModbusConnectionBackendSerial:
    def test_esphome_url_scheme_is_openable(self) -> None:
        """The ``modbus-connection`` extra must make ``esphome://`` reachable.

        serialx only registers the scheme when aioesphomeapi is importable
        (its ``esphome`` extra), so a missing dependency would leave the
        auto-selected backend unable to open the port (#180).
        """
        import importlib

        importlib.import_module("aioesphomeapi")
        esphome = importlib.import_module("serialx.platforms.serial_esphome")
        assert esphome is not None

    @pytest.mark.asyncio
    async def test_socket_url_connect_refused_is_typed(self) -> None:
        server = FakeModbusServer()
        await server.start()
        port = server.port
        await server.stop()

        transport = ModbusSerialTransport(
            port=f"socket://127.0.0.1:{port}",
            serial="CE1",
            timeout=1.0,
            backend="modbus_connection",
        )
        assert transport.backend == "modbus_connection"
        with pytest.raises(TransportConnectionError, match="Failed to connect"):
            await transport.connect()
        assert transport.is_connected is False
        assert transport._client is None

    @pytest.mark.asyncio
    async def test_injected_unit_is_never_closed(self) -> None:
        fake = _FakeUnit()
        transport = ModbusSerialTransport(port="/dev/ttyUSB0", serial="CE1", unit=fake)
        await transport.connect()
        assert transport.backend_shares_link is True
        assert await transport.read_parameters(2, 1) == {2: 2}
        await transport.disconnect()
        assert fake.disconnect_calls == 0


# ----------------------------------------------------------------------
# Lifecycle regressions (adversarial review, 2026-09-04)
# ----------------------------------------------------------------------


class TestLifecycleRegressions:
    @pytest.mark.asyncio
    async def test_tcp_async_shutdown_awaits_owned_close(self) -> None:
        """A released endpoint is really closed when async_shutdown() returns."""
        server = FakeModbusServer()
        await server.start()
        transport = _mc_transport(server.port)
        try:
            await transport.connect()
            connection = transport._client
            assert isinstance(connection, ModbusConnection)
            await transport.async_shutdown()
            assert connection.connected is False
            assert transport._draining_units == []
            with pytest.raises(TransportConnectionError, match="shut down"):
                await transport.connect()
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_serial_cancelled_dial_does_not_orphan_connection(self) -> None:
        """Cancel a dial, dial again, disconnect: every connection ends closed."""
        server = FakeModbusServer()
        await server.start()
        transport = ModbusSerialTransport(
            port=f"socket://127.0.0.1:{server.port}",
            serial="CE1",
            timeout=2.0,
            backend="modbus_connection",
        )
        connections: list[ModbusConnection] = []
        try:
            task = asyncio.create_task(transport.connect())
            for _ in range(50):
                await asyncio.sleep(0)
                if transport._client is not None:
                    break
            assert isinstance(transport._client, ModbusConnection)
            connections.append(transport._client)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            assert transport.is_connected is False

            await transport.connect()
            assert isinstance(transport._client, ModbusConnection)
            connections.append(transport._client)
            assert connections[0] is not connections[1]

            await transport.disconnect()
            for connection in connections:
                assert connection.connected is False
            assert transport._draining_units == []
        finally:
            for connection in connections:
                await connection.close()
            await server.stop()

    @pytest.mark.asyncio
    async def test_shared_link_not_recycled_for_exception_responses(self) -> None:
        """Refused reads never disconnect an endpoint other units share."""
        fake = _FakeUnit(mc_exc.ModbusExceptionError.from_code(2, "illegal address"))
        transport = ModbusTransport(host="10.0.0.1", serial="CE1", unit=fake, retries=0)
        await transport.connect()
        for _ in range(transport._max_consecutive_errors + 2):
            with pytest.raises(TransportReadError):
                await transport.read_parameters(0, 1)
        assert transport._consecutive_errors > transport._max_consecutive_errors
        assert transport._consecutive_link_errors == 0
        assert fake.disconnect_calls == 0
        assert transport._session_reconnect_count == 0

    @pytest.mark.asyncio
    async def test_shared_link_recycled_for_link_errors(self) -> None:
        for make in (
            lambda fake: ModbusTransport(host="10.0.0.1", serial="CE1", unit=fake, retries=0),
            lambda fake: ModbusSerialTransport(
                port="/dev/ttyUSB0", serial="CE1", unit=fake, retries=0
            ),
        ):
            fake = _FakeUnit(mc_exc.ModbusConnectionError("down"))
            transport = make(fake)
            await transport.connect()
            for _ in range(transport._max_consecutive_errors):
                with pytest.raises(TransportReadError):
                    await transport.read_parameters(0, 1)
            assert fake.disconnect_calls == 0
            fake.error = None
            assert await transport.read_parameters(0, 1) == {0: 0}
            assert fake.disconnect_calls == 1
            assert transport._consecutive_link_errors == 0

    def test_transport_config_positional_arguments_keep_their_meaning(self) -> None:
        """``backend`` is appended, so ``max_input_block_size`` stays positional."""
        config = TransportConfig(
            "10.0.0.1",
            502,
            "CE1",
            TransportType.MODBUS_TCP,
            None,
            1,
            None,
            10.0,
            None,
            19200,
            "N",
            1,
            2,
            0.5,
            0.05,
            120,
        )
        assert config.max_input_block_size == 120
        assert config.backend == "auto"
