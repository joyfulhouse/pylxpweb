# Battery RS485 Protocol Support — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add direct RS485 battery reading as the highest-priority data source for battery BMS data, with extensible protocol support for EG4, PYLON, Hanchu, and future protocols.

**Architecture:** Protocol + Transport separation. `BatteryProtocol` subclasses define register maps as pure data (no I/O). `BatteryModbusTransport` handles physical Modbus TCP/RTU communication to the battery RS485 bus. The transport uses protocol definitions to decode raw registers into `BatteryData` objects (the existing transport-agnostic dataclass). Priority: RS485 > Inverter 5000+ > BMS registers.

**Tech Stack:** pymodbus (already a dependency), dataclasses, existing `ScaleFactor`/`BatteryData` infrastructure.

**Design Doc:** `docs/plans/2026-03-02-battery-protocol-design.md`
**Protocol Reference:** `docs/BATTERY_RS485_PROTOCOLS.md`

---

## Task 1: BatteryProtocol Base Classes

**Files:**
- Create: `src/pylxpweb/battery_protocols/__init__.py`
- Create: `src/pylxpweb/battery_protocols/base.py`
- Test: `tests/unit/battery_protocols/__init__.py`
- Test: `tests/unit/battery_protocols/test_base.py`

**Step 1: Write the failing test**

```python
# tests/unit/battery_protocols/__init__.py
# (empty)

# tests/unit/battery_protocols/test_base.py
"""Tests for battery protocol base classes."""
from __future__ import annotations

import struct

import pytest

from pylxpweb.battery_protocols.base import (
    BatteryRegister,
    BatteryRegisterBlock,
    BatteryProtocol,
)
from pylxpweb.constants.scaling import ScaleFactor


class TestBatteryRegister:
    """Tests for BatteryRegister dataclass."""

    def test_basic_register(self) -> None:
        reg = BatteryRegister(
            address=22, name="voltage", scale=ScaleFactor.SCALE_100, unit="V"
        )
        assert reg.address == 22
        assert reg.name == "voltage"
        assert reg.scale == ScaleFactor.SCALE_100
        assert reg.signed is False
        assert reg.unit == "V"

    def test_signed_register(self) -> None:
        reg = BatteryRegister(
            address=23, name="current", scale=ScaleFactor.SCALE_100, signed=True, unit="A"
        )
        assert reg.signed is True

    def test_frozen(self) -> None:
        reg = BatteryRegister(address=0, name="x", scale=ScaleFactor.SCALE_NONE)
        with pytest.raises(AttributeError):
            reg.address = 5  # type: ignore[misc]


class TestBatteryRegisterBlock:
    """Tests for BatteryRegisterBlock."""

    def test_block_creation(self) -> None:
        regs = (
            BatteryRegister(address=22, name="voltage", scale=ScaleFactor.SCALE_100, unit="V"),
            BatteryRegister(address=23, name="current", scale=ScaleFactor.SCALE_100, signed=True, unit="A"),
        )
        block = BatteryRegisterBlock(start=19, count=23, registers=regs)
        assert block.start == 19
        assert block.count == 23
        assert len(block.registers) == 2


class TestBatteryProtocol:
    """Tests for BatteryProtocol base class."""

    def test_decode_unsigned(self) -> None:
        """Protocol.decode_register handles unsigned values."""
        reg = BatteryRegister(address=22, name="voltage", scale=ScaleFactor.SCALE_100, unit="V")
        result = BatteryProtocol.decode_register(reg, 5294)
        assert result == pytest.approx(52.94)

    def test_decode_signed_negative(self) -> None:
        """Protocol.decode_register handles signed negative values."""
        reg = BatteryRegister(
            address=23, name="current", scale=ScaleFactor.SCALE_100, signed=True, unit="A"
        )
        # -3080 as unsigned 16-bit = 62456
        raw = struct.unpack("H", struct.pack("h", -3080))[0]
        result = BatteryProtocol.decode_register(reg, raw)
        assert result == pytest.approx(-30.80)

    def test_decode_no_scale(self) -> None:
        """Protocol.decode_register with SCALE_NONE returns float."""
        reg = BatteryRegister(address=41, name="num_cells", scale=ScaleFactor.SCALE_NONE)
        result = BatteryProtocol.decode_register(reg, 16)
        assert result == 16.0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/battery_protocols/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pylxpweb.battery_protocols'`

**Step 3: Write minimal implementation**

```python
# src/pylxpweb/battery_protocols/__init__.py
"""Battery RS485 protocol definitions.

Each protocol defines register maps as pure data structures.
No I/O code — decoding only.
"""
from __future__ import annotations

from .base import BatteryProtocol, BatteryRegister, BatteryRegisterBlock

__all__ = [
    "BatteryProtocol",
    "BatteryRegister",
    "BatteryRegisterBlock",
]

# src/pylxpweb/battery_protocols/base.py
"""Base classes for battery protocol definitions."""
from __future__ import annotations

import struct
from dataclasses import dataclass

from pylxpweb.constants.scaling import ScaleFactor, apply_scale
from pylxpweb.transports.data import BatteryData


@dataclass(frozen=True)
class BatteryRegister:
    """Single register field definition.

    Attributes:
        address: Modbus register address.
        name: Canonical field name (e.g. "voltage", "current").
        scale: How to convert raw 16-bit value to real units.
        signed: If True, interpret raw value as signed int16.
        unit: Display unit string ("V", "A", "°C", "%").
    """

    address: int
    name: str
    scale: ScaleFactor
    signed: bool = False
    unit: str = ""


@dataclass(frozen=True)
class BatteryRegisterBlock:
    """Contiguous block of registers to read in one Modbus call.

    Attributes:
        start: First register address in the block.
        count: Number of contiguous registers to read.
        registers: Field definitions for registers within this block.
    """

    start: int
    count: int
    registers: tuple[BatteryRegister, ...]


class BatteryProtocol:
    """Base class for battery protocol definitions.

    Subclasses define register_blocks and override decode() to produce
    BatteryData from raw register values.
    """

    name: str = "base"
    register_blocks: list[BatteryRegisterBlock] = []

    @staticmethod
    def decode_register(reg: BatteryRegister, raw_value: int) -> float:
        """Decode a single raw register value using the register definition.

        Args:
            reg: Register definition with scaling and sign info.
            raw_value: Raw unsigned 16-bit value from Modbus.

        Returns:
            Scaled float value in proper units.
        """
        if reg.signed:
            raw_value = struct.unpack("h", struct.pack("H", raw_value & 0xFFFF))[0]
        return apply_scale(raw_value, reg.scale)

    def decode(self, raw_regs: dict[int, int], battery_index: int = 0) -> BatteryData:
        """Decode raw registers into a BatteryData object.

        Subclasses must override this method.

        Args:
            raw_regs: Dict mapping register address to raw 16-bit value.
            battery_index: 0-based index of the battery in the bank.

        Returns:
            BatteryData with all values properly scaled.
        """
        raise NotImplementedError
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/battery_protocols/test_base.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add src/pylxpweb/battery_protocols/ tests/unit/battery_protocols/
git commit -m "feat: add battery protocol base classes

BatteryRegister, BatteryRegisterBlock, and BatteryProtocol provide
the foundation for extensible battery RS485 protocol support.
Register maps are pure data; no I/O code."
```

