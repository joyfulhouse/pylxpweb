"""Tests for data corruption detection in transport data classes.

Tests the ``is_corrupt()`` methods and ``_raw_soc``/``_raw_soh`` fields on
InverterRuntimeData, InverterEnergyData, BatteryData, BatteryBankData,
and MidboxRuntimeData.  These canary checks detect physically impossible
register values that indicate Modbus transaction ID desync or bad dongle data
(see: eg4_web_monitor issue #83).

Canary ranges (tuned 2026-02-13):
  - Grid frequency: 30-90 Hz (0 Hz is valid in off-grid/EPS mode)
  - SoC/SoH: must be <= 100
  - Battery voltage: must be <= 100V (no LFP exceeds 60V)
  - Smart port status: must be 0-2
  - ac_input_type: NOT checked (unreliable across firmware)
"""

from __future__ import annotations

from pylxpweb.transports.data import (
    BatteryBankData,
    BatteryData,
    InverterEnergyData,
    InverterRuntimeData,
    MidboxRuntimeData,
)


class TestInverterRuntimeDataCorruption:
    """Corruption detection for InverterRuntimeData."""

    def test_valid_data_not_corrupt(self) -> None:
        """is_corrupt() returns False for physically plausible values."""
        data = InverterRuntimeData(
            battery_soc=85,
            battery_soh=95,
            grid_frequency=60.0,
            ac_input_type=1,
        )
        assert data.is_corrupt() is False

    def test_raw_soc_above_100_is_corrupt(self) -> None:
        """is_corrupt() returns True when _raw_soc > 100 (e.g. battery_soc=144)."""
        data = InverterRuntimeData(battery_soc=144)
        assert data.is_corrupt() is True

    def test_raw_soh_above_100_is_corrupt(self) -> None:
        """is_corrupt() returns True when _raw_soh > 100 (e.g. battery_soh=200)."""
        data = InverterRuntimeData(battery_soh=200)
        assert data.is_corrupt() is True

    def test_grid_frequency_zero_not_corrupt(self) -> None:
        """is_corrupt() returns False when grid_frequency is 0 (off-grid/EPS mode)."""
        data = InverterRuntimeData(grid_frequency=0.0)
        assert data.is_corrupt() is False

    def test_grid_frequency_below_30_is_corrupt(self) -> None:
        """is_corrupt() returns True when grid_frequency is non-zero and < 30 Hz."""
        data = InverterRuntimeData(grid_frequency=15.0)
        assert data.is_corrupt() is True

    def test_grid_frequency_above_90_is_corrupt(self) -> None:
        """is_corrupt() returns True when grid_frequency > 90 Hz."""
        data = InverterRuntimeData(grid_frequency=255.0)
        assert data.is_corrupt() is True

    def test_grid_frequency_50hz_valid(self) -> None:
        """is_corrupt() returns False for 50 Hz grid (EU/Asia)."""
        data = InverterRuntimeData(grid_frequency=50.0)
        assert data.is_corrupt() is False

    def test_grid_frequency_60hz_valid(self) -> None:
        """is_corrupt() returns False for 60 Hz grid (US)."""
        data = InverterRuntimeData(grid_frequency=60.0)
        assert data.is_corrupt() is False

    def test_ac_input_type_not_checked(self) -> None:
        """ac_input_type is no longer a canary check (unreliable across firmware)."""
        data = InverterRuntimeData(ac_input_type=7)
        assert data.is_corrupt() is False

    def test_raw_soc_preserves_original_while_soc_clamped(self) -> None:
        """_raw_soc preserves the pre-clamp value while battery_soc is clamped to 100."""
        data = InverterRuntimeData(battery_soc=144)
        assert data._raw_soc == 144
        assert data.battery_soc == 100

    def test_raw_soh_preserves_original_while_soh_clamped(self) -> None:
        """_raw_soh preserves the pre-clamp value while battery_soh is clamped to 100."""
        data = InverterRuntimeData(battery_soh=200)
        assert data._raw_soh == 200
        assert data.battery_soh == 100

    def test_all_none_fields_not_corrupt(self) -> None:
        """is_corrupt() returns False when all fields are None (default construction)."""
        data = InverterRuntimeData()
        assert data.is_corrupt() is False


