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
from .register_maps import (
    EnergyRegisterMap,
    RegisterField,
    RuntimeRegisterMap,
    get_energy_map,
    get_runtime_map,
)

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
    # Register maps
    "RegisterField",
    "RuntimeRegisterMap",
    "EnergyRegisterMap",
    "get_runtime_map",
    "get_energy_map",
    # Exceptions
    "TransportError",
    "TransportConnectionError",
    "TransportTimeoutError",
    "TransportReadError",
    "TransportWriteError",
    "UnsupportedOperationError",
]

# Deprecated register map aliases — forwarded via __getattr__
_DEPRECATED_MAP_ALIASES: dict[str, str] = {
    "PV_SERIES_RUNTIME_MAP": "EG4_HYBRID_RUNTIME_MAP",
    "PV_SERIES_ENERGY_MAP": "EG4_HYBRID_ENERGY_MAP",
    "LXP_EU_RUNTIME_MAP": "LXP_RUNTIME_MAP",
    "LXP_EU_ENERGY_MAP": "LXP_ENERGY_MAP",
}


def __getattr__(name: str) -> object:
    if name in _DEPRECATED_MAP_ALIASES:
        import warnings

        new_name = _DEPRECATED_MAP_ALIASES[name]
        warnings.warn(
            f"'{name}' is deprecated. Use '{new_name}' from "
            "pylxpweb.transports.register_maps instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from . import register_maps

        return getattr(register_maps, new_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
