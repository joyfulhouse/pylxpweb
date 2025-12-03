"""Unit tests for BaseInverter parameter initialization behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.inverters.base import BaseInverter
from pylxpweb.devices.models import Entity


class ConcreteInverter(BaseInverter):
    """Concrete implementation for testing."""

    def to_entities(self) -> list[Entity]:
        """Generate test entities."""
        return []


@pytest.fixture
def mock_client() -> LuxpowerClient:
    """Create a mock client for testing."""
    client = Mock(spec=LuxpowerClient)
    client.api = Mock()
    client.api.devices = Mock()
    client.api.control = Mock()
    return client


class TestParameterInitialization:
    """Test parameter initialization behavior.

    These tests verify that parameter-based properties return None
    when parameters haven't been loaded yet, preventing Home Assistant
    sensors from initializing with incorrect default values (False/0).
    """

    def test_get_parameter_returns_none_when_unloaded(self, mock_client: LuxpowerClient) -> None:
        """Test that _get_parameter returns None when parameters aren't loaded."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Parameters not loaded yet
        assert inverter.parameters is None

        # Should return None (not default values)
        assert inverter._get_parameter("HOLD_AC_CHARGE_POWER_CMD", 0, int) is None
        assert inverter._get_parameter("HOLD_AC_CHARGE_POWER_CMD", 0.0, float) is None
        assert inverter._get_parameter("FUNC_EPS_EN", False, bool) is None

    def test_get_parameter_returns_value_when_loaded(self, mock_client: LuxpowerClient) -> None:
        """Test that _get_parameter returns actual values when loaded."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Simulate loaded parameters
        inverter.parameters = {
            "HOLD_AC_CHARGE_POWER_CMD": 5000,
            "FUNC_EPS_EN": 1,
            "HOLD_SOC_EMPTY_TO_UTILITY_GRID": 10,
        }

        # Should return actual values
        assert inverter._get_parameter("HOLD_AC_CHARGE_POWER_CMD", 0, int) == 5000
        assert inverter._get_parameter("FUNC_EPS_EN", False, bool) == 1
        assert inverter._get_parameter("HOLD_SOC_EMPTY_TO_UTILITY_GRID", 0, int) == 10

    def test_get_parameter_returns_default_when_key_missing(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test that _get_parameter returns default when key doesn't exist."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Simulate loaded parameters (but without the key we're looking for)
        inverter.parameters = {"OTHER_KEY": 123}

        # Should return default values
        assert inverter._get_parameter("MISSING_KEY", 0, int) == 0
        assert inverter._get_parameter("MISSING_KEY", 99, int) == 99
        assert inverter._get_parameter("MISSING_KEY", False, bool) is False

    def test_properties_return_none_before_parameter_load(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test that parameter-based properties return None before load.

        This is critical for Home Assistant integration - sensors should
        show 'Unknown' state rather than incorrect default values like 'off'.
        """
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Parameters not loaded yet
        assert inverter.parameters is None

        # Properties should return None (which HA interprets as Unknown)
        assert inverter.ac_charge_power_limit is None
        assert inverter.pv_charge_power_limit is None
        assert inverter.ac_charge_soc_limit is None
        assert inverter.system_charge_soc_limit is None
        assert inverter.battery_charge_current_limit is None
        assert inverter.battery_discharge_current_limit is None

    def test_properties_return_values_after_parameter_load(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test that properties return actual values after load."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Simulate loaded parameters
        inverter.parameters = {
            "HOLD_AC_CHARGE_POWER_CMD": 5.0,
            "HOLD_AC_CHARGE_SOC_LIMIT": 80,
            "HOLD_SYSTEM_CHARGE_SOC_LIMIT": 100,
            "HOLD_FORCED_CHG_POWER_CMD": 10,
        }

        # Properties should now return actual values
        assert inverter.ac_charge_power_limit == 5.0
        assert inverter.ac_charge_soc_limit == 80
        assert inverter.system_charge_soc_limit == 100
        assert inverter.pv_charge_power_limit == 10

    @pytest.mark.asyncio
    async def test_parameter_cache_invalidation_after_write(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test that parameter cache time is cleared after write.

        Note: The parameters dict itself is NOT cleared, only the cache time.
        This means properties will continue returning cached values until
        the next refresh() call. This is intentional to avoid returning None
        during the brief period between write and next refresh.
        """
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Simulate loaded parameters with cache time
        from datetime import datetime

        inverter.parameters = {"HOLD_AC_CHARGE_POWER_CMD": 5.0}
        inverter._parameters_cache_time = datetime.now()
        assert inverter.ac_charge_power_limit == 5.0

        # Mock write response
        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        # Write parameters - should invalidate cache TIME (not parameters dict)
        await inverter.write_parameters({21: 6000})

        # Cache time should be None (invalidated)
        assert inverter._parameters_cache_time is None

        # Parameters dict still exists (not cleared)
        assert inverter.parameters is not None

        # Properties still return cached values
        assert inverter.ac_charge_power_limit == 5.0

    def test_bool_parameter_none_vs_false_distinction(self, mock_client: LuxpowerClient) -> None:
        """Test that boolean parameters distinguish None (unloaded) from False.

        This is the core fix for the Home Assistant issue where boolean
        sensors were showing 'off' instead of 'Unknown' on startup.
        """
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Case 1: Parameters not loaded - should return None
        assert inverter.parameters is None
        # Note: BaseInverter doesn't have boolean parameters exposed as properties
        # The _get_parameter method is tested directly above
        assert inverter._get_parameter("FUNC_EPS_EN", False, bool) is None

        # Case 2: Parameters loaded, value is explicitly False (0)
        inverter.parameters = {"FUNC_EPS_EN": 0}
        assert inverter._get_parameter("FUNC_EPS_EN", False, bool) == 0

        # Case 3: Parameters loaded, value is True (1)
        inverter.parameters = {"FUNC_EPS_EN": 1}
        assert inverter._get_parameter("FUNC_EPS_EN", False, bool) == 1

    def test_numeric_parameter_none_vs_zero_distinction(self, mock_client: LuxpowerClient) -> None:
        """Test that numeric parameters distinguish None (unloaded) from 0."""
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Case 1: Parameters not loaded - should return None
        assert inverter.parameters is None
        assert inverter.ac_charge_power_limit is None  # Not 0!

        # Case 2: Parameters loaded, value is explicitly 0
        inverter.parameters = {"HOLD_AC_CHARGE_POWER_CMD": 0.0}
        assert inverter.ac_charge_power_limit == 0.0  # Now it's 0

        # Case 3: Parameters loaded, value is non-zero
        inverter.parameters = {"HOLD_AC_CHARGE_POWER_CMD": 5.0}
        assert inverter.ac_charge_power_limit == 5.0

    def test_system_charge_soc_limit_property(self, mock_client: LuxpowerClient) -> None:
        """Test system_charge_soc_limit property returns correct values.

        The system charge SOC limit controls when the battery stops charging:
        - 0-100%: Stop charging when battery reaches this SOC
        - 101%: Enable top balancing (full charge with cell balancing)
        """
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Case 1: Parameters not loaded - should return None
        assert inverter.parameters is None
        assert inverter.system_charge_soc_limit is None

        # Case 2: Parameters loaded with normal SOC limit
        inverter.parameters = {"HOLD_SYSTEM_CHARGE_SOC_LIMIT": 80}
        assert inverter.system_charge_soc_limit == 80

        # Case 3: Parameters loaded with top balancing mode (101%)
        inverter.parameters = {"HOLD_SYSTEM_CHARGE_SOC_LIMIT": 101}
        assert inverter.system_charge_soc_limit == 101

        # Case 4: Parameters loaded with 100% (maximum without top balancing)
        inverter.parameters = {"HOLD_SYSTEM_CHARGE_SOC_LIMIT": 100}
        assert inverter.system_charge_soc_limit == 100

        # Case 5: Parameters loaded but key missing - should return default (100)
        inverter.parameters = {"OTHER_PARAM": 50}
        assert inverter.system_charge_soc_limit == 100  # Default value

    def test_discharge_power_limit_property(self, mock_client: LuxpowerClient) -> None:
        """Test discharge_power_limit property returns correct values.

        The discharge power limit controls the maximum discharge power as a percentage.
        """
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Case 1: Parameters not loaded - should return None
        assert inverter.parameters is None
        assert inverter.discharge_power_limit is None

        # Case 2: Parameters loaded with discharge power limit
        inverter.parameters = {"HOLD_DISCHG_POWER_PERCENT_CMD": 80}
        assert inverter.discharge_power_limit == 80

        # Case 3: Parameters loaded with 100% (maximum)
        inverter.parameters = {"HOLD_DISCHG_POWER_PERCENT_CMD": 100}
        assert inverter.discharge_power_limit == 100

        # Case 4: Parameters loaded with 0% (minimum)
        inverter.parameters = {"HOLD_DISCHG_POWER_PERCENT_CMD": 0}
        assert inverter.discharge_power_limit == 0

        # Case 5: Parameters loaded but key missing - should return default (100)
        inverter.parameters = {"OTHER_PARAM": 50}
        assert inverter.discharge_power_limit == 100  # Default value

    def test_battery_voltage_limits_property(self, mock_client: LuxpowerClient) -> None:
        """Test battery_voltage_limits property returns correct scaled values.

        Battery voltage values are stored as V * 100 in the API.
        """
        inverter = ConcreteInverter(
            client=mock_client, serial_number="1234567890", model="TestModel"
        )

        # Case 1: Parameters not loaded - should return None
        assert inverter.parameters is None
        assert inverter.battery_voltage_limits is None

        # Case 2: Parameters loaded with all voltage limits
        inverter.parameters = {
            "HOLD_BAT_VOLT_MAX_CHG": 5840,  # 58.4V
            "HOLD_BAT_VOLT_MIN_CHG": 4800,  # 48.0V
            "HOLD_BAT_VOLT_MAX_DISCHG": 5760,  # 57.6V
            "HOLD_BAT_VOLT_MIN_DISCHG": 4600,  # 46.0V
        }
        limits = inverter.battery_voltage_limits
        assert limits is not None
        assert limits["max_charge_voltage"] == 58.4
        assert limits["min_charge_voltage"] == 48.0
        assert limits["max_discharge_voltage"] == 57.6
        assert limits["min_discharge_voltage"] == 46.0

        # Case 3: Parameters partially loaded - should return None
        inverter.parameters = {
            "HOLD_BAT_VOLT_MAX_CHG": 5840,
            "HOLD_BAT_VOLT_MIN_CHG": 4800,
            # Missing discharge voltage params
        }
        assert inverter.battery_voltage_limits is None
