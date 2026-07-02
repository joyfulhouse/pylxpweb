"""Configurable input-register block coalescing (eg4_web_monitor#254).

``max_input_block_size`` lets capable hardware read the adjacent
``INPUT_REGISTER_GROUPS`` in consolidated Modbus transactions (e.g. regs
0-112 in ONE read instead of four), cutting round-trips per poll.

Safety contract under test:

- **Default unchanged**: the default (40) issues EXACTLY the same reads as
  before the feature — byte-identical request sequence.
- **No gap bridging**: coalescing only merges groups whose spans are
  contiguous or overlapping.  A merged block never reads a register address
  that the plain grouped reads don't already read (the 154-169 and 174-192
  gaps stay unread).
- **Graceful degradation**: the FIRST failed/short coalesced read latches the
  transport back to plain grouped reads permanently (one WARNING), and the
  same cycle completes via the grouped fallback — an old dongle that cannot
  serve large reads must degrade, not hard-fail polling.
- **Validation**: only 40..125 accepted (125 = Modbus FC04 PDU cap).
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from pylxpweb.transports._register_data import (
    DEFAULT_INPUT_BLOCK_SIZE,
    INPUT_REGISTER_GROUPS,
    MAX_INPUT_BLOCK_SIZE,
    coalesce_register_groups,
)
from pylxpweb.transports.config import TransportConfig, TransportType
from pylxpweb.transports.dongle import DongleTransport
from pylxpweb.transports.exceptions import TransportReadError
from pylxpweb.transports.modbus import ModbusTransport
from pylxpweb.transports.modbus_serial import ModbusSerialTransport

_VOLTAGE_RAW = 534  # reg 4, DIV_10 -> 53.4 V (above the no-battery gate)
_SOC_SOH_PACKED = (100 << 8) | 82  # reg 5: SOC=82, SOH=100

# The reads issued today (and forever, by default) for read_all_input_data:
# the 8 register groups.  Battery/PV4-6/reg-210 reads are out of scope.
_GROUPED_READS = [(start, count) for start, count in INPUT_REGISTER_GROUPS.values()]

# Expected plan for the current group table at max_input_block_size=120:
# groups 0-31|32-63|64-79|80-112 are contiguous -> one 113-register read;
# eps_split_phase (140-142) is a subset of extended_data (113-153) -> merged
# (same span extended_data already reads today); the 154-169 / 174-192 gaps
# are never bridged, so output_power and split_phase_grid stay separate.
_COALESCED_READS_120 = [(0, 113), (113, 41), (170, 4), (193, 12)]


def _make_fake_read(fail_starts: set[int] = frozenset(), short_starts: set[int] = frozenset()):
    """Fake ``_read_input_registers`` recording each (start, count) request.

    ``fail_starts`` raise; ``short_starts`` return a truncated list without
    raising.  Register 4/5 carry a valid battery voltage + SOC whenever the
    read covers them, so battery parsing exercises the real paths.
    """
    calls: list[tuple[int, int]] = []

    async def fake_read(start: int, count: int) -> list[int]:
        calls.append((start, count))
        if start in fail_starts:
            raise OSError("simulated dropped Modbus request")
        n = 5 if start in short_starts else count
        vals = [0] * n
        for reg, value in ((4, _VOLTAGE_RAW), (5, _SOC_SOH_PACKED)):
            if start <= reg < start + n:
                vals[reg - start] = value
        return vals

    fake_read.calls = calls  # type: ignore[attr-defined]
    return fake_read


def _transport(**kwargs) -> ModbusTransport:
    t = ModbusTransport(host="192.168.1.100", serial="CE12345678", **kwargs)
    t.pv_string_count = 3  # skip the pv4-6 extended read
    t._inter_register_delay = 0.0  # keep tests fast
    return t


# ---------------------------------------------------------------------------
# coalesce_register_groups (pure planning function)
# ---------------------------------------------------------------------------


class TestCoalescePlanning:
    def test_current_table_at_120(self) -> None:
        """The live group table consolidates 8 reads into 4 at 120."""
        plan = coalesce_register_groups(list(INPUT_REGISTER_GROUPS.items()), 120)
        assert [(b.start, b.count) for b in plan] == _COALESCED_READS_120
        assert plan[0].members == (
            "power_energy",
            "status_energy",
            "temperatures",
            "bms_data",
        )
        assert plan[1].members == ("extended_data", "eps_split_phase")
        assert plan[2].members == ("output_power",)
        assert plan[3].members == ("split_phase_grid",)

    def test_current_table_at_125_same_as_120(self) -> None:
        """The FC04 PDU cap (125) doesn't admit any further merge."""
        plan = coalesce_register_groups(list(INPUT_REGISTER_GROUPS.items()), 125)
        assert [(b.start, b.count) for b in plan] == _COALESCED_READS_120

    def test_current_table_at_40_is_identity(self) -> None:
        """At the conservative default no merge fits -> plain group reads."""
        plan = coalesce_register_groups(list(INPUT_REGISTER_GROUPS.items()), 40)
        assert [(b.start, b.count) for b in plan] == _GROUPED_READS
        assert all(len(b.members) == 1 for b in plan)

    def test_never_bridges_gaps(self) -> None:
        """Groups separated by unread registers stay separate reads.

        (10,10) ends at 20 and (30,10) starts at 30: registers 20-29 are not
        read by any group, so even though the combined span (30) fits in the
        block size, they must NOT be merged into one read.
        """
        plan = coalesce_register_groups([("a", (10, 10)), ("b", (30, 10))], 120)
        assert [(b.start, b.count) for b in plan] == [(10, 10), (30, 10)]

    def test_merges_contiguous_and_contained(self) -> None:
        """Contiguous groups merge; a fully-contained group folds in."""
        plan = coalesce_register_groups([("a", (0, 10)), ("b", (10, 10)), ("c", (5, 3))], 120)
        assert [(b.start, b.count) for b in plan] == [(0, 20)]
        assert plan[0].members == ("a", "c", "b")

    def test_oversized_single_group_is_never_split(self) -> None:
        """A group larger than the limit stays one read (never split)."""
        plan = coalesce_register_groups([("big", (0, 60))], 40)
        assert [(b.start, b.count) for b in plan] == [(0, 60)]

    def test_merge_stops_at_size_limit(self) -> None:
        """A merge that would exceed the limit starts a new block."""
        plan = coalesce_register_groups([("a", (0, 30)), ("b", (30, 30)), ("c", (60, 30))], 60)
        assert [(b.start, b.count) for b in plan] == [(0, 60), (60, 30)]


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


