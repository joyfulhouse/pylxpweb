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
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .http import HTTPTransport
from .modbus import ModbusTransport

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient


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
) -> ModbusTransport:
    """Create a Modbus TCP transport for local network communication.

    This allows direct communication with the inverter over the local network
    without requiring cloud connectivity.

    Args:
        host: Inverter IP address or hostname
        serial: Inverter serial number (for identification)
        port: Modbus TCP port (default: 502)
        unit_id: Modbus unit/slave ID (default: 1)
        timeout: Operation timeout in seconds (default: 10.0)

    Returns:
        ModbusTransport instance ready for use

    Example:
        transport = create_modbus_transport(
            host="192.168.1.100",
            serial="CE12345678",
        )

        async with transport:
            runtime = await transport.read_runtime()
            print(f"PV Power: {runtime.pv_total_power}W")

            battery = await transport.read_battery()
            if battery:
                print(f"Battery SOC: {battery.soc}%")

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
    )


__all__ = [
    "create_http_transport",
    "create_modbus_transport",
]
