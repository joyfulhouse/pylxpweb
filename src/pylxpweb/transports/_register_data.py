"""Shared register data operations for Modbus-based transports.

Provides ``RegisterDataMixin`` which implements all register-level data
reading/writing methods shared between ``BaseModbusTransport`` and
``DongleTransport``.  The mixin assumes the host class exposes:

- ``_read_input_registers(start, count) -> list[int]``
- ``_read_holding_registers(start, count) -> list[int]``
- ``_write_holding_registers(start, values) -> None``
- ``_serial: str``
- ``_inter_register_delay: float``
- ``_inverter_family: InverterFamily | None``

At *runtime* ``_DataMixinBase`` resolves to ``object`` so the MRO is
unchanged.  Under ``TYPE_CHECKING`` it supplies typed stubs for mypy.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pylxpweb.registers import (
    BATTERY_BASE_ADDRESS,
    BATTERY_MAX_COUNT,
    BATTERY_REGISTER_COUNT,
    PV4_6_ENERGY_INPUT_REGISTER_GROUP,
    PV4_6_INPUT_REGISTER_GROUP,
)

from ._canonical_reader import read_battery_serial
from ._register_readers import (
    is_midbox_device,
    read_device_type_async,
    read_firmware_version_async,
    read_parallel_config_async,
    read_serial_number_async,
)
from .data import (
    BatteryBankData,
    InverterEnergyData,
    InverterRuntimeData,
    MidboxRuntimeData,
)
from .exceptions import (
    TransportReadError,
    TransportResponseMismatchError,
    TransportTimeoutError,
)

if TYPE_CHECKING:
    from pylxpweb.devices.inverters._features import InverterFamily

_LOGGER = logging.getLogger(__name__)

# Minimum length for a BMS-reported battery serial to be trusted as a stable
# identity.  Shorter strings are truncated/partial reads; such a slot falls
# back to position-based identity until its full serial appears.  Mirrors the
# integration's round-robin merge threshold (coordinator_local._MIN_SERIAL_LENGTH).
_MIN_BATTERY_SERIAL_LEN = 10

# Rotation-stall watchdog (eg4_web_monitor#258).  Firmware rotates >4 batteries
# through the 4 physical slots; a battery not surfaced for the effective
# threshold means rotation has stalled/pinned for it — the 2026-06-28 incident
# pinned one page for ~9 HOURS with zero non-debug logs (every block read
# succeeded; the data was just frozen).  One latched WARNING per battery per
# stall episode makes that state visible; HYBRID compensates via the
# supplemental cloud refresh, LOCAL has no compensation so the warning is the
# only signal.
#
# Calibration (#170): a 12-battery system (3 pages of 4) surfaces every battery
# within ~30 minutes worst-case, i.e. ~10 min/page.  The effective threshold is
# max(this 45-minute floor, pages x 15 min) — 15 min/page carries a 50% margin
# over the measured cadence, and the floor keeps small arrays quiet, so a
# 24-battery (6-page) array warns at 90 min instead of spamming at 45.
BATTERY_ROTATION_STALL_WARN_AFTER = timedelta(minutes=45)
_BATTERY_STALL_PER_PAGE = timedelta(minutes=15)

# Empty-bank convergence (#282 review): consecutive SUCCESSFUL block reads
# reporting reg 96 = 0 with an all-ghost page before the never-evict
# accumulator is retired.  One or two empty reads are indistinguishable from
# a transient reg-96/bms glitch (the reason the gate guard exists); three in
# a row on a healthy link means the batteries are genuinely gone.
_BATTERY_EMPTY_BANK_RETIRE_STREAK = 3

# ---------------------------------------------------------------------------
# Register group constants (unified across Modbus and Dongle transports)
# ---------------------------------------------------------------------------
# Based on the 40-register-per-call convention for pymodbus/dongle protocol.
# Battery registers use a single atomic read (up to 120 regs) to avoid
# round-robin rotation issues on systems with >4 batteries (#170).
#
# Source: EG4-18KPV-12LV Modbus Protocol + eg4-modbus-monitor + Yippy's BMS docs

INPUT_REGISTER_GROUPS: dict[str, tuple[int, int]] = {
    "power_energy": (0, 32),  # Registers 0-31: Power, voltage, SOC/SOH, current
    "status_energy": (32, 32),  # Registers 32-63: Status, energy, fault/warning codes
    "temperatures": (64, 16),  # Registers 64-79: Temps, currents, fault history
    "bms_data": (80, 33),  # Registers 80-112: BMS passthrough data
    "extended_data": (113, 41),  # Regs 113-153: Parallel, generator, EPS, per-leg, AC couple
    "eps_split_phase": (140, 3),  # Registers 140-142: EPS L1/L2 voltages
    "output_power": (170, 4),  # Regs 170-173: output power + load energy (171, 172-173)
    "split_phase_grid": (193, 12),  # Registers 193-204: Split-phase grid voltages + per-leg power
}

# GridBOSS/MID register groups for ``read_midbox_runtime``
MIDBOX_REGISTER_GROUPS: list[tuple[int, int]] = [
    (0, 40),  # Voltages, currents, power, smart loads 1-3
    (40, 28),  # Smart load 4 power + energy today
    (68, 40),  # Energy totals
    (108, 12),  # AC couple port 3-4 totals
    (128, 4),  # Frequencies
]

# ---------------------------------------------------------------------------
# Configurable input-register block coalescing (eg4_web_monitor#254)
# ---------------------------------------------------------------------------
# The vendor Modbus RTU doc (2025/6/13) specifies reads must not span
# 40-register block boundaries on old firmware; newer dongles/firmware accept
# up to the Modbus FC04 PDU cap (125 registers; DG dongle fw 2.04-2.09 field-
# verified at 120).  ``max_input_block_size`` lets capable hardware coalesce
# the adjacent INPUT_REGISTER_GROUPS into fewer transactions.  The default
# keeps the plain per-group reads (byte-identical to previous releases).
#
# GridBOSS/MID reads are deliberately NOT coalesced: >40-register midbox
# reads empirically failed on real GridBOSS hardware (see f050eb2, "fix
# critical 40-register hardware limit bug ... for GridBOSS midbox runtime
# reads"), so MIDBOX_REGISTER_GROUPS stays chunked at <=40 regardless of
# this setting.

DEFAULT_INPUT_BLOCK_SIZE = 40
"""Conservative default: no coalescing — reads are exactly the group table.

