"""Direct RS485 battery Modbus transport.

Connects to an RS485-to-TCP bridge (e.g., Waveshare) on the battery
daisy chain, separate from the inverter's Modbus connection.

Each battery unit has a unique Modbus unit ID (1=master, 2+=slave).
The transport auto-detects the protocol (master vs slave) per unit.

Data overlay (master battery only):
  The master protocol cannot provide per-cell temperatures via RS485
  (only aggregate MAX at reg 24). When ``read_all()`` receives inverter
  BMS data (already read during the inverter's normal refresh cycle),
  it overlays the missing fields onto the master's BatteryData.
  Slave batteries have complete data from RS485 and need no overlay.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Self

from pymodbus.client import AsyncModbusTcpClient

from pylxpweb.battery_protocols.base import BatteryProtocol
from pylxpweb.battery_protocols.detection import detect_protocol
from pylxpweb.battery_protocols.eg4_master import EG4MasterProtocol
from pylxpweb.battery_protocols.eg4_slave import EG4SlaveProtocol
from pylxpweb.transports.data import BatteryData, InverterRuntimeData

_LOGGER = logging.getLogger(__name__)

# Number of registers to read for initial runtime block (covers both protocols).
# This is a speculative union read issued before the protocol is known: the
# master map runs to reg 41, the slave map only to reg 38, so on every slave
# 3 of these registers are requested but never decoded.
_INITIAL_BLOCK_COUNT = 42

# Registers 0-18 decide master vs slave in ``detect_protocol``. A runtime read
# shorter than this must never reach detection: a truncated slave looks like a
# master (all-zero early registers) and the result is cached for the life of
# the transport. Both protocols need well past this, so it is a floor, not the
# acceptance threshold.
_DETECTION_REGISTER_COUNT = 19

# Small delay between sequential register reads to avoid bus congestion (seconds)
_INTER_READ_DELAY = 0.1

# Delay between sequential unit reads during scan or read_all (seconds)
_INTER_UNIT_DELAY = 0.2

# A unit that stops answering must not silently shrink the remembered topology
# and re-enable master back-calculation against a partial bank. Retention mirrors
# the 6h battery-eviction precedent (#258/#170) so a genuinely removed battery
# still converges instead of pinning the master to the aggregate forever (#249).
_UNIT_TOPOLOGY_RETENTION = 6 * 3600.0

# Minimum interval between reconnect attempts. This code uses an absolute
# deadline (``now < retry_after``), so 0.0 would not throttle the first attempt.
# None remains the honest "never attempted" state and protects a future change
# to the delta form whose 0.0 default caused the low-uptime EG4 #378/#380 bug.
_RECONNECT_COOLDOWN = 30.0

# Protocol name -> class mapping
_PROTOCOL_MAP: dict[str, type[BatteryProtocol]] = {
    "eg4_master": EG4MasterProtocol,
    "eg4_slave": EG4SlaveProtocol,
}


def _initial_block_requirement(protocol: BatteryProtocol) -> int:
    """Registers a protocol actually decodes out of the initial runtime read.

    Derived from the protocol's own blocks so it tracks map changes: the
    master runtime block ends at reg 41 (42 registers), the slave's at reg 38
    (39). Blocks that start past the initial read (master cells 113-128,
    slave info 105-127) are fetched separately and excluded here.

    Args:
        protocol: Protocol whose register map defines the requirement.

    Returns:
        Minimum number of registers the initial read must return for this
        protocol to decode without holes.
    """
    return max(
        (b.start + b.count for b in protocol.register_blocks if b.start < _INITIAL_BLOCK_COUNT),
        default=_DETECTION_REGISTER_COUNT,
    )


# Least any candidate protocol needs from the initial read. Accepting down to
# this instead of the full union avoids discarding a decodable slave, and the
# detected protocol's own requirement is re-checked afterwards.
_MIN_INITIAL_REGISTERS = max(
    _DETECTION_REGISTER_COUNT,
    min(_initial_block_requirement(cls()) for cls in _PROTOCOL_MAP.values()),
)


class BatteryModbusTransport:
    """Direct RS485 connection to battery BMS units.

    Connects to an RS485-to-TCP bridge that sits on the battery daisy
    chain. Each battery has its own Modbus unit ID.

    Supports async context manager for automatic connection management::

        async with BatteryModbusTransport(host="10.100.3.27") as bus:
            data = await bus.read_all()

    Args:
        host: Bridge IP address (e.g., "10.100.3.27").
        port: Modbus TCP port (default 502).
        unit_ids: Specific unit IDs to read. None = scan up to max_units.
        max_units: Maximum unit IDs to scan when unit_ids is None.
        protocol: Protocol name or "auto" for auto-detection.
        inverter_serial: Serial number of the inverter these batteries belong to.
        timeout: Modbus connection and read timeout in seconds.
    """

    def __init__(
        self,
        host: str,
        port: int = 502,
        unit_ids: list[int] | None = None,
        max_units: int = 8,
        protocol: str = "auto",
        inverter_serial: str = "",
        timeout: float = 3.0,
    ) -> None:
        self.host = host
        self.port = port
        self.unit_ids = unit_ids
        self.max_units = max_units
        self.protocol_name = protocol
        self.inverter_serial = inverter_serial
        self.timeout = timeout
        self._client: AsyncModbusTcpClient | None = None
        self._connected = False
        # Serializes every operation that uses the shared client across its
        # reconnect gate and reads. It is intentionally distinct from the
        # narrower reconnect state lock below (#248).
        self._operation_lock = asyncio.Lock()
        self._reconnect_lock = asyncio.Lock()
        self._reconnect_retry_after: float | None = None
        self._reconnect_warned = False
        self._consecutive_errors = 0
        self._max_consecutive_errors = 3
        self._empty_scan_warned = False
        # Unit degradation is transition-based so persistent faults warn once (#248).
        self._degraded_units: set[int] = set()
        self._unit_last_seen: dict[int, float] = {}
        # Units evicted from topology memory. Only a genuine response re-admits
        # one, which is what keeps the re-decode gate from flapping (#249).
        self._evicted_units: set[int] = set()
        # Cache detected protocols per unit ID
        self._detected_protocols: dict[int, BatteryProtocol] = {}

    @property
    def is_connected(self) -> bool:
        """Check if transport is connected to the RS485 bridge."""
        return self._connected and self._client is not None and bool(self._client.connected)

    async def __aenter__(self) -> Self:
        """Enter async context manager, connecting the transport."""
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
        """Establish a connection while excluding shared-client operations.

        Public lifecycle methods acquire the operation lock. Code that already
        owns it, such as ``_reconnect()``, must call ``_connect_locked()`` to
        preserve the operation -> reconnect lock order and avoid re-entry (#248).
        """
        async with self._operation_lock:
            await self._connect_locked()

    async def _connect_locked(self) -> None:
        """Establish a connection while the caller holds the operation lock."""
        self._client = AsyncModbusTcpClient(self.host, port=self.port, timeout=self.timeout)
        await self._client.connect()
        self._connected = self._client.connected
        if self._connected:
            _LOGGER.info("Connected to battery RS485 bridge at %s:%d", self.host, self.port)
        else:
            _LOGGER.error(
                "Failed to connect to battery RS485 bridge at %s:%d",
                self.host,
                self.port,
            )

    async def disconnect(self) -> None:
        """Close the connection while excluding shared-client operations.

        Public lifecycle methods acquire the operation lock. Code that already
        owns it must call ``_disconnect_locked()`` so this non-reentrant lock is
        never acquired twice (#248).
        """
        async with self._operation_lock:
            await self._disconnect_locked()

    async def _disconnect_locked(self) -> None:
        """Close the connection while the caller holds the operation lock."""
        if self._client:
            self._client.close()
        self._connected = False

    async def _reconnect(self) -> None:
        """Reconnect after the consecutive-error gate trips.

        ``_read_unit_raw_locked()`` and ``scan_units()`` call this while holding the
        operation lock, so no public read can queue work on a client being
        closed. The distinct reconnect lock protects the threshold/cooldown
        transition itself. Locks are always acquired operation-first and never
        in reverse, so reconnect and read serialization cannot deadlock.
        """
        async with self._reconnect_lock:
            if self._consecutive_errors < self._max_consecutive_errors:
                return

            now = time.monotonic()
            if self._reconnect_retry_after is not None and now < self._reconnect_retry_after:
                return
            self._reconnect_retry_after = now + _RECONNECT_COOLDOWN

            if not self._reconnect_warned:
                self._reconnect_warned = True
                _LOGGER.warning(
                    "Reconnecting battery RS485 bridge at %s:%d after %d consecutive errors",
                    self.host,
                    self.port,
                    self._consecutive_errors,
                )
            else:
                _LOGGER.debug(
                    "Reconnecting battery RS485 bridge at %s:%d after %d consecutive errors",
                    self.host,
                    self.port,
                    self._consecutive_errors,
                )

            await self._disconnect_locked()
            try:
                await self._connect_locked()
            except Exception as exc:
                # Reads are non-raising by contract. A connector implementation
                # that raises must not crash the whole battery poll (#248).
                _LOGGER.debug(
                    "Battery RS485 bridge reconnect at %s:%d raised: %s",
                    self.host,
                    self.port,
                    exc,
                )
                return

            if self.is_connected:
                self._consecutive_errors = 0
            else:
                # pymodbus normally returns False instead of raising when the
                # network is still down. Keep the gate tripped; cooldown, not a
                # fabricated reset, controls the next attempt (#248).
                _LOGGER.debug(
                    "Battery RS485 bridge reconnect at %s:%d did not connect",
                    self.host,
                    self.port,
                )

    def _recover_reconnect_episode(self) -> None:
        """Clear reconnect warning/cooldown after a real Modbus response."""
        if not self._reconnect_warned:
            return

        self._reconnect_warned = False
        self._reconnect_retry_after = None
        _LOGGER.info(
            "Battery RS485 bridge at %s:%d recovered after a successful read",
            self.host,
            self.port,
        )

    def _degrade_unit(
        self,
        unit_id: int,
        start: int,
        expected: int,
        got: int,
    ) -> None:
        """Warn once when a unit transitions into degraded reads.

        Args:
            unit_id: Modbus unit/slave ID.
            start: First register address of the failed block.
            expected: Minimum register count needed from the block.
            got: Register count returned, or zero on an error/exception.
        """
        if unit_id in self._degraded_units:
            return

        self._degraded_units.add(unit_id)
        _LOGGER.warning(
            "Battery unit %d read degraded: start=%d expected=%d got=%d registers. "
            "Possible causes: bus contention, wiring problems, a BMS that truncates "
            "responses, or the unit powered down (#248)",
            unit_id,
            start,
            expected,
            got,
        )

    def _recover_unit(self, unit_id: int) -> None:
        """Clear degradation after every block for a unit reads cleanly.

        Args:
            unit_id: Modbus unit/slave ID.
        """
        if unit_id not in self._degraded_units:
            return

        self._degraded_units.remove(unit_id)
        # Recovery is INFO: it confirms health without repeating the fault severity (#248).
        _LOGGER.info("Battery unit %d read recovered; all register blocks completed", unit_id)

    async def _read_registers(
        self,
        start: int,
        count: int,
        unit_id: int,
        minimum: int | None = None,
        probe: bool = False,
    ) -> list[int] | None:
        """Read holding registers from a battery unit.

        Args:
            start: First register address to read.
            count: Number of contiguous registers to read.
            unit_id: Modbus unit/slave ID.
            minimum: Registers that must come back for the response to be
                usable. Defaults to ``count``; pass a lower value only when
                the request deliberately over-reads what will be decoded.
            probe: Whether this is an expected-miss discovery probe. Probe
                failures do not affect degradation or reconnect state.

        Returns:
            List of register values, or None on error/timeout/short read.
        """
        required = count if minimum is None else minimum
        if not self._client:
            if not probe:
                self._consecutive_errors += 1
                self._degrade_unit(unit_id, start, required, 0)
            return None
        try:
            result = await self._client.read_holding_registers(
                start, count=count, device_id=unit_id
            )
            if result.isError():
                _LOGGER.debug(
                    "Modbus error response: unit=%d start=%d count=%d",
                    unit_id,
                    start,
                    count,
                )
                if not probe:
                    self._consecutive_errors += 1
                    self._degrade_unit(unit_id, start, required, 0)
                return None
            registers = list(result.registers)
            # pymodbus decodes registers from the response's own byte_count
            # and never checks it against the requested count, so a truncated
            # response returns a short list without error and would be
            # decoded as if complete, producing wrong battery values.
            # Reject it like any other failed read (same guard as the
            # holding-register paths on the inverter transports, #203).
            #
            # Rejecting a block does not make its fields absent: BatteryData
            # has no nullable cell fields, so a dropped block reads out as
            # zeroes or as whatever fallback the protocol has. See the note
            # on _read_unit_raw. The DEBUG detail is paired with a single
            # per-unit degradation transition WARNING (#248).
            if len(registers) < required:
                _LOGGER.debug(
                    "Short read: unit=%d start=%d expected %d registers, got %d",
                    unit_id,
                    start,
                    required,
                    len(registers),
                )
                if not probe:
                    self._consecutive_errors += 1
                    self._degrade_unit(unit_id, start, required, len(registers))
                return None
            if not probe:
                self._consecutive_errors = 0
                self._recover_reconnect_episode()
            return registers
        except Exception:
            _LOGGER.debug("Read failed: unit=%d start=%d count=%d", unit_id, start, count)
            if not probe:
                self._consecutive_errors += 1
                self._degrade_unit(unit_id, start, required, 0)
            return None

    def _get_protocol(self, unit_id: int, raw_regs: dict[int, int]) -> BatteryProtocol:
        """Get the protocol for a unit, auto-detecting if needed.

        Args:
            unit_id: Modbus unit/slave ID.
            raw_regs: Dict mapping register address to raw 16-bit value.

        Returns:
            BatteryProtocol instance for decoding this unit's registers.
        """
        if self.protocol_name != "auto":
            proto_cls = _PROTOCOL_MAP.get(self.protocol_name)
            if proto_cls:
                return proto_cls()
            _LOGGER.warning("Unknown protocol '%s', falling back to auto", self.protocol_name)

        # Check cache
        if unit_id in self._detected_protocols:
            return self._detected_protocols[unit_id]

        # Auto-detect from register values
        protocol = detect_protocol(raw_regs)
        self._detected_protocols[unit_id] = protocol
        _LOGGER.info("Auto-detected protocol '%s' for unit %d", protocol.name, unit_id)
        return protocol

    async def read_unit(self, unit_id: int) -> BatteryData | None:
        """Read a single battery unit, returning decoded BatteryData.

        Auto-detects the protocol (master vs slave) on first read.
        For master battery with slave context and BMS overlay, use
        ``read_all()`` instead.

        Args:
            unit_id: Modbus unit/slave ID (1=master, 2+=slave).

        Returns:
            BatteryData with all values scaled, or None if unit doesn't respond.
        """
        _, data = await self._read_unit_raw(unit_id)
        return data

    async def scan_units(self) -> list[int]:
        """Discover which unit IDs respond on the bus.

        If explicit unit_ids were provided at construction, returns them
        without probing. Otherwise, probes unit IDs 1 through max_units.

        Returns:
            List of responding unit IDs.
        """
        if self.unit_ids is not None:
            self._remember_polled_units(self.unit_ids)
            return self.unit_ids

        async with self._operation_lock:
            responding: list[int] = []
            for uid in range(1, self.max_units + 1):
                # Individual non-responding IDs are expected discovery misses,
                # not unit degradation or separate bus faults (#248).
                regs = await self._read_registers(0, 1, uid, probe=True)
                if regs is not None:
                    responding.append(uid)
                    self._observe_unit(uid)
                await asyncio.sleep(_INTER_UNIT_DELAY)

            if responding:
                self._consecutive_errors = 0
                if self._empty_scan_warned:
                    self._empty_scan_warned = False
                    _LOGGER.info(
                        "Battery bus scan at %s:%d has units responding again",
                        self.host,
                        self.port,
                    )
                self._recover_reconnect_episode()
            else:
                # Previously seeing units and now seeing none is the strongest
                # form of this signal, but a first-ever empty scan also deserves
                # reporting as likely bridge/bus failure or misconfiguration.
                # Count once per scan, never once per expected probe miss.
                self._consecutive_errors += 1
                if not self._empty_scan_warned:
                    self._empty_scan_warned = True
                    _LOGGER.warning(
                        "Battery bus scan at %s:%d: no units responded while probing 1-%d; "
                        "a bus/bridge fault or configuration error is likely (#248)",
                        self.host,
                        self.port,
                        self.max_units,
                    )
                if self._consecutive_errors >= self._max_consecutive_errors:
                    await self._reconnect()

        _LOGGER.info(
            "Battery bus scan: %d/%d units responding",
            len(responding),
            self.max_units,
        )
        return responding

    def _remember_polled_units(self, unit_ids: list[int]) -> None:
        """Seed topology memory for declared or discovered units.

        A configured unit must count before its first successful response;
        otherwise explicit configuration would permit the same partial-bank
        master back-calculation that topology memory prevents (#249).

        Args:
            unit_ids: Unit IDs declared or selected for the current poll.
        """
        now = time.monotonic()
        for unit_id in unit_ids:
            if unit_id in self._evicted_units:
                # Seeding a still-absent declared unit again would re-arm the
                # gate one cycle after eviction, so an explicitly configured but
                # removed battery would flap between individual and aggregate
                # SOC once per retention window instead of converging. Only a
                # genuine response re-admits an evicted unit (#249).
                continue
            self._unit_last_seen.setdefault(unit_id, now)

    def _observe_unit(self, unit_id: int) -> None:
        """Record a genuine response from a unit, re-admitting it if evicted.

        Args:
            unit_id: Modbus unit/slave ID that answered.
        """
        self._unit_last_seen[unit_id] = time.monotonic()
        self._evicted_units.discard(unit_id)

    def _remembered_unit_ids(self) -> set[int]:
        """Return retained topology, evicting units absent for six hours.

        Returns:
            Unit IDs still within the topology retention window.
        """
        now = time.monotonic()
        stale_units = [
            (unit_id, last_seen)
            for unit_id, last_seen in self._unit_last_seen.items()
            if now - last_seen > _UNIT_TOPOLOGY_RETENTION
        ]
        for unit_id, last_seen in stale_units:
            del self._unit_last_seen[unit_id]
            self._evicted_units.add(unit_id)
            _LOGGER.info(
                "Battery unit %d evicted from remembered topology after %.0f seconds "
                "without observation (#249)",
                unit_id,
                now - last_seen,
            )
        return set(self._unit_last_seen)

    async def read_all(
        self,
        inverter_bms_data: InverterRuntimeData | None = None,
    ) -> list[BatteryData]:
        """Read all battery units with master SOC back-calculation and BMS overlay.

        Reads slaves first, then re-decodes the master using slave context
        (for individual SOC/remaining capacity). If inverter BMS data is
        provided, overlays missing master fields (per-cell temperatures)
        that are only available via the inverter's CAN bus connection.

        Args:
            inverter_bms_data: Already-read inverter runtime data containing
                BMS fields (bms_max_cell_temperature, bms_min_cell_temperature,
                etc.). Passed from the inverter's normal refresh cycle to avoid
                redundant reads. Only used for the master battery.

        Returns:
            List of BatteryData objects for responding units, master first.
        """
        units = self.unit_ids or await self.scan_units()
        self._remember_polled_units(units)

        # Read all units, keeping track of raw registers for master re-decode
        raw_by_unit: dict[int, dict[int, int]] = {}
        slave_results: list[BatteryData] = []
        decoded_slave_ids: set[int] = set()
        master_uid: int | None = None
        master_data: BatteryData | None = None

        for uid in units:
            raw, data = await self._read_unit_raw(uid)
            if data is None:
                continue

            self._observe_unit(uid)
            raw_by_unit[uid] = raw
            protocol = self._get_protocol(uid, raw)

            if isinstance(protocol, EG4MasterProtocol):
                master_uid = uid
                master_data = data
            else:
                slave_results.append(data)
                decoded_slave_ids.add(uid)

            await asyncio.sleep(_INTER_UNIT_DELAY)

        # Re-decode only when decoded slave IDs cover the retained topology.
        # Thus a three-unit bank scanning as [1, 2] keeps aggregate reg 21, while
        # a genuine [1, 2] bank re-decodes. A one-unit bank has no slave result,
        # so its already-individual aggregate remains unchanged. After a removed
        # battery is absent for six hours it is evicted and re-decode resumes
        # against the remaining topology; this is intentional convergence (#249).
        #
        # KNOWN BOUNDARY -- auto-scan cold start. Topology memory cannot
        # remember a unit it has never seen, so on a fresh transport with
        # unit_ids=None whose first scan misses a unit, the remembered set is
        # already short and this gate passes on incomplete topology. It is the
        # original defect's shape in a narrow, self-healing window: the missing
        # unit's first genuine response is remembered permanently, after which
        # its silence blocks the gate like any other. Explicit unit_ids have no
        # such window because the declared list seeds memory before the first
        # read. Closing it would need a declared expected count, which is the
        # configuration auto-scan exists to avoid.
        remembered_unit_ids = self._remembered_unit_ids()
        required_slave_ids = (
            remembered_unit_ids - {master_uid} if master_uid is not None else remembered_unit_ids
        )
        if (
            master_uid is not None
            and master_data is not None
            and slave_results
            and decoded_slave_ids.issuperset(required_slave_ids)
        ):
            master_proto = self._get_protocol(master_uid, raw_by_unit[master_uid])
            if isinstance(master_proto, EG4MasterProtocol):
                master_data = master_proto.decode_with_slaves(
                    raw_by_unit[master_uid],
                    slave_results,
                    battery_index=master_uid - 1,
                )

        # Overlay inverter BMS data onto master (fills RS485 gaps)
        if master_data is not None and inverter_bms_data is not None:
            master_data = self._overlay_inverter_bms(master_data, inverter_bms_data)

        # Assemble results: master first, then slaves in order
        results: list[BatteryData] = []
        if master_data is not None:
            results.append(master_data)
        results.extend(slave_results)

        _LOGGER.info(
            "Read %d batteries from RS485 bus %s:%d",
            len(results),
            self.host,
            self.port,
        )
        return results

    async def _read_unit_raw(self, unit_id: int) -> tuple[dict[int, int], BatteryData | None]:
        """Read a single unit, returning both raw registers and decoded data.

        Args:
            unit_id: Modbus unit/slave ID.

        Returns:
            Tuple of (raw_registers, decoded_data). Raw registers are always
            returned (may be empty). Decoded data is None on read failure.

        Note:
            An extra block that fails is dropped whole rather than partially
            decoded. ``BatteryData`` has no nullable cell fields, so the
            master cell block becomes zeroed cells and the explicit 0.0
            absent pack-voltage sentinel. The unit remains degraded until a
            later read completes its runtime block and every extra block.
        """
        async with self._operation_lock:
            return await self._read_unit_raw_locked(unit_id)

    async def _read_unit_raw_locked(
        self, unit_id: int
    ) -> tuple[dict[int, int], BatteryData | None]:
        """Read one unit while the caller holds the shared-client operation lock."""
        if self._consecutive_errors >= self._max_consecutive_errors:
            await self._reconnect()

        runtime_regs = await self._read_registers(
            0, _INITIAL_BLOCK_COUNT, unit_id, minimum=_MIN_INITIAL_REGISTERS
        )
        if runtime_regs is None:
            return {}, None

        raw: dict[int, int] = dict(enumerate(runtime_regs))
        # Safe to detect: the guard above guarantees registers 0-18 are all
        # present, so a truncated response can no longer be cached as the
        # wrong protocol for the life of the transport.
        protocol = self._get_protocol(unit_id, raw)

        # A BMS that range-clamps a read past its last implemented register
        # (rather than answering ILLEGAL DATA ADDRESS) returns a slave's full
        # 39 registers for the 42 requested. That is complete data, so it is
        # only rejected when the detected protocol needs the missing tail.
        required = _initial_block_requirement(protocol)
        if len(runtime_regs) < required:
            _LOGGER.debug(
                "Short runtime read: unit=%d protocol=%s needs %d registers, got %d",
                unit_id,
                protocol.name,
                required,
                len(runtime_regs),
            )
            self._consecutive_errors += 1
            self._degrade_unit(unit_id, 0, required, len(runtime_regs))
            return {}, None

        unit_read_clean = True
        for block in protocol.register_blocks:
            if block.start >= _INITIAL_BLOCK_COUNT:
                extra = await self._read_registers(block.start, block.count, unit_id)
                if extra is not None:
                    for i, v in enumerate(extra):
                        raw[block.start + i] = v
                else:
                    unit_read_clean = False
                await asyncio.sleep(_INTER_READ_DELAY)

        battery_index = unit_id - 1
        data = protocol.decode(raw, battery_index=battery_index)
        if unit_read_clean:
            self._recover_unit(unit_id)
        return raw, data

    @staticmethod
    def _overlay_inverter_bms(
        master: BatteryData,
        bms: InverterRuntimeData,
    ) -> BatteryData:
        """Overlay inverter BMS fields onto master battery data.

        The master RS485 protocol only provides aggregate MAX temperature
        (reg 24) with no per-cell or min temperature. The inverter reads
        this data from the battery CAN bus and exposes it in its own
        registers. This method fills those gaps without overwriting any
        field that RS485 already provides accurately.

        Args:
            master: Master BatteryData from RS485 decode.
            bms: Inverter runtime data with BMS fields already populated.

        Returns:
            New BatteryData with gaps filled from inverter BMS.
        """
        # Only overlay temperature fields that RS485 can't provide.
        # Master RS485 sets both min and max to reg 24 (aggregate MAX),
        # so if inverter BMS has actual per-cell temps, use those.
        min_cell_temp = master.min_cell_temperature
        max_cell_temp = master.max_cell_temperature
        if bms.bms_min_cell_temperature is not None:
            min_cell_temp = bms.bms_min_cell_temperature
        if bms.bms_max_cell_temperature is not None:
            max_cell_temp = bms.bms_max_cell_temperature

        return BatteryData(
            battery_index=master.battery_index,
            serial_number=master.serial_number,
            voltage=master.voltage,
            current=master.current,
            soc=master.soc,
            soh=master.soh,
            temperature=master.temperature,
            max_capacity=master.max_capacity,
            current_capacity=master.current_capacity,
            cycle_count=master.cycle_count,
            cell_count=master.cell_count,
            cell_voltages=master.cell_voltages,
            cell_temperatures=master.cell_temperatures,
            min_cell_voltage=master.min_cell_voltage,
            max_cell_voltage=master.max_cell_voltage,
            min_cell_temperature=min_cell_temp,
            max_cell_temperature=max_cell_temp,
            max_cell_num_voltage=master.max_cell_num_voltage,
            min_cell_num_voltage=master.min_cell_num_voltage,
            max_cell_num_temp=master.max_cell_num_temp,
            min_cell_num_temp=master.min_cell_num_temp,
            charge_voltage_ref=master.charge_voltage_ref,
            charge_current_limit=master.charge_current_limit,
            discharge_current_limit=master.discharge_current_limit,
            discharge_voltage_cutoff=master.discharge_voltage_cutoff,
            model=master.model,
            firmware_version=master.firmware_version,
            status=master.status,
            fault_code=master.fault_code,
            warning_code=master.warning_code,
        )
