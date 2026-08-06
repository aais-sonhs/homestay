import 'dart:convert';

import 'package:flutter/material.dart';

import '../offline/models.dart';
import '../presentation/task_presentation.dart';

Future<bool?> showConflictResolutionSheet(
  BuildContext context,
  SyncConflict conflict,
) => showModalBottomSheet<bool>(
  context: context,
  isScrollControlled: true,
  useSafeArea: true,
  builder: (context) => ConflictResolutionSheet(conflict: conflict),
);

class ConflictResolutionSheet extends StatelessWidget {
  const ConflictResolutionSheet({required this.conflict, super.key});

  final SyncConflict conflict;

  @override
  Widget build(BuildContext context) {
    final base = conflict.payload['baseSnapshot'];
    final local = conflict.payload['localOperation'];
    final server = conflict.payload['serverSnapshot'];
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: .88,
      minChildSize: .55,
      builder: (context, controller) => ListView(
        controller: controller,
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          Center(
            child: Container(
              width: 44,
              height: 4,
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.outlineVariant,
                borderRadius: BorderRadius.circular(99),
              ),
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Icon(
                Icons.sync_problem,
                color: Theme.of(context).colorScheme.error,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Xung đột dữ liệu',
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            '${viCodeLabel(conflict.operation)} · Công việc ${conflict.taskId}',
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.errorContainer,
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Text(
              'Máy chủ có phiên bản mới hơn. Ứng dụng chưa ghi đè bất kỳ dữ liệu nào. '
              'Hãy so sánh ba phần dưới đây trước khi chọn.',
            ),
          ),
          const SizedBox(height: 12),
          _SnapshotCard(
            icon: Icons.history,
            title: 'Dữ liệu gốc lúc làm ngoại tuyến',
            value: base,
          ),
          _SnapshotCard(
            icon: Icons.phone_android,
            title: 'Thay đổi trên thiết bị',
            value: local,
          ),
          _SnapshotCard(
            icon: Icons.cloud_outlined,
            title: 'Dữ liệu mới nhất trên máy chủ',
            value: server,
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: () => Navigator.pop(context, false),
            icon: const Icon(Icons.delete_outline),
            label: const Text('Bỏ thay đổi trên thiết bị'),
          ),
          const SizedBox(height: 8),
          FilledButton.icon(
            onPressed: server == null
                ? null
                : () => Navigator.pop(context, true),
            icon: const Icon(Icons.replay),
            label: const Text('Áp dụng lại trên phiên bản máy chủ'),
          ),
          const SizedBox(height: 8),
          Text(
            'Khi thử lại, ứng dụng dùng mã chống trùng mới; nếu máy chủ '
            'tiếp tục thay đổi, ứng dụng sẽ hiển thị xung đột mới.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}

class _SnapshotCard extends StatelessWidget {
  const _SnapshotCard({
    required this.icon,
    required this.title,
    required this.value,
  });

  final IconData icon;
  final String title;
  final Object? value;

  @override
  Widget build(BuildContext context) => Card(
    child: ExpansionTile(
      initiallyExpanded: true,
      leading: Icon(icon),
      title: Text(title),
      children: [
        Container(
          width: double.infinity,
          margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(10),
          ),
          child: SelectableText(
            const JsonEncoder.withIndent('  ').convert(localizedPayload(value)),
            style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
          ),
        ),
      ],
    ),
  );
}
