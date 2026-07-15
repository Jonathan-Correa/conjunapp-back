from __future__ import annotations

import logging
from uuid import uuid4

from app.ports import ImageStoragePort, StoredObject
from app.services.reservations import ReservationError

logger = logging.getLogger("conjunapp.adapters.storage")


class UrlOnlyImageStorageAdapter:
    """Phase 4 placeholder: binary upload not wired; admin keeps using absolute URLs."""

    provider = "url-only"

    def store(self, *, filename: str, content_type: str, data: bytes) -> StoredObject:
        logger.warning(
            "storage.store rejected filename=%s content_type=%s bytes=%s (upload not enabled)",
            filename,
            content_type,
            len(data),
        )
        raise ReservationError(
            501,
            "Carga binaria de imágenes no está habilitada. Usa URLs absolutas en la configuración de la zona.",
        )


class StubObjectStorageAdapter:
    """Returns a fake CDN URL so clients can exercise the port without S3."""

    provider = "stub-object"

    def store(self, *, filename: str, content_type: str, data: bytes) -> StoredObject:
        key = f"zones/{uuid4().hex}/{filename}"
        url = f"https://cdn.example.local/{key}"
        logger.info("storage.store stub key=%s content_type=%s bytes=%s", key, content_type, len(data))
        return StoredObject(url=url, key=key, provider=self.provider)


_: ImageStoragePort = UrlOnlyImageStorageAdapter()
