import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../api/housekeeping_api.dart';
import '../device/device_evidence.dart';
import '../offline/models.dart';
import '../offline/offline_repository.dart';
import '../offline/sync_engine.dart';
import '../presentation/task_presentation.dart';
import '../widgets/checklist_editor.dart';

class OfflineTaskDetailScreen extends StatefulWidget {
  const OfflineTaskDetailScreen({
    required this.taskId,
    required this.api,
    required this.repository,
    required this.syncEngine,
    super.key,
  });

  final String taskId;
  final HousekeepingApi api;
  final OfflineRepository repository;
  final OfflineSyncEngine syncEngine;

  @override
  State<OfflineTaskDetailScreen> createState() =>
      _OfflineTaskDetailScreenState();
}

class _OfflineTaskDetailScreenState extends State<OfflineTaskDetailScreen> {
  final _picker = ImagePicker();
  final _note = TextEditingController();
  Map<String, Object?>? _task;
  List<LocalMediaPreview> _localMedia = const [];
  int _pending = 0;
  bool _loading = true;
  String? _notice;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({bool online = true}) async {
    if (mounted) setState(() => _loading = true);
    _task = await widget.repository.cachedTaskDetail(widget.taskId);
    if (online) {
      try {
        _task = await widget.api.taskDetail(widget.taskId);
        await widget.repository.cacheTaskDetail(_task!);
        _notice = null;
      } on Object {
        _notice = _task == null
            ? 'Không có dữ liệu chi tiết của công việc này trên thiết bị.'
            : 'Ngoại tuyến: thay đổi mới được giữ trong kho dữ liệu mã hóa.';
      }
    }
    if (_note.text.isEmpty && _task?['note'] is String) {
      _note.text = _task!['note']! as String;
    }
    _pending = await widget.repository.unresolvedCount(taskId: widget.taskId);
    _localMedia = await widget.repository.localMedia(widget.taskId);
    if (mounted) setState(() => _loading = false);
  }

  Map get _capabilities => _task?['capabilities'] as Map? ?? const {};
  bool _can(String capability) => _capabilities[capability] == true;

  Future<void> _queueOperation(
    String operation,
    Map<String, Object?> payload, {
    String? projectedStatus,
    Map<String, bool>? projectedCapabilities,
  }) async {
    final task = _task!;
    final baseVersion = await widget.repository.nextProjectedVersion(
      widget.taskId,
    );
    final dependsOn = await widget.repository.latestTaskDependency(
      widget.taskId,
    );
    await widget.repository.enqueueMutation(
      taskId: widget.taskId,
      operation: operation,
      baseVersion: baseVersion,
      baseSnapshot: {
        'version': task['version'],
        'status': task['status'],
        'note': task['note'],
      },
      dependsOn: dependsOn,
      payload: payload,
    );
    if (projectedStatus != null) {
      task['status'] = projectedStatus;
      task['statusLabel'] = _statusLabel(projectedStatus);
    }
    if (projectedCapabilities != null) {
      final capabilities = Map<String, Object?>.from(
        task['capabilities'] as Map? ?? const {},
      );
      capabilities.addAll(projectedCapabilities);
      task['capabilities'] = capabilities;
    }
    await widget.repository.cacheTaskDetail(task);
    await _load(online: false);
  }

  Future<void> _saveNote() async {
    await _queueOperation('UPDATE_TASK_NOTE', {'note': _note.text.trim()});
    _task!['note'] = _note.text.trim();
    await widget.repository.cacheTaskDetail(_task!);
    setState(() => _notice = 'Ghi chú đang chờ đồng bộ.');
  }

  Future<void> _editChecklist(Map<String, Object?> item) async {
    final result = await showChecklistEditor(context, item);
    if (result == null) return;
    if (result.capturePhoto) {
      final captured = await _capturePhoto(
        source: ImageSource.camera,
        category: 'AREA',
        checklistItemId: item['id'] as String?,
      );
      if (captured == null) return;
    }
    final baseVersion = await widget.repository.nextProjectedVersion(
      widget.taskId,
    );
    final dependsOn = await widget.repository.latestTaskDependency(
      widget.taskId,
    );
    await widget.repository.enqueueMutation(
      taskId: widget.taskId,
      operation: 'UPDATE_CHECKLIST_ITEM',
      baseVersion: baseVersion,
      baseSnapshot: {'version': _task!['version'], 'checklistItem': item},
      dependsOn: dependsOn,
      payload: {
        'itemId': item['id'],
        'itemVersion': item['updateVersion'],
        'status': result.status,
        'value': result.value,
        'note': result.note,
        'failureReason': result.failureReason,
      },
    );
    item
      ..['status'] = result.status
      ..['value'] = result.value
      ..['note'] = result.note
      ..['failureReason'] = result.failureReason
      ..['updateVersion'] = (item['updateVersion'] as int? ?? 1) + 1;
    for (final cached
        in (_task!['checklist'] as List? ?? const []).whereType<Map>()) {
      if (cached['id'] == item['id']) {
        cached
          ..['status'] = result.status
          ..['value'] = result.value
          ..['note'] = result.note
          ..['failureReason'] = result.failureReason
          ..['updateVersion'] = item['updateVersion'];
        break;
      }
    }
    _recalculateLocalProgress();
    await widget.repository.cacheTaskDetail(_task!);
    await _load(online: false);
  }

  void _recalculateLocalProgress() {
    final checklist = (_task!['checklist'] as List? ?? const [])
        .whereType<Map>();
    final required = checklist
        .where((item) => item['required'] == true)
        .toList();
    final completed = required
        .where((item) => item['status'] == 'COMPLETED')
        .length;
    _task!['progressPercent'] = required.isEmpty
        ? 100
        : (completed * 100 / required.length).round();
    _task!['checklistSummary'] = {
      'totalRequired': required.length,
      'completedRequired': completed,
    };
  }

  Future<QueuedMedia?> _capturePhoto({
    required ImageSource source,
    required String category,
    String? checklistItemId,
  }) async {
    final file = await _picker.pickImage(source: source, imageQuality: 86);
    if (file == null) return null;
    final bytes = await file.readAsBytes();
    final baseVersion = await widget.repository.nextProjectedVersion(
      widget.taskId,
    );
    final dependsOn = await widget.repository.latestTaskDependency(
      widget.taskId,
    );
    final media = await widget.repository.enqueueMedia(
      taskId: widget.taskId,
      baseVersion: baseVersion,
      bytes: bytes,
      fileName: file.name,
      checksum: sha256.convert(bytes).toString(),
      dependsOn: dependsOn,
      metadata: {
        'category': category,
        'checklistItemId': ?checklistItemId,
        'source': source == ImageSource.camera ? 'OFFLINE_CAMERA' : 'GALLERY',
        'capturedAt': DateTime.now().toUtc().toIso8601String(),
        'metadata': {
          'offline': true,
          'originalPathHash': sha256.convert(utf8.encode(file.path)).toString(),
        },
      },
    );
    await _load(online: false);
    return media;
  }

