from typing import Annotated

import httpx
from fastapi import Depends

from app.config import Settings, get_settings
from app.enums import VehicleStatus


class CoreSyncError(RuntimeError):
    pass


class CoreClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.core_base_url
        self._service_token = settings.service_token.get_secret_value()
        self._timeout = settings.core_request_timeout_seconds

    async def update_vehicle_status(self, vehicle_id: str, status: VehicleStatus) -> None:
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                response = await client.put(
                    f"/internal/v1/vehicles/{vehicle_id}/status",
                    headers={"X-Service-Token": self._service_token},
                    json={"status": status.value},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CoreSyncError("não foi possível sincronizar o estado com o core") from exc


def get_core_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> CoreClient:
    return CoreClient(settings)
