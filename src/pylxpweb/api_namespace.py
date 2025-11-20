"""API Namespace for Luxpower/EG4 Client.

This module provides the APINamespace class that organizes all API endpoint
access under the `client.api.*` namespace for cleaner API design.

Design Rationale:
- Separates direct API calls (client.api.*) from high-level objects (client.get_station())
- Makes it clear when you're making raw API calls vs using object interface
- Prevents confusion between endpoint methods and object methods
- Follows best practices from similar libraries (requests.api, etc.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
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


class APINamespace:
    """Namespace for all API endpoint access.

    This class provides access to all API endpoint groups through the
    `client.api.*` interface, creating a clear separation between:
    - Low-level API calls: `client.api.plants.get_plants()`
    - High-level object interface: `client.get_station(plant_id)`

    Example:
        ```python
        async with LuxpowerClient(username, password) as client:
            # Low-level API access
            plants = await client.api.plants.get_plants()
            runtime = await client.api.devices.get_inverter_runtime(serial)

            # High-level object interface
            station = await client.get_station(plant_id)
            await station.refresh_all_data()
        ```
    """

    def __init__(self, client: LuxpowerClient) -> None:
        """Initialize the API namespace.

        Args:
            client: The LuxpowerClient instance that owns this namespace.
        """
        self._client = client

        # Endpoint modules (lazy-loaded via properties)
        self._plants: PlantEndpoints | None = None
        self._devices: DeviceEndpoints | None = None
        self._control: ControlEndpoints | None = None
        self._analytics: AnalyticsEndpoints | None = None
        self._forecasting: ForecastingEndpoints | None = None
        self._export: ExportEndpoints | None = None
        self._firmware: FirmwareEndpoints | None = None

    @property
    def plants(self) -> PlantEndpoints:
        """Access plant/station management endpoints.

        Provides methods for:
        - Listing stations/plants
        - Getting plant details
        - Managing plant configuration

        Returns:
            PlantEndpoints: The plant endpoints instance.

        Example:
            ```python
            plants = await client.api.plants.get_plants()
            details = await client.api.plants.get_plant_details(plant_id)
            ```
        """
        if self._plants is None:
            from .endpoints import PlantEndpoints

            self._plants = PlantEndpoints(self._client)
        return self._plants

    @property
    def devices(self) -> DeviceEndpoints:
        """Access device discovery and runtime data endpoints.

        Provides methods for:
        - Device enumeration
        - Inverter runtime data
        - Battery information
        - MID/GridBOSS data
        - Parallel group details

        Returns:
            DeviceEndpoints: The device endpoints instance.

        Example:
            ```python
            devices = await client.api.devices.get_devices(plant_id)
            runtime = await client.api.devices.get_inverter_runtime(serial)
            battery = await client.api.devices.get_battery_info(serial)
            ```
        """
        if self._devices is None:
            from .endpoints import DeviceEndpoints

            self._devices = DeviceEndpoints(self._client)
        return self._devices

    @property
    def control(self) -> ControlEndpoints:
        """Access parameter control and device function endpoints.

        Provides methods for:
        - Parameter read/write
        - Quick charge control
        - EPS mode control
        - Operating mode changes
        - SOC limits

        Returns:
            ControlEndpoints: The control endpoints instance.

        Example:
            ```python
            await client.api.control.start_quick_charge(serial)
            await client.api.control.write_parameter(serial, param_id, value)
            params = await client.api.control.read_parameters(serial, [param_ids])
            ```
        """
        if self._control is None:
            from .endpoints import ControlEndpoints

            self._control = ControlEndpoints(self._client)
        return self._control

    @property
    def analytics(self) -> AnalyticsEndpoints:
        """Access analytics, charts, and event log endpoints.

        Provides methods for:
        - Energy charts
        - Production statistics
        - Event logs
        - Historical data

        Returns:
            AnalyticsEndpoints: The analytics endpoints instance.

        Example:
            ```python
            chart = await client.api.analytics.get_energy_chart(plant_id, date_range)
            events = await client.api.analytics.get_event_logs(plant_id)
            ```
        """
        if self._analytics is None:
            from .endpoints import AnalyticsEndpoints

            self._analytics = AnalyticsEndpoints(self._client)
        return self._analytics

    @property
    def forecasting(self) -> ForecastingEndpoints:
        """Access weather and solar forecasting endpoints.

        Provides methods for:
        - Weather forecasts
        - Solar production forecasts
        - Irradiance data

        Returns:
            ForecastingEndpoints: The forecasting endpoints instance.

        Example:
            ```python
            weather = await client.api.forecasting.get_weather(plant_id)
            forecast = await client.api.forecasting.get_solar_forecast(plant_id)
            ```
        """
        if self._forecasting is None:
            from .endpoints import ForecastingEndpoints

            self._forecasting = ForecastingEndpoints(self._client)
        return self._forecasting

    @property
    def export(self) -> ExportEndpoints:
        """Access data export endpoints.

        Provides methods for:
        - Excel export
        - CSV export
        - Report generation

        Returns:
            ExportEndpoints: The export endpoints instance.

        Example:
            ```python
            excel_data = await client.api.export.export_to_excel(plant_id, date_range)
            csv_data = await client.api.export.export_to_csv(plant_id, date_range)
            ```
        """
        if self._export is None:
            from .endpoints import ExportEndpoints

            self._export = ExportEndpoints(self._client)
        return self._export

    @property
    def firmware(self) -> FirmwareEndpoints:
        """Access firmware management endpoints.

        Provides methods for:
        - Firmware version checking
        - Firmware updates
        - Update status

        Returns:
            FirmwareEndpoints: The firmware endpoints instance.

        Example:
            ```python
            version = await client.api.firmware.get_version(serial)
            await client.api.firmware.start_update(serial, version)
            ```
        """
        if self._firmware is None:
            from .endpoints import FirmwareEndpoints

            self._firmware = FirmwareEndpoints(self._client)
        return self._firmware
