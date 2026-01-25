"""Configuration classes for transport layer.

This module provides configuration classes for defining local transports
that can be attached to HTTP-discovered devices for hybrid mode operation.

It supports serialization to/from dictionaries for Home Assistant config entries.

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

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pylxpweb.devices.inverters._features import InverterFamily


class TransportType(str, Enum):
    """Types of local transports supported for hybrid mode.

    These transports can be attached to HTTP-discovered devices to enable
    local data fetching with automatic HTTP fallback.

    String enum for easy serialization and comparison.
    """

    MODBUS_TCP = "modbus_tcp"
    """Modbus TCP transport via RS485-to-Ethernet adapter."""

    WIFI_DONGLE = "wifi_dongle"
    """WiFi dongle transport via inverter's built-in WiFi dongle."""

    HTTP = "http"
    """HTTP cloud API (for hybrid mode reference)."""


@dataclass
class TransportConfig:
    """Configuration for a local transport connection.

    This class holds all parameters needed to create a local transport
    for a specific inverter. Used with Station.attach_local_transports()
    to enable hybrid mode operation.

    Supports validation and serialization for storage in Home Assistant config entries.

    Attributes:
        host: IP address or hostname of the transport endpoint.
        port: TCP port number for the connection.
        serial: Serial number of the inverter this transport connects to.
        transport_type: Type of transport (Modbus TCP or WiFi Dongle).
        inverter_family: Optional inverter family for register map selection.
        unit_id: Modbus unit ID (only for MODBUS_TCP, default: 1).
        dongle_serial: Dongle serial number (only for WIFI_DONGLE).
        timeout: Connection timeout in seconds (default: 10.0).

    Example:
        ```python
        from pylxpweb.transports.config import TransportConfig, TransportType

        # Modbus TCP configuration
        modbus_config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
            unit_id=1,
        )

        # WiFi Dongle configuration
        dongle_config = TransportConfig(
            host="192.168.1.101",
            port=8000,
            serial="CE87654321",
            transport_type=TransportType.WIFI_DONGLE,
            dongle_serial="BA12345678",
        )
        ```
    """

    host: str
    """IP address or hostname of the transport endpoint."""

    port: int
    """TCP port number for the connection."""

    serial: str
    """Serial number of the inverter this transport connects to."""

    transport_type: TransportType
    """Type of transport (Modbus TCP or WiFi Dongle)."""

    inverter_family: InverterFamily | None = None
    """Optional inverter family for register map selection."""

    unit_id: int = field(default=1)
    """Modbus unit ID (only for MODBUS_TCP transport)."""

    dongle_serial: str | None = field(default=None)
    """Dongle serial number (only for WIFI_DONGLE transport)."""

    timeout: float = field(default=10.0)
    """Connection timeout in seconds."""

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        self.validate()

    def validate(self) -> None:
        """Validate configuration completeness.

        Checks that all required fields are present and valid for the
        specified transport type.

        Raises:
            ValueError: If configuration is invalid
        """
        # HTTP transport has relaxed validation (used for hybrid mode reference only)
        if self.transport_type == TransportType.HTTP:
            if not self.serial:
                raise ValueError("serial is required")
            return

        # Local transports require host and port
        if not self.host:
            raise ValueError("host is required")
        if self.port <= 0 or self.port > 65535:
            raise ValueError(f"Invalid port: {self.port}")
        if not self.serial:
            raise ValueError("serial is required")
        if self.transport_type == TransportType.WIFI_DONGLE and not self.dongle_serial:
            raise ValueError("dongle_serial is required for WiFi dongle transport")

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

        # Create instance without validation (we'll validate after)
        instance = object.__new__(cls)
        instance.host = data.get("host", "")
        instance.port = data.get("port", 502)
        instance.serial = data.get("serial", "")
        instance.transport_type = transport_type
        instance.inverter_family = inverter_family
        instance.dongle_serial = data.get("dongle_serial")
        instance.timeout = data.get("timeout", 10.0)
        instance.unit_id = data.get("unit_id", 1)

        # Validate the restored config
        instance.validate()
        return instance


@dataclass
class AttachResult:
    """Result of attaching local transports to station devices.

    This class reports the outcome of Station.attach_local_transports(),
    indicating which transports were successfully connected, which had
    no matching device, and which failed to connect.

    Attributes:
        matched: Number of transports successfully attached to devices.
        unmatched: Number of transports with no matching device serial.
        failed: Number of transports that failed to connect.
        unmatched_serials: List of serial numbers with no matching device.
        failed_serials: List of serial numbers that failed to connect.

    Example:
        ```python
        result = await station.attach_local_transports(configs)
        if result.matched > 0:
            print(f"Successfully attached {result.matched} transport(s)")
        if result.unmatched_serials:
            print(f"No devices found for: {result.unmatched_serials}")
        if result.failed_serials:
            print(f"Failed to connect: {result.failed_serials}")
        ```
    """

    matched: int = 0
    """Number of transports successfully attached to devices."""

    unmatched: int = 0
    """Number of transports with no matching device serial."""

    failed: int = 0
    """Number of transports that failed to connect."""

    unmatched_serials: list[str] = field(default_factory=list)
    """List of serial numbers with no matching device."""

    failed_serials: list[str] = field(default_factory=list)
    """List of serial numbers that failed to connect."""


__all__ = [
    "TransportType",
    "TransportConfig",
    "AttachResult",
]
