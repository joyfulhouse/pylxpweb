"""Tests for device factory methods (from_modbus_transport, from_transport)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pylxpweb.constants import (
    DEVICE_TYPE_CODE_GRIDBOSS,
    DEVICE_TYPE_CODE_PV_SERIES,
    DEVICE_TYPE_CODE_SNA,
)
from pylxpweb.devices.inverters.base import BaseInverter
from pylxpweb.devices.mid_device import MIDDevice
from pylxpweb.exceptions import LuxpowerDeviceError
from pylxpweb.transports.data import InverterEnergyData, InverterRuntimeData


@pytest.fixture
def mock_transport() -> MagicMock:
    """Create a mock transport for testing."""
    transport = MagicMock()
    transport.serial = "CE12345678"
    transport.is_connected = True
    transport.connect = AsyncMock()
    transport.read_parameters = AsyncMock()
    transport.read_runtime = AsyncMock(
        return_value=InverterRuntimeData(
            pv_total_power=1000,
            battery_soc=50,
            battery_charge_power=100,
            battery_voltage=52.0,
        )
    )
    transport.read_energy = AsyncMock(
        return_value=InverterEnergyData(
            pv_energy_today=5.0,
            pv_energy_total=1000.0,
        )
    )
    transport.read_battery = AsyncMock(return_value=None)
    return transport


class TestBaseInverterFromModbusTransport:
    """Tests for BaseInverter.from_modbus_transport() factory method."""

    @pytest.mark.asyncio
    async def test_rejects_gridboss_device(self, mock_transport: MagicMock) -> None:
        """Test that from_modbus_transport() rejects GridBOSS devices."""
        # Configure transport to return GridBOSS device type
        mock_transport.read_parameters.return_value = {
            19: DEVICE_TYPE_CODE_GRIDBOSS,
        }

        with pytest.raises(LuxpowerDeviceError) as exc_info:
            await BaseInverter.from_modbus_transport(mock_transport)

        assert "GridBOSS/MIDbox" in str(exc_info.value)
        assert "device type code 50" in str(exc_info.value)
        assert "MIDDevice.from_transport()" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_accepts_pv_series_device(self, mock_transport: MagicMock) -> None:
        """Test that from_modbus_transport() accepts PV Series devices."""
        mock_transport.read_parameters.return_value = {
            19: DEVICE_TYPE_CODE_PV_SERIES,
        }

        inverter = await BaseInverter.from_modbus_transport(mock_transport)

        assert inverter.serial_number == "CE12345678"
        assert inverter.model == "18KPV"  # Default for PV series

    @pytest.mark.asyncio
    async def test_accepts_sna_device(self, mock_transport: MagicMock) -> None:
        """Test that from_modbus_transport() accepts SNA devices."""
        mock_transport.read_parameters.return_value = {
            19: DEVICE_TYPE_CODE_SNA,
        }

        inverter = await BaseInverter.from_modbus_transport(mock_transport)

        assert inverter.serial_number == "CE12345678"
        assert inverter.model == "12000XP"  # Default for SNA series

    @pytest.mark.asyncio
    async def test_connects_transport_if_needed(self, mock_transport: MagicMock) -> None:
        """Test that factory connects transport if not connected."""
        mock_transport.is_connected = False
        mock_transport.read_parameters.return_value = {19: DEVICE_TYPE_CODE_PV_SERIES}

        await BaseInverter.from_modbus_transport(mock_transport)

        mock_transport.connect.assert_called_once()


class TestMIDDeviceFromTransport:
    """Tests for MIDDevice.from_transport() factory method."""

    @pytest.mark.asyncio
    async def test_accepts_gridboss_device(self, mock_transport: MagicMock) -> None:
        """Test that from_transport() accepts GridBOSS devices."""
        mock_transport.serial = "GB12345678"
        mock_transport.read_parameters.return_value = {
            19: DEVICE_TYPE_CODE_GRIDBOSS,
        }

        mid_device = await MIDDevice.from_transport(mock_transport)

        assert mid_device.serial_number == "GB12345678"
        assert mid_device.model == "GridBOSS"
        assert mid_device._transport == mock_transport

    @pytest.mark.asyncio
    async def test_rejects_pv_series_device(self, mock_transport: MagicMock) -> None:
        """Test that from_transport() rejects inverters."""
        mock_transport.read_parameters.return_value = {
            19: DEVICE_TYPE_CODE_PV_SERIES,
        }

        with pytest.raises(LuxpowerDeviceError) as exc_info:
            await MIDDevice.from_transport(mock_transport)

        assert "not a GridBOSS/MIDbox" in str(exc_info.value)
        assert "BaseInverter.from_modbus_transport()" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_accepts_unknown_device_type(self, mock_transport: MagicMock) -> None:
        """Test that from_transport() accepts device with read failure (assumes GridBOSS)."""
        # Simulate read failure - device type code 0 is treated as unknown
        mock_transport.read_parameters.side_effect = Exception("Read error")

        # Should not raise - assumes GridBOSS when read fails
        mid_device = await MIDDevice.from_transport(mock_transport)

        assert mid_device.serial_number == "CE12345678"

    @pytest.mark.asyncio
    async def test_connects_transport_if_needed(self, mock_transport: MagicMock) -> None:
        """Test that factory connects transport if not connected."""
        mock_transport.is_connected = False
        mock_transport.read_parameters.return_value = {19: DEVICE_TYPE_CODE_GRIDBOSS}

        await MIDDevice.from_transport(mock_transport)

        mock_transport.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_custom_model_name(self, mock_transport: MagicMock) -> None:
        """Test that custom model name can be specified."""
        mock_transport.read_parameters.return_value = {
            19: DEVICE_TYPE_CODE_GRIDBOSS,
        }

        mid_device = await MIDDevice.from_transport(mock_transport, model="Custom GridBOSS")

        assert mid_device.model == "Custom GridBOSS"
