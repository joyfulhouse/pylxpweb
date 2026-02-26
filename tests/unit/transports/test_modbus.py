"""Tests for Modbus transport implementation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.registers.battery import (
    BATTERY_BASE_ADDRESS,
    BATTERY_MAX_COUNT,
    BATTERY_REGISTER_COUNT,
)
from pylxpweb.transports.exceptions import (
    TransportConnectionError,
    TransportReadError,
    TransportWriteError,
)
from pylxpweb.transports.modbus import ModbusTransport


def _build_battery_slot_values(
    positions: list[int],
    voltage_raw: int = 5246,
) -> list[int]:
    """Build 120-register response with batteries at specified positions.

    Each slot gets: status=0xC003, voltage at offset 6, and pos encoded
    in offset 24 high byte.  Remaining registers are zero.

    Args:
        positions: List of 0-based battery positions for each of the 4 slots.
            Use -1 for an empty slot.
        voltage_raw: Raw voltage value (default 5246 → 52.46V after DIV_100).

    Returns:
        List of 120 register values (4 slots × 30 registers).
    """
    vals = [0] * (BATTERY_MAX_COUNT * BATTERY_REGISTER_COUNT)
    for slot_idx, pos in enumerate(positions):
        if pos < 0:
            continue  # empty slot
        base = slot_idx * BATTERY_REGISTER_COUNT
        vals[base] = 0xC003  # status header: connected
        vals[base + 6] = voltage_raw  # voltage
        vals[base + 8] = (100 << 8) | 95  # SOH=100, SOC=95 packed
        vals[base + 24] = pos << 8  # pos in high byte
    return vals


class TestModbusTransport:
    """Tests for ModbusTransport class."""

    def test_init_default_values(self) -> None:
        """Test Modbus transport initialization with defaults."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        assert transport.serial == "CE12345678"
        assert transport._host == "192.168.1.100"
        assert transport._port == 502
        assert transport._unit_id == 1
        assert transport._timeout == 10.0
        assert transport.is_connected is False

    def test_init_custom_values(self) -> None:
        """Test Modbus transport initialization with custom values."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
            port=8502,
            unit_id=2,
            timeout=30.0,
        )

        assert transport._port == 8502
        assert transport._unit_id == 2
        assert transport._timeout == 30.0

    def test_capabilities(self) -> None:
        """Test Modbus transport capabilities."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        caps = transport.capabilities
        assert caps.can_read_runtime is True
        assert caps.can_read_energy is True
        assert caps.can_read_battery is True
        assert caps.is_local is True
        assert caps.requires_authentication is False

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        """Test successful Modbus connection."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        # Mock the Modbus client - import is done inside connect()
        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client_class.return_value = mock_client

            await transport.connect()

            assert transport.is_connected is True
            mock_client.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self) -> None:
        """Test Modbus connection failure."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            with pytest.raises(TransportConnectionError, match="Failed to connect"):
                await transport.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        """Test Modbus disconnection."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()
            mock_client_class.return_value = mock_client

            await transport.connect()
            assert transport.is_connected is True

            await transport.disconnect()
            assert transport.is_connected is False
            mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_runtime_not_connected(self) -> None:
        """Test runtime read when not connected."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        # The ModbusTransport wraps TransportConnectionError in TransportReadError

        with pytest.raises(TransportReadError):
            await transport.read_runtime()

    @pytest.mark.asyncio
    async def test_read_runtime_success(self) -> None:
        """Test successful runtime read via Modbus.

        Uses the corrected PV_SERIES register layout:
        - PV power at regs 7-9 (16-bit)
        - Charge/discharge at regs 10-11 (16-bit)
        - Grid voltages at regs 12-14
        - Grid frequency at reg 15
        - Inverter power at reg 16
        - EPS power at reg 24
        - Load power at reg 27
        """
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()

            # Mock register read response with correct PV_SERIES layout
            mock_response = MagicMock()
            mock_response.isError.return_value = False
            # 128 registers for runtime data - using new layout
            mock_response.registers = [
                0,  # 0: Status
                5100,  # 1: PV1 voltage (×10 = 510V)
                5050,  # 2: PV2 voltage
                0,  # 3: PV3 voltage
                530,  # 4: Battery voltage (×10 = 53V)
                (100 << 8) | 85,  # 5: SOC=85 (low), SOH=100 (high)
                0,  # 6: (unused in new layout)
                1000,  # 7: PV1 power (16-bit)
                1500,  # 8: PV2 power (16-bit)
                0,  # 9: PV3 power (16-bit)
                500,  # 10: Charge power (16-bit)
                0,  # 11: Discharge power (16-bit)
                2410,  # 12: Grid voltage R (×10)
                2415,  # 13: Grid voltage S
                2420,  # 14: Grid voltage T
                5998,  # 15: Grid frequency (×100 = 59.98Hz)
                2300,  # 16: Inverter power (16-bit)
                100,  # 17: Grid power/AC charge (16-bit)
                50,  # 18: IinvRMS (×100 = 0.5A)
                990,  # 19: Power factor (×1000 = 0.99)
                2400,  # 20: EPS voltage R
                2405,  # 21: EPS voltage S
                2410,  # 22: EPS voltage T
                5999,  # 23: EPS frequency
                300,  # 24: EPS power (16-bit)
                1,  # 25: EPS status
                200,  # 26: Power to grid (16-bit)
                1500,  # 27: Load power (16-bit)
            ] + [0] * 100  # Fill remaining registers

            mock_client.read_input_registers = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await transport.connect()
            runtime = await transport.read_runtime()

            assert runtime.pv1_voltage == pytest.approx(510.0, rel=0.01)
            assert runtime.battery_soc == 85
            assert runtime.grid_frequency == pytest.approx(59.98, rel=0.01)
            assert runtime.pv1_power == 1000.0
            assert runtime.load_power == 1500.0

    @pytest.mark.asyncio
    async def test_manual_connect_disconnect(self) -> None:
        """Test manual connect and disconnect."""
        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()
            mock_client_class.return_value = mock_client

            transport = ModbusTransport(
                host="192.168.1.100",
                serial="CE12345678",
            )

            await transport.connect()
            assert transport.is_connected is True

            await transport.disconnect()
            assert transport.is_connected is False
            mock_client.close.assert_called_once()


