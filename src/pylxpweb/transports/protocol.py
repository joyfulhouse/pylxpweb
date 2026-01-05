"""Transport protocol definition.

This module defines the InverterTransport protocol that all transport
implementations must follow. Using Protocol allows for structural subtyping
(duck typing) while still providing type safety.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .capabilities import TransportCapabilities
    from .data import BatteryBankData, InverterEnergyData, InverterRuntimeData


@runtime_checkable
class InverterTransport(Protocol):
    """Protocol defining the interface for inverter communication.

    All transport implementations (HTTP, Modbus) must implement this interface.
    This enables the same device code to work with any transport type.

    The protocol is runtime-checkable, allowing isinstance() checks:
        if isinstance(transport, InverterTransport):
            await transport.read_runtime()
    """

    @property
    def serial(self) -> str:
        """Get the inverter serial number.

        Returns:
            10-digit serial number string
        """
        ...

    @property
    def is_connected(self) -> bool:
        """Check if transport is currently connected.

        Returns:
            True if connected and ready for operations
        """
        ...

    @property
    def capabilities(self) -> TransportCapabilities:
        """Get transport capabilities.

        Returns:
            Capabilities indicating what operations are supported
        """
        ...

    async def connect(self) -> None:
        """Establish connection to the device.

        For HTTP: Validates credentials and establishes session
        For Modbus: Opens TCP connection to the adapter

        Raises:
            TransportConnectionError: If connection fails
        """
        ...

    async def disconnect(self) -> None:
        """Close the connection.

        Should be called when done with the transport.
        Safe to call multiple times.
        """
        ...

    async def read_runtime(self) -> InverterRuntimeData:
        """Read real-time operating data from inverter.

        Returns:
            Runtime data with all values properly scaled

        Raises:
            TransportReadError: If read operation fails
            TransportConnectionError: If not connected
        """
        ...

    async def read_energy(self) -> InverterEnergyData:
        """Read energy statistics from inverter.

        Returns:
            Energy data with all values in kWh

        Raises:
            TransportReadError: If read operation fails
            TransportConnectionError: If not connected
        """
        ...

    async def read_battery(self) -> BatteryBankData | None:
        """Read battery bank information.

        Returns:
            Battery bank data if batteries present, None otherwise

        Raises:
            TransportReadError: If read operation fails
            TransportConnectionError: If not connected
        """
        ...

    async def read_parameters(
        self,
        start_address: int,
        count: int,
    ) -> dict[int, int]:
        """Read configuration parameters (hold registers).

        Args:
            start_address: Starting register address
            count: Number of registers to read (max 127 for HTTP, 40 for Modbus)

        Returns:
            Dict mapping register address to raw integer value

        Raises:
            TransportReadError: If read operation fails
            TransportConnectionError: If not connected
        """
        ...

    async def write_parameters(
        self,
        parameters: dict[int, int],
    ) -> bool:
        """Write configuration parameters (hold registers).

        Args:
            parameters: Dict mapping register address to value to write

        Returns:
            True if write succeeded

        Raises:
            TransportWriteError: If write operation fails
            TransportConnectionError: If not connected
        """
        ...


class BaseTransport:
    """Base class providing common transport functionality.

    Transport implementations can inherit from this class to get
    common utilities while implementing the InverterTransport protocol.
    """

    def __init__(self, serial: str) -> None:
        """Initialize base transport.

        Args:
            serial: Inverter serial number
        """
        self._serial = serial
        self._connected = False

    @property
    def serial(self) -> str:
        """Get the inverter serial number."""
        return self._serial

    @property
    def is_connected(self) -> bool:
        """Check if transport is connected."""
        return self._connected

    def _ensure_connected(self) -> None:
        """Ensure transport is connected.

        Raises:
            TransportConnectionError: If not connected
        """
        if not self._connected:
            from .exceptions import TransportConnectionError

            raise TransportConnectionError(
                f"Transport not connected for inverter {self._serial}. Call connect() first."
            )