---

## Task 2: EG4 Slave Protocol

**Files:**
- Create: `src/pylxpweb/battery_protocols/eg4_slave.py`
- Test: `tests/unit/battery_protocols/test_eg4_slave.py`

**Step 1: Write the failing test**

```python
# tests/unit/battery_protocols/test_eg4_slave.py
"""Tests for EG4 slave battery protocol (unit IDs 2+)."""
from __future__ import annotations

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
        """Decode standard slave registers: voltage ÷100, current ÷100 signed."""
        raw = {0: 5294, 1: 62456}  # 52.94V, -30.80A (as unsigned)
        # Fill cells and other required regs
        for i in range(2, 39):
            raw.setdefault(i, 0)
        data = self.protocol.decode(raw, battery_index=0)
        assert data.voltage == pytest.approx(52.94)
        assert data.current == pytest.approx(-30.80)

    def test_decode_cell_voltages(self) -> None:
        """Cell voltages at regs 2-17, ÷1000."""
        raw: dict[int, int] = {i: 0 for i in range(39)}
        raw[0] = 5300  # voltage
        raw[36] = 16  # num cells
        for i in range(16):
            raw[2 + i] = 3310 + i  # 3.310V to 3.325V
        data = self.protocol.decode(raw, battery_index=0)
        assert len(data.cell_voltages) == 16
        assert data.cell_voltages[0] == pytest.approx(3.310)
        assert data.cell_voltages[15] == pytest.approx(3.325)

    def test_decode_soc_soh(self) -> None:
        """SOC and SOH are direct (no scaling)."""
        raw: dict[int, int] = {i: 0 for i in range(39)}
        raw[23] = 100  # SOH
        raw[24] = 76  # SOC
        data = self.protocol.decode(raw, battery_index=0)
        assert data.soh == 100
        assert data.soc == 76

    def test_decode_temperatures(self) -> None:
        """Temperatures: PCB=reg18, avg=reg19, max=reg20."""
        raw: dict[int, int] = {i: 0 for i in range(39)}
        raw[18] = 25  # PCB temp
        raw[19] = 23  # Avg temp
        raw[20] = 27  # Max temp
        data = self.protocol.decode(raw, battery_index=0)
        assert data.temperature == 27.0  # Use max as primary temp

    def test_decode_designed_capacity(self) -> None:
        """Designed capacity: reg37 ÷10."""
        raw: dict[int, int] = {i: 0 for i in range(39)}
        raw[37] = 2800  # 280.0 Ah
        data = self.protocol.decode(raw, battery_index=0)
        assert data.max_capacity == pytest.approx(280.0)

    def test_decode_cycle_count_32bit(self) -> None:
        """Cycle count: 32-bit big-endian from regs 29-30."""
        raw: dict[int, int] = {i: 0 for i in range(39)}
        raw[29] = 0  # High word
        raw[30] = 138  # Low word
        data = self.protocol.decode(raw, battery_index=0)
        assert data.cycle_count == 138

    def test_decode_device_info(self) -> None:
        """Device info: model at 105-116, firmware at 117-119, serial at 120-127."""
        raw: dict[int, int] = {i: 0 for i in range(39)}
        # Add device info registers
        # "EG" in ASCII = 0x4547
        raw[105] = 0x4547
        raw[106] = 0x342D
        raw[107] = 0x4C4C
        for i in range(108, 117):
            raw[i] = 0
        # FW "217" = 0x3231, 0x3700
        raw[117] = 0x3231
        raw[118] = 0x3700
        raw[119] = 0
        data = self.protocol.decode(raw, battery_index=0)
        assert "EG4-LL" in data.model
        assert data.firmware_version != ""
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/battery_protocols/test_eg4_slave.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pylxpweb.battery_protocols.eg4_slave'`

**Step 3: Write minimal implementation**

