#!/usr/bin/env python3
"""Compare GridBOSS Modbus registers against Cloud API data.

Reads GridBOSS MID device data from both sources and prints a side-by-side
comparison table.  Useful for diagnosing data mismatches (off-by-one, scaling
errors, firmware-specific register shifts).

Connection to the GridBOSS is via WiFi dongle (the only supported transport
for MID devices).  Cloud API data comes from getMidboxRuntime.

Environment variables (loaded from .env in repo root):
    LUXPOWER_USERNAME      Cloud API username
    LUXPOWER_PASSWORD      Cloud API password
    LUXPOWER_BASE_URL      Cloud API base URL (default: https://monitor.eg4electronics.com)
    GRIDBOSS_DONGLE_IP     WiFi dongle IP address
    GRIDBOSS_DONGLE_SERIAL WiFi dongle serial number
    GRIDBOSS_INVERTER_SERIAL GridBOSS inverter serial number
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# Suppress noisy library output
logging.getLogger("pymodbus").setLevel(logging.ERROR)
logging.getLogger("pylxpweb").setLevel(logging.WARNING)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

USERNAME = os.environ["LUXPOWER_USERNAME"]
PASSWORD = os.environ["LUXPOWER_PASSWORD"]
BASE_URL = os.getenv("LUXPOWER_BASE_URL", "https://monitor.eg4electronics.com")

DONGLE_IP = os.environ["GRIDBOSS_DONGLE_IP"]
DONGLE_SERIAL = os.environ["GRIDBOSS_DONGLE_SERIAL"]
GRIDBOSS_SERIAL = os.environ["GRIDBOSS_INVERTER_SERIAL"]


# ---------------------------------------------------------------------------
# Cloud API reader
# ---------------------------------------------------------------------------


async def read_cloud_api(serial: str):
    """Fetch raw MidboxData from Cloud API getMidboxRuntime."""
    from pylxpweb import LuxpowerClient

    async with LuxpowerClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
        midbox_response = await client.api.devices.get_midbox_runtime(serial)
        return midbox_response.midboxData


# ---------------------------------------------------------------------------
# Dongle Modbus reader
# ---------------------------------------------------------------------------


async def read_dongle_registers(
    host: str,
    dongle_serial: str,
    inverter_serial: str,
    port: int = 8000,
) -> dict[int, int]:
    """Read all GridBOSS input registers + holding register 20 via dongle.

    Returns a dict mapping register address to raw 16-bit value.
    Holding register 20 is stored with a special key: ``"hold_20"``.
    """
    from pylxpweb.transports import create_dongle_transport

    transport = create_dongle_transport(
        host=host,
        port=port,
        inverter_serial=inverter_serial,
        dongle_serial=dongle_serial,
    )
    await transport.connect()

    registers: dict[int, int] = {}

    # Read input registers in standard GridBOSS groups
    groups = [(0, 40), (40, 28), (68, 40), (108, 12), (128, 4)]
    for start, count in groups:
        try:
            values = await transport._read_input_registers(start, count)
            for offset, value in enumerate(values):
                registers[start + offset] = value
        except Exception as exc:
            print(f"  WARNING: Failed to read input regs {start}-{start+count-1}: {exc}")
        await asyncio.sleep(0.3)

    # Holding register 20 — smart port status (bit-packed)
    try:
        holding = await transport._read_holding_registers(20, 1)
        registers["hold_20"] = holding[0]
    except Exception as exc:
        print(f"  WARNING: Failed to read holding reg 20: {exc}")

    await transport.disconnect()
    return registers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def signed16(value: int) -> int:
    """Convert unsigned 16-bit to signed."""
    return value - 65536 if value > 32767 else value


def _scale(raw: int, scale_factor, *, is_signed: bool = False) -> float:
    """Apply scale factor to a raw register value."""
    val = signed16(raw) if is_signed else raw
    if scale_factor.name == "DIV_10":
        return val / 10.0
    if scale_factor.name == "DIV_100":
        return val / 100.0
    return float(val)


def _combine_32bit(low: int, high: int) -> int:
    """Combine two 16-bit registers into a 32-bit value (low + high << 16)."""
    return low + (high << 16)


_STATUS_LABELS = {0: "unused", 1: "smart_load", 2: "ac_couple"}


# ---------------------------------------------------------------------------
# Comparison table builder
# ---------------------------------------------------------------------------


def format_comparison(
    cloud_data,
    modbus_regs: dict[int, int],
) -> None:
    """Print a full comparison between Cloud API and Dongle Modbus."""
    from pylxpweb.registers.gridboss import GRIDBOSS_REGISTERS

    print("\n" + "=" * 110)
    print("GRIDBOSS: CLOUD API vs DONGLE MODBUS COMPARISON")
    print("=" * 110)

    # Table header
    hdr = (
        f"{'Field':<35} {'API field':<28} {'Cloud':>10} {'Reg':>5} "
        f"{'Modbus':>10} {'Scaled':>10} {'Match':>7}"
    )
    rows: list[str] = []
    mismatches: list[str] = []

    current_category = None

    for reg_def in GRIDBOSS_REGISTERS:
        # Section headers
        if reg_def.category.value != current_category:
            current_category = reg_def.category.value
            rows.append(f"\n--- {current_category.upper().replace('_', ' ')} ---")
            rows.append(hdr)
            rows.append("-" * 110)

        api_field = reg_def.cloud_api_field or ""
        cloud_val = getattr(cloud_data, api_field, None) if api_field else None

        addr = reg_def.address
        if reg_def.bit_width == 32:
            low = modbus_regs.get(addr, 0)
            high = modbus_regs.get(addr + 1, 0)
            modbus_raw = _combine_32bit(low, high)
            reg_label = f"{addr}/{addr+1}"
        else:
            modbus_raw = modbus_regs.get(addr, 0)
            if reg_def.signed:
                modbus_raw = signed16(modbus_raw)
            reg_label = str(addr)

        # Scale the modbus value
        if reg_def.bit_width == 32:
            modbus_scaled = modbus_raw / 10.0 if reg_def.scale.name == "DIV_10" else float(modbus_raw)
        else:
            modbus_scaled = _scale(
                modbus_regs.get(addr, 0), reg_def.scale, is_signed=reg_def.signed
            )

        unit = reg_def.unit or ""

        # Compare: cloud API values are raw (pre-scale), modbus_raw is also raw
        # For 16-bit regs: cloud should equal modbus_raw (both raw)
        # For 32-bit regs: cloud is the combined 32-bit raw value
        if cloud_val is not None:
            match = "OK" if cloud_val == modbus_raw else "DIFF"
        else:
            match = "n/a"

        cloud_str = str(cloud_val) if cloud_val is not None else "-"
        modbus_str = str(modbus_raw)
        scaled_str = f"{modbus_scaled:.1f}{unit}" if unit else str(modbus_scaled)

        row = (
            f"{reg_def.canonical_name:<35} {api_field:<28} {cloud_str:>10} "
            f"{reg_label:>5} {modbus_str:>10} {scaled_str:>10} {match:>7}"
        )
        rows.append(row)

        if match == "DIFF":
            mismatches.append(
                f"  {reg_def.canonical_name}: cloud={cloud_val} modbus={modbus_raw} "
                f"(reg {reg_label}, {reg_def.description})"
            )

    for row in rows:
        print(row)

    # ------------------------------------------------------------------
    # Smart port status from holding register 20
    # ------------------------------------------------------------------
    print("\n--- SMART PORT STATUS (holding register 20) ---")
    hold_20 = modbus_regs.get("hold_20", 0)
    print(f"Holding reg 20 raw = {hold_20} (0b{hold_20:08b})")
    for port in range(1, 5):
        modbus_status = (hold_20 >> ((port - 1) * 2)) & 0x03
        cloud_status = getattr(cloud_data, f"smartPort{port}Status", None)
        label_m = _STATUS_LABELS.get(modbus_status, f"unknown({modbus_status})")
        label_c = _STATUS_LABELS.get(cloud_status, f"unknown({cloud_status})")
        match = "OK" if cloud_status == modbus_status else "DIFF"
        print(
            f"  Port {port}: cloud={label_c}({cloud_status})  "
            f"modbus={label_m}({modbus_status})  {match}"
        )
        if match == "DIFF":
            mismatches.append(
                f"  smart_port{port}_status: cloud={cloud_status} modbus={modbus_status}"
            )

    # ------------------------------------------------------------------
    # Smart port energy focus (the off-by-one diagnostic)
    # ------------------------------------------------------------------
    print("\n--- SMART PORT ENERGY FOCUS (issue #146 diagnostic) ---")
    print("Checking if Cloud API port N energy matches Modbus port N-1 (off-by-one).")

    for energy_type, daily_base, lifetime_base in [
        ("smart_load", 50, 84),
        ("ac_couple", 60, 104),
    ]:
        print(f"\n  {energy_type.upper()} Daily Energy (regs {daily_base}-{daily_base+7}):")
        for port in range(1, 5):
            cloud_l1 = getattr(cloud_data, f"e{energy_type.replace('_', '').title().replace(' ', '')}{port}TodayL1", None)
            # Simpler approach: construct the field name explicitly
            if energy_type == "smart_load":
                cloud_l1 = getattr(cloud_data, f"eSmartLoad{port}TodayL1", None)
                cloud_l2 = getattr(cloud_data, f"eSmartLoad{port}TodayL2", None)
            else:
                cloud_l1 = getattr(cloud_data, f"eACcouple{port}TodayL1", None)
                cloud_l2 = getattr(cloud_data, f"eACcouple{port}TodayL2", None)

            reg_l1 = daily_base + (port - 1) * 2
            reg_l2 = reg_l1 + 1
            modbus_l1 = modbus_regs.get(reg_l1, 0)
            modbus_l2 = modbus_regs.get(reg_l2, 0)

            match_same = "OK" if cloud_l1 == modbus_l1 and cloud_l2 == modbus_l2 else "DIFF"

            # Off-by-one check: does cloud port N match modbus port N-1?
            if port > 1:
                prev_l1 = modbus_regs.get(reg_l1 - 2, 0)
                prev_l2 = modbus_regs.get(reg_l2 - 2, 0)
                off_by_one = (
                    "OFF-BY-ONE!"
                    if (cloud_l1 == prev_l1 and cloud_l2 == prev_l2
                        and (cloud_l1 or cloud_l2))
                    else ""
                )
            else:
                off_by_one = ""

            print(
                f"    Port {port}: cloud=({cloud_l1},{cloud_l2}) "
                f"modbus_reg({reg_l1},{reg_l2})=({modbus_l1},{modbus_l2}) "
                f"{match_same} {off_by_one}"
            )

        print(f"\n  {energy_type.upper()} Lifetime Energy (regs {lifetime_base}+):")
        for port in range(1, 5):
            if energy_type == "smart_load":
                cloud_l1 = getattr(cloud_data, f"eSmartLoad{port}TotalL1", None)
                cloud_l2 = getattr(cloud_data, f"eSmartLoad{port}TotalL2", None)
            else:
                cloud_l1 = getattr(cloud_data, f"eACcouple{port}TotalL1", None)
                cloud_l2 = getattr(cloud_data, f"eACcouple{port}TotalL2", None)

            base = lifetime_base + (port - 1) * 4
            low_l1 = modbus_regs.get(base, 0)
            high_l1 = modbus_regs.get(base + 1, 0)
            low_l2 = modbus_regs.get(base + 2, 0)
            high_l2 = modbus_regs.get(base + 3, 0)
            modbus_l1 = _combine_32bit(low_l1, high_l1)
            modbus_l2 = _combine_32bit(low_l2, high_l2)

            match_same = "OK" if cloud_l1 == modbus_l1 and cloud_l2 == modbus_l2 else "DIFF"

            # Off-by-one check
            if port > 1:
                prev_base = base - 4
                prev_l1 = _combine_32bit(
                    modbus_regs.get(prev_base, 0), modbus_regs.get(prev_base + 1, 0)
                )
                prev_l2 = _combine_32bit(
                    modbus_regs.get(prev_base + 2, 0), modbus_regs.get(prev_base + 3, 0)
                )
                off_by_one = (
                    "OFF-BY-ONE!"
                    if (cloud_l1 == prev_l1 and cloud_l2 == prev_l2
                        and (cloud_l1 or cloud_l2))
                    else ""
                )
            else:
                off_by_one = ""

            kwh_l1 = modbus_l1 / 10.0
            kwh_l2 = modbus_l2 / 10.0
            print(
                f"    Port {port}: cloud=({cloud_l1},{cloud_l2}) "
                f"modbus_reg({base}-{base+3})=({modbus_l1},{modbus_l2}) "
                f"[{kwh_l1:.1f}/{kwh_l2:.1f} kWh] {match_same} {off_by_one}"
            )

    # ------------------------------------------------------------------
    # Mismatch summary
    # ------------------------------------------------------------------
    if mismatches:
        print(f"\n{'=' * 110}")
        print(f"MISMATCHES FOUND: {len(mismatches)}")
        print("=" * 110)
        for m in mismatches:
            print(m)
        print(
            "\nNote: Small differences (1-2 units) in energy fields are normal "
            "due to timing between Cloud API and Modbus reads."
        )
    else:
        print(f"\n{'=' * 110}")
        print("ALL VALUES MATCH")
        print("=" * 110)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    """Entry point."""
    print("GridBOSS (MID) — Cloud API vs Dongle Modbus Comparison")
    print(f"GridBOSS serial : {GRIDBOSS_SERIAL}")
    print(f"Dongle          : {DONGLE_SERIAL} @ {DONGLE_IP}:8000")
    print(f"Cloud API       : {BASE_URL}")
    print("=" * 110)

    print("\nReading from Cloud API...")
    cloud_task = read_cloud_api(GRIDBOSS_SERIAL)

    print("Reading from Dongle Modbus...")
    dongle_task = read_dongle_registers(
        DONGLE_IP, DONGLE_SERIAL, GRIDBOSS_SERIAL
    )

    cloud_data, modbus_regs = await asyncio.gather(cloud_task, dongle_task)
    print("  Cloud API: OK")
    print(f"  Dongle Modbus: {len([k for k in modbus_regs if isinstance(k, int)])} input registers")

    format_comparison(cloud_data, modbus_regs)


if __name__ == "__main__":
    asyncio.run(main())
