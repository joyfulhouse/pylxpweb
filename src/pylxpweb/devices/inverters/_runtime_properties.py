"""Runtime properties mixin for BaseInverter.

This mixin provides properly-scaled property accessors for all runtime
sensor data from the inverter. All properties return typed, scaled values
with graceful None handling.

Properties are organized by category:
- PV (Solar Panel) Properties
- AC Grid Properties
- EPS (Emergency Power Supply) Properties
- Power Flow Properties
- Battery Properties
- Temperature Properties
- Bus Voltage Properties
- AC Couple & Generator Properties
- Consumption Properties
- Status & Info Properties
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pylxpweb.constants import scale_runtime_value

if TYPE_CHECKING:
    from pylxpweb.models import InverterRuntime


class InverterRuntimePropertiesMixin:
    """Mixin providing runtime property accessors for inverters."""

    _runtime: InverterRuntime | None

    # ===========================================
    # PV (Solar Panel) Properties
    # ===========================================

    @property
    def pv1_voltage(self) -> float:
        """Get PV string 1 voltage in volts.

        Returns:
            PV1 voltage (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("vpv1", self._runtime.vpv1)

    @property
    def pv2_voltage(self) -> float:
        """Get PV string 2 voltage in volts.

        Returns:
            PV2 voltage (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_runtime_value("vpv2", self._runtime.vpv2)

    @property
    def pv3_voltage(self) -> float:
        """Get PV string 3 voltage in volts (if available).

        Returns:
            PV3 voltage (÷10), or 0.0 if no data or not supported.
        """
        if self._runtime is None or self._runtime.vpv3 is None:
            return 0.0

        return scale_runtime_value("vpv3", self._runtime.vpv3)

    @property
    def pv1_power(self) -> int:
        """Get PV string 1 power in watts.

        Returns:
            PV1 power in watts, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.ppv1

    @property
    def pv2_power(self) -> int:
        """Get PV string 2 power in watts.

        Returns:
            PV2 power in watts, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.ppv2

    @property
    def pv3_power(self) -> int:
        """Get PV string 3 power in watts (if available).

        Returns:
            PV3 power in watts, or 0 if no data or not supported.
        """
        if self._runtime is None or self._runtime.ppv3 is None:
            return 0
        return self._runtime.ppv3

    @property
    def pv_total_power(self) -> int:
        """Get total PV power from all strings in watts.

        Returns:
            Total PV power in watts, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.ppv

    # ===========================================
    # AC Grid Properties
    # ===========================================

    @property
    def grid_voltage_r(self) -> float:
        """Get grid AC voltage phase R in volts.

        Returns:
            AC grid voltage R phase (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_runtime_value("vacr", self._runtime.vacr)

    @property
    def grid_voltage_s(self) -> float:
        """Get grid AC voltage phase S in volts.

        Returns:
            AC grid voltage S phase (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_runtime_value("vacs", self._runtime.vacs)

    @property
    def grid_voltage_t(self) -> float:
        """Get grid AC voltage phase T in volts.

        Returns:
            AC grid voltage T phase (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_runtime_value("vact", self._runtime.vact)

    @property
    def grid_frequency(self) -> float:
        """Get grid AC frequency in Hz.

        Returns:
            Grid frequency (÷100), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_runtime_value("fac", self._runtime.fac)

    @property
    def power_factor(self) -> str:
        """Get power factor.

        Returns:
            Power factor as string, or empty string if no data.
        """
        if self._runtime is None:
            return ""
        return self._runtime.pf

    # ===========================================
    # EPS (Emergency Power Supply) Properties
    # ===========================================

    @property
    def eps_voltage_r(self) -> float:
        """Get EPS voltage phase R in volts.

        Returns:
            EPS voltage R phase (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_runtime_value("vepsr", self._runtime.vepsr)

    @property
    def eps_voltage_s(self) -> float:
        """Get EPS voltage phase S in volts.

        Returns:
            EPS voltage S phase (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_runtime_value("vepss", self._runtime.vepss)

    @property
    def eps_voltage_t(self) -> float:
        """Get EPS voltage phase T in volts.

        Returns:
            EPS voltage T phase (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_runtime_value("vepst", self._runtime.vepst)

    @property
    def eps_frequency(self) -> float:
        """Get EPS frequency in Hz.

        Returns:
            EPS frequency (÷100), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_runtime_value("feps", self._runtime.feps)

    @property
    def eps_power(self) -> int:
        """Get EPS power in watts.

        Returns:
            EPS power in watts, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.peps

    @property
    def eps_power_l1(self) -> int:
        """Get EPS L1 power in watts.

        Returns:
            EPS L1 power in watts, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.pEpsL1N

    @property
    def eps_power_l2(self) -> int:
        """Get EPS L2 power in watts.

        Returns:
            EPS L2 power in watts, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.pEpsL2N

    # ===========================================
    # Power Flow Properties
    # ===========================================

    @property
    def power_to_grid(self) -> int:
        """Get power flowing to grid in watts.

        Returns:
            Power to grid in watts, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.pToGrid

    @property
    def power_to_user(self) -> int:
        """Get power flowing to user loads in watts.

        Returns:
            Power to user in watts, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.pToUser

    @property
    def inverter_power(self) -> int:
        """Get inverter power in watts.

        Returns:
            Inverter power in watts, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.pinv

    @property
    def rectifier_power(self) -> int | None:
        """Get rectifier power (AC→DC from grid) in watts.

        Returns:
            Rectifier power in watts, or None if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.grid_power
            return int(val) if val is not None else None
        if self._runtime is None:
            return None
        return self._runtime.prec

    # ===========================================
    # Battery Properties
    # ===========================================

    @property
    def battery_voltage(self) -> float:
        """Get battery voltage in volts.

        Returns:
            Battery voltage (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_runtime_value("vBat", self._runtime.vBat)

    @property
    def battery_charge_power(self) -> int:
        """Get battery charging power in watts.

        Returns:
            Battery charge power in watts, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.pCharge

    @property
    def battery_discharge_power(self) -> int:
        """Get battery discharging power in watts.

        Returns:
            Battery discharge power in watts, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.pDisCharge

    @property
    def battery_power(self) -> int:
        """Get net battery power in watts (positive = charging, negative = discharging).

        Returns:
            Battery power in watts, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.batPower

    @property
    def battery_temperature(self) -> int:
        """Get battery temperature in Celsius.

        Returns:
            Battery temperature in °C, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.tBat

    @property
    def max_charge_current(self) -> float:
        """Get maximum charge current in amps.

        Returns:
            Max charge current (÷100), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_runtime_value("maxChgCurr", self._runtime.maxChgCurr)

    @property
    def max_discharge_current(self) -> float:
        """Get maximum discharge current in amps.

        Returns:
            Max discharge current (÷100), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_runtime_value("maxDischgCurr", self._runtime.maxDischgCurr)

    # ===========================================
    # Temperature Properties
    # ===========================================

    @property
    def inverter_temperature(self) -> int:
        """Get inverter internal temperature in Celsius.

        Returns:
            Internal temperature in °C, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.tinner

    @property
    def radiator1_temperature(self) -> int:
        """Get radiator 1 temperature in Celsius.

        Returns:
            Radiator 1 temperature in °C, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.tradiator1

    @property
    def radiator2_temperature(self) -> int:
        """Get radiator 2 temperature in Celsius.

        Returns:
            Radiator 2 temperature in °C, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.tradiator2

    # ===========================================
    # Bus Voltage Properties
    # ===========================================

    @property
    def bus1_voltage(self) -> float:
        """Get bus 1 voltage in volts.

        Returns:
            Bus 1 voltage (÷100), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_runtime_value("vBus1", self._runtime.vBus1)

    @property
    def bus2_voltage(self) -> float:
        """Get bus 2 voltage in volts.

        Returns:
            Bus 2 voltage (÷100), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_runtime_value("vBus2", self._runtime.vBus2)

    # ===========================================
    # AC Couple & Generator Properties
    # ===========================================

    @property
    def ac_couple_power(self) -> int:
        """Get AC coupled power in watts.

        Returns:
            AC couple power in watts, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.acCouplePower

    @property
    def generator_voltage(self) -> float:
        """Get generator voltage in volts.

        Returns:
            Generator voltage (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_runtime_value("genVolt", self._runtime.genVolt)

    @property
    def generator_frequency(self) -> float:
        """Get generator frequency in Hz.

        Returns:
            Generator frequency (÷100), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_runtime_value("genFreq", self._runtime.genFreq)

    @property
    def generator_power(self) -> int:
        """Get generator power in watts.

        Returns:
            Generator power in watts, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.genPower

    @property
    def is_using_generator(self) -> bool:
        """Check if generator is currently in use.

        Returns:
            True if using generator, False otherwise.
        """
        if self._runtime is None:
            return False
        return self._runtime._12KUsingGenerator

    # ===========================================
    # Consumption Properties
    # ===========================================

    @property
    def consumption_power(self) -> int | None:
        """Get consumption power in watts.

        For HTTP data, uses the server-computed consumptionPower field.
        For local transport data (Modbus/Dongle), computes as:
            consumption = load_power - grid_power
        where load_power is pToUser and grid_power is prec (rectifier).

        Returns:
            Consumption power in watts, or None if no data.
        """
        if self._transport_runtime is not None:
            load = self._transport_runtime.load_power
            rectifier = self._transport_runtime.grid_power
            if load is None or rectifier is None:
                return None
            return max(0, int(load) - int(rectifier))
        if self._runtime is None:
            return None
        return self._runtime.consumptionPower

    # ===========================================
    # Status & Info Properties
    # ===========================================

    @property
    def firmware_version(self) -> str:
        """Get firmware version.

        Returns:
            Firmware version string, or empty string if no data.
        """
        if self._runtime is None:
            return ""
        return self._runtime.fwCode

    @property
    def status(self) -> int:
        """Get inverter status code.

        Returns:
            Status code, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.status

    @property
    def status_text(self) -> str:
        """Get inverter status as text.

        Returns:
            Status text, or empty string if no data.
        """
        if self._runtime is None:
            return ""
        return self._runtime.statusText

    @property
    def is_lost(self) -> bool:
        """Check if inverter connection is lost.

        Returns:
            True if connection lost, False otherwise.
        """
        if self._runtime is None:
            return True  # No data means lost
        return self._runtime.lost

    @property
    def power_rating(self) -> str:
        """Get power rating text (e.g., "16kW").

        Returns:
            Power rating string, or empty string if no data.
        """
        if self._runtime is None:
            return ""
        return self._runtime.powerRatingText