```python
# src/pylxpweb/battery_protocols/eg4_slave.py
"""EG4 slave battery protocol (standard EG4-LL register map).

Used by batteries with unit ID 2+ on the RS485 daisy chain.
Register map sourced from ricardocello's eg4_waveshare.py.

Register layout:
  - Regs 0-38: Runtime state (voltage, current, cells, temps, SOC, etc.)
  - Regs 105-127: Device info (model, firmware, serial)
"""
from __future__ import annotations

import struct

from pylxpweb.constants.scaling import ScaleFactor
from pylxpweb.transports.data import BatteryData

from .base import BatteryProtocol, BatteryRegister, BatteryRegisterBlock

# Runtime registers (0-38)
_RUNTIME_REGISTERS = (
    BatteryRegister(0, "voltage", ScaleFactor.SCALE_100, unit="V"),
    BatteryRegister(1, "current", ScaleFactor.SCALE_100, signed=True, unit="A"),
    # Cell voltages 2-17 handled separately (loop)
    BatteryRegister(18, "pcb_temp", ScaleFactor.SCALE_NONE, signed=True, unit="°C"),
    BatteryRegister(19, "avg_temp", ScaleFactor.SCALE_NONE, signed=True, unit="°C"),
    BatteryRegister(20, "max_temp", ScaleFactor.SCALE_NONE, signed=True, unit="°C"),
    BatteryRegister(21, "remaining_capacity", ScaleFactor.SCALE_NONE, unit="Ah"),
    BatteryRegister(22, "max_charge_current", ScaleFactor.SCALE_NONE, unit="A"),
    BatteryRegister(23, "soh", ScaleFactor.SCALE_NONE, unit="%"),
    BatteryRegister(24, "soc", ScaleFactor.SCALE_NONE, unit="%"),
    BatteryRegister(25, "status", ScaleFactor.SCALE_NONE),
    BatteryRegister(26, "warning", ScaleFactor.SCALE_NONE),
    BatteryRegister(27, "protection", ScaleFactor.SCALE_NONE),
    BatteryRegister(28, "error", ScaleFactor.SCALE_NONE),
    # Regs 29-30: cycle count (32-bit BE), handled in decode()
    # Regs 31-32: full capacity (32-bit), handled in decode()
    BatteryRegister(36, "num_cells", ScaleFactor.SCALE_NONE),
    BatteryRegister(37, "designed_capacity", ScaleFactor.SCALE_10, unit="Ah"),
    BatteryRegister(38, "balance_bitmap", ScaleFactor.SCALE_NONE),
)

_RUNTIME_BLOCK = BatteryRegisterBlock(start=0, count=39, registers=_RUNTIME_REGISTERS)
_INFO_BLOCK = BatteryRegisterBlock(start=105, count=23, registers=())


def _decode_ascii(registers: dict[int, int], start: int, count: int) -> str:
    """Decode register values as ASCII (high byte, low byte per register)."""
    raw_bytes = bytearray()
    for i in range(count):
        val = registers.get(start + i, 0)
        raw_bytes.append((val >> 8) & 0xFF)
        raw_bytes.append(val & 0xFF)
    return raw_bytes.decode("ascii", errors="replace").replace("\x00", "").strip()


class EG4SlaveProtocol(BatteryProtocol):
    """Standard EG4-LL register map for slave batteries (unit ID 2+)."""

    name = "eg4_slave"
    register_blocks = [_RUNTIME_BLOCK, _INFO_BLOCK]

    def decode(self, raw_regs: dict[int, int], battery_index: int = 0) -> BatteryData:
        """Decode slave battery registers into BatteryData."""
        voltage = self.decode_register(
            BatteryRegister(0, "voltage", ScaleFactor.SCALE_100, unit="V"),
            raw_regs.get(0, 0),
        )
        current = self.decode_register(
            BatteryRegister(1, "current", ScaleFactor.SCALE_100, signed=True, unit="A"),
            raw_regs.get(1, 0),
        )

        # Cell voltages: regs 2-17, ÷1000
        num_cells = raw_regs.get(36, 16)
        cell_voltages = [raw_regs.get(2 + i, 0) / 1000.0 for i in range(num_cells)]
        non_zero_cells = [v for v in cell_voltages if v > 0]

        # Temperatures
        max_temp_raw = raw_regs.get(20, 0)
        max_temp = struct.unpack("h", struct.pack("H", max_temp_raw & 0xFFFF))[0]

        # SOC/SOH (direct, no scaling)
        soc = raw_regs.get(24, 0)
        soh = raw_regs.get(23, 100)

        # Cycle count: 32-bit big-endian
        cycle_count = (raw_regs.get(29, 0) << 16) | raw_regs.get(30, 0)

        # Designed capacity: ÷10
        max_capacity = raw_regs.get(37, 0) / 10.0

        # Status/fault/warning
        status = raw_regs.get(25, 0)
        warning = raw_regs.get(26, 0)
        fault = raw_regs.get(27, 0)

        # Device info (if available)
        model = _decode_ascii(raw_regs, 105, 12)
        firmware = _decode_ascii(raw_regs, 117, 3)
        serial = _decode_ascii(raw_regs, 120, 8)

        return BatteryData(
            battery_index=battery_index,
            serial_number=serial,
            voltage=voltage,
            current=current,
            soc=soc,
            soh=soh,
            temperature=float(max_temp),
            max_capacity=max_capacity,
            cycle_count=cycle_count,
            cell_count=num_cells,
            cell_voltages=cell_voltages,
            min_cell_voltage=min(non_zero_cells) if non_zero_cells else 0.0,
            max_cell_voltage=max(non_zero_cells) if non_zero_cells else 0.0,
            min_cell_temperature=float(
                struct.unpack("h", struct.pack("H", raw_regs.get(18, 0) & 0xFFFF))[0]
            ),
            max_cell_temperature=float(max_temp),
            model=model,
            firmware_version=firmware,
            status=status,
            warning_code=warning,
            fault_code=fault,
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/battery_protocols/test_eg4_slave.py -v`
Expected: All 9 tests PASS

**Step 5: Commit**

```bash
git add src/pylxpweb/battery_protocols/eg4_slave.py tests/unit/battery_protocols/test_eg4_slave.py
git commit -m "feat: add EG4 slave battery protocol (standard EG4-LL register map)

Registers 0-38 (runtime) + 105-127 (device info).
Decodes voltage, current, 16 cell voltages, temperatures,
SOC, SOH, cycle count, and model/firmware/serial."
```

---

## Task 3: EG4 Master Protocol

**Files:**
- Create: `src/pylxpweb/battery_protocols/eg4_master.py`
- Test: `tests/unit/battery_protocols/test_eg4_master.py`

**Step 1: Write the failing test**

