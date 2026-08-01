"""Tests for BatteryModbusTransport."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.battery_protocols.detection import _DETECTION_RANGE_END
from pylxpweb.battery_protocols.eg4_master import EG4MasterProtocol
from pylxpweb.battery_protocols.eg4_slave import EG4SlaveProtocol
from pylxpweb.transports.battery_modbus import (
    _DETECTION_REGISTER_COUNT,
    _INITIAL_BLOCK_COUNT,
    _MIN_INITIAL_REGISTERS,
    _PROTOCOL_MAP,
    _UNIT_TOPOLOGY_RETENTION,
    BatteryModbusTransport,
    _initial_block_requirement,
)
from pylxpweb.transports.data import BatteryData, InverterRuntimeData


@pytest.fixture
def transport() -> BatteryModbusTransport:
    """Create a transport with explicit unit IDs."""
    return BatteryModbusTransport(
        host="10.100.3.27",
        port=502,
        unit_ids=[1, 2, 3],
        inverter_serial="1234567890",
    )


@pytest.fixture
def connected_transport(transport: BatteryModbusTransport) -> BatteryModbusTransport:
    """Create a transport with a mocked connected client."""
    mock_client = AsyncMock()
    mock_client.connected = True
    # close() is synchronous on real pymodbus client
    mock_client.close = MagicMock()
    transport._client = mock_client
    transport._connected = True
    return transport


class TestBatteryModbusTransportInit:
    """Tests for transport initialization."""

    def test_basic_init(self, transport: BatteryModbusTransport) -> None:
        """Transport stores host, port, unit_ids, and serial."""
        assert transport.host == "10.100.3.27"
        assert transport.port == 502
        assert transport.unit_ids == [1, 2, 3]
        assert transport.inverter_serial == "1234567890"
        assert transport.is_connected is False

    def test_default_unit_ids_none(self) -> None:
        """When no unit_ids given, default is None (scan mode)."""
        t = BatteryModbusTransport(host="10.100.3.27")
        assert t.unit_ids is None
        assert t.max_units == 8

    def test_protocol_auto(self) -> None:
        """Default protocol is 'auto' for auto-detection."""
        t = BatteryModbusTransport(host="10.100.3.27", protocol="auto")
        assert t.protocol_name == "auto"

    def test_explicit_protocol(self) -> None:
        """Explicit protocol name is stored."""
        t = BatteryModbusTransport(host="10.100.3.27", protocol="eg4_slave")
        assert t.protocol_name == "eg4_slave"

    def test_default_timeout(self) -> None:
        """Default timeout is 3.0 seconds."""
        t = BatteryModbusTransport(host="10.100.3.27")
        assert t.timeout == 3.0

    def test_custom_max_units(self) -> None:
        """Custom max_units for bus scanning."""
        t = BatteryModbusTransport(host="10.100.3.27", max_units=16)
        assert t.max_units == 16

    def test_empty_detected_protocols_cache(self, transport: BatteryModbusTransport) -> None:
        """Protocol cache starts empty."""
        assert transport._detected_protocols == {}


class TestBatteryModbusTransportContextManager:
    """Tests for async context manager (__aenter__/__aexit__)."""

    @pytest.mark.asyncio
    async def test_context_manager_connects_and_disconnects(self) -> None:
        """async with connects on enter and disconnects on exit."""
        transport = BatteryModbusTransport(host="10.100.3.27")
        mock_client = AsyncMock()
        mock_client.connected = True
        mock_client.connect = AsyncMock()
        mock_client.close = MagicMock()

        with patch(
            "pylxpweb.transports.battery_modbus.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            async with transport as t:
                assert t is transport
                assert t.is_connected is True

        assert transport.is_connected is False
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_disconnects_on_exception(self) -> None:
        """Transport disconnects even if body raises."""
        transport = BatteryModbusTransport(host="10.100.3.27")
        mock_client = AsyncMock()
        mock_client.connected = True
        mock_client.connect = AsyncMock()
        mock_client.close = MagicMock()

        with (
            patch(
                "pylxpweb.transports.battery_modbus.AsyncModbusTcpClient",
                return_value=mock_client,
            ),
            pytest.raises(RuntimeError, match="test error"),
        ):
            async with transport:
                raise RuntimeError("test error")

        assert transport.is_connected is False
        mock_client.close.assert_called_once()


class TestBatteryModbusTransportConnect:
    """Tests for connect/disconnect lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        """Successful connection sets is_connected to True."""
        transport = BatteryModbusTransport(host="10.100.3.27")
        mock_client = AsyncMock()
        mock_client.connected = True
        mock_client.connect = AsyncMock()

        with patch(
            "pylxpweb.transports.battery_modbus.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await transport.connect()

        assert transport.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_failure(self) -> None:
        """Failed connection keeps is_connected as False."""
        transport = BatteryModbusTransport(host="10.100.3.27")
        mock_client = AsyncMock()
        mock_client.connected = False
        mock_client.connect = AsyncMock()

        with patch(
            "pylxpweb.transports.battery_modbus.AsyncModbusTcpClient",
            return_value=mock_client,
        ):
            await transport.connect()

        assert transport.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_waits_for_in_flight_read(self) -> None:
        """A public connect cannot replace the client between read blocks (#248)."""
        transport = BatteryModbusTransport(host="10.100.3.27", unit_ids=[2])
        original_client = AsyncMock()
        original_client.connected = True
        original_client.close = MagicMock()
        transport._client = original_client
        transport._connected = True

        first_block_started = asyncio.Event()
        release_first_block = asyncio.Event()
        original_calls = 0

        async def read_original_block(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal original_calls
            original_calls += 1
            if original_calls == 1:
                first_block_started.set()
                await release_first_block.wait()
                return _mock_result(_make_slave_regs())
            return _mock_result([0] * 23)

        original_client.read_holding_registers = AsyncMock(side_effect=read_original_block)

        replacement_client = AsyncMock()
        replacement_client.connected = True
        replacement_client.connect = AsyncMock()
        replacement_client.close = MagicMock()
        replacement_client.read_holding_registers = AsyncMock(return_value=_mock_result([0] * 23))

        with patch(
            "pylxpweb.transports.battery_modbus.AsyncModbusTcpClient",
            return_value=replacement_client,
        ):
            read_task = asyncio.create_task(transport.read_unit(2))
            await asyncio.wait_for(first_block_started.wait(), timeout=1.0)

            connect_task = asyncio.create_task(transport.connect())
            await asyncio.sleep(0)
            connect_interleaved = connect_task.done()

            release_first_block.set()
            data = await asyncio.wait_for(read_task, timeout=1.0)
            await asyncio.wait_for(connect_task, timeout=1.0)

        assert connect_interleaved is False
        assert data is not None
        assert original_client.read_holding_registers.await_count == 2
        replacement_client.read_holding_registers.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disconnect(self, connected_transport: BatteryModbusTransport) -> None:
        """Disconnect closes client and clears connected flag."""
        assert connected_transport.is_connected is True
        await connected_transport.disconnect()
        assert connected_transport.is_connected is False
        connected_transport._client.close.assert_called_once()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_disconnect_no_client(self) -> None:
        """Disconnect when no client is a no-op."""
        transport = BatteryModbusTransport(host="10.100.3.27")
        await transport.disconnect()  # Should not raise
        assert transport.is_connected is False

    def test_is_connected_tracks_underlying_client(
        self, connected_transport: BatteryModbusTransport
    ) -> None:
        """A mid-session socket drop is visible without explicit disconnect()."""
        assert connected_transport.is_connected is True

        connected_transport._client.connected = False

        assert connected_transport.is_connected is False


class TestBatteryModbusTransportReadUnit:
    """Tests for reading a single battery unit."""

    @pytest.mark.asyncio
    async def test_read_unit_slave(self, connected_transport: BatteryModbusTransport) -> None:
        """Reading a slave unit returns BatteryData with correct values."""
        # Simulate slave battery response (voltage at reg 0)
        slave_regs = [0] * 42
        slave_regs[0] = 5294  # 52.94V
        slave_regs[1] = 100  # 1.00A
        slave_regs[24] = 76  # SOC
        slave_regs[23] = 100  # SOH
        slave_regs[36] = 16  # num cells
        # Set some cell voltages (regs 2-17)
        for i in range(16):
            slave_regs[2 + i] = 3300  # 3.300V per cell

        mock_result = MagicMock()
        mock_result.isError.return_value = False
        mock_result.registers = slave_regs
        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            return_value=mock_result,
        )

        data = await connected_transport.read_unit(2)
        assert data is not None
        assert data.voltage == pytest.approx(52.94)
        assert data.current == pytest.approx(1.00)
        assert data.soc == 76
        assert data.soh == 100
        assert data.battery_index == 1  # unit_id 2 -> index 1

    @pytest.mark.asyncio
    async def test_read_unit_master(self, connected_transport: BatteryModbusTransport) -> None:
        """Reading unit 1 (master) auto-detects master protocol."""
        # Master: regs 0-18 all zeros, data starts at reg 19
        master_regs = [0] * 42
        master_regs[21] = 76  # SOC direct % (aggregate)
        master_regs[22] = 5294  # voltage /100 = 52.94V
        master_regs[23] = 200  # current /100 = 2.00A (aggregate)
        master_regs[24] = 35  # temperature = 35°C
        master_regs[32] = 98  # SOH = 98%
        master_regs[41] = 16  # num cells

        # First call returns runtime regs (0-41), subsequent calls for cell block
        mock_result_runtime = MagicMock()
        mock_result_runtime.isError.return_value = False
        mock_result_runtime.registers = master_regs

        cell_regs = [3300] * 16
        mock_result_cells = MagicMock()
        mock_result_cells.isError.return_value = False
        mock_result_cells.registers = cell_regs

        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            side_effect=[mock_result_runtime, mock_result_cells],
        )

        data = await connected_transport.read_unit(1)
        assert data is not None
        assert data.voltage == pytest.approx(52.8)
        assert data.soc == 76
        assert data.battery_index == 0  # unit_id 1 -> index 0

    @pytest.mark.asyncio
    async def test_read_unit_no_response(self, connected_transport: BatteryModbusTransport) -> None:
        """No response from unit returns None."""
        mock_result = MagicMock()
        mock_result.isError.return_value = True
        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            return_value=mock_result,
        )

        data = await connected_transport.read_unit(5)
        assert data is None

    @pytest.mark.asyncio
    async def test_read_unit_exception(self, connected_transport: BatteryModbusTransport) -> None:
        """Exception during read returns None."""
        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            side_effect=TimeoutError("Connection timeout"),
        )

        data = await connected_transport.read_unit(2)
        assert data is None

    @pytest.mark.asyncio
    async def test_read_unit_not_connected(self, transport: BatteryModbusTransport) -> None:
        """Reading when not connected returns None."""
        data = await transport.read_unit(1)
        assert data is None

    @pytest.mark.asyncio
    async def test_protocol_cache(self, connected_transport: BatteryModbusTransport) -> None:
        """Protocol is cached after first detection."""
        slave_regs = [0] * 42
        slave_regs[0] = 5294
        slave_regs[1] = 100
        slave_regs[24] = 76
        slave_regs[23] = 100
        slave_regs[36] = 16
        for i in range(16):
            slave_regs[2 + i] = 3300

        mock_result = MagicMock()
        mock_result.isError.return_value = False
        mock_result.registers = slave_regs
        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            return_value=mock_result,
        )

        # First read detects and caches
        await connected_transport.read_unit(2)
        assert 2 in connected_transport._detected_protocols

        # Second read uses cached protocol
        await connected_transport.read_unit(2)
        # Protocol should still be the same object
        assert connected_transport._detected_protocols[2].name == "eg4_slave"


