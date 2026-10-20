"""Exercise provenance through the real HTTP request and endpoint-cache path."""

from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import aiohttp
import pytest
from aioresponses import CallbackResult, aioresponses
from pydantic import ValidationError

from pylxpweb import LuxpowerClient
from pylxpweb import client as client_module
from pylxpweb.exceptions import LuxpowerAPIError, LuxpowerConnectionError
from pylxpweb.provenance import EnergyProvenance, derived_provenance, unknown_provenance

BASE_URL = "https://monitor.eg4electronics.com"
SERIAL = "1234567890"
ENERGY_URL = f"{BASE_URL}/WManage/api/inverter/getInverterEnergyInfo"


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    now = [datetime(2026, 1, 1, 18, 29, 55, tzinfo=UTC)]

    class CacheClock(datetime):
        @classmethod
        def now(cls, tz=None):
            # Cache bookkeeping uses host-local naive time; this host is UTC.
            return cls.fromtimestamp(now[0].timestamp(), UTC if tz is None else tz).replace(
                tzinfo=tz
            )

    monkeypatch.setattr(client_module, "datetime", CacheClock)
    monkeypatch.setattr(client_module, "_utc_now", lambda: now[0])
    return now


def _login(mocked_api: aioresponses, payload: dict[str, Any]) -> None:
    mocked_api.post(f"{BASE_URL}/WManage/api/login", payload=payload)


def _assert_http(record: EnergyProvenance, acquired: datetime, field: str) -> None:
    assert record.source == "http"
    assert record.source_id == f"{ENERGY_URL}?serialNum={SERIAL}"
    assert record.acquired_at == acquired
    assert record.acquired_at.tzinfo is UTC
    assert record.field_name == field
    assert record.measured_at is None
    assert record.counter_day is None
    assert record.reset_timezone is None
    assert record.components == ()


async def test_real_cache_hit_across_device_midnight_keeps_original_reception(
    mocked_api, login_response, energy_response, clock
):
    _login(mocked_api, login_response)
    mocked_api.post(ENERGY_URL, payload=energy_response)
    acquired = clock[0]
    async with LuxpowerClient("user", "password") as client:
        first = await client.api.devices.get_inverter_energy(SERIAL)
        clock[0] += timedelta(seconds=10)
        assert (
            acquired.astimezone(ZoneInfo("Asia/Kolkata")).date()
            != clock[0].astimezone(ZoneInfo("Asia/Kolkata")).date()
        )
        cached = await client.api.devices.get_inverter_energy(SERIAL)
        assert cached == first
        assert cached is not first
        _assert_http(cached.provenance["todayYielding"], acquired, "todayYielding")
        assert len(cached.provenance) == 12
        assert (
            sum(
                len(calls)
                for (_, url), calls in mocked_api.requests.items()
                if str(url) == ENERGY_URL
            )
            == 1
        )
        client.clear_cache()
        _assert_http(first.provenance["todayYielding"], acquired, "todayYielding")


async def test_fresh_identical_cloud_payload_after_host_midnight_has_no_measurement_day(
    mocked_api, login_response, energy_response, clock
):
    clock[0] = datetime(2026, 1, 1, 23, 59, 55, tzinfo=UTC)
    _login(mocked_api, login_response)
    mocked_api.post(ENERGY_URL, payload=energy_response)
    mocked_api.post(ENERGY_URL, payload=energy_response)
    async with LuxpowerClient("user", "password") as client:
        first = await client.api.devices.get_inverter_energy(SERIAL)
        received = clock[0]
        clock[0] += timedelta(seconds=10)
        second = await client.api.devices.get_inverter_energy(SERIAL)
        assert first.todayYielding == second.todayYielding
        _assert_http(first.provenance["todayYielding"], received, "todayYielding")
        _assert_http(second.provenance["todayYielding"], clock[0], "todayYielding")


