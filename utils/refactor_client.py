#!/usr/bin/env python3
"""Script to refactor client.py by removing extracted endpoint methods."""

import re

# Read the current client.py
with open("src/pylxpweb/client.py") as f:
    content = f.read()
    lines = content.splitlines(keepends=True)

# Methods to remove (these have been extracted to endpoint modules)
METHODS_TO_REMOVE = [
    # Plants methods
    "get_plant_details",
    "_fetch_country_location_from_api",
    "_prepare_plant_update_data",
    "update_plant_config",
    "set_daylight_saving_time",
    "get_plant_overview",
    "get_inverter_overview",
    # Devices methods
    "get_parallel_group_details",
    "get_devices",
    "get_inverter_runtime",
    "get_inverter_energy",
    "get_parallel_energy",
    "get_battery_info",
    "get_midbox_runtime",
    # Control methods
    "read_parameters",
    "write_parameter",
    "control_function",
    "start_quick_charge",
    "stop_quick_charge",
    "get_quick_charge_status",
    # Analytics methods
    "get_chart_data",
    "get_energy_day_breakdown",
    "get_energy_month_breakdown",
    "get_energy_year_breakdown",
    "get_energy_total_breakdown",
    "get_event_list",
    "get_battery_list",
    "get_inverter_info",
    # Forecasting methods
    "get_solar_forecast",
    "get_weather_forecast",
    # Export methods
    "export_data",
    # Firmware methods
    "check_firmware_updates",
    "get_firmware_update_status",
    "check_update_eligibility",
    "start_firmware_update",
]


def find_method_range(lines, method_name):
    """Find the start and end line numbers of a method."""
    # Find method start
    start_idx = None
    for i, line in enumerate(lines):
        # Match: "    async def method_name(" or "    def method_name("
        if re.match(rf"^\s+(async\s+)?def {re.escape(method_name)}\(", line):
            start_idx = i
            break

    if start_idx is None:
        return None, None

    # Find method end (next method or class-level code at same indentation)
    indent_level = len(lines[start_idx]) - len(lines[start_idx].lstrip())
    end_idx = None

    for i in range(start_idx + 1, len(lines)):
        line = lines[i]

        # Skip empty lines
        if line.strip() == "":
            continue

        # Check if we've hit another method or class-level code
        current_indent = len(line) - len(line.lstrip())
        if current_indent <= indent_level and line.strip():
            # Found next method or class-level statement
            end_idx = i
            break

    # If no end found, go to end of file
    if end_idx is None:
        end_idx = len(lines)

    return start_idx, end_idx


# Remove methods
removed_methods = []
lines_to_remove = set()

for method_name in METHODS_TO_REMOVE:
    start, end = find_method_range(lines, method_name)
    if start is not None:
        print(f"Found {method_name}: lines {start + 1}-{end}")
        removed_methods.append(method_name)
        for i in range(start, end):
            lines_to_remove.add(i)
    else:
        print(f"WARNING: Could not find method: {method_name}")

# Build new content
new_lines = [line for i, line in enumerate(lines) if i not in lines_to_remove]

# Write new client.py
with open("src/pylxpweb/client.py", "w") as f:
    f.writelines(new_lines)

print(f"\nRemoved {len(removed_methods)} methods:")
for method in removed_methods:
    print(f"  - {method}")

print(f"\nOld line count: {len(lines)}")
print(f"New line count: {len(new_lines)}")
print(f"Lines removed: {len(lines_to_remove)}")
