"""Constants and mappings for Luxpower/EG4 API.

This module contains mapping tables extracted from the EG4 web interface
to convert between human-readable API values and the enum values required
for configuration updates.

These mappings were discovered by analyzing the HTML form at:
/WManage/web/config/plant/edit/{plant_id}
"""

from __future__ import annotations

# Timezone mappings: Human-readable (from API) → Form enum (for POST)
# Source: Analyzed all 28 timezone options from the HTML form
TIMEZONE_MAP: dict[str, str] = {
    "GMT -12": "WEST12",
    "GMT -11": "WEST11",
    "GMT -10": "WEST10",
    "GMT -9": "WEST9",
    "GMT -8": "WEST8",
    "GMT -7": "WEST7",
    "GMT -6": "WEST6",
    "GMT -5": "WEST5",
    "GMT -4": "WEST4",
    "GMT -3": "WEST3",
    "GMT -2": "WEST2",
    "GMT -1": "WEST1",
    "GMT 0": "ZERO",
    "GMT +1": "EAST1",
    "GMT +2": "EAST2",
    "GMT +3": "EAST3",
    "GMT +3:30": "EAST3_30",
    "GMT +4": "EAST4",
    "GMT +5": "EAST5",
    "GMT +5:30": "EAST5_30",
    "GMT +6": "EAST6",
    "GMT +6:30": "EAST6_30",
    "GMT +7": "EAST7",
    "GMT +8": "EAST8",
    "GMT +9": "EAST9",
    "GMT +10": "EAST10",
    "GMT +11": "EAST11",
    "GMT +12": "EAST12",
}

# Reverse mapping: Form enum → Human-readable
TIMEZONE_REVERSE_MAP: dict[str, str] = {v: k for k, v in TIMEZONE_MAP.items()}

# Country mappings: Human-readable (from API) → Form enum (for POST)
# Source: Analyzed country options from HTML form (North America region shown)
# NOTE: This list is incomplete - only shows North American countries
# Additional countries would appear based on selected continent/region
COUNTRY_MAP: dict[str, str] = {
    "Canada": "CANADA",
    "United States of America": "UNITED_STATES_OF_AMERICA",
    "Mexico": "MEXICO",
    "Greenland": "GREENLAND",
}

# Reverse mapping: Form enum → Human-readable
COUNTRY_REVERSE_MAP: dict[str, str] = {v: k for k, v in COUNTRY_MAP.items()}

# Continent mappings: Human-readable → Form enum
# Source: All 6 continent options from HTML form
CONTINENT_MAP: dict[str, str] = {
    "Africa": "AFRICA",
    "Asia": "ASIA",
    "Europe": "EUROPE",
    "North America": "NORTH_AMERICA",
    "Oceania": "OCEANIA",
    "South America": "SOUTH_AMERICA",
}

CONTINENT_REVERSE_MAP: dict[str, str] = {v: k for k, v in CONTINENT_MAP.items()}

# Region mappings: Human-readable → Form enum
# Source: Region options from HTML form (context: North America continent)
# NOTE: Region options are hierarchical and depend on selected continent
REGION_MAP: dict[str, str] = {
    # North America regions (when continent = NORTH_AMERICA)
    "Caribbean": "CARIBBEAN",
    "Central America": "CENTRAL_AMERICA",
    "North America": "NORTH_AMERICA",
    # Additional regions would be discovered when exploring other continents
}

REGION_REVERSE_MAP: dict[str, str] = {v: k for k, v in REGION_MAP.items()}


def get_timezone_enum(human_readable: str) -> str:
    """Convert human-readable timezone to API enum.

    Args:
        human_readable: Timezone string like "GMT -8"

    Returns:
        API enum like "WEST8"

    Raises:
        ValueError: If timezone is not recognized
    """
    if human_readable in TIMEZONE_MAP:
        return TIMEZONE_MAP[human_readable]
    raise ValueError(f"Unknown timezone: {human_readable}")


def get_country_enum(human_readable: str) -> str:
    """Convert human-readable country to API enum.

    Args:
        human_readable: Country string like "United States of America"

    Returns:
        API enum like "UNITED_STATES_OF_AMERICA"

    Raises:
        ValueError: If country is not recognized
    """
    if human_readable in COUNTRY_MAP:
        return COUNTRY_MAP[human_readable]
    raise ValueError(f"Unknown country: {human_readable}")


