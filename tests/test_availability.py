from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.models.domain import CommonArea, CommonAreaSchedule
from app.services.availability import get_availability
from app.services.reservations import ReservationError


def _area(**kwargs):
    defaults = dict(
        id=uuid4(),
        complex_id=uuid4(),
        name="Salon",
        category="salon",
        description="",
        capacity=10,
        hourly_rate=Decimal("10000"),
        has_cost=True,
        requires_approval=False,
        rules="",
        is_active=True,
        is_bookable=True,
        min_duration_minutes=60,
        max_duration_minutes=120,
        min_advance_minutes=0,
        max_advance_days=30,
        cleanup_buffer_minutes=0,
        max_active_per_resident=3,
        required_documents=[],
        schedules=[],
    )
    defaults.update(kwargs)
    return CommonArea(**defaults)


def test_availability_returns_slots_for_open_day(monkeypatch: pytest.MonkeyPatch) -> None:
    area = _area(
        schedules=[
            CommonAreaSchedule(
                id=uuid4(),
                common_area_id=uuid4(),
                weekday=0,  # Monday
                open_time=time(9, 0),
                close_time=time(12, 0),
                is_closed=False,
            )
        ]
    )
    db = MagicMock()
    db.scalars.return_value = []  # no blackouts
    monkeypatch.setattr("app.services.availability.has_blocking_overlap", lambda *_a, **_k: False)

    day = date(2026, 7, 20)  # Monday
    now = datetime(2026, 7, 19, 8, 0)
    slots = get_availability(db, area=area, day=day, duration_minutes=60, now=now)
    assert len(slots) >= 2
    assert slots[0]["starts_at"].hour == 9
    assert slots[0]["amount"] == Decimal("10000.00")


def test_availability_closed_day() -> None:
    area = _area(
        schedules=[
            CommonAreaSchedule(
                id=uuid4(),
                common_area_id=uuid4(),
                weekday=0,
                open_time=None,
                close_time=None,
                is_closed=True,
            )
        ]
    )
    db = MagicMock()
    slots = get_availability(db, area=area, day=date(2026, 7, 20), duration_minutes=60, now=datetime(2026, 7, 19))
    assert slots == []


def test_availability_rejects_bad_duration() -> None:
    area = _area()
    db = MagicMock()
    with pytest.raises(ReservationError) as exc:
        get_availability(db, area=area, day=date(2026, 7, 20), duration_minutes=15, now=datetime(2026, 7, 19))
    assert exc.value.status_code == 400
