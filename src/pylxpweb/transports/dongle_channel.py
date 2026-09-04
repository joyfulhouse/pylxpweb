"""Endpoint-scoped shared dongle channel (pylxpweb#329).

A WiFi dongle fronts one RS485 bus and — as measured on a GridBOSS dongle
(2026-09-03 live probe) — *accepts* a second TCP client but cannot sustain
two: the later client is evicted repeatedly, replies are cross-routed
(correlation is positional, there is no transaction id), and the first
client's poll cadence degrades.  Every ``DongleTransport`` that targets the
same physical dongle must therefore share ONE serialized socket.

Model
-----
* **Key** — ``(normalized host, int port, dongle_serial)``.  The host is
  normalized by strip + lowercase only; it is never DNS-resolved.
* **Channel** — :class:`DongleChannel` owns everything that is per-socket:
  the stream reader/writer and receive buffer, the connection lock (the dial
  runs behind it, with a re-check after acquire, so two leases can never race
  the dongle's single slot), the transaction lock (drain → write → read →
  parse is one critical section), the operation lock (multi-step reads and
  read-modify-write sequences are serialized per *channel*, not per
  transport — a positional protocol cannot detect a same-register reply that
  lands on the wrong device's step), the TLS-PSK detection memo, the single
  ``connected`` boolean, and the lease set.
* **Leases** — a transport holds at most one lease per channel.  The
  refcount is derived (``len(leases)``) and mutated at exactly two sites:
  ``DongleTransport.connect()`` acquires (idempotent per transport) and
  ``disconnect()`` / ``async_shutdown()`` release (idempotent).  The last
  release closes the socket with the bounded-close discipline and retires
  the channel from the registry; a later ``connect()`` creates a fresh one.
* **Generation** — a monotonic counter bumped on every close.  A
  transaction records the generation it started on and fails coherently if
  the socket was replaced underneath it, instead of parsing a stale stream.
  There is deliberately no callback / observer list for failure propagation:
  siblings observe ``connected`` and ``generation`` directly.
* **Registry** — one module-level mapping per process, every lookup /
  create / retire under one process-wide ``threading.Lock`` (check-then-create
  never suspends, so it is also atomic on a single loop).  Channels are
  single-loop objects: an attach from a different running loop is refused.
* **Users and dialers** — ``_users`` counts tasks queued on or holding the
  transaction/operation locks; ``connect_owner`` names the transport whose
  ``connect()`` holds the connect lock and ``connect_waiters`` lists the
  transports queued for it.  A channel is retired only when it has no lease,
  no socket, no user, no dialer and no lock held, so a task queued on a lock
  never wakes on a retired channel — and ``async_shutdown()`` can tell its
  own dial from a sibling's without touching the lock.

The dial ladder itself (retry/backoff, TLS-PSK auto-detection, initial-data
discard) lives in ``DongleTransport._dial()``, called from ``connect()``
under this channel's connection lock, because it is parameterised by that
transport's per-operation knobs.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from .exceptions import DongleChannelLoopError, DongleChannelMismatchError
from .protocol import _ReentrantAsyncLock

if TYPE_CHECKING:
    from .dongle import DongleTransport

_LOGGER = logging.getLogger(__name__)


class _ChannelOpLock(_ReentrantAsyncLock):
    """The base transport's task-reentrant op lock, plus a ``locked()`` probe."""

    def locked(self) -> bool:
        """Whether any task currently holds the lock."""
        return self._owner is not None


DongleChannelKey = tuple[str, int, str]
"""``(normalized host, port, dongle_serial)`` — identity of one physical dongle."""

_CLOSE_TIMEOUT = 5.0
"""Bound on ``wait_closed()`` for ordinary (non-shutdown) closes."""


def make_channel_key(host: str, port: int, dongle_serial: str) -> DongleChannelKey:
    """Normalize an endpoint into its channel key (strip + lowercase host only)."""
    return (host.strip().lower(), int(port), dongle_serial)


def _running_loop_or_none() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


