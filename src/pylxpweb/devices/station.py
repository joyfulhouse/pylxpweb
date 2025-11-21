"""Station (Plant) class for solar installations.

This module provides the Station class that represents a complete solar
installation with inverters, batteries, and optional MID devices.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pylxpweb.models import InverterOverviewItem, ParallelGroupDeviceItem

from .base import BaseDevice
from .models import DeviceInfo, Entity

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient


@dataclass
class Location:
    """Geographic location information.

    Attributes:
        address: Street address
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        country: Country name or code
    """

    address: str
    latitude: float
    longitude: float
    country: str


class Station(BaseDevice):
    """Represents a complete solar installation.

    A single user account can have multiple stations (e.g., home, cabin, rental).
    Each station is independent with its own device hierarchy.

    The station manages:
    - Parallel groups (if multi-inverter parallel operation)
    - Standalone inverters (not in parallel groups)
    - Weather data (optional)
    - Aggregate statistics across all devices

    Example:
        ```python
        # Load a station
        station = await Station.load(client, plant_id=12345)

        # Access devices
        print(f"Total inverters: {len(station.all_inverters)}")
        print(f"Total batteries: {len(station.all_batteries)}")

        # Refresh all data
        await station.refresh_all_data()

        # Get production stats
        stats = await station.get_total_production()
        print(f"Today: {stats.today_kwh} kWh")
        ```
    """

    def __init__(
        self,
        client: LuxpowerClient,
        plant_id: int,
        name: str,
        location: Location,
        timezone: str,
        created_date: datetime,
    ) -> None:
        """Initialize station.

        Args:
            client: LuxpowerClient instance for API access
            plant_id: Unique plant/station identifier
            name: Human-readable station name
            location: Geographic location information
            timezone: Timezone string (e.g., "America/New_York")
            created_date: Station creation timestamp
        """
        # BaseDevice expects serial_number, but stations use plant_id
        # We'll use str(plant_id) as the "serial number" for consistency
        super().__init__(client, str(plant_id), "Solar Station")

        self.id = plant_id
        self.name = name
        self.location = location
        self.timezone = timezone
        self.created_date = created_date

        # Device collections (loaded by _load_devices)
        self.parallel_groups: list[Any] = []  # Will be ParallelGroup objects
        self.standalone_inverters: list[Any] = []  # Will be BaseInverter objects
        self.weather: Any | None = None  # Weather data (optional)

    @property
    def all_inverters(self) -> list[Any]:
        """Get all inverters (parallel + standalone).

        Returns:
            List of all inverter objects in this station.
        """
        inverters = []
        # Add inverters from parallel groups
        for group in self.parallel_groups:
            if hasattr(group, "inverters"):
                inverters.extend(group.inverters)
        # Add standalone inverters
        inverters.extend(self.standalone_inverters)
        return inverters

    @property
    def all_batteries(self) -> list[Any]:
        """Get all batteries from all inverters.

        Returns:
            List of all battery objects across all inverters.
        """
        batteries = []
        for inverter in self.all_inverters:
            if (
                hasattr(inverter, "batteries")
                and inverter.batteries
                and isinstance(inverter.batteries, list)
            ):
                batteries.extend(inverter.batteries)
        return batteries

    async def refresh(self) -> None:
        """Refresh station metadata.

        Note: This refreshes station-level data only.
        Use refresh_all_data() to refresh all devices.
        """
        # Station-level data doesn't change often, just update timestamp
        self._last_refresh = datetime.now()

    async def refresh_all_data(self) -> None:
        """Refresh runtime data for all devices concurrently.

        This method refreshes:
        - All inverters (runtime and energy data)
        - All MID devices
        - Does NOT reload device hierarchy (use load() for that)
        """
        import asyncio

        tasks = []

        # Refresh all inverters
        for inverter in self.all_inverters:
            if hasattr(inverter, "refresh"):
                tasks.append(inverter.refresh())

        # Refresh MID devices
        for group in self.parallel_groups:
            if (
                hasattr(group, "mid_device")
                and group.mid_device
                and hasattr(group.mid_device, "refresh")
            ):
                tasks.append(group.mid_device.refresh())

        # Execute concurrently, ignore exceptions (partial failure OK)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._last_refresh = datetime.now()

    async def get_total_production(self) -> dict[str, float]:
        """Calculate total energy production across all inverters.

        Returns:
            Dictionary with 'today_kwh' and 'lifetime_kwh' totals.
        """
        total_today = 0.0
        total_lifetime = 0.0

        for inverter in self.all_inverters:
            # Refresh if needed
            if (
                hasattr(inverter, "needs_refresh")
                and inverter.needs_refresh
                and hasattr(inverter, "refresh")
            ):
                await inverter.refresh()

            # Sum energy data
            if hasattr(inverter, "energy") and inverter.energy:
                total_today += getattr(inverter.energy, "eToday", 0.0)
                total_lifetime += getattr(inverter.energy, "eTotal", 0.0)

        return {
            "today_kwh": total_today,
            "lifetime_kwh": total_lifetime,
        }

    def to_device_info(self) -> DeviceInfo:
        """Convert to device info model.

        Returns:
            DeviceInfo with station metadata.
        """
        return DeviceInfo(
            identifiers={("pylxpweb", f"station_{self.id}")},
            name=f"Station: {self.name}",
            manufacturer="EG4/Luxpower",
            model="Solar Station",
        )

    def to_entities(self) -> list[Entity]:
        """Generate entities for station.

        Returns:
            List of station-level entities (aggregated metrics).
        """
        entities = []

        # Total production today
        entities.append(
            Entity(
                unique_id=f"station_{self.id}_total_production_today",
                name=f"{self.name} Total Production Today",
                device_class="energy",
                state_class="total_increasing",
                unit_of_measurement="kWh",
                value=0.0,  # Will be updated by data coordinator
            )
        )

        # Total power
        entities.append(
            Entity(
                unique_id=f"station_{self.id}_total_power",
                name=f"{self.name} Total Power",
                device_class="power",
                state_class="measurement",
                unit_of_measurement="W",
                value=0.0,  # Will be updated by data coordinator
            )
        )

        return entities

    @classmethod
    async def load(cls, client: LuxpowerClient, plant_id: int) -> Station:
        """Load a station from the API with all devices.

        Args:
            client: LuxpowerClient instance
            plant_id: Plant/station ID to load

        Returns:
            Station instance with device hierarchy loaded

        Example:
            ```python
            station = await Station.load(client, plant_id=12345)
            print(f"Loaded {len(station.all_inverters)} inverters")
            ```
        """
        from datetime import datetime

        # Get plant details from API
        plant_data = await client.api.plants.get_plant_details(plant_id)

        # Create Location from plant data
        location = Location(
            address=plant_data.get("address", ""),
            latitude=plant_data.get("lat", 0.0),
            longitude=plant_data.get("lng", 0.0),
            country=plant_data.get("country", ""),
        )

        # Parse creation date
        created_date_str = plant_data.get("createDate", "")
        try:
            created_date = datetime.fromisoformat(created_date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            created_date = datetime.now()

        # Create station instance
        station = cls(
            client=client,
            plant_id=plant_id,
            name=plant_data.get("name", f"Station {plant_id}"),
            location=location,
            timezone=plant_data.get("timezone", "UTC"),
            created_date=created_date,
        )

        # Load device hierarchy
        await station._load_devices()

        return station

    @classmethod
    async def load_all(cls, client: LuxpowerClient) -> list[Station]:
        """Load all stations accessible by the current user.

        Args:
            client: LuxpowerClient instance

        Returns:
            List of Station instances with device hierarchies loaded

        Example:
            ```python
            stations = await Station.load_all(client)
            for station in stations:
                print(f"{station.name}: {len(station.all_inverters)} inverters")
            ```
        """
        # Get all plants from API
        plants_response = await client.api.plants.get_plants()

        # Load each station concurrently
        import asyncio

        tasks = [cls.load(client, plant.plantId) for plant in plants_response.rows]
        return await asyncio.gather(*tasks)

    async def _load_devices(self) -> None:
        """Load device hierarchy from API.

        This method:
        1. Gets parallel group configuration
        2. Creates ParallelGroup objects
        3. Discovers inverters and assigns to groups or standalone list
        4. Discovers MID devices and assigns to parallel groups
        """
        from .inverters.generic import GenericInverter
        from .mid_device import MIDDevice
        from .parallel_group import ParallelGroup

        try:
            import logging

            _LOGGER = logging.getLogger(__name__)

            # Step 1: Get device list first
            devices_response = await self._client.api.devices.get_devices(self.id)

            # Step 2: Find GridBOSS/MID device (deviceType == 9) to query parallel groups
            gridboss_serial = None
            if hasattr(devices_response, "rows") and devices_response.rows:
                for device in devices_response.rows:
                    if device.deviceType == 9:  # GridBOSS/MID device
                        gridboss_serial = device.serialNum
                        _LOGGER.debug("Found GridBOSS device: %s", gridboss_serial)
                        break

            # Step 3: Query parallel group details if GridBOSS exists
            group_data = None
            if gridboss_serial:
                try:
                    group_data = await self._client.api.devices.get_parallel_group_details(
                        gridboss_serial
                    )
                except Exception as e:
                    _LOGGER.debug("Could not load parallel group details: %s", str(e))
                    group_data = None

            # Step 4: Create parallel groups from devices with parallelGroup field
            if group_data and hasattr(group_data, "devices") and group_data.devices:
                # Group devices by their parallelGroup field
                groups_by_name: dict[str, list[ParallelGroupDeviceItem]] = {}
                for pg_device in group_data.devices:
                    # Get parallel group name from device list (not from group_data)
                    device_info: InverterOverviewItem | None = next(
                        (d for d in devices_response.rows if d.serialNum == pg_device.serialNum),
                        None,
                    )
                    if device_info and device_info.parallelGroup:
                        group_name = device_info.parallelGroup
                        if group_name not in groups_by_name:
                            groups_by_name[group_name] = []
                        groups_by_name[group_name].append(pg_device)

                # Create ParallelGroup objects
                for group_name, devices in groups_by_name.items():
                    # Use first device serial as reference
                    first_serial = devices[0].serialNum if devices else ""
                    group = ParallelGroup(
                        client=self._client,
                        station=self,
                        name=group_name,
                        first_device_serial=first_serial,
                    )
                    self.parallel_groups.append(group)
                    _LOGGER.debug(
                        "Created parallel group '%s' with %d devices", group_name, len(devices)
                    )

            # Step 5: Process devices and assign to groups or standalone
            if (
                not isinstance(devices_response, BaseException)
                and hasattr(devices_response, "rows")
                and devices_response.rows
            ):
                for device_data in devices_response.rows:
                    serial_num = device_data.serialNum
                    device_type = device_data.deviceType
                    # Use deviceTypeText as the model name (e.g., "18KPV", "Grid Boss")
                    model_text = getattr(device_data, "deviceTypeText", "Unknown")

                    if not serial_num:
                        continue

                    # Get parallel group name
                    parallel_group_name = device_data.parallelGroup

                    # Handle GridBOSS/MID devices (deviceType 9)
                    if device_type == 9:
                        mid_device = MIDDevice(
                            client=self._client, serial_number=serial_num, model=model_text
                        )

                        # Assign MID device to parallel group
                        if parallel_group_name:
                            for group in self.parallel_groups:
                                if group.name == parallel_group_name:
                                    group.mid_device = mid_device
                                    _LOGGER.debug(
                                        "Assigned MID device %s to parallel group '%s'",
                                        serial_num,
                                        parallel_group_name,
                                    )
                                    break
                        else:
                            _LOGGER.warning(
                                "MID device %s has no parallel group assignment", serial_num
                            )
                        continue

                    # Create inverter object
                    inverter = GenericInverter(
                        client=self._client, serial_number=serial_num, model=model_text
                    )

                    # Assign inverter to parallel group or standalone
                    if parallel_group_name:
                        # Find matching parallel group
                        group_found = False
                        for group in self.parallel_groups:
                            if group.name == parallel_group_name:
                                group.inverters.append(inverter)
                                group_found = True
                                _LOGGER.debug(
                                    "Assigned inverter %s to parallel group '%s'",
                                    serial_num,
                                    parallel_group_name,
                                )
                                break

                        # If parallel group not found, treat as standalone
                        if not group_found:
                            self.standalone_inverters.append(inverter)
                            _LOGGER.debug(
                                "Parallel group '%s' not found for %s - treating as standalone",
                                parallel_group_name,
                                serial_num,
                            )
                    else:
                        # Standalone inverter
                        self.standalone_inverters.append(inverter)
                        _LOGGER.debug("Assigned inverter %s as standalone", serial_num)

        except Exception:
            # If device loading fails, log and continue
            # Station can still function with empty device lists
            import logging

            logging.getLogger(__name__).warning(
                "Failed to load devices for station %s", self.id, exc_info=True
            )
