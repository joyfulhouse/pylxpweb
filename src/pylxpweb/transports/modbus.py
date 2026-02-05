"""Modbus TCP transport implementation.

This module provides the ModbusTransport class for direct local
communication with inverters via Modbus TCP (typically through
a Waveshare RS485-to-Ethernet adapter).

IMPORTANT: Single-Client Limitation
------------------------------------
Modbus TCP supports only ONE concurrent connection per gateway/inverter.
Running multiple clients (e.g., Home Assistant + custom script) causes:
- Transaction ID desynchronization
- "Request cancelled outside pymodbus" errors
- Intermittent timeouts and data corruption

Ensure only ONE integration/script connects to each inverter at a time.
Disable other Modbus integrations before using this transport.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ._modbus_base import INPUT_REGISTER_GROUPS, BaseModbusTransport
from .capabilities import MODBUS_CAPABILITIES, TransportCapabilities
from .exceptions import TransportConnectionError

if TYPE_CHECKING:
    from pymodbus.client import AsyncModbusTcpClient

    from pylxpweb.devices.inverters._features import InverterFamily

_LOGGER = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = ["INPUT_REGISTER_GROUPS", "ModbusTransport"]


class ModbusTransport(BaseModbusTransport):
    """Modbus TCP transport for local inverter communication.

    This transport connects directly to the inverter via a Modbus TCP
    gateway (e.g., Waveshare RS485-to-Ethernet adapter).

    IMPORTANT: Single-Client Limitation
    ------------------------------------
    Modbus TCP supports only ONE concurrent connection per gateway/inverter.
    Running multiple clients (e.g., Home Assistant + custom script) causes:
    - Transaction ID desynchronization
    - "Request cancelled outside pymodbus" errors
    - Intermittent timeouts and data corruption

    Ensure only ONE integration/script connects to each inverter at a time.
    Disable other Modbus integrations before using this transport.

    Example:
        transport = ModbusTransport(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
        )
        await transport.connect()

        runtime = await transport.read_runtime()
        print(f"PV Power: {runtime.pv_total_power}W")

    Note:
        Requires the `pymodbus` package to be installed:
        uv add pymodbus
    """

    transport_type: str = "modbus_tcp"

    def __init__(
        self,
        host: str,
        port: int = 502,
        unit_id: int = 1,
        serial: str = "",
        timeout: float = 10.0,
        inverter_family: InverterFamily | None = None,
        retries: int = 2,
        retry_delay: float = 0.5,
        inter_register_delay: float = 0.05,
        pymodbus_retries: int = 3,
    ) -> None:
        """Initialize Modbus transport.

        Args:
            host: IP address or hostname of Modbus TCP gateway
            port: TCP port (default 502 for Modbus)
            unit_id: Modbus unit/slave ID (default 1)
            serial: Inverter serial number (for identification)
            timeout: Connection and operation timeout in seconds
            inverter_family: Inverter model family for correct register mapping.
                If None, defaults to EG4_HYBRID (18kPV, FlexBOSS) for backward
                compatibility. Use InverterFamily.LXP for Luxpower models.
            retries: Application-level retries per register read (default 2)
            retry_delay: Initial delay between retries in seconds, doubles each
                attempt (default 0.5)
            inter_register_delay: Delay between register group reads in seconds
                (default 0.05)
            pymodbus_retries: Number of retries passed to pymodbus client
                (default 3)
        """
        super().__init__(
            serial,
            unit_id=unit_id,
            timeout=timeout,
            inverter_family=inverter_family,
            retries=retries,
            retry_delay=retry_delay,
            inter_register_delay=inter_register_delay,
            pymodbus_retries=pymodbus_retries,
        )
        self._host = host
        self._port = port
        # Narrow type for TCP client
        self._client: AsyncModbusTcpClient | None = None  # type: ignore[assignment]

    @property
    def capabilities(self) -> TransportCapabilities:
        """Get Modbus transport capabilities."""
        return MODBUS_CAPABILITIES

    @property
    def host(self) -> str:
        """Get the Modbus gateway host."""
        return self._host

    @property
    def port(self) -> int:
        """Get the Modbus gateway port."""
        return self._port

    async def connect(self) -> None:
        """Establish Modbus TCP connection.

        After connecting, performs a synchronization read to drain any stale
        responses from the gateway's TCP buffer. This prevents transaction ID
        desynchronization that occurs after integration reload/reconfigure,
        where the gateway still has buffered responses from the old connection.

        Raises:
            TransportConnectionError: If connection fails
        """
        try:
            # Import pymodbus here to make it optional
            from pymodbus.client import AsyncModbusTcpClient

            self._client = AsyncModbusTcpClient(
                host=self._host,
                port=self._port,
                timeout=self._timeout,
                retries=self._pymodbus_retries,
            )

            connected = await self._client.connect()
            if not connected:
                raise TransportConnectionError(
                    f"Failed to connect to Modbus gateway at {self._host}:{self._port}"
                )

            self._connected = True
            self._consecutive_errors = 0

            # Waveshare "Modbus TCP to RTU" gateways use MBAP framing on
            # the TCP side but don't echo the request's transaction ID —
            # they substitute their own counter. Patch pymodbus to skip
            # TID validation and suppress stale response log spam.
            self._patch_tid_validation()

            _LOGGER.info(
                "Modbus transport connected to %s:%s (unit %s) for %s",
                self._host,
                self._port,
                self._unit_id,
                self._serial,
            )

        except ImportError as err:
            raise TransportConnectionError(
                "pymodbus package not installed. Install with: uv add pymodbus"
            ) from err
        except (TimeoutError, OSError) as err:
            _LOGGER.error(
                "Failed to connect to Modbus gateway at %s:%s: %s",
                self._host,
                self._port,
                err,
            )
            raise TransportConnectionError(
                f"Failed to connect to {self._host}:{self._port}: {err}. "
                "Verify: (1) IP address is correct, (2) port 502 is not blocked, "
                "(3) Modbus TCP is enabled on the inverter/datalogger."
            ) from err

    def _patch_tid_validation(self) -> None:
        """Disable MBAP transaction ID validation in pymodbus.

        Waveshare RS485-to-Ethernet gateways use MBAP framing on the TCP
        side but don't echo the request's transaction ID in responses --
        they use their own incrementing counter. This causes pymodbus to
        reject every response at two validation points:

        1. ``framer.handleFrame``: ``if exp_tid and tid != exp_tid``
        2. ``execute``: ``if response.transaction_id != request.transaction_id``

        We patch ``handleFrame`` to pass ``exp_tid=0`` (disabling check 1)
        and set the decoded PDU's TID to the expected value (fixing check 2).
        Stale responses arriving after a future is resolved are also
        silently dropped to prevent log spam.
        """
        if self._client is None:
            return

        ctx = getattr(self._client, "ctx", None)
        if ctx is None or not hasattr(ctx, "framer"):
            return

        framer = ctx.framer
        original_handle_frame = framer.handleFrame

        def _patched_handle_frame(
            data: bytes,
            exp_devid: int,
            exp_tid: int,
        ) -> tuple[int, object | None]:
            used_len, pdu = original_handle_frame(data, exp_devid, 0)
            if pdu is not None:
                # Drop stale responses whose future is already resolved.
                future = getattr(ctx, "response_future", None)
                if future is not None and future.done():
                    return used_len, None
                if exp_tid:
                    pdu.transaction_id = exp_tid
            return used_len, pdu

        framer.handleFrame = _patched_handle_frame
        _LOGGER.debug(
            "Patched TID validation for Modbus gateway %s:%s (%s)",
            self._host,
            self._port,
            self._serial,
        )

    async def disconnect(self) -> None:
        """Close Modbus TCP connection."""
        if self._client:
            self._client.close()
            self._client = None

        self._connected = False
        _LOGGER.debug("Modbus transport disconnected for %s", self._serial)

    async def _reconnect(self) -> None:
        """Reconnect Modbus client to reset transaction ID state.

        Called when consecutive read errors exceed the threshold, which
        typically indicates transaction ID desynchronization (pymodbus
        responses arriving for stale requests).
        """
        async with self._lock:
            if self._consecutive_errors < self._max_consecutive_errors:
                return

            _LOGGER.warning(
                "Reconnecting Modbus client for %s after %d consecutive errors "
                "(likely transaction ID desync)",
                self._serial,
                self._consecutive_errors,
            )
            await self.disconnect()
            await self.connect()
            self._consecutive_errors = 0
