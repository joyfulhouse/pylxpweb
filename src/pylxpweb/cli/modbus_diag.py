#!/usr/bin/env python3
"""Modbus Diagnostic Tool for pylxpweb.

This CLI tool collects register data from Luxpower/EG4 inverters via:
- Modbus TCP (RS485-to-Ethernet adapter)
- WiFi Dongle (direct connection)
- Cloud API (for comparison)

Generates diagnostic reports in multiple formats for debugging register
mapping issues and comparing local vs cloud data.

Usage:
    pylxpweb-modbus-diag                 # Interactive mode
    pylxpweb-modbus-diag --host 192.168.1.100 --transport modbus
    pylxpweb-modbus-diag --help
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from pylxpweb import __version__

# Default register ranges based on known mappings
DEFAULT_INPUT_RANGES = [
    (0, 200),  # Core input registers 0-199
    (200, 200),  # Extended input registers 200-399
]

DEFAULT_HOLDING_RANGES = [
    (0, 127),  # Core holding registers 0-126
    (127, 127),  # Extended holding registers 127-253
    (240, 60),  # Additional holding registers 240-299
]


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="pylxpweb-modbus-diag",
        description="Collect Modbus register data from Luxpower/EG4 inverters for diagnostics.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  pylxpweb-modbus-diag
      Interactive mode - prompts for all options

  pylxpweb-modbus-diag --host 192.168.1.100
      Connect via Modbus TCP to specified IP

  pylxpweb-modbus-diag --host 192.168.1.100 --transport dongle
      Connect via WiFi dongle protocol

  pylxpweb-modbus-diag --host 192.168.1.100 --cloud --username user@email.com
      Include cloud API data for comparison

  pylxpweb-modbus-diag --host 192.168.1.100 --serial 1234567890
      Override auto-detected serial number
""",
    )

    # Connection options
    conn_group = parser.add_argument_group("Connection Options")
    conn_group.add_argument(
        "--host",
        "-H",
        help="Inverter IP address",
    )
    conn_group.add_argument(
        "--port",
        "-p",
        type=int,
        help="Port number (default: 502 for Modbus, 8000 for dongle)",
    )
    conn_group.add_argument(
        "--transport",
        "-t",
        choices=["modbus", "dongle", "both"],
        default=None,
        help="Connection method (default: interactive prompt)",
    )
    conn_group.add_argument(
        "--serial",
        "-s",
        help="Override auto-detected inverter serial number",
    )
    conn_group.add_argument(
        "--dongle-serial",
        help="WiFi dongle serial number (required for dongle transport)",
    )

    # Cloud API options
    cloud_group = parser.add_argument_group("Cloud API Options")
    cloud_group.add_argument(
        "--cloud",
        "-c",
        action="store_true",
        help="Include cloud API data for comparison",
    )
    cloud_group.add_argument(
        "--username",
        "-u",
        help="Luxpower/EG4 cloud username (email)",
    )
    cloud_group.add_argument(
        "--password",
        help="Cloud password (will prompt if not provided)",
    )
    cloud_group.add_argument(
        "--base-url",
        default="https://monitor.eg4electronics.com",
        help="API base URL (default: %(default)s)",
    )

    # Register range options
    range_group = parser.add_argument_group("Register Range Options")
    range_group.add_argument(
        "--input-start",
        type=int,
        default=0,
        help="Input register start address (default: 0)",
    )
    range_group.add_argument(
        "--input-count",
        type=int,
        default=400,
        help="Number of input registers to read (default: 400)",
    )
    range_group.add_argument(
        "--holding-start",
        type=int,
        default=0,
        help="Holding register start address (default: 0)",
    )
    range_group.add_argument(
        "--holding-count",
        type=int,
        default=300,
        help="Number of holding registers to read (default: 300)",
    )

    # Output options
    output_group = parser.add_argument_group("Output Options")
    output_group.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=Path.cwd(),
        help="Output directory (default: current directory)",
    )
    output_group.add_argument(
        "--no-sanitize",
        action="store_true",
        help="Don't mask serial numbers and credentials in output",
    )
    output_group.add_argument(
        "--no-archive",
        action="store_true",
        help="Don't create ZIP archive (output individual files)",
    )
    output_group.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress progress output",
    )

    # General options
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    return parser


