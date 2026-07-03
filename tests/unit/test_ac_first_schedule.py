"""Tests for the AC First schedule type (eg4_web_monitor issue #295).

AC First is the off-grid (SNA / EG4_OFFGRID) counterpart of the AC Charge
schedule: the EG4 portal's SNA working-mode page
(``/WManage/web/maintain/workingMode/sna``) declares cloud write params
``HOLD_AC_FIRST_{START|END}_{HOUR|MINUTE}`` with window suffixes ``""``/
``_1``/``_2`` — the identical convention to AC Charge — and the live register
probe (docs/inverters/SNA12KUS_52XXXXXX68.json, blocks 106-111) maps them to
Modbus holding registers 152-157 (152/153 = window-1 start/end, 154/155 =
window 2, 156/157 = window 3), packed hour-low/minute-high per register.

These tests also pin the REGISTER_TO_PARAM_KEYS names for the forced
discharge schedule registers 84-89, which were previously unmapped (LOCAL
reads surfaced raw numeric keys).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.constants import (
    HOLD_AC_FIRST_TIME_0_END,
    HOLD_AC_FIRST_TIME_0_START,
    HOLD_AC_FIRST_TIME_1_END,
    HOLD_AC_FIRST_TIME_1_START,
    HOLD_AC_FIRST_TIME_2_END,
    HOLD_AC_FIRST_TIME_2_START,
    REGISTER_TO_PARAM_KEYS,
    SCHEDULE_CONFIGS,
    ScheduleType,
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


class TestACFirstScheduleConfig:
    """The AC First schedule type is wired into the shared infrastructure."""

    def test_schedule_type_member(self) -> None:
        assert ScheduleType.AC_FIRST == "ac_first"

    def test_schedule_config_entry(self) -> None:
        config = SCHEDULE_CONFIGS[ScheduleType.AC_FIRST]
        assert config.cloud_prefix == "HOLD_AC_FIRST"
        assert config.base_register == 152

    def test_every_schedule_type_has_a_config(self) -> None:
        """SCHEDULE_CONFIGS must cover every ScheduleType member."""
        assert set(SCHEDULE_CONFIGS) == set(ScheduleType)

    def test_register_constants(self) -> None:
        assert HOLD_AC_FIRST_TIME_0_START == 152
        assert HOLD_AC_FIRST_TIME_0_END == 153
        assert HOLD_AC_FIRST_TIME_1_START == 154
        assert HOLD_AC_FIRST_TIME_1_END == 155
        assert HOLD_AC_FIRST_TIME_2_START == 156
        assert HOLD_AC_FIRST_TIME_2_END == 157

    def test_schedule_bases_do_not_overlap(self) -> None:
        """Each schedule occupies 6 registers; the blocks must be disjoint."""
        blocks = [
            set(range(cfg.base_register, cfg.base_register + 6))
            for cfg in SCHEDULE_CONFIGS.values()
        ]
        merged: set[int] = set()
        for block in blocks:
            assert not (merged & block)
            merged |= block


class TestScheduleRegisterNames:
    """LOCAL read_named_parameters surfaces schedule registers under
    canonical packed-time names (not raw numeric keys)."""

    @pytest.mark.parametrize(
        ("register", "name"),
        [
            (84, "HOLD_FORCED_DISCHARGE_TIME_0_START"),
            (85, "HOLD_FORCED_DISCHARGE_TIME_0_END"),
            (86, "HOLD_FORCED_DISCHARGE_TIME_1_START"),
            (87, "HOLD_FORCED_DISCHARGE_TIME_1_END"),
            (88, "HOLD_FORCED_DISCHARGE_TIME_2_START"),
            (89, "HOLD_FORCED_DISCHARGE_TIME_2_END"),
            (152, "HOLD_AC_FIRST_TIME_0_START"),
            (153, "HOLD_AC_FIRST_TIME_0_END"),
            (154, "HOLD_AC_FIRST_TIME_1_START"),
            (155, "HOLD_AC_FIRST_TIME_1_END"),
            (156, "HOLD_AC_FIRST_TIME_2_START"),
            (157, "HOLD_AC_FIRST_TIME_2_END"),
        ],
    )
    def test_register_to_param_keys(self, register: int, name: str) -> None:
        assert REGISTER_TO_PARAM_KEYS[register] == [name]

    def test_forced_charge_names_unchanged(self) -> None:
        """Regression: the pre-existing 76-81 names must not drift."""
        for offset in range(6):
            period, boundary = divmod(offset, 2)
            expected = f"HOLD_FORCED_CHARGE_TIME_{period}_{'END' if boundary else 'START'}"
            assert REGISTER_TO_PARAM_KEYS[76 + offset] == [expected]


class TestACFirstScheduleCloud:
    """Cloud API wrappers mirror the AC charge/forced charge pattern."""

    @pytest.mark.asyncio
    async def test_set_ac_first_schedule_period_0(self, control: ControlEndpoints) -> None:
        """Period 0 uses the unsuffixed HOLD_AC_FIRST_* params."""
        control.write_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        result = await control.set_ac_first_schedule(SERIAL, 0, 23, 0, 7, 0)

        assert result.success is True
        assert control.write_parameter.call_count == 4
        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_FIRST_START_HOUR", "23", client_type="WEB"
        )
        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_FIRST_START_MINUTE", "0", client_type="WEB"
        )
        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_FIRST_END_HOUR", "7", client_type="WEB"
        )
        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_FIRST_END_MINUTE", "0", client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_set_ac_first_schedule_period_1_suffix(self, control: ControlEndpoints) -> None:
        """Periods 1/2 use the _1/_2 suffixes (portal holdParam convention)."""
        control.write_parameter = AsyncMock(return_value=SuccessResponse(success=True))

        await control.set_ac_first_schedule(SERIAL, 1, 8, 30, 16, 0)

        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_FIRST_START_HOUR_1", "8", client_type="WEB"
        )
        control.write_parameter.assert_any_call(
            SERIAL, "HOLD_AC_FIRST_END_MINUTE_1", "0", client_type="WEB"
        )

    @pytest.mark.asyncio
    async def test_set_ac_first_schedule_invalid_period(self, control: ControlEndpoints) -> None:
        with pytest.raises(ValueError, match="period must be 0-2"):
            await control.set_ac_first_schedule(SERIAL, 3, 0, 0, 0, 0)

    @pytest.mark.asyncio
    async def test_get_ac_first_schedule(self, control: ControlEndpoints) -> None:
        control.read_device_parameters_ranges = AsyncMock(
            return_value={
                "HOLD_AC_FIRST_START_HOUR": 23,
                "HOLD_AC_FIRST_START_MINUTE": 0,
                "HOLD_AC_FIRST_END_HOUR": 7,
                "HOLD_AC_FIRST_END_MINUTE": 30,
            }
        )

        schedule = await control.get_ac_first_schedule(SERIAL, 0)

        assert schedule == {
            "start_hour": 23,
            "start_minute": 0,
            "end_hour": 7,
            "end_minute": 30,
        }


class TestACFirstScheduleModbus:
    """Local (transport) path writes packed times to registers 152-157 via FC06."""

    @pytest.mark.asyncio
    async def test_set_ac_first_schedule_period_0(self, mock_client: LuxpowerClient) -> None:
        transport = Mock()
        transport.write_parameters = AsyncMock(return_value=True)
        inverter = HybridInverter(
            client=mock_client, serial_number=SERIAL, model="12000XP", transport=transport
        )

        result = await inverter.set_ac_first_schedule(0, 23, 0, 7, 0)

        # Two individual writes (FC06) — firmware rejects FC16 multi-writes
        # on schedule registers.  reg 152 = pack_time(23, 0) = 23; reg 153 =
        # pack_time(7, 0) = 7.
        assert transport.write_parameters.await_count == 2
        transport.write_parameters.assert_any_await({152: 23})
        transport.write_parameters.assert_any_await({153: 7})
        # Cloud raw-register write is NOT used on the transport path.
        assert not mock_client.api.control.write_parameters.called
        assert result is True

    @pytest.mark.asyncio
    async def test_set_ac_first_schedule_period_2_packed(self, mock_client: LuxpowerClient) -> None:
        transport = Mock()
        transport.write_parameters = AsyncMock(return_value=True)
        inverter = HybridInverter(
            client=mock_client, serial_number=SERIAL, model="12000XP", transport=transport
        )

        result = await inverter.set_ac_first_schedule(2, 12, 30, 14, 45)

        # pack_time(12, 30) = 12 | (30 << 8) = 7692; pack_time(14, 45) = 11534
        transport.write_parameters.assert_any_await({156: 7692})
        transport.write_parameters.assert_any_await({157: 11534})
        assert result is True

    @pytest.mark.asyncio
    async def test_get_ac_first_schedule(self, mock_client: LuxpowerClient) -> None:
        # LOCAL (Modbus) path: read the packed-time registers via the transport.
        # reg 152 = pack_time(23, 0) = 23; reg 153 = pack_time(7, 30) = (30<<8)|7.
        transport = Mock()
        transport.read_parameters = AsyncMock(return_value={152: 23, 153: (30 << 8) | 7})
        inverter = HybridInverter(
            client=mock_client, serial_number=SERIAL, model="12000XP", transport=transport
        )

        schedule = await inverter.get_ac_first_schedule(0)

        transport.read_parameters.assert_awaited_once_with(152, 2)
        assert schedule == {
            "start_hour": 23,
            "start_minute": 0,
            "end_hour": 7,
            "end_minute": 30,
        }


class TestScheduleHybridCloudWrite:
    """Cloud (transport-less) schedule writes delegate to the named cloud setter.

    Symmetric with the PR #205 read-side fix: the cloud API models schedules as
    named per-field params (``{cloud_prefix}_START_HOUR`` etc.), not raw
    ``reg_<n>`` writes.  ``HybridInverter._set_schedule`` used to POST a packed
    register value to ``remoteSet/write`` keyed by register address, which would
    not round-trip through the named cloud getter.  It now delegates to
    ``ControlEndpoints._set_schedule``.
    """

    @pytest.mark.asyncio
    async def test_cloud_set_delegates_to_named_setter(self, mock_client: LuxpowerClient) -> None:
        inverter = HybridInverter(client=mock_client, serial_number=SERIAL, model="12000XP")
        mock_client.api.control._set_schedule = AsyncMock(
            return_value=SuccessResponse(success=True)
        )
        # A raw-register cloud write would go through control.write_parameters —
        # it must NOT be used.
        mock_client.api.control.write_parameters = AsyncMock()

        result = await inverter.set_ac_first_schedule(1, 8, 30, 16, 0)

        mock_client.api.control._set_schedule.assert_awaited_once_with(
            SERIAL, ScheduleType.AC_FIRST, 1, 8, 30, 16, 0
        )
        assert not mock_client.api.control.write_parameters.called
        assert result is True

    @pytest.mark.asyncio
    async def test_cloud_set_propagates_failure(self, mock_client: LuxpowerClient) -> None:
        inverter = HybridInverter(client=mock_client, serial_number=SERIAL, model="12000XP")
        mock_client.api.control._set_schedule = AsyncMock(
            return_value=SuccessResponse(success=False)
        )

        result = await inverter.set_forced_charge_schedule(0, 1, 0, 5, 0)

        mock_client.api.control._set_schedule.assert_awaited_once_with(
            SERIAL, ScheduleType.FORCED_CHARGE, 0, 1, 0, 5, 0
        )
        assert result is False
