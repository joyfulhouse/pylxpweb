"""Hybrid inverter implementation for grid-tied models with battery storage.

This module provides the HybridInverter class for hybrid inverters that support:
- AC charging from grid
- Forced charge/discharge
- EPS (backup) mode
- Time-of-use scheduling
"""

from __future__ import annotations

from pylxpweb.constants import ScheduleType
from pylxpweb.exceptions import LuxpowerDeviceError

from .generic import GenericInverter


class HybridInverter(GenericInverter):
    """Hybrid inverter with grid-tied and battery backup capabilities.

    Extends GenericInverter with hybrid-specific controls:
    - AC charging from grid
    - Forced charge/discharge
    - EPS/backup mode enable/disable
    - Time-based charge/discharge scheduling

    Suitable for models: FlexBOSS21, FlexBOSS18, 18KPV, 12KPV

    Example:
        ```python
        inverter = HybridInverter(
            client=client,
            serial_number="1234567890",
            model="18KPV"
        )

        # Enable AC charging at 50% power up to 100% SOC
        await inverter.set_ac_charge(enabled=True, power_percent=50, soc_limit=100)

        # Enable EPS backup mode
        await inverter.set_eps_enabled(True)

        # Set forced charge
        await inverter.set_forced_charge(True)
        ```
    """

    # ============================================================================
    # Private Helpers
    # ============================================================================

    async def _set_register_bit(self, register: int, bit: int, enabled: bool) -> bool:
        """Read-modify-write a single bit in a register.

        Reads the current register value, sets or clears the specified bit,
        and writes the new value back. Other bits are preserved.

        Args:
            register: Register address
            bit: Bit number to set or clear
            enabled: True to set bit, False to clear

        Returns:
            True if successful
        """
        params = await self.read_parameters(register, 1)
        current_value = params.get(f"reg_{register}", 0)
        new_value = current_value | (1 << bit) if enabled else current_value & ~(1 << bit)
        return await self.write_parameters({register: new_value})

    async def _read_modbus_register(self, register: int) -> int:
        """Read a single register via transport-only Modbus path."""
        value = await self.read_transport_register(register)
        if value is None:
            raise LuxpowerDeviceError(
                f"Register {register} read requires transport mode and a successful Modbus read"
            )
        return int(value)

    async def _write_modbus_register(self, register: int, value: int) -> bool:
        """Write a single register via transport-only Modbus path."""
        success = await self.write_transport_register(register, value)
        if not success:
            raise LuxpowerDeviceError(
                f"Register {register} write requires transport mode and a successful Modbus write"
            )
        return True

    async def _set_modbus_register_bit(self, register: int, bit: int, enabled: bool) -> bool:
        """Read-modify-write a single bit via transport-only Modbus path."""
        current_value = await self._read_modbus_register(register)
        new_value = current_value | (1 << bit) if enabled else current_value & ~(1 << bit)
        return await self._write_modbus_register(register, new_value)

    # ============================================================================
    # Hybrid-Specific Control Operations
    # ============================================================================

    async def get_ac_charge_settings(self) -> dict[str, int | bool]:
        """Get AC charge configuration.

        Returns:
            Dictionary with:
            - enabled: AC charge function enabled
            - power_percent: Charge power (0-100%)
            - soc_limit: Target SOC (0-100%)
            - schedule1_enabled: Time schedule 1 enabled
            - schedule2_enabled: Time schedule 2 enabled

        Example:
            >>> settings = await inverter.get_ac_charge_settings()
            >>> settings
            {
                'enabled': True,
                'power_percent': 50,
                'soc_limit': 100,
                'schedule1_enabled': True,
                'schedule2_enabled': False
            }
        """
        from pylxpweb.constants import (
            FUNC_EN_BIT_AC_CHARGE_EN,
            FUNC_EN_REGISTER,
            HOLD_AC_CHARGE_POWER_CMD,
        )

        # Read function enable register for AC charge bit
        func_params = await self.read_parameters(FUNC_EN_REGISTER, 1)
        func_value = func_params.get(f"reg_{FUNC_EN_REGISTER}", 0)
        ac_charge_enabled = bool(func_value & (1 << FUNC_EN_BIT_AC_CHARGE_EN))

        # Read AC charge parameters
        ac_params = await self.read_parameters(HOLD_AC_CHARGE_POWER_CMD, 8)

        return {
            "enabled": ac_charge_enabled,
            "power_percent": ac_params.get("HOLD_AC_CHARGE_POWER_CMD", 0),
            "soc_limit": ac_params.get("HOLD_AC_CHARGE_SOC_LIMIT", 0),
            "schedule1_enabled": bool(ac_params.get("HOLD_AC_CHARGE_ENABLE_1", 0)),
            "schedule2_enabled": bool(ac_params.get("HOLD_AC_CHARGE_ENABLE_2", 0)),
        }

    async def set_ac_charge(
        self, enabled: bool, power_percent: int | None = None, soc_limit: int | None = None
    ) -> bool:
        """Configure AC charging from grid.

        Args:
            enabled: Enable AC charging
            power_percent: Charge power percentage (0-100), optional
            soc_limit: Target SOC percentage (0-100), optional

        Returns:
            True if successful

        Example:
            >>> # Enable AC charge at 50% power to 100% SOC
            >>> await inverter.set_ac_charge(True, power_percent=50, soc_limit=100)
            True

            >>> # Disable AC charge
            >>> await inverter.set_ac_charge(False)
            True
        """
        from pylxpweb.constants import (
            FUNC_EN_BIT_AC_CHARGE_EN,
            FUNC_EN_REGISTER,
            HOLD_AC_CHARGE_POWER_CMD,
            HOLD_AC_CHARGE_SOC_LIMIT,
        )

        # Validate parameters first (before any API calls)
        if power_percent is not None and not 0 <= power_percent <= 100:
            raise ValueError("power_percent must be between 0 and 100")

        if soc_limit is not None and not 0 <= soc_limit <= 100:
            raise ValueError("soc_limit must be between 0 and 100")

        # Update function enable bit
        func_params = await self.read_parameters(FUNC_EN_REGISTER, 1)
        current_func = func_params.get(f"reg_{FUNC_EN_REGISTER}", 0)

        if enabled:
            new_func = current_func | (1 << FUNC_EN_BIT_AC_CHARGE_EN)
        else:
            new_func = current_func & ~(1 << FUNC_EN_BIT_AC_CHARGE_EN)

        params_to_write = {FUNC_EN_REGISTER: new_func}

        # Add power and SOC limit if provided (already validated)
        if power_percent is not None:
            params_to_write[HOLD_AC_CHARGE_POWER_CMD] = power_percent

        if soc_limit is not None:
            params_to_write[HOLD_AC_CHARGE_SOC_LIMIT] = soc_limit

        return await self.write_parameters(params_to_write)

    async def set_eps_enabled(self, enabled: bool) -> bool:
        """Enable or disable EPS (backup/off-grid) mode.

        Args:
            enabled: True to enable EPS mode, False to disable

        Returns:
            True if successful

        Example:
            >>> await inverter.set_eps_enabled(True)
            True
        """
        from pylxpweb.constants import FUNC_EN_BIT_EPS_EN, FUNC_EN_REGISTER

        return await self._set_register_bit(FUNC_EN_REGISTER, FUNC_EN_BIT_EPS_EN, enabled)

    async def set_forced_charge(self, enabled: bool) -> bool:
        """Enable or disable forced charge mode.

        Forces inverter to charge batteries regardless of time schedule.

        Args:
            enabled: True to enable forced charge, False to disable

        Returns:
            True if successful

        Example:
            >>> await inverter.set_forced_charge(True)
            True
        """
        from pylxpweb.constants import FUNC_EN_BIT_FORCED_CHG_EN, FUNC_EN_REGISTER

        return await self._set_register_bit(FUNC_EN_REGISTER, FUNC_EN_BIT_FORCED_CHG_EN, enabled)

    async def set_forced_discharge(self, enabled: bool) -> bool:
        """Enable or disable forced discharge mode.

        Forces inverter to discharge batteries regardless of time schedule.

        Args:
            enabled: True to enable forced discharge, False to disable

        Returns:
            True if successful

        Example:
            >>> await inverter.set_forced_discharge(True)
            True
        """
        from pylxpweb.constants import FUNC_EN_BIT_FORCED_DISCHG_EN, FUNC_EN_REGISTER

        return await self._set_register_bit(FUNC_EN_REGISTER, FUNC_EN_BIT_FORCED_DISCHG_EN, enabled)

    async def get_charge_discharge_power(self) -> dict[str, int]:
        """Get charge and discharge power settings.

        Returns:
            Dictionary with:
            - charge_power_percent: AC charge power (0-100%)
            - forced_charge_power_percent: Forced charge power (0-100%)

        Example:
            >>> settings = await inverter.get_charge_discharge_power()
            >>> settings
            {'charge_power_percent': 50, 'forced_charge_power_percent': 100}
        """
        from pylxpweb.constants import HOLD_AC_CHARGE_POWER_CMD

        params = await self.read_parameters(HOLD_AC_CHARGE_POWER_CMD, 9)

        return {
            "charge_power_percent": params.get("HOLD_AC_CHARGE_POWER_CMD", 0),
            "forced_charge_power_percent": params.get("HOLD_FORCED_CHG_POWER_CMD", 0),
        }

    async def set_forced_charge_power(self, power_percent: int) -> bool:
        """Set forced charge (PV charge priority) power limit.

        Args:
            power_percent: Forced charge power percentage (0-100)

        Returns:
            True if successful

        Example:
            >>> await inverter.set_forced_charge_power(80)
            True
        """
        from pylxpweb.constants import HOLD_FORCED_CHG_POWER_CMD

        if not 0 <= power_percent <= 100:
            raise ValueError("power_percent must be between 0 and 100")

        return await self.write_parameters({HOLD_FORCED_CHG_POWER_CMD: power_percent})

    # ============================================================================
    # Working Mode Time Schedule Operations (Generic + Type-Specific)
    # ============================================================================
    # Each mode supports 3 time periods (0, 1, 2).
    # Registers use packed time format: value = (hour & 0xFF) | ((minute & 0xFF) << 8)
    # Source: EG4-18KPV-12LV Modbus Protocol specification

    async def _set_schedule(
        self,
        schedule_type: ScheduleType,
        period: int,
        start_hour: int,
        start_minute: int,
        end_hour: int,
        end_minute: int,
    ) -> bool:
        """Set a time period schedule via Modbus (generic helper).

        Args:
            schedule_type: Which schedule to set
            period: Time period index (0, 1, or 2)
            start_hour: Schedule start hour (0-23)
            start_minute: Schedule start minute (0-59)
            end_hour: Schedule end hour (0-23)
            end_minute: Schedule end minute (0-59)

        Returns:
            True if successful

        Raises:
            ValueError: If period, hour, or minute is out of range
        """
        from pylxpweb.constants import SCHEDULE_CONFIGS, pack_time

        if period not in (0, 1, 2):
            raise ValueError(f"period must be 0, 1, or 2, got {period}")

        base_reg = SCHEDULE_CONFIGS[schedule_type].base_register
        start_reg = base_reg + (period * 2)
        end_reg = start_reg + 1

        # Write each register individually — inverter rejects FC16 (write
        # multiple) for schedule registers, only FC06 (write single) works.
        await self.write_parameters({start_reg: pack_time(start_hour, start_minute)})
        await self.write_parameters({end_reg: pack_time(end_hour, end_minute)})
        return True

    async def _get_schedule(self, schedule_type: ScheduleType, period: int) -> dict[str, int]:
        """Read a time period schedule via Modbus (generic helper).

        Args:
            schedule_type: Which schedule to read
            period: Time period index (0, 1, or 2)

        Returns:
            Dictionary with start_hour, start_minute, end_hour, end_minute

        Raises:
            ValueError: If period is not 0, 1, or 2
        """
        from pylxpweb.constants import SCHEDULE_CONFIGS, unpack_time

        if period not in (0, 1, 2):
            raise ValueError(f"period must be 0, 1, or 2, got {period}")

        base_reg = SCHEDULE_CONFIGS[schedule_type].base_register
        start_reg = base_reg + (period * 2)
        params = await self.read_parameters(start_reg, 2)
        start_val = params.get(f"reg_{start_reg}", 0)
        end_val = params.get(f"reg_{start_reg + 1}", 0)
        sh, sm = unpack_time(start_val)
        eh, em = unpack_time(end_val)
        return {"start_hour": sh, "start_minute": sm, "end_hour": eh, "end_minute": em}

    async def set_ac_charge_schedule(
        self,
        period: int,
        start_hour: int,
        start_minute: int,
        end_hour: int,
        end_minute: int,
    ) -> bool:
        """Set AC charge time period schedule.

        Args:
            period: Time period index (0, 1, or 2)
            start_hour: Schedule start hour (0-23)
            start_minute: Schedule start minute (0-59)
            end_hour: Schedule end hour (0-23)
            end_minute: Schedule end minute (0-59)

        Returns:
            True if successful

        Raises:
            ValueError: If period, hour, or minute is out of range

        Example:
            >>> await inverter.set_ac_charge_schedule(0, 23, 0, 7, 0)
            True
        """
        return await self._set_schedule(
            ScheduleType.AC_CHARGE, period, start_hour, start_minute, end_hour, end_minute
        )

    async def get_ac_charge_schedule(self, period: int) -> dict[str, int]:
        """Read AC charge time period schedule.

        Args:
            period: Time period index (0, 1, or 2)

        Returns:
            Dictionary with start_hour, start_minute, end_hour, end_minute

        Raises:
            ValueError: If period is not 0, 1, or 2

        Example:
            >>> schedule = await inverter.get_ac_charge_schedule(0)
            >>> schedule
            {'start_hour': 23, 'start_minute': 0, 'end_hour': 7, 'end_minute': 0}
        """
        return await self._get_schedule(ScheduleType.AC_CHARGE, period)

    async def set_forced_charge_schedule(
        self,
        period: int,
        start_hour: int,
        start_minute: int,
        end_hour: int,
        end_minute: int,
    ) -> bool:
        """Set forced charge (PV charge priority) time period schedule.

        Args:
            period: Time period index (0, 1, or 2)
            start_hour: Schedule start hour (0-23)
            start_minute: Schedule start minute (0-59)
            end_hour: Schedule end hour (0-23)
            end_minute: Schedule end minute (0-59)

        Returns:
            True if successful

        Raises:
            ValueError: If period, hour, or minute is out of range

        Example:
            >>> await inverter.set_forced_charge_schedule(0, 8, 0, 16, 0)
            True
        """
        return await self._set_schedule(
            ScheduleType.FORCED_CHARGE, period, start_hour, start_minute, end_hour, end_minute
        )

    async def get_forced_charge_schedule(self, period: int) -> dict[str, int]:
        """Read forced charge (PV charge priority) time period schedule.

        Args:
            period: Time period index (0, 1, or 2)

        Returns:
            Dictionary with start_hour, start_minute, end_hour, end_minute

        Raises:
            ValueError: If period is not 0, 1, or 2

        Example:
            >>> schedule = await inverter.get_forced_charge_schedule(0)
            >>> schedule
            {'start_hour': 8, 'start_minute': 0, 'end_hour': 16, 'end_minute': 0}
        """
        return await self._get_schedule(ScheduleType.FORCED_CHARGE, period)

    async def set_forced_discharge_schedule(
        self,
        period: int,
        start_hour: int,
        start_minute: int,
        end_hour: int,
        end_minute: int,
    ) -> bool:
        """Set forced discharge time period schedule.

        Args:
            period: Time period index (0, 1, or 2)
            start_hour: Schedule start hour (0-23)
            start_minute: Schedule start minute (0-59)
            end_hour: Schedule end hour (0-23)
            end_minute: Schedule end minute (0-59)

        Returns:
            True if successful

        Raises:
            ValueError: If period, hour, or minute is out of range

        Example:
            >>> await inverter.set_forced_discharge_schedule(0, 16, 0, 21, 0)
            True
        """
        return await self._set_schedule(
            ScheduleType.FORCED_DISCHARGE, period, start_hour, start_minute, end_hour, end_minute
        )

    async def get_forced_discharge_schedule(self, period: int) -> dict[str, int]:
        """Read forced discharge time period schedule.

        Args:
            period: Time period index (0, 1, or 2)

        Returns:
            Dictionary with start_hour, start_minute, end_hour, end_minute

        Raises:
            ValueError: If period is not 0, 1, or 2

        Example:
            >>> schedule = await inverter.get_forced_discharge_schedule(0)
            >>> schedule
            {'start_hour': 16, 'start_minute': 0, 'end_hour': 21, 'end_minute': 0}
        """
        return await self._get_schedule(ScheduleType.FORCED_DISCHARGE, period)

    async def get_ac_charge_type(self) -> int:
        """Get AC charge type (what the charge schedule is based on).

        Returns:
            0 = Time, 1 = SOC/Volt, 2 = Time + SOC/Volt

        Example:
            >>> charge_type = await inverter.get_ac_charge_type()
            >>> charge_type  # 0 = Time, 1 = SOC/Volt, 2 = Time+SOC/Volt
            0
        """
        from pylxpweb.constants import (
            AC_CHARGE_TYPE_MASK,
            AC_CHARGE_TYPE_SHIFT,
            HOLD_AC_CHARGE_TYPE_REGISTER,
        )

        params = await self.read_parameters(HOLD_AC_CHARGE_TYPE_REGISTER, 1)
        raw: int = params.get(f"reg_{HOLD_AC_CHARGE_TYPE_REGISTER}", 0)
        return (raw & AC_CHARGE_TYPE_MASK) >> AC_CHARGE_TYPE_SHIFT

    async def set_ac_charge_type(self, charge_type: int) -> bool:
        """Set AC charge type (what the charge schedule is based on).

        Args:
            charge_type: 0 = Time, 1 = SOC/Volt, 2 = Time + SOC/Volt

        Returns:
            True if successful

        Raises:
            ValueError: If charge_type is not 0, 1, or 2

        Example:
            >>> await inverter.set_ac_charge_type(0)  # Time-based
            True
        """
        from pylxpweb.constants import (
            AC_CHARGE_TYPE_MASK,
            AC_CHARGE_TYPE_SHIFT,
            HOLD_AC_CHARGE_TYPE_REGISTER,
        )

        if charge_type not in (0, 1, 2):
            raise ValueError(f"charge_type must be 0, 1, or 2, got {charge_type}")

        # Read-modify-write to preserve other bits in register 120
        params = await self.read_parameters(HOLD_AC_CHARGE_TYPE_REGISTER, 1)
        current = params.get(f"reg_{HOLD_AC_CHARGE_TYPE_REGISTER}", 0)
        new_value = (current & ~AC_CHARGE_TYPE_MASK) | (charge_type << AC_CHARGE_TYPE_SHIFT)

        return await self.write_parameters({HOLD_AC_CHARGE_TYPE_REGISTER: new_value})

    # ============================================================================
    # AC Charge SOC/Voltage Threshold Operations
    # ============================================================================
    # These thresholds control when AC charging starts/stops based on battery
    # SOC or voltage. Used when charge type is SOC/Volt or Time+SOC/Volt.
    # Registers 158-161, verified via Modbus probe 2026-02-13.

    async def get_ac_charge_soc_limits(self) -> dict[str, int]:
        """Get AC charge start/stop SOC thresholds.

        These control when AC charging starts and stops based on battery SOC.
        Active when charge type is SOC/Volt or Time+SOC/Volt.

        Returns:
            Dictionary with:
            - start_soc: Battery SOC (%) to start AC charging (0-90)
            - end_soc: Battery SOC (%) to stop AC charging (0-100), reg 67

        Example:
            >>> limits = await inverter.get_ac_charge_soc_limits()
            >>> limits
            {'start_soc': 20, 'end_soc': 100}
        """
        from pylxpweb.constants import HOLD_AC_CHARGE_SOC_LIMIT, HOLD_AC_CHARGE_START_SOC

        params = await self.read_parameters(HOLD_AC_CHARGE_START_SOC, 1)
        start_soc: int = params.get(f"reg_{HOLD_AC_CHARGE_START_SOC}", 0)

        # End SOC is register 67 (HOLD_AC_CHARGE_SOC_LIMIT), not 161
        params2 = await self.read_parameters(HOLD_AC_CHARGE_SOC_LIMIT, 1)
        end_soc: int = params2.get(f"reg_{HOLD_AC_CHARGE_SOC_LIMIT}", 0)

        return {"start_soc": start_soc, "end_soc": end_soc}

    async def set_ac_charge_soc_limits(self, start_soc: int, end_soc: int) -> bool:
        """Set AC charge start/stop SOC thresholds.

        Args:
            start_soc: Battery SOC (%) to start AC charging (0-90)
            end_soc: Battery SOC (%) to stop AC charging (0-100), reg 67

        Returns:
            True if successful

        Raises:
            ValueError: If SOC values are out of range

        Example:
            >>> await inverter.set_ac_charge_soc_limits(start_soc=20, end_soc=100)
            True
        """
        from pylxpweb.constants import HOLD_AC_CHARGE_SOC_LIMIT, HOLD_AC_CHARGE_START_SOC

        if not 0 <= start_soc <= 90:
            raise ValueError(f"start_soc must be 0-90, got {start_soc}")
        if not 0 <= end_soc <= 100:
            raise ValueError(f"end_soc must be 0-100, got {end_soc}")

        return await self.write_parameters(
            {HOLD_AC_CHARGE_START_SOC: start_soc, HOLD_AC_CHARGE_SOC_LIMIT: end_soc}
        )

    async def get_ac_charge_voltage_limits(self) -> dict[str, int]:
        """Get AC charge start/stop voltage thresholds.

        These control when AC charging starts and stops based on battery voltage.
        Active when charge type is SOC/Volt or Time+SOC/Volt.

        Returns:
            Dictionary with:
            - start_voltage: Battery voltage (V) to start AC charging
            - end_voltage: Battery voltage (V) to stop AC charging

        Example:
            >>> limits = await inverter.get_ac_charge_voltage_limits()
            >>> limits
            {'start_voltage': 40, 'end_voltage': 58}
        """
        from pylxpweb.constants import HOLD_AC_CHARGE_START_VOLTAGE

        params = await self.read_parameters(HOLD_AC_CHARGE_START_VOLTAGE, 2)
        start_raw: int = params.get(f"reg_{HOLD_AC_CHARGE_START_VOLTAGE}", 0)
        end_raw: int = params.get(f"reg_{HOLD_AC_CHARGE_START_VOLTAGE + 1}", 0)
        return {"start_voltage": start_raw // 10, "end_voltage": end_raw // 10}

    async def set_ac_charge_voltage_limits(self, start_voltage: int, end_voltage: int) -> bool:
        """Set AC charge start/stop voltage thresholds.

        Only whole volt values are accepted (inverter rejects fractional volts).

        Args:
            start_voltage: Battery voltage (V) to start AC charging (39-52)
            end_voltage: Battery voltage (V) to stop AC charging (48-59)

        Returns:
            True if successful

        Raises:
            ValueError: If voltage values are out of range

        Example:
            >>> await inverter.set_ac_charge_voltage_limits(
            ...     start_voltage=40, end_voltage=58
            ... )
            True
        """
        from pylxpweb.constants import HOLD_AC_CHARGE_END_VOLTAGE, HOLD_AC_CHARGE_START_VOLTAGE

        if not isinstance(start_voltage, int):
            raise ValueError(f"start_voltage must be a whole number, got {start_voltage}")
        if not isinstance(end_voltage, int):
            raise ValueError(f"end_voltage must be a whole number, got {end_voltage}")
        if not 39 <= start_voltage <= 52:
            raise ValueError(f"start_voltage must be 39-52V, got {start_voltage}")
        if not 48 <= end_voltage <= 59:
            raise ValueError(f"end_voltage must be 48-59V, got {end_voltage}")

        return await self.write_parameters(
            {
                HOLD_AC_CHARGE_START_VOLTAGE: start_voltage * 10,
                HOLD_AC_CHARGE_END_VOLTAGE: end_voltage * 10,
            }
        )

    # ============================================================================
    # Sporadic Charge Operations
    # ============================================================================
    # Sporadic charge is controlled via register 233, bit 12.
    # Confirmed via web UI toggle + Modbus read on FlexBOSS21 (FAAB-2525).

    async def get_sporadic_charge(self) -> bool:
        """Get sporadic charge enabled state.

        Returns:
            True if sporadic charge is enabled, False otherwise

        Example:
            >>> enabled = await inverter.get_sporadic_charge()
            >>> enabled
            True
        """
        from pylxpweb.constants import FUNC_EN_2_BIT_SPORADIC_CHARGE, FUNC_EN_2_REGISTER

        params = await self.read_parameters(FUNC_EN_2_REGISTER, 1)
        value = params.get(f"reg_{FUNC_EN_2_REGISTER}", 0)
        return bool(value & (1 << FUNC_EN_2_BIT_SPORADIC_CHARGE))

    async def set_sporadic_charge(self, enabled: bool) -> bool:
        """Enable or disable sporadic charge.

        Uses read-modify-write to preserve other bits in register 233.

        Args:
            enabled: True to enable sporadic charge, False to disable

        Returns:
            True if successful

        Example:
            >>> await inverter.set_sporadic_charge(True)
            True
        """
        from pylxpweb.constants import FUNC_EN_2_BIT_SPORADIC_CHARGE, FUNC_EN_2_REGISTER

        return await self._set_register_bit(
            FUNC_EN_2_REGISTER, FUNC_EN_2_BIT_SPORADIC_CHARGE, enabled
        )

    # ============================================================================
    # Charge Last Mode Operations
    # ============================================================================
    # Register 110 bit 4: charge battery only after loads are satisfied.
    # Mapped in inverter_holding.py as "charge_last" (FUNC_CHARGE_LAST).

    async def get_charge_last(self) -> bool:
        """Get charge last mode.

        When enabled, the inverter charges the battery only after house
        loads are satisfied (PV surplus goes to battery).

        Returns:
            True if charge last is enabled

        Example:
            >>> await inverter.get_charge_last()
            False
        """
        from pylxpweb.constants import FUNC_SYS_BIT_CHARGE_LAST, FUNC_SYS_REGISTER

        raw = await self._read_modbus_register(FUNC_SYS_REGISTER)
        return bool(raw & (1 << FUNC_SYS_BIT_CHARGE_LAST))

    async def set_charge_last(self, enabled: bool) -> bool:
        """Enable or disable charge last mode.

        Args:
            enabled: True to charge battery only after loads are satisfied

        Returns:
            True if successful

        Example:
            >>> await inverter.set_charge_last(True)
            True
        """
        from pylxpweb.constants import FUNC_SYS_BIT_CHARGE_LAST, FUNC_SYS_REGISTER

        return await self._set_modbus_register_bit(
            FUNC_SYS_REGISTER, FUNC_SYS_BIT_CHARGE_LAST, enabled
        )

    # ============================================================================
    # Battery Charge/Discharge Control Mode Operations
    # ============================================================================
    # Controls whether battery charge/discharge limits are based on SOC or Voltage.
    # Register 179 bits 9 and 10, confirmed via live toggle 2026-02-18.

    async def get_battery_charge_control(self) -> bool:
        """Get battery charge control mode.

        Returns:
            False = SOC mode, True = Voltage mode

        Example:
            >>> is_voltage = await inverter.get_battery_charge_control()
            >>> is_voltage
            False  # SOC mode
        """
        from pylxpweb.constants import FUNC_EXT_BIT_BAT_CHARGE_CONTROL, FUNC_EXT_REGISTER

        raw = await self._read_modbus_register(FUNC_EXT_REGISTER)
        return bool(raw & (1 << FUNC_EXT_BIT_BAT_CHARGE_CONTROL))

    async def set_battery_charge_control(self, voltage_mode: bool) -> bool:
        """Set battery charge control mode.

        Args:
            voltage_mode: True for Voltage mode, False for SOC mode

        Returns:
            True if successful

        Example:
            >>> await inverter.set_battery_charge_control(voltage_mode=True)
            True
        """
        from pylxpweb.constants import FUNC_EXT_BIT_BAT_CHARGE_CONTROL, FUNC_EXT_REGISTER

        return await self._set_modbus_register_bit(
            FUNC_EXT_REGISTER, FUNC_EXT_BIT_BAT_CHARGE_CONTROL, voltage_mode
        )

    async def get_battery_discharge_control(self) -> bool:
        """Get battery discharge control mode.

        Returns:
            False = SOC mode, True = Voltage mode

        Example:
            >>> is_voltage = await inverter.get_battery_discharge_control()
            >>> is_voltage
            False  # SOC mode
        """
        from pylxpweb.constants import FUNC_EXT_BIT_BAT_DISCHARGE_CONTROL, FUNC_EXT_REGISTER

        raw = await self._read_modbus_register(FUNC_EXT_REGISTER)
        return bool(raw & (1 << FUNC_EXT_BIT_BAT_DISCHARGE_CONTROL))

    async def set_battery_discharge_control(self, voltage_mode: bool) -> bool:
        """Set battery discharge control mode.

        Args:
            voltage_mode: True for Voltage mode, False for SOC mode

        Returns:
            True if successful

        Example:
            >>> await inverter.set_battery_discharge_control(voltage_mode=True)
            True
        """
        from pylxpweb.constants import FUNC_EXT_BIT_BAT_DISCHARGE_CONTROL, FUNC_EXT_REGISTER

        return await self._set_modbus_register_bit(
            FUNC_EXT_REGISTER, FUNC_EXT_BIT_BAT_DISCHARGE_CONTROL, voltage_mode
        )

    # ============================================================================
    # Battery Charge/Discharge Current Limit Operations (Modbus)
    # ============================================================================
    # Register 101: charge current limit in amps (no scaling)
    # Register 102: discharge current limit in amps (no scaling)
    # Confirmed via live Modbus testing 2026-02-18 on FlexBOSS21.

    async def get_charge_current_limit(self) -> int:
        """Get battery charge current limit via Modbus.

        Returns:
            Charge current limit in amps

        Example:
            >>> amps = await inverter.get_charge_current_limit()
            >>> amps
            249
        """
        from pylxpweb.constants import HOLD_LEAD_ACID_CHARGE_RATE

        return await self._read_modbus_register(HOLD_LEAD_ACID_CHARGE_RATE)

    async def set_charge_current_limit(self, current_amps: int) -> bool:
        """Set battery charge current limit via Modbus.

        Args:
            current_amps: Charge current limit in amps (0-250 for FlexBOSS21)

        Returns:
            True if successful

        Example:
            >>> await inverter.set_charge_current_limit(140)
            True
        """
        from pylxpweb.constants import HOLD_LEAD_ACID_CHARGE_RATE

        if current_amps < 0:
            raise ValueError(f"current_amps must be non-negative, got {current_amps}")
        return await self._write_modbus_register(HOLD_LEAD_ACID_CHARGE_RATE, current_amps)

    async def get_discharge_current_limit(self) -> int:
        """Get battery discharge current limit via Modbus.

        Returns:
            Discharge current limit in amps

        Example:
            >>> amps = await inverter.get_discharge_current_limit()
            >>> amps
            249
        """
        from pylxpweb.constants import HOLD_LEAD_ACID_DISCHARGE_RATE

        return await self._read_modbus_register(HOLD_LEAD_ACID_DISCHARGE_RATE)

    async def set_discharge_current_limit(self, current_amps: int) -> bool:
        """Set battery discharge current limit via Modbus.

        Args:
            current_amps: Discharge current limit in amps (0-250 for FlexBOSS21)

        Returns:
            True if successful

        Example:
            >>> await inverter.set_discharge_current_limit(140)
            True
        """
        from pylxpweb.constants import HOLD_LEAD_ACID_DISCHARGE_RATE

        if current_amps < 0:
            raise ValueError(f"current_amps must be non-negative, got {current_amps}")
        return await self._write_modbus_register(HOLD_LEAD_ACID_DISCHARGE_RATE, current_amps)

    # ============================================================================
    # System Charge SOC Limit Operations (Modbus)
    # ============================================================================
    # Register 227: system charge SOC limit (0-100%, or 101 for top balancing)
    # Verified via live testing 2026-01-27 on FlexBOSS21.
    # Active when battery charge control is in SOC mode (reg 179 bit 9 = 0).

    async def get_system_charge_soc_limit(self) -> int:
        """Get system charge SOC limit via Modbus.

        Returns:
            SOC limit percentage (0-100, or 101 for top balancing)

        Example:
            >>> soc = await inverter.get_system_charge_soc_limit()
            >>> soc
            98
        """
        from pylxpweb.constants import HOLD_SYSTEM_CHARGE_SOC_LIMIT

        return await self._read_modbus_register(HOLD_SYSTEM_CHARGE_SOC_LIMIT)

    async def set_system_charge_soc_limit(self, soc_percent: int) -> bool:
        """Set system charge SOC limit via Modbus.

        Args:
            soc_percent: SOC limit (0-100, or 101 for top balancing)

        Returns:
            True if successful

        Raises:
            ValueError: If soc_percent is out of range

        Example:
            >>> await inverter.set_system_charge_soc_limit(98)
            True
        """
        from pylxpweb.constants import HOLD_SYSTEM_CHARGE_SOC_LIMIT

        if not 0 <= soc_percent <= 101:
            raise ValueError(f"soc_percent must be 0-101, got {soc_percent}")
        return await self._write_modbus_register(HOLD_SYSTEM_CHARGE_SOC_LIMIT, soc_percent)

    # ============================================================================
    # System Charge Voltage Limit Operations (Modbus)
    # ============================================================================
    # Register 228: system charge voltage limit in decivolts (×10)
    # Confirmed via live Modbus testing 2026-02-18 on FlexBOSS21.
    # Active when battery charge control is in Voltage mode (reg 179 bit 9).

    async def get_system_charge_volt_limit(self) -> float:
        """Get system charge voltage limit via Modbus.

        Returns:
            Voltage limit in volts (e.g. 58.0)

        Example:
            >>> volts = await inverter.get_system_charge_volt_limit()
            >>> volts
            58.0
        """
        from pylxpweb.constants import HOLD_SYSTEM_CHARGE_VOLT_LIMIT

        raw = await self._read_modbus_register(HOLD_SYSTEM_CHARGE_VOLT_LIMIT)
        return raw / 10.0

    async def set_system_charge_volt_limit(self, voltage: float) -> bool:
        """Set system charge voltage limit via Modbus.

        Args:
            voltage: Voltage limit in volts (e.g. 58.0). Stored as ×10
                     integer (580). Only whole and half-volt values
                     are representable.

        Returns:
            True if successful

        Example:
            >>> await inverter.set_system_charge_volt_limit(58.0)
            True
        """
        from pylxpweb.constants import HOLD_SYSTEM_CHARGE_VOLT_LIMIT

        raw = int(round(voltage * 10))
        if raw <= 0:
            raise ValueError(f"voltage must be positive, got {voltage}")
        return await self._write_modbus_register(HOLD_SYSTEM_CHARGE_VOLT_LIMIT, raw)

    # ============================================================================
    # Discharge Cutoff SOC Operations (Modbus)
    # ============================================================================
    # Register 105: on-grid discharge cutoff SOC (verified)
    # Register 125: off-grid (EPS) discharge cutoff SOC (verified 2026-01-27)

    async def get_on_grid_cutoff_soc(self) -> int:
        """Get on-grid discharge cutoff SOC via Modbus.

        The inverter stops discharging the battery when SOC drops to
        this level while grid-connected.

        Returns:
            Cutoff SOC percentage (10-90)

        Example:
            >>> soc = await inverter.get_on_grid_cutoff_soc()
            >>> soc
            20
        """
        from pylxpweb.constants import HOLD_DISCHG_CUT_OFF_SOC_EOD

        return await self._read_modbus_register(HOLD_DISCHG_CUT_OFF_SOC_EOD)

    async def set_on_grid_cutoff_soc(self, soc_percent: int) -> bool:
        """Set on-grid discharge cutoff SOC via Modbus.

        Args:
            soc_percent: Cutoff SOC percentage (10-90)

        Returns:
            True if successful

        Raises:
            ValueError: If soc_percent is out of range

        Example:
            >>> await inverter.set_on_grid_cutoff_soc(20)
            True
        """
        from pylxpweb.constants import HOLD_DISCHG_CUT_OFF_SOC_EOD

        if not 10 <= soc_percent <= 90:
            raise ValueError(f"soc_percent must be 10-90, got {soc_percent}")
        return await self._write_modbus_register(HOLD_DISCHG_CUT_OFF_SOC_EOD, soc_percent)

    async def get_off_grid_cutoff_soc(self) -> int:
        """Get off-grid (EPS) discharge cutoff SOC via Modbus.

        The inverter stops discharging the battery when SOC drops to
        this level while in off-grid/EPS mode.

        Returns:
            Cutoff SOC percentage (0-100)

        Example:
            >>> soc = await inverter.get_off_grid_cutoff_soc()
            >>> soc
            20
        """
        from pylxpweb.constants import HOLD_SOC_LOW_LIMIT_EPS_DISCHG

        return await self._read_modbus_register(HOLD_SOC_LOW_LIMIT_EPS_DISCHG)

    async def set_off_grid_cutoff_soc(self, soc_percent: int) -> bool:
        """Set off-grid (EPS) discharge cutoff SOC via Modbus.

        Args:
            soc_percent: Cutoff SOC percentage (0-100)

        Returns:
            True if successful

        Raises:
            ValueError: If soc_percent is out of range

        Example:
            >>> await inverter.set_off_grid_cutoff_soc(20)
            True
        """
        from pylxpweb.constants import HOLD_SOC_LOW_LIMIT_EPS_DISCHG

        if not 0 <= soc_percent <= 100:
            raise ValueError(f"soc_percent must be 0-100, got {soc_percent}")
        return await self._write_modbus_register(HOLD_SOC_LOW_LIMIT_EPS_DISCHG, soc_percent)

    # ============================================================================
    # On-Grid Discharge Cutoff Voltage Operations (Modbus)
    # ============================================================================
    # Register 169: on-grid discharge cutoff voltage in decivolts (×10)
    # Confirmed via live Modbus testing 2026-02-18 on FlexBOSS21.

    async def get_on_grid_cutoff_voltage(self) -> float:
        """Get on-grid discharge cutoff voltage via Modbus.

        The inverter stops discharging the battery when its voltage
        drops to this level while grid-connected.

        Returns:
            Cutoff voltage in volts (e.g. 40.0)

        Example:
            >>> volts = await inverter.get_on_grid_cutoff_voltage()
            >>> volts
            40.0
        """
        from pylxpweb.constants import HOLD_ON_GRID_EOD_VOLTAGE

        raw = await self._read_modbus_register(HOLD_ON_GRID_EOD_VOLTAGE)
        return raw / 10.0

    async def set_on_grid_cutoff_voltage(self, voltage: float) -> bool:
        """Set on-grid discharge cutoff voltage via Modbus.

        Args:
            voltage: Cutoff voltage in volts (e.g. 40.0). Stored as ×10.

        Returns:
            True if successful

        Example:
            >>> await inverter.set_on_grid_cutoff_voltage(40.0)
            True
        """
        from pylxpweb.constants import HOLD_ON_GRID_EOD_VOLTAGE

        raw = int(round(voltage * 10))
        if raw <= 0:
            raise ValueError(f"voltage must be positive, got {voltage}")
        return await self._write_modbus_register(HOLD_ON_GRID_EOD_VOLTAGE, raw)

    # ============================================================================
    # Off-Grid Discharge Cutoff Voltage Operations (Modbus)
    # ============================================================================
    # Register 100: off-grid discharge cutoff voltage in decivolts (×10)
    # API name: HOLD_LEAD_ACID_DISCHARGE_CUT_OFF_VOLT
    # Previously mislabeled as HOLD_BAT_VOLT_MIN_CHG ("battery min charge voltage").
    # Confirmed via live Modbus testing 2026-02-18 on FlexBOSS21.

    async def get_off_grid_cutoff_voltage(self) -> float:
        """Get off-grid (EPS) discharge cutoff voltage via Modbus.

        The inverter stops discharging the battery when its voltage
        drops to this level while in off-grid/EPS mode.

        Returns:
            Cutoff voltage in volts (e.g. 40.0)

        Example:
            >>> volts = await inverter.get_off_grid_cutoff_voltage()
            >>> volts
            40.0
        """
        from pylxpweb.constants import HOLD_OFF_GRID_EOD_VOLTAGE

        raw = await self._read_modbus_register(HOLD_OFF_GRID_EOD_VOLTAGE)
        return raw / 10.0

    async def set_off_grid_cutoff_voltage(self, voltage: float) -> bool:
        """Set off-grid (EPS) discharge cutoff voltage via Modbus.

        Args:
            voltage: Cutoff voltage in volts (e.g. 40.0). Stored as ×10.

        Returns:
            True if successful

        Example:
            >>> await inverter.set_off_grid_cutoff_voltage(40.0)
            True
        """
        from pylxpweb.constants import HOLD_OFF_GRID_EOD_VOLTAGE

        raw = int(round(voltage * 10))
        if raw <= 0:
            raise ValueError(f"voltage must be positive, got {voltage}")
        return await self._write_modbus_register(HOLD_OFF_GRID_EOD_VOLTAGE, raw)

    # ============================================================================
    # Discharge Start Threshold Operations (Modbus)
    # ============================================================================
    # Register 116: start battery discharge when grid import exceeds this wattage.
    # Confirmed via live Modbus testing 2026-02-18 on FlexBOSS21.

    async def get_start_discharge_power(self) -> int:
        """Get discharge start threshold (P_import) via Modbus.

        The inverter starts discharging the battery when grid import
        power exceeds this threshold.

        Returns:
            Threshold in watts

        Example:
            >>> watts = await inverter.get_start_discharge_power()
            >>> watts
            100
        """
        from pylxpweb.constants import HOLD_P_TO_USER_START_DISCHG

        return await self._read_modbus_register(HOLD_P_TO_USER_START_DISCHG)

    async def set_start_discharge_power(self, watts: int) -> bool:
        """Set discharge start threshold (P_import) via Modbus.

        Args:
            watts: Start discharging when grid import exceeds this (W)

        Returns:
            True if successful

        Example:
            >>> await inverter.set_start_discharge_power(100)
            True
        """
        from pylxpweb.constants import HOLD_P_TO_USER_START_DISCHG

        if watts < 0:
            raise ValueError(f"watts must be non-negative, got {watts}")
        return await self._write_modbus_register(HOLD_P_TO_USER_START_DISCHG, watts)

    # TODO: Charge priority schedule (regs 76-81) and forced discharge schedule
    # (regs 82-89) are not yet implemented. The existing HOLD_DISCHG_* constants
    # (regs 74-79) are named as "Discharge" but per the EG4-18KPV-12LV Modbus
    # Protocol PDF, these are actually "Charging Priority" (ChgFirst*) registers.
    # The real forced discharge registers start at 82. Additionally, there may be
    # variation in register mappings between Luxpower-branded and EG4-branded
    # inverters — the EG4 PDF is the only verified source, and further investigation
    # is needed across different brands/models. Once the mismapping is investigated
    # and resolved, they can follow the same pattern as set_ac_charge_schedule().
