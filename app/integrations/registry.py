from __future__ import annotations

from functools import lru_cache

from app.adapters.access_local import LocalAccessControlAdapter
from app.adapters.calendar_stub import StubICalCalendarAdapter
from app.adapters.notifications_logging import LoggingNotificationAdapter
from app.adapters.payment_stub import StubPaymentAdapter
from app.adapters.storage_url import StubObjectStorageAdapter, UrlOnlyImageStorageAdapter
from app.core.config import get_settings
from app.ports import (
    AccessControlPort,
    CalendarExportPort,
    ImageStoragePort,
    NotificationPort,
    PaymentPort,
)


@lru_cache
def get_payment_port() -> PaymentPort:
    settings = get_settings()
    if settings.payment_adapter == "stub":
        return StubPaymentAdapter()
    return StubPaymentAdapter()


@lru_cache
def get_notification_port() -> NotificationPort:
    settings = get_settings()
    if settings.notification_adapter == "logging":
        return LoggingNotificationAdapter()
    return LoggingNotificationAdapter()


@lru_cache
def get_access_port() -> AccessControlPort:
    settings = get_settings()
    if settings.access_adapter == "local":
        return LocalAccessControlAdapter()
    return LocalAccessControlAdapter()


@lru_cache
def get_image_storage_port() -> ImageStoragePort:
    settings = get_settings()
    if settings.image_storage_adapter == "stub":
        return StubObjectStorageAdapter()
    return UrlOnlyImageStorageAdapter()


@lru_cache
def get_calendar_port() -> CalendarExportPort:
    return StubICalCalendarAdapter()
