"""Unit tests for HybridInverter class."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import BatteryControlMode, LuxpowerClient
from pylxpweb.devices.inverters.hybrid import HybridInverter
from pylxpweb.exceptions import LuxpowerDeviceError


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
        with pytest.raises(ValueError, match="soc_limit must be between 0 and 101"):
            await inverter.set_ac_charge(enabled=True, soc_limit=-5)

    @pytest.mark.asyncio
    async def test_set_ac_charge_soc_validation_too_high(self, mock_client: LuxpowerClient) -> None:
        """Test AC charge SOC validation - too high (102 is past the 101 cap)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        # Try to set SOC above 101%
        with pytest.raises(ValueError, match="soc_limit must be between 0 and 101"):
            await inverter.set_ac_charge(enabled=True, soc_limit=102)

    @pytest.mark.asyncio
    async def test_set_ac_charge_soc_101_accepted(self, mock_client: LuxpowerClient) -> None:
        """101% AC charge SOC limit is accepted (never-stop / cell-balancing).

        GH eg4_web_monitor#158: the inverter accepts 101 (= never stop AC
        charging, since SOC cannot reach 101). It must write reg 67 = 101,
        not raise.
        """
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_read_response = Mock()
        mock_read_response.parameters = {"reg_21": 0}
        mock_client.api.control.read_parameters = AsyncMock(return_value=mock_read_response)

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_ac_charge(enabled=True, soc_limit=101)

        mock_client.api.control.write_parameters.assert_called_once_with(
            "1234567890", {21: 128, 67: 101}
        )
        assert result is True


