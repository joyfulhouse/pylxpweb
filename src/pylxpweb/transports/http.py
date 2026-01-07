"""HTTP transport implementation.

This module provides the HTTPTransport class that wraps the existing
LuxpowerClient for cloud API communication.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pylxpweb.exceptions import (
    LuxpowerAPIError,
    LuxpowerAuthError,
    LuxpowerConnectionError,
    LuxpowerDeviceError,
)

from .capabilities import HTTP_CAPABILITIES, TransportCapabilities
from .data import BatteryBankData, BatteryData, InverterEnergyData, InverterRuntimeData
from .exceptions import (
    TransportConnectionError,
    TransportReadError,
    TransportTimeoutError,
    TransportWriteError,
)
from .protocol import BaseTransport

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient

_LOGGER = logging.getLogger(__name__)


class HTTPTransport(BaseTransport):
    """HTTP transport using cloud API via LuxpowerClient.

    This transport wraps the existing LuxpowerClient to provide
    the standard InverterTransport interface.

    Example:
        async with LuxpowerClient(username, password) as client:
            transport = HTTPTransport(client, serial="CE12345678")
            await transport.connect()

            runtime = await transport.read_runtime()
            print(f"PV Power: {runtime.pv_total_power}W")
    """

    def __init__(self, client: LuxpowerClient, serial: str) -> None:
        """Initialize HTTP transport.

        Args:
            client: Connected LuxpowerClient instance
            serial: Inverter serial number
        """
        super().__init__(serial)
        self._client = client

    @property
    def capabilities(self) -> TransportCapabilities:
        """Get HTTP transport capabilities."""
        return HTTP_CAPABILITIES

    async def connect(self) -> None:
        """Verify connection to cloud API.

        The LuxpowerClient handles actual authentication.
        This method ensures the client session is valid.

        Raises:
            TransportConnectionError: If client not authenticated
        """
        try:
            # Ensure client is authenticated - login() handles session management
            await self._client.login()
        except LuxpowerAuthError as err:
            _LOGGER.error("Authentication failed for %s: %s", self._serial, err)
            raise TransportConnectionError(f"Authentication failed for cloud API: {err}") from err
        except (TimeoutError, LuxpowerConnectionError, OSError) as err:
            _LOGGER.error("Connection failed for %s: %s", self._serial, err)
            raise TransportConnectionError(f"Failed to connect to cloud API: {err}") from err

        self._connected = True
        _LOGGER.debug("HTTP transport connected for %s", self._serial)

    async def disconnect(self) -> None:
        """Mark transport as disconnected.

        Note: Does not close the LuxpowerClient session, as it may be
        shared across multiple transports.
        """
        self._connected = False
        _LOGGER.debug("HTTP transport disconnected for %s", self._serial)

    async def read_runtime(self) -> InverterRuntimeData:
        """Read runtime data via HTTP API.

        Returns:
            Runtime data with all values properly scaled

        Raises:
            TransportReadError: If API call fails
            TransportTimeoutError: If request times out
        """
        self._ensure_connected()

        try:
            runtime = await self._client.api.devices.get_inverter_runtime(self._serial)
            return InverterRuntimeData.from_http_response(runtime)
        except TimeoutError as err:
            _LOGGER.error("Timeout reading runtime data for %s", self._serial)
            raise TransportTimeoutError(f"Timeout reading runtime data for {self._serial}") from err
        except (LuxpowerAPIError, LuxpowerDeviceError, LuxpowerConnectionError) as err:
            _LOGGER.error("Failed to read runtime data for %s: %s", self._serial, err)
            raise TransportReadError(
                f"Failed to read runtime data for {self._serial}: {err}"
            ) from err

    async def read_energy(self) -> InverterEnergyData:
        """Read energy statistics via HTTP API.

        Returns:
            Energy data with all values in kWh

        Raises:
            TransportReadError: If API call fails
            TransportTimeoutError: If request times out
        """
        self._ensure_connected()

        try:
            energy = await self._client.api.devices.get_inverter_energy(self._serial)
            return InverterEnergyData.from_http_response(energy)
        except TimeoutError as err:
            _LOGGER.error("Timeout reading energy data for %s", self._serial)
            raise TransportTimeoutError(f"Timeout reading energy data for {self._serial}") from err
        except (LuxpowerAPIError, LuxpowerDeviceError, LuxpowerConnectionError) as err:
            _LOGGER.error("Failed to read energy data for %s: %s", self._serial, err)
            raise TransportReadError(
                f"Failed to read energy data for {self._serial}: {err}"
            ) from err

    async def read_battery(self) -> BatteryBankData | None:
        """Read battery information via HTTP API.

        Returns:
            Battery bank data if batteries present, None otherwise

        Raises:
            TransportReadError: If API call fails
        """
        self._ensure_connected()

        try:
            battery_info = await self._client.api.devices.get_battery_info(self._serial)

            if battery_info is None:
                return None

            # Import scaling here to avoid circular imports
            from pylxpweb.constants.scaling import ScaleFactor, apply_scale

            # Build individual battery data from batteryArray
            batteries: list[BatteryData] = []
            if battery_info.batteryArray:
                for bat in battery_info.batteryArray:
                    # BatteryModule fields: batIndex, batterySn, totalVoltage, current, etc.
                    batteries.append(
                        BatteryData(
                            battery_index=bat.batIndex,
                            serial_number=bat.batterySn or "",
                            # totalVoltage needs /100 scaling
                            voltage=apply_scale(bat.totalVoltage, ScaleFactor.SCALE_100),
                            # current needs /10 scaling (not /100!)
                            current=apply_scale(bat.current, ScaleFactor.SCALE_10),
                            soc=bat.soc or 0,
                            soh=bat.soh or 100,
                            # Temperatures: batMaxCellTemp/batMinCellTemp are /10
                            temperature=apply_scale(bat.batMaxCellTemp, ScaleFactor.SCALE_10),
                            max_capacity=float(bat.currentFullCapacity or 0),
                            current_capacity=float(bat.currentRemainCapacity or 0),
                            cycle_count=bat.cycleCnt or 0,
                            # Cell voltage extremes: /1000 scaling
                            min_cell_voltage=apply_scale(
                                bat.batMinCellVoltage, ScaleFactor.SCALE_1000
                            ),
                            max_cell_voltage=apply_scale(
                                bat.batMaxCellVoltage, ScaleFactor.SCALE_1000
                            ),
                            # BatteryModule doesn't have status/fault/warning codes
                        )
                    )

            # Build aggregate bank data from BatteryInfo header
            # BatteryInfo fields: vBat (/10), soc, pCharge, pDisCharge, etc.
            return BatteryBankData(
                voltage=apply_scale(battery_info.vBat, ScaleFactor.SCALE_10),
                soc=battery_info.soc or 0,
                charge_power=float(battery_info.pCharge or 0),
                discharge_power=float(battery_info.pDisCharge or 0),
                max_capacity=float(battery_info.maxBatteryCharge or 0),
                current_capacity=float(battery_info.currentBatteryCharge or 0),
                battery_count=battery_info.totalNumber or len(batteries),
                batteries=batteries,
                # Note: BatteryInfo doesn't have soh, temperature, current, status codes
            )

        except TimeoutError as err:
            _LOGGER.error("Timeout reading battery data for %s", self._serial)
            raise TransportTimeoutError(f"Timeout reading battery data for {self._serial}") from err
        except (LuxpowerAPIError, LuxpowerDeviceError, LuxpowerConnectionError) as err:
            _LOGGER.error("Failed to read battery data for %s: %s", self._serial, err)
            raise TransportReadError(
                f"Failed to read battery data for {self._serial}: {err}"
            ) from err

    async def read_parameters(
        self,
        start_address: int,
        count: int,
    ) -> dict[int, int]:
        """Read configuration parameters via HTTP API.

        Args:
            start_address: Starting register address
            count: Number of registers to read (max 127)

        Returns:
            Dict mapping register address to raw integer value

        Raises:
            TransportReadError: If API call fails
            TransportTimeoutError: If request times out
        """
        self._ensure_connected()

        try:
            response = await self._client.api.control.read_parameters(
                self._serial,
                start_register=start_address,
                point_number=min(count, 127),  # API limit
            )

            # ParameterReadResponse has a .parameters property that extracts
            # the register values as a dict (excluding metadata fields)
            params = response.parameters

            # Convert response to address -> value dict
            # The API returns parameter names, we need to map back to addresses
            result: dict[int, int] = {}
            for key, value in params.items():
                try:
                    # Try to extract register address from various formats
                    if isinstance(value, int):
                        # Value is the register value, key might be the address
                        if key.isdigit():
                            result[int(key)] = value
                        else:
                            # Key is parameter name, need reverse lookup
                            # For now, skip named parameters (they need mapping)
                            _LOGGER.debug(
                                "Skipping named parameter %s=%s (address lookup not implemented)",
                                key,
                                value,
                            )
                    elif isinstance(value, (str, float)) and key.isdigit():
                        result[int(key)] = int(float(value))
                    else:
                        _LOGGER.debug(
                            "Skipping parameter with unexpected format: key=%s, value=%s (type=%s)",
                            key,
                            value,
                            type(value).__name__,
                        )
                except (ValueError, TypeError) as err:
                    _LOGGER.warning(
                        "Failed to parse parameter %s=%s: %s",
                        key,
                        value,
                        err,
                    )
                    continue

            return result

        except TimeoutError as err:
            _LOGGER.error("Timeout reading parameters for %s", self._serial)
            raise TransportTimeoutError(f"Timeout reading parameters for {self._serial}") from err
        except (LuxpowerAPIError, LuxpowerDeviceError, LuxpowerConnectionError) as err:
            _LOGGER.error("Failed to read parameters for %s: %s", self._serial, err)
            raise TransportReadError(
                f"Failed to read parameters for {self._serial}: {err}"
            ) from err

    async def write_parameters(
        self,
        parameters: dict[int, int],
    ) -> bool:
        """Write configuration parameters via HTTP API.

        Args:
            parameters: Dict mapping register address to value to write

        Returns:
            True if write succeeded

        Raises:
            TransportWriteError: If API call fails
            TransportTimeoutError: If request times out
        """
        self._ensure_connected()

        try:
            # Use the batch write_parameters method which takes dict[int, int]
            await self._client.api.control.write_parameters(
                self._serial,
                parameters=parameters,
            )
            return True

        except TimeoutError as err:
            _LOGGER.error("Timeout writing parameters for %s", self._serial)
            raise TransportTimeoutError(f"Timeout writing parameters for {self._serial}") from err
        except (LuxpowerAPIError, LuxpowerDeviceError, LuxpowerConnectionError) as err:
            _LOGGER.error("Failed to write parameters for %s: %s", self._serial, err)
            raise TransportWriteError(
                f"Failed to write parameters for {self._serial}: {err}"
            ) from err
