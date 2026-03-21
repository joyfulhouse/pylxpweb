#!/usr/bin/env python3
"""Compare Modbus registers against Web API data for FlexBOSS21.

Reads from both sources and compares values to identify register correlations.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Suppress debug output
logging.getLogger("pymodbus").setLevel(logging.ERROR)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

load_dotenv(Path(__file__).parent.parent / ".env")


async def read_modbus_registers(host: str, port: int, unit_id: int = 1) -> dict[int, int]:
    """Read all input registers from Modbus."""
    from pymodbus.client import AsyncModbusTcpClient

    client = AsyncModbusTcpClient(host=host, port=port, timeout=5.0)
    await client.connect()

    registers: dict[int, int] = {}

    # Read input registers 0-255
    for start in range(0, 256, 40):
        count = min(40, 256 - start)
        try:
            resp = await asyncio.wait_for(
                client.read_input_registers(address=start, count=count, device_id=unit_id),
                timeout=5.0,
            )
            if not resp.isError() and hasattr(resp, "registers"):
                for offset, value in enumerate(resp.registers):
                    registers[start + offset] = value
        except Exception:
            pass

    client.close()
    return registers


async def read_webapp_data(serial: str):
    """Read runtime data from Web API."""
    from pylxpweb import LuxpowerClient

    username = os.getenv("LUXPOWER_USERNAME")
    password = os.getenv("LUXPOWER_PASSWORD")
    base_url = os.getenv("LUXPOWER_BASE_URL", "https://monitor.eg4electronics.com")

    async with LuxpowerClient(
        username=username,
        password=password,
        base_url=base_url,
    ) as client:
        # Get runtime data
        runtime = await client.api.devices.get_inverter_runtime(serial)
        # Get energy data
        energy = await client.api.devices.get_inverter_energy(serial)
        # Get battery data
        battery = await client.api.devices.get_battery_info(serial)

        return runtime, energy, battery


def signed16(value: int) -> int:
    """Convert unsigned 16-bit to signed."""
    return value - 65536 if value > 32767 else value


def format_comparison(
    modbus_regs: dict[int, int],
    runtime,
    energy,
) -> None:
    """Format and print comparison between Modbus and Web API."""

    print("\n" + "=" * 100)
    print("MODBUS vs WEB API COMPARISON")
    print("=" * 100)

    # Build comparison table:
    # (field_name, webapp_raw, webapp_scaled, modbus_reg, modbus_raw, modbus_scaled)
    comparisons = []

    # -------------------------------------------------------------------------
    # PV Data
    # -------------------------------------------------------------------------
    comparisons.append(("--- PV DATA ---", "", "", "", "", ""))
    comparisons.append(
        (
            "vpv1 (PV1 Voltage)",
            f"{runtime.vpv1}",
            f"{runtime.vpv1 / 10:.1f}V",
            "1",
            f"{modbus_regs.get(1, 0)}",
            f"{modbus_regs.get(1, 0) / 10:.1f}V",
        )
    )
    comparisons.append(
        (
            "vpv2 (PV2 Voltage)",
            f"{runtime.vpv2}",
            f"{runtime.vpv2 / 10:.1f}V",
            "2",
            f"{modbus_regs.get(2, 0)}",
            f"{modbus_regs.get(2, 0) / 10:.1f}V",
        )
    )
    comparisons.append(
        (
            "ppv1 (PV1 Power)",
            f"{runtime.ppv1}",
            f"{runtime.ppv1}W",
            "?",
            "-",
            "-",
        )
    )
    comparisons.append(
        (
            "ppv2 (PV2 Power)",
            f"{runtime.ppv2}",
            f"{runtime.ppv2}W",
            "?",
            "-",
            "-",
        )
    )
    comparisons.append(
        (
            "ppv (Total PV)",
            f"{runtime.ppv}",
            f"{runtime.ppv}W",
            "?",
            "-",
            "-",
        )
    )

    # -------------------------------------------------------------------------
    # Battery Data
    # -------------------------------------------------------------------------
    comparisons.append(("--- BATTERY DATA ---", "", "", "", "", ""))
    comparisons.append(
        (
            "vBat (Battery V)",
            f"{runtime.vBat}",
            f"{runtime.vBat / 10:.1f}V",
            "4",
            f"{modbus_regs.get(4, 0)}",
            f"{modbus_regs.get(4, 0) / 10:.1f}V",
        )
    )
    comparisons.append(
        (
            "soc (SOC %)",
            f"{runtime.soc}",
            f"{runtime.soc}%",
            "5 (lo)",
            f"{modbus_regs.get(5, 0) & 0xFF}",
            f"{modbus_regs.get(5, 0) & 0xFF}%",
        )
    )
    comparisons.append(
        (
            "pCharge",
            f"{runtime.pCharge}",
            f"{runtime.pCharge}W",
            "?",
            "-",
            "-",
        )
    )
    comparisons.append(
        (
            "pDisCharge",
            f"{runtime.pDisCharge}",
            f"{runtime.pDisCharge}W",
            "11",
            f"{modbus_regs.get(11, 0)}",
            f"{modbus_regs.get(11, 0)}W",
        )
    )

    # -------------------------------------------------------------------------
    # Grid Data
    # -------------------------------------------------------------------------
    comparisons.append(("--- GRID DATA ---", "", "", "", "", ""))
    comparisons.append(
        (
            "vacr (Grid V R)",
            f"{runtime.vacr}",
            f"{runtime.vacr / 10:.1f}V",
            "12",
            f"{modbus_regs.get(12, 0)}",
            f"{modbus_regs.get(12, 0) / 10:.1f}V",
        )
    )
    comparisons.append(
        (
            "vacs (Grid V S)",
            f"{runtime.vacs}",
            f"{runtime.vacs / 10:.1f}V",
            "13",
            f"{modbus_regs.get(13, 0)}",
            f"{modbus_regs.get(13, 0) / 10:.1f}V",
        )
    )
    comparisons.append(
        (
            "fac (Grid Freq)",
            f"{runtime.fac}",
            f"{runtime.fac / 100:.2f}Hz",
            "15",
            f"{modbus_regs.get(15, 0)}",
            f"{modbus_regs.get(15, 0) / 100:.2f}Hz",
        )
    )
    comparisons.append(
        (
            "pToGrid",
            f"{runtime.pToGrid}",
            f"{runtime.pToGrid}W",
            "?",
            "-",
            "-",
        )
    )
    comparisons.append(
        (
            "pToUser",
            f"{runtime.pToUser}",
            f"{runtime.pToUser}W",
            "?",
            "-",
            "-",
        )
    )
    comparisons.append(
        (
            "prec (Grid Power)",
            f"{runtime.prec}",
            f"{runtime.prec}W",
            "?",
            "-",
            "-",
        )
    )

    # -------------------------------------------------------------------------
    # EPS Data
    # -------------------------------------------------------------------------
    comparisons.append(("--- EPS DATA ---", "", "", "", "", ""))
    comparisons.append(
        (
            "vepsr (EPS V R)",
            f"{runtime.vepsr}",
            f"{runtime.vepsr / 10:.1f}V",
            "20",
            f"{modbus_regs.get(20, 0)}",
            f"{modbus_regs.get(20, 0) / 10:.1f}V",
        )
    )
    comparisons.append(
        (
            "vepss (EPS V S)",
            f"{runtime.vepss}",
            f"{runtime.vepss / 10:.1f}V",
            "21",
            f"{modbus_regs.get(21, 0)}",
            f"{signed16(modbus_regs.get(21, 0)) / 10:.1f}V",
        )
    )
    comparisons.append(
        (
            "vepst (EPS V T)",
            f"{runtime.vepst}",
            f"{runtime.vepst / 10:.1f}V",
            "22",
            f"{modbus_regs.get(22, 0)}",
            f"{modbus_regs.get(22, 0) / 10:.1f}V",
        )
    )
    comparisons.append(
        (
            "feps (EPS Freq)",
            f"{runtime.feps}",
            f"{runtime.feps / 100:.2f}Hz",
            "23",
            f"{modbus_regs.get(23, 0)}",
            f"{modbus_regs.get(23, 0) / 100:.2f}Hz",
        )
    )
    comparisons.append(
        (
            "peps (EPS Power)",
            f"{runtime.peps}",
            f"{runtime.peps}W",
            "?",
            "-",
            "-",
        )
    )

    # -------------------------------------------------------------------------
    # Inverter Data
    # -------------------------------------------------------------------------
    comparisons.append(("--- INVERTER DATA ---", "", "", "", "", ""))
    comparisons.append(
        (
            "pinv (Inverter P)",
            f"{runtime.pinv}",
            f"{runtime.pinv}W",
            "16",
            f"{modbus_regs.get(16, 0)}",
            f"{modbus_regs.get(16, 0)}W",
        )
    )

    # -------------------------------------------------------------------------
    # Temperature Data
    # -------------------------------------------------------------------------
    comparisons.append(("--- TEMPERATURE DATA ---", "", "", "", "", ""))
    comparisons.append(
        (
            "tinner",
            f"{runtime.tinner}",
            f"{runtime.tinner}°C",
            "64",
            f"{modbus_regs.get(64, 0)}",
            f"{modbus_regs.get(64, 0)}°C",
        )
    )
    comparisons.append(
        (
            "tradiator1",
            f"{runtime.tradiator1}",
            f"{runtime.tradiator1}°C",
            "65",
            f"{modbus_regs.get(65, 0)}",
            f"{modbus_regs.get(65, 0)}°C",
        )
    )
    comparisons.append(
        (
            "tradiator2",
            f"{runtime.tradiator2}",
            f"{runtime.tradiator2}°C",
            "66",
            f"{modbus_regs.get(66, 0)}",
            f"{modbus_regs.get(66, 0)}°C",
        )
    )
    comparisons.append(
        (
            "tBat",
            f"{runtime.tBat}",
            f"{runtime.tBat}°C",
            "67",
            f"{modbus_regs.get(67, 0)}",
            f"{modbus_regs.get(67, 0)}°C",
        )
    )

    # -------------------------------------------------------------------------
    # Energy Data
    # -------------------------------------------------------------------------
    comparisons.append(("--- ENERGY DATA (today) ---", "", "", "", "", ""))
    comparisons.append(
        (
            "todayYielding",
            f"{energy.todayYielding}",
            f"{energy.todayYielding / 10:.1f}kWh",
            "28+29",
            f"{modbus_regs.get(28, 0)}+{modbus_regs.get(29, 0)}",
            f"{(modbus_regs.get(28, 0) + modbus_regs.get(29, 0)) / 10:.1f}kWh",
        )
    )
    comparisons.append(
        (
            "todayCharging",
            f"{energy.todayCharging}",
            f"{energy.todayCharging / 10:.1f}kWh",
            "33",
            f"{modbus_regs.get(33, 0)}",
            f"{modbus_regs.get(33, 0) / 10:.1f}kWh",
        )
    )
    comparisons.append(
        (
            "todayDischarging",
            f"{energy.todayDischarging}",
            f"{energy.todayDischarging / 10:.1f}kWh",
            "34",
            f"{modbus_regs.get(34, 0)}",
            f"{modbus_regs.get(34, 0) / 10:.1f}kWh",
        )
    )
    comparisons.append(
        (
            "todayExport",
            f"{energy.todayExport}",
            f"{energy.todayExport / 10:.1f}kWh",
            "36",
            f"{modbus_regs.get(36, 0)}",
            f"{modbus_regs.get(36, 0) / 10:.1f}kWh",
        )
    )
    comparisons.append(
        (
            "todayImport",
            f"{energy.todayImport}",
            f"{energy.todayImport / 10:.1f}kWh",
            "37",
            f"{modbus_regs.get(37, 0)}",
            f"{modbus_regs.get(37, 0) / 10:.1f}kWh",
        )
    )

    # Print comparison table
    print(
        f"\n{'Field':<25} {'WebAPI Raw':>12} {'WebAPI Scaled':>15} "
        f"{'Reg':>6} {'Modbus Raw':>12} {'Modbus Scaled':>15}"
    )
    print("-" * 100)
    for row in comparisons:
        if row[1] == "":  # Section header
            print(f"\n{row[0]}")
        else:
            print(f"{row[0]:<25} {row[1]:>12} {row[2]:>15} {row[3]:>6} {row[4]:>12} {row[5]:>15}")

    # -------------------------------------------------------------------------
    # Now scan unmapped registers to find correlations
    # -------------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("UNMAPPED REGISTER CORRELATION ANALYSIS")
    print("=" * 100)

    # Web API values to search for
    search_values = {
        "ppv1": runtime.ppv1,
        "ppv2": runtime.ppv2,
        "ppv": runtime.ppv,
        "pCharge": runtime.pCharge,
        "pToGrid": runtime.pToGrid,
        "pToUser": runtime.pToUser,
        "prec": runtime.prec,
        "peps": runtime.peps,
        "consumptionPower": runtime.consumptionPower,
        "consumptionPower114": runtime.consumptionPower114,
        "batPower": runtime.batPower,
        "maxChgCurr": runtime.maxChgCurr,
        "maxDischgCurr": runtime.maxDischgCurr,
    }

    # Known mapped registers
    mapped_regs = {
        0,
        1,
        2,
        3,
        4,
        5,
        11,
        12,
        13,
        15,
        16,
        18,
        19,
        20,
        21,
        22,
        23,
        28,
        29,
        31,
        32,
        33,
        34,
        36,
        37,
        38,
        39,
        40,
        42,
        46,
        48,
        50,
        52,
        56,
        58,
        64,
        65,
        66,
        67,
        69,
        70,
        77,
        81,
        82,
        83,
        84,
        96,
        97,
        101,
        102,
        103,
        104,
        106,
        108,
        113,
        124,
        125,
    }

    print("\nSearching for WebAPI values in unmapped Modbus registers...")
    print(f"\n{'WebAPI Field':<25} {'Value':>10} {'Potential Register Matches':<50}")
    print("-" * 100)

    for field, value in search_values.items():
        if value is None or value == 0:
            continue

        matches = []
        for reg, reg_val in modbus_regs.items():
            if reg in mapped_regs:
                continue
            if reg_val == 0:
                continue

            # Direct match
            if reg_val == value:
                matches.append(f"[{reg}]={reg_val} (exact)")
            # Signed match
            elif signed16(reg_val) == value:
                matches.append(f"[{reg}]={signed16(reg_val)} (signed)")
            # Scaled matches
            elif abs(reg_val - value * 10) < 5:
                matches.append(f"[{reg}]={reg_val} (×10)")
            elif abs(reg_val - value * 100) < 50:
                matches.append(f"[{reg}]={reg_val} (×100)")

        if matches:
            print(f"{field:<25} {value:>10} {', '.join(matches[:3]):<50}")
        else:
            print(f"{field:<25} {value:>10} {'(no match found)':<50}")

    # -------------------------------------------------------------------------
    # Show all unmapped registers with their values
    # -------------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("ALL UNMAPPED REGISTERS WITH VALUES")
    print("=" * 100)

    print(f"\n{'Reg':>5} {'Raw':>8} {'Signed':>8} {'÷10':>10} {'÷100':>10} {'Hex':>8}")
    print("-" * 60)

    for reg in sorted(modbus_regs.keys()):
        if reg in mapped_regs:
            continue
        val = modbus_regs[reg]
        if val == 0:
            continue
        signed = signed16(val)
        print(f"{reg:>5} {val:>8} {signed:>8} {val / 10:>10.1f} {val / 100:>10.2f} {val:>8X}")


async def main():
    """Main entry point."""
    host = os.getenv("MODBUS_IP", "172.16.40.98")
    port = int(os.getenv("MODBUS_PORT", "502"))
    serial = os.getenv("MODBUS_SERIAL", "52842P0581")

    print("FlexBOSS21 Modbus vs Web API Comparison")
    print(f"Target: {host}:{port} (Serial: {serial})")
    print("=" * 100)

    # Read from both sources
    print("\nReading from Modbus...")
    modbus_regs = await read_modbus_registers(host, port)
    print(f"  Read {len(modbus_regs)} registers")

    print("\nReading from Web API...")
    runtime, energy, battery = await read_webapp_data(serial)
    print("  Got runtime, energy, and battery data")

    # Compare
    format_comparison(modbus_regs, runtime, energy)


if __name__ == "__main__":
    asyncio.run(main())
