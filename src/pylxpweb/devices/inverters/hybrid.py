"""Hybrid inverter implementation for grid-tied models with battery storage.

This module provides the HybridInverter class for hybrid inverters that support:
- AC charging from grid
- Forced charge/discharge
- EPS (backup) mode
- Time-of-use scheduling
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .generic import GenericInverter

if TYPE_CHECKING:
    pass


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
            "soc_limit": ac_params.get("HOLD_AC_CHARGE_SOC_LIMIT"),
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

        # Read current function enable register
        params = await self.read_parameters(FUNC_EN_REGISTER, 1)
        current_value = params.get(f"reg_{FUNC_EN_REGISTER}", 0)

        if enabled:
            new_value = current_value | (1 << FUNC_EN_BIT_EPS_EN)
        else:
            new_value = current_value & ~(1 << FUNC_EN_BIT_EPS_EN)

        return await self.write_parameters({FUNC_EN_REGISTER: new_value})

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

        params = await self.read_parameters(FUNC_EN_REGISTER, 1)
        current_value = params.get(f"reg_{FUNC_EN_REGISTER}", 0)

        if enabled:
            new_value = current_value | (1 << FUNC_EN_BIT_FORCED_CHG_EN)
        else:
            new_value = current_value & ~(1 << FUNC_EN_BIT_FORCED_CHG_EN)

        return await self.write_parameters({FUNC_EN_REGISTER: new_value})

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

        params = await self.read_parameters(FUNC_EN_REGISTER, 1)
        current_value = params.get(f"reg_{FUNC_EN_REGISTER}", 0)

        if enabled:
            new_value = current_value | (1 << FUNC_EN_BIT_FORCED_DISCHG_EN)
        else:
            new_value = current_value & ~(1 << FUNC_EN_BIT_FORCED_DISCHG_EN)

        return await self.write_parameters({FUNC_EN_REGISTER: new_value})

    async def get_charge_discharge_power(self) -> dict[str, int]:
        """Get charge and discharge power settings.

        Returns:
            Dictionary with:
            - charge_power_percent: AC charge power (0-100%)
            - discharge_power_percent: Discharge power (0-100%)

        Example:
            >>> settings = await inverter.get_charge_discharge_power()
            >>> settings
            {'charge_power_percent': 50, 'discharge_power_percent': 100}
        """
        from pylxpweb.constants import HOLD_AC_CHARGE_POWER_CMD

        params = await self.read_parameters(HOLD_AC_CHARGE_POWER_CMD, 9)

        return {
            "charge_power_percent": params.get("HOLD_AC_CHARGE_POWER_CMD", 0),
            "discharge_power_percent": params.get("HOLD_DISCHG_POWER_CMD"),
        }

    async def set_discharge_power(self, power_percent: int) -> bool:
        """Set battery discharge power limit.

        Args:
            power_percent: Discharge power percentage (0-100)

        Returns:
            True if successful

        Example:
            >>> await inverter.set_discharge_power(80)
            True
        """
        from pylxpweb.constants import HOLD_DISCHG_POWER_CMD

        if not 0 <= power_percent <= 100:
            raise ValueError("power_percent must be between 0 and 100")

        return await self.write_parameters({HOLD_DISCHG_POWER_CMD: power_percent})
