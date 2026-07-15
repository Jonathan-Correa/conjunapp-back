import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.auth import get_current_admin, get_current_resident
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.domain import (
    AccountingEntry,
    AdminUser,
    Announcement,
    CommonArea,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    Payment,
    PaymentAgreement,
    PeaceClearance,
    Reservation,
    ReservationStatus,
    Resident,
    ResidentUser,
    ResidentialComplex,
    Tower,
    Unit,
    VisitorInvitation,
)
from app.schemas.domain import (
    AccountingReportOut,
    AdminAuthResponse,
    AdminRegisterRequest,
    AdminUserOut,
    AnnouncementCreate,
    AnnouncementOut,
    BlackoutCreate,
    BlackoutOut,
    CommonAreaCreate,
    CommonAreaDetailOut,
    CommonAreaOut,
    CommonAreaUpdate,
    DashboardOut,
    GenerateInvoicesRequest,
    ImageItem,
    InvoiceOut,
    LoginRequest,
    PaymentAgreementCreate,
    PaymentCreate,
    PaymentOut,
    PeaceClearanceOut,
    AvailabilityOut,
    AvailabilitySlotOut,
    MaintenanceJobOut,
    ReservationAccessPassOut,
    ReservationAdminOut,
    ReservationCreate,
    ReservationOut,
    ReservationPayRequest,
    ReservationReceiptOut,
    ReservationRejectRequest,
    ReservationReschedule,
    SpecialHoursCreate,
    SpecialHoursOut,
    ResidentCreate,
    ResidentRegisterRequest,
    ResidentSummary,
    ResidentAuthResponse,
    ResidentUserOut,
    ScheduleItem,
    UnitSummary,
    VisitorCreate,
    VisitorOut,
)

router = APIRouter(prefix="/api/v1")


def _unit_balance(db: Session, unit_id: UUID) -> Decimal:
    total = db.scalar(select(func.coalesce(func.sum(Invoice.total - Invoice.paid_amount), 0)).where(Invoice.unit_id == unit_id))
    return Decimal(total or 0)


def _resident_summary(db: Session, resident: Resident) -> ResidentSummary:
    return ResidentSummary(
        id=resident.id,
        full_name=resident.user.full_name,
        email=resident.user.email,
        phone=resident.phone,
        document_number=resident.document_number,
        resident_type=resident.resident_type,
        is_owner=resident.is_owner,
        is_delinquent=_unit_balance(db, resident.unit_id) > 0,
        unit=f"{resident.unit.tower.name}-{resident.unit.number}",
        unit_id=resident.unit_id,
    )


def _resident_user_out(resident: Resident) -> ResidentUserOut:
    return ResidentUserOut(
        id=resident.user.id,
        email=resident.user.email,
        full_name=resident.user.full_name,
        resident_id=resident.id,
        unit_id=resident.unit_id,
        unit=f"{resident.unit.tower.name}-{resident.unit.number}",
        phone=resident.phone,
        document_number=resident.document_number,
    )


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/auth/admin/login", response_model=AdminAuthResponse)
def admin_login(payload: LoginRequest, db: Session = Depends(get_db)) -> AdminAuthResponse:
    user = db.scalar(select(AdminUser).where(AdminUser.email == payload.email.lower()))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales administrativas invalidas.")
    return AdminAuthResponse(
        access_token=create_access_token(user.id, "admin"),
        user=AdminUserOut.model_validate(user),
    )


