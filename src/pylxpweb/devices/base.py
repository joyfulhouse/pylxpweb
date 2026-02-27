"""Base device classes for pylxpweb.

This module provides abstract base classes for all device types,
implementing common functionality like refresh intervals, caching,
and Home Assistant integration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from pylxpweb.validation import (
    MAX_ENERGY_DELTA,
    validate_daily_energy_bounds,
    validate_energy_monotonicity,
)

from .models import DeviceInfo, Entity

if TYPE_CHECKING:
    from pylxpweb import LuxpowerClient
    from pylxpweb.transports.protocol import InverterTransport


class BaseDevice(ABC):
    """Abstract base class for all device types.

    This class provides common functionality for inverters, batteries,
    MID devices, and stations, including:
    - Refresh interval management with TTL
    - Client reference for API access
    - Home Assistant integration methods

    Subclasses must implement:
    - refresh(): Load/reload device data from API
    - to_device_info(): Convert to device info model
    - to_entities(): Generate entity list

    Example:
        ```python
        class MyDevice(BaseDevice):
            async def refresh(self) -> None:
                data = await self._client.api.devices.get_data(self.serial_number)
                self._process_data(data)
                self._last_refresh = datetime.now()

            def to_device_info(self) -> DeviceInfo:
                return DeviceInfo(
                    identifiers={("pylxpweb", f"device_{self.serial_number}")},
                    name=f"My Device {self.serial_number}",
                    manufacturer="EG4",
                    model=self.model,
                )

            def to_entities(self) -> list[Entity]:
                return [
                    Entity(unique_id=f"{self.serial_number}_power", ...)
                ]
        ```
    """

    def __init__(
        self,
        client: LuxpowerClient,
        serial_number: str,
        model: str,
    ) -> None:
        """Initialize base device.

        Args:
            client: LuxpowerClient instance for API access.  Local-only
                (transport-backed) devices pass ``None`` via
                ``type: ignore[arg-type]`` since they never call cloud API
                methods.
            serial_number: Device serial number (unique identifier)
            model: Device model name
        """
        self._client = client
        self.serial_number = serial_number
        self._model = model
        self._last_refresh: datetime | None = None
        self._refresh_interval = timedelta(seconds=30)

        # Local transport (Modbus/Dongle) - None means HTTP-only mode
        self._local_transport: InverterTransport | None = None

        # Data validation: when True, corrupt transport reads are rejected
        # and the previous cached value is kept instead. Set by coordinator
        # from the CONF_DATA_VALIDATION option.
        self.validate_data: bool = False

        # Energy monotonicity validation counter (consecutive rejections).
        # Shared by BaseInverter and MIDDevice for lifetime energy checks.
        self._energy_reject_count: int = 0

        # Max energy delta (kWh) for spike detection.  Subclasses override
        # with rated_power_kw * 1.5 once device capabilities are known.
        self._max_energy_delta: float = MAX_ENERGY_DELTA

        # Max power (watts) for canary checks.  Zero means "not yet known",
        # so power checks are skipped until detect_features() or
        # set_max_system_power() populates this.  Computed as rated_kw * 2000
        # (2x margin) to catch 0xFFFF (65535W) corrupt register reads.
        self._max_power_watts: float = 0.0

        # Rated power (kW) for daily energy bounds validation.  Set by
        # detect_features() (inverters) or set_max_system_power() (MID).
        # Zero means unknown — validation falls back to DEFAULT_RATED_POWER_KW.
        self._rated_power_kw: float = 0.0

    @property
    def model(self) -> str:
        """Get device model name.

        Returns:
            Device model name, or "Unknown" if not available.
        """
        return self._model if self._model else "Unknown"

    @property
    def needs_refresh(self) -> bool:
        """Check if device data needs refreshing based on TTL.

        Returns:
            True if device has never been refreshed or TTL has expired,
            False if data is still fresh.
        """
        if self._last_refresh is None:
            return True
        return datetime.now() - self._last_refresh > self._refresh_interval

    @property
    def has_local_transport(self) -> bool:
        """Check if device has an attached local transport.

        Returns:
            True if a local transport (Modbus or Dongle) is attached,
            False if only HTTP API is available.
        """
        return self._local_transport is not None

    @property
    def is_local_only(self) -> bool:
        """Check if device is local-only (no HTTP client credentials).

        Returns:
            True if the device was created from local transport without
            cloud API credentials, False otherwise.
        """
        return self._local_transport is not None and not self._client.username

    def _is_energy_valid(
        self,
        prev_values: dict[str, float | None],
        curr_values: dict[str, float | None],
    ) -> bool:
        """Check whether new lifetime energy values pass monotonicity validation.

        Always active — lifetime kWh counters physically cannot decrease,
        so a decrease is always corruption regardless of the validate_data
        toggle.  The validate_data flag controls canary-based is_corrupt()
        checks which can have edge-case false positives; monotonicity
        cannot false-positive.

        Updates ``_energy_reject_count`` as a side-effect.

        Args:
            prev_values: Previous cycle's lifetime energy dict.
            curr_values: Current cycle's lifetime energy dict.

        Returns:
            True if the data should be accepted, False if it should be rejected.
        """
        result, self._energy_reject_count = validate_energy_monotonicity(
            prev_values,
            curr_values,
            self._energy_reject_count,
            self.serial_number,
            max_delta=self._max_energy_delta,
        )
        return result != "reject"

    def _is_daily_energy_valid(
        self,
        curr_values: dict[str, float | None],
        prev_values: dict[str, float | None] | None,
        elapsed_seconds: float | None,
    ) -> bool:
        """Check whether daily energy values are within plausible bounds.

        Delegates to :func:`~pylxpweb.validation.validate_daily_energy_bounds`
        which applies an absolute cap and, when previous data exists, a
        tighter time-based delta check.  Always active (not gated by
        ``validate_data`` toggle).
        """
        return validate_daily_energy_bounds(
            curr_values=curr_values,
            device_id=self.serial_number,
            rated_power_kw=self._rated_power_kw,
            elapsed_seconds=elapsed_seconds,
            prev_values=prev_values,
        )

    @abstractmethod
    async def refresh(self) -> None:
        """Refresh device data from API.

        Subclasses must implement this to load/reload device-specific data.
        Should update self._last_refresh on success.
        """
        ...

    @abstractmethod
    def to_device_info(self) -> DeviceInfo:
        """Convert device to generic device info model.

        Returns:
            DeviceInfo instance with device metadata.
        """
        ...

    @abstractmethod
    def to_entities(self) -> list[Entity]:
        """Generate entities for this device.

        Returns:
            List of Entity instances (sensors, switches, etc.)
        """
        ...
