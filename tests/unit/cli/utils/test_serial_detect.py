"""Tests for serial detection utilities."""

from pylxpweb.cli.utils.serial_detect import (
    detect_serial_from_registers,
    extract_arm_firmware,
    extract_model_code,
    format_device_info,
    parse_firmware_version,
)


class TestDetectSerialFromRegisters:
    """Tests for detect_serial_from_registers function."""

    def test_valid_serial(self) -> None:
        """Test extracting a valid serial number."""
        # "CE12345678" as 5 registers (2 chars each, big-endian)
        # C=0x43, E=0x45 -> 0x4345
        # 1=0x31, 2=0x32 -> 0x3132
        # etc.
        registers = {
            115: 0x4345,  # CE
            116: 0x3132,  # 12
            117: 0x3334,  # 34
            118: 0x3536,  # 56
            119: 0x3738,  # 78
        }

        serial = detect_serial_from_registers(registers)
        assert serial == "CE12345678"

    def test_missing_registers(self) -> None:
        """Test with missing registers."""
        registers = {
            115: 0x4345,  # CE
            116: 0x3132,  # 12
            # Missing 117-119
        }

        serial = detect_serial_from_registers(registers)
        assert serial is None

    def test_empty_registers(self) -> None:
        """Test with empty register dict."""
        serial = detect_serial_from_registers({})
        assert serial is None

    def test_null_padded_serial(self) -> None:
        """Test serial with null padding."""
        # "AB1234" with nulls at end
        registers = {
            115: 0x4142,  # AB
            116: 0x3132,  # 12
            117: 0x3334,  # 34
            118: 0x0000,  # nulls
            119: 0x0000,  # nulls
        }

        serial = detect_serial_from_registers(registers)
        assert serial == "AB1234"


class TestParseFirmwareVersion:
    """Tests for parse_firmware_version function."""

    def test_valid_firmware(self) -> None:
        """Test extracting valid firmware version."""
        # "FAAB2525" as 4 registers
        registers = {
            7: 0x4641,  # FA
            8: 0x4142,  # AB
            9: 0x3235,  # 25
            10: 0x3235,  # 25
        }

        firmware = parse_firmware_version(registers)
        assert firmware == "FAAB2525"

    def test_missing_registers(self) -> None:
        """Test with missing firmware registers."""
        registers = {
            7: 0x4641,  # FA
            8: 0x4142,  # AB
            # Missing 9-10
        }

        firmware = parse_firmware_version(registers)
        assert firmware is None


class TestExtractModelCode:
    """Tests for extract_model_code function."""

    def test_extract_model_code(self) -> None:
        """Test extracting model code from register 19."""
        registers = {19: 2092}  # PV Series
        assert extract_model_code(registers) == 2092

    def test_missing_model_code(self) -> None:
        """Test with missing register 19."""
        registers = {0: 100, 1: 200}
        assert extract_model_code(registers) is None


class TestExtractArmFirmware:
    """Tests for extract_arm_firmware function."""

    def test_valid_arm_firmware(self) -> None:
        """Test extracting ARM firmware."""
        # "V1.2.3.456" as 5 registers
        registers = {
            110: 0x5631,  # V1
            111: 0x2E32,  # .2
            112: 0x2E33,  # .3
            113: 0x2E34,  # .4
            114: 0x3536,  # 56
        }

        firmware = extract_arm_firmware(registers)
        assert firmware == "V1.2.3.456"


class TestFormatDeviceInfo:
    """Tests for format_device_info function."""

    def test_full_info(self) -> None:
        """Test formatting with all info present."""
        info = format_device_info(
            serial="CE12345678",
            firmware="FAAB-2525",
            model_code=2092,
            arm_firmware="V1.2.3",
        )

        assert "CE12345678" in info
        assert "FAAB-2525" in info
        assert "2092" in info
        assert "V1.2.3" in info

    def test_minimal_info(self) -> None:
        """Test formatting with minimal info."""
        info = format_device_info(
            serial=None,
            firmware=None,
            model_code=None,
        )

        assert "Unknown" in info

    def test_partial_info(self) -> None:
        """Test formatting with partial info."""
        info = format_device_info(
            serial="TEST123456",
            firmware="1.0.0",
            model_code=None,
        )

        assert "TEST123456" in info
        assert "1.0.0" in info
