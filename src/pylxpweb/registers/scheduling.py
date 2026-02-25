"""7-day scheduling register definitions (holding registers 500-723).

224 registers generated parametrically from schedule type templates.
Active only when register 233 bit 3 (FUNC_ENERTEK_WORKING_MODE) is enabled.
When disabled, daily schedule registers 68-89 are in effect instead.

Cloud API:
  Read:   POST /web/maintain/remoteWeeklyOperation/readValues
  Write:  POST /web/maintain/remoteWeeklyOperation/setValues
  Toggle: POST /web/maintain/remoteSet/functionControl (FUNC_ENERTEK_WORKING_MODE)
"""

from __future__ import annotations

from dataclasses import dataclass

from pylxpweb.registers.inverter_holding import HoldingCategory, HoldingRegisterDefinition
from pylxpweb.registers.inverter_input import ALL


@dataclass(frozen=True)
class ScheduleTypeConfig:
    """Configuration for one schedule type."""

    name: str
    base_address: int
    api_write_suffix: str
    api_read_prefix: str


SCHEDULE_TYPES: tuple[ScheduleTypeConfig, ...] = (
    ScheduleTypeConfig("ac_charge", 500, "AC_CHARGE", "ubACChg"),
    ScheduleTypeConfig("forced_charge", 556, "FORCED_CHARGE", "ubForcedChg"),
    ScheduleTypeConfig("forced_discharge", 612, "FORCED_DISCHARGE", "ubForcedDischg"),
    ScheduleTypeConfig("peak_shaving", 668, "GRID_PEAK_SHAVING", "ubGridPeakShav"),
)

DAYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

_SLOT_FIELDS: tuple[tuple[int, str, str], ...] = (
    (0, "power_cmd", "PowerCMD"),
    (1, "volt_limit", "VoltLimit"),
    (2, "time_start", "StartHour"),
    (3, "time_end", "EndHour"),
)


def _generate_schedule_registers() -> tuple[HoldingRegisterDefinition, ...]:
    """Generate all 224 schedule register definitions from templates."""
    regs: list[HoldingRegisterDefinition] = []
    for stype in SCHEDULE_TYPES:
        for day_idx, day in enumerate(DAYS):
            for slot in range(2):
                for offset, field, api_field in _SLOT_FIELDS:
                    address = stype.base_address + day_idx * 8 + slot * 4 + offset
                    canonical = f"{stype.name}_{field}_{slot + 1}_{day}"
                    api_key = f"{stype.api_read_prefix}{api_field}{slot + 1}_Day_{day_idx + 1}"
                    regs.append(
                        HoldingRegisterDefinition(
                            address=address,
                            canonical_name=canonical,
                            api_param_key=api_key,
                            writable=True,
                            category=HoldingCategory.SCHEDULE,
                            models=ALL,
                            description=(
                                f"{stype.name.replace('_', ' ').title()} "
                                f"{field.replace('_', ' ')} "
                                f"slot {slot + 1}, {day.title()}."
                            ),
                        ),
                    )
    return tuple(regs)


SCHEDULE_REGISTERS: tuple[HoldingRegisterDefinition, ...] = _generate_schedule_registers()

SCHEDULE_BY_ADDRESS: dict[int, HoldingRegisterDefinition] = {
    r.address: r for r in SCHEDULE_REGISTERS
}
SCHEDULE_BY_NAME: dict[str, HoldingRegisterDefinition] = {
    r.canonical_name: r for r in SCHEDULE_REGISTERS
}
SCHEDULE_BY_API_KEY: dict[str, HoldingRegisterDefinition] = {
    r.api_param_key: r for r in SCHEDULE_REGISTERS
}
