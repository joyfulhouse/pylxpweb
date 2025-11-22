"""Unit tests for transient error retry functionality."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.constants import MAX_TRANSIENT_ERROR_RETRIES, TRANSIENT_ERROR_MESSAGES
from pylxpweb.exceptions import LuxpowerAPIError


@pytest.fixture
def mock_session():
    """Create a mock aiohttp session."""
    session = Mock()
    return session


@pytest.fixture
def client(mock_session: Mock) -> LuxpowerClient:
    """Create a LuxpowerClient for testing."""
    client = LuxpowerClient(
        username="test_user",
        password="test_pass",
        session=mock_session,
    )
    # Set session to avoid auto-creation
    client._session = mock_session
    client._session_id = "test_session"
    return client


class TestTransientErrorDetection:
    """Test transient error detection."""

    def test_is_transient_error_dataframe_timeout(self, client: LuxpowerClient) -> None:
        """Test DATAFRAME_TIMEOUT is detected as transient."""
        assert client._is_transient_error("DATAFRAME_TIMEOUT")

    def test_is_transient_error_timeout(self, client: LuxpowerClient) -> None:
        """Test TIMEOUT is detected as transient."""
        assert client._is_transient_error("TIMEOUT")

    def test_is_transient_error_busy(self, client: LuxpowerClient) -> None:
        """Test BUSY is detected as transient."""
        assert client._is_transient_error("BUSY")

    def test_is_transient_error_device_busy(self, client: LuxpowerClient) -> None:
        """Test DEVICE_BUSY is detected as transient."""
        assert client._is_transient_error("DEVICE_BUSY")

    def test_is_transient_error_communication_error(self, client: LuxpowerClient) -> None:
        """Test COMMUNICATION_ERROR is detected as transient."""
        assert client._is_transient_error("COMMUNICATION_ERROR")

    def test_is_not_transient_error_api_blocked(self, client: LuxpowerClient) -> None:
        """Test apiBlocked is NOT detected as transient."""
        assert not client._is_transient_error("apiBlocked")

    def test_is_not_transient_error_other(self, client: LuxpowerClient) -> None:
        """Test other errors are NOT detected as transient."""
        assert not client._is_transient_error("Some other error")


class TestTransientErrorRetry:
    """Test automatic retry behavior for transient errors."""

    @pytest.mark.asyncio
    async def test_transient_error_retries_and_succeeds(
        self, client: LuxpowerClient, mock_session: Mock
    ) -> None:
        """Test that transient errors are retried and succeed on retry."""
        # Mock responses: first call returns DATAFRAME_TIMEOUT, second succeeds
        response1 = Mock()
        response1.status = 200
        response1.json = AsyncMock(return_value={"success": False, "msg": "DATAFRAME_TIMEOUT"})
        response1.raise_for_status = Mock()

        response2 = Mock()
        response2.status = 200
        response2.json = AsyncMock(return_value={"success": True, "data": "test_data"})
        response2.raise_for_status = Mock()

        # Create async context managers
        cm1 = AsyncMock()
        cm1.__aenter__.return_value = response1
        cm1.__aexit__.return_value = None

        cm2 = AsyncMock()
        cm2.__aenter__.return_value = response2
        cm2.__aexit__.return_value = None

        mock_session.request = Mock(side_effect=[cm1, cm2])

        # Should succeed after retry
        result = await client._request("POST", "/test/endpoint")
        assert result == {"success": True, "data": "test_data"}
        assert mock_session.request.call_count == 2

    @pytest.mark.asyncio
    async def test_transient_error_max_retries_exceeded(
        self, client: LuxpowerClient, mock_session: Mock
    ) -> None:
        """Test that transient errors raise exception after max retries."""
        # Mock response that always returns DATAFRAME_TIMEOUT
        response = Mock()
        response.status = 200
        response.json = AsyncMock(return_value={"success": False, "msg": "DATAFRAME_TIMEOUT"})
        response.raise_for_status = Mock()

        # Create async context manager
        cm = AsyncMock()
        cm.__aenter__.return_value = response
        cm.__aexit__.return_value = None

        mock_session.request = Mock(return_value=cm)

        # Should raise after MAX_TRANSIENT_ERROR_RETRIES attempts
        with pytest.raises(LuxpowerAPIError, match="DATAFRAME_TIMEOUT"):
            await client._request("POST", "/test/endpoint")

        # Should have tried MAX_TRANSIENT_ERROR_RETRIES + 1 times (initial + retries)
        assert mock_session.request.call_count == MAX_TRANSIENT_ERROR_RETRIES + 1

    @pytest.mark.asyncio
    async def test_non_transient_error_not_retried(
        self, client: LuxpowerClient, mock_session: Mock
    ) -> None:
        """Test that non-transient errors are not retried."""
        # Mock response with non-transient error
        response = Mock()
        response.status = 200
        response.json = AsyncMock(return_value={"success": False, "msg": "apiBlocked"})
        response.raise_for_status = Mock()

        # Create async context manager
        cm = AsyncMock()
        cm.__aenter__.return_value = response
        cm.__aexit__.return_value = None

        mock_session.request = Mock(return_value=cm)

        # Should raise immediately without retry
        with pytest.raises(LuxpowerAPIError, match="apiBlocked"):
            await client._request("POST", "/test/endpoint")

        # Should only be called once (no retry)
        assert mock_session.request.call_count == 1

    @pytest.mark.asyncio
    async def test_transient_error_triggers_backoff(
        self, client: LuxpowerClient, mock_session: Mock
    ) -> None:
        """Test that transient errors trigger exponential backoff."""
        # Mock responses: first returns error, second succeeds
        response1 = Mock()
        response1.status = 200
        response1.json = AsyncMock(return_value={"success": False, "msg": "BUSY"})
        response1.raise_for_status = Mock()

        response2 = Mock()
        response2.status = 200
        response2.json = AsyncMock(return_value={"success": True, "data": "test_data"})
        response2.raise_for_status = Mock()

        # Create async context managers
        cm1 = AsyncMock()
        cm1.__aenter__.return_value = response1
        cm1.__aexit__.return_value = None

        cm2 = AsyncMock()
        cm2.__aenter__.return_value = response2
        cm2.__aexit__.return_value = None

        mock_session.request = Mock(side_effect=[cm1, cm2])

        # Patch _apply_backoff to verify it's called
        with patch.object(client, "_apply_backoff", new_callable=AsyncMock) as mock_backoff:
            result = await client._request("POST", "/test/endpoint")
            assert result == {"success": True, "data": "test_data"}

            # Backoff should be called twice (once per request attempt)
            assert mock_backoff.call_count == 2

    @pytest.mark.asyncio
    async def test_multiple_transient_errors(
        self, client: LuxpowerClient, mock_session: Mock
    ) -> None:
        """Test retry with multiple different transient errors."""
        # Mock responses with different transient errors
        response1 = Mock()
        response1.status = 200
        response1.json = AsyncMock(return_value={"success": False, "msg": "DATAFRAME_TIMEOUT"})
        response1.raise_for_status = Mock()

        response2 = Mock()
        response2.status = 200
        response2.json = AsyncMock(return_value={"success": False, "msg": "BUSY"})
        response2.raise_for_status = Mock()

        response3 = Mock()
        response3.status = 200
        response3.json = AsyncMock(return_value={"success": True, "data": "test_data"})
        response3.raise_for_status = Mock()

        # Create async context managers
        cm1 = AsyncMock()
        cm1.__aenter__.return_value = response1
        cm1.__aexit__.return_value = None

        cm2 = AsyncMock()
        cm2.__aenter__.return_value = response2
        cm2.__aexit__.return_value = None

        cm3 = AsyncMock()
        cm3.__aenter__.return_value = response3
        cm3.__aexit__.return_value = None

        mock_session.request = Mock(side_effect=[cm1, cm2, cm3])

        # Should succeed after multiple retries
        result = await client._request("POST", "/test/endpoint")
        assert result == {"success": True, "data": "test_data"}
        assert mock_session.request.call_count == 3


class TestTransientErrorConstants:
    """Test transient error constants configuration."""

    def test_transient_error_messages_defined(self) -> None:
        """Test that TRANSIENT_ERROR_MESSAGES is properly defined."""
        assert len(TRANSIENT_ERROR_MESSAGES) > 0
        assert "DATAFRAME_TIMEOUT" in TRANSIENT_ERROR_MESSAGES
        assert "TIMEOUT" in TRANSIENT_ERROR_MESSAGES
        assert "BUSY" in TRANSIENT_ERROR_MESSAGES

    def test_max_retries_defined(self) -> None:
        """Test that MAX_TRANSIENT_ERROR_RETRIES is properly defined."""
        assert MAX_TRANSIENT_ERROR_RETRIES > 0
        assert MAX_TRANSIENT_ERROR_RETRIES <= 5  # Reasonable upper bound
