"""Unit tests for the typed pylxpweb<->consumer seam public API.

These cover the public surface added for the typed-contract epic: the
consumed-surface exports in ``pylxpweb.__all__``, the read-only transport
accessors and ``set_cache_ttls`` on inverters, and the device properties that
close the seam gaps (``power_rating_text`` / ``has_runtime_data`` on inverters,
``cycle_count`` on the battery bank).
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import Mock

import pytest

import pylxpweb
from pylxpweb import (
    BaseInverter,
    Battery,
    BatteryBank,
    BatteryBankData,
    GridType,
    InverterEnergyData,
    InverterFamily,
    InverterFeatures,
    InverterModelInfo,
    InverterRuntimeData,
    LuxpowerClient,
    MidboxRuntimeData,
    MIDDevice,
    ParallelGroup,
    Station,
)
from pylxpweb.devices.inverters.hybrid import HybridInverter
from pylxpweb.models import BatteryInfo


@pytest.fixture
def mock_client() -> LuxpowerClient:
    """Create a mock client for testing (only API calls touch it)."""
    return Mock(spec=LuxpowerClient)


def _make_inverter(mock_client: LuxpowerClient) -> HybridInverter:
    return HybridInverter(client=mock_client, serial_number="1234567890", model="FlexBOSS21")


def _make_battery_info() -> BatteryInfo:
    return BatteryInfo(
        success=True,
        serialNum="1234567890",
        batStatus="Idle",
        soc=50,
        vBat=520,
        pCharge=0,
        pDisCharge=0,
    )


class TestConsumedSurfaceExports:
    """Every consumed-surface symbol is importable from the package root."""

    @pytest.mark.parametrize(
        "symbol",
        [
            Station,
            ParallelGroup,
            BaseInverter,
            MIDDevice,
            Battery,
            BatteryBank,
            InverterRuntimeData,
            InverterEnergyData,
            BatteryBankData,
            MidboxRuntimeData,
            InverterFeatures,
            InverterModelInfo,
            InverterFamily,
            GridType,
        ],
    )
    def test_symbol_is_a_type(self, symbol: type) -> None:
        assert isinstance(symbol, type)

    def test_symbols_listed_in_dunder_all(self) -> None:
        for name in (
            "Station",
            "ParallelGroup",
            "BaseInverter",
            "MIDDevice",
            "Battery",
            "BatteryBank",
            "InverterRuntimeData",
            "InverterEnergyData",
            "BatteryData",
            "BatteryBankData",
            "MidboxRuntimeData",
            "InverterFeatures",
            "InverterModelInfo",
            "InverterFamily",
            "GridType",
        ):
            assert name in pylxpweb.__all__, f"{name} missing from pylxpweb.__all__"


class TestTransportAccessors:
    """Read-only transport accessors mirror the private fields."""

    def test_accessors_none_in_cloud_mode(self, mock_client: LuxpowerClient) -> None:
        inv = _make_inverter(mock_client)
        assert inv.transport is None
        assert inv.transport_runtime is None
        assert inv.transport_energy is None
        assert inv.transport_battery is None

    def test_accessors_reflect_injected_transport_data(self, mock_client: LuxpowerClient) -> None:
        inv = _make_inverter(mock_client)
        runtime = InverterRuntimeData()
        energy = InverterEnergyData()
        battery = BatteryBankData()
        inv._transport_runtime = runtime
        inv._transport_energy = energy
        inv._transport_battery = battery
        assert inv.transport_runtime is runtime
        assert inv.transport_energy is energy
        assert inv.transport_battery is battery


class TestSetCacheTtls:
    """Public cache-TTL setter replaces private-attr poking."""

    def test_sets_only_provided_ttls(self, mock_client: LuxpowerClient) -> None:
        inv = _make_inverter(mock_client)
        original_energy = inv._energy_cache_ttl
        original_battery = inv._battery_cache_ttl
        inv.set_cache_ttls(runtime=timedelta(seconds=5))
        assert inv._runtime_cache_ttl == timedelta(seconds=5)
        assert inv._energy_cache_ttl == original_energy
        assert inv._battery_cache_ttl == original_battery

    def test_sets_all_three(self, mock_client: LuxpowerClient) -> None:
        inv = _make_inverter(mock_client)
        ttl = timedelta(seconds=15)
        inv.set_cache_ttls(runtime=ttl, energy=ttl, battery=ttl)
        assert inv._runtime_cache_ttl == ttl
        assert inv._energy_cache_ttl == ttl
        assert inv._battery_cache_ttl == ttl

    def test_no_args_is_a_noop(self, mock_client: LuxpowerClient) -> None:
        inv = _make_inverter(mock_client)
        before = (
            inv._runtime_cache_ttl,
            inv._energy_cache_ttl,
            inv._battery_cache_ttl,
        )
        inv.set_cache_ttls()
        after = (
            inv._runtime_cache_ttl,
            inv._energy_cache_ttl,
            inv._battery_cache_ttl,
        )
        assert before == after


class TestSeamGapProperties:
    """Properties that close the eg4-ohz device-map seam gaps."""

    def test_power_rating_text_aliases_power_rating(self, mock_client: LuxpowerClient) -> None:
        inv = _make_inverter(mock_client)
        # No runtime loaded -> empty, identical to power_rating.
        assert inv.power_rating_text == inv.power_rating == ""

    def test_has_runtime_data_false_without_data(self, mock_client: LuxpowerClient) -> None:
        inv = _make_inverter(mock_client)
        assert inv.has_runtime_data is False

    def test_has_runtime_data_true_with_transport_runtime(
        self, mock_client: LuxpowerClient
    ) -> None:
        inv = _make_inverter(mock_client)
        inv._transport_runtime = InverterRuntimeData()
        assert inv.has_runtime_data is True

    def test_bank_cycle_count_none_without_transport_battery(
        self, mock_client: LuxpowerClient
    ) -> None:
        inv = _make_inverter(mock_client)
        bank = BatteryBank(mock_client, "1234567890", _make_battery_info(), inverter=inv)
        assert bank.cycle_count is None

    def test_bank_cycle_count_reads_transport_battery(self, mock_client: LuxpowerClient) -> None:
        inv = _make_inverter(mock_client)
        inv._transport_battery = BatteryBankData(cycle_count=123)
        bank = BatteryBank(mock_client, "1234567890", _make_battery_info(), inverter=inv)
        assert bank.cycle_count == 123

    def test_bank_cycle_count_none_without_parent_inverter(
        self, mock_client: LuxpowerClient
    ) -> None:
        bank = BatteryBank(mock_client, "1234567890", _make_battery_info())
        assert bank.cycle_count is None


class TestMidTransportAccessors:
    """MIDDevice exposes the same public transport accessors as inverters."""

    def test_accessors_none_in_cloud_mode(self, mock_client: LuxpowerClient) -> None:
        mid = MIDDevice(mock_client, "0987654321", "GridBOSS")
        assert mid.transport is None
        assert mid.transport_runtime is None

    def test_transport_runtime_reflects_injected_data(self, mock_client: LuxpowerClient) -> None:
        mid = MIDDevice(mock_client, "0987654321", "GridBOSS")
        runtime = MidboxRuntimeData()
        mid._transport_runtime = runtime
        assert mid.transport_runtime is runtime
