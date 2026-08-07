import 'package:flutter/material.dart';

import '../api/housekeeping_api.dart';
import '../presentation/task_presentation.dart';
import '../theme/app_theme.dart';

class RoomReadinessScreen extends StatefulWidget {
  const RoomReadinessScreen({required this.api, super.key});
  final HousekeepingApi api;

  @override
  State<RoomReadinessScreen> createState() => _RoomReadinessScreenState();
}

class _RoomReadinessScreenState extends State<RoomReadinessScreen> {
  final _search = TextEditingController();
  Map<String, Object?> _summary = const {};
  List<Map<String, Object?>> _rooms = const [];
  String _state = '';
  bool _loading = true;
  String? _error;
  int _loadGeneration = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final generation = ++_loadGeneration;
    final query = _search.text;
    final state = _state;
    if (mounted) setState(() => _loading = true);
    try {
      final data = await widget.api.roomReadiness(query: query, state: state);
      final summary = Map<String, Object?>.from(
        data['summary'] as Map? ?? const {},
      );
      final rooms = (data['items'] as List? ?? const [])
          .whereType<Map>()
          .map((row) => Map<String, Object?>.from(row))
          .toList(growable: false);
      if (!mounted || generation != _loadGeneration) return;
      setState(() {
        _summary = summary;
        _rooms = rooms;
        _error = null;
        _loading = false;
      });
    } on Object catch (error) {
      if (!mounted || generation != _loadGeneration) return;
      setState(() {
        _error = 'Không tải được trạng thái phòng: $error';
        _loading = false;
      });
    }
  }

  int _count(String key) => (_summary[key] as num?)?.toInt() ?? 0;

  Future<void> _changeState(String value) async {
    if (_state == value) return;
    setState(() => _state = value);
    await _load();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Trạng thái phòng'),
      actions: [
        IconButton(
          tooltip: 'Tải lại',
          onPressed: _loading ? null : _load,
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
    body: RefreshIndicator(
      onRefresh: _load,
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _RoomSummary(
                    total: _count('total'),
                    ready: _count('ready'),
                    occupied: _count('occupied'),
                    blocked: _count('blocked'),
                    stopSell: _count('stopSell'),
                  ),
                  const SizedBox(height: 16),
                  SearchBar(
                    controller: _search,
                    hintText: 'Tìm mã phòng, tầng hoặc khu vực',
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
                    onChanged: (_) => setState(() {}),
                    onSubmitted: (_) => _load(),
                  ),
                  const SizedBox(height: 12),
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: [
                        for (final entry in const {
                          '': 'Tất cả',
                          'READY': 'Sẵn sàng',
                          'OCCUPIED': 'Có khách',
                          'NOT_READY': 'Chưa sẵn sàng',
                          'BLOCKED': 'Bị chặn',
                        }.entries)
                          Padding(
                            padding: const EdgeInsets.only(right: 7),
                            child: ChoiceChip(
                              selected: _state == entry.key,
                              label: Text(entry.value),
                              onSelected: (_) => _changeState(entry.key),
                            ),
                          ),
                      ],
                    ),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Card(
                      color: Theme.of(context).colorScheme.errorContainer,
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Row(
                          children: [
                            const Icon(Icons.cloud_off_outlined),
                            const SizedBox(width: 10),
                            Expanded(child: Text(_error!)),
                          ],
                        ),
                      ),
                    ),
                  ],
                  const SizedBox(height: 16),
                  Text(
                    '${_rooms.length} phòng',
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ],
              ),
            ),
          ),
          if (_rooms.isEmpty && !_loading)
            const SliverFillRemaining(
              hasScrollBody: false,
              child: Center(
                child: Padding(
                  padding: EdgeInsets.all(28),
                  child: Text(
                    'Không có phòng phù hợp với bộ lọc.',
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
            )
          else
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
              sliver: SliverList.builder(
                itemCount: _rooms.length,
                itemBuilder: (context, index) => _RoomReadinessCard(
                  row: _rooms[index],
                  onTap: () => _showRoomDetails(context, _rooms[index]),
                ),
              ),
            ),
        ],
      ),
    ),
  );
}

class _RoomSummary extends StatelessWidget {
  const _RoomSummary({
    required this.total,
    required this.ready,
    required this.occupied,
    required this.blocked,
    required this.stopSell,
  });
  final int total;
  final int ready;
  final int occupied;
  final int blocked;
  final int stopSell;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(18),
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(28),
      gradient: const LinearGradient(
        colors: [BlissAppTheme.brandDark, Color(0xff0d9488)],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Row(
          children: [
            Icon(Icons.meeting_room_outlined, color: Colors.white),
            SizedBox(width: 9),
            Text(
              'Tình trạng toàn chi nhánh',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _SummaryChip(label: 'Tổng', value: total),
            _SummaryChip(label: 'Sẵn sàng', value: ready),
            _SummaryChip(label: 'Có khách', value: occupied),
            _SummaryChip(label: 'Bị chặn', value: blocked),
            _SummaryChip(label: 'Dừng bán', value: stopSell),
          ],
        ),
      ],
    ),
  );
}

