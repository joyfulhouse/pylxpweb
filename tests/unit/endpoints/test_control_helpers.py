"""Unit tests for control endpoint helper methods."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.models import ParameterReadResponse, SuccessResponse


@pytest.fixture
def mock_client() -> LuxpowerClient:
    """Create a mock client for testing."""
    client = Mock(spec=LuxpowerClient)
    client.api = Mock()
    client.api.control = Mock()
    return client


class TestBatteryBackupHelpers:
    """Test battery backup (EPS) convenience methods."""

    @pytest.mark.asyncio
    async def test_enable_battery_backup(self) -> None:
        """Test enable_battery_backup convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock control_function
        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        # Call convenience method
        result = await control.enable_battery_backup("1234567890")

        # Verify control_function was called correctly
        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_EPS_EN", True, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_disable_battery_backup(self) -> None:
        """Test disable_battery_backup convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock control_function
        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        # Call convenience method
        result = await control.disable_battery_backup("1234567890")

        # Verify control_function was called correctly
        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_EPS_EN", False, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_get_battery_backup_status(self) -> None:
        """Test get_battery_backup_status method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock read_parameters response
        mock_params = Mock(spec=ParameterReadResponse)
        mock_params.parameters = {"FUNC_EPS_EN": True}
        control.read_parameters = AsyncMock(return_value=mock_params)

        # Get status
        status = await control.get_battery_backup_status("1234567890")

        # Verify read_parameters was called
        control.read_parameters.assert_called_once_with("1234567890", 21, 1)
        assert status is True

    @pytest.mark.asyncio
    async def test_get_battery_backup_status_disabled(self) -> None:
        """Test get_battery_backup_status when EPS is disabled."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock read_parameters response
        mock_params = Mock(spec=ParameterReadResponse)
        mock_params.parameters = {"FUNC_EPS_EN": False}
        control.read_parameters = AsyncMock(return_value=mock_params)

        # Get status
        status = await control.get_battery_backup_status("1234567890")

        assert status is False

    @pytest.mark.asyncio
    async def test_get_battery_backup_status_missing_field(self) -> None:
        """Test get_battery_backup_status when field is missing."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock read_parameters response without FUNC_EPS_EN
        mock_params = Mock(spec=ParameterReadResponse)
        mock_params.parameters = {}
        control.read_parameters = AsyncMock(return_value=mock_params)

        # Get status (should default to False)
        status = await control.get_battery_backup_status("1234567890")

        assert status is False


class TestStandbyModeHelpers:
    """Test standby mode convenience methods."""

    @pytest.mark.asyncio
    async def test_enable_normal_mode(self) -> None:
        """Test enable_normal_mode convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock control_function
        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        # Call convenience method
        result = await control.enable_normal_mode("1234567890")

        # Verify control_function was called correctly
        # Note: FUNC_SET_TO_STANDBY = True means NOT in standby (normal mode)
        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_SET_TO_STANDBY", True, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_enable_standby_mode(self) -> None:
        """Test enable_standby_mode convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock control_function
        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        # Call convenience method
        result = await control.enable_standby_mode("1234567890")

        # Verify control_function was called correctly
        # Note: FUNC_SET_TO_STANDBY = False means standby mode is active
        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_SET_TO_STANDBY", False, client_type="WEB"
        )
        assert result.success is True


class TestPeakShavingHelpers:
    """Test grid peak shaving convenience methods."""

    @pytest.mark.asyncio
    async def test_enable_grid_peak_shaving(self) -> None:
        """Test enable_grid_peak_shaving convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock control_function
        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        # Call convenience method
        result = await control.enable_grid_peak_shaving("1234567890")

        # Verify control_function was called correctly
        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_GRID_PEAK_SHAVING", True, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_disable_grid_peak_shaving(self) -> None:
        """Test disable_grid_peak_shaving convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock control_function
        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        # Call convenience method
        result = await control.disable_grid_peak_shaving("1234567890")

        # Verify control_function was called correctly
        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_GRID_PEAK_SHAVING", False, client_type="WEB"
        )
        assert result.success is True


