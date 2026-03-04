# EG4 Battery RS485 Protocol Documentation

**Date**: 2026-03-03
**Source**: Ghidra reverse engineering of HC32 BMS firmware + capstone disassembly + live RS485 validation
**Firmware**: `firmware.bin` (137KB, HC32 ARM Cortex-M, Thumb-2)
**Hardware**: EG4-LL WP-16/280-1AWLL batteries via Waveshare RS485-to-TCP bridge

## Overview

EG4-LL batteries communicate on an RS485 daisy chain using Modbus RTU (function
code 3, holding registers). Each battery has a unique unit ID (1, 2, 3...). The
**master battery** (unit ID 1) uses a completely different register map from
**slave batteries** (unit ID 2+).

This was discovered through firmware reverse engineering when the master battery
returned "garbage" data using the standard EG4-LL register map.

## Key Discovery: Two Register Maps

| Aspect | Master (Unit ID 1) | Slave (Unit ID 2+) |
|--------|-------------------|-------------------|
| Register layout | Data starts at reg 19 | Data starts at reg 0 |
| Regs 0-18 | All zeros | Voltage, current, cells |
| Cell voltages | Regs 113-128 | Regs 2-17 |
| Current meaning | **Aggregate** (sum of all batteries) | Individual battery |
| Voltage meaning | Minimum across all batteries | Individual battery |
| Temperature | Maximum across all batteries | Individual battery |
| Cycle count | Maximum across all batteries | Individual battery |
| SOC meaning | **Aggregate** (capacity-weighted: remaining/full×100) | Individual battery |
| Device info | Not available via RS485 | Regs 105-127 empty (status flags, not ASCII) |

## Side-by-Side Register Comparison

Shows how the same sensor data maps between master and slave register layouts.
"Derivable" means the master's individual value can be back-calculated from aggregate registers.

```
Sensor Data          Slave (Unit 2+)          Master (Unit 1)              Individual?
─────────────────────────────────────────────────────────────────────────────────────────
Voltage              reg 0   ÷100  V          reg 22  ÷100 V  (MIN all)   Derivable ¹
Current              reg 1   ÷100  A (signed) reg 23  ÷100 A  (SUM all)   NO
Cell voltages        reg 2-17  ÷1000 V        reg 113-128 ÷1000 V         YES (own cells)
PCB temperature      reg 18  direct °C        —                            NO
Avg temperature      reg 19  direct °C        —                            NO
Max temperature      reg 20  direct °C        reg 24  direct °C (MAX all)  NO
Remaining capacity   reg 21  direct Ah        reg 26  ×100 Ah (SUM all)²  Derivable ³
Max charge current   reg 22  direct A         —                            NO
SOH                  reg 23  direct %         reg 32  direct %             YES
SOC                  reg 24  direct %         reg 21  direct % (weighted)  Derivable ³
Status               reg 25  bitfield         reg 19  bitfield             YES (own)
Warning              reg 26  bitfield         reg 34  bitfield             YES (merged)
Protection           reg 27  bitfield         reg 20  bitfield             YES (merged)
Error                reg 28  bitfield         —                            NO
Cycle count          reg 29-30  32-bit BE     reg 30  direct (MAX all)     NO
Full capacity        reg 31-32  32-bit BE     —                            NO
Number of cells      reg 36  direct           reg 41  direct               YES
Designed capacity    reg 37  ÷10 Ah           reg 33  ÷20 Ah              YES
Balance bitmap       reg 38  bitfield         —                            NO
Total remaining      —                        reg 26  ×100 Ah (overflow)²  —
Total full capacity  —                        reg 27  ×100 Ah (overflow)²  —
Firmware version     —                        reg 28  packed BCD           YES
Max cell voltage     —                        reg 37  ÷1000 V             YES (own)
Min cell voltage     —                        reg 38  ÷1000 V             YES (own)
Max cell index       —                        reg 39  direct (0-based)     YES (own)
Min cell index       —                        reg 40  direct (0-based)     YES (own)
Overflow sentinel    —                        reg 25  ×100, cap 30000     —
Overflow sentinel    —                        reg 35  ×100, cap 30000     —
Device info          reg 105-127 (empty)⁴     —                            NO

¹ Master voltage = sum of cell voltages (regs 113-128), more accurate than reg 22 (MIN all)
² Overflows uint16. See "Register 26/27 Overflow" section for unwrap formula.
³ Derivable via reg 26/27 overflow unwrap: master_remaining = total_remaining - Σ slave_remaining
⁴ EG4-LL firmware never populates these; device info only available via CAN bus (cloud API)
```

