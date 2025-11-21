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
    def cell_voltage_delta(self) -> float:
        """Get cell voltage imbalance (max - min).

        Returns:
            Voltage difference between highest and lowest cell in volts.
        """
        return self.max_cell_voltage - self.min_cell_voltage

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

    @property
    def is_lost(self) -> bool:
        """Check if battery communication is lost.

        Returns:
            True if battery is not communicating.
        """
        return self._data.lost

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
