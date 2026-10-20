"""Tests for EG4 master battery protocol (unit ID 1).

Register map derived from Ghidra decompilation of HC32 BMS firmware
function FUN_0001cf78.
"""

from __future__ import annotations

import struct

import pytest

from pylxpweb.battery_protocols.eg4_master import EG4MasterProtocol
from pylxpweb.transports.data import BatteryData


def _to_unsigned16(value: int) -> int:
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

    def test_master_map_has_no_register_named_voltage(self) -> None:
        """Reg 22 is the bank minimum and must not answer to "voltage".

        The name is the guardrail: a future author reaching for
        ``_reg("voltage")`` here -- as the slave protocol legitimately does --
        would silently reintroduce #249 by decoding a bank aggregate as the
        master's own pack voltage.  Failing the lookup is the point.
        """
        with pytest.raises(KeyError, match="voltage"):
            self.protocol._reg("voltage")

        assert self.protocol._reg("bank_min_voltage").address == 22

    def test_decode_does_not_use_bank_minimum_as_master_voltage(self) -> None:
        """Bank-minimum reg 22 is never relabeled as the master's voltage."""
        raw = self._base_regs()
        raw[22] = 5294
        data = self.protocol.decode(raw)
        assert data.voltage == 0.0

    def test_decode_voltage_from_complete_cell_block(self) -> None:
        """A complete plausible cell block supplies the master's pack voltage."""
        raw = self._base_regs()
        raw[22] = 5200
        raw[41] = 16
        for i in range(16):
            raw[113 + i] = 3310

        data = self.protocol.decode(raw)
        assert data.voltage == pytest.approx(52.96)

    def test_decode_voltage_rejects_all_zero_cell_block(self) -> None:
        """A dropped all-zero cell block yields the absent sentinel, not reg 22."""
        raw = self._base_regs()
        raw[22] = 5294
        raw[41] = 16

        data = self.protocol.decode(raw)
        assert data.voltage == 0.0

    def test_decode_voltage_rejects_implausibly_low_cell(self) -> None:
        """A cell below the 1.0 V plausibility bound invalidates the pack sum."""
        raw = self._base_regs()
        raw[22] = 5294
        raw[41] = 16
        for i in range(16):
            raw[113 + i] = 3310
        raw[120] = 999

        data = self.protocol.decode(raw)
        assert data.voltage == 0.0

    def test_decode_voltage_rejects_implausibly_high_cell(self) -> None:
        """A corrupt high cell register cannot create a plausible pack voltage."""
        raw = self._base_regs()
        raw[22] = 5294
        raw[41] = 16
        for i in range(16):
            raw[113 + i] = 3310
        raw[120] = 60000

        data = self.protocol.decode(raw)
        assert data.voltage == 0.0

    def test_decode_voltage_rejects_zero_cell_count(self) -> None:
        """Cell count zero makes master voltage explicitly absent."""
        raw = self._base_regs()
        raw[22] = 5294
        for i in range(16):
            raw[113 + i] = 3310

        data = self.protocol.decode(raw)
        assert data.voltage == 0.0

    def test_decode_voltage_rejects_sum_below_bank_minimum(self) -> None:
        """Reg 22 rejects a truncated sum that cannot be any bank member's voltage."""
        raw = self._base_regs()
        raw[22] = 5294
        raw[41] = 15
        for i in range(15):
            raw[113 + i] = 3310

        data = self.protocol.decode(raw)

        assert data.voltage == 0.0

    def test_decode_voltage_rejects_implausible_cell_count(self) -> None:
        """A transient one-cell count cannot turn one healthy cell into a pack."""
        raw = self._base_regs()
        raw[41] = 1
        raw[113] = 3310

        data = self.protocol.decode(raw)

        assert data.voltage == 0.0

    def test_decode_voltage_rejects_underreported_count_without_bank_minimum(self) -> None:
        """A live register after cell_count catches truncation even when reg 22 is absent."""
        raw = self._base_regs()
        raw[22] = 0
        raw[41] = 15
        for i in range(16):
            raw[113 + i] = 3310

        data = self.protocol.decode(raw)

        assert data.voltage == 0.0

    def test_decode_voltage_accepts_consistent_fifteen_cell_pack(self) -> None:
        """A genuine 15-cell pack with a matching bank minimum remains usable."""
        raw = self._base_regs()
        raw[22] = 4960
        raw[41] = 15
        for i in range(15):
            raw[113 + i] = 3310

        data = self.protocol.decode(raw)

        assert data.voltage == pytest.approx(49.65)

    def test_decode_aggregate_current(self) -> None:
        """Aggregate current: reg 23 /100, signed."""
        raw = self._base_regs()
        raw[23] = _to_unsigned16(-3080)
        data = self.protocol.decode(raw)
        assert data.current == pytest.approx(-30.80)

    def test_decode_temperature(self) -> None:
        """Max temperature: reg 24, direct C."""
        raw = self._base_regs()
        raw[24] = 22
        data = self.protocol.decode(raw)
        assert data.temperature == 22.0

    def test_decode_soc(self) -> None:
        """SOC: reg 21, direct % (capacity-weighted aggregate across all batteries)."""
        raw = self._base_regs()
        raw[21] = 79
        data = self.protocol.decode(raw)
        assert data.soc is None

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

    @pytest.mark.parametrize(
        ("raw_soh", "expected_soh"),
        [(0, None), (100, 100), (1, 1)],
    )
    def test_decode_soh_zero_is_unreported(self, raw_soh: int, expected_soh: int | None) -> None:
        """SOH reg 32 = 0 means not reported → None, never a fabricated value (#309)."""
        raw = self._base_regs()
        raw[32] = raw_soh
        data = self.protocol.decode(raw)
        assert data.soh == expected_soh

    def test_decode_soh_absent_register_is_none(self) -> None:
        """A missing SOH register decodes as unreported (None), not 100 (#309)."""
        raw = self._base_regs()
        del raw[32]
        data = self.protocol.decode(raw)
        assert data.soh is None

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
        """Slave voltage reg 0 is ignored and an absent cell set stays absent."""
        raw = self._base_regs()
        raw[0] = 5294  # Would be voltage in slave protocol
        data = self.protocol.decode(raw)
        assert data.voltage == pytest.approx(0.0)

    def test_decode_negative_temperature(self) -> None:
        """Temperature can be negative (signed int16)."""
        raw = self._base_regs()
        raw[24] = _to_unsigned16(-5)
        data = self.protocol.decode(raw)
        assert data.temperature == -5.0

    def test_decode_positive_current_charging(self) -> None:
        """Positive current represents charging."""
        raw = self._base_regs()
        raw[23] = 1500  # +15.00A charging
        data = self.protocol.decode(raw)
        assert data.current == pytest.approx(15.00)

    def test_decode_soc_full_charge(self) -> None:
        """SOC at 100% (direct value, no scaling)."""
        raw = self._base_regs()
        raw[21] = 100
        data = self.protocol.decode(raw)
        assert data.soc is None

    def test_decode_battery_index_passthrough(self) -> None:
        """Battery index is passed through to BatteryData."""
        raw = self._base_regs()
        data = self.protocol.decode(raw, battery_index=0)
        assert data.battery_index == 0

    def test_decode_all_zeros_graceful(self) -> None:
        """All-zero registers decode with an explicitly absent master voltage."""
        raw = self._base_regs()
        data = self.protocol.decode(raw)
        assert data.voltage == 0.0
        assert data.current == 0.0
        assert data.soc is None
        assert data.soh is None  # SOH 0 = not reported (#309)
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


