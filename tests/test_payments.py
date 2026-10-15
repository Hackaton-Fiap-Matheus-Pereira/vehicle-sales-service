from datetime import UTC, datetime

import httpx
from app.enums import VehicleStatus

from tests.helpers import create_purchase, create_vehicle


def payment_payload(payment_code: str, *, event_id: str, status: str) -> dict[str, str]:
    return {
        "event_id": event_id,
        "payment_code": payment_code,
        "status": status,
        "occurred_at": datetime.now(UTC).isoformat(),
    }


async def test_paid_payment_is_atomic_idempotent_and_listed_as_sold(
    client: httpx.AsyncClient,
    service_headers: dict[str, str],
    fake_core_client,
) -> None:
    expensive_id = "00000000-0000-4000-8000-000000000201"
    cheap_id = "00000000-0000-4000-8000-000000000202"
    await create_vehicle(client, service_headers, expensive_id, price="90000.00")
    await create_vehicle(client, service_headers, cheap_id, price="50000.00")
    expensive = await create_purchase(client, expensive_id)
    cheap = await create_purchase(client, cheap_id)

    expensive_payment = payment_payload(
        expensive.json()["payment_code"], event_id="evt-expensive", status="PAID"
    )
    cheap_payment = payment_payload(
        cheap.json()["payment_code"], event_id="evt-cheap", status="PAID"
    )
    paid_expensive = await client.post(
        "/internal/v1/payments", headers=service_headers, json=expensive_payment
    )
    paid_cheap = await client.post(
        "/internal/v1/payments", headers=service_headers, json=cheap_payment
    )
    calls_before_replay = len(fake_core_client.calls)
    replay = await client.post("/internal/v1/payments", headers=service_headers, json=cheap_payment)
    sold = await client.get("/api/v1/vehicles/sold")

    assert paid_expensive.status_code == 200
    assert paid_cheap.json()["status"] == "PAID"
    assert replay.status_code == 200
    assert len(fake_core_client.calls) == calls_before_replay
    assert [item["id"] for item in sold.json()["items"]] == [cheap_id, expensive_id]
    assert [item["price"] for item in sold.json()["items"]] == ["50000.00", "90000.00"]
    assert fake_core_client.calls[-1] == (cheap_id, VehicleStatus.SOLD)


async def test_canceled_payment_releases_vehicle_and_terminal_transition_is_rejected(
    client: httpx.AsyncClient,
    service_headers: dict[str, str],
    fake_core_client,
) -> None:
    vehicle_id = "00000000-0000-4000-8000-000000000203"
    await create_vehicle(client, service_headers, vehicle_id)
    purchase = await create_purchase(client, vehicle_id)
    payment_code = purchase.json()["payment_code"]

    canceled = await client.post(
        "/internal/v1/payments",
        headers=service_headers,
        json=payment_payload(payment_code, event_id="evt-cancel", status="CANCELED"),
    )
    available = await client.get("/api/v1/vehicles/available")
    second_purchase = await create_purchase(client, vehicle_id)
    late_paid = await client.post(
        "/internal/v1/payments",
        headers=service_headers,
        json=payment_payload(payment_code, event_id="evt-late-paid", status="PAID"),
    )

    assert canceled.json()["status"] == "CANCELED"
    assert available.json()["total"] == 1
    assert second_purchase.status_code == 201
    assert late_paid.status_code == 409
    assert (vehicle_id, VehicleStatus.AVAILABLE) in fake_core_client.calls


async def test_payment_rejects_bad_auth_unknown_code_and_conflicting_replay(
    client: httpx.AsyncClient,
    service_headers: dict[str, str],
) -> None:
    vehicle_id = "00000000-0000-4000-8000-000000000204"
    await create_vehicle(client, service_headers, vehicle_id)
    purchase = await create_purchase(client, vehicle_id)
    payment_code = purchase.json()["payment_code"]
    paid = payment_payload(payment_code, event_id="evt-reused", status="PAID")

    unauthorized = await client.post("/internal/v1/payments", json=paid)
    unknown = await client.post(
        "/internal/v1/payments",
        headers=service_headers,
        json=payment_payload("pay_unknown", event_id="evt-unknown", status="PAID"),
    )
    accepted = await client.post("/internal/v1/payments", headers=service_headers, json=paid)
    conflict = await client.post(
        "/internal/v1/payments",
        headers=service_headers,
        json=payment_payload(payment_code, event_id="evt-reused", status="CANCELED"),
    )

    assert unauthorized.status_code == 401
    assert unknown.status_code == 404
    assert accepted.status_code == 200
    assert conflict.status_code == 409
