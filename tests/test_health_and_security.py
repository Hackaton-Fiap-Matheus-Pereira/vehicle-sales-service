import httpx


async def test_liveness_and_readiness(client: httpx.AsyncClient) -> None:
    live = await client.get("/health/live")
    ready = await client.get("/health/ready")

    assert live.status_code == 200
    assert live.json()["status"] == "ok"
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


async def test_internal_endpoint_requires_valid_service_token(client: httpx.AsyncClient) -> None:
    vehicle_id = "00000000-0000-4000-8000-000000000001"
    payload = {
        "brand": "Ford",
        "model": "Ka",
        "year": 2020,
        "color": "Preto",
        "price": "45000.00",
        "status": "AVAILABLE",
        "source_version": 1,
    }

    missing = await client.put(f"/internal/v1/vehicles/{vehicle_id}", json=payload)
    invalid = await client.put(
        f"/internal/v1/vehicles/{vehicle_id}",
        headers={"X-Service-Token": "wrong"},
        json=payload,
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401
