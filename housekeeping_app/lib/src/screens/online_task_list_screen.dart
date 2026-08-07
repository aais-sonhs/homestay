import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../api/housekeeping_api.dart';
import '../offline/models.dart';
import '../presentation/task_presentation.dart';
import '../theme/app_theme.dart';
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
    this.active = true,
    super.key,
  });

  final HousekeepingApi api;
  final AsyncCallback onSignOut;
  final String title;
  final HousekeepingTaskTab initialTab;
  final List<HousekeepingTaskTab> availableTabs;
  final bool active;

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
  int _loadGeneration = 0;

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
    if (widget.active) {
      _load();
      _loadUnreadNotifications();
      _startPolling();
    }
  }

  @override
  void didUpdateWidget(covariant OnlineTaskListScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.active == widget.active) return;
    if (widget.active) {
      _load();
      _loadUnreadNotifications();
      _startPolling();
    } else {
      _loadGeneration++;
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
    final generation = ++_loadGeneration;
    final filters = Map<String, String>.from(_filters);
    if (!silent && mounted) setState(() => _loading = true);
    try {
      final tasks = await widget.api.tasks(filters: filters);
      if (!mounted || generation != _loadGeneration) return;
      setState(() {
        _tasks = tasks;
        _error = null;
        _loading = false;
      });
    } on Object catch (error) {
      if (!mounted || generation != _loadGeneration) return;
      setState(() {
        _error = 'Không tải được dữ liệu từ máy chủ: $error';
        _loading = false;
      });
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
        title: _BrandAppBarTitle(subtitle: widget.title),
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
          PopupMenuButton<String>(
            tooltip: 'Tài khoản',
            icon: Container(
              width: 34,
              height: 34,
              alignment: Alignment.center,
              decoration: const BoxDecoration(
                color: BlissAppTheme.brandSoft,
                shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.person_outline_rounded,
                size: 20,
                color: BlissAppTheme.brand,
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
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 5),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _TaskOverview(
                      title: _tab.label,
                      count: views.length,
                      loading: _loading,
                    ),
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(24),
                        border: Border.all(color: BlissAppTheme.line),
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
                            height: 48,
                            child: ListView.separated(
                              scrollDirection: Axis.horizontal,
                              itemCount: widget.availableTabs.length,
                              separatorBuilder: (_, _) =>
                                  const SizedBox(width: 8),
                              itemBuilder: (context, index) {
                                final tab = widget.availableTabs[index];
                                return ChoiceChip(
                                  selected: _tab == tab,
                                  avatar: Icon(_tabIcon(tab), size: 19),
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
                    const SizedBox(height: 18),
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
                              color: BlissAppTheme.brandSoft,
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: const Icon(
                              Icons.cloud_done_outlined,
                              size: 19,
                              color: BlissAppTheme.brand,
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
                padding: const EdgeInsets.fromLTRB(16, 7, 16, 32),
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

class _BrandAppBarTitle extends StatelessWidget {
  const _BrandAppBarTitle({required this.subtitle});

  final String subtitle;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Container(
        width: 38,
        height: 38,
        padding: const EdgeInsets.all(3),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(11),
          border: Border.all(color: BlissAppTheme.line),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: Image.asset('assets/branding/app_icon.png', fit: BoxFit.cover),
        ),
      ),
      const SizedBox(width: 10),
      Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Bliss Home',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: BlissAppTheme.brandDark,
                fontSize: 17,
                fontWeight: FontWeight.w900,
              ),
            ),
            Text(
              subtitle,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: BlissAppTheme.muted,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    ],
  );
}

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
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(28),
      gradient: const LinearGradient(
        colors: [BlissAppTheme.brandDark, Color(0xff0d9488)],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
    ),
    child: Row(
      children: [
        Container(
          width: 54,
          height: 54,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: .14),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: Colors.white.withValues(alpha: .16)),
          ),
          child: const Icon(
            Icons.assignment_turned_in_outlined,
            color: Colors.white,
            size: 29,
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
                  color: Color(0xffccfbf1),
                  fontSize: 14,
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
                  fontSize: 20,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ],
          ),
        ),
        Container(
          constraints: const BoxConstraints(minWidth: 54, minHeight: 54),
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(17),
          ),
          child: loading
              ? const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : Text(
                  '$count',
                  style: const TextStyle(
                    color: BlissAppTheme.brandDark,
                    fontSize: 24,
                    fontWeight: FontWeight.w900,
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
            style: const TextStyle(
              color: Color(0xff991b1b),
              fontSize: 14,
              fontWeight: FontWeight.w600,
            ),
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
            color: BlissAppTheme.brandSoft,
            shape: BoxShape.circle,
          ),
          child: const Icon(
            Icons.assignment_turned_in_outlined,
            color: BlissAppTheme.brand,
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
