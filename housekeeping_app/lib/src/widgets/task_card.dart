import 'package:flutter/material.dart';

import '../offline/models.dart';
import '../presentation/task_presentation.dart';
import '../theme/app_theme.dart';

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
    final overdue = task.isOverdue;
    final nearDue =
        !overdue && task.dueAt != null && task.dueDelta.inMinutes <= 15;
    final severe = overdue || task.status == 'QC_REJECTED';
    final warning = nearDue || task.isCheckinRisk || task.priority == 'URGENT';
    final accent = _statusColor(task.status, overdue: overdue);
    final alertLabel = overdue
        ? task.dueLabel(now: now)
        : task.isCheckinRisk
        ? 'Nguy cơ trễ giờ nhận phòng · ${task.dueLabel(now: now)}'
        : nearDue
        ? 'Sắp quá hạn · ${task.dueLabel(now: now)}'
        : task.status == 'WAITING_SUPPORT'
        ? 'Đang chờ hỗ trợ · ${task.dueLabel(now: now)}'
        : task.status == 'QC_REJECTED'
        ? 'Kiểm tra yêu cầu làm lại'
        : null;

    return Semantics(
      button: true,
      label:
          '${task.roomCode}, ${task.taskTypeLabel}, ${task.statusLabel}, '
          '${task.dueLabel(now: now)}, tiến độ ${task.progress} phần trăm',
      child: Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Card(
          clipBehavior: Clip.antiAlias,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(24),
            side: BorderSide(
              color: severe
                  ? const Color(0xfffecaca)
                  : warning
                  ? const Color(0xfffde68a)
                  : BlissAppTheme.line,
              width: severe || warning ? 1.4 : 1,
            ),
          ),
          child: InkWell(
            onTap: onTap,
            borderRadius: BorderRadius.circular(24),
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        width: 52,
                        height: 52,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color: accent.withValues(alpha: .1),
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: Icon(
                          _taskIcon(task.taskType),
                          color: accent,
                          size: 28,
                        ),
                      ),
                      const SizedBox(width: 13),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              task.roomCode.isEmpty
                                  ? task.code
                                  : 'Phòng ${task.roomCode}',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                color: BlissAppTheme.ink,
                                fontSize: 21,
                                height: 1.2,
                                fontWeight: FontWeight.w900,
                                letterSpacing: -.3,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              task.taskTypeLabel,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                color: Color(0xff45564c),
                                fontSize: 15,
                                height: 1.35,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      _StatusBadge(label: task.statusLabel, color: accent),
                    ],
                  ),
                  if (alertLabel != null) ...[
                    const SizedBox(height: 14),
                    _AlertBanner(
                      icon: severe
                          ? Icons.error_outline_rounded
                          : Icons.warning_amber_rounded,
                      label: alertLabel,
                      severe: severe,
                    ),
                  ],
                  const SizedBox(height: 15),
                  _InfoRow(
                    icon: Icons.schedule_rounded,
                    label: 'Thời hạn',
                    value: task.dueLabel(now: now),
                    color: overdue ? BlissAppTheme.danger : BlissAppTheme.brand,
                  ),
                  if (task.assigneeName.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    _InfoRow(
                      icon: Icons.person_outline_rounded,
                      label: 'Người thực hiện',
                      value: task.assigneeName,
                      color: const Color(0xff0284c7),
                    ),
                  ],
                  if (task.guestInRoom ||
                      task.specialRequest.isNotEmpty ||
                      task.status == 'QC_REJECTED') ...[
                    const SizedBox(height: 13),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        if (task.guestInRoom)
                          const _NoticePill(
                            icon: Icons.person_pin_circle_outlined,
                            label: 'Khách đang trong phòng',
                            color: BlissAppTheme.danger,
                          ),
                        if (task.specialRequest.isNotEmpty)
                          const _NoticePill(
                            icon: Icons.star_outline_rounded,
                            label: 'Có yêu cầu đặc biệt',
                            color: Color(0xffb45309),
                          ),
                        if (task.status == 'QC_REJECTED')
                          const _NoticePill(
                            icon: Icons.replay_rounded,
                            label: 'Kiểm tra yêu cầu làm lại',
                            color: BlissAppTheme.danger,
                          ),
                      ],
                    ),
                  ],
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      const Text(
                        'Tiến độ',
                        style: TextStyle(
                          color: BlissAppTheme.muted,
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const Spacer(),
                      Text(
                        '${task.progress}%',
                        style: TextStyle(
                          color: accent,
                          fontSize: 15,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(99),
                    child: LinearProgressIndicator(
                      value: task.progress.clamp(0, 100) / 100,
                      minHeight: 9,
                      color: accent,
                      backgroundColor: accent.withValues(alpha: .1),
                      semanticsLabel: 'Tiến độ danh sách kiểm tra',
                      semanticsValue: '${task.progress}',
                    ),
                  ),
                  const SizedBox(height: 15),
                  const Divider(height: 1),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: Wrap(
                          spacing: 12,
                          runSpacing: 8,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  Icons.check_circle_outline_rounded,
                                  size: 19,
                                  color: accent,
                                ),
                                const SizedBox(width: 6),
                                Text(
                                  '${task.checklistDone}/${task.checklistTotal} mục',
                                  style: const TextStyle(
                                    color: BlissAppTheme.muted,
                                    fontSize: 14,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ],
                            ),
                            _SyncBadge(summary: sync),
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      const Text(
                        'Mở',
                        style: TextStyle(
                          color: BlissAppTheme.brandDark,
                          fontSize: 15,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      const SizedBox(width: 3),
                      const Icon(
                        Icons.chevron_right_rounded,
                        size: 24,
                        color: BlissAppTheme.brand,
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

Color _statusColor(String status, {required bool overdue}) {
  if (overdue || status == 'QC_REJECTED') return BlissAppTheme.danger;
  return switch (status) {
    'QC_APPROVED' || 'COMPLETED' => const Color(0xff15803d),
    'WAITING_QC' => const Color(0xff7c3aed),
    'IN_PROGRESS' => const Color(0xff2563eb),
    'PAUSED' || 'WAITING_SUPPORT' => const Color(0xffb45309),
    'CANCELLED' => BlissAppTheme.muted,
    _ => BlissAppTheme.brand,
  };
}

IconData _taskIcon(String taskType) => switch (taskType) {
  'CHECKIN_PREPARATION' => Icons.hotel_rounded,
  'CHECKOUT_CLEANING' => Icons.logout_rounded,
  'STAYOVER_CLEANING' => Icons.bedroom_parent_outlined,
  'DEEP_CLEANING' => Icons.auto_awesome_rounded,
  'QC_REWORK' => Icons.replay_rounded,
  _ => Icons.cleaning_services_rounded,
};

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.label, required this.color});
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
    constraints: const BoxConstraints(maxWidth: 118),
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
    decoration: BoxDecoration(
      color: color.withValues(alpha: .1),
      borderRadius: BorderRadius.circular(999),
      border: Border.all(color: color.withValues(alpha: .2)),
    ),
    child: Text(
      label,
      maxLines: 2,
      overflow: TextOverflow.ellipsis,
      textAlign: TextAlign.center,
      style: TextStyle(
        color: color,
        fontSize: 13,
        height: 1.2,
        fontWeight: FontWeight.w900,
      ),
    ),
  );
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });
  final IconData icon;
  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Container(
        width: 38,
        height: 38,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: color.withValues(alpha: .1),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Icon(icon, color: color, size: 21),
      ),
      const SizedBox(width: 10),
      Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: const TextStyle(
                color: BlissAppTheme.muted,
                fontSize: 13,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 1),
            Text(
              value,
              style: TextStyle(
                color: color,
                fontSize: 16,
                height: 1.3,
                fontWeight: FontWeight.w900,
              ),
            ),
          ],
        ),
      ),
    ],
  );
}

