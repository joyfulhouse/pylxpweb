#!/usr/bin/env python3
"""Device Data Collection Tool for pylxpweb.

This script automatically discovers and collects comprehensive device information
from all Luxpower/EG4 inverters in your account. It's designed to help developers
add support for new/unknown inverter models.

The tool:
1. Discovers all plants and devices in your account
2. Reads all register values from each device
3. Generates JSON and Markdown reports for each device

Usage:
    pylxpweb-collect -u YOUR_USERNAME -p YOUR_PASSWORD

    # For EU Luxpower portal users:
    pylxpweb-collect -u YOUR_USERNAME -p YOUR_PASSWORD -b https://eu.luxpowertek.com

    # For US Luxpower portal users:
    pylxpweb-collect -u YOUR_USERNAME -p YOUR_PASSWORD -b https://us.luxpowertek.com

For detailed instructions, see: https://github.com/joyfulhouse/pylxpweb/blob/main/docs/COLLECT_DEVICE_DATA.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

# Handle imports whether run as module or directly
try:
    from pylxpweb import __version__
    from pylxpweb.client import LuxpowerClient
except ImportError:
    # Running directly from source
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
    from pylxpweb import __version__
    from pylxpweb.client import LuxpowerClient


GITHUB_ISSUES_URL = "https://github.com/joyfulhouse/pylxpweb/issues/new"
GITHUB_DISCUSSIONS_URL = "https://github.com/joyfulhouse/pylxpweb/discussions"

# Keys in sample_values that may contain sensitive data
SENSITIVE_PARAM_KEYS = {
    "HOLD_SERIAL_NUM",
    "HOLD_DATALOG_SN",
    "HOLD_MODBUS_ADDR",
    # Add any other parameter names that might contain sensitive data
}


def sanitize_serial(serial: str) -> str:
    """Mask a serial number for privacy.

    Example: "4512670118" -> "45******18"
    """
    if len(serial) >= 6:
        return f"{serial[:2]}{'*' * (len(serial) - 4)}{serial[-2:]}"
    elif len(serial) > 2:
        return f"{serial[0]}{'*' * (len(serial) - 2)}{serial[-1]}"
    return "*" * len(serial)


def sanitize_plant_name(_name: str) -> str:
    """Replace plant name with generic placeholder."""
    return "My Solar System"


def sanitize_location(value: Any) -> Any:
    """Sanitize location-related values (lat/long, addresses)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Latitude/longitude - replace with 0.0
        return 0.0
    if isinstance(value, str):
        # Address string - replace with placeholder
        return "123 Example Street"
    return value


def sanitize_output(data: dict[str, Any], serial_map: dict[str, str]) -> dict[str, Any]:
    """Sanitize sensitive data in the output structure.

    Args:
        data: The output data dictionary
        serial_map: Mapping of original serial -> sanitized serial

    Returns:
        Sanitized copy of the data
    """
    import copy

    result = copy.deepcopy(data)

    # Sanitize metadata
    if "metadata" in result:
        meta = result["metadata"]
        if "serial_num" in meta:
            original = meta["serial_num"]
            meta["serial_num"] = serial_map.get(original, sanitize_serial(original))

    # Sanitize register blocks
    if "register_blocks" in result:
        for block in result["register_blocks"]:
            if "sample_values" in block:
                samples = block["sample_values"]
                for key in list(samples.keys()):
                    # Sanitize known sensitive parameters
                    if key in SENSITIVE_PARAM_KEYS:
                        val = samples[key]
                        if isinstance(val, str) and len(val) >= 4:
                            # Check if it's a serial number in our map
                            if val in serial_map:
                                samples[key] = serial_map[val]
                            else:
                                samples[key] = sanitize_serial(val)

    return result


def merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping register ranges into consolidated ranges."""
    if not ranges:
        return []

    intervals = [(start, start + length - 1) for start, length in ranges]
    intervals.sort(key=lambda x: x[0])

    merged = [intervals[0]]
    for current_start, current_end in intervals[1:]:
        last_start, last_end = merged[-1]
        if current_start <= last_end + 1:
            merged[-1] = (last_start, max(last_end, current_end))
        else:
            merged.append((current_start, current_end))

    return [(start, end - start + 1) for start, end in merged]


async def find_min_block_size(
    client: LuxpowerClient,
    serial_num: str,
    start_register: int,
    max_size: int = 127,
) -> tuple[int | None, dict[str, Any]]:
    """Find minimum block size needed to get data from a register."""
    for block_size in range(1, max_size + 1):
        try:
            response = await client.api.control.read_parameters(
                serial_num,
                start_register=start_register,
                point_number=block_size,
            )

            if response.success and response.parameters:
                return (block_size, response.parameters)

            await asyncio.sleep(0.1)

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
    """Detect leading empty registers in a multi-register block."""
    if block_size <= 1:
        return {
            "original_start": start_register,
            "original_size": block_size,
            "actual_start": start_register,
            "actual_size": block_size,
            "leading_empty_registers": 0,
        }

    baseline_param_keys = sorted(baseline_params.keys())
    leading_empty = 0

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
                break

            test_param_keys = sorted(test_response.parameters.keys())

            if test_param_keys == baseline_param_keys:
                leading_empty = offset
                await asyncio.sleep(0.1)
            else:
                break

        except Exception:
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
    indent: str = "    ",
) -> list[dict[str, Any]]:
    """Map a register range using dynamic block sizing."""
    print(f"{indent}Mapping registers {start} to {start + length - 1}")

    blocks = []
    range_end = start + length
    current_reg = start

    while current_reg < range_end:
        print(f"{indent}  Register {current_reg:4d}: ", end="", flush=True)

        block_size, params = await find_min_block_size(
            client, serial_num, current_reg, max_size=127
        )

        if block_size is None:
            print("No data - stopping scan")
            break

        param_keys = sorted(params.keys())
        print(f"Block size={block_size:2d}, {len(param_keys):3d} params")

        boundary_info: dict[str, Any] = {}
        if validate_boundaries and block_size > 1:
            boundary_info = await validate_block_boundaries(
                client, serial_num, current_reg, block_size, params
            )

            if boundary_info["leading_empty_registers"] > 0:
                print(
                    f"{indent}    -> Actual: register {boundary_info['actual_start']}, "
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

        current_reg += block_size

    return blocks


def format_sample_value(value: Any) -> str:
    """Format a sample value for markdown table."""
    if isinstance(value, (bool, int, float)):
        return str(value)
    elif isinstance(value, str):
        return f'"{value}"'
    else:
        return str(value)


def create_markdown_report(data: dict[str, Any]) -> str:
    """Create markdown report from register data."""
    metadata = data.get("metadata", {})
    statistics = data.get("statistics", {})
    register_blocks = data.get("register_blocks", [])

    lines = []

    # Title
    device_type = metadata.get("device_type", "Unknown Device")
    serial_num = metadata.get("serial_num", "Unknown")
    lines.append(f"# {device_type} Register Map")
    lines.append(f"## Serial Number: {serial_num}")
    lines.append("")

    # Metadata
    lines.append("## Metadata")
    lines.append("")
    lines.append(f"- **Timestamp**: {metadata.get('timestamp', 'N/A')}")
    lines.append(f"- **pylxpweb Version**: {metadata.get('pylxpweb_version', 'N/A')}")
    lines.append(f"- **Base URL**: {metadata.get('base_url', 'N/A')}")
    lines.append(f"- **Device Type**: {device_type}")
    lines.append("")

    # Statistics
    lines.append("### Statistics")
    lines.append("")
    lines.append(f"- **Total Register Blocks**: {statistics.get('total_blocks', 'N/A')}")
    lines.append(f"- **Total Parameters**: {statistics.get('total_parameters', 'N/A')}")
    lines.append(
        f"- **Blocks with Leading Empty**: {statistics.get('blocks_with_leading_empty', 'N/A')}"
    )
    lines.append("")

    # Register table
    lines.append("## Register Map")
    lines.append("")
    lines.append("| Register | Start | Length | Parameters | Sample Values |")
    lines.append("|----------|-------|--------|------------|---------------|")

    for block in register_blocks:
        original_start = block["start_register"]
        original_size = block["block_size"]
        params = block["parameter_keys"]
        samples = block["sample_values"]

        boundary = block.get("boundary_validation", {})
        actual_start = boundary.get("actual_start", original_start)
        actual_size = boundary.get("actual_size", original_size)
        leading_empty = boundary.get("leading_empty_registers", 0)

        # Add row for leading empty registers
        if leading_empty > 0:
            empty_start = original_start
            if leading_empty == 1:
                empty_display = str(empty_start)
            else:
                empty_end = empty_start + leading_empty - 1
                empty_display = f"{empty_start}-{empty_end}"
            lines.append(f"| {empty_display} | {empty_start} | {leading_empty} | `<EMPTY>` | - |")

        # Format register display
        if actual_size == 1:
            reg_display = str(actual_start)
        else:
            end_reg = actual_start + actual_size - 1
            reg_display = f"{actual_start}-{end_reg}"

        if len(params) == 0:
            lines.append(f"| {reg_display} | {actual_start} | {actual_size} | `<EMPTY>` | - |")
        elif len(params) == 1:
            param = params[0]
            value = format_sample_value(samples.get(param, "N/A"))
            lines.append(
                f"| {reg_display} | {actual_start} | {actual_size} | `{param}` | {value} |"
            )
        else:
            param_list = "<br>".join([f"`{p}`" for p in params])
            value_list = "<br>".join([format_sample_value(samples.get(p, "N/A")) for p in params])
            lines.append(
                f"| {reg_display} | {actual_start} | {actual_size} | {param_list} | {value_list} |"
            )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*Generated by pylxpweb v{__version__}*")

    return "\n".join(lines)


def get_default_ranges(device_type: str) -> list[tuple[int, int]]:
    """Get default register ranges based on device type."""
    device_lower = device_type.lower()

    if "gridboss" in device_lower or "grid boss" in device_lower or "mid" in device_lower:
        # GridBOSS/MID devices have extended register ranges
        return [(0, 381), (2032, 127)]
    else:
        # Standard inverters (18KPV, etc.)
        return [(0, 127), (127, 127), (240, 127)]


async def discover_all_devices(
    client: LuxpowerClient,
) -> list[dict[str, Any]]:
    """Discover all plants and devices in the account."""
    devices: list[dict[str, Any]] = []

    plants = await client.api.plants.get_plants()

    for plant in plants.rows:
        plant_devices = await client.api.devices.get_devices(plant.plantId)
        for device in plant_devices.rows:
            devices.append(
                {
                    "serial_num": device.serialNum,
                    "device_type": device.deviceTypeText,
                    "plant_id": plant.plantId,
                    "plant_name": plant.name,
                    "status": device.statusText,
                }
            )

    return devices


async def collect_single_device(
    client: LuxpowerClient,
    serial_num: str,
    device_type: str,
    output_dir: Path,
    sanitize: bool = False,
    serial_map: dict[str, str] | None = None,
) -> tuple[Path, Path] | None:
    """Collect data from a single device."""
    if serial_map is None:
        serial_map = {}
    # Get register ranges for this device type
    ranges = get_default_ranges(device_type)
    merged_ranges = merge_ranges(ranges)

    print(f"    Register ranges: {len(merged_ranges)}")
    for start, length in merged_ranges:
        print(f"      - {start} to {start + length - 1}")

    # Map all register ranges
    all_blocks: list[dict[str, Any]] = []
    for range_idx, (start, length) in enumerate(merged_ranges, 1):
        print(f"    Scanning range {range_idx}/{len(merged_ranges)}...")
        try:
            blocks = await map_register_range(
                client, serial_num, start, length, validate_boundaries=True, indent="      "
            )
            all_blocks.extend(blocks)
        except Exception as e:
            print(f"      Error scanning range: {e}")
            continue

    if not all_blocks:
        print("    No data collected - device may be offline")
        return None

    # Calculate statistics
    all_params: set[str] = set()
    for block in all_blocks:
        all_params.update(block["parameter_keys"])

    blocks_with_leading_empty = [
        b for b in all_blocks if b["boundary_validation"]["leading_empty_registers"] > 0
    ]

    # Build output structure
    output = {
        "metadata": {
            "timestamp": datetime.now().astimezone().isoformat(),
            "pylxpweb_version": __version__,
            "base_url": client.base_url,
            "serial_num": serial_num,
            "device_type": device_type,
            "merged_ranges": [
                {"start": start, "length": length, "end": start + length - 1}
                for start, length in merged_ranges
            ],
        },
        "statistics": {
            "total_blocks": len(all_blocks),
            "total_parameters": len(all_params),
            "blocks_with_leading_empty": len(blocks_with_leading_empty),
        },
        "register_blocks": all_blocks,
        "all_parameter_names": sorted(all_params),
    }

    # Apply sanitization if requested
    if sanitize:
        output = sanitize_output(output, serial_map)
        # Use sanitized serial for filename
        serial_for_filename = serial_map.get(serial_num, sanitize_serial(serial_num))
    else:
        serial_for_filename = serial_num

    # Generate filenames
    device_type_clean = device_type.replace(" ", "").replace("-", "")
    base_name = f"{device_type_clean}_{serial_for_filename}"

    json_path = output_dir / f"{base_name}.json"
    md_path = output_dir / f"{base_name}.md"

    # Write JSON
    print(f"    Writing {json_path.name}...")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)

    # Write Markdown
    print(f"    Writing {md_path.name}...")
    markdown_content = create_markdown_report(output)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    return json_path, md_path


def create_zip_archive(
    created_files: list[tuple[Path, Path]],
    output_dir: Path,
    sanitize: bool = False,
) -> Path:
    """Create a zip archive of all generated files.

    Args:
        created_files: List of (json_path, md_path) tuples
        output_dir: Directory where zip should be created
        sanitize: Whether files were sanitized (affects filename)

    Returns:
        Path to the created zip file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_sanitized" if sanitize else ""
    zip_name = f"pylxpweb_device_data_{timestamp}{suffix}.zip"
    zip_path = output_dir / zip_name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for json_path, md_path in created_files:
            # Add files with just their filename (no directory structure)
            zf.write(json_path, json_path.name)
            zf.write(md_path, md_path.name)

    return zip_path


