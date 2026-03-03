"""Transport layer abstraction for pylxpweb.

This module provides transport-agnostic communication with inverters,
supporting cloud HTTP API, local Modbus TCP, and WiFi dongle connections.

Usage:
    # HTTP Transport (cloud API) - using factory function
    from pylxpweb.transports import create_http_transport

    async with LuxpowerClient(username, password) as client:
        transport = create_http_transport(client, serial="CE12345678")
        await transport.connect()
        runtime = await transport.read_runtime()

    # Modbus Transport (RS485-to-Ethernet adapter) - using factory function
    from pylxpweb.transports import create_modbus_transport

    transport = create_modbus_transport(
        host="192.168.1.100",
        serial="CE12345678",
    )
    async with transport:
        runtime = await transport.read_runtime()

    # WiFi Dongle Transport (no additional hardware) - using factory function
    from pylxpweb.transports import create_dongle_transport

    transport = create_dongle_transport(
        host="192.168.1.100",
        dongle_serial="BA12345678",
        inverter_serial="CE12345678",
    )
    async with transport:
        runtime = await transport.read_runtime()  # Same interface!
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .capabilities import (
    DONGLE_CAPABILITIES,
    HTTP_CAPABILITIES,
    MODBUS_CAPABILITIES,
    TransportCapabilities,
)
from .config import (
    AttachResult,
    TransportConfig,
    TransportType,
)
from .data import (
    BatteryBankData,
    BatteryData,
    InverterEnergyData,
    InverterRuntimeData,
)
from .discovery import (
    HOLD_DEVICE_TYPE_CODE,
    HOLD_PARALLEL_NUMBER,
    HOLD_PARALLEL_PHASE,
    DeviceDiscoveryInfo,
    discover_device_info,
    discover_multiple_devices,
    get_model_family_name,
    get_parallel_group_key,
    group_by_parallel_config,
    is_gridboss_device,
)
from .dongle import DongleTransport
from .exceptions import (
    TransportConnectionError,
    TransportError,
    TransportReadError,
    TransportTimeoutError,
    TransportWriteError,
    UnsupportedOperationError,
)
from .factory import (
    ConnectionType,
    create_dongle_transport,
    create_http_transport,
    create_modbus_transport,
    create_serial_transport,
    create_transport,
    create_transport_from_config,
)
from .http import HTTPTransport
from .hybrid import HybridTransport
from .modbus import ModbusTransport
from .modbus_serial import ModbusSerialTransport
from .protocol import BaseTransport, InverterTransport

if TYPE_CHECKING:
    from .battery_modbus import BatteryModbusTransport


def __getattr__(name: str) -> type[BatteryModbusTransport]:
    """Lazy import for BatteryModbusTransport to avoid circular dependency.

    The battery_modbus module imports from battery_protocols, which imports
    from transports.data, creating a circular dependency at import time.
    """
    if name == "BatteryModbusTransport":
        from .battery_modbus import BatteryModbusTransport

        return BatteryModbusTransport
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Unified factory (recommended)
    "create_transport",
    "ConnectionType",
    # Legacy factory functions
    "create_http_transport",
    "create_modbus_transport",
    "create_serial_transport",
    "create_dongle_transport",
    "create_transport_from_config",
    # Configuration
    "TransportConfig",
    "TransportType",
    "AttachResult",
    # Protocol
    "InverterTransport",
    "BaseTransport",
    # Transport implementations
    "HTTPTransport",
    "ModbusTransport",
    "ModbusSerialTransport",
    "DongleTransport",
    "HybridTransport",
    "BatteryModbusTransport",
    # Discovery utilities
    "DeviceDiscoveryInfo",
    "HOLD_DEVICE_TYPE_CODE",
    "HOLD_PARALLEL_NUMBER",
    "HOLD_PARALLEL_PHASE",
    "discover_device_info",
    "discover_multiple_devices",
    "get_model_family_name",
    "get_parallel_group_key",
    "group_by_parallel_config",
    "is_gridboss_device",
    # Capabilities
    "TransportCapabilities",
    "HTTP_CAPABILITIES",
    "MODBUS_CAPABILITIES",
    "DONGLE_CAPABILITIES",
    # Data models
    "InverterRuntimeData",
    "InverterEnergyData",
    "BatteryBankData",
    "BatteryData",
    # Exceptions
    "TransportError",
    "TransportConnectionError",
    "TransportTimeoutError",
    "TransportReadError",
    "TransportWriteError",
    "UnsupportedOperationError",
]
