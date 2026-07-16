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
            ("enable_feed_in_grid", "FUNC_FEED_IN_GRID_EN", True),
            ("disable_feed_in_grid", "FUNC_FEED_IN_GRID_EN", False),
            ("enable_pv_sell_to_grid", "FUNC_PV_SELL_TO_GRID_EN", True),
            ("disable_pv_sell_to_grid", "FUNC_PV_SELL_TO_GRID_EN", False),
            # Fast Zero Export (GH eg4_web_monitor#274): reg 110 bit 1;
            # both web UIs toggle FUNC_RUN_WITHOUT_GRID for the button.
            ("enable_fast_zero_export", "FUNC_RUN_WITHOUT_GRID", True),
            ("disable_fast_zero_export", "FUNC_RUN_WITHOUT_GRID", False),
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
            # Reg 179, NOT 21: live named reads (2026-06-12) show the key
            # only appears in the (179, 1) response on EG4 hardware.
            ("get_peak_shaving_mode_status", 179, "FUNC_GRID_PEAK_SHAVING"),
            ("get_green_mode_status", 110, "FUNC_GREEN_EN"),
            ("get_sporadic_charge_status", 233, "FUNC_SPORADIC_CHARGE"),
            ("get_feed_in_grid_status", 21, "FUNC_FEED_IN_GRID_EN"),
            ("get_pv_sell_to_grid_status", 179, "FUNC_PV_SELL_TO_GRID_EN"),
            ("get_fast_zero_export_status", 110, "FUNC_RUN_WITHOUT_GRID"),
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
            ("get_feed_in_grid_status", 21, "FUNC_FEED_IN_GRID_EN"),
            ("get_pv_sell_to_grid_status", 179, "FUNC_PV_SELL_TO_GRID_EN"),
            ("get_fast_zero_export_status", 110, "FUNC_RUN_WITHOUT_GRID"),
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
        """A successful register write invalidates the device cache."""
        api_client._request = AsyncMock(return_value={"success": True})
        control = ControlEndpoints(api_client)

        # Reg 67 = HOLD_AC_CHARGE_SOC_LIMIT (a pure value register, scale NONE).
        result = await control.write_parameters(SERIAL, {67: 90})

        assert result.success is True
        api_client.invalidate_cache_for_device.assert_called_once_with(SERIAL)

    @pytest.mark.asyncio
    async def test_write_parameters_translates_to_named_writes(self, api_client: Mock) -> None:
        """Each register is sent as a NAMED holdParam/valueText write, never as
        the old malformed nested ``data={reg: val}`` form field."""
        api_client._request = AsyncMock(return_value={"success": True})
        control = ControlEndpoints(api_client)

        # 228 = HOLD_SYSTEM_CHARGE_VOLT_LIMIT (÷10 → "59.5"); 67 = SOC (1:1).
        result = await control.write_parameters(SERIAL, {228: 595, 67: 90})

        assert result.success is True
        assert api_client._request.await_count == 2
        sent = [call.kwargs["data"] for call in api_client._request.await_args_list]
        # No call carries a dict-valued "data" form field anymore.
        assert all(isinstance(d.get("valueText"), str) for d in sent)
        assert all(not isinstance(d.get("data"), dict) for d in sent)
        assert {
            "inverterSn": SERIAL,
            "holdParam": "HOLD_SYSTEM_CHARGE_VOLT_LIMIT",
            "valueText": "59.5",
            "clientType": "WEB",
            "remoteSetType": "NORMAL",
        } in sent
        assert {
            "inverterSn": SERIAL,
            "holdParam": "HOLD_AC_CHARGE_SOC_LIMIT",
            "valueText": "90",
            "clientType": "WEB",
            "remoteSetType": "NORMAL",
        } in sent

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("register", "raw", "expected_name", "expected_value"),
        [
            # Decivolt (DIV_10) registers via the canonical table.
            (228, 595, "HOLD_SYSTEM_CHARGE_VOLT_LIMIT", "59.5"),
            (158, 400, "HOLD_AC_CHARGE_START_BATTERY_VOLTAGE", "40"),
            (159, 480, "HOLD_AC_CHARGE_END_BATTERY_VOLTAGE", "48"),
            (169, 485, "HOLD_ON_GRID_EOD_VOLTAGE", "48.5"),
            (100, 480, "HOLD_LEAD_ACID_DISCHARGE_CUT_OFF_VOLT", "48"),
            # CLOUD_WRITE_DIV10_REGISTERS: table scale is NONE but the cloud
            # named-write expects engineering units (raw ÷ 10).
            (202, 480, "_12K_HOLD_STOP_DISCHG_VOLT", "48"),
            (202, 505, "_12K_HOLD_STOP_DISCHG_VOLT", "50.5"),
            (66, 120, "HOLD_AC_CHARGE_POWER_CMD", "12"),
            (74, 120, "HOLD_FORCED_CHG_POWER_CMD", "12"),
            (82, 120, "HOLD_FORCED_DISCHG_POWER_CMD", "12"),
            (103, 120, "HOLD_FEED_IN_GRID_POWER_PERCENT", "12"),
            # LOCAL_PARAM_SCALE_DIV10 peak-shaving power regs (raw deci-kW).
            (206, 120, "_12K_HOLD_GRID_PEAK_SHAVING_POWER", "12"),
            (232, 41, "_12K_HOLD_GRID_PEAK_SHAVING_POWER_2", "4.1"),
            # 1:1 (NONE) registers pass the raw value straight through.
            (67, 90, "HOLD_AC_CHARGE_SOC_LIMIT", "90"),
        ],
    )
    async def test_write_parameters_scaling(
        self,
        register: int,
        raw: int,
        expected_name: str,
        expected_value: str,
    ) -> None:
        """Register raw values scale to the cloud's string form by divisor."""
        name, value = ControlEndpoints._resolve_named_write(register, raw)
        assert name == expected_name
        assert value == expected_value

    def test_cloud_write_div10_registers_all_covered(self) -> None:
        """Every register in CLOUD_WRITE_DIV10_REGISTERS resolves with a ÷10
        divisor (guards against the set drifting out of sync with the resolver)."""
        from pylxpweb.constants.registers import CLOUD_WRITE_DIV10_REGISTERS

        for register in CLOUD_WRITE_DIV10_REGISTERS:
            _, value = ControlEndpoints._resolve_named_write(register, 120)
            assert value == "12", f"register {register} did not scale ÷10"

    @pytest.mark.asyncio
    async def test_write_parameters_pre_validates_atomically(self, api_client: Mock) -> None:
        """A bad register anywhere in the batch raises BEFORE any write, so a
        valid earlier register is NOT written (all-or-nothing resolution)."""
        api_client._request = AsyncMock(return_value={"success": True})
        control = ControlEndpoints(api_client)

        # 67 is valid; 21 is a bitfield. Insertion order writes 67 first, but
        # resolution happens up front so nothing is sent.
        with pytest.raises(ValueError, match="bitfield"):
            await control.write_parameters(SERIAL, {67: 90, 21: 128})
        api_client._request.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "register",
        [68, 76, 84, 152, 209, 256, 269],  # one per schedule family base.
        ids=[
            "ac_charge",
            "forced_chg",
            "forced_dischg",
            "ac_first",
            "peak_shaving",
            "gen",
            "offgrid",
        ],
    )
    async def test_write_parameters_rejects_schedule_register(
        self, api_client: Mock, register: int
    ) -> None:
        """Packed-time schedule registers raise, directing to the schedule setters."""
        api_client._request = AsyncMock(return_value={"success": True})
        control = ControlEndpoints(api_client)

        with pytest.raises(ValueError, match="schedule register"):
            await control.write_parameters(SERIAL, {register: 1})
        api_client._request.assert_not_called()

    @pytest.mark.asyncio
    async def test_write_parameters_stops_on_first_failure(self, api_client: Mock) -> None:
        """A failed write returns immediately; later registers are not written."""
        failure = {"success": False}
        api_client._request = AsyncMock(return_value=failure)
        control = ControlEndpoints(api_client)

        # dict preserves insertion order: 228 is attempted first and fails.
        result = await control.write_parameters(SERIAL, {228: 595, 67: 90})

        assert result.success is False
        api_client._request.assert_awaited_once()
        assert api_client._request.await_args.kwargs["data"]["holdParam"] == (
            "HOLD_SYSTEM_CHARGE_VOLT_LIMIT"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "register",
        [21, 110],  # register 21 / 110 pack many FUNC_ bits.
        ids=["reg21_bitfield", "reg110_bitfield"],
    )
    async def test_write_parameters_rejects_bitfield(self, api_client: Mock, register: int) -> None:
        """Bitfield registers raise ValueError instead of a malformed write."""
        api_client._request = AsyncMock(return_value={"success": True})
        control = ControlEndpoints(api_client)

        with pytest.raises(ValueError, match="bitfield"):
            await control.write_parameters(SERIAL, {register: 1})
        api_client._request.assert_not_called()

    @pytest.mark.asyncio
    async def test_write_parameters_rejects_unmapped(self, api_client: Mock) -> None:
        """An unmapped register raises ValueError, never a silent no-op body."""
        api_client._request = AsyncMock(return_value={"success": True})
        control = ControlEndpoints(api_client)

        with pytest.raises(ValueError, match="not mapped"):
            await control.write_parameters(SERIAL, {9999: 1})
        api_client._request.assert_not_called()

    @pytest.mark.asyncio
    async def test_write_parameters_empty_is_noop_success(self, api_client: Mock) -> None:
        """An empty dict is a successful no-op with no requests sent."""
        api_client._request = AsyncMock(return_value={"success": True})
        control = ControlEndpoints(api_client)

        result = await control.write_parameters(SERIAL, {})

        assert result.success is True
        api_client._request.assert_not_called()


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
    async def test_set_ac_charge_schedule_stops_on_first_write_failure(
        self, control: ControlEndpoints
    ) -> None:
        """Legacy four-param path returns the first failed write and stops.

        If HOLD_AC_CHARGE_START_HOUR is rejected, the remaining three params
        must not be written (no half-applied schedule window).
        """
        failure = SuccessResponse(success=False)
        control.write_parameter = AsyncMock(return_value=failure)

        result = await control.set_ac_charge_schedule(SERIAL, 0, 23, 0, 7, 0)

        assert result is failure
        control.write_parameter.assert_called_once_with(
            SERIAL, "HOLD_AC_CHARGE_START_HOUR", "23", client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_set_ac_charge_schedule_stops_on_later_write_failure(
        self, control: ControlEndpoints
    ) -> None:
        """A failure on the third write stops before the final END_MINUTE."""
        results = [
            SuccessResponse(success=True),
            SuccessResponse(success=True),
            SuccessResponse(success=False),
            SuccessResponse(success=True),
        ]
        control.write_parameter = AsyncMock(side_effect=results)

        result = await control.set_ac_charge_schedule(SERIAL, 0, 23, 0, 7, 0)

        assert result.success is False
        # START_HOUR, START_MINUTE, END_HOUR only — END_MINUTE skipped.
        assert control.write_parameter.call_count == 3

    @pytest.mark.asyncio
    async def test_set_ac_charge_schedule_invalid_period(self, control: ControlEndpoints) -> None:
        """Test that invalid period raises ValueError."""
        with pytest.raises(ValueError, match="period must be 0-2"):
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

    @pytest.mark.asyncio
    async def test_get_schedule_present_but_null_field_defaults_zero(
        self, control: ControlEndpoints
    ) -> None:
        """A field present-but-null must default to 0, not raise int(None)."""
        control.read_device_parameters_ranges = AsyncMock(
            return_value={
                "HOLD_AC_CHARGE_START_HOUR": None,
                "HOLD_AC_CHARGE_START_MINUTE": 30,
                # END_HOUR / END_MINUTE absent entirely
            }
        )

        schedule = await control.get_ac_charge_schedule(SERIAL, 0)

        assert schedule == {
            "start_hour": 0,
            "start_minute": 30,
            "end_hour": 0,
            "end_minute": 0,
        }

    @pytest.mark.asyncio
    async def test_get_schedule_clamps_out_of_range(self, control: ControlEndpoints) -> None:
        """Out-of-range cloud values are clamped to valid clock components."""
        control.read_device_parameters_ranges = AsyncMock(
            return_value={
                "HOLD_AC_CHARGE_START_HOUR": 99,  # -> 23
                "HOLD_AC_CHARGE_START_MINUTE": 250,  # -> 59
                "HOLD_AC_CHARGE_END_HOUR": -5,  # -> 0
                "HOLD_AC_CHARGE_END_MINUTE": "45",  # string coerces -> 45
            }
        )

        schedule = await control.get_ac_charge_schedule(SERIAL, 0)

        assert schedule == {
            "start_hour": 23,
            "start_minute": 59,
            "end_hour": 0,
            "end_minute": 45,
        }

    @pytest.mark.asyncio
    async def test_get_schedule_non_numeric_defaults_zero(self, control: ControlEndpoints) -> None:
        """Non-numeric garbage coerces to 0 rather than raising."""
        control.read_device_parameters_ranges = AsyncMock(
            return_value={
                "HOLD_AC_CHARGE_START_HOUR": "",
                "HOLD_AC_CHARGE_START_MINUTE": "oops",
            }
        )

        schedule = await control.get_ac_charge_schedule(SERIAL, 0)

        assert schedule == {
            "start_hour": 0,
            "start_minute": 0,
            "end_hour": 0,
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
    async def test_set_ac_charge_soc_limits_end_101_accepted(
        self, control: ControlEndpoints
    ) -> None:
        """end_soc=101 is accepted (never-stop / cell balancing, GH eg4_web_monitor#158)."""
        control.write_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        result = await control.set_ac_charge_soc_limits(SERIAL, 20, 101)

        assert result.success is True
        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_CHARGE_SOC_LIMIT", "101", client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_set_ac_charge_soc_limits_invalid_end(self, control: ControlEndpoints) -> None:
        """end_soc above the 101 cap raises ValueError."""
        with pytest.raises(ValueError, match="end_soc must be 0-101"):
            await control.set_ac_charge_soc_limits(SERIAL, 20, 102)

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


class TestInverterACCoupleSocLimitsCloud:
    """Inverter-level AC couple SOC cloud API methods (eg4_web_monitor#352).

    Distinct from the GridBOSS/MID per-port ``set_ac_couple_start_soc`` methods:
    these write the inverter's own ``_12K_HOLD_AC_COUPLE_{START,END}_SOC``
    holdParams (wire evidence: the reporter's 12000XP v2 portal capture and the
    SNA12K-US EG4_OFFGRID register probe).
    """

    @pytest.mark.asyncio
    async def test_set_inverter_ac_couple_start_soc(self, control: ControlEndpoints) -> None:
        """Start SOC writes the _12K_HOLD_AC_COUPLE_START_SOC holdParam."""
        control.write_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        result = await control.set_inverter_ac_couple_start_soc(SERIAL, 85)

        assert result.success is True
        control.write_parameter.assert_called_once_with(
            SERIAL, "_12K_HOLD_AC_COUPLE_START_SOC", "85", client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_set_inverter_ac_couple_end_soc(self, control: ControlEndpoints) -> None:
        """End SOC writes the _12K_HOLD_AC_COUPLE_END_SOC holdParam (the wire
        name for the reporter's "STOP" SOC)."""
        control.write_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        result = await control.set_inverter_ac_couple_end_soc(SERIAL, 95)

        assert result.success is True
        control.write_parameter.assert_called_once_with(
            SERIAL, "_12K_HOLD_AC_COUPLE_END_SOC", "95", client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_set_inverter_ac_couple_start_soc_bounds(self, control: ControlEndpoints) -> None:
        """0, 1 (the reporter's step-wise low) and 100 are all accepted."""
        control.write_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        assert (await control.set_inverter_ac_couple_start_soc(SERIAL, 0)).success is True
        assert (await control.set_inverter_ac_couple_start_soc(SERIAL, 1)).success is True
        assert (await control.set_inverter_ac_couple_end_soc(SERIAL, 100)).success is True

    @pytest.mark.asyncio
    async def test_set_inverter_ac_couple_start_soc_invalid(
        self, control: ControlEndpoints
    ) -> None:
        """Out-of-range start SOC raises ValueError before any write."""
        control.write_parameter = AsyncMock(return_value=SuccessResponse(success=True))
        with pytest.raises(ValueError, match="percent must be 0-100"):
            await control.set_inverter_ac_couple_start_soc(SERIAL, 101)
        control.write_parameter.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_inverter_ac_couple_start_soc_rejects_255(
        self, control: ControlEndpoints
    ) -> None:
        """The 255 disabled sentinel is END-only; START rejects it with its
        plain 0-100 message (no probe dump shows start=255 — the observed
        disabled pair is start=100)."""
        control.write_parameter = AsyncMock(return_value=SuccessResponse(success=True))
        with pytest.raises(ValueError, match=r"percent must be 0-100, got 255"):
            await control.set_inverter_ac_couple_start_soc(SERIAL, 255)
        control.write_parameter.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_inverter_ac_couple_end_soc_255_accepted(
        self, control: ControlEndpoints
    ) -> None:
        """END accepts the 255 disabled/never-stop sentinel (4 factory-state
        probe dumps read END=255 paired with START=100)."""
        control.write_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        result = await control.set_inverter_ac_couple_end_soc(SERIAL, 255)

        assert result.success is True
        control.write_parameter.assert_called_once_with(
            SERIAL, "_12K_HOLD_AC_COUPLE_END_SOC", "255", client_type="WEB"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [-1, 101, 254, 256])
    async def test_set_inverter_ac_couple_end_soc_invalid(
        self, control: ControlEndpoints, bad: int
    ) -> None:
        """Values outside 0-100 that are not exactly 255 raise before any write
        (101 and 254 prove 255 is a single sentinel, not an open upper range)."""
        control.write_parameter = AsyncMock(return_value=SuccessResponse(success=True))
        with pytest.raises(ValueError, match="percent must be 0-100 or 255"):
            await control.set_inverter_ac_couple_end_soc(SERIAL, bad)
        control.write_parameter.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_inverter_ac_couple_soc_client_type_propagates(
        self, control: ControlEndpoints
    ) -> None:
        """client_type flows through to write_parameter on both setters."""
        control.write_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        await control.set_inverter_ac_couple_start_soc(SERIAL, 85, client_type="APP")
        await control.set_inverter_ac_couple_end_soc(SERIAL, 95, client_type="APP")

        control.write_parameter.assert_any_call(
            SERIAL, "_12K_HOLD_AC_COUPLE_START_SOC", "85", client_type="APP"
        )
        control.write_parameter.assert_any_call(
            SERIAL, "_12K_HOLD_AC_COUPLE_END_SOC", "95", client_type="APP"
        )

    @pytest.mark.asyncio
    async def test_get_inverter_ac_couple_soc_limits(self, control: ControlEndpoints) -> None:
        """Getter surfaces both params from the cloud parameter read (portal
        returns them as strings, e.g. the SNA12K-US probe's "50"/"90")."""
        control.read_device_parameters_ranges = AsyncMock(
            return_value={
                "_12K_HOLD_AC_COUPLE_START_SOC": "50",
                "_12K_HOLD_AC_COUPLE_END_SOC": "90",
            }
        )

        limits = await control.get_inverter_ac_couple_soc_limits(SERIAL)
        assert limits == {"start_soc": 50, "end_soc": 90}

    @pytest.mark.asyncio
    async def test_get_inverter_ac_couple_soc_limits_passes_255_through(
        self, control: ControlEndpoints
    ) -> None:
        """The 255 disabled sentinel is surfaced unmodified (factory state:
        START=100, END=255)."""
        control.read_device_parameters_ranges = AsyncMock(
            return_value={
                "_12K_HOLD_AC_COUPLE_START_SOC": "100",
                "_12K_HOLD_AC_COUPLE_END_SOC": "255",
            }
        )

        limits = await control.get_inverter_ac_couple_soc_limits(SERIAL)
        assert limits == {"start_soc": 100, "end_soc": 255}

    @pytest.mark.asyncio
    async def test_get_inverter_ac_couple_soc_limits_absent(
        self, control: ControlEndpoints
    ) -> None:
        """A family without these params (grid-tied) reads back None/None — not
        0/0, since 0 is a legal writable SOC and would be ambiguous."""
        control.read_device_parameters_ranges = AsyncMock(return_value={})

        limits = await control.get_inverter_ac_couple_soc_limits(SERIAL)
        assert limits == {"start_soc": None, "end_soc": None}

    @pytest.mark.asyncio
    async def test_get_inverter_ac_couple_soc_limits_partial(
        self, control: ControlEndpoints
    ) -> None:
        """A present param is parsed; a missing sibling is None (not 0)."""
        control.read_device_parameters_ranges = AsyncMock(
            return_value={"_12K_HOLD_AC_COUPLE_START_SOC": "85"}
        )

        limits = await control.get_inverter_ac_couple_soc_limits(SERIAL)
        assert limits == {"start_soc": 85, "end_soc": None}

    @pytest.mark.asyncio
    async def test_get_inverter_ac_couple_soc_limits_non_numeric(
        self, control: ControlEndpoints
    ) -> None:
        """Non-numeric garbage parses to None rather than raising."""
        control.read_device_parameters_ranges = AsyncMock(
            return_value={
                "_12K_HOLD_AC_COUPLE_START_SOC": "n/a",
                "_12K_HOLD_AC_COUPLE_END_SOC": None,
            }
        )

        limits = await control.get_inverter_ac_couple_soc_limits(SERIAL)
        assert limits == {"start_soc": None, "end_soc": None}


class TestACChargeVoltageLimitsCloud:
    """Test AC charge voltage limit cloud API methods."""

    @pytest.mark.asyncio
    async def test_set_ac_charge_voltage_limits(self, control: ControlEndpoints) -> None:
        """The cloud API takes VOLTS, not decivolts (live-verified 2026-07-07):
        40V is sent as "40", never "400"."""
        control.write_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        result = await control.set_ac_charge_voltage_limits(SERIAL, 40, 58)

        assert result.success is True
        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_CHARGE_START_BATTERY_VOLTAGE", "40", client_type="WEB"
        )
        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_CHARGE_END_BATTERY_VOLTAGE", "58", client_type="WEB"
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
        """The cloud read returns VOLTS; parse as float, no ÷10.

        A whole-volt read ("40") must come back as 40.0V, not 4V.
        """
        control.read_device_parameters_ranges = AsyncMock(
            return_value={
                "HOLD_AC_CHARGE_START_BATTERY_VOLTAGE": "40",
                "HOLD_AC_CHARGE_END_BATTERY_VOLTAGE": "58",
            }
        )

        limits = await control.get_ac_charge_voltage_limits(SERIAL)
        assert limits == {"start_voltage": 40.0, "end_voltage": 58.0}

    @pytest.mark.asyncio
    async def test_get_ac_charge_voltage_limits_fractional(self, control: ControlEndpoints) -> None:
        """A fractional-volt read ("40.5") parses as 40.5, not a ValueError."""
        control.read_device_parameters_ranges = AsyncMock(
            return_value={
                "HOLD_AC_CHARGE_START_BATTERY_VOLTAGE": "40.5",
                "HOLD_AC_CHARGE_END_BATTERY_VOLTAGE": "58",
            }
        )

        limits = await control.get_ac_charge_voltage_limits(SERIAL)
        assert limits == {"start_voltage": 40.5, "end_voltage": 58.0}


class TestSignedRegisterInvariant:
    """No signed holding register may be silently writable via write_parameters.

    The cloud wire format for negative values is unvalidated; the resolver
    refuses signed registers. This invariant test forces an explicit decision
    if a signed register is ever added to REGISTER_TO_PARAM_KEYS.
    """

    def test_no_mapped_register_is_signed(self) -> None:
        from pylxpweb.constants.registers import REGISTER_TO_PARAM_KEYS
        from pylxpweb.registers import HOLDING_BY_ADDRESS

        signed_mapped = [
            addr
            for addr in REGISTER_TO_PARAM_KEYS
            if any(d.signed for d in HOLDING_BY_ADDRESS.get(addr, ()))
        ]
        assert signed_mapped == [], (
            f"Signed registers {signed_mapped} are mapped in "
            "REGISTER_TO_PARAM_KEYS; validate their cloud negative-value "
            "format before allowing them through write_parameters"
        )