40 is the documented per-read cap of the oldest dongle firmware.  Multiples
of 40 are recommended for larger values (the vendor doc's block convention);
120 is the field-proven fast setting.
"""

MAX_INPUT_BLOCK_SIZE = 125
"""Modbus FC04 PDU limit (the dongle frame's u8 byte count caps at 127)."""

COALESCING_MISMATCH_COOLDOWN = 300.0
"""Seconds of plain grouped reads after a misrouted-frame coalesced fallback.

A misrouted/unsolicited dongle frame does not latch coalescing off (#320) —
it re-probes automatically.  But under *persistent* misrouting (e.g. a busy
parallel cloud poller) that would re-fail a big read every cycle.  After a
mismatch fallback the transport reverts to plain reads for this window, then
re-probes coalescing once — bounding the retry cost without a permanent latch.
"""


def validate_input_block_size(value: int) -> int:
    """Validate a ``max_input_block_size`` setting.

    Args:
        value: Requested maximum registers per coalesced input read.

    Returns:
        The validated value.

    Raises:
        ValueError: If outside ``DEFAULT_INPUT_BLOCK_SIZE..MAX_INPUT_BLOCK_SIZE``.
    """
    if not DEFAULT_INPUT_BLOCK_SIZE <= value <= MAX_INPUT_BLOCK_SIZE:
        raise ValueError(
            f"max_input_block_size must be {DEFAULT_INPUT_BLOCK_SIZE}.."
            f"{MAX_INPUT_BLOCK_SIZE} (40-multiples recommended; got {value})"
        )
    return int(value)


@dataclass(frozen=True, slots=True)
class _ReadBlock:
    """One planned input-register read (a single Modbus transaction)."""

    members: tuple[str, ...]
    """Constituent group names (length 1 = plain, unmerged group read)."""

    start: int
    count: int

    @property
    def label(self) -> str:
        """Human-readable name for logs ('power_energy+status_energy+...')."""
        return "+".join(self.members)

    @property
    def coalesced(self) -> bool:
        """Whether this block merges multiple groups (fallback-eligible)."""
        return len(self.members) > 1


class _CoalescedReadFallback(Exception):
    """Internal: a coalesced block read failed; retry with plain group reads."""


def coalesce_register_groups(
    groups: Sequence[tuple[str, tuple[int, int]]],
    max_block_size: int,
) -> list[_ReadBlock]:
    """Merge contiguous/overlapping register groups into larger read blocks.

    Generic span coalescing: groups are merged only when the next group's
    start lies within (or exactly at the end of) the running block, so a
    merged block is always the exact union of its members' spans — it never
    reads an address the plain grouped reads don't already read.  Registers
    in the gaps *between* groups (which may misbehave or not exist on some
    models) are never bridged, no matter the block size.

    A single group larger than ``max_block_size`` is never split; it stays
    one read, exactly as in the plain plan.

    Args:
        groups: ``(name, (start, count))`` pairs (e.g. INPUT_REGISTER_GROUPS
            items, or a subset).
        max_block_size: Maximum registers per merged read.

    Returns:
        Ordered read plan covering the same addresses as ``groups``.
    """
    merged: list[tuple[list[str], int, int]] = []  # (names, start, end)
    for name, (start, count) in sorted(groups, key=lambda g: (g[1][0], g[1][0] + g[1][1])):
        end = start + count
        if merged:
            names, run_start, run_end = merged[-1]
            new_end = max(run_end, end)
            if start <= run_end and new_end - run_start <= max_block_size:
                names.append(name)
                merged[-1] = (names, run_start, new_end)
                continue
        merged.append(([name], start, end))
    return [_ReadBlock(tuple(names), start, end - start) for names, start, end in merged]


# ---------------------------------------------------------------------------
# TYPE_CHECKING-only base class for mixin attribute stubs
# ---------------------------------------------------------------------------

if TYPE_CHECKING:

    class _DataMixinBase:
        """Typed stubs so mypy sees attributes provided by the host class."""

        _serial: str
        _inter_register_delay: float
        _inverter_family: InverterFamily | None
        _split_phase: bool
        _pv_string_count: int
        _max_input_block_size: int

        async def _read_input_registers(self, start: int, count: int) -> list[int]: ...

        async def _read_holding_registers(self, start: int, count: int) -> list[int]: ...

        async def _write_holding_registers(self, start: int, values: list[int]) -> bool: ...

else:
    _DataMixinBase = object


# ---------------------------------------------------------------------------
# Mixin
# ---------------------------------------------------------------------------


class RegisterDataMixin(_DataMixinBase):
    """Shared register data reading/writing for Modbus-based transports.

    Concrete transports must provide the low-level register I/O methods
    (``_read_input_registers``, ``_read_holding_registers``,
    ``_write_holding_registers``) and set ``_inter_register_delay``
    in their ``__init__``.
    """

    # Last-seen HOLD 110 value, opportunistically stashed by
    # read_parameters()/write_parameters() when register 110 passes through
    # an existing call (never triggers a read of its own).  Bit 3 is
    # FUNC_BAT_SHARED — on a shared-bank *secondary* inverter (not on the
    # battery CAN bus) reg96=0 is expected, and the battery_count debug
    # lines annotate that so logs are not misread (eg4_web_monitor#288,
    # the #282/#258 red herring).
    _last_hold_110: int | None = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _registers_from_values(start: int, values: list[int]) -> dict[int, int]:
        """Build address-to-value dict from a contiguous register read."""
        return {start + offset: value for offset, value in enumerate(values)}

    def _shared_battery_note(self, battery_count: int) -> str:
        """Debug-log annotation for reg96=0 on a shared-battery secondary.

        Returns a suffix for the ``battery_count (reg 96)`` debug lines when
        the last-seen HOLD 110 has FUNC_BAT_SHARED (bit 3) set and reg 96
        reads 0 — the expected state on a secondary inverter sharing another
        inverter's battery bank (eg4_web_monitor#288).  Empty string
        otherwise, or when HOLD 110 has not passed through this transport yet.
        """
        if battery_count == 0 and self._last_hold_110 is not None and self._last_hold_110 & 0x8:
            return " (shared-battery secondary — reg96=0 expected)"
        return ""

    async def _read_individual_battery_registers(
        self,
        battery_count: int,
    ) -> dict[int, int] | None:
        """Read battery slots atomically and accumulate across round-robin cycles.

        All 4 slots (120 registers) are read in one Modbus FC 04 call starting
        at ``BATTERY_BASE_ADDRESS`` (5002).  This fits within the Modbus PDU
        limit of 125 registers and ensures firmware round-robin rotation cannot
        change slot contents between reads (#170).

        **Serial-keyed round-robin accumulation** (#170, #258):

        Firmware rotates batteries through the 4 register slots; each read sees
        one "page" of up to 4 batteries.  ``_battery_accumulator`` maps a stable
        battery *identity* to that battery's 30-register block.  Identity is the
        BMS serial (offsets 17-23) when present, else the firmware slot position
        (offset 24 high byte) as a fallback.  ``_battery_slot_index`` assigns
        each identity a stable virtual slot, so the merged map presents every
        accumulated battery in a contiguous slot range
        (``BATTERY_BASE_ADDRESS + slot * BATTERY_REGISTER_COUNT + offset``).

        ``battery_count`` (reg 96) is deliberately NOT used for gating,
        clearing, or counting: it under-reports on parallel systems (#170 saw
        12 for a 6-battery bank; #258's 5-battery rig intermittently reads 4).
        Accumulated entries are never evicted, so a momentary under-report or a
        battery rotating out of the visible page never drops it.

        Args:
            battery_count: Value from register 96 (total batteries reported).
                Used only for debug logging.

        Returns:
            Dict of address→value for all accumulated batteries, or *None*
            if the read failed or no battery slots are populated.
        """
        # reg 96 (battery_parallel_count) is unreliable on parallel systems:
        # #170 reported 12 for a 6-battery bank, and the #258 5-battery rig
        # intermittently reads 4.  We therefore IGNORE battery_count for
        # gating, clearing, and counting — it is kept only for the debug log.
        # All physical slots are always read and accumulated by stable battery
        # identity so a momentary under-report never drops a battery.
        total_registers = BATTERY_MAX_COUNT * BATTERY_REGISTER_COUNT
        _LOGGER.debug(
            "[%s] Reading %d battery slots (%d regs) in single read (reg96=%d)",
            self._serial,
            BATTERY_MAX_COUNT,
            total_registers,
            battery_count,
        )

        try:
            values = await self._read_input_registers(BATTERY_BASE_ADDRESS, total_registers)
        except Exception:
            # eg4_web_monitor#258 (2026-06-28): returning None here while the
            # bms_data group succeeded made the caller build a bank with
            # batteries=[] that REPLACED the cached one — every individual
            # battery vanished for the cycle even though the accumulator still
            # held them all.  Serve the accumulator's last-known blocks instead;
            # their last_seen stamps stay old (not re-stamped), so the hybrid
            # supplemental gate and the integration's freshness overlay see the
            # staleness honestly.  Only a first-poll failure (nothing
            # accumulated yet) still returns None.
            cached = self._merged_accumulator_registers()
            if cached is None:
                _LOGGER.warning(
                    "[%s] Failed to read battery registers %d-%d, will retry next poll",
                    self._serial,
                    BATTERY_BASE_ADDRESS,
                    BATTERY_BASE_ADDRESS + total_registers - 1,
                )
                return None
            _LOGGER.warning(
                "[%s] Failed to read battery registers %d-%d; serving %d "
                "accumulated batteries from the last good read, will retry next poll",
                self._serial,
                BATTERY_BASE_ADDRESS,
                BATTERY_BASE_ADDRESS + total_registers - 1,
                len(getattr(self, "_battery_accumulator", {})),
            )
            return cached

        raw_registers = self._registers_from_values(BATTERY_BASE_ADDRESS, values)

        # --- Serial-keyed round-robin accumulation (#170, #258) ---
        # Firmware rotates batteries through the 4 fixed register slots.  Each
        # slot's block is accumulated under a stable identity — the BMS serial
        # when present, else the firmware slot position (offset 24 high byte) as
        # a fallback for BMS that don't report a serial.  Entries are NEVER
        # evicted: a battery the firmware rotates out keeps its last-known data
        # so its entities stay populated.  Each identity is assigned a stable
        # virtual slot so the merged map presents every accumulated battery in
        # a contiguous slot range for the parser.
        accumulator: dict[str, dict[int, int]] = getattr(self, "_battery_accumulator", {})
        slot_index: dict[str, int] = getattr(self, "_battery_slot_index", {})
        last_seen: dict[int, datetime] = getattr(self, "_battery_last_seen", {})
        # tz-aware UTC: last_seen crosses into Home Assistant, which would
        # interpret a naive datetime as its own local zone (eg4_web_monitor#258).
        now = datetime.now(UTC)

        # Raw physical-slot -> identity page for rotation diagnostics
        # (eg4_web_monitor#258): the accumulator log below reports VIRTUAL slots
        # and the merged map hides which battery occupies each PHYSICAL slot, so
        # firmware rotation cannot be characterized from logs.  Diffing this line
        # across reads shows exactly when a battery rotates into/out of a slot.
        raw_page: list[str] = []
        page_has_active_slot = False
        # Identities already claimed by earlier slots of THIS page, for the
        # duplicate-serial guard below (eg4_web_monitor#258).
        page_identities: set[str] = set()

        for phys_slot in range(BATTERY_MAX_COUNT):
            slot_base = BATTERY_BASE_ADDRESS + (phys_slot * BATTERY_REGISTER_COUNT)
            status = raw_registers.get(slot_base, 0)
            if not status:
                raw_page.append(f"{phys_slot}=empty")
                continue  # Empty physical slot — skip

            # Ghost slot: status set but no electrical data (canonical ghost
            # definition, voltage=0 and soc=0).  Counted as inactive for the
            # empty-bank convergence streak below.
            slot_voltage = raw_registers.get(slot_base + 6, 0)
            slot_soc = raw_registers.get(slot_base + 8, 0) & 0xFF
            if slot_voltage or slot_soc:
                page_has_active_slot = True

            # Extract this slot's 30-register block (using slot-local offsets 0-29)
            slot_regs: dict[int, int] = {}
            for offset in range(BATTERY_REGISTER_COUNT):
                addr = slot_base + offset
                if addr in raw_registers:
                    slot_regs[offset] = raw_registers[addr]

            # Identity: prefer the BMS serial (the only identity stable across
            # rotation).  Serial occupies offsets 17-23 (offset 24's high byte is
            # the position index, filtered out by read_battery_serial).
            #   - valid serial (>= min length) → key by serial
            #   - serial regs present but decode too short → partial/corrupt read;
            #     SKIP this poll (the battery reappears with a full serial on a
            #     later rotation).  Minting a fallback identity here would make one
            #     physical battery accumulate twice and never evict.
            #   - no serial regs at all → genuinely serial-less BMS; fall back to
            #     the firmware slot position.
            serial = read_battery_serial(raw_registers, base_address=slot_base)
            serial_reported = any(raw_registers.get(slot_base + off, 0) for off in range(17, 24))
            pos = (raw_registers.get(slot_base + 24, 0) >> 8) & 0xFF
            serial_valid = bool(serial) and len(serial) >= _MIN_BATTERY_SERIAL_LEN
            if serial_valid:
                identity = serial
                if identity in page_identities:
                    # Duplicate serial WITHIN one page: two physical slots
                    # claiming one identity (corrupt serial bytes during a
                    # misroute storm, or genuinely duplicated serial strings).
                    # Silent last-write-wins would collapse two packs into one
                    # accumulator entry and hide a battery with no log trace
                    # (eg4_web_monitor#258).  Disambiguate the later slot by
                    # the battery's bank position (offset 24 high byte —
                    # stable per battery across rotation) and warn once per
                    # colliding serial.
                    identity = f"{serial}@pos{pos}"
                    dup_warned: set[str] = getattr(self, "_battery_dup_serial_warned", set())
                    if serial not in dup_warned:
                        dup_warned.add(serial)
                        self._battery_dup_serial_warned = dup_warned
                        _LOGGER.warning(
                            "[%s] Two battery slots in one page report the same "
                            "serial %r; keeping both, disambiguating the second "
                            "as %r by bank position (duplicate or corrupt BMS "
                            "serial)",
                            self._serial,
                            serial,
                            identity,
                        )
            elif serial_reported:
                raw_page.append(f"{phys_slot}={serial!r}~trunc")
                _LOGGER.debug(
                    "[%s] slot %d: truncated serial %r — skipping this poll",
                    self._serial,
                    phys_slot,
                    serial,
                )
                continue
            else:
                identity = f"pos:{pos}"

            # Synthetic @pos reconciliation (#258 review P1): a "{serial}@posN"
            # entry is only a snapshot of a SUSPECT read at bank position N.
            # When position N is next read successfully under a different
            # identity, that snapshot is stale — evict it so transient serial
            # corruption self-heals instead of publishing a phantom twin until
            # full-bank retirement.  A genuine duplicate pack appears in the
            # same page as its twin and re-mints its @pos entry right there
            # (the entry's own read ends with the suffix, so it never evicts
            # itself) — the collapse protection above is preserved.
            pos_suffix = f"@pos{pos}"
            if not identity.endswith(pos_suffix):
                for stale_key in [k for k in accumulator if k.endswith(pos_suffix)]:
                    del accumulator[stale_key]
                    stale_slot = slot_index.get(stale_key)
                    if stale_slot is not None:
                        # Keep the slot_index reservation: virtual slots are
                        # assigned as len(slot_index), so deleting the row
                        # would let a future identity collide with a live
                        # slot.  Only the data and its clock are retired.
                        last_seen.pop(stale_slot, None)
                    stall_warned: set[str] = getattr(self, "_battery_stall_warned", set())
                    stall_warned.discard(stale_key)
                    self._battery_stall_warned = stall_warned
                    _LOGGER.info(
                        "[%s] Evicted synthetic duplicate-serial entry %r: bank "
                        "position %d was read successfully as %r (transient "
                        "serial corruption self-healed)",
                        self._serial,
                        stale_key,
                        pos,
                        identity,
                    )

            # Positional-fallback reconciliation (symmetric to the @posN
            # eviction above): a "pos:N" entry is a snapshot taken while bank
            # position N's serial string was entirely unreadable (offsets 17-23
            # all zero on a good read).  On a cold start the electrical data can
            # arrive before the serial, minting pos:N; once the serial becomes
            # readable, the real serial key is created and pos:N is stale — but
            # it never ends with the @posN suffix, so the loop above misses it
            # and it lingers forever as a frozen phantom twin (each key holds a
            # distinct virtual slot).  Exactly one battery occupies a bank
            # position, so when a VALID serial is read at position N the pos:N
            # fallback is unambiguously the same pack — evict it.
            if serial_valid:
                pos_fallback_key = f"pos:{pos}"
                if pos_fallback_key in accumulator:
                    del accumulator[pos_fallback_key]
                    stale_slot = slot_index.get(pos_fallback_key)
                    if stale_slot is not None:
                        last_seen.pop(stale_slot, None)
                    stall_warned = getattr(self, "_battery_stall_warned", set())
                    stall_warned.discard(pos_fallback_key)
                    self._battery_stall_warned = stall_warned
                    _LOGGER.info(
                        "[%s] Evicted positional-fallback entry %r: bank position "
                        "%d was read successfully as %r (serial became readable)",
                        self._serial,
                        pos_fallback_key,
                        pos,
                        identity,
                    )

            raw_page.append(f"{phys_slot}={identity}")
            page_identities.add(identity)
            if identity not in slot_index:
                slot_index[identity] = len(slot_index)
            accumulator[identity] = slot_regs
            last_seen[slot_index[identity]] = now

        self._battery_accumulator = accumulator
        self._battery_slot_index = slot_index
        self._battery_last_seen = last_seen

        _LOGGER.debug(
            "[%s] RR raw page: %s (reg96=%d)",
            self._serial,
            " ".join(raw_page),
            battery_count,
        )

        # Empty-bank convergence streak (#282 review P1): the accumulator
        # never evicts, and since the reg96-zero gate guard it is consulted
        # on every read — so a bank whose batteries were PHYSICALLY removed
        # would be served from stale accumulation forever (pre-guard, the
        # gate skip was accidentally the only convergence path, wiping
        # transients along with real removals).  Retire the accumulator only
        # after N consecutive SUCCESSFUL reads that report reg 96 = 0 AND an
        # all-ghost page.  Failed reads never reach this code (the failure
        # path above returns first), so a #258-style misroute storm cannot
        # advance the streak, and any real slot or reg 96 > 0 resets it.
        if battery_count == 0 and not page_has_active_slot:
            streak = getattr(self, "_battery_empty_page_streak", 0) + 1
            self._battery_empty_page_streak = streak
            if streak >= _BATTERY_EMPTY_BANK_RETIRE_STREAK and accumulator:
                retired = len(accumulator)
                self._battery_accumulator = {}
                self._battery_slot_index = {}
                self._battery_last_seen = {}
                self._battery_stall_warned = set()
                self._battery_dup_serial_warned = set()
                _LOGGER.info(
                    "[%s] Battery bank converged to empty after %d consecutive "
                    "empty reads (reg 96 = 0, all slots ghost); retiring %d "
                    "accumulated batteries",
                    self._serial,
                    streak,
                    retired,
                )
                return None
        else:
            self._battery_empty_page_streak = 0

        if not accumulator:
            return None

        _LOGGER.debug(
            "[%s] Battery accumulator: %d batteries populated (slots %s, reg96=%d)",
            self._serial,
            len(accumulator),
            sorted(slot_index.values()),
            battery_count,
        )

        self._log_battery_rotation_stall(now)

        return self._merged_accumulator_registers()

    def _merged_accumulator_registers(self) -> dict[int, int] | None:
        """Merged register map of every accumulated battery at its virtual slot.

        Returns *None* when nothing has been accumulated yet.
        """
        accumulator: dict[str, dict[int, int]] = getattr(self, "_battery_accumulator", {})
        slot_index: dict[str, int] = getattr(self, "_battery_slot_index", {})
        if not accumulator:
            return None

        merged: dict[int, int] = {}
        for identity, regs in accumulator.items():
            virtual_base = BATTERY_BASE_ADDRESS + (slot_index[identity] * BATTERY_REGISTER_COUNT)
            for offset, value in regs.items():
                merged[virtual_base + offset] = value
        return merged

    def _log_battery_rotation_stall(self, now: datetime) -> None:
        """Per-battery latched WARNING when accumulation stops being surfaced (#258).

        The 2026-06-28 incident pinned the firmware's battery page for ~9 hours:
        every 120-register block read SUCCEEDED, so no warning ever fired while
        half the accumulated batteries silently served frozen data.  This
        watchdog warns once per battery per stall episode when it has not
        appeared in a physical slot for the effective threshold
        (``max(BATTERY_ROTATION_STALL_WARN_AFTER, pages x 15 min)``), and logs
        an INFO — re-arming that battery's latch — when it is surfaced again.

        Latching is per identity, not global: a permanent straggler (e.g. a
        physically removed battery, never evicted by design) must not hold a
        global latch armed and mask a later, unrelated battery's stall — that
        would silently reproduce the exact blind spot this watchdog closes.

        This only covers the SUCCESS path — block reads succeeding while the
        firmware pins the page.  Persistent block-read FAILURES never reach
        this method; they are surfaced by the per-cycle "Failed to read
        battery registers ... serving N accumulated batteries" warning in
        :meth:`_read_individual_battery_registers` instead.
        """
        slot_index: dict[str, int] = getattr(self, "_battery_slot_index", {})
        last_seen: dict[int, datetime] = getattr(self, "_battery_last_seen", {})

        # Threshold scales with the rotation cycle length (see the constants'
        # calibration note): more accumulated batteries means more pages to
        # cycle through before a battery legitimately reappears.
        pages = max(1, -(-len(slot_index) // BATTERY_MAX_COUNT))
        threshold = max(BATTERY_ROTATION_STALL_WARN_AFTER, pages * _BATTERY_STALL_PER_PAGE)

        stale: dict[str, str] = {}
        for identity, slot in sorted(slot_index.items(), key=lambda kv: kv[1]):
            seen = last_seen.get(slot)
            if seen is not None and now - seen > threshold:
                stale[identity] = f"{identity} ({int((now - seen).total_seconds() // 60)} min)"

        warned: set[str] = getattr(self, "_battery_stall_warned", set())
        newly_stale = [identity for identity in stale if identity not in warned]
        recovered = sorted(warned - stale.keys())

        if newly_stale:
            _LOGGER.warning(
                "[%s] Battery rotation stalled: %d of %d accumulated batteries "
                "not surfaced by the firmware for over %d minutes (%s); their "
                "local data is frozen at the last read (HYBRID keeps them fresh "
                "from the cloud; LOCAL has no fallback)",
                self._serial,
                len(stale),
                len(slot_index),
                int(threshold.total_seconds() // 60),
                ", ".join(stale.values()),
            )
        if recovered:
            _LOGGER.info(
                "[%s] Battery rotation resumed for %d of %d accumulated batteries (%s)",
                self._serial,
                len(recovered),
                len(slot_index),
                ", ".join(recovered),
            )

        self._battery_stall_warned = (warned | set(newly_stale)) - set(recovered)

    def _stamp_battery_last_seen(self, battery: BatteryBankData | None) -> None:
        """Stamp each battery's ``last_seen`` from the accumulator's per-slot clock.

        ``_battery_last_seen`` records, per virtual slot, when that slot's battery
        was last actually read.  A battery the firmware has rotated out keeps its
        OLD timestamp here — that staleness is exactly the signal the hybrid
        supplemental gate and the integration's freshness overlay rely on
        (eg4_web_monitor#258).  ``battery_index`` equals the virtual slot, so every
        accumulated battery has an entry; the ``now`` fallback is a defensive
        default for the unreachable case of a battery with no recorded read.
        """
        if battery is None or not battery.batteries:
            return

        last_seen: dict[int, datetime] = getattr(self, "_battery_last_seen", {})
        # tz-aware UTC: last_seen crosses into Home Assistant, which would
        # interpret a naive datetime as its own local zone (eg4_web_monitor#258).
        now = datetime.now(UTC)

        for b in battery.batteries:
            b.last_seen = last_seen.get(b.battery_index, now)

    def _log_battery_slot_debug(
        self,
        individual_registers: dict[int, int],
        battery_count: int,
    ) -> None:
        """Log per-slot status/voltage/serial for round-robin debugging (#165).

        Includes header registers 5000-5001 (if previously read) and offset 24
        per slot, which appears to encode the battery position index.

        When round-robin accumulation is active (battery_count > 4), the
        register map may contain virtual addresses beyond slot 3, so we
        iterate up to battery_count.
        """
        slots_to_log = battery_count

        # Log header registers 5000-5001 if available (read by
        # _read_battery_header_registers).  These are consistently zero on
        # 3-battery systems but may hold rotation metadata on larger arrays.
        header_regs: dict[int, int] | None = getattr(self, "_battery_header_registers", None)
        if header_regs is not None:
            _LOGGER.debug(
                "[%s] Battery header: reg5000=%d (0x%04X) reg5001=%d (0x%04X) battery_count=%d",
                self._serial,
                header_regs.get(5000, -1),
                header_regs.get(5000, 0),
                header_regs.get(5001, -1),
                header_regs.get(5001, 0),
                battery_count,
            )

        for slot_idx in range(slots_to_log):
            slot_base = BATTERY_BASE_ADDRESS + (slot_idx * BATTERY_REGISTER_COUNT)
            status = individual_registers.get(slot_base, 0)
            voltage_raw = individual_registers.get(slot_base + 6, 0)

            # Offset 24: encodes the battery position index in the high byte
            # (0x0100=pos1, 0x0200=pos2, etc.) and the FINAL serial character
            # in the low byte.  May change during round-robin rotation on
            # systems with >4 batteries.
            reserved_24 = individual_registers.get(slot_base + 24, 0)

            # Serial: decode with the SAME reader the accumulator identity and
            # BatteryData.serial_number use (offsets 17-24, non-printables
            # filtered).  The previous manual 17-23 decode dropped the final
            # character (offset 24 low byte), so a bank whose serials differ
            # only there logged phantom "duplicate" serials
            # (eg4_web_monitor#258 beta.18 red herring).
            slot_serial = read_battery_serial(individual_registers, base_address=slot_base)

            _LOGGER.debug(
                "[%s] Pos %d: status=0x%04X voltage_raw=%d serial=%r offset24=0x%04X (%d)",
                self._serial,
                slot_idx,
                status,
                voltage_raw,
                slot_serial or "(empty)",
                reserved_24,
                reserved_24,
            )

    async def _read_battery_header_registers(self) -> None:
        """Read registers 5000-5001 for round-robin rotation debugging (#165).

        These two registers sit before the per-battery blocks at 5002+.
        On systems tested with 3 batteries they are consistently zero.
        On larger arrays (>4 batteries) they may hold a rotation counter
        or other CAN bus metadata useful for diagnosing round-robin issues.

        Results are stored on ``self._battery_header_registers`` and logged
        by ``_log_battery_slot_debug()``.  Reading failures are non-fatal.
        """
        try:
            values = await self._read_input_registers(5000, 2)
            self._battery_header_registers: dict[int, int] = {
                5000: values[0],
                5001: values[1],
            }
        except Exception:
            _LOGGER.debug(
                "[%s] Failed to read battery header registers 5000-5001 (non-fatal)",
                self._serial,
            )
            self._battery_header_registers = {}

    # ------------------------------------------------------------------
    # Register group reading
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_input_groups(
        group_names: list[str] | None,
    ) -> list[tuple[str, tuple[int, int]]]:
        """Resolve group names to ``(name, (start, count))`` pairs."""
        if group_names is None:
            return list(INPUT_REGISTER_GROUPS.items())
        return [
            (name, INPUT_REGISTER_GROUPS[name])
            for name in group_names
            if name in INPUT_REGISTER_GROUPS
        ]

    def _plan_input_reads(
        self,
        groups: list[tuple[str, tuple[int, int]]],
    ) -> list[_ReadBlock]:
        """Plan the input reads for ``groups``, coalescing when configured.

        With the conservative default block size — or after a coalesced read
        has failed and latched the transport back (``eg4_web_monitor#254``),
        or during the post-mismatch cooldown (#320) — the plan is exactly one
        read per group, byte-identical to the pre-feature behavior.

        When a cooldown expires the transport re-probes coalescing and logs it
        once (the re-arm was previously silent), so operators can confirm the
        connection returned to large-read mode (#320).
        """
        max_size = getattr(self, "_max_input_block_size", DEFAULT_INPUT_BLOCK_SIZE)
        if max_size <= DEFAULT_INPUT_BLOCK_SIZE or getattr(
            self, "_input_coalescing_latched_off", False
        ):
            return self._plain_input_plan(groups)

        retry_after = getattr(self, "_input_coalescing_retry_after", 0.0)
        if retry_after:
            if time.monotonic() < retry_after:
                return self._plain_input_plan(groups)
            # Cooldown elapsed: clear it and re-probe.  Clearing means this
            # DEBUG line fires once at the re-arm, not every subsequent cycle.
            self._input_coalescing_retry_after = 0.0
            _LOGGER.debug(
                "[%s] coalescing cooldown expired — re-probing large input reads",
                self._serial,
            )
        return coalesce_register_groups(groups, max_size)

    @staticmethod
    def _plain_input_plan(
        groups: list[tuple[str, tuple[int, int]]],
    ) -> list[_ReadBlock]:
        """One read per group — the plain, never-coalesced plan.

        The coalesced-read fallback handlers use this directly so the retry is
        always plain, regardless of whether the failing block latched
        coalescing off.  A misrouted-frame fallback (#320) deliberately does
        *not* latch, so re-planning via :meth:`_plan_input_reads` could
        coalesce again and fail a second time — this bypasses that.
        """
        return [_ReadBlock((name,), start, count) for name, (start, count) in groups]

    def _latch_input_coalescing_off(self, block: _ReadBlock, reason: object) -> None:
        """Disable coalescing for this transport's lifetime (probe-once).

        Old dongle firmware caps reads at ~40 registers; a large read on
        such hardware fails (or times out) every time, so the first failure
        latches the transport back to the plain grouped reads permanently
        (until the transport is recreated, e.g. on reload) instead of
        re-paying retries every poll cycle.  A short (truncated) frame trips
        the same latch.  Misrouted frames do NOT reach here — they fall back
        for one cycle without latching (see :meth:`_read_block`, #320).  Nor
        does any failure once the transport has *proven* large-read support
        (:meth:`_degrade_coalescing`), so this permanent latch is reserved for
        a transport that has NEVER completed a coalesced read — the genuine
        old-firmware signal.
        """
        self._input_coalescing_latched_off = True
        _LOGGER.warning(
            "[%s] Coalesced input-register read %d-%d (%d registers; groups %s) "
            "failed (%s) — falling back to the standard grouped reads for this "
            "connection. Possible causes: older dongle firmware that only "
            "supports ~40-register reads, or a persistent link error (e.g. a "
            "truncated frame). Coalescing re-arms when the transport is "
            "recreated (e.g. on reload); lower the configured block size to "
            "disable this probe.",
            self._serial,
            block.start,
            block.start + block.count - 1,
            block.count,
            block.label,
            reason,
        )

    def _start_coalescing_cooldown(self, block: _ReadBlock, reason: object, note: str) -> None:
        """Fall back to plain reads for a cooldown window instead of latching.

        Used both for a misrouted/unsolicited frame (never a firmware signal)
        and for any failure once the transport has proven large-read support.
        Either way the failure is transient, so coalescing re-probes after
        :data:`COALESCING_MISMATCH_COOLDOWN` rather than latching permanently
        (#320).  ``note`` names the cause in the log.
        """
        self._input_coalescing_retry_after = time.monotonic() + COALESCING_MISMATCH_COOLDOWN
        _LOGGER.debug(
            "[%s] Coalesced input-register read %d-%d %s (%s) — falling back to "
            "grouped reads; coalescing re-probes in ~%d minutes (#320)",
            self._serial,
            block.start,
            block.start + block.count - 1,
            note,
            reason,
            int(COALESCING_MISMATCH_COOLDOWN // 60),
        )

    def _degrade_coalescing(self, block: _ReadBlock, reason: object) -> None:
        """Degrade coalescing after a genuine failure (exception or short read).

        Latch permanently only if this transport has NEVER completed a
        coalesced read — the true old-firmware probe.  Once a coalesced read
        has ever succeeded (:attr:`_input_coalescing_proven`) the firmware has
        proven it serves large reads, so a later failure can't mean the
        ~40-register cap; treat it as transient via the cooldown instead of a
        permanent latch (#320, reporter ivanfmartinez).
        """
        if getattr(self, "_input_coalescing_proven", False):
            self._start_coalescing_cooldown(
                block, reason, "failed but large-read support was already proven"
            )
        else:
            self._latch_input_coalescing_off(block, reason)

    def _note_coalescing_proven(self) -> None:
        """Record that a coalesced read succeeded; log once on first proof.

        The log fires only on the False->True transition, so it is one line
        per transport (at startup or after a cooldown re-probe) and doubles as
        the operator's confirmation that large-read mode is active (#320).
        """
        if not getattr(self, "_input_coalescing_proven", False):
            self._input_coalescing_proven = True
            _LOGGER.debug(
                "[%s] Coalesced input read succeeded — large-read support confirmed",
                self._serial,
            )

    async def _read_block(self, block: _ReadBlock) -> list[int]:
        """Read one planned block.

        A failed or short **coalesced** read latches coalescing off and
        raises :class:`_CoalescedReadFallback` so the caller re-reads the
        cycle with plain group reads.  Plain (single-group) reads propagate
        errors unchanged, preserving the existing per-group semantics.

        Two coalesced errors do **not** latch:

        * A :class:`TransportResponseMismatchError` — a misrouted or
          interleaved frame (the WiFi dongle proxies cloud traffic, so a
          response meant for the cloud server can land on a local reader; an
          unsolicited heartbeat counts too).  It says nothing about large-read
          support, so it starts a cooldown instead of latching.
        * ANY failure once the transport has proven large-read support (a
          coalesced read has completed at least once).  Proven capability
          rules out the old ~40-register cap, so a later exception/short read
          is transient and also uses the cooldown (:meth:`_degrade_coalescing`,
          #320 reporter ivanfmartinez — his dongle served coalesced reads for
          minutes, then one bad frame would have latched permanently).

        An unproven transport keeps the permanent latch on a genuine
        exception/short read — the true old-firmware probe.  During the
        cooldown reads stay plain, then coalescing re-probes once.  The
        per-read dongle transport already retries 3x, so an escaping mismatch
        is rare (no strike counter needed).
        """
        try:
            values = await self._read_input_registers(block.start, block.count)
        except TransportResponseMismatchError as err:
            if block.coalesced:
                self._start_coalescing_cooldown(block, err, "hit a misrouted response")
                raise _CoalescedReadFallback() from err
            raise
        except Exception as err:
            if block.coalesced:
                self._degrade_coalescing(block, err)
                raise _CoalescedReadFallback() from err
            raise
        if block.coalesced and len(values) < block.count:
            # A short-but-well-formed response (matching serial/function/start
            # register, valid CRC, just fewer registers) is the classic
            # signature of the old ~40-register firmware cap this probe exists
            # to detect — so on an UNPROVEN transport it latches, unlike a
            # misrouted frame.  A misrouted frame passing all three identity
            # checks *including* start register yet truncated is too narrow a
            # coincidence to design around (#320).  On a proven transport
            # _degrade_coalescing treats it as transient (cooldown) instead.
            self._degrade_coalescing(
                block, f"short response ({len(values)}/{block.count} registers)"
            )
            raise _CoalescedReadFallback()
        if block.coalesced:
            self._note_coalescing_proven()
        return values

    async def _read_register_groups(
        self,
        group_names: list[str] | None = None,
    ) -> dict[int, int]:
        """Read multiple register groups sequentially with inter-group delays.

        When a larger ``max_input_block_size`` is configured, adjacent groups
        are coalesced into fewer reads; the first failed coalesced read falls
        back to the plain per-group reads for the cycle and latches the
        transport back permanently (eg4_web_monitor#254).

        Subclasses (e.g. BaseModbusTransport) may override this to add
        auto-reconnect logic around it.

        Args:
            group_names: Specific group names from ``INPUT_REGISTER_GROUPS``.
                If *None*, reads all groups.

        Returns:
            Dict mapping register address to value.

        Raises:
            TransportReadError: If any group read fails.
        """
        groups = self._resolve_input_groups(group_names)
        try:
            return await self._read_group_plan(self._plan_input_reads(groups))
        except _CoalescedReadFallback:
            # A coalesced block fell back — either it latched coalescing off,
            # or it was a misrouted frame that intentionally did not (#320).
            # Re-read with an explicit plain plan so the retry is one
            # read/group regardless of whether the latch fired.
            return await self._read_group_plan(self._plain_input_plan(groups))

    async def _read_group_plan(self, plan: list[_ReadBlock]) -> dict[int, int]:
        """Execute a read plan sequentially with inter-read delays.

        The adaptive-delay backoff only applies to transports that track
        ``_last_read_retried`` (the pymodbus-based ones); the dongle
        transport has no such attribute and keeps its fixed delay.
        """
        registers: dict[int, int] = {}
        current_delay = self._inter_register_delay

        for i, block in enumerate(plan):
            try:
                values = await self._read_block(block)
            except _CoalescedReadFallback:
                raise
            except Exception as e:
                _LOGGER.error(
                    "Failed to read register group '%s': %s",
                    block.label,
                    e,
                )
                raise TransportReadError(
                    f"Failed to read register group '{block.label}': {e}"
                ) from e

            for offset, value in enumerate(values):
                registers[block.start + offset] = value

            # Increase delay when retries occurred to give the device breathing room
            if getattr(self, "_last_read_retried", False):
                current_delay = min(current_delay * 2, 1.0)
                _LOGGER.debug(
                    "Increasing inter-group delay to %.3fs after retries",
                    current_delay,
                )

            if i < len(plan) - 1:
                await asyncio.sleep(current_delay)

        return registers

    async def _read_pv4_6_registers(self) -> dict[int, int]:
        """Read the V23-extended PV4-6 input registers if applicable.

        Covers both the voltage/power group (217-222) and the daily/lifetime
        energy group (223-231).  Only models whose ``pv_string_count >= 4``
        expose these registers, so a 3-string model never issues these reads
        (no wasteful/failing transaction on residential hardware).  A read
        failure is non-fatal — pv4-6 simply stay unpopulated — to match the
        resilience of the other supplementary register groups.

        Returns:
            Dict mapping address to raw value (empty if not applicable or on
            read failure).
        """
        if self._pv_string_count < 4:
            return {}

        registers: dict[int, int] = {}
        for start, count in (
            PV4_6_INPUT_REGISTER_GROUP,
            PV4_6_ENERGY_INPUT_REGISTER_GROUP,
        ):
            await asyncio.sleep(self._inter_register_delay)
            try:
                values = await self._read_input_registers(start, count)
            except (TransportReadError, TransportTimeoutError) as e:
                _LOGGER.debug(
                    "PV4-6 registers (%d-%d) unavailable for %s, continuing: %s",
                    start,
                    start + count - 1,
                    self._serial,
                    e,
                )
                continue
            registers.update(self._registers_from_values(start, values))
        return registers

    async def read_quick_charge_remaining_seconds(self) -> int | None:
        """Read the quick-charge remaining-time countdown (INPUT register 210).

        Register 210 is a read-only input register exposing the remaining quick
        charge time in **seconds** (finer-grained than the minute-resolution
        holding register 234). It is only populated on newer firmware (≈v25+);
        older firmware reports 0. The read is non-fatal and out-of-band of the
        main input groups, mirroring :meth:`_read_pv4_6_registers`.

        Returns:
            The remaining seconds when the register reports a positive value,
            otherwise ``None`` (older firmware reporting 0, or a read failure) —
            so callers can fall back to the holding-register 234 derivation.
        """
        try:
            values = await self._read_input_registers(210, 1)
        except (TransportReadError, TransportTimeoutError) as e:
            _LOGGER.debug(
                "Quick charge remaining (input reg 210) unavailable for %s: %s",
                self._serial,
                e,
            )
            return None
        seconds = int(values[0]) if values else 0
        return seconds if seconds > 0 else None

    # ------------------------------------------------------------------
    # Device data methods
    # ------------------------------------------------------------------

    async def read_runtime(self) -> InverterRuntimeData:
        """Read runtime data via input registers.

        Returns:
            Runtime data with all values properly scaled.

        Raises:
            TransportReadError: If read operation fails.
        """
        input_registers = await self._read_register_groups()
        input_registers.update(await self._read_pv4_6_registers())
        family = self._inverter_family.value if self._inverter_family else "EG4_HYBRID"
        return InverterRuntimeData.from_modbus_registers(
            input_registers,
            family,
            split_phase=self._split_phase,
            pv_string_count=self._pv_string_count,
        )

    async def read_energy(self) -> InverterEnergyData:
        """Read energy statistics via input registers.

        Returns:
            Energy data with all values in kWh.

        Raises:
            TransportReadError: If read operation fails.
        """
        input_registers = await self._read_register_groups(
            ["power_energy", "status_energy", "output_power"]
        )

        # bms_data is supplementary — don't fail the entire energy read
        # if these registers time out
        try:
            bms_registers = await self._read_register_groups(["bms_data"])
            input_registers.update(bms_registers)
        except (TransportReadError, TransportTimeoutError):
            _LOGGER.debug(
                "bms_data registers unavailable for %s, continuing without them",
                self._serial,
            )

        # V23-extended PV4-6 energy registers (only read for models with >=4
        # strings); gated identically to the runtime path.
        input_registers.update(await self._read_pv4_6_registers())

        family = self._inverter_family.value if self._inverter_family else "EG4_HYBRID"
        return InverterEnergyData.from_modbus_registers(
            input_registers,
            family,
            pv_string_count=self._pv_string_count,
        )

    async def read_battery(
        self,
        include_individual: bool = True,
    ) -> BatteryBankData | None:
        """Read battery information via registers.

        Args:
            include_individual: If True, also reads extended registers (5000+)
                for individual battery module data.

        Returns:
            Battery bank data, or *None* if no battery detected.

        Raises:
            TransportReadError: If read operation fails.
        """
        all_registers: dict[int, int] = {}

        # Read core battery registers (power + BMS).
        # Registers 0-31 contain power/voltage/SOC; 80-112 contain BMS data.
        try:
            power_regs = await self._read_input_registers(0, 32)
            all_registers.update(self._registers_from_values(0, power_regs))
        except Exception as e:
            _LOGGER.warning("Failed to read power registers 0-31: %s", e)

        bms_ok = True
        try:
            bms_regs = await self._read_input_registers(80, 33)
            if len(bms_regs) < 33:
                # Short/partial BMS response that didn't raise — reg 96 / BMS
                # fields would be absent, rebuilding the half-empty bank (#261).
                _LOGGER.warning(
                    "Short BMS read (%d/33 regs) for %s; treating as unavailable",
                    len(bms_regs),
                    self._serial,
                )
                bms_ok = False
            else:
                all_registers.update(self._registers_from_values(80, bms_regs))
        except Exception as e:
            _LOGGER.warning("Failed to read BMS registers 80-112: %s", e)
            bms_ok = False

        # The bank's count + all BMS fields come from the 80-112 block.  If that
        # read failed, a valid power-group voltage alone would still build a
        # half-empty bank (battery_count=None) that overwrites the good cache and
        # flickers battery_bank_* sensors to unavailable (eg4_web_monitor#261).
        # Return None so the caller (_fetch_battery, guarded by
        # ``if transport_battery is not None``) keeps the last-good cache.
        if not bms_ok:
            _LOGGER.debug(
                "[%s] bms_data unavailable; preserving last-good battery cache",
                self._serial,
            )
            return None

        # Read individual battery registers (5000+) if requested
        battery_count = all_registers.get(96, 0)
        individual_registers: dict[int, int] | None = None

        _LOGGER.debug(
            "[%s] battery_count (reg 96) = %d, include_individual = %s%s",
            self._serial,
            battery_count,
            include_individual,
            self._shared_battery_note(battery_count),
        )

        # reg 96 is unreliable (#170/#258): a transient 0 on a battery-bearing
        # unit must not bypass the block read — the accumulator would never be
        # consulted (its failure fallback only covers RAISED reads, not a
        # gate skip), so the bank would be built with batteries=[] and every
        # accumulated battery would vanish for the cycle (eg4_web_monitor#282
        # review flag, same family as the #258 wipe).  Once anything has been
        # accumulated, read the block regardless of reg 96; a unit that never
        # accumulated anything (genuinely battery-less) still skips the read.
        if include_individual and (
            battery_count > 0 or getattr(self, "_battery_accumulator", None)
        ):
            await self._read_battery_header_registers()
            individual_registers = await self._read_individual_battery_registers(
                battery_count,
            )

        if individual_registers:
            self._log_battery_slot_debug(individual_registers, battery_count)

        result = BatteryBankData.from_modbus_registers(
            all_registers,
            individual_registers,
        )
        self._stamp_battery_last_seen(result)

        if result is None:
            _LOGGER.debug("Battery voltage below threshold, assuming no battery present")
        elif result.batteries:
            _LOGGER.debug(
                "[%s] Parsed %d connected batteries from %d slots (battery_count reg 96 = %d)",
                self._serial,
                len(result.batteries),
                min(battery_count, BATTERY_MAX_COUNT) if battery_count > 0 else 0,
                battery_count,
            )

        return result

    async def _read_all_input_groups(
        self,
        plan: list[_ReadBlock],
    ) -> tuple[dict[int, int], bool]:
        """Execute the combined-read plan, tracking bms_data availability.

        A plain ``bms_data`` read failing or coming back short is non-fatal
        (#261): its registers stay absent and ``bms_ok`` turns False so the
        caller suppresses the half-empty battery bank.  In a coalesced plan
        the bms registers ride inside a merged block, whose failure raises
        :class:`_CoalescedReadFallback` (via ``_read_block``) so the whole
        cycle re-runs with plain group reads — restoring exactly these
        per-group semantics.

        Returns:
            Tuple of (address→value map, bms_ok).
        """
        input_registers: dict[int, int] = {}
        bms_ok = True

        for i, block in enumerate(plan):
            is_plain_bms = block.members == ("bms_data",)
            try:
                values = await self._read_block(block)
                if is_plain_bms and len(values) < block.count:
                    # A short BMS response (e.g. a misrouted/partial dongle
                    # frame that didn't raise) would leave reg 96 / BMS fields
                    # absent and rebuild the half-empty bank.  Treat it as
                    # unavailable, like an outright failure (#261).
                    _LOGGER.debug(
                        "bms_data short read (%d/%d regs) for %s, treating as unavailable",
                        len(values),
                        block.count,
                        self._serial,
                    )
                    bms_ok = False
                    continue
                for offset, value in enumerate(values):
                    input_registers[block.start + offset] = value
            except _CoalescedReadFallback:
                raise
            except Exception:
                if is_plain_bms:
                    _LOGGER.debug(
                        "bms_data registers unavailable for %s, continuing",
                        self._serial,
                    )
                    bms_ok = False
                    continue
                raise

            if i < len(plan) - 1:
                await asyncio.sleep(self._inter_register_delay)

        return input_registers, bms_ok

    async def read_all_input_data(
        self,
    ) -> tuple[InverterRuntimeData, InverterEnergyData, BatteryBankData | None]:
        """Read all input register groups once, returning runtime + energy + battery.

        Reduces Modbus transactions by reading each register group exactly once
        and constructing all three data types from the shared snapshot.

        BMS data failure is non-fatal to match ``read_energy()`` resilience.

        Returns:
            Tuple of (runtime_data, energy_data, battery_data_or_none).
        """
        groups = self._resolve_input_groups(None)
        try:
            input_registers, bms_ok = await self._read_all_input_groups(
                self._plan_input_reads(groups)
            )
        except _CoalescedReadFallback:
            # A coalesced block fell back — either it latched coalescing off,
            # or it was a non-latching misrouted frame (#320).  Re-read with
            # an explicit plain plan (one read/group) so the retry never
            # coalesces again, restoring the exact per-group (bms non-fatal)
            # semantics regardless of whether the latch fired.
            input_registers, bms_ok = await self._read_all_input_groups(
                self._plain_input_plan(groups)
            )

        # V23-extended PV4-6 registers (only read for models with >=4 strings)
        input_registers.update(await self._read_pv4_6_registers())

        family = self._inverter_family.value if self._inverter_family else "EG4_HYBRID"

        # Construct all three data types from the shared snapshot
        runtime = InverterRuntimeData.from_modbus_registers(
            input_registers,
            family,
            split_phase=self._split_phase,
            pv_string_count=self._pv_string_count,
        )
        energy = InverterEnergyData.from_modbus_registers(
            input_registers,
            family,
            pv_string_count=self._pv_string_count,
        )

        # The battery bank lives entirely in the bms_data group (reg 96 +
        # voltage/SOC/current/cell/BMS-limit fields).  If that group's read
        # dropped — common on a flaky dongle link, where single requests time
        # out / get misrouted — the power group's voltage alone would still
        # yield a half-empty bank (battery_count=None, current/cell data all
        # None) that overwrites the good cache and flickers the battery_bank_*
        # sensors to unavailable (eg4_web_monitor#261).  Return None instead so
        # the caller (_fetch_combined_input_data, which guards
        # ``if battery is not None``) preserves the last-good battery cache;
        # runtime + energy still update.  A SUCCESSFUL bms_data read with a
        # genuine reg 96 = 0 is unaffected and still builds a bank.
        if not bms_ok:
            return runtime, energy, None

        # Read individual battery registers (5000+) if present
        battery_count = input_registers.get(96, 0)

        _LOGGER.debug(
            "[%s] combined path: battery_count (reg 96) = %d%s",
            self._serial,
            battery_count,
            self._shared_battery_note(battery_count),
        )

        individual_registers: dict[int, int] | None = None
        # reg 96 is unreliable (#170/#258): a transient 0 on a battery-bearing
        # unit must not bypass the block read — the accumulator would never be
        # consulted (its failure fallback only covers RAISED reads, not a
        # gate skip), so the bank would be built with batteries=[] and every
        # accumulated battery would vanish for the cycle (eg4_web_monitor#282
        # review flag, same family as the #258 wipe).  Once anything has been
        # accumulated, read the block regardless of reg 96; a unit that never
        # accumulated anything (genuinely battery-less) still skips the read.
        if battery_count > 0 or getattr(self, "_battery_accumulator", None):
            await self._read_battery_header_registers()
            individual_registers = await self._read_individual_battery_registers(
                battery_count,
            )

        if individual_registers:
            self._log_battery_slot_debug(individual_registers, battery_count)

        battery = BatteryBankData.from_modbus_registers(
            input_registers,
            individual_registers,
        )
        self._stamp_battery_last_seen(battery)

        return runtime, energy, battery

    async def read_midbox_runtime(self) -> MidboxRuntimeData:
        """Read runtime data from a MID/GridBOSS device.

        Returns:
            MidboxRuntimeData with all values properly scaled.

        Raises:
            TransportReadError: If read operation fails.
        """
        input_registers: dict[int, int] = {}

        try:
            for i, (start, count) in enumerate(MIDBOX_REGISTER_GROUPS):
                values = await self._read_input_registers(start, count)
                input_registers.update(self._registers_from_values(start, values))

                if i < len(MIDBOX_REGISTER_GROUPS) - 1:
                    await asyncio.sleep(self._inter_register_delay)

        except Exception as e:
            _LOGGER.error("Failed to read MID input registers: %s", e)
            raise TransportReadError(f"Failed to read MID registers: {e}") from e

        # Smart port mode is stored as a bit-packed value in holding register 20
        # (2 bits per port, LSB-first: bits 0-1 = port 1, bits 2-3 = port 2, etc.)
        # Values: 0 = off, 1 = smart_load, 2 = ac_couple
        # Delay before switching from input (FC 04) to holding (FC 03) registers —
        # WiFi dongles need time between function code changes to avoid corrupt reads.
        await asyncio.sleep(self._inter_register_delay)
        smart_port_mode_reg: int | None = None
        try:
            holding_vals = await self._read_holding_registers(20, 1)
            smart_port_mode_reg = holding_vals[0]
        except Exception:
            _LOGGER.debug("Failed to read smart port mode register 20")

        return MidboxRuntimeData.from_modbus_registers(
            input_registers, smart_port_mode_reg=smart_port_mode_reg
        )

    async def read_parameters(
        self,
        start_address: int,
        count: int,
    ) -> dict[int, int]:
        """Read configuration parameters via holding registers.

        Args:
            start_address: Starting register address.
            count: Number of registers to read (chunked at 40 per call).

        Returns:
            Dict mapping register address to raw integer value.

        Raises:
            TransportReadError: If read operation fails.
        """
        result: dict[int, int] = {}
        remaining = count
        current_address = start_address

        while remaining > 0:
            chunk_size = min(remaining, 40)
            values = await self._read_holding_registers(current_address, chunk_size)
            result.update(self._registers_from_values(current_address, values))
            current_address += chunk_size
            remaining -= chunk_size

        # Opportunistic stash for _shared_battery_note() — no extra read.
        if 110 in result:
            self._last_hold_110 = result[110]

        return result

    async def write_parameters(
        self,
        parameters: dict[int, int],
    ) -> bool:
        """Write configuration parameters via holding registers.

        Groups consecutive addresses into batch writes for efficiency.

        Args:
            parameters: Dict mapping register address to value.

        Returns:
            True if all writes succeeded.

        Raises:
            TransportWriteError: If any write fails.
        """
        sorted_params = sorted(parameters.items())

        # Group consecutive addresses for batch writing
        groups: list[tuple[int, list[int]]] = []
        current_start: int | None = None
        current_values: list[int] = []

        for address, value in sorted_params:
            if current_start is None:
                current_start = address
                current_values = [value]
            elif address == current_start + len(current_values):
                current_values.append(value)
            else:
                groups.append((current_start, current_values))
                current_start = address
                current_values = [value]

        if current_start is not None and current_values:
            groups.append((current_start, current_values))

        for start_address, values in groups:
            await self._write_holding_registers(start_address, values)

        # Keep the _shared_battery_note() stash coherent with our own writes
        # (e.g. a FUNC_BAT_SHARED bit flip via read-modify-write of reg 110).
        if 110 in parameters:
            self._last_hold_110 = parameters[110]

        return True

    # ------------------------------------------------------------------
    # Device info / discovery (delegates to _register_readers.py)
    # ------------------------------------------------------------------

    async def read_serial_number(self) -> str:
        """Read inverter serial number from input registers 115-119."""
        return await read_serial_number_async(self._read_input_registers, self._serial)

    async def read_firmware_version(self) -> str:
        """Read firmware version from holding registers 7-10."""
        return await read_firmware_version_async(self._read_holding_registers)

    async def read_device_type(self) -> int:
        """Read device type code from holding register 19."""
        return await read_device_type_async(self._read_holding_registers)

    def is_midbox_device(self, device_type_code: int) -> bool:
        """Check if device type code indicates a MID/GridBOSS device."""
        return is_midbox_device(device_type_code)

    async def read_parallel_config(self) -> int:
        """Read parallel configuration from input register 113."""
        return await read_parallel_config_async(self._read_input_registers, self._serial)

    async def validate_serial(self, expected_serial: str) -> bool:
        """Validate that the connected inverter matches the expected serial."""
        actual_serial = await self.read_serial_number()
        matches = actual_serial == expected_serial

        if not matches:
            _LOGGER.warning(
                "Serial mismatch: expected %s, got %s",
                expected_serial,
                actual_serial,
            )

        return matches
