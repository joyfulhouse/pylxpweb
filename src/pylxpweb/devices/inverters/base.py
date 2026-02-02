"""Base inverter class for all inverter types.

This module provides the BaseInverter abstract class that all model-specific
inverter implementations must inherit from.
"""

from __future__ import annotations

import asyncio
import logging
from abc import abstractmethod
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from pylxpweb.constants import (
    DEVICE_TYPE_CODE_GRIDBOSS,
    MAX_REGISTERS_PER_READ,
    SOC_MAX_PERCENT,
    SOC_MIN_PERCENT,
)
from pylxpweb.exceptions import LuxpowerAPIError, LuxpowerConnectionError, LuxpowerDeviceError
from pylxpweb.models import OperatingMode

from .._firmware_update_mixin import FirmwareUpdateMixin
from ..base import BaseDevice
from ..models import DeviceInfo, Entity
from ._features import (
    DEVICE_TYPE_CODE_TO_FAMILY,
    GridType,
    InverterFamily,
    InverterFeatures,
    InverterModelInfo,
)
from ._runtime_properties import InverterRuntimePropertiesMixin

_LOGGER = logging.getLogger(__name__)

# ============================================================================
# Holding Register Constants for Transport Control Operations
# ============================================================================
# Register 21: FUNC_EN - Function enable bit field
HOLD_FUNC_EN = 21
FUNC_EN_BIT_EPS = 0  # EPS/Battery Backup mode
FUNC_EN_BIT_AC_CHARGE = 7  # AC Charge enable
FUNC_EN_BIT_STANDBY = 9  # Standby mode (power off)
FUNC_EN_BIT_FORCED_DISCHARGE = 10  # Forced discharge
FUNC_EN_BIT_FORCED_CHARGE = 11  # Forced charge
FUNC_EN_BIT_PV_PRIORITY = 12  # PV charge priority

# Register 110: SYS_FUNC - System function bit field
HOLD_SYS_FUNC = 110
SYS_FUNC_BIT_GREEN_MODE = 8  # Green/Off-Grid mode

# Value registers - AC charge settings
HOLD_AC_CHARGE_POWER = 66  # AC charge power percentage (0-100)
HOLD_AC_CHARGE_SOC_LIMIT = 67  # AC charge SOC limit (0-100)

# Value registers - SOC limits
HOLD_ON_GRID_SOC_CUTOFF = 105  # On-grid discharge SOC cutoff (10-90)
HOLD_OFF_GRID_SOC_CUTOFF = 106  # Off-grid discharge SOC cutoff (0-100)

# Value registers - charge/discharge current
HOLD_CHARGE_CURRENT = 101  # Max charge current (amps)
HOLD_DISCHARGE_CURRENT = 102  # Max discharge current (amps)

# Value registers - power settings
HOLD_PV_CHARGE_POWER = 64  # PV charge power percentage (0-100)
HOLD_DISCHARGE_POWER = 65  # Discharge power percentage (0-100)

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient
    from pylxpweb.models import EnergyInfo, InverterRuntime
    from pylxpweb.transports.protocol import InverterTransport