  Future<void> _addPhoto() async {
    final request = await showModalBottomSheet<_PhotoRequest>(
      context: context,
      useSafeArea: true,
      builder: (context) => _PhotoPickerSheet(qcMode: _can('qcReview')),
    );
    if (request == null) return;
    await _capturePhoto(source: request.source, category: request.category);
  }

  Future<void> _accept() => _queueOperation(
    'ACCEPT',
    const {},
    projectedStatus: 'ACCEPTED',
    projectedCapabilities: const {'accept': false, 'start': true},
  );

  Future<void> _start() async {
    final verification = await showDialog<Map<String, Object?>>(
      context: context,
      builder: (context) =>
          _StartDialog(guestInRoom: _task!['guestInRoom'] == true),
    );
    if (verification == null) return;
    if (verification['method'] == 'CAMERA') {
      final media = await _capturePhoto(
        source: ImageSource.camera,
        category: 'BEFORE',
      );
      if (media == null) return;
      verification['cameraPhotoClientId'] = media.clientMediaId;
    }
    await _queueOperation(
      'START',
      {'roomVerification': verification},
      projectedStatus: 'IN_PROGRESS',
      projectedCapabilities: const {
        'start': false,
        'update': true,
        'pause': true,
        'resume': false,
        'complete': true,
      },
    );
  }

  Future<void> _pause() async {
    final payload = await showDialog<Map<String, Object?>>(
      context: context,
      builder: (context) => const _PauseDialog(),
    );
    if (payload == null) return;
    await _queueOperation(
      'PAUSE',
      payload,
      projectedStatus: payload['reasonCode'] == 'WAITING_TECHNICIAN'
          ? 'WAITING_SUPPORT'
          : 'PAUSED',
      projectedCapabilities: const {
        'update': false,
        'pause': false,
        'resume': true,
        'complete': false,
      },
    );
  }

  Future<void> _resume() => _queueOperation(
    'RESUME',
    const {},
    projectedStatus: 'IN_PROGRESS',
    projectedCapabilities: const {
      'update': true,
      'pause': true,
      'resume': false,
      'complete': true,
    },
  );

  Future<void> _queueSupply() async {
    final payload = await showDialog<Map<String, Object?>>(
      context: context,
      builder: (context) => const _SupplyDialog(),
    );
    if (payload != null) {
      await _queueOperation('CREATE_SUPPLY_REQUEST', payload);
    }
  }

  Future<void> _queueIssue() async {
    final payload = await showDialog<Map<String, Object?>>(
      context: context,
      builder: (context) => const _IssueDialog(),
    );
    if (payload != null) await _queueOperation('REPORT_ISSUE', payload);
  }

  Future<void> _showCompletion() async {
    Map<String, Object?>? summary;
    try {
      summary = await widget.api.completionSummary(widget.taskId);
    } on Object {
      // The dialog below clearly labels local-only validation. Backend will
      // remain authoritative when the queued completion eventually syncs.
    }
    if (!mounted) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => _CompletionDialog(
        task: _task!,
        summary: summary,
        localPending: _pending,
      ),
    );
    if (confirmed != true) return;
    if (_pending > 0) {
      setState(
        () => _notice =
            'Phải đồng bộ hoặc xử lý hết thay đổi đang chờ, bị lỗi và xung đột trước khi hoàn thành.',
      );
      return;
    }
    await _queueOperation(
      'COMPLETE',
      {'confirmFinalInspection': true, 'finalNote': _note.text.trim()},
      projectedStatus: 'WAITING_QC',
      projectedCapabilities: const {
        'update': false,
        'pause': false,
        'complete': false,
      },
    );
    await _sync();
  }

  Future<void> _sync() async {
    setState(() => _notice = 'Đang đồng bộ…');
    try {
      final result = await widget.syncEngine.syncNow();
      _notice =
          'Đồng bộ ${result.mediaSynced + result.mutationsSynced} thay đổi; '
          '${result.conflicts} xung đột, ${result.failed} lỗi.';
    } on Object catch (error) {
      _notice = 'Không thể đồng bộ: $error';
    }
    await _load();
  }

  String _statusLabel(String status) => switch (status) {
    'ACCEPTED' => 'Đã nhận việc',
    'IN_PROGRESS' => 'Đang thực hiện',
    'PAUSED' => 'Tạm dừng',
    'WAITING_SUPPORT' => 'Chờ hỗ trợ',
    'WAITING_QC' => 'Chờ kiểm tra chất lượng',
    _ => viCodeLabel(status),
  };

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final task = _task;
    if (task == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Chi tiết công việc')),
        body: Center(
          child: _loading
              ? const CircularProgressIndicator()
              : const Text('Không có dữ liệu công việc trên thiết bị.'),
        ),
      );
    }
    final room = task['room'] as Map? ?? const {};
    return Scaffold(
      appBar: AppBar(
        title: Text('${room['code'] ?? ''} · ${task['code']}'),
        actions: [
          Badge(
            isLabelVisible: _pending > 0,
            label: Text('$_pending'),
            child: IconButton(
              tooltip: 'Đồng bộ công việc',
              onPressed: _sync,
              icon: const Icon(Icons.sync),
            ),
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
        onRefresh: () => _load(),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 110),
          children: [
            if (_notice != null) _InfoBanner(text: _notice!),
            _TaskHeader(task: task, pending: _pending),
            _GeneralSection(task: task),
            _RoomSection(task: task),
            _SlaSection(task: task),
            if (task['status'] == 'QC_REJECTED' ||
                (task['qcRounds'] as List? ?? const []).isNotEmpty)
              _ReworkSection(task: task),
            _ChecklistSection(
              task: task,
              editable: _can('update'),
              onEdit: _editChecklist,
            ),
            _PhotoSection(
              task: task,
              localMedia: _localMedia,
              canAdd: _can('update') || _can('qcReview'),
              onAdd: _addPhoto,
            ),
            _SupportSection(task: task),
            _NoteSection(
              controller: _note,
              canEdit: _can('update'),
              onSave: _saveNote,
            ),
            _TimelineSection(task: task),
            _ActionPanel(
              task: task,
              canAccept: _can('accept'),
              canStart: _can('start'),
              canPause: _can('pause'),
              canResume: _can('resume'),
              canUpdate: _can('update'),
              canComplete: _can('complete') && _pending == 0,
              pending: _pending,
              onAccept: _accept,
              onStart: _start,
              onPause: _pause,
              onResume: _resume,
              onSupply: _queueSupply,
              onIssue: _queueIssue,
              onComplete: _showCompletion,
              onSync: _sync,
            ),
          ],
        ),
      ),
    );
  }
}