class _NoticePill extends StatelessWidget {
  const _NoticePill({
    required this.icon,
    required this.label,
    required this.color,
  });
  final IconData icon;
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 8),
    decoration: BoxDecoration(
      color: color.withValues(alpha: .08),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 17, color: color),
        const SizedBox(width: 6),
        Flexible(
          child: Text(
            label,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: color,
              fontSize: 13,
              fontWeight: FontWeight.w900,
            ),
          ),
        ),
      ],
    ),
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
    final color = severe ? BlissAppTheme.danger : const Color(0xffb45309);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 11),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .08),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          Icon(icon, size: 21, color: color),
          const SizedBox(width: 9),
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                color: color,
                fontSize: 15,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SyncBadge extends StatelessWidget {
  const _SyncBadge({required this.summary});
  final TaskSyncSummary summary;

  @override
  Widget build(BuildContext context) {
    final bad = summary.failed > 0 || summary.conflict > 0;
    final pending = summary.pending > 0 || summary.syncing > 0;
    final color = bad
        ? BlissAppTheme.danger
        : pending
        ? const Color(0xffb45309)
        : const Color(0xff15803d);
    return Semantics(
      label: 'Trạng thái đồng bộ: ${summary.label}',
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            bad
                ? Icons.sync_problem_rounded
                : pending
                ? Icons.cloud_upload_outlined
                : Icons.cloud_done_outlined,
            size: 18,
            color: color,
          ),
          const SizedBox(width: 5),
          Text(
            summary.label,
            style: TextStyle(
              color: color,
              fontSize: 13,
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      ),
    );
  }
}
