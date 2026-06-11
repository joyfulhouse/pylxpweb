"""Tests for transport-agnostic data models."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from pylxpweb.models import EnergyInfo, InverterRuntime, MidboxData
from pylxpweb.transports.data import (
    BatteryBankData,
    BatteryData,
    InverterEnergyData,
    InverterRuntimeData,
    MidboxRuntimeData,
)


class TestInverterRuntimeData:
    """Tests for InverterRuntimeData dataclass."""

    def test_default_values(self) -> None:
        """Test that default values are None (unavailable).

        Fields default to None to indicate data is unavailable, which allows
        Home Assistant to show "unavailable" state rather than recording false
        zero values in history graphs. See: eg4_web_monitor issue #91
        """
        data = InverterRuntimeData()

        # All numeric fields default to None (unavailable)
        assert data.pv_total_power is None
        assert data.battery_soc is None
        assert data.grid_frequency is None
        assert data.device_status is None
        assert isinstance(data.timestamp, datetime)

    def test_from_http_response(self) -> None:
        """Test conversion from HTTP API response."""
        # Create a mock InverterRuntime with test data
        runtime = MagicMock(spec=InverterRuntime)
        runtime.vpv1 = 5100  # 510.0V after /10 scaling
        runtime.vpv2 = 5050
        runtime.vpv3 = None
        runtime.vpv4 = None
        runtime.vpv5 = None
        runtime.vpv6 = None
        runtime.ppv1 = 1000
        runtime.ppv2 = 1500
        runtime.ppv3 = None
        runtime.ppv4 = None
        runtime.ppv5 = None
        runtime.ppv6 = None
        runtime.ppv = 2500
        runtime.vBat = 530  # 53.0V after /10 scaling
        runtime.soc = 85
        runtime.pCharge = 500
        runtime.pDisCharge = 0
        runtime.tBat = 25
        runtime.vacr = 2410  # 241.0V
        runtime.vacs = 2415
        runtime.vact = 2420
        runtime.fac = 5998  # 59.98Hz after /100 scaling
        runtime.prec = 100
        runtime.pToGrid = 200
        runtime.pinv = 2300
        runtime.pLoad170 = 1800
        runtime.vepsr = 2400
        runtime.vepss = 2405
        runtime.vepst = 2410
        runtime.feps = 5999
        runtime.peps = 300
        runtime.seps = 1
        runtime.pToUser = 1500
        runtime.vBus1 = 3700  # 370.0V after /10 scaling
        runtime.vBus2 = 3650  # 365.0V after /10 scaling
        runtime.tinner = 35
        runtime.tradiator1 = 40
        runtime.tradiator2 = 38
        runtime.status = 0

        data = InverterRuntimeData.from_http_response(runtime)

        # Check scaling was applied correctly
        assert data.pv1_voltage == 510.0
        assert data.pv2_voltage == 505.0
        assert data.pv_total_power == 2500.0
        assert data.battery_voltage == 53.0
        assert data.battery_soc == 85
        assert data.battery_charge_power == 500.0
        assert data.grid_voltage_r == 241.0
        assert data.grid_frequency == 59.98
        assert data.eps_apparent_power == 1
        assert data.bus_voltage_1 == 370.0
        # Reg-17 semantics (eg4-9wf): prec is RECTIFIER power; grid import
        # comes from pToUser, matching the Modbus path (reg 27).
        assert data.rectifier_power == 100.0
        assert data.power_from_grid == 1500.0
        assert data.power_to_grid == 200.0
        # Reg-170 mirror (eg4-9e4): pLoad170 feeds output_power.
        assert data.output_power == 1800.0

    def test_grid_power_deprecated_alias(self) -> None:
        """grid_power is a deprecated read-only alias for rectifier_power."""
        data = InverterRuntimeData(rectifier_power=100.0)

        with pytest.warns(DeprecationWarning, match="rectifier_power"):
            assert data.grid_power == 100.0

    def test_from_modbus_registers(self) -> None:
        """Test conversion from Modbus registers.

        Register layout based on validated implementations:
        - galets/eg4-modbus-monitor (registers-18kpv.yaml)
        - poldim/EG4-Inverter-Modbus (const.py)

        Key differences from old layout:
        - Power values are 16-bit SINGLE registers, not 32-bit pairs
        - PV power at regs 7-9 (not 6-11)
        - Grid voltages at regs 12-14 (not 16-18)
        - Bus voltages at regs 38-39 (not 43-44)
        """
        # Simulate input registers using correct PV_SERIES layout
        input_regs: dict[int, int] = {
            0: 0,  # Status
            1: 5100,  # PV1 voltage (×10 = 510.0V)
            2: 5050,  # PV2 voltage (×10 = 505.0V)
            3: 0,  # PV3 voltage
            4: 530,  # Battery voltage (×10 = 53.0V)
            5: (100 << 8) | 85,  # SOC=85 (low byte), SOH=100 (high byte)
            7: 1000,  # PV1 power (16-bit, W)
            8: 1500,  # PV2 power (16-bit, W)
            9: 0,  # PV3 power
            10: 500,  # Charge power (16-bit, W)
            11: 0,  # Discharge power (16-bit, W)
            12: 2410,  # Grid voltage R (×10 = 241.0V)
            13: 2415,  # Grid voltage S
            14: 2420,  # Grid voltage T
            15: 5998,  # Grid frequency (×100 = 59.98Hz)
            16: 2300,  # Inverter power (16-bit, W)
            17: 100,  # Grid power/AC charge (16-bit, W)
            19: 990,  # Power factor (×1000 = 0.99)
            20: 2400,  # EPS voltage R
            21: 2405,  # EPS voltage S
            22: 2410,  # EPS voltage T
            23: 5999,  # EPS frequency
            24: 300,  # EPS power (16-bit, W)
            25: 1,  # EPS status
            26: 200,  # Power to grid (16-bit, W)
            27: 1500,  # Load power (16-bit, W)
            38: 3700,  # Bus voltage 1 (×10 = 370.0V)
            39: 3650,  # Bus voltage 2
            64: 25,  # Internal temp (°C, signed)
            65: 40,  # Radiator temp 1
            66: 38,  # Radiator temp 2
            67: 25,  # Battery temp
            60: 35,  # Fault code low (32-bit LE: low word at base address)
            61: 0,  # Fault code high
            62: 38,  # Warning code low (32-bit LE: low word at base address)
            63: 0,  # Warning code high
        }

        data = InverterRuntimeData.from_modbus_registers(input_regs)

        assert data.pv1_voltage == 510.0
        assert data.pv1_power == 1000.0
        assert data.pv2_power == 1500.0
        assert data.pv_total_power == 2500.0
        assert data.battery_voltage == 53.0
        assert data.battery_soc == 85
        assert data.battery_soh == 100
        assert data.grid_frequency == 59.98
        assert data.load_power == 1500.0
        assert data.bus_voltage_1 == 370.0
        assert data.internal_temperature == 25.0
        assert data.fault_code == 35  # From regs 60-61 (32-bit)
        # Reg 17 lands on rectifier_power (renamed from grid_power, eg4-9wf);
        # regs 26/27 carry the real grid flows.
        assert data.rectifier_power == 100.0
        assert data.power_to_grid == 200.0
        assert data.power_from_grid == 1500.0


class TestInverterEnergyData:
    """Tests for InverterEnergyData dataclass."""

    def test_default_values(self) -> None:
        """Test that default values are None (unavailable).

        See: eg4_web_monitor issue #91
        """
        data = InverterEnergyData()

        # All numeric fields default to None (unavailable)
        assert data.pv_energy_today is None
        assert data.charge_energy_today is None
        assert data.grid_import_total is None
        assert isinstance(data.timestamp, datetime)

    def test_from_http_response(self) -> None:
        """Test conversion from HTTP API response."""
        energy = MagicMock(spec=EnergyInfo)
        energy.todayYielding = 184  # 18.4 kWh after /10
        energy.todayCharging = 50  # 5.0 kWh
        energy.todayDischarging = 30  # 3.0 kWh
        energy.todayImport = 100  # 10.0 kWh
        energy.todayExport = 150  # 15.0 kWh
        energy.todayUsage = 200  # 20.0 kWh
        energy.totalYielding = 50000  # 5000 kWh
        energy.totalCharging = 10000
        energy.totalDischarging = 8000
        energy.totalImport = 15000
        energy.totalExport = 25000
        energy.totalUsage = 40000

        data = InverterEnergyData.from_http_response(energy)

        assert data.pv_energy_today == 18.4
        assert data.charge_energy_today == 5.0
        assert data.discharge_energy_today == 3.0
        assert data.grid_import_today == 10.0
        assert data.grid_export_today == 15.0
        assert data.load_energy_today == 20.0
        assert data.pv_energy_total == 5000.0
        assert data.grid_import_total == 1500.0
        assert data.grid_export_total == 2500.0

    def test_from_modbus_registers(self) -> None:
        """Test conversion from Modbus registers.

        Energy register layout:
        - Daily energy: 16-bit registers 28-37, scale 0.1 kWh
        - Lifetime energy: 32-bit little-endian pairs starting at 40, 42, etc.
          Low word at base address, high word at base+1 (validated via Modbus testing)

        After apply_scale(raw, SCALE_10), result is directly in kWh.
        """
        input_regs: dict[int, int] = {
            # Daily energy - 16-bit, scale 0.1 kWh
            28: 100,  # PV1 today (10.0 kWh)
            29: 80,  # PV2 today (8.0 kWh)
            30: 4,  # PV3 today (0.4 kWh)
            31: 184,  # Inverter today (18.4 kWh)
            32: 100,  # AC-charge today / Erec_day (10.0 kWh)
            33: 50,  # Charge today (5.0 kWh)
            34: 30,  # Discharge today (3.0 kWh)
            35: 10,  # EPS today (1.0 kWh)
            36: 150,  # Grid export today (15.0 kWh)
            37: 200,  # Grid import today / Etouser_day (20.0 kWh) - matches HTTP todayImport
            # Lifetime energy - 32-bit little-endian (low word, high word), scale 0.1 kWh
            40: 10000,
            41: 0,  # PV1 total (1000.0 kWh)
            42: 8000,
            43: 0,  # PV2 total (800.0 kWh)
            44: 5000,
            45: 0,  # PV3 total (500.0 kWh)
            46: 50000,
            47: 0,  # Inverter total (5000.0 kWh)
            # Grid/load totals - 32-bit little-endian pairs
            48: 15000,
            49: 0,  # AC-charge total / Erec_all (1500.0 kWh)
            50: 10000,
            51: 0,  # Charge total (1000.0 kWh)
            52: 8000,
            53: 0,  # Discharge total (800.0 kWh)
            54: 2000,
            55: 0,  # EPS total (200.0 kWh)
            56: 25000,
            57: 0,  # Grid export total (2500.0 kWh)
            58: 40000,
            59: 0,  # Grid import total / Etouser_all (4000.0 kWh)
            # Real load energy (Eload, regs 171 and 172-173 32-bit) — distinct
            # from the AC-charge (Erec) values above to prove they no longer
            # alias each other (eg4-8oq).
            171: 250,  # Load today / Eload_day (25.0 kWh)
            172: 20000,
            173: 0,  # Load total / Eload_all (2000.0 kWh)
        }

        data = InverterEnergyData.from_modbus_registers(input_regs)

        # Daily values: raw / 10 = kWh
        assert data.inverter_energy_today == pytest.approx(18.4, rel=0.01)
        # Note: grid_import/load swapped to match HTTP API naming convention
        assert data.grid_import_today == pytest.approx(20.0, rel=0.01)  # Etouser_day (reg 37)
        assert data.charge_energy_today == pytest.approx(5.0, rel=0.01)
        assert data.discharge_energy_today == pytest.approx(3.0, rel=0.01)
        assert data.grid_export_today == pytest.approx(15.0, rel=0.01)
        # Real load energy (Eload_day, reg 171) and AC-charge (Erec_day, reg 32)
        # are now separate fields (eg4-8oq).
        assert data.load_energy_today == pytest.approx(25.0, rel=0.01)  # Eload_day (reg 171)
        assert data.ac_charge_energy_today == pytest.approx(10.0, rel=0.01)  # Erec_day (reg 32)

        # Per-PV daily values
        assert data.pv1_energy_today == pytest.approx(10.0, rel=0.01)
        assert data.pv2_energy_today == pytest.approx(8.0, rel=0.01)
        assert data.pv3_energy_today == pytest.approx(0.4, rel=0.01)
        assert data.pv_energy_today == pytest.approx(18.4, rel=0.01)  # Sum

        # Lifetime values: 32-bit LE, then / 10 = kWh
        assert data.inverter_energy_total == pytest.approx(5000.0, rel=0.01)
        # Note: grid_import/load swapped to match HTTP API naming convention
        assert data.grid_import_total == pytest.approx(4000.0, rel=0.01)  # Etouser_all (reg 58)
        assert data.charge_energy_total == pytest.approx(1000.0, rel=0.01)
        assert data.discharge_energy_total == pytest.approx(800.0, rel=0.01)
        assert data.grid_export_total == pytest.approx(2500.0, rel=0.01)
        # Real load energy (Eload_all, regs 172-173) and AC-charge (Erec_all,
        # regs 48-49) are now separate fields (eg4-8oq).
        assert data.load_energy_total == pytest.approx(2000.0, rel=0.01)  # Eload_all (reg 172)
        assert data.ac_charge_energy_total == pytest.approx(1500.0, rel=0.01)  # Erec_all (reg 48)

        # Per-PV lifetime values
        assert data.pv1_energy_total == pytest.approx(1000.0, rel=0.01)
        assert data.pv2_energy_total == pytest.approx(800.0, rel=0.01)
        assert data.pv3_energy_total == pytest.approx(500.0, rel=0.01)
        assert data.pv_energy_total == pytest.approx(2300.0, rel=0.01)  # Sum


class TestBatteryData:
    """Tests for BatteryData dataclass."""

    def test_default_values(self) -> None:
        """Test that default values are properly set."""
        data = BatteryData()

        assert data.battery_index == 0
        assert data.serial_number == ""
        assert data.voltage == 0.0
        assert data.current == 0.0
        assert data.soc == 0
        assert data.soh == 100
        assert data.cell_voltages == []
        assert data.cell_temperatures == []

    def test_custom_values(self) -> None:
        """Test setting custom values."""
        data = BatteryData(
            battery_index=0,
            serial_number="BAT001",
            voltage=53.05,
            current=15.5,
            soc=85,
            soh=98,
            temperature=25.0,
            max_capacity=100.0,
            current_capacity=85.0,
            cycle_count=150,
            cell_count=16,
            min_cell_voltage=3.317,
            max_cell_voltage=3.364,
        )

        assert data.serial_number == "BAT001"
        assert data.voltage == 53.05
        assert data.current == 15.5
        assert data.soc == 85
        assert data.cycle_count == 150

    def test_from_modbus_registers_cell_numbers_not_crossed(self) -> None:
        """Cell-number registers: offset 14 = temp numbers, offset 15 = voltage numbers.

        Regression test for eg4-4yg: the original map had offsets 14/15
        crossed (temp-number register parsed into the voltage-number fields
        and vice versa).

        Raw values reconstructed from the 2026-02-26 cross-mode capture of
        18kPV 4512670118 battery 01 (scratchpad/snapshots in eg4_web_monitor):
        the live cloud API reported batMaxCellNumTemp=1, batMinCellNumTemp=2,
        batMaxCellNumVolt=3, batMinCellNumVolt=1 while the local register
        read of the same battery held 0x0201 at offset 14 and 0x0103 at
        offset 15.  Cell temp/voltage extreme VALUES (offsets 10-13) are
        pinned too so an off-by-one cannot reintroduce the cross silently.
        """
        base = 5002  # battery slot 0
        registers = dict.fromkeys(range(base, base + 30), 0)
        registers[base + 0] = 0xC003  # status header: connected, 3 batteries
        registers[base + 6] = 5305  # voltage 53.05 V
        registers[base + 8] = (100 << 8) | 85  # SOH=100 / SOC=85
        registers[base + 10] = 250  # max cell temp 25.0 °C
        registers[base + 11] = 240  # min cell temp 24.0 °C
        registers[base + 12] = 3364  # max cell voltage 3.364 V
        registers[base + 13] = 3361  # min cell voltage 3.361 V
        # Offset 14: TEMP cell numbers — low byte = max (1), high byte = min (2)
        registers[base + 14] = 0x0201
        # Offset 15: VOLTAGE cell numbers — low byte = max (3), high byte = min (1)
        registers[base + 15] = 0x0103

        data = BatteryData.from_modbus_registers(0, registers)

        assert data is not None
        # Cell numbers must land in the matching fields (cloud-verified truth)
        assert data.max_cell_num_temp == 1
        assert data.min_cell_num_temp == 2
        assert data.max_cell_num_voltage == 3
        assert data.min_cell_num_voltage == 1
        # Neighboring extreme values stay on offsets 10-13
        assert data.max_cell_temperature == pytest.approx(25.0)
        assert data.min_cell_temperature == pytest.approx(24.0)
        assert data.max_cell_voltage == pytest.approx(3.364)
        assert data.min_cell_voltage == pytest.approx(3.361)


class TestBatteryBankData:
    """Tests for BatteryBankData dataclass."""

    def test_default_values(self) -> None:
        """Test that default values are None (unavailable).

        Fields default to None to indicate data is unavailable, which allows
        Home Assistant to show "unavailable" state rather than recording false
        zero values in history graphs. See: eg4_web_monitor issue #91
        """
        data = BatteryBankData()

        # All numeric fields default to None (unavailable)
        assert data.voltage is None
        assert data.soc is None
        assert data.battery_count is None
        assert data.batteries == []
        assert isinstance(data.timestamp, datetime)

    def test_with_batteries(self) -> None:
        """Test with battery modules."""
        bat1 = BatteryData(
            battery_index=0,
            serial_number="BAT001",
            voltage=53.05,
            soc=85,
        )
        bat2 = BatteryData(
            battery_index=1,
            serial_number="BAT002",
            voltage=53.10,
            soc=86,
        )

        bank = BatteryBankData(
            voltage=53.0,
            soc=85,
            charge_power=1000.0,
            discharge_power=0.0,
            battery_count=2,
            batteries=[bat1, bat2],
        )

        assert bank.battery_count == 2
        assert len(bank.batteries) == 2
        assert bank.batteries[0].serial_number == "BAT001"
        assert bank.batteries[1].serial_number == "BAT002"


class TestBatteryBankDataBMSFallback:
    """Tests for BatteryBankData bank-level BMS register fallbacks.

    When individual batteries are absent (batteries=[]), diagnostic properties
    should fall back to bank-level BMS registers (max/min cell voltage/temp)
    which are always populated from input registers 101-106.
    """

    def test_max_cell_temp_fallback_to_bank_bms(self) -> None:
        """max_cell_temp returns bank-level value when no individual batteries."""
        bank = BatteryBankData(
            batteries=[],
            max_cell_temperature=35.0,
        )
        assert bank.max_cell_temp == 35.0

    def test_temp_delta_fallback_to_bank_bms(self) -> None:
        """temp_delta returns bank max-min when no individual batteries."""
        bank = BatteryBankData(
            batteries=[],
            max_cell_temperature=38.0,
            min_cell_temperature=32.5,
        )
        assert bank.temp_delta == 5.5

    def test_cell_voltage_delta_fallback_to_bank_bms(self) -> None:
        """cell_voltage_delta_max returns bank max-min when no batteries."""
        bank = BatteryBankData(
            batteries=[],
            max_cell_voltage=3.400,
            min_cell_voltage=3.350,
        )
        assert bank.cell_voltage_delta_max == 0.050

    def test_diagnostics_prefer_individual_batteries(self) -> None:
        """When batteries are populated, per-battery data is used over bank."""
        bat1 = BatteryData(
            battery_index=0,
            serial_number="BAT001",
            voltage=53.0,
            soc=85,
            max_cell_voltage=3.410,
            min_cell_voltage=3.380,
            max_cell_temperature=36.0,
            min_cell_temperature=33.0,
        )
        bat2 = BatteryData(
            battery_index=1,
            serial_number="BAT002",
            voltage=53.1,
            soc=86,
            max_cell_voltage=3.420,
            min_cell_voltage=3.360,
            max_cell_temperature=37.0,
            min_cell_temperature=34.0,
        )
        bank = BatteryBankData(
            batteries=[bat1, bat2],
            max_cell_voltage=3.500,
            min_cell_voltage=3.200,
            max_cell_temperature=40.0,
            min_cell_temperature=30.0,
        )
        # Per-battery values used, NOT bank-level (3.420 - 3.360 = 0.060)
        assert bank.cell_voltage_delta_max == 0.060
        # Per-battery: max(36.0, 37.0) = 37.0
        assert bank.max_cell_temp == 37.0
        # Per-battery: max(36.0, 37.0) - min(33.0, 34.0) = 4.0
        assert bank.temp_delta == 4.0

    def test_fallback_none_when_bank_bms_also_missing(self) -> None:
        """Returns None when both batteries and bank BMS fields are absent."""
        bank = BatteryBankData(batteries=[])
        assert bank.max_cell_temp is None
        assert bank.temp_delta is None
        assert bank.cell_voltage_delta_max is None


class TestInverterEnergyLifetimeValues:
    """Test InverterEnergyData.lifetime_energy_values()."""

    def test_returns_correct_keys(self) -> None:
        """Method returns dict with expected lifetime energy keys."""
        data = InverterEnergyData(
            pv_energy_total=100.0,
            charge_energy_total=200.0,
            discharge_energy_total=300.0,
            grid_import_total=400.0,
            grid_export_total=500.0,
            load_energy_total=600.0,
            inverter_energy_total=700.0,
            eps_energy_total=800.0,
            eps_l1_energy_total=900.0,
            eps_l2_energy_total=1000.0,
        )
        result = data.lifetime_energy_values()
        assert result == {
            "pv_energy_total": 100.0,
            "charge_energy_total": 200.0,
            "discharge_energy_total": 300.0,
            "grid_import_total": 400.0,
            "grid_export_total": 500.0,
            "load_energy_total": 600.0,
            "inverter_energy_total": 700.0,
            "eps_energy_total": 800.0,
            "eps_l1_energy_total": 900.0,
            "eps_l2_energy_total": 1000.0,
        }

    def test_none_fields_preserved(self) -> None:
        """None values are included in the dict (not filtered out)."""
        data = InverterEnergyData()
        result = data.lifetime_energy_values()
        assert all(v is None for v in result.values())
        assert len(result) == 10


class TestMidboxRuntimeLifetimeValues:
    """Test MidboxRuntimeData.lifetime_energy_values()."""

    def test_returns_correct_keys(self) -> None:
        """Method returns dict with expected lifetime energy keys."""
        data = MidboxRuntimeData(
            load_energy_total_l1=10.0,
            load_energy_total_l2=20.0,
            ups_energy_total_l1=30.0,
            ups_energy_total_l2=40.0,
        )
        result = data.lifetime_energy_values()
        assert result["load_energy_total_l1"] == 10.0
        assert result["load_energy_total_l2"] == 20.0
        assert result["ups_energy_total_l1"] == 30.0
        assert result["ups_energy_total_l2"] == 40.0
        # Total keys = 24 (8 categories * 2 legs + 8 smart load * 2 legs)
        assert len(result) == 24

    def test_none_fields_preserved(self) -> None:
        """None values are included in the dict (not filtered out)."""
        data = MidboxRuntimeData()
        result = data.lifetime_energy_values()
        assert all(v is None for v in result.values())
        assert len(result) == 24


class TestMidboxSmartLoadCurrentFromHttp:
    """Smart-load per-leg current surfaces from cloud getMidboxRuntime (#243)."""

    @staticmethod
    def _midbox(**overrides: object) -> MidboxData:
        """Build a MidboxData with required fields stubbed + given overrides."""
        base: dict[str, object] = {
            f: None for f, info in MidboxData.model_fields.items() if info.is_required()
        }
        base["serverTime"] = ""
        base["deviceTime"] = ""
        base.update(overrides)
        return MidboxData(**base)  # type: ignore[arg-type]

    def test_smart_load_current_scaled_div10(self) -> None:
        """Cloud smartLoad*RmsCurr (deci-amps) -> smart_port current ÷10."""
        md = self._midbox(
            smartLoad1L1RmsCurr=130,  # 13.0 A
            smartLoad1L2RmsCurr=7,  # 0.7 A
            smartLoad4L2RmsCurr=16,  # 1.6 A
        )
        rt = MidboxRuntimeData.from_http_response(md)
        assert rt.smart_port_1_l1_current == 13.0
        assert rt.smart_port_1_l2_current == 0.7
        assert rt.smart_port_4_l2_current == 1.6
        # Same divisor as the sibling grid/load/gen/ups currents
        md2 = self._midbox(gridL1RmsCurr=130, smartLoad2L1RmsCurr=130)
        rt2 = MidboxRuntimeData.from_http_response(md2)
        assert rt2.smart_port_2_l1_current == rt2.grid_l1_current == 13.0

    def test_smart_load_current_none_when_absent(self) -> None:
        """Unset smart-load current fields stay None (not 0)."""
        rt = MidboxRuntimeData.from_http_response(self._midbox())
        assert rt.smart_port_1_l1_current is None
        assert rt.smart_port_3_l2_current is None


class TestSplitPhaseEpsFallback:
    """Test split-phase EPS power L1+L2 fallback in from_modbus_registers().

    Split-phase inverters (FlexBOSS, 18kPV, 12kPV) may report 0 in the
    combined EPS power register (reg 24) while per-leg registers (129/130)
    have correct values. The fallback computes combined from L1+L2.
    """

    @staticmethod
    def _base_registers() -> dict[int, int]:
        """Minimal register set for a split-phase inverter."""
        return {
            0: 0,  # Status
            5: (100 << 8) | 50,  # SOC=50, SOH=100
            15: 5998,  # Grid frequency
        }

    def test_eps_fallback_split_phase_combined_zero(self) -> None:
        """Combined eps_power=0, L1/L2 non-zero → fallback fires."""
        regs = self._base_registers()
        regs[24] = 0  # EPS power combined = 0
        regs[129] = 1213  # EPS L1 power = 1213W
        regs[130] = 423  # EPS L2 power = 423W

        data = InverterRuntimeData.from_modbus_registers(regs, "EG4_HYBRID", split_phase=True)
        assert data.eps_power == 1636.0  # 1213 + 423
        assert data.eps_l1_power == 1213
        assert data.eps_l2_power == 423

    def test_eps_no_fallback_when_not_split_phase(self) -> None:
        """split_phase=False: combined=0 stays 0 even with L1/L2 values."""
        regs = self._base_registers()
        regs[24] = 0
        regs[129] = 1213
        regs[130] = 423

        data = InverterRuntimeData.from_modbus_registers(regs, "EG4_HYBRID", split_phase=False)
        assert data.eps_power == 0.0
        assert data.eps_l1_power == 1213
        assert data.eps_l2_power == 423

    def test_eps_no_fallback_when_combined_nonzero(self) -> None:
        """Combined register has value → no fallback even on split-phase."""
        regs = self._base_registers()
        regs[24] = 1500  # Combined already populated
        regs[129] = 800
        regs[130] = 700

        data = InverterRuntimeData.from_modbus_registers(regs, "EG4_HYBRID", split_phase=True)
        assert data.eps_power == 1500.0  # Uses combined, not L1+L2

    def test_eps_no_fallback_when_all_zero(self) -> None:
        """On-grid (EPS inactive): all zeros → no false computation."""
        regs = self._base_registers()
        regs[24] = 0
        regs[129] = 0
        regs[130] = 0

        data = InverterRuntimeData.from_modbus_registers(regs, "EG4_HYBRID", split_phase=True)
        assert data.eps_power == 0.0

    def test_eps_apparent_power_fallback(self) -> None:
        """EPS apparent power (VA) also gets L1+L2 fallback."""
        regs = self._base_registers()
        regs[25] = 0  # EPS apparent power combined = 0
        regs[131] = 1300  # EPS L1 apparent power
        regs[132] = 500  # EPS L2 apparent power

        data = InverterRuntimeData.from_modbus_registers(regs, "EG4_HYBRID", split_phase=True)
        assert data.eps_apparent_power == 1800  # 1300 + 500

    def test_eps_apparent_power_field_rename(self) -> None:
        """Verify eps_apparent_power (formerly eps_status) maps correctly."""
        regs = self._base_registers()
        regs[25] = 1650  # EPS apparent power (VA)

        data = InverterRuntimeData.from_modbus_registers(regs, "EG4_HYBRID")
        assert data.eps_apparent_power == 1650

    def test_eps_fallback_only_l1_present(self) -> None:
        """Only L1 has value, L2 is zero → fallback uses L1 alone."""
        regs = self._base_registers()
        regs[24] = 0
        regs[129] = 500
        regs[130] = 0

        data = InverterRuntimeData.from_modbus_registers(regs, "EG4_HYBRID", split_phase=True)
        assert data.eps_power == 500.0


class TestPv456Parity:
    """PV string 4-6 parity for InverterRuntimeData (LOCAL + HTTP paths).

    PV strings 4-6 (V23 extended) carry voltage + power only (no current).
    A 3-string model leaves pv4-6 None, so its output — including
    ``pv_total_power`` — must be byte-for-byte identical to before this
    feature existed.  A >3-string model must include the extra strings in
    ``pv_total_power`` (LOCAL ``from_modbus_registers``) and populate the
    pv4-6 voltage/power fields from cloud (HTTP ``from_http_response``).
    """

    @staticmethod
    def _real_runtime() -> InverterRuntime:
        """Load a real cloud runtime payload (3-string, pv4-6 absent)."""
        import json
        from pathlib import Path

        sample = Path(__file__).resolve().parents[2] / "samples" / "runtime_1234567890.json"
        return InverterRuntime.model_validate(json.loads(sample.read_text()))

    # -- LOCAL (from_modbus_registers) ------------------------------------

    def test_local_pv_total_includes_pv4_pv5(self) -> None:
        """5-string LOCAL: pv_total_power sums pv1-5 (pv4/5 non-None)."""
        regs: dict[int, int] = {
            0: 0,  # status
            5: (100 << 8) | 50,  # SOC=50, SOH=100
            7: 1000,  # PV1 power
            8: 1500,  # PV2 power
            9: 500,  # PV3 power
            217: 3300,  # PV4 voltage (×10 = 330.0V)
            218: 3200,  # PV5 voltage
            220: 700,  # PV4 power (W)
            221: 300,  # PV5 power (W)
            222: 0,  # PV6 power (model only has 5 strings)
        }
        data = InverterRuntimeData.from_modbus_registers(regs, "EG4_HYBRID", pv_string_count=5)
        assert data.pv4_power == 700.0
        assert data.pv5_power == 300.0
        assert data.pv6_power is None  # index 6 > count 5 → not parsed
        # 1000 + 1500 + 500 + 700 + 300 = 4000
        assert data.pv_total_power == 4000.0

    def test_local_pv_total_3string_unchanged(self) -> None:
        """3-string LOCAL regression: pv4-6 ignored, total = pv1-3 only.

        Even when regs 217-222 are present in the raw snapshot, a 3-string
        model must not pick them up — the output must match a snapshot
        without those registers at all.
        """
        base: dict[int, int] = {
            0: 0,
            5: (100 << 8) | 50,
            7: 1000,
            8: 1500,
            9: 500,
        }
        with_pv456 = dict(base)
        with_pv456.update({217: 3300, 218: 3200, 220: 700, 221: 300, 222: 100})

        data_clean = InverterRuntimeData.from_modbus_registers(
            base, "EG4_HYBRID", pv_string_count=3
        )
        data_noisy = InverterRuntimeData.from_modbus_registers(
            with_pv456, "EG4_HYBRID", pv_string_count=3
        )

        assert data_clean.pv_total_power == 3000.0  # 1000+1500+500
        # pv4-6 ignored: total and pv4-6 fields identical with/without regs
        assert data_noisy.pv_total_power == 3000.0
        assert data_noisy.pv4_power is None
        assert data_noisy.pv5_power is None
        assert data_noisy.pv6_power is None
        assert data_noisy.pv4_voltage is None

    # -- HTTP (from_http_response) ----------------------------------------

    def test_http_populates_pv4_pv5_pv6(self) -> None:
        """HTTP: vpv4-6/ppv4-6 populate pv4-6 voltage/power with scaling."""
        runtime = self._real_runtime()
        # Inject a >3-string cloud payload (real object, mutated fields).
        runtime.vpv4 = 3300  # ×0.1 = 330.0V
        runtime.vpv5 = 3200  # 320.0V
        runtime.vpv6 = 3100  # 310.0V
        runtime.ppv4 = 700  # W (no scaling)
        runtime.ppv5 = 300
        runtime.ppv6 = 100

        data = InverterRuntimeData.from_http_response(runtime)

        assert data.pv4_voltage == 330.0
        assert data.pv5_voltage == 320.0
        assert data.pv6_voltage == 310.0
        assert data.pv4_power == 700.0
        assert data.pv5_power == 300.0
        assert data.pv6_power == 100.0

    def test_http_3string_pv4_6_none(self) -> None:
        """HTTP 3-string regression: pv4-6 stay None (cloud sends null)."""
        runtime = self._real_runtime()  # pv4-6 absent in real payload
        assert runtime.vpv4 is None and runtime.ppv4 is None

        data = InverterRuntimeData.from_http_response(runtime)

        assert data.pv4_voltage is None
        assert data.pv5_voltage is None
        assert data.pv6_voltage is None
        assert data.pv4_power is None
        assert data.pv5_power is None
        assert data.pv6_power is None
