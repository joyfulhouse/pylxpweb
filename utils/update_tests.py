#!/usr/bin/env python3
"""Update test files to use new modular client structure."""

import re
from pathlib import Path

# Mapping of old method calls to new endpoint-style calls
METHOD_MAPPINGS = {
    # Plants endpoints
    r"client\.get_plants\(": "client.plants.get_plants(",
    r"client\.get_plant_details\(": "client.plants.get_plant_details(",
    r"client\.update_plant_config\(": "client.plants.update_plant_config(",
    r"client\.set_daylight_saving_time\(": "client.plants.set_daylight_saving_time(",
    r"client\.get_plant_overview\(": "client.plants.get_plant_overview(",
    r"client\.get_inverter_overview\(": "client.plants.get_inverter_overview(",
    # Devices endpoints
    r"client\.get_parallel_group_details\(": "client.devices.get_parallel_group_details(",
    r"client\.get_devices\(": "client.devices.get_devices(",
    r"client\.get_inverter_runtime\(": "client.devices.get_inverter_runtime(",
    r"client\.get_inverter_energy\(": "client.devices.get_inverter_energy(",
    r"client\.get_parallel_energy\(": "client.devices.get_parallel_energy(",
    r"client\.get_battery_info\(": "client.devices.get_battery_info(",
    r"client\.get_midbox_runtime\(": "client.devices.get_midbox_runtime(",
    # Control endpoints
    r"client\.read_parameters\(": "client.control.read_parameters(",
    r"client\.write_parameter\(": "client.control.write_parameter(",
    r"client\.control_function\(": "client.control.control_function(",
    r"client\.start_quick_charge\(": "client.control.start_quick_charge(",
    r"client\.stop_quick_charge\(": "client.control.stop_quick_charge(",
    r"client\.get_quick_charge_status\(": "client.control.get_quick_charge_status(",
    # Analytics endpoints
    r"client\.get_chart_data\(": "client.analytics.get_chart_data(",
    r"client\.get_energy_day_breakdown\(": "client.analytics.get_energy_day_breakdown(",
    r"client\.get_energy_month_breakdown\(": "client.analytics.get_energy_month_breakdown(",
    r"client\.get_energy_year_breakdown\(": "client.analytics.get_energy_year_breakdown(",
    r"client\.get_energy_total_breakdown\(": "client.analytics.get_energy_total_breakdown(",
    r"client\.get_event_list\(": "client.analytics.get_event_list(",
    r"client\.get_battery_list\(": "client.analytics.get_battery_list(",
    r"client\.get_inverter_info\(": "client.analytics.get_inverter_info(",
    # Forecasting endpoints
    r"client\.get_solar_forecast\(": "client.forecasting.get_solar_forecast(",
    r"client\.get_weather_forecast\(": "client.forecasting.get_weather_forecast(",
    # Export endpoints
    r"client\.export_data\(": "client.export.export_data(",
    # Firmware endpoints
    r"client\.check_firmware_updates\(": "client.firmware.check_firmware_updates(",
    r"client\.get_firmware_update_status\(": "client.firmware.get_firmware_update_status(",
    r"client\.check_update_eligibility\(": "client.firmware.check_update_eligibility(",
    r"client\.start_firmware_update\(": "client.firmware.start_firmware_update(",
}


def update_file(file_path: Path) -> tuple[int, list[str]]:
    """Update a single test file.

    Returns:
        Tuple of (number of replacements, list of changes made)
    """
    with open(file_path) as f:
        content = f.read()

    original_content = content
    changes = []
    replacement_count = 0

    for old_pattern, new_call in METHOD_MAPPINGS.items():
        matches = list(re.finditer(old_pattern, content))
        if matches:
            old_method = old_pattern.replace(r"client\.", "").replace(r"\(", "(")
            new_method = new_call.replace("client.", "")
            changes.append(f"  {old_method} → {new_method}")
            replacement_count += len(matches)
            content = re.sub(old_pattern, new_call, content)

    if content != original_content:
        with open(file_path, "w") as f:
            f.write(content)

    return replacement_count, changes


def main():
    """Update all test files."""
    test_files = [
        Path("tests/unit/test_client.py"),
        Path("tests/unit/test_firmware.py"),
        Path("tests/integration/test_live_api.py"),
        Path("tests/integration/test_new_endpoints.py"),
        Path("tests/integration/test_dst_control.py"),
        Path("tests/integration/test_firmware_endpoints.py"),
    ]

    total_replacements = 0
    files_updated = 0

    print("Updating test files for modular client structure...\n")

    for file_path in test_files:
        if not file_path.exists():
            print(f"⚠️  Skipping {file_path} (not found)")
            continue

        count, changes = update_file(file_path)

        if count > 0:
            files_updated += 1
            total_replacements += count
            print(f"✅ {file_path}")
            for change in changes:
                print(change)
            print(f"   Total: {count} replacements\n")
        else:
            print(f"⏭️  {file_path} (no changes needed)\n")

    print(f"\n{'=' * 60}")
    print("Summary:")
    print(f"  Files updated: {files_updated}")
    print(f"  Total replacements: {total_replacements}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
