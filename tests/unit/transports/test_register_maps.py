"""Tests for model-specific Modbus register maps."""

from __future__ import annotations

import pytest

from pylxpweb.constants.scaling import ScaleFactor
from pylxpweb.devices.inverters._features import InverterFamily
from pylxpweb.transports.register_maps import (
    LXP_EU_ENERGY_MAP,
    LXP_EU_RUNTIME_MAP,
    PV_SERIES_ENERGY_MAP,
    PV_SERIES_RUNTIME_MAP,
    RegisterField,
    get_energy_map,
    get_runtime_map,
)


class TestRegisterField:
    """Tests for RegisterField dataclass."""

    def test_register_field_default_values(self) -> None:
        """Test RegisterField with default values."""
        field = RegisterField(address=16)

        assert field.address == 16
        assert field.bit_width == 16
        assert field.scale_factor == ScaleFactor.SCALE_NONE
        assert field.signed is False

    def test_register_field_32bit_with_scaling(self) -> None:
        """Test RegisterField with 32-bit width and scaling."""
        field = RegisterField(
            address=6,
            bit_width=32,
            scale_factor=ScaleFactor.SCALE_10,
        )

        assert field.address == 6
        assert field.bit_width == 32
        assert field.scale_factor == ScaleFactor.SCALE_10
        assert field.signed is False

    def test_register_field_signed(self) -> None:
        """Test RegisterField with signed value."""
        field = RegisterField(
            address=64,
            bit_width=16,
            scale_factor=ScaleFactor.SCALE_NONE,
            signed=True,
        )

        assert field.signed is True

    def test_register_field_frozen(self) -> None:
        """Test that RegisterField is immutable (frozen)."""
        field = RegisterField(address=16)

        with pytest.raises(AttributeError):
            field.address = 17  # type: ignore[misc]


