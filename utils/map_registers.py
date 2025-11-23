#!/usr/bin/env python3
"""
Comprehensive register mapping tool for Luxpower/EG4 inverters.

This script maps register space for any inverter, automatically detecting:
- Register block boundaries using dynamic sizing
- Leading empty registers within multi-register blocks
- Parameter names and sample values
- Device type mapping (serial number → device model)

Overlapping register ranges are automatically merged into consolidated ranges.

Usage:
    # Multiple ranges (recommended) with shorthand flags
    python research/map_registers.py \\
        -u your_username -p your_password \\
        -s 1234567890 \\
        -r 0,127 -r 127,127 -r 240,127 -r 269,7 \\
        -o results.json

    # Single range (legacy style)
    python research/map_registers.py \\
        --username your_username --password your_password \\
        --serial-num 1234567890 \\
        --start 0 --length 127 \\
        --output results.json

    # The ranges -r 0,127 -r 127,127 -r 240,127 -r 269,7
    # automatically merge to: 0-366 (single consolidated range)

    # With custom base URL:
    python research/map_registers.py \\
        -u your_username -p your_password \\
        -s 1234567890 -r 0,127 -r 127,127 \\
        -b https://us.luxpowertek.com \\
        -o results.json

Authentication (in priority order):
    1. Command-line flags: --username/-u and --password/-p
    2. Environment file: LUXPOWER_USERNAME and LUXPOWER_PASSWORD in .env
    3. Environment variables: LUXPOWER_USERNAME and LUXPOWER_PASSWORD

Other environment variables:
    LUXPOWER_BASE_URL - API base URL (optional, defaults to monitor.eg4electronics.com)
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

from pylxpweb.client import LuxpowerClient


def merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping register ranges into consolidated ranges.

    Args:
        ranges: List of (start, length) tuples

    Returns:
        List of non-overlapping (start, length) tuples sorted by start position

    Example:
        >>> merge_ranges([(0, 127), (127, 127), (240, 127), (269, 7)])
        [(0, 367)]  # 0-366 consolidated
    """
    if not ranges:
        return []

    # Convert (start, length) to (start, end) for easier merging
    intervals = [(start, start + length - 1) for start, length in ranges]

    # Sort by start position
    intervals.sort(key=lambda x: x[0])

    # Merge overlapping/adjacent intervals
    merged = [intervals[0]]
    for current_start, current_end in intervals[1:]:
        last_start, last_end = merged[-1]

        # Check if current interval overlaps or is adjacent to last merged interval
        if current_start <= last_end + 1:
            # Merge by extending the end position
            merged[-1] = (last_start, max(last_end, current_end))
        else:
            # No overlap, add as new interval
            merged.append((current_start, current_end))

    # Convert back to (start, length) format
    return [(start, end - start + 1) for start, end in merged]


async def find_min_block_size(
    client: LuxpowerClient,
    serial_num: str,
    start_register: int,
    max_size: int = 127,
) -> tuple[int | None, dict[str, Any]]:
    """Find minimum block size needed to get data from a register.

    Args:
        client: Authenticated LuxpowerClient
        serial_num: Inverter serial number
        start_register: Starting register to test
        max_size: Maximum block size to try

    Returns:
        (block_size, parameters) or (None, {}) if no data found
    """
    for block_size in range(1, max_size + 1):
        try:
            response = await client.api.control.read_parameters(
                serial_num,
                start_register=start_register,
                point_number=block_size,
            )

            if response.success and response.parameters:
                return (block_size, response.parameters)

            await asyncio.sleep(0.1)  # Rate limiting

        except Exception:
            await asyncio.sleep(0.1)
            continue

    return (None, {})


async def validate_block_boundaries(
    client: LuxpowerClient,
    serial_num: str,
    start_register: int,
    block_size: int,
    baseline_params: dict[str, Any],
) -> dict[str, Any]:
    """Detect leading empty registers in a multi-register block.

    Args:
        client: Authenticated LuxpowerClient
        serial_num: Inverter serial number
        start_register: Block starting register
        block_size: Block size from find_min_block_size
        baseline_params: Parameters from the full block read

    Returns:
        dict with boundary validation results
    """
    if block_size <= 1:
        # Single register, no leading empty possible
        return {
            "original_start": start_register,
            "original_size": block_size,
            "actual_start": start_register,
            "actual_size": block_size,
            "leading_empty_registers": 0,
        }

    baseline_param_keys = sorted(baseline_params.keys())
    leading_empty = 0

    # Test progressively skipping leading registers
    for offset in range(1, block_size):
        test_start = start_register + offset
        test_size = block_size - offset

        try:
            test_response = await client.api.control.read_parameters(
                serial_num,
                start_register=test_start,
                point_number=test_size,
            )

            if not test_response.success or not test_response.parameters:
                # No data returned, baseline is correct
                break

            test_param_keys = sorted(test_response.parameters.keys())

            if test_param_keys == baseline_param_keys:
                # Same parameters, leading register was empty
                leading_empty = offset
                await asyncio.sleep(0.1)
            else:
                # Different parameters, found actual start
                break

        except Exception:
            # Error reading, assume baseline is correct
            break

    actual_start = start_register + leading_empty
    actual_size = block_size - leading_empty

    return {
        "original_start": start_register,
        "original_size": block_size,
        "actual_start": actual_start,
        "actual_size": actual_size,
        "leading_empty_registers": leading_empty,
    }


