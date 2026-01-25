"""Interactive prompts for the Modbus diagnostic CLI tool.

Provides user-friendly prompts for collecting configuration options.
"""

from __future__ import annotations

import getpass
from typing import Literal


def prompt_transport() -> Literal["modbus", "dongle", "both"]:
    """Prompt user to select transport type.

    Returns:
        Selected transport: "modbus", "dongle", or "both"
    """
    print("\nSelect connection method:")
    print("  1. Modbus TCP (RS485-to-Ethernet adapter, port 502)")
    print("  2. WiFi Dongle (direct connection, port 8000)")
    print("  3. Both (compare data from both sources)")
    print()

    while True:
        choice = input("Enter choice [1-3] (default: 1): ").strip() or "1"
        if choice == "1":
            return "modbus"
        elif choice == "2":
            return "dongle"
        elif choice == "3":
            return "both"
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")


def prompt_host(transport: str) -> str:
    """Prompt user for inverter host/IP address.

    Args:
        transport: Transport type for context in prompt

    Returns:
        Host address
    """
    hint = "RS485-to-Ethernet adapter" if transport == "modbus" else "WiFi dongle"

    print(f"\nEnter inverter IP address ({hint}):")
    while True:
        host = input("IP address (e.g., 192.168.1.100): ").strip()
        if host:
            return host
        print("IP address is required.")


def prompt_serial(detected_serial: str | None = None) -> str:
    """Prompt user for serial number with optional auto-detected value.

    Args:
        detected_serial: Auto-detected serial from registers (if available)

    Returns:
        Serial number to use
    """
    if detected_serial:
        print(f"\nSerial number detected: {detected_serial}")
        override = input("Press Enter to use detected serial, or enter a different one: ").strip()
        return override if override else detected_serial
    else:
        print("\nCould not auto-detect serial number.")
        while True:
            serial = input("Enter inverter serial number (10 characters): ").strip()
            if serial:
                return serial
            print("Serial number is required.")


def prompt_credentials() -> tuple[str, str]:
    """Prompt user for Luxpower/EG4 cloud credentials.

    Returns:
        Tuple of (username, password)
    """
    print("\nEnter Luxpower/EG4 cloud credentials:")
    print("(These are used to fetch data from the monitoring API for comparison)")
    print()

    while True:
        username = input("Username (email): ").strip()
        if username:
            break
        print("Username is required.")

    while True:
        password = getpass.getpass("Password: ")
        if password:
            break
        print("Password is required.")

    return username, password


def prompt_base_url() -> str:
    """Prompt user for API base URL.

    Returns:
        Base URL for API
    """
    print("\nSelect monitoring server:")
    print("  1. EG4 Electronics (US) - monitor.eg4electronics.com [default]")
    print("  2. Luxpower (US) - us.luxpowertek.com")
    print("  3. Luxpower (EU) - eu.luxpowertek.com")
    print("  4. Custom URL")
    print()

    urls = {
        "1": "https://monitor.eg4electronics.com",
        "2": "https://us.luxpowertek.com",
        "3": "https://eu.luxpowertek.com",
    }

    while True:
        choice = input("Enter choice [1-4] (default: 1): ").strip() or "1"
        if choice in urls:
            return urls[choice]
        elif choice == "4":
            custom = input("Enter custom URL (e.g., https://example.com): ").strip()
            if custom:
                if not custom.startswith(("http://", "https://")):
                    custom = f"https://{custom}"
                return custom.rstrip("/")
            print("URL is required.")
        else:
            print("Invalid choice. Please enter 1-4.")


def prompt_register_ranges(
    default_input: list[tuple[int, int]],
    default_holding: list[tuple[int, int]],
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Prompt user for register ranges to read.

    Args:
        default_input: Default input register ranges
        default_holding: Default holding register ranges

    Returns:
        Tuple of (input_ranges, holding_ranges)
    """
    print("\nRegister ranges to read:")
    print(f"  Default input registers: {_format_ranges(default_input)}")
    print(f"  Default holding registers: {_format_ranges(default_holding)}")
    print()

    use_defaults = input("Use default ranges? [Y/n]: ").strip().lower()
    if use_defaults != "n":
        return default_input, default_holding

    print("\nEnter custom ranges (format: start-end,start-end,...):")
    print("Example: 0-100,200-250")
    print()

    input_ranges = _prompt_range_input("Input register ranges", default_input)
    holding_ranges = _prompt_range_input("Holding register ranges", default_holding)

    return input_ranges, holding_ranges


def _prompt_range_input(
    label: str,
    default: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Prompt for a single range input."""
    default_str = _format_ranges(default)
    while True:
        raw = input(f"{label} [{default_str}]: ").strip()
        if not raw:
            return default

        try:
            return _parse_ranges(raw)
        except ValueError as e:
            print(f"Invalid format: {e}")
            print("Use format: start-end,start-end,...")


def _format_ranges(ranges: list[tuple[int, int]]) -> str:
    """Format ranges as string."""
    return ", ".join(f"{start}-{start + count - 1}" for start, count in ranges)


def _parse_ranges(raw: str) -> list[tuple[int, int]]:
    """Parse range string into list of (start, count) tuples."""
    ranges = []
    for part in raw.split(","):
        part = part.strip()
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            start = int(start_str.strip())
            end = int(end_str.strip())
            if start > end:
                raise ValueError(f"Start ({start}) must be <= end ({end})")
            count = end - start + 1
            ranges.append((start, count))
        else:
            # Single register
            addr = int(part)
            ranges.append((addr, 1))
    return ranges


def prompt_confirm(message: str, default: bool = True) -> bool:
    """Prompt user for yes/no confirmation.

    Args:
        message: Confirmation message
        default: Default value if user presses Enter

    Returns:
        True if confirmed, False otherwise
    """
    default_str = "Y/n" if default else "y/N"
    while True:
        response = input(f"{message} [{default_str}]: ").strip().lower()
        if not response:
            return default
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        print("Please enter 'y' or 'n'.")


def prompt_include_cloud() -> bool:
    """Prompt whether to include cloud API data.

    Returns:
        True to include cloud data
    """
    print("\nInclude cloud API data for comparison?")
    print("This will fetch register data from the Luxpower/EG4 monitoring API")
    print("to compare against local Modbus readings.")
    print()
    return prompt_confirm("Include cloud data?", default=True)


def prompt_output_directory() -> str:
    """Prompt for output directory.

    Returns:
        Output directory path
    """
    import os

    default_dir = os.getcwd()
    print(f"\nOutput directory (default: {default_dir}):")
    dir_path = input("Directory: ").strip()
    return dir_path if dir_path else default_dir
