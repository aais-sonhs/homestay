import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:uuid/uuid.dart';

import '../api/housekeeping_api.dart';
import 'models.dart';
import 'offline_repository.dart';

final class SyncReport {
  const SyncReport({
    required this.mediaSynced,
    required this.mutationsSynced,
    required this.failed,
    required this.conflicts,
  });

  final int mediaSynced;
  final int mutationsSynced;
  final int failed;
  final int conflicts;
}

final class _SyncRound {
  const _SyncRound({
    this.mediaSynced = 0,
    this.mutationsSynced = 0,
    this.failed = 0,
    this.conflicts = 0,
  });

  final int mediaSynced;
  final int mutationsSynced;
  final int failed;
  final int conflicts;

  int get synced => mediaSynced + mutationsSynced;
}

final class OfflineSyncEngine {
  OfflineSyncEngine({
    required OfflineRepository repository,
    required HousekeepingApi api,
    Connectivity? connectivity,
  }) : _repository = repository,
       _api = api,
       _connectivity = connectivity ?? Connectivity();

  final OfflineRepository _repository;
  final HousekeepingApi _api;
  final Connectivity _connectivity;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySubscription;
  bool _running = false;

  void startAutomaticSync() {
    _connectivitySubscription ??= _connectivity.onConnectivityChanged.listen((
      results,
    ) {
      if (!results.contains(ConnectivityResult.none)) {
        unawaited(syncNow());
      }
    });
  }

  Future<SyncReport> syncNow() async {
    if (_running) {
      return const SyncReport(
        mediaSynced: 0,
        mutationsSynced: 0,
        failed: 0,
        conflicts: 0,
      );
    }
    _running = true;
    var mediaSynced = 0;
    var mutationsSynced = 0;
    var failed = 0;
    var conflicts = 0;
    try {
      // A checklist -> photo -> complete chain can span both local tables.
      // Re-evaluate readiness after every successful round so the full chain
      // is drained in one reconnect without busy-looping failures/conflicts.
      for (var roundNumber = 0; roundNumber < 100; roundNumber += 1) {
        final mediaRound = await _syncReadyMedia();
        final mutationRound = await _syncReadyMutations();
        mediaSynced += mediaRound.mediaSynced;
        mutationsSynced += mutationRound.mutationsSynced;
        failed += mediaRound.failed + mutationRound.failed;
        conflicts += mediaRound.conflicts + mutationRound.conflicts;
        if (mediaRound.synced + mutationRound.synced == 0) break;
      }
      await _repository.purgeSynced();
      return SyncReport(
        mediaSynced: mediaSynced,
        mutationsSynced: mutationsSynced,
        failed: failed,
        conflicts: conflicts,
      );
    } finally {
      _running = false;
    }
  }

  Future<_SyncRound> _syncReadyMedia() async {
    var synced = 0;
    var failed = 0;
    var conflicts = 0;
    // Connectivity is only a hint. Every request still handles timeout,
    // socket and API errors and keeps the encrypted local row retryable.
    for (final media in await _repository.readyMedia()) {
      await _repository.markMediaSyncing(media.clientMediaId);
      try {
        final result = await _api.uploadMedia(media);
        await _repository.markMediaResult(
          media.clientMediaId,
          LocalSyncState.synced,
          photoId: result['photoId'] as String?,
          taskVersion: result['taskVersion'] as int?,
        );
        synced += 1;
      } on ApiFailure catch (error) {
        if (error.isConflict) {
          Map<String, Object?> server = const {};
          try {
            server = await _api.taskDetail(media.taskId);
          } on Object {
            // The local/base snapshot is still useful until the server
            // snapshot can be downloaded on a later attempt.
          }
          await _repository.recordMediaConflict(
            media: media,
            serverSnapshot: server,
            errorCode: error.code,
            errorMessage: error.message,
          );
          conflicts += 1;
        } else {
          await _repository.markMediaResult(
            media.clientMediaId,
            LocalSyncState.failed,
            errorCode: error.code,
            errorMessage: error.message,
          );
          failed += 1;
        }
      } on Object catch (error) {
        await _repository.markMediaResult(
          media.clientMediaId,
          LocalSyncState.failed,
          errorCode: 'NETWORK_ERROR',
          errorMessage: error.toString(),
        );
        failed += 1;
      }
    }
    return _SyncRound(
      mediaSynced: synced,
      failed: failed,
      conflicts: conflicts,
    );
  }

