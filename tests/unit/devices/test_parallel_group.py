"""Unit tests for ParallelGroup class.

This module tests the ParallelGroup class that represents a group of
inverters operating in parallel.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.parallel_group import ParallelGroup


@pytest.fixture
def mock_client() -> LuxpowerClient:
    """Create a mock client for testing."""
    client = Mock(spec=LuxpowerClient)
    client.api = Mock()
    return client


@pytest.fixture
def mock_station() -> Mock:
    """Create a mock station for testing."""
    station = Mock()
    station.id = 12345
    station.name = "Test Station"
    return station


class TestParallelGroupInitialization:
    """Test ParallelGroup initialization."""

    def test_parallel_group_initialization(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test ParallelGroup constructor."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        assert group.name == "Group A"
        assert group.first_device_serial == "1234567890"
        assert group.station is mock_station
        assert group.inverters == []
        assert group.mid_device is None

    def test_parallel_group_has_client_reference(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test ParallelGroup stores reference to client."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        assert group._client is mock_client


class TestParallelGroupWithMIDDevice:
    """Test parallel group with MID device."""

    def test_parallel_group_with_mid_device(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test group with GridBOSS/MID device."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        # Add mock MID device
        mid_device = Mock()
        mid_device.serial_number = "9999999999"
        group.mid_device = mid_device

        assert group.mid_device is mid_device
        assert group.mid_device.serial_number == "9999999999"


class TestParallelGroupWithoutMIDDevice:
    """Test parallel group without MID device."""

    def test_parallel_group_without_mid_device(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test group without GridBOSS (standalone parallel)."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        assert group.mid_device is None


class TestParallelGroupWithMultipleInverters:
    """Test parallel group with multiple inverters."""

    def test_parallel_group_multiple_inverters(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test group with 2+ inverters in parallel."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        # Add mock inverters
        inv1 = Mock()
        inv1.serial_number = "1111111111"
        inv2 = Mock()
        inv2.serial_number = "2222222222"
        inv3 = Mock()
        inv3.serial_number = "3333333333"

        group.inverters = [inv1, inv2, inv3]

        assert len(group.inverters) == 3
        assert inv1 in group.inverters
        assert inv2 in group.inverters
        assert inv3 in group.inverters


class TestParallelGroupRefresh:
    """Test parallel group refresh operation."""

    @pytest.mark.asyncio
    async def test_parallel_group_refresh_all_devices(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test refreshing all devices in group."""
        from unittest.mock import AsyncMock

        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        # Add mock inverters with async refresh methods
        inv1 = Mock()
        inv1.refresh = AsyncMock()
        inv2 = Mock()
        inv2.refresh = AsyncMock()

        group.inverters = [inv1, inv2]

        # Add mock MID device with async refresh method
        mid_device = Mock()
        mid_device.refresh = AsyncMock()
        group.mid_device = mid_device

        # Refresh should call all device refresh methods
        await group.refresh()

        # Verify all refresh methods were called
        inv1.refresh.assert_called_once()
        inv2.refresh.assert_called_once()
        mid_device.refresh.assert_called_once()


