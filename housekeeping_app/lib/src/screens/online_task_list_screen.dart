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
        title: Text(widget.title),
        actions: [
          Badge(
            isLabelVisible: _unreadNotifications > 0,
            label: Text('$_unreadNotifications'),
            child: IconButton(
              tooltip: 'Thông báo',
              onPressed: _openNotifications,
              icon: const Icon(Icons.notifications_outlined),
            ),
          ),
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
            itemBuilder: (_) => const [
              PopupMenuItem(value: 'logout', child: Text('Đăng xuất')),
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
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SearchBar(
                      controller: _search,
                      hintText: 'Mã công việc hoặc phòng',
                      leading: const Icon(Icons.search),
                      trailing: [
                        if (_search.text.isNotEmpty)
                          IconButton(
                            tooltip: 'Xóa tìm kiếm',
                            onPressed: () {
                              _search.clear();
                              _load();
                            },
                            icon: const Icon(Icons.clear),
                          ),
                      ],
                      onSubmitted: (_) => _load(),
                    ),
                    const SizedBox(height: 10),
                    SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      child: Row(
                        children: [
                          for (final tab in widget.availableTabs)
                            Padding(
                              padding: const EdgeInsets.only(right: 7),
                              child: ChoiceChip(
                                selected: _tab == tab,
                                label: Text(tab.label),
                                onSelected: (_) {
                                  setState(() => _tab = tab);
                                  _load();
                                },
                              ),
                            ),
                        ],
                      ),
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: 10),
                      Card(
                        color: Theme.of(context).colorScheme.errorContainer,
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Row(
                            children: [
                              const Icon(Icons.cloud_off_outlined),
                              const SizedBox(width: 8),
                              Expanded(child: Text(_error!)),
                            ],
                          ),
                        ),
                      ),
                    ],
                    const SizedBox(height: 12),
                    Text(
                      '${_tab.label} · ${views.length}',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                  ],
                ),
              ),
            ),
            if (views.isEmpty && !_loading)
              const SliverFillRemaining(
                hasScrollBody: false,
                child: Center(
                  child: Padding(
                    padding: EdgeInsets.all(28),
                    child: Text(
                      'Không có công việc phù hợp.',
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
              )
            else
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(8, 8, 8, 110),
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
