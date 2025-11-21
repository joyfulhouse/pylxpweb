"""ParallelGroup class for inverters in parallel operation.

This module provides the ParallelGroup class that represents a group of
inverters operating in parallel, optionally with a MID (GridBOSS) device.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient

    from .station import Station


class ParallelGroup:
    """Represents a group of inverters operating in parallel.

    In the Luxpower/EG4 system, multiple inverters can operate in parallel
    to increase total power capacity. The parallel group may include:
    - Multiple inverters (2 or more)
    - Optional MID device (GridBOSS) for grid management

    Example:
        ```python
        # Access parallel groups from station
        station = await client.get_station(plant_id)

        for group in station.parallel_groups:
            print(f"Group {group.name}: {len(group.inverters)} inverters")

            if group.mid_device:
                print(f"  GridBOSS: {group.mid_device.serial_number}")

            for inverter in group.inverters:
                await inverter.refresh()
                print(f"  Inverter {inverter.serial_number}: {inverter.runtime.pac}W")
        ```
    """

    def __init__(
        self,
        client: LuxpowerClient,
        station: Station,
        name: str,
        first_device_serial: str,
    ) -> None:
        """Initialize parallel group.

        Args:
            client: LuxpowerClient instance for API access
            station: Parent station object
            name: Group identifier (typically "A", "B", etc.)
            first_device_serial: Serial number of first device in group
        """
        self._client = client
        self.station = station
        self.name = name
        self.first_device_serial = first_device_serial

        # Device collections (loaded by factory methods)
        self.inverters: list[Any] = []  # Will be BaseInverter objects
        self.mid_device: Any | None = None  # Will be MIDDevice object if present

    async def refresh(self) -> None:
        """Refresh runtime data for all devices in group.

        This refreshes:
        - All inverters in the group
        - MID device if present
        """
        import asyncio

        tasks = []

        # Refresh all inverters
        for inverter in self.inverters:
            if hasattr(inverter, "refresh"):
                tasks.append(inverter.refresh())

        # Refresh MID device
        if self.mid_device and hasattr(self.mid_device, "refresh"):
            tasks.append(self.mid_device.refresh())

        # Execute concurrently
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def get_combined_energy(self) -> dict[str, float]:
        """Get combined energy statistics for all inverters in group.

        Returns:
            Dictionary with 'today_kwh' and 'lifetime_kwh' totals.
        """
        total_today = 0.0
        total_lifetime = 0.0

        for inverter in self.inverters:
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

    @classmethod
    async def from_api_data(
        cls,
        client: LuxpowerClient,
        station: Station,
        group_data: dict[str, Any],
    ) -> ParallelGroup:
        """Factory method to create ParallelGroup from API data.

        Args:
            client: LuxpowerClient instance
            station: Parent station object
            group_data: API response data for parallel group

        Returns:
            ParallelGroup instance with devices loaded.
        """
        # Extract group info
        name = group_data.get("parallelGroup", "A")
        first_serial = group_data.get("parallelFirstDeviceSn", "")

        # Create group
        group = cls(
            client=client,
            station=station,
            name=name,
            first_device_serial=first_serial,
        )

        # Note: Inverters and MID device will be loaded by Station._load_devices()
        # This is because device creation requires model-specific inverter classes
        # which will be implemented in Phase 2

        return group
