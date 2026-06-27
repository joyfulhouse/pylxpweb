"""Unit tests for scanner.scanner module."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.scanner.scanner import PORT_DONGLE, PORT_MODBUS, NetworkScanner
from pylxpweb.scanner.types import DeviceType, ScanConfig, ScanProgress


class TestNetworkScanner:
    """Tests for NetworkScanner class."""

    @pytest.fixture
    def minimal_config(self) -> ScanConfig:
        """Minimal scan config for testing."""
        return ScanConfig(
            ip_range="192.168.1.1",
            ports=[502],
            timeout=0.1,
            concurrency=1,
            verify_modbus=False,
            lookup_mac=False,
        )

    @pytest.fixture
    def multi_host_config(self) -> ScanConfig:
        """Config scanning multiple hosts."""
        return ScanConfig(
            ip_range="192.168.1.1-192.168.1.3",
            ports=[502],
            timeout=0.1,
            concurrency=10,
            verify_modbus=False,
            lookup_mac=False,
        )

    def test_scanner_initialization(self, minimal_config: ScanConfig) -> None:
        """Test NetworkScanner initialization."""
        scanner = NetworkScanner(minimal_config)
        assert scanner._config == minimal_config
        assert scanner._progress_callback is None
        assert scanner._cancelled is False

    def test_scanner_initialization_with_callback(self, minimal_config: ScanConfig) -> None:
        """Test NetworkScanner initialization with progress callback."""

        def callback(progress: ScanProgress) -> None:
            pass

        scanner = NetworkScanner(minimal_config, progress_callback=callback)
        assert scanner._progress_callback == callback

    def test_cancel_method(self, minimal_config: ScanConfig) -> None:
        """Test cancel method sets cancelled flag."""
        scanner = NetworkScanner(minimal_config)
        assert scanner._cancelled is False
        scanner.cancel()
        assert scanner._cancelled is True

    async def test_scan_empty_ip_range(self) -> None:
        """Test scan with empty IP range returns no results."""
        config = ScanConfig(ip_range="192.168.1.1", ports=[502])

        with patch("pylxpweb.scanner.scanner.parse_ip_range", return_value=[]):
            scanner = NetworkScanner(config)
            results = [r async for r in scanner.scan()]

        assert results == []

    async def test_scan_no_open_ports(self, minimal_config: ScanConfig) -> None:
        """Test scan when all connections fail."""
        with patch(
            "pylxpweb.scanner.scanner.asyncio.open_connection",
            side_effect=ConnectionRefusedError,
        ):
            scanner = NetworkScanner(minimal_config)
            results = [r async for r in scanner.scan()]

        assert results == []

    async def test_scan_timeout_error(self, minimal_config: ScanConfig) -> None:
        """Test scan handles timeout errors."""
        with patch(
            "pylxpweb.scanner.scanner.asyncio.open_connection",
            side_effect=TimeoutError,
        ):
            scanner = NetworkScanner(minimal_config)
            results = [r async for r in scanner.scan()]

        assert results == []

    async def test_scan_os_error(self, minimal_config: ScanConfig) -> None:
        """Test scan handles OS errors."""
        with patch(
            "pylxpweb.scanner.scanner.asyncio.open_connection",
            side_effect=OSError("Network unreachable"),
        ):
            scanner = NetworkScanner(minimal_config)
            results = [r async for r in scanner.scan()]

        assert results == []

    async def test_scan_finds_open_port(self, minimal_config: ScanConfig) -> None:
        """Test scan finds open port."""
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch(
            "pylxpweb.scanner.scanner.asyncio.open_connection",
            return_value=(MagicMock(), writer),
        ):
            scanner = NetworkScanner(minimal_config)
            results = [r async for r in scanner.scan()]

        assert len(results) == 1
        assert results[0].ip == "192.168.1.1"
        assert results[0].port == 502
        assert results[0].device_type == DeviceType.MODBUS_UNVERIFIED

    async def test_scan_multiple_hosts(self, multi_host_config: ScanConfig) -> None:
        """Test scanning multiple hosts."""
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch(
            "pylxpweb.scanner.scanner.asyncio.open_connection",
            return_value=(MagicMock(), writer),
        ):
            scanner = NetworkScanner(multi_host_config)
            results = [r async for r in scanner.scan()]

        assert len(results) == 3
        ips = {r.ip for r in results}
        assert ips == {"192.168.1.1", "192.168.1.2", "192.168.1.3"}

    async def test_scan_multiple_ports(self) -> None:
        """Test scanning multiple ports per host."""
        config = ScanConfig(
            ip_range="192.168.1.1",
            ports=[502, 8000],
            timeout=0.1,
            verify_modbus=False,
            lookup_mac=False,
        )
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch(
            "pylxpweb.scanner.scanner.asyncio.open_connection",
            return_value=(MagicMock(), writer),
        ):
            scanner = NetworkScanner(config)
            results = [r async for r in scanner.scan()]

        assert len(results) == 2
        ports = {r.port for r in results}
        assert ports == {502, 8000}

    async def test_scan_dongle_port(self) -> None:
        """Test scan identifies dongle candidate on port 8000."""
        config = ScanConfig(
            ip_range="192.168.1.1",
            ports=[8000],
            timeout=0.1,
            verify_modbus=False,
            lookup_mac=False,
        )
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch(
            "pylxpweb.scanner.scanner.asyncio.open_connection",
            return_value=(MagicMock(), writer),
        ):
            scanner = NetworkScanner(config)
            results = [r async for r in scanner.scan()]

        assert len(results) == 1
        assert results[0].device_type == DeviceType.DONGLE_CANDIDATE
        assert results[0].port == 8000

    async def test_scan_progress_callback(self, multi_host_config: ScanConfig) -> None:
        """Test progress callback is invoked."""
        progress_updates: list[ScanProgress] = []

        with patch(
            "pylxpweb.scanner.scanner.asyncio.open_connection",
            side_effect=ConnectionRefusedError,
        ):
            scanner = NetworkScanner(multi_host_config, progress_callback=progress_updates.append)
            _ = [r async for r in scanner.scan()]

        # Should have at least final update
        assert len(progress_updates) > 0
        final = progress_updates[-1]
        assert final.total_hosts == 3
        assert final.scanned == 3
        assert final.found == 0

    async def test_scan_progress_increments(self, multi_host_config: ScanConfig) -> None:
        """Test progress callback increments properly."""
        progress_updates: list[ScanProgress] = []

        with patch(
            "pylxpweb.scanner.scanner.asyncio.open_connection",
            side_effect=ConnectionRefusedError,
        ):
            scanner = NetworkScanner(multi_host_config, progress_callback=progress_updates.append)
            _ = [r async for r in scanner.scan()]

        # Check that scanned count increases
        scanned_counts = [p.scanned for p in progress_updates]
        assert scanned_counts == sorted(scanned_counts)

    async def test_scan_cancellation(self, multi_host_config: ScanConfig) -> None:
        """Test scan can be cancelled."""

        async def slow_connect(host: str, port: int) -> tuple[object, object]:
            await asyncio.sleep(1.0)
            writer = MagicMock()
            writer.close = MagicMock()
            writer.wait_closed = AsyncMock()
            return MagicMock(), writer

        with patch(
            "pylxpweb.scanner.scanner.asyncio.open_connection",
            side_effect=slow_connect,
        ):
            scanner = NetworkScanner(multi_host_config)

            # Cancel after brief delay
            async def cancel_soon() -> None:
                await asyncio.sleep(0.01)
                scanner.cancel()

            cancel_task = asyncio.create_task(cancel_soon())

            results = [r async for r in scanner.scan()]
            await cancel_task

        # Should have fewer results than total hosts
        assert len(results) < 3

    async def test_scan_with_mac_lookup(self) -> None:
        """Test scan with MAC lookup enabled."""
        config = ScanConfig(
            ip_range="192.168.1.1",
            ports=[502],
            timeout=0.1,
            verify_modbus=False,
            lookup_mac=True,
        )
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with (
            patch(
                "pylxpweb.scanner.scanner.asyncio.open_connection",
                return_value=(MagicMock(), writer),
            ),
            patch(
                "pylxpweb.scanner.scanner.lookup_mac_address",
                return_value="A4:CF:12:34:56:78",
            ),
            patch("pylxpweb.scanner.scanner.get_oui_vendor", return_value="Espressif"),
        ):
            scanner = NetworkScanner(config)
            results = [r async for r in scanner.scan()]

        assert len(results) == 1
        assert results[0].mac_address == "A4:CF:12:34:56:78"
        assert results[0].mac_vendor == "Espressif"

    async def test_scan_with_modbus_verification_verified(self) -> None:
        """Test scan with Modbus verification succeeds."""
        config = ScanConfig(
            ip_range="192.168.1.1",
            ports=[502],
            timeout=0.1,
            verify_modbus=True,
            lookup_mac=False,
        )
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        mock_info = MagicMock()
        mock_info.serial = "4512345678"
        mock_info.device_type_code = 2092  # PV_SERIES
        mock_info.firmware_version = "1.0.5"

        mock_transport = MagicMock()
        mock_transport.connect = AsyncMock()
        mock_transport.disconnect = AsyncMock()

        with (
            patch(
                "pylxpweb.scanner.scanner.asyncio.open_connection",
                return_value=(MagicMock(), writer),
            ),
            patch(
                "pylxpweb.transports.factory.create_modbus_transport",
                return_value=mock_transport,
            ),
            patch(
                "pylxpweb.transports.discovery.discover_device_info",
                return_value=mock_info,
            ),
            patch("pylxpweb.transports.discovery.get_model_family_name", return_value="PV_SERIES"),
        ):
            scanner = NetworkScanner(config)
            results = [r async for r in scanner.scan()]

        assert len(results) == 1
        assert results[0].device_type == DeviceType.MODBUS_VERIFIED
        assert results[0].serial == "4512345678"
        assert results[0].model_family == "PV_SERIES"
        assert results[0].device_type_code == 2092
        assert results[0].firmware_version == "1.0.5"

    async def test_scan_verifies_6000xp_type_code_38(self) -> None:
        """Code 38 (6000XP variant, GH eg4_web_monitor#222) scans as VERIFIED.

        Uses the real get_model_family_name so the known_codes membership and
        the family mapping are exercised together.
        """
        config = ScanConfig(
            ip_range="192.168.1.1",
            ports=[502],
            timeout=0.1,
            verify_modbus=True,
            lookup_mac=False,
        )
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        mock_info = MagicMock()
        mock_info.serial = "4233740012"
        mock_info.device_type_code = 38  # 6000XP variant
        mock_info.firmware_version = "2.0.1"

        mock_transport = MagicMock()
        mock_transport.connect = AsyncMock()
        mock_transport.disconnect = AsyncMock()

        with (
            patch(
                "pylxpweb.scanner.scanner.asyncio.open_connection",
                return_value=(MagicMock(), writer),
            ),
            patch(
                "pylxpweb.transports.factory.create_modbus_transport",
                return_value=mock_transport,
            ),
            patch(
                "pylxpweb.transports.discovery.discover_device_info",
                return_value=mock_info,
            ),
        ):
            scanner = NetworkScanner(config)
            results = [r async for r in scanner.scan()]

        assert len(results) == 1
        assert results[0].device_type == DeviceType.MODBUS_VERIFIED
        assert results[0].model_family == "EG4_OFFGRID"
        assert results[0].device_type_code == 38

    async def test_scan_with_modbus_verification_unknown_code(self) -> None:
        """Test Modbus verification with unknown device type code."""
        config = ScanConfig(
            ip_range="192.168.1.1",
            ports=[502],
            timeout=0.1,
            verify_modbus=True,
            lookup_mac=False,
        )
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        mock_info = MagicMock()
        mock_info.serial = "9999999999"
        mock_info.device_type_code = 9999  # Unknown
        mock_info.firmware_version = None

        mock_transport = MagicMock()
        mock_transport.connect = AsyncMock()
        mock_transport.disconnect = AsyncMock()

        with (
            patch(
                "pylxpweb.scanner.scanner.asyncio.open_connection",
                return_value=(MagicMock(), writer),
            ),
            patch(
                "pylxpweb.transports.factory.create_modbus_transport",
                return_value=mock_transport,
            ),
            patch(
                "pylxpweb.transports.discovery.discover_device_info",
                return_value=mock_info,
            ),
        ):
            scanner = NetworkScanner(config)
            results = [r async for r in scanner.scan()]

        assert len(results) == 1
        assert results[0].device_type == DeviceType.MODBUS_UNVERIFIED
        assert results[0].device_type_code == 9999
        assert "Unknown device type code" in (results[0].error or "")

    async def test_scan_with_modbus_verification_failure(self) -> None:
        """Test Modbus verification failure is handled."""
        config = ScanConfig(
            ip_range="192.168.1.1",
            ports=[502],
            timeout=0.1,
            verify_modbus=True,
            lookup_mac=False,
        )
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        mock_transport = MagicMock()
        mock_transport.connect = AsyncMock(side_effect=OSError("Connection reset"))

        with (
            patch(
                "pylxpweb.scanner.scanner.asyncio.open_connection",
                return_value=(MagicMock(), writer),
            ),
            patch(
                "pylxpweb.transports.factory.create_modbus_transport",
                return_value=mock_transport,
            ),
        ):
            scanner = NetworkScanner(config)
            results = [r async for r in scanner.scan()]

        assert len(results) == 1
        assert results[0].device_type == DeviceType.MODBUS_UNVERIFIED
        assert "Connection reset" in (results[0].error or "")

    async def test_scan_task_exception_handling(self, multi_host_config: ScanConfig) -> None:
        """Test scan handles task exceptions gracefully."""

        async def failing_connect(host: str, port: int) -> tuple[object, object]:
            if host == "192.168.1.2":
                raise ValueError("Unexpected error")
            raise ConnectionRefusedError

        with patch(
            "pylxpweb.scanner.scanner.asyncio.open_connection",
            side_effect=failing_connect,
        ):
            scanner = NetworkScanner(multi_host_config)
            results = [r async for r in scanner.scan()]

        # Should complete without raising
        assert results == []

    async def test_scan_response_time_recorded(self, minimal_config: ScanConfig) -> None:
        """Test response time is recorded."""
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch(
            "pylxpweb.scanner.scanner.asyncio.open_connection",
            return_value=(MagicMock(), writer),
        ):
            scanner = NetworkScanner(minimal_config)
            results = [r async for r in scanner.scan()]

        assert len(results) == 1
        assert results[0].response_time_ms >= 0.0

    async def test_scan_non_standard_port(self) -> None:
        """Test scanning non-standard port returns MODBUS_UNVERIFIED."""
        config = ScanConfig(
            ip_range="192.168.1.1",
            ports=[503],  # Non-standard port
            timeout=0.1,
            verify_modbus=False,
            lookup_mac=False,
        )
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch(
            "pylxpweb.scanner.scanner.asyncio.open_connection",
            return_value=(MagicMock(), writer),
        ):
            scanner = NetworkScanner(config)
            results = [r async for r in scanner.scan()]

        assert len(results) == 1
        assert results[0].device_type == DeviceType.MODBUS_UNVERIFIED
        assert results[0].port == 503

    async def test_constants(self) -> None:
        """Test module constants have correct values."""
        assert PORT_MODBUS == 502
        assert PORT_DONGLE == 8000

    async def test_scan_concurrent_execution(self) -> None:
        """Test scan respects concurrency limit."""
        config = ScanConfig(
            ip_range="192.168.1.1-192.168.1.10",
            ports=[502],
            timeout=0.1,
            concurrency=5,
            verify_modbus=False,
            lookup_mac=False,
        )

        call_count = 0
        max_concurrent = 0
        current_concurrent = 0

        async def mock_connect(host: str, port: int) -> tuple[object, object]:
            nonlocal call_count, max_concurrent, current_concurrent
            call_count += 1
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)

            await asyncio.sleep(0.01)

            current_concurrent -= 1
            writer = MagicMock()
            writer.close = MagicMock()
            writer.wait_closed = AsyncMock()
            return MagicMock(), writer

        with patch(
            "pylxpweb.scanner.scanner.asyncio.open_connection",
            side_effect=mock_connect,
        ):
            scanner = NetworkScanner(config)
            results = [r async for r in scanner.scan()]

        assert len(results) == 10
        # Max concurrent should not exceed concurrency limit significantly
        # (allowing some buffer due to async timing)
        assert max_concurrent <= config.concurrency + 2

    async def test_scan_cancellation_cleans_up(self, multi_host_config: ScanConfig) -> None:
        """Test cancellation properly cleans up tasks."""
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch(
            "pylxpweb.scanner.scanner.asyncio.open_connection",
            return_value=(MagicMock(), writer),
        ):
            scanner = NetworkScanner(multi_host_config)

            # Start scan and cancel immediately
            gen = scanner.scan()
            scanner.cancel()

            results = [r async for r in gen]

        # Should complete without hanging
        assert isinstance(results, list)

    async def test_scan_modbus_port_without_verification(self) -> None:
        """Test Modbus port without verification returns MODBUS_UNVERIFIED."""
        config = ScanConfig(
            ip_range="192.168.1.1",
            ports=[502],
            timeout=0.1,
            verify_modbus=False,
            lookup_mac=False,
        )
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch(
            "pylxpweb.scanner.scanner.asyncio.open_connection",
            return_value=(MagicMock(), writer),
        ):
            scanner = NetworkScanner(config)
            results = [r async for r in scanner.scan()]

        assert len(results) == 1
        assert results[0].device_type == DeviceType.MODBUS_UNVERIFIED

    async def test_scan_found_count_increments(self) -> None:
        """Test found count increments in progress updates."""
        config = ScanConfig(
            ip_range="192.168.1.1-192.168.1.3",
            ports=[502],
            timeout=0.1,
            concurrency=10,
            verify_modbus=False,
            lookup_mac=False,
        )
        progress_updates: list[ScanProgress] = []

        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch(
            "pylxpweb.scanner.scanner.asyncio.open_connection",
            return_value=(MagicMock(), writer),
        ):
            scanner = NetworkScanner(config, progress_callback=progress_updates.append)
            results = [r async for r in scanner.scan()]

        assert len(results) == 3
        # Final progress should show 3 found
        final = progress_updates[-1]
        assert final.found == 3
