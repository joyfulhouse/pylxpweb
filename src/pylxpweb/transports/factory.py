"""Factory functions for creating transport instances.

This module provides convenience functions to create transport instances
for communicating with Luxpower/EG4 inverters via different protocols.

Example:
    # HTTP Transport (cloud API)
    async with LuxpowerClient(username, password) as client:
        transport = create_http_transport(client, serial="CE12345678")
        await transport.connect()
        runtime = await transport.read_runtime()

    # Modbus Transport (local network)
    transport = create_modbus_transport(
        host="192.168.1.100",
        serial="CE12345678",
    )
    async with transport:
        runtime = await transport.read_runtime()

    # Modbus Transport with specific inverter family (for LXP-EU models)
    from pylxpweb.devices.inverters._features import InverterFamily
    transport = create_modbus_transport(
        host="192.168.1.100",
        serial="CE12345678",
        inverter_family=InverterFamily.LXP_EU,
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .http import HTTPTransport
from .modbus import ModbusTransport

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient
    from pylxpweb.devices.inverters._features import InverterFamily


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
            If None, defaults to PV_SERIES (EG4-18KPV) for backward
            compatibility. Use InverterFamily.LXP_EU for LXP-EU 12K and
            similar European models which have different register layouts.

    Returns:
        ModbusTransport instance ready for use

    Example:
        # Default usage (PV_SERIES/EG4-18KPV register map)
        transport = create_modbus_transport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        async with transport:
            runtime = await transport.read_runtime()
            print(f"PV Power: {runtime.pv_total_power}W")

        # LXP-EU 12K with explicit family
        from pylxpweb.devices.inverters._features import InverterFamily

        transport = create_modbus_transport(
            host="192.168.1.100",
            serial="CE12345678",
            inverter_family=InverterFamily.LXP_EU,
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


__all__ = [
    "create_http_transport",
    "create_modbus_transport",
]