class _InfoBanner extends StatelessWidget {
  const _InfoBanner({required this.text});
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

class _TaskHeader extends StatelessWidget {
  const _TaskHeader({required this.task, required this.pending});
  final Map<String, Object?> task;
  final int pending;

  @override
  Widget build(BuildContext context) {
    final view = TaskViewData(task);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: 8,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text(
                  view.taskTypeLabel,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                Chip(label: Text(view.statusLabel)),
                if (view.priority != 'NORMAL')
                  Chip(
                    avatar: const Icon(Icons.priority_high, size: 16),
                    label: Text('Ưu tiên ${view.priorityLabel}'),
                  ),
              ],
            ),
            const SizedBox(height: 10),
            if (view.guestInRoom)
              const _InlineWarning(
                icon: Icons.person_pin_circle,
                text:
                    'Khách đang trong phòng — phải xác nhận đồng ý trước khi vào.',
              ),
            if (view.specialRequest.isNotEmpty)
              _InlineWarning(
                icon: Icons.star_outline,
                text: 'Yêu cầu đặc biệt: ${view.specialRequest}',
              ),
            if (view.isCheckinRisk)
              _InlineWarning(
                icon: Icons.warning_amber,
                text: 'Nguy cơ không kịp giờ nhận phòng · ${view.dueLabel()}',
              ),
            const SizedBox(height: 10),
            LinearProgressIndicator(
              value: view.progress.clamp(0, 100) / 100,
              minHeight: 10,
              borderRadius: BorderRadius.circular(99),
              semanticsLabel: 'Tiến độ công việc',
              semanticsValue: '${view.progress}%',
            ),
            const SizedBox(height: 6),
            Text(
              '${view.progress}% · ${view.checklistDone}/${view.checklistTotal} mục bắt buộc',
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Icon(
                  pending == 0 ? Icons.cloud_done : Icons.cloud_upload_outlined,
                  size: 18,
                ),
                const SizedBox(width: 6),
                Text(
                  pending == 0 ? 'Đã đồng bộ' : '$pending thay đổi chưa xử lý',
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _InlineWarning extends StatelessWidget {
  const _InlineWarning({required this.icon, required this.text});
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 7),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 19, color: Theme.of(context).colorScheme.error),
        const SizedBox(width: 7),
        Expanded(child: Text(text)),
      ],
    ),
  );
}

class _GeneralSection extends StatelessWidget {
  const _GeneralSection({required this.task});
  final Map<String, Object?> task;

  @override
  Widget build(BuildContext context) {
    final branch = task['branch'] as Map? ?? const {};
    final area = task['area'] as Map? ?? const {};
    final shift = task['shift'] as Map? ?? const {};
    final assignee = task['assignee'] as Map? ?? const {};
    final assignedBy = task['assignedBy'] as Map? ?? const {};
    final requiredSkills = (task['requiredSkills'] as List? ?? const [])
        .whereType<Map>()
        .map((skill) => '${skill['name'] ?? skill['code'] ?? ''}')
        .where((name) => name.isNotEmpty)
        .join(', ');
    return _SectionCard(
      title: 'Thông tin công việc',
      icon: Icons.assignment_outlined,
      initiallyExpanded: true,
      child: _FactsGrid(
        facts: {
          'Mã công việc': task['code'],
          'Chi nhánh': branch['name'],
          'Khu vực': area['name'] ?? (task['room'] as Map?)?['area'],
          'Ca': shift['name'],
          'Bắt đầu dự kiến': shortDateTime(task['scheduledStartAt']),
          'Hạn hoàn thành': shortDateTime(task['dueAt']),
          'Người giao': assignedBy['name'],
          'Người thực hiện': assignee['name'] ?? 'Chưa có',
          'Kỹ năng bắt buộc': requiredSkills.isEmpty
              ? 'Không yêu cầu'
              : requiredSkills,
          'Phiên bản trên máy chủ': task['version'],
          'Cập nhật tiến độ': shortDateTime(task['lastProgressAt']),
        },
      ),
    );
  }
}

class _RoomSection extends StatelessWidget {
  const _RoomSection({required this.task});
  final Map<String, Object?> task;

  @override
  Widget build(BuildContext context) {
    final room = task['room'] as Map? ?? const {};
    final booking = task['booking'] as Map? ?? const {};
    return _SectionCard(
      title: 'Phòng và đặt phòng',
      icon: Icons.meeting_room_outlined,
      initiallyExpanded: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _FactsGrid(
            facts: {
              'Phòng': '${room['code'] ?? ''} · ${room['name'] ?? ''}',
              'Tầng / khu vực':
                  '${room['floor'] ?? '—'} · ${room['area'] ?? '—'}',
              'Loại phòng': viCodeLabel(room['roomType']),
              'Trạng thái phòng': viCodeLabel(room['status']),
              'Đặt phòng': booking['code'] ?? task['bookingCode'],
              'Giờ trả phòng': shortDateTime(booking['checkoutAt']),
              'Giờ nhận phòng tiếp theo': shortDateTime(
                booking['checkinAt'] ?? task['nextCheckinAt'],
              ),
              'Số khách': booking['guestCount'],
            },
          ),
          if (booking['guestName'] != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text('Khách: ${booking['guestName']}'),
            ),
        ],
      ),
    );
  }
}

class _SlaSection extends StatelessWidget {
  const _SlaSection({required this.task});
  final Map<String, Object?> task;

