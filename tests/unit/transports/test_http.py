"""Tests for HTTP transport implementation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pylxpweb.exceptions import LuxpowerAPIError, LuxpowerAuthError
from pylxpweb.transports.exceptions import (
    TransportConnectionError,
    TransportReadError,
)
from pylxpweb.transports.http import HTTPTransport


class TestHTTPTransport:
    """Tests for HTTPTransport class."""

    def test_init(self) -> None:
        """Test HTTP transport initialization."""
        client = MagicMock()
        transport = HTTPTransport(client, serial="CE12345678")

        assert transport.serial == "CE12345678"
        assert transport.is_connected is False
        assert transport._client is client

    def test_capabilities(self) -> None:
        """Test HTTP transport capabilities."""
        client = MagicMock()
        transport = HTTPTransport(client, serial="CE12345678")

        caps = transport.capabilities
        assert caps.can_read_runtime is True
        assert caps.can_read_energy is True
        assert caps.can_read_battery is True
        assert caps.is_local is False
        assert caps.requires_authentication is True

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        """Test successful connection."""
        client = MagicMock()
        client.login = AsyncMock()

        transport = HTTPTransport(client, serial="CE12345678")
        await transport.connect()

        assert transport.is_connected is True
        client.login.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self) -> None:
        """Test connection failure."""
        client = MagicMock()
        client.login = AsyncMock(side_effect=LuxpowerAuthError("Auth failed"))

        transport = HTTPTransport(client, serial="CE12345678")

        with pytest.raises(TransportConnectionError, match="Authentication failed"):
            await transport.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        """Test disconnection."""
        client = MagicMock()
        client.login = AsyncMock()

        transport = HTTPTransport(client, serial="CE12345678")
        await transport.connect()
        assert transport.is_connected is True

        await transport.disconnect()
        assert transport.is_connected is False

    @pytest.mark.asyncio
    async def test_read_runtime_success(self) -> None:
        """Test successful runtime read."""
        client = MagicMock()
        client.login = AsyncMock()

        # Create mock runtime response
        mock_runtime = MagicMock()
        mock_runtime.vpv1 = 5100
        mock_runtime.vpv2 = 5050
        mock_runtime.vpv3 = None
        mock_runtime.ppv1 = 1000
        mock_runtime.ppv2 = 1500
        mock_runtime.ppv3 = None
        mock_runtime.ppv = 2500
        mock_runtime.vBat = 530
        mock_runtime.soc = 85
        mock_runtime.pCharge = 500
        mock_runtime.pDisCharge = 0
        mock_runtime.tBat = 25
        mock_runtime.vacr = 2410
        mock_runtime.vacs = 2415
        mock_runtime.vact = 2420
        mock_runtime.fac = 5998
        mock_runtime.prec = 100
        mock_runtime.pToGrid = 200
        mock_runtime.pinv = 2300
        mock_runtime.vepsr = 2400
        mock_runtime.vepss = 2405
        mock_runtime.vepst = 2410
        mock_runtime.feps = 5999
        mock_runtime.peps = 300
        mock_runtime.seps = 1
        mock_runtime.pToUser = 1500
        mock_runtime.vBus1 = 3700
        mock_runtime.vBus2 = 3650
        mock_runtime.tinner = 35
        mock_runtime.tradiator1 = 40
        mock_runtime.tradiator2 = 38
        mock_runtime.status = 0

        client.api.devices.get_inverter_runtime = AsyncMock(return_value=mock_runtime)

        transport = HTTPTransport(client, serial="CE12345678")
        await transport.connect()

        runtime = await transport.read_runtime()

        assert runtime.pv_total_power == 2500.0
        assert runtime.battery_soc == 85
        assert runtime.grid_frequency == pytest.approx(59.98, rel=0.01)

    @pytest.mark.asyncio
    async def test_read_runtime_not_connected(self) -> None:
        """Test runtime read when not connected."""
        client = MagicMock()
        transport = HTTPTransport(client, serial="CE12345678")

        with pytest.raises(TransportConnectionError, match="Transport not connected"):
            await transport.read_runtime()

    @pytest.mark.asyncio
    async def test_read_runtime_api_error(self) -> None:
        """Test runtime read with API error."""
        client = MagicMock()
        client.login = AsyncMock()
        client.api.devices.get_inverter_runtime = AsyncMock(
            side_effect=LuxpowerAPIError("API error")
        )

        transport = HTTPTransport(client, serial="CE12345678")
        await transport.connect()

        with pytest.raises(TransportReadError, match="Failed to read runtime"):
            await transport.read_runtime()

    @pytest.mark.asyncio
    async def test_read_energy_success(self) -> None:
        """Test successful energy read."""
        client = MagicMock()
        client.login = AsyncMock()

        # Create mock energy response
        mock_energy = MagicMock()
        mock_energy.todayYielding = 184
        mock_energy.todayCharging = 50
        mock_energy.todayDischarging = 30
        mock_energy.todayImport = 100
        mock_energy.todayExport = 150
        mock_energy.todayUsage = 200
        mock_energy.totalYielding = 50000
        mock_energy.totalCharging = 10000
        mock_energy.totalDischarging = 8000
        mock_energy.totalImport = 15000
        mock_energy.totalExport = 25000
        mock_energy.totalUsage = 40000

        client.api.devices.get_inverter_energy = AsyncMock(return_value=mock_energy)

        transport = HTTPTransport(client, serial="CE12345678")
        await transport.connect()

        energy = await transport.read_energy()

        assert energy.pv_energy_today == pytest.approx(18.4, rel=0.01)
        assert energy.charge_energy_today == pytest.approx(5.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_read_battery_returns_none_when_no_battery(self) -> None:
        """Test battery read returns None when no battery info."""
        client = MagicMock()
        client.login = AsyncMock()
        client.api.devices.get_battery_info = AsyncMock(return_value=None)

        transport = HTTPTransport(client, serial="CE12345678")
        await transport.connect()

        battery = await transport.read_battery()

        assert battery is None

    @pytest.mark.asyncio
    async def test_read_battery_success(self) -> None:
        """Test successful battery read."""
        client = MagicMock()
        client.login = AsyncMock()

        # Create mock battery response
        mock_battery = MagicMock()
        mock_battery.vBat = 530  # 53.0V
        mock_battery.soc = 85
        mock_battery.pCharge = 500
        mock_battery.pDisCharge = 0
        mock_battery.maxBatteryCharge = 100
        mock_battery.currentBatteryCharge = 85.0
        mock_battery.totalNumber = 2
        mock_battery.batteryArray = []

        client.api.devices.get_battery_info = AsyncMock(return_value=mock_battery)

        transport = HTTPTransport(client, serial="CE12345678")
        await transport.connect()

        battery = await transport.read_battery()

        assert battery is not None
        assert battery.voltage == pytest.approx(53.0, rel=0.01)
        assert battery.soc == 85
        assert battery.charge_power == 500.0

    @pytest.mark.asyncio
    async def test_read_battery_uses_cached_bat_parallel_num(self) -> None:
        """Test battery count uses cached batParallelNum from runtime.

        For LXP-EU devices, getBatteryInfo.totalNumber can return 0 when
        CAN bus communication with battery BMS isn't established.
        The batParallelNum from runtime is always correct.
        """
        client = MagicMock()
        client.login = AsyncMock()

        # Mock runtime with batParallelNum=3
        mock_runtime = MagicMock()
        mock_runtime.batParallelNum = "3"  # String from API
        # Add required fields for InverterRuntimeData.from_http_response
        mock_runtime.vpv1 = 0
        mock_runtime.vpv2 = 0
        mock_runtime.vpv3 = None
        mock_runtime.vpv4 = None
        mock_runtime.ppv1 = 0
        mock_runtime.ppv2 = 0
        mock_runtime.ppv3 = None
        mock_runtime.ppv4 = None
        mock_runtime.ppv = 0
        mock_runtime.vBat = 0
        mock_runtime.soc = 50
        mock_runtime.pCharge = 0
        mock_runtime.pDisCharge = 0
        mock_runtime.vacr = 0
        mock_runtime.vacs = 0
        mock_runtime.vact = 0
        mock_runtime.fac = 0
        mock_runtime.vepsr = 0
        mock_runtime.vepss = 0
        mock_runtime.vepst = 0
        mock_runtime.feps = 0
        mock_runtime.seps = 0
        mock_runtime.pToGrid = 0
        mock_runtime.pToUser = 0
        mock_runtime.peps = 0
        mock_runtime.tinner = 25
        mock_runtime.tradiator1 = 25
        mock_runtime.tradiator2 = 25
        mock_runtime.vBus1 = 0
        mock_runtime.vBus2 = 0
        mock_runtime.status = 0
        mock_runtime.faultCode = 0
        mock_runtime.warningCode = 0
        mock_runtime.workMode = 0
        mock_runtime.masterOrSlave = 0
        mock_runtime.invBatV = 0
        mock_runtime.maxChgCurr = 0
        mock_runtime.maxDischgCurr = 0
        mock_runtime.acChargeEnergy = 0
        mock_runtime.chargePrior = 0
        client.api.devices.get_inverter_runtime = AsyncMock(return_value=mock_runtime)

        # Mock battery info with totalNumber=0 (simulating CAN bus issue)
        mock_battery = MagicMock()
        mock_battery.vBat = 530
        mock_battery.soc = 85
        mock_battery.pCharge = 0
        mock_battery.pDisCharge = 0
        mock_battery.maxBatteryCharge = 100
        mock_battery.currentBatteryCharge = 85.0
        mock_battery.totalNumber = 0  # BMS communication failed
        mock_battery.batteryArray = []
        client.api.devices.get_battery_info = AsyncMock(return_value=mock_battery)

        transport = HTTPTransport(client, serial="CE12345678")
        await transport.connect()

        # First read runtime to cache batParallelNum
        await transport.read_runtime()

        # Now read battery - should use cached value instead of totalNumber
        battery = await transport.read_battery()

        assert battery is not None
        assert battery.battery_count == 3  # From cached batParallelNum, not totalNumber

    @pytest.mark.asyncio
    async def test_read_battery_fallback_to_total_number(self) -> None:
        """Test battery count falls back to totalNumber when no cached value."""
        client = MagicMock()
        client.login = AsyncMock()

        # Mock battery info with totalNumber=2
        mock_battery = MagicMock()
        mock_battery.vBat = 530
        mock_battery.soc = 85
        mock_battery.pCharge = 0
        mock_battery.pDisCharge = 0
        mock_battery.maxBatteryCharge = 100
        mock_battery.currentBatteryCharge = 85.0
        mock_battery.totalNumber = 2
        mock_battery.batteryArray = []
        client.api.devices.get_battery_info = AsyncMock(return_value=mock_battery)

        transport = HTTPTransport(client, serial="CE12345678")
        await transport.connect()

        # Read battery without first reading runtime (no cached batParallelNum)
        battery = await transport.read_battery()

        assert battery is not None
        assert battery.battery_count == 2  # From totalNumber

    @pytest.mark.asyncio
    async def test_manual_connect_disconnect(self) -> None:
        """Test manual connect and disconnect."""
        client = MagicMock()
        client.login = AsyncMock()

        transport = HTTPTransport(client, serial="CE12345678")
        await transport.connect()
        assert transport.is_connected is True

        await transport.disconnect()
        assert transport.is_connected is False

    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        """Test async context manager (async with)."""
        client = MagicMock()
        client.login = AsyncMock()

        transport = HTTPTransport(client, serial="CE12345678")

        async with transport as t:
            assert t is transport
            assert transport.is_connected is True

        assert transport.is_connected is False
        client.login.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_read_parameters_success(self) -> None:
        """Test successful parameter read."""
        client = MagicMock()
        client.login = AsyncMock()

        # Create mock parameter response
        mock_response = MagicMock()
        mock_response.parameters = {"0": 100, "1": 200, "2": 300}

        client.api.control.read_parameters = AsyncMock(return_value=mock_response)

        transport = HTTPTransport(client, serial="CE12345678")
        await transport.connect()

        params = await transport.read_parameters(0, 3)

        assert params == {0: 100, 1: 200, 2: 300}
        client.api.control.read_parameters.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_read_parameters_not_connected(self) -> None:
        """Test parameter read when not connected."""
        client = MagicMock()
        transport = HTTPTransport(client, serial="CE12345678")

        with pytest.raises(TransportConnectionError, match="Transport not connected"):
            await transport.read_parameters(0, 10)

    @pytest.mark.asyncio
    async def test_read_parameters_api_error(self) -> None:
        """Test parameter read with API error."""
        client = MagicMock()
        client.login = AsyncMock()
        client.api.control.read_parameters = AsyncMock(side_effect=LuxpowerAPIError("API error"))

        transport = HTTPTransport(client, serial="CE12345678")
        await transport.connect()

        with pytest.raises(TransportReadError, match="Failed to read parameters"):
            await transport.read_parameters(0, 10)

    @pytest.mark.asyncio
    async def test_write_parameters_success(self) -> None:
        """Test successful parameter write."""
        client = MagicMock()
        client.login = AsyncMock()
        client.api.control.write_parameters = AsyncMock()

        transport = HTTPTransport(client, serial="CE12345678")
        await transport.connect()

        result = await transport.write_parameters({0: 100, 1: 200})

        assert result is True
        client.api.control.write_parameters.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_write_parameters_not_connected(self) -> None:
        """Test parameter write when not connected."""

        client = MagicMock()
        transport = HTTPTransport(client, serial="CE12345678")

        with pytest.raises(TransportConnectionError, match="Transport not connected"):
            await transport.write_parameters({0: 100})

    @pytest.mark.asyncio
    async def test_write_parameters_api_error(self) -> None:
        """Test parameter write with API error."""
        from pylxpweb.transports.exceptions import TransportWriteError

        client = MagicMock()
        client.login = AsyncMock()
        client.api.control.write_parameters = AsyncMock(side_effect=LuxpowerAPIError("API error"))

        transport = HTTPTransport(client, serial="CE12345678")
        await transport.connect()

        with pytest.raises(TransportWriteError, match="Failed to write parameters"):
            await transport.write_parameters({0: 100})
