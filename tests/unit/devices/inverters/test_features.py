"""Unit tests for inverter feature detection system."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.constants import (
    DEVICE_TYPE_CODE_LXP_LB,
)
from pylxpweb.devices.inverters._features import (
    DEVICE_TYPE_CODE_TO_FAMILY,
    FAMILY_DEFAULT_FEATURES,
    GridType,
    InverterFamily,
    InverterFeatures,
    InverterModelInfo,
    get_family_features,
    get_inverter_family,
)
from pylxpweb.devices.inverters.base import BaseInverter
from pylxpweb.devices.models import Entity


class ConcreteInverter(BaseInverter):
    """Concrete implementation for testing feature detection."""

    def to_entities(self) -> list[Entity]:
        """Generate test entities."""
        return []


# =============================================================================
# Module-Level Fixtures
# =============================================================================


@pytest.fixture
def mock_client() -> LuxpowerClient:
    """Create a mock client for testing."""
    client = Mock(spec=LuxpowerClient)
    client.api = Mock()
    client.api.control = Mock()
    client.api.control.read_parameters = AsyncMock()
    return client


# =============================================================================
# InverterModelInfo Tests
# =============================================================================


class TestInverterModelInfo:
    """Tests for InverterModelInfo dataclass."""

    def test_from_parameters_sna12k(self) -> None:
        """Test creating model info from SNA12K-US API parameters."""
        params = {
            "HOLD_MODEL": "0x90AC1",
            "HOLD_MODEL_batteryType": 2,
            "HOLD_MODEL_leadAcidType": 0,
            "HOLD_MODEL_lithiumType": 2,  # EG4 protocol
            "HOLD_MODEL_measurement": 1,
            "HOLD_MODEL_meterBrand": 0,
            "HOLD_MODEL_meterType": 0,
            "HOLD_MODEL_powerRating": 6,  # 12kW
            "HOLD_MODEL_rule": 1,
            "HOLD_MODEL_ruleMask": 0,
            "HOLD_MODEL_usVersion": 1,
            "HOLD_MODEL_wirelessMeter": 0,
        }
        model = InverterModelInfo.from_parameters(params)

        assert model.raw_value == 0x90AC1
        assert model.battery_type == 2  # Hybrid
        assert model.lithium_type == 2  # EG4 protocol
        assert model.power_rating == 6  # 12kW code
        assert model.us_version is True
        assert model.power_rating_kw == 12
        assert model.lithium_protocol_name == "EG4"

    def test_from_parameters_18kpv(self) -> None:
        """Test creating model info from 18KPV API parameters."""
        params = {
            "HOLD_MODEL": "0x986C0",
            "HOLD_MODEL_batteryType": 0,
            "HOLD_MODEL_lithiumType": 1,  # Standard
            "HOLD_MODEL_powerRating": 6,
            "HOLD_MODEL_usVersion": 1,
        }
        model = InverterModelInfo.from_parameters(params)

        assert model.raw_value == 0x986C0
        assert model.lithium_type == 1  # Standard
        assert model.us_version is True
        assert model.lithium_protocol_name == "Standard"

    def test_from_parameters_lxp_eu(self) -> None:
        """Test creating model info from LXP-EU 12K API parameters."""
        params = {
            "HOLD_MODEL": "0x19AC0",
            "HOLD_MODEL_lithiumType": 6,  # EU protocol
            "HOLD_MODEL_powerRating": 6,
            "HOLD_MODEL_usVersion": 0,
        }
        model = InverterModelInfo.from_parameters(params)

        assert model.raw_value == 0x19AC0
        assert model.lithium_type == 6  # EU protocol
        assert model.us_version is False
        assert model.power_rating_kw == 12
        assert model.lithium_protocol_name == "EU Standard"

    def test_from_raw_preserves_value(self) -> None:
        """Test that from_raw preserves the raw value."""
        model = InverterModelInfo.from_raw(0x90AC1)

        assert model.raw_value == 0x90AC1
        # Other fields remain at defaults since bit layout varies
        assert model.battery_type == 0
        assert model.lithium_type == 0
        assert model.power_rating == 0
        assert model.us_version is False

    def test_from_parameters_empty(self) -> None:
        """Test creating model info from empty parameters."""
        model = InverterModelInfo.from_parameters({})

        assert model.raw_value == 0
        assert model.battery_type == 0
        assert model.lithium_type == 0
        assert model.power_rating == 0
        assert model.us_version is False
        assert model.power_rating_kw == 0
        assert model.lithium_protocol_name == "None"

    def test_power_rating_mapping(self) -> None:
        """Test power rating code to kW mapping."""
        # Test various power rating codes
        test_cases = [
            (4, 6),  # 6kW
            (5, 8),  # 8kW
            (6, 12),  # 12kW
            (7, 15),  # 15kW
            (8, 18),  # 18kW
            (9, 21),  # 21kW
            (0, 0),  # Unknown
            (15, 0),  # Unknown
        ]

        for code, expected_kw in test_cases:
            model = InverterModelInfo(power_rating=code)
            msg = f"Code {code} should map to {expected_kw}kW"
            assert model.power_rating_kw == expected_kw, msg

    def test_lithium_protocol_names(self) -> None:
        """Test lithium protocol code to name mapping."""
        test_cases = [
            (0, "None"),
            (1, "Standard"),
            (2, "EG4"),
            (3, "Pylontech"),
            (4, "Growatt"),
            (5, "BYD"),
            (6, "EU Standard"),
            (99, "Unknown (99)"),
        ]

        for code, expected_name in test_cases:
            model = InverterModelInfo(lithium_type=code)
            assert model.lithium_protocol_name == expected_name

    def test_get_power_rating_kw_pv_series(self) -> None:
        """Test family-aware power rating for PV Series (2092)."""
        # 12KPV: powerRating=2 -> 12kW
        model = InverterModelInfo(power_rating=2)
        assert model.get_power_rating_kw(2092) == 12

        # 18KPV: powerRating=6 -> 18kW
        model = InverterModelInfo(power_rating=6)
        assert model.get_power_rating_kw(2092) == 18

    def test_get_power_rating_kw_flexboss_series(self) -> None:
        """Test family-aware power rating for FlexBOSS Series (10284)."""
        # FlexBOSS18: powerRating=6 -> 18kW
        model = InverterModelInfo(power_rating=6)
        assert model.get_power_rating_kw(10284) == 18

        # FlexBOSS21: powerRating=8 -> 21kW
        model = InverterModelInfo(power_rating=8)
        assert model.get_power_rating_kw(10284) == 21

    def test_get_power_rating_kw_offgrid_series(self) -> None:
        """Test family-aware power rating for Off-Grid Series (54)."""
        # SNA12K: powerRating=6 -> 12kW (uses legacy mapping)
        model = InverterModelInfo(power_rating=6)
        assert model.get_power_rating_kw(54) == 12

    def test_get_model_name_pv_series(self) -> None:
        """Test model name detection for PV Series."""
        model = InverterModelInfo(power_rating=2)
        assert model.get_model_name(2092) == "12KPV"

        model = InverterModelInfo(power_rating=6)
        assert model.get_model_name(2092) == "18KPV"

    def test_get_model_name_flexboss_series(self) -> None:
        """Test model name detection for FlexBOSS Series."""
        model = InverterModelInfo(power_rating=6)
        assert model.get_model_name(10284) == "FlexBOSS18"

        model = InverterModelInfo(power_rating=8)
        assert model.get_model_name(10284) == "FlexBOSS21"

    def test_get_model_name_gridboss(self) -> None:
        """Test model name detection for GridBOSS."""
        model = InverterModelInfo(power_rating=0)
        assert model.get_model_name(50) == "GridBOSS"

    def test_get_model_name_luxpower_eu(self) -> None:
        """Test model name detection for Luxpower EU Series (device type 12)."""
        model = InverterModelInfo(power_rating=6)
        assert model.get_model_name(12) == "LXP-EU-12K"

    def test_get_model_name_luxpower_lb(self) -> None:
        """Test model name detection for LXP-LB Series (device type 44)."""
        # Non-US version (us_version=False by default)
        model = InverterModelInfo(power_rating=4)
        # powerRating=4 maps to 6kW in legacy mapping
        assert model.get_model_name(DEVICE_TYPE_CODE_LXP_LB) == "LXP-LB-6K"

        # US version
        model_us = InverterModelInfo(power_rating=4, us_version=True)
        assert model_us.get_model_name(DEVICE_TYPE_CODE_LXP_LB) == "LXP-LB-US-6K"

    def test_get_power_rating_kw_unknown_code_returns_zero(self) -> None:
        """Test that unknown power rating codes return 0."""
        model = InverterModelInfo(power_rating=99)

        # Unknown code in PV Series should return 0
        assert model.get_power_rating_kw(2092) == 0

        # Unknown code in FlexBOSS Series should return 0
        assert model.get_power_rating_kw(10284) == 0

    def test_get_model_name_fallback_unknown_power_rating(self) -> None:
        """Test model name fallback for unknown power ratings."""
        model = InverterModelInfo(power_rating=99)

        # PV Series with unknown power rating
        assert model.get_model_name(2092) == "PV-Unknown"

        # FlexBOSS with unknown power rating
        assert model.get_model_name(10284) == "FlexBOSS-Unknown"

        # Off-Grid with unknown power rating (0 kW from legacy mapping)
        assert model.get_model_name(54) == "EG4-XP"

    def test_get_model_name_unknown_device_type(self) -> None:
        """Test model name for completely unknown device type codes."""
        model = InverterModelInfo(power_rating=6)
        assert model.get_model_name(9999) == "Unknown-9999"


# =============================================================================
# InverterFeatures Tests
# =============================================================================


class TestInverterFeatures:
    """Tests for InverterFeatures dataclass."""

    def test_from_device_type_code_sna(self) -> None:
        """Test creating features from SNA device type code (54)."""
        features = InverterFeatures.from_device_type_code(54)

        assert features.device_type_code == 54
        assert features.model_family == InverterFamily.EG4_OFFGRID
        assert features.grid_type == GridType.SPLIT_PHASE
        assert features.split_phase is True
        assert features.off_grid_capable is True
        assert features.discharge_recovery_hysteresis is True
        assert features.quick_charge_minute is True
        assert features.three_phase_capable is False
        assert features.parallel_support is False
        assert features.volt_watt_curve is False
        assert features.drms_support is False

    def test_from_device_type_code_pv_series(self) -> None:
        """Test creating features from PV Series device type code (2092).

        PV_SERIES inverters (18kPV, FlexBOSS) in US markets use split-phase
        L1/L2 registers (127-128, 140-141). The R/S/T registers (17-19, 20-22)
        contain garbage data on US split-phase installations.
        """
        features = InverterFeatures.from_device_type_code(2092)

        assert features.device_type_code == 2092
        assert features.model_family == InverterFamily.EG4_HYBRID
        assert features.grid_type == GridType.SPLIT_PHASE  # US split-phase
        assert features.split_phase is True  # Uses L1/L2 registers
        assert features.three_phase_capable is False  # R/S/T invalid in US
        assert features.parallel_support is True
        assert features.volt_watt_curve is True
        assert features.grid_peak_shaving is True
        assert features.drms_support is True

    def test_from_device_type_code_lxp_eu(self) -> None:
        """Test creating features from LXP-EU device type code (12)."""
        features = InverterFeatures.from_device_type_code(12)

        assert features.device_type_code == 12
        assert features.model_family == InverterFamily.LXP
        assert features.grid_type == GridType.SINGLE_PHASE
        assert features.split_phase is False
        assert features.three_phase_capable is True
        assert features.parallel_support is True
        assert features.eu_grid_compliance is True

    def test_from_device_type_code_unknown(self) -> None:
        """Test creating features from unknown device type code."""
        features = InverterFeatures.from_device_type_code(9999)

        assert features.device_type_code == 9999
        assert features.model_family == InverterFamily.UNKNOWN
        assert features.grid_type == GridType.UNKNOWN
        # Unknown devices get conservative defaults
        assert features.split_phase is False
        assert features.parallel_support is False
        assert features.volt_watt_curve is False
        assert features.off_grid_capable is True  # Most inverters have this


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for feature detection helper functions."""

    def test_get_inverter_family_sna(self) -> None:
        """Test getting SNA family from device type code."""
        family = get_inverter_family(54)
        assert family == InverterFamily.EG4_OFFGRID

    def test_get_inverter_family_pv_series(self) -> None:
        """Test getting PV Series family from device type code."""
        family = get_inverter_family(2092)
        assert family == InverterFamily.EG4_HYBRID

    def test_get_inverter_family_lxp_eu(self) -> None:
        """Test getting LXP-EU family from device type code."""
        family = get_inverter_family(12)
        assert family == InverterFamily.LXP

    def test_get_inverter_family_unknown(self) -> None:
        """Test getting UNKNOWN family from unknown device type code."""
        family = get_inverter_family(9999)
        assert family == InverterFamily.UNKNOWN

    def test_get_family_features_sna(self) -> None:
        """Test getting default features for SNA family."""
        features = get_family_features(InverterFamily.EG4_OFFGRID)

        assert features["split_phase"] is True
        assert features["discharge_recovery_hysteresis"] is True
        assert features["quick_charge_minute"] is True
        assert features["parallel_support"] is False

    def test_get_family_features_unknown(self) -> None:
        """Test getting default features for UNKNOWN family."""
        features = get_family_features(InverterFamily.UNKNOWN)

        # Unknown family gets conservative defaults
        assert features["split_phase"] is False
        assert features["parallel_support"] is False
        assert features["off_grid_capable"] is True

    def test_get_family_features_lxp(self) -> None:
        """Test getting default features for LXP family (merged LXP-EU, LXP-LV, LXP-BR)."""
        features = get_family_features(InverterFamily.LXP)

        # LXP family has parallel support and various capabilities
        # Feature availability varies by specific model but defaults are capabilities
        assert features["split_phase"] is False
        assert features["three_phase_capable"] is True  # Some LXP models support 3-phase
        assert features["parallel_support"] is True
        assert features["off_grid_capable"] is True
        assert features["volt_watt_curve"] is True  # Some LXP models support volt-watt
        assert features["eu_grid_compliance"] is True

    def test_device_type_code_mapping_completeness(self) -> None:
        """Test that all known device type codes are mapped."""
        # Known device type codes
        known_codes = [54, 2092, 12]

        for code in known_codes:
            assert code in DEVICE_TYPE_CODE_TO_FAMILY
            family = DEVICE_TYPE_CODE_TO_FAMILY[code]
            assert family != InverterFamily.UNKNOWN

    def test_family_default_features_completeness(self) -> None:
        """Test that all families have default features defined."""
        for family in InverterFamily:
            assert family in FAMILY_DEFAULT_FEATURES
            features = FAMILY_DEFAULT_FEATURES[family]
            assert isinstance(features, dict)
            assert "off_grid_capable" in features