### Data Source Mapping (Firmware RE)

How the master register builder (`FUN_0001cf78`) reads slave data to build each aggregate register:

| Master reg | Slave reg read | Slave field | Aggregation |
|------------|---------------|-------------|-------------|
| 19 (status) | — | — | Master's own BMS status |
| 20 (protection) | 27, 19 | protection, avg_temp | Bitfield merge + temp→flag |
| 21 (SOC) | — | — | FUN_190BA: total_remaining / total_full × 100 |
| 22 (voltage) | 0 | voltage | **MIN** across all batteries |
| 23 (current) | — | — | FUN_1933C: **SUM** of all currents |
| 24 (temperature) | 20 | max_temp | **MAX** across all batteries |
| 26 (total remaining) | 21 | remaining_cap | **SUM** × 100, overflows uint16 |
| 27 (total full) | 37 | designed_cap | **SUM** × 10, overflows uint16 |
| 28 (firmware) | — | — | FUN_1CDE8: packed BCD version |
| 30 (cycle count) | 29, 30 | cycle_hi, cycle_lo | **MAX** across all batteries |
| 32 (SOH) | 26 | warning | FUN_19244: warning→SOH calc |
| 33 (designed cap) | — | — | Cell count lookup table (÷20) |
| 34 (warning) | 19 | avg_temp | Temp→warning flag bits |
| 41 (num cells) | 36 | num_cells | Direct copy from master |

## Master Battery Register Map

Derived from Ghidra decompilation of `FUN_0001cf78` (the master register builder).
Two buffer bases: `DAT_0001d374` (byte offsets 0x26-0x32, 0x52) and
`DAT_0001d780` (byte offsets 0x34-0x50, 0xe2).

### Runtime Registers (19-41)

| Reg | Offset | Field | Scaling | Unit | Notes |
|-----|--------|-------|---------|------|-------|
| 19 | 0x26 | Status bitfield | Bitfield | - | See status decode below |
| 20 | 0x28 | Protection flags | Bitfield | - | See protection decode below |
| 21 | 0x2a | SOC | Direct | % | Capacity-weighted aggregate: total_remaining / total_full × 100 (all batteries) |
| 22 | 0x2c | Pack voltage | ÷100 | V | Min voltage across all batteries |
| 23 | 0x2e | Aggregate current | ÷100 | A | Sum of all batteries (signed) |
| 24 | 0x30 | Max temperature | Direct | °C | Max across all batteries |
| 25 | 0x32 | Overflow sentinel | ×100, cap 30000 | - | FUN_000191fc result |
| 26 | 0x34 | Total remaining capacity | ×100, overflows | Ah | FUN_18BD0 (master) + Σ slave reg 21. See overflow section |
| 27 | 0x36 | Total full capacity | ×10 then ×10, overflows | Ah | FUN_18BA0 (master) + Σ slave reg 37. See overflow section |
| 28 | 0x38 | Firmware version | Packed BCD | - | 0x0211 → V 2.17 |
| 29 | 0x3a | (reserved) | - | - | Typically zero |
| 30 | 0x3c | Cycle count | Direct | cycles | Max across all batteries |
| 31 | 0x3e | (reserved) | - | - | Typically zero |
| 32 | 0x40 | SOH | Direct | % | State of health |
| 33 | 0x42 | Designed capacity | ÷20 | Ah | 5600→280Ah for WP-16/280 |
| 34 | 0x44 | Warning bitfield | Bitfield | - | Warning flags |
| 35 | 0x46 | Overflow sentinel | ×100, cap 30000 | - | FUN_00019220 result |
| 36 | 0x48 | (reserved) | - | - | Typically zero |
| 37 | 0x4a | Max cell voltage | ÷1000 | V | Highest cell in master |
| 38 | 0x4c | Min cell voltage | ÷1000 | V | Lowest cell in master |
| 39 | 0x4e | Max cell index | Direct | - | 0-based cell index |
| 40 | 0x50 | Min cell index | Direct | - | 0-based cell index |
| 41 | 0x52 | Number of cells | Direct | - | 16 for WP-16/280 |

