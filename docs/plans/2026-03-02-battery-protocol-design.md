# Battery RS485 Protocol Support Design

**Date**: 2026-03-02
**Status**: Approved
**Scope**: pylxpweb library + diagnostic scripts

## Motivation

EG4-LL batteries on an RS485 daisy chain expose per-cell voltage, per-battery
current, and BMS status data that the inverter's cloud API and register
gateway (input regs 5000+) provide only in aggregate or reduced precision.
Additionally, the master battery (unit ID 1) uses a completely different
register map from slave batteries (unit ID 2+), discovered via firmware
reverse engineering.

This design adds direct RS485 battery reading as the **highest priority**
data source, with graceful fallback to existing paths.

## Data Source Priority

```
1. Battery RS485 Bus    (direct to BMS via Modbus TCP bridge)
2. Inverter Regs 5000+  (inverter relays BMS data via CAN, existing)
3. Inverter BMS Regs    (older register range, existing fallback)
```

## Architecture: Protocol + Transport Separation

### BatteryProtocol — Register Map Definitions (Pure Data)

Each battery protocol is a data-only definition: which registers hold which
fields, with what scaling. No I/O code.

**New package**: `src/pylxpweb/battery_protocols/`

```
battery_protocols/
├── __init__.py          # Exports: BatteryProtocol, detect_protocol, PROTOCOLS
├── base.py              # BatteryRegister, BatteryRegisterBlock, BatteryProtocol
├── eg4_master.py        # EG4MasterProtocol (regs 19-41, 113-128)
├── eg4_slave.py         # EG4SlaveProtocol (regs 0-38, 105-127)
├── pylon.py             # PylonProtocol (placeholder for future)
└── detection.py         # Auto-detection logic
```

**Core data structures:**

```python
@dataclass(frozen=True)
class BatteryRegister:
    address: int              # Modbus register address
    name: str                 # Canonical field name (e.g. "voltage")
    scale: ScaleFactor        # Scaling factor (SCALE_100, SCALE_1000, etc.)
    signed: bool = False      # Interpret as signed int16
    unit: str = ""            # Display unit ("V", "A", "°C", "%")

@dataclass(frozen=True)
class BatteryRegisterBlock:
    start: int                # First register address in block
    count: int                # Number of contiguous registers
    registers: tuple[BatteryRegister, ...]  # Field definitions within block

class BatteryProtocol:
    name: str                             # "eg4_master", "eg4_slave", etc.
    register_blocks: list[BatteryRegisterBlock]

    def decode(self, raw_regs: dict[int, int]) -> BatteryData:
        """Decode raw registers into transport-agnostic BatteryData."""
```

**Auto-detection:**

```python
def detect_protocol(raw_regs: dict[int, int]) -> BatteryProtocol:
    """Detect master vs slave by checking if regs 0-18 are all zeros."""
    early_non_zero = sum(1 for r in range(0, 19) if raw_regs.get(r, 0) != 0)
    if early_non_zero <= 2:
        return EG4MasterProtocol()
    return EG4SlaveProtocol()
```

### BatteryModbusTransport — Physical Connection

**New file**: `src/pylxpweb/transports/battery_modbus.py`

Handles Modbus TCP/RTU communication to the battery RS485 bus, separate from
the inverter's Modbus connection.

```python
class BatteryModbusTransport:
    def __init__(
        self,
        host: str,                          # Bridge IP
        port: int = 502,                    # Bridge Modbus TCP port
        unit_ids: list[int] | None = None,  # Specific units (None = scan)
        max_units: int = 8,                 # Max to scan if unit_ids=None
        protocol: str = "auto",             # "auto", "eg4", "pylon", "hanchu"
        inverter_serial: str = "",          # Binds to specific inverter
        timeout: float = 3.0,
    ) -> None: ...

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def scan_units(self) -> list[int]: ...
    async def read_unit(self, unit_id: int) -> BatteryData | None: ...
    async def read_all(self) -> list[BatteryData]: ...
```

**Inverter binding:**

`inverter_serial` explicitly ties a battery transport to a specific inverter.
`unit_ids` partitions battery units when multiple inverters share one RS485 bus.

