import 'dart:async';
import 'dart:convert';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../api/housekeeping_api.dart';
import '../offline/models.dart';
import '../offline/offline_repository.dart';
import '../offline/sync_engine.dart';
import '../presentation/task_presentation.dart';
import '../widgets/conflict_resolution_sheet.dart';
import '../widgets/task_card.dart';
import 'notification_screen.dart';
import 'offline_task_detail_screen.dart';

class OfflineHomeScreen extends StatefulWidget {
  const OfflineHomeScreen({
    required this.api,
    required this.repository,
    required this.syncEngine,
    required this.onSignOut,
    this.title = 'Công việc buồng phòng',
    this.initialTab = HousekeepingTaskTab.mine,
    this.availableTabs = HousekeepingTaskTab.values,
    super.key,
  });

  final HousekeepingApi api;
  final OfflineRepository repository;
  final OfflineSyncEngine syncEngine;
  final AsyncCallback onSignOut;
  final String title;
  final HousekeepingTaskTab initialTab;
  final List<HousekeepingTaskTab> availableTabs;

  @override
  State<OfflineHomeScreen> createState() => _OfflineHomeScreenState();
}

class _OfflineHomeScreenState extends State<OfflineHomeScreen> {
  final _search = TextEditingController();
  final _connectivity = Connectivity();
  List<Map<String, Object?>> _tasks = const [];
  List<SyncConflict> _conflicts = const [];
  List<SyncFailure> _failures = const [];
  Map<String, TaskSyncSummary> _syncSummaries = const {};
  late HousekeepingTaskTab _tab;
  TaskFilters _filters = const TaskFilters();
  StreamSubscription<List<ConnectivityResult>>? _networkSubscription;
  Timer? _clock;
  Timer? _progressPoller;
  int _pending = 0;
  int _unreadNotifications = 0;
  bool _loading = true;
  bool _refreshing = false;
  bool? _online;
  String? _notice;

  Map<String, String> get _apiFilters => _filters.toApiQuery(_tab);
  String get _viewKey => jsonEncode(_apiFilters);