### Cell Voltages (113-128)

| Reg | Field | Scaling | Notes |
|-----|-------|---------|-------|
| 113-128 | Cell 1-16 voltage | ÷1000 | V, master's own cells only |

Firmware loop: `for (i = 0; i < num_cells; i++) { buffer[(i + 0x71) * 2] }`
where 0x71 = 113.

### Status Bitfield (Register 19)

```
Bits 0-2: Base state (0=Standby, 1=Charging, 2=Discharging, 3=Charge+Discharge)
Bit 5:    DSG MOSFET active
Bit 6:    CHG MOSFET active
```

### Protection Bitfield (Register 20)

| Bit | Flag |
|-----|------|
| 0x0001 | Discharge SC |
| 0x0002 | Float Stopped |
| 0x0008 | Cell UV |
| 0x0010 | Discharge OC |
| 0x0020 | Charge OC |
| 0x0040 | Abnormal Temp |
| 0x0080 | MOSFET OT |
| 0x0100 | Charge UT |
| 0x0200 | Discharge UT |
| 0x0400 | Charge OT |
| 0x0800 | Discharge OT |
| 0x1000 | Cell OV Protection |
| 0x2000 | Pack UV/OV |
| 0x4000 | CHG Voltage |
| 0x8000 | Heat Flag |

### Designed Capacity by Cell Count

From firmware lookup table in `FUN_0001cf78`:

| Cell Count | Raw Value | ÷20 = Ah | Model |
|-----------|-----------|----------|-------|
| 16 | 5600 (0x15E0) | 280 | WP-16/280-1AWLL |
| 15 | 5350 (0x14E6) | 267.5 | WM-48-280 variant |
| 8 | 2800 (0x0AF0) | 140 | 8-cell variant |
| 4 | 1400 (0x0578) | 70 | 4-cell variant |

## Slave Battery Register Map (Standard EG4-LL)

Based on ricardocello's eg4_waveshare.py register map. Used by unit IDs 2+.

### Runtime Registers (0-38)

| Reg | Field | Scaling | Unit |
|-----|-------|---------|------|
| 0 | Pack voltage | ÷100 | V |
| 1 | Current (signed) | ÷100 | A |
| 2-17 | Cell voltages 1-16 | ÷1000 | V |
| 18 | PCB temperature | Direct | °C |
| 19 | Avg temperature | Direct | °C |
| 20 | Max temperature | Direct | °C |
| 21 | Remaining capacity | Direct | Ah |
| 22 | Max charge current | Direct | A |
| 23 | SOH | Direct | % |
| 24 | SOC | Direct | % |
| 25 | Status | Bitfield | - |
| 26 | Warning | Bitfield | - |
| 27 | Protection | Bitfield | - |
| 28 | Error | Bitfield | - |
| 29-30 | Cycle count | 32-bit BE | cycles |
| 31-32 | Full capacity | 32-bit BE | mAh÷3600000→Ah |
| 33-35 | Packed temps | 2 per reg | °C |
| 36 | Number of cells | Direct | - |
| 37 | Designed capacity | ÷10 | Ah |
| 38 | Balance bitmap | Bitfield | - |

