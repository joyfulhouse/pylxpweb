"""Tests for transport factory functions."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pylxpweb.devices.inverters._features import InverterFamily
from pylxpweb.transports import (
    DongleTransport,
    HTTPTransport,
    ModbusTransport,
    create_dongle_transport,
    create_http_transport,
    create_modbus_transport,
)
from pylxpweb.transports.config import TransportConfig, TransportType
from pylxpweb.transports.factory import create_transport_from_config


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

        # Config classes
        assert hasattr(transports, "TransportConfig")
        assert hasattr(transports, "TransportType")

        # Config-based factory
        assert hasattr(transports, "create_transport_from_config")


class TestCreateDongleTransport:
    """Tests for create_dongle_transport factory function."""

    def test_creates_dongle_transport_defaults(self) -> None:
        """Test factory creates DongleTransport with defaults."""
        transport = create_dongle_transport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        assert isinstance(transport, DongleTransport)
        assert transport.serial == "CE12345678"
        assert transport._host == "192.168.1.100"
        assert transport._port == 8000
        assert transport._timeout == 10.0

    def test_creates_dongle_transport_custom(self) -> None:
        """Test factory creates DongleTransport with custom settings."""
        transport = create_dongle_transport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
            port=9000,
            timeout=30.0,
        )

        assert transport._port == 9000
        assert transport._timeout == 30.0

    def test_is_not_connected_initially(self) -> None:
        """Test transport is not connected initially."""
        transport = create_dongle_transport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        assert transport.is_connected is False


class TestCreateTransportFromConfig:
    """Tests for create_transport_from_config factory function."""

    def test_creates_modbus_transport_from_config(self) -> None:
        """Test factory creates ModbusTransport from config."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
            timeout=15.0,
            unit_id=2,
        )

        transport = create_transport_from_config(config)

        assert isinstance(transport, ModbusTransport)
        assert transport.serial == "CE12345678"
        assert transport._host == "192.168.1.100"
        assert transport._port == 502
        assert transport._timeout == 15.0
        assert transport._unit_id == 2

    def test_creates_modbus_with_inverter_family(self) -> None:
        """Test factory creates ModbusTransport with inverter family."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
            inverter_family=InverterFamily.LXP,
        )

        transport = create_transport_from_config(config)

        assert isinstance(transport, ModbusTransport)
        assert transport._inverter_family == InverterFamily.LXP

    def test_creates_dongle_transport_from_config(self) -> None:
        """Test factory creates DongleTransport from config."""
        config = TransportConfig(
            host="192.168.1.100",
            port=8000,
            serial="CE12345678",
            transport_type=TransportType.WIFI_DONGLE,
            dongle_serial="BA12345678",
            timeout=20.0,
        )

        transport = create_transport_from_config(config)

        assert isinstance(transport, DongleTransport)
        assert transport.serial == "CE12345678"
        assert transport._host == "192.168.1.100"
        assert transport._port == 8000
        assert transport._timeout == 20.0

    def test_raises_for_http_transport_type(self) -> None:
        """Test factory raises for HTTP transport type (requires client)."""
        config = TransportConfig(
            host="",
            port=0,
            serial="CE12345678",
            transport_type=TransportType.HTTP,
        )

        with pytest.raises(ValueError, match="HTTP transport requires"):
            create_transport_from_config(config)

    def test_validates_config_before_creation(self) -> None:
        """Test TransportConfig validates at creation time."""
        # Validation now happens in TransportConfig.__post_init__
        # Missing dongle_serial should fail at config creation time
        with pytest.raises(ValueError, match="dongle_serial is required"):
            TransportConfig(
                host="192.168.1.100",
                port=8000,
                serial="CE12345678",
                transport_type=TransportType.WIFI_DONGLE,
                # Missing dongle_serial - should fail validation
            )
