#!/usr/bin/env python3
"""Diagnostic Data Collection Tool for pylxpweb.

This script collects comprehensive diagnostic information from Luxpower/EG4 inverter
systems for support and troubleshooting purposes. It gathers:
- Station and device hierarchy
- Runtime data from all devices (inverters, MID devices)
- Energy statistics
- Battery information (bank aggregate + individual modules)
- Parameter settings for all discovered devices:
  * Inverters (18KPV): 3 ranges (0-126, 127-253, 240-366) = 367 registers
  * MID devices (GridBOSS): 2 ranges (0-380, 2032-2158) = 508 registers
- System configuration

All sensitive information (addresses, serial numbers) is automatically sanitized.

Usage:
    python -m utils.collect_diagnostics --username USER --password PASS [options]

    # Or with environment variables
    export LUXPOWER_USERNAME=your_username
    export LUXPOWER_PASSWORD=your_password
    python -m utils.collect_diagnostics

    # Specify output file
    python -m utils.collect_diagnostics --output my_system_diagnostics.json

    # Use different API endpoint (EU/US Luxpower vs EG4)
    python -m utils.collect_diagnostics --base-url https://eu.luxpowertek.com
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pylxpweb.client import LuxpowerClient


def sanitize_value(key: str, value: Any) -> Any:
    """Sanitize sensitive information from diagnostic data.

    Args:
        key: The field name
        value: The field value

    Returns:
        Sanitized value (placeholder for sensitive data, original for safe data)
    """
    # Convert key to lowercase for case-insensitive matching
    key_lower = key.lower()

    # Serial numbers - replace with placeholder pattern
    if any(
        pattern in key_lower
        for pattern in [
            "serial",
            "sn",
            "serialnum",
            "device_sn",
            "inverter_sn",
        ]
    ):
        if isinstance(value, str) and value:
            # Keep first 2 and last 2 characters, mask middle
            if len(value) > 4:
                return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"
            return "*" * len(value)
        return value

    # Addresses - replace with placeholder
    if any(
        pattern in key_lower
        for pattern in [
            "address",
            "street",
            "location",
            "addr",
        ]
    ):
        if isinstance(value, str) and value:
            return "123 Example Street, City, State"
        return value

    # GPS coordinates - replace with generic coordinates
    if any(
        pattern in key_lower
        for pattern in [
            "latitude",
            "longitude",
            "lat",
            "lng",
            "lon",
        ]
    ):
        if isinstance(value, (int, float)):
            return 0.0
        return value

    # Plant/Station names that might contain addresses
    if "name" in key_lower and isinstance(value, str):
        # Check if it looks like an address (contains numbers and common address words)
        if re.search(
            r"\d+.*\b(street|st|avenue|ave|road|rd|drive|dr|way|lane|ln|boulevard|blvd|court|ct)\b",
            value.lower(),
        ):
            return "Example Station"
        return value

    # Recursively sanitize nested structures
    if isinstance(value, dict):
        return {k: sanitize_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_value(key, item) for item in value]

    return value


def sanitize_diagnostics(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively sanitize all sensitive information from diagnostic data.

    Args:
        data: Raw diagnostic data dictionary

    Returns:
        Sanitized diagnostic data with sensitive info replaced
    """
    return {key: sanitize_value(key, value) for key, value in data.items()}


