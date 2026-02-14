"""Unit tests for control endpoint helper methods."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.endpoints.control import ControlEndpoints
from pylxpweb.models import ParameterReadResponse, SuccessResponse

SERIAL = "1234567890"


@pytest.fixture
def control() -> ControlEndpoints:
    """Create a ControlEndpoints instance with a mocked client."""
    return ControlEndpoints(Mock(spec=LuxpowerClient))


# ============================================================================
# Convenience method tests (enable/disable wrappers around control_function)
# ============================================================================


class TestFunctionToggleHelpers:
    """Test enable/disable convenience methods that wrap control_function.

    Each parametrized case verifies that the convenience method delegates
    to control_function with the correct function parameter and enable flag.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method_name", "func_param", "enable"),
        [
            ("enable_battery_backup", "FUNC_EPS_EN", True),
            ("disable_battery_backup", "FUNC_EPS_EN", False),
            ("enable_battery_backup_ctrl", "FUNC_BATTERY_BACKUP_CTRL", True),
            ("disable_battery_backup_ctrl", "FUNC_BATTERY_BACKUP_CTRL", False),
            ("enable_normal_mode", "FUNC_SET_TO_STANDBY", True),
            ("enable_standby_mode", "FUNC_SET_TO_STANDBY", False),
            ("enable_grid_peak_shaving", "FUNC_GRID_PEAK_SHAVING", True),
            ("disable_grid_peak_shaving", "FUNC_GRID_PEAK_SHAVING", False),
            ("enable_ac_charge_mode", "FUNC_AC_CHARGE", True),
            ("disable_ac_charge_mode", "FUNC_AC_CHARGE", False),
            ("enable_pv_charge_priority", "FUNC_FORCED_CHG_EN", True),
            ("disable_pv_charge_priority", "FUNC_FORCED_CHG_EN", False),
            ("enable_forced_discharge", "FUNC_FORCED_DISCHG_EN", True),
            ("disable_forced_discharge", "FUNC_FORCED_DISCHG_EN", False),
            ("enable_peak_shaving_mode", "FUNC_GRID_PEAK_SHAVING", True),
            ("disable_peak_shaving_mode", "FUNC_GRID_PEAK_SHAVING", False),
            ("enable_green_mode", "FUNC_GREEN_EN", True),
            ("disable_green_mode", "FUNC_GREEN_EN", False),
            ("enable_sporadic_charge", "FUNC_SPORADIC_CHARGE", True),
            ("disable_sporadic_charge", "FUNC_SPORADIC_CHARGE", False),
        ],
    )
    async def test_toggle_delegates_to_control_function(
        self, control: ControlEndpoints, method_name: str, func_param: str, enable: bool
    ) -> None:
        """Verify convenience method delegates to control_function correctly."""
        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        result = await getattr(control, method_name)(SERIAL)

        control.control_function.assert_called_once_with(
            SERIAL, func_param, enable, client_type="WEB"
        )
        assert result.success is True


# ============================================================================
# Function status tests (get_*_status wrappers around read_parameters)
# ============================================================================


