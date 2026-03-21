#!/usr/bin/env python3
"""Validate register-to-parameter mappings by comparing HTTP vs local transport.

This script reads hold parameters from both the web API (HTTP) and local transport
(Dongle/Modbus), then compares the results to validate our register mappings.

Usage:
    uv run python scripts/validate_register_mappings.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")


async def validate_18kpv() -> None:
    """Validate 18kPV register mappings via Dongle vs HTTP."""
    from pylxpweb import LuxpowerClient
    from pylxpweb.devices.inverters._features import InverterFamily
    from pylxpweb.transports import create_dongle_transport, create_http_transport

    dongle_ip = os.environ.get("DONGLE_IP")
    dongle_serial = os.environ.get("DONGLE_SERIAL")
    inverter_serial = os.environ.get("DONGLE_INVERTER_SERIAL")
    username = os.environ.get("LUXPOWER_USERNAME")
    password = os.environ.get("LUXPOWER_PASSWORD")
    base_url = os.environ.get("LUXPOWER_BASE_URL")

    if not all([dongle_ip, dongle_serial, inverter_serial, username, password]):
        print("⚠️  18kPV: Missing environment variables, skipping")
        return

    print("\n" + "=" * 70)
    print("18kPV VALIDATION (Dongle vs HTTP)")
    print("=" * 70)
    print(f"Dongle IP: {dongle_ip}")
    print(f"Inverter Serial: {inverter_serial}")

    # Create transports
    async with LuxpowerClient(username, password, base_url=base_url) as client:
        http_transport = create_http_transport(client, inverter_serial)
        dongle_transport = create_dongle_transport(
            host=dongle_ip,
            dongle_serial=dongle_serial,
            inverter_serial=inverter_serial,
            inverter_family=InverterFamily.PV_SERIES,
        )

        await http_transport.connect()
        await dongle_transport.connect()

        try:
            await _compare_parameters(http_transport, dongle_transport, "HTTP", "Dongle")
        finally:
            await dongle_transport.disconnect()
            await http_transport.disconnect()


async def validate_flexboss() -> None:
    """Validate FlexBOSS21 register mappings via Modbus vs HTTP."""
    from pylxpweb import LuxpowerClient
    from pylxpweb.devices.inverters._features import InverterFamily
    from pylxpweb.transports import create_http_transport, create_modbus_transport

    modbus_ip = os.environ.get("MODBUS_IP")
    modbus_port = int(os.environ.get("MODBUS_PORT", "502"))
    inverter_serial = os.environ.get("MODBUS_SERIAL")
    username = os.environ.get("LUXPOWER_USERNAME")
    password = os.environ.get("LUXPOWER_PASSWORD")
    base_url = os.environ.get("LUXPOWER_BASE_URL")

    if not all([modbus_ip, inverter_serial, username, password]):
        print("⚠️  FlexBOSS21: Missing environment variables, skipping")
        return

    print("\n" + "=" * 70)
    print("FLEXBOSS21 VALIDATION (Modbus vs HTTP)")
    print("=" * 70)
    print(f"Modbus IP: {modbus_ip}:{modbus_port}")
    print(f"Inverter Serial: {inverter_serial}")

    # Create transports
    async with LuxpowerClient(username, password, base_url=base_url) as client:
        http_transport = create_http_transport(client, inverter_serial)
        modbus_transport = create_modbus_transport(
            host=modbus_ip,
            serial=inverter_serial,
            port=modbus_port,
            inverter_family=InverterFamily.PV_SERIES,  # FlexBOSS uses PV_SERIES
        )

        await http_transport.connect()
        await modbus_transport.connect()

        try:
            await _compare_parameters(http_transport, modbus_transport, "HTTP", "Modbus")
        finally:
            await modbus_transport.disconnect()
            await http_transport.disconnect()


async def _compare_parameters(
    http_transport,
    local_transport,
    http_name: str,
    local_name: str,
) -> None:
    """Compare parameters between HTTP and local transport."""
    print("\n--- Reading parameters ---")

    all_http_params: dict[str, int] = {}
    all_local_params: dict[str, int] = {}

    # Standard parameter ranges (matching HA integration's read pattern)
    # API limit is 127 registers per call
    register_ranges = [
        (0, 127),  # Base parameters
        (127, 127),  # Extended parameters 1
        (240, 127),  # Extended parameters 2
    ]

    for start, count in register_ranges:
        print(f"  Registers {start}-{start + count - 1} ({count} regs)...")

        # HTTP returns named parameters directly from server
        http_params = await http_transport.read_named_parameters(start, count)

        # Local uses our mapping
        local_params = await local_transport.read_named_parameters(start, count)

        all_http_params.update(http_params)
        all_local_params.update(local_params)

        # Small delay to avoid rate limiting
        await asyncio.sleep(0.3)

    # Compare results
    print("\n--- Comparison Results ---")

    http_keys = set(all_http_params.keys())
    local_keys = set(all_local_params.keys())

    # Keys only in HTTP (we're missing mappings)
    http_only = http_keys - local_keys
    if http_only:
        print(f"\n⚠️  Keys in {http_name} but not {local_name} ({len(http_only)}):")
        for key in sorted(http_only)[:20]:
            print(f"    {key}: {all_http_params[key]}")
        if len(http_only) > 20:
            print(f"    ... and {len(http_only) - 20} more")

    # Keys only in local (extra mappings or numeric fallbacks)
    local_only = local_keys - http_keys
    if local_only:
        print(f"\n⚠️  Keys in {local_name} but not {http_name} ({len(local_only)}):")
        for key in sorted(local_only)[:20]:
            print(f"    {key}: {all_local_params[key]}")
        if len(local_only) > 20:
            print(f"    ... and {len(local_only) - 20} more")

    # Common keys - check value mismatches (normalize types for comparison)
    common_keys = http_keys & local_keys
    mismatches: list[tuple[str, Any, Any]] = []

    def normalize(val: Any) -> Any:
        """Normalize value for comparison (handle str/int/bool differences)."""
        if isinstance(val, str):
            # Try to convert numeric strings
            if val.isdigit():
                return int(val)
            if val.lower() in ("true", "false"):
                return val.lower() == "true"
        return val

    for key in common_keys:
        http_val = normalize(all_http_params[key])
        local_val = normalize(all_local_params[key])
        if http_val != local_val:
            mismatches.append((key, all_http_params[key], all_local_params[key]))

    if mismatches:
        print(f"\n❌ Value mismatches ({len(mismatches)}):")
        for key, http_val, local_val in sorted(mismatches)[:20]:
            print(f"    {key}: {http_name}={http_val}, {local_name}={local_val}")
        if len(mismatches) > 20:
            print(f"    ... and {len(mismatches) - 20} more")
    else:
        print(f"\n✅ All {len(common_keys)} common parameters have matching values!")

    # Summary
    print("\n--- Summary ---")
    print(f"  {http_name} parameters: {len(http_keys)}")
    print(f"  {local_name} parameters: {len(local_keys)}")
    print(f"  Common parameters: {len(common_keys)}")
    print(f"  Only in {http_name}: {len(http_only)}")
    print(f"  Only in {local_name}: {len(local_only)}")
    print(f"  Value mismatches: {len(mismatches)}")


async def dump_http_mapping(serial: str, output_file: str) -> None:
    """Dump HTTP parameter mapping to a file for analysis."""
    import json

    from pylxpweb import LuxpowerClient
    from pylxpweb.transports import create_http_transport

    username = os.environ.get("LUXPOWER_USERNAME")
    password = os.environ.get("LUXPOWER_PASSWORD")
    base_url = os.environ.get("LUXPOWER_BASE_URL")

    async with LuxpowerClient(username, password, base_url=base_url) as client:
        http_transport = create_http_transport(client, serial)
        await http_transport.connect()

        all_params: dict[str, int] = {}
        register_ranges = [(0, 127), (127, 127), (240, 127)]

        for start, count in register_ranges:
            params = await http_transport.read_named_parameters(start, count)
            all_params.update(params)
            await asyncio.sleep(0.3)

        await http_transport.disconnect()

        # Sort by key and save
        sorted_params = dict(sorted(all_params.items()))
        with open(output_file, "w") as f:
            json.dump(sorted_params, f, indent=2)

        print(f"Saved {len(sorted_params)} parameters to {output_file}")


async def main() -> None:
    """Run all validations."""
    print("=" * 70)
    print("REGISTER MAPPING VALIDATION")
    print("Comparing Web API (HTTP) vs Local Transport (Dongle/Modbus)")
    print("=" * 70)

    # Run validations
    try:
        await validate_18kpv()
    except Exception as e:
        print(f"\n❌ 18kPV validation failed: {e}")

    try:
        await validate_flexboss()
    except Exception as e:
        print(f"\n❌ FlexBOSS21 validation failed: {e}")

    print("\n" + "=" * 70)
    print("VALIDATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