class TestRuntimeRegisterMap:
    """Tests for RuntimeRegisterMap dataclass."""

    def test_pv_series_map_pv_power_32bit(self) -> None:
        """Test PV_SERIES uses 32-bit power values."""
        assert PV_SERIES_RUNTIME_MAP.pv1_power is not None
        assert PV_SERIES_RUNTIME_MAP.pv1_power.bit_width == 32
        assert PV_SERIES_RUNTIME_MAP.pv1_power.address == 6

        assert PV_SERIES_RUNTIME_MAP.pv2_power is not None
        assert PV_SERIES_RUNTIME_MAP.pv2_power.bit_width == 32
        assert PV_SERIES_RUNTIME_MAP.pv2_power.address == 8

        assert PV_SERIES_RUNTIME_MAP.pv3_power is not None
        assert PV_SERIES_RUNTIME_MAP.pv3_power.bit_width == 32
        assert PV_SERIES_RUNTIME_MAP.pv3_power.address == 10

    def test_lxp_eu_map_pv_power_16bit(self) -> None:
        """Test LXP_EU uses 16-bit power values at different addresses."""
        assert LXP_EU_RUNTIME_MAP.pv1_power is not None
        assert LXP_EU_RUNTIME_MAP.pv1_power.bit_width == 16
        assert LXP_EU_RUNTIME_MAP.pv1_power.address == 7

        assert LXP_EU_RUNTIME_MAP.pv2_power is not None
        assert LXP_EU_RUNTIME_MAP.pv2_power.bit_width == 16
        assert LXP_EU_RUNTIME_MAP.pv2_power.address == 8

        assert LXP_EU_RUNTIME_MAP.pv3_power is not None
        assert LXP_EU_RUNTIME_MAP.pv3_power.bit_width == 16
        assert LXP_EU_RUNTIME_MAP.pv3_power.address == 9

    def test_pv_series_grid_voltage_addresses(self) -> None:
        """Test PV_SERIES grid voltage register addresses."""
        assert PV_SERIES_RUNTIME_MAP.grid_voltage_r is not None
        assert PV_SERIES_RUNTIME_MAP.grid_voltage_r.address == 16

        assert PV_SERIES_RUNTIME_MAP.grid_frequency is not None
        assert PV_SERIES_RUNTIME_MAP.grid_frequency.address == 19

    def test_lxp_eu_grid_voltage_offset(self) -> None:
        """Test LXP_EU grid voltage has 4-register offset from PV_SERIES."""
        assert LXP_EU_RUNTIME_MAP.grid_voltage_r is not None
        assert LXP_EU_RUNTIME_MAP.grid_voltage_r.address == 12  # Was 16

        assert LXP_EU_RUNTIME_MAP.grid_frequency is not None
        assert LXP_EU_RUNTIME_MAP.grid_frequency.address == 15  # Was 19

    def test_pv_series_eps_addresses(self) -> None:
        """Test PV_SERIES EPS register addresses."""
        assert PV_SERIES_RUNTIME_MAP.eps_voltage_r is not None
        assert PV_SERIES_RUNTIME_MAP.eps_voltage_r.address == 26

        assert PV_SERIES_RUNTIME_MAP.eps_power is not None
        assert PV_SERIES_RUNTIME_MAP.eps_power.address == 30
        assert PV_SERIES_RUNTIME_MAP.eps_power.bit_width == 32

    def test_lxp_eu_eps_offset(self) -> None:
        """Test LXP_EU EPS register offset and 16-bit power."""
        assert LXP_EU_RUNTIME_MAP.eps_voltage_r is not None
        assert LXP_EU_RUNTIME_MAP.eps_voltage_r.address == 20  # Was 26

        assert LXP_EU_RUNTIME_MAP.eps_power is not None
        assert LXP_EU_RUNTIME_MAP.eps_power.address == 24  # Was 30
        assert LXP_EU_RUNTIME_MAP.eps_power.bit_width == 16  # Was 32

    def test_pv_series_load_power_32bit(self) -> None:
        """Test PV_SERIES load power is 32-bit."""
        assert PV_SERIES_RUNTIME_MAP.load_power is not None
        assert PV_SERIES_RUNTIME_MAP.load_power.address == 34
        assert PV_SERIES_RUNTIME_MAP.load_power.bit_width == 32

    def test_lxp_eu_load_power_16bit(self) -> None:
        """Test LXP_EU load power is 16-bit at different address."""
        assert LXP_EU_RUNTIME_MAP.load_power is not None
        assert LXP_EU_RUNTIME_MAP.load_power.address == 27  # Was 34
        assert LXP_EU_RUNTIME_MAP.load_power.bit_width == 16  # Was 32

    def test_pv_series_bus_voltage_addresses(self) -> None:
        """Test PV_SERIES bus voltage addresses."""
        assert PV_SERIES_RUNTIME_MAP.bus_voltage_1 is not None
        assert PV_SERIES_RUNTIME_MAP.bus_voltage_1.address == 43

        assert PV_SERIES_RUNTIME_MAP.bus_voltage_2 is not None
        assert PV_SERIES_RUNTIME_MAP.bus_voltage_2.address == 44

    def test_lxp_eu_bus_voltage_offset(self) -> None:
        """Test LXP_EU bus voltage offset."""
        assert LXP_EU_RUNTIME_MAP.bus_voltage_1 is not None
        assert LXP_EU_RUNTIME_MAP.bus_voltage_1.address == 38  # Was 43

        assert LXP_EU_RUNTIME_MAP.bus_voltage_2 is not None
        assert LXP_EU_RUNTIME_MAP.bus_voltage_2.address == 39  # Was 44

    def test_temperature_addresses_same(self) -> None:
        """Test temperature registers are same for both families."""
        # Temperatures are in the same location for both models
        assert PV_SERIES_RUNTIME_MAP.internal_temperature is not None
        assert LXP_EU_RUNTIME_MAP.internal_temperature is not None
        assert (
            PV_SERIES_RUNTIME_MAP.internal_temperature.address
            == LXP_EU_RUNTIME_MAP.internal_temperature.address
        )
        assert PV_SERIES_RUNTIME_MAP.internal_temperature.address == 64

    def test_voltage_scaling(self) -> None:
        """Test voltage fields have correct scaling."""
        # Grid voltages should be SCALE_10
        assert PV_SERIES_RUNTIME_MAP.grid_voltage_r is not None
        assert PV_SERIES_RUNTIME_MAP.grid_voltage_r.scale_factor == ScaleFactor.SCALE_10

        # Battery voltage should be SCALE_100
        assert PV_SERIES_RUNTIME_MAP.battery_voltage is not None
        assert PV_SERIES_RUNTIME_MAP.battery_voltage.scale_factor == ScaleFactor.SCALE_100

        # Frequency should be SCALE_100
        assert PV_SERIES_RUNTIME_MAP.grid_frequency is not None
        assert PV_SERIES_RUNTIME_MAP.grid_frequency.scale_factor == ScaleFactor.SCALE_100


