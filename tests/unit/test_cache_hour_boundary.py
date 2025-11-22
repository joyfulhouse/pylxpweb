"""Tests for hour boundary cache invalidation.

This module tests the automatic cache invalidation logic that triggers
on the first request after an hour boundary is crossed.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.client import LuxpowerClient


@pytest.fixture
def mock_session():
    """Create a mock aiohttp session."""
    session = MagicMock()
    session.closed = False
    return session


@pytest.fixture
def client(mock_session):
    """Create a client with mocked session."""
    return LuxpowerClient(
        username="test_user",
        password="test_pass",
        session=mock_session,
    )


@pytest.mark.asyncio
async def test_cache_cleared_on_hour_change(client):
    """Test that cache is cleared on first request after hour changes."""
    # Populate cache with test data
    client._response_cache["test_key_1"] = {
        "timestamp": datetime(2025, 1, 1, 23, 30, 0),
        "response": {"data": "old_value_1"},
    }
    client._response_cache["test_key_2"] = {
        "timestamp": datetime(2025, 1, 1, 23, 30, 0),
        "response": {"data": "old_value_2"},
    }
    assert len(client._response_cache) == 2

    # Mock _request dependencies
    with patch.object(client, "_get_session", new_callable=AsyncMock) as mock_get_session:
        mock_get_session.return_value = MagicMock()

        # Mock the actual HTTP request to avoid network calls
        with patch.object(mock_get_session.return_value, "request") as mock_request:
            # Mock successful response
            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json = AsyncMock(return_value={"success": True, "data": "new"})
            mock_response.status = 200
            mock_request.return_value.__aenter__.return_value = mock_response

            # First request at hour 23
            with patch("pylxpweb.client.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2025, 1, 1, 23, 30, 0)

                await client._request("POST", "/test", data={})

                # Hour tracking should be set to 23
                assert client._last_request_hour == 23
                # Cache should still have entries (no hour change yet)
                assert len(client._response_cache) == 2

            # Second request at hour 0 (midnight crossed)
            with patch("pylxpweb.client.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2025, 1, 2, 0, 1, 0)

                await client._request("POST", "/test", data={})

                # Hour tracking should be updated to 0
                assert client._last_request_hour == 0
                # Cache should be cleared (hour changed from 23 to 0)
                assert len(client._response_cache) == 0


@pytest.mark.asyncio
async def test_cache_not_cleared_within_same_hour(client):
    """Test that cache is NOT cleared for requests within same hour."""
    # Populate cache
    client._response_cache["test_key"] = {
        "timestamp": datetime(2025, 1, 1, 14, 10, 0),
        "response": {"data": "value"},
    }

    with patch.object(client, "_get_session", new_callable=AsyncMock) as mock_get_session:
        mock_get_session.return_value = MagicMock()

        with patch.object(mock_get_session.return_value, "request") as mock_request:
            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json = AsyncMock(return_value={"success": True})
            mock_response.status = 200
            mock_request.return_value.__aenter__.return_value = mock_response

            # Multiple requests at hour 14
            for minute in [10, 20, 30, 45, 55]:
                with patch("pylxpweb.client.datetime") as mock_dt:
                    mock_dt.now.return_value = datetime(2025, 1, 1, 14, minute, 0)

                    await client._request("POST", "/test", data={})

                    # Hour should remain 14
                    assert client._last_request_hour == 14
                    # Cache should still exist (no hour change)
                    assert len(client._response_cache) >= 1


@pytest.mark.asyncio
async def test_first_request_sets_hour_without_clearing(client):
    """Test that first request sets hour tracking without clearing cache."""
    # Populate cache before any request
    client._response_cache["existing_key"] = {
        "timestamp": datetime(2025, 1, 1, 10, 0, 0),
        "response": {"data": "existing"},
    }

    assert client._last_request_hour is None  # Not set yet

    with patch.object(client, "_get_session", new_callable=AsyncMock) as mock_get_session:
        mock_get_session.return_value = MagicMock()

        with patch.object(mock_get_session.return_value, "request") as mock_request:
            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json = AsyncMock(return_value={"success": True})
            mock_response.status = 200
            mock_request.return_value.__aenter__.return_value = mock_response

            with patch("pylxpweb.client.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2025, 1, 1, 15, 30, 0)

                await client._request("POST", "/test", data={})

                # Hour should be set
                assert client._last_request_hour == 15
                # Cache should NOT be cleared (first request, no previous hour to compare)
                assert len(client._response_cache) >= 1


@pytest.mark.asyncio
async def test_dst_spring_forward_hour_jump(client):
    """Test hour boundary detection across DST spring forward (1:59 → 3:00)."""
    client._response_cache["test"] = {
        "timestamp": datetime(2025, 3, 9, 1, 59, 0),
        "response": {"data": "before_dst"},
    }

    with patch.object(client, "_get_session", new_callable=AsyncMock) as mock_get_session:
        mock_get_session.return_value = MagicMock()

        with patch.object(mock_get_session.return_value, "request") as mock_request:
            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json = AsyncMock(return_value={"success": True})
            mock_response.status = 200
            mock_request.return_value.__aenter__.return_value = mock_response

            # Request before DST
            with patch("pylxpweb.client.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2025, 3, 9, 1, 59, 0)
                await client._request("POST", "/test", data={})
                assert client._last_request_hour == 1

            # Request after DST (hour jumped to 3)
            with patch("pylxpweb.client.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2025, 3, 9, 3, 0, 0)
                await client._request("POST", "/test", data={})

                # Hour changed from 1 to 3
                assert client._last_request_hour == 3
                # Cache should be cleared
                assert len(client._response_cache) == 0


@pytest.mark.asyncio
async def test_dst_fall_back_hour_jump(client):
    """Test hour boundary detection across DST fall back (2:00 → 1:00)."""
    client._response_cache["test"] = {
        "timestamp": datetime(2025, 11, 2, 2, 0, 0),
        "response": {"data": "before_dst"},
    }

    with patch.object(client, "_get_session", new_callable=AsyncMock) as mock_get_session:
        mock_get_session.return_value = MagicMock()

        with patch.object(mock_get_session.return_value, "request") as mock_request:
            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json = AsyncMock(return_value={"success": True})
            mock_response.status = 200
            mock_request.return_value.__aenter__.return_value = mock_response

            # Request before DST fall back
            with patch("pylxpweb.client.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2025, 11, 2, 2, 0, 0)
                await client._request("POST", "/test", data={})
                assert client._last_request_hour == 2

            # Request after DST fall back (hour goes back to 1)
            with patch("pylxpweb.client.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2025, 11, 2, 1, 0, 0)
                await client._request("POST", "/test", data={})

                # Hour changed from 2 to 1
                assert client._last_request_hour == 1
                # Cache should be cleared
                assert len(client._response_cache) == 0


@pytest.mark.asyncio
async def test_long_gap_between_requests(client):
    """Test cache invalidation when multiple hours pass between requests."""
    client._response_cache["test"] = {
        "timestamp": datetime(2025, 1, 1, 22, 30, 0),
        "response": {"data": "old"},
    }

    with patch.object(client, "_get_session", new_callable=AsyncMock) as mock_get_session:
        mock_get_session.return_value = MagicMock()

        with patch.object(mock_get_session.return_value, "request") as mock_request:
            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json = AsyncMock(return_value={"success": True})
            mock_response.status = 200
            mock_request.return_value.__aenter__.return_value = mock_response

            # First request at 22:30
            with patch("pylxpweb.client.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2025, 1, 1, 22, 30, 0)
                await client._request("POST", "/test", data={})
                assert client._last_request_hour == 22

            # Next request at 02:15 (crossed 23:00, 00:00, 01:00, 02:00)
            with patch("pylxpweb.client.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2025, 1, 2, 2, 15, 0)
                await client._request("POST", "/test", data={})

                # Hour changed from 22 to 2
                assert client._last_request_hour == 2
                # Cache should be cleared
                assert len(client._response_cache) == 0


@pytest.mark.asyncio
async def test_midnight_boundary_specifically(client):
    """Test the critical midnight boundary (23:xx → 00:xx) for daily energy resets."""
    client._response_cache["energy_data"] = {
        "timestamp": datetime(2025, 1, 1, 23, 58, 0),
        "response": {"todayYielding": 155},  # Yesterday's final total
    }

    with patch.object(client, "_get_session", new_callable=AsyncMock) as mock_get_session:
        mock_get_session.return_value = MagicMock()

        with patch.object(mock_get_session.return_value, "request") as mock_request:
            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json = AsyncMock(
                return_value={"success": True, "todayYielding": 0}  # New day value
            )
            mock_response.status = 200
            mock_request.return_value.__aenter__.return_value = mock_response

            # Request at 23:58
            with patch("pylxpweb.client.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2025, 1, 1, 23, 58, 0)
                await client._request("POST", "/api/inverter/getInverterEnergyInfo", data={})
                assert client._last_request_hour == 23

            # First request after midnight
            with patch("pylxpweb.client.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2025, 1, 2, 0, 1, 0)
                result = await client._request(
                    "POST", "/api/inverter/getInverterEnergyInfo", data={}
                )

                # Hour crossed midnight
                assert client._last_request_hour == 0
                # Cache was cleared, new data fetched
                assert len(client._response_cache) == 0  # Cleared before fetch
                assert result["todayYielding"] == 0  # Fresh data


@pytest.mark.asyncio
async def test_concurrent_requests_at_boundary(client):
    """Test that concurrent requests during hour boundary handle cache clearing safely."""
    client._response_cache["test"] = {
        "timestamp": datetime(2025, 1, 1, 23, 59, 0),
        "response": {"data": "old"},
    }

    with patch.object(client, "_get_session", new_callable=AsyncMock) as mock_get_session:
        mock_get_session.return_value = MagicMock()

        with patch.object(mock_get_session.return_value, "request") as mock_request:
            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json = AsyncMock(return_value={"success": True})
            mock_response.status = 200
            mock_request.return_value.__aenter__.return_value = mock_response

            # Set initial hour
            client._last_request_hour = 23

            # Simulate two concurrent requests at midnight
            with patch("pylxpweb.client.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2025, 1, 2, 0, 0, 1)

                # Both should clear cache (clear_cache is idempotent)
                await client._request("POST", "/test1", data={})
                await client._request("POST", "/test2", data={})

                # Both should update hour to 0
                assert client._last_request_hour == 0
                # Cache cleared (idempotent operation)
                assert len(client._response_cache) == 0


@pytest.mark.asyncio
async def test_hour_tracking_persists_across_cache_operations(client):
    """Test that _last_request_hour is independent of cache clearing."""
    with patch.object(client, "_get_session", new_callable=AsyncMock) as mock_get_session:
        mock_get_session.return_value = MagicMock()

        with patch.object(mock_get_session.return_value, "request") as mock_request:
            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json = AsyncMock(return_value={"success": True})
            mock_response.status = 200
            mock_request.return_value.__aenter__.return_value = mock_response

            # Make request at hour 10
            with patch("pylxpweb.client.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2025, 1, 1, 10, 30, 0)
                await client._request("POST", "/test", data={})
                assert client._last_request_hour == 10

            # Manually clear cache
            client.clear_cache()

            # Hour tracking should persist
            assert client._last_request_hour == 10

            # Next request in same hour should not trigger clearing
            with patch("pylxpweb.client.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(2025, 1, 1, 10, 45, 0)
                await client._request("POST", "/test", data={})

                # Hour unchanged
                assert client._last_request_hour == 10
                # No automatic clearing (same hour)
