import 'dart:async';

import 'package:flutter/material.dart';

import '../api/housekeeping_api.dart';
import '../presentation/task_presentation.dart';
import '../security/secure_store.dart';
import '../theme/app_theme.dart';
import 'offline_task_detail_screen.dart';

enum _HomeTaskFilter { all, inProgress, done, overdue }

class HousekeepingHomeScreen extends StatefulWidget {
  const HousekeepingHomeScreen({
    required this.api,
    required this.user,
    required this.onOpenTasks,
    required this.onOpenRequests,
    required this.onReportIssue,
    required this.onOpenNotifications,
    required this.onOpenProfile,
    this.active = true,
    super.key,
  });

  final HousekeepingApi api;
  final AppUserProfile user;
  final VoidCallback onOpenTasks;
  final VoidCallback onOpenRequests;
  final VoidCallback onReportIssue;
  final VoidCallback onOpenNotifications;
  final VoidCallback onOpenProfile;
  final bool active;

  @override
  State<HousekeepingHomeScreen> createState() => _HousekeepingHomeScreenState();
}

class _HousekeepingHomeScreenState extends State<HousekeepingHomeScreen> {
  List<TaskViewData> _tasks = const [];
  _HomeTaskFilter _filter = _HomeTaskFilter.all;
  Timer? _poller;
  bool _loading = true;
  int _unreadNotifications = 0;
  int _generation = 0;
  String? _error;

  @override
  void initState() {
    super.initState();
    if (widget.active) {
      _load();
      _startPolling();
    }
  }

