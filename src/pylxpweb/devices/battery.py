"""Battery module for individual battery monitoring.

This module provides the Battery class for monitoring individual battery modules
within an inverter's battery array.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pylxpweb.constants import scale_battery_value

from .base import BaseDevice
from .models import DeviceClass, DeviceInfo, Entity, StateClass

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient
    from pylxpweb.models import BatteryModule


class Battery(BaseDevice):
    """Represents an individual battery module.

    Each inverter can have multiple battery modules, each with independent monitoring
    of voltage, current, SoC, SoH, temperature, and cell voltages.

    Example:
        ```python
        # Battery is typically created from BatteryInfo API response
        battery_info = await client.api.batteries.get_battery_info(serial_num)

        for battery_data in battery_info.batteryArray:
            battery = Battery(client=client, battery_data=battery_data)
            print(f"Battery {battery.battery_index}: {battery.soc}% SOC")
            print(f"Voltage: {battery.voltage}V, Current: {battery.current}A")
            print(f"Cell voltage delta: {battery.cell_voltage_delta}V")
        ```
    """

    def __init__(self, client: LuxpowerClient, battery_data: BatteryModule) -> None:
        """Initialize battery module.

        Args:
            client: LuxpowerClient instance for API access
            battery_data: BatteryModule data from API
        """
        # Use batteryKey as serial_number for BaseDevice
        super().__init__(client, battery_data.batteryKey, "Battery Module")

        self._battery_key = battery_data.batteryKey
        self._battery_sn = battery_data.batterySn
        self._battery_index = battery_data.batIndex
        self._data = battery_data

    # Public accessors for backward compatibility
    @property
    def battery_key(self) -> str:
        """Get battery key identifier."""
        return self._battery_key

    @property
    def battery_sn(self) -> str:
        """Get battery serial number."""
        return self._battery_sn

    @property
    def battery_index(self) -> int:
        """Get battery index position."""
        return self._battery_index

    @property
    def data(self) -> BatteryModule:
        """Get raw battery data.

        Note: Direct modification of this data is discouraged.
        Use the provided setter methods or properties instead.
        """
        return self._data

    @data.setter
    def data(self, value: BatteryModule) -> None:
        """Set raw battery data.

        Args:
            value: New BatteryModule data
        """
        self._data = value

    # ========== Identification Properties ==========

    @property
    def battery_type(self) -> str | None:
        """Get battery type identifier.

        Returns:
            Battery type string, or None if not available.
        """
        return self._data.batteryType

    @property
    def battery_type_text(self) -> str:
        """Get battery type display text.

        Returns:
            Battery type display text. Falls back to "Lithium" if not available.
        """
        # If batteryTypeText is empty or None, provide reasonable default
        if not self._data.batteryTypeText:
            # Most EG4/Luxpower batteries are Lithium
            return "Lithium"
        return self._data.batteryTypeText

    @property
    def bms_model(self) -> str | None:
        """Get BMS model information.

        Returns:
            BMS model text, or None if not available.
        """
        return self._data.batBmsModelText

    # ========== Status Properties ==========

    @property
    def is_lost(self) -> bool:
        """Check if battery communication is lost.

        Returns:
            True if battery is not communicating.
        """
        return self._data.lost

    @property
    def last_update_time(self) -> str | None:
        """Get last update timestamp.

        Returns:
            Last update timestamp string, or None if not available.
        """
        return self._data.lastUpdateTime

    # ========== Voltage and Current ==========

    @property
    def voltage(self) -> float:
        """Get battery voltage in volts.

        Returns:
            Battery voltage (scaled from totalVoltage ÷100).
        """
        return scale_battery_value("totalVoltage", self._data.totalVoltage)

    @property
    def current(self) -> float:
        """Get battery current in amps.

        Returns:
            Battery current (scaled from current ÷10). **CRITICAL: Not ÷100**
        """
        return scale_battery_value("current", self._data.current)

    @property
    def power(self) -> float:
        """Get battery power in watts (calculated from V * I).

        Returns:
            Battery power in watts.
        """
        return self.voltage * self.current

    # ========== State of Charge/Health ==========

    @property
    def soc(self) -> int:
        """Get battery state of charge.

        Returns:
            State of charge percentage (0-100).
        """
        return self._data.soc

    @property
    def soh(self) -> int:
        """Get battery state of health.

        Returns:
            State of health percentage (0-100).
        """
        return self._data.soh

    # ========== Capacity Properties ==========

    @property
    def current_remain_capacity(self) -> int:
        """Get current remaining capacity in amp-hours.

        Returns:
            Current remaining capacity in Ah.
        """
        return self._data.currentRemainCapacity

    @property
    def current_full_capacity(self) -> int:
        """Get current full capacity in amp-hours.

        Returns:
            Current full capacity in Ah.
        """
        return self._data.currentFullCapacity

    @property
    def capacity_percent(self) -> int:
        """Get current capacity as percentage of full capacity.

        Returns:
            Capacity percentage (0-100). If not provided by API, calculates
            from currentRemainCapacity / currentFullCapacity and rounds to
            nearest integer.
        """
        # Use API value if available
        if self._data.currentCapacityPercent is not None:
            return self._data.currentCapacityPercent

        # Calculate from remain/full capacity, rounded to nearest integer
        if self._data.currentFullCapacity > 0:
            return round(
                (self._data.currentRemainCapacity / self._data.currentFullCapacity) * 100
            )

        # Fallback to 0 if full capacity is 0
        return 0

    @property
    def max_battery_charge(self) -> int | None:
        """Get maximum battery charge capacity in amp-hours.

        Returns:
            Maximum charge capacity in Ah, or None if not available.
        """
        return self._data.maxBatteryCharge

    # ========== Temperature Properties ==========

    @property
    def max_cell_temp(self) -> float:
        """Get maximum cell temperature in Celsius.

        Returns:
            Maximum cell temperature (scaled from batMaxCellTemp ÷10).
        """
        return scale_battery_value("batMaxCellTemp", self._data.batMaxCellTemp)

    @property
    def min_cell_temp(self) -> float:
        """Get minimum cell temperature in Celsius.

        Returns:
            Minimum cell temperature (scaled from batMinCellTemp ÷10).
        """
        return scale_battery_value("batMinCellTemp", self._data.batMinCellTemp)

    @property
    def max_cell_temp_num(self) -> int | None:
        """Get cell number with maximum temperature.

        Returns:
            Cell number (0-indexed), or None if not available.
        """
        return self._data.batMaxCellNumTemp

    @property
    def min_cell_temp_num(self) -> int | None:
        """Get cell number with minimum temperature.

        Returns:
            Cell number (0-indexed), or None if not available.
        """
        return self._data.batMinCellNumTemp

    @property
    def cell_temp_delta(self) -> float:
        """Get cell temperature imbalance (max - min).

        Returns:
            Temperature difference between hottest and coolest cell in Celsius.
        """
        return self.max_cell_temp - self.min_cell_temp

    # ========== Cell Voltage Properties ==========

    @property
    def max_cell_voltage(self) -> float:
        """Get maximum cell voltage in volts.

        Returns:
            Maximum cell voltage (scaled from batMaxCellVoltage ÷1000).
        """
        return scale_battery_value("batMaxCellVoltage", self._data.batMaxCellVoltage)

    @property
    def min_cell_voltage(self) -> float:
        """Get minimum cell voltage in volts.

        Returns:
            Minimum cell voltage (scaled from batMinCellVoltage ÷1000).
        """
        return scale_battery_value("batMinCellVoltage", self._data.batMinCellVoltage)

    @property
    def max_cell_voltage_num(self) -> int | None:
        """Get cell number with maximum voltage.

        Returns:
            Cell number (0-indexed), or None if not available.
        """
        return self._data.batMaxCellNumVolt

    @property
    def min_cell_voltage_num(self) -> int | None:
        """Get cell number with minimum voltage.

        Returns:
            Cell number (0-indexed), or None if not available.
        """
        return self._data.batMinCellNumVolt

    @property
    def cell_voltage_delta(self) -> float:
        """Get cell voltage imbalance (max - min).

        Returns:
            Voltage difference between highest and lowest cell in volts.
        """
        return self.max_cell_voltage - self.min_cell_voltage

    # ========== Charge Parameters ==========

    @property
    def charge_max_current(self) -> float | None:
        """Get maximum charge current setting in amps.

        Returns:
            Maximum charge current (÷100 for amps), or None if not available.
        """
        if self._data.batChargeMaxCur is None:
            return None
        return scale_battery_value("batChargeMaxCur", self._data.batChargeMaxCur)

    @property
    def charge_voltage_ref(self) -> float | None:
        """Get charge voltage reference setting in volts.

        Returns:
            Charge voltage reference (÷10 for volts), or None if not available.
        """
        if self._data.batChargeVoltRef is None:
            return None
        return scale_battery_value("batChargeVoltRef", self._data.batChargeVoltRef)

    # ========== Cycle Count and Firmware ==========

    @property
    def cycle_count(self) -> int:
        """Get battery cycle count.

        Returns:
            Number of charge/discharge cycles.
        """
        return self._data.cycleCnt

    @property
    def firmware_version(self) -> str:
        """Get battery firmware version.

        Returns:
            Firmware version string.
        """
        return self._data.fwVersionText

    # ========== Additional Metrics ==========

    @property
    def charge_capacity(self) -> str | None:
        """Get charge capacity metric.

        Returns:
            Charge capacity string, or None if not available.
        """
        return self._data.chgCapacity

    @property
    def discharge_capacity(self) -> str | None:
        """Get discharge capacity metric.

        Returns:
            Discharge capacity string, or None if not available.
        """
        return self._data.disChgCapacity

    @property
    def ambient_temp(self) -> str | None:
        """Get ambient temperature.

        Returns:
            Ambient temperature string, or None if not available.
        """
        return self._data.ambientTemp

    @property
    def mos_temp(self) -> str | None:
        """Get MOSFET temperature.

        Returns:
            MOSFET temperature string, or None if not available.
        """
        return self._data.mosTemp

    @property
    def notice_info(self) -> str | None:
        """Get notice/warning information.

        Returns:
            Notice information string, or None if not available.
        """
        return self._data.noticeInfo

    async def refresh(self) -> None:
        """Refresh battery data.

        Note: Battery data is refreshed through the parent inverter.
        This method is a no-op for individual batteries.
        """
        # Battery data comes from inverter's getBatteryInfo call
        # Individual batteries don't have their own refresh endpoint
        pass

    def to_device_info(self) -> DeviceInfo:
        """Convert to device info model.

        Returns:
            DeviceInfo with battery metadata.
        """
        return DeviceInfo(
            identifiers={("pylxpweb", f"battery_{self._battery_key}")},
            name=f"Battery {self._battery_index + 1} ({self._battery_sn})",
            manufacturer="EG4/Luxpower",
            model="Battery Module",
            sw_version=self.firmware_version,
        )

    def to_entities(self) -> list[Entity]:
        """Generate entities for this battery.

        Returns:
            List of Entity objects representing sensors for this battery.
        """
        entities = []
        # Use properties for consistent access
        battery_key = self.battery_key
        battery_num = self.battery_index + 1

        # Voltage
        entities.append(
            Entity(
                unique_id=f"{battery_key}_voltage",
                name=f"Battery {battery_num} Voltage",
                device_class=DeviceClass.VOLTAGE,
                state_class=StateClass.MEASUREMENT,
                unit_of_measurement="V",
                value=self.voltage,
            )
        )

        # Current
        entities.append(
            Entity(
                unique_id=f"{battery_key}_current",
                name=f"Battery {battery_num} Current",
                device_class=DeviceClass.CURRENT,
                state_class=StateClass.MEASUREMENT,
                unit_of_measurement="A",
                value=self.current,
            )
        )

        # Power
        entities.append(
            Entity(
                unique_id=f"{battery_key}_power",
                name=f"Battery {battery_num} Power",
                device_class=DeviceClass.POWER,
                state_class=StateClass.MEASUREMENT,
                unit_of_measurement="W",
                value=self.power,
            )
        )

        # State of Charge
        entities.append(
            Entity(
                unique_id=f"{battery_key}_soc",
                name=f"Battery {battery_num} SOC",
                device_class=DeviceClass.BATTERY,
                state_class=StateClass.MEASUREMENT,
                unit_of_measurement="%",
                value=self.soc,
            )
        )

        # State of Health
        entities.append(
            Entity(
                unique_id=f"{battery_key}_soh",
                name=f"Battery {battery_num} SOH",
                device_class=DeviceClass.BATTERY,
                state_class=StateClass.MEASUREMENT,
                unit_of_measurement="%",
                value=self.soh,
            )
        )

        # Maximum Cell Temperature
        entities.append(
            Entity(
                unique_id=f"{battery_key}_max_cell_temp",
                name=f"Battery {battery_num} Max Cell Temperature",
                device_class=DeviceClass.TEMPERATURE,
                state_class=StateClass.MEASUREMENT,
                unit_of_measurement="°C",
                value=self.max_cell_temp,
            )
        )

        # Minimum Cell Temperature
        entities.append(
            Entity(
                unique_id=f"{battery_key}_min_cell_temp",
                name=f"Battery {battery_num} Min Cell Temperature",
                device_class=DeviceClass.TEMPERATURE,
                state_class=StateClass.MEASUREMENT,
                unit_of_measurement="°C",
                value=self.min_cell_temp,
            )
        )

        # Maximum Cell Voltage
        entities.append(
            Entity(
                unique_id=f"{battery_key}_max_cell_voltage",
                name=f"Battery {battery_num} Max Cell Voltage",
                device_class=DeviceClass.VOLTAGE,
                state_class=StateClass.MEASUREMENT,
                unit_of_measurement="V",
                value=self.max_cell_voltage,
            )
        )

        # Minimum Cell Voltage
        entities.append(
            Entity(
                unique_id=f"{battery_key}_min_cell_voltage",
                name=f"Battery {battery_num} Min Cell Voltage",
                device_class=DeviceClass.VOLTAGE,
                state_class=StateClass.MEASUREMENT,
                unit_of_measurement="V",
                value=self.min_cell_voltage,
            )
        )

        # Cell Voltage Delta (imbalance indicator)
        entities.append(
            Entity(
                unique_id=f"{battery_key}_cell_voltage_delta",
                name=f"Battery {battery_num} Cell Voltage Delta",
                device_class=DeviceClass.VOLTAGE,
                state_class=StateClass.MEASUREMENT,
                unit_of_measurement="V",
                value=self.cell_voltage_delta,
            )
        )

        # Cycle Count
        entities.append(
            Entity(
                unique_id=f"{battery_key}_cycle_count",
                name=f"Battery {battery_num} Cycle Count",
                device_class=None,  # No standard device class for cycle count
                state_class=StateClass.TOTAL_INCREASING,
                unit_of_measurement="cycles",
                value=self.cycle_count,
            )
        )

        return entities
