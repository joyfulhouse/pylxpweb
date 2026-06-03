# pylxpweb Documentation

Welcome to the **pylxpweb** documentation. This directory contains comprehensive
documentation for the Luxpower/EG4 inverter Python API client library.

## User Guides

- **[Usage Guide](USAGE_GUIDE.md)** — Object hierarchy, station/device management,
  inverters, batteries, GridBOSS, control operations, caching, error handling.
- **[Property Reference](PROPERTY_REFERENCE.md)** — All device properties with
  scaling, types, and descriptions (~150 properties across all device types).
- **[Scaling Guide](SCALING_GUIDE.md)** — Voltage, current, frequency, power, and
  energy scaling factors; examples and conversion tables.
- **[Parameter Reference](PARAMETER_REFERENCE.md)** — Hold/input register definitions
  and control function parameters.
- **[Device Types](DEVICE_TYPES.md)** — Supported inverter families, GridBOSS, and
  battery module types.
- **[Battery RS485 Protocols](BATTERY_RS485_PROTOCOLS.md)** — Direct RS485 battery
  communication protocol details.
- **[Collect Device Data](COLLECT_DEVICE_DATA.md)** — Guide for capturing live API
  sample data for testing and diagnostics.

## API Documentation

- **[API Reference](api/LUXPOWER_API.md)** — Complete endpoint catalog, authentication,
  session management, error codes, and data scaling reference.
- **[OpenAPI Specification](luxpower-api.yaml)** — OpenAPI 3.0 spec for the Luxpower
  web API.
- **[GridBOSS Firmware Addendum](gridboss-firmware-addendum.yaml)** — Additional
  endpoints from GridBOSS firmware analysis.
- **[LSP API Addendum](lsp-api-addendum.yaml)** — Additional LSP-variant endpoints.

## Device Data Samples

The `inverters/` directory contains real-world device data used for testing and
reference. The `samples/` directory contains API response samples.

## Internal / Process Artifacts

Development notes, session logs, investigation reports, and design documents live in
`docs/claude/` and are not user-facing.

## Quick Start

1. **[README.md](../README.md)** — Installation and quick-start examples.
2. **[Usage Guide](USAGE_GUIDE.md)** — Comprehensive usage documentation.
3. **[Property Reference](PROPERTY_REFERENCE.md)** — All available device properties.
4. **[API Reference](api/LUXPOWER_API.md)** — Low-level endpoint details.