  @override
  void initState() {
    super.initState();
    _tab = widget.availableTabs.contains(widget.initialTab)
        ? widget.initialTab
        : widget.availableTabs.first;
    _search.text = _filters.query;
    _connectivity.checkConnectivity().then(_networkChanged);
    _networkSubscription = _connectivity.onConnectivityChanged.listen(
      _networkChanged,
    );
    _clock = Timer.periodic(const Duration(minutes: 1), (_) {
      if (mounted) setState(() {});
    });
    _progressPoller = Timer.periodic(const Duration(seconds: 30), (_) {
      if (mounted && _online == true && !_refreshing) {
        unawaited(_load(refreshOnline: true, background: true));
      }
    });
    _load(refreshOnline: true);
    _loadUnreadNotifications();
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
      // Notifications are online-only; task cache remains fully usable offline.
    }
  }

  Future<void> _openTask(String taskId) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => OfflineTaskDetailScreen(
          taskId: taskId,
          api: widget.api,
          repository: widget.repository,
          syncEngine: widget.syncEngine,
        ),
      ),
    );
    await _load();
  }

  void _networkChanged(List<ConnectivityResult> results) {
    if (!mounted) return;
    setState(() => _online = !results.contains(ConnectivityResult.none));
  }

  Future<void> _load({
    bool refreshOnline = false,
    bool background = false,
  }) async {
    if (_refreshing) return;
    _refreshing = true;
    if (mounted && !background) setState(() => _loading = true);
    try {
      _tasks = await widget.repository.cachedTasks(viewKey: _viewKey);
      if (refreshOnline) {
        try {
          final online = await widget.api.tasks(filters: _apiFilters);
          await widget.repository.cacheTaskList(online, viewKey: _viewKey);
          _tasks = online;
          _notice = null;
        } on Object {
          _notice = _tasks.isEmpty
              ? 'Không kết nối được máy chủ và bộ lọc này chưa có dữ liệu trên thiết bị.'
              : 'Đang hiển thị dữ liệu đã mã hóa trên thiết bị.';
        }
      }
      _conflicts = await widget.repository.conflicts();
      _failures = await widget.repository.failures();
      _syncSummaries = await widget.repository.syncSummariesByTask();
      _pending = await widget.repository.unresolvedCount();
    } finally {
      _refreshing = false;
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _sync() async {
    setState(() => _notice = 'Đang đồng bộ theo thứ tự phụ thuộc…');
    try {
      final report = await widget.syncEngine.syncNow();
      _notice =
          'Đã đồng bộ ${report.mediaSynced + report.mutationsSynced}; '
          '${report.conflicts} xung đột, ${report.failed} lỗi.';
    } on Object catch (error) {
      _notice = 'Không thể đồng bộ: $error';
    }
    await _load(refreshOnline: true);
  }

  Future<void> _openConflict(SyncConflict conflict) async {
    final retry = await showConflictResolutionSheet(context, conflict);
    if (retry == null || !mounted) return;
    try {
      if (retry) {
        await widget.syncEngine.retryConflict(conflict);
      } else {
        await widget.syncEngine.discardConflict(conflict);
      }
      await _load(refreshOnline: true);
    } on Object catch (error) {
      setState(() => _notice = error.toString());
    }
  }

  Future<void> _retryFailure(SyncFailure failure) async {
    try {
      await widget.syncEngine.retryFailure(failure);
      await _load(refreshOnline: true);
    } on Object catch (error) {
      setState(() => _notice = error.toString());
    }
  }

  Future<void> _discardFailure(SyncFailure failure) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Bỏ thay đổi lỗi?'),
        content: Text(
          '${viCodeLabel(failure.operation)}\n${failure.errorMessage}',
        ),
        actions: [
          Badge(
            isLabelVisible: _unreadNotifications > 0,
            label: Text('$_unreadNotifications'),
            child: IconButton(
              tooltip: 'Thông báo',
              onPressed: () async {
                final taskId = await Navigator.of(context).push<String>(
                  MaterialPageRoute<String>(
                    builder: (_) => NotificationScreen(api: widget.api),
                  ),
                );
                await _loadUnreadNotifications();
                if (taskId != null && mounted) await _openTask(taskId);
              },
              icon: const Icon(Icons.notifications_outlined),
            ),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Giữ lại'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Bỏ thay đổi'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await widget.syncEngine.discardFailure(failure);
    await _load();
  }

  Future<void> _changeTab(HousekeepingTaskTab tab) async {
    if (_tab == tab) return;
    setState(() => _tab = tab);
    await _load(refreshOnline: true);
  }

  Future<void> _applySearch(String value) async {
    _filters = _filters.copyWith(query: value.trim());
    await _load(refreshOnline: true);
  }

  Future<void> _openFilters() async {
    final result = await showModalBottomSheet<TaskFilters>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (context) => _TaskFilterSheet(
        initial: _filters,
        tasks: _tasks.map(TaskViewData.new).toList(growable: false),
      ),
    );
    if (result == null) return;
    _filters = result.copyWith(query: _search.text.trim());
    await _load(refreshOnline: true);
  }

  @override
  void dispose() {
    _search.dispose();
    _networkSubscription?.cancel();
    _clock?.cancel();
    _progressPoller?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final views = _tasks
        .map(TaskViewData.new)
        .where((task) {
          // Server applies the authoritative tab/permission filters. The local
          // check keeps cached search results predictable while offline.
          return task.matchesText(_filters.query);
        })
        .toList(growable: false);
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.title),
        actions: [
          Badge(
            isLabelVisible: _pending > 0,
            label: Text('$_pending'),
            child: IconButton(
              tooltip: 'Đồng bộ dữ liệu',
              onPressed: _sync,
              icon: const Icon(Icons.sync),
            ),
          ),
          PopupMenuButton<String>(
            tooltip: 'Tài khoản',
            icon: const Icon(Icons.account_circle_outlined),
            onSelected: (value) async {
              if (value != 'logout') return;
              final confirmed = await showDialog<bool>(
                context: context,
                builder: (context) => AlertDialog(
                  title: const Text('Đăng xuất?'),
                  content: Text(
                    _pending > 0
                        ? 'Thiết bị còn $_pending thay đổi chưa đồng bộ. Dữ liệu mã hóa vẫn được giữ, nhưng hãy đồng bộ trước khi đổi tài khoản.'
                        : 'Mã truy cập và mã làm mới sẽ được xóa khỏi vùng lưu trữ bảo mật.',
                  ),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(context, false),
                      child: const Text('Ở lại'),
                    ),
                    FilledButton(
                      onPressed: _pending > 0
                          ? null
                          : () => Navigator.pop(context, true),
                      child: const Text('Đăng xuất'),
                    ),
                  ],
                ),
              );
              if (confirmed == true) await widget.onSignOut();
            },
            itemBuilder: (context) => const [
              PopupMenuItem(value: 'logout', child: Text('Đăng xuất')),
            ],
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => _load(refreshOnline: true),
        child: CustomScrollView(
          slivers: [
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _NetworkBanner(online: _online, pending: _pending),
                    const SizedBox(height: 10),
                    SearchBar(
                      controller: _search,
                      hintText: 'Mã công việc, phòng hoặc đặt phòng',
                      leading: const Icon(Icons.search),
                      trailing: [
                        IconButton(
                          tooltip: 'Bộ lọc nâng cao',
                          onPressed: _openFilters,
                          icon: Badge(
                            isLabelVisible: _filters.active,
                            child: const Icon(Icons.tune),
                          ),
                        ),
                      ],
                      onSubmitted: _applySearch,
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
                                onSelected: (_) => _changeTab(tab),
                              ),
                            ),
                        ],
                      ),
                    ),
                    if (_notice != null) ...[
                      const SizedBox(height: 10),
                      _Notice(text: _notice!),
                    ],
                    if (_conflicts.isNotEmpty || _failures.isNotEmpty) ...[
                      const SizedBox(height: 10),
                      _SyncProblems(
                        conflicts: _conflicts,
                        failures: _failures,
                        onConflict: _openConflict,
                        onRetryFailure: _retryFailure,
                        onDiscardFailure: _discardFailure,
                      ),
                    ],
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            '${_tab.label} · ${views.length}',
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                        ),
                        if (_loading)
                          const SizedBox.square(
                            dimension: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                      ],
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
                      'Không có công việc phù hợp. Thử đổi nhóm hoặc bỏ bớt bộ lọc.',
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
                  itemBuilder: (context, index) {
                    final task = views[index];
                    return HousekeepingTaskCard(
                      task: task,
                      sync: _syncSummaries[task.id] ?? const TaskSyncSummary(),
                      onTap: () => _openTask(task.id),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _sync,
        icon: Icon(_pending == 0 ? Icons.cloud_done : Icons.cloud_upload),
        label: Text(_pending == 0 ? 'Đã đồng bộ' : 'Đồng bộ $_pending'),
      ),
    );
  }
}

