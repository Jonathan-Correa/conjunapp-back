"""Wire Phase 4 ports into the application."""

from app.integrations.registry import (
    get_access_port,
    get_calendar_port,
    get_image_storage_port,
    get_notification_port,
    get_payment_port,
)

__all__ = [
    "get_access_port",
    "get_calendar_port",
    "get_image_storage_port",
    "get_notification_port",
    "get_payment_port",
]
