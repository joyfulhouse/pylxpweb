"""MID Device (GridBOSS) module for grid management and load control.

This module provides the MIDDevice class for GridBOSS devices that handle
grid interconnection, UPS functionality, smart loads, and AC coupling.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from pylxpweb.constants import scale_mid_frequency, scale_mid_voltage
from pylxpweb.exceptions import LuxpowerAPIError, LuxpowerConnectionError, LuxpowerDeviceError

from .base import BaseDevice
from .models import DeviceClass, DeviceInfo, Entity, StateClass

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient
    from pylxpweb.models import MidboxRuntime


class MIDDevice(BaseDevice):
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

        # Runtime data
        self.runtime: MidboxRuntime | None = None

    async def refresh(self) -> None:
        """Refresh MID device runtime data from API."""
        try:
            runtime_data = await self._client.api.devices.get_midbox_runtime(self.serial_number)
            self.runtime = runtime_data
            self._last_refresh = datetime.now()
        except (LuxpowerAPIError, LuxpowerConnectionError, LuxpowerDeviceError) as err:
            # Graceful error handling - keep existing cached data
            _LOGGER.debug("Failed to fetch MID device runtime for %s: %s", self.serial_number, err)

    @property
    def has_data(self) -> bool:
        """Check if device has runtime data.

        Returns:
            True if runtime data is available.
        """
        return self.runtime is not None

    @property
    def grid_voltage(self) -> float:
        """Get grid voltage in volts.

        Returns:
            Grid RMS voltage (scaled from gridRmsVolt ÷10), or 0.0 if no data.
        """
        if self.runtime is None:
            return 0.0
        return scale_mid_voltage(self.runtime.midboxData.gridRmsVolt)

    @property
    def ups_voltage(self) -> float:
        """Get UPS voltage in volts.

        Returns:
            UPS RMS voltage (scaled from upsRmsVolt ÷10), or 0.0 if no data.
        """
        if self.runtime is None:
            return 0.0
        return scale_mid_voltage(self.runtime.midboxData.upsRmsVolt)

    @property
    def grid_power(self) -> int:
        """Get total grid power in watts (L1 + L2).

        Returns:
            Total grid power, or 0 if no data.
        """
        if self.runtime is None:
            return 0
        return self.runtime.midboxData.gridL1ActivePower + self.runtime.midboxData.gridL2ActivePower

    @property
    def ups_power(self) -> int:
        """Get total UPS power in watts (L1 + L2).

        Returns:
            Total UPS power, or 0 if no data.
        """
        if self.runtime is None:
            return 0
        return self.runtime.midboxData.upsL1ActivePower + self.runtime.midboxData.upsL2ActivePower

    @property
    def hybrid_power(self) -> int:
        """Get hybrid power in watts.

        Returns:
            Hybrid power (combined system power), or 0 if no data.
        """
        if self.runtime is None:
            return 0
        return self.runtime.midboxData.hybridPower

    @property
    def grid_frequency(self) -> float:
        """Get grid frequency in Hz.

        Returns:
            Grid frequency (scaled from gridFreq ÷100), or 0.0 if no data.
        """
        if self.runtime is None:
            return 0.0
        return scale_mid_frequency(self.runtime.midboxData.gridFreq)

    @property
    def firmware_version(self) -> str | None:
        """Get firmware version.

        Returns:
            Firmware version string, or None if no data.
        """
        if self.runtime is None:
            return None
        return self.runtime.fwCode

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
        if self.runtime is None:
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
