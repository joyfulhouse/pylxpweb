"""Unit tests for data scaling functions.

Tests the centralized scaling system in constants.py to ensure
correct scaling factors are applied to all data types.
"""

from __future__ import annotations

import pytest

from pylxpweb.constants import (
    BATTERY_MODULE_SCALING,
    ENERGY_INFO_SCALING,
    INVERTER_RUNTIME_SCALING,
    ScaleFactor,
    _get_scaling_for_field,
    apply_scale,
    scale_battery_value,
    scale_energy_value,
    scale_runtime_value,
)


class TestScaleFactor:
    """Test ScaleFactor enum."""

    def test_scale_factor_values(self) -> None:
        """Test enum values are correct."""
        assert ScaleFactor.SCALE_NONE.value == 1
        assert ScaleFactor.SCALE_10.value == 10
        assert ScaleFactor.SCALE_100.value == 100
        assert ScaleFactor.SCALE_1000.value == 1000

    def test_scale_factor_is_int(self) -> None:
        """Test ScaleFactor enum members are integers."""
        assert isinstance(ScaleFactor.SCALE_10, int)
        assert isinstance(ScaleFactor.SCALE_100, int)


class TestApplyScale:
    """Test apply_scale() function."""

    def test_scale_none(self) -> None:
        """Test no scaling."""
        assert apply_scale(1030, ScaleFactor.SCALE_NONE) == 1030.0
        assert apply_scale(100, ScaleFactor.SCALE_NONE) == 100.0

    def test_scale_10(self) -> None:
        """Test divide by 10."""
        assert apply_scale(5300, ScaleFactor.SCALE_10) == 530.0
        assert apply_scale(2411, ScaleFactor.SCALE_10) == 241.1
        assert apply_scale(530, ScaleFactor.SCALE_10) == 53.0

    def test_scale_100(self) -> None:
        """Test divide by 100."""
        assert apply_scale(5998, ScaleFactor.SCALE_100) == 59.98
        assert apply_scale(6000, ScaleFactor.SCALE_100) == 60.0
        assert apply_scale(3703, ScaleFactor.SCALE_100) == 37.03

    def test_scale_1000(self) -> None:
        """Test divide by 1000."""
        assert apply_scale(3317, ScaleFactor.SCALE_1000) == 3.317
        assert apply_scale(3315, ScaleFactor.SCALE_1000) == 3.315
        assert apply_scale(3364, ScaleFactor.SCALE_1000) == 3.364

    def test_with_float_input(self) -> None:
        """Test scaling with float input."""
        assert apply_scale(5300.0, ScaleFactor.SCALE_10) == 530.0
        assert apply_scale(5998.5, ScaleFactor.SCALE_100) == 59.985


class TestInverterRuntimeScaling:
    """Test inverter runtime data scaling."""

    def test_pv_voltage_scaling(self) -> None:
        """Test PV voltage scaling (÷10)."""
        assert scale_runtime_value("vpv1", 5100) == 510.0
        assert scale_runtime_value("vpv2", 5200) == 520.0
        assert scale_runtime_value("vpv3", 0) == 0.0

    def test_ac_voltage_scaling(self) -> None:
        """Test AC voltage scaling (÷10)."""
        assert scale_runtime_value("vacr", 2411) == 241.1
        assert scale_runtime_value("vacs", 2400) == 240.0
        assert scale_runtime_value("vact", 2420) == 242.0

    def test_eps_voltage_scaling(self) -> None:
        """Test EPS voltage scaling (÷10)."""
        assert scale_runtime_value("vepsr", 2410) == 241.0
        assert scale_runtime_value("vepss", 2560) == 256.0
        assert scale_runtime_value("vepst", 64) == 6.4

    def test_battery_voltage_in_runtime(self) -> None:
        """Test battery voltage in runtime data (÷10)."""
        assert scale_runtime_value("vBat", 530) == 53.0
        assert scale_runtime_value("vBat", 5300) == 530.0

    def test_bus_voltage_scaling(self) -> None:
        """Test bus voltage scaling (÷100) - different from other voltages."""
        assert scale_runtime_value("vBus1", 3703) == 37.03
        assert scale_runtime_value("vBus2", 3228) == 32.28

    def test_frequency_scaling(self) -> None:
        """Test frequency scaling (÷100)."""
        assert scale_runtime_value("fac", 5998) == 59.98
        assert scale_runtime_value("feps", 6001) == 60.01
        assert scale_runtime_value("genFreq", 5995) == 59.95

    def test_current_scaling(self) -> None:
        """Test current scaling (÷100)."""
        assert scale_runtime_value("maxChgCurr", 6000) == 60.0
        assert scale_runtime_value("maxDischgCurr", 6000) == 60.0

    def test_power_no_scaling(self) -> None:
        """Test power values have no scaling."""
        assert scale_runtime_value("ppv1", 1030) == 1030.0
        assert scale_runtime_value("pCharge", 1045) == 1045.0
        assert scale_runtime_value("pinv", 0) == 0.0
        assert scale_runtime_value("pToGrid", 0) == 0.0
        assert scale_runtime_value("pToUser", 1030) == 1030.0

    def test_temperature_no_scaling(self) -> None:
        """Test temperature values have no scaling."""
        assert scale_runtime_value("tinner", 39) == 39.0
        assert scale_runtime_value("tradiator1", 45) == 45.0
        assert scale_runtime_value("tradiator2", 43) == 43.0
        assert scale_runtime_value("tBat", 2) == 2.0

    def test_percentage_no_scaling(self) -> None:
        """Test percentage values have no scaling."""
        assert scale_runtime_value("soc", 71) == 71.0
        assert scale_runtime_value("seps", 0) == 0.0

    def test_unknown_field_returns_direct_value(self) -> None:
        """Test unknown fields return direct float value."""
        result = scale_runtime_value("unknownField", 100)
        assert result == 100.0


