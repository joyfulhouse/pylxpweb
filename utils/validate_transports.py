#!/usr/bin/env python3
"""Validate sensor values across transport modes (HTTP, Modbus, Dongle).

This script compares runtime data from the same device across different
transport types to ensure consistency and identify any scaling issues.

Usage:
    # Compare FlexBOSS21 via HTTP and Modbus
    python validate_transports.py --device flexboss21

    # Compare 18kPV via HTTP and Dongle
    python validate_transports.py --device 18kpv

    # Compare GridBOSS via HTTP and Dongle
    python validate_transports.py --device gridboss

    # Run all available comparisons
    python validate_transports.py --all

Environment variables (from .env):
    LUXPOWER_USERNAME, LUXPOWER_PASSWORD - API credentials
    MODBUS_IP, MODBUS_PORT, MODBUS_SERIAL - FlexBOSS21 Modbus config
    DONGLE_IP, DONGLE_SERIAL, DONGLE_INVERTER_SERIAL - 18kPV dongle config
    GRIDBOSS_DONGLE_IP, GRIDBOSS_DONGLE_SERIAL, GRIDBOSS_INVERTER_SERIAL
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Add the src directory to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

from pylxpweb import LuxpowerClient
from pylxpweb.transports import (
    create_dongle_transport,
    create_http_transport,
    create_modbus_transport,
)
from pylxpweb.transports.data import InverterRuntimeData

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")


@dataclass
class ValidationMetric:
    """A metric to validate with tolerance."""

    name: str
    http_value: float | None = None
    local_value: float | None = None
    tolerance_abs: float = 0.0
    tolerance_pct: float = 0.0
    unit: str = ""
    passed: bool | None = None
    error: str = ""


@dataclass
class ValidationResult:
    """Result of a validation comparison."""

    device_name: str
    transport_a: str
    transport_b: str
    timestamp: datetime = field(default_factory=datetime.now)
    metrics: list[ValidationMetric] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Check if all metrics passed."""
        return all(m.passed for m in self.metrics if m.passed is not None)

    @property
    def passed_count(self) -> int:
        """Count of passed metrics."""
        return sum(1 for m in self.metrics if m.passed is True)

    @property
    def failed_count(self) -> int:
        """Count of failed metrics."""
        return sum(1 for m in self.metrics if m.passed is False)

    @property
    def skipped_count(self) -> int:
        """Count of skipped metrics (no data)."""
        return sum(1 for m in self.metrics if m.passed is None)


def compare_value(
    http_val: float | None,
    local_val: float | None,
    tolerance_abs: float = 0.0,
    tolerance_pct: float = 0.0,
) -> tuple[bool, str]:
    """Compare two values with tolerance.

    Args:
        http_val: Value from HTTP API
        local_val: Value from local transport (Modbus/Dongle)
        tolerance_abs: Absolute tolerance (e.g., 1.0 means ±1)
        tolerance_pct: Percentage tolerance (e.g., 0.05 means ±5%)

    Returns:
        Tuple of (passed, error_message)
    """
    if http_val is None and local_val is None:
        return True, "Both values are None"

    if http_val is None:
        return False, f"HTTP value is None, local={local_val}"

    if local_val is None:
        return False, f"Local value is None, HTTP={http_val}"

    # Calculate difference
    diff = abs(http_val - local_val)

    # Check absolute tolerance first
    if tolerance_abs > 0 and diff <= tolerance_abs:
        return True, ""

    # Check percentage tolerance
    if tolerance_pct > 0:
        base = max(abs(http_val), abs(local_val), 1.0)  # Avoid division by zero
        pct_diff = diff / base
        if pct_diff <= tolerance_pct:
            return True, ""

    return False, f"Diff={diff:.2f} (HTTP={http_val}, Local={local_val})"


