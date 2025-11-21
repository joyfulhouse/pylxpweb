"""Unit tests for date boundary detection and monotonic value enforcement.

This module tests the critical date boundary and monotonic value behavior
implemented in Station and BaseInverter to prevent stale data issues at
midnight and hour boundaries.

Reference: docs/SCALING_GUIDE.md - Date Boundary Handling
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from pylxpweb.client import LuxpowerClient
from pylxpweb.devices.inverters.generic import GenericInverter
from pylxpweb.devices.station import Location, Station
from pylxpweb.models import EnergyInfo


class TestStationDateDetection:
    """Test Station.get_current_date() method for timezone-aware date detection."""

    def test_timezone_gmt_minus_8(self):
        """Test timezone parsing for GMT -8 (PST)."""
        client = Mock(spec=LuxpowerClient)
        station = Station(
            client=client,
            plant_id=12345,
            name="Test Station",
            location=Location(address="", latitude=0.0, longitude=0.0, country=""),
            timezone="GMT -8",
            created_date=datetime.now(),
        )

        # Mock datetime.now to return a known UTC time
        utc_time = datetime(2025, 11, 21, 10, 30, tzinfo=UTC)  # 10:30 UTC
        with patch("pylxpweb.devices.station.datetime") as mock_dt:
            # Return timezone-aware datetime
            pst_time = utc_time.astimezone(timezone(timedelta(hours=-8)))  # 02:30 PST
            mock_dt.now.return_value = pst_time

            result = station.get_current_date()

        assert result == "2025-11-21"

    def test_timezone_gmt_plus_9(self):
        """Test timezone parsing for GMT +9 (JST)."""
        client = Mock(spec=LuxpowerClient)
        station = Station(
            client=client,
            plant_id=12345,
            name="Test Station",
            location=Location(address="", latitude=0.0, longitude=0.0, country=""),
            timezone="GMT +9",
            created_date=datetime.now(),
        )

        utc_time = datetime(2025, 11, 21, 15, 30, tzinfo=UTC)  # 15:30 UTC
        with patch("pylxpweb.devices.station.datetime") as mock_dt:
            jst_time = utc_time.astimezone(timezone(timedelta(hours=9)))  # 00:30 JST next day
            mock_dt.now.return_value = jst_time

            result = station.get_current_date()

        assert result == "2025-11-22"  # Next day in JST

    def test_timezone_invalid_format(self):
        """Test graceful handling of invalid timezone format."""
        client = Mock(spec=LuxpowerClient)
        station = Station(
            client=client,
            plant_id=12345,
            name="Test Station",
            location=Location(address="", latitude=0.0, longitude=0.0, country=""),
            timezone="Invalid/Timezone",
            created_date=datetime.now(),
        )

        with patch("pylxpweb.devices.station.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 11, 21, 10, 30, tzinfo=UTC)

            result = station.get_current_date()

        # Should fall back to UTC
        assert result == "2025-11-21"

    def test_timezone_missing(self):
        """Test handling when timezone is None or empty."""
        client = Mock(spec=LuxpowerClient)
        station = Station(
            client=client,
            plant_id=12345,
            name="Test Station",
            location=Location(address="", latitude=0.0, longitude=0.0, country=""),
            timezone="",
            created_date=datetime.now(),
        )

        with patch("pylxpweb.devices.station.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 11, 21, 10, 30, tzinfo=UTC)

            result = station.get_current_date()

        # Should fall back to UTC
        assert result == "2025-11-21"

    def test_timezone_uses_current_timezone_with_minute(self):
        """Test that currentTimezoneWithMinute takes priority over timezone string."""
        client = Mock(spec=LuxpowerClient)
        station = Station(
            client=client,
            plant_id=12345,
            name="Test Station",
            location=Location(address="", latitude=0.0, longitude=0.0, country=""),
            timezone="GMT -8",  # PST
            created_date=datetime.now(),
            current_timezone_with_minute=-420,  # PDT (7 hours behind UTC)
        )

        utc_time = datetime(2025, 11, 21, 10, 30, tzinfo=UTC)  # 10:30 UTC
        with patch("pylxpweb.devices.station.datetime") as mock_dt:
            # Should use -420 minutes (PDT), not GMT -8
            pdt_time = utc_time.astimezone(timezone(timedelta(minutes=-420)))  # 03:30 PDT
            mock_dt.now.return_value = pdt_time

            result = station.get_current_date()

        assert result == "2025-11-21"


class TestStationDSTDetection:
    """Test Station.detect_dst_status() method for DST detection."""

    def test_dst_active_pacific_time(self):
        """Test DST detection when DST is active (PDT)."""
        client = Mock(spec=LuxpowerClient)
        station = Station(
            client=client,
            plant_id=12345,
            name="Test Station",
            location=Location(address="", latitude=0.0, longitude=0.0, country=""),
            timezone="GMT -8",  # PST base
            created_date=datetime.now(),
            current_timezone_with_minute=-420,  # PDT (DST active)
        )

        result = station.detect_dst_status()

        assert result is True  # DST is active (difference = -7 - (-8) = 1 hour)

    def test_dst_inactive_pacific_time(self):
        """Test DST detection when DST is inactive (PST)."""
        client = Mock(spec=LuxpowerClient)
        station = Station(
            client=client,
            plant_id=12345,
            name="Test Station",
            location=Location(address="", latitude=0.0, longitude=0.0, country=""),
            timezone="GMT -8",  # PST base
            created_date=datetime.now(),
            current_timezone_with_minute=-480,  # PST (DST inactive)
        )

        result = station.detect_dst_status()

        assert result is False  # DST is inactive (difference = -8 - (-8) = 0)

    def test_dst_active_eastern_time(self):
        """Test DST detection for Eastern Time when DST is active (EDT)."""
        client = Mock(spec=LuxpowerClient)
        station = Station(
            client=client,
            plant_id=12345,
            name="Test Station",
            location=Location(address="", latitude=0.0, longitude=0.0, country=""),
            timezone="GMT -5",  # EST base
            created_date=datetime.now(),
            current_timezone_with_minute=-240,  # EDT (DST active)
        )

        result = station.detect_dst_status()

        assert result is True  # DST is active (difference = -4 - (-5) = 1 hour)

    def test_dst_inactive_eastern_time(self):
        """Test DST detection for Eastern Time when DST is inactive (EST)."""
        client = Mock(spec=LuxpowerClient)
        station = Station(
            client=client,
            plant_id=12345,
            name="Test Station",
            location=Location(address="", latitude=0.0, longitude=0.0, country=""),
            timezone="GMT -5",  # EST base
            created_date=datetime.now(),
            current_timezone_with_minute=-300,  # EST (DST inactive)
        )

        result = station.detect_dst_status()

        assert result is False  # DST is inactive (difference = -5 - (-5) = 0)

    def test_dst_europe_summer_time(self):
        """Test DST detection for Central European Time (CEST)."""
        client = Mock(spec=LuxpowerClient)
        station = Station(
            client=client,
            plant_id=12345,
            name="Test Station",
            location=Location(address="", latitude=0.0, longitude=0.0, country=""),
            timezone="GMT +1",  # CET base
            created_date=datetime.now(),
            current_timezone_with_minute=120,  # CEST (DST active)
        )

        result = station.detect_dst_status()

        assert result is True  # DST is active (difference = 2 - 1 = 1 hour)

    def test_dst_no_current_timezone_with_minute(self):
        """Test DST detection when currentTimezoneWithMinute is not available."""
        client = Mock(spec=LuxpowerClient)
        station = Station(
            client=client,
            plant_id=12345,
            name="Test Station",
            location=Location(address="", latitude=0.0, longitude=0.0, country=""),
            timezone="GMT -8",
            created_date=datetime.now(),
            current_timezone_with_minute=None,  # Not available
        )

        result = station.detect_dst_status()

        assert result is None  # Cannot determine

    def test_dst_invalid_timezone_format(self):
        """Test DST detection with invalid timezone format."""
        client = Mock(spec=LuxpowerClient)
        station = Station(
            client=client,
            plant_id=12345,
            name="Test Station",
            location=Location(address="", latitude=0.0, longitude=0.0, country=""),
            timezone="Invalid/Timezone",
            created_date=datetime.now(),
            current_timezone_with_minute=-420,
        )

        result = station.detect_dst_status()

        assert result is None  # Cannot parse base timezone


class TestStationDSTSync:
    """Test Station.sync_dst_setting() method for API synchronization."""

    @pytest.mark.asyncio
    async def test_sync_corrects_wrong_dst_flag(self):
        """Test that sync_dst_setting corrects wrong API DST flag."""
        client = Mock(spec=LuxpowerClient)

        # Mock successful API call
        async def mock_set_dst(plant_id: int, enabled: bool) -> dict[str, bool]:
            return {"success": True}

        client.api.plants.set_daylight_saving_time = Mock(side_effect=mock_set_dst)

        station = Station(
            client=client,
            plant_id=12345,
            name="Test Station",
            location=Location(address="", latitude=0.0, longitude=0.0, country=""),
            timezone="GMT -8",  # PST base
            created_date=datetime.now(),
            current_timezone_with_minute=-420,  # PDT (DST active)
            daylight_saving_time=False,  # WRONG - API says no DST but offset says yes
        )

        result = await station.sync_dst_setting()

        assert result is True
        assert station.daylight_saving_time is True  # Should be corrected
        client.api.plants.set_daylight_saving_time.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_skips_when_correct(self):
        """Test that sync_dst_setting skips update when DST is already correct."""
        client = Mock(spec=LuxpowerClient)

        # Mock API call (should NOT be called)
        client.api.plants.set_daylight_saving_time = Mock()

        station = Station(
            client=client,
            plant_id=12345,
            name="Test Station",
            location=Location(address="", latitude=0.0, longitude=0.0, country=""),
            timezone="GMT -8",  # PST base
            created_date=datetime.now(),
            current_timezone_with_minute=-480,  # PST (DST inactive)
            daylight_saving_time=False,  # CORRECT - matches offset
        )

        result = await station.sync_dst_setting()

        assert result is True
        client.api.plants.set_daylight_saving_time.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_handles_api_failure(self):
        """Test that sync_dst_setting handles API failures gracefully."""
        client = Mock(spec=LuxpowerClient)

        # Mock failed API call
        async def mock_set_dst_fail(plant_id: int, enabled: bool) -> dict[str, bool]:
            return {"success": False}

        client.api.plants.set_daylight_saving_time = Mock(side_effect=mock_set_dst_fail)

        station = Station(
            client=client,
            plant_id=12345,
            name="Test Station",
            location=Location(address="", latitude=0.0, longitude=0.0, country=""),
            timezone="GMT -8",  # PST base
            created_date=datetime.now(),
            current_timezone_with_minute=-420,  # PDT (DST active)
            daylight_saving_time=False,  # WRONG
        )

        result = await station.sync_dst_setting()

        assert result is False
        assert station.daylight_saving_time is False  # Should NOT be updated on failure

    @pytest.mark.asyncio
    async def test_sync_cannot_determine_dst(self):
        """Test that sync_dst_setting skips when DST cannot be determined."""
        client = Mock(spec=LuxpowerClient)

        # Mock API call (should NOT be called)
        client.api.plants.set_daylight_saving_time = Mock()

        station = Station(
            client=client,
            plant_id=12345,
            name="Test Station",
            location=Location(address="", latitude=0.0, longitude=0.0, country=""),
            timezone="GMT -8",
            created_date=datetime.now(),
            current_timezone_with_minute=None,  # Cannot determine
            daylight_saving_time=False,
        )

        result = await station.sync_dst_setting()

        assert result is False
        client.api.plants.set_daylight_saving_time.assert_not_called()


class TestMonotonicEnergyTracking:
    """Test monotonic value enforcement in BaseInverter energy properties."""

    def test_daily_energy_increases_normally(self):
        """Test that daily energy increases normally within same day."""
        client = Mock(spec=LuxpowerClient)
        inverter = GenericInverter(client, "1234567890", "18KPV")

        # Set date to today
        inverter._last_energy_date = "2025-11-21"
        inverter._last_energy_today = 45.5

        # API returns higher value
        inverter.energy = EnergyInfo.model_construct(todayYielding=46500)  # 46.5 kWh (in Wh)

        result = inverter.total_energy_today

        assert result == 46.5
        assert inverter._last_energy_today == 46.5

    def test_daily_energy_rejects_decrease(self):
        """Test that daily energy rejects decreases within same day."""
        client = Mock(spec=LuxpowerClient)
        inverter = GenericInverter(client, "1234567890", "18KPV")

        # Set date to today
        inverter._last_energy_date = "2025-11-21"
        inverter._last_energy_today = 45.5

        # API returns lower value (stale cache)
        inverter.energy = EnergyInfo.model_construct(todayYielding=45000)  # 45.0 kWh

        result = inverter.total_energy_today

        # Should maintain previous value
        assert result == 45.5
        assert inverter._last_energy_today == 45.5

    def test_daily_energy_rejects_zero_without_date_change(self):
        """Test that daily energy rejects decrease to 0 without date change.

        Note: Our current implementation treats 0 as stale data within the same day
        to prevent false resets from API cache issues. Manual resets would typically
        occur at midnight (date boundary), which would force the reset properly.
        """
        client = Mock(spec=LuxpowerClient)
        inverter = GenericInverter(client, "1234567890", "18KPV")

        inverter._last_energy_date = "2025-11-21"
        inverter._last_energy_today = 45.5

        # API returns 0 (likely stale cache showing post-midnight value)
        inverter.energy = EnergyInfo.model_construct(todayYielding=0)

        result = inverter.total_energy_today

        # Should reject decrease to protect against stale data
        assert result == 45.5
        assert inverter._last_energy_today == 45.5

    def test_lifetime_energy_never_decreases(self):
        """Test that lifetime energy never decreases."""
        client = Mock(spec=LuxpowerClient)
        inverter = GenericInverter(client, "1234567890", "18KPV")

        inverter._last_energy_lifetime = 12345.6

        # API returns lower value
        inverter.energy = EnergyInfo.model_construct(totalYielding=12300000)  # 12300.0 kWh (in Wh)

        result = inverter.total_energy_lifetime

        # Should maintain previous value
        assert result == 12345.6
        assert inverter._last_energy_lifetime == 12345.6

    def test_lifetime_energy_allows_increase(self):
        """Test that lifetime energy accepts increases."""
        client = Mock(spec=LuxpowerClient)
        inverter = GenericInverter(client, "1234567890", "18KPV")

        inverter._last_energy_lifetime = 12345.6

        # API returns higher value
        inverter.energy = EnergyInfo.model_construct(totalYielding=12350000)  # 12350.0 kWh

        result = inverter.total_energy_lifetime

        assert result == 12350.0
        assert inverter._last_energy_lifetime == 12350.0

    def test_lifetime_energy_never_resets_to_zero(self):
        """Test that lifetime energy rejects reset to 0."""
        client = Mock(spec=LuxpowerClient)
        inverter = GenericInverter(client, "1234567890", "18KPV")

        inverter._last_energy_lifetime = 12345.6

        # API returns 0 (should be rejected)
        inverter.energy = EnergyInfo.model_construct(totalYielding=0)

        result = inverter.total_energy_lifetime

        # Should maintain previous value
        assert result == 12345.6
        assert inverter._last_energy_lifetime == 12345.6


class TestCacheInvalidation:
    """Test cache invalidation logic in LuxpowerClient."""

    def test_should_invalidate_within_5_minutes_first_run(self):
        """Test cache invalidation within 5-minute window on first run."""
        client = LuxpowerClient("user", "pass")

        # Mock datetime to be at 23:57 (3 minutes before hour)
        with patch("pylxpweb.client.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 11, 21, 23, 57)

            result = client.should_invalidate_cache()

        assert result is True

    def test_should_not_invalidate_outside_window(self):
        """Test no invalidation outside 5-minute window."""
        client = LuxpowerClient("user", "pass")

        # Mock datetime to be at 23:50 (10 minutes before hour)
        with patch("pylxpweb.client.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 11, 21, 23, 50)

            result = client.should_invalidate_cache()

        assert result is False

    def test_should_invalidate_on_hour_crossing(self):
        """Test invalidation when hour boundary is crossed."""
        client = LuxpowerClient("user", "pass")
        client._last_cache_invalidation = datetime(2025, 11, 21, 23, 58)

        # Mock datetime to be in next hour, but within 5-minute window
        # 00:57 is 3 minutes before next hour boundary (01:00)
        with patch("pylxpweb.client.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 11, 22, 0, 57)

            result = client.should_invalidate_cache()

        assert result is True

    def test_rate_limiting_within_window(self):
        """Test rate limiting prevents frequent invalidations."""
        client = LuxpowerClient("user", "pass")
        client._last_cache_invalidation = datetime(2025, 11, 21, 23, 52)

        # Mock datetime to be 5 minutes later (still within rate limit)
        with patch("pylxpweb.client.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 11, 21, 23, 57)

            result = client.should_invalidate_cache()

        # Should not invalidate (less than 10 minutes since last)
        assert result is False

    def test_invalidate_after_rate_limit_expires(self):
        """Test invalidation after rate limit expires."""
        client = LuxpowerClient("user", "pass")
        client._last_cache_invalidation = datetime(2025, 11, 21, 23, 45)

        # Mock datetime to be 12 minutes later (rate limit expired)
        with patch("pylxpweb.client.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 11, 21, 23, 57)

            result = client.should_invalidate_cache()

        # Should invalidate (more than 10 minutes since last)
        assert result is True

    def test_clear_all_caches_updates_timestamp(self):
        """Test that clear_all_caches updates invalidation timestamp."""
        client = LuxpowerClient("user", "pass")

        with patch("pylxpweb.client.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 11, 21, 23, 58)

            client.clear_all_caches()

        assert client._last_cache_invalidation == datetime(2025, 11, 21, 23, 58)

    def test_clear_all_caches_clears_response_cache(self):
        """Test that clear_all_caches clears the response cache."""
        client = LuxpowerClient("user", "pass")

        # Add some cached data
        client._response_cache["test_key"] = {"data": "value"}

        client.clear_all_caches()

        assert len(client._response_cache) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