  @override
  Widget build(BuildContext context) {
    final sla = task['sla'] as Map? ?? const {};
    final view = TaskViewData(task);
    return _SectionCard(
      title: 'Thời hạn và thời gian',
      icon: Icons.timer_outlined,
      initiallyExpanded: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Semantics(
            liveRegion: true,
            child: Text(
              view.dueLabel(),
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                color: view.isOverdue
                    ? Theme.of(context).colorScheme.error
                    : null,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
          const SizedBox(height: 8),
          _FactsGrid(
            facts: {
              'Hạn nhận': shortDateTime(
                sla['acceptanceDueAt'] ?? task['acceptanceDueAt'],
              ),
              'Hạn bắt đầu': shortDateTime(
                sla['startDueAt'] ?? task['startDueAt'],
              ),
              'Hạn hoàn thành': shortDateTime(
                sla['completionDueAt'] ?? task['dueAt'],
              ),
              'Nhận phòng tiếp theo': shortDateTime(task['nextCheckinAt']),
              'Thời gian tạm dừng không tính vào hạn': durationLabel(
                sla['excludedPauseSeconds'],
              ),
              'Vi phạm nhận/bắt đầu/hoàn thành': [
                if (sla['acceptanceBreachedAt'] != null) 'Nhận',
                if (sla['startBreachedAt'] != null) 'Bắt đầu',
                if (sla['completionBreachedAt'] != null) 'Hoàn thành',
              ].join(', '),
            },
          ),
        ],
      ),
    );
  }
}

class _ChecklistSection extends StatelessWidget {
  const _ChecklistSection({
    required this.task,
    required this.editable,
    required this.onEdit,
  });
  final Map<String, Object?> task;
  final bool editable;
  final ValueChanged<Map<String, Object?>> onEdit;

  @override
  Widget build(BuildContext context) {
    final rawItems = (task['checklist'] as List? ?? const []).whereType<Map>();
    final groups = <String, List<Map<String, Object?>>>{};
    for (final raw in rawItems) {
      final item = Map<String, Object?>.from(raw);
      groups
          .putIfAbsent(item['group'] as String? ?? 'Khác', () => [])
          .add(item);
    }
    return _SectionCard(
      title: 'Danh sách kiểm tra theo khu vực',
      icon: Icons.checklist,
      initiallyExpanded: true,
      child: groups.isEmpty
          ? const Text('Công việc chưa có danh sách kiểm tra.')
          : Column(
              children: [
                for (final entry in groups.entries)
                  ExpansionTile(
                    initiallyExpanded: true,
                    tilePadding: EdgeInsets.zero,
                    title: Text(
                      '${entry.key} · '
                      '${entry.value.where((item) => item['status'] == 'COMPLETED').length}/'
                      '${entry.value.length}',
                    ),
                    children: [
                      for (final item in entry.value)
                        _ChecklistTile(
                          item: item,
                          editable: editable,
                          onTap: () => onEdit(item),
                        ),
                    ],
                  ),
              ],
            ),
    );
  }
}

class _ChecklistTile extends StatelessWidget {
  const _ChecklistTile({
    required this.item,
    required this.editable,
    required this.onTap,
  });
  final Map<String, Object?> item;
  final bool editable;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final status = item['status'] as String? ?? 'PENDING';
    final icon = switch (status) {
      'COMPLETED' => Icons.check_circle,
      'FAILED' => Icons.error,
      _ => Icons.radio_button_unchecked,
    };
    final color = switch (status) {
      'COMPLETED' => Colors.green,
      'FAILED' => Theme.of(context).colorScheme.error,
      _ => Theme.of(context).colorScheme.outline,
    };
    return Semantics(
      button: editable,
      label: '${item['title']}, ${viCodeLabel(status)}',
      child: ListTile(
        contentPadding: EdgeInsets.zero,
        leading: Icon(icon, color: color),
        title: Text('${item['title']}'),
        subtitle: Text(
          [
            viCodeLabel(item['type']),
            if (item['required'] == true) 'Bắt buộc',
            if (item['requiresPhoto'] == true) 'Cần ảnh',
            if (item['value'] != null) 'Giá trị: ${item['value']}',
            if (status == 'FAILED') 'Lý do: ${item['failureReason']}',
          ].join(' · '),
          maxLines: 3,
          overflow: TextOverflow.ellipsis,
        ),
        trailing: editable ? const Icon(Icons.edit_outlined) : null,
        onTap: editable ? onTap : null,
      ),
    );
  }
}

class _PhotoSection extends StatelessWidget {
  const _PhotoSection({
    required this.task,
    required this.localMedia,
    required this.canAdd,
    required this.onAdd,
  });
  final Map<String, Object?> task;
  final List<LocalMediaPreview> localMedia;
  final bool canAdd;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    final serverPhotos = (task['photos'] as List? ?? const []).whereType<Map>();
    return _SectionCard(
      title: 'Ảnh và trạng thái đồng bộ',
      icon: Icons.photo_library_outlined,
      initiallyExpanded: true,
      trailing: canAdd
          ? IconButton(
              tooltip: 'Chụp hoặc chọn ảnh',
              onPressed: onAdd,
              icon: const Icon(Icons.add_a_photo),
            )
          : null,
      child: serverPhotos.isEmpty && localMedia.isEmpty
          ? const Text('Chưa có ảnh công việc.')
          : GridView.count(
              crossAxisCount: MediaQuery.sizeOf(context).width > 700 ? 4 : 2,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              mainAxisSpacing: 8,
              crossAxisSpacing: 8,
              childAspectRatio: 1.05,
              children: [
                for (final photo in serverPhotos) _ServerPhoto(photo: photo),
                for (final photo in localMedia) _LocalPhoto(photo: photo),
              ],
            ),
    );
  }
}

class _ServerPhoto extends StatelessWidget {
  const _ServerPhoto({required this.photo});
  final Map photo;

  @override
  Widget build(BuildContext context) => Stack(
    fit: StackFit.expand,
    children: [
      ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: photo['url'] is String
            ? Image.network(
                photo['url']! as String,
                fit: BoxFit.cover,
                errorBuilder: (_, _, _) => const ColoredBox(
                  color: Colors.black12,
                  child: Icon(Icons.broken_image_outlined),
                ),
              )
            : const ColoredBox(
                color: Colors.black12,
                child: Icon(Icons.image_not_supported_outlined),
              ),
      ),
      Positioned(
        left: 5,
        bottom: 5,
        child: Chip(
          visualDensity: VisualDensity.compact,
          avatar: const Icon(Icons.cloud_done, size: 14),
          label: Text(viCodeLabel(photo['category'] ?? 'Ảnh')),
        ),
      ),
    ],
  );
}

class _LocalPhoto extends StatelessWidget {
  const _LocalPhoto({required this.photo});
  final LocalMediaPreview photo;

  @override
  Widget build(BuildContext context) => Stack(
    fit: StackFit.expand,
    children: [
      ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: Image.memory(Uint8List.fromList(photo.bytes), fit: BoxFit.cover),
      ),
      Positioned(
        left: 5,
        right: 5,
        bottom: 5,
        child: Chip(
          visualDensity: VisualDensity.compact,
          avatar: Icon(
            photo.state == LocalSyncState.failed
                ? Icons.sync_problem
                : Icons.cloud_upload_outlined,
            size: 14,
          ),
          label: Text(
            '${viCodeLabel(photo.category)} · ${viCodeLabel(photo.state.name.toUpperCase())}',
          ),
        ),
      ),
    ],
  );
}

