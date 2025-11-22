"""Tests for InverterRuntimePropertiesMixin.

This module tests the runtime property accessors to ensure:
- Correct scaling is applied
- Graceful None handling with appropriate defaults
- Type safety (returns match type hints)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pylxpweb.devices.inverters.generic import GenericInverter
from pylxpweb.models import InverterRuntime


@pytest.fixture
def inverter_with_runtime() -> GenericInverter:
    """Create inverter with sample runtime data."""
    # Create mock client
    mock_client = MagicMock()

    inverter = GenericInverter(
        client=mock_client,
        serial_number="1234567890",
        model="18KPV",
    )

    # Create runtime data with known values for testing scaling
    runtime = InverterRuntime.model_construct(
        # PV Voltages (÷10)
        vpv1=5100,  # Should be 510.0V
        vpv2=4800,  # Should be 480.0V
        vpv3=0,  # Should be 0.0V
        # PV Powers (no scaling)
        ppv1=1500,  # Should be 1500W
        ppv2=1200,  # Should be 1200W
        ppv3=0,  # Should be 0W
        ppv=2700,  # Should be 2700W
        # AC Voltages (÷10)
        vacr=2418,  # Should be 241.8V
        vacs=2411,  # Should be 241.1V
        vact=2405,  # Should be 240.5V
        # AC Frequency (÷100)
        fac=5998,  # Should be 59.98Hz
        # EPS Voltages (÷10)
        vepsr=2401,  # Should be 240.1V
        vepss=2398,  # Should be 239.8V
        vepst=2395,  # Should be 239.5V
        # EPS Frequency (÷100)
        feps=5995,  # Should be 59.95Hz
        # EPS Powers (no scaling)
        peps=500,  # Should be 500W
        pEpsL1N=250,  # Should be 250W
        pEpsL2N=250,  # Should be 250W
        # Power Flow (no scaling)
        pToGrid=100,  # Should be 100W
        pToUser=800,  # Should be 800W
        pinv=900,  # Should be 900W
        prec=50,  # Should be 50W
        # Battery (÷10 for voltage, no scaling for power/temp)
        vBat=539,  # Should be 53.9V
        pCharge=1000,  # Should be 1000W
        pDisCharge=0,  # Should be 0W
        batPower=1000,  # Should be 1000W (positive = charging)
        tBat=25,  # Should be 25°C
        # Currents (÷100)
        maxChgCurr=10000,  # Should be 100.00A
        maxDischgCurr=12000,  # Should be 120.00A
        # Temperatures (no scaling)
        tinner=35,  # Should be 35°C
        tradiator1=40,  # Should be 40°C
        tradiator2=42,  # Should be 42°C
        # Bus Voltages (÷100)
        vBus1=37003,  # Should be 370.03V
        vBus2=37105,  # Should be 371.05V
        # Generator (÷10 for voltage, ÷100 for frequency, no scaling for power)
        genVolt=2400,  # Should be 240.0V
        genFreq=6000,  # Should be 60.00Hz
        genPower=0,  # Should be 0W
        # AC Couple (no scaling)
        acCouplePower=0,  # Should be 0W
        # Consumption (no scaling)
        consumptionPower=700,  # Should be 700W
        # Status
        soc=85,  # Should be 85%
        status=1,  # Should be 1
        statusText="Normal",  # Should be "Normal"
        lost=False,  # Should be False
        fwCode="v1.2.3",  # Should be "v1.2.3"
        powerRatingText="18kW",  # Should be "18kW"
        pf="1.00",  # Should be "1.00"
        _12KUsingGenerator=False,  # Should be False
    )

    inverter._runtime = runtime
    return inverter


@pytest.fixture
def inverter_without_runtime() -> GenericInverter:
    """Create inverter with no runtime data."""
    # Create mock client
    mock_client = MagicMock()

    inverter = GenericInverter(
        client=mock_client,
        serial_number="1234567890",
        model="18KPV",
    )
    inverter._runtime = None
    return inverter


class TestPVProperties:
    """Test PV (Solar Panel) properties."""

    def test_pv_voltages_scaled_correctly(self, inverter_with_runtime):
        """Verify PV voltages use ÷10 scaling."""
        assert inverter_with_runtime.pv1_voltage == 510.0
        assert inverter_with_runtime.pv2_voltage == 480.0
        assert inverter_with_runtime.pv3_voltage == 0.0

    def test_pv_powers_unscaled(self, inverter_with_runtime):
        """Verify PV powers have no scaling."""
        assert inverter_with_runtime.pv1_power == 1500
        assert inverter_with_runtime.pv2_power == 1200
        assert inverter_with_runtime.pv3_power == 0
        assert inverter_with_runtime.pv_total_power == 2700

    def test_pv_properties_return_defaults_when_none(self, inverter_without_runtime):
        """Verify PV properties return defaults when runtime is None."""
        assert inverter_without_runtime.pv1_voltage == 0.0
        assert inverter_without_runtime.pv2_voltage == 0.0
        assert inverter_without_runtime.pv3_voltage == 0.0
        assert inverter_without_runtime.pv1_power == 0
        assert inverter_without_runtime.pv2_power == 0
        assert inverter_without_runtime.pv3_power == 0
        assert inverter_without_runtime.pv_total_power == 0

    def test_pv_voltage_types(self, inverter_with_runtime):
        """Verify PV voltages return float type."""
        assert isinstance(inverter_with_runtime.pv1_voltage, float)
        assert isinstance(inverter_with_runtime.pv2_voltage, float)
        assert isinstance(inverter_with_runtime.pv3_voltage, float)

    def test_pv_power_types(self, inverter_with_runtime):
        """Verify PV powers return int type."""
        assert isinstance(inverter_with_runtime.pv1_power, int)
        assert isinstance(inverter_with_runtime.pv2_power, int)
        assert isinstance(inverter_with_runtime.pv3_power, int)
        assert isinstance(inverter_with_runtime.pv_total_power, int)


class TestACGridProperties:
    """Test AC Grid properties."""

    def test_grid_voltages_scaled_correctly(self, inverter_with_runtime):
        """Verify grid voltages use ÷10 scaling."""
        assert inverter_with_runtime.grid_voltage_r == 241.8
        assert inverter_with_runtime.grid_voltage_s == 241.1
        assert inverter_with_runtime.grid_voltage_t == 240.5

    def test_grid_frequency_scaled_correctly(self, inverter_with_runtime):
        """Verify grid frequency uses ÷100 scaling."""
        assert inverter_with_runtime.grid_frequency == 59.98

    def test_grid_properties_return_defaults_when_none(self, inverter_without_runtime):
        """Verify grid properties return defaults when runtime is None."""
        assert inverter_without_runtime.grid_voltage_r == 0.0
        assert inverter_without_runtime.grid_voltage_s == 0.0
        assert inverter_without_runtime.grid_voltage_t == 0.0
        assert inverter_without_runtime.grid_frequency == 0.0
        assert inverter_without_runtime.power_factor == ""


class TestEPSProperties:
    """Test EPS (Emergency Power Supply) properties."""

    def test_eps_voltages_scaled_correctly(self, inverter_with_runtime):
        """Verify EPS voltages use ÷10 scaling."""
        assert inverter_with_runtime.eps_voltage_r == 240.1
        assert inverter_with_runtime.eps_voltage_s == 239.8
        assert inverter_with_runtime.eps_voltage_t == 239.5

    def test_eps_frequency_scaled_correctly(self, inverter_with_runtime):
        """Verify EPS frequency uses ÷100 scaling."""
        assert inverter_with_runtime.eps_frequency == 59.95

    def test_eps_powers_unscaled(self, inverter_with_runtime):
        """Verify EPS powers have no scaling."""
        assert inverter_with_runtime.eps_power == 500
        assert inverter_with_runtime.eps_power_l1 == 250
        assert inverter_with_runtime.eps_power_l2 == 250


class TestBatteryProperties:
    """Test Battery properties."""

    def test_battery_voltage_scaled_correctly(self, inverter_with_runtime):
        """Verify battery voltage uses ÷10 scaling."""
        assert inverter_with_runtime.battery_voltage == 53.9

    def test_battery_powers_unscaled(self, inverter_with_runtime):
        """Verify battery powers have no scaling."""
        assert inverter_with_runtime.battery_charge_power == 1000
        assert inverter_with_runtime.battery_discharge_power == 0
        assert inverter_with_runtime.battery_power == 1000

    def test_battery_temperature_unscaled(self, inverter_with_runtime):
        """Verify battery temperature has no scaling."""
        assert inverter_with_runtime.battery_temperature == 25

    def test_battery_currents_scaled_correctly(self, inverter_with_runtime):
        """Verify battery currents use ÷100 scaling."""
        assert inverter_with_runtime.max_charge_current == 100.0
        assert inverter_with_runtime.max_discharge_current == 120.0


class TestPowerFlowProperties:
    """Test Power Flow properties."""

    def test_power_flow_unscaled(self, inverter_with_runtime):
        """Verify power flow values have no scaling."""
        assert inverter_with_runtime.power_to_grid == 100
        assert inverter_with_runtime.power_to_user == 800
        assert inverter_with_runtime.inverter_power == 900
        assert inverter_with_runtime.rectifier_power == 50


class TestTemperatureProperties:
    """Test Temperature properties."""

    def test_temperatures_unscaled(self, inverter_with_runtime):
        """Verify temperatures have no scaling."""
        assert inverter_with_runtime.inverter_temperature == 35
        assert inverter_with_runtime.radiator1_temperature == 40
        assert inverter_with_runtime.radiator2_temperature == 42


class TestBusVoltageProperties:
    """Test Bus Voltage properties."""

    def test_bus_voltages_scaled_correctly(self, inverter_with_runtime):
        """Verify bus voltages use ÷100 scaling."""
        assert inverter_with_runtime.bus1_voltage == 370.03
        assert inverter_with_runtime.bus2_voltage == 371.05


class TestGeneratorProperties:
    """Test Generator properties."""

    def test_generator_voltage_scaled_correctly(self, inverter_with_runtime):
        """Verify generator voltage uses ÷10 scaling."""
        assert inverter_with_runtime.generator_voltage == 240.0

    def test_generator_frequency_scaled_correctly(self, inverter_with_runtime):
        """Verify generator frequency uses ÷100 scaling."""
        assert inverter_with_runtime.generator_frequency == 60.0

    def test_generator_power_unscaled(self, inverter_with_runtime):
        """Verify generator power has no scaling."""
        assert inverter_with_runtime.generator_power == 0

    def test_generator_status(self, inverter_with_runtime):
        """Verify generator status is boolean."""
        assert inverter_with_runtime.is_using_generator is False


class TestStatusProperties:
    """Test Status & Info properties."""

    def test_status_properties(self, inverter_with_runtime):
        """Verify status properties return correct values."""
        assert inverter_with_runtime.status == 1
        assert inverter_with_runtime.status_text == "Normal"
        assert inverter_with_runtime.is_lost is False
        assert inverter_with_runtime.firmware_version == "v1.2.3"
        assert inverter_with_runtime.power_rating == "18kW"

    def test_status_properties_when_none(self, inverter_without_runtime):
        """Verify status properties return defaults when runtime is None."""
        assert inverter_without_runtime.status == 0
        assert inverter_without_runtime.status_text == ""
        assert inverter_without_runtime.is_lost is True  # No data = lost
        assert inverter_without_runtime.firmware_version == ""
        assert inverter_without_runtime.power_rating == ""


class TestPropertyTypes:
    """Test that all properties return expected types."""

    def test_all_float_properties_return_float(self, inverter_with_runtime):
        """Verify all voltage/frequency properties return float."""
        float_properties = [
            "pv1_voltage",
            "pv2_voltage",
            "pv3_voltage",
            "grid_voltage_r",
            "grid_voltage_s",
            "grid_voltage_t",
            "grid_frequency",
            "eps_voltage_r",
            "eps_voltage_s",
            "eps_voltage_t",
            "eps_frequency",
            "battery_voltage",
            "max_charge_current",
            "max_discharge_current",
            "bus1_voltage",
            "bus2_voltage",
            "generator_voltage",
            "generator_frequency",
        ]

        for prop in float_properties:
            value = getattr(inverter_with_runtime, prop)
            assert isinstance(value, float), f"{prop} should return float, got {type(value)}"

    def test_all_int_properties_return_int(self, inverter_with_runtime):
        """Verify all power/temperature properties return int."""
        int_properties = [
            "pv1_power",
            "pv2_power",
            "pv3_power",
            "pv_total_power",
            "eps_power",
            "eps_power_l1",
            "eps_power_l2",
            "power_to_grid",
            "power_to_user",
            "inverter_power",
            "rectifier_power",
            "battery_charge_power",
            "battery_discharge_power",
            "battery_power",
            "battery_temperature",
            "inverter_temperature",
            "radiator1_temperature",
            "radiator2_temperature",
            "ac_couple_power",
            "generator_power",
            "consumption_power",
            "status",
        ]

        for prop in int_properties:
            value = getattr(inverter_with_runtime, prop)
            assert isinstance(value, int), f"{prop} should return int, got {type(value)}"

    def test_all_string_properties_return_str(self, inverter_with_runtime):
        """Verify all text properties return str."""
        str_properties = [
            "power_factor",
            "status_text",
            "firmware_version",
            "power_rating",
        ]

        for prop in str_properties:
            value = getattr(inverter_with_runtime, prop)
            assert isinstance(value, str), f"{prop} should return str, got {type(value)}"

    def test_all_bool_properties_return_bool(self, inverter_with_runtime):
        """Verify all boolean properties return bool."""
        bool_properties = [
            "is_lost",
            "is_using_generator",
        ]

        for prop in bool_properties:
            value = getattr(inverter_with_runtime, prop)
            assert isinstance(value, bool), f"{prop} should return bool, got {type(value)}"
