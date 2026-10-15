import os
from collections.abc import AsyncIterator

os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["SERVICE_TOKEN"] = "test-service-token"
os.environ["CORE_BASE_URL"] = "http://core.test"

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from app.clients import CoreSyncError, get_core_client  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.database import Base, get_session  # noqa: E402
from app.enums import VehicleStatus  # noqa: E402
from app.main import create_app  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402


class FakeCoreClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, VehicleStatus]] = []
        self.fail = False

    async def update_vehicle_status(self, vehicle_id: str, status: VehicleStatus) -> None:
        self.calls.append((vehicle_id, status))
        if self.fail:
            raise CoreSyncError("core indisponível")


@pytest.fixture
def fake_core_client() -> FakeCoreClient:
    return FakeCoreClient()


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite://",
        service_token="test-service-token",
        core_base_url="http://core.test",
        docs_enabled=False,
    )


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(
    session_factory,
    fake_core_client: FakeCoreClient,
    test_settings: Settings,
) -> AsyncIterator[httpx.AsyncClient]:
    application = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    application.dependency_overrides[get_session] = override_session
    application.dependency_overrides[get_settings] = lambda: test_settings
    application.dependency_overrides[get_core_client] = lambda: fake_core_client

    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api_client:
        yield api_client

    application.dependency_overrides.clear()


@pytest.fixture
def service_headers() -> dict[str, str]:
    return {"X-Service-Token": "test-service-token"}