class _SupportSection extends StatelessWidget {
  const _SupportSection({required this.task});
  final Map<String, Object?> task;

  @override
  Widget build(BuildContext context) {
    final supplies = (task['supplyRequests'] as List? ?? const [])
        .whereType<Map>();
    final issues = (task['issues'] as List? ?? const []).whereType<Map>();
    return _SectionCard(
      title: 'Vật tư và sự cố',
      icon: Icons.support_agent,
      child: supplies.isEmpty && issues.isEmpty
          ? const Text('Chưa có yêu cầu hỗ trợ.')
          : Column(
              children: [
                for (final supply in supplies)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.inventory_2_outlined),
                    title: Text(
                      (supply['items'] as List? ?? const [])
                          .whereType<Map>()
                          .map(
                            (item) => '${item['name']} × ${item['quantity']}',
                          )
                          .join(', '),
                    ),
                    subtitle: Text(
                      '${viCodeLabel(supply['status'])} · ${supply['note'] ?? ''}',
                    ),
                  ),
                for (final issue in issues)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(
                      issue['blocksRoomReady'] == true
                          ? Icons.block
                          : Icons.build_outlined,
                    ),
                    title: Text(
                      '${viCodeLabel(issue['type'])} · ${viCodeLabel(issue['severity'])}',
                    ),
                    subtitle: Text(
                      '${viCodeLabel(issue['status'])} · ${issue['description']}',
                    ),
                  ),
              ],
            ),
    );
  }
}

class _NoteSection extends StatelessWidget {
  const _NoteSection({
    required this.controller,
    required this.canEdit,
    required this.onSave,
  });
  final TextEditingController controller;
  final bool canEdit;
  final VoidCallback onSave;

  @override
  Widget build(BuildContext context) => _SectionCard(
    title: 'Ghi chú',
    icon: Icons.notes,
    child: Column(
      children: [
        TextField(
          controller: controller,
          enabled: canEdit,
          minLines: 2,
          maxLines: 5,
          decoration: const InputDecoration(labelText: 'Ghi chú công việc'),
        ),
        if (canEdit)
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: onSave,
              icon: const Icon(Icons.save),
              label: const Text('Lưu ngoại tuyến'),
            ),
          ),
      ],
    ),
  );
}

class _ReworkSection extends StatelessWidget {
  const _ReworkSection({required this.task});
  final Map<String, Object?> task;

  @override
  Widget build(BuildContext context) {
    final rounds = (task['qcRounds'] as List? ?? const []).whereType<Map>();
    return _SectionCard(
      title: 'Kiểm tra chất lượng và hạng mục làm lại',
      icon: Icons.fact_check_outlined,
      initiallyExpanded: task['status'] == 'QC_REJECTED',
      child: Column(
        children: [
          for (final round in rounds)
            Card.outlined(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Vòng ${round['round']} · ${viCodeLabel(round['status'])}',
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                    Text('Hạn làm lại: ${shortDateTime(round['deadlineAt'])}'),
                    if ('${round['reason'] ?? ''}'.isNotEmpty)
                      Text('Lý do: ${round['reason']}'),
                    if ('${round['note'] ?? ''}'.isNotEmpty)
                      Text('Ghi chú: ${round['note']}'),
                    for (final failed
                        in (round['failedItems'] as List? ?? const [])
                            .whereType<Map>())
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(Icons.replay),
                        title: Text('${failed['title']}'),
                        subtitle: Text(
                          '${viCodeLabel(failed['reasonCode'] ?? '')} · ${failed['reason']}',
                        ),
                      ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _TimelineSection extends StatelessWidget {
  const _TimelineSection({required this.task});
  final Map<String, Object?> task;

  @override
  Widget build(BuildContext context) {
    final events = (task['timeline'] as List? ?? const [])
        .whereType<Map>()
        .toList();
    return _SectionCard(
      title: 'Lịch sử trạng thái',
      icon: Icons.timeline,
      child: events.isEmpty
          ? const Text('Chưa có sự kiện trạng thái.')
          : Column(
              children: [
                for (final event in events.reversed)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.circle, size: 12),
                    title: Text(
                      '${event['fromStatus'] == null ? 'Khởi tạo' : viCodeLabel(event['fromStatus'])} → ${viCodeLabel(event['toStatus'])}',
                    ),
                    subtitle: Text(
                      '${shortDateTime(event['changedAt'])} · '
                      '${(event['changedBy'] as Map?)?['name'] ?? 'Hệ thống'}'
                      '${'${event['reasonCode'] ?? ''}'.isEmpty ? '' : ' · ${viCodeLabel(event['reasonCode'])}'}'
                      '${'${event['note'] ?? ''}'.isEmpty ? '' : '\n${event['note']}'}',
                    ),
                  ),
              ],
            ),
    );
  }
}

class _ActionPanel extends StatelessWidget {
  const _ActionPanel({
    required this.task,
    required this.canAccept,
    required this.canStart,
    required this.canPause,
    required this.canResume,
    required this.canUpdate,
    required this.canComplete,
    required this.pending,
    required this.onAccept,
    required this.onStart,
    required this.onPause,
    required this.onResume,
    required this.onSupply,
    required this.onIssue,
    required this.onComplete,
    required this.onSync,
  });
  final Map<String, Object?> task;
  final bool canAccept;
  final bool canStart;
  final bool canPause;
  final bool canResume;
  final bool canUpdate;
  final bool canComplete;
  final int pending;
  final VoidCallback onAccept;
  final VoidCallback onStart;
  final VoidCallback onPause;
  final VoidCallback onResume;
  final VoidCallback onSupply;
  final VoidCallback onIssue;
  final VoidCallback onComplete;
  final VoidCallback onSync;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Thao tác', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              if (canAccept)
                FilledButton.icon(
                  onPressed: onAccept,
                  icon: const Icon(Icons.assignment_turned_in_outlined),
                  label: const Text('Nhận việc'),
                ),
              if (canStart)
                FilledButton.icon(
                  onPressed: onStart,
                  icon: const Icon(Icons.play_arrow),
                  label: Text(
                    task['status'] == 'QC_REJECTED'
                        ? 'Bắt đầu làm lại'
                        : 'Bắt đầu',
                  ),
                ),
              if (canPause)
                OutlinedButton.icon(
                  onPressed: onPause,
                  icon: const Icon(Icons.pause),
                  label: const Text('Tạm dừng'),
                ),
              if (canResume)
                FilledButton.icon(
                  onPressed: onResume,
                  icon: const Icon(Icons.play_circle_outline),
                  label: const Text('Tiếp tục'),
                ),
              if (canUpdate)
                OutlinedButton.icon(
                  onPressed: onSupply,
                  icon: const Icon(Icons.inventory_2_outlined),
                  label: const Text('Thiếu vật tư'),
                ),
              if (canUpdate)
                OutlinedButton.icon(
                  onPressed: onIssue,
                  icon: const Icon(Icons.build_outlined),
                  label: const Text('Báo sự cố'),
                ),
            ],
          ),
          if (pending > 0) ...[
            const SizedBox(height: 10),
            Text(
              'Còn $pending thay đổi đang chờ, bị lỗi hoặc xung đột. '
              'Không thể hoàn thành cuối.',
            ),
            const SizedBox(height: 8),
            FilledButton.tonalIcon(
              onPressed: onSync,
              icon: const Icon(Icons.cloud_upload),
              label: const Text('Đồng bộ ngay'),
            ),
          ],
          if (_couldCompleteTask) ...[
            const SizedBox(height: 10),
            FilledButton.icon(
              onPressed: canComplete ? onComplete : null,
              icon: const Icon(Icons.task_alt),
              label: const Text('Xem tóm tắt và gửi kiểm tra'),
            ),
          ],
        ],
      ),
    ),
  );

  bool get _couldCompleteTask => task['status'] == 'IN_PROGRESS';
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({
    required this.title,
    required this.icon,
    required this.child,
    this.initiallyExpanded = false,
    this.trailing,
  });
  final String title;
  final IconData icon;
  final Widget child;
  final bool initiallyExpanded;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Card(
    child: ExpansionTile(
      initiallyExpanded: initiallyExpanded,
      leading: Icon(icon),
      title: Text(title),
      trailing: trailing,
      childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      children: [Align(alignment: Alignment.centerLeft, child: child)],
    ),
  );
}