class TestParallelGroupName:
    """Test parallel group naming."""

    def test_parallel_group_name_format(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test group name follows expected format."""
        group_a = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="A",
            first_device_serial="1234567890",
        )

        group_b = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="B",
            first_device_serial="9876543210",
        )

        assert group_a.name == "A"
        assert group_b.name == "B"


class TestParallelGroupCombinedEnergy:
    """Test parallel group combined energy calculations."""

    @pytest.mark.asyncio
    async def test_get_combined_energy_empty_group(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test combined energy with no inverters."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        result = await group.get_combined_energy()

        assert result["today_kwh"] == 0.0
        assert result["lifetime_kwh"] == 0.0

    @pytest.mark.asyncio
    async def test_get_combined_energy_multiple_inverters(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test combined energy uses parallel group API endpoint."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        # Mock inverters (just need serial number and count)
        inv1 = Mock()
        inv1.serial_number = "INV001"

        inv2 = Mock()
        inv2.serial_number = "INV002"

        group.inverters = [inv1, inv2]

        # Mock parallel energy API response
        mock_energy = Mock()
        mock_energy.todayYielding = 258  # 25.8 kWh * 10
        mock_energy.totalYielding = 25000  # 2500.0 kWh * 10
        mock_client.api.devices.get_parallel_energy = AsyncMock(return_value=mock_energy)

        result = await group.get_combined_energy()

        # Verify API was called with first inverter serial
        mock_client.api.devices.get_parallel_energy.assert_called_once_with("INV001")

        # Verify results are correctly scaled (divided by 10)
        assert result["today_kwh"] == 25.8
        assert result["lifetime_kwh"] == 2500.0

    @pytest.mark.asyncio
    async def test_get_combined_energy_with_single_inverter(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test combined energy with single inverter in group."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="Group A",
            first_device_serial="1234567890",
        )

        # Single inverter in the group
        inv1 = Mock()
        inv1.serial_number = "INV001"

        group.inverters = [inv1]

        # Mock parallel energy API response
        mock_energy = Mock()
        mock_energy.todayYielding = 105  # 10.5 kWh * 10
        mock_energy.totalYielding = 10000  # 1000.0 kWh * 10
        mock_client.api.devices.get_parallel_energy = AsyncMock(return_value=mock_energy)

        result = await group.get_combined_energy()

        # Verify API was called with the inverter serial
        mock_client.api.devices.get_parallel_energy.assert_called_once_with("INV001")

        assert result["today_kwh"] == 10.5
        assert result["lifetime_kwh"] == 1000.0


class TestComputeEnergyFromInvertersUsesEnergyBalance:
    """Test _compute_energy_from_inverters uses energy balance for consumption.

    Issue #163: todayUsage/totalUsage were computed by summing load_energy_today
    and load_energy_total which are actually mapped to AC charge rectifier energy
    (register 32/48-49).  The correct approach is energy balance:
        usage = yield + discharge + import - charge - export
    """

    def _make_transport_energy(
        self,
        *,
        pv: float = 0.0,
        charge: float = 0.0,
        discharge: float = 0.0,
        grid_import: float = 0.0,
        grid_export: float = 0.0,
        load: float = 999.0,
    ) -> Mock:
        """Create mock transport energy with given values (kWh).

        The ``load`` field is deliberately set to a sentinel value (999.0)
        so the test can verify it is NOT used in the computation.
        """
        energy = Mock()
        energy.pv_energy_today = pv
        energy.charge_energy_today = charge
        energy.discharge_energy_today = discharge
        energy.grid_import_today = grid_import
        energy.grid_export_today = grid_export
        energy.load_energy_today = load  # Should NOT be used

        energy.pv_energy_total = pv * 100
        energy.charge_energy_total = charge * 100
        energy.discharge_energy_total = discharge * 100
        energy.grid_import_total = grid_import * 100
        energy.grid_export_total = grid_export * 100
        energy.load_energy_total = load * 100  # Should NOT be used
        return energy

    def test_usage_computed_from_energy_balance(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """todayUsage and totalUsage equal yield+discharge+import-charge-export."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="A",
            first_device_serial="INV001",
        )

        inv = Mock()
        inv.serial_number = "INV001"
        inv._transport_energy = self._make_transport_energy(
            pv=30.0, charge=5.0, discharge=10.0, grid_import=20.0, grid_export=8.0,
            load=999.0,  # sentinel — must NOT appear in result
        )
        group.inverters = [inv]

        result = group._compute_energy_from_inverters()

        # Energy balance: 30 + 10 + 20 - 5 - 8 = 47 kWh
        # Result is in raw API units (0.1 kWh) → 470
        expected_today = 470
        expected_total = 47000  # lifetime = today * 100 in our mock

        assert result.todayUsage == expected_today
        assert result.totalUsage == expected_total

    def test_usage_sums_across_multiple_inverters(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Energy balance is computed per-inverter then summed."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="A",
            first_device_serial="INV001",
        )

        inv1 = Mock()
        inv1.serial_number = "INV001"
        inv1._transport_energy = self._make_transport_energy(
            pv=20.0, charge=3.0, discharge=5.0, grid_import=10.0, grid_export=4.0,
        )
        inv2 = Mock()
        inv2.serial_number = "INV002"
        inv2._transport_energy = self._make_transport_energy(
            pv=15.0, charge=2.0, discharge=8.0, grid_import=12.0, grid_export=6.0,
        )
        group.inverters = [inv1, inv2]

        result = group._compute_energy_from_inverters()

        # inv1 balance: 20+5+10-3-4 = 28
        # inv2 balance: 15+8+12-2-6 = 27
        # Total = 55 kWh → 550 raw units
        assert result.todayUsage == 550
        assert result.totalUsage == 55000

    def test_load_energy_fields_not_used(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Verify load_energy_today/total are ignored (they map to AC charge)."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="A",
            first_device_serial="INV001",
        )

        inv = Mock()
        inv.serial_number = "INV001"
        inv._transport_energy = self._make_transport_energy(
            pv=10.0, charge=2.0, discharge=3.0, grid_import=5.0, grid_export=1.0,
            load=777.0,  # If this were used, todayUsage would be 7770
        )
        group.inverters = [inv]

        result = group._compute_energy_from_inverters()

        # Energy balance: 10+3+5-2-1 = 15 kWh → 150 raw
        assert result.todayUsage == 150
        assert result.todayUsage != 7770  # Confirm load field NOT used