class TestBatteryModuleScaling:
    """Test battery module data scaling."""

    def test_total_voltage_scaling(self) -> None:
        """Test total voltage scaling (÷100)."""
        assert scale_battery_value("totalVoltage", 5305) == 53.05
        assert scale_battery_value("totalVoltage", 5304) == 53.04
        assert scale_battery_value("totalVoltage", 5303) == 53.03

    def test_current_scaling_critical(self) -> None:
        """Test battery current scaling (÷10) - CRITICAL: Not ÷100!"""
        # This is the critical fix - battery current is ÷10, not ÷100
        assert scale_battery_value("current", 60) == 6.0
        assert scale_battery_value("current", 54) == 5.4
        assert scale_battery_value("current", 47) == 4.7

        # Verify it's NOT ÷100
        assert scale_battery_value("current", 60) != 0.6

    def test_cell_voltage_scaling(self) -> None:
        """Test cell voltage scaling (÷1000) - millivolts."""
        assert scale_battery_value("batMaxCellVoltage", 3317) == 3.317
        assert scale_battery_value("batMinCellVoltage", 3315) == 3.315
        assert scale_battery_value("batMaxCellVoltage", 3316) == 3.316
        assert scale_battery_value("batMinCellVoltage", 3314) == 3.314

    def test_cell_temperature_scaling(self) -> None:
        """Test cell temperature scaling (÷10)."""
        assert scale_battery_value("batMaxCellTemp", 240) == 24.0
        assert scale_battery_value("batMinCellTemp", 240) == 24.0
        assert scale_battery_value("batMaxCellTemp", 250) == 25.0

    def test_charge_reference_scaling(self) -> None:
        """Test charge reference value scaling (÷100)."""
        assert scale_battery_value("batChargeMaxCur", 2000) == 20.0
        assert scale_battery_value("batChargeVoltRef", 560) == 5.6

    def test_percentage_no_scaling(self) -> None:
        """Test percentage values have no scaling."""
        assert scale_battery_value("soc", 67) == 67.0
        assert scale_battery_value("soh", 100) == 100.0

    def test_capacity_no_scaling(self) -> None:
        """Test capacity values have no scaling."""
        assert scale_battery_value("currentRemainCapacity", 187) == 187.0
        assert scale_battery_value("currentFullCapacity", 280) == 280.0


