"""Production-path boundary tests for firmware-supported holding-register ranges."""

from unittest.mock import AsyncMock, Mock

import pytest

from pylxpweb import LuxpowerClient
from pylxpweb.devices.inverters.hybrid import HybridInverter
from pylxpweb.endpoints.control import ControlEndpoints

SERIAL = "TEST000001"


def _cloud_inverter() -> tuple[HybridInverter, Mock]:
    """Build an inverter whose real cloud control endpoint stops at mocked HTTP."""
    client = Mock(spec=LuxpowerClient)
    client._ensure_authenticated = AsyncMock()
    client._request = AsyncMock(return_value={"success": True})
    client.invalidate_cache_for_device = Mock()
    client.api = Mock()
    client.api.control = ControlEndpoints(client)
    return HybridInverter(client=client, serial_number=SERIAL, model="FlexBOSS21"), client


@pytest.mark.asyncio
async def test_h66_raw_boundaries_use_local_and_cloud_write_conversions() -> None:
    """H66 raw 0 and 100 write; -1 and 101 fail before local or cloud I/O (#272)."""
    transport = Mock()
    transport.write_named_parameters = AsyncMock(return_value=True)
    transport.write_parameters = AsyncMock(return_value=True)
    local = HybridInverter(
        client=Mock(spec=LuxpowerClient),
        serial_number=SERIAL,
        model="FlexBOSS21",
        transport=transport,
    )

    for value in (0, 100):
        assert await local.set_ac_charge(True, power_percent=value) is True
    assert {66: 0} in [call.args[0] for call in transport.write_parameters.await_args_list]
    assert {66: 100} in [call.args[0] for call in transport.write_parameters.await_args_list]

    writes_before = transport.write_parameters.await_count
    for value in (101, -1):
        with pytest.raises(ValueError, match="power_percent must be between 0 and 100"):
            await local.set_ac_charge(True, power_percent=value)
    assert transport.write_parameters.await_count == writes_before

    cloud, client = _cloud_inverter()
    for value in (0, 100):
        assert await cloud.set_ac_charge(True, power_percent=value) is True
    payloads = [call.kwargs["data"] for call in client._request.await_args_list]
    assert any(
        data.get("holdParam") == "HOLD_AC_CHARGE_POWER_CMD" and data.get("valueText") == "0"
        for data in payloads
    )
    assert any(
        data.get("holdParam") == "HOLD_AC_CHARGE_POWER_CMD" and data.get("valueText") == "10"
        for data in payloads
    )

    writes_before = client._request.await_count
    for value in (101, -1):
        with pytest.raises(ValueError, match="power_percent must be between 0 and 100"):
            await cloud.set_ac_charge(True, power_percent=value)
    assert client._request.await_count == writes_before


@pytest.mark.asyncio
async def test_h66_engineering_boundaries_reach_named_cloud_write() -> None:
    """H66 accepts 0.0 and 10.0 kW, while adjacent tenths fail before cloud I/O (#272)."""
    inverter, client = _cloud_inverter()

    for value in (0.0, 10.0):
        assert await inverter.set_ac_charge_power(value) is True
    payloads = [call.kwargs["data"] for call in client._request.await_args_list]
    assert [data["valueText"] for data in payloads] == ["0.0", "10.0"]

    writes_before = client._request.await_count
    for value in (10.1, -0.1):
        with pytest.raises(ValueError, match="between 0.0 and 10.0 kW"):
            await inverter.set_ac_charge_power(value)
    assert client._request.await_count == writes_before


@pytest.mark.asyncio
async def test_h160_boundaries_use_local_and_cloud_write_paths() -> None:
    """H160 writes 1 and 90; 0 and 91 fail before local or cloud I/O (#271)."""
    transport = Mock()
    transport.write_parameters = AsyncMock(return_value=True)
    local = HybridInverter(
        client=Mock(spec=LuxpowerClient),
        serial_number=SERIAL,
        model="FlexBOSS21",
        transport=transport,
    )

    for value in (1, 90):
        assert await local.set_ac_charge_soc_limits(value, 100) is True
    assert [call.args[0][160] for call in transport.write_parameters.await_args_list] == [1, 90]

    writes_before = transport.write_parameters.await_count
    for value in (0, 91):
        with pytest.raises(ValueError, match="start_soc must be 1-90"):
            await local.set_ac_charge_soc_limits(value, 100)
    assert transport.write_parameters.await_count == writes_before

    cloud, client = _cloud_inverter()
    for value in (1, 90):
        assert await cloud.set_ac_charge_soc_limits(value, 100) is True
    payloads = [call.kwargs["data"] for call in client._request.await_args_list]
    assert [
        data["valueText"]
        for data in payloads
        if data.get("holdParam") == "HOLD_AC_CHARGE_START_BATTERY_SOC"
    ] == ["1", "90"]

    writes_before = client._request.await_count
    for value in (0, 91):
        with pytest.raises(ValueError, match="start_soc must be 1-90"):
            await cloud.set_ac_charge_soc_limits(value, 100)
    assert client._request.await_count == writes_before

    _, direct_client = _cloud_inverter()
    control = direct_client.api.control
    for value in (1, 90):
        assert (await control.set_ac_charge_soc_limits(SERIAL, value, 100)).success is True
    writes_before = direct_client._request.await_count
    for value in (0, 91):
        with pytest.raises(ValueError, match="start_soc must be 1-90"):
            await control.set_ac_charge_soc_limits(SERIAL, value, 100)
    assert direct_client._request.await_count == writes_before