@router.get("/auth/admin/me", response_model=AdminUserOut)
def admin_me(current_admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    return current_admin


@router.post("/auth/admin/register", response_model=AdminAuthResponse)
def admin_register(payload: AdminRegisterRequest, db: Session = Depends(get_db)) -> AdminAuthResponse:
    settings = get_settings()
    if not settings.allow_admin_register:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El registro publico de administradores esta deshabilitado.",
        )

    if payload.password != payload.password_confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Las contraseñas no coinciden.")

    existing = db.scalar(select(AdminUser).where(AdminUser.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Este correo ya está registrado.")

    admin_user = AdminUser(
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        position=payload.position,
        is_super_admin=False,
    )
    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)

    return AdminAuthResponse(
        access_token=create_access_token(admin_user.id, "admin"),
        user=AdminUserOut.model_validate(admin_user),
    )


@router.post("/auth/resident/login", response_model=ResidentAuthResponse)
def resident_login(payload: LoginRequest, db: Session = Depends(get_db)) -> ResidentAuthResponse:
    user = db.scalar(select(ResidentUser).where(ResidentUser.email == payload.email.lower()))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales de residente invalidas.")
    resident = db.scalar(select(Resident).where(Resident.user_id == user.id))
    if resident is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Perfil de residente no encontrado.")
    return ResidentAuthResponse(
        access_token=create_access_token(user.id, "resident"),
        user=_resident_user_out(resident),
    )


@router.get("/auth/resident/me", response_model=ResidentUserOut)
def resident_me(current_resident: Resident = Depends(get_current_resident)) -> ResidentUserOut:
    return _resident_user_out(current_resident)


@router.post("/auth/resident/register", response_model=ResidentAuthResponse)
def resident_register(payload: ResidentRegisterRequest, db: Session = Depends(get_db)) -> ResidentAuthResponse:
    # Validar que las contraseñas coincidan
    if payload.password != payload.password_confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Las contraseñas no coinciden.")
    
    # Validar que el correo no exista
    existing_user = db.scalar(select(ResidentUser).where(ResidentUser.email == payload.email.lower()))
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Este correo ya está registrado.")
    
    # Validar que el documento no exista
    existing_doc = db.scalar(select(Resident).where(Resident.document_number == payload.document_number))
    if existing_doc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Este documento ya está registrado.")
    
    tower = db.scalar(select(Tower).where(Tower.name == payload.tower_name).limit(1))
    if not tower:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Torre '{payload.tower_name}' no encontrada.",
        )

    unit = db.scalar(
        select(Unit).where(and_(Unit.tower_id == tower.id, Unit.number == payload.unit_number))
    )
    if not unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unidad '{payload.unit_number}' en la torre '{payload.tower_name}' no encontrada.",
        )

    resident_user = ResidentUser(
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
    )
    db.add(resident_user)
    db.flush()
    
    # Crear perfil de residente
    resident = Resident(
        user_id=resident_user.id,
        unit_id=unit.id,
        document_number=payload.document_number,
        phone=payload.phone,
        resident_type=payload.resident_type,
        is_owner=payload.is_owner,
    )
    db.add(resident)
    db.commit()
    db.refresh(resident_user)
    db.refresh(resident)
    
    return ResidentAuthResponse(
        access_token=create_access_token(resident_user.id, "resident"),
        user=_resident_user_out(resident),
    )


@router.get("/towers", response_model=list[dict])
def get_towers(db: Session = Depends(get_db)) -> list[dict]:
    """Get all towers with their units"""
    towers = db.scalars(select(Tower)).all()
    result = []
    for tower in towers:
        units = db.scalars(select(Unit).where(Unit.tower_id == tower.id)).all()
        result.append({
            "id": str(tower.id),
            "name": tower.name,
            "units": [
                {
                    "id": str(u.id),
                    "number": u.number,
                    "parking_slot": u.parking_slot,
                    "administration_fee": str(u.administration_fee),
                }
                for u in units
            ]
        })
    return result


@router.get("/admin/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), current_admin: AdminUser = Depends(get_current_admin)) -> DashboardOut:
    total_units = db.scalar(select(func.count(Unit.id))) or 0
    total_residents = db.scalar(select(func.count(Resident.id))) or 0
    monthly_billed = Decimal(db.scalar(select(func.coalesce(func.sum(Invoice.total), 0))) or 0)
    collected = Decimal(db.scalar(select(func.coalesce(func.sum(Invoice.paid_amount), 0))) or 0)
    overdue = Decimal(db.scalar(select(func.coalesce(func.sum(Invoice.total - Invoice.paid_amount), 0)).where(Invoice.status == InvoiceStatus.overdue)) or 0)
    delinquent_units = db.scalar(select(func.count(func.distinct(Invoice.unit_id))).where(Invoice.status == InvoiceStatus.overdue)) or 0
    active_query = select(func.count(Reservation.id)).where(
        Reservation.status.in_([ReservationStatus.approved, ReservationStatus.paid])
    )
    if current_admin.complex_id is not None:
        active_query = active_query.join(CommonArea, CommonArea.id == Reservation.common_area_id).where(
            CommonArea.complex_id == current_admin.complex_id
        )
    active_reservations = db.scalar(active_query) or 0
    rate = float(collected / monthly_billed * 100) if monthly_billed else 0
    return DashboardOut(
        total_units=total_units,
        total_residents=total_residents,
        monthly_billed=monthly_billed,
        collected=collected,
        overdue=overdue,
        delinquent_units=delinquent_units,
        active_reservations=active_reservations,
        monthly_collection_rate=round(rate, 2),
    )


@router.get("/admin/units", response_model=list[UnitSummary])
def list_units(db: Session = Depends(get_db), current_admin: AdminUser = Depends(get_current_admin)) -> list[UnitSummary]:
    units = db.scalars(select(Unit).join(Tower).order_by(Tower.name, Unit.number)).all()
    return [
        UnitSummary(
            id=unit.id,
            tower=unit.tower.name,
            number=unit.number,
            administration_fee=unit.administration_fee,
            parking_slot=unit.parking_slot,
            balance=_unit_balance(db, unit.id),
        )
        for unit in units
    ]


@router.get("/admin/residents", response_model=list[ResidentSummary])
def list_residents(db: Session = Depends(get_db), current_admin: AdminUser = Depends(get_current_admin)) -> list[ResidentSummary]:
    residents = db.scalars(select(Resident).join(ResidentUser).join(Unit).order_by(ResidentUser.full_name)).all()
    return [_resident_summary(db, resident) for resident in residents]


@router.post("/admin/residents", response_model=ResidentSummary, status_code=status.HTTP_201_CREATED)
def create_resident(payload: ResidentCreate, db: Session = Depends(get_db), current_admin: AdminUser = Depends(get_current_admin)) -> ResidentSummary:
    complex_ = db.scalar(select(ResidentialComplex).limit(1))
    if complex_ is None:
        complex_ = ResidentialComplex(name="Conjunto Principal", nit=f"NIT-{uuid.uuid4().hex[:8]}", address="Pendiente", city="Bogota")
        db.add(complex_)
        db.flush()

    tower = db.scalar(select(Tower).where(Tower.complex_id == complex_.id, Tower.name == payload.tower_name))
    if tower is None:
        tower = Tower(complex_id=complex_.id, name=payload.tower_name)
        db.add(tower)
        db.flush()

    unit = db.scalar(select(Unit).where(Unit.tower_id == tower.id, Unit.number == payload.unit_number))
    if unit is None:
        unit = Unit(tower_id=tower.id, number=payload.unit_number, administration_fee=payload.administration_fee, parking_slot=payload.parking_slot)
        db.add(unit)
        db.flush()

    user = ResidentUser(
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.initial_password),
    )
    resident = Resident(
        user=user,
        unit=unit,
        document_number=payload.document_number,
        phone=payload.phone,
        resident_type=payload.resident_type,
        is_owner=payload.is_owner,
    )
    db.add(resident)
    db.commit()
    db.refresh(resident)
    return _resident_summary(db, resident)


