"""Configuration classes for transport layer.

This module provides configuration classes for defining local transports
that can be attached to HTTP-discovered devices for hybrid mode operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pylxpweb.devices.inverters._features import InverterFamily


class TransportType(Enum):
    """Types of local transports supported for hybrid mode.

    These transports can be attached to HTTP-discovered devices to enable
    local data fetching with automatic HTTP fallback.
    """

    MODBUS_TCP = "modbus_tcp"
    """Modbus TCP transport via RS485-to-Ethernet adapter."""

    WIFI_DONGLE = "wifi_dongle"
    """WiFi dongle transport via inverter's built-in WiFi dongle."""


@dataclass
class TransportConfig:
    """Configuration for a local transport connection.

    This class holds all parameters needed to create a local transport
    for a specific inverter. Used with Station.attach_local_transports()
    to enable hybrid mode operation.

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

    dongle_serial: str = field(default="")
    """Dongle serial number (only for WIFI_DONGLE transport)."""

    timeout: float = field(default=10.0)
    """Connection timeout in seconds."""

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.host:
            raise ValueError("host is required")
        if self.port <= 0 or self.port > 65535:
            raise ValueError(f"Invalid port: {self.port}")
        if not self.serial:
            raise ValueError("serial is required")
        if self.transport_type == TransportType.WIFI_DONGLE and not self.dongle_serial:
            raise ValueError("dongle_serial is required for WiFi dongle transport")


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
