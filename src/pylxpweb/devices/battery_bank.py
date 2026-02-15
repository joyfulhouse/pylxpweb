"""Battery bank module for aggregate battery monitoring.

This module provides the BatteryBank class that represents the aggregate
battery system data (total capacity, charge/discharge power, overall status)
for all batteries connected to an inverter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pylxpweb.constants import ScaleFactor, apply_scale

from .base import BaseDevice
from .models import DeviceInfo, Entity

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient
    from pylxpweb.models import BatteryInfo

    from .battery import Battery
    from .inverters.base import BaseInverter


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
        bat_parallel_num: int | None = None,
        inverter: BaseInverter | None = None,
    ) -> None:
        """Initialize battery bank.

        Args:
            client: LuxpowerClient instance for API access
            inverter_serial: Serial number of parent inverter
            battery_info: BatteryInfo data from API
            bat_parallel_num: Battery count from runtime data (more reliable than
                totalNumber for LXP-EU devices where CAN bus BMS communication
                may fail and return 0)
            inverter: Parent inverter reference for accessing transport runtime data.
                When provided, real-time properties (charge_power, discharge_power,
                voltage, soc) will use transport data when available for faster updates.
        """
        # Use inverter serial + "_battery_bank" as unique ID
        super().__init__(client, f"{inverter_serial}_battery_bank", "Battery Bank")

        self.inverter_serial = inverter_serial
        self.data = battery_info

        # Cache batParallelNum from runtime for accurate battery count
        # getBatteryInfo.totalNumber returns 0 when CAN bus BMS communication fails
        # but batParallelNum from runtime is always correct
        self._bat_parallel_num = bat_parallel_num

        # Parent inverter reference for transport runtime data access
        # This enables real-time data from Modbus/Dongle when available
        self._inverter: BaseInverter | None = inverter

        # Individual battery modules in this bank
        self.batteries: list[Battery] = []  # Will be Battery objects

    def _get_transport_runtime(self) -> Any | None:
        """Get transport runtime data from parent inverter if available.

        Returns:
            InverterRuntimeData from transport, or None if not available.
        """
        if self._inverter is not None:
            return getattr(self._inverter, "_transport_runtime", None)
        return None

    def _get_transport_value(self, attr: str) -> float | int | None:
        """Get a value from transport runtime data if available.

        Args:
            attr: Attribute name to retrieve from transport runtime data

        Returns:
            Attribute value if transport data is available, None otherwise.
        """
        transport = self._get_transport_runtime()
        if transport is not None:
            return getattr(transport, attr, None)
        return None

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

        Uses transport runtime data when available for real-time values,
        falling back to cloud API data.

        Returns:
            State of charge percentage (0-100).
        """
        val = self._get_transport_value("battery_soc")
        if val is not None:
            return int(val)
        return self.data.soc

    @property
    def soc_delta(self) -> int | None:
        """Get SOC imbalance across batteries in the bank (max - min).

        Useful for determining if top balancing is required between
        battery packs. A high delta indicates uneven charge states.

        Returns:
            SOC difference in percentage points, or None if fewer than
            2 batteries are present (delta not meaningful).
        """
        if len(self.batteries) < 2:
            return None
        soc_values = [b.soc for b in self.batteries]
        return max(soc_values) - min(soc_values)

    # ========== State of Health ==========

    @property
    def min_soh(self) -> int | None:
        """Get minimum state of health across all batteries.

        The weakest battery determines effective bank health.

        Returns:
            Lowest SOH percentage, or None if no batteries present.
        """
        if not self.batteries:
            return None
        return min(b.soh for b in self.batteries)

    @property
    def soh_delta(self) -> int | None:
        """Get SOH imbalance across batteries in the bank (max - min).

        A high delta indicates uneven aging and may suggest pack
        replacement planning.

        Returns:
            SOH difference in percentage points, or None if fewer than
            2 batteries are present.
        """
        if len(self.batteries) < 2:
            return None
        soh_values = [b.soh for b in self.batteries]
        return max(soh_values) - min(soh_values)

    # ========== Cross-Battery Diagnostics ==========

    @property
    def voltage_delta(self) -> float | None:
        """Get voltage spread across batteries in the bank (max - min).

        Voltage can diverge from SOC under load, making this a useful
        complement to soc_delta.

        Returns:
            Voltage difference in volts, or None if fewer than
            2 batteries are present.
        """
        if len(self.batteries) < 2:
            return None
        voltages = [b.voltage for b in self.batteries]
        return round(max(voltages) - min(voltages), 2)

    @property
    def cell_voltage_delta_max(self) -> float | None:
        """Get worst-case cell voltage imbalance across all batteries.

        Returns the highest cell_voltage_delta from any battery in
        the bank. Useful for quickly checking if any pack needs
        cell-level balancing.

        Returns:
            Maximum cell voltage delta in volts, or None if no
            batteries present.
        """
        if not self.batteries:
            return None
        return max(b.cell_voltage_delta for b in self.batteries)

    @property
    def cycle_count_delta(self) -> int | None:
        """Get cycle count spread across batteries (max - min).

        A high delta indicates uneven usage across packs.

        Returns:
            Cycle count difference, or None if fewer than
            2 batteries are present.
        """
        if len(self.batteries) < 2:
            return None
        counts = [b.cycle_count for b in self.batteries]
        return max(counts) - min(counts)

    @property
    def max_cell_temp(self) -> float | None:
        """Get highest cell temperature across all batteries.

        Bank-wide thermal ceiling for safety monitoring.

        Returns:
            Maximum cell temperature in Celsius, or None if no
            batteries present.
        """
        if not self.batteries:
            return None
        return max(b.max_cell_temp for b in self.batteries)

    @property
    def temp_delta(self) -> float | None:
        """Get thermal spread across all batteries (max - min).

        Compares the hottest cell in any battery to the coolest cell
        in any battery across the entire bank.

        Returns:
            Temperature difference in Celsius, or None if no
            batteries present.
        """
        if not self.batteries:
            return None
        highest = max(b.max_cell_temp for b in self.batteries)
        lowest = min(b.min_cell_temp for b in self.batteries)
        return round(highest - lowest, 1)

    # ========== Voltage Properties ==========

    @property
    def voltage(self) -> float:
        """Get battery bank voltage in volts.

        Uses transport runtime data when available for real-time values,
        falling back to cloud API data.

        Returns:
            Battery voltage (scaled from vBat ÷10).
        """
        val = self._get_transport_value("battery_voltage")
        if val is not None:
            return float(val)
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

        Uses transport runtime data when available for real-time values,
        falling back to cloud API data.

        Returns:
            Charging power in watts.
        """
        val = self._get_transport_value("battery_charge_power")
        if val is not None:
            return int(val)
        return self.data.pCharge

    @property
    def discharge_power(self) -> int:
        """Get total discharging power in watts.

        Uses transport runtime data when available for real-time values,
        falling back to cloud API data.

        Returns:
            Discharging power in watts.
        """
        val = self._get_transport_value("battery_discharge_power")
        if val is not None:
            return int(val)
        return self.data.pDisCharge

    @property
    def battery_power(self) -> int | None:
        """Get net battery power in watts (positive = charging, negative = discharging).

        Uses transport runtime data when available for real-time values,
        falling back to cloud API data.

        Returns:
            Net battery power in watts, or None if not available.
        """
        charge = self._get_transport_value("battery_charge_power")
        discharge = self._get_transport_value("battery_discharge_power")
        if charge is not None and discharge is not None:
            return int(charge) - int(discharge)
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
            Maximum capacity in Ah, or 0 if no battery installed.
        """
        return self.data.maxBatteryCharge or 0

    @property
    def current_capacity(self) -> float:
        """Get current battery bank capacity in amp-hours.

        When transport runtime data is available, calculates from real-time
        SOC and max capacity for more accurate values. Falls back to cloud
        API data.

        Returns:
            Current capacity in Ah, rounded to 1 decimal place, or 0.0 if no battery.
        """
        max_cap = self.data.maxBatteryCharge
        if max_cap is None or max_cap == 0:
            return 0.0

        soc_val = self._get_transport_value("battery_soc")
        if soc_val is not None:
            # Calculate current capacity from real-time SOC and max capacity
            return round((float(soc_val) / 100.0) * max_cap, 1)

        if self.data.currentBatteryCharge is not None:
            return round(self.data.currentBatteryCharge, 1)
        return 0.0

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
    def current(self) -> float | None:
        """Get battery bank current in amps.

        Positive = charging, negative = discharging.

        Uses transport runtime data when available for real-time values,
        falling back to parsing cloud API currentText/currentType.

        Returns:
            Current in amps, or None if not available.
        """
        val = self._get_transport_value("battery_current")
        if val is not None:
            return float(val)

        # Parse from cloud API currentText (e.g., "49.8A") + currentType
        text = self.data.currentText
        if text is None:
            return None
        try:
            amps = float(text.rstrip("AaVvWw "))
        except (ValueError, AttributeError):
            return None
        if self.data.currentType == "discharge":
            amps = -amps
        return amps

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

        Battery count priority (same logic as HTTPTransport.read_battery()):
        1. _bat_parallel_num from runtime (most reliable for LXP-EU devices)
        2. totalNumber from getBatteryInfo (can be 0 if CAN bus BMS communication fails)
        3. len(batteryArray) as fallback

        Returns:
            Number of battery modules.
        """
        # Prefer batParallelNum from runtime - most reliable
        if self._bat_parallel_num is not None and self._bat_parallel_num > 0:
            return self._bat_parallel_num
        # Fall back to totalNumber from API
        if self.data.totalNumber is not None and self.data.totalNumber > 0:
            return self.data.totalNumber
        # Last resort: count batteries in array
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
