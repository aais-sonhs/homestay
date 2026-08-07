import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../api/housekeeping_api.dart';
import '../presentation/task_presentation.dart';
import '../security/secure_store.dart';
import 'offline_task_detail_screen.dart';

class ManagementDashboardScreen extends StatefulWidget {
  const ManagementDashboardScreen({
    required this.api,
    required this.user,
    required this.onOpenTasks,
    required this.onOpenQc,
    required this.onOpenStaff,
    required this.onSignOut,
    super.key,
  });

  final HousekeepingApi api;
  final AppUserProfile user;
  final VoidCallback onOpenTasks;
  final VoidCallback onOpenQc;
  final VoidCallback onOpenStaff;
  final AsyncCallback onSignOut;

  @override
  State<ManagementDashboardScreen> createState() =>
      _ManagementDashboardScreenState();
}

class _ManagementDashboardScreenState extends State<ManagementDashboardScreen> {
  Map<String, Object?> _sla = const {};
  Map<String, Object?> _performance = const {};
  bool _loading = true;
  String? _error;

  Map get _summary => _sla['summary'] as Map? ?? const {};
  List<Map<String, Object?>> get _riskTasks =>
      (_sla['tasks'] as List? ?? const [])
          .whereType<Map>()
          .map((row) => Map<String, Object?>.from(row))
          .toList(growable: false);
  List<Map<String, Object?>> get _performanceRows =>
      (_performance['rows'] as List? ?? const [])
          .whereType<Map>()
          .map((row) => Map<String, Object?>.from(row))
          .toList(growable: false);

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (mounted) setState(() => _loading = true);
    try {
      final date = TaskFilters.dateOnly(DateTime.now());
      final result = await Future.wait([
        widget.api.slaDashboard(date: date),
        widget.api.performanceDashboard(date: date),
      ]);
      _sla = result[0];
      _performance = result[1];
      _error = null;
    } on Object catch (error) {
      _error = 'Không tải được dashboard: $error';
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  int _count(String key) => (_summary[key] as num?)?.toInt() ?? 0;

  Future<void> _openTask(String taskId) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => OnlineTaskDetailScreen(taskId: taskId, api: widget.api),
      ),
    );
    await _load();
  }

  Future<void> _confirmSignOut() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Đăng xuất?'),
        content: const Text('Phiên đăng nhập trên thiết bị sẽ được xóa.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Ở lại'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Đăng xuất'),
          ),
        ],
      ),
    );
    if (confirmed == true) await widget.onSignOut();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Tổng quan vận hành'),
      actions: [
        IconButton(
          tooltip: 'Tải lại',
          onPressed: _loading ? null : _load,
          icon: const Icon(Icons.refresh),
        ),
        PopupMenuButton<String>(
          tooltip: 'Tài khoản',
          icon: const Icon(Icons.account_circle_outlined),
          onSelected: (value) {
            if (value == 'logout') unawaited(_confirmSignOut());
          },
          itemBuilder: (_) => [
            PopupMenuItem(
              enabled: false,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    widget.user.name,
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                  Text(widget.user.roleLabel),
                ],
              ),
            ),
            const PopupMenuDivider(),
            const PopupMenuItem(value: 'logout', child: Text('Đăng xuất')),
          ],
        ),
      ],
      bottom: _loading
          ? const PreferredSize(
              preferredSize: Size.fromHeight(3),
              child: LinearProgressIndicator(),
            )
          : null,
    ),
    body: RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
        children: [
          _WelcomeCard(user: widget.user),
          if (_error != null) ...[
            const SizedBox(height: 12),
            _ErrorCard(message: _error!, onRetry: _load),
          ],
          const SizedBox(height: 20),
          Text(
            'Hôm nay cần chú ý',
            style: Theme.of(
              context,
            ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 12),
          LayoutBuilder(
            builder: (context, constraints) {
              final width = (constraints.maxWidth - 12) / 2;
              return Wrap(
                spacing: 12,
                runSpacing: 12,
                children: [
                  _DashboardMetric(
                    width: width,
                    label: 'Tổng công việc',
                    value: _count('totalTasks'),
                    icon: Icons.assignment_outlined,
                    color: const Color(0xff4f46e5),
                  ),
                  _DashboardMetric(
                    width: width,
                    label: 'Đang xử lý',
                    value: _count('inProgress'),
                    icon: Icons.play_circle_outline,
                    color: const Color(0xff2563eb),
                  ),
                  _DashboardMetric(
                    width: width,
                    label: 'Quá hạn',
                    value: _count('overdue'),
                    icon: Icons.warning_amber_rounded,
                    color: const Color(0xffef4444),
                  ),
                  _DashboardMetric(
                    width: width,
                    label: 'Rủi ro check-in',
                    value: _count('checkinRisk'),
                    icon: Icons.hotel_outlined,
                    color: const Color(0xfff59e0b),
                  ),
                ],
              );
            },
          ),
          const SizedBox(height: 20),
          _QuickActions(
            onOpenTasks: widget.onOpenTasks,
            onOpenQc: widget.onOpenQc,
            onOpenStaff: widget.onOpenStaff,
            showStaff:
                widget.user.role == 'branch_owner' ||
                widget.user.role == 'manager',
            waitingQc:
                (_summary['byStatus'] as Map?)?['WAITING_QC'] as int? ?? 0,
          ),
          const SizedBox(height: 20),
          _SectionHeader(
            title: 'Công việc rủi ro',
            actionLabel: 'Xem công việc',
            onAction: widget.onOpenTasks,
          ),
          const SizedBox(height: 10),
          if (_riskTasks.isEmpty)
            const _EmptyCard(
              icon: Icons.verified_outlined,
              text: 'Không có công việc quá hạn hoặc rủi ro check-in.',
            )
          else
            Card(
              child: Column(
                children: [
                  for (
                    var index = 0;
                    index < _riskTasks.length && index < 5;
                    index++
                  ) ...[
                    _RiskTaskTile(
                      row: _riskTasks[index],
                      onTap: () => _openTask('${_riskTasks[index]['taskId']}'),
                    ),
                    if (index < _riskTasks.length - 1 && index < 4)
                      const Divider(height: 1),
                  ],
                ],
              ),
            ),
          const SizedBox(height: 20),
          const _SectionHeader(title: 'Hiệu suất trong ngày'),
          const SizedBox(height: 10),
          if (_performanceRows.isEmpty)
            const _EmptyCard(
              icon: Icons.insights_outlined,
              text: 'Chưa có dữ liệu hiệu suất trong ngày.',
            )
          else
            Card(
              child: Column(
                children: [
                  for (
                    var index = 0;
                    index < _performanceRows.length && index < 4;
                    index++
                  ) ...[
                    _PerformanceTile(row: _performanceRows[index]),
                    if (index < _performanceRows.length - 1 && index < 3)
                      const Divider(height: 1),
                  ],
                ],
              ),
            ),
        ],
      ),
    ),
  );
}

