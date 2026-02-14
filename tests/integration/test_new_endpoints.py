"""Integration tests for newly discovered endpoints."""

import pytest

from pylxpweb import LuxpowerClient

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_plant_overview(live_client: LuxpowerClient) -> None:
    """Test plant overview endpoint with real-time metrics."""
    response = await live_client._request(
        "POST", "/WManage/api/plantOverview/list/viewer", data={"searchText": ""}
    )

    assert response["success"] is True
    assert "total" in response
    assert "rows" in response
    assert len(response["rows"]) > 0

    plant = response["rows"][0]

    # Verify real-time power metrics
    assert "ppv" in plant
    assert "pCharge" in plant
    assert "pDisCharge" in plant
    assert "pConsumption" in plant

    # Verify energy totals
    assert "todayYielding" in plant
    assert "totalYielding" in plant

    # Verify inverter details
    assert "inverters" in plant
    assert len(plant["inverters"]) > 0


@pytest.mark.asyncio
async def test_inverter_overview_list(live_client: LuxpowerClient) -> None:
    """Test inverter overview list endpoint."""
    response = await live_client._request(
        "POST",
        "/WManage/api/inverterOverview/list",
        data={
            "page": 1,
            "rows": 30,
            "plantId": -1,  # All plants
            "searchText": "",
            "statusText": "all",
        },
    )

    assert response["success"] is True
    assert "total" in response
    assert "rows" in response

    if response["total"] > 0:
        inverter = response["rows"][0]

        # Verify inverter identification
        assert "serialNum" in inverter
        assert "deviceType" in inverter
        assert "deviceTypeText" in inverter
        assert "plantId" in inverter

        # Verify parallel info
        assert "parallelGroup" in inverter
        assert "parallelIndex" in inverter


@pytest.mark.asyncio
async def test_inverter_overview_list_pagination(live_client: LuxpowerClient) -> None:
    """Test inverter overview pagination."""
    # Page 1
    page1 = await live_client._request(
        "POST",
        "/WManage/api/inverterOverview/list",
        data={"page": 1, "rows": 1, "plantId": -1, "searchText": "", "statusText": "all"},
    )

    assert page1["success"] is True
    assert len(page1["rows"]) <= 1

    if page1["total"] > 1:
        # Page 2
        page2 = await live_client._request(
            "POST",
            "/WManage/api/inverterOverview/list",
            data={"page": 2, "rows": 1, "plantId": -1, "searchText": "", "statusText": "all"},
        )

        assert page2["success"] is True
        # Different inverters on different pages
        if len(page2["rows"]) > 0:
            assert page1["rows"][0]["serialNum"] != page2["rows"][0]["serialNum"]


@pytest.mark.asyncio
async def test_inverter_overview_filter_by_plant(live_client: LuxpowerClient) -> None:
    """Test filtering inverters by specific plant."""
    # Get a plant ID
    plants = await live_client.plants.get_plants()
    plant_id = plants.rows[0].plantId

    response = await live_client._request(
        "POST",
        "/WManage/api/inverterOverview/list",
        data={
            "page": 1,
            "rows": 30,
            "plantId": plant_id,  # Specific plant
            "searchText": "",
            "statusText": "all",
        },
    )

    assert response["success"] is True

    # All inverters should belong to this plant
    for inverter in response["rows"]:
        assert inverter["plantId"] == plant_id


@pytest.mark.asyncio
async def test_locale_region_endpoint(live_client: LuxpowerClient) -> None:
    """Test locale region endpoint."""
    session = await live_client._get_session()

    async with session.post(
        f"{live_client.base_url}/WManage/locale/region",
        data="continent=NORTH_AMERICA",
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
    ) as resp:
        assert resp.status == 200
        text = await resp.text()

        import json

        regions = json.loads(text)

        assert isinstance(regions, list)
        assert len(regions) > 0

        # Verify structure
        region = regions[0]
        assert "value" in region
        assert "text" in region


@pytest.mark.asyncio
async def test_locale_country_endpoint(live_client: LuxpowerClient) -> None:
    """Test locale country endpoint."""
    session = await live_client._get_session()

    async with session.post(
        f"{live_client.base_url}/WManage/locale/country",
        data="region=NORTH_AMERICA",
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
    ) as resp:
        assert resp.status == 200
        text = await resp.text()

        import json

        countries = json.loads(text)

        assert isinstance(countries, list)
        assert len(countries) > 0

        # Verify structure
        country = countries[0]
        assert "value" in country
        assert "text" in country


@pytest.mark.asyncio
async def test_plant_list_with_target_id(live_client: LuxpowerClient) -> None:
    """Test plant list viewer with targetPlantId parameter."""
    plants = await live_client.plants.get_plants()
    plant_id = plants.rows[0].plantId

    response = await live_client._request(
        "POST",
        "/WManage/web/config/plant/list/viewer",
        data={
            "page": 1,
            "rows": 10,
            "searchText": "",
            "targetPlantId": str(plant_id),
            "sort": "createDate",
            "order": "desc",
        },
    )

    assert "total" in response
    assert "rows" in response
    assert len(response["rows"]) == 1
    assert response["rows"][0]["plantId"] == plant_id
