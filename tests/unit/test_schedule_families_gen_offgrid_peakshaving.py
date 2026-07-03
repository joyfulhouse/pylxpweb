"""Tests for the Generator / Off-Grid / Peak Shaving schedule families.

These three families extend the shared schedule infrastructure with two traits
the earlier families (AC Charge/First, Forced Charge/Discharge) do not have:

1. **Window-suffix scheme**: they number ALL windows ``_1..._N`` (no bare
   unsuffixed window). The suffix scheme is per-config, not a fixed formula.
2. **Atomic writeTime cloud writes**: cloud writes go through the portal's
   ``/WManage/web/maintain/remoteSet/writeTime`` endpoint (one call per boundary
   sets hour+minute together) instead of four separate ``write`` calls.

Peak Shaving additionally reads its schedule back under the interleaved
``LSP_HOLD_DIS_CHG_POWER_TIME_{n}`` params rather than the
``{prefix}_{START|END}_{HOUR|MINUTE}`` convention.

Register map live-verified on a FlexBOSS21 (FAAB-2525, EG4_HYBRID); the
SNA12K-US probe (docs/inverters/SNA12KUS_52XXXXXX68.json) confirms the Generator
family (regs 256-259) also applies to EG4_OFFGRID.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.constants import (
    REGISTER_TO_PARAM_KEYS,
    SCHEDULE_CONFIGS,
    ScheduleType,
    pack_time,
)
from pylxpweb.devices.inverters.hybrid import HybridInverter
from pylxpweb.endpoints.control import ControlEndpoints
from pylxpweb.models import SuccessResponse

SERIAL = "1234567890"


@pytest.fixture
def control() -> ControlEndpoints:
    """Create a ControlEndpoints instance with a mocked client."""
    return ControlEndpoints(Mock(spec=LuxpowerClient))


@pytest.fixture
def mock_client() -> LuxpowerClient:
    """Create a mock client for testing."""
    client = Mock(spec=LuxpowerClient)
    client.api = Mock()
    client.api.control = Mock()
    return client


class TestScheduleConfigTable:
    """The three families are wired into SCHEDULE_CONFIGS with the right shape."""

    def test_new_enum_members(self) -> None:
        assert ScheduleType.GEN_CHARGE == "gen_charge"
        assert ScheduleType.OFF_GRID == "off_grid"
        assert ScheduleType.PEAK_SHAVING == "peak_shaving"

    def test_every_schedule_type_has_a_config(self) -> None:
        """SCHEDULE_CONFIGS must cover every ScheduleType member."""
        assert set(SCHEDULE_CONFIGS) == set(ScheduleType)

    @pytest.mark.parametrize(
        ("schedule_type", "prefix", "base", "periods", "suffixes", "write_time", "lsp_base"),
        [
            (ScheduleType.GEN_CHARGE, "HOLD_GEN", 256, 2, ("_1", "_2"), True, None),
            (ScheduleType.OFF_GRID, "HOLD_OFF_GRID", 269, 3, ("_1", "_2", "_3"), True, None),
            (ScheduleType.PEAK_SHAVING, "HOLD_PEAK_SHAVING", 209, 2, ("_1", "_2"), True, 37),
        ],
    )
    def test_config_fields(
        self,
        schedule_type: ScheduleType,
        prefix: str,
        base: int,
        periods: int,
        suffixes: tuple[str, ...],
        write_time: bool,
        lsp_base: int | None,
    ) -> None:
        config = SCHEDULE_CONFIGS[schedule_type]
        assert config.cloud_prefix == prefix
        assert config.base_register == base
        assert config.periods == periods
        assert config.period_suffixes == suffixes
        assert config.write_via_time_api is write_time
        assert config.read_lsp_base == lsp_base

    def test_classic_families_keep_bare_window(self) -> None:
        """The pre-existing families keep the ("", "_1", "_2") scheme and
        write via separate params (regression guard)."""
        for schedule_type in (
            ScheduleType.AC_CHARGE,
            ScheduleType.AC_FIRST,
            ScheduleType.FORCED_CHARGE,
            ScheduleType.FORCED_DISCHARGE,
        ):
            config = SCHEDULE_CONFIGS[schedule_type]
            assert config.period_suffixes == ("", "_1", "_2")
            assert config.periods == 3
            assert config.write_via_time_api is False
            assert config.read_lsp_base is None

    def test_periods_matches_suffix_count(self) -> None:
        for config in SCHEDULE_CONFIGS.values():
            assert config.periods == len(config.period_suffixes)

    def test_schedule_bases_do_not_overlap(self) -> None:
        """Each schedule occupies 2 * periods registers; blocks must be disjoint."""
        merged: set[int] = set()
        for config in SCHEDULE_CONFIGS.values():
            block = set(range(config.base_register, config.base_register + 2 * config.periods))
            assert not (merged & block)
            merged |= block


class TestScheduleRegisterNames:
    """LOCAL read_named_parameters surfaces the new registers under canonical
    packed-time names (not raw numeric keys)."""

    @pytest.mark.parametrize(
        ("register", "name"),
        [
            (209, "HOLD_PEAK_SHAVING_TIME_0_START"),
            (210, "HOLD_PEAK_SHAVING_TIME_0_END"),
            (211, "HOLD_PEAK_SHAVING_TIME_1_START"),
            (212, "HOLD_PEAK_SHAVING_TIME_1_END"),
            (256, "HOLD_GEN_TIME_0_START"),
            (257, "HOLD_GEN_TIME_0_END"),
            (258, "HOLD_GEN_TIME_1_START"),
            (259, "HOLD_GEN_TIME_1_END"),
            (269, "HOLD_OFF_GRID_TIME_0_START"),
            (270, "HOLD_OFF_GRID_TIME_0_END"),
            (271, "HOLD_OFF_GRID_TIME_1_START"),
            (272, "HOLD_OFF_GRID_TIME_1_END"),
            (273, "HOLD_OFF_GRID_TIME_2_START"),
            (274, "HOLD_OFF_GRID_TIME_2_END"),
        ],
    )
    def test_register_to_param_keys(self, register: int, name: str) -> None:
        assert REGISTER_TO_PARAM_KEYS[register] == [name]


class TestWriteTimeParameter:
    """The atomic writeTime endpoint builds the right request."""

    @pytest.mark.asyncio
    async def test_write_time_request_shape(self, control: ControlEndpoints) -> None:
        control.client._ensure_authenticated = AsyncMock()
        control.client._request = AsyncMock(return_value={"success": True})
        control.client.invalidate_cache_for_device = Mock()

        result = await control.write_time_parameter(SERIAL, "HOLD_GEN_START_TIME_1", 16, 5)

        assert result.success is True
        control.client._request.assert_awaited_once_with(
            "POST",
            "/WManage/web/maintain/remoteSet/writeTime",
            data={
                "inverterSn": SERIAL,
                "timeParam": "HOLD_GEN_START_TIME_1",
                "hour": "16",
                "minute": "5",
                "clientType": "WEB",
                "remoteSetType": "NORMAL",
            },
        )
        control.client.invalidate_cache_for_device.assert_called_once_with(SERIAL)

    @pytest.mark.asyncio
    async def test_write_time_rejects_bad_hour(self, control: ControlEndpoints) -> None:
        with pytest.raises(ValueError, match="hour must be 0-23"):
            await control.write_time_parameter(SERIAL, "HOLD_GEN_START_TIME_1", 24, 0)

    @pytest.mark.asyncio
    async def test_write_time_rejects_bad_minute(self, control: ControlEndpoints) -> None:
        with pytest.raises(ValueError, match="minute must be 0-59"):
            await control.write_time_parameter(SERIAL, "HOLD_GEN_START_TIME_1", 0, 60)


class TestCloudWrites:
    """Cloud writes for the new families go through writeTime with composite
    ``{prefix}_{START|END}_TIME{suffix}`` params (2 calls, not 4)."""

    @pytest.mark.asyncio
    async def test_set_gen_charge_period_0(self, control: ControlEndpoints) -> None:
        control.write_time_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        result = await control.set_gen_charge_schedule(SERIAL, 0, 16, 0, 20, 59)

        assert result.success is True
        assert control.write_time_parameter.call_count == 2
        control.write_time_parameter.assert_any_call(
            SERIAL, "HOLD_GEN_START_TIME_1", 16, 0, client_type="WEB"
        )
        control.write_time_parameter.assert_any_call(
            SERIAL, "HOLD_GEN_END_TIME_1", 20, 59, client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_set_gen_charge_period_1_suffix(self, control: ControlEndpoints) -> None:
        """Window 2 uses suffix _2 (no bare window)."""
        control.write_time_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        await control.set_gen_charge_schedule(SERIAL, 1, 1, 5, 2, 10)

        control.write_time_parameter.assert_any_call(
            SERIAL, "HOLD_GEN_START_TIME_2", 1, 5, client_type="WEB"
        )
        control.write_time_parameter.assert_any_call(
            SERIAL, "HOLD_GEN_END_TIME_2", 2, 10, client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_set_off_grid_period_2(self, control: ControlEndpoints) -> None:
        control.write_time_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        await control.set_off_grid_schedule(SERIAL, 2, 9, 15, 11, 45)

        control.write_time_parameter.assert_any_call(
            SERIAL, "HOLD_OFF_GRID_START_TIME_3", 9, 15, client_type="WEB"
        )
        control.write_time_parameter.assert_any_call(
            SERIAL, "HOLD_OFF_GRID_END_TIME_3", 11, 45, client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_set_peak_shaving_period_0(self, control: ControlEndpoints) -> None:
        control.write_time_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        await control.set_peak_shaving_schedule(SERIAL, 0, 16, 0, 20, 59)

        control.write_time_parameter.assert_any_call(
            SERIAL, "HOLD_PEAK_SHAVING_START_TIME_1", 16, 0, client_type="WEB"
        )
        control.write_time_parameter.assert_any_call(
            SERIAL, "HOLD_PEAK_SHAVING_END_TIME_1", 20, 59, client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_off_grid_period_out_of_range_for_two_window(
        self, control: ControlEndpoints
    ) -> None:
        """Generator has 2 windows: period 2 is invalid."""
        with pytest.raises(ValueError, match="period must be 0-1"):
            await control.set_gen_charge_schedule(SERIAL, 2, 0, 0, 0, 0)

    @pytest.mark.asyncio
    async def test_off_grid_period_3_invalid(self, control: ControlEndpoints) -> None:
        """Off-Grid has 3 windows: period 3 is invalid."""
        with pytest.raises(ValueError, match="period must be 0-2"):
            await control.set_off_grid_schedule(SERIAL, 3, 0, 0, 0, 0)


class TestCloudReads:
    """Cloud reads: Generator/Off-Grid use the named hour/minute convention;
    Peak Shaving uses the interleaved LSP params."""

    @pytest.mark.asyncio
    async def test_get_gen_charge_period_1(self, control: ControlEndpoints) -> None:
        control.read_device_parameters_ranges = AsyncMock(
            return_value={
                "HOLD_GEN_START_HOUR_2": 1,
                "HOLD_GEN_START_MINUTE_2": 47,
                "HOLD_GEN_END_HOUR_2": 2,
                "HOLD_GEN_END_MINUTE_2": 30,
            }
        )

        schedule = await control.get_gen_charge_schedule(SERIAL, 1)

        assert schedule == {
            "start_hour": 1,
            "start_minute": 47,
            "end_hour": 2,
            "end_minute": 30,
        }

    @pytest.mark.asyncio
    async def test_get_off_grid_period_0(self, control: ControlEndpoints) -> None:
        control.read_device_parameters_ranges = AsyncMock(
            return_value={
                "HOLD_OFF_GRID_START_HOUR_1": 22,
                "HOLD_OFF_GRID_START_MINUTE_1": 0,
                "HOLD_OFF_GRID_END_HOUR_1": 23,
                "HOLD_OFF_GRID_END_MINUTE_1": 59,
            }
        )

        schedule = await control.get_off_grid_schedule(SERIAL, 0)

        assert schedule == {
            "start_hour": 22,
            "start_minute": 0,
            "end_hour": 23,
            "end_minute": 59,
        }

    @pytest.mark.asyncio
    async def test_get_peak_shaving_uses_lsp_params(self, control: ControlEndpoints) -> None:
        """Window 0 pulls LSP_..._37/38/39/40; window 1 pulls _41/42/43/44."""
        control.read_device_parameters_ranges = AsyncMock(
            return_value={
                "LSP_HOLD_DIS_CHG_POWER_TIME_37": 16,  # start1 hour
                "LSP_HOLD_DIS_CHG_POWER_TIME_38": 0,  # start1 minute
                "LSP_HOLD_DIS_CHG_POWER_TIME_39": 20,  # end1 hour
                "LSP_HOLD_DIS_CHG_POWER_TIME_40": 59,  # end1 minute
                "LSP_HOLD_DIS_CHG_POWER_TIME_41": 1,  # start2 hour
                "LSP_HOLD_DIS_CHG_POWER_TIME_42": 5,  # start2 minute
                "LSP_HOLD_DIS_CHG_POWER_TIME_43": 2,  # end2 hour
                "LSP_HOLD_DIS_CHG_POWER_TIME_44": 10,  # end2 minute
            }
        )

        window0 = await control.get_peak_shaving_schedule(SERIAL, 0)
        window1 = await control.get_peak_shaving_schedule(SERIAL, 1)

        assert window0 == {"start_hour": 16, "start_minute": 0, "end_hour": 20, "end_minute": 59}
        assert window1 == {"start_hour": 1, "start_minute": 5, "end_hour": 2, "end_minute": 10}


class TestModbusWrites:
    """Modbus (transport) writes pack hour|minute per register at the family's
    base via FC06 — one write per boundary."""

    @staticmethod
    def _local_inverter(mock_client: LuxpowerClient) -> tuple[HybridInverter, Mock]:
        transport = Mock()
        transport.write_parameters = AsyncMock(return_value=True)
        inverter = HybridInverter(
            client=mock_client, serial_number=SERIAL, model="FlexBOSS21", transport=transport
        )
        return inverter, transport

    @pytest.mark.asyncio
    async def test_gen_charge_local_write(self, mock_client: LuxpowerClient) -> None:
        inverter, transport = self._local_inverter(mock_client)

        # Window 2 (period 1) -> regs 258/259. pack_time(1, 47) = 1 | (47 << 8).
        await inverter.set_gen_charge_schedule(1, 1, 47, 2, 30)

        assert transport.write_parameters.await_count == 2
        transport.write_parameters.assert_any_await({258: pack_time(1, 47)})
        transport.write_parameters.assert_any_await({259: pack_time(2, 30)})

    @pytest.mark.asyncio
    async def test_off_grid_local_write_window_3(self, mock_client: LuxpowerClient) -> None:
        inverter, transport = self._local_inverter(mock_client)

        # Window 3 (period 2) -> regs 273/274.
        await inverter.set_off_grid_schedule(2, 9, 15, 11, 45)

        transport.write_parameters.assert_any_await({273: pack_time(9, 15)})
        transport.write_parameters.assert_any_await({274: pack_time(11, 45)})

    @pytest.mark.asyncio
    async def test_peak_shaving_local_write(self, mock_client: LuxpowerClient) -> None:
        inverter, transport = self._local_inverter(mock_client)

        # Window 1 (period 0) -> regs 209/210.
        await inverter.set_peak_shaving_schedule(0, 16, 0, 20, 59)

        transport.write_parameters.assert_any_await({209: pack_time(16, 0)})
        transport.write_parameters.assert_any_await({210: pack_time(20, 59)})

    @pytest.mark.asyncio
    async def test_gen_charge_local_period_out_of_range(self, mock_client: LuxpowerClient) -> None:
        inverter, _ = self._local_inverter(mock_client)
        with pytest.raises(ValueError, match="period must be 0-1"):
            await inverter.set_gen_charge_schedule(2, 0, 0, 0, 0)


class TestCloudDelegation:
    """A transport-less HybridInverter delegates schedule writes to the cloud
    setter (PR #206), which for these families uses the atomic writeTime path."""

    @pytest.mark.asyncio
    async def test_gen_charge_cloud_delegation_uses_write_time(
        self, mock_client: LuxpowerClient
    ) -> None:
        inverter = HybridInverter(client=mock_client, serial_number=SERIAL, model="FlexBOSS21")
        write_time = AsyncMock(return_value=SuccessResponse(success=True))
        mock_client.api.control._set_schedule = ControlEndpoints._set_schedule.__get__(
            mock_client.api.control
        )
        mock_client.api.control.write_time_parameter = write_time

        result = await inverter.set_gen_charge_schedule(0, 16, 0, 20, 59)

        assert result is True
        write_time.assert_any_await(SERIAL, "HOLD_GEN_START_TIME_1", 16, 0, client_type="WEB")
        write_time.assert_any_await(SERIAL, "HOLD_GEN_END_TIME_1", 20, 59, client_type="WEB")


class TestModbusReads:
    """Modbus reads decode the packed registers uniformly for all families."""

    @pytest.mark.asyncio
    async def test_gen_charge_local_read(self, mock_client: LuxpowerClient) -> None:
        transport = Mock()
        # reg 256 = pack_time(16, 0); reg 257 = pack_time(20, 59).
        transport.read_parameters = AsyncMock(
            return_value={256: pack_time(16, 0), 257: pack_time(20, 59)}
        )
        inverter = HybridInverter(
            client=mock_client, serial_number=SERIAL, model="FlexBOSS21", transport=transport
        )

        schedule = await inverter.get_gen_charge_schedule(0)

        transport.read_parameters.assert_awaited_once_with(256, 2)
        assert schedule == {"start_hour": 16, "start_minute": 0, "end_hour": 20, "end_minute": 59}

    @pytest.mark.asyncio
    async def test_off_grid_local_read_window_2(self, mock_client: LuxpowerClient) -> None:
        transport = Mock()
        transport.read_parameters = AsyncMock(
            return_value={271: pack_time(8, 30), 272: pack_time(9, 0)}
        )
        inverter = HybridInverter(
            client=mock_client, serial_number=SERIAL, model="FlexBOSS21", transport=transport
        )

        schedule = await inverter.get_off_grid_schedule(1)

        transport.read_parameters.assert_awaited_once_with(271, 2)
        assert schedule == {"start_hour": 8, "start_minute": 30, "end_hour": 9, "end_minute": 0}
