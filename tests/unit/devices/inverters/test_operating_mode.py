"""Unit tests for inverter operating mode and quick charge/discharge control."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pylxpweb.devices.inverters.generic import GenericInverter
from pylxpweb.models import OperatingMode, QuickChargeStatus, SuccessResponse


@pytest.fixture
def mock_client():
    """Create a mock client for testing."""
    client = MagicMock()
    client.api = MagicMock()
    client.api.control = MagicMock()
    return client


@pytest.fixture
def inverter(mock_client):
    """Create a generic inverter for testing."""
    return GenericInverter(
        client=mock_client,
        serial_number="1234567890",
        model="18KPV",
    )


class TestOperatingModeControl:
    """Test operating mode control methods."""

    @pytest.mark.asyncio
    async def test_set_operating_mode_to_normal(self, inverter, mock_client):
        """Test setting operating mode to NORMAL."""
        # Mock set_standby_mode method
        inverter.set_standby_mode = AsyncMock(return_value=True)

        result = await inverter.set_operating_mode(OperatingMode.NORMAL)

        assert result is True
        inverter.set_standby_mode.assert_called_once_with(False)

    @pytest.mark.asyncio
    async def test_set_operating_mode_to_standby(self, inverter, mock_client):
        """Test setting operating mode to STANDBY."""
        # Mock set_standby_mode method
        inverter.set_standby_mode = AsyncMock(return_value=True)

        result = await inverter.set_operating_mode(OperatingMode.STANDBY)

        assert result is True
        inverter.set_standby_mode.assert_called_once_with(True)

    @pytest.mark.asyncio
    async def test_get_operating_mode_normal(self, inverter, mock_client):
        """Test getting operating mode when in NORMAL state."""
        # Mock read_parameters to return FUNC_EN with bit 9 set (normal mode)
        inverter.read_parameters = AsyncMock(return_value={"FUNC_EN_REGISTER": 0b1000000000})

        mode = await inverter.get_operating_mode()

        assert mode == OperatingMode.NORMAL
        inverter.read_parameters.assert_called_once_with(21, 1)

    @pytest.mark.asyncio
    async def test_get_operating_mode_standby(self, inverter, mock_client):
        """Test getting operating mode when in STANDBY state."""
        # Mock read_parameters to return FUNC_EN with bit 9 clear (standby mode)
        inverter.read_parameters = AsyncMock(return_value={"FUNC_EN_REGISTER": 0b0000000000})

        mode = await inverter.get_operating_mode()

        assert mode == OperatingMode.STANDBY
        inverter.read_parameters.assert_called_once_with(21, 1)

    @pytest.mark.asyncio
    async def test_get_operating_mode_with_other_bits_set(self, inverter, mock_client):
        """Test getting operating mode when other FUNC_EN bits are set."""
        # Bit 9 set (normal), other bits also set
        inverter.read_parameters = AsyncMock(
            return_value={"FUNC_EN_REGISTER": 0b1111111111}  # All bits set
        )

        mode = await inverter.get_operating_mode()

        assert mode == OperatingMode.NORMAL


class TestQuickChargeControl:
    """Test quick charge control methods."""

    @pytest.mark.asyncio
    async def test_enable_quick_charge(self, inverter, mock_client):
        """Test enabling quick charge."""
        mock_client.api.control.start_quick_charge = AsyncMock(
            return_value=SuccessResponse(success=True)
        )

        result = await inverter.enable_quick_charge()

        assert result is True
        mock_client.api.control.start_quick_charge.assert_called_once_with("1234567890")

    @pytest.mark.asyncio
    async def test_disable_quick_charge(self, inverter, mock_client):
        """Test disabling quick charge."""
        mock_client.api.control.stop_quick_charge = AsyncMock(
            return_value=SuccessResponse(success=True)
        )

        result = await inverter.disable_quick_charge()

        assert result is True
        mock_client.api.control.stop_quick_charge.assert_called_once_with("1234567890")

    @pytest.mark.asyncio
    async def test_get_quick_charge_status_inactive(self, inverter, mock_client):
        """Test getting quick charge status when inactive."""
        mock_client.api.control.get_quick_charge_status = AsyncMock(
            return_value=QuickChargeStatus(
                success=True,
                hasUnclosedQuickChargeTask=False,
                hasUnclosedQuickDischargeTask=False,
            )
        )

        result = await inverter.get_quick_charge_status()

        assert result is False
        mock_client.api.control.get_quick_charge_status.assert_called_once_with("1234567890")

    @pytest.mark.asyncio
    async def test_get_quick_charge_status_active(self, inverter, mock_client):
        """Test getting quick charge status when active."""
        mock_client.api.control.get_quick_charge_status = AsyncMock(
            return_value=QuickChargeStatus(
                success=True,
                hasUnclosedQuickChargeTask=True,
                hasUnclosedQuickDischargeTask=False,
            )
        )

        result = await inverter.get_quick_charge_status()

        assert result is True

    @pytest.mark.asyncio
    async def test_enable_quick_charge_failure(self, inverter, mock_client):
        """Test enabling quick charge when operation fails."""
        mock_client.api.control.start_quick_charge = AsyncMock(
            return_value=SuccessResponse(success=False, message="Device offline")
        )

        result = await inverter.enable_quick_charge()

        assert result is False


class TestQuickDischargeControl:
    """Test quick discharge control methods."""

    @pytest.mark.asyncio
    async def test_enable_quick_discharge(self, inverter, mock_client):
        """Test enabling quick discharge."""
        mock_client.api.control.start_quick_discharge = AsyncMock(
            return_value=SuccessResponse(success=True)
        )

        result = await inverter.enable_quick_discharge()

        assert result is True
        mock_client.api.control.start_quick_discharge.assert_called_once_with("1234567890")

    @pytest.mark.asyncio
    async def test_disable_quick_discharge(self, inverter, mock_client):
        """Test disabling quick discharge."""
        mock_client.api.control.stop_quick_discharge = AsyncMock(
            return_value=SuccessResponse(success=True)
        )

        result = await inverter.disable_quick_discharge()

        assert result is True
        mock_client.api.control.stop_quick_discharge.assert_called_once_with("1234567890")

    @pytest.mark.asyncio
    async def test_get_quick_discharge_status_inactive(self, inverter, mock_client):
        """Test getting quick discharge status when inactive."""
        mock_client.api.control.get_quick_charge_status = AsyncMock(
            return_value=QuickChargeStatus(
                success=True,
                hasUnclosedQuickChargeTask=False,
                hasUnclosedQuickDischargeTask=False,
            )
        )

        result = await inverter.get_quick_discharge_status()

        assert result is False
        # Note: Uses quickCharge/getStatusInfo endpoint
        mock_client.api.control.get_quick_charge_status.assert_called_once_with("1234567890")

    @pytest.mark.asyncio
    async def test_get_quick_discharge_status_active(self, inverter, mock_client):
        """Test getting quick discharge status when active."""
        mock_client.api.control.get_quick_charge_status = AsyncMock(
            return_value=QuickChargeStatus(
                success=True,
                hasUnclosedQuickChargeTask=False,
                hasUnclosedQuickDischargeTask=True,
            )
        )

        result = await inverter.get_quick_discharge_status()

        assert result is True

    @pytest.mark.asyncio
    async def test_get_quick_discharge_status_uses_charge_endpoint(self, inverter, mock_client):
        """Test that discharge status uses the quickCharge/getStatusInfo endpoint."""
        mock_client.api.control.get_quick_charge_status = AsyncMock(
            return_value=QuickChargeStatus(
                success=True,
                hasUnclosedQuickChargeTask=False,
                hasUnclosedQuickDischargeTask=True,
            )
        )

        await inverter.get_quick_discharge_status()

        # Verify it calls get_quick_charge_status (not a separate discharge endpoint)
        mock_client.api.control.get_quick_charge_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_enable_quick_discharge_failure(self, inverter, mock_client):
        """Test enabling quick discharge when operation fails."""
        mock_client.api.control.start_quick_discharge = AsyncMock(
            return_value=SuccessResponse(
                success=False, message="Success device: , Failure device: 1234567890"
            )
        )

        result = await inverter.enable_quick_discharge()

        assert result is False


class TestOperatingModeEnum:
    """Test OperatingMode enum."""

    def test_operating_mode_values(self):
        """Test OperatingMode enum has correct values."""
        assert OperatingMode.NORMAL.value == "normal"
        assert OperatingMode.STANDBY.value == "standby"

    def test_operating_mode_string_representation(self):
        """Test OperatingMode string representation."""
        assert str(OperatingMode.NORMAL) == "normal"
        assert str(OperatingMode.STANDBY) == "standby"

    def test_operating_mode_comparison(self):
        """Test OperatingMode comparison."""
        assert OperatingMode.NORMAL != OperatingMode.STANDBY
        assert OperatingMode.NORMAL == OperatingMode.NORMAL


class TestCombinedOperations:
    """Test combined operating mode and quick charge/discharge scenarios."""

    @pytest.mark.asyncio
    async def test_both_charge_and_discharge_active(self, inverter, mock_client):
        """Test scenario where both quick charge and discharge are active (unlikely but valid)."""
        mock_client.api.control.get_quick_charge_status = AsyncMock(
            return_value=QuickChargeStatus(
                success=True,
                hasUnclosedQuickChargeTask=True,
                hasUnclosedQuickDischargeTask=True,
            )
        )

        charge_status = await inverter.get_quick_charge_status()
        discharge_status = await inverter.get_quick_discharge_status()

        assert charge_status is True
        assert discharge_status is True

    @pytest.mark.asyncio
    async def test_operating_mode_independent_of_quick_charge(self, inverter, mock_client):
        """Test that operating mode and quick charge are independent."""
        # Set to normal mode
        inverter.set_standby_mode = AsyncMock(return_value=True)
        await inverter.set_operating_mode(OperatingMode.NORMAL)

        # Enable quick charge
        mock_client.api.control.start_quick_charge = AsyncMock(
            return_value=SuccessResponse(success=True)
        )
        await inverter.enable_quick_charge()

        # Both should succeed independently
        inverter.set_standby_mode.assert_called_once_with(False)
        mock_client.api.control.start_quick_charge.assert_called_once()
