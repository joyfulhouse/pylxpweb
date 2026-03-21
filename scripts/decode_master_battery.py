#!/usr/bin/env python3
"""Decode Master Battery (Unit ID 1) registers using firmware-derived register map.

The EG4-LL battery firmware uses TWO different register maps:
  - SLAVE batteries (ID 2+): Standard EG4-LL register map (regs 0-38 runtime, 105-127 info)
  - MASTER battery (ID 1):  Different layout with data starting at reg 19

This was reverse-engineered from the HC32 BMS firmware (firmware.bin) using Ghidra.
The key function FUN_0001cf78 populates the Modbus register buffer for the master battery.

Buffer structure (byte offset / 2 = register number):
  - DAT_0001d374 base: regs 19-25, 41
  - DAT_0001d780 base: regs 26-40, 113-128

Usage:
    uv run python scripts/decode_master_battery.py
    uv run python scripts/decode_master_battery.py --host 10.100.3.27 --port 502
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import sys

from pymodbus.client import AsyncModbusTcpClient


def make_signed16(value: int) -> int:
    """Reinterpret unsigned 16-bit as signed."""
    return struct.unpack("h", struct.pack("H", value))[0]


async def try_read(
    client: AsyncModbusTcpClient,
    start: int,
    count: int,
    unit_id: int,
) -> list[int] | None:
    """Read holding registers, return list or None on error."""
    try:
        result = await client.read_holding_registers(start, count=count, device_id=unit_id)
        if result.isError():
            return None
        return list(result.registers)
    except Exception:
        return None


async def read_all_registers(
    client: AsyncModbusTcpClient,
    unit_id: int,
) -> dict[int, int]:
    """Read all relevant registers for a unit, returning {reg_addr: value}."""
    all_regs: dict[int, int] = {}

    # Read in small chunks to avoid timeouts
    chunks = [
        (0, 50),  # Regs 0-49
        (100, 30),  # Regs 100-129 (device info area)
        (113, 16),  # Regs 113-128 (cell voltages, may overlap)
    ]

    for start, count in chunks:
        regs = await try_read(client, start, count, unit_id)
        if regs:
            for i, val in enumerate(regs):
                all_regs[start + i] = val
        await asyncio.sleep(0.2)

    return all_regs


def decode_master_battery(regs: dict[int, int]) -> dict[str, object]:
    """Decode master battery registers using firmware-derived map.

    Register map derived from Ghidra decompilation of FUN_0001cf78:
      - Buffer offsets / 2 = register numbers
      - Two buffer bases: DAT_0001d374 (regs 19-25, 41) and
        DAT_0001d780 (regs 26-40, 113-128)
    """
    data: dict[str, object] = {}

    # --- Registers from DAT_0001d374 buffer ---

    # Reg 19 (offset 0x26): Status/mode bitfield
    # Firmware builds this from charge/discharge state, heating, etc.
    raw_19 = regs.get(19, 0)
    data["status_raw"] = raw_19

    # Decode status bitfield (from firmware logic)
    base_state = raw_19 & 0x07
    state_labels = {
        0: "Standby",
        1: "Charging",
        2: "Discharging",
        3: "Charge+Discharge",
    }
    data["status_text"] = state_labels.get(base_state, f"Unknown({base_state})")

    if raw_19 & 0x20:
        data["status_text"] += ", DSG MOSFET Active"
    if raw_19 & 0x40:
        data["status_text"] += ", CHG MOSFET Active"

    # Reg 20 (offset 0x28): Protection bitfield
    raw_20 = regs.get(20, 0)
    data["protection_raw"] = raw_20

    prot_flags = []
    prot_bits = {
        0x0001: "Discharge SC",
        0x0002: "Float Stopped",
        0x0008: "Cell UV",
        0x0010: "Discharge OC",
        0x0020: "Charge OC",
        0x0040: "Abnormal Temp",
        0x0080: "MOSFET OT",
        0x0100: "Charge UT",
        0x0200: "Discharge UT",
        0x0400: "Charge OT",
        0x0800: "Discharge OT",
        0x1000: "Cell OV Prot",
        0x2000: "Pack UV/OV",
        0x4000: "CHG Voltage",
        0x8000: "Heat Flag",
    }
    for bit, label in prot_bits.items():
        if raw_20 & bit:
            prot_flags.append(label)
    data["protection_text"] = " | ".join(prot_flags) if prot_flags else "None"

    # Reg 21 (offset 0x2a): Error/balance bitfield
    raw_21 = regs.get(21, 0)
    data["error_raw"] = raw_21

    # Reg 22 (offset 0x2c): Pack voltage (÷100 for V)
    # Firmware: minimum of all slaves' voltage + local BMS voltage
    raw_22 = regs.get(22, 0)
    data["voltage_raw"] = raw_22
    data["voltage"] = raw_22 / 100.0

    # Reg 23 (offset 0x2e): Current
    # Firmware: FUN_0001933c() × 10, capped at ±30000
    # FUN_0001933c() appears to return current in 0.1A
    # So reg 23 = current_0.1A × 10 = current in 0.01A (centiamps)
    raw_23 = make_signed16(regs.get(23, 0))
    data["current_raw"] = raw_23
    data["current_cA"] = raw_23 / 100.0  # Interpretation: ÷100 → Amps

    # Reg 24 (offset 0x30): Temperature (°C)
    # Firmware: max of slave temperature or local BMS temperature
    raw_24 = make_signed16(regs.get(24, 0))
    data["temperature_raw"] = raw_24
    data["temperature"] = raw_24  # Direct °C

    # Reg 25 (offset 0x32): SOC or charge voltage × 100
    # Firmware: FUN_000191fc() × 100, capped at 30001
    raw_25 = regs.get(25, 0)
    data["reg25_raw"] = raw_25
    # If this is SOC: 30000/100 = 300% (capped, implies overflow or not SOC)
    # More likely charge voltage limit or max current
    if raw_25 == 30000:
        data["reg25_text"] = "CAPPED (30000) - overflow/sentinel"
    else:
        data["reg25_text"] = f"{raw_25} (÷100 = {raw_25 / 100:.2f})"

    # Reg 41 (offset 0x52): Number of cells
    raw_41 = regs.get(41, 0)
    data["num_cells"] = raw_41

    # --- Registers from DAT_0001d780 buffer ---

    # Reg 26 (offset 0x34): SOC × 100 (aggregated)
    raw_26 = regs.get(26, 0)
    data["soc_raw"] = raw_26

    # Reg 27 (offset 0x36): Something × 10
    raw_27 = regs.get(27, 0)
    data["reg27_raw"] = raw_27

    # Reg 28 (offset 0x38): Firmware version packed
    # Firmware encodes version digits from ASCII, packed into 16 bits
    raw_28 = regs.get(28, 0)
    high_byte = (raw_28 >> 8) & 0xFF
    low_byte = raw_28 & 0xFF
    data["firmware_version_raw"] = raw_28
    data["firmware_version_text"] = f"{high_byte}.{low_byte:02d}"

    # Reg 29: (unknown/zero typically)
    data["reg29"] = regs.get(29, 0)

    # Reg 30 (offset 0x3c): Cycle count (max across all batteries)
    raw_30 = regs.get(30, 0)
    data["cycle_count"] = raw_30

    # Reg 31: (unknown)
    data["reg31"] = regs.get(31, 0)

    # Reg 32 (offset 0x40): SOH or balance info
    raw_32 = regs.get(32, 0)
    data["soh_or_balance"] = raw_32

    # Reg 33 (offset 0x42): Designed capacity
    # Based on cell count: 16→5600 (0x15E0), 15→5350, 8→2800, 4→1400
    # Pattern: ~350 per cell. 5600 / 20 = 280 Ah (matches WP-16/280)
    raw_33 = regs.get(33, 0)
    data["designed_capacity_raw"] = raw_33
    data["designed_capacity_ah"] = raw_33 / 20.0

    # Reg 34 (offset 0x44): Warning/protection bitfield
    raw_34 = regs.get(34, 0)
    data["warning_raw"] = raw_34

    # Reg 35 (offset 0x46): Something × 100, capped at 30001
    raw_35 = regs.get(35, 0)
    data["reg35_raw"] = raw_35
    if raw_35 == 30000:
        data["reg35_text"] = "CAPPED (30000) - overflow/sentinel"
    else:
        data["reg35_text"] = f"{raw_35} (÷100 = {raw_35 / 100:.2f})"

    # Reg 36: (unknown)
    data["reg36"] = regs.get(36, 0)

    # Reg 37 (offset 0x4a): Max cell voltage (mV)
    raw_37 = regs.get(37, 0)
    data["max_cell_voltage_mv"] = raw_37
    data["max_cell_voltage"] = raw_37 / 1000.0

    # Reg 38 (offset 0x4c): Min cell voltage (mV)
    raw_38 = regs.get(38, 0)
    data["min_cell_voltage_mv"] = raw_38
    data["min_cell_voltage"] = raw_38 / 1000.0

    # Reg 39 (offset 0x4e): Max cell index/count (byte)
    data["max_cell_index"] = regs.get(39, 0)

    # Reg 40 (offset 0x50): Min cell index/count (byte)
    data["min_cell_index"] = regs.get(40, 0)

    # --- Cell voltages at register 113+ (offset 0xe2) ---
    num_cells = data["num_cells"]
    if isinstance(num_cells, int) and num_cells > 0:
        cells = []
        for i in range(num_cells):
            cell_mv = regs.get(113 + i, 0)
            cells.append(cell_mv / 1000.0)
        data["cell_voltages"] = cells

    return data


def decode_slave_battery(regs: dict[int, int]) -> dict[str, object]:
    """Decode slave battery using standard EG4-LL register map."""
    data: dict[str, object] = {}

    data["voltage"] = regs.get(0, 0) / 100.0
    data["current"] = make_signed16(regs.get(1, 0)) / 100.0
    data["cell_voltages"] = [regs.get(2 + i, 0) / 1000.0 for i in range(16)]
    data["pcb_temp"] = make_signed16(regs.get(18, 0))
    data["avg_temp"] = make_signed16(regs.get(19, 0))
    data["max_temp"] = make_signed16(regs.get(20, 0))
    data["capacity_remaining"] = regs.get(21, 0)
    data["max_charge_current"] = regs.get(22, 0)
    data["soh"] = regs.get(23, 0)
    data["soc"] = regs.get(24, 0)

    raw_status = regs.get(25, 0)
    base = raw_status & 0x000F
    labels = {0: "Standby", 1: "Charging", 2: "Discharging", 4: "Protect", 8: "Charge Limit"}
    status_text = labels.get(base, f"Unknown(0x{base:X})")
    if raw_status & 0x8000:
        status_text += ", Heat On"
    data["status_text"] = status_text

    data["warning"] = regs.get(26, 0)
    data["protection"] = regs.get(27, 0)
    data["error"] = regs.get(28, 0)
    data["cycle_count"] = (regs.get(29, 0) << 16) | regs.get(30, 0)
    data["num_cells"] = regs.get(36, 0)
    data["designed_capacity_ah"] = regs.get(37, 0) / 10.0

    return data


def print_master_battery(data: dict[str, object]) -> None:
    """Pretty-print master battery data."""
    print(f"\n{'=' * 72}")
    print("  MASTER BATTERY (Unit ID 1) - Firmware-Derived Register Map")
    print(f"{'=' * 72}")

    print("\n  --- Core Data ---")
    print(f"  Pack Voltage:     {data['voltage']:.2f} V  (reg 22 = {data['voltage_raw']})")
    print(f"  Current:          {data['current_cA']:.2f} A  (reg 23 = {data['current_raw']}, ÷100)")
    print(f"  Temperature:      {data['temperature']}°C  (reg 24 = {data['temperature_raw']})")

    print("\n  --- Status ---")
    status_hex = f"0x{data['status_raw']:04X}"
    print(
        f"  Status:           {data['status_text']}  (reg 19 = {data['status_raw']} / {status_hex})"
    )
    print(f"  Protection:       {data['protection_text']}  (reg 20 = {data['protection_raw']})")
    print(f"  Error/Balance:    reg 21 = {data['error_raw']} (0x{data['error_raw']:04X})")

    print("\n  --- Battery Info ---")
    print(f"  Cycle Count:      {data['cycle_count']}  (reg 30)")
    print(f"  SOH/Balance:      {data['soh_or_balance']}  (reg 32)")
    cap_ah = data["designed_capacity_ah"]
    cap_raw = data["designed_capacity_raw"]
    print(f"  Designed Capacity:{cap_ah:.1f} Ah  (reg 33 = {cap_raw}, \u00f720)")
    print(f"  Number of Cells:  {data['num_cells']}  (reg 41)")

    print("\n  --- Cell Voltages (reg 113+) ---")
    cells = data.get("cell_voltages", [])
    if cells:
        non_zero = [v for v in cells if v > 0]
        if non_zero:
            for i in range(0, len(cells), 8):
                chunk = cells[i : i + 8]
                formatted = " ".join(f"{v:.3f}" for v in chunk)
                print(f"    [{i + 1:2d}-{min(i + 8, len(cells)):2d}]:  {formatted}")
            min_v = min(non_zero)
            max_v = max(non_zero)
            print(f"    Min/Max:      {min_v:.3f} / {max_v:.3f} V  (delta: {max_v - min_v:.3f} V)")

    print("\n  --- Max/Min Cell ---")
    max_mv = data["max_cell_voltage_mv"]
    print(f"  Max Cell V:       {data['max_cell_voltage']:.3f} V  (reg 37 = {max_mv} mV)")
    min_mv = data["min_cell_voltage_mv"]
    print(f"  Min Cell V:       {data['min_cell_voltage']:.3f} V  (reg 38 = {min_mv} mV)")
    print(f"  Max Cell Index:   {data['max_cell_index']}  (reg 39)")
    print(f"  Min Cell Index:   {data['min_cell_index']}  (reg 40)")

    print("\n  --- Firmware & Unknown ---")
    fw_raw = data["firmware_version_raw"]
    print(
        f"  FW Version:       {data['firmware_version_text']}  (reg 28 = {fw_raw} / 0x{fw_raw:04X})"
    )
    print(f"  Reg 25:           {data.get('reg25_text', '')}  (possible overflow sentinel)")
    print(f"  Reg 27:           {data['reg27_raw']}  (0x{data['reg27_raw']:04X})")
    print(f"  Reg 29:           {data['reg29']}")
    print(f"  Reg 31:           {data['reg31']}")
    print(f"  Reg 34 (warning): {data['warning_raw']}  (0x{data['warning_raw']:04X})")
    print(f"  Reg 35:           {data.get('reg35_text', '')}  (possible overflow sentinel)")
    print(f"  Reg 36:           {data['reg36']}")
    print(f"  SOC raw:          {data['soc_raw']}  (reg 26)")


def print_slave_battery(uid: int, data: dict[str, object]) -> None:
    """Pretty-print slave battery data for comparison."""
    print(f"\n{'=' * 72}")
    print(f"  SLAVE BATTERY (Unit ID {uid}) - Standard EG4-LL Register Map")
    print(f"{'=' * 72}")
    print(f"  Pack Voltage:     {data['voltage']:.2f} V")
    print(f"  Current:          {data['current']:.2f} A")
    print(f"  SOC:              {data['soc']}%")
    print(f"  SOH:              {data['soh']}%")
    print(f"  Status:           {data['status_text']}")
    pcb = data["pcb_temp"]
    avg = data["avg_temp"]
    mx = data["max_temp"]
    print(f"  Temperature:      PCB={pcb}\u00b0C  Avg={avg}\u00b0C  Max={mx}\u00b0C")
    print(f"  Cycle Count:      {data['cycle_count']}")
    print(f"  Designed Cap:     {data['designed_capacity_ah']:.1f} Ah")
    print(f"  Number of Cells:  {data['num_cells']}")

    cells = data.get("cell_voltages", [])
    non_zero = [v for v in cells if v > 0]
    if non_zero:
        for i in range(0, len(cells), 8):
            chunk = cells[i : i + 8]
            formatted = " ".join(f"{v:.3f}" for v in chunk)
            print(f"    [{i + 1:2d}-{min(i + 8, len(cells)):2d}]:  {formatted}")
        min_v = min(non_zero)
        max_v = max(non_zero)
        print(f"    Min/Max:      {min_v:.3f} / {max_v:.3f} V  (delta: {max_v - min_v:.3f} V)")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Decode master battery registers using firmware-derived map."
    )
    parser.add_argument("--host", default="10.100.3.27", help="Waveshare bridge IP")
    parser.add_argument("--port", type=int, default=502, help="Modbus TCP port")
    args = parser.parse_args()

    print("EG4 Master Battery Register Decoder")
    print(f"Target: {args.host}:{args.port}")
    print("Register map: Firmware-derived (Ghidra decompilation of HC32 BMS)")
    print("=" * 72)

    client = AsyncModbusTcpClient(args.host, port=args.port, timeout=3.0)
    await client.connect()

    if not client.connected:
        print(f"FAILED to connect to {args.host}:{args.port}")
        sys.exit(1)

    print(f"Connected to {args.host}:{args.port}")

    # --- Read and decode master battery (Unit 1) ---
    print("\nReading Unit 1 (Master)...")
    master_regs = await read_all_registers(client, unit_id=1)

    if not master_regs:
        print("  No response from Unit 1!")
    else:
        # Check if this is actually a master battery (regs 0-18 should be ~zero)
        early_non_zero = sum(1 for r in range(0, 19) if master_regs.get(r, 0) != 0)
        if early_non_zero > 2:
            print(f"  WARNING: {early_non_zero} non-zero regs in 0-18. May not be master layout!")
        else:
            print("  Confirmed: Regs 0-18 are mostly zero → Master battery register layout")

        master_data = decode_master_battery(master_regs)
        print_master_battery(master_data)

        # Also dump raw non-zero registers for debugging
        print("\n  --- Raw Register Dump (non-zero) ---")
        for addr in sorted(master_regs.keys()):
            val = master_regs[addr]
            if val != 0:
                signed = make_signed16(val)
                print(f"    reg {addr:4d}: {val:5d} (0x{val:04X})  signed={signed:6d}")

    # --- Read and decode slave batteries (Units 2, 3) for comparison ---
    for uid in [2, 3]:
        print(f"\nReading Unit {uid} (Slave)...")
        slave_regs = await read_all_registers(client, uid)
        if slave_regs:
            slave_data = decode_slave_battery(slave_regs)
            print_slave_battery(uid, slave_data)
        else:
            print(f"  Unit {uid}: No response")
        await asyncio.sleep(0.3)

    client.close()

    # --- Comparison Summary ---
    print(f"\n{'=' * 72}")
    print("COMPARISON SUMMARY")
    print("=" * 72)
    if master_regs:
        master_data = decode_master_battery(master_regs)
        print(
            f"  Master (ID 1):  V={master_data['voltage']:.2f}V  I={master_data['current_cA']:.2f}A"
            f"  T={master_data['temperature']}°C  Cycles={master_data['cycle_count']}"
            f"  Cells={master_data['num_cells']}"
        )
        print(
            f"                  MaxCell={master_data['max_cell_voltage']:.3f}V"
            f"  MinCell={master_data['min_cell_voltage']:.3f}V"
            f"  DesignCap={master_data['designed_capacity_ah']:.0f}Ah"
        )


if __name__ == "__main__":
    asyncio.run(main())
