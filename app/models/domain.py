import enum
import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, JSON, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class InvoiceStatus(str, enum.Enum):
    draft = "draft"
    issued = "issued"
    partially_paid = "partially_paid"
    paid = "paid"
    overdue = "overdue"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ReservationStatus(str, enum.Enum):
    requested = "requested"
    approved = "approved"
    paid = "paid"
    waitlisted = "waitlisted"  # legacy; no longer assigned
    cancelled = "cancelled"
    rescheduled = "rescheduled"
    rejected = "rejected"
    completed = "completed"


class VisitorStatus(str, enum.Enum):
    active = "active"
    used = "used"
    expired = "expired"
    cancelled = "cancelled"


class ResidentialComplex(Base, TimestampMixin):
    __tablename__ = "residential_complexes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    nit: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    address: Mapped[str] = mapped_column(String(240), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)

    towers: Mapped[list["Tower"]] = relationship(back_populates="complex")


class Tower(Base, TimestampMixin):
    __tablename__ = "towers"
    __table_args__ = (UniqueConstraint("complex_id", "name", name="uq_tower_complex_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    complex_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("residential_complexes.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)

    complex: Mapped[ResidentialComplex] = relationship(back_populates="towers")
    units: Mapped[list["Unit"]] = relationship(back_populates="tower")


class Unit(Base, TimestampMixin):
    __tablename__ = "units"
    __table_args__ = (UniqueConstraint("tower_id", "number", name="uq_unit_tower_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tower_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("towers.id"), nullable=False)
    number: Mapped[str] = mapped_column(String(40), nullable=False)
    coefficient: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0, nullable=False)
    administration_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    parking_slot: Mapped[str | None] = mapped_column(String(40))

    tower: Mapped[Tower] = relationship(back_populates="units")
    residents: Mapped[list["Resident"]] = relationship(back_populates="unit")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="unit")


class ResidentUser(Base, TimestampMixin):
    __tablename__ = "resident_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    resident_profile: Mapped["Resident | None"] = relationship(back_populates="user")


class AdminUser(Base, TimestampMixin):
    __tablename__ = "admin_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[str] = mapped_column(String(120), default="Administrador", nullable=False)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    complex_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("residential_complexes.id"), nullable=True)


class Resident(Base, TimestampMixin):
    __tablename__ = "residents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resident_users.id"), nullable=False, unique=True)
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id"), nullable=False)
    document_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    phone: Mapped[str] = mapped_column(String(40), nullable=False)
    resident_type: Mapped[str] = mapped_column(String(40), nullable=False)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_delinquent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[ResidentUser] = relationship(back_populates="resident_profile")
    unit: Mapped[Unit] = relationship(back_populates="residents")
    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="resident")
    pets: Mapped[list["Pet"]] = relationship(back_populates="resident")


class Vehicle(Base, TimestampMixin):
    __tablename__ = "vehicles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("residents.id"), nullable=False)
    plate: Mapped[str] = mapped_column(String(12), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)

    resident: Mapped[Resident] = relationship(back_populates="vehicles")


class Pet(Base, TimestampMixin):
    __tablename__ = "pets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("residents.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    species: Mapped[str] = mapped_column(String(60), nullable=False)
    breed: Mapped[str | None] = mapped_column(String(80))

    resident: Mapped[Resident] = relationship(back_populates="pets")


