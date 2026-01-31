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
from typing import TYPE_CHECKING, Any

from pylxpweb.constants import DEVICE_TYPE_GRIDBOSS, parse_hhmm_timezone
from pylxpweb.exceptions import LuxpowerAPIError, LuxpowerConnectionError, LuxpowerDeviceError
from pylxpweb.models import (
    InverterOverviewResponse,
    ParallelGroupDetailsResponse,
    ParallelGroupDeviceItem,
)

from .base import BaseDevice
from .models import DeviceInfo, Entity

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient
    from pylxpweb.transports.config import AttachResult, TransportConfig

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
        *,
        station_name: str = "Local Station",
        plant_id: int = 0,
        timezone_str: str = "UTC",
    ) -> Station:
        """Create a Station from local transport discovery.

        This factory method creates a Station hierarchy by connecting to
        devices via local transports (Modbus TCP or WiFi Dongle) and using
        register-based parallel group detection instead of the HTTP API.

        The parallel group detection works by reading registers 107-108 from
        each device. Devices with matching (parallel_number, parallel_phase)
        values are grouped together.

        Args:
            configs: List of TransportConfig objects for devices to discover.
            station_name: Name for the created station (default: "Local Station").
            plant_id: Unique identifier for the station (default: 0).
            timezone_str: Timezone string for the station (default: "UTC").

        Returns:
            Station instance with devices organized by parallel groups.

        Raises:
            ValueError: If no configs are provided.
            TransportConnectionError: If all transports fail to connect.

        Example:
            ```python
            from pylxpweb.transports import TransportConfig, TransportType

            configs = [
                TransportConfig(
                    host="192.168.1.100",
                    port=502,
                    serial="CE12345678",
                    transport_type=TransportType.MODBUS_TCP,
                ),
                TransportConfig(
                    host="192.168.1.101",
                    port=502,
                    serial="CE87654321",
                    transport_type=TransportType.MODBUS_TCP,
                ),
            ]

            station = await Station.from_local_discovery(
                configs,
                station_name="My Solar System",
                plant_id=1,
            )

            # Devices are grouped by parallel registers (107-108)
            for group in station.parallel_groups:
                print(f"Group: {len(group.inverters)} inverters")
            ```
        """
        from pylxpweb.transports import (
            TransportConnectionError,
            group_by_parallel_config,
        )

        if not configs:
            raise ValueError("At least one TransportConfig is required")

        # Create station with minimal placeholder client (local-only mode)
        station = cls(
            client=None,  # type: ignore[arg-type]
            plant_id=plant_id,
            name=station_name,
            location=Location(address="", country=""),
            timezone=timezone_str,
            created_date=datetime.now(UTC),
        )

        # Discover devices from all transports
        discovered, failed_serials = await cls._discover_devices_from_configs(configs)

        if not discovered:
            raise TransportConnectionError("All transports failed to connect")

        # Group devices by parallel config (registers 107-108)
        infos = [info for _, info in discovered]
        groups = group_by_parallel_config(infos)
        transport_lookup = {info.serial: transport for transport, info in discovered}

        # Process each parallel group
        for group_key, group_infos in groups.items():
            if group_key is None:
                # Standalone devices (no parallel config)
                cls._add_standalone_devices(station, group_infos, transport_lookup)
            else:
                # Devices with matching parallel config form a group
                cls._add_parallel_group(station, group_key, group_infos, transport_lookup)

        _LOGGER.info(
            "Created station '%s' with %d parallel groups, %d standalone inverters, "
            "%d standalone MID devices (%d failed)",
            station_name,
            len(station.parallel_groups),
            len(station.standalone_inverters),
            len(station.standalone_mid_devices),
            len(failed_serials),
        )

        return station

    @classmethod
    async def _discover_devices_from_configs(
        cls,
        configs: list[TransportConfig],
    ) -> tuple[list[tuple[Any, Any]], list[str]]:
        """Connect to transports and discover device information.

        Args:
            configs: List of transport configurations.

        Returns:
            Tuple of (discovered devices, failed serials).
        """
        from pylxpweb.transports import discover_device_info

        discovered: list[tuple[Any, Any]] = []
        failed_serials: list[str] = []

        for config in configs:
            transport = cls._create_transport_from_config(config)
            if transport is None:
                failed_serials.append(config.serial)
                continue

            try:
                await transport.connect()
                info = await discover_device_info(transport)
                discovered.append((transport, info))
                _LOGGER.debug(
                    "Discovered device %s: type=%d, family=%s, parallel=(%s, %s)",
                    info.serial,
                    info.device_type_code,
                    info.model_family,
                    info.parallel_number,
                    info.parallel_phase,
                )
            except Exception as err:
                _LOGGER.warning("Failed to connect to %s: %s", config.serial, err)
                failed_serials.append(config.serial)

        return discovered, failed_serials

    @classmethod
    def _create_transport_from_config(cls, config: TransportConfig) -> Any | None:
        """Create a transport from configuration.

        Args:
            config: Transport configuration.

        Returns:
            Transport instance or None if creation failed.
        """
        from pylxpweb.transports import create_dongle_transport, create_modbus_transport
        from pylxpweb.transports.config import TransportType

        if config.transport_type == TransportType.MODBUS_TCP:
            return create_modbus_transport(
                host=config.host,
                port=config.port,
                unit_id=config.unit_id,
                serial=config.serial,
                inverter_family=config.inverter_family,
                timeout=config.timeout,
            )

        if config.transport_type == TransportType.WIFI_DONGLE:
            if not config.dongle_serial:
                _LOGGER.warning(
                    "Dongle serial required for WiFi dongle transport, skipping %s",
                    config.serial,
                )
                return None
            return create_dongle_transport(
                host=config.host,
                dongle_serial=config.dongle_serial,
                inverter_serial=config.serial,
                port=config.port,
                inverter_family=config.inverter_family,
                timeout=config.timeout,
            )

        _LOGGER.warning("Unknown transport type: %s", config.transport_type)
        return None

    @classmethod
    def _create_device_with_transport(
        cls,
        info: Any,
        transport: Any,
    ) -> tuple[Any, bool]:
        """Create a device (inverter or MID) with attached transport.

        Args:
            info: Device discovery info.
            transport: Transport to attach.

        Returns:
            Tuple of (device instance, is_gridboss flag).
        """
        from pylxpweb.transports import is_gridboss_device

        from .inverters.generic import GenericInverter
        from .mid_device import MIDDevice

        is_gridboss = is_gridboss_device(info.device_type_code)
        device: MIDDevice | GenericInverter

        if is_gridboss:
            device = MIDDevice(
                client=None,  # type: ignore[arg-type]
                serial_number=info.serial,
                model=info.model_family,
            )
        else:
            device = GenericInverter(
                client=None,  # type: ignore[arg-type]
                serial_number=info.serial,
                model=info.model_family,
            )

        device._transport = transport
        return device, is_gridboss

    @classmethod
    def _add_standalone_devices(
        cls,
        station: Station,
        infos: list[Any],
        transport_lookup: dict[str, Any],
    ) -> None:
        """Add standalone devices to the station.

        Args:
            station: Station to add devices to.
            infos: List of device discovery infos.
            transport_lookup: Map of serial to transport.
        """
        for info in infos:
            transport = transport_lookup[info.serial]
            device, is_gridboss = cls._create_device_with_transport(info, transport)

            if is_gridboss:
                station.standalone_mid_devices.append(device)
                _LOGGER.debug("Added standalone MID device: %s", info.serial)
            else:
                station.standalone_inverters.append(device)
                _LOGGER.debug("Added standalone inverter: %s", info.serial)

    @classmethod
    def _add_parallel_group(
        cls,
        station: Station,
        group_key: tuple[int, int],
        infos: list[Any],
        transport_lookup: dict[str, Any],
    ) -> None:
        """Create a parallel group and add devices to it.

        Args:
            station: Station to add the group to.
            group_key: Tuple of (parallel_number, parallel_phase).
            infos: List of device discovery infos for this group.
            transport_lookup: Map of serial to transport.
        """
        from pylxpweb.transports import is_gridboss_device

        from .parallel_group import ParallelGroup

        parallel_number, parallel_phase = group_key
        group_name = f"Group_{parallel_number}_{parallel_phase}"

        # Find first inverter serial for the group
        first_inverter_serial = next(
            (info.serial for info in infos if not is_gridboss_device(info.device_type_code)),
            infos[0].serial,
        )

        parallel_group = ParallelGroup(
            client=None,  # type: ignore[arg-type]
            station=station,
            name=group_name,
            first_device_serial=first_inverter_serial,
        )

        # Add devices to the group
        for info in infos:
            transport = transport_lookup[info.serial]
            device, is_gridboss = cls._create_device_with_transport(info, transport)

            if is_gridboss:
                parallel_group.mid_device = device
                _LOGGER.debug("Added MID device %s to group %s", info.serial, group_name)
            else:
                parallel_group.inverters.append(device)
                _LOGGER.debug("Added inverter %s to group %s", info.serial, group_name)

        station.parallel_groups.append(parallel_group)

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

    # ============================================================================
    # Hybrid Mode Support (Local Transports + HTTP Fallback)
    # ============================================================================

    @property
    def is_hybrid_mode(self) -> bool:
        """Check if station is operating in hybrid mode.

        Hybrid mode means at least one inverter has a local transport attached
        for direct communication, with HTTP API as fallback.

        Returns:
            True if any inverter has a local transport attached.

        Example:
            >>> station = await Station.load(client, plant_id)
            >>> station.is_hybrid_mode
            False
            >>> await station.attach_local_transports(configs)
            >>> station.is_hybrid_mode
            True
        """
        return any(inverter._transport is not None for inverter in self.all_inverters)

    async def attach_local_transports(self, configs: list[TransportConfig]) -> AttachResult:
        """Attach local transports to HTTP-discovered devices.

        This method enables hybrid mode by connecting local transports
        (Modbus TCP or WiFi Dongle) to devices discovered via HTTP API.
        After attachment, devices will use local transport for data fetching
        with automatic fallback to HTTP on failure.

        Args:
            configs: List of TransportConfig objects specifying local transports.
                Each config includes serial, host, port, and transport type.

        Returns:
            AttachResult with counts of matched, unmatched, and failed attachments.

        Example:
            ```python
            from pylxpweb.transports.config import TransportConfig, TransportType

            configs = [
                TransportConfig(
                    host="192.168.1.100",
                    port=502,
                    serial="CE12345678",
                    transport_type=TransportType.MODBUS_TCP,
                    unit_id=1,
                ),
            ]

            result = await station.attach_local_transports(configs)
            print(f"Attached {result.matched} transport(s)")
            ```
        """
        from pylxpweb.transports import (
            DongleTransport,
            ModbusTransport,
            create_dongle_transport,
            create_modbus_transport,
        )
        from pylxpweb.transports.config import AttachResult, TransportType

        from .mid_device import MIDDevice

        result = AttachResult()

        # Build device lookup for O(1) matching (inverters + MID devices)
        device_lookup: dict[str, BaseInverter | MIDDevice] = {
            inv.serial_number: inv for inv in self.all_inverters
        }
        for mid in self.all_mid_devices:
            device_lookup[mid.serial_number] = mid

        for config in configs:
            serial = config.serial

            # Check if device (inverter or MID/GridBOSS) exists in station
            device = device_lookup.get(serial)
            if device is None:
                _LOGGER.warning(
                    "No device found with serial %s in station %s",
                    serial,
                    self.id,
                )
                result.unmatched += 1
                result.unmatched_serials.append(serial)
                continue

            # Create and connect transport
            try:
                transport: ModbusTransport | DongleTransport
                if config.transport_type == TransportType.MODBUS_TCP:
                    transport = create_modbus_transport(
                        host=config.host,
                        port=config.port,
                        unit_id=config.unit_id,
                        serial=serial,
                        timeout=config.timeout,
                        inverter_family=config.inverter_family,
                    )
                elif config.transport_type == TransportType.WIFI_DONGLE:
                    # dongle_serial is guaranteed by TransportConfig validation
                    assert config.dongle_serial is not None
                    transport = create_dongle_transport(
                        host=config.host,
                        port=config.port,
                        dongle_serial=config.dongle_serial,
                        inverter_serial=serial,
                        timeout=config.timeout,
                        inverter_family=config.inverter_family,
                    )
                else:
                    _LOGGER.error("Unknown transport type: %s", config.transport_type)
                    result.failed += 1
                    result.failed_serials.append(serial)
                    continue

                # Connect the transport
                await transport.connect()

                # Attach to device (inverter or MID device)
                device._transport = transport
                result.matched += 1
                device_type = "MID device" if isinstance(device, MIDDevice) else "inverter"
                _LOGGER.info(
                    "Attached %s transport to %s %s (%s:%d)",
                    config.transport_type.value,
                    device_type,
                    serial,
                    config.host,
                    config.port,
                )

            except Exception as err:
                _LOGGER.error(
                    "Failed to attach transport to device %s: %s",
                    serial,
                    err,
                )
                result.failed += 1
                result.failed_serials.append(serial)

        return result
