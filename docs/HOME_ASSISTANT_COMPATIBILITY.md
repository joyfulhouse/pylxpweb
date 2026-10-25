# Home Assistant and optional Modbus dependencies

Install `pylxpweb[modbus-connection]` for TCP and serial transports using the
optional backend. This extra does not install aioesphomeapi. Install
`pylxpweb[esphome]` for `esphome://` ports; it includes the Modbus backend and
serialx's ESPHome dependencies. Existing ESPHome users must select this extra
when upgrading. Backend selection remains automatic for ESPHome URLs.

## Released Home Assistant versions

Releases starting with 0.10.0b14 support Home Assistant 2026.10.0 and newer. Older HA versions
are no longer part of the compatibility matrix. Library 0.10.0b13 and integration
3.5.1-beta.20 retain their published requirements; upgrade HA before moving
to later integration releases. Standalone Python 3.13 support is unchanged.

The CI matrix fetches each release's actual `package_constraints.txt`, Modbus
integration manifest, and the aioesphomeapi requirement from the ESPHome
manifest. It co-installs Home Assistant and pylxpweb under those constraints,
checks the installed dependency graph, and runs the transport tests on Python
3.14 (these HA releases require Python >=3.14.2).

| HA release | serialx | pymodbus | modbus-connection | tmodbus | aioesphomeapi |
| --- | --- | --- | --- | --- | --- |
| 2026.10.0 | 1.11.0 | 3.13.1 | 4.12.3 | 0.6.2 | 46.6.0 |
| 2026.10.4 | 1.11.0 | 3.13.1 | 4.12.4 | 0.6.2 | 46.6.0 |

The 2026.10.0 row was verified against released sources on 2026-10-20;
the current stable 2026.10.4 row was verified on 2026-10-25. serialx 1.8.2 declares an
ESPHome minimum of aioesphomeapi 44.17.0; 1.9.0 and 1.10.0 require 46.0.0;
1.11.0 requires 46.5.0. These are version-specific upstream requirements,
not one universal aioesphomeapi floor. HA's corresponding pins satisfy them.
The earlier changelog's version-specific floors remain correct.

## Host-owned units

Home Assistant 2026.9+ exposes `async_get_unit` as a synchronous callback;
do not await it. Acquire a unit once during entry setup and pass it to the
transport. Home Assistant registers its release callback on the config entry.

```python
from homeassistant.components.modbus import async_get_unit
from modbus_connection import ModbusTcpParams
from pylxpweb.transports.modbus import ModbusTransport

unit = async_get_unit(hass, entry, ModbusTcpParams(host=host, port=502), unit_id)
transport = ModbusTransport(host=host, port=502, serial=serial, unit=unit)
await transport.connect()
```

Transport connect does not dial a borrowed unit. Reads open the host's link
lazily; transport disconnect leaves it available to other consumers. The last
Home Assistant entry unload closes the connection. The installed-HA CI test
calls the real `async_get_unit`, uses a loopback Modbus server, and verifies
this lifecycle with two consumers on every supported HA matrix row.

These tests establish dependency and API compatibility. They do not validate
a specific physical gateway's transaction-ID behavior or firmware.
