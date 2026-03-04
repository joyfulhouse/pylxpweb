"""Tests for EG4 slave battery protocol (unit IDs 2+)."""

from __future__ import annotations

import struct

import pytest

from pylxpweb.battery_protocols.eg4_slave import EG4SlaveProtocol


class TestEG4SlaveProtocol:
    """Tests for EG4 slave battery register map."""

    def setup_method(self) -> None:
        self.protocol = EG4SlaveProtocol()

    def test_protocol_name(self) -> None:
        assert self.protocol.name == "eg4_slave"

    def test_register_blocks_cover_runtime_and_info(self) -> None:
        starts = [b.start for b in self.protocol.register_blocks]
        assert 0 in starts  # Runtime block
        assert 105 in starts  # Device info block

    def test_decode_voltage_and_current(self) -> None:
        """Decode standard slave registers: voltage /100, current /100 signed."""
        # -30.80A as unsigned 16-bit
        neg_current = struct.unpack("H", struct.pack("h", -3080))[0]
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        raw[0] = 5294  # 52.94V
        raw[1] = neg_current  # -30.80A
        data = self.protocol.decode(raw, battery_index=0)
        assert data.voltage == pytest.approx(52.94)
        assert data.current == pytest.approx(-30.80)

    def test_decode_cell_voltages(self) -> None:
        """Cell voltages at regs 2-17, /1000."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        raw[0] = 5300  # voltage
        raw[36] = 16  # num cells
        for i in range(16):
            raw[2 + i] = 3310 + i  # 3.310V to 3.325V
        data = self.protocol.decode(raw, battery_index=0)
        assert len(data.cell_voltages) == 16
        assert data.cell_voltages[0] == pytest.approx(3.310)
        assert data.cell_voltages[15] == pytest.approx(3.325)

    def test_decode_cell_voltages_fewer_cells(self) -> None:
        """Only decode as many cell voltages as num_cells indicates."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        raw[36] = 8  # Only 8 cells
        for i in range(8):
            raw[2 + i] = 3300 + i
        data = self.protocol.decode(raw, battery_index=0)
        assert len(data.cell_voltages) == 8
        assert data.cell_count == 8

    def test_decode_min_max_cell_voltage(self) -> None:
        """Min/max cell voltages are derived from cell voltage array."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        raw[36] = 4
        raw[2] = 3300  # 3.300V
        raw[3] = 3350  # 3.350V
        raw[4] = 3280  # 3.280V - minimum
        raw[5] = 3400  # 3.400V - maximum
        data = self.protocol.decode(raw, battery_index=0)
        assert data.min_cell_voltage == pytest.approx(3.280)
        assert data.max_cell_voltage == pytest.approx(3.400)

    def test_decode_soc_soh(self) -> None:
        """SOC and SOH are direct (no scaling)."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        raw[23] = 100  # SOH
        raw[24] = 76  # SOC
        data = self.protocol.decode(raw, battery_index=0)
        assert data.soh == 100
        assert data.soc == 76

    def test_decode_temperatures_fallback(self) -> None:
        """Without packed temps, falls back to PCB (min) and max (max)."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        raw[18] = 25  # PCB temp
        raw[19] = 23  # Avg temp
        raw[20] = 27  # Max temp
        # regs 33-35 = 0 → no packed temps → fallback
        data = self.protocol.decode(raw, battery_index=0)
        assert data.temperature == 27.0  # Use max as primary temp
        assert data.max_cell_temperature == 27.0
        assert data.min_cell_temperature == 25.0  # PCB temp as fallback min

    def test_decode_signed_temperature(self) -> None:
        """Temperatures can be negative (signed int16)."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        neg_temp = struct.unpack("H", struct.pack("h", -5))[0]
        raw[18] = neg_temp  # PCB temp = -5
        raw[19] = neg_temp  # Avg temp = -5
        raw[20] = neg_temp  # Max temp = -5
        data = self.protocol.decode(raw, battery_index=0)
        assert data.temperature == -5.0

    def test_decode_remaining_capacity(self) -> None:
        """Remaining capacity: reg21, direct Ah."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        raw[21] = 200  # 200 Ah
        data = self.protocol.decode(raw, battery_index=0)
        assert data.current_capacity == 200.0

    def test_decode_designed_capacity(self) -> None:
        """Designed capacity: reg37 /10."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        raw[37] = 2800  # 280.0 Ah
        data = self.protocol.decode(raw, battery_index=0)
        assert data.max_capacity == pytest.approx(280.0)

    def test_decode_cycle_count_32bit(self) -> None:
        """Cycle count: 32-bit big-endian from regs 29-30."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        raw[29] = 0  # High word
        raw[30] = 138  # Low word
        data = self.protocol.decode(raw, battery_index=0)
        assert data.cycle_count == 138

    def test_decode_cycle_count_large(self) -> None:
        """Cycle count spans both registers for large values."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        raw[29] = 1  # High word = 1 (65536)
        raw[30] = 500  # Low word
        data = self.protocol.decode(raw, battery_index=0)
        assert data.cycle_count == 65536 + 500

    def test_decode_status_and_faults(self) -> None:
        """Status, warning, protection, error bitfields."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        raw[25] = 0x0001  # Status
        raw[26] = 0x0004  # Warning
        raw[27] = 0x0010  # Protection (mapped to fault_code)
        data = self.protocol.decode(raw, battery_index=0)
        assert data.status == 0x0001
        assert data.warning_code == 0x0004
        assert data.fault_code == 0x0010

    def test_decode_device_info_model(self) -> None:
        """Device info: model at regs 105-116 decoded as ASCII."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        # "EG4-LL" in ASCII: E=0x45, G=0x47, 4=0x34, -=0x2D, L=0x4C, L=0x4C
        raw[105] = 0x4547  # "EG"
        raw[106] = 0x342D  # "4-"
        raw[107] = 0x4C4C  # "LL"
        for i in range(108, 117):
            raw[i] = 0
        data = self.protocol.decode(raw, battery_index=0)
        assert "EG4-LL" in data.model

    def test_decode_device_info_firmware(self) -> None:
        """Firmware at regs 117-119 decoded as ASCII."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        # "217" -> 0x3231 ("21"), 0x3700 ("7\x00")
        raw[117] = 0x3231  # "21"
        raw[118] = 0x3700  # "7\0"
        raw[119] = 0
        data = self.protocol.decode(raw, battery_index=0)
        assert data.firmware_version != ""
        assert "217" in data.firmware_version

    def test_decode_device_info_serial(self) -> None:
        """Serial number at regs 120-127 decoded as ASCII."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        # "AB123456" -> 8 chars = 4 registers
        raw[120] = 0x4142  # "AB"
        raw[121] = 0x3132  # "12"
        raw[122] = 0x3334  # "34"
        raw[123] = 0x3536  # "56"
        for i in range(124, 128):
            raw[i] = 0
        data = self.protocol.decode(raw, battery_index=0)
        assert data.serial_number == "AB123456"

    def test_decode_battery_index(self) -> None:
        """Battery index is passed through to BatteryData."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        data = self.protocol.decode(raw, battery_index=3)
        assert data.battery_index == 3

    def test_decode_all_zero_registers(self) -> None:
        """Gracefully handles all-zero register map."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        data = self.protocol.decode(raw, battery_index=0)
        assert data.voltage == 0.0
        assert data.current == 0.0
        assert data.soc == 0
        assert data.max_capacity == 0.0
        assert data.cell_voltages == []  # 0 cells -> empty

    def test_decode_zero_cells_no_crash(self) -> None:
        """When num_cells=0, cell arrays are empty and min/max are 0."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        raw[36] = 0  # num_cells = 0
        data = self.protocol.decode(raw, battery_index=0)
        assert data.cell_count == 0
        assert data.cell_voltages == []
        assert data.min_cell_voltage == 0.0
        assert data.max_cell_voltage == 0.0

    def test_decode_max_charge_current(self) -> None:
        """Max charge current: reg22, direct A."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        raw[22] = 100  # 100A
        data = self.protocol.decode(raw, battery_index=0)
        assert data.charge_current_limit == 100.0

    def test_decode_packed_temps(self) -> None:
        """Per-cell NTC temps from packed regs 33-35 override summary regs."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        raw[18] = 25  # PCB temp (fallback min)
        raw[20] = 27  # Max temp (fallback max)
        # Packed temps: reg33=0x1312 (19,18), reg34=0x1211 (18,17), reg35=0x1312 (19,18)
        raw[33] = 0x1312
        raw[34] = 0x1211
        raw[35] = 0x1312
        data = self.protocol.decode(raw, battery_index=0)
        assert data.cell_temperatures == [19.0, 18.0, 18.0, 17.0, 19.0, 18.0]
        assert data.min_cell_temperature == 17.0
        assert data.max_cell_temperature == 19.0

    def test_decode_packed_temps_negative(self) -> None:
        """Packed temps handle negative values (signed bytes)."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        raw[18] = 0  # PCB temp
        raw[20] = 0  # Max temp
        # -3°C = 0xFD, -5°C = 0xFB
        raw[33] = 0xFDFB
        data = self.protocol.decode(raw, battery_index=0)
        assert data.cell_temperatures == [-3.0, -5.0]
        assert data.min_cell_temperature == -5.0
        assert data.max_cell_temperature == -3.0

    def test_decode_packed_temps_partial(self) -> None:
        """Only non-zero packed temp registers are decoded."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        raw[18] = 20  # PCB temp
        raw[20] = 22  # Max temp
        raw[33] = 0x1514  # 21, 20
        # regs 34, 35 = 0 → skipped
        data = self.protocol.decode(raw, battery_index=0)
        assert data.cell_temperatures == [21.0, 20.0]
        assert data.min_cell_temperature == 20.0
        assert data.max_cell_temperature == 21.0

    def test_decode_packed_temps_all_zero_uses_fallback(self) -> None:
        """When all packed temp regs are zero, falls back to PCB/max temps."""
        raw: dict[int, int] = dict.fromkeys(range(39), 0)
        raw[18] = 25  # PCB temp
        raw[20] = 27  # Max temp
        # regs 33-35 all zero
        data = self.protocol.decode(raw, battery_index=0)
        assert data.cell_temperatures == []
        assert data.min_cell_temperature == 25.0
        assert data.max_cell_temperature == 27.0
