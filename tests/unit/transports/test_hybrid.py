"""Tests for HybridTransport class."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.transports.data import InverterEnergyData, InverterRuntimeData
from pylxpweb.transports.exceptions import (
    TransportConnectionError,
    TransportReadError,
    TransportTimeoutError,
)
from pylxpweb.transports.hybrid import HybridTransport

if TYPE_CHECKING:
    pass


@pytest.fixture
def mock_local_transport() -> MagicMock:
    """Create mock local transport."""
    transport = MagicMock()
    transport.serial = "CE12345678"
    transport.is_connected = True
    transport.capabilities = MagicMock()
    transport.connect = AsyncMock()
    transport.disconnect = AsyncMock()
    transport.read_runtime = AsyncMock(return_value=InverterRuntimeData(pv_total_power=1000.0))
    transport.read_energy = AsyncMock(return_value=InverterEnergyData(pv_energy_today=5.0))
    transport.read_battery = AsyncMock(return_value=None)
    transport.read_parameters = AsyncMock(return_value={0: 100, 1: 200})
    transport.write_parameters = AsyncMock(return_value=True)
    return transport


@pytest.fixture
def mock_http_transport() -> MagicMock:
    """Create mock HTTP transport."""
    transport = MagicMock()
    transport.serial = "CE12345678"
    transport.is_connected = True
    transport.capabilities = MagicMock()
    transport.connect = AsyncMock()
    transport.disconnect = AsyncMock()
    transport.read_runtime = AsyncMock(
        return_value=InverterRuntimeData(pv_total_power=950.0)  # Slightly different
    )
    transport.read_energy = AsyncMock(return_value=InverterEnergyData(pv_energy_today=4.9))
    transport.read_battery = AsyncMock(return_value=None)
    transport.read_parameters = AsyncMock(return_value={0: 100, 1: 200})
    transport.write_parameters = AsyncMock(return_value=True)
    return transport


class TestHybridTransportInit:
    """Tests for HybridTransport initialization."""

    def test_init_default_values(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test default initialization values."""
        transport = HybridTransport(mock_local_transport, mock_http_transport)

        assert transport._serial == "CE12345678"
        assert transport._local == mock_local_transport
        assert transport._http == mock_http_transport
        assert transport._prefer_local is True
        assert transport._local_retry_interval == 60.0
        assert transport._local_failed_at is None
        assert transport._using_local is True

    def test_init_custom_values(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test custom initialization values."""
        transport = HybridTransport(
            mock_local_transport,
            mock_http_transport,
            prefer_local=False,
            local_retry_interval=120.0,
        )

        assert transport._prefer_local is False
        assert transport._local_retry_interval == 120.0


class TestHybridTransportProperties:
    """Tests for HybridTransport properties."""

    def test_capabilities_returns_local(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test capabilities returns local transport capabilities."""
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        caps = transport.capabilities

        assert caps == mock_local_transport.capabilities

    def test_is_using_local_true_by_default(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test is_using_local is True when no failures."""
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        assert transport.is_using_local is True

    def test_is_using_local_false_when_prefer_local_false(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test is_using_local respects prefer_local setting."""
        transport = HybridTransport(mock_local_transport, mock_http_transport, prefer_local=False)
        assert transport.is_using_local is False

    def test_is_using_local_recovers_after_interval(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test local transport retries after retry interval."""
        transport = HybridTransport(
            mock_local_transport, mock_http_transport, local_retry_interval=0.1
        )
        # Simulate failure
        transport._local_failed_at = time.monotonic() - 0.2  # Failed 0.2s ago
        assert transport.is_using_local is True  # Should retry

    def test_is_using_local_false_before_interval(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test local transport doesn't retry before interval."""
        transport = HybridTransport(
            mock_local_transport, mock_http_transport, local_retry_interval=60.0
        )
        # Simulate recent failure
        transport._local_failed_at = time.monotonic() - 1.0  # Failed 1s ago
        assert transport.is_using_local is False  # Should not retry yet

    def test_local_transport_property(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test local_transport property returns local transport."""
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        assert transport.local_transport is mock_local_transport

    def test_http_transport_property(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test http_transport property returns HTTP transport."""
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        assert transport.http_transport is mock_http_transport


class TestHybridTransportConnect:
    """Tests for HybridTransport connect/disconnect."""

    @pytest.mark.asyncio
    async def test_connect_both_succeed(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test connect succeeds when both transports work."""
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        await transport.connect()

        assert transport.is_connected is True
        assert transport._using_local is True
        mock_http_transport.connect.assert_called_once()
        mock_local_transport.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_local_fails_uses_http(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test connect falls back to HTTP when local fails."""
        mock_local_transport.connect.side_effect = TransportConnectionError("Failed")
        transport = HybridTransport(mock_local_transport, mock_http_transport)

        await transport.connect()

        assert transport.is_connected is True
        assert transport._using_local is False
        assert transport._local_failed_at is not None

    @pytest.mark.asyncio
    async def test_connect_http_fails_raises(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test connect raises when HTTP fails (critical)."""
        mock_http_transport.connect.side_effect = TransportConnectionError("Failed")
        transport = HybridTransport(mock_local_transport, mock_http_transport)

        with pytest.raises(TransportConnectionError):
            await transport.connect()

    @pytest.mark.asyncio
    async def test_disconnect_both(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test disconnect closes both transports."""
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        transport._connected = True

        await transport.disconnect()

        assert transport.is_connected is False
        mock_local_transport.disconnect.assert_called_once()
        mock_http_transport.disconnect.assert_called_once()


class TestHybridTransportReadRuntime:
    """Tests for read_runtime method."""

    @pytest.mark.asyncio
    async def test_read_runtime_uses_local(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test read_runtime uses local transport when available."""
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        transport._connected = True

        result = await transport.read_runtime()

        assert result.pv_total_power == 1000.0  # Local value
        mock_local_transport.read_runtime.assert_called_once()
        mock_http_transport.read_runtime.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_runtime_falls_back_to_http(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test read_runtime falls back to HTTP on local failure."""
        mock_local_transport.read_runtime.side_effect = TransportReadError("Failed")
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        transport._connected = True

        result = await transport.read_runtime()

        assert result.pv_total_power == 950.0  # HTTP value
        mock_local_transport.read_runtime.assert_called_once()
        mock_http_transport.read_runtime.assert_called_once()
        assert transport._local_failed_at is not None

    @pytest.mark.asyncio
    async def test_read_runtime_timeout_falls_back(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test read_runtime falls back on timeout."""
        mock_local_transport.read_runtime.side_effect = TransportTimeoutError("Timeout")
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        transport._connected = True

        result = await transport.read_runtime()

        assert result.pv_total_power == 950.0  # HTTP value

    @pytest.mark.asyncio
    async def test_read_runtime_uses_http_when_local_disabled(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test read_runtime uses HTTP when local failed recently."""
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        transport._connected = True
        transport._using_local = False
        transport._local_failed_at = time.monotonic()

        result = await transport.read_runtime()

        assert result.pv_total_power == 950.0  # HTTP value
        mock_local_transport.read_runtime.assert_not_called()
        mock_http_transport.read_runtime.assert_called_once()


class TestHybridTransportReadEnergy:
    """Tests for read_energy method."""

    @pytest.mark.asyncio
    async def test_read_energy_uses_local(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test read_energy uses local transport."""
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        transport._connected = True

        result = await transport.read_energy()

        assert result.pv_energy_today == 5.0
        mock_local_transport.read_energy.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_energy_falls_back(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test read_energy falls back on failure."""
        mock_local_transport.read_energy.side_effect = TransportReadError("Failed")
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        transport._connected = True

        result = await transport.read_energy()

        assert result.pv_energy_today == 4.9


class TestHybridTransportReadBattery:
    """Tests for read_battery method."""

    @pytest.mark.asyncio
    async def test_read_battery_uses_local(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test read_battery uses local transport."""
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        transport._connected = True

        result = await transport.read_battery()

        assert result is None  # Mock returns None
        mock_local_transport.read_battery.assert_called_once()


class TestHybridTransportReadParameters:
    """Tests for read_parameters method."""

    @pytest.mark.asyncio
    async def test_read_parameters_uses_local(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test read_parameters uses local transport."""
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        transport._connected = True

        result = await transport.read_parameters(0, 10)

        assert result == {0: 100, 1: 200}
        mock_local_transport.read_parameters.assert_called_once_with(0, 10)

    @pytest.mark.asyncio
    async def test_read_parameters_falls_back(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test read_parameters falls back on failure."""
        mock_local_transport.read_parameters.side_effect = TransportReadError("Failed")
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        transport._connected = True

        result = await transport.read_parameters(0, 10)

        assert result == {0: 100, 1: 200}
        mock_http_transport.read_parameters.assert_called_once_with(0, 10)


class TestHybridTransportWriteParameters:
    """Tests for write_parameters method."""

    @pytest.mark.asyncio
    async def test_write_parameters_uses_local(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test write_parameters uses local transport."""
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        transport._connected = True

        result = await transport.write_parameters({100: 50})

        assert result is True
        mock_local_transport.write_parameters.assert_called_once_with({100: 50})

    @pytest.mark.asyncio
    async def test_write_parameters_falls_back(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test write_parameters falls back on failure."""
        from pylxpweb.transports.exceptions import TransportWriteError

        mock_local_transport.write_parameters.side_effect = TransportWriteError("Failed")
        transport = HybridTransport(mock_local_transport, mock_http_transport)
        transport._connected = True

        result = await transport.write_parameters({100: 50})

        assert result is True
        mock_http_transport.write_parameters.assert_called_once_with({100: 50})


class TestHybridTransportRecovery:
    """Tests for local transport recovery behavior."""

    @pytest.mark.asyncio
    async def test_local_recovery_after_interval(
        self, mock_local_transport: MagicMock, mock_http_transport: MagicMock
    ) -> None:
        """Test local transport is retried after recovery interval."""
        transport = HybridTransport(
            mock_local_transport, mock_http_transport, local_retry_interval=0.1
        )
        transport._connected = True

        # Simulate local failure
        mock_local_transport.read_runtime.side_effect = TransportReadError("Failed")
        await transport.read_runtime()  # This will fail and set _local_failed_at

        # Reset mock and wait for recovery
        mock_local_transport.read_runtime.side_effect = None
        mock_local_transport.read_runtime.reset_mock()
        mock_http_transport.read_runtime.reset_mock()

        # Wait for retry interval
        with patch("time.monotonic", return_value=time.monotonic() + 0.2):
            transport._check_local_recovery()
            assert transport._local_failed_at is None
            assert transport._using_local is True