class DongleChannel:
    """Per-socket state shared by every lease on one dongle endpoint.

    Attributes are deliberately plain: ``DongleTransport`` is the only
    writer, and it always holds the appropriate lock (``connect_lock`` for
    stream replacement, ``transaction_lock`` for stream use).
    """

    def __init__(
        self,
        key: DongleChannelKey,
        *,
        ssl_mode: bool | None,
        shared: bool,
    ) -> None:
        self.key = key
        self.ssl_mode = ssl_mode
        self.shared = shared
        self._loop: asyncio.AbstractEventLoop | None = None
        # --- per-socket stream state (replace only under connect_lock) ---
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.receive_buffer = bytearray()
        self.connected = False
        self.generation = 0
        # --- locks; order is always transaction_lock -> connect_lock ---
        self.transaction_lock = asyncio.Lock()
        self.connect_lock = asyncio.Lock()
        self.op_lock = _ChannelOpLock()
        self.transaction_owner: DongleTransport | None = None
        # Dial bookkeeping: who holds connect_lock inside connect(), and who
        # is queued for it (a queued waiter captures the lock on release,
        # so "not locked()" alone never proves the lock is free to take).
        self.connect_owner: DongleTransport | None = None
        self.connect_waiters: list[DongleTransport] = []
        # --- TLS-PSK detection memo (per socket, shared by all leases) ---
        self.ssl_active = False
        self.ssl_proven = False
        self.ssl_unsupported_until: float | None = None
        self.ssl_unavailable_logged = False
        # --- leases and in-flight users ---
        self._leases: set[DongleTransport] = set()
        self._users = 0
        self.retired = False

    # ------------------------------------------------------------------
    # Leases
    # ------------------------------------------------------------------

    @property
    def lease_count(self) -> int:
        """Derived refcount: the number of transports currently leasing."""
        return len(self._leases)

    def holds_lease(self, transport: DongleTransport) -> bool:
        """Whether ``transport`` currently holds a lease on this channel."""
        return transport in self._leases

    def acquire_lease(self, transport: DongleTransport) -> None:
        """Record a lease for ``transport`` (idempotent)."""
        self._leases.add(transport)

    def release_lease(self, transport: DongleTransport) -> None:
        """Drop ``transport``'s lease (idempotent)."""
        self._leases.discard(transport)

    # ------------------------------------------------------------------
    # Loop affinity
    # ------------------------------------------------------------------

    def bind_loop(self) -> None:
        """Adopt the running loop, or refuse an attach from a foreign live loop.

        Raises:
            DongleChannelLoopError: The channel belongs to a different loop
                that is still open.
        """
        loop = _running_loop_or_none()
        if loop is None:
            return
        if self._loop is None:
            self._loop = loop
            return
        if self._loop is not loop:
            raise DongleChannelLoopError(
                f"Dongle channel {self.key[0]}:{self.key[1]} (dongle={self.key[2]}) "
                "belongs to a different running event loop; every transport sharing "
                "a dongle must run on the same loop"
            )

    def loop_is_dead(self) -> bool:
        """True when the owning loop has closed (the channel is garbage)."""
        return self._loop is not None and self._loop.is_closed()

    # ------------------------------------------------------------------
    # Socket lifecycle
    # ------------------------------------------------------------------

    async def close(self, *, timeout: float = _CLOSE_TIMEOUT) -> None:
        """Mark the socket broken, bump ``generation`` and close it (bounded).

        Callers replacing the stream hold ``connect_lock`` (``teardown``
        does); the terminal ``async_shutdown`` path calls this lock-free on
        purpose so a muted dongle cannot hold shutdown behind a transaction.
        Awaits ``wait_closed()`` (bounded) so the dongle's single slot is
        actually free before the next dial.
        """
        self.connected = False
        self.ssl_active = False
        self.reader = None
        self.receive_buffer.clear()
        writer = self.writer
        self.writer = None
        self.generation += 1
        if writer is not None:
            with contextlib.suppress(Exception):
                writer.close()
                await asyncio.wait_for(writer.wait_closed(), timeout=timeout)

    async def teardown(self, *, expected_generation: int | None = None) -> None:
        """Close under ``connect_lock`` so no lease dials while it drains.

        With ``expected_generation`` the teardown is stream-scoped: it closes
        only if the stream the caller ran on is still the current one.  If
        ``generation`` has already moved past it, someone else replaced the
        stream (a sibling's dial, a terminal shutdown) and the caller's
        failure says nothing about the new socket — leave it alone.  Without
        it the teardown is unconditional.
        """
        async with self.connect_lock:
            if expected_generation is not None and self.generation != expected_generation:
                return
            await self.close()

    @contextlib.asynccontextmanager
    async def transaction(self, owner: DongleTransport) -> AsyncIterator[None]:
        """Hold the transaction lock for one drain → write → read → parse cycle.

        Records ``owner`` so ``async_shutdown()`` can tell whether the
        shutting-down lease owns the in-flight transaction (tear down) or a
        sibling does (just release).  The caller counts as a user from before
        the lock is awaited until after it is released, so the channel cannot
        be retired underneath a queued waiter; retirement of an idle shared
        channel is attempted once the lock is released.
        """
        self._users += 1
        try:
            async with self.transaction_lock:
                self.transaction_owner = owner
                try:
                    yield
                finally:
                    self.transaction_owner = None
        finally:
            self._users -= 1
            self.retire_if_idle()

    @contextlib.asynccontextmanager
    async def operation(self) -> AsyncIterator[None]:
        """Hold the operation lock for one multi-step operation (same user rules)."""
        self._users += 1
        try:
            async with self.op_lock:
                yield
        finally:
            self._users -= 1
            self.retire_if_idle()

    # ------------------------------------------------------------------
    # Registry membership
    # ------------------------------------------------------------------

    def is_idle(self) -> bool:
        """No lease, no socket, nobody queued on or holding a lock, no dial."""
        return (
            not self._leases
            and not self.connected
            and self._users == 0
            and self.connect_owner is None
            and not self.connect_waiters
            and not self.op_lock.locked()
            and not self.transaction_lock.locked()
            and not self.connect_lock.locked()
        )

    def sibling_dialing(self, transport: DongleTransport) -> bool:
        """Whether another transport holds, or is queued for, the connect lock."""
        owner = self.connect_owner
        if owner is not None and owner is not transport:
            return True
        return any(waiter is not transport for waiter in self.connect_waiters)

    def retire_if_idle(self) -> bool:
        """Remove an idle shared channel from the registry.

        A retired channel is never reused: transports bound to it re-resolve
        through the registry on their next use.  A channel with a user (a task
        queued on or holding its operation/transaction lock) is never retired,
        so an operation always finishes on the channel it started on.
        """
        if self.retired or not self.shared or not self.is_idle():
            return False
        with _REGISTRY_LOCK:
            if _REGISTRY.get(self.key) is self:
                del _REGISTRY[self.key]
        self.retired = True
        return True


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------