class TestBlockSizeValidation:
    def test_defaults(self) -> None:
        assert DEFAULT_INPUT_BLOCK_SIZE == 40
        assert MAX_INPUT_BLOCK_SIZE == 125
        t = ModbusTransport(host="h", serial="CE12345678")
        assert t._max_input_block_size == DEFAULT_INPUT_BLOCK_SIZE

    @pytest.mark.parametrize("value", [40, 80, 120, 125])
    def test_accepts_sane_values(self, value: int) -> None:
        t = ModbusTransport(host="h", serial="CE12345678", max_input_block_size=value)
        assert t._max_input_block_size == value

    @pytest.mark.parametrize("value", [0, 39, 126, 1000, -1])
    def test_rejects_out_of_range_modbus(self, value: int) -> None:
        with pytest.raises(ValueError, match="max_input_block_size"):
            ModbusTransport(host="h", serial="CE12345678", max_input_block_size=value)

    @pytest.mark.parametrize("value", [39, 126])
    def test_rejects_out_of_range_dongle(self, value: int) -> None:
        with pytest.raises(ValueError, match="max_input_block_size"):
            DongleTransport(
                host="h",
                dongle_serial="BA12345678",
                inverter_serial="CE12345678",
                max_input_block_size=value,
            )

    def test_dongle_accepts_120(self) -> None:
        t = DongleTransport(
            host="h",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
            max_input_block_size=120,
        )
        assert t._max_input_block_size == 120

    def test_serial_transport_accepts_120(self) -> None:
        t = ModbusSerialTransport(
            port="/dev/ttyUSB0", serial="CE12345678", max_input_block_size=120
        )
        assert t._max_input_block_size == 120


