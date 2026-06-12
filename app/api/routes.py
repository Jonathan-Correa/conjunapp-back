import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.auth import get_current_admin, get_current_resident
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
    CommonAreaOut,
    DashboardOut,
    GenerateInvoicesRequest,
    InvoiceOut,
    LoginRequest,
    PaymentAgreementCreate,
    PaymentCreate,
    PaymentOut,
    PeaceClearanceOut,
    ReservationCreate,
    ReservationOut,
    ResidentCreate,
    ResidentRegisterRequest,
    ResidentSummary,
    ResidentAuthResponse,
    ResidentUserOut,
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
    # Validar que las contraseñas coincidan
    if payload.password != payload.password_confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Las contraseñas no coinciden.")
    
    # Validar que el correo no exista
    existing = db.scalar(select(AdminUser).where(AdminUser.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Este correo ya está registrado.")
    
    # Crear nuevo administrador
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
    
    # Obtener o crear la unidad
    try:
        tower = db.scalar(select(Tower).where(Tower.name == payload.tower_name).limit(1))
        if not tower:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Torre '{payload.tower_name}' no encontrada.")
        
        unit = db.scalar(select(Unit).where(
            and_(Unit.tower_id == tower.id, Unit.number == payload.unit_number)
        ))
        if not unit:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unidad '{payload.unit_number}' en la torre '{payload.tower_name}' no encontrada.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
    # Crear usuario residente
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
    active_reservations = db.scalar(select(func.count(Reservation.id)).where(Reservation.status.in_([ReservationStatus.approved, ReservationStatus.paid]))) or 0
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

    user = ResidentUser(email=payload.email.lower(), full_name=payload.full_name, password_hash=hash_password(payload.document_number))
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
def common_areas(db: Session = Depends(get_db)) -> list[CommonArea]:
    return list(db.scalars(select(CommonArea).where(CommonArea.is_active.is_(True)).order_by(CommonArea.name)))


@router.get("/admin/reservations", response_model=list[ReservationOut])
def admin_list_reservations(db: Session = Depends(get_db), current_admin: AdminUser = Depends(get_current_admin)) -> list[Reservation]:
    return list(db.scalars(select(Reservation).order_by(Reservation.starts_at.desc())))


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
def create_reservation(payload: ReservationCreate, db: Session = Depends(get_db), current_resident: Resident = Depends(get_current_resident)) -> Reservation:
    if payload.ends_at <= payload.starts_at:
        raise HTTPException(status_code=400, detail="La fecha final debe ser posterior a la inicial.")

    area = db.get(CommonArea, payload.common_area_id)
    resident = db.get(Resident, current_resident.id)
    if area is None or resident is None:
        raise HTTPException(status_code=404, detail="Residente o zona comun no existe.")

    overlap = db.scalar(
        select(Reservation).where(
            Reservation.common_area_id == payload.common_area_id,
            Reservation.status.in_([ReservationStatus.approved, ReservationStatus.paid, ReservationStatus.requested]),
            or_(
                and_(Reservation.starts_at <= payload.starts_at, Reservation.ends_at > payload.starts_at),
                and_(Reservation.starts_at < payload.ends_at, Reservation.ends_at >= payload.ends_at),
                and_(Reservation.starts_at >= payload.starts_at, Reservation.ends_at <= payload.ends_at),
            ),
        )
    )
    hours = Decimal((payload.ends_at - payload.starts_at).total_seconds() / 3600).quantize(Decimal("0.01"))
    status_value = ReservationStatus.waitlisted if overlap else (ReservationStatus.requested if area.requires_approval else ReservationStatus.approved)
    reservation = Reservation(
        resident_id=current_resident.id,
        common_area_id=payload.common_area_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        status=status_value,
        amount=area.hourly_rate * hours,
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return reservation


@router.patch("/reservations/{reservation_id}/cancel", response_model=ReservationOut)
def cancel_reservation(reservation_id: UUID, db: Session = Depends(get_db), current_resident: Resident = Depends(get_current_resident)) -> Reservation:
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reserva no encontrada.")
    if reservation.resident_id != current_resident.id:
        raise HTTPException(status_code=403, detail="No puedes cancelar esta reserva.")
    reservation.status = ReservationStatus.cancelled
    db.commit()
    db.refresh(reservation)
    return reservation


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