async def collect_station_data(
    client: LuxpowerClient,
) -> dict[str, Any]:
    """Collect comprehensive diagnostic data from all stations.

    This function collects all available data including parameters for all discovered
    devices (inverters and MID devices). Parameter ranges are automatically selected
    based on device type:
    - Standard inverters (18KPV): 3 ranges (0-126, 127-253, 240-366)
    - MID devices (GridBOSS): 2 ranges (0-380, 2032-2158)

    Args:
        client: Authenticated LuxpowerClient instance

    Returns:
        Dictionary containing all diagnostic information including parameters
    """
    from pylxpweb.devices.station import Station

    print("🔍 Discovering stations...")
    stations = await Station.load_all(client)

    if not stations:
        print("❌ No stations found!")
        return {}

    print(f"✅ Found {len(stations)} station(s)\n")

    diagnostics: dict[str, Any] = {
        "collection_timestamp": datetime.now().isoformat(),
        "pylxpweb_version": "0.2.2",
        "base_url": client.base_url,
        "stations": [],
    }

    for idx, station in enumerate(stations, 1):
        print(f"📊 Processing Station {idx}/{len(stations)}: {station.name}")

        # Convert location to dict if it exists
        location = getattr(station, "location", None)
        location_dict = None
        if location:
            location_dict = {
                "lat": getattr(location, "lat", None),
                "lng": getattr(location, "lng", None),
                "address": getattr(location, "address", None),
            }

        station_data: dict[str, Any] = {
            "id": station.id,
            "name": station.name,
            "location": location_dict,
            "capacity": getattr(station, "capacity", None),
            "parallel_groups": [],
            "standalone_inverters": [],
        }

        # Collect parallel group data
        if station.parallel_groups:
            print(f"  ├─ {len(station.parallel_groups)} Parallel Group(s)")
            for group_idx, group in enumerate(station.parallel_groups, 1):
                print(f"  │  ├─ Group {group_idx}: {len(group.inverters)} inverter(s)")

                group_data: dict[str, Any] = {
                    "inverters": [],
                    "mid_device": None,
                }

                # Collect MID device data if present
                if group.mid_device:
                    print(f"  │  │  ├─ MID Device: {group.mid_device.serial_number}")
                    mid_data = await collect_mid_device_data(group.mid_device)
                    group_data["mid_device"] = mid_data

                # Collect inverter data
                for inv_idx, inverter in enumerate(group.inverters, 1):
                    print(f"  │  │  ├─ Inverter {inv_idx}: {inverter.serial_number}")
                    inv_data = await collect_inverter_data(inverter)
                    group_data["inverters"].append(inv_data)

                station_data["parallel_groups"].append(group_data)

        # Collect standalone inverter data
        if station.standalone_inverters:
            print(f"  ├─ {len(station.standalone_inverters)} Standalone Inverter(s)")
            for inv_idx, inverter in enumerate(station.standalone_inverters, 1):
                print(f"  │  ├─ Inverter {inv_idx}: {inverter.serial_number}")
                inv_data = await collect_inverter_data(inverter)
                station_data["standalone_inverters"].append(inv_data)

        diagnostics["stations"].append(station_data)
        print(f"  └─ ✅ Station {idx} complete\n")

    return diagnostics


async def collect_inverter_data(
    inverter: Any,
) -> dict[str, Any]:
    """Collect comprehensive data from a single inverter.

    Collects runtime data, energy data, battery information, and all parameters
    using the standard 18KPV register ranges (0-126, 127-253, 240-366).

    Args:
        inverter: Inverter instance (GenericInverter or HybridInverter)

    Returns:
        Dictionary containing inverter diagnostic data including parameters
    """
    inv_data: dict[str, Any] = {
        "serial_number": inverter.serial_number,
        "model": inverter.model,
        "inverter_class": inverter.__class__.__name__,
        "runtime_data": None,
        "energy_data": None,
        "battery_bank": None,
        "parameters": None,
    }

    # Collect runtime, energy, and battery data (single concurrent call)
    try:
        print("  │  │  │  ├─ Refreshing runtime/energy/battery data...")
        await inverter.refresh()

        if inverter.runtime:
            inv_data["runtime_data"] = inverter.runtime.model_dump()
            print("  │  │  │  │  ✅ Runtime data")

        if inverter.energy:
            inv_data["energy_data"] = inverter.energy.model_dump()
            print("  │  │  │  │  ✅ Energy data")

        if inverter.battery_bank:
            bank_data: dict[str, Any] = {
                "soc": inverter.battery_bank.soc,
                "voltage": inverter.battery_bank.voltage,
                "charge_power": inverter.battery_bank.charge_power,
                "discharge_power": inverter.battery_bank.discharge_power,
                "max_capacity": inverter.battery_bank.max_capacity,
                "current_capacity": inverter.battery_bank.current_capacity,
                "battery_count": inverter.battery_bank.battery_count,
                "batteries": [],
            }

            # Collect individual battery data
            for battery in inverter.battery_bank.batteries:
                battery_data = {
                    "battery_index": battery.battery_index,
                    "voltage": battery.voltage,
                    "current": battery.current,
                    "power": battery.power,
                    "soc": battery.soc,
                    "soh": battery.soh,
                    "max_cell_temp": battery.max_cell_temp,
                    "min_cell_temp": battery.min_cell_temp,
                    "max_cell_voltage": battery.max_cell_voltage,
                    "min_cell_voltage": battery.min_cell_voltage,
                    "cell_voltage_delta": battery.cell_voltage_delta,
                    "cycle_count": battery.cycle_count,
                    "firmware_version": battery.firmware_version,
                    "is_lost": battery.is_lost,
                }
                bank_data["batteries"].append(battery_data)

            inv_data["battery_bank"] = bank_data
            print(
                f"  │  │  │  │  ✅ Battery bank ({len(inverter.battery_bank.batteries)} batteries)"
            )

    except Exception as e:
        print(f"  │  │  │  │  ⚠️ Failed to collect runtime data: {e}")
        inv_data["runtime_error"] = str(e)

    # Collect parameter data - ALWAYS included for diagnostic purposes
    # Use device-specific parameter ranges based on device type
    # Standard Inverter (18KPV): 3 ranges covering registers 0-366
    # Reference: utils/README.md - Known Register Ranges
    try:
        print("  │  │  │  ├─ Reading parameters (3 ranges for 18KPV)...")
        params1 = await inverter.read_parameters(0, 127)  # 0-126: Primary config
        params2 = await inverter.read_parameters(127, 127)  # 127-253: Extended config
        params3 = await inverter.read_parameters(240, 127)  # 240-366: Advanced settings

        inv_data["parameters"] = {
            "range_0_126": params1,
            "range_127_253": params2,
            "range_240_366": params3,
        }
        print("  │  │  │  │  ✅ Parameters (3 ranges, 367 registers)")
    except Exception as e:
        print(f"  │  │  │  │  ⚠️ Failed to collect parameters: {e}")
        inv_data["parameters_error"] = str(e)

    return inv_data


