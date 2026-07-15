from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.adapters.calendar_stub import StubICalCalendarAdapter
from app.adapters.payment_stub import StubPaymentAdapter
from app.models.domain import CommonArea, Reservation, ReservationStatus, Resident
from app.ports import CalendarEvent, PaymentChargeRequest
from app.services.availability import pay_reservation
from app.services.reservations import ReservationError


def test_stub_payment_charge_succeeds() -> None:
    adapter = StubPaymentAdapter()
    result = adapter.charge(
        PaymentChargeRequest(
            reservation_id=uuid4(),
            resident_id=uuid4(),
            amount=Decimal("25000"),
            description="Salon",
            method="PSE",
        )
    )
    assert result.success is True
    assert result.reference.startswith("PAY-PSE-")
    assert result.provider == "stub-pse"


def test_ical_export_contains_event() -> None:
    ical = StubICalCalendarAdapter().to_ical(
        [
            CalendarEvent(
                uid="abc@test",
                summary="BBQ",
                description="Demo",
                starts_at=datetime(2026, 7, 20, 10, 0),
                ends_at=datetime(2026, 7, 20, 12, 0),
                location="Terraza",
            )
        ]
    )
    assert "BEGIN:VCALENDAR" in ical
    assert "SUMMARY:BBQ" in ical
    assert "LOCATION:Terraza" in ical


def test_pay_reservation_marks_paid(monkeypatch: pytest.MonkeyPatch) -> None:
    reservation = Reservation(
        id=uuid4(),
        resident_id=uuid4(),
        common_area_id=uuid4(),
        starts_at=datetime(2026, 7, 20, 10, 0),
        ends_at=datetime(2026, 7, 20, 11, 0),
        status=ReservationStatus.approved,
        amount=Decimal("15000"),
    )
    area = CommonArea(id=reservation.common_area_id, complex_id=uuid4(), name="Salón", capacity=10, hourly_rate=Decimal("0"))
    db = MagicMock()
    db.get.side_effect = lambda model, _id: reservation if model is Reservation else area
    resident = Resident(id=reservation.resident_id, unit_id=uuid4())

    monkeypatch.setattr("app.integrations.hooks.ensure_access_pass", lambda *_a, **_k: None)
    monkeypatch.setattr("app.integrations.hooks.notify_reservation", lambda *_a, **_k: None)

    paid = pay_reservation(db, current_resident=resident, reservation_id=reservation.id, method="PSE")
    assert paid.status == ReservationStatus.paid
    assert paid.payment_reference
    db.commit.assert_called()


def test_pay_reservation_rejects_free(monkeypatch: pytest.MonkeyPatch) -> None:
    reservation = Reservation(
        id=uuid4(),
        resident_id=uuid4(),
        common_area_id=uuid4(),
        starts_at=datetime(2026, 7, 20, 10, 0),
        ends_at=datetime(2026, 7, 20, 11, 0),
        status=ReservationStatus.approved,
        amount=Decimal("0"),
    )
    db = MagicMock()
    db.get.return_value = reservation
    resident = Resident(id=reservation.resident_id, unit_id=uuid4())
    with pytest.raises(ReservationError) as exc:
        pay_reservation(db, current_resident=resident, reservation_id=reservation.id)
    assert exc.value.status_code == 409
