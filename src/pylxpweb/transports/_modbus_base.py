"""Shared Modbus transport logic for TCP and Serial transports.

This module provides the BaseModbusTransport class containing Modbus-specific
register read/write logic with retry handling and adaptive inter-group delays.

Data interpretation methods (read_runtime, read_energy, etc.) are inherited
from ``RegisterDataMixin`` in ``_register_data.py``.

Subclasses must implement:
- connect() / disconnect() — protocol-specific connection management
- _reconnect() — protocol-specific reconnection with logging
- capabilities property — transport capability flags
- _create_client() — optional, for client initialization
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from pymodbus.exceptions import ModbusIOException

from ._register_data import INPUT_REGISTER_GROUPS, RegisterDataMixin
from .exceptions import (
    TransportConnectionError,
    TransportReadError,
    TransportTimeoutError,
    TransportWriteError,
)
from .protocol import BaseTransport

if TYPE_CHECKING:
    from pylxpweb.devices.inverters._features import InverterFamily
    from pylxpweb.transports.data import BatteryBankData

_LOGGER = logging.getLogger(__name__)

__all__ = ["BaseModbusTransport", "INPUT_REGISTER_GROUPS"]


class BaseModbusTransport(RegisterDataMixin, BaseTransport):
    """Base class for Modbus-based transports (TCP and Serial).

    Provides Modbus wire-level register read/write with retry handling,
    adaptive inter-group delays, and auto-reconnect on consecutive errors.

    Data interpretation methods are inherited from ``RegisterDataMixin``.

    Subclasses must set ``self._client`` to a pymodbus async client
    and implement ``connect()``, ``disconnect()``, and ``_reconnect()``.
    """

    def __init__(
        self,
        serial: str,
        *,
        unit_id: int = 1,
        timeout: float = 10.0,
        inverter_family: InverterFamily | None = None,
        retries: int = 2,
        retry_delay: float = 0.5,
        inter_register_delay: float = 0.05,
        pymodbus_retries: int = 3,
    ) -> None:
        """Initialize base Modbus transport.

        Args:
            serial: Inverter serial number (for identification)
            unit_id: Modbus unit/slave ID (default 1)
            timeout: Connection and operation timeout in seconds
            inverter_family: Inverter model family for correct register mapping
            retries: Application-level retries per register read (default 2)
            retry_delay: Initial delay between retries in seconds, doubles each
                attempt (default 0.5)
            inter_register_delay: Delay between register group reads in seconds
                (default 0.05)
            pymodbus_retries: Number of retries passed to pymodbus client
                (default 3)
        """
        super().__init__(serial)
        self._unit_id = unit_id
        self._timeout = timeout
        self._inverter_family = inverter_family
        self._retries = retries
        self._retry_delay = retry_delay
        self._inter_register_delay = inter_register_delay
        self._pymodbus_retries = pymodbus_retries
        self._client: Any = None
        self._lock = asyncio.Lock()
        self._consecutive_errors: int = 0
        self._max_consecutive_errors: int = 3
        self._last_read_retried: bool = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def unit_id(self) -> int:
        """Get the Modbus unit/slave ID."""
        return self._unit_id

    @property
    def inverter_family(self) -> InverterFamily | None:
        """Get the inverter family for register mapping."""
        return self._inverter_family

    @inverter_family.setter
    def inverter_family(self, value: InverterFamily | None) -> None:
        """Set the inverter family for register mapping."""
        if value != self._inverter_family:
            _LOGGER.debug(
                "Updating inverter family from %s to %s for %s",
                self._inverter_family,
                value,
                self._serial,
            )
        self._inverter_family = value

    # ------------------------------------------------------------------
    # Register Read/Write (with retry and error tracking)
    # ------------------------------------------------------------------

    async def _read_registers(
        self,
        address: int,
        count: int,
        *,
        input_registers: bool,
    ) -> list[int]:
        """Read Modbus registers with retry and error tracking.

        Args:
            address: Starting register address
            count: Number of registers to read (max 125 per Modbus FC 03/04 spec)
            input_registers: True for input registers (FC4), False for holding (FC3)

        Returns:
            List of register values

        Raises:
            TransportReadError: If read fails after all retries
            TransportTimeoutError: If operation times out
        """
        self._ensure_connected()

        if self._client is None:
            raise TransportConnectionError("Modbus client not initialized")

        reg_type = "input" if input_registers else "holding"
        last_err: Exception | None = None
        self._last_read_retried = False

        for attempt in range(self._retries + 1):
            async with self._lock:
                try:
                    read_fn = (
                        self._client.read_input_registers
                        if input_registers
                        else self._client.read_holding_registers
                    )
                    result = await read_fn(
                        address=address,
                        count=count,
                        device_id=self._unit_id,
                    )

                    if result.isError():
                        raise TransportReadError(
                            f"Modbus read error at address {address}: {result}"
                        )

                    if not hasattr(result, "registers") or result.registers is None:
                        raise TransportReadError(
                            f"Invalid Modbus response at address {address}: "
                            "no registers in response"
                        )

                    self._consecutive_errors = 0
                    return list(result.registers)

                except ModbusIOException as err:
                    self._consecutive_errors += 1
                    if "timeout" in str(err).lower():
                        last_err = TransportTimeoutError(
                            f"Timeout reading {reg_type} registers at {address}"
                        )
                    else:
                        last_err = TransportReadError(
                            f"Failed to read {reg_type} registers at {address}: {err}"
                        )
                    last_err.__cause__ = err
                except TimeoutError as err:
                    self._consecutive_errors += 1
                    last_err = TransportTimeoutError(
                        f"Timeout reading {reg_type} registers at {address}"
                    )
                    last_err.__cause__ = err
                except (TransportReadError, TransportTimeoutError) as err:
                    self._consecutive_errors += 1
                    last_err = err
                except OSError as err:
                    self._consecutive_errors += 1
                    last_err = TransportReadError(
                        f"Failed to read {reg_type} registers at {address}: {err}"
                    )
                    last_err.__cause__ = err

            # Retry with exponential backoff (skip on last attempt)
            if attempt < self._retries:
                self._last_read_retried = True
                delay = self._retry_delay * (2**attempt)
                _LOGGER.debug(
                    "Retry %d/%d reading %s registers at %d after %.1fs",
                    attempt + 1,
                    self._retries,
                    reg_type,
                    address,
                    delay,
                )
                await asyncio.sleep(delay)

        _LOGGER.error(
            "Failed to read %s registers at %d after %d attempts: %s",
            reg_type,
            address,
            self._retries + 1,
            last_err,
        )
        raise last_err  # type: ignore[misc]

    async def _read_input_registers(
        self,
        address: int,
        count: int,
    ) -> list[int]:
        """Read input registers (read-only runtime data)."""
        return await self._read_registers(address, count, input_registers=True)

    async def _read_holding_registers(
        self,
        address: int,
        count: int,
    ) -> list[int]:
        """Read holding registers (configuration parameters)."""
        return await self._read_registers(address, count, input_registers=False)

    async def _write_holding_registers(
        self,
        address: int,
        values: list[int],
    ) -> bool:
        """Write holding registers.

        Args:
            address: Starting register address
            values: List of values to write

        Returns:
            True if write succeeded

        Raises:
            TransportWriteError: If write fails
            TransportTimeoutError: If operation times out
        """
        self._ensure_connected()

        if self._client is None:
            raise TransportConnectionError("Modbus client not initialized")

        async with self._lock:
            try:
                if len(values) == 1:
                    result = await self._client.write_register(
                        address=address,
                        value=values[0],
                        device_id=self._unit_id,
                    )
                else:
                    result = await self._client.write_registers(
                        address=address,
                        values=values,
                        device_id=self._unit_id,
                    )

                if result.isError():
                    _LOGGER.error(
                        "Modbus error writing registers at %d: %s",
                        address,
                        result,
                    )
                    raise TransportWriteError(f"Modbus write error at address {address}: {result}")

                return True

            except ModbusIOException as err:
                if "timeout" in str(err).lower():
                    _LOGGER.error("Timeout writing registers at %d", address)
                    raise TransportTimeoutError(f"Timeout writing registers at {address}") from err
                _LOGGER.error("Failed to write registers at %d: %s", address, err)
                raise TransportWriteError(f"Failed to write registers at {address}: {err}") from err
            except TimeoutError as err:
                _LOGGER.error("Timeout writing registers at %d", address)
                raise TransportTimeoutError(f"Timeout writing registers at {address}") from err
            except OSError as err:
                _LOGGER.error("Failed to write registers at %d: %s", address, err)
                raise TransportWriteError(f"Failed to write registers at {address}: {err}") from err

    # ------------------------------------------------------------------
    # Override: adaptive inter-group delay + auto-reconnect
    # ------------------------------------------------------------------

    async def _read_register_groups(
        self,
        group_names: list[str] | None = None,
    ) -> dict[int, int]:
        """Read register groups with adaptive delay and auto-reconnect.

        Overrides ``RegisterDataMixin._read_register_groups`` to add:
        - Auto-reconnect after consecutive errors
        - Adaptive delay increase when retries have occurred
        """
        if group_names is None:
            groups = list(INPUT_REGISTER_GROUPS.items())
        else:
            groups = [
                (name, INPUT_REGISTER_GROUPS[name])
                for name in group_names
                if name in INPUT_REGISTER_GROUPS
            ]

        if self._consecutive_errors >= self._max_consecutive_errors:
            await self._reconnect()

        registers: dict[int, int] = {}
        current_delay = self._inter_register_delay

        for i, (group_name, (start, count)) in enumerate(groups):
            try:
                values = await self._read_input_registers(start, count)
                for offset, value in enumerate(values):
                    registers[start + offset] = value
            except Exception as e:
                _LOGGER.error(
                    "Failed to read register group '%s': %s",
                    group_name,
                    e,
                )
                raise TransportReadError(
                    f"Failed to read register group '{group_name}': {e}"
                ) from e

            # Increase delay when retries occurred to give the device breathing room
            if self._last_read_retried:
                current_delay = min(current_delay * 2, 1.0)
                _LOGGER.debug(
                    "Increasing inter-group delay to %.3fs after retries",
                    current_delay,
                )

            if i < len(groups) - 1:
                await asyncio.sleep(current_delay)

        return registers

    # ------------------------------------------------------------------
    # Override: read_battery with reconnect check
    # ------------------------------------------------------------------

    async def read_battery(
        self,
        include_individual: bool = True,
    ) -> BatteryBankData | None:
        """Read battery information with reconnect on consecutive errors."""

        if self._consecutive_errors >= self._max_consecutive_errors:
            await self._reconnect()

        return await super().read_battery(include_individual)

    # ------------------------------------------------------------------
    # Reconnect (subclasses may override for custom logging)
    # ------------------------------------------------------------------

    async def _reconnect(self) -> None:
        """Reconnect Modbus client to reset state after consecutive errors.

        Uses lock with double-check to prevent concurrent reconnection.
        """
        async with self._lock:
            if self._consecutive_errors < self._max_consecutive_errors:
                return

            _LOGGER.warning(
                "Reconnecting Modbus client for %s after %d consecutive errors",
                self._serial,
                self._consecutive_errors,
            )
            await self.disconnect()
            await self.connect()
            self._consecutive_errors = 0
