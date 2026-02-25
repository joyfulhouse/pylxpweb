"""Unit tests for fault and warning code catalogs."""

from __future__ import annotations

from pylxpweb.constants.fault_codes import (
    BMS_FAULT_CODES,
    BMS_WARNING_CODES,
    INVERTER_FAULT_CODES,
    INVERTER_WARNING_CODES,
    decode_bms_code,
    decode_fault_bits,
)
from pylxpweb.registers.inverter_input import BY_NAME
from pylxpweb.transports.data import InverterRuntimeData


class TestInverterFaultCodes:
    """Tests for the INVERTER_FAULT_CODES bitfield catalog."""

    def test_catalog_exists_and_nonempty(self) -> None:
        """Catalog should have at least 21 entries."""
        assert isinstance(INVERTER_FAULT_CODES, dict)
        assert len(INVERTER_FAULT_CODES) >= 21

    def test_keys_are_valid_bit_positions(self) -> None:
        """All keys must be bit positions in range 0-31."""
        for bit in INVERTER_FAULT_CODES:
            assert isinstance(bit, int)
            assert 0 <= bit <= 31, f"Bit position {bit} out of range 0-31"

    def test_values_are_nonempty_strings(self) -> None:
        """All descriptions must be non-empty strings."""
        for desc in INVERTER_FAULT_CODES.values():
            assert isinstance(desc, str)
            assert len(desc) > 0

    def test_known_entries_match(self) -> None:
        """Spot-check a few known fault descriptions."""
        assert INVERTER_FAULT_CODES[0] == "Internal communication failure 1"
        assert INVERTER_FAULT_CODES[21] == "PV overvoltage"
        assert INVERTER_FAULT_CODES[25] == "Heatsink temperature out of range"
        assert INVERTER_FAULT_CODES[31] == "Internal communication failure 4"


class TestInverterWarningCodes:
    """Tests for the INVERTER_WARNING_CODES bitfield catalog."""

    def test_catalog_exists_and_nonempty(self) -> None:
        """Catalog should have at least 30 entries."""
        assert isinstance(INVERTER_WARNING_CODES, dict)
        assert len(INVERTER_WARNING_CODES) >= 30

    def test_keys_are_valid_bit_positions(self) -> None:
        """All keys must be bit positions in range 0-31."""
        for bit in INVERTER_WARNING_CODES:
            assert isinstance(bit, int)
            assert 0 <= bit <= 31, f"Bit position {bit} out of range 0-31"

    def test_values_are_nonempty_strings(self) -> None:
        """All descriptions must be non-empty strings."""
        for desc in INVERTER_WARNING_CODES.values():
            assert isinstance(desc, str)
            assert len(desc) > 0

    def test_known_entries_match(self) -> None:
        """Spot-check a few known warning descriptions."""
        assert INVERTER_WARNING_CODES[0] == "Battery communication failed"
        assert INVERTER_WARNING_CODES[6] == "RSD Active"
        assert INVERTER_WARNING_CODES[16] == "No grid connection"
        assert INVERTER_WARNING_CODES[30] == "Meter reversed"


class TestBmsFaultCodes:
    """Tests for the BMS_FAULT_CODES enumerated catalog."""

    def test_catalog_exists_and_nonempty(self) -> None:
        """Catalog should have at least 15 entries."""
        assert isinstance(BMS_FAULT_CODES, dict)
        assert len(BMS_FAULT_CODES) >= 15

    def test_keys_in_expected_range(self) -> None:
        """Keys should span 0x00 through 0x0E."""
        for code in BMS_FAULT_CODES:
            assert isinstance(code, int)
            assert 0x00 <= code <= 0x0E, f"BMS fault code 0x{code:02X} out of range"

    def test_normal_is_zero(self) -> None:
        """Code 0x00 should indicate normal / no fault."""
        assert BMS_FAULT_CODES[0x00] == "Normal / No Fault"

    def test_known_entries_match(self) -> None:
        """Spot-check known BMS fault descriptions."""
        assert BMS_FAULT_CODES[0x01] == "Cell Over-Voltage Protection (COVP)"
        assert BMS_FAULT_CODES[0x0B] == "Short Circuit"
        assert BMS_FAULT_CODES[0x0E] == "Over-Capacity"


class TestBmsWarningCodes:
    """Tests for the BMS_WARNING_CODES enumerated catalog."""

    def test_catalog_exists_and_nonempty(self) -> None:
        """Catalog should have at least 15 entries."""
        assert isinstance(BMS_WARNING_CODES, dict)
        assert len(BMS_WARNING_CODES) >= 15

    def test_keys_in_expected_range(self) -> None:
        """Keys should span 0x00 through 0x0E."""
        for code in BMS_WARNING_CODES:
            assert isinstance(code, int)
            assert 0x00 <= code <= 0x0E, f"BMS warning code 0x{code:02X} out of range"

    def test_normal_is_zero(self) -> None:
        """Code 0x00 should indicate normal / no warning."""
        assert BMS_WARNING_CODES[0x00] == "Normal / No Warning"

    def test_known_entries_match(self) -> None:
        """Spot-check known BMS warning descriptions."""
        assert BMS_WARNING_CODES[0x01] == "Cell Over-Voltage Warning"
        assert BMS_WARNING_CODES[0x0B] == "Short Circuit Warning"
        assert BMS_WARNING_CODES[0x0E] == "Over-Capacity Warning"