class TestFunctionStatusHelpers:
    """Test get_*_status methods that read a register and extract a bool flag.

    Each parametrized case verifies the correct register and parameter key.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method_name", "register", "param_key"),
        [
            ("get_battery_backup_status", 21, "FUNC_EPS_EN"),
            ("get_ac_charge_mode_status", 21, "FUNC_AC_CHARGE"),
            ("get_pv_charge_priority_status", 21, "FUNC_FORCED_CHG_EN"),
            ("get_forced_discharge_status", 21, "FUNC_FORCED_DISCHG_EN"),
            ("get_peak_shaving_mode_status", 21, "FUNC_GRID_PEAK_SHAVING"),
            ("get_green_mode_status", 110, "FUNC_GREEN_EN"),
            ("get_sporadic_charge_status", 233, "FUNC_SPORADIC_CHARGE"),
        ],
    )
    async def test_status_enabled(
        self, control: ControlEndpoints, method_name: str, register: int, param_key: str
    ) -> None:
        """Verify status method returns True when function is enabled."""
        mock_params = Mock(spec=ParameterReadResponse)
        mock_params.parameters = {param_key: True}
        control.read_parameters = AsyncMock(return_value=mock_params)

        status = await getattr(control, method_name)(SERIAL)

        control.read_parameters.assert_called_once_with(SERIAL, register, 1)
        assert status is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method_name", "register", "param_key"),
        [
            ("get_battery_backup_status", 21, "FUNC_EPS_EN"),
            ("get_green_mode_status", 110, "FUNC_GREEN_EN"),
            ("get_sporadic_charge_status", 233, "FUNC_SPORADIC_CHARGE"),
        ],
    )
    async def test_status_disabled(
        self, control: ControlEndpoints, method_name: str, register: int, param_key: str
    ) -> None:
        """Verify status method returns False when function is disabled."""
        mock_params = Mock(spec=ParameterReadResponse)
        mock_params.parameters = {param_key: False}
        control.read_parameters = AsyncMock(return_value=mock_params)

        status = await getattr(control, method_name)(SERIAL)
        assert status is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "method_name",
        [
            "get_battery_backup_status",
            "get_green_mode_status",
        ],
    )
    async def test_status_missing_field_defaults_false(
        self, control: ControlEndpoints, method_name: str
    ) -> None:
        """Verify status method defaults to False when parameter key is absent."""
        mock_params = Mock(spec=ParameterReadResponse)
        mock_params.parameters = {}
        control.read_parameters = AsyncMock(return_value=mock_params)

        status = await getattr(control, method_name)(SERIAL)
        assert status is False


class TestBulkParameterRead:
    """Test bulk parameter reading method."""

    @pytest.mark.asyncio
    async def test_read_device_parameters_ranges(self, control: ControlEndpoints) -> None:
        """Test reading all parameter ranges concurrently."""
        mock_range1 = Mock(spec=ParameterReadResponse)
        mock_range1.parameters = {"HOLD_AC_CHARGE_POWER_CMD": 50, "FUNC_EPS_EN": True}

        mock_range2 = Mock(spec=ParameterReadResponse)
        mock_range2.parameters = {"HOLD_SYSTEM_CHARGE_SOC_LIMIT": 90}

        mock_range3 = Mock(spec=ParameterReadResponse)
        mock_range3.parameters = {"HOLD_DISCHG_POWER_CMD": 80}

        control.read_parameters = AsyncMock(side_effect=[mock_range1, mock_range2, mock_range3])

        combined = await control.read_device_parameters_ranges(SERIAL)

        assert control.read_parameters.call_count == 3
        control.read_parameters.assert_any_call(SERIAL, 0, 127)
        control.read_parameters.assert_any_call(SERIAL, 127, 127)
        control.read_parameters.assert_any_call(SERIAL, 240, 127)

        assert combined["HOLD_AC_CHARGE_POWER_CMD"] == 50
        assert combined["FUNC_EPS_EN"] is True
        assert combined["HOLD_SYSTEM_CHARGE_SOC_LIMIT"] == 90
        assert combined["HOLD_DISCHG_POWER_CMD"] == 80

    @pytest.mark.asyncio
    async def test_read_device_parameters_ranges_with_errors(
        self, control: ControlEndpoints
    ) -> None:
        """Test handling errors in bulk parameter read."""
        mock_range1 = Mock(spec=ParameterReadResponse)
        mock_range1.parameters = {"HOLD_AC_CHARGE_POWER_CMD": 50}

        control.read_parameters = AsyncMock(
            side_effect=[mock_range1, Exception("Network error"), mock_range1]
        )

        combined = await control.read_device_parameters_ranges(SERIAL)

        assert "HOLD_AC_CHARGE_POWER_CMD" in combined
        assert len(combined) > 0


class TestCacheInvalidation:
    """Test cache invalidation on write operations."""

    @pytest.fixture
    def api_client(self) -> Mock:
        """Create a mock client with API-level mocks for cache invalidation tests."""
        client = Mock(spec=LuxpowerClient)
        client._ensure_authenticated = AsyncMock()
        client.invalidate_cache_for_device = Mock()
        return client

    @pytest.mark.asyncio
    async def test_write_parameter_invalidates_cache(self, api_client: Mock) -> None:
        """Test that write_parameter invalidates cache on successful write."""
        api_client._request = AsyncMock(return_value={"success": True})
        control = ControlEndpoints(api_client)

        result = await control.write_parameter(SERIAL, "HOLD_SYSTEM_CHARGE_SOC_LIMIT", "90")

        assert result.success is True
        api_client.invalidate_cache_for_device.assert_called_once_with(SERIAL)

    @pytest.mark.asyncio
    async def test_write_parameter_no_cache_invalidation_on_failure(self, api_client: Mock) -> None:
        """Test that write_parameter does NOT invalidate cache on failure."""
        api_client._request = AsyncMock(return_value={"success": False})
        control = ControlEndpoints(api_client)

        result = await control.write_parameter(SERIAL, "HOLD_SYSTEM_CHARGE_SOC_LIMIT", "90")

        assert result.success is False
        api_client.invalidate_cache_for_device.assert_not_called()

    @pytest.mark.asyncio
    async def test_control_function_invalidates_cache(self, api_client: Mock) -> None:
        """Test that control_function invalidates cache on successful operation."""
        api_client._request = AsyncMock(return_value={"success": True})
        control = ControlEndpoints(api_client)

        result = await control.control_function(SERIAL, "FUNC_EPS_EN", True)

        assert result.success is True
        api_client.invalidate_cache_for_device.assert_called_once_with(SERIAL)

    @pytest.mark.asyncio
    async def test_write_parameters_invalidates_cache(self, api_client: Mock) -> None:
        """Test that write_parameters invalidates cache on successful write."""
        api_client._request = AsyncMock(return_value={"success": True})
        control = ControlEndpoints(api_client)

        result = await control.write_parameters(SERIAL, {21: 512})

        assert result.success is True
        api_client.invalidate_cache_for_device.assert_called_once_with(SERIAL)

    @pytest.mark.asyncio
    async def test_write_parameters_sends_all_registers(self, api_client: Mock) -> None:
        """Test that write_parameters sends all registers in data dict."""
        api_client._request = AsyncMock(return_value={"success": True})
        control = ControlEndpoints(api_client)

        result = await control.write_parameters(SERIAL, {160: 20, 67: 100})

        assert result.success is True
        call_data = api_client._request.call_args[1]["data"]
        assert call_data["data"] == {"160": 20, "67": 100}


class TestSystemChargeSocLimit:
    """Test system charge SOC limit convenience methods."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("percent", "expected_value_str"),
        [
            (90, "90"),
            (101, "101"),
            (0, "0"),
        ],
        ids=["normal_90", "top_balance_101", "zero"],
    )
    async def test_set_system_charge_soc_limit_valid(
        self, control: ControlEndpoints, percent: int, expected_value_str: str
    ) -> None:
        """Test setting system charge SOC limit to valid values."""
        control.write_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        result = await control.set_system_charge_soc_limit(SERIAL, percent)

        control.write_parameter.assert_called_once_with(
            SERIAL, "HOLD_SYSTEM_CHARGE_SOC_LIMIT", expected_value_str
        )
        assert result.success is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("percent", [102, -1], ids=["too_high", "negative"])
    async def test_set_system_charge_soc_limit_invalid(
        self, control: ControlEndpoints, percent: int
    ) -> None:
        """Test that out-of-range values raise ValueError."""
        with pytest.raises(ValueError, match="0-101%"):
            await control.set_system_charge_soc_limit(SERIAL, percent)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("params", "expected"),
        [
            ({"HOLD_SYSTEM_CHARGE_SOC_LIMIT": 90}, 90),
            ({"HOLD_SYSTEM_CHARGE_SOC_LIMIT": 101}, 101),
            ({}, 100),
        ],
        ids=["normal", "top_balance", "default_100"],
    )
    async def test_get_system_charge_soc_limit(
        self, control: ControlEndpoints, params: dict[str, int], expected: int
    ) -> None:
        """Test getting current system charge SOC limit."""
        control.read_device_parameters_ranges = AsyncMock(return_value=params)

        limit = await control.get_system_charge_soc_limit(SERIAL)

        control.read_device_parameters_ranges.assert_called_once_with(SERIAL)
        assert limit == expected


