"""Tests for transport protocol and base classes."""

from __future__ import annotations

import pytest

from pylxpweb.transports.capabilities import (
    HTTP_CAPABILITIES,
    MODBUS_CAPABILITIES,
    TransportCapabilities,
)
from pylxpweb.transports.exceptions import TransportConnectionError
from pylxpweb.transports.protocol import BaseTransport


class TestTransportCapabilities:
    """Tests for TransportCapabilities."""

    def test_http_capabilities(self) -> None:
        """Test HTTP transport capabilities."""
        assert HTTP_CAPABILITIES.can_read_runtime is True
        assert HTTP_CAPABILITIES.can_read_energy is True
        assert HTTP_CAPABILITIES.can_read_battery is True
        assert HTTP_CAPABILITIES.can_read_parameters is True
        assert HTTP_CAPABILITIES.can_write_parameters is True
        assert HTTP_CAPABILITIES.is_local is False
        assert HTTP_CAPABILITIES.requires_authentication is True
        # Cloud-specific features
        assert HTTP_CAPABILITIES.can_discover_devices is True
        assert HTTP_CAPABILITIES.can_read_history is True

    def test_modbus_capabilities(self) -> None:
        """Test Modbus transport capabilities."""
        assert MODBUS_CAPABILITIES.can_read_runtime is True
        assert MODBUS_CAPABILITIES.can_read_energy is True
        assert MODBUS_CAPABILITIES.can_read_battery is True
        assert MODBUS_CAPABILITIES.can_read_parameters is True
        assert MODBUS_CAPABILITIES.can_write_parameters is True
        assert MODBUS_CAPABILITIES.is_local is True
        assert MODBUS_CAPABILITIES.requires_authentication is False
        # Cloud-specific features not available
        assert MODBUS_CAPABILITIES.can_discover_devices is False
        assert MODBUS_CAPABILITIES.can_read_history is False

    def test_custom_capabilities(self) -> None:
        """Test creating custom capabilities."""
        caps = TransportCapabilities(
            can_read_runtime=True,
            can_read_energy=False,
            can_read_battery=False,
            can_read_parameters=True,
            can_write_parameters=False,
            is_local=True,
        )

        assert caps.can_read_runtime is True
        assert caps.can_read_energy is False
        assert caps.can_write_parameters is False
        assert caps.is_local is True


class ConcreteTransport(BaseTransport):
    """Concrete implementation for testing BaseTransport."""

    @property
    def capabilities(self) -> TransportCapabilities:
        return HTTP_CAPABILITIES

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False


class TestBaseTransport:
    """Tests for BaseTransport abstract class."""

    def test_init(self) -> None:
        """Test transport initialization."""
        transport = ConcreteTransport(serial="CE12345678")

        assert transport.serial == "CE12345678"
        assert transport.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_disconnect(self) -> None:
        """Test connect and disconnect."""
        transport = ConcreteTransport(serial="CE12345678")

        await transport.connect()
        assert transport.is_connected is True

        await transport.disconnect()
        assert transport.is_connected is False

    @pytest.mark.asyncio
    async def test_ensure_connected_raises_when_not_connected(self) -> None:
        """Test _ensure_connected raises when not connected."""
        transport = ConcreteTransport(serial="CE12345678")

        with pytest.raises(TransportConnectionError, match="Transport not connected"):
            transport._ensure_connected()

    @pytest.mark.asyncio
    async def test_ensure_connected_passes_when_connected(self) -> None:
        """Test _ensure_connected passes when connected."""
        transport = ConcreteTransport(serial="CE12345678")
        await transport.connect()

        # Should not raise
        transport._ensure_connected()