@pytest.mark.parametrize("failure", ["connection", "api", "invalid_model"])
async def test_failed_or_invalid_response_does_not_redate_previous_values(
    mocked_api, login_response, energy_response, clock, failure
):
    _login(mocked_api, login_response)
    mocked_api.post(ENERGY_URL, payload=energy_response)
    if failure == "connection":
        mocked_api.post(ENERGY_URL, exception=aiohttp.ClientConnectionError("offline"))
        expected = LuxpowerConnectionError
    elif failure == "api":
        mocked_api.post(ENERGY_URL, payload={"success": False, "message": "not permitted"})
        expected = LuxpowerAPIError
    else:
        mocked_api.post(ENERGY_URL, payload={"success": True, "todayYielding": 999})
        expected = ValidationError
    async with LuxpowerClient("user", "password") as client:
        first = await client.api.devices.get_inverter_energy(SERIAL)
        acquired = clock[0]
        before = dict(first.provenance)
        clock[0] += timedelta(seconds=21)
        with pytest.raises(expected):
            await client.api.devices.get_inverter_energy(SERIAL)
        assert first.provenance == before
        _assert_http(first.provenance["todayYielding"], acquired, "todayYielding")


@pytest.mark.parametrize("failure", ["transient_api", "authentication"])
async def test_retry_records_the_successful_response_reception(
    mocked_api, login_response, energy_response, clock, monkeypatch, failure
):
    _login(mocked_api, login_response)
    if failure == "transient_api":
        mocked_api.post(ENERGY_URL, payload={"success": False, "message": "DATAFRAME_TIMEOUT"})
    else:
        mocked_api.post(ENERGY_URL, status=401)
        _login(mocked_api, login_response)

    def successful_response(url, **kwargs):
        clock[0] += timedelta(seconds=2)
        return CallbackResult(payload=energy_response)

    mocked_api.post(ENERGY_URL, callback=successful_response)
    async with LuxpowerClient("user", "password") as client:
        monkeypatch.setattr(client, "_apply_backoff", AsyncMock())
        result = await client.api.devices.get_inverter_energy(SERIAL)
        _assert_http(result.provenance["todayYielding"], clock[0], "todayYielding")
        cached = await client.api.devices.get_inverter_energy(SERIAL)
        assert cached.provenance == result.provenance


async def test_overlapping_same_key_responses_keep_their_own_metadata(
    mocked_api, login_response, energy_response, clock, monkeypatch
):
    _login(mocked_api, login_response)
    mocked_api.post(ENERGY_URL, payload=energy_response)
    newer = {**energy_response, "todayYielding": energy_response["todayYielding"] + 1}
    mocked_api.post(ENERGY_URL, payload=newer)
    async with LuxpowerClient("user", "password") as client:
        first_received = asyncio.Event()
        return_first = asyncio.Event()
        request = client._request

        async def delayed_return(*args: Any, **kwargs: Any) -> dict[str, Any]:
            response = await request(*args, **kwargs)
            if not first_received.is_set():
                first_received.set()
                await return_first.wait()
            return response

        monkeypatch.setattr(client, "_request", delayed_return)
        acquired = clock[0]
        first_task = asyncio.create_task(client.api.devices.get_inverter_energy(SERIAL))
        try:
            await asyncio.wait_for(first_received.wait(), 5)
            client.clear_cache()
            clock[0] += timedelta(seconds=1)
            second = await client.api.devices.get_inverter_energy(SERIAL)
        finally:
            return_first.set()
            first = await first_task
        assert first.todayYielding == energy_response["todayYielding"]
        assert second.todayYielding == newer["todayYielding"]
        _assert_http(first.provenance["todayYielding"], acquired, "todayYielding")
        _assert_http(second.provenance["todayYielding"], clock[0], "todayYielding")


async def test_server_cannot_inject_provenance_or_measurement_day(
    mocked_api, login_response, energy_response, clock
):
    _login(mocked_api, login_response)
    payload = {
        **energy_response,
        "provenance": {
            "todayYielding": {"source": "local", "source_id": "forged", "counter_day": "2026-01-02"}
        },
    }
    mocked_api.post(ENERGY_URL, payload=payload)
    async with LuxpowerClient("user", "password") as client:
        result = await client.api.devices.get_inverter_energy(SERIAL)
        _assert_http(result.provenance["todayYielding"], clock[0], "todayYielding")


