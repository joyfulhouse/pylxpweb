"""Hybrid inverter implementation for grid-tied models with battery storage.

This module provides the HybridInverter class for hybrid inverters that support:
- AC charging from grid
- Forced charge/discharge
- EPS (backup) mode
- Time-of-use scheduling
"""

from __future__ import annotations

from typing import Any

from pylxpweb.constants import ScheduleType
from pylxpweb.exceptions import LuxpowerDeviceError
from pylxpweb.models import BatteryControlMode

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

    @staticmethod
    def _cloud_param_key(register: int, bit: int = 0) -> str:
        """Resolve the cloud API parameter name for a register value or bit.

        Uses ``REGISTER_TO_PARAM_KEYS`` so the cloud (HTTP) path can name the
        register the same way the EG4 API does. For a value register the bit
        index defaults to 0 (the single value key); for a bit field the index
        is the bit position.
        """
        from pylxpweb.constants.registers import REGISTER_TO_PARAM_KEYS

        keys = REGISTER_TO_PARAM_KEYS.get(register)
        if not keys or bit >= len(keys):
            raise LuxpowerDeviceError(
                f"No cloud parameter mapping for register {register} bit {bit}"
            )
        return keys[bit]

    @staticmethod
    def _register_scale_divisor(register: int) -> int:
        """Return the raw→engineering divisor for a value register (default 1).

        The cloud API returns parameter values already in engineering units
        (e.g. ``59.5`` V for a DIV_10 register), whereas the local transport
        returns the raw register integer (e.g. ``595``). This divisor lets the
        cloud path reconstruct the raw value so both transports agree on what
        :meth:`_read_modbus_register` returns.
        """
        from pylxpweb.registers.inverter_holding import BY_ADDRESS

        defs = BY_ADDRESS.get(register)
        if not defs:
            return 1
        return int(defs[0].scale.value)

    async def _read_modbus_register(self, register: int) -> int:
        """Read a single value register, via transport (raw) or cloud (named param).

        Transport mode reads the raw register directly. Cloud mode reads the
        single named value parameter the API exposes for this register. Bit
        fields must use :meth:`_get_register_bit` instead — the cloud API does
        not return a raw 16-bit value for them.
        """
        if self._transport is not None:
            value = await self.read_transport_register(register)
            if value is None:
                raise LuxpowerDeviceError(
                    f"Register {register} read requires a successful Modbus read"
                )
            return int(value)
        if self._client is None:
            raise LuxpowerDeviceError(
                f"Register {register} read requires a transport or a cloud client"
            )
        param_key = self._cloud_param_key(register)
        response = await self._client.api.control.read_parameters(self.serial_number, register, 1)
        # Cloud returns engineering units (possibly a float-like string, e.g.
        # "59.5"); reconstruct the raw register value so callers that re-apply
        # the register scale get the same result as the transport path.
        raw = float(response.parameters.get(param_key, 0))
        return int(round(raw * self._register_scale_divisor(register)))

    async def _write_modbus_register(self, register: int, value: int) -> bool:
        """Write a single raw register value, via transport or cloud.

        Cloud mode writes the raw register value directly (``write_parameters``
        keys by register address), so no name mapping or scaling translation is
        needed — the same raw value used by the transport path is written.
        """
        if self._transport is not None:
            success = await self.write_transport_register(register, value)
            if not success:
                raise LuxpowerDeviceError(
                    f"Register {register} write requires a successful Modbus write"
                )
            return True
        if self._client is None:
            raise LuxpowerDeviceError(
                f"Register {register} write requires a transport or a cloud client"
            )
        response = await self._client.api.control.write_parameters(
            self.serial_number, {register: value}
        )
        return bool(response.success)

    async def _get_register_bit(self, register: int, bit: int) -> bool:
        """Read a single bit, via transport (raw mask) or cloud (named bool param)."""
        if self._transport is not None:
            raw = await self.read_transport_register(register)
            if raw is None:
                raise LuxpowerDeviceError(
                    f"Register {register} read requires a successful Modbus read"
                )
            return bool(raw & (1 << bit))
        if self._client is None:
            raise LuxpowerDeviceError(
                f"Register {register} read requires a transport or a cloud client"
            )
        param_key = self._cloud_param_key(register, bit)
        response = await self._client.api.control.read_parameters(self.serial_number, register, 1)
        return bool(response.parameters.get(param_key, False))

    async def _set_modbus_register_bit(self, register: int, bit: int, enabled: bool) -> bool:
        """Set/clear a single register bit, via transport or cloud.

        Transport mode performs an atomic read-modify-write that preserves the
        other bits. Cloud mode uses the function-control API, which applies the
        bit update server-side (also preserving the other bits) — avoiding a
        read-modify-write race across the slower HTTP round-trip.
        """
        if self._transport is not None:
            current_value = await self._read_modbus_register(register)
            new_value = current_value | (1 << bit) if enabled else current_value & ~(1 << bit)
            return await self._write_modbus_register(register, new_value)
        if self._client is None:
            raise LuxpowerDeviceError(
                f"Register {register} write requires a transport or a cloud client"
            )
        param_key = self._cloud_param_key(register, bit)
        response = await self._client.api.control.control_function(
            self.serial_number, param_key, enabled
        )
        return bool(response.success)

    # ============================================================================
    # Hybrid-Specific Control Operations
    # ============================================================================

    async def get_ac_charge_settings(self) -> dict[str, int | bool]:
        """Get AC charge configuration.

        Returns:
            Dictionary with:
            - enabled: AC charge function enabled
            - power_percent: Charge power (0-100%)
            - soc_limit: Target SOC (0-101%; 101 = never stop)
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
            soc_limit: Target SOC percentage (0-101), optional. 101 = never
                stop AC charging (used for battery cell balancing).

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

        if soc_limit is not None and not 0 <= soc_limit <= 101:
            raise ValueError("soc_limit must be between 0 and 101")

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

        return await self._set_modbus_register_bit(FUNC_EN_REGISTER, FUNC_EN_BIT_EPS_EN, enabled)

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

        return await self._set_modbus_register_bit(
            FUNC_EN_REGISTER, FUNC_EN_BIT_FORCED_CHG_EN, enabled
        )

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

        return await self._set_modbus_register_bit(
            FUNC_EN_REGISTER, FUNC_EN_BIT_FORCED_DISCHG_EN, enabled
        )

    async def get_charge_discharge_power(self) -> dict[str, int]:
        """Get AC charge and forced/PV charge power settings.

        Both values are RAW 100W units (0-150 = 0-15 kW), not percentages.
        The ``*_percent`` dict keys are a legacy misnomer kept for backward
        compatibility; divide by 10 for kW.

        Returns:
            Dictionary with:
            - charge_power_percent: AC charge power, raw 100W units (reg 66)
            - forced_charge_power_percent: Forced/PV charge power, raw 100W
              units (reg 74)

        Example:
            >>> settings = await inverter.get_charge_discharge_power()
            >>> settings
            {'charge_power_percent': 120, 'forced_charge_power_percent': 20}
        """
        from pylxpweb.constants import HOLD_AC_CHARGE_POWER_CMD

        params = await self.read_parameters(HOLD_AC_CHARGE_POWER_CMD, 9)

        return {
            "charge_power_percent": params.get("HOLD_AC_CHARGE_POWER_CMD", 0),
            "forced_charge_power_percent": params.get("HOLD_FORCED_CHG_POWER_CMD", 0),
        }

    async def set_forced_charge_power(self, power_100w: int) -> bool:
        """Set forced charge (PV charge priority) power limit.

        Register 74 stores RAW 100W units (0-150 = 0-15 kW), not a percentage
        — same encoding as AC charge power (reg 66). e.g. ``20`` -> 2.0 kW.

        Args:
            power_100w: Forced charge power in 100W units (0-150 = 0-15 kW).

        Returns:
            True if successful

        Example:
            >>> await inverter.set_forced_charge_power(20)  # 2.0 kW
            True
        """
        from pylxpweb.constants import HOLD_FORCED_CHG_POWER_CMD

        if not 0 <= power_100w <= 150:
            raise ValueError("power_100w must be between 0 and 150 (0-15 kW)")

        return await self.write_parameters({HOLD_FORCED_CHG_POWER_CMD: power_100w})

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
        """Set a time period schedule (generic helper, transport or cloud).

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

        Note:
            Local (Modbus) mode writes the packed-time registers directly via
            FC06.  Cloud mode has no raw ``reg_<n>`` schedule write — the API
            models schedules as named per-field params
            (``{cloud_prefix}_START_HOUR`` etc.), the same convention the cloud
            getter reads back (PR #205).  Writing a packed-time value to a raw
            register address would not round-trip through the named getter, so
            the cloud path delegates to the tested cloud setter, mirroring
            :meth:`_get_schedule`'s cloud delegation.
        """
        from pylxpweb.constants import SCHEDULE_CONFIGS, pack_time

        config = SCHEDULE_CONFIGS[schedule_type]
        if not 0 <= period < config.periods:
            raise ValueError(f"period must be 0-{config.periods - 1}, got {period}")

        if self._transport is None:
            if self._client is None:
                raise LuxpowerDeviceError(
                    "Setting a schedule requires a transport or a cloud client"
                )
            response = await self._client.api.control._set_schedule(
                self.serial_number,
                schedule_type,
                period,
                start_hour,
                start_minute,
                end_hour,
                end_minute,
            )
            return response.success

        base_reg = config.base_register
        start_reg = base_reg + (period * 2)
        end_reg = start_reg + 1

        # Write each register individually — inverter rejects FC16 (write
        # multiple) for schedule registers, only FC06 (write single) works.
        await self.write_parameters({start_reg: pack_time(start_hour, start_minute)})
        await self.write_parameters({end_reg: pack_time(end_hour, end_minute)})
        return True

    async def _get_schedule(self, schedule_type: ScheduleType, period: int) -> dict[str, int]:
        """Read a time period schedule (generic helper, transport or cloud).

        Args:
            schedule_type: Which schedule to read
            period: Time period index (0, 1, or 2)

        Returns:
            Dictionary with start_hour, start_minute, end_hour, end_minute

        Raises:
            ValueError: If period is not 0, 1, or 2

        Note:
            Local (Modbus) mode reads the packed-time registers directly. Cloud
            mode has no ``reg_<n>`` keys — the API returns named schedule params
            (``{cloud_prefix}_START_HOUR`` etc.), so it delegates to the cloud
            endpoint getter, which mirrors the cloud setter's named-field
            convention.
        """
        from pylxpweb.constants import SCHEDULE_CONFIGS, unpack_time

        config = SCHEDULE_CONFIGS[schedule_type]
        if not 0 <= period < config.periods:
            raise ValueError(f"period must be 0-{config.periods - 1}, got {period}")

        if self._transport is None:
            if self._client is None:
                raise LuxpowerDeviceError(
                    "Reading a schedule requires a transport or a cloud client"
                )
            return await self._client.api.control._get_schedule(
                self.serial_number, schedule_type, period
            )

        base_reg = config.base_register
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

    async def set_ac_first_schedule(
        self,
        period: int,
        start_hour: int,
        start_minute: int,
        end_hour: int,
        end_minute: int,
    ) -> bool:
        """Set AC first time period schedule (off-grid/SNA working mode).

        Registers 152-157 (packed hour|minute per register), verified by the
        live SNA12K-US register probe (docs/inverters/SNA12KUS_52XXXXXX68.json).

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
            >>> await inverter.set_ac_first_schedule(0, 8, 0, 16, 0)
            True
        """
        return await self._set_schedule(
            ScheduleType.AC_FIRST, period, start_hour, start_minute, end_hour, end_minute
        )

    async def get_ac_first_schedule(self, period: int) -> dict[str, int]:
        """Read AC first time period schedule (off-grid/SNA working mode).

        Args:
            period: Time period index (0, 1, or 2)

        Returns:
            Dictionary with start_hour, start_minute, end_hour, end_minute

        Raises:
            ValueError: If period is not 0, 1, or 2

        Example:
            >>> schedule = await inverter.get_ac_first_schedule(0)
            >>> schedule
            {'start_hour': 8, 'start_minute': 0, 'end_hour': 16, 'end_minute': 0}
        """
        return await self._get_schedule(ScheduleType.AC_FIRST, period)

    async def set_gen_charge_schedule(
        self,
        period: int,
        start_hour: int,
        start_minute: int,
        end_hour: int,
        end_minute: int,
    ) -> bool:
        """Set Generator charge time period schedule (regs 256-259, 2 windows).

        Args:
            period: Time period index (0 or 1)
            start_hour: Schedule start hour (0-23)
            start_minute: Schedule start minute (0-59)
            end_hour: Schedule end hour (0-23)
            end_minute: Schedule end minute (0-59)

        Returns:
            True if successful

        Raises:
            ValueError: If period, hour, or minute is out of range
        """
        return await self._set_schedule(
            ScheduleType.GEN_CHARGE, period, start_hour, start_minute, end_hour, end_minute
        )

    async def get_gen_charge_schedule(self, period: int) -> dict[str, int]:
        """Read Generator charge time period schedule (regs 256-259, 2 windows).

        Args:
            period: Time period index (0 or 1)

        Returns:
            Dictionary with start_hour, start_minute, end_hour, end_minute

        Raises:
            ValueError: If period is out of range
        """
        return await self._get_schedule(ScheduleType.GEN_CHARGE, period)

    async def set_off_grid_schedule(
        self,
        period: int,
        start_hour: int,
        start_minute: int,
        end_hour: int,
        end_minute: int,
    ) -> bool:
        """Set Off-Grid time period schedule (regs 269-274, 3 windows).

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
        """
        return await self._set_schedule(
            ScheduleType.OFF_GRID, period, start_hour, start_minute, end_hour, end_minute
        )

    async def get_off_grid_schedule(self, period: int) -> dict[str, int]:
        """Read Off-Grid time period schedule (regs 269-274, 3 windows).

        Args:
            period: Time period index (0, 1, or 2)

        Returns:
            Dictionary with start_hour, start_minute, end_hour, end_minute

        Raises:
            ValueError: If period is out of range
        """
        return await self._get_schedule(ScheduleType.OFF_GRID, period)

    async def set_peak_shaving_schedule(
        self,
        period: int,
        start_hour: int,
        start_minute: int,
        end_hour: int,
        end_minute: int,
    ) -> bool:
        """Set Peak Shaving time period schedule (regs 209-212, 2 windows).

        Args:
            period: Time period index (0 or 1)
            start_hour: Schedule start hour (0-23)
            start_minute: Schedule start minute (0-59)
            end_hour: Schedule end hour (0-23)
            end_minute: Schedule end minute (0-59)

        Returns:
            True if successful

        Raises:
            ValueError: If period, hour, or minute is out of range
        """
        return await self._set_schedule(
            ScheduleType.PEAK_SHAVING, period, start_hour, start_minute, end_hour, end_minute
        )

    async def get_peak_shaving_schedule(self, period: int) -> dict[str, int]:
        """Read Peak Shaving time period schedule (regs 209-212, 2 windows).

        Args:
            period: Time period index (0 or 1)

        Returns:
            Dictionary with start_hour, start_minute, end_hour, end_minute

        Raises:
            ValueError: If period is out of range
        """
        return await self._get_schedule(ScheduleType.PEAK_SHAVING, period)

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
            - end_soc: Battery SOC (%) to stop AC charging (0-101; 101 = never
              stop), reg 67

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
            end_soc: Battery SOC (%) to stop AC charging (0-101), reg 67.
                101 = never stop AC charging (used for cell balancing).

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
        if not 0 <= end_soc <= 101:
            raise ValueError(f"end_soc must be 0-101, got {end_soc}")

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

        return await self._set_modbus_register_bit(
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

        return await self._get_register_bit(FUNC_SYS_REGISTER, FUNC_SYS_BIT_CHARGE_LAST)

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

        return await self._get_register_bit(FUNC_EXT_REGISTER, FUNC_EXT_BIT_BAT_CHARGE_CONTROL)

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

        return await self._get_register_bit(FUNC_EXT_REGISTER, FUNC_EXT_BIT_BAT_DISCHARGE_CONTROL)

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

    # -- Friendly mode-aware helpers ------------------------------------------
    # These wrap the raw bool primitives above with the BatteryControlMode enum
    # and derive the currently-active limit from the live regime, so callers do
    # not re-implement the "which register is active" logic.

    async def get_battery_charge_control_mode(self) -> BatteryControlMode:
        """Get the battery charge control regime as a :class:`BatteryControlMode`.

        Friendly wrapper over :meth:`get_battery_charge_control` (which returns a
        raw bool). Works in cloud, hybrid and local modes.
        """
        return BatteryControlMode.from_voltage_flag(await self.get_battery_charge_control())

    async def set_battery_charge_control_mode(self, mode: BatteryControlMode) -> bool:
        """Set the battery charge control regime (SOC or Voltage)."""
        return await self.set_battery_charge_control(mode.is_voltage)

    async def get_battery_discharge_control_mode(self) -> BatteryControlMode:
        """Get the battery discharge control regime as a :class:`BatteryControlMode`."""
        return BatteryControlMode.from_voltage_flag(await self.get_battery_discharge_control())

    async def set_battery_discharge_control_mode(self, mode: BatteryControlMode) -> bool:
        """Set the battery discharge control regime (SOC or Voltage)."""
        return await self.set_battery_discharge_control(mode.is_voltage)

    async def get_active_charge_limit(self) -> dict[str, Any]:
        """Return the charge ceiling the inverter is currently honoring.

        Derives from the live charge regime (reg 179 bit 9): SOC mode → system
        charge SOC limit (%, reg 227); Voltage mode → system charge voltage
        limit (V, reg 228). The other register is ignored by firmware until the
        regime is switched.

        Returns ``{"mode": BatteryControlMode, "value": <number>, "unit": "%"|"V"}``.
        """
        mode = await self.get_battery_charge_control_mode()
        if mode.is_voltage:
            return {
                "mode": mode,
                "value": await self.get_system_charge_volt_limit(),
                "unit": "V",
            }
        return {
            "mode": mode,
            "value": await self.get_system_charge_soc_limit(),
            "unit": "%",
        }

    async def get_active_discharge_cutoff(self, *, off_grid: bool = False) -> dict[str, Any]:
        """Return the discharge cutoff the inverter is currently honoring.

        Derives from the live discharge regime (reg 179 bit 10): SOC mode →
        discharge cutoff SOC (%); Voltage mode → end-of-discharge voltage (V).
        Pass ``off_grid=True`` for the EPS/off-grid cutoff (regs 125 / 100),
        otherwise the on-grid cutoff (regs 105 / 169) is returned.

        Returns ``{"mode": BatteryControlMode, "value": <number>, "unit": "%"|"V"}``.
        """
        mode = await self.get_battery_discharge_control_mode()
        if mode.is_voltage:
            value: float = (
                await self.get_off_grid_cutoff_voltage()
                if off_grid
                else await self.get_on_grid_cutoff_voltage()
            )
            return {"mode": mode, "value": value, "unit": "V"}
        soc_value: int = (
            await self.get_off_grid_cutoff_soc()
            if off_grid
            else await self.get_on_grid_cutoff_soc()
        )
        return {"mode": mode, "value": soc_value, "unit": "%"}

    # ============================================================================
    # PV Sell to Grid / Export PV Only Operations (GH eg4_web_monitor#135)
    # ============================================================================
    # Register 179 bit 3 (FUNC_PV_SELL_TO_GRID_EN, "Export PV Only" in the EG4
    # web UI).  Bit pinned 2026-06-12 ~16:05-16:07 PT via authorized live
    # cloud toggles with raw verification (remoteRead (179,1) valueFrame,
    # base64 LE uint16) on BOTH 12K-hybrid models: FlexBOSS21 52842P0581 and
    # 18kPV 4512670118 each toggled raw 0x104c <-> 0x1044 (XOR 0x0008 =
    # single bit 3) in lockstep with the named param, restores verified by
    # re-read.  These overrides replace the cloud-only BaseInverter
    # implementations with the same dual-path dispatch the battery
    # charge/discharge control bits (9/10) use.

    async def get_pv_sell_to_grid_status(self) -> bool:
        """Get current PV sell to grid (Export PV Only) status.

        Reads register 179 bit 3 via the transport when one is attached,
        otherwise via the cloud named-parameter read.

        Returns:
            True if Export PV Only is enabled, False otherwise

        Example:
            >>> is_enabled = await inverter.get_pv_sell_to_grid_status()
            >>> is_enabled
            True
        """
        from pylxpweb.constants import FUNC_EXT_BIT_PV_SELL_TO_GRID, FUNC_EXT_REGISTER

        return await self._get_register_bit(FUNC_EXT_REGISTER, FUNC_EXT_BIT_PV_SELL_TO_GRID)

    async def set_pv_sell_to_grid(self, enabled: bool) -> bool:
        """Enable or disable PV sell to grid ("Export PV Only").

        Transport mode performs a read-modify-write on register 179 that
        preserves the other function bits from the read value (a read
        followed by a write — the same non-atomic sequence as bits 9/10);
        cloud mode applies the bit server-side via the function-control API.

        Args:
            enabled: True to only export PV surplus (never battery)

        Returns:
            True if successful

        Example:
            >>> await inverter.set_pv_sell_to_grid(True)
            True
        """
        from pylxpweb.constants import FUNC_EXT_BIT_PV_SELL_TO_GRID, FUNC_EXT_REGISTER

        return await self._set_modbus_register_bit(
            FUNC_EXT_REGISTER, FUNC_EXT_BIT_PV_SELL_TO_GRID, enabled
        )

    async def enable_pv_sell_to_grid(self) -> bool:
        """Enable PV sell to grid ("Export PV Only" in the EG4 web UI).

        Dual-path override of the cloud-only BaseInverter method: register
        179 bit 3 read-modify-write over the transport, or the atomic cloud
        function-control update without one.

        Returns:
            True if successful

        Example:
            >>> await inverter.enable_pv_sell_to_grid()
            True
        """
        return await self.set_pv_sell_to_grid(True)

    async def disable_pv_sell_to_grid(self) -> bool:
        """Disable PV sell to grid ("Export PV Only" in the EG4 web UI).

        Returns:
            True if successful

        Example:
            >>> await inverter.disable_pv_sell_to_grid()
            True
        """
        return await self.set_pv_sell_to_grid(False)

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