def generate_issue_url(
    devices: list[dict[str, Any]],
    zip_filename: str,
    sanitized: bool = False,
) -> str:
    """Generate a pre-filled GitHub issue URL.

    Args:
        devices: List of device info dicts with device_type, serial_num, status
        zip_filename: Name of the zip file to attach
        sanitized: Whether data was sanitized

    Returns:
        URL string with pre-filled title and body
    """
    # Build title from device types
    device_types = sorted({d["device_type"] for d in devices})
    if len(device_types) == 1:
        title = f"Add support for {device_types[0]}"
    else:
        title = f"Add support for {', '.join(device_types)}"

    # Build body with device info
    body_lines = [
        "## Device Information",
        "",
        "| Device Type | Serial | Status |",
        "|-------------|--------|--------|",
    ]

    for device in devices:
        dtype = device["device_type"]
        serial = device.get("display_serial", device["serial_num"])
        status = device["status"]
        body_lines.append(f"| {dtype} | {serial} | {status} |")

    body_lines.extend(
        [
            "",
            "## Features Needed",
            "",
            "<!-- Please describe what features you need supported -->",
            "- [ ] Battery monitoring and control",
            "- [ ] Grid export/import limits",
            "- [ ] Time-of-use scheduling",
            "- [ ] Other: ",
            "",
            "## Inverter Details",
            "",
            "- **Firmware Version**: <!-- Check your inverter's display or web portal -->",
            "- **Inverter Type**: <!-- Hybrid / Grid-tie / Off-grid -->",
            "- **Battery Type**: <!-- LiFePO4 / Lead-acid / None -->",
            "",
            "## Attached Data",
            "",
            f"Please attach the zip file: `{zip_filename}`",
            "",
            "---",
            f"*Collected with pylxpweb v{__version__}*",
        ]
    )

    if sanitized:
        body_lines.insert(0, "> Note: Serial numbers have been sanitized for privacy.\n")

    body = "\n".join(body_lines)

    # Build URL with query parameters
    params = {
        "title": title,
        "body": body,
        "labels": "new-device",
    }

    return f"{GITHUB_ISSUES_URL}?{urlencode(params, quote_via=quote)}"


