from __future__ import annotations

import logging
from uuid import uuid4

from app.ports import PaymentChargeRequest, PaymentChargeResult, PaymentPort, PaymentRefundRequest

logger = logging.getLogger("conjunapp.adapters.payment")


class StubPaymentAdapter:
    """Simulates PSE/card gateway — always succeeds in development."""

    provider = "stub-pse"

    def charge(self, request: PaymentChargeRequest) -> PaymentChargeResult:
        reference = f"PAY-{request.method.upper()}-{uuid4().hex[:10].upper()}"
        logger.info(
            "payment.charge reservation=%s amount=%s method=%s ref=%s",
            request.reservation_id,
            request.amount,
            request.method,
            reference,
        )
        return PaymentChargeResult(
            success=True,
            reference=reference,
            provider=self.provider,
            raw={"method": request.method, "description": request.description},
        )

    def refund(self, request: PaymentRefundRequest) -> PaymentChargeResult:
        reference = f"RFND-{uuid4().hex[:10].upper()}"
        logger.info(
            "payment.refund reservation=%s amount=%s original=%s ref=%s reason=%s",
            request.reservation_id,
            request.amount,
            request.payment_reference,
            reference,
            request.reason,
        )
        return PaymentChargeResult(
            success=True,
            reference=reference,
            provider=self.provider,
            raw={"original": request.payment_reference, "reason": request.reason},
        )


# Explicit Protocol conformance
_: PaymentPort = StubPaymentAdapter()