async def test_plain_response_without_receive_metadata_stays_unknown(
    mocked_api, login_response, energy_response, monkeypatch
):
    _login(mocked_api, login_response)
    async with LuxpowerClient("user", "password") as client:
        monkeypatch.setattr(client, "_ensure_authenticated", AsyncMock())
        monkeypatch.setattr(
            client,
            "_request",
            AsyncMock(return_value={**energy_response, "provenance": {"todayYielding": "forged"}}),
        )
        result = await client.api.devices.get_inverter_energy(SERIAL)
        assert result.provenance == {}


async def test_parallel_endpoint_identifies_the_cloud_aggregate(
    mocked_api, login_response, parallel_energy_response, clock
):
    _login(mocked_api, login_response)
    url = f"{BASE_URL}/WManage/api/inverter/getInverterEnergyInfoParallel"
    mocked_api.post(url, payload=parallel_energy_response)
    async with LuxpowerClient("user", "password") as client:
        result = await client.api.devices.get_parallel_energy(SERIAL)
        record = result.provenance["todayUsage"]
        assert record.source == "http"
        assert record.source_id == f"{url}?serialNum={SERIAL}"
        assert record.acquired_at == clock[0]
        assert record.measured_at is None
        assert record.counter_day is None
        assert record.components == ()


async def test_midbox_nested_energy_metadata_preserves_zero_missing_and_stale_device_time(
    mocked_api, login_response, midbox_response, clock
):
    _login(mocked_api, login_response)
    url = f"{BASE_URL}/WManage/api/midbox/getMidboxRuntime"
    payload = {
        **midbox_response,
        "lost": True,
        "midboxData": {
            **midbox_response["midboxData"],
            "deviceTime": "2000-01-01 00:00:00",
            "eLoadTodayL1": 0,
            "eLoadTodayL2": None,
            "provenance": {"eLoadTodayL1": "forged"},
        },
    }
    mocked_api.post(url, payload=payload)
    async with LuxpowerClient("user", "password") as client:
        result = await client.api.devices.get_midbox_runtime(SERIAL)
        received = clock[0]
        clock[0] += timedelta(seconds=10)
        cached = await client.api.devices.get_midbox_runtime(SERIAL)
        assert cached.midboxData.provenance == result.midboxData.provenance
        record = cached.midboxData.provenance["eLoadTodayL1"]
        assert record.acquired_at == received
        assert record.source_id == f"{url}?serialNum={SERIAL}"
        assert record.field_name == "eLoadTodayL1"
        assert record.measured_at is None
        assert record.counter_day is None
        assert record.reset_timezone is None
        assert "eLoadTodayL2" not in cached.midboxData.provenance
        assert "gridRmsVolt" not in cached.midboxData.provenance


@pytest.mark.parametrize("field", ["acquired_at", "measured_at"])
def test_provenance_rejects_naive_timestamps(field):
    with pytest.raises(ValueError, match="timezone-aware"):
        EnergyProvenance("http", "source", **{field: datetime(2026, 1, 1)})


def test_provenance_normalizes_aware_times_and_is_immutable():
    offset = timezone(timedelta(hours=5, minutes=30))
    timestamp = datetime(2026, 1, 2, tzinfo=offset)
    provenance = EnergyProvenance("local", "inverter", timestamp, measured_at=timestamp)
    assert provenance.acquired_at == datetime(2026, 1, 1, 18, 30, tzinfo=UTC)
    assert provenance.measured_at == provenance.acquired_at
    with pytest.raises(FrozenInstanceError):
        provenance.acquired_at = datetime.now(UTC)


def test_derived_provenance_preserves_mixed_age_unknown_and_field_identity():
    first = EnergyProvenance(
        "local", "inverter-1", datetime(2026, 1, 1, tzinfo=UTC), field_name="pv"
    )
    second = EnergyProvenance(
        "http", "inverter-2", datetime(2026, 1, 2, tzinfo=UTC), field_name="import"
    )
    missing = unknown_provenance("inverter-3", field_name="pv")
    combined = derived_provenance("group", [first, second, missing, None], field_name="usage")
    assert combined.components[:3] == (first, second, missing)
    assert combined.components[3].source == "unknown"
    assert combined.acquired_at is None
    assert combined.measured_at is None
    assert combined.counter_day is None
    assert combined.reset_timezone is None
