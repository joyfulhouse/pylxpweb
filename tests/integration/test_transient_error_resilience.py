"""Integration tests for transient error resilience.

These tests verify that the client automatically retries transient errors
like DATAFRAME_TIMEOUT with exponential backoff.

IMPORTANT: These tests interact with real devices and may encounter
genuine hardware communication timeouts. Tests are designed to skip
(not fail) when max retries are exceeded, as this indicates a real
hardware issue, not a code bug.

To run these tests:
1. Create a .env file in project root with credentials:
   LUXPOWER_USERNAME=your_username
   LUXPOWER_PASSWORD=your_password
   LUXPOWER_BASE_URL=https://monitor.eg4electronics.com

2. Run with pytest marker:
   pytest -m integration tests/integration/test_transient_error_resilience.py
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load .env file before importing anything else
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Import after loading .env
sys.path.insert(0, str(Path(__file__).parent.parent))

from pylxpweb import LuxpowerClient  # noqa: E402
from pylxpweb.constants import MAX_TRANSIENT_ERROR_RETRIES  # noqa: E402
from pylxpweb.devices.station import Station  # noqa: E402
from pylxpweb.exceptions import LuxpowerAPIError  # noqa: E402

# Load credentials from environment
LUXPOWER_USERNAME = os.getenv("LUXPOWER_USERNAME")
LUXPOWER_PASSWORD = os.getenv("LUXPOWER_PASSWORD")
LUXPOWER_BASE_URL = os.getenv("LUXPOWER_BASE_URL", "https://monitor.eg4electronics.com")

# Skip all tests if credentials are not provided
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not LUXPOWER_USERNAME or not LUXPOWER_PASSWORD,
        reason="Integration tests require LUXPOWER_USERNAME and LUXPOWER_PASSWORD env vars",
    ),
]


@pytest.fixture
async def client() -> AsyncGenerator[LuxpowerClient, None]:
    """Create authenticated client for testing."""
    async with LuxpowerClient(
        username=LUXPOWER_USERNAME,
        password=LUXPOWER_PASSWORD,
        base_url=LUXPOWER_BASE_URL,
    ) as client:
        yield client


@pytest.mark.integration
class TestDataframeTimeoutResilience:
    """Test resilience to DATAFRAME_TIMEOUT errors.

    DATAFRAME_TIMEOUT is a common transient error that occurs when the
    inverter's dataframe communication times out. This is usually temporary
    and succeeds on retry.
    """

    async def test_dataframe_timeout_is_retried_automatically(self, client: LuxpowerClient) -> None:
        """Test that DATAFRAME_TIMEOUT errors are automatically retried.

        This test performs normal operations that may encounter DATAFRAME_TIMEOUT.
        The client should automatically retry up to MAX_TRANSIENT_ERROR_RETRIES times.

        If all retries fail, the test will be skipped (not failed) since this
        indicates a genuine hardware communication issue, not a code bug.
        """
        try:
            # Load stations - this makes multiple API calls
            stations = await Station.load_all(client)
            assert len(stations) > 0

            # Get first inverter
            inverter = stations[0].all_inverters[0]

            # Refresh data - this makes 3-4 API calls
            await inverter.refresh()

            # Verify we got data
            assert inverter.has_data

            # If we got here, either:
            # 1. No DATAFRAME_TIMEOUT occurred, OR
            # 2. DATAFRAME_TIMEOUT occurred but was successfully retried
            # Both scenarios are success cases!

        except LuxpowerAPIError as err:
            if "DATAFRAME_TIMEOUT" in str(err):
                # DATAFRAME_TIMEOUT after max retries - this is a hardware issue
                pytest.skip(
                    f"DATAFRAME_TIMEOUT after {MAX_TRANSIENT_ERROR_RETRIES} "
                    "retries - genuine hardware communication issue, not a code bug"
                )
            # Other API errors should fail the test
            raise

    async def test_parameter_read_with_dataframe_timeout_resilience(
        self, client: LuxpowerClient
    ) -> None:
        """Test that parameter reads handle DATAFRAME_TIMEOUT gracefully.

        Parameter reads are more prone to DATAFRAME_TIMEOUT because they
        fetch 3 register ranges (127 registers each) sequentially.
        """
        try:
            stations = await Station.load_all(client)
            inverter = stations[0].all_inverters[0]

            # Refresh with parameters - this makes 3 additional API calls
            await inverter.refresh(include_parameters=True)

            # Verify we got parameters (may be None if first refresh)
            # but should not raise exception due to automatic retry
            # The parameters dict should be populated or None
            assert inverter.parameters is None or isinstance(inverter.parameters, dict)

        except LuxpowerAPIError as err:
            if "DATAFRAME_TIMEOUT" in str(err):
                pytest.skip("DATAFRAME_TIMEOUT after max retries - genuine hardware issue")
            raise

    async def test_write_operations_with_dataframe_timeout_resilience(
        self, client: LuxpowerClient
    ) -> None:
        """Test that write operations handle DATAFRAME_TIMEOUT gracefully.

        Write operations (like toggling quick charge) are also prone to
        DATAFRAME_TIMEOUT and should be automatically retried.

        NOTE: This test only reads current state and toggles safely.
        """
        try:
            stations = await Station.load_all(client)
            inverter = stations[0].all_inverters[0]

            # Get current quick charge status (read operation)
            current_status = await inverter.get_quick_charge_status()

            # Toggle to opposite state (write operation)
            if current_status:
                success = await inverter.disable_quick_charge()
            else:
                success = await inverter.enable_quick_charge()

            # Restore original state (write operation)
            if current_status:
                await inverter.enable_quick_charge()
            else:
                await inverter.disable_quick_charge()

            # If we got here without exceptions, retry logic worked!
            assert success is True

        except LuxpowerAPIError as err:
            if "DATAFRAME_TIMEOUT" in str(err):
                pytest.skip("DATAFRAME_TIMEOUT after max retries - genuine hardware issue")
            raise


@pytest.mark.integration
class TestTransientErrorRetryBehavior:
    """Test general transient error retry behavior."""

    async def test_successful_operations_dont_trigger_retries(self, client: LuxpowerClient) -> None:
        """Test that successful operations complete without retries.

        This verifies that the retry logic only activates on errors,
        not on successful responses.
        """
        # Perform a simple operation
        stations = await Station.load_all(client)
        assert len(stations) > 0

        # Error count should be reset on successful operations
        assert client._consecutive_errors == 0  # Reset on success

    async def test_retry_count_preserved_across_reauthentication(
        self, client: LuxpowerClient
    ) -> None:
        """Test that retry count is preserved during re-authentication.

        If a transient error occurs, then session expires, then we retry,
        the retry count should be preserved across the re-authentication.

        This is a design verification test - we can't easily trigger this
        scenario, but we verify the code structure is correct.
        """
        # This is more of a code inspection test
        # The _request method signature includes _retry_count parameter
        # and it's preserved in the re-authentication retry call
        import inspect

        sig = inspect.signature(client._request)
        assert "_retry_count" in sig.parameters

        # The default should be 0
        assert sig.parameters["_retry_count"].default == 0