class TestBatteryModbusTransportExplicitProtocol:
    """Tests for explicit protocol selection (not auto-detect)."""

    @pytest.mark.asyncio
    async def test_explicit_slave_protocol(self) -> None:
        """Explicit eg4_slave protocol skips auto-detection."""
        transport = BatteryModbusTransport(
            host="10.100.3.27",
            protocol="eg4_slave",
            unit_ids=[2],
        )
        transport._client = AsyncMock()
        transport._connected = True

        slave_regs = [0] * 42
        slave_regs[0] = 5294
        slave_regs[24] = 76
        slave_regs[36] = 16

        mock_result = MagicMock()
        mock_result.isError.return_value = False
        mock_result.registers = slave_regs
        transport._client.read_holding_registers = AsyncMock(return_value=mock_result)

        data = await transport.read_unit(2)
        assert data is not None
        # Cache should not be populated for explicit protocol
        assert 2 not in transport._detected_protocols

    @pytest.mark.asyncio
    async def test_unknown_protocol_falls_back_to_auto(self) -> None:
        """Unknown protocol name falls back to auto-detection."""
        transport = BatteryModbusTransport(
            host="10.100.3.27",
            protocol="unknown_protocol",
            unit_ids=[2],
        )
        transport._client = AsyncMock()
        transport._connected = True

        slave_regs = [0] * 42
        slave_regs[0] = 5294
        slave_regs[24] = 76
        slave_regs[36] = 16
        for i in range(16):
            slave_regs[2 + i] = 3300

        mock_result = MagicMock()
        mock_result.isError.return_value = False
        mock_result.registers = slave_regs
        transport._client.read_holding_registers = AsyncMock(return_value=mock_result)

        data = await transport.read_unit(2)
        assert data is not None
        # Should have auto-detected and cached
        assert 2 in transport._detected_protocols


