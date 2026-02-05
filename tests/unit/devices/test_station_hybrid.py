"""Tests for Station hybrid mode functionality."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.devices.station import Station
from pylxpweb.transports.config import TransportConfig, TransportType


@pytest.fixture
def mock_client() -> MagicMock:
    """Create a mock LuxpowerClient."""
    client = MagicMock()
    client.api = MagicMock()
    return client


@pytest.fixture
def mock_inverter() -> MagicMock:
    """Create a mock inverter."""
    inverter = MagicMock()
    inverter.serial_number = "CE12345678"
    inverter._transport = None
    return inverter


@pytest.fixture
def station_with_inverter(mock_client: MagicMock, mock_inverter: MagicMock) -> Station:
    """Create a Station with one inverter."""
    from datetime import datetime

    from pylxpweb.devices.station import Location

    station = Station(
        client=mock_client,
        plant_id=12345,
        name="Test Station",
        location=Location(address="123 Test St", country="US"),
        timezone="UTC",
        created_date=datetime.now(),
    )
    station.standalone_inverters = [mock_inverter]
    return station


class TestIsHybridMode:
    """Tests for Station.is_hybrid_mode property."""

    def test_no_transports_attached(
        self, station_with_inverter: Station, mock_inverter: MagicMock
    ) -> None:
        """Test is_hybrid_mode is False when no transports attached."""
        mock_inverter._transport = None
        assert station_with_inverter.is_hybrid_mode is False

    def test_with_transport_attached(
        self, station_with_inverter: Station, mock_inverter: MagicMock
    ) -> None:
        """Test is_hybrid_mode is True when transport is attached."""
        mock_inverter._transport = MagicMock()
        assert station_with_inverter.is_hybrid_mode is True

    def test_empty_station(self, mock_client: MagicMock) -> None:
        """Test is_hybrid_mode is False for empty station."""
        from datetime import datetime

        from pylxpweb.devices.station import Location

        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Empty Station",
            location=Location(address="", country=""),
            timezone="UTC",
            created_date=datetime.now(),
        )
        assert station.is_hybrid_mode is False


class TestAttachLocalTransports:
    """Tests for Station.attach_local_transports method."""

    @pytest.mark.asyncio
    async def test_attach_modbus_transport_success(
        self, station_with_inverter: Station, mock_inverter: MagicMock
    ) -> None:
        """Test successfully attaching a Modbus transport."""
        mock_transport = AsyncMock()
        mock_transport.connect = AsyncMock()

        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
            unit_id=1,
        )

        with patch(
            "pylxpweb.transports.create_modbus_transport",
            return_value=mock_transport,
        ) as mock_create:
            result = await station_with_inverter.attach_local_transports([config])

        assert result.matched == 1
        assert result.unmatched == 0
        assert result.failed == 0
        mock_create.assert_called_once()
        mock_transport.connect.assert_called_once()
        assert mock_inverter._transport == mock_transport

    @pytest.mark.asyncio
    async def test_attach_dongle_transport_success(
        self, station_with_inverter: Station, mock_inverter: MagicMock
    ) -> None:
        """Test successfully attaching a WiFi dongle transport."""
        mock_transport = AsyncMock()
        mock_transport.connect = AsyncMock()

        config = TransportConfig(
            host="192.168.1.100",
            port=8000,
            serial="CE12345678",
            transport_type=TransportType.WIFI_DONGLE,
            dongle_serial="BA12345678",
        )

        with patch(
            "pylxpweb.transports.create_dongle_transport",
            return_value=mock_transport,
        ) as mock_create:
            result = await station_with_inverter.attach_local_transports([config])

        assert result.matched == 1
        assert result.unmatched == 0
        assert result.failed == 0
        mock_create.assert_called_once()
        mock_transport.connect.assert_called_once()
        assert mock_inverter._transport == mock_transport

    @pytest.mark.asyncio
    async def test_attach_unmatched_serial(self, station_with_inverter: Station) -> None:
        """Test attaching transport with non-existent serial."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE99999999",  # Not in station
            transport_type=TransportType.MODBUS_TCP,
        )

        result = await station_with_inverter.attach_local_transports([config])

        assert result.matched == 0
        assert result.unmatched == 1
        assert result.failed == 0
        assert "CE99999999" in result.unmatched_serials

    @pytest.mark.asyncio
    async def test_attach_connection_failure(
        self, station_with_inverter: Station, mock_inverter: MagicMock
    ) -> None:
        """Test attaching transport that fails to connect."""
        mock_transport = AsyncMock()
        mock_transport.connect = AsyncMock(side_effect=Exception("Connection refused"))

        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
        )

        with patch(
            "pylxpweb.transports.create_modbus_transport",
            return_value=mock_transport,
        ):
            result = await station_with_inverter.attach_local_transports([config])

        assert result.matched == 0
        assert result.unmatched == 0
        assert result.failed == 1
        assert "CE12345678" in result.failed_serials
        assert mock_inverter._transport is None

    @pytest.mark.asyncio
    async def test_attach_multiple_configs(self, mock_client: MagicMock) -> None:
        """Test attaching multiple transports."""
        from datetime import datetime

        from pylxpweb.devices.station import Location

        # Create two inverters
        inv1 = MagicMock()
        inv1.serial_number = "CE11111111"
        inv1._transport = None

        inv2 = MagicMock()
        inv2.serial_number = "CE22222222"
        inv2._transport = None

        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Multi-Inverter Station",
            location=Location(address="", country=""),
            timezone="UTC",
            created_date=datetime.now(),
        )
        station.standalone_inverters = [inv1, inv2]

        configs = [
            TransportConfig(
                host="192.168.1.100",
                port=502,
                serial="CE11111111",
                transport_type=TransportType.MODBUS_TCP,
            ),
            TransportConfig(
                host="192.168.1.101",
                port=502,
                serial="CE22222222",
                transport_type=TransportType.MODBUS_TCP,
            ),
        ]

        mock_transport1 = AsyncMock()
        mock_transport1.connect = AsyncMock()
        mock_transport2 = AsyncMock()
        mock_transport2.connect = AsyncMock()

        with patch(
            "pylxpweb.transports.create_modbus_transport",
            side_effect=[mock_transport1, mock_transport2],
        ):
            result = await station.attach_local_transports(configs)

        assert result.matched == 2
        assert result.unmatched == 0
        assert result.failed == 0
        assert inv1._transport == mock_transport1
        assert inv2._transport == mock_transport2

    @pytest.mark.asyncio
    async def test_attach_mixed_results(self, mock_client: MagicMock) -> None:
        """Test attaching with mixed success/failure results."""
        from datetime import datetime

        from pylxpweb.devices.station import Location

        inv1 = MagicMock()
        inv1.serial_number = "CE11111111"
        inv1._transport = None

        station = Station(
            client=mock_client,
            plant_id=12345,
            name="Test Station",
            location=Location(address="", country=""),
            timezone="UTC",
            created_date=datetime.now(),
        )
        station.standalone_inverters = [inv1]

        configs = [
            TransportConfig(
                host="192.168.1.100",
                port=502,
                serial="CE11111111",  # Will match
                transport_type=TransportType.MODBUS_TCP,
            ),
            TransportConfig(
                host="192.168.1.101",
                port=502,
                serial="CE99999999",  # Won't match
                transport_type=TransportType.MODBUS_TCP,
            ),
        ]

        mock_transport = AsyncMock()
        mock_transport.connect = AsyncMock()

        with patch(
            "pylxpweb.transports.create_modbus_transport",
            return_value=mock_transport,
        ):
            result = await station.attach_local_transports(configs)

        assert result.matched == 1
        assert result.unmatched == 1
        assert result.failed == 0
        assert "CE99999999" in result.unmatched_serials

    @pytest.mark.asyncio
    async def test_attach_empty_configs(self, station_with_inverter: Station) -> None:
        """Test attaching with empty config list."""
        result = await station_with_inverter.attach_local_transports([])

        assert result.matched == 0
        assert result.unmatched == 0
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_attach_with_inverter_family(
        self, station_with_inverter: Station, mock_inverter: MagicMock
    ) -> None:
        """Test attaching transport with inverter family specified."""
        from pylxpweb.devices.inverters._features import InverterFamily

        mock_transport = AsyncMock()
        mock_transport.connect = AsyncMock()

        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
            inverter_family=InverterFamily.EG4_HYBRID,
        )

        with patch(
            "pylxpweb.transports.create_modbus_transport",
            return_value=mock_transport,
        ) as mock_create:
            result = await station_with_inverter.attach_local_transports([config])

        assert result.matched == 1
        # Verify inverter_family was passed to create_modbus_transport
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs.get("inverter_family") == InverterFamily.EG4_HYBRID