class CommonArea(Base, TimestampMixin):
    __tablename__ = "common_areas"
    __table_args__ = (Index("ix_common_areas_complex_active", "complex_id", "is_active"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    complex_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("residential_complexes.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(60), default="general", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    has_cost: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rules: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_bookable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_duration_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    max_duration_minutes: Mapped[int] = mapped_column(Integer, default=240, nullable=False)
    min_advance_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_advance_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    cleanup_buffer_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_active_per_resident: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    required_documents: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    schedules: Mapped[list["CommonAreaSchedule"]] = relationship(back_populates="common_area", cascade="all, delete-orphan")
    blackouts: Mapped[list["CommonAreaBlackout"]] = relationship(back_populates="common_area", cascade="all, delete-orphan")
    images: Mapped[list["CommonAreaImage"]] = relationship(back_populates="common_area", cascade="all, delete-orphan")
    special_hours: Mapped[list["CommonAreaSpecialHours"]] = relationship(
        back_populates="common_area", cascade="all, delete-orphan"
    )


class CommonAreaSchedule(Base, TimestampMixin):
    __tablename__ = "common_area_schedules"
    __table_args__ = (UniqueConstraint("common_area_id", "weekday", name="uq_common_area_weekday"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    common_area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("common_areas.id", ondelete="CASCADE"), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Monday .. 6=Sunday
    open_time: Mapped[time | None] = mapped_column(Time)
    close_time: Mapped[time | None] = mapped_column(Time)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    common_area: Mapped[CommonArea] = relationship(back_populates="schedules")


class CommonAreaBlackout(Base, TimestampMixin):
    __tablename__ = "common_area_blackouts"
    __table_args__ = (Index("ix_common_area_blackouts_range", "common_area_id", "starts_at", "ends_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    common_area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("common_areas.id", ondelete="CASCADE"), nullable=False)
    reason_type: Mapped[str] = mapped_column(String(40), nullable=False)  # maintenance | holiday | block
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    note: Mapped[str] = mapped_column(String(240), default="", nullable=False)

    common_area: Mapped[CommonArea] = relationship(back_populates="blackouts")


class CommonAreaImage(Base, TimestampMixin):
    __tablename__ = "common_area_images"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    common_area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("common_areas.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    common_area: Mapped[CommonArea] = relationship(back_populates="images")


class Reservation(Base, TimestampMixin):
    __tablename__ = "reservations"
    __table_args__ = (
        Index("ix_reservations_area_times", "common_area_id", "starts_at", "ends_at"),
        Index("ix_reservations_resident_status", "resident_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("residents.id"), nullable=False)
    common_area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("common_areas.id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(Enum(ReservationStatus), default=ReservationStatus.requested, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    payment_reference: Mapped[str | None] = mapped_column(String(80))
    reject_reason: Mapped[str | None] = mapped_column(String(240))
    receipt_number: Mapped[str | None] = mapped_column(String(40), unique=True)

    events: Mapped[list["ReservationEvent"]] = relationship(back_populates="reservation", cascade="all, delete-orphan")


class ReservationEvent(Base, TimestampMixin):
    __tablename__ = "reservation_events"
    __table_args__ = (Index("ix_reservation_events_reservation", "reservation_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reservation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)  # resident | admin | system
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    reservation: Mapped[Reservation] = relationship(back_populates="events")


class CommonAreaSpecialHours(Base, TimestampMixin):
    """Overrides the weekly schedule for a specific calendar date."""

    __tablename__ = "common_area_special_hours"
    __table_args__ = (UniqueConstraint("common_area_id", "on_date", name="uq_common_area_special_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    common_area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("common_areas.id", ondelete="CASCADE"), nullable=False)
    on_date: Mapped[date] = mapped_column(Date, nullable=False)
    open_time: Mapped[time | None] = mapped_column(Time)
    close_time: Mapped[time | None] = mapped_column(Time)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    note: Mapped[str] = mapped_column(String(240), default="", nullable=False)

    common_area: Mapped[CommonArea] = relationship(back_populates="special_hours")


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id"), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    late_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus), default=InvoiceStatus.issued, nullable=False)

    unit: Mapped[Unit] = relationship(back_populates="invoices")
    items: Mapped[list["InvoiceItem"]] = relationship(back_populates="invoice")


class InvoiceItem(Base, TimestampMixin):
    __tablename__ = "invoice_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    description: Mapped[str] = mapped_column(String(180), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="items")


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[str] = mapped_column(String(40), nullable=False)
    gateway_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    paid_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.approved, nullable=False)


class PaymentAgreement(Base, TimestampMixin):
    __tablename__ = "payment_agreements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    installments: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)


class VisitorInvitation(Base, TimestampMixin):
    __tablename__ = "visitor_invitations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("residents.id"), nullable=False)
    visitor_name: Mapped[str] = mapped_column(String(160), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(40))
    vehicle_plate: Mapped[str | None] = mapped_column(String(12))
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    qr_code: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    status: Mapped[VisitorStatus] = mapped_column(Enum(VisitorStatus), default=VisitorStatus.active, nullable=False)


class Announcement(Base, TimestampMixin):
    __tablename__ = "announcements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)


class PeaceClearance(Base, TimestampMixin):
    __tablename__ = "peace_clearances"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("units.id"), nullable=False)
    certificate_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AccountingEntry(Base, TimestampMixin):
    __tablename__ = "accounting_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    account_code: Mapped[str] = mapped_column(String(20), nullable=False)
    account_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(220), nullable=False)
    debit: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    credit: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    cost_center: Mapped[str] = mapped_column(String(80), default="Administracion", nullable=False)