class TestEPSOperations:
    """Test EPS (backup) mode operations.

    In CLOUD mode these route through the atomic ``control_function`` API
    (server-side bit update preserving other bits), not a client-side
    read-modify-write. In TRANSPORT mode they do an on-device RMW.
    """

    @pytest.mark.asyncio
    async def test_set_eps_enabled_cloud(self, mock_client: LuxpowerClient) -> None:
        """Enabling EPS in cloud mode uses control_function(FUNC_EPS_EN, True)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        mock_client.api.control.control_function = AsyncMock(return_value=_cloud_success())

        result = await inverter.set_eps_enabled(True)

        mock_client.api.control.control_function.assert_awaited_once_with(
            "1234567890", "FUNC_EPS_EN", True
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_set_eps_disabled_cloud(self, mock_client: LuxpowerClient) -> None:
        """Disabling EPS in cloud mode uses control_function(FUNC_EPS_EN, False)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        mock_client.api.control.control_function = AsyncMock(return_value=_cloud_success())

        result = await inverter.set_eps_enabled(False)

        mock_client.api.control.control_function.assert_awaited_once_with(
            "1234567890", "FUNC_EPS_EN", False
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_set_eps_enabled_transport_preserves_bits(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Transport mode RMW sets bit 0 while preserving other reg-21 bits."""
        inverter = HybridInverter(
            client=mock_client,
            serial_number="1234567890",
            model="FlexBOSS21",
            transport=Mock(),
        )
        inverter.read_transport_register = AsyncMock(return_value=2048)  # bit 11 set
        inverter.write_transport_register = AsyncMock(return_value=True)

        result = await inverter.set_eps_enabled(True)

        inverter.read_transport_register.assert_awaited_once_with(21)
        inverter.write_transport_register.assert_awaited_once_with(21, 2049)  # 2048|1
        assert result is True


class TestForcedChargeDischargeOperations:
    """Test forced charge/discharge operations (cloud control_function path)."""

    @pytest.mark.asyncio
    async def test_set_forced_charge_enable(self, mock_client: LuxpowerClient) -> None:
        """Enable forced charge → control_function(FUNC_FORCED_CHG_EN, True)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        mock_client.api.control.control_function = AsyncMock(return_value=_cloud_success())

        result = await inverter.set_forced_charge(True)

        mock_client.api.control.control_function.assert_awaited_once_with(
            "1234567890", "FUNC_FORCED_CHG_EN", True
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_set_forced_charge_disable(self, mock_client: LuxpowerClient) -> None:
        """Disable forced charge → control_function(FUNC_FORCED_CHG_EN, False)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        mock_client.api.control.control_function = AsyncMock(return_value=_cloud_success())

        result = await inverter.set_forced_charge(False)

        mock_client.api.control.control_function.assert_awaited_once_with(
            "1234567890", "FUNC_FORCED_CHG_EN", False
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_set_forced_discharge_enable(self, mock_client: LuxpowerClient) -> None:
        """Enable forced discharge → control_function(FUNC_FORCED_DISCHG_EN, True)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        mock_client.api.control.control_function = AsyncMock(return_value=_cloud_success())

        result = await inverter.set_forced_discharge(True)

        mock_client.api.control.control_function.assert_awaited_once_with(
            "1234567890", "FUNC_FORCED_DISCHG_EN", True
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_set_forced_discharge_disable(self, mock_client: LuxpowerClient) -> None:
        """Disable forced discharge → control_function(FUNC_FORCED_DISCHG_EN, False)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        mock_client.api.control.control_function = AsyncMock(return_value=_cloud_success())

        result = await inverter.set_forced_discharge(False)

        mock_client.api.control.control_function.assert_awaited_once_with(
            "1234567890", "FUNC_FORCED_DISCHG_EN", False
        )
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

        with pytest.raises(ValueError, match="power_100w must be between 0 and 150"):
            await inverter.set_forced_charge_power(-5)

    @pytest.mark.asyncio
    async def test_set_forced_charge_power_validation_too_high(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test forced charge power validation - too high (>150 = >15kW)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="power_100w must be between 0 and 150"):
            await inverter.set_forced_charge_power(151)


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

        with pytest.raises(ValueError, match="end_soc must be 0-101"):
            await inverter.set_ac_charge_soc_limits(start_soc=10, end_soc=-1)

    @pytest.mark.asyncio
    async def test_set_ac_charge_soc_limits_end_too_high(self, mock_client: LuxpowerClient) -> None:
        """Test end_soc > 101 raises ValueError (102 is past the cap)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="end_soc must be 0-101"):
            await inverter.set_ac_charge_soc_limits(start_soc=10, end_soc=102)

    @pytest.mark.asyncio
    async def test_set_ac_charge_soc_limits_end_101_accepted(
        self, mock_client: LuxpowerClient
    ) -> None:
        """end_soc=101 is accepted and writes reg 67 = 101 (GH eg4_web_monitor#158).

        101 = never stop AC charging (cell balancing); only the stop SOC (reg 67)
        is widened, the start SOC stays 0-90.
        """
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameters = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_ac_charge_soc_limits(start_soc=20, end_soc=101)

        # reg 67 = HOLD_AC_CHARGE_SOC_LIMIT (end), reg 160 = start
        mock_client.api.control.write_parameters.assert_called_once_with(
            "1234567890", {160: 20, 67: 101}
        )
        assert result is True


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
    async def test_set_sporadic_charge_enable_cloud(self, mock_client: LuxpowerClient) -> None:
        """Cloud enable → control_function(FUNC_SPORADIC_CHARGE, True)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        mock_client.api.control.control_function = AsyncMock(return_value=_cloud_success())

        result = await inverter.set_sporadic_charge(True)

        mock_client.api.control.control_function.assert_awaited_once_with(
            "1234567890", "FUNC_SPORADIC_CHARGE", True
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_set_sporadic_charge_disable_cloud(self, mock_client: LuxpowerClient) -> None:
        """Cloud disable → control_function(FUNC_SPORADIC_CHARGE, False)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        mock_client.api.control.control_function = AsyncMock(return_value=_cloud_success())

        result = await inverter.set_sporadic_charge(False)

        mock_client.api.control.control_function.assert_awaited_once_with(
            "1234567890", "FUNC_SPORADIC_CHARGE", False
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_set_sporadic_charge_transport_preserves_other_bits(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Transport RMW sets bit 12 while preserving other reg-233 bits."""
        inverter = HybridInverter(
            client=mock_client,
            serial_number="1234567890",
            model="FlexBOSS21",
            transport=Mock(),
        )
        # Bit 1 (battery backup) set = 2
        inverter.read_transport_register = AsyncMock(return_value=2)
        inverter.write_transport_register = AsyncMock(return_value=True)

        result = await inverter.set_sporadic_charge(True)

        # Set bit 12 (4096) while preserving bit 1 (2) = 4098
        inverter.write_transport_register.assert_awaited_once_with(233, 4098)
        assert result is True

    @pytest.mark.asyncio
    async def test_set_sporadic_charge_transport_disable_preserves_other_bits(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Transport RMW clears bit 12 while preserving other reg-233 bits."""
        inverter = HybridInverter(
            client=mock_client,
            serial_number="1234567890",
            model="FlexBOSS21",
            transport=Mock(),
        )
        # Bit 1 (2) + bit 12 (4096) = 4098
        inverter.read_transport_register = AsyncMock(return_value=4098)
        inverter.write_transport_register = AsyncMock(return_value=True)

        result = await inverter.set_sporadic_charge(False)

        # Clear bit 12 while preserving bit 1 (2)
        inverter.write_transport_register.assert_awaited_once_with(233, 2)
        assert result is True


def _cloud_read_response(**parameters: object) -> Mock:
    """Build a mock cloud ParameterReadResponse exposing ``.parameters``."""
    response = Mock()
    response.parameters = dict(parameters)
    return response


def _cloud_success(success: bool = True) -> Mock:
    """Build a mock cloud SuccessResponse exposing ``.success``."""
    response = Mock()
    response.success = success
    return response


class TestModbusOnlyChargeDischargeOperations:
    """Charge/discharge convenience operations over the TRANSPORT (Modbus) path.

    These now go through the dual-path helpers, so the inverter is constructed
    with a transport sentinel to exercise the transport branch.
    """

    def _inverter(self, client: LuxpowerClient) -> HybridInverter:
        return HybridInverter(
            client=client,
            serial_number="1234567890",
            model="FlexBOSS21",
            transport=Mock(),  # non-None → dual-path helpers take the transport branch
        )

    @pytest.mark.asyncio
    async def test_get_off_grid_cutoff_voltage(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        inverter.read_transport_register = AsyncMock(return_value=415)

        result = await inverter.get_off_grid_cutoff_voltage()

        inverter.read_transport_register.assert_awaited_once_with(100)
        assert result == 41.5

    @pytest.mark.asyncio
    async def test_set_off_grid_cutoff_voltage(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        inverter.write_transport_register = AsyncMock(return_value=True)

        result = await inverter.set_off_grid_cutoff_voltage(42.0)

        inverter.write_transport_register.assert_awaited_once_with(100, 420)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_charge_last_enabled(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        inverter.read_transport_register = AsyncMock(return_value=16)  # bit 4

        result = await inverter.get_charge_last()

        inverter.read_transport_register.assert_awaited_once_with(110)
        assert result is True

    @pytest.mark.asyncio
    async def test_set_charge_last_preserves_other_bits(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        inverter.read_transport_register = AsyncMock(return_value=3)
        inverter.write_transport_register = AsyncMock(return_value=True)

        result = await inverter.set_charge_last(True)

        inverter.read_transport_register.assert_awaited_once_with(110)
        inverter.write_transport_register.assert_awaited_once_with(110, 19)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_battery_charge_control_voltage_mode(
        self, mock_client: LuxpowerClient
    ) -> None:
        inverter = self._inverter(mock_client)
        inverter.read_transport_register = AsyncMock(return_value=512)  # bit 9

        result = await inverter.get_battery_charge_control()

        inverter.read_transport_register.assert_awaited_once_with(179)
        assert result is True

    @pytest.mark.asyncio
    async def test_set_battery_discharge_control_preserves_charge_bit(
        self, mock_client: LuxpowerClient
    ) -> None:
        inverter = self._inverter(mock_client)
        inverter.read_transport_register = AsyncMock(return_value=512)
        inverter.write_transport_register = AsyncMock(return_value=True)

        result = await inverter.set_battery_discharge_control(voltage_mode=True)

        inverter.read_transport_register.assert_awaited_once_with(179)
        inverter.write_transport_register.assert_awaited_once_with(179, 1536)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_charge_current_limit(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        inverter.read_transport_register = AsyncMock(return_value=249)

        result = await inverter.get_charge_current_limit()

        inverter.read_transport_register.assert_awaited_once_with(101)
        assert result == 249

    @pytest.mark.asyncio
    async def test_set_discharge_current_limit(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        inverter.write_transport_register = AsyncMock(return_value=True)

        result = await inverter.set_discharge_current_limit(140)

        inverter.write_transport_register.assert_awaited_once_with(102, 140)
        assert result is True

    @pytest.mark.asyncio
    async def test_set_charge_current_limit_rejects_negative(
        self, mock_client: LuxpowerClient
    ) -> None:
        inverter = self._inverter(mock_client)

        with pytest.raises(ValueError, match="current_amps must be non-negative"):
            await inverter.set_charge_current_limit(-1)

    @pytest.mark.asyncio
    async def test_get_system_charge_soc_limit(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        inverter.read_transport_register = AsyncMock(return_value=98)

        result = await inverter.get_system_charge_soc_limit()

        inverter.read_transport_register.assert_awaited_once_with(227)
        assert result == 98

    @pytest.mark.asyncio
    async def test_set_system_charge_soc_limit_allows_101(
        self, mock_client: LuxpowerClient
    ) -> None:
        inverter = self._inverter(mock_client)
        inverter.write_transport_register = AsyncMock(return_value=True)

        result = await inverter.set_system_charge_soc_limit(101)

        inverter.write_transport_register.assert_awaited_once_with(227, 101)
        assert result is True

    @pytest.mark.asyncio
    async def test_set_system_charge_soc_limit_rejects_out_of_range(
        self, mock_client: LuxpowerClient
    ) -> None:
        inverter = self._inverter(mock_client)

        with pytest.raises(ValueError, match="soc_percent must be 0-101"):
            await inverter.set_system_charge_soc_limit(102)

        with pytest.raises(ValueError, match="soc_percent must be 0-101"):
            await inverter.set_system_charge_soc_limit(-1)

    @pytest.mark.asyncio
    async def test_get_system_charge_volt_limit(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        inverter.read_transport_register = AsyncMock(return_value=580)

        result = await inverter.get_system_charge_volt_limit()

        inverter.read_transport_register.assert_awaited_once_with(228)
        assert result == 58.0

    @pytest.mark.asyncio
    async def test_set_system_charge_volt_limit_rejects_zero(
        self, mock_client: LuxpowerClient
    ) -> None:
        inverter = self._inverter(mock_client)

        with pytest.raises(ValueError, match="voltage must be positive"):
            await inverter.set_system_charge_volt_limit(0)

    @pytest.mark.asyncio
    async def test_get_on_grid_cutoff_soc(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        inverter.read_transport_register = AsyncMock(return_value=20)

        result = await inverter.get_on_grid_cutoff_soc()

        inverter.read_transport_register.assert_awaited_once_with(105)
        assert result == 20

    @pytest.mark.asyncio
    async def test_set_off_grid_cutoff_soc(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        inverter.write_transport_register = AsyncMock(return_value=True)

        result = await inverter.set_off_grid_cutoff_soc(20)

        inverter.write_transport_register.assert_awaited_once_with(125, 20)
        assert result is True

    @pytest.mark.asyncio
    async def test_set_on_grid_cutoff_soc_rejects_out_of_range(
        self, mock_client: LuxpowerClient
    ) -> None:
        inverter = self._inverter(mock_client)

        with pytest.raises(ValueError, match="soc_percent must be 10-90"):
            await inverter.set_on_grid_cutoff_soc(9)

        with pytest.raises(ValueError, match="soc_percent must be 10-90"):
            await inverter.set_on_grid_cutoff_soc(91)

    @pytest.mark.asyncio
    async def test_get_on_grid_cutoff_voltage(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        inverter.read_transport_register = AsyncMock(return_value=400)

        result = await inverter.get_on_grid_cutoff_voltage()

        inverter.read_transport_register.assert_awaited_once_with(169)
        assert result == 40.0

    @pytest.mark.asyncio
    async def test_set_on_grid_cutoff_voltage(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        inverter.write_transport_register = AsyncMock(return_value=True)

        result = await inverter.set_on_grid_cutoff_voltage(42.0)

        inverter.write_transport_register.assert_awaited_once_with(169, 420)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_start_discharge_power(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        inverter.read_transport_register = AsyncMock(return_value=100)

        result = await inverter.get_start_discharge_power()

        inverter.read_transport_register.assert_awaited_once_with(116)
        assert result == 100

    @pytest.mark.asyncio
    async def test_set_start_discharge_power_rejects_negative(
        self, mock_client: LuxpowerClient
    ) -> None:
        inverter = self._inverter(mock_client)

        with pytest.raises(ValueError, match="watts must be non-negative"):
            await inverter.set_start_discharge_power(-1)

    @pytest.mark.asyncio
    async def test_no_transport_no_client_raises(self, mock_client: LuxpowerClient) -> None:
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        inverter._transport = None
        inverter._client = None  # type: ignore[assignment]

        with pytest.raises(LuxpowerDeviceError, match="requires a transport or a cloud client"):
            await inverter.get_off_grid_cutoff_voltage()
        with pytest.raises(LuxpowerDeviceError, match="requires a transport or a cloud client"):
            await inverter.set_off_grid_cutoff_voltage(42.0)


class TestCloudChargeDischargeOperations:
    """Charge/discharge convenience operations over the CLOUD (HTTP) path.

    With no transport, the dual-path helpers route through the control endpoint:
    value reads via ``read_parameters``, value writes via ``write_parameters``
    (raw register dict), and bit writes via the atomic ``control_function`` API.
    """

    def _inverter(self, mock_client: LuxpowerClient) -> HybridInverter:
        # No transport → cloud branch. mock_client.api.control is a Mock.
        return HybridInverter(client=mock_client, serial_number="1234567890", model="FlexBOSS21")

    @pytest.mark.asyncio
    async def test_cloud_get_off_grid_cutoff_voltage(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        # Cloud returns the already-scaled value in volts (DIV_10 register 100).
        mock_client.api.control.read_parameters = AsyncMock(
            return_value=_cloud_read_response(HOLD_LEAD_ACID_DISCHARGE_CUT_OFF_VOLT=41.5)
        )

        result = await inverter.get_off_grid_cutoff_voltage()

        mock_client.api.control.read_parameters.assert_awaited_once_with("1234567890", 100, 1)
        assert result == 41.5

    @pytest.mark.asyncio
    async def test_cloud_set_off_grid_cutoff_voltage_writes_raw_register(
        self, mock_client: LuxpowerClient
    ) -> None:
        inverter = self._inverter(mock_client)
        mock_client.api.control.write_parameters = AsyncMock(return_value=_cloud_success())

        result = await inverter.set_off_grid_cutoff_voltage(42.0)

        mock_client.api.control.write_parameters.assert_awaited_once_with("1234567890", {100: 420})
        assert result is True

    @pytest.mark.asyncio
    async def test_cloud_get_battery_charge_control(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        mock_client.api.control.read_parameters = AsyncMock(
            return_value=_cloud_read_response(FUNC_BAT_CHARGE_CONTROL=True)
        )

        result = await inverter.get_battery_charge_control()

        mock_client.api.control.read_parameters.assert_awaited_once_with("1234567890", 179, 1)
        assert result is True

    @pytest.mark.asyncio
    async def test_cloud_set_battery_charge_control_uses_function_control(
        self, mock_client: LuxpowerClient
    ) -> None:
        inverter = self._inverter(mock_client)
        mock_client.api.control.control_function = AsyncMock(return_value=_cloud_success())

        result = await inverter.set_battery_charge_control(voltage_mode=True)

        # Atomic server-side bit update preserves the other reg-179 bits.
        mock_client.api.control.control_function.assert_awaited_once_with(
            "1234567890", "FUNC_BAT_CHARGE_CONTROL", True
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_cloud_set_battery_discharge_control_uses_function_control(
        self, mock_client: LuxpowerClient
    ) -> None:
        inverter = self._inverter(mock_client)
        mock_client.api.control.control_function = AsyncMock(return_value=_cloud_success())

        result = await inverter.set_battery_discharge_control(voltage_mode=False)

        mock_client.api.control.control_function.assert_awaited_once_with(
            "1234567890", "FUNC_BAT_DISCHARGE_CONTROL", False
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_cloud_get_system_charge_volt_limit(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        # Cloud returns the already-scaled value in volts (DIV_10 register 228).
        mock_client.api.control.read_parameters = AsyncMock(
            return_value=_cloud_read_response(HOLD_SYSTEM_CHARGE_VOLT_LIMIT=58.0)
        )

        result = await inverter.get_system_charge_volt_limit()

        mock_client.api.control.read_parameters.assert_awaited_once_with("1234567890", 228, 1)
        assert result == 58.0

    @pytest.mark.asyncio
    async def test_cloud_get_volt_limit_float_string(self, mock_client: LuxpowerClient) -> None:
        # Cloud may return a fractional value as a string ("59.5"); must not crash
        # and must round-trip through the raw reconstruction back to 59.5 V.
        inverter = self._inverter(mock_client)
        mock_client.api.control.read_parameters = AsyncMock(
            return_value=_cloud_read_response(HOLD_SYSTEM_CHARGE_VOLT_LIMIT="59.5")
        )

        result = await inverter.get_system_charge_volt_limit()

        assert result == 59.5

    @pytest.mark.asyncio
    async def test_cloud_get_off_grid_cutoff_soc_unscaled(
        self, mock_client: LuxpowerClient
    ) -> None:
        # Unscaled register (SOC %, scale NONE): cloud value passes through as-is.
        inverter = self._inverter(mock_client)
        mock_client.api.control.read_parameters = AsyncMock(
            return_value=_cloud_read_response(HOLD_SOC_LOW_LIMIT_EPS_DISCHG=20)
        )

        result = await inverter.get_off_grid_cutoff_soc()

        assert result == 20


class TestBatteryControlModeHelpers:
    """Friendly BatteryControlMode wrappers + derive-from-active-mode accessors."""

    def _inverter(self, mock_client: LuxpowerClient) -> HybridInverter:
        return HybridInverter(
            client=mock_client,
            serial_number="1234567890",
            model="FlexBOSS21",
            transport=Mock(),
        )

    @pytest.mark.asyncio
    async def test_get_charge_control_mode_soc(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        inverter.read_transport_register = AsyncMock(return_value=0)  # bit 9 clear

        assert await inverter.get_battery_charge_control_mode() is BatteryControlMode.SOC

    @pytest.mark.asyncio
    async def test_get_charge_control_mode_voltage(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        inverter.read_transport_register = AsyncMock(return_value=512)  # bit 9 set

        assert await inverter.get_battery_charge_control_mode() is BatteryControlMode.VOLTAGE

    @pytest.mark.asyncio
    async def test_set_discharge_control_mode_voltage(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        inverter.read_transport_register = AsyncMock(return_value=0)
        inverter.write_transport_register = AsyncMock(return_value=True)

        result = await inverter.set_battery_discharge_control_mode(BatteryControlMode.VOLTAGE)

        inverter.write_transport_register.assert_awaited_once_with(179, 1024)  # bit 10
        assert result is True

    @pytest.mark.asyncio
    async def test_active_charge_limit_voltage_mode(self, mock_client: LuxpowerClient) -> None:
        inverter = self._inverter(mock_client)
        # reg 179 read → bit 9 set (Voltage); reg 228 read → 580 (58.0V)
        inverter.read_transport_register = AsyncMock(side_effect=[512, 580])

        result = await inverter.get_active_charge_limit()

        assert result == {"mode": BatteryControlMode.VOLTAGE, "value": 58.0, "unit": "V"}

    @pytest.mark.asyncio
    async def test_active_discharge_cutoff_soc_mode_on_grid(
        self, mock_client: LuxpowerClient
    ) -> None:
        inverter = self._inverter(mock_client)
        # reg 179 read → bit 10 clear (SOC); reg 105 read → 20 (%)
        inverter.read_transport_register = AsyncMock(side_effect=[0, 20])

        result = await inverter.get_active_discharge_cutoff()

        assert result == {"mode": BatteryControlMode.SOC, "value": 20, "unit": "%"}


class TestForcedDischargeOperations:
    """Forced discharge power/SOC controls (regs 82/83, GH #207 / PR #249)."""

    @pytest.mark.asyncio
    async def test_set_forced_discharge_power(self, mock_client: LuxpowerClient) -> None:
        """Setter writes HOLD_FORCED_DISCHG_POWER_CMD as a kW string.

        Fractional kW is real hardware behavior: PR #249 verified panel
        entry 2.5 kW reads back raw 25 (100W units, the reg-74 encoding).
        """
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        inverter._parameters_cache_time = datetime.now()

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameter = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_forced_discharge_power(2.5)

        mock_client.api.control.write_parameter.assert_called_once_with(
            "1234567890", "HOLD_FORCED_DISCHG_POWER_CMD", "2.5"
        )
        assert result is True
        # Successful write invalidates the parameter cache
        assert inverter._parameters_cache_time is None

    @pytest.mark.asyncio
    async def test_set_forced_discharge_power_out_of_range(
        self, mock_client: LuxpowerClient
    ) -> None:
        """kW outside 0.0-25.5 raises ValueError (both directions)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="between 0.0 and 25.5"):
            await inverter.set_forced_discharge_power(25.6)
        with pytest.raises(ValueError, match="between 0.0 and 25.5"):
            await inverter.set_forced_discharge_power(-0.1)

    @pytest.mark.asyncio
    async def test_set_forced_discharge_power_failure_keeps_cache(
        self, mock_client: LuxpowerClient
    ) -> None:
        """A failed write returns False and does NOT invalidate the cache."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        stamp = datetime.now()
        inverter._parameters_cache_time = stamp

        mock_write_response = Mock()
        mock_write_response.success = False
        mock_client.api.control.write_parameter = AsyncMock(return_value=mock_write_response)

        assert await inverter.set_forced_discharge_power(4.0) is False
        assert inverter._parameters_cache_time == stamp

    @pytest.mark.asyncio
    async def test_set_forced_discharge_soc_limit(self, mock_client: LuxpowerClient) -> None:
        """Setter writes HOLD_FORCED_DISCHG_SOC_LIMIT as percent string."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameter = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_forced_discharge_soc_limit(20)

        mock_client.api.control.write_parameter.assert_called_once_with(
            "1234567890", "HOLD_FORCED_DISCHG_SOC_LIMIT", "20"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_set_forced_discharge_soc_limit_out_of_range(
        self, mock_client: LuxpowerClient
    ) -> None:
        """SOC outside 0-100 raises ValueError."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="between 0 and 100"):
            await inverter.set_forced_discharge_soc_limit(101)

    def test_properties_none_before_parameter_load(self, mock_client: LuxpowerClient) -> None:
        """Both getters return None until parameters are loaded."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        assert inverter.parameters is None
        assert inverter.forced_discharge_power is None
        assert inverter.forced_discharge_soc_limit is None

    def test_properties_read_cached_parameters(self, mock_client: LuxpowerClient) -> None:
        """Power getter returns cloud kW as float; SOC getter validates 0-100."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        inverter.parameters = {
            "HOLD_FORCED_DISCHG_POWER_CMD": 2.5,
            "HOLD_FORCED_DISCHG_SOC_LIMIT": 20,
        }

        assert inverter.forced_discharge_power == 2.5
        assert inverter.forced_discharge_soc_limit == 20

    def test_properties_reject_garbage_cache_values(self, mock_client: LuxpowerClient) -> None:
        """Unparseable power and out-of-range SOC read as None, not numbers."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        inverter.parameters = {
            "HOLD_FORCED_DISCHG_POWER_CMD": "garbage",
            "HOLD_FORCED_DISCHG_SOC_LIMIT": 250,
        }

        assert inverter.forced_discharge_power is None
        assert inverter.forced_discharge_soc_limit is None

    def test_register_map_carries_forced_discharge_params(self) -> None:
        """REGISTER_TO_PARAM_KEYS resolves regs 82/83 to the canonical names
        so transport read_named_parameters() populates the param cache."""
        from pylxpweb.constants import REGISTER_TO_PARAM_KEYS

        assert REGISTER_TO_PARAM_KEYS[82] == ["HOLD_FORCED_DISCHG_POWER_CMD"]
        assert REGISTER_TO_PARAM_KEYS[83] == ["HOLD_FORCED_DISCHG_SOC_LIMIT"]

    def test_register_map_names_full_64_to_83_window(self) -> None:
        """Every register in the 64-83 block resolves to an API name that
        matches the canonical holding table — no raw numeric keys can leak
        into parameter caches and no single-value name can drift from
        canonical (codex r1 LOW: leakage; r2 LOW: per-register pinning)."""
        from pylxpweb.constants import REGISTER_TO_PARAM_KEYS
        from pylxpweb.registers.inverter_holding import BY_ADDRESS

        for reg in range(64, 84):
            assert reg in REGISTER_TO_PARAM_KEYS, f"unnamed register {reg}"
            names = REGISTER_TO_PARAM_KEYS[reg]
            if len(names) != 1:
                continue  # bitfield registers are pinned elsewhere
            canonical = BY_ADDRESS.get(reg)
            if not canonical:
                continue  # no canonical definition to compare against
            assert names[0] == canonical[0].api_param_key, (
                f"reg {reg}: map name {names[0]!r} != canonical {canonical[0].api_param_key!r}"
            )


class TestGridSellBackOperations:
    """Grid Sell Back / Export PV Only controls (reg 21 bit 15, reg 103,
    reg-179-family FUNC_PV_SELL_TO_GRID_EN — GH eg4_web_monitor#135)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("inverter_method", "control_method"),
        [
            ("enable_feed_in_grid", "enable_feed_in_grid"),
            ("disable_feed_in_grid", "disable_feed_in_grid"),
        ],
    )
    async def test_toggle_delegates_to_control_endpoint(
        self, mock_client: LuxpowerClient, inverter_method: str, control_method: str
    ) -> None:
        """Device-level toggles delegate to the control endpoint by serial.

        Export PV Only is no longer in this list: HybridInverter overrides
        it with the reg-179 bit-3 dual-path (see TestPVSellToGridDualPath).
        """
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        mock_response = Mock()
        mock_response.success = True
        setattr(mock_client.api.control, control_method, AsyncMock(return_value=mock_response))

        assert await getattr(inverter, inverter_method)() is True
        getattr(mock_client.api.control, control_method).assert_called_once_with("1234567890")

    @pytest.mark.asyncio
    async def test_status_delegates_to_control_endpoint(self, mock_client: LuxpowerClient) -> None:
        """Device-level status getters delegate to the control endpoint."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        mock_client.api.control.get_feed_in_grid_status = AsyncMock(return_value=True)

        assert await inverter.get_feed_in_grid_status() is True
        mock_client.api.control.get_feed_in_grid_status.assert_called_once_with("1234567890")

    @pytest.mark.asyncio
    async def test_set_feed_in_grid_power_percent(self, mock_client: LuxpowerClient) -> None:
        """Setter writes HOLD_FEED_IN_GRID_POWER_PERCENT as a percent string."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        inverter._parameters_cache_time = datetime.now()

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameter = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_feed_in_grid_power_percent(50)

        mock_client.api.control.write_parameter.assert_called_once_with(
            "1234567890", "HOLD_FEED_IN_GRID_POWER_PERCENT", "50"
        )
        assert result is True
        # Successful write invalidates the parameter cache
        assert inverter._parameters_cache_time is None

    @pytest.mark.asyncio
    async def test_set_feed_in_grid_power_percent_out_of_range(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Percent outside 0-100 raises ValueError (both directions)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="between 0 and 100"):
            await inverter.set_feed_in_grid_power_percent(101)
        with pytest.raises(ValueError, match="between 0 and 100"):
            await inverter.set_feed_in_grid_power_percent(-1)

    @pytest.mark.asyncio
    async def test_set_feed_in_grid_power_percent_failure_keeps_cache(
        self, mock_client: LuxpowerClient
    ) -> None:
        """A failed write returns False and does NOT invalidate the cache."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        stamp = datetime.now()
        inverter._parameters_cache_time = stamp

        mock_write_response = Mock()
        mock_write_response.success = False
        mock_client.api.control.write_parameter = AsyncMock(return_value=mock_write_response)

        assert await inverter.set_feed_in_grid_power_percent(40) is False
        assert inverter._parameters_cache_time == stamp

    def test_property_none_before_parameter_load(self, mock_client: LuxpowerClient) -> None:
        """Percent getter returns None until parameters are loaded."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        assert inverter.parameters is None
        assert inverter.feed_in_grid_power_percent is None

    def test_property_reads_cached_parameters(self, mock_client: LuxpowerClient) -> None:
        """Percent getter returns the cached value (whole percent both paths)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        inverter.parameters = {"HOLD_FEED_IN_GRID_POWER_PERCENT": "16"}

        assert inverter.feed_in_grid_power_percent == 16

    def test_property_rejects_garbage_cache_values(self, mock_client: LuxpowerClient) -> None:
        """Unparseable or out-of-range percent reads as None, not a number."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        inverter.parameters = {"HOLD_FEED_IN_GRID_POWER_PERCENT": "garbage"}
        assert inverter.feed_in_grid_power_percent is None

        inverter.parameters = {"HOLD_FEED_IN_GRID_POWER_PERCENT": 250}
        assert inverter.feed_in_grid_power_percent is None

    def test_register_map_carries_feed_in_grid_power_percent(self) -> None:
        """REGISTER_TO_PARAM_KEYS resolves reg 103 to the cloud-pinned name
        (single-register named reads, 18kPV + FlexBOSS21, 2026-06-12) and it
        agrees with the canonical holding table."""
        from pylxpweb.constants import REGISTER_TO_PARAM_KEYS
        from pylxpweb.registers.inverter_holding import BY_ADDRESS

        assert REGISTER_TO_PARAM_KEYS[103] == ["HOLD_FEED_IN_GRID_POWER_PERCENT"]
        canonical = BY_ADDRESS[103]
        assert canonical[0].api_param_key == "HOLD_FEED_IN_GRID_POWER_PERCENT"
        assert canonical[0].min_value == 0
        assert canonical[0].max_value == 100

    def test_pv_sell_to_grid_bit_pinned_at_bit3(self) -> None:
        """FUNC_PV_SELL_TO_GRID_EN is register 179 bit 3.

        Pinned 2026-06-12 ~16:05-16:07 PT via authorized live cloud toggles
        with raw verification (remoteRead (179,1) valueFrame, base64 LE
        uint16) on BOTH 12K-hybrid models: FlexBOSS21 52842P0581 and 18kPV
        4512670118 each toggled raw 0x104c <-> 0x1044 (XOR 0x0008 = single
        bit 3) in lockstep with the named param; restores verified by
        re-read.  The list index in REGISTER_TO_PARAM_KEYS IS the bit
        position, and the FUNC_EXT_BIT constant must agree.
        """
        from pylxpweb.constants import (
            FUNC_EXT_BIT_PV_SELL_TO_GRID,
            FUNC_EXT_REGISTER,
            REGISTER_TO_PARAM_KEYS,
        )

        assert FUNC_EXT_REGISTER == 179
        assert FUNC_EXT_BIT_PV_SELL_TO_GRID == 3
        assert (
            REGISTER_TO_PARAM_KEYS[179].index("FUNC_PV_SELL_TO_GRID_EN")
            == FUNC_EXT_BIT_PV_SELL_TO_GRID
        )

    def test_pv_sell_to_grid_canonical_table_agrees_on_bit3(self) -> None:
        """The canonical holding table's bit-3 entry (spec name
        FUNC_BAT_WAKEUP_EN, "Battery wakeup / PV sell first enable") sits at
        the same (address, bit) the live pin established for the cloud name
        — the two tables must never drift apart on this bit."""
        from pylxpweb.registers.inverter_holding import BY_API_KEY

        canonical = BY_API_KEY["FUNC_BAT_WAKEUP_EN"]
        assert canonical.address == 179
        assert canonical.bit_position == 3


class TestPVSellToGridDualPath:
    """Export PV Only (FUNC_PV_SELL_TO_GRID_EN) — reg 179 bit 3 dual-path.

    Bit pinned 2026-06-12 ~16:05-16:07 PT via authorized live cloud toggles
    raw-verified on BOTH 12K-hybrid models — FlexBOSS21 52842P0581 and
    18kPV 4512670118 each toggled reg-179 raw 0x104c <-> 0x1044 (XOR 0x0008
    = single bit 3), restores verified by re-read.  The transport tests
    below use those exact live frames as vectors.
    """

    def _transport_inverter(self, client: LuxpowerClient) -> HybridInverter:
        return HybridInverter(
            client=client,
            serial_number="52842P0581",
            model="FlexBOSS21",
            transport=Mock(),  # non-None → dual-path helpers take the transport branch
        )

    @pytest.mark.asyncio
    async def test_transport_enable_replays_live_frames(self, mock_client: LuxpowerClient) -> None:
        """Enable over Modbus: RMW 0x1044 -> 0x104c, preserving bits 2/6/12."""
        inverter = self._transport_inverter(mock_client)
        inverter.read_transport_register = AsyncMock(return_value=0x1044)
        inverter.write_transport_register = AsyncMock(return_value=True)

        assert await inverter.enable_pv_sell_to_grid() is True

        inverter.read_transport_register.assert_awaited_once_with(179)
        inverter.write_transport_register.assert_awaited_once_with(179, 0x104C)

    @pytest.mark.asyncio
    async def test_transport_disable_replays_live_frames(self, mock_client: LuxpowerClient) -> None:
        """Disable over Modbus: RMW 0x104c -> 0x1044 (the live toggle)."""
        inverter = self._transport_inverter(mock_client)
        inverter.read_transport_register = AsyncMock(return_value=0x104C)
        inverter.write_transport_register = AsyncMock(return_value=True)

        assert await inverter.disable_pv_sell_to_grid() is True

        inverter.read_transport_register.assert_awaited_once_with(179)
        inverter.write_transport_register.assert_awaited_once_with(179, 0x1044)

    @pytest.mark.asyncio
    async def test_transport_status_reads_bit3(self, mock_client: LuxpowerClient) -> None:
        """Status over Modbus reads bit 3 of register 179."""
        inverter = self._transport_inverter(mock_client)

        inverter.read_transport_register = AsyncMock(return_value=0x104C)
        assert await inverter.get_pv_sell_to_grid_status() is True

        inverter.read_transport_register = AsyncMock(return_value=0x1044)
        assert await inverter.get_pv_sell_to_grid_status() is False

    @pytest.mark.asyncio
    async def test_cloud_enable_uses_function_control(self, mock_client: LuxpowerClient) -> None:
        """Without a transport, enable routes through the atomic
        function-control API with the named parameter (same server-side
        update the cloud-only BaseInverter wrapper performs)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="52842P0581", model="FlexBOSS21"
        )
        mock_client.api.control.control_function = AsyncMock(return_value=_cloud_success())

        assert await inverter.enable_pv_sell_to_grid() is True

        mock_client.api.control.control_function.assert_awaited_once_with(
            "52842P0581", "FUNC_PV_SELL_TO_GRID_EN", True
        )

    @pytest.mark.asyncio
    async def test_cloud_disable_uses_function_control(self, mock_client: LuxpowerClient) -> None:
        inverter = HybridInverter(
            client=mock_client, serial_number="52842P0581", model="FlexBOSS21"
        )
        mock_client.api.control.control_function = AsyncMock(return_value=_cloud_success())

        assert await inverter.disable_pv_sell_to_grid() is True

        mock_client.api.control.control_function.assert_awaited_once_with(
            "52842P0581", "FUNC_PV_SELL_TO_GRID_EN", False
        )

    @pytest.mark.asyncio
    async def test_cloud_status_reads_named_parameter(self, mock_client: LuxpowerClient) -> None:
        """Without a transport, status reads the named param from reg 179."""
        inverter = HybridInverter(
            client=mock_client, serial_number="52842P0581", model="FlexBOSS21"
        )
        mock_client.api.control.read_parameters = AsyncMock(
            return_value=_cloud_read_response(FUNC_PV_SELL_TO_GRID_EN=True)
        )

        assert await inverter.get_pv_sell_to_grid_status() is True

        mock_client.api.control.read_parameters.assert_awaited_once_with("52842P0581", 179, 1)

    @pytest.mark.asyncio
    async def test_generic_inverter_keeps_cloud_endpoint_delegation(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Station discovery instantiates GenericInverter (not Hybrid) — its
        inherited BaseInverter methods must keep delegating to the dedicated
        cloud endpoint helpers so the HTTP flow is unchanged."""
        from pylxpweb.devices.inverters.generic import GenericInverter

        inverter = GenericInverter(
            client=mock_client, serial_number="52842P0581", model="FlexBOSS21"
        )
        mock_client.api.control.enable_pv_sell_to_grid = AsyncMock(return_value=_cloud_success())

        assert await inverter.enable_pv_sell_to_grid() is True

        mock_client.api.control.enable_pv_sell_to_grid.assert_called_once_with("52842P0581")


class TestStopDischargeVoltageOperations:
    """Forced-discharge stop voltage (reg 202, eg4-aa3t).

    The voltage-regime counterpart of the reg-83 stop SOC. Cloud accepts
    float volts in [40, 56] (live round-trip 40 -> 41.5 -> 40 V on an 18kPV
    and a FlexBOSS21); the register stores decivolts (raw 400 == 40 V,
    raw-verified 2026-06-11).
    """

    @pytest.mark.asyncio
    async def test_set_stop_discharge_voltage(self, mock_client: LuxpowerClient) -> None:
        """Setter writes _12K_HOLD_STOP_DISCHG_VOLT as a float-volt string
        and invalidates the parameter cache on success."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        inverter._parameters_cache_time = datetime.now()

        mock_write_response = Mock()
        mock_write_response.success = True
        mock_client.api.control.write_parameter = AsyncMock(return_value=mock_write_response)

        result = await inverter.set_stop_discharge_voltage(41.5)

        mock_client.api.control.write_parameter.assert_called_once_with(
            "1234567890", "_12K_HOLD_STOP_DISCHG_VOLT", "41.5"
        )
        assert result is True
        # Successful write invalidates the parameter cache
        assert inverter._parameters_cache_time is None

    @pytest.mark.asyncio
    async def test_set_stop_discharge_voltage_out_of_range(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Volts outside 40.0-56.0 raise ValueError (both directions)."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        with pytest.raises(ValueError, match="between 40.0 and 56.0"):
            await inverter.set_stop_discharge_voltage(39.9)
        with pytest.raises(ValueError, match="between 40.0 and 56.0"):
            await inverter.set_stop_discharge_voltage(56.1)

    @pytest.mark.asyncio
    async def test_set_stop_discharge_voltage_failure_keeps_cache(
        self, mock_client: LuxpowerClient
    ) -> None:
        """A failed write returns False and does NOT invalidate the cache."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        stamp = datetime.now()
        inverter._parameters_cache_time = stamp

        mock_write_response = Mock()
        mock_write_response.success = False
        mock_client.api.control.write_parameter = AsyncMock(return_value=mock_write_response)

        assert await inverter.set_stop_discharge_voltage(41.5) is False
        assert inverter._parameters_cache_time == stamp

    def test_property_none_before_parameter_load(self, mock_client: LuxpowerClient) -> None:
        """Getter returns None until parameters are loaded."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        assert inverter.parameters is None
        assert inverter.stop_discharge_voltage is None

    def test_property_reads_cached_parameters(self, mock_client: LuxpowerClient) -> None:
        """Getter passes the cached value through unscaled: cloud volts read
        as volts; a local-transport cache surfaces raw decivolts (415) and
        the caller normalizes — mirroring forced_discharge_power."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        inverter.parameters = {"_12K_HOLD_STOP_DISCHG_VOLT": 41.5}
        assert inverter.stop_discharge_voltage == 41.5

        inverter.parameters = {"_12K_HOLD_STOP_DISCHG_VOLT": 415}
        assert inverter.stop_discharge_voltage == 415.0

    def test_property_rejects_garbage_cache_values(self, mock_client: LuxpowerClient) -> None:
        """Unparseable values read as None, not numbers."""
        inverter = HybridInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        inverter.parameters = {"_12K_HOLD_STOP_DISCHG_VOLT": "garbage"}

        assert inverter.stop_discharge_voltage is None

    def test_register_map_carries_stop_discharge_voltage(self) -> None:
        """REGISTER_TO_PARAM_KEYS resolves reg 202 to the canonical name so
        transport read_named_parameters() populates the param cache and
        write_named_parameters() can target the register by name."""
        from pylxpweb.constants import REGISTER_TO_PARAM_KEYS
        from pylxpweb.registers.inverter_holding import BY_ADDRESS

        assert REGISTER_TO_PARAM_KEYS[202] == ["_12K_HOLD_STOP_DISCHG_VOLT"]
        # And the transport map agrees with the canonical holding table.
        canonical = BY_ADDRESS[202]
        assert canonical[0].api_param_key == "_12K_HOLD_STOP_DISCHG_VOLT"
