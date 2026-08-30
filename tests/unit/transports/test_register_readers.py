"""Tests for shared register-reading helpers (_register_readers).

Covers the GridBOSS serial fallback (eg4_web_monitor#593): MID devices keep
AC-couple lifetime-energy counters at input registers 115-119, so the serial
read must fall back to holding registers 2-6 (HOLD_SERIAL_NUM).
"""

from __future__ import annotations

import pytest

from pylxpweb.transports._register_readers import (
    _is_plausible_serial,
    decode_firmware_from_registers,
    decode_serial_from_registers,
    read_serial_number_async,
)
from pylxpweb.transports.exceptions import TransportReadError

# Reporter's GridBOSS (fw IAAB-1600) holding registers 2-6: ASCII serial,
# low byte first per register (same byte order as the firmware code regs).
GRIDBOSS_HOLDING_SERIAL_REGS = [0x3036, 0x3333, 0x3538, 0x3730, 0x3438]
GRIDBOSS_HOLDING_SERIAL = "6033850784"

INVERTER_INPUT_SERIAL_REGS = [0x4142, 0x3231, 0x3433, 0x3635, 0x3837]
INVERTER_INPUT_SERIAL = "BA12345678"

# Serial with a letter mid-string (real FlexBOSS21-style serial), low byte first.
LETTERED_INPUT_SERIAL_REGS = [0x3235, 0x3438, 0x5032, 0x3530, 0x3138]
LETTERED_INPUT_SERIAL = "52842P0581"

# Energy-counter bytes that happen to decode to 10 printable but
# non-alphanumeric chars (".*" per register) — must not pass as a serial.
GARBAGE_PRINTABLE_REGS = [0x2A2E] * 5
GARBAGE_PRINTABLE_DECODE = ".*.*.*.*.*"


class TestDecodeSerialFromRegisters:
    def test_decodes_low_byte_first(self) -> None:
        assert decode_serial_from_registers(GRIDBOSS_HOLDING_SERIAL_REGS) == GRIDBOSS_HOLDING_SERIAL

    def test_all_zero_registers_decode_empty(self) -> None:
        assert decode_serial_from_registers([0, 0, 0, 0, 0]) == ""

    def test_byte_order_matches_firmware_decode(self) -> None:
        # Firmware regs 7-10 from the same device dump decode to IAAB-1600,
        # anchoring the low-byte-first ordering used for the serial.
        assert decode_firmware_from_registers([0x4149, 0x4241, 0x1600, 0x0100]) == ("IAAB-1600")


class TestIsPlausibleSerial:
    @pytest.mark.parametrize(
        "serial",
        ["1234567890", "1234A56789", "52842P0581", "BA12345678", "ba12345678"],
    )
    def test_accepts_10_char_alphanumeric(self, serial: str) -> None:
        assert _is_plausible_serial(serial)

    @pytest.mark.parametrize(
        "candidate",
        ["", "BA", "123456789", "12345678901", GARBAGE_PRINTABLE_DECODE, "BA12345 67"],
    )
    def test_rejects_non_serial_decodes(self, candidate: str) -> None:
        assert not _is_plausible_serial(candidate)


