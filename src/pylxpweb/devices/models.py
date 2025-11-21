"""Device and entity models for pylxpweb.

This module provides generic models for representing devices and their
entities (sensors, controls, etc.) in a platform-agnostic way.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DeviceInfo(BaseModel):
    """Device information model.

    Represents a physical device with metadata and hierarchy information.

    Example:
        ```python
        device_info = DeviceInfo(
            identifiers={("pylxpweb", "inverter_1234567890")},
            name="FlexBOSS21 Inverter",
            manufacturer="EG4 Electronics",
            model="FlexBOSS21",
            sw_version="34",
            via_device=("pylxpweb", "station_12345"),
        )
        ```
    """

    identifiers: set[tuple[str, str]] = Field(
        description="Set of (domain, unique_id) tuples that identify this device"
    )
    name: str = Field(description="Human-readable device name")
    manufacturer: str = Field(description="Device manufacturer")
    model: str = Field(description="Device model name")
    sw_version: str | None = Field(default=None, description="Software/firmware version")
    via_device: tuple[str, str] | None = Field(
        default=None, description="Parent device identifier (domain, unique_id)"
    )
    hw_version: str | None = Field(default=None, description="Hardware version")
    configuration_url: str | None = Field(
        default=None, description="URL to device configuration page"
    )

    model_config = {"frozen": False}


class Entity(BaseModel):
    """Entity representation model.

    Represents a single data point or control (sensor, switch, button, etc.)
    from a device. Devices can have multiple entities.

    Example:
        ```python
        entity = Entity(
            unique_id="inverter_1234567890_pac",
            name="Inverter 1234567890 AC Power",
            device_class="power",
            state_class="measurement",
            unit_of_measurement="W",
            value=1030.5,
            attributes={"voltage": 240.0, "frequency": 60.0},
        )
        ```
    """

    unique_id: str = Field(description="Unique identifier for this entity")
    name: str = Field(description="Human-readable entity name")
    device_class: str | None = Field(
        default=None, description="Device class (power, energy, temperature, etc.)"
    )
    state_class: str | None = Field(
        default=None, description="State class (measurement, total, total_increasing)"
    )
    unit_of_measurement: str | None = Field(
        default=None, description="Unit of measurement (W, kWh, %, °C, V, etc.)"
    )
    value: Any = Field(description="Current entity value/state")
    attributes: dict[str, Any] = Field(
        default_factory=dict, description="Additional entity attributes"
    )
    icon: str | None = Field(default=None, description="Icon identifier (e.g., mdi:solar-power)")
    entity_category: str | None = Field(
        default=None, description="Entity category (config, diagnostic)"
    )

    model_config = {"frozen": False}


# Standard device classes (platform-agnostic)
class DeviceClass:
    """Standard device classes for entity categorization."""

    # Sensor device classes
    POWER = "power"
    ENERGY = "energy"
    BATTERY = "battery"
    VOLTAGE = "voltage"
    CURRENT = "current"
    TEMPERATURE = "temperature"
    FREQUENCY = "frequency"
    POWER_FACTOR = "power_factor"

    # Binary sensor device classes
    CONNECTIVITY = "connectivity"
    PROBLEM = "problem"


# Standard state classes
class StateClass:
    """Standard state classes for entity state behavior."""

    MEASUREMENT = "measurement"
    TOTAL = "total"
    TOTAL_INCREASING = "total_increasing"


# Standard entity categories
class EntityCategory:
    """Standard entity categories for organization."""

    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"
