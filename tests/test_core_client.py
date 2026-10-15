import httpx
import pytest
from app.clients import CoreClient, CoreSyncError, get_core_client
from app.config import Settings
from app.enums import VehicleStatus


class DummyResponse:
    def __init__(self, error: bool = False) -> None:
        self.error = error

    def raise_for_status(self) -> None:
        if self.error:
            request = httpx.Request("PUT", "http://core.test/internal")
            response = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError("failure", request=request, response=response)


class DummyAsyncClient:
    response_error = False
    last_request: tuple[str, dict, dict] | None = None

    def __init__(self, **_kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def put(self, path: str, *, headers: dict, json: dict) -> DummyResponse:
        self.__class__.last_request = (path, headers, json)
        return DummyResponse(self.__class__.response_error)


async def test_core_client_sends_expected_contract(monkeypatch) -> None:
    settings = Settings(service_token="secret", core_base_url="http://core.test/")
    monkeypatch.setattr("app.clients.httpx.AsyncClient", DummyAsyncClient)
    DummyAsyncClient.response_error = False
    client = CoreClient(settings)

    await client.update_vehicle_status(
        "00000000-0000-4000-8000-000000000301", VehicleStatus.RESERVED
    )

    assert DummyAsyncClient.last_request == (
        "/internal/v1/vehicles/00000000-0000-4000-8000-000000000301/status",
        {"X-Service-Token": "secret"},
        {"status": "RESERVED"},
    )
    assert isinstance(get_core_client(settings), CoreClient)


async def test_core_client_wraps_http_errors(monkeypatch) -> None:
    monkeypatch.setattr("app.clients.httpx.AsyncClient", DummyAsyncClient)
    DummyAsyncClient.response_error = True
    client = CoreClient(Settings(service_token="secret", core_base_url="http://core.test"))

    with pytest.raises(CoreSyncError):
        await client.update_vehicle_status(
            "00000000-0000-4000-8000-000000000302", VehicleStatus.SOLD
        )
