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


class CommonAreaOut(ORMModel):
    id: UUID
    name: str
    capacity: int
    hourly_rate: Decimal
    requires_approval: bool
    rules: str
    is_active: bool


class ReservationCreate(BaseModel):
    resident_id: UUID
    common_area_id: UUID
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
