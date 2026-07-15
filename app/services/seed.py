from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import (
    AccountingEntry,
    AdminUser,
    Announcement,
    CommonArea,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    Payment,
    PaymentStatus,
    Resident,
    ResidentUser,
    ResidentialComplex,
    Tower,
    Unit,
    Vehicle,
)
from app.core.security import hash_password


def seed_database(db: Session) -> None:
    existing = db.scalar(select(ResidentialComplex).limit(1))
    if existing:
        # Backfill admin.complex_id on DBs seeded before Phase 0.
        for admin in db.scalars(select(AdminUser).where(AdminUser.complex_id.is_(None))).all():
            admin.complex_id = existing.id
        db.commit()
        return

    complex_ = ResidentialComplex(
        name="Conjunto Reserva del Sol",
        nit="900123456-7",
        address="Calle 123 #45-67",
        city="Bogota",
    )
    tower_a = Tower(name="Torre A", complex=complex_)
    tower_b = Tower(name="Torre B", complex=complex_)

    units = [
        Unit(tower=tower_a, number="101", coefficient=Decimal("1.2500"), administration_fee=Decimal("420000"), parking_slot="A-12"),
        Unit(tower=tower_a, number="203", coefficient=Decimal("1.5000"), administration_fee=Decimal("490000"), parking_slot="A-34"),
        Unit(tower=tower_b, number="504", coefficient=Decimal("1.9000"), administration_fee=Decimal("610000"), parking_slot="B-18"),
    ]
    db.add_all([complex_, tower_a, tower_b, *units])
    db.flush()

    resident_users = [
        ResidentUser(email="ana@example.com", full_name="Ana Maria Ruiz", password_hash=hash_password("residente123")),
        ResidentUser(email="carlos@example.com", full_name="Carlos Gomez", password_hash=hash_password("residente123")),
    ]
    admin_user = AdminUser(
        email="admin@conjunapp.com",
        full_name="Laura Administradora",
        password_hash=hash_password("admin123"),
        position="Administradora principal",
        is_super_admin=True,
        complex_id=complex_.id,
    )
    residents = [
        Resident(user=resident_users[0], unit=units[0], document_number="52123456", phone="+573001112233", resident_type="owner", is_owner=True),
        Resident(user=resident_users[1], unit=units[1], document_number="80111222", phone="+573004445566", resident_type="tenant", is_owner=False, is_delinquent=True),
    ]
    vehicles = [
        Vehicle(resident=residents[0], plate="ABC123", kind="car"),
        Vehicle(resident=residents[1], plate="XYZ987", kind="motorcycle"),
    ]
    areas = [
        CommonArea(complex_id=complex_.id, name="Salon social", capacity=80, hourly_rate=Decimal("90000"), requires_approval=True, rules="Maximo hasta las 11 p.m."),
        CommonArea(complex_id=complex_.id, name="Cancha multiple", capacity=20, hourly_rate=Decimal("25000"), rules="Uso con zapatos deportivos."),
        CommonArea(complex_id=complex_.id, name="BBQ", capacity=25, hourly_rate=Decimal("45000"), requires_approval=True, rules="Entrega limpia obligatoria."),
        CommonArea(complex_id=complex_.id, name="Piscina", capacity=30, hourly_rate=Decimal("0"), rules="Ingreso con gorro."),
        CommonArea(complex_id=complex_.id, name="Coworking", capacity=12, hourly_rate=Decimal("15000"), rules="Reserva maxima de 4 horas."),
    ]
    db.add_all([*resident_users, admin_user, *residents, *vehicles, *areas])
    db.flush()

    today = date.today()
    invoices = [
        Invoice(
            unit=units[0],
            invoice_number="FAC-2026-0001",
            issue_date=today.replace(day=1),
            due_date=today.replace(day=15),
            period=today.strftime("%Y-%m"),
            subtotal=Decimal("420000"),
            total=Decimal("420000"),
            paid_amount=Decimal("420000"),
            status=InvoiceStatus.paid,
        ),
        Invoice(
            unit=units[1],
            invoice_number="FAC-2026-0002",
            issue_date=today.replace(day=1),
            due_date=today.replace(day=15),
            period=today.strftime("%Y-%m"),
            subtotal=Decimal("490000"),
            late_fee=Decimal("35000"),
            total=Decimal("525000"),
            paid_amount=Decimal("0"),
            status=InvoiceStatus.overdue,
        ),
    ]
    db.add_all(invoices)
    db.flush()
    db.add_all(
        [
            InvoiceItem(invoice=invoices[0], description="Cuota de administracion", amount=Decimal("420000")),
            InvoiceItem(invoice=invoices[1], description="Cuota de administracion", amount=Decimal("490000")),
            InvoiceItem(invoice=invoices[1], description="Intereses de mora", amount=Decimal("35000")),
            Payment(invoice_id=invoices[0].id, amount=Decimal("420000"), method="PSE", gateway_reference="PSE-SEED-001", status=PaymentStatus.approved),
            Announcement(title="Mantenimiento de piscina", body="La piscina estara cerrada el martes por mantenimiento preventivo.", category="mantenimiento"),
            Announcement(title="Asamblea ordinaria", body="Recuerda revisar el estado financiero antes de la asamblea.", category="asamblea"),
            AccountingEntry(entry_date=today, account_code="130505", account_name="Cuentas por cobrar", description="Facturacion mensual", debit=Decimal("945000"), credit=Decimal("0")),
            AccountingEntry(entry_date=today, account_code="416005", account_name="Ingresos administracion", description="Facturacion mensual", debit=Decimal("0"), credit=Decimal("910000")),
            AccountingEntry(entry_date=today, account_code="421005", account_name="Intereses de mora", description="Intereses de mora", debit=Decimal("0"), credit=Decimal("35000")),
            AccountingEntry(entry_date=today, account_code="111005", account_name="Bancos", description="Pago administracion", debit=Decimal("420000"), credit=Decimal("0")),
        ]
    )
    db.commit()