async def map_register_range(
    client: LuxpowerClient,
    serial_num: str,
    start: int,
    length: int,
    validate_boundaries: bool = True,
) -> list[dict[str, Any]]:
    """Map a register range using dynamic block sizing and boundary validation.

    Args:
        client: Authenticated LuxpowerClient
        serial_num: Inverter serial number
        start: Starting register (e.g., 0)
        length: Number of registers to scan (e.g., 127)
        validate_boundaries: Whether to detect leading empty registers

    Returns:
        List of register blocks with parameters and boundary info
    """
    print(f"\nMapping registers {start} to {start + length - 1}")
    print("=" * 80)

    blocks = []
    range_end = start + length
    current_reg = start

    while current_reg < range_end:
        print(f"Register {current_reg:4d}: ", end="", flush=True)

        # Find minimum block size for this register
        block_size, params = await find_min_block_size(
            client, serial_num, current_reg, max_size=127
        )

        if block_size is None:
            # No data found after trying all block sizes
            print("No data - stopping scan")
            break

        param_keys = sorted(params.keys())
        print(f"Block size={block_size:2d}, {len(param_keys):3d} params")

        # Validate block boundaries if multi-register and validation enabled
        boundary_info = {}
        if validate_boundaries and block_size > 1:
            boundary_info = await validate_block_boundaries(
                client, serial_num, current_reg, block_size, params
            )

            if boundary_info["leading_empty_registers"] > 0:
                print(
                    f"  → Actual: register {boundary_info['actual_start']}, "
                    f"size {boundary_info['actual_size']} "
                    f"({boundary_info['leading_empty_registers']} leading empty)"
                )
        else:
            boundary_info = {
                "original_start": current_reg,
                "original_size": block_size,
                "actual_start": current_reg,
                "actual_size": block_size,
                "leading_empty_registers": 0,
            }

        # Record block with all information
        blocks.append(
            {
                "start_register": current_reg,
                "block_size": block_size,
                "end_register": current_reg + block_size - 1,
                "parameter_count": len(param_keys),
                "parameter_keys": param_keys,
                "sample_values": params,
                "boundary_validation": boundary_info,
            }
        )

        # Jump to next unmapped register
        current_reg += block_size

    return blocks


async def get_device_type_map(client: LuxpowerClient) -> dict[str, str]:
    """Build a map of serial numbers to device types.

    Args:
        client: Authenticated LuxpowerClient

    Returns:
        Dict mapping serial number → deviceTypeText4APP
    """
    device_map = {}

    try:
        # Get device information from plants endpoint
        plants = await client.api.plants.get_plants()

        for plant in plants.rows:
            devices = await client.api.devices.get_devices(plant.plantId)
            for device in devices.rows:
                device_map[device.serialNum] = device.deviceTypeText

    except Exception as e:
        print(f"Warning: Could not build device type map: {e}")

    return device_map


