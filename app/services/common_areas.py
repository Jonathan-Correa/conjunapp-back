from datetime import datetime, time, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.domain import (
    CommonArea,
    CommonAreaBlackout,
    CommonAreaImage,
    CommonAreaSchedule,
)
from app.schemas.domain import (
    BlackoutCreate,
    CommonAreaCreate,
    CommonAreaDetailOut,
    CommonAreaOut,
    CommonAreaUpdate,
    ImageItem,
    ImageOut,
    ScheduleItem,
    ScheduleOut,
    BlackoutOut,
)
from app.services.reservations import ReservationError


def _parse_hhmm(value: str | None) -> time | None:
    if not value:
        return None
    hour, minute = value.split(":")[:2]
    return time(int(hour), int(minute))


def _fmt_time(value: time | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%H:%M")


def to_common_area_out(area: CommonArea) -> CommonAreaOut:
    docs = area.required_documents if isinstance(area.required_documents, list) else []
    return CommonAreaOut(
        id=area.id,
        name=area.name,
        category=area.category,
        description=area.description or "",
        capacity=area.capacity,
        hourly_rate=area.hourly_rate,
        has_cost=area.has_cost,
        requires_approval=area.requires_approval,
        rules=area.rules or "",
        is_active=area.is_active,
        is_bookable=area.is_bookable,
        min_duration_minutes=area.min_duration_minutes,
        max_duration_minutes=area.max_duration_minutes,
        min_advance_minutes=area.min_advance_minutes,
        max_advance_days=area.max_advance_days,
        cleanup_buffer_minutes=area.cleanup_buffer_minutes,
        max_active_per_resident=area.max_active_per_resident,
        required_documents=[str(x) for x in docs],
    )


def to_detail(area: CommonArea) -> CommonAreaDetailOut:
    base = to_common_area_out(area).model_dump()
    return CommonAreaDetailOut(
        **base,
        schedules=[
            ScheduleOut(
                id=s.id,
                weekday=s.weekday,
                open_time=_fmt_time(s.open_time),
                close_time=_fmt_time(s.close_time),
                is_closed=s.is_closed,
            )
            for s in sorted(area.schedules, key=lambda x: x.weekday)
        ],
        blackouts=[
            BlackoutOut(
                id=b.id,
                common_area_id=b.common_area_id,
                reason_type=b.reason_type,
                starts_at=b.starts_at,
                ends_at=b.ends_at,
                note=b.note or "",
            )
            for b in sorted(area.blackouts, key=lambda x: x.starts_at)
        ],
        images=[
            ImageOut(id=i.id, url=i.url, sort_order=i.sort_order)
            for i in sorted(area.images, key=lambda x: x.sort_order)
        ],
    )


def _resolve_admin_complex_id(db: Session, admin_complex_id: UUID | None) -> UUID:
    if admin_complex_id is not None:
        return admin_complex_id
    from app.models.domain import ResidentialComplex

    complex_id = db.scalar(select(ResidentialComplex.id).limit(1))
    if complex_id is None:
        raise ReservationError(400, "No hay conjunto residencial configurado.")
    return complex_id


def get_area(db: Session, area_id: UUID) -> CommonArea | None:
    return db.scalar(
        select(CommonArea)
        .options(
            selectinload(CommonArea.schedules),
            selectinload(CommonArea.blackouts),
            selectinload(CommonArea.images),
        )
        .where(CommonArea.id == area_id)
    )


def create_common_area(db: Session, *, admin_complex_id: UUID | None, payload: CommonAreaCreate) -> CommonArea:
    complex_id = _resolve_admin_complex_id(db, admin_complex_id)
    if payload.max_duration_minutes < payload.min_duration_minutes:
        raise ReservationError(400, "La duración máxima debe ser mayor o igual a la mínima.")
    area = CommonArea(
        id=uuid4(),
        complex_id=complex_id,
        name=payload.name.strip(),
        category=payload.category.strip() or "general",
        description=payload.description,
        capacity=payload.capacity,
        hourly_rate=payload.hourly_rate,
        has_cost=payload.has_cost if payload.has_cost or payload.hourly_rate > 0 else False,
        requires_approval=payload.requires_approval,
        rules=payload.rules,
        is_active=payload.is_active,
        is_bookable=payload.is_bookable,
        min_duration_minutes=payload.min_duration_minutes,
        max_duration_minutes=payload.max_duration_minutes,
        min_advance_minutes=payload.min_advance_minutes,
        max_advance_days=payload.max_advance_days,
        cleanup_buffer_minutes=payload.cleanup_buffer_minutes,
        max_active_per_resident=payload.max_active_per_resident,
        required_documents=payload.required_documents,
    )
    if area.hourly_rate > 0:
        area.has_cost = True
    db.add(area)
    db.commit()
    db.refresh(area)
    return area


def update_common_area(db: Session, *, area: CommonArea, payload: CommonAreaUpdate) -> CommonArea:
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()
    if "category" in data and data["category"] is not None:
        data["category"] = data["category"].strip() or "general"
    for key, value in data.items():
        setattr(area, key, value)
    if area.max_duration_minutes < area.min_duration_minutes:
        raise ReservationError(400, "La duración máxima debe ser mayor o igual a la mínima.")
    if area.hourly_rate > 0:
        area.has_cost = True
    db.commit()
    db.refresh(area)
    return area


def deactivate_common_area(db: Session, *, area: CommonArea) -> CommonArea:
    area.is_active = False
    db.commit()
    db.refresh(area)
    return area


def replace_schedules(db: Session, *, area: CommonArea, items: list[ScheduleItem]) -> CommonArea:
    weekdays = [i.weekday for i in items]
    if len(weekdays) != len(set(weekdays)):
        raise ReservationError(400, "Hay días de la semana duplicados en el horario.")
    area.schedules.clear()
    db.flush()
    for item in items:
        if not item.is_closed:
            open_t = _parse_hhmm(item.open_time)
            close_t = _parse_hhmm(item.close_time)
            if open_t is None or close_t is None or close_t <= open_t:
                raise ReservationError(400, f"Horario inválido para el día {item.weekday}.")
        else:
            open_t = close_t = None
        area.schedules.append(
            CommonAreaSchedule(
                id=uuid4(),
                common_area_id=area.id,
                weekday=item.weekday,
                open_time=open_t,
                close_time=close_t,
                is_closed=item.is_closed,
            )
        )
    db.commit()
    return get_area(db, area.id)  # type: ignore[return-value]


def create_blackout(db: Session, *, area: CommonArea, payload: BlackoutCreate) -> CommonAreaBlackout:
    if payload.ends_at <= payload.starts_at:
        raise ReservationError(400, "La fecha final del bloqueo debe ser posterior a la inicial.")
    row = CommonAreaBlackout(
        id=uuid4(),
        common_area_id=area.id,
        reason_type=payload.reason_type,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        note=payload.note or "",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_blackout(db: Session, *, area: CommonArea, blackout_id: UUID) -> None:
    row = db.get(CommonAreaBlackout, blackout_id)
    if row is None or row.common_area_id != area.id:
        raise ReservationError(404, "Bloqueo no encontrado.")
    db.delete(row)
    db.commit()


def replace_images(db: Session, *, area: CommonArea, items: list[ImageItem]) -> CommonArea:
    area.images.clear()
    db.flush()
    for item in items:
        area.images.append(
            CommonAreaImage(
                id=uuid4(),
                common_area_id=area.id,
                url=item.url.strip(),
                sort_order=item.sort_order,
            )
        )
    db.commit()
    return get_area(db, area.id)  # type: ignore[return-value]


def validate_booking_window(area: CommonArea, starts_at: datetime, ends_at: datetime, now: datetime | None = None) -> None:
    """Phase 1 business rules used when creating a reservation."""
    now = now or datetime.utcnow()
    if not area.is_bookable:
        raise ReservationError(409, "Esta zona social es solo informativa (no reservable).")

    duration_min = int((ends_at - starts_at).total_seconds() / 60)
    if duration_min < area.min_duration_minutes:
        raise ReservationError(400, f"La reserva mínima es de {area.min_duration_minutes} minutos.")
    if duration_min > area.max_duration_minutes:
        raise ReservationError(400, f"La reserva máxima es de {area.max_duration_minutes} minutos.")

    min_start = now + timedelta(minutes=area.min_advance_minutes)
    max_start = now + timedelta(days=area.max_advance_days)
    if starts_at < min_start:
        raise ReservationError(400, "La reserva no cumple la anticipación mínima.")
    if starts_at > max_start:
        raise ReservationError(400, "La reserva excede la anticipación máxima permitida.")

    if starts_at.date() != ends_at.date():
        raise ReservationError(400, "Las reservas deben iniciar y terminar el mismo día.")

    if area.schedules:
        weekday = starts_at.weekday()  # Monday=0
        day = next((s for s in area.schedules if s.weekday == weekday), None)
        if day is None:
            raise ReservationError(409, "No hay horario configurado para ese día.")
        if day.is_closed or day.open_time is None or day.close_time is None:
            raise ReservationError(409, "La zona está cerrada ese día.")
        if starts_at.time() < day.open_time or ends_at.time() > day.close_time:
            raise ReservationError(409, "El horario está fuera de la franja de apertura.")


def has_blackout_conflict(db: Session, area_id: UUID, starts_at: datetime, ends_at: datetime) -> bool:
    return (
        db.scalar(
            select(CommonAreaBlackout.id)
            .where(
                CommonAreaBlackout.common_area_id == area_id,
                CommonAreaBlackout.starts_at < ends_at,
                CommonAreaBlackout.ends_at > starts_at,
            )
            .limit(1)
        )
        is not None
    )