@router.get("/common-areas", response_model=list[CommonAreaOut])
def common_areas(
    db: Session = Depends(get_db),
    current_resident: Resident = Depends(get_current_resident),
) -> list[CommonAreaOut]:
    """Zonas sociales activas del conjunto del residente autenticado."""
    from app.services.common_areas import to_common_area_out
    from app.services.reservations import ReservationError, get_resident_complex_id, list_active_common_areas_for_complex

    try:
        complex_id = get_resident_complex_id(db, current_resident)
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return [to_common_area_out(a) for a in list_active_common_areas_for_complex(db, complex_id)]


@router.get("/common-areas/{area_id}", response_model=CommonAreaDetailOut)
def common_area_detail(
    area_id: UUID,
    db: Session = Depends(get_db),
    current_resident: Resident = Depends(get_current_resident),
) -> CommonAreaDetailOut:
    from app.services.common_areas import get_area, to_detail
    from app.services.reservations import ReservationError, get_resident_complex_id

    area = get_area(db, area_id)
    if area is None or not area.is_active:
        raise HTTPException(status_code=404, detail="Zona social no encontrada.")
    try:
        complex_id = get_resident_complex_id(db, current_resident)
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    if area.complex_id != complex_id:
        raise HTTPException(status_code=403, detail="La zona social no pertenece a tu conjunto.")
    return to_detail(area)


@router.get("/common-areas/{area_id}/availability", response_model=AvailabilityOut)
def common_area_availability(
    area_id: UUID,
    on_date: date = Query(..., alias="date"),
    duration_minutes: int | None = None,
    exclude_reservation_id: UUID | None = None,
    db: Session = Depends(get_db),
    current_resident: Resident = Depends(get_current_resident),
) -> AvailabilityOut:
    from app.services.availability import get_availability
    from app.services.common_areas import get_area
    from app.services.reservations import ReservationError, get_resident_complex_id

    area = get_area(db, area_id)
    if area is None or not area.is_active:
        raise HTTPException(status_code=404, detail="Zona social no encontrada.")
    try:
        complex_id = get_resident_complex_id(db, current_resident)
        if area.complex_id != complex_id:
            raise HTTPException(status_code=403, detail="La zona social no pertenece a tu conjunto.")
        if exclude_reservation_id is not None:
            owned = db.get(Reservation, exclude_reservation_id)
            if owned is None or owned.resident_id != current_resident.id:
                raise HTTPException(status_code=403, detail="No puedes excluir esa reserva.")
        duration = duration_minutes or area.min_duration_minutes
        slots = get_availability(
            db,
            area=area,
            day=on_date,
            duration_minutes=duration,
            exclude_reservation_id=exclude_reservation_id,
        )
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return AvailabilityOut(
        common_area_id=area.id,
        date=on_date,
        duration_minutes=duration,
        slots=[AvailabilitySlotOut(**s) for s in slots],
    )