class TestEnergyRegisterMap:
    """Tests for EnergyRegisterMap dataclass."""

    def test_pv_series_daily_energy_32bit(self) -> None:
        """Test PV_SERIES daily energy uses 32-bit register pairs."""
        assert PV_SERIES_ENERGY_MAP.inverter_energy_today is not None
        assert PV_SERIES_ENERGY_MAP.inverter_energy_today.bit_width == 32
        assert PV_SERIES_ENERGY_MAP.inverter_energy_today.address == 45

    def test_lxp_eu_daily_energy_16bit(self) -> None:
        """Test LXP_EU daily energy uses 16-bit registers."""
        assert LXP_EU_ENERGY_MAP.inverter_energy_today is not None
        assert LXP_EU_ENERGY_MAP.inverter_energy_today.bit_width == 16
        assert LXP_EU_ENERGY_MAP.inverter_energy_today.address == 28

    def test_pv_series_lifetime_energy_format(self) -> None:
        """Test PV_SERIES lifetime energy uses single-register kWh format."""
        assert PV_SERIES_ENERGY_MAP.inverter_energy_total is not None
        assert PV_SERIES_ENERGY_MAP.inverter_energy_total.bit_width == 16
        assert PV_SERIES_ENERGY_MAP.inverter_energy_total.address == 36
        # Single-register lifetime values are in kWh directly (SCALE_NONE)
        assert PV_SERIES_ENERGY_MAP.inverter_energy_total.scale_factor == ScaleFactor.SCALE_NONE

    def test_lxp_eu_lifetime_energy_32bit(self) -> None:
        """Test LXP_EU lifetime energy uses 32-bit 0.1 Wh format."""
        assert LXP_EU_ENERGY_MAP.inverter_energy_total is not None
        assert LXP_EU_ENERGY_MAP.inverter_energy_total.bit_width == 32
        assert LXP_EU_ENERGY_MAP.inverter_energy_total.address == 40
        assert LXP_EU_ENERGY_MAP.inverter_energy_total.scale_factor == ScaleFactor.SCALE_10

    def test_no_per_pv_energy_via_modbus(self) -> None:
        """Test neither map has per-PV string energy (not available via Modbus).

        Per-PV string power is available (registers 6-11), but per-PV string
        energy counters are not exposed via Modbus. Only aggregate energy is
        available (registers 36-58).
        """
        # LXP_EU has no per-PV string energy
        assert LXP_EU_ENERGY_MAP.pv1_energy_today is None
        assert LXP_EU_ENERGY_MAP.pv2_energy_today is None
        assert LXP_EU_ENERGY_MAP.pv3_energy_today is None
        assert LXP_EU_ENERGY_MAP.pv1_energy_total is None
        assert LXP_EU_ENERGY_MAP.pv2_energy_total is None
        assert LXP_EU_ENERGY_MAP.pv3_energy_total is None

        # PV_SERIES also has no per-PV string energy via Modbus
        # (registers 91-102 are BMS data, not energy)
        assert PV_SERIES_ENERGY_MAP.pv1_energy_today is None
        assert PV_SERIES_ENERGY_MAP.pv2_energy_today is None
        assert PV_SERIES_ENERGY_MAP.pv3_energy_today is None
        assert PV_SERIES_ENERGY_MAP.pv1_energy_total is None
        assert PV_SERIES_ENERGY_MAP.pv2_energy_total is None
        assert PV_SERIES_ENERGY_MAP.pv3_energy_total is None