class BaseInverter(FirmwareUpdateMixin, InverterRuntimePropertiesMixin, BaseDevice):
    """Abstract base class for all inverter types.

    All model-specific inverter classes (FlexBOSS, 18KPV, etc.) must inherit
    from this class and implement its abstract methods.

    Attributes:
        runtime: Cached runtime data (power, voltage, current, temperature)
        energy: Cached energy data (daily, monthly, lifetime production)
        batteries: List of battery objects connected to this inverter
    """

    def __init__(
        self,
        client: LuxpowerClient,
        serial_number: str,
        model: str,
        transport: InverterTransport | None = None,
    ) -> None:
        """Initialize inverter.

        Args:
            client: LuxpowerClient instance for API access
            serial_number: Inverter serial number (10-digit)
            model: Inverter model name (e.g., "FlexBOSS21", "18KPV")
            transport: Optional transport for direct local communication
                (Modbus TCP, WiFi dongle). When provided, data fetching
                uses the transport instead of the HTTP API client.
        """
        super().__init__(client, serial_number, model)

        # Optional transport for direct local communication
        self._transport: InverterTransport | None = transport

        # Runtime data (refreshed frequently) - PRIVATE: use properties for access
        # HTTP API returns InverterRuntime, transport returns InverterRuntimeData
        self._runtime: InverterRuntime | None = None
        self._transport_runtime: Any | None = None  # InverterRuntimeData when using transport

        # Energy data (refreshed less frequently) - PRIVATE: use properties for access
        # HTTP API returns EnergyInfo, transport returns InverterEnergyData
        self._energy: EnergyInfo | None = None
        self._transport_energy: Any | None = None  # InverterEnergyData when using transport

        # Battery bank (aggregate data and individual batteries) - PRIVATE: use properties
        self._battery_bank: Any | None = None  # Will be BatteryBank object
        self._transport_battery: Any | None = None  # BatteryBankData when using transport

        # Parameters (configuration registers, refreshed hourly)
        self.parameters: dict[str, Any] | None = None

        # ===== Cache Management =====
        # Parameters cache time tracking
        self._parameters_cache_time: datetime | None = None
        self._parameters_cache_ttl = timedelta(hours=1)  # 1-hour TTL for parameters
        self._parameters_cache_lock = asyncio.Lock()

        # Runtime data cache
        self._runtime_cache_time: datetime | None = None
        self._runtime_cache_ttl = timedelta(seconds=30)  # 30-second TTL for runtime
        self._runtime_cache_lock = asyncio.Lock()

        # Energy data cache
        self._energy_cache_time: datetime | None = None
        self._energy_cache_ttl = timedelta(minutes=5)  # 5-minute TTL for energy
        self._energy_cache_lock = asyncio.Lock()

        # Battery data cache
        self._battery_cache_time: datetime | None = None
        self._battery_cache_ttl = timedelta(seconds=30)  # 30-second TTL for battery
        self._battery_cache_lock = asyncio.Lock()

        # ===== Firmware Update Cache =====
        # Initialize firmware update detection (from FirmwareUpdateMixin)
        self._init_firmware_update_cache()

        # ===== Feature Detection =====
        # Detected inverter features and capabilities
        self._features: InverterFeatures = InverterFeatures()
        self._features_detected: bool = False

    def _is_cache_expired(
        self,
        cache_time: datetime | None,
        ttl: timedelta,
        force: bool,
    ) -> bool:
        """Check if cache entry has expired.

        Args:
            cache_time: Timestamp of cached data
            ttl: Time-to-live for this cache
            force: If True, always return True (force refresh)

        Returns:
            True if cache is expired or missing
        """
        if force:
            return True
        if cache_time is None:
            return True
        return (datetime.now() - cache_time) > ttl

    def set_transport_cache_ttls(self) -> None:
        """Adjust cache TTLs based on attached transport type.

        Modbus TCP/Serial transports can be polled every 5s (local network).
        WiFi Dongle transports use 30s (slower protocol).
        Cloud (no transport) keeps defaults (runtime=30s, energy=5min, battery=30s).
        """
        if self._transport is None:
            return
        transport_type = getattr(self._transport, "transport_type", "")
        if transport_type in ("modbus_tcp", "modbus_serial"):
            ttl = timedelta(seconds=5)
        elif transport_type == "wifi_dongle":
            ttl = timedelta(seconds=30)
        else:
            return  # Keep defaults for unknown transport types
        self._runtime_cache_ttl = ttl
        self._energy_cache_ttl = ttl
        self._battery_cache_ttl = ttl
        _LOGGER.debug(
            "Set cache TTLs to %ss for %s (transport: %s)",
            ttl.total_seconds(),
            self.serial_number,
            transport_type,
        )

    # ============================================================================
    # Factory Methods
    # ============================================================================

    @classmethod
    async def from_transport(
        cls,
        transport_or_type: InverterTransport | str,
        *,
        model: str | None = None,
        **config: Any,
    ) -> BaseInverter:
        """Create an inverter from a transport or transport configuration.

        This is the unified factory method for creating transport-backed inverters.
        It accepts either an existing transport object or a connection type string
        with configuration parameters.

        Args:
            transport_or_type: Either an InverterTransport instance, or a connection
                type string ("modbus", "dongle", or "hybrid")
            model: Optional model name override. If not provided, will be
                determined from device type code.
            **config: Configuration parameters when transport_or_type is a string.
                See create_transport() for available options per connection type.

        Returns:
            Configured BaseInverter with transport-backed data

        Raises:
            TransportConnectionError: If transport fails to connect
            TransportReadError: If device type code cannot be read
            ValueError: If connection_type is invalid or required config is missing

        Examples:
            Using an existing transport:
                >>> transport = create_transport("modbus", host="192.168.1.100", ...)
                >>> inverter = await BaseInverter.from_transport(transport)

            Creating transport inline (recommended):
                >>> inverter = await BaseInverter.from_transport(
                ...     "modbus",
                ...     host="192.168.1.100",
                ...     serial="CE12345678",
                ...     port=502,
                ... )

            WiFi dongle:
                >>> inverter = await BaseInverter.from_transport(
                ...     "dongle",
                ...     host="192.168.1.100",
                ...     dongle_serial="BA12345678",
                ...     inverter_serial="CE12345678",
                ... )
        """
        # Import here to avoid circular dependency
        from pylxpweb.transports import create_transport

        # If given a string, create the transport from config
        if isinstance(transport_or_type, str):
            connection_type = transport_or_type
            if connection_type not in ("modbus", "serial", "dongle", "hybrid"):
                raise ValueError(
                    f"Invalid connection type '{connection_type}'. "
                    "Use 'modbus', 'serial', 'dongle', or 'hybrid'."
                )
            transport = create_transport(connection_type, **config)  # type: ignore[call-overload]
        else:
            transport = transport_or_type

        # Delegate to from_modbus_transport which handles the actual creation
        return await cls.from_modbus_transport(transport, model=model)

    @classmethod
    async def from_modbus_transport(
        cls,
        transport: InverterTransport,
        model: str | None = None,
    ) -> BaseInverter:
        """Create an inverter from a Modbus or Dongle transport.

        This factory method creates a BaseInverter (or appropriate subclass)
        that uses the transport for data fetching instead of HTTP API.

        The method:
        1. Connects to the transport (if not already connected)
        2. Reads device type code from register 19 to determine model family
        3. Creates appropriate inverter subclass based on family
        4. Reads initial runtime/energy data

        Args:
            transport: Modbus TCP or WiFi dongle transport (must implement
                InverterTransport protocol)
            model: Optional model name override. If not provided, will be
                determined from device type code.

        Returns:
            Configured BaseInverter (or subclass) with transport-backed data

        Raises:
            TransportConnectionError: If transport fails to connect
            TransportReadError: If device type code cannot be read

        Example:
            >>> from pylxpweb.transports import create_modbus_transport
            >>> transport = create_modbus_transport(
            ...     host="192.168.1.100",
            ...     serial="CE12345678",
            ... )
            >>> inverter = await BaseInverter.from_modbus_transport(transport)
            >>> await inverter.refresh()
            >>> print(f"SOC: {inverter.battery_soc}%")

        Note:
            Control operations (enable_quick_charge, set_ac_charge_power, etc.)
            are not available when using transport mode, as they require the
            HTTP API. Use transport mode for read-only monitoring.
        """
        # Import here to avoid circular dependency
        from pylxpweb.devices.inverters.generic import GenericInverter

        # Ensure transport is connected
        if not transport.is_connected:
            await transport.connect()

        # Read device type code from register 19 to determine model family
        device_type_code = 0
        model_family = InverterFamily.UNKNOWN
        detected_model = model

        try:
            # Read holding register 19 (HOLD_DEVICE_TYPE_CODE)
            params = await transport.read_parameters(19, 1)
            if 19 in params:
                device_type_code = params[19]

                # Check for GridBOSS/MIDbox - these are not inverters
                if device_type_code == DEVICE_TYPE_CODE_GRIDBOSS:
                    raise LuxpowerDeviceError(
                        f"Device {transport.serial} is a GridBOSS/MIDbox (device type code 50), "
                        "not an inverter. Use MIDDevice.from_transport() instead."
                    )

                model_family = DEVICE_TYPE_CODE_TO_FAMILY.get(
                    device_type_code, InverterFamily.UNKNOWN
                )
                _LOGGER.debug(
                    "Detected device type code %d -> family %s for %s",
                    device_type_code,
                    model_family.value,
                    transport.serial,
                )

                # Set model name from family if not provided
                if detected_model is None:
                    if model_family == InverterFamily.PV_SERIES:
                        detected_model = "18KPV"  # Default for PV series
                    elif model_family == InverterFamily.SNA:
                        detected_model = "12000XP"  # Default for SNA series
                    elif model_family == InverterFamily.LXP_EU:
                        detected_model = "LXP-EU"  # Default for EU series
                    else:
                        detected_model = "Unknown"
        except LuxpowerDeviceError:
            # Re-raise device errors (e.g., GridBOSS detected)
            raise
        except Exception as err:
            _LOGGER.warning(
                "Failed to read device type code for %s: %s, using defaults",
                transport.serial,
                err,
            )
            if detected_model is None:
                detected_model = "Unknown"

        # Ensure model is always set
        if detected_model is None:
            detected_model = "Unknown"

        # Update transport's inverter_family to match detected family
        # This ensures the correct register map is used for read_runtime/read_energy
        # Even if the transport was created with a different/default family
        if (
            model_family != InverterFamily.UNKNOWN
            and hasattr(transport, "inverter_family")
            and transport.inverter_family != model_family
        ):
            _LOGGER.info(
                "Auto-correcting transport family from %s to %s for %s",
                transport.inverter_family,
                model_family.value,
                transport.serial,
            )
            transport.inverter_family = model_family

        # Create a placeholder client (not used for data, only required by init)
        # In transport mode, all data comes from transport, not client
        placeholder_client: Any = None

        # Create GenericInverter with transport
        # Note: We pass None as client since transport handles all data fetching
        inverter = GenericInverter(
            client=placeholder_client,
            serial_number=transport.serial,
            model=detected_model,
            transport=transport,
        )

        # Set detected features using from_device_type_code() which applies
        # all family defaults (split_phase, three_phase_capable, etc.)
        inverter._features = InverterFeatures.from_device_type_code(device_type_code)
        inverter._features_detected = True

        _LOGGER.info(
            "Created transport-backed inverter %s (model=%s, family=%s)",
            transport.serial,
            detected_model,
            model_family.value,
        )

        return inverter

    @classmethod
    async def from_dongle_transport(
        cls,
        transport: InverterTransport,
        model: str | None = None,
    ) -> BaseInverter:
        """Create an inverter from a WiFi dongle transport.

        This is an alias for from_modbus_transport() since both methods work
        identically with any transport implementing the InverterTransport protocol.

        Args:
            transport: WiFi dongle transport (DongleTransport instance)
            model: Optional model name override. If not provided, will be
                determined from device type code.

        Returns:
            Configured BaseInverter (or subclass) with transport-backed data

        Raises:
            TransportConnectionError: If transport fails to connect
            TransportReadError: If device type code cannot be read

        Example:
            >>> from pylxpweb.transports import create_dongle_transport
            >>> transport = create_dongle_transport(
            ...     host="192.168.1.100",
            ...     dongle_serial="BA12345678",
            ...     inverter_serial="CE12345678",
            ... )
            >>> inverter = await BaseInverter.from_dongle_transport(transport)
            >>> await inverter.refresh()
            >>> print(f"SOC: {inverter.battery_soc}%")
        """
        return await cls.from_modbus_transport(transport, model=model)

    @property
    def has_transport(self) -> bool:
        """Check if this inverter uses a local transport.

        Returns:
            True if transport mode is active (Modbus/Dongle),
            False if using HTTP API.
        """
        return self._transport is not None

    async def refresh(self, force: bool = False, include_parameters: bool = False) -> None:
        """Refresh runtime, energy, battery, and optionally parameters from API.

        This method fetches data concurrently for optimal performance.
        Results are cached with different TTLs based on update frequency.

        Args:
            force: If True, bypass cache and force fresh data from API
            include_parameters: If True, also refresh parameters (default: False)
        """
        # Prepare tasks to fetch only expired/missing data
        tasks = []

        # Runtime data (30s TTL for cloud, 5s for Modbus, 30s for Dongle)
        if self._is_cache_expired(self._runtime_cache_time, self._runtime_cache_ttl, force):
            tasks.append(self._fetch_runtime())

        # Energy data (5min TTL)
        if self._is_cache_expired(self._energy_cache_time, self._energy_cache_ttl, force):
            tasks.append(self._fetch_energy())

        # Battery data (30s TTL) - Lazy loading optimization
        # Only fetch if we have batteries OR haven't checked yet (first fetch)
        if self._is_cache_expired(self._battery_cache_time, self._battery_cache_ttl, force):
            should_fetch_battery = (
                self._battery_bank is None  # Haven't checked yet
                or (self._battery_bank and self._battery_bank.battery_count > 0)  # Has batteries
            )
            if should_fetch_battery:
                tasks.append(self._fetch_battery())

        # Parameters (1hr TTL) - only fetch if explicitly requested
        if include_parameters and self._is_cache_expired(
            self._parameters_cache_time, self._parameters_cache_ttl, force
        ):
            tasks.append(self._fetch_parameters())

        # Execute all needed fetches concurrently
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._last_refresh = datetime.now()

    async def _fetch_runtime(self) -> None:
        """Fetch runtime data with caching.

        Uses transport if available, otherwise falls back to HTTP API.
        """
        async with self._runtime_cache_lock:
            try:
                if self._transport is not None:
                    # Use transport for direct local communication
                    transport_data = await self._transport.read_runtime()
                    # Store transport data directly - we'll expose via properties
                    self._transport_runtime = transport_data
                    self._runtime_cache_time = datetime.now()
                else:
                    # Use HTTP API
                    runtime_data = await self._client.api.devices.get_inverter_runtime(
                        self.serial_number
                    )
                    self._runtime = runtime_data
                    self._runtime_cache_time = datetime.now()
            except (LuxpowerAPIError, LuxpowerConnectionError, LuxpowerDeviceError) as err:
                # Keep existing cached data on API/connection errors
                _LOGGER.debug("Failed to fetch runtime data for %s: %s", self.serial_number, err)
                # Preserve existing cached data
            except Exception as err:
                # Catch transport errors as well
                _LOGGER.debug("Failed to fetch runtime data for %s: %s", self.serial_number, err)

    async def _fetch_energy(self) -> None:
        """Fetch energy data with caching.

        Uses transport if available, otherwise falls back to HTTP API.
        """
        async with self._energy_cache_lock:
            try:
                if self._transport is not None:
                    # Use transport for direct local communication
                    transport_data = await self._transport.read_energy()
                    self._transport_energy = transport_data
                    self._energy_cache_time = datetime.now()
                else:
                    # Use HTTP API
                    energy_data = await self._client.api.devices.get_inverter_energy(
                        self.serial_number
                    )
                    self._energy = energy_data
                    self._energy_cache_time = datetime.now()
            except (LuxpowerAPIError, LuxpowerConnectionError, LuxpowerDeviceError) as err:
                # Keep existing cached data on API/connection errors
                _LOGGER.debug("Failed to fetch energy data for %s: %s", self.serial_number, err)
            except Exception as err:
                # Catch transport errors as well
                _LOGGER.debug("Failed to fetch energy data for %s: %s", self.serial_number, err)

    async def _fetch_battery(self) -> None:
        """Fetch battery data with caching.

        Uses transport if available, otherwise falls back to HTTP API.
        Note: Transport returns BatteryBankData with aggregate info only
        (individual battery data requires HTTP API).
        """
        async with self._battery_cache_lock:
            try:
                if self._transport is not None:
                    # Use transport for direct local communication
                    # Transport returns aggregate BMS data from input registers
                    transport_battery = await self._transport.read_battery()
                    if transport_battery is not None:
                        # Store transport battery data in battery bank format
                        # Note: Transport doesn't have individual battery details
                        self._transport_battery = transport_battery
                    self._battery_cache_time = datetime.now()
                else:
                    # Use HTTP API for full battery details
                    battery_data = await self._client.api.devices.get_battery_info(
                        self.serial_number
                    )

                    # Create/update battery bank with aggregate data
                    await self._update_battery_bank(battery_data)

                    # Update individual batteries
                    if battery_data.batteryArray:
                        await self._update_batteries(battery_data.batteryArray)

                    self._battery_cache_time = datetime.now()
            except (LuxpowerAPIError, LuxpowerConnectionError, LuxpowerDeviceError) as err:
                # Keep existing cached data on API/connection errors
                _LOGGER.debug("Failed to fetch battery data for %s: %s", self.serial_number, err)
            except Exception as err:
                # Catch any other exceptions (e.g., ValidationError from unexpected API response)
                # Log at warning level since this indicates an unexpected issue
                _LOGGER.warning(
                    "Unexpected error fetching battery data for %s: %s (%s)",
                    self.serial_number,
                    err,
                    type(err).__name__,
                )

    async def _fetch_parameters(self) -> None:
        """Fetch all parameters with caching.

        Uses transport if available for direct Modbus register reads,
        otherwise fetches from HTTP API (3 concurrent register ranges).

        Register ranges (HTTP mode):
        - Range 1: Registers 0-126 (base parameters)
        - Range 2: Registers 127-253 (extended parameters 1)
        - Range 3: Registers 240-366 (extended parameters 2)
        """
        async with self._parameters_cache_lock:
            try:
                if self._transport is not None:
                    # Use transport for direct register reads with named parameter mapping
                    # The read_named_parameters method handles:
                    # - Reading raw register values via Modbus/Dongle
                    # - Converting register addresses to named parameter keys
                    # - Decoding bit field registers (FUNC_*, BIT_*) into individual booleans
                    all_parameters: dict[str, Any] = {}

                    # Read the full holding register range to match HTTP mode
                    # coverage. Modbus reads are cheap and local, so there's
                    # no reason to limit to a subset of registers.
                    # Max 125 registers per Modbus read (protocol limit).
                    register_groups = [
                        (0, 125),  # Registers 0-124
                        (125, 125),  # Registers 125-249
                    ]

                    for start, count in register_groups:
                        try:
                            # Use read_named_parameters to get properly decoded parameter names
                            # e.g., {"FUNC_EPS_EN": True, "FUNC_AC_CHARGE": False, ...}
                            named_params = await self._transport.read_named_parameters(start, count)
                            all_parameters.update(named_params)
                        except Exception as err:
                            _LOGGER.debug(
                                "Failed to read registers %d-%d for %s: %s",
                                start,
                                start + count,
                                self.serial_number,
                                err,
                            )

                    if all_parameters:
                        self.parameters = all_parameters
                        self._parameters_cache_time = datetime.now()
                else:
                    # Use HTTP API for full parameter access
                    range_tasks = [
                        self._client.api.control.read_parameters(
                            self.serial_number, 0, MAX_REGISTERS_PER_READ
                        ),
                        self._client.api.control.read_parameters(
                            self.serial_number, MAX_REGISTERS_PER_READ, MAX_REGISTERS_PER_READ
                        ),
                        self._client.api.control.read_parameters(
                            self.serial_number, 240, MAX_REGISTERS_PER_READ
                        ),
                    ]

                    responses = await asyncio.gather(*range_tasks, return_exceptions=True)

                    # Merge all parameter dictionaries
                    all_parameters = {}
                    for response in responses:
                        if not isinstance(response, BaseException):
                            all_parameters.update(response.parameters)

                    # Only update if we got at least some parameters
                    if all_parameters:
                        self.parameters = all_parameters
                        self._parameters_cache_time = datetime.now()
            except (LuxpowerAPIError, LuxpowerConnectionError, LuxpowerDeviceError) as err:
                # Keep existing cached data on API/connection errors
                _LOGGER.debug("Failed to fetch parameters for %s: %s", self.serial_number, err)
            except Exception as err:
                # Catch transport errors as well
                _LOGGER.debug("Failed to fetch parameters for %s: %s", self.serial_number, err)

    def to_device_info(self) -> DeviceInfo:
        """Convert to device info model.

        Returns:
            DeviceInfo with inverter metadata.
        """
        return DeviceInfo(
            identifiers={("pylxpweb", f"inverter_{self.serial_number}")},
            name=f"{self.model} {self.serial_number}",
            manufacturer="EG4/Luxpower",
            model=self.model,
            sw_version=getattr(self._runtime, "fwCode", None) if self._runtime else None,
        )

    @abstractmethod
    def to_entities(self) -> list[Entity]:
        """Generate entities for this inverter.

        Each inverter model may have different available entities based on
        hardware capabilities. Subclasses must implement this method.

        Returns:
            List of Entity objects for this inverter model.
        """
        ...

    @property
    def model(self) -> str:
        """Get inverter model name.

        Returns the human-readable model name from deviceTypeText provided
        during initialization. This is set during Station.load() from the
        inverterOverview/list API response.

        Returns:
            Inverter model name (e.g., "18KPV", "FlexBOSS21"), or "Unknown" if unavailable.
        """
        return self._model if self._model else "Unknown"

    @property
    def has_data(self) -> bool:
        """Check if inverter has valid runtime data.

        Returns:
            True if runtime data is available (HTTP or transport), False otherwise.
        """
        return self._runtime is not None or self._transport_runtime is not None

    @property
    def power_output(self) -> float | None:
        """Get current power output in watts.

        Returns:
            Current AC power output in watts, or None if unavailable.
        """
        # Check transport data first
        if self._transport_runtime is not None:
            val = self._transport_runtime.inverter_power
            return float(val) if val is not None else None

        # Fall back to HTTP data
        if self._runtime is None:
            return None
        return float(getattr(self._runtime, "pinv", 0))

    @property
    def total_energy_today(self) -> float | None:
        """Get total energy produced today in kWh.

        This is a daily value that resets at midnight (API server time).
        Home Assistant's SensorStateClass.TOTAL_INCREASING handles resets.

        Returns:
            Energy produced today in kWh, or None if unavailable.
        """
        # Check transport data first
        if self._transport_energy is not None:
            val = self._transport_energy.pv_energy_today
            return float(val) if val is not None else None

        # Fall back to HTTP data
        if self._energy is None:
            return None

        from pylxpweb.constants import scale_energy_value

        raw_value = getattr(self._energy, "todayYielding", 0)
        return scale_energy_value("todayYielding", raw_value, to_kwh=True)

    @property
    def total_energy_lifetime(self) -> float | None:
        """Get total energy produced lifetime in kWh.

        Returns:
            Total lifetime energy in kWh, or None if unavailable.
        """
        # Check transport data first
        if self._transport_energy is not None:
            val = self._transport_energy.pv_energy_total
            return float(val) if val is not None else None

        # Fall back to HTTP data
        if self._energy is None:
            return None

        from pylxpweb.constants import scale_energy_value

        raw_value = getattr(self._energy, "totalYielding", 0)
        return scale_energy_value("totalYielding", raw_value, to_kwh=True)

    @property
    def battery_soc(self) -> int | None:
        """Get battery state of charge percentage.

        Returns:
            Battery SOC (0-100), or None if no data.
        """
        # Check transport data first
        if self._transport_runtime is not None:
            val = self._transport_runtime.battery_soc
            return int(val) if val is not None else None

        # Fall back to HTTP data
        if self._runtime is None:
            return None
        return getattr(self._runtime, "soc", None)

    @property
    def battery_bank(self) -> Any | None:
        """Get battery bank with aggregate data and individual batteries.

        Returns:
            BatteryBank object with batteries list, or None if no battery data.
        """
        return self._battery_bank

    # ============================================================================
    # Additional Energy Statistics Properties
    # ============================================================================

    @property
    def energy_today_charging(self) -> float | None:
        """Get battery charging energy today in kWh.

        Returns:
            Energy charged to battery today in kWh, or None if unavailable.
        """
        if self._transport_energy is not None:
            val = self._transport_energy.charge_energy_today
            return float(val) if val is not None else None
        if self._energy is None:
            return None
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("todayCharging", self._energy.todayCharging, to_kwh=True)

    @property
    def energy_today_discharging(self) -> float | None:
        """Get battery discharging energy today in kWh.

        Returns:
            Energy discharged from battery today in kWh, or None if unavailable.
        """
        if self._transport_energy is not None:
            val = self._transport_energy.discharge_energy_today
            return float(val) if val is not None else None
        if self._energy is None:
            return None
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("todayDischarging", self._energy.todayDischarging, to_kwh=True)

    @property
    def energy_today_import(self) -> float | None:
        """Get grid import energy today in kWh.

        Returns:
            Energy imported from grid today in kWh, or None if unavailable.
        """
        if self._transport_energy is not None:
            val = self._transport_energy.grid_import_today
            return float(val) if val is not None else None
        if self._energy is None:
            return None
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("todayImport", self._energy.todayImport, to_kwh=True)

    @property
    def energy_today_export(self) -> float | None:
        """Get grid export energy today in kWh.

        Returns:
            Energy exported to grid today in kWh, or None if unavailable.
        """
        if self._transport_energy is not None:
            val = self._transport_energy.grid_export_today
            return float(val) if val is not None else None
        if self._energy is None:
            return None
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("todayExport", self._energy.todayExport, to_kwh=True)

    @property
    def energy_today_usage(self) -> float | None:
        """Get energy consumption today in kWh.

        Returns:
            Energy consumed by loads today in kWh, or None if unavailable.
        """
        if self._transport_energy is not None:
            val = self._transport_energy.load_energy_today
            return float(val) if val is not None else None
        if self._energy is None:
            return None
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("todayUsage", self._energy.todayUsage, to_kwh=True)

    @property
    def energy_lifetime_charging(self) -> float | None:
        """Get total battery charging energy lifetime in kWh.

        Returns:
            Total energy charged to battery lifetime in kWh, or None if unavailable.
        """
        if self._transport_energy is not None:
            val = self._transport_energy.charge_energy_total
            return float(val) if val is not None else None
        if self._energy is None:
            return None
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("totalCharging", self._energy.totalCharging, to_kwh=True)

    @property
    def energy_lifetime_discharging(self) -> float | None:
        """Get total battery discharging energy lifetime in kWh.

        Returns:
            Total energy discharged from battery lifetime in kWh, or None if unavailable.
        """
        if self._transport_energy is not None:
            val = self._transport_energy.discharge_energy_total
            return float(val) if val is not None else None
        if self._energy is None:
            return None
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("totalDischarging", self._energy.totalDischarging, to_kwh=True)

    @property
    def energy_lifetime_import(self) -> float | None:
        """Get total grid import energy lifetime in kWh.

        Returns:
            Total energy imported from grid lifetime in kWh, or None if unavailable.
        """
        if self._transport_energy is not None:
            val = self._transport_energy.grid_import_total
            return float(val) if val is not None else None
        if self._energy is None:
            return None
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("totalImport", self._energy.totalImport, to_kwh=True)

    @property
    def energy_lifetime_export(self) -> float | None:
        """Get total grid export energy lifetime in kWh.

        Returns:
            Total energy exported to grid lifetime in kWh, or None if unavailable.
        """
        if self._transport_energy is not None:
            val = self._transport_energy.grid_export_total
            return float(val) if val is not None else None
        if self._energy is None:
            return None
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("totalExport", self._energy.totalExport, to_kwh=True)

    @property
    def energy_lifetime_usage(self) -> float | None:
        """Get total energy consumption lifetime in kWh.

        Returns:
            Total energy consumed by loads lifetime in kWh, or None if unavailable.
        """
        if self._transport_energy is not None:
            val = self._transport_energy.load_energy_total
            return float(val) if val is not None else None
        if self._energy is None:
            return None
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("totalUsage", self._energy.totalUsage, to_kwh=True)

    async def _update_battery_bank(self, battery_info: Any) -> None:
        """Update battery bank object from API data.

        Args:
            battery_info: BatteryInfo object from API with aggregate data
        """
        from ..battery_bank import BatteryBank

        # Create or update battery bank with aggregate data
        if self._battery_bank is None:
            self._battery_bank = BatteryBank(
                client=self._client,
                inverter_serial=self.serial_number,
                battery_info=battery_info,
            )
        else:
            # Update existing battery bank data
            self._battery_bank.data = battery_info

    async def _update_batteries(self, battery_modules: list[Any]) -> None:
        """Update battery objects from API data.

        Args:
            battery_modules: List of BatteryModule objects from API
        """
        from ..battery import Battery

        # Batteries are stored in battery_bank, not directly on inverter
        if self._battery_bank is None:
            return

        # Create Battery objects for each module
        # Use batteryKey to match existing batteries or create new ones
        battery_map = {b.battery_key: b for b in self._battery_bank.batteries}
        updated_batteries = []

        for module in battery_modules:
            battery_key = module.batteryKey

            # Reuse existing Battery object or create new one
            if battery_key in battery_map:
                battery = battery_map[battery_key]
                battery.data = module  # Update data
            else:
                battery = Battery(client=self._client, battery_data=module)

            updated_batteries.append(battery)

        self._battery_bank.batteries = updated_batteries

    # ============================================================================
    # Control Operations - Universal inverter controls
    # ============================================================================

    async def read_parameters(
        self, start_register: int = 0, point_number: int = 127
    ) -> dict[str, Any]:
        """Read configuration parameters from inverter.

        .. deprecated:: 0.3.0
            Use :meth:`refresh(include_parameters=True) <refresh>` to populate
            the :attr:`parameters` property, then access parameters directly
            from :attr:`parameters` or via property accessors like
            :attr:`ac_charge_power_limit`.

        Args:
            start_register: Starting register address
            point_number: Number of registers to read

        Returns:
            Dictionary of parameter name to value mappings

        Example:
            >>> # OLD (deprecated):
            >>> params = await inverter.read_parameters(21, 1)
            >>> params["FUNC_SET_TO_STANDBY"]
            True
            >>>
            >>> # NEW (recommended):
            >>> await inverter.refresh(include_parameters=True)
            >>> inverter.parameters["FUNC_SET_TO_STANDBY"]
            True
        """
        import warnings

        warnings.warn(
            "read_parameters() is deprecated. Use refresh(include_parameters=True) "
            "to populate the 'parameters' property, then access via inverter.parameters "
            "or property accessors like inverter.ac_charge_power_limit.",
            DeprecationWarning,
            stacklevel=2,
        )

        if self._transport is not None:
            # Use transport for direct register reads
            regs = await self._transport.read_parameters(start_register, point_number)
            # Convert to named parameters (simple mapping for now)
            return {f"reg_{addr}": value for addr, value in regs.items()}
        else:
            # Use HTTP API
            response = await self._client.api.control.read_parameters(
                self.serial_number, start_register, point_number
            )
            return response.parameters

    async def write_parameters(self, parameters: dict[int, int]) -> bool:
        """Write configuration parameters to inverter.

        Uses transport for direct Modbus register writes when available,
        otherwise falls back to HTTP API.

        Args:
            parameters: Dict of register address to value

        Returns:
            True if successful

        Example:
            >>> # Set register 21 bit 9 to enable (standby off)
            >>> await inverter.write_parameters({21: 512})  # Bit 9 set
        """
        if self._transport is not None:
            # Use transport for direct register writes
            try:
                success = await self._transport.write_parameters(parameters)
                if success:
                    self._parameters_cache_time = None
                return success
            except Exception as err:
                _LOGGER.warning(
                    "Failed to write parameters via transport for %s: %s",
                    self.serial_number,
                    err,
                )
                return False
        else:
            # Use HTTP API
            response = await self._client.api.control.write_parameters(
                self.serial_number, parameters
            )

            # Invalidate parameter cache on successful write
            if response.success:
                self._parameters_cache_time = None

            return response.success

    # ============================================================================
    # Transport Control Operations - Modbus register-level control
    # ============================================================================

    async def write_transport_bit(
        self,
        register: int,
        bit: int,
        value: bool,
    ) -> bool:
        """Write a single bit in a register using read-modify-write.

        This method reads the current register value, modifies the specified bit,
        and writes the new value back. Useful for FUNC_EN (register 21) and
        SYS_FUNC (register 110) bit field operations.

        Args:
            register: Register address (e.g., 21 for FUNC_EN)
            bit: Bit position (0-15)
            value: True to set bit, False to clear bit

        Returns:
            True if successful

        Example:
            >>> # Enable AC charge (register 21, bit 7)
            >>> await inverter.write_transport_bit(21, 7, True)
            >>> # Disable forced discharge (register 21, bit 10)
            >>> await inverter.write_transport_bit(21, 10, False)

        Note:
            Only available in transport mode (Modbus/Dongle).
            For HTTP mode, use the specific control methods like enable_ac_charge().
        """
        if self._transport is None:
            _LOGGER.warning(
                "write_transport_bit() only available in transport mode for %s",
                self.serial_number,
            )
            return False

        try:
            # Read current register value
            current_values = await self._transport.read_parameters(register, 1)
            if register not in current_values:
                _LOGGER.warning("Failed to read register %d for %s", register, self.serial_number)
                return False

            current_value = current_values[register]

            # Modify the bit (set if value=True, clear if value=False)
            new_value = current_value | (1 << bit) if value else current_value & ~(1 << bit)

            # Write back if changed
            if new_value != current_value:
                success = await self._transport.write_parameters({register: new_value})
                if success:
                    _LOGGER.debug(
                        "Set register %d bit %d to %s for %s (0x%04X -> 0x%04X)",
                        register,
                        bit,
                        value,
                        self.serial_number,
                        current_value,
                        new_value,
                    )
                    self._parameters_cache_time = None
                return success
            else:
                _LOGGER.debug(
                    "Register %d bit %d already %s for %s",
                    register,
                    bit,
                    value,
                    self.serial_number,
                )
                return True  # Already in desired state

        except Exception as err:
            _LOGGER.warning(
                "Failed to write bit %d in register %d for %s: %s",
                bit,
                register,
                self.serial_number,
                err,
            )
            return False

    async def write_transport_register(
        self,
        register: int,
        value: int,
    ) -> bool:
        """Write a single register value via transport.

        Args:
            register: Register address
            value: Value to write (0-65535)

        Returns:
            True if successful

        Example:
            >>> # Set AC charge SOC limit to 95%
            >>> await inverter.write_transport_register(67, 95)
            >>> # Set on-grid SOC cutoff to 30%
            >>> await inverter.write_transport_register(105, 30)

        Note:
            Only available in transport mode (Modbus/Dongle).
        """
        if self._transport is None:
            _LOGGER.warning(
                "write_transport_register() only available in transport mode for %s",
                self.serial_number,
            )
            return False

        try:
            success = await self._transport.write_parameters({register: value})
            if success:
                _LOGGER.debug(
                    "Wrote register %d = %d (0x%04X) for %s",
                    register,
                    value,
                    value,
                    self.serial_number,
                )
                self._parameters_cache_time = None
            return success
        except Exception as err:
            _LOGGER.warning(
                "Failed to write register %d for %s: %s",
                register,
                self.serial_number,
                err,
            )
            return False

    async def read_transport_register(
        self,
        register: int,
    ) -> int | None:
        """Read a single register value via transport.

        Args:
            register: Register address

        Returns:
            Register value, or None if read failed

        Note:
            Only available in transport mode (Modbus/Dongle).
        """
        if self._transport is None:
            _LOGGER.warning(
                "read_transport_register() only available in transport mode for %s",
                self.serial_number,
            )
            return None

        try:
            values = await self._transport.read_parameters(register, 1)
            return values.get(register)
        except Exception as err:
            _LOGGER.warning(
                "Failed to read register %d for %s: %s",
                register,
                self.serial_number,
                err,
            )
            return None

    def _get_parameter(
        self,
        key: str,
        default: int | float | bool = 0,
        cast: type[int] | type[float] | type[bool] = int,
    ) -> int | float | bool | None:
        """Get parameter value from cache with default and type casting.

        This method reads from the cached `self.parameters` dictionary, which is
        populated by `refresh(include_parameters=True)` with a 1-hour TTL.

        **NO API CALLS ARE MADE** - this is purely a cache lookup.

        The cache is automatically refreshed on parameter writes and can be
        manually invalidated via `self._parameters_cache_time = None`.

        Helper method to:
        - Reduce code repetition in property accessors
        - Provide consistent default handling
        - Enable type-safe parameter access
        - Support model-specific overrides (for inverters with different mappings)

        Args:
            key: Parameter key name (e.g., "HOLD_AC_CHARGE_POWER_CMD")
            default: Default value if parameter not found or cache is empty
            cast: Type to cast the value to (int, float, or bool)

        Returns:
            Parameter value cast to specified type, default if not found,
            or None if parameters haven't been loaded yet

        Note:
            Subclasses can override this method to map standard parameter names
            to model-specific names if needed for different inverter types.

        Example:
            >>> # Cache hit (no API call)
            >>> self._get_parameter("HOLD_AC_CHARGE_POWER_CMD", 0.0, float)
            5.0
            >>> self._get_parameter("FUNC_EPS_EN", False, bool)
            True
        """
        if self.parameters is None:
            return None

        value = self.parameters.get(key, default)

        # Handle bool explicitly since bool(0) is False but we want the actual bool value
        if cast is bool and isinstance(value, bool):
            return value

        return cast(value) if value is not None else cast(default)

    async def set_standby_mode(self, standby: bool) -> bool:
        """Enable or disable standby mode.

        Universal control: All inverters support standby mode.

        Args:
            standby: True to enter standby (power off), False for normal operation

        Returns:
            True if successful

        Example:
            >>> await inverter.set_standby_mode(False)  # Power on
            True
        """
        from pylxpweb.constants import FUNC_EN_BIT_SET_TO_STANDBY, FUNC_EN_REGISTER

        # Read current function enable register
        params = await self.read_parameters(FUNC_EN_REGISTER, 1)
        current_value = params.get(f"reg_{FUNC_EN_REGISTER}", 0)

        # Bit logic: 0=Standby, 1=Power On (inverse of parameter)
        if standby:
            # Clear bit 9 to enter standby
            new_value = current_value & ~(1 << FUNC_EN_BIT_SET_TO_STANDBY)
        else:
            # Set bit 9 to power on
            new_value = current_value | (1 << FUNC_EN_BIT_SET_TO_STANDBY)

        result = await self.write_parameters({FUNC_EN_REGISTER: new_value})

        # Invalidate parameter cache on successful write
        if result:
            self._parameters_cache_time = None

        return result

    @property
    def battery_soc_limits(self) -> dict[str, int] | None:
        """Get battery SOC discharge limits from cached parameters.

        Universal control: All inverters have SOC limits.

        Returns:
            Dictionary with on_grid_limit and off_grid_limit (0-100%),
            or None if parameters haven't been loaded yet

        Example:
            >>> limits = inverter.battery_soc_limits
            >>> limits
            {'on_grid_limit': 10, 'off_grid_limit': 20}
        """
        on_grid = self._get_parameter("HOLD_DISCHG_CUT_OFF_SOC_EOD", 10, int)
        off_grid = self._get_parameter("HOLD_SOC_LOW_LIMIT_EPS_DISCHG", 10, int)

        if on_grid is None or off_grid is None:
            return None

        return {
            "on_grid_limit": int(on_grid),
            "off_grid_limit": int(off_grid),
        }

    async def set_battery_soc_limits(
        self, on_grid_limit: int | None = None, off_grid_limit: int | None = None
    ) -> bool:
        """Set battery SOC discharge limits.

        Universal control: All inverters have SOC protection.

        Args:
            on_grid_limit: On-grid discharge cutoff SOC (10-90%)
            off_grid_limit: Off-grid/EPS discharge cutoff SOC (0-100%)

        Returns:
            True if successful

        Example:
            >>> await inverter.set_battery_soc_limits(on_grid_limit=15, off_grid_limit=20)
            True
        """
        # Write each parameter individually using parameter names
        success = True

        if on_grid_limit is not None:
            if not 10 <= on_grid_limit <= 90:
                raise ValueError("on_grid_limit must be between 10 and 90%")
            result = await self._client.api.control.write_parameter(
                self.serial_number,
                "HOLD_DISCHG_CUT_OFF_SOC_EOD",
                str(on_grid_limit),
            )
            success = success and result.success

        if off_grid_limit is not None:
            if not SOC_MIN_PERCENT <= off_grid_limit <= SOC_MAX_PERCENT:
                raise ValueError(
                    f"off_grid_limit must be between {SOC_MIN_PERCENT} and {SOC_MAX_PERCENT}%"
                )
            result = await self._client.api.control.write_parameter(
                self.serial_number,
                "HOLD_SOC_LOW_LIMIT_EPS_DISCHG",
                str(off_grid_limit),
            )
            success = success and result.success

        # Invalidate parameter cache on successful write
        if success:
            self._parameters_cache_time = None

        return success

    # ============================================================================
    # Battery Backup Control (Issue #8)
    # ============================================================================

    async def enable_battery_backup(self) -> bool:
        """Enable battery backup (EPS) mode.

        Universal control: All inverters support EPS mode.

        Returns:
            True if successful

        Example:
            >>> await inverter.enable_battery_backup()
            True
        """
        result = await self._client.api.control.enable_battery_backup(self.serial_number)
        return result.success

    async def disable_battery_backup(self) -> bool:
        """Disable battery backup (EPS) mode.

        Universal control: All inverters support EPS mode.

        Returns:
            True if successful

        Example:
            >>> await inverter.disable_battery_backup()
            True
        """
        result = await self._client.api.control.disable_battery_backup(self.serial_number)
        return result.success

    async def get_battery_backup_status(self) -> bool:
        """Get current battery backup (EPS) mode status.

        Universal control: All inverters support EPS mode.

        Returns:
            True if EPS mode is enabled, False otherwise

        Example:
            >>> is_enabled = await inverter.get_battery_backup_status()
            >>> is_enabled
            True
        """
        return await self._client.api.control.get_battery_backup_status(self.serial_number)

    async def enable_battery_backup_ctrl(self) -> bool:
        """Enable battery backup control mode (working mode).

        This controls FUNC_BATTERY_BACKUP_CTRL, which is distinct from
        enable_battery_backup() which controls FUNC_EPS_EN (EPS/off-grid mode).

        Battery backup control is a working mode setting that affects how
        the inverter manages battery reserves for backup power.

        Universal control: All inverters support this working mode.

        Returns:
            True if successful

        Example:
            >>> await inverter.enable_battery_backup_ctrl()
            True
        """
        result = await self._client.api.control.enable_battery_backup_ctrl(self.serial_number)
        return result.success

    async def disable_battery_backup_ctrl(self) -> bool:
        """Disable battery backup control mode (working mode).

        This controls FUNC_BATTERY_BACKUP_CTRL, which is distinct from
        disable_battery_backup() which controls FUNC_EPS_EN (EPS/off-grid mode).

        Battery backup control is a working mode setting that affects how
        the inverter manages battery reserves for backup power.

        Universal control: All inverters support this working mode.

        Returns:
            True if successful

        Example:
            >>> await inverter.disable_battery_backup_ctrl()
            True
        """
        result = await self._client.api.control.disable_battery_backup_ctrl(self.serial_number)
        return result.success

    # ============================================================================
    # Green Mode Control (Off-Grid Mode in Web Monitor)
    # ============================================================================

    async def enable_green_mode(self) -> bool:
        """Enable green mode (off-grid mode in the web monitoring display).

        Green Mode controls the off-grid operating mode toggle visible in the
        EG4 web monitoring interface. When enabled, the inverter operates in
        an off-grid optimized configuration.

        Note: This is FUNC_GREEN_EN in register 110, distinct from FUNC_EPS_EN
        (battery backup/EPS mode) in register 21.

        Universal control: All inverters support green mode.

        Returns:
            True if successful

        Example:
            >>> await inverter.enable_green_mode()
            True
        """
        result = await self._client.api.control.enable_green_mode(self.serial_number)
        return result.success

    async def disable_green_mode(self) -> bool:
        """Disable green mode (off-grid mode in the web monitoring display).

        Green Mode controls the off-grid operating mode toggle visible in the
        EG4 web monitoring interface. When disabled, the inverter operates in
        standard grid-tied configuration.

        Note: This is FUNC_GREEN_EN in register 110, distinct from FUNC_EPS_EN
        (battery backup/EPS mode) in register 21.

        Universal control: All inverters support green mode.

        Returns:
            True if successful

        Example:
            >>> await inverter.disable_green_mode()
            True
        """
        result = await self._client.api.control.disable_green_mode(self.serial_number)
        return result.success

    async def get_green_mode_status(self) -> bool:
        """Get current green mode (off-grid mode) status.

        Green Mode controls the off-grid operating mode toggle visible in the
        EG4 web monitoring interface.

        Universal control: All inverters support green mode.

        Returns:
            True if green mode is enabled, False otherwise

        Example:
            >>> is_enabled = await inverter.get_green_mode_status()
            >>> is_enabled
            True
        """
        return await self._client.api.control.get_green_mode_status(self.serial_number)

    @property
    def green_mode_enabled(self) -> bool | None:
        """Get green mode status from cached parameters.

        Green Mode controls the off-grid operating mode toggle visible in the
        EG4 web monitoring interface.

        Returns:
            True if green mode is enabled, False if disabled,
            or None if parameters not loaded

        Example:
            >>> enabled = inverter.green_mode_enabled
            >>> enabled
            True
        """
        value = self._get_parameter("FUNC_GREEN_EN", False, bool)
        return bool(value) if value is not None else None

    # ============================================================================
    # AC Charge Power Control (Issue #9)
    # ============================================================================

    async def set_ac_charge_power(self, power_kw: float) -> bool:
        """Set AC charge power limit.

        Universal control: All inverters support AC charging.

        Args:
            power_kw: Power limit in kilowatts (0.0 to 15.0)

        Returns:
            True if successful

        Raises:
            ValueError: If power_kw is out of valid range

        Example:
            >>> await inverter.set_ac_charge_power(5.0)
            True
        """
        if not 0.0 <= power_kw <= 15.0:
            raise ValueError(f"AC charge power must be between 0.0 and 15.0 kW, got {power_kw}")

        # API accepts kW values directly
        result = await self._client.api.control.write_parameter(
            self.serial_number, "HOLD_AC_CHARGE_POWER_CMD", str(power_kw)
        )

        # Invalidate parameter cache on successful write
        if result.success:
            self._parameters_cache_time = None

        return result.success

    @property
    def ac_charge_power_limit(self) -> float | None:
        """Get current AC charge power limit from cached parameters.

        Universal control: All inverters support AC charging.

        Returns:
            Current power limit in kilowatts, or None if parameters not loaded

        Example:
            >>> power = inverter.ac_charge_power_limit
            >>> power
            5.0
        """
        value = self._get_parameter("HOLD_AC_CHARGE_POWER_CMD", 0.0, float)
        return float(value) if value is not None else None

    # ============================================================================
    # PV Charge Power Control (Issue #10)
    # ============================================================================

    async def set_pv_charge_power(self, power_kw: int) -> bool:
        """Set PV (forced) charge power limit.

        Universal control: All inverters support PV charging.

        Args:
            power_kw: Power limit in kilowatts (0 to 15, integer values only)

        Returns:
            True if successful

        Raises:
            ValueError: If power_kw is out of valid range

        Example:
            >>> await inverter.set_pv_charge_power(10)
            True
        """
        if not 0 <= power_kw <= 15:
            raise ValueError(f"PV charge power must be between 0 and 15 kW, got {power_kw}")

        # API accepts integer kW values directly
        result = await self._client.api.control.write_parameter(
            self.serial_number, "HOLD_FORCED_CHG_POWER_CMD", str(power_kw)
        )

        # Invalidate parameter cache on successful write
        if result.success:
            self._parameters_cache_time = None

        return result.success

    @property
    def pv_charge_power_limit(self) -> int | None:
        """Get current PV (forced) charge power limit from cached parameters.

        Universal control: All inverters support PV charging.

        Returns:
            Current power limit in kilowatts (integer), or None if parameters not loaded

        Example:
            >>> power = inverter.pv_charge_power_limit
            >>> power
            10
        """
        value = self._get_parameter("HOLD_FORCED_CHG_POWER_CMD", 0, int)
        return int(value) if value is not None else None

    # ============================================================================
    # Grid Peak Shaving Control (Issue #11)
    # ============================================================================

    async def set_grid_peak_shaving_power(self, power_kw: float) -> bool:
        """Set grid peak shaving power limit.

        Universal control: Most inverters support peak shaving.

        Args:
            power_kw: Power limit in kilowatts (0.0 to 25.5)

        Returns:
            True if successful

        Raises:
            ValueError: If power_kw is out of valid range

        Example:
            >>> await inverter.set_grid_peak_shaving_power(7.0)
            True
        """
        if not 0.0 <= power_kw <= 25.5:
            raise ValueError(
                f"Grid peak shaving power must be between 0.0 and 25.5 kW, got {power_kw}"
            )

        # API accepts kW values directly
        result = await self._client.api.control.write_parameter(
            self.serial_number, "_12K_HOLD_GRID_PEAK_SHAVING_POWER", str(power_kw)
        )

        # Invalidate parameter cache on successful write
        if result.success:
            self._parameters_cache_time = None

        return result.success

    @property
    def grid_peak_shaving_power_limit(self) -> float | None:
        """Get current grid peak shaving power limit from cached parameters.

        Universal control: Most inverters support peak shaving.

        Returns:
            Current power limit in kilowatts, or None if parameters not loaded

        Example:
            >>> power = inverter.grid_peak_shaving_power_limit
            >>> power
            7.0
        """
        value = self._get_parameter("_12K_HOLD_GRID_PEAK_SHAVING_POWER", 0.0, float)
        return float(value) if value is not None else None

    # ============================================================================
    # AC Charge SOC Limit Control (Issue #12)
    # ============================================================================

    async def set_ac_charge_soc_limit(self, soc_percent: int) -> bool:
        """Set AC charge stop SOC limit (when to stop AC charging).

        Universal control: All inverters support AC charge SOC limits.

        Args:
            soc_percent: SOC percentage (0 to 100)

        Returns:
            True if successful

        Raises:
            ValueError: If soc_percent is out of valid range (0-100)

        Example:
            >>> await inverter.set_ac_charge_soc_limit(90)
            True
        """
        if not 0 <= soc_percent <= 100:
            raise ValueError(f"AC charge SOC limit must be between 0 and 100%, got {soc_percent}")

        result = await self._client.api.control.write_parameter(
            self.serial_number, "HOLD_AC_CHARGE_SOC_LIMIT", str(soc_percent)
        )

        # Invalidate parameter cache on successful write
        if result.success:
            self._parameters_cache_time = None

        return result.success

    @property
    def ac_charge_soc_limit(self) -> int | None:
        """Get current AC charge stop SOC limit from cached parameters.

        Universal control: All inverters support AC charge SOC limits.

        Returns:
            Current SOC limit percentage (0-100), or None if parameters not loaded
            or parameter not found

        Example:
            >>> limit = inverter.ac_charge_soc_limit
            >>> limit
            90
        """
        if self.parameters is None:
            return None
        value = self.parameters.get("HOLD_AC_CHARGE_SOC_LIMIT")
        if value is None:
            return None
        try:
            int_value = int(value)
            return int_value if 0 <= int_value <= 100 else None
        except (ValueError, TypeError):
            return None

    @property
    def system_charge_soc_limit(self) -> int | None:
        """Get current system charge SOC limit from cached parameters.

        This controls when the battery stops charging:
        - 0-100%: Stop charging when battery reaches this SOC
        - 101%: Enable top balancing (full charge with cell balancing)

        Universal control: All inverters support system charge SOC limits.

        Returns:
            Current SOC limit percentage (0-101), or None if parameters not loaded
            or parameter not found

        Example:
            >>> limit = inverter.system_charge_soc_limit
            >>> limit
            80
        """
        if self.parameters is None:
            return None
        value = self.parameters.get("HOLD_SYSTEM_CHARGE_SOC_LIMIT")
        if value is None:
            return None
        try:
            int_value = int(value)
            return int_value if 0 <= int_value <= 101 else None
        except (ValueError, TypeError):
            return None

    # ============================================================================
    # Battery Current Control (Issue #13)
    # ============================================================================

    async def set_battery_charge_current(self, current_amps: int) -> bool:
        """Set battery charge current limit.

        Universal control: All inverters support charge current limits.

        Args:
            current_amps: Current limit in amperes (0 to 250)

        Returns:
            True if successful

        Raises:
            ValueError: If current_amps is out of valid range

        Example:
            >>> await inverter.set_battery_charge_current(100)
            True
        """
        result = await self._client.api.control.set_battery_charge_current(
            self.serial_number, current_amps
        )

        # Invalidate parameter cache on successful write
        if result.success:
            self._parameters_cache_time = None

        return result.success

    async def set_battery_discharge_current(self, current_amps: int) -> bool:
        """Set battery discharge current limit.

        Universal control: All inverters support discharge current limits.

        Args:
            current_amps: Current limit in amperes (0 to 250)

        Returns:
            True if successful

        Raises:
            ValueError: If current_amps is out of valid range

        Example:
            >>> await inverter.set_battery_discharge_current(120)
            True
        """
        result = await self._client.api.control.set_battery_discharge_current(
            self.serial_number, current_amps
        )

        # Invalidate parameter cache on successful write
        if result.success:
            self._parameters_cache_time = None

        return result.success

    @property
    def battery_charge_current_limit(self) -> int | None:
        """Get current battery charge current limit from cached parameters.

        Universal control: All inverters support charge current limits.

        Returns:
            Current limit in amperes, or None if parameters not loaded

        Example:
            >>> current = inverter.battery_charge_current_limit
            >>> current
            100
        """
        value = self._get_parameter("HOLD_LEAD_ACID_CHARGE_RATE", 0, int)
        return int(value) if value is not None else None

    @property
    def battery_discharge_current_limit(self) -> int | None:
        """Get current battery discharge current limit from cached parameters.

        Universal control: All inverters support discharge current limits.

        Returns:
            Current limit in amperes, or None if parameters not loaded

        Example:
            >>> current = inverter.battery_discharge_current_limit
            >>> current
            120
        """
        value = self._get_parameter("HOLD_LEAD_ACID_DISCHARGE_RATE", 0, int)
        return int(value) if value is not None else None

    # ============================================================================
    # Discharge Power Control
    # ============================================================================

    @property
    def discharge_power_limit(self) -> int | None:
        """Get current discharge power limit from cached parameters.

        Universal control: All inverters support discharge power limits.

        Returns:
            Discharge power limit as percentage (0-100%), or None if not loaded
            or parameter not found

        Example:
            >>> power = inverter.discharge_power_limit
            >>> power
            100
        """
        if self.parameters is None:
            return None
        value = self.parameters.get("HOLD_DISCHG_POWER_PERCENT_CMD")
        if value is None:
            return None
        try:
            int_value = int(value)
            return int_value if 0 <= int_value <= 100 else None
        except (ValueError, TypeError):
            return None

    # ============================================================================
    # Battery Voltage Limits
    # ============================================================================

    @property
    def battery_voltage_limits(self) -> dict[str, float] | None:
        """Get battery voltage limits from cached parameters.

        Universal control: All inverters have battery voltage protection.

        Returns:
            Dictionary with voltage limits in volts, or None if not loaded:
            - max_charge_voltage: Maximum charge voltage (V)
            - min_charge_voltage: Minimum charge voltage (V)
            - max_discharge_voltage: Maximum discharge voltage (V)
            - min_discharge_voltage: Minimum discharge voltage (V)

        Example:
            >>> limits = inverter.battery_voltage_limits
            >>> limits
            {'max_charge_voltage': 58.4, 'min_charge_voltage': 48.0,
             'max_discharge_voltage': 57.6, 'min_discharge_voltage': 46.0}
        """
        # Return None if parameters not loaded yet
        if self.parameters is None:
            return None

        # Check if all required params are present
        required_keys = [
            "HOLD_BAT_VOLT_MAX_CHG",
            "HOLD_BAT_VOLT_MIN_CHG",
            "HOLD_BAT_VOLT_MAX_DISCHG",
            "HOLD_BAT_VOLT_MIN_DISCHG",
        ]
        if not all(key in self.parameters for key in required_keys):
            return None

        # Get values directly from parameters dict (already validated as present)
        # Battery voltage values are stored as V * 100, so divide by 100
        max_chg = self.parameters.get("HOLD_BAT_VOLT_MAX_CHG", 0)
        min_chg = self.parameters.get("HOLD_BAT_VOLT_MIN_CHG", 0)
        max_dischg = self.parameters.get("HOLD_BAT_VOLT_MAX_DISCHG", 0)
        min_dischg = self.parameters.get("HOLD_BAT_VOLT_MIN_DISCHG", 0)

        return {
            "max_charge_voltage": float(max_chg) / 100.0,
            "min_charge_voltage": float(min_chg) / 100.0,
            "max_discharge_voltage": float(max_dischg) / 100.0,
            "min_discharge_voltage": float(min_dischg) / 100.0,
        }

    # ============================================================================
    # Operating Mode Control (Issue #14)
    # ============================================================================

    async def set_operating_mode(self, mode: OperatingMode) -> bool:
        """Set inverter operating mode.

        Valid operating modes:
        - NORMAL: Normal operation (power on)
        - STANDBY: Standby mode (power off)

        Note: Quick Charge and Quick Discharge are not operating modes,
        they are separate functions that can be enabled/disabled independently.

        Args:
            mode: Operating mode (NORMAL or STANDBY)

        Returns:
            True if successful

        Example:
            >>> from pylxpweb.models import OperatingMode
            >>> await inverter.set_operating_mode(OperatingMode.NORMAL)
            True
            >>> await inverter.set_operating_mode(OperatingMode.STANDBY)
            True
        """
        # Import here to avoid circular dependency
        from pylxpweb.models import OperatingMode as OM

        standby = mode == OM.STANDBY
        result = await self.set_standby_mode(standby)

        # Invalidate parameter cache on successful write
        if result:
            self._parameters_cache_time = None

        return result

    async def get_operating_mode(self) -> OperatingMode:
        """Get current operating mode.

        Returns:
            Current operating mode (NORMAL or STANDBY)

        Example:
            >>> from pylxpweb.models import OperatingMode
            >>> mode = await inverter.get_operating_mode()
            >>> mode
            <OperatingMode.NORMAL: 'normal'>
        """
        # Import here to avoid circular dependency
        from pylxpweb.models import OperatingMode as OM

        # Read FUNC_EN register bit 9 (FUNC_EN_BIT_SET_TO_STANDBY)
        # 0 = Standby, 1 = Normal (Power On)
        params = await self.read_parameters(21, 1)
        func_en = params.get("FUNC_EN_REGISTER", 0)

        # Bit 9: 0=Standby, 1=Normal
        is_standby = not bool((func_en >> 9) & 1)

        return OM.STANDBY if is_standby else OM.NORMAL

    # ============================================================================
    # Quick Charge Control (Issue #14)
    # ============================================================================

    async def enable_quick_charge(self) -> bool:
        """Enable quick charge function.

        Quick charge is a function control (not an operating mode) that
        can be active alongside Normal or Standby operating modes.

        Returns:
            True if successful

        Example:
            >>> await inverter.enable_quick_charge()
            True
        """
        result = await self._client.api.control.start_quick_charge(self.serial_number)
        return result.success

    async def disable_quick_charge(self) -> bool:
        """Disable quick charge function.

        Returns:
            True if successful

        Example:
            >>> await inverter.disable_quick_charge()
            True
        """
        result = await self._client.api.control.stop_quick_charge(self.serial_number)
        return result.success

    async def get_quick_charge_status(self) -> bool:
        """Get quick charge function status.

        Returns:
            True if quick charge is active, False otherwise

        Example:
            >>> is_active = await inverter.get_quick_charge_status()
            >>> is_active
            False
        """
        status = await self._client.api.control.get_quick_charge_status(self.serial_number)
        return status.hasUnclosedQuickChargeTask

    # ============================================================================
    # Quick Discharge Control (Issue #14)
    # ============================================================================

    async def enable_quick_discharge(self) -> bool:
        """Enable quick discharge function.

        Quick discharge is a function control (not an operating mode) that
        can be active alongside Normal or Standby operating modes.

        Note: There is no status endpoint for quick discharge, unlike quick charge.

        Returns:
            True if successful

        Example:
            >>> await inverter.enable_quick_discharge()
            True
        """
        result = await self._client.api.control.start_quick_discharge(self.serial_number)
        return result.success

    async def disable_quick_discharge(self) -> bool:
        """Disable quick discharge function.

        Returns:
            True if successful

        Example:
            >>> await inverter.disable_quick_discharge()
            True
        """
        result = await self._client.api.control.stop_quick_discharge(self.serial_number)
        return result.success

    async def get_quick_discharge_status(self) -> bool:
        """Get quick discharge function status.

        Note: Uses the quickCharge/getStatusInfo endpoint which returns status
        for both quick charge and quick discharge operations.

        Returns:
            True if quick discharge is active, False otherwise

        Example:
            >>> is_active = await inverter.get_quick_discharge_status()
            >>> is_active
            False
        """
        status = await self._client.api.control.get_quick_charge_status(self.serial_number)
        return status.hasUnclosedQuickDischargeTask

    # ============================================================================
    # Working Mode Controls (Issue #16)
    # ============================================================================

    async def enable_ac_charge_mode(self) -> bool:
        """Enable AC charge mode to allow battery charging from grid.

        Universal control: All inverters support AC charging.

        Returns:
            True if successful

        Example:
            >>> await inverter.enable_ac_charge_mode()
            True
        """
        result = await self._client.api.control.enable_ac_charge_mode(self.serial_number)
        return result.success

    async def disable_ac_charge_mode(self) -> bool:
        """Disable AC charge mode.

        Universal control: All inverters support AC charging.

        Returns:
            True if successful

        Example:
            >>> await inverter.disable_ac_charge_mode()
            True
        """
        result = await self._client.api.control.disable_ac_charge_mode(self.serial_number)
        return result.success

    async def get_ac_charge_mode_status(self) -> bool:
        """Get current AC charge mode status.

        Universal control: All inverters support AC charging.

        Returns:
            True if AC charge mode is enabled, False otherwise

        Example:
            >>> is_enabled = await inverter.get_ac_charge_mode_status()
            >>> is_enabled
            True
        """
        return await self._client.api.control.get_ac_charge_mode_status(self.serial_number)

    async def enable_pv_charge_priority(self) -> bool:
        """Enable PV charge priority mode during specified hours.

        Universal control: All inverters support forced charge.

        Returns:
            True if successful

        Example:
            >>> await inverter.enable_pv_charge_priority()
            True
        """
        result = await self._client.api.control.enable_pv_charge_priority(self.serial_number)
        return result.success

    async def disable_pv_charge_priority(self) -> bool:
        """Disable PV charge priority mode.

        Universal control: All inverters support forced charge.

        Returns:
            True if successful

        Example:
            >>> await inverter.disable_pv_charge_priority()
            True
        """
        result = await self._client.api.control.disable_pv_charge_priority(self.serial_number)
        return result.success

    async def get_pv_charge_priority_status(self) -> bool:
        """Get current PV charge priority status.

        Universal control: All inverters support forced charge.

        Returns:
            True if PV charge priority is enabled, False otherwise

        Example:
            >>> is_enabled = await inverter.get_pv_charge_priority_status()
            >>> is_enabled
            True
        """
        return await self._client.api.control.get_pv_charge_priority_status(self.serial_number)

    async def enable_forced_discharge(self) -> bool:
        """Enable forced discharge mode for grid export.

        Universal control: All inverters support forced discharge.

        Returns:
            True if successful

        Example:
            >>> await inverter.enable_forced_discharge()
            True
        """
        result = await self._client.api.control.enable_forced_discharge(self.serial_number)
        return result.success

    async def disable_forced_discharge(self) -> bool:
        """Disable forced discharge mode.

        Universal control: All inverters support forced discharge.

        Returns:
            True if successful

        Example:
            >>> await inverter.disable_forced_discharge()
            True
        """
        result = await self._client.api.control.disable_forced_discharge(self.serial_number)
        return result.success

    async def get_forced_discharge_status(self) -> bool:
        """Get current forced discharge status.

        Universal control: All inverters support forced discharge.

        Returns:
            True if forced discharge is enabled, False otherwise

        Example:
            >>> is_enabled = await inverter.get_forced_discharge_status()
            >>> is_enabled
            True
        """
        return await self._client.api.control.get_forced_discharge_status(self.serial_number)

    async def enable_peak_shaving_mode(self) -> bool:
        """Enable grid peak shaving mode.

        Universal control: Most inverters support peak shaving.

        Returns:
            True if successful

        Example:
            >>> await inverter.enable_peak_shaving_mode()
            True
        """
        result = await self._client.api.control.enable_peak_shaving_mode(self.serial_number)
        return result.success

    async def disable_peak_shaving_mode(self) -> bool:
        """Disable grid peak shaving mode.

        Universal control: Most inverters support peak shaving.

        Returns:
            True if successful

        Example:
            >>> await inverter.disable_peak_shaving_mode()
            True
        """
        result = await self._client.api.control.disable_peak_shaving_mode(self.serial_number)
        return result.success

    async def get_peak_shaving_mode_status(self) -> bool:
        """Get current peak shaving mode status.

        Universal control: Most inverters support peak shaving.

        Returns:
            True if peak shaving mode is enabled, False otherwise

        Example:
            >>> is_enabled = await inverter.get_peak_shaving_mode_status()
            >>> is_enabled
            True
        """
        return await self._client.api.control.get_peak_shaving_mode_status(self.serial_number)

    # ============================================================================
    # Feature Detection (Model-Based Capabilities)
    # ============================================================================

    async def detect_features(self, force: bool = False) -> InverterFeatures:
        """Detect inverter features and capabilities.

        This method uses a multi-layer approach to determine what features
        are available on this specific inverter:

        1. **Device Type Code**: Read HOLD_DEVICE_TYPE_CODE (register 19) to
           identify the model family (SNA, PV Series, LXP-EU, etc.)

        2. **Model Info**: Decode HOLD_MODEL (registers 0-1) for hardware
           configuration (power rating, battery type, US/EU version)

        3. **Family Defaults**: Apply known feature sets for the model family

        4. **Runtime Probing**: Check for optional registers that may or may
           not exist on specific firmware versions

        Feature detection results are cached. Use `force=True` to re-detect.

        Args:
            force: If True, re-detect features even if already cached

        Returns:
            InverterFeatures with all detected capabilities

        Example:
            >>> features = await inverter.detect_features()
            >>> features.model_family
            <InverterFamily.SNA: 'SNA'>
            >>> features.split_phase
            True
            >>> features.supports_volt_watt_curve
            False
        """
        if self._features_detected and not force:
            return self._features

        # Ensure parameters are loaded (needed for feature detection)
        if self.parameters is None:
            await self._fetch_parameters()

        if self.parameters is None:
            _LOGGER.warning(
                "Cannot detect features for %s: parameters not available",
                self.serial_number,
            )
            return self._features

        # Layer 1: Get device type code
        device_type_code = self.parameters.get("HOLD_DEVICE_TYPE_CODE", 0)
        if isinstance(device_type_code, str):
            device_type_code = int(device_type_code)

        # Create features from device type code (applies family defaults)
        self._features = InverterFeatures.from_device_type_code(device_type_code)

        # Layer 2: Decode model info from HOLD_MODEL_* parameters
        # The API returns individual decoded fields like HOLD_MODEL_lithiumType
        self._features.model_info = InverterModelInfo.from_parameters(self.parameters)

        # Layer 3: Runtime probing for optional features
        await self._probe_optional_features()

        self._features_detected = True
        _LOGGER.debug(
            "Detected features for %s: family=%s, grid_type=%s",
            self.serial_number,
            self._features.model_family.value,
            self._features.grid_type.value,
        )

        return self._features

    async def _probe_optional_features(self) -> None:
        """Probe for optional features by checking for specific registers.

        This method checks for registers that may or may not be present
        depending on firmware version or hardware variant.
        """
        if self.parameters is None:
            return

        # Check for SNA-specific registers
        # SNA models have discharge recovery hysteresis parameters
        has_recovery_lag = "HOLD_DISCHG_RECOVERY_LAG_SOC" in self.parameters
        has_quick_charge = "SNA_HOLD_QUICK_CHARGE_MINUTE" in self.parameters
        if has_recovery_lag or has_quick_charge:
            self._features.has_sna_registers = True
            self._features.discharge_recovery_hysteresis = True

        # Check for PV series registers (volt-watt curve parameters)
        if "_12K_HOLD_GRID_PEAK_SHAVING_POWER" in self.parameters:
            self._features.has_pv_series_registers = True
            self._features.grid_peak_shaving = True

        # Check for volt-watt curve support
        if "HOLD_VW_V1" in self.parameters or "HOLD_VOLT_WATT_V1" in self.parameters:
            self._features.volt_watt_curve = True

        # Check for DRMS support
        if "FUNC_DRMS_EN" in self.parameters:
            drms_val = self.parameters.get("FUNC_DRMS_EN")
            # DRMS is available if the parameter exists (regardless of value)
            self._features.drms_support = drms_val is not None

    # ============================================================================
    # Feature Properties (Read-Only Capability Flags)
    # ============================================================================

    @property
    def features(self) -> InverterFeatures:
        """Get detected inverter features.

        Note: Call `detect_features()` first to populate feature data.
        If features haven't been detected yet, returns default features.

        Returns:
            InverterFeatures instance with capability flags

        Example:
            >>> await inverter.detect_features()
            >>> inverter.features.split_phase
            True
        """
        return self._features

    @property
    def model_family(self) -> InverterFamily:
        """Get the inverter model family.

        Returns:
            InverterFamily enum value (SNA, PV_SERIES, LXP_EU, etc.)

        Example:
            >>> await inverter.detect_features()
            >>> inverter.model_family
            <InverterFamily.SNA: 'SNA'>
        """
        return self._features.model_family

    @property
    def device_type_code(self) -> int:
        """Get the device type code from HOLD_DEVICE_TYPE_CODE register.

        This is the firmware-level model identifier that varies per model:
        - SNA12K-US: 54
        - 18KPV: 2092
        - LXP-EU 12K: 12

        Returns:
            Device type code integer

        Example:
            >>> await inverter.detect_features()
            >>> inverter.device_type_code
            54
        """
        return self._features.device_type_code

    @property
    def grid_type(self) -> GridType:
        """Get the grid configuration type.

        Returns:
            GridType enum value (SPLIT_PHASE, SINGLE_PHASE, THREE_PHASE)

        Example:
            >>> await inverter.detect_features()
            >>> inverter.grid_type
            <GridType.SPLIT_PHASE: 'split_phase'>
        """
        return self._features.grid_type

    @property
    def power_rating_kw(self) -> int:
        """Get the nominal power rating in kilowatts.

        Decoded from HOLD_MODEL register.

        Returns:
            Power rating in kW, or 0 if unknown

        Example:
            >>> await inverter.detect_features()
            >>> inverter.power_rating_kw
            12
        """
        return self._features.model_info.power_rating_kw

    @property
    def is_us_version(self) -> bool:
        """Check if this is a US market version.

        Decoded from HOLD_MODEL register.

        Returns:
            True if US version, False for EU/other

        Example:
            >>> await inverter.detect_features()
            >>> inverter.is_us_version
            True
        """
        return self._features.model_info.us_version

    @property
    def supports_split_phase(self) -> bool:
        """Check if inverter supports split-phase grid configuration.

        Split-phase is the standard US residential configuration (120V/240V).

        Returns:
            True if split-phase is supported

        Example:
            >>> await inverter.detect_features()
            >>> inverter.supports_split_phase
            True
        """
        return self._features.split_phase

    @property
    def supports_three_phase(self) -> bool:
        """Check if inverter supports three-phase grid configuration.

        Returns:
            True if three-phase is supported

        Example:
            >>> await inverter.detect_features()
            >>> inverter.supports_three_phase
            False
        """
        return self._features.three_phase_capable

    @property
    def supports_off_grid(self) -> bool:
        """Check if inverter supports off-grid (EPS) mode.

        Returns:
            True if off-grid/EPS mode is supported

        Example:
            >>> await inverter.detect_features()
            >>> inverter.supports_off_grid
            True
        """
        return self._features.off_grid_capable

    @property
    def supports_parallel(self) -> bool:
        """Check if inverter supports parallel operation with other inverters.

        Returns:
            True if parallel operation is supported

        Example:
            >>> await inverter.detect_features()
            >>> inverter.supports_parallel
            False
        """
        return self._features.parallel_support

    @property
    def supports_volt_watt_curve(self) -> bool:
        """Check if inverter supports volt-watt curve settings.

        Returns:
            True if volt-watt curve is supported

        Example:
            >>> await inverter.detect_features()
            >>> inverter.supports_volt_watt_curve
            False
        """
        return self._features.volt_watt_curve

    @property
    def supports_grid_peak_shaving(self) -> bool:
        """Check if inverter supports grid peak shaving.

        Returns:
            True if grid peak shaving is supported

        Example:
            >>> await inverter.detect_features()
            >>> inverter.supports_grid_peak_shaving
            True
        """
        return self._features.grid_peak_shaving

    @property
    def supports_drms(self) -> bool:
        """Check if inverter supports DRMS (Demand Response Management).

        Returns:
            True if DRMS is supported

        Example:
            >>> await inverter.detect_features()
            >>> inverter.supports_drms
            False
        """
        return self._features.drms_support

    @property
    def supports_discharge_recovery_hysteresis(self) -> bool:
        """Check if inverter supports discharge recovery hysteresis settings.

        This feature allows setting SOC/voltage lag values for discharge
        recovery, preventing oscillation when SOC is near the cutoff threshold.

        SNA series inverters have this feature.

        Returns:
            True if discharge recovery hysteresis is supported

        Example:
            >>> await inverter.detect_features()
            >>> inverter.supports_discharge_recovery_hysteresis
            True
        """
        return self._features.discharge_recovery_hysteresis

    # ============================================================================
    # Model-Specific Parameter Access
    # ============================================================================

    @property
    def discharge_recovery_lag_soc(self) -> int | None:
        """Get discharge recovery SOC hysteresis value (SNA models only).

        This setting prevents rapid on/off cycling when battery SOC is near
        the discharge cutoff threshold. The inverter waits until SOC rises
        by this amount before resuming discharge.

        Returns:
            SOC hysteresis percentage, or None if not supported/loaded

        Example:
            >>> await inverter.detect_features()
            >>> if inverter.supports_discharge_recovery_hysteresis:
            ...     print(f"Lag SOC: {inverter.discharge_recovery_lag_soc}%")
        """
        if not self._features.discharge_recovery_hysteresis:
            return None
        value = self._get_parameter("HOLD_DISCHG_RECOVERY_LAG_SOC", 0, int)
        return int(value) if value is not None else None

    @property
    def discharge_recovery_lag_volt(self) -> float | None:
        """Get discharge recovery voltage hysteresis value (SNA models only).

        This setting prevents rapid on/off cycling when battery voltage is
        near the discharge cutoff threshold. The inverter waits until voltage
        rises by this amount before resuming discharge.

        Returns:
            Voltage hysteresis in volts, or None if not supported/loaded

        Example:
            >>> await inverter.detect_features()
            >>> if inverter.supports_discharge_recovery_hysteresis:
            ...     print(f"Lag Voltage: {inverter.discharge_recovery_lag_volt}V")
        """
        if not self._features.discharge_recovery_hysteresis:
            return None
        value = self._get_parameter("HOLD_DISCHG_RECOVERY_LAG_VOLT", 0, float)
        return float(value) / 10.0 if value is not None else None  # Scaled by 10

    @property
    def quick_charge_minute(self) -> int | None:
        """Get quick charge duration in minutes (SNA models only).

        This setting controls how long quick charge runs when activated.

        Returns:
            Quick charge duration in minutes, or None if not supported/loaded

        Example:
            >>> await inverter.detect_features()
            >>> if inverter.features.quick_charge_minute:
            ...     print(f"Quick charge: {inverter.quick_charge_minute} min")
        """
        if not self._features.quick_charge_minute:
            return None
        value = self._get_parameter("SNA_HOLD_QUICK_CHARGE_MINUTE", 0, int)
        return int(value) if value is not None else None
