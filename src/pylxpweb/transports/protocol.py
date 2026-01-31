"""Transport protocol definition.

This module defines the InverterTransport protocol that all transport
implementations must follow. Using Protocol allows for structural subtyping
(duck typing) while still providing type safety.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol, Self, runtime_checkable

if TYPE_CHECKING:
    from .capabilities import TransportCapabilities
    from .data import BatteryBankData, InverterEnergyData, InverterRuntimeData

_LOGGER = logging.getLogger(__name__)


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

    async def read_named_parameters(
        self,
        start_address: int,
        count: int,
    ) -> dict[str, Any]:
        """Read configuration parameters as named key-value pairs.

        Args:
            start_address: Starting register address
            count: Number of registers to read

        Returns:
            Dict mapping parameter name to value

        Raises:
            TransportReadError: If read operation fails
            TransportConnectionError: If not connected
        """
        ...

    async def write_named_parameters(
        self,
        parameters: dict[str, Any],
    ) -> bool:
        """Write configuration parameters using named keys.

        Args:
            parameters: Dict mapping parameter name to value

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

    Supports async context manager for automatic connection management:
        async with transport:
            data = await transport.read_runtime()
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

    async def __aenter__(self) -> Self:
        """Enter async context manager, connecting the transport.

        Returns:
            Self after connecting
        """
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit async context manager, disconnecting the transport."""
        await self.disconnect()

    async def connect(self) -> None:
        """Establish connection. Must be implemented by subclasses."""
        raise NotImplementedError

    async def disconnect(self) -> None:
        """Close connection. Must be implemented by subclasses."""
        raise NotImplementedError

    async def read_parameters(
        self,
        start_address: int,
        count: int,
    ) -> dict[int, int]:
        """Read configuration parameters. Must be implemented by subclasses."""
        raise NotImplementedError

    async def write_parameters(
        self,
        parameters: dict[int, int],
    ) -> bool:
        """Write configuration parameters. Must be implemented by subclasses."""
        raise NotImplementedError

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

    # -------------------------------------------------------------------------
    # Named Parameter Methods (Transport-Agnostic)
    # -------------------------------------------------------------------------
    # These methods provide a consistent API for reading/writing parameters
    # by name, regardless of whether using HTTP, Modbus, or Hybrid transport.
    # The library handles all register-to-parameter mapping internally.

    def _get_inverter_family(self) -> str | None:
        """Get the inverter family for this transport.

        Subclasses that support family-specific parameter mapping (Modbus, Dongle)
        should set self._inverter_family in their __init__.

        Returns:
            Inverter family string (e.g., "PV_SERIES", "SNA") or None if not set.
        """
        family = getattr(self, "_inverter_family", None)
        if family is None:
            return None
        # Handle both InverterFamily enum and string values
        if hasattr(family, "value"):
            return str(family.value)
        return str(family)

    def _is_bit_field_register(self, param_keys: list[str]) -> bool:
        """Check if parameter keys represent a bit field register.

        Bit field registers contain multiple boolean parameters packed into
        a single 16-bit value, where each bit represents a separate parameter.
        These are identified by FUNC_* and BIT_* prefixes.

        Args:
            param_keys: List of parameter key names for a register

        Returns:
            True if this is a bit field register
        """
        return len(param_keys) > 1 and all(k.startswith(("FUNC_", "BIT_")) for k in param_keys)

    async def read_named_parameters(
        self,
        start_address: int,
        count: int,
    ) -> dict[str, Any]:
        """Read configuration parameters and return as named key-value pairs.

        This method provides transport-agnostic parameter access. For HTTP,
        the server returns named parameters directly. For Modbus/Dongle,
        the library maps register addresses to parameter names using the
        appropriate mapping for the inverter family.

        Args:
            start_address: Starting register address
            count: Number of registers to read

        Returns:
            Dict mapping parameter name to value. Values are typed appropriately:
            - Boolean for bit fields (FUNC_*, BIT_*)
            - String for serial numbers, firmware versions
            - Integer for most other parameters

        Raises:
            TransportReadError: If read operation fails
            TransportConnectionError: If not connected

        Example:
            params = await transport.read_named_parameters(21, 1)
            # Returns: {"FUNC_EPS_EN": True, "FUNC_AC_CHARGE": False, ...}

            params = await transport.read_named_parameters(66, 2)
            # Returns: {"HOLD_AC_CHARGE_POWER_CMD": 50, "HOLD_AC_CHARGE_SOC_LIMIT": 95}
        """
        from pylxpweb.constants.registers import get_register_to_param_mapping

        # Get family-specific register mapping
        family = self._get_inverter_family()
        register_mapping = get_register_to_param_mapping(family)

        raw_params = await self.read_parameters(start_address, count)
        result: dict[str, Any] = {}

        for addr, value in raw_params.items():
            param_keys = register_mapping.get(addr)
            if not param_keys:
                result[str(addr)] = value
                continue

            if self._is_bit_field_register(param_keys):
                for bit_index, param_key in enumerate(param_keys):
                    result[param_key] = bool((value >> bit_index) & 1)
            elif len(param_keys) == 1:
                result[param_keys[0]] = value
            else:
                for param_key in param_keys:
                    result[param_key] = value

        return result

    async def write_named_parameters(
        self,
        parameters: dict[str, Any],
    ) -> bool:
        """Write configuration parameters using named keys.

        This method provides transport-agnostic parameter access. The library
        handles mapping parameter names to register addresses and combining
        bit fields into register values, using the appropriate mapping for
        the inverter family.

        Args:
            parameters: Dict mapping parameter name to value. For bit fields
                (FUNC_*, BIT_*), values should be boolean. For other parameters,
                values should be integers.

        Returns:
            True if write succeeded

        Raises:
            TransportWriteError: If write operation fails
            TransportConnectionError: If not connected
            ValueError: If parameter name is not recognized

        Example:
            # Write a simple parameter
            await transport.write_named_parameters({"HOLD_AC_CHARGE_POWER_CMD": 50})

            # Write bit field parameters (will read-modify-write register 21)
            await transport.write_named_parameters({
                "FUNC_EPS_EN": True,
                "FUNC_AC_CHARGE": False,
            })
        """
        from pylxpweb.constants.registers import (
            get_param_to_register_mapping,
            get_register_to_param_mapping,
        )

        # Get family-specific mappings
        family = self._get_inverter_family()
        param_to_register = get_param_to_register_mapping(family)
        register_to_params = get_register_to_param_mapping(family)

        registers_to_write: dict[int, int] = {}
        bit_field_registers: dict[int, dict[str, bool]] = {}

        for param_name, value in parameters.items():
            if param_name not in param_to_register:
                raise ValueError(f"Unknown parameter name: {param_name}")

            register_addr = param_to_register[param_name]
            param_keys = register_to_params.get(register_addr, [])

            if self._is_bit_field_register(param_keys):
                if register_addr not in bit_field_registers:
                    bit_field_registers[register_addr] = {}
                bit_field_registers[register_addr][param_name] = bool(value)
            else:
                registers_to_write[register_addr] = int(value)

        # Handle bit field registers with read-modify-write
        for register_addr, bit_updates in bit_field_registers.items():
            current_values = await self.read_parameters(register_addr, 1)
            current_value = current_values.get(register_addr, 0)
            param_keys = register_to_params.get(register_addr, [])

            new_value = current_value
            for param_name, enable in bit_updates.items():
                if param_name not in param_keys:
                    raise ValueError(
                        f"Bit field '{param_name}' not in register {register_addr} mapping"
                    )
                bit_index = param_keys.index(param_name)
                if enable:
                    new_value |= 1 << bit_index
                else:
                    new_value &= ~(1 << bit_index)

            registers_to_write[register_addr] = new_value

        if registers_to_write:
            return await self.write_parameters(registers_to_write)

        return True