class TestInverterEnergyDataCorruption:
    """Corruption detection for InverterEnergyData."""

    def test_always_returns_false(self) -> None:
        """is_corrupt() always returns False (no physical canaries for energy)."""
        data = InverterEnergyData(
            pv_energy_today=100.0,
            charge_energy_today=50.0,
            grid_import_total=5000.0,
        )
        assert data.is_corrupt() is False

    def test_default_construction_not_corrupt(self) -> None:
        """is_corrupt() returns False for default-constructed energy data."""
        data = InverterEnergyData()
        assert data.is_corrupt() is False


class TestBatteryDataCorruption:
    """Corruption detection for BatteryData."""

    def test_valid_data_not_corrupt(self) -> None:
        """is_corrupt() returns False for valid battery data."""
        data = BatteryData(soc=50, soh=90, voltage=52.0)
        assert data.is_corrupt() is False

    def test_raw_soc_above_100_is_corrupt(self) -> None:
        """is_corrupt() returns True when _raw_soc > 100."""
        data = BatteryData(soc=144)
        assert data.is_corrupt() is True

    def test_raw_soh_above_100_is_corrupt(self) -> None:
        """is_corrupt() returns True when _raw_soh > 100."""
        data = BatteryData(soh=200)
        assert data.is_corrupt() is True

    def test_voltage_above_100_is_corrupt(self) -> None:
        """is_corrupt() returns True when voltage > 100.0V (no LFP exceeds 60V)."""
        data = BatteryData(voltage=655.35)
        assert data.is_corrupt() is True

    def test_raw_soc_preserves_pre_clamp_value(self) -> None:
        """_raw_soc preserves the original value before clamping."""
        data = BatteryData(soc=144)
        assert data._raw_soc == 144
        assert data.soc == 100

    # --- Cell voltage canary checks (issue #166) ---

    def test_max_cell_voltage_above_5v_is_corrupt(self) -> None:
        """is_corrupt() returns True when max_cell_voltage > 5.0V (0xFFFF/1000 = 65.535V)."""
        data = BatteryData(soc=50, soh=90, voltage=52.0, max_cell_voltage=65.535)
        assert data.is_corrupt() is True

    def test_min_cell_voltage_above_5v_is_corrupt(self) -> None:
        """is_corrupt() returns True when min_cell_voltage > 5.0V."""
        data = BatteryData(soc=50, soh=90, voltage=52.0, min_cell_voltage=65.535)
        assert data.is_corrupt() is True

    def test_max_cell_voltage_below_1v_nonzero_is_corrupt(self) -> None:
        """is_corrupt() True when max_cell_voltage nonzero but < 1.0V."""
        data = BatteryData(soc=50, soh=90, voltage=52.0, max_cell_voltage=0.3)
        assert data.is_corrupt() is True

    def test_min_cell_voltage_below_1v_nonzero_is_corrupt(self) -> None:
        """is_corrupt() returns True when min_cell_voltage is nonzero but < 1.0V."""
        data = BatteryData(soc=50, soh=90, voltage=52.0, min_cell_voltage=0.1)
        assert data.is_corrupt() is True

    def test_cell_voltage_zero_not_corrupt(self) -> None:
        """is_corrupt() returns False when cell voltage is 0.0 (no data / absent)."""
        data = BatteryData(soc=50, soh=90, voltage=52.0, max_cell_voltage=0.0, min_cell_voltage=0.0)
        assert data.is_corrupt() is False

    def test_cell_voltage_normal_lfp_not_corrupt(self) -> None:
        """is_corrupt() returns False for typical LFP cell voltages (3.2-3.4V)."""
        data = BatteryData(
            soc=50,
            soh=90,
            voltage=52.0,
            max_cell_voltage=3.365,
            min_cell_voltage=3.310,
        )
        assert data.is_corrupt() is False

    def test_cell_voltage_at_upper_bound_not_corrupt(self) -> None:
        """is_corrupt() returns False for cell voltage at 5.0V (boundary)."""
        data = BatteryData(soc=50, soh=90, voltage=52.0, max_cell_voltage=5.0)
        assert data.is_corrupt() is False

    def test_cell_voltage_at_lower_bound_not_corrupt(self) -> None:
        """is_corrupt() returns False for cell voltage at 1.0V (boundary)."""
        data = BatteryData(soc=50, soh=90, voltage=52.0, min_cell_voltage=1.0)
        assert data.is_corrupt() is False

    def test_min_cell_exceeds_max_cell_is_corrupt(self) -> None:
        """is_corrupt() returns True when min_cell_voltage > max_cell_voltage (inversion)."""
        data = BatteryData(
            soc=50,
            soh=90,
            voltage=52.0,
            max_cell_voltage=3.300,
            min_cell_voltage=3.400,
        )
        assert data.is_corrupt() is True

    def test_min_equals_max_cell_not_corrupt(self) -> None:
        """is_corrupt() False when min == max cell voltage (balanced)."""
        data = BatteryData(
            soc=50,
            soh=90,
            voltage=52.0,
            max_cell_voltage=3.350,
            min_cell_voltage=3.350,
        )
        assert data.is_corrupt() is False

    def test_cell_inversion_check_skipped_when_zero(self) -> None:
        """Inversion check skipped when either cell voltage is 0 (no data)."""
        data = BatteryData(
            soc=50,
            soh=90,
            voltage=52.0,
            max_cell_voltage=0.0,
            min_cell_voltage=3.300,
        )
        # max=0 means no data, so inversion check should not fire
        assert data.is_corrupt() is False


