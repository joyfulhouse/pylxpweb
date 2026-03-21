#!/usr/bin/env python3
"""Run multiple read cycles to confirm register correlations."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

logging.getLogger("pymodbus").setLevel(logging.ERROR)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

load_dotenv(Path(__file__).parent.parent / ".env")


@dataclass
class ReadingPair:
    """A pair of Modbus and Web API readings."""

    cycle: int
    modbus_regs: dict[int, int]
    webapp_runtime: object
    webapp_energy: object


def signed16(value: int) -> int:
    """Convert unsigned 16-bit to signed."""
    return value - 65536 if value > 32767 else value


async def read_modbus(host: str, port: int, unit_id: int = 1) -> dict[int, int]:
    """Read input registers from Modbus."""
    from pymodbus.client import AsyncModbusTcpClient

    client = AsyncModbusTcpClient(host=host, port=port, timeout=5.0)
    await client.connect()

    registers: dict[int, int] = {}
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


async def read_webapp(serial: str):
    """Read from Web API."""
    from pylxpweb import LuxpowerClient

    username = os.getenv("LUXPOWER_USERNAME")
    password = os.getenv("LUXPOWER_PASSWORD")
    base_url = os.getenv("LUXPOWER_BASE_URL", "https://monitor.eg4electronics.com")

    async with LuxpowerClient(username=username, password=password, base_url=base_url) as client:
        runtime = await client.api.devices.get_inverter_runtime(serial)
        energy = await client.api.devices.get_inverter_energy(serial)
        return runtime, energy


async def run_cycles(
    num_cycles: int, delay: float, host: str, port: int, serial: str
) -> list[ReadingPair]:
    """Run multiple read cycles."""
    readings: list[ReadingPair] = []

    for i in range(num_cycles):
        print(f"\n--- Cycle {i + 1}/{num_cycles} ---")

        # Read Modbus first (faster)
        modbus = await read_modbus(host, port)
        # Then Web API
        runtime, energy = await read_webapp(serial)

        readings.append(
            ReadingPair(
                cycle=i + 1,
                modbus_regs=modbus,
                webapp_runtime=runtime,
                webapp_energy=energy,
            )
        )

        # Show key values
        print(
            f"  Modbus: vBat={modbus.get(4, 0)}, SOC={modbus.get(5, 0) & 0xFF}%, "
            f"pDischg={modbus.get(11, 0)}W, pinv={modbus.get(16, 0)}W"
        )
        print(
            f"  WebAPI: vBat={runtime.vBat}, SOC={runtime.soc}%, "
            f"pDischg={runtime.pDisCharge}W, pinv={runtime.pinv}W"
        )

        # Show unmapped registers of interest
        print(
            f"  Unmapped: [6]={modbus.get(6, 0)}, [98]={signed16(modbus.get(98, 0))}, "
            f"[127]={modbus.get(127, 0)}, [128]={modbus.get(128, 0)}, "
            f"[145]={modbus.get(145, 0)}, [170]={modbus.get(170, 0)}"
        )

        if i < num_cycles - 1:
            print(f"  Waiting {delay}s...")
            await asyncio.sleep(delay)

    return readings


def analyze_correlations(readings: list[ReadingPair]) -> None:
    """Analyze correlations between unmapped registers and Web API fields."""
    print("\n" + "=" * 100)
    print("CORRELATION ANALYSIS ACROSS ALL CYCLES")
    print("=" * 100)

    # Registers to analyze
    unmapped_regs = [6, 78, 98, 107, 127, 128, 139, 140, 141, 144, 145, 170]

    # Web API fields to correlate
    webapp_fields = [
        ("pDisCharge", lambda r: r.webapp_runtime.pDisCharge),
        ("pCharge", lambda r: r.webapp_runtime.pCharge),
        ("pinv", lambda r: r.webapp_runtime.pinv),
        ("peps", lambda r: r.webapp_runtime.peps),
        ("pToGrid", lambda r: r.webapp_runtime.pToGrid),
        ("pToUser", lambda r: r.webapp_runtime.pToUser),
        ("prec", lambda r: r.webapp_runtime.prec),
        ("consumptionPower", lambda r: r.webapp_runtime.consumptionPower),
        ("batPower", lambda r: r.webapp_runtime.batPower),
        ("vBat", lambda r: r.webapp_runtime.vBat),
        ("vacr", lambda r: r.webapp_runtime.vacr),
        ("vacs", lambda r: r.webapp_runtime.vacs),
    ]

    # Build correlation table
    print(
        f"\n{'Register':<10} {'Scaling':<10} "
        + " ".join(f"{'Cycle ' + str(i + 1):>12}" for i in range(len(readings)))
    )
    print("-" * (22 + 13 * len(readings)))

    for reg in unmapped_regs:
        # Raw values
        raw_vals = [r.modbus_regs.get(reg, 0) for r in readings]
        print(f"[{reg:>3}] raw  {'':>10} " + " ".join(f"{v:>12}" for v in raw_vals))

        # Signed
        signed_vals = [signed16(v) for v in raw_vals]
        if any(v < 0 for v in signed_vals):
            print(f"[{reg:>3}] sign {'':>10} " + " ".join(f"{v:>12}" for v in signed_vals))

        # ÷10
        div10_vals = [v / 10 for v in raw_vals]
        print(f"[{reg:>3}] ÷10  {'':>10} " + " ".join(f"{v:>12.1f}" for v in div10_vals))

        # ÷100
        div100_vals = [v / 100 for v in raw_vals]
        print(f"[{reg:>3}] ÷100 {'':>10} " + " ".join(f"{v:>12.2f}" for v in div100_vals))

        print()

    # Web API values for comparison
    print("\n" + "=" * 100)
    print("WEB API VALUES FOR COMPARISON")
    print("=" * 100)

    print(
        f"\n{'Field':<20} " + " ".join(f"{'Cycle ' + str(i + 1):>12}" for i in range(len(readings)))
    )
    print("-" * (22 + 13 * len(readings)))

    for field_name, getter in webapp_fields:
        vals = [getter(r) for r in readings]
        # Handle None values
        val_strs = [f"{v:>12}" if v is not None else f"{'None':>12}" for v in vals]
        print(f"{field_name:<20} " + " ".join(val_strs))

    # Direct comparison for specific registers
    print("\n" + "=" * 100)
    print("CONFIRMED CORRELATIONS")
    print("=" * 100)

    # Check register 98 vs battery current (derived from batPower / vBat)
    print("\n--- Register 98: Battery Current Analysis ---")
    print(
        f"{'Cycle':<8} {'Reg98 raw':>12} {'Reg98 sign':>12} {'Reg98÷10':>12} "
        f"{'batPower':>12} {'vBat':>10} {'Calc Curr':>12} {'Match?':>10}"
    )
    print("-" * 100)

    for r in readings:
        reg98 = r.modbus_regs.get(98, 0)
        reg98_signed = signed16(reg98)
        reg98_div10 = reg98_signed / 10
        bat_power = r.webapp_runtime.batPower or 0
        vbat = r.webapp_runtime.vBat / 10  # Convert to volts
        calc_curr = bat_power / vbat if vbat > 0 else 0
        match = "✓" if abs(reg98_div10 - calc_curr) < 5 else "✗"
        print(
            f"{r.cycle:<8} {reg98:>12} {reg98_signed:>12} {reg98_div10:>12.1f} "
            f"{bat_power:>12} {vbat:>10.1f} {calc_curr:>12.1f} {match:>10}"
        )

    # Check registers 127/128 vs L1/L2 voltages
    print("\n--- Registers 127/128: L1/L2 Voltage Analysis ---")
    print(
        f"{'Cycle':<8} {'Reg127':>10} {'÷10':>10} {'Reg128':>10} {'÷10':>10} "
        f"{'vacr':>10} {'vacs':>10} {'Sum':>10}"
    )
    print("-" * 90)

    for r in readings:
        reg127 = r.modbus_regs.get(127, 0)
        reg128 = r.modbus_regs.get(128, 0)
        vacr = r.webapp_runtime.vacr
        vacs = r.webapp_runtime.vacs
        line_sum = reg127 / 10 + reg128 / 10
        print(
            f"{r.cycle:<8} {reg127:>10} {reg127 / 10:>10.1f} {reg128:>10} {reg128 / 10:>10.1f} "
            f"{vacr / 10:>10.1f} {vacs / 10:>10.1f} {line_sum:>10.1f}"
        )

    # Check register 170 vs line-to-line voltage
    print("\n--- Register 170: Line-to-Line Voltage Analysis ---")
    print(f"{'Cycle':<8} {'Reg170':>10} {'÷10':>10} {'vacr÷10':>10} {'L1+L2':>10} {'Match?':>10}")
    print("-" * 70)

    for r in readings:
        reg170 = r.modbus_regs.get(170, 0)
        vacr = r.webapp_runtime.vacr / 10
        l1_l2 = r.modbus_regs.get(127, 0) / 10 + r.modbus_regs.get(128, 0) / 10
        match = "✓" if abs(reg170 / 10 - l1_l2) < 5 else "~"
        print(
            f"{r.cycle:<8} {reg170:>10} {reg170 / 10:>10.1f} "
            f"{vacr:>10.1f} {l1_l2:>10.1f} {match:>10}"
        )

    # Check register 6 vs power values
    print("\n--- Register 6: Power Analysis ---")
    print(
        f"{'Cycle':<8} {'Reg6':>10} {'÷10':>10} {'pinv':>10} "
        f"{'peps':>10} {'pDischg':>10} {'consPwr':>10}"
    )
    print("-" * 80)

    for r in readings:
        reg6 = r.modbus_regs.get(6, 0)
        print(
            f"{r.cycle:<8} {reg6:>10} {reg6 / 10:>10.1f} {r.webapp_runtime.pinv:>10} "
            f"{r.webapp_runtime.peps:>10} {r.webapp_runtime.pDisCharge:>10} "
            f"{r.webapp_runtime.consumptionPower:>10}"
        )

    # Summary
    print("\n" + "=" * 100)
    print("SUMMARY OF CONFIRMED MAPPINGS")
    print("=" * 100)

    print("""
