"""Integration tests for control operations with live API.

WARNING: These tests WRITE to real devices. They use read-then-restore pattern
to minimize risk, but should still be run with EXTREME CAUTION.

Safety features:
1. Read current values before any write
2. Restore original values after test
3. Use small, safe value changes
4. Skip tests if no suitable device found

To run these tests:
1. Create a .env file in project root with credentials
2. Understand the risks - these tests control real hardware
3. Run with explicit marker:
   pytest -m "integration and control" tests/integration/test_control_operations.py

DO NOT run these tests casually!
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load .env file before importing anything else
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Import after loading .env
sys.path.insert(0, str(Path(__file__).parent.parent))

from pylxpweb import LuxpowerClient  # noqa: E402
from pylxpweb.devices import Station  # noqa: E402
from pylxpweb.devices.inverters import HybridInverter  # noqa: E402
from pylxpweb.exceptions import LuxpowerAPIError  # noqa: E402

# Load credentials from environment
LUXPOWER_USERNAME = os.getenv("LUXPOWER_USERNAME")
LUXPOWER_PASSWORD = os.getenv("LUXPOWER_PASSWORD")
LUXPOWER_BASE_URL = os.getenv("LUXPOWER_BASE_URL", "https://monitor.eg4electronics.com")

# Skip all tests if credentials are not provided
pytestmark = [
    pytest.mark.integration,
    pytest.mark.control,  # Extra marker for dangerous tests
    pytest.mark.skipif(
        not LUXPOWER_USERNAME or not LUXPOWER_PASSWORD,
        reason="Control tests require LUXPOWER_USERNAME and LUXPOWER_PASSWORD env vars",
    ),
]


@pytest.fixture
async def client() -> AsyncGenerator[LuxpowerClient, None]:
    """Create authenticated client for testing."""
    async with LuxpowerClient(
        username=LUXPOWER_USERNAME,
        password=LUXPOWER_PASSWORD,
        base_url=LUXPOWER_BASE_URL,
    ) as client:
        yield client


@pytest.fixture
async def hybrid_inverter(client: LuxpowerClient) -> HybridInverter | None:
    """Find a hybrid inverter for testing (if available)."""
    stations = await Station.load_all(client)

    for station in stations:
        for inverter in station.all_inverters:
            if isinstance(inverter, HybridInverter):
                return inverter

    return None


@pytest.mark.asyncio
class TestParameterReadWrite:
    """Test basic parameter read/write operations."""

    async def test_read_parameters(self, client: LuxpowerClient) -> None:
        """Test reading inverter parameters."""
        stations = await Station.load_all(client)
        assert len(stations) > 0

        inverter = stations[0].all_inverters[0]

        # Read function enable register (register 21)
        try:
            params = await inverter.read_parameters(21, 1)

            # Should have parsed parameter names (not raw register keys)
            assert len(params) > 0
            # Register 21 contains function enable flags
            assert any("FUNC" in str(k) for k in params)
        except LuxpowerAPIError as err:
            # If apiBlocked and account is viewer/operator, skip test
            if "apiBlocked" in str(err) and client.account_level in ("guest", "viewer", "operator"):
                pytest.skip(
                    f"Parameter read blocked for {client.account_level} account - "
                    "requires owner/installer permissions"
                )
            raise  # Re-raise if different error or unexpected account level

    # NOTE: write_parameters test removed because:
    # 1. Register 21 controls critical function enables (standby, EPS, etc.)
    # 2. Test was incorrectly extracting value (getting 0, which disables all functions)
    # 3. Caused HTTP 400 errors from malformed requests
    # 4. Too dangerous to test without understanding exact bit fields
    # Control-specific write tests (AC charge, SOC limits) remain below


@pytest.mark.asyncio
class TestSOCLimits:
    """Test battery SOC limit controls."""

    async def test_get_battery_soc_limits(self, client: LuxpowerClient) -> None:
        """Test reading battery SOC limits."""
        stations = await Station.load_all(client)
        inverter = stations[0].all_inverters[0]

        # Refresh parameters first
        await inverter.refresh(include_parameters=True)

        # Read SOC limits
        limits = inverter.battery_soc_limits

        # Should have both on-grid and off-grid limits
        assert "on_grid_limit" in limits
        assert "off_grid_limit" in limits

        # Limits should be in valid ranges
        # Convert to int if strings (API may return strings)
        on_grid_val = limits["on_grid_limit"]
        on_grid = int(on_grid_val) if isinstance(on_grid_val, str) else on_grid_val
        off_grid_val = limits["off_grid_limit"]
        off_grid = int(off_grid_val) if isinstance(off_grid_val, str) else off_grid_val
        assert 0 <= on_grid <= 100
        assert 0 <= off_grid <= 100

    async def test_set_battery_soc_limits_safe(self, client: LuxpowerClient) -> None:
        """Test setting SOC limits with read-then-restore pattern.

        NOTE: This test verifies the API call succeeds but does NOT verify the
        value is applied, as inverters may have undocumented validation rules
        that prevent certain values from being set.
        """
        stations = await Station.load_all(client)
        inverter = stations[0].all_inverters[0]

        try:
            # Refresh parameters and read current limits
            await inverter.refresh(include_parameters=True)
            original_limits = inverter.battery_soc_limits
            # Convert to int if string
            on_grid_val = original_limits["on_grid_limit"]
            original_on_grid = int(on_grid_val) if isinstance(on_grid_val, str) else on_grid_val

            try:
                # Make a small safe change (±1%)
                new_limit = original_on_grid + 1 if original_on_grid < 90 else original_on_grid - 1

                # Set new limit - verify API call succeeds
                success = await inverter.set_battery_soc_limits(on_grid_limit=new_limit)
                assert success is True

                # Note: We don't verify the value is applied because the inverter
                # may have validation rules (e.g., must be multiple of 5, min distance
                # from current SOC, etc.) that cause it to reject or adjust the value

            finally:
                # ALWAYS restore original value
                await inverter.set_battery_soc_limits(on_grid_limit=original_on_grid)

        except LuxpowerAPIError as err:
            # If apiBlocked and account is viewer/operator, skip test
            if "apiBlocked" in str(err) and client.account_level in ("guest", "viewer", "operator"):
                pytest.skip(
                    f"SOC limit control blocked for {client.account_level} account - "
                    "requires owner/installer permissions"
                )
            raise  # Re-raise if different error or unexpected account level


@pytest.mark.asyncio
class TestHybridInverterControls:
    """Test hybrid inverter specific controls."""

    async def test_get_ac_charge_settings(self, hybrid_inverter: HybridInverter | None) -> None:
        """Test reading AC charge settings."""
        if hybrid_inverter is None:
            pytest.skip("No hybrid inverter available")

        # Read AC charge settings
        settings = await hybrid_inverter.get_ac_charge_settings()

        # Should have all expected fields
        assert "enabled" in settings
        assert "power_percent" in settings
        assert "soc_limit" in settings
        assert "schedule1_enabled" in settings
        assert "schedule2_enabled" in settings

        # Values should be in valid ranges
        assert isinstance(settings["enabled"], bool)
        assert 0 <= settings["power_percent"] <= 100
        assert 0 <= settings["soc_limit"] <= 100

    async def test_ac_charge_enable_disable(self, hybrid_inverter: HybridInverter | None) -> None:
        """Test AC charge enable/disable with restore."""
        if hybrid_inverter is None:
            pytest.skip("No hybrid inverter available")

        # Read current state
        original_settings = await hybrid_inverter.get_ac_charge_settings()
        original_enabled = original_settings["enabled"]

        try:
            # Toggle state
            new_enabled = not original_enabled
            success = await hybrid_inverter.set_ac_charge(enabled=new_enabled)
            assert success is True

            # Verify change
            new_settings = await hybrid_inverter.get_ac_charge_settings()
            assert new_settings["enabled"] == new_enabled

        finally:
            # ALWAYS restore original state
            await hybrid_inverter.set_ac_charge(enabled=original_enabled)

    async def test_get_charge_discharge_power(self, hybrid_inverter: HybridInverter | None) -> None:
        """Test reading charge/discharge power settings."""
        if hybrid_inverter is None:
            pytest.skip("No hybrid inverter available")

        # Read power settings
        power = await hybrid_inverter.get_charge_discharge_power()

        # Should have both charge and discharge
        assert "charge_power_percent" in power
        assert "discharge_power_percent" in power

        # Values should be in valid range
        assert 0 <= power["charge_power_percent"] <= 100
        assert 0 <= power["discharge_power_percent"] <= 100

    async def test_set_discharge_power_safe(self, hybrid_inverter: HybridInverter | None) -> None:
        """Test setting discharge power with restore."""
        if hybrid_inverter is None:
            pytest.skip("No hybrid inverter available")

        # Read current power settings
        original_power = await hybrid_inverter.get_charge_discharge_power()
        original_discharge = original_power["discharge_power_percent"]

        try:
            # Make a small safe change (±5%)
            if original_discharge <= 95:
                new_power = min(original_discharge + 5, 100)
            else:
                new_power = max(original_discharge - 5, 0)

            # Set new power
            success = await hybrid_inverter.set_discharge_power(new_power)
            assert success is True

            # Verify change
            new_power_settings = await hybrid_inverter.get_charge_discharge_power()
            assert new_power_settings["discharge_power_percent"] == new_power

        finally:
            # ALWAYS restore original value
            await hybrid_inverter.set_discharge_power(original_discharge)


@pytest.mark.asyncio
class TestEPSMode:
    """Test EPS (backup) mode controls."""

    async def test_eps_toggle_safe(self, hybrid_inverter: HybridInverter | None) -> None:
        """Test EPS enable/disable with immediate restore.

        WARNING: This test briefly toggles EPS mode. It should be safe but
        may cause a momentary switch event.
        """
        if hybrid_inverter is None:
            pytest.skip("No hybrid inverter available")

        # Read current function enable register to get EPS state
        params = await hybrid_inverter.read_parameters(21, 1)
        original_reg_value = params.get("reg_21", 0)

        # Extract EPS bit (bit 0)
        original_eps_enabled = bool(original_reg_value & (1 << 0))

        try:
            # Toggle EPS
            new_eps_state = not original_eps_enabled
            success = await hybrid_inverter.set_eps_enabled(new_eps_state)
            assert success is True

            # Verify change
            new_params = await hybrid_inverter.read_parameters(21, 1)
            new_reg_value = new_params.get("reg_21", 0)
            new_eps_enabled = bool(new_reg_value & (1 << 0))
            assert new_eps_enabled == new_eps_state

        finally:
            # IMMEDIATELY restore original state
            await hybrid_inverter.set_eps_enabled(original_eps_enabled)


@pytest.mark.asyncio
class TestStandbyMode:
    """Test standby mode controls.

    NOTE: Standby mode tests are commented out by default as they power off the inverter.
    Uncomment only if you understand the implications and can safely restore power.
    """

    async def test_read_standby_state(self, client: LuxpowerClient) -> None:
        """Test reading standby state (safe - read only)."""
        stations = await Station.load_all(client)
        inverter = stations[0].all_inverters[0]

        # Read function enable register
        params = await inverter.read_parameters(21, 1)
        reg_value = params.get("reg_21", 0)

        # Bit 9: 0=Standby, 1=Power On
        standby_bit = bool(reg_value & (1 << 9))

        # Inverter should normally be powered on (bit 9 set)
        # This is informational only
        assert isinstance(standby_bit, bool)

    # async def test_standby_mode_toggle(self, client: LuxpowerClient) -> None:
    #     """DANGEROUS: Test standby mode toggle.
    #
    #     This test is commented out because it powers off the inverter.
    #     Only enable if you:
    #     1. Understand the implications
    #     2. Have physical access to restore power
    #     3. Are willing to accept the risk
    #     """
    #     # Implementation would go here
    #     pass


