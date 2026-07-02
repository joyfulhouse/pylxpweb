"""A failed/partial parameter read must not blank previously-known parameters.

Regression for eg4_web_monitor#282 (ivanfmartinez, 2026-07-01, beta.17 HYBRID):
a WiFi-dongle misroute storm failed the second holding-register range read
(``Failed to read registers 125-250``).  ``_fetch_parameters`` swallowed the
failure per range and then REPLACED ``self.parameters`` with the partial dict
(range 0-124 only) — every parameter backed by registers 125-249 (e.g.
``HOLD_SYSTEM_CHARGE_SOC_LIMIT``, reg 227) vanished, flipping the entity to
*unknown*.  It also stamped ``_parameters_cache_time``, arming the cache/
throttle so the blank state persisted for up to an hour.

Sticky semantics (the #261 fault/warning-code precedent): a partial read
merges fresh values OVER the previous parameters (failed ranges keep their
last-known values), the cache timestamp is stamped only on a FULLY successful
read (so the next ``include_parameters`` refresh retries instead of waiting
out the TTL), and the new public ``parameters_complete`` flag lets consumers
(the HA integration's refresh throttle) distinguish a clean read from a
degraded one.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.inverters.generic import GenericInverter


def _make_inverter(client: LuxpowerClient | None = None) -> GenericInverter:
    return GenericInverter(client=client, serial_number="1234567890", model="TestModel")


@pytest.fixture
def mock_client() -> LuxpowerClient:
    client = Mock(spec=LuxpowerClient)
    client.username = "user@example.com"
    client.api = Mock()
    client.api.devices = Mock()
    client.api.control = Mock()
    return client


def _range_transport(responses: dict[int, dict[str, int] | Exception]) -> Mock:
    """Transport whose ``read_named_parameters`` is scripted per start register."""

    async def read_named(start: int, count: int) -> dict[str, int]:
        entry = responses[start]
        if isinstance(entry, Exception):
            raise entry
        return entry

    transport = Mock()
    transport.read_named_parameters = AsyncMock(side_effect=read_named)
    return transport


class TestTransportParameterSticky:
    """Transport path: per-range carry-forward, completeness, stamping."""

    @pytest.mark.asyncio
    async def test_partial_failure_carries_forward_previous_values(self) -> None:
        """The exact #282 shape: range 125-249 drops, reg-227 param survives."""
        inverter = _make_inverter()
        inverter.parameters = {
            "HOLD_SYSTEM_CHARGE_SOC_LIMIT": 101,  # reg 227, in the failed range
            "HOLD_CHG_POWER_PERCENT_CMD": 80,  # reg 64, in the healthy range
        }
        inverter._transport = _range_transport(
            {
                0: {"HOLD_CHG_POWER_PERCENT_CMD": 60},
                125: OSError("Response function mismatch: expected 0x03, got 0x04"),
            }
        )

        await inverter._fetch_parameters()

        assert inverter.parameters == {
            "HOLD_SYSTEM_CHARGE_SOC_LIMIT": 101,  # carried forward, NOT blanked
            "HOLD_CHG_POWER_PERCENT_CMD": 60,  # fresh value from the healthy range
        }
        assert inverter.parameters_complete is False
        # Not stamped: the next include_parameters refresh must retry, not
        # wait out the full parameter TTL with a degraded dict.
        assert inverter._parameters_cache_time is None

    @pytest.mark.asyncio
    async def test_full_success_replaces_and_stamps(self) -> None:
        """A clean read is authoritative: stale keys go, cache is stamped."""
        inverter = _make_inverter()
        inverter.parameters = {"STALE_KEY": 1, "HOLD_CHG_POWER_PERCENT_CMD": 80}
        inverter._transport = _range_transport(
            {
                0: {"HOLD_CHG_POWER_PERCENT_CMD": 60},
                125: {"HOLD_SYSTEM_CHARGE_SOC_LIMIT": 90},
            }
        )

        await inverter._fetch_parameters()

        assert inverter.parameters == {
            "HOLD_CHG_POWER_PERCENT_CMD": 60,
            "HOLD_SYSTEM_CHARGE_SOC_LIMIT": 90,
        }
        assert inverter.parameters_complete is True
        assert inverter._parameters_cache_time is not None

    @pytest.mark.asyncio
    async def test_total_failure_keeps_parameters_untouched(self) -> None:
        inverter = _make_inverter()
        inverter.parameters = {"HOLD_SYSTEM_CHARGE_SOC_LIMIT": 101}
        inverter._transport = _range_transport({0: OSError("boom"), 125: OSError("boom")})

        await inverter._fetch_parameters()

        assert inverter.parameters == {"HOLD_SYSTEM_CHARGE_SOC_LIMIT": 101}
        assert inverter.parameters_complete is False
        assert inverter._parameters_cache_time is None

    @pytest.mark.asyncio
    async def test_partial_failure_retries_on_next_unforced_refresh(self) -> None:
        """No stamp on partial -> the next include_parameters refresh re-reads.

        This is the amplifier from #282: stamping the cache on a partial read
        armed the TTL/throttle, so one bad read meant a degraded dict for the
        whole parameter interval (~1 h at the integration level).
        """
        inverter = _make_inverter()
        transport = _range_transport(
            {
                0: {"HOLD_CHG_POWER_PERCENT_CMD": 60},
                125: OSError("boom"),
            }
        )
        inverter._transport = transport

        await inverter._fetch_parameters()
        first_calls = transport.read_named_parameters.await_count
        assert first_calls == 2

        # Unforced second parameter fetch happens because the cache was never
        # stamped (refresh() gates _fetch_parameters on the cache TTL).
        assert inverter._is_cache_expired(
            inverter._parameters_cache_time, inverter._parameters_cache_ttl, force=False
        )
        await inverter._fetch_parameters()
        assert transport.read_named_parameters.await_count == first_calls + 2

    @pytest.mark.asyncio
    async def test_full_success_after_partial_restores_completeness(self) -> None:
        inverter = _make_inverter()
        transport = _range_transport(
            {
                0: {"HOLD_CHG_POWER_PERCENT_CMD": 60},
                125: OSError("boom"),
            }
        )
        inverter._transport = transport
        await inverter._fetch_parameters()
        assert inverter.parameters_complete is False

        inverter._transport = _range_transport(
            {
                0: {"HOLD_CHG_POWER_PERCENT_CMD": 61},
                125: {"HOLD_SYSTEM_CHARGE_SOC_LIMIT": 90},
            }
        )
        await inverter._fetch_parameters()

        assert inverter.parameters_complete is True
        assert inverter._parameters_cache_time is not None


