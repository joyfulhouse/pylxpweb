"""Device endpoints for the Luxpower API.

This module provides device functionality including:
- Device discovery and hierarchy
- Real-time runtime data
- Energy statistics
- Battery information
- GridBOSS/MID device data
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pylxpweb.endpoints.base import BaseEndpoint
from pylxpweb.models import (
    BatteryInfo,
    BatteryListResponse,
    EnergyInfo,
    InverterInfo,
    InverterOverviewResponse,
    InverterRuntime,
    MidboxRuntime,
    ParallelGroupDetailsResponse,
)

if TYPE_CHECKING:
    from pylxpweb.client import LuxpowerClient


class DeviceEndpoints(BaseEndpoint):
    """Device endpoints for discovery, runtime data, and device information."""

    def __init__(self, client: LuxpowerClient) -> None:
        """Initialize device endpoints.

        Args:
            client: The parent LuxpowerClient instance
        """
        super().__init__(client)

    async def get_parallel_group_details(self, serial_num: str) -> ParallelGroupDetailsResponse:
        """Get parallel group device hierarchy for a specific device.

        Note: This endpoint requires a device serial number, not a plant ID.
        Use the GridBOSS/MID device serial number for parallel group details.

        Args:
            serial_num: Serial number of GridBOSS or any device in the parallel group

        Returns:
            ParallelGroupDetailsResponse: Parallel group structure

        Example:
            groups = await client.devices.get_parallel_group_details("4524850115")
            print(f"Total devices: {groups.total}")
            for device in groups.devices:
                print(f"  {device.serialNum}: {device.roleText}")
        """
        await self.client._ensure_authenticated()

        data = {"serialNum": serial_num}

        cache_key = self._get_cache_key("parallel_groups", serialNum=serial_num)
        response = await self.client._request(
            "POST",
            "/WManage/api/inverterOverview/getParallelGroupDetails",
            data=data,
            cache_key=cache_key,
            cache_endpoint="device_discovery",
        )
        return ParallelGroupDetailsResponse.model_validate(response)

    async def get_devices(self, plant_id: int) -> InverterOverviewResponse:
        """Get overview/status of all devices in a plant.

        Args:
            plant_id: Plant/station ID

        Returns:
            InverterOverviewResponse: Overview data for inverters and devices

        Example:
            devices = await client.devices.get_devices(12345)
            for device in devices.rows:
                print(f"Device: {device.serialNum} - {device.statusText}")
        """
        await self.client._ensure_authenticated()

        data = {
            "page": 1,
            "rows": 30,
            "plantId": plant_id,
            "searchText": "",
            "statusText": "all",
        }

        cache_key = self._get_cache_key("devices", plantId=plant_id)
        response = await self.client._request(
            "POST",
            "/WManage/api/inverterOverview/list",
            data=data,
            cache_key=cache_key,
            cache_endpoint="device_discovery",
        )
        return InverterOverviewResponse.model_validate(response)

    async def get_inverter_info(self, serial_num: str) -> InverterInfo:
        """Get detailed inverter configuration and device information.

        This endpoint returns static device configuration, firmware versions,
        and hardware details. For real-time operational data, use get_inverter_runtime().

        Args:
            serial_num: Inverter serial number

        Returns:
            InverterInfo: Detailed device configuration

        Example:
            info = await client.devices.get_inverter_info("1234567890")
            print(f"Device: {info.deviceTypeText}")
            print(f"Firmware: {info.inverterDetail.fwCode}")
            print(f"Power Rating: {info.powerRatingText}")
            print(f"Battery Type: {info.batteryType}")
        """
        await self.client._ensure_authenticated()

        data = {"serialNum": serial_num}

        cache_key = self._get_cache_key("inverter_info", serialNum=serial_num)
        response = await self.client._request(
            "POST",
            "/WManage/api/inverter/getInverterInfo",
            data=data,
            cache_key=cache_key,
            cache_endpoint="device_discovery",  # Static data, cache like device discovery
        )
        return InverterInfo.model_validate(response)

    async def get_inverter_runtime(self, serial_num: str) -> InverterRuntime:
        """Get real-time runtime data for an inverter.

        Note: Many values require scaling:
        - Voltage: divide by 100
        - Current: divide by 100
        - Frequency: divide by 100
        - Power: no scaling (direct watts)

        Args:
            serial_num: 10-digit device serial number

        Returns:
            InverterRuntime: Real-time inverter metrics

        Example:
            runtime = await client.devices.get_inverter_runtime("1234567890")
            print(f"PV Power: {runtime.ppv}W")
            print(f"Battery SOC: {runtime.soc}%")
            print(f"Grid Voltage: {runtime.vacr / 100}V")
        """
        await self.client._ensure_authenticated()

        data = {"serialNum": serial_num}

        cache_key = self._get_cache_key("runtime", serialNum=serial_num)
        response = await self.client._request(
            "POST",
            "/WManage/api/inverter/getInverterRuntime",
            data=data,
            cache_key=cache_key,
            cache_endpoint="inverter_runtime",
        )
        return InverterRuntime.model_validate(response)

    async def get_inverter_energy(self, serial_num: str) -> EnergyInfo:
        """Get energy statistics for an inverter.

        All energy values are in Wh (divide by 1000 for kWh).

        Args:
            serial_num: 10-digit device serial number

        Returns:
            EnergyInfo: Energy production and consumption statistics

        Example:
            energy = await client.devices.get_inverter_energy("1234567890")
            print(f"Today's Production: {energy.eInvDay / 1000}kWh")
            print(f"Total Production: {energy.eInvAll / 1000}kWh")
        """
        await self.client._ensure_authenticated()

        data = {"serialNum": serial_num}

        cache_key = self._get_cache_key("energy", serialNum=serial_num)
        response = await self.client._request(
            "POST",
            "/WManage/api/inverter/getInverterEnergyInfo",
            data=data,
            cache_key=cache_key,
            cache_endpoint="inverter_energy",
        )
        return EnergyInfo.model_validate(response)

    async def get_parallel_energy(self, serial_num: str) -> EnergyInfo:
        """Get aggregate energy statistics for entire parallel group.

        Args:
            serial_num: Serial number of any inverter in the parallel group

        Returns:
            EnergyInfo: Aggregate energy statistics for the group

        Example:
            energy = await client.devices.get_parallel_energy("1234567890")
            print(f"Group Total Today: {energy.eInvDay / 1000}kWh")
        """
        await self.client._ensure_authenticated()

        data = {"serialNum": serial_num}

        cache_key = self._get_cache_key("parallel_energy", serialNum=serial_num)
        response = await self.client._request(
            "POST",
            "/WManage/api/inverter/getInverterEnergyInfoParallel",
            data=data,
            cache_key=cache_key,
            cache_endpoint="inverter_energy",
        )
        return EnergyInfo.model_validate(response)

    async def get_battery_info(self, serial_num: str) -> BatteryInfo:
        """Get battery information including individual modules.

        Note: Cell voltages are in millivolts (divide by 1000 for volts).

        Args:
            serial_num: Inverter serial number

        Returns:
            BatteryInfo: Battery status and individual module data

        Example:
            battery = await client.devices.get_battery_info("1234567890")
            print(f"Battery SOC: {battery.soc}%")
            print(f"Number of Modules: {len(battery.batteryArray)}")
            for module in battery.batteryArray:
                print(f"  Module {module.batIndex}: {module.vBat / 100}V")
        """
        await self.client._ensure_authenticated()

        data = {"serialNum": serial_num}

        cache_key = self._get_cache_key("battery", serialNum=serial_num)
        response = await self.client._request(
            "POST",
            "/WManage/api/battery/getBatteryInfo",
            data=data,
            cache_key=cache_key,
            cache_endpoint="battery_info",
        )
        return BatteryInfo.model_validate(response)

    async def get_battery_list(self, serial_num: str) -> BatteryListResponse:
        """Get simplified battery list for an inverter.

        This endpoint returns only battery identification and status without detailed metrics.
        Use get_battery_info() for full battery metrics including voltage, current, SOC, etc.

        Args:
            serial_num: Inverter serial number

        Returns:
            BatteryListResponse: Simplified battery list with keys and status

        Example:
            batteries = await client.devices.get_battery_list("1234567890")
            print(f"Total batteries: {batteries.totalNumber}")
            for battery in batteries.batteryArray:
                status = "Online" if not battery.lost else "Offline"
                print(f"  Battery {battery.batIndex}: {battery.batterySn} ({status})")
        """
        await self.client._ensure_authenticated()

        data = {"serialNum": serial_num}

        cache_key = self._get_cache_key("battery_list", serialNum=serial_num)
        response = await self.client._request(
            "POST",
            "/WManage/api/battery/getBatteryInfoForSet",
            data=data,
            cache_key=cache_key,
            cache_endpoint="battery_info",
        )
        return BatteryListResponse.model_validate(response)

    async def get_midbox_runtime(self, serial_num: str) -> MidboxRuntime:
        """Get GridBOSS/MID device runtime data.

        Note: Voltages, currents, and frequency require scaling (÷100).

        Args:
            serial_num: GridBOSS device serial number

        Returns:
            MidboxRuntime: GridBOSS runtime metrics

        Example:
            midbox = await client.devices.get_midbox_runtime("1234567890")
            print(f"Grid Power: {midbox.gridPower}W")
            print(f"Load Power: {midbox.loadPower}W")
            print(f"Generator Power: {midbox.genPower}W")
        """
        await self.client._ensure_authenticated()

        data = {"serialNum": serial_num}

        cache_key = self._get_cache_key("midbox", serialNum=serial_num)
        response = await self.client._request(
            "POST",
            "/WManage/api/midbox/getMidboxRuntime",
            data=data,
            cache_key=cache_key,
            cache_endpoint="midbox_runtime",
        )
        return MidboxRuntime.model_validate(response)