class TestBatteryBankDataCorruption:
    """Corruption detection for BatteryBankData."""

    def test_valid_bank_not_corrupt(self) -> None:
        """is_corrupt() returns False for valid battery bank data."""
        data = BatteryBankData(
            soc=85,
            soh=95,
            voltage=53.0,
            batteries=[
                BatteryData(soc=85, soh=95, voltage=53.0),
                BatteryData(soc=86, soh=96, voltage=53.1),
            ],
        )
        assert data.is_corrupt() is False

    def test_bank_raw_soc_above_100_is_corrupt(self) -> None:
        """is_corrupt() returns True when bank _raw_soc > 100."""
        data = BatteryBankData(soc=144, soh=95)
        assert data.is_corrupt() is True

    def test_child_battery_corrupt_cascades(self) -> None:
        """is_corrupt() returns True when any child BatteryData is corrupt."""
        corrupt_battery = BatteryData(soc=144, voltage=52.0)
        data = BatteryBankData(
            soc=85,
            soh=95,
            batteries=[
                BatteryData(soc=50, soh=90, voltage=52.0),
                corrupt_battery,
            ],
        )
        assert data.is_corrupt() is True

    def test_ghost_battery_skipped_in_cascade(self) -> None:
        """is_corrupt() skips ghost batteries (voltage=0, soc=0) in cascade check."""
        ghost = BatteryData(soc=0, soh=0, voltage=0.0)
        data = BatteryBankData(
            soc=85,
            soh=95,
            batteries=[
                BatteryData(soc=50, soh=90, voltage=52.0),
                ghost,
            ],
        )
        assert data.is_corrupt() is False

    def test_empty_batteries_with_valid_bank_soc_not_corrupt(self) -> None:
        """is_corrupt() returns False for empty batteries list with valid bank SoC/SoH."""
        data = BatteryBankData(soc=85, soh=95, batteries=[])
        assert data.is_corrupt() is False

    def test_battery_count_above_20_is_corrupt(self) -> None:
        """is_corrupt() returns True when battery_count exceeds physical maximum."""
        data = BatteryBankData(soc=85, soh=95, battery_count=5421)
        assert data.is_corrupt() is True

    def test_battery_count_at_boundary_not_corrupt(self) -> None:
        """is_corrupt() returns False for battery_count at upper bound (20)."""
        data = BatteryBankData(soc=85, soh=95, battery_count=20)
        assert data.is_corrupt() is False

    def test_battery_count_none_not_corrupt(self) -> None:
        """is_corrupt() returns False when battery_count is None."""
        data = BatteryBankData(soc=85, soh=95, battery_count=None)
        assert data.is_corrupt() is False

    def test_battery_current_above_500_is_corrupt(self) -> None:
        """is_corrupt() returns True when abs(current) exceeds 500A."""
        data = BatteryBankData(soc=85, soh=95, current=2996.0)
        assert data.is_corrupt() is True

    def test_battery_current_negative_above_500_is_corrupt(self) -> None:
        """is_corrupt() returns True for large negative current (discharging)."""
        data = BatteryBankData(soc=85, soh=95, current=-600.0)
        assert data.is_corrupt() is True

    def test_battery_current_at_boundary_not_corrupt(self) -> None:
        """is_corrupt() returns False for current at 500A boundary."""
        data = BatteryBankData(soc=85, soh=95, current=500.0)
        assert data.is_corrupt() is False

    def test_battery_current_none_not_corrupt(self) -> None:
        """is_corrupt() returns False when current is None."""
        data = BatteryBankData(soc=85, soh=95, current=None)
        assert data.is_corrupt() is False


