"""Factory functions for creating transport instances.

This module provides convenience functions to create transport instances
for communicating with Luxpower/EG4 inverters via different protocols.

Example:
    # Unified factory (recommended)
    from pylxpweb.transports import create_transport

    # HTTP Transport
    transport = create_transport("http", client=client, serial="CE12345678")

    # Modbus Transport
    transport = create_transport("modbus", host="192.168.1.100", serial="CE12345678")

    # Dongle Transport
    transport = create_transport(
        "dongle",
        host="192.168.1.100",
        dongle_serial="BA12345678",
        inverter_serial="CE12345678",
    )

    # Hybrid Transport (local + HTTP fallback)
    transport = create_transport(
        "hybrid",
        client=client,
        serial="CE12345678",
        local_host="192.168.1.100",
    )

    # Legacy factory functions still work
    transport = create_http_transport(client, serial="CE12345678")
    transport = create_modbus_transport(host="192.168.1.100", serial="CE12345678")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, overload

from .config import TransportConfig, TransportType
from .dongle import DongleTransport
from .http import HTTPTransport
from .hybrid import HybridTransport
from .modbus import ModbusTransport
from .modbus_serial import ModbusSerialTransport
from .protocol import BaseTransport, InverterTransport

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient
    from pylxpweb.devices.inverters._features import InverterFamily

# Type alias for connection types
ConnectionType = Literal["http", "modbus", "serial", "dongle", "hybrid"]


# -----------------------------------------------------------------------------
# Unified Transport Factory
# -----------------------------------------------------------------------------


@overload
def create_transport(
    connection_type: Literal["http"],
    *,
    client: LuxpowerClient,
    serial: str,
) -> HTTPTransport: ...


@overload
def create_transport(
    connection_type: Literal["modbus"],
    *,
    host: str,
    serial: str,
    port: int = ...,
    unit_id: int = ...,
    timeout: float = ...,
    inverter_family: InverterFamily | None = ...,
) -> ModbusTransport: ...


@overload
def create_transport(
    connection_type: Literal["serial"],
    *,
    port: str,
    serial: str,
    baudrate: int = ...,
    parity: str = ...,
    stopbits: int = ...,
    unit_id: int = ...,
    timeout: float = ...,
    inverter_family: InverterFamily | None = ...,
) -> ModbusSerialTransport: ...


@overload
def create_transport(
    connection_type: Literal["dongle"],
    *,
    host: str,
    dongle_serial: str,
    inverter_serial: str,
    port: int = ...,
    timeout: float = ...,
    inverter_family: InverterFamily | None = ...,
) -> DongleTransport: ...


@overload
def create_transport(
    connection_type: Literal["hybrid"],
    *,
    client: LuxpowerClient,
    serial: str,
    local_host: str,
    local_type: Literal["modbus", "dongle"] = ...,
    local_port: int | None = ...,
    dongle_serial: str | None = ...,
    unit_id: int = ...,
    timeout: float = ...,
    inverter_family: InverterFamily | None = ...,
    local_retry_interval: float = ...,
) -> HybridTransport: ...


def create_transport(
    connection_type: ConnectionType,
    **config: Any,
) -> InverterTransport:
    """Create a transport instance for inverter communication.

    This is the unified entry point for creating any transport type.
    All transports implement the same InverterTransport protocol.

    Args:
        connection_type: One of "http", "modbus", "dongle", or "hybrid"
        **config: Configuration parameters (vary by connection_type)

    Connection Types:
        http: Cloud API transport
            - client: LuxpowerClient instance (required)
            - serial: Inverter serial number (required)

        modbus: Local Modbus TCP transport
            - host: Gateway IP address (required)
            - serial: Inverter serial number (required)
            - port: TCP port (default: 502)
            - unit_id: Modbus unit ID (default: 1)
            - timeout: Operation timeout (default: 10.0)
            - inverter_family: Register map selection (optional)

        dongle: WiFi dongle transport
            - host: Dongle IP address (required)
            - dongle_serial: Dongle serial number (required)
            - inverter_serial: Inverter serial number (required)
            - port: TCP port (default: 8000)
            - timeout: Operation timeout (default: 10.0)
            - inverter_family: Register map selection (optional)

        hybrid: Local + HTTP fallback
            - client: LuxpowerClient instance (required)
            - serial: Inverter serial number (required)
            - local_host: Local gateway IP (required)
            - local_type: "modbus" or "dongle" (default: "modbus")
            - local_port: TCP port (default: 502 for modbus, 8000 for dongle)
            - dongle_serial: Required if local_type is "dongle"
            - unit_id: Modbus unit ID (default: 1)
            - timeout: Operation timeout (default: 10.0)
            - inverter_family: Register map selection (optional)
            - local_retry_interval: Seconds before retrying local (default: 60.0)

    Returns:
        Configured transport instance implementing InverterTransport

    Raises:
        ValueError: If required parameters are missing or invalid

    Example:
        from pylxpweb.transports import create_transport

        # HTTP transport
        transport = create_transport("http", client=client, serial="CE12345678")

        # Modbus transport
        transport = create_transport("modbus", host="192.168.1.100", serial="CE12345678")

        # Hybrid transport (local with HTTP fallback)
        transport = create_transport(
            "hybrid",
            client=client,
            serial="CE12345678",
            local_host="192.168.1.100",
        )
    """
    if connection_type == "http":
        client = config.get("client")
        serial = config.get("serial")
        if client is None:
            raise ValueError("client is required for HTTP transport")
        if not serial:
            raise ValueError("serial is required for HTTP transport")
        return HTTPTransport(client, serial)

    if connection_type == "modbus":
        host = config.get("host")
        serial = config.get("serial")
        if not host:
            raise ValueError("host is required for Modbus transport")
        if not serial:
            raise ValueError("serial is required for Modbus transport")
        return ModbusTransport(
            host=host,
            serial=serial,
            port=config.get("port", 502),
            unit_id=config.get("unit_id", 1),
            timeout=config.get("timeout", 10.0),
            inverter_family=config.get("inverter_family"),
        )

    if connection_type == "serial":
        port = config.get("port")
        serial = config.get("serial")
        if not port:
            raise ValueError("port is required for Serial transport")
        if not serial:
            raise ValueError("serial is required for Serial transport")
        return ModbusSerialTransport(
            port=port,
            serial=serial,
            baudrate=config.get("baudrate", 19200),
            parity=config.get("parity", "N"),
            stopbits=config.get("stopbits", 1),
            unit_id=config.get("unit_id", 1),
            timeout=config.get("timeout", 10.0),
            inverter_family=config.get("inverter_family"),
        )

    if connection_type == "dongle":
        host = config.get("host")
        dongle_serial = config.get("dongle_serial")
        inverter_serial = config.get("inverter_serial")
        if not host:
            raise ValueError("host is required for Dongle transport")
        if not dongle_serial:
            raise ValueError("dongle_serial is required for Dongle transport")
        if not inverter_serial:
            raise ValueError("inverter_serial is required for Dongle transport")
        return DongleTransport(
            host=host,
            dongle_serial=dongle_serial,
            inverter_serial=inverter_serial,
            port=config.get("port", 8000),
            timeout=config.get("timeout", 10.0),
            inverter_family=config.get("inverter_family"),
        )

    if connection_type == "hybrid":
        client = config.get("client")
        serial = config.get("serial")
        local_host = config.get("local_host")
        if client is None:
            raise ValueError("client is required for Hybrid transport")
        if not serial:
            raise ValueError("serial is required for Hybrid transport")
        if not local_host:
            raise ValueError("local_host is required for Hybrid transport")

        local_type = config.get("local_type", "modbus")
        inverter_family = config.get("inverter_family")
        timeout = config.get("timeout", 10.0)
        local_retry_interval = config.get("local_retry_interval", 60.0)

        # Create HTTP transport
        http_transport = HTTPTransport(client, serial)

        # Create local transport based on local_type
        if local_type == "modbus":
            local_transport: ModbusTransport | DongleTransport = ModbusTransport(
                host=local_host,
                serial=serial,
                port=config.get("local_port") or 502,
                unit_id=config.get("unit_id", 1),
                timeout=timeout,
                inverter_family=inverter_family,
            )
        elif local_type == "dongle":
            dongle_serial = config.get("dongle_serial")
            if not dongle_serial:
                raise ValueError("dongle_serial is required for hybrid with dongle")
            local_transport = DongleTransport(
                host=local_host,
                dongle_serial=dongle_serial,
                inverter_serial=serial,
                port=config.get("local_port") or 8000,
                timeout=timeout,
                inverter_family=inverter_family,
            )
        else:
            raise ValueError(f"Invalid local_type: {local_type}")

        return HybridTransport(
            local_transport=local_transport,
            http_transport=http_transport,
            local_retry_interval=local_retry_interval,
        )

    raise ValueError(f"Invalid connection_type: {connection_type}")


# -----------------------------------------------------------------------------
# Legacy Factory Functions (still supported)
# -----------------------------------------------------------------------------


def create_http_transport(
    client: LuxpowerClient,
    serial: str,
) -> HTTPTransport:
    """Create an HTTP transport using the cloud API.

    Args:
        client: Authenticated LuxpowerClient instance
        serial: Inverter serial number

    Returns:
        HTTPTransport instance ready for use

    Example:
        async with LuxpowerClient(username, password) as client:
            transport = create_http_transport(client, "CE12345678")
            await transport.connect()

            runtime = await transport.read_runtime()
            print(f"PV Power: {runtime.pv_total_power}W")
            print(f"Battery SOC: {runtime.battery_soc}%")

            energy = await transport.read_energy()
            print(f"Today's yield: {energy.pv_energy_today} kWh")
    """
    return HTTPTransport(client, serial)


def create_modbus_transport(
    host: str,
    serial: str,
    *,
    port: int = 502,
    unit_id: int = 1,
    timeout: float = 10.0,
    inverter_family: InverterFamily | None = None,
) -> ModbusTransport:
    """Create a Modbus TCP transport for local network communication.

    This allows direct communication with the inverter over the local network
    without requiring cloud connectivity.

    IMPORTANT: Single-Client Limitation
    ------------------------------------
    Modbus TCP supports only ONE concurrent connection per gateway/inverter.
    Running multiple clients (e.g., Home Assistant + custom script) causes:
    - Transaction ID desynchronization
    - "Request cancelled outside pymodbus" errors
    - Intermittent timeouts and data corruption

    Ensure only ONE integration/script connects to each inverter at a time.

    Args:
        host: Inverter IP address or hostname
        serial: Inverter serial number (for identification)
        port: Modbus TCP port (default: 502)
        unit_id: Modbus unit/slave ID (default: 1)
        timeout: Operation timeout in seconds (default: 10.0)
        inverter_family: Inverter model family for correct register mapping.
            If None, defaults to EG4_HYBRID (18kPV, FlexBOSS) for backward
            compatibility. Use InverterFamily.LXP for Luxpower models
            (LXP-EU, LXP-LB-BR, LXP-LV) which have different register layouts.

    Returns:
        ModbusTransport instance ready for use

    Example:
        # Default usage (EG4_HYBRID register map)
        transport = create_modbus_transport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        async with transport:
            runtime = await transport.read_runtime()
            print(f"PV Power: {runtime.pv_total_power}W")

        # Luxpower with explicit family
        from pylxpweb.devices.inverters._features import InverterFamily

        transport = create_modbus_transport(
            host="192.168.1.100",
            serial="CE12345678",
            inverter_family=InverterFamily.LXP,
        )

    Note:
        Modbus communication requires:
        - Network access to the inverter
        - Modbus TCP enabled on the inverter (check inverter settings)
        - No firewall blocking port 502

        The inverter must have a datalogger/dongle that supports Modbus TCP,
        or direct Modbus TCP capability (varies by model).
    """
    return ModbusTransport(
        host=host,
        serial=serial,
        port=port,
        unit_id=unit_id,
        timeout=timeout,
        inverter_family=inverter_family,
    )


def create_dongle_transport(
    host: str,
    dongle_serial: str,
    inverter_serial: str,
    *,
    port: int = 8000,
    timeout: float = 10.0,
    inverter_family: InverterFamily | None = None,
) -> DongleTransport:
    """Create a WiFi dongle transport for local network communication.

    This allows direct communication with the inverter via the WiFi dongle's
    TCP interface (port 8000) without requiring cloud connectivity or
    additional hardware (no RS485-to-Ethernet adapter needed).

    IMPORTANT: Single-Client Limitation
    ------------------------------------
    The WiFi dongle supports only ONE concurrent TCP connection.
    Running multiple clients (e.g., Home Assistant + Solar Assistant) causes
    connection failures and data loss.

    Ensure only ONE integration/script connects to each dongle at a time.
    Disable other integrations before using this transport.

    IMPORTANT: Firmware Compatibility
    ---------------------------------
    Recent firmware updates may block port 8000 access for security.
    If connection fails, check if your dongle firmware has been updated.
    Older firmware versions (BA dongles) typically work reliably.

    Args:
        host: WiFi dongle IP address or hostname
        dongle_serial: 10-character dongle serial number (e.g., "BA12345678")
            This can be found in your router's DHCP client list, on the
            dongle label, or as the dongle's WiFi AP SSID.
        inverter_serial: 10-character inverter serial number (e.g., "CE12345678")
        port: TCP port (default: 8000)
        timeout: Operation timeout in seconds (default: 10.0)
        inverter_family: Inverter model family for correct register mapping.
            If None, defaults to PV_SERIES (EG4-18KPV) for backward
            compatibility.

    Returns:
        DongleTransport instance ready for use

    Example:
        transport = create_dongle_transport(
            host="192.168.1.100",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
        )

        async with transport:
            runtime = await transport.read_runtime()
            print(f"PV Power: {runtime.pv_total_power}W")

    Note:
        Unlike Modbus TCP transport, the dongle transport:
        - Does NOT require pymodbus (uses pure asyncio sockets)
        - Does NOT require additional hardware (RS485-to-Ethernet adapter)
        - Uses the proprietary LuxPower/EG4 protocol on port 8000
        - Requires both dongle AND inverter serial numbers for authentication
    """
    return DongleTransport(
        host=host,
        dongle_serial=dongle_serial,
        inverter_serial=inverter_serial,
        port=port,
        timeout=timeout,
        inverter_family=inverter_family,
    )


def create_serial_transport(
    port: str,
    serial: str,
    *,
    baudrate: int = 19200,
    parity: str = "N",
    stopbits: int = 1,
    unit_id: int = 1,
    timeout: float = 10.0,
    inverter_family: InverterFamily | None = None,
) -> ModbusSerialTransport:
    """Create a Modbus RTU serial transport for local communication.

    This allows direct communication with the inverter via a USB-to-RS485
    serial adapter using Modbus RTU protocol.

    IMPORTANT: Single-Client Limitation
    ------------------------------------
    Serial ports support only ONE concurrent connection.
    Running multiple clients (e.g., Home Assistant + custom script) causes
    communication errors and data corruption.

    Ensure only ONE integration/script connects to each serial port at a time.

    Args:
        port: Serial port path (e.g., "/dev/ttyUSB0", "COM1")
        serial: Inverter serial number (for identification)
        baudrate: Serial baud rate (default: 19200)
        parity: Serial parity: 'N' (none), 'E' (even), 'O' (odd) (default: 'N')
        stopbits: Serial stop bits: 1 or 2 (default: 1)
        unit_id: Modbus unit/slave ID (default: 1)
        timeout: Operation timeout in seconds (default: 10.0)
        inverter_family: Inverter model family for correct register mapping.
            If None, defaults to PV_SERIES (EG4-18KPV) for backward
            compatibility.

    Returns:
        ModbusSerialTransport instance ready for use

    Example:
        transport = create_serial_transport(
            port="/dev/ttyUSB0",
            serial="CE12345678",
            baudrate=19200,
        )

        async with transport:
            runtime = await transport.read_runtime()
            print(f"PV Power: {runtime.pv_total_power}W")

    Note:
        Serial communication requires:
        - USB-to-RS485 adapter connected to inverter
        - Correct serial parameters (baudrate, parity, stopbits)
        - Appropriate permissions for serial port access
    """
    return ModbusSerialTransport(
        port=port,
        serial=serial,
        baudrate=baudrate,
        parity=parity,
        stopbits=stopbits,
        unit_id=unit_id,
        timeout=timeout,
        inverter_family=inverter_family,
    )


def create_transport_from_config(config: TransportConfig) -> BaseTransport:
    """Create transport instance from configuration object.

    This factory function creates the appropriate transport instance based
    on the configuration's transport_type. It validates the configuration
    before creating the transport.

    Args:
        config: Transport configuration specifying connection parameters

    Returns:
        Configured transport instance (ModbusTransport or DongleTransport)

    Raises:
        ValueError: If transport_type is HTTP (requires client) or
            if configuration validation fails

    Example:
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
            inverter_family=InverterFamily.EG4_HYBRID,
        )
        transport = create_transport_from_config(config)
        async with transport:
            runtime = await transport.read_runtime()
    """
    # Validate configuration first
    config.validate()

    if config.transport_type == TransportType.MODBUS_TCP:
        return ModbusTransport(
            host=config.host,
            port=config.port,
            serial=config.serial,
            unit_id=config.unit_id,
            timeout=config.timeout,
            inverter_family=config.inverter_family,
            retries=config.retries,
            retry_delay=config.retry_delay,
            inter_register_delay=config.inter_register_delay,
        )
    elif config.transport_type == TransportType.MODBUS_SERIAL:
        # serial_port is guaranteed to be set after validate() for MODBUS_SERIAL
        assert config.serial_port is not None
        return ModbusSerialTransport(
            port=config.serial_port,
            serial=config.serial,
            baudrate=config.serial_baudrate,
            parity=config.serial_parity,
            stopbits=config.serial_stopbits,
            unit_id=config.unit_id,
            timeout=config.timeout,
            inverter_family=config.inverter_family,
            retries=config.retries,
            retry_delay=config.retry_delay,
            inter_register_delay=config.inter_register_delay,
        )
    elif config.transport_type == TransportType.WIFI_DONGLE:
        # dongle_serial is guaranteed to be set after validate() for WIFI_DONGLE
        assert config.dongle_serial is not None
        return DongleTransport(
            host=config.host,
            port=config.port,
            dongle_serial=config.dongle_serial,
            inverter_serial=config.serial,
            timeout=config.timeout,
            inverter_family=config.inverter_family,
        )
    elif config.transport_type == TransportType.HTTP:
        raise ValueError(
            "HTTP transport requires a LuxpowerClient instance. "
            "Use create_http_transport() instead."
        )
    else:
        raise ValueError(f"Unsupported transport type: {config.transport_type}")


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
    # Transport classes
    "ModbusSerialTransport",
    # Configuration
    "TransportConfig",
    "TransportType",
]
