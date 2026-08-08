"""Input registers 123-126 are not measurements on EG4_OFFGRID (eg4_web_monitor#544).

Proven by decoding the reporting device's own firmware (12000XP, ``ceaa-0709``):

  * Reg 123 — the Modbus FC04 handler returns a word of the ARM comms
    processor's own RAM that a timer task increments once per second with no
    bound check, so it wraps at 65536.  It is seconds-since-boot, not watts; a
    whole-image writer audit found no DSP measurement path to it.  The reporting
    user saw 28,646 W with nothing connected to the GEN port, and their two
    samples fit the wrap with zero free parameters
    (``(5610 - 28646) mod 65536 = 42500 s``, within 33 s of the real interval).
  * Regs 124/125/126 — ARM-local status words, not accumulators.

On EG4_HYBRID reg 123 IS measurement-derived, but from the MULTIPLEXED GEN
terminal, so it carries AC-coupled PV too and is still not generator-specific.
Hence: ``generator_power`` is None only on EG4_OFFGRID, while
``is_using_generator`` stops using that register on BOTH families.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pylxpweb.devices.inverters._features import InverterFamily, InverterFeatures
from pylxpweb.devices.inverters.generic import GenericInverter
from pylxpweb.models import InverterRuntime
from pylxpweb.registers.inverter_input import sensor_keys_for_model
from pylxpweb.transports.data import InverterEnergyData, InverterRuntimeData


def _inverter(family: InverterFamily) -> GenericInverter:
    """Inverter with a transport runtime and a positively-resolved family."""
    inverter = GenericInverter(client=MagicMock(), serial_number="1234567890", model="12000XP")
    inverter._transport_runtime = InverterRuntimeData()
    inverter._features = InverterFeatures(model_family=family)
    return inverter


class TestRegisterMapFamilyScoping:
    """The decode layer — the surface downstream consumers actually read.

    Gating only the ``generator_power`` property would have left
    ``InverterRuntimeData``/``InverterEnergyData`` publishing the raw counter
    and status bitfields, which is what the Home Assistant integration reads on
    its LOCAL and HYBRID paths — i.e. exactly the modes #544 was reported on.
    """

    def test_offgrid_runtime_decode_drops_the_counter(self) -> None:
        """Reg 123 must not reach InverterRuntimeData on EG4_OFFGRID."""
        data = InverterRuntimeData.from_modbus_registers(
            {121: 0, 122: 0, 123: 28646}, "EG4_OFFGRID"
        )
        assert data.generator_power is None
        # ...while the genuine GEN-terminal measurements still decode.
        assert data.generator_voltage == 0
        assert data.generator_frequency == 0

    @pytest.mark.parametrize("family", ["EG4_HYBRID", "LXP"])
    def test_other_families_still_decode_reg123(self, family: str) -> None:
        data = InverterRuntimeData.from_modbus_registers({123: 2645}, family)
        assert data.generator_power == 2645

    def test_offgrid_energy_decode_drops_the_status_words(self) -> None:
        """Regs 124/125/126 must not reach InverterEnergyData on EG4_OFFGRID.

        These are the worse harm of the two: they would land in Home
        Assistant's long-term statistics as kWh totals.
        """
        data = InverterEnergyData.from_modbus_registers(
            {124: 1792, 125: 44225, 126: 20}, "EG4_OFFGRID"
        )
        assert data.generator_energy_today is None
        assert data.generator_energy_total is None

    def test_offgrid_sensor_keys_exclude_the_phantom_keys(self) -> None:
        keys = sensor_keys_for_model("EG4_OFFGRID")
        assert "generator_power" not in keys
        # The real measurements keep their keys.
        assert "generator_voltage" in keys
        assert "generator_frequency" in keys
        assert "generator_power" in sensor_keys_for_model("EG4_HYBRID")


class TestGeneratorPowerFamilyGate:
    """Reg 123 is suppressed only where it is proven not to be a measurement."""

    def test_offgrid_returns_none_despite_a_live_register(self) -> None:
        """The exact #544 reading is withheld rather than reported as watts."""
        inverter = _inverter(InverterFamily.EG4_OFFGRID)
        inverter._transport_runtime.generator_power = 28646.0
        assert inverter.generator_power is None

    @pytest.mark.parametrize(
        "family",
        [InverterFamily.EG4_HYBRID, InverterFamily.LXP, InverterFamily.UNKNOWN],
    )
    def test_other_families_pass_the_register_through(self, family: InverterFamily) -> None:
        """Hybrid/LXP keep the value; an UNRESOLVED family keeps it too.

        The gate is deliberately narrow: only positively-identified EG4_OFFGRID
        is suppressed, so a transient feature-detection failure cannot silently
        blank a genuine hybrid measurement.
        """
        inverter = _inverter(family)
        inverter._transport_runtime.generator_power = 2645.0
        assert inverter.generator_power == 2645


