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

    DST auto-correction (optional):
        from pylxpweb import LuxpowerClient
        from pylxpweb.devices import Station

        # Configure with IANA timezone for DST detection
        async with LuxpowerClient(
            username,
            password,
            iana_timezone="America/Los_Angeles"
        ) as client:
            station = await Station.load(client, plant_id)

            # Optionally sync DST setting (convenience method)
            # This does NOT run automatically - you must call it explicitly
            if user_wants_dst_sync:
                await station.sync_dst_setting()
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
    LuxpowerDeviceOfflineError,
    LuxpowerError,
)
from .models import (
    DatalogListItem,
    DatalogListResponse,
    DongleStatus,
    FirmwareUpdateInfo,
    OperatingMode,
)

__version__ = "0.6.5"
__all__ = [
    "LuxpowerClient",
    "LuxpowerError",
    "LuxpowerAPIError",
    "LuxpowerAuthError",
    "LuxpowerConnectionError",
    "LuxpowerDeviceError",
    "LuxpowerDeviceOfflineError",
    # Endpoint modules
    "PlantEndpoints",
    "DeviceEndpoints",
    "ControlEndpoints",
    "AnalyticsEndpoints",
    "ForecastingEndpoints",
    "ExportEndpoints",
    "FirmwareEndpoints",
    # Models
    "DatalogListItem",
    "DatalogListResponse",
    "DongleStatus",
    "FirmwareUpdateInfo",
    # Enums
    "OperatingMode",
]
