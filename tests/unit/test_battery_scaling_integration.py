"""Integration tests for battery scaling with actual Pydantic models.

Tests that Battery class correctly applies scaling using the centralized
scaling system with real BatteryModule data.
"""

from __future__ import annotations

import pytest

from pylxpweb.devices.battery import Battery
from pylxpweb.models import BatteryModule


class TestBatteryScalingIntegration:
    """Test Battery class scaling with Pydantic models."""

    @pytest.fixture
    def sample_battery_data(self) -> BatteryModule:
        """Create sample battery module data.

        Based on real API response from research/.../battery_4512670118.json
        """
        return BatteryModule.model_construct(
            batteryKey="4512670118_Battery_ID_01",
            batterySn="Battery_ID_01",
            batIndex=0,
            lost=False,
            totalVoltage=5305,  # Should scale to 53.05V
            current=60,  # Should scale to 6.0A (÷10, not ÷100!)
            soc=67,
            soh=100,
            currentRemainCapacity=187,
            currentFullCapacity=280,
            batMaxCellTemp=240,  # Should scale to 24.0°C
            batMinCellTemp=240,
            batMaxCellVoltage=3317,  # Should scale to 3.317V
            batMinCellVoltage=3315,  # Should scale to 3.315V
            cycleCnt=58,
            fwVersionText="2.17",
        )

    def test_voltage_scaling(self, sample_battery_data: BatteryModule, mock_client: None) -> None:
        """Test battery voltage is scaled correctly (÷100)."""
        battery = Battery(client=mock_client, battery_data=sample_battery_data)  # type: ignore

        # totalVoltage: 5305 → 53.05V (÷100)
        assert battery.voltage == 53.05
        assert isinstance(battery.voltage, float)

    def test_current_scaling_critical(
        self, sample_battery_data: BatteryModule, mock_client: None
    ) -> None:
        """Test battery current is scaled correctly (÷10, NOT ÷100).

        This is the CRITICAL fix - battery current uses ÷10, not ÷100.
        """
        battery = Battery(client=mock_client, battery_data=sample_battery_data)  # type: ignore

        # current: 60 → 6.0A (÷10)
        assert battery.current == 6.0
        assert isinstance(battery.current, float)

        # Verify it's NOT ÷100
        assert battery.current != 0.6

    def test_power_calculation(self, sample_battery_data: BatteryModule, mock_client: None) -> None:
        """Test power is calculated correctly from scaled values."""
        battery = Battery(client=mock_client, battery_data=sample_battery_data)  # type: ignore

        # Power = Voltage × Current
        # 53.05V × 6.0A = 318.3W
        expected_power = 53.05 * 6.0
        assert battery.power == pytest.approx(expected_power, abs=0.01)

    def test_cell_voltage_scaling(
        self, sample_battery_data: BatteryModule, mock_client: None
    ) -> None:
        """Test cell voltages are scaled correctly (÷1000)."""
        battery = Battery(client=mock_client, battery_data=sample_battery_data)  # type: ignore

        # batMaxCellVoltage: 3317 → 3.317V (÷1000)
        assert battery.max_cell_voltage == 3.317

        # batMinCellVoltage: 3315 → 3.315V (÷1000)
        assert battery.min_cell_voltage == 3.315

    def test_cell_voltage_delta(
        self, sample_battery_data: BatteryModule, mock_client: None
    ) -> None:
        """Test cell voltage delta calculation."""
        battery = Battery(client=mock_client, battery_data=sample_battery_data)  # type: ignore

        # Delta = max - min = 3.317 - 3.315 = 0.002V
        expected_delta = 3.317 - 3.315
        assert battery.cell_voltage_delta == pytest.approx(expected_delta, abs=0.0001)

    def test_temperature_scaling(
        self, sample_battery_data: BatteryModule, mock_client: None
    ) -> None:
        """Test temperature is scaled correctly (÷10)."""
        battery = Battery(client=mock_client, battery_data=sample_battery_data)  # type: ignore

        # batMaxCellTemp: 240 → 24.0°C (÷10)
        assert battery.max_cell_temp == 24.0

        # batMinCellTemp: 240 → 24.0°C (÷10)
        assert battery.min_cell_temp == 24.0

    def test_no_scaling_fields(self, sample_battery_data: BatteryModule, mock_client: None) -> None:
        """Test fields that don't require scaling."""
        battery = Battery(client=mock_client, battery_data=sample_battery_data)  # type: ignore

        # These should be direct values (no scaling)
        assert battery.soc == 67  # Percentage
        assert battery.soh == 100  # Percentage
        assert battery.cycle_count == 58  # Count
        assert battery.firmware_version == "2.17"  # String

    def test_multiple_batteries_different_values(self, mock_client: None) -> None:
        """Test scaling works correctly for multiple batteries with different values."""
        # Battery 1
        battery1_data = BatteryModule.model_construct(
            batteryKey="test_bat1",
            batterySn="BAT1",
            batIndex=0,
            lost=False,
            totalVoltage=5305,
            current=60,
            soc=67,
            soh=100,
            currentRemainCapacity=187,
            currentFullCapacity=280,
            batMaxCellTemp=240,
            batMinCellTemp=240,
            batMaxCellVoltage=3317,
            batMinCellVoltage=3315,
            cycleCnt=58,
            fwVersionText="2.17",
        )

        # Battery 2 - different values
        battery2_data = BatteryModule.model_construct(
            batteryKey="test_bat2",
            batterySn="BAT2",
            batIndex=1,
            lost=False,
            totalVoltage=5304,  # Slightly different
            current=54,  # Different current
            soc=71,
            soh=100,
            currentRemainCapacity=198,
            currentFullCapacity=280,
            batMaxCellTemp=250,  # Higher temp
            batMinCellTemp=240,
            batMaxCellVoltage=3316,
            batMinCellVoltage=3314,
            cycleCnt=53,
            fwVersionText="2.17",
        )

        battery1 = Battery(client=mock_client, battery_data=battery1_data)  # type: ignore
        battery2 = Battery(client=mock_client, battery_data=battery2_data)  # type: ignore

        # Verify each battery has correct scaled values
        assert battery1.voltage == 53.05
        assert battery2.voltage == 53.04

        assert battery1.current == 6.0
        assert battery2.current == 5.4

        assert battery1.max_cell_temp == 24.0
        assert battery2.max_cell_temp == 25.0

    def test_zero_current(self, sample_battery_data: BatteryModule, mock_client: None) -> None:
        """Test scaling with zero current (idle battery)."""
        sample_battery_data.current = 0
        battery = Battery(client=mock_client, battery_data=sample_battery_data)  # type: ignore

        assert battery.current == 0.0
        assert battery.power == 0.0  # V × 0A = 0W

    def test_lost_battery(self, sample_battery_data: BatteryModule, mock_client: None) -> None:
        """Test battery marked as lost still has scaled values."""
        sample_battery_data.lost = True
        battery = Battery(client=mock_client, battery_data=sample_battery_data)  # type: ignore

        # Even if lost, scaling should still work
        assert battery.is_lost is True
        assert battery.voltage == 53.05
        assert battery.current == 6.0


