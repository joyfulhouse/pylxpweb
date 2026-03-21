#!/usr/bin/env python3
"""Scan FlexBOSS21 registers via Modbus and identify unmapped data."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Suppress pymodbus debug output
logging.getLogger("pymodbus").setLevel(logging.ERROR)
logging.getLogger("pymodbus.transaction").setLevel(logging.ERROR)

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

load_dotenv(Path(__file__).parent.parent / ".env")


def get_mapped_registers() -> tuple[dict[int, str], dict[int, str]]:
    """Get all mapped input and holding registers."""
    from pylxpweb.transports.register_maps import (
        PV_SERIES_ENERGY_MAP,
        PV_SERIES_RUNTIME_MAP,
    )

    input_mapped: dict[int, str] = {}
    holding_mapped: dict[int, str] = {}

    # Runtime map uses INPUT registers
    for field_name in dir(PV_SERIES_RUNTIME_MAP):
        if field_name.startswith("_"):
            continue
        field_def = getattr(PV_SERIES_RUNTIME_MAP, field_name)
        if hasattr(field_def, "address"):
            input_mapped[field_def.address] = field_name
            if hasattr(field_def, "bit_width") and field_def.bit_width == 32:
                input_mapped[field_def.address + 1] = f"{field_name}[hi]"

    # Energy map also uses INPUT registers
    for field_name in dir(PV_SERIES_ENERGY_MAP):
        if field_name.startswith("_"):
            continue
        field_def = getattr(PV_SERIES_ENERGY_MAP, field_name)
        if hasattr(field_def, "address"):
            input_mapped[field_def.address] = f"energy.{field_name}"
            if hasattr(field_def, "bit_width") and field_def.bit_width == 32:
                input_mapped[field_def.address + 1] = f"energy.{field_name}[hi]"

    return input_mapped, holding_mapped


async def read_registers_safe(read_func, start: int, count: int, unit_id: int) -> dict[int, int]:
    """Read registers with timeout handling."""
    result: dict[int, int] = {}
    try:
        resp = await asyncio.wait_for(
            read_func(address=start, count=count, device_id=unit_id),
            timeout=5.0,
        )
        if not resp.isError() and hasattr(resp, "registers"):
            for offset, value in enumerate(resp.registers):
                result[start + offset] = value
    except TimeoutError:
        pass  # Skip on timeout
    except Exception:
        pass  # Skip on error
    return result


async def scan_all_registers(host: str, port: int, unit_id: int = 1):
    """Scan all registers from the FlexBOSS21."""
    from pymodbus.client import AsyncModbusTcpClient

    print(f"Connecting to {host}:{port}...")
    client = AsyncModbusTcpClient(host=host, port=port, timeout=5.0)
    connected = await client.connect()

    if not connected:
        print("Failed to connect!")
        return None, None

    print("Connected. Reading registers...")

    input_regs: dict[int, int] = {}
    holding_regs: dict[int, int] = {}

    # Read INPUT registers 0-127
    print("  Reading input registers 0-127...")
    for start in range(0, 128, 40):
        count = min(40, 128 - start)
        regs = await read_registers_safe(client.read_input_registers, start, count, unit_id)
        input_regs.update(regs)

    # Read INPUT registers 128-255
    print("  Reading input registers 128-255...")
    for start in range(128, 256, 40):
        count = min(40, 256 - start)
        regs = await read_registers_safe(client.read_input_registers, start, count, unit_id)
        input_regs.update(regs)

    # Read HOLDING registers 0-127
    print("  Reading holding registers 0-127...")
    for start in range(0, 128, 40):
        count = min(40, 128 - start)
        regs = await read_registers_safe(client.read_holding_registers, start, count, unit_id)
        holding_regs.update(regs)

    # Read HOLDING registers 128-255
    print("  Reading holding registers 128-255...")
    for start in range(128, 256, 40):
        count = min(40, 256 - start)
        regs = await read_registers_safe(client.read_holding_registers, start, count, unit_id)
        holding_regs.update(regs)

    client.close()
    return input_regs, holding_regs


def interpret_value(value: int) -> str:
    """Try to interpret a register value."""
    parts = []
    # Check if it's a signed value
    if value > 32767:
        signed = value - 65536
        parts.append(f"signed={signed}")
    # Check if it's likely a scaled value
    if 1000 <= value <= 65000:
        parts.append(f"÷10={value / 10:.1f}")
        parts.append(f"÷100={value / 100:.2f}")
    # Check if it's an ASCII pair
    low = value & 0xFF
    high = (value >> 8) & 0xFF
    if 32 <= low <= 126 and 32 <= high <= 126:
        parts.append(f"ascii='{chr(low)}{chr(high)}'")
    elif 32 <= low <= 126:
        parts.append(f"lo='{chr(low)}'")

    return " | ".join(parts) if parts else ""


def get_webapp_fields() -> set[str]:
    """Get fields available via web API InverterRuntime."""
    from pylxpweb.models import InverterRuntime

    return set(InverterRuntime.model_fields.keys())


def get_modbus_fields() -> set[str]:
    """Get fields available via Modbus InverterRuntimeData."""
    from pylxpweb.transports.data import InverterRuntimeData

    return {f.name for f in InverterRuntimeData.__dataclass_fields__.values()}


async def main():
    """Main entry point."""
    host = os.getenv("MODBUS_IP", "172.16.40.98")
    port = int(os.getenv("MODBUS_PORT", "502"))
    serial = os.getenv("MODBUS_SERIAL", "unknown")

    print("FlexBOSS21 Register Scanner")
    print(f"Target: {host}:{port} (Serial: {serial})")
    print("=" * 80)

    # Get mapped registers
    input_mapped, _ = get_mapped_registers()
    print(f"Currently mapped input registers: {len(input_mapped)}")

    # Scan registers
    input_regs, holding_regs = await scan_all_registers(host, port)

    if input_regs is None:
        print("Scan failed!")
        return

    print(f"\nRead {len(input_regs)} input registers, {len(holding_regs)} holding registers")

    # Find unmapped INPUT registers with non-zero values
    print("\n" + "=" * 80)
    print("UNMAPPED INPUT REGISTERS (non-zero values only)")
    print("=" * 80)

    unmapped_input = []
    for addr in sorted(input_regs.keys()):
        value = input_regs[addr]
        if addr not in input_mapped and value != 0:
            interpretation = interpret_value(value)
            unmapped_input.append((addr, value, interpretation))
            print(f"  [{addr:3d}] = {value:5d} (0x{value:04X})  {interpretation}")

    print(f"\nTotal unmapped non-zero input registers: {len(unmapped_input)}")

    # Show mapped INPUT registers for reference
    print("\n" + "=" * 80)
    print("MAPPED INPUT REGISTERS (current values)")
    print("=" * 80)

    for addr in sorted(input_mapped.keys()):
        if addr in input_regs:
            value = input_regs[addr]
            name = input_mapped[addr]
            if value != 0:
                print(f"  [{addr:3d}] = {value:5d} -> {name}")

    # HOLDING registers (configuration parameters)
    print("\n" + "=" * 80)
    print("HOLDING REGISTERS (non-zero values, all)")
    print("=" * 80)

    for addr in sorted(holding_regs.keys()):
        value = holding_regs[addr]
        if value != 0:
            interpretation = interpret_value(value)
            print(f"  [{addr:3d}] = {value:5d} (0x{value:04X})  {interpretation}")

    # Compare webapp vs Modbus fields
    print("\n" + "=" * 80)
    print("WEB API vs MODBUS DATA AVAILABILITY")
    print("=" * 80)

    webapp_fields = get_webapp_fields()
    modbus_fields = get_modbus_fields()

    # Fields in webapp but not in Modbus
    print("\n--- WebAPI InverterRuntime fields NOT in Modbus ---")
    webapp_only = webapp_fields - modbus_fields
    # Filter out internal fields
    webapp_only = {
        f
        for f in webapp_only
        if not f.startswith("_")
        and f
        not in {
            "success",
            "model_config",
            "model_fields",
            "model_computed_fields",
        }
    }
    for field in sorted(webapp_only):
        print(f"  {field}")

    # Fields in Modbus but not in webapp
    print("\n--- Modbus InverterRuntimeData fields NOT in WebAPI ---")
    modbus_only = modbus_fields - webapp_fields
    for field in sorted(modbus_only):
        print(f"  {field}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Input registers read: {len(input_regs)}")
    print(f"Holding registers read: {len(holding_regs)}")
    print(f"Mapped input registers: {len(input_mapped)}")
    print(f"Unmapped input with data: {len(unmapped_input)}")
    print(f"WebAPI-only fields: {len(webapp_only)}")
    print(f"Modbus-only fields: {len(modbus_only)}")


if __name__ == "__main__":
    asyncio.run(main())