  @override
  void didUpdateWidget(covariant HousekeepingHomeScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.active == widget.active) return;
    if (widget.active) {
      _load();
      _startPolling();
    } else {
      _generation++;
      _poller?.cancel();
      _poller = null;
    }
  }

  void _startPolling() {
    _poller?.cancel();
    _poller = Timer.periodic(const Duration(seconds: 30), (_) {
      if (widget.active) _load(silent: true);
    });
  }

  Future<void> _load({bool silent = false}) async {
    final generation = ++_generation;
    if (!silent && mounted) setState(() => _loading = true);
    try {
      final rows = await widget.api.tasks(
        filters: {
          'assignee': 'me',
          'date': TaskFilters.dateOnly(DateTime.now()),
        },
      );
      if (!mounted || generation != _generation) return;
      final tasks = rows.map(TaskViewData.new).toList(growable: false)
        ..sort(_compareTasks);
      setState(() {
        _tasks = tasks;
        _loading = false;
        _error = null;
      });
    } on Object catch (error) {
      if (!mounted || generation != _generation) return;
      setState(() {
        _loading = false;
        _error = 'Không tải được công việc hôm nay: $error';
      });
    }

    try {
      final result = await widget.api.notifications(unread: true);
      if (mounted && generation == _generation) {
        setState(
          () => _unreadNotifications = result['unreadCount'] as int? ?? 0,
        );
      }
    } on Object {
      // Trang chủ vẫn dùng được nếu số thông báo tạm thời chưa tải được.
    }
  }

  static int _compareTasks(TaskViewData left, TaskViewData right) {
    int rank(TaskViewData task) {
      if (_isOverdue(task)) return 0;
      if (task.priority == 'URGENT') return 1;
      if (task.priority == 'HIGH') return 2;
      if (_isInProgress(task)) return 3;
      if (_isDone(task)) return 5;
      return 4;
    }

    final rankComparison = rank(left).compareTo(rank(right));
    if (rankComparison != 0) return rankComparison;
    final leftDue = left.dueAt ?? DateTime(9999);
    final rightDue = right.dueAt ?? DateTime(9999);
    return leftDue.compareTo(rightDue);
  }

  static bool _isDone(TaskViewData task) =>
      const {'COMPLETED', 'WAITING_QC', 'QC_APPROVED'}.contains(task.status);

  static bool _isInProgress(TaskViewData task) =>
      const {'IN_PROGRESS', 'PAUSED', 'WAITING_SUPPORT'}.contains(task.status);

  static bool _isOverdue(TaskViewData task) =>
      task.isOverdue && !_isDone(task) && task.status != 'CANCELLED';

  List<TaskViewData> get _visibleTasks => switch (_filter) {
    _HomeTaskFilter.all => _tasks,
    _HomeTaskFilter.inProgress => _tasks.where(_isInProgress).toList(),
    _HomeTaskFilter.done => _tasks.where(_isDone).toList(),
    _HomeTaskFilter.overdue => _tasks.where(_isOverdue).toList(),
  };

  Future<void> _openTask(TaskViewData task) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) =>
            OnlineTaskDetailScreen(taskId: task.id, api: widget.api),
      ),
    );
    if (mounted) await _load();
  }

  void _showShift() {
    final shift = _shiftSummary(_tasks);
    showModalBottomSheet<void>(
      context: context,
      builder: (context) => Padding(
        padding: const EdgeInsets.fromLTRB(22, 4, 22, 30),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Lịch ca hôm nay',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 14),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const CircleAvatar(
                backgroundColor: BlissAppTheme.brandSoft,
                child: Icon(Icons.calendar_month_rounded),
              ),
              title: Text(shift.title),
              subtitle: Text(shift.timeLabel),
            ),
          ],
        ),
      ),
    );
  }

  void _showPolicies() {
    showModalBottomSheet<void>(
      context: context,
      builder: (context) => const Padding(
        padding: EdgeInsets.fromLTRB(22, 4, 22, 30),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Quy trình làm việc',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900),
            ),
            SizedBox(height: 15),
            _PolicyRow(
              icon: Icons.qr_code_scanner_rounded,
              text: 'Xác minh đúng phòng trước khi bắt đầu.',
            ),
            _PolicyRow(
              icon: Icons.fact_check_outlined,
              text: 'Hoàn tất đủ checklist và ảnh bắt buộc.',
            ),
            _PolicyRow(
              icon: Icons.report_problem_outlined,
              text: 'Báo ngay sự cố hoặc vật tư thiếu để được hỗ trợ.',
            ),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    _poller?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final done = _tasks.where(_isDone).length;
    final remaining = _tasks
        .where((task) => !_isDone(task) && task.status != 'CANCELLED')
        .length;
    final shift = _shiftSummary(_tasks);
    final estimatedIncome = _estimatedIncome(_tasks);
    final visibleTasks = _visibleTasks;

    return Scaffold(
      backgroundColor: const Color(0xfff7f9f7),
      body: SafeArea(
        bottom: false,
        child: RefreshIndicator(
          onRefresh: _load,
          child: CustomScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                  child: _HomeHeader(
                    user: widget.user,
                    shift: shift,
                    unreadNotifications: _unreadNotifications,
                    onNotifications: widget.onOpenNotifications,
                    onProfile: widget.onOpenProfile,
                  ),
                ),
              ),
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: IntrinsicHeight(
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Expanded(
                          flex: 3,
                          child: _WorkSummaryCard(
                            total: _tasks.length,
                            done: done,
                            remaining: remaining,
                            loading: _loading,
                            onTap: widget.onOpenTasks,
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          flex: 2,
                          child: _IncomeCard(
                            amount: estimatedIncome,
                            onTap: widget.onOpenTasks,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
                  child: _ShortcutPanel(
                    onTasks: widget.onOpenTasks,
                    onShift: _showShift,
                    onReport: widget.onReportIssue,
                    onRequests: widget.onOpenRequests,
                    onPolicies: _showPolicies,
                  ),
                ),
              ),
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                  child: _TaskTabs(
                    selected: _filter,
                    total: _tasks.length,
                    inProgress: _tasks.where(_isInProgress).length,
                    done: done,
                    overdue: _tasks.where(_isOverdue).length,
                    onSelected: (value) => setState(() => _filter = value),
                  ),
                ),
              ),
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(19, 12, 19, 8),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      const Text(
                        'Sắp xếp: Ưu tiên',
                        style: TextStyle(
                          color: BlissAppTheme.muted,
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(width: 5),
                      Icon(
                        Icons.tune_rounded,
                        size: 20,
                        color: Theme.of(context).colorScheme.onSurface,
                      ),
                    ],
                  ),
                ),
              ),
              if (_error != null)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
                    child: _HomeError(message: _error!, onRetry: _load),
                  ),
                ),
              if (_loading && _tasks.isEmpty)
                const SliverToBoxAdapter(
                  child: Padding(
                    padding: EdgeInsets.all(36),
                    child: Center(child: CircularProgressIndicator()),
                  ),
                )
              else if (visibleTasks.isEmpty)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.all(26),
                    child: Center(
                      child: Text(
                        'Chưa có công việc trong nhóm này.',
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                    ),
                  ),
                )
              else
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
                  sliver: SliverList.builder(
                    itemCount: visibleTasks.length,
                    itemBuilder: (context, index) => _CompactTaskCard(
                      task: visibleTasks[index],
                      onTap: () => _openTask(visibleTasks[index]),
                    ),
                  ),
                ),
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 22),
                  child: _SupportBanner(onTap: widget.onReportIssue),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ShiftSummary {
  const _ShiftSummary({
    required this.title,
    required this.timeLabel,
    required this.working,
  });

  final String title;
  final String timeLabel;
  final bool working;
}