def get_region_enum(human_readable: str) -> str:
    """Convert human-readable region to API enum.

    Args:
        human_readable: Region string like "North America"

    Returns:
        API enum like "NORTH_AMERICA"

    Raises:
        ValueError: If region is not recognized
    """
    if human_readable in REGION_MAP:
        return REGION_MAP[human_readable]
    raise ValueError(f"Unknown region: {human_readable}")


def get_continent_enum(human_readable: str) -> str:
    """Convert human-readable continent to API enum.

    Args:
        human_readable: Continent string like "North America"

    Returns:
        API enum like "NORTH_AMERICA"

    Raises:
        ValueError: If continent is not recognized
    """
    if human_readable in CONTINENT_MAP:
        return CONTINENT_MAP[human_readable]
    raise ValueError(f"Unknown continent: {human_readable}")


# Static mapping for common countries (fast path)
# This covers the most frequently used countries to avoid API calls
COUNTRY_TO_LOCATION_STATIC: dict[str, tuple[str, str]] = {
    # North America
    "United States of America": ("NORTH_AMERICA", "NORTH_AMERICA"),
    "Canada": ("NORTH_AMERICA", "NORTH_AMERICA"),
    "Mexico": ("NORTH_AMERICA", "CENTRAL_AMERICA"),
    "Greenland": ("NORTH_AMERICA", "NORTH_AMERICA"),
    # Europe (common)
    "United Kingdom": ("EUROPE", "WESTERN_EUROPE"),
    "Germany": ("EUROPE", "CENTRAL_EUROPE"),
    "France": ("EUROPE", "WESTERN_EUROPE"),
    "Spain": ("EUROPE", "SOUTHERN_EUROPE"),
    "Italy": ("EUROPE", "SOUTHERN_EUROPE"),
    "The Netherlands": ("EUROPE", "WESTERN_EUROPE"),
    "Belgium": ("EUROPE", "WESTERN_EUROPE"),
    "Switzerland": ("EUROPE", "CENTRAL_EUROPE"),
    "Austria": ("EUROPE", "CENTRAL_EUROPE"),
    "Poland": ("EUROPE", "CENTRAL_EUROPE"),
    "Sweden": ("EUROPE", "NORDIC_EUROPE"),
    "Norway": ("EUROPE", "NORDIC_EUROPE"),
    "Denmark": ("EUROPE", "NORDIC_EUROPE"),
    # Asia (common)
    "China": ("ASIA", "EAST_ASIA"),
    "Japan": ("ASIA", "EAST_ASIA"),
    "South korea": ("ASIA", "EAST_ASIA"),
    "India": ("ASIA", "SOUTH_ASIA"),
    "Singapore": ("ASIA", "SOUTHEAST_ASIA"),
    "Thailand": ("ASIA", "SOUTHEAST_ASIA"),
    "Malaysia": ("ASIA", "SOUTHEAST_ASIA"),
    "Indonesia": ("ASIA", "SOUTHEAST_ASIA"),
    "Philippines": ("ASIA", "SOUTHEAST_ASIA"),
    "Vietnam": ("ASIA", "SOUTHEAST_ASIA"),
    # Oceania
    "Australia": ("OCEANIA", "OCEANIA"),
    "New Zealand": ("OCEANIA", "OCEANIA"),
    # South America
    "Brazil": ("SOUTH_AMERICA", "SA_EAST"),
    "Argentina": ("SOUTH_AMERICA", "SA_SOUTHERN_PART"),  # Note: API has "Aregntine" typo
    "Chile": ("SOUTH_AMERICA", "SA_SOUTHERN_PART"),
    # Africa (common)
    "South Africa": ("AFRICA", "SOUTH_AFRICA"),
    "Egypt": ("AFRICA", "NORTH_AFRICA"),
}


def get_continent_region_from_country(country_human: str) -> tuple[str, str]:
    """Derive continent and region enums from country name.

    Uses static mapping for common countries (fast path).
    For unknown countries, requires dynamic fetching from locale API.

    Args:
        country_human: Human-readable country name from API

    Returns:
        Tuple of (continent_enum, region_enum)

    Raises:
        ValueError: If country is not in static mapping (requires dynamic fetch)
    """
    # Fast path: check static mapping
    if country_human in COUNTRY_TO_LOCATION_STATIC:
        return COUNTRY_TO_LOCATION_STATIC[country_human]

    # Country not in static mapping - requires dynamic fetch
    raise ValueError(
        f"Country '{country_human}' not in static mapping. "
        "Dynamic fetching from locale API required."
    )
