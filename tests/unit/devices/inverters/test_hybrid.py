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
        assert inverter._runtime is None
        assert inverter._energy is None
        assert inverter._battery_bank is None


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

        # Mock parameters read — impl reads HOLD_AC_CHARGE_POWER_CMD and
        # HOLD_FORCED_CHG_POWER_CMD (register 74)
        mock_response = Mock()
        mock_response.parameters = {
            "HOLD_AC_CHARGE_POWER_CMD": 60,
            "HOLD_FORCED_CHG_POWER_CMD": 80,
        }
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_response)

        # Get power settings
        power = await inverter.get_charge_discharge_power()

        # Verify API call
        mock_client.api.control.read_parameters.assert_called_once_with("1234567890", 66, 9)

        # Verify returned data
        assert power == {"charge_power_percent": 60, "forced_charge_power_percent": 80}

    @pytest.mark.asyncio
    async def test_set_forced_charge_power(self, mock_client: LuxpowerClient) -> None:
        """Test setting forced charge power limit."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Mock write response
        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        # Set forced charge power (register 74 = HOLD_FORCED_CHG_POWER_CMD)
        result = await inverter.set_forced_charge_power(75)

        # Verify write call
        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {74: 75})

        assert result is True

    @pytest.mark.asyncio
    async def test_set_forced_charge_power_validation_too_low(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test forced charge power validation - too low."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="power_percent must be between 0 and 100"):
            await inverter.set_forced_charge_power(-5)

    @pytest.mark.asyncio
    async def test_set_forced_charge_power_validation_too_high(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test forced charge power validation - too high."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="power_percent must be between 0 and 100"):
            await inverter.set_forced_charge_power(105)


class TestACChargeScheduleOperations:
    """Test AC charge time schedule operations."""

    @pytest.mark.asyncio
    async def test_set_ac_charge_schedule_period_0(self, mock_client: LuxpowerClient) -> None:
        """Test setting AC charge schedule period 0."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_ac_charge_schedule(0, 23, 0, 7, 0)

        # Two individual writes (FC06) — inverter rejects FC16 for schedule regs
        assert mock_client.api.control.write_parameters.call_count == 2
        mock_client.api.control.write_parameters.assert_any_call("1234567890", {68: 23})
        mock_client.api.control.write_parameters.assert_any_call("1234567890", {69: 7})
        assert result is True

    @pytest.mark.asyncio
    async def test_set_ac_charge_schedule_period_1(self, mock_client: LuxpowerClient) -> None:
        """Test setting AC charge schedule period 1."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_ac_charge_schedule(1, 12, 30, 14, 45)

        # Reg 70 = pack_time(12, 30) = 12|(30<<8) = 7692
        # Reg 71 = pack_time(14, 45) = 14|(45<<8) = 11534
        assert mock_client.api.control.write_parameters.call_count == 2
        mock_client.api.control.write_parameters.assert_any_call("1234567890", {70: 7692})
        mock_client.api.control.write_parameters.assert_any_call("1234567890", {71: 11534})
        assert result is True

    @pytest.mark.asyncio
    async def test_set_ac_charge_schedule_period_2(self, mock_client: LuxpowerClient) -> None:
        """Test setting AC charge schedule period 2."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_ac_charge_schedule(2, 0, 0, 6, 0)

        # Reg 72 = pack_time(0, 0) = 0, Reg 73 = pack_time(6, 0) = 6
        assert mock_client.api.control.write_parameters.call_count == 2
        mock_client.api.control.write_parameters.assert_any_call("1234567890", {72: 0})
        mock_client.api.control.write_parameters.assert_any_call("1234567890", {73: 6})
        assert result is True

    @pytest.mark.asyncio
    async def test_set_ac_charge_schedule_invalid_period(self, mock_client: LuxpowerClient) -> None:
        """Test invalid period raises ValueError."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="period must be 0, 1, or 2"):
            await inverter.set_ac_charge_schedule(3, 0, 0, 6, 0)

    @pytest.mark.asyncio
    async def test_set_ac_charge_schedule_invalid_hour(self, mock_client: LuxpowerClient) -> None:
        """Test invalid hour raises ValueError via pack_time."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="Hour must be 0-23"):
            await inverter.set_ac_charge_schedule(0, 24, 0, 7, 0)

    @pytest.mark.asyncio
    async def test_get_ac_charge_schedule(self, mock_client: LuxpowerClient) -> None:
        """Test reading AC charge schedule."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Mock read response - reg 68 = pack_time(23, 0) = 23, reg 69 = pack_time(7, 0) = 7
        mock_response = Mock()
        mock_response.parameters = {"reg_68": 23, "reg_69": 7}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_response)

        schedule = await inverter.get_ac_charge_schedule(0)

        mock_client.api.control.read_parameters.assert_called_once_with("1234567890", 68, 2)
        assert schedule == {
            "start_hour": 23,
            "start_minute": 0,
            "end_hour": 7,
            "end_minute": 0,
        }

    @pytest.mark.asyncio
    async def test_get_ac_charge_schedule_with_minutes(self, mock_client: LuxpowerClient) -> None:
        """Test reading AC charge schedule with non-zero minutes."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # pack_time(22, 30) = 22 | (30 << 8) = 7702
        # pack_time(6, 45) = 6 | (45 << 8) = 11526
        mock_response = Mock()
        mock_response.parameters = {"reg_68": 7702, "reg_69": 11526}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_response)

        schedule = await inverter.get_ac_charge_schedule(0)

        assert schedule == {
            "start_hour": 22,
            "start_minute": 30,
            "end_hour": 6,
            "end_minute": 45,
        }

    @pytest.mark.asyncio
    async def test_get_ac_charge_schedule_invalid_period(self, mock_client: LuxpowerClient) -> None:
        """Test invalid period on get raises ValueError."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="period must be 0, 1, or 2"):
            await inverter.get_ac_charge_schedule(3)


class TestACChargeTypeOperations:
    """Test AC charge type (Time / SOC-Volt / Time+SOC-Volt) operations."""

    @pytest.mark.asyncio
    async def test_get_ac_charge_type_time(self, mock_client: LuxpowerClient) -> None:
        """Test reading AC charge type when set to Time."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_response = Mock()
        mock_response.parameters = {"reg_120": 0}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_response)

        result = await inverter.get_ac_charge_type()

        mock_client.api.control.read_parameters.assert_called_once_with("1234567890", 120, 1)
        assert result == 0

    @pytest.mark.asyncio
    async def test_get_ac_charge_type_soc_volt(self, mock_client: LuxpowerClient) -> None:
        """Test reading AC charge type when set to SOC/Volt."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_response = Mock()
        mock_response.parameters = {"reg_120": 2}  # Bits 1-2 = 01
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_response)

        result = await inverter.get_ac_charge_type()
        assert result == 1

    @pytest.mark.asyncio
    async def test_get_ac_charge_type_time_soc_volt(self, mock_client: LuxpowerClient) -> None:
        """Test reading AC charge type when set to Time+SOC/Volt."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_response = Mock()
        mock_response.parameters = {"reg_120": 4}  # Bits 1-2 = 10
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_response)

        result = await inverter.get_ac_charge_type()
        assert result == 2

    @pytest.mark.asyncio
    async def test_get_ac_charge_type_preserves_other_bits(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test reading AC charge type ignores other bits in register 120."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Bit 0 and bit 4 set, plus SOC/Volt (bit 1) = 0b00010011 = 19
        mock_response = Mock()
        mock_response.parameters = {"reg_120": 19}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_response)

        result = await inverter.get_ac_charge_type()
        assert result == 1  # Only bits 1-3 extracted

    @pytest.mark.asyncio
    async def test_set_ac_charge_type_time(self, mock_client: LuxpowerClient) -> None:
        """Test setting AC charge type to Time."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_120": 2}  # Currently SOC/Volt
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_ac_charge_type(0)

        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {120: 0})
        assert result is True

    @pytest.mark.asyncio
    async def test_set_ac_charge_type_soc_volt(self, mock_client: LuxpowerClient) -> None:
        """Test setting AC charge type to SOC/Volt."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_120": 0}  # Currently Time
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_ac_charge_type(1)

        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {120: 2})
        assert result is True

    @pytest.mark.asyncio
    async def test_set_ac_charge_type_time_soc_volt(self, mock_client: LuxpowerClient) -> None:
        """Test setting AC charge type to Time+SOC/Volt."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_120": 0}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_ac_charge_type(2)

        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {120: 4})
        assert result is True

    @pytest.mark.asyncio
    async def test_set_ac_charge_type_preserves_other_bits(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test setting AC charge type preserves other bits in register 120."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Bit 0 and bit 4 set (other features enabled) = 0b00010001 = 17
        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_120": 17}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_ac_charge_type(1)  # SOC/Volt

        # Should set bits 1-2 to 01 (value 2) while preserving bits 0 and 4
        # 17 & ~0x06 = 17 & 0xFFF9 = 17 (bits 1-2 were 0) | 2 = 19
        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {120: 19})
        assert result is True

    @pytest.mark.asyncio
    async def test_set_ac_charge_type_invalid_value(self, mock_client: LuxpowerClient) -> None:
        """Test invalid charge type raises ValueError."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="charge_type must be 0, 1, or 2"):
            await inverter.set_ac_charge_type(3)

    @pytest.mark.asyncio
    async def test_set_ac_charge_type_invalid_negative(self, mock_client: LuxpowerClient) -> None:
        """Test negative charge type raises ValueError."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="charge_type must be 0, 1, or 2"):
            await inverter.set_ac_charge_type(-1)


class TestACChargeSocLimitOperations:
    """Test AC charge SOC threshold operations."""

    @pytest.mark.asyncio
    async def test_get_ac_charge_soc_limits(self, mock_client: LuxpowerClient) -> None:
        """Test reading AC charge SOC limits."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Start SOC from reg 160, End SOC from reg 67
        mock_start_response = Mock()
        mock_start_response.parameters = {"reg_160": 20}
        mock_end_response = Mock()
        mock_end_response.parameters = {"reg_67": 100}
        mock_client.api.control.read_parameters = AsyncMock(
            side_effect=[mock_start_response, mock_end_response]
        )

        result = await inverter.get_ac_charge_soc_limits()

        assert mock_client.api.control.read_parameters.call_count == 2
        mock_client.api.control.read_parameters.assert_any_call("1234567890", 160, 1)
        mock_client.api.control.read_parameters.assert_any_call("1234567890", 67, 1)
        assert result == {"start_soc": 20, "end_soc": 100}

    @pytest.mark.asyncio
    async def test_get_ac_charge_soc_limits_defaults(self, mock_client: LuxpowerClient) -> None:
        """Test reading AC charge SOC limits returns 0 for missing keys."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_response = Mock()
        mock_response.parameters = {}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_response)

        result = await inverter.get_ac_charge_soc_limits()
        assert result == {"start_soc": 0, "end_soc": 0}

    @pytest.mark.asyncio
    async def test_set_ac_charge_soc_limits(self, mock_client: LuxpowerClient) -> None:
        """Test setting AC charge SOC limits (start=reg 160, end=reg 67)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_ac_charge_soc_limits(start_soc=20, end_soc=100)

        mock_client.api.control.write_parameters.assert_called_once_with(
            "1234567890", {160: 20, 67: 100}
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_set_ac_charge_soc_limits_start_too_high(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test start_soc > 90 raises ValueError."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="start_soc must be 0-90"):
            await inverter.set_ac_charge_soc_limits(start_soc=91, end_soc=100)

    @pytest.mark.asyncio
    async def test_set_ac_charge_soc_limits_start_negative(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test start_soc < 0 raises ValueError."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="start_soc must be 0-90"):
            await inverter.set_ac_charge_soc_limits(start_soc=-1, end_soc=100)

    @pytest.mark.asyncio
    async def test_set_ac_charge_soc_limits_end_negative(self, mock_client: LuxpowerClient) -> None:
        """Test end_soc < 0 raises ValueError."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="end_soc must be 0-100"):
            await inverter.set_ac_charge_soc_limits(start_soc=10, end_soc=-1)

    @pytest.mark.asyncio
    async def test_set_ac_charge_soc_limits_end_too_high(self, mock_client: LuxpowerClient) -> None:
        """Test end_soc > 100 raises ValueError."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="end_soc must be 0-100"):
            await inverter.set_ac_charge_soc_limits(start_soc=10, end_soc=101)


class TestACChargeVoltageLimitOperations:
    """Test AC charge voltage threshold operations."""

    @pytest.mark.asyncio
    async def test_get_ac_charge_voltage_limits(self, mock_client: LuxpowerClient) -> None:
        """Test reading AC charge voltage limits."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Raw register values: 400 = 40V, 580 = 58V
        mock_response = Mock()
        mock_response.parameters = {"reg_158": 400, "reg_159": 580}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_response)

        result = await inverter.get_ac_charge_voltage_limits()

        mock_client.api.control.read_parameters.assert_called_once_with("1234567890", 158, 2)
        assert result == {"start_voltage": 40, "end_voltage": 58}

    @pytest.mark.asyncio
    async def test_get_ac_charge_voltage_limits_defaults(self, mock_client: LuxpowerClient) -> None:
        """Test reading AC charge voltage limits returns 0 for missing keys."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_response = Mock()
        mock_response.parameters = {}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_response)

        result = await inverter.get_ac_charge_voltage_limits()
        assert result == {"start_voltage": 0, "end_voltage": 0}

    @pytest.mark.asyncio
    async def test_set_ac_charge_voltage_limits(self, mock_client: LuxpowerClient) -> None:
        """Test setting AC charge voltage limits."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_ac_charge_voltage_limits(start_voltage=40, end_voltage=58)

        # 40 * 10 = 400, 58 * 10 = 580
        mock_client.api.control.write_parameters.assert_called_once_with(
            "1234567890", {158: 400, 159: 580}
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_set_ac_charge_voltage_limits_rejects_fractional(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test fractional volts are rejected."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="start_voltage must be a whole number"):
            await inverter.set_ac_charge_voltage_limits(start_voltage=40.5, end_voltage=58)

    @pytest.mark.asyncio
    async def test_set_ac_charge_voltage_limits_rejects_fractional_end(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test fractional end volts are rejected."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="end_voltage must be a whole number"):
            await inverter.set_ac_charge_voltage_limits(start_voltage=40, end_voltage=58.5)

    @pytest.mark.asyncio
    async def test_set_ac_charge_voltage_limits_start_too_low(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test start_voltage < 39 raises ValueError."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="start_voltage must be 39-52V"):
            await inverter.set_ac_charge_voltage_limits(start_voltage=38, end_voltage=58)

    @pytest.mark.asyncio
    async def test_set_ac_charge_voltage_limits_start_too_high(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test start_voltage > 52 raises ValueError."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="start_voltage must be 39-52V"):
            await inverter.set_ac_charge_voltage_limits(start_voltage=53, end_voltage=58)

    @pytest.mark.asyncio
    async def test_set_ac_charge_voltage_limits_end_too_low(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test end_voltage < 48 raises ValueError."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="end_voltage must be 48-59V"):
            await inverter.set_ac_charge_voltage_limits(start_voltage=40, end_voltage=47)

    @pytest.mark.asyncio
    async def test_set_ac_charge_voltage_limits_end_too_high(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test end_voltage > 59 raises ValueError."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="end_voltage must be 48-59V"):
            await inverter.set_ac_charge_voltage_limits(start_voltage=40, end_voltage=60)


class TestSporadicChargeOperations:
    """Test sporadic charge operations (register 233, bit 12)."""

    @pytest.mark.asyncio
    async def test_get_sporadic_charge_enabled(self, mock_client: LuxpowerClient) -> None:
        """Test reading sporadic charge when enabled (bit 12 set)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_response = Mock()
        mock_response.parameters = {"reg_233": 4096}  # Bit 12 = 4096
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_response)

        result = await inverter.get_sporadic_charge()

        mock_client.api.control.read_parameters.assert_called_once_with("1234567890", 233, 1)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_sporadic_charge_disabled(self, mock_client: LuxpowerClient) -> None:
        """Test reading sporadic charge when disabled (bit 12 clear)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_response = Mock()
        mock_response.parameters = {"reg_233": 0}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_response)

        result = await inverter.get_sporadic_charge()

        assert result is False

    @pytest.mark.asyncio
    async def test_set_sporadic_charge_enable(self, mock_client: LuxpowerClient) -> None:
        """Test enabling sporadic charge sets bit 12."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_233": 0}  # Currently disabled
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_sporadic_charge(True)

        # Bit 12 = 4096
        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {233: 4096})
        assert result is True

    @pytest.mark.asyncio
    async def test_set_sporadic_charge_disable(self, mock_client: LuxpowerClient) -> None:
        """Test disabling sporadic charge clears bit 12."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_233": 4096}  # Currently enabled
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_sporadic_charge(False)

        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {233: 0})
        assert result is True

    @pytest.mark.asyncio
    async def test_set_sporadic_charge_preserves_other_bits(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test set_sporadic_charge preserves other bits in register 233."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Bit 1 (battery backup) set = 2
        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_233": 2}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_sporadic_charge(True)

        # Should set bit 12 (4096) while preserving bit 1 (2) = 4098
        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {233: 4098})
        assert result is True

    @pytest.mark.asyncio
    async def test_set_sporadic_charge_disable_preserves_other_bits(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test disabling sporadic charge preserves other bits in register 233."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Bit 1 (battery backup) + bit 12 (sporadic charge) = 2 + 4096 = 4098
        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_233": 4098}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_sporadic_charge(False)

        # Should clear bit 12 while preserving bit 1 (2)
        mock_client.api.control.write_parameters.assert_called_once_with("1234567890", {233: 2})
        assert result is True
