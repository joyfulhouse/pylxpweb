"""Tests for model-specific Modbus register maps.

Register mappings validated against:
- galets/eg4-modbus-monitor (registers-18kpv.yaml)
- poldim/EG4-Inverter-Modbus (const.py)

Key finding: PV_SERIES uses 16-bit power values at specific registers,
NOT 32-bit pairs as previously assumed. This matches the validated
implementations.
"""

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
    """Tests for RuntimeRegisterMap dataclass.

    Based on validated implementations from galets/poldim:
    - PV_SERIES (18kPV): 16-bit power at regs 7-9, 10-11, 16, 24, 27
    - LXP_EU (12K): 16-bit power at same addresses but different offsets
    """

    def test_pv_series_map_pv_power_16bit(self) -> None:
        """Test PV_SERIES uses 16-bit power values (validated from galets/poldim)."""
        assert PV_SERIES_RUNTIME_MAP.pv1_power is not None
        assert PV_SERIES_RUNTIME_MAP.pv1_power.bit_width == 16
        assert PV_SERIES_RUNTIME_MAP.pv1_power.address == 7

        assert PV_SERIES_RUNTIME_MAP.pv2_power is not None
        assert PV_SERIES_RUNTIME_MAP.pv2_power.bit_width == 16
        assert PV_SERIES_RUNTIME_MAP.pv2_power.address == 8

        assert PV_SERIES_RUNTIME_MAP.pv3_power is not None
        assert PV_SERIES_RUNTIME_MAP.pv3_power.bit_width == 16
        assert PV_SERIES_RUNTIME_MAP.pv3_power.address == 9

    def test_lxp_eu_map_pv_power_16bit(self) -> None:
        """Test LXP_EU uses 16-bit power values at same addresses."""
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
        """Test PV_SERIES grid voltage register addresses (validated)."""
        assert PV_SERIES_RUNTIME_MAP.grid_voltage_r is not None
        assert PV_SERIES_RUNTIME_MAP.grid_voltage_r.address == 12

        assert PV_SERIES_RUNTIME_MAP.grid_frequency is not None
        assert PV_SERIES_RUNTIME_MAP.grid_frequency.address == 15

    def test_lxp_eu_grid_voltage_same(self) -> None:
        """Test LXP_EU grid voltage same addresses as PV_SERIES."""
        assert LXP_EU_RUNTIME_MAP.grid_voltage_r is not None
        assert LXP_EU_RUNTIME_MAP.grid_voltage_r.address == 12

        assert LXP_EU_RUNTIME_MAP.grid_frequency is not None
        assert LXP_EU_RUNTIME_MAP.grid_frequency.address == 15

    def test_pv_series_eps_addresses(self) -> None:
        """Test PV_SERIES EPS register addresses (validated)."""
        assert PV_SERIES_RUNTIME_MAP.eps_voltage_r is not None
        assert PV_SERIES_RUNTIME_MAP.eps_voltage_r.address == 20

        assert PV_SERIES_RUNTIME_MAP.eps_power is not None
        assert PV_SERIES_RUNTIME_MAP.eps_power.address == 24
        assert PV_SERIES_RUNTIME_MAP.eps_power.bit_width == 16

    def test_lxp_eu_eps_addresses(self) -> None:
        """Test LXP_EU EPS register addresses."""
        assert LXP_EU_RUNTIME_MAP.eps_voltage_r is not None
        assert LXP_EU_RUNTIME_MAP.eps_voltage_r.address == 20

        assert LXP_EU_RUNTIME_MAP.eps_power is not None
        assert LXP_EU_RUNTIME_MAP.eps_power.address == 24
        assert LXP_EU_RUNTIME_MAP.eps_power.bit_width == 16

    def test_pv_series_load_power_16bit(self) -> None:
        """Test PV_SERIES load power is 16-bit at reg 27 (validated)."""
        assert PV_SERIES_RUNTIME_MAP.load_power is not None
        assert PV_SERIES_RUNTIME_MAP.load_power.address == 27
        assert PV_SERIES_RUNTIME_MAP.load_power.bit_width == 16

    def test_lxp_eu_load_power_16bit(self) -> None:
        """Test LXP_EU load power is 16-bit at reg 27."""
        assert LXP_EU_RUNTIME_MAP.load_power is not None
        assert LXP_EU_RUNTIME_MAP.load_power.address == 27
        assert LXP_EU_RUNTIME_MAP.load_power.bit_width == 16

    def test_pv_series_bus_voltage_addresses(self) -> None:
        """Test PV_SERIES bus voltage addresses (validated: regs 38-39)."""
        assert PV_SERIES_RUNTIME_MAP.bus_voltage_1 is not None
        assert PV_SERIES_RUNTIME_MAP.bus_voltage_1.address == 38

        assert PV_SERIES_RUNTIME_MAP.bus_voltage_2 is not None
        assert PV_SERIES_RUNTIME_MAP.bus_voltage_2.address == 39

    def test_lxp_eu_bus_voltage_same(self) -> None:
        """Test LXP_EU bus voltage same addresses."""
        assert LXP_EU_RUNTIME_MAP.bus_voltage_1 is not None
        assert LXP_EU_RUNTIME_MAP.bus_voltage_1.address == 38

        assert LXP_EU_RUNTIME_MAP.bus_voltage_2 is not None
        assert LXP_EU_RUNTIME_MAP.bus_voltage_2.address == 39

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
        """Test voltage fields have correct scaling (validated)."""
        # Grid voltages should be SCALE_10
        assert PV_SERIES_RUNTIME_MAP.grid_voltage_r is not None
        assert PV_SERIES_RUNTIME_MAP.grid_voltage_r.scale_factor == ScaleFactor.SCALE_10

        # Battery voltage should be SCALE_10 (galets: Vbat scale=0.1)
        assert PV_SERIES_RUNTIME_MAP.battery_voltage is not None
        assert PV_SERIES_RUNTIME_MAP.battery_voltage.scale_factor == ScaleFactor.SCALE_10

        # Frequency should be SCALE_100
        assert PV_SERIES_RUNTIME_MAP.grid_frequency is not None
        assert PV_SERIES_RUNTIME_MAP.grid_frequency.scale_factor == ScaleFactor.SCALE_100