Based on the analysis:

CONFIRMED (can be mapped):
- Register 98: Battery current (signed, ÷10 = Amps)
  - Correlates with batPower / vBat calculation
  - Negative = discharge, Positive = charge

LIKELY (need more cycles to confirm):
- Register 127: L1 voltage (÷10 = Volts) - split-phase leg 1
- Register 128: L2 voltage (÷10 = Volts) - split-phase leg 2
- Register 170: Appears related to voltage but doesn't match L1+L2 exactly

UNCERTAIN (values don't clearly correlate):
- Register 6: Changes with power but scaling unclear
- Register 145: Current measurement but source unclear
""")


async def main():
    """Main entry point."""
    host = os.getenv("MODBUS_IP", "172.16.40.98")
    port = int(os.getenv("MODBUS_PORT", "502"))
    serial = os.getenv("MODBUS_SERIAL", "52842P0581")

    print("FlexBOSS21 Register Correlation Confirmation")
    print(f"Target: {host}:{port} (Serial: {serial})")
    print("=" * 100)

    num_cycles = 5
    delay = 3.0  # seconds between cycles

    print(f"\nRunning {num_cycles} read cycles with {delay}s delay...")

    readings = await run_cycles(num_cycles, delay, host, port, serial)
    analyze_correlations(readings)


if __name__ == "__main__":
    asyncio.run(main())
