import 'package:bliss_housekeeping_app/src/offline/models.dart';
import 'package:bliss_housekeeping_app/src/presentation/task_presentation.dart';
import 'package:bliss_housekeeping_app/src/widgets/checklist_editor.dart';
import 'package:bliss_housekeeping_app/src/widgets/conflict_resolution_sheet.dart';
import 'package:bliss_housekeeping_app/src/widgets/task_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, Object?> richTask() => {
  'id': 'task-1',
  'code': 'HK-001',
  'status': 'QC_REJECTED',
  'statusLabel': 'QC không đạt',
  'taskType': 'QC_REWORK',
  'taskTypeLabel': 'Dọn lại sau QC',
  'priority': 'URGENT',
  'progressPercent': 70,
  'dueAt': '2026-08-05T09:00:00+07:00',
  'isOverdue': true,
  'isCheckinRisk': true,
  'guestInRoom': true,
  'specialRequest': 'Dị ứng mùi hương',
  'photoCount': 3,
  'roomStatus': 'REWORK_REQUIRED',
  'room': {
    'code': 'A101',
    'name': 'Phòng A101',
    'floor': 'Tầng 1',
    'area': 'Khu A',
  },
  'branch': {'name': 'Đà Lạt'},
  'assignee': {'name': 'Nguyễn Hương'},
  'checklistSummary': {'totalRequired': 10, 'completedRequired': 7},
};

void main() {
  testWidgets(
    'task card communicates overdue, rework and sync without color only',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: HousekeepingTaskCard(
              task: TaskViewData(richTask()),
              sync: const TaskSyncSummary(conflict: 1),
              now: DateTime.parse('2026-08-05T10:00:00+07:00'),
              onTap: () {},
            ),
          ),
        ),
      );

      expect(find.textContaining('Quá hạn'), findsAtLeastNWidgets(1));
      expect(find.text('Quá hạn 1g 0p'), findsAtLeastNWidgets(1));
      expect(find.text('QC yêu cầu làm lại'), findsOneWidget);
      expect(find.text('Khách đang trong phòng'), findsOneWidget);
      expect(find.text('1 xung đột'), findsOneWidget);
      expect(
        tester
            .widget<LinearProgressIndicator>(
              find.byType(LinearProgressIndicator),
            )
            .semanticsValue,
        '70',
      );
    },
  );

  testWidgets('conflict screen shows base local server before resolution', (
    tester,
  ) async {
    final conflict = SyncConflict(
      receiptId: 'receipt-1',
      clientMutationId: 'mutation-1',
      taskId: 'task-1',
      operation: 'UPDATE_TASK_NOTE',
      payload: const {
        'baseSnapshot': {'note': 'Gốc'},
        'localOperation': {
          'payload': {'note': 'Local'},
        },
        'serverSnapshot': {'note': 'Server', 'version': 3},
      },
      createdAt: DateTime.utc(2026, 8, 5),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: ConflictResolutionSheet(conflict: conflict)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Dữ liệu gốc lúc làm offline'), findsOneWidget);
    expect(find.text('Thay đổi trên thiết bị'), findsOneWidget);
    await tester.drag(find.byType(ListView), const Offset(0, -700));
    await tester.pumpAndSettle();
    expect(find.text('Dữ liệu mới nhất trên server'), findsOneWidget);
    await tester.drag(find.byType(ListView), const Offset(0, -500));
    await tester.pumpAndSettle();
    expect(find.text('Bỏ thay đổi trên thiết bị'), findsOneWidget);
    expect(find.text('Áp dụng lại trên phiên bản server'), findsOneWidget);
  });

  testWidgets('typed checklist editor requires a reason for failed item', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: FilledButton(
              onPressed: () => showChecklistEditor(context, const {
                'id': 'item-1',
                'title': 'Kiểm tra nhiệt độ minibar',
                'group': 'Minibar',
                'type': 'NUMBER',
                'status': 'PENDING',
                'required': true,
                'validationRules': {'min': 2, 'max': 8},
              }),
              child: const Text('Mở editor'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Mở editor'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Không đạt'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Số lượng'), '12');
    await tester.tap(find.text('Lưu thay đổi offline'));
    await tester.pump();

    expect(find.text('Mục Không đạt phải có lý do.'), findsOneWidget);
  });
}
