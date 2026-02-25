#!/usr/bin/env python3
"""Compare battery data between Modbus registers and Web API.

This script connects to both the Modbus TCP interface and the Web API
to compare what battery data is available from each source.

Usage:
    uv run python scripts/compare_battery_data.py
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

# Load .env file
load_dotenv()


async def read_modbus_battery_data() -> dict:
    """Read battery data via Modbus TCP."""
    from pymodbus.client import AsyncModbusTcpClient

    host = os.environ.get("MODBUS_IP", "172.16.40.98")
    port = int(os.environ.get("MODBUS_PORT", "502"))

    print(f"\n[MODBUS] Connecting to {host}:{port}...")

    client = AsyncModbusTcpClient(host=host, port=port, timeout=10.0)
    connected = await client.connect()

    if not connected:
        print("[MODBUS] Failed to connect!")
        return {}

    data = {}

    # Read core battery registers (0-31)
    try:
        result = await client.read_input_registers(address=0, count=32, device_id=1)
        if not result.isError():
            regs = list(result.registers)
            data["voltage"] = regs[4] / 10.0  # Reg 4, scale /10
            soc_soh = regs[5]
            data["soc"] = soc_soh & 0xFF
            data["soh"] = (soc_soh >> 8) & 0xFF
            data["charge_power"] = regs[10]  # Reg 10
            data["discharge_power"] = regs[11]  # Reg 11
            print("[MODBUS] Core registers 0-31 read OK")
    except Exception as e:
        print(f"[MODBUS] Error reading core registers: {e}")

    await asyncio.sleep(0.5)

    # Read BMS registers (80-112)
    try:
        result = await client.read_input_registers(address=80, count=33, device_id=1)
        if not result.isError():
            regs = {80 + i: v for i, v in enumerate(result.registers)}
            data["charge_current_limit"] = regs.get(81, 0) / 10.0  # scale /10
            data["discharge_current_limit"] = regs.get(82, 0) / 10.0
            data["charge_voltage_ref"] = regs.get(83, 0) / 10.0  # scale /10
            data["discharge_cutoff"] = regs.get(84, 0) / 10.0
            data["battery_count"] = regs.get(96, 0)
            data["capacity_ah"] = regs.get(97, 0)
            data["max_cell_voltage_mv"] = regs.get(101, 0)
            data["min_cell_voltage_mv"] = regs.get(102, 0)
            data["max_cell_temp_c"] = regs.get(103, 0) / 10.0 if regs.get(103, 0) < 32768 else (regs.get(103, 0) - 65536) / 10.0
            data["min_cell_temp_c"] = regs.get(104, 0) / 10.0 if regs.get(104, 0) < 32768 else (regs.get(104, 0) - 65536) / 10.0
            data["cycle_count"] = regs.get(106, 0)
            print("[MODBUS] BMS registers 80-112 read OK")
    except Exception as e:
        print(f"[MODBUS] Error reading BMS registers: {e}")

    await asyncio.sleep(0.5)

    # Try extended ranges (200-300) where battery array data might be
    for start in [200, 300, 400, 500, 1000, 2000]:
        try:
            result = await client.read_input_registers(address=start, count=32, device_id=1)
            if not result.isError():
                non_zero = [(start + i, v) for i, v in enumerate(result.registers) if v != 0]
                if non_zero:
                    print(f"[MODBUS] Extended INPUT {start}-{start+31}: {len(non_zero)} non-zero values")
                    data[f"extended_input_{start}"] = non_zero
        except Exception:
            pass
        await asyncio.sleep(0.3)

    # Try different unit IDs (batteries might be separate slaves)
    for unit_id in [2, 3, 4]:
        try:
            result = await client.read_input_registers(address=0, count=16, device_id=unit_id)
            if not result.isError():
                non_zero = [v for v in result.registers if v != 0]
                if non_zero:
                    print(f"[MODBUS] Unit {unit_id}: Found {len(non_zero)} non-zero values!")
                    data[f"unit_{unit_id}"] = list(result.registers)
        except Exception:
            pass
        await asyncio.sleep(0.3)

    client.close()
    return data


async def read_web_api_battery_data() -> dict:
    """Read battery data via Web API."""
    from pylxpweb import LuxpowerClient

    username = os.environ.get("LUXPOWER_USERNAME")
    password = os.environ.get("LUXPOWER_PASSWORD")
    base_url = os.environ.get("LUXPOWER_BASE_URL", "https://monitor.eg4electronics.com")

    if not username or not password:
        print("[WEB API] Missing LUXPOWER_USERNAME or LUXPOWER_PASSWORD")
        return {}

    print(f"\n[WEB API] Connecting to {base_url}...")

    async with LuxpowerClient(username, password, base_url) as client:
        # Get stations
        stations = await client.api.plants.get_stations()
        if not stations:
            print("[WEB API] No stations found!")
            return {}

        # Get device list
        devices = await client.api.devices.get_devices_list()

        # Find the FlexBOSS21 by serial
        modbus_serial = os.environ.get("MODBUS_SERIAL", "52842P0581")
        target_device = None
        for device in devices:
            if device.serialNum == modbus_serial:
                target_device = device
                break

        if not target_device:
            print(f"[WEB API] Device {modbus_serial} not found in device list")
            # Try to get any inverter's battery info
            for device in devices:
                if device.deviceType == 6:  # Inverter
                    target_device = device
                    print(f"[WEB API] Using device: {device.serialNum}")
                    break

        if not target_device:
            print("[WEB API] No inverter found!")
            return {}

        # Get battery info
        battery_info = await client.api.devices.get_battery_info(target_device.serialNum)

        data = {
            "serial": target_device.serialNum,
            "soc": battery_info.soc,
            "voltage": battery_info.vBat / 10.0 if battery_info.vBat else 0,
            "charge_power": battery_info.pCharge,
            "discharge_power": battery_info.pDisCharge,
            "max_capacity": battery_info.maxBatteryCharge,
            "current_capacity": battery_info.currentBatteryCharge,
            "battery_count": battery_info.totalNumber,
            "batteries": [],
        }

        if battery_info.batteryArray:
            for batt in battery_info.batteryArray:
                battery_data = {
                    "index": batt.batIndex,
                    "serial": batt.batterySn,
                    "voltage": batt.totalVoltage / 100.0,  # scale /100
                    "current": batt.current / 100.0,  # scale /100
                    "soc": batt.soc,
                    "soh": batt.soh,
                    "max_cell_voltage_mv": batt.batMaxCellVoltage,
                    "min_cell_voltage_mv": batt.batMinCellVoltage,
                    "max_cell_temp_c": batt.batMaxCellTemp / 10.0 if batt.batMaxCellTemp else 0,
                    "min_cell_temp_c": batt.batMinCellTemp / 10.0 if batt.batMinCellTemp else 0,
                    "cycle_count": batt.cycleCnt,
                    "remain_capacity_ah": batt.currentRemainCapacity,
                    "full_capacity_ah": batt.currentFullCapacity,
                    "charge_current_limit": batt.batChargeMaxCur / 10.0 if batt.batChargeMaxCur else 0,
                    "charge_voltage_ref": batt.batChargeVoltRef / 10.0 if batt.batChargeVoltRef else 0,
                }
                data["batteries"].append(battery_data)

        print(f"[WEB API] Found {len(data['batteries'])} individual batteries")
        return data


def compare_data(modbus_data: dict, web_data: dict) -> None:
    """Compare and display the data from both sources."""
    print("\n" + "=" * 70)
    print("COMPARISON: Modbus vs Web API")
    print("=" * 70)

    print("\n--- Aggregate Battery Data ---")
    print(f"{'Field':<30} {'Modbus':<20} {'Web API':<20}")
    print("-" * 70)

    fields = [
        ("soc", "%", 0),
        ("voltage", "V", 1),
        ("charge_power", "W", 0),
        ("discharge_power", "W", 0),
        ("battery_count", "", 0),
        ("max_cell_voltage_mv", "mV", 0),
        ("min_cell_voltage_mv", "mV", 0),
        ("max_cell_temp_c", "°C", 1),
        ("min_cell_temp_c", "°C", 1),
        ("cycle_count", "", 0),
    ]

    for field, unit, decimals in fields:
        modbus_val = modbus_data.get(field, "N/A")
        web_val = web_data.get(field, "N/A")
        if isinstance(modbus_val, float):
            modbus_str = f"{modbus_val:.{decimals}f}{unit}"
        elif modbus_val != "N/A":
            modbus_str = f"{modbus_val}{unit}"
        else:
            modbus_str = "N/A"
        if isinstance(web_val, float):
            web_str = f"{web_val:.{decimals}f}{unit}"
        elif web_val != "N/A":
            web_str = f"{web_val}{unit}"
        else:
            web_str = "N/A"
        print(f"{field:<30} {modbus_str:<20} {web_str:<20}")

    # Individual batteries (only available via Web API)
    if web_data.get("batteries"):
        print("\n--- Individual Battery Data (Web API only) ---")
        for batt in web_data["batteries"]:
            print(f"\n  Battery {batt['index'] + 1} ({batt['serial']}):")
            print(f"    Voltage: {batt['voltage']:.2f}V")
            print(f"    Current: {batt['current']:.2f}A")
            print(f"    SOC: {batt['soc']}%")
            print(f"    SOH: {batt['soh']}%")
            print(f"    Cell V range: {batt['min_cell_voltage_mv']}-{batt['max_cell_voltage_mv']} mV")
            print(f"    Cell T range: {batt['min_cell_temp_c']:.1f}-{batt['max_cell_temp_c']:.1f}°C")
            print(f"    Cycle count: {batt['cycle_count']}")
            print(f"    Capacity: {batt['remain_capacity_ah']}/{batt['full_capacity_ah']} Ah")

    print("\n" + "=" * 70)
    print("CONCLUSION:")
    print("=" * 70)
    if web_data.get("batteries"):
        print(f"""
The Web API provides individual battery data for {len(web_data['batteries'])} batteries,
while Modbus only provides aggregate BMS data (max/min across all batteries).

This suggests the individual battery data is:
1. Collected by the inverter via its internal BMS communication (likely CAN bus)
2. Aggregated and sent to the cloud via the WiFi dongle
3. NOT exposed via standard Modbus registers

Possible workarounds:
- Use Web API for individual battery monitoring
- Investigate if there's a proprietary Modbus extension (unlikely)
- Check if the dongle has a hidden API on its local network
- Research the BMS communication protocol (usually CAN or RS-485 to inverter)
""")
    else:
        print("Could not compare - missing data from one or both sources")


async def main() -> None:
    """Main function."""
    print("Battery Data Comparison: Modbus vs Web API")
    print("=" * 70)

    # Read from both sources
    modbus_data = await read_modbus_battery_data()
    web_data = await read_web_api_battery_data()

    # Compare
    compare_data(modbus_data, web_data)


if __name__ == "__main__":
    asyncio.run(main())