async def run_interactive(args: argparse.Namespace) -> int:
    """Run in interactive mode, prompting for missing options."""
    from pylxpweb.cli.utils.prompts import (
        prompt_base_url,
        prompt_confirm,
        prompt_credentials,
        prompt_host,
        prompt_include_cloud,
        prompt_transport,
    )

    print(f"\n{'=' * 60}")
    print("  pylxpweb Modbus Diagnostic Tool v{__version__}")
    print(f"{'=' * 60}")

    # Transport selection
    if args.transport is None:
        args.transport = prompt_transport()

    # Host
    if args.host is None:
        args.host = prompt_host(args.transport)

    # Port defaults
    if args.port is None:
        if args.transport == "dongle":
            args.port = 8000
        else:
            args.port = 502

    # Cloud API
    include_cloud = args.cloud
    if not include_cloud:
        include_cloud = prompt_include_cloud()

    if include_cloud:
        if args.username is None:
            args.username, args.password = prompt_credentials()
        elif args.password is None:
            import getpass

            args.password = getpass.getpass("Password: ")

        if args.base_url == "https://monitor.eg4electronics.com":
            custom_url = prompt_confirm("Use default EG4 server?", default=True)
            if not custom_url:
                args.base_url = prompt_base_url()

    args.cloud = include_cloud

    # Confirm before proceeding
    print("\n" + "-" * 40)
    print("Configuration Summary:")
    print("-" * 40)
    print(f"  Transport: {args.transport}")
    print(f"  Host: {args.host}:{args.port}")
    input_end = args.input_start + args.input_count - 1
    holding_end = args.holding_start + args.holding_count - 1
    print(f"  Input registers: {args.input_start}-{input_end}")
    print(f"  Holding registers: {args.holding_start}-{holding_end}")
    if args.cloud:
        print(f"  Cloud API: Yes ({args.base_url})")
    else:
        print("  Cloud API: No")
    print(f"  Output: {args.output_dir}")
    print("-" * 40)

    if not prompt_confirm("\nProceed with collection?", default=True):
        print("Cancelled.")
        return 0

    return await run_collection(args)


