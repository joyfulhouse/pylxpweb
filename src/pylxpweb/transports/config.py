"""Transport configuration for local device discovery.

This module provides the TransportConfig dataclass for configuring
transport instances in a uniform way, supporting serialization to/from
dictionaries for Home Assistant config entries.

Example:
    # Create a Modbus transport config
    config = TransportConfig(
        host="192.168.1.100",
        port=502,
        serial="CE12345678",
        transport_type=TransportType.MODBUS_TCP,
        inverter_family=InverterFamily.PV_SERIES,
    )
    config.validate()

    # Serialize to dict for storage
    data = config.to_dict()

    # Restore from dict
    restored = TransportConfig.from_dict(data)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pylxpweb.devices.inverters._features import InverterFamily


class TransportType(str, Enum):
    """Transport type enumeration.

    String enum for easy serialization and comparison.
    """

    # Modbus TCP via RS485-to-Ethernet adapter
    MODBUS_TCP = "modbus_tcp"

    # WiFi dongle direct TCP connection (port 8000)
    WIFI_DONGLE = "wifi_dongle"

    # HTTP cloud API (for hybrid mode reference)
    HTTP = "http"


@dataclass
class TransportConfig:
    """Configuration for a single transport connection.

    This dataclass encapsulates all parameters needed to create a
    transport instance (Modbus or Dongle). It supports validation
    and serialization for storage in Home Assistant config entries.

    Attributes:
        host: IP address or hostname of the device
        port: TCP port (502 for Modbus, 8000 for dongle)
        serial: Device serial number (10 characters)
        transport_type: Type of transport (MODBUS_TCP, WIFI_DONGLE, or HTTP)
        inverter_family: Model family for register mapping (None = auto-detect)
        dongle_serial: Required for WIFI_DONGLE transport only (10 characters)
        timeout: Connection timeout in seconds (default 10.0)
        unit_id: Modbus unit ID (default 1, only for Modbus)

    Example:
        # Modbus configuration
        modbus_config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
        )

        # WiFi dongle configuration
        dongle_config = TransportConfig(
            host="192.168.1.101",
            port=8000,
            serial="CE12345678",
            transport_type=TransportType.WIFI_DONGLE,
            dongle_serial="BA12345678",
        )
    """

    host: str
    port: int
    serial: str
    transport_type: TransportType
    inverter_family: InverterFamily | None = None
    dongle_serial: str | None = None
    timeout: float = 10.0
    unit_id: int = 1

    def validate(self) -> None:
        """Validate configuration completeness.

        Checks that all required fields are present and valid for the
        specified transport type.

        Raises:
            ValueError: If configuration is invalid
        """
        # Serial number validation (applies to Modbus and Dongle)
        if self.transport_type != TransportType.HTTP and (
            not self.serial or len(self.serial) != 10
        ):
            raise ValueError("serial must be 10 characters")

        # Dongle-specific validation
        if self.transport_type == TransportType.WIFI_DONGLE:
            if not self.dongle_serial:
                raise ValueError("dongle_serial required for WIFI_DONGLE transport")
            if len(self.dongle_serial) != 10:
                raise ValueError("dongle_serial must be 10 characters")

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary for serialization.

        Returns:
            Dictionary with all configuration values, suitable for
            JSON serialization and storage in Home Assistant config entries.
        """
        return {
            "host": self.host,
            "port": self.port,
            "serial": self.serial,
            "transport_type": self.transport_type.value,
            "inverter_family": self.inverter_family.value if self.inverter_family else None,
            "dongle_serial": self.dongle_serial,
            "timeout": self.timeout,
            "unit_id": self.unit_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TransportConfig:
        """Create configuration from dictionary.

        Args:
            data: Dictionary with configuration values (from to_dict() or
                Home Assistant config entry)

        Returns:
            TransportConfig instance with values from dictionary
        """
        from pylxpweb.devices.inverters._features import InverterFamily

        # Parse transport type
        transport_type_str = data.get("transport_type", "modbus_tcp")
        transport_type = TransportType(transport_type_str)

        # Parse inverter family if present
        family_str = data.get("inverter_family")
        inverter_family = InverterFamily(family_str) if family_str else None

        return cls(
            host=data.get("host", ""),
            port=data.get("port", 502),
            serial=data.get("serial", ""),
            transport_type=transport_type,
            inverter_family=inverter_family,
            dongle_serial=data.get("dongle_serial"),
            timeout=data.get("timeout", 10.0),
            unit_id=data.get("unit_id", 1),
        )


__all__ = [
    "TransportConfig",
    "TransportType",
]
