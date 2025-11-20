"""Station (Plant) class for solar installations.

This module provides the Station class that represents a complete solar
installation with inverters, batteries, and optional MID devices.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

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
            if hasattr(inverter, "batteries") and inverter.batteries:
                # Handle both list and async property
                if isinstance(inverter.batteries, list):
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
            if hasattr(group, "mid_device") and group.mid_device:
                if hasattr(group.mid_device, "refresh"):
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
            if hasattr(inverter, "needs_refresh") and inverter.needs_refresh:
                if hasattr(inverter, "refresh"):
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
