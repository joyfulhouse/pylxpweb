"""ParallelGroup class for inverters in parallel operation.

This module provides the ParallelGroup class that represents a group of
inverters operating in parallel, optionally with a MID (GridBOSS) device.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient
    from pylxpweb.models import EnergyInfo

    from .inverters.base import BaseInverter
    from .mid_device import MIDDevice
    from .station import Station


class ParallelGroup:
    """Represents a group of inverters operating in parallel.

    In the Luxpower/EG4 system, multiple inverters can operate in parallel
    to increase total power capacity. The parallel group may include:
    - Multiple inverters (2 or more)
    - Optional MID device (GridBOSS) for grid management

    Example:
        ```python
        # Access parallel groups from station
        station = await client.get_station(plant_id)

        for group in station.parallel_groups:
            print(f"Group {group.name}: {len(group.inverters)} inverters")

            if group.mid_device:
                print(f"  GridBOSS: {group.mid_device.serial_number}")

            for inverter in group.inverters:
                await inverter.refresh()
                print(f"  Inverter {inverter.serial_number}: {inverter.ac_output_power}W")
        ```
    """

    def __init__(
        self,
        client: LuxpowerClient,
        station: Station,
        name: str,
        first_device_serial: str,
    ) -> None:
        """Initialize parallel group.

        Args:
            client: LuxpowerClient instance for API access
            station: Parent station object
            name: Group identifier (typically "A", "B", etc.)
            first_device_serial: Serial number of first device in group
        """
        self._client = client
        self.station = station
        self.name = name
        self.first_device_serial = first_device_serial

        # Device collections (loaded by factory methods)
        self.inverters: list[BaseInverter] = []
        self.mid_device: MIDDevice | None = None

        # Energy data (private - use properties for access)
        self._energy: EnergyInfo | None = None

    async def refresh(self) -> None:
        """Refresh runtime data for all devices in group.

        This refreshes:
        - All inverters in the group
        - MID device if present
        - Parallel group energy data
        """
        import asyncio

        tasks = []

        # Refresh all inverters (all inverters have refresh method)
        for inverter in self.inverters:
            tasks.append(inverter.refresh())

        # Refresh MID device (check for None, mid_device always has refresh method)
        if self.mid_device:
            tasks.append(self.mid_device.refresh())

        # Fetch parallel group energy data if we have inverters
        if self.inverters:
            first_serial = self.inverters[0].serial_number
            tasks.append(self._fetch_energy_data(first_serial))

        # Execute concurrently
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _fetch_energy_data(self, serial_number: str) -> None:
        """Fetch parallel group energy data.

        Args:
            serial_number: Serial number of first inverter in group.
        """
        import logging

        from pylxpweb.exceptions import LuxpowerAPIError, LuxpowerConnectionError

        _logger = logging.getLogger(__name__)

        try:
            self._energy = await self._client.api.devices.get_parallel_energy(serial_number)
            _logger.debug(
                "Parallel group %s energy data fetched: todayYielding=%s",
                self.name,
                self._energy.todayYielding if self._energy else None,
            )
        except (LuxpowerAPIError, LuxpowerConnectionError) as e:
            # Keep existing cached data on error, but log the failure
            _logger.warning(
                "Failed to fetch parallel group %s energy data: %s",
                self.name,
                e,
            )

    async def get_combined_energy(self) -> dict[str, float]:
        """Get combined energy statistics for all inverters in group.

        Uses the parallel group energy endpoint which returns aggregate data
        for the entire parallel group instead of summing individual inverters.

        Returns:
            Dictionary with 'today_kwh' and 'lifetime_kwh' totals.

        Raises:
            ValueError: If no inverters in the group to query
        """
        if not self.inverters:
            return {
                "today_kwh": 0.0,
                "lifetime_kwh": 0.0,
            }

        # Use first inverter serial to query parallel group energy
        # The API returns aggregate data for the entire group
        first_serial = self.inverters[0].serial_number
        energy_info = await self._client.api.devices.get_parallel_energy(first_serial)

        # Energy values are in units of 0.1 kWh, divide by 10 for kWh
        return {
            "today_kwh": energy_info.todayYielding / 10,
            "lifetime_kwh": energy_info.totalYielding / 10,
        }

    # ===========================================
    # Energy Properties - Today
    # ===========================================
    # Daily energy values reset at midnight (API server time).
    # The client automatically invalidates cache on hour boundaries
    # to minimize stale data, but cannot control API reset timing.

    @property
    def today_yielding(self) -> float:
        """Get today's PV generation in kWh.

        This value resets daily at midnight (API-controlled timing).
        The client invalidates cache on hour boundaries, but values
        shortly after midnight may reflect stale API data.

        For Home Assistant: Use SensorStateClass.TOTAL_INCREASING
        to let HA's statistics handle resets automatically.

        Returns:
            Today's yielding (÷10 for kWh), or 0.0 if no data.
        """
        if self._energy is None:
            return 0.0
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("todayYielding", self._energy.todayYielding, to_kwh=True)

    @property
    def today_charging(self) -> float:
        """Get today's battery charging energy in kWh.

        Returns:
            Today's charging (÷10 for kWh), or 0.0 if no data.
        """
        if self._energy is None:
            return 0.0
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("todayCharging", self._energy.todayCharging, to_kwh=True)

    @property
    def today_discharging(self) -> float:
        """Get today's battery discharging energy in kWh.

        Returns:
            Today's discharging (÷10 for kWh), or 0.0 if no data.
        """
        if self._energy is None:
            return 0.0
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("todayDischarging", self._energy.todayDischarging, to_kwh=True)

    @property
    def today_import(self) -> float:
        """Get today's grid import energy in kWh.

        Returns:
            Today's import (÷10 for kWh), or 0.0 if no data.
        """
        if self._energy is None:
            return 0.0
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("todayImport", self._energy.todayImport, to_kwh=True)

    @property
    def today_export(self) -> float:
        """Get today's grid export energy in kWh.

        Returns:
            Today's export (÷10 for kWh), or 0.0 if no data.
        """
        if self._energy is None:
            return 0.0
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("todayExport", self._energy.todayExport, to_kwh=True)

    @property
    def today_usage(self) -> float:
        """Get today's energy usage in kWh.

        Returns:
            Today's usage (÷10 for kWh), or 0.0 if no data.
        """
        if self._energy is None:
            return 0.0
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("todayUsage", self._energy.todayUsage, to_kwh=True)

    # ===========================================
    # Energy Properties - Total (Lifetime)
    # ===========================================

    @property
    def total_yielding(self) -> float:
        """Get total lifetime PV generation in kWh.

        Returns:
            Total yielding (÷10 for kWh), or 0.0 if no data.
        """
        if self._energy is None:
            return 0.0
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("totalYielding", self._energy.totalYielding, to_kwh=True)

    @property
    def total_charging(self) -> float:
        """Get total lifetime battery charging energy in kWh.

        Returns:
            Total charging (÷10 for kWh), or 0.0 if no data.
        """
        if self._energy is None:
            return 0.0
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("totalCharging", self._energy.totalCharging, to_kwh=True)

    @property
    def total_discharging(self) -> float:
        """Get total lifetime battery discharging energy in kWh.

        Returns:
            Total discharging (÷10 for kWh), or 0.0 if no data.
        """
        if self._energy is None:
            return 0.0
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("totalDischarging", self._energy.totalDischarging, to_kwh=True)

    @property
    def total_import(self) -> float:
        """Get total lifetime grid import energy in kWh.

        Returns:
            Total import (÷10 for kWh), or 0.0 if no data.
        """
        if self._energy is None:
            return 0.0
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("totalImport", self._energy.totalImport, to_kwh=True)

    @property
    def total_export(self) -> float:
        """Get total lifetime grid export energy in kWh.

        Returns:
            Total export (÷10 for kWh), or 0.0 if no data.
        """
        if self._energy is None:
            return 0.0
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("totalExport", self._energy.totalExport, to_kwh=True)

    @property
    def total_usage(self) -> float:
        """Get total lifetime energy usage in kWh.

        Returns:
            Total usage (÷10 for kWh), or 0.0 if no data.
        """
        if self._energy is None:
            return 0.0
        from pylxpweb.constants import scale_energy_value

        return scale_energy_value("totalUsage", self._energy.totalUsage, to_kwh=True)

    # ===========================================
    # Aggregate Battery Properties
    # ===========================================
    # These properties aggregate battery data from all inverters in the group.
    # Data is calculated from each inverter's battery_bank, not from a single API call.

    @property
    def battery_charge_power(self) -> int:
        """Get total battery charging power across all inverters in watts.

        Aggregates charge_power from all inverters' battery banks.

        Returns:
            Total charging power in watts, or 0 if no battery data.
        """
        total = 0
        for inverter in self.inverters:
            if inverter.battery_bank:
                total += inverter.battery_bank.charge_power or 0
        return total

    @property
    def battery_discharge_power(self) -> int:
        """Get total battery discharging power across all inverters in watts.

        Aggregates discharge_power from all inverters' battery banks.

        Returns:
            Total discharging power in watts, or 0 if no battery data.
        """
        total = 0
        for inverter in self.inverters:
            if inverter.battery_bank:
                total += inverter.battery_bank.discharge_power or 0
        return total

    @property
    def battery_power(self) -> int:
        """Get net battery power across all inverters in watts.

        Positive = charging, negative = discharging.
        Aggregates battery_power from all inverters' battery banks.

        Returns:
            Net battery power in watts, or 0 if no battery data.
        """
        total = 0
        for inverter in self.inverters:
            if inverter.battery_bank and inverter.battery_bank.battery_power is not None:
                total += inverter.battery_bank.battery_power
        return total

    @property
    def battery_soc(self) -> float:
        """Get weighted average state of charge across all batteries.

        SOC is calculated as: (total current capacity / total max capacity) * 100
        This provides a capacity-weighted average rather than a simple average,
        which is more accurate when batteries have different capacities.

        Returns:
            Weighted average SOC percentage (0-100), or 0.0 if no battery data.
        """
        total_current = 0.0
        total_max = 0.0

        for inverter in self.inverters:
            if inverter.battery_bank:
                current = inverter.battery_bank.current_capacity or 0
                max_cap = inverter.battery_bank.max_capacity or 0
                total_current += current
                total_max += max_cap

        if total_max > 0:
            return round((total_current / total_max) * 100, 1)
        return 0.0

    @property
    def battery_max_capacity(self) -> int:
        """Get total maximum battery capacity across all inverters in Ah.

        Aggregates max_capacity from all inverters' battery banks.

        Returns:
            Total maximum capacity in Ah, or 0 if no battery data.
        """
        total = 0
        for inverter in self.inverters:
            if inverter.battery_bank:
                total += inverter.battery_bank.max_capacity or 0
        return total

    @property
    def battery_current_capacity(self) -> float:
        """Get total current battery capacity across all inverters in Ah.

        Aggregates current_capacity from all inverters' battery banks.

        Returns:
            Total current capacity in Ah, or 0.0 if no battery data.
        """
        total = 0.0
        for inverter in self.inverters:
            if inverter.battery_bank:
                total += inverter.battery_bank.current_capacity or 0
        return round(total, 1)

    @property
    def battery_voltage(self) -> float | None:
        """Get average battery voltage across all inverters.

        Returns the average voltage from all battery banks. Returns None
        if no battery data is available.

        Returns:
            Average battery voltage in volts, or None if no battery data.
        """
        voltages: list[float] = []
        for inverter in self.inverters:
            if inverter.battery_bank:
                voltage = inverter.battery_bank.voltage
                if voltage is not None and voltage > 0:
                    voltages.append(voltage)

        if voltages:
            return round(sum(voltages) / len(voltages), 1)
        return None

    @property
    def battery_count(self) -> int:
        """Get total number of batteries across all inverters.

        Aggregates battery_count from all inverters' battery banks.

        Returns:
            Total number of battery modules, or 0 if no battery data.
        """
        total = 0
        for inverter in self.inverters:
            if inverter.battery_bank:
                total += inverter.battery_bank.battery_count or 0
        return total

    @classmethod
    async def from_api_data(
        cls,
        client: LuxpowerClient,
        station: Station,
        group_data: dict[str, Any],
    ) -> ParallelGroup:
        """Factory method to create ParallelGroup from API data.

        Args:
            client: LuxpowerClient instance
            station: Parent station object
            group_data: API response data for parallel group

        Returns:
            ParallelGroup instance with devices loaded.
        """
        # Extract group info
        name = group_data.get("parallelGroup", "A")
        first_serial = group_data.get("parallelFirstDeviceSn", "")

        # Create group
        group = cls(
            client=client,
            station=station,
            name=name,
            first_device_serial=first_serial,
        )

        # Note: Inverters and MID device will be loaded by Station._load_devices()
        # This is because device creation requires model-specific inverter classes
        # which will be implemented in Phase 2

        return group
