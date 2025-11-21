"""Generic inverter implementation for standard EG4/Luxpower models.

This module provides the GenericInverter class that handles all standard
inverter models including FlexBOSS21, FlexBOSS18, 18KPV, 12KPV, and XP.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import DeviceClass, Entity, StateClass
from .base import BaseInverter

if TYPE_CHECKING:
    pass


class GenericInverter(BaseInverter):
    """Generic inverter for standard EG4/Luxpower models.

    Handles all standard inverter models:
    - FlexBOSS21 (21kW)
    - FlexBOSS18 (18kW)
    - 18KPV (18kW)
    - 12KPV (12kW)
    - XP (various power ratings)

    Example:
        ```python
        inverter = GenericInverter(
            client=client,
            serial_number="1234567890",
            model="FlexBOSS21"
        )
        await inverter.refresh()
        print(f"Power: {inverter.power_output}W")
        print(f"SOC: {inverter.battery_soc}%")
        ```
    """

    def to_entities(self) -> list[Entity]:
        """Generate entities for this inverter.

        Returns:
            List of Entity objects representing sensors for this inverter.
        """
        entities = []

        # Power sensors
        if self._runtime:
            # AC Power Output
            entities.append(
                Entity(
                    unique_id=f"{self.serial_number}_power",
                    name=f"{self.model} {self.serial_number} Power",
                    device_class=DeviceClass.POWER,
                    state_class=StateClass.MEASUREMENT,
                    unit_of_measurement="W",
                    value=self.power_output,
                )
            )

            # Battery SOC
            if self.battery_soc is not None:
                entities.append(
                    Entity(
                        unique_id=f"{self.serial_number}_soc",
                        name=f"{self.model} {self.serial_number} Battery SOC",
                        device_class=DeviceClass.BATTERY,
                        state_class=StateClass.MEASUREMENT,
                        unit_of_measurement="%",
                        value=self.battery_soc,
                    )
                )

            # Battery Voltage
            if hasattr(self._runtime, "vBat") and self._runtime.vBat:
                entities.append(
                    Entity(
                        unique_id=f"{self.serial_number}_battery_voltage",
                        name=f"{self.model} {self.serial_number} Battery Voltage",
                        device_class=DeviceClass.VOLTAGE,
                        state_class=StateClass.MEASUREMENT,
                        unit_of_measurement="V",
                        value=self._runtime.vBat / 100.0,  # Scaled value
                    )
                )

            # PV Power
            if hasattr(self._runtime, "ppv"):
                entities.append(
                    Entity(
                        unique_id=f"{self.serial_number}_pv_power",
                        name=f"{self.model} {self.serial_number} PV Power",
                        device_class=DeviceClass.POWER,
                        state_class=StateClass.MEASUREMENT,
                        unit_of_measurement="W",
                        value=self._runtime.ppv,
                    )
                )

            # Grid Power
            if hasattr(self._runtime, "pToGrid"):
                entities.append(
                    Entity(
                        unique_id=f"{self.serial_number}_grid_power",
                        name=f"{self.model} {self.serial_number} Grid Power",
                        device_class=DeviceClass.POWER,
                        state_class=StateClass.MEASUREMENT,
                        unit_of_measurement="W",
                        value=self._runtime.pToGrid,
                    )
                )

            # Load Power
            if hasattr(self._runtime, "pToUser"):
                entities.append(
                    Entity(
                        unique_id=f"{self.serial_number}_load_power",
                        name=f"{self.model} {self.serial_number} Load Power",
                        device_class=DeviceClass.POWER,
                        state_class=StateClass.MEASUREMENT,
                        unit_of_measurement="W",
                        value=self._runtime.pToUser,
                    )
                )

            # Battery Charge/Discharge Power
            if hasattr(self._runtime, "batPower"):
                entities.append(
                    Entity(
                        unique_id=f"{self.serial_number}_battery_power",
                        name=f"{self.model} {self.serial_number} Battery Power",
                        device_class=DeviceClass.POWER,
                        state_class=StateClass.MEASUREMENT,
                        unit_of_measurement="W",
                        value=self._runtime.batPower,
                    )
                )

            # Temperature sensors
            if hasattr(self._runtime, "tinner"):
                entities.append(
                    Entity(
                        unique_id=f"{self.serial_number}_temp_internal",
                        name=f"{self.model} {self.serial_number} Internal Temperature",
                        device_class=DeviceClass.TEMPERATURE,
                        state_class=StateClass.MEASUREMENT,
                        unit_of_measurement="°C",
                        value=self._runtime.tinner,
                    )
                )

            if hasattr(self._runtime, "tBat"):
                entities.append(
                    Entity(
                        unique_id=f"{self.serial_number}_temp_battery",
                        name=f"{self.model} {self.serial_number} Battery Temperature",
                        device_class=DeviceClass.TEMPERATURE,
                        state_class=StateClass.MEASUREMENT,
                        unit_of_measurement="°C",
                        value=self._runtime.tBat,
                    )
                )

        # Energy sensors
        if self._energy:
            # Today's Production
            entities.append(
                Entity(
                    unique_id=f"{self.serial_number}_energy_today",
                    name=f"{self.model} {self.serial_number} Energy Today",
                    device_class=DeviceClass.ENERGY,
                    state_class=StateClass.TOTAL_INCREASING,
                    unit_of_measurement="kWh",
                    value=self.total_energy_today,
                )
            )

            # Lifetime Production
            entities.append(
                Entity(
                    unique_id=f"{self.serial_number}_energy_total",
                    name=f"{self.model} {self.serial_number} Energy Total",
                    device_class=DeviceClass.ENERGY,
                    state_class=StateClass.TOTAL_INCREASING,
                    unit_of_measurement="kWh",
                    value=self.total_energy_lifetime,
                )
            )

        return entities
