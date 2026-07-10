"""Tests for InverterRuntimePropertiesMixin.

This module tests the runtime property accessors to ensure:
- Correct scaling is applied
- Graceful None handling with appropriate defaults
- Type safety (returns match type hints)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pylxpweb.devices.inverters._features import InverterFamily, InverterFeatures
from pylxpweb.devices.inverters.generic import GenericInverter
from pylxpweb.models import InverterRuntime
from pylxpweb.transports.data import InverterRuntimeData


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
        # Bus Voltages (÷10)
        vBus1=3707,  # Should be 370.7V
        vBus2=3711,  # Should be 371.1V
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


@pytest.fixture
def inverter_with_transport() -> GenericInverter:
    """Create inverter with transport runtime data (local Modbus path)."""
    mock_client = MagicMock()

    inverter = GenericInverter(
        client=mock_client,
        serial_number="1234567890",
        model="18KPV",
    )
    inverter._transport_runtime = InverterRuntimeData()
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

    def test_pv_properties_return_none_when_no_data(self, inverter_without_runtime):
        """Verify PV properties return None when runtime is None."""
        assert inverter_without_runtime.pv1_voltage is None
        assert inverter_without_runtime.pv2_voltage is None
        assert inverter_without_runtime.pv3_voltage is None
        assert inverter_without_runtime.pv1_power is None
        assert inverter_without_runtime.pv2_power is None
        assert inverter_without_runtime.pv3_power is None
        assert inverter_without_runtime.pv_total_power is None

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

    def test_grid_properties_return_none_when_no_data(self, inverter_without_runtime):
        """Verify grid properties return None when runtime is None."""
        assert inverter_without_runtime.grid_voltage_r is None
        assert inverter_without_runtime.grid_voltage_s is None
        assert inverter_without_runtime.grid_voltage_t is None
        assert inverter_without_runtime.grid_frequency is None
        assert inverter_without_runtime.power_factor is None


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

    def test_battery_temperature_cloud_sentinel_is_none(self):
        """Pure-cloud path: the raw InverterRuntime tBat=127 "no reading"
        sentinel is normalized to None so a no-BMS secondary reads unknown
        rather than a bogus 127°C (eg4_web_monitor#348)."""
        inverter = GenericInverter(
            client=MagicMock(), serial_number="1234567890", model="FlexBOSS21"
        )
        inverter._runtime = InverterRuntime.model_construct(tBat=127)
        assert inverter.battery_temperature is None
        # A real cloud reading is still surfaced.
        inverter._runtime = InverterRuntime.model_construct(tBat=25)
        assert inverter.battery_temperature == 25

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
        """Verify bus voltages use ÷10 scaling."""
        assert inverter_with_runtime.bus1_voltage == 370.7
        assert inverter_with_runtime.bus2_voltage == 371.1


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
        assert inverter_without_runtime.status is None
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
            "power_factor",
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


class TestACCouplePower:
    """Tests for ac_couple_power property — register 153 preferred over reg 123."""

    def test_prefers_transport_reg153_over_reg123(self, inverter_with_transport):
        """When transport has ac_couple_power (reg 153), use it — not generator_power."""
        inverter = inverter_with_transport
        inverter._transport_runtime.ac_couple_power = 1500.0
        inverter._transport_runtime.generator_power = 9999.0  # seconds counter on OFFGRID
        assert inverter.ac_couple_power == 1500

    def test_falls_back_to_transport_generator_power(self, inverter_with_transport):
        """When transport has no ac_couple_power, fall back to generator_power."""
        inverter = inverter_with_transport
        inverter._transport_runtime.ac_couple_power = None
        inverter._transport_runtime.generator_power = 750.0
        assert inverter.ac_couple_power == 750

    def test_falls_back_to_cloud_acCouplePower(self, inverter_with_runtime):
        """When no transport, use cloud acCouplePower."""
        inverter = inverter_with_runtime
        inverter._runtime.acCouplePower = 654
        assert inverter.ac_couple_power == 654

    def test_returns_zero_when_no_data(self, inverter_without_runtime):
        """When no transport and no cloud data, return 0."""
        assert inverter_without_runtime.ac_couple_power == 0


class TestBmsPermissionProperties:
    """Dual-source BMS permission/request flags (reg 95 / cloud, issue #232)."""

    def test_cloud_reads_runtime_booleans(self, inverter_with_runtime):
        """No transport → read RuntimeInfo.bmsCharge/bmsDischarge/bmsForceCharge."""
        inverter = inverter_with_runtime
        inverter._runtime.bmsCharge = True
        inverter._runtime.bmsDischarge = True
        inverter._runtime.bmsForceCharge = False
        assert inverter.bms_allow_charge is True
        assert inverter.bms_allow_discharge is True
        assert inverter.bms_force_charge is False

    def test_local_prefers_transport_decode(self, inverter_with_transport):
        """Transport present → read the reg-95-decoded transport flags."""
        inverter = inverter_with_transport
        inverter._transport_runtime.bms_allow_charge = False
        inverter._transport_runtime.bms_allow_discharge = True
        inverter._transport_runtime.bms_force_charge = True
        assert inverter.bms_allow_charge is False
        assert inverter.bms_allow_discharge is True
        assert inverter.bms_force_charge is True

    def test_none_when_no_data(self, inverter_without_runtime):
        """No transport and no cloud runtime → None (unavailable)."""
        assert inverter_without_runtime.bms_allow_charge is None
        assert inverter_without_runtime.bms_allow_discharge is None
        assert inverter_without_runtime.bms_force_charge is None


class TestSmartLoadProperties:
    """Tests for cloud-only smart load split properties (GH eg4_web_monitor#222).

    On the EG4 Off-Grid family (6000XP/12000XP) the GEN terminal can be a
    smart-load output.  The cloud splits the backup-path output into
    smartLoadPower + epsLoadPower + gridLoadPower while peps carries the
    combined value.  No validated local register exists, so the properties
    must read the HTTP runtime even when a transport is attached (HYBRID).
    """

    def test_cloud_values_returned(self, inverter_with_runtime):
        """Cloud runtime present → raw watt values returned."""
        inverter = inverter_with_runtime
        inverter._runtime.smartLoadPower = 2999
        inverter._runtime.gridLoadPower = 0
        inverter._runtime.epsLoadPower = 365
        assert inverter.smart_load_power == 2999
        assert inverter.grid_load_power == 0
        assert inverter.eps_load_power == 365

    def test_none_without_runtime(self, inverter_without_runtime):
        """No cloud runtime → None (sensor unavailable, not a false 0)."""
        assert inverter_without_runtime.smart_load_power is None
        assert inverter_without_runtime.grid_load_power is None
        assert inverter_without_runtime.eps_load_power is None

    def test_hybrid_transport_does_not_mask_cloud_value(self, inverter_with_transport):
        """HYBRID: attached transport must NOT short-circuit the cloud read.

        This is the reporter's exact configuration (6000XP via WiFi dongle in
        HYBRID mode): _transport_runtime is populated but the smart load split
        only exists in the cloud runtime.  A transport-first helper would
        return None here — the properties must read the HTTP runtime directly.
        """
        inverter = inverter_with_transport
        inverter._runtime = InverterRuntime.model_construct(
            smartLoadPower=2999,
            gridLoadPower=0,
            epsLoadPower=365,
        )
        assert inverter.smart_load_power == 2999
        assert inverter.grid_load_power == 0
        assert inverter.eps_load_power == 365

    def test_hybrid_transport_without_cloud_is_none(self, inverter_with_transport):
        """Transport attached but no cloud runtime yet → None, not 0."""
        inverter = inverter_with_transport
        inverter._runtime = None
        assert inverter.smart_load_power is None
        assert inverter.grid_load_power is None
        assert inverter.eps_load_power is None


class TestConsumptionPowerCloudFallback:
    """consumption_power HTTP-branch family awareness (GH eg4_web_monitor#226).

    The cloud does not populate consumptionPower for the EG4 Off-Grid family
    (it reads a false 0 under load), but it does carry the authoritative
    backup-path split.  During a hybrid link-down cloud-fallback window the
    transport runtime is cleared, so the HTTP branch is what keeps the Loads
    sensor honest: it must sum epsLoadPower + smartLoadPower + gridLoadPower
    for EG4_OFFGRID and keep using consumptionPower for everything else.
    """

    @staticmethod
    def _offgrid_features() -> InverterFeatures:
        features = InverterFeatures.from_device_type_code(38)
        assert features.model_family is InverterFamily.EG4_OFFGRID
        return features

    def test_offgrid_sums_cloud_split(self, inverter_with_runtime):
        """EG4_OFFGRID + no transport runtime → eps + smart + grid sum."""
        inverter = inverter_with_runtime
        inverter._features = self._offgrid_features()
        inverter._runtime = InverterRuntime.model_construct(
            epsLoadPower=365,
            smartLoadPower=2999,
            gridLoadPower=0,
            consumptionPower=0,  # the false 0 the cloud serves this family
        )
        assert inverter.consumption_power == 3364
        # total_load_power is the deprecated alias — the reporter's actual
        # sensor; it must resolve through the same fallback.
        assert inverter.total_load_power == 3364

    def test_offgrid_transport_branch_unchanged(self, inverter_with_transport):
        """Transport runtime present → energy balance wins, split ignored."""
        inverter = inverter_with_transport
        inverter._features = self._offgrid_features()
        inverter._runtime = InverterRuntime.model_construct(
            epsLoadPower=365,
            smartLoadPower=2999,
            gridLoadPower=0,
        )
        tr = inverter._transport_runtime
        tr.pv_total_power = 1000
        tr.power_from_grid = 0
        tr.power_to_grid = 0
        tr.battery_discharge_power = 500
        tr.battery_charge_power = 0
        assert inverter.consumption_power == 1500

    def test_non_offgrid_keeps_consumption_field(self, inverter_with_runtime):
        """Grid-tied families keep the server-computed consumptionPower."""
        inverter = inverter_with_runtime
        inverter._features = InverterFeatures(model_family=InverterFamily.EG4_HYBRID)
        inverter._runtime = InverterRuntime.model_construct(
            consumptionPower=1234,
            epsLoadPower=365,
            smartLoadPower=2999,
            gridLoadPower=0,
        )
        assert inverter.consumption_power == 1234

    def test_no_features_keeps_consumption_field(self, inverter_with_runtime):
        """Family not yet detected → existing behavior (no fallback)."""
        inverter = inverter_with_runtime
        inverter._features = None
        inverter._runtime = InverterRuntime.model_construct(consumptionPower=777)
        assert inverter.consumption_power == 777

    def test_offgrid_no_runtime_is_none(self, inverter_without_runtime):
        """EG4_OFFGRID with no cloud runtime at all → None, not a fake 0."""
        inverter = inverter_without_runtime
        inverter._features = self._offgrid_features()
        assert inverter.consumption_power is None
        assert inverter.total_load_power is None
