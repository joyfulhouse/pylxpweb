# Register Map Table Example

This file demonstrates how the register map tables render in markdown.

## Single Register

Single-register parameters appear with just the register number:

| Register | Start | Length | Parameters | Sample Values |
|----------|-------|--------|------------|---------------|
| 15 | 15 | 1 | `HOLD_COM_ADDR` | "1" |
| 16 | 16 | 1 | `HOLD_LANGUAGE` | "1" |
| 20 | 20 | 1 | `HOLD_PV_INPUT_MODE` | "4" |

## Multi-Register Block

Multi-register blocks show the range (start-end):

| Register | Start | Length | Parameters | Sample Values |
|----------|-------|--------|------------|---------------|
| 2-6 | 2 | 5 | `HOLD_SERIAL_NUM` | "1234567890" |
| 7-10 | 7 | 4 | `HOLD_FW_CODE` | "fAAB-2525" |

## Multiple Parameters Register

Registers with multiple parameters use `<br>` tags to create line breaks within cells:

| Register | Start | Length | Parameters | Sample Values |
|----------|-------|--------|------------|---------------|
| 0 | 0 | 2 | `HOLD_MODEL`<br>`HOLD_MODEL_batteryType`<br>`HOLD_MODEL_lithiumType` | "0x986C0"<br>2<br>1 |
| 17 | 17 | 3 | `BIT_DEVICE_TYPE_ODM`<br>`BIT_MACHINE_TYPE`<br>`HOLD_DEVICE_TYPE_CODE` | 4<br>0<br>"2092" |

## Large Multi-Parameter Register

Some registers contain many parameters (e.g., bit fields):

| Register | Start | Length | Parameters | Sample Values |
|----------|-------|--------|------------|---------------|
| 21 | 21 | 1 | `FUNC_EPS_EN`<br>`FUNC_AC_CHARGE`<br>`FUNC_DRMS_EN`<br>`FUNC_ANTI_ISLAND_EN`<br>`FUNC_FEED_IN_GRID_EN` | True<br>True<br>True<br>True<br>True |

## Empty Registers

When boundary validation detects leading empty registers, they're shown as separate rows:

| Register | Start | Length | Parameters | Sample Values |
|----------|-------|--------|------------|---------------|
| 11 | 11 | 1 | `<EMPTY>` | - |
| 12-14 | 12 | 3 | `HOLD_TIME` | "2025-11-18 20:56:25" |
| 17-18 | 17 | 2 | `<EMPTY>` | - |
| 19 | 19 | 1 | `BIT_DEVICE_TYPE_ODM`<br>`BIT_MACHINE_TYPE`<br>`HOLD_DEVICE_TYPE_CODE` | 4<br>0<br>"2092" |

**Explanation**:
- Register 11 is empty, then registers 12-14 contain the `HOLD_TIME` parameter
- Registers 17-18 are empty, then register 19 contains device type information
- Empty registers are explicitly shown so you can see the complete register map

## Benefits of This Format

1. **Compact**: One row per register block instead of one row per parameter
2. **Complete**: Empty registers are explicitly shown
3. **Scannable**: Easy to see register addresses at a glance
4. **Aligned**: Parameters and values line up vertically within cells
5. **Accurate**: Uses boundary validation to show true data locations

## How It Works

The `<br>` tag is HTML that works in markdown tables to create line breaks within cells. Most markdown renderers (GitHub, GitLab, VS Code, etc.) properly render these as multi-line cells.

This gives the effect of "merged cells" where the Register, Start, and Length columns span multiple logical rows of parameters.
