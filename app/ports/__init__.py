"""Integration ports for Phase 4 — swap adapters without changing domain services."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class PaymentChargeRequest:
    reservation_id: UUID
    resident_id: UUID
    amount: Decimal
    description: str
    method: str = "PSE"


@dataclass(frozen=True)
class PaymentChargeResult:
    success: bool
    reference: str
    provider: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaymentRefundRequest:
    reservation_id: UUID
    payment_reference: str
    amount: Decimal
    reason: str = ""


@dataclass(frozen=True)
class NotificationMessage:
    channel: str  # email | push | whatsapp | sms
    template: str
    recipient: str
    subject: str
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AccessPassRequest:
    reservation_id: UUID
    resident_id: UUID
    zone_name: str
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True)
class AccessPass:
    code: str
    kind: str  # qr | pin | rfid | biometric_token
    provider: str
    expires_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StoredObject:
    url: str
    key: str
    provider: str


@dataclass(frozen=True)
class CalendarEvent:
    uid: str
    summary: str
    description: str
    starts_at: datetime
    ends_at: datetime
    location: str = ""


class PaymentPort(Protocol):
    def charge(self, request: PaymentChargeRequest) -> PaymentChargeResult: ...

    def refund(self, request: PaymentRefundRequest) -> PaymentChargeResult: ...


class NotificationPort(Protocol):
    def send(self, message: NotificationMessage) -> str:
        """Return a delivery id (stub may return logged id)."""


class AccessControlPort(Protocol):
    def issue_pass(self, request: AccessPassRequest) -> AccessPass: ...

    def revoke_pass(self, code: str, reason: str = "") -> None: ...


class ImageStoragePort(Protocol):
    def store(self, *, filename: str, content_type: str, data: bytes) -> StoredObject: ...


class CalendarExportPort(Protocol):
    def to_ical(self, events: list[CalendarEvent]) -> str: ...
