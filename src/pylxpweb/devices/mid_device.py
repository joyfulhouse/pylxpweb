"""MID Device (GridBOSS) module for grid management and load control.

This module provides the MIDDevice class for GridBOSS devices that handle
grid interconnection, UPS functionality, smart loads, and AC coupling.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pylxpweb.constants import DEVICE_TYPE_CODE_GRIDBOSS
from pylxpweb.exceptions import LuxpowerDeviceError

from ._firmware_update_mixin import FirmwareUpdateMixin
from ._mid_runtime_properties import MIDRuntimePropertiesMixin
from .base import BaseDevice
from .models import DeviceClass, DeviceInfo, Entity, StateClass

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient
    from pylxpweb.models import MidboxRuntime
    from pylxpweb.transports.data import MidboxRuntimeData
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
        self._transport_runtime: MidboxRuntimeData | None = None

        # Timestamp of last accepted runtime data (for daily energy bounds).
        self._runtime_cache_time: datetime | None = None

        # Max power for the system behind this GridBOSS (kW).
        # Set by the coordinator once inverter count and ratings are known.
        self._max_system_power_kw: float = 0.0

        # Initialize firmware update detection (from FirmwareUpdateMixin)
        self._init_firmware_update_cache()

        # Local transport for hybrid/local-only mode (optional)
        self._transport: InverterTransport | None = None

    def set_max_system_power(self, total_kw: float) -> None:
        """Set the max system power behind this GridBOSS.

        Called by the coordinator once inverter ratings are known.
        Computes ``_max_energy_delta`` as ``total_kw * 1.5`` (50% margin)
        and ``_max_power_watts`` as ``total_kw * 2000`` (2x margin).
        """
        self._max_system_power_kw = total_kw
        if total_kw > 0:
            self._rated_power_kw = total_kw
            self._max_energy_delta = total_kw * 1.5
            self._max_power_watts = total_kw * 2000
            _LOGGER.debug(
                "GridBOSS %s: system power=%dkW, max_energy_delta=%.0f kWh, max_power=%.0fW",
                self.serial_number,
                total_kw,
                self._max_energy_delta,
                self._max_power_watts,
            )

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

    def _runtime_elapsed_seconds(self) -> float | None:
        """Seconds since last successful runtime cache, or None at startup."""
        if self._runtime_cache_time is None:
            return None
        return (datetime.now() - self._runtime_cache_time).total_seconds()

    def _validate_runtime_energy(self, new_runtime: MidboxRuntimeData) -> bool:
        """Validate lifetime and daily energy in a new runtime read.

        Checks lifetime monotonicity first, then daily bounds.  Both must
        pass for the new data to be accepted.

        Args:
            new_runtime: Freshly-read MidboxRuntimeData to validate.

        Returns:
            True if the data should be accepted, False if it should be
            rejected (caller keeps cached data).
        """
        if self._transport_runtime is not None and not self._is_energy_valid(
            self._transport_runtime.lifetime_energy_values(),
            new_runtime.lifetime_energy_values(),
        ):
            return False
        prev_daily = (
            self._transport_runtime.daily_energy_values()
            if self._transport_runtime is not None
            else None
        )
        return self._is_daily_energy_valid(
            new_runtime.daily_energy_values(),
            prev_daily,
            self._runtime_elapsed_seconds(),
        )

    async def refresh(self) -> None:
        """Refresh MID device runtime data from API or transport.

        Uses transport if available, otherwise falls back to HTTP API.
        Transport data is stored directly in ``_transport_runtime`` as a
        pre-scaled ``MidboxRuntimeData`` dataclass — no conversion needed.
        """
        try:
            if self._transport is not None and hasattr(self._transport, "read_midbox_runtime"):
                read_midbox = self._transport.read_midbox_runtime
                runtime_data = await read_midbox()
                if self.validate_data and runtime_data.is_corrupt(
                    max_power_watts=self._max_power_watts,
                ):
                    _LOGGER.warning(
                        "Corrupt MID runtime for %s, keeping cached",
                        self.serial_number,
                    )
                    return
                if not self._validate_runtime_energy(runtime_data):
                    return  # keep cached runtime
                now = datetime.now()
                self._transport_runtime = runtime_data
                self._runtime_cache_time = now
                self._last_refresh = now
                _LOGGER.debug(
                    "Refreshed MID device %s via transport",
                    self.serial_number,
                )
            elif self._client is not None:
                from pylxpweb.transports.data import MidboxRuntimeData

                self._runtime = await self._client.api.devices.get_midbox_runtime(
                    self.serial_number
                )
                new_runtime = MidboxRuntimeData.from_http_response(self._runtime.midboxData)
                # Extract isOffGrid from deviceData (primary inverter's data)
                if self._runtime.deviceData is not None:
                    new_runtime.off_grid = self._runtime.deviceData.isOffGrid
                if not self._validate_runtime_energy(new_runtime):
                    return  # keep cached runtime
                now = datetime.now()
                self._transport_runtime = new_runtime
                self._runtime_cache_time = now
                self._last_refresh = now
            else:
                _LOGGER.warning(
                    "No transport or client available for MID device %s",
                    self.serial_number,
                )
        except Exception as err:
            _LOGGER.warning(
                "Failed to fetch MID device runtime for %s: %s",
                self.serial_number,
                err,
            )

    # All properties are provided by MIDRuntimePropertiesMixin

    # ============================================================================
    # Smart Port Controls
    # ============================================================================

    async def set_smart_port_mode(self, port: int, mode: int) -> bool:
        """Set a smart port mode.

        Args:
            port: Smart port number (1-4)
            mode: Port mode (0=Off, 1=Smart Load, 2=AC Couple)

        Returns:
            True if successful
        """
        result = await self._client.api.control.set_smart_port_mode(self.serial_number, port, mode)
        return result.success

    async def enable_smart_load(self, port: int) -> bool:
        """Enable a smart load on the specified port.

        Args:
            port: Smart port number (1-4)

        Returns:
            True if successful
        """
        result = await self._client.api.control.enable_smart_load(self.serial_number, port)
        return result.success

    async def disable_smart_load(self, port: int) -> bool:
        """Disable a smart load on the specified port.

        Args:
            port: Smart port number (1-4)

        Returns:
            True if successful
        """
        result = await self._client.api.control.disable_smart_load(self.serial_number, port)
        return result.success

    async def enable_ac_couple(self, port: int) -> bool:
        """Enable AC coupling on the specified port.

        Args:
            port: Smart port number (1-4)

        Returns:
            True if successful
        """
        result = await self._client.api.control.enable_ac_couple(self.serial_number, port)
        return result.success

    async def disable_ac_couple(self, port: int) -> bool:
        """Disable AC coupling on the specified port.

        Args:
            port: Smart port number (1-4)

        Returns:
            True if successful
        """
        result = await self._client.api.control.disable_ac_couple(self.serial_number, port)
        return result.success

    async def set_smart_load_start_soc(self, port: int, percent: int) -> bool:
        """Set the Smart Load start SOC threshold for a smart port.

        Args:
            port: Smart port number (1-4)
            percent: SOC percentage threshold (0-100)

        Returns:
            True if successful
        """
        result = await self._client.api.control.set_smart_load_start_soc(
            self.serial_number, port, percent
        )
        return result.success

    async def set_smart_load_end_soc(self, port: int, percent: int) -> bool:
        """Set the Smart Load end SOC threshold for a smart port.

        Args:
            port: Smart port number (1-4)
            percent: SOC percentage threshold (0-100)

        Returns:
            True if successful
        """
        result = await self._client.api.control.set_smart_load_end_soc(
            self.serial_number, port, percent
        )
        return result.success

    async def set_ac_couple_start_soc(self, port: int, percent: int) -> bool:
        """Set the AC Couple start SOC threshold for a smart port.

        Args:
            port: Smart port number (1-4)
            percent: SOC percentage threshold (0-100)

        Returns:
            True if successful
        """
        result = await self._client.api.control.set_ac_couple_start_soc(
            self.serial_number, port, percent
        )
        return result.success

    async def set_ac_couple_end_soc(self, port: int, percent: int) -> bool:
        """Set the AC Couple end SOC threshold for a smart port.

        Args:
            port: Smart port number (1-4)
            percent: SOC percentage threshold (0-100)

        Returns:
            True if successful
        """
        result = await self._client.api.control.set_ac_couple_end_soc(
            self.serial_number, port, percent
        )
        return result.success

    async def set_smart_load_grid_on(self, port: int, enable: bool) -> bool:
        """Set whether a smart load stays powered when grid is available.

        Args:
            port: Smart port number (1-4)
            enable: True to keep load on when grid is up

        Returns:
            True if successful
        """
        result = await self._client.api.control.set_smart_load_grid_on(
            self.serial_number, port, enable
        )
        return result.success

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