class _NetworkBanner extends StatelessWidget {
  const _NetworkBanner({required this.online, required this.pending});
  final bool? online;
  final int pending;

  @override
  Widget build(BuildContext context) {
    final connected = online == true;
    final color = connected
        ? Theme.of(context).colorScheme.secondaryContainer
        : Theme.of(context).colorScheme.errorContainer;
    final text = online == null
        ? 'Đang kiểm tra kết nối…'
        : connected
        ? 'Trực tuyến${pending > 0 ? ' · $pending thay đổi chưa đồng bộ' : ''}'
        : 'Ngoại tuyến · dữ liệu mới được giữ trong kho dữ liệu mã hóa trên thiết bị';
    return Semantics(
      liveRegion: true,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          children: [
            Icon(connected ? Icons.cloud_done_outlined : Icons.cloud_off),
            const SizedBox(width: 8),
            Expanded(child: Text(text)),
          ],
        ),
      ),
    );
  }
}

class _Notice extends StatelessWidget {
  const _Notice({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        children: [
          const Icon(Icons.info_outline),
          const SizedBox(width: 8),
          Expanded(child: Text(text)),
        ],
      ),
    ),
  );
}

class _SyncProblems extends StatelessWidget {
  const _SyncProblems({
    required this.conflicts,
    required this.failures,
    required this.onConflict,
    required this.onRetryFailure,
    required this.onDiscardFailure,
  });

  final List<SyncConflict> conflicts;
  final List<SyncFailure> failures;
  final ValueChanged<SyncConflict> onConflict;
  final ValueChanged<SyncFailure> onRetryFailure;
  final ValueChanged<SyncFailure> onDiscardFailure;

