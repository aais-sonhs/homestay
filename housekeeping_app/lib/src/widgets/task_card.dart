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
        padding: const EdgeInsets.only(bottom: 13),
        child: Card(
          clipBehavior: Clip.antiAlias,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(22),
            side: BorderSide(
              color: severe
                  ? const Color(0xfffecaca)
                  : warning
                  ? const Color(0xfffde68a)
                  : const Color(0xffe6eaf2),
            ),
          ),
          child: InkWell(
            onTap: onTap,
            child: Stack(
              children: [
                Positioned(
                  top: 0,
                  bottom: 0,
                  left: 0,
                  child: ColoredBox(
                    color: accent,
                    child: const SizedBox(width: 4),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(18, 17, 16, 15),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            width: 48,
                            height: 48,
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: accent.withValues(alpha: .1),
                              borderRadius: BorderRadius.circular(16),
                            ),
                            child: Icon(
                              _taskIcon(task.taskType),
                              color: accent,
                              size: 25,
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  '${task.roomCode} · ${task.code}',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                    color: Color(0xff172033),
                                    fontSize: 16,
                                    height: 1.25,
                                    fontWeight: FontWeight.w800,
                                    letterSpacing: -.2,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  [task.roomName, task.floor, task.area]
                                      .where((value) => value.isNotEmpty)
                                      .join(' · '),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(width: 8),
                          _StatusBadge(label: task.statusLabel, color: accent),
                        ],
                      ),
                      const SizedBox(height: 14),
                      Row(
                        children: [
                          Icon(
                            Icons.cleaning_services_rounded,
                            size: 18,
                            color: accent,
                          ),
                          const SizedBox(width: 7),
                          Expanded(
                            child: Text(
                              task.taskTypeLabel,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                color: Color(0xff334155),
                                fontSize: 13,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                          if (task.priority != 'NORMAL')
                            _PriorityBadge(priority: task.priority),
                        ],
                      ),
                      if (alertLabel != null) ...[
                        const SizedBox(height: 11),
                        _AlertBanner(
                          icon: severe
                              ? Icons.error_outline_rounded
                              : Icons.warning_amber_rounded,
                          label: alertLabel,
                          severe: severe,
                        ),
                      ],
                      const SizedBox(height: 13),
                      Row(
                        children: [
                          Expanded(
                            child: _FactTile(
                              icon: Icons.schedule_rounded,
                              label: 'Thời hạn',
                              value: task.dueLabel(now: now),
                              color: overdue
                                  ? const Color(0xffdc2626)
                                  : const Color(0xff4f46e5),
                            ),
                          ),
                          const SizedBox(width: 9),
                          Expanded(
                            child: _FactTile(
                              icon: Icons.person_outline_rounded,
                              label: 'Thực hiện',
                              value: task.assigneeName.isEmpty
                                  ? 'Chưa có người nhận'
                                  : task.assigneeName,
                              color: const Color(0xff0d9488),
                            ),
                          ),
                        ],
                      ),
                      if (task.guestInRoom ||
                          task.specialRequest.isNotEmpty ||
                          task.status == 'QC_REJECTED') ...[
                        const SizedBox(height: 11),
                        Wrap(
                          spacing: 7,
                          runSpacing: 7,
                          children: [
                            if (task.guestInRoom)
                              const _NoticePill(
                                icon: Icons.person_pin_circle_outlined,
                                label: 'Khách đang trong phòng',
                                color: Color(0xffdc2626),
                              ),
                            if (task.specialRequest.isNotEmpty)
                              const _NoticePill(
                                icon: Icons.star_outline_rounded,
                                label: 'Có yêu cầu đặc biệt',
                                color: Color(0xffd97706),
                              ),
                            if (task.status == 'QC_REJECTED')
                              const _NoticePill(
                                icon: Icons.replay_rounded,
                                label: 'Kiểm tra yêu cầu làm lại',
                                color: Color(0xffdc2626),
                              ),
                          ],
                        ),
                      ],
                      const SizedBox(height: 15),
                      Row(
                        children: [
                          const Text(
                            'Tiến độ',
                            style: TextStyle(
                              color: Color(0xff64748b),
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const Spacer(),
                          Text(
                            '${task.progress}%',
                            style: TextStyle(
                              color: accent,
                              fontSize: 12,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 7),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(99),
                        child: LinearProgressIndicator(
                          value: task.progress.clamp(0, 100) / 100,
                          minHeight: 8,
                          color: accent,
                          backgroundColor: accent.withValues(alpha: .1),
                          semanticsLabel: 'Tiến độ danh sách kiểm tra',
                          semanticsValue: '${task.progress}',
                        ),
                      ),
                      const SizedBox(height: 13),
                      Row(
                        children: [
                          _CompactFact(
                            icon: Icons.check_circle_outline_rounded,
                            text:
                                '${task.checklistDone}/${task.checklistTotal} mục',
                          ),
                          const SizedBox(width: 12),
                          _CompactFact(
                            icon: Icons.photo_outlined,
                            text: '${task.photos} ảnh',
                          ),
                          const Spacer(),
                          _SyncBadge(summary: sync),
                          const SizedBox(width: 4),
                          const Icon(
                            Icons.chevron_right_rounded,
                            size: 21,
                            color: Color(0xff94a3b8),
                          ),
                        ],
                      ),
                      if (task.note.isNotEmpty) ...[
                        const SizedBox(height: 12),
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(11),
                          decoration: BoxDecoration(
                            color: const Color(0xfff8fafc),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Text(
                            task.note,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

Color _statusColor(String status, {required bool overdue}) {
  if (overdue || status == 'QC_REJECTED') return const Color(0xffdc2626);
  return switch (status) {
    'QC_APPROVED' || 'COMPLETED' => const Color(0xff059669),
    'WAITING_QC' => const Color(0xff7c3aed),
    'IN_PROGRESS' => const Color(0xff2563eb),
    'PAUSED' || 'WAITING_SUPPORT' => const Color(0xffd97706),
    'CANCELLED' => const Color(0xff64748b),
    _ => const Color(0xff4f46e5),
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
    constraints: const BoxConstraints(maxWidth: 124),
    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
    decoration: BoxDecoration(
      color: color.withValues(alpha: .1),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Text(
      label,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w800),
    ),
  );
}

class _PriorityBadge extends StatelessWidget {
  const _PriorityBadge({required this.priority});
  final String priority;

  @override
  Widget build(BuildContext context) {
    final urgent = priority == 'URGENT';
    final color = urgent ? const Color(0xffdc2626) : const Color(0xffd97706);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .09),
        borderRadius: BorderRadius.circular(9),
      ),
      child: Text(
        viCodeLabel(priority),
        style: TextStyle(
          color: color,
          fontSize: 9,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

class _FactTile extends StatelessWidget {
  const _FactTile({
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
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(11),
    decoration: BoxDecoration(
      color: const Color(0xfff8fafc),
      borderRadius: BorderRadius.circular(14),
      border: Border.all(color: const Color(0xffedf0f5)),
    ),
    child: Row(
      children: [
        Container(
          width: 31,
          height: 31,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: color.withValues(alpha: .1),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(icon, color: color, size: 17),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: const TextStyle(
                  color: Color(0xff94a3b8),
                  fontSize: 9,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 1),
              Text(
                value,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: Color(0xff334155),
                  fontSize: 10,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
        ),
      ],
    ),
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
    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
    decoration: BoxDecoration(
      color: color.withValues(alpha: .08),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 14, color: color),
        const SizedBox(width: 5),
        Text(
          label,
          style: TextStyle(
            color: color,
            fontSize: 9,
            fontWeight: FontWeight.w800,
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
    final color = severe ? const Color(0xffdc2626) : const Color(0xffd97706);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 9),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .08),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Icon(icon, size: 17, color: color),
          const SizedBox(width: 7),
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                color: color,
                fontSize: 11,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _CompactFact extends StatelessWidget {
  const _CompactFact({required this.icon, required this.text});
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Icon(icon, size: 15, color: const Color(0xff64748b)),
      const SizedBox(width: 4),
      Text(
        text,
        style: const TextStyle(
          color: Color(0xff64748b),
          fontSize: 10,
          fontWeight: FontWeight.w700,
        ),
      ),
    ],
  );
}

class _SyncBadge extends StatelessWidget {
  const _SyncBadge({required this.summary});
  final TaskSyncSummary summary;

  @override
  Widget build(BuildContext context) {
    final bad = summary.failed > 0 || summary.conflict > 0;
    final pending = summary.pending > 0 || summary.syncing > 0;
    final color = bad
        ? const Color(0xffdc2626)
        : pending
        ? const Color(0xffd97706)
        : const Color(0xff059669);
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
            size: 15,
            color: color,
          ),
          const SizedBox(width: 4),
          Text(
            summary.label,
            style: TextStyle(
              color: color,
              fontSize: 9,
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      ),
    );
  }
}
