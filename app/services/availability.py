from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.domain import (
    CommonArea,
    CommonAreaBlackout,
    CommonAreaSpecialHours,
    Reservation,
    ReservationEvent,
    ReservationStatus,
    Resident,
)
from app.services.reservations import (
    ReservationError,
    count_active_reservations,
    get_resident_complex_id,
    has_blocking_overlap,
    unit_balance,
)


def add_reservation_event(
    db: Session,
    *,
    reservation_id: UUID,
    event_type: str,
    actor_type: str,
    actor_id: UUID | None = None,
    payload: dict | None = None,
) -> None:
    db.add(
        ReservationEvent(
            id=uuid4(),
            reservation_id=reservation_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            payload=payload or {},
        )
    )


def _ensure_receipt(reservation: Reservation) -> None:
    if reservation.receipt_number:
        return
    reservation.receipt_number = f"RCP-{date.today().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"


def _day_window(db: Session, area: CommonArea, day: date) -> tuple[datetime, datetime] | None:
    """Return open/close for a day. Special hours override weekly schedule."""
    special = db.scalar(
        select(CommonAreaSpecialHours).where(
            CommonAreaSpecialHours.common_area_id == area.id,
            CommonAreaSpecialHours.on_date == day,
        )
    )
    if special is not None:
        if special.is_closed or special.open_time is None or special.close_time is None:
            return None
        start = datetime.combine(day, special.open_time)
        end = datetime.combine(day, special.close_time)
        return None if end <= start else (start, end)

    if not area.schedules:
        return datetime.combine(day, time(0, 0)), datetime.combine(day, time(23, 59))

    weekday = day.weekday()
    day_sched = next((s for s in area.schedules if s.weekday == weekday), None)
    if day_sched is None or day_sched.is_closed or day_sched.open_time is None or day_sched.close_time is None:
        return None
    start = datetime.combine(day, day_sched.open_time)
    end = datetime.combine(day, day_sched.close_time)
    if end <= start:
        return None
    return start, end


