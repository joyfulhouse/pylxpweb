#!/usr/bin/env python3
"""Read specific Modbus registers from an inverter for testing."""

import asyncio
import sys

from pymodbus.client import AsyncModbusTcpClient


async def read_registers(host: str, port: int = 8000, unit_id: int = 1):
    """Read registers from inverter."""
    client = AsyncModbusTcpClient(host, port=port)
    await client.connect()

    if not client.connected:
        print(f"Failed to connect to {host}:{port}")
        return

    print(f"Connected to {host}:{port}")
    print("=" * 60)

    # Registers to test
    test_ranges = [
        # Register 18 - Inverter RMS current
        (18, 1, "Reg 18: IinvRMS (Inverter RMS current, scale 0.01A)"),
        # Compare with known load energy registers
        (32, 1, "Reg 32: Erec_day (load_energy_today, scale 0.1 kWh)"),
        (48, 2, "Reg 48-49: Erec_all (load_energy_total, 32-bit LE, scale 0.1 kWh)"),
        # US Model Split-Phase Registers (193-204)
        (193, 1, "Reg 193: GridVoltL1N (Grid Voltage L1N, scale 0.1V) - US model"),
        (194, 1, "Reg 194: GridVoltL2N (Grid Voltage L2N, scale 0.1V) - US model"),
        (195, 1, "Reg 195: GenVoltL1N (Gen Voltage L1N, scale 0.1V) - US model"),
        (196, 1, "Reg 196: GenVoltL2N (Gen Voltage L2N, scale 0.1V) - US model"),
        (197, 1, "Reg 197: PinvL1N (Inverting power L1N, W) - US model"),
        (198, 1, "Reg 198: PinvL2N (Inverting power L2N, W) - US model"),
        (199, 1, "Reg 199: PrecL1N (Rectifying power L1N, W) - US model"),
        (200, 1, "Reg 200: PrecL2N (Rectifying power L2N, W) - US model"),
        (201, 1, "Reg 201: Ptogrid_L1N (Grid export power L1N, W) - US model"),
        (202, 1, "Reg 202: Ptogrid_L2N (Grid export power L2N, W) - US model"),
        (203, 1, "Reg 203: Ptouser_L1N (Grid import power L1N, W) - US model"),
        (204, 1, "Reg 204: Ptouser_L2N (Grid import power L2N, W) - US model"),
        # Registers 171-173 - Potential load energy
        (171, 1, "Reg 171: Unknown (potential load energy today?)"),
        (172, 2, "Reg 172-173: Unknown (potential load energy total, 32-bit LE?)"),
        # Registers 190-191 - S/T phase current (3-phase only)
        (190, 2, "Reg 190-191: IinvRMS S/T (3-phase current, scale 0.01A)"),
    ]

    for start_reg, count, description in test_ranges:
        try:
            result = await client.read_input_registers(start_reg, count=count, device_id=unit_id)
            if result.isError():
                print(f"\n{description}")
                print(f"  ERROR: {result}")
            else:
                print(f"\n{description}")
                for i, val in enumerate(result.registers):
                    reg_addr = start_reg + i
                    # Show raw value and potential scaled values
                    print(f"  Reg {reg_addr}: {val} (raw)")
                    if count == 1:
                        print(f"    - As 0.01 scale: {val / 100:.2f}")
                        print(f"    - As 0.1 scale:  {val / 10:.1f}")

                # For 32-bit pairs, also show combined value
                if count == 2 and len(result.registers) == 2:
                    low, high = result.registers
                    combined = (high << 16) | low
                    print(f"  32-bit LE value: {combined}")
                    print(f"    - As 0.1 scale: {combined / 10:.1f} kWh")

        except Exception as e:
            print(f"\n{description}")
            print(f"  EXCEPTION: {e}")

    client.close()
    print("\n" + "=" * 60)
    print("Done")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python read_registers.py <host> [port] [unit_id]")
        print("Example: python read_registers.py 192.168.1.100 8000 1")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    unit_id = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    asyncio.run(read_registers(host, port, unit_id))