class TestCapacityReconstruction:
    """Remaining capacity requires unique wrap and complete physical topology."""

    @pytest.mark.parametrize("count", [1, 2, 3, 5, 10])
    @pytest.mark.parametrize("soc", [0, 1, 10, 25, 50, 75, 99, 100])
    def test_empty_through_full_at_multiple_bank_sizes(self, count: int, soc: int) -> None:
        remaining = 280 * soc / 100
        slaves = [
            BatteryData(battery_index=i, current_capacity=remaining, max_capacity=280)
            for i in range(1, count)
        ]
        raw = {
            21: soc,
            26: round(remaining * count * 100) % 65536,
            27: (28000 * count) % 65536,
            33: 5600,
        }
        result = EG4MasterProtocol().decode_with_slaves(raw, slaves, topology_complete=True)
        assert result.current_capacity == pytest.approx(remaining)
        assert result.soc == soc

    @pytest.mark.parametrize("wrap", [1, 2, 3, 4])
    @pytest.mark.parametrize("offset", [-1, 0, 1])
    def test_each_wrap_boundary(self, wrap: int, offset: int) -> None:
        total_ticks = wrap * 65536 + offset
        total = total_ticks / 100
        count = 10
        per_slave = int(total / count)
        slaves = [
            BatteryData(battery_index=i, current_capacity=per_slave, max_capacity=280)
            for i in range(1, count)
        ]
        result = EG4MasterProtocol().decode_with_slaves(
            {26: total_ticks % 65536, 27: 280000 % 65536, 33: 5600},
            slaves,
            topology_complete=True,
        )
        assert result.current_capacity == pytest.approx(total - 9 * per_slave)
        assert result.soc == round((total - 9 * per_slave) / 280 * 100)

    def test_issue_384_requires_topology_attestation(self) -> None:
        slaves = [
            BatteryData(battery_index=i, soc=10, current_capacity=28, max_capacity=280)
            for i in (1, 2)
        ]
        raw = {21: 10, 26: 8400, 27: 18464, 33: 5600}
        protocol = EG4MasterProtocol()
        assert protocol.decode_with_slaves(raw, slaves).soc is None
        result = protocol.decode_with_slaves(raw, slaves, topology_complete=True)
        assert result.soc == 10
        assert result.current_capacity == 28

    def test_historical_firmware_example(self) -> None:
        result = EG4MasterProtocol().decode_with_slaves(
            {21: 79, 26: 464, 27: 18464, 33: 5600},
            [
                BatteryData(battery_index=1, current_capacity=224, max_capacity=280),
                BatteryData(battery_index=2, current_capacity=223, max_capacity=280),
            ],
            topology_complete=True,
        )
        assert result.current_capacity == 213
        assert result.soc == 76

    def test_empty_master_in_charged_bank(self) -> None:
        result = EG4MasterProtocol().decode_with_slaves(
            {21: 50, 26: 28000, 27: 56000, 33: 5600},
            [BatteryData(battery_index=1, current_capacity=280, max_capacity=280)],
            topology_complete=True,
        )
        assert result.current_capacity == 0
        assert result.soc == 0

    def test_mixed_designed_capacities_and_different_soc(self) -> None:
        slave = BatteryData(battery_index=1, current_capacity=50, max_capacity=100)
        result = EG4MasterProtocol().decode_with_slaves(
            {21: 69, 26: 26300, 27: 38000, 33: 5600}, [slave], topology_complete=True
        )
        assert result.current_capacity == 213
        assert result.soc == 76

    @pytest.mark.parametrize("missing", [26, 27, 33])
    def test_missing_register_is_unknown(self, missing: int) -> None:
        raw = {21: 10, 26: 2800, 27: 28000, 33: 5600}
        del raw[missing]
        result = EG4MasterProtocol().decode_with_slaves(raw, [], topology_complete=True)
        assert result.soc is None
        assert result.current_capacity is None

    @pytest.mark.parametrize(
        "remaining,designed",
        [
            (None, 280),
            (28, 0),
            (28, -1),
            (-1, 280),
            (281, 280),
            (float("nan"), 280),
            (float("inf"), 280),
            (28, float("inf")),
        ],
    )
    def test_invalid_slave_capacity_is_unknown(
        self,
        remaining: float | None,
        designed: float,
    ) -> None:
        slave = BatteryData(battery_index=1, current_capacity=remaining, max_capacity=designed)
        result = EG4MasterProtocol().decode_with_slaves(
            {21: 10, 26: 5600, 27: 56000, 33: 5600}, [slave], topology_complete=True
        )
        assert result.soc is None
        assert result.current_capacity is None

    @pytest.mark.parametrize(
        "raw",
        [
            {26: 8400, 27: 18464, 33: 5600},  # missing third pack
            {26: 10, 27: 56000, 33: 5600},  # negative master remainder
            {26: 60000, 27: 56000, 33: 5600},  # overfull master
            {26: 5600, 27: 56000, 33: 0},
            {26: -1, 27: 56000, 33: 5600},
            {26: 65536, 27: 56000, 33: 5600},
            {26: 5600, 27: -1, 33: 5600},
        ],
    )
    def test_inconsistent_evidence_is_unknown(self, raw: dict[int, int]) -> None:
        result = EG4MasterProtocol().decode_with_slaves(
            raw,
            [BatteryData(battery_index=1, current_capacity=28, max_capacity=280)],
            topology_complete=True,
        )
        assert result.soc is None
        assert result.current_capacity is None

    @pytest.mark.parametrize("indices", [[1, 1], [0, 1]])
    def test_duplicate_or_master_slave_identity_rejected(self, indices: list[int]) -> None:
        result = EG4MasterProtocol().decode_with_slaves(
            {26: 8400, 27: 18464, 33: 5600},
            [BatteryData(battery_index=i, current_capacity=28, max_capacity=280) for i in indices],
            topology_complete=True,
        )
        assert result.soc is None

    def test_ambiguous_large_master_rejected(self) -> None:
        result = EG4MasterProtocol().decode_with_slaves(
            {21: 10, 26: 8000, 27: 14464, 33: 16000}, [], topology_complete=True
        )
        assert result.soc is None
        assert result.current_capacity is None

    def test_full_capacity_modulo_cannot_establish_topology(self) -> None:
        # An unseen 655.36Ah pack contributes zero modulo 65536 at full charge.
        result = EG4MasterProtocol().decode_with_slaves(
            {21: 100, 26: 28000, 27: 28000, 33: 5600}, []
        )
        assert result.soc is None
        assert result.current_capacity is None

    def test_other_fields_preserved(self) -> None:
        raw = {
            21: 79,
            22: 5200,
            24: 22,
            26: 21300,
            27: 28000,
            28: 0x0211,
            30: 138,
            32: 100,
            33: 5600,
            41: 16,
        }
        raw.update(dict.fromkeys(range(113, 129), 3310))
        protocol = EG4MasterProtocol()
        basic = protocol.decode(raw)
        reconstructed = protocol.decode_with_slaves(raw, [], topology_complete=True)
        assert reconstructed.soc == 76
        assert reconstructed.current_capacity == 213
        assert reconstructed.voltage == basic.voltage == pytest.approx(52.96)
        assert reconstructed.temperature == basic.temperature == 22
        assert reconstructed.firmware_version == basic.firmware_version == "2.17"
        assert reconstructed.cycle_count == basic.cycle_count == 138
        assert reconstructed.soh == basic.soh == 100

    def test_unwrap_rejects_nominal_capacity_ambiguity(self) -> None:
        assert EG4MasterProtocol.unwrap_capacity_register(8400, 3, 280) is None
        assert EG4MasterProtocol.unwrap_capacity_register(42000, 3, 280) == 420
        assert EG4MasterProtocol.unwrap_capacity_register(0, 1, 280) == 0
        assert EG4MasterProtocol.unwrap_capacity_register(28000, 1, 280) == 280

    @pytest.mark.parametrize("count,designed", [(0, 280), (-1, 280), (3, 0), (3, -1)])
    def test_unwrap_invalid_bounds(self, count: int, designed: float) -> None:
        assert EG4MasterProtocol.unwrap_capacity_register(464, count, designed) is None

    def test_subtraction_rejects_negative_result(self) -> None:
        assert EG4MasterProtocol.compute_master_remaining(400, [210, 200]) is None
        assert EG4MasterProtocol.compute_master_remaining(0, [0]) == 0
