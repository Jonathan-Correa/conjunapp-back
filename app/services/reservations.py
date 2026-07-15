from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.domain import CommonArea, Invoice, Reservation, ReservationStatus, Resident, Unit


class ReservationError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


BLOCKING_STATUSES = (
    ReservationStatus.approved,
    ReservationStatus.paid,
    ReservationStatus.requested,
)


def intervals_overlap(starts_a: datetime, ends_a: datetime, starts_b: datetime, ends_b: datetime) -> bool:
    """Half-open friendly overlap: [start, end) intersects if start < other_end and other_start < end."""
    return starts_a < ends_b and starts_b < ends_a


def unit_balance(db: Session, unit_id: UUID) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(Invoice.total - Invoice.paid_amount), 0)).where(Invoice.unit_id == unit_id)
    )
    return Decimal(total or 0)


def get_resident_complex_id(db: Session, resident: Resident) -> UUID:
    unit = db.scalar(select(Unit).options(joinedload(Unit.tower)).where(Unit.id == resident.unit_id))
    if unit is None or unit.tower is None:
        raise ReservationError(404, "Unidad del residente no encontrada.")
    return unit.tower.complex_id


def list_active_common_areas_for_complex(db: Session, complex_id: UUID) -> list[CommonArea]:
    return list(
        db.scalars(
            select(CommonArea)
            .where(CommonArea.complex_id == complex_id, CommonArea.is_active.is_(True))
            .order_by(CommonArea.name)
        )
    )


def list_common_areas_for_admin(db: Session, complex_id: UUID | None) -> list[CommonArea]:
    query = select(CommonArea).order_by(CommonArea.name)
    if complex_id is not None:
        query = query.where(CommonArea.complex_id == complex_id)
    return list(db.scalars(query))


def has_blocking_overlap(
    db: Session,
    common_area_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
    *,
    buffer_minutes: int = 0,
    exclude_reservation_id: UUID | None = None,
) -> bool:
    buffer = timedelta(minutes=max(buffer_minutes, 0))
    window_start = starts_at - buffer
    window_end = ends_at + buffer
    query = select(Reservation.id).where(
        Reservation.common_area_id == common_area_id,
        Reservation.status.in_(BLOCKING_STATUSES),
        Reservation.starts_at < window_end,
        Reservation.ends_at > window_start,
    )
    if exclude_reservation_id is not None:
        query = query.where(Reservation.id != exclude_reservation_id)
    return db.scalar(query.limit(1)) is not None


def count_active_reservations(db: Session, *, resident_id: UUID, common_area_id: UUID, now: datetime | None = None) -> int:
    now = now or datetime.utcnow()
    return (
        db.scalar(
            select(func.count(Reservation.id)).where(
                Reservation.resident_id == resident_id,
                Reservation.common_area_id == common_area_id,
                Reservation.status.in_(BLOCKING_STATUSES),
                Reservation.ends_at > now,
            )
        )
        or 0
    )


def create_reservation(
    db: Session,
    *,
    current_resident: Resident,
    common_area_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
) -> Reservation:
    from app.services.availability import create_reservation_with_event

    return create_reservation_with_event(
        db,
        current_resident=current_resident,
        common_area_id=common_area_id,
        starts_at=starts_at,
        ends_at=ends_at,
    )


def cancel_reservation(db: Session, *, current_resident: Resident, reservation_id: UUID) -> Reservation:
    from app.services.availability import resident_cancel_reservation

    return resident_cancel_reservation(db, current_resident=current_resident, reservation_id=reservation_id)
