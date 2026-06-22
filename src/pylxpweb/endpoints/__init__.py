"""Endpoint-specific modules for the Luxpower API client.

This package organizes API endpoints into logical modules following the strategy pattern.
Each module handles a specific category of endpoints (analytics, plants, devices, etc.).
"""

from __future__ import annotations

from pylxpweb.endpoints.analytics import AnalyticsEndpoints
from pylxpweb.endpoints.base import BaseEndpoint
from pylxpweb.endpoints.control import ControlEndpoints
from pylxpweb.endpoints.devices import DeviceEndpoints
from pylxpweb.endpoints.export import ExportDaySheet, ExportEndpoints, parse_export
from pylxpweb.endpoints.firmware import FirmwareEndpoints
from pylxpweb.endpoints.forecasting import ForecastingEndpoints
from pylxpweb.endpoints.plants import PlantEndpoints

__all__ = [
    "BaseEndpoint",
    "PlantEndpoints",
    "DeviceEndpoints",
    "ControlEndpoints",
    "AnalyticsEndpoints",
    "ExportEndpoints",
    "ExportDaySheet",
    "parse_export",
    "ForecastingEndpoints",
    "FirmwareEndpoints",
]