class _WelcomeCard extends StatelessWidget {
  const _WelcomeCard({required this.user});
  final AppUserProfile user;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(22),
      gradient: const LinearGradient(
        colors: [Color(0xff4338ca), Color(0xff7c3aed)],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
      boxShadow: const [
        BoxShadow(
          color: Color(0x334f46e5),
          blurRadius: 28,
          offset: Offset(0, 14),
        ),
      ],
    ),
    child: Row(
      children: [
        Container(
          width: 52,
          height: 52,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: .18),
            borderRadius: BorderRadius.circular(17),
            border: Border.all(color: Colors.white.withValues(alpha: .24)),
          ),
          child: Text(
            user.name.isEmpty ? 'B' : user.name.characters.first.toUpperCase(),
            style: const TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.w800,
            ),
          ),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Chào ngày mới,',
                style: TextStyle(color: Color(0xffddd6fe)),
              ),
              const SizedBox(height: 2),
              Text(
                user.name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                ),
              ),
              Text(
                user.roleLabel,
                style: const TextStyle(color: Color(0xffe0e7ff)),
              ),
            ],
          ),
        ),
        const Icon(Icons.auto_graph_rounded, color: Colors.white, size: 30),
      ],
    ),
  );
}

class _DashboardMetric extends StatelessWidget {
  const _DashboardMetric({
    required this.width,
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
  });
  final double width;
  final String label;
  final int value;
  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
    width: width,
    constraints: const BoxConstraints(minHeight: 142),
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(20),
      gradient: LinearGradient(
        colors: [color.withValues(alpha: .14), Colors.white],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
      border: Border.all(color: color.withValues(alpha: .14)),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 42,
          height: 42,
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: .82),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Icon(icon, color: color),
        ),
        const Spacer(),
        Text(
          '$value',
          style: const TextStyle(
            color: Color(0xff111827),
            fontSize: 30,
            height: 1,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          label,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: color,
            fontSize: 12,
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    ),
  );
}

