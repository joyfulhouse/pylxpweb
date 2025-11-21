# Register Map Documentation

This directory contains human-readable register map documentation for various Luxpower/EG4 inverter models.

## Available Register Maps

### 18KPV (LXP 18K-Hybrid Gen4)
- **File**: [`18KPV_example.md`](18KPV_example.md)
- **Device Type**: 18KPV
- **Serial Number**: 1234567890 (Example)
- **Register Ranges**: 0-274
- **Total Parameters**: 488
- **Total Register Blocks**: 209

### GridBoss (Grid Boss 18K-Hybrid)
- **File**: [`GridBoss_example.md`](GridBoss_example.md)
- **Device Type**: Grid Boss
- **Serial Number**: 0987654321 (Example)
- **Register Ranges**: 0-380, 2032-2158
- **Total Parameters**: 579
- **Total Register Blocks**: 241

> **Note**: These are sanitized example register maps with generic serial numbers and sample values.
> They are provided for documentation and reference purposes only.
> To generate register maps for your own devices, use the utilities described in the "Generating Register Maps" section below.

## Table Format

Each register map follows the same format:

| Column | Description |
|--------|-------------|
| **Register** | The register address or range (e.g., `15` or `12-14`) |
| **Start** | Starting address where data actually begins |
| **Length** | Number of registers containing data |
| **Parameters** | Parameter name(s) - multiple params separated by `<br>` |
| **Sample Values** | Example value(s) from the device - aligned with parameters |

### Special Notations

- **Single register**: Shown as just the number (e.g., `15`)
- **Register range**: Shown as `start-end` (e.g., `12-14` for a 3-register block)
- **Empty registers**: Shown as separate rows with `<EMPTY>` parameter
  - Single empty: `| 11 | 11 | 1 | <EMPTY> | - |`
  - Multiple empty: `| 17-18 | 17 | 2 | <EMPTY> | - |`
  - These appear before the actual data row for that block

For registers with multiple parameters, all parameters are listed in a single row using `<br>` tags for line breaks within the table cells.

## Metadata

Each file includes comprehensive metadata:
- Discovery timestamp
- Device serial number and type
- Base API URL used
- Input register ranges scanned
- Statistics (total blocks, parameters, etc.)

## Usage

These markdown files are ideal for:
- Understanding device register layouts
- Planning parameter read/write operations
- Comparing register maps across device types
- API client development reference
- Home Assistant integration development

## Generating Register Maps

To generate new register maps:

1. **Discover registers** (produces JSON):
   ```bash
   uv run python utils/map_registers.py -s <serial> -r <start>,<length>
   ```

2. **Convert to markdown** (produces MD):
   ```bash
   python3 utils/json_to_markdown.py <input.json> <output.md>
   ```

See [`../../utils/README.md`](../../utils/README.md) for detailed instructions.

## Contributing

To contribute register maps for new device types:
1. Run the register mapper on your device
2. Generate the markdown documentation
3. Submit a pull request with both JSON and MD files
4. Include device model and firmware version

## Notes

- Sample values are from live devices and may vary by configuration
- Register maps may change with firmware updates
- Some parameters may be read-only or require specific conditions to modify
- GridBoss devices have additional register ranges (2032+) for smart load management

## Related Documentation

- [API Documentation](../api/LUXPOWER_API.md) - Luxpower API reference
- [Utilities](../../utils/README.md) - Register mapping tools
- [Parameter Mapping](../api/PARAMETER_MAPPING.md) - Parameter ID reference
