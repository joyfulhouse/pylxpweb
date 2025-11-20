"""Unit tests for HybridInverter class."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.inverters.hybrid import HybridInverter


@pytest.fixture
def mock_client() -> LuxpowerClient:
    """Create a mock client for testing."""
    client = Mock(spec=LuxpowerClient)
    client.api = Mock()
    client.api.control = Mock()
    return client


class TestHybridInverterInitialization:
    """Test HybridInverter initialization."""

    def test_hybrid_inverter_initialization(self, mock_client: LuxpowerClient) -> None:
        """Test HybridInverter can be instantiated."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        assert inverter.serial_number == "1234567890"
        assert inverter.model == "FlexBOSS21"
        assert inverter.runtime is None
        assert inverter.energy is None
        assert inverter.batteries == []


class TestACChargeOperations:
    """Test AC charge control operations."""

    @pytest.mark.asyncio
    async def test_get_ac_charge_settings(self, mock_client: LuxpowerClient) -> None:
        """Test reading AC charge configuration."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Mock function enable register read
        mock_func_response = Mock()
        mock_func_response.parameters = {"reg_21": 128}  # Bit 7 set (AC charge enabled)

        # Mock AC charge parameters read
        mock_ac_response = Mock()
        mock_ac_response.parameters = {
            "HOLD_AC_CHARGE_POWER_CMD": 50,
            "HOLD_AC_CHARGE_SOC_LIMIT": 100,
            "HOLD_AC_CHARGE_ENABLE_1": 1,
            "HOLD_AC_CHARGE_ENABLE_2": 0,
        }

        mock_client.api.control.read_parameters = AsyncMock(
            side_effect=[mock_func_response, mock_ac_response]
        )

        # Get AC charge settings
        settings = await inverter.get_ac_charge_settings()

        # Verify both API calls
        assert mock_client.api.control.read_parameters.call_count == 2
        mock_client.api.control.read_parameters.assert_any_call("1234567890", 21, 1)
        mock_client.api.control.read_parameters.assert_any_call("1234567890", 66, 8)

        # Verify returned data
        assert settings == {
            "enabled": True,
            "power_percent": 50,
            "soc_limit": 100,
            "schedule1_enabled": True,
            "schedule2_enabled": False,
        }

    @pytest.mark.asyncio
    async def test_set_ac_charge_enable(self, mock_client: LuxpowerClient) -> None:
        """Test enabling AC charge."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Mock read response - AC charge currently disabled
        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_21": 0}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        # Mock write response
        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        # Enable AC charge
        result = await inverter.set_ac_charge(enabled=True)

        # Verify write call - bit 7 should be set (128)
        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {21: 128})

        assert result is True

    @pytest.mark.asyncio
    async def test_set_ac_charge_disable(self, mock_client: LuxpowerClient) -> None:
        """Test disabling AC charge."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Mock read response - AC charge currently enabled
        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_21": 128}  # Bit 7 set
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        # Mock write response
        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        # Disable AC charge
        result = await inverter.set_ac_charge(enabled=False)

        # Verify write call - bit 7 should be cleared (0)
        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {21: 0})

        assert result is True

    @pytest.mark.asyncio
    async def test_set_ac_charge_with_power_and_soc(self, mock_client: LuxpowerClient) -> None:
        """Test setting AC charge with power and SOC parameters."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Mock read response
        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_21": 0}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        # Mock write response
        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        # Enable AC charge with power and SOC
        result = await inverter.set_ac_charge(enabled=True, power_percent=75, soc_limit=95)

        # Verify write call with all three parameters
        mock_client.api.control.write_parameters.assert_called_once_with(
            "1234567890", {21: 128, 66: 75, 67: 95}
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_set_ac_charge_power_validation_too_low(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test AC charge power validation - too low."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Try to set power below 0%
        with pytest.raises(ValueError, match="power_percent must be between 0 and 100"):
            await inverter.set_ac_charge(enabled=True, power_percent=-5)

    @pytest.mark.asyncio
    async def test_set_ac_charge_power_validation_too_high(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test AC charge power validation - too high."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Try to set power above 100%
        with pytest.raises(ValueError, match="power_percent must be between 0 and 100"):
            await inverter.set_ac_charge(enabled=True, power_percent=105)

    @pytest.mark.asyncio
    async def test_set_ac_charge_soc_validation_too_low(self, mock_client: LuxpowerClient) -> None:
        """Test AC charge SOC validation - too low."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Try to set SOC below 0%
        with pytest.raises(ValueError, match="soc_limit must be between 0 and 100"):
            await inverter.set_ac_charge(enabled=True, soc_limit=-5)

    @pytest.mark.asyncio
    async def test_set_ac_charge_soc_validation_too_high(self, mock_client: LuxpowerClient) -> None:
        """Test AC charge SOC validation - too high."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Try to set SOC above 100%
        with pytest.raises(ValueError, match="soc_limit must be between 0 and 100"):
            await inverter.set_ac_charge(enabled=True, soc_limit=105)


class TestEPSOperations:
    """Test EPS (backup) mode operations."""

    @pytest.mark.asyncio
    async def test_set_eps_enabled(self, mock_client: LuxpowerClient) -> None:
        """Test enabling EPS mode."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Mock read response - EPS currently disabled
        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_21": 0}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        # Mock write response
        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        # Enable EPS
        result = await inverter.set_eps_enabled(True)

        # Verify write call - bit 0 should be set (1)
        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {21: 1})

        assert result is True

    @pytest.mark.asyncio
    async def test_set_eps_disabled(self, mock_client: LuxpowerClient) -> None:
        """Test disabling EPS mode."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Mock read response - EPS currently enabled
        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_21": 1}  # Bit 0 set
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        # Mock write response
        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        # Disable EPS
        result = await inverter.set_eps_enabled(False)

        # Verify write call - bit 0 should be cleared (0)
        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {21: 0})

        assert result is True


class TestForcedChargeDischargeOperations:
    """Test forced charge/discharge operations."""

    @pytest.mark.asyncio
    async def test_set_forced_charge_enable(self, mock_client: LuxpowerClient) -> None:
        """Test enabling forced charge."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Mock read response
        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_21": 0}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        # Mock write response
        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        # Enable forced charge
        result = await inverter.set_forced_charge(True)

        # Verify write call - bit 11 should be set (2048)
        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {21: 2048})

        assert result is True

    @pytest.mark.asyncio
    async def test_set_forced_charge_disable(self, mock_client: LuxpowerClient) -> None:
        """Test disabling forced charge."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Mock read response - forced charge enabled
        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_21": 2048}  # Bit 11 set
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        # Mock write response
        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        # Disable forced charge
        result = await inverter.set_forced_charge(False)

        # Verify write call - bit 11 should be cleared (0)
        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {21: 0})

        assert result is True

    @pytest.mark.asyncio
    async def test_set_forced_discharge_enable(self, mock_client: LuxpowerClient) -> None:
        """Test enabling forced discharge."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Mock read response
        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_21": 0}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        # Mock write response
        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        # Enable forced discharge
        result = await inverter.set_forced_discharge(True)

        # Verify write call - bit 10 should be set (1024)
        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {21: 1024})

        assert result is True

    @pytest.mark.asyncio
    async def test_set_forced_discharge_disable(self, mock_client: LuxpowerClient) -> None:
        """Test disabling forced discharge."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Mock read response - forced discharge enabled
        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_21": 1024}  # Bit 10 set
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        # Mock write response
        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        # Disable forced discharge
        result = await inverter.set_forced_discharge(False)

        # Verify write call - bit 10 should be cleared (0)
        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {21: 0})

        assert result is True


