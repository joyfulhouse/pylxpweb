"""Base device classes for pylxpweb.

This module provides abstract base classes for all device types,
implementing common functionality like refresh intervals, caching,
and Home Assistant integration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .models import DeviceInfo, Entity

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient
    from pylxpweb.transports.protocol import InverterTransport


class BaseDevice(ABC):
    """Abstract base class for all device types.

    This class provides common functionality for inverters, batteries,
    MID devices, and stations, including:
    - Refresh interval management with TTL
    - Client reference for API access
    - Home Assistant integration methods

    Subclasses must implement:
    - refresh(): Load/reload device data from API
    - to_ha_device_info(): Convert to HA device registry format
    - to_ha_entities(): Generate HA entity list

    Example:
        ```python
        class MyDevice(BaseDevice):
            async def refresh(self) -> None:
                data = await self._client.api.devices.get_data(self.serial_number)
                self._process_data(data)
                self._last_refresh = datetime.now()

            def to_device_info(self) -> DeviceInfo:
                return DeviceInfo(
                    identifiers={("pylxpweb", f"device_{self.serial_number}")},
                    name=f"My Device {self.serial_number}",
                    manufacturer="EG4",
                    model=self.model,
                )

            def to_entities(self) -> list[Entity]:
                return [
                    Entity(unique_id=f"{self.serial_number}_power", ...)
                ]
        ```
    """

    def __init__(
        self,
        client: LuxpowerClient,
        serial_number: str,
        model: str,
    ) -> None:
        """Initialize base device.

        Args:
            client: LuxpowerClient instance for API access
            serial_number: Device serial number (unique identifier)
            model: Device model name
        """
        self._client = client
        self.serial_number = serial_number
        self._model = model
        self._last_refresh: datetime | None = None
        self._refresh_interval = timedelta(seconds=30)

        # Local transport (Modbus/Dongle) - None means HTTP-only mode
        self._local_transport: InverterTransport | None = None

    @property
    def model(self) -> str:
        """Get device model name.

        Returns:
            Device model name, or "Unknown" if not available.
        """
        return self._model if self._model else "Unknown"

    @property
    def needs_refresh(self) -> bool:
        """Check if device data needs refreshing based on TTL.

        Returns:
            True if device has never been refreshed or TTL has expired,
            False if data is still fresh.
        """
        if self._last_refresh is None:
            return True
        return datetime.now() - self._last_refresh > self._refresh_interval

    @property
    def has_local_transport(self) -> bool:
        """Check if device has an attached local transport.

        Returns:
            True if a local transport (Modbus or Dongle) is attached,
            False if only HTTP API is available.
        """
        return self._local_transport is not None

    @property
    def is_local_only(self) -> bool:
        """Check if device is local-only (no HTTP client credentials).

        Returns:
            True if the device was created from local transport without
            cloud API credentials, False otherwise.
        """
        return self._local_transport is not None and not self._client.username

    @abstractmethod
    async def refresh(self) -> None:
        """Refresh device data from API.

        Subclasses must implement this to load/reload device-specific data.
        Should update self._last_refresh on success.
        """
        ...

    @abstractmethod
    def to_device_info(self) -> DeviceInfo:
        """Convert device to generic device info model.

        Returns:
            DeviceInfo instance with device metadata.
        """
        ...

    @abstractmethod
    def to_entities(self) -> list[Entity]:
        """Generate entities for this device.

        Returns:
            List of Entity instances (sensors, switches, etc.)
        """
        ...