```python
# tests/unit/battery_protocols/test_eg4_master.py
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
        """Pack voltage: reg 22 ÷100."""
        raw = self._base_regs()
        raw[22] = 5294
        data = self.protocol.decode(raw)
        assert data.voltage == pytest.approx(52.94)

    def test_decode_aggregate_current(self) -> None:
        """Aggregate current: reg 23 ÷100, signed."""
        raw = self._base_regs()
        raw[23] = _signed16(-3080)
        data = self.protocol.decode(raw)
        assert data.current == pytest.approx(-30.80)

    def test_decode_temperature(self) -> None:
        """Max temperature: reg 24, direct °C."""
        raw = self._base_regs()
        raw[24] = 22
        data = self.protocol.decode(raw)
        assert data.temperature == 22.0

    def test_decode_soc(self) -> None:
        """SOC: reg 26 ÷10."""
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
        """Designed capacity: reg 33 ÷20."""
        raw = self._base_regs()
        raw[33] = 5600  # 280 Ah
        data = self.protocol.decode(raw)
        assert data.max_capacity == pytest.approx(280.0)

    def test_decode_cell_voltages(self) -> None:
        """Cell voltages: regs 113-128, ÷1000."""
        raw = self._base_regs()
        raw[41] = 16  # num cells
        for i in range(16):
            raw[113 + i] = 3308 + i
        data = self.protocol.decode(raw)
        assert len(data.cell_voltages) == 16
        assert data.cell_voltages[0] == pytest.approx(3.308)
        assert data.cell_voltages[15] == pytest.approx(3.323)

    def test_decode_min_max_cell(self) -> None:
        """Max/min cell voltage: regs 37/38 ÷1000."""
        raw = self._base_regs()
        raw[37] = 3311
        raw[38] = 3308
        data = self.protocol.decode(raw)
        assert data.max_cell_voltage == pytest.approx(3.311)
        assert data.min_cell_voltage == pytest.approx(3.308)

    def test_decode_firmware_version(self) -> None:
        """Firmware: reg 28, packed BCD → 'V 2.17'."""
        raw = self._base_regs()
        raw[28] = 0x0211  # High=2, Low=0x11=17
        data = self.protocol.decode(raw)
        assert data.firmware_version == "2.17"

    def test_regs_0_to_18_ignored(self) -> None:
        """Regs 0-18 are unused in master protocol."""
        raw = self._base_regs()
        # Set reg 0 to a value that would be voltage in slave protocol
        raw[0] = 5294
        data = self.protocol.decode(raw)
        # Voltage should come from reg 22, not reg 0
        assert data.voltage == pytest.approx(0.0)

    def _base_regs(self) -> dict[int, int]:
        """Create a minimal raw register dict with all zeros."""
        return {i: 0 for i in range(42)} | {i: 0 for i in range(113, 129)}
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/battery_protocols/test_eg4_master.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pylxpweb.battery_protocols.eg4_master'`

**Step 3: Write minimal implementation**

```python
# src/pylxpweb/battery_protocols/eg4_master.py
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
  - Designed capacity at reg 33 uses ÷20 (not ÷10)
  - SOC at reg 26 uses ÷10
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
    BatteryRegister(24, "temperature", ScaleFactor.SCALE_NONE, signed=True, unit="°C"),
    BatteryRegister(26, "soc", ScaleFactor.SCALE_10, unit="%"),
    BatteryRegister(28, "firmware_version", ScaleFactor.SCALE_NONE),
    BatteryRegister(30, "cycle_count", ScaleFactor.SCALE_NONE),
    BatteryRegister(32, "soh", ScaleFactor.SCALE_NONE, unit="%"),
    BatteryRegister(33, "designed_capacity_raw", ScaleFactor.SCALE_NONE, unit="Ah"),
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

    The master battery aggregates data from all batteries on the chain:
    - Current = sum of all batteries
    - Voltage = minimum across all batteries
    - Temperature = maximum across all batteries
    - Cycle count = maximum across all batteries
    """

    name = "eg4_master"
    register_blocks = [_RUNTIME_BLOCK, _CELL_BLOCK]

    def decode(self, raw_regs: dict[int, int], battery_index: int = 0) -> BatteryData:
        """Decode master battery registers into BatteryData."""
        # Voltage: reg 22 ÷100
        voltage = self.decode_register(
            BatteryRegister(22, "voltage", ScaleFactor.SCALE_100, unit="V"),
            raw_regs.get(22, 0),
        )

        # Current: reg 23 ÷100, signed (AGGREGATE across all batteries)
        current = self.decode_register(
            BatteryRegister(23, "current", ScaleFactor.SCALE_100, signed=True, unit="A"),
            raw_regs.get(23, 0),
        )

        # Temperature: reg 24, direct (max across all batteries)
        temp_raw = raw_regs.get(24, 0)
        temperature = float(struct.unpack("h", struct.pack("H", temp_raw & 0xFFFF))[0])

        # SOC: reg 26 ÷10, truncate to int
        soc_raw = raw_regs.get(26, 0)
        soc = int(soc_raw / 10.0)

        # SOH: reg 32, direct
        soh = raw_regs.get(32, 100)

        # Cycle count: reg 30, direct
        cycle_count = raw_regs.get(30, 0)

        # Designed capacity: reg 33 ÷20
        max_capacity = raw_regs.get(33, 0) / 20.0

        # Cell voltages: regs 113-128, ÷1000
        num_cells = raw_regs.get(41, 16)
        cell_voltages = [raw_regs.get(113 + i, 0) / 1000.0 for i in range(num_cells)]
        non_zero_cells = [v for v in cell_voltages if v > 0]

        # Max/min cell voltage: regs 37/38 ÷1000
        max_cell_v = raw_regs.get(37, 0) / 1000.0
        min_cell_v = raw_regs.get(38, 0) / 1000.0

        # Firmware version: reg 28, packed BCD
        fw_raw = raw_regs.get(28, 0)
        fw_high = (fw_raw >> 8) & 0xFF
        fw_low = fw_raw & 0xFF
        firmware_version = f"{fw_high}.{fw_low:02d}" if fw_raw else ""

        # Status/protection
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
            min_cell_voltage=min_cell_v if min_cell_v > 0 else (min(non_zero_cells) if non_zero_cells else 0.0),
            max_cell_voltage=max_cell_v if max_cell_v > 0 else (max(non_zero_cells) if non_zero_cells else 0.0),
            min_cell_temperature=temperature,
            max_cell_temperature=temperature,
            firmware_version=firmware_version,
            status=status,
            fault_code=fault_code,
            warning_code=warning_code,
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/battery_protocols/test_eg4_master.py -v`
Expected: All 13 tests PASS

**Step 5: Commit**

