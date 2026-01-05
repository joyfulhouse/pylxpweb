"""Tests for transport factory functions."""

from __future__ import annotations

from unittest.mock import MagicMock

from pylxpweb.transports import (
    HTTPTransport,
    ModbusTransport,
    create_http_transport,
    create_modbus_transport,
)


class TestCreateHTTPTransport:
    """Tests for create_http_transport factory function."""

    def test_creates_http_transport(self) -> None:
        """Test that factory creates HTTPTransport."""
        client = MagicMock()
        transport = create_http_transport(client, serial="CE12345678")

        assert isinstance(transport, HTTPTransport)
        assert transport.serial == "CE12345678"
        assert transport._client is client

    def test_is_not_connected_initially(self) -> None:
        """Test transport is not connected initially."""
        client = MagicMock()
        transport = create_http_transport(client, serial="CE12345678")

        assert transport.is_connected is False


class TestCreateModbusTransport:
    """Tests for create_modbus_transport factory function."""

    def test_creates_modbus_transport_defaults(self) -> None:
        """Test factory creates ModbusTransport with defaults."""
        transport = create_modbus_transport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        assert isinstance(transport, ModbusTransport)
        assert transport.serial == "CE12345678"
        assert transport._host == "192.168.1.100"
        assert transport._port == 502
        assert transport._unit_id == 1
        assert transport._timeout == 10.0

    def test_creates_modbus_transport_custom(self) -> None:
        """Test factory creates ModbusTransport with custom settings."""
        transport = create_modbus_transport(
            host="192.168.1.100",
            serial="CE12345678",
            port=8502,
            unit_id=2,
            timeout=30.0,
        )

        assert transport._port == 8502
        assert transport._unit_id == 2
        assert transport._timeout == 30.0

    def test_is_not_connected_initially(self) -> None:
        """Test transport is not connected initially."""
        transport = create_modbus_transport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        assert transport.is_connected is False


class TestTransportImports:
    """Tests for transport module exports."""

    def test_all_exports_available(self) -> None:
        """Test all expected items are exported."""
        from pylxpweb import transports

        # Factory functions
        assert hasattr(transports, "create_http_transport")
        assert hasattr(transports, "create_modbus_transport")

        # Transport classes
        assert hasattr(transports, "HTTPTransport")
        assert hasattr(transports, "ModbusTransport")
        assert hasattr(transports, "BaseTransport")
        assert hasattr(transports, "InverterTransport")

        # Data classes
        assert hasattr(transports, "InverterRuntimeData")
        assert hasattr(transports, "InverterEnergyData")
        assert hasattr(transports, "BatteryData")
        assert hasattr(transports, "BatteryBankData")

        # Capabilities
        assert hasattr(transports, "TransportCapabilities")
        assert hasattr(transports, "HTTP_CAPABILITIES")
        assert hasattr(transports, "MODBUS_CAPABILITIES")

        # Exceptions
        assert hasattr(transports, "TransportError")
        assert hasattr(transports, "TransportConnectionError")
        assert hasattr(transports, "TransportReadError")
        assert hasattr(transports, "TransportWriteError")
        assert hasattr(transports, "TransportTimeoutError")
        assert hasattr(transports, "UnsupportedOperationError")
