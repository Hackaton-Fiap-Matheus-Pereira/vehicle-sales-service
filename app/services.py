from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import CoreClient, CoreSyncError
from app.enums import CatalogSyncStatus, PaymentStatus, PurchaseStatus, VehicleStatus
from app.models import PaymentEvent, Purchase, VehicleListing
from app.schemas import PaymentProcess, PurchaseCreate, PurchaseRead, SoldVehicleRead, VehicleUpsert
from app.validation import mask_cpf


def _vehicle_matches(vehicle: VehicleListing, payload: VehicleUpsert) -> bool:
    return all(
        (
            vehicle.brand == payload.brand,
            vehicle.model == payload.model,
            vehicle.year == payload.year,
            vehicle.color == payload.color,
            vehicle.price == payload.price,
            vehicle.status == payload.status,
            vehicle.source_version == payload.source_version,
        )
    )


async def upsert_vehicle(
    session: AsyncSession,
    vehicle_id: str,
    payload: VehicleUpsert,
) -> tuple[VehicleListing, bool]:
    async with session.begin():
        vehicle = await session.scalar(
            select(VehicleListing).where(VehicleListing.id == vehicle_id).with_for_update()
        )
        if vehicle is None:
            vehicle = VehicleListing(id=vehicle_id, **payload.model_dump())
            session.add(vehicle)
            created = True
        elif payload.source_version < vehicle.source_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="source_version anterior à versão persistida",
            )
        elif payload.source_version == vehicle.source_version:
            if not _vehicle_matches(vehicle, payload):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="mesma source_version com conteúdo diferente",
                )
            created = False
        else:
            if payload.status != vehicle.status:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="estado comercial é controlado pelo serviço de vendas",
                )
            vehicle.brand = payload.brand
            vehicle.model = payload.model
            vehicle.year = payload.year
            vehicle.color = payload.color
            vehicle.price = payload.price
            vehicle.source_version = payload.source_version
            created = False

    await session.refresh(vehicle)
    return vehicle, created