class _FactsGrid extends StatelessWidget {
  const _FactsGrid({required this.facts});
  final Map<String, Object?> facts;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) => Wrap(
      spacing: 10,
      runSpacing: 10,
      children: [
        for (final entry in facts.entries)
          SizedBox(
            width: constraints.maxWidth > 560
                ? (constraints.maxWidth - 10) / 2
                : constraints.maxWidth,
            child: Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surfaceContainerLowest,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(
                  color: Theme.of(context).colorScheme.outlineVariant,
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    entry.key,
                    style: Theme.of(context).textTheme.labelMedium,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    entry.value == null || '${entry.value}'.isEmpty
                        ? '—'
                        : '${entry.value}',
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ],
              ),
            ),
          ),
      ],
    ),
  );
}

final class _PhotoRequest {
  const _PhotoRequest(this.source, this.category);
  final ImageSource source;
  final String category;
}

class _PhotoPickerSheet extends StatefulWidget {
  const _PhotoPickerSheet({required this.qcMode});
  final bool qcMode;

  @override
  State<_PhotoPickerSheet> createState() => _PhotoPickerSheetState();
}

class _PhotoPickerSheetState extends State<_PhotoPickerSheet> {
  late String _category = widget.qcMode ? 'QC' : 'AFTER';

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.all(16),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Thêm ảnh công việc',
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 12),
        if (widget.qcMode)
          const ListTile(
            contentPadding: EdgeInsets.zero,
            leading: Icon(Icons.fact_check_outlined),
            title: Text('Ảnh kiểm tra chất lượng'),
            subtitle: Text('Ảnh sẽ được gắn vào vòng kiểm tra đang mở.'),
          )
        else
          DropdownButtonFormField<String>(
            initialValue: _category,
            decoration: const InputDecoration(labelText: 'Loại ảnh'),
            items: const [
              DropdownMenuItem(value: 'BEFORE', child: Text('Trước khi dọn')),
              DropdownMenuItem(value: 'AFTER', child: Text('Sau khi dọn')),
              DropdownMenuItem(value: 'AREA', child: Text('Theo khu vực')),
              DropdownMenuItem(value: 'ISSUE', child: Text('Sự cố')),
              DropdownMenuItem(value: 'SUPPLY', child: Text('Thiếu vật tư')),
              DropdownMenuItem(value: 'EVIDENCE', child: Text('Bằng chứng')),
            ],
            onChanged: (value) => setState(() => _category = value ?? 'AFTER'),
          ),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: () => Navigator.pop(
            context,
            _PhotoRequest(ImageSource.camera, _category),
          ),
          icon: const Icon(Icons.camera_alt),
          label: const Text('Chụp trực tiếp'),
        ),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: _category == 'EVIDENCE' || widget.qcMode
              ? null
              : () => Navigator.pop(
                  context,
                  _PhotoRequest(ImageSource.gallery, _category),
                ),
          icon: const Icon(Icons.photo_library_outlined),
          label: const Text('Chọn từ thư viện'),
        ),
        if (_category == 'EVIDENCE')
          const Text('Ảnh bằng chứng bắt buộc chỉ cho phép chụp trực tiếp.'),
      ],
    ),
  );
}

class _StartDialog extends StatefulWidget {
  const _StartDialog({required this.guestInRoom});
  final bool guestInRoom;

  @override
  State<_StartDialog> createState() => _StartDialogState();
}

class _StartDialogState extends State<_StartDialog> {
  final _value = TextEditingController();
  final _guestNote = TextEditingController();
  Map<String, Object?>? _location;
  String _method = 'QR_CODE';
  bool _guestConsent = false;
  bool _capturing = false;
  String? _error;

  @override
  void dispose() {
    _value.dispose();
    _guestNote.dispose();
    super.dispose();
  }

  void _submit() {
    if ({'QR_CODE', 'WIFI'}.contains(_method) && _value.text.trim().isEmpty) {
      setState(() => _error = 'Vui lòng thu thập dữ liệu từ thiết bị.');
      return;
    }
    if (_method == 'GPS' && _location == null) {
      setState(() => _error = 'Vui lòng lấy vị trí GPS hiện tại.');
      return;
    }
    if (widget.guestInRoom && !_guestConsent) {
      setState(() => _error = 'Phải xác nhận khách đã đồng ý cho vào phòng.');
      return;
    }
    Navigator.pop(context, <String, Object?>{
      'method': _method,
      if (_method == 'QR_CODE') 'value': _value.text.trim(),
      if (_method == 'WIFI') 'wifiIdentifier': _value.text.trim(),
      if (_method == 'GPS') 'location': _location,
      'guestConsentConfirmed': _guestConsent,
      'guestConsentNote': _guestNote.text.trim(),
    });
  }