async def collect_mid_device_data(
    mid_device: Any,
) -> dict[str, Any]:
    """Collect comprehensive data from a MID device (GridBOSS).

    Args:
        mid_device: MIDDevice instance

    Returns:
        Dictionary containing MID device diagnostic data
    """
    mid_data: dict[str, Any] = {
        "serial_number": mid_device.serial_number,
        "model": mid_device.model,
        "runtime_data": None,
        "parameters": None,
    }

    # Collect runtime data
    try:
        print("  │  │  │  ├─ Refreshing MID device runtime data...")
        await mid_device.refresh()

        if mid_device.runtime:
            mid_data["runtime_data"] = mid_device.runtime.model_dump()
            print("  │  │  │  │  ✅ Runtime data")

    except Exception as e:
        print(f"  │  │  │  │  ⚠️ Failed to collect runtime data: {e}")
        mid_data["runtime_error"] = str(e)

    # Collect parameter data - GridBOSS specific ranges
    # GridBOSS: 2 ranges covering registers 0-380 and 2032-2158
    # Reference: utils/README.md - Known Register Ranges
    try:
        print("  │  │  │  ├─ Reading parameters (2 ranges for GridBOSS)...")
        params1 = await mid_device.read_parameters(0, 381)  # 0-380: Standard config
        params2 = await mid_device.read_parameters(2032, 127)  # 2032-2158: GridBOSS features

        mid_data["parameters"] = {
            "range_0_380": params1,
            "range_2032_2158": params2,
        }
        print("  │  │  │  │  ✅ Parameters (2 ranges, 508 registers)")
    except Exception as e:
        print(f"  │  │  │  │  ⚠️ Failed to collect parameters: {e}")
        mid_data["parameters_error"] = str(e)

    return mid_data


