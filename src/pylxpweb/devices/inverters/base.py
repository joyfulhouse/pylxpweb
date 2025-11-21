"""Base inverter class for all inverter types.

This module provides the BaseInverter abstract class that all model-specific
inverter implementations must inherit from.
"""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from pylxpweb.models import OperatingMode

from ..base import BaseDevice
from ..models import DeviceInfo, Entity

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient
    from pylxpweb.models import EnergyInfo, InverterRuntime


class BaseInverter(BaseDevice):
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
    ) -> None:
        """Initialize inverter.

        Args:
            client: LuxpowerClient instance for API access
            serial_number: Inverter serial number (10-digit)
            model: Inverter model name (e.g., "FlexBOSS21", "18KPV")
        """
        super().__init__(client, serial_number, model)

        # Runtime data (refreshed frequently)
        self.runtime: InverterRuntime | None = None

        # Energy data (refreshed less frequently)
        self.energy: EnergyInfo | None = None

        # Battery bank (contains aggregate data and individual batteries)
        self.battery_bank: Any | None = None  # Will be BatteryBank object

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
        task_types = []

        now = datetime.now()

        # Runtime data (30s TTL)
        runtime_expired = (
            force
            or self._runtime_cache_time is None
            or (now - self._runtime_cache_time) > self._runtime_cache_ttl
        )
        if runtime_expired:
            tasks.append(self._fetch_runtime())
            task_types.append("runtime")

        # Energy data (5min TTL)
        energy_expired = (
            force
            or self._energy_cache_time is None
            or (now - self._energy_cache_time) > self._energy_cache_ttl
        )
        if energy_expired:
            tasks.append(self._fetch_energy())
            task_types.append("energy")

        # Battery data (30s TTL)
        battery_expired = (
            force
            or self._battery_cache_time is None
            or (now - self._battery_cache_time) > self._battery_cache_ttl
        )
        if battery_expired:
            tasks.append(self._fetch_battery())
            task_types.append("battery")

        # Parameters (1hr TTL) - only fetch if explicitly requested or expired
        parameters_expired = (
            force
            or self._parameters_cache_time is None
            or (now - self._parameters_cache_time) > self._parameters_cache_ttl
        )
        if include_parameters and parameters_expired:
            tasks.append(self._fetch_parameters())
            task_types.append("parameters")

        # Execute all needed fetches concurrently
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._last_refresh = datetime.now()

    async def _fetch_runtime(self) -> None:
        """Fetch runtime data with caching."""
        async with self._runtime_cache_lock:
            try:
                runtime_data = await self._client.api.devices.get_inverter_runtime(
                    self.serial_number
                )
                self.runtime = runtime_data
                self._runtime_cache_time = datetime.now()
            except Exception:
                # Keep existing cached data on error
                pass

    async def _fetch_energy(self) -> None:
        """Fetch energy data with caching."""
        async with self._energy_cache_lock:
            try:
                energy_data = await self._client.api.devices.get_inverter_energy(self.serial_number)
                self.energy = energy_data
                self._energy_cache_time = datetime.now()
            except Exception:
                # Keep existing cached data on error
                pass

    async def _fetch_battery(self) -> None:
        """Fetch battery data with caching."""
        async with self._battery_cache_lock:
            try:
                battery_data = await self._client.api.devices.get_battery_info(self.serial_number)

                # Create/update battery bank with aggregate data
                await self._update_battery_bank(battery_data)

                # Update individual batteries
                if battery_data.batteryArray:
                    await self._update_batteries(battery_data.batteryArray)

                self._battery_cache_time = datetime.now()
            except Exception:
                # Keep existing cached data on error
                pass

    async def _fetch_parameters(self) -> None:
        """Fetch all parameters with caching.

        Fetches parameters from all 3 register ranges concurrently:
        - Range 1: Registers 0-126 (base parameters)
        - Range 2: Registers 127-253 (extended parameters 1)
        - Range 3: Registers 240-366 (extended parameters 2)
        """
        async with self._parameters_cache_lock:
            try:
                # Fetch all 3 register ranges concurrently
                range_tasks = [
                    self._client.api.control.read_parameters(self.serial_number, 0, 127),
                    self._client.api.control.read_parameters(self.serial_number, 127, 127),
                    self._client.api.control.read_parameters(self.serial_number, 240, 127),
                ]

                responses = await asyncio.gather(*range_tasks, return_exceptions=True)

                # Merge all parameter dictionaries
                all_parameters: dict[str, Any] = {}
                for response in responses:
                    if not isinstance(response, BaseException):
                        all_parameters.update(response.parameters)

                # Only update if we got at least some parameters
                if all_parameters:
                    self.parameters = all_parameters
                    self._parameters_cache_time = datetime.now()
            except Exception:
                # Keep existing cached data on error
                pass

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
            sw_version=getattr(self.runtime, "fwCode", None) if self.runtime else None,
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
            True if runtime data is available, False otherwise.
        """
        return self.runtime is not None

    @property
    def power_output(self) -> float:
        """Get current power output in watts.

        Returns:
            Current AC power output in watts, or 0.0 if no data.
        """
        if self.runtime is None:
            return 0.0
        return float(getattr(self.runtime, "pinv", 0))

    @property
    def total_energy_today(self) -> float:
        """Get total energy produced today in kWh.

        Returns:
            Energy produced today in kWh, or 0.0 if no data.
        """
        if self.energy is None:
            return 0.0
        # todayYielding is in Wh, divide by 1000 for kWh
        return float(getattr(self.energy, "todayYielding", 0)) / 1000.0

    @property
    def total_energy_lifetime(self) -> float:
        """Get total energy produced lifetime in kWh.

        Returns:
            Total lifetime energy in kWh, or 0.0 if no data.
        """
        if self.energy is None:
            return 0.0
        # totalYielding is in Wh, divide by 1000 for kWh
        return float(getattr(self.energy, "totalYielding", 0)) / 1000.0

    @property
    def battery_soc(self) -> int | None:
        """Get battery state of charge percentage.

        Returns:
            Battery SOC (0-100), or None if no data.
        """
        if self.runtime is None:
            return None
        return getattr(self.runtime, "soc", None)

    async def _update_battery_bank(self, battery_info: Any) -> None:
        """Update battery bank object from API data.

        Args:
            battery_info: BatteryInfo object from API with aggregate data
        """
        from ..battery_bank import BatteryBank

        # Create or update battery bank with aggregate data
        if self.battery_bank is None:
            self.battery_bank = BatteryBank(
                client=self._client,
                inverter_serial=self.serial_number,
                battery_info=battery_info,
            )
        else:
            # Update existing battery bank data
            self.battery_bank.data = battery_info

    async def _update_batteries(self, battery_modules: list[Any]) -> None:
        """Update battery objects from API data.

        Args:
            battery_modules: List of BatteryModule objects from API
        """
        from ..battery import Battery

        # Batteries are stored in battery_bank, not directly on inverter
        if self.battery_bank is None:
            return

        # Create Battery objects for each module
        # Use batteryKey to match existing batteries or create new ones
        battery_map = {b.battery_key: b for b in self.battery_bank.batteries}
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

        self.battery_bank.batteries = updated_batteries

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

        response = await self._client.api.control.read_parameters(
            self.serial_number, start_register, point_number
        )
        return response.parameters

    async def write_parameters(self, parameters: dict[int, int]) -> bool:
        """Write configuration parameters to inverter.

        Args:
            parameters: Dict of register address to value

        Returns:
            True if successful

        Example:
            >>> # Set register 21 bit 9 to enable (standby off)
            >>> await inverter.write_parameters({21: 512})  # Bit 9 set
        """
        response = await self._client.api.control.write_parameters(self.serial_number, parameters)

        # Invalidate parameter cache on successful write
        if response.success:
            self._parameters_cache_time = None

        return response.success

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
    def battery_soc_limits(self) -> dict[str, int]:
        """Get battery SOC discharge limits from cached parameters.

        Universal control: All inverters have SOC limits.

        Returns:
            Dictionary with on_grid_limit and off_grid_limit (0-100%)

        Example:
            >>> limits = inverter.battery_soc_limits
            >>> limits
            {'on_grid_limit': 10, 'off_grid_limit': 20}
        """
        if self.parameters is None:
            return {"on_grid_limit": 10, "off_grid_limit": 10}

        return {
            "on_grid_limit": int(self.parameters.get("HOLD_DISCHG_CUT_OFF_SOC_EOD", 10)),
            "off_grid_limit": int(self.parameters.get("HOLD_SOC_LOW_LIMIT_EPS_DISCHG", 10)),
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
            if not 0 <= off_grid_limit <= 100:
                raise ValueError("off_grid_limit must be between 0 and 100%")
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
    def ac_charge_power_limit(self) -> float:
        """Get current AC charge power limit from cached parameters.

        Universal control: All inverters support AC charging.

        Returns:
            Current power limit in kilowatts

        Example:
            >>> power = inverter.ac_charge_power_limit
            >>> power
            5.0
        """
        if self.parameters is None:
            return 0.0
        value = self.parameters.get("HOLD_AC_CHARGE_POWER_CMD", 0.0)
        # API returns kW values directly
        return float(value)

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
    def pv_charge_power_limit(self) -> int:
        """Get current PV (forced) charge power limit from cached parameters.

        Universal control: All inverters support PV charging.

        Returns:
            Current power limit in kilowatts (integer)

        Example:
            >>> power = inverter.pv_charge_power_limit
            >>> power
            10
        """
        if self.parameters is None:
            return 0
        value = self.parameters.get("HOLD_FORCED_CHG_POWER_CMD", 0)
        # API returns integer kW values directly
        return int(value)

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
    def grid_peak_shaving_power_limit(self) -> float:
        """Get current grid peak shaving power limit from cached parameters.

        Universal control: Most inverters support peak shaving.

        Returns:
            Current power limit in kilowatts

        Example:
            >>> power = inverter.grid_peak_shaving_power_limit
            >>> power
            7.0
        """
        if self.parameters is None:
            return 0.0
        value = self.parameters.get("_12K_HOLD_GRID_PEAK_SHAVING_POWER", 0.0)
        # API returns kW values directly
        return float(value)

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
    def ac_charge_soc_limit(self) -> int:
        """Get current AC charge stop SOC limit from cached parameters.

        Universal control: All inverters support AC charge SOC limits.

        Returns:
            Current SOC limit percentage

        Example:
            >>> limit = inverter.ac_charge_soc_limit
            >>> limit
            90
        """
        if self.parameters is None:
            return 100
        return int(self.parameters.get("HOLD_AC_CHARGE_SOC_LIMIT", 100))

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
    def battery_charge_current_limit(self) -> int:
        """Get current battery charge current limit from cached parameters.

        Universal control: All inverters support charge current limits.

        Returns:
            Current limit in amperes

        Example:
            >>> current = inverter.battery_charge_current_limit
            >>> current
            100
        """
        if self.parameters is None:
            return 0
        return int(self.parameters.get("HOLD_LEAD_ACID_CHARGE_RATE", 0))

    @property
    def battery_discharge_current_limit(self) -> int:
        """Get current battery discharge current limit from cached parameters.

        Universal control: All inverters support discharge current limits.

        Returns:
            Current limit in amperes

        Example:
            >>> current = inverter.battery_discharge_current_limit
            >>> current
            120
        """
        if self.parameters is None:
            return 0
        return int(self.parameters.get("HOLD_LEAD_ACID_DISCHARGE_RATE", 0))

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