class TestWorkingModeHelpers:
    """Test working mode convenience methods (Issue #16)."""

    # AC Charge Mode tests
    @pytest.mark.asyncio
    async def test_enable_ac_charge_mode(self) -> None:
        """Test enable_ac_charge_mode convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock control_function
        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        # Call convenience method
        result = await control.enable_ac_charge_mode("1234567890")

        # Verify control_function was called correctly
        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_AC_CHARGE", True, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_disable_ac_charge_mode(self) -> None:
        """Test disable_ac_charge_mode convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock control_function
        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        # Call convenience method
        result = await control.disable_ac_charge_mode("1234567890")

        # Verify control_function was called correctly
        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_AC_CHARGE", False, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_get_ac_charge_mode_status(self) -> None:
        """Test get_ac_charge_mode_status method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock read_parameters response
        mock_params = Mock(spec=ParameterReadResponse)
        mock_params.parameters = {"FUNC_AC_CHARGE": True}
        control.read_parameters = AsyncMock(return_value=mock_params)

        # Get status
        status = await control.get_ac_charge_mode_status("1234567890")

        # Verify read_parameters was called
        control.read_parameters.assert_called_once_with("1234567890", 21, 1)
        assert status is True

    # PV Charge Priority tests
    @pytest.mark.asyncio
    async def test_enable_pv_charge_priority(self) -> None:
        """Test enable_pv_charge_priority convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock control_function
        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        # Call convenience method
        result = await control.enable_pv_charge_priority("1234567890")

        # Verify control_function was called correctly
        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_FORCED_CHG_EN", True, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_disable_pv_charge_priority(self) -> None:
        """Test disable_pv_charge_priority convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock control_function
        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        # Call convenience method
        result = await control.disable_pv_charge_priority("1234567890")

        # Verify control_function was called correctly
        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_FORCED_CHG_EN", False, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_get_pv_charge_priority_status(self) -> None:
        """Test get_pv_charge_priority_status method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock read_parameters response
        mock_params = Mock(spec=ParameterReadResponse)
        mock_params.parameters = {"FUNC_FORCED_CHG_EN": True}
        control.read_parameters = AsyncMock(return_value=mock_params)

        # Get status
        status = await control.get_pv_charge_priority_status("1234567890")

        # Verify read_parameters was called
        control.read_parameters.assert_called_once_with("1234567890", 21, 1)
        assert status is True

    # Forced Discharge tests
    @pytest.mark.asyncio
    async def test_enable_forced_discharge(self) -> None:
        """Test enable_forced_discharge convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock control_function
        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        # Call convenience method
        result = await control.enable_forced_discharge("1234567890")

        # Verify control_function was called correctly
        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_FORCED_DISCHG_EN", True, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_disable_forced_discharge(self) -> None:
        """Test disable_forced_discharge convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock control_function
        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        # Call convenience method
        result = await control.disable_forced_discharge("1234567890")

        # Verify control_function was called correctly
        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_FORCED_DISCHG_EN", False, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_get_forced_discharge_status(self) -> None:
        """Test get_forced_discharge_status method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock read_parameters response
        mock_params = Mock(spec=ParameterReadResponse)
        mock_params.parameters = {"FUNC_FORCED_DISCHG_EN": True}
        control.read_parameters = AsyncMock(return_value=mock_params)

        # Get status
        status = await control.get_forced_discharge_status("1234567890")

        # Verify read_parameters was called
        control.read_parameters.assert_called_once_with("1234567890", 21, 1)
        assert status is True

    # Peak Shaving Mode tests (additional to existing tests above)
    @pytest.mark.asyncio
    async def test_enable_peak_shaving_mode(self) -> None:
        """Test enable_peak_shaving_mode convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock control_function
        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        # Call convenience method
        result = await control.enable_peak_shaving_mode("1234567890")

        # Verify control_function was called correctly
        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_GRID_PEAK_SHAVING", True, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_disable_peak_shaving_mode(self) -> None:
        """Test disable_peak_shaving_mode convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock control_function
        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        # Call convenience method
        result = await control.disable_peak_shaving_mode("1234567890")

        # Verify control_function was called correctly
        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_GRID_PEAK_SHAVING", False, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_get_peak_shaving_mode_status(self) -> None:
        """Test get_peak_shaving_mode_status method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock read_parameters response
        mock_params = Mock(spec=ParameterReadResponse)
        mock_params.parameters = {"FUNC_GRID_PEAK_SHAVING": True}
        control.read_parameters = AsyncMock(return_value=mock_params)

        # Get status
        status = await control.get_peak_shaving_mode_status("1234567890")

        # Verify read_parameters was called
        control.read_parameters.assert_called_once_with("1234567890", 21, 1)
        assert status is True


