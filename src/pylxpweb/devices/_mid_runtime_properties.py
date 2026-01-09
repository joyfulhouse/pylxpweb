"""Runtime properties mixin for MIDDevice (GridBOSS).

This mixin provides properly-scaled property accessors for all GridBOSS
sensor data from the MID device runtime API. All properties return typed,
scaled values with graceful None handling.

Properties are organized by category:
- Voltage Properties (Grid, UPS, Generator - aggregate and per-phase)
- Current Properties (Grid, Load, Generator, UPS - per-phase)
- Power Properties (Grid, Load, Generator, UPS - per-phase and totals)
- Frequency Properties
- Smart Port Status
- System Status & Info
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pylxpweb.constants import scale_mid_frequency, scale_mid_voltage

if TYPE_CHECKING:
    from pylxpweb.models import MidboxRuntime


class MIDRuntimePropertiesMixin:
    """Mixin providing runtime property accessors for MID devices."""

    _runtime: MidboxRuntime | None

    # ===========================================
    # Voltage Properties - Aggregate
    # ===========================================

    @property
    def grid_voltage(self) -> float:
        """Get aggregate grid voltage in volts.

        Returns:
            Grid RMS voltage (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_mid_voltage(self._runtime.midboxData.gridRmsVolt)

    @property
    def ups_voltage(self) -> float:
        """Get aggregate UPS voltage in volts.

        Returns:
            UPS RMS voltage (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_mid_voltage(self._runtime.midboxData.upsRmsVolt)

    @property
    def generator_voltage(self) -> float:
        """Get aggregate generator voltage in volts.

        Returns:
            Generator RMS voltage (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_mid_voltage(self._runtime.midboxData.genRmsVolt)

    # ===========================================
    # Voltage Properties - Grid Per-Phase
    # ===========================================

    @property
    def grid_l1_voltage(self) -> float:
        """Get grid L1 voltage in volts.

        Returns:
            Grid L1 RMS voltage (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_mid_voltage(self._runtime.midboxData.gridL1RmsVolt)

    @property
    def grid_l2_voltage(self) -> float:
        """Get grid L2 voltage in volts.

        Returns:
            Grid L2 RMS voltage (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_mid_voltage(self._runtime.midboxData.gridL2RmsVolt)

    # ===========================================
    # Voltage Properties - UPS Per-Phase
    # ===========================================

    @property
    def ups_l1_voltage(self) -> float:
        """Get UPS L1 voltage in volts.

        Returns:
            UPS L1 RMS voltage (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_mid_voltage(self._runtime.midboxData.upsL1RmsVolt)

    @property
    def ups_l2_voltage(self) -> float:
        """Get UPS L2 voltage in volts.

        Returns:
            UPS L2 RMS voltage (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_mid_voltage(self._runtime.midboxData.upsL2RmsVolt)

    # ===========================================
    # Voltage Properties - Generator Per-Phase
    # ===========================================

    @property
    def generator_l1_voltage(self) -> float:
        """Get generator L1 voltage in volts.

        Returns:
            Generator L1 RMS voltage (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_mid_voltage(self._runtime.midboxData.genL1RmsVolt)

    @property
    def generator_l2_voltage(self) -> float:
        """Get generator L2 voltage in volts.

        Returns:
            Generator L2 RMS voltage (÷10), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_mid_voltage(self._runtime.midboxData.genL2RmsVolt)

    # ===========================================
    # Current Properties - Grid
    # ===========================================

    @property
    def grid_l1_current(self) -> float:
        """Get grid L1 current in amps.

        Returns:
            Grid L1 RMS current (÷100), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0
        return self._runtime.midboxData.gridL1RmsCurr / 100.0

    @property
    def grid_l2_current(self) -> float:
        """Get grid L2 current in amps.

        Returns:
            Grid L2 RMS current (÷100), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0
        return self._runtime.midboxData.gridL2RmsCurr / 100.0

    # ===========================================
    # Current Properties - Load
    # ===========================================

    @property
    def load_l1_current(self) -> float:
        """Get load L1 current in amps.

        Returns:
            Load L1 RMS current (÷100), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0
        return self._runtime.midboxData.loadL1RmsCurr / 100.0

    @property
    def load_l2_current(self) -> float:
        """Get load L2 current in amps.

        Returns:
            Load L2 RMS current (÷100), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0
        return self._runtime.midboxData.loadL2RmsCurr / 100.0

    # ===========================================
    # Current Properties - Generator
    # ===========================================

    @property
    def generator_l1_current(self) -> float:
        """Get generator L1 current in amps.

        Returns:
            Generator L1 RMS current (÷100), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0
        return self._runtime.midboxData.genL1RmsCurr / 100.0

    @property
    def generator_l2_current(self) -> float:
        """Get generator L2 current in amps.

        Returns:
            Generator L2 RMS current (÷100), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0
        return self._runtime.midboxData.genL2RmsCurr / 100.0

    # ===========================================
    # Current Properties - UPS
    # ===========================================

    @property
    def ups_l1_current(self) -> float:
        """Get UPS L1 current in amps.

        Returns:
            UPS L1 RMS current (÷100), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0
        return self._runtime.midboxData.upsL1RmsCurr / 100.0

    @property
    def ups_l2_current(self) -> float:
        """Get UPS L2 current in amps.

        Returns:
            UPS L2 RMS current (÷100), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0
        return self._runtime.midboxData.upsL2RmsCurr / 100.0

    # ===========================================
    # Power Properties - Grid
    # ===========================================

    @property
    def grid_l1_power(self) -> int:
        """Get grid L1 active power in watts.

        Returns:
            Grid L1 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.gridL1ActivePower

    @property
    def grid_l2_power(self) -> int:
        """Get grid L2 active power in watts.

        Returns:
            Grid L2 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.gridL2ActivePower

    @property
    def grid_power(self) -> int:
        """Get total grid power in watts (L1 + L2).

        Returns:
            Total grid power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return (
            self._runtime.midboxData.gridL1ActivePower + self._runtime.midboxData.gridL2ActivePower
        )

    # ===========================================
    # Power Properties - Load
    # ===========================================

    @property
    def load_l1_power(self) -> int:
        """Get load L1 active power in watts.

        Returns:
            Load L1 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.loadL1ActivePower

    @property
    def load_l2_power(self) -> int:
        """Get load L2 active power in watts.

        Returns:
            Load L2 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.loadL2ActivePower

    @property
    def load_power(self) -> int:
        """Get total load power in watts (L1 + L2).

        Returns:
            Total load power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return (
            self._runtime.midboxData.loadL1ActivePower + self._runtime.midboxData.loadL2ActivePower
        )

    # ===========================================
    # Power Properties - Generator
    # ===========================================

    @property
    def generator_l1_power(self) -> int:
        """Get generator L1 active power in watts.

        Returns:
            Generator L1 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.genL1ActivePower

    @property
    def generator_l2_power(self) -> int:
        """Get generator L2 active power in watts.

        Returns:
            Generator L2 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.genL2ActivePower

    @property
    def generator_power(self) -> int:
        """Get total generator power in watts (L1 + L2).

        Returns:
            Total generator power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.genL1ActivePower + self._runtime.midboxData.genL2ActivePower

    # ===========================================
    # Power Properties - UPS
    # ===========================================

    @property
    def ups_l1_power(self) -> int:
        """Get UPS L1 active power in watts.

        Returns:
            UPS L1 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.upsL1ActivePower

    @property
    def ups_l2_power(self) -> int:
        """Get UPS L2 active power in watts.

        Returns:
            UPS L2 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.upsL2ActivePower

    @property
    def ups_power(self) -> int:
        """Get total UPS power in watts (L1 + L2).

        Returns:
            Total UPS power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.upsL1ActivePower + self._runtime.midboxData.upsL2ActivePower

    # ===========================================
    # Power Properties - Hybrid System
    # ===========================================

    @property
    def hybrid_power(self) -> int:
        """Get hybrid system power in watts.

        Returns:
            Hybrid power (combined system power), or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.hybridPower

    # ===========================================
    # Frequency Properties
    # ===========================================

    @property
    def grid_frequency(self) -> float:
        """Get grid frequency in Hz.

        Returns:
            Grid frequency (÷100), or 0.0 if no data.
        """
        if self._runtime is None:
            return 0.0

        return scale_mid_frequency(self._runtime.midboxData.gridFreq)

    # ===========================================
    # Smart Port Status
    # ===========================================

    @property
    def smart_port1_status(self) -> int:
        """Get smart port 1 status.

        Returns:
            Port 1 status code, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.smartPort1Status

    @property
    def smart_port2_status(self) -> int:
        """Get smart port 2 status.

        Returns:
            Port 2 status code, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.smartPort2Status

    @property
    def smart_port3_status(self) -> int:
        """Get smart port 3 status.

        Returns:
            Port 3 status code, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.smartPort3Status

    @property
    def smart_port4_status(self) -> int:
        """Get smart port 4 status.

        Returns:
            Port 4 status code, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.smartPort4Status

    # ===========================================
    # Power Properties - Smart Load 1
    # ===========================================

    @property
    def smart_load1_l1_power(self) -> int:
        """Get Smart Load 1 L1 active power in watts.

        Returns:
            Smart Load 1 L1 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.smartLoad1L1ActivePower

    @property
    def smart_load1_l2_power(self) -> int:
        """Get Smart Load 1 L2 active power in watts.

        Returns:
            Smart Load 1 L2 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.smartLoad1L2ActivePower

    @property
    def smart_load1_power(self) -> int:
        """Get Smart Load 1 total power in watts (L1 + L2).

        Returns:
            Smart Load 1 total power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return (
            self._runtime.midboxData.smartLoad1L1ActivePower
            + self._runtime.midboxData.smartLoad1L2ActivePower
        )

    # ===========================================
    # Power Properties - Smart Load 2
    # ===========================================

    @property
    def smart_load2_l1_power(self) -> int:
        """Get Smart Load 2 L1 active power in watts.

        Returns:
            Smart Load 2 L1 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.smartLoad2L1ActivePower

    @property
    def smart_load2_l2_power(self) -> int:
        """Get Smart Load 2 L2 active power in watts.

        Returns:
            Smart Load 2 L2 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.smartLoad2L2ActivePower

    @property
    def smart_load2_power(self) -> int:
        """Get Smart Load 2 total power in watts (L1 + L2).

        Returns:
            Smart Load 2 total power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return (
            self._runtime.midboxData.smartLoad2L1ActivePower
            + self._runtime.midboxData.smartLoad2L2ActivePower
        )

    # ===========================================
    # Power Properties - Smart Load 3
    # ===========================================

    @property
    def smart_load3_l1_power(self) -> int:
        """Get Smart Load 3 L1 active power in watts.

        Returns:
            Smart Load 3 L1 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.smartLoad3L1ActivePower

    @property
    def smart_load3_l2_power(self) -> int:
        """Get Smart Load 3 L2 active power in watts.

        Returns:
            Smart Load 3 L2 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.smartLoad3L2ActivePower

    @property
    def smart_load3_power(self) -> int:
        """Get Smart Load 3 total power in watts (L1 + L2).

        Returns:
            Smart Load 3 total power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return (
            self._runtime.midboxData.smartLoad3L1ActivePower
            + self._runtime.midboxData.smartLoad3L2ActivePower
        )

    # ===========================================
    # Power Properties - Smart Load 4
    # ===========================================

    @property
    def smart_load4_l1_power(self) -> int:
        """Get Smart Load 4 L1 active power in watts.

        Returns:
            Smart Load 4 L1 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.smartLoad4L1ActivePower

    @property
    def smart_load4_l2_power(self) -> int:
        """Get Smart Load 4 L2 active power in watts.

        Returns:
            Smart Load 4 L2 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.smartLoad4L2ActivePower

    @property
    def smart_load4_power(self) -> int:
        """Get Smart Load 4 total power in watts (L1 + L2).

        Returns:
            Smart Load 4 total power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return (
            self._runtime.midboxData.smartLoad4L1ActivePower
            + self._runtime.midboxData.smartLoad4L2ActivePower
        )

    # ===========================================
    # Power Properties - AC Couple 1
    # ===========================================

    @property
    def ac_couple1_l1_power(self) -> int:
        """Get AC Couple 1 L1 active power in watts.

        Returns:
            AC Couple 1 L1 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.acCouple1L1ActivePower

    @property
    def ac_couple1_l2_power(self) -> int:
        """Get AC Couple 1 L2 active power in watts.

        Returns:
            AC Couple 1 L2 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.acCouple1L2ActivePower

    @property
    def ac_couple1_power(self) -> int:
        """Get AC Couple 1 total power in watts (L1 + L2).

        Returns:
            AC Couple 1 total power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return (
            self._runtime.midboxData.acCouple1L1ActivePower
            + self._runtime.midboxData.acCouple1L2ActivePower
        )

    # ===========================================
    # Power Properties - AC Couple 2
    # ===========================================

    @property
    def ac_couple2_l1_power(self) -> int:
        """Get AC Couple 2 L1 active power in watts.

        Returns:
            AC Couple 2 L1 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.acCouple2L1ActivePower

    @property
    def ac_couple2_l2_power(self) -> int:
        """Get AC Couple 2 L2 active power in watts.

        Returns:
            AC Couple 2 L2 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.acCouple2L2ActivePower

    @property
    def ac_couple2_power(self) -> int:
        """Get AC Couple 2 total power in watts (L1 + L2).

        Returns:
            AC Couple 2 total power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return (
            self._runtime.midboxData.acCouple2L1ActivePower
            + self._runtime.midboxData.acCouple2L2ActivePower
        )

    # ===========================================
    # Power Properties - AC Couple 3
    # ===========================================

    @property
    def ac_couple3_l1_power(self) -> int:
        """Get AC Couple 3 L1 active power in watts.

        Returns:
            AC Couple 3 L1 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.acCouple3L1ActivePower

    @property
    def ac_couple3_l2_power(self) -> int:
        """Get AC Couple 3 L2 active power in watts.

        Returns:
            AC Couple 3 L2 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.acCouple3L2ActivePower

    @property
    def ac_couple3_power(self) -> int:
        """Get AC Couple 3 total power in watts (L1 + L2).

        Returns:
            AC Couple 3 total power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return (
            self._runtime.midboxData.acCouple3L1ActivePower
            + self._runtime.midboxData.acCouple3L2ActivePower
        )

    # ===========================================
    # Power Properties - AC Couple 4
    # ===========================================

    @property
    def ac_couple4_l1_power(self) -> int:
        """Get AC Couple 4 L1 active power in watts.

        Returns:
            AC Couple 4 L1 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.acCouple4L1ActivePower

    @property
    def ac_couple4_l2_power(self) -> int:
        """Get AC Couple 4 L2 active power in watts.

        Returns:
            AC Couple 4 L2 power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.acCouple4L2ActivePower

    @property
    def ac_couple4_power(self) -> int:
        """Get AC Couple 4 total power in watts (L1 + L2).

        Returns:
            AC Couple 4 total power, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return (
            self._runtime.midboxData.acCouple4L1ActivePower
            + self._runtime.midboxData.acCouple4L2ActivePower
        )

    # ===========================================
    # System Status & Info
    # ===========================================

    @property
    def status(self) -> int:
        """Get device status code.

        Returns:
            Status code, or 0 if no data.
        """
        if self._runtime is None:
            return 0
        return self._runtime.midboxData.status

    @property
    def server_time(self) -> str:
        """Get server timestamp.

        Returns:
            Server time string, or empty string if no data.
        """
        if self._runtime is None:
            return ""
        return self._runtime.midboxData.serverTime

    @property
    def device_time(self) -> str:
        """Get device timestamp.

        Returns:
            Device time string, or empty string if no data.
        """
        if self._runtime is None:
            return ""
        return self._runtime.midboxData.deviceTime

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
    def has_data(self) -> bool:
        """Check if device has runtime data.

        Returns:
            True if runtime data is available.
        """
        return self._runtime is not None

    # ===========================================
    # Energy Properties - UPS
    # ===========================================

    @property
    def e_ups_today_l1(self) -> float | None:
        """Get UPS L1 energy today in kWh.

        Returns:
            UPS L1 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eUpsTodayL1
        return val / 10.0 if val is not None else None

    @property
    def e_ups_today_l2(self) -> float | None:
        """Get UPS L2 energy today in kWh.

        Returns:
            UPS L2 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eUpsTodayL2
        return val / 10.0 if val is not None else None

    @property
    def e_ups_total_l1(self) -> float | None:
        """Get UPS L1 lifetime energy in kWh.

        Returns:
            UPS L1 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eUpsTotalL1
        return val / 10.0 if val is not None else None

    @property
    def e_ups_total_l2(self) -> float | None:
        """Get UPS L2 lifetime energy in kWh.

        Returns:
            UPS L2 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eUpsTotalL2
        return val / 10.0 if val is not None else None

    # ===========================================
    # Energy Properties - Grid Export
    # ===========================================

    @property
    def e_to_grid_today_l1(self) -> float | None:
        """Get grid export L1 energy today in kWh.

        Returns:
            Grid export L1 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eToGridTodayL1
        return val / 10.0 if val is not None else None

    @property
    def e_to_grid_today_l2(self) -> float | None:
        """Get grid export L2 energy today in kWh.

        Returns:
            Grid export L2 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eToGridTodayL2
        return val / 10.0 if val is not None else None

    @property
    def e_to_grid_total_l1(self) -> float | None:
        """Get grid export L1 lifetime energy in kWh.

        Returns:
            Grid export L1 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eToGridTotalL1
        return val / 10.0 if val is not None else None

    @property
    def e_to_grid_total_l2(self) -> float | None:
        """Get grid export L2 lifetime energy in kWh.

        Returns:
            Grid export L2 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eToGridTotalL2
        return val / 10.0 if val is not None else None

    # ===========================================
    # Energy Properties - Grid Import
    # ===========================================

    @property
    def e_to_user_today_l1(self) -> float | None:
        """Get grid import L1 energy today in kWh.

        Returns:
            Grid import L1 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eToUserTodayL1
        return val / 10.0 if val is not None else None

    @property
    def e_to_user_today_l2(self) -> float | None:
        """Get grid import L2 energy today in kWh.

        Returns:
            Grid import L2 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eToUserTodayL2
        return val / 10.0 if val is not None else None

    @property
    def e_to_user_total_l1(self) -> float | None:
        """Get grid import L1 lifetime energy in kWh.

        Returns:
            Grid import L1 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eToUserTotalL1
        return val / 10.0 if val is not None else None

    @property
    def e_to_user_total_l2(self) -> float | None:
        """Get grid import L2 lifetime energy in kWh.

        Returns:
            Grid import L2 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eToUserTotalL2
        return val / 10.0 if val is not None else None

    # ===========================================
    # Energy Properties - Load
    # ===========================================

    @property
    def e_load_today_l1(self) -> float | None:
        """Get load L1 energy today in kWh.

        Returns:
            Load L1 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eLoadTodayL1
        return val / 10.0 if val is not None else None

    @property
    def e_load_today_l2(self) -> float | None:
        """Get load L2 energy today in kWh.

        Returns:
            Load L2 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eLoadTodayL2
        return val / 10.0 if val is not None else None

    @property
    def e_load_total_l1(self) -> float | None:
        """Get load L1 lifetime energy in kWh.

        Returns:
            Load L1 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eLoadTotalL1
        return val / 10.0 if val is not None else None

    @property
    def e_load_total_l2(self) -> float | None:
        """Get load L2 lifetime energy in kWh.

        Returns:
            Load L2 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eLoadTotalL2
        return val / 10.0 if val is not None else None

    # ===========================================
    # Energy Properties - AC Couple 1
    # ===========================================

    @property
    def e_ac_couple1_today_l1(self) -> float | None:
        """Get AC Couple 1 L1 energy today in kWh.

        Returns:
            AC Couple 1 L1 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eACcouple1TodayL1
        return val / 10.0 if val is not None else None

    @property
    def e_ac_couple1_today_l2(self) -> float | None:
        """Get AC Couple 1 L2 energy today in kWh.

        Returns:
            AC Couple 1 L2 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eACcouple1TodayL2
        return val / 10.0 if val is not None else None

    @property
    def e_ac_couple1_total_l1(self) -> float | None:
        """Get AC Couple 1 L1 lifetime energy in kWh.

        Returns:
            AC Couple 1 L1 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eACcouple1TotalL1
        return val / 10.0 if val is not None else None

    @property
    def e_ac_couple1_total_l2(self) -> float | None:
        """Get AC Couple 1 L2 lifetime energy in kWh.

        Returns:
            AC Couple 1 L2 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eACcouple1TotalL2
        return val / 10.0 if val is not None else None

    # ===========================================
    # Energy Properties - AC Couple 2
    # ===========================================

    @property
    def e_ac_couple2_today_l1(self) -> float | None:
        """Get AC Couple 2 L1 energy today in kWh.

        Returns:
            AC Couple 2 L1 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eACcouple2TodayL1
        return val / 10.0 if val is not None else None

    @property
    def e_ac_couple2_today_l2(self) -> float | None:
        """Get AC Couple 2 L2 energy today in kWh.

        Returns:
            AC Couple 2 L2 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eACcouple2TodayL2
        return val / 10.0 if val is not None else None

    @property
    def e_ac_couple2_total_l1(self) -> float | None:
        """Get AC Couple 2 L1 lifetime energy in kWh.

        Returns:
            AC Couple 2 L1 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eACcouple2TotalL1
        return val / 10.0 if val is not None else None

    @property
    def e_ac_couple2_total_l2(self) -> float | None:
        """Get AC Couple 2 L2 lifetime energy in kWh.

        Returns:
            AC Couple 2 L2 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eACcouple2TotalL2
        return val / 10.0 if val is not None else None

    # ===========================================
    # Energy Properties - AC Couple 3
    # ===========================================

    @property
    def e_ac_couple3_today_l1(self) -> float | None:
        """Get AC Couple 3 L1 energy today in kWh.

        Returns:
            AC Couple 3 L1 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eACcouple3TodayL1
        return val / 10.0 if val is not None else None

    @property
    def e_ac_couple3_today_l2(self) -> float | None:
        """Get AC Couple 3 L2 energy today in kWh.

        Returns:
            AC Couple 3 L2 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eACcouple3TodayL2
        return val / 10.0 if val is not None else None

    @property
    def e_ac_couple3_total_l1(self) -> float | None:
        """Get AC Couple 3 L1 lifetime energy in kWh.

        Returns:
            AC Couple 3 L1 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eACcouple3TotalL1
        return val / 10.0 if val is not None else None

    @property
    def e_ac_couple3_total_l2(self) -> float | None:
        """Get AC Couple 3 L2 lifetime energy in kWh.

        Returns:
            AC Couple 3 L2 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eACcouple3TotalL2
        return val / 10.0 if val is not None else None

    # ===========================================
    # Energy Properties - AC Couple 4
    # ===========================================

    @property
    def e_ac_couple4_today_l1(self) -> float | None:
        """Get AC Couple 4 L1 energy today in kWh.

        Returns:
            AC Couple 4 L1 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eACcouple4TodayL1
        return val / 10.0 if val is not None else None

    @property
    def e_ac_couple4_today_l2(self) -> float | None:
        """Get AC Couple 4 L2 energy today in kWh.

        Returns:
            AC Couple 4 L2 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eACcouple4TodayL2
        return val / 10.0 if val is not None else None

    @property
    def e_ac_couple4_total_l1(self) -> float | None:
        """Get AC Couple 4 L1 lifetime energy in kWh.

        Returns:
            AC Couple 4 L1 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eACcouple4TotalL1
        return val / 10.0 if val is not None else None

    @property
    def e_ac_couple4_total_l2(self) -> float | None:
        """Get AC Couple 4 L2 lifetime energy in kWh.

        Returns:
            AC Couple 4 L2 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eACcouple4TotalL2
        return val / 10.0 if val is not None else None

    # ===========================================
    # Energy Properties - Smart Load 1
    # ===========================================

    @property
    def e_smart_load1_today_l1(self) -> float | None:
        """Get Smart Load 1 L1 energy today in kWh.

        Returns:
            Smart Load 1 L1 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eSmartLoad1TodayL1
        return val / 10.0 if val is not None else None

    @property
    def e_smart_load1_today_l2(self) -> float | None:
        """Get Smart Load 1 L2 energy today in kWh.

        Returns:
            Smart Load 1 L2 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eSmartLoad1TodayL2
        return val / 10.0 if val is not None else None

    @property
    def e_smart_load1_total_l1(self) -> float | None:
        """Get Smart Load 1 L1 lifetime energy in kWh.

        Returns:
            Smart Load 1 L1 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eSmartLoad1TotalL1
        return val / 10.0 if val is not None else None

    @property
    def e_smart_load1_total_l2(self) -> float | None:
        """Get Smart Load 1 L2 lifetime energy in kWh.

        Returns:
            Smart Load 1 L2 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eSmartLoad1TotalL2
        return val / 10.0 if val is not None else None

    # ===========================================
    # Energy Properties - Smart Load 2
    # ===========================================

    @property
    def e_smart_load2_today_l1(self) -> float | None:
        """Get Smart Load 2 L1 energy today in kWh.

        Returns:
            Smart Load 2 L1 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eSmartLoad2TodayL1
        return val / 10.0 if val is not None else None

    @property
    def e_smart_load2_today_l2(self) -> float | None:
        """Get Smart Load 2 L2 energy today in kWh.

        Returns:
            Smart Load 2 L2 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eSmartLoad2TodayL2
        return val / 10.0 if val is not None else None

    @property
    def e_smart_load2_total_l1(self) -> float | None:
        """Get Smart Load 2 L1 lifetime energy in kWh.

        Returns:
            Smart Load 2 L1 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eSmartLoad2TotalL1
        return val / 10.0 if val is not None else None

    @property
    def e_smart_load2_total_l2(self) -> float | None:
        """Get Smart Load 2 L2 lifetime energy in kWh.

        Returns:
            Smart Load 2 L2 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eSmartLoad2TotalL2
        return val / 10.0 if val is not None else None

    # ===========================================
    # Energy Properties - Smart Load 3
    # ===========================================

    @property
    def e_smart_load3_today_l1(self) -> float | None:
        """Get Smart Load 3 L1 energy today in kWh.

        Returns:
            Smart Load 3 L1 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eSmartLoad3TodayL1
        return val / 10.0 if val is not None else None

    @property
    def e_smart_load3_today_l2(self) -> float | None:
        """Get Smart Load 3 L2 energy today in kWh.

        Returns:
            Smart Load 3 L2 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eSmartLoad3TodayL2
        return val / 10.0 if val is not None else None

    @property
    def e_smart_load3_total_l1(self) -> float | None:
        """Get Smart Load 3 L1 lifetime energy in kWh.

        Returns:
            Smart Load 3 L1 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eSmartLoad3TotalL1
        return val / 10.0 if val is not None else None

    @property
    def e_smart_load3_total_l2(self) -> float | None:
        """Get Smart Load 3 L2 lifetime energy in kWh.

        Returns:
            Smart Load 3 L2 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eSmartLoad3TotalL2
        return val / 10.0 if val is not None else None

    # ===========================================
    # Energy Properties - Smart Load 4
    # ===========================================

    @property
    def e_smart_load4_today_l1(self) -> float | None:
        """Get Smart Load 4 L1 energy today in kWh.

        Returns:
            Smart Load 4 L1 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eSmartLoad4TodayL1
        return val / 10.0 if val is not None else None

    @property
    def e_smart_load4_today_l2(self) -> float | None:
        """Get Smart Load 4 L2 energy today in kWh.

        Returns:
            Smart Load 4 L2 energy today (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eSmartLoad4TodayL2
        return val / 10.0 if val is not None else None

    @property
    def e_smart_load4_total_l1(self) -> float | None:
        """Get Smart Load 4 L1 lifetime energy in kWh.

        Returns:
            Smart Load 4 L1 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eSmartLoad4TotalL1
        return val / 10.0 if val is not None else None

    @property
    def e_smart_load4_total_l2(self) -> float | None:
        """Get Smart Load 4 L2 lifetime energy in kWh.

        Returns:
            Smart Load 4 L2 lifetime energy (÷10), or None if not available.
        """
        if self._runtime is None:
            return None
        val = self._runtime.midboxData.eSmartLoad4TotalL2
        return val / 10.0 if val is not None else None

    # ===========================================
    # Aggregate Energy Properties (L1 + L2)
    # ===========================================

    def _sum_energy(self, l1: float | None, l2: float | None) -> float | None:
        """Sum L1 and L2 energy values, returning None if both are None.

        Args:
            l1: L1 phase energy value or None
            l2: L2 phase energy value or None

        Returns:
            Sum of L1 + L2, treating None as 0, or None if both are None.
        """
        if l1 is None and l2 is None:
            return None
        return (l1 or 0.0) + (l2 or 0.0)

    # UPS Energy Aggregates

    @property
    def e_ups_today(self) -> float | None:
        """Get total UPS energy today in kWh (L1 + L2).

        Returns:
            Total UPS energy today, or None if not available.
        """
        return self._sum_energy(self.e_ups_today_l1, self.e_ups_today_l2)

    @property
    def e_ups_total(self) -> float | None:
        """Get total UPS lifetime energy in kWh (L1 + L2).

        Returns:
            Total UPS lifetime energy, or None if not available.
        """
        return self._sum_energy(self.e_ups_total_l1, self.e_ups_total_l2)

    # Grid Export Energy Aggregates

    @property
    def e_to_grid_today(self) -> float | None:
        """Get total grid export energy today in kWh (L1 + L2).

        Returns:
            Total grid export energy today, or None if not available.
        """
        return self._sum_energy(self.e_to_grid_today_l1, self.e_to_grid_today_l2)

    @property
    def e_to_grid_total(self) -> float | None:
        """Get total grid export lifetime energy in kWh (L1 + L2).

        Returns:
            Total grid export lifetime energy, or None if not available.
        """
        return self._sum_energy(self.e_to_grid_total_l1, self.e_to_grid_total_l2)

    # Grid Import Energy Aggregates

    @property
    def e_to_user_today(self) -> float | None:
        """Get total grid import energy today in kWh (L1 + L2).

        Returns:
            Total grid import energy today, or None if not available.
        """
        return self._sum_energy(self.e_to_user_today_l1, self.e_to_user_today_l2)

    @property
    def e_to_user_total(self) -> float | None:
        """Get total grid import lifetime energy in kWh (L1 + L2).

        Returns:
            Total grid import lifetime energy, or None if not available.
        """
        return self._sum_energy(self.e_to_user_total_l1, self.e_to_user_total_l2)

    # Load Energy Aggregates

    @property
    def e_load_today(self) -> float | None:
        """Get total load energy today in kWh (L1 + L2).

        Returns:
            Total load energy today, or None if not available.
        """
        return self._sum_energy(self.e_load_today_l1, self.e_load_today_l2)

    @property
    def e_load_total(self) -> float | None:
        """Get total load lifetime energy in kWh (L1 + L2).

        Returns:
            Total load lifetime energy, or None if not available.
        """
        return self._sum_energy(self.e_load_total_l1, self.e_load_total_l2)

    # AC Couple 1 Energy Aggregates

    @property
    def e_ac_couple1_today(self) -> float | None:
        """Get total AC Couple 1 energy today in kWh (L1 + L2).

        Returns:
            Total AC Couple 1 energy today, or None if not available.
        """
        return self._sum_energy(self.e_ac_couple1_today_l1, self.e_ac_couple1_today_l2)

    @property
    def e_ac_couple1_total(self) -> float | None:
        """Get total AC Couple 1 lifetime energy in kWh (L1 + L2).

        Returns:
            Total AC Couple 1 lifetime energy, or None if not available.
        """
        return self._sum_energy(self.e_ac_couple1_total_l1, self.e_ac_couple1_total_l2)

    # AC Couple 2 Energy Aggregates

    @property
    def e_ac_couple2_today(self) -> float | None:
        """Get total AC Couple 2 energy today in kWh (L1 + L2).

        Returns:
            Total AC Couple 2 energy today, or None if not available.
        """
        return self._sum_energy(self.e_ac_couple2_today_l1, self.e_ac_couple2_today_l2)

    @property
    def e_ac_couple2_total(self) -> float | None:
        """Get total AC Couple 2 lifetime energy in kWh (L1 + L2).

        Returns:
            Total AC Couple 2 lifetime energy, or None if not available.
        """
        return self._sum_energy(self.e_ac_couple2_total_l1, self.e_ac_couple2_total_l2)

    # AC Couple 3 Energy Aggregates

    @property
    def e_ac_couple3_today(self) -> float | None:
        """Get total AC Couple 3 energy today in kWh (L1 + L2).

        Returns:
            Total AC Couple 3 energy today, or None if not available.
        """
        return self._sum_energy(self.e_ac_couple3_today_l1, self.e_ac_couple3_today_l2)

    @property
    def e_ac_couple3_total(self) -> float | None:
        """Get total AC Couple 3 lifetime energy in kWh (L1 + L2).

        Returns:
            Total AC Couple 3 lifetime energy, or None if not available.
        """
        return self._sum_energy(self.e_ac_couple3_total_l1, self.e_ac_couple3_total_l2)

    # AC Couple 4 Energy Aggregates

    @property
    def e_ac_couple4_today(self) -> float | None:
        """Get total AC Couple 4 energy today in kWh (L1 + L2).

        Returns:
            Total AC Couple 4 energy today, or None if not available.
        """
        return self._sum_energy(self.e_ac_couple4_today_l1, self.e_ac_couple4_today_l2)

    @property
    def e_ac_couple4_total(self) -> float | None:
        """Get total AC Couple 4 lifetime energy in kWh (L1 + L2).

        Returns:
            Total AC Couple 4 lifetime energy, or None if not available.
        """
        return self._sum_energy(self.e_ac_couple4_total_l1, self.e_ac_couple4_total_l2)

    # Smart Load 1 Energy Aggregates

    @property
    def e_smart_load1_today(self) -> float | None:
        """Get total Smart Load 1 energy today in kWh (L1 + L2).

        Returns:
            Total Smart Load 1 energy today, or None if not available.
        """
        return self._sum_energy(self.e_smart_load1_today_l1, self.e_smart_load1_today_l2)

    @property
    def e_smart_load1_total(self) -> float | None:
        """Get total Smart Load 1 lifetime energy in kWh (L1 + L2).

        Returns:
            Total Smart Load 1 lifetime energy, or None if not available.
        """
        return self._sum_energy(self.e_smart_load1_total_l1, self.e_smart_load1_total_l2)

    # Smart Load 2 Energy Aggregates

    @property
    def e_smart_load2_today(self) -> float | None:
        """Get total Smart Load 2 energy today in kWh (L1 + L2).

        Returns:
            Total Smart Load 2 energy today, or None if not available.
        """
        return self._sum_energy(self.e_smart_load2_today_l1, self.e_smart_load2_today_l2)

    @property
    def e_smart_load2_total(self) -> float | None:
        """Get total Smart Load 2 lifetime energy in kWh (L1 + L2).

        Returns:
            Total Smart Load 2 lifetime energy, or None if not available.
        """
        return self._sum_energy(self.e_smart_load2_total_l1, self.e_smart_load2_total_l2)

    # Smart Load 3 Energy Aggregates

    @property
    def e_smart_load3_today(self) -> float | None:
        """Get total Smart Load 3 energy today in kWh (L1 + L2).

        Returns:
            Total Smart Load 3 energy today, or None if not available.
        """
        return self._sum_energy(self.e_smart_load3_today_l1, self.e_smart_load3_today_l2)

    @property
    def e_smart_load3_total(self) -> float | None:
        """Get total Smart Load 3 lifetime energy in kWh (L1 + L2).

        Returns:
            Total Smart Load 3 lifetime energy, or None if not available.
        """
        return self._sum_energy(self.e_smart_load3_total_l1, self.e_smart_load3_total_l2)

    # Smart Load 4 Energy Aggregates

    @property
    def e_smart_load4_today(self) -> float | None:
        """Get total Smart Load 4 energy today in kWh (L1 + L2).

        Returns:
            Total Smart Load 4 energy today, or None if not available.
        """
        return self._sum_energy(self.e_smart_load4_today_l1, self.e_smart_load4_today_l2)

    @property
    def e_smart_load4_total(self) -> float | None:
        """Get total Smart Load 4 lifetime energy in kWh (L1 + L2).

        Returns:
            Total Smart Load 4 lifetime energy, or None if not available.
        """
        return self._sum_energy(self.e_smart_load4_total_l1, self.e_smart_load4_total_l2)
