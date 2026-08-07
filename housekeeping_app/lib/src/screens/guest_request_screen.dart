import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../api/housekeeping_api.dart';
import '../security/secure_store.dart';
import '../theme/app_theme.dart';

enum _GuestRequestTab {
  open('Đang mở', null),
  mine('Của tôi', 'mine'),
  done('Đã giao', 'done');

  const _GuestRequestTab(this.label, this.apiValue);
  final String label;
  final String? apiValue;
}

class GuestRequestScreen extends StatefulWidget {
  const GuestRequestScreen({
    required this.api,
    required this.user,
    this.onSignOut,
    this.active = true,
    super.key,
  });

  final HousekeepingApi api;
  final AppUserProfile user;
  final AsyncCallback? onSignOut;
  final bool active;

  @override
  State<GuestRequestScreen> createState() => _GuestRequestScreenState();
}

class _GuestRequestScreenState extends State<GuestRequestScreen> {
  List<Map<String, Object?>> _items = const [];
  Map<String, Object?>? _options;
  _GuestRequestTab _tab = _GuestRequestTab.open;
  Timer? _poller;
  bool _loading = true;
  bool _mutating = false;
  String? _error;
  int _generation = 0;

  bool get _canCreate =>
      widget.user.isManagement || widget.user.isCustomerService;

  @override
  void initState() {
    super.initState();
    if (widget.active) {
      _load();
      _startPolling();
    }
  }

