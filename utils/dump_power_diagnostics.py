#!/usr/bin/env python3
"""Power Flow Diagnostic Dump Tool for pylxpweb.

Collects raw unprocessed register readings AND HTTP API runtime data
for troubleshooting power sensor discrepancies (rectifier power, consumption
power, total load power, etc.).

Outputs a sanitized JSON file suitable for sharing via GitHub private gist.

Setup (one-time):
    pip install pylxpweb

Usage:
    # Interactive mode (prompts for everything)
    python dump_power_diagnostics.py

    # With explicit credentials (EG4)
    python dump_power_diagnostics.py --username USER --password PASS

    # With LuxPower portal
    python dump_power_diagnostics.py --username USER --password PASS \\
        --base-url https://us.luxpowertek.com

    # Single dongle connection
    python dump_power_diagnostics.py --username USER --password PASS \\
        --dongle 10.0.0.1:BJ45000202:4512670118

    # Multiple dongle connections (one per inverter)
    python dump_power_diagnostics.py --username USER --password PASS \\
        --dongle 10.0.0.1:DONGLE_SN1:INV_SN1 \\
        --dongle 10.0.0.2:DONGLE_SN2:INV_SN2

    # Modbus TCP connection
    python dump_power_diagnostics.py --username USER --password PASS \\
        --modbus 172.16.40.98:52842P0581

    # Multiple Modbus + dongle connections
    python dump_power_diagnostics.py --username USER --password PASS \\
        --dongle 10.0.0.1:DONGLE_SN:INV_SN \\
        --modbus 172.16.40.98:INV_SN2

    # Output to specific file
    python dump_power_diagnostics.py -o my_diagnostics.json

Sharing results:
    The output is automatically sanitized (serial numbers masked,
    addresses and personal info removed). You can safely paste the
    JSON contents directly into a GitHub issue comment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add src to path for development imports (when running from pylxpweb repo)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Optional .env support (not required for end users)
try:
    from dotenv import load_dotenv

    _env_path = Path(__file__).parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass  # dotenv not installed - credentials must come from args or prompts


def _prompt_if_missing(value: str | None, prompt_text: str, secret: bool = False) -> str | None:
    """Prompt the user interactively if a value is not provided."""
    if value:
        return value
    try:
        if secret:
            import getpass
            return getpass.getpass(prompt_text) or None
        return input(prompt_text) or None
    except (EOFError, KeyboardInterrupt):
        return None


# ──────────────────────────────────────────────────────────────────────
# Sanitization
# ──────────────────────────────────────────────────────────────────────

_SENSITIVE_KEYS = re.compile(
    r"serial|sn$|password|token|address|street|location|"
    r"latitude|longitude|lat$|lng$|lon$|plant.?name|station.?name|^name$|"
    r"plant.?id|station.?id|^id$|username|email",
    re.IGNORECASE,
)


def _mask_serial(value: str) -> str:
    """Mask serial number keeping first 2 and last 2 chars."""
    if len(value) > 4:
        return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"
    return "*" * len(value)


def sanitize(key: str, value: Any) -> Any:
    """Sanitize sensitive fields recursively."""
    if isinstance(value, dict):
        return {k: sanitize(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(key, item) for item in value]

    if not _SENSITIVE_KEYS.search(key):
        return value

    key_lower = key.lower()
    if any(s in key_lower for s in ("serial", "sn")):
        return _mask_serial(str(value)) if isinstance(value, str) and value else value
    if any(s in key_lower for s in ("password", "token", "username", "email")):
        return "***REDACTED***"
    if any(s in key_lower for s in ("latitude", "longitude", "lat", "lng", "lon")):
        return 0.0 if isinstance(value, (int, float)) else value
    if any(s in key_lower for s in ("address", "street", "location")):
        return "REDACTED" if isinstance(value, str) else value
    if key_lower in ("id", "plant_id", "station_id"):
        return "XXXXX"
    if key_lower in ("name", "plant_name", "station_name"):
        return "REDACTED_STATION" if isinstance(value, str) else value

    return value


# ──────────────────────────────────────────────────────────────────────
# Register labels for human-readable output
# ──────────────────────────────────────────────────────────────────────

REGISTER_LABELS: dict[int, str] = {
    0: "device_status",
    1: "pv1_voltage (scale /10)",
    2: "pv2_voltage (scale /10)",
    3: "pv3_voltage (scale /10)",
    4: "battery_voltage (scale /10)",
    5: "soc_soh_packed (low=SOC, high=SOH)",
    6: "(reserved)",
    7: "pv1_power (W)",
    8: "pv2_power (W)",
    9: "pv3_power (W)",
    10: "battery_charge_power (W)",
    11: "battery_discharge_power (W)",
    12: "grid_voltage_r (scale /10)",
    13: "grid_voltage_s (scale /10)",
    14: "grid_voltage_t (scale /10)",
    15: "grid_frequency (scale /100)",
    16: "inverter_power / Pinv (W)",
    17: "rectifier_power / Prec (W) - AC→DC from grid",
    18: "inverter_rms_current (scale /100)",
    19: "power_factor (scale /1000)",
    20: "eps_voltage_r (scale /10)",
    21: "eps_voltage_s (scale /10)",
    22: "eps_voltage_t (scale /10)",
    23: "eps_frequency (scale /100)",
    24: "eps_power / Peps (W)",
    25: "eps_status / Seps",
    26: "power_to_grid / Ptogrid (W)",
    27: "load_power / Ptouser (W)",
    38: "bus_voltage_1 (scale /10)",
    39: "bus_voltage_2 (scale /10)",
    60: "fault_code_low (32-bit, regs 60-61)",
    61: "fault_code_high",
    62: "warning_code_low (32-bit, regs 62-63)",
    63: "warning_code_high",
    64: "internal_temperature (°C, signed)",
    65: "radiator_temperature_1 (°C)",
    66: "radiator_temperature_2 (°C)",
    67: "battery_temperature (°C)",
    75: "battery_current (scale /100, signed)",
    96: "battery_parallel_num",
    97: "battery_capacity_ah",
    99: "bms_fault_code",
    100: "bms_warning_code",
    101: "bms_max_cell_voltage (mV)",
    102: "bms_min_cell_voltage (mV)",
    103: "bms_max_cell_temperature (scale /10, signed)",
    104: "bms_min_cell_temperature (scale /10, signed)",
    106: "bms_cycle_count",
    113: "parallel_config",
    121: "generator_voltage (scale /10)",
    122: "generator_frequency (scale /100)",
    123: "generator_power (W)",
    127: "grid_l1_voltage (scale /10)",
    128: "grid_l2_voltage (scale /10)",
    140: "eps_l1_voltage (scale /10)",
    141: "eps_l2_voltage (scale /10)",
    170: "output_power (W, signed)",
    171: "(reserved/output_power_2)",
}


# ──────────────────────────────────────────────────────────────────────
# Data collection
# ──────────────────────────────────────────────────────────────────────


async def collect_http_data(
    username: str, password: str, base_url: str
) -> dict[str, Any]:
    """Collect runtime data from HTTP API for all inverters."""
    from pylxpweb import LuxpowerClient
    from pylxpweb.devices import Station

    result: dict[str, Any] = {"source": "http_api", "base_url": base_url, "inverters": []}

    async with LuxpowerClient(
        username=username, password=password, base_url=base_url
    ) as client:
        stations = await Station.load_all(client)
        if not stations:
            result["error"] = "No stations found"
            return result

        for station in stations:
            for inv in station.all_inverters:
                await inv.refresh()
                runtime = inv._runtime
                if runtime is None:
                    result["inverters"].append({
                        "serial": inv.serial_number,
                        "model": inv.model,
                        "error": "No runtime data",
                    })
                    continue

                # Dump ALL runtime fields as raw dict
                raw_fields = runtime.model_dump()

                # Highlight key power fields for easy reading
                power_summary = {
                    "ppv_total": runtime.ppv,
                    "ppv1": runtime.ppv1,
                    "ppv2": runtime.ppv2,
                    "ppv3": getattr(runtime, "ppv3", 0),
                    "pinv": runtime.pinv,
                    "prec": runtime.prec,
                    "pToGrid": runtime.pToGrid,
                    "pToUser": runtime.pToUser,
                    "peps": runtime.peps,
                    "pCharge": runtime.pCharge,
                    "pDisCharge": runtime.pDisCharge,
                    "consumptionPower": runtime.consumptionPower,
                    "consumptionPower114": getattr(runtime, "consumptionPower114", None),
                    "soc": runtime.soc,
                }

                # Energy balance
                sources = runtime.ppv + runtime.pDisCharge + runtime.prec
                sinks = runtime.pCharge + runtime.pToGrid + runtime.pToUser + runtime.peps
                balance = {
                    "sources_total": sources,
                    "sources_detail": f"ppv({runtime.ppv}) + pDisCharge({runtime.pDisCharge}) + prec({runtime.prec})",
                    "sinks_total": sinks,
                    "sinks_detail": f"pCharge({runtime.pCharge}) + pToGrid({runtime.pToGrid}) + pToUser({runtime.pToUser}) + peps({runtime.peps})",
                    "imbalance": sources - sinks,
                    "consumption_equals_pToUser_plus_peps": runtime.consumptionPower == (runtime.pToUser + runtime.peps),
                }

                result["inverters"].append({
                    "serial": inv.serial_number,
                    "model": inv.model,
                    "power_summary": power_summary,
                    "energy_balance": balance,
                    "raw_api_response": raw_fields,
                })

    return result


async def collect_raw_registers(
    transport_type: str,
    host: str,
    port: int,
    dongle_serial: str | None = None,
    inverter_serial: str | None = None,
    serial: str | None = None,
) -> dict[str, Any]:
    """Read raw unprocessed registers from a local transport.

    Returns both the raw register values and annotated versions with labels.
    """
    result: dict[str, Any] = {
        "source": transport_type,
        "host": host,
        "port": port,
    }

    try:
        if transport_type == "dongle":
            from pylxpweb.transports.dongle import INPUT_REGISTER_GROUPS, DongleTransport

            transport = DongleTransport(
                host=host,
                port=port,
                dongle_serial=dongle_serial or "",
                inverter_serial=inverter_serial or "",
            )
            result["dongle_serial"] = dongle_serial
            result["inverter_serial"] = inverter_serial
        elif transport_type == "modbus":
            from pylxpweb.transports.modbus import INPUT_REGISTER_GROUPS, ModbusTransport

            transport = ModbusTransport(
                host=host,
                port=port,
                serial=serial or "",
            )
            result["serial"] = serial
        else:
            result["error"] = f"Unknown transport type: {transport_type}"
            return result

        await transport.connect()

        # Read raw registers group by group
        raw_registers: dict[int, int] = {}
        group_results: dict[str, dict[str, Any]] = {}

        for group_name, (start, count) in INPUT_REGISTER_GROUPS.items():
            try:
                values = await transport._read_input_registers(start, count)
                group_regs: dict[str, Any] = {}
                for offset, value in enumerate(values):
                    addr = start + offset
                    raw_registers[addr] = value
                    label = REGISTER_LABELS.get(addr, "")
                    key = f"reg_{addr:03d}"
                    group_regs[key] = {
                        "address": addr,
                        "raw_value": value,
                        "hex": f"0x{value:04X}",
                        "label": label,
                    }
                group_results[group_name] = {
                    "start": start,
                    "count": count,
                    "registers": group_regs,
                }
                # Delay between groups for dongle stability
                if transport_type == "dongle":
                    await asyncio.sleep(0.2)
            except Exception as e:
                group_results[group_name] = {
                    "start": start,
                    "count": count,
                    "error": str(e),
                }

        # Also produce the processed InverterRuntimeData for comparison
        processed: dict[str, Any] = {}
        try:
            from pylxpweb.transports.data import InverterRuntimeData

            runtime_data = InverterRuntimeData.from_modbus_registers(raw_registers)
            processed = {
                "pv_total_power": runtime_data.pv_total_power,
                "pv1_power": runtime_data.pv1_power,
                "pv2_power": runtime_data.pv2_power,
                "pv3_power": runtime_data.pv3_power,
                "inverter_power": runtime_data.inverter_power,
                "grid_power": runtime_data.grid_power,
                "power_to_grid": runtime_data.power_to_grid,
                "power_from_grid": runtime_data.power_from_grid,
                "load_power": runtime_data.load_power,
                "eps_power": runtime_data.eps_power,
                "battery_charge_power": runtime_data.battery_charge_power,
                "battery_discharge_power": runtime_data.battery_discharge_power,
                "battery_soc": runtime_data.battery_soc,
                "battery_soh": runtime_data.battery_soh,
                "battery_voltage": runtime_data.battery_voltage,
                "battery_temperature": runtime_data.battery_temperature,
            }
        except Exception as e:
            processed["error"] = str(e)

        # Key power registers side-by-side for quick inspection
        power_register_summary = {}
        for addr, label in sorted(REGISTER_LABELS.items()):
            if addr in raw_registers:
                power_register_summary[f"reg_{addr:03d}_{label.split('(')[0].strip()}"] = raw_registers[addr]

        result["register_groups"] = group_results
        result["power_register_summary"] = power_register_summary
        result["processed_runtime"] = processed
        result["raw_register_dump"] = {
            str(addr): value for addr, value in sorted(raw_registers.items())
        }

        await transport.disconnect()

    except Exception as e:
        result["error"] = str(e)
        import traceback
        result["traceback"] = traceback.format_exc()

    return result


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Dump power flow diagnostic data for troubleshooting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
The output is automatically sanitized (serial numbers masked,
addresses removed). You can safely paste it into a GitHub issue.
Use --no-sanitize to keep raw values (not recommended for sharing).
        """,
    )

    # HTTP API options
    parser.add_argument("--username", default=os.getenv("LUXPOWER_USERNAME"))
    parser.add_argument("--password", default=os.getenv("LUXPOWER_PASSWORD"))
    parser.add_argument(
        "--base-url",
        default=os.getenv("LUXPOWER_BASE_URL", "https://monitor.eg4electronics.com"),
    )
    parser.add_argument("--skip-http", action="store_true", help="Skip HTTP API collection")

    # Dongle options (repeatable via --dongle for multiple inverters)
    parser.add_argument(
        "--dongle",
        action="append",
        metavar="IP:DONGLE_SERIAL:INVERTER_SERIAL",
        help=(
            "WiFi dongle connection as IP:DONGLE_SERIAL:INVERTER_SERIAL. "
            "Can be specified multiple times for multiple inverters. "
            "Example: --dongle 10.0.0.1:BJ45000202:4512670118"
        ),
    )
    parser.add_argument("--dongle-port", type=int, default=8000)

    # Modbus options (repeatable via --modbus for multiple inverters)
    parser.add_argument(
        "--modbus",
        action="append",
        metavar="IP:INVERTER_SERIAL",
        help=(
            "Modbus TCP connection as IP:INVERTER_SERIAL. "
            "Can be specified multiple times for multiple inverters. "
            "Port defaults to 502. Use IP:PORT:SERIAL for non-standard ports. "
            "Example: --modbus 172.16.40.98:52842P0581"
        ),
    )

    # Output options
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("--no-sanitize", action="store_true")

    args = parser.parse_args()

    # Generate output filename
    if args.output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = f"power_diagnostics_{timestamp}.json"

    print("=" * 60)
    print("  Power Flow Diagnostic Dump")
    print("  pylxpweb - troubleshooting tool")
    print("=" * 60)
    print()

    # Interactive prompts for missing credentials
    if not args.skip_http:
        args.username = _prompt_if_missing(
            args.username, "Monitor portal username (or press Enter to skip HTTP): "
        )
        if args.username:
            args.password = _prompt_if_missing(
                args.password, "Monitor portal password: ", secret=True
            )
            # Prompt for base URL if using default and interactive
            if args.base_url == "https://monitor.eg4electronics.com":
                print("\n  API endpoint options:")
                print("    1. EG4 Electronics (US)  - monitor.eg4electronics.com [default]")
                print("    2. LuxPower (US)         - us.luxpowertek.com")
                print("    3. LuxPower (EU)         - eu.luxpowertek.com")
                print("    4. LuxPower (AU/Global)  - luxpowertek.com")
                choice = _prompt_if_missing(None, "  Select endpoint (1-4, or Enter for default): ")
                if choice == "2":
                    args.base_url = "https://us.luxpowertek.com"
                elif choice == "3":
                    args.base_url = "https://eu.luxpowertek.com"
                elif choice == "4":
                    args.base_url = "https://luxpowertek.com"

    # Build dongle list from --dongle args or env vars
    dongles: list[tuple[str, str, str]] = []  # (ip, dongle_serial, inverter_serial)
    if args.dongle:
        for spec in args.dongle:
            parts = spec.split(":")
            if len(parts) == 3:
                dongles.append((parts[0], parts[1], parts[2]))
            else:
                print(f"WARNING: Invalid --dongle format '{spec}', expected IP:DONGLE_SERIAL:INVERTER_SERIAL")
    elif os.getenv("DONGLE_IP"):
        # Fall back to single env var set
        dongles.append((
            os.getenv("DONGLE_IP", ""),
            os.getenv("DONGLE_SERIAL", ""),
            os.getenv("DONGLE_INVERTER_SERIAL", ""),
        ))

    # Build modbus list from --modbus args or env vars
    modbus_connections: list[tuple[str, int, str]] = []  # (ip, port, serial)
    if args.modbus:
        for spec in args.modbus:
            parts = spec.split(":")
            if len(parts) == 2:
                modbus_connections.append((parts[0], 502, parts[1]))
            elif len(parts) == 3:
                modbus_connections.append((parts[0], int(parts[1]), parts[2]))
            else:
                print(f"WARNING: Invalid --modbus format '{spec}', expected IP:SERIAL or IP:PORT:SERIAL")
    elif os.getenv("MODBUS_IP"):
        modbus_connections.append((
            os.getenv("MODBUS_IP", ""),
            int(os.getenv("MODBUS_PORT", "502")),
            os.getenv("MODBUS_SERIAL", ""),
        ))

    # Interactive prompts for local connections if none configured
    if not dongles and not modbus_connections:
        print("Local connections (WiFi dongle / Modbus TCP):")
        print("  Add one or more inverter connections, or press Enter to skip.\n")

        idx = 1
        while True:
            conn_type = _prompt_if_missing(
                None,
                f"  Inverter #{idx} connection type (dongle/modbus/Enter to finish): ",
            )
            if not conn_type:
                break
            conn_type = conn_type.strip().lower()

            if conn_type == "dongle":
                ip = _prompt_if_missing(None, "    Dongle IP address: ")
                if not ip:
                    break
                d_serial = _prompt_if_missing(None, "    Dongle serial number: ")
                i_serial = _prompt_if_missing(None, "    Inverter serial number: ")
                if d_serial and i_serial:
                    dongles.append((ip, d_serial, i_serial))
                    idx += 1
            elif conn_type == "modbus":
                ip = _prompt_if_missing(None, "    Modbus gateway IP address: ")
                if not ip:
                    break
                i_serial = _prompt_if_missing(None, "    Inverter serial number: ")
                if i_serial:
                    modbus_connections.append((ip, 502, i_serial))
                    idx += 1
            else:
                print(f"    Unknown type '{conn_type}'. Use 'dongle' or 'modbus'.")

    print()

    diagnostics: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "tool": "dump_power_diagnostics.py",
        "http_data": None,
        "local_devices": [],
    }

    # ── HTTP API ──
    if not args.skip_http and args.username and args.password:
        print(f"[HTTP] Fetching from {args.base_url} ...")
        try:
            diagnostics["http_data"] = await collect_http_data(
                args.username, args.password, args.base_url
            )
            inv_count = len(diagnostics["http_data"].get("inverters", []))
            print(f"[HTTP] Done - {inv_count} inverter(s)")
        except Exception as e:
            print(f"[HTTP] Error: {e}")
            diagnostics["http_data"] = {"error": str(e)}
    else:
        print("[HTTP] Skipped (no credentials or --skip-http)")

    # ── Dongles ──
    for i, (ip, d_serial, i_serial) in enumerate(dongles, 1):
        label = f"DONGLE #{i}" if len(dongles) > 1 else "DONGLE"
        print(f"\n[{label}] Reading raw registers from {ip}:{args.dongle_port} (inv: {i_serial}) ...")
        try:
            data = await collect_raw_registers(
                "dongle",
                ip,
                args.dongle_port,
                dongle_serial=d_serial,
                inverter_serial=i_serial,
            )
            data["label"] = label
            diagnostics["local_devices"].append(data)
            print(f"[{label}] Done")
        except Exception as e:
            print(f"[{label}] Error: {e}")
            diagnostics["local_devices"].append({
                "label": label, "source": "dongle", "host": ip, "error": str(e),
            })

    # ── Modbus TCP ──
    for i, (ip, port, serial) in enumerate(modbus_connections, 1):
        label = f"MODBUS #{i}" if len(modbus_connections) > 1 else "MODBUS"
        print(f"\n[{label}] Reading raw registers from {ip}:{port} (inv: {serial}) ...")
        try:
            data = await collect_raw_registers(
                "modbus",
                ip,
                port,
                serial=serial,
            )
            data["label"] = label
            diagnostics["local_devices"].append(data)
            print(f"[{label}] Done")
        except Exception as e:
            print(f"[{label}] Error: {e}")
            diagnostics["local_devices"].append({
                "label": label, "source": "modbus", "host": ip, "error": str(e),
            })

    if not dongles and not modbus_connections:
        print("\n[LOCAL] Skipped (no dongle or Modbus connections configured)")

    # ── Sanitize ──
    if not args.no_sanitize:
        print("\nSanitizing sensitive data ...")
        diagnostics = sanitize("root", diagnostics)

    # ── Write output ──
    output_path = Path(args.output)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(diagnostics, f, indent=2, ensure_ascii=False, default=str)

    file_size = output_path.stat().st_size / 1024
    print(f"\nSaved to: {args.output} ({file_size:.1f} KB)")
    print()
    print("To share:")
    print("  Paste the contents of the JSON file into a GitHub issue comment.")
    print("  Sensitive data (serials, addresses) has been automatically redacted.")


if __name__ == "__main__":
    asyncio.run(main())
