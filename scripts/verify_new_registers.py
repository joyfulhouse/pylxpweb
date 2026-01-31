#!/usr/bin/env python3
"""Verify the new split-phase register mappings."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

logging.getLogger("pymodbus").setLevel(logging.ERROR)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


async def main():
    """Verify new register mappings."""
    from pymodbus.client import AsyncModbusTcpClient

    from pylxpweb.transports.data import InverterRuntimeData
    from pylxpweb.transports.register_maps import PV_SERIES_RUNTIME_MAP

    host = os.getenv("MODBUS_IP", "172.16.40.98")
    port = int(os.getenv("MODBUS_PORT", "502"))

    print("Verifying new split-phase register mappings")
    print(f"Target: {host}:{port}")
    print("=" * 60)

    # Read all registers
    client = AsyncModbusTcpClient(host=host, port=port, timeout=5.0)
    await client.connect()

    registers: dict[int, int] = {}
    for start in range(0, 256, 40):
        count = min(40, 256 - start)
        try:
            resp = await asyncio.wait_for(
                client.read_input_registers(address=start, count=count, device_id=1),
                timeout=5.0,
            )
            if not resp.isError() and hasattr(resp, "registers"):
                for offset, value in enumerate(resp.registers):
                    registers[start + offset] = value
        except Exception:
            pass

    client.close()

    # Parse using the new mappings
    data = InverterRuntimeData.from_modbus_registers(registers, PV_SERIES_RUNTIME_MAP)

    print("\n--- NEW SPLIT-PHASE REGISTERS ---")
    print(f"Grid L1 Voltage (reg 127): {data.grid_l1_voltage} V")
    print(f"Grid L2 Voltage (reg 128): {data.grid_l2_voltage} V")
    print(f"EPS L1 Voltage (reg 140):  {data.eps_l1_voltage} V")
    print(f"EPS L2 Voltage (reg 141):  {data.eps_l2_voltage} V")
    print(f"Output Power (reg 170):    {data.output_power} W")

    print("\n--- EXISTING REGISTERS FOR COMPARISON ---")
    print(f"Grid Voltage R (reg 12):   {data.grid_voltage_r} V")
    print(f"Grid Voltage S (reg 13):   {data.grid_voltage_s} V")
    print(f"EPS Voltage R (reg 20):    {data.eps_voltage_r} V")
    print(f"EPS Voltage S (reg 21):    {data.eps_voltage_s} V")
    print(f"Discharge Power (reg 11):  {data.battery_discharge_power} W")

    print("\n--- VALIDATION ---")
    if data.grid_l1_voltage and data.grid_l2_voltage:
        l1_l2_sum = data.grid_l1_voltage + data.grid_l2_voltage
        print(f"L1 + L2 = {l1_l2_sum:.1f} V (should be ~240V)")
        if 235 <= l1_l2_sum <= 250:
            print("✅ Split-phase voltages look correct!")
        else:
            print("⚠️ Split-phase sum out of expected range")
    else:
        print("❌ Split-phase voltages not available")


if __name__ == "__main__":
    asyncio.run(main())
