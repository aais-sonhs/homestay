import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';

import '../api/housekeeping_api.dart';
import '../offline/offline_repository.dart';
import '../offline/sync_engine.dart';
import '../presentation/task_presentation.dart';
import '../security/secure_store.dart';
import 'management_dashboard_screen.dart';
import 'notification_screen.dart';
import 'offline_home_screen.dart';
import 'offline_task_detail_screen.dart';
import 'room_readiness_screen.dart';

class InternalWorkspaceScreen extends StatelessWidget {
  const InternalWorkspaceScreen({
    required this.api,
    required this.repository,
    required this.syncEngine,
    required this.user,
    required this.onSignOut,
    super.key,
  });

  final HousekeepingApi api;
  final OfflineRepository repository;
  final OfflineSyncEngine syncEngine;
  final AppUserProfile user;
  final AsyncCallback onSignOut;

  @override
  Widget build(BuildContext context) {
    if (user.isManagement) {
      return _ManagementWorkspace(
        api: api,
        repository: repository,
        syncEngine: syncEngine,
        user: user,
        onSignOut: onSignOut,
      );
    }
    if (user.isQc) {
      return OfflineHomeScreen(
        api: api,
        repository: repository,
        syncEngine: syncEngine,
        onSignOut: onSignOut,
        title: 'Kiểm tra chất lượng',
        initialTab: HousekeepingTaskTab.waitingQc,
        availableTabs: const [
          HousekeepingTaskTab.waitingQc,
          HousekeepingTaskTab.rework,
          HousekeepingTaskTab.done,
        ],
      );
    }
    if (user.role == 'housekeeping') {
      return OfflineHomeScreen(
        api: api,
        repository: repository,
        syncEngine: syncEngine,
        onSignOut: onSignOut,
        title: 'Công việc buồng phòng',
      );
    }
    return _UnsupportedWorkspace(user: user, onSignOut: onSignOut);
  }
}

class _ManagementWorkspace extends StatefulWidget {
  const _ManagementWorkspace({
    required this.api,
    required this.repository,
    required this.syncEngine,
    required this.user,
    required this.onSignOut,
  });
  final HousekeepingApi api;
  final OfflineRepository repository;
  final OfflineSyncEngine syncEngine;
  final AppUserProfile user;
  final AsyncCallback onSignOut;

  @override
  State<_ManagementWorkspace> createState() => _ManagementWorkspaceState();
}

class _ManagementWorkspaceState extends State<_ManagementWorkspace> {
  int _index = 0;

  Future<void> _openTask(String taskId) => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => OfflineTaskDetailScreen(
        taskId: taskId,
        api: widget.api,
        repository: widget.repository,
        syncEngine: widget.syncEngine,
      ),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final pages = [
      ManagementDashboardScreen(
        api: widget.api,
        repository: widget.repository,
        syncEngine: widget.syncEngine,
        user: widget.user,
        onOpenTasks: () => setState(() => _index = 1),
        onOpenQc: () => setState(() => _index = 3),
        onSignOut: widget.onSignOut,
      ),
      OfflineHomeScreen(
        api: widget.api,
        repository: widget.repository,
        syncEngine: widget.syncEngine,
        onSignOut: widget.onSignOut,
        title: 'Điều phối công việc',
        initialTab: HousekeepingTaskTab.inProgress,
        availableTabs: const [
          HousekeepingTaskTab.available,
          HousekeepingTaskTab.inProgress,
          HousekeepingTaskTab.support,
          HousekeepingTaskTab.waitingQc,
          HousekeepingTaskTab.rework,
          HousekeepingTaskTab.done,
        ],
      ),
      RoomReadinessScreen(api: widget.api),
      OfflineHomeScreen(
        api: widget.api,
        repository: widget.repository,
        syncEngine: widget.syncEngine,
        onSignOut: widget.onSignOut,
        title: 'Kiểm tra chất lượng',
        initialTab: HousekeepingTaskTab.waitingQc,
        availableTabs: const [
          HousekeepingTaskTab.waitingQc,
          HousekeepingTaskTab.rework,
          HousekeepingTaskTab.done,
        ],
      ),
      NotificationScreen(api: widget.api, onTaskSelected: _openTask),
    ];
    return Scaffold(
      body: IndexedStack(index: _index, children: pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (value) => setState(() => _index = value),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard),
            label: 'Tổng quan',
          ),
          NavigationDestination(
            icon: Icon(Icons.assignment_outlined),
            selectedIcon: Icon(Icons.assignment),
            label: 'Công việc',
          ),
          NavigationDestination(
            icon: Icon(Icons.meeting_room_outlined),
            selectedIcon: Icon(Icons.meeting_room),
            label: 'Phòng',
          ),
          NavigationDestination(
            icon: Icon(Icons.fact_check_outlined),
            selectedIcon: Icon(Icons.fact_check),
            label: 'QC',
          ),
          NavigationDestination(
            icon: Icon(Icons.notifications_outlined),
            selectedIcon: Icon(Icons.notifications),
            label: 'Thông báo',
          ),
        ],
      ),
    );
  }
}

class _UnsupportedWorkspace extends StatelessWidget {
  const _UnsupportedWorkspace({required this.user, required this.onSignOut});
  final AppUserProfile user;
  final AsyncCallback onSignOut;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Bliss Home nội bộ')),
    body: Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.construction_outlined, size: 54),
            const SizedBox(height: 16),
            Text(
              'Xin chào ${user.name}',
              style: Theme.of(context).textTheme.headlineSmall,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              'Workspace ${user.roleLabel} sẽ được bổ sung ở giai đoạn tiếp theo.',
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 20),
            OutlinedButton.icon(
              onPressed: onSignOut,
              icon: const Icon(Icons.logout),
              label: const Text('Đăng xuất'),
            ),
          ],
        ),
      ),
    ),
  );
}
