from datetime import UTC, date, datetime, timedelta

import pytest
from app.schemas import PaymentProcess, PurchaseCreate
from app.validation import mask_cpf, normalize_cpf
from pydantic import ValidationError


def test_normalize_and_mask_cpf() -> None:
    assert normalize_cpf("529.982.247-25") == "52998224725"
    assert mask_cpf("52998224725") == "***.***.***-25"


@pytest.mark.parametrize("cpf", ["11111111111", "52998224724", "123"])
def test_invalid_cpf_is_rejected(cpf: str) -> None:
    with pytest.raises(ValueError, match="CPF inválido"):
        normalize_cpf(cpf)


def test_purchase_rejects_invalid_uuid_and_future_date() -> None:
    with pytest.raises(ValidationError):
        PurchaseCreate(
            vehicle_id="not-a-uuid",
            buyer_cpf="52998224725",
            purchase_date=date.today(),
        )

    with pytest.raises(ValidationError):
        PurchaseCreate(
            vehicle_id="00000000-0000-4000-8000-000000000001",
            buyer_cpf="52998224725",
            purchase_date=date.today() + timedelta(days=1),
        )


def test_payment_timestamp_must_include_timezone() -> None:
    with pytest.raises(ValidationError):
        PaymentProcess(
            event_id="evt-1",
            payment_code="pay-1",
            status="PAID",
            occurred_at=datetime.now(),
        )

    valid = PaymentProcess(
        event_id="evt-1",
        payment_code="pay-1",
        status="PAID",
        occurred_at=datetime.now(UTC),
    )
    assert valid.occurred_at.tzinfo is not None
