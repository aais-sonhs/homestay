import 'package:bliss_housekeeping_app/src/presentation/task_presentation.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, Object?> task({
  String status = 'IN_PROGRESS',
  String dueAt = '2026-08-05T11:00:00+07:00',
}) => {
  'id': 'task-1',
  'code': 'HK-001',
  'status': status,
  'statusLabel': 'Đang thực hiện',
  'taskType': 'CHECKOUT_CLEANING',
  'taskTypeLabel': 'Dọn sau check-out',
  'dueAt': dueAt,
  'room': {
    'code': 'A101',
    'name': 'Phòng A101',
    'floor': 'Tầng 1',
    'area': 'Khu A',
  },
  'branch': {'name': 'Đà Lạt'},
  'checklistSummary': {'totalRequired': 10, 'completedRequired': 4},
};

void main() {
  test('all seven tabs map to an authoritative server filter', () {
    expect(HousekeepingTaskTab.values, hasLength(7));
    for (final tab in HousekeepingTaskTab.values) {
      expect(tab.apiFilters, isNotEmpty, reason: tab.name);
    }
    expect(
      HousekeepingTaskTab.support.apiFilters['status'],
      contains('WAITING_SUPPORT'),
    );
    expect(HousekeepingTaskTab.rework.apiFilters['status'], 'QC_REJECTED');
  });

  test('filter query preserves task scope fields and risk flags', () {
    final filters = TaskFilters(
      query: 'A101',
      date: DateTime(2026, 8, 5),
      branchId: 'branch-1',
      floor: 'Tầng 1',
      roomType: 'DELUXE',
      priority: 'URGENT',
      areaId: 'area-1',
      shiftId: 'shift-1',
      status: 'WAITING_QC',
      assignee: 'worker-1',
      qcRework: true,
      overdue: true,
      checkinRisk: true,
    ).toApiQuery(HousekeepingTaskTab.mine);

    expect(filters['assignee'], 'worker-1');
    expect(filters['areaId'], 'area-1');
    expect(filters['shiftId'], 'shift-1');
    expect(filters['status'], 'WAITING_QC');
    expect(filters['qcRework'], 'true');
    expect(filters['q'], 'A101');
    expect(filters['date'], '2026-08-05');
    expect(filters['overdue'], 'true');
    expect(filters['checkinRisk'], 'true');
  });

  test('task presentation exposes countdown, checklist and scoped search', () {
    final view = TaskViewData(task());
    final now = DateTime.parse('2026-08-05T10:00:00+07:00');

    expect(view.dueLabel(now: now), 'Còn 1g 0p');
    expect(view.checklistDone, 4);
    expect(view.checklistTotal, 10);
    expect(view.matchesText('a101'), isTrue);
    expect(view.matchesText('không tồn tại'), isFalse);
  });
}