class TestMidboxRuntimeDataCorruption:
    """Corruption detection for MidboxRuntimeData."""

    def test_valid_data_not_corrupt(self) -> None:
        """is_corrupt() returns False for valid GridBOSS data."""
        data = MidboxRuntimeData(
            grid_frequency=60.0,
            smart_port_1_status=0,
            smart_port_2_status=1,
            smart_port_3_status=2,
            smart_port_4_status=0,
        )
        assert data.is_corrupt() is False

    def test_grid_frequency_zero_not_corrupt(self) -> None:
        """is_corrupt() returns False when grid_frequency is 0 (off-grid/EPS mode)."""
        data = MidboxRuntimeData(grid_frequency=0.0)
        assert data.is_corrupt() is False

    def test_grid_frequency_below_30_is_corrupt(self) -> None:
        """is_corrupt() returns True when grid_frequency is non-zero and < 30 Hz."""
        data = MidboxRuntimeData(grid_frequency=15.0)
        assert data.is_corrupt() is True

    def test_grid_frequency_above_90_is_corrupt(self) -> None:
        """is_corrupt() returns True when grid_frequency > 90 Hz."""
        data = MidboxRuntimeData(grid_frequency=255.0)
        assert data.is_corrupt() is True

    def test_smart_port_status_above_2_is_corrupt(self) -> None:
        """is_corrupt() returns True when any smart_port_N_status > 2."""
        data = MidboxRuntimeData(smart_port_1_status=7)
        assert data.is_corrupt() is True

    def test_smart_port_2_status_above_2_is_corrupt(self) -> None:
        """is_corrupt() detects corruption on any of the four smart ports."""
        data = MidboxRuntimeData(smart_port_2_status=5)
        assert data.is_corrupt() is True

    def test_smart_port_3_status_above_2_is_corrupt(self) -> None:
        """is_corrupt() detects corruption on smart port 3."""
        data = MidboxRuntimeData(smart_port_3_status=3)
        assert data.is_corrupt() is True

    def test_smart_port_4_status_above_2_is_corrupt(self) -> None:
        """is_corrupt() detects corruption on smart port 4."""
        data = MidboxRuntimeData(smart_port_4_status=4)
        assert data.is_corrupt() is True

    def test_all_none_fields_not_corrupt(self) -> None:
        """is_corrupt() returns False when all fields are None (default construction)."""
        data = MidboxRuntimeData()
        assert data.is_corrupt() is False

    # --- Grid voltage canary checks (#162: ghost voltage tolerance) ---

    def test_grid_voltage_zero_not_corrupt(self) -> None:
        """is_corrupt() returns False when grid voltage is 0V (grid down)."""
        data = MidboxRuntimeData(grid_l1_voltage=0.0, grid_l2_voltage=0.0)
        assert data.is_corrupt() is False

    def test_ghost_voltage_not_corrupt(self) -> None:
        """is_corrupt() returns False for ghost/leakage voltage on disconnected CTs (#162).

        Disconnected grid/gen CT inputs produce ~0.5-1.5V from electromagnetic
        coupling.  These are physically real and should not trigger rejection.
        """
        data = MidboxRuntimeData(grid_l1_voltage=0.8, grid_l2_voltage=0.7)
        assert data.is_corrupt() is False

    def test_ghost_voltage_up_to_5v_not_corrupt(self) -> None:
        """is_corrupt() tolerates ghost voltages up to 5V (generous margin)."""
        data = MidboxRuntimeData(grid_l1_voltage=4.9, grid_l2_voltage=5.0)
        assert data.is_corrupt() is False

    def test_grid_voltage_mid_range_is_corrupt(self) -> None:
        """is_corrupt() returns True for voltage in impossible 5-50V range."""
        data = MidboxRuntimeData(grid_l1_voltage=25.0)
        assert data.is_corrupt() is True

    def test_grid_l2_voltage_mid_range_is_corrupt(self) -> None:
        """is_corrupt() detects corruption on L2 voltage."""
        data = MidboxRuntimeData(grid_l2_voltage=40.0)
        assert data.is_corrupt() is True

    def test_grid_voltage_above_300_is_corrupt(self) -> None:
        """is_corrupt() returns True for voltage > 300V (0xFFFF/10 = 6553.5V)."""
        data = MidboxRuntimeData(grid_l1_voltage=6553.5)
        assert data.is_corrupt() is True

    def test_grid_voltage_normal_120v_not_corrupt(self) -> None:
        """is_corrupt() returns False for normal US split-phase voltage."""
        data = MidboxRuntimeData(grid_l1_voltage=120.5, grid_l2_voltage=121.0)
        assert data.is_corrupt() is False

    def test_grid_voltage_normal_240v_not_corrupt(self) -> None:
        """is_corrupt() returns False for normal 240V (non-US or L-L)."""
        data = MidboxRuntimeData(grid_l1_voltage=240.0, grid_l2_voltage=241.0)
        assert data.is_corrupt() is False