```bash
git add src/pylxpweb/battery_protocols/eg4_master.py tests/unit/battery_protocols/test_eg4_master.py
git commit -m "feat: add EG4 master battery protocol (firmware-derived)

Registers 19-41 + 113-128. Reverse-engineered from HC32 BMS firmware
FUN_0001cf78. Master reports aggregate current, min voltage, max temp,
and max cycle count across all batteries on the daisy chain."
```

---

## Task 4: Protocol Auto-Detection

**Files:**
- Create: `src/pylxpweb/battery_protocols/detection.py`
- Test: `tests/unit/battery_protocols/test_detection.py`
- Modify: `src/pylxpweb/battery_protocols/__init__.py` — add exports

**Step 1: Write the failing test**

```python
# tests/unit/battery_protocols/test_detection.py
"""Tests for battery protocol auto-detection."""
from __future__ import annotations

from pylxpweb.battery_protocols.detection import detect_protocol
from pylxpweb.battery_protocols.eg4_master import EG4MasterProtocol
from pylxpweb.battery_protocols.eg4_slave import EG4SlaveProtocol


class TestDetectProtocol:
    """Tests for detect_protocol()."""

    def test_detect_master_all_zeros_early(self) -> None:
        """Regs 0-18 all zeros → master protocol."""
        raw = {i: 0 for i in range(39)}
        raw[22] = 5294  # Master voltage at reg 22
        protocol = detect_protocol(raw)
        assert isinstance(protocol, EG4MasterProtocol)

    def test_detect_slave_has_voltage_at_reg0(self) -> None:
        """Reg 0 has voltage → slave protocol."""
        raw = {i: 0 for i in range(39)}
        raw[0] = 5294  # Slave voltage at reg 0
        raw[1] = 100  # Slave current
        protocol = detect_protocol(raw)
        assert isinstance(protocol, EG4SlaveProtocol)

    def test_detect_master_tolerates_noise(self) -> None:
        """Up to 2 non-zero regs in 0-18 still detected as master."""
        raw = {i: 0 for i in range(39)}
        raw[5] = 1  # One spurious non-zero
        raw[10] = 1  # Second spurious
        protocol = detect_protocol(raw)
        assert isinstance(protocol, EG4MasterProtocol)

    def test_detect_slave_3_or_more_nonzero(self) -> None:
        """3+ non-zero regs in 0-18 → slave protocol."""
        raw = {i: 0 for i in range(39)}
        raw[0] = 5294
        raw[1] = 100
        raw[2] = 3310
        protocol = detect_protocol(raw)
        assert isinstance(protocol, EG4SlaveProtocol)

    def test_detect_empty_regs_returns_master(self) -> None:
        """Empty/all-zero registers default to master."""
        raw: dict[int, int] = {}
        protocol = detect_protocol(raw)
        assert isinstance(protocol, EG4MasterProtocol)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/battery_protocols/test_detection.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pylxpweb.battery_protocols.detection'`

**Step 3: Write minimal implementation**

```python
# src/pylxpweb/battery_protocols/detection.py
"""Auto-detection of battery protocol from raw register values.

The master battery (unit ID 1) has registers 0-18 all zeros, with data
starting at register 19. Slave batteries (unit ID 2+) have voltage at
register 0 and current at register 1.
"""
from __future__ import annotations

from .base import BatteryProtocol
from .eg4_master import EG4MasterProtocol
from .eg4_slave import EG4SlaveProtocol


def detect_protocol(raw_regs: dict[int, int]) -> BatteryProtocol:
    """Detect battery protocol from raw register values.

    Checks registers 0-18: if mostly zeros, it's a master battery.
    If 3+ registers are non-zero, it's a slave battery.

    Args:
        raw_regs: Dict mapping register address to raw 16-bit value.
            Should contain at least registers 0-18 for reliable detection.

    Returns:
        Appropriate BatteryProtocol instance.
    """
    early_non_zero = sum(1 for r in range(0, 19) if raw_regs.get(r, 0) != 0)
    if early_non_zero <= 2:
        return EG4MasterProtocol()
    return EG4SlaveProtocol()
```

Update `__init__.py`:

```python
# src/pylxpweb/battery_protocols/__init__.py
"""Battery RS485 protocol definitions.

Each protocol defines register maps as pure data structures.
No I/O code — decoding only.
"""
from __future__ import annotations

from .base import BatteryProtocol, BatteryRegister, BatteryRegisterBlock
from .detection import detect_protocol
from .eg4_master import EG4MasterProtocol
from .eg4_slave import EG4SlaveProtocol

__all__ = [
    "BatteryProtocol",
    "BatteryRegister",
    "BatteryRegisterBlock",
    "EG4MasterProtocol",
    "EG4SlaveProtocol",
    "detect_protocol",
]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/battery_protocols/ -v`
Expected: All tests PASS (base + slave + master + detection)

**Step 5: Commit**

```bash
git add src/pylxpweb/battery_protocols/ tests/unit/battery_protocols/
git commit -m "feat: add battery protocol auto-detection

Detects master vs slave by checking if registers 0-18 are zeros.
Exports all protocols from battery_protocols package."
```

---

## Task 5: BatteryModbusTransport

**Files:**
- Create: `src/pylxpweb/transports/battery_modbus.py`
- Test: `tests/unit/transports/test_battery_modbus.py`

**Step 1: Write the failing test**