class TestBatteryModbusTransportScanUnits:
    """Tests for unit scanning/discovery."""

    @pytest.mark.asyncio
    async def test_scan_with_explicit_unit_ids(
        self, connected_transport: BatteryModbusTransport
    ) -> None:
        """Scan returns explicit unit_ids without probing."""
        result = await connected_transport.scan_units()
        assert result == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_scan_discovers_units(self) -> None:
        """Scan probes bus and returns responding unit IDs."""
        transport = BatteryModbusTransport(
            host="10.100.3.27",
            max_units=4,
        )
        transport._client = AsyncMock()
        transport._connected = True

        # Units 1 and 3 respond, 2 and 4 don't
        ok_result = MagicMock()
        ok_result.isError.return_value = False
        ok_result.registers = [100]

        err_result = MagicMock()
        err_result.isError.return_value = True

        transport._client.read_holding_registers = AsyncMock(
            side_effect=[ok_result, err_result, ok_result, err_result],
        )

        result = await transport.scan_units()
        assert result == [1, 3]

    @pytest.mark.asyncio
    async def test_individual_scan_misses_on_responding_bus_do_not_escalate(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Expected per-ID misses stay silent when at least one unit proves the bus is live."""
        transport = BatteryModbusTransport(
            host="10.100.3.27",
            max_units=4,
        )
        transport._client = AsyncMock()
        transport._client.connected = True
        transport._connected = True

        err_result = MagicMock()
        err_result.isError.return_value = True
        ok_result = MagicMock()
        ok_result.isError.return_value = False
        ok_result.registers = [100]

        transport._client.read_holding_registers = AsyncMock(
            side_effect=[err_result, ok_result, err_result, err_result]
        )

        with (
            caplog.at_level(logging.WARNING),
            patch.object(transport, "_reconnect", new_callable=AsyncMock) as reconnect,
        ):
            result = await transport.scan_units()

        assert result == [2]
        assert transport._consecutive_errors == 0
        assert transport._degraded_units == set()
        reconnect.assert_not_awaited()
        assert not [record for record in caplog.records if record.levelno >= logging.WARNING]

    @pytest.mark.asyncio
    async def test_empty_scan_warns_once_and_reaches_reconnect_gate(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A wholly silent scan is one bus failure and eventually reconnects (#248)."""
        transport = BatteryModbusTransport(host="10.100.3.27", max_units=2)
        transport._client = AsyncMock()
        transport._client.connected = False
        transport._connected = False
        transport._client.read_holding_registers = AsyncMock(return_value=_mock_error())

        with (
            caplog.at_level(logging.WARNING),
            patch("pylxpweb.transports.battery_modbus.asyncio.sleep", new_callable=AsyncMock),
            patch.object(transport, "_reconnect", new_callable=AsyncMock) as reconnect,
        ):
            for _ in range(transport._max_consecutive_errors):
                assert await transport.scan_units() == []

        assert transport._consecutive_errors == transport._max_consecutive_errors
        reconnect.assert_awaited_once()
        warnings = [
            record
            for record in caplog.records
            if record.levelno == logging.WARNING and "no units responded" in record.getMessage()
        ]
        assert len(warnings) == 1
        assert "10.100.3.27:502" in warnings[0].getMessage()
        assert "1-2" in warnings[0].getMessage()
        assert transport._degraded_units == set()

    @pytest.mark.asyncio
    async def test_nonempty_scan_logs_recovery_and_resets_bus_fault(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The first responding unit clears the empty-scan episode and counter."""
        transport = BatteryModbusTransport(host="10.100.3.27", max_units=1)
        transport._client = AsyncMock()
        transport._client.connected = True
        transport._connected = True
        transport._client.read_holding_registers = AsyncMock(
            side_effect=[_mock_error(), _mock_result([100])]
        )

        with (
            caplog.at_level(logging.INFO),
            patch("pylxpweb.transports.battery_modbus.asyncio.sleep", new_callable=AsyncMock),
        ):
            assert await transport.scan_units() == []
            assert await transport.scan_units() == [1]

        assert transport._consecutive_errors == 0
        assert sum("no units responded" in r.getMessage() for r in caplog.records) == 1
        assert sum("responding again" in r.getMessage() for r in caplog.records) == 1

    @pytest.mark.asyncio
    async def test_scan_holds_operation_lock_across_all_probes(self) -> None:
        """A public unit read cannot race the shared client during a scan loop."""
        transport = BatteryModbusTransport(host="10.100.3.27", max_units=2)

        async def probe(*_args: object, **_kwargs: object) -> list[int]:
            assert transport._operation_lock.locked()
            return [100]

        with (
            patch.object(transport, "_read_registers", side_effect=probe),
            patch("pylxpweb.transports.battery_modbus.asyncio.sleep", new_callable=AsyncMock),
        ):
            assert await transport.scan_units() == [1, 2]


class TestBatteryModbusTransportReadAll:
    """Tests for reading all battery units."""

    @pytest.mark.asyncio
    async def test_read_all_explicit_units(
        self, connected_transport: BatteryModbusTransport
    ) -> None:
        """read_all reads all configured unit IDs."""
        slave_regs = [0] * 42
        slave_regs[0] = 5294
        slave_regs[24] = 76
        slave_regs[36] = 16
        for i in range(16):
            slave_regs[2 + i] = 3300

        # Master regs: 0-18 zeros, data at 19+
        master_regs = [0] * 42
        master_regs[22] = 5294
        master_regs[26] = 760
        master_regs[41] = 16

        cell_regs = [3300] * 16
        mock_cell_result = MagicMock()
        mock_cell_result.isError.return_value = False
        mock_cell_result.registers = cell_regs

        mock_master = MagicMock()
        mock_master.isError.return_value = False
        mock_master.registers = master_regs

        mock_slave = MagicMock()
        mock_slave.isError.return_value = False
        mock_slave.registers = slave_regs

        mock_err = MagicMock()
        mock_err.isError.return_value = True

        # Unit 1 (master): runtime + cells; Unit 2 (slave): runtime + info; Unit 3: error
        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            side_effect=[
                mock_master,
                mock_cell_result,  # master cell block
                mock_slave,
                mock_slave,  # slave info block
                mock_err,  # unit 3 fails
            ],
        )

        results = await connected_transport.read_all()
        assert len(results) == 2
        assert results[0].battery_index == 0  # unit 1 -> index 0
        assert results[1].battery_index == 1  # unit 2 -> index 1

    @pytest.mark.asyncio
    async def test_read_all_no_units(self) -> None:
        """read_all returns empty list when no unit_ids and no scan results."""
        transport = BatteryModbusTransport(
            host="10.100.3.27",
            max_units=2,
        )
        transport._client = AsyncMock()
        transport._connected = True

        err_result = MagicMock()
        err_result.isError.return_value = True
        transport._client.read_holding_registers = AsyncMock(return_value=err_result)

        results = await transport.read_all()
        assert results == []


class TestBatteryModbusTransportReadRegisters:
    """Tests for the internal _read_registers method."""

    @pytest.mark.asyncio
    async def test_read_registers_no_client(self, transport: BatteryModbusTransport) -> None:
        """Returns None when client is not set."""
        result = await transport._read_registers(0, 10, 1)
        assert result is None

    @pytest.mark.asyncio
    async def test_read_registers_success(
        self, connected_transport: BatteryModbusTransport
    ) -> None:
        """Successful read returns list of register values."""
        mock_result = MagicMock()
        mock_result.isError.return_value = False
        mock_result.registers = [100, 200, 300]
        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            return_value=mock_result,
        )

        result = await connected_transport._read_registers(0, 3, 1)
        assert result == [100, 200, 300]

    @pytest.mark.asyncio
    async def test_read_registers_error_logs_debug(
        self,
        connected_transport: BatteryModbusTransport,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A Modbus error response is DEBUG-visible while retaining drop semantics."""
        mock_result = MagicMock()
        mock_result.isError.return_value = True
        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            return_value=mock_result,
        )

        with caplog.at_level(logging.DEBUG):
            result = await connected_transport._read_registers(0, 3, 1)

        assert result is None
        assert any(
            "Modbus error response: unit=1 start=0 count=3" in record.getMessage()
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_read_registers_exception(
        self, connected_transport: BatteryModbusTransport
    ) -> None:
        """Exception during read returns None."""
        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            side_effect=ConnectionError("Lost connection"),
        )

        result = await connected_transport._read_registers(0, 3, 1)
        assert result is None

    @pytest.mark.asyncio
    async def test_read_registers_short_read_returns_none(
        self, connected_transport: BatteryModbusTransport
    ) -> None:
        """A response with fewer registers than requested is rejected (#203).

        pymodbus decodes from the response's own byte_count without
        checking it against the requested count, so a truncated frame
        returns a short list without error.  The transport must treat
        that as a failed read, never as data.
        """
        mock_result = MagicMock()
        mock_result.isError.return_value = False
        mock_result.registers = [100] * 20  # 20 of 42 requested

        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            return_value=mock_result,
        )

        result = await connected_transport._read_registers(0, 42, 2)
        assert result is None


