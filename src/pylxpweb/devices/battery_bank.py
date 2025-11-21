"""Battery bank module for aggregate battery monitoring.

This module provides the BatteryBank class that represents the aggregate
battery system data (total capacity, charge/discharge power, overall status)
for all batteries connected to an inverter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BaseDevice
from .models import DeviceInfo, Entity

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient
    from pylxpweb.models import BatteryInfo

    from .battery import Battery


class BatteryBank(BaseDevice):
    """Represents the aggregate battery bank for an inverter.

    This class provides aggregate information for all batteries connected
    to an inverter, including total capacity, charge/discharge power, and
    overall status.

    Example:
        ```python
        # BatteryBank is typically created from BatteryInfo API response
        battery_info = await client.api.devices.get_battery_info(serial_num)

        battery_bank = BatteryBank(
            client=client,
            inverter_serial=serial_num,
            battery_info=battery_info
        )

        print(f"Battery Bank Status: {battery_bank.status}")
        print(f"Total Capacity: {battery_bank.max_capacity} Ah")
        print(f"Current Capacity: {battery_bank.current_capacity} Ah")
        print(f"SOC: {battery_bank.soc}%")
        print(f"Charge Power: {battery_bank.charge_power}W")
        ```
    """

    def __init__(
        self,
        client: LuxpowerClient,
        inverter_serial: str,
        battery_info: BatteryInfo,
    ) -> None:
        """Initialize battery bank.

        Args:
            client: LuxpowerClient instance for API access
            inverter_serial: Serial number of parent inverter
            battery_info: BatteryInfo data from API
        """
        # Use inverter serial + "_battery_bank" as unique ID
        super().__init__(client, f"{inverter_serial}_battery_bank", "Battery Bank")

        self.inverter_serial = inverter_serial
        self.data = battery_info

        # Individual battery modules in this bank
        self.batteries: list[Battery] = []  # Will be Battery objects

    @property
    def status(self) -> str:
        """Get battery bank charging status.

        Returns:
            Status string (e.g., "Charging", "Discharging", "Idle").
        """
        return self.data.batStatus

    @property
    def soc(self) -> int:
        """Get aggregate state of charge for battery bank.

        Returns:
            State of charge percentage (0-100).
        """
        return self.data.soc

    @property
    def voltage(self) -> float:
        """Get battery bank voltage in volts.

        Returns:
            Battery voltage (scaled from vBat ÷10).
        """
        return float(self.data.vBat) / 10.0

    @property
    def charge_power(self) -> int:
        """Get total charging power in watts.

        Returns:
            Charging power in watts.
        """
        return self.data.pCharge

    @property
    def discharge_power(self) -> int:
        """Get total discharging power in watts.

        Returns:
            Discharging power in watts.
        """
        return self.data.pDisCharge

    @property
    def max_capacity(self) -> int:
        """Get maximum battery bank capacity in amp-hours.

        Returns:
            Maximum capacity in Ah.
        """
        return self.data.maxBatteryCharge

    @property
    def current_capacity(self) -> float:
        """Get current battery bank capacity in amp-hours.

        Returns:
            Current capacity in Ah.
        """
        return self.data.currentBatteryCharge

    @property
    def battery_count(self) -> int:
        """Get number of batteries in the bank.

        Returns:
            Number of battery modules.
        """
        return len(self.data.batteryArray)

    async def refresh(self) -> None:
        """Refresh battery bank data.

        Note: Battery bank data is refreshed through the parent inverter.
        This method is a no-op for battery banks.
        """
        # Battery bank data comes from inverter's getBatteryInfo call
        # Individual battery banks don't have their own refresh endpoint
        pass

    def to_device_info(self) -> DeviceInfo:
        """Convert to device info model.

        Note: BatteryBank entities are not currently exposed to Home Assistant.
        Aggregate battery data is available through inverter sensors.
        This method is preserved for potential future use.

        Returns:
            DeviceInfo with battery bank metadata.
        """
        return DeviceInfo(
            identifiers={("pylxpweb", f"battery_bank_{self.inverter_serial}")},
            name=f"Battery Bank ({self.inverter_serial})",
            manufacturer="EG4/Luxpower",
            model=f"Battery Bank ({self.battery_count} modules)",
            via_device=("pylxpweb", f"inverter_{self.inverter_serial}"),
        )

    def to_entities(self) -> list[Entity]:
        """Generate entities for this battery bank.

        Note: BatteryBank entities are not currently generated for Home Assistant
        to avoid excessive entity proliferation. Aggregate battery data is available
        through inverter sensors, and individual battery data is available through
        Battery entities.

        This method is preserved for potential future use if aggregate battery
        entities are needed.

        Returns:
            Empty list (entities not currently generated).
        """
        # Return empty list - BatteryBank entities not needed for HA integration
        # Aggregate data is accessible via inverter sensors
        # Individual battery data is accessible via Battery entities
        return []