class TestBulkParameterRead:
    """Test bulk parameter reading method."""

    @pytest.mark.asyncio
    async def test_read_device_parameters_ranges(self) -> None:
        """Test reading all parameter ranges concurrently."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock read_parameters for three ranges
        mock_range1 = Mock(spec=ParameterReadResponse)
        mock_range1.parameters = {"HOLD_AC_CHARGE_POWER_CMD": 50, "FUNC_EPS_EN": True}

        mock_range2 = Mock(spec=ParameterReadResponse)
        mock_range2.parameters = {"HOLD_SYSTEM_CHARGE_SOC_LIMIT": 90}

        mock_range3 = Mock(spec=ParameterReadResponse)
        mock_range3.parameters = {"HOLD_DISCHG_POWER_CMD": 80}

        control.read_parameters = AsyncMock(side_effect=[mock_range1, mock_range2, mock_range3])

        # Read all ranges
        combined = await control.read_device_parameters_ranges("1234567890")

        # Verify all three read_parameters calls
        assert control.read_parameters.call_count == 3
        control.read_parameters.assert_any_call("1234567890", 0, 127)
        control.read_parameters.assert_any_call("1234567890", 127, 127)
        control.read_parameters.assert_any_call("1234567890", 240, 127)

        # Verify combined parameters
        assert combined["HOLD_AC_CHARGE_POWER_CMD"] == 50
        assert combined["FUNC_EPS_EN"] is True
        assert combined["HOLD_SYSTEM_CHARGE_SOC_LIMIT"] == 90
        assert combined["HOLD_DISCHG_POWER_CMD"] == 80

    @pytest.mark.asyncio
    async def test_read_device_parameters_ranges_with_errors(self) -> None:
        """Test handling errors in bulk parameter read."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock read_parameters with one error
        mock_range1 = Mock(spec=ParameterReadResponse)
        mock_range1.parameters = {"HOLD_AC_CHARGE_POWER_CMD": 50}

        control.read_parameters = AsyncMock(
            side_effect=[mock_range1, Exception("Network error"), mock_range1]
        )

        # Read all ranges (should not raise exception)
        combined = await control.read_device_parameters_ranges("1234567890")

        # Verify we got data from successful calls only
        assert "HOLD_AC_CHARGE_POWER_CMD" in combined
        assert len(combined) > 0


class TestCacheInvalidation:
    """Test cache invalidation on write operations."""

    @pytest.mark.asyncio
    async def test_write_parameter_invalidates_cache(self) -> None:
        """Test that write_parameter invalidates cache on successful write."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        mock_client._ensure_authenticated = AsyncMock()
        mock_client._request = AsyncMock(return_value={"success": True})
        mock_client.invalidate_cache_for_device = Mock()

        control = ControlEndpoints(mock_client)

        # Write parameter
        result = await control.write_parameter("1234567890", "HOLD_SYSTEM_CHARGE_SOC_LIMIT", "90")

        # Verify cache was invalidated
        assert result.success is True
        mock_client.invalidate_cache_for_device.assert_called_once_with("1234567890")

    @pytest.mark.asyncio
    async def test_write_parameter_no_cache_invalidation_on_failure(self) -> None:
        """Test that write_parameter does NOT invalidate cache on failure."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        mock_client._ensure_authenticated = AsyncMock()
        mock_client._request = AsyncMock(return_value={"success": False})
        mock_client.invalidate_cache_for_device = Mock()

        control = ControlEndpoints(mock_client)

        # Write parameter (fails)
        result = await control.write_parameter("1234567890", "HOLD_SYSTEM_CHARGE_SOC_LIMIT", "90")

        # Verify cache was NOT invalidated
        assert result.success is False
        mock_client.invalidate_cache_for_device.assert_not_called()

    @pytest.mark.asyncio
    async def test_control_function_invalidates_cache(self) -> None:
        """Test that control_function invalidates cache on successful operation."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        mock_client._ensure_authenticated = AsyncMock()
        mock_client._request = AsyncMock(return_value={"success": True})
        mock_client.invalidate_cache_for_device = Mock()

        control = ControlEndpoints(mock_client)

        # Call control_function
        result = await control.control_function("1234567890", "FUNC_EPS_EN", True)

        # Verify cache was invalidated
        assert result.success is True
        mock_client.invalidate_cache_for_device.assert_called_once_with("1234567890")

    @pytest.mark.asyncio
    async def test_write_parameters_invalidates_cache(self) -> None:
        """Test that write_parameters invalidates cache on successful write."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        mock_client._ensure_authenticated = AsyncMock()
        mock_client._request = AsyncMock(return_value={"success": True})
        mock_client.invalidate_cache_for_device = Mock()

        control = ControlEndpoints(mock_client)

        # Write parameters
        result = await control.write_parameters("1234567890", {21: 512})

        # Verify cache was invalidated
        assert result.success is True
        mock_client.invalidate_cache_for_device.assert_called_once_with("1234567890")


