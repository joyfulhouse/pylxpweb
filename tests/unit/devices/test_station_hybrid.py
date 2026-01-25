"""Tests for Station.attach_local_transports() hybrid mode support.

This module tests the hybrid mode functionality where local transports
are attached to HTTP-discovered Station devices for direct local access.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.devices.station import Location, Station
from pylxpweb.transports.config import TransportConfig, TransportType

if TYPE_CHECKING:
    pass


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock LuxpowerClient."""
    client = MagicMock()
    client.iana_timezone = "America/Los_Angeles"
    return client


@pytest.fixture
def station(mock_client: MagicMock) -> Station:
    """Create a Station instance for testing."""
    location = Location(address="123 Test St", country="USA")
    station = Station(
        client=mock_client,
        plant_id=12345,
        name="Test Station",
        location=location,
        timezone="UTC",
        created_date=datetime.now(),
    )
    return station


@pytest.fixture
def modbus_config() -> TransportConfig:
    """Create a Modbus TCP transport config."""
    return TransportConfig(
        host="192.168.1.100",
        port=502,
        serial="CE12345678",
        transport_type=TransportType.MODBUS_TCP,
    )


@pytest.fixture
def dongle_config() -> TransportConfig:
    """Create a WiFi dongle transport config."""
    return TransportConfig(
        host="192.168.1.101",
        port=8000,
        serial="CE87654321",
        dongle_serial="DONGLE1234",
        transport_type=TransportType.WIFI_DONGLE,
    )


# ============================================================================
# Test: attach_local_transports() Method
# ============================================================================


