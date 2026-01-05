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
)


class TestInverterRuntimeData:
    """Tests for InverterRuntimeData dataclass."""

    def test_default_values(self) -> None:
        """Test that default values are properly set."""
        data = InverterRuntimeData()

        assert data.pv_total_power == 0.0
        assert data.battery_soc == 0
        assert data.grid_frequency == 0.0
        assert data.device_status == 0
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
        runtime.vBus1 = 3700  # 37.0V after /100 scaling
        runtime.vBus2 = 3650
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
        assert data.bus_voltage_1 == 37.0

    def test_from_modbus_registers(self) -> None:
        """Test conversion from Modbus registers."""
        # Simulate input registers
        input_regs: dict[int, int] = {
            0: 0,  # Status
            1: 5100,  # PV1 voltage (×10)
            2: 5050,  # PV2 voltage
            3: 0,  # PV3 voltage
            4: 5300,  # Battery voltage (×100)
            5: 85,  # SOC
            6: 0,  # PV1 power high
            7: 1000,  # PV1 power low
            8: 0,  # PV2 power high
            9: 1500,  # PV2 power low
            10: 0,  # PV3 power high
            11: 0,  # PV3 power low
            12: 0,  # Charge power high
            13: 500,  # Charge power low
            14: 0,  # Discharge power high
            15: 0,  # Discharge power low
            16: 2410,  # Grid voltage R
            17: 2415,  # Grid voltage S
            18: 2420,  # Grid voltage T
            19: 5998,  # Grid frequency (×100)
            20: 0,  # Inverter power high
            21: 2300,  # Inverter power low
            22: 0,  # Grid power high
            23: 100,  # Grid power low
            26: 2400,  # EPS voltage R
            27: 2405,  # EPS voltage S
            28: 2410,  # EPS voltage T
            29: 5999,  # EPS frequency
            30: 0,  # EPS power high
            31: 300,  # EPS power low
            32: 1,  # EPS status
            33: 200,  # Power to grid
            34: 0,  # Load power high
            35: 1500,  # Load power low
            43: 3700,  # Bus voltage 1
            44: 3650,  # Bus voltage 2
            61: 35,  # Internal temp
            62: 40,  # Radiator temp 1
            63: 38,  # Radiator temp 2
            64: 25,  # Battery temp
        }

        data = InverterRuntimeData.from_modbus_registers(input_regs)

        assert data.pv1_voltage == 510.0
        assert data.pv1_power == 1000.0
        assert data.pv2_power == 1500.0
        assert data.pv_total_power == 2500.0
        assert data.battery_voltage == 53.0
        assert data.battery_soc == 85
        assert data.grid_frequency == 59.98
        assert data.load_power == 1500.0


class TestInverterEnergyData:
    """Tests for InverterEnergyData dataclass."""

    def test_default_values(self) -> None:
        """Test that default values are properly set."""
        data = InverterEnergyData()

        assert data.pv_energy_today == 0.0
        assert data.charge_energy_today == 0.0
        assert data.grid_import_total == 0.0
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
        """Test conversion from Modbus registers."""
        input_regs: dict[int, int] = {
            36: 5000,  # Inverter energy total (kWh)
            37: 1500,  # Grid import total
            38: 1000,  # Charge total
            39: 800,  # Discharge total
            40: 200,  # EPS total
            41: 2500,  # Grid export total
            42: 4000,  # Load total
            45: 0,  # Inverter today high
            46: 184,  # Inverter today low (0.1 Wh)
            47: 0,  # Grid import today high
            48: 100,  # Grid import today low
            49: 0,  # Charge today high
            50: 50,  # Charge today low
            51: 0,  # Discharge today high
            52: 30,  # Discharge today low
            53: 0,  # EPS today high
            54: 10,  # EPS today low
            55: 0,  # Grid export today high
            56: 150,  # Grid export today low
            57: 0,  # Load today high
            58: 200,  # Load today low
            91: 0,
            92: 1000,  # PV1 total
            93: 0,
            94: 800,  # PV2 total
            95: 0,
            96: 500,  # PV3 total
            97: 0,
            98: 100,  # PV1 today
            99: 0,
            100: 80,  # PV2 today
            101: 0,
            102: 4,  # PV3 today
        }

        data = InverterEnergyData.from_modbus_registers(input_regs)

        # Today values are scaled from 0.1 Wh to kWh
        # 184 * 0.1 Wh = 18.4 Wh = 0.0184 kWh
        assert data.inverter_energy_today == pytest.approx(0.0184, rel=0.01)
        # 100 * 0.1 Wh = 10 Wh = 0.01 kWh
        assert data.grid_import_today == pytest.approx(0.01, rel=0.01)


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
        """Test that default values are properly set."""
        data = BatteryBankData()

        assert data.voltage == 0.0
        assert data.soc == 0
        assert data.battery_count == 0
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
