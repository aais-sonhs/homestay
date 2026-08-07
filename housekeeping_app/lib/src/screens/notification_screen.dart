import 'package:flutter/material.dart';

import '../api/housekeeping_api.dart';
import '../presentation/task_presentation.dart';

class NotificationScreen extends StatefulWidget {
  const NotificationScreen({required this.api, this.onTaskSelected, super.key});

  final HousekeepingApi api;
  final ValueChanged<String>? onTaskSelected;

  @override
  State<NotificationScreen> createState() => _NotificationScreenState();
}

class _NotificationScreenState extends State<NotificationScreen> {
  List<Map<String, Object?>> _items = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (mounted) setState(() => _loading = true);
    try {
      final response = await widget.api.notifications();
      _items = (response['items'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, Object?>.from(item))
          .toList(growable: false);
      _error = null;
    } on Object catch (error) {
      _error = 'Không tải được thông báo: $error';
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _open(Map<String, Object?> item) async {
    if (item['readAt'] == null) {
      try {
        await widget.api.markNotificationRead('${item['recipientId']}');
        item['readAt'] = DateTime.now().toUtc().toIso8601String();
      } on Object catch (error) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Không đánh dấu đã đọc được: $error')),
          );
        }
      }
    }
    final taskId = item['taskId'] as String?;
    if (taskId != null && taskId.isNotEmpty && mounted) {
      if (widget.onTaskSelected != null) {
        widget.onTaskSelected!(taskId);
      } else {
        Navigator.pop(context, taskId);
      }
    } else if (mounted) {
      setState(() {});
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Thông báo'),
      actions: [
        IconButton(
          tooltip: 'Tải lại',
          onPressed: _load,
          icon: const Icon(Icons.refresh),
        ),
      ],
      bottom: _loading
          ? const PreferredSize(
              preferredSize: Size.fromHeight(3),
              child: LinearProgressIndicator(),
            )
          : null,
    ),
    body: _error != null && _items.isEmpty
        ? Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Text(_error!),
            ),
          )
        : RefreshIndicator(
            onRefresh: _load,
            child: ListView.separated(
              padding: const EdgeInsets.symmetric(vertical: 8),
              itemCount: _items.length,
              separatorBuilder: (_, _) => const Divider(height: 1),
              itemBuilder: (context, index) {
                final item = _items[index];
                final unread = item['readAt'] == null;
                return ListTile(
                  leading: Icon(
                    unread
                        ? Icons.notifications_active
                        : Icons.notifications_none,
                    color: unread
                        ? Theme.of(context).colorScheme.primary
                        : null,
                  ),
                  title: Text(
                    '${item['title'] ?? 'Thông báo'}',
                    style: TextStyle(
                      fontWeight: unread ? FontWeight.w800 : null,
                    ),
                  ),
                  subtitle: Text(
                    '${item['body'] ?? ''}\n${shortDateTime(item['createdAt'])}',
                  ),
                  isThreeLine: true,
                  trailing: item['taskId'] == null
                      ? null
                      : const Icon(Icons.chevron_right),
                  onTap: () => _open(item),
                );
              },
            ),
          ),
  );
}
