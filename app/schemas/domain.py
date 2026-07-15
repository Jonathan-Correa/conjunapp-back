from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.domain import InvoiceStatus, ReservationStatus, VisitorStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UnitSummary(ORMModel):
    id: UUID
    tower: str
    number: str
    administration_fee: Decimal
    parking_slot: str | None
    balance: Decimal = Decimal("0")


class ResidentSummary(ORMModel):
    id: UUID
    full_name: str
    email: str
    phone: str
    document_number: str
    resident_type: str
    is_owner: bool
    is_delinquent: bool
    unit: str
    unit_id: UUID


class AdminUserOut(ORMModel):
    id: UUID
    email: str
    full_name: str
    position: str
    is_super_admin: bool


class ResidentUserOut(ORMModel):
    id: UUID
    email: str
    full_name: str
    resident_id: UUID
    unit_id: UUID
    unit: str
    phone: str
    document_number: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AdminRegisterRequest(BaseModel):
    email: str
    full_name: str
    password: str
    password_confirm: str
    position: str = "Administrador"


class ResidentRegisterRequest(BaseModel):
    email: str
    full_name: str
    password: str
    password_confirm: str
    phone: str
    document_number: str
    resident_type: str = "owner"
    is_owner: bool = True
    tower_name: str
    unit_number: str
    parking_slot: str | None = None


class AdminAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AdminUserOut


class ResidentAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: ResidentUserOut


class ResidentCreate(BaseModel):
    full_name: str
    email: str
    phone: str
    document_number: str
    resident_type: str = "owner"
    is_owner: bool = True
    tower_name: str
    unit_number: str
    administration_fee: Decimal = Field(gt=0)
    parking_slot: str | None = None
    initial_password: str = Field(min_length=8)


class CommonAreaOut(ORMModel):
    id: UUID
    name: str
    category: str = "general"
    description: str = ""
    capacity: int
    hourly_rate: Decimal
    has_cost: bool = False
    requires_approval: bool
    rules: str
    is_active: bool
    is_bookable: bool = True
    min_duration_minutes: int = 60
    max_duration_minutes: int = 240
    min_advance_minutes: int = 0
    max_advance_days: int = 90
    cleanup_buffer_minutes: int = 0
    max_active_per_resident: int = 3
    required_documents: list[str] = Field(default_factory=list)


class CommonAreaCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    category: str = "general"
    description: str = ""
    capacity: int = Field(gt=0)
    hourly_rate: Decimal = Field(ge=0, default=Decimal("0"))
    has_cost: bool = False
    requires_approval: bool = False
    rules: str = ""
    is_active: bool = True
    is_bookable: bool = True
    min_duration_minutes: int = Field(ge=15, default=60)
    max_duration_minutes: int = Field(ge=15, default=240)
    min_advance_minutes: int = Field(ge=0, default=0)
    max_advance_days: int = Field(ge=1, default=90)
    cleanup_buffer_minutes: int = Field(ge=0, default=0)
    max_active_per_resident: int = Field(ge=1, default=3)
    required_documents: list[str] = Field(default_factory=list)


class CommonAreaUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    category: str | None = None
    description: str | None = None
    capacity: int | None = Field(default=None, gt=0)
    hourly_rate: Decimal | None = Field(default=None, ge=0)
    has_cost: bool | None = None
    requires_approval: bool | None = None
    rules: str | None = None
    is_active: bool | None = None
    is_bookable: bool | None = None
    min_duration_minutes: int | None = Field(default=None, ge=15)
    max_duration_minutes: int | None = Field(default=None, ge=15)
    min_advance_minutes: int | None = Field(default=None, ge=0)
    max_advance_days: int | None = Field(default=None, ge=1)
    cleanup_buffer_minutes: int | None = Field(default=None, ge=0)
    max_active_per_resident: int | None = Field(default=None, ge=1)
    required_documents: list[str] | None = None


class ScheduleItem(BaseModel):
    weekday: int = Field(ge=0, le=6)
    open_time: str | None = None  # HH:MM
    close_time: str | None = None
    is_closed: bool = False


class BlackoutCreate(BaseModel):
    reason_type: str = Field(pattern="^(maintenance|holiday|block)$")
    starts_at: datetime
    ends_at: datetime
    note: str = ""


class BlackoutOut(ORMModel):
    id: UUID
    common_area_id: UUID
    reason_type: str
    starts_at: datetime
    ends_at: datetime
    note: str


class ImageItem(BaseModel):
    url: str = Field(min_length=4, max_length=500)
    sort_order: int = 0


class ImageOut(ORMModel):
    id: UUID
    url: str
    sort_order: int


