#!/usr/bin/env python3
"""Compare FlexBOSS21 Modbus registers with web API data availability.

Reads all registers from the FlexBOSS21 via Modbus TCP and identifies:
1. Registers that contain non-zero data
2. Registers that are not mapped in the current register_maps.py
3. Comparison with InverterRuntime fields available via web API
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Suppress pymodbus debug output
logging.getLogger("pymodbus").setLevel(logging.WARNING)

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
load_dotenv(Path(__file__).parent.parent / ".env")


@dataclass
class RegisterInfo:
    """Information about a register."""

    address: int
    value: int
    mapped: bool = False
    mapped_name: str = ""
    scale_info: str = ""


@dataclass
class RegisterScanResult:
    """Results from scanning registers."""

    input_registers: dict[int, int] = field(default_factory=dict)
    holding_registers: dict[int, int] = field(default_factory=dict)
    individual_battery_registers: dict[int, int] = field(default_factory=dict)


def get_mapped_input_registers() -> dict[int, str]:
    """Get all registers mapped in PV_SERIES_RUNTIME_MAP and PV_SERIES_ENERGY_MAP."""
    from pylxpweb.transports.register_maps import (
        PV_SERIES_ENERGY_MAP,
        PV_SERIES_RUNTIME_MAP,
    )

    mapped: dict[int, str] = {}

    # Extract from runtime map
    for field_name in dir(PV_SERIES_RUNTIME_MAP):
        if field_name.startswith("_"):
            continue
        field_def = getattr(PV_SERIES_RUNTIME_MAP, field_name)
        if hasattr(field_def, "address"):
            mapped[field_def.address] = f"runtime.{field_name}"
            if field_def.bit_width == 32:
                mapped[field_def.address + 1] = f"runtime.{field_name} (high/low)"

    # Extract from energy map
    for field_name in dir(PV_SERIES_ENERGY_MAP):
        if field_name.startswith("_"):
            continue
        field_def = getattr(PV_SERIES_ENERGY_MAP, field_name)
        if hasattr(field_def, "address"):
            mapped[field_def.address] = f"energy.{field_name}"
            if field_def.bit_width == 32:
                mapped[field_def.address + 1] = f"energy.{field_name} (high/low)"

    return mapped


def get_webapp_runtime_fields() -> dict[str, str]:
    """Get all fields available in InverterRuntime from web API."""
    from pylxpweb.models import InverterRuntime

    fields: dict[str, str] = {}
    for field_name, field_info in InverterRuntime.model_fields.items():
        fields[field_name] = str(field_info.annotation)
    return fields


async def scan_registers(
    host: str,
    port: int,
    unit_id: int = 1,
) -> RegisterScanResult:
    """Scan all registers from the inverter."""
    from pymodbus.client import AsyncModbusTcpClient

    result = RegisterScanResult()

    print(f"Connecting to {host}:{port}...")
    client = AsyncModbusTcpClient(host=host, port=port, timeout=10.0)
    connected = await client.connect()

    if not connected:
        print("Failed to connect!")
        return result

    print("Connected. Scanning registers...")

    # Read input registers 0-127 (standard range)
    print("\n--- Input Registers 0-127 ---")
    for start in range(0, 128, 40):
        count = min(40, 128 - start)
        try:
            resp = await client.read_input_registers(address=start, count=count, device_id=unit_id)
            if not resp.isError() and hasattr(resp, "registers"):
                for offset, value in enumerate(resp.registers):
                    result.input_registers[start + offset] = value
        except Exception as e:
            print(f"  Error reading {start}-{start + count}: {e}")

    # Read extended input registers 128-255
    print("\n--- Input Registers 128-255 ---")
    for start in range(128, 256, 40):
        count = min(40, 256 - start)
        try:
            resp = await client.read_input_registers(address=start, count=count, device_id=unit_id)
            if not resp.isError() and hasattr(resp, "registers"):
                for offset, value in enumerate(resp.registers):
                    result.input_registers[start + offset] = value
        except Exception as e:
            print(f"  Error reading {start}-{start + count}: {e}")

    # Read holding registers 0-127
    print("\n--- Holding Registers 0-127 ---")
    for start in range(0, 128, 40):
        count = min(40, 128 - start)
        try:
            resp = await client.read_holding_registers(
                address=start, count=count, device_id=unit_id
            )
            if not resp.isError() and hasattr(resp, "registers"):
                for offset, value in enumerate(resp.registers):
                    result.holding_registers[start + offset] = value
        except Exception as e:
            print(f"  Error reading {start}-{start + count}: {e}")

    # Read holding registers 128-255
    print("\n--- Holding Registers 128-255 ---")
    for start in range(128, 256, 40):
        count = min(40, 256 - start)
        try:
            resp = await client.read_holding_registers(
                address=start, count=count, device_id=unit_id
            )
            if not resp.isError() and hasattr(resp, "registers"):
                for offset, value in enumerate(resp.registers):
                    result.holding_registers[start + offset] = value
        except Exception as e:
            print(f"  Error reading {start}-{start + count}: {e}")

    # Read individual battery registers (5000-5150)
    # Note: These may not be available on all inverters
    print("\n--- Individual Battery Registers 5000-5150 ---")
    battery_read_failed = False
    for start in range(5000, 5152, 40):
        if battery_read_failed:
            break  # Skip if already failed
        count = min(40, 5152 - start)
        try:
            resp = await asyncio.wait_for(
                client.read_input_registers(address=start, count=count, device_id=unit_id),
                timeout=5.0,
            )
            if not resp.isError() and hasattr(resp, "registers"):
                for offset, value in enumerate(resp.registers):
                    result.individual_battery_registers[start + offset] = value
            else:
                print("  Registers 5000+ not available on this device")
                battery_read_failed = True
        except TimeoutError:
            print("  Timeout reading battery registers - skipping")
            battery_read_failed = True
        except Exception as e:
            print(f"  Error reading {start}-{start + count}: {e}")
            battery_read_failed = True

    client.close()
    return result


def analyze_unmapped_registers(
    scan_result: RegisterScanResult,
    mapped_registers: dict[int, str],
) -> None:
    """Analyze and report unmapped registers with non-zero values."""
    print("\n" + "=" * 80)
    print("UNMAPPED INPUT REGISTERS WITH NON-ZERO VALUES")
    print("=" * 80)

    unmapped_count = 0
    for addr in sorted(scan_result.input_registers.keys()):
        value = scan_result.input_registers[addr]
        if addr not in mapped_registers and value != 0:
            unmapped_count += 1
            # Try to interpret the value
            interpretation = ""
            if 32 <= value <= 126:
                interpretation = f" (ASCII: {chr(value)})"
            elif value > 32767:
                signed = value - 65536
                interpretation = f" (signed: {signed})"

            print(f"  Reg {addr:3d}: {value:5d} (0x{value:04X}){interpretation}")

    if unmapped_count == 0:
        print("  (all non-zero registers are mapped)")

    # Also show mapped registers for comparison
    print("\n" + "=" * 80)
    print("MAPPED INPUT REGISTERS (current values)")
    print("=" * 80)

    for addr in sorted(mapped_registers.keys()):
        if addr in scan_result.input_registers:
            value = scan_result.input_registers[addr]
            name = mapped_registers[addr]
            if value != 0:
                print(f"  Reg {addr:3d}: {value:5d} -> {name}")


def analyze_webapp_vs_modbus() -> None:
    """Compare web API fields with Modbus register availability."""
    from pylxpweb.transports.data import InverterRuntimeData

    print("\n" + "=" * 80)
    print("WEB API FIELDS vs MODBUS DATA AVAILABILITY")
    print("=" * 80)

    webapp_fields = get_webapp_runtime_fields()
    modbus_fields = {f.name for f in InverterRuntimeData.__dataclass_fields__.values()}

    # Fields in webapp but not in Modbus data model
    print("\n--- Fields in WebAPI InverterRuntime NOT in Modbus InverterRuntimeData ---")
    webapp_only = set(webapp_fields.keys()) - modbus_fields - {"model_fields"}
    for field_name in sorted(webapp_only):
        if not field_name.startswith("_") and field_name not in (
            "success",
            "model_config",
            "model_fields",
            "model_computed_fields",
            "pac",
        ):
            print(f"  {field_name}: {webapp_fields[field_name]}")

    print("\n--- Fields in Modbus InverterRuntimeData NOT in WebAPI InverterRuntime ---")
    modbus_only = modbus_fields - set(webapp_fields.keys())
    for field_name in sorted(modbus_only):
        print(f"  {field_name}")


def format_battery_registers(
    registers: dict[int, int],
) -> None:
    """Format and display individual battery register data."""
    print("\n" + "=" * 80)
    print("INDIVIDUAL BATTERY REGISTERS (5000+)")
    print("=" * 80)

    if not registers:
        print("  (no battery registers read)")
        return

    # Battery block structure (30 registers per battery)
    # Offset 0: Status header (0xC003 = connected)
    # Offset 1: Full capacity (Ah)
    # Offset 2: Charge voltage ref (÷10 = V)
    # Offset 3: Charge current limit (÷100 = A)
    # Offset 4: Discharge current limit (÷100 = A)
    # Offset 5: Discharge voltage cutoff (÷10 = V)
    # Offset 6: Battery voltage (÷100 = V)
    # Offset 7: Current (÷10 = A, signed)
    # Offset 8: SOC (low byte) / SOH (high byte)
    # Offset 9: Cycle count
    # Offset 10: Max cell temp (÷10 = °C)
    # Offset 11: Min cell temp (÷10 = °C)
    # Offset 12: Max cell voltage (mV)
    # Offset 13: Min cell voltage (mV)
    # Offset 14: Cell num voltage packed (low=max, high=min)
    # Offset 15: Cell num temp packed (low=max, high=min)
    # Offset 16: Firmware version (high=major, low=minor)
    # Offset 17-23: Serial number (7 registers)
    # Offset 24-29: Reserved/unknown

    for battery_idx in range(5):
        base = 5002 + (battery_idx * 30)
        status = registers.get(base, 0)
        if status == 0:
            continue

        print(f"\n  Battery {battery_idx + 1} (base: {base}):")
        print(f"    Status: 0x{status:04X}")

        # Show all 30 registers for this battery
        for offset in range(30):
            addr = base + offset
            value = registers.get(addr, 0)
            if value == 0:
                continue

            label = ""
            scaled = ""
            if offset == 1:
                label = "Capacity"
                scaled = f" ({value} Ah)"
            elif offset == 2:
                label = "ChargeVoltRef"
                scaled = f" ({value / 10:.1f} V)"
            elif offset == 3:
                label = "ChargeCurrLim"
                scaled = f" ({value / 100:.2f} A)"
            elif offset == 4:
                label = "DischgCurrLim"
                scaled = f" ({value / 100:.2f} A)"
            elif offset == 5:
                label = "DischgVoltCut"
                scaled = f" ({value / 10:.1f} V)"
            elif offset == 6:
                label = "Voltage"
                scaled = f" ({value / 100:.2f} V)"
            elif offset == 7:
                label = "Current"
                signed = value - 65536 if value > 32767 else value
                scaled = f" ({signed / 10:.1f} A)"
            elif offset == 8:
                soc = value & 0xFF
                soh = (value >> 8) & 0xFF
                label = "SOC/SOH"
                scaled = f" (SOC={soc}%, SOH={soh}%)"
            elif offset == 9:
                label = "CycleCount"
            elif offset == 10:
                label = "MaxCellTemp"
                scaled = f" ({value / 10:.1f}°C)"
            elif offset == 11:
                label = "MinCellTemp"
                scaled = f" ({value / 10:.1f}°C)"
            elif offset == 12:
                label = "MaxCellVolt"
                scaled = f" ({value} mV)"
            elif offset == 13:
                label = "MinCellVolt"
                scaled = f" ({value} mV)"
            elif offset == 14:
                label = "CellNumVolt"
                scaled = f" (max=#{value & 0xFF}, min=#{(value >> 8) & 0xFF})"
            elif offset == 15:
                label = "CellNumTemp"
                scaled = f" (max=#{value & 0xFF}, min=#{(value >> 8) & 0xFF})"
            elif offset == 16:
                label = "FW Version"
                major = (value >> 8) & 0xFF
                minor = value & 0xFF
                scaled = f" ({major}.{minor})"
            elif 17 <= offset <= 23:
                label = f"Serial[{offset - 17}]"
                low = chr(value & 0xFF) if 32 <= (value & 0xFF) <= 126 else "?"
                high = chr((value >> 8) & 0xFF) if 32 <= ((value >> 8) & 0xFF) <= 126 else "?"
                scaled = f" ('{low}{high}')"
            else:
                label = "Unknown"

            print(f"    [{offset:2d}] {addr:5d}: {value:5d} (0x{value:04X}) - {label}{scaled}")


async def main() -> None:
    """Main entry point."""
    # Get connection details from environment
    host = os.getenv("MODBUS_IP", "172.16.40.98")
    port = int(os.getenv("MODBUS_PORT", "502"))
    serial = os.getenv("MODBUS_SERIAL", "unknown")

    print("FlexBOSS21 Unmapped Register Scanner")
    print(f"Target: {host}:{port} (Serial: {serial})")
    print("=" * 80)

    # Get mapped registers
    mapped_registers = get_mapped_input_registers()
    print(f"Currently mapped input registers: {len(mapped_registers)}")

    # Scan all registers
    scan_result = await scan_registers(host, port)

    print(f"\nRead {len(scan_result.input_registers)} input registers")
    print(f"Read {len(scan_result.holding_registers)} holding registers")
    print(f"Read {len(scan_result.individual_battery_registers)} battery registers")

    # Analyze unmapped registers
    analyze_unmapped_registers(scan_result, mapped_registers)

    # Show individual battery data
    format_battery_registers(scan_result.individual_battery_registers)

    # Compare webapp vs modbus
    analyze_webapp_vs_modbus()

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    non_zero_unmapped = sum(
        1
        for addr, val in scan_result.input_registers.items()
        if addr not in mapped_registers and val != 0
    )
    print(f"Total input registers scanned: {len(scan_result.input_registers)}")
    print(f"Registers with mappings: {len(mapped_registers)}")
    print(f"Unmapped registers with non-zero values: {non_zero_unmapped}")


if __name__ == "__main__":
    asyncio.run(main())
