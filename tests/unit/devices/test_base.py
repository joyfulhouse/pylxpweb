"""Unit tests for BaseDevice abstract class.

This module tests the BaseDevice abstract class that provides common
functionality for all device types (inverters, batteries, MID devices).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.base import BaseDevice
from pylxpweb.devices.models import DeviceInfo, Entity


class ConcreteDevice(BaseDevice):
    """Concrete implementation of BaseDevice for testing."""

    async def refresh(self) -> None:
        """Refresh device data."""
        self._last_refresh = datetime.now()

    def to_device_info(self) -> DeviceInfo:
        """Convert to HA device info."""
        return DeviceInfo(
            identifiers={("pylxpweb", f"test_{self.serial_number}")},
            name=f"Test Device {self.serial_number}",
            manufacturer="Test Manufacturer",
            model=self.model,
        )

    def to_entities(self) -> list[Entity]:
        """Generate HA entities."""
        return [
            Entity(
                unique_id=f"{self.serial_number}_test",
                name=f"Test {self.serial_number}",
                value=42,
            )
        ]


class TestBaseDeviceInitialization:
    """Test BaseDevice initialization."""

    def test_base_device_initialization(self) -> None:
        """Test BaseDevice constructor."""
        client = LuxpowerClient("test_user", "test_pass")
        device = ConcreteDevice(client, "1234567890", "TestModel")

        assert device.serial_number == "1234567890"
        assert device.model == "TestModel"
        assert device._client is client
        assert device._last_refresh is None

    def test_base_device_default_refresh_interval(self) -> None:
        """Test default refresh interval is 30 seconds."""
        client = LuxpowerClient("test_user", "test_pass")
        device = ConcreteDevice(client, "1234567890", "TestModel")

        assert device._refresh_interval == timedelta(seconds=30)


class TestNeedsRefresh:
    """Test needs_refresh property logic."""

    def test_needs_refresh_initial_state(self) -> None:
        """Test needs_refresh returns True before first refresh."""
        client = LuxpowerClient("test_user", "test_pass")
        device = ConcreteDevice(client, "1234567890", "TestModel")

        assert device.needs_refresh is True

    @pytest.mark.asyncio
    async def test_needs_refresh_after_refresh(self) -> None:
        """Test needs_refresh returns False immediately after refresh."""
        client = LuxpowerClient("test_user", "test_pass")
        device = ConcreteDevice(client, "1234567890", "TestModel")

        await device.refresh()

        assert device.needs_refresh is False

    @pytest.mark.asyncio
    async def test_needs_refresh_after_ttl_expiration(self) -> None:
        """Test needs_refresh returns True after TTL expires."""
        client = LuxpowerClient("test_user", "test_pass")
        device = ConcreteDevice(client, "1234567890", "TestModel")

        # Refresh device
        await device.refresh()
        assert device.needs_refresh is False

        # Mock time advancing beyond TTL
        future_time = datetime.now() + timedelta(seconds=31)
        with patch("pylxpweb.devices.base.datetime") as mock_dt:
            mock_dt.now.return_value = future_time
            assert device.needs_refresh is True


class TestRefreshIntervalConfiguration:
    """Test configurable refresh intervals."""

    def test_custom_refresh_interval(self) -> None:
        """Test setting custom refresh interval."""
        client = LuxpowerClient("test_user", "test_pass")
        device = ConcreteDevice(client, "1234567890", "TestModel")

        # Set custom interval
        device._refresh_interval = timedelta(seconds=60)

        assert device._refresh_interval == timedelta(seconds=60)

    @pytest.mark.asyncio
    async def test_custom_refresh_interval_affects_needs_refresh(self) -> None:
        """Test custom interval affects needs_refresh logic."""
        client = LuxpowerClient("test_user", "test_pass")
        device = ConcreteDevice(client, "1234567890", "TestModel")
        device._refresh_interval = timedelta(seconds=60)

        await device.refresh()

        # 31 seconds later - should NOT need refresh (TTL is 60s)
        future_time = datetime.now() + timedelta(seconds=31)
        with patch("pylxpweb.devices.base.datetime") as mock_dt:
            mock_dt.now.return_value = future_time
            assert device.needs_refresh is False

        # 61 seconds later - SHOULD need refresh
        future_time = datetime.now() + timedelta(seconds=61)
        with patch("pylxpweb.devices.base.datetime") as mock_dt:
            mock_dt.now.return_value = future_time
            assert device.needs_refresh is True


class TestAbstractMethods:
    """Test that abstract methods are enforced."""

    def test_cannot_instantiate_base_device_directly(self) -> None:
        """Test that BaseDevice cannot be instantiated directly."""
        client = LuxpowerClient("test_user", "test_pass")

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            BaseDevice(client, "1234567890", "TestModel")  # type: ignore


class TestHADeviceInfo:
    """Test to_device_info method."""

    def test_to_device_info_returns_device_info(self) -> None:
        """Test to_device_info returns DeviceInfo instance."""
        client = LuxpowerClient("test_user", "test_pass")
        device = ConcreteDevice(client, "1234567890", "TestModel")

        device_info = device.to_device_info()

        assert isinstance(device_info, DeviceInfo)
        assert device_info.name == "Test Device 1234567890"
        assert device_info.manufacturer == "Test Manufacturer"
        assert device_info.model == "TestModel"

    def test_to_device_info_identifiers_format(self) -> None:
        """Test device identifiers use correct format."""
        client = LuxpowerClient("test_user", "test_pass")
        device = ConcreteDevice(client, "1234567890", "TestModel")

        device_info = device.to_device_info()

        assert ("pylxpweb", "test_1234567890") in device_info.identifiers


class TestHAEntities:
    """Test to_entities method."""

    def test_to_entities_returns_list(self) -> None:
        """Test to_entities returns list of Entity."""
        client = LuxpowerClient("test_user", "test_pass")
        device = ConcreteDevice(client, "1234567890", "TestModel")

        entities = device.to_entities()

        assert isinstance(entities, list)
        assert len(entities) > 0
        assert all(isinstance(e, Entity) for e in entities)

    def test_to_entities_unique_ids(self) -> None:
        """Test entities have proper unique IDs."""
        client = LuxpowerClient("test_user", "test_pass")
        device = ConcreteDevice(client, "1234567890", "TestModel")

        entities = device.to_entities()

        assert entities[0].unique_id == "1234567890_test"
        assert entities[0].name == "Test 1234567890"
        assert entities[0].value == 42


class TestClientReference:
    """Test that device has reference to client."""

    def test_device_has_client_reference(self) -> None:
        """Test device stores reference to client."""
        client = LuxpowerClient("test_user", "test_pass")
        device = ConcreteDevice(client, "1234567890", "TestModel")

        assert device._client is client

    def test_multiple_devices_same_client(self) -> None:
        """Test multiple devices can share same client."""
        client = LuxpowerClient("test_user", "test_pass")
        device1 = ConcreteDevice(client, "1111111111", "Model1")
        device2 = ConcreteDevice(client, "2222222222", "Model2")

        assert device1._client is client
        assert device2._client is client
        assert device1._client is device2._client


class TestLocalTransportSupport:
    """Tests for local transport (Modbus/Dongle) support."""

    def test_local_transport_initially_none(self) -> None:
        """Test that local transport is None by default."""
        client = LuxpowerClient("test_user", "test_pass")
        device = ConcreteDevice(client, "1234567890", "TestModel")

        assert device._local_transport is None

    def test_has_local_transport_false_initially(self) -> None:
        """Test has_local_transport returns False when no transport."""
        client = LuxpowerClient("test_user", "test_pass")
        device = ConcreteDevice(client, "1234567890", "TestModel")

        assert device.has_local_transport is False

    def test_has_local_transport_true_when_set(self) -> None:
        """Test has_local_transport returns True when transport attached."""
        from unittest.mock import MagicMock

        client = LuxpowerClient("test_user", "test_pass")
        device = ConcreteDevice(client, "1234567890", "TestModel")

        # Attach mock transport
        mock_transport = MagicMock()
        device._local_transport = mock_transport

        assert device.has_local_transport is True

    def test_is_local_only_false_with_credentials(self) -> None:
        """Test is_local_only returns False when client has credentials."""
        from unittest.mock import MagicMock

        client = LuxpowerClient("test_user", "test_pass")
        device = ConcreteDevice(client, "1234567890", "TestModel")

        # Attach mock transport
        mock_transport = MagicMock()
        device._local_transport = mock_transport

        assert device.is_local_only is False

    def test_is_local_only_true_without_credentials(self) -> None:
        """Test is_local_only returns True when client has no credentials."""
        from unittest.mock import MagicMock

        # Create client without credentials (local-only mode)
        client = LuxpowerClient("", "")
        device = ConcreteDevice(client, "1234567890", "TestModel")

        # Attach mock transport
        mock_transport = MagicMock()
        device._local_transport = mock_transport

        assert device.is_local_only is True

    def test_is_local_only_false_without_transport(self) -> None:
        """Test is_local_only returns False when no transport attached."""
        client = LuxpowerClient("", "")  # Empty credentials
        device = ConcreteDevice(client, "1234567890", "TestModel")

        # No transport attached
        assert device.is_local_only is False