_ShiftSummary _shiftSummary(List<TaskViewData> tasks) {
  for (final task in tasks) {
    final shift = task.shift;
    if (shift.isEmpty) continue;
    final start = DateTime.tryParse('${shift['startsAt'] ?? ''}')?.toLocal();
    final end = DateTime.tryParse('${shift['endsAt'] ?? ''}')?.toLocal();
    final now = DateTime.now();
    return _ShiftSummary(
      title: '${shift['name'] ?? 'Ca làm hôm nay'}',
      timeLabel: start != null && end != null
          ? '${_clock(start)} – ${_clock(end)}'
          : 'Theo lịch phân công',
      working:
          start != null &&
          end != null &&
          !now.isBefore(start) &&
          !now.isAfter(end),
    );
  }
  return _ShiftSummary(
    title: 'Ca làm hôm nay',
    timeLabel: tasks.isEmpty ? 'Chưa có lịch phân công' : 'Theo lịch công việc',
    working: tasks.isNotEmpty,
  );
}

int? _estimatedIncome(List<TaskViewData> tasks) {
  var found = false;
  var total = 0;
  for (final task in tasks) {
    final value =
        task.raw['estimatedIncome'] ??
        task.raw['estimatedPay'] ??
        task.raw['taskPay'];
    if (value is num) {
      total += value.round();
      found = true;
    }
  }
  return found ? total : null;
}

String _clock(DateTime value) =>
    '${value.hour.toString().padLeft(2, '0')}:'
    '${value.minute.toString().padLeft(2, '0')}';

String _money(int value) {
  final digits = value.toString();
  final output = StringBuffer();
  for (var index = 0; index < digits.length; index++) {
    if (index > 0 && (digits.length - index) % 3 == 0) output.write('.');
    output.write(digits[index]);
  }
  return '$output\u0111';
}

class _HomeHeader extends StatelessWidget {
  const _HomeHeader({
    required this.user,
    required this.shift,
    required this.unreadNotifications,
    required this.onNotifications,
    required this.onProfile,
  });

  final AppUserProfile user;
  final _ShiftSummary shift;
  final int unreadNotifications;
  final VoidCallback onNotifications;
  final VoidCallback onProfile;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Container(
        width: 54,
        height: 54,
        padding: const EdgeInsets.all(3),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(17),
          border: Border.all(color: BlissAppTheme.line),
          boxShadow: const [
            BoxShadow(
              color: Color(0x120f172a),
              blurRadius: 14,
              offset: Offset(0, 4),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(13),
          child: Image.asset('assets/branding/app_icon.png', fit: BoxFit.cover),
        ),
      ),
      const SizedBox(width: 11),
      Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Bliss Home',
              style: TextStyle(
                color: BlissAppTheme.brandDark,
                fontSize: 21,
                height: 1.1,
                fontWeight: FontWeight.w900,
                letterSpacing: -.5,
              ),
            ),
            const SizedBox(height: 3),
            Text(
              '${shift.title} ${shift.timeLabel}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: Color(0xff475569),
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 4),
            Row(
              children: [
                Container(
                  width: 7,
                  height: 7,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: shift.working
                        ? const Color(0xff22c55e)
                        : BlissAppTheme.muted,
                  ),
                ),
                const SizedBox(width: 5),
                Text(
                  shift.working ? 'Đang làm việc' : 'Chưa vào ca',
                  style: const TextStyle(
                    color: BlissAppTheme.muted,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
      Badge(
        isLabelVisible: unreadNotifications > 0,
        label: Text('$unreadNotifications'),
        child: IconButton(
          tooltip: 'Thông báo',
          onPressed: onNotifications,
          icon: const Icon(Icons.notifications_none_rounded, size: 29),
        ),
      ),
      const SizedBox(width: 3),
      IconButton.filledTonal(
        tooltip: 'Cá nhân',
        onPressed: onProfile,
        icon: const Icon(Icons.person_rounded),
      ),
    ],
  );
}

class _WorkSummaryCard extends StatelessWidget {
  const _WorkSummaryCard({
    required this.total,
    required this.done,
    required this.remaining,
    required this.loading,
    required this.onTap,
  });