class TestBatteryEntitiesScaling:
    """Test that Battery.to_entities() returns properly scaled values."""

    @pytest.fixture
    def sample_battery(self, mock_client: None) -> Battery:
        """Create a sample battery for testing."""
        battery_data = BatteryModule.model_construct(
            batteryKey="test_battery",
            batterySn="TEST001",
            batIndex=0,
            lost=False,
            totalVoltage=5305,
            current=60,
            soc=67,
            soh=100,
            currentRemainCapacity=187,
            currentFullCapacity=280,
            batMaxCellTemp=240,
            batMinCellTemp=240,
            batMaxCellVoltage=3317,
            batMinCellVoltage=3315,
            cycleCnt=58,
            fwVersionText="2.17",
        )
        return Battery(client=mock_client, battery_data=battery_data)  # type: ignore

    def test_voltage_entity_has_scaled_value(self, sample_battery: Battery) -> None:
        """Test voltage entity contains scaled value."""
        entities = sample_battery.to_entities()

        voltage_entity = next(
            e for e in entities if "voltage" in e.unique_id and "cell" not in e.unique_id
        )
        assert voltage_entity.value == 53.05
        assert voltage_entity.unit_of_measurement == "V"

    def test_current_entity_has_scaled_value(self, sample_battery: Battery) -> None:
        """Test current entity contains scaled value."""
        entities = sample_battery.to_entities()

        current_entity = next(e for e in entities if "current" in e.unique_id)
        assert current_entity.value == 6.0  # Not 0.6!
        assert current_entity.unit_of_measurement == "A"

    def test_power_entity_has_calculated_value(self, sample_battery: Battery) -> None:
        """Test power entity contains calculated value."""
        entities = sample_battery.to_entities()

        power_entity = next(e for e in entities if "power" in e.unique_id)
        expected_power = 53.05 * 6.0
        assert power_entity.value == pytest.approx(expected_power, abs=0.01)
        assert power_entity.unit_of_measurement == "W"

    def test_temperature_entities_have_scaled_values(self, sample_battery: Battery) -> None:
        """Test temperature entities contain scaled values."""
        entities = sample_battery.to_entities()

        max_temp_entity = next(e for e in entities if "max_cell_temp" in e.unique_id)
        min_temp_entity = next(e for e in entities if "min_cell_temp" in e.unique_id)

        assert max_temp_entity.value == 24.0
        assert min_temp_entity.value == 24.0
        assert max_temp_entity.unit_of_measurement == "°C"

    def test_cell_voltage_entities_have_scaled_values(self, sample_battery: Battery) -> None:
        """Test cell voltage entities contain scaled values."""
        entities = sample_battery.to_entities()

        max_cell_v = next(e for e in entities if "max_cell_voltage" in e.unique_id)
        min_cell_v = next(e for e in entities if "min_cell_voltage" in e.unique_id)
        delta_v = next(e for e in entities if "cell_voltage_delta" in e.unique_id)

        assert max_cell_v.value == 3.317
        assert min_cell_v.value == 3.315
        assert delta_v.value == pytest.approx(0.002, abs=0.0001)
        assert max_cell_v.unit_of_measurement == "V"


@pytest.fixture
def mock_client():
    """Mock LuxpowerClient for testing."""
    from unittest.mock import Mock

    mock = Mock()
    return mock


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
