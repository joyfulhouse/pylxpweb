"""Tests for BatteryModbusTransport."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.transports.battery_modbus import BatteryModbusTransport
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
    async def test_master_redecoded_with_slave_context(self) -> None:
        """Master SOC is back-calculated from slave remaining capacities."""
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
    async def test_master_without_slaves_uses_aggregate(self) -> None:
        """When no slaves respond, master keeps aggregate SOC."""
        transport = BatteryModbusTransport(host="10.100.3.27", unit_ids=[1, 2])
        transport._client = AsyncMock()
        transport._client.close = MagicMock()
        transport._connected = True

        master_regs = _make_master_regs(soc=79)
        cell_regs = [3310] * 16

        transport._client.read_holding_registers = AsyncMock(
            side_effect=[
                _mock_result(master_regs),
                _mock_result(cell_regs),
                _mock_error(),  # unit 2 fails
            ],
        )

        results = await transport.read_all()
        assert len(results) == 1
        # No slaves → no re-decode → aggregate SOC
        assert results[0].soc == 79


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
