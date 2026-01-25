"""Station (Plant) class for solar installations.

This module provides the Station class that represents a complete solar
installation with inverters, batteries, and optional MID devices.
"""

from __future__ import annotations

import asyncio
import logging
import zoneinfo
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, cast

from pylxpweb.constants import DEVICE_TYPE_GRIDBOSS, parse_hhmm_timezone
from pylxpweb.devices.discovery import (
    DeviceDiscoveryInfo,
    DiscoveryTransport,
    discover_device_info,
)
from pylxpweb.exceptions import LuxpowerAPIError, LuxpowerConnectionError, LuxpowerDeviceError
from pylxpweb.models import (
    InverterOverviewResponse,
    ParallelGroupDetailsResponse,
    ParallelGroupDeviceItem,
)
from pylxpweb.transports.config import TransportConfig
from pylxpweb.transports.factory import create_transport_from_config

from .base import BaseDevice
from .models import DeviceInfo, Entity

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient

    from .battery import Battery
    from .inverters.base import BaseInverter
    from .mid_device import MIDDevice
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


@dataclass
class AttachResult:
    """Result of attaching local transports to station devices.

    Attributes:
        matched: Number of transports successfully attached to devices.
        unmatched: Number of transports that didn't match any device.
        failed: Number of transports that failed to connect.
        unmatched_serials: List of serial numbers that didn't match any device.
        failed_serials: List of serial numbers that failed to connect.

    Example:
        >>> result = await station.attach_local_transports(configs)
        >>> print(f"Attached {result.matched} of {result.total} transports")
        >>> if result.unmatched_serials:
        ...     print(f"No devices found for: {result.unmatched_serials}")
    """

    matched: int
    unmatched: int
    failed: int
    unmatched_serials: list[str]
    failed_serials: list[str]

    @property
    def total(self) -> int:
        """Total number of transport configs processed."""
        return self.matched + self.unmatched + self.failed


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
        self.standalone_mid_devices: list[MIDDevice] = []
        self.weather: dict[str, Any] | None = None  # Weather data (optional)

        # Local-only mode flag (set by from_local_discovery)
        self._is_local_only: bool = False

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

        except (zoneinfo.ZoneInfoNotFoundError, ValueError, KeyError) as e:
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

        except (
            LuxpowerAPIError,
            LuxpowerConnectionError,
            zoneinfo.ZoneInfoNotFoundError,
            ValueError,
            KeyError,
        ) as e:
            _LOGGER.error("Station %s: Error syncing DST setting: %s", self.id, e)
            return False

    @property
    def current_date(self) -> str | None:
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
                hours, minutes = parse_hhmm_timezone(value)
                total_minutes = hours * 60 + minutes

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

        except (zoneinfo.ZoneInfoNotFoundError, ValueError, KeyError) as e:
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
            if inverter._battery_bank and inverter._battery_bank.batteries:
                batteries.extend(inverter._battery_bank.batteries)
        return batteries

    @property
    def all_mid_devices(self) -> list[MIDDevice]:
        """Get all MID devices (GridBOSS) in this station.

        Returns:
            List of all MID device objects, from both parallel groups and standalone.
        """

        mid_devices: list[MIDDevice] = []
        # Add MID devices from parallel groups
        for group in self.parallel_groups:
            if group.mid_device:
                mid_devices.append(group.mid_device)
        # Add standalone MID devices
        mid_devices.extend(self.standalone_mid_devices)
        return mid_devices

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
            Cache is automatically invalidated on the first request after any
            hour boundary (handled by LuxpowerClient._request method). This
            ensures fresh data at midnight for daily energy resets.
        """

        tasks = []

        # Refresh all inverters (all inverters have refresh method)
        for inverter in self.all_inverters:
            tasks.append(inverter.refresh())

        # Refresh all MID devices (from parallel groups and standalone)
        for mid_device in self.all_mid_devices:
            tasks.append(mid_device.refresh())

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
        tasks = []

        # Refresh parameters for all inverters concurrently (all inverters have refresh method)
        for inverter in self.all_inverters:
            # include_parameters=True triggers parameter fetch
            tasks.append(inverter.refresh(include_parameters=True))

        # Execute concurrently, ignore exceptions (partial failure OK)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _warm_parallel_group_energy_cache(self) -> None:
        """Pre-fetch energy data for all parallel groups to eliminate first-access latency.

        This optimization fetches energy data concurrently for all parallel groups during
        initial station load, ensuring energy sensors show data immediately in Home Assistant.

        Called automatically by Station.load() and Station.load_all().

        Benefits:
        - Parallel group energy properties return immediately with actual values
        - Eliminates 0.00 kWh display on integration startup in Home Assistant
        - All energy properties show real data from first access

        Trade-offs:
        - Adds 1 API call per parallel group on startup
        - Minimal increase in initial load time (~100ms, concurrent)
        """
        tasks = []

        # Fetch energy data for all parallel groups concurrently
        for group in self.parallel_groups:
            if group.inverters:
                first_serial = group.inverters[0].serial_number
                tasks.append(group._fetch_energy_data(first_serial))

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
            # Refresh if needed (all inverters have these attributes)
            if inverter.needs_refresh:
                await inverter.refresh()

            # Sum energy data (all inverters have _energy attribute)
            if inverter._energy:
                total_today += getattr(inverter._energy, "eToday", 0.0)
                total_lifetime += getattr(inverter._energy, "eTotal", 0.0)

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

        # Warm caches for better initial performance (optimization)
        # This pre-fetches data to eliminate first-access latency
        await station._warm_parameter_cache()
        await station._warm_parallel_group_energy_cache()

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
        tasks = [cls.load(client, plant.plantId) for plant in plants_response.rows]
        return await asyncio.gather(*tasks)

    @classmethod
    async def from_local_discovery(
        cls,
        configs: list[TransportConfig],
        station_name: str,
        plant_id: int,
        timezone: str = "UTC",
    ) -> Station:
        """Create a station from local transports without cloud API.

        This factory method creates a Station and its device hierarchy by
        connecting to inverters directly via Modbus TCP or WiFi dongle
        transports. It auto-discovers device types and parallel group
        membership from register data.

        The resulting station can be used for monitoring and control
        operations without requiring cloud API credentials.

        Args:
            configs: List of TransportConfig objects for each device.
                Each config specifies connection details (host, port, serial)
                and transport type (MODBUS_TCP or WIFI_DONGLE).
            station_name: Human-readable name for the station.
            plant_id: Unique identifier for the station. Use any unique int
                for local-only operation (e.g., 99999).
            timezone: Timezone string (IANA format like "America/Los_Angeles"
                or legacy format like "UTC"). Default: "UTC".

        Returns:
            Station instance with device hierarchy populated from local
            discovery. Inverters will have transports attached for direct
            data fetching.

        Raises:
            ValueError: If configs list is empty.

        Example:
            >>> from pylxpweb.transports import TransportConfig, TransportType
            >>> configs = [
            ...     TransportConfig(
            ...         host="192.168.1.100",
            ...         port=502,
            ...         serial="CE12345678",
            ...         transport_type=TransportType.MODBUS_TCP,
            ...     ),
            ... ]
            >>> station = await Station.from_local_discovery(
            ...     configs=configs,
            ...     station_name="Home Solar",
            ...     plant_id=99999,
            ...     timezone="America/Los_Angeles",
            ... )
            >>> print(f"Found {len(station.all_inverters)} inverters")

        Note:
            - Devices that fail to connect are skipped (partial discovery)
            - GridBOSS/MID devices are detected by device type code 50
            - Parallel groups are determined from register 107 values
            - The station's _client will be a placeholder (no API access)
        """
        from pylxpweb import LuxpowerClient

        from .inverters.base import BaseInverter
        from .mid_device import MIDDevice
        from .parallel_group import ParallelGroup

        if not configs:
            raise ValueError("At least one transport config required")

        # Create a placeholder client (no credentials = local-only)
        # This client provides the interface expected by devices but
        # won't make any HTTP API calls
        placeholder_client = LuxpowerClient("", "")

        # Create station instance with minimal metadata
        location = Location(address="Local", country="")
        station = cls(
            client=placeholder_client,
            plant_id=plant_id,
            name=station_name,
            location=location,
            timezone=timezone,
            created_date=datetime.now(),
        )

        # Mark station as local-only
        station._is_local_only = True

        # Connect to each transport and discover device info
        discovered_devices: list[tuple[Any, DeviceDiscoveryInfo]] = []

        for config in configs:
            transport = None
            try:
                config.validate()
                transport = create_transport_from_config(config)
                await transport.connect()

                # Cast to DiscoveryTransport - both ModbusTransport and DongleTransport
                # implement the required methods (read_device_type, is_midbox_device, etc.)
                discovery_transport = cast(DiscoveryTransport, transport)
                info = await discover_device_info(discovery_transport)
                discovered_devices.append((transport, info))
                _LOGGER.info(
                    "Discovered device %s: type=%d, gridboss=%s, parallel=%d",
                    info.serial,
                    info.device_type_code,
                    info.is_gridboss,
                    info.parallel_number,
                )

            except Exception as e:
                _LOGGER.warning(
                    "Failed to connect to %s:%d (%s): %s",
                    config.host,
                    config.port,
                    config.serial,
                    e,
                )
                # Cleanup partially connected transport to prevent resource leak
                if transport is not None:
                    try:
                        await transport.disconnect()
                    except Exception:  # noqa: S110 - best effort cleanup
                        _LOGGER.debug("Cleanup disconnect failed for %s", config.serial)
                continue

        # Group devices by parallel_number
        # parallel_number=0 means standalone, 1-n means group A-Z
        groups_by_number: dict[int, list[tuple[Any, DeviceDiscoveryInfo]]] = {}
        for transport, info in discovered_devices:
            pn = info.parallel_number
            if pn not in groups_by_number:
                groups_by_number[pn] = []
            groups_by_number[pn].append((transport, info))

        # Process standalone devices (parallel_number=0)
        if 0 in groups_by_number:
            for transport, info in groups_by_number[0]:
                if info.is_gridboss:
                    mid_device = MIDDevice(
                        client=placeholder_client,
                        serial_number=info.serial,
                        model="GridBOSS",
                    )
                    mid_device._local_transport = transport
                    station.standalone_mid_devices.append(mid_device)
                else:
                    inverter = await BaseInverter.from_modbus_transport(transport)
                    station.standalone_inverters.append(inverter)
            del groups_by_number[0]

        # Process parallel groups (parallel_number > 0)
        for group_number in sorted(groups_by_number.keys()):
            devices_in_group = groups_by_number[group_number]
            group_name = chr(ord("A") + group_number - 1)  # 1=A, 2=B, etc.

            # Create parallel group
            first_serial = devices_in_group[0][1].serial if devices_in_group else ""
            group = ParallelGroup(
                client=placeholder_client,
                station=station,
                name=group_name,
                first_device_serial=first_serial,
            )

            # Assign devices to group
            for transport, info in devices_in_group:
                if info.is_gridboss:
                    mid_device = MIDDevice(
                        client=placeholder_client,
                        serial_number=info.serial,
                        model="GridBOSS",
                    )
                    mid_device._local_transport = transport
                    group.mid_device = mid_device
                else:
                    inverter = await BaseInverter.from_modbus_transport(transport)
                    group.inverters.append(inverter)

            station.parallel_groups.append(group)
            _LOGGER.info(
                "Created parallel group %s with %d inverter(s) and %s",
                group_name,
                len(group.inverters),
                "GridBOSS" if group.mid_device else "no MID device",
            )

        _LOGGER.info(
            "Local discovery complete: %d standalone inverters, %d parallel groups, %d MID devices",
            len(station.standalone_inverters),
            len(station.parallel_groups),
            len(station.all_mid_devices),
        )

        return station

    @property
    def is_local_only(self) -> bool:
        """Check if this station was created from local discovery only.

        Returns:
            True if station was created via from_local_discovery(),
            False if created via load() or load_all() (cloud API).
        """
        return getattr(self, "_is_local_only", False)

    @property
    def is_hybrid_mode(self) -> bool:
        """Check if any device has a local transport attached for hybrid mode.

        Hybrid mode means the station was discovered via HTTP API but has
        local transports attached for faster/local-only data access.

        Returns:
            True if at least one device has _local_transport attached,
            False otherwise.
        """
        # Check standalone inverters
        for inverter in self.standalone_inverters:
            if getattr(inverter, "_local_transport", None) is not None:
                return True

        # Check inverters in parallel groups
        for group in self.parallel_groups:
            for inverter in group.inverters:
                if getattr(inverter, "_local_transport", None) is not None:
                    return True
            # Check MID device in group
            if group.mid_device and getattr(group.mid_device, "_local_transport", None) is not None:
                return True

        # Check standalone MID devices
        for mid_device in self.standalone_mid_devices:
            if getattr(mid_device, "_local_transport", None) is not None:
                return True

        return False

    async def attach_local_transports(self, configs: list[TransportConfig]) -> AttachResult:
        """Attach local transports to HTTP-discovered devices for hybrid mode.

        This method enables hybrid mode by connecting local transports
        (Modbus TCP or WiFi Dongle) to devices that were originally
        discovered via the HTTP API. When a local transport is attached,
        the device will use it for data fetching instead of HTTP.

        The matching is done by serial number - each transport config's
        serial must match a device's serial_number in the station.

        Args:
            configs: List of TransportConfig objects specifying connection
                details. Each config should have a serial number that
                matches a device in this station.

        Returns:
            AttachResult with counts of matched, unmatched, and failed
            transports, plus lists of problematic serial numbers.

        Example:
            >>> from pylxpweb.transports import TransportConfig, TransportType
            >>> configs = [
            ...     TransportConfig(
            ...         host="192.168.1.100",
            ...         port=502,
            ...         serial="CE12345678",
            ...         transport_type=TransportType.MODBUS_TCP,
            ...     ),
            ... ]
            >>> result = await station.attach_local_transports(configs)
            >>> print(f"Attached {result.matched} transports")
            >>> if result.unmatched_serials:
            ...     print(f"No devices for: {result.unmatched_serials}")

        Note:
            - Transports are only attached to devices with matching serial
            - Connection failures are logged and skipped (partial success OK)
            - Use is_hybrid_mode property to check if any transports attached
        """
        if not configs:
            return AttachResult(
                matched=0, unmatched=0, failed=0, unmatched_serials=[], failed_serials=[]
            )

        # Build device lookup by serial number
        device_lookup: dict[str, Any] = {}

        # Add standalone inverters
        for inverter in self.standalone_inverters:
            device_lookup[inverter.serial_number] = inverter

        # Add inverters from parallel groups
        for group in self.parallel_groups:
            for inverter in group.inverters:
                device_lookup[inverter.serial_number] = inverter
            # Add MID device if present
            if group.mid_device:
                device_lookup[group.mid_device.serial_number] = group.mid_device

        # Add standalone MID devices
        for mid_device in self.standalone_mid_devices:
            device_lookup[mid_device.serial_number] = mid_device

        matched = 0
        unmatched = 0
        failed = 0
        unmatched_serials: list[str] = []
        failed_serials: list[str] = []

        for config in configs:
            try:
                config.validate()
                transport = create_transport_from_config(config)
                await transport.connect()

                # Find matching device
                device = device_lookup.get(config.serial)
                if device is None:
                    _LOGGER.warning(
                        "No device found with serial %s for transport %s:%d",
                        config.serial,
                        config.host,
                        config.port,
                    )
                    # Close unused transport to prevent resource leak
                    try:
                        await transport.disconnect()
                    except Exception:  # noqa: S110 - best effort cleanup
                        _LOGGER.debug("Cleanup disconnect failed for %s", config.serial)
                    unmatched += 1
                    unmatched_serials.append(config.serial)
                    continue

                # Attach transport to device
                device._local_transport = transport
                matched += 1
                _LOGGER.info(
                    "Attached %s transport to device %s at %s:%d",
                    config.transport_type.value,
                    config.serial,
                    config.host,
                    config.port,
                )

            except Exception as e:
                _LOGGER.warning(
                    "Failed to attach transport for %s at %s:%d: %s",
                    config.serial,
                    config.host,
                    config.port,
                    e,
                )
                failed += 1
                failed_serials.append(config.serial)

        _LOGGER.info(
            "Transport attachment complete: %d matched, %d unmatched, %d failed",
            matched,
            unmatched,
            failed,
        )

        return AttachResult(
            matched=matched,
            unmatched=unmatched,
            failed=failed,
            unmatched_serials=unmatched_serials,
            failed_serials=failed_serials,
        )

    async def _load_devices(self) -> None:
        """Load device hierarchy from API.

        This method orchestrates device loading by:
        1. Getting device list from API
        2. Finding GridBOSS to query parallel group configuration
        3. If GridBOSS found but no parallel groups, trigger auto-sync
        4. Creating ParallelGroup objects
        5. Assigning inverters and MID devices to groups or standalone list
        """
        try:
            # Get device list and parallel group configuration
            devices_response = await self._get_device_list()
            gridboss_serial = self._find_gridboss(devices_response)
            group_data = await self._get_parallel_groups(gridboss_serial)

            # If GridBOSS detected but no parallel group data, trigger auto-sync
            if gridboss_serial and (not group_data or not group_data.devices):
                _LOGGER.info(
                    "GridBOSS %s detected but no parallel groups found, triggering auto-sync",
                    gridboss_serial,
                )
                sync_success = await self._client.api.devices.sync_parallel_groups(self.id)
                if sync_success:
                    _LOGGER.info("Parallel group sync successful, re-fetching group data")
                    # Re-fetch parallel group data after sync
                    group_data = await self._get_parallel_groups(gridboss_serial)
                else:
                    _LOGGER.warning(
                        "Parallel group sync failed for station %s - GridBOSS may not appear",
                        self.id,
                    )

            # Create parallel groups and lookup dictionary
            groups_lookup = self._create_parallel_groups(group_data, devices_response)

            # Assign devices to groups or standalone
            self._assign_devices(devices_response, groups_lookup)

        except (LuxpowerAPIError, LuxpowerConnectionError, LuxpowerDeviceError) as e:
            # If device loading fails, log and continue
            # Station can still function with empty device lists
            _LOGGER.warning("Failed to load devices for station %s: %s", self.id, e, exc_info=True)

    async def _get_device_list(self) -> InverterOverviewResponse:
        """Get device list from API.

        Returns:
            Device list response from API.
        """
        return await self._client.api.devices.get_devices(self.id)

    def _find_gridboss(self, devices_response: InverterOverviewResponse) -> str | None:
        """Find GridBOSS device in device list.

        Args:
            devices_response: Device list response from API.

        Returns:
            GridBOSS serial number if found, None otherwise.
        """
        if not devices_response.rows:
            return None

        for device in devices_response.rows:
            if device.deviceType == DEVICE_TYPE_GRIDBOSS:
                _LOGGER.debug("Found GridBOSS device: %s", device.serialNum)
                return device.serialNum

        return None

    async def _get_parallel_groups(
        self, gridboss_serial: str | None
    ) -> ParallelGroupDetailsResponse | None:
        """Get parallel group details if GridBOSS exists.

        Args:
            gridboss_serial: GridBOSS serial number or None.

        Returns:
            Parallel group details or None if not available.
        """
        if not gridboss_serial:
            return None

        try:
            return await self._client.api.devices.get_parallel_group_details(gridboss_serial)
        except (LuxpowerAPIError, LuxpowerConnectionError, LuxpowerDeviceError) as e:
            _LOGGER.debug("Could not load parallel group details: %s", str(e))
            return None

    def _create_parallel_groups(
        self,
        group_data: ParallelGroupDetailsResponse | None,
        devices_response: InverterOverviewResponse,
    ) -> dict[str, ParallelGroup]:
        """Create ParallelGroup objects from API data.

        Args:
            group_data: Parallel group details from API.
            devices_response: Device list for looking up group names.

        Returns:
            Dictionary mapping group names to ParallelGroup objects.
        """
        from .parallel_group import ParallelGroup

        if not group_data or not group_data.devices:
            return {}

        # Create device lookup for O(1) access
        device_lookup = {d.serialNum: d for d in devices_response.rows}

        # Group devices by parallelGroup field
        groups_by_name: dict[str, list[ParallelGroupDeviceItem]] = {}
        for pg_device in group_data.devices:
            device_info = device_lookup.get(pg_device.serialNum)
            if device_info and device_info.parallelGroup:
                group_name = device_info.parallelGroup
                if group_name not in groups_by_name:
                    groups_by_name[group_name] = []
                groups_by_name[group_name].append(pg_device)

        # Create ParallelGroup objects
        groups_lookup = {}
        for group_name, devices in groups_by_name.items():
            first_serial = devices[0].serialNum if devices else ""
            group = ParallelGroup(
                client=self._client,
                station=self,
                name=group_name,
                first_device_serial=first_serial,
            )
            self.parallel_groups.append(group)
            groups_lookup[group_name] = group
            _LOGGER.debug("Created parallel group '%s' with %d devices", group_name, len(devices))

        return groups_lookup

    def _assign_devices(
        self, devices_response: InverterOverviewResponse, groups_lookup: dict[str, ParallelGroup]
    ) -> None:
        """Assign devices to parallel groups or standalone list.

        Args:
            devices_response: Device list from API.
            groups_lookup: Dictionary mapping group names to ParallelGroup objects.
        """

        if not devices_response.rows:
            return

        for device_data in devices_response.rows:
            if not device_data.serialNum:
                continue

            serial_num = device_data.serialNum
            device_type = device_data.deviceType
            model_text = device_data.deviceTypeText
            parallel_group_name = device_data.parallelGroup

            # Handle GridBOSS/MID devices
            if device_type == DEVICE_TYPE_GRIDBOSS:
                self._assign_mid_device(serial_num, model_text, parallel_group_name, groups_lookup)
                continue

            # Handle inverters
            self._assign_inverter(serial_num, model_text, parallel_group_name, groups_lookup)

    def _assign_mid_device(
        self,
        serial_num: str,
        model_text: str,
        parallel_group_name: str | None,
        groups_lookup: dict[str, ParallelGroup],
    ) -> None:
        """Assign MID device to parallel group or standalone list.

        Args:
            serial_num: MID device serial number.
            model_text: MID device model name.
            parallel_group_name: Parallel group name or None.
            groups_lookup: Dictionary mapping group names to ParallelGroup objects.
        """
        from .mid_device import MIDDevice

        mid_device = MIDDevice(client=self._client, serial_number=serial_num, model=model_text)

        if parallel_group_name:
            found_group = groups_lookup.get(parallel_group_name)
            if found_group:
                found_group.mid_device = mid_device
                _LOGGER.debug(
                    "Assigned MID device %s to parallel group '%s'",
                    serial_num,
                    parallel_group_name,
                )
            else:
                # Parallel group not found - treat as standalone
                self.standalone_mid_devices.append(mid_device)
                _LOGGER.debug(
                    "Parallel group '%s' not found for MID device %s - treating as standalone",
                    parallel_group_name,
                    serial_num,
                )
        else:
            # Standalone MID device (no inverters in system)
            self.standalone_mid_devices.append(mid_device)
            _LOGGER.debug("Assigned MID device %s as standalone", serial_num)

    def _assign_inverter(
        self,
        serial_num: str,
        model_text: str,
        parallel_group_name: str | None,
        groups_lookup: dict[str, ParallelGroup],
    ) -> None:
        """Assign inverter to parallel group or standalone list.

        Args:
            serial_num: Inverter serial number.
            model_text: Inverter model name.
            parallel_group_name: Parallel group name or None.
            groups_lookup: Dictionary mapping group names to ParallelGroup objects.
        """
        from .inverters.generic import GenericInverter

        inverter = GenericInverter(client=self._client, serial_number=serial_num, model=model_text)

        if parallel_group_name:
            found_group = groups_lookup.get(parallel_group_name)
            if found_group:
                found_group.inverters.append(inverter)
                _LOGGER.debug(
                    "Assigned inverter %s to parallel group '%s'",
                    serial_num,
                    parallel_group_name,
                )
            else:
                # If parallel group not found, treat as standalone
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

    # ============================================================================
    # Station-Level Control Operations (Issue #15)
    # ============================================================================

    async def set_daylight_saving_time(self, enabled: bool) -> bool:
        """Set daylight saving time adjustment for the station.

        This is a station-level setting that affects all devices in the station.

        After a successful write, the cached DST state is updated to reflect the new value.
        This ensures that subsequent reads return the correct state without requiring
        an additional API call.

        Args:
            enabled: True to enable DST, False to disable

        Returns:
            True if successful, False otherwise

        Example:
            >>> await station.set_daylight_saving_time(True)
            True
            >>> station.daylight_saving_time  # Immediately reflects new value
            True
        """
        result = await self._client.api.plants.set_daylight_saving_time(self.id, enabled)
        success = bool(result.get("success", False))

        # Update cached state on successful write to ensure consistency
        if success:
            self.daylight_saving_time = enabled

        return success

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