```python
# tests/unit/transports/test_battery_modbus.py
"""Tests for BatteryModbusTransport."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.transports.battery_modbus import BatteryModbusTransport


@pytest.fixture
def transport() -> BatteryModbusTransport:
    return BatteryModbusTransport(
        host="10.100.3.27",
        port=502,
        unit_ids=[1, 2, 3],
        inverter_serial="1234567890",
    )


class TestBatteryModbusTransportInit:
    """Tests for transport initialization."""

    def test_basic_init(self, transport: BatteryModbusTransport) -> None:
        assert transport.host == "10.100.3.27"
        assert transport.port == 502
        assert transport.unit_ids == [1, 2, 3]
        assert transport.inverter_serial == "1234567890"
        assert transport.is_connected is False

    def test_default_unit_ids_none(self) -> None:
        t = BatteryModbusTransport(host="10.100.3.27")
        assert t.unit_ids is None
        assert t.max_units == 8

    def test_protocol_auto(self) -> None:
        t = BatteryModbusTransport(host="10.100.3.27", protocol="auto")
        assert t.protocol_name == "auto"


class TestBatteryModbusTransportReadUnit:
    """Tests for reading a single battery unit."""

    @pytest.mark.asyncio
    async def test_read_unit_slave(self, transport: BatteryModbusTransport) -> None:
        """Reading a slave unit returns BatteryData with correct values."""
        mock_client = AsyncMock()

        # Simulate slave battery response (voltage at reg 0)
        slave_regs = [0] * 39
        slave_regs[0] = 5294  # 52.94V
        slave_regs[1] = 100  # 1.00A
        slave_regs[24] = 76  # SOC
        slave_regs[23] = 100  # SOH
        slave_regs[36] = 16  # num cells

        mock_result = MagicMock()
        mock_result.isError.return_value = False
        mock_result.registers = slave_regs
        mock_client.read_holding_registers = AsyncMock(return_value=mock_result)

        transport._client = mock_client
        transport._connected = True

        data = await transport.read_unit(2)
        assert data is not None
        assert data.voltage == pytest.approx(52.94)
        assert data.soc == 76

    @pytest.mark.asyncio
    async def test_read_unit_no_response(self, transport: BatteryModbusTransport) -> None:
        """No response from unit returns None."""
        mock_client = AsyncMock()
        mock_result = MagicMock()
        mock_result.isError.return_value = True
        mock_client.read_holding_registers = AsyncMock(return_value=mock_result)

        transport._client = mock_client
        transport._connected = True

        data = await transport.read_unit(5)
        assert data is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/transports/test_battery_modbus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pylxpweb.transports.battery_modbus'`

**Step 3: Write minimal implementation**

```python
# src/pylxpweb/transports/battery_modbus.py
"""Direct RS485 battery Modbus transport.

Connects to an RS485-to-TCP bridge (e.g., Waveshare) on the battery
daisy chain, separate from the inverter's Modbus connection.

Each battery unit has a unique Modbus unit ID (1=master, 2+=slave).
The transport auto-detects the protocol (master vs slave) per unit.
"""
from __future__ import annotations

import asyncio
import logging

from pymodbus.client import AsyncModbusTcpClient

from pylxpweb.battery_protocols import detect_protocol
from pylxpweb.battery_protocols.base import BatteryProtocol
from pylxpweb.battery_protocols.eg4_master import EG4MasterProtocol
from pylxpweb.battery_protocols.eg4_slave import EG4SlaveProtocol
from pylxpweb.transports.data import BatteryData

_LOGGER = logging.getLogger(__name__)

# Protocol name → class mapping
_PROTOCOL_MAP: dict[str, type[BatteryProtocol]] = {
    "eg4_master": EG4MasterProtocol,
    "eg4_slave": EG4SlaveProtocol,
}


class BatteryModbusTransport:
    """Direct RS485 connection to battery BMS units.

    Connects to an RS485-to-TCP bridge that sits on the battery daisy
    chain. Each battery has its own Modbus unit ID.

    Args:
        host: Bridge IP address (e.g., "10.100.3.27").
        port: Modbus TCP port (default 502).
        unit_ids: Specific unit IDs to read. None = scan up to max_units.
        max_units: Maximum unit IDs to scan when unit_ids is None.
        protocol: Protocol name or "auto" for auto-detection.
        inverter_serial: Serial number of the inverter these batteries belong to.
        timeout: Modbus connection and read timeout in seconds.
    """

    def __init__(
        self,
        host: str,
        port: int = 502,
        unit_ids: list[int] | None = None,
        max_units: int = 8,
        protocol: str = "auto",
        inverter_serial: str = "",
        timeout: float = 3.0,
    ) -> None:
        self.host = host
        self.port = port
        self.unit_ids = unit_ids
        self.max_units = max_units
        self.protocol_name = protocol
        self.inverter_serial = inverter_serial
        self.timeout = timeout
        self._client: AsyncModbusTcpClient | None = None
        self._connected = False
        # Cache detected protocols per unit ID
        self._detected_protocols: dict[int, BatteryProtocol] = {}

    @property
    def is_connected(self) -> bool:
        """Check if transport is connected."""
        return self._connected

    async def connect(self) -> None:
        """Establish Modbus TCP connection to the RS485 bridge."""
        self._client = AsyncModbusTcpClient(
            self.host, port=self.port, timeout=self.timeout
        )
        await self._client.connect()
        self._connected = self._client.connected
        if self._connected:
            _LOGGER.info(
                "Connected to battery RS485 bridge at %s:%d", self.host, self.port
            )
        else:
            _LOGGER.error(
                "Failed to connect to battery RS485 bridge at %s:%d",
                self.host,
                self.port,
            )

    async def disconnect(self) -> None:
        """Close the Modbus TCP connection."""
        if self._client:
            self._client.close()
        self._connected = False

    async def _read_registers(
        self, start: int, count: int, unit_id: int
    ) -> list[int] | None:
        """Read holding registers from a battery unit.

        Returns list of register values, or None on error/timeout.
        """
        if not self._client:
            return None
        try:
            result = await self._client.read_holding_registers(
                start, count=count, device_id=unit_id
            )
            if result.isError():
                return None
            return list(result.registers)
        except Exception:
            _LOGGER.debug(
                "Read failed: unit=%d start=%d count=%d", unit_id, start, count
            )
            return None

    def _get_protocol(self, unit_id: int, raw_regs: dict[int, int]) -> BatteryProtocol:
        """Get the protocol for a unit, auto-detecting if needed."""
        if self.protocol_name != "auto":
            proto_cls = _PROTOCOL_MAP.get(self.protocol_name)
            if proto_cls:
                return proto_cls()
            _LOGGER.warning("Unknown protocol '%s', falling back to auto", self.protocol_name)

        # Check cache
        if unit_id in self._detected_protocols:
            return self._detected_protocols[unit_id]

        # Auto-detect from register values
        protocol = detect_protocol(raw_regs)
        self._detected_protocols[unit_id] = protocol
        _LOGGER.info(
            "Auto-detected protocol '%s' for unit %d", protocol.name, unit_id
        )
        return protocol

    async def read_unit(self, unit_id: int) -> BatteryData | None:
        """Read a single battery unit, returning decoded BatteryData.

        Auto-detects the protocol (master vs slave) on first read.

        Args:
            unit_id: Modbus unit/slave ID (1=master, 2+=slave).

        Returns:
            BatteryData with all values scaled, or None if unit doesn't respond.
        """
        # Read runtime registers (0-41 covers both master and slave)
        runtime_regs = await self._read_registers(0, 42, unit_id)
        if runtime_regs is None:
            return None

        raw: dict[int, int] = {i: v for i, v in enumerate(runtime_regs)}

        # Detect protocol
        protocol = self._get_protocol(unit_id, raw)

        # Read additional blocks defined by the protocol
        for block in protocol.register_blocks:
            if block.start >= 42:  # Don't re-read 0-41
                extra = await self._read_registers(block.start, block.count, unit_id)
                if extra:
                    for i, v in enumerate(extra):
                        raw[block.start + i] = v
                await asyncio.sleep(0.1)

        # For slave protocol, also try device info registers
        if isinstance(protocol, EG4SlaveProtocol):
            info_regs = await self._read_registers(105, 23, unit_id)
            if info_regs:
                for i, v in enumerate(info_regs):
                    raw[105 + i] = v

        # Decode using the detected protocol
        battery_index = unit_id - 1  # 0-based index
        return protocol.decode(raw, battery_index=battery_index)

    async def scan_units(self) -> list[int]:
        """Discover which unit IDs respond on the bus.

        Returns:
            List of responding unit IDs.
        """
        if self.unit_ids is not None:
            return self.unit_ids

        responding: list[int] = []
        for uid in range(1, self.max_units + 1):
            regs = await self._read_registers(0, 1, uid)
            if regs is not None:
                responding.append(uid)
            await asyncio.sleep(0.2)

        _LOGGER.info(
            "Battery bus scan: %d/%d units responding", len(responding), self.max_units
        )
        return responding

    async def read_all(self) -> list[BatteryData]:
        """Read all configured/discovered battery units.

        Returns:
            List of BatteryData objects for responding units.
        """
        units = self.unit_ids or await self.scan_units()
        results: list[BatteryData] = []

        for uid in units:
            data = await self.read_unit(uid)
            if data is not None:
                results.append(data)
            await asyncio.sleep(0.2)

        _LOGGER.info(
            "Read %d batteries from RS485 bus %s:%d",
            len(results),
            self.host,
            self.port,
        )
        return results
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/transports/test_battery_modbus.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/pylxpweb/transports/battery_modbus.py tests/unit/transports/test_battery_modbus.py
git commit -m "feat: add BatteryModbusTransport for direct RS485 battery reading

Connects to RS485-to-TCP bridge (Waveshare), reads battery BMS units
with auto-detection of master vs slave protocol. Supports explicit
unit_id partitioning for multi-inverter setups."
```