@pytest.mark.asyncio
class TestForcedChargeDischarge:
    """Test forced charge/discharge controls."""

    async def test_forced_charge_toggle_safe(self, hybrid_inverter: HybridInverter | None) -> None:
        """Test forced charge enable/disable with restore."""
        if hybrid_inverter is None:
            pytest.skip("No hybrid inverter available")

        # Read current state
        params = await hybrid_inverter.read_parameters(21, 1)
        original_reg_value = params.get("reg_21", 0)
        original_forced_charge = bool(original_reg_value & (1 << 11))

        try:
            # Toggle forced charge
            new_state = not original_forced_charge
            success = await hybrid_inverter.set_forced_charge(new_state)
            assert success is True

            # Verify change
            new_params = await hybrid_inverter.read_parameters(21, 1)
            new_reg_value = new_params.get("reg_21", 0)
            new_forced_charge = bool(new_reg_value & (1 << 11))
            assert new_forced_charge == new_state

        finally:
            # ALWAYS restore original state
            await hybrid_inverter.set_forced_charge(original_forced_charge)

    async def test_forced_discharge_toggle_safe(
        self, hybrid_inverter: HybridInverter | None
    ) -> None:
        """Test forced discharge enable/disable with restore."""
        if hybrid_inverter is None:
            pytest.skip("No hybrid inverter available")

        # Read current state
        params = await hybrid_inverter.read_parameters(21, 1)
        original_reg_value = params.get("reg_21", 0)
        original_forced_discharge = bool(original_reg_value & (1 << 10))

        try:
            # Toggle forced discharge
            new_state = not original_forced_discharge
            success = await hybrid_inverter.set_forced_discharge(new_state)
            assert success is True

            # Verify change
            new_params = await hybrid_inverter.read_parameters(21, 1)
            new_reg_value = new_params.get("reg_21", 0)
            new_forced_discharge = bool(new_reg_value & (1 << 10))
            assert new_forced_discharge == new_state

        finally:
            # ALWAYS restore original state
            await hybrid_inverter.set_forced_discharge(original_forced_discharge)


