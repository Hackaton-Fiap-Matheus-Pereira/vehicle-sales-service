from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings


async def require_service_token(
    settings: Annotated[Settings, Depends(get_settings)],
    x_service_token: Annotated[str | None, Header(alias="X-Service-Token")] = None,
) -> None:
    expected = settings.service_token.get_secret_value()
    if x_service_token is None or not compare_digest(x_service_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="credencial de serviço inválida",
        )
