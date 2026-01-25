"""Tests for base collector data structures."""

from datetime import datetime

from pylxpweb.cli.collectors.base import (
    CollectionResult,
    ComparisonResult,
    RegisterMismatch,
    compare_collections,
)


class TestCollectionResult:
    """Tests for CollectionResult dataclass."""

    def test_create_collection_result(self) -> None:
        """Test creating a basic collection result."""
        result = CollectionResult(
            source="modbus",
            timestamp=datetime(2026, 1, 25, 12, 0, 0),
            serial_number="CE12345678",
            firmware_version="FAAB-2525",
            input_registers={0: 100, 1: 200, 2: 0},
            holding_registers={0: 50, 1: 0},
        )

        assert result.source == "modbus"
        assert result.serial_number == "CE12345678"
        assert result.firmware_version == "FAAB-2525"
        assert result.input_register_count() == 3
        assert result.holding_register_count() == 2

    def test_nonzero_counts(self) -> None:
        """Test counting non-zero registers."""
        result = CollectionResult(
            source="test",
            timestamp=datetime.now(),
            serial_number="TEST",
            input_registers={0: 100, 1: 0, 2: 200, 3: 0},
            holding_registers={0: 50, 1: 0, 2: 0},
        )

        assert result.input_nonzero_count() == 2
        assert result.holding_nonzero_count() == 1

    def test_empty_result(self) -> None:
        """Test empty collection result."""
        result = CollectionResult(
            source="test",
            timestamp=datetime.now(),
            serial_number="TEST",
        )

        assert result.input_register_count() == 0
        assert result.holding_register_count() == 0
        assert result.input_nonzero_count() == 0
        assert result.holding_nonzero_count() == 0


class TestRegisterMismatch:
    """Tests for RegisterMismatch dataclass."""

    def test_mismatch_string(self) -> None:
        """Test mismatch string representation."""
        mismatch = RegisterMismatch(
            address=42,
            register_type="input",
            source_a="modbus",
            value_a=100,
            source_b="cloud",
            value_b=200,
        )

        assert str(mismatch) == "input[42]: modbus=100 vs cloud=200"

    def test_mismatch_with_none(self) -> None:
        """Test mismatch with None value."""
        mismatch = RegisterMismatch(
            address=10,
            register_type="holding",
            source_a="modbus",
            value_a=50,
            source_b="cloud",
            value_b=None,
        )

        assert str(mismatch) == "holding[10]: modbus=50 vs cloud=None"


class TestComparisonResult:
    """Tests for ComparisonResult dataclass."""

    def test_is_match_with_no_mismatches(self) -> None:
        """Test is_match returns True when no mismatches."""
        result = ComparisonResult(
            sources=["modbus", "cloud"],
            input_match_count=100,
            holding_match_count=50,
        )

        assert result.is_match() is True
        assert result.total_mismatches() == 0

    def test_is_match_with_mismatches(self) -> None:
        """Test is_match returns False with mismatches."""
        result = ComparisonResult(
            sources=["modbus", "cloud"],
            input_mismatches=[
                RegisterMismatch(
                    address=1,
                    register_type="input",
                    source_a="modbus",
                    value_a=100,
                    source_b="cloud",
                    value_b=200,
                )
            ],
            holding_mismatches=[
                RegisterMismatch(
                    address=5,
                    register_type="holding",
                    source_a="modbus",
                    value_a=50,
                    source_b="cloud",
                    value_b=60,
                )
            ],
        )

        assert result.is_match() is False
        assert result.total_mismatches() == 2


class TestCompareCollections:
    """Tests for compare_collections function."""

    def test_identical_collections(self) -> None:
        """Test comparing identical collections."""
        result_a = CollectionResult(
            source="modbus",
            timestamp=datetime.now(),
            serial_number="TEST",
            input_registers={0: 100, 1: 200},
            holding_registers={0: 50},
        )
        result_b = CollectionResult(
            source="dongle",
            timestamp=datetime.now(),
            serial_number="TEST",
            input_registers={0: 100, 1: 200},
            holding_registers={0: 50},
        )

        comparison = compare_collections(result_a, result_b)

        assert comparison.is_match() is True
        assert comparison.input_match_count == 2
        assert comparison.holding_match_count == 1
        assert len(comparison.input_mismatches) == 0
        assert len(comparison.holding_mismatches) == 0

    def test_different_values(self) -> None:
        """Test comparing collections with different values."""
        result_a = CollectionResult(
            source="modbus",
            timestamp=datetime.now(),
            serial_number="TEST",
            input_registers={0: 100, 1: 200},
            holding_registers={0: 50, 1: 60},
        )
        result_b = CollectionResult(
            source="dongle",
            timestamp=datetime.now(),
            serial_number="TEST",
            input_registers={0: 100, 1: 999},  # Different
            holding_registers={0: 50, 1: 888},  # Different
        )

        comparison = compare_collections(result_a, result_b)

        assert comparison.is_match() is False
        assert comparison.input_match_count == 1  # addr 0 matches
        assert comparison.holding_match_count == 1  # addr 0 matches
        assert len(comparison.input_mismatches) == 1
        assert len(comparison.holding_mismatches) == 1

    def test_missing_registers(self) -> None:
        """Test comparing collections with missing registers."""
        result_a = CollectionResult(
            source="modbus",
            timestamp=datetime.now(),
            serial_number="TEST",
            input_registers={0: 100, 1: 200, 2: 300},
            holding_registers={0: 50},
        )
        result_b = CollectionResult(
            source="dongle",
            timestamp=datetime.now(),
            serial_number="TEST",
            input_registers={0: 100},  # Missing 1 and 2
            holding_registers={0: 50, 1: 60},  # Extra 1
        )

        comparison = compare_collections(result_a, result_b)

        # addr 1 and 2 are mismatches (present in a, missing in b)
        # addr 0 matches
        assert comparison.input_match_count == 1
        assert len(comparison.input_mismatches) == 2

        # addr 1 is mismatch (missing in a, present in b)
        # addr 0 matches
        assert comparison.holding_match_count == 1
        assert len(comparison.holding_mismatches) == 1
