# Diagnostic Samples

This directory contains diagnostic data from various Luxpower/EG4 inverter configurations to help identify device capabilities, parameter registers, and API variations across different hardware.

## Purpose

Collecting diagnostic samples from different inverter models, firmware versions, and configurations helps us:

1. **Map Parameter Registers** - Identify which registers are available for each inverter model
2. **Understand Device Capabilities** - Document what functions, controls, and data points each model supports
3. **API Endpoint Coverage** - Discover regional API differences and endpoint variations
4. **Improve Compatibility** - Ensure pylxpweb works correctly across all hardware variants
5. **Support Development** - Provide test data for features we cannot physically test

## Current Samples

### EG4_18KPV_with_GridBOSS_diagnostic.json

**Configuration:**
- **Base URL**: `https://monitor.eg4electronics.com` (EG4 Electronics - North America)
- **Inverter Model**: EG4 18KPV (GenericInverter)
- **MID Device**: GridBOSS (4524850115)
- **Battery Bank**: 3 battery modules
- **Parameter Ranges**: 367 registers (0-126, 127-253, 240-366)
- **Features**: Parallel group with single inverter + GridBOSS

**Key Data Collected:**
- 74 runtime data fields
- 15 energy statistic fields
- 14 battery attributes per module (temperature, voltage, SoC, SoH, etc.)
- Complete parameter register mapping

## Contributing Your Diagnostic Data

We welcome diagnostic samples from all users! Your contribution helps improve pylxpweb for everyone.

### How to Contribute

1. **Run the diagnostic tool:**
   ```bash
   # Install pylxpweb
   pip install pylxpweb

   # Or from source
   cd pylxpweb
   pip install -e .

   # Run diagnostic collection (sanitizes sensitive data by default)
   python -m utils.collect_diagnostics --username YOUR_USERNAME --password YOUR_PASSWORD
   ```

2. **Review the output file:**
   - Default filename: `diagnostics_YYYYMMDD_HHMMSS.json`
   - Verify serial numbers are masked (e.g., `45****15`)
   - Verify addresses are sanitized
   - Check that no personally identifiable information is exposed

3. **Rename the file descriptively:**
   ```
   Format: {Brand}_{Model}_{Configuration}_diagnostic.json

   Examples:
   - EG4_18KPV_standalone_diagnostic.json
   - Luxpower_12K_Hybrid_parallel_2inv_diagnostic.json
   - EG4_6KPV_with_FlexBOSS_diagnostic.json
   ```

4. **Submit via GitHub:**
   - Fork the repository
   - Add your file to `docs/samples/`
   - Create a pull request with:
     - Brief description of your setup
     - Any notable observations or issues
     - Region/country for API endpoint reference

### What Gets Sanitized

The diagnostic tool **automatically sanitizes** sensitive information:

- ✅ **Serial numbers** - Masked to show first/last 2 digits only (e.g., `45****15`)
- ✅ **Street addresses** - Replaced with generic placeholder
- ✅ **GPS coordinates** - Replaced with `0.0`
- ✅ **Plant names with addresses** - Replaced with "Example Station"

### What to Check Before Sharing

Even with automatic sanitization, please review your diagnostic file:

1. **Station names** - If your station name contains personal info, it may not be auto-sanitized
2. **Custom fields** - Any custom labels or notes you added to your system
3. **Location data** - Verify GPS coordinates are `0.0`
4. **Personal patterns** - Check for any identifiable patterns in your data

### Information We're Looking For

Your diagnostic sample is especially valuable if you have:

- **Uncommon inverter models** (LSP, FlexBOSS, older models)
- **Different firmware versions** - Helps identify API changes
- **Regional variations** - EU, Asia-Pacific, other regions
- **Unusual configurations** - Multi-inverter parallel, AC coupling, etc.
- **Different battery chemistries** - LiFePO4, NMC, etc.
- **MID device variations** - GridBOSS, FlexBOSS, other models

## Parameter Register Analysis

One of the most valuable aspects of diagnostic samples is the parameter register data. Each inverter model may have different registers available.

### Example: 18KPV Parameter Ranges

```
Range 1 (0-126):   127 registers - Basic configuration and functions
Range 2 (127-253): 127 registers - Extended parameters
Range 3 (240-366): 127 registers - Advanced settings (overlaps with Range 2)
```

**Key parameters discovered:**
- Register 21: Function enable flags (FUNC_EN_REGISTER)
- Register 105-106: Battery SoC limits
- Register 150: Grid charge enable/disable
- Many more documented in `docs/PARAMETER_REFERENCE.md`

### Using Samples for Development

Developers can use these samples to:

1. **Test without hardware** - Mock API responses using sample data
2. **Validate new features** - Ensure compatibility across models
3. **Document capabilities** - Generate feature matrices
4. **Reverse engineer parameters** - Identify undocumented registers

## Privacy & Security

**Important:** Never share diagnostic files that contain:
- ❌ Unmasked serial numbers (full 10-digit serials)
- ❌ Real street addresses or GPS coordinates
- ❌ Personal identifiable information
- ❌ Custom labels with personal data

If you're unsure, run the tool with default sanitization enabled (don't use `--no-sanitize` flag).

## Sample Data Structure

Each diagnostic file contains:

```json
{
  "collection_timestamp": "2025-11-20T...",
  "pylxpweb_version": "0.2.2",
  "base_url": "https://monitor.eg4electronics.com",
  "stations": [
    {
      "id": 12345,
      "name": "Example Station",
      "location": {
        "lat": 0.0,
        "lng": 0.0,
        "address": "123 Example Street, City, State"
      },
      "parallel_groups": [...],
      "standalone_inverters": [...]
    }
  ]
}
```

### Key Sections

- **stations** - Top-level plant/station data
- **parallel_groups** - Multi-inverter configurations with MID devices
- **inverters** - Individual inverter data (runtime, energy, battery, parameters)
- **battery_bank** - Aggregate battery data + individual module array
- **mid_device** - GridBOSS/FlexBOSS data (if present)
- **parameters** - Complete register mapping (most valuable for development)

## Questions or Issues?

- **GitHub Issues**: https://github.com/joyfulhouse/pylxpweb/issues
- **Documentation**: See main README and `utils/README.md`
- **API Reference**: `docs/api/LUXPOWER_API.md`

## Contributing Guidelines

When submitting diagnostic samples:

1. ✅ Run with default sanitization enabled
2. ✅ Review output before sharing
3. ✅ Use descriptive filenames
4. ✅ Include setup description in PR
5. ✅ Note any unusual behavior or errors
6. ❌ Don't share unsanitized data publicly
7. ❌ Don't commit samples from personal forks to main repo without PR review

Thank you for helping improve pylxpweb! 🎉