class TestBatteryModbusTransportShortRead:
    """End-to-end tests for short-read rejection on unit reads."""

    @pytest.mark.asyncio
    async def test_read_unit_short_runtime_block_returns_none(
        self, connected_transport: BatteryModbusTransport
    ) -> None:
        """A truncated runtime block fails the whole unit read.

        Without the short-read guard the 20-register fragment would be
        decoded as a complete 42-register block, producing a BatteryData
        with silently wrong values.
        """
        short_regs = _make_slave_regs()[:20]  # truncated mid-block
        mock_result = MagicMock()
        mock_result.isError.return_value = False
        mock_result.registers = short_regs

        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            return_value=mock_result,
        )

        data = await connected_transport.read_unit(2)
        assert data is None

    @pytest.mark.asyncio
    async def test_read_unit_short_extra_block_skips_block(
        self, connected_transport: BatteryModbusTransport
    ) -> None:
        """A truncated extra block is dropped whole, never partially decoded.

        Without the guard, a short master cell-voltage read (8 of 16
        registers) would populate half the cells with real-looking
        values and leave the rest at zero — min/max cell voltage would
        then be computed over the fragment.

        The block being dropped does not make the cells absent:
        ``BatteryData`` has no nullable cell fields, so cell_count (reg
        41, from the runtime block) still yields sixteen 0.000 V cells
        and, with the dedicated max/min registers 37/38 unset, a 0 V
        min/max fallback.  That is the point of the guard — it trades a
        plausible wrong min/max computed over the surviving fragment for
        an implausible 0.0, and implausible-wrong is far easier to spot.

        ``test_dropped_cell_block_uses_absent_voltage_sentinel`` also pins
        that the master pack voltage follows the same detectable sentinel
        policy instead of falling back to the bank minimum.
        """
        master_regs = _make_master_regs()
        short_cell_regs = [3310] * 8  # 8 of 16 requested

        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            side_effect=[
                _mock_result(master_regs),  # runtime block, full
                _mock_result(short_cell_regs),  # cell block 113-128, short
            ],
        )

        data = await connected_transport.read_unit(1)
        assert data is not None
        # Cell block dropped: no partial cell voltages leak into min/max
        assert data.max_cell_voltage == 0.0
        assert data.min_cell_voltage == 0.0
        # ...and the dropped block reads out as zeroed cells, not as absence.
        assert data.cell_voltages == [0.0] * 16

    @pytest.mark.asyncio
    async def test_read_unit_recovers_after_short_read(
        self, connected_transport: BatteryModbusTransport
    ) -> None:
        """A short read is transient: the next full read succeeds normally."""
        full_regs = _make_slave_regs()
        short_result = MagicMock()
        short_result.isError.return_value = False
        short_result.registers = full_regs[:20]

        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            side_effect=[
                short_result,  # first runtime read: truncated
                _mock_result(full_regs),  # second runtime read: full
                _mock_result([0] * 23),  # slave info block 105-127
            ],
        )

        assert await connected_transport.read_unit(2) is None
        data = await connected_transport.read_unit(2)
        assert data is not None
        assert data.voltage == pytest.approx(52.94)

    @pytest.mark.asyncio
    async def test_short_read_does_not_poison_protocol_cache(
        self, connected_transport: BatteryModbusTransport
    ) -> None:
        """A truncated read never reaches protocol detection.

        ``detect_protocol`` calls a unit a master when at most 2 of
        registers 0-18 are non-zero, and ``_get_protocol`` caches the
        verdict permanently.  A slave truncated to its first 2 registers
        therefore looks exactly like a master, and every later read of
        that unit would decode against the wrong register map for the
        life of the transport.  The guard returns before detection runs.
        """
        full_regs = _make_slave_regs()
        truncated = MagicMock()
        truncated.isError.return_value = False
        truncated.registers = full_regs[:2]  # 2 of 42 -> would detect as master

        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            side_effect=[
                truncated,
                _mock_result(full_regs),
                _mock_result([0] * 23),  # slave info block 105-127
            ],
        )

        assert await connected_transport.read_unit(2) is None
        assert connected_transport._detected_protocols == {}

        # The next clean read detects the unit correctly.
        data = await connected_transport.read_unit(2)
        assert data is not None
        assert connected_transport._detected_protocols[2].name == "eg4_slave"

    @pytest.mark.asyncio
    async def test_slave_accepts_clamped_runtime_read(
        self, connected_transport: BatteryModbusTransport
    ) -> None:
        """A BMS that clamps the read to its own map still decodes.

        The 42-register runtime read is sized for the master map; the
        slave map ends at reg 38.  A BMS that range-clamps a read past
        its last implemented register instead of raising ILLEGAL DATA
        ADDRESS returns 39 registers — everything the slave decodes.
        Rejecting that would delete a working battery every cycle.
        """
        clamped = MagicMock()
        clamped.isError.return_value = False
        clamped.registers = _make_slave_regs()[:39]  # 39 of 42, slave map complete

        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            side_effect=[
                clamped,
                _mock_result([0] * 23),  # slave info block 105-127
            ],
        )

        data = await connected_transport.read_unit(2)
        assert data is not None
        assert data.voltage == pytest.approx(52.94)
        assert data.soc == 80
        assert data.cell_count == 16

    @pytest.mark.asyncio
    async def test_slave_rejects_read_one_short_of_its_map(
        self, connected_transport: BatteryModbusTransport
    ) -> None:
        """38 registers is one short of the slave map and must be rejected.

        39 is accepted as a legitimately clamped read; 38 has genuinely lost
        data (balance_bitmap, reg 38).  Only the accept side of that boundary
        was covered.

        This pins the end-to-end outcome, not the mechanism: rejection is
        defence in depth.  Lowering _MIN_INITIAL_REGISTERS to 38 does NOT
        make this test pass -- the per-protocol recheck against the slave's
        own requirement of 39 still rejects it (only the drift test in
        TestInitialBlockRequirement catches the lowered floor itself).  That
        redundancy is the point: neither guard alone is load-bearing here.
        """
        truncated = MagicMock()
        truncated.isError.return_value = False
        truncated.registers = _make_slave_regs()[:38]  # slave map needs 39

        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            return_value=truncated,
        )

        assert await connected_transport.read_unit(2) is None

    @pytest.mark.asyncio
    async def test_master_rejects_runtime_read_short_of_its_map(
        self, connected_transport: BatteryModbusTransport
    ) -> None:
        """The relaxed floor does not let a truncated master through.

        39 registers satisfy the slave map but cut the master's map off
        at reg 38, dropping num_cells (41) and the min/max cell indices
        (39/40).  Detection still runs on complete data, so the unit is
        correctly identified and then rejected for the cycle.
        """
        truncated = MagicMock()
        truncated.isError.return_value = False
        truncated.registers = _make_master_regs()[:39]  # master needs all 42

        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            return_value=truncated,
        )

        assert await connected_transport.read_unit(1) is None
        assert connected_transport._detected_protocols[1].name == "eg4_master"

    @pytest.mark.asyncio
    async def test_dropped_cell_block_uses_absent_voltage_sentinel(self) -> None:
        """A dropped master cell block yields 0.0 instead of bank-minimum reg 22.

        Master pack voltage is derivable only from a complete, usable cell
        set. A short block is dropped whole and decoded as sixteen zero cells,
        so 0.0 is the explicit absent sentinel. Returning reg 22 would attach
        a plausible bank aggregate to the master and hide the failed block.
        """

        async def read(cell_regs: list[int]) -> BatteryData:
            transport = BatteryModbusTransport(host="10.100.3.27", unit_ids=[1, 2])
            transport._client = AsyncMock()
            transport._client.close = MagicMock()
            transport._connected = True
            transport._client.read_holding_registers = AsyncMock(
                side_effect=[
                    _mock_result(_make_master_regs()),  # unit 1 runtime
                    _mock_result(cell_regs),  # unit 1 cells (113-128)
                    _mock_result(_make_slave_regs()),  # unit 2 runtime
                    _mock_result([0] * 23),  # unit 2 info block
                ],
            )
            return (await transport.read_all())[0]

        # Full block: master voltage is the sum of its own 16 cells.
        assert (await read([3310] * 16)).voltage == pytest.approx(52.96)

        # Short block: no complete master cell set, so voltage is absent.
        assert (await read([3310] * 8)).voltage == 0.0