class ScheduleOut(ORMModel):
    id: UUID
    weekday: int
    open_time: str | None = None
    close_time: str | None = None
    is_closed: bool


class SpecialHoursCreate(BaseModel):
    on_date: date
    open_time: str | None = None  # HH:MM
    close_time: str | None = None
    is_closed: bool = False
    note: str = ""


class SpecialHoursOut(ORMModel):
    id: UUID
    common_area_id: UUID
    on_date: date
    open_time: str | None = None
    close_time: str | None = None
    is_closed: bool
    note: str


class CommonAreaDetailOut(CommonAreaOut):
    schedules: list[ScheduleOut] = Field(default_factory=list)
    blackouts: list[BlackoutOut] = Field(default_factory=list)
    images: list[ImageOut] = Field(default_factory=list)
    special_hours: list[SpecialHoursOut] = Field(default_factory=list)


class ReservationCreate(BaseModel):
    resident_id: UUID
    common_area_id: UUID
    starts_at: datetime
    ends_at: datetime


class ReservationReschedule(BaseModel):
    starts_at: datetime
    ends_at: datetime


class ReservationOut(ORMModel):
    id: UUID
    resident_id: UUID
    common_area_id: UUID
    starts_at: datetime
    ends_at: datetime
    status: ReservationStatus
    amount: Decimal
    payment_reference: str | None
    reject_reason: str | None = None
    receipt_number: str | None = None
    access_code: str | None = None


class ReservationAdminOut(ReservationOut):
    resident_name: str
    common_area_name: str


class ReservationRejectRequest(BaseModel):
    reason: str = ""


class ReservationPayRequest(BaseModel):
    method: str = "PSE"


class ReservationAccessPassOut(BaseModel):
    reservation_id: UUID
    code: str
    kind: str
    pin: str | None = None
    provider: str
    expires_at: datetime
    status: str


class ReservationReceiptOut(BaseModel):
    receipt_number: str
    reservation_id: UUID
    zone_name: str
    resident_name: str
    starts_at: datetime
    ends_at: datetime
    amount: Decimal
    status: str
    issued_at: datetime


class MaintenanceJobOut(BaseModel):
    completed: int
    expired: int


class AvailabilitySlotOut(BaseModel):
    starts_at: datetime
    ends_at: datetime
    amount: Decimal


class AvailabilityOut(BaseModel):
    common_area_id: UUID
    date: date
    duration_minutes: int
    slots: list[AvailabilitySlotOut]


class InvoiceOut(ORMModel):
    id: UUID
    unit_id: UUID
    invoice_number: str
    issue_date: date
    due_date: date
    period: str
    subtotal: Decimal
    late_fee: Decimal
    discount: Decimal
    total: Decimal
    paid_amount: Decimal
    status: InvoiceStatus


class GenerateInvoicesRequest(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    issue_date: date
    due_date: date


class PaymentCreate(BaseModel):
    invoice_id: UUID
    amount: Decimal = Field(gt=0)
    method: str
    gateway_reference: str


class PaymentOut(ORMModel):
    id: UUID
    invoice_id: UUID
    amount: Decimal
    method: str
    gateway_reference: str
    paid_at: datetime
    status: str


class PaymentAgreementCreate(BaseModel):
    unit_id: UUID
    total_amount: Decimal = Field(gt=0)
    installments: int = Field(gt=0)
    start_date: date


class VisitorCreate(BaseModel):
    resident_id: UUID
    visitor_name: str
    document_number: str | None = None
    vehicle_plate: str | None = None
    valid_from: datetime
    valid_until: datetime


class VisitorOut(ORMModel):
    id: UUID
    resident_id: UUID
    visitor_name: str
    document_number: str | None
    vehicle_plate: str | None
    valid_from: datetime
    valid_until: datetime
    qr_code: str
    status: VisitorStatus


class AnnouncementCreate(BaseModel):
    title: str
    body: str
    category: str = "general"
    expires_at: datetime | None = None


class AnnouncementOut(ORMModel):
    id: UUID
    title: str
    body: str
    category: str
    published_at: datetime
    expires_at: datetime | None


class DashboardOut(BaseModel):
    total_units: int
    total_residents: int
    monthly_billed: Decimal
    collected: Decimal
    overdue: Decimal
    delinquent_units: int
    active_reservations: int
    monthly_collection_rate: float


class PeaceClearanceOut(ORMModel):
    id: UUID
    unit_id: UUID
    certificate_number: str
    issued_at: datetime
    valid_until: date
    is_valid: bool


class AccountingReportOut(BaseModel):
    income: Decimal
    expenses: Decimal
    net_result: Decimal
    receivables: Decimal
    entries: list[dict]