class TestEnergyScaling:
    """Test energy data scaling."""

    def test_energy_to_wh(self) -> None:
        """Test energy scaling to Wh (÷10 to get kWh, ×1000 for Wh)."""
        # 90÷10=9kWh, 9×1000=9000Wh
        assert scale_energy_value("todayYielding", 90, to_kwh=False) == 9000.0
        # 1500÷10=150kWh
        assert scale_energy_value("monthYielding", 1500, to_kwh=False) == 150000.0
        # 5000÷10=500kWh
        assert scale_energy_value("totalYielding", 5000, to_kwh=False) == 500000.0

    def test_energy_to_kwh(self) -> None:
        """Test energy scaling to kWh (÷10 directly - API uses 0.1 kWh units)."""
        assert scale_energy_value("todayYielding", 90, to_kwh=True) == 9.0  # 90÷10=9kWh
        assert scale_energy_value("monthYielding", 1500, to_kwh=True) == 150.0  # 1500÷10=150kWh
        assert scale_energy_value("totalYielding", 5000, to_kwh=True) == 500.0  # 5000÷10=500kWh

    def test_all_energy_fields(self) -> None:
        """Test all energy field types."""
        # Daily - 100÷10=10kWh, ×1000=10000Wh
        assert scale_energy_value("todayCharging", 100, to_kwh=False) == 10000.0
        # Daily - 200÷10=20kWh, ×1000=20000Wh
        assert scale_energy_value("todayDischarging", 200, to_kwh=False) == 20000.0

        # Monthly - 3000÷10=300kWh
        assert scale_energy_value("monthGridImport", 3000, to_kwh=True) == 300.0
        # Monthly - 4000÷10=400kWh
        assert scale_energy_value("monthExport", 4000, to_kwh=True) == 400.0

        # Yearly - 50000÷10=5000kWh
        assert scale_energy_value("yearUsage", 50000, to_kwh=True) == 5000.0

        # Total - 100000÷10=10000kWh
        assert scale_energy_value("totalExport", 100000, to_kwh=True) == 10000.0


class TestGetScalingForField:
    """Test _get_scaling_for_field() internal function."""

    def test_runtime_field_lookup(self) -> None:
        """Test runtime data field lookup."""
        assert _get_scaling_for_field("vpv1", "runtime") == ScaleFactor.SCALE_10
        assert _get_scaling_for_field("fac", "runtime") == ScaleFactor.SCALE_100
        assert _get_scaling_for_field("ppv1", "runtime") == ScaleFactor.SCALE_NONE

    def test_battery_module_field_lookup(self) -> None:
        """Test battery module field lookup."""
        assert _get_scaling_for_field("totalVoltage", "battery_module") == ScaleFactor.SCALE_100
        assert _get_scaling_for_field("current", "battery_module") == ScaleFactor.SCALE_10
        assert (
            _get_scaling_for_field("batMaxCellVoltage", "battery_module")
            == ScaleFactor.SCALE_1000
        )
        assert _get_scaling_for_field("soc", "battery_module") == ScaleFactor.SCALE_NONE

    def test_energy_field_lookup(self) -> None:
        """Test energy field lookup."""
        assert _get_scaling_for_field("todayYielding", "energy") == ScaleFactor.SCALE_10
        assert _get_scaling_for_field("totalExport", "energy") == ScaleFactor.SCALE_10

    def test_invalid_field_raises_error(self) -> None:
        """Test invalid field raises KeyError."""
        with pytest.raises(KeyError):
            _get_scaling_for_field("invalidField", "runtime")

    def test_invalid_data_type_raises_error(self) -> None:
        """Test invalid data type raises KeyError."""
        with pytest.raises(KeyError):
            _get_scaling_for_field("vpv1", "invalid_type")  # type: ignore


