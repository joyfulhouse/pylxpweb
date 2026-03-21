#!/usr/bin/env python3
"""Validate data integrity reading through Waveshare RS485-to-Ethernet gateway.

Two test modes:
  1. WITH TID patching (pylxpweb's ModbusTransport) — should work fine
  2. WITHOUT TID patching (raw pymodbus) — expect TID mismatch failures

This proves whether the Waveshare gateway actually has the TID echo issue.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("pylxpweb.transports").setLevel(logging.DEBUG)

_LOG = logging.getLogger("validate_waveshare")


async def test_without_tid_patch(host: str, port: int, unit_id: int, num_reads: int) -> None:
    """Test raw pymodbus WITHOUT TID patching — proves the TID issue exists."""
    from pymodbus.client import AsyncModbusTcpClient

    _LOG.info("=" * 60)
    _LOG.info("TEST 1: RAW PYMODBUS (no TID patch)")
    _LOG.info("=" * 60)
    _LOG.info("Connecting to %s:%d ...", host, port)

    # Suppress pymodbus logs to WARNING so we see errors clearly
    logging.getLogger("pymodbus").setLevel(logging.WARNING)

    client = AsyncModbusTcpClient(host=host, port=port, timeout=5.0)
    await client.connect()

    if not client.connected:
        _LOG.error("Failed to connect")
        return

    _LOG.info("Connected. Reading %d times WITHOUT TID patch...\n", num_reads)

    ok = 0
    errors = 0

    for i in range(1, num_reads + 1):
        try:
            # Read input registers 0-39 (runtime group 1)
            result = await asyncio.wait_for(
                client.read_input_registers(address=0, count=40, device_id=unit_id),
                timeout=5.0,
            )
            if result.isError():
                _LOG.warning("  Read %d: ERROR response: %s", i, result)
                errors += 1
            else:
                # Quick sanity: reg 14 = grid_freq (should be ~600 = 60.0Hz)
                freq_raw = result.registers[14] if len(result.registers) > 14 else None
                freq = freq_raw / 10.0 if freq_raw else 0
                _LOG.info(
                    "  Read %d: OK — %d registers, freq=%.1fHz",
                    i,
                    len(result.registers),
                    freq,
                )
                ok += 1
        except Exception as e:
            _LOG.warning("  Read %d: EXCEPTION: %s", i, e)
            errors += 1

        if i < num_reads:
            await asyncio.sleep(0.5)

    client.close()
    _LOG.info("\nRaw pymodbus result: %d OK, %d errors out of %d", ok, errors, num_reads)
    if errors > 0:
        _LOG.warning("TID ISSUE CONFIRMED — pymodbus rejected responses without our patch")
    else:
        _LOG.info("No TID issues detected (gateway may echo TIDs correctly)")


async def test_with_tid_patch(host: str, port: int, serial: str, num_reads: int) -> None:
    """Test pylxpweb's ModbusTransport WITH TID patching — should work fine."""
    from pylxpweb.transports.modbus import ModbusTransport

    _LOG.info("\n" + "=" * 60)
    _LOG.info("TEST 2: PYLXPWEB MODBUS TRANSPORT (with TID patch)")
    _LOG.info("=" * 60)

    transport = ModbusTransport(host=host, port=port, serial=serial)
    await transport.connect()
    _LOG.info("Running %d read cycles with TID patch + canary checks...\n", num_reads)

    stats = {"ok": 0, "corrupt": 0, "error": 0}

    for i in range(1, num_reads + 1):
        try:
            runtime = await transport.read_runtime()
            if runtime.is_corrupt():
                _LOG.warning(
                    "  Cycle %d: CORRUPT — soc=%s freq=%s pv1_v=%s temp=%s",
                    i,
                    runtime.battery_soc,
                    runtime.grid_frequency,
                    runtime.pv1_voltage,
                    runtime.internal_temperature,
                )
                stats["corrupt"] += 1
            else:
                _LOG.info(
                    "  Cycle %d: OK — soc=%s%% freq=%sHz pv=%sW temp=%s°C",
                    i,
                    runtime.battery_soc,
                    runtime.grid_frequency,
                    runtime.pv_total_power,
                    runtime.internal_temperature,
                )
                stats["ok"] += 1
        except Exception as e:
            _LOG.error("  Cycle %d: ERROR — %s", i, e)
            stats["error"] += 1

        # Also test energy
        try:
            energy = await transport.read_energy()
            if energy.is_corrupt():
                _LOG.warning("  Cycle %d energy: CORRUPT", i)
            else:
                _LOG.info(
                    "  Cycle %d energy: OK — today=%.1fkWh total=%.1fkWh",
                    i,
                    energy.pv_energy_today or 0,
                    energy.pv_energy_total or 0,
                )
        except Exception as e:
            _LOG.error("  Cycle %d energy: ERROR — %s", i, e)

        # Battery
        try:
            battery = await transport.read_battery()
            if battery.is_corrupt():
                _LOG.warning(
                    "  Cycle %d battery: CORRUPT — count=%d v=%s",
                    i,
                    battery.battery_count,
                    battery.voltage,
                )
            else:
                _LOG.info(
                    "  Cycle %d battery: OK — count=%d soc=%d%% v=%.1fV i=%.1fA",
                    i,
                    battery.battery_count,
                    battery.soc,
                    battery.voltage,
                    battery.current,
                )
        except Exception as e:
            _LOG.error("  Cycle %d battery: ERROR — %s", i, e)

        if i < num_reads:
            await asyncio.sleep(1.0)

    await transport.disconnect()

    _LOG.info(
        "\nPatched result: %d OK, %d corrupt, %d errors",
        stats["ok"],
        stats["corrupt"],
        stats["error"],
    )


async def main(host: str, port: int, serial: str, num_reads: int) -> None:
    """Run both tests sequentially."""
    # Test 1: Without patch — prove TID issue exists
    await test_without_tid_patch(host, port, 1, num_reads)

    # Brief pause between tests
    await asyncio.sleep(2.0)

    # Test 2: With patch — prove our fix works
    await test_with_tid_patch(host, port, serial, num_reads)

    _LOG.info("\n" + "=" * 60)
    _LOG.info("DONE — compare results above")
    _LOG.info("=" * 60)


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else os.getenv("MODBUS_IP", "10.100.10.184")
    port = int(sys.argv[2]) if len(sys.argv) > 2 else int(os.getenv("MODBUS_PORT", "502"))
    serial = sys.argv[3] if len(sys.argv) > 3 else os.getenv("MODBUS_SERIAL", "52842P0581")
    num_reads = int(sys.argv[4]) if len(sys.argv) > 4 else 5

    asyncio.run(main(host, port, serial, num_reads))
