from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import router
from app.config import get_settings
from app.database import database_is_ready, dispose_engine, get_session
from app.schemas import HealthResponse


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        lifespan=lifespan,
    )

    @application.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def live() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=settings.app_name,
            version=settings.app_version,
        )

    @application.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def ready(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> HealthResponse:
        try:
            await database_is_ready(session)
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="banco de dados indisponível",
            ) from exc
        return HealthResponse(
            status="ready",
            service=settings.app_name,
            version=settings.app_version,
        )

    application.include_router(router)
    return application


app = create_app()