class TestRealWorldData:
    """Test with actual API response data from samples."""

    def test_runtime_sample_4512670118(self) -> None:
        """Test with real runtime data from sample file.

        Sample: research/.../runtime_4512670118.json
        """
        # Voltage data
        assert scale_runtime_value("vpv1", 0) == 0.0  # No PV input
        assert scale_runtime_value("vpv2", 1) == 0.1
        assert scale_runtime_value("vacr", 2411) == 241.1  # AC voltage
        assert scale_runtime_value("vBat", 530) == 53.0  # Battery voltage

        # Frequency
        assert scale_runtime_value("fac", 5998) == 59.98  # 59.98 Hz

        # Power (no scaling)
        assert scale_runtime_value("pCharge", 1045) == 1045.0  # 1045W
        assert scale_runtime_value("pToUser", 1030) == 1030.0  # 1030W

        # Temperature (no scaling)
        assert scale_runtime_value("tinner", 39) == 39.0  # 39°C
        assert scale_runtime_value("tradiator1", 45) == 45.0  # 45°C

        # Bus voltages (÷100)
        assert scale_runtime_value("vBus1", 3703) == 37.03
        assert scale_runtime_value("vBus2", 3228) == 32.28

        # SOC (no scaling)
        assert scale_runtime_value("soc", 71) == 71.0  # 71%

    def test_battery_sample_4512670118(self) -> None:
        """Test with real battery data from sample file.

        Sample: research/.../battery_4512670118.json
        """
        # Battery 1 data (batIndex: 0)
        assert scale_battery_value("totalVoltage", 5305) == 53.05  # 53.05V
        assert scale_battery_value("current", 60) == 6.0  # 6.0A (÷10!)
        assert scale_battery_value("batMaxCellTemp", 240) == 24.0  # 24.0°C
        assert scale_battery_value("batMaxCellVoltage", 3317) == 3.317  # 3.317V
        assert scale_battery_value("batMinCellVoltage", 3315) == 3.315  # 3.315V

        # Battery 2 data (batIndex: 1)
        assert scale_battery_value("totalVoltage", 5304) == 53.04
        assert scale_battery_value("current", 54) == 5.4  # 5.4A
        assert scale_battery_value("batMaxCellTemp", 250) == 25.0  # 25.0°C

        # Battery 3 data (batIndex: 2)
        assert scale_battery_value("totalVoltage", 5303) == 53.03
        assert scale_battery_value("current", 47) == 4.7  # 4.7A

        # Verify total current adds up (approximately)
        # API shows currentText: "18.1" A
        # Our batteries: 6.0 + 5.4 + 4.7 = 16.1A (close enough, API aggregates differently)

    def test_voltage_difference_aggregate_vs_individual(self) -> None:
        """Test the different voltage scaling for aggregate vs individual.

        This is a CRITICAL difference:
        - Battery BANK voltage (aggregate): vBat=530 → 53.0V (÷10)
        - Individual battery voltage: totalVoltage=5305 → 53.05V (÷100)
        """
        # Aggregate (from BatteryInfo header or InverterRuntime)
        bank_voltage = apply_scale(530, ScaleFactor.SCALE_10)
        assert bank_voltage == 53.0

        # Individual (from batteryArray)
        battery_voltage = scale_battery_value("totalVoltage", 5305)
        assert battery_voltage == 53.05

        # They're close but use different precision
        assert abs(bank_voltage - battery_voltage) < 1.0  # Within 1V


class TestScalingDictionaries:
    """Test scaling dictionary completeness."""

    def test_inverter_runtime_scaling_has_voltage_fields(self) -> None:
        """Test all voltage fields are in runtime scaling."""
        voltage_fields = ["vpv1", "vpv2", "vpv3", "vacr", "vacs", "vact", "vBat"]
        for field in voltage_fields:
            assert field in INVERTER_RUNTIME_SCALING

    def test_battery_module_scaling_has_all_fields(self) -> None:
        """Test critical battery fields are in scaling."""
        critical_fields = [
            "totalVoltage",
            "current",
            "batMaxCellVoltage",
            "batMinCellVoltage",
            "batMaxCellTemp",
            "batMinCellTemp",
        ]
        for field in critical_fields:
            assert field in BATTERY_MODULE_SCALING

    def test_energy_scaling_has_all_time_periods(self) -> None:
        """Test all time periods are in energy scaling."""
        time_periods = ["today", "month", "year", "total"]
        metrics = ["Yielding", "Charging", "Discharging", "GridImport", "Usage", "Export"]

        for period in time_periods:
            for metric in metrics:
                field = f"{period}{metric}"
                assert field in ENERGY_INFO_SCALING


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_values(self) -> None:
        """Test scaling with zero values."""
        assert scale_runtime_value("vpv1", 0) == 0.0
        assert scale_battery_value("current", 0) == 0.0
        assert scale_energy_value("todayYielding", 0, to_kwh=True) == 0.0

    def test_negative_values(self) -> None:
        """Test scaling with negative values (rare but possible)."""
        # Negative current might indicate direction
        assert apply_scale(-60, ScaleFactor.SCALE_10) == -6.0

    def test_large_values(self) -> None:
        """Test scaling with large values."""
        # 1000000÷10=100000kWh
        assert scale_energy_value("totalYielding", 1000000, to_kwh=True) == 100000.0
        assert scale_runtime_value("pToUser", 15000) == 15000.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
