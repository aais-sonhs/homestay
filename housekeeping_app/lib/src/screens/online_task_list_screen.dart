import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../api/housekeeping_api.dart';
import '../offline/models.dart';
import '../presentation/task_presentation.dart';
import '../widgets/task_card.dart';
import 'notification_screen.dart';
import 'offline_task_detail_screen.dart';

class OnlineTaskListScreen extends StatefulWidget {
  const OnlineTaskListScreen({
    required this.api,
    required this.onSignOut,
    this.title = 'Công việc buồng phòng',
    this.initialTab = HousekeepingTaskTab.mine,
    this.availableTabs = HousekeepingTaskTab.values,
    super.key,
  });

  final HousekeepingApi api;
  final AsyncCallback onSignOut;
  final String title;
  final HousekeepingTaskTab initialTab;
  final List<HousekeepingTaskTab> availableTabs;

  @override
  State<OnlineTaskListScreen> createState() => _OnlineTaskListScreenState();
}

class _OnlineTaskListScreenState extends State<OnlineTaskListScreen> {
  final _search = TextEditingController();
  List<Map<String, Object?>> _tasks = const [];
  late HousekeepingTaskTab _tab;
  Timer? _poller;
  bool _loading = true;
  int _unreadNotifications = 0;
  String? _error;

  Map<String, String> get _filters => {
    ..._tab.apiFilters,
    if (_search.text.trim().isNotEmpty) 'q': _search.text.trim(),
  };

  @override
  void initState() {
    super.initState();
    _tab = widget.availableTabs.contains(widget.initialTab)
        ? widget.initialTab
        : widget.availableTabs.first;
    _load();
    _loadUnreadNotifications();
    _poller = Timer.periodic(
      const Duration(seconds: 30),
      (_) => _load(silent: true),
    );
  }