# ---------------------------------------------------------------------------
# Default behavior is byte-identical to before the feature
# ---------------------------------------------------------------------------


class TestDefaultUnchanged:
    @pytest.mark.asyncio
    async def test_combined_read_issues_grouped_reads(self) -> None:
        transport = _transport()
        fake = _make_fake_read()
        with patch.object(transport, "_read_input_registers", side_effect=fake):
            runtime, energy, battery = await transport.read_all_input_data()

        assert fake.calls == _GROUPED_READS
        assert runtime is not None
        assert energy is not None
        assert battery is not None

    @pytest.mark.asyncio
    async def test_read_runtime_issues_grouped_reads(self) -> None:
        transport = _transport()
        fake = _make_fake_read()
        with patch.object(transport, "_read_input_registers", side_effect=fake):
            await transport.read_runtime()

        assert fake.calls == _GROUPED_READS


# ---------------------------------------------------------------------------
# Opt-in coalesced reads
# ---------------------------------------------------------------------------


class TestCoalescedReads:
    @pytest.mark.asyncio
    async def test_combined_read_coalesces_at_120(self) -> None:
        transport = _transport(max_input_block_size=120)
        fake = _make_fake_read()
        with patch.object(transport, "_read_input_registers", side_effect=fake):
            runtime, energy, battery = await transport.read_all_input_data()

        assert fake.calls == _COALESCED_READS_120
        assert runtime is not None
        assert energy is not None
        # bms_data (reg 96 et al) rode along in the 0-112 block
        assert battery is not None
        assert battery.soc == 82

    @pytest.mark.asyncio
    async def test_read_runtime_coalesces_at_120(self) -> None:
        transport = _transport(max_input_block_size=120)
        fake = _make_fake_read()
        with patch.object(transport, "_read_input_registers", side_effect=fake):
            await transport.read_runtime()

        assert fake.calls == _COALESCED_READS_120

    @pytest.mark.asyncio
    async def test_read_energy_coalesces_main_groups(self) -> None:
        """read_energy's power+status subset merges; bms stays its own read."""
        transport = _transport(max_input_block_size=120)
        fake = _make_fake_read()
        with patch.object(transport, "_read_input_registers", side_effect=fake):
            await transport.read_energy()

        assert fake.calls == [(0, 64), (170, 4), (80, 33)]

    @pytest.mark.asyncio
    async def test_coalesced_data_equivalent_to_grouped(self) -> None:
        """Runtime parsed from coalesced reads == parsed from grouped reads."""
        fake_a = _make_fake_read()
        grouped = _transport()
        with patch.object(grouped, "_read_input_registers", side_effect=fake_a):
            runtime_grouped, energy_grouped, battery_grouped = await grouped.read_all_input_data()

        fake_b = _make_fake_read()
        coalesced = _transport(max_input_block_size=120)
        with patch.object(coalesced, "_read_input_registers", side_effect=fake_b):
            (
                runtime_coalesced,
                energy_coalesced,
                battery_coalesced,
            ) = await coalesced.read_all_input_data()

        assert runtime_coalesced.battery_voltage == runtime_grouped.battery_voltage
        assert runtime_coalesced.battery_soc == runtime_grouped.battery_soc
        assert energy_coalesced.pv_energy_today == energy_grouped.pv_energy_today
        assert battery_grouped is not None and battery_coalesced is not None
        assert battery_coalesced.soc == battery_grouped.soc


# ---------------------------------------------------------------------------
# Failure fallback latch
# ---------------------------------------------------------------------------