class TestSystemChargeSocLimit:
    """Test system charge SOC limit convenience methods."""

    @pytest.mark.asyncio
    async def test_set_system_charge_soc_limit_normal(self) -> None:
        """Test setting system charge SOC limit to normal value."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock write_parameter
        mock_response = SuccessResponse(success=True)
        control.write_parameter = AsyncMock(return_value=mock_response)

        # Set SOC limit to 90%
        result = await control.set_system_charge_soc_limit("1234567890", 90)

        # Verify write_parameter was called correctly
        control.write_parameter.assert_called_once_with(
            "1234567890", "HOLD_SYSTEM_CHARGE_SOC_LIMIT", "90"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_set_system_charge_soc_limit_top_balance(self) -> None:
        """Test setting system charge SOC limit to 101 for top balancing."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock write_parameter
        mock_response = SuccessResponse(success=True)
        control.write_parameter = AsyncMock(return_value=mock_response)

        # Set SOC limit to 101% (top balancing)
        result = await control.set_system_charge_soc_limit("1234567890", 101)

        # Verify write_parameter was called correctly
        control.write_parameter.assert_called_once_with(
            "1234567890", "HOLD_SYSTEM_CHARGE_SOC_LIMIT", "101"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_set_system_charge_soc_limit_zero(self) -> None:
        """Test setting system charge SOC limit to 0%."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock write_parameter
        mock_response = SuccessResponse(success=True)
        control.write_parameter = AsyncMock(return_value=mock_response)

        # Set SOC limit to 0%
        result = await control.set_system_charge_soc_limit("1234567890", 0)

        # Verify write_parameter was called correctly
        control.write_parameter.assert_called_once_with(
            "1234567890", "HOLD_SYSTEM_CHARGE_SOC_LIMIT", "0"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_set_system_charge_soc_limit_invalid_high(self) -> None:
        """Test that values above 101 raise ValueError."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Attempt to set invalid value
        with pytest.raises(ValueError) as exc_info:
            await control.set_system_charge_soc_limit("1234567890", 102)

        assert "0-101%" in str(exc_info.value)
        assert "102" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_set_system_charge_soc_limit_invalid_negative(self) -> None:
        """Test that negative values raise ValueError."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Attempt to set invalid value
        with pytest.raises(ValueError) as exc_info:
            await control.set_system_charge_soc_limit("1234567890", -1)

        assert "0-101%" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_system_charge_soc_limit(self) -> None:
        """Test getting current system charge SOC limit."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock read_device_parameters_ranges
        control.read_device_parameters_ranges = AsyncMock(
            return_value={"HOLD_SYSTEM_CHARGE_SOC_LIMIT": 90}
        )

        # Get SOC limit
        limit = await control.get_system_charge_soc_limit("1234567890")

        # Verify
        control.read_device_parameters_ranges.assert_called_once_with("1234567890")
        assert limit == 90

    @pytest.mark.asyncio
    async def test_get_system_charge_soc_limit_top_balance(self) -> None:
        """Test getting system charge SOC limit when set to 101 (top balancing)."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock read_device_parameters_ranges
        control.read_device_parameters_ranges = AsyncMock(
            return_value={"HOLD_SYSTEM_CHARGE_SOC_LIMIT": 101}
        )

        # Get SOC limit
        limit = await control.get_system_charge_soc_limit("1234567890")

        assert limit == 101

    @pytest.mark.asyncio
    async def test_get_system_charge_soc_limit_default(self) -> None:
        """Test getting system charge SOC limit defaults to 100 if not present."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock read_device_parameters_ranges without the parameter
        control.read_device_parameters_ranges = AsyncMock(return_value={})

        # Get SOC limit
        limit = await control.get_system_charge_soc_limit("1234567890")

        assert limit == 100


class TestGreenModeHelpers:
    """Test green mode (off-grid mode) convenience methods."""

    @pytest.mark.asyncio
    async def test_enable_green_mode(self) -> None:
        """Test enable_green_mode convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock control_function
        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        # Call convenience method
        result = await control.enable_green_mode("1234567890")

        # Verify control_function was called correctly
        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_GREEN_EN", True, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_disable_green_mode(self) -> None:
        """Test disable_green_mode convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock control_function
        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        # Call convenience method
        result = await control.disable_green_mode("1234567890")

        # Verify control_function was called correctly
        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_GREEN_EN", False, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_get_green_mode_status_enabled(self) -> None:
        """Test get_green_mode_status when enabled."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock read_parameters response
        mock_params = Mock(spec=ParameterReadResponse)
        mock_params.parameters = {"FUNC_GREEN_EN": True}
        control.read_parameters = AsyncMock(return_value=mock_params)

        # Get status
        status = await control.get_green_mode_status("1234567890")

        # Verify read_parameters was called with register 110 (system functions)
        control.read_parameters.assert_called_once_with("1234567890", 110, 1)
        assert status is True

    @pytest.mark.asyncio
    async def test_get_green_mode_status_disabled(self) -> None:
        """Test get_green_mode_status when disabled."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock read_parameters response
        mock_params = Mock(spec=ParameterReadResponse)
        mock_params.parameters = {"FUNC_GREEN_EN": False}
        control.read_parameters = AsyncMock(return_value=mock_params)

        # Get status
        status = await control.get_green_mode_status("1234567890")

        assert status is False

    @pytest.mark.asyncio
    async def test_get_green_mode_status_missing_field(self) -> None:
        """Test get_green_mode_status when field is missing (defaults to False)."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        # Mock read_parameters response without FUNC_GREEN_EN
        mock_params = Mock(spec=ParameterReadResponse)
        mock_params.parameters = {}
        control.read_parameters = AsyncMock(return_value=mock_params)

        # Get status (should default to False)
        status = await control.get_green_mode_status("1234567890")

        assert status is False


class TestACChargeScheduleCloud:
    """Test AC charge schedule cloud API methods."""

    @pytest.mark.asyncio
    async def test_set_ac_charge_schedule_period_0(self) -> None:
        """Test setting AC charge schedule for period 0 (unsuffixed params)."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        mock_response = SuccessResponse(success=True)
        control.write_parameter = AsyncMock(return_value=mock_response)

        result = await control.set_ac_charge_schedule("1234567890", 0, 23, 0, 7, 0)

        assert result.success is True
        assert control.write_parameter.call_count == 4
        control.write_parameter.assert_any_call(
            "1234567890", "HOLD_AC_CHARGE_START_HOUR", "23", client_type="WEB"
        )
        control.write_parameter.assert_any_call(
            "1234567890", "HOLD_AC_CHARGE_START_MINUTE", "0", client_type="WEB"
        )
        control.write_parameter.assert_any_call(
            "1234567890", "HOLD_AC_CHARGE_END_HOUR", "7", client_type="WEB"
        )
        control.write_parameter.assert_any_call(
            "1234567890", "HOLD_AC_CHARGE_END_MINUTE", "0", client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_set_ac_charge_schedule_period_1(self) -> None:
        """Test setting AC charge schedule for period 1 (_1 suffix)."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        mock_response = SuccessResponse(success=True)
        control.write_parameter = AsyncMock(return_value=mock_response)

        await control.set_ac_charge_schedule("1234567890", 1, 8, 30, 16, 0)

        control.write_parameter.assert_any_call(
            "1234567890", "HOLD_AC_CHARGE_START_HOUR_1", "8", client_type="WEB"
        )
        control.write_parameter.assert_any_call(
            "1234567890", "HOLD_AC_CHARGE_END_MINUTE_1", "0", client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_set_ac_charge_schedule_invalid_period(self) -> None:
        """Test that invalid period raises ValueError."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        with pytest.raises(ValueError, match="period must be 0, 1, or 2"):
            await control.set_ac_charge_schedule("1234567890", 3, 0, 0, 0, 0)

    @pytest.mark.asyncio
    async def test_set_ac_charge_schedule_invalid_hour(self) -> None:
        """Test that invalid hour raises ValueError."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        with pytest.raises(ValueError, match="start_hour must be 0-23"):
            await control.set_ac_charge_schedule("1234567890", 0, 24, 0, 7, 0)

    @pytest.mark.asyncio
    async def test_get_ac_charge_schedule(self) -> None:
        """Test getting AC charge schedule via cloud API."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        control.read_device_parameters_ranges = AsyncMock(return_value={
            "HOLD_AC_CHARGE_START_HOUR": 23,
            "HOLD_AC_CHARGE_START_MINUTE": 0,
            "HOLD_AC_CHARGE_END_HOUR": 7,
            "HOLD_AC_CHARGE_END_MINUTE": 0,
        })

        schedule = await control.get_ac_charge_schedule("1234567890", 0)

        assert schedule == {
            "start_hour": 23, "start_minute": 0,
            "end_hour": 7, "end_minute": 0,
        }