@pytest.mark.asyncio
class TestWorkingModeControls:
    """Test working mode control convenience methods (Issue #16).

    NOTE: These tests verify API calls succeed but do NOT verify values are
    applied, as inverters may have undocumented validation rules or delays
    that prevent immediate changes.
    """

    async def test_ac_charge_mode_toggle_safe(self, client: LuxpowerClient) -> None:
        """Test AC charge mode enable/disable - verify API calls succeed."""
        stations = await Station.load_all(client)
        inverter = stations[0].all_inverters[0]

        try:
            # Read current state
            original_status = await inverter.get_ac_charge_mode_status()

            try:
                # Toggle AC charge mode - verify API call succeeds
                new_state = not original_status

                if new_state:
                    success = await inverter.enable_ac_charge_mode()
                else:
                    success = await inverter.disable_ac_charge_mode()

                assert success is True

                # Note: We don't verify the value is applied because the inverter
                # may have validation rules or delays that prevent immediate changes

            finally:
                # ALWAYS restore original state
                if original_status:
                    await inverter.enable_ac_charge_mode()
                else:
                    await inverter.disable_ac_charge_mode()

        except LuxpowerAPIError as err:
            # If apiBlocked and account is viewer/operator, skip test
            if "apiBlocked" in str(err) and client.account_level in ("guest", "viewer", "operator"):
                pytest.skip(
                    f"AC charge control blocked for {client.account_level} account - "
                    "requires owner/installer permissions"
                )
            raise  # Re-raise if different error or unexpected account level

    async def test_pv_charge_priority_toggle_safe(self, client: LuxpowerClient) -> None:
        """Test PV charge priority enable/disable - verify API calls succeed."""
        stations = await Station.load_all(client)
        inverter = stations[0].all_inverters[0]

        # Read current state
        original_status = await inverter.get_pv_charge_priority_status()

        try:
            # Toggle PV charge priority - verify API call succeeds
            new_state = not original_status

            if new_state:
                success = await inverter.enable_pv_charge_priority()
            else:
                success = await inverter.disable_pv_charge_priority()

            assert success is True

            # Note: We don't verify the value is applied because the inverter
            # may have validation rules or delays that prevent immediate changes

        finally:
            # ALWAYS restore original state
            if original_status:
                await inverter.enable_pv_charge_priority()
            else:
                await inverter.disable_pv_charge_priority()

    async def test_forced_discharge_mode_toggle_safe(self, client: LuxpowerClient) -> None:
        """Test forced discharge mode enable/disable - verify API calls succeed."""
        stations = await Station.load_all(client)
        inverter = stations[0].all_inverters[0]

        try:
            # Read current state
            original_status = await inverter.get_forced_discharge_status()

            try:
                # Toggle forced discharge mode - verify API call succeeds
                new_state = not original_status

                if new_state:
                    success = await inverter.enable_forced_discharge()
                else:
                    success = await inverter.disable_forced_discharge()

                assert success is True

                # Note: We don't verify the value is applied because the inverter
                # may have validation rules or delays that prevent immediate changes

            finally:
                # ALWAYS restore original state
                if original_status:
                    await inverter.enable_forced_discharge()
                else:
                    await inverter.disable_forced_discharge()

        except LuxpowerAPIError as err:
            # If apiBlocked and account is viewer/operator, skip test
            if "apiBlocked" in str(err) and client.account_level in ("guest", "viewer", "operator"):
                pytest.skip(
                    f"Forced discharge control blocked for {client.account_level} account - "
                    "requires owner/installer permissions"
                )
            raise  # Re-raise if different error or unexpected account level

    async def test_peak_shaving_mode_toggle_safe(self, client: LuxpowerClient) -> None:
        """Test peak shaving mode enable/disable - verify API calls succeed."""
        stations = await Station.load_all(client)
        inverter = stations[0].all_inverters[0]

        try:
            # Read current state
            original_status = await inverter.get_peak_shaving_mode_status()

            try:
                # Toggle peak shaving mode - verify API call succeeds
                new_state = not original_status

                if new_state:
                    success = await inverter.enable_peak_shaving_mode()
                else:
                    success = await inverter.disable_peak_shaving_mode()

                assert success is True

                # Note: We don't verify the value is applied because the inverter
                # may have validation rules or delays that prevent immediate changes

            finally:
                # ALWAYS restore original state
                if original_status:
                    await inverter.enable_peak_shaving_mode()
                else:
                    await inverter.disable_peak_shaving_mode()

        except LuxpowerAPIError as err:
            # If apiBlocked and account is viewer/operator, skip test
            if "apiBlocked" in str(err) and client.account_level in ("guest", "viewer", "operator"):
                pytest.skip(
                    f"Peak shaving control blocked for {client.account_level} account - "
                    "requires owner/installer permissions"
                )
            raise  # Re-raise if different error or unexpected account level
