"""EG4 master battery protocol (firmware-derived register map).

Used by the master battery (unit ID 1) on the RS485 daisy chain.
Register map derived from Ghidra decompilation of HC32 BMS firmware
function FUN_0001cf78.

Key differences from slave protocol:
  - Regs 0-18 are ALL ZEROS (data starts at reg 19)
  - Current (reg 23) is AGGREGATE across all batteries
  - Voltage (reg 22) is minimum across all batteries
  - Temperature (reg 24) is maximum across all batteries
  - Cycle count (reg 30) is maximum across all batteries
  - Cell voltages at regs 113-128 (not regs 2-17)
  - Designed capacity at reg 33 uses /20 (not /10)
  - SOC at reg 26 uses /10
  - No device info registers (105+ timeout)
"""

from __future__ import annotations

import struct

from pylxpweb.constants.scaling import ScaleFactor
from pylxpweb.transports.data import BatteryData

from .base import BatteryProtocol, BatteryRegister, BatteryRegisterBlock

# Runtime registers (19-41)
_RUNTIME_REGISTERS = (
    BatteryRegister(19, "status", ScaleFactor.SCALE_NONE),
    BatteryRegister(20, "protection", ScaleFactor.SCALE_NONE),
    BatteryRegister(21, "error_balance", ScaleFactor.SCALE_NONE),
    BatteryRegister(22, "voltage", ScaleFactor.SCALE_100, unit="V"),
    BatteryRegister(23, "current", ScaleFactor.SCALE_100, signed=True, unit="A"),
    BatteryRegister(24, "temperature", ScaleFactor.SCALE_NONE, signed=True, unit="\u00b0C"),
    BatteryRegister(26, "soc", ScaleFactor.SCALE_10, unit="%"),
    BatteryRegister(28, "firmware_version", ScaleFactor.SCALE_NONE),
    BatteryRegister(30, "cycle_count", ScaleFactor.SCALE_NONE),
    BatteryRegister(32, "soh", ScaleFactor.SCALE_NONE, unit="%"),
    BatteryRegister(33, "designed_capacity_raw", ScaleFactor.SCALE_NONE, unit="Ah"),
    BatteryRegister(34, "warning", ScaleFactor.SCALE_NONE),
    BatteryRegister(37, "max_cell_voltage", ScaleFactor.SCALE_1000, unit="V"),
    BatteryRegister(38, "min_cell_voltage", ScaleFactor.SCALE_1000, unit="V"),
    BatteryRegister(39, "max_cell_index", ScaleFactor.SCALE_NONE),
    BatteryRegister(40, "min_cell_index", ScaleFactor.SCALE_NONE),
    BatteryRegister(41, "num_cells", ScaleFactor.SCALE_NONE),
)

_RUNTIME_BLOCK = BatteryRegisterBlock(start=19, count=23, registers=_RUNTIME_REGISTERS)
_CELL_BLOCK = BatteryRegisterBlock(start=113, count=16, registers=())


def _signed_int16(raw: int) -> int:
    """Interpret a raw unsigned 16-bit value as signed int16.

    Args:
        raw: Unsigned 16-bit register value.

    Returns:
        Signed integer in range [-32768, 32767].
    """
    result: int = struct.unpack("h", struct.pack("H", raw & 0xFFFF))[0]
    return result


class EG4MasterProtocol(BatteryProtocol):
    """Firmware-derived register map for master battery (unit ID 1).

    The master battery aggregates data from all batteries on the chain:
    - Current = sum of all batteries
    - Voltage = minimum across all batteries
    - Temperature = maximum across all batteries
    - Cycle count = maximum across all batteries
    """

    name = "eg4_master"
    register_blocks = [_RUNTIME_BLOCK, _CELL_BLOCK]

    def decode(self, raw_regs: dict[int, int], battery_index: int = 0) -> BatteryData:
        """Decode master battery registers into BatteryData.

        Args:
            raw_regs: Dict mapping register address to raw 16-bit value.
            battery_index: 0-based index of the battery in the bank.

        Returns:
            BatteryData with all values properly scaled.
        """
        # Voltage: reg 22 /100
        voltage = self.decode_register(
            BatteryRegister(22, "voltage", ScaleFactor.SCALE_100, unit="V"),
            raw_regs.get(22, 0),
        )

        # Current: reg 23 /100, signed (AGGREGATE across all batteries)
        current = self.decode_register(
            BatteryRegister(23, "current", ScaleFactor.SCALE_100, signed=True, unit="A"),
            raw_regs.get(23, 0),
        )

        # Temperature: reg 24, direct (max across all batteries), signed
        temperature = float(_signed_int16(raw_regs.get(24, 0)))

        # SOC: reg 26 /10, truncate to int
        soc_raw = raw_regs.get(26, 0)
        soc = int(soc_raw / 10.0)

        # SOH: reg 32, direct
        soh = raw_regs.get(32, 100)

        # Cycle count: reg 30, direct (max across all batteries)
        cycle_count = raw_regs.get(30, 0)

        # Designed capacity: reg 33 /20
        max_capacity = raw_regs.get(33, 0) / 20.0

        # Number of cells: reg 41
        num_cells = raw_regs.get(41, 0)

        # Cell voltages: regs 113-128, /1000
        cell_voltages = [raw_regs.get(113 + i, 0) / 1000.0 for i in range(num_cells)]
        non_zero_cells = [v for v in cell_voltages if v > 0]

        # Max/min cell voltage: regs 37/38 /1000
        max_cell_v = raw_regs.get(37, 0) / 1000.0
        min_cell_v = raw_regs.get(38, 0) / 1000.0

        # Max/min cell index: regs 39/40, 0-based -> 1-based for BatteryData
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
            min_cell_voltage=(
                min_cell_v if min_cell_v > 0 else (min(non_zero_cells) if non_zero_cells else 0.0)
            ),
            max_cell_voltage=(
                max_cell_v if max_cell_v > 0 else (max(non_zero_cells) if non_zero_cells else 0.0)
            ),
            min_cell_temperature=temperature,
            max_cell_temperature=temperature,
            max_cell_num_voltage=max_cell_index + 1 if max_cell_index > 0 or num_cells > 0 else 0,
            min_cell_num_voltage=min_cell_index + 1 if min_cell_index > 0 or num_cells > 0 else 0,
            firmware_version=firmware_version,
            status=status,
            fault_code=fault_code,
            warning_code=warning_code,
        )
