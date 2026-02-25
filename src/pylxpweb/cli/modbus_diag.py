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
from typing import TYPE_CHECKING

from pylxpweb import __version__

if TYPE_CHECKING:
    from pylxpweb.cli.collectors import DongleCollector, ModbusCollector

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

  pylxpweb-modbus-diag --host 192.168.1.100 --battery-probe
      Read battery registers (5000+) with 3-6 slot variations to detect rotation
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

    # Battery probe options
    battery_group = parser.add_argument_group("Battery Probe Options")
    battery_group.add_argument(
        "--battery-probe",
        action="store_true",
        help=(
            "Read battery registers (5000+) with slot variations (3-6) "
            "to detect round-robin rotation.  Iterations are adaptive: "
            "ceil(battery_count / slots) * 3 per variation."
        ),
    )
    battery_group.add_argument(
        "--battery-delay",
        type=float,
        default=1.0,
        help="Delay in seconds between battery read iterations (default: 1.0)",
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


async def _read_input_regs(
    collector: ModbusCollector | DongleCollector,
    start: int,
    count: int,
) -> list[int]:
    """Read input registers via collector's transport (must be connected)."""
    transport = collector._transport
    if transport is None:
        raise RuntimeError("Collector not connected")
    return await transport._read_input_registers(start, count)


def _parse_battery_slot(
    bat_regs: dict[int, int],
    slot_base: int,
) -> tuple[str, str]:
    """Parse one battery slot and return (detail_line, serial).

    Returns a formatted detail string and the decoded serial (may be empty).
    """
    status = bat_regs.get(slot_base, 0)
    voltage_raw = bat_regs.get(slot_base + 6, 0)
    soc_soh = bat_regs.get(slot_base + 8, 0)
    soc = soc_soh & 0xFF
    soh = (soc_soh >> 8) & 0xFF
    offset24 = bat_regs.get(slot_base + 24, 0)

    # Serial: 7 regs at offset 17-23
    serial_chars: list[str] = []
    for reg_off in range(7):
        raw_word = bat_regs.get(slot_base + 17 + reg_off, 0)
        lo = raw_word & 0xFF
        hi = (raw_word >> 8) & 0xFF
        if 32 <= lo <= 126:
            serial_chars.append(chr(lo))
        if 32 <= hi <= 126:
            serial_chars.append(chr(hi))
    slot_serial = "".join(serial_chars).strip()

    # Raw words for serial regs (for debugging truncation)
    serial_raw = " ".join(f"0x{bat_regs.get(slot_base + 17 + i, 0):04X}" for i in range(7))

    status_str = f"0x{status:04X}" if status else "empty"
    voltage = voltage_raw / 100.0
    pos_byte = (offset24 >> 8) & 0xFF

    detail = (
        f"{status_str} "
        f"V={voltage:.2f} SoC={soc}% SoH={soh}% "
        f"pos={pos_byte} "
        f"serial={slot_serial or '(empty)'!r} "
        f"raw=[{serial_raw}]"
    )
    return detail, slot_serial


async def _run_probe_experiment(
    collector: ModbusCollector | DongleCollector,
    label: str,
    num_slots: int,
    iterations: int,
    delay: float,
    lines: list[str],
    all_serials: set[str],
) -> None:
    """Run one battery probe experiment (read N slots for M iterations).

    Args:
        collector: Connected ModbusCollector
        label: Human-readable experiment label
        num_slots: Number of battery slots to read (e.g. 4 or 6)
        iterations: Number of read iterations
        delay: Delay in seconds between iterations
        lines: Output lines buffer
        all_serials: Set to accumulate unique serials seen
    """
    bat_header_start = 5000
    bat_header_count = 2
    bat_base = 5002
    bat_slot_count = 30
    bat_total = num_slots * bat_slot_count

    print(f"\n  --- {label}: {num_slots} slots, {iterations} iterations ---")
    lines.append("")
    lines.append(f"=== {label}: {num_slots} slots × {iterations} iterations ===")
    lines.append(f"  Registers: 5000-{bat_base + bat_total - 1}")
    lines.append("")

    prev_header: tuple[int, int] | None = None

    for iteration in range(iterations):
        # Read header regs 5000-5001
        try:
            header_vals = await _read_input_regs(collector, bat_header_start, bat_header_count)
            header_0 = header_vals[0]
            header_1 = header_vals[1]
        except Exception:
            header_0 = -1
            header_1 = -1

        # Detect header changes
        header_changed = prev_header is not None and (header_0, header_1) != prev_header
        prev_header = (header_0, header_1)
        change_marker = " *** HEADER CHANGED ***" if header_changed else ""

        # Read all battery slots in chunks of 40
        bat_regs: dict[int, int] = {}
        current = bat_base
        remaining = bat_total
        while remaining > 0:
            chunk = min(remaining, 40)
            try:
                vals = await _read_input_regs(collector, current, chunk)
                for offset, val in enumerate(vals):
                    bat_regs[current + offset] = val
                current += chunk
                remaining -= chunk
            except Exception as e:
                lines.append(f"  [iter {iteration}] Read failed at reg {current}: {e}")
                break

        # Parse each slot
        slot_details: list[str] = []
        slot_serials: list[str] = []
        for slot_idx in range(num_slots):
            slot_base = bat_base + (slot_idx * bat_slot_count)
            detail, slot_serial = _parse_battery_slot(bat_regs, slot_base)
            slot_details.append(f"slot{slot_idx}: {detail}")
            slot_serials.append(slot_serial or "(empty)")
            if slot_serial:
                all_serials.add(slot_serial)

        # Full detail line: header as both hex and decimal
        header_detail = (
            f"[{iteration:3d}] "
            f"r5000=0x{header_0:04X}({header_0}) "
            f"r5001=0x{header_1:04X}({header_1})"
            f"{change_marker}"
        )
        line = f"{header_detail} | " + " | ".join(slot_details)
        lines.append(line)

        # Console output (abbreviated)
        serial_summary = " | ".join(slot_serials)
        marker = " <<< CHANGED" if header_changed else ""
        print(
            f"  [{iteration:3d}] r5000={header_0:5d} r5001={header_1:5d}  {serial_summary}{marker}"
        )

        if iteration < iterations - 1:
            await asyncio.sleep(delay)


async def run_battery_probe(args: argparse.Namespace) -> int:
    """Read battery registers (5000+) repeatedly to detect round-robin rotation.

    Runs multiple experiments varying the number of slots read (3-6) to
    understand how the inverter firmware exposes batteries.  For each slot
    count, the number of iterations is adaptive:

        iterations = ceil(battery_count / num_slots) * 3

    This ensures enough reads to observe a full rotation (if one exists).

    Output is saved to a text file for attaching to GitHub issues.
    """
    import math

    from pylxpweb.cli.collectors import DongleCollector, ModbusCollector

    delay: float = args.battery_delay
    transport_type: str = args.transport

    print(f"\n{'=' * 70}")
    print("  Battery Round-Robin Probe")
    print(f"{'=' * 70}")
    print(f"  Host: {args.host}:{args.port}")
    print(f"  Transport: {transport_type}")
    print(f"  Delay: {delay}s between reads")
    print(f"{'=' * 70}")

    # Create the appropriate collector
    collector: ModbusCollector | DongleCollector
    if transport_type == "dongle":
        dongle_serial = getattr(args, "dongle_serial", None) or ""
        if not dongle_serial:
            print("  ✗ --dongle-serial is required for dongle transport")
            print(
                "    Usage: pylxpweb-modbus-diag --host <IP> --transport dongle "
                "--dongle-serial <SERIAL> --battery-probe"
            )
            return 1
        collector = DongleCollector(
            host=args.host,
            dongle_serial=dongle_serial,
            inverter_serial=args.serial or "",
            port=args.port,
        )
    else:
        collector = ModbusCollector(
            host=args.host,
            port=args.port,
        )

    try:
        await collector.connect()
    except Exception as e:
        print(f"  ✗ Connection failed: {e}")
        return 1

    serial = args.serial or await collector.detect_serial() or "UNKNOWN"
    print(f"\n  Inverter serial: {serial}")

    # Read battery_count from reg 96
    try:
        regs_96 = await _read_input_regs(collector, 96, 1)
        battery_count = regs_96[0]
        print(f"  battery_count (reg 96): {battery_count}")
    except Exception:
        battery_count = 12  # sensible default for probing
        print(f"  ⚠ Could not read reg 96 (battery_count), assuming {battery_count}")

    # Collect results
    lines: list[str] = []
    lines.append(f"Battery Round-Robin Probe — {serial}")
    lines.append(f"battery_count (reg 96): {battery_count}")
    lines.append(f"Delay between reads: {delay}s")
    lines.append(f"pylxpweb version: {__version__}")

    all_serials_seen: set[str] = set()

    # Slot variations: 3, 4, 5, 6
    # For each, iterations = ceil(battery_count / slots) * 3
    slot_variations = [3, 4, 5, 6]

    for exp_num, num_slots in enumerate(slot_variations, start=1):
        exp_iters = max(math.ceil(battery_count / num_slots) * 3, 6)
        await _run_probe_experiment(
            collector=collector,
            label=f"Experiment {exp_num}: {num_slots}-slot read",
            num_slots=num_slots,
            iterations=exp_iters,
            delay=delay,
            lines=lines,
            all_serials=all_serials_seen,
        )

    await collector.disconnect()

    # Summary
    lines.append("")
    lines.append(f"Unique serials seen across all experiments: {len(all_serials_seen)}")
    for s in sorted(all_serials_seen):
        lines.append(f"  - {s}")

    print(f"\n{'=' * 70}")
    print(f"  Unique serials seen (all experiments): {len(all_serials_seen)}")
    for s in sorted(all_serials_seen):
        print(f"    - {s}")

    # Save to file
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"battery_probe_{serial}_{ts}.txt"
    output_file.write_text("\n".join(lines) + "\n")
    print(f"\n  ✓ Saved to {output_file}")

    return 0


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Determine run mode
    if getattr(args, "battery_probe", False):
        # Battery probe mode — needs host
        if args.host is None:
            parser.error("--host is required for battery probe")
        if args.transport is None:
            args.transport = "modbus"
        if args.port is None:
            args.port = 8000 if args.transport == "dongle" else 502
        return asyncio.run(run_battery_probe(args))
    elif args.host is None:
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
