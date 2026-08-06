import 'package:flutter/material.dart';

import '../offline/models.dart';
import '../presentation/task_presentation.dart';

class HousekeepingTaskCard extends StatelessWidget {
  const HousekeepingTaskCard({
    required this.task,
    required this.sync,
    required this.onTap,
    this.now,
    super.key,
  });

  final TaskViewData task;
  final TaskSyncSummary sync;
  final VoidCallback onTap;
  final DateTime? now;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final overdue = task.isOverdue;
    final nearDue =
        !overdue && task.dueAt != null && task.dueDelta.inMinutes <= 15;
    final alertLabel = overdue
        ? 'Quá hạn'
        : task.isCheckinRisk
        ? 'Nguy cơ trễ giờ nhận phòng'
        : nearDue
        ? 'Sắp quá hạn'
        : task.status == 'WAITING_SUPPORT'
        ? 'Đang chờ hỗ trợ'
        : task.status == 'QC_REJECTED'
        ? 'Kiểm tra yêu cầu làm lại'
        : null;
    final borderColor = overdue || task.status == 'QC_REJECTED'
        ? colors.error
        : nearDue || task.isCheckinRisk || task.priority == 'URGENT'
        ? colors.tertiary
        : colors.outlineVariant;
    return Semantics(
      button: true,
      label:
          '${task.roomCode}, ${task.taskTypeLabel}, ${task.statusLabel}, '
          '${task.dueLabel(now: now)}, tiến độ ${task.progress} phần trăm',
      child: Card(
        clipBehavior: Clip.antiAlias,
        shape: RoundedRectangleBorder(
          side: BorderSide(
            color: borderColor,
            width: alertLabel == null ? 1 : 2,
          ),
          borderRadius: BorderRadius.circular(16),
        ),
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${task.roomCode} · ${task.code}',
                            style: Theme.of(context).textTheme.titleMedium
                                ?.copyWith(fontWeight: FontWeight.w800),
                          ),
                          Text(
                            [
                              task.roomName,
                              task.floor,
                              task.area,
                              task.branchName,
                            ].where((value) => value.isNotEmpty).join(' · '),
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ],
                      ),
                    ),
                    _StatusChip(label: task.statusLabel, status: task.status),
                  ],
                ),
                if (alertLabel != null) ...[
                  const SizedBox(height: 8),
                  _AlertBanner(
                    icon: overdue || task.status == 'QC_REJECTED'
                        ? Icons.error_outline
                        : Icons.warning_amber_rounded,
                    label: overdue
                        ? task.dueLabel(now: now)
                        : '$alertLabel · ${task.dueLabel(now: now)}',
                    severe: overdue || task.status == 'QC_REJECTED',
                  ),
                ],
                const SizedBox(height: 10),
                Wrap(
                  spacing: 12,
                  runSpacing: 6,
                  children: [
                    _Fact(
                      icon: Icons.cleaning_services,
                      label: task.taskTypeLabel,
                    ),
                    _Fact(
                      icon: Icons.schedule,
                      label: task.dueLabel(now: now),
                    ),
                    _Fact(
                      icon: Icons.person_outline,
                      label: task.assigneeName.isEmpty
                          ? 'Chưa có người nhận'
                          : task.assigneeName,
                    ),
                    _Fact(
                      icon: Icons.meeting_room_outlined,
                      label: 'Phòng ${task.roomStatusLabel}',
                    ),
                    if (task.nextCheckin != null)
                      _Fact(
                        icon: Icons.login,
                        label:
                            'Nhận phòng ${shortDateTime(task.raw['nextCheckinAt'])}',
                      ),
                  ],
                ),
                if (task.guestInRoom ||
                    task.specialRequest.isNotEmpty ||
                    task.status == 'QC_REJECTED') ...[
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 6,
                    children: [
                      if (task.guestInRoom)
                        const _WarningChip(
                          icon: Icons.person_pin_circle_outlined,
                          label: 'Khách đang trong phòng',
                        ),
                      if (task.specialRequest.isNotEmpty)
                        const _WarningChip(
                          icon: Icons.star_outline,
                          label: 'Có yêu cầu đặc biệt',
                        ),
                      if (task.status == 'QC_REJECTED')
                        const _WarningChip(
                          icon: Icons.replay,
                          label: 'Kiểm tra yêu cầu làm lại',
                        ),
                    ],
                  ),
                ],
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: LinearProgressIndicator(
                        value: task.progress.clamp(0, 100) / 100,
                        minHeight: 8,
                        borderRadius: BorderRadius.circular(99),
                        semanticsLabel: 'Tiến độ danh sách kiểm tra',
                        // Flutter parses progress-bar semantics as a number.
                        // Keep the spoken unit in the surrounding card label.
                        semanticsValue: '${task.progress}',
                      ),
                    ),
                    const SizedBox(width: 10),
                    Text('${task.progress}%'),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        '${task.checklistDone}/${task.checklistTotal} bắt buộc · '
                        '${task.photos} ảnh',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                    _SyncChip(summary: sync),
                  ],
                ),
                if (task.note.isNotEmpty) ...[
                  const Divider(height: 20),
                  Text(
                    task.note,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Fact extends StatelessWidget {
  const _Fact({required this.icon, required this.label});
  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Icon(icon, size: 16),
      const SizedBox(width: 4),
      Text(label, style: Theme.of(context).textTheme.bodySmall),
    ],
  );
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.label, required this.status});
  final String label;
  final String status;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final severe = status == 'QC_REJECTED';
    final support = {'PAUSED', 'WAITING_SUPPORT'}.contains(status);
    return Chip(
      visualDensity: VisualDensity.compact,
      avatar: Icon(
        severe
            ? Icons.replay
            : support
            ? Icons.pause_circle_outline
            : Icons.task_alt,
        size: 16,
      ),
      backgroundColor: severe
          ? colors.errorContainer
          : support
          ? colors.tertiaryContainer
          : colors.secondaryContainer,
      label: Text(label),
    );
  }
}

class _WarningChip extends StatelessWidget {
  const _WarningChip({required this.icon, required this.label});
  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) => Chip(
    visualDensity: VisualDensity.compact,
    avatar: Icon(icon, size: 16),
    label: Text(label),
  );
}

class _AlertBanner extends StatelessWidget {
  const _AlertBanner({
    required this.icon,
    required this.label,
    required this.severe,
  });
  final IconData icon;
  final String label;
  final bool severe;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Semantics(
      liveRegion: true,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
        decoration: BoxDecoration(
          color: severe ? colors.errorContainer : colors.tertiaryContainer,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          children: [
            Icon(icon, size: 18),
            const SizedBox(width: 7),
            Expanded(
              child: Text(
                label,
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SyncChip extends StatelessWidget {
  const _SyncChip({required this.summary});
  final TaskSyncSummary summary;

  @override
  Widget build(BuildContext context) {
    final bad = summary.failed > 0 || summary.conflict > 0;
    final pending = summary.pending > 0 || summary.syncing > 0;
    return Semantics(
      label: 'Trạng thái đồng bộ: ${summary.label}',
      child: Chip(
        visualDensity: VisualDensity.compact,
        avatar: Icon(
          bad
              ? Icons.sync_problem
              : pending
              ? Icons.cloud_upload_outlined
              : Icons.cloud_done_outlined,
          size: 16,
        ),
        label: Text(summary.label),
      ),
    );
  }
}
