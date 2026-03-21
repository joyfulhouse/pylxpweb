"""Runtime properties mixin for BaseInverter.

This mixin provides properly-scaled property accessors for all runtime
sensor data from the inverter. All properties return typed, scaled values
with graceful None handling.

Properties prefer transport data (Modbus/Dongle) when available, falling
back to HTTP cloud data. Transport data uses InverterRuntimeData with
pythonic field names; cloud data uses InverterRuntime with raw API names.

Transport fields return None when a register read fails, allowing Home
Assistant to show "unavailable" state instead of recording false zeros.

Helper methods:

- ``_raw_float(transport_attr, http_field)`` — read a pre-scaled float.
- ``_raw_int(transport_attr, http_field)`` — read a pre-scaled int.
- ``_scaled_float(transport_attr, http_field)`` — read a float that
  needs ``scale_runtime_value()`` applied to the HTTP path.

Both factory methods on InverterRuntimeData (``from_modbus_registers()``)
and InverterRuntime (HTTP cloud API) are supported. Transport data is
already scaled; HTTP data uses ``scale_runtime_value()`` for fields that
need ÷10 or ÷100 conversion.

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
    # Data Access Helpers
    # ===========================================

    def _raw_float(self, transport_attr: str, http_field: str) -> float | None:
        """Get a float value that is already scaled in both transport and HTTP.

        Use for HTTP fields that need NO scaling (e.g., power values stored
        as-is in the cloud API).  For fields that need scale_runtime_value(),
        use ``_scaled_float()`` instead.
        """
        tr = self._transport_runtime
        if tr is not None:
            val = getattr(tr, transport_attr, None)
            return float(val) if val is not None else None
        if self._runtime is None:
            return None
        val = getattr(self._runtime, http_field, None)
        return float(val) if val is not None else None

    def _raw_int(self, transport_attr: str, http_field: str) -> int | None:
        """Get an integer value that is already scaled in both transport and HTTP."""
        tr = self._transport_runtime
        if tr is not None:
            val = getattr(tr, transport_attr, None)
            return int(val) if val is not None else None
        if self._runtime is None:
            return None
        val = getattr(self._runtime, http_field, None)
        return int(val) if val is not None else None

    def _scaled_float(self, transport_attr: str, http_field: str) -> float | None:
        """Get a float value where the HTTP path needs scale_runtime_value().

        Transport data is already scaled by ``from_modbus_registers()``.
        HTTP data (InverterRuntime) stores raw API ints that need ÷10 or ÷100
        conversion via ``scale_runtime_value(http_field, raw_value)``.
        """
        tr = self._transport_runtime
        if tr is not None:
            val = getattr(tr, transport_attr, None)
            return float(val) if val is not None else None
        if self._runtime is None:
            return None
        raw = getattr(self._runtime, http_field, None)
        if raw is None:
            return None
        return scale_runtime_value(http_field, raw)

    # ===========================================
    # PV (Solar Panel) Properties
    # ===========================================

    @property
    def pv1_voltage(self) -> float | None:
        """Get PV string 1 voltage in volts."""
        return self._scaled_float("pv1_voltage", "vpv1")

    @property
    def pv2_voltage(self) -> float | None:
        """Get PV string 2 voltage in volts."""
        return self._scaled_float("pv2_voltage", "vpv2")

    @property
    def pv3_voltage(self) -> float | None:
        """Get PV string 3 voltage in volts (if available)."""
        return self._scaled_float("pv3_voltage", "vpv3")

    @property
    def pv1_power(self) -> int | None:
        """Get PV string 1 power in watts."""
        return self._raw_int("pv1_power", "ppv1")

    @property
    def pv2_power(self) -> int | None:
        """Get PV string 2 power in watts."""
        return self._raw_int("pv2_power", "ppv2")

    @property
    def pv3_power(self) -> int | None:
        """Get PV string 3 power in watts (if available)."""
        return self._raw_int("pv3_power", "ppv3")

    @property
    def pv_total_power(self) -> int | None:
        """Get total PV power from all strings in watts."""
        return self._raw_int("pv_total_power", "ppv")

    # ===========================================
    # AC Grid Properties
    # ===========================================

    @property
    def grid_voltage_r(self) -> float | None:
        """Get grid AC voltage phase R in volts."""
        return self._scaled_float("grid_voltage_r", "vacr")

    @property
    def grid_voltage_s(self) -> float | None:
        """Get grid AC voltage phase S in volts."""
        return self._scaled_float("grid_voltage_s", "vacs")

    @property
    def grid_voltage_t(self) -> float | None:
        """Get grid AC voltage phase T in volts."""
        return self._scaled_float("grid_voltage_t", "vact")

    @property
    def grid_frequency(self) -> float | None:
        """Get grid AC frequency in Hz."""
        return self._scaled_float("grid_frequency", "fac")

    @property
    def power_factor(self) -> str | None:
        """Get power factor."""
        if self._transport_runtime is not None:
            val = self._transport_runtime.power_factor
            return str(val) if val is not None else None
        if self._runtime is None:
            return None
        return self._runtime.pf

    # ===========================================
    # EPS (Emergency Power Supply) Properties
    # ===========================================

    @property
    def eps_voltage_r(self) -> float | None:
        """Get EPS voltage phase R in volts."""
        return self._scaled_float("eps_voltage_r", "vepsr")

    @property
    def eps_voltage_s(self) -> float | None:
        """Get EPS voltage phase S in volts."""
        return self._scaled_float("eps_voltage_s", "vepss")

    @property
    def eps_voltage_t(self) -> float | None:
        """Get EPS voltage phase T in volts."""
        return self._scaled_float("eps_voltage_t", "vepst")

    @property
    def eps_frequency(self) -> float | None:
        """Get EPS frequency in Hz."""
        return self._scaled_float("eps_frequency", "feps")

    @property
    def eps_power(self) -> int | None:
        """Get EPS power in watts."""
        return self._raw_int("eps_power", "peps")

    @property
    def eps_power_l1(self) -> int:
        """Get EPS L1 power in watts.

        Prefers direct register 129 read when available. Falls back to
        voltage-ratio computation for older firmware or GridBOSS setups.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.eps_l1_power
            if val is not None:
                return val
            return self._compute_eps_leg_power("l1")
        if self._runtime is None:
            return 0
        return self._runtime.pEpsL1N

    @property
    def eps_power_l2(self) -> int:
        """Get EPS L2 power in watts.

        Prefers direct register 130 read when available. Falls back to
        voltage-ratio computation for older firmware or GridBOSS setups.
        """
        if self._transport_runtime is not None:
            val = self._transport_runtime.eps_l2_power
            if val is not None:
                return val
            return self._compute_eps_leg_power("l2")
        if self._runtime is None:
            return 0
        return self._runtime.pEpsL2N

    @property
    def eps_apparent_power_l1(self) -> int | None:
        """Get EPS L1 apparent power in VA (reg 131)."""
        return self._raw_int("eps_l1_apparent_power", "sEpsL1N")

    @property
    def eps_apparent_power_l2(self) -> int | None:
        """Get EPS L2 apparent power in VA (reg 132)."""
        return self._raw_int("eps_l2_apparent_power", "sEpsL2N")

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
        """Get power flowing to grid in watts."""
        return self._raw_int("power_to_grid", "pToGrid")

    @property
    def power_to_user(self) -> int | None:
        """Get power imported from grid in watts (Ptouser)."""
        return self._raw_int("load_power", "pToUser")

    @property
    def inverter_power(self) -> int | None:
        """Get inverter power in watts."""
        return self._raw_int("inverter_power", "pinv")

    @property
    def rectifier_power(self) -> int | None:
        """Get AC charging rectifier power (Prec) in watts.

        This is the power from grid used specifically for AC battery charging,
        NOT the total grid import power. See power_to_user for grid import.
        """
        return self._raw_int("grid_power", "prec")

    # ===========================================
    # Battery Properties
    # ===========================================

    @property
    def battery_voltage(self) -> float | None:
        """Get battery voltage in volts."""
        return self._scaled_float("battery_voltage", "vBat")

    @property
    def battery_charge_power(self) -> int | None:
        """Get battery charging power in watts."""
        return self._raw_int("battery_charge_power", "pCharge")

    @property
    def battery_discharge_power(self) -> int | None:
        """Get battery discharging power in watts."""
        return self._raw_int("battery_discharge_power", "pDisCharge")

    @property
    def battery_power(self) -> int | None:
        """Get net battery power in watts (positive = charging, negative = discharging)."""
        if self._transport_runtime is not None:
            charge = self._transport_runtime.battery_charge_power
            discharge = self._transport_runtime.battery_discharge_power
            if charge is None or discharge is None:
                return None
            return int(charge) - int(discharge)
        if self._runtime is None:
            return None
        return self._runtime.batPower

    @property
    def battery_temperature(self) -> int | None:
        """Get battery temperature in Celsius."""
        return self._raw_int("battery_temperature", "tBat")

    @property
    def max_charge_current(self) -> float | None:
        """Get maximum charge current in amps."""
        return self._scaled_float("bms_charge_current_limit", "maxChgCurr")

    @property
    def max_discharge_current(self) -> float | None:
        """Get maximum discharge current in amps."""
        return self._scaled_float("bms_discharge_current_limit", "maxDischgCurr")

    # ===========================================
    # Temperature Properties
    # ===========================================

    @property
    def inverter_temperature(self) -> int | None:
        """Get inverter internal temperature in Celsius."""
        return self._raw_int("internal_temperature", "tinner")

    @property
    def radiator1_temperature(self) -> int | None:
        """Get radiator 1 temperature in Celsius."""
        return self._raw_int("radiator_temperature_1", "tradiator1")

    @property
    def radiator2_temperature(self) -> int | None:
        """Get radiator 2 temperature in Celsius."""
        return self._raw_int("radiator_temperature_2", "tradiator2")

    # ===========================================
    # Bus Voltage Properties
    # ===========================================

    @property
    def bus1_voltage(self) -> float | None:
        """Get bus 1 voltage in volts."""
        return self._scaled_float("bus_voltage_1", "vBus1")

    @property
    def bus2_voltage(self) -> float | None:
        """Get bus 2 voltage in volts."""
        return self._scaled_float("bus_voltage_2", "vBus2")

    # ===========================================
    # AC Couple & Generator Properties
    # ===========================================

    @property
    def ac_couple_power(self) -> int:
        """Get AC coupled power in watts.

        Prefers register 153 (ac_couple_power) from local transport when
        available.  Falls back to register 123 (generator_power) for
        EG4_HYBRID devices where both registers carry equivalent AC
        couple data.  Cloud path uses acCouplePower field.

        On EG4_OFFGRID (12000XP/6000XP), register 123 is a seconds
        counter — only register 153 is correct.
        """
        if self._transport_runtime is not None:
            # Prefer reg 153 (ac_couple_power) — correct for all families
            val = self._transport_runtime.ac_couple_power
            if val is not None:
                return int(val)
            # Fall back to reg 123 (generator_power) — valid on EG4_HYBRID
            val = self._transport_runtime.generator_power
            return int(val) if val is not None else 0
        if self._runtime is None:
            return 0
        return self._runtime.acCouplePower

    @property
    def generator_voltage(self) -> float | None:
        """Get generator voltage in volts."""
        return self._scaled_float("generator_voltage", "genVolt")

    @property
    def generator_frequency(self) -> float | None:
        """Get generator frequency in Hz."""
        return self._scaled_float("generator_frequency", "genFreq")

    @property
    def generator_power(self) -> int | None:
        """Get generator power in watts."""
        return self._raw_int("generator_power", "genPower")

    @property
    def is_using_generator(self) -> bool:
        """Check if generator is currently in use."""
        if self._transport_runtime is not None:
            val = self._transport_runtime.generator_power
            return val is not None and int(val) > 0
        if self._runtime is None:
            return False
        return self._runtime._12KUsingGenerator

    # ===========================================
    # US Split-Phase Per-Leg Properties (regs 195-204)
    # ===========================================

    @property
    def generator_l1_voltage(self) -> float | None:
        """Get generator L1 voltage in volts (reg 195)."""
        return self._scaled_float("generator_l1_voltage", "genVoltL1")

    @property
    def generator_l2_voltage(self) -> float | None:
        """Get generator L2 voltage in volts (reg 196)."""
        return self._scaled_float("generator_l2_voltage", "genVoltL2")

    @property
    def inverter_power_l1(self) -> int | None:
        """Get inverter power L1 in watts (reg 197)."""
        return self._raw_int("inverter_power_l1", "pinvL1")

    @property
    def inverter_power_l2(self) -> int | None:
        """Get inverter power L2 in watts (reg 198)."""
        return self._raw_int("inverter_power_l2", "pinvL2")

    @property
    def rectifier_power_l1(self) -> int | None:
        """Get rectifier power L1 in watts (reg 199)."""
        return self._raw_int("rectifier_power_l1", "precL1")

    @property
    def rectifier_power_l2(self) -> int | None:
        """Get rectifier power L2 in watts (reg 200)."""
        return self._raw_int("rectifier_power_l2", "precL2")

    @property
    def grid_export_power_l1(self) -> int | None:
        """Get grid export power L1 in watts (reg 201)."""
        return self._raw_int("grid_export_power_l1", "pToGridL1")

    @property
    def grid_export_power_l2(self) -> int | None:
        """Get grid export power L2 in watts (reg 202)."""
        return self._raw_int("grid_export_power_l2", "pToGridL2")

    @property
    def grid_import_power_l1(self) -> int | None:
        """Get grid import power L1 in watts (reg 203)."""
        return self._raw_int("grid_import_power_l1", "pToUserL1")

    @property
    def grid_import_power_l2(self) -> int | None:
        """Get grid import power L2 in watts (reg 204)."""
        return self._raw_int("grid_import_power_l2", "pToUserL2")

    # ===========================================
    # Consumption Properties
    # ===========================================

    @property
    def consumption_power(self) -> int | None:
        """Get consumption power in watts.

        For HTTP data, uses the server-computed consumptionPower field.
        For local transport data (Modbus/Dongle), computes from energy balance:
            consumption = pv + battery_power + grid_import - grid_export

        Where battery_power is signed (positive = discharging, negative = charging).
        This accounts for all power sources (PV, battery, grid) flowing to loads.

        The result is clamped to >= 0 to avoid negative values during edge cases.
        """
        if self._transport_runtime is not None:
            pv = self._transport_runtime.pv_total_power
            grid_import = self._transport_runtime.power_from_grid
            grid_export = self._transport_runtime.power_to_grid
            # Battery power: positive = discharging (adds to consumption)
            # negative = charging (subtracts from consumption)
            bat_discharge = self._transport_runtime.battery_discharge_power
            bat_charge = self._transport_runtime.battery_charge_power

            if all(v is None for v in [pv, grid_import, grid_export, bat_discharge, bat_charge]):
                return None

            # Full energy balance: consumption = pv + battery_power + grid_import - grid_export
            battery_power = int(bat_discharge or 0) - int(bat_charge or 0)
            grid_in = int(grid_import or 0)
            grid_out = int(grid_export or 0)
            consumption = int(pv or 0) + battery_power + grid_in - grid_out
            return max(0, consumption)
        if self._runtime is None:
            return None
        return self._runtime.consumptionPower

    @property
    def total_load_power(self) -> int | None:
        """Get total load power in watts.

        Deprecated: use consumption_power instead, which returns the same data.
        """
        return self.consumption_power

    # ===========================================
    # Status & Info Properties
    # ===========================================

    @property
    def firmware_version(self) -> str:
        """Get firmware version."""
        if self._runtime is None:
            return ""
        return self._runtime.fwCode

    @property
    def status(self) -> int | None:
        """Get inverter status code."""
        return self._raw_int("device_status", "status")

    @property
    def status_text(self) -> str:
        """Get inverter status as text."""
        if self._runtime is None:
            return ""
        return self._runtime.statusText

    @property
    def is_lost(self) -> bool:
        """Check if inverter connection is lost."""
        if self._transport_runtime is not None:
            return False  # Transport connected = not lost
        if self._runtime is None:
            return True  # No data means lost
        return self._runtime.lost

    @property
    def power_rating(self) -> str:
        """Get power rating text (e.g., "16kW")."""
        if self._runtime is None:
            return ""
        return self._runtime.powerRatingText
