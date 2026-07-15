from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
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
    exclude_reservation_id: UUID | None = None,
) -> bool:
    query = select(Reservation.id).where(
        Reservation.common_area_id == common_area_id,
        Reservation.status.in_(BLOCKING_STATUSES),
        or_(
            and_(Reservation.starts_at <= starts_at, Reservation.ends_at > starts_at),
            and_(Reservation.starts_at < ends_at, Reservation.ends_at >= ends_at),
            and_(Reservation.starts_at >= starts_at, Reservation.ends_at <= ends_at),
        ),
    )
    if exclude_reservation_id is not None:
        query = query.where(Reservation.id != exclude_reservation_id)
    return db.scalar(query.limit(1)) is not None


def create_reservation(
    db: Session,
    *,
    current_resident: Resident,
    common_area_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
) -> Reservation:
    if ends_at <= starts_at:
        raise ReservationError(400, "La fecha final debe ser posterior a la inicial.")

    area = db.get(CommonArea, common_area_id)
    if area is None:
        raise ReservationError(404, "Zona social no encontrada.")
    if not area.is_active:
        raise ReservationError(409, "La zona social está inactiva.")

    complex_id = get_resident_complex_id(db, current_resident)
    if area.complex_id != complex_id:
        raise ReservationError(403, "La zona social no pertenece a tu conjunto.")

    if unit_balance(db, current_resident.unit_id) > 0:
        raise ReservationError(409, "No puedes reservar con saldo pendiente de administración.")

    if has_blocking_overlap(db, common_area_id, starts_at, ends_at):
        raise ReservationError(409, "El horario solicitado no está disponible.")

    hours = Decimal((ends_at - starts_at).total_seconds() / 3600).quantize(Decimal("0.01"))
    status_value = ReservationStatus.requested if area.requires_approval else ReservationStatus.approved
    reservation = Reservation(
        resident_id=current_resident.id,
        common_area_id=common_area_id,
        starts_at=starts_at,
        ends_at=ends_at,
        status=status_value,
        amount=area.hourly_rate * hours,
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return reservation


def cancel_reservation(db: Session, *, current_resident: Resident, reservation_id: UUID) -> Reservation:
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise ReservationError(404, "Reserva no encontrada.")
    if reservation.resident_id != current_resident.id:
        raise ReservationError(403, "No puedes cancelar esta reserva.")
    if reservation.status in {ReservationStatus.cancelled}:
        raise ReservationError(409, "La reserva ya está cancelada.")
    reservation.status = ReservationStatus.cancelled
    db.commit()
    db.refresh(reservation)
    return reservation
