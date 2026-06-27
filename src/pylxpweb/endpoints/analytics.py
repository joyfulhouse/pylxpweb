"""Analytics endpoints for the Luxpower API.

This module provides analytics functionality including:
- Time-series chart data for sensors
- Energy breakdowns (hourly, daily, monthly, yearly, lifetime)
- Event/fault/warning logs
- Battery and inverter information
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pylxpweb.endpoints.base import BaseEndpoint
from pylxpweb.models import DailyEnergyHistoryEntry, MonthlyEnergyHistory

if TYPE_CHECKING:
    from pylxpweb.client import LuxpowerClient

# Energy fields carried by /WManage/api/inverterChart/monthColumn[Parallel] rows.
# Derived from the EG4 mobile app's chart parser (decompiled) plus the standard
# daily energy field family; unknown extra fields are ignored.
_DAILY_HISTORY_FIELDS: tuple[str, ...] = (
    "ePvDay",
    "ePv1Day",
    "ePv2Day",
    "ePv3Day",
    "eInvDay",
    "eRecDay",
    "eChgDay",
    "eDisChgDay",
    "eEpsDay",
    "eToGridDay",
    "eExportDay",
    "eToUserDay",
    "eImportDay",
    "eConsumptionDay",
    "eGenDay",
)


class AnalyticsEndpoints(BaseEndpoint):
    """Analytics endpoints for charts, energy breakdowns, and event logs."""

    def __init__(self, client: LuxpowerClient) -> None:
        """Initialize analytics endpoints.

        Args:
            client: The parent LuxpowerClient instance
        """
        super().__init__(client)

    async def get_chart_data(
        self,
        serial_num: str,
        attribute: str,
        date: str,
    ) -> dict[str, Any]:
        """Get time-series data for specific sensor attribute.

        This endpoint retrieves hourly time-series data for any sensor attribute
        over a specific date. Very flexible - supports all InverterRuntime fields.

        Available attributes: vpv1, vpv2, ppv, ppv1, ppv2, vBat, soc, pCharge,
        pDisCharge, pToGrid, pToUser, pInv, pRec, pEps, vacr, vacs, vact, fac,
        tinner, tradiator1, tradiator2, tBat, and more.

        Args:
            serial_num: Device serial number
            attribute: Sensor attribute name (from InverterRuntime fields)
            date: Date in YYYY-MM-DD format

        Returns:
            Dict containing:
                - success: Boolean
                - dataPoints: List of {time: str, value: number} objects

        Example:
            # Get PV voltage over time
            data = await client.analytics.get_chart_data("1234567890", "vpv1", "2025-11-19")
            for point in data["dataPoints"]:
                print(f"{point['time']}: {point['value']/100}V")  # Scale voltage

        Note:
            Data points are typically hourly (24 entries for full day).
            Remember to apply scaling factors (voltage ÷100, etc.)
        """
        await self.client._ensure_authenticated()

        data = {
            "serialNum": serial_num,
            "attr": attribute,
            "dateText": date,
        }

        response = await self.client._request(
            "POST",
            "/WManage/api/analyze/chart/dayLine",
            data=data,
        )

        return dict(response)

    async def get_energy_day_breakdown(
        self,
        serial_num: str,
        date: str,
        energy_type: str = "eInvDay",
        *,
        parallel: bool = False,
    ) -> dict[str, Any]:
        """Get hourly energy breakdown for specific day.

        Returns 24 hourly energy values for the specified date and energy type.

        Energy Types:
            - eInvDay: Inverter daily energy production
            - eToUserDay: Load consumption
            - eToGridDay: Grid export
            - eAcChargeDay: AC charging
            - eBatChargeDay: Battery charging
            - eBatDischargeDay: Battery discharging

        Args:
            serial_num: Device serial number
            date: Date in YYYY-MM-DD format
            energy_type: Energy type to query (default: eInvDay)
            parallel: Query parallel group data (default: False)

        Returns:
            Dict containing:
                - success: Boolean
                - dataPoints: List of {period: str, value: number} hourly energy values

        Example:
            # Get hourly solar production
            breakdown = await client.analytics.get_energy_day_breakdown(
                "1234567890",
                "2025-11-19",
                "eInvDay"
            )
            total = sum(p["value"] for p in breakdown["dataPoints"])
            print(f"Total production: {total/1000}kWh")
        """
        await self.client._ensure_authenticated()

        # Parse date to extract year, month, day
        date_obj = datetime.strptime(date, "%Y-%m-%d")

        data = {
            "serialNum": serial_num,
            "parallel": str(parallel).lower(),
            "year": date_obj.year,
            "month": date_obj.month,
            "day": date_obj.day,
            "energyType": energy_type,
        }

        response = await self.client._request(
            "POST",
            "/WManage/api/analyze/energy/dayColumn",
            data=data,
        )

        return dict(response)

    async def get_energy_month_breakdown(
        self,
        serial_num: str,
        year: int,
        month: int,
        energy_type: str = "eInvDay",
        *,
        parallel: bool = False,
    ) -> dict[str, Any]:
        """Get daily energy breakdown for specific month.

        Returns daily energy values for each day in the specified month.

        Args:
            serial_num: Device serial number
            year: Year (e.g., 2025)
            month: Month (1-12)
            energy_type: Energy type to query (default: eInvDay)
            parallel: Query parallel group data (default: False)

        Returns:
            Dict containing:
                - success: Boolean
                - dataPoints: List of {period: str, value: number} daily energy values

        Example:
            # Get November 2025 daily production
            breakdown = await client.analytics.get_energy_month_breakdown(
                "1234567890",
                2025,
                11,
                "eInvDay"
            )
        """
        await self.client._ensure_authenticated()

        data = {
            "serialNum": serial_num,
            "parallel": str(parallel).lower(),
            "year": year,
            "month": month,
            "energyType": energy_type,
        }

        response = await self.client._request(
            "POST",
            "/WManage/api/analyze/energy/monthColumn",
            data=data,
        )

        return dict(response)

    async def get_month_daily_energy(
        self,
        serial_num: str,
        year: int,
        month: int,
        *,
        parallel: bool = False,
    ) -> MonthlyEnergyHistory:
        """Get typed daily energy history for one calendar month.

        Wraps ``/WManage/api/inverterChart/monthColumn`` (single inverter) or
        ``/WManage/api/inverterChart/monthColumnParallel`` (parallel-group
        aggregate) — the endpoints the EG4 mobile app uses for its daily
        energy bar charts. Unlike :meth:`get_energy_month_breakdown`, a
        single request returns ALL energy series for the month (PV, yield,
        charge, discharge, grid import/export, consumption), with known
        0.1 kWh raw units.

        Args:
            serial_num: Inverter serial number. For ``parallel=True`` use the
                serial of any inverter in the parallel group.
            year: Year (e.g., 2025)
            month: Month (1-12)
            parallel: Query the parallel-group aggregate endpoint

        Returns:
            MonthlyEnergyHistory with one entry per returned day. Day numbers
            come from each row's ``day`` field when present, otherwise from
            the row position (1-based), matching the EG4 app's behavior.

        Example:
            history = await client.analytics.get_month_daily_energy(
                "1234567890", 2025, 11
            )
            for entry in history.days:
                print(f"{history.year}-{history.month:02d}-{entry.day:02d}: "
                      f"{entry.inverter_kwh} kWh")
        """
        await self.client._ensure_authenticated()

        endpoint = "/WManage/api/inverterChart/monthColumn"
        if parallel:
            endpoint = "/WManage/api/inverterChart/monthColumnParallel"

        data = {
            "serialNum": serial_num,
            "year": year,
            "month": month,
        }

        response = await self.client._request("POST", endpoint, data=data)

        rows = response.get("data")
        entries: list[DailyEnergyHistoryEntry] = []
        if isinstance(rows, list):
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                day_field = row.get("day")
                if isinstance(day_field, int) and 1 <= day_field <= 31:
                    day = day_field
                else:
                    day = index + 1
                payload: dict[str, Any] = {"day": day}
                for field in _DAILY_HISTORY_FIELDS:
                    value = row.get(field)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        payload[field] = value
                entries.append(DailyEnergyHistoryEntry.model_validate(payload))

        return MonthlyEnergyHistory(
            success=bool(response.get("success", False)),
            year=year,
            month=month,
            days=entries,
        )

    async def get_energy_year_breakdown(
        self,
        serial_num: str,
        year: int,
        energy_type: str = "eInvDay",
        *,
        parallel: bool = False,
    ) -> dict[str, Any]:
        """Get monthly energy breakdown for specific year.

        Returns monthly energy values for the specified year (12 months).

        Args:
            serial_num: Device serial number
            year: Year (e.g., 2025)
            energy_type: Energy type to query (default: eInvDay)
            parallel: Query parallel group data (default: False)

        Returns:
            Dict containing:
                - success: Boolean
                - dataPoints: List of {period: str, value: number} monthly energy values

        Example:
            # Get 2025 monthly production
            breakdown = await client.analytics.get_energy_year_breakdown(
                "1234567890",
                2025,
                "eInvDay"
            )
        """
        await self.client._ensure_authenticated()

        data = {
            "serialNum": serial_num,
            "parallel": str(parallel).lower(),
            "year": year,
            "energyType": energy_type,
        }

        response = await self.client._request(
            "POST",
            "/WManage/api/analyze/energy/yearColumn",
            data=data,
        )

        return dict(response)

    async def get_energy_total_breakdown(
        self,
        serial_num: str,
        energy_type: str = "eInvDay",
        *,
        parallel: bool = False,
    ) -> dict[str, Any]:
        """Get yearly energy breakdown for device lifetime.

        Returns energy data broken down by year for the device's entire lifetime.

        Args:
            serial_num: Device serial number
            energy_type: Energy type to query (default: eInvDay)
            parallel: Query parallel group data (default: False)

        Returns:
            Dict containing:
                - success: Boolean
                - dataPoints: List of {period: str, value: number} yearly energy values

        Example:
            # Get lifetime yearly production
            breakdown = await client.analytics.get_energy_total_breakdown(
                "1234567890",
                "eInvDay"
            )
        """
        await self.client._ensure_authenticated()

        data = {
            "serialNum": serial_num,
            "parallel": str(parallel).lower(),
            "energyType": energy_type,
        }

        response = await self.client._request(
            "POST",
            "/WManage/api/analyze/energy/totalColumn",
            data=data,
        )

        return dict(response)

    async def get_event_list(
        self,
        serial_num: str,
        *,
        page: int = 1,
        rows: int = 30,
        plant_id: int = -1,
        event_filter: str = "_all",
    ) -> dict[str, Any]:
        """Get fault/warning/event log with pagination.

        Retrieves system events including faults, warnings, and informational messages.
        Critical for monitoring system health and tracking issues over time.

        Args:
            serial_num: Device serial number
            page: Page number (default: 1)
            rows: Rows per page (default: 30)
            plant_id: Plant ID filter (-1 for all plants)
            event_filter: Event type filter ("_all", or specific fault/warning code)

        Returns:
            Dict containing:
                - success: Boolean
                - total: Total number of events
                - rows: List of event objects with:
                    - eventId: Event identifier
                    - eventCode: Fault/warning code
                    - eventType: FAULT/WARNING/INFO
                    - eventText: Human-readable description
                    - startTime: Event start timestamp
                    - endTime: Event end timestamp (empty if ongoing)
                    - statusText: ACTIVE/RESOLVED

        Example:
            # Get all events
            events = await client.analytics.get_event_list("1234567890")
            for event in events["rows"]:
                if event["statusText"] == "ACTIVE":
                    print(f"Active {event['eventType']}: {event['eventText']}")

            # Get only faults
            faults = await client.analytics.get_event_list(
                "1234567890",
                event_filter="FAULT"
            )
        """
        await self.client._ensure_authenticated()

        data = {
            "page": page,
            "rows": rows,
            "plantId": plant_id,
            "serialNum": serial_num,
            "eventText": event_filter,
        }

        response = await self.client._request(
            "POST",
            "/WManage/api/analyze/event/list",
            data=data,
        )

        return dict(response)

    async def get_battery_list(self, serial_num: str) -> dict[str, Any]:
        """Get simplified battery list for UI selection.

        Retrieves lightweight battery enumeration without full metrics.
        Useful for populating dropdown menus or battery selection UI.

        Difference from devices.get_battery_info():
            - This endpoint: Only batteryKey, SN, index, online status
            - Full endpoint: Complete metrics (voltage, current, SOC, SoH, temps, etc.)

        Args:
            serial_num: Inverter serial number

        Returns:
            Dict containing:
                - success: Boolean
                - serialNum: Inverter serial number
                - totalNumber: Total battery count
                - batteryArray: List of battery objects with:
                    - batteryKey: Unique identifier
                    - batterySn: Battery serial number
                    - batIndex: Position in array (0-indexed)
                    - lost: Whether battery is offline

        Example:
            batteries = await client.analytics.get_battery_list("1234567890")
            print(f"Found {batteries['totalNumber']} batteries")
            for bat in batteries["batteryArray"]:
                status = "Offline" if bat["lost"] else "Online"
                print(f"  {bat['batterySn']}: {status}")
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

        return dict(response)

    async def get_inverter_info(self, serial_num: str) -> dict[str, Any]:
        """Get inverter static information.

        Retrieves inverter configuration and static details (model, firmware, capacity).

        Complements devices.get_inverter_runtime():
            - This endpoint: Static configuration data
            - Runtime endpoint: Dynamic operational metrics

        Args:
            serial_num: Inverter serial number

        Returns:
            Dict containing:
                - success: Boolean
                - serialNum: Inverter serial number
                - deviceType: Device type code
                - deviceTypeText: Model name (e.g., "18KPV")
                - powerRating: Power rating code
                - powerRatingText: Power rating (e.g., "12kW")
                - fwCode: Firmware version
                - batteryType: LITHIUM/LEAD_ACID
                - nominalCapacity: Battery capacity (Ah)
                - installedCapacity: PV capacity (W)
                - phase: 1=single phase, 3=three phase

        Example:
            info = await client.analytics.get_inverter_info("1234567890")
            print(f"Model: {info['deviceTypeText']}")
            print(f"Firmware: {info['fwCode']}")
            print(f"PV Capacity: {info['installedCapacity']}W")
        """
        await self.client._ensure_authenticated()

        data = {"serialNum": serial_num}

        cache_key = self._get_cache_key("inverter_info", serialNum=serial_num)
        response = await self.client._request(
            "POST",
            "/WManage/api/inverter/getInverterInfo",
            data=data,
            cache_key=cache_key,
            cache_endpoint="device_discovery",
        )

        return dict(response)