async def main():
    parser = argparse.ArgumentParser(
        description="Map Luxpower/EG4 inverter register space",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--username",
        "-u",
        help="API username (alternative to LUXPOWER_USERNAME in .env)",
    )

    parser.add_argument(
        "--password",
        "-p",
        help="API password (alternative to LUXPOWER_PASSWORD in .env)",
    )

    parser.add_argument(
        "--serial-num",
        "--serial",
        "-s",
        required=True,
        help="Inverter serial number (10 digits)",
    )

    parser.add_argument(
        "--range",
        "-r",
        action="append",
        dest="ranges",
        help=(
            "Register range as 'start,length' (can be specified multiple times). "
            "Overlapping ranges are automatically merged. "
            "Example: --range 0,127 --range 127,127 --range 240,127"
        ),
    )

    parser.add_argument(
        "--start",
        type=int,
        help="Starting register (deprecated, use --range instead)",
    )

    parser.add_argument(
        "--length",
        type=int,
        help="Number of registers to scan (deprecated, use --range instead)",
    )

    parser.add_argument(
        "--base-url",
        "-b",
        help="API base URL (default: from LUXPOWER_BASE_URL or monitor.eg4electronics.com)",
    )

    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output JSON file (default: {DeviceType}_{SerialNum}.json)",
    )

    parser.add_argument(
        "--no-boundary-validation",
        action="store_true",
        help="Skip leading empty register detection (faster but less accurate)",
    )

    args = parser.parse_args()

    # Load environment (will be overridden by command-line args if provided)
    load_dotenv()

    # Prefer command-line args, fall back to environment variables
    username = args.username or os.getenv("LUXPOWER_USERNAME")
    password = args.password or os.getenv("LUXPOWER_PASSWORD")

    if not username or not password:
        print("Error: Username and password required")
        print("Provide via --username/-u and --password/-p flags")
        print("OR set LUXPOWER_USERNAME and LUXPOWER_PASSWORD in .env file")
        sys.exit(1)

    # Parse and merge register ranges
    ranges_to_scan = []

    if args.ranges:
        # Parse --range arguments
        for range_spec in args.ranges:
            try:
                start_str, length_str = range_spec.split(",")
                start = int(start_str.strip())
                length = int(length_str.strip())
                if start < 0 or length <= 0:
                    print(
                        f"Error: Invalid range '{range_spec}' "
                        f"(start must be >= 0, length must be > 0)"
                    )
                    sys.exit(1)
                ranges_to_scan.append((start, length))
            except ValueError:
                print(f"Error: Invalid range format '{range_spec}' (expected 'start,length')")
                sys.exit(1)
    elif args.start is not None and args.length is not None:
        # Legacy --start/--length arguments
        ranges_to_scan.append((args.start, args.length))
    else:
        # Default range
        ranges_to_scan.append((0, 127))

    # Merge overlapping/adjacent ranges
    merged_ranges = merge_ranges(ranges_to_scan)

    # Determine base URL
    base_url = (
        args.base_url or os.getenv("LUXPOWER_BASE_URL") or "https://monitor.eg4electronics.com"
    )

    print("\nLuxpower Register Mapping Tool")
    print("=" * 80)
    print(f"Base URL: {base_url}")
    print(f"Serial Number: {args.serial_num}")
    print(f"Input Ranges: {len(ranges_to_scan)} range(s)")
    for i, (start, length) in enumerate(ranges_to_scan, 1):
        print(f"  Range {i}: {start} - {start + length - 1} (length={length})")
    print(f"Merged Ranges: {len(merged_ranges)} range(s)")
    for i, (start, length) in enumerate(merged_ranges, 1):
        print(f"  Range {i}: {start} - {start + length - 1} (length={length})")
    print(f"Boundary Validation: {'Enabled' if not args.no_boundary_validation else 'Disabled'}")
    print()

    async with LuxpowerClient(username, password, base_url=base_url) as client:
        # Authenticate and build device type map
        print("Authenticating...")
        device_type_map = await get_device_type_map(client)

        device_type = device_type_map.get(args.serial_num, "Unknown")
        print(f"Device Type: {device_type}")

        # Set default output filename if not provided
        if args.output is None:
            # Sanitize device type for filename (remove spaces, special chars)
            device_type_clean = device_type.replace(" ", "").replace("-", "")
            output_filename = f"{device_type_clean}_{args.serial_num}.json"
        else:
            output_filename = args.output

        print(f"Output File: {output_filename}")
        print()

        # Map all merged register ranges
        all_blocks = []
        for range_idx, (start, length) in enumerate(merged_ranges, 1):
            print(
                f"\nScanning range {range_idx}/{len(merged_ranges)}: {start} - {start + length - 1}"
            )
            blocks = await map_register_range(
                client,
                args.serial_num,
                start,
                length,
                validate_boundaries=not args.no_boundary_validation,
            )
            all_blocks.extend(blocks)

        # Calculate statistics
        all_params = set()
        for block in all_blocks:
            all_params.update(block["parameter_keys"])

        blocks_with_leading_empty = [
            b for b in all_blocks if b["boundary_validation"]["leading_empty_registers"] > 0
        ]

        # Build output structure
        output = {
            "metadata": {
                "timestamp": datetime.now().astimezone().isoformat(),
                "base_url": base_url,
                "serial_num": args.serial_num,
                "device_type": device_type,
                "input_ranges": [
                    {"start": start, "length": length, "end": start + length - 1}
                    for start, length in ranges_to_scan
                ],
                "merged_ranges": [
                    {"start": start, "length": length, "end": start + length - 1}
                    for start, length in merged_ranges
                ],
                "boundary_validation_enabled": not args.no_boundary_validation,
            },
            "statistics": {
                "total_blocks": len(all_blocks),
                "total_parameters": len(all_params),
                "blocks_with_leading_empty": len(blocks_with_leading_empty),
            },
            "device_type_map": device_type_map,
            "register_blocks": all_blocks,
            "all_parameter_names": sorted(all_params),
        }

        # Save results
        output_path = Path(output_filename)
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2, default=str)

        print(f"\n{'=' * 80}")
        print("✅ Mapping complete")
        print(f"{'=' * 80}\n")

        print("Statistics:")
        print(f"  Total blocks: {output['statistics']['total_blocks']}")
        print(f"  Total parameters: {output['statistics']['total_parameters']}")
        print(
            f"  Blocks with leading empty registers: "
            f"{output['statistics']['blocks_with_leading_empty']}"
        )
        print()
        print(f"Results saved to: {output_path.absolute()}")


if __name__ == "__main__":
    asyncio.run(main())