  final int total;
  final int done;
  final int remaining;
  final bool loading;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Material(
    color: Colors.transparent,
    child: InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(22),
      child: Ink(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(22),
          gradient: const LinearGradient(
            colors: [Color(0xff047857), Color(0xff115e59)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 32,
                  height: 32,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: .14),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(
                    Icons.assignment_turned_in_outlined,
                    color: Colors.white,
                    size: 20,
                  ),
                ),
                const SizedBox(width: 8),
                const Expanded(
                  child: Text(
                    'Công việc hôm nay',
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 12,
                      height: 1.15,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 7),
            Row(
              children: [
                Expanded(
                  child: Text(
                    loading ? 'Đang tải…' : '$total việc',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 21,
                      height: 1,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                ),
                _SummaryNumber(value: done, label: 'Đã xong'),
                _SummaryNumber(value: remaining, label: 'Còn lại'),
              ],
            ),
          ],
        ),
      ),
    ),
  );
}

class _SummaryNumber extends StatelessWidget {
  const _SummaryNumber({required this.value, required this.label});
  final int value;
  final String label;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: 50,
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          '$value',
          style: const TextStyle(
            color: Colors.white,
            fontSize: 16,
            height: 1,
            fontWeight: FontWeight.w900,
          ),
        ),
        Text(
          label,
          maxLines: 1,
          style: const TextStyle(
            color: Color(0xffd1fae5),
            fontSize: 9,
            height: 1.2,
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    ),
  );
}

class _IncomeCard extends StatelessWidget {
  const _IncomeCard({required this.amount, required this.onTap});
  final int? amount;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Card(
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(22),
      side: const BorderSide(color: BlissAppTheme.line),
    ),
    child: InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(22),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(11, 10, 10, 9),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Thu nhập ước tính',
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 13,
                height: 1.2,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              amount == null ? '—' : _money(amount!),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: BlissAppTheme.brandDark,
                fontSize: 19,
                fontWeight: FontWeight.w900,
                letterSpacing: -.5,
              ),
            ),
            const SizedBox(height: 3),
            Text(
              amount == null ? 'Chưa có dữ liệu' : 'Xem chi tiết  ›',
              style: const TextStyle(
                color: BlissAppTheme.brandDark,
                fontSize: 10,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

class _ShortcutPanel extends StatelessWidget {
  const _ShortcutPanel({
    required this.onTasks,
    required this.onShift,
    required this.onReport,
    required this.onRequests,
    required this.onPolicies,
  });

  final VoidCallback onTasks;
  final VoidCallback onShift;
  final VoidCallback onReport;
  final VoidCallback onRequests;
  final VoidCallback onPolicies;

  @override
  Widget build(BuildContext context) => Card(
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(20),
      side: const BorderSide(color: BlissAppTheme.line),
    ),
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 13),
      child: Row(
        children: [
          _Shortcut(
            icon: Icons.assignment_outlined,
            label: 'Tất cả việc',
            color: BlissAppTheme.brand,
            onTap: onTasks,
          ),
          _Shortcut(
            icon: Icons.calendar_month_outlined,
            label: 'Lịch ca',
            color: const Color(0xff059669),
            onTap: onShift,
          ),
          _Shortcut(
            icon: Icons.chat_bubble_outline_rounded,
            label: 'Báo vấn đề',
            color: const Color(0xff7c3aed),
            onTap: onReport,
          ),
          _Shortcut(
            icon: Icons.inventory_2_outlined,
            label: 'Yêu cầu đồ',
            color: const Color(0xfff59e0b),
            onTap: onRequests,
          ),
          _Shortcut(
            icon: Icons.policy_outlined,
            label: 'Quy định',
            color: const Color(0xff0f766e),
            onTap: onPolicies,
          ),
        ],
      ),
    ),
  );
}