  @override
  void didUpdateWidget(covariant GuestRequestScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.active == widget.active) return;
    if (widget.active) {
      _load();
      _startPolling();
    } else {
      _generation++;
      _poller?.cancel();
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
      final items = await widget.api.guestRequests(
        filters: {
          if (_tab.apiValue != null) 'tab': _tab.apiValue!,
        },
      );
      if (!mounted || generation != _generation) return;
      setState(() {
        _items = items;
        _loading = false;
        _error = null;
      });
    } on Object catch (error) {
      if (!mounted || generation != _generation) return;
      setState(() {
        _loading = false;
        _error = 'Không tải được yêu cầu khách: $error';
      });
    }
  }

  Future<Map<String, Object?>> _loadOptions() async {
    final cached = _options;
    if (cached != null) return cached;
    final options = await widget.api.guestRequestOptions();
    if (mounted) setState(() => _options = options);
    return options;
  }

  Future<void> _runAction(
    Map<String, Object?> item,
    String action, {
    String? assigneeId,
    String? note,
    String? reason,
  }) async {
    if (_mutating) return;
    setState(() => _mutating = true);
    try {
      await widget.api.updateGuestRequest(
        requestId: '${item['id']}',
        action: action,
        version: item['version'] as int? ?? 1,
        assigneeId: assigneeId,
        note: note,
        reason: reason,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(_successMessage(action))),
        );
      }
      await _load(silent: true);
    } on Object catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Không cập nhật được: $error')),
        );
      }
    } finally {
      if (mounted) setState(() => _mutating = false);
    }
  }

  String _successMessage(String action) => switch (action) {
    'accept' => 'Đã nhận yêu cầu.',
    'start' => 'Đã bắt đầu thực hiện.',
    'complete' => 'Đã xác nhận giao cho khách.',
    'assign' => 'Đã phân công nhân viên.',
    'cancel' => 'Đã hủy yêu cầu.',
    _ => 'Đã cập nhật yêu cầu.',
  };

  Future<void> _complete(Map<String, Object?> item) async {
    final controller = TextEditingController(text: 'Đã giao tận tay khách');
    final note = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        icon: const Icon(Icons.check_circle_outline_rounded),
        title: const Text('Xác nhận đã giao khách'),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLines: 2,
          decoration: const InputDecoration(labelText: 'Ghi chú kết quả'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Quay lại'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('Đã giao'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (note != null) await _runAction(item, 'complete', note: note);
  }

  Future<void> _cancel(Map<String, Object?> item) async {
    final controller = TextEditingController();
    final reason = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        icon: const Icon(Icons.cancel_outlined, color: BlissAppTheme.danger),
        title: const Text('Hủy yêu cầu?'),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLines: 2,
          decoration: const InputDecoration(labelText: 'Lý do hủy *'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Giữ yêu cầu'),
          ),
          FilledButton(
            onPressed: () {
              final value = controller.text.trim();
              if (value.isNotEmpty) Navigator.pop(context, value);
            },
            style: FilledButton.styleFrom(backgroundColor: BlissAppTheme.danger),
            child: const Text('Xác nhận hủy'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (reason != null) await _runAction(item, 'cancel', reason: reason);
  }

  Future<void> _assign(Map<String, Object?> item) async {
    try {
      final options = await _loadOptions();
      final branch = Map<String, Object?>.from(item['branch'] as Map? ?? const {});
      final assignees = (options['assignees'] as List? ?? const [])
          .whereType<Map>()
          .map((row) => Map<String, Object?>.from(row))
          .where((row) => '${row['branchId']}' == '${branch['id']}')
          .toList(growable: false);
      if (!mounted) return;
      if (assignees.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Chi nhánh chưa có nhân viên tạp vụ.')),
        );
        return;
      }
      final selected = await showModalBottomSheet<String>(
        context: context,
        showDragHandle: true,
        builder: (context) => SafeArea(
          child: ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(18, 0, 18, 24),
            children: [
              Text('Giao cho tạp vụ', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 12),
              for (final assignee in assignees)
                Card(
                  child: ListTile(
                    minTileHeight: 64,
                    leading: const CircleAvatar(
                      child: Icon(Icons.person_outline_rounded),
                    ),
                    title: Text(
                      '${assignee['name']}',
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () => Navigator.pop(context, '${assignee['id']}'),
                  ),
                ),
            ],
          ),
        ),
      );
      if (selected != null) {
        await _runAction(item, 'assign', assigneeId: selected);
      }
    } on Object catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Không tải được nhân viên: $error')),
        );
      }
    }
  }

  Future<void> _create() async {
    try {
      final options = await _loadOptions();
      if (!mounted) return;
      final created = await Navigator.of(context).push<bool>(
        MaterialPageRoute<bool>(
          builder: (_) => _CreateGuestRequestScreen(
            api: widget.api,
            options: options,
          ),
        ),
      );
      if (created == true) await _load();
    } on Object catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Không mở được biểu mẫu: $error')),
        );
      }
    }
  }

  @override
  void dispose() {
    _poller?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Khách gọi thêm'),
          Text(
            'Nước · khăn · đồ dùng phòng',
            style: TextStyle(
              color: BlissAppTheme.muted,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
      actions: [
        IconButton(
          tooltip: 'Tải lại',
          onPressed: _loading ? null : _load,
          icon: const Icon(Icons.refresh_rounded),
        ),
        if (widget.onSignOut != null)
          IconButton(
            tooltip: 'Đăng xuất',
            onPressed: widget.onSignOut,
            icon: const Icon(Icons.logout_rounded),
          ),
        const SizedBox(width: 6),
      ],
      bottom: _loading
          ? const PreferredSize(
              preferredSize: Size.fromHeight(3),
              child: LinearProgressIndicator(),
            )
          : null,
    ),
    floatingActionButton: _canCreate
        ? FloatingActionButton.extended(
            onPressed: _create,
            icon: const Icon(Icons.add_rounded),
            label: const Text('Tạo yêu cầu'),
          )
        : null,
    body: RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 110),
        children: [
          _GuestRequestSummary(items: _items),
          const SizedBox(height: 14),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: SegmentedButton<_GuestRequestTab>(
              segments: [
                for (final tab in _GuestRequestTab.values)
                  ButtonSegment(value: tab, label: Text(tab.label)),
              ],
              selected: {_tab},
              onSelectionChanged: (selection) {
                setState(() => _tab = selection.first);
                _load();
              },
            ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 14),
            MaterialBanner(
              content: Text(_error!),
              actions: [TextButton(onPressed: _load, child: const Text('Thử lại'))],
            ),
          ],
          const SizedBox(height: 16),
          if (_items.isEmpty && !_loading)
            const _GuestRequestEmpty()
          else
            for (final item in _items) ...[
              _GuestRequestCard(
                item: item,
                disabled: _mutating,
                onAccept: () => _runAction(item, 'accept'),
                onStart: () => _runAction(item, 'start'),
                onComplete: () => _complete(item),
                onAssign: () => _assign(item),
                onCancel: () => _cancel(item),
              ),
              const SizedBox(height: 12),
            ],
        ],
      ),
    ),
  );
}