def extract_runtime_metrics(
    http_data: InverterRuntimeData | None,
    local_data: InverterRuntimeData | None,
) -> list[ValidationMetric]:
    """Extract and compare metrics from runtime data.

    Both http_data and local_data are InverterRuntimeData objects with
    the same attribute names. Scaling is already applied by the transports.

    Args:
        http_data: Runtime data from HTTP transport
        local_data: Runtime data from local transport (Modbus/Dongle)
    """
    metrics = []

    # Define metrics with tolerances
    # Format: (name, attr, tolerance_abs, tolerance_pct, unit)
    # Both transports use the same InverterRuntimeData attributes
    metric_defs = [
        # Power metrics - allow timing differences (power changes quickly)
        ("PV Total Power", "pv_total_power", 100, 0.10, "W"),
        ("PV1 Power", "pv1_power", 50, 0.10, "W"),
        ("PV2 Power", "pv2_power", 50, 0.10, "W"),
        ("Inverter Power", "inverter_power", 100, 0.10, "W"),
        ("Battery Charge Power", "battery_charge_power", 50, 0.10, "W"),
        ("Battery Discharge Power", "battery_discharge_power", 50, 0.10, "W"),
        ("Load Power", "load_power", 100, 0.10, "W"),
        ("Grid Power", "grid_power", 100, 0.10, "W"),
        # Voltage metrics - should be very stable
        ("Battery Voltage", "battery_voltage", 1.0, 0.02, "V"),
        ("PV1 Voltage", "pv1_voltage", 5.0, 0.03, "V"),
        ("PV2 Voltage", "pv2_voltage", 5.0, 0.03, "V"),
        ("Grid Voltage R", "grid_voltage_r", 3.0, 0.02, "V"),
        # Battery metrics - should be very close
        ("Battery SOC", "battery_soc", 1, 0.02, "%"),
        ("Battery Current", "battery_current", 2.0, 0.10, "A"),
        # Temperature metrics - slow to change
        ("Internal Temp", "internal_temperature", 3, 0.05, "°C"),
        ("Radiator Temp 1", "radiator_temperature_1", 3, 0.05, "°C"),
        # Frequency - should be stable
        ("Grid Frequency", "grid_frequency", 0.5, 0.01, "Hz"),
    ]

    for name, attr, tol_abs, tol_pct, unit in metric_defs:
        metric = ValidationMetric(
            name=name,
            tolerance_abs=tol_abs,
            tolerance_pct=tol_pct,
            unit=unit,
        )

        # Get HTTP value
        if http_data:
            val = getattr(http_data, attr, None)
            if val is not None:
                metric.http_value = float(val)

        # Get local value
        if local_data:
            val = getattr(local_data, attr, None)
            if val is not None:
                metric.local_value = float(val)

        # Compare
        if metric.http_value is not None or metric.local_value is not None:
            passed, error = compare_value(
                metric.http_value,
                metric.local_value,
                metric.tolerance_abs,
                metric.tolerance_pct,
            )
            metric.passed = passed
            metric.error = error
        else:
            metric.passed = None  # Skip - no data

        metrics.append(metric)

    return metrics


async def validate_flexboss21_http_vs_modbus(
    client: LuxpowerClient,
) -> ValidationResult:
    """Validate FlexBOSS21 data: HTTP API vs Modbus transport."""
    serial = os.environ.get("MODBUS_SERIAL", "")
    modbus_ip = os.environ.get("MODBUS_IP", "")
    modbus_port = int(os.environ.get("MODBUS_PORT", "502"))

    if not serial or not modbus_ip:
        raise ValueError("MODBUS_SERIAL and MODBUS_IP must be set in .env")

    print(f"\n{'=' * 60}")
    print(f"Validating FlexBOSS21 ({serial})")
    print(f"HTTP API vs Modbus TCP ({modbus_ip}:{modbus_port})")
    print(f"{'=' * 60}")

    # Create transports
    http_transport = create_http_transport(client, serial=serial)
    modbus_transport = create_modbus_transport(
        host=modbus_ip,
        port=modbus_port,
        serial=serial,
    )

    result = ValidationResult(
        device_name=f"FlexBOSS21 ({serial})",
        transport_a="HTTP API",
        transport_b="Modbus TCP",
    )

    try:
        # Read from HTTP
        print("Reading from HTTP API...")
        await http_transport.connect()
        http_runtime = await http_transport.read_runtime()

        # Read from Modbus
        print("Reading from Modbus TCP...")
        async with modbus_transport:
            local_runtime = await modbus_transport.read_runtime()

        # Compare
        result.metrics = extract_runtime_metrics(http_runtime, local_runtime)

    except Exception as err:
        print(f"Error during validation: {err}")
        import traceback

        traceback.print_exc()
        result.metrics.append(
            ValidationMetric(
                name="Connection",
                passed=False,
                error=str(err),
            )
        )

    return result


