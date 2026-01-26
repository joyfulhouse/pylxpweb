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
from .factory import create_dongle_transport, create_http_transport, create_modbus_transport
from .http import HTTPTransport
from .modbus import ModbusTransport
from .protocol import BaseTransport, InverterTransport
from .register_maps import (
    LXP_EU_ENERGY_MAP,
    LXP_EU_RUNTIME_MAP,
    PV_SERIES_ENERGY_MAP,
    PV_SERIES_RUNTIME_MAP,
    EnergyRegisterMap,
    RegisterField,
    RuntimeRegisterMap,
    get_energy_map,
    get_runtime_map,
)

__all__ = [
    # Factory functions (recommended)
    "create_http_transport",
    "create_modbus_transport",
    "create_dongle_transport",
    # Protocol
    "InverterTransport",
    "BaseTransport",
    # Transport implementations
    "HTTPTransport",
    "ModbusTransport",
    "DongleTransport",
    # Configuration (for hybrid mode)
    "TransportType",
    "TransportConfig",
    "AttachResult",
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
    "PV_SERIES_RUNTIME_MAP",
    "PV_SERIES_ENERGY_MAP",
    "LXP_EU_RUNTIME_MAP",
    "LXP_EU_ENERGY_MAP",
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