class TestAttachLocalTransports:
    """Tests for Station.attach_local_transports() method."""

    @pytest.mark.asyncio
    async def test_attach_to_matching_inverter(
        self, station: Station, modbus_config: TransportConfig
    ) -> None:
        """Test attaching transport to an inverter with matching serial."""
        # Create mock inverter with matching serial
        mock_inverter = MagicMock()
        mock_inverter.serial_number = "CE12345678"
        mock_inverter._local_transport = None
        station.standalone_inverters = [mock_inverter]

        # Create mock transport
        mock_transport = AsyncMock()
        mock_transport.connect = AsyncMock()
        mock_transport.serial = "CE12345678"

        with patch(
            "pylxpweb.devices.station.create_transport_from_config",
            return_value=mock_transport,
        ):
            result = await station.attach_local_transports([modbus_config])

        # Verify transport was attached
        assert result.matched == 1
        assert result.unmatched == 0
        assert mock_inverter._local_transport is mock_transport

    @pytest.mark.asyncio
    async def test_attach_to_inverter_in_parallel_group(
        self, station: Station, modbus_config: TransportConfig
    ) -> None:
        """Test attaching transport to an inverter in a parallel group."""
        # Create mock parallel group with inverter
        mock_inverter = MagicMock()
        mock_inverter.serial_number = "CE12345678"
        mock_inverter._local_transport = None

        mock_group = MagicMock()
        mock_group.inverters = [mock_inverter]
        mock_group.mid_device = None
        station.parallel_groups = [mock_group]

        # Create mock transport
        mock_transport = AsyncMock()
        mock_transport.connect = AsyncMock()
        mock_transport.serial = "CE12345678"

        with patch(
            "pylxpweb.devices.station.create_transport_from_config",
            return_value=mock_transport,
        ):
            result = await station.attach_local_transports([modbus_config])

        # Verify transport was attached
        assert result.matched == 1
        assert mock_inverter._local_transport is mock_transport

    @pytest.mark.asyncio
    async def test_attach_to_mid_device(
        self, station: Station, modbus_config: TransportConfig
    ) -> None:
        """Test attaching transport to a MID device."""
        # Create mock MID device with matching serial
        mock_mid = MagicMock()
        mock_mid.serial_number = "CE12345678"
        mock_mid._local_transport = None
        station.standalone_mid_devices = [mock_mid]

        # Create mock transport
        mock_transport = AsyncMock()
        mock_transport.connect = AsyncMock()
        mock_transport.serial = "CE12345678"

        with patch(
            "pylxpweb.devices.station.create_transport_from_config",
            return_value=mock_transport,
        ):
            result = await station.attach_local_transports([modbus_config])

        # Verify transport was attached
        assert result.matched == 1
        assert mock_mid._local_transport is mock_transport

    @pytest.mark.asyncio
    async def test_attach_to_mid_device_in_parallel_group(
        self, station: Station, modbus_config: TransportConfig
    ) -> None:
        """Test attaching transport to a MID device in a parallel group."""
        # Create mock parallel group with MID device
        mock_mid = MagicMock()
        mock_mid.serial_number = "CE12345678"
        mock_mid._local_transport = None

        mock_group = MagicMock()
        mock_group.inverters = []
        mock_group.mid_device = mock_mid
        station.parallel_groups = [mock_group]

        # Create mock transport
        mock_transport = AsyncMock()
        mock_transport.connect = AsyncMock()
        mock_transport.serial = "CE12345678"

        with patch(
            "pylxpweb.devices.station.create_transport_from_config",
            return_value=mock_transport,
        ):
            result = await station.attach_local_transports([modbus_config])

        # Verify transport was attached
        assert result.matched == 1
        assert mock_mid._local_transport is mock_transport

    @pytest.mark.asyncio
    async def test_unmatched_config_no_device(
        self, station: Station, modbus_config: TransportConfig
    ) -> None:
        """Test config that doesn't match any device."""
        # Station has no devices
        station.standalone_inverters = []
        station.parallel_groups = []
        station.standalone_mid_devices = []

        # Create mock transport
        mock_transport = AsyncMock()
        mock_transport.connect = AsyncMock()
        mock_transport.serial = "CE12345678"

        with patch(
            "pylxpweb.devices.station.create_transport_from_config",
            return_value=mock_transport,
        ):
            result = await station.attach_local_transports([modbus_config])

        # Verify no match
        assert result.matched == 0
        assert result.unmatched == 1
        assert "CE12345678" in result.unmatched_serials

    @pytest.mark.asyncio
    async def test_connection_failure_skipped(
        self, station: Station, modbus_config: TransportConfig
    ) -> None:
        """Test that connection failures are skipped gracefully."""
        # Create mock inverter
        mock_inverter = MagicMock()
        mock_inverter.serial_number = "CE12345678"
        mock_inverter._local_transport = None
        station.standalone_inverters = [mock_inverter]

        # Create mock transport that fails to connect
        mock_transport = AsyncMock()
        mock_transport.connect = AsyncMock(side_effect=ConnectionError("Connection refused"))

        with patch(
            "pylxpweb.devices.station.create_transport_from_config",
            return_value=mock_transport,
        ):
            result = await station.attach_local_transports([modbus_config])

        # Verify failure was handled
        assert result.matched == 0
        assert result.failed == 1
        assert mock_inverter._local_transport is None

    @pytest.mark.asyncio
    async def test_multiple_transports_mixed_results(
        self, station: Station, modbus_config: TransportConfig, dongle_config: TransportConfig
    ) -> None:
        """Test attaching multiple transports with mixed results."""
        # Create mock inverters - one match, one no match
        mock_inverter1 = MagicMock()
        mock_inverter1.serial_number = "CE12345678"
        mock_inverter1._local_transport = None

        mock_inverter2 = MagicMock()
        mock_inverter2.serial_number = "CE11111111"  # Different serial
        mock_inverter2._local_transport = None

        station.standalone_inverters = [mock_inverter1, mock_inverter2]

        # Create mock transports
        mock_transport1 = AsyncMock()
        mock_transport1.connect = AsyncMock()
        mock_transport1.serial = "CE12345678"

        mock_transport2 = AsyncMock()
        mock_transport2.connect = AsyncMock()
        mock_transport2.serial = "CE87654321"  # Won't match

        def create_transport_side_effect(config: TransportConfig) -> AsyncMock:
            if config.serial == "CE12345678":
                return mock_transport1
            return mock_transport2

        with patch(
            "pylxpweb.devices.station.create_transport_from_config",
            side_effect=create_transport_side_effect,
        ):
            result = await station.attach_local_transports([modbus_config, dongle_config])

        # Verify mixed results
        assert result.matched == 1
        assert result.unmatched == 1
        assert mock_inverter1._local_transport is mock_transport1
        assert mock_inverter2._local_transport is None

    @pytest.mark.asyncio
    async def test_empty_configs_list(self, station: Station) -> None:
        """Test attaching with empty configs list."""
        result = await station.attach_local_transports([])

        assert result.matched == 0
        assert result.unmatched == 0
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_is_hybrid_mode_property(
        self, station: Station, modbus_config: TransportConfig
    ) -> None:
        """Test is_hybrid_mode property reflects attached transports."""
        # Initially not hybrid
        assert station.is_hybrid_mode is False

        # Create mock inverter and transport
        mock_inverter = MagicMock()
        mock_inverter.serial_number = "CE12345678"
        mock_inverter._local_transport = None
        station.standalone_inverters = [mock_inverter]

        mock_transport = AsyncMock()
        mock_transport.connect = AsyncMock()
        mock_transport.serial = "CE12345678"

        with patch(
            "pylxpweb.devices.station.create_transport_from_config",
            return_value=mock_transport,
        ):
            await station.attach_local_transports([modbus_config])

        # Now hybrid mode should be True
        assert station.is_hybrid_mode is True