_REGISTRY: dict[DongleChannelKey, DongleChannel] = {}
"""Live shared channels by key.  Every mutation happens under ``_REGISTRY_LOCK``."""

_REGISTRY_LOCK = threading.Lock()
"""Process-wide guard: loops on other threads must never race check-then-create."""


def _prune_dead_loops() -> None:
    """Drop channels whose loop has closed.  Caller holds ``_REGISTRY_LOCK``."""
    for key, channel in list(_REGISTRY.items()):
        if channel.loop_is_dead():
            del _REGISTRY[key]
            channel.retired = True


def resolve_shared_channel(key: DongleChannelKey, *, ssl_mode: bool | None) -> DongleChannel:
    """Return the live channel for ``key``, creating it if absent.

    Atomic check-then-create: the whole lookup/create runs under the
    process-wide registry lock and never suspends, so two transports
    resolving the same key — on one loop or on loops in different threads —
    can never both create a channel.

    Raises:
        DongleChannelMismatchError: ``key``'s host:port already has a channel
            with a different dongle serial, or the existing channel was
            created with a different TLS mode.
        DongleChannelLoopError: The existing channel belongs to another
            running loop.
    """
    with _REGISTRY_LOCK:
        _prune_dead_loops()
        channel = _REGISTRY.get(key)
        if channel is None:
            for other_key, other in _REGISTRY.items():
                if other_key[:2] == key[:2] and other_key[2] != key[2]:
                    raise DongleChannelMismatchError(
                        f"Dongle endpoint {key[0]}:{key[1]} is already attached with "
                        f"dongle_serial {other.key[2]!r}; refusing dongle_serial {key[2]!r} "
                        "(one physical dongle has one serial)"
                    )
            channel = DongleChannel(key, ssl_mode=ssl_mode, shared=True)
            channel.bind_loop()
            _REGISTRY[key] = channel
            _LOGGER.debug("Created shared dongle channel for %s:%s (%s)", key[0], key[1], key[2])
            return channel

        channel.bind_loop()
        if channel.ssl_mode != ssl_mode:
            raise DongleChannelMismatchError(
                f"Dongle endpoint {key[0]}:{key[1]} is already attached with "
                f"use_ssl={channel.ssl_mode!r}; refusing use_ssl={ssl_mode!r} "
                "(TLS mode is a per-socket fact)"
            )
        return channel