class TestInverterPowerCanary:
    """Power canary checks for InverterRuntimeData.

    When max_power_watts > 0 (rated power known), key power fields are
    checked against the threshold.  Corrupt 16-bit reads produce 0xFFFF
    = 65535W, which exceeds 2x rated for all EG4 models (6-21 kW).
    """

    def test_power_check_skipped_when_zero(self) -> None:
        """Power checks skipped when max_power_watts=0 (rated power unknown)."""
        data = InverterRuntimeData(pv_total_power=65535.0)
        assert data.is_corrupt(max_power_watts=0.0) is False

    def test_pv_power_exceeds_max(self) -> None:
        """Corrupt PV power (0xFFFF=65535W) detected for 18kW inverter."""
        data = InverterRuntimeData(pv_total_power=65535.0)
        assert data.is_corrupt(max_power_watts=36000.0) is True  # 18kW * 2

    def test_battery_charge_power_exceeds_max(self) -> None:
        """Corrupt battery charge power detected."""
        data = InverterRuntimeData(battery_charge_power=65535.0)
        assert data.is_corrupt(max_power_watts=36000.0) is True

    def test_battery_discharge_power_exceeds_max(self) -> None:
        """Corrupt battery discharge power detected."""
        data = InverterRuntimeData(battery_discharge_power=65535.0)
        assert data.is_corrupt(max_power_watts=36000.0) is True

    def test_inverter_power_exceeds_max(self) -> None:
        """Corrupt inverter power detected."""
        data = InverterRuntimeData(inverter_power=65535.0)
        assert data.is_corrupt(max_power_watts=36000.0) is True

    def test_eps_power_exceeds_max(self) -> None:
        """Corrupt EPS power detected."""
        data = InverterRuntimeData(eps_power=65535.0)
        assert data.is_corrupt(max_power_watts=36000.0) is True

    def test_valid_power_under_threshold(self) -> None:
        """Normal power readings pass when under max threshold."""
        data = InverterRuntimeData(
            pv_total_power=15000.0,
            battery_charge_power=8000.0,
            inverter_power=18000.0,
        )
        assert data.is_corrupt(max_power_watts=36000.0) is False

    def test_negative_power_within_threshold(self) -> None:
        """Negative power (grid export) passes when abs value under threshold."""
        data = InverterRuntimeData(inverter_power=-15000.0)
        assert data.is_corrupt(max_power_watts=36000.0) is False

    def test_negative_power_exceeds_threshold(self) -> None:
        """Large negative power (corruption) detected via abs()."""
        data = InverterRuntimeData(inverter_power=-65535.0)
        assert data.is_corrupt(max_power_watts=36000.0) is True

    def test_6kw_inverter_catches_corrupt(self) -> None:
        """Smallest inverter (6kW, threshold=12000W) catches 0xFFFF."""
        data = InverterRuntimeData(pv_total_power=65535.0)
        assert data.is_corrupt(max_power_watts=12000.0) is True  # 6kW * 2


