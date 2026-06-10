"""Unit tests for get_month_daily_energy (inverterChart monthColumn).

Response shapes are synthetic, modeled on the EG4 mobile app's decompiled
chart parser:

- Single-inverter rows carry ePv1Day/ePv2Day/ePv3Day and eToGridDay.
- Parallel-group rows carry aggregated ePvDay and eExportDay.
- Both variants carry eDisChgDay and eConsumptionDay.
- Raw values are integers in 0.1 kWh units (the app divides by 10 before
  plotting on kWh axes).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb.endpoints.analytics import AnalyticsEndpoints
from pylxpweb.models import DailyEnergyHistoryEntry, MonthlyEnergyHistory


@pytest.fixture
def mock_client() -> Mock:
    """Create mock LuxpowerClient."""
    client = Mock()
    client._ensure_authenticated = AsyncMock()
    client._request = AsyncMock()
    return client


@pytest.fixture
def analytics(mock_client: Mock) -> AnalyticsEndpoints:
    """Create AnalyticsEndpoints instance with mock client."""
    return AnalyticsEndpoints(mock_client)


def _single_inverter_response(days: int = 3) -> dict[str, Any]:
    """Synthetic monthColumn response (single-inverter variant)."""
    return {
        "success": True,
        "data": [
            {
                "ePv1Day": 100 + i,  # 10.0+ kWh
                "ePv2Day": 50,
                "ePv3Day": 0,
                "eInvDay": 140 + i,
                "eRecDay": 5,
                "eChgDay": 60,
                "eDisChgDay": 55,
                "eEpsDay": 0,
                "eToGridDay": 20,
                "eToUserDay": 30,
                "eConsumptionDay": 150,
            }
            for i in range(days)
        ],
    }


def _parallel_response(days: int = 2) -> dict[str, Any]:
    """Synthetic monthColumnParallel response (group-aggregate variant)."""
    return {
        "success": True,
        "data": [
            {
                "ePvDay": 300 + i,
                "eDisChgDay": 110,
                "eExportDay": 40,
                "eConsumptionDay": 280,
            }
            for i in range(days)
        ],
    }


class TestGetMonthDailyEnergy:
    """Tests for the get_month_daily_energy endpoint wrapper."""

    @pytest.mark.asyncio
    async def test_single_inverter_request_and_parse(
        self, analytics: AnalyticsEndpoints, mock_client: Mock
    ) -> None:
        """Single-inverter variant hits monthColumn and parses all fields."""
        mock_client._request.return_value = _single_inverter_response(days=3)

        result = await analytics.get_month_daily_energy("1234567890", 2025, 11)

        mock_client._ensure_authenticated.assert_called_once()
        mock_client._request.assert_called_once_with(
            "POST",
            "/WManage/api/inverterChart/monthColumn",
            data={"serialNum": "1234567890", "year": 2025, "month": 11},
        )

        assert isinstance(result, MonthlyEnergyHistory)
        assert result.success is True
        assert result.year == 2025
        assert result.month == 11
        assert len(result.days) == 3

        first = result.days[0]
        assert first.day == 1
        assert first.eInvDay == 140
        assert first.eToGridDay == 20
        assert result.days[2].day == 3
        assert result.days[2].eInvDay == 142

    @pytest.mark.asyncio
    async def test_parallel_request_uses_parallel_endpoint(
        self, analytics: AnalyticsEndpoints, mock_client: Mock
    ) -> None:
        """Parallel variant hits monthColumnParallel."""
        mock_client._request.return_value = _parallel_response()

        result = await analytics.get_month_daily_energy("1234567890", 2025, 10, parallel=True)

        mock_client._request.assert_called_once_with(
            "POST",
            "/WManage/api/inverterChart/monthColumnParallel",
            data={"serialNum": "1234567890", "year": 2025, "month": 10},
        )
        assert len(result.days) == 2
        assert result.days[0].ePvDay == 300
        assert result.days[0].eExportDay == 40
        # Single-inverter-only fields absent in parallel rows
        assert result.days[0].eInvDay is None
        assert result.days[0].eToGridDay is None

    @pytest.mark.asyncio
    async def test_day_field_used_when_present(
        self, analytics: AnalyticsEndpoints, mock_client: Mock
    ) -> None:
        """An explicit valid day field overrides the row position."""
        mock_client._request.return_value = {
            "success": True,
            "data": [
                {"day": 5, "eInvDay": 10},
                {"day": 6, "eInvDay": 20},
            ],
        }

        result = await analytics.get_month_daily_energy("1234567890", 2025, 1)

        assert [entry.day for entry in result.days] == [5, 6]

    @pytest.mark.asyncio
    async def test_invalid_day_field_falls_back_to_position(
        self, analytics: AnalyticsEndpoints, mock_client: Mock
    ) -> None:
        """Out-of-range or non-int day fields fall back to 1-based position."""
        mock_client._request.return_value = {
            "success": True,
            "data": [
                {"day": 0, "eInvDay": 10},
                {"day": "06", "eInvDay": 20},
                {"day": 99, "eInvDay": 30},
            ],
        }

        result = await analytics.get_month_daily_energy("1234567890", 2025, 1)

        assert [entry.day for entry in result.days] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_non_dict_rows_and_garbage_values_skipped(
        self, analytics: AnalyticsEndpoints, mock_client: Mock
    ) -> None:
        """Non-dict rows are skipped; non-numeric field values become None."""
        mock_client._request.return_value = {
            "success": True,
            "data": [
                {"eInvDay": 10, "eToGridDay": "--", "eChgDay": None},
                "garbage",
                {"eInvDay": True},  # bool is not a valid energy value
            ],
        }

        result = await analytics.get_month_daily_energy("1234567890", 2025, 1)

        assert len(result.days) == 2
        assert result.days[0].eInvDay == 10
        assert result.days[0].eToGridDay is None
        assert result.days[0].eChgDay is None
        # bool filtered out, day index still advances per accepted row
        assert result.days[1].eInvDay is None

    @pytest.mark.asyncio
    async def test_missing_or_non_list_data(
        self, analytics: AnalyticsEndpoints, mock_client: Mock
    ) -> None:
        """Missing or non-list data yields an empty days list."""
        mock_client._request.return_value = {"success": True}
        result = await analytics.get_month_daily_energy("1234567890", 2025, 1)
        assert result.days == []

        mock_client._request.return_value = {"success": False, "data": {"bad": 1}}
        result = await analytics.get_month_daily_energy("1234567890", 2025, 1)
        assert result.success is False
        assert result.days == []


class TestDailyEnergyHistoryEntryScaling:
    """Tests for the 0.1 kWh -> kWh scaling properties."""

    def test_kwh_properties_scale_by_ten(self) -> None:
        """All scaled properties divide raw values by 10."""
        entry = DailyEnergyHistoryEntry(
            day=1,
            eInvDay=144,
            eRecDay=5,
            eChgDay=60,
            eDisChgDay=55,
            eEpsDay=7,
            eToGridDay=20,
            eToUserDay=30,
            eConsumptionDay=150,
        )

        assert entry.inverter_kwh == 14.4
        assert entry.ac_charge_kwh == 0.5
        assert entry.charge_kwh == 6.0
        assert entry.discharge_kwh == 5.5
        assert entry.eps_kwh == 0.7
        assert entry.export_kwh == 2.0
        assert entry.import_kwh == 3.0
        assert entry.consumption_kwh == 15.0

    def test_missing_fields_yield_none(self) -> None:
        """Absent raw fields produce None scaled values."""
        entry = DailyEnergyHistoryEntry(day=1)

        assert entry.pv_kwh is None
        assert entry.inverter_kwh is None
        assert entry.ac_charge_kwh is None
        assert entry.charge_kwh is None
        assert entry.discharge_kwh is None
        assert entry.eps_kwh is None
        assert entry.export_kwh is None
        assert entry.import_kwh is None
        assert entry.consumption_kwh is None

    def test_pv_prefers_aggregate_field(self) -> None:
        """ePvDay (parallel aggregate) wins over per-string fields."""
        entry = DailyEnergyHistoryEntry(day=1, ePvDay=300, ePv1Day=100, ePv2Day=50)
        assert entry.pv_kwh == 30.0

    def test_pv_sums_string_fields(self) -> None:
        """Without ePvDay, PV is the sum of present per-string fields."""
        entry = DailyEnergyHistoryEntry(day=1, ePv1Day=100, ePv2Day=50)
        assert entry.pv_kwh == 15.0

        entry = DailyEnergyHistoryEntry(day=1, ePv1Day=100, ePv2Day=50, ePv3Day=25)
        assert entry.pv_kwh == 17.5

    def test_export_prefers_to_grid_field(self) -> None:
        """eToGridDay (single-inverter) wins over eExportDay (parallel)."""
        entry = DailyEnergyHistoryEntry(day=1, eToGridDay=20, eExportDay=40)
        assert entry.export_kwh == 2.0

        entry = DailyEnergyHistoryEntry(day=1, eExportDay=40)
        assert entry.export_kwh == 4.0

    def test_zero_values_are_not_none(self) -> None:
        """Zero raw values scale to 0.0, not None."""
        entry = DailyEnergyHistoryEntry(day=1, eInvDay=0, eToGridDay=0)
        assert entry.inverter_kwh == 0.0
        assert entry.export_kwh == 0.0