async def run_collection(args: argparse.Namespace) -> int:
    """Run the data collection process."""
    from pylxpweb.cli.collectors import (
        CloudCollector,
        CollectionResult,
        DongleCollector,
        ModbusCollector,
        compare_collections,
    )
    from pylxpweb.cli.formatters import (
        ArchiveCreator,
        DiagnosticData,
        generate_filename,
    )
    from pylxpweb.cli.utils.github import generate_full_instructions
    from pylxpweb.cli.utils.serial_detect import format_device_info

    collections: list[CollectionResult] = []
    errors: list[str] = []

    # Prepare register ranges
    input_ranges = [(args.input_start, args.input_count)]
    holding_ranges = [(args.holding_start, args.holding_count)]

    def progress(msg: str) -> None:
        if not args.quiet:
            print(f"  {msg}")

    # Collect from local transports
    print("\n[1/4] Connecting to inverter...")

    if args.transport in ("modbus", "both"):
        print("\n  Collecting via Modbus TCP...")
        try:
            collector = ModbusCollector(
                host=args.host,
                port=args.port if args.transport == "modbus" else 502,
            )
            await collector.connect()

            # Auto-detect serial if not provided
            serial = args.serial or await collector.detect_serial()
            if serial and not args.quiet:
                print(f"  Detected serial: {serial}")

            result = await collector.collect(
                input_ranges=input_ranges,
                holding_ranges=holding_ranges,
                progress_callback=progress,
            )
            collections.append(result)
            await collector.disconnect()
            print(
                f"  ✓ Modbus collection complete: {result.input_register_count()} input, "
                f"{result.holding_register_count()} holding registers"
            )
        except Exception as e:
            error_msg = f"Modbus collection failed: {e}"
            errors.append(error_msg)
            print(f"  ✗ {error_msg}")

    if args.transport in ("dongle", "both"):
        print("\n  Collecting via WiFi Dongle...")
        dongle_serial = getattr(args, "dongle_serial", None)
        if not dongle_serial:
            print("  ✗ Dongle serial required for WiFi dongle connection")
            print("    Use --dongle-serial to specify the dongle serial number")
            errors.append("Dongle serial not provided")
        else:
            try:
                dongle_collector = DongleCollector(
                    host=args.host,
                    dongle_serial=dongle_serial,
                    inverter_serial=args.serial or "",
                    port=args.port if args.transport == "dongle" else 8000,
                )
                await dongle_collector.connect()

                serial = args.serial or await dongle_collector.detect_serial()
                if serial and not args.quiet:
                    print(f"  Detected serial: {serial}")

                result = await dongle_collector.collect(
                    input_ranges=input_ranges,
                    holding_ranges=holding_ranges,
                    progress_callback=progress,
                )
                collections.append(result)
                await dongle_collector.disconnect()
                print(
                    f"  ✓ Dongle collection complete: {result.input_register_count()} input, "
                    f"{result.holding_register_count()} holding registers"
                )
            except Exception as e:
                error_msg = f"Dongle collection failed: {e}"
                errors.append(error_msg)
                print(f"  ✗ {error_msg}")

    # Collect from cloud API
    if args.cloud and args.username:
        print("\n[2/4] Collecting from cloud API...")
        try:
            # Get serial from collected data
            cloud_serial = args.serial
            if not cloud_serial and collections:
                cloud_serial = collections[0].serial_number

            if not cloud_serial:
                print("  ✗ Cannot collect from cloud: no serial number available")
            else:
                cloud_collector = CloudCollector(
                    username=args.username,
                    password=args.password,
                    serial=cloud_serial,
                    base_url=args.base_url,
                )
                await cloud_collector.connect()
                result = await cloud_collector.collect(
                    input_ranges=[],  # Not available via cloud
                    holding_ranges=holding_ranges,
                    progress_callback=progress,
                )
                collections.append(result)
                await cloud_collector.disconnect()
                print(
                    f"  ✓ Cloud collection complete: {result.holding_register_count()} "
                    f"holding registers"
                )
        except Exception as e:
            error_msg = f"Cloud collection failed: {e}"
            errors.append(error_msg)
            print(f"  ✗ {error_msg}")
    else:
        print("\n[2/4] Skipping cloud API collection")

    # Check we have data
    if not collections:
        print("\n✗ No data collected. Cannot generate report.")
        return 1

    # Compare collections
    print("\n[3/4] Analyzing data...")
    comparison = None
    if len(collections) >= 2:
        comparison = compare_collections(collections[0], collections[1])
        if comparison.is_match():
            print("  ✓ All registers match between sources")
        else:
            print(
                f"  ⚠ Found {len(comparison.input_mismatches)} input and "
                f"{len(comparison.holding_mismatches)} holding register mismatches"
            )

    # Create diagnostic data
    primary = collections[0]
    data = DiagnosticData(
        collections=collections,
        comparison=comparison,
        metadata={
            "tool_version": __version__,
            "transport": args.transport,
            "host": args.host,
            "port": args.port,
            "cloud_enabled": args.cloud,
        },
        timestamp=datetime.now().astimezone(),
    )

    # Generate output
    print("\n[4/4] Generating output files...")
    sanitize = not args.no_sanitize
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.no_archive:
        # Output individual files
        from pylxpweb.cli.formatters import (
            BinaryFormatter,
            CSVFormatter,
            JSONFormatter,
            MarkdownFormatter,
        )

        base_name = generate_filename(primary.serial_number, sanitize).replace(".zip", "")

        json_fmt = JSONFormatter(sanitize=sanitize)
        json_path = output_dir / f"{base_name}.json"
        json_path.write_text(json_fmt.format(data))
        print(f"  ✓ {json_path}")

        md_fmt = MarkdownFormatter(sanitize=sanitize)
        md_path = output_dir / f"{base_name}.md"
        md_path.write_text(md_fmt.format(data))
        print(f"  ✓ {md_path}")

        csv_fmt = CSVFormatter(sanitize=sanitize)
        csv_path = output_dir / f"{base_name}.csv"
        csv_path.write_text(csv_fmt.format(data))
        print(f"  ✓ {csv_path}")

        bin_fmt = BinaryFormatter(sanitize=sanitize)
        bin_path = output_dir / f"{base_name}.bin"
        bin_path.write_bytes(bin_fmt.format(data))
        print(f"  ✓ {bin_path}")

        archive_path = None
    else:
        # Create ZIP archive
        archive = ArchiveCreator(sanitize=sanitize)
        filename = generate_filename(primary.serial_number, sanitize)
        archive_path = archive.create_file(data, output_dir / filename)
        print(f"  ✓ {archive_path}")

    # Summary
    print("\n" + "=" * 60)
    print("  Collection Complete!")
    print("=" * 60)

    # Device info
    device_info = format_device_info(
        serial=primary.serial_number,
        firmware=primary.firmware_version,
        model_code=primary.holding_registers.get(19),
    )
    print(f"\n{device_info}")

    # Statistics
    print(f"\nCollections: {len(collections)}")
    for c in collections:
        print(
            f"  - {c.source}: {c.input_register_count()} input, "
            f"{c.holding_register_count()} holding"
        )

    if comparison and not comparison.is_match():
        print(
            f"\n⚠ Mismatches found: {len(comparison.input_mismatches)} input, "
            f"{len(comparison.holding_mismatches)} holding"
        )

    if errors:
        print(f"\nWarnings: {len(errors)}")
        for err in errors:
            print(f"  - {err}")

    # GitHub instructions
    if archive_path:
        print("\n" + "-" * 60)
        instructions = generate_full_instructions(archive_path, data, sanitize)
        print(instructions)

    return 0


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Determine run mode
    if args.host is None:
        # Interactive mode
        return asyncio.run(run_interactive(args))
    else:
        # Non-interactive mode
        # Validate required options
        if args.transport is None:
            args.transport = "modbus"  # Default

        if args.port is None:
            args.port = 8000 if args.transport == "dongle" else 502

        if args.cloud and args.username is None:
            parser.error("--username is required when --cloud is specified")

        if args.cloud and args.password is None:
            import getpass

            args.password = getpass.getpass("Cloud password: ")

        return asyncio.run(run_collection(args))


if __name__ == "__main__":
    sys.exit(main())
