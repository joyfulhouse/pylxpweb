"""Unit tests for Pydantic models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pylxpweb.models import (
    BatteryInfo,
    BatteryModule,
    DongleStatus,
    EnergyInfo,
    InverterRuntime,
    LoginResponse,
    MidboxRuntime,
    PlantInfo,
    energy_to_kwh,
    scale_cell_voltage,
    scale_current,
    scale_frequency,
    scale_voltage,
)

SAMPLES_DIR = Path(__file__).parent.parent / "samples"


def load_sample(filename: str) -> dict[str, Any]:
    """Load a sample JSON file."""
    with open(SAMPLES_DIR / filename) as f:
        result: dict[str, Any] = json.load(f)
        return result


class TestLoginResponse:
    """Test LoginResponse model."""

    def test_parse_login_response(self) -> None:
        """Test parsing login response."""
        data = load_sample("login.json")
        model = LoginResponse.model_validate(data)

        assert model.success is True
        assert model.userId == 99999
        assert model.username == "testuser"
        assert model.email == "testuser@gmail.com"
        assert len(model.plants) == 1
        assert model.plants[0].plantId == 99999

    def test_obfuscate_email(self) -> None:
        """Test that email is obfuscated in serialization."""
        data = load_sample("login.json")
        model = LoginResponse.model_validate(data)

        serialized = model.model_dump(mode="json")
        # Email should be obfuscated
        assert serialized["email"] != "testuser@gmail.com"
        assert "@gmail.com" in serialized["email"]

    def test_obfuscate_phone(self) -> None:
        """Test that phone number is obfuscated."""
        data = load_sample("login.json")
        model = LoginResponse.model_validate(data)

        serialized = model.model_dump(mode="json")
        # Phone should be obfuscated, showing only last 4 digits
        assert serialized["telNumber"].startswith("***-***-")

    def test_obfuscate_serial_numbers(self) -> None:
        """Test that serial numbers are obfuscated."""
        data = load_sample("login.json")
        model = LoginResponse.model_validate(data)

        serialized = model.model_dump(mode="json")
        # Serial numbers in inverters should be obfuscated
        for plant in serialized["plants"]:
            for inverter in plant["inverters"]:
                serial = inverter["serialNum"]
                # Should show first 2 and last 2 digits only
                assert serial.count("*") > 0

    def test_parse_eu_server_techinfo_empty(self) -> None:
        """Test parsing login response with EU server's minimal techInfo.

        EU Luxpower server (eu.luxpowertek.com) returns techInfo with only
        techInfoCount=0, without techInfoType1/techInfo1 fields.
        Regression test for GitHub issue #84.
        """
        data = load_sample("login.json")
        # Simulate EU server response: only techInfoCount, no other fields
        data["techInfo"] = {"techInfoCount": 0}
        model = LoginResponse.model_validate(data)

        assert model.techInfo is not None
        assert model.techInfo.techInfoCount == 0
        assert model.techInfo.techInfoType1 is None
        assert model.techInfo.techInfo1 is None

    def test_parse_techinfo_with_all_fields(self) -> None:
        """Test parsing login response with full techInfo fields."""
        data = load_sample("login.json")
        data["techInfo"] = {
            "techInfoCount": 2,
            "techInfoType1": "Phone",
            "techInfo1": "1-800-555-1234",
            "techInfoType2": "Email",
            "techInfo2": "support@example.com",
        }
        model = LoginResponse.model_validate(data)

        assert model.techInfo is not None
        assert model.techInfo.techInfoCount == 2
        assert model.techInfo.techInfoType1 == "Phone"
        assert model.techInfo.techInfo1 == "1-800-555-1234"
        assert model.techInfo.techInfoType2 == "Email"
        assert model.techInfo.techInfo2 == "support@example.com"


class TestPlantInfo:
    """Test PlantInfo model."""

    def test_parse_plant_info(self) -> None:
        """Test parsing plant info."""
        data = load_sample("plants.json")
        assert isinstance(data, list)
        model = PlantInfo.model_validate(data[0])

        assert model.plantId == 99999
        assert model.name == "Example Solar Station"
        assert model.daylightSavingTime is True

    def test_obfuscate_contact_info(self) -> None:
        """Test that contact information is obfuscated."""
        data = load_sample("plants.json")
        assert isinstance(data, list)
        model = PlantInfo.model_validate(data[0])

        serialized = model.model_dump(mode="json")
        # Address should be obfuscated
        assert serialized["address"] == "***"


class TestInverterRuntime:
    """Test InverterRuntime model."""

    def test_parse_runtime(self) -> None:
        """Test parsing inverter runtime data."""
        data = load_sample("runtime_1234567890.json")
        model = InverterRuntime.model_validate(data)

        assert model.success is True
        assert model.serialNum == "1234567890"
        assert model.soc == 71
        assert model.ppv == 0  # Total PV power
        assert model.pToUser == 1030  # Power to user

    def test_runtime_voltage_scaling(self) -> None:
        """Test that voltage values are correctly parsed."""
        data = load_sample("runtime_1234567890.json")
        model = InverterRuntime.model_validate(data)

        # Raw values
        assert model.vacr == 2411  # Should be divided by 100
        assert model.vBat == 530  # Should be divided by 100

        # Scaled values
        assert scale_voltage(model.vacr) == pytest.approx(24.11, rel=0.01)
        assert scale_voltage(model.vBat) == pytest.approx(5.30, rel=0.01)

    def test_runtime_frequency_scaling(self) -> None:
        """Test that frequency values are correctly scaled."""
        data = load_sample("runtime_1234567890.json")
        model = InverterRuntime.model_validate(data)

        # Raw value
        assert model.fac == 5998  # Should be divided by 100

        # Scaled value
        assert scale_frequency(model.fac) == pytest.approx(59.98, rel=0.01)


class TestEnergyInfo:
    """Test EnergyInfo model."""

    def test_parse_energy_info(self) -> None:
        """Test parsing energy statistics."""
        data = load_sample("energy_1234567890.json")
        model = EnergyInfo.model_validate(data)

        assert model.success is True
        assert model.serialNum == "1234567890"
        assert model.soc == 71

    def test_energy_conversion(self) -> None:
        """Test energy value conversion to kWh."""
        data = load_sample("energy_1234567890.json")
        model = EnergyInfo.model_validate(data)

        # Energy values are in Wh, convert to kWh
        total_usage_kwh = energy_to_kwh(model.totalUsage)
        assert isinstance(total_usage_kwh, float)


class TestBatteryInfo:
    """Test BatteryInfo model."""

    def test_parse_battery_info(self) -> None:
        """Test parsing battery information."""
        data = load_sample("battery_1234567890.json")
        model = BatteryInfo.model_validate(data)

        assert model.success is True
        assert model.serialNum == "1234567890"
        assert model.soc == 71
        assert len(model.batteryArray) > 0

    def test_battery_module_parsing(self) -> None:
        """Test parsing individual battery modules."""
        data = load_sample("battery_1234567890.json")
        model = BatteryInfo.model_validate(data)

        # Check first battery module
        battery = model.batteryArray[0]
        assert isinstance(battery, BatteryModule)
        assert battery.batteryKey.startswith("1234567890_Battery")
        assert battery.soc >= 0 and battery.soc <= 100
        assert battery.soh >= 0 and battery.soh <= 100

    def test_battery_cell_voltage_scaling(self) -> None:
        """Test that cell voltages are correctly scaled."""
        data = load_sample("battery_1234567890.json")
        model = BatteryInfo.model_validate(data)

        battery = model.batteryArray[0]

        # Cell voltages are in millivolts
        assert battery.batMaxCellVoltage > 3000  # Raw value
        assert battery.batMinCellVoltage > 3000  # Raw value

        # Scaled values (÷1000 for volts)
        max_voltage = scale_cell_voltage(battery.batMaxCellVoltage)
        min_voltage = scale_cell_voltage(battery.batMinCellVoltage)

        assert max_voltage >= 3.0 and max_voltage <= 4.2  # Typical lithium cell range
        assert min_voltage >= 3.0 and min_voltage <= 4.2

    def test_battery_key_obfuscation(self) -> None:
        """Test that battery keys are obfuscated."""
        data = load_sample("battery_1234567890.json")
        model = BatteryInfo.model_validate(data)

        # Note: We would need to add serializers to BatteryModule for this test
        # For now, just verify the data is parsed correctly
        battery = model.batteryArray[0]
        assert "_Battery" in battery.batteryKey


class TestMidboxRuntime:
    """Test MidboxRuntime model."""

    def test_parse_midbox_runtime(self) -> None:
        """Test parsing GridBOSS/MID runtime data."""
        data = load_sample("midbox_0987654321.json")
        model = MidboxRuntime.model_validate(data)

        assert model.success is True
        assert model.serialNum == "0987654321"
        assert model.midboxData is not None

    def test_midbox_voltage_scaling(self) -> None:
        """Test that GridBOSS voltages are correctly scaled."""
        data = load_sample("midbox_0987654321.json")
        model = MidboxRuntime.model_validate(data)

        # Raw values
        grid_volt = model.midboxData.gridRmsVolt
        assert grid_volt > 0

        # Scaled value (÷100 for volts)
        assert scale_voltage(grid_volt) > 0

    def test_midbox_frequency_scaling(self) -> None:
        """Test that GridBOSS frequency is correctly scaled."""
        data = load_sample("midbox_0987654321.json")
        model = MidboxRuntime.model_validate(data)

        # Raw value
        grid_freq = model.midboxData.gridFreq

        # Scaled value (÷100 for Hz)
        assert scale_frequency(grid_freq) == pytest.approx(59.98, rel=0.01)


class TestScalingFunctions:
    """Test scaling helper functions."""

    def test_scale_voltage(self) -> None:
        """Test voltage scaling."""
        assert scale_voltage(5100) == 51.0
        assert scale_voltage(2411) == 24.11

    def test_scale_current(self) -> None:
        """Test current scaling."""
        assert scale_current(1500) == 15.0
        assert scale_current(6000) == 60.0

    def test_scale_frequency(self) -> None:
        """Test frequency scaling."""
        assert scale_frequency(5998) == 59.98
        assert scale_frequency(6000) == 60.0

    def test_scale_cell_voltage(self) -> None:
        """Test cell voltage scaling."""
        assert scale_cell_voltage(3300) == 3.3
        assert scale_cell_voltage(3317) == 3.317

    def test_energy_to_kwh(self) -> None:
        """Test energy conversion to kWh."""
        assert energy_to_kwh(1000) == 1.0
        assert energy_to_kwh(69269) == 69.269


class TestDongleStatus:
    """Test DongleStatus model."""

    def test_parse_online_status(self) -> None:
        """Test parsing dongle status when online."""
        data = {"success": True, "msg": "current"}
        model = DongleStatus.model_validate(data)

        assert model.success is True
        assert model.msg == "current"
        assert model.is_online is True
        assert model.status_text == "Online"

    def test_parse_offline_status(self) -> None:
        """Test parsing dongle status when offline."""
        data = {"success": True, "msg": ""}
        model = DongleStatus.model_validate(data)

        assert model.success is True
        assert model.msg == ""
        assert model.is_online is False
        assert model.status_text == "Offline"

    def test_parse_missing_msg_defaults_to_empty(self) -> None:
        """Test that missing msg field defaults to empty string (offline)."""
        data = {"success": True}
        model = DongleStatus.model_validate(data)

        assert model.success is True
        assert model.msg == ""
        assert model.is_online is False
        assert model.status_text == "Offline"

    def test_parse_other_msg_values(self) -> None:
        """Test that only 'current' msg value indicates online status."""
        # Any value other than "current" should be considered offline
        data = {"success": True, "msg": "other"}
        model = DongleStatus.model_validate(data)

        assert model.is_online is False
        assert model.status_text == "Offline"

    def test_success_false(self) -> None:
        """Test handling of success=false response."""
        data = {"success": False, "msg": "error"}
        model = DongleStatus.model_validate(data)

        assert model.success is False
        # Even with success=false, the msg value should be preserved
        assert model.msg == "error"


class TestDatalogListResponse:
    """Test DatalogListItem and DatalogListResponse models."""

    def test_parse_datalog_list(self) -> None:
        """Test parsing datalog list response."""
        from pylxpweb.models import DatalogListItem, DatalogListResponse

        data = {
            "total": 2,
            "rows": [
                {
                    "datalogSn": "BC34000380",
                    "plantId": 19147,
                    "plantName": "Test Plant",
                    "endUserAccount": "testuser",
                    "datalogType": "WLAN",
                    "datalogTypeText": "WLAN",
                    "createDate": "2025-06-19",
                    "lost": False,
                    "serverId": 1,
                    "lastUpdateTime": "2026-01-14 17:35:16",
                },
                {
                    "datalogSn": "BC42900293",
                    "plantId": 19147,
                    "plantName": "Test Plant",
                    "endUserAccount": "testuser",
                    "datalogType": "WLAN",
                    "datalogTypeText": "WLAN",
                    "createDate": "2025-06-19",
                    "lost": True,
                    "serverId": 5,
                    "lastUpdateTime": "2026-01-14 17:33:56",
                },
            ],
        }
        model = DatalogListResponse.model_validate(data)

        assert model.total == 2
        assert len(model.rows) == 2

        # First datalog is online (lost=False)
        assert model.rows[0].datalogSn == "BC34000380"
        assert model.rows[0].lost is False
        assert model.rows[0].is_online is True
        assert model.rows[0].status_text == "Online"

        # Second datalog is offline (lost=True)
        assert model.rows[1].datalogSn == "BC42900293"
        assert model.rows[1].lost is True
        assert model.rows[1].is_online is False
        assert model.rows[1].status_text == "Offline"

    def test_get_status_by_serial(self) -> None:
        """Test get_status_by_serial helper method."""
        from pylxpweb.models import DatalogListResponse

        data = {
            "total": 2,
            "rows": [
                {
                    "datalogSn": "BC34000380",
                    "plantId": 19147,
                    "plantName": "Test",
                    "endUserAccount": "test",
                    "datalogType": "WLAN",
                    "datalogTypeText": "WLAN",
                    "createDate": "2025-06-19",
                    "lost": False,
                    "serverId": 1,
                    "lastUpdateTime": "2026-01-14 17:35:16",
                },
                {
                    "datalogSn": "BC42900293",
                    "plantId": 19147,
                    "plantName": "Test",
                    "endUserAccount": "test",
                    "datalogType": "WLAN",
                    "datalogTypeText": "WLAN",
                    "createDate": "2025-06-19",
                    "lost": True,
                    "serverId": 5,
                    "lastUpdateTime": "2026-01-14 17:33:56",
                },
            ],
        }
        model = DatalogListResponse.model_validate(data)

        # Known serials
        assert model.get_status_by_serial("BC34000380") is True  # Online
        assert model.get_status_by_serial("BC42900293") is False  # Offline

        # Unknown serial
        assert model.get_status_by_serial("BC00000000") is None
