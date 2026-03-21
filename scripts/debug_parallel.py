#!/usr/bin/env python3
"""Parallel Group Diagnostic Script for EG4/LuxPower systems.

Dumps raw API responses for parallel group discovery to help debug
missing or broken parallel group data.

Usage:
    uv run python scripts/debug_parallel.py -u YOUR_USERNAME -p YOUR_PASSWORD

For EU LuxPower portal:
    uv run python scripts/debug_parallel.py -u YOUR_USERNAME -p YOUR_PASSWORD -b https://eu.luxpowertek.com
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime


async def main(username: str, password: str, base_url: str) -> None:
    from pylxpweb import LuxpowerClient
    from pylxpweb.devices import Station

    print("=== Parallel Group Diagnostic ===")
    print(f"Timestamp: {datetime.now(UTC).isoformat()}")
    print(f"Base URL: {base_url}")
    print()

    async with LuxpowerClient(username, password, base_url=base_url) as client:
        # 1. Get all plants
        print("--- Step 1: Plant Discovery ---")
        plants_response = await client.api.plants.get_plants()
        for plant in plants_response.rows:
            print(f"  Plant: {plant.plantName} (ID: {plant.id})")
        print()

        # 2. For each plant, get device list
        for plant in plants_response.rows:
            print(f"--- Step 2: Device List for '{plant.plantName}' (ID: {plant.id}) ---")
            devices = await client.api.devices.get_inverter_overview(plant.id)
            gridboss_serial = None

            for dev in devices.rows:
                dev_dict = dev.model_dump()
                # Sanitize serial
                serial = dev_dict.get("serialNum", "")
                safe_serial = serial[:4] + "X" * (len(serial) - 4) if len(serial) > 4 else serial
                dev_dict["serialNum"] = safe_serial
                if "datalogSn" in dev_dict:
                    dsn = dev_dict["datalogSn"]
                    dev_dict["datalogSn"] = dsn[:4] + "X" * (len(dsn) - 4) if len(dsn) > 4 else dsn

                print(f"  Device: {safe_serial}")
                print(f"    Model: {dev_dict.get('deviceType', 'N/A')}")
                print(f"    Parallel Group: {dev_dict.get('parallelGroup', 'N/A')}")
                print(f"    Device Type: {dev_dict.get('devType', 'N/A')}")
                print(f"    Status: {dev_dict.get('status', 'N/A')}")

                # Detect GridBOSS (devType 5 = MID device)
                if dev.devType == 5:
                    gridboss_serial = serial
                    print("    ** GridBOSS detected **")
                print()

            # 3. Get parallel group details
            print("--- Step 3: Parallel Group Details ---")
            if gridboss_serial:
                safe_gb = gridboss_serial[:4] + "X" * (len(gridboss_serial) - 4)
                print(f"  Using GridBOSS serial: {safe_gb}")
                try:
                    pg_response = await client.api.devices.get_parallel_group_details(
                        gridboss_serial
                    )
                    pg_dict = pg_response.model_dump()

                    # Sanitize serials in response
                    if "devices" in pg_dict and pg_dict["devices"]:
                        for d in pg_dict["devices"]:
                            if "serialNum" in d:
                                s = d["serialNum"]
                                d["serialNum"] = s[:4] + "X" * (len(s) - 4) if len(s) > 4 else s

                    print(f"  Total devices in response: {pg_dict.get('total', 'N/A')}")
                    print("  Raw response:")
                    print(json.dumps(pg_dict, indent=2, default=str))
                except Exception as e:
                    print(f"  ERROR: {type(e).__name__}: {e}")
            else:
                print("  No GridBOSS found — parallel groups require GridBOSS")
                print("  Checking if any devices have parallelGroup field set...")
                for dev in devices.rows:
                    if dev.parallelGroup:
                        safe = dev.serialNum[:4] + "X" * (len(dev.serialNum) - 4)
                        print(f"    {safe} -> parallelGroup='{dev.parallelGroup}'")
            print()

            # 4. Try sync_parallel_groups
            print(f"--- Step 4: Sync Parallel Groups (plant {plant.id}) ---")
            try:
                success = await client.api.devices.sync_parallel_groups(plant.id)
                print(f"  Sync result: {success}")

                if success and gridboss_serial:
                    # Clear cache and re-fetch
                    client._cache.clear()
                    print("  Re-fetching parallel group details after sync...")
                    pg_response2 = await client.api.devices.get_parallel_group_details(
                        gridboss_serial
                    )
                    pg_dict2 = pg_response2.model_dump()
                    if "devices" in pg_dict2 and pg_dict2["devices"]:
                        for d in pg_dict2["devices"]:
                            if "serialNum" in d:
                                s = d["serialNum"]
                                d["serialNum"] = s[:4] + "X" * (len(s) - 4) if len(s) > 4 else s
                    print(f"  Post-sync total: {pg_dict2.get('total', 'N/A')}")
                    print("  Post-sync response:")
                    print(json.dumps(pg_dict2, indent=2, default=str))
            except Exception as e:
                print(f"  ERROR: {type(e).__name__}: {e}")
            print()

            # 5. Load station via pylxpweb high-level API
            print("--- Step 5: High-Level Station Load ---")
            try:
                station = await Station.load(client, plant.id)
                print(f"  Station: {station.name}")
                print(f"  Parallel groups found: {len(station.parallel_groups)}")
                for i, pg in enumerate(station.parallel_groups):
                    print(
                        f"    Group {i}: first_serial={pg.first_device_serial[:4]}XXXX, "
                        f"inverters={len(pg.inverters)}, "
                        f"mid={pg.mid_device is not None}"
                    )
                    for inv in pg.inverters:
                        safe = inv.serial[:4] + "X" * (len(inv.serial) - 4)
                        print(f"      Inverter: {safe} model={inv.model}")
                print(f"  Standalone inverters: {len(station.standalone_inverters)}")
                for inv in station.standalone_inverters:
                    safe = inv.serial[:4] + "X" * (len(inv.serial) - 4)
                    print(f"    {safe} model={inv.model}")
            except Exception as e:
                print(f"  ERROR: {type(e).__name__}: {e}")
                import traceback

                traceback.print_exc()

    print()
    print("=== Done ===")
    print("Please paste the full output in a GitHub comment (serials are partially redacted).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parallel Group Diagnostic")
    parser.add_argument("-u", "--username", required=True)
    parser.add_argument("-p", "--password", required=True)
    parser.add_argument("-b", "--base-url", default="https://monitor.eg4electronics.com")
    args = parser.parse_args()
    asyncio.run(main(args.username, args.password, args.base_url))
