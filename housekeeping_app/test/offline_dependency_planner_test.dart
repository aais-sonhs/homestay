import 'package:bliss_housekeeping_app/src/offline/models.dart';
import 'package:flutter_test/flutter_test.dart';

QueuedMutation mutation(String id, {List<String> dependsOn = const []}) =>
    QueuedMutation(
      clientMutationId: id,
      idempotencyKey: id,
      taskId: 'task-1',
      operation: 'UPDATE_CHECKLIST_ITEM',
      baseVersion: 1,
      payload: const {},
      baseSnapshot: const {},
      dependsOn: dependsOn,
      state: LocalSyncState.pending,
      createdAt: DateTime.utc(2026, 8, 5),
    );

void main() {
  test('dependency planner sends prerequisites before dependent mutations', () {
    final ordered = OfflineDependencyPlanner.order([
      mutation('complete', dependsOn: ['photo', 'checklist']),
      mutation('photo', dependsOn: ['checklist']),
      mutation('checklist'),
    ]);

    expect(ordered.map((item) => item.clientMutationId), [
      'checklist',
      'photo',
      'complete',
    ]);
  });

  test('dependency planner rejects cycles instead of overwriting order', () {
    expect(
      () => OfflineDependencyPlanner.order([
        mutation('first', dependsOn: ['second']),
        mutation('second', dependsOn: ['first']),
      ]),
      throwsFormatException,
    );
  });

  test('sync state parser preserves server result states', () {
    expect(LocalSyncState.parse('SYNCED'), LocalSyncState.synced);
    expect(LocalSyncState.parse('CONFLICT'), LocalSyncState.conflict);
    expect(LocalSyncState.parse('FAILED'), LocalSyncState.failed);
  });

  test('media reference resolution can replace a queued payload safely', () {
    final original = mutation('start');
    final resolved = original.withPayload({
      'roomVerification': {'cameraPhotoId': 'server-photo-1'},
    });

    expect(original.payload, isEmpty);
    expect(
      (resolved.payload['roomVerification'] as Map)['cameraPhotoId'],
      'server-photo-1',
    );
    expect(resolved.clientMutationId, original.clientMutationId);
    expect(resolved.baseVersion, original.baseVersion);
  });
}