class TestDecodeFaultBits:
    """Tests for the decode_fault_bits() bitfield decoder."""

    def test_no_faults_returns_empty(self) -> None:
        """A raw value of 0 should produce an empty list."""
        result = decode_fault_bits(0, INVERTER_FAULT_CODES)
        assert result == []

    def test_single_fault(self) -> None:
        """A single set bit should return exactly one description."""
        result = decode_fault_bits(1 << 21, INVERTER_FAULT_CODES)
        assert result == ["PV overvoltage"]

    def test_multiple_faults(self) -> None:
        """Multiple set bits should return sorted descriptions."""
        raw = (1 << 0) | (1 << 21)
        result = decode_fault_bits(raw, INVERTER_FAULT_CODES)
        assert result == ["Internal communication failure 1", "PV overvoltage"]

    def test_unknown_bit_ignored(self) -> None:
        """Bits not in the catalog should not appear in the output."""
        # Bit 2 is not in INVERTER_FAULT_CODES
        raw = (1 << 2) | (1 << 0)
        result = decode_fault_bits(raw, INVERTER_FAULT_CODES)
        assert result == ["Internal communication failure 1"]

    def test_all_bits_set(self) -> None:
        """Setting all 32 bits should return all catalog entries in order."""
        raw = 0xFFFFFFFF
        result = decode_fault_bits(raw, INVERTER_FAULT_CODES)
        assert len(result) == len(INVERTER_FAULT_CODES)
        # Results should be sorted by bit position
        expected = [desc for _, desc in sorted(INVERTER_FAULT_CODES.items())]
        assert result == expected

    def test_works_with_warning_codes(self) -> None:
        """Decoder should also work with the warning code catalog."""
        raw = 1 << 6
        result = decode_fault_bits(raw, INVERTER_WARNING_CODES)
        assert result == ["RSD Active"]


class TestDecodeBmsCode:
    """Tests for the decode_bms_code() enum decoder."""

    def test_normal_code(self) -> None:
        """Code 0x00 should return normal description."""
        result = decode_bms_code(0x00, BMS_FAULT_CODES)
        assert result == "Normal / No Fault"

    def test_known_code(self) -> None:
        """A known code should return its description."""
        result = decode_bms_code(0x0B, BMS_FAULT_CODES)
        assert result == "Short Circuit"

    def test_unknown_code(self) -> None:
        """An unknown code should return a formatted unknown string."""
        result = decode_bms_code(0xFF, BMS_FAULT_CODES)
        assert result == "Unknown code: 0xFF"

    def test_works_with_warning_codes(self) -> None:
        """Decoder should also work with the warning code catalog."""
        result = decode_bms_code(0x05, BMS_WARNING_CODES)
        assert result == "Charging Over-Temperature Warning"

    def test_unknown_warning_code(self) -> None:
        """Unknown warning code should use hex formatting."""
        result = decode_bms_code(0x10, BMS_WARNING_CODES)
        assert result == "Unknown code: 0x10"


class TestFaultRegisterSensorKeys:
    """Verify fault/warning registers have ha_sensor_key for HA diagnostics."""

    def test_fault_code_has_sensor_key(self) -> None:
        assert BY_NAME["fault_code"].ha_sensor_key == "fault_code"

    def test_warning_code_has_sensor_key(self) -> None:
        assert BY_NAME["warning_code"].ha_sensor_key == "warning_code"

    def test_bms_fault_code_has_sensor_key(self) -> None:
        assert BY_NAME["bms_fault_code"].ha_sensor_key == "bms_fault_code"

    def test_bms_warning_code_has_sensor_key(self) -> None:
        assert BY_NAME["bms_warning_code"].ha_sensor_key == "bms_warning_code"


class TestInverterRuntimeDataFaultProperties:
    """Test fault/warning message properties on InverterRuntimeData."""

    def test_fault_messages_no_fault(self) -> None:
        data = InverterRuntimeData(fault_code=0)
        assert data.fault_messages == []

    def test_fault_messages_single(self) -> None:
        data = InverterRuntimeData(fault_code=(1 << 21))
        assert data.fault_messages == ["PV overvoltage"]

    def test_fault_messages_none_value(self) -> None:
        data = InverterRuntimeData(fault_code=None)
        assert data.fault_messages == []

    def test_warning_messages_multiple(self) -> None:
        data = InverterRuntimeData(warning_code=(1 << 0) | (1 << 9))
        assert len(data.warning_messages) == 2

    def test_warning_messages_none_value(self) -> None:
        data = InverterRuntimeData(warning_code=None)
        assert data.warning_messages == []


class TestPackageExports:
    """Test new symbols are accessible from package-level imports."""

    def test_fault_codes_from_constants(self) -> None:
        from pylxpweb.constants.fault_codes import (
            BMS_FAULT_CODES,
            INVERTER_FAULT_CODES,
            decode_bms_code,
            decode_fault_bits,
        )

        assert len(INVERTER_FAULT_CODES) > 0
        assert len(BMS_FAULT_CODES) > 0
        assert callable(decode_fault_bits)
        assert callable(decode_bms_code)

    def test_scheduling_from_registers(self) -> None:
        from pylxpweb.registers import (
            SCHEDULE_BY_ADDRESS,
            SCHEDULE_BY_API_KEY,
            SCHEDULE_BY_NAME,
            SCHEDULE_REGISTERS,
            ScheduleTypeConfig,
        )

        assert len(SCHEDULE_REGISTERS) == 224
        assert len(SCHEDULE_BY_ADDRESS) == 224
        assert len(SCHEDULE_BY_NAME) == 224
        assert len(SCHEDULE_BY_API_KEY) == 224
        assert ScheduleTypeConfig is not None
