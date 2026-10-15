from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import CoreClient, get_core_client
from app.database import get_session
from app.schemas import (
    PaymentProcess,
    PurchaseCreate,
    PurchaseRead,
    SoldVehicleListResponse,
    VehicleListResponse,
    VehicleRead,
    VehicleUpsert,
)
from app.security import require_service_token
from app.services import (
    available_vehicles,
    create_purchase,
    process_payment,
    purchase_by_id,
    purchase_by_payment_code,
    purchase_read,
    sold_vehicles,
    synchronize_purchase,
    upsert_vehicle,
)

router = APIRouter()
SessionDep = Annotated[AsyncSession, Depends(get_session)]
CoreClientDep = Annotated[CoreClient, Depends(get_core_client)]
InternalAuth = Annotated[None, Depends(require_service_token)]


@router.put(
    "/internal/v1/vehicles/{vehicle_id}",
    response_model=VehicleRead,
    summary="Cria ou atualiza a projeção de um veículo",
)
async def put_vehicle(
    vehicle_id: Annotated[UUID, Path()],
    payload: VehicleUpsert,
    response: Response,
    session: SessionDep,
    _authorization: InternalAuth,
) -> VehicleRead:
    vehicle, created = await upsert_vehicle(session, str(vehicle_id), payload)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return VehicleRead.model_validate(vehicle)


@router.get(
    "/api/v1/vehicles/available",
    response_model=VehicleListResponse,
    summary="Lista veículos disponíveis pelo menor preço",
)
async def get_available_vehicles(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VehicleListResponse:
    items, total = await available_vehicles(session, limit, offset)
    return VehicleListResponse(
        items=[VehicleRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/api/v1/vehicles/sold",
    response_model=SoldVehicleListResponse,
    summary="Lista veículos vendidos pelo menor preço da venda",
)
async def get_sold_vehicles(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SoldVehicleListResponse:
    items, total = await sold_vehicles(session, limit, offset)
    return SoldVehicleListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/api/v1/purchases",
    response_model=PurchaseRead,
    summary="Reserva um veículo e inicia a compra",
)
async def post_purchase(
    payload: PurchaseCreate,
    response: Response,
    session: SessionDep,
    core_client: CoreClientDep,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", min_length=1, max_length=128),
    ] = None,
) -> PurchaseRead:
    purchase, created = await create_purchase(session, payload, idempotency_key)
    if created or purchase.catalog_sync_status.value != "SYNCED":
        purchase = await synchronize_purchase(session, purchase, core_client)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return purchase_read(purchase)


@router.get(
    "/api/v1/purchases/{payment_code}",
    response_model=PurchaseRead,
    summary="Consulta uma compra pelo código de pagamento",
)
async def get_purchase(
    payment_code: Annotated[str, Path(min_length=1, max_length=64)],
    session: SessionDep,
) -> PurchaseRead:
    return purchase_read(await purchase_by_payment_code(session, payment_code))


@router.post(
    "/internal/v1/payments",
    response_model=PurchaseRead,
    summary="Processa uma decisão de pagamento enviada pelo core",
)
async def post_payment(
    payload: PaymentProcess,
    session: SessionDep,
    core_client: CoreClientDep,
    _authorization: InternalAuth,
) -> PurchaseRead:
    purchase, changed = await process_payment(session, payload)
    if changed or purchase.catalog_sync_status.value != "SYNCED":
        purchase = await synchronize_purchase(session, purchase, core_client)
    return purchase_read(purchase)


@router.post(
    "/internal/v1/purchases/{purchase_id}/sync",
    response_model=PurchaseRead,
    summary="Tenta novamente sincronizar o estado comercial com o core",
)
async def retry_purchase_sync(
    purchase_id: Annotated[UUID, Path()],
    session: SessionDep,
    core_client: CoreClientDep,
    _authorization: InternalAuth,
) -> PurchaseRead:
    purchase = await purchase_by_id(session, str(purchase_id))
    return purchase_read(await synchronize_purchase(session, purchase, core_client))