class TestFallbackLatch:
    @pytest.mark.asyncio
    async def test_failed_coalesced_read_falls_back_same_cycle(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """First coalesced failure -> WARNING + grouped completion + latch."""
        transport = _transport(max_input_block_size=120)
        # The coalesced 0-112 read fails; the plain group reads (0,32 etc.)
        # succeed — only start=0 with count=113 must fail.
        calls: list[tuple[int, int]] = []

        async def fake_read(start: int, count: int) -> list[int]:
            calls.append((start, count))
            if (start, count) == (0, 113):
                raise OSError("large read not supported by this dongle")
            vals = [0] * count
            for reg, value in ((4, _VOLTAGE_RAW), (5, _SOC_SOH_PACKED)):
                if start <= reg < start + count:
                    vals[reg - start] = value
            return vals

        with (
            caplog.at_level(logging.WARNING, logger="pylxpweb.transports._register_data"),
            patch.object(transport, "_read_input_registers", side_effect=fake_read),
        ):
            runtime, energy, battery = await transport.read_all_input_data()

        # Same cycle completed via the conservative grouped reads
        assert calls == [(0, 113), *_GROUPED_READS]
        assert runtime is not None
        assert energy is not None
        assert battery is not None
        # Latched off permanently for this transport
        assert transport._input_coalescing_latched_off is True
        assert any("falling back" in rec.message.lower() for rec in caplog.records), caplog.records

    @pytest.mark.asyncio
    async def test_latched_transport_stays_grouped_next_cycle(self) -> None:
        transport = _transport(max_input_block_size=120)
        transport._input_coalescing_latched_off = True
        fake = _make_fake_read()
        with patch.object(transport, "_read_input_registers", side_effect=fake):
            await transport.read_all_input_data()

        assert fake.calls == _GROUPED_READS

    @pytest.mark.asyncio
    async def test_short_coalesced_read_latches_and_falls_back(self) -> None:
        """A truncated (non-raising) coalesced frame also degrades safely."""
        transport = _transport(max_input_block_size=120)
        calls: list[tuple[int, int]] = []

        async def fake_read(start: int, count: int) -> list[int]:
            calls.append((start, count))
            # Truncate ONLY the coalesced 113-register read; the plain
            # 32-register read of the same start must succeed.
            if (start, count) == (0, 113):
                return [0] * 5
            vals = [0] * count
            for reg, value in ((4, _VOLTAGE_RAW), (5, _SOC_SOH_PACKED)):
                if start <= reg < start + count:
                    vals[reg - start] = value
            return vals

        with patch.object(transport, "_read_input_registers", side_effect=fake_read):
            runtime, _energy, battery = await transport.read_all_input_data()

        assert transport._input_coalescing_latched_off is True
        assert calls == [(0, 113), *_GROUPED_READS]
        assert runtime is not None
        assert battery is not None

    @pytest.mark.asyncio
    async def test_single_group_failure_in_coalesced_plan_raises(self) -> None:
        """An unmerged block failing behaves exactly like today (no latch)."""
        transport = _transport(max_input_block_size=120)
        # split_phase_grid (193,12) is never merged; its failure must raise
        # TransportReadError as before, without latching coalescing off.
        fake = _make_fake_read(fail_starts={193})
        with (
            patch.object(transport, "_read_input_registers", side_effect=fake),
            pytest.raises(TransportReadError),
        ):
            await transport.read_runtime()

        assert transport._input_coalescing_latched_off is False

    @pytest.mark.asyncio
    async def test_bms_semantics_preserved_in_fallback(self) -> None:
        """Coalesced fail -> grouped fallback -> bms-only drop is non-fatal."""
        transport = _transport(max_input_block_size=120)

        async def fake_read(start: int, count: int) -> list[int]:
            if (start, count) == (0, 113):
                raise OSError("large read not supported")
            if start == 80:  # bms_data group drops in the fallback too
                raise OSError("bms flaky")
            vals = [0] * count
            for reg, value in ((4, _VOLTAGE_RAW), (5, _SOC_SOH_PACKED)):
                if start <= reg < start + count:
                    vals[reg - start] = value
            return vals

        with patch.object(transport, "_read_input_registers", side_effect=fake_read):
            runtime, _energy, battery = await transport.read_all_input_data()

        assert runtime is not None
        assert battery is None  # degraded bank suppressed, cache preserved


# ---------------------------------------------------------------------------
# TransportConfig plumbing (hybrid attach path)
# ---------------------------------------------------------------------------


class TestTransportConfigField:
    def test_round_trip(self) -> None:
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
            max_input_block_size=120,
        )
        data = config.to_dict()
        assert data["max_input_block_size"] == 120
        restored = TransportConfig.from_dict(data)
        assert restored.max_input_block_size == 120

    def test_from_dict_default_when_absent(self) -> None:
        """Configs stored by older versions restore to the conservative default."""
        restored = TransportConfig.from_dict(
            {
                "host": "192.168.1.100",
                "port": 502,
                "serial": "CE12345678",
                "transport_type": "modbus_tcp",
            }
        )
        assert restored.max_input_block_size == DEFAULT_INPUT_BLOCK_SIZE

    def test_validate_rejects_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="max_input_block_size"):
            TransportConfig(
                host="192.168.1.100",
                port=502,
                serial="CE12345678",
                transport_type=TransportType.MODBUS_TCP,
                max_input_block_size=200,
            )


