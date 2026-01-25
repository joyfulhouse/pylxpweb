"""Tests for Station.from_local_discovery() factory method."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylxpweb.devices.discovery import DeviceDiscoveryInfo
from pylxpweb.devices.station import Station
from pylxpweb.transports.config import TransportConfig, TransportType


class TestFromLocalDiscovery:
    """Tests for Station.from_local_discovery() factory method."""

    @pytest.mark.asyncio
    async def test_creates_station_from_single_modbus_transport(self) -> None:
        """Test creating station with a single standalone inverter via Modbus."""
        # Create transport config
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
        )

        # Mock the transport creation and discovery
        with patch(
            "pylxpweb.devices.station.create_transport_from_config"
        ) as mock_create:
            mock_transport = MagicMock()
            mock_transport.serial = "CE12345678"
            mock_transport.is_connected = True
            mock_transport.read_parameters = AsyncMock(return_value={19: 2092})
            mock_transport.read_device_type = AsyncMock(return_value=2092)
            mock_transport.is_midbox_device = MagicMock(return_value=False)
            mock_transport.read_firmware_version = AsyncMock(return_value="FAAB-2525")
            mock_transport.connect = AsyncMock()
            mock_create.return_value = mock_transport

            with patch(
                "pylxpweb.devices.station.discover_device_info"
            ) as mock_discover:
                mock_discover.return_value = DeviceDiscoveryInfo(
                    serial="CE12345678",
                    device_type_code=2092,
                    is_gridboss=False,
                    parallel_number=0,  # Standalone
                    parallel_phase=0,
                    firmware_version="FAAB-2525",
                )

                station = await Station.from_local_discovery(
                    configs=[config],
                    station_name="Local Station",
                    plant_id=99999,
                )

        assert station.name == "Local Station"
        assert station.id == 99999
        assert len(station.standalone_inverters) == 1
        assert len(station.parallel_groups) == 0
        assert station.standalone_inverters[0].serial_number == "CE12345678"

    @pytest.mark.asyncio
    async def test_creates_station_from_dongle_transport(self) -> None:
        """Test creating station with a single inverter via WiFi dongle."""
        config = TransportConfig(
            host="192.168.1.100",
            port=8000,
            serial="CE12345678",
            transport_type=TransportType.WIFI_DONGLE,
            dongle_serial="BA12345678",
        )

        with patch(
            "pylxpweb.devices.station.create_transport_from_config"
        ) as mock_create:
            mock_transport = MagicMock()
            mock_transport.serial = "CE12345678"
            mock_transport.is_connected = True
            mock_transport.read_parameters = AsyncMock(return_value={19: 10284})
            mock_transport.read_device_type = AsyncMock(return_value=10284)
            mock_transport.is_midbox_device = MagicMock(return_value=False)
            mock_transport.read_firmware_version = AsyncMock(return_value="FAAB-2525")
            mock_transport.connect = AsyncMock()
            mock_create.return_value = mock_transport

            with patch(
                "pylxpweb.devices.station.discover_device_info"
            ) as mock_discover:
                mock_discover.return_value = DeviceDiscoveryInfo(
                    serial="CE12345678",
                    device_type_code=10284,
                    is_gridboss=False,
                    parallel_number=0,
                    parallel_phase=0,
                    firmware_version="FAAB-2525",
                )

                station = await Station.from_local_discovery(
                    configs=[config],
                    station_name="Dongle Station",
                    plant_id=88888,
                )

        assert station.name == "Dongle Station"
        assert len(station.standalone_inverters) == 1

    @pytest.mark.asyncio
    async def test_groups_parallel_inverters(self) -> None:
        """Test that inverters in same parallel group are grouped together."""
        # Two inverters in parallel group 1
        config1 = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE11111111",
            transport_type=TransportType.MODBUS_TCP,
        )
        config2 = TransportConfig(
            host="192.168.1.101",
            port=502,
            serial="CE22222222",
            transport_type=TransportType.MODBUS_TCP,
        )

        def create_mock_transport(serial: str) -> MagicMock:
            transport = MagicMock()
            transport.serial = serial
            transport.is_connected = True
            transport.read_parameters = AsyncMock(return_value={19: 2092})
            transport.read_device_type = AsyncMock(return_value=2092)
            transport.is_midbox_device = MagicMock(return_value=False)
            transport.read_firmware_version = AsyncMock(return_value="FAAB-2525")
            transport.connect = AsyncMock()
            return transport

        discovery_results = {
            "CE11111111": DeviceDiscoveryInfo(
                serial="CE11111111",
                device_type_code=2092,
                is_gridboss=False,
                parallel_number=1,  # Group 1
                parallel_phase=0,
                firmware_version="FAAB-2525",
            ),
            "CE22222222": DeviceDiscoveryInfo(
                serial="CE22222222",
                device_type_code=2092,
                is_gridboss=False,
                parallel_number=1,  # Group 1 (same)
                parallel_phase=1,
                firmware_version="FAAB-2525",
            ),
        }

        with patch(
            "pylxpweb.devices.station.create_transport_from_config"
        ) as mock_create:

            def side_effect(config: TransportConfig) -> MagicMock:
                return create_mock_transport(config.serial)

            mock_create.side_effect = side_effect

            with patch(
                "pylxpweb.devices.station.discover_device_info"
            ) as mock_discover:

                async def discover_side_effect(transport: MagicMock) -> DeviceDiscoveryInfo:
                    return discovery_results[transport.serial]

                mock_discover.side_effect = discover_side_effect

                station = await Station.from_local_discovery(
                    configs=[config1, config2],
                    station_name="Parallel Station",
                    plant_id=77777,
                )

        # Both inverters should be in one parallel group
        assert len(station.parallel_groups) == 1
        assert len(station.standalone_inverters) == 0
        assert len(station.parallel_groups[0].inverters) == 2
        assert station.parallel_groups[0].name == "A"  # Group 1 = "A"

    @pytest.mark.asyncio
    async def test_separates_standalone_and_parallel(self) -> None:
        """Test that standalone and parallel inverters are separated correctly."""
        config1 = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE11111111",
            transport_type=TransportType.MODBUS_TCP,
        )
        config2 = TransportConfig(
            host="192.168.1.101",
            port=502,
            serial="CE22222222",
            transport_type=TransportType.MODBUS_TCP,
        )

        def create_mock_transport(serial: str) -> MagicMock:
            transport = MagicMock()
            transport.serial = serial
            transport.is_connected = True
            transport.read_parameters = AsyncMock(return_value={19: 2092})
            transport.connect = AsyncMock()
            return transport

        discovery_results = {
            "CE11111111": DeviceDiscoveryInfo(
                serial="CE11111111",
                device_type_code=2092,
                is_gridboss=False,
                parallel_number=0,  # Standalone
                parallel_phase=0,
                firmware_version="FAAB-2525",
            ),
            "CE22222222": DeviceDiscoveryInfo(
                serial="CE22222222",
                device_type_code=2092,
                is_gridboss=False,
                parallel_number=1,  # Parallel group 1
                parallel_phase=0,
                firmware_version="FAAB-2525",
            ),
        }

        with patch(
            "pylxpweb.devices.station.create_transport_from_config"
        ) as mock_create:
            mock_create.side_effect = lambda c: create_mock_transport(c.serial)

            with patch(
                "pylxpweb.devices.station.discover_device_info"
            ) as mock_discover:
                mock_discover.side_effect = lambda t: discovery_results[t.serial]

                station = await Station.from_local_discovery(
                    configs=[config1, config2],
                    station_name="Mixed Station",
                    plant_id=66666,
                )

        assert len(station.standalone_inverters) == 1
        assert len(station.parallel_groups) == 1
        assert station.standalone_inverters[0].serial_number == "CE11111111"
        assert station.parallel_groups[0].inverters[0].serial_number == "CE22222222"

    @pytest.mark.asyncio
    async def test_handles_gridboss_device(self) -> None:
        """Test that GridBOSS devices are detected and handled separately."""
        config1 = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="GB12345678",
            transport_type=TransportType.MODBUS_TCP,
        )
        config2 = TransportConfig(
            host="192.168.1.101",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
        )

        def create_mock_transport(serial: str) -> MagicMock:
            transport = MagicMock()
            transport.serial = serial
            transport.is_connected = True
            transport.read_parameters = AsyncMock(return_value={19: 50 if serial.startswith("GB") else 2092})
            transport.connect = AsyncMock()
            return transport

        discovery_results = {
            "GB12345678": DeviceDiscoveryInfo(
                serial="GB12345678",
                device_type_code=50,  # GridBOSS
                is_gridboss=True,
                parallel_number=1,
                parallel_phase=0,
                firmware_version="GB-1234",
            ),
            "CE12345678": DeviceDiscoveryInfo(
                serial="CE12345678",
                device_type_code=2092,
                is_gridboss=False,
                parallel_number=1,  # Same group as GridBOSS
                parallel_phase=0,
                firmware_version="FAAB-2525",
            ),
        }

        with patch(
            "pylxpweb.devices.station.create_transport_from_config"
        ) as mock_create:
            mock_create.side_effect = lambda c: create_mock_transport(c.serial)

            with patch(
                "pylxpweb.devices.station.discover_device_info"
            ) as mock_discover:
                mock_discover.side_effect = lambda t: discovery_results[t.serial]

                station = await Station.from_local_discovery(
                    configs=[config1, config2],
                    station_name="GridBOSS Station",
                    plant_id=55555,
                )

        # Should have one parallel group with inverter and MID device
        assert len(station.parallel_groups) == 1
        assert len(station.parallel_groups[0].inverters) == 1
        assert station.parallel_groups[0].mid_device is not None
        assert station.parallel_groups[0].mid_device.serial_number == "GB12345678"

    @pytest.mark.asyncio
    async def test_handles_connection_failure_gracefully(self) -> None:
        """Test that connection failures for one device don't prevent others."""
        config1 = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE11111111",
            transport_type=TransportType.MODBUS_TCP,
        )
        config2 = TransportConfig(
            host="192.168.1.101",
            port=502,
            serial="CE22222222",
            transport_type=TransportType.MODBUS_TCP,
        )

        call_count = 0

        def create_mock_transport_with_failure(config: TransportConfig) -> MagicMock:
            nonlocal call_count
            call_count += 1
            transport = MagicMock()
            transport.serial = config.serial
            transport.is_connected = False

            if config.serial == "CE11111111":
                # First transport fails to connect
                transport.connect = AsyncMock(side_effect=Exception("Connection refused"))
            else:
                # Second transport connects successfully
                transport.is_connected = True
                transport.connect = AsyncMock()
                transport.read_parameters = AsyncMock(return_value={19: 2092})

            return transport

        with patch(
            "pylxpweb.devices.station.create_transport_from_config"
        ) as mock_create:
            mock_create.side_effect = create_mock_transport_with_failure

            with patch(
                "pylxpweb.devices.station.discover_device_info"
            ) as mock_discover:
                mock_discover.return_value = DeviceDiscoveryInfo(
                    serial="CE22222222",
                    device_type_code=2092,
                    is_gridboss=False,
                    parallel_number=0,
                    parallel_phase=0,
                    firmware_version="FAAB-2525",
                )

                station = await Station.from_local_discovery(
                    configs=[config1, config2],
                    station_name="Partial Station",
                    plant_id=44444,
                )

        # Should have one inverter (the one that connected)
        assert len(station.standalone_inverters) == 1
        assert station.standalone_inverters[0].serial_number == "CE22222222"

    @pytest.mark.asyncio
    async def test_uses_custom_timezone(self) -> None:
        """Test that custom timezone is used for the station."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
        )

        with patch(
            "pylxpweb.devices.station.create_transport_from_config"
        ) as mock_create:
            mock_transport = MagicMock()
            mock_transport.serial = "CE12345678"
            mock_transport.is_connected = True
            mock_transport.read_parameters = AsyncMock(return_value={19: 2092})
            mock_transport.connect = AsyncMock()
            mock_create.return_value = mock_transport

            with patch(
                "pylxpweb.devices.station.discover_device_info"
            ) as mock_discover:
                mock_discover.return_value = DeviceDiscoveryInfo(
                    serial="CE12345678",
                    device_type_code=2092,
                    is_gridboss=False,
                    parallel_number=0,
                    parallel_phase=0,
                    firmware_version="FAAB-2525",
                )

                station = await Station.from_local_discovery(
                    configs=[config],
                    station_name="Test Station",
                    plant_id=33333,
                    timezone="America/Los_Angeles",
                )

        assert station.timezone == "America/Los_Angeles"

    @pytest.mark.asyncio
    async def test_empty_configs_raises_error(self) -> None:
        """Test that empty config list raises ValueError."""
        with pytest.raises(ValueError, match="At least one transport config required"):
            await Station.from_local_discovery(
                configs=[],
                station_name="Empty Station",
                plant_id=22222,
            )


class TestLocalStationProperties:
    """Tests for local-only station properties."""

    @pytest.mark.asyncio
    async def test_is_local_only_true_for_local_station(self) -> None:
        """Test is_local_only returns True for locally-created station."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
        )

        with patch(
            "pylxpweb.devices.station.create_transport_from_config"
        ) as mock_create:
            mock_transport = MagicMock()
            mock_transport.serial = "CE12345678"
            mock_transport.is_connected = True
            mock_transport.read_parameters = AsyncMock(return_value={19: 2092})
            mock_transport.connect = AsyncMock()
            mock_create.return_value = mock_transport

            with patch(
                "pylxpweb.devices.station.discover_device_info"
            ) as mock_discover:
                mock_discover.return_value = DeviceDiscoveryInfo(
                    serial="CE12345678",
                    device_type_code=2092,
                    is_gridboss=False,
                    parallel_number=0,
                    parallel_phase=0,
                    firmware_version="FAAB-2525",
                )

                station = await Station.from_local_discovery(
                    configs=[config],
                    station_name="Local Station",
                    plant_id=11111,
                )

        assert station.is_local_only is True

    @pytest.mark.asyncio
    async def test_all_inverters_have_transport(self) -> None:
        """Test that all inverters created locally have transports attached."""
        config = TransportConfig(
            host="192.168.1.100",
            port=502,
            serial="CE12345678",
            transport_type=TransportType.MODBUS_TCP,
        )

        with patch(
            "pylxpweb.devices.station.create_transport_from_config"
        ) as mock_create:
            mock_transport = MagicMock()
            mock_transport.serial = "CE12345678"
            mock_transport.is_connected = True
            mock_transport.read_parameters = AsyncMock(return_value={19: 2092})
            mock_transport.connect = AsyncMock()
            mock_create.return_value = mock_transport

            with patch(
                "pylxpweb.devices.station.discover_device_info"
            ) as mock_discover:
                mock_discover.return_value = DeviceDiscoveryInfo(
                    serial="CE12345678",
                    device_type_code=2092,
                    is_gridboss=False,
                    parallel_number=0,
                    parallel_phase=0,
                    firmware_version="FAAB-2525",
                )

                station = await Station.from_local_discovery(
                    configs=[config],
                    station_name="Local Station",
                    plant_id=11111,
                )

        for inverter in station.all_inverters:
            assert inverter.has_transport is True