  Future<void> _load({bool silent = false}) async {
    if (!silent && mounted) setState(() => _loading = true);
    try {
      _tasks = await widget.api.tasks(filters: _filters);
      _error = null;
    } on Object catch (error) {
      _error = 'Không tải được dữ liệu từ máy chủ: $error';
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loadUnreadNotifications() async {
    try {
      final result = await widget.api.notifications(unread: true);
      if (mounted) {
        setState(
          () => _unreadNotifications = result['unreadCount'] as int? ?? 0,
        );
      }
    } on Object {
      // Danh sách công việc vẫn hoạt động nếu thông báo tải lỗi.
    }
  }

  Future<void> _openTask(String taskId) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => OnlineTaskDetailScreen(taskId: taskId, api: widget.api),
      ),
    );
    await _load();
  }

  Future<void> _openNotifications() async {
    final taskId = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(
        builder: (_) => NotificationScreen(api: widget.api),
      ),
    );
    await _loadUnreadNotifications();
    if (taskId != null && mounted) await _openTask(taskId);
  }

  Future<void> _confirmSignOut() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        icon: const Icon(Icons.logout_rounded),
        title: const Text('Đăng xuất khỏi Bliss Home?'),
        content: const Text('Phiên đăng nhập trên thiết bị này sẽ được xóa.'),
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
  void dispose() {
    _poller?.cancel();
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final views = _tasks.map(TaskViewData.new).toList(growable: false);
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.title),
            const Text(
              'Dữ liệu trực tiếp từ Bliss Home',
              style: TextStyle(
                color: Color(0xff94a3b8),
                fontSize: 10,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 3),
            child: Badge(
              isLabelVisible: _unreadNotifications > 0,
              label: Text('$_unreadNotifications'),
              child: IconButton(
                tooltip: 'Thông báo',
                onPressed: _openNotifications,
                icon: const Icon(Icons.notifications_none_rounded),
              ),
            ),
          ),
          IconButton(
            tooltip: 'Tải lại',
            onPressed: _loading ? null : _load,
            icon: const Icon(Icons.refresh_rounded),
          ),
          PopupMenuButton<String>(
            tooltip: 'Tài khoản',
            icon: Container(
              width: 34,
              height: 34,
              alignment: Alignment.center,
              decoration: const BoxDecoration(
                color: Color(0xffe9e8ff),
                shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.person_outline_rounded,
                size: 20,
                color: Color(0xff4f46e5),
              ),
            ),
            onSelected: (value) {
              if (value == 'logout') unawaited(_confirmSignOut());
            },
            itemBuilder: (_) => const [
              PopupMenuItem(
                value: 'logout',
                child: Row(
                  children: [
                    Icon(Icons.logout_rounded, size: 19),
                    SizedBox(width: 10),
                    Text('Đăng xuất'),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(width: 7),
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
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 5),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _TaskOverview(
                      title: _tab.label,
                      count: views.length,
                      loading: _loading,
                    ),
                    const SizedBox(height: 14),
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(color: const Color(0xffe6eaf2)),
                      ),
                      child: Column(
                        children: [
                          SearchBar(
                            controller: _search,
                            hintText: 'Tìm mã công việc hoặc phòng',
                            leading: const Icon(Icons.search_rounded),
                            trailing: [
                              if (_search.text.isNotEmpty)
                                IconButton(
                                  tooltip: 'Xóa tìm kiếm',
                                  onPressed: () {
                                    _search.clear();
                                    setState(() {});
                                    _load();
                                  },
                                  icon: const Icon(Icons.close_rounded),
                                ),
                            ],
                            onChanged: (_) => setState(() {}),
                            onSubmitted: (_) => _load(),
                          ),
                          const SizedBox(height: 11),
                          SizedBox(
                            height: 40,
                            child: ListView.separated(
                              scrollDirection: Axis.horizontal,
                              itemCount: widget.availableTabs.length,
                              separatorBuilder: (_, _) =>
                                  const SizedBox(width: 7),
                              itemBuilder: (context, index) {
                                final tab = widget.availableTabs[index];
                                return ChoiceChip(
                                  selected: _tab == tab,
                                  avatar: Icon(_tabIcon(tab), size: 16),
                                  label: Text(tab.label),
                                  onSelected: (_) {
                                    setState(() => _tab = tab);
                                    _load();
                                  },
                                );
                              },
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: 12),
                      _TaskError(message: _error!, onRetry: () => _load()),
                    ],
                    const SizedBox(height: 20),
                    Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                _tab.label,
                                style: Theme.of(context).textTheme.titleLarge,
                              ),
                              const SizedBox(height: 2),
                              Text(
                                '${views.length} công việc phù hợp',
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                            ],
                          ),
                        ),
                        if (!_loading)
                          Container(
                            width: 36,
                            height: 36,
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: const Color(0xffecfdf5),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: const Icon(
                              Icons.cloud_done_outlined,
                              size: 19,
                              color: Color(0xff059669),
                            ),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            if (views.isEmpty && _loading)
              const SliverFillRemaining(
                hasScrollBody: false,
                child: Center(child: CircularProgressIndicator()),
              )
            else if (views.isEmpty)
              SliverFillRemaining(
                hasScrollBody: false,
                child: Center(
                  child: _TaskEmpty(
                    title: 'Chưa có công việc',
                    message:
                        'Không có công việc phù hợp với bộ lọc ${_tab.label.toLowerCase()}.',
                  ),
                ),
              )
            else
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 7, 16, 110),
                sliver: SliverList.builder(
                  itemCount: views.length,
                  itemBuilder: (context, index) => HousekeepingTaskCard(
                    task: views[index],
                    sync: const TaskSyncSummary(),
                    onTap: () => _openTask(views[index].id),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

IconData _tabIcon(HousekeepingTaskTab tab) => switch (tab) {
  HousekeepingTaskTab.mine => Icons.person_outline_rounded,
  HousekeepingTaskTab.available => Icons.inbox_outlined,
  HousekeepingTaskTab.inProgress => Icons.play_circle_outline_rounded,
  HousekeepingTaskTab.support => Icons.support_agent_rounded,
  HousekeepingTaskTab.waitingQc => Icons.fact_check_outlined,
  HousekeepingTaskTab.rework => Icons.replay_rounded,
  HousekeepingTaskTab.done => Icons.check_circle_outline_rounded,
};

class _TaskOverview extends StatelessWidget {
  const _TaskOverview({
    required this.title,
    required this.count,
    required this.loading,
  });

  final String title;
  final int count;
  final bool loading;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(19),
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(23),
      gradient: const LinearGradient(
        colors: [Color(0xff3730a3), Color(0xff4f46e5), Color(0xff7c3aed)],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
      boxShadow: const [
        BoxShadow(
          color: Color(0x304f46e5),
          blurRadius: 26,
          offset: Offset(0, 13),
        ),
      ],
    ),
    child: Row(
      children: [
        Container(
          width: 50,
          height: 50,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: .14),
            borderRadius: BorderRadius.circular(17),
            border: Border.all(color: Colors.white.withValues(alpha: .16)),
          ),
          child: const Icon(
            Icons.assignment_turned_in_outlined,
            color: Colors.white,
            size: 27,
          ),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Công việc hôm nay',
                style: TextStyle(
                  color: Color(0xffc7d2fe),
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 3),
              Text(
                title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
        ),
        Container(
          constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(16),
          ),
          child: loading
              ? const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : Text(
                  '$count',
                  style: const TextStyle(
                    color: Color(0xff4f46e5),
                    fontSize: 21,
                    fontWeight: FontWeight.w800,
                  ),
                ),
        ),
      ],
    ),
  );
}

class _TaskError extends StatelessWidget {
  const _TaskError({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(13),
    decoration: BoxDecoration(
      color: const Color(0xfffef2f2),
      borderRadius: BorderRadius.circular(16),
      border: Border.all(color: const Color(0xfffecaca)),
    ),
    child: Row(
      children: [
        const Icon(Icons.cloud_off_outlined, color: Color(0xffdc2626)),
        const SizedBox(width: 9),
        Expanded(
          child: Text(
            message,
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Color(0xff991b1b), fontSize: 11),
          ),
        ),
        IconButton(
          tooltip: 'Thử lại',
          onPressed: onRetry,
          icon: const Icon(Icons.refresh_rounded, color: Color(0xffdc2626)),
        ),
      ],
    ),
  );
}

class _TaskEmpty extends StatelessWidget {
  const _TaskEmpty({required this.title, required this.message});
  final String title;
  final String message;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.all(30),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 78,
          height: 78,
          alignment: Alignment.center,
          decoration: const BoxDecoration(
            color: Color(0xffe9e8ff),
            shape: BoxShape.circle,
          ),
          child: const Icon(
            Icons.assignment_turned_in_outlined,
            color: Color(0xff4f46e5),
            size: 36,
          ),
        ),
        const SizedBox(height: 17),
        Text(title, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 6),
        Text(
          message,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodyMedium,
        ),
      ],
    ),
  );
}
