"""Inverter feature detection and model identification.

This module provides dataclasses and utilities for detecting inverter capabilities
based on device type codes, HOLD_MODEL register values, and runtime parameter probing.

Feature detection uses a multi-layer approach:
1. Model decoding from HOLD_MODEL register (hardware configuration)
2. Device type code mapping to known model families
3. Runtime parameter probing for optional features
4. Clean property-based API for capability checking
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from enum import Enum

# Mapping of deprecated family names to their replacements
_DEPRECATED_FAMILY_NAMES: dict[str, str] = {
    "SNA": "EG4_OFFGRID",
    "PV_SERIES": "EG4_HYBRID",
    "LXP_EU": "LXP",
    "LXP_LV": "LXP",
}


class InverterFamily(str, Enum):
    """Inverter model family classification.

    Each family has distinct hardware capabilities and parameter sets.
    The family is determined by the HOLD_DEVICE_TYPE_CODE register value.

    Family naming convention:
    - EG4_* families: EG4 Electronics branded inverters (US market)
    - LXP: Luxpower branded inverters (EU, Brazil, low-voltage - all use same registers)
    """

    # EG4 Off-Grid Series - Off-grid capable, no grid sellback
    # Models: 12000XP, 6000XP
    # Device type code: 54
    EG4_OFFGRID = "EG4_OFFGRID"

    # EG4 Hybrid Series - Grid-tied hybrid with sellback capability
    # Models: 18kPV, 12kPV, FlexBOSS21, FlexBOSS18
    # Device type codes: 2092, 10284
    EG4_HYBRID = "EG4_HYBRID"

    # Luxpower Series - All Luxpower branded inverters (same register maps)
    # Models: LXP-EU 12K, LXP-LB-BR 10K, LXP-LV 6048
    # Device type codes: 12, 44, and others
    LXP = "LXP"

    # Unknown model family
    UNKNOWN = "UNKNOWN"

    # -------------------------------------------------------------------------
    # DEPRECATED ALIASES - Will be removed in a future version
    # These allow existing config entries using old names to still work
    # -------------------------------------------------------------------------
    SNA = "EG4_OFFGRID"  # Deprecated since v0.8.0: use EG4_OFFGRID
    PV_SERIES = "EG4_HYBRID"  # Deprecated since v0.8.0: use EG4_HYBRID
    LXP_EU = "LXP"  # Deprecated since v0.8.0: use LXP
    LXP_LV = "LXP"  # Deprecated since v0.8.0: use LXP (same register maps)


class GridType(str, Enum):
    """Grid configuration type."""

    # Split-phase (US residential: 120V/240V)
    SPLIT_PHASE = "split_phase"

    # Single-phase (EU: 230V)
    SINGLE_PHASE = "single_phase"

    # Three-phase (commercial/industrial)
    THREE_PHASE = "three_phase"

    # Unknown grid type
    UNKNOWN = "unknown"


def resolve_family(name: str | InverterFamily) -> InverterFamily:
    """Resolve an inverter family name to its canonical InverterFamily enum.

    This function handles both current and deprecated family names, emitting
    a DeprecationWarning when a deprecated name is used.

    Args:
        name: Family name string or InverterFamily enum value

    Returns:
        The canonical InverterFamily enum value

    Raises:
        ValueError: If the name is not a valid family name

    Example:
        >>> resolve_family("EG4_HYBRID")  # Current name - no warning
        <InverterFamily.EG4_HYBRID: 'EG4_HYBRID'>

        >>> resolve_family("PV_SERIES")  # Deprecated - emits warning
        DeprecationWarning: InverterFamily 'PV_SERIES' is deprecated...
        <InverterFamily.EG4_HYBRID: 'EG4_HYBRID'>
    """
    # If already an enum, return as-is
    if isinstance(name, InverterFamily):
        return name

    # Check if it's a deprecated name
    if name in _DEPRECATED_FAMILY_NAMES:
        new_name = _DEPRECATED_FAMILY_NAMES[name]
        warnings.warn(
            f"InverterFamily '{name}' is deprecated since v0.8.0. Use '{new_name}' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return InverterFamily(new_name)

    # Try to resolve as a current name
    try:
        return InverterFamily(name)
    except ValueError as e:
        raise ValueError(
            f"Unknown inverter family: '{name}'. "
            f"Valid families: {[f.value for f in InverterFamily if f.value == f.name]}"
        ) from e


# Device type code to family mapping
# These values come from HOLD_DEVICE_TYPE_CODE (register 19)
DEVICE_TYPE_CODE_TO_FAMILY: dict[int, InverterFamily] = {
    # EG4 Off-Grid Series (12000XP, 6000XP)
    54: InverterFamily.EG4_OFFGRID,
    # EG4 Hybrid Series (18kPV, 12kPV, FlexBOSS21, FlexBOSS18)
    2092: InverterFamily.EG4_HYBRID,  # 18KPV, 12kPV
    10284: InverterFamily.EG4_HYBRID,  # FlexBOSS21, FlexBOSS18
    # Luxpower Series (LXP-EU, LXP-LB-BR, LXP-LV - all use same register maps)
    12: InverterFamily.LXP,  # LXP-EU 12K
    44: InverterFamily.LXP,  # LXP-LB-BR 10K (Brazil)
    # Add more mappings as devices are discovered
    # Note: GridBOSS (device type code 50) uses API deviceType=9 and is handled
    # separately as a MID (Main Interconnect Device) controller, not as an inverter
}


# Known feature sets by model family
# These represent the default capabilities for each family
FAMILY_DEFAULT_FEATURES: dict[InverterFamily, dict[str, bool]] = {
    InverterFamily.EG4_OFFGRID: {
        # EG4 Off-Grid Series (12000XP, 6000XP) - no grid sellback
        "split_phase": True,
        "off_grid_capable": True,
        "discharge_recovery_hysteresis": True,  # HOLD_DISCHG_RECOVERY_LAG_SOC/VOLT
        "quick_charge_minute": True,  # SNA_HOLD_QUICK_CHARGE_MINUTE
        "three_phase_capable": False,
        "parallel_support": False,  # Single inverter typically
        "volt_watt_curve": False,
        "grid_peak_shaving": True,
        "drms_support": False,
    },
    InverterFamily.EG4_HYBRID: {
        # EG4 Hybrid Series (18kPV, 12kPV, FlexBOSS) - grid-tied with sellback
        # US markets use split-phase L1/L2 registers (127-128, 140-141)
        # R/S/T registers (17-19, 20-22) contain garbage on US split-phase installations
        "split_phase": True,
        "off_grid_capable": True,
        "discharge_recovery_hysteresis": False,
        "quick_charge_minute": False,
        "three_phase_capable": False,
        "parallel_support": True,
        "volt_watt_curve": True,
        "grid_peak_shaving": True,
        "drms_support": True,
    },
    InverterFamily.LXP: {
        # Luxpower Series (LXP-EU, LXP-LB-BR, LXP-LV) - all use same register maps
        # Feature availability varies by model but register layout is identical
        "split_phase": False,
        "off_grid_capable": True,
        "discharge_recovery_hysteresis": False,
        "quick_charge_minute": False,
        "three_phase_capable": True,  # Some models support 3-phase
        "parallel_support": True,
        "volt_watt_curve": True,  # Some models support volt-watt
        "grid_peak_shaving": True,
        "drms_support": True,  # Some models support DRMS
        "eu_grid_compliance": True,
    },
    InverterFamily.UNKNOWN: {
        # Conservative defaults for unknown models
        "split_phase": False,
        "off_grid_capable": True,
        "discharge_recovery_hysteresis": False,
        "quick_charge_minute": False,
        "three_phase_capable": False,
        "parallel_support": False,
        "volt_watt_curve": False,
        "grid_peak_shaving": False,
        "drms_support": False,
    },
}


@dataclass
class InverterModelInfo:
    """Model information from HOLD_MODEL register and API-decoded fields.

    The HOLD_MODEL register (registers 0-1) contains a bitfield with
    hardware configuration information. The API decodes this bitfield
    and returns individual fields like HOLD_MODEL_lithiumType, etc.

    This class stores either:
    1. API-decoded fields (preferred, from parameters like HOLD_MODEL_*)
    2. Raw value for reference (bit layout varies by firmware)

    Example raw values:
        - SNA12K-US: 0x90AC1 (592577)
        - 18KPV: 0x986C0 (624320)
        - LXP-EU 12K: 0x19AC0 (105152)
    """

    # Raw model value (32-bit from registers 0-1)
    raw_value: int = 0

    # Decoded fields (from API HOLD_MODEL_* parameters)
    battery_type: int = 0  # 0=Lead-acid, 1=Lithium primary, 2=Hybrid
    lead_acid_type: int = 0  # Lead-acid battery subtype
    lithium_type: int = 0  # Lithium battery protocol (1-6+)
    measurement: int = 0  # Measurement unit type
    meter_brand: int = 0  # CT meter brand
    meter_type: int = 0  # CT meter type
    power_rating: int = 0  # Power rating code (6=12K, 7=15K, 8=18K)
    rule: int = 0  # Grid compliance rule
    rule_mask: int = 0  # Grid compliance mask
    us_version: bool = False  # True for US market, False for EU/other
    wireless_meter: bool = False  # True if wireless CT meter

    @classmethod
    def from_raw(cls, raw_value: int) -> InverterModelInfo:
        """Create InverterModelInfo with just the raw value.

        Note: The raw value bit layout varies by firmware version, so
        individual fields will remain at defaults. Use from_parameters()
        when API-decoded fields are available.

        Args:
            raw_value: Raw 32-bit value from HOLD_MODEL register

        Returns:
            InverterModelInfo with raw_value set
        """
        return cls(raw_value=raw_value)

    @classmethod
    def from_parameters(cls, params: dict[str, int | str | bool]) -> InverterModelInfo:
        """Create InverterModelInfo from API-decoded parameters.

        The API returns individual HOLD_MODEL_* fields that are already
        decoded from the raw register value.

        Args:
            params: Dictionary containing HOLD_MODEL_* parameters

        Returns:
            InverterModelInfo with all fields populated
        """

        def get_int(key: str, default: int = 0) -> int:
            val = params.get(key, default)
            if isinstance(val, str):
                try:
                    return int(val)
                except ValueError:
                    return default
            return int(val) if val is not None else default

        def get_bool(key: str, default: bool = False) -> bool:
            val = params.get(key, default)
            if isinstance(val, str):
                return val.lower() in ("1", "true", "yes")
            return bool(val) if val is not None else default

        # Parse raw HOLD_MODEL value
        hold_model = params.get("HOLD_MODEL", "0x0")
        if isinstance(hold_model, str) and hold_model.startswith("0x"):
            raw_value = int(hold_model, 16)
        elif isinstance(hold_model, str) and hold_model.isdigit():
            raw_value = int(hold_model)
        else:
            raw_value = int(hold_model) if hold_model else 0

        return cls(
            raw_value=raw_value,
            battery_type=get_int("HOLD_MODEL_batteryType"),
            lead_acid_type=get_int("HOLD_MODEL_leadAcidType"),
            lithium_type=get_int("HOLD_MODEL_lithiumType"),
            measurement=get_int("HOLD_MODEL_measurement"),
            meter_brand=get_int("HOLD_MODEL_meterBrand"),
            meter_type=get_int("HOLD_MODEL_meterType"),
            power_rating=get_int("HOLD_MODEL_powerRating"),
            rule=get_int("HOLD_MODEL_rule"),
            rule_mask=get_int("HOLD_MODEL_ruleMask"),
            us_version=get_bool("HOLD_MODEL_usVersion"),
            wireless_meter=get_bool("HOLD_MODEL_wirelessMeter"),
        )

    @property
    def power_rating_kw(self) -> int:
        """Get power rating in kilowatts.

        Returns:
            Nominal power rating in kW, or 0 if unknown
        """
        # Power rating codes observed:
        # 6 = 12kW, 7 = 15kW, 8 = 18kW, 9 = 21kW
        rating_map = {
            4: 6,  # 6kW
            5: 8,  # 8kW
            6: 12,  # 12kW
            7: 15,  # 15kW
            8: 18,  # 18kW
            9: 21,  # 21kW
        }
        return rating_map.get(self.power_rating, 0)

    @property
    def lithium_protocol_name(self) -> str:
        """Get lithium battery protocol name.

        Returns:
            Protocol name string
        """
        # Lithium type codes observed:
        # 1 = Standard lithium, 2 = EG4 protocol, 6 = EU protocol
        protocol_map = {
            0: "None",
            1: "Standard",
            2: "EG4",
            3: "Pylontech",
            4: "Growatt",
            5: "BYD",
            6: "EU Standard",
        }
        return protocol_map.get(self.lithium_type, f"Unknown ({self.lithium_type})")


@dataclass
class InverterFeatures:
    """Detected inverter feature capabilities.

    This class tracks which features are available on a specific inverter,
    determined through a combination of:
    - Device type code (HOLD_DEVICE_TYPE_CODE register)
    - Model family lookup
    - Runtime parameter probing

    All feature flags default to False (conservative approach).
    """

    # Device identification
    device_type_code: int = 0
    model_family: InverterFamily = InverterFamily.UNKNOWN
    model_info: InverterModelInfo = field(default_factory=InverterModelInfo)

    # Grid configuration
    grid_type: GridType = GridType.UNKNOWN

    # Hardware capabilities
    split_phase: bool = False  # Split-phase grid (US 120V/240V)
    three_phase_capable: bool = False  # Three-phase grid support
    off_grid_capable: bool = True  # Off-grid/EPS mode support
    parallel_support: bool = False  # Multi-inverter parallel operation

    # Control features
    discharge_recovery_hysteresis: bool = False  # SOC/Volt hysteresis on recovery
    quick_charge_minute: bool = False  # SNA quick charge minute setting
    volt_watt_curve: bool = False  # Volt-Watt curve support
    grid_peak_shaving: bool = False  # Grid peak shaving support
    drms_support: bool = False  # DRMS (demand response) support
    eu_grid_compliance: bool = False  # EU grid compliance features

    # Runtime-detected capabilities (probed from actual registers)
    has_sna_registers: bool = False  # SNA-specific registers present
    has_pv_series_registers: bool = False  # PV series registers present

    @classmethod
    def from_device_type_code(cls, device_type_code: int) -> InverterFeatures:
        """Create features instance from device type code.

        Args:
            device_type_code: Value from HOLD_DEVICE_TYPE_CODE register

        Returns:
            InverterFeatures with family defaults applied
        """
        family = DEVICE_TYPE_CODE_TO_FAMILY.get(device_type_code, InverterFamily.UNKNOWN)
        unknown_defaults = FAMILY_DEFAULT_FEATURES[InverterFamily.UNKNOWN]
        defaults = FAMILY_DEFAULT_FEATURES.get(family, unknown_defaults)

        features = cls(
            device_type_code=device_type_code,
            model_family=family,
        )

        # Apply family defaults
        for key, value in defaults.items():
            if hasattr(features, key):
                setattr(features, key, value)

        # Set grid type based on family
        if family in (InverterFamily.EG4_OFFGRID, InverterFamily.EG4_HYBRID):
            # EG4 inverters in US markets use split-phase (120V/240V)
            features.grid_type = GridType.SPLIT_PHASE
        elif family == InverterFamily.LXP:
            features.grid_type = GridType.SINGLE_PHASE  # Can also be three-phase

        return features


def get_inverter_family(device_type_code: int) -> InverterFamily:
    """Get inverter family from device type code.

    Args:
        device_type_code: Value from HOLD_DEVICE_TYPE_CODE register

    Returns:
        InverterFamily enum value
    """
    return DEVICE_TYPE_CODE_TO_FAMILY.get(device_type_code, InverterFamily.UNKNOWN)


def get_family_features(family: InverterFamily) -> dict[str, bool]:
    """Get default feature set for a model family.

    Args:
        family: InverterFamily enum value

    Returns:
        Dictionary of feature name to enabled status
    """
    unknown_defaults = FAMILY_DEFAULT_FEATURES[InverterFamily.UNKNOWN]
    return FAMILY_DEFAULT_FEATURES.get(family, unknown_defaults).copy()
