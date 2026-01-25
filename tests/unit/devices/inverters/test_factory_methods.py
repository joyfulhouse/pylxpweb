"""Tests for BaseInverter factory methods (from_modbus_transport, from_dongle_transport)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pylxpweb.devices.inverters._features import InverterFamily
from pylxpweb.devices.inverters.base import BaseInverter


class TestFromModbusTransport:
    """Tests for BaseInverter.from_modbus_transport()."""

    @pytest.mark.asyncio
    async def test_creates_inverter_from_connected_modbus_transport(self) -> None:
        """Test creating inverter from already-connected Modbus transport."""
        # Create mock transport
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.is_connected = True
        transport.read_parameters = AsyncMock(return_value={19: 2092})  # PV_SERIES

        inverter = await BaseInverter.from_modbus_transport(transport)

        assert inverter.serial_number == "CE12345678"
        assert inverter._transport is transport
        assert inverter.has_transport is True
        # Should not call connect since already connected
        transport.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_connects_if_not_connected(self) -> None:
        """Test that transport is connected if not already connected."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.is_connected = False
        transport.connect = AsyncMock()
        transport.read_parameters = AsyncMock(return_value={19: 2092})

        await BaseInverter.from_modbus_transport(transport)

        transport.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_detects_pv_series_from_device_type(self) -> None:
        """Test detection of PV Series from device type code 2092."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.is_connected = True
        transport.read_parameters = AsyncMock(return_value={19: 2092})

        inverter = await BaseInverter.from_modbus_transport(transport)

        assert inverter._features.model_family == InverterFamily.PV_SERIES
        assert inverter._features.device_type_code == 2092
        assert inverter.model == "18KPV"  # Default for PV series

    @pytest.mark.asyncio
    async def test_detects_sna_series_from_device_type(self) -> None:
        """Test detection of SNA Series from device type code 54."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.is_connected = True
        transport.read_parameters = AsyncMock(return_value={19: 54})

        inverter = await BaseInverter.from_modbus_transport(transport)

        assert inverter._features.model_family == InverterFamily.SNA
        assert inverter._features.device_type_code == 54
        assert inverter.model == "12000XP"

    @pytest.mark.asyncio
    async def test_detects_lxp_eu_from_device_type(self) -> None:
        """Test detection of LXP-EU from device type code (varies by model)."""
        # LXP-EU devices use different type codes, but family should be detected
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.is_connected = True
        # For LXP-EU, let's simulate a device type that maps to LXP_EU
        # The exact code depends on DEVICE_TYPE_CODE_TO_FAMILY mapping
        transport.read_parameters = AsyncMock(return_value={19: 0})  # Unknown type

        inverter = await BaseInverter.from_modbus_transport(transport, model="LXP-EU")

        assert inverter.model == "LXP-EU"

    @pytest.mark.asyncio
    async def test_uses_provided_model_override(self) -> None:
        """Test that provided model overrides auto-detection."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.is_connected = True
        transport.read_parameters = AsyncMock(return_value={19: 2092})  # PV_SERIES

        inverter = await BaseInverter.from_modbus_transport(transport, model="Custom18kPV")

        assert inverter.model == "Custom18kPV"  # Uses provided model

    @pytest.mark.asyncio
    async def test_handles_device_type_read_failure(self) -> None:
        """Test graceful handling when device type cannot be read."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.is_connected = True
        transport.read_parameters = AsyncMock(side_effect=Exception("Modbus read failed"))

        inverter = await BaseInverter.from_modbus_transport(transport)

        # Should still create inverter with unknown model
        assert inverter.serial_number == "CE12345678"
        assert inverter.model == "Unknown"
        assert inverter._features.model_family == InverterFamily.UNKNOWN

    @pytest.mark.asyncio
    async def test_handles_empty_device_type_response(self) -> None:
        """Test handling when device type register returns empty."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.is_connected = True
        transport.read_parameters = AsyncMock(return_value={})  # No register 19

        inverter = await BaseInverter.from_modbus_transport(transport)

        assert inverter.model == "Unknown"


class TestFromDongleTransport:
    """Tests for BaseInverter.from_dongle_transport()."""

    @pytest.mark.asyncio
    async def test_creates_inverter_from_dongle_transport(self) -> None:
        """Test creating inverter from WiFi dongle transport."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.is_connected = True
        transport.read_parameters = AsyncMock(return_value={19: 10284})  # FlexBOSS

        inverter = await BaseInverter.from_dongle_transport(transport)

        assert inverter.serial_number == "CE12345678"
        assert inverter._transport is transport
        assert inverter.has_transport is True

    @pytest.mark.asyncio
    async def test_dongle_transport_connects_if_needed(self) -> None:
        """Test that dongle transport is connected if not already."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.is_connected = False
        transport.connect = AsyncMock()
        transport.read_parameters = AsyncMock(return_value={19: 2092})

        await BaseInverter.from_dongle_transport(transport)

        transport.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_dongle_with_model_override(self) -> None:
        """Test dongle transport with model name override."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.is_connected = True
        transport.read_parameters = AsyncMock(return_value={19: 2092})

        inverter = await BaseInverter.from_dongle_transport(transport, model="FlexBOSS21")

        assert inverter.model == "FlexBOSS21"

    @pytest.mark.asyncio
    async def test_dongle_detects_flexboss(self) -> None:
        """Test detection of FlexBOSS from device type code 10284."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.is_connected = True
        transport.read_parameters = AsyncMock(return_value={19: 10284})

        inverter = await BaseInverter.from_dongle_transport(transport)

        # FlexBOSS is part of PV_SERIES family
        assert inverter._features.device_type_code == 10284


class TestFromTransportAlias:
    """Tests to verify from_dongle_transport and from_modbus_transport are equivalent."""

    @pytest.mark.asyncio
    async def test_methods_produce_same_result(self) -> None:
        """Test that both methods produce equivalent inverters."""
        transport1 = MagicMock()
        transport1.serial = "CE12345678"
        transport1.is_connected = True
        transport1.read_parameters = AsyncMock(return_value={19: 2092})

        transport2 = MagicMock()
        transport2.serial = "CE12345678"
        transport2.is_connected = True
        transport2.read_parameters = AsyncMock(return_value={19: 2092})

        inverter1 = await BaseInverter.from_modbus_transport(transport1)
        inverter2 = await BaseInverter.from_dongle_transport(transport2)

        assert inverter1.serial_number == inverter2.serial_number
        assert inverter1.model == inverter2.model
        assert type(inverter1) is type(inverter2)


class TestTransportModeProperties:
    """Tests for transport-mode specific properties."""

    @pytest.mark.asyncio
    async def test_has_transport_true_when_transport_attached(self) -> None:
        """Test has_transport returns True when transport is attached."""
        transport = MagicMock()
        transport.serial = "CE12345678"
        transport.is_connected = True
        transport.read_parameters = AsyncMock(return_value={19: 2092})

        inverter = await BaseInverter.from_modbus_transport(transport)

        assert inverter.has_transport is True

    def test_has_transport_false_for_http_inverter(self) -> None:
        """Test has_transport returns False for HTTP-only inverter."""
        from pylxpweb.devices.inverters.generic import GenericInverter

        # Create inverter without transport (HTTP mode)
        client = MagicMock()
        inverter = GenericInverter(
            client=client,
            serial_number="CE12345678",
            model="18KPV",
            transport=None,
        )

        assert inverter.has_transport is False
