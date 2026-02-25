"""Canonical Modbus register maps for all device types.

This package is the single source of truth for register definitions.
Each module covers one device type / register category:

- inverter_input: Inverter input registers (function code 0x04, read-only)
- inverter_holding: Inverter holding registers (function code 0x03, read/write)
- battery: Individual battery module registers (5000+ range, INPUT 0x04)
- gridboss: GridBOSS/MID device registers (INPUT 0x04)
"""

from pylxpweb.registers.battery import (
    BATTERY_BASE_ADDRESS,
    BATTERY_MAX_COUNT,
    BATTERY_REGISTER_COUNT,
    BATTERY_REGISTERS,
    BatteryCategory,
    BatteryRegisterDefinition,
    absolute_address,
    sensor_key_registers,
)
from pylxpweb.registers.battery import (
    BY_CATEGORY as BATTERY_BY_CATEGORY,
)
from pylxpweb.registers.battery import (
    BY_CLOUD_FIELD as BATTERY_BY_CLOUD_FIELD,
)
from pylxpweb.registers.battery import (
    BY_NAME as BATTERY_BY_NAME,
)
from pylxpweb.registers.battery import (
    BY_OFFSET as BATTERY_BY_OFFSET,
)
from pylxpweb.registers.battery import (
    BY_SENSOR_KEY as BATTERY_BY_SENSOR_KEY,
)
from pylxpweb.registers.battery import (
    CLOUD_ONLY_SENSOR_KEYS as BATTERY_CLOUD_ONLY_KEYS,
)
from pylxpweb.registers.battery import (
    COMPUTED_SENSOR_KEYS as BATTERY_COMPUTED_KEYS,
)
from pylxpweb.registers.battery import (
    all_ha_sensor_keys as battery_all_ha_sensor_keys,
)
from pylxpweb.registers.gridboss import (
    BY_ADDRESS as GRIDBOSS_BY_ADDRESS,
)
from pylxpweb.registers.gridboss import (
    BY_CATEGORY as GRIDBOSS_BY_CATEGORY,
)
from pylxpweb.registers.gridboss import (
    BY_CLOUD_FIELD as GRIDBOSS_BY_CLOUD_FIELD,
)
from pylxpweb.registers.gridboss import (
    BY_NAME as GRIDBOSS_BY_NAME,
)
from pylxpweb.registers.gridboss import (
    BY_SENSOR_KEY as GRIDBOSS_BY_SENSOR_KEY,
)
from pylxpweb.registers.gridboss import (
    CLOUD_ONLY_SENSOR_KEYS as GRIDBOSS_CLOUD_ONLY_KEYS,
)
from pylxpweb.registers.gridboss import (
    COMPUTED_SENSOR_KEYS as GRIDBOSS_COMPUTED_KEYS,
)
from pylxpweb.registers.gridboss import (
    GRIDBOSS_REGISTERS,
    GridBossCategory,
    GridBossRegisterDefinition,
    energy_registers,
    runtime_registers,
)
from pylxpweb.registers.gridboss import (
    all_ha_sensor_keys as gridboss_all_ha_sensor_keys,
)
from pylxpweb.registers.inverter_holding import (
    BY_ADDRESS as HOLDING_BY_ADDRESS,
)
from pylxpweb.registers.inverter_holding import (
    BY_API_KEY as HOLDING_BY_API_KEY,
)
from pylxpweb.registers.inverter_holding import (
    BY_CATEGORY as HOLDING_BY_CATEGORY,
)
from pylxpweb.registers.inverter_holding import (
    BY_ENTITY_KEY as HOLDING_BY_ENTITY_KEY,
)
from pylxpweb.registers.inverter_holding import (
    BY_NAME as HOLDING_BY_NAME,
)
from pylxpweb.registers.inverter_holding import (
    INVERTER_HOLDING_REGISTERS,
    HoldingCategory,
    HoldingRegisterDefinition,
    bitfield_entries_for_address,
    bitfield_registers,
    entity_keys_for_model,
    value_registers,
)
from pylxpweb.registers.inverter_holding import (
    registers_for_model as holding_registers_for_model,
)
from pylxpweb.registers.inverter_input import (
    ALL,
    BY_ADDRESS,
    BY_CATEGORY,
    BY_CLOUD_FIELD,
    BY_NAME,
    BY_SENSOR_KEY,
    EG4,
    INVERTER_INPUT_REGISTERS,
    LXP_ONLY,
    RegisterCategory,
    RegisterDefinition,
    ScaleFactor,
    registers_for_model,
    sensor_keys_for_model,
)
from pylxpweb.registers.scheduling import (
    SCHEDULE_BY_ADDRESS,
    SCHEDULE_BY_API_KEY,
    SCHEDULE_BY_NAME,
    SCHEDULE_REGISTERS,
    SCHEDULE_TYPES,
    ScheduleTypeConfig,
)

__all__ = [
    # Shared types
    "ALL",
    "EG4",
    "LXP_ONLY",
    "ScaleFactor",
    # Input registers
    "BY_ADDRESS",
    "BY_CATEGORY",
    "BY_CLOUD_FIELD",
    "BY_NAME",
    "BY_SENSOR_KEY",
    "INVERTER_INPUT_REGISTERS",
    "RegisterCategory",
    "RegisterDefinition",
    "registers_for_model",
    "sensor_keys_for_model",
    # Holding registers
    "HOLDING_BY_ADDRESS",
    "HOLDING_BY_API_KEY",
    "HOLDING_BY_CATEGORY",
    "HOLDING_BY_ENTITY_KEY",
    "HOLDING_BY_NAME",
    "INVERTER_HOLDING_REGISTERS",
    "HoldingCategory",
    "HoldingRegisterDefinition",
    "bitfield_entries_for_address",
    "bitfield_registers",
    "entity_keys_for_model",
    "holding_registers_for_model",
    "value_registers",
    # Battery registers
    "BATTERY_BASE_ADDRESS",
    "BATTERY_BY_CATEGORY",
    "BATTERY_BY_CLOUD_FIELD",
    "BATTERY_BY_NAME",
    "BATTERY_BY_OFFSET",
    "BATTERY_BY_SENSOR_KEY",
    "BATTERY_CLOUD_ONLY_KEYS",
    "BATTERY_COMPUTED_KEYS",
    "BATTERY_MAX_COUNT",
    "BATTERY_REGISTER_COUNT",
    "BATTERY_REGISTERS",
    "BatteryCategory",
    "BatteryRegisterDefinition",
    "absolute_address",
    "battery_all_ha_sensor_keys",
    "sensor_key_registers",
    # GridBOSS registers
    "GRIDBOSS_BY_ADDRESS",
    "GRIDBOSS_BY_CATEGORY",
    "GRIDBOSS_BY_CLOUD_FIELD",
    "GRIDBOSS_BY_NAME",
    "GRIDBOSS_BY_SENSOR_KEY",
    "GRIDBOSS_CLOUD_ONLY_KEYS",
    "GRIDBOSS_COMPUTED_KEYS",
    "GRIDBOSS_REGISTERS",
    "GridBossCategory",
    "GridBossRegisterDefinition",
    "energy_registers",
    "gridboss_all_ha_sensor_keys",
    "runtime_registers",
    # Scheduling registers
    "SCHEDULE_BY_ADDRESS",
    "SCHEDULE_BY_API_KEY",
    "SCHEDULE_BY_NAME",
    "SCHEDULE_REGISTERS",
    "SCHEDULE_TYPES",
    "ScheduleTypeConfig",
]
