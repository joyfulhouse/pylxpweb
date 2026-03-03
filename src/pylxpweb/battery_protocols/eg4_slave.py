"""EG4 slave battery protocol (standard EG4-LL register map).

Used by batteries with unit ID 2+ on the RS485 daisy chain.
Register map sourced from ricardocello's eg4_waveshare.py.

Register layout:
  - Regs 0-38: Runtime state (voltage, current, cells, temps, SOC, etc.)
  - Regs 105-127: Device info (model, firmware, serial)
"""

from __future__ import annotations

from pylxpweb.constants.scaling import ScaleFactor
from pylxpweb.transports.data import BatteryData

from .base import (
    BatteryProtocol,
    BatteryRegister,
    BatteryRegisterBlock,
    decode_ascii,
    signed_int16,
)

# Runtime registers (0-38)
_RUNTIME_REGISTERS = (
    BatteryRegister(0, "voltage", ScaleFactor.SCALE_100, unit="V"),
    BatteryRegister(1, "current", ScaleFactor.SCALE_100, signed=True, unit="A"),
    # Cell voltages 2-17 handled dynamically based on num_cells (reg 36)
    BatteryRegister(18, "pcb_temp", ScaleFactor.SCALE_NONE, signed=True, unit="\u00b0C"),
    BatteryRegister(19, "avg_temp", ScaleFactor.SCALE_NONE, signed=True, unit="\u00b0C"),
    BatteryRegister(20, "max_temp", ScaleFactor.SCALE_NONE, signed=True, unit="\u00b0C"),
    BatteryRegister(21, "remaining_capacity", ScaleFactor.SCALE_NONE, unit="Ah"),
    BatteryRegister(22, "max_charge_current", ScaleFactor.SCALE_NONE, unit="A"),
    BatteryRegister(23, "soh", ScaleFactor.SCALE_NONE, unit="%"),
    BatteryRegister(24, "soc", ScaleFactor.SCALE_NONE, unit="%"),
    BatteryRegister(25, "status", ScaleFactor.SCALE_NONE),
    BatteryRegister(26, "warning", ScaleFactor.SCALE_NONE),
    BatteryRegister(27, "protection", ScaleFactor.SCALE_NONE),
    BatteryRegister(28, "error", ScaleFactor.SCALE_NONE),
    # Regs 29-30: cycle count (32-bit BE), handled in decode()
    # Regs 31-32: full capacity (32-bit), not used in basic decode
    BatteryRegister(36, "num_cells", ScaleFactor.SCALE_NONE),
    BatteryRegister(37, "designed_capacity", ScaleFactor.SCALE_10, unit="Ah"),
    BatteryRegister(38, "balance_bitmap", ScaleFactor.SCALE_NONE),
)

_RUNTIME_BLOCK = BatteryRegisterBlock(start=0, count=39, registers=_RUNTIME_REGISTERS)
_INFO_BLOCK = BatteryRegisterBlock(start=105, count=23, registers=())


class EG4SlaveProtocol(BatteryProtocol):
    """Standard EG4-LL register map for slave batteries (unit ID 2+).

    Decodes runtime registers (0-38) and device info registers (105-127)
    into a BatteryData object with all values properly scaled.
    """

    name = "eg4_slave"
    register_blocks = (_RUNTIME_BLOCK, _INFO_BLOCK)

    def decode(self, raw_regs: dict[int, int], battery_index: int = 0) -> BatteryData:
        """Decode slave battery registers into BatteryData.

        Args:
            raw_regs: Dict mapping register address to raw 16-bit value.
            battery_index: 0-based index of the battery in the bank.

        Returns:
            BatteryData with all values properly scaled.
        """
        voltage_reg = self._reg("voltage")
        current_reg = self._reg("current")
        capacity_reg = self._reg("designed_capacity")

        voltage = self.decode_register(voltage_reg, raw_regs.get(voltage_reg.address, 0))
        current = self.decode_register(current_reg, raw_regs.get(current_reg.address, 0))

        num_cells = raw_regs.get(36, 0)
        cell_voltages, min_cell_v, max_cell_v = self.decode_cell_voltages(
            raw_regs, start_address=2, num_cells=num_cells
        )

        pcb_temp = signed_int16(raw_regs.get(18, 0))
        max_temp = signed_int16(raw_regs.get(20, 0))

        soc = raw_regs.get(24, 0)
        soh = raw_regs.get(23, 100)
        remaining_capacity = float(raw_regs.get(21, 0))
        max_charge_current = float(raw_regs.get(22, 0))
        max_capacity = self.decode_register(capacity_reg, raw_regs.get(capacity_reg.address, 0))

        # Cycle count (regs 29-30): 32-bit big-endian
        cycle_count = (raw_regs.get(29, 0) << 16) | raw_regs.get(30, 0)

        # Status/warning/protection bitfields
        status = raw_regs.get(25, 0)
        warning = raw_regs.get(26, 0)
        fault = raw_regs.get(27, 0)

        # Device info (if available in register map)
        model = decode_ascii(raw_regs, 105, 12)
        firmware = decode_ascii(raw_regs, 117, 3)
        serial = decode_ascii(raw_regs, 120, 8)

        return BatteryData(
            battery_index=battery_index,
            serial_number=serial,
            voltage=voltage,
            current=current,
            soc=soc,
            soh=soh,
            temperature=float(max_temp),
            max_capacity=max_capacity,
            current_capacity=remaining_capacity if remaining_capacity > 0 else None,
            cycle_count=cycle_count,
            cell_count=num_cells,
            cell_voltages=cell_voltages,
            min_cell_voltage=min_cell_v,
            max_cell_voltage=max_cell_v,
            min_cell_temperature=float(pcb_temp),
            max_cell_temperature=float(max_temp),
            charge_current_limit=max_charge_current,
            model=model,
            firmware_version=firmware,
            status=status,
            warning_code=warning,
            fault_code=fault,
        )
