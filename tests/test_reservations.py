from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.models.domain import CommonArea, ReservationStatus, Resident
from app.services.reservations import ReservationError, create_reservation, intervals_overlap


def test_intervals_overlap_detects_partial_and_contained() -> None:
    start = datetime(2026, 7, 15, 10, 0)
    end = datetime(2026, 7, 15, 12, 0)
    assert intervals_overlap(start, end, start + timedelta(hours=1), end + timedelta(hours=1))
    assert intervals_overlap(start, end, start - timedelta(hours=1), end - timedelta(hours=1))
    assert intervals_overlap(start, end, start - timedelta(hours=1), end + timedelta(hours=1))
    assert not intervals_overlap(start, end, end, end + timedelta(hours=1))
    assert not intervals_overlap(start, end, start - timedelta(hours=2), start)


def test_create_reservation_rejects_inactive_zone(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    area = CommonArea(
        id=uuid4(),
        complex_id=uuid4(),
        name="Piscina",
        capacity=10,
        hourly_rate=Decimal("0"),
        requires_approval=False,
        rules="",
        is_active=False,
        is_bookable=True,
    )
    db.scalar.return_value = area
    resident = Resident(id=uuid4(), unit_id=uuid4())
    monkeypatch.setattr("app.services.availability.get_resident_complex_id", lambda *_a, **_k: area.complex_id)

    with pytest.raises(ReservationError) as exc:
        create_reservation(
            db,
            current_resident=resident,
            common_area_id=area.id,
            starts_at=datetime(2026, 7, 20, 10, 0),
            ends_at=datetime(2026, 7, 20, 11, 0),
        )
    assert exc.value.status_code == 409
    assert "inactiva" in exc.value.detail.lower()


def test_create_reservation_rejects_invalid_range() -> None:
    db = MagicMock()
    resident = Resident(id=uuid4(), unit_id=uuid4())
    when = datetime(2026, 7, 20, 10, 0)
    with pytest.raises(ReservationError) as exc:
        create_reservation(
            db,
            current_resident=resident,
            common_area_id=uuid4(),
            starts_at=when,
            ends_at=when,
        )
    assert exc.value.status_code == 400


def test_create_reservation_happy_path_auto_approved(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    complex_id = uuid4()
    area = CommonArea(
        id=uuid4(),
        complex_id=complex_id,
        name="Coworking",
        capacity=12,
        hourly_rate=Decimal("15000"),
        requires_approval=False,
        rules="",
        is_active=True,
        is_bookable=True,
        has_cost=True,
        min_duration_minutes=60,
        max_duration_minutes=240,
        min_advance_minutes=0,
        max_advance_days=90,
        cleanup_buffer_minutes=0,
        max_active_per_resident=3,
        schedules=[],
    )
    resident = Resident(id=uuid4(), unit_id=uuid4())
    db.scalar.return_value = area

    monkeypatch.setattr("app.services.availability.get_resident_complex_id", lambda *_a, **_k: complex_id)
    monkeypatch.setattr("app.services.availability.unit_balance", lambda *_a, **_k: Decimal("0"))
    monkeypatch.setattr("app.services.availability.has_blocking_overlap", lambda *_a, **_k: False)
    monkeypatch.setattr("app.services.availability.count_active_reservations", lambda *_a, **_k: 0)
    monkeypatch.setattr("app.services.common_areas.has_blackout_conflict", lambda *_a, **_k: False)
    monkeypatch.setattr("app.services.common_areas.validate_booking_window", lambda *_a, **_k: None)
    monkeypatch.setattr("app.integrations.hooks.notify_reservation", lambda *_a, **_k: None)
    monkeypatch.setattr("app.integrations.hooks.after_reservation_ready", lambda *_a, **_k: None)

    starts = datetime(2026, 7, 20, 10, 0)
    ends = datetime(2026, 7, 20, 12, 0)
    reservation = create_reservation(
        db,
        current_resident=resident,
        common_area_id=area.id,
        starts_at=starts,
        ends_at=ends,
    )

    assert reservation.status == ReservationStatus.approved
    assert reservation.amount == Decimal("30000.00")
    assert db.add.call_count >= 2  # reservation + audit event (+ integration side effects)
    db.commit.assert_called_once()


def test_create_reservation_blocks_delinquent(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    complex_id = uuid4()
    area = CommonArea(
        id=uuid4(),
        complex_id=complex_id,
        name="BBQ",
        capacity=25,
        hourly_rate=Decimal("45000"),
        requires_approval=True,
        rules="",
        is_active=True,
        is_bookable=True,
    )
    resident = Resident(id=uuid4(), unit_id=uuid4())
    db.scalar.return_value = area
    monkeypatch.setattr("app.services.availability.get_resident_complex_id", lambda *_a, **_k: complex_id)
    monkeypatch.setattr("app.services.availability.unit_balance", lambda *_a, **_k: Decimal("100000"))

    with pytest.raises(ReservationError) as exc:
        create_reservation(
            db,
            current_resident=resident,
            common_area_id=area.id,
            starts_at=datetime(2026, 7, 20, 10, 0),
            ends_at=datetime(2026, 7, 20, 11, 0),
        )
    assert exc.value.status_code == 409
    assert "saldo pendiente" in exc.value.detail.lower()


def test_create_reservation_rejects_overlap(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    complex_id = uuid4()
    area = CommonArea(
        id=uuid4(),
        complex_id=complex_id,
        name="Salon",
        capacity=80,
        hourly_rate=Decimal("90000"),
        requires_approval=False,
        rules="",
        is_active=True,
        is_bookable=True,
        cleanup_buffer_minutes=0,
        max_active_per_resident=3,
        schedules=[],
    )
    resident = Resident(id=uuid4(), unit_id=uuid4())
    db.scalar.return_value = area
    monkeypatch.setattr("app.services.availability.get_resident_complex_id", lambda *_a, **_k: complex_id)
    monkeypatch.setattr("app.services.availability.unit_balance", lambda *_a, **_k: Decimal("0"))
    monkeypatch.setattr("app.services.availability.count_active_reservations", lambda *_a, **_k: 0)
    monkeypatch.setattr("app.services.common_areas.validate_booking_window", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.common_areas.has_blackout_conflict", lambda *_a, **_k: False)
    monkeypatch.setattr("app.services.availability.has_blocking_overlap", lambda *_a, **_k: True)

    with pytest.raises(ReservationError) as exc:
        create_reservation(
            db,
            current_resident=resident,
            common_area_id=area.id,
            starts_at=datetime(2026, 7, 20, 10, 0),
            ends_at=datetime(2026, 7, 20, 11, 0),
        )
    assert exc.value.status_code == 409
    assert "no está disponible" in exc.value.detail.lower()
