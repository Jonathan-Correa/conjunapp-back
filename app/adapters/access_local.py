from __future__ import annotations

import logging
from uuid import uuid4

from app.ports import AccessControlPort, AccessPass, AccessPassRequest

logger = logging.getLogger("conjunapp.adapters.access")


class LocalAccessControlAdapter:
    """Issues local QR / PIN codes without hardware integrations."""

    provider = "local"

    def issue_pass(self, request: AccessPassRequest) -> AccessPass:
        code = f"ZONA-{uuid4().hex[:10].upper()}"
        pin = f"{int(uuid4().int % 1000000):06d}"
        logger.info(
            "access.issue reservation=%s zone=%s code=%s pin=%s",
            request.reservation_id,
            request.zone_name,
            code,
            pin,
        )
        return AccessPass(
            code=code,
            kind="qr",
            provider=self.provider,
            expires_at=request.ends_at,
            payload={"pin": pin, "zone_name": request.zone_name, "resident_id": str(request.resident_id)},
        )

    def revoke_pass(self, code: str, reason: str = "") -> None:
        logger.info("access.revoke code=%s reason=%s", code, reason)


_: AccessControlPort = LocalAccessControlAdapter()
