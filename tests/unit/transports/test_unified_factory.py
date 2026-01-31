"""Tests for unified create_transport factory function."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from pylxpweb.transports.dongle import DongleTransport
from pylxpweb.transports.factory import create_transport
from pylxpweb.transports.http import HTTPTransport
from pylxpweb.transports.hybrid import HybridTransport
from pylxpweb.transports.modbus import ModbusTransport

if TYPE_CHECKING:
    pass


@pytest.fixture
def mock_client() -> MagicMock:
    """Create mock LuxpowerClient."""
    return MagicMock()


class TestCreateTransportHTTP:
    """Tests for HTTP transport creation."""

    def test_create_http_transport(self, mock_client: MagicMock) -> None:
        """Test creating HTTP transport."""
        transport = create_transport("http", client=mock_client, serial="CE12345678")

        assert isinstance(transport, HTTPTransport)
        assert transport._serial == "CE12345678"
        assert transport._client is mock_client

    def test_create_http_missing_client(self) -> None:
        """Test error when client is missing."""
        with pytest.raises(ValueError, match="client is required"):
            create_transport("http", serial="CE12345678")

    def test_create_http_missing_serial(self, mock_client: MagicMock) -> None:
        """Test error when serial is missing."""
        with pytest.raises(ValueError, match="serial is required"):
            create_transport("http", client=mock_client)


class TestCreateTransportModbus:
    """Tests for Modbus transport creation."""

    def test_create_modbus_transport_minimal(self) -> None:
        """Test creating Modbus transport with minimal config."""
        transport = create_transport(
            "modbus",
            host="192.168.1.100",
            serial="CE12345678",
        )

        assert isinstance(transport, ModbusTransport)
        assert transport._host == "192.168.1.100"
        assert transport._serial == "CE12345678"
        assert transport._port == 502  # Default
        assert transport._unit_id == 1  # Default

    def test_create_modbus_transport_full(self) -> None:
        """Test creating Modbus transport with all options."""
        transport = create_transport(
            "modbus",
            host="192.168.1.100",
            serial="CE12345678",
            port=503,
            unit_id=2,
            timeout=5.0,
        )

        assert isinstance(transport, ModbusTransport)
        assert transport._port == 503
        assert transport._unit_id == 2
        assert transport._timeout == 5.0

    def test_create_modbus_missing_host(self) -> None:
        """Test error when host is missing."""
        with pytest.raises(ValueError, match="host is required"):
            create_transport("modbus", serial="CE12345678")

    def test_create_modbus_missing_serial(self) -> None:
        """Test error when serial is missing."""
        with pytest.raises(ValueError, match="serial is required"):
            create_transport("modbus", host="192.168.1.100")


class TestCreateTransportDongle:
    """Tests for Dongle transport creation."""

    def test_create_dongle_transport_minimal(self) -> None:
        """Test creating Dongle transport with minimal config."""
        transport = create_transport(
            "dongle",
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        assert isinstance(transport, DongleTransport)
        assert transport._host == "192.168.1.100"
        assert transport._dongle_serial == "BA12345678"
        assert transport._serial == "CE12345678"
        assert transport._port == 8000  # Default

    def test_create_dongle_transport_full(self) -> None:
        """Test creating Dongle transport with all options."""
        transport = create_transport(
            "dongle",
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
            port=8001,
            timeout=15.0,
        )

        assert isinstance(transport, DongleTransport)
        assert transport._port == 8001
        assert transport._timeout == 15.0

    def test_create_dongle_missing_host(self) -> None:
        """Test error when host is missing."""
        with pytest.raises(ValueError, match="host is required"):
            create_transport(
                "dongle",
                dongle_serial="BA12345678",
                inverter_serial="CE12345678",
            )

    def test_create_dongle_missing_dongle_serial(self) -> None:
        """Test error when dongle_serial is missing."""
        with pytest.raises(ValueError, match="dongle_serial is required"):
            create_transport(
                "dongle",
                host="192.168.1.100",
                inverter_serial="CE12345678",
            )

    def test_create_dongle_missing_inverter_serial(self) -> None:
        """Test error when inverter_serial is missing."""
        with pytest.raises(ValueError, match="inverter_serial is required"):
            create_transport(
                "dongle",
                host="192.168.1.100",
                dongle_serial="BA12345678",
            )


class TestCreateTransportHybrid:
    """Tests for Hybrid transport creation."""

    def test_create_hybrid_transport_modbus(self, mock_client: MagicMock) -> None:
        """Test creating Hybrid transport with Modbus local."""
        transport = create_transport(
            "hybrid",
            client=mock_client,
            serial="CE12345678",
            local_host="192.168.1.100",
        )

        assert isinstance(transport, HybridTransport)
        assert isinstance(transport.local_transport, ModbusTransport)
        assert isinstance(transport.http_transport, HTTPTransport)
        assert transport._serial == "CE12345678"

    def test_create_hybrid_transport_dongle(self, mock_client: MagicMock) -> None:
        """Test creating Hybrid transport with Dongle local."""
        transport = create_transport(
            "hybrid",
            client=mock_client,
            serial="CE12345678",
            local_host="192.168.1.100",
            local_type="dongle",
            dongle_serial="BA12345678",
        )

        assert isinstance(transport, HybridTransport)
        assert isinstance(transport.local_transport, DongleTransport)
        assert isinstance(transport.http_transport, HTTPTransport)

    def test_create_hybrid_custom_ports(self, mock_client: MagicMock) -> None:
        """Test creating Hybrid transport with custom ports."""
        transport = create_transport(
            "hybrid",
            client=mock_client,
            serial="CE12345678",
            local_host="192.168.1.100",
            local_port=503,
            timeout=5.0,
            local_retry_interval=120.0,
        )

        assert isinstance(transport, HybridTransport)
        assert transport.local_transport._port == 503
        assert transport._local_retry_interval == 120.0

    def test_create_hybrid_missing_client(self) -> None:
        """Test error when client is missing."""
        with pytest.raises(ValueError, match="client is required"):
            create_transport(
                "hybrid",
                serial="CE12345678",
                local_host="192.168.1.100",
            )

    def test_create_hybrid_missing_serial(self, mock_client: MagicMock) -> None:
        """Test error when serial is missing."""
        with pytest.raises(ValueError, match="serial is required"):
            create_transport(
                "hybrid",
                client=mock_client,
                local_host="192.168.1.100",
            )

    def test_create_hybrid_missing_local_host(self, mock_client: MagicMock) -> None:
        """Test error when local_host is missing."""
        with pytest.raises(ValueError, match="local_host is required"):
            create_transport(
                "hybrid",
                client=mock_client,
                serial="CE12345678",
            )

    def test_create_hybrid_dongle_missing_serial(self, mock_client: MagicMock) -> None:
        """Test error when dongle_serial missing for dongle local type."""
        with pytest.raises(ValueError, match="dongle_serial is required"):
            create_transport(
                "hybrid",
                client=mock_client,
                serial="CE12345678",
                local_host="192.168.1.100",
                local_type="dongle",
            )

    def test_create_hybrid_invalid_local_type(self, mock_client: MagicMock) -> None:
        """Test error with invalid local_type."""
        with pytest.raises(ValueError, match="Invalid local_type"):
            create_transport(
                "hybrid",
                client=mock_client,
                serial="CE12345678",
                local_host="192.168.1.100",
                local_type="invalid",  # type: ignore
            )


class TestCreateTransportInvalid:
    """Tests for invalid transport types."""

    def test_invalid_connection_type(self) -> None:
        """Test error with invalid connection type."""
        with pytest.raises(ValueError, match="Invalid connection_type"):
            create_transport("invalid", serial="CE12345678")  # type: ignore


class TestCreateTransportTypeHints:
    """Tests verifying type hints work correctly."""

    def test_http_return_type(self, mock_client: MagicMock) -> None:
        """Verify HTTP transport returns HTTPTransport."""
        transport = create_transport("http", client=mock_client, serial="CE12345678")
        # Type checker should recognize this as HTTPTransport
        assert transport._client is mock_client

    def test_modbus_return_type(self) -> None:
        """Verify Modbus transport returns ModbusTransport."""
        transport = create_transport("modbus", host="192.168.1.100", serial="CE12345678")
        # Type checker should recognize this as ModbusTransport
        assert transport._host == "192.168.1.100"

    def test_dongle_return_type(self) -> None:
        """Verify Dongle transport returns DongleTransport."""
        transport = create_transport(
            "dongle",
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )
        # Type checker should recognize this as DongleTransport
        assert transport._dongle_serial == "BA12345678"

    def test_hybrid_return_type(self, mock_client: MagicMock) -> None:
        """Verify Hybrid transport returns HybridTransport."""
        transport = create_transport(
            "hybrid",
            client=mock_client,
            serial="CE12345678",
            local_host="192.168.1.100",
        )
        # Type checker should recognize this as HybridTransport
        assert transport.local_transport is not None
        assert transport.http_transport is not None