class TestModbusRegisterReading:
    """Tests for Modbus register reading."""

    @pytest.mark.asyncio
    async def test_read_parameters(self) -> None:
        """Test reading holding registers (parameters)."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()

            # Mock holding register response
            mock_response = MagicMock()
            mock_response.isError.return_value = False
            mock_response.registers = [100, 200, 300, 400, 500]

            mock_client.read_holding_registers = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await transport.connect()
            params = await transport.read_parameters(0, 5)

            assert params[0] == 100
            assert params[1] == 200
            assert params[2] == 300
            assert params[3] == 400
            assert params[4] == 500

    @pytest.mark.asyncio
    async def test_read_parameters_chunked(self) -> None:
        """Test reading parameters in chunks (>40 registers)."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()

            # Each read returns 40 registers
            call_count = 0

            async def make_response(**kwargs: int) -> MagicMock:
                nonlocal call_count
                response = MagicMock()
                response.isError.return_value = False
                # Return different values for each chunk
                start = call_count * 40
                response.registers = list(range(start, start + 40))
                call_count += 1
                return response

            mock_client.read_holding_registers = make_response
            mock_client_class.return_value = mock_client

            await transport.connect()
            params = await transport.read_parameters(0, 80)

            # Verify we got 80 parameter values
            assert len(params) == 80

            # Check first chunk values (0-39)
            assert params[0] == 0
            assert params[39] == 39

            # Check second chunk values (40-79)
            assert params[40] == 40
            assert params[79] == 79

            # Verify call_count tracks the 2 calls
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_read_parameters_not_connected(self) -> None:
        """Test parameter read when not connected."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with pytest.raises(TransportConnectionError, match="Transport not connected"):
            await transport.read_parameters(0, 10)

    @pytest.mark.asyncio
    async def test_read_parameters_modbus_error(self) -> None:
        """Test parameter read with Modbus error."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)

            # Mock error response
            mock_response = MagicMock()
            mock_response.isError.return_value = True

            mock_client.read_holding_registers = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await transport.connect()

            with pytest.raises(TransportReadError, match="Modbus read error"):
                await transport.read_parameters(0, 10)

    @pytest.mark.asyncio
    async def test_write_parameters_success(self) -> None:
        """Test successful parameter write."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)

            # Mock successful write response
            mock_response = MagicMock()
            mock_response.isError.return_value = False

            mock_client.write_register = AsyncMock(return_value=mock_response)
            mock_client.write_registers = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await transport.connect()
            result = await transport.write_parameters({0: 100, 1: 200})

            assert result is True
            # Multiple consecutive registers use FC16 (write_registers)
            mock_client.write_registers.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_write_parameters_not_connected(self) -> None:
        """Test parameter write when not connected."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with pytest.raises(TransportConnectionError, match="Transport not connected"):
            await transport.write_parameters({0: 100})

    @pytest.mark.asyncio
    async def test_write_parameters_modbus_error(self) -> None:
        """Test parameter write with Modbus error."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)

            # Mock error response
            mock_response = MagicMock()
            mock_response.isError.return_value = True

            mock_client.write_register = AsyncMock(return_value=mock_response)
            mock_client.write_registers = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await transport.connect()

            with pytest.raises(TransportWriteError, match="Modbus write error"):
                await transport.write_parameters({0: 100})

    @pytest.mark.asyncio
    async def test_write_parameters_consecutive_batching(self) -> None:
        """Test that consecutive parameters are batched into single writes."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)

            mock_response = MagicMock()
            mock_response.isError.return_value = False

            mock_client.write_register = AsyncMock(return_value=mock_response)
            mock_client.write_registers = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await transport.connect()

            # Write consecutive addresses - should be batched
            result = await transport.write_parameters({0: 100, 1: 200, 2: 300})
            assert result is True

            # Should be called once with all 3 values
            mock_client.write_registers.assert_awaited_once()
            call_args = mock_client.write_registers.call_args
            assert call_args.kwargs["address"] == 0
            assert call_args.kwargs["values"] == [100, 200, 300]

    @pytest.mark.asyncio
    async def test_write_parameters_non_consecutive_multiple_calls(self) -> None:
        """Test that non-consecutive parameters result in multiple writes."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)

            mock_response = MagicMock()
            mock_response.isError.return_value = False

            mock_client.write_register = AsyncMock(return_value=mock_response)
            mock_client.write_registers = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await transport.connect()

            # Write non-consecutive addresses - should result in multiple calls
            # Single registers use FC6 (write_register), not FC16 (write_registers)
            result = await transport.write_parameters({0: 100, 5: 500, 10: 1000})
            assert result is True

            # Should be called 3 times (one for each non-consecutive single register)
            assert mock_client.write_register.await_count == 3

    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        """Test async context manager (async with)."""
        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()
            mock_client_class.return_value = mock_client

            transport = ModbusTransport(
                host="192.168.1.100",
                serial="CE12345678",
            )

            async with transport as t:
                assert t is transport
                assert transport.is_connected is True

            assert transport.is_connected is False
            mock_client.close.assert_called_once()


class TestReadAllInputData:
    """Tests for the combined read_all_input_data method."""

    @pytest.mark.asyncio
    async def test_read_all_returns_runtime_energy_battery(self) -> None:
        """Test combined read returns all three data types from shared registers."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()

            # Build a register response with battery data
            registers = [0] * 197
            registers[1] = 5100  # PV1 voltage (×10 = 510V)
            registers[4] = 530  # Battery voltage (×10 = 53V)
            registers[5] = (100 << 8) | 85  # SOC=85, SOH=100
            registers[7] = 1000  # PV1 power
            registers[10] = 500  # Charge power
            registers[12] = 2410  # Grid voltage
            registers[15] = 5998  # Grid frequency
            registers[27] = 1500  # Load power
            registers[96] = 0  # Battery count = 0 (no individual batteries)

            mock_response = MagicMock()
            mock_response.isError.return_value = False
            mock_response.registers = registers[:32]

            # Each register group read returns appropriate slice
            call_idx = 0

            async def mock_read(address: int, count: int, **kwargs: int) -> MagicMock:
                nonlocal call_idx
                resp = MagicMock()
                resp.isError.return_value = False
                resp.registers = registers[address : address + count]
                call_idx += 1
                return resp

            mock_client.read_input_registers = mock_read
            mock_client_class.return_value = mock_client

            await transport.connect()
            runtime, energy, battery = await transport.read_all_input_data()

            # All three data types should be constructed
            assert runtime is not None
            assert energy is not None
            assert runtime.pv1_voltage == pytest.approx(510.0, rel=0.01)
            assert runtime.battery_soc == 85

            # Should have made exactly 8 reads (one per register group)
            assert call_idx == 8

    @pytest.mark.asyncio
    async def test_read_all_reads_individual_batteries(self) -> None:
        """Test combined read includes individual battery registers when present."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()

            # Build registers with battery_count = 2
            registers = [0] * 197
            registers[4] = 530  # Battery voltage
            registers[5] = (100 << 8) | 85  # SOC/SOH
            registers[96] = 2  # Battery count = 2

            read_addresses: list[int] = []

            async def mock_read(address: int, count: int, **kwargs: int) -> MagicMock:
                read_addresses.append(address)
                resp = MagicMock()
                resp.isError.return_value = False
                if address < 200:
                    resp.registers = registers[address : address + count]
                else:
                    # Individual battery registers at 5002+
                    resp.registers = [0] * count
                return resp

            mock_client.read_input_registers = mock_read
            mock_client_class.return_value = mock_client

            await transport.connect()
            runtime, energy, battery = await transport.read_all_input_data()

            # Should read 8 register groups + individual battery reads at 5002+
            assert any(addr >= 5000 for addr in read_addresses)
            # First 8 reads are the register groups
            group_starts = [0, 32, 64, 80, 113, 140, 170, 193]
            for expected_start in group_starts:
                assert expected_start in read_addresses

    @pytest.mark.asyncio
    async def test_read_all_fewer_reads_than_separate(self) -> None:
        """Test combined read uses fewer Modbus reads than separate calls."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()

            registers = [0] * 197
            registers[4] = 530  # Battery voltage
            registers[5] = (100 << 8) | 85  # SOC/SOH
            registers[96] = 0  # No individual batteries

            async def count_reads(address: int, count: int, **kwargs: int) -> MagicMock:
                resp = MagicMock()
                resp.isError.return_value = False
                if address < 200:
                    resp.registers = registers[address : address + count]
                else:
                    resp.registers = [0] * count
                return resp

            mock_client.read_input_registers = count_reads
            mock_client_class.return_value = mock_client

            await transport.connect()

            # Count combined reads
            original_read = mock_client.read_input_registers
            call_count = 0

            async def counting_read(address: int, count: int, **kwargs: int) -> MagicMock:
                nonlocal call_count
                call_count += 1
                return await original_read(address, count, **kwargs)

            mock_client.read_input_registers = counting_read

            await transport.read_all_input_data()
            combined_reads = call_count

            # Combined should use exactly 8 reads (no individual batteries)
            assert combined_reads == 8

    @pytest.mark.asyncio
    async def test_read_all_survives_bms_data_failure(self) -> None:
        """Test that bms_data failure is non-fatal, matching read_energy() resilience."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()

            registers = [0] * 197
            registers[4] = 530  # Battery voltage
            registers[5] = (100 << 8) | 85  # SOC/SOH
            registers[96] = 0  # No individual batteries

            async def mock_read_with_bms_failure(
                address: int, count: int, **kwargs: int
            ) -> MagicMock:
                # bms_data group starts at register 80
                if address == 80:
                    raise OSError("BMS communication timeout")
                resp = MagicMock()
                resp.isError.return_value = False
                resp.registers = registers[address : address + count]
                return resp

            mock_client.read_input_registers = mock_read_with_bms_failure
            mock_client_class.return_value = mock_client

            await transport.connect()
            runtime, energy, battery = await transport.read_all_input_data()

            # Should succeed despite bms_data failure
            assert runtime is not None
            assert energy is not None

    @pytest.mark.asyncio
    async def test_read_all_battery_single_atomic_read(self) -> None:
        """Battery registers are read in a single atomic Modbus call.

        Since v0.9.13 (#170), all battery slots are read in one FC 04 call
        (up to 120 regs) to prevent round-robin rotation from changing slot
        contents between reads.
        """
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()

            registers = [0] * 197
            registers[4] = 530  # Battery voltage
            registers[5] = (100 << 8) | 85  # SOC/SOH
            registers[96] = 4  # Battery count = 4

            read_addresses: list[int] = []

            async def mock_read_atomic(address: int, count: int, **kwargs: int) -> MagicMock:
                read_addresses.append(address)
                resp = MagicMock()
                resp.isError.return_value = False
                if address < 200:
                    resp.registers = registers[address : address + count]
                elif address == 5000:
                    # Header registers
                    resp.registers = [0] * count
                elif address == 5002:
                    # Single atomic read of all 120 battery regs
                    assert count == 120, f"Expected atomic read of 120 regs, got {count}"
                    vals = [0] * count
                    # Populate status header for each slot
                    for slot in range(4):
                        vals[slot * 30] = 0xC003
                    resp.registers = vals
                else:
                    resp.registers = [0] * count
                return resp

            mock_client.read_input_registers = mock_read_atomic
            mock_client_class.return_value = mock_client

            await transport.connect()
            runtime, energy, battery = await transport.read_all_input_data()

            # Runtime/energy still valid
            assert runtime is not None
            assert energy is not None

            # Battery bank should exist
            assert battery is not None

            # Should have exactly one read at 5002 (atomic), plus header at 5000
            battery_reads = [a for a in read_addresses if a >= 5000]
            assert 5000 in battery_reads  # header read
            assert 5002 in battery_reads  # single atomic read
            # No chunked reads at 5042, 5082, etc.
            assert 5042 not in battery_reads
            assert 5082 not in battery_reads


class TestAdaptiveBatterySlotCeiling:
    """Tests for the adaptive slot ceiling with atomic battery reads.

    Since v0.9.13 (#170), all battery slots are read in a single atomic
    Modbus FC 04 call.  If the read fails, the ceiling drops to 0 so
    subsequent polls skip battery registers entirely.  The ceiling
    resets when the transport reconnects.
    """

    @pytest.mark.asyncio
    async def test_ceiling_drops_to_zero_on_failure(self) -> None:
        """Atomic read failure sets ceiling to 0 and returns None."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()

            async def mock_read(address: int, count: int, **kwargs: int) -> MagicMock:
                if address >= 5002:
                    raise TransportReadError(
                        f"Modbus read error at address {address}: "
                        "ExceptionResponse(exception_code=3)"
                    )
                resp = MagicMock()
                resp.isError.return_value = False
                resp.registers = [0] * count
                return resp

            mock_client.read_input_registers = mock_read
            mock_client_class.return_value = mock_client

            await transport.connect()

            # battery_count=12 capped at 4 (MAX_COUNT), single read of
            # 120 regs fails -> ceiling drops to 0
            result = await transport._read_individual_battery_registers(12)
            assert result is None
            assert transport._battery_slot_ceiling == 0

    @pytest.mark.asyncio
    async def test_ceiling_prevents_retry_on_subsequent_polls(self) -> None:
        """After ceiling drops to 0, battery reads are skipped entirely."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()

            read_addresses: list[int] = []

            async def mock_read(address: int, count: int, **kwargs: int) -> MagicMock:
                read_addresses.append(address)
                if address >= 5002:
                    raise TransportReadError(f"Illegal data address {address}")
                resp = MagicMock()
                resp.isError.return_value = False
                resp.registers = [0] * count
                return resp

            mock_client.read_input_registers = mock_read
            mock_client_class.return_value = mock_client

            await transport.connect()

            # First call: fails, ceiling drops to 0
            await transport._read_individual_battery_registers(12)
            first_call_addrs = list(read_addresses)

            # Second call: ceiling=0, returns None immediately without reading
            read_addresses.clear()
            result = await transport._read_individual_battery_registers(12)
            assert result is None
            assert len(read_addresses) == 0  # no reads attempted
            assert 5002 in first_call_addrs  # first call did attempt

    @pytest.mark.asyncio
    async def test_successful_atomic_read(self) -> None:
        """Successful atomic read returns all 120 registers."""
        transport = ModbusTransport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        with patch("pymodbus.client.AsyncModbusTcpClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.close = MagicMock()

            read_addresses: list[int] = []

            async def mock_read(address: int, count: int, **kwargs: int) -> MagicMock:
                read_addresses.append(address)
                resp = MagicMock()
                resp.isError.return_value = False
                vals = [0] * count
                if address == 5002:
                    # Populate status header for each of 4 slots
                    for slot in range(4):
                        vals[slot * 30] = 0xC003
                resp.registers = vals
                return resp

            mock_client.read_input_registers = mock_read
            mock_client_class.return_value = mock_client

            await transport.connect()

            result = await transport._read_individual_battery_registers(4)
            assert result is not None
            assert len(result) == 120  # 4 slots * 30 regs
            # Only one battery read at 5002 (atomic)
            battery_reads = [a for a in read_addresses if a >= 5002]
            assert battery_reads == [5002]


class TestBatteryRoundRobinAccumulator:
    """Tests for round-robin battery accumulation (#170).

    Systems with >4 batteries expose data through 4 register slots that
    rotate.  The accumulator merges slot data across refresh cycles using
    the ``pos`` field (offset 24, high byte) as canonical battery identity.
    """

    def _make_transport(self) -> ModbusTransport:
        return ModbusTransport(host="192.168.1.100", serial="CE12345678")

    def _mock_client(
        self,
        slot_values_per_call: list[list[int]],
    ) -> tuple[MagicMock, MagicMock]:
        """Create mock client that returns different battery data per call.

        Args:
            slot_values_per_call: List of 120-int lists, one per call to
                read_input_registers at address 5002.

        Returns:
            (mock_client, mock_client_class) for use with patch.
        """
        call_idx = [0]
        mock_client = MagicMock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = MagicMock()

        async def mock_read(address: int, count: int, **kwargs: int) -> MagicMock:
            resp = MagicMock()
            resp.isError.return_value = False
            if address == 5002:
                idx = min(call_idx[0], len(slot_values_per_call) - 1)
                resp.registers = slot_values_per_call[idx]
                call_idx[0] += 1
            else:
                resp.registers = [0] * count
            return resp

        mock_client.read_input_registers = mock_read
        mock_class = MagicMock(return_value=mock_client)
        return mock_client, mock_class

    @pytest.mark.asyncio
    async def test_no_accumulation_when_count_le_4(self) -> None:
        """battery_count <= 4: no accumulation, raw registers returned."""
        transport = self._make_transport()
        page_a = _build_battery_slot_values([0, 1, 2, 3])
        _, mock_class = self._mock_client([page_a])

        with patch("pymodbus.client.AsyncModbusTcpClient", mock_class):
            await transport.connect()
            result = await transport._read_individual_battery_registers(4)

        assert result is not None
        # Raw registers: 4 slots × 30 = 120
        assert len(result) == 120
        # No accumulator created
        assert not hasattr(transport, "_battery_accumulator") or not getattr(
            transport, "_battery_accumulator", {}
        )

    @pytest.mark.asyncio
    async def test_accumulation_first_page(self) -> None:
        """First read with battery_count=8 populates 4 of 8 positions."""
        transport = self._make_transport()
        page_a = _build_battery_slot_values([0, 1, 2, 3])
        _, mock_class = self._mock_client([page_a])

        with patch("pymodbus.client.AsyncModbusTcpClient", mock_class):
            await transport.connect()
            result = await transport._read_individual_battery_registers(8)

        assert result is not None
        # 4 batteries accumulated, each with 30 registers
        assert len(result) == 4 * BATTERY_REGISTER_COUNT

        # Verify positions 0-3 present
        for pos in range(4):
            base = BATTERY_BASE_ADDRESS + (pos * BATTERY_REGISTER_COUNT)
            assert result.get(base) == 0xC003, f"pos {pos} status missing"

        # Positions 4-7 not yet populated
        for pos in range(4, 8):
            base = BATTERY_BASE_ADDRESS + (pos * BATTERY_REGISTER_COUNT)
            assert result.get(base) is None, f"pos {pos} should not exist yet"

    @pytest.mark.asyncio
    async def test_accumulation_two_pages_full_population(self) -> None:
        """Two reads with different pages populate all 8 batteries."""
        transport = self._make_transport()
        page_a = _build_battery_slot_values([0, 1, 2, 3])
        page_b = _build_battery_slot_values([4, 5, 6, 7])
        _, mock_class = self._mock_client([page_a, page_b])

        with patch("pymodbus.client.AsyncModbusTcpClient", mock_class):
            await transport.connect()

            # First read: positions 0-3
            result1 = await transport._read_individual_battery_registers(8)
            assert result1 is not None
            assert len(result1) == 4 * BATTERY_REGISTER_COUNT

            # Second read: positions 4-7 merge with 0-3
            result2 = await transport._read_individual_battery_registers(8)
            assert result2 is not None
            assert len(result2) == 8 * BATTERY_REGISTER_COUNT

        # All 8 positions present
        for pos in range(8):
            base = BATTERY_BASE_ADDRESS + (pos * BATTERY_REGISTER_COUNT)
            assert result2.get(base) == 0xC003, f"pos {pos} missing after 2 pages"

    @pytest.mark.asyncio
    async def test_accumulation_overwrites_stale_data(self) -> None:
        """Re-reading the same page updates existing positions with fresh data."""
        transport = self._make_transport()
        page_a_v1 = _build_battery_slot_values([0, 1, 2, 3], voltage_raw=5246)
        page_a_v2 = _build_battery_slot_values([0, 1, 2, 3], voltage_raw=5300)
        _, mock_class = self._mock_client([page_a_v1, page_a_v2])

        with patch("pymodbus.client.AsyncModbusTcpClient", mock_class):
            await transport.connect()
            await transport._read_individual_battery_registers(8)
            result = await transport._read_individual_battery_registers(8)

        assert result is not None
        # pos 0 voltage should be updated to 5300
        pos0_voltage_addr = BATTERY_BASE_ADDRESS + 6
        assert result[pos0_voltage_addr] == 5300

    @pytest.mark.asyncio
    async def test_empty_slots_skipped_during_accumulation(self) -> None:
        """Empty slots (status=0) don't pollute the accumulator."""
        transport = self._make_transport()
        # Slot 0: pos=0, Slot 1: empty, Slot 2: pos=2, Slot 3: empty
        page = _build_battery_slot_values([0, -1, 2, -1])
        _, mock_class = self._mock_client([page])

        with patch("pymodbus.client.AsyncModbusTcpClient", mock_class):
            await transport.connect()
            result = await transport._read_individual_battery_registers(8)

        assert result is not None
        # Only pos 0 and 2 populated
        assert result.get(BATTERY_BASE_ADDRESS) == 0xC003  # pos 0
        pos2_base = BATTERY_BASE_ADDRESS + (2 * BATTERY_REGISTER_COUNT)
        assert result.get(pos2_base) == 0xC003  # pos 2
        # pos 1 not present
        pos1_base = BATTERY_BASE_ADDRESS + (1 * BATTERY_REGISTER_COUNT)
        assert result.get(pos1_base) is None

    @pytest.mark.asyncio
    async def test_battery_count_change_clears_accumulator(self) -> None:
        """Accumulator resets when battery_count changes."""
        transport = self._make_transport()
        page_8bat = _build_battery_slot_values([0, 1, 2, 3])
        page_12bat = _build_battery_slot_values([0, 1, 2, 3])
        _, mock_class = self._mock_client([page_8bat, page_12bat])

        with patch("pymodbus.client.AsyncModbusTcpClient", mock_class):
            await transport.connect()

            # First read with battery_count=8
            result1 = await transport._read_individual_battery_registers(8)
            assert result1 is not None
            assert len(transport._battery_accumulator) == 4

            # Second read with battery_count=12 — accumulator cleared
            result2 = await transport._read_individual_battery_registers(12)
            assert result2 is not None
            # Should have exactly 4 (fresh), not 4+4
            assert len(transport._battery_accumulator) == 4

    @pytest.mark.asyncio
    async def test_pos_exceeding_battery_count_skipped(self) -> None:
        """Battery with pos >= battery_count is ignored."""
        transport = self._make_transport()
        # pos=10 exceeds battery_count=8
        page = _build_battery_slot_values([0, 1, 10, 3])
        _, mock_class = self._mock_client([page])

        with patch("pymodbus.client.AsyncModbusTcpClient", mock_class):
            await transport.connect()
            result = await transport._read_individual_battery_registers(8)

        assert result is not None
        # Only 3 valid positions accumulated (0, 1, 3)
        assert len(transport._battery_accumulator) == 3
        assert 10 not in transport._battery_accumulator

    @pytest.mark.asyncio
    async def test_twelve_battery_three_page_accumulation(self) -> None:
        """12-battery system accumulates across 3 pages."""
        transport = self._make_transport()
        page_a = _build_battery_slot_values([0, 1, 2, 3])
        page_b = _build_battery_slot_values([4, 5, 6, 7])
        page_c = _build_battery_slot_values([8, 9, 10, 11])
        _, mock_class = self._mock_client([page_a, page_b, page_c])

        with patch("pymodbus.client.AsyncModbusTcpClient", mock_class):
            await transport.connect()

            r1 = await transport._read_individual_battery_registers(12)
            assert r1 is not None
            assert len(transport._battery_accumulator) == 4

            r2 = await transport._read_individual_battery_registers(12)
            assert r2 is not None
            assert len(transport._battery_accumulator) == 8

            r3 = await transport._read_individual_battery_registers(12)
            assert r3 is not None
            assert len(transport._battery_accumulator) == 12

        # All 12 positions present in final result
        for pos in range(12):
            base = BATTERY_BASE_ADDRESS + (pos * BATTERY_REGISTER_COUNT)
            assert r3.get(base) == 0xC003, f"pos {pos} missing after 3 pages"

    @pytest.mark.asyncio
    async def test_last_seen_timestamps_tracked(self) -> None:
        """Accumulator tracks per-position last_seen timestamps."""
        transport = self._make_transport()
        page_a = _build_battery_slot_values([0, 1, 2, 3])
        page_b = _build_battery_slot_values([4, 5, 6, 7])
        _, mock_class = self._mock_client([page_a, page_b])

        with patch("pymodbus.client.AsyncModbusTcpClient", mock_class):
            await transport.connect()

            # First read: positions 0-3 get timestamps
            await transport._read_individual_battery_registers(8)
            ts_page_a = dict(transport._battery_last_seen)
            assert set(ts_page_a.keys()) == {0, 1, 2, 3}

            # Second read: positions 4-7 added, 0-3 timestamps preserved
            await transport._read_individual_battery_registers(8)
            assert set(transport._battery_last_seen.keys()) == {0, 1, 2, 3, 4, 5, 6, 7}

            # Page A timestamps unchanged (those positions weren't in page B)
            for pos in range(4):
                assert transport._battery_last_seen[pos] == ts_page_a[pos]

            # Page B timestamps are newer
            for pos in range(4, 8):
                assert transport._battery_last_seen[pos] >= ts_page_a[0]

    @pytest.mark.asyncio
    async def test_last_seen_not_set_when_count_le_4(self) -> None:
        """No last_seen tracking when accumulation is inactive."""
        transport = self._make_transport()
        page = _build_battery_slot_values([0, 1, 2, 3])
        _, mock_class = self._mock_client([page])

        with patch("pymodbus.client.AsyncModbusTcpClient", mock_class):
            await transport.connect()
            await transport._read_individual_battery_registers(4)

        # No accumulator or last_seen created for <=4 batteries
        assert not getattr(transport, "_battery_last_seen", {})
