"""Device control endpoints for the Luxpower API.

This module provides device control functionality including:
- Parameter reading and writing
- Function enable/disable control
- Quick charge operations
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pylxpweb.endpoints.base import BaseEndpoint
from pylxpweb.models import (
    ParameterReadResponse,
    QuickChargeStatus,
    SuccessResponse,
)

if TYPE_CHECKING:
    from pylxpweb.client import LuxpowerClient

_LOGGER = logging.getLogger(__name__)


class ControlEndpoints(BaseEndpoint):
    """Device control endpoints for parameters, functions, and quick charge."""

    def __init__(self, client: LuxpowerClient) -> None:
        """Initialize control endpoints.

        Args:
            client: The parent LuxpowerClient instance
        """
        super().__init__(client)

    async def read_parameters(
        self,
        inverter_sn: str,
        start_register: int = 0,
        point_number: int = 127,
        auto_retry: bool = True,
    ) -> ParameterReadResponse:
        """Read configuration parameters from inverter registers.

        IMPORTANT: The API returns parameters as FLAT key-value pairs with
        descriptive names (like "HOLD_AC_CHARGE_POWER_CMD"), NOT nested under
        a 'parameters' field or using register numbers as keys!

        Common register ranges (web interface strategy):
        - 0-126 (startRegister=0, pointNumber=127) - System config, grid protection
        - 127-253 (startRegister=127, pointNumber=127) - Additional config
        - 240-366 (startRegister=240, pointNumber=127) - Extended parameters

        Critical registers (verified on 18KPV):
        - Register 21: Function enable bit field (27 bits including AC charge, EPS, standby)
        - Register 66: AC charge power command (HOLD_AC_CHARGE_POWER_CMD)
        - Register 67: AC charge SOC limit (HOLD_AC_CHARGE_SOC_LIMIT)
        - Register 70: AC charge schedule start (hour + minute)
        - Register 100: Battery discharge cutoff voltage
        - Register 110: System function bit field (14 bits including microgrid, eco mode)

        Example:
            >>> response = await client.control.read_parameters("1234567890", 66, 8)
            >>> # Access parameters directly from response
            >>> response.parameters["HOLD_AC_CHARGE_POWER_CMD"]
            50
            >>> response.parameters["HOLD_AC_CHARGE_SOC_LIMIT"]
            100
            >>> # Or access via model dump (includes all parameter keys at root level)
            >>> data = response.model_dump()
            >>> data["HOLD_AC_CHARGE_POWER_CMD"]
            50

            >>> # Read function enable register (27 bit fields)
            >>> response = await client.control.read_parameters("1234567890", 21, 1)
            >>> response.parameters["FUNC_AC_CHARGE"]
            True
            >>> response.parameters["FUNC_SET_TO_STANDBY"]
            False

        Args:
            inverter_sn: Inverter serial number (e.g., "1234567890")
            start_register: Starting register address
            point_number: Number of registers to read (max 127 in practice)
            auto_retry: Enable automatic retry on failure

        Returns:
            ParameterReadResponse: Contains inverterSn, deviceType, startRegister,
                pointNumber, and all parameter keys as flat attributes.
                Use .parameters property to get dict of parameter keys.

        See Also:
            - constants.REGISTER_TO_PARAM_KEYS: Verified register→parameter mappings
            - research/REGISTER_NUMBER_MAPPING.md: Complete register documentation
        """
        await self.client._ensure_authenticated()

        data = {
            "inverterSn": inverter_sn,
            "startRegister": start_register,
            "pointNumber": point_number,
            "autoRetry": auto_retry,
        }

        cache_key = self._get_cache_key(
            "params", sn=inverter_sn, start=start_register, count=point_number
        )
        response = await self.client._request(
            "POST",
            "/WManage/web/maintain/remoteRead/read",
            data=data,
            cache_key=cache_key,
            cache_endpoint="parameter_read",
        )
        return ParameterReadResponse.model_validate(response)

    async def write_parameter(
        self,
        inverter_sn: str,
        hold_param: str,
        value_text: str,
        client_type: str = "WEB",
        remote_set_type: str = "NORMAL",
    ) -> SuccessResponse:
        """Write a configuration parameter to the inverter.

         WARNING: This changes device configuration!

        Common parameters:
        - HOLD_SYSTEM_CHARGE_SOC_LIMIT: Battery charge limit (%)
        - HOLD_SYSTEM_DISCHARGE_SOC_LIMIT: Battery discharge limit (%)
        - HOLD_AC_CHARGE_POWER: AC charge power limit (W)
        - HOLD_AC_DISCHARGE_POWER: AC discharge power limit (W)

        Args:
            inverter_sn: Inverter serial number
            hold_param: Parameter name to write
            value_text: Value to write (as string)
            client_type: Client type (WEB/APP)
            remote_set_type: Set type (NORMAL/QUICK)

        Returns:
            SuccessResponse: Operation result

        Example:
            # Set battery charge limit to 90%
            await client.control.write_parameter(
                "1234567890",
                "HOLD_SYSTEM_CHARGE_SOC_LIMIT",
                "90"
            )
        """
        await self.client._ensure_authenticated()

        data = {
            "inverterSn": inverter_sn,
            "holdParam": hold_param,
            "valueText": value_text,
            "clientType": client_type,
            "remoteSetType": remote_set_type,
        }

        response = await self.client._request(
            "POST", "/WManage/web/maintain/remoteSet/write", data=data
        )
        result = SuccessResponse.model_validate(response)

        # Invalidate cache after successful write to ensure fresh data on next read
        if result.success:
            self.client.invalidate_cache_for_device(inverter_sn)

        return result

    async def write_parameters(
        self,
        inverter_sn: str,
        parameters: dict[int, int],
        client_type: str = "WEB",
    ) -> SuccessResponse:
        """Write multiple configuration parameters to the inverter.

         WARNING: This changes device configuration!

        This is a convenience method that writes register values directly.
        For named parameters, use write_parameter() instead.

        Args:
            inverter_sn: Inverter serial number
            parameters: Dict mapping register addresses to values
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            # Set multiple registers at once
            await client.control.write_parameters(
                "1234567890",
                {21: 512, 66: 50, 67: 100}  # Register addresses and values
            )
        """
        # Note: The API doesn't support batch writes, so we write sequentially
        # For now, just write the first parameter (most common use case is single register)
        # Multi-parameter support would require sequential writes with proper error handling
        if not parameters:
            return SuccessResponse(success=True)

        # For now, we only support single parameter writes through this method
        # Multi-parameter support would require discovering parameter names from register IDs
        register, value = next(iter(parameters.items()))

        # This is a simplified implementation - would need register-to-param mapping
        # for production use. For now, used primarily by device classes for single writes.
        await self.client._ensure_authenticated()

        data = {
            "inverterSn": inverter_sn,
            "data": {str(register): value},
            "clientType": client_type,
        }

        response = await self.client._request(
            "POST", "/WManage/web/maintain/remoteSet/write", data=data
        )
        result = SuccessResponse.model_validate(response)

        # Invalidate cache after successful write to ensure fresh data on next read
        if result.success:
            self.client.invalidate_cache_for_device(inverter_sn)

        return result

    async def control_function(
        self,
        inverter_sn: str,
        function_param: str,
        enable: bool,
        client_type: str = "WEB",
        remote_set_type: str = "NORMAL",
    ) -> SuccessResponse:
        """Enable or disable a device function.

         WARNING: This changes device state!

        Common functions:
        - FUNC_EPS_EN: Battery backup (EPS) mode
        - FUNC_SET_TO_STANDBY: Standby mode
        - FUNC_GRID_PEAK_SHAVING: Peak shaving mode

        Args:
            inverter_sn: Inverter serial number
            function_param: Function parameter name
            enable: Enable or disable the function
            client_type: Client type (WEB/APP)
            remote_set_type: Set type (NORMAL/QUICK)

        Returns:
            SuccessResponse: Operation result

        Example:
            # Enable EPS mode
            await client.control.control_function(
                "1234567890",
                "FUNC_EPS_EN",
                True
            )

            # Disable standby mode
            await client.control.control_function(
                "1234567890",
                "FUNC_SET_TO_STANDBY",
                False
            )
        """
        await self.client._ensure_authenticated()

        data = {
            "inverterSn": inverter_sn,
            "functionParam": function_param,
            "enable": "true" if enable else "false",
            "clientType": client_type,
            "remoteSetType": remote_set_type,
        }

        response = await self.client._request(
            "POST", "/WManage/web/maintain/remoteSet/functionControl", data=data
        )
        result = SuccessResponse.model_validate(response)

        # Invalidate cache after successful write to ensure fresh data on next read
        if result.success:
            self.client.invalidate_cache_for_device(inverter_sn)

        return result

    async def control_bit_param(
        self,
        inverter_sn: str,
        bit_param: str,
        value: int,
        client_type: str = "WEB",
        remote_set_type: str = "NORMAL",
    ) -> SuccessResponse:
        """Set a bit-level parameter on a device.

         WARNING: This changes device configuration!

        Bit parameters control individual feature toggles that are distinct
        from hold register writes and function controls. Used primarily for
        GridBOSS/MID device smart port mode configuration.

        Common bit parameters:
        - BIT_MIDBOX_SP_MODE_1: Smart Port 1 mode (0=Off, 1=Smart Load, 2=AC Couple)
        - BIT_MIDBOX_SP_MODE_2: Smart Port 2 mode
        - BIT_MIDBOX_SP_MODE_3: Smart Port 3 mode
        - BIT_MIDBOX_SP_MODE_4: Smart Port 4 mode

        Args:
            inverter_sn: Device serial number (GridBOSS or inverter)
            bit_param: Bit parameter name (e.g., "BIT_MIDBOX_SP_MODE_1")
            value: Value to set
            client_type: Client type (WEB/APP)
            remote_set_type: Set type (NORMAL/QUICK)

        Returns:
            SuccessResponse: Operation result

        Example:
            # Set Smart Port 1 to AC Couple mode
            await client.control.control_bit_param(
                "1234567890",
                "BIT_MIDBOX_SP_MODE_1",
                2
            )
        """
        await self.client._ensure_authenticated()

        data = {
            "inverterSn": inverter_sn,
            "bitParam": bit_param,
            "value": value,
            "clientType": client_type,
            "remoteSetType": remote_set_type,
        }

        response = await self.client._request(
            "POST", "/WManage/web/maintain/remoteSet/bitParamControl", data=data
        )
        result = SuccessResponse.model_validate(response)

        if result.success:
            self.client.invalidate_cache_for_device(inverter_sn)

        return result

    async def start_quick_charge(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Start quick charge operation.

         WARNING: This starts charging!

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            result = await client.control.start_quick_charge("1234567890")
            if result.success:
                print("Quick charge started successfully")
        """
        await self.client._ensure_authenticated()

        data = {"inverterSn": inverter_sn, "clientType": client_type}

        response = await self.client._request(
            "POST", "/WManage/web/config/quickCharge/start", data=data
        )
        return SuccessResponse.model_validate(response)

    async def stop_quick_charge(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Stop quick charge operation.

         WARNING: This stops charging!

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            result = await client.control.stop_quick_charge("1234567890")
            if result.success:
                print("Quick charge stopped successfully")
        """
        await self.client._ensure_authenticated()

        data = {"inverterSn": inverter_sn, "clientType": client_type}

        response = await self.client._request(
            "POST", "/WManage/web/config/quickCharge/stop", data=data
        )
        return SuccessResponse.model_validate(response)

    async def get_quick_charge_status(self, inverter_sn: str) -> QuickChargeStatus:
        """Get current quick charge operation status.

        Args:
            inverter_sn: Inverter serial number

        Returns:
            QuickChargeStatus: Quick charge status

        Example:
            status = await client.control.get_quick_charge_status("1234567890")
            if status.is_charging:
                print("Quick charge is active")
        """
        await self.client._ensure_authenticated()

        data = {"inverterSn": inverter_sn}

        cache_key = self._get_cache_key("quick_charge", serialNum=inverter_sn)
        response = await self.client._request(
            "POST",
            "/WManage/web/config/quickCharge/getStatusInfo",
            data=data,
            cache_key=cache_key,
            cache_endpoint="quick_charge_status",
        )
        return QuickChargeStatus.model_validate(response)

    async def start_quick_discharge(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Start quick discharge operation.

         WARNING: This starts discharging!

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            result = await client.control.start_quick_discharge("1234567890")
            if result.success:
                print("Quick discharge started successfully")
        """
        await self.client._ensure_authenticated()

        data = {"inverterSn": inverter_sn, "clientType": client_type}

        response = await self.client._request(
            "POST", "/WManage/web/config/quickDischarge/start", data=data
        )
        return SuccessResponse.model_validate(response)

    async def stop_quick_discharge(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Stop quick discharge operation.

         WARNING: This stops discharging!

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            result = await client.control.stop_quick_discharge("1234567890")
            if result.success:
                print("Quick discharge stopped successfully")
        """
        await self.client._ensure_authenticated()

        data = {"inverterSn": inverter_sn, "clientType": client_type}

        response = await self.client._request(
            "POST", "/WManage/web/config/quickDischarge/stop", data=data
        )
        return SuccessResponse.model_validate(response)

    # ============================================================================
    # Convenience Helper Methods
    # ============================================================================

    async def enable_battery_backup(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Enable battery backup (EPS) mode.

        Convenience wrapper for control_function(..., "FUNC_EPS_EN", True).

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.enable_battery_backup("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_EPS_EN", True, client_type=client_type
        )

    async def disable_battery_backup(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Disable battery backup (EPS) mode.

        Convenience wrapper for control_function(..., "FUNC_EPS_EN", False).

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.disable_battery_backup("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_EPS_EN", False, client_type=client_type
        )

    async def enable_battery_backup_ctrl(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Enable battery backup control mode (working mode).

        This controls FUNC_BATTERY_BACKUP_CTRL, which is distinct from
        FUNC_EPS_EN (EPS/off-grid mode). Battery backup control is a
        working mode setting that affects how the inverter manages
        battery reserves for backup power.

        Convenience wrapper for control_function(..., "FUNC_BATTERY_BACKUP_CTRL", True).

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.enable_battery_backup_ctrl("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_BATTERY_BACKUP_CTRL", True, client_type=client_type
        )

    async def disable_battery_backup_ctrl(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Disable battery backup control mode (working mode).

        This controls FUNC_BATTERY_BACKUP_CTRL, which is distinct from
        FUNC_EPS_EN (EPS/off-grid mode). Battery backup control is a
        working mode setting that affects how the inverter manages
        battery reserves for backup power.

        Convenience wrapper for control_function(..., "FUNC_BATTERY_BACKUP_CTRL", False).

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.disable_battery_backup_ctrl("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_BATTERY_BACKUP_CTRL", False, client_type=client_type
        )

    async def enable_normal_mode(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Enable normal operating mode (power on).

        Convenience wrapper for control_function(..., "FUNC_SET_TO_STANDBY", True).
        Note: FUNC_SET_TO_STANDBY = True means NOT in standby (normal mode).

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.enable_normal_mode("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_SET_TO_STANDBY", True, client_type=client_type
        )

    async def enable_standby_mode(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Enable standby mode (power off).

        Convenience wrapper for control_function(..., "FUNC_SET_TO_STANDBY", False).
        Note: FUNC_SET_TO_STANDBY = False means standby mode is active.

        WARNING: This powers off the inverter!

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.enable_standby_mode("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_SET_TO_STANDBY", False, client_type=client_type
        )

    async def enable_grid_peak_shaving(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Enable grid peak shaving mode.

        Convenience wrapper for control_function(..., "FUNC_GRID_PEAK_SHAVING", True).

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.enable_grid_peak_shaving("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_GRID_PEAK_SHAVING", True, client_type=client_type
        )

    async def disable_grid_peak_shaving(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Disable grid peak shaving mode.

        Convenience wrapper for control_function(..., "FUNC_GRID_PEAK_SHAVING", False).

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.disable_grid_peak_shaving("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_GRID_PEAK_SHAVING", False, client_type=client_type
        )

    async def get_battery_backup_status(self, inverter_sn: str) -> bool:
        """Get battery backup (EPS) enabled status.

        Reads register 21 (function enable) and extracts FUNC_EPS_EN bit.

        Args:
            inverter_sn: Inverter serial number

        Returns:
            bool: True if EPS mode is enabled, False otherwise

        Example:
            >>> enabled = await client.control.get_battery_backup_status("1234567890")
            >>> if enabled:
            >>>     print("EPS mode is active")
        """
        response = await self.read_parameters(inverter_sn, 21, 1)
        value = response.parameters.get("FUNC_EPS_EN", False)
        return bool(value)

    # ============================================================================
    # Working Mode Controls (Issue #16)
    # ============================================================================

    async def enable_ac_charge_mode(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Enable AC charge mode to allow battery charging from grid.

        Convenience wrapper for control_function(..., "FUNC_AC_CHARGE", True).

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.enable_ac_charge_mode("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_AC_CHARGE", True, client_type=client_type
        )

    async def disable_ac_charge_mode(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Disable AC charge mode.

        Convenience wrapper for control_function(..., "FUNC_AC_CHARGE", False).

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.disable_ac_charge_mode("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_AC_CHARGE", False, client_type=client_type
        )

    async def get_ac_charge_mode_status(self, inverter_sn: str) -> bool:
        """Get current AC charge mode status.

        Reads register 21 (function enable) and extracts FUNC_AC_CHARGE bit.

        Args:
            inverter_sn: Inverter serial number

        Returns:
            bool: True if AC charge mode is enabled, False otherwise

        Example:
            >>> enabled = await client.control.get_ac_charge_mode_status("1234567890")
            >>> if enabled:
            >>>     print("AC charge mode is active")
        """
        response = await self.read_parameters(inverter_sn, 21, 1)
        value = response.parameters.get("FUNC_AC_CHARGE", False)
        return bool(value)

    async def enable_pv_charge_priority(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Enable PV charge priority mode during specified hours.

        Convenience wrapper for control_function(..., "FUNC_FORCED_CHG_EN", True).

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.enable_pv_charge_priority("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_FORCED_CHG_EN", True, client_type=client_type
        )

    async def disable_pv_charge_priority(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Disable PV charge priority mode.

        Convenience wrapper for control_function(..., "FUNC_FORCED_CHG_EN", False).

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.disable_pv_charge_priority("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_FORCED_CHG_EN", False, client_type=client_type
        )

    async def get_pv_charge_priority_status(self, inverter_sn: str) -> bool:
        """Get current PV charge priority status.

        Reads register 21 (function enable) and extracts FUNC_FORCED_CHG_EN bit.

        Args:
            inverter_sn: Inverter serial number

        Returns:
            bool: True if PV charge priority is enabled, False otherwise

        Example:
            >>> enabled = await client.control.get_pv_charge_priority_status("1234567890")
            >>> if enabled:
            >>>     print("PV charge priority mode is active")
        """
        response = await self.read_parameters(inverter_sn, 21, 1)
        value = response.parameters.get("FUNC_FORCED_CHG_EN", False)
        return bool(value)

    async def enable_forced_discharge(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Enable forced discharge mode for grid export.

        Convenience wrapper for control_function(..., "FUNC_FORCED_DISCHG_EN", True).

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.enable_forced_discharge("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_FORCED_DISCHG_EN", True, client_type=client_type
        )

    async def disable_forced_discharge(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Disable forced discharge mode.

        Convenience wrapper for control_function(..., "FUNC_FORCED_DISCHG_EN", False).

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.disable_forced_discharge("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_FORCED_DISCHG_EN", False, client_type=client_type
        )

    async def get_forced_discharge_status(self, inverter_sn: str) -> bool:
        """Get current forced discharge status.

        Reads register 21 (function enable) and extracts FUNC_FORCED_DISCHG_EN bit.

        Args:
            inverter_sn: Inverter serial number

        Returns:
            bool: True if forced discharge is enabled, False otherwise

        Example:
            >>> enabled = await client.control.get_forced_discharge_status("1234567890")
            >>> if enabled:
            >>>     print("Forced discharge mode is active")
        """
        response = await self.read_parameters(inverter_sn, 21, 1)
        value = response.parameters.get("FUNC_FORCED_DISCHG_EN", False)
        return bool(value)

    async def enable_peak_shaving_mode(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Enable grid peak shaving mode.

        Convenience wrapper for control_function(..., "FUNC_GRID_PEAK_SHAVING", True).

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.enable_peak_shaving_mode("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_GRID_PEAK_SHAVING", True, client_type=client_type
        )

    async def disable_peak_shaving_mode(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Disable grid peak shaving mode.

        Convenience wrapper for control_function(..., "FUNC_GRID_PEAK_SHAVING", False).

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.disable_peak_shaving_mode("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_GRID_PEAK_SHAVING", False, client_type=client_type
        )

    async def get_peak_shaving_mode_status(self, inverter_sn: str) -> bool:
        """Get current peak shaving mode status.

        Reads register 21 (function enable) and extracts FUNC_GRID_PEAK_SHAVING bit.

        Args:
            inverter_sn: Inverter serial number

        Returns:
            bool: True if peak shaving mode is enabled, False otherwise

        Example:
            >>> enabled = await client.control.get_peak_shaving_mode_status("1234567890")
            >>> if enabled:
            >>>     print("Peak shaving mode is active")
        """
        response = await self.read_parameters(inverter_sn, 21, 1)
        value = response.parameters.get("FUNC_GRID_PEAK_SHAVING", False)
        return bool(value)

    # ============================================================================
    # Green Mode Controls (Off-Grid Mode in Web Monitor)
    # ============================================================================

    async def enable_green_mode(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Enable green mode (off-grid mode in the web monitoring display).

        Green Mode controls the off-grid operating mode toggle visible in the
        EG4 web monitoring interface. When enabled, the inverter operates in
        an off-grid optimized configuration.

        Note: This is FUNC_GREEN_EN in register 110, distinct from FUNC_EPS_EN
        (battery backup/EPS mode) in register 21.

        Convenience wrapper for control_function(..., "FUNC_GREEN_EN", True).

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.enable_green_mode("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_GREEN_EN", True, client_type=client_type
        )

    async def disable_green_mode(
        self, inverter_sn: str, client_type: str = "WEB"
    ) -> SuccessResponse:
        """Disable green mode (off-grid mode in the web monitoring display).

        Green Mode controls the off-grid operating mode toggle visible in the
        EG4 web monitoring interface. When disabled, the inverter operates in
        standard grid-tied configuration.

        Note: This is FUNC_GREEN_EN in register 110, distinct from FUNC_EPS_EN
        (battery backup/EPS mode) in register 21.

        Convenience wrapper for control_function(..., "FUNC_GREEN_EN", False).

        Args:
            inverter_sn: Inverter serial number
            client_type: Client type (WEB/APP)

        Returns:
            SuccessResponse: Operation result

        Example:
            >>> result = await client.control.disable_green_mode("1234567890")
            >>> result.success
            True
        """
        return await self.control_function(
            inverter_sn, "FUNC_GREEN_EN", False, client_type=client_type
        )

    async def get_green_mode_status(self, inverter_sn: str) -> bool:
        """Get current green mode (off-grid mode) status.

        Green Mode controls the off-grid operating mode toggle visible in the
        EG4 web monitoring interface.

        Reads register 110 (system functions) and extracts FUNC_GREEN_EN bit.

        Args:
            inverter_sn: Inverter serial number

        Returns:
            bool: True if green mode is enabled, False otherwise

        Example:
            >>> enabled = await client.control.get_green_mode_status("1234567890")
            >>> if enabled:
            >>>     print("Green mode (off-grid) is active")
        """
        response = await self.read_parameters(inverter_sn, 110, 1)
        value = response.parameters.get("FUNC_GREEN_EN", False)
        return bool(value)

    async def read_device_parameters_ranges(self, inverter_sn: str) -> dict[str, int | bool]:
        """Read all device parameters across three common register ranges.

        This method combines three read_parameters() calls:
        - Range 1: 0-126 (System config, grid protection)
        - Range 2: 127-253 (Additional config)
        - Range 3: 240-366 (Extended parameters)

        Args:
            inverter_sn: Inverter serial number

        Returns:
            dict: Combined parameters from all three ranges

        Example:
            >>> params = await client.control.read_device_parameters_ranges("1234567890")
            >>> params["HOLD_AC_CHARGE_POWER_CMD"]
            50
            >>> params["FUNC_EPS_EN"]
            True
        """
        import asyncio

        # Read all three ranges concurrently
        range1_task = self.read_parameters(inverter_sn, 0, 127)
        range2_task = self.read_parameters(inverter_sn, 127, 127)
        range3_task = self.read_parameters(inverter_sn, 240, 127)

        range1, range2, range3 = await asyncio.gather(
            range1_task, range2_task, range3_task, return_exceptions=True
        )

        # Combine parameters from all ranges
        combined: dict[str, int | bool] = {}

        if not isinstance(range1, BaseException):
            combined.update(range1.parameters)

        if not isinstance(range2, BaseException):
            combined.update(range2.parameters)

        if not isinstance(range3, BaseException):
            combined.update(range3.parameters)

        return combined

    # ============================================================================
    # Battery Current Control (Added in v0.3)
    # ============================================================================

    async def set_battery_charge_current(
        self,
        inverter_sn: str,
        amperes: int,
        *,
        validate_battery_limits: bool = True,
    ) -> SuccessResponse:
        """Set battery charge current limit.

        Controls the maximum current allowed to charge batteries.

        Common use cases:
        - Prevent inverter throttling during high solar production
        - Time-of-use optimization (reduce charge during peak rates)
        - Battery health management (gentle charging)
        - Weather-based automation (reduce on sunny days, maximize on cloudy)

        Power Calculation (48V nominal system):
        - 50A = ~2.4kW
        - 100A = ~4.8kW
        - 150A = ~7.2kW
        - 200A = ~9.6kW
        - 250A = ~12kW

        Args:
            inverter_sn: Inverter serial number
            amperes: Charge current limit (0-250 A)
            validate_battery_limits: Warn if value exceeds typical battery limits

        Returns:
            SuccessResponse: Operation result

        Raises:
            ValueError: If amperes not in valid range (0-250 A)

        Warning:
            CRITICAL: Never exceed your battery's maximum charge current rating.
            Check battery manufacturer specifications before setting high values.
            Monitor battery temperature during high current operations.

        Example:
            >>> # Prevent throttling on sunny days (limit to ~4kW charge at 48V)
            >>> await client.control.set_battery_charge_current("1234567890", 80)
            SuccessResponse(success=True)

            >>> # Maximum charge on cloudy days
            >>> await client.control.set_battery_charge_current("1234567890", 200)
            SuccessResponse(success=True)
        """
        if not (0 <= amperes <= 250):
            raise ValueError(f"Battery charge current must be between 0-250 A, got {amperes}")

        if validate_battery_limits and amperes > 200:
            _LOGGER.warning(
                "Setting battery charge current to %d A. "
                "Ensure this does not exceed your battery's maximum rating. "
                "Typical limits: 200A for 10kWh, 150A for 7.5kWh, 100A for 5kWh.",
                amperes,
            )

        return await self.write_parameter(inverter_sn, "HOLD_LEAD_ACID_CHARGE_RATE", str(amperes))

    async def set_battery_discharge_current(
        self,
        inverter_sn: str,
        amperes: int,
        *,
        validate_battery_limits: bool = True,
    ) -> SuccessResponse:
        """Set battery discharge current limit.

        Controls the maximum current allowed to discharge from batteries.

        Common use cases:
        - Preserve battery capacity during grid outages
        - Extend battery lifespan (conservative discharge)
        - Emergency power management
        - Peak load management

        Args:
            inverter_sn: Inverter serial number
            amperes: Discharge current limit (0-250 A)
            validate_battery_limits: Warn if value exceeds typical battery limits

        Returns:
            SuccessResponse: Operation result

        Raises:
            ValueError: If amperes not in valid range (0-250 A)

        Warning:
            Never exceed your battery's maximum discharge current rating.
            Check battery manufacturer specifications.

        Example:
            >>> # Conservative discharge for battery longevity
            >>> await client.control.set_battery_discharge_current("1234567890", 150)
            SuccessResponse(success=True)

            >>> # Minimal discharge during grid outage
            >>> await client.control.set_battery_discharge_current("1234567890", 50)
            SuccessResponse(success=True)
        """
        if not (0 <= amperes <= 250):
            raise ValueError(f"Battery discharge current must be between 0-250 A, got {amperes}")

        if validate_battery_limits and amperes > 200:
            _LOGGER.warning(
                "Setting battery discharge current to %d A. "
                "Ensure this does not exceed your battery's maximum rating.",
                amperes,
            )

        return await self.write_parameter(
            inverter_sn, "HOLD_LEAD_ACID_DISCHARGE_RATE", str(amperes)
        )

    async def get_battery_charge_current(self, inverter_sn: str) -> int:
        """Get current battery charge current limit.

        Args:
            inverter_sn: Inverter serial number

        Returns:
            int: Current charge current limit in Amperes (0-250 A)

        Example:
            >>> current = await client.control.get_battery_charge_current("1234567890")
            >>> print(f"Charge limit: {current} A (~{current * 0.048:.1f} kW at 48V)")
            Charge limit: 200 A (~9.6 kW at 48V)
        """
        params = await self.read_device_parameters_ranges(inverter_sn)
        return int(params.get("HOLD_LEAD_ACID_CHARGE_RATE", 200))

    async def get_battery_discharge_current(self, inverter_sn: str) -> int:
        """Get current battery discharge current limit.

        Args:
            inverter_sn: Inverter serial number

        Returns:
            int: Current discharge current limit in Amperes (0-250 A)

        Example:
            >>> current = await client.control.get_battery_discharge_current("1234567890")
            >>> print(f"Discharge limit: {current} A")
            Discharge limit: 200 A
        """
        params = await self.read_device_parameters_ranges(inverter_sn)
        return int(params.get("HOLD_LEAD_ACID_DISCHARGE_RATE", 200))

    # ============================================================================
    # System SOC Limit Controls
    # ============================================================================

    async def set_system_charge_soc_limit(
        self,
        inverter_sn: str,
        percent: int,
    ) -> SuccessResponse:
        """Set the system charge SOC limit.

        Controls the maximum State of Charge (SOC) percentage the battery will
        charge to during normal operation.

        Args:
            inverter_sn: Inverter serial number
            percent: Target SOC limit (0-101%)
                - 0-100: Stop charging when battery reaches this SOC
                - 101: Special value to enable top balancing (allows full charge
                       with cell balancing for lithium batteries)

        Returns:
            SuccessResponse: Operation result

        Raises:
            ValueError: If percent not in valid range (0-101)

        Note:
            Setting 101% enables top balancing mode, which allows the battery
            management system to fully charge and balance individual cells.
            This is recommended periodically for lithium battery health.

        Example:
            >>> # Limit charging to 90% for daily use (extends battery life)
            >>> await client.control.set_system_charge_soc_limit("1234567890", 90)
            SuccessResponse(success=True)

            >>> # Enable top balancing (charge to 100% with cell balancing)
            >>> await client.control.set_system_charge_soc_limit("1234567890", 101)
            SuccessResponse(success=True)
        """
        if not (0 <= percent <= 101):
            raise ValueError(
                f"System charge SOC limit must be between 0-101%, got {percent}. "
                "Use 101 for top balancing mode."
            )

        return await self.write_parameter(inverter_sn, "HOLD_SYSTEM_CHARGE_SOC_LIMIT", str(percent))

    async def get_system_charge_soc_limit(self, inverter_sn: str) -> int:
        """Get the current system charge SOC limit.

        Args:
            inverter_sn: Inverter serial number

        Returns:
            int: Current charge SOC limit (0-101%)
                - 0-100: Normal SOC limit
                - 101: Top balancing mode enabled

        Example:
            >>> limit = await client.control.get_system_charge_soc_limit("1234567890")
            >>> if limit == 101:
            >>>     print("Top balancing enabled")
            >>> else:
            >>>     print(f"Charge limit: {limit}%")
        """
        params = await self.read_device_parameters_ranges(inverter_sn)
        return int(params.get("HOLD_SYSTEM_CHARGE_SOC_LIMIT", 100))

    # ============================================================================
    # GridBOSS/MID Smart Port Controls
    # ============================================================================

    async def set_smart_port_mode(
        self,
        midbox_sn: str,
        port: int,
        mode: int,
    ) -> SuccessResponse:
        """Set a GridBOSS smart port mode.

         WARNING: This changes device configuration!

        Args:
            midbox_sn: GridBOSS/MID device serial number
            port: Smart port number (1-4)
            mode: Port mode (0=Off, 1=Smart Load, 2=AC Couple)

        Returns:
            SuccessResponse: Operation result

        Raises:
            ValueError: If port or mode is out of range

        Example:
            >>> # Set Smart Port 1 to AC Couple
            >>> await client.control.set_smart_port_mode("1234567890", 1, 2)

            >>> # Disable Smart Port 2
            >>> await client.control.set_smart_port_mode("1234567890", 2, 0)
        """
        if port not in (1, 2, 3, 4):
            raise ValueError(f"Smart port must be 1-4, got {port}")
        if mode not in (0, 1, 2):
            raise ValueError(
                f"Smart port mode must be 0 (Off), 1 (Smart Load), or 2 (AC Couple), got {mode}"
            )

        return await self.control_bit_param(midbox_sn, f"BIT_MIDBOX_SP_MODE_{port}", mode)

    async def set_ac_couple_start_soc(
        self,
        midbox_sn: str,
        port: int,
        percent: int,
    ) -> SuccessResponse:
        """Set the AC Couple start SOC threshold for a smart port.

        When battery SOC drops below this threshold, the AC-coupled source
        on the specified port will be activated.

        Args:
            midbox_sn: GridBOSS/MID device serial number
            port: Smart port number (1-4)
            percent: SOC percentage threshold (0-100)

        Returns:
            SuccessResponse: Operation result

        Raises:
            ValueError: If port or percent is out of range

        Example:
            >>> # Start AC Couple 1 when SOC drops below 20%
            >>> await client.control.set_ac_couple_start_soc("1234567890", 1, 20)
        """
        if port not in (1, 2, 3, 4):
            raise ValueError(f"Smart port must be 1-4, got {port}")
        if not (0 <= percent <= 100):
            raise ValueError(f"SOC percent must be 0-100, got {percent}")

        return await self.write_parameter(
            midbox_sn, f"MIDBOX_HOLD_AC_START_SOC_{port}", str(percent)
        )

    async def set_ac_couple_end_soc(
        self,
        midbox_sn: str,
        port: int,
        percent: int,
    ) -> SuccessResponse:
        """Set the AC Couple end SOC threshold for a smart port.

        When battery SOC rises above this threshold, the AC-coupled source
        on the specified port will be deactivated.

        Args:
            midbox_sn: GridBOSS/MID device serial number
            port: Smart port number (1-4)
            percent: SOC percentage threshold (0-100)

        Returns:
            SuccessResponse: Operation result

        Raises:
            ValueError: If port or percent is out of range

        Example:
            >>> # Stop AC Couple 1 when SOC reaches 95%
            >>> await client.control.set_ac_couple_end_soc("1234567890", 1, 95)
        """
        if port not in (1, 2, 3, 4):
            raise ValueError(f"Smart port must be 1-4, got {port}")
        if not (0 <= percent <= 100):
            raise ValueError(f"SOC percent must be 0-100, got {percent}")

        return await self.write_parameter(midbox_sn, f"MIDBOX_HOLD_AC_END_SOC_{port}", str(percent))

    async def set_smart_load_start_soc(
        self,
        midbox_sn: str,
        port: int,
        percent: int,
    ) -> SuccessResponse:
        """Set the Smart Load start SOC threshold for a smart port.

        When battery SOC rises above this threshold, the smart load
        on the specified port will be activated.

        Args:
            midbox_sn: GridBOSS/MID device serial number
            port: Smart port number (1-4)
            percent: SOC percentage threshold (0-100)

        Returns:
            SuccessResponse: Operation result

        Raises:
            ValueError: If port or percent is out of range

        Example:
            >>> # Enable Smart Load 1 when SOC exceeds 80%
            >>> await client.control.set_smart_load_start_soc("1234567890", 1, 80)
        """
        if port not in (1, 2, 3, 4):
            raise ValueError(f"Smart port must be 1-4, got {port}")
        if not (0 <= percent <= 100):
            raise ValueError(f"SOC percent must be 0-100, got {percent}")

        return await self.write_parameter(
            midbox_sn, f"MIDBOX_HOLD_SL_START_SOC_{port}", str(percent)
        )

    async def set_smart_load_end_soc(
        self,
        midbox_sn: str,
        port: int,
        percent: int,
    ) -> SuccessResponse:
        """Set the Smart Load end SOC threshold for a smart port.

        When battery SOC drops below this threshold, the smart load
        on the specified port will be deactivated.

        Args:
            midbox_sn: GridBOSS/MID device serial number
            port: Smart port number (1-4)
            percent: SOC percentage threshold (0-100)

        Returns:
            SuccessResponse: Operation result

        Raises:
            ValueError: If port or percent is out of range

        Example:
            >>> # Disable Smart Load 1 when SOC drops below 50%
            >>> await client.control.set_smart_load_end_soc("1234567890", 1, 50)
        """
        if port not in (1, 2, 3, 4):
            raise ValueError(f"Smart port must be 1-4, got {port}")
        if not (0 <= percent <= 100):
            raise ValueError(f"SOC percent must be 0-100, got {percent}")

        return await self.write_parameter(midbox_sn, f"MIDBOX_HOLD_SL_END_SOC_{port}", str(percent))

    async def enable_smart_load(
        self,
        midbox_sn: str,
        port: int,
    ) -> SuccessResponse:
        """Enable a smart load on the specified port.

        This uses the functionControl endpoint to set FUNC_SMART_LOAD_EN_{n}.
        The port must already be configured as Smart Load mode via
        set_smart_port_mode().

        Args:
            midbox_sn: GridBOSS/MID device serial number
            port: Smart port number (1-4)

        Returns:
            SuccessResponse: Operation result

        Raises:
            ValueError: If port is out of range

        Example:
            >>> await client.control.enable_smart_load("1234567890", 3)
        """
        if port not in (1, 2, 3, 4):
            raise ValueError(f"Smart port must be 1-4, got {port}")
        return await self.control_function(midbox_sn, f"FUNC_SMART_LOAD_EN_{port}", True)

    async def disable_smart_load(
        self,
        midbox_sn: str,
        port: int,
    ) -> SuccessResponse:
        """Disable a smart load on the specified port.

        Args:
            midbox_sn: GridBOSS/MID device serial number
            port: Smart port number (1-4)

        Returns:
            SuccessResponse: Operation result

        Raises:
            ValueError: If port is out of range

        Example:
            >>> await client.control.disable_smart_load("1234567890", 3)
        """
        if port not in (1, 2, 3, 4):
            raise ValueError(f"Smart port must be 1-4, got {port}")
        return await self.control_function(midbox_sn, f"FUNC_SMART_LOAD_EN_{port}", False)

    async def enable_ac_couple(
        self,
        midbox_sn: str,
        port: int,
    ) -> SuccessResponse:
        """Enable AC coupling on the specified port.

        This uses the functionControl endpoint to set FUNC_AC_COUPLE_EN_{n}.
        The port must already be configured as AC Couple mode via
        set_smart_port_mode().

        Args:
            midbox_sn: GridBOSS/MID device serial number
            port: Smart port number (1-4)

        Returns:
            SuccessResponse: Operation result

        Raises:
            ValueError: If port is out of range

        Example:
            >>> await client.control.enable_ac_couple("1234567890", 1)
        """
        if port not in (1, 2, 3, 4):
            raise ValueError(f"Smart port must be 1-4, got {port}")
        return await self.control_function(midbox_sn, f"FUNC_AC_COUPLE_EN_{port}", True)

    async def disable_ac_couple(
        self,
        midbox_sn: str,
        port: int,
    ) -> SuccessResponse:
        """Disable AC coupling on the specified port.

        Args:
            midbox_sn: GridBOSS/MID device serial number
            port: Smart port number (1-4)

        Returns:
            SuccessResponse: Operation result

        Raises:
            ValueError: If port is out of range

        Example:
            >>> await client.control.disable_ac_couple("1234567890", 1)
        """
        if port not in (1, 2, 3, 4):
            raise ValueError(f"Smart port must be 1-4, got {port}")
        return await self.control_function(midbox_sn, f"FUNC_AC_COUPLE_EN_{port}", False)

    async def set_smart_load_grid_on(
        self,
        midbox_sn: str,
        port: int,
        enable: bool,
    ) -> SuccessResponse:
        """Set whether a smart load stays powered when grid is available.

        Args:
            midbox_sn: GridBOSS/MID device serial number
            port: Smart port number (1-4)
            enable: True to keep load on when grid is up

        Returns:
            SuccessResponse: Operation result

        Raises:
            ValueError: If port is out of range

        Example:
            >>> await client.control.set_smart_load_grid_on("1234567890", 2, True)
        """
        if port not in (1, 2, 3, 4):
            raise ValueError(f"Smart port must be 1-4, got {port}")
        return await self.control_function(midbox_sn, f"FUNC_SMART_LOAD_GRID_ON_{port}", enable)
