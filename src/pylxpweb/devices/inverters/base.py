"""Base inverter class for all inverter types.

This module provides the BaseInverter abstract class that all model-specific
inverter implementations must inherit from.
"""

from __future__ import annotations

from abc import abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any

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

    async def refresh(self) -> None:
        """Refresh runtime, energy, and battery data from API.

        This method fetches runtime, energy, and battery data concurrently
        for optimal performance.
        """
        import asyncio

        # Fetch all data concurrently
        runtime_task = self._client.api.devices.get_inverter_runtime(self.serial_number)
        energy_task = self._client.api.devices.get_inverter_energy(self.serial_number)
        battery_task = self._client.api.devices.get_battery_info(self.serial_number)

        runtime_data, energy_data, battery_data = await asyncio.gather(
            runtime_task, energy_task, battery_task, return_exceptions=True
        )

        # Update runtime if successful
        if not isinstance(runtime_data, BaseException):
            self.runtime = runtime_data

        # Update energy if successful
        if not isinstance(energy_data, BaseException):
            self.energy = energy_data

        # Update batteries and battery bank if successful
        if not isinstance(battery_data, BaseException):
            # Create/update battery bank with aggregate data
            await self._update_battery_bank(battery_data)

            # Update individual batteries
            if battery_data.batteryArray:
                await self._update_batteries(battery_data.batteryArray)

        self._last_refresh = datetime.now()

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

        Args:
            start_register: Starting register address
            point_number: Number of registers to read

        Returns:
            Dictionary of parameter name to value mappings

        Example:
            >>> params = await inverter.read_parameters(21, 1)
            >>> params["FUNC_SET_TO_STANDBY"]
            True
        """
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

        return await self.write_parameters({FUNC_EN_REGISTER: new_value})

    async def get_battery_soc_limits(self) -> dict[str, int]:
        """Get battery SOC discharge limits.

        Universal control: All inverters have SOC limits.

        Returns:
            Dictionary with on_grid_limit and off_grid_limit (0-100%)

        Example:
            >>> limits = await inverter.get_battery_soc_limits()
            >>> limits
            {'on_grid_limit': 10, 'off_grid_limit': 20}
        """

        params = await self.read_parameters(105, 2)
        return {
            "on_grid_limit": params.get("HOLD_DISCHG_CUT_OFF_SOC_EOD", 10),
            "off_grid_limit": params.get("HOLD_SOC_LOW_LIMIT_EPS_DISCHG", 10),
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
        from pylxpweb.constants import HOLD_DISCHG_CUT_OFF_SOC_EOD, HOLD_SOC_LOW_LIMIT_EPS_DISCHG

        params_to_write = {}

        if on_grid_limit is not None:
            if not 10 <= on_grid_limit <= 90:
                raise ValueError("on_grid_limit must be between 10 and 90%")
            params_to_write[HOLD_DISCHG_CUT_OFF_SOC_EOD] = on_grid_limit

        if off_grid_limit is not None:
            if not 0 <= off_grid_limit <= 100:
                raise ValueError("off_grid_limit must be between 0 and 100%")
            params_to_write[HOLD_SOC_LOW_LIMIT_EPS_DISCHG] = off_grid_limit

        if not params_to_write:
            return True

        return await self.write_parameters(params_to_write)
