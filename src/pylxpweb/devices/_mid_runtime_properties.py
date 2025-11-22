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
