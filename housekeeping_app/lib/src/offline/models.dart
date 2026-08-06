import 'dart:convert';

enum LocalSyncState {
  pending,
  syncing,
  synced,
  failed,
  conflict,
  discarded;

  static LocalSyncState parse(String value) => LocalSyncState.values.firstWhere(
    (candidate) => candidate.name == value.toLowerCase(),
    orElse: () => LocalSyncState.failed,
  );
}

final class QueuedMutation {
  const QueuedMutation({
    required this.clientMutationId,
    required this.idempotencyKey,
    required this.taskId,
    required this.operation,
    required this.baseVersion,
    required this.payload,
    required this.baseSnapshot,
    required this.dependsOn,
    required this.state,
    required this.createdAt,
    this.receiptId,
    this.errorCode,
    this.errorMessage,
  });

  final String clientMutationId;
  final String idempotencyKey;
  final String taskId;
  final String operation;
  final int baseVersion;
  final Map<String, Object?> payload;
  final Map<String, Object?> baseSnapshot;
  final List<String> dependsOn;
  final LocalSyncState state;
  final DateTime createdAt;
  final String? receiptId;
  final String? errorCode;
  final String? errorMessage;

  Map<String, Object?> toBatchJson() => {
    'clientMutationId': clientMutationId,
    'idempotencyKey': idempotencyKey,
    'taskId': taskId,
    'operation': operation,
    'baseVersion': baseVersion,
    'payload': payload,
    'baseSnapshot': baseSnapshot,
    'dependsOn': dependsOn,
  };

  QueuedMutation withPayload(Map<String, Object?> resolvedPayload) =>
      QueuedMutation(
        clientMutationId: clientMutationId,
        idempotencyKey: idempotencyKey,
        taskId: taskId,
        operation: operation,
        baseVersion: baseVersion,
        payload: resolvedPayload,
        baseSnapshot: baseSnapshot,
        dependsOn: dependsOn,
        state: state,
        createdAt: createdAt,
        receiptId: receiptId,
        errorCode: errorCode,
        errorMessage: errorMessage,
      );

  static QueuedMutation fromRow(Map<String, Object?> row) => QueuedMutation(
    clientMutationId: row['client_mutation_id']! as String,
    idempotencyKey: row['idempotency_key']! as String,
    taskId: row['task_id']! as String,
    operation: row['operation']! as String,
    baseVersion: row['base_version']! as int,
    payload: Map<String, Object?>.from(
      jsonDecode(row['payload_json']! as String) as Map,
    ),
    baseSnapshot: Map<String, Object?>.from(
      jsonDecode(row['base_snapshot_json']! as String) as Map,
    ),
    dependsOn: List<String>.from(
      jsonDecode(row['depends_on_json']! as String) as List,
    ),
    state: LocalSyncState.parse(row['sync_state']! as String),
    createdAt: DateTime.parse(row['created_at']! as String),
    receiptId: row['receipt_id'] as String?,
    errorCode: row['error_code'] as String?,
    errorMessage: row['error_message'] as String?,
  );
}

final class QueuedMedia {
  const QueuedMedia({
    required this.clientMediaId,
    required this.idempotencyKey,
    required this.taskId,
    required this.baseVersion,
    required this.bytes,
    required this.fileName,
    required this.checksum,
    required this.metadata,
    required this.dependsOn,
    required this.state,
  });

  final String clientMediaId;
  final String idempotencyKey;
  final String taskId;
  final int baseVersion;
  final List<int> bytes;
  final String fileName;
  final String checksum;
  final Map<String, Object?> metadata;
  final List<String> dependsOn;
  final LocalSyncState state;
}

final class LocalMediaPreview {
  const LocalMediaPreview({
    required this.clientMediaId,
    required this.bytes,
    required this.category,
    required this.state,
    required this.createdAt,
    this.checklistItemId,
    this.errorMessage,
  });

  final String clientMediaId;
  final List<int> bytes;
  final String category;
  final String? checklistItemId;
  final LocalSyncState state;
  final DateTime createdAt;
  final String? errorMessage;
}

final class TaskSyncSummary {
  const TaskSyncSummary({
    this.pending = 0,
    this.syncing = 0,
    this.failed = 0,
    this.conflict = 0,
  });

  final int pending;
  final int syncing;
  final int failed;
  final int conflict;

  int get unresolved => pending + syncing + failed + conflict;

  String get label {
    if (conflict > 0) return '$conflict xung đột';
    if (failed > 0) return '$failed lỗi đồng bộ';
    if (syncing > 0) return '$syncing đang đồng bộ';
    if (pending > 0) return '$pending chờ đồng bộ';
    return 'Đã đồng bộ';
  }
}

final class SyncConflict {
  const SyncConflict({
    required this.receiptId,
    required this.clientMutationId,
    required this.taskId,
    required this.operation,
    required this.payload,
    required this.createdAt,
  });

  final String receiptId;
  final String clientMutationId;
  final String taskId;
  final String operation;
  final Map<String, Object?> payload;
  final DateTime createdAt;
}

final class SyncFailure {
  const SyncFailure({
    required this.localId,
    required this.taskId,
    required this.operation,
    required this.isMedia,
    required this.errorCode,
    required this.errorMessage,
    this.receiptId,
  });

  final String localId;
  final String taskId;
  final String operation;
  final bool isMedia;
  final String errorCode;
  final String errorMessage;
  final String? receiptId;
}

final class OfflineDependencyPlanner {
  const OfflineDependencyPlanner._();

  static List<QueuedMutation> order(List<QueuedMutation> mutations) {
    final byId = {
      for (final mutation in mutations) mutation.clientMutationId: mutation,
    };
    final incoming = {
      for (final mutation in mutations) mutation.clientMutationId: 0,
    };
    final children = <String, List<String>>{};
    for (final mutation in mutations) {
      for (final dependency in mutation.dependsOn.where(byId.containsKey)) {
        incoming[mutation.clientMutationId] =
            incoming[mutation.clientMutationId]! + 1;
        children
            .putIfAbsent(dependency, () => <String>[])
            .add(mutation.clientMutationId);
      }
    }
    final ready = mutations
        .where((mutation) => incoming[mutation.clientMutationId] == 0)
        .toList(growable: true);
    final ordered = <QueuedMutation>[];
    while (ready.isNotEmpty) {
      final mutation = ready.removeAt(0);
      ordered.add(mutation);
      for (final child
          in children[mutation.clientMutationId] ?? const <String>[]) {
        incoming[child] = incoming[child]! - 1;
        if (incoming[child] == 0) ready.add(byId[child]!);
      }
    }
    if (ordered.length != mutations.length) {
      throw const FormatException(
        'Các thay đổi ngoại tuyến phụ thuộc lẫn nhau nên không thể đồng bộ.',
      );
    }
    return ordered;
  }
}
