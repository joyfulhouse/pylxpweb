"""Tests for BatteryModbusTransport."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.transports.battery_modbus import BatteryModbusTransport


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

        with patch(
            "pylxpweb.transports.battery_modbus.AsyncModbusTcpClient",
            return_value=mock_client,
        ), pytest.raises(RuntimeError, match="test error"):
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
        master_regs[22] = 5294  # voltage /100 = 52.94V
        master_regs[23] = 200  # current /100 = 2.00A (aggregate)
        master_regs[24] = 35  # temperature = 35°C
        master_regs[26] = 760  # SOC /10 = 76%
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
        assert data.voltage == pytest.approx(52.94)
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
    async def test_scan_no_units_responding(self) -> None:
        """Scan returns empty list when no units respond."""
        transport = BatteryModbusTransport(
            host="10.100.3.27",
            max_units=2,
        )
        transport._client = AsyncMock()
        transport._connected = True

        err_result = MagicMock()
        err_result.isError.return_value = True

        transport._client.read_holding_registers = AsyncMock(return_value=err_result)

        result = await transport.scan_units()
        assert result == []


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
    async def test_read_registers_error(self, connected_transport: BatteryModbusTransport) -> None:
        """Error response returns None."""
        mock_result = MagicMock()
        mock_result.isError.return_value = True
        connected_transport._client.read_holding_registers = AsyncMock(  # type: ignore[union-attr]
            return_value=mock_result,
        )

        result = await connected_transport._read_registers(0, 3, 1)
        assert result is None

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