class _GuestRequestSummary extends StatelessWidget {
  const _GuestRequestSummary({required this.items});
  final List<Map<String, Object?>> items;

  @override
  Widget build(BuildContext context) {
    final urgent = items.where((item) => item['priority'] == 'URGENT').length;
    final overdue = items.where((item) => item['isOverdue'] == true).length;
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [BlissAppTheme.brandDark, Color(0xff0d9488)],
        ),
        borderRadius: BorderRadius.circular(24),
      ),
      child: Row(
        children: [
          const Icon(Icons.room_service_outlined, color: Colors.white, size: 42),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${items.length} yêu cầu trong danh sách',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 19,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '$urgent khẩn cấp · $overdue quá hạn',
                  style: const TextStyle(
                    color: Color(0xffccfbf1),
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _GuestRequestCard extends StatelessWidget {
  const _GuestRequestCard({
    required this.item,
    required this.disabled,
    required this.onAccept,
    required this.onStart,
    required this.onComplete,
    required this.onAssign,
    required this.onCancel,
  });

  final Map<String, Object?> item;
  final bool disabled;
  final VoidCallback onAccept;
  final VoidCallback onStart;
  final VoidCallback onComplete;
  final VoidCallback onAssign;
  final VoidCallback onCancel;

  bool _can(String key) =>
      (item['capabilities'] as Map?)?[key] == true;

  @override
  Widget build(BuildContext context) {
    final room = Map<String, Object?>.from(item['room'] as Map? ?? const {});
    final assignee = Map<String, Object?>.from(item['assignee'] as Map? ?? const {});
    final isOverdue = item['isOverdue'] == true;
    return Card(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(22),
        side: BorderSide(
          color: isOverdue ? const Color(0xfffca5a5) : BlissAppTheme.line,
          width: isOverdue ? 1.5 : 1,
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(17),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: BlissAppTheme.brandSoft,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    'Phòng ${room['code'] ?? '—'}',
                    style: const TextStyle(
                      color: BlissAppTheme.brandDark,
                      fontSize: 17,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                ),
                const Spacer(),
                _StatusChip(
                  label: '${item['statusLabel'] ?? item['status']}',
                  status: '${item['status']}',
                ),
              ],
            ),
            const SizedBox(height: 14),
            Text(
              '${item['description']}',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            Text(
              '${item['quantity']} ${item['unit'] ?? ''} · ${item['requestTypeLabel']}',
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _InfoPill(
                  icon: Icons.schedule_rounded,
                  label: isOverdue
                      ? 'Quá hạn ${_formatDate(item['dueAt'])}'
                      : 'Hạn ${_formatDate(item['dueAt'])}',
                  danger: isOverdue,
                ),
                _InfoPill(
                  icon: Icons.person_outline_rounded,
                  label: assignee.isEmpty
                      ? 'Chưa phân công'
                      : '${assignee['name']}',
                ),
                if (item['priority'] == 'URGENT' || item['priority'] == 'HIGH')
                  _InfoPill(
                    icon: Icons.priority_high_rounded,
                    label: '${item['priorityLabel']}',
                    danger: item['priority'] == 'URGENT',
                  ),
              ],
            ),
            if (_can('accept') ||
                _can('start') ||
                _can('complete') ||
                _can('assign') ||
                _can('cancel')) ...[
              const Divider(height: 28),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  if (_can('accept'))
                    FilledButton.icon(
                      onPressed: disabled ? null : onAccept,
                      icon: const Icon(Icons.pan_tool_alt_outlined),
                      label: const Text('Nhận việc'),
                    ),
                  if (_can('start'))
                    FilledButton.icon(
                      onPressed: disabled ? null : onStart,
                      icon: const Icon(Icons.play_arrow_rounded),
                      label: const Text('Bắt đầu'),
                    ),
                  if (_can('complete'))
                    FilledButton.icon(
                      onPressed: disabled ? null : onComplete,
                      icon: const Icon(Icons.check_rounded),
                      label: const Text('Đã giao khách'),
                    ),
                  if (_can('assign'))
                    OutlinedButton.icon(
                      onPressed: disabled ? null : onAssign,
                      icon: const Icon(Icons.person_add_alt_1_outlined),
                      label: const Text('Phân công'),
                    ),
                  if (_can('cancel'))
                    IconButton(
                      tooltip: 'Hủy yêu cầu',
                      onPressed: disabled ? null : onCancel,
                      color: BlissAppTheme.danger,
                      icon: const Icon(Icons.cancel_outlined),
                    ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.label, required this.status});
  final String label;
  final String status;

  @override
  Widget build(BuildContext context) {
    final (color, background) = switch (status) {
      'COMPLETED' => (const Color(0xff047857), const Color(0xffd1fae5)),
      'CANCELLED' => (BlissAppTheme.danger, const Color(0xfffee2e2)),
      'IN_PROGRESS' => (const Color(0xff1d4ed8), const Color(0xffdbeafe)),
      _ => (const Color(0xff92400e), const Color(0xfffef3c7)),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w800),
      ),
    );
  }
}

class _InfoPill extends StatelessWidget {
  const _InfoPill({required this.icon, required this.label, this.danger = false});
  final IconData icon;
  final String label;
  final bool danger;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
    decoration: BoxDecoration(
      color: danger ? const Color(0xfffef2f2) : const Color(0xfff1f5f9),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          icon,
          size: 17,
          color: danger ? BlissAppTheme.danger : BlissAppTheme.muted,
        ),
        const SizedBox(width: 6),
        Text(
          label,
          style: TextStyle(
            color: danger ? BlissAppTheme.danger : BlissAppTheme.ink,
            fontSize: 13,
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    ),
  );
}

class _GuestRequestEmpty extends StatelessWidget {
  const _GuestRequestEmpty();

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 48),
    child: Column(
      children: [
        const Icon(Icons.room_service_outlined, size: 58, color: BlissAppTheme.muted),
        const SizedBox(height: 14),
        Text('Chưa có yêu cầu', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 6),
        const Text('Kéo xuống để kiểm tra lại.', textAlign: TextAlign.center),
      ],
    ),
  );
}