def print_upload_instructions(
    devices: list[dict[str, Any]],
    created_files: list[tuple[Path, Path]],
    zip_path: Path | None = None,
    sanitized: bool = False,
) -> None:
    """Print instructions for uploading the data."""
    print("\n" + "=" * 70)
    print("  UPLOAD INSTRUCTIONS")
    print("=" * 70)
    print()

    # Generate pre-filled issue URL
    if zip_path:
        issue_url = generate_issue_url(devices, zip_path.name, sanitized)
        print("CLICK THIS LINK to create a pre-filled GitHub issue:")
        print()
        print(f"  {issue_url}")
        print()
        print("-" * 70)
        print()
        print("After the page opens:")
        print()
        print("1. Review the pre-filled information (edit if needed)")
        print()
        print("2. ATTACH this zip file by dragging it into the description:")
        print(f"   >>> {zip_path.name} <<<")
        print()
        print("3. Click 'Submit new issue'")
    else:
        print("Create a new GitHub issue at:")
        print(f"   {GITHUB_ISSUES_URL}")
        print()
        print("Attach these files:")
        for json_path, md_path in created_files:
            print(f"   - {json_path.name}")
            print(f"   - {md_path.name}")

    print()
    print("-" * 70)
    if sanitized:
        print("NOTE: Sensitive data (serial numbers, locations) has been SANITIZED.")
        print("      The files are safe to share publicly.")
    else:
        print("NOTE: Serial numbers are NOT sanitized. Re-run with --sanitize if needed.")
    print()
    print("Questions? Start a discussion at:")
    print(f"   {GITHUB_DISCUSSIONS_URL}")
    print("=" * 70)


