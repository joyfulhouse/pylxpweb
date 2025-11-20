"""MID Device (GridBOSS) module for grid management and load control.

This module provides the MIDDevice class for GridBOSS devices that handle
grid interconnection, UPS functionality, smart loads, and AC coupling.

Note: This is a simplified implementation. Full GridBOSS support will be
added in a future release with comprehensive smart load and AC coupling features.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BaseDevice
from .models import DeviceInfo, Entity

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient


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
        ```

    Note: This is a stub implementation. Full GridBOSS support including
    smart loads, AC coupling, and generator monitoring will be added in
    a future release.
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

        # Runtime data will be stored here
        self.runtime: dict | None = None

    async def refresh(self) -> None:
        """Refresh MID device runtime data from API.

        Note: This is a stub implementation. Full implementation will
        fetch midbox runtime data and parse all metrics.
        """
        # TODO: Implement midbox runtime data fetching
        # runtime_data = await self._client.api.devices.get_midbox_runtime(self.serial_number)
        # self.runtime = runtime_data
        pass

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
        )

    def to_entities(self) -> list[Entity]:
        """Generate entities for this MID device.

        Returns:
            List of Entity objects (empty in stub implementation).

        Note: Full implementation will return 50+ entities for:
        - Grid voltage/current/power (L1/L2)
        - UPS voltage/current/power (L1/L2)
        - Generator monitoring (L1/L2)
        - Smart load 1-4 monitoring
        - AC couple 1-4 monitoring
        - Energy meters (today/lifetime)
        """
        # TODO: Implement full entity generation
        return []