class TestGetRegisterMap:
    """Tests for get_runtime_map and get_energy_map functions."""

    def test_get_runtime_map_pv_series(self) -> None:
        """Test get_runtime_map returns correct map for PV_SERIES."""
        result = get_runtime_map(InverterFamily.PV_SERIES)
        assert result is PV_SERIES_RUNTIME_MAP

    def test_get_runtime_map_lxp_eu(self) -> None:
        """Test get_runtime_map returns correct map for LXP_EU."""
        result = get_runtime_map(InverterFamily.LXP_EU)
        assert result is LXP_EU_RUNTIME_MAP

    def test_get_runtime_map_sna_uses_pv_series(self) -> None:
        """Test SNA family uses PV_SERIES map (US market same layout)."""
        result = get_runtime_map(InverterFamily.SNA)
        assert result is PV_SERIES_RUNTIME_MAP

    def test_get_runtime_map_lxp_lv_uses_lxp_eu(self) -> None:
        """Test LXP_LV family uses LXP_EU map (similar architecture)."""
        result = get_runtime_map(InverterFamily.LXP_LV)
        assert result is LXP_EU_RUNTIME_MAP

    def test_get_runtime_map_unknown_defaults_pv_series(self) -> None:
        """Test UNKNOWN family defaults to PV_SERIES (backward compat)."""
        result = get_runtime_map(InverterFamily.UNKNOWN)
        assert result is PV_SERIES_RUNTIME_MAP

    def test_get_runtime_map_none_defaults_pv_series(self) -> None:
        """Test None input defaults to PV_SERIES."""
        result = get_runtime_map(None)
        assert result is PV_SERIES_RUNTIME_MAP

    def test_get_energy_map_pv_series(self) -> None:
        """Test get_energy_map returns correct map for PV_SERIES."""
        result = get_energy_map(InverterFamily.PV_SERIES)
        assert result is PV_SERIES_ENERGY_MAP

    def test_get_energy_map_lxp_eu(self) -> None:
        """Test get_energy_map returns correct map for LXP_EU."""
        result = get_energy_map(InverterFamily.LXP_EU)
        assert result is LXP_EU_ENERGY_MAP

    def test_get_energy_map_none_defaults_pv_series(self) -> None:
        """Test None input defaults to PV_SERIES energy map."""
        result = get_energy_map(None)
        assert result is PV_SERIES_ENERGY_MAP


class TestRegisterMapIntegration:
    """Integration tests for register maps with data parsing."""

    def test_pv_series_runtime_data_parsing(self) -> None:
        """Test PV_SERIES register map produces correct runtime data."""
        from pylxpweb.transports.data import InverterRuntimeData

        # Sample registers for PV_SERIES (32-bit power values)
        registers = {
            0: 1,  # Device status
            1: 4100,  # PV1 voltage (410.0V)
            2: 4200,  # PV2 voltage (420.0V)
            3: 0,  # PV3 voltage
            4: 5300,  # Battery voltage (53.00V)
            5: 0x6428,  # SOC=40, SOH=100 packed
            6: 0,  # PV1 power high word
            7: 3000,  # PV1 power low word (3000W)
            8: 0,  # PV2 power high word
            9: 2500,  # PV2 power low word (2500W)
            16: 2410,  # Grid voltage R (241.0V)
            19: 5998,  # Grid frequency (59.98Hz)
        }

        result = InverterRuntimeData.from_modbus_registers(registers, PV_SERIES_RUNTIME_MAP)

        assert result.pv1_voltage == 410.0
        assert result.pv2_voltage == 420.0
        assert result.battery_voltage == 53.0
        assert result.battery_soc == 40
        assert result.battery_soh == 100
        assert result.pv1_power == 3000.0
        assert result.pv2_power == 2500.0
        assert result.grid_voltage_r == 241.0
        assert result.grid_frequency == 59.98

    def test_lxp_eu_runtime_data_parsing(self) -> None:
        """Test LXP_EU register map produces correct runtime data."""
        from pylxpweb.transports.data import InverterRuntimeData

        # Sample registers for LXP_EU (16-bit power values at offset addresses)
        registers = {
            0: 1,  # Device status
            1: 3800,  # PV1 voltage (380.0V)
            4: 5100,  # Battery voltage (51.00V)
            5: 0x6432,  # SOC=50, SOH=100 packed
            7: 4000,  # PV1 power (4000W) - 16-bit at reg 7
            8: 3500,  # PV2 power (3500W) - 16-bit at reg 8
            12: 2300,  # Grid voltage R (230.0V) - offset from 16
            15: 5000,  # Grid frequency (50.00Hz) - offset from 19
        }

        result = InverterRuntimeData.from_modbus_registers(registers, LXP_EU_RUNTIME_MAP)

        assert result.pv1_voltage == 380.0
        assert result.battery_voltage == 51.0
        assert result.battery_soc == 50
        assert result.battery_soh == 100
        assert result.pv1_power == 4000.0
        assert result.pv2_power == 3500.0
        assert result.grid_voltage_r == 230.0
        assert result.grid_frequency == 50.0

    def test_pv_series_energy_data_parsing(self) -> None:
        """Test PV_SERIES energy register map parsing."""
        from pylxpweb.transports.data import InverterEnergyData

        # Sample registers for PV_SERIES energy
        registers = {
            36: 1500,  # Inverter energy total (1500 kWh)
            45: 0,  # Inverter energy today high
            46: 150000,  # Inverter energy today low (15.0 kWh after scaling)
        }

        result = InverterEnergyData.from_modbus_registers(registers, PV_SERIES_ENERGY_MAP)

        # Lifetime is in kWh directly for PV_SERIES
        assert result.inverter_energy_total == 1500.0
        # Daily is in 0.1 Wh, converted to kWh
        assert result.inverter_energy_today == 15.0

    def test_backward_compatibility_no_register_map(self) -> None:
        """Test from_modbus_registers works without register_map arg."""
        from pylxpweb.transports.data import InverterRuntimeData

        # Should use PV_SERIES_RUNTIME_MAP by default
        registers = {
            0: 1,
            1: 4100,  # PV1 voltage
            4: 5300,  # Battery voltage
            5: 0x6428,  # SOC/SOH
            16: 2410,  # Grid voltage R at PV_SERIES location
        }

        result = InverterRuntimeData.from_modbus_registers(registers)

        assert result.pv1_voltage == 410.0
        assert result.battery_voltage == 53.0
        assert result.grid_voltage_r == 241.0