class TestACChargeScheduleCloud:
    """Test AC charge schedule cloud API methods."""

    @pytest.mark.asyncio
    async def test_set_ac_charge_schedule_period_0(self, control: ControlEndpoints) -> None:
        """Test setting AC charge schedule for period 0 (unsuffixed params)."""
        control.write_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        result = await control.set_ac_charge_schedule(SERIAL, 0, 23, 0, 7, 0)

        assert result.success is True
        assert control.write_parameter.call_count == 4
        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_CHARGE_START_HOUR", "23", client_type="WEB"
        )
        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_CHARGE_START_MINUTE", "0", client_type="WEB"
        )
        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_CHARGE_END_HOUR", "7", client_type="WEB"
        )
        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_CHARGE_END_MINUTE", "0", client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_set_ac_charge_schedule_period_1(self, control: ControlEndpoints) -> None:
        """Test setting AC charge schedule for period 1 (_1 suffix)."""
        control.write_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        await control.set_ac_charge_schedule(SERIAL, 1, 8, 30, 16, 0)

        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_CHARGE_START_HOUR_1", "8", client_type="WEB"
        )
        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_CHARGE_END_MINUTE_1", "0", client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_set_ac_charge_schedule_invalid_period(self, control: ControlEndpoints) -> None:
        """Test that invalid period raises ValueError."""
        with pytest.raises(ValueError, match="period must be 0, 1, or 2"):
            await control.set_ac_charge_schedule(SERIAL, 3, 0, 0, 0, 0)

    @pytest.mark.asyncio
    async def test_set_ac_charge_schedule_invalid_hour(self, control: ControlEndpoints) -> None:
        """Test that invalid hour raises ValueError."""
        with pytest.raises(ValueError, match="start_hour must be 0-23"):
            await control.set_ac_charge_schedule(SERIAL, 0, 24, 0, 7, 0)

    @pytest.mark.asyncio
    async def test_get_ac_charge_schedule(self, control: ControlEndpoints) -> None:
        """Test getting AC charge schedule via cloud API."""
        control.read_device_parameters_ranges = AsyncMock(
            return_value={
                "HOLD_AC_CHARGE_START_HOUR": 23,
                "HOLD_AC_CHARGE_START_MINUTE": 0,
                "HOLD_AC_CHARGE_END_HOUR": 7,
                "HOLD_AC_CHARGE_END_MINUTE": 0,
            }
        )

        schedule = await control.get_ac_charge_schedule(SERIAL, 0)

        assert schedule == {
            "start_hour": 23,
            "start_minute": 0,
            "end_hour": 7,
            "end_minute": 0,
        }


