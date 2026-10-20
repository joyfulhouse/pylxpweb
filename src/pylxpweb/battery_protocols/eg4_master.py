"""EG4 master battery protocol (firmware-derived register map).

Used by the master battery (unit ID 1) on the RS485 daisy chain.
Register map derived from Ghidra decompilation of HC32 BMS firmware
function FUN_0001cf78.

Key differences from slave protocol:
  - Regs 0-18 are ALL ZEROS (data starts at reg 19)
  - SOC at reg 21 (capacity-weighted aggregate across ALL batteries)
  - Current (reg 23) is AGGREGATE (sum) across all batteries
  - Voltage (reg 22) is minimum across all batteries
  - Temperature (reg 24) is maximum across all batteries
  - Cycle count (reg 30) is maximum across all batteries
  - Cell voltages at regs 113-128 (not regs 2-17)
  - Designed capacity at reg 33 uses /20 (not /10)
  - Regs 26/27 = total remaining/full capacity ×100 (overflow uint16)
  - No device info registers (slave regs 105+ are status flags, not ASCII)
  - No per-cell temperature registers (only aggregate max at reg 24)
  - No packed temp registers like slave regs 33-35

Temperature limitations (master RS485):
  - Only reg 24 is available: aggregate MAX across all batteries on the chain.
  - No min temperature register exists. Probed regs 0-255; confirmed no hidden data.
  - Per-cell NTC readings are only available via CAN bus (cloud API).
  - min_cell_temperature and max_cell_temperature are both set to reg 24 value.

Master pack voltage is derived only from a complete, usable cell-voltage set.
Register 22 is a bank minimum, so it is never exposed as the master's own
voltage; when the cells are unavailable, voltage is the explicit 0.0 absent
sentinel instead.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from pylxpweb.constants.scaling import ScaleFactor
from pylxpweb.transports.data import BatteryData

from .base import (
    BatteryProtocol,
    BatteryRegister,
    BatteryRegisterBlock,
    signed_int16,
)

# Runtime registers (19-41)
_RUNTIME_REGISTERS = (
    BatteryRegister(19, "status", ScaleFactor.SCALE_NONE),
    BatteryRegister(20, "protection", ScaleFactor.SCALE_NONE),
    BatteryRegister(21, "soc", ScaleFactor.SCALE_NONE, unit="%"),
    # Named for what it is, not for the field it used to populate. Keeping this
    # metadata distinct makes _reg("voltage") fail instead of relabeling an
    # aggregate as master data, and supplies the scale for the physical
    # cross-check below (#249). Register-block start/count, not this metadata,
    # determines what the transport reads.
    BatteryRegister(22, "bank_min_voltage", ScaleFactor.SCALE_100, unit="V"),
    BatteryRegister(23, "current", ScaleFactor.SCALE_100, signed=True, unit="A"),
    BatteryRegister(24, "temperature", ScaleFactor.SCALE_NONE, signed=True, unit="\u00b0C"),
    BatteryRegister(28, "firmware_version", ScaleFactor.SCALE_NONE),
    BatteryRegister(30, "cycle_count", ScaleFactor.SCALE_NONE),
    BatteryRegister(32, "soh", ScaleFactor.SCALE_NONE, unit="%"),
    BatteryRegister(33, "designed_capacity_raw", ScaleFactor.SCALE_NONE, unit="Ah"),
    BatteryRegister(26, "total_remaining_raw", ScaleFactor.SCALE_NONE),
    BatteryRegister(27, "total_full_raw", ScaleFactor.SCALE_NONE),
    BatteryRegister(34, "warning", ScaleFactor.SCALE_NONE),
    BatteryRegister(37, "max_cell_voltage", ScaleFactor.SCALE_1000, unit="V"),
    BatteryRegister(38, "min_cell_voltage", ScaleFactor.SCALE_1000, unit="V"),
    BatteryRegister(39, "max_cell_index", ScaleFactor.SCALE_NONE),
    BatteryRegister(40, "min_cell_index", ScaleFactor.SCALE_NONE),
    BatteryRegister(41, "num_cells", ScaleFactor.SCALE_NONE),
)

_RUNTIME_BLOCK = BatteryRegisterBlock(start=19, count=23, registers=_RUNTIME_REGISTERS)
_CELL_BLOCK = BatteryRegisterBlock(start=113, count=16, registers=())

# Sanity bounds against corrupt registers, not LiFePO4 specification limits.
_MIN_PLAUSIBLE_CELL_V = 1.0
_MAX_PLAUSIBLE_CELL_V = 5.0
# Stops a transient count such as 1 from turning a truncated prefix of the
# fixed 16-register cell block into a pack voltage. The only EG4 pack this repo
# documents is 16S (WP-16/280, see eg4_slave); the floor is set one below that
# rather than at 16 so a 15S variant we have not seen is not rejected outright.
# That looseness is deliberate and costs nothing: a 16S pack whose count is
# corrupted to 15 is caught by the cross-checks below, not by this bound.
_MIN_PLAUSIBLE_CELL_COUNT = 15
_MAX_PLAUSIBLE_CELL_COUNT = _CELL_BLOCK.count
# Reg 22 and the cell block are sampled separately. Half a volt accommodates
# that skew while still rejecting one-or-more-cell truncation by a wide margin.
_BANK_MIN_VOLTAGE_TOLERANCE_V = 0.5


def _derive_master_voltage(
    cell_voltages: list[float],
    cell_count: int,
    bank_min_voltage: float = 0.0,
    following_cell_voltage: float = 0.0,
) -> float:
    """Derive master pack voltage from a complete, plausible cell set.

    Register 22 is the minimum pack voltage across the bank, not the master's
    own pack voltage. A missing, partial, zeroed, or corrupt cell set therefore
    returns the schema's explicit absent sentinel rather than that aggregate.
    A genuinely collapsed cell below 1.0 V also makes the whole pack voltage
    absent by design: cell-level canaries retain the fault signal, while a pack
    sum containing that cell would turn a serious fault into a plausible but
    misleading low voltage.

    Args:
        cell_voltages: Decoded individual cell voltages in volts.
        cell_count: Expected cell count from register 41.
        bank_min_voltage: Minimum pack voltage across the bank from register 22.
        following_cell_voltage: Cell-block value immediately after the declared
            cell count, or zero when the count consumes the full block.

    Returns:
        Rounded sum of all cells, or 0.0 when the cell set is unusable.
    """
    if not _MIN_PLAUSIBLE_CELL_COUNT <= cell_count <= _MAX_PLAUSIBLE_CELL_COUNT:
        return 0.0
    # decode_cell_voltages currently returns exactly cell_count entries. Keep
    # this length check as defence in depth for alternate decoders/callers; the
    # real register protections are the bounds and cross-checks below.
    if len(cell_voltages) != cell_count:
        return 0.0
    if not all(_MIN_PLAUSIBLE_CELL_V <= value <= _MAX_PLAUSIBLE_CELL_V for value in cell_voltages):
        return 0.0
    # The physical block always has 16 registers. A plausible cell immediately
    # after the declared count proves reg 41 under-reported, even when reg 22 is
    # absent and cannot provide the stronger physical cross-check.
    if _MIN_PLAUSIBLE_CELL_V <= following_cell_voltage <= _MAX_PLAUSIBLE_CELL_V:
        return 0.0

    derived_voltage = round(sum(cell_voltages), 2)
    # The master is one of the packs contributing to reg 22's bank minimum, so
    # its voltage cannot be materially below that minimum. This catches corrupt
    # but superficially plausible counts such as 15 or 1 (#249).
    if bank_min_voltage > 0 and derived_voltage + _BANK_MIN_VOLTAGE_TOLERANCE_V < bank_min_voltage:
        return 0.0
    return derived_voltage


class EG4MasterProtocol(BatteryProtocol):
    """Firmware-derived register map for master battery (unit ID 1).

    The master battery aggregates data from slave batteries on the chain:
    - SOC (reg 21) = capacity-weighted aggregate across ALL batteries
    - Current (reg 23) = sum of all batteries
    - Voltage (reg 22) = minimum across all batteries
    - Temperature (reg 24) = maximum across all batteries
    - Cycle count (reg 30) = maximum across all batteries
    - Total remaining (reg 26) = sum of all remaining capacity × 100 (overflows uint16)
    - Total full (reg 27) = sum of all designed capacity × 100 (overflows uint16)

    Master individual SOC can be back-calculated from reg 26/27 after uint16 overflow
    unwrap, by subtracting slave remaining capacities from the total.
    See ``unwrap_capacity_register`` and ``compute_master_remaining``.
    """

    name = "eg4_master"
    register_blocks = (_RUNTIME_BLOCK, _CELL_BLOCK)

    @staticmethod
    def unwrap_capacity_register(
        raw_reg: int,
        num_batteries: int,
        designed_capacity_ah: float,
        *,
        minimum_capacity_ah: float = 0.0,
    ) -> float | None:
        """Return the unique uint16 capacity candidate within the supplied bounds.

        Nominal capacity alone cannot select a remaining-capacity wrap count.
        The default lower bound is zero; ambiguous or invalid inputs return None.
        ``num_batteries * designed_capacity_ah`` is the strict upper bound.
        """
        lower = Decimal(str(minimum_capacity_ah)) * 100
        upper = Decimal(str(designed_capacity_ah)) * num_batteries * 100
        if (
            not 0 <= raw_reg <= 65535
            or num_batteries <= 0
            or not lower.is_finite()
            or not upper.is_finite()
            or upper <= 0
            or lower < 0
            or lower > upper
        ):
            return None
        # Work in register ticks to avoid floating-point boundary errors.
        first = max(0, int(((lower - raw_reg) / 65536).to_integral_value(rounding="ROUND_CEILING")))
        last = int(((upper - raw_reg) / 65536).to_integral_value(rounding="ROUND_FLOOR"))
        if first != last:
            return None
        return (raw_reg + first * 65536) / 100.0

    @staticmethod
    def compute_master_remaining(
        total_remaining_ah: float,
        slave_remaining: list[float],
    ) -> float | None:
        """Subtract known slave capacities, rejecting invalid or negative results."""
        values = [Decimal(str(value)) for value in [total_remaining_ah, *slave_remaining]]
        if any(not value.is_finite() or value < 0 for value in values):
            return None
        remaining = values[0] - sum(values[1:])
        return float(remaining) if remaining >= 0 else None

    def decode(self, raw_regs: dict[int, int], battery_index: int = 0) -> BatteryData:
        """Decode master battery registers into BatteryData.

        Register 22 is never used as the master's own voltage because it is
        the minimum across the whole bank. It can look correct in a genuine
        single-battery bank, but the protocol cannot distinguish that case
        from a multi-battery bank whose slaves failed to read. A plausible
        aggregate mislabeled as master data is worse than the explicit 0.0
        absent sentinel, so only a complete plausible cell set is trusted
        (#249).

        Args:
            raw_regs: Dict mapping register address to raw 16-bit value.
            battery_index: 0-based index of the battery in the bank.

        Returns:
            BatteryData with all values properly scaled.
        """
        current_reg = self._reg("current")
        max_cell_reg = self._reg("max_cell_voltage")
        min_cell_reg = self._reg("min_cell_voltage")

        current = self.decode_register(current_reg, raw_regs.get(current_reg.address, 0))

        temperature = float(signed_int16(raw_regs.get(24, 0)))

        # Register 21 is bank SOC, not an individual master measurement.
        # Only decode_with_slaves() with complete evidence can recover master SOC.
        soh_raw = raw_regs.get(32, 0)
        soh = soh_raw if soh_raw > 0 else None  # 0 = not reported (#309)
        cycle_count = raw_regs.get(30, 0)

        # Designed capacity: reg 33 /20 (unique to master protocol)
        max_capacity = raw_regs.get(33, 0) / 20.0

        num_cells = raw_regs.get(41, 0)
        cell_voltages, fallback_min, fallback_max = self.decode_cell_voltages(
            raw_regs, start_address=113, num_cells=num_cells
        )
        bank_min_reg = self._reg("bank_min_voltage")
        bank_min_voltage = self.decode_register(bank_min_reg, raw_regs.get(bank_min_reg.address, 0))
        following_cell_voltage = 0.0
        if 0 <= num_cells < _CELL_BLOCK.count:
            following_cell_voltage = raw_regs.get(_CELL_BLOCK.start + num_cells, 0) / 1000.0
        voltage = _derive_master_voltage(
            cell_voltages,
            num_cells,
            bank_min_voltage=bank_min_voltage,
            following_cell_voltage=following_cell_voltage,
        )

        # Prefer dedicated max/min cell voltage registers; fall back to computed values
        max_cell_v = self.decode_register(max_cell_reg, raw_regs.get(max_cell_reg.address, 0))
        min_cell_v = self.decode_register(min_cell_reg, raw_regs.get(min_cell_reg.address, 0))

        max_cell_index = raw_regs.get(39, 0)
        min_cell_index = raw_regs.get(40, 0)

        # Firmware version: reg 28, packed BCD (high_byte.low_byte)
        fw_raw = raw_regs.get(28, 0)
        fw_high = (fw_raw >> 8) & 0xFF
        fw_low = fw_raw & 0xFF
        firmware_version = f"{fw_high}.{fw_low:02d}" if fw_raw else ""

        # Status/protection/warning bitfields
        status = raw_regs.get(19, 0)
        fault_code = raw_regs.get(20, 0)
        warning_code = raw_regs.get(34, 0)

        return BatteryData(
            battery_index=battery_index,
            voltage=voltage,
            current=current,
            soc=None,
            soh=soh,
            temperature=temperature,
            max_capacity=max_capacity,
            cycle_count=cycle_count,
            cell_count=num_cells,
            cell_voltages=cell_voltages,
            min_cell_voltage=min_cell_v if min_cell_v > 0 else fallback_min,
            max_cell_voltage=max_cell_v if max_cell_v > 0 else fallback_max,
            min_cell_temperature=temperature,
            max_cell_temperature=temperature,
            max_cell_num_voltage=max_cell_index + 1 if max_cell_index > 0 or num_cells > 0 else 0,
            min_cell_num_voltage=min_cell_index + 1 if min_cell_index > 0 or num_cells > 0 else 0,
            firmware_version=firmware_version,
            status=status,
            fault_code=fault_code,
            warning_code=warning_code,
        )

    def decode_with_slaves(
        self,
        raw_regs: dict[int, int],
        slave_data: list[BatteryData],
        battery_index: int = 0,
        *,
        topology_complete: bool = False,
    ) -> BatteryData:
        """Recover individual master capacity only with complete, consistent evidence.

        ``topology_complete`` attests that every slave in the physical bank is
        represented. Discovery alone cannot establish this: an unseen pack may
        alias register 27 after wrapping. Unknown topology, missing capacities,
        inconsistent full capacity, and ambiguous remaining capacity leave SOC
        and current_capacity as None. Valid empty packs retain zero.
        """
        data = self.decode(raw_regs, battery_index)
        if not topology_complete or any(address not in raw_regs for address in (26, 27, 33)):
            return data
        if any(not 0 <= raw_regs[address] <= 65535 for address in (26, 27, 33)):
            return data
        if data.max_capacity <= 0:
            return data
        indices = [slave.battery_index for slave in slave_data]
        if len(set(indices)) != len(indices) or battery_index in indices:
            return data

        full = Decimal(str(data.max_capacity))
        slave_remaining: list[float] = []
        for slave in slave_data:
            designed = Decimal(str(slave.max_capacity))
            if slave.current_capacity is None:
                return data
            remaining = Decimal(str(slave.current_capacity))
            if (
                not designed.is_finite()
                or not remaining.is_finite()
                or designed <= 0
                or remaining < 0
                or remaining > designed
            ):
                return data
            full += designed
            slave_remaining.append(slave.current_capacity)

        full_ticks = full * 100
        if full_ticks != full_ticks.to_integral_value() or int(full_ticks) % 65536 != raw_regs[27]:
            return data
        lower = sum(Decimal(str(value)) for value in slave_remaining)
        upper = lower + Decimal(str(data.max_capacity))
        total = self.unwrap_capacity_register(
            raw_regs[26], 1, float(upper), minimum_capacity_ah=float(lower)
        )
        if total is None:
            return data
        remaining_ah = self.compute_master_remaining(total, slave_remaining)
        if remaining_ah is None or remaining_ah > data.max_capacity:
            return data
        return replace(
            data,
            soc=round(remaining_ah / data.max_capacity * 100),
            current_capacity=remaining_ah,
        )