class TestACChargeTypeCloud:
    """Test AC charge type cloud API methods."""

    @pytest.mark.asyncio
    async def test_set_ac_charge_type_time(self) -> None:
        """Test setting AC charge type to time-based."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        mock_response = SuccessResponse(success=True)
        control.control_bit_param = AsyncMock(return_value=mock_response)

        result = await control.set_ac_charge_type("1234567890", 0)

        control.control_bit_param.assert_called_once_with(
            "1234567890", "BIT_AC_CHARGE_TYPE", 0, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_set_ac_charge_type_soc_volt(self) -> None:
        """Test setting AC charge type to SOC/Volt."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        mock_response = SuccessResponse(success=True)
        control.control_bit_param = AsyncMock(return_value=mock_response)

        result = await control.set_ac_charge_type("1234567890", 1)

        control.control_bit_param.assert_called_once_with(
            "1234567890", "BIT_AC_CHARGE_TYPE", 1, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_set_ac_charge_type_invalid(self) -> None:
        """Test that invalid charge type raises ValueError."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        with pytest.raises(ValueError, match="charge_type must be 0, 1, or 2"):
            await control.set_ac_charge_type("1234567890", 5)

    @pytest.mark.asyncio
    async def test_get_ac_charge_type(self) -> None:
        """Test getting AC charge type via cloud API."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        control.read_device_parameters_ranges = AsyncMock(
            return_value={"BIT_AC_CHARGE_TYPE": 2}
        )

        charge_type = await control.get_ac_charge_type("1234567890")
        assert charge_type == 2