class TestAcCouplePowerFallbackGate:
    """The reg-123 fallback must never fire on EG4_OFFGRID."""

    def test_offgrid_partial_read_does_not_republish_the_counter(self) -> None:
        """Reg 153 missing + reg 123 present must NOT surface as AC couple power.

        This is the residual path #544 left behind: regs 121/122/153 and 123 sit
        in different read blocks, so a partial local read can lose 153 while
        keeping 123.  Falling back would report ~28 kW of "AC Couple Power" on
        the exact hardware the counter lives on.
        """
        inverter = _inverter(InverterFamily.EG4_OFFGRID)
        inverter._transport_runtime.ac_couple_power = None
        inverter._transport_runtime.generator_power = 28646.0
        assert inverter.ac_couple_power == 0

    def test_offgrid_still_uses_reg153_when_present(self) -> None:
        """Reg 153 is confirmed on this family (#196: I153=1409 W) — keep it."""
        inverter = _inverter(InverterFamily.EG4_OFFGRID)
        inverter._transport_runtime.ac_couple_power = 1409.0
        inverter._transport_runtime.generator_power = 28646.0
        assert inverter.ac_couple_power == 1409

    def test_hybrid_fallback_is_preserved(self) -> None:
        """Non-off-grid behaviour is unchanged — the fallback still applies."""
        inverter = _inverter(InverterFamily.EG4_HYBRID)
        inverter._transport_runtime.ac_couple_power = None
        inverter._transport_runtime.generator_power = 750.0
        assert inverter.ac_couple_power == 750


class TestIsUsingGenerator:
    """Derived from GEN terminal V/Hz, never from reg 123."""

    def test_offgrid_counter_no_longer_latches_true(self) -> None:
        """The #544 symptom: a huge reg 123 with a dead GEN port.

        The previous implementation returned True here (28646 > 0) and stayed
        True until the 16-bit wrap.
        """
        inverter = _inverter(InverterFamily.EG4_OFFGRID)
        inverter._transport_runtime.generator_power = 28646.0
        inverter._transport_runtime.generator_voltage = 0.0
        inverter._transport_runtime.generator_frequency = 0.0
        assert inverter.is_using_generator is False

    def test_hybrid_ac_coupled_pv_is_not_a_generator(self) -> None:
        """Real hardware case: 3 kW of AC-coupled PV crossing the GEN terminal.

        Measured on a FlexBOSS21 in a GridBOSS parallel system with no generator
        anywhere on site — reg 123 read ~3069 W while gen V/Hz read 0.
        """
        inverter = _inverter(InverterFamily.EG4_HYBRID)
        inverter._transport_runtime.generator_power = 3069.0
        inverter._transport_runtime.generator_voltage = 0.0
        inverter._transport_runtime.generator_frequency = 0.0
        assert inverter.is_using_generator is False

    def test_energised_generator_detected(self) -> None:
        """A live GEN terminal is True even with reg 123 at zero."""
        inverter = _inverter(InverterFamily.EG4_HYBRID)
        inverter._transport_runtime.generator_power = 0.0
        inverter._transport_runtime.generator_voltage = 240.1
        inverter._transport_runtime.generator_frequency = 59.9
        assert inverter.is_using_generator is True

    @pytest.mark.parametrize(("volt", "freq"), [(240.0, 0.0), (0.0, 60.0)])
    def test_requires_both_voltage_and_frequency(self, volt: float, freq: float) -> None:
        """One live measurement alone is not an energised generator."""
        inverter = _inverter(InverterFamily.EG4_HYBRID)
        inverter._transport_runtime.generator_voltage = volt
        inverter._transport_runtime.generator_frequency = freq
        assert inverter.is_using_generator is False

    def test_cloud_measurements_win_over_the_portal_flag(self) -> None:
        """Pure CLOUD: V/Hz decide, because they are always present there.

        ``InverterRuntime.genVolt``/``genFreq`` are non-optional ints defaulting
        to 0, so the cloud path never has "missing" measurements and the portal
        flag is not reached.  A dead GEN terminal answers False even if the
        portal's 12K-specific flag disagrees — that ordering is deliberate,
        since V/Hz is family-agnostic and the flag is not.
        """
        inverter = GenericInverter(client=MagicMock(), serial_number="1234567890", model="12000XP")
        inverter._features = InverterFeatures(model_family=InverterFamily.EG4_OFFGRID)
        inverter._runtime = InverterRuntime.model_construct(
            genVolt=0, genFreq=0, genPower=28646, _12KUsingGenerator=True
        )
        assert inverter.is_using_generator is False

    def test_transport_partial_read_does_not_use_the_stale_cloud_flag(self) -> None:
        """HYBRID partial read: regs 121/122 lost → False, not the portal flag.

        In HYBRID the cloud ``_runtime`` is refreshed only for EG4_OFFGRID
        (``_wants_hybrid_supplemental_runtime``), so for other families it is a
        setup-time snapshot.  Presenting a stale boolean as current state would
        be worse than reporting nothing — and falling back to
        ``generator_power`` instead would reintroduce #544 outright.
        """
        inverter = _inverter(InverterFamily.EG4_HYBRID)
        inverter._transport_runtime.generator_voltage = None
        inverter._transport_runtime.generator_frequency = None
        inverter._transport_runtime.generator_power = 28646.0
        inverter._runtime = InverterRuntime.model_construct(_12KUsingGenerator=True)
        assert inverter.is_using_generator is False

    def test_pure_cloud_with_no_measurements_uses_the_portal_flag(self) -> None:
        """No transport and no V/Hz at all: the portal's own flag is all there is.

        It is the portal's independent determination, NOT a
        ``generator_power > 0`` comparison — #196 recorded the flag reading
        false while reg 123 held a large counter value, so the portal does not
        derive it from that register either.
        """
        inverter = GenericInverter(client=MagicMock(), serial_number="1234567890", model="12000XP")
        inverter._features = InverterFeatures(model_family=InverterFamily.EG4_OFFGRID)
        runtime = InverterRuntime.model_construct(_12KUsingGenerator=True)
        # Drop the defaulted fields so the measurements read as genuinely absent.
        del runtime.genVolt
        del runtime.genFreq
        inverter._runtime = runtime
        assert inverter.is_using_generator is True
