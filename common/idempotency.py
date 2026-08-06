import hashlib
import json

from django.db import transaction

from housekeeping.models import OfflineMutationReceipt


class IdempotencyError(Exception):
    def __init__(self, code, message, *, receipt=None):
        self.code = code
        self.message = message
        self.receipt = receipt
        super().__init__(message)


def canonical_payload_hash(payload):
    encoded = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@transaction.atomic
def execute_idempotent(
    *,
    user,
    task,
    idempotency_key,
    operation,
    payload,
    base_version,
    mutation,
    client_mutation_id="",
    depends_on=None,
):
    key = str(idempotency_key or "").strip()
    if not key:
        raise IdempotencyError(
            "IDEMPOTENCY_KEY_REQUIRED",
            "Thay đổi cần có mã chống gửi trùng.",
        )
    payload_hash = canonical_payload_hash(payload)
    receipt = OfflineMutationReceipt.objects.select_for_update().filter(
        user=user,
        idempotency_key=key,
    ).first()
    if receipt is not None:
        if receipt.payload_hash != payload_hash or receipt.operation != operation:
            raise IdempotencyError(
                "IDEMPOTENCY_KEY_REUSED",
                "Idempotency-Key đã được dùng cho payload hoặc thao tác khác.",
                receipt=receipt,
            )
        if receipt.status == OfflineMutationReceipt.Status.SUCCEEDED:
            return receipt.response_payload, True, receipt
        if receipt.status == OfflineMutationReceipt.Status.CONFLICT:
            raise IdempotencyError(
                "OFFLINE_SYNC_CONFLICT",
                "Thay đổi đang có xung đột.",
                receipt=receipt,
            )
        if receipt.status == OfflineMutationReceipt.Status.FAILED:
            raise IdempotencyError(
                receipt.error_code or "SYSTEM_ERROR",
                "Thay đổi trước đó đã thất bại.",
                receipt=receipt,
            )
        if receipt.status == OfflineMutationReceipt.Status.DISCARDED:
            raise IdempotencyError(
                "IDEMPOTENCY_KEY_REUSED",
                "Thay đổi trên thiết bị đã bị bỏ; hãy dùng mã chống gửi trùng mới nếu cần gửi lại.",
                receipt=receipt,
            )
        raise IdempotencyError(
            "MUTATION_IN_PROGRESS",
            "Thay đổi đang được xử lý.",
            receipt=receipt,
        )

    receipt = OfflineMutationReceipt.objects.create(
        user=user,
        task=task,
        idempotency_key=key,
        client_mutation_id=str(client_mutation_id or "")[:80],
        operation=operation,
        payload_hash=payload_hash,
        request_payload=payload or {},
        base_version=base_version,
        depends_on=list(depends_on or []),
    )
    response_payload, result_version = mutation()
    receipt.response_payload = response_payload or {}
    receipt.result_version = result_version
    receipt.status = OfflineMutationReceipt.Status.SUCCEEDED
    receipt.save(update_fields=["response_payload", "result_version", "status", "updated_at"])
    return receipt.response_payload, False, receipt
