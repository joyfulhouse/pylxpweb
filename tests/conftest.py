"""Pytest configuration and fixtures for pylxpweb tests."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from aioresponses import aioresponses


def is_ci_environment() -> bool:
    """Check if running in CI environment."""
    return os.getenv("CI") is not None or os.getenv("GITHUB_ACTIONS") is not None


def redact_sensitive(value: str, redact_type: str = "serial") -> str:
    """Redact sensitive information if running in CI.

    Args:
        value: Value to potentially redact
        redact_type: Type of redaction - "serial", "name", "address", "coord"

    Returns:
        Original value if not in CI, redacted value if in CI
    """
    if not is_ci_environment():
        return value

    if redact_type == "serial":
        # Redact serial numbers (10-digit numbers)
        if value.isdigit() and len(value) == 10:
            return f"{value[:2]}****{value[-2:]}"
    elif redact_type == "name":
        # Redact plant/station names
        return "[REDACTED_NAME]"
    elif redact_type == "address":
        # Redact addresses
        return "[REDACTED_ADDRESS]"
    elif redact_type == "coord":
        # Redact coordinates (show only 1 decimal place)
        try:
            coord = float(value)
            return f"{coord:.1f}"
        except (ValueError, TypeError):
            return "[REDACTED_COORD]"

    return value


# Pytest plugin to redact output in CI
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    """Hook to redact sensitive information from test output in CI."""
    if is_ci_environment():
        # Capture original stdout/stderr
        import sys
        from io import StringIO

        original_stdout = sys.stdout
        original_stderr = sys.stderr

        # Create capturing streams
        stdout_capture = StringIO()
        stderr_capture = StringIO()

        # Redirect output
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        try:
            # Run the test
            outcome = yield
        finally:
            # Restore original streams
            sys.stdout = original_stdout
            sys.stderr = original_stderr

            # Get captured output
            stdout_text = stdout_capture.getvalue()
            stderr_text = stderr_capture.getvalue()

            # Redact sensitive patterns
            import re

            # Redact 10-digit serial numbers
            stdout_text = re.sub(
                r"\b\d{10}\b", lambda m: f"{m.group()[:2]}****{m.group()[-2:]}", stdout_text
            )
            stderr_text = re.sub(
                r"\b\d{10}\b", lambda m: f"{m.group()[:2]}****{m.group()[-2:]}", stderr_text
            )

            # Write redacted output
            if stdout_text:
                original_stdout.write(stdout_text)
            if stderr_text:
                original_stderr.write(stderr_text)

        return outcome
    else:
        # Not in CI, run normally
        yield


# Load sample API responses
SAMPLES_DIR = Path(__file__).parent / "samples"


def load_sample(filename: str) -> dict[str, Any]:
    """Load a sample JSON response file."""
    file_path = SAMPLES_DIR / filename
    with open(file_path) as f:
        result: dict[str, Any] = json.load(f)
        return result


@pytest.fixture
def login_response() -> dict[str, Any]:
    """Sample login response."""
    return load_sample("login.json")


@pytest.fixture
def plants_response() -> dict[str, Any]:
    """Sample plants list response."""
    data = load_sample("plants.json")
    return {"total": len(data), "rows": data}


@pytest.fixture
def runtime_response() -> dict[str, Any]:
    """Sample inverter runtime response."""
    return load_sample("runtime_1234567890.json")


@pytest.fixture
def energy_response() -> dict[str, Any]:
    """Sample energy info response."""
    return load_sample("energy_1234567890.json")


@pytest.fixture
def battery_response() -> dict[str, Any]:
    """Sample battery info response."""
    return load_sample("battery_1234567890.json")


@pytest.fixture
def midbox_response() -> dict[str, Any]:
    """Sample GridBOSS/MID runtime response."""
    return load_sample("midbox_0987654321.json")


@pytest.fixture
def parallel_energy_response() -> dict[str, Any]:
    """Sample parallel group energy response."""
    return load_sample("parallel_energy_1234567890.json")


@pytest.fixture
def firmware_check_response() -> dict[str, Any]:
    """Sample firmware check response with updates available."""
    return {
        "success": True,
        "details": {
            "serialNum": "1234567890",
            "deviceType": 6,
            "standard": "fAAB",
            "firmwareType": "PCS",
            "fwCodeBeforeUpload": "fAAB-2122",
            "v1": 33,
            "v2": 34,
            "v3Value": 0,
            "lastV1": 37,
            "lastV1FileName": "FAAB-25xx_20250925_App.hex",
            "lastV2": 37,
            "lastV2FileName": "fAAB-xx25_Para375_20250925.hex",
            "m3Version": 33,
            "pcs1UpdateMatch": True,
            "pcs2UpdateMatch": True,
            "pcs3UpdateMatch": False,
            "needRunStep2": False,
            "needRunStep3": False,
            "needRunStep4": False,
            "needRunStep5": False,
            "midbox": False,
            "lowVoltBattery": True,
            "type6": True,
        },
        "infoForwardUrl": "http://os.solarcloudsystem.com/#/apiLogin?...",
    }


@pytest.fixture
def firmware_check_no_update_response() -> dict[str, Any]:
    """Sample firmware check response with no updates available."""
    return {
        "success": True,
        "details": {
            "serialNum": "1234567890",
            "deviceType": 6,
            "standard": "fAAB",
            "firmwareType": "PCS",
            "fwCodeBeforeUpload": "fAAB-2525",
            "v1": 37,
            "v2": 37,
            "v3Value": 0,
            "lastV1": 37,
            "lastV1FileName": "FAAB-25xx_20250925_App.hex",
            "lastV2": 37,
            "lastV2FileName": "fAAB-xx25_Para375_20250925.hex",
            "m3Version": 33,
            "pcs1UpdateMatch": True,
            "pcs2UpdateMatch": True,
            "pcs3UpdateMatch": False,
            "needRunStep2": False,
            "needRunStep3": False,
            "needRunStep4": False,
            "needRunStep5": False,
            "midbox": False,
            "lowVoltBattery": True,
            "type6": True,
        },
        "infoForwardUrl": "http://os.solarcloudsystem.com/#/apiLogin?...",
    }


@pytest.fixture
def firmware_status_response() -> dict[str, Any]:
    """Sample firmware update status response."""
    return {
        "receiving": False,
        "progressing": False,
        "fileReady": False,
        "deviceInfos": [
            {
                "inverterSn": "1234567890",
                "startTime": "2025-11-18 19:16:59",
                "stopTime": "2025-11-18 19:23:21",
                "standardUpdate": True,
                "firmware": "FAAB-25xx",
                "firmwareType": "PCS",
                "updateStatus": "SUCCESS",
                "isSendStartUpdate": True,
                "isSendEndUpdate": True,
                "packageIndex": 560,
                "updateRate": "100% - 561 / 561",
            }
        ],
    }


@pytest.fixture
def firmware_status_in_progress_response() -> dict[str, Any]:
    """Sample firmware update status response with update in progress."""
    return {
        "receiving": False,
        "progressing": True,
        "fileReady": False,
        "deviceInfos": [
            {
                "inverterSn": "1234567890",
                "startTime": "2025-11-18 19:16:59",
                "stopTime": "",
                "standardUpdate": True,
                "firmware": "FAAB-25xx",
                "firmwareType": "PCS",
                "updateStatus": "UPLOADING",
                "isSendStartUpdate": True,
                "isSendEndUpdate": False,
                "packageIndex": 439,
                "updateRate": "78% - 439 / 561",
            }
        ],
    }


@pytest.fixture
def eligibility_allowed_response() -> dict[str, Any]:
    """Sample eligibility response - allowed."""
    return {"success": True, "msg": "allowToUpdate"}


@pytest.fixture
def eligibility_device_updating_response() -> dict[str, Any]:
    """Sample eligibility response - device updating."""
    return {"success": True, "msg": "deviceUpdating"}


@pytest.fixture
def eligibility_parallel_updating_response() -> dict[str, Any]:
    """Sample eligibility response - parallel group updating."""
    return {"success": True, "msg": "parallelGroupUpdating"}


@pytest.fixture
def firmware_api_error_response() -> dict[str, Any]:
    """Sample API error response for firmware operations."""
    return {"success": False, "message": "Device not found"}


@pytest.fixture
async def mock_api_server(
    login_response: dict[str, Any],
    plants_response: dict[str, Any],
    runtime_response: dict[str, Any],
    energy_response: dict[str, Any],
    battery_response: dict[str, Any],
    midbox_response: dict[str, Any],
    parallel_energy_response: dict[str, Any],
    firmware_check_response: dict[str, Any],
    firmware_status_response: dict[str, Any],
    eligibility_allowed_response: dict[str, Any],
) -> AsyncGenerator[TestServer, None]:
    """Create a mock API server for testing.

    This fixture creates an aiohttp test server that mimics the Luxpower API.
    """

    async def handle_login(request: web.Request) -> web.Response:
        """Handle login requests."""
        data = await request.post()
        if data.get("account") == "testuser" and data.get("password") == "testpass":
            return web.json_response(login_response)
        return web.json_response({"success": False, "message": "Invalid credentials"}, status=401)

    async def handle_plants(request: web.Request) -> web.Response:
        """Handle plant list and plant details requests."""
        data = await request.post()
        # If targetPlantId is provided, return plant details
        if data.get("targetPlantId"):
            target_plant_id = data.get("targetPlantId")
            # Convert to string first to handle different types
            plant_id = int(str(target_plant_id)) if target_plant_id else 0
            return web.json_response(
                {
                    "success": True,
                    "total": 1,
                    "rows": [
                        {
                            "plantId": plant_id,
                            "name": "My Solar Station",
                            "country": "United States of America",
                            "timezone": "GMT -8",
                            "createDate": "2024-01-01",
                            "daylightSavingTime": False,
                            "nominalPower": "10.0",
                        }
                    ],
                }
            )
        # Otherwise return plant list
        return web.json_response(plants_response)

    async def handle_devices(request: web.Request) -> web.Response:
        """Handle device list requests."""
        # Create a simplified device list from login response
        devices = login_response["plants"][0]["inverters"]
        return web.json_response({"success": True, "rows": devices})

    async def handle_parallel_groups(request: web.Request) -> web.Response:
        """Handle parallel group details requests."""
        # Create parallel group structure from login data
        groups = [
            {
                "parallelGroup": "A",
                "devices": [login_response["plants"][0]["inverters"][0]],
            }
        ]
        return web.json_response({"success": True, "parallelGroups": groups})

    async def handle_runtime(request: web.Request) -> web.Response:
        """Handle inverter runtime requests."""
        return web.json_response(runtime_response)

    async def handle_energy(request: web.Request) -> web.Response:
        """Handle energy info requests."""
        return web.json_response(energy_response)

    async def handle_parallel_energy(request: web.Request) -> web.Response:
        """Handle parallel group energy requests."""
        return web.json_response(parallel_energy_response)

    async def handle_battery(request: web.Request) -> web.Response:
        """Handle battery info requests."""
        return web.json_response(battery_response)

    async def handle_midbox(request: web.Request) -> web.Response:
        """Handle GridBOSS/MID runtime requests."""
        return web.json_response(midbox_response)

    async def handle_read_params(request: web.Request) -> web.Response:
        """Handle parameter read requests."""
        return web.json_response(
            {
                "success": True,
                "inverterSn": "1234567890",
                "deviceType": 624320,
                "startRegister": 0,
                "pointNumber": 127,
                "valueFrame": "0000000000000000",
                "HOLD_SYSTEM_CHARGE_SOC_LIMIT": 100,
                "HOLD_SYSTEM_DISCHARGE_SOC_LIMIT": 10,
            }
        )

    async def handle_write_param(request: web.Request) -> web.Response:
        """Handle parameter write requests."""
        return web.json_response({"success": True, "message": "Parameter updated"})

    async def handle_function_control(request: web.Request) -> web.Response:
        """Handle function control requests."""
        return web.json_response({"success": True, "message": "Function updated"})

    async def handle_quick_charge_start(request: web.Request) -> web.Response:
        """Handle quick charge start requests."""
        return web.json_response({"success": True, "message": "Quick charge started"})

    async def handle_quick_charge_stop(request: web.Request) -> web.Response:
        """Handle quick charge stop requests."""
        return web.json_response({"success": True, "message": "Quick charge stopped"})

    async def handle_quick_charge_status(request: web.Request) -> web.Response:
        """Handle quick charge status requests."""
        return web.json_response({"success": True, "hasUnclosedQuickChargeTask": False})

    async def handle_firmware_check(request: web.Request) -> web.Response:
        """Handle firmware update check requests."""
        return web.json_response(firmware_check_response)

    async def handle_firmware_status(request: web.Request) -> web.Response:
        """Handle firmware update status requests."""
        return web.json_response(firmware_status_response)

    async def handle_check_eligibility(request: web.Request) -> web.Response:
        """Handle firmware update eligibility check requests."""
        return web.json_response(eligibility_allowed_response)

    async def handle_start_update(request: web.Request) -> web.Response:
        """Handle start firmware update requests."""
        return web.json_response({"success": True, "message": "Update started"})

    async def handle_plant_overview(request: web.Request) -> web.Response:
        """Handle plant overview requests."""
        return web.json_response(
            {
                "success": True,
                "total": 1,
                "rows": [
                    {
                        "plantId": 99999,
                        "name": "My Solar Station",
                        "ppv": 5000,
                        "eToday": 25.5,
                    }
                ],
            }
        )

    async def handle_plant_details(request: web.Request) -> web.Response:
        """Handle plant details requests."""
        return web.json_response(
            {
                "success": True,
                "total": 1,
                "rows": [
                    {
                        "plantId": 99999,
                        "name": "My Solar Station",
                        "country": "United States of America",
                        "timezone": "GMT -8",
                        "createDate": "2024-01-01",
                        "daylightSavingTime": False,
                        "nominalPower": "10.0",
                    }
                ],
            }
        )

    async def handle_plant_update(request: web.Request) -> web.Response:
        """Handle plant configuration update requests."""
        return web.json_response({"success": True, "message": "Plant configuration updated"})

    async def handle_locale_region(request: web.Request) -> web.Response:
        """Handle locale region requests."""
        # Return regions based on the continent parameter
        await request.post()

        # Return appropriate regions for each continent
        # Start with North America for testing
        return web.json_response(
            [
                {"value": "NORTH_AMERICA", "text": "North America"},
                {"value": "CENTRAL_AMERICA", "text": "Central America"},
            ]
        )

    async def handle_locale_country(request: web.Request) -> web.Response:
        """Handle locale country requests."""
        return web.json_response(
            [
                {"value": "UNITED_STATES_OF_AMERICA", "text": "United States of America"},
                {"value": "CANADA", "text": "Canada"},
            ]
        )

    async def handle_analytics(request: web.Request) -> web.Response:
        """Handle analytics and chart data requests."""
        return web.json_response(
            {
                "success": True,
                "data": {
                    "timestamps": ["00:00", "01:00", "02:00"],
                    "values": [0, 100, 200],
                },
            }
        )

    async def handle_export(request: web.Request) -> web.Response:
        """Handle data export requests."""
        # Return mock CSV/Excel data as bytes
        return web.Response(
            body=b"Plant ID,Date,Energy\n99999,2024-01-01,25.5\n", content_type="text/csv"
        )

    async def handle_forecasting(request: web.Request) -> web.Response:
        """Handle weather and production forecast requests."""
        return web.json_response(
            {
                "success": True,
                "forecast": {
                    "today": {"temperature": 72, "condition": "sunny", "production": 30.5},
                    "tomorrow": {
                        "temperature": 68,
                        "condition": "partly_cloudy",
                        "production": 28.0,
                    },
                },
            }
        )

    # Create application with routes
    app = web.Application()
    app.router.add_post("/WManage/api/login", handle_login)
    app.router.add_post("/WManage/web/config/plant/list/viewer", handle_plants)
    app.router.add_post("/WManage/api/inverterOverview/list", handle_devices)
    app.router.add_post(
        "/WManage/api/inverterOverview/getParallelGroupDetails", handle_parallel_groups
    )
    app.router.add_post("/WManage/api/inverter/getInverterRuntime", handle_runtime)
    app.router.add_post("/WManage/api/inverter/getInverterEnergyInfo", handle_energy)
    app.router.add_post(
        "/WManage/api/inverter/getInverterEnergyInfoParallel", handle_parallel_energy
    )
    app.router.add_post("/WManage/api/battery/getBatteryInfo", handle_battery)
    app.router.add_post("/WManage/api/midbox/getMidboxRuntime", handle_midbox)
    app.router.add_post("/WManage/web/maintain/remoteRead/read", handle_read_params)
    app.router.add_post("/WManage/web/maintain/remoteSet/write", handle_write_param)
    app.router.add_post("/WManage/web/maintain/remoteSet/functionControl", handle_function_control)
    app.router.add_post("/WManage/web/config/quickCharge/start", handle_quick_charge_start)
    app.router.add_post("/WManage/web/config/quickCharge/stop", handle_quick_charge_stop)
    app.router.add_post("/WManage/web/config/quickCharge/getStatusInfo", handle_quick_charge_status)
    app.router.add_post("/WManage/web/maintain/standardUpdate/checkUpdates", handle_firmware_check)
    app.router.add_post("/WManage/web/maintain/remoteUpdate/info", handle_firmware_status)
    app.router.add_post(
        "/WManage/web/maintain/standardUpdate/check12KParallelStatus",
        handle_check_eligibility,
    )
    app.router.add_post("/WManage/web/maintain/standardUpdate/run", handle_start_update)
    app.router.add_post("/WManage/api/plantOverview/list/viewer", handle_plant_overview)
    app.router.add_post("/WManage/web/config/plant/edit", handle_plant_update)
    app.router.add_post("/WManage/locale/region", handle_locale_region)
    app.router.add_post("/WManage/locale/country", handle_locale_country)

    # Analytics endpoints
    app.router.add_post("/WManage/api/analyze/chart/dayLine", handle_analytics)
    app.router.add_post("/WManage/api/analyze/energy/dayColumn", handle_analytics)
    app.router.add_post("/WManage/api/analyze/energy/monthColumn", handle_analytics)
    app.router.add_post("/WManage/api/analyze/energy/yearColumn", handle_analytics)
    app.router.add_post("/WManage/api/analyze/energy/totalColumn", handle_analytics)
    app.router.add_post("/WManage/api/analyze/event/list", handle_analytics)
    app.router.add_post("/WManage/api/battery/getBatteryInfoForSet", handle_analytics)
    app.router.add_post("/WManage/api/inverter/getInverterInfo", handle_analytics)

    # Export endpoints (handle both POST and GET for export)
    app.router.add_get("/WManage/web/analyze/data/export/{serial_num}/{start_date}", handle_export)

    # Forecasting endpoints
    app.router.add_post("/WManage/api/predict/solar/dayPredictColumnParallel", handle_forecasting)
    app.router.add_post("/WManage/api/weather/forecast", handle_forecasting)

    # Create and return test server
    server = TestServer(app)
    await server.start_server()
    yield server
    await server.close()


@pytest.fixture
async def test_client(mock_api_server: TestServer) -> TestClient[web.Request, web.Application]:
    """Create a test client for the mock API server."""
    return TestClient(mock_api_server)


@pytest.fixture
async def live_client():
    """Create authenticated client for integration tests.

    Loads credentials from environment variables or .env file:
    - LUXPOWER_USERNAME
    - LUXPOWER_PASSWORD
    - LUXPOWER_BASE_URL (optional, defaults to https://monitor.eg4electronics.com)
    - LUXPOWER_IANA_TIMEZONE (optional, defaults to America/Los_Angeles)

    Skips test if credentials are not configured.
    """
    import os
    from pathlib import Path

    from dotenv import load_dotenv

    from pylxpweb import LuxpowerClient

    # Load .env file from project root
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    username = os.getenv("LUXPOWER_USERNAME")
    password = os.getenv("LUXPOWER_PASSWORD")
    base_url = os.getenv("LUXPOWER_BASE_URL", "https://monitor.eg4electronics.com")
    iana_timezone = os.getenv("LUXPOWER_IANA_TIMEZONE", "America/Los_Angeles")

    if not username or not password:
        pytest.skip("Live API credentials not configured (LUXPOWER_USERNAME, LUXPOWER_PASSWORD)")

    async with LuxpowerClient(
        username, password, base_url=base_url, iana_timezone=iana_timezone
    ) as client:
        yield client


@pytest.fixture
def mocked_api() -> Generator[aioresponses, None, None]:
    """Create aioresponses mock for HTTP requests.

    This fixture provides a context manager for mocking aiohttp requests
    using the aioresponses library.
    """
    with aioresponses() as m:
        yield m