@router.get("/admin/common-areas", response_model=list[CommonAreaOut])
def admin_common_areas(
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> list[CommonAreaOut]:
    from app.services.common_areas import to_common_area_out
    from app.services.reservations import list_common_areas_for_admin

    return [to_common_area_out(a) for a in list_common_areas_for_admin(db, current_admin.complex_id)]


@router.post("/admin/common-areas", response_model=CommonAreaOut, status_code=status.HTTP_201_CREATED)
def admin_create_common_area(
    payload: CommonAreaCreate,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> CommonAreaOut:
    from app.services.common_areas import create_common_area, to_common_area_out
    from app.services.reservations import ReservationError

    try:
        area = create_common_area(db, admin_complex_id=current_admin.complex_id, payload=payload)
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return to_common_area_out(area)


@router.get("/admin/common-areas/{area_id}", response_model=CommonAreaDetailOut)
def admin_common_area_detail(
    area_id: UUID,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> CommonAreaDetailOut:
    from app.services.common_areas import get_area, to_detail

    area = get_area(db, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="Zona social no encontrada.")
    if current_admin.complex_id and area.complex_id != current_admin.complex_id:
        raise HTTPException(status_code=403, detail="Zona fuera de tu conjunto.")
    return to_detail(area)


@router.patch("/admin/common-areas/{area_id}", response_model=CommonAreaOut)
def admin_update_common_area(
    area_id: UUID,
    payload: CommonAreaUpdate,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> CommonAreaOut:
    from app.services.common_areas import get_area, to_common_area_out, update_common_area
    from app.services.reservations import ReservationError

    area = get_area(db, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="Zona social no encontrada.")
    if current_admin.complex_id and area.complex_id != current_admin.complex_id:
        raise HTTPException(status_code=403, detail="Zona fuera de tu conjunto.")
    try:
        area = update_common_area(db, area=area, payload=payload)
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return to_common_area_out(area)


@router.delete("/admin/common-areas/{area_id}", response_model=CommonAreaOut)
def admin_deactivate_common_area(
    area_id: UUID,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> CommonAreaOut:
    from app.services.common_areas import deactivate_common_area, get_area, to_common_area_out

    area = get_area(db, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="Zona social no encontrada.")
    if current_admin.complex_id and area.complex_id != current_admin.complex_id:
        raise HTTPException(status_code=403, detail="Zona fuera de tu conjunto.")
    return to_common_area_out(deactivate_common_area(db, area=area))


@router.put("/admin/common-areas/{area_id}/schedules", response_model=CommonAreaDetailOut)
def admin_replace_schedules(
    area_id: UUID,
    items: list[ScheduleItem],
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> CommonAreaDetailOut:
    from app.services.common_areas import get_area, replace_schedules, to_detail
    from app.services.reservations import ReservationError

    area = get_area(db, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="Zona social no encontrada.")
    if current_admin.complex_id and area.complex_id != current_admin.complex_id:
        raise HTTPException(status_code=403, detail="Zona fuera de tu conjunto.")
    try:
        area = replace_schedules(db, area=area, items=items)
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return to_detail(area)


@router.post("/admin/common-areas/{area_id}/blackouts", response_model=BlackoutOut, status_code=status.HTTP_201_CREATED)
def admin_create_blackout(
    area_id: UUID,
    payload: BlackoutCreate,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> BlackoutOut:
    from app.services.common_areas import create_blackout, get_area
    from app.services.reservations import ReservationError

    area = get_area(db, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="Zona social no encontrada.")
    if current_admin.complex_id and area.complex_id != current_admin.complex_id:
        raise HTTPException(status_code=403, detail="Zona fuera de tu conjunto.")
    try:
        row = create_blackout(db, area=area, payload=payload)
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return BlackoutOut.model_validate(row)


@router.delete("/admin/common-areas/{area_id}/blackouts/{blackout_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_blackout(
    area_id: UUID,
    blackout_id: UUID,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> None:
    from app.services.common_areas import delete_blackout, get_area
    from app.services.reservations import ReservationError

    area = get_area(db, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="Zona social no encontrada.")
    if current_admin.complex_id and area.complex_id != current_admin.complex_id:
        raise HTTPException(status_code=403, detail="Zona fuera de tu conjunto.")
    try:
        delete_blackout(db, area=area, blackout_id=blackout_id)
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.put("/admin/common-areas/{area_id}/images", response_model=CommonAreaDetailOut)
def admin_replace_images(
    area_id: UUID,
    items: list[ImageItem],
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> CommonAreaDetailOut:
    from app.services.common_areas import get_area, replace_images, to_detail
    from app.services.reservations import ReservationError

    area = get_area(db, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="Zona social no encontrada.")
    if current_admin.complex_id and area.complex_id != current_admin.complex_id:
        raise HTTPException(status_code=403, detail="Zona fuera de tu conjunto.")
    try:
        area = replace_images(db, area=area, items=items)
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return to_detail(area)


@router.post(
    "/admin/common-areas/{area_id}/special-hours",
    response_model=SpecialHoursOut,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_special_hours(
    area_id: UUID,
    payload: SpecialHoursCreate,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> SpecialHoursOut:
    from app.services.common_areas import create_special_hours, get_area
    from app.services.reservations import ReservationError

    area = get_area(db, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="Zona social no encontrada.")
    if current_admin.complex_id and area.complex_id != current_admin.complex_id:
        raise HTTPException(status_code=403, detail="Zona fuera de tu conjunto.")
    try:
        row = create_special_hours(db, area=area, payload=payload)
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return SpecialHoursOut(
        id=row.id,
        common_area_id=row.common_area_id,
        on_date=row.on_date,
        open_time=row.open_time.strftime("%H:%M") if row.open_time else None,
        close_time=row.close_time.strftime("%H:%M") if row.close_time else None,
        is_closed=row.is_closed,
        note=row.note or "",
    )


@router.delete("/admin/common-areas/{area_id}/special-hours/{special_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_special_hours(
    area_id: UUID,
    special_id: UUID,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> None:
    from app.services.common_areas import delete_special_hours, get_area
    from app.services.reservations import ReservationError

    area = get_area(db, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="Zona social no encontrada.")
    if current_admin.complex_id and area.complex_id != current_admin.complex_id:
        raise HTTPException(status_code=403, detail="Zona fuera de tu conjunto.")
    try:
        delete_special_hours(db, area=area, special_id=special_id)
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/admin/reservations", response_model=list[ReservationAdminOut])
def admin_list_reservations(
    from_date: date | None = None,
    to_date: date | None = None,
    common_area_id: UUID | None = None,
    resident_id: UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> list[ReservationAdminOut]:
    query = (
        select(Reservation, ResidentUser.full_name, CommonArea.name)
        .join(Resident, Resident.id == Reservation.resident_id)
        .join(ResidentUser, ResidentUser.id == Resident.user_id)
        .join(CommonArea, CommonArea.id == Reservation.common_area_id)
        .order_by(Reservation.starts_at.desc())
    )
    if current_admin.complex_id is not None:
        query = query.where(CommonArea.complex_id == current_admin.complex_id)
    if common_area_id:
        query = query.where(Reservation.common_area_id == common_area_id)
    if resident_id:
        query = query.where(Reservation.resident_id == resident_id)
    if status_filter:
        try:
            status_value = ReservationStatus(status_filter)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Estado de reserva inválido.") from exc
        query = query.where(Reservation.status == status_value)
    if from_date:
        query = query.where(Reservation.starts_at >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        query = query.where(Reservation.starts_at < datetime.combine(to_date, datetime.min.time()) + timedelta(days=1))

    rows = db.execute(query).all()
    return [
        ReservationAdminOut(
            id=reservation.id,
            resident_id=reservation.resident_id,
            common_area_id=reservation.common_area_id,
            starts_at=reservation.starts_at,
            ends_at=reservation.ends_at,
            status=reservation.status,
            amount=reservation.amount,
            payment_reference=reservation.payment_reference,
            reject_reason=reservation.reject_reason,
            receipt_number=reservation.receipt_number,
            access_code=reservation.access_code,
            resident_name=resident_name,
            common_area_name=area_name,
        )
        for reservation, resident_name, area_name in rows
    ]


@router.get("/admin/reservations/export")
def admin_export_reservations(
    from_date: date | None = None,
    to_date: date | None = None,
    common_area_id: UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> Response:
    import csv
    import io

    query = (
        select(Reservation, ResidentUser.full_name, CommonArea.name)
        .join(CommonArea, CommonArea.id == Reservation.common_area_id)
        .join(Resident, Resident.id == Reservation.resident_id)
        .join(ResidentUser, ResidentUser.id == Resident.user_id)
        .order_by(Reservation.starts_at.desc())
    )
    if current_admin.complex_id:
        query = query.where(CommonArea.complex_id == current_admin.complex_id)
    if common_area_id:
        query = query.where(Reservation.common_area_id == common_area_id)
    if status_filter:
        try:
            query = query.where(Reservation.status == ReservationStatus(status_filter))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Estado inválido.") from exc
    if from_date:
        query = query.where(Reservation.starts_at >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        query = query.where(Reservation.starts_at < datetime.combine(to_date, datetime.min.time()) + timedelta(days=1))

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "resident_name",
            "common_area_name",
            "starts_at",
            "ends_at",
            "status",
            "amount",
            "receipt_number",
            "reject_reason",
        ]
    )
    for reservation, resident_name, area_name in db.execute(query).all():
        writer.writerow(
            [
                str(reservation.id),
                resident_name,
                area_name,
                reservation.starts_at.isoformat(),
                reservation.ends_at.isoformat(),
                reservation.status.value,
                str(reservation.amount),
                reservation.receipt_number or "",
                reservation.reject_reason or "",
            ]
        )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=reservas.csv"},
    )


@router.post("/admin/jobs/reservations-maintenance", response_model=MaintenanceJobOut)
def admin_run_reservations_maintenance(
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> MaintenanceJobOut:
    from app.services.availability import run_reservation_maintenance

    _ = current_admin
    return MaintenanceJobOut(**run_reservation_maintenance(db))


@router.post("/admin/reservations/{reservation_id}/approve", response_model=ReservationAdminOut)
def admin_approve_reservation(
    reservation_id: UUID,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> ReservationAdminOut:
    from app.services.availability import approve_reservation

    return _admin_mutation(db, current_admin, reservation_id, lambda r: approve_reservation(db, reservation=r, admin_id=current_admin.id))


@router.post("/admin/reservations/{reservation_id}/reject", response_model=ReservationAdminOut)
def admin_reject_reservation(
    reservation_id: UUID,
    payload: ReservationRejectRequest,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> ReservationAdminOut:
    from app.services.availability import reject_reservation

    return _admin_mutation(
        db,
        current_admin,
        reservation_id,
        lambda r: reject_reservation(db, reservation=r, admin_id=current_admin.id, reason=payload.reason),
    )


@router.post("/admin/reservations/{reservation_id}/cancel", response_model=ReservationAdminOut)
def admin_cancel_reservation_route(
    reservation_id: UUID,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> ReservationAdminOut:
    from app.services.availability import admin_cancel_reservation

    return _admin_mutation(
        db,
        current_admin,
        reservation_id,
        lambda r: admin_cancel_reservation(db, reservation=r, admin_id=current_admin.id),
    )


def _admin_mutation(db: Session, current_admin: AdminUser, reservation_id: UUID, action) -> ReservationAdminOut:
    from app.services.reservations import ReservationError

    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reserva no encontrada.")
    area = db.get(CommonArea, reservation.common_area_id)
    resident = db.scalar(
        select(Resident).options(joinedload(Resident.user)).where(Resident.id == reservation.resident_id)
    )
    if area is None or resident is None:
        raise HTTPException(status_code=404, detail="Reserva inconsistente.")
    if current_admin.complex_id and area.complex_id != current_admin.complex_id:
        raise HTTPException(status_code=403, detail="Reserva fuera de tu conjunto.")
    try:
        reservation = action(reservation)
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return ReservationAdminOut(
        id=reservation.id,
        resident_id=reservation.resident_id,
        common_area_id=reservation.common_area_id,
        starts_at=reservation.starts_at,
        ends_at=reservation.ends_at,
        status=reservation.status,
        amount=reservation.amount,
        payment_reference=reservation.payment_reference,
        reject_reason=reservation.reject_reason,
        receipt_number=reservation.receipt_number,
        access_code=reservation.access_code,
        resident_name=resident.user.full_name if resident.user else str(resident.id),
        common_area_name=area.name,
    )


@router.get("/reservations", response_model=list[ReservationOut])
def list_reservations(
    resident_id: UUID | None = None,
    db: Session = Depends(get_db),
    current_resident: Resident = Depends(get_current_resident),
) -> list[Reservation]:
    query = select(Reservation).order_by(Reservation.starts_at.desc())
    query = query.where(Reservation.resident_id == current_resident.id)
    return list(db.scalars(query))


@router.post("/reservations", response_model=ReservationOut, status_code=status.HTTP_201_CREATED)
def create_reservation(
    payload: ReservationCreate,
    db: Session = Depends(get_db),
    current_resident: Resident = Depends(get_current_resident),
) -> Reservation:
    from app.services.reservations import ReservationError, create_reservation as create_reservation_service

    try:
        return create_reservation_service(
            db,
            current_resident=current_resident,
            common_area_id=payload.common_area_id,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
        )
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.patch("/reservations/{reservation_id}/reschedule", response_model=ReservationOut)
def reschedule_reservation_route(
    reservation_id: UUID,
    payload: ReservationReschedule,
    db: Session = Depends(get_db),
    current_resident: Resident = Depends(get_current_resident),
) -> Reservation:
    from app.services.availability import reschedule_reservation
    from app.services.reservations import ReservationError

    try:
        return reschedule_reservation(
            db,
            current_resident=current_resident,
            reservation_id=reservation_id,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
        )
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/reservations/{reservation_id}/receipt", response_model=ReservationReceiptOut)
def reservation_receipt(
    reservation_id: UUID,
    db: Session = Depends(get_db),
    current_resident: Resident = Depends(get_current_resident),
) -> ReservationReceiptOut:
    from app.services.availability import build_receipt
    from app.services.reservations import ReservationError

    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reserva no encontrada.")
    if reservation.resident_id != current_resident.id:
        raise HTTPException(status_code=403, detail="No puedes ver este comprobante.")
    try:
        return ReservationReceiptOut(**build_receipt(db, reservation=reservation))
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/reservations/{reservation_id}/pay", response_model=ReservationOut)
def pay_reservation_route(
    reservation_id: UUID,
    payload: ReservationPayRequest,
    db: Session = Depends(get_db),
    current_resident: Resident = Depends(get_current_resident),
) -> Reservation:
    from app.services.availability import pay_reservation
    from app.services.reservations import ReservationError

    try:
        return pay_reservation(
            db,
            current_resident=current_resident,
            reservation_id=reservation_id,
            method=payload.method or "PSE",
        )
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/reservations/{reservation_id}/access-pass", response_model=ReservationAccessPassOut)
def reservation_access_pass(
    reservation_id: UUID,
    db: Session = Depends(get_db),
    current_resident: Resident = Depends(get_current_resident),
) -> ReservationAccessPassOut:
    from app.services.availability import get_reservation_access_pass
    from app.services.reservations import ReservationError

    try:
        return ReservationAccessPassOut(
            **get_reservation_access_pass(db, current_resident=current_resident, reservation_id=reservation_id)
        )
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/reservations/{reservation_id}/ical")
def reservation_ical(
    reservation_id: UUID,
    db: Session = Depends(get_db),
    current_resident: Resident = Depends(get_current_resident),
) -> Response:
    from app.integrations.registry import get_calendar_port
    from app.ports import CalendarEvent

    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reserva no encontrada.")
    if reservation.resident_id != current_resident.id:
        raise HTTPException(status_code=403, detail="No puedes exportar esta reserva.")
    area = db.get(CommonArea, reservation.common_area_id)
    ical = get_calendar_port().to_ical(
        [
            CalendarEvent(
                uid=f"{reservation.id}@conjunapp.local",
                summary=f"Reserva {(area.name if area else 'zona social')}",
                description=f"Estado: {reservation.status.value}",
                starts_at=reservation.starts_at,
                ends_at=reservation.ends_at,
                location=area.name if area else "",
            )
        ]
    )
    return Response(
        content=ical,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="reserva-{reservation_id}.ics"'},
    )


@router.patch("/reservations/{reservation_id}/cancel", response_model=ReservationOut)
def cancel_reservation(
    reservation_id: UUID,
    db: Session = Depends(get_db),
    current_resident: Resident = Depends(get_current_resident),
) -> Reservation:
    from app.services.reservations import ReservationError, cancel_reservation as cancel_reservation_service

    try:
        return cancel_reservation_service(db, current_resident=current_resident, reservation_id=reservation_id)
    except ReservationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/invoices", response_model=list[InvoiceOut])
def invoices(
    unit_id: UUID | None = None,
    only_open: bool = False,
    db: Session = Depends(get_db),
    current_resident: Resident = Depends(get_current_resident),
) -> list[Invoice]:
    query = select(Invoice).order_by(Invoice.issue_date.desc())
    query = query.where(Invoice.unit_id == current_resident.unit_id)
    if only_open:
        query = query.where(Invoice.status.in_([InvoiceStatus.issued, InvoiceStatus.partially_paid, InvoiceStatus.overdue]))
    return list(db.scalars(query))


@router.get("/admin/invoices", response_model=list[InvoiceOut])
def admin_invoices(
    unit_id: UUID | None = None,
    only_open: bool = False,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> list[Invoice]:
    query = select(Invoice).order_by(Invoice.issue_date.desc())
    if unit_id:
        query = query.where(Invoice.unit_id == unit_id)
    if only_open:
        query = query.where(Invoice.status.in_([InvoiceStatus.issued, InvoiceStatus.partially_paid, InvoiceStatus.overdue]))
    return list(db.scalars(query))


@router.post("/admin/invoices/generate", response_model=list[InvoiceOut], status_code=status.HTTP_201_CREATED)
def generate_invoices(payload: GenerateInvoicesRequest, db: Session = Depends(get_db), current_admin: AdminUser = Depends(get_current_admin)) -> list[Invoice]:
    created: list[Invoice] = []
    units = db.scalars(select(Unit).order_by(Unit.created_at)).all()
    for index, unit in enumerate(units, start=1):
        exists = db.scalar(select(Invoice).where(Invoice.unit_id == unit.id, Invoice.period == payload.period))
        if exists:
            continue
        invoice = Invoice(
            unit_id=unit.id,
            invoice_number=f"FAC-{payload.period.replace('-', '')}-{index:04d}",
            issue_date=payload.issue_date,
            due_date=payload.due_date,
            period=payload.period,
            subtotal=unit.administration_fee,
            total=unit.administration_fee,
            paid_amount=Decimal("0"),
            status=InvoiceStatus.issued,
        )
        db.add(invoice)
        db.flush()
        db.add(InvoiceItem(invoice_id=invoice.id, description="Cuota de administracion", amount=unit.administration_fee))
        created.append(invoice)
    db.commit()
    return created


@router.post("/payments", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def register_payment(payload: PaymentCreate, db: Session = Depends(get_db), current_resident: Resident = Depends(get_current_resident)) -> Payment:
    invoice = db.get(Invoice, payload.invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Factura no encontrada.")
    if invoice.unit_id != current_resident.unit_id:
        raise HTTPException(status_code=403, detail="No puedes pagar esta factura.")

    remaining = invoice.total - invoice.paid_amount
    if remaining <= 0:
        raise HTTPException(status_code=400, detail="La factura ya esta pagada.")
    if payload.amount > remaining:
        raise HTTPException(
            status_code=400,
            detail=f"El pago excede el saldo pendiente ({remaining}).",
        )

    payment = Payment(**payload.model_dump())
    invoice.paid_amount += payload.amount
    if invoice.paid_amount >= invoice.total:
        invoice.status = InvoiceStatus.paid
    elif invoice.paid_amount > 0:
        invoice.status = InvoiceStatus.partially_paid
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


@router.post("/admin/payment-agreements", status_code=status.HTTP_201_CREATED)
def create_payment_agreement(payload: PaymentAgreementCreate, db: Session = Depends(get_db), current_admin: AdminUser = Depends(get_current_admin)) -> dict[str, str]:
    if db.get(Unit, payload.unit_id) is None:
        raise HTTPException(status_code=404, detail="Unidad no encontrada.")
    agreement = PaymentAgreement(**payload.model_dump())
    db.add(agreement)
    db.commit()
    return {"id": str(agreement.id), "status": agreement.status}


@router.post("/visitors", response_model=VisitorOut, status_code=status.HTTP_201_CREATED)
def create_visitor(payload: VisitorCreate, db: Session = Depends(get_db), current_resident: Resident = Depends(get_current_resident)) -> VisitorInvitation:
    if payload.valid_until <= payload.valid_from:
        raise HTTPException(status_code=400, detail="La fecha final debe ser posterior a la inicial.")
    if db.get(Resident, current_resident.id) is None:
        raise HTTPException(status_code=404, detail="Residente no encontrado.")
    visitor_payload = payload.model_dump()
    visitor_payload["resident_id"] = current_resident.id
    visitor = VisitorInvitation(**visitor_payload, qr_code=f"VIS-{uuid.uuid4().hex[:12].upper()}")
    db.add(visitor)
    db.commit()
    db.refresh(visitor)
    return visitor


@router.get("/visitors", response_model=list[VisitorOut])
def list_visitors(
    resident_id: UUID | None = None,
    db: Session = Depends(get_db),
    current_resident: Resident = Depends(get_current_resident),
) -> list[VisitorInvitation]:
    query = select(VisitorInvitation).order_by(VisitorInvitation.valid_from.desc())
    query = query.where(VisitorInvitation.resident_id == current_resident.id)
    return list(db.scalars(query))


@router.get("/announcements", response_model=list[AnnouncementOut])
def list_announcements(db: Session = Depends(get_db)) -> list[Announcement]:
    now = datetime.utcnow()
    return list(db.scalars(select(Announcement).where(or_(Announcement.expires_at.is_(None), Announcement.expires_at > now)).order_by(Announcement.published_at.desc())))


@router.post("/admin/announcements", response_model=AnnouncementOut, status_code=status.HTTP_201_CREATED)
def create_announcement(payload: AnnouncementCreate, db: Session = Depends(get_db), current_admin: AdminUser = Depends(get_current_admin)) -> Announcement:
    announcement = Announcement(**payload.model_dump())
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    return announcement


@router.post("/admin/peace-clearances/{unit_id}", response_model=PeaceClearanceOut, status_code=status.HTTP_201_CREATED)
def issue_peace_clearance(unit_id: UUID, db: Session = Depends(get_db), current_admin: AdminUser = Depends(get_current_admin)) -> PeaceClearance:
    if db.get(Unit, unit_id) is None:
        raise HTTPException(status_code=404, detail="Unidad no encontrada.")
    if _unit_balance(db, unit_id) > 0:
        raise HTTPException(status_code=409, detail="La unidad tiene saldo pendiente.")
    certificate = PeaceClearance(
        unit_id=unit_id,
        certificate_number=f"PS-{date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
        valid_until=date.today() + timedelta(days=30),
    )
    db.add(certificate)
    db.commit()
    db.refresh(certificate)
    return certificate


@router.get("/admin/accounting-report", response_model=AccountingReportOut)
def accounting_report(db: Session = Depends(get_db), current_admin: AdminUser = Depends(get_current_admin)) -> AccountingReportOut:
    entries = db.scalars(select(AccountingEntry).order_by(AccountingEntry.entry_date.desc())).all()
    income = sum((entry.credit for entry in entries if entry.account_code.startswith("4")), Decimal("0"))
    expenses = sum((entry.debit for entry in entries if entry.account_code.startswith("5")), Decimal("0"))
    receivables = Decimal(db.scalar(select(func.coalesce(func.sum(Invoice.total - Invoice.paid_amount), 0))) or 0)
    return AccountingReportOut(
        income=income,
        expenses=expenses,
        net_result=income - expenses,
        receivables=receivables,
        entries=[
            {
                "date": entry.entry_date.isoformat(),
                "account": f"{entry.account_code} - {entry.account_name}",
                "description": entry.description,
                "debit": str(entry.debit),
                "credit": str(entry.credit),
                "cost_center": entry.cost_center,
            }
            for entry in entries
        ],
    )