class TestChargeDischargePowerOperations:
    """Test charge/discharge power operations."""

    @pytest.mark.asyncio
    async def test_get_charge_discharge_power(self, mock_client: LuxpowerClient) -> None:
        """Test reading charge/discharge power settings."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Mock parameters read
        mock_response = Mock()
        mock_response.parameters = {
            "HOLD_AC_CHARGE_POWER_CMD": 60,
            "HOLD_DISCHG_POWER_CMD": 80,
        }
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_response)

        # Get power settings
        power = await inverter.get_charge_discharge_power()

        # Verify API call
        mock_client.api.control.read_parameters.assert_called_once_with("1234567890", 66, 9)

        # Verify returned data
        assert power == {"charge_power_percent": 60, "discharge_power_percent": 80}

    @pytest.mark.asyncio
    async def test_set_discharge_power(self, mock_client: LuxpowerClient) -> None:
        """Test setting discharge power limit."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Mock write response
        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        # Set discharge power
        result = await inverter.set_discharge_power(75)

        # Verify write call
        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {74: 75})

        assert result is True

    @pytest.mark.asyncio
    async def test_set_discharge_power_validation_too_low(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test discharge power validation - too low."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Try to set power below 0%
        with pytest.raises(ValueError, match="power_percent must be between 0 and 100"):
            await inverter.set_discharge_power(-5)

    @pytest.mark.asyncio
    async def test_set_discharge_power_validation_too_high(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test discharge power validation - too high."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Try to set power above 100%
        with pytest.raises(ValueError, match="power_percent must be between 0 and 100"):
            await inverter.set_discharge_power(105)
