import 'package:flutter/material.dart';

import '../api/housekeeping_api.dart';
import '../presentation/task_presentation.dart';
import '../theme/app_theme.dart';

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
  int _loadGeneration = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final generation = ++_loadGeneration;
    if (mounted) setState(() => _loading = true);
    try {
      final response = await widget.api.notifications();
      final items = (response['items'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, Object?>.from(item))
          .toList(growable: false);
      if (!mounted || generation != _loadGeneration) return;
      setState(() {
        _items = items;
        _error = null;
        _loading = false;
      });
    } on Object catch (error) {
      if (!mounted || generation != _loadGeneration) return;
      setState(() {
        _error = 'Không tải được thông báo: $error';
        _loading = false;
      });
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
      title: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Thông báo'),
          Text(
            'Cập nhật vận hành mới nhất',
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
          onPressed: _load,
          icon: const Icon(Icons.refresh_rounded),
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
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
        children: [
          _NotificationHero(
            total: _items.length,
            unread: _items.where((item) => item['readAt'] == null).length,
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            _NotificationError(message: _error!),
          ],
          const SizedBox(height: 20),
          Text('Gần đây', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 10),
          if (_items.isEmpty && !_loading)
            const _NotificationEmpty()
          else
            for (final item in _items) ...[
              _NotificationCard(item: item, onTap: () => _open(item)),
              const SizedBox(height: 10),
            ],
        ],
      ),
    ),
  );
}

class _NotificationHero extends StatelessWidget {
  const _NotificationHero({required this.total, required this.unread});
  final int total;
  final int unread;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(19),
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
          width: 50,
          height: 50,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: .15),
            borderRadius: BorderRadius.circular(17),
          ),
          child: const Icon(
            Icons.notifications_active_outlined,
            color: Colors.white,
            size: 27,
          ),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                unread == 0 ? 'Bạn đã xem hết' : '$unread thông báo chưa đọc',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 19,
                  fontWeight: FontWeight.w900,
                ),
              ),
              const SizedBox(height: 3),
              Text(
                '$total thông báo trong danh sách',
                style: const TextStyle(
                  color: Color(0xffccfbf1),
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ],
    ),
  );
}

class _NotificationCard extends StatelessWidget {
  const _NotificationCard({required this.item, required this.onTap});
  final Map<String, Object?> item;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final unread = item['readAt'] == null;
    final hasTask = item['taskId'] != null;
    final color = unread ? BlissAppTheme.brand : BlissAppTheme.muted;
    return Card(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(19),
        side: BorderSide(
          color: unread ? const Color(0xff99f6e4) : BlissAppTheme.line,
        ),
      ),
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(15),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 43,
                height: 43,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: color.withValues(alpha: .1),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(
                  unread
                      ? Icons.notifications_active_outlined
                      : Icons.notifications_none_rounded,
                  color: color,
                  size: 22,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            '${item['title'] ?? 'Thông báo'}',
                            style: TextStyle(
                              color: BlissAppTheme.ink,
                              fontSize: 16,
                              fontWeight: unread
                                  ? FontWeight.w800
                                  : FontWeight.w700,
                            ),
                          ),
                        ),
                        if (unread)
                          Container(
                            width: 8,
                            height: 8,
                            decoration: const BoxDecoration(
                              color: BlissAppTheme.brand,
                              shape: BoxShape.circle,
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 5),
                    Text(
                      '${item['body'] ?? ''}',
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        const Icon(
                          Icons.schedule_rounded,
                          size: 17,
                          color: BlissAppTheme.muted,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          shortDateTime(item['createdAt']),
                          style: const TextStyle(
                            color: BlissAppTheme.muted,
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const Spacer(),
                        if (hasTask)
                          const Icon(
                            Icons.arrow_forward_rounded,
                            size: 18,
                            color: BlissAppTheme.brand,
                          ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _NotificationError extends StatelessWidget {
  const _NotificationError({required this.message});
  final String message;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(13),
    decoration: BoxDecoration(
      color: const Color(0xfffef2f2),
      borderRadius: BorderRadius.circular(15),
      border: Border.all(color: const Color(0xfffecaca)),
    ),
    child: Row(
      children: [
        const Icon(Icons.cloud_off_outlined, color: Color(0xffdc2626)),
        const SizedBox(width: 9),
        Expanded(
          child: Text(
            message,
            style: const TextStyle(color: Color(0xff991b1b), fontSize: 14),
          ),
        ),
      ],
    ),
  );
}

class _NotificationEmpty extends StatelessWidget {
  const _NotificationEmpty();

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 34),
      child: Column(
        children: [
          Container(
            width: 68,
            height: 68,
            alignment: Alignment.center,
            decoration: const BoxDecoration(
              color: Color(0xffecfdf5),
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.notifications_off_outlined,
              color: Color(0xff059669),
              size: 31,
            ),
          ),
          const SizedBox(height: 14),
          Text(
            'Chưa có thông báo',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 5),
          Text(
            'Các cập nhật mới sẽ xuất hiện tại đây.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    ),
  );
}