class TestDataHelperFunctions:
    """Tests for data.py helper functions edge cases."""

    def test_read_register_field_none_returns_default(self) -> None:
        """Test _read_register_field returns default when field is None."""
        from pylxpweb.transports.data import _read_register_field

        result = _read_register_field({0: 100}, None, default=42)
        assert result == 42

    def test_read_register_field_signed_16bit_negative(self) -> None:
        """Test _read_register_field handles signed 16-bit negative values."""
        from pylxpweb.transports.data import _read_register_field

        # 65535 in unsigned 16-bit is -1 in signed
        field = RegisterField(address=0, bit_width=16, signed=True)
        result = _read_register_field({0: 65535}, field)
        assert result == -1

        # 32768 in unsigned 16-bit is -32768 in signed
        result = _read_register_field({0: 32768}, field)
        assert result == -32768

    def test_read_register_field_signed_32bit_negative(self) -> None:
        """Test _read_register_field handles signed 32-bit negative values."""
        from pylxpweb.transports.data import _read_register_field

        # 0xFFFFFFFF in unsigned 32-bit is -1 in signed
        field = RegisterField(address=0, bit_width=32, signed=True)
        result = _read_register_field({0: 0xFFFF, 1: 0xFFFF}, field)
        assert result == -1

        # 0x80000000 in unsigned 32-bit is -2147483648 in signed
        result = _read_register_field({0: 0x8000, 1: 0x0000}, field)
        assert result == -2147483648

    def test_read_and_scale_field_none_returns_default(self) -> None:
        """Test _read_and_scale_field returns default when field is None."""
        from pylxpweb.transports.data import _read_and_scale_field

        result = _read_and_scale_field({0: 100}, None, default=99.5)
        assert result == 99.5

    def test_clamp_percentage_negative_value(self) -> None:
        """Test _clamp_percentage clamps negative values to 0."""
        from pylxpweb.transports.data import _clamp_percentage

        result = _clamp_percentage(-5, "test_field")
        assert result == 0

    def test_clamp_percentage_over_100(self) -> None:
        """Test _clamp_percentage clamps values over 100 to 100."""
        from pylxpweb.transports.data import _clamp_percentage

        result = _clamp_percentage(150, "test_field")
        assert result == 100

    def test_clamp_percentage_valid_range(self) -> None:
        """Test _clamp_percentage returns value unchanged when in valid range."""
        from pylxpweb.transports.data import _clamp_percentage

        assert _clamp_percentage(0, "test") == 0
        assert _clamp_percentage(50, "test") == 50
        assert _clamp_percentage(100, "test") == 100


class TestEnergyDataEdgeCases:
    """Tests for InverterEnergyData edge cases."""

    def test_energy_data_none_field_returns_zero(self) -> None:
        """Test energy data parsing handles None fields gracefully."""
        from pylxpweb.transports.data import InverterEnergyData
        from pylxpweb.transports.register_maps import EnergyRegisterMap

        # EnergyRegisterMap defaults all fields to None, so empty instance
        # will test the None field code paths
        sparse_map = EnergyRegisterMap()

        # All values should default to 0.0 when fields are None
        result = InverterEnergyData.from_modbus_registers({}, sparse_map)

        assert result.pv_energy_today == 0.0
        assert result.pv_energy_total == 0.0
        assert result.charge_energy_today == 0.0
        assert result.discharge_energy_today == 0.0
        assert result.inverter_energy_today == 0.0
        assert result.inverter_energy_total == 0.0
