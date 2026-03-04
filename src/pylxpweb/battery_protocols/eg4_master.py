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
"""

from __future__ import annotations

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
    BatteryRegister(22, "voltage", ScaleFactor.SCALE_100, unit="V"),
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
    ) -> float:
        """Unwrap a uint16-overflowed capacity register to get true Ah value.

        The firmware stores ``total_capacity_Ah * 100`` as uint16, which
        overflows for multi-battery systems.  We find the overflow count N
        such that ``(raw_reg + N * 65536) / 100`` falls within the expected
        physical range ``[0, num_batteries * designed_capacity_ah * 1.05]``.

        Uses floor-based N estimation with fallback to N-1 to handle both
        near-full-capacity and low-SOC cases correctly.

        Args:
            raw_reg: Raw uint16 register value (reg 26 or 27).
            num_batteries: Total number of batteries on the chain.
            designed_capacity_ah: Designed capacity per battery in Ah.

        Returns:
            Total capacity in Ah, or 0.0 if inputs are invalid.
        """
        if num_batteries <= 0 or designed_capacity_ah <= 0:
            return 0.0

        max_expected = num_batteries * designed_capacity_ah
        upper_bound = max_expected * 1.05
        n = int(max_expected * 100 / 65536)

        for candidate_n in [n, max(0, n - 1)]:
            result = (raw_reg + candidate_n * 65536) / 100.0
            if 0 <= result <= upper_bound:
                return result

        return 0.0

    @staticmethod
    def compute_master_remaining(
        total_remaining_ah: float,
        slave_remaining: list[float],
    ) -> float:
        """Compute master battery's individual remaining capacity.

        Subtracts all slave remaining capacities from the bank total.

        Args:
            total_remaining_ah: Total remaining Ah from unwrapped reg 26.
            slave_remaining: List of slave remaining capacities in Ah.

        Returns:
            Master's own remaining capacity in Ah, clamped to >= 0.
        """
        return max(0.0, total_remaining_ah - sum(slave_remaining))

    def decode(self, raw_regs: dict[int, int], battery_index: int = 0) -> BatteryData:
        """Decode master battery registers into BatteryData.

        Args:
            raw_regs: Dict mapping register address to raw 16-bit value.
            battery_index: 0-based index of the battery in the bank.

        Returns:
            BatteryData with all values properly scaled.
        """
        voltage_reg = self._reg("voltage")
        current_reg = self._reg("current")
        max_cell_reg = self._reg("max_cell_voltage")
        min_cell_reg = self._reg("min_cell_voltage")

        voltage = self.decode_register(voltage_reg, raw_regs.get(voltage_reg.address, 0))
        current = self.decode_register(current_reg, raw_regs.get(current_reg.address, 0))

        temperature = float(signed_int16(raw_regs.get(24, 0)))

        # SOC: reg 21, direct % (capacity-weighted aggregate across all batteries)
        # Firmware: total_remaining / total_full * 100 via FUN_190BA
        # For master's individual SOC, use decode_with_slaves() instead
        soc = raw_regs.get(21, 0)
        soh = raw_regs.get(32, 100)
        cycle_count = raw_regs.get(30, 0)

        # Designed capacity: reg 33 /20 (unique to master protocol)
        max_capacity = raw_regs.get(33, 0) / 20.0

        # Total remaining/full from reg 26/27 (overflow uint16, stored for decode_with_slaves)
        self._last_total_remaining_raw = raw_regs.get(26, 0)
        self._last_total_full_raw = raw_regs.get(27, 0)

        num_cells = raw_regs.get(41, 0)
        cell_voltages, fallback_min, fallback_max = self.decode_cell_voltages(
            raw_regs, start_address=113, num_cells=num_cells
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
            soc=soc,
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
    ) -> BatteryData:
        """Decode master registers with slave context for individual SOC.

        Uses reg 26/27 overflow unwrap and slave remaining capacities to
        back-calculate the master battery's own remaining capacity and SOC,
        instead of reporting the aggregate values.

        Args:
            raw_regs: Dict mapping register address to raw 16-bit value.
            slave_data: List of decoded BatteryData from slave batteries.
            battery_index: 0-based index of the battery in the bank.

        Returns:
            BatteryData with master's individual SOC and remaining capacity.
        """
        data = self.decode(raw_regs, battery_index)

        reg26 = raw_regs.get(26, 0)
        reg27 = raw_regs.get(27, 0)
        if reg26 == 0 and reg27 == 0:
            return data

        num_batteries = 1 + len(slave_data)
        designed_ah = data.max_capacity if data.max_capacity > 0 else 280.0

        total_remaining = self.unwrap_capacity_register(reg26, num_batteries, designed_ah)

        if total_remaining <= 0:
            return data

        slave_remaining = [
            s.current_capacity if s.current_capacity is not None else 0.0 for s in slave_data
        ]
        master_remaining = self.compute_master_remaining(total_remaining, slave_remaining)

        master_soc = round(master_remaining / designed_ah * 100) if designed_ah > 0 else 0
        master_soc = max(0, min(100, master_soc))

        # Compute master voltage from cell voltages (more accurate than reg 22 = MIN all)
        voltage = data.voltage
        if data.cell_voltages:
            cell_sum = sum(data.cell_voltages)
            if cell_sum > 0:
                voltage = round(cell_sum, 2)

        return BatteryData(
            battery_index=data.battery_index,
            voltage=voltage,
            current=data.current,
            soc=master_soc,
            soh=data.soh,
            temperature=data.temperature,
            max_capacity=data.max_capacity,
            current_capacity=master_remaining,
            cycle_count=data.cycle_count,
            cell_count=data.cell_count,
            cell_voltages=data.cell_voltages,
            min_cell_voltage=data.min_cell_voltage,
            max_cell_voltage=data.max_cell_voltage,
            min_cell_temperature=data.min_cell_temperature,
            max_cell_temperature=data.max_cell_temperature,
            max_cell_num_voltage=data.max_cell_num_voltage,
            min_cell_num_voltage=data.min_cell_num_voltage,
            firmware_version=data.firmware_version,
            status=data.status,
            fault_code=data.fault_code,
            warning_code=data.warning_code,
        )