class _CreateGuestRequestScreen extends StatefulWidget {
  const _CreateGuestRequestScreen({required this.api, required this.options});
  final HousekeepingApi api;
  final Map<String, Object?> options;

  @override
  State<_CreateGuestRequestScreen> createState() =>
      _CreateGuestRequestScreenState();
}

class _CreateGuestRequestScreenState extends State<_CreateGuestRequestScreen> {
  final _formKey = GlobalKey<FormState>();
  final _description = TextEditingController();
  final _quantity = TextEditingController(text: '1');
  final _unit = TextEditingController(text: 'chai');
  String? _bookingId;
  String _requestType = 'WATER';
  String _source = 'ZALO';
  String _priority = 'NORMAL';
  bool _submitting = false;

  List<Map<String, Object?>> _rows(String key) =>
      (widget.options[key] as List? ?? const [])
          .whereType<Map>()
          .map((row) => Map<String, Object?>.from(row))
          .toList(growable: false);

  Future<void> _submit() async {
    if (_submitting || !_formKey.currentState!.validate()) return;
    final booking = _rows('bookings').firstWhere(
      (row) => '${row['id']}' == _bookingId,
    );
    final room = Map<String, Object?>.from(booking['room'] as Map);
    setState(() => _submitting = true);
    try {
      await widget.api.createGuestRequest(
        bookingId: '${booking['id']}',
        branchId: '${booking['branchId']}',
        roomId: '${room['id']}',
        requestType: _requestType,
        description: _description.text.trim(),
        quantity: int.parse(_quantity.text),
        unit: _unit.text.trim(),
        source: _source,
        priority: _priority,
      );
      if (mounted) Navigator.pop(context, true);
    } on Object catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Không tạo được yêu cầu: $error')),
        );
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  void dispose() {
    _description.dispose();
    _quantity.dispose();
    _unit.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bookings = _rows('bookings');
    return Scaffold(
      appBar: AppBar(title: const Text('Tạo yêu cầu cho khách')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 40),
          children: [
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: BlissAppTheme.brandSoft,
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Row(
                children: [
                  Icon(Icons.chat_bubble_outline_rounded, color: BlissAppTheme.brand),
                  SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'Nhập đúng nội dung khách nhắn. Tạp vụ sẽ nhận yêu cầu ngay trên ứng dụng.',
                      style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 18),
            DropdownButtonFormField<String>(
              initialValue: _bookingId,
              decoration: const InputDecoration(
                labelText: 'Phòng / booking đang lưu trú *',
                prefixIcon: Icon(Icons.hotel_outlined),
              ),
              isExpanded: true,
              items: [
                for (final booking in bookings)
                  DropdownMenuItem(
                    value: '${booking['id']}',
                    child: Text(
                      'Phòng ${(booking['room'] as Map)['code']} · ${booking['code']}'
                      '${('${booking['guestName'] ?? ''}').isEmpty ? '' : ' · ${booking['guestName']}'}',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
              ],
              onChanged: (value) => setState(() => _bookingId = value),
              validator: (value) => value == null ? 'Vui lòng chọn phòng.' : null,
            ),
            const SizedBox(height: 14),
            DropdownButtonFormField<String>(
              initialValue: _requestType,
              decoration: const InputDecoration(
                labelText: 'Loại yêu cầu *',
                prefixIcon: Icon(Icons.room_service_outlined),
              ),
              items: [
                for (final row in _rows('requestTypes'))
                  DropdownMenuItem(
                    value: '${row['value']}',
                    child: Text('${row['label']}'),
                  ),
              ],
              onChanged: (value) {
                if (value == null) return;
                setState(() {
                  _requestType = value;
                  if (value == 'WATER') _unit.text = 'chai';
                  if (value == 'TOWEL') _unit.text = 'cái';
                });
              },
            ),
            const SizedBox(height: 14),
            TextFormField(
              controller: _description,
              minLines: 2,
              maxLines: 4,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                labelText: 'Khách cần gì? *',
                hintText: 'Ví dụ: Giao thêm 2 chai nước suối',
                prefixIcon: Icon(Icons.edit_note_rounded),
              ),
              validator: (value) => (value ?? '').trim().isEmpty
                  ? 'Vui lòng nhập nội dung khách yêu cầu.'
                  : null,
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: TextFormField(
                    controller: _quantity,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Số lượng *'),
                    validator: (value) {
                      final number = int.tryParse(value ?? '');
                      return number == null || number < 1 ? 'Từ 1 trở lên' : null;
                    },
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextFormField(
                    controller: _unit,
                    decoration: const InputDecoration(labelText: 'Đơn vị'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            DropdownButtonFormField<String>(
              initialValue: _priority,
              decoration: const InputDecoration(
                labelText: 'Mức ưu tiên',
                prefixIcon: Icon(Icons.priority_high_rounded),
              ),
              items: [
                for (final row in _rows('priorities'))
                  DropdownMenuItem(
                    value: '${row['value']}',
                    child: Text('${row['label']}'),
                  ),
              ],
              onChanged: (value) => setState(() => _priority = value ?? 'NORMAL'),
            ),
            const SizedBox(height: 14),
            DropdownButtonFormField<String>(
              initialValue: _source,
              decoration: const InputDecoration(
                labelText: 'Kênh khách liên hệ',
                prefixIcon: Icon(Icons.forum_outlined),
              ),
              items: [
                for (final row in _rows('sources'))
                  DropdownMenuItem(
                    value: '${row['value']}',
                    child: Text('${row['label']}'),
                  ),
              ],
              onChanged: (value) => setState(() => _source = value ?? 'ZALO'),
            ),
            const SizedBox(height: 22),
            FilledButton.icon(
              onPressed: _submitting || bookings.isEmpty ? null : _submit,
              icon: _submitting
                  ? const SizedBox.square(
                      dimension: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.send_rounded),
              label: Text(_submitting ? 'Đang gửi...' : 'Tạo và chuyển tạp vụ'),
            ),
            if (bookings.isEmpty) ...[
              const SizedBox(height: 12),
              const Text(
                'Chưa có booking ở trạng thái Đã nhận phòng.',
                textAlign: TextAlign.center,
                style: TextStyle(color: BlissAppTheme.danger, fontWeight: FontWeight.w700),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

String _formatDate(Object? raw) {
  final value = DateTime.tryParse('$raw')?.toLocal();
  if (value == null) return '—';
  String two(int number) => number.toString().padLeft(2, '0');
  return '${two(value.hour)}:${two(value.minute)} ${two(value.day)}/${two(value.month)}';
}
