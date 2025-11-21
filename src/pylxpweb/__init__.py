"""Python client library for Luxpower/EG4 inverter web monitoring API.

Usage:
    Basic client usage:
        from pylxpweb import LuxpowerClient

        async with LuxpowerClient(username, password) as client:
            # Use low-level API endpoints
            plants = await client.api.plants.get_plants()

    High-level device hierarchy:
        from pylxpweb import LuxpowerClient
        from pylxpweb.devices import Station

        async with LuxpowerClient(username, password) as client:
            # Load stations with auto-discovery
            stations = await Station.load_all(client)
            for station in stations:
                for inverter in station.all_inverters:
                    await inverter.refresh()
"""

from __future__ import annotations

from .client import LuxpowerClient
from .endpoints import (
    AnalyticsEndpoints,
    ControlEndpoints,
    DeviceEndpoints,
    ExportEndpoints,
    FirmwareEndpoints,
    ForecastingEndpoints,
    PlantEndpoints,
)
from .exceptions import (
    LuxpowerAPIError,
    LuxpowerAuthError,
    LuxpowerConnectionError,
    LuxpowerDeviceError,
    LuxpowerError,
)
from .models import OperatingMode

__version__ = "0.2.6"
__all__ = [
    "LuxpowerClient",
    "LuxpowerError",
    "LuxpowerAPIError",
    "LuxpowerAuthError",
    "LuxpowerConnectionError",
    "LuxpowerDeviceError",
    # Endpoint modules
    "PlantEndpoints",
    "DeviceEndpoints",
    "ControlEndpoints",
    "AnalyticsEndpoints",
    "ForecastingEndpoints",
    "ExportEndpoints",
    "FirmwareEndpoints",
    # Enums
    "OperatingMode",
]