def get_availability(
    db: Session,
    *,
    area: CommonArea,
    day: date,
    duration_minutes: int | None = None,
    now: datetime | None = None,
    exclude_reservation_id: UUID | None = None,
) -> list[dict]:
    now = now or datetime.utcnow()
    if not area.is_active or not area.is_bookable:
        return []

    duration = duration_minutes or area.min_duration_minutes
    if duration < area.min_duration_minutes or duration > area.max_duration_minutes:
        raise ReservationError(400, "Duración fuera de los límites de la zona.")

    window = _day_window(db, area, day)
    if window is None:
        return []
    open_at, close_at = window

    step = max(15, min(area.min_duration_minutes, 60) // 2 or 15)
    if step > area.min_duration_minutes:
        step = area.min_duration_minutes

    blackouts = list(
        db.scalars(
            select(CommonAreaBlackout).where(
                CommonAreaBlackout.common_area_id == area.id,
                CommonAreaBlackout.starts_at < close_at,
                CommonAreaBlackout.ends_at > open_at,
            )
        )
    )

    slots: list[dict] = []
    cursor = open_at
    min_start = now + timedelta(minutes=area.min_advance_minutes)
    max_start = now + timedelta(days=area.max_advance_days)

    while cursor + timedelta(minutes=duration) <= close_at:
        starts_at = cursor
        ends_at = cursor + timedelta(minutes=duration)
        cursor += timedelta(minutes=step)

        if starts_at < min_start or starts_at > max_start:
            continue
        if any(b.starts_at < ends_at and b.ends_at > starts_at for b in blackouts):
            continue
        if has_blocking_overlap(
            db,
            area.id,
            starts_at,
            ends_at,
            buffer_minutes=area.cleanup_buffer_minutes,
            exclude_reservation_id=exclude_reservation_id,
        ):
            continue

        hours = Decimal(duration / 60).quantize(Decimal("0.01"))
        amount = (area.hourly_rate * hours) if area.has_cost or area.hourly_rate > 0 else Decimal("0")
        slots.append({"starts_at": starts_at, "ends_at": ends_at, "amount": amount})

    return slots


def create_reservation_with_event(
    db: Session,
    *,
    current_resident: Resident,
    common_area_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
) -> Reservation:
    from app.services.common_areas import has_blackout_conflict, validate_booking_window

    if ends_at <= starts_at:
        raise ReservationError(400, "La fecha final debe ser posterior a la inicial.")

    area = db.scalar(
        select(CommonArea).options(selectinload(CommonArea.schedules)).where(CommonArea.id == common_area_id)
    )
    if area is None:
        raise ReservationError(404, "Zona social no encontrada.")
    if not area.is_active:
        raise ReservationError(409, "La zona social está inactiva.")

    complex_id = get_resident_complex_id(db, current_resident)
    if area.complex_id != complex_id:
        raise ReservationError(403, "La zona social no pertenece a tu conjunto.")

    if unit_balance(db, current_resident.unit_id) > 0:
        raise ReservationError(409, "No puedes reservar con saldo pendiente de administración.")

    validate_booking_window(area, starts_at, ends_at, db=db)

    if has_blackout_conflict(db, common_area_id, starts_at, ends_at):
        raise ReservationError(409, "La zona tiene un bloqueo/mantenimiento en ese horario.")

    active = count_active_reservations(db, resident_id=current_resident.id, common_area_id=common_area_id)
    if active >= area.max_active_per_resident:
        raise ReservationError(409, "Alcanzaste el máximo de reservas activas para esta zona.")

    if has_blocking_overlap(db, common_area_id, starts_at, ends_at, buffer_minutes=area.cleanup_buffer_minutes):
        raise ReservationError(409, "El horario solicitado no está disponible.")

    hours = Decimal((ends_at - starts_at).total_seconds() / 3600).quantize(Decimal("0.01"))
    amount = (area.hourly_rate * hours) if area.has_cost or area.hourly_rate > 0 else Decimal("0")
    status_value = ReservationStatus.requested if area.requires_approval else ReservationStatus.approved
    reservation = Reservation(
        resident_id=current_resident.id,
        common_area_id=common_area_id,
        starts_at=starts_at,
        ends_at=ends_at,
        status=status_value,
        amount=amount,
    )
    if status_value == ReservationStatus.approved:
        _ensure_receipt(reservation)
    db.add(reservation)
    db.flush()
    add_reservation_event(
        db,
        reservation_id=reservation.id,
        event_type="created",
        actor_type="resident",
        actor_id=current_resident.id,
        payload={"status": status_value.value},
    )
    from app.integrations.hooks import after_reservation_ready, notify_reservation

    if status_value == ReservationStatus.approved:
        if amount > 0:
            notify_reservation(
                db,
                reservation=reservation,
                template="reservation_payment_required",
                subject=f"Pago pendiente — {area.name}",
                body=f"Tu reserva en {area.name} requiere pago de {amount} para confirmar el acceso.",
            )
        else:
            after_reservation_ready(db, reservation=reservation)
    else:
        notify_reservation(
            db,
            reservation=reservation,
            template="reservation_requested",
            subject=f"Solicitud recibida — {area.name}",
            body=f"Tu solicitud de reserva en {area.name} está pendiente de aprobación.",
        )
    db.commit()
    db.refresh(reservation)
    return reservation


def reschedule_reservation(
    db: Session,
    *,
    current_resident: Resident,
    reservation_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
) -> Reservation:
    from app.services.common_areas import has_blackout_conflict, validate_booking_window

    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise ReservationError(404, "Reserva no encontrada.")
    if reservation.resident_id != current_resident.id:
        raise ReservationError(403, "No puedes reprogramar esta reserva.")
    if reservation.status not in {ReservationStatus.requested, ReservationStatus.approved, ReservationStatus.paid}:
        raise ReservationError(409, "Solo se pueden reprogramar reservas activas.")
    if ends_at <= starts_at:
        raise ReservationError(400, "La fecha final debe ser posterior a la inicial.")

    area = db.scalar(
        select(CommonArea).options(selectinload(CommonArea.schedules)).where(CommonArea.id == reservation.common_area_id)
    )
    if area is None or not area.is_active:
        raise ReservationError(409, "La zona social no está disponible.")

    validate_booking_window(area, starts_at, ends_at, db=db)
    if has_blackout_conflict(db, area.id, starts_at, ends_at):
        raise ReservationError(409, "La zona tiene un bloqueo/mantenimiento en ese horario.")
    if has_blocking_overlap(
        db,
        area.id,
        starts_at,
        ends_at,
        buffer_minutes=area.cleanup_buffer_minutes,
        exclude_reservation_id=reservation.id,
    ):
        raise ReservationError(409, "El horario solicitado no está disponible.")

    old = {"starts_at": reservation.starts_at.isoformat(), "ends_at": reservation.ends_at.isoformat()}
    hours = Decimal((ends_at - starts_at).total_seconds() / 3600).quantize(Decimal("0.01"))
    reservation.starts_at = starts_at
    reservation.ends_at = ends_at
    reservation.amount = (area.hourly_rate * hours) if area.has_cost or area.hourly_rate > 0 else Decimal("0")
    add_reservation_event(
        db,
        reservation_id=reservation.id,
        event_type="rescheduled",
        actor_type="resident",
        actor_id=current_resident.id,
        payload={"from": old, "to": {"starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()}},
    )
    db.commit()
    db.refresh(reservation)
    return reservation


def approve_reservation(db: Session, *, reservation: Reservation, admin_id: UUID) -> Reservation:
    from app.integrations.hooks import after_reservation_ready, notify_reservation

    if reservation.status != ReservationStatus.requested:
        raise ReservationError(409, "Solo se pueden aprobar reservas en estado solicitado.")
    reservation.status = ReservationStatus.approved
    _ensure_receipt(reservation)
    add_reservation_event(
        db,
        reservation_id=reservation.id,
        event_type="approved",
        actor_type="admin",
        actor_id=admin_id,
    )
    if reservation.amount > 0:
        notify_reservation(
            db,
            reservation=reservation,
            template="reservation_payment_required",
            subject="Reserva aprobada — pago pendiente",
            body="Tu reserva fue aprobada. Realiza el pago para obtener el acceso.",
        )
    else:
        after_reservation_ready(db, reservation=reservation)
    db.commit()
    db.refresh(reservation)
    return reservation


def reject_reservation(db: Session, *, reservation: Reservation, admin_id: UUID, reason: str = "") -> Reservation:
    from app.integrations.hooks import notify_reservation

    if reservation.status != ReservationStatus.requested:
        raise ReservationError(409, "Solo se pueden rechazar reservas en estado solicitado.")
    reservation.status = ReservationStatus.rejected
    reservation.reject_reason = reason.strip() or None
    add_reservation_event(
        db,
        reservation_id=reservation.id,
        event_type="rejected",
        actor_type="admin",
        actor_id=admin_id,
        payload={"reason": reason},
    )
    notify_reservation(
        db,
        reservation=reservation,
        template="reservation_rejected",
        subject="Reserva rechazada",
        body=reason.strip() or "Tu solicitud de reserva fue rechazada.",
    )
    db.commit()
    db.refresh(reservation)
    return reservation


def admin_cancel_reservation(db: Session, *, reservation: Reservation, admin_id: UUID) -> Reservation:
    from app.integrations.hooks import notify_reservation, revoke_access_pass
    from app.integrations.registry import get_payment_port
    from app.ports import PaymentRefundRequest

    if reservation.status in {ReservationStatus.cancelled, ReservationStatus.rejected, ReservationStatus.completed}:
        raise ReservationError(409, "La reserva ya está cerrada.")
    previous = reservation.status
    reservation.status = ReservationStatus.cancelled
    revoke_access_pass(db, reservation=reservation, reason="cancelled_by_admin")
    if previous == ReservationStatus.paid and reservation.payment_reference and reservation.amount > 0:
        refund = get_payment_port().refund(
            PaymentRefundRequest(
                reservation_id=reservation.id,
                payment_reference=reservation.payment_reference,
                amount=reservation.amount,
                reason="cancelled_by_admin",
            )
        )
        add_reservation_event(
            db,
            reservation_id=reservation.id,
            event_type="payment_refunded",
            actor_type="admin",
            actor_id=admin_id,
            payload={"reference": refund.reference, "provider": refund.provider},
        )
    add_reservation_event(
        db,
        reservation_id=reservation.id,
        event_type="cancelled_by_admin",
        actor_type="admin",
        actor_id=admin_id,
    )
    notify_reservation(
        db,
        reservation=reservation,
        template="reservation_cancelled",
        subject="Reserva cancelada",
        body="La administración canceló tu reserva.",
    )
    db.commit()
    db.refresh(reservation)
    return reservation


def resident_cancel_reservation(db: Session, *, current_resident: Resident, reservation_id: UUID) -> Reservation:
    from app.integrations.hooks import notify_reservation, revoke_access_pass
    from app.integrations.registry import get_payment_port
    from app.ports import PaymentRefundRequest

    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise ReservationError(404, "Reserva no encontrada.")
    if reservation.resident_id != current_resident.id:
        raise ReservationError(403, "No puedes cancelar esta reserva.")
    if reservation.status in {ReservationStatus.cancelled, ReservationStatus.rejected, ReservationStatus.completed}:
        raise ReservationError(409, "La reserva ya está cerrada.")
    previous = reservation.status
    reservation.status = ReservationStatus.cancelled
    revoke_access_pass(db, reservation=reservation, reason="cancelled_by_resident")
    if previous == ReservationStatus.paid and reservation.payment_reference and reservation.amount > 0:
        refund = get_payment_port().refund(
            PaymentRefundRequest(
                reservation_id=reservation.id,
                payment_reference=reservation.payment_reference,
                amount=reservation.amount,
                reason="cancelled_by_resident",
            )
        )
        add_reservation_event(
            db,
            reservation_id=reservation.id,
            event_type="payment_refunded",
            actor_type="resident",
            actor_id=current_resident.id,
            payload={"reference": refund.reference, "provider": refund.provider},
        )
    add_reservation_event(
        db,
        reservation_id=reservation.id,
        event_type="cancelled_by_resident",
        actor_type="resident",
        actor_id=current_resident.id,
    )
    notify_reservation(
        db,
        reservation=reservation,
        template="reservation_cancelled",
        subject="Reserva cancelada",
        body="Cancelaste tu reserva de zona social.",
    )
    db.commit()
    db.refresh(reservation)
    return reservation


def pay_reservation(
    db: Session,
    *,
    current_resident: Resident,
    reservation_id: UUID,
    method: str = "PSE",
) -> Reservation:
    from app.integrations.hooks import ensure_access_pass, notify_reservation
    from app.integrations.registry import get_payment_port
    from app.ports import PaymentChargeRequest

    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise ReservationError(404, "Reserva no encontrada.")
    if reservation.resident_id != current_resident.id:
        raise ReservationError(403, "No puedes pagar esta reserva.")
    if reservation.status != ReservationStatus.approved:
        raise ReservationError(409, "Solo se pueden pagar reservas aprobadas.")
    if reservation.amount <= 0:
        raise ReservationError(409, "Esta reserva no requiere pago.")

    area = db.get(CommonArea, reservation.common_area_id)
    zone = area.name if area else "zona social"
    charge = get_payment_port().charge(
        PaymentChargeRequest(
            reservation_id=reservation.id,
            resident_id=current_resident.id,
            amount=reservation.amount,
            description=f"Reserva {zone}",
            method=method,
        )
    )
    if not charge.success:
        raise ReservationError(502, "El pago no pudo completarse.")

    reservation.status = ReservationStatus.paid
    reservation.payment_reference = charge.reference
    _ensure_receipt(reservation)
    add_reservation_event(
        db,
        reservation_id=reservation.id,
        event_type="paid",
        actor_type="resident",
        actor_id=current_resident.id,
        payload={"reference": charge.reference, "provider": charge.provider, "method": method},
    )
    ensure_access_pass(db, reservation=reservation)
    notify_reservation(
        db,
        reservation=reservation,
        template="reservation_paid",
        subject=f"Pago confirmado — {zone}",
        body=f"Pago registrado ({charge.reference}). Ya puedes usar tu pase de acceso.",
    )
    # Avoid double ready notification body — still fine to skip after_reservation_ready subject
    db.commit()
    db.refresh(reservation)
    return reservation


def get_reservation_access_pass(db: Session, *, current_resident: Resident, reservation_id: UUID) -> dict:
    from app.integrations.hooks import ensure_access_pass

    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise ReservationError(404, "Reserva no encontrada.")
    if reservation.resident_id != current_resident.id:
        raise ReservationError(403, "No puedes ver este pase.")
    if reservation.status not in {ReservationStatus.approved, ReservationStatus.paid, ReservationStatus.completed}:
        raise ReservationError(409, "El pase de acceso no está disponible en este estado.")
    if reservation.amount > 0 and reservation.status == ReservationStatus.approved:
        raise ReservationError(409, "Debes pagar la reserva antes de obtener el pase de acceso.")

    pass_obj = ensure_access_pass(db, reservation=reservation)
    if pass_obj is None:
        raise ReservationError(404, "No se pudo emitir el pase.")
    db.commit()
    db.refresh(reservation)
    return {
        "reservation_id": reservation.id,
        "code": pass_obj.code,
        "kind": pass_obj.kind,
        "pin": reservation.access_pin or pass_obj.payload.get("pin"),
        "provider": pass_obj.provider,
        "expires_at": pass_obj.expires_at,
        "status": reservation.status.value,
    }


def build_receipt(db: Session, *, reservation: Reservation) -> dict:
    from sqlalchemy.orm import joinedload

    area = db.get(CommonArea, reservation.common_area_id)
    resident = db.scalar(
        select(Resident).options(joinedload(Resident.user)).where(Resident.id == reservation.resident_id)
    )
    if area is None or resident is None:
        raise ReservationError(404, "Reserva inconsistente.")
    if reservation.status not in {ReservationStatus.approved, ReservationStatus.paid, ReservationStatus.completed}:
        raise ReservationError(409, "El comprobante solo aplica a reservas aprobadas o finalizadas.")
    _ensure_receipt(reservation)
    db.commit()
    db.refresh(reservation)
    return {
        "receipt_number": reservation.receipt_number or "",
        "reservation_id": reservation.id,
        "zone_name": area.name,
        "resident_name": resident.user.full_name if resident.user else str(resident.id),
        "starts_at": reservation.starts_at,
        "ends_at": reservation.ends_at,
        "amount": reservation.amount,
        "status": reservation.status.value,
        "issued_at": datetime.utcnow(),
    }


def run_reservation_maintenance(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    """Mark past approved as completed; expire overdue pending requests."""
    now = now or datetime.utcnow()
    completed = 0
    expired = 0

    to_complete = list(
        db.scalars(
            select(Reservation).where(
                Reservation.status.in_([ReservationStatus.approved, ReservationStatus.paid]),
                Reservation.ends_at < now,
            )
        )
    )
    from app.integrations.hooks import notify_reservation, revoke_access_pass

    for reservation in to_complete:
        reservation.status = ReservationStatus.completed
        _ensure_receipt(reservation)
        revoke_access_pass(db, reservation=reservation, reason="completed")
        add_reservation_event(
            db,
            reservation_id=reservation.id,
            event_type="completed",
            actor_type="system",
            payload={},
        )
        notify_reservation(
            db,
            reservation=reservation,
            template="reservation_completed",
            subject="Reserva finalizada",
            body="Tu reserva de zona social ha finalizado.",
        )
        completed += 1

    to_expire = list(
        db.scalars(
            select(Reservation).where(
                Reservation.status == ReservationStatus.requested,
                Reservation.starts_at < now,
            )
        )
    )
    for reservation in to_expire:
        reservation.status = ReservationStatus.rejected
        reservation.reject_reason = reservation.reject_reason or "Solicitud vencida sin aprobación."
        add_reservation_event(
            db,
            reservation_id=reservation.id,
            event_type="expired",
            actor_type="system",
            payload={},
        )
        expired += 1

    db.commit()
    return {"completed": completed, "expired": expired}
