"""Tests for EG4 master battery protocol (unit ID 1).

Register map derived from Ghidra decompilation of HC32 BMS firmware
function FUN_0001cf78.
"""

from __future__ import annotations

import struct

import pytest

from pylxpweb.battery_protocols.eg4_master import EG4MasterProtocol


def _signed16(value: int) -> int:
    """Convert signed int16 to unsigned for raw register simulation."""
    return struct.unpack("H", struct.pack("h", value))[0]


class TestEG4MasterProtocol:
    """Tests for EG4 master battery register map."""

    def setup_method(self) -> None:
        self.protocol = EG4MasterProtocol()

    def test_protocol_name(self) -> None:
        assert self.protocol.name == "eg4_master"

    def test_register_blocks_cover_runtime_and_cells(self) -> None:
        starts = [b.start for b in self.protocol.register_blocks]
        assert 19 in starts  # Runtime starts at 19, not 0
        assert 113 in starts  # Cell voltage block

    def test_decode_voltage(self) -> None:
        """Pack voltage: reg 22 /100."""
        raw = self._base_regs()
        raw[22] = 5294
        data = self.protocol.decode(raw)
        assert data.voltage == pytest.approx(52.94)

    def test_decode_aggregate_current(self) -> None:
        """Aggregate current: reg 23 /100, signed."""
        raw = self._base_regs()
        raw[23] = _signed16(-3080)
        data = self.protocol.decode(raw)
        assert data.current == pytest.approx(-30.80)

    def test_decode_temperature(self) -> None:
        """Max temperature: reg 24, direct C."""
        raw = self._base_regs()
        raw[24] = 22
        data = self.protocol.decode(raw)
        assert data.temperature == 22.0

    def test_decode_soc(self) -> None:
        """SOC: reg 26 /10, truncated to int."""
        raw = self._base_regs()
        raw[26] = 764
        data = self.protocol.decode(raw)
        assert data.soc == 76  # Truncated to int

    def test_decode_cycle_count(self) -> None:
        """Cycle count: reg 30, direct."""
        raw = self._base_regs()
        raw[30] = 138
        data = self.protocol.decode(raw)
        assert data.cycle_count == 138

    def test_decode_soh(self) -> None:
        """SOH: reg 32, direct."""
        raw = self._base_regs()
        raw[32] = 100
        data = self.protocol.decode(raw)
        assert data.soh == 100

    def test_decode_designed_capacity(self) -> None:
        """Designed capacity: reg 33 /20."""
        raw = self._base_regs()
        raw[33] = 5600  # 280 Ah
        data = self.protocol.decode(raw)
        assert data.max_capacity == pytest.approx(280.0)

    def test_decode_cell_voltages(self) -> None:
        """Cell voltages: regs 113-128, /1000."""
        raw = self._base_regs()
        raw[41] = 16  # num cells
        for i in range(16):
            raw[113 + i] = 3308 + i
        data = self.protocol.decode(raw)
        assert len(data.cell_voltages) == 16
        assert data.cell_voltages[0] == pytest.approx(3.308)
        assert data.cell_voltages[15] == pytest.approx(3.323)

    def test_decode_min_max_cell(self) -> None:
        """Max/min cell voltage: regs 37/38 /1000."""
        raw = self._base_regs()
        raw[37] = 3311
        raw[38] = 3308
        data = self.protocol.decode(raw)
        assert data.max_cell_voltage == pytest.approx(3.311)
        assert data.min_cell_voltage == pytest.approx(3.308)

    def test_decode_firmware_version(self) -> None:
        """Firmware: reg 28, packed BCD -> '2.17'."""
        raw = self._base_regs()
        raw[28] = 0x0211  # High=2, Low=0x11=17
        data = self.protocol.decode(raw)
        assert data.firmware_version == "2.17"

    def test_regs_0_to_18_ignored(self) -> None:
        """Regs 0-18 are unused in master protocol."""
        raw = self._base_regs()
        raw[0] = 5294  # Would be voltage in slave protocol
        data = self.protocol.decode(raw)
        # Voltage should come from reg 22, not reg 0
        assert data.voltage == pytest.approx(0.0)

    def test_decode_negative_temperature(self) -> None:
        """Temperature can be negative (signed int16)."""
        raw = self._base_regs()
        raw[24] = _signed16(-5)
        data = self.protocol.decode(raw)
        assert data.temperature == -5.0

    def test_decode_positive_current_charging(self) -> None:
        """Positive current represents charging."""
        raw = self._base_regs()
        raw[23] = 1500  # +15.00A charging
        data = self.protocol.decode(raw)
        assert data.current == pytest.approx(15.00)

    def test_decode_soc_truncation(self) -> None:
        """SOC /10 truncates (does not round)."""
        raw = self._base_regs()
        raw[26] = 999  # 99.9% -> 99 (truncated, not 100)
        data = self.protocol.decode(raw)
        assert data.soc == 99

    def test_decode_battery_index_passthrough(self) -> None:
        """Battery index is passed through to BatteryData."""
        raw = self._base_regs()
        data = self.protocol.decode(raw, battery_index=0)
        assert data.battery_index == 0

    def test_decode_all_zeros_graceful(self) -> None:
        """All-zero registers decode without error."""
        raw = self._base_regs()
        data = self.protocol.decode(raw)
        assert data.voltage == 0.0
        assert data.current == 0.0
        assert data.soc == 0
        assert data.soh == 100  # Default SOH
        assert data.max_capacity == 0.0
        assert data.firmware_version == ""

    def test_decode_status_and_faults(self) -> None:
        """Status, protection, and warning bitfields."""
        raw = self._base_regs()
        raw[19] = 0x0001  # Status
        raw[20] = 0x0010  # Protection -> fault_code
        raw[34] = 0x0004  # Warning
        data = self.protocol.decode(raw)
        assert data.status == 0x0001
        assert data.fault_code == 0x0010
        assert data.warning_code == 0x0004

    def test_decode_cell_count_fewer_than_16(self) -> None:
        """Cell voltages limited to num_cells."""
        raw = self._base_regs()
        raw[41] = 8  # Only 8 cells
        for i in range(8):
            raw[113 + i] = 3300 + i
        data = self.protocol.decode(raw)
        assert len(data.cell_voltages) == 8
        assert data.cell_count == 8

    def test_decode_zero_cells_no_crash(self) -> None:
        """When num_cells=0, cell arrays empty and min/max are 0."""
        raw = self._base_regs()
        raw[41] = 0
        data = self.protocol.decode(raw)
        assert data.cell_count == 0
        assert data.cell_voltages == []
        assert data.min_cell_voltage == 0.0
        assert data.max_cell_voltage == 0.0

    def test_decode_max_min_cell_index(self) -> None:
        """Max/min cell index registers (0-based)."""
        raw = self._base_regs()
        raw[39] = 3  # Max cell index
        raw[40] = 7  # Min cell index
        data = self.protocol.decode(raw)
        # max_cell_num_voltage is 1-indexed in BatteryData
        assert data.max_cell_num_voltage == 4  # 0-based 3 -> 1-based 4
        assert data.min_cell_num_voltage == 8  # 0-based 7 -> 1-based 8

    def _base_regs(self) -> dict[int, int]:
        """Create a minimal raw register dict with all zeros."""
        return dict.fromkeys(range(42), 0) | dict.fromkeys(range(113, 129), 0)