  Future<_SyncRound> _syncReadyMutations() async {
    final ready = await _repository.readyMutations();
    final mutations = <QueuedMutation>[];
    var resolutionFailures = 0;
    for (final mutation in ready) {
      try {
        mutations.add(await _repository.resolveMediaReferences(mutation));
      } on Object catch (error) {
        await _repository.markMutationFailed(
          mutation.clientMutationId,
          code: 'MEDIA_REFERENCE_NOT_READY',
          message: error.toString(),
        );
        resolutionFailures += 1;
      }
    }
    if (mutations.isEmpty) return _SyncRound(failed: resolutionFailures);
    for (final mutation in mutations) {
      await _repository.markMutationSyncing(mutation.clientMutationId);
    }
    var synced = 0;
    var failed = resolutionFailures;
    var conflicts = 0;
    try {
      final batch = await _api.syncBatch(mutations);
      final results = (batch['results']! as List).cast<Map>();
      for (final rawResult in results) {
        final result = Map<String, Object?>.from(rawResult);
        await _repository.applyBatchResult(result);
        switch ((result['status']! as String).toUpperCase()) {
          case 'SYNCED':
            synced += 1;
          case 'CONFLICT':
            conflicts += 1;
          case 'FAILED':
          case 'BLOCKED':
            failed += 1;
        }
      }
    } on Object catch (error) {
      for (final mutation in mutations) {
        await _repository.markMutationFailed(
          mutation.clientMutationId,
          code: error is ApiFailure ? error.code : 'NETWORK_ERROR',
          message: error is ApiFailure ? error.message : error.toString(),
        );
      }
      failed += mutations.length;
    }
    return _SyncRound(
      mutationsSynced: synced,
      failed: failed,
      conflicts: conflicts,
    );
  }

  Future<void> discardConflict(SyncConflict conflict) async {
    if (conflict.receiptId.startsWith('media:')) {
      await _repository.discardConflictLocally(conflict.receiptId);
      return;
    }
    await _api.resolveConflict(
      receiptId: conflict.receiptId,
      action: 'DISCARD_LOCAL',
      resolutionIdempotencyKey: const Uuid().v4(),
    );
    await _repository.discardConflictLocally(conflict.receiptId);
  }

  Future<void> retryConflict(SyncConflict conflict) async {
    if (conflict.receiptId.startsWith('media:')) {
      final server = conflict.payload['serverSnapshot'] as Map?;
      final version = server?['version'];
      if (version is! int) {
        throw const FormatException(
          'Không có phiên bản trên máy chủ để thử đồng bộ lại ảnh.',
        );
      }
      await _repository.retryMediaWithServerVersion(
        conflict.clientMutationId,
        version,
      );
      await syncNow();
      return;
    }
    final retryKey = const Uuid().v4();
    final result = await _api.resolveConflict(
      receiptId: conflict.receiptId,
      action: 'RETRY_WITH_SERVER_VERSION',
      resolutionIdempotencyKey: const Uuid().v4(),
      newIdempotencyKey: retryKey,
      clientMutationId: retryKey,
    );
    final retry = result['retry'] as Map?;
    if (retry != null) {
      await _repository.applyConflictRetryResult(
        original: conflict,
        retryIdempotencyKey: retryKey,
        result: Map<String, Object?>.from(retry),
      );
    }
  }

  Future<void> discardFailure(SyncFailure failure) async {
    if (failure.receiptId != null) {
      await _api.discardReceipt(
        receiptId: failure.receiptId!,
        idempotencyKey: const Uuid().v4(),
      );
    }
    await _repository.discardFailure(failure);
  }

  Future<void> retryFailure(SyncFailure failure) async {
    String? replacementKey;
    if (failure.receiptId != null) {
      await _api.discardReceipt(
        receiptId: failure.receiptId!,
        idempotencyKey: const Uuid().v4(),
      );
      replacementKey = const Uuid().v4();
    }
    await _repository.retryFailure(failure, newIdempotencyKey: replacementKey);
    await syncNow();
  }

  Future<void> dispose() async {
    await _connectivitySubscription?.cancel();
    _connectivitySubscription = null;
  }
}
