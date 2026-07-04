"""Transport-specific exceptions.

This module provides exception classes for transport operations,
allowing clients to handle errors appropriately.

All transport exceptions inherit from :class:`~pylxpweb.exceptions.LuxpowerError`
so callers can use a single ``except LuxpowerError`` to catch both HTTP API
and Modbus/dongle transport failures.
"""

from __future__ import annotations

from pylxpweb.exceptions import LuxpowerError


class TransportError(LuxpowerError):
    """Base exception for all transport errors."""

    pass


class TransportConnectionError(TransportError):
    """Failed to connect to the device."""

    pass


class TransportTimeoutError(TransportError):
    """Operation timed out."""

    pass


class TransportReadError(TransportError):
    """Failed to read data from device."""

    pass


class TransportResponseMismatchError(TransportReadError):
    """A response frame failed cross-request validation.

    Raised when a received frame carries the wrong serial, function code, or
    start register for the request that was sent — i.e. a misrouted or
    interleaved frame (the WiFi dongle proxies cloud traffic and can deliver a
    response meant for the cloud server to a local reader).  This is a
    transport-level routing hiccup, **not** a device/firmware refusal of the
    request, so callers that latch behavior off a genuine refusal (e.g. the
    large-read coalescing probe) must not treat it as one.
    """

    pass


class TransportWriteError(TransportError):
    """Failed to write data to device."""

    pass


class UnsupportedOperationError(TransportError):
    """Operation not supported by this transport.

    Raised when attempting an operation that the transport
    doesn't support (e.g., reading history via Modbus).
    """

    def __init__(self, operation: str, transport_type: str) -> None:
        """Initialize with operation and transport details.

        Args:
            operation: The operation that was attempted
            transport_type: The type of transport that doesn't support it
        """
        self.operation = operation
        self.transport_type = transport_type
        super().__init__(
            f"Operation '{operation}' is not supported by {transport_type} transport. "
            "Use HTTP transport for this feature."
        )