  @override
  Widget build(BuildContext context) => Card(
    color: Theme.of(context).colorScheme.errorContainer,
    child: ExpansionTile(
      initiallyExpanded: true,
      leading: const Icon(Icons.sync_problem),
      title: Text('${conflicts.length} xung đột · ${failures.length} lỗi'),
      subtitle: const Text('Cần xử lý rõ ràng trước khi hoàn thành công việc'),
      children: [
        for (final conflict in conflicts)
          ListTile(
            title: Text(
              '${viCodeLabel(conflict.operation)} · ${conflict.taskId}',
            ),
            subtitle: const Text('Máy chủ có phiên bản mới hơn'),
            trailing: const Icon(Icons.compare_arrows),
            onTap: () => onConflict(conflict),
          ),
        for (final failure in failures)
          ListTile(
            title: Text(
              '${viCodeLabel(failure.operation)} · ${failure.taskId}',
            ),
            subtitle: Text(failure.errorMessage),
            trailing: Wrap(
              children: [
                IconButton(
                  tooltip: 'Bỏ thay đổi',
                  onPressed: () => onDiscardFailure(failure),
                  icon: const Icon(Icons.delete_outline),
                ),
                IconButton(
                  tooltip: 'Thử lại',
                  onPressed: () => onRetryFailure(failure),
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),
          ),
      ],
    ),
  );
}

class _TaskFilterSheet extends StatefulWidget {
  const _TaskFilterSheet({required this.initial, required this.tasks});
  final TaskFilters initial;
  final List<TaskViewData> tasks;

  @override
  State<_TaskFilterSheet> createState() => _TaskFilterSheetState();
}

class _TaskFilterSheetState extends State<_TaskFilterSheet> {
  late DateTime? _date = widget.initial.date;
  late String _branchId = widget.initial.branchId;
  late String _floor = widget.initial.floor;
  late String _roomType = widget.initial.roomType;
  late String _taskType = widget.initial.taskType;
  late String _priority = widget.initial.priority;
  late String _areaId = widget.initial.areaId;
  late String _shiftId = widget.initial.shiftId;
  late String _status = widget.initial.status;
  late String _assignee = widget.initial.assignee;
  late bool _qcRework = widget.initial.qcRework;
  late bool _overdue = widget.initial.overdue;
  late bool _checkinRisk = widget.initial.checkinRisk;

  @override
  Widget build(BuildContext context) {
    final branches = <String, String>{};
    for (final task in widget.tasks) {
      final id = task.branch['id'] as String?;
      final name = task.branchName;
      if (id != null && name.isNotEmpty) branches[id] = name;
    }
    final areas = <String, String>{};
    final shifts = <String, String>{};
    final assignees = <String, String>{};
    for (final task in widget.tasks) {
      if (task.areaId.isNotEmpty) areas[task.areaId] = task.areaName;
      if (task.shiftId.isNotEmpty) shifts[task.shiftId] = task.shiftName;
      if (task.assigneeId.isNotEmpty) {
        assignees[task.assigneeId] = task.assigneeName;
      }
    }
    List<String> values(String Function(TaskViewData task) getter) =>
        widget.tasks
            .map(getter)
            .where((value) => value.isNotEmpty)
            .toSet()
            .toList()
          ..sort();
    return Padding(
      padding: EdgeInsets.fromLTRB(
        16,
        12,
        16,
        20 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: ListView(
        shrinkWrap: true,
        children: [
          Text(
            'Bộ lọc công việc',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 12),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.calendar_today),
            title: const Text('Ngày'),
            subtitle: Text(
              _date == null
                  ? 'Theo mặc định của máy chủ'
                  : TaskFilters.dateOnly(_date!),
            ),
            trailing: Wrap(
              children: [
                if (_date != null)
                  IconButton(
                    tooltip: 'Bỏ ngày',
                    onPressed: () => setState(() => _date = null),
                    icon: const Icon(Icons.clear),
                  ),
                IconButton(
                  tooltip: 'Chọn ngày',
                  onPressed: () async {
                    final result = await showDatePicker(
                      context: context,
                      initialDate: _date ?? DateTime.now(),
                      firstDate: DateTime.now().subtract(
                        const Duration(days: 30),
                      ),
                      lastDate: DateTime.now().add(const Duration(days: 365)),
                    );
                    if (result != null) setState(() => _date = result);
                  },
                  icon: const Icon(Icons.edit_calendar),
                ),
              ],
            ),
          ),
          _Dropdown(
            label: 'Chi nhánh',
            value: _branchId,
            values: branches,
            onChanged: (value) => setState(() => _branchId = value),
          ),
          _Dropdown.fromValues(
            label: 'Tầng',
            value: _floor,
            values: values((task) => task.floor),
            onChanged: (value) => setState(() => _floor = value),
          ),
          _Dropdown.fromValues(
            label: 'Loại phòng',
            value: _roomType,
            values: values((task) => task.roomType),
            onChanged: (value) => setState(() => _roomType = value),
          ),
          _Dropdown.fromValues(
            label: 'Loại công việc',
            value: _taskType,
            values: values((task) => task.taskType),
            onChanged: (value) => setState(() => _taskType = value),
          ),
          _Dropdown(
            label: 'Khu vực',
            value: _areaId,
            values: areas,
            onChanged: (value) => setState(() => _areaId = value),
          ),
          _Dropdown(
            label: 'Ca làm việc',
            value: _shiftId,
            values: shifts,
            onChanged: (value) => setState(() => _shiftId = value),
          ),
          _Dropdown(
            label: 'Trạng thái',
            value: _status,
            values: const {
              'UNASSIGNED': 'Chưa phân công',
              'PENDING_ACCEPTANCE': 'Chờ nhận',
              'ACCEPTED': 'Đã nhận',
              'IN_PROGRESS': 'Đang làm',
              'PAUSED': 'Tạm dừng',
              'WAITING_SUPPORT': 'Chờ hỗ trợ',
              'WAITING_QC': 'Chờ kiểm tra chất lượng',
              'QC_REJECTED': 'Kiểm tra không đạt, cần làm lại',
              'QC_APPROVED': 'Kiểm tra chất lượng đạt',
              'COMPLETED': 'Hoàn thành',
              'CANCELLED': 'Đã hủy',
            },
            onChanged: (value) => setState(() => _status = value),
          ),
          _Dropdown(
            label: 'Người thực hiện',
            value: _assignee,
            values: {'me': 'Tôi', 'unassigned': 'Chưa phân công', ...assignees},
            onChanged: (value) => setState(() => _assignee = value),
          ),
          _Dropdown(
            label: 'Ưu tiên',
            value: _priority,
            values: const {
              'NORMAL': 'Bình thường',
              'HIGH': 'Cao',
              'URGENT': 'Khẩn cấp',
            },
            onChanged: (value) => setState(() => _priority = value),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Chỉ công việc quá hạn'),
            value: _overdue,
            onChanged: (value) => setState(() => _overdue = value),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Nguy cơ không kịp giờ nhận phòng'),
            value: _checkinRisk,
            onChanged: (value) => setState(() => _checkinRisk = value),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Chỉ công việc cần làm lại sau kiểm tra'),
            value: _qcRework,
            onChanged: (value) => setState(() => _qcRework = value),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => Navigator.pop(
                    context,
                    TaskFilters(query: widget.initial.query),
                  ),
                  child: const Text('Xóa bộ lọc'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: FilledButton(
                  onPressed: () => Navigator.pop(
                    context,
                    TaskFilters(
                      query: widget.initial.query,
                      date: _date,
                      branchId: _branchId,
                      floor: _floor,
                      roomType: _roomType,
                      taskType: _taskType,
                      priority: _priority,
                      areaId: _areaId,
                      shiftId: _shiftId,
                      status: _status,
                      assignee: _assignee,
                      qcRework: _qcRework,
                      overdue: _overdue,
                      checkinRisk: _checkinRisk,
                    ),
                  ),
                  child: const Text('Áp dụng'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Dropdown extends StatelessWidget {
  const _Dropdown({
    required this.label,
    required this.value,
    required this.values,
    required this.onChanged,
  });

  factory _Dropdown.fromValues({
    required String label,
    required String value,
    required List<String> values,
    required ValueChanged<String> onChanged,
  }) => _Dropdown(
    label: label,
    value: value,
    values: {for (final item in values) item: item},
    onChanged: onChanged,
  );

  final String label;
  final String value;
  final Map<String, String> values;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child: DropdownButtonFormField<String>(
      initialValue: values.containsKey(value) ? value : '',
      decoration: InputDecoration(labelText: label),
      items: [
        const DropdownMenuItem(value: '', child: Text('Tất cả')),
        for (final entry in values.entries)
          DropdownMenuItem(value: entry.key, child: Text(entry.value)),
      ],
      onChanged: (value) => onChanged(value ?? ''),
    ),
  );
}
