from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from common.idempotency import IdempotencyError, canonical_payload_hash, execute_idempotent
from .models import HousekeepingTask, OfflineMutationReceipt, TaskChecklistItem
from .selectors import task_queryset_for_user
from .services import (
    HousekeepingError,
    accept_task,
    complete_task,
    create_supply_request,
    pause_task,
    report_issue,
    resume_task,
    start_task,
    update_checklist_item,
    update_task_note,
)


SUPPORTED_OPERATIONS = {
    "ACCEPT",
    "START",
    "UPDATE_CHECKLIST_ITEM",
    "UPDATE_TASK_NOTE",
    "PAUSE",
    "RESUME",
    "CREATE_SUPPLY_REQUEST",
    "REPORT_ISSUE",
    "COMPLETE",
}


def _task_result(task):
    return {
        "taskId": str(task.id),
        "status": task.status,
        "roomStatus": task.room.status,
        "progressPercent": task.progress_percent,
        "priority": task.priority,
        "version": task.version,
    }


def _task_reference(user, task_id):
    try:
        return task_queryset_for_user(user).get(pk=task_id)
    except (HousekeepingTask.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy công việc.", status=404) from None


def _normalize_mutation(raw, index):
    if not isinstance(raw, dict):
        raise HousekeepingError("SYSTEM_ERROR", f"Thay đổi thứ {index + 1} không hợp lệ.")
    client_mutation_id = str(raw.get("clientMutationId") or "").strip()
    idempotency_key = str(raw.get("idempotencyKey") or client_mutation_id).strip()
    if not client_mutation_id or len(client_mutation_id) > 80:
        raise HousekeepingError("SYSTEM_ERROR", "Mã thay đổi trên thiết bị là bắt buộc và tối đa 80 ký tự.")
    if not idempotency_key or len(idempotency_key) > 80:
        raise HousekeepingError(
            "IDEMPOTENCY_KEY_REQUIRED",
            "Mã chống gửi trùng là bắt buộc và tối đa 80 ký tự.",
        )
    operation = str(raw.get("operation") or "").strip().upper()
    if operation not in SUPPORTED_OPERATIONS:
        raise HousekeepingError(
            "TASK_INVALID_STATUS",
            f"Thao tác ngoại tuyến không được hỗ trợ: {operation or '(trống)' }.",
        )
    try:
        base_version = int(raw.get("baseVersion"))
    except (TypeError, ValueError):
        raise HousekeepingError("TASK_VERSION_CONFLICT", "Thay đổi ngoại tuyến cần có phiên bản dữ liệu gốc.", status=409) from None
    if base_version < 1:
        raise HousekeepingError("TASK_VERSION_CONFLICT", "Phiên bản dữ liệu gốc không hợp lệ.", status=409)
    payload = raw.get("payload") or {}
    if not isinstance(payload, dict):
        raise HousekeepingError("SYSTEM_ERROR", "Nội dung thay đổi phải là một đối tượng dữ liệu.")
    if payload.get("version") is not None and payload.get("version") != base_version:
        raise HousekeepingError(
            "TASK_VERSION_CONFLICT",
            "Phiên bản trong nội dung thay đổi không khớp phiên bản dữ liệu gốc.",
            status=409,
        )
    depends_on = raw.get("dependsOn") or []
    if not isinstance(depends_on, list) or any(not isinstance(value, str) for value in depends_on):
        raise HousekeepingError("SYSTEM_ERROR", "Danh sách thay đổi phụ thuộc không hợp lệ.")
    return {
        "clientMutationId": client_mutation_id,
        "idempotencyKey": idempotency_key,
        "operation": operation,
        "taskId": str(raw.get("taskId") or ""),
        "baseVersion": base_version,
        "payload": {**payload, "version": base_version},
        "baseSnapshot": raw.get("baseSnapshot") if isinstance(raw.get("baseSnapshot"), dict) else {},
        "dependsOn": list(dict.fromkeys(depends_on)),
        "originalIndex": index,
    }


def _ordered_mutations(raw_mutations):
    if not isinstance(raw_mutations, list) or not raw_mutations:
        raise HousekeepingError("SYSTEM_ERROR", "Mỗi đợt đồng bộ phải có ít nhất một thay đổi.")
    if len(raw_mutations) > 100:
        raise HousekeepingError("SYSTEM_ERROR", "Mỗi đợt đồng bộ chỉ được tối đa 100 thay đổi.")
    mutations = [_normalize_mutation(raw, index) for index, raw in enumerate(raw_mutations)]
    by_id = {}
    for mutation in mutations:
        mutation_id = mutation["clientMutationId"]
        if mutation_id in by_id:
            raise HousekeepingError("IDEMPOTENCY_KEY_REUSED", "Mã thay đổi bị lặp trong đợt đồng bộ.", status=409)
        by_id[mutation_id] = mutation
    incoming = {mutation_id: 0 for mutation_id in by_id}
    children = defaultdict(list)
    for mutation in mutations:
        for dependency in mutation["dependsOn"]:
            if dependency in by_id:
                incoming[mutation["clientMutationId"]] += 1
                children[dependency].append(mutation["clientMutationId"])
    ready = sorted(
        (mutation for mutation in mutations if incoming[mutation["clientMutationId"]] == 0),
        key=lambda mutation: mutation["originalIndex"],
    )
    ordered = []
    while ready:
        mutation = ready.pop(0)
        ordered.append(mutation)
        for child_id in children[mutation["clientMutationId"]]:
            incoming[child_id] -= 1
            if incoming[child_id] == 0:
                ready.append(by_id[child_id])
                ready.sort(key=lambda item: item["originalIndex"])
    if len(ordered) != len(mutations):
        raise HousekeepingError("SYSTEM_ERROR", "Các thay đổi phụ thuộc lẫn nhau nên không thể đồng bộ.")
    return ordered


def _server_snapshot(user, task_id, payload):
    try:
        task = task_queryset_for_user(user).get(pk=task_id)
    except (HousekeepingTask.DoesNotExist, ValueError):
        return None
    snapshot = {
        "taskId": str(task.id),
        "version": task.version,
        "status": task.status,
        "priority": task.priority,
        "progressPercent": task.progress_percent,
        "note": task.note,
        "updatedAt": task.updated_at.isoformat(),
    }
    item_id = payload.get("itemId") or payload.get("checklistItemId")
    if item_id:
        try:
            item = task.checklist_items.get(pk=item_id)
        except (TaskChecklistItem.DoesNotExist, ValueError):
            pass
        else:
            snapshot["checklistItem"] = {
                "id": str(item.id),
                "status": item.status,
                "value": item.value,
                "note": item.note,
                "itemVersion": item.update_version,
                "completedAt": item.completed_at.isoformat() if item.completed_at else None,
            }
    return snapshot


def _dispatch(user, mutation, context):
    task_id = mutation["taskId"]
    payload = mutation["payload"]
    version = mutation["baseVersion"]
    operation = mutation["operation"]
    operation_context = {**context, "idempotency_key": mutation["idempotencyKey"]}
    if operation == "ACCEPT":
        task = accept_task(user, task_id, version, operation_context)
        return _task_result(task), task.version
    if operation == "START":
        task = start_task(user, task_id, version, operation_context, payload.get("roomVerification") or payload)
        return _task_result(task), task.version
    if operation == "UPDATE_CHECKLIST_ITEM":
        item_id = payload.get("itemId") or payload.get("checklistItemId")
        item, task = update_checklist_item(user, task_id, item_id, payload, operation_context)
        return {
            "taskId": str(task.id),
            "itemId": str(item.id),
            "status": item.status,
            "value": item.value,
            "itemVersion": item.update_version,
            "progressPercent": task.progress_percent,
            "taskVersion": task.version,
        }, task.version
    if operation == "UPDATE_TASK_NOTE":
        task = update_task_note(user, task_id, version, payload.get("note"), operation_context)
        return _task_result(task), task.version
    if operation == "PAUSE":
        task = pause_task(
            user,
            task_id,
            version,
            payload.get("reasonCode"),
            payload.get("note"),
            operation_context,
        )
        return _task_result(task), task.version
    if operation == "RESUME":
        task = resume_task(user, task_id, version, operation_context)
        return _task_result(task), task.version
    if operation == "CREATE_SUPPLY_REQUEST":
        payload.setdefault("clientRequestId", mutation["clientMutationId"])
        supply, created = create_supply_request(user, task_id, payload, operation_context)
        task = HousekeepingTask.objects.select_related("room").get(pk=task_id)
        return {
            "taskId": str(task.id),
            "requestId": str(supply.id),
            "status": supply.status,
            "created": created,
            "taskVersion": task.version,
        }, task.version
    if operation == "REPORT_ISSUE":
        payload.setdefault("clientRequestId", mutation["clientMutationId"])
        issue, created = report_issue(user, task_id, payload, operation_context)
        task = HousekeepingTask.objects.select_related("room").get(pk=task_id)
        return {
            "taskId": str(task.id),
            "issueId": str(issue.id),
            "status": issue.status,
            "created": created,
            "taskVersion": task.version,
        }, task.version
    if operation == "COMPLETE":
        task = complete_task(
            user,
            task_id,
            version,
            payload.get("confirmFinalInspection") is True,
            payload.get("finalNote"),
            operation_context,
        )
        return _task_result(task), task.version
    raise HousekeepingError("TASK_INVALID_STATUS", "Thao tác ngoại tuyến không được hỗ trợ.")


def _store_error_receipt(user, task, mutation, error):
    is_conflict = isinstance(error, HousekeepingError) and error.code == "TASK_VERSION_CONFLICT"
    conflict_payload = {}
    if is_conflict:
        conflict_payload = {
            "baseVersion": mutation["baseVersion"],
            "baseSnapshot": mutation["baseSnapshot"],
            "localOperation": {
                "operation": mutation["operation"],
                "payload": mutation["payload"],
            },
            "serverSnapshot": _server_snapshot(user, mutation["taskId"], mutation["payload"]),
            "resolutionOptions": ["DISCARD_LOCAL", "RETRY_WITH_SERVER_VERSION"],
        }
    with transaction.atomic():
        receipt, _created = OfflineMutationReceipt.objects.get_or_create(
            user=user,
            idempotency_key=mutation["idempotencyKey"],
            defaults={
                "task": task,
                "client_mutation_id": mutation["clientMutationId"],
                "operation": mutation["operation"],
                "payload_hash": canonical_payload_hash(mutation["payload"]),
                "request_payload": mutation["payload"],
                "base_version": mutation["baseVersion"],
                "status": (
                    OfflineMutationReceipt.Status.CONFLICT
                    if is_conflict
                    else OfflineMutationReceipt.Status.FAILED
                ),
                "error_code": error.code,
                "depends_on": mutation["dependsOn"],
                "conflict_payload": conflict_payload,
            },
        )
    return receipt


def _receipt_result(receipt, mutation, *, replayed=False):
    status_map = {
        OfflineMutationReceipt.Status.SUCCEEDED: "SYNCED",
        OfflineMutationReceipt.Status.CONFLICT: "CONFLICT",
        OfflineMutationReceipt.Status.FAILED: "FAILED",
        OfflineMutationReceipt.Status.DISCARDED: "DISCARDED",
        OfflineMutationReceipt.Status.RECEIVED: "PENDING",
    }
    return {
        "clientMutationId": mutation["clientMutationId"],
        "idempotencyKey": mutation["idempotencyKey"],
        "receiptId": str(receipt.id),
        "operation": mutation["operation"],
        "status": status_map[receipt.status],
        "replayed": replayed,
        "result": receipt.response_payload if receipt.status == OfflineMutationReceipt.Status.SUCCEEDED else None,
        "error": (
            {"code": receipt.error_code, "message": "Thay đổi ngoại tuyến không thể đồng bộ."}
            if receipt.error_code
            else None
        ),
        "conflict": receipt.conflict_payload if receipt.status == OfflineMutationReceipt.Status.CONFLICT else None,
    }


def _dependency_succeeded(user, dependency_id, batch_results):
    if dependency_id in batch_results:
        return batch_results[dependency_id]["status"] == "SYNCED"
    return OfflineMutationReceipt.objects.filter(
        user=user,
        client_mutation_id=dependency_id,
        status=OfflineMutationReceipt.Status.SUCCEEDED,
    ).exists()


def process_sync_batch(user, raw_mutations, context):
    ordered = _ordered_mutations(raw_mutations)
    results_by_id = {}
    for mutation in ordered:
        missing_dependencies = [
            dependency
            for dependency in mutation["dependsOn"]
            if not _dependency_succeeded(user, dependency, results_by_id)
        ]
        if missing_dependencies:
            results_by_id[mutation["clientMutationId"]] = {
                "clientMutationId": mutation["clientMutationId"],
                "idempotencyKey": mutation["idempotencyKey"],
                "receiptId": None,
                "operation": mutation["operation"],
                "status": "BLOCKED",
                "replayed": False,
                "result": None,
                "error": {
                    "code": "DEPENDENCY_NOT_SYNCED",
                    "message": "Thay đổi phụ thuộc chưa được đồng bộ thành công.",
                    "dependencyIds": missing_dependencies,
                },
                "conflict": None,
            }
            continue
        try:
            task = _task_reference(user, mutation["taskId"])
        except HousekeepingError as error:
            receipt = _store_error_receipt(user, None, mutation, error)
            result = _receipt_result(receipt, mutation)
            result["error"] = {"code": error.code, "message": error.message, "details": error.details}
            results_by_id[mutation["clientMutationId"]] = result
            continue
        try:
            response, replayed, receipt = execute_idempotent(
                user=user,
                task=task,
                idempotency_key=mutation["idempotencyKey"],
                operation=mutation["operation"],
                payload=mutation["payload"],
                base_version=mutation["baseVersion"],
                mutation=lambda mutation=mutation: _dispatch(user, mutation, context),
                client_mutation_id=mutation["clientMutationId"],
                depends_on=mutation["dependsOn"],
            )
            if not replayed:
                receipt.response_payload = response
            result = _receipt_result(receipt, mutation, replayed=replayed)
        except HousekeepingError as error:
            receipt = _store_error_receipt(user, task, mutation, error)
            result = _receipt_result(receipt, mutation)
            result["error"] = {"code": error.code, "message": error.message, "details": error.details}
        except IdempotencyError as error:
            if error.receipt:
                result = _receipt_result(error.receipt, mutation, replayed=True)
                result["error"] = {"code": error.code, "message": error.message}
            else:
                result = {
                    "clientMutationId": mutation["clientMutationId"],
                    "idempotencyKey": mutation["idempotencyKey"],
                    "receiptId": None,
                    "operation": mutation["operation"],
                    "status": "FAILED",
                    "replayed": False,
                    "result": None,
                    "error": {"code": error.code, "message": error.message},
                    "conflict": None,
                }
        results_by_id[mutation["clientMutationId"]] = result
    results = sorted(results_by_id.values(), key=lambda item: next(
        mutation["originalIndex"] for mutation in ordered if mutation["clientMutationId"] == item["clientMutationId"]
    ))
    return {
        "results": results,
        "summary": {
            "total": len(results),
            "synced": sum(item["status"] == "SYNCED" for item in results),
            "blocked": sum(item["status"] == "BLOCKED" for item in results),
            "failed": sum(item["status"] == "FAILED" for item in results),
            "conflicts": sum(item["status"] == "CONFLICT" for item in results),
        },
    }


def conflict_data(receipt):
    return {
        "receiptId": str(receipt.id),
        "clientMutationId": receipt.client_mutation_id,
        "taskId": str(receipt.task_id) if receipt.task_id else None,
        "operation": receipt.operation,
        "status": receipt.status,
        "errorCode": receipt.error_code,
        "conflict": receipt.conflict_payload,
        "createdAt": receipt.created_at.isoformat(),
        "resolvedAt": receipt.resolved_at.isoformat() if receipt.resolved_at else None,
        "resolution": receipt.resolution,
    }


@transaction.atomic
def discard_conflict(user, receipt_id):
    try:
        receipt = OfflineMutationReceipt.objects.select_for_update().get(
            pk=receipt_id,
            user=user,
            status=OfflineMutationReceipt.Status.CONFLICT,
        )
    except (OfflineMutationReceipt.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy xung đột ngoại tuyến.", status=404) from None
    receipt.status = OfflineMutationReceipt.Status.DISCARDED
    receipt.resolution = "DISCARD_LOCAL"
    receipt.resolved_at = timezone.now()
    receipt.save(update_fields=["status", "resolution", "resolved_at", "updated_at"])
    return receipt


@transaction.atomic
def retry_conflict(user, receipt_id, *, idempotency_key, client_mutation_id, context):
    try:
        receipt = OfflineMutationReceipt.objects.select_for_update().select_related("task").get(
            pk=receipt_id,
            user=user,
            status=OfflineMutationReceipt.Status.CONFLICT,
        )
    except (OfflineMutationReceipt.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy xung đột ngoại tuyến.", status=404) from None
    if receipt.task is None:
        raise HousekeepingError("TASK_NOT_FOUND", "Xung đột không còn liên kết với công việc.", status=404)
    task = _task_reference(user, receipt.task_id)
    receipt.status = OfflineMutationReceipt.Status.DISCARDED
    receipt.resolution = "RETRY_WITH_SERVER_VERSION"
    receipt.resolved_at = timezone.now()
    receipt.save(update_fields=["status", "resolution", "resolved_at", "updated_at"])
    payload = {**receipt.request_payload}
    payload.pop("version", None)
    batch = process_sync_batch(
        user,
        [
            {
                "clientMutationId": client_mutation_id,
                "idempotencyKey": idempotency_key,
                "operation": receipt.operation,
                "taskId": str(receipt.task_id),
                "baseVersion": task.version,
                "baseSnapshot": receipt.conflict_payload.get("serverSnapshot") or {},
                "payload": payload,
            }
        ],
        context,
    )
    result = batch["results"][0]
    return receipt, result


@transaction.atomic
def discard_failed_receipt(user, receipt_id):
    try:
        receipt = OfflineMutationReceipt.objects.select_for_update().get(
            pk=receipt_id,
            user=user,
            status__in={
                OfflineMutationReceipt.Status.FAILED,
                OfflineMutationReceipt.Status.CONFLICT,
            },
        )
    except (OfflineMutationReceipt.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy bản ghi đồng bộ cần bỏ.", status=404) from None
    receipt.status = OfflineMutationReceipt.Status.DISCARDED
    receipt.resolution = "DISCARD_LOCAL"
    receipt.resolved_at = timezone.now()
    receipt.save(update_fields=["status", "resolution", "resolved_at", "updated_at"])
    return receipt
