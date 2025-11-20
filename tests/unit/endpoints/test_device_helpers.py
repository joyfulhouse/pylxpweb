"""Unit tests for device endpoint helper methods."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.models import BatteryInfo, InverterOverviewResponse, InverterRuntime


class TestBulkDeviceData:
    """Test bulk device data convenience methods."""

    @pytest.mark.asyncio
    async def test_get_all_device_data(self) -> None:
        """Test getting all device data in one call."""
        from pylxpweb.endpoints.devices import DeviceEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        devices_endpoint = DeviceEndpoints(mock_client)

        # Mock device overview response
        mock_overview = Mock(spec=InverterOverviewResponse)
        mock_device1 = Mock()
        mock_device1.serialNum = "1111111111"
        mock_device1.deviceType = 6
        mock_device1.deviceTypeText = "18KPV"

        mock_device2 = Mock()
        mock_device2.serialNum = "2222222222"
        mock_device2.deviceType = 6
        mock_device2.deviceTypeText = "18KPV"

        mock_overview.rows = [mock_device1, mock_device2]

        # Mock runtime responses
        mock_runtime1 = Mock(spec=InverterRuntime)
        mock_runtime1.serialNum = "1111111111"
        mock_runtime1.pac = 1500
        mock_runtime1.soc = 70

        mock_runtime2 = Mock(spec=InverterRuntime)
        mock_runtime2.serialNum = "2222222222"
        mock_runtime2.pac = 1600
        mock_runtime2.soc = 71

        # Mock battery responses
        mock_battery1 = Mock(spec=BatteryInfo)
        mock_battery1.serialNum = "1111111111"
        mock_battery1.soc = 70

        mock_battery2 = Mock(spec=BatteryInfo)
        mock_battery2.serialNum = "2222222222"
        mock_battery2.soc = 71

        # Set up mocks
        devices_endpoint.get_devices = AsyncMock(return_value=mock_overview)
        devices_endpoint.get_inverter_runtime = AsyncMock(
            side_effect=[mock_runtime1, mock_runtime2]
        )
        devices_endpoint.get_battery_info = AsyncMock(side_effect=[mock_battery1, mock_battery2])

        # Call get_all_device_data
        result = await devices_endpoint.get_all_device_data(12345)

        # Verify get_devices was called
        devices_endpoint.get_devices.assert_called_once_with(12345)

        # Verify runtime and battery calls for both inverters
        assert devices_endpoint.get_inverter_runtime.call_count == 2
        devices_endpoint.get_inverter_runtime.assert_any_call("1111111111")
        devices_endpoint.get_inverter_runtime.assert_any_call("2222222222")

        assert devices_endpoint.get_battery_info.call_count == 2
        devices_endpoint.get_battery_info.assert_any_call("1111111111")
        devices_endpoint.get_battery_info.assert_any_call("2222222222")

        # Verify result structure
        assert "devices" in result
        assert "runtime" in result
        assert "batteries" in result

        assert result["devices"] == mock_overview
        assert result["runtime"]["1111111111"] == mock_runtime1
        assert result["runtime"]["2222222222"] == mock_runtime2
        assert result["batteries"]["1111111111"] == mock_battery1
        assert result["batteries"]["2222222222"] == mock_battery2

    @pytest.mark.asyncio
    async def test_get_all_device_data_with_errors(self) -> None:
        """Test get_all_device_data handles individual device errors gracefully."""
        from pylxpweb.endpoints.devices import DeviceEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        devices_endpoint = DeviceEndpoints(mock_client)

        # Mock device overview response
        mock_overview = Mock(spec=InverterOverviewResponse)
        mock_device1 = Mock()
        mock_device1.serialNum = "1111111111"
        mock_device1.deviceType = 6
        mock_device1.deviceTypeText = "18KPV"

        mock_device2 = Mock()
        mock_device2.serialNum = "2222222222"
        mock_device2.deviceType = 6
        mock_device2.deviceTypeText = "18KPV"

        mock_overview.rows = [mock_device1, mock_device2]

        # Mock runtime responses (one success, one failure)
        mock_runtime1 = Mock(spec=InverterRuntime)
        mock_runtime1.serialNum = "1111111111"
        mock_runtime1.pac = 1500

        # Mock battery responses (one success, one failure)
        mock_battery2 = Mock(spec=BatteryInfo)
        mock_battery2.serialNum = "2222222222"
        mock_battery2.soc = 71

        # Set up mocks with errors
        devices_endpoint.get_devices = AsyncMock(return_value=mock_overview)
        devices_endpoint.get_inverter_runtime = AsyncMock(
            side_effect=[mock_runtime1, Exception("Device offline")]
        )
        devices_endpoint.get_battery_info = AsyncMock(
            side_effect=[Exception("Battery error"), mock_battery2]
        )

        # Call get_all_device_data (should not raise)
        result = await devices_endpoint.get_all_device_data(12345)

        # Verify result structure - only successful calls included
        assert "devices" in result
        assert "runtime" in result
        assert "batteries" in result

        # Only successful runtime call
        assert "1111111111" in result["runtime"]
        assert "2222222222" not in result["runtime"]

        # Only successful battery call
        assert "2222222222" in result["batteries"]
        assert "1111111111" not in result["batteries"]

    @pytest.mark.asyncio
    async def test_get_all_device_data_no_inverters(self) -> None:
        """Test get_all_device_data with no inverters."""
        from pylxpweb.endpoints.devices import DeviceEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        devices_endpoint = DeviceEndpoints(mock_client)

        # Mock device overview with no inverters
        mock_overview = Mock(spec=InverterOverviewResponse)
        mock_overview.rows = []

        devices_endpoint.get_devices = AsyncMock(return_value=mock_overview)

        # Mock runtime and battery methods to track calls
        devices_endpoint.get_inverter_runtime = AsyncMock()
        devices_endpoint.get_battery_info = AsyncMock()

        # Call get_all_device_data
        result = await devices_endpoint.get_all_device_data(12345)

        # Verify empty results
        assert result["devices"] == mock_overview
        assert result["runtime"] == {}
        assert result["batteries"] == {}

        # Verify no runtime/battery calls made since no inverters
        assert devices_endpoint.get_inverter_runtime.call_count == 0
        assert devices_endpoint.get_battery_info.call_count == 0

    @pytest.mark.asyncio
    async def test_get_all_device_data_concurrency(self) -> None:
        """Test that get_all_device_data makes concurrent API calls."""
        import asyncio

        from pylxpweb.endpoints.devices import DeviceEndpoints

        mock_client = Mock(spec=LuxpowerClient)
        devices_endpoint = DeviceEndpoints(mock_client)

        # Mock device overview response
        mock_overview = Mock(spec=InverterOverviewResponse)
        mock_device1 = Mock()
        mock_device1.serialNum = "1111111111"
        mock_device1.deviceType = 6
        mock_device1.deviceTypeText = "18KPV"

        mock_device2 = Mock()
        mock_device2.serialNum = "2222222222"
        mock_device2.deviceType = 6
        mock_device2.deviceTypeText = "18KPV"

        mock_overview.rows = [mock_device1, mock_device2]

        # Track call times to verify concurrency
        call_times: list[float] = []

        async def mock_runtime_call(serial: str) -> Mock:
            call_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.01)  # Simulate API delay
            mock = Mock(spec=InverterRuntime)
            mock.serialNum = serial
            return mock

        async def mock_battery_call(serial: str) -> Mock:
            call_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.01)  # Simulate API delay
            mock = Mock(spec=BatteryInfo)
            mock.serialNum = serial
            return mock

        # Set up mocks
        devices_endpoint.get_devices = AsyncMock(return_value=mock_overview)
        devices_endpoint.get_inverter_runtime = AsyncMock(side_effect=mock_runtime_call)
        devices_endpoint.get_battery_info = AsyncMock(side_effect=mock_battery_call)

        # Call get_all_device_data
        start_time = asyncio.get_event_loop().time()
        await devices_endpoint.get_all_device_data(12345)
        end_time = asyncio.get_event_loop().time()

        # Verify calls were made concurrently (not sequentially)
        # If sequential: 4 calls * 0.01s = 0.04s minimum
        # If concurrent: 2 parallel groups * 0.01s = 0.02s minimum
        total_time = end_time - start_time
        assert total_time < 0.03, f"Calls appear to be sequential: {total_time}s"

        # Verify all 4 calls were made (2 runtime + 2 battery)
        assert len(call_times) == 4
