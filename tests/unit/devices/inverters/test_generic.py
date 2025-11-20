"""Unit tests for GenericInverter class."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.inverters.generic import GenericInverter
from pylxpweb.devices.models import Entity
from pylxpweb.models import EnergyInfo, InverterRuntime


@pytest.fixture
def mock_client() -> LuxpowerClient:
    """Create a mock client for testing."""
    client = Mock(spec=LuxpowerClient)
    client.api = Mock()
    client.api.inverters = Mock()
    return client


@pytest.fixture
def sample_runtime() -> InverterRuntime:
    """Load sample runtime data."""
    sample_path = Path(__file__).parent / "samples" / "runtime_44300E0585.json"
    with open(sample_path) as f:
        data = json.load(f)
    return InverterRuntime.model_validate(data)


@pytest.fixture
def sample_energy() -> EnergyInfo:
    """Create sample energy data."""
    return EnergyInfo(
        success=True,
        serialNum="1234567890",
        soc=85,
        todayYielding=25500,  # 25.5 kWh in Wh
        todayCharging=10000,
        todayDischarging=8000,
        todayImport=5000,
        todayExport=3000,
        todayUsage=15000,
        totalYielding=5000000,  # 5000 kWh in Wh
        totalCharging=2000000,
        totalDischarging=1800000,
        totalImport=1000000,
        totalExport=800000,
        totalUsage=3000000,
    )


class TestGenericInverterInitialization:
    """Test GenericInverter initialization."""

    def test_generic_inverter_initialization(
        self, mock_client: LuxpowerClient
    ) -> None:
        """Test GenericInverter can be instantiated."""
        inverter = GenericInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        assert inverter.serial_number == "1234567890"
        assert inverter.model == "FlexBOSS21"
        assert inverter.runtime is None
        assert inverter.energy is None


class TestGenericInverterEntities:
    """Test GenericInverter entity generation."""

    def test_to_entities_with_no_data(self, mock_client: LuxpowerClient) -> None:
        """Test entity generation with no data returns empty list."""
        inverter = GenericInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )

        entities = inverter.to_entities()

        assert isinstance(entities, list)
        assert len(entities) == 0

    def test_to_entities_with_runtime_data(
        self, mock_client: LuxpowerClient, sample_runtime: InverterRuntime
    ) -> None:
        """Test entity generation with runtime data."""
        inverter = GenericInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        inverter.runtime = sample_runtime

        entities = inverter.to_entities()

        assert isinstance(entities, list)
        assert len(entities) > 0

        # Check for key entities
        entity_ids = [e.unique_id for e in entities]
        assert "1234567890_power" in entity_ids
        assert "1234567890_soc" in entity_ids
        assert "1234567890_battery_voltage" in entity_ids
        assert "1234567890_pv_power" in entity_ids

    def test_to_entities_with_energy_data(
        self, mock_client: LuxpowerClient, sample_energy: EnergyInfo
    ) -> None:
        """Test entity generation with energy data."""
        inverter = GenericInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        inverter.energy = sample_energy

        entities = inverter.to_entities()

        assert isinstance(entities, list)
        assert len(entities) == 2  # Today and total

        # Check for energy entities
        entity_ids = [e.unique_id for e in entities]
        assert "1234567890_energy_today" in entity_ids
        assert "1234567890_energy_total" in entity_ids

    def test_to_entities_with_complete_data(
        self,
        mock_client: LuxpowerClient,
        sample_runtime: InverterRuntime,
        sample_energy: EnergyInfo,
    ) -> None:
        """Test entity generation with complete data."""
        inverter = GenericInverter(
            client=mock_client, serial_number="1234567890", model="FlexBOSS21"
        )
        inverter.runtime = sample_runtime
        inverter.energy = sample_energy

        entities = inverter.to_entities()

        assert isinstance(entities, list)
        # Should have runtime sensors + energy sensors
        assert len(entities) >= 10

        # Verify all entities are Entity objects
        assert all(isinstance(e, Entity) for e in entities)


class TestGenericInverterModels:
    """Test GenericInverter works with different models."""

    @pytest.mark.parametrize(
        "model",
        ["FlexBOSS21", "FlexBOSS18", "18KPV", "12KPV", "XP"],
    )
    def test_supports_all_standard_models(
        self, mock_client: LuxpowerClient, model: str
    ) -> None:
        """Test GenericInverter supports all standard models."""
        inverter = GenericInverter(
            client=mock_client, serial_number="1234567890", model=model
        )

        assert inverter.model == model
        assert inverter.to_entities() == []  # No data yet
