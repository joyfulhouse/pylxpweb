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


class DongleChannelError(TransportConnectionError):
    """A ``DongleTransport`` could not attach to its shared endpoint channel.

    Every ``DongleTransport`` that targets the same physical dongle
    (``host:port`` + ``dongle_serial``) shares ONE serialized TCP socket
    (pylxpweb#329).  Attaching is refused — before any dial — when the
    request is incompatible with the channel that already exists for that
    endpoint.  Subclasses name the incompatibility.
    """

    pass


class DongleChannelMismatchError(DongleChannelError):
    """Incompatible configuration for an endpoint that already has a channel.

    Raised when a transport asks for a different TLS-PSK mode (``use_ssl``)
    than the channel already serving its ``host:port``, or for a different
    ``dongle_serial`` on the same ``host:port``.  Per-operation knobs
    (timeouts, block sizes, write retries, family) are per-transport and never
    conflict; only the per-socket facts do.  The existing channel is left
    untouched.
    """

    pass


class DongleChannelLoopError(DongleChannelError):
    """A transport tried to attach to a channel owned by another event loop.

    Channels are single-loop objects: their locks, streams and leases belong
    to the loop that created them.  Attaching from a different *running* loop
    is a programming error and is refused before any socket work.  (A channel
    whose loop has already closed is discarded and recreated transparently.)
    """

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