class TestEnergyRegisterMap:
    """Tests for EnergyRegisterMap dataclass.

    Based on galets/eg4-modbus-monitor:
    - Daily energy: 16-bit at regs 28-37, scale 0.1 kWh
    - Lifetime energy: 32-bit pairs at regs 40-59, scale 0.1 kWh
    """

    def test_pv_series_daily_energy_16bit(self) -> None:
        """Test PV_SERIES daily energy uses 16-bit registers (validated)."""
        assert PV_SERIES_ENERGY_MAP.inverter_energy_today is not None
        assert PV_SERIES_ENERGY_MAP.inverter_energy_today.bit_width == 16
        assert PV_SERIES_ENERGY_MAP.inverter_energy_today.address == 31

    def test_lxp_eu_daily_energy_16bit(self) -> None:
        """Test LXP_EU daily energy uses 16-bit registers (same layout as PV_SERIES).

        Source: luxpower-ha-integration constants confirm same register layout.
        """
        assert LXP_EU_ENERGY_MAP.inverter_energy_today is not None
        assert LXP_EU_ENERGY_MAP.inverter_energy_today.bit_width == 16
        assert LXP_EU_ENERGY_MAP.inverter_energy_today.address == 31  # Same as PV_SERIES

    def test_pv_series_lifetime_energy_16bit(self) -> None:
        """Test PV_SERIES lifetime energy uses 16-bit registers (empirically validated).

        Note: galets/eg4-modbus-monitor claims 32-bit pairs, but empirical testing
        shows these are 16-bit registers that match HTTP API values exactly.
        """
        assert PV_SERIES_ENERGY_MAP.inverter_energy_total is not None
        assert PV_SERIES_ENERGY_MAP.inverter_energy_total.bit_width == 16
        assert PV_SERIES_ENERGY_MAP.inverter_energy_total.address == 46
        # Scale 0.1 = SCALE_10
        assert PV_SERIES_ENERGY_MAP.inverter_energy_total.scale_factor == ScaleFactor.SCALE_10

    def test_lxp_eu_lifetime_energy_32bit(self) -> None:
        """Test LXP_EU lifetime energy uses 32-bit pairs per luxpower-ha-integration.

        Source: luxpower-ha-integration uses 32-bit pairs (L/H registers).
        """
        assert LXP_EU_ENERGY_MAP.inverter_energy_total is not None
        assert LXP_EU_ENERGY_MAP.inverter_energy_total.bit_width == 32  # 32-bit pairs
        assert LXP_EU_ENERGY_MAP.inverter_energy_total.address == 46  # Same as PV_SERIES
        assert LXP_EU_ENERGY_MAP.inverter_energy_total.scale_factor == ScaleFactor.SCALE_10

    def test_pv_series_per_pv_energy_available(self) -> None:
        """Test PV_SERIES has per-PV string energy (validated from galets).

        galets/eg4-modbus-monitor shows:
        - Epv1_day at reg 28, Epv2_day at 29, Epv3_day at 30
        - Epv1_all at regs 40-41, Epv2_all at 42-43, Epv3_all at 44-45
        """
        # Daily per-PV energy
        assert PV_SERIES_ENERGY_MAP.pv1_energy_today is not None
        assert PV_SERIES_ENERGY_MAP.pv1_energy_today.address == 28
        assert PV_SERIES_ENERGY_MAP.pv2_energy_today is not None
        assert PV_SERIES_ENERGY_MAP.pv2_energy_today.address == 29
        assert PV_SERIES_ENERGY_MAP.pv3_energy_today is not None
        assert PV_SERIES_ENERGY_MAP.pv3_energy_today.address == 30

        # Lifetime per-PV energy
        assert PV_SERIES_ENERGY_MAP.pv1_energy_total is not None
        assert PV_SERIES_ENERGY_MAP.pv1_energy_total.address == 40
        assert PV_SERIES_ENERGY_MAP.pv2_energy_total is not None
        assert PV_SERIES_ENERGY_MAP.pv2_energy_total.address == 42
        assert PV_SERIES_ENERGY_MAP.pv3_energy_total is not None
        assert PV_SERIES_ENERGY_MAP.pv3_energy_total.address == 44

    def test_lxp_eu_per_pv_energy_available(self) -> None:
        """Test LXP_EU has per-PV string energy (same layout as PV_SERIES).

        Source: luxpower-ha-integration confirms same register addresses.
        """
        # Daily per-PV energy
        assert LXP_EU_ENERGY_MAP.pv1_energy_today is not None
        assert LXP_EU_ENERGY_MAP.pv1_energy_today.address == 28
        assert LXP_EU_ENERGY_MAP.pv2_energy_today is not None
        assert LXP_EU_ENERGY_MAP.pv2_energy_today.address == 29
        assert LXP_EU_ENERGY_MAP.pv3_energy_today is not None
        assert LXP_EU_ENERGY_MAP.pv3_energy_today.address == 30

        # Lifetime per-PV energy (32-bit pairs)
        assert LXP_EU_ENERGY_MAP.pv1_energy_total is not None
        assert LXP_EU_ENERGY_MAP.pv1_energy_total.address == 40
        assert LXP_EU_ENERGY_MAP.pv1_energy_total.bit_width == 32
        assert LXP_EU_ENERGY_MAP.pv2_energy_total is not None
        assert LXP_EU_ENERGY_MAP.pv2_energy_total.address == 42
        assert LXP_EU_ENERGY_MAP.pv3_energy_total is not None
        assert LXP_EU_ENERGY_MAP.pv3_energy_total.address == 44


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
        """Test PV_SERIES register map produces correct runtime data.

        Uses validated register layout from galets/poldim:
        - PV power: 16-bit at regs 7-9
        - Grid voltage: 16-bit at reg 12
        - Grid frequency: 16-bit at reg 15
        """
        from pylxpweb.transports.data import InverterRuntimeData

        # Sample registers for PV_SERIES (16-bit power values)
        registers = {
            0: 1,  # Device status
            1: 4100,  # PV1 voltage (×10 = 410.0V)
            2: 4200,  # PV2 voltage (×10 = 420.0V)
            3: 0,  # PV3 voltage
            4: 530,  # Battery voltage (×10 = 53.0V)
            5: (100 << 8) | 40,  # SOC=40, SOH=100 packed
            7: 3000,  # PV1 power (16-bit, 3000W)
            8: 2500,  # PV2 power (16-bit, 2500W)
            12: 2410,  # Grid voltage R (×10 = 241.0V)
            15: 5998,  # Grid frequency (×100 = 59.98Hz)
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

        # Sample registers for LXP_EU (16-bit power values)
        # Battery voltage uses SCALE_10 (0.1V units) per luxpower-ha-integration
        registers = {
            0: 1,  # Device status
            1: 3800,  # PV1 voltage (380.0V)
            4: 510,  # Battery voltage (51.0V) - raw 510 with SCALE_10
            5: (100 << 8) | 50,  # SOC=50, SOH=100 packed
            7: 4000,  # PV1 power (4000W) - 16-bit at reg 7
            8: 3500,  # PV2 power (3500W) - 16-bit at reg 8
            12: 2300,  # Grid voltage R (230.0V)
            15: 5000,  # Grid frequency (50.00Hz)
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
        """Test PV_SERIES energy register map parsing (validated layout)."""
        from pylxpweb.transports.data import InverterEnergyData

        # Sample registers for PV_SERIES energy
        # Daily energy: 16-bit at regs 28-37, scale 0.1 kWh
        # Lifetime energy: 16-bit registers (not 32-bit pairs as docs claim), scale 0.1 kWh
        registers = {
            31: 184,  # Inverter energy today (18.4 kWh after scaling)
            46: 50000,  # Inverter energy total (5000.0 kWh) - 16-bit register
        }

        result = InverterEnergyData.from_modbus_registers(registers, PV_SERIES_ENERGY_MAP)

        # Daily: raw / 10 = kWh
        assert result.inverter_energy_today == pytest.approx(18.4, rel=0.01)
        # Lifetime: 16-bit value / 10 = kWh
        assert result.inverter_energy_total == pytest.approx(5000.0, rel=0.01)

    def test_backward_compatibility_no_register_map(self) -> None:
        """Test from_modbus_registers works without register_map arg."""
        from pylxpweb.transports.data import InverterRuntimeData

        # Should use PV_SERIES_RUNTIME_MAP by default
        # With new layout: grid voltage at reg 12, not 16
        registers = {
            0: 1,
            1: 4100,  # PV1 voltage
            4: 530,  # Battery voltage (×10 = 53.0V with new SCALE_10)
            5: (100 << 8) | 40,  # SOC/SOH
            12: 2410,  # Grid voltage R at PV_SERIES location (new: reg 12)
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


class TestExtendedSensors:
    """Tests for extended sensors (generator, BMS limits, additional temps).

    Based on poldim/EG4-Inverter-Modbus register definitions.
    """

    def test_pv_series_generator_registers(self) -> None:
        """Test PV_SERIES has generator input registers."""
        assert PV_SERIES_RUNTIME_MAP.generator_voltage is not None
        assert PV_SERIES_RUNTIME_MAP.generator_voltage.address == 121
        assert PV_SERIES_RUNTIME_MAP.generator_voltage.scale_factor == ScaleFactor.SCALE_10

        assert PV_SERIES_RUNTIME_MAP.generator_frequency is not None
        assert PV_SERIES_RUNTIME_MAP.generator_frequency.address == 122
        assert PV_SERIES_RUNTIME_MAP.generator_frequency.scale_factor == ScaleFactor.SCALE_100

        assert PV_SERIES_RUNTIME_MAP.generator_power is not None
        assert PV_SERIES_RUNTIME_MAP.generator_power.address == 123

    def test_lxp_eu_generator_registers(self) -> None:
        """Test LXP_EU has generator input registers."""
        assert LXP_EU_RUNTIME_MAP.generator_voltage is not None
        assert LXP_EU_RUNTIME_MAP.generator_voltage.address == 121

        assert LXP_EU_RUNTIME_MAP.generator_frequency is not None
        assert LXP_EU_RUNTIME_MAP.generator_frequency.address == 122

        assert LXP_EU_RUNTIME_MAP.generator_power is not None
        assert LXP_EU_RUNTIME_MAP.generator_power.address == 123

    def test_pv_series_bms_limits(self) -> None:
        """Test PV_SERIES has BMS limit registers."""
        assert PV_SERIES_RUNTIME_MAP.bms_charge_current_limit is not None
        assert PV_SERIES_RUNTIME_MAP.bms_charge_current_limit.address == 81

        assert PV_SERIES_RUNTIME_MAP.bms_discharge_current_limit is not None
        assert PV_SERIES_RUNTIME_MAP.bms_discharge_current_limit.address == 82

        assert PV_SERIES_RUNTIME_MAP.bms_charge_voltage_ref is not None
        assert PV_SERIES_RUNTIME_MAP.bms_charge_voltage_ref.address == 83
        assert PV_SERIES_RUNTIME_MAP.bms_charge_voltage_ref.scale_factor == ScaleFactor.SCALE_10

        assert PV_SERIES_RUNTIME_MAP.bms_discharge_cutoff is not None
        assert PV_SERIES_RUNTIME_MAP.bms_discharge_cutoff.address == 84
        assert PV_SERIES_RUNTIME_MAP.bms_discharge_cutoff.scale_factor == ScaleFactor.SCALE_10

    def test_pv_series_bms_cell_data(self) -> None:
        """Test PV_SERIES has BMS cell voltage/temperature registers."""
        assert PV_SERIES_RUNTIME_MAP.bms_max_cell_voltage is not None
        assert PV_SERIES_RUNTIME_MAP.bms_max_cell_voltage.address == 101

        assert PV_SERIES_RUNTIME_MAP.bms_min_cell_voltage is not None
        assert PV_SERIES_RUNTIME_MAP.bms_min_cell_voltage.address == 102

        assert PV_SERIES_RUNTIME_MAP.bms_max_cell_temperature is not None
        assert PV_SERIES_RUNTIME_MAP.bms_max_cell_temperature.address == 103

        assert PV_SERIES_RUNTIME_MAP.bms_min_cell_temperature is not None
        assert PV_SERIES_RUNTIME_MAP.bms_min_cell_temperature.address == 104

        assert PV_SERIES_RUNTIME_MAP.bms_cycle_count is not None
        assert PV_SERIES_RUNTIME_MAP.bms_cycle_count.address == 106

    def test_pv_series_battery_info(self) -> None:
        """Test PV_SERIES has battery info registers."""
        assert PV_SERIES_RUNTIME_MAP.battery_parallel_num is not None
        assert PV_SERIES_RUNTIME_MAP.battery_parallel_num.address == 96

        assert PV_SERIES_RUNTIME_MAP.battery_capacity_ah is not None
        assert PV_SERIES_RUNTIME_MAP.battery_capacity_ah.address == 97

    def test_pv_series_additional_temperatures(self) -> None:
        """Test PV_SERIES has additional temperature registers."""
        assert PV_SERIES_RUNTIME_MAP.temperature_t1 is not None
        assert PV_SERIES_RUNTIME_MAP.temperature_t1.address == 108

        assert PV_SERIES_RUNTIME_MAP.temperature_t2 is not None
        assert PV_SERIES_RUNTIME_MAP.temperature_t2.address == 109

        assert PV_SERIES_RUNTIME_MAP.temperature_t3 is not None
        assert PV_SERIES_RUNTIME_MAP.temperature_t3.address == 110

        assert PV_SERIES_RUNTIME_MAP.temperature_t4 is not None
        assert PV_SERIES_RUNTIME_MAP.temperature_t4.address == 111

        assert PV_SERIES_RUNTIME_MAP.temperature_t5 is not None
        assert PV_SERIES_RUNTIME_MAP.temperature_t5.address == 112

    def test_pv_series_inverter_operational(self) -> None:
        """Test PV_SERIES has inverter operational registers."""
        assert PV_SERIES_RUNTIME_MAP.inverter_rms_current is not None
        assert PV_SERIES_RUNTIME_MAP.inverter_rms_current.address == 18
        assert PV_SERIES_RUNTIME_MAP.inverter_rms_current.scale_factor == ScaleFactor.SCALE_100

        assert PV_SERIES_RUNTIME_MAP.inverter_apparent_power is not None
        assert PV_SERIES_RUNTIME_MAP.inverter_apparent_power.address == 25

        assert PV_SERIES_RUNTIME_MAP.inverter_on_time is not None
        assert PV_SERIES_RUNTIME_MAP.inverter_on_time.address == 69
        assert PV_SERIES_RUNTIME_MAP.inverter_on_time.bit_width == 32

        assert PV_SERIES_RUNTIME_MAP.ac_input_type is not None
        assert PV_SERIES_RUNTIME_MAP.ac_input_type.address == 77

    def test_pv_series_generator_energy(self) -> None:
        """Test PV_SERIES has generator energy registers."""
        assert PV_SERIES_ENERGY_MAP.generator_energy_today is not None
        assert PV_SERIES_ENERGY_MAP.generator_energy_today.address == 124
        assert PV_SERIES_ENERGY_MAP.generator_energy_today.bit_width == 16

        assert PV_SERIES_ENERGY_MAP.generator_energy_total is not None
        assert PV_SERIES_ENERGY_MAP.generator_energy_total.address == 125
        assert PV_SERIES_ENERGY_MAP.generator_energy_total.bit_width == 16  # 16-bit, not 32-bit

    def test_lxp_eu_generator_energy(self) -> None:
        """Test LXP_EU has generator energy registers."""
        assert LXP_EU_ENERGY_MAP.generator_energy_today is not None
        assert LXP_EU_ENERGY_MAP.generator_energy_today.address == 124

        assert LXP_EU_ENERGY_MAP.generator_energy_total is not None
        assert LXP_EU_ENERGY_MAP.generator_energy_total.address == 125


class TestExtendedSensorsDataParsing:
    """Tests for parsing extended sensor data from registers."""

    def test_generator_data_parsing(self) -> None:
        """Test generator sensor data parsing."""
        from pylxpweb.transports.data import InverterRuntimeData

        registers = {
            121: 2400,  # Generator voltage (×10 = 240.0V)
            122: 6000,  # Generator frequency (×100 = 60.00Hz)
            123: 5000,  # Generator power (5000W)
        }

        result = InverterRuntimeData.from_modbus_registers(registers, PV_SERIES_RUNTIME_MAP)

        assert result.generator_voltage == 240.0
        assert result.generator_frequency == 60.0
        assert result.generator_power == 5000.0

    def test_bms_limits_parsing(self) -> None:
        """Test BMS limit sensor data parsing.

        Per Yippy's docs: BMS current limits use 0.01A scale (SCALE_100).
        """
        from pylxpweb.transports.data import InverterRuntimeData

        registers = {
            81: 10000,  # BMS charge current limit (×100 = 100.0A)
            82: 10000,  # BMS discharge current limit (×100 = 100.0A)
            83: 560,  # BMS charge voltage ref (×10 = 56.0V)
            84: 480,  # BMS discharge cutoff (×10 = 48.0V)
        }

        result = InverterRuntimeData.from_modbus_registers(registers, PV_SERIES_RUNTIME_MAP)

        assert result.bms_charge_current_limit == 100.0
        assert result.bms_discharge_current_limit == 100.0
        assert result.bms_charge_voltage_ref == 56.0
        assert result.bms_discharge_cutoff == 48.0

    def test_bms_cell_data_parsing(self) -> None:
        """Test BMS cell voltage/temperature data parsing.

        Per Yippy's docs:
        - Cell voltages are in millivolts (0.001V), converted to V in data.py
        - Cell temperatures use 0.1°C scale (SCALE_10), signed
        """
        from pylxpweb.transports.data import InverterRuntimeData

        registers = {
            101: 3450,  # BMS max cell voltage (3450 mV = 3.450V)
            102: 3320,  # BMS min cell voltage (3320 mV = 3.320V)
            103: 280,  # BMS max cell temperature (×10 = 28.0°C)
            104: 250,  # BMS min cell temperature (×10 = 25.0°C)
            106: 150,  # BMS cycle count
        }

        result = InverterRuntimeData.from_modbus_registers(registers, PV_SERIES_RUNTIME_MAP)

        assert result.bms_max_cell_voltage == pytest.approx(3.450, rel=0.01)
        assert result.bms_min_cell_voltage == pytest.approx(3.320, rel=0.01)
        assert result.bms_max_cell_temperature == 28.0
        assert result.bms_min_cell_temperature == 25.0
        assert result.bms_cycle_count == 150

    def test_battery_info_parsing(self) -> None:
        """Test battery info data parsing."""
        from pylxpweb.transports.data import InverterRuntimeData

        registers = {
            96: 4,  # Battery parallel number (4 batteries)
            97: 100,  # Battery capacity (100Ah)
        }

        result = InverterRuntimeData.from_modbus_registers(registers, PV_SERIES_RUNTIME_MAP)

        assert result.battery_parallel_num == 4
        assert result.battery_capacity_ah == 100.0

    def test_additional_temperatures_parsing(self) -> None:
        """Test additional temperature sensor data parsing.

        Per Yippy's docs: T1-T5 use 0.1°C scale (SCALE_10).
        """
        from pylxpweb.transports.data import InverterRuntimeData

        registers = {
            108: 300,  # T1 (×10 = 30.0°C)
            109: 320,  # T2 (×10 = 32.0°C)
            110: 350,  # T3 (×10 = 35.0°C)
            111: 280,  # T4 (×10 = 28.0°C)
            112: 260,  # T5 (×10 = 26.0°C)
        }

        result = InverterRuntimeData.from_modbus_registers(registers, PV_SERIES_RUNTIME_MAP)

        assert result.temperature_t1 == 30.0
        assert result.temperature_t2 == 32.0
        assert result.temperature_t3 == 35.0
        assert result.temperature_t4 == 28.0
        assert result.temperature_t5 == 26.0

    def test_inverter_operational_parsing(self) -> None:
        """Test inverter operational data parsing."""
        from pylxpweb.transports.data import InverterRuntimeData

        registers = {
            18: 500,  # Inverter RMS current (×100 = 5.00A)
            25: 1000,  # Inverter apparent power (1000VA)
            69: 0,  # Inverter on time high word
            70: 1000,  # Inverter on time low word (1000 hours)
            77: 1,  # AC input type
        }

        result = InverterRuntimeData.from_modbus_registers(registers, PV_SERIES_RUNTIME_MAP)

        assert result.inverter_rms_current == 5.0
        assert result.inverter_apparent_power == 1000.0
        assert result.inverter_on_time == 1000
        assert result.ac_input_type == 1

    def test_generator_energy_parsing(self) -> None:
        """Test generator energy data parsing."""
        from pylxpweb.transports.data import InverterEnergyData

        # Generator energy registers are 16-bit (not 32-bit pairs)
        registers = {
            124: 50,  # Generator energy today (÷10 = 5.0 kWh)
            125: 1000,  # Generator energy total (÷10 = 100.0 kWh) - 16-bit register
        }

        result = InverterEnergyData.from_modbus_registers(registers, PV_SERIES_ENERGY_MAP)

        assert result.generator_energy_today == pytest.approx(5.0, rel=0.01)
        assert result.generator_energy_total == pytest.approx(100.0, rel=0.01)


class TestHoldingRegisterMap:
    """Tests for HoldingRegisterMap and writable parameter definitions."""

    def test_pv_series_holding_map_exists(self) -> None:
        """Test that PV_SERIES_HOLDING_MAP is defined."""
        from pylxpweb.transports.register_maps import PV_SERIES_HOLDING_MAP

        assert PV_SERIES_HOLDING_MAP is not None

    def test_holding_map_power_percentages(self) -> None:
        """Test power percentage holding registers."""
        from pylxpweb.transports.register_maps import PV_SERIES_HOLDING_MAP

        # Charge power percent at reg 64
        assert PV_SERIES_HOLDING_MAP.charge_power_percent is not None
        assert PV_SERIES_HOLDING_MAP.charge_power_percent.address == 64
        assert PV_SERIES_HOLDING_MAP.charge_power_percent.min_value == 0
        assert PV_SERIES_HOLDING_MAP.charge_power_percent.max_value == 100

        # Discharge power percent at reg 65
        assert PV_SERIES_HOLDING_MAP.discharge_power_percent is not None
        assert PV_SERIES_HOLDING_MAP.discharge_power_percent.address == 65
        assert PV_SERIES_HOLDING_MAP.discharge_power_percent.min_value == 0
        assert PV_SERIES_HOLDING_MAP.discharge_power_percent.max_value == 100

    def test_holding_map_battery_voltage_settings(self) -> None:
        """Test battery voltage holding registers with scaling."""
        from pylxpweb.constants.scaling import ScaleFactor
        from pylxpweb.transports.register_maps import PV_SERIES_HOLDING_MAP

        # Charge voltage ref at reg 99 with 0.1V scaling
        assert PV_SERIES_HOLDING_MAP.charge_voltage_ref is not None
        assert PV_SERIES_HOLDING_MAP.charge_voltage_ref.address == 99
        assert PV_SERIES_HOLDING_MAP.charge_voltage_ref.scale_factor == ScaleFactor.SCALE_10
        assert PV_SERIES_HOLDING_MAP.charge_voltage_ref.min_value == 50.0
        assert PV_SERIES_HOLDING_MAP.charge_voltage_ref.max_value == 59.0

    def test_holding_map_battery_currents(self) -> None:
        """Test battery current holding registers."""
        from pylxpweb.transports.register_maps import PV_SERIES_HOLDING_MAP

        # Charge current at reg 101
        assert PV_SERIES_HOLDING_MAP.charge_current is not None
        assert PV_SERIES_HOLDING_MAP.charge_current.address == 101
        assert PV_SERIES_HOLDING_MAP.charge_current.min_value == 0
        assert PV_SERIES_HOLDING_MAP.charge_current.max_value == 140

        # Discharge current at reg 102
        assert PV_SERIES_HOLDING_MAP.discharge_current is not None
        assert PV_SERIES_HOLDING_MAP.discharge_current.address == 102

    def test_holding_map_soc_limits(self) -> None:
        """Test SOC limit holding registers."""
        from pylxpweb.transports.register_maps import PV_SERIES_HOLDING_MAP

        # EOD SOC at reg 105
        assert PV_SERIES_HOLDING_MAP.eod_soc is not None
        assert PV_SERIES_HOLDING_MAP.eod_soc.address == 105
        assert PV_SERIES_HOLDING_MAP.eod_soc.min_value == 10
        assert PV_SERIES_HOLDING_MAP.eod_soc.max_value == 90

        # AC charge SOC limit at reg 67
        assert PV_SERIES_HOLDING_MAP.ac_charge_soc_limit is not None
        assert PV_SERIES_HOLDING_MAP.ac_charge_soc_limit.address == 67

    def test_holding_map_generator_settings(self) -> None:
        """Test generator holding registers."""
        from pylxpweb.transports.register_maps import PV_SERIES_HOLDING_MAP

        # Gen rated power at reg 177
        assert PV_SERIES_HOLDING_MAP.gen_rated_power is not None
        assert PV_SERIES_HOLDING_MAP.gen_rated_power.address == 177

        # Gen charge start SOC at reg 196
        assert PV_SERIES_HOLDING_MAP.gen_charge_start_soc is not None
        assert PV_SERIES_HOLDING_MAP.gen_charge_start_soc.address == 196
        assert PV_SERIES_HOLDING_MAP.gen_charge_start_soc.min_value == 0
        assert PV_SERIES_HOLDING_MAP.gen_charge_start_soc.max_value == 90

    def test_holding_map_system_type(self) -> None:
        """Test system type (parallel config) holding register."""
        from pylxpweb.transports.register_maps import PV_SERIES_HOLDING_MAP

        # System type at reg 112
        assert PV_SERIES_HOLDING_MAP.system_type is not None
        assert PV_SERIES_HOLDING_MAP.system_type.address == 112
        assert PV_SERIES_HOLDING_MAP.system_type.min_value == 0
        assert PV_SERIES_HOLDING_MAP.system_type.max_value == 3

    def test_get_holding_map_function(self) -> None:
        """Test get_holding_map lookup function."""
        from pylxpweb.devices.inverters._features import InverterFamily
        from pylxpweb.transports.register_maps import (
            PV_SERIES_HOLDING_MAP,
            get_holding_map,
        )

        # Default returns PV_SERIES
        assert get_holding_map() is PV_SERIES_HOLDING_MAP
        assert get_holding_map(None) is PV_SERIES_HOLDING_MAP

        # PV_SERIES family
        assert get_holding_map(InverterFamily.PV_SERIES) is PV_SERIES_HOLDING_MAP

        # SNA uses same as PV_SERIES
        assert get_holding_map(InverterFamily.SNA) is PV_SERIES_HOLDING_MAP

    def test_lxp_eu_uses_same_holding_map(self) -> None:
        """Test that LXP_EU uses same holding map as PV_SERIES."""
        from pylxpweb.transports.register_maps import (
            LXP_EU_HOLDING_MAP,
            PV_SERIES_HOLDING_MAP,
        )

        assert LXP_EU_HOLDING_MAP is PV_SERIES_HOLDING_MAP


class TestParallelConfiguration:
    """Tests for parallel configuration parsing from register 113."""

    def test_parallel_config_register_defined(self) -> None:
        """Test that parallel_config is defined in runtime maps."""
        assert PV_SERIES_RUNTIME_MAP.parallel_config is not None
        assert PV_SERIES_RUNTIME_MAP.parallel_config.address == 113
        assert PV_SERIES_RUNTIME_MAP.parallel_config.bit_width == 16

    def test_parallel_config_no_parallel(self) -> None:
        """Test parsing parallel config when not in parallel mode."""
        from pylxpweb.transports.data import InverterRuntimeData

        # Register 113 = 0x0000: no parallel, phase R, unit 0
        registers = {113: 0x0000}

        result = InverterRuntimeData.from_modbus_registers(registers, PV_SERIES_RUNTIME_MAP)

        assert result.parallel_master_slave == 0  # No parallel
        assert result.parallel_phase == 0  # Phase R
        assert result.parallel_number == 0  # Unit 0

    def test_parallel_config_master(self) -> None:
        """Test parsing parallel config as master."""
        from pylxpweb.transports.data import InverterRuntimeData

        # Register 113 = 0x0101: master, phase R, unit 1
        # bits 0-1 = 1 (master), bits 2-3 = 0 (phase R), bits 8-15 = 1 (unit 1)
        registers = {113: 0x0101}

        result = InverterRuntimeData.from_modbus_registers(registers, PV_SERIES_RUNTIME_MAP)

        assert result.parallel_master_slave == 1  # Master
        assert result.parallel_phase == 0  # Phase R
        assert result.parallel_number == 1  # Unit 1

    def test_parallel_config_slave(self) -> None:
        """Test parsing parallel config as slave."""
        from pylxpweb.transports.data import InverterRuntimeData

        # Register 113 = 0x0202: slave, phase R, unit 2
        # bits 0-1 = 2 (slave), bits 2-3 = 0 (phase R), bits 8-15 = 2 (unit 2)
        registers = {113: 0x0202}

        result = InverterRuntimeData.from_modbus_registers(registers, PV_SERIES_RUNTIME_MAP)

        assert result.parallel_master_slave == 2  # Slave
        assert result.parallel_phase == 0  # Phase R
        assert result.parallel_number == 2  # Unit 2

    def test_parallel_config_three_phase_master(self) -> None:
        """Test parsing parallel config as 3-phase master."""
        from pylxpweb.transports.data import InverterRuntimeData

        # Register 113 = 0x0103: 3-phase master, phase R, unit 1
        # bits 0-1 = 3 (3-phase master), bits 2-3 = 0 (phase R), bits 8-15 = 1 (unit 1)
        registers = {113: 0x0103}

        result = InverterRuntimeData.from_modbus_registers(registers, PV_SERIES_RUNTIME_MAP)

        assert result.parallel_master_slave == 3  # 3-phase master
        assert result.parallel_phase == 0  # Phase R
        assert result.parallel_number == 1  # Unit 1

    def test_parallel_config_phase_s(self) -> None:
        """Test parsing parallel config with phase S."""
        from pylxpweb.transports.data import InverterRuntimeData

        # Register 113 = 0x0205: slave, phase S, unit 2
        # bits 0-1 = 1 (slave from 0x01 masked), but we have 0x05 = 0101
        # bits 0-1 = 1 (master), bits 2-3 = 1 (phase S), bits 8-15 = 2 (unit 2)
        # 0x0205 = 0000 0010 0000 0101
        registers = {113: 0x0205}

        result = InverterRuntimeData.from_modbus_registers(registers, PV_SERIES_RUNTIME_MAP)

        assert result.parallel_master_slave == 1  # bits 0-1 = 01 = master
        assert result.parallel_phase == 1  # bits 2-3 = 01 = phase S
        assert result.parallel_number == 2  # bits 8-15 = 2

    def test_parallel_config_phase_t(self) -> None:
        """Test parsing parallel config with phase T."""
        from pylxpweb.transports.data import InverterRuntimeData

        # Register 113 with phase T (bits 2-3 = 2)
        # 0x0309 = 0000 0011 0000 1001
        # bits 0-1 = 01 (master), bits 2-3 = 10 (phase T), bits 8-15 = 3 (unit 3)
        registers = {113: 0x0309}

        result = InverterRuntimeData.from_modbus_registers(registers, PV_SERIES_RUNTIME_MAP)

        assert result.parallel_master_slave == 1  # bits 0-1 = 01 = master
        assert result.parallel_phase == 2  # bits 2-3 = 10 = phase T
        assert result.parallel_number == 3  # bits 8-15 = 3