class TestBatteryModbusTransportHealth:
    """Tests for per-unit degradation and reconnect state."""

    @pytest.mark.asyncio
    async def test_repeated_unit_failures_warn_once(
        self,
        connected_transport: BatteryModbusTransport,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A persistently failing extra block warns only on degradation transition."""
        connected_transport._client.read_holding_registers = AsyncMock(
            side_effect=[
                _mock_result(_make_slave_regs()),
                _mock_error(),
                _mock_result(_make_slave_regs()),
                _mock_error(),
            ],
        )

        with caplog.at_level(logging.WARNING):
            assert await connected_transport.read_unit(2) is not None
            assert await connected_transport.read_unit(2) is not None

        warnings = [
            record
            for record in caplog.records
            if record.levelno == logging.WARNING
            and "Battery unit 2 read degraded" in record.getMessage()
        ]
        assert len(warnings) == 1
        assert "start=105 expected=23 got=0" in warnings[0].getMessage()
        assert connected_transport._consecutive_errors == 1

    @pytest.mark.asyncio
    async def test_clean_unit_read_recovers_and_rearms_warning(
        self,
        connected_transport: BatteryModbusTransport,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Only a wholly clean unit read logs recovery and permits a later warning."""
        connected_transport._client.read_holding_registers = AsyncMock(
            side_effect=[
                _mock_result(_make_slave_regs()),
                _mock_error(),
                _mock_result(_make_slave_regs()),
                _mock_result([0] * 23),
                _mock_result(_make_slave_regs()),
                _mock_error(),
            ],
        )

        with caplog.at_level(logging.INFO):
            assert await connected_transport.read_unit(2) is not None
            assert await connected_transport.read_unit(2) is not None
            assert await connected_transport.read_unit(2) is not None

        messages = [record.getMessage() for record in caplog.records]
        assert sum("Battery unit 2 read degraded" in message for message in messages) == 2
        assert sum("Battery unit 2 read recovered" in message for message in messages) == 1
        assert connected_transport._consecutive_errors == 1
        assert connected_transport._degraded_units == {2}

    @pytest.mark.asyncio
    async def test_successful_reconnect_completes_without_deadlock_and_resets_counter(
        self, connected_transport: BatteryModbusTransport
    ) -> None:
        """Locked reconnect completes and a connected client resets the gate (#248)."""
        connected_transport._client.read_holding_registers = AsyncMock(
            side_effect=[
                _mock_error(),
                _mock_error(),
                _mock_error(),
                _mock_result(_make_slave_regs()),
                _mock_result([0] * 23),
            ],
        )

        for _ in range(connected_transport._max_consecutive_errors):
            assert await connected_transport.read_unit(2) is None

        assert (
            connected_transport._consecutive_errors == connected_transport._max_consecutive_errors
        )

        async def disconnect_side_effect() -> None:
            assert connected_transport._operation_lock.locked()
            connected_transport._connected = False

        async def connect_side_effect() -> None:
            assert connected_transport._operation_lock.locked()
            connected_transport._connected = True
            assert connected_transport._client is not None
            connected_transport._client.connected = True

        with (
            patch.object(
                connected_transport,
                "_disconnect_locked",
                new=AsyncMock(side_effect=disconnect_side_effect),
            ) as disconnect,
            patch.object(
                connected_transport,
                "_connect_locked",
                new=AsyncMock(side_effect=connect_side_effect),
            ) as connect,
        ):
            data = await asyncio.wait_for(connected_transport.read_unit(2), timeout=1.0)

        assert data is not None
        disconnect.assert_awaited_once()
        connect.assert_awaited_once()
        assert connected_transport._consecutive_errors == 0

    @pytest.mark.asyncio
    async def test_reconnect_returning_false_does_not_reset_counter(
        self, connected_transport: BatteryModbusTransport
    ) -> None:
        """pymodbus returns False on normal network failure, which is not recovery."""
        connected_transport._consecutive_errors = connected_transport._max_consecutive_errors
        connected_transport._connected = False

        with (
            patch.object(connected_transport, "_disconnect_locked", new_callable=AsyncMock),
            patch.object(
                connected_transport,
                "_connect_locked",
                new=AsyncMock(return_value=False),
            ) as connect,
            patch("pylxpweb.transports.battery_modbus.time.monotonic", return_value=1.0),
        ):
            await connected_transport._reconnect()

        connect.assert_awaited_once()
        assert (
            connected_transport._consecutive_errors == connected_transport._max_consecutive_errors
        )

    @pytest.mark.asyncio
    async def test_reconnect_exception_does_not_escape_read_all(
        self, connected_transport: BatteryModbusTransport
    ) -> None:
        """A raising connect cannot crash a poll or reset the failed gate."""
        connected_transport.unit_ids = [2]
        connected_transport._consecutive_errors = connected_transport._max_consecutive_errors
        connected_transport._client.read_holding_registers = AsyncMock(return_value=_mock_error())

        with (
            patch.object(connected_transport, "_disconnect_locked", new_callable=AsyncMock),
            patch.object(
                connected_transport,
                "_connect_locked",
                new=AsyncMock(side_effect=OSError("bridge down")),
            ),
            patch("pylxpweb.transports.battery_modbus.time.monotonic", return_value=1.0),
        ):
            results = await connected_transport.read_all()

        assert results == []
        assert (
            connected_transport._consecutive_errors >= connected_transport._max_consecutive_errors
        )

    @pytest.mark.asyncio
    async def test_reconnect_cooldown_and_warning_dedup_start_at_small_monotonic(
        self,
        connected_transport: BatteryModbusTransport,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A small monotonic value permits attempt one, then cooldown/dedup apply."""
        assert connected_transport._reconnect_retry_after is None
        connected_transport._consecutive_errors = connected_transport._max_consecutive_errors
        connected_transport._connected = False

        with (
            caplog.at_level(logging.DEBUG),
            patch.object(
                connected_transport, "_disconnect_locked", new_callable=AsyncMock
            ) as disconnect,
            patch.object(
                connected_transport,
                "_connect_locked",
                new=AsyncMock(return_value=False),
            ) as connect,
            patch(
                "pylxpweb.transports.battery_modbus.time.monotonic",
                side_effect=[1.0, 2.0, 32.0],
            ),
        ):
            await connected_transport._reconnect()
            await connected_transport._reconnect()
            await connected_transport._reconnect()

        assert disconnect.await_count == 2
        assert connect.await_count == 2
        warnings = [
            record
            for record in caplog.records
            if record.levelno == logging.WARNING and "Reconnecting battery" in record.getMessage()
        ]
        assert len(warnings) == 1
        assert any(
            record.levelno == logging.DEBUG and "Reconnecting battery" in record.getMessage()
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_successful_read_recovers_reconnect_warning_episode(
        self,
        connected_transport: BatteryModbusTransport,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A real response clears warning dedup/cooldown and logs one recovery."""
        connected_transport._reconnect_warned = True
        connected_transport._reconnect_retry_after = 60.0
        connected_transport._client.read_holding_registers = AsyncMock(
            side_effect=[
                _mock_result(_make_slave_regs()),
                _mock_result([0] * 23),
            ]
        )

        with caplog.at_level(logging.INFO):
            assert await connected_transport.read_unit(2) is not None

        assert connected_transport._reconnect_warned is False
        assert connected_transport._reconnect_retry_after is None
        recoveries = [
            r for r in caplog.records if "recovered after a successful read" in r.getMessage()
        ]
        assert len(recoveries) == 1

    @pytest.mark.asyncio
    async def test_unit_read_holds_operation_lock_across_gate_and_reads(
        self, connected_transport: BatteryModbusTransport
    ) -> None:
        """The reconnect gate and register reads share one client-operation lock."""
        connected_transport._consecutive_errors = connected_transport._max_consecutive_errors

        async def reconnect() -> None:
            assert connected_transport._operation_lock.locked()
            connected_transport._consecutive_errors = 0

        async def read_registers(*_args: object, **_kwargs: object) -> None:
            assert connected_transport._operation_lock.locked()
            return None

        with (
            patch.object(connected_transport, "_reconnect", side_effect=reconnect),
            patch.object(connected_transport, "_read_registers", side_effect=read_registers),
        ):
            assert await connected_transport.read_unit(2) is None


class TestInitialBlockRequirement:
    """The initial runtime read must cover every protocol's runtime block."""

    def test_requirement_matches_each_protocol_map(self) -> None:
        """Requirements are derived from the maps, not hardcoded guesses."""
        assert _initial_block_requirement(EG4SlaveProtocol()) == 39  # regs 0-38
        assert _initial_block_requirement(EG4MasterProtocol()) == 42  # regs 0-41

    def test_union_read_covers_all_protocols(self) -> None:
        """_INITIAL_BLOCK_COUNT is the union; the floor is the smallest map."""
        requirements = [_initial_block_requirement(cls()) for cls in _PROTOCOL_MAP.values()]
        assert max(requirements) == _INITIAL_BLOCK_COUNT
        assert min(requirements) == _MIN_INITIAL_REGISTERS
        # Detection reads registers 0-18; the floor must never dip below it.
        # This is the load-bearing guarantee: it is the outer max() in
        # _MIN_INITIAL_REGISTERS that enforces it, not the happenstance that
        # today's smallest map (39) already exceeds 19.  A protocol with a
        # short map added later would drag min() down, and detection would
        # still be safe.
        assert _MIN_INITIAL_REGISTERS >= _DETECTION_REGISTER_COUNT

    def test_detection_floor_tracks_the_detection_range(self) -> None:
        """The transport's copy of the detection range must not drift.

        battery_modbus mirrors detection's range as its own constant.  If
        detection widens its range and this copy is not updated, the floor
        silently stops guaranteeing detection sees complete data -- the exact
        safety property the relaxed floor rests on.
        """
        assert _DETECTION_REGISTER_COUNT == _DETECTION_RANGE_END


def _make_slave_regs(soc: int = 80, remaining: int = 224) -> list[int]:
    """Build a minimal slave register set (42 regs).

    Must have 3+ non-zero registers in range 0-18 to pass auto-detection
    as a slave (detection threshold is >2 non-zero in regs 0-18).
    """
    regs = [0] * 42
    regs[0] = 5294  # voltage 52.94V
    regs[1] = 100  # current 1.00A (non-zero for detection)
    # Cell voltages (regs 2-17) — need at least one for detection
    regs[2] = 3310  # cell 1 voltage
    regs[18] = 18  # pcb temp
    regs[20] = 19  # max temp
    regs[21] = remaining  # remaining capacity Ah
    regs[24] = soc  # SOC
    regs[33] = 0x1312  # packed temps: 19, 18
    regs[34] = 0x1211  # packed temps: 18, 17
    regs[35] = 0x1312  # packed temps: 19, 18
    regs[36] = 16  # num cells
    regs[37] = 2800  # designed capacity 280 Ah
    return regs


def _make_master_regs(soc: int = 79, reg26: int = 464, reg27: int = 18464) -> list[int]:
    """Build a minimal master register set (42 regs, zeros at 0-18)."""
    regs = [0] * 42
    regs[21] = soc  # aggregate SOC
    regs[22] = 5294  # voltage 52.94V
    regs[24] = 19  # aggregate max temp
    regs[26] = reg26  # total remaining (overflowed)
    regs[27] = reg27  # total full (overflowed)
    regs[33] = 5600  # designed capacity 280 Ah (/20)
    regs[41] = 16  # num cells
    return regs


def _mock_result(regs: list[int]) -> MagicMock:
    """Build a mock Modbus read result."""
    m = MagicMock()
    m.isError.return_value = False
    m.registers = regs
    return m


def _mock_error() -> MagicMock:
    m = MagicMock()
    m.isError.return_value = True
    return m


class TestReadAllWithSlaves:
    """Tests for read_all() master SOC back-calculation using slave context."""

    @pytest.mark.asyncio
    async def test_full_slave_context_redecodes_master(self) -> None:
        """A complete slave set back-calculates master remaining capacity."""
        transport = BatteryModbusTransport(host="10.100.3.27", unit_ids=[1, 2, 3])
        transport._client = AsyncMock()
        transport._client.close = MagicMock()
        transport._connected = True

        master_regs = _make_master_regs(soc=79, reg26=464, reg27=18464)
        slave2_regs = _make_slave_regs(soc=80, remaining=224)
        slave3_regs = _make_slave_regs(soc=80, remaining=223)
        cell_regs = [3310] * 16

        transport._client.read_holding_registers = AsyncMock(
            side_effect=[
                _mock_result(master_regs),  # unit 1 runtime
                _mock_result(cell_regs),  # unit 1 cells (113-128)
                _mock_result(slave2_regs),  # unit 2 runtime
                _mock_result([0] * 23),  # unit 2 info block (105-127)
                _mock_result(slave3_regs),  # unit 3 runtime
                _mock_result([0] * 23),  # unit 3 info block (105-127)
            ],
        )

        results = await transport.read_all()
        assert len(results) == 3

        master = results[0]
        assert master.battery_index == 0
        # Back-calculated: 660 - 224 - 223 = 213 Ah → 213/280 = 76%
        assert master.soc == 76
        assert master.current_capacity == pytest.approx(213.0)

        # Slaves unchanged
        assert results[1].soc == 80
        assert results[2].soc == 80

    @pytest.mark.asyncio
    async def test_single_battery_keeps_aggregate_soc_and_derives_voltage(self) -> None:
        """A genuine one-battery bank needs no capacity back-calculation."""
        transport = BatteryModbusTransport(host="10.100.3.27", unit_ids=[1])
        transport._client = AsyncMock()
        transport._client.close = MagicMock()
        transport._client.connected = True
        transport._connected = True

        master_regs = _make_master_regs(soc=79, reg26=22400, reg27=28000)
        cell_regs = [3310] * 16

        transport._client.read_holding_registers = AsyncMock(
            side_effect=[
                _mock_result(master_regs),
                _mock_result(cell_regs),
            ],
        )

        results = await transport.read_all()
        assert len(results) == 1
        assert results[0].voltage == pytest.approx(52.96)
        assert results[0].soc == 79
        assert results[0].current_capacity is None

    @pytest.mark.asyncio
    async def test_failed_only_slave_keeps_master_aggregate_soc(self) -> None:
        """An empty slave result is failed topology, not proof of one battery (#249)."""
        transport = BatteryModbusTransport(host="10.100.3.27", unit_ids=[1, 2])
        transport._client = AsyncMock()
        transport._client.close = MagicMock()
        transport._client.connected = True
        transport._connected = True

        transport._client.read_holding_registers = AsyncMock(
            side_effect=[
                _mock_result(_make_master_regs(soc=79, reg26=22400, reg27=28000)),
                _mock_result([3310] * 16),
                _mock_error(),
            ]
        )

        results = await transport.read_all()

        assert len(results) == 1
        assert results[0].voltage == pytest.approx(52.96)
        assert results[0].soc == 79
        assert results[0].current_capacity is None

    @pytest.mark.asyncio
    async def test_partial_slave_context_keeps_master_aggregate_soc(self) -> None:
        """One missing battery from a three-unit bank makes subtraction unsafe (#249)."""
        transport = BatteryModbusTransport(host="10.100.3.27", unit_ids=[1, 2, 3])
        transport._client = AsyncMock()
        transport._client.close = MagicMock()
        transport._client.connected = True
        transport._connected = True

        transport._client.read_holding_registers = AsyncMock(
            side_effect=[
                _mock_result(_make_master_regs(soc=79, reg26=464, reg27=18464)),
                _mock_result([3310] * 16),
                _mock_result(_make_slave_regs(soc=80, remaining=224)),
                _mock_result([0] * 23),
                _mock_error(),
            ]
        )

        results = await transport.read_all()

        assert len(results) == 2
        assert results[0].soc == 79
        assert results[0].current_capacity is None

    @pytest.mark.asyncio
    async def test_auto_scan_remembers_a_missing_slave(self) -> None:
        """A shrunken later scan cannot validate its own partial topology (#249)."""
        transport = BatteryModbusTransport(host="10.100.3.27", max_units=3)
        transport._client = AsyncMock()
        transport._client.close = MagicMock()
        transport._client.connected = True
        transport._connected = True
        transport._client.read_holding_registers = AsyncMock(
            side_effect=[
                _mock_result([100]),
                _mock_result([100]),
                _mock_result([100]),
                _mock_result(_make_master_regs()),
                _mock_result([3310] * 16),
                _mock_result(_make_slave_regs(remaining=224)),
                _mock_result([0] * 23),
                _mock_result(_make_slave_regs(remaining=223)),
                _mock_result([0] * 23),
                _mock_result([100]),
                _mock_result([100]),
                _mock_error(),
                _mock_result(_make_master_regs()),
                _mock_result([3310] * 16),
                _mock_result(_make_slave_regs(remaining=224)),
                _mock_result([0] * 23),
            ]
        )

        with patch("pylxpweb.transports.battery_modbus.asyncio.sleep", new_callable=AsyncMock):
            with patch("pylxpweb.transports.battery_modbus.time.monotonic", return_value=1.0):
                complete_results = await transport.read_all()
            with patch("pylxpweb.transports.battery_modbus.time.monotonic", return_value=2.0):
                partial_results = await transport.read_all()

        assert complete_results[0].soc == 76
        assert complete_results[0].current_capacity == pytest.approx(213.0)
        assert len(partial_results) == 2
        assert partial_results[0].soc == 79
        assert partial_results[0].current_capacity is None

    @pytest.mark.asyncio
    async def test_auto_scan_two_battery_bank_redecodes_master(self) -> None:
        """Remembered topology permits a complete genuine two-unit bank (#249)."""
        transport = BatteryModbusTransport(host="10.100.3.27", max_units=2)
        transport._client = AsyncMock()
        transport._client.close = MagicMock()
        transport._client.connected = True
        transport._connected = True
        transport._client.read_holding_registers = AsyncMock(
            side_effect=[
                _mock_result([100]),
                _mock_result([100]),
                _mock_result(_make_master_regs(reg26=43700, reg27=56000)),
                _mock_result([3310] * 16),
                _mock_result(_make_slave_regs(remaining=224)),
                _mock_result([0] * 23),
            ]
        )

        with (
            patch("pylxpweb.transports.battery_modbus.asyncio.sleep", new_callable=AsyncMock),
            patch("pylxpweb.transports.battery_modbus.time.monotonic", return_value=1.0),
        ):
            results = await transport.read_all()

        assert len(results) == 2
        assert results[0].soc == 76
        assert results[0].current_capacity == pytest.approx(213.0)

    @pytest.mark.asyncio
    async def test_never_seen_explicit_slave_remains_required(self) -> None:
        """A configured slave is required even before its first response (#249)."""
        transport = BatteryModbusTransport(host="10.100.3.27", unit_ids=[1, 2, 3])
        transport._client = AsyncMock()
        transport._client.close = MagicMock()
        transport._client.connected = True
        transport._connected = True
        transport._client.read_holding_registers = AsyncMock(
            side_effect=[
                _mock_result(_make_master_regs()),
                _mock_result([3310] * 16),
                _mock_result(_make_slave_regs(remaining=224)),
                _mock_result([0] * 23),
                _mock_error(),
            ]
        )

        with (
            patch("pylxpweb.transports.battery_modbus.asyncio.sleep", new_callable=AsyncMock),
            patch("pylxpweb.transports.battery_modbus.time.monotonic", return_value=1.0),
        ):
            results = await transport.read_all()

        assert len(results) == 2
        assert results[0].soc == 79
        assert results[0].current_capacity is None
        assert transport._unit_last_seen == {1: 1.0, 2: 1.0, 3: 1.0}

    @pytest.mark.asyncio
    async def test_stale_topology_evicts_after_retention_from_small_monotonic(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A removed unit eventually stops pinning aggregate SOC on low uptime (#249)."""
        transport = BatteryModbusTransport(host="10.100.3.27", max_units=3)
        transport._client = AsyncMock()
        transport._client.close = MagicMock()
        transport._client.connected = True
        transport._connected = True
        transport._client.read_holding_registers = AsyncMock(
            side_effect=[
                _mock_result([100]),
                _mock_result([100]),
                _mock_result([100]),
                _mock_result(_make_master_regs()),
                _mock_result([3310] * 16),
                _mock_result(_make_slave_regs(remaining=224)),
                _mock_result([0] * 23),
                _mock_result(_make_slave_regs(remaining=223)),
                _mock_result([0] * 23),
                _mock_result([100]),
                _mock_result([100]),
                _mock_error(),
                _mock_result(_make_master_regs(reg26=43700, reg27=56000)),
                _mock_result([3310] * 16),
                _mock_result(_make_slave_regs(remaining=224)),
                _mock_result([0] * 23),
            ]
        )

        with (
            caplog.at_level(logging.INFO),
            patch("pylxpweb.transports.battery_modbus.asyncio.sleep", new_callable=AsyncMock),
        ):
            with patch("pylxpweb.transports.battery_modbus.time.monotonic", return_value=1.0):
                await transport.read_all()
            with patch(
                "pylxpweb.transports.battery_modbus.time.monotonic",
                return_value=_UNIT_TOPOLOGY_RETENTION + 2.0,
            ):
                results = await transport.read_all()

        assert len(results) == 2
        assert results[0].soc == 76
        assert results[0].current_capacity == pytest.approx(213.0)
        assert set(transport._unit_last_seen) == {1, 2}
        assert any(
            record.levelno == logging.INFO
            and "unit 3" in record.getMessage()
            and "topology" in record.getMessage()
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_evicted_declared_unit_does_not_re_arm_the_gate(self) -> None:
        """Convergence must hold, not flap once per retention window (#249).

        With explicit unit_ids, every poll re-offers the configured list to
        topology memory.  Seeding on that offer alone would re-admit a unit the
        previous cycle had just evicted, so an removed-but-still-configured
        battery would hand back one cycle of individual SOC/capacity every six
        hours and revert in between -- a periodic step in history rather than a
        convergence.  Only a genuine response re-admits an evicted unit, so the
        cycle after eviction must look exactly like the eviction cycle.
        """
        transport = BatteryModbusTransport(host="10.100.3.27", unit_ids=[1, 2, 3])
        transport._client = AsyncMock()
        transport._client.close = MagicMock()
        transport._client.connected = True
        transport._connected = True

        def one_poll() -> list[MagicMock]:
            return [
                _mock_result(_make_master_regs(soc=79, reg26=43700, reg27=56000)),
                _mock_result([3310] * 16),
                _mock_result(_make_slave_regs(soc=80, remaining=224)),
                _mock_result([0] * 23),
                _mock_error(),  # unit 3 stays dead throughout
            ]

        with patch("pylxpweb.transports.battery_modbus.asyncio.sleep", new_callable=AsyncMock):
            with patch("pylxpweb.transports.battery_modbus.time.monotonic", return_value=1.0):
                transport._client.read_holding_registers = AsyncMock(side_effect=one_poll())
                first = await transport.read_all()
            assert first[0].current_capacity is None  # aggregate held

            with patch(
                "pylxpweb.transports.battery_modbus.time.monotonic",
                return_value=_UNIT_TOPOLOGY_RETENTION * 3,
            ):
                transport._client.read_holding_registers = AsyncMock(side_effect=one_poll())
                converged = await transport.read_all()
            assert converged[0].current_capacity == pytest.approx(213.0)

            # The next poll re-offers unit 3; it must not be re-seeded.
            with patch(
                "pylxpweb.transports.battery_modbus.time.monotonic",
                return_value=_UNIT_TOPOLOGY_RETENTION * 3 + 60.0,
            ):
                transport._client.read_holding_registers = AsyncMock(side_effect=one_poll())
                after = await transport.read_all()

        assert after[0].current_capacity == pytest.approx(213.0)
        assert after[0].soc == converged[0].soc
        assert set(transport._unit_last_seen) == {1, 2}
        assert transport._evicted_units == {3}

    @pytest.mark.asyncio
    async def test_auto_scan_cold_start_boundary_is_pinned_as_is(self) -> None:
        """Auto-scan's first scan cannot protect against a unit never seen (#249).

        Topology memory is built from observation, so a fresh transport with
        unit_ids=None whose very first scan misses a unit has nothing to compare
        against: the remembered set is already short and the re-decode gate
        passes on incomplete topology.  This is the original defect's shape in a
        narrow, self-healing window, and it is pinned deliberately rather than
        fixed -- closing it would require a declared expected unit count, which
        is exactly the configuration auto-scan exists to avoid.  The second half
        of this test is the self-heal: once the missing unit answers even once,
        it is remembered and its later silence blocks the gate.
        """
        transport = BatteryModbusTransport(host="10.100.3.27", max_units=3)
        transport._client = AsyncMock()
        transport._client.close = MagicMock()
        transport._client.connected = True
        transport._connected = True

        with (
            patch("pylxpweb.transports.battery_modbus.asyncio.sleep", new_callable=AsyncMock),
            patch("pylxpweb.transports.battery_modbus.time.monotonic", return_value=1.0),
        ):
            transport._client.read_holding_registers = AsyncMock(
                side_effect=[
                    _mock_result([100]),  # scan: unit 1 answers
                    _mock_result([100]),  # scan: unit 2 answers
                    _mock_error(),  # scan: unit 3 silent on the very first scan
                    _mock_result(_make_master_regs(soc=79, reg26=43700, reg27=56000)),
                    _mock_result([3310] * 16),
                    _mock_result(_make_slave_regs(soc=80, remaining=224)),
                    _mock_result([0] * 23),
                ]
            )
            cold = await transport.read_all()

        # Boundary: the gate passed, because unit 3 was never observed.
        assert cold[0].current_capacity == pytest.approx(213.0)
        assert set(transport._unit_last_seen) == {1, 2}

        # Self-heal: unit 3 answers once, so it joins remembered topology...
        with (
            patch("pylxpweb.transports.battery_modbus.asyncio.sleep", new_callable=AsyncMock),
            patch("pylxpweb.transports.battery_modbus.time.monotonic", return_value=2.0),
        ):
            transport._client.read_holding_registers = AsyncMock(
                side_effect=[
                    _mock_result([100]),
                    _mock_result([100]),
                    _mock_result([100]),  # unit 3 present this time
                    _mock_result(_make_master_regs(soc=79, reg26=43700, reg27=56000)),
                    _mock_result([3310] * 16),
                    _mock_result(_make_slave_regs(soc=80, remaining=224)),
                    _mock_result([0] * 23),
                    _mock_result(_make_slave_regs(soc=80, remaining=223)),
                    _mock_result([0] * 23),
                ]
            )
            await transport.read_all()
        assert set(transport._unit_last_seen) == {1, 2, 3}

        # ...and from now on its silence keeps the master on the aggregate.
        with (
            patch("pylxpweb.transports.battery_modbus.asyncio.sleep", new_callable=AsyncMock),
            patch("pylxpweb.transports.battery_modbus.time.monotonic", return_value=3.0),
        ):
            transport._client.read_holding_registers = AsyncMock(
                side_effect=[
                    _mock_result([100]),
                    _mock_result([100]),
                    _mock_error(),  # unit 3 silent again, but now remembered
                    _mock_result(_make_master_regs(soc=79, reg26=43700, reg27=56000)),
                    _mock_result([3310] * 16),
                    _mock_result(_make_slave_regs(soc=80, remaining=224)),
                    _mock_result([0] * 23),
                ]
            )
            healed = await transport.read_all()

        assert healed[0].current_capacity is None
        assert healed[0].soc == 79

    @pytest.mark.asyncio
    async def test_returning_unit_is_readmitted_after_eviction(self) -> None:
        """A battery that comes back must rejoin topology and re-gate the master.

        Eviction is not a permanent blacklist: a genuine response re-admits the
        unit, which immediately makes the re-decode gate demand it again.
        """
        transport = BatteryModbusTransport(host="10.100.3.27", unit_ids=[1, 2, 3])
        transport._client = AsyncMock()
        transport._client.close = MagicMock()
        transport._client.connected = True
        transport._connected = True
        transport._evicted_units = {3}

        with (
            patch("pylxpweb.transports.battery_modbus.asyncio.sleep", new_callable=AsyncMock),
            patch("pylxpweb.transports.battery_modbus.time.monotonic", return_value=10.0),
        ):
            transport._client.read_holding_registers = AsyncMock(
                side_effect=[
                    _mock_result(_make_master_regs(soc=79, reg26=43700, reg27=56000)),
                    _mock_result([3310] * 16),
                    _mock_result(_make_slave_regs(soc=80, remaining=224)),
                    _mock_result([0] * 23),
                    _mock_result(_make_slave_regs(soc=80, remaining=223)),  # unit 3 returns
                    _mock_result([0] * 23),
                ]
            )
            results = await transport.read_all()

        assert len(results) == 3
        assert transport._evicted_units == set()
        assert set(transport._unit_last_seen) == {1, 2, 3}


class TestOverlayInverterBMS:
    """Tests for _overlay_inverter_bms() filling master RS485 gaps."""

    def test_overlay_fills_temperatures(self) -> None:
        """Inverter BMS temps replace master's reg-24-only values."""
        master = BatteryData(
            battery_index=0,
            voltage=52.94,
            soc=76,
            temperature=19.0,
            # RS485 sets both to aggregate MAX (reg 24)
            min_cell_temperature=19.0,
            max_cell_temperature=19.0,
        )
        bms = InverterRuntimeData(
            bms_max_cell_temperature=19.0,
            bms_min_cell_temperature=17.0,
        )

        result = BatteryModbusTransport._overlay_inverter_bms(master, bms)
        assert result.min_cell_temperature == 17.0
        assert result.max_cell_temperature == 19.0
        # Other fields preserved
        assert result.voltage == 52.94
        assert result.soc == 76

    def test_overlay_no_bms_temps_preserves_original(self) -> None:
        """When BMS has no temp data, master values are unchanged."""
        master = BatteryData(
            battery_index=0,
            min_cell_temperature=19.0,
            max_cell_temperature=19.0,
        )
        bms = InverterRuntimeData(
            bms_max_cell_temperature=None,
            bms_min_cell_temperature=None,
        )

        result = BatteryModbusTransport._overlay_inverter_bms(master, bms)
        assert result.min_cell_temperature == 19.0
        assert result.max_cell_temperature == 19.0

    def test_overlay_partial_bms_data(self) -> None:
        """Only available BMS fields are overlaid."""
        master = BatteryData(
            battery_index=0,
            min_cell_temperature=19.0,
            max_cell_temperature=19.0,
        )
        bms = InverterRuntimeData(
            bms_max_cell_temperature=None,
            bms_min_cell_temperature=16.0,
        )

        result = BatteryModbusTransport._overlay_inverter_bms(master, bms)
        assert result.min_cell_temperature == 16.0
        assert result.max_cell_temperature == 19.0  # unchanged

    @pytest.mark.asyncio
    async def test_read_all_with_bms_overlay(self) -> None:
        """End-to-end: read_all applies BMS overlay to master."""
        transport = BatteryModbusTransport(host="10.100.3.27", unit_ids=[1, 2])
        transport._client = AsyncMock()
        transport._client.close = MagicMock()
        transport._connected = True

        master_regs = _make_master_regs(soc=79, reg26=464, reg27=18464)
        slave_regs = _make_slave_regs(soc=80, remaining=447)
        cell_regs = [3310] * 16

        transport._client.read_holding_registers = AsyncMock(
            side_effect=[
                _mock_result(master_regs),
                _mock_result(cell_regs),
                _mock_result(slave_regs),
                _mock_result([0] * 23),  # slave info block
            ],
        )

        bms = InverterRuntimeData(
            bms_max_cell_temperature=19.0,
            bms_min_cell_temperature=17.0,
        )

        results = await transport.read_all(inverter_bms_data=bms)
        master = results[0]
        # BMS temps overlaid
        assert master.min_cell_temperature == 17.0
        assert master.max_cell_temperature == 19.0
        # Slave unaffected
        assert results[1].min_cell_temperature == 17.0  # from packed temps