### Device Info Registers (105-127) — NOT AVAILABLE

**Firmware RE confirmed**: Slave registers 105-127 return **all zeros** on EG4-LL batteries.
The Modbus register lookup function (`FUN_2CDB4`) serves registers 0-199 from a flat buffer,
but the slave code path never populates positions 105-127 with ASCII device info.

A separate internal function writes status flags to buffer offsets 0xC8-0xE8 (regs 100-116)
in a **different buffer** used for CAN bus communication, not the Modbus response buffer.

Device info (model, firmware version, serial number) is only available via the **CAN bus**
protocol (P01-EG4), which the inverter reads and reports to the cloud API.

**ricardocello's eg4_waveshare.py register map** listed these as ASCII fields, but this
does not match the EG4-LL WP-16/280-1AWLL firmware behavior.

### Slave Status Bitfield (Register 25)

```
Bits 0-3: Base state (0=Standby, 1=Charging, 2=Discharging, 4=Protect, 8=Charge Limit)
Bit 15:   Heat On
```

## Firmware Multi-Protocol Support

The BMS firmware supports 8 inverter communication protocols via CAN bus,
selected by configuration. Found in `FUN_00019f80` (CAN frame builder) and
`FUN_00017760` (CAN timer/protocol selection).

| Code | Name | CAN Frames | Notes |
|------|------|------------|-------|
| P01 | EG4 | 11 | Default EG4/Luxpower protocol |
| P02 | GRW | 8 | Growatt compatible |
| P03 | SCH | 8 | Schneider compatible |
| P04 | DY | 5 | Deye compatible |
| P05 | MGR | 18 | MG/Renac compatible |
| P06 | VCT | 6 | Victron compatible |
| P07 | LUX | 7 | Luxpower direct |
| P08 | SMA | 8 | SMA compatible (uses PYLON ASCII) |

Protocol strings found at firmware offset ~0x021458.
P08 (SMA) embeds "PYLON" ASCII identifier in CAN frames, suggesting
PYLON emulation mode.

## Register 26/27 Overflow and Master SOC Back-Calculation

### The Overflow Problem

Master registers 26 and 27 store aggregate capacity values multiplied by 100,
but the result is stored as uint16 (max 65535), causing overflow for multi-battery systems.

**Register 26** (total remaining capacity):
```
r4 = FUN_18BD0()        # master's own remaining capacity (Ah)
for each slave:
    r4 += slave_reg_21  # slave remaining capacity (Ah)
reg_26 = (r4 * 100) & 0xFFFF   # multiply by 100, overflow uint16
```

**Register 27** (total full/designed capacity):
```
r4 = FUN_18BA0()        # master's own designed capacity (in reg37 units = ×10 Ah)
for each slave:
    r4 += slave_reg_37  # slave designed capacity (×10 Ah, e.g., 2800 = 280 Ah)
reg_27 = (r4 * 10) & 0xFFFF    # multiply by 10, overflow uint16
```

Both registers end up in units of **Ah × 100** after all multiplications.

### Unwrap Formula

To recover the true value, find N such that the result is physically reasonable:

```
total_remaining_Ah = (reg_26 + N * 65536) / 100
total_full_Ah      = (reg_27 + N * 65536) / 100
```

N is deterministic from the battery count and designed capacity:
- `expected_full = num_batteries × designed_capacity_Ah`
- `N = round(expected_full * 100 / 65536)` (typically N=1 for 3× 280 Ah)

### Master SOC Back-Calculation

Once unwrapped, the master battery's individual remaining capacity and SOC:

```
master_remaining = total_remaining - Σ slave_remaining
master_soc = master_remaining / master_designed_capacity × 100
```

### Validated Example (2026-03-03, 3× WP-16/280-1AWLL)