class TestACChargeTypeCloud:
    """Test AC charge type cloud API methods."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("charge_type", [0, 1, 2], ids=["time", "soc_volt", "time_soc_volt"])
    async def test_set_ac_charge_type_valid(
        self, control: ControlEndpoints, charge_type: int
    ) -> None:
        """Test setting AC charge type to valid values."""
        control.control_bit_param = AsyncMock(return_value=SuccessResponse(success=True))

        result = await control.set_ac_charge_type(SERIAL, charge_type)

        control.control_bit_param.assert_called_once_with(
            SERIAL, "BIT_AC_CHARGE_TYPE", charge_type, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_set_ac_charge_type_invalid(self, control: ControlEndpoints) -> None:
        """Test that invalid charge type raises ValueError."""
        with pytest.raises(ValueError, match="charge_type must be 0, 1, or 2"):
            await control.set_ac_charge_type(SERIAL, 5)

    @pytest.mark.asyncio
    async def test_get_ac_charge_type(self, control: ControlEndpoints) -> None:
        """Test getting AC charge type via cloud API."""
        control.read_device_parameters_ranges = AsyncMock(return_value={"BIT_AC_CHARGE_TYPE": 2})

        charge_type = await control.get_ac_charge_type(SERIAL)
        assert charge_type == 2


class TestACChargeSocLimitsCloud:
    """Test AC charge SOC limit cloud API methods."""

    @pytest.mark.asyncio
    async def test_set_ac_charge_soc_limits(self, control: ControlEndpoints) -> None:
        """Test setting AC charge SOC limits."""
        control.write_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        result = await control.set_ac_charge_soc_limits(SERIAL, 20, 100)

        assert result.success is True
        assert control.write_parameter.call_count == 2
        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_CHARGE_START_BATTERY_SOC", "20", client_type="WEB"
        )
        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_CHARGE_SOC_LIMIT", "100", client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_set_ac_charge_soc_limits_invalid_start(self, control: ControlEndpoints) -> None:
        """Test that invalid start_soc raises ValueError."""
        with pytest.raises(ValueError, match="start_soc must be 0-90"):
            await control.set_ac_charge_soc_limits(SERIAL, 95, 100)

    @pytest.mark.asyncio
    async def test_get_ac_charge_soc_limits(self, control: ControlEndpoints) -> None:
        """Test getting AC charge SOC limits."""
        control.read_device_parameters_ranges = AsyncMock(
            return_value={
                "HOLD_AC_CHARGE_START_BATTERY_SOC": 20,
                "HOLD_AC_CHARGE_SOC_LIMIT": 100,
            }
        )

        limits = await control.get_ac_charge_soc_limits(SERIAL)
        assert limits == {"start_soc": 20, "end_soc": 100}


class TestACChargeVoltageLimitsCloud:
    """Test AC charge voltage limit cloud API methods."""

    @pytest.mark.asyncio
    async def test_set_ac_charge_voltage_limits(self, control: ControlEndpoints) -> None:
        """Test setting AC charge voltage limits (decivolts conversion)."""
        control.write_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        result = await control.set_ac_charge_voltage_limits(SERIAL, 40, 58)

        assert result.success is True
        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_CHARGE_START_BATTERY_VOLTAGE", "400", client_type="WEB"
        )
        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_CHARGE_END_BATTERY_VOLTAGE", "580", client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_set_ac_charge_voltage_limits_invalid_start(
        self, control: ControlEndpoints
    ) -> None:
        """Test that invalid start_voltage raises ValueError."""
        with pytest.raises(ValueError, match="start_voltage must be 39-52V"):
            await control.set_ac_charge_voltage_limits(SERIAL, 30, 58)

    @pytest.mark.asyncio
    async def test_get_ac_charge_voltage_limits(self, control: ControlEndpoints) -> None:
        """Test getting AC charge voltage limits (decivolts conversion)."""
        control.read_device_parameters_ranges = AsyncMock(
            return_value={
                "HOLD_AC_CHARGE_START_BATTERY_VOLTAGE": 400,
                "HOLD_AC_CHARGE_END_BATTERY_VOLTAGE": 580,
            }
        )

        limits = await control.get_ac_charge_voltage_limits(SERIAL)
        assert limits == {"start_voltage": 40, "end_voltage": 58}