# ---------------------------------------------------------------------------
# Factory plumbing
# ---------------------------------------------------------------------------


class TestFactoryPlumbing:
    def test_create_transport_modbus_forwards(self) -> None:
        from pylxpweb.transports import create_transport

        t = create_transport("modbus", host="h", serial="CE12345678", max_input_block_size=120)
        assert t._max_input_block_size == 120

    def test_create_transport_dongle_forwards(self) -> None:
        from pylxpweb.transports import create_transport

        t = create_transport(
            "dongle",
            host="h",
            dongle_serial="BA12345678",
            inverter_serial="CE12345678",
            max_input_block_size=120,
        )
        assert t._max_input_block_size == 120

    def test_create_transport_default_conservative(self) -> None:
        from pylxpweb.transports import create_transport

        t = create_transport("modbus", host="h", serial="CE12345678")
        assert t._max_input_block_size == DEFAULT_INPUT_BLOCK_SIZE


# ---------------------------------------------------------------------------
# Station local-discovery plumbing (the third construction path)
# ---------------------------------------------------------------------------


class TestLocalDiscoveryPlumbing:
    """`Station.from_local_discovery` must propagate the block size.

    Regression: `Station._create_transport_from_config()` (used by
    `from_local_discovery` -> `_discover_devices_from_configs`) omitted
    `max_input_block_size` at both its call sites, so a
    `TransportConfig(..., max_input_block_size=120)` silently got the
    default 40 and coalescing never activated on that public path — while
    `attach_local_transports()` and the factory paths propagated correctly.
    """

    def _modbus_config(self) -> TransportConfig:
        return TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
            max_input_block_size=120,
        )

    def _dongle_config(self) -> TransportConfig:
        return TransportConfig(
            host="192.168.1.101",
            port=8000,
            serial="CE87654321",
            transport_type=TransportType.WIFI_DONGLE,
            dongle_serial="BA12345678",
            max_input_block_size=120,
        )

    def test_create_transport_from_config_modbus_propagates(self) -> None:
        from pylxpweb.devices.station import Station

        transport = Station._create_transport_from_config(self._modbus_config())
        assert transport is not None
        assert transport._max_input_block_size == 120

    def test_create_transport_from_config_dongle_propagates(self) -> None:
        from pylxpweb.devices.station import Station

        transport = Station._create_transport_from_config(self._dongle_config())
        assert transport is not None
        assert transport._max_input_block_size == 120

    def test_create_transport_from_config_default_conservative(self) -> None:
        from pylxpweb.devices.station import Station

        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
        )
        transport = Station._create_transport_from_config(config)
        assert transport is not None
        assert transport._max_input_block_size == DEFAULT_INPUT_BLOCK_SIZE

    @pytest.mark.asyncio
    async def test_discovery_pipeline_propagates_for_both_types(self) -> None:
        """The from_local_discovery pipeline carries the size end-to-end."""
        from unittest.mock import AsyncMock, MagicMock

        from pylxpweb.devices.station import Station

        with (
            patch.object(ModbusTransport, "connect", new=AsyncMock()),
            patch.object(DongleTransport, "connect", new=AsyncMock()),
            patch(
                "pylxpweb.transports.discover_device_info",
                new=AsyncMock(side_effect=lambda t: MagicMock(serial=t._serial)),
            ),
        ):
            discovered, failed = await Station._discover_devices_from_configs(
                [self._modbus_config(), self._dongle_config()]
            )

        assert failed == []
        assert len(discovered) == 2
        for transport, _info in discovered:
            assert transport._max_input_block_size == 120