async def main_async(args: argparse.Namespace) -> int:
    """Async main entry point."""
    username = args.username
    password = args.password
    base_url = args.base_url or "https://monitor.eg4electronics.com"
    sanitize = args.sanitize

    # Create output directory
    output_dir = Path(args.output_dir) if args.output_dir else Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 70)
    print("  pylxpweb Device Data Collection Tool")
    print(f"  Version: {__version__}")
    print("=" * 70)
    print()
    print(f"Base URL: {base_url}")
    print(f"Output Directory: {output_dir.absolute()}")
    if sanitize:
        print("Sanitization: ENABLED (serial numbers and locations will be masked)")
    print()

    try:
        async with LuxpowerClient(username, password, base_url=base_url) as client:
            # Discover all devices
            print("Discovering devices in your account...")
            devices = await discover_all_devices(client)

            if not devices:
                print("\nNo devices found in your account.")
                print("Please check your credentials and try again.")
                return 1

            # Build serial map for sanitization (all serials discovered)
            serial_map: dict[str, str] = {}
            if sanitize:
                for device in devices:
                    original = device["serial_num"]
                    serial_map[original] = sanitize_serial(original)

            # Add display_serial to each device for use in issue URL
            for device in devices:
                serial = device["serial_num"]
                device["display_serial"] = serial_map.get(serial, serial) if sanitize else serial

            print(f"\nFound {len(devices)} device(s):")
            for i, device in enumerate(devices, 1):
                dtype = device["device_type"]
                display_serial = device["display_serial"]
                status = device["status"]
                print(f"  {i}. {dtype} ({display_serial}) - {status}")
            print()

            # Collect data from each device
            created_files: list[tuple[Path, Path]] = []
            for i, device in enumerate(devices, 1):
                display_serial = (
                    serial_map.get(device["serial_num"], device["serial_num"])
                    if sanitize
                    else device["serial_num"]
                )
                print(f"\n[{i}/{len(devices)}] Processing: {device['device_type']}")
                print(f"  Serial: {display_serial}")
                print(f"  Status: {device['status']}")

                result = await collect_single_device(
                    client,
                    device["serial_num"],
                    device["device_type"],
                    output_dir,
                    sanitize=sanitize,
                    serial_map=serial_map,
                )

                if result:
                    created_files.append(result)
                    print("  Done!")

            if not created_files:
                print("\nNo data was collected. All devices may be offline.")
                return 1

            # Create zip archive
            print("\nCreating zip archive...")
            zip_path = create_zip_archive(created_files, output_dir, sanitize)
            print(f"  Created: {zip_path.name}")

            # Print summary
            print()
            print("=" * 70)
            print("  Collection Complete!")
            print("=" * 70)
            print()
            print(f"Files created in: {output_dir.absolute()}")
            print()
            print("  ZIP FILE (attach this):")
            print(f"    >>> {zip_path.name} <<<")
            print()
            print("  Individual files (included in zip):")
            for json_path, md_path in created_files:
                print(f"    - {json_path.name}")
                print(f"    - {md_path.name}")

            # Print upload instructions with pre-filled issue link
            print_upload_instructions(devices, created_files, zip_path, sanitize)

            return 0

    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()
        return 1


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Automatically collect device data from all inverters in your account",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Standard usage (EG4 users)
  pylxpweb-collect -u your@email.com -p YourPassword

  # EU Luxpower portal users
  pylxpweb-collect -u your@email.com -p YourPassword -b https://eu.luxpowertek.com

  # US Luxpower portal users
  pylxpweb-collect -u your@email.com -p YourPassword -b https://us.luxpowertek.com

  # Save files to a specific folder
  pylxpweb-collect -u your@email.com -p YourPassword -o ./my_inverter_data

Regional API Endpoints:
  - EG4 (US):      https://monitor.eg4electronics.com (default)
  - Luxpower (US): https://us.luxpowertek.com
  - Luxpower (EU): https://eu.luxpowertek.com

The tool will automatically:
  1. Discover all plants and devices in your account
  2. Read all register values from each device
  3. Generate JSON and Markdown reports for each device

For detailed instructions: https://github.com/joyfulhouse/pylxpweb/blob/main/docs/COLLECT_DEVICE_DATA.md
        """,
    )

    parser.add_argument(
        "--username",
        "-u",
        required=True,
        help="Your EG4/Luxpower web portal username (email)",
    )
    parser.add_argument(
        "--password",
        "-p",
        required=True,
        help="Your EG4/Luxpower web portal password",
    )
    parser.add_argument(
        "--base-url",
        "-b",
        help="API base URL (default: https://monitor.eg4electronics.com)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        help="Output directory for generated files (default: current directory)",
    )
    parser.add_argument(
        "--sanitize",
        "-S",
        action="store_true",
        help="Sanitize sensitive data (serial numbers, plant names, locations) in output files",
    )

    args = parser.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
