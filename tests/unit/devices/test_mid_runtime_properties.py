"""Tests for MIDRuntimePropertiesMixin.

This module tests the MID (GridBOSS) runtime property accessors to ensure:
- Correct scaling is applied
- Graceful None handling with appropriate defaults
- Type safety (returns match type hints)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pylxpweb.devices.mid_device import MIDDevice
from pylxpweb.models import MidboxData, MidboxRuntime


@pytest.fixture
def mid_device_with_runtime() -> MIDDevice:
    """Create MID device with sample runtime data."""
    # Create mock client
    mock_client = MagicMock()

    mid_device = MIDDevice(
        client=mock_client,
        serial_number="4524850115",
        model="GridBOSS",
    )

    # Create runtime data with known values for testing scaling
    midbox_data = MidboxData.model_construct(
        # Aggregate Voltages (÷10)
        gridRmsVolt=2420,  # Should be 242.0V
        upsRmsVolt=2400,  # Should be 240.0V
        genRmsVolt=2390,  # Should be 239.0V
        # Grid Per-Phase Voltages (÷10)
        gridL1RmsVolt=2418,  # Should be 241.8V
        gridL2RmsVolt=2422,  # Should be 242.2V
        # UPS Per-Phase Voltages (÷10)
        upsL1RmsVolt=2398,  # Should be 239.8V
        upsL2RmsVolt=2402,  # Should be 240.2V
        # Generator Per-Phase Voltages (÷10)
        genL1RmsVolt=2388,  # Should be 238.8V
        genL2RmsVolt=2392,  # Should be 239.2V
        # Currents (÷10)
        gridL1RmsCurr=150,  # Should be 15.0A
        gridL2RmsCurr=160,  # Should be 16.0A
        loadL1RmsCurr=80,  # Should be 8.0A
        loadL2RmsCurr=90,  # Should be 9.0A
        genL1RmsCurr=0,  # Should be 0.0A
        genL2RmsCurr=0,  # Should be 0.0A
        upsL1RmsCurr=70,  # Should be 7.0A
        upsL2RmsCurr=75,  # Should be 7.5A
        # Powers (no scaling)
        gridL1ActivePower=3600,  # Should be 3600W
        gridL2ActivePower=3800,  # Should be 3800W
        loadL1ActivePower=1800,  # Should be 1800W
        loadL2ActivePower=2000,  # Should be 2000W
        genL1ActivePower=0,  # Should be 0W
        genL2ActivePower=0,  # Should be 0W
        upsL1ActivePower=1600,  # Should be 1600W
        upsL2ActivePower=1700,  # Should be 1700W
        hybridPower=7400,  # Should be 7400W
        # Frequency (÷100)
        gridFreq=5998,  # Should be 59.98Hz
        # Smart Port Status (no scaling)
        smartPort1Status=1,  # Should be 1
        smartPort2Status=0,  # Should be 0
        smartPort3Status=1,  # Should be 1
        smartPort4Status=0,  # Should be 0
        # Status
        status=1,  # Should be 1
        serverTime="2025-11-22 10:30:00",
        deviceTime="2025-11-22 10:30:05",
    )

    runtime = MidboxRuntime.model_construct(
        midboxData=midbox_data,
        fwCode="v1.0.0",
    )

    mid_device._runtime = runtime
    return mid_device


@pytest.fixture
def mid_device_without_runtime() -> MIDDevice:
    """Create MID device with no runtime data."""
    # Create mock client
    mock_client = MagicMock()

    mid_device = MIDDevice(
        client=mock_client,
        serial_number="4524850115",
        model="GridBOSS",
    )
    mid_device._runtime = None
    return mid_device


class TestVoltagePropertiesAggregate:
    """Test aggregate voltage properties."""

    def test_aggregate_voltages_scaled_correctly(self, mid_device_with_runtime):
        """Verify aggregate voltages use ÷10 scaling."""
        assert mid_device_with_runtime.grid_voltage == 242.0
        assert mid_device_with_runtime.ups_voltage == 240.0
        assert mid_device_with_runtime.generator_voltage == 239.0

    def test_aggregate_voltages_return_defaults_when_none(self, mid_device_without_runtime):
        """Verify aggregate voltages return defaults when runtime is None."""
        assert mid_device_without_runtime.grid_voltage == 0.0
        assert mid_device_without_runtime.ups_voltage == 0.0
        assert mid_device_without_runtime.generator_voltage == 0.0


class TestVoltagePropertiesPerPhase:
    """Test per-phase voltage properties."""

    def test_grid_phase_voltages_scaled_correctly(self, mid_device_with_runtime):
        """Verify grid phase voltages use ÷10 scaling."""
        assert mid_device_with_runtime.grid_l1_voltage == 241.8
        assert mid_device_with_runtime.grid_l2_voltage == 242.2

    def test_ups_phase_voltages_scaled_correctly(self, mid_device_with_runtime):
        """Verify UPS phase voltages use ÷10 scaling."""
        assert mid_device_with_runtime.ups_l1_voltage == 239.8
        assert mid_device_with_runtime.ups_l2_voltage == 240.2

    def test_generator_phase_voltages_scaled_correctly(self, mid_device_with_runtime):
        """Verify generator phase voltages use ÷10 scaling."""
        assert mid_device_with_runtime.generator_l1_voltage == 238.8
        assert mid_device_with_runtime.generator_l2_voltage == 239.2

    def test_phase_voltages_return_defaults_when_none(self, mid_device_without_runtime):
        """Verify phase voltages return defaults when runtime is None."""
        assert mid_device_without_runtime.grid_l1_voltage == 0.0
        assert mid_device_without_runtime.grid_l2_voltage == 0.0
        assert mid_device_without_runtime.ups_l1_voltage == 0.0
        assert mid_device_without_runtime.ups_l2_voltage == 0.0
        assert mid_device_without_runtime.generator_l1_voltage == 0.0
        assert mid_device_without_runtime.generator_l2_voltage == 0.0


class TestCurrentProperties:
    """Test current properties."""

    def test_grid_currents_scaled_correctly(self, mid_device_with_runtime):
        """Verify grid currents use ÷10 scaling."""
        assert mid_device_with_runtime.grid_l1_current == 15.0
        assert mid_device_with_runtime.grid_l2_current == 16.0

    def test_load_currents_scaled_correctly(self, mid_device_with_runtime):
        """Verify load currents use ÷10 scaling."""
        assert mid_device_with_runtime.load_l1_current == 8.0
        assert mid_device_with_runtime.load_l2_current == 9.0

    def test_generator_currents_scaled_correctly(self, mid_device_with_runtime):
        """Verify generator currents use ÷10 scaling."""
        assert mid_device_with_runtime.generator_l1_current == 0.0
        assert mid_device_with_runtime.generator_l2_current == 0.0

    def test_ups_currents_scaled_correctly(self, mid_device_with_runtime):
        """Verify UPS currents use ÷10 scaling."""
        assert mid_device_with_runtime.ups_l1_current == 7.0
        assert mid_device_with_runtime.ups_l2_current == 7.5

    def test_currents_return_defaults_when_none(self, mid_device_without_runtime):
        """Verify currents return defaults when runtime is None."""
        assert mid_device_without_runtime.grid_l1_current == 0.0
        assert mid_device_without_runtime.grid_l2_current == 0.0
        assert mid_device_without_runtime.load_l1_current == 0.0
        assert mid_device_without_runtime.load_l2_current == 0.0


class TestPowerPropertiesGrid:
    """Test grid power properties."""

    def test_grid_phase_powers_unscaled(self, mid_device_with_runtime):
        """Verify grid phase powers have no scaling."""
        assert mid_device_with_runtime.grid_l1_power == 3600
        assert mid_device_with_runtime.grid_l2_power == 3800

    def test_grid_total_power_calculated_correctly(self, mid_device_with_runtime):
        """Verify total grid power is sum of phases."""
        assert mid_device_with_runtime.grid_power == 7400  # 3600 + 3800


class TestPowerPropertiesLoad:
    """Test load power properties."""

    def test_load_phase_powers_unscaled(self, mid_device_with_runtime):
        """Verify load phase powers have no scaling."""
        assert mid_device_with_runtime.load_l1_power == 1800
        assert mid_device_with_runtime.load_l2_power == 2000

    def test_load_total_power_calculated_correctly(self, mid_device_with_runtime):
        """Verify total load power is sum of phases."""
        assert mid_device_with_runtime.load_power == 3800  # 1800 + 2000


class TestPowerPropertiesGenerator:
    """Test generator power properties."""

    def test_generator_phase_powers_unscaled(self, mid_device_with_runtime):
        """Verify generator phase powers have no scaling."""
        assert mid_device_with_runtime.generator_l1_power == 0
        assert mid_device_with_runtime.generator_l2_power == 0

    def test_generator_total_power_calculated_correctly(self, mid_device_with_runtime):
        """Verify total generator power is sum of phases."""
        assert mid_device_with_runtime.generator_power == 0  # 0 + 0


class TestPowerPropertiesUPS:
    """Test UPS power properties."""

    def test_ups_phase_powers_unscaled(self, mid_device_with_runtime):
        """Verify UPS phase powers have no scaling."""
        assert mid_device_with_runtime.ups_l1_power == 1600
        assert mid_device_with_runtime.ups_l2_power == 1700

    def test_ups_total_power_calculated_correctly(self, mid_device_with_runtime):
        """Verify total UPS power is sum of phases."""
        assert mid_device_with_runtime.ups_power == 3300  # 1600 + 1700


class TestPowerPropertiesHybrid:
    """Test hybrid system power properties."""

    def test_hybrid_power_unscaled(self, mid_device_with_runtime):
        """Verify hybrid power has no scaling."""
        assert mid_device_with_runtime.hybrid_power == 7400


class TestFrequencyProperties:
    """Test frequency properties."""

    def test_grid_frequency_scaled_correctly(self, mid_device_with_runtime):
        """Verify grid frequency uses ÷100 scaling."""
        assert mid_device_with_runtime.grid_frequency == 59.98

    def test_grid_frequency_returns_default_when_none(self, mid_device_without_runtime):
        """Verify grid frequency returns default when runtime is None."""
        assert mid_device_without_runtime.grid_frequency == 0.0


class TestSmartPortStatus:
    """Test smart port status properties."""

    def test_smart_port_status_values(self, mid_device_with_runtime):
        """Verify smart port status returns correct values."""
        assert mid_device_with_runtime.smart_port1_status == 1
        assert mid_device_with_runtime.smart_port2_status == 0
        assert mid_device_with_runtime.smart_port3_status == 1
        assert mid_device_with_runtime.smart_port4_status == 0

    def test_smart_port_status_defaults_when_none(self, mid_device_without_runtime):
        """Verify smart port status returns defaults when runtime is None."""
        assert mid_device_without_runtime.smart_port1_status == 0
        assert mid_device_without_runtime.smart_port2_status == 0
        assert mid_device_without_runtime.smart_port3_status == 0
        assert mid_device_without_runtime.smart_port4_status == 0


class TestStatusProperties:
    """Test status & info properties."""

    def test_status_properties(self, mid_device_with_runtime):
        """Verify status properties return correct values."""
        assert mid_device_with_runtime.status == 1
        assert mid_device_with_runtime.server_time == "2025-11-22 10:30:00"
        assert mid_device_with_runtime.device_time == "2025-11-22 10:30:05"
        assert mid_device_with_runtime.firmware_version == "v1.0.0"
        assert mid_device_with_runtime.has_data is True

    def test_status_properties_when_none(self, mid_device_without_runtime):
        """Verify status properties return defaults when runtime is None."""
        assert mid_device_without_runtime.status == 0
        assert mid_device_without_runtime.server_time == ""
        assert mid_device_without_runtime.device_time == ""
        assert mid_device_without_runtime.firmware_version == ""
        assert mid_device_without_runtime.has_data is False


class TestPropertyTypes:
    """Test that all properties return expected types."""

    def test_all_float_properties_return_float(self, mid_device_with_runtime):
        """Verify all voltage/frequency/current properties return float."""
        float_properties = [
            "grid_voltage",
            "ups_voltage",
            "generator_voltage",
            "grid_l1_voltage",
            "grid_l2_voltage",
            "ups_l1_voltage",
            "ups_l2_voltage",
            "generator_l1_voltage",
            "generator_l2_voltage",
            "grid_l1_current",
            "grid_l2_current",
            "load_l1_current",
            "load_l2_current",
            "generator_l1_current",
            "generator_l2_current",
            "ups_l1_current",
            "ups_l2_current",
            "grid_frequency",
        ]

        for prop in float_properties:
            value = getattr(mid_device_with_runtime, prop)
            assert isinstance(value, float), f"{prop} should return float, got {type(value)}"

    def test_all_int_properties_return_int(self, mid_device_with_runtime):
        """Verify all power/status properties return int."""
        int_properties = [
            "grid_l1_power",
            "grid_l2_power",
            "grid_power",
            "load_l1_power",
            "load_l2_power",
            "load_power",
            "generator_l1_power",
            "generator_l2_power",
            "generator_power",
            "ups_l1_power",
            "ups_l2_power",
            "ups_power",
            "hybrid_power",
            "smart_port1_status",
            "smart_port2_status",
            "smart_port3_status",
            "smart_port4_status",
            "status",
        ]

        for prop in int_properties:
            value = getattr(mid_device_with_runtime, prop)
            assert isinstance(value, int), f"{prop} should return int, got {type(value)}"

    def test_all_string_properties_return_str(self, mid_device_with_runtime):
        """Verify all text properties return str."""
        str_properties = [
            "server_time",
            "device_time",
            "firmware_version",
        ]

        for prop in str_properties:
            value = getattr(mid_device_with_runtime, prop)
            assert isinstance(value, str), f"{prop} should return str, got {type(value)}"

    def test_all_bool_properties_return_bool(self, mid_device_with_runtime):
        """Verify all boolean properties return bool."""
        bool_properties = [
            "has_data",
        ]

        for prop in bool_properties:
            value = getattr(mid_device_with_runtime, prop)
            assert isinstance(value, bool), f"{prop} should return bool, got {type(value)}"


class TestACCouplePowerRemapping:
    """Tests for AC Couple power remapping based on Smart Port status.

    The EG4 API only provides power data in smartLoad*L*ActivePower fields.
    When a port is configured for AC Couple mode (status=2), the AC Couple
    power properties should read from the Smart Load fields to get actual
    power values.

    See GitHub issue #87 for context.
    """

    @pytest.fixture
    def mid_device_ac_couple_mode(self) -> MIDDevice:
        """Create MID device with ports in AC Couple mode and Smart Load data."""
        mock_client = MagicMock()

        mid_device = MIDDevice(
            client=mock_client,
            serial_number="4524850115",
            model="GridBOSS",
        )

        # Create runtime data simulating real API response where:
        # - Smart Port 1 is in AC Couple mode (status=2)
        # - Smart Port 4 is in AC Couple mode (status=2)
        # - Smart Load power fields have actual data (as the API provides)
        # - AC Couple power fields are 0 (API doesn't populate these)
        midbox_data = MidboxData.model_construct(
            # Smart Port Status - ports 1 and 4 in AC Couple mode
            smartPort1Status=2,  # AC Couple mode
            smartPort2Status=0,  # Unused
            smartPort3Status=1,  # Smart Load mode
            smartPort4Status=2,  # AC Couple mode
            # Smart Load power fields - this is where API provides data
            smartLoad1L1ActivePower=-1019,  # Port 1 L1 power
            smartLoad1L2ActivePower=-1020,  # Port 1 L2 power
            smartLoad2L1ActivePower=0,
            smartLoad2L2ActivePower=0,
            smartLoad3L1ActivePower=500,  # Port 3 is Smart Load mode
            smartLoad3L2ActivePower=600,
            smartLoad4L1ActivePower=800,  # Port 4 L1 power
            smartLoad4L2ActivePower=900,  # Port 4 L2 power
            # AC Couple power fields - API doesn't provide these (defaults to 0)
            acCouple1L1ActivePower=0,
            acCouple1L2ActivePower=0,
            acCouple2L1ActivePower=0,
            acCouple2L2ActivePower=0,
            acCouple3L1ActivePower=0,
            acCouple3L2ActivePower=0,
            acCouple4L1ActivePower=0,
            acCouple4L2ActivePower=0,
            # Required fields
            status=0,
            serverTime="2025-11-22 10:30:00",
            deviceTime="2025-11-22 10:30:05",
            gridRmsVolt=2420,
            upsRmsVolt=2400,
            genRmsVolt=0,
            gridL1RmsVolt=1210,
            gridL2RmsVolt=1210,
            upsL1RmsVolt=1200,
            upsL2RmsVolt=1200,
            genL1RmsVolt=0,
            genL2RmsVolt=0,
            gridL1RmsCurr=0,
            gridL2RmsCurr=0,
            loadL1RmsCurr=0,
            loadL2RmsCurr=0,
            genL1RmsCurr=0,
            genL2RmsCurr=0,
            upsL1RmsCurr=0,
            upsL2RmsCurr=0,
            gridL1ActivePower=0,
            gridL2ActivePower=0,
            loadL1ActivePower=0,
            loadL2ActivePower=0,
            genL1ActivePower=0,
            genL2ActivePower=0,
            upsL1ActivePower=0,
            upsL2ActivePower=0,
            hybridPower=0,
            gridFreq=6000,
        )

        runtime = MidboxRuntime.model_construct(
            midboxData=midbox_data,
            fwCode="v1.0.0",
        )

        mid_device._runtime = runtime
        return mid_device

    def test_ac_couple_power_reads_from_smart_load_when_ac_couple_mode(
        self, mid_device_ac_couple_mode
    ):
        """Verify AC Couple power reads Smart Load data when port is in AC Couple mode."""
        device = mid_device_ac_couple_mode

        # Port 1 is in AC Couple mode (status=2)
        # Should read from smartLoad1L*ActivePower fields
        assert device.ac_couple1_l1_power == -1019
        assert device.ac_couple1_l2_power == -1020
        assert device.ac_couple1_power == -2039  # Sum of L1 + L2

        # Port 4 is in AC Couple mode (status=2)
        # Should read from smartLoad4L*ActivePower fields
        assert device.ac_couple4_l1_power == 800
        assert device.ac_couple4_l2_power == 900
        assert device.ac_couple4_power == 1700  # Sum of L1 + L2

    def test_ac_couple_power_returns_zero_when_not_ac_couple_mode(self, mid_device_ac_couple_mode):
        """Verify AC Couple power returns 0 when port is not in AC Couple mode."""
        device = mid_device_ac_couple_mode

        # Port 2 is unused (status=0)
        # Should return 0 from acCouple2L*ActivePower fields
        assert device.ac_couple2_l1_power == 0
        assert device.ac_couple2_l2_power == 0
        assert device.ac_couple2_power == 0

        # Port 3 is in Smart Load mode (status=1)
        # Should return 0 from acCouple3L*ActivePower fields (not from smartLoad)
        assert device.ac_couple3_l1_power == 0
        assert device.ac_couple3_l2_power == 0
        assert device.ac_couple3_power == 0

    def test_smart_load_power_unaffected_by_remapping(self, mid_device_ac_couple_mode):
        """Verify Smart Load power properties always read from Smart Load fields."""
        device = mid_device_ac_couple_mode

        # Smart Load properties should always return Smart Load field values
        # regardless of port status
        assert device.smart_load1_l1_power == -1019
        assert device.smart_load1_l2_power == -1020
        assert device.smart_load3_l1_power == 500
        assert device.smart_load3_l2_power == 600
        assert device.smart_load4_l1_power == 800
        assert device.smart_load4_l2_power == 900