class TestACChargeSocLimitsCloud:
    """Test AC charge SOC limit cloud API methods."""

    @pytest.mark.asyncio
    async def test_set_ac_charge_soc_limits(self) -> None:
        """Test setting AC charge SOC limits."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        mock_response = SuccessResponse(success=True)
        control.write_parameter = AsyncMock(return_value=mock_response)

        result = await control.set_ac_charge_soc_limits("1234567890", 20, 100)

        assert result.success is True
        assert control.write_parameter.call_count == 2
        control.write_parameter.assert_any_call(
            "1234567890", "HOLD_AC_CHARGE_START_BATTERY_SOC", "20", client_type="WEB"
        )
        control.write_parameter.assert_any_call(
            "1234567890", "HOLD_AC_CHARGE_SOC_LIMIT", "100", client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_set_ac_charge_soc_limits_invalid_start(self) -> None:
        """Test that invalid start_soc raises ValueError."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        with pytest.raises(ValueError, match="start_soc must be 0-90"):
            await control.set_ac_charge_soc_limits("1234567890", 95, 100)

    @pytest.mark.asyncio
    async def test_get_ac_charge_soc_limits(self) -> None:
        """Test getting AC charge SOC limits."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        control.read_device_parameters_ranges = AsyncMock(return_value={
            "HOLD_AC_CHARGE_START_BATTERY_SOC": 20,
            "HOLD_AC_CHARGE_SOC_LIMIT": 100,
        })

        limits = await control.get_ac_charge_soc_limits("1234567890")
        assert limits == {"start_soc": 20, "end_soc": 100}


class TestACChargeVoltageLimitsCloud:
    """Test AC charge voltage limit cloud API methods."""

    @pytest.mark.asyncio
    async def test_set_ac_charge_voltage_limits(self) -> None:
        """Test setting AC charge voltage limits (decivolts conversion)."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        mock_response = SuccessResponse(success=True)
        control.write_parameter = AsyncMock(return_value=mock_response)

        result = await control.set_ac_charge_voltage_limits("1234567890", 40, 58)

        assert result.success is True
        # Verify decivolts conversion (×10)
        control.write_parameter.assert_any_call(
            "1234567890", "HOLD_AC_CHARGE_START_BATTERY_VOLTAGE", "400", client_type="WEB"
        )
        control.write_parameter.assert_any_call(
            "1234567890", "HOLD_AC_CHARGE_END_BATTERY_VOLTAGE", "580", client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_set_ac_charge_voltage_limits_invalid_start(self) -> None:
        """Test that invalid start_voltage raises ValueError."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        with pytest.raises(ValueError, match="start_voltage must be 39-52V"):
            await control.set_ac_charge_voltage_limits("1234567890", 30, 58)

    @pytest.mark.asyncio
    async def test_get_ac_charge_voltage_limits(self) -> None:
        """Test getting AC charge voltage limits (decivolts conversion)."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        control.read_device_parameters_ranges = AsyncMock(return_value={
            "HOLD_AC_CHARGE_START_BATTERY_VOLTAGE": 400,
            "HOLD_AC_CHARGE_END_BATTERY_VOLTAGE": 580,
        })

        limits = await control.get_ac_charge_voltage_limits("1234567890")
        assert limits == {"start_voltage": 40, "end_voltage": 58}


