from __future__ import annotations

import logging
from uuid import uuid4

from app.ports import NotificationMessage, NotificationPort

logger = logging.getLogger("conjunapp.adapters.notifications")


class LoggingNotificationAdapter:
    """Logs notifications instead of sending email/push/WhatsApp."""

    def send(self, message: NotificationMessage) -> str:
        delivery_id = f"NOTIF-{uuid4().hex[:12].upper()}"
        logger.info(
            "notification.send id=%s channel=%s template=%s to=%s subject=%s body=%s meta=%s",
            delivery_id,
            message.channel,
            message.template,
            message.recipient,
            message.subject,
            message.body,
            message.metadata,
        )
        return delivery_id


_: NotificationPort = LoggingNotificationAdapter()
