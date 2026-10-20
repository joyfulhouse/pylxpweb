# Modbus connection ownership and scheduling

`ModbusTransport` and `ModbusSerialTransport` accept a host-provided `unit=`
from `modbus-connection`. The host owns that connection's lifetime and the
policy for sharing its physical gateway or bus. pylxpweb borrows the unit;
disconnecting a pylxpweb transport does not close the host's connection.
Error recovery may call the unit's `disconnect()` to recycle the link, so
other consumers of that link must tolerate reconnection.

## Request serialization is per connection

In `modbus-connection` 4.12.3 and 4.12.5, unit requests run inside the connection's
`Pacer.paced()` context. Its lock serializes requests even when
`message_spacing` is zero. Two unit handles from the same connection,
including handles for different unit IDs, therefore do not pipeline their
requests. tmodbus's ability to match TCP transaction IDs does not change
that guarantee at the shared-unit API.

The minimum supported `modbus-connection` 4.10.0 bypasses its pacing lock
when spacing is zero. Its tmodbus TCP factory still uses `AsyncSmartTransport`,
whose communication lock serializes requests on that connection. The scheduling
regression exercises both real lock layers and stubs only the underlying wire;
it covers 4.10.0, 4.12.3, and 4.12.5 with tmodbus 0.6.2. This guarantee does not
describe an application using tmodbus's bare TCP transport directly.

| Scope | Guarantee |
| --- | --- |
| One pylxpweb transport | Its operation lock protects that transport's multi-step operations. |
| Multiple units from one `ModbusConnection` | The connection serializes individual requests and applies its configured pacing. |
| Separate `ModbusConnection` instances at the same endpoint | Their locks and pacing are independent; requests can overlap. |
| Different applications or processes | An asyncio lock in one host cannot coordinate the other application. |

Serialization and spacing are distinct. Zero spacing still prevents concurrent
requests on one connection, but does not impose a quiet interval after a
response. The host can configure `ModbusConnection(message_spacing=...)` or a
unit's `set_message_spacing(...)` using a requirement established for its
gateway. pylxpweb's `inter_register_delay` is local to a transport and is not
an endpoint-wide pacing setting. No universal gateway delay is assumed.

## Host contract for gateways that cannot pipeline

1. Prefer one host-owned connection and inject its unit handles into every
   cooperating consumer. In Home Assistant, use its `async_get_unit()`
   ownership mechanism and release the host's holds on unload.
2. Identify the physical resource shared by all requests. Different unit IDs
   behind one gateway share the same bus. Hostname aliases or separate network
   ports can also reach the same physical resource; an exact host/port key
   alone does not establish that they are independent.
3. If separate connections are unavoidable, the host must schedule all of
   them through one endpoint policy, including retries and other integrations'
   requests. A lock attached only to one pylxpweb transport cannot provide
   this guarantee. Do not silently open an independent connection after a
   shared-connection configuration conflict on an exclusive gateway.
4. If an entire read/modify/write sequence must be atomic across consumers,
   coordinate that complete operation at the host. A connection's request
   lock is released between separate requests and cannot make a multi-step
   operation atomic across two pylxpweb transports.
5. Define cancellation, timeout, reconnect, and unload behavior in the host
   scheduler. Cancelling a queued caller must not close another consumer's
   borrowed connection or leave endpoint ownership held indefinitely.

Tests for a host scheduler should demonstrate one in-flight request across
distinct connections, shared scheduling across unit IDs, configured quiet
intervals, and recovery after cancellation/reconnect/unload. Use events or a
fake clock to verify ordering; gateway-specific timing still requires evidence
from the target device.

[Issue #350](https://github.com/joyfulhouse/pylxpweb/issues/350) tracks the host
dependency. pylxpweb does not supply a global endpoint scheduler, and this
document does not establish that a particular host implements one.

## Close completion and owned-link release

As checked on 2026-10-20, tmodbus 0.6.2 is the latest published release. Its
async RTU and TCP transport `close()` methods call the underlying synchronous
`close()` without waiting for resource release. serialx can finish releasing
the descriptor or ESPHome connection later. An already-closing transport also
returns immediately from tmodbus's `close()`.

pylxpweb retains its owned-connection release gate: an observable pending
release prevents a replacement link from dialing, even if the bounded close
wait expires. The gate uses private upstream layout and is not an
endpoint-wide scheduler. A borrowed host connection does not pass through
pylxpweb's owned-connection gate; its host must manage lifecycle safety.
Plain asyncio TCP transports do not expose the same `wait_closed()` hook,
so the gate must not be interpreted as proof of TCP peer-side release.

[Issue #345](https://github.com/joyfulhouse/pylxpweb/issues/345) remains blocked
on an upstream release with a public, verified close-completion contract.
The upstream request and no-hardware reproduction are recorded in
[tmodbus #153](https://github.com/wlcrs/tmodbus/issues/153).
Before removing the gate, validate normal close, repeated/already-closing
close, cancellation, failed open cleanup, and reconnect on the supported
dependency versions. Updating documentation or testing a development commit
does not establish that the fix has shipped.
