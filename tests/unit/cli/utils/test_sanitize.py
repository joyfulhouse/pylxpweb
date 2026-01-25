"""Tests for sanitization utilities."""


from pylxpweb.cli.utils.sanitize import sanitize_serial, sanitize_username


class TestSanitizeSerial:
    """Tests for sanitize_serial function."""

    def test_basic_sanitization(self) -> None:
        """Test basic serial sanitization."""
        result = sanitize_serial("CE12345678")
        # Should keep first 2 and last 2, replace middle with alphanumeric
        assert result.startswith("CE")
        assert result.endswith("78")
        assert len(result) == 10
        # Middle should NOT contain asterisks
        assert "*" not in result

    def test_deterministic(self) -> None:
        """Test that sanitization is deterministic."""
        result1 = sanitize_serial("CE12345678")
        result2 = sanitize_serial("CE12345678")
        assert result1 == result2

    def test_different_inputs_different_outputs(self) -> None:
        """Test that different inputs produce different outputs."""
        result1 = sanitize_serial("CE12345678")
        result2 = sanitize_serial("AB98765432")
        # Middle portions should differ
        assert result1[2:-2] != result2[2:-2]

    def test_disabled(self) -> None:
        """Test that sanitization can be disabled."""
        result = sanitize_serial("CE12345678", enabled=False)
        assert result == "CE12345678"

    def test_empty_serial(self) -> None:
        """Test with empty serial."""
        assert sanitize_serial("") == ""
        assert sanitize_serial("", enabled=True) == ""

    def test_short_serial(self) -> None:
        """Test with serial too short to sanitize."""
        assert sanitize_serial("AB") == "AB"
        assert sanitize_serial("ABC") == "ABC"
        assert sanitize_serial("ABCD") == "ABCD"  # 4 chars = 0 middle chars

    def test_five_char_serial(self) -> None:
        """Test with 5-character serial (1 middle char)."""
        result = sanitize_serial("AB1CD")
        assert result.startswith("AB")
        assert result.endswith("CD")
        assert len(result) == 5
        # Middle char is replaced (may coincidentally match original)
        assert result[2].isalnum()
        assert "*" not in result

    def test_replacement_chars_alphanumeric(self) -> None:
        """Test that replacement characters are alphanumeric."""
        result = sanitize_serial("CE12345678")
        middle = result[2:-2]
        # All characters should be uppercase alphanumeric
        assert middle.isalnum()
        assert middle == middle.upper()


class TestSanitizeUsername:
    """Tests for sanitize_username function."""

    def test_basic_sanitization(self) -> None:
        """Test basic username sanitization."""
        result = sanitize_username("user@example.com")
        assert result == "use***om"

    def test_short_username(self) -> None:
        """Test with short username."""
        assert sanitize_username("user") == "***"
        assert sanitize_username("usr") == "***"
        assert sanitize_username("ab") == "***"

    def test_exactly_five_chars(self) -> None:
        """Test with exactly 5 characters."""
        assert sanitize_username("users") == "***"

    def test_six_chars(self) -> None:
        """Test with 6 characters."""
        result = sanitize_username("user12")
        assert result == "use***12"

    def test_disabled(self) -> None:
        """Test that sanitization can be disabled."""
        result = sanitize_username("user@example.com", enabled=False)
        assert result == "user@example.com"

    def test_empty_username(self) -> None:
        """Test with empty username."""
        assert sanitize_username("") == "***"
