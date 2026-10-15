from datetime import date

import httpx


async def create_vehicle(
    client: httpx.AsyncClient,
    service_headers: dict[str, str],
    vehicle_id: str,
    *,
    price: str = "100000.00",
    source_version: int = 1,
    status: str = "AVAILABLE",
) -> httpx.Response:
    return await client.put(
        f"/internal/v1/vehicles/{vehicle_id}",
        headers=service_headers,
        json={
            "brand": "Toyota",
            "model": "Corolla",
            "year": 2025,
            "color": "Prata",
            "price": price,
            "status": status,
            "source_version": source_version,
        },
    )


async def create_purchase(
    client: httpx.AsyncClient,
    vehicle_id: str,
    *,
    cpf: str = "52998224725",
    idempotency_key: str | None = None,
) -> httpx.Response:
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
    return await client.post(
        "/api/v1/purchases",
        headers=headers,
        json={
            "vehicle_id": vehicle_id,
            "buyer_cpf": cpf,
            "purchase_date": date.today().isoformat(),
        },
    )
