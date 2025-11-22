"""Shared fixtures for integration tests."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from dotenv import load_dotenv

from pylxpweb import LuxpowerClient
from pylxpweb.devices.station import Station

# Load .env file before running tests
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Load credentials from environment
LUXPOWER_USERNAME = os.getenv("LUXPOWER_USERNAME")
LUXPOWER_PASSWORD = os.getenv("LUXPOWER_PASSWORD")
LUXPOWER_BASE_URL = os.getenv("LUXPOWER_BASE_URL", "https://monitor.eg4electronics.com")

# Global throttling to prevent API rate limiting
_LAST_API_CALL = 0.0
_API_THROTTLE_SECONDS = 0.5  # 500ms between API calls


async def throttle_api_call() -> None:
    """Throttle API calls to prevent rate limiting."""
    global _LAST_API_CALL
    import time

    now = time.time()
    elapsed = now - _LAST_API_CALL
    if elapsed < _API_THROTTLE_SECONDS:
        await asyncio.sleep(_API_THROTTLE_SECONDS - elapsed)
    _LAST_API_CALL = time.time()


@pytest.fixture(scope="function")
async def client() -> AsyncGenerator[LuxpowerClient, None]:
    """Create authenticated client for testing with throttling.

    Uses function scope but with global throttling to prevent rate limiting.
    Each test gets a fresh client, but API calls are throttled to 500ms intervals.
    """
    await throttle_api_call()
    async with LuxpowerClient(
        username=LUXPOWER_USERNAME,
        password=LUXPOWER_PASSWORD,
        base_url=LUXPOWER_BASE_URL,
    ) as client:
        yield client


@pytest.fixture(scope="function")
async def station(client: LuxpowerClient) -> Station | None:
    """Load first station for testing with throttling.

    Uses function scope with throttling to prevent excessive API calls.
    """
    await throttle_api_call()
    stations = await Station.load_all(client)
    if not stations:
        pytest.skip("No stations found")
    return stations[0]