class _SummaryChip extends StatelessWidget {
  const _SummaryChip({required this.label, required this.value});
  final String label;
  final int value;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 8),
    decoration: BoxDecoration(
      color: Colors.white.withValues(alpha: .16),
      borderRadius: BorderRadius.circular(13),
      border: Border.all(color: Colors.white.withValues(alpha: .2)),
    ),
    child: Text(
      '$label · $value',
      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
    ),
  );
}

class _RoomReadinessCard extends StatelessWidget {
  const _RoomReadinessCard({required this.row, required this.onTap});
  final Map<String, Object?> row;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final room = row['room'] as Map? ?? const {};
    final branch = row['branch'] as Map? ?? const {};
    final state = '${row['state'] ?? 'NOT_READY'}';
    final accent = _stateColor(state);
    final blockers = row['blockers'] as List? ?? const [];
    final nextBooking = row['nextBooking'] as Map?;
    final stopSell = row['salesStatus'] == 'STOP_SELL';
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Card(
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              border: Border(left: BorderSide(color: accent, width: 4)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${room['code'] ?? ''} · ${room['name'] ?? ''}',
                            style: const TextStyle(
                              fontSize: 19,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                          Text(
                            [branch['name'], room['floor'], room['area']]
                                .where(
                                  (item) => item != null && '$item'.isNotEmpty,
                                )
                                .join(' · '),
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ],
                      ),
                    ),
                    _StateBadge(
                      label: '${row['stateLabel'] ?? viCodeLabel(state)}',
                      color: accent,
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 7,
                  children: [
                    _RoomFact(
                      icon: Icons.assignment_outlined,
                      label: '${row['activeTaskCount'] ?? 0} việc mở',
                    ),
                    _RoomFact(
                      icon: stopSell
                          ? Icons.block_outlined
                          : Icons.sell_outlined,
                      label: '${row['salesStatusLabel'] ?? ''}',
                      color: stopSell ? const Color(0xffdc2626) : null,
                    ),
                    if (row['checkinRisk'] == true)
                      const _RoomFact(
                        icon: Icons.warning_amber_rounded,
                        label: 'Rủi ro check-in',
                        color: Color(0xffd97706),
                      ),
                  ],
                ),
                if (blockers.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: const Color(0xfffef2f2),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      '${(blockers.first as Map)['label']}'
                      '${blockers.length > 1 ? ' · +${blockers.length - 1} blocker' : ''}',
                      style: const TextStyle(
                        color: Color(0xff991b1b),
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
                if (nextBooking != null) ...[
                  const SizedBox(height: 12),
                  Text(
                    'Booking tiếp theo ${nextBooking['code']} · '
                    '${shortDateTime(nextBooking['checkinAt'])}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _StateBadge extends StatelessWidget {
  const _StateBadge({required this.label, required this.color});
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
    decoration: BoxDecoration(
      color: color.withValues(alpha: .12),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 6),
        Text(
          label,
          style: TextStyle(
            color: color,
            fontSize: 13,
            fontWeight: FontWeight.w900,
          ),
        ),
      ],
    ),
  );
}

class _RoomFact extends StatelessWidget {
  const _RoomFact({required this.icon, required this.label, this.color});
  final IconData icon;
  final String label;
  final Color? color;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Icon(icon, size: 18, color: color),
      const SizedBox(width: 4),
      Text(
        label,
        style: TextStyle(
          fontSize: 14,
          color: color,
          fontWeight: FontWeight.w600,
        ),
      ),
    ],
  );
}

Color _stateColor(String state) => switch (state) {
  'READY' => const Color(0xff059669),
  'OCCUPIED' => const Color(0xff2563eb),
  'BLOCKED' => const Color(0xffdc2626),
  _ => const Color(0xffd97706),
};

Future<void> _showRoomDetails(BuildContext context, Map<String, Object?> row) {
  final room = row['room'] as Map? ?? const {};
  final blockers = row['blockers'] as List? ?? const [];
  final stopSells = row['activeStopSells'] as List? ?? const [];
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (context) => Padding(
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 28),
      child: ListView(
        shrinkWrap: true,
        children: [
          Text(
            '${room['code'] ?? ''} · ${room['name'] ?? ''}',
            style: Theme.of(
              context,
            ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 5),
          Text('${row['stateLabel']} · ${row['salesStatusLabel']}'),
          const SizedBox(height: 18),
          if (blockers.isEmpty)
            const ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(Icons.verified_outlined, color: Color(0xff059669)),
              title: Text('Không có blocker vận hành'),
            )
          else ...[
            const Text(
              'Điều kiện đang chặn',
              style: TextStyle(fontWeight: FontWeight.w800),
            ),
            for (final blocker in blockers.whereType<Map>())
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(
                  Icons.error_outline,
                  color: Color(0xffdc2626),
                ),
                title: Text('${blocker['label']}'),
              ),
          ],
          if (stopSells.isNotEmpty) ...[
            const Divider(height: 28),
            const Text(
              'Dừng bán đang hiệu lực',
              style: TextStyle(fontWeight: FontWeight.w800),
            ),
            for (final stopSell in stopSells.whereType<Map>())
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.block, color: Color(0xffdc2626)),
                title: Text('${stopSell['reason']}'),
                subtitle: Text(
                  'Dự kiến ${shortDateTime(stopSell['plannedEndAt'])}',
                ),
              ),
          ],
          const SizedBox(height: 8),
          FilledButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Đóng'),
          ),
        ],
      ),
    ),
  );
}
