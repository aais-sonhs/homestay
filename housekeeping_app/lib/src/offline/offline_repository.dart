import 'dart:convert';
import 'dart:typed_data';

import 'package:sqflite_sqlcipher/sqflite.dart';
import 'package:uuid/uuid.dart';

import '../storage/encrypted_database.dart';
import 'models.dart';

final class OfflineRepository {
  OfflineRepository(this._encryptedDatabase, {Uuid? uuid})
    : _uuid = uuid ?? const Uuid();

  final EncryptedHousekeepingDatabase _encryptedDatabase;
  final Uuid _uuid;
  Database get _db => _encryptedDatabase.database;

  Future<void> cacheTaskList(
    List<Map<String, Object?>> tasks, {
    String? viewKey,
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    await _db.transaction((transaction) async {
      if (viewKey != null) {
        await transaction.delete(
          'cached_task_views',
          where: 'view_key = ?',
          whereArgs: [viewKey],
        );
      }
      for (var index = 0; index < tasks.length; index += 1) {
        final task = tasks[index];
        final taskId = task['id'] ?? task['taskId'];
        final values = {
          'payload_json': jsonEncode(task),
          'server_version': task['version'],
          'cached_at': now,
        };
        final updated = await transaction.update(
          'cached_tasks',
          values,
          where: 'task_id = ?',
          whereArgs: [taskId],
        );
        if (updated == 0) {
          await transaction.insert('cached_tasks', {
            'task_id': taskId,
            ...values,
          });
        }
        if (viewKey != null) {
          await transaction.insert('cached_task_views', {
            'view_key': viewKey,
            'task_id': taskId,
            'sort_order': index,
          });
        }
      }
    });
  }

  Future<void> cacheTaskDetail(Map<String, Object?> task) async {
    final taskId = (task['id'] ?? task['taskId'])! as String;
    await _db.insert('cached_task_details', {
      'task_id': taskId,
      'payload_json': jsonEncode(task),
      'server_version': task['version'],
      'cached_at': DateTime.now().toUtc().toIso8601String(),
    }, conflictAlgorithm: ConflictAlgorithm.replace);
    await cacheTaskList([task]);
  }

  Future<List<Map<String, Object?>>> cachedTasks({String? viewKey}) async {
    final rows = viewKey == null
        ? await _db.query('cached_tasks', orderBy: 'cached_at DESC, task_id')
        : await _db.rawQuery(
            '''
              SELECT cached_tasks.payload_json
              FROM cached_task_views
              JOIN cached_tasks
                ON cached_tasks.task_id = cached_task_views.task_id
              WHERE cached_task_views.view_key = ?
              ORDER BY cached_task_views.sort_order, cached_tasks.task_id
            ''',
            [viewKey],
          );
    return rows
        .map(
          (row) => Map<String, Object?>.from(
            jsonDecode(row['payload_json']! as String) as Map,
          ),
        )
        .toList(growable: false);
  }

  Future<Map<String, Object?>?> cachedTaskDetail(String taskId) async {
    final rows = await _db.query(
      'cached_task_details',
      where: 'task_id = ?',
      whereArgs: [taskId],
      limit: 1,
    );
    if (rows.isEmpty) return null;
    return Map<String, Object?>.from(
      jsonDecode(rows.first['payload_json']! as String) as Map,
    );
  }

  Future<void> bindUser(String userId) async {
    await _db.transaction((transaction) async {
      final ownerRows = await transaction.query(
        'local_metadata',
        columns: ['metadata_value'],
        where: 'metadata_key = ?',
        whereArgs: ['owner_user_id'],
        limit: 1,
      );
      final owner = ownerRows.isEmpty
          ? null
          : ownerRows.first['metadata_value'] as String;
      if (owner == userId) return;
      if (owner != null) {
        final unresolvedMutations =
            Sqflite.firstIntValue(
              await transaction.rawQuery(
                '''
                  SELECT COUNT(*) FROM mutation_queue
                  WHERE sync_state IN (?, ?, ?, ?)
                ''',
                [
                  LocalSyncState.pending.name,
                  LocalSyncState.syncing.name,
                  LocalSyncState.failed.name,
                  LocalSyncState.conflict.name,
                ],
              ),
            ) ??
            0;
        final unresolvedMedia =
            Sqflite.firstIntValue(
              await transaction.rawQuery(
                '''
                  SELECT COUNT(*) FROM media_queue
                  WHERE sync_state IN (?, ?, ?, ?)
                ''',
                [
                  LocalSyncState.pending.name,
                  LocalSyncState.syncing.name,
                  LocalSyncState.failed.name,
                  LocalSyncState.conflict.name,
                ],
              ),
            ) ??
            0;
        if (unresolvedMutations + unresolvedMedia > 0) {
          throw StateError(
            'Thiết bị còn dữ liệu chưa đồng bộ của tài khoản trước. '
            'Hãy đăng nhập lại tài khoản đó để xử lý.',
          );
        }
        await _clearAccountTables(transaction);
      }
      await transaction.insert('local_metadata', {
        'metadata_key': 'owner_user_id',
        'metadata_value': userId,
      }, conflictAlgorithm: ConflictAlgorithm.replace);
    });
  }

  Future<void> clearUserData() async {
    await _db.transaction((transaction) async {
      // Logout is disabled while unresolved work exists. Secure-delete every
      // account-bound row before another employee can use a shared device.
      await _clearAccountTables(transaction);
      await transaction.delete('local_metadata');
    });
  }

  Future<void> _clearAccountTables(Transaction transaction) async {
    for (final table in const [
      'sync_conflicts',
      'media_queue',
      'mutation_queue',
      'cached_task_views',
      'cached_task_details',
      'cached_tasks',
    ]) {
      await transaction.delete(table);
    }
  }

  Future<int?> cachedTaskVersion(String taskId) async {
    final detail = await _db.query(
      'cached_task_details',
      columns: ['server_version'],
      where: 'task_id = ?',
      whereArgs: [taskId],
      limit: 1,
    );
    if (detail.isNotEmpty) return detail.first['server_version']! as int;
    final list = await _db.query(
      'cached_tasks',
      columns: ['server_version'],
      where: 'task_id = ?',
      whereArgs: [taskId],
      limit: 1,
    );
    return list.isEmpty ? null : list.first['server_version']! as int;
  }

  Future<int> nextProjectedVersion(String taskId) async {
    final serverVersion = await cachedTaskVersion(taskId);
    if (serverVersion == null) {
      throw StateError(
        'Công việc phải được lưu trên thiết bị trước khi tạo thay đổi ngoại tuyến.',
      );
    }
    final mutationCount =
        Sqflite.firstIntValue(
          await _db.rawQuery(
            '''
              SELECT COUNT(*) FROM mutation_queue
              WHERE task_id = ? AND sync_state IN (?, ?, ?, ?)
            ''',
            [
              taskId,
              LocalSyncState.pending.name,
              LocalSyncState.syncing.name,
              LocalSyncState.failed.name,
              LocalSyncState.conflict.name,
            ],
          ),
        ) ??
        0;
    final mediaCount =
        Sqflite.firstIntValue(
          await _db.rawQuery(
            '''
              SELECT COUNT(*) FROM media_queue
              WHERE task_id = ? AND sync_state IN (?, ?, ?, ?)
            ''',
            [
              taskId,
              LocalSyncState.pending.name,
              LocalSyncState.syncing.name,
              LocalSyncState.failed.name,
              LocalSyncState.conflict.name,
            ],
          ),
        ) ??
        0;
    return serverVersion + mutationCount + mediaCount;
  }

  Future<List<String>> latestTaskDependency(String taskId) async {
    final mutations = await _db.query(
      'mutation_queue',
      columns: ['client_mutation_id', 'created_at'],
      where: 'task_id = ? AND sync_state IN (?, ?, ?, ?)',
      whereArgs: [
        taskId,
        LocalSyncState.pending.name,
        LocalSyncState.syncing.name,
        LocalSyncState.failed.name,
        LocalSyncState.conflict.name,
      ],
      orderBy: 'created_at DESC',
      limit: 1,
    );
    final media = await _db.query(
      'media_queue',
      columns: ['client_media_id', 'created_at'],
      where: 'task_id = ? AND sync_state IN (?, ?, ?, ?)',
      whereArgs: [
        taskId,
        LocalSyncState.pending.name,
        LocalSyncState.syncing.name,
        LocalSyncState.failed.name,
        LocalSyncState.conflict.name,
      ],
      orderBy: 'created_at DESC',
      limit: 1,
    );
    if (mutations.isEmpty && media.isEmpty) return const [];
    if (media.isEmpty ||
        (mutations.isNotEmpty &&
            (mutations.first['created_at']! as String).compareTo(
                  media.first['created_at']! as String,
                ) >=
                0)) {
      return [mutations.first['client_mutation_id']! as String];
    }
    return [media.first['client_media_id']! as String];
  }

  Future<QueuedMutation> enqueueMutation({
    required String taskId,
    required String operation,
    required int baseVersion,
    required Map<String, Object?> payload,
    Map<String, Object?> baseSnapshot = const {},
    List<String> dependsOn = const [],
  }) async {
    final id = _uuid.v4();
    final now = DateTime.now().toUtc();
    final mutation = QueuedMutation(
      clientMutationId: id,
      idempotencyKey: id,
      taskId: taskId,
      operation: operation,
      baseVersion: baseVersion,
      payload: payload,
      baseSnapshot: baseSnapshot,
      dependsOn: dependsOn,
      state: LocalSyncState.pending,
      createdAt: now,
    );
    await _db.insert('mutation_queue', {
      'client_mutation_id': mutation.clientMutationId,
      'idempotency_key': mutation.idempotencyKey,
      'task_id': mutation.taskId,
      'operation': mutation.operation,
      'base_version': mutation.baseVersion,
      'payload_json': jsonEncode(mutation.payload),
      'base_snapshot_json': jsonEncode(mutation.baseSnapshot),
      'depends_on_json': jsonEncode(mutation.dependsOn),
      'sync_state': mutation.state.name,
      'created_at': now.toIso8601String(),
      'updated_at': now.toIso8601String(),
    });
    return mutation;
  }

  Future<QueuedMedia> enqueueMedia({
    required String taskId,
    required int baseVersion,
    required List<int> bytes,
    required String fileName,
    required String checksum,
    required Map<String, Object?> metadata,
    List<String> dependsOn = const [],
  }) async {
    final id = _uuid.v4();
    final now = DateTime.now().toUtc().toIso8601String();
    final media = QueuedMedia(
      clientMediaId: id,
      idempotencyKey: id,
      taskId: taskId,
      baseVersion: baseVersion,
      bytes: bytes,
      fileName: fileName,
      checksum: checksum,
      metadata: metadata,
      dependsOn: dependsOn,
      state: LocalSyncState.pending,
    );
    // SQLCipher encrypts every page, including this BLOB and its metadata.
    await _db.insert('media_queue', {
      'client_media_id': id,
      'idempotency_key': id,
      'task_id': taskId,
      'base_version': baseVersion,
      'file_name': fileName,
      'encrypted_blob': Uint8List.fromList(bytes),
      'checksum': checksum,
      'metadata_json': jsonEncode(metadata),
      'depends_on_json': jsonEncode(dependsOn),
      'sync_state': LocalSyncState.pending.name,
      'created_at': now,
      'updated_at': now,
    });
    return media;
  }

  Future<List<QueuedMutation>> readyMutations({int limit = 50}) async {
    final rows = await _db.query(
      'mutation_queue',
      where: 'sync_state = ?',
      whereArgs: [LocalSyncState.pending.name],
      orderBy: 'created_at, client_mutation_id',
    );
    final candidates = OfflineDependencyPlanner.order(
      rows.map(QueuedMutation.fromRow).toList(growable: false),
    );
    final ready = <QueuedMutation>[];
    final includedIds = <String>{};
    for (final mutation in candidates) {
      var dependenciesReady = true;
      for (final dependency in mutation.dependsOn) {
        if (includedIds.contains(dependency)) continue;
        if (!await dependenciesSucceeded([dependency])) {
          dependenciesReady = false;
          break;
        }
      }
      if (dependenciesReady) {
        ready.add(mutation);
        includedIds.add(mutation.clientMutationId);
      }
      if (ready.length == limit) break;
    }
    return ready;
  }

  Future<QueuedMutation> resolveMediaReferences(QueuedMutation mutation) async {
    final verification = mutation.payload['roomVerification'];
    if (verification is! Map ||
        verification['cameraPhotoClientId'] is! String) {
      return mutation;
    }
    final clientMediaId = verification['cameraPhotoClientId']! as String;
    final rows = await _db.query(
      'media_queue',
      columns: ['server_photo_id'],
      where: 'client_media_id = ? AND sync_state = ?',
      whereArgs: [clientMediaId, LocalSyncState.synced.name],
      limit: 1,
    );
    if (rows.isEmpty || rows.single['server_photo_id'] == null) {
      throw StateError('Ảnh xác minh chụp trực tiếp chưa được máy chủ tiếp nhận.');
    }
    final resolvedVerification = Map<String, Object?>.from(verification)
      ..remove('cameraPhotoClientId')
      ..['cameraPhotoId'] = rows.single['server_photo_id'];
    return mutation.withPayload({
      ...mutation.payload,
      'roomVerification': resolvedVerification,
    });
  }

  Future<List<QueuedMedia>> readyMedia({int limit = 10}) async {
    final rows = await _db.query(
      'media_queue',
      where: 'sync_state = ?',
      whereArgs: [LocalSyncState.pending.name],
      orderBy: 'created_at, client_media_id',
      limit: limit,
    );
    final ready = <QueuedMedia>[];
    for (final row in rows) {
      final dependencies = List<String>.from(
        jsonDecode(row['depends_on_json']! as String) as List,
      );
      if (!await dependenciesSucceeded(dependencies)) continue;
      ready.add(
        QueuedMedia(
          clientMediaId: row['client_media_id']! as String,
          idempotencyKey: row['idempotency_key']! as String,
          taskId: row['task_id']! as String,
          baseVersion: row['base_version']! as int,
          bytes: List<int>.from(row['encrypted_blob']! as List<int>),
          fileName: row['file_name']! as String,
          checksum: row['checksum']! as String,
          metadata: Map<String, Object?>.from(
            jsonDecode(row['metadata_json']! as String) as Map,
          ),
          dependsOn: dependencies,
          state: LocalSyncState.parse(row['sync_state']! as String),
        ),
      );
    }
    return ready;
  }

  Future<bool> dependenciesSucceeded(List<String> dependencyIds) async {
    for (final id in dependencyIds) {
      final mutation = await _db.query(
        'mutation_queue',
        columns: ['sync_state'],
        where: 'client_mutation_id = ?',
        whereArgs: [id],
        limit: 1,
      );
      if (mutation.isNotEmpty) {
        if (mutation.first['sync_state'] != LocalSyncState.synced.name) {
          return false;
        }
        continue;
      }
      final media = await _db.query(
        'media_queue',
        columns: ['sync_state'],
        where: 'client_media_id = ?',
        whereArgs: [id],
        limit: 1,
      );
      if (media.isEmpty) {
        // Synced rows are retained for seven days and then purged. Treat an
        // absent historical dependency as locally satisfied; the backend
        // still verifies its durable receipt and returns BLOCKED if unknown.
        continue;
      }
      if (media.first['sync_state'] != LocalSyncState.synced.name) {
        return false;
      }
    }
    return true;
  }

  Future<void> markMutationSyncing(String id) =>
      _updateMutation(id, LocalSyncState.syncing);

  Future<void> markMutationFailed(
    String id, {
    required String code,
    required String message,
  }) async {
    await _db.rawUpdate(
      '''
        UPDATE mutation_queue
        SET sync_state = ?, error_code = ?, error_message = ?,
            attempt_count = attempt_count + 1, updated_at = ?
        WHERE client_mutation_id = ?
      ''',
      [
        LocalSyncState.failed.name,
        code,
        message,
        DateTime.now().toUtc().toIso8601String(),
        id,
      ],
    );
  }

  Future<void> applyBatchResult(Map<String, Object?> result) async {
    final id = result['clientMutationId']! as String;
    final state = LocalSyncState.parse(result['status']! as String);
    final error = result['error'] as Map?;
    await _db.rawUpdate(
      '''
        UPDATE mutation_queue
        SET sync_state = ?, receipt_id = ?, error_code = ?, error_message = ?,
            attempt_count = attempt_count + 1, updated_at = ?
        WHERE client_mutation_id = ?
      ''',
      [
        state.name,
        result['receiptId'],
        error?['code'],
        error?['message'],
        DateTime.now().toUtc().toIso8601String(),
        id,
      ],
    );
    final conflict = result['conflict'];
    if (state == LocalSyncState.conflict &&
        conflict is Map &&
        result['receiptId'] != null) {
      final mutationRows = await _db.query(
        'mutation_queue',
        where: 'client_mutation_id = ?',
        whereArgs: [id],
        limit: 1,
      );
      final mutation = QueuedMutation.fromRow(mutationRows.single);
      await _db.insert('sync_conflicts', {
        'receipt_id': result['receiptId'],
        'client_mutation_id': id,
        'task_id': mutation.taskId,
        'operation': mutation.operation,
        'conflict_json': jsonEncode(conflict),
        'created_at': DateTime.now().toUtc().toIso8601String(),
      }, conflictAlgorithm: ConflictAlgorithm.replace);
    }
    if (state == LocalSyncState.synced && result['result'] is Map) {
      final serverResult = Map<String, Object?>.from(result['result']! as Map);
      final taskId = serverResult['taskId'] as String?;
      final version = serverResult['taskVersion'] ?? serverResult['version'];
      if (taskId != null && version is int) {
        await _updateCachedTaskVersion(taskId, version);
      }
    }
  }

  Future<void> markMediaResult(
    String id,
    LocalSyncState state, {
    String? photoId,
    String? errorCode,
    String? errorMessage,
    int? taskVersion,
  }) async {
    await _db.rawUpdate(
      '''
        UPDATE media_queue
        SET sync_state = ?, server_photo_id = ?, error_code = ?, error_message = ?,
            attempt_count = attempt_count + 1, updated_at = ?
        WHERE client_media_id = ?
      ''',
      [
        state.name,
        photoId,
        errorCode,
        errorMessage,
        DateTime.now().toUtc().toIso8601String(),
        id,
      ],
    );
    if (state == LocalSyncState.synced && taskVersion != null) {
      final rows = await _db.query(
        'media_queue',
        columns: ['task_id'],
        where: 'client_media_id = ?',
        whereArgs: [id],
        limit: 1,
      );
      if (rows.isNotEmpty) {
        await _updateCachedTaskVersion(
          rows.first['task_id']! as String,
          taskVersion,
        );
      }
    }
  }

  Future<void> _updateCachedTaskVersion(String taskId, int version) async {
    await _db.transaction((transaction) async {
      for (final table in const ['cached_tasks', 'cached_task_details']) {
        final rows = await transaction.query(
          table,
          columns: ['payload_json'],
          where: 'task_id = ?',
          whereArgs: [taskId],
          limit: 1,
        );
        if (rows.isEmpty) continue;
        final payload = Map<String, Object?>.from(
          jsonDecode(rows.first['payload_json']! as String) as Map,
        )..['version'] = version;
        await transaction.update(
          table,
          {'server_version': version, 'payload_json': jsonEncode(payload)},
          where: 'task_id = ?',
          whereArgs: [taskId],
        );
      }
    });
  }

  Future<void> markMediaSyncing(String id) async {
    await _db.update(
      'media_queue',
      {
        'sync_state': LocalSyncState.syncing.name,
        'updated_at': DateTime.now().toUtc().toIso8601String(),
      },
      where: 'client_media_id = ?',
      whereArgs: [id],
    );
  }

  Future<void> recordMediaConflict({
    required QueuedMedia media,
    required Map<String, Object?> serverSnapshot,
    required String errorCode,
    required String errorMessage,
  }) async {
    final receiptId = 'media:${media.clientMediaId}';
    final now = DateTime.now().toUtc().toIso8601String();
    await _db.transaction((transaction) async {
      await transaction.update(
        'media_queue',
        {
          'sync_state': LocalSyncState.conflict.name,
          'error_code': errorCode,
          'error_message': errorMessage,
          'updated_at': now,
        },
        where: 'client_media_id = ?',
        whereArgs: [media.clientMediaId],
      );
      await transaction.insert('sync_conflicts', {
        'receipt_id': receiptId,
        'client_mutation_id': media.clientMediaId,
        'task_id': media.taskId,
        'operation': 'UPLOAD_MEDIA',
        'conflict_json': jsonEncode({
          'baseVersion': media.baseVersion,
          'localOperation': {
            'metadata': media.metadata,
            'checksum': media.checksum,
          },
          'serverSnapshot': serverSnapshot,
          'resolutionOptions': ['DISCARD_LOCAL', 'RETRY_WITH_SERVER_VERSION'],
        }),
        'created_at': now,
      }, conflictAlgorithm: ConflictAlgorithm.replace);
    });
  }

  Future<void> _updateMutation(String id, LocalSyncState state) async {
    await _db.update(
      'mutation_queue',
      {
        'sync_state': state.name,
        'updated_at': DateTime.now().toUtc().toIso8601String(),
      },
      where: 'client_mutation_id = ?',
      whereArgs: [id],
    );
  }

  Future<int> unresolvedCount({String? taskId}) async {
    const unresolved = ['pending', 'syncing', 'failed', 'conflict'];
    final args = <Object?>[...unresolved];
    var mutationWhere = 'sync_state IN (?, ?, ?, ?)';
    var mediaWhere = 'sync_state IN (?, ?, ?, ?)';
    if (taskId != null) {
      mutationWhere += ' AND task_id = ?';
      mediaWhere += ' AND task_id = ?';
      args.add(taskId);
    }
    final mutationCount =
        Sqflite.firstIntValue(
          await _db.rawQuery(
            'SELECT COUNT(*) FROM mutation_queue WHERE $mutationWhere',
            args,
          ),
        ) ??
        0;
    final mediaCount =
        Sqflite.firstIntValue(
          await _db.rawQuery(
            'SELECT COUNT(*) FROM media_queue WHERE $mediaWhere',
            args,
          ),
        ) ??
        0;
    return mutationCount + mediaCount;
  }

  Future<bool> canComplete(String taskId) async =>
      await unresolvedCount(taskId: taskId) == 0;

  Future<Map<String, TaskSyncSummary>> syncSummariesByTask() async {
    final counters = <String, List<int>>{};
    for (final table in const ['mutation_queue', 'media_queue']) {
      final rows = await _db.rawQuery(
        '''
        SELECT task_id, sync_state, COUNT(*) AS item_count
        FROM $table
        WHERE sync_state IN (?, ?, ?, ?)
        GROUP BY task_id, sync_state
      ''',
        [
          LocalSyncState.pending.name,
          LocalSyncState.syncing.name,
          LocalSyncState.failed.name,
          LocalSyncState.conflict.name,
        ],
      );
      for (final row in rows) {
        final values = counters.putIfAbsent(
          row['task_id']! as String,
          () => [0, 0, 0, 0],
        );
        final count = row['item_count']! as int;
        switch (LocalSyncState.parse(row['sync_state']! as String)) {
          case LocalSyncState.pending:
            values[0] += count;
          case LocalSyncState.syncing:
            values[1] += count;
          case LocalSyncState.failed:
            values[2] += count;
          case LocalSyncState.conflict:
            values[3] += count;
          case LocalSyncState.synced:
          case LocalSyncState.discarded:
        }
      }
    }
    return {
      for (final entry in counters.entries)
        entry.key: TaskSyncSummary(
          pending: entry.value[0],
          syncing: entry.value[1],
          failed: entry.value[2],
          conflict: entry.value[3],
        ),
    };
  }

  Future<List<LocalMediaPreview>> localMedia(String taskId) async {
    final rows = await _db.query(
      'media_queue',
      where: 'task_id = ? AND sync_state IN (?, ?, ?, ?)',
      whereArgs: [
        taskId,
        LocalSyncState.pending.name,
        LocalSyncState.syncing.name,
        LocalSyncState.failed.name,
        LocalSyncState.conflict.name,
      ],
      orderBy: 'created_at DESC, client_media_id',
    );
    return rows
        .map((row) {
          final metadata = Map<String, Object?>.from(
            jsonDecode(row['metadata_json']! as String) as Map,
          );
          return LocalMediaPreview(
            clientMediaId: row['client_media_id']! as String,
            bytes: List<int>.from(row['encrypted_blob']! as List<int>),
            category: metadata['category'] as String? ?? 'AFTER',
            checklistItemId: metadata['checklistItemId'] as String?,
            state: LocalSyncState.parse(row['sync_state']! as String),
            createdAt: DateTime.parse(row['created_at']! as String),
            errorMessage: row['error_message'] as String?,
          );
        })
        .toList(growable: false);
  }

  Future<List<SyncConflict>> conflicts() async {
    final rows = await _db.query(
      'sync_conflicts',
      where: 'resolved_at IS NULL',
      orderBy: 'created_at, receipt_id',
    );
    return rows
        .map(
          (row) => SyncConflict(
            receiptId: row['receipt_id']! as String,
            clientMutationId: row['client_mutation_id']! as String,
            taskId: row['task_id']! as String,
            operation: row['operation']! as String,
            payload: Map<String, Object?>.from(
              jsonDecode(row['conflict_json']! as String) as Map,
            ),
            createdAt: DateTime.parse(row['created_at']! as String),
          ),
        )
        .toList(growable: false);
  }

  Future<List<SyncFailure>> failures() async {
    final failures = <SyncFailure>[];
    final mutations = await _db.query(
      'mutation_queue',
      where: 'sync_state = ?',
      whereArgs: [LocalSyncState.failed.name],
      orderBy: 'created_at',
    );
    failures.addAll(
      mutations.map(
        (row) => SyncFailure(
          localId: row['client_mutation_id']! as String,
          taskId: row['task_id']! as String,
          operation: row['operation']! as String,
          isMedia: false,
          errorCode: row['error_code'] as String? ?? 'SYNC_FAILED',
          errorMessage:
              row['error_message'] as String? ??
                  'Không thể đồng bộ thay đổi ngoại tuyến.',
          receiptId: row['receipt_id'] as String?,
        ),
      ),
    );
    final media = await _db.query(
      'media_queue',
      where: 'sync_state = ?',
      whereArgs: [LocalSyncState.failed.name],
      orderBy: 'created_at',
    );
    failures.addAll(
      media.map(
        (row) => SyncFailure(
          localId: row['client_media_id']! as String,
          taskId: row['task_id']! as String,
          operation: 'UPLOAD_MEDIA',
          isMedia: true,
          errorCode: row['error_code'] as String? ?? 'SYNC_FAILED',
          errorMessage:
              row['error_message'] as String? ?? 'Không thể đồng bộ ảnh.',
        ),
      ),
    );
    return failures;
  }

  Future<void> discardConflictLocally(String receiptId) async {
    final now = DateTime.now().toUtc().toIso8601String();
    await _db.transaction((transaction) async {
      final rows = await transaction.query(
        'sync_conflicts',
        columns: ['client_mutation_id'],
        where: 'receipt_id = ?',
        whereArgs: [receiptId],
        limit: 1,
      );
      if (rows.isEmpty) return;
      await transaction.update(
        'sync_conflicts',
        {'resolved_at': now},
        where: 'receipt_id = ?',
        whereArgs: [receiptId],
      );
      await transaction.update(
        receiptId.startsWith('media:') ? 'media_queue' : 'mutation_queue',
        {'sync_state': LocalSyncState.discarded.name, 'updated_at': now},
        where: receiptId.startsWith('media:')
            ? 'client_media_id = ?'
            : 'client_mutation_id = ?',
        whereArgs: [rows.first['client_mutation_id']],
      );
      await _markDependentsFailed(
        transaction,
        rows.first['client_mutation_id']! as String,
        now,
      );
    });
  }

  Future<void> applyConflictRetryResult({
    required SyncConflict original,
    required String retryIdempotencyKey,
    required Map<String, Object?> result,
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    final state = LocalSyncState.parse(result['status']! as String);
    final error = result['error'] as Map?;
    final newReceiptId = result['receiptId'] as String?;
    await _db.transaction((transaction) async {
      await transaction.update(
        'sync_conflicts',
        {'resolved_at': now},
        where: 'receipt_id = ?',
        whereArgs: [original.receiptId],
      );
      await transaction.update(
        'mutation_queue',
        {
          // Keep the stable local mutation id so queued dependents still point
          // to the operation the user explicitly chose to retry.
          'idempotency_key': retryIdempotencyKey,
          'base_version':
              (original.payload['serverSnapshot'] as Map?)?['version'],
          'sync_state': state.name,
          'receipt_id': newReceiptId,
          'error_code': error?['code'],
          'error_message': error?['message'],
          'updated_at': now,
        },
        where: 'client_mutation_id = ?',
        whereArgs: [original.clientMutationId],
      );
      await transaction.rawUpdate(
        '''
          UPDATE mutation_queue
          SET attempt_count = attempt_count + 1
          WHERE client_mutation_id = ?
        ''',
        [original.clientMutationId],
      );
      final conflict = result['conflict'];
      if (state == LocalSyncState.conflict &&
          newReceiptId != null &&
          conflict is Map) {
        await transaction.insert('sync_conflicts', {
          'receipt_id': newReceiptId,
          'client_mutation_id': original.clientMutationId,
          'task_id': original.taskId,
          'operation': original.operation,
          'conflict_json': jsonEncode(conflict),
          'created_at': now,
        }, conflictAlgorithm: ConflictAlgorithm.replace);
      }
    });
    if (state == LocalSyncState.synced && result['result'] is Map) {
      final serverResult = Map<String, Object?>.from(result['result']! as Map);
      final version = serverResult['taskVersion'] ?? serverResult['version'];
      if (version is int) {
        await _updateCachedTaskVersion(original.taskId, version);
      }
    }
  }

  Future<void> retryMediaWithServerVersion(
    String clientMediaId,
    int serverVersion,
  ) async {
    final receiptId = 'media:$clientMediaId';
    final now = DateTime.now().toUtc().toIso8601String();
    await _db.transaction((transaction) async {
      await transaction.update(
        'media_queue',
        {
          'base_version': serverVersion,
          'idempotency_key': _uuid.v4(),
          'sync_state': LocalSyncState.pending.name,
          'error_code': null,
          'error_message': null,
          'updated_at': now,
        },
        where: 'client_media_id = ?',
        whereArgs: [clientMediaId],
      );
      await transaction.update(
        'sync_conflicts',
        {'resolved_at': now},
        where: 'receipt_id = ?',
        whereArgs: [receiptId],
      );
    });
  }

  Future<void> retryFailed(String clientMutationId) =>
      _updateMutation(clientMutationId, LocalSyncState.pending);

  Future<void> retryFailure(
    SyncFailure failure, {
    String? newIdempotencyKey,
  }) async {
    if (!failure.isMedia) {
      if (newIdempotencyKey == null) {
        await retryFailed(failure.localId);
      } else {
        await _db.update(
          'mutation_queue',
          {
            'idempotency_key': newIdempotencyKey,
            'receipt_id': null,
            'sync_state': LocalSyncState.pending.name,
            'error_code': null,
            'error_message': null,
            'updated_at': DateTime.now().toUtc().toIso8601String(),
          },
          where: 'client_mutation_id = ?',
          whereArgs: [failure.localId],
        );
      }
      return;
    }
    await _db.update(
      'media_queue',
      {
        'sync_state': LocalSyncState.pending.name,
        'updated_at': DateTime.now().toUtc().toIso8601String(),
      },
      where: 'client_media_id = ?',
      whereArgs: [failure.localId],
    );
  }

  Future<void> discardFailure(SyncFailure failure) async {
    final now = DateTime.now().toUtc().toIso8601String();
    await _db.transaction((transaction) async {
      await transaction.update(
        failure.isMedia ? 'media_queue' : 'mutation_queue',
        {'sync_state': LocalSyncState.discarded.name, 'updated_at': now},
        where: failure.isMedia
            ? 'client_media_id = ?'
            : 'client_mutation_id = ?',
        whereArgs: [failure.localId],
      );
      await _markDependentsFailed(transaction, failure.localId, now);
    });
  }

  Future<void> _markDependentsFailed(
    Transaction transaction,
    String dependencyId,
    String now,
  ) async {
    for (final descriptor in const [
      ('mutation_queue', 'client_mutation_id'),
      ('media_queue', 'client_media_id'),
    ]) {
      final rows = await transaction.query(
        descriptor.$1,
        columns: [descriptor.$2, 'depends_on_json'],
        where: 'sync_state IN (?, ?)',
        whereArgs: [LocalSyncState.pending.name, LocalSyncState.syncing.name],
      );
      for (final row in rows) {
        final dependencies = List<String>.from(
          jsonDecode(row['depends_on_json']! as String) as List,
        );
        if (!dependencies.contains(dependencyId)) continue;
        await transaction.update(
          descriptor.$1,
          {
            'sync_state': LocalSyncState.failed.name,
            'error_code': 'DEPENDENCY_DISCARDED',
            'error_message':
                'Thao tác phụ thuộc đã bị bỏ. Hãy bỏ hoặc tạo lại thao tác này.',
            'updated_at': now,
          },
          where: '${descriptor.$2} = ?',
          whereArgs: [row[descriptor.$2]],
        );
      }
    }
  }

  Future<void> purgeSynced({
    Duration olderThan = const Duration(days: 7),
  }) async {
    final threshold = DateTime.now()
        .toUtc()
        .subtract(olderThan)
        .toIso8601String();
    await _db.delete(
      'mutation_queue',
      where: 'sync_state IN (?, ?) AND updated_at < ?',
      whereArgs: [
        LocalSyncState.synced.name,
        LocalSyncState.discarded.name,
        threshold,
      ],
    );
    await _db.delete(
      'media_queue',
      where: 'sync_state = ? AND updated_at < ?',
      whereArgs: [LocalSyncState.synced.name, threshold],
    );
  }
}