class _Shortcut extends StatelessWidget {
  const _Shortcut({
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
  Widget build(BuildContext context) => Expanded(
    child: InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 3),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 42,
              height: 42,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: color.withValues(alpha: .08),
                borderRadius: BorderRadius.circular(13),
              ),
              child: Icon(icon, color: color, size: 23),
            ),
            const SizedBox(height: 7),
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w800),
            ),
          ],
        ),
      ),
    ),
  );
}

class _TaskTabs extends StatelessWidget {
  const _TaskTabs({
    required this.selected,
    required this.total,
    required this.inProgress,
    required this.done,
    required this.overdue,
    required this.onSelected,
  });

  final _HomeTaskFilter selected;
  final int total;
  final int inProgress;
  final int done;
  final int overdue;
  final ValueChanged<_HomeTaskFilter> onSelected;

  @override
  Widget build(BuildContext context) {
    final rows = [
      (_HomeTaskFilter.all, 'Tất cả ($total)'),
      (_HomeTaskFilter.inProgress, 'Đang dọn ($inProgress)'),
      (_HomeTaskFilter.done, 'Đã xong ($done)'),
      (_HomeTaskFilter.overdue, 'Quá hạn ($overdue)'),
    ];
    return Container(
      padding: const EdgeInsets.fromLTRB(4, 5, 4, 0),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: BlissAppTheme.line),
      ),
      child: Row(
        children: rows.map((row) {
          final active = selected == row.$1;
          final color = row.$1 == _HomeTaskFilter.overdue
              ? BlissAppTheme.danger
              : BlissAppTheme.brand;
          return Expanded(
            child: InkWell(
              onTap: () => onSelected(row.$1),
              borderRadius: BorderRadius.circular(12),
              child: Container(
                padding: const EdgeInsets.fromLTRB(2, 10, 2, 9),
                decoration: BoxDecoration(
                  border: Border(
                    bottom: BorderSide(
                      color: active ? color : Colors.transparent,
                      width: 3,
                    ),
                  ),
                ),
                child: Text(
                  row.$2,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: active ? color : BlissAppTheme.muted,
                    fontSize: 10,
                    fontWeight: active ? FontWeight.w900 : FontWeight.w700,
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

class _CompactTaskCard extends StatelessWidget {
  const _CompactTaskCard({required this.task, required this.onTap});
  final TaskViewData task;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final done = _HousekeepingHomeScreenState._isDone(task);
    final inProgress = _HousekeepingHomeScreenState._isInProgress(task);
    final overdue = _HousekeepingHomeScreenState._isOverdue(task);
    final color = overdue
        ? BlissAppTheme.danger
        : done
        ? const Color(0xff059669)
        : inProgress
        ? const Color(0xfff59e0b)
        : const Color(0xff64748b);
    final label = overdue
        ? 'Ưu tiên cao'
        : done
        ? 'Đã xong'
        : inProgress
        ? 'Đang dọn'
        : 'Chờ dọn';
    final status = done
        ? 'Đã hoàn thành'
        : inProgress
        ? task.dueLabel()
        : overdue
        ? 'Quá hạn'
        : 'Chưa bắt đầu';
    final floor = task.floor.isEmpty ? '' : ' · ${task.floor}';
    final summary =
        task.taskType == 'CHECKIN_PREPARATION' && task.nextCheckin != null
        ? 'Khách check-in ${_clock(task.nextCheckin!)}'
        : task.taskType == 'CHECKOUT_CLEANING'
        ? 'Dọn phòng trả khách'
        : task.taskTypeLabel;

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Card(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(18),
          side: BorderSide(
            color: overdue ? const Color(0xfffecaca) : BlissAppTheme.line,
          ),
        ),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(18),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(10, 11, 8, 11),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 68,
                  constraints: const BoxConstraints(minHeight: 86),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 5,
                    vertical: 10,
                  ),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: .07),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        done
                            ? Icons.check_circle_outline_rounded
                            : Icons.schedule_rounded,
                        color: color,
                        size: 30,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        label,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: color,
                          fontSize: 10,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 11),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              '${task.roomCode.isEmpty ? task.code : task.roomCode}$floor',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontSize: 17,
                                fontWeight: FontWeight.w900,
                                letterSpacing: -.2,
                              ),
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 5,
                            ),
                            decoration: BoxDecoration(
                              color: color.withValues(alpha: .08),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Text(
                              status,
                              style: TextStyle(
                                color: color,
                                fontSize: 9,
                                fontWeight: FontWeight.w900,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 3),
                      Text(
                        summary,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      if (task.dueAt != null) ...[
                        const SizedBox(height: 2),
                        Text(
                          done
                              ? 'Hoàn thành công việc trong ca'
                              : 'Cần hoàn thành trước ${_clock(task.dueAt!)}',
                          style: TextStyle(
                            color: overdue
                                ? BlissAppTheme.danger
                                : const Color(0xff475569),
                            fontSize: 12,
                            fontWeight: overdue
                                ? FontWeight.w800
                                : FontWeight.w600,
                          ),
                        ),
                      ],
                      const SizedBox(height: 7),
                      Wrap(
                        spacing: 10,
                        runSpacing: 4,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(
                                Icons.fact_check_outlined,
                                size: 15,
                                color: BlissAppTheme.muted,
                              ),
                              const SizedBox(width: 4),
                              Text(
                                '${task.checklistDone}/${task.checklistTotal} hạng mục',
                                style: const TextStyle(
                                  color: BlissAppTheme.muted,
                                  fontSize: 11,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ],
                          ),
                          if (task.note.isNotEmpty)
                            const Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  Icons.notes_rounded,
                                  size: 15,
                                  color: BlissAppTheme.muted,
                                ),
                                SizedBox(width: 3),
                                Text(
                                  'Có ghi chú',
                                  style: TextStyle(
                                    color: BlissAppTheme.muted,
                                    fontSize: 11,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ],
                            ),
                        ],
                      ),
                      if (inProgress && task.progress > 0) ...[
                        const SizedBox(height: 8),
                        ClipRRect(
                          borderRadius: BorderRadius.circular(99),
                          child: LinearProgressIndicator(
                            value: task.progress.clamp(0, 100) / 100,
                            minHeight: 5,
                            color: color,
                            backgroundColor: color.withValues(alpha: .1),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(width: 3),
                const Padding(
                  padding: EdgeInsets.only(top: 34),
                  child: Icon(
                    Icons.chevron_right_rounded,
                    color: BlissAppTheme.brandDark,
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

class _SupportBanner extends StatelessWidget {
  const _SupportBanner({required this.onTap});
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Material(
    color: const Color(0xffedf5f2),
    borderRadius: BorderRadius.circular(18),
    child: InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(18),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: Row(
          children: [
            Container(
              width: 38,
              height: 38,
              alignment: Alignment.center,
              decoration: const BoxDecoration(
                color: Colors.white,
                shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.error_rounded,
                color: BlissAppTheme.danger,
              ),
            ),
            const SizedBox(width: 10),
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Không thể dọn phòng?',
                    style: TextStyle(fontWeight: FontWeight.w900),
                  ),
                  Text(
                    'Báo ngay để quản lý hỗ trợ',
                    style: TextStyle(color: BlissAppTheme.muted, fontSize: 12),
                  ),
                ],
              ),
            ),
            const CircleAvatar(
              backgroundColor: Colors.white,
              child: Icon(
                Icons.chevron_right_rounded,
                color: BlissAppTheme.brand,
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

class _PolicyRow extends StatelessWidget {
  const _PolicyRow({required this.icon, required this.text});
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: Row(
      children: [
        Icon(icon, color: BlissAppTheme.brand),
        const SizedBox(width: 11),
        Expanded(child: Text(text)),
      ],
    ),
  );
}

class _HomeError extends StatelessWidget {
  const _HomeError({required this.message, required this.onRetry});
  final String message;
  final Future<void> Function({bool silent}) onRetry;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: const Color(0xfffef2f2),
      borderRadius: BorderRadius.circular(15),
      border: Border.all(color: const Color(0xfffecaca)),
    ),
    child: Row(
      children: [
        const Icon(Icons.cloud_off_outlined, color: BlissAppTheme.danger),
        const SizedBox(width: 8),
        Expanded(
          child: Text(message, maxLines: 2, overflow: TextOverflow.ellipsis),
        ),
        IconButton(
          tooltip: 'Thử lại',
          onPressed: () => onRetry(silent: false),
          icon: const Icon(Icons.refresh_rounded),
        ),
      ],
    ),
  );
}