async def available_vehicles(
    session: AsyncSession, limit: int, offset: int
) -> tuple[list[VehicleListing], int]:
    total = await session.scalar(
        select(func.count(VehicleListing.id)).where(
            VehicleListing.status == VehicleStatus.AVAILABLE
        )
    )
    vehicles = list(
        (
            await session.scalars(
                select(VehicleListing)
                .where(VehicleListing.status == VehicleStatus.AVAILABLE)
                .order_by(VehicleListing.price.asc(), VehicleListing.id.asc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    return vehicles, int(total or 0)


async def sold_vehicles(
    session: AsyncSession, limit: int, offset: int
) -> tuple[list[SoldVehicleRead], int]:
    predicate = Purchase.status == PurchaseStatus.PAID
    total = await session.scalar(select(func.count(Purchase.id)).where(predicate))
    rows = (
        await session.execute(
            select(VehicleListing, Purchase)
            .join(Purchase, Purchase.vehicle_id == VehicleListing.id)
            .where(predicate)
            .order_by(Purchase.price_at_purchase.asc(), VehicleListing.id.asc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    items = [
        SoldVehicleRead(
            id=vehicle.id,
            brand=vehicle.brand,
            model=vehicle.model,
            year=vehicle.year,
            color=vehicle.color,
            price=purchase.price_at_purchase,
            status=VehicleStatus.SOLD,
            purchase_date=purchase.purchase_date,
            sale_date=purchase.sale_date,
        )
        for vehicle, purchase in rows
        if purchase.sale_date is not None
    ]
    return items, int(total or 0)


def _same_purchase(purchase: Purchase, payload: PurchaseCreate) -> bool:
    return (
        purchase.vehicle_id == payload.vehicle_id
        and purchase.buyer_cpf == payload.buyer_cpf
        and purchase.purchase_date == payload.purchase_date
    )


async def create_purchase(
    session: AsyncSession,
    payload: PurchaseCreate,
    idempotency_key: str | None,
) -> tuple[Purchase, bool]:
    try:
        async with session.begin():
            if idempotency_key is not None:
                existing = await session.scalar(
                    select(Purchase).where(Purchase.idempotency_key == idempotency_key)
                )
                if existing is not None:
                    if not _same_purchase(existing, payload):
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="Idempotency-Key já utilizada com outro payload",
                        )
                    return existing, False

            vehicle = await session.scalar(
                select(VehicleListing)
                .where(VehicleListing.id == payload.vehicle_id)
                .with_for_update()
            )
            if vehicle is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="veículo não encontrado",
                )
            if vehicle.status != VehicleStatus.AVAILABLE:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="veículo não está disponível",
                )

            vehicle.status = VehicleStatus.RESERVED
            purchase = Purchase(
                vehicle_id=vehicle.id,
                buyer_cpf=payload.buyer_cpf,
                price_at_purchase=vehicle.price,
                purchase_date=payload.purchase_date,
                payment_code=f"pay_{uuid4().hex}",
                status=PurchaseStatus.PENDING,
                idempotency_key=idempotency_key,
                catalog_sync_status=CatalogSyncStatus.PENDING,
            )
            session.add(purchase)
    except IntegrityError:
        await session.rollback()
        if idempotency_key is None:
            raise
        existing = await session.scalar(
            select(Purchase).where(Purchase.idempotency_key == idempotency_key)
        )
        if existing is None or not _same_purchase(existing, payload):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency-Key já utilizada com outro payload",
            ) from None
        return existing, False

    await session.refresh(purchase)
    return purchase, True


async def purchase_by_payment_code(session: AsyncSession, payment_code: str) -> Purchase:
    purchase = await session.scalar(select(Purchase).where(Purchase.payment_code == payment_code))
    if purchase is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="compra não encontrada",
        )
    return purchase


async def purchase_by_id(session: AsyncSession, purchase_id: str) -> Purchase:
    purchase = await session.get(Purchase, purchase_id)
    if purchase is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="compra não encontrada",
        )
    return purchase


def desired_vehicle_status(purchase_status: PurchaseStatus) -> VehicleStatus:
    return {
        PurchaseStatus.PENDING: VehicleStatus.RESERVED,
        PurchaseStatus.PAID: VehicleStatus.SOLD,
        PurchaseStatus.CANCELED: VehicleStatus.AVAILABLE,
    }[purchase_status]


async def synchronize_purchase(
    session: AsyncSession,
    purchase: Purchase,
    core_client: CoreClient,
) -> Purchase:
    purchase.catalog_sync_attempts += 1
    try:
        await core_client.update_vehicle_status(
            purchase.vehicle_id, desired_vehicle_status(purchase.status)
        )
    except CoreSyncError as exc:
        purchase.catalog_sync_status = CatalogSyncStatus.FAILED
        purchase.catalog_sync_last_error = str(exc)[:500]
    else:
        purchase.catalog_sync_status = CatalogSyncStatus.SYNCED
        purchase.catalog_sync_last_error = None
    await session.commit()
    await session.refresh(purchase)
    return purchase


async def process_payment(
    session: AsyncSession,
    payload: PaymentProcess,
) -> tuple[Purchase, bool]:
    async with session.begin():
        replay = await session.scalar(
            select(PaymentEvent).where(PaymentEvent.event_id == payload.event_id)
        )
        if replay is not None:
            if replay.payment_code != payload.payment_code or replay.status != payload.status:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="event_id já utilizado com outro payload",
                )
            purchase = await session.get(Purchase, replay.purchase_id)
            if purchase is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="evento órfão",
                )
            return purchase, False

        purchase = await session.scalar(
            select(Purchase).where(Purchase.payment_code == payload.payment_code).with_for_update()
        )
        if purchase is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="código de pagamento não encontrado",
            )

        vehicle = await session.scalar(
            select(VehicleListing).where(VehicleListing.id == purchase.vehicle_id).with_for_update()
        )
        if vehicle is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="veículo da compra não encontrado",
            )

        target_status = PurchaseStatus(payload.status.value)
        changed = purchase.status != target_status
        if changed:
            if purchase.status != PurchaseStatus.PENDING:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="transição de pagamento inválida",
                )
            if vehicle.status != VehicleStatus.RESERVED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="veículo não está reservado",
                )

            purchase.status = target_status
            if payload.status == PaymentStatus.PAID:
                vehicle.status = VehicleStatus.SOLD
                purchase.sale_date = payload.occurred_at
            else:
                vehicle.status = VehicleStatus.AVAILABLE
                purchase.sale_date = None
            purchase.catalog_sync_status = CatalogSyncStatus.PENDING
            purchase.catalog_sync_last_error = None

        session.add(
            PaymentEvent(
                event_id=payload.event_id,
                purchase_id=purchase.id,
                payment_code=payload.payment_code,
                status=payload.status,
                occurred_at=payload.occurred_at,
            )
        )

    await session.refresh(purchase)
    return purchase, changed


def purchase_read(purchase: Purchase) -> PurchaseRead:
    return PurchaseRead(
        id=purchase.id,
        vehicle_id=purchase.vehicle_id,
        buyer_cpf_masked=mask_cpf(purchase.buyer_cpf),
        price_at_purchase=Decimal(purchase.price_at_purchase),
        purchase_date=purchase.purchase_date,
        payment_code=purchase.payment_code,
        status=purchase.status,
        sale_date=purchase.sale_date,
        catalog_sync_status=purchase.catalog_sync_status,
        created_at=purchase.created_at,
        updated_at=purchase.updated_at,
    )
