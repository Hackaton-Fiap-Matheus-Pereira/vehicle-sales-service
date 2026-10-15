from datetime import date, timedelta

import httpx
from app.enums import VehicleStatus

from tests.helpers import create_purchase, create_vehicle


async def test_purchase_reserves_vehicle_masks_cpf_and_can_be_queried(
    client: httpx.AsyncClient,
    service_headers: dict[str, str],
    fake_core_client,
) -> None:
    vehicle_id = "00000000-0000-4000-8000-000000000101"
    cpf = "52998224725"
    await create_vehicle(client, service_headers, vehicle_id)

    response = await create_purchase(client, vehicle_id, cpf=cpf)
    body = response.json()
    lookup = await client.get(f"/api/v1/purchases/{body['payment_code']}")
    available = await client.get("/api/v1/vehicles/available")

    assert response.status_code == 201
    assert body["buyer_cpf_masked"] == "***.***.***-25"
    assert cpf not in response.text
    assert body["status"] == "PENDING"
    assert body["catalog_sync_status"] == "SYNCED"
    assert lookup.status_code == 200
    assert cpf not in lookup.text
    assert available.json()["total"] == 0
    assert fake_core_client.calls[-1] == (vehicle_id, VehicleStatus.RESERVED)


async def test_purchase_idempotency_returns_original_and_detects_payload_mismatch(
    client: httpx.AsyncClient,
    service_headers: dict[str, str],
) -> None:
    vehicle_id = "00000000-0000-4000-8000-000000000102"
    await create_vehicle(client, service_headers, vehicle_id)

    first = await create_purchase(client, vehicle_id, idempotency_key="purchase-key")
    replay = await create_purchase(client, vehicle_id, idempotency_key="purchase-key")
    mismatch = await client.post(
        "/api/v1/purchases",
        headers={"Idempotency-Key": "purchase-key"},
        json={
            "vehicle_id": vehicle_id,
            "buyer_cpf": "52998224725",
            "purchase_date": (date.today() - timedelta(days=1)).isoformat(),
        },
    )

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert mismatch.status_code == 409


async def test_purchase_rejects_invalid_data_and_unavailable_vehicle(
    client: httpx.AsyncClient,
    service_headers: dict[str, str],
) -> None:
    vehicle_id = "00000000-0000-4000-8000-000000000103"
    await create_vehicle(client, service_headers, vehicle_id)
    await create_purchase(client, vehicle_id)

    duplicate = await create_purchase(client, vehicle_id)
    bad_cpf = await create_purchase(client, vehicle_id, cpf="11111111111")
    future = await client.post(
        "/api/v1/purchases",
        json={
            "vehicle_id": vehicle_id,
            "buyer_cpf": "52998224725",
            "purchase_date": (date.today() + timedelta(days=1)).isoformat(),
        },
    )
    missing = await create_purchase(client, "00000000-0000-4000-8000-000000000999")

    assert duplicate.status_code == 409
    assert bad_cpf.status_code == 422
    assert future.status_code == 422
    assert missing.status_code == 404


async def test_failed_core_sync_can_be_retried(
    client: httpx.AsyncClient,
    service_headers: dict[str, str],
    fake_core_client,
) -> None:
    vehicle_id = "00000000-0000-4000-8000-000000000104"
    await create_vehicle(client, service_headers, vehicle_id)
    fake_core_client.fail = True

    purchase = await create_purchase(client, vehicle_id)
    assert purchase.json()["catalog_sync_status"] == "FAILED"

    fake_core_client.fail = False
    retried = await client.post(
        f"/internal/v1/purchases/{purchase.json()['id']}/sync",
        headers=service_headers,
    )

    assert retried.status_code == 200
    assert retried.json()["catalog_sync_status"] == "SYNCED"


async def test_purchase_lookup_not_found(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/purchases/unknown-code")
    assert response.status_code == 404