async def main() -> None:
    """Main entry point for diagnostic collection script."""
    parser = argparse.ArgumentParser(
        description="Collect diagnostic data from Luxpower/EG4 inverter systems",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with credentials
  python -m utils.collect_diagnostics --username USER --password PASS

  # Use environment variables
  export LUXPOWER_USERNAME=your_username
  export LUXPOWER_PASSWORD=your_password
  python -m utils.collect_diagnostics

  # Specify output file
  python -m utils.collect_diagnostics --output my_diagnostics.json

  # Use EU Luxpower endpoint
  python -m utils.collect_diagnostics --base-url https://eu.luxpowertek.com

Regional API Endpoints:
  - EG4 (US):          https://monitor.eg4electronics.com (default)
  - Luxpower (US):     https://us.luxpowertek.com
  - Luxpower (EU):     https://eu.luxpowertek.com

Parameter Collection:
  Parameters are automatically collected for all discovered devices using
  device-specific register ranges for maximum compatibility:
  - Standard Inverters: 367 registers across 3 ranges
  - MID/GridBOSS Devices: 508 registers across 2 ranges
        """,
    )

    parser.add_argument(
        "--username",
        help="Luxpower/EG4 account username (or set LUXPOWER_USERNAME env var)",
        default=os.getenv("LUXPOWER_USERNAME"),
    )
    parser.add_argument(
        "--password",
        help="Luxpower/EG4 account password (or set LUXPOWER_PASSWORD env var)",
        default=os.getenv("LUXPOWER_PASSWORD"),
    )
    parser.add_argument(
        "--base-url",
        help="API base URL (default: EG4 monitor)",
        default=os.getenv("LUXPOWER_BASE_URL", "https://monitor.eg4electronics.com"),
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (default: diagnostics_TIMESTAMP.json)",
        default=None,
    )
    parser.add_argument(
        "--no-sanitize",
        action="store_true",
        help="Disable automatic sanitization of sensitive data (NOT RECOMMENDED)",
    )

    args = parser.parse_args()

    # Validate credentials
    if not args.username or not args.password:
        parser.error(
            "Username and password required. Provide via --username/--password or "
            "set LUXPOWER_USERNAME/LUXPOWER_PASSWORD environment variables."
        )

    # Generate output filename if not specified
    if args.output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = f"diagnostics_{timestamp}.json"

    print("╔═══════════════════════════════════════════════════════════╗")
    print("║  Luxpower/EG4 Diagnostic Data Collection Tool            ║")
    print("║  pylxpweb v0.2.2                                          ║")
    print("╚═══════════════════════════════════════════════════════════╝\n")

    print(f"🌐 API Endpoint: {args.base_url}")
    print(f"👤 Username: {args.username}")
    print("📊 Parameters: Included for all devices")
    print(f"🔒 Sanitize Data: {not args.no_sanitize}")
    print(f"💾 Output File: {args.output}\n")

    # Create client and authenticate
    try:
        print("🔐 Authenticating...")
        async with LuxpowerClient(
            username=args.username,
            password=args.password,
            base_url=args.base_url,
        ) as client:
            print("✅ Authentication successful!\n")

            # Collect diagnostic data (includes all parameters automatically)
            diagnostics = await collect_station_data(client)

            if not diagnostics.get("stations"):
                print("\n❌ No data collected. Exiting.")
                return

            # Sanitize data if requested
            if not args.no_sanitize:
                print("🔒 Sanitizing sensitive information...")
                diagnostics = sanitize_diagnostics(diagnostics)
                print("✅ Data sanitized\n")

            # Write to file
            print(f"💾 Writing diagnostic data to {args.output}...")
            output_path = Path(args.output)
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(diagnostics, f, indent=2, ensure_ascii=False)

            file_size = output_path.stat().st_size / 1024  # KB
            print(f"✅ Diagnostic data saved ({file_size:.1f} KB)\n")

            # Summary
            print("╔═══════════════════════════════════════════════════════════╗")
            print("║  Collection Summary                                       ║")
            print("╚═══════════════════════════════════════════════════════════╝")
            print(f"Stations: {len(diagnostics['stations'])}")

            total_inverters = 0
            total_batteries = 0
            for station in diagnostics["stations"]:
                for group in station.get("parallel_groups", []):
                    total_inverters += len(group.get("inverters", []))
                    for inv in group.get("inverters", []):
                        if inv.get("battery_bank"):
                            total_batteries += len(inv["battery_bank"].get("batteries", []))

                for inv in station.get("standalone_inverters", []):
                    total_inverters += 1
                    if inv.get("battery_bank"):
                        total_batteries += len(inv["battery_bank"].get("batteries", []))

            print(f"Inverters: {total_inverters}")
            print(f"Batteries: {total_batteries}")
            print("\n✅ Diagnostic collection complete!")
            print(f"\n📎 Share this file for support: {args.output}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