---

## Task 6: Raw Register Collection Script

**Files:**
- Create: `scripts/collect_battery_registers.py`

**Step 1: Write the script**

```python
# scripts/collect_battery_registers.py
#!/usr/bin/env python3
"""Collect raw battery register dumps for protocol discovery.

Scans a battery RS485 bus, reads all accessible registers, and outputs
structured JSON for analysis, protocol development, and debugging.

Usage:
    uv run python scripts/collect_battery_registers.py --host 10.100.3.27
    uv run python scripts/collect_battery_registers.py --host 10.100.3.27 --unit 1 --output dump.json
    uv run python scripts/collect_battery_registers.py --host 10.100.3.27 --max-units 8
"""
from __future__ import annotations

import argparse
import asyncio
import json
import struct
import sys
from datetime import datetime, timezone

from pymodbus.client import AsyncModbusTcpClient


async def try_read(
    client: AsyncModbusTcpClient, start: int, count: int, unit_id: int, func: str = "holding"
) -> list[int] | None:
    """Read registers, return list or None on error."""
    try:
        if func == "holding":
            result = await client.read_holding_registers(start, count=count, device_id=unit_id)
        else:
            result = await client.read_input_registers(start, count=count, device_id=unit_id)
        if result.isError():
            return None
        return list(result.registers)
    except Exception:
        return None


def make_signed16(value: int) -> int:
    """Reinterpret unsigned 16-bit as signed."""
    return struct.unpack("h", struct.pack("H", value))[0]


async def collect_unit(
    client: AsyncModbusTcpClient, unit_id: int, verbose: bool = True
) -> dict | None:
    """Collect all accessible registers from a single battery unit."""
    unit_data: dict = {
        "unit_id": unit_id,
        "holding_registers": {},
        "input_registers": {},
        "detected_protocol": "unknown",
        "decoded": {},
    }

    # Read holding registers in chunks
    for func_name in ("holding", "input"):
        reg_key = f"{func_name}_registers"
        for start, count in [(0, 50), (50, 50), (100, 30)]:
            regs = await try_read(client, start, count, unit_id, func_name)
            if regs:
                for i, val in enumerate(regs):
                    if val != 0:
                        addr = start + i
                        unit_data[reg_key][str(addr)] = {
                            "raw": val,
                            "hex": f"0x{val:04X}",
                            "signed": make_signed16(val),
                        }
            await asyncio.sleep(0.15)

    if not unit_data["holding_registers"] and not unit_data["input_registers"]:
        return None

    # Auto-detect protocol
    early_non_zero = 0
    for r in range(0, 19):
        if str(r) in unit_data["holding_registers"]:
            early_non_zero += 1

    if early_non_zero <= 2:
        unit_data["detected_protocol"] = "eg4_master"
    else:
        unit_data["detected_protocol"] = "eg4_slave"

    # Decode key values based on detected protocol
    decoded = {}
    hold = unit_data["holding_registers"]

    if unit_data["detected_protocol"] == "eg4_master":
        if "22" in hold:
            decoded["voltage"] = hold["22"]["raw"] / 100.0
        if "23" in hold:
            decoded["current_aggregate"] = hold["23"]["signed"] / 100.0
        if "24" in hold:
            decoded["temperature_max"] = hold["24"]["signed"]
        if "26" in hold:
            decoded["soc"] = hold["26"]["raw"] / 10.0
        if "30" in hold:
            decoded["cycle_count_max"] = hold["30"]["raw"]
        if "32" in hold:
            decoded["soh"] = hold["32"]["raw"]
        if "33" in hold:
            decoded["designed_capacity_ah"] = hold["33"]["raw"] / 20.0
        if "37" in hold:
            decoded["max_cell_voltage"] = hold["37"]["raw"] / 1000.0
        if "38" in hold:
            decoded["min_cell_voltage"] = hold["38"]["raw"] / 1000.0
        if "41" in hold:
            decoded["num_cells"] = hold["41"]["raw"]
        # Cell voltages
        cells = []
        for i in range(16):
            key = str(113 + i)
            if key in hold:
                cells.append(hold[key]["raw"] / 1000.0)
        if cells:
            decoded["cell_voltages"] = cells
    else:
        if "0" in hold:
            decoded["voltage"] = hold["0"]["raw"] / 100.0
        if "1" in hold:
            decoded["current"] = hold["1"]["signed"] / 100.0
        if "24" in hold:
            decoded["soc"] = hold["24"]["raw"]
        if "23" in hold:
            decoded["soh"] = hold["23"]["raw"]
        if "36" in hold:
            decoded["num_cells"] = hold["36"]["raw"]
        if "37" in hold:
            decoded["designed_capacity_ah"] = hold["37"]["raw"] / 10.0
        cells = []
        for i in range(16):
            key = str(2 + i)
            if key in hold:
                cells.append(hold[key]["raw"] / 1000.0)
        if cells:
            decoded["cell_voltages"] = cells

    unit_data["decoded"] = decoded

    if verbose:
        proto = unit_data["detected_protocol"]
        v = decoded.get("voltage", "?")
        soc = decoded.get("soc", "?")
        print(f"  Unit {unit_id}: {proto}  V={v}  SOC={soc}")

    return unit_data


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect raw battery register dumps for protocol discovery."
    )
    parser.add_argument("--host", default="10.100.3.27", help="RS485 bridge IP")
    parser.add_argument("--port", type=int, default=502, help="Modbus TCP port")
    parser.add_argument("--max-units", type=int, default=8, help="Max unit IDs to scan")
    parser.add_argument("--unit", type=int, default=0, help="Specific unit ID (0=scan all)")
    parser.add_argument("--output", "-o", default="", help="Output JSON file (default: stdout)")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()

    if not args.quiet:
        print(f"Battery Register Collector")
        print(f"Target: {args.host}:{args.port}")
        print("=" * 60)

    client = AsyncModbusTcpClient(args.host, port=args.port, timeout=3.0)
    await client.connect()

    if not client.connected:
        print(f"FAILED to connect to {args.host}:{args.port}", file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print(f"Connected to {args.host}:{args.port}")

    units_to_scan = [args.unit] if args.unit > 0 else list(range(1, args.max_units + 1))

    output = {
        "metadata": {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "host": args.host,
            "port": args.port,
            "tool_version": "1.0.0",
        },
        "units": [],
    }

    for uid in units_to_scan:
        unit_data = await collect_unit(client, uid, verbose=not args.quiet)
        if unit_data:
            output["units"].append(unit_data)
        elif not args.quiet:
            print(f"  Unit {uid}: no response")
        await asyncio.sleep(0.3)

    client.close()

    json_str = json.dumps(output, indent=2)

    if args.output:
        with open(args.output, "w") as f:
            f.write(json_str)
        if not args.quiet:
            print(f"\nOutput written to {args.output}")
    else:
        if not args.quiet:
            print(f"\n{'='*60}")
            print("JSON OUTPUT")
            print("=" * 60)
        print(json_str)


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 2: Verify script runs**

Run: `uv run python scripts/collect_battery_registers.py --help`
Expected: Shows usage help without errors

**Step 3: Commit**

```bash
git add scripts/collect_battery_registers.py
git commit -m "feat: add battery register collection script

