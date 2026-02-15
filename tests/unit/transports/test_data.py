"""Tests for transport-agnostic data models."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from pylxpweb.models import EnergyInfo, InverterRuntime
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
        runtime.ppv1 = 1000
        runtime.ppv2 = 1500
        runtime.ppv3 = None
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
        assert data.eps_status == 1
        assert data.bus_voltage_1 == 370.0

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
            32: 100,  # Load today / Erec_day (10.0 kWh)
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
            49: 0,  # Load total / Erec_all (1500.0 kWh)
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
        }

        data = InverterEnergyData.from_modbus_registers(input_regs)

        # Daily values: raw / 10 = kWh
        assert data.inverter_energy_today == pytest.approx(18.4, rel=0.01)
        # Note: grid_import/load swapped to match HTTP API naming convention
        assert data.grid_import_today == pytest.approx(20.0, rel=0.01)  # Etouser_day (reg 37)
        assert data.charge_energy_today == pytest.approx(5.0, rel=0.01)
        assert data.discharge_energy_today == pytest.approx(3.0, rel=0.01)
        assert data.grid_export_today == pytest.approx(15.0, rel=0.01)
        assert data.load_energy_today == pytest.approx(10.0, rel=0.01)  # Erec_day (reg 32)

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
        assert data.load_energy_total == pytest.approx(1500.0, rel=0.01)  # Erec_all (reg 48)

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
        }

    def test_none_fields_preserved(self) -> None:
        """None values are included in the dict (not filtered out)."""
        data = InverterEnergyData()
        result = data.lifetime_energy_values()
        assert all(v is None for v in result.values())
        assert len(result) == 8


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
