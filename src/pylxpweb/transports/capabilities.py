"""Transport capabilities definition.

This module defines what operations each transport type can perform,
allowing clients to check capabilities before attempting operations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransportCapabilities:
    """Defines what operations a transport can perform.

    Clients can check these capabilities to gracefully handle
    feature differences between HTTP and Modbus transports.

    Attributes:
        can_read_runtime: Can read real-time inverter data
        can_read_energy: Can read energy statistics
        can_read_battery: Can read battery bank information
        can_read_parameters: Can read configuration registers
        can_write_parameters: Can write configuration registers
        can_discover_devices: Can discover devices (HTTP only)
        can_read_history: Can read historical data (HTTP only)
        can_read_analytics: Can read analytics data (HTTP only)
        can_trigger_firmware_update: Can trigger firmware updates (HTTP only)
        can_read_parallel_group_energy: Can read parallel group totals (HTTP only)
        min_poll_interval_seconds: Minimum recommended polling interval
        supports_concurrent_reads: Can perform concurrent register reads
        requires_authentication: Requires login/authentication
        is_local: Operates on local network (no cloud dependency)
    """

    # Core data access
    can_read_runtime: bool = True
    can_read_energy: bool = True
    can_read_battery: bool = True
    can_read_parameters: bool = True
    can_write_parameters: bool = True

    # Cloud-only features
    can_discover_devices: bool = False
    can_read_history: bool = False
    can_read_analytics: bool = False
    can_trigger_firmware_update: bool = False
    can_read_parallel_group_energy: bool = False

    # Performance characteristics
    min_poll_interval_seconds: float = 1.0
    supports_concurrent_reads: bool = True

    # Connection characteristics
    requires_authentication: bool = False
    is_local: bool = False


# Predefined capability sets for each transport type

HTTP_CAPABILITIES = TransportCapabilities(
    # Core access - all supported
    can_read_runtime=True,
    can_read_energy=True,
    can_read_battery=True,
    can_read_parameters=True,
    can_write_parameters=True,
    # Cloud features - all supported
    can_discover_devices=True,
    can_read_history=True,
    can_read_analytics=True,
    can_trigger_firmware_update=True,
    can_read_parallel_group_energy=True,
    # Performance - rate limited
    min_poll_interval_seconds=30.0,  # Cloud API rate limiting
    supports_concurrent_reads=True,
    # Connection
    requires_authentication=True,
    is_local=False,
)

MODBUS_CAPABILITIES = TransportCapabilities(
    # Core access - all supported
    can_read_runtime=True,
    can_read_energy=True,  # Via input registers
    can_read_battery=True,  # Via input registers
    can_read_parameters=True,
    can_write_parameters=True,
    # Cloud features - not available
    can_discover_devices=False,
    can_read_history=False,
    can_read_analytics=False,
    can_trigger_firmware_update=False,
    can_read_parallel_group_energy=False,
    # Performance - no rate limiting
    min_poll_interval_seconds=1.0,  # Local network, minimal delay
    supports_concurrent_reads=True,
    # Connection
    requires_authentication=False,
    is_local=True,
)