class TestMidboxPowerCanary:
    """Power canary checks for MidboxRuntimeData.

    When max_power_watts > 0 (system power known), per-leg power fields
    are checked against the threshold.
    """

    def test_power_check_skipped_when_zero(self) -> None:
        """Power checks skipped when max_power_watts=0 (system power unknown)."""
        data = MidboxRuntimeData(grid_l1_power=65535.0)
        assert data.is_corrupt(max_power_watts=0.0) is False

    def test_grid_l1_power_exceeds_max(self) -> None:
        """Corrupt grid L1 power detected."""
        data = MidboxRuntimeData(grid_l1_power=65535.0)
        assert data.is_corrupt(max_power_watts=58000.0) is True  # 2*18+21=57kW

    def test_grid_l2_power_exceeds_max(self) -> None:
        """Corrupt grid L2 power detected."""
        data = MidboxRuntimeData(grid_l2_power=65535.0)
        assert data.is_corrupt(max_power_watts=58000.0) is True

    def test_load_l1_power_exceeds_max(self) -> None:
        """Corrupt load L1 power detected."""
        data = MidboxRuntimeData(load_l1_power=65535.0)
        assert data.is_corrupt(max_power_watts=58000.0) is True

    def test_ups_l1_power_exceeds_max(self) -> None:
        """Corrupt UPS L1 power detected."""
        data = MidboxRuntimeData(ups_l1_power=65535.0)
        assert data.is_corrupt(max_power_watts=58000.0) is True

    def test_valid_power_under_threshold(self) -> None:
        """Normal GridBOSS power readings pass."""
        data = MidboxRuntimeData(
            grid_l1_power=5000.0,
            grid_l2_power=4000.0,
            load_l1_power=3000.0,
            load_l2_power=2000.0,
        )
        assert data.is_corrupt(max_power_watts=58000.0) is False

    def test_negative_power_within_threshold(self) -> None:
        """Negative grid power (export) passes when abs under threshold."""
        data = MidboxRuntimeData(grid_l1_power=-15000.0)
        assert data.is_corrupt(max_power_watts=58000.0) is False

    def test_negative_power_exceeds_threshold(self) -> None:
        """Large negative power (corruption) detected via abs()."""
        data = MidboxRuntimeData(grid_l1_power=-65535.0)
        assert data.is_corrupt(max_power_watts=58000.0) is True