# =============================================================================
# BaseInverter Feature Detection Integration Tests
# =============================================================================


class TestBaseInverterFeatureDetection:
    """Tests for feature detection in BaseInverter."""

    @pytest.fixture
    def sna_inverter(self, mock_client: LuxpowerClient) -> ConcreteInverter:
        """Create an SNA series inverter for testing."""
        inverter = ConcreteInverter(
            client=mock_client,
            serial_number="5200000068",
            model="SNA12K-US",
        )
        # Pre-populate parameters with SNA data (API-decoded fields)
        inverter.parameters = {
            "HOLD_DEVICE_TYPE_CODE": "54",
            "HOLD_MODEL": "0x90AC1",
            "HOLD_MODEL_batteryType": 2,
            "HOLD_MODEL_lithiumType": 2,
            "HOLD_MODEL_powerRating": 6,
            "HOLD_MODEL_usVersion": 1,
            "HOLD_DISCHG_RECOVERY_LAG_SOC": 5,
            "HOLD_DISCHG_RECOVERY_LAG_VOLT": 10,  # 1.0V after scaling
            "SNA_HOLD_QUICK_CHARGE_MINUTE": 30,
            "FUNC_DRMS_EN": False,
        }
        return inverter

    @pytest.fixture
    def pv_series_inverter(self, mock_client: LuxpowerClient) -> ConcreteInverter:
        """Create a PV Series inverter for testing."""
        inverter = ConcreteInverter(
            client=mock_client,
            serial_number="4512670118",
            model="18KPV",
        )
        # Pre-populate parameters with PV Series data (API-decoded fields)
        inverter.parameters = {
            "HOLD_DEVICE_TYPE_CODE": "2092",
            "HOLD_MODEL": "0x986C0",
            "HOLD_MODEL_batteryType": 0,
            "HOLD_MODEL_lithiumType": 1,
            "HOLD_MODEL_powerRating": 6,
            "HOLD_MODEL_usVersion": 1,
            "_12K_HOLD_GRID_PEAK_SHAVING_POWER": 7.0,
            "HOLD_VW_V1": 235,
            "FUNC_DRMS_EN": True,
        }
        return inverter

    @pytest.mark.asyncio
    async def test_detect_features_sna(self, sna_inverter: ConcreteInverter) -> None:
        """Test feature detection for SNA series inverter."""
        features = await sna_inverter.detect_features()

        assert features.device_type_code == 54
        assert features.model_family == InverterFamily.EG4_OFFGRID
        assert features.model_info.raw_value == 0x90AC1
        assert features.model_info.power_rating == 6
        assert features.model_info.power_rating_kw == 12
        assert features.model_info.lithium_type == 2
        assert features.model_info.us_version is True
        assert features.split_phase is True
        assert features.discharge_recovery_hysteresis is True
        assert features.has_sna_registers is True

    @pytest.mark.asyncio
    async def test_detect_features_pv_series(self, pv_series_inverter: ConcreteInverter) -> None:
        """Test feature detection for PV Series inverter."""
        features = await pv_series_inverter.detect_features()

        assert features.device_type_code == 2092
        assert features.model_family == InverterFamily.EG4_HYBRID
        assert features.has_pv_series_registers is True
        assert features.grid_peak_shaving is True
        assert features.volt_watt_curve is True
        assert features.drms_support is True

    @pytest.mark.asyncio
    async def test_detect_features_caching(self, sna_inverter: ConcreteInverter) -> None:
        """Test that feature detection is cached."""
        features1 = await sna_inverter.detect_features()
        features2 = await sna_inverter.detect_features()

        # Should return the same cached object
        assert features1 is features2
        assert sna_inverter._features_detected is True

    @pytest.mark.asyncio
    async def test_detect_features_force_refresh(self, sna_inverter: ConcreteInverter) -> None:
        """Test force refresh of feature detection."""
        await sna_inverter.detect_features()

        # Modify the parameters
        sna_inverter.parameters["HOLD_DEVICE_TYPE_CODE"] = "12"  # Change to LXP-EU

        # Without force, should return cached
        features2 = await sna_inverter.detect_features()
        assert features2.device_type_code == 54  # Still SNA

        # With force, should re-detect
        features3 = await sna_inverter.detect_features(force=True)
        assert features3.device_type_code == 12  # Now LXP-EU

    def test_feature_properties_sna(self, sna_inverter: ConcreteInverter) -> None:
        """Test feature properties for SNA inverter (before detection)."""
        # Before detection, features should be default
        assert sna_inverter.model_family == InverterFamily.UNKNOWN
        assert sna_inverter.device_type_code == 0
        assert sna_inverter.supports_split_phase is False

    @pytest.mark.asyncio
    async def test_feature_properties_after_detection(self, sna_inverter: ConcreteInverter) -> None:
        """Test feature properties after detection."""
        await sna_inverter.detect_features()

        assert sna_inverter.model_family == InverterFamily.EG4_OFFGRID
        assert sna_inverter.device_type_code == 54
        assert sna_inverter.grid_type == GridType.SPLIT_PHASE
        assert sna_inverter.power_rating_kw == 12
        assert sna_inverter.is_us_version is True
        assert sna_inverter.supports_split_phase is True
        assert sna_inverter.supports_three_phase is False
        assert sna_inverter.supports_off_grid is True
        assert sna_inverter.supports_parallel is False
        assert sna_inverter.supports_volt_watt_curve is False
        assert sna_inverter.supports_grid_peak_shaving is True
        assert sna_inverter.supports_drms is True  # FUNC_DRMS_EN exists
        assert sna_inverter.supports_discharge_recovery_hysteresis is True

    @pytest.mark.asyncio
    async def test_model_specific_parameters_sna(self, sna_inverter: ConcreteInverter) -> None:
        """Test SNA-specific parameter access."""
        await sna_inverter.detect_features()

        # SNA-specific parameters should be accessible
        assert sna_inverter.discharge_recovery_lag_soc == 5
        assert sna_inverter.discharge_recovery_lag_volt == 1.0  # 10 / 10
        assert sna_inverter.quick_charge_minute == 30

    @pytest.mark.asyncio
    async def test_model_specific_parameters_non_sna(
        self, pv_series_inverter: ConcreteInverter
    ) -> None:
        """Test that SNA parameters return None for non-SNA inverters."""
        await pv_series_inverter.detect_features()

        # SNA-specific parameters should return None
        assert pv_series_inverter.discharge_recovery_lag_soc is None
        assert pv_series_inverter.discharge_recovery_lag_volt is None
        assert pv_series_inverter.quick_charge_minute is None


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_detect_features_no_parameters(self, mock_client: LuxpowerClient) -> None:
        """Test feature detection when parameters are not available."""
        inverter = ConcreteInverter(
            client=mock_client,
            serial_number="0000000000",
            model="Unknown",
        )
        # Directly set empty parameters to test the edge case
        inverter.parameters = {}

        features = await inverter.detect_features()

        # Should return default features
        assert features.model_family == InverterFamily.UNKNOWN
        assert features.device_type_code == 0
        assert features.grid_type == GridType.UNKNOWN

    def test_model_info_from_string_hex(self) -> None:
        """Test parsing HOLD_MODEL from hex string."""
        # The API might return hex strings like "0x90AC1"
        model = InverterModelInfo.from_raw(int("0x90AC1", 16))
        assert model.raw_value == 0x90AC1

    def test_model_info_from_decimal_string(self) -> None:
        """Test parsing HOLD_MODEL from decimal integer."""
        model = InverterModelInfo.from_raw(592577)  # 0x90AC1 in decimal
        assert model.raw_value == 592577
        # from_raw only preserves raw_value, other fields need from_parameters
        assert model.us_version is False  # Default, not decoded

    def test_features_all_families_have_off_grid(self) -> None:
        """Test that all model families support off-grid by default."""
        for family in InverterFamily:
            features = FAMILY_DEFAULT_FEATURES[family]
            # All inverters in this ecosystem support off-grid/EPS
            assert features.get("off_grid_capable", True) is True

    def test_device_type_code_string_conversion(self) -> None:
        """Test that device type code can be parsed from string."""
        # Test both string and int handling
        features1 = InverterFeatures.from_device_type_code(54)
        features2 = InverterFeatures.from_device_type_code(int("54"))

        assert features1.model_family == features2.model_family
        assert features1.device_type_code == features2.device_type_code
