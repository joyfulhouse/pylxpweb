"""Runtime properties mixin for MIDDevice (GridBOSS).

This mixin provides properly-scaled property accessors for all GridBOSS
sensor data.  ``_transport_runtime`` (a ``MidboxRuntimeData`` dataclass)
is the single data source — it is populated by both the Modbus/Dongle
transport (via ``from_modbus_registers()``) and the HTTP API (via
``from_http_response()``).  Both factory methods produce final, scaled
values (V, A, W, Hz, kWh), so property accessors are simple pass-throughs.

``_runtime`` (``MidboxRuntime``) is only kept for HTTP-only metadata
(firmware version, off-grid status, server/device timestamps).

Helper methods:

- ``_raw_float(transport_attr, http_attr)`` — read a pre-scaled float.
- ``_raw_int(transport_attr, http_attr)`` — read an int (smart port status).

Aggregate properties (e.g. ``grid_power``, ``e_ups_today``) delegate to
per-phase properties so the access logic is handled in one place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pylxpweb.models import MidboxRuntime
    from pylxpweb.transports.data import MidboxRuntimeData


def _safe_sum(*values: int | float | None) -> float | None:
    """Sum values, returning None if all are None, treating individual Nones as 0.

    Note: GridBOSS aggregates (grid_power, ups_power, load_power) use per-phase
    CT summation (L1 + L2) via this helper.  Inverter aggregates use a different
    strategy — energy balance computed in the HA coordinator (coordinator_mixins.py,
    coordinator_local.py).  The two strategies differ because GridBOSS has direct
    CT measurements per phase while inverters only expose total values.
    """
    if all(v is None for v in values):
        return None
    return sum(v for v in values if v is not None)


class MIDRuntimePropertiesMixin:
    """Mixin providing runtime property accessors for MID devices."""

    _runtime: MidboxRuntime | None
    _transport_runtime: MidboxRuntimeData | None

    # ===========================================
    # Data Access Helpers
    # ===========================================

    def _raw_float(self, transport_attr: str, http_attr: str) -> float | None:
        """Get a numeric value that has the same scale in both modes.

        Returns the value as-is (int from HTTP, float from transport).
        Both are subtypes of ``float`` in the Python type system.

        Falls through to HTTP data when the transport value is None,
        supporting hybrid mode where holding register data (parameters)
        may not be loaded yet while HTTP data is already available.
        """
        tr = self._transport_runtime
        if tr is not None:
            val = cast("float | None", getattr(tr, transport_attr, None))
            if val is not None:
                return val
        if self._runtime is None:
            return None
        return cast("float | None", getattr(self._runtime.midboxData, http_attr, None))

    def _raw_int(self, transport_attr: str, http_attr: str) -> int | None:
        """Get an integer value that has the same scale in both modes.

        Falls through to HTTP data when the transport value is None.
        """
        tr = self._transport_runtime
        if tr is not None:
            val = cast("int | None", getattr(tr, transport_attr, None))
            if val is not None:
                return val
        if self._runtime is None:
            return None
        return cast("int | None", getattr(self._runtime.midboxData, http_attr, None))

    # ===========================================
    # Smart Port Power Helper
    # ===========================================

    def _get_ac_couple_power(self, port: int, phase: str) -> float | None:
        """Get AC Couple power for a port, using Smart Load data when in AC Couple mode.

        The EG4 API only provides power data in smartLoad*L*ActivePower fields.
        The acCouple*L*ActivePower fields don't exist in the API response and
        default to 0. When a port is configured for AC Couple mode (status=2),
        we read from the Smart Load fields to get the actual power values.

        For LOCAL mode (Modbus/Dongle), port status registers are not available,
        so status defaults to 0. In this case, we check if Smart Load power is
        non-zero and return it directly, allowing LOCAL mode users to see
        AC Couple power without needing port status.

        Args:
            port: Port number (1-4)
            phase: Phase identifier ("l1" or "l2")

        Returns:
            Power in watts, or None if no data.
        """
        tr = self._transport_runtime
        if tr is not None:
            status: int | None = getattr(tr, f"smart_port_{port}_status", None)
            smart_power: float | None = getattr(tr, f"smart_load_{port}_{phase}_power", None)
            if status == 2:
                return smart_power
            if status in (None, 0) and smart_power is not None and smart_power != 0:
                return smart_power
            return None

        if self._runtime is None:
            return None

        midbox = self._runtime.midboxData
        port_status: int | None = getattr(midbox, f"smartPort{port}Status", None)
        smart_load_power: int | None = getattr(
            midbox, f"smartLoad{port}{phase.upper()}ActivePower", None
        )

        if port_status == 2:
            return smart_load_power
        if port_status in (None, 0) and smart_load_power is not None and smart_load_power != 0:
            return smart_load_power
        return getattr(midbox, f"acCouple{port}{phase.upper()}ActivePower", None)

    # ===========================================
    # Voltage Properties - Aggregate
    # ===========================================

    @property
    def grid_voltage(self) -> float | None:
        """Get aggregate grid voltage in volts."""
        return self._raw_float("grid_voltage", "gridRmsVolt")

    @property
    def ups_voltage(self) -> float | None:
        """Get aggregate UPS voltage in volts."""
        return self._raw_float("ups_voltage", "upsRmsVolt")

    @property
    def generator_voltage(self) -> float | None:
        """Get aggregate generator voltage in volts."""
        return self._raw_float("gen_voltage", "genRmsVolt")

    # ===========================================
    # Voltage Properties - Grid Per-Phase
    # ===========================================

    @property
    def grid_l1_voltage(self) -> float | None:
        """Get grid L1 voltage in volts."""
        return self._raw_float("grid_l1_voltage", "gridL1RmsVolt")

    @property
    def grid_l2_voltage(self) -> float | None:
        """Get grid L2 voltage in volts."""
        return self._raw_float("grid_l2_voltage", "gridL2RmsVolt")

    # ===========================================
    # Voltage Properties - UPS Per-Phase
    # ===========================================

    @property
    def ups_l1_voltage(self) -> float | None:
        """Get UPS L1 voltage in volts."""
        return self._raw_float("ups_l1_voltage", "upsL1RmsVolt")

    @property
    def ups_l2_voltage(self) -> float | None:
        """Get UPS L2 voltage in volts."""
        return self._raw_float("ups_l2_voltage", "upsL2RmsVolt")

    # ===========================================
    # Voltage Properties - Generator Per-Phase
    # ===========================================

    @property
    def generator_l1_voltage(self) -> float | None:
        """Get generator L1 voltage in volts."""
        return self._raw_float("gen_l1_voltage", "genL1RmsVolt")

    @property
    def generator_l2_voltage(self) -> float | None:
        """Get generator L2 voltage in volts."""
        return self._raw_float("gen_l2_voltage", "genL2RmsVolt")

    # ===========================================
    # Current Properties - Grid
    # ===========================================

    @property
    def grid_l1_current(self) -> float | None:
        """Get grid L1 current in amps."""
        return self._raw_float("grid_l1_current", "gridL1RmsCurr")

    @property
    def grid_l2_current(self) -> float | None:
        """Get grid L2 current in amps."""
        return self._raw_float("grid_l2_current", "gridL2RmsCurr")

    # ===========================================
    # Current Properties - Load
    # ===========================================

    @property
    def load_l1_current(self) -> float | None:
        """Get load L1 current in amps."""
        return self._raw_float("load_l1_current", "loadL1RmsCurr")

    @property
    def load_l2_current(self) -> float | None:
        """Get load L2 current in amps."""
        return self._raw_float("load_l2_current", "loadL2RmsCurr")

    # ===========================================
    # Current Properties - Generator
    # ===========================================

    @property
    def generator_l1_current(self) -> float | None:
        """Get generator L1 current in amps."""
        return self._raw_float("gen_l1_current", "genL1RmsCurr")

    @property
    def generator_l2_current(self) -> float | None:
        """Get generator L2 current in amps."""
        return self._raw_float("gen_l2_current", "genL2RmsCurr")

    # ===========================================
    # Current Properties - UPS
    # ===========================================

    @property
    def ups_l1_current(self) -> float | None:
        """Get UPS L1 current in amps."""
        return self._raw_float("ups_l1_current", "upsL1RmsCurr")

    @property
    def ups_l2_current(self) -> float | None:
        """Get UPS L2 current in amps."""
        return self._raw_float("ups_l2_current", "upsL2RmsCurr")

    # ===========================================
    # Power Properties - Per-Phase
    # ===========================================

    @property
    def grid_l1_power(self) -> float | None:
        """Get grid L1 active power in watts."""
        return self._raw_float("grid_l1_power", "gridL1ActivePower")

    @property
    def grid_l2_power(self) -> float | None:
        """Get grid L2 active power in watts."""
        return self._raw_float("grid_l2_power", "gridL2ActivePower")

    @property
    def grid_power(self) -> float | None:
        """Get total grid power in watts (L1 + L2)."""
        return _safe_sum(self.grid_l1_power, self.grid_l2_power)

    @property
    def load_l1_power(self) -> float | None:
        """Get load L1 active power in watts."""
        return self._raw_float("load_l1_power", "loadL1ActivePower")

    @property
    def load_l2_power(self) -> float | None:
        """Get load L2 active power in watts."""
        return self._raw_float("load_l2_power", "loadL2ActivePower")

    @property
    def load_power(self) -> float | None:
        """Get total load power in watts (L1 + L2)."""
        return _safe_sum(self.load_l1_power, self.load_l2_power)

    @property
    def generator_l1_power(self) -> float | None:
        """Get generator L1 active power in watts."""
        return self._raw_float("gen_l1_power", "genL1ActivePower")

    @property
    def generator_l2_power(self) -> float | None:
        """Get generator L2 active power in watts."""
        return self._raw_float("gen_l2_power", "genL2ActivePower")

    @property
    def generator_power(self) -> float | None:
        """Get total generator power in watts (L1 + L2)."""
        return _safe_sum(self.generator_l1_power, self.generator_l2_power)

    @property
    def ups_l1_power(self) -> float | None:
        """Get UPS L1 active power in watts."""
        return self._raw_float("ups_l1_power", "upsL1ActivePower")

    @property
    def ups_l2_power(self) -> float | None:
        """Get UPS L2 active power in watts."""
        return self._raw_float("ups_l2_power", "upsL2ActivePower")

    @property
    def ups_power(self) -> float | None:
        """Get total UPS power in watts (L1 + L2)."""
        return _safe_sum(self.ups_l1_power, self.ups_l2_power)

    @property
    def hybrid_power(self) -> float | None:
        """Get hybrid system power in watts.

        Transport path uses computed_hybrid_power (ups - grid + smart_load_total)
        because no Modbus register exists for hybrid_power.  HTTP-only path
        reads hybridPower directly from the API response.
        """
        tr = self._transport_runtime
        if tr is not None:
            return tr.computed_hybrid_power
        if self._runtime is None:
            return None
        return cast("float | None", getattr(self._runtime.midboxData, "hybridPower", None))

    # ===========================================
    # Frequency Properties
    # ===========================================

    @property
    def phase_lock_frequency(self) -> float | None:
        """Get PLL (phase-lock loop) frequency in Hz."""
        return self._raw_float("phase_lock_freq", "phaseLockFreq")

    @property
    def grid_frequency(self) -> float | None:
        """Get grid frequency in Hz."""
        return self._raw_float("grid_frequency", "gridFreq")

    @property
    def generator_frequency(self) -> float | None:
        """Get generator frequency in Hz."""
        return self._raw_float("gen_frequency", "genFreq")

    # ===========================================
    # Smart Port Status
    # ===========================================

    @property
    def smart_port1_status(self) -> int | None:
        """Get smart port 1 status."""
        return self._raw_int("smart_port_1_status", "smartPort1Status")

    @property
    def smart_port2_status(self) -> int | None:
        """Get smart port 2 status."""
        return self._raw_int("smart_port_2_status", "smartPort2Status")

    @property
    def smart_port3_status(self) -> int | None:
        """Get smart port 3 status."""
        return self._raw_int("smart_port_3_status", "smartPort3Status")

    @property
    def smart_port4_status(self) -> int | None:
        """Get smart port 4 status."""
        return self._raw_int("smart_port_4_status", "smartPort4Status")

    # ===========================================
    # Power Properties - Smart Load 1
    # ===========================================

    @property
    def smart_load1_l1_power(self) -> float | None:
        """Get Smart Load 1 L1 active power in watts."""
        return self._raw_float("smart_load_1_l1_power", "smartLoad1L1ActivePower")

    @property
    def smart_load1_l2_power(self) -> float | None:
        """Get Smart Load 1 L2 active power in watts."""
        return self._raw_float("smart_load_1_l2_power", "smartLoad1L2ActivePower")

    @property
    def smart_load1_power(self) -> float | None:
        """Get Smart Load 1 total power in watts (L1 + L2)."""
        return _safe_sum(self.smart_load1_l1_power, self.smart_load1_l2_power)

    # ===========================================
    # Power Properties - Smart Load 2
    # ===========================================

    @property
    def smart_load2_l1_power(self) -> float | None:
        """Get Smart Load 2 L1 active power in watts."""
        return self._raw_float("smart_load_2_l1_power", "smartLoad2L1ActivePower")

    @property
    def smart_load2_l2_power(self) -> float | None:
        """Get Smart Load 2 L2 active power in watts."""
        return self._raw_float("smart_load_2_l2_power", "smartLoad2L2ActivePower")

    @property
    def smart_load2_power(self) -> float | None:
        """Get Smart Load 2 total power in watts (L1 + L2)."""
        return _safe_sum(self.smart_load2_l1_power, self.smart_load2_l2_power)

    # ===========================================
    # Power Properties - Smart Load 3
    # ===========================================

    @property
    def smart_load3_l1_power(self) -> float | None:
        """Get Smart Load 3 L1 active power in watts."""
        return self._raw_float("smart_load_3_l1_power", "smartLoad3L1ActivePower")

    @property
    def smart_load3_l2_power(self) -> float | None:
        """Get Smart Load 3 L2 active power in watts."""
        return self._raw_float("smart_load_3_l2_power", "smartLoad3L2ActivePower")

    @property
    def smart_load3_power(self) -> float | None:
        """Get Smart Load 3 total power in watts (L1 + L2)."""
        return _safe_sum(self.smart_load3_l1_power, self.smart_load3_l2_power)

    # ===========================================
    # Power Properties - Smart Load 4
    # ===========================================

    @property
    def smart_load4_l1_power(self) -> float | None:
        """Get Smart Load 4 L1 active power in watts."""
        return self._raw_float("smart_load_4_l1_power", "smartLoad4L1ActivePower")

    @property
    def smart_load4_l2_power(self) -> float | None:
        """Get Smart Load 4 L2 active power in watts."""
        return self._raw_float("smart_load_4_l2_power", "smartLoad4L2ActivePower")

    @property
    def smart_load4_power(self) -> float | None:
        """Get Smart Load 4 total power in watts (L1 + L2)."""
        return _safe_sum(self.smart_load4_l1_power, self.smart_load4_l2_power)

    # ===========================================
    # Power Properties - AC Couple 1-4
    # ===========================================

    @property
    def ac_couple1_l1_power(self) -> float | None:
        """Get AC Couple 1 L1 active power in watts."""
        return self._get_ac_couple_power(1, "l1")

    @property
    def ac_couple1_l2_power(self) -> float | None:
        """Get AC Couple 1 L2 active power in watts."""
        return self._get_ac_couple_power(1, "l2")

    @property
    def ac_couple1_power(self) -> float | None:
        """Get AC Couple 1 total power in watts (L1 + L2)."""
        return _safe_sum(self.ac_couple1_l1_power, self.ac_couple1_l2_power)

    @property
    def ac_couple2_l1_power(self) -> float | None:
        """Get AC Couple 2 L1 active power in watts."""
        return self._get_ac_couple_power(2, "l1")

    @property
    def ac_couple2_l2_power(self) -> float | None:
        """Get AC Couple 2 L2 active power in watts."""
        return self._get_ac_couple_power(2, "l2")

    @property
    def ac_couple2_power(self) -> float | None:
        """Get AC Couple 2 total power in watts (L1 + L2)."""
        return _safe_sum(self.ac_couple2_l1_power, self.ac_couple2_l2_power)

    @property
    def ac_couple3_l1_power(self) -> float | None:
        """Get AC Couple 3 L1 active power in watts."""
        return self._get_ac_couple_power(3, "l1")

    @property
    def ac_couple3_l2_power(self) -> float | None:
        """Get AC Couple 3 L2 active power in watts."""
        return self._get_ac_couple_power(3, "l2")

    @property
    def ac_couple3_power(self) -> float | None:
        """Get AC Couple 3 total power in watts (L1 + L2)."""
        return _safe_sum(self.ac_couple3_l1_power, self.ac_couple3_l2_power)

    @property
    def ac_couple4_l1_power(self) -> float | None:
        """Get AC Couple 4 L1 active power in watts."""
        return self._get_ac_couple_power(4, "l1")

    @property
    def ac_couple4_l2_power(self) -> float | None:
        """Get AC Couple 4 L2 active power in watts."""
        return self._get_ac_couple_power(4, "l2")

    @property
    def ac_couple4_power(self) -> float | None:
        """Get AC Couple 4 total power in watts (L1 + L2)."""
        return _safe_sum(self.ac_couple4_l1_power, self.ac_couple4_l2_power)

    # ===========================================
    # System Status & Info
    # ===========================================

    @property
    def status(self) -> int | None:
        """Get device status code (HTTP API only)."""
        if self._runtime is None:
            return None
        return self._runtime.midboxData.status

    @property
    def server_time(self) -> str:
        """Get server timestamp (HTTP API only)."""
        if self._runtime is None:
            return ""
        return self._runtime.midboxData.serverTime

    @property
    def device_time(self) -> str:
        """Get device timestamp (HTTP API only)."""
        if self._runtime is None:
            return ""
        return self._runtime.midboxData.deviceTime

    @property
    def firmware_version(self) -> str:
        """Get firmware version (HTTP API only)."""
        if self._runtime is None:
            return ""
        return self._runtime.fwCode

    @property
    def has_data(self) -> bool:
        """Check if device has runtime data from any source."""
        return self._transport_runtime is not None or self._runtime is not None

    @property
    def is_off_grid(self) -> bool:
        """Check if the system is operating in off-grid/EPS mode.

        Detection order:
        1. Transport ``off_grid`` field (set from HTTP deviceData.isOffGrid)
        2. Modbus fallback: grid_frequency=0 AND grid_voltage<5V = off-grid.
           UPS voltage is NOT a valid signal — UPS CTs always show voltage
           when loads are running, even on-grid.
        3. HTTP-only fallback (no transport): read from MidboxRuntime.deviceData
        """
        tr = self._transport_runtime
        if tr is not None:
            if tr.off_grid is not None:
                return tr.off_grid
            # Modbus fallback: grid frequency=0 AND grid voltage near-zero
            return (
                tr.grid_frequency is not None
                and tr.grid_frequency == 0.0
                and tr.grid_voltage is not None
                and tr.grid_voltage < 5.0
            )
        if self._runtime is None:
            return False
        # HTTP-only fallback: read from MidboxRuntime.deviceData
        dd = self._runtime.deviceData
        if dd is not None:
            return bool(dd.isOffGrid)
        return False

    # ===========================================
    # Energy Properties - Per-Phase
    # ===========================================

    # UPS
    @property
    def e_ups_today_l1(self) -> float | None:
        """Get UPS L1 energy today in kWh."""
        return self._raw_float("ups_energy_today_l1", "eUpsTodayL1")

    @property
    def e_ups_today_l2(self) -> float | None:
        """Get UPS L2 energy today in kWh."""
        return self._raw_float("ups_energy_today_l2", "eUpsTodayL2")

    @property
    def e_ups_total_l1(self) -> float | None:
        """Get UPS L1 lifetime energy in kWh."""
        return self._raw_float("ups_energy_total_l1", "eUpsTotalL1")

    @property
    def e_ups_total_l2(self) -> float | None:
        """Get UPS L2 lifetime energy in kWh."""
        return self._raw_float("ups_energy_total_l2", "eUpsTotalL2")

    # Grid Export
    @property
    def e_to_grid_today_l1(self) -> float | None:
        """Get grid export L1 energy today in kWh."""
        return self._raw_float("to_grid_energy_today_l1", "eToGridTodayL1")

    @property
    def e_to_grid_today_l2(self) -> float | None:
        """Get grid export L2 energy today in kWh."""
        return self._raw_float("to_grid_energy_today_l2", "eToGridTodayL2")

    @property
    def e_to_grid_total_l1(self) -> float | None:
        """Get grid export L1 lifetime energy in kWh."""
        return self._raw_float("to_grid_energy_total_l1", "eToGridTotalL1")

    @property
    def e_to_grid_total_l2(self) -> float | None:
        """Get grid export L2 lifetime energy in kWh."""
        return self._raw_float("to_grid_energy_total_l2", "eToGridTotalL2")

    # Grid Import
    @property
    def e_to_user_today_l1(self) -> float | None:
        """Get grid import L1 energy today in kWh."""
        return self._raw_float("to_user_energy_today_l1", "eToUserTodayL1")

    @property
    def e_to_user_today_l2(self) -> float | None:
        """Get grid import L2 energy today in kWh."""
        return self._raw_float("to_user_energy_today_l2", "eToUserTodayL2")

    @property
    def e_to_user_total_l1(self) -> float | None:
        """Get grid import L1 lifetime energy in kWh."""
        return self._raw_float("to_user_energy_total_l1", "eToUserTotalL1")

    @property
    def e_to_user_total_l2(self) -> float | None:
        """Get grid import L2 lifetime energy in kWh."""
        return self._raw_float("to_user_energy_total_l2", "eToUserTotalL2")

    # Load
    @property
    def e_load_today_l1(self) -> float | None:
        """Get load L1 energy today in kWh."""
        return self._raw_float("load_energy_today_l1", "eLoadTodayL1")

    @property
    def e_load_today_l2(self) -> float | None:
        """Get load L2 energy today in kWh."""
        return self._raw_float("load_energy_today_l2", "eLoadTodayL2")

    @property
    def e_load_total_l1(self) -> float | None:
        """Get load L1 lifetime energy in kWh."""
        return self._raw_float("load_energy_total_l1", "eLoadTotalL1")

    @property
    def e_load_total_l2(self) -> float | None:
        """Get load L2 lifetime energy in kWh."""
        return self._raw_float("load_energy_total_l2", "eLoadTotalL2")

    # AC Couple 1
    @property
    def e_ac_couple1_today_l1(self) -> float | None:
        """Get AC Couple 1 L1 energy today in kWh."""
        return self._raw_float("ac_couple_1_energy_today_l1", "eACcouple1TodayL1")

    @property
    def e_ac_couple1_today_l2(self) -> float | None:
        """Get AC Couple 1 L2 energy today in kWh."""
        return self._raw_float("ac_couple_1_energy_today_l2", "eACcouple1TodayL2")

    @property
    def e_ac_couple1_total_l1(self) -> float | None:
        """Get AC Couple 1 L1 lifetime energy in kWh."""
        return self._raw_float("ac_couple_1_energy_total_l1", "eACcouple1TotalL1")

    @property
    def e_ac_couple1_total_l2(self) -> float | None:
        """Get AC Couple 1 L2 lifetime energy in kWh."""
        return self._raw_float("ac_couple_1_energy_total_l2", "eACcouple1TotalL2")

    # AC Couple 2
    @property
    def e_ac_couple2_today_l1(self) -> float | None:
        """Get AC Couple 2 L1 energy today in kWh."""
        return self._raw_float("ac_couple_2_energy_today_l1", "eACcouple2TodayL1")

    @property
    def e_ac_couple2_today_l2(self) -> float | None:
        """Get AC Couple 2 L2 energy today in kWh."""
        return self._raw_float("ac_couple_2_energy_today_l2", "eACcouple2TodayL2")

    @property
    def e_ac_couple2_total_l1(self) -> float | None:
        """Get AC Couple 2 L1 lifetime energy in kWh."""
        return self._raw_float("ac_couple_2_energy_total_l1", "eACcouple2TotalL1")

    @property
    def e_ac_couple2_total_l2(self) -> float | None:
        """Get AC Couple 2 L2 lifetime energy in kWh."""
        return self._raw_float("ac_couple_2_energy_total_l2", "eACcouple2TotalL2")

    # AC Couple 3
    @property
    def e_ac_couple3_today_l1(self) -> float | None:
        """Get AC Couple 3 L1 energy today in kWh."""
        return self._raw_float("ac_couple_3_energy_today_l1", "eACcouple3TodayL1")

    @property
    def e_ac_couple3_today_l2(self) -> float | None:
        """Get AC Couple 3 L2 energy today in kWh."""
        return self._raw_float("ac_couple_3_energy_today_l2", "eACcouple3TodayL2")

    @property
    def e_ac_couple3_total_l1(self) -> float | None:
        """Get AC Couple 3 L1 lifetime energy in kWh."""
        return self._raw_float("ac_couple_3_energy_total_l1", "eACcouple3TotalL1")

    @property
    def e_ac_couple3_total_l2(self) -> float | None:
        """Get AC Couple 3 L2 lifetime energy in kWh."""
        return self._raw_float("ac_couple_3_energy_total_l2", "eACcouple3TotalL2")

    # AC Couple 4
    @property
    def e_ac_couple4_today_l1(self) -> float | None:
        """Get AC Couple 4 L1 energy today in kWh."""
        return self._raw_float("ac_couple_4_energy_today_l1", "eACcouple4TodayL1")

    @property
    def e_ac_couple4_today_l2(self) -> float | None:
        """Get AC Couple 4 L2 energy today in kWh."""
        return self._raw_float("ac_couple_4_energy_today_l2", "eACcouple4TodayL2")

    @property
    def e_ac_couple4_total_l1(self) -> float | None:
        """Get AC Couple 4 L1 lifetime energy in kWh."""
        return self._raw_float("ac_couple_4_energy_total_l1", "eACcouple4TotalL1")

    @property
    def e_ac_couple4_total_l2(self) -> float | None:
        """Get AC Couple 4 L2 lifetime energy in kWh."""
        return self._raw_float("ac_couple_4_energy_total_l2", "eACcouple4TotalL2")

    # Smart Load 1
    @property
    def e_smart_load1_today_l1(self) -> float | None:
        """Get Smart Load 1 L1 energy today in kWh."""
        return self._raw_float("smart_load_1_energy_today_l1", "eSmartLoad1TodayL1")

    @property
    def e_smart_load1_today_l2(self) -> float | None:
        """Get Smart Load 1 L2 energy today in kWh."""
        return self._raw_float("smart_load_1_energy_today_l2", "eSmartLoad1TodayL2")

    @property
    def e_smart_load1_total_l1(self) -> float | None:
        """Get Smart Load 1 L1 lifetime energy in kWh."""
        return self._raw_float("smart_load_1_energy_total_l1", "eSmartLoad1TotalL1")

    @property
    def e_smart_load1_total_l2(self) -> float | None:
        """Get Smart Load 1 L2 lifetime energy in kWh."""
        return self._raw_float("smart_load_1_energy_total_l2", "eSmartLoad1TotalL2")

    # Smart Load 2
    @property
    def e_smart_load2_today_l1(self) -> float | None:
        """Get Smart Load 2 L1 energy today in kWh."""
        return self._raw_float("smart_load_2_energy_today_l1", "eSmartLoad2TodayL1")

    @property
    def e_smart_load2_today_l2(self) -> float | None:
        """Get Smart Load 2 L2 energy today in kWh."""
        return self._raw_float("smart_load_2_energy_today_l2", "eSmartLoad2TodayL2")

    @property
    def e_smart_load2_total_l1(self) -> float | None:
        """Get Smart Load 2 L1 lifetime energy in kWh."""
        return self._raw_float("smart_load_2_energy_total_l1", "eSmartLoad2TotalL1")

    @property
    def e_smart_load2_total_l2(self) -> float | None:
        """Get Smart Load 2 L2 lifetime energy in kWh."""
        return self._raw_float("smart_load_2_energy_total_l2", "eSmartLoad2TotalL2")

    # Smart Load 3
    @property
    def e_smart_load3_today_l1(self) -> float | None:
        """Get Smart Load 3 L1 energy today in kWh."""
        return self._raw_float("smart_load_3_energy_today_l1", "eSmartLoad3TodayL1")

    @property
    def e_smart_load3_today_l2(self) -> float | None:
        """Get Smart Load 3 L2 energy today in kWh."""
        return self._raw_float("smart_load_3_energy_today_l2", "eSmartLoad3TodayL2")

    @property
    def e_smart_load3_total_l1(self) -> float | None:
        """Get Smart Load 3 L1 lifetime energy in kWh."""
        return self._raw_float("smart_load_3_energy_total_l1", "eSmartLoad3TotalL1")

    @property
    def e_smart_load3_total_l2(self) -> float | None:
        """Get Smart Load 3 L2 lifetime energy in kWh."""
        return self._raw_float("smart_load_3_energy_total_l2", "eSmartLoad3TotalL2")

    # Smart Load 4
    @property
    def e_smart_load4_today_l1(self) -> float | None:
        """Get Smart Load 4 L1 energy today in kWh."""
        return self._raw_float("smart_load_4_energy_today_l1", "eSmartLoad4TodayL1")

    @property
    def e_smart_load4_today_l2(self) -> float | None:
        """Get Smart Load 4 L2 energy today in kWh."""
        return self._raw_float("smart_load_4_energy_today_l2", "eSmartLoad4TodayL2")

    @property
    def e_smart_load4_total_l1(self) -> float | None:
        """Get Smart Load 4 L1 lifetime energy in kWh."""
        return self._raw_float("smart_load_4_energy_total_l1", "eSmartLoad4TotalL1")

    @property
    def e_smart_load4_total_l2(self) -> float | None:
        """Get Smart Load 4 L2 lifetime energy in kWh."""
        return self._raw_float("smart_load_4_energy_total_l2", "eSmartLoad4TotalL2")

    # ===========================================
    # Aggregate Energy Properties (L1 + L2)
    # ===========================================

    def _sum_energy(self, l1: float | None, l2: float | None) -> float | None:
        """Sum L1 and L2 energy values, returning None if both are None."""
        if l1 is None and l2 is None:
            return None
        return (l1 or 0.0) + (l2 or 0.0)

    # UPS Energy Aggregates

    @property
    def e_ups_today(self) -> float | None:
        """Get total UPS energy today in kWh (L1 + L2)."""
        return self._sum_energy(self.e_ups_today_l1, self.e_ups_today_l2)

    @property
    def e_ups_total(self) -> float | None:
        """Get total UPS lifetime energy in kWh (L1 + L2)."""
        return self._sum_energy(self.e_ups_total_l1, self.e_ups_total_l2)

    # Grid Export Energy Aggregates

    @property
    def e_to_grid_today(self) -> float | None:
        """Get total grid export energy today in kWh (L1 + L2)."""
        return self._sum_energy(self.e_to_grid_today_l1, self.e_to_grid_today_l2)

    @property
    def e_to_grid_total(self) -> float | None:
        """Get total grid export lifetime energy in kWh (L1 + L2)."""
        return self._sum_energy(self.e_to_grid_total_l1, self.e_to_grid_total_l2)

    # Grid Import Energy Aggregates

    @property
    def e_to_user_today(self) -> float | None:
        """Get total grid import energy today in kWh (L1 + L2)."""
        return self._sum_energy(self.e_to_user_today_l1, self.e_to_user_today_l2)

    @property
    def e_to_user_total(self) -> float | None:
        """Get total grid import lifetime energy in kWh (L1 + L2)."""
        return self._sum_energy(self.e_to_user_total_l1, self.e_to_user_total_l2)

    # Load Energy Aggregates

    @property
    def e_load_today(self) -> float | None:
        """Get total load energy today in kWh (L1 + L2)."""
        return self._sum_energy(self.e_load_today_l1, self.e_load_today_l2)

    @property
    def e_load_total(self) -> float | None:
        """Get total load lifetime energy in kWh (L1 + L2)."""
        return self._sum_energy(self.e_load_total_l1, self.e_load_total_l2)

    # AC Couple 1 Energy Aggregates

    @property
    def e_ac_couple1_today(self) -> float | None:
        """Get total AC Couple 1 energy today in kWh (L1 + L2)."""
        return self._sum_energy(self.e_ac_couple1_today_l1, self.e_ac_couple1_today_l2)

    @property
    def e_ac_couple1_total(self) -> float | None:
        """Get total AC Couple 1 lifetime energy in kWh (L1 + L2)."""
        return self._sum_energy(self.e_ac_couple1_total_l1, self.e_ac_couple1_total_l2)

    # AC Couple 2 Energy Aggregates

    @property
    def e_ac_couple2_today(self) -> float | None:
        """Get total AC Couple 2 energy today in kWh (L1 + L2)."""
        return self._sum_energy(self.e_ac_couple2_today_l1, self.e_ac_couple2_today_l2)

    @property
    def e_ac_couple2_total(self) -> float | None:
        """Get total AC Couple 2 lifetime energy in kWh (L1 + L2)."""
        return self._sum_energy(self.e_ac_couple2_total_l1, self.e_ac_couple2_total_l2)

    # AC Couple 3 Energy Aggregates

    @property
    def e_ac_couple3_today(self) -> float | None:
        """Get total AC Couple 3 energy today in kWh (L1 + L2)."""
        return self._sum_energy(self.e_ac_couple3_today_l1, self.e_ac_couple3_today_l2)

    @property
    def e_ac_couple3_total(self) -> float | None:
        """Get total AC Couple 3 lifetime energy in kWh (L1 + L2)."""
        return self._sum_energy(self.e_ac_couple3_total_l1, self.e_ac_couple3_total_l2)

    # AC Couple 4 Energy Aggregates

    @property
    def e_ac_couple4_today(self) -> float | None:
        """Get total AC Couple 4 energy today in kWh (L1 + L2)."""
        return self._sum_energy(self.e_ac_couple4_today_l1, self.e_ac_couple4_today_l2)

    @property
    def e_ac_couple4_total(self) -> float | None:
        """Get total AC Couple 4 lifetime energy in kWh (L1 + L2)."""
        return self._sum_energy(self.e_ac_couple4_total_l1, self.e_ac_couple4_total_l2)

    # Smart Load 1 Energy Aggregates

    @property
    def e_smart_load1_today(self) -> float | None:
        """Get total Smart Load 1 energy today in kWh (L1 + L2)."""
        return self._sum_energy(self.e_smart_load1_today_l1, self.e_smart_load1_today_l2)

    @property
    def e_smart_load1_total(self) -> float | None:
        """Get total Smart Load 1 lifetime energy in kWh (L1 + L2)."""
        return self._sum_energy(self.e_smart_load1_total_l1, self.e_smart_load1_total_l2)

    # Smart Load 2 Energy Aggregates

    @property
    def e_smart_load2_today(self) -> float | None:
        """Get total Smart Load 2 energy today in kWh (L1 + L2)."""
        return self._sum_energy(self.e_smart_load2_today_l1, self.e_smart_load2_today_l2)

    @property
    def e_smart_load2_total(self) -> float | None:
        """Get total Smart Load 2 lifetime energy in kWh (L1 + L2)."""
        return self._sum_energy(self.e_smart_load2_total_l1, self.e_smart_load2_total_l2)

    # Smart Load 3 Energy Aggregates

    @property
    def e_smart_load3_today(self) -> float | None:
        """Get total Smart Load 3 energy today in kWh (L1 + L2)."""
        return self._sum_energy(self.e_smart_load3_today_l1, self.e_smart_load3_today_l2)

    @property
    def e_smart_load3_total(self) -> float | None:
        """Get total Smart Load 3 lifetime energy in kWh (L1 + L2)."""
        return self._sum_energy(self.e_smart_load3_total_l1, self.e_smart_load3_total_l2)

    # Smart Load 4 Energy Aggregates

    @property
    def e_smart_load4_today(self) -> float | None:
        """Get total Smart Load 4 energy today in kWh (L1 + L2)."""
        return self._sum_energy(self.e_smart_load4_today_l1, self.e_smart_load4_today_l2)

    @property
    def e_smart_load4_total(self) -> float | None:
        """Get total Smart Load 4 lifetime energy in kWh (L1 + L2)."""
        return self._sum_energy(self.e_smart_load4_total_l1, self.e_smart_load4_total_l2)