# ============================================================================
# Test: AttachResult Dataclass
# ============================================================================


class TestAttachResult:
    """Tests for AttachResult dataclass."""

    def test_attach_result_properties(self) -> None:
        """Test AttachResult dataclass properties."""
        from pylxpweb.devices.station import AttachResult

        result = AttachResult(
            matched=2,
            unmatched=1,
            failed=1,
            unmatched_serials=["CE99999999"],
            failed_serials=["CE88888888"],
        )

        assert result.matched == 2
        assert result.unmatched == 1
        assert result.failed == 1
        assert "CE99999999" in result.unmatched_serials
        assert "CE88888888" in result.failed_serials

    def test_attach_result_total_property(self) -> None:
        """Test AttachResult.total property."""
        from pylxpweb.devices.station import AttachResult

        result = AttachResult(
            matched=2,
            unmatched=1,
            failed=1,
            unmatched_serials=[],
            failed_serials=[],
        )

        assert result.total == 4


# ============================================================================
# Test: Inverter Hybrid Mode Refresh
# ============================================================================


class TestInverterHybridRefresh:
    """Tests for inverter refresh with hybrid mode."""

    @pytest.mark.asyncio
    async def test_refresh_prefers_local_transport(self) -> None:
        """Test that refresh uses _local_transport when available."""
        from pylxpweb.devices.inverters.generic import GenericInverter

        # Create inverter with mock client
        mock_client = MagicMock()
        mock_client.api.devices.get_inverter_runtime = AsyncMock()

        inverter = GenericInverter(
            client=mock_client,
            serial_number="CE12345678",
            model="18kPV",
        )

        # Attach local transport
        mock_transport = AsyncMock()
        mock_transport.read_runtime = AsyncMock(
            return_value={"ppv": 5000, "soc": 85}
        )
        inverter._local_transport = mock_transport

        # Refresh should use local transport
        await inverter.refresh(force=True)

        # Verify local transport was used, not HTTP API
        mock_transport.read_runtime.assert_called_once()
        mock_client.api.devices.get_inverter_runtime.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_fallback_to_http_on_transport_failure(self) -> None:
        """Test that refresh falls back to HTTP on local transport failure."""
        from pylxpweb.devices.inverters.generic import GenericInverter
        from pylxpweb.models import InverterRuntime

        # Create mock runtime response
        mock_runtime = MagicMock(spec=InverterRuntime)
        mock_runtime.ppv = 4000

        # Create inverter with mock client
        mock_client = MagicMock()
        mock_client.api.devices.get_inverter_runtime = AsyncMock(
            return_value=mock_runtime
        )

        inverter = GenericInverter(
            client=mock_client,
            serial_number="CE12345678",
            model="18kPV",
        )

        # Attach local transport that fails
        mock_transport = AsyncMock()
        mock_transport.read_runtime = AsyncMock(
            side_effect=ConnectionError("Connection lost")
        )
        inverter._local_transport = mock_transport

        # Refresh should fall back to HTTP
        await inverter.refresh(force=True)

        # Verify fallback occurred
        mock_transport.read_runtime.assert_called_once()
        mock_client.api.devices.get_inverter_runtime.assert_called_once_with("CE12345678")

    @pytest.mark.asyncio
    async def test_has_local_transport_property(self) -> None:
        """Test has_local_transport property."""
        from pylxpweb.devices.inverters.generic import GenericInverter

        mock_client = MagicMock()
        inverter = GenericInverter(
            client=mock_client,
            serial_number="CE12345678",
            model="18kPV",
        )

        # Initially no local transport
        assert inverter.has_local_transport is False

        # Attach transport
        inverter._local_transport = MagicMock()
        assert inverter.has_local_transport is True