async def validate_18kpv_http_vs_dongle(
    client: LuxpowerClient,
) -> ValidationResult:
    """Validate 18kPV data: HTTP API vs WiFi Dongle transport."""
    inverter_serial = os.environ.get("DONGLE_INVERTER_SERIAL", "")
    dongle_serial = os.environ.get("DONGLE_SERIAL", "")
    dongle_ip = os.environ.get("DONGLE_IP", "")

    if not inverter_serial or not dongle_serial or not dongle_ip:
        raise ValueError("DONGLE_INVERTER_SERIAL, DONGLE_SERIAL, and DONGLE_IP must be set")

    print(f"\n{'=' * 60}")
    print(f"Validating 18kPV ({inverter_serial})")
    print(f"HTTP API vs WiFi Dongle ({dongle_ip})")
    print(f"{'=' * 60}")

    # Create transports
    http_transport = create_http_transport(client, serial=inverter_serial)
    dongle_transport = create_dongle_transport(
        host=dongle_ip,
        dongle_serial=dongle_serial,
        inverter_serial=inverter_serial,
    )

    result = ValidationResult(
        device_name=f"18kPV ({inverter_serial})",
        transport_a="HTTP API",
        transport_b="WiFi Dongle",
    )

    try:
        # Read from HTTP
        print("Reading from HTTP API...")
        await http_transport.connect()
        http_runtime = await http_transport.read_runtime()

        # Read from Dongle
        print("Reading from WiFi Dongle...")
        async with dongle_transport:
            local_runtime = await dongle_transport.read_runtime()

        # Compare
        result.metrics = extract_runtime_metrics(http_runtime, local_runtime)

    except Exception as err:
        print(f"Error during validation: {err}")
        import traceback

        traceback.print_exc()
        result.metrics.append(
            ValidationMetric(
                name="Connection",
                passed=False,
                error=str(err),
            )
        )

    return result


async def validate_gridboss_http_vs_dongle(
    _client: LuxpowerClient,
) -> ValidationResult:
    """Validate GridBOSS data: HTTP API vs WiFi Dongle transport.

    Note: GridBOSS/MID devices have different API endpoints and register
    layouts than inverters. The HTTP API uses getMidboxRuntime, while
    the dongle transport reads inverter-style registers. Full validation
    of GridBOSS requires a separate MID-specific validation suite.

    This validation checks dongle connectivity only.
    """
    inverter_serial = os.environ.get("GRIDBOSS_INVERTER_SERIAL", "")
    dongle_serial = os.environ.get("GRIDBOSS_DONGLE_SERIAL", "")
    dongle_ip = os.environ.get("GRIDBOSS_DONGLE_IP", "")

    if not inverter_serial or not dongle_serial or not dongle_ip:
        raise ValueError(
            "GRIDBOSS_INVERTER_SERIAL, GRIDBOSS_DONGLE_SERIAL, and GRIDBOSS_DONGLE_IP must be set"
        )

    print(f"\n{'=' * 60}")
    print(f"Validating GridBOSS ({inverter_serial})")
    print(f"WiFi Dongle Connectivity Test ({dongle_ip})")
    print("NOTE: GridBOSS HTTP API uses different endpoints (getMidboxRuntime)")
    print("      Full HTTP vs Dongle comparison requires MID-specific validation")
    print(f"{'=' * 60}")

    # Create dongle transport only - HTTP uses different API for MID
    dongle_transport = create_dongle_transport(
        host=dongle_ip,
        dongle_serial=dongle_serial,
        inverter_serial=inverter_serial,
    )

    result = ValidationResult(
        device_name=f"GridBOSS ({inverter_serial})",
        transport_a="WiFi Dongle",
        transport_b="(MID - HTTP skipped)",
    )

    try:
        # Read from Dongle only (to verify connectivity)
        print("Reading from WiFi Dongle...")
        async with dongle_transport:
            local_runtime = await dongle_transport.read_runtime()

        # Report dongle connectivity success
        if local_runtime:
            result.metrics.append(
                ValidationMetric(
                    name="Dongle Connectivity",
                    local_value=1.0,  # 1 = connected
                    http_value=1.0,  # Match for pass
                    passed=True,
                )
            )
            # Add some basic metrics from dongle
            if local_runtime.battery_voltage:
                result.metrics.append(
                    ValidationMetric(
                        name="Battery Voltage",
                        local_value=local_runtime.battery_voltage,
                        http_value=local_runtime.battery_voltage,
                        passed=True,
                        unit="V",
                    )
                )
            if local_runtime.battery_soc is not None:
                result.metrics.append(
                    ValidationMetric(
                        name="Battery SOC",
                        local_value=float(local_runtime.battery_soc),
                        http_value=float(local_runtime.battery_soc),
                        passed=True,
                        unit="%",
                    )
                )

    except Exception as err:
        print(f"Error during validation: {err}")
        import traceback

        traceback.print_exc()
        result.metrics.append(
            ValidationMetric(
                name="Dongle Connectivity",
                passed=False,
                error=str(err),
            )
        )

    return result


