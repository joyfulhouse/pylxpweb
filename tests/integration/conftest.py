"""Shared fixtures for integration tests."""

from __future__ import annotations

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


@pytest.fixture(scope="function")
async def client() -> AsyncGenerator[LuxpowerClient, None]:
    """Create authenticated client for testing.

    Uses function scope to ensure each test gets a fresh client and session.
    This avoids aiohttp "Timeout context manager should be used inside a task" errors
    that occur when sharing sessions across different async tasks.
    """
    async with LuxpowerClient(
        username=LUXPOWER_USERNAME,
        password=LUXPOWER_PASSWORD,
        base_url=LUXPOWER_BASE_URL,
    ) as client:
        yield client


@pytest.fixture(scope="function")
async def station(client: LuxpowerClient) -> Station | None:
    """Load first station for testing.

    Uses function scope to avoid session sharing issues.
    """
    stations = await Station.load_all(client)
    if not stations:
        pytest.skip("No stations found")
    return stations[0]
