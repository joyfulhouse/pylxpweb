"""Tests for transport configuration dataclasses."""

from __future__ import annotations

import pytest

from pylxpweb.devices.inverters._features import InverterFamily
from pylxpweb.transports.config import (
    TransportConfig,
    TransportType,
)


class TestTransportType:
    """Tests for TransportType enum."""

    def test_modbus_tcp_value(self) -> None:
        """Test MODBUS_TCP enum value."""
        assert TransportType.MODBUS_TCP == "modbus_tcp"
        assert TransportType.MODBUS_TCP.value == "modbus_tcp"

    def test_wifi_dongle_value(self) -> None:
        """Test WIFI_DONGLE enum value."""
        assert TransportType.WIFI_DONGLE == "wifi_dongle"
        assert TransportType.WIFI_DONGLE.value == "wifi_dongle"

    def test_http_value(self) -> None:
        """Test HTTP enum value."""
        assert TransportType.HTTP == "http"
        assert TransportType.HTTP.value == "http"

    def test_all_types_have_string_values(self) -> None:
        """Test all transport types have string values for serialization."""
        for transport_type in TransportType:
            assert isinstance(transport_type.value, str)


class TestTransportConfig:
    """Tests for TransportConfig dataclass."""

    def test_modbus_config_minimal(self) -> None:
        """Test minimal Modbus configuration."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
        )

        assert config.host == "192.168.1.100"
        assert config.port == 502
        assert config.serial == "CE12345678"
        assert config.transport_type == TransportType.MODBUS_TCP
        assert config.inverter_family is None
        assert config.dongle_serial is None
        assert config.timeout == 10.0
        assert config.unit_id == 1

    def test_modbus_config_with_family(self) -> None:
        """Test Modbus configuration with inverter family."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
            inverter_family=InverterFamily.LXP_EU,
        )

        assert config.inverter_family == InverterFamily.LXP_EU

    def test_modbus_config_custom_timeout(self) -> None:
        """Test Modbus configuration with custom timeout."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
            timeout=30.0,
            unit_id=2,
        )

        assert config.timeout == 30.0
        assert config.unit_id == 2

    def test_dongle_config_minimal(self) -> None:
        """Test minimal dongle configuration."""
        config = TransportConfig(
            host="192.168.1.100",
            port=8000,
            serial="CE12345678",
            transport_type=TransportType.WIFI_DONGLE,
            dongle_serial="BA12345678",
        )

        assert config.host == "192.168.1.100"
        assert config.port == 8000
        assert config.serial == "CE12345678"
        assert config.transport_type == TransportType.WIFI_DONGLE
        assert config.dongle_serial == "BA12345678"

    def test_http_config(self) -> None:
        """Test HTTP configuration."""
        config = TransportConfig(
            host="",  # Not used for HTTP
            port=0,  # Not used for HTTP
            serial="CE12345678",
            transport_type=TransportType.HTTP,
        )

        assert config.transport_type == TransportType.HTTP


class TestTransportConfigValidation:
    """Tests for TransportConfig validation."""

    def test_validate_modbus_success(self) -> None:
        """Test validation passes for valid Modbus config."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
        )

        # Should not raise
        config.validate()

    def test_validate_dongle_success(self) -> None:
        """Test validation passes for valid dongle config."""
        config = TransportConfig(
            host="192.168.1.100",
            port=8000,
            serial="CE12345678",
            transport_type=TransportType.WIFI_DONGLE,
            dongle_serial="BA12345678",
        )

        # Should not raise
        config.validate()

    def test_validate_dongle_missing_serial(self) -> None:
        """Test validation fails when dongle serial is missing."""
        config = TransportConfig(
            host="192.168.1.100",
            port=8000,
            serial="CE12345678",
            transport_type=TransportType.WIFI_DONGLE,
            # dongle_serial is missing
        )

        with pytest.raises(ValueError, match="dongle_serial required"):
            config.validate()

    def test_validate_serial_too_short(self) -> None:
        """Test validation fails when serial is too short."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE123",  # Too short
            transport_type=TransportType.MODBUS_TCP,
        )

        with pytest.raises(ValueError, match="serial must be 10 characters"):
            config.validate()

    def test_validate_serial_too_long(self) -> None:
        """Test validation fails when serial is too long."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE1234567890",  # Too long
            transport_type=TransportType.MODBUS_TCP,
        )

        with pytest.raises(ValueError, match="serial must be 10 characters"):
            config.validate()

    def test_validate_empty_serial(self) -> None:
        """Test validation fails when serial is empty."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="",
            transport_type=TransportType.MODBUS_TCP,
        )

        with pytest.raises(ValueError, match="serial must be 10 characters"):
            config.validate()

    def test_validate_http_no_validation_needed(self) -> None:
        """Test HTTP config validation (relaxed requirements)."""
        config = TransportConfig(
            host="",
            port=0,
            serial="CE12345678",
            transport_type=TransportType.HTTP,
        )

        # Should not raise - HTTP is handled differently
        config.validate()

    def test_validate_dongle_serial_length(self) -> None:
        """Test validation fails when dongle serial is wrong length."""
        config = TransportConfig(
            host="192.168.1.100",
            port=8000,
            serial="CE12345678",
            transport_type=TransportType.WIFI_DONGLE,
            dongle_serial="BA123",  # Too short
        )

        with pytest.raises(ValueError, match="dongle_serial must be 10 characters"):
            config.validate()


class TestTransportConfigSerialization:
    """Tests for TransportConfig serialization."""

    def test_to_dict_modbus(self) -> None:
        """Test converting Modbus config to dictionary."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
            inverter_family=InverterFamily.PV_SERIES,
            timeout=15.0,
            unit_id=2,
        )

        result = config.to_dict()

        assert result["host"] == "192.168.1.100"
        assert result["port"] == 502
        assert result["serial"] == "CE12345678"
        assert result["transport_type"] == "modbus_tcp"
        assert result["inverter_family"] == "PV_SERIES"
        assert result["timeout"] == 15.0
        assert result["unit_id"] == 2
        assert result["dongle_serial"] is None

    def test_to_dict_dongle(self) -> None:
        """Test converting dongle config to dictionary."""
        config = TransportConfig(
            host="192.168.1.100",
            port=8000,
            serial="CE12345678",
            transport_type=TransportType.WIFI_DONGLE,
            dongle_serial="BA12345678",
        )

        result = config.to_dict()

        assert result["transport_type"] == "wifi_dongle"
        assert result["dongle_serial"] == "BA12345678"

    def test_from_dict_modbus(self) -> None:
        """Test creating Modbus config from dictionary."""
        data = {
            "host": "192.168.1.100",
            "port": 502,
            "serial": "CE12345678",
            "transport_type": "modbus_tcp",
            "inverter_family": "PV_SERIES",
            "timeout": 15.0,
            "unit_id": 2,
        }

        config = TransportConfig.from_dict(data)

        assert config.host == "192.168.1.100"
        assert config.port == 502
        assert config.serial == "CE12345678"
        assert config.transport_type == TransportType.MODBUS_TCP
        assert config.inverter_family == InverterFamily.PV_SERIES
        assert config.timeout == 15.0
        assert config.unit_id == 2

    def test_from_dict_dongle(self) -> None:
        """Test creating dongle config from dictionary."""
        data = {
            "host": "192.168.1.100",
            "port": 8000,
            "serial": "CE12345678",
            "transport_type": "wifi_dongle",
            "dongle_serial": "BA12345678",
        }

        config = TransportConfig.from_dict(data)

        assert config.transport_type == TransportType.WIFI_DONGLE
        assert config.dongle_serial == "BA12345678"

    def test_from_dict_with_none_family(self) -> None:
        """Test creating config from dict with None inverter_family."""
        data = {
            "host": "192.168.1.100",
            "port": 502,
            "serial": "CE12345678",
            "transport_type": "modbus_tcp",
            "inverter_family": None,
        }

        config = TransportConfig.from_dict(data)

        assert config.inverter_family is None

    def test_roundtrip_serialization(self) -> None:
        """Test roundtrip serialization preserves all values."""
        original = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
            inverter_family=InverterFamily.LXP_EU,
            timeout=20.0,
            unit_id=3,
        )

        restored = TransportConfig.from_dict(original.to_dict())

        assert restored.host == original.host
        assert restored.port == original.port
        assert restored.serial == original.serial
        assert restored.transport_type == original.transport_type
        assert restored.inverter_family == original.inverter_family
        assert restored.timeout == original.timeout
        assert restored.unit_id == original.unit_id