class TestReadSerialNumberAsync:
    @pytest.mark.asyncio
    async def test_input_registers_preferred(self) -> None:
        holding_calls: list[tuple[int, int]] = []

        async def read_input(address: int, count: int) -> list[int]:
            assert (address, count) == (115, 5)
            return INVERTER_INPUT_SERIAL_REGS

        async def read_holding(address: int, count: int) -> list[int]:
            holding_calls.append((address, count))
            return GRIDBOSS_HOLDING_SERIAL_REGS

        result = await read_serial_number_async(read_input, "test", read_holding=read_holding)
        assert result == INVERTER_INPUT_SERIAL
        assert holding_calls == []

    @pytest.mark.asyncio
    async def test_gridboss_zero_input_falls_back_to_holding(self) -> None:
        async def read_input(address: int, count: int) -> list[int]:
            return [0, 0, 0, 0, 0]

        async def read_holding(address: int, count: int) -> list[int]:
            assert (address, count) == (2, 5)
            return GRIDBOSS_HOLDING_SERIAL_REGS

        result = await read_serial_number_async(read_input, "discovery", read_holding=read_holding)
        assert result == GRIDBOSS_HOLDING_SERIAL

    @pytest.mark.asyncio
    async def test_truncated_input_serial_falls_back(self) -> None:
        # Printable garbage shorter than 10 chars (e.g. partial AC-couple
        # energy bytes) must not be accepted as a serial.
        async def read_input(address: int, count: int) -> list[int]:
            return [0x4142, 0, 0, 0, 0]

        async def read_holding(address: int, count: int) -> list[int]:
            return GRIDBOSS_HOLDING_SERIAL_REGS

        result = await read_serial_number_async(read_input, "discovery", read_holding=read_holding)
        assert result == GRIDBOSS_HOLDING_SERIAL

    @pytest.mark.asyncio
    async def test_lettered_input_serial_accepted_without_fallback(self) -> None:
        # Regression guard for inverters: a genuine serial with a letter
        # mid-string must short-circuit — no holding read.
        holding_calls: list[tuple[int, int]] = []

        async def read_input(address: int, count: int) -> list[int]:
            return LETTERED_INPUT_SERIAL_REGS

        async def read_holding(address: int, count: int) -> list[int]:
            holding_calls.append((address, count))
            return GRIDBOSS_HOLDING_SERIAL_REGS

        result = await read_serial_number_async(read_input, "test", read_holding=read_holding)
        assert result == LETTERED_INPUT_SERIAL
        assert holding_calls == []

    @pytest.mark.asyncio
    async def test_ten_char_printable_garbage_input_falls_back(self) -> None:
        # GridBOSS with accumulated AC-couple energy: input 115-119 can
        # decode to 10 printable but non-alphanumeric chars. That must not
        # be adopted as the identity — the holding fallback still fires.
        async def read_input(address: int, count: int) -> list[int]:
            return GARBAGE_PRINTABLE_REGS

        async def read_holding(address: int, count: int) -> list[int]:
            assert (address, count) == (2, 5)
            return GRIDBOSS_HOLDING_SERIAL_REGS

        result = await read_serial_number_async(read_input, "discovery", read_holding=read_holding)
        assert result == GRIDBOSS_HOLDING_SERIAL

    @pytest.mark.asyncio
    async def test_partial_holding_decode_not_adopted(self) -> None:
        # A truncated holding decode (e.g. flaky read) must not be adopted
        # as the serial; the input-register result is kept.
        async def read_input(address: int, count: int) -> list[int]:
            return [0, 0, 0, 0, 0]

        async def read_holding(address: int, count: int) -> list[int]:
            return [0x4142, 0, 0, 0, 0]

        result = await read_serial_number_async(read_input, "discovery", read_holding=read_holding)
        assert result == ""

    @pytest.mark.asyncio
    async def test_garbage_holding_decode_not_adopted(self) -> None:
        # Both sources garbage: keep the input-register result unchanged
        # (pre-fallback behavior) rather than adopting holding garbage.
        async def read_input(address: int, count: int) -> list[int]:
            return GARBAGE_PRINTABLE_REGS

        async def read_holding(address: int, count: int) -> list[int]:
            return GARBAGE_PRINTABLE_REGS

        result = await read_serial_number_async(read_input, "discovery", read_holding=read_holding)
        assert result == GARBAGE_PRINTABLE_DECODE

    @pytest.mark.asyncio
    async def test_holding_read_error_keeps_input_result(self) -> None:
        # Devices with a restricted register map can reject holding reads
        # 2-6; the fallback must degrade to the pre-fallback input result,
        # not turn discovery into a hard transport failure.
        async def read_input(address: int, count: int) -> list[int]:
            return [0, 0, 0, 0, 0]

        async def read_holding(address: int, count: int) -> list[int]:
            raise TransportReadError("holding registers rejected")

        result = await read_serial_number_async(read_input, "discovery", read_holding=read_holding)
        assert result == ""

    @pytest.mark.asyncio
    async def test_no_holding_reader_preserves_legacy_behavior(self) -> None:
        async def read_input(address: int, count: int) -> list[int]:
            return [0, 0, 0, 0, 0]

        assert await read_serial_number_async(read_input, "discovery") == ""

    @pytest.mark.asyncio
    async def test_both_sources_empty_returns_input_result(self) -> None:
        async def read_input(address: int, count: int) -> list[int]:
            return [0, 0, 0, 0, 0]

        async def read_holding(address: int, count: int) -> list[int]:
            return [0, 0, 0, 0, 0]

        result = await read_serial_number_async(read_input, "discovery", read_holding=read_holding)
        assert result == ""
