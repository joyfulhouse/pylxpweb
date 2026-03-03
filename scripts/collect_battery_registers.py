#!/usr/bin/env python3
"""Collect raw battery register dumps for protocol discovery.

Scans a battery RS485 bus, reads all accessible registers, and outputs
structured JSON for analysis, protocol development, and debugging.

Usage:
    uv run python scripts/collect_battery_registers.py --host 10.100.3.27
    uv run python scripts/collect_battery_registers.py --host 10.100.3.27 \
        --unit 1 --output dump.json
    uv run python scripts/collect_battery_registers.py --host 10.100.3.27 --max-units 8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import struct
import sys
from datetime import UTC, datetime

from pymodbus.client import AsyncModbusTcpClient


async def try_read(
    client: AsyncModbusTcpClient,
    start: int,
    count: int,
    unit_id: int,
    func: str = "holding",
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
    client: AsyncModbusTcpClient,
    unit_id: int,
    verbose: bool = True,
) -> dict | None:
    """Collect all accessible registers from a single battery unit."""
    unit_data: dict = {
        "unit_id": unit_id,
        "holding_registers": {},
        "input_registers": {},
        "detected_protocol": "unknown",
        "decoded": {},
    }

    # Read holding and input registers in chunks
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

    # Auto-detect protocol: master has regs 0-18 mostly zero, data starts at reg 19+
    early_non_zero = 0
    for r in range(0, 19):
        if str(r) in unit_data["holding_registers"]:
            early_non_zero += 1

    if early_non_zero <= 2:
        unit_data["detected_protocol"] = "eg4_master"
    else:
        unit_data["detected_protocol"] = "eg4_slave"

    # Decode key values based on detected protocol
    decoded: dict = {}
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
        # Cell voltages at register 113+
        cells = []
        for i in range(16):
            key = str(113 + i)
            if key in hold:
                cells.append(hold[key]["raw"] / 1000.0)
        if cells:
            decoded["cell_voltages"] = cells
    else:
        # Slave protocol: standard EG4-LL register map
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
        # Cell voltages at register 2+
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
        print("Battery Register Collector")
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
            "timestamp": datetime.now(tz=UTC).isoformat(),
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
            print(f"\n{'=' * 60}")
            print("JSON OUTPUT")
            print("=" * 60)
        print(json_str)


if __name__ == "__main__":
    asyncio.run(main())
