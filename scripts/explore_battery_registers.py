#!/usr/bin/env python3
"""Explore Modbus registers to find individual battery data.

This script connects to a FlexBOSS21 via Modbus TCP and scans various
register ranges to discover where individual battery module data might
be stored.

Usage:
    MODBUS_IP=172.16.40.98 MODBUS_PORT=502 uv run python scripts/explore_battery_registers.py
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from pymodbus.client import AsyncModbusTcpClient


@dataclass
class ScanResult:
    """Result of scanning a register range."""

    start: int
    count: int
    function: str
    values: list[int] | None
    error: str | None


async def scan_input_registers(
    client: AsyncModbusTcpClient,
    start: int,
    count: int,
    unit_id: int = 1,
) -> ScanResult:
    """Scan INPUT registers (function 0x04)."""
    try:
        result = await client.read_input_registers(
            address=start,
            count=count,
            device_id=unit_id,
        )
        if result.isError():
            return ScanResult(start, count, "INPUT", None, str(result))
        return ScanResult(start, count, "INPUT", list(result.registers), None)
    except Exception as e:
        return ScanResult(start, count, "INPUT", None, str(e))


async def scan_holding_registers(
    client: AsyncModbusTcpClient,
    start: int,
    count: int,
    unit_id: int = 1,
) -> ScanResult:
    """Scan HOLDING registers (function 0x03)."""
    try:
        result = await client.read_holding_registers(
            address=start,
            count=count,
            device_id=unit_id,
        )
        if result.isError():
            return ScanResult(start, count, "HOLDING", None, str(result))
        return ScanResult(start, count, "HOLDING", list(result.registers), None)
    except Exception as e:
        return ScanResult(start, count, "HOLDING", None, str(e))


async def scan_coils(
    client: AsyncModbusTcpClient,
    start: int,
    count: int,
    unit_id: int = 1,
) -> ScanResult:
    """Scan COILS (function 0x01)."""
    try:
        result = await client.read_coils(
            address=start,
            count=count,
            device_id=unit_id,
        )
        if result.isError():
            return ScanResult(start, count, "COIL", None, str(result))
        # Convert bits to list of 0/1
        values = [1 if b else 0 for b in result.bits[:count]]
        return ScanResult(start, count, "COIL", values, None)
    except Exception as e:
        return ScanResult(start, count, "COIL", None, str(e))


async def scan_discrete_inputs(
    client: AsyncModbusTcpClient,
    start: int,
    count: int,
    unit_id: int = 1,
) -> ScanResult:
    """Scan DISCRETE INPUTS (function 0x02)."""
    try:
        result = await client.read_discrete_inputs(
            address=start,
            count=count,
            device_id=unit_id,
        )
        if result.isError():
            return ScanResult(start, count, "DISCRETE", None, str(result))
        values = [1 if b else 0 for b in result.bits[:count]]
        return ScanResult(start, count, "DISCRETE", values, None)
    except Exception as e:
        return ScanResult(start, count, "DISCRETE", None, str(e))


def format_registers(values: list[int], start: int, show_hex: bool = True) -> str:
    """Format register values for display."""
    lines = []
    for i, val in enumerate(values):
        addr = start + i
        if val != 0:  # Only show non-zero values
            if show_hex:
                lines.append(f"  [{addr:4d}] = {val:5d} (0x{val:04X})")
            else:
                lines.append(f"  [{addr:4d}] = {val:5d}")
    return "\n".join(lines) if lines else "  (all zeros)"


async def main() -> None:
    """Main exploration function."""
    host = os.environ.get("MODBUS_IP", "172.16.40.98")
    port = int(os.environ.get("MODBUS_PORT", "502"))
    unit_id = int(os.environ.get("MODBUS_UNIT_ID", "1"))

    print(f"Connecting to {host}:{port} (unit {unit_id})...")

    client = AsyncModbusTcpClient(host=host, port=port, timeout=10.0)
    connected = await client.connect()

    if not connected:
        print("Failed to connect!")
        return

    print("Connected! Starting register exploration...\n")

    # =========================================================================
    # Phase 1: Scan extended INPUT registers beyond the known range
    # =========================================================================
    print("=" * 70)
    print("PHASE 1: Extended INPUT registers (beyond 0-127)")
    print("=" * 70)

    # Standard range is 0-127, let's scan further
    input_ranges = [
        (128, 128),  # 128-255
        (256, 128),  # 256-383
        (384, 128),  # 384-511
        (512, 128),  # 512-639
        (640, 128),  # 640-767
        (768, 128),  # 768-895
        (896, 128),  # 896-1023
        (1024, 128),  # 1024-1151
    ]

    for start, count in input_ranges:
        result = await scan_input_registers(client, start, count, unit_id)
        if result.values:
            non_zero = [v for v in result.values if v != 0]
            if non_zero:
                print(f"\n[INPUT {start}-{start + count - 1}] Found {len(non_zero)} non-zero values:")
                print(format_registers(result.values, start))
        elif result.error:
            print(f"[INPUT {start}-{start + count - 1}] Error: {result.error}")
        await asyncio.sleep(0.3)

    # =========================================================================
    # Phase 2: Scan extended HOLDING registers
    # =========================================================================
    print("\n" + "=" * 70)
    print("PHASE 2: Extended HOLDING registers (beyond 0-200)")
    print("=" * 70)

    holding_ranges = [
        (200, 100),  # 200-299
        (300, 100),  # 300-399
        (400, 100),  # 400-499
        (500, 100),  # 500-599
        (600, 100),  # 600-699
        (700, 100),  # 700-799
        (800, 100),  # 800-899
        (900, 100),  # 900-999
        (1000, 100),  # 1000-1099
    ]

    for start, count in holding_ranges:
        result = await scan_holding_registers(client, start, count, unit_id)
        if result.values:
            non_zero = [v for v in result.values if v != 0]
            if non_zero:
                print(f"\n[HOLDING {start}-{start + count - 1}] Found {len(non_zero)} non-zero values:")
                print(format_registers(result.values, start))
        elif result.error:
            print(f"[HOLDING {start}-{start + count - 1}] Error: {result.error}")
        await asyncio.sleep(0.3)

    # =========================================================================
    # Phase 3: Try COIL registers (1-bit read)
    # =========================================================================
    print("\n" + "=" * 70)
    print("PHASE 3: COIL registers (function 0x01)")
    print("=" * 70)

    coil_ranges = [
        (0, 64),
        (64, 64),
        (128, 64),
    ]

    for start, count in coil_ranges:
        result = await scan_coils(client, start, count, unit_id)
        if result.values:
            non_zero = [v for v in result.values if v != 0]
            if non_zero:
                print(f"\n[COIL {start}-{start + count - 1}] Found {len(non_zero)} set bits:")
                for i, v in enumerate(result.values):
                    if v:
                        print(f"  [{start + i}] = 1")
        elif result.error:
            print(f"[COIL {start}-{start + count - 1}] Error: {result.error}")
        await asyncio.sleep(0.3)

    # =========================================================================
    # Phase 4: Try DISCRETE INPUT registers (1-bit read)
    # =========================================================================
    print("\n" + "=" * 70)
    print("PHASE 4: DISCRETE INPUT registers (function 0x02)")
    print("=" * 70)

    for start, count in coil_ranges:
        result = await scan_discrete_inputs(client, start, count, unit_id)
        if result.values:
            non_zero = [v for v in result.values if v != 0]
            if non_zero:
                print(f"\n[DISCRETE {start}-{start + count - 1}] Found {len(non_zero)} set bits:")
                for i, v in enumerate(result.values):
                    if v:
                        print(f"  [{start + i}] = 1")
        elif result.error:
            print(f"[DISCRETE {start}-{start + count - 1}] Error: {result.error}")
        await asyncio.sleep(0.3)

    # =========================================================================
    # Phase 5: Focused scan of known BMS registers with comparison
    # =========================================================================
    print("\n" + "=" * 70)
    print("PHASE 5: Detailed BMS register dump (80-127)")
    print("=" * 70)

    result = await scan_input_registers(client, 80, 48, unit_id)
    if result.values:
        print("\nBMS INPUT registers 80-127:")
        print(format_registers(result.values, 80))

        # Decode known fields
        print("\n--- Decoded BMS fields ---")
        regs = {80 + i: v for i, v in enumerate(result.values)}

        # From register_maps.py:
        # bms_charge_current_limit = reg 81, scale /10
        # bms_discharge_current_limit = reg 82, scale /10
        # bms_charge_voltage_ref = reg 83, scale /10
        # bms_discharge_cutoff = reg 84, scale /10
        # battery_parallel_num = reg 96
        # battery_capacity_ah = reg 97
        # bms_max_cell_voltage = reg 101 (mV)
        # bms_min_cell_voltage = reg 102 (mV)
        # bms_max_cell_temperature = reg 103, scale /10
        # bms_min_cell_temperature = reg 104, scale /10
        # bms_cycle_count = reg 106

        print(f"  Charge current limit: {regs.get(81, 0) / 100:.2f} A")
        print(f"  Discharge current limit: {regs.get(82, 0) / 100:.2f} A")
        print(f"  Charge voltage ref: {regs.get(83, 0) / 10:.1f} V")
        print(f"  Discharge cutoff: {regs.get(84, 0) / 10:.1f} V")
        print(f"  Battery parallel count: {regs.get(96, 0)}")
        print(f"  Battery capacity: {regs.get(97, 0)} Ah")
        print(f"  Max cell voltage: {regs.get(101, 0)} mV ({regs.get(101, 0) / 1000:.3f} V)")
        print(f"  Min cell voltage: {regs.get(102, 0)} mV ({regs.get(102, 0) / 1000:.3f} V)")
        print(f"  Max cell temp: {regs.get(103, 0) / 10:.1f} °C")
        print(f"  Min cell temp: {regs.get(104, 0) / 10:.1f} °C")
        print(f"  Cycle count: {regs.get(106, 0)}")

    # =========================================================================
    # Phase 6: Try different unit IDs (maybe batteries are separate slaves?)
    # =========================================================================
    print("\n" + "=" * 70)
    print("PHASE 6: Try different Modbus unit IDs (batteries as slaves?)")
    print("=" * 70)

    for test_unit in [2, 3, 4, 5]:
        result = await scan_input_registers(client, 0, 32, test_unit)
        if result.values:
            non_zero = [v for v in result.values if v != 0]
            if non_zero:
                print(f"\n[Unit {test_unit}] Found data! {len(non_zero)} non-zero registers:")
                print(format_registers(result.values, 0))
        elif result.error:
            if "timeout" in result.error.lower():
                print(f"[Unit {test_unit}] Timeout (likely not present)")
            else:
                print(f"[Unit {test_unit}] Error: {result.error}")
        await asyncio.sleep(0.5)

    # =========================================================================
    # Phase 7: Dump first 128 INPUT registers for reference
    # =========================================================================
    print("\n" + "=" * 70)
    print("PHASE 7: Complete INPUT register dump (0-127)")
    print("=" * 70)

    result = await scan_input_registers(client, 0, 64, unit_id)
    if result.values:
        print("\nINPUT registers 0-63:")
        print(format_registers(result.values, 0))

    await asyncio.sleep(0.3)

    result = await scan_input_registers(client, 64, 64, unit_id)
    if result.values:
        print("\nINPUT registers 64-127:")
        print(format_registers(result.values, 64))

    client.close()
    print("\n" + "=" * 70)
    print("Exploration complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
