"""Plant/Station endpoints for the Luxpower API.

This module provides plant/station functionality including:
- Plant discovery and listing
- Plant configuration management
- Daylight Saving Time control
- Plant overview with real-time metrics
- Inverter overview across plants
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pylxpweb.endpoints.base import BaseEndpoint
from pylxpweb.models import PlantListResponse

if TYPE_CHECKING:
    from pylxpweb.client import LuxpowerClient

_LOGGER = logging.getLogger(__name__)


class PlantEndpoints(BaseEndpoint):
    """Plant/Station endpoints for discovery, configuration, and overview."""

    def __init__(self, client: LuxpowerClient) -> None:
        """Initialize plant endpoints.

        Args:
            client: The parent LuxpowerClient instance
        """
        super().__init__(client)

    async def get_plants(
        self,
        *,
        sort: str = "createDate",
        order: str = "desc",
        search_text: str = "",
        page: int = 1,
        rows: int = 20,
    ) -> PlantListResponse:
        """Get list of available plants/stations.

        Args:
            sort: Sort field (default: createDate)
            order: Sort order (asc/desc, default: desc)
            search_text: Search filter text
            page: Page number for pagination
            rows: Number of rows per page

        Returns:
            PlantListResponse: List of plants with metadata

        Example:
            plants = await client.plants.get_plants()
            for plant in plants.rows:
                print(f"Plant: {plant.name}, ID: {plant.plantId}")
        """
        await self.client._ensure_authenticated()

        data = {
            "sort": sort,
            "order": order,
            "searchText": search_text,
            "page": page,
            "rows": rows,
        }

        response = await self.client._request(
            "POST", "/WManage/web/config/plant/list/viewer", data=data
        )
        return PlantListResponse.model_validate(response)

    async def get_plant_details(self, plant_id: int | str) -> dict[str, Any]:
        """Get detailed plant/station configuration information.

        Args:
            plant_id: The plant/station ID

        Returns:
            Dict containing plant configuration including:
                - plantId: Plant identifier
                - name: Station name
                - nominalPower: Solar PV power rating (W)
                - timezone: Timezone string (e.g., "GMT -8")
                - currentTimezoneWithMinute: Timezone offset in minutes
                - daylightSavingTime: DST enabled (boolean)
                - country: Country name
                - createDate: Plant creation date
                - address: Physical address

            Note: Latitude and longitude coordinates are NOT included in the API response.

        Raises:
            LuxpowerAPIError: If plant not found or API error occurs

        Example:
            details = await client.plants.get_plant_details("12345")
            print(f"Plant: {details['name']}")
            print(f"Timezone: {details['timezone']}")
            print(f"DST Enabled: {details['daylightSavingTime']}")
        """
        await self.client._ensure_authenticated()

        data = {
            "page": 1,
            "rows": 20,
            "searchText": "",
            "targetPlantId": str(plant_id),
            "sort": "createDate",
            "order": "desc",
        }

        response = await self.client._request(
            "POST", "/WManage/web/config/plant/list/viewer", data=data
        )

        if isinstance(response, dict) and response.get("rows"):
            from logging import getLogger

            plant_data = response["rows"][0]
            getLogger(__name__).debug(
                "Retrieved plant details for plant %s: %s",
                plant_id,
                plant_data.get("name"),
            )
            return dict(plant_data)

        from pylxpweb.exceptions import LuxpowerAPIError

        raise LuxpowerAPIError(f"Plant {plant_id} not found in API response")

    async def _fetch_country_location_from_api(self, country_human: str) -> tuple[str, str]:
        """Fetch continent and region for a country from locale API.

        This is the fallback method when country is not in static mapping.
        Queries the locale API to discover the continent and region dynamically.

        Args:
            country_human: Human-readable country name from API

        Returns:
            Tuple of (continent_enum, region_enum)

        Raises:
            LuxpowerAPIError: If country cannot be found in locale API
        """
        import json

        _LOGGER.debug(
            "Country '%s' not in static mapping, fetching from locale API",
            country_human,
        )

        # Get all continents from constants
        from pylxpweb.constants import CONTINENT_MAP

        session = await self.client._get_session()

        # Search through all continents and regions
        for continent_enum in CONTINENT_MAP.values():
            # Get regions for this continent
            async with session.post(
                f"{self.client.base_url}/WManage/locale/region",
                data=f"continent={continent_enum}",
                headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            ) as resp:
                if resp.status != 200:
                    continue
                regions_text = await resp.text()
                regions = json.loads(regions_text)

            # Check each region for our country
            for region in regions:
                region_value = region["value"]

                async with session.post(
                    f"{self.client.base_url}/WManage/locale/country",
                    data=f"region={region_value}",
                    headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
                ) as resp:
                    if resp.status != 200:
                        continue
                    countries_text = await resp.text()
                    countries = json.loads(countries_text)

                # Check if our country is in this region
                for country in countries:
                    if country["text"] == country_human:
                        _LOGGER.debug(
                            "Found country '%s' in locale API: continent=%s, region=%s",
                            country_human,
                            continent_enum,
                            region_value,
                        )
                        return (continent_enum, region_value)

        # Country not found anywhere
        from pylxpweb.exceptions import LuxpowerAPIError

        raise LuxpowerAPIError(
            f"Country '{country_human}' not found in locale API. "
            "This country may not be supported by the Luxpower platform."
        )

    async def _prepare_plant_update_data(
        self, plant_details: dict[str, Any], **overrides: Any
    ) -> dict[str, Any]:
        """Prepare data for plant configuration update POST request.

        Converts API response values to the enum format required by the POST endpoint.
        Uses hybrid approach: static mapping for common countries (fast), dynamic
        fetching from locale API for unknown countries (comprehensive).

        Args:
            plant_details: Plant details from get_plant_details()
            **overrides: Fields to override (e.g., daylightSavingTime=True)

        Returns:
            Dictionary ready for POST to /WManage/web/config/plant/edit

        Raises:
            ValueError: If unable to map required fields
            LuxpowerAPIError: If dynamic fetch fails
        """
        from pylxpweb.constants import (
            COUNTRY_MAP,
            TIMEZONE_MAP,
            get_continent_region_from_country,
        )

        # Required fields for POST
        data: dict[str, Any] = {
            "plantId": str(plant_details["plantId"]),
            "name": plant_details["name"],
            "createDate": plant_details["createDate"],
            "daylightSavingTime": plant_details["daylightSavingTime"],
        }

        # Map timezone: "GMT -8" → "WEST8"
        timezone_human = plant_details["timezone"]
        if timezone_human not in TIMEZONE_MAP:
            raise ValueError(f"Unknown timezone: {timezone_human}")
        data["timezone"] = TIMEZONE_MAP[timezone_human]

        # Map country: "United States of America" → "UNITED_STATES_OF_AMERICA"
        country_human = plant_details["country"]
        if country_human not in COUNTRY_MAP:
            raise ValueError(f"Unknown country: {country_human}")
        data["country"] = COUNTRY_MAP[country_human]

        # Hybrid approach: Try static mapping first, fall back to dynamic fetch
        try:
            # Fast path: static mapping
            continent_enum, region_enum = get_continent_region_from_country(country_human)
            _LOGGER.debug(
                "Used static mapping for country '%s': %s/%s",
                country_human,
                continent_enum,
                region_enum,
            )
        except ValueError:
            # Slow path: dynamic fetch from locale API
            _LOGGER.debug(
                "Country '%s' not in static mapping, fetching from locale API",
                country_human,
            )
            continent_enum, region_enum = await self._fetch_country_location_from_api(country_human)

        data["continent"] = continent_enum
        data["region"] = region_enum

        # Include nominalPower if present and not blank
        if plant_details.get("nominalPower"):
            data["nominalPower"] = plant_details["nominalPower"]

        # Apply any overrides
        data.update(overrides)

        _LOGGER.debug(
            "Prepared plant update data for plant %s: timezone=%s, country=%s, "
            "continent=%s, region=%s, dst=%s",
            plant_details["plantId"],
            data["timezone"],
            data["country"],
            data["continent"],
            data["region"],
            data["daylightSavingTime"],
        )

        return data

    async def update_plant_config(self, plant_id: int | str, **kwargs: Any) -> dict[str, Any]:
        """Update plant/station configuration.

        Uses API-only data with mapping tables to convert human-readable values
        to the enum format required by the POST endpoint. No HTML parsing needed.

        Args:
            plant_id: The plant/station ID
            **kwargs: Configuration parameters to update:
                - name (str): Station name
                - nominalPower (int): Solar PV power rating in Watts
                - daylightSavingTime (bool): DST enabled

        Returns:
            Dict containing API response (success status and message)

        Raises:
            LuxpowerAPIError: If update fails or validation error occurs
            ValueError: If unable to map timezone or country values

        Example:
            # Toggle DST
            await client.plants.update_plant_config(
                "12345",
                daylightSavingTime=True
            )

            # Update power rating
            await client.plants.update_plant_config(
                "12345",
                nominalPower=20000
            )
        """
        from logging import getLogger

        _LOGGER = getLogger(__name__)
        await self.client._ensure_authenticated()

        # Get current configuration from API (human-readable values)
        _LOGGER.debug("Fetching plant details for plant %s", plant_id)
        plant_details = await self.get_plant_details(plant_id)

        # Prepare POST data using hybrid approach (static + dynamic mapping)
        data = await self._prepare_plant_update_data(plant_details, **kwargs)

        _LOGGER.debug(
            "Updating plant %s configuration: %s",
            plant_id,
            dict(kwargs),
        )

        response = await self.client._request("POST", "/WManage/web/config/plant/edit", data=data)

        _LOGGER.debug("Plant %s configuration updated successfully", plant_id)
        return response

    async def set_daylight_saving_time(self, plant_id: int | str, enabled: bool) -> dict[str, Any]:
        """Set Daylight Saving Time (DST) for a plant/station.

        Convenience method for toggling DST without affecting other settings.

        Args:
            plant_id: The plant/station ID
            enabled: True to enable DST, False to disable

        Returns:
            Dict containing API response

        Raises:
            LuxpowerAPIError: If update fails

        Example:
            # Enable DST
            await client.plants.set_daylight_saving_time("12345", True)

            # Disable DST
            await client.plants.set_daylight_saving_time("12345", False)
        """
        from logging import getLogger

        _LOGGER = getLogger(__name__)
        _LOGGER.debug(
            "Setting Daylight Saving Time to %s for plant %s",
            "enabled" if enabled else "disabled",
            plant_id,
        )
        return await self.update_plant_config(plant_id, daylightSavingTime=enabled)

    async def get_plant_overview(self, search_text: str = "") -> dict[str, Any]:
        """Get plant overview with real-time metrics.

        This endpoint provides plant-level aggregated data including:
        - Real-time power metrics (PV, charge, discharge, consumption)
        - Energy totals (today, total)
        - Inverter details nested within plant data

        Args:
            search_text: Optional search filter for plant name/address

        Returns:
            Dict containing:
                - total: Total number of plants matching filter
                - rows: List of plant objects with real-time metrics

        Example:
            overview = await client.plants.get_plant_overview()
            for plant in overview["rows"]:
                print(f"{plant['name']}: {plant['ppv']}W PV")
        """
        data = {"searchText": search_text}

        response = await self.client._request(
            "POST",
            "/WManage/api/plantOverview/list/viewer",
            data=data,
        )

        return dict(response)

    async def get_inverter_overview(
        self,
        page: int = 1,
        rows: int = 30,
        plant_id: int = -1,
        search_text: str = "",
        status_filter: str = "all",
    ) -> dict[str, Any]:
        """Get paginated list of all inverters with real-time metrics.

        This endpoint provides per-inverter data across all plants or filtered
        by specific plant. Unlike get_plant_overview which aggregates at plant
        level, this shows individual inverter metrics.

        Args:
            page: Page number (1-indexed)
            rows: Number of rows per page (default 30)
            plant_id: Plant ID (-1 for all plants, or specific plant ID)
            search_text: Search filter for serial number or device name
            status_filter: Status filter ("all", "normal", "fault", "offline")

        Returns:
            Dict containing:
                - success: Boolean indicating success
                - total: Total number of inverters matching filter
                - rows: List of inverter objects with metrics

        Example:
            # All inverters across all plants
            overview = await client.plants.get_inverter_overview()

            # Inverters for specific plant
            overview = await client.plants.get_inverter_overview(plant_id=19147)

            # Only faulted inverters
            overview = await client.plants.get_inverter_overview(status_filter="fault")
        """
        data = {
            "page": page,
            "rows": rows,
            "plantId": plant_id,
            "searchText": search_text,
            "statusText": status_filter,
        }

        response = await self.client._request(
            "POST",
            "/WManage/api/inverterOverview/list",
            data=data,
        )

        return dict(response)