class TestSporadicChargeCloud:
    """Test sporadic charge cloud API methods."""

    @pytest.mark.asyncio
    async def test_enable_sporadic_charge(self) -> None:
        """Test enable_sporadic_charge convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        result = await control.enable_sporadic_charge("1234567890")

        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_SPORADIC_CHARGE", True, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_disable_sporadic_charge(self) -> None:
        """Test disable_sporadic_charge convenience method."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        mock_response = SuccessResponse(success=True)
        control.control_function = AsyncMock(return_value=mock_response)

        result = await control.disable_sporadic_charge("1234567890")

        control.control_function.assert_called_once_with(
            "1234567890", "FUNC_SPORADIC_CHARGE", False, client_type="WEB"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_get_sporadic_charge_status_enabled(self) -> None:
        """Test get_sporadic_charge_status when enabled."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        mock_params = Mock(spec=ParameterReadResponse)
        mock_params.parameters = {"FUNC_SPORADIC_CHARGE": True}
        control.read_parameters = AsyncMock(return_value=mock_params)

        status = await control.get_sporadic_charge_status("1234567890")

        control.read_parameters.assert_called_once_with("1234567890", 233, 1)
        assert status is True

    @pytest.mark.asyncio
    async def test_get_sporadic_charge_status_disabled(self) -> None:
        """Test get_sporadic_charge_status when disabled."""
        from pylxpweb.endpoints.control import ControlEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        control = ControlEndpoints(mock_client)

        mock_params = Mock(spec=ParameterReadResponse)
        mock_params.parameters = {"FUNC_SPORADIC_CHARGE": False}
        control.read_parameters = AsyncMock(return_value=mock_params)

        status = await control.get_sporadic_charge_status("1234567890")
        assert status is False