# ---------------------------------------------------------------------------
# Merge-boundary sentinels (guard against off-by-one in the offset math)
# ---------------------------------------------------------------------------

# Distinct raw values planted at the registers that sit on every coalesced
# merge boundary: 112|113 (mega-block end / extended_data start), 153
# (extended_data end), 170|173 (output_power start/end), 193|204
# (split_phase_grid start/end).  Expected parsed values are pinned against
# the GROUPED (pre-feature) parser, which is ground truth by definition.
_BOUNDARY_SENTINELS = {
    112: 250,  # temperature_t5, DIV_10 -> 25.0
    113: (7 << 8) | 0b0101,  # packed parallel config -> parallel_number 7
    153: 1530,  # ac_couple_power -> 1530.0 W
    170: 1700,  # output_power -> 1700.0 W
    173: 2,  # load_energy_total high word (regs 172-173) -> 13107.2 kWh
    193: 1201,  # grid_l1_voltage, DIV_10 -> 120.1 V
    204: 2040,  # grid_import_power_l2 -> 2040 W
}


def _make_sentinel_read():
    """Fake reader serving a register image with the boundary sentinels."""

    async def fake_read(start: int, count: int) -> list[int]:
        return [_BOUNDARY_SENTINELS.get(start + offset, 0) for offset in range(count)]

    return fake_read


class TestBoundarySentinels:
    """Each boundary register lands in its exact field in BOTH modes.

    The equivalence tests elsewhere plant values only around regs 4-5, so an
    off-by-one at a merge boundary (e.g. block (0,113) mapping register 113's
    value onto 112) could slip through while SOC still matched.  These
    sentinels bracket every merge seam; any regression in the offset math
    shifts at least one of them into the wrong field.
    """

    def _parse(self, transport: ModbusTransport):
        return transport.read_all_input_data()

    @pytest.mark.parametrize("block_size", [40, 120])
    @pytest.mark.asyncio
    async def test_sentinels_land_in_correct_fields(self, block_size: int) -> None:
        transport = _transport(max_input_block_size=block_size)
        with patch.object(transport, "_read_input_registers", side_effect=_make_sentinel_read()):
            runtime, energy, _battery = await transport.read_all_input_data()

        assert runtime.temperature_t5 == 25.0  # reg 112
        assert runtime.parallel_number == 7  # reg 113 (bits 8-15)
        assert runtime.ac_couple_power == 1530.0  # reg 153
        assert runtime.output_power == 1700.0  # reg 170
        assert energy.load_energy_total == 13107.2  # regs 172-173 high word
        assert runtime.grid_l1_voltage == 120.1  # reg 193
        assert runtime.grid_import_power_l2 == 2040  # reg 204

    @pytest.mark.asyncio
    async def test_modes_parse_identically(self) -> None:
        """Full-dataclass equivalence between grouped and coalesced modes."""
        import dataclasses

        results = {}
        for block_size in (40, 120):
            transport = _transport(max_input_block_size=block_size)
            with patch.object(
                transport, "_read_input_registers", side_effect=_make_sentinel_read()
            ):
                runtime, energy, battery = await transport.read_all_input_data()
            rt = dataclasses.asdict(runtime)
            en = dataclasses.asdict(energy)
            rt.pop("timestamp", None)
            en.pop("timestamp", None)
            results[block_size] = (rt, en, battery)

        assert results[40][0] == results[120][0]  # runtime
        assert results[40][1] == results[120][1]  # energy
        assert results[40][2] == results[120][2]  # battery (None == None)
