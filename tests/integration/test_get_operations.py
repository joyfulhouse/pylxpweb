"""Integration tests for GET operations with live API.

These tests are READ-ONLY and safe to run. They test data retrieval without
modifying any device settings.

To run these tests:
1. Create a .env file in project root with credentials
2. Run: pytest -m integration tests/integration/test_get_operations.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load .env file before importing anything else
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Import after loading .env
sys.path.insert(0, str(Path(__file__).parent.parent))

from pylxpweb import LuxpowerClient, OperatingMode  # noqa: E402
from pylxpweb.devices import Station  # noqa: E402
from pylxpweb.devices.inverters import BaseInverter  # noqa: E402
from pylxpweb.exceptions import LuxpowerAPIError  # noqa: E402

# Load credentials from environment
LUXPOWER_USERNAME = os.getenv("LUXPOWER_USERNAME")
LUXPOWER_PASSWORD = os.getenv("LUXPOWER_PASSWORD")
LUXPOWER_BASE_URL = os.getenv("LUXPOWER_BASE_URL", "https://monitor.eg4electronics.com")

# Skip all tests if credentials are not provided
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not LUXPOWER_USERNAME or not LUXPOWER_PASSWORD,
        reason="Integration tests require LUXPOWER_USERNAME and LUXPOWER_PASSWORD in .env",
    ),
]


# Note: client and station fixtures now provided by conftest.py (session-scoped with throttling)


@pytest.fixture
async def inverter(station: Station | None) -> BaseInverter | None:
    """Get first inverter from station."""
    if not station:
        return None
    return station.all_inverters[0] if station.all_inverters else None


@pytest.fixture
async def hybrid_inverter(station: Station | None) -> BaseInverter | None:
    """Get first inverter with hybrid capabilities (18KPV, FlexBOSS, etc)."""
    if not station:
        return None
    # Look for inverters with hybrid-capable models
    hybrid_models = ["18kpv", "flexboss", "12kpv", "xp"]
    for inv in station.all_inverters:
        if any(model in inv.model.lower() for model in hybrid_models):
            return inv
    return None


class TestStationGetOperations:
    """Test Station GET operations (read-only, safe)."""

    @pytest.mark.asyncio
    async def test_get_daylight_saving_time_enabled(self, station: Station | None):
        """Test getting DST setting from station."""
        if not station:
            pytest.skip("No station available for testing")

        # This is a read-only method, safe to test
        dst_enabled = await station.get_daylight_saving_time_enabled()

        # Should return a boolean value
        assert isinstance(dst_enabled, bool)
        print(f"\nStation DST enabled: {dst_enabled}")


class TestOperatingModeGetOperations:
    """Test Operating Mode GET operations (read-only, safe)."""

    @pytest.mark.asyncio
    async def test_get_operating_mode(self, client: LuxpowerClient, inverter: BaseInverter | None):
        """Test getting current operating mode."""
        if not inverter:
            pytest.skip("No inverter available for testing")

        try:
            # Read current operating mode
            mode = await inverter.get_operating_mode()

            # Should return an OperatingMode enum value
            assert isinstance(mode, OperatingMode)
            assert mode in [OperatingMode.NORMAL, OperatingMode.STANDBY]
            print(f"\nInverter {inverter.serial_number} operating mode: {mode.value}")

        except LuxpowerAPIError as err:
            # If apiBlocked, skip test - account lacks permission for parameter read
            if "apiBlocked" in str(err):
                pytest.skip(
                    "Operating mode read blocked (apiBlocked) - "
                    "account lacks permission for parameter read operations"
                )
            raise  # Re-raise if different error

    @pytest.mark.asyncio
    async def test_get_quick_charge_status(self, inverter: BaseInverter | None):
        """Test getting quick charge status."""
        if not inverter:
            pytest.skip("No inverter available for testing")

        # Read quick charge status
        status = await inverter.get_quick_charge_status()

        # Should return a boolean
        assert isinstance(status, bool)
        print(f"\nInverter {inverter.serial_number} quick charge active: {status}")

    @pytest.mark.asyncio
    async def test_get_quick_discharge_status(self, inverter: BaseInverter | None):
        """Test getting quick discharge status."""
        if not inverter:
            pytest.skip("No inverter available for testing")

        # Read quick discharge status
        status = await inverter.get_quick_discharge_status()

        # Should return a boolean
        assert isinstance(status, bool)
        print(f"\nInverter {inverter.serial_number} quick discharge active: {status}")


class TestBatteryCurrentGetOperations:
    """Test Battery Current GET operations (read-only, safe)."""

    @pytest.mark.asyncio
    async def test_get_battery_charge_current(self, inverter: BaseInverter | None):
        """Test getting battery charge current limit."""
        if not inverter:
            pytest.skip("No inverter available for testing")

        # Read battery charge current limit
        current = await inverter._client.api.control.get_battery_charge_current(
            inverter.serial_number
        )

        # Should return a non-negative integer
        assert isinstance(current, int)
        assert 0 <= current <= 250
        print(f"\nInverter {inverter.serial_number} charge current limit: {current}A")

    @pytest.mark.asyncio
    async def test_get_battery_discharge_current(self, inverter: BaseInverter | None):
        """Test getting battery discharge current limit."""
        if not inverter:
            pytest.skip("No inverter available for testing")

        # Read battery discharge current limit
        current = await inverter._client.api.control.get_battery_discharge_current(
            inverter.serial_number
        )

        # Should return a non-negative integer
        assert isinstance(current, int)
        assert 0 <= current <= 250
        print(f"\nInverter {inverter.serial_number} discharge current limit: {current}A")


class TestACChargeGetOperations:
    """Test AC Charge GET operations (read-only, safe)."""

    @pytest.mark.asyncio
    async def test_get_ac_charge_power(
        self, client: LuxpowerClient, hybrid_inverter: BaseInverter | None
    ):
        """Test getting AC charge power setting."""
        if not hybrid_inverter:
            pytest.skip("No hybrid-capable inverter available for testing")

        try:
            # Refresh parameters and read AC charge power
            await hybrid_inverter.refresh(include_parameters=True)
            power = hybrid_inverter.ac_charge_power_limit

            # Skip if API returned None (rate limiting or incomplete data)
            if power is None:
                pytest.skip("AC charge power returned None - API may be rate limiting")

            # Should return a float
            assert isinstance(power, (int, float))
            assert power >= 0
            print(f"\nInverter {hybrid_inverter.serial_number} AC charge power: {power}W")

        except LuxpowerAPIError as err:
            if "apiBlocked" in str(err):
                pytest.skip(
                    "AC charge power read blocked (apiBlocked) - "
                    "account lacks permission for parameter read operations"
                )
            raise

    @pytest.mark.asyncio
    async def test_get_ac_charge_soc_limit(
        self, client: LuxpowerClient, hybrid_inverter: BaseInverter | None
    ):
        """Test getting AC charge SOC limit setting."""
        if not hybrid_inverter:
            pytest.skip("No hybrid-capable inverter available for testing")

        try:
            # First refresh parameters to populate the cache
            await hybrid_inverter.refresh(include_parameters=True)

            # Read AC charge SOC limit from cached parameters
            soc_limit = hybrid_inverter.ac_charge_soc_limit

            # Skip if API returned None (rate limiting or incomplete data)
            if soc_limit is None:
                pytest.skip("AC charge SOC limit returned None - API may be rate limiting")

            # Should return an integer between 0-100
            assert isinstance(soc_limit, int)
            assert 0 <= soc_limit <= 100
            print(f"\nInverter {hybrid_inverter.serial_number} AC charge SOC limit: {soc_limit}%")

        except LuxpowerAPIError as err:
            if "apiBlocked" in str(err):
                pytest.skip(
                    "AC charge SOC limit read blocked (apiBlocked) - "
                    "account lacks permission for parameter read operations"
                )
            raise


class TestParameterReadOperations:
    """Test parameter read operations (read-only, safe).

    NOTE: Direct read_parameters() test removed because:
    1. The method is deprecated in favor of refresh(include_parameters=True)
    2. Functionality is tested via property accessors in other tests
    """

    pass  # Class kept for organizational purposes


class TestSOCLimitGetOperations:
    """Test SOC Limit GET operations (read-only, safe)."""

    @pytest.mark.asyncio
    async def test_get_battery_soc_limits(
        self, client: LuxpowerClient, inverter: BaseInverter | None
    ):
        """Test getting battery SOC limits."""
        if not inverter:
            pytest.skip("No inverter available for testing")

        try:
            # Refresh parameters and read battery SOC limits
            await inverter.refresh(include_parameters=True)
            limits = inverter.battery_soc_limits

            # Skip if API returned None (rate limiting or incomplete data)
            if limits is None:
                pytest.skip("Battery SOC limits returned None - API may be rate limiting")

            # Should return a dict with on_grid_limit and off_grid_limit
            assert isinstance(limits, dict)
            assert "on_grid_limit" in limits
            assert "off_grid_limit" in limits

            on_grid = limits["on_grid_limit"]
            off_grid = limits["off_grid_limit"]

            # Skip if values are None (incomplete data)
            if on_grid is None or off_grid is None:
                pytest.skip("Battery SOC limit values are None - API may be rate limiting")

            # Convert to int if string
            if isinstance(on_grid, str):
                on_grid = int(on_grid)
            if isinstance(off_grid, str):
                off_grid = int(off_grid)

            assert isinstance(on_grid, int)
            assert isinstance(off_grid, int)
            assert 0 <= on_grid <= 100
            assert 0 <= off_grid <= 100

            print(f"\nInverter {inverter.serial_number} SOC limits:")
            print(f"  On-grid cutoff: {on_grid}%")
            print(f"  Off-grid cutoff: {off_grid}%")

        except LuxpowerAPIError as err:
            if "apiBlocked" in str(err):
                pytest.skip(
                    "SOC limits read blocked (apiBlocked) - "
                    "account lacks permission for parameter read operations"
                )
            raise


class TestQuickChargeStatusAPIEndpoint:
    """Test quick charge/discharge status API endpoint directly."""

    @pytest.mark.asyncio
    async def test_get_quick_charge_status_api(
        self, client: LuxpowerClient, inverter: BaseInverter | None
    ):
        """Test quick charge status API endpoint returns both charge and discharge status."""
        if not inverter:
            pytest.skip("No inverter available for testing")

        # Call the API endpoint directly
        status = await client.api.control.get_quick_charge_status(inverter.serial_number)

        # Should return QuickChargeStatus with both fields
        assert status.success is True
        assert hasattr(status, "hasUnclosedQuickChargeTask")
        assert hasattr(status, "hasUnclosedQuickDischargeTask")
        assert isinstance(status.hasUnclosedQuickChargeTask, bool)
        assert isinstance(status.hasUnclosedQuickDischargeTask, bool)

        print(f"\nQuick charge/discharge status for {inverter.serial_number}:")
        print(f"  Quick charge active: {status.hasUnclosedQuickChargeTask}")
        print(f"  Quick discharge active: {status.hasUnclosedQuickDischargeTask}")