| Value | Formula | Result | Cloud API |
|-------|---------|--------|-----------|
| reg 26 | — | 464 | — |
| reg 27 | — | 18464 | — |
| total_remaining | (464 + 65536) / 100 | **660 Ah** | 659 Ah |
| total_full | (18464 + 65536) / 100 | **840 Ah** | 840 Ah |
| slave remaining | 220 + 227 (RS485 reg 21) | **447 Ah** | 447 Ah |
| master remaining | 660 - 447 | **213 Ah** | 212 Ah |
| master SOC | 213 / 280 × 100 | **76.1%** | 76% |

Error: 0.1% SOC (1 Ah timing difference between RS485 and cloud reads).

## Validation Results

Tested 2026-03-01 against live system (3x WP-16/280-1AWLL batteries).

### Current Aggregation (Confirmed)

| Source | Value |
|--------|-------|
| Master reg 23 (÷100) | -30.80 A |
| Cloud API Battery 1 current (÷10) | -10.8 A |
| Cloud API Battery 2 current (÷10) | -10.8 A |
| Cloud API Battery 3 current (÷10) | -9.4 A |
| **Sum of individual** | **-31.0 A** |

Master's current register represents the **aggregate** current across all
batteries on the daisy chain, not individual battery current.

### SOC Computation (Confirmed via Firmware RE)

Master reg 21 = capacity-weighted aggregate SOC across ALL batteries:
- `FUN_290BA`: Sums remaining capacity (master FUN_28BD0 + slave cmd 0x15)
  and full capacity (master FUN_28BA0 + slave cmd 0x25)
- SOC = total_remaining / total_full × 100

| Source | Value |
|--------|-------|
| Master reg 21 | 79% |
| Battery 1 remaining (cloud) | 212 Ah |
| Battery 2 remaining (cloud) | 221 Ah |
| Battery 3 remaining (cloud) | 226 Ah |
| **Total remaining / total full** | **659 / 840 = 78.5% ≈ 79%** |

### Register Space Boundaries (Confirmed)

- Master: Regs 0-18 = zeros, 19-41 = data, 42-112 = zeros, 113-128 = cells, 129+ = timeout
- Slave: Regs 0-38 = data, 39-127 = zeros (no device info), 128+ = timeout
- Modbus lookup (`FUN_2CDB4`): Hard limit at register < 200 (0xC8)

## Reverse Engineering Methodology

1. **Firmware extraction**: 137KB binary from EG4-LL battery BMS (HC32 MCU)
2. **Ghidra 12.0.3 headless analysis**: Decompiled all functions referencing
   register-related constants (0x71, 0xe2, 0x4a, etc.)
3. **capstone ARM Thumb-2 disassembly**: Verified Ghidra findings and traced
   SOC computation, register lookup, and device info code paths
4. **Key function identification**:
   - `FUN_0001cf78` (file offset 0x1CF78) = master register builder
   - `FUN_0001d858` (file offset 0x1D858) = slave summary builder (CAN bus)
   - `FUN_290BA` (file offset 0x190BA) = SOC computation (capacity-weighted)
   - `FUN_2CDB4` (file offset 0x1CDB4) = Modbus register lookup (limit: reg < 200)
   - Modbus handler at file offset 0x1C87C: FC3 routing for master/slave
5. **Buffer offset mapping**: Byte offsets in firmware ÷ 2 = register addresses
6. **Live validation**: Compared decoded RS485 values to cloud API responses
7. **Scaling verification**: Cross-referenced firmware arithmetic (×10, ÷100, etc.)
   with known physical values

### Firmware Build Info

- Build date: `2026-02-10` (found at file offset 0x21434)
- Model strings at offset 0x1FA60: `EG4-LL`, `WM-48|280-LL-00`, `SR-24|200-LL-00`, etc.
- Flash layout: Bootloader 0x0000-0x4800, Main app 0x10000-0x21720