class _QuickActions extends StatelessWidget {
  const _QuickActions({
    required this.onOpenTasks,
    required this.onOpenQc,
    required this.onOpenStaff,
    required this.showStaff,
    required this.waitingQc,
  });
  final VoidCallback onOpenTasks;
  final VoidCallback onOpenQc;
  final VoidCallback onOpenStaff;
  final bool showStaff;
  final int waitingQc;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          Expanded(
            child: _ActionButton(
              icon: Icons.assignment_outlined,
              label: 'Điều phối việc',
              color: const Color(0xff2563eb),
              onTap: onOpenTasks,
            ),
          ),
          if (showStaff) ...[
            const SizedBox(width: 12),
            Expanded(
              child: _ActionButton(
                icon: Icons.groups_2_outlined,
                label: 'Nhân sự',
                color: const Color(0xff0d9488),
                onTap: onOpenStaff,
              ),
            ),
          ],
          const SizedBox(width: 12),
          Expanded(
            child: _ActionButton(
              icon: Icons.fact_check_outlined,
              label: 'Chờ QC${waitingQc > 0 ? ' · $waitingQc' : ''}',
              color: const Color(0xff7c3aed),
              onTap: onOpenQc,
            ),
          ),
        ],
      ),
    ),
  );
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => InkWell(
    borderRadius: BorderRadius.circular(16),
    onTap: onTap,
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 14),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .08),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        children: [
          Icon(icon, color: color, size: 28),
          const SizedBox(height: 7),
          Text(
            label,
            textAlign: TextAlign.center,
            style: TextStyle(color: color, fontWeight: FontWeight.w700),
          ),
        ],
      ),
    ),
  );
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({this.title = '', this.actionLabel, this.onAction});
  final String title;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Expanded(
        child: Text(
          title,
          style: Theme.of(
            context,
          ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800),
        ),
      ),
      if (actionLabel != null)
        TextButton(onPressed: onAction, child: Text(actionLabel!)),
    ],
  );
}

class _RiskTaskTile extends StatelessWidget {
  const _RiskTaskTile({required this.row, required this.onTap});
  final Map<String, Object?> row;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final room = row['room'] as Map? ?? const {};
    final assignee = row['assignee'] as Map? ?? const {};
    final overdue = row['overdue'] == true;
    final checkinRisk = row['checkinRisk'] == true;
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
      leading: Container(
        width: 44,
        height: 44,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: overdue ? const Color(0xfffef2f2) : const Color(0xfffffbeb),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Icon(
          overdue ? Icons.timer_off_outlined : Icons.hotel_outlined,
          color: overdue ? const Color(0xffdc2626) : const Color(0xffd97706),
        ),
      ),
      title: Text(
        '${room['code'] ?? 'Phòng'} · ${row['taskCode'] ?? ''}',
        style: const TextStyle(fontWeight: FontWeight.w800),
      ),
      subtitle: Text(
        '${row['statusLabel'] ?? viCodeLabel(row['status'])}'
        ' · ${assignee['name'] ?? 'Chưa giao'}\n'
        '${overdue ? 'Quá hạn ${(row['overdueMinutes'] as num?)?.toInt() ?? 0} phút' : ''}'
        '${overdue && checkinRisk ? ' · ' : ''}'
        '${checkinRisk ? 'Nguy cơ trễ check-in' : ''}',
      ),
      isThreeLine: true,
      trailing: const Icon(Icons.chevron_right),
      onTap: onTap,
    );
  }
}

class _PerformanceTile extends StatelessWidget {
  const _PerformanceTile({required this.row});
  final Map<String, Object?> row;

  @override
  Widget build(BuildContext context) {
    final employee = row['employee'] as Map? ?? const {};
    final branch = row['branch'] as Map? ?? const {};
    final completion = (row['completionRatePercent'] as num?)?.round() ?? 0;
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 5),
      leading: CircleAvatar(
        backgroundColor: const Color(0xffeef2ff),
        foregroundColor: const Color(0xff4f46e5),
        child: Text(
          '${employee['name'] ?? '?'}'.characters.first.toUpperCase(),
        ),
      ),
      title: Text(
        '${employee['name'] ?? 'Chưa phân công'}',
        style: const TextStyle(fontWeight: FontWeight.w700),
      ),
      subtitle: Text(
        '${branch['name'] ?? ''} · ${row['taskCount'] ?? 0} công việc',
      ),
      trailing: Text(
        '$completion%',
        style: const TextStyle(
          color: Color(0xff059669),
          fontSize: 16,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

class _EmptyCard extends StatelessWidget {
  const _EmptyCard({required this.icon, required this.text});
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(22),
      child: Row(
        children: [
          Icon(icon, color: const Color(0xff059669)),
          const SizedBox(width: 12),
          Expanded(child: Text(text)),
        ],
      ),
    ),
  );
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.message, required this.onRetry});
  final String message;
  final AsyncCallback onRetry;

  @override
  Widget build(BuildContext context) => Card(
    color: Theme.of(context).colorScheme.errorContainer,
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Row(
        children: [
          const Icon(Icons.cloud_off_outlined),
          const SizedBox(width: 10),
          Expanded(child: Text(message)),
          IconButton(onPressed: onRetry, icon: const Icon(Icons.refresh)),
        ],
      ),
    ),
  );
}