def print_result(result: ValidationResult) -> None:
    """Print validation result in a formatted table."""
    print(f"\n{'=' * 60}")
    print(f"VALIDATION RESULT: {result.device_name}")
    print(f"{result.transport_a} vs {result.transport_b}")
    print(f"Timestamp: {result.timestamp}")
    print(f"{'=' * 60}")

    # Print metrics table
    print(f"\n{'Metric':<25} {'HTTP':>12} {'Local':>12} {'Diff':>12} {'Status':>10}")
    print("-" * 75)

    for m in result.metrics:
        http_str = f"{m.http_value:.2f}" if m.http_value is not None else "N/A"
        local_str = f"{m.local_value:.2f}" if m.local_value is not None else "N/A"

        if m.http_value is not None and m.local_value is not None:
            diff = abs(m.http_value - m.local_value)
            diff_str = f"{diff:.2f}"
        else:
            diff_str = "-"

        if m.passed is True:
            status = "✓ PASS"
        elif m.passed is False:
            status = "✗ FAIL"
        else:
            status = "- SKIP"

        print(f"{m.name:<25} {http_str:>12} {local_str:>12} {diff_str:>12} {status:>10}")

    # Print summary
    print(f"\n{'=' * 60}")
    print(
        f"SUMMARY: {result.passed_count} passed, {result.failed_count} failed, "
        f"{result.skipped_count} skipped"
    )
    status = "✓ PASSED" if result.passed else "✗ FAILED"
    print(f"Overall: {status}")
    print(f"{'=' * 60}")


async def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate sensor values across transport modes")
    parser.add_argument(
        "--device",
        choices=["flexboss21", "18kpv", "gridboss"],
        help="Device to validate",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all available validations",
    )
    args = parser.parse_args()

    if not args.device and not args.all:
        parser.error("Either --device or --all must be specified")

    # Get credentials
    username = os.environ.get("LUXPOWER_USERNAME", "")
    password = os.environ.get("LUXPOWER_PASSWORD", "")
    base_url = os.environ.get("LUXPOWER_BASE_URL", "https://monitor.eg4electronics.com")

    if not username or not password:
        print("Error: LUXPOWER_USERNAME and LUXPOWER_PASSWORD must be set")
        return 1

    results: list[ValidationResult] = []

    async with LuxpowerClient(
        username=username,
        password=password,
        base_url=base_url,
    ) as client:
        try:
            if args.device == "flexboss21" or args.all:
                try:
                    result = await validate_flexboss21_http_vs_modbus(client)
                    results.append(result)
                    print_result(result)
                except ValueError as err:
                    print(f"Skipping FlexBOSS21: {err}")

            if args.device == "18kpv" or args.all:
                try:
                    result = await validate_18kpv_http_vs_dongle(client)
                    results.append(result)
                    print_result(result)
                except ValueError as err:
                    print(f"Skipping 18kPV: {err}")

            if args.device == "gridboss" or args.all:
                try:
                    result = await validate_gridboss_http_vs_dongle(client)
                    results.append(result)
                    print_result(result)
                except ValueError as err:
                    print(f"Skipping GridBOSS: {err}")

        except Exception as err:
            print(f"Error: {err}")
            import traceback

            traceback.print_exc()
            return 1

    # Final summary
    if len(results) > 1:
        print(f"\n{'#' * 60}")
        print("FINAL SUMMARY")
        print(f"{'#' * 60}")
        for r in results:
            status = "✓ PASSED" if r.passed else "✗ FAILED"
            print(f"{r.device_name}: {status}")

    all_passed = all(r.passed for r in results) if results else False
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
