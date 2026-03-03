"""Tests for battery protocol auto-detection."""

from __future__ import annotations

from pylxpweb.battery_protocols.detection import detect_protocol
from pylxpweb.battery_protocols.eg4_master import EG4MasterProtocol
from pylxpweb.battery_protocols.eg4_slave import EG4SlaveProtocol


class TestDetectProtocol:
    """Tests for detect_protocol()."""

    def test_detect_master_all_zeros_early(self) -> None:
        """Regs 0-18 all zeros -> master protocol."""
        raw = dict.fromkeys(range(39), 0)
        raw[22] = 5294  # Master voltage at reg 22
        protocol = detect_protocol(raw)
        assert isinstance(protocol, EG4MasterProtocol)

    def test_detect_slave_has_voltage_at_reg0(self) -> None:
        """Reg 0 has voltage -> slave protocol."""
        raw = dict.fromkeys(range(39), 0)
        raw[0] = 5294  # Slave voltage at reg 0
        raw[1] = 100  # Slave current
        raw[2] = 3310  # Cell voltage
        protocol = detect_protocol(raw)
        assert isinstance(protocol, EG4SlaveProtocol)

    def test_detect_master_tolerates_noise(self) -> None:
        """Up to 2 non-zero regs in 0-18 still detected as master."""
        raw = dict.fromkeys(range(39), 0)
        raw[5] = 1  # One spurious non-zero
        raw[10] = 1  # Second spurious
        protocol = detect_protocol(raw)
        assert isinstance(protocol, EG4MasterProtocol)

    def test_detect_slave_3_or_more_nonzero(self) -> None:
        """3+ non-zero regs in 0-18 -> slave protocol."""
        raw = dict.fromkeys(range(39), 0)
        raw[0] = 5294
        raw[1] = 100
        raw[2] = 3310
        protocol = detect_protocol(raw)
        assert isinstance(protocol, EG4SlaveProtocol)

    def test_detect_empty_regs_returns_master(self) -> None:
        """Empty/all-zero registers default to master."""
        raw: dict[int, int] = {}
        protocol = detect_protocol(raw)
        assert isinstance(protocol, EG4MasterProtocol)

    def test_detect_exactly_2_nonzero_is_master(self) -> None:
        """Exactly 2 non-zero regs in 0-18 is still master (boundary)."""
        raw = dict.fromkeys(range(39), 0)
        raw[0] = 42
        raw[18] = 7
        protocol = detect_protocol(raw)
        assert isinstance(protocol, EG4MasterProtocol)

    def test_detect_exactly_3_nonzero_is_slave(self) -> None:
        """Exactly 3 non-zero regs in 0-18 triggers slave (boundary)."""
        raw = dict.fromkeys(range(39), 0)
        raw[0] = 42
        raw[9] = 7
        raw[18] = 3
        protocol = detect_protocol(raw)
        assert isinstance(protocol, EG4SlaveProtocol)

    def test_detect_nonzero_outside_range_ignored(self) -> None:
        """Registers outside 0-18 don't affect detection."""
        raw = dict.fromkeys(range(39), 0)
        # Only non-zero values outside the 0-18 range
        raw[19] = 1000
        raw[22] = 5294
        raw[30] = 50
        protocol = detect_protocol(raw)
        assert isinstance(protocol, EG4MasterProtocol)
