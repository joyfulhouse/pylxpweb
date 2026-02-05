"""Tests for pylxpweb.transports.config module."""

from __future__ import annotations

import pytest

from pylxpweb.devices.inverters._features import InverterFamily
from pylxpweb.transports.config import AttachResult, TransportConfig, TransportType


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

    def test_from_string_modbus(self) -> None:
        """Test creating TransportType from string."""
        transport_type = TransportType("modbus_tcp")
        assert transport_type == TransportType.MODBUS_TCP

    def test_from_string_dongle(self) -> None:
        """Test creating TransportType from string."""
        transport_type = TransportType("wifi_dongle")
        assert transport_type == TransportType.WIFI_DONGLE

    def test_from_invalid_string(self) -> None:
        """Test creating TransportType from invalid string raises ValueError."""
        with pytest.raises(ValueError):
            TransportType("invalid")

    def test_all_types_have_string_values(self) -> None:
        """Test all transport types have string values for serialization."""
        for transport_type in TransportType:
            assert isinstance(transport_type.value, str)


class TestTransportConfig:
    """Tests for TransportConfig dataclass."""

    def test_modbus_config_basic(self) -> None:
        """Test creating basic Modbus config."""
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
        assert config.unit_id == 1  # default
        assert config.timeout == 10.0  # default
        assert config.inverter_family is None
        assert config.dongle_serial is None

    def test_modbus_config_with_unit_id(self) -> None:
        """Test creating Modbus config with custom unit_id."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
            unit_id=5,
        )
        assert config.unit_id == 5

    def test_modbus_config_with_family(self) -> None:
        """Test Modbus configuration with inverter family."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
            inverter_family=InverterFamily.LXP,
        )
        assert config.inverter_family == InverterFamily.LXP

    def test_dongle_config_basic(self) -> None:
        """Test creating basic WiFi dongle config."""
        config = TransportConfig(
            host="192.168.1.101",
            port=8000,
            serial="CE87654321",
            transport_type=TransportType.WIFI_DONGLE,
            dongle_serial="BA12345678",
        )
        assert config.host == "192.168.1.101"
        assert config.port == 8000
        assert config.serial == "CE87654321"
        assert config.transport_type == TransportType.WIFI_DONGLE
        assert config.dongle_serial == "BA12345678"

    def test_dongle_config_requires_dongle_serial(self) -> None:
        """Test that WiFi dongle config requires dongle_serial."""
        with pytest.raises(ValueError, match="dongle_serial is required"):
            TransportConfig(
                host="192.168.1.101",
                port=8000,
                serial="CE87654321",
                transport_type=TransportType.WIFI_DONGLE,
                # Missing dongle_serial
            )

    def test_config_with_inverter_family(self) -> None:
        """Test creating config with inverter family."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
            inverter_family=InverterFamily.EG4_HYBRID,
        )
        assert config.inverter_family == InverterFamily.EG4_HYBRID

    def test_config_requires_host(self) -> None:
        """Test that config requires non-empty host."""
        with pytest.raises(ValueError, match="host is required"):
            TransportConfig(
                host="",
                port=502,
                serial="CE12345678",
                transport_type=TransportType.MODBUS_TCP,
            )

    def test_config_requires_serial(self) -> None:
        """Test that config requires non-empty serial."""
        with pytest.raises(ValueError, match="serial is required"):
            TransportConfig(
                host="192.168.1.100",
                port=502,
                serial="",
                transport_type=TransportType.MODBUS_TCP,
            )

    def test_config_validates_port_range(self) -> None:
        """Test that config validates port range."""
        with pytest.raises(ValueError, match="Invalid port"):
            TransportConfig(
                host="192.168.1.100",
                port=0,
                serial="CE12345678",
                transport_type=TransportType.MODBUS_TCP,
            )

        with pytest.raises(ValueError, match="Invalid port"):
            TransportConfig(
                host="192.168.1.100",
                port=65536,
                serial="CE12345678",
                transport_type=TransportType.MODBUS_TCP,
            )

    def test_config_with_custom_timeout(self) -> None:
        """Test creating config with custom timeout."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
            timeout=30.0,
        )
        assert config.timeout == 30.0


class TestTransportConfigSerialization:
    """Tests for TransportConfig serialization."""

    def test_to_dict_modbus(self) -> None:
        """Test converting Modbus config to dictionary."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
            inverter_family=InverterFamily.EG4_HYBRID,
            timeout=15.0,
            unit_id=2,
        )

        result = config.to_dict()

        assert result["host"] == "192.168.1.100"
        assert result["port"] == 502
        assert result["serial"] == "CE12345678"
        assert result["transport_type"] == "modbus_tcp"
        assert result["inverter_family"] == "EG4_HYBRID"
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
        assert config.inverter_family == InverterFamily.EG4_HYBRID
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
            inverter_family=InverterFamily.LXP,
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


class TestAttachResult:
    """Tests for AttachResult dataclass."""

    def test_default_values(self) -> None:
        """Test AttachResult default values."""
        result = AttachResult()
        assert result.matched == 0
        assert result.unmatched == 0
        assert result.failed == 0
        assert result.unmatched_serials == []
        assert result.failed_serials == []

    def test_with_values(self) -> None:
        """Test AttachResult with values."""
        result = AttachResult(
            matched=2,
            unmatched=1,
            failed=1,
            unmatched_serials=["CE11111111"],
            failed_serials=["CE22222222"],
        )
        assert result.matched == 2
        assert result.unmatched == 1
        assert result.failed == 1
        assert result.unmatched_serials == ["CE11111111"]
        assert result.failed_serials == ["CE22222222"]

    def test_mutable_lists(self) -> None:
        """Test that AttachResult lists are mutable and independent."""
        result1 = AttachResult()
        result2 = AttachResult()

        result1.unmatched_serials.append("CE12345678")
        assert result1.unmatched_serials == ["CE12345678"]
        assert result2.unmatched_serials == []  # independent