  Future<void> _capture() async {
    setState(() {
      _capturing = true;
      _error = null;
    });
    try {
      if (_method == 'QR_CODE') {
        final value = await scanRoomQr(context);
        if (value != null) _value.text = value;
      } else if (_method == 'GPS') {
        _location = await captureLocationEvidence();
        if (_location == null) {
          _error = 'Hãy bật dịch vụ vị trí và cấp quyền cho ứng dụng.';
        }
      } else if (_method == 'WIFI') {
        final value = await captureWifiEvidence();
        if (value == null) {
          _error = 'Không đọc được Wi-Fi đang kết nối hoặc chưa cấp quyền.';
        } else {
          _value.text = value;
        }
      }
    } on Object catch (error) {
      _error = 'Không thể thu thập bằng chứng: $error';
    } finally {
      if (mounted) setState(() => _capturing = false);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Xác minh trước khi bắt đầu'),
    content: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          DropdownButtonFormField<String>(
            initialValue: _method,
            decoration: const InputDecoration(labelText: 'Phương thức'),
            items: const [
              DropdownMenuItem(value: 'QR_CODE', child: Text('QR phòng')),
              DropdownMenuItem(value: 'WIFI', child: Text('Wi-Fi chi nhánh')),
              DropdownMenuItem(value: 'GPS', child: Text('Tọa độ GPS')),
              DropdownMenuItem(value: 'CAMERA', child: Text('Ảnh cửa phòng')),
            ],
            onChanged: (value) => setState(() {
              _method = value ?? 'QR_CODE';
              _value.clear();
              _location = null;
              _error = null;
            }),
          ),
          const SizedBox(height: 10),
          if (_method == 'GPS')
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.my_location),
              title: Text(
                _location == null
                    ? 'Chưa lấy vị trí'
                    : '${_location!['latitude']}, ${_location!['longitude']}',
              ),
              subtitle: _location == null
                  ? const Text('Dùng GPS độ chính xác cao của thiết bị')
                  : Text('Sai số ${_location!['accuracyMeters']} m'),
            )
          else if (_method != 'CAMERA')
            TextField(
              controller: _value,
              readOnly: true,
              decoration: InputDecoration(
                labelText: switch (_method) {
                  'WIFI' => 'BSSID/SSID Wi-Fi từ thiết bị',
                  _ => 'Giá trị QR phòng',
                },
                prefixIcon: Icon(
                  _method == 'WIFI' ? Icons.wifi : Icons.qr_code_scanner,
                ),
              ),
            )
          else
            const ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(Icons.camera_alt),
              title: Text('Máy ảnh sẽ mở sau khi xác nhận'),
              subtitle: Text(
                'Chỉ ảnh chụp trực tiếp trước khi dọn được chấp nhận.',
              ),
            ),
          if (_method != 'CAMERA')
            FilledButton.tonalIcon(
              onPressed: _capturing ? null : _capture,
              icon: _capturing
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Icon(
                      _method == 'GPS'
                          ? Icons.my_location
                          : _method == 'WIFI'
                          ? Icons.wifi_find
                          : Icons.qr_code_scanner,
                    ),
              label: Text(
                _method == 'GPS'
                    ? 'Lấy vị trí hiện tại'
                    : _method == 'WIFI'
                    ? 'Đọc Wi-Fi đang kết nối'
                    : 'Quét mã QR bằng máy ảnh',
              ),
            ),
          if (widget.guestInRoom) ...[
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              value: _guestConsent,
              title: const Text('Khách đã đồng ý cho vào phòng'),
              onChanged: (value) =>
                  setState(() => _guestConsent = value == true),
            ),
            TextField(
              controller: _guestNote,
              decoration: const InputDecoration(
                labelText: 'Ghi chú xác nhận khách',
              ),
            ),
          ],
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Hủy'),
      ),
      FilledButton(
        onPressed: _submit,
        child: const Text('Bắt đầu khi ngoại tuyến'),
      ),
    ],
  );
}

class _PauseDialog extends StatefulWidget {
  const _PauseDialog();

  @override
  State<_PauseDialog> createState() => _PauseDialogState();
}

class _PauseDialogState extends State<_PauseDialog> {
  final _note = TextEditingController();
  String _reason = 'GUEST_IN_ROOM';

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Tạm dừng công việc'),
    content: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        DropdownButtonFormField<String>(
          initialValue: _reason,
          decoration: const InputDecoration(labelText: 'Lý do'),
          items: const [
            DropdownMenuItem(
              value: 'GUEST_IN_ROOM',
              child: Text('Khách chưa rời phòng'),
            ),
            DropdownMenuItem(
              value: 'GUEST_REQUEST_LATER',
              child: Text('Khách yêu cầu quay lại'),
            ),
            DropdownMenuItem(
              value: 'WAITING_SUPPLIES',
              child: Text('Chờ vật tư'),
            ),
            DropdownMenuItem(
              value: 'DEVICE_BROKEN',
              child: Text('Thiết bị hỏng'),
            ),
            DropdownMenuItem(
              value: 'WAITING_TECHNICIAN',
              child: Text('Chờ Kỹ thuật'),
            ),
            DropdownMenuItem(
              value: 'WAITING_MANAGER',
              child: Text('Chờ Quản lý'),
            ),
            DropdownMenuItem(
              value: 'HIGHER_PRIORITY_TASK',
              child: Text('Công việc ưu tiên hơn'),
            ),
            DropdownMenuItem(value: 'BREAK', child: Text('Nghỉ giữa ca')),
            DropdownMenuItem(value: 'OTHER', child: Text('Lý do khác')),
          ],
          onChanged: (value) => setState(() => _reason = value ?? 'OTHER'),
        ),
        const SizedBox(height: 10),
        TextField(
          controller: _note,
          minLines: 2,
          maxLines: 4,
          decoration: const InputDecoration(labelText: 'Ghi chú'),
          onChanged: (_) => setState(() {}),
        ),
      ],
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Hủy'),
      ),
      FilledButton(
        onPressed: _reason == 'OTHER' && _note.text.trim().isEmpty
            ? null
            : () => Navigator.pop(context, <String, Object?>{
                'reasonCode': _reason,
                'note': _note.text.trim(),
              }),
        child: const Text('Tạm dừng'),
      ),
    ],
  );
}

class _SupplyDialog extends StatefulWidget {
  const _SupplyDialog();

  @override
  State<_SupplyDialog> createState() => _SupplyDialogState();
}

