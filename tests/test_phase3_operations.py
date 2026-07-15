from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.models.domain import CommonArea, CommonAreaSpecialHours, Reservation, ReservationStatus, Resident
from app.services.availability import build_receipt, reschedule_reservation, run_reservation_maintenance
from app.services.reservations import ReservationError


def test_maintenance_completes_past_approved() -> None:
    db = MagicMock()
    past = Reservation(
        id=uuid4(),
        resident_id=uuid4(),
        common_area_id=uuid4(),
        starts_at=datetime(2026, 7, 1, 10, 0),
        ends_at=datetime(2026, 7, 1, 11, 0),
        status=ReservationStatus.approved,
        amount=Decimal("0"),
    )
    pending_past = Reservation(
        id=uuid4(),
        resident_id=uuid4(),
        common_area_id=uuid4(),
        starts_at=datetime(2026, 7, 1, 9, 0),
        ends_at=datetime(2026, 7, 1, 10, 0),
        status=ReservationStatus.requested,
        amount=Decimal("0"),
    )
    db.scalars.side_effect = [[past], [pending_past]]
    result = run_reservation_maintenance(db, now=datetime(2026, 7, 15, 12, 0))
    assert result == {"completed": 1, "expired": 1}
    assert past.status == ReservationStatus.completed
    assert past.receipt_number is not None
    assert pending_past.status == ReservationStatus.rejected
    db.commit.assert_called()


def test_reschedule_rejects_wrong_status() -> None:
    db = MagicMock()
    reservation = Reservation(
        id=uuid4(),
        resident_id=uuid4(),
        common_area_id=uuid4(),
        starts_at=datetime(2026, 7, 20, 10, 0),
        ends_at=datetime(2026, 7, 20, 11, 0),
        status=ReservationStatus.cancelled,
        amount=Decimal("0"),
    )
    db.get.return_value = reservation
    resident = Resident(id=reservation.resident_id, unit_id=uuid4())
    with pytest.raises(ReservationError) as exc:
        reschedule_reservation(
            db,
            current_resident=resident,
            reservation_id=reservation.id,
            starts_at=datetime(2026, 7, 21, 10, 0),
            ends_at=datetime(2026, 7, 21, 11, 0),
        )
    assert exc.value.status_code == 409


def test_build_receipt_requires_approved(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    reservation = Reservation(
        id=uuid4(),
        resident_id=uuid4(),
        common_area_id=uuid4(),
        starts_at=datetime(2026, 7, 20, 10, 0),
        ends_at=datetime(2026, 7, 20, 11, 0),
        status=ReservationStatus.requested,
        amount=Decimal("0"),
    )
    area = CommonArea(
        id=reservation.common_area_id,
        complex_id=uuid4(),
        name="Salón",
        capacity=10,
        hourly_rate=Decimal("0"),
    )
    db.get.return_value = area
    resident = Resident(id=reservation.resident_id, unit_id=uuid4())
    user = MagicMock()
    user.full_name = "Ana"
    resident.user = user
    db.scalar.return_value = resident
    with pytest.raises(ReservationError) as exc:
        build_receipt(db, reservation=reservation)
    assert exc.value.status_code == 409


def test_special_hours_close_day_via_day_window() -> None:
    from app.services.availability import _day_window

    area = CommonArea(
        id=uuid4(),
        complex_id=uuid4(),
        name="Gym",
        capacity=5,
        hourly_rate=Decimal("0"),
        schedules=[],
    )
    special = CommonAreaSpecialHours(
        id=uuid4(),
        common_area_id=area.id,
        on_date=date(2026, 7, 20),
        open_time=None,
        close_time=None,
        is_closed=True,
        note="Festivo",
    )
    db = MagicMock()
    db.scalar.return_value = special
    assert _day_window(db, area, date(2026, 7, 20)) is None


def test_special_hours_override_open() -> None:
    from app.services.availability import _day_window

    area = CommonArea(
        id=uuid4(),
        complex_id=uuid4(),
        name="Gym",
        capacity=5,
        hourly_rate=Decimal("0"),
        schedules=[],
    )
    special = CommonAreaSpecialHours(
        id=uuid4(),
        common_area_id=area.id,
        on_date=date(2026, 7, 20),
        open_time=time(10, 0),
        close_time=time(14, 0),
        is_closed=False,
        note="",
    )
    db = MagicMock()
    db.scalar.return_value = special
    window = _day_window(db, area, date(2026, 7, 20))
    assert window is not None
    assert window[0].hour == 10
    assert window[1].hour == 14
