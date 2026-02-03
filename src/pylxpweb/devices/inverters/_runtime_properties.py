"""Runtime properties mixin for BaseInverter.

This mixin provides properly-scaled property accessors for all runtime
sensor data from the inverter. All properties return typed, scaled values
with graceful None handling.

Properties prefer transport data (Modbus/Dongle) when available, falling
back to HTTP cloud data. Transport data uses InverterRuntimeData with
pythonic field names; cloud data uses InverterRuntime with raw API names.

Transport fields return None when a register read fails, allowing Home
Assistant to show "unavailable" state instead of recording false zeros.

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
    from pylxpweb.transports.data import InverterRuntimeData


class InverterRuntimePropertiesMixin:
    """Mixin providing runtime property accessors for inverters."""

    _runtime: InverterRuntime | None
    _transport_runtime: InverterRuntimeData | None

    # ===========================================
    # PV (Solar Panel) Properties
    # ===========================================

    @property
    def pv1_voltage(self) -> float | None:
        """Get PV string 1 voltage in volts.

        Returns:
            PV1 voltage (÷10), None if transport read failed, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.pv1_voltage
            return float(val) if val is not None else None
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("vpv1", self._runtime.vpv1)

    @property
    def pv2_voltage(self) -> float | None:
        """Get PV string 2 voltage in volts.

        Returns:
            PV2 voltage (÷10), None if transport read failed, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.pv2_voltage
            return float(val) if val is not None else None
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("vpv2", self._runtime.vpv2)

    @property
    def pv3_voltage(self) -> float | None:
        """Get PV string 3 voltage in volts (if available).

        Returns:
            PV3 voltage (÷10), None if unavailable, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.pv3_voltage
            return float(val) if val is not None else None
        if self._runtime is None or self._runtime.vpv3 is None:
            return 0.0
        return scale_runtime_value("vpv3", self._runtime.vpv3)

    @property
    def pv1_power(self) -> int | None:
        """Get PV string 1 power in watts.

        Returns:
            PV1 power in watts, None if transport read failed, or 0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.pv1_power
            return int(val) if val is not None else None
        if self._runtime is None:
            return 0
        return self._runtime.ppv1

    @property
    def pv2_power(self) -> int | None:
        """Get PV string 2 power in watts.

        Returns:
            PV2 power in watts, None if transport read failed, or 0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.pv2_power
            return int(val) if val is not None else None
        if self._runtime is None:
            return 0
        return self._runtime.ppv2

    @property
    def pv3_power(self) -> int | None:
        """Get PV string 3 power in watts (if available).

        Returns:
            PV3 power in watts, None if unavailable, or 0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.pv3_power
            return int(val) if val is not None else None
        if self._runtime is None or self._runtime.ppv3 is None:
            return 0
        return self._runtime.ppv3

    @property
    def pv_total_power(self) -> int | None:
        """Get total PV power from all strings in watts.

        Returns:
            Total PV power in watts, None if transport read failed, or 0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.pv_total_power
            return int(val) if val is not None else None
        if self._runtime is None:
            return 0
        return self._runtime.ppv

    # ===========================================
    # AC Grid Properties
    # ===========================================

    @property
    def grid_voltage_r(self) -> float | None:
        """Get grid AC voltage phase R in volts.

        Returns:
            AC grid voltage R phase (÷10), None if transport read failed, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.grid_voltage_r
            return float(val) if val is not None else None
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("vacr", self._runtime.vacr)

    @property
    def grid_voltage_s(self) -> float | None:
        """Get grid AC voltage phase S in volts.

        Returns:
            AC grid voltage S phase (÷10), None if transport read failed, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.grid_voltage_s
            return float(val) if val is not None else None
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("vacs", self._runtime.vacs)

    @property
    def grid_voltage_t(self) -> float | None:
        """Get grid AC voltage phase T in volts.

        Returns:
            AC grid voltage T phase (÷10), None if transport read failed, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.grid_voltage_t
            return float(val) if val is not None else None
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("vact", self._runtime.vact)

    @property
    def grid_frequency(self) -> float | None:
        """Get grid AC frequency in Hz.

        Returns:
            Grid frequency (÷100), None if transport read failed, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.grid_frequency
            return float(val) if val is not None else None
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("fac", self._runtime.fac)

    @property
    def power_factor(self) -> str | None:
        """Get power factor.

        Returns:
            Power factor as string, None if transport read failed, or empty string if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.power_factor
            return str(val) if val is not None else None
        if self._runtime is None:
            return ""
        return self._runtime.pf

    # ===========================================
    # EPS (Emergency Power Supply) Properties
    # ===========================================

    @property
    def eps_voltage_r(self) -> float | None:
        """Get EPS voltage phase R in volts.

        Returns:
            EPS voltage R phase (÷10), None if transport read failed, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.eps_voltage_r
            return float(val) if val is not None else None
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("vepsr", self._runtime.vepsr)

    @property
    def eps_voltage_s(self) -> float | None:
        """Get EPS voltage phase S in volts.

        Returns:
            EPS voltage S phase (÷10), None if transport read failed, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.eps_voltage_s
            return float(val) if val is not None else None
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("vepss", self._runtime.vepss)

    @property
    def eps_voltage_t(self) -> float | None:
        """Get EPS voltage phase T in volts.

        Returns:
            EPS voltage T phase (÷10), None if transport read failed, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.eps_voltage_t
            return float(val) if val is not None else None
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("vepst", self._runtime.vepst)

    @property
    def eps_frequency(self) -> float | None:
        """Get EPS frequency in Hz.

        Returns:
            EPS frequency (÷100), None if transport read failed, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.eps_frequency
            return float(val) if val is not None else None
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("feps", self._runtime.feps)

    @property
    def eps_power(self) -> int | None:
        """Get EPS power in watts.

        Returns:
            EPS power in watts, None if transport read failed, or 0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.eps_power
            return int(val) if val is not None else None
        if self._runtime is None:
            return 0
        return self._runtime.peps

    @property
    def eps_power_l1(self) -> int:
        """Get EPS L1 power in watts.

        When using local transport, computes L1 share from total EPS power
        proportional to L1/L2 voltages. Falls back to cloud data.

        Returns:
            EPS L1 power in watts, or 0 if no data.
        """
        if self._transport_runtime is not None:
            return self._compute_eps_leg_power("l1")
        if self._runtime is None:
            return 0
        return self._runtime.pEpsL1N

    @property
    def eps_power_l2(self) -> int:
        """Get EPS L2 power in watts.

        When using local transport, computes L2 share from total EPS power
        proportional to L1/L2 voltages. Falls back to cloud data.

        Returns:
            EPS L2 power in watts, or 0 if no data.
        """
        if self._transport_runtime is not None:
            return self._compute_eps_leg_power("l2")
        if self._runtime is None:
            return 0
        return self._runtime.pEpsL2N

    def _compute_eps_leg_power(self, leg: str) -> int:
        """Compute per-leg EPS power from local transport data.

        Splits total eps_power proportionally by L1/L2 voltage. When both
        voltages are available, power is distributed by voltage ratio. When
        only one voltage is present, all power is attributed to that leg.

        Args:
            leg: "l1" or "l2"

        Returns:
            Estimated power for the requested leg in watts.
        """
        rt = self._transport_runtime
        if rt is None or rt.eps_power is None:
            return 0
        total = rt.eps_power
        v_l1 = rt.eps_l1_voltage
        v_l2 = rt.eps_l2_voltage
        if v_l1 and v_l2:
            v_sum = v_l1 + v_l2
            if v_sum > 0:
                ratio = v_l1 / v_sum if leg == "l1" else v_l2 / v_sum
                return int(total * ratio)
        # Single-leg or no voltage data: assume equal split
        if leg == "l1":
            return int(total / 2) if v_l2 else int(total)
        return int(total / 2) if v_l1 else int(total)

    # ===========================================
    # Power Flow Properties
    # ===========================================

    @property
    def power_to_grid(self) -> int | None:
        """Get power flowing to grid in watts.

        Returns:
            Power to grid in watts, None if transport read failed, or 0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.power_to_grid
            return int(val) if val is not None else None
        if self._runtime is None:
            return 0
        return self._runtime.pToGrid

    @property
    def power_to_user(self) -> int | None:
        """Get power imported from grid in watts (Ptouser).

        Returns:
            Grid import power in watts, None if transport read failed, or 0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.load_power
            return int(val) if val is not None else None
        if self._runtime is None:
            return 0
        return self._runtime.pToUser

    @property
    def inverter_power(self) -> int | None:
        """Get inverter power in watts.

        Returns:
            Inverter power in watts, None if transport read failed, or 0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.inverter_power
            return int(val) if val is not None else None
        if self._runtime is None:
            return 0
        return self._runtime.pinv

    @property
    def rectifier_power(self) -> int | None:
        """Get AC charging rectifier power (Prec) in watts.

        This is the power from grid used specifically for AC battery charging,
        NOT the total grid import power. See power_to_user for grid import.

        Returns:
            AC charge rectifier power in watts, or None if no data.
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
    def battery_voltage(self) -> float | None:
        """Get battery voltage in volts.

        Returns:
            Battery voltage (÷10), None if transport read failed, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.battery_voltage
            return float(val) if val is not None else None
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("vBat", self._runtime.vBat)

    @property
    def battery_charge_power(self) -> int | None:
        """Get battery charging power in watts.

        Returns:
            Battery charge power in watts, None if transport read failed, or 0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.battery_charge_power
            return int(val) if val is not None else None
        if self._runtime is None:
            return 0
        return self._runtime.pCharge

    @property
    def battery_discharge_power(self) -> int | None:
        """Get battery discharging power in watts.

        Returns:
            Battery discharge power in watts, None if transport read failed, or 0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.battery_discharge_power
            return int(val) if val is not None else None
        if self._runtime is None:
            return 0
        return self._runtime.pDisCharge

    @property
    def battery_power(self) -> int | None:
        """Get net battery power in watts (positive = charging, negative = discharging).

        Returns:
            Battery power in watts, None if transport read failed, or 0 if no data.
        """
        if self._transport_runtime is not None:
            charge = self._transport_runtime.battery_charge_power
            discharge = self._transport_runtime.battery_discharge_power
            if charge is None or discharge is None:
                return None
            return int(charge) - int(discharge)
        if self._runtime is None:
            return 0
        return self._runtime.batPower

    @property
    def battery_temperature(self) -> int | None:
        """Get battery temperature in Celsius.

        Returns:
            Battery temperature in °C, None if transport read failed, or 0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.battery_temperature
            return int(val) if val is not None else None
        if self._runtime is None:
            return 0
        return self._runtime.tBat

    @property
    def max_charge_current(self) -> float | None:
        """Get maximum charge current in amps.

        Returns:
            Max charge current (÷100), None if transport read failed, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.bms_charge_current_limit
            return float(val) if val is not None else None
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("maxChgCurr", self._runtime.maxChgCurr)

    @property
    def max_discharge_current(self) -> float | None:
        """Get maximum discharge current in amps.

        Returns:
            Max discharge current (÷100), None if transport read failed, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.bms_discharge_current_limit
            return float(val) if val is not None else None
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("maxDischgCurr", self._runtime.maxDischgCurr)

    # ===========================================
    # Temperature Properties
    # ===========================================

    @property
    def inverter_temperature(self) -> int | None:
        """Get inverter internal temperature in Celsius.

        Returns:
            Internal temperature in °C, None if transport read failed, or 0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.internal_temperature
            return int(val) if val is not None else None
        if self._runtime is None:
            return 0
        return self._runtime.tinner

    @property
    def radiator1_temperature(self) -> int | None:
        """Get radiator 1 temperature in Celsius.

        Returns:
            Radiator 1 temperature in °C, None if transport read failed, or 0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.radiator_temperature_1
            return int(val) if val is not None else None
        if self._runtime is None:
            return 0
        return self._runtime.tradiator1

    @property
    def radiator2_temperature(self) -> int | None:
        """Get radiator 2 temperature in Celsius.

        Returns:
            Radiator 2 temperature in °C, None if transport read failed, or 0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.radiator_temperature_2
            return int(val) if val is not None else None
        if self._runtime is None:
            return 0
        return self._runtime.tradiator2

    # ===========================================
    # Bus Voltage Properties
    # ===========================================

    @property
    def bus1_voltage(self) -> float | None:
        """Get bus 1 voltage in volts.

        Returns:
            Bus 1 voltage (÷100), None if transport read failed, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.bus_voltage_1
            return float(val) if val is not None else None
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("vBus1", self._runtime.vBus1)

    @property
    def bus2_voltage(self) -> float | None:
        """Get bus 2 voltage in volts.

        Returns:
            Bus 2 voltage (÷100), None if transport read failed, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.bus_voltage_2
            return float(val) if val is not None else None
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("vBus2", self._runtime.vBus2)

    # ===========================================
    # AC Couple & Generator Properties
    # ===========================================

    @property
    def ac_couple_power(self) -> int:
        """Get AC coupled power in watts.

        Uses generator_power register (123) from local transport as the
        closest proxy — the generator port carries AC couple flow when no
        physical generator is connected. Falls back to cloud acCouplePower.

        Returns:
            AC couple power in watts, or 0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.generator_power
            return int(val) if val is not None else 0
        if self._runtime is None:
            return 0
        return self._runtime.acCouplePower

    @property
    def generator_voltage(self) -> float | None:
        """Get generator voltage in volts.

        Returns:
            Generator voltage (÷10), None if transport read failed, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.generator_voltage
            return float(val) if val is not None else None
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("genVolt", self._runtime.genVolt)

    @property
    def generator_frequency(self) -> float | None:
        """Get generator frequency in Hz.

        Returns:
            Generator frequency (÷100), None if transport read failed, or 0.0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.generator_frequency
            return float(val) if val is not None else None
        if self._runtime is None:
            return 0.0
        return scale_runtime_value("genFreq", self._runtime.genFreq)

    @property
    def generator_power(self) -> int | None:
        """Get generator power in watts.

        Returns:
            Generator power in watts, None if transport read failed, or 0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.generator_power
            return int(val) if val is not None else None
        if self._runtime is None:
            return 0
        return self._runtime.genPower

    @property
    def is_using_generator(self) -> bool:
        """Check if generator is currently in use.

        Returns:
            True if using generator, False otherwise.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.generator_power
            return val is not None and int(val) > 0
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
            consumption = load_power + eps_power
        where load_power is pToUser and eps_power is peps.

        This matches the HTTP API formula: consumptionPower = pToUser + peps

        Returns:
            Consumption power in watts, or None if no data.
        """
        if self._transport_runtime is not None:
            load = self._transport_runtime.load_power
            eps = self._transport_runtime.eps_power
            if load is None and eps is None:
                return None
            # Sum available values, treating None as 0
            return int(load or 0) + int(eps or 0)
        if self._runtime is None:
            return None
        return self._runtime.consumptionPower

    @property
    def total_load_power(self) -> int | None:
        """Get total load power in watts.

        Computes: eps_power + consumption_power

        This represents the total power being consumed by all loads
        (both EPS-connected and non-EPS loads).

        Returns:
            Total load power in watts, or None if no data.
        """
        eps = self.eps_power
        consumption = self.consumption_power
        if eps is None and consumption is None:
            return None
        return (eps or 0) + (consumption or 0)

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
    def status(self) -> int | None:
        """Get inverter status code.

        Returns:
            Status code, None if transport read failed, or 0 if no data.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.device_status
            return int(val) if val is not None else None
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
        if self._transport_runtime is not None:
            return False  # Transport connected = not lost
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