class TestHttpParameterSticky:
    """HTTP path: one dropped range must not blank the other ranges' values."""

    @staticmethod
    def _param_response(params: dict[str, int]) -> Mock:
        response = Mock()
        response.parameters = params
        return response

    @pytest.mark.asyncio
    async def test_http_partial_failure_carries_forward(self, mock_client: LuxpowerClient) -> None:
        inverter = _make_inverter(client=mock_client)
        inverter.parameters = {
            "HOLD_SYSTEM_CHARGE_SOC_LIMIT": 101,
            "HOLD_CHG_POWER_PERCENT_CMD": 80,
        }
        mock_client.api.control.read_parameters = AsyncMock(
            side_effect=[
                self._param_response({"HOLD_CHG_POWER_PERCENT_CMD": 60}),
                OSError("DATAFRAME_TIMEOUT"),
                self._param_response({"HOLD_LEAD_ACID_CHARGE_RATE": 40}),
            ]
        )

        await inverter._fetch_parameters()

        assert inverter.parameters == {
            "HOLD_SYSTEM_CHARGE_SOC_LIMIT": 101,  # carried forward
            "HOLD_CHG_POWER_PERCENT_CMD": 60,
            "HOLD_LEAD_ACID_CHARGE_RATE": 40,
        }
        assert inverter.parameters_complete is False
        assert inverter._parameters_cache_time is None

    @pytest.mark.asyncio
    async def test_http_full_success_replaces_and_stamps(self, mock_client: LuxpowerClient) -> None:
        inverter = _make_inverter(client=mock_client)
        inverter.parameters = {"STALE_KEY": 1}
        mock_client.api.control.read_parameters = AsyncMock(
            side_effect=[
                self._param_response({"HOLD_CHG_POWER_PERCENT_CMD": 60}),
                self._param_response({"HOLD_SYSTEM_CHARGE_SOC_LIMIT": 90}),
                self._param_response({}),
            ]
        )

        await inverter._fetch_parameters()

        assert inverter.parameters == {
            "HOLD_CHG_POWER_PERCENT_CMD": 60,
            "HOLD_SYSTEM_CHARGE_SOC_LIMIT": 90,
        }
        assert inverter.parameters_complete is True
        assert inverter._parameters_cache_time is not None