Diagnostic utility for RS485 protocol discovery. Scans battery units,
reads all accessible registers, auto-detects master vs slave protocol,
and outputs structured JSON with decoded values."
```

---

## Task 7: Quality Checks

**Step 1: Run ruff**

Run: `uv run ruff check --fix src/pylxpweb/battery_protocols/ scripts/collect_battery_registers.py && uv run ruff format src/pylxpweb/battery_protocols/ scripts/collect_battery_registers.py`

**Step 2: Run mypy**

Run: `uv run mypy src/pylxpweb/battery_protocols/ --strict`

Fix any type errors that arise. Common fixes:
- Add `from __future__ import annotations` if missing
- Ensure `list[BatteryRegisterBlock]` class vars have proper type annotations
- Add return type annotations to all functions

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v --tb=short`

Ensure no existing tests are broken by the new code.

**Step 4: Commit any fixes**

```bash
git add -u
git commit -m "fix: resolve lint and type errors in battery protocols"
```

---

## Summary

| Task | Component | Tests | Commit |
|------|-----------|-------|--------|
| 1 | `battery_protocols/base.py` | 6 | Base classes |
| 2 | `battery_protocols/eg4_slave.py` | 9 | Slave protocol |
| 3 | `battery_protocols/eg4_master.py` | 13 | Master protocol |
| 4 | `battery_protocols/detection.py` | 5 | Auto-detection |
| 5 | `transports/battery_modbus.py` | 5 | Transport |
| 6 | `scripts/collect_battery_registers.py` | - | Collection script |
| 7 | Quality checks | - | Lint/type fixes |

**Total new tests:** ~38
**Total new files:** 8 source + 5 test + 1 script = 14

**Future work (not in this plan):**
- Priority chain integration into existing `read_battery()` (requires touching existing transport code)
- PYLON protocol definition (needs register map from hardware testing)
- Hanchu protocol definition (needs register map)
- `BatteryBankData.from_direct_batteries()` factory method
