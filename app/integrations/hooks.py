from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.integrations.registry import get_access_port, get_notification_port
from app.models.domain import CommonArea, Reservation, Resident
from app.ports import AccessPass, AccessPassRequest, NotificationMessage


def _add_event(db: Session, **kwargs) -> None:
    from app.services.availability import add_reservation_event

    add_reservation_event(db, **kwargs)


def _recipient_for(resident: Resident) -> str:
    if resident.user and resident.user.email:
        return resident.user.email
    return str(resident.id)


def notify_reservation(
    db: Session,
    *,
    reservation: Reservation,
    template: str,
    subject: str,
    body: str,
    channel: str = "email",
) -> str | None:
    resident = db.scalar(
        select(Resident).options(joinedload(Resident.user)).where(Resident.id == reservation.resident_id)
    )
    if resident is None:
        return None
    delivery_id = get_notification_port().send(
        NotificationMessage(
            channel=channel,
            template=template,
            recipient=_recipient_for(resident),
            subject=subject,
            body=body,
            metadata={
                "reservation_id": str(reservation.id),
                "status": reservation.status.value,
            },
        )
    )
    _add_event(
        db,
        reservation_id=reservation.id,
        event_type="notified",
        actor_type="system",
        payload={"channel": channel, "template": template, "delivery_id": delivery_id},
    )
    return delivery_id


def ensure_access_pass(db: Session, *, reservation: Reservation) -> AccessPass | None:
    """Issue (or return existing) access pass for an approved/paid reservation."""
    if reservation.access_code:
        return AccessPass(
            code=reservation.access_code,
            kind="qr",
            provider="local",
            expires_at=reservation.ends_at,
            payload={"pin": reservation.access_pin or "", "reused": True},
        )

    area = db.get(CommonArea, reservation.common_area_id)
    if area is None:
        return None
    pass_obj = get_access_port().issue_pass(
        AccessPassRequest(
            reservation_id=reservation.id,
            resident_id=reservation.resident_id,
            zone_name=area.name,
            starts_at=reservation.starts_at,
            ends_at=reservation.ends_at,
        )
    )
    reservation.access_code = pass_obj.code
    reservation.access_pin = str(pass_obj.payload.get("pin") or "")
    _add_event(
        db,
        reservation_id=reservation.id,
        event_type="access_issued",
        actor_type="system",
        payload={"code": pass_obj.code, "kind": pass_obj.kind, "provider": pass_obj.provider},
    )
    return pass_obj


def revoke_access_pass(db: Session, *, reservation: Reservation, reason: str = "") -> None:
    if not reservation.access_code:
        return
    get_access_port().revoke_pass(reservation.access_code, reason=reason)
    _add_event(
        db,
        reservation_id=reservation.id,
        event_type="access_revoked",
        actor_type="system",
        payload={"code": reservation.access_code, "reason": reason},
    )
    reservation.access_code = None
    reservation.access_pin = None


def after_reservation_ready(db: Session, *, reservation: Reservation) -> None:
    """Call when reservation becomes usable (approved free, or paid)."""
    area = db.get(CommonArea, reservation.common_area_id)
    zone = area.name if area else "zona social"
    notify_reservation(
        db,
        reservation=reservation,
        template="reservation_ready",
        subject=f"Reserva confirmada — {zone}",
        body=f"Tu reserva en {zone} quedó confirmada ({reservation.starts_at} → {reservation.ends_at}).",
    )
    # Free zones get access immediately; paid zones after payment.
    if reservation.amount <= 0:
        ensure_access_pass(db, reservation=reservation)