Multi-inverter example:
```python
# Two inverters, shared bus, batteries partitioned
bus_inv1 = BatteryModbusTransport(
    host="10.100.3.27", port=502,
    unit_ids=[1, 2, 3],
    inverter_serial="1234567890",
)
bus_inv2 = BatteryModbusTransport(
    host="10.100.3.27", port=502,
    unit_ids=[4, 5],
    inverter_serial="9876543210",
)
```

### Priority Chain Integration

The existing inverter transport's `read_battery()` gains awareness of the
optional direct battery transport:

```python
async def read_battery(self) -> BatteryBankData | None:
    # Priority 1: Direct RS485 battery bus
    if self._battery_transport is not None:
        batteries = await self._battery_transport.read_all()
        if batteries:
            return BatteryBankData.from_direct_batteries(batteries)

    # Priority 2: Inverter input registers 5000+ (existing)
    bank = await self._read_battery_from_input_registers()
    if bank and bank.batteries:
        return bank

    # Priority 3: Inverter BMS registers (existing fallback)
    return await self._read_battery_from_bms_registers()
```

### Data Flow

```
RS485 Bridge ──Modbus TCP──→ BatteryModbusTransport
                                    │
                             BatteryProtocol.decode()
                                    │
                              BatteryData (list)
                                    │
                         BatteryBankData.from_direct()
                                    │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
            Battery objects    BatteryBank       HA Entities
```

`BatteryData` is the existing transport-agnostic dataclass. `Battery.from_transport_data()`
already handles conversion. No changes needed to the device layer.

## Raw Register Collection Script

**New file**: `scripts/collect_battery_registers.py`

Diagnostic utility for protocol discovery and validation.

**Features:**
- Full register scan (holding 0-128 + input 0-128 per unit)
- Structured JSON output with metadata
- Optional cloud API comparison mode
- Protocol auto-detection reporting
- Delta mode (compare two snapshots to find dynamic registers)

**Output format:**
```json
{
  "metadata": {
    "timestamp": "2026-03-02T10:30:00Z",
    "host": "10.100.3.27",
    "port": 502,
    "tool_version": "1.0.0"
  },
  "units": [{
    "unit_id": 1,
    "detected_protocol": "eg4_master",
    "holding_registers": {"19": {"raw": 99, "hex": "0x0063"}, ...},
    "decoded": {"voltage": 52.94, "current": -30.80, ...}
  }]
}
```

## File Structure

```
src/pylxpweb/
├── battery_protocols/              # NEW
│   ├── __init__.py
│   ├── base.py
│   ├── eg4_master.py
│   ├── eg4_slave.py
│   ├── pylon.py                    # Placeholder
│   └── detection.py
├── transports/
│   ├── battery_modbus.py           # NEW
│   └── ... (existing, minor integration)
scripts/
├── collect_battery_registers.py    # NEW
docs/
└── BATTERY_RS485_PROTOCOLS.md      # NEW (already written)
tests/unit/
├── battery_protocols/              # NEW
│   ├── test_eg4_master.py
│   ├── test_eg4_slave.py
│   └── test_detection.py
└── transports/
    └── test_battery_modbus.py      # NEW
```

## What Stays Unchanged

- `Battery` class — `from_transport_data()` factory already handles `BatteryData`
- `BatteryData` dataclass — transport-agnostic, reused
- `BatteryBank` / `BatteryBankData` — receives `BatteryData` list
- Existing Modbus/HTTP transports — no changes to core logic
- `ScaleFactor` enum — reused in protocol register definitions
- Cloud API integration — unaffected

## Implementation Phases

1. **Protocol definitions** — `battery_protocols/` package with EG4 master/slave
2. **Transport** — `BatteryModbusTransport` with connect/scan/read
3. **Integration** — Priority chain in existing transport, `from_direct_batteries()`
4. **Collection script** — `collect_battery_registers.py`
5. **Tests** — Unit tests for protocols and transport
6. **Future** — PYLON, Hanchu protocols (community-contributed register maps)
