import httpx

from tests.helpers import create_vehicle


async def test_vehicle_upsert_is_versioned_and_idempotent(
    client: httpx.AsyncClient,
    service_headers: dict[str, str],
) -> None:
    vehicle_id = "00000000-0000-4000-8000-000000000011"

    created = await create_vehicle(client, service_headers, vehicle_id)
    replay = await create_vehicle(client, service_headers, vehicle_id)
    stale = await create_vehicle(client, service_headers, vehicle_id, source_version=0)
    conflict = await client.put(
        f"/internal/v1/vehicles/{vehicle_id}",
        headers=service_headers,
        json={
            "brand": "Outra",
            "model": "Corolla",
            "year": 2025,
            "color": "Prata",
            "price": "100000.00",
            "status": "AVAILABLE",
            "source_version": 1,
        },
    )
    updated = await create_vehicle(
        client,
        service_headers,
        vehicle_id,
        price="99000.00",
        source_version=2,
    )

    assert created.status_code == 201
    assert replay.status_code == 200
    assert stale.status_code == 422
    assert conflict.status_code == 409
    assert updated.status_code == 200
    assert updated.json()["price"] == "99000.00"


async def test_vehicle_upsert_rejects_stale_version_and_external_state_change(
    client: httpx.AsyncClient,
    service_headers: dict[str, str],
) -> None:
    vehicle_id = "00000000-0000-4000-8000-000000000012"
    await create_vehicle(client, service_headers, vehicle_id, source_version=2)

    stale = await create_vehicle(client, service_headers, vehicle_id, source_version=1)
    state_change = await create_vehicle(
        client,
        service_headers,
        vehicle_id,
        source_version=3,
        status="SOLD",
    )

    assert stale.status_code == 409
    assert state_change.status_code == 409


async def test_available_list_is_filtered_sorted_and_paginated(
    client: httpx.AsyncClient,
    service_headers: dict[str, str],
) -> None:
    ids = [
        "00000000-0000-4000-8000-000000000021",
        "00000000-0000-4000-8000-000000000022",
        "00000000-0000-4000-8000-000000000023",
    ]
    await create_vehicle(client, service_headers, ids[0], price="90000.00")
    await create_vehicle(client, service_headers, ids[1], price="50000.00")
    await create_vehicle(client, service_headers, ids[2], price="50000.00")

    response = await client.get("/api/v1/vehicles/available?limit=2&offset=0")

    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert [item["id"] for item in response.json()["items"]] == [ids[1], ids[2]]


async def test_vehicle_input_validation(client: httpx.AsyncClient, service_headers) -> None:
    response = await client.put(
        "/internal/v1/vehicles/00000000-0000-4000-8000-000000000031",
        headers=service_headers,
        json={
            "brand": "   ",
            "model": "Model",
            "year": 9999,
            "color": "Azul",
            "price": "0",
            "status": "AVAILABLE",
            "source_version": 1,
        },
    )

    assert response.status_code == 422
