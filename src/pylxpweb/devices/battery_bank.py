"""Battery bank module for aggregate battery monitoring.

This module provides the BatteryBank class that represents the aggregate
battery system data (total capacity, charge/discharge power, overall status)
for all batteries connected to an inverter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pylxpweb.constants import ScaleFactor, apply_scale

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

    # ========== Status Properties ==========

    @property
    def status(self) -> str:
        """Get battery bank charging status.

        Returns:
            Status string (e.g., "Charging", "Discharging", "Idle").
        """
        return self.data.batStatus

    @property
    def status_text(self) -> str | None:
        """Get detailed status text.

        Returns:
            Detailed status text, or None if not available.
        """
        return self.data.statusText

    @property
    def is_lost(self) -> bool:
        """Check if battery communication is lost.

        Returns:
            True if battery is not communicating, False otherwise.
        """
        return self.data.lost if self.data.lost is not None else False

    @property
    def has_runtime_data(self) -> bool:
        """Check if runtime data is available.

        Returns:
            True if runtime data is available, False otherwise.
        """
        return self.data.hasRuntimeData if self.data.hasRuntimeData is not None else False

    # ========== State of Charge ==========

    @property
    def soc(self) -> int:
        """Get aggregate state of charge for battery bank.

        Returns:
            State of charge percentage (0-100).
        """
        return self.data.soc

    # ========== Voltage Properties ==========

    @property
    def voltage(self) -> float:
        """Get battery bank voltage in volts.

        Returns:
            Battery voltage (scaled from vBat ÷10).
        """
        return apply_scale(self.data.vBat, ScaleFactor.SCALE_10)

    @property
    def voltage_text(self) -> str | None:
        """Get formatted voltage text.

        Returns:
            Voltage text (e.g., "53.8V"), or None if not available.
        """
        return self.data.totalVoltageText

    # ========== Power Properties ==========

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
    def battery_power(self) -> int | None:
        """Get net battery power in watts (positive = charging, negative = discharging).

        Returns:
            Net battery power in watts, or None if not available.
        """
        return self.data.batPower

    @property
    def pv_power(self) -> int | None:
        """Get PV solar power in watts.

        Returns:
            PV power in watts, or None if not available.
        """
        return self.data.ppv

    @property
    def inverter_power(self) -> int | None:
        """Get inverter power in watts.

        Returns:
            Inverter power in watts, or None if not available.
        """
        return self.data.pinv

    @property
    def grid_power(self) -> int | None:
        """Get grid power in watts.

        Returns:
            Grid power in watts, or None if not available.
        """
        return self.data.prec

    @property
    def eps_power(self) -> int | None:
        """Get EPS/backup power in watts.

        Returns:
            EPS power in watts, or None if not available.
        """
        return self.data.peps

    # ========== Capacity Properties ==========

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
            Current capacity in Ah, rounded to 1 decimal place.
        """
        return round(self.data.currentBatteryCharge, 1)

    @property
    def remain_capacity(self) -> int | None:
        """Get remaining capacity in amp-hours.

        Returns:
            Remaining capacity in Ah, or None if not available.
        """
        return self.data.remainCapacity

    @property
    def full_capacity(self) -> int | None:
        """Get full capacity in amp-hours.

        Returns:
            Full capacity in Ah, or None if not available.
        """
        return self.data.fullCapacity

    @property
    def capacity_percent(self) -> int | None:
        """Get capacity percentage.

        Returns:
            Capacity percentage (0-100), or None if not available.
        """
        return self.data.capacityPercent

    # ========== Current Properties ==========

    @property
    def current_text(self) -> str | None:
        """Get formatted current text.

        Returns:
            Current text (e.g., "49.8A"), or None if not available.
        """
        return self.data.currentText

    @property
    def current_type(self) -> str | None:
        """Get current flow direction.

        Returns:
            "charge" or "discharge", or None if not available.
        """
        return self.data.currentType

    # ========== Battery Count ==========

    @property
    def battery_count(self) -> int:
        """Get number of batteries in the bank.

        Returns:
            Number of battery modules.
        """
        if self.data.totalNumber is not None:
            return self.data.totalNumber
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
