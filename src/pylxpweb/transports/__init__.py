"""Transport layer abstraction for pylxpweb.

This module provides transport-agnostic communication with inverters,
supporting both cloud HTTP API and local Modbus TCP connections.

Usage:
    # HTTP Transport (cloud API) - using factory function
    from pylxpweb.transports import create_http_transport

    async with LuxpowerClient(username, password) as client:
        transport = create_http_transport(client, serial="CE12345678")
        await transport.connect()
        runtime = await transport.read_runtime()

    # Modbus Transport (local) - using factory function
    from pylxpweb.transports import create_modbus_transport

    transport = create_modbus_transport(
        host="192.168.1.100",
        serial="CE12345678",
    )
    async with transport:
        runtime = await transport.read_runtime()  # Same interface!
"""

from __future__ import annotations

from .capabilities import (
    HTTP_CAPABILITIES,
    MODBUS_CAPABILITIES,
    TransportCapabilities,
)
from .data import (
    BatteryBankData,
    BatteryData,
    InverterEnergyData,
    InverterRuntimeData,
)
from .exceptions import (
    TransportConnectionError,
    TransportError,
    TransportReadError,
    TransportTimeoutError,
    TransportWriteError,
    UnsupportedOperationError,
)
from .factory import create_http_transport, create_modbus_transport
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
    # Protocol
    "InverterTransport",
    "BaseTransport",
    # Transport implementations
    "HTTPTransport",
    "ModbusTransport",
    # Capabilities
    "TransportCapabilities",
    "HTTP_CAPABILITIES",
    "MODBUS_CAPABILITIES",
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
