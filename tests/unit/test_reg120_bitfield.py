"""Register-120 compound-field metadata contract."""

from pylxpweb.registers import bitfield_entries_for_address


class TestRegister120Bitfield:
    """The canonical catalog must agree with named-parameter RMW semantics."""

    def test_compound_field_offsets_and_widths(self) -> None:
        """H120 contains five fields, not seven consecutive booleans."""
        entries = bitfield_entries_for_address(120)

        assert [
            (entry.api_param_key, entry.bit_position, entry.field_width) for entry in entries
        ] == [
            ("FUNC_HALF_HOUR_AC_CHG_START_EN", 0, 1),
            ("BIT_AC_CHARGE_TYPE", 1, 3),
            ("BIT_DISCHG_CONTROL_TYPE", 4, 2),
            ("BIT_ON_GRID_EOD_TYPE", 6, 1),
            ("BIT_GENERATOR_CHARGE_TYPE", 7, 1),
        ]

    def test_overlapping_legacy_boolean_names_are_absent(self) -> None:
        """Compound AC-charge bits cannot also be advertised as booleans."""
        api_keys = {entry.api_param_key for entry in bitfield_entries_for_address(120)}

        assert "FUNC_SNA_BAT_DISCHARGE_CONTROL" not in api_keys
        assert "FUNC_PHASE_INDEPEND_COMPENSATE_EN" not in api_keys
