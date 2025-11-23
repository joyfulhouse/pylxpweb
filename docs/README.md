# pylxpweb Documentation

Welcome to the **pylxpweb** documentation. This directory contains comprehensive documentation for the Luxpower/EG4 inverter Python API client library.

## Documentation Structure

### API Documentation
- **[Luxpower API Reference](api/LUXPOWER_API.md)** - Complete API endpoint documentation
  - Authentication and session management
  - Station/plant management
  - Device discovery
  - Runtime data retrieval
  - Energy statistics
  - Battery information
  - GridBOSS/MID device operations
  - Control operations
  - Data scaling reference
  - Error handling and retry strategies

### User Guides
- **[Usage Guide](USAGE_GUIDE.md)** - Comprehensive usage guide with examples
  - Object hierarchy overview
  - Station and device management
  - Working with inverters, batteries, and GridBOSS devices
  - Control operations
  - Caching and performance optimization
  - Error handling best practices

- **[Property Reference](PROPERTY_REFERENCE.md)** - Complete property reference for all device types
  - Inverter properties (~40 properties)
  - MID device properties (~50 properties)
  - Battery properties (~20 properties)
  - BatteryBank properties (~10 properties)
  - ParallelGroup properties (~12 properties)
  - All properties with scaling, types, and descriptions

- **[Scaling Guide](SCALING_GUIDE.md)** - Data scaling reference
  - Voltage, current, frequency, power, energy scaling
  - Different scaling factors for different data types
  - Examples and conversion tables
  - Best practices for using device properties vs raw API

- **[Parameter Reference](PARAMETER_REFERENCE.md)** - Complete parameter catalog
  - Hold register definitions
  - Input register definitions
  - Control function parameters
  - Register ranges and mappings

### Architecture Documentation
*Coming soon*
- System design and patterns
- Authentication flow diagrams
- Data model documentation
- Caching strategies

### Examples
*Coming soon*
- Basic usage examples
- Advanced integration patterns
- Home Assistant integration guide
- Error handling examples

## Quick Start

For getting started with the pylxpweb library, see:
1. Project README.md (root) - Installation and quick start examples
2. [Usage Guide](USAGE_GUIDE.md) - Comprehensive usage documentation
3. [Property Reference](PROPERTY_REFERENCE.md) - All available device properties
4. [Luxpower API Reference](api/LUXPOWER_API.md) - Low-level API details

## Research Materials

The `research/` directory at the project root contains reference implementations:
- **eg4_web_monitor/** - Production-quality Home Assistant integration
- **eg4_inverter_ha/** - Earlier implementation for comparison

**IMPORTANT**: Research materials are for reference only and should not be imported or used in production code.

## Contributing to Documentation

When adding new documentation:
1. Choose the appropriate category (api/, architecture/, examples/)
2. Use clear, descriptive filenames in UPPER_CASE.md format
3. Update this README.md index
4. Cross-reference related documentation
5. Include code examples where applicable
6. Document any API findings with evidence from sample responses

## Documentation Status

- ✅ **API Reference** - Complete comprehensive documentation
- ✅ **User Guides** - Complete (Usage Guide, Property Reference, Scaling Guide, Parameter Reference)
- ⏳ **Architecture** - To be created
- ⏳ **Examples** - To be created

## Additional Resources

- [CLAUDE.md](../CLAUDE.md) - Project guidelines for Claude Code
- [CHANGELOG.md](../CHANGELOG.md) - Version history and release notes
- Research Materials: `research/eg4_web_monitor/` - Reference implementation
- Sample API Responses: `research/eg4_web_monitor/.../samples/` - Real API data

---

Last Updated: 2025-11-22 (v0.3.5)
