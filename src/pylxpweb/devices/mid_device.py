"""MID Device (GridBOSS) module for grid management and load control.

This module provides the MIDDevice class for GridBOSS devices that handle
grid interconnection, UPS functionality, smart loads, and AC coupling.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pylxpweb.constants import DEVICE_TYPE_CODE_GRIDBOSS
from pylxpweb.exceptions import LuxpowerAPIError, LuxpowerConnectionError, LuxpowerDeviceError

from ._firmware_update_mixin import FirmwareUpdateMixin
from ._mid_runtime_properties import MIDRuntimePropertiesMixin
from .base import BaseDevice
from .models import DeviceClass, DeviceInfo, Entity, StateClass

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient
    from pylxpweb.models import MidboxRuntime
    from pylxpweb.transports.protocol import InverterTransport


class MIDDevice(FirmwareUpdateMixin, MIDRuntimePropertiesMixin, BaseDevice):
    """Represents a GridBOSS/MID device for grid management.

    GridBOSS devices handle:
    - Grid interconnection and UPS functionality
    - Smart load management (4 configurable outputs)
    - AC coupling for additional inverters/generators
    - Load monitoring and control

    Example:
        ```python
        # MIDDevice is typically created from parallel group data
        mid_device = MIDDevice(
            client=client,
            serial_number="1234567890",
            model="GridBOSS"
        )
        await mid_device.refresh()
        print(f"Grid Power: {mid_device.grid_power}W")
        print(f"UPS Power: {mid_device.ups_power}W")
        ```
    """

    def __init__(
        self,
        client: LuxpowerClient,
        serial_number: str,
        model: str = "GridBOSS",
    ) -> None:
        """Initialize MID device.

        Args:
            client: LuxpowerClient instance for API access
            serial_number: MID device serial number (10-digit)
            model: Device model name (default: "GridBOSS")
        """
        super().__init__(client, serial_number, model)

        # Runtime data (private - use properties for access)
        self._runtime: MidboxRuntime | None = None

        # Initialize firmware update detection (from FirmwareUpdateMixin)
        self._init_firmware_update_cache()

        # Local transport for hybrid/local-only mode (optional)
        self._transport: InverterTransport | None = None

    @classmethod
    async def from_transport(
        cls,
        transport: InverterTransport,
        model: str = "GridBOSS",
    ) -> MIDDevice:
        """Create a MIDDevice from a Modbus or Dongle transport.

        This factory method creates a MIDDevice that uses the local transport
        for data fetching instead of HTTP API. Used for local-only or hybrid
        mode operation.

        The method:
        1. Connects to the transport (if not already connected)
        2. Reads device type code from register 19 to verify it's a GridBOSS
        3. Creates MIDDevice with transport attached

        Args:
            transport: Modbus TCP or WiFi dongle transport (must implement
                InverterTransport protocol)
            model: Model name (default: "GridBOSS")

        Returns:
            Configured MIDDevice with transport-backed data

        Raises:
            LuxpowerDeviceError: If device is not a GridBOSS/MIDbox
            TransportConnectionError: If transport fails to connect

        Example:
            >>> from pylxpweb.transports import create_dongle_transport
            >>> transport = create_dongle_transport(
            ...     host="192.168.1.100",
            ...     dongle_serial="DJ12345678",
            ...     inverter_serial="GB12345678",
            ... )
            >>> mid_device = await MIDDevice.from_transport(transport)
            >>> print(f"GridBOSS serial: {mid_device.serial_number}")
        """
        # Ensure transport is connected
        if not transport.is_connected:
            await transport.connect()

        # Read device type code to verify it's a GridBOSS
        device_type_code = 0
        try:
            params = await transport.read_parameters(19, 1)
            if 19 in params:
                device_type_code = params[19]
        except Exception as err:
            _LOGGER.warning(
                "Failed to read device type code for %s: %s, assuming GridBOSS",
                transport.serial,
                err,
            )

        # Verify device is a GridBOSS
        if device_type_code != 0 and device_type_code != DEVICE_TYPE_CODE_GRIDBOSS:
            raise LuxpowerDeviceError(
                f"Device {transport.serial} is not a GridBOSS/MIDbox "
                f"(device type code {device_type_code}, expected {DEVICE_TYPE_CODE_GRIDBOSS}). "
                "Use BaseInverter.from_modbus_transport() for inverters."
            )

        # Create placeholder client (not used for transport mode)
        placeholder_client: Any = None

        # Create MIDDevice with transport
        mid_device = cls(
            client=placeholder_client,
            serial_number=transport.serial,
            model=model,
        )
        mid_device._transport = transport

        _LOGGER.info(
            "Created MIDDevice from transport: serial=%s, model=%s",
            transport.serial,
            model,
        )

        return mid_device

    async def refresh(self) -> None:
        """Refresh MID device runtime data from API."""
        try:
            runtime_data = await self._client.api.devices.get_midbox_runtime(self.serial_number)
            self._runtime = runtime_data
            self._last_refresh = datetime.now()
        except (LuxpowerAPIError, LuxpowerConnectionError, LuxpowerDeviceError) as err:
            # Graceful error handling - keep existing cached data
            _LOGGER.debug("Failed to fetch MID device runtime for %s: %s", self.serial_number, err)

    # All properties are provided by MIDRuntimePropertiesMixin

    def to_device_info(self) -> DeviceInfo:
        """Convert to device info model.

        Returns:
            DeviceInfo with MID device metadata.
        """
        return DeviceInfo(
            identifiers={("pylxpweb", f"mid_{self.serial_number}")},
            name=f"GridBOSS {self.serial_number}",
            manufacturer="EG4/Luxpower",
            model=self.model,
            sw_version=self.firmware_version,
        )

    def to_entities(self) -> list[Entity]:
        """Generate entities for this MID device.

        Returns:
            List of Entity objects for GridBOSS monitoring.

        Note: This implementation focuses on core grid/UPS monitoring.
        Future versions will add smart loads, AC coupling, and generator sensors.
        """
        if self._runtime is None:
            return []

        entities = []

        # Grid Voltage
        entities.append(
            Entity(
                unique_id=f"{self.serial_number}_grid_voltage",
                name=f"{self.model} {self.serial_number} Grid Voltage",
                device_class=DeviceClass.VOLTAGE,
                state_class=StateClass.MEASUREMENT,
                unit_of_measurement="V",
                value=self.grid_voltage,
            )
        )

        # Grid Power
        entities.append(
            Entity(
                unique_id=f"{self.serial_number}_grid_power",
                name=f"{self.model} {self.serial_number} Grid Power",
                device_class=DeviceClass.POWER,
                state_class=StateClass.MEASUREMENT,
                unit_of_measurement="W",
                value=self.grid_power,
            )
        )

        # UPS Voltage
        entities.append(
            Entity(
                unique_id=f"{self.serial_number}_ups_voltage",
                name=f"{self.model} {self.serial_number} UPS Voltage",
                device_class=DeviceClass.VOLTAGE,
                state_class=StateClass.MEASUREMENT,
                unit_of_measurement="V",
                value=self.ups_voltage,
            )
        )

        # UPS Power
        entities.append(
            Entity(
                unique_id=f"{self.serial_number}_ups_power",
                name=f"{self.model} {self.serial_number} UPS Power",
                device_class=DeviceClass.POWER,
                state_class=StateClass.MEASUREMENT,
                unit_of_measurement="W",
                value=self.ups_power,
            )
        )

        # Hybrid Power
        entities.append(
            Entity(
                unique_id=f"{self.serial_number}_hybrid_power",
                name=f"{self.model} {self.serial_number} Hybrid Power",
                device_class=DeviceClass.POWER,
                state_class=StateClass.MEASUREMENT,
                unit_of_measurement="W",
                value=self.hybrid_power,
            )
        )

        # Grid Frequency
        entities.append(
            Entity(
                unique_id=f"{self.serial_number}_grid_frequency",
                name=f"{self.model} {self.serial_number} Grid Frequency",
                device_class=DeviceClass.FREQUENCY,
                state_class=StateClass.MEASUREMENT,
                unit_of_measurement="Hz",
                value=self.grid_frequency,
            )
        )

        return entities
