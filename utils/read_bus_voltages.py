#!/usr/bin/env python3
"""Quick diagnostic to validate bus voltage readings from FlexBOSS21."""

import asyncio
import sys

from pymodbus.client import AsyncModbusTcpClient


async def read_bus_voltages(host: str, port: int = 502, unit_id: int = 1) -> None:
    """Read bus voltages directly from Modbus registers."""
    client = AsyncModbusTcpClient(host, port=port)

    try:
        await client.connect()
        if not client.connected:
            print(f"Failed to connect to {host}:{port}")
            return

        print(f"Connected to {host}:{port}")

        # Read registers 38-39 (bus voltages) - need to read from input registers (function 04)
        # Most Luxpower inverters use unit ID 1 and input registers
        # Note: pymodbus 3.10+ uses 'device_id' (3.9.x and earlier used 'slave')
        result = await client.read_input_registers(address=38, count=2, device_id=unit_id)

        if result.isError():
            print(f"Error reading registers: {result}")
            return

        raw_bus1 = result.registers[0]
        raw_bus2 = result.registers[1]

        # Apply SCALE_10 (÷10) scaling
        bus_voltage_1 = raw_bus1 / 10.0
        bus_voltage_2 = raw_bus2 / 10.0

        print("\nBus Voltage Registers (38-39):")
        print(f"  Register 38 (raw): {raw_bus1}")
        print(f"  Register 39 (raw): {raw_bus2}")
        print("\nAfter SCALE_10 (÷10):")
        print(f"  Bus Voltage 1: {bus_voltage_1:.1f} V")
        print(f"  Bus Voltage 2: {bus_voltage_2:.1f} V")
        print("\nExpected values: 330.7 V and 178.3 V")
        print(f"Match: Bus1={bus_voltage_1:.1f}≈330.7? Bus2={bus_voltage_2:.1f}≈178.3?")

    finally:
        client.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python read_bus_voltages.py <inverter_ip> [port] [unit_id]")
        print("Example: python read_bus_voltages.py 192.168.1.100 502 1")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 502
    unit_id = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    print("NOTE: Stop Home Assistant first to avoid concurrent Modbus read issues!")
    print("-" * 60)

    asyncio.run(read_bus_voltages(host, port, unit_id))
