#!/usr/bin/env python3
"""Diagnostic script to find firmware version registers.

This script reads holding registers and looks for values that might
represent the firmware code prefix (like "fAAB" or "FAAB").

Usage:
    uv run python utils/read_firmware_registers.py <host> <serial>

Example:
    uv run python utils/read_firmware_registers.py 192.168.1.100 BA12345678
"""

import asyncio
import sys


async def main(host: str, serial: str) -> None:
    """Read registers and look for firmware version data."""
    from pylxpweb.transports import create_modbus_transport

    print(f"Connecting to {host} for inverter {serial}...")

    transport = create_modbus_transport(
        host=host,
        serial=serial,
        port=502,
    )

    try:
        await transport.connect()
        print("Connected!\n")

        # Read holding registers 0-50 (likely contains config/version info)
        print("=" * 60)
        print("HOLDING REGISTERS 0-50")
        print("=" * 60)

        regs = await transport.read_parameters(0, 50)

        for addr in sorted(regs.keys()):
            val = regs[addr]
            # Show decimal, hex, and possible ASCII interpretation
            ascii_chars = ""
            try:
                # Try to interpret as 2 ASCII characters
                high_byte = (val >> 8) & 0xFF
                low_byte = val & 0xFF
                if 32 <= high_byte <= 126 and 32 <= low_byte <= 126:
                    ascii_chars = f" '{chr(high_byte)}{chr(low_byte)}'"
                elif 32 <= high_byte <= 126:
                    ascii_chars = f" '{chr(high_byte)}.'"
                elif 32 <= low_byte <= 126:
                    ascii_chars = f" '.{chr(low_byte)}'"
            except:
                pass

            print(f"  Reg {addr:3d}: {val:5d} (0x{val:04X}){ascii_chars}")

        # Focus on registers 9-20 which might have version/device info
        print("\n" + "=" * 60)
        print("ANALYSIS OF KEY REGISTERS")
        print("=" * 60)

        # Check register 9 and 10 (suspected firmware version)
        if 9 in regs and 10 in regs:
            v1 = regs[9]
            v2 = regs[10]
            print(f"\nRegisters 9-10 (suspected v1/v2):")
            print(f"  Reg 9:  {v1} (0x{v1:04X}) → as hex version: {v1:02X}")
            print(f"  Reg 10: {v2} (0x{v2:04X}) → as hex version: {v2:02X}")
            print(f"  Combined: {v1:02X}{v2:02X}")

        # Check register 19 (device type code)
        if 19 in regs:
            dt = regs[19]
            print(f"\nRegister 19 (HOLD_DEVICE_TYPE_CODE):")
            print(f"  Value: {dt} (0x{dt:04X})")

        # Look for values that might be the prefix
        print("\n" + "=" * 60)
        print("SEARCHING FOR FIRMWARE PREFIX PATTERNS")
        print("=" * 60)

        target_values = {
            64171: "0xFAAB (FAAB as hex)",
            26177: "fA in BE (0x6641)",
            16706: "AB in BE (0x4142)",
            16742: "Af in LE (0x4166)",
            16961: "BA in LE (0x4241)",
            17985: "FA in BE (0x4641)",
            16710: "AF in LE (0x4146)",
        }

        found_any = False
        for addr, val in regs.items():
            if val in target_values:
                print(f"  Found at Reg {addr}: {val} = {target_values[val]}")
                found_any = True

        if not found_any:
            print("  No known prefix patterns found in registers 0-50")

        # Also read input registers for comparison
        print("\n" + "=" * 60)
        print("INPUT REGISTERS 0-20 (for comparison)")
        print("=" * 60)

        # Read input registers directly using the transport's internal method
        input_regs = await transport._read_input_registers(0, 20)
        for i, val in enumerate(input_regs):
            ascii_chars = ""
            try:
                high_byte = (val >> 8) & 0xFF
                low_byte = val & 0xFF
                if 32 <= high_byte <= 126 and 32 <= low_byte <= 126:
                    ascii_chars = f" '{chr(high_byte)}{chr(low_byte)}'"
            except:
                pass
            print(f"  Input Reg {i:3d}: {val:5d} (0x{val:04X}){ascii_chars}")

    finally:
        await transport.disconnect()
        print("\nDisconnected.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    host = sys.argv[1]
    serial = sys.argv[2]

    asyncio.run(main(host, serial))
