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
import dataclasses
import json
import sys
from datetime import UTC, datetime
from typing import Any

from pymodbus.client import AsyncModbusTcpClient

from pylxpweb.battery_protocols.base import signed_int16
from pylxpweb.battery_protocols.detection import detect_protocol


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


async def collect_unit(
    client: AsyncModbusTcpClient,
    unit_id: int,
    verbose: bool = True,
) -> dict[str, Any] | None:
    """Collect all accessible registers from a single battery unit."""
    unit_data: dict[str, Any] = {
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
                            "signed": signed_int16(val),
                        }
            await asyncio.sleep(0.15)

    if not unit_data["holding_registers"] and not unit_data["input_registers"]:
        return None

    # Build int-keyed dict for library detection and decode
    raw_int: dict[int, int] = {}
    for addr_str, info in unit_data["holding_registers"].items():
        raw_int[int(addr_str)] = info["raw"]

    # Auto-detect protocol using library
    protocol = detect_protocol(raw_int)
    unit_data["detected_protocol"] = protocol.name

    # Decode using the protocol's decode() method
    battery_data = protocol.decode(raw_int, battery_index=unit_id - 1)
    decoded = dataclasses.asdict(battery_data)
    # Remove None values and empty lists for cleaner output
    unit_data["decoded"] = {k: v for k, v in decoded.items() if v is not None and v != []}

    if verbose:
        v = battery_data.voltage
        soc = battery_data.soc
        print(f"  Unit {unit_id}: {protocol.name}  V={v}  SOC={soc}")

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

    output: dict[str, Any] = {
        "metadata": {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "host": args.host,
            "port": args.port,
            "tool_version": "1.1.0",
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
