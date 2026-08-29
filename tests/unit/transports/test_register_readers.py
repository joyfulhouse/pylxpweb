"""Tests for shared register-reading helpers (_register_readers).

Covers the GridBOSS serial fallback (eg4_web_monitor#593): MID devices keep
AC-couple lifetime-energy counters at input registers 115-119, so the serial
read must fall back to holding registers 2-6 (HOLD_SERIAL_NUM).
"""

from __future__ import annotations

import pytest

from pylxpweb.transports._register_readers import (
    decode_firmware_from_registers,
    decode_serial_from_registers,
    read_serial_number_async,
)

# Reporter's GridBOSS (fw IAAB-1600) holding registers 2-6: ASCII serial,
# low byte first per register (same byte order as the firmware code regs).
GRIDBOSS_HOLDING_SERIAL_REGS = [0x3036, 0x3333, 0x3538, 0x3730, 0x3438]
GRIDBOSS_HOLDING_SERIAL = "6033850784"

INVERTER_INPUT_SERIAL_REGS = [0x4142, 0x3231, 0x3433, 0x3635, 0x3837]
INVERTER_INPUT_SERIAL = "BA12345678"


class TestDecodeSerialFromRegisters:
    def test_decodes_low_byte_first(self) -> None:
        assert decode_serial_from_registers(GRIDBOSS_HOLDING_SERIAL_REGS) == GRIDBOSS_HOLDING_SERIAL

    def test_all_zero_registers_decode_empty(self) -> None:
        assert decode_serial_from_registers([0, 0, 0, 0, 0]) == ""

    def test_byte_order_matches_firmware_decode(self) -> None:
        # Firmware regs 7-10 from the same device dump decode to IAAB-1600,
        # anchoring the low-byte-first ordering used for the serial.
        assert decode_firmware_from_registers([0x4149, 0x4241, 0x1600, 0x0100]) == ("IAAB-1600")


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
