#!/usr/bin/env python3
"""Remove orphaned method remnants from client.py."""

# Read the file
with open("src/pylxpweb/client.py") as f:
    lines = f.readlines()

# Orphaned return type lines to remove (with their docstrings/bodies)
orphan_lines = [444, 519, 553, 588, 607, 628, 715, 763, 809, 867, 911, 952, 990, 1049]


def find_orphan_end(lines, start_idx):
    """Find the end of an orphaned method body."""
    # Look for next method or class-level code at same/lower indentation
    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        if line.strip() == "":
            continue
        # If we find a line starting with 4 spaces or less (not 8+), we've hit the end
        if not line.startswith("        ") and line.strip():
            return i
    return len(lines)


# Convert to 0-indexed
orphan_indices = [line - 1 for line in orphan_lines]

# Find ranges to remove
ranges_to_remove = set()
for idx in orphan_indices:
    end_idx = find_orphan_end(lines, idx)
    print(f"Removing orphan at line {idx + 1} to {end_idx}")
    for i in range(idx, end_idx):
        ranges_to_remove.add(i)

# Build new content
new_lines = [line for i, line in enumerate(lines) if i not in ranges_to_remove]

# Write back
with open("src/pylxpweb/client.py", "w") as f:
    f.writelines(new_lines)

print(f"\nRemoved {len(ranges_to_remove)} lines")
print(f"Old line count: {len(lines)}")
print(f"New line count: {len(new_lines)}")