class TestParallelGroupFactory:
    """Test parallel group factory methods."""

    @pytest.mark.asyncio
    async def test_from_api_data(self, mock_client: LuxpowerClient, mock_station: Mock) -> None:
        """Test creating group from API response."""
        api_data = {
            "parallelGroup": "A",
            "parallelFirstDeviceSn": "1234567890",
        }

        group = await ParallelGroup.from_api_data(
            client=mock_client, station=mock_station, group_data=api_data
        )

        assert group.name == "A"
        assert group.first_device_serial == "1234567890"
        assert group.station is mock_station
        assert group._client is mock_client
        assert group.inverters == []
        assert group.mid_device is None

    @pytest.mark.asyncio
    async def test_from_api_data_with_defaults(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test creating group from minimal API data uses defaults."""
        api_data = {}

        group = await ParallelGroup.from_api_data(
            client=mock_client, station=mock_station, group_data=api_data
        )

        assert group.name == "A"  # Default
        assert group.first_device_serial == ""  # Default
        assert group.station is mock_station


class TestParallelGroupAggregateBattery:
    """Test parallel group aggregate battery properties."""

    def _create_mock_inverter_with_battery(
        self,
        charge_power: int = 0,
        discharge_power: int = 0,
        battery_power: int | None = 0,
        soc: int = 50,
        max_capacity: int = 280,
        current_capacity: float = 140.0,
        voltage: float = 53.0,
        battery_count: int = 3,
    ) -> Mock:
        """Create a mock inverter with battery bank."""
        inverter = Mock()
        battery_bank = Mock()
        battery_bank.charge_power = charge_power
        battery_bank.discharge_power = discharge_power
        battery_bank.battery_power = battery_power
        battery_bank.soc = soc
        battery_bank.max_capacity = max_capacity
        battery_bank.current_capacity = current_capacity
        battery_bank.voltage = voltage
        battery_bank.battery_count = battery_count
        inverter.battery_bank = battery_bank
        return inverter

    def test_battery_charge_power_single_inverter(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test charge power with single inverter."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="A",
            first_device_serial="1234567890",
        )
        group.inverters = [self._create_mock_inverter_with_battery(charge_power=1500)]

        assert group.battery_charge_power == 1500

    def test_battery_charge_power_multiple_inverters(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test charge power sums across multiple inverters."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="A",
            first_device_serial="1234567890",
        )
        group.inverters = [
            self._create_mock_inverter_with_battery(charge_power=1000),
            self._create_mock_inverter_with_battery(charge_power=1500),
            self._create_mock_inverter_with_battery(charge_power=500),
        ]

        assert group.battery_charge_power == 3000

    def test_battery_discharge_power_multiple_inverters(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test discharge power sums across multiple inverters."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="A",
            first_device_serial="1234567890",
        )
        group.inverters = [
            self._create_mock_inverter_with_battery(discharge_power=2000),
            self._create_mock_inverter_with_battery(discharge_power=1800),
        ]

        assert group.battery_discharge_power == 3800

    def test_battery_power_net_aggregation(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test net battery power aggregation."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="A",
            first_device_serial="1234567890",
        )
        group.inverters = [
            self._create_mock_inverter_with_battery(battery_power=1000),  # Charging
            self._create_mock_inverter_with_battery(battery_power=-500),  # Discharging
        ]

        assert group.battery_power == 500  # Net: 1000 - 500

    def test_battery_soc_weighted_average(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test SOC is weighted by capacity, not simple average."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="A",
            first_device_serial="1234567890",
        )
        # Inverter 1: 200 Ah capacity, 50% SOC (100 Ah current)
        # Inverter 2: 400 Ah capacity, 75% SOC (300 Ah current)
        # Weighted average: (100 + 300) / (200 + 400) * 100 = 66.7%
        group.inverters = [
            self._create_mock_inverter_with_battery(max_capacity=200, current_capacity=100.0),
            self._create_mock_inverter_with_battery(max_capacity=400, current_capacity=300.0),
        ]

        # (100 + 300) / (200 + 400) * 100 = 66.666...
        assert group.battery_soc == 66.7

    def test_battery_max_capacity_sum(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test max capacity sums across inverters."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="A",
            first_device_serial="1234567890",
        )
        group.inverters = [
            self._create_mock_inverter_with_battery(max_capacity=280),
            self._create_mock_inverter_with_battery(max_capacity=560),
        ]

        assert group.battery_max_capacity == 840

    def test_battery_current_capacity_sum(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test current capacity sums across inverters."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="A",
            first_device_serial="1234567890",
        )
        group.inverters = [
            self._create_mock_inverter_with_battery(current_capacity=140.5),
            self._create_mock_inverter_with_battery(current_capacity=280.3),
        ]

        assert group.battery_current_capacity == 420.8

    def test_battery_voltage_average(self, mock_client: LuxpowerClient, mock_station: Mock) -> None:
        """Test voltage is averaged across inverters."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="A",
            first_device_serial="1234567890",
        )
        group.inverters = [
            self._create_mock_inverter_with_battery(voltage=52.0),
            self._create_mock_inverter_with_battery(voltage=54.0),
        ]

        assert group.battery_voltage == 53.0

    def test_battery_count_sum(self, mock_client: LuxpowerClient, mock_station: Mock) -> None:
        """Test battery count sums across inverters."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="A",
            first_device_serial="1234567890",
        )
        group.inverters = [
            self._create_mock_inverter_with_battery(battery_count=3),
            self._create_mock_inverter_with_battery(battery_count=4),
        ]

        assert group.battery_count == 7

    def test_battery_properties_no_inverters(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test battery properties return defaults with no inverters."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="A",
            first_device_serial="1234567890",
        )
        group.inverters = []

        assert group.battery_charge_power == 0
        assert group.battery_discharge_power == 0
        assert group.battery_power == 0
        assert group.battery_soc == 0.0
        assert group.battery_max_capacity == 0
        assert group.battery_current_capacity == 0.0
        assert group.battery_voltage is None
        assert group.battery_count == 0

    def test_battery_properties_no_battery_bank(
        self, mock_client: LuxpowerClient, mock_station: Mock
    ) -> None:
        """Test battery properties handle inverters without battery banks."""
        group = ParallelGroup(
            client=mock_client,
            station=mock_station,
            name="A",
            first_device_serial="1234567890",
        )
        # Inverter with no battery bank
        inverter_no_battery = Mock()
        inverter_no_battery.battery_bank = None
        group.inverters = [inverter_no_battery]

        assert group.battery_charge_power == 0
        assert group.battery_discharge_power == 0
        assert group.battery_power == 0
        assert group.battery_soc == 0.0
        assert group.battery_max_capacity == 0
        assert group.battery_current_capacity == 0.0
        assert group.battery_voltage is None
        assert group.battery_count == 0
