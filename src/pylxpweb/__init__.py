"""Python client library for Luxpower/EG4 inverter web monitoring API."""

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

__version__ = "0.2.2"
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
]