class _SupplyDialogState extends State<_SupplyDialog> {
  final _name = TextEditingController();
  final _quantity = TextEditingController(text: '1');
  final _note = TextEditingController();
  String _priority = 'HIGH';

  @override
  void dispose() {
    _name.dispose();
    _quantity.dispose();
    _note.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Báo thiếu vật tư'),
    content: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _name,
            decoration: const InputDecoration(labelText: 'Tên / mã vật tư'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _quantity,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'Số lượng'),
          ),
          const SizedBox(height: 10),
          DropdownButtonFormField<String>(
            initialValue: _priority,
            decoration: const InputDecoration(labelText: 'Mức độ'),
            items: const [
              DropdownMenuItem(value: 'NORMAL', child: Text('Bình thường')),
              DropdownMenuItem(value: 'HIGH', child: Text('Cao')),
              DropdownMenuItem(value: 'URGENT', child: Text('Khẩn cấp')),
            ],
            onChanged: (value) => setState(() => _priority = value ?? 'HIGH'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _note,
            minLines: 2,
            maxLines: 4,
            decoration: const InputDecoration(
              labelText: 'Ghi chú / vị trí cấp',
            ),
          ),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Hủy'),
      ),
      FilledButton(
        onPressed: () {
          final quantity = num.tryParse(_quantity.text.trim());
          if (_name.text.trim().isEmpty || quantity == null || quantity <= 0) {
            return;
          }
          Navigator.pop(context, <String, Object?>{
            'priority': _priority,
            'note': _note.text.trim(),
            'items': [
              {
                'inventoryItemId': _name.text.trim(),
                'name': _name.text.trim(),
                'quantity': quantity,
                'unit': 'Cái',
              },
            ],
          });
        },
        child: const Text('Lưu ngoại tuyến'),
      ),
    ],
  );
}

class _IssueDialog extends StatefulWidget {
  const _IssueDialog();

  @override
  State<_IssueDialog> createState() => _IssueDialogState();
}

class _IssueDialogState extends State<_IssueDialog> {
  final _device = TextEditingController();
  final _description = TextEditingController();
  String _severity = 'HIGH';
  bool _blocksRoom = false;

  @override
  void dispose() {
    _device.dispose();
    _description.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Báo sự cố'),
    content: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _device,
            decoration: const InputDecoration(labelText: 'Thiết bị / khu vực'),
          ),
          const SizedBox(height: 10),
          DropdownButtonFormField<String>(
            initialValue: _severity,
            decoration: const InputDecoration(labelText: 'Mức độ ảnh hưởng'),
            items: const [
              DropdownMenuItem(value: 'NORMAL', child: Text('Bình thường')),
              DropdownMenuItem(value: 'HIGH', child: Text('Cao')),
              DropdownMenuItem(value: 'URGENT', child: Text('Khẩn cấp')),
            ],
            onChanged: (value) => setState(() => _severity = value ?? 'HIGH'),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _description,
            minLines: 3,
            maxLines: 6,
            decoration: const InputDecoration(labelText: 'Mô tả sự cố'),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Chặn phòng chuyển sang sẵn sàng'),
            value: _blocksRoom,
            onChanged: (value) => setState(() => _blocksRoom = value),
          ),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Hủy'),
      ),
      FilledButton(
        onPressed: () {
          if (_description.text.trim().isEmpty) return;
          Navigator.pop(context, <String, Object?>{
            'deviceId': _device.text.trim(),
            'issueType': 'DEVICE_NOT_WORKING',
            'severity': _severity,
            'description': _description.text.trim(),
            'blocksRoomReady': _blocksRoom,
          });
        },
        child: const Text('Lưu ngoại tuyến'),
      ),
    ],
  );
}

class _CompletionDialog extends StatefulWidget {
  const _CompletionDialog({
    required this.task,
    required this.summary,
    required this.localPending,
  });
  final Map<String, Object?> task;
  final Map<String, Object?>? summary;
  final int localPending;

  @override
  State<_CompletionDialog> createState() => _CompletionDialogState();
}

class _CompletionDialogState extends State<_CompletionDialog> {
  bool _confirmed = false;

  @override
  Widget build(BuildContext context) {
    final summary = widget.summary;
    final checklist =
        summary?['checklistSummary'] as Map? ??
        widget.task['checklistSummary'] as Map? ??
        const {};
    final blockers = (summary?['blockers'] as List? ?? const [])
        .whereType<Map>();
    final canComplete =
        widget.localPending == 0 &&
        (summary == null || summary['canComplete'] == true);
    return AlertDialog(
      title: const Text('Tóm tắt hoàn thành'),
      content: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (summary == null)
              const _InlineWarning(
                icon: Icons.cloud_off,
                text:
                    'Đang ngoại tuyến: máy chủ sẽ kiểm tra lại toàn bộ điều kiện chặn khi đồng bộ.',
              ),
            _FactsGrid(
              facts: {
                'Thời gian thực hiện': durationLabel(
                  summary?['activeDurationSeconds'],
                ),
                'Tạm dừng': durationLabel(summary?['pauseSeconds']),
                'Hạng mục bắt buộc':
                    '${checklist['completedRequired'] ?? 0}/${checklist['totalRequired'] ?? 0}',
                'Ảnh bằng chứng':
                    summary?['photoCount'] ?? widget.task['photoCount'],
                'Yêu cầu vật tư':
                    summary?['supplyRequestCount'] ??
                    (widget.task['supplyRequests'] as List? ?? const []).length,
                'Sự cố':
                    summary?['issueCount'] ??
                    (widget.task['issues'] as List? ?? const []).length,
                'Dữ liệu trên thiết bị chưa xử lý': widget.localPending,
              },
            ),
            if (blockers.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(
                'Chưa thể hoàn thành',
                style: TextStyle(
                  color: Theme.of(context).colorScheme.error,
                  fontWeight: FontWeight.w800,
                ),
              ),
              for (final blocker in blockers)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.block),
                  title: Text('${blocker['message']}'),
                  subtitle: Text(viCodeLabel(blocker['code'])),
                ),
            ],
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              value: _confirmed,
              title: const Text('Tôi xác nhận đã kiểm tra cuối phòng'),
              onChanged: canComplete
                  ? (value) => setState(() => _confirmed = value == true)
                  : null,
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context, false),
          child: const Text('Quay lại'),
        ),
        FilledButton(
          onPressed: canComplete && _confirmed
              ? () => Navigator.pop(context, true)
              : null,
          child: const Text('Hoàn thành và gửi kiểm tra'),
        ),
      ],
    );
  }
}
