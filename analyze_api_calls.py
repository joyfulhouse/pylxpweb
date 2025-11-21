"""Analyze API calls for full data refresh."""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from pylxpweb import LuxpowerClient
from pylxpweb.devices import Station

# Track API calls
call_log = []

load_dotenv(Path(__file__).parent / ".env")


async def main():
    async with LuxpowerClient(
        os.getenv("LUXPOWER_USERNAME"),
        os.getenv("LUXPOWER_PASSWORD"),
        base_url=os.getenv("LUXPOWER_BASE_URL"),
    ) as client:
        # Patch the _request method to log calls
        original_request = client._request

        async def logging_request(method, endpoint, **kwargs):
            call_log.append(endpoint)
            return await original_request(method, endpoint, **kwargs)

        client._request = logging_request

        print("=" * 80)
        print("API CALL ANALYSIS FOR FULL DATA REFRESH")
        print("=" * 80)

        # Load stations (discovery)
        print("\n--- PHASE 1: Station Discovery ---")
        call_log.clear()
        stations = await Station.load_all(client)
        print(f"Loaded {len(stations)} station(s)")

        phase1_calls = list(call_log)
        print(f"\nAPI calls during station load: {len(phase1_calls)}")
        for idx, endpoint in enumerate(phase1_calls, 1):
            print(f"  {idx}. {endpoint}")

        # Refresh all data (runtime, energy, battery)
        print("\n--- PHASE 2: Full Data Refresh ---")
        call_log.clear()

        for station in stations:
            await station.refresh_all_data()

        phase2_calls = list(call_log)

        # Read parameters (would be done periodically to detect external changes)
        print("\n--- PHASE 3: Parameter Refresh ---")
        call_log.clear()

        for station in stations:
            for inverter in station.all_inverters:
                # Read all parameter ranges as per reference implementation
                # (0-127), (127-127), (240-127)
                await inverter.read_parameters(0, 127)
                await inverter.read_parameters(127, 127)
                await inverter.read_parameters(240, 127)

        phase3_calls = list(call_log)

        # Count by endpoint type for each phase
        from collections import Counter

        print(f"\nAPI calls during data refresh: {len(phase2_calls)}")
        endpoint_counts = Counter(phase2_calls)
        for endpoint, count in sorted(endpoint_counts.items()):
            print(f"  {count}x {endpoint}")

        print(f"\nAPI calls during parameter refresh: {len(phase3_calls)}")
        param_counts = Counter(phase3_calls)
        for endpoint, count in sorted(param_counts.items()):
            print(f"  {count}x {endpoint}")

        # Total summary
        total = len(phase1_calls) + len(phase2_calls) + len(phase3_calls)
        print("\n" + "=" * 80)
        print(f"TOTAL API CALLS: {total}")
        print("=" * 80)

        print("\nBreakdown by phase:")
        print(f"  Station Discovery:    {len(phase1_calls)} calls")
        print(f"  Data Refresh:         {len(phase2_calls)} calls")
        print(f"  Parameter Refresh:    {len(phase3_calls)} calls")

        # Per-station breakdown
        print("\n" + "=" * 80)
        print("STATION CONFIGURATION")
        print("=" * 80)

        for station in stations:
            print(f"\nStation: {station.name}")
            print(f"  Parallel Groups:      {len(station.parallel_groups)}")
            for group in station.parallel_groups:
                print(
                    f"    - Group '{group.name}': {len(group.inverters)} inverters, "
                    + f"{'MID device' if group.mid_device else 'no MID'}"
                )
            print(f"  Standalone Inverters: {len(station.standalone_inverters)}")
            print(f"  Total Inverters:      {len(station.all_inverters)}")

            total_batteries = 0
            for inv in station.all_inverters:
                if inv.battery_bank and inv.battery_bank.batteries:
                    total_batteries += len(inv.battery_bank.batteries)
                    print(f"    - {inv.serial_number}: {len(inv.battery_bank.batteries)} batteries")
            print(f"  Total Batteries:      {total_batteries}")

        print("\n" + "=" * 80)
        print("API CALL PATTERN")
        print("=" * 80)

        print("\nStation Discovery (once per session):")
        print("  1x /WManage/web/config/plant/list/viewer")
        print("  Nx /WManage/web/config/plant/get (N = number of stations)")
        print("  Nx /WManage/api/inverterOverview/list (N = number of stations)")
        print("  Nx /WManage/api/inverterOverview/getParallelGroupDetails (if GridBOSS)")

        print("\nData Refresh (per inverter, called frequently):")
        print("  1x /WManage/api/inverter/getInverterRuntime")
        print("  1x /WManage/api/inverter/getInverterEnergyInfo")
        print("  1x /WManage/api/battery/getBatteryInfo")
        print("  1x /WManage/api/midbox/getMidboxRuntime (if MID device present)")
        print("  = 3-4 calls per refresh cycle")

        print("\nParameter Refresh (per inverter, called hourly):")
        print("  3x /WManage/web/maintain/inverter/param/read")
        print("    - Range 1: registers 0-127 (base parameters)")
        print("    - Range 2: registers 127-254 (extended parameters 1)")
        print("    - Range 3: registers 240-367 (extended parameters 2)")
        print("  = 3 calls per inverter")

        inverter_count = sum(len(s.all_inverters) for s in stations)
        expected_data_refresh = inverter_count * 3
        expected_param_refresh = inverter_count * 3

        print(f"\nYour configuration ({inverter_count} inverter(s)):")
        print(
            f"  Data refresh:      {len(phase2_calls)} calls "
            f"(expected: {expected_data_refresh} + MID)"
        )
        print(
            f"  Parameter refresh: {len(phase3_calls)} calls (expected: {expected_param_refresh})"
        )
        print(f"  Total per cycle:   {len(phase2_calls) + len(phase3_calls)} calls")

        if len(phase3_calls) == expected_param_refresh:
            print("  ✅ Parameter refresh matches expected pattern")
        else:
            print(f"  ⚠️  Parameter difference: {len(phase3_calls) - expected_param_refresh} calls")


if __name__ == "__main__":
    asyncio.run(main())
