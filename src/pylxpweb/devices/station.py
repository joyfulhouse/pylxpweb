"""Station (Plant) class for solar installations.

This module provides the Station class that represents a complete solar
installation with inverters, batteries, and optional MID devices.
"""

from __future__ import annotations

import logging
import zoneinfo
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from pylxpweb.models import InverterOverviewItem, ParallelGroupDeviceItem

from .base import BaseDevice
from .models import DeviceInfo, Entity

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient

    from .battery import Battery
    from .inverters.base import BaseInverter
    from .parallel_group import ParallelGroup


@dataclass
class Location:
    """Geographic location information.

    Attributes:
        address: Street address
        country: Country name or code

    Note:
        Latitude and longitude are not provided by the API.
    """

    address: str
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
        current_timezone_with_minute: int | None = None,
        daylight_saving_time: bool = False,
    ) -> None:
        """Initialize station.

        Args:
            client: LuxpowerClient instance for API access
            plant_id: Unique plant/station identifier
            name: Human-readable station name
            location: Geographic location information
            timezone: Timezone string (e.g., "GMT -8")
            created_date: Station creation timestamp
            current_timezone_with_minute: Timezone offset in HHMM format
                (e.g., -700 for PDT = -7:00)
            daylight_saving_time: DST flag from API (may be incorrect)
        """
        # BaseDevice expects serial_number, but stations use plant_id
        # We'll use str(plant_id) as the "serial number" for consistency
        super().__init__(client, str(plant_id), "Solar Station")

        self.id = plant_id
        self.name = name
        self.location = location
        self.timezone = timezone  # "GMT -8" (base timezone)
        self.created_date = created_date

        # Timezone precision fields
        self.current_timezone_with_minute = current_timezone_with_minute  # -700 = GMT-7:00 (PDT)
        self.daylight_saving_time = daylight_saving_time  # API's DST flag (may be wrong)

        # Computed DST status (based on offset analysis)
        self._actual_dst_active: bool | None = None

        # Device collections (loaded by _load_devices)
        self.parallel_groups: list[ParallelGroup] = []
        self.standalone_inverters: list[BaseInverter] = []
        self.weather: dict[str, Any] | None = None  # Weather data (optional)

    def detect_dst_status(self) -> bool | None:
        """Detect if DST should be currently active based on system time and timezone.

        This method uses Python's zoneinfo to determine if DST should be active
        at the current date/time for the station's timezone. This is necessary because
        the API's currentTimezoneWithMinute is not independent - it's calculated from
        the base timezone + DST flag, creating circular logic.

        IMPORTANT: This method requires an IANA timezone to be configured on the
        LuxpowerClient (via the iana_timezone parameter). The API does not provide
        sufficient location data to reliably determine the IANA timezone automatically.

        Returns:
            True if DST should be active, False if not, None if cannot determine
            (no IANA timezone configured or invalid timezone).

        Example:
            # Client configured with IANA timezone
            client = LuxpowerClient(username, password, iana_timezone="America/Los_Angeles")
            station = await Station.load(client, plant_id)
            dst_active = station.detect_dst_status()  # Returns True/False

            # Client without IANA timezone
            client = LuxpowerClient(username, password)
            station = await Station.load(client, plant_id)
            dst_active = station.detect_dst_status()  # Returns None (disabled)
        """
        try:
            # Check if IANA timezone is configured
            iana_timezone = getattr(self._client, "iana_timezone", None)
            if not iana_timezone:
                _LOGGER.debug(
                    "Station %s: DST detection disabled (no IANA timezone configured)",
                    self.id,
                )
                return None

            # Validate timezone string
            try:
                tz = zoneinfo.ZoneInfo(iana_timezone)
            except zoneinfo.ZoneInfoNotFoundError:
                _LOGGER.error(
                    "Station %s: Invalid IANA timezone '%s'",
                    self.id,
                    iana_timezone,
                )
                return None

            # Check if DST is active using zoneinfo
            now = datetime.now(tz)
            dst_offset = now.dst()
            dst_active = dst_offset is not None and dst_offset.total_seconds() > 0

            _LOGGER.debug(
                "Station %s: DST detected using %s: %s (offset: %s)",
                self.id,
                iana_timezone,
                "ACTIVE" if dst_active else "INACTIVE",
                now.strftime("%z"),
            )

            return dst_active

        except Exception as e:
            _LOGGER.debug("Station %s: Error detecting DST status: %s", self.id, e)
            return None

    async def sync_dst_setting(self) -> bool:
        """Convenience method to synchronize DST setting with API if mismatch detected.

        This is a convenience method that implementing applications can call to
        automatically correct the API's DST flag based on the configured IANA timezone.
        It does NOT run automatically - the application must explicitly call it.

        Use case examples:
        - Home Assistant: Add a config option "Auto-correct DST" and call this method
          when enabled
        - CLI tools: Provide a --sync-dst flag to trigger this method
        - Periodic tasks: Call during daily maintenance windows

        This method:
        1. Detects actual DST status using configured IANA timezone
        2. Compares with API's daylightSavingTime flag
        3. Updates API if mismatch found (only if needed)

        IMPORTANT: This method requires an IANA timezone to be configured on the
        LuxpowerClient. If not configured, sync will be skipped.

        Returns:
            True if setting was synced (or already correct), False if sync failed
            or if DST detection is disabled (no IANA timezone configured).

        Example:
            ```python
            # In Home Assistant integration config flow
            if user_config.get("auto_correct_dst"):
                station = await Station.load(client, plant_id)
                await station.sync_dst_setting()
            ```
        """
        actual_dst = self.detect_dst_status()

        if actual_dst is None:
            _LOGGER.debug(
                "Station %s: DST detection disabled or failed, skipping sync",
                self.id,
            )
            return False

        # Check if API setting matches detected status
        if actual_dst == self.daylight_saving_time:
            _LOGGER.debug("Station %s: DST setting already correct (%s)", self.id, actual_dst)
            return True

        # Mismatch detected - update API
        _LOGGER.warning(
            "Station %s: DST mismatch detected! API reports %s but offset indicates %s. "
            "Updating API setting...",
            self.id,
            self.daylight_saving_time,
            actual_dst,
        )

        try:
            success = await self.set_daylight_saving_time(actual_dst)
            if success:
                self.daylight_saving_time = actual_dst
                _LOGGER.info(
                    "Station %s: Successfully updated DST setting to %s", self.id, actual_dst
                )
            else:
                _LOGGER.error("Station %s: Failed to update DST setting", self.id)
            return success

        except Exception as e:
            _LOGGER.error("Station %s: Error syncing DST setting: %s", self.id, e)
            return False

    def get_current_date(self) -> str | None:
        """Get current date in station's timezone as YYYY-MM-DD string.

        This method uses currentTimezoneWithMinute (most accurate) as the primary
        source, falling back to parsing the timezone string if unavailable.

        Returns:
            Date string in YYYY-MM-DD format, or None if timezone cannot be determined.

        Example:
            currentTimezoneWithMinute: -420 (7 hours behind UTC)
            Current UTC: 2025-11-21 08:00
            Result: "2025-11-21" (01:00 PST, same date)

            currentTimezoneWithMinute: -420
            Current UTC: 2025-11-22 06:30
            Result: "2025-11-21" (23:30 PST, previous date)
        """
        try:
            # Primary: Use currentTimezoneWithMinute (most accurate, includes DST)
            # Note: This field is in HHMM format (e.g., -800 = -8:00), not literal minutes
            if self.current_timezone_with_minute is not None:
                # Parse HHMM format: -800 = -8 hours, 00 minutes
                value = self.current_timezone_with_minute
                hours = abs(value) // 100
                minutes = abs(value) % 100
                total_minutes = -(hours * 60 + minutes) if value < 0 else (hours * 60 + minutes)

                tz = timezone(timedelta(minutes=total_minutes))
                result = datetime.now(tz).strftime("%Y-%m-%d")
                _LOGGER.debug(
                    "Station %s: Date in timezone (offset %+d HHMM = %+d min): %s",
                    self.id,
                    self.current_timezone_with_minute,
                    total_minutes,
                    result,
                )
                return result

            # Fallback: Parse base timezone string
            if self.timezone and "GMT" in self.timezone:
                offset_str = self.timezone.replace("GMT", "").strip()
                if offset_str:
                    offset_hours = int(offset_str)
                    tz = timezone(timedelta(hours=offset_hours))
                    result = datetime.now(tz).strftime("%Y-%m-%d")
                    _LOGGER.debug(
                        "Station %s: Date using base timezone %s: %s",
                        self.id,
                        self.timezone,
                        result,
                    )
                    return result

            # Last resort: UTC
            _LOGGER.debug("Station %s: No timezone info available, using UTC", self.id)
            return datetime.now(UTC).strftime("%Y-%m-%d")

        except Exception as e:
            _LOGGER.debug("Error getting current date for station %s: %s", self.id, e)
            return None

    @property
    def all_inverters(self) -> list[BaseInverter]:
        """Get all inverters (parallel + standalone).

        Returns:
            List of all inverter objects in this station.
        """
        inverters: list[BaseInverter] = []
        # Add inverters from parallel groups
        for group in self.parallel_groups:
            inverters.extend(group.inverters)
        # Add standalone inverters
        inverters.extend(self.standalone_inverters)
        return inverters

    @property
    def all_batteries(self) -> list[Battery]:
        """Get all batteries from all inverters.

        Returns:
            List of all battery objects across all inverters.
        """

        batteries: list[Battery] = []
        for inverter in self.all_inverters:
            if inverter.battery_bank and inverter.battery_bank.batteries:
                batteries.extend(inverter.battery_bank.batteries)
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

        This method:
        1. Checks if cache should be invalidated (hour boundaries)
        2. Refreshes all inverters (runtime and energy data)
        3. Refreshes all MID devices
        4. Does NOT reload device hierarchy (use load() for that)

        Cache Invalidation:
            Automatically clears API caches within 5 minutes of hour boundaries
            to ensure fresh data at midnight (daily energy reset).
        """
        import asyncio

        # Check if cache invalidation is needed before refreshing
        if self._client.should_invalidate_cache():
            _LOGGER.info(
                "Station %s: Cache invalidation needed before hour boundary, clearing all caches",
                self.id,
            )
            self._client.clear_all_caches()

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

    async def _warm_parameter_cache(self) -> None:
        """Pre-fetch parameters for all inverters to eliminate first-access latency.

        This optimization fetches parameters concurrently for all inverters during
        initial station load, eliminating the ~300ms latency on first property access.

        Called automatically by Station.load() and Station.load_all().

        Benefits:
        - First access to properties like `ac_charge_power_limit` is instant (<1ms)
        - Reduces perceived latency in Home Assistant on integration startup
        - All parameter properties return immediately (already cached)

        Trade-offs:
        - Adds 3 API calls per inverter on startup (parameter ranges 0-127, 127-254, 240-367)
        - Increases initial load time by ~300ms (concurrent, not per-inverter)
        - May fetch data that's never accessed
        """
        import asyncio

        tasks = []

        # Refresh parameters for all inverters concurrently
        for inverter in self.all_inverters:
            if hasattr(inverter, "refresh"):
                # include_parameters=True triggers parameter fetch
                tasks.append(inverter.refresh(include_parameters=True))

        # Execute concurrently, ignore exceptions (partial failure OK)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

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
            country=plant_data.get("country", ""),
        )

        # Parse creation date
        created_date_str = plant_data.get("createDate", "")
        try:
            created_date = datetime.fromisoformat(created_date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            created_date = datetime.now()

        # Create station instance with timezone fields
        station = cls(
            client=client,
            plant_id=plant_id,
            name=plant_data.get("name", f"Station {plant_id}"),
            location=location,
            timezone=plant_data.get("timezone", "UTC"),
            created_date=created_date,
            current_timezone_with_minute=plant_data.get("currentTimezoneWithMinute"),
            daylight_saving_time=plant_data.get("daylightSavingTime", False),
        )

        # Load device hierarchy
        await station._load_devices()

        # Warm parameter cache for better initial performance (optimization)
        # This pre-fetches parameters for all inverters to eliminate first-access latency
        await station._warm_parameter_cache()

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
                    # Use deviceTypeText as the model name (e.g., "18KPV", "FlexBOSS21")
                    # This provides the human-readable model name
                    model_text = device_data.deviceTypeText

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

    # ============================================================================
    # Station-Level Control Operations (Issue #15)
    # ============================================================================

    async def set_daylight_saving_time(self, enabled: bool) -> bool:
        """Set daylight saving time adjustment for the station.

        This is a station-level setting that affects all devices in the station.

        Args:
            enabled: True to enable DST, False to disable

        Returns:
            True if successful, False otherwise

        Example:
            >>> await station.set_daylight_saving_time(True)
            True
        """
        result = await self._client.api.plants.set_daylight_saving_time(self.id, enabled)
        return bool(result.get("success", False))

    async def get_daylight_saving_time_enabled(self) -> bool:
        """Get current daylight saving time setting.

        Returns:
            True if DST is enabled, False otherwise

        Example:
            >>> is_dst = await station.get_daylight_saving_time_enabled()
            >>> is_dst
            False
        """
        plant_details = await self._client.api.plants.get_plant_details(self.id)
        return bool(plant_details.get("daylightSavingTime", False))
