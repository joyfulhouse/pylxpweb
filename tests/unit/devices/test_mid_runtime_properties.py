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
        # Currents (÷100)
        gridL1RmsCurr=1500,  # Should be 15.00A
        gridL2RmsCurr=1600,  # Should be 16.00A
        loadL1RmsCurr=800,  # Should be 8.00A
        loadL2RmsCurr=900,  # Should be 9.00A
        genL1RmsCurr=0,  # Should be 0.00A
        genL2RmsCurr=0,  # Should be 0.00A
        upsL1RmsCurr=700,  # Should be 7.00A
        upsL2RmsCurr=750,  # Should be 7.50A
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
        """Verify grid currents use ÷100 scaling."""
        assert mid_device_with_runtime.grid_l1_current == 15.0
        assert mid_device_with_runtime.grid_l2_current == 16.0

    def test_load_currents_scaled_correctly(self, mid_device_with_runtime):
        """Verify load currents use ÷100 scaling."""
        assert mid_device_with_runtime.load_l1_current == 8.0
        assert mid_device_with_runtime.load_l2_current == 9.0

    def test_generator_currents_scaled_correctly(self, mid_device_with_runtime):
        """Verify generator currents use ÷100 scaling."""
        assert mid_device_with_runtime.generator_l1_current == 0.0
        assert mid_device_with_runtime.generator_l2_current == 0.0

    def test_ups_currents_scaled_correctly(self, mid_device_with_runtime):
        """Verify UPS currents use ÷100 scaling."""
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
