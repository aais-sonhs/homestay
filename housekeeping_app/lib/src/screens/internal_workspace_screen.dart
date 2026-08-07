import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';

import '../api/housekeeping_api.dart';
import '../presentation/task_presentation.dart';
import '../security/secure_store.dart';
import 'guest_request_screen.dart';
import 'management_dashboard_screen.dart';
import 'notification_screen.dart';
import 'offline_task_detail_screen.dart';
import 'online_task_list_screen.dart';
import 'room_readiness_screen.dart';
import 'staff_management_screen.dart';

class InternalWorkspaceScreen extends StatelessWidget {
  const InternalWorkspaceScreen({
    required this.api,
    required this.user,
    required this.onSignOut,
    super.key,
  });

  final HousekeepingApi api;
  final AppUserProfile user;
  final AsyncCallback onSignOut;

  @override
  Widget build(BuildContext context) {
    if (user.isManagement) {
      return _ManagementWorkspace(api: api, user: user, onSignOut: onSignOut);
    }
    if (user.isQc) {
      return OnlineTaskListScreen(
        api: api,
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
      return _HousekeepingWorkspace(api: api, user: user, onSignOut: onSignOut);
    }
    if (user.isCustomerService) {
      return _CustomerServiceWorkspace(
        api: api,
        user: user,
        onSignOut: onSignOut,
      );
    }
    return _UnsupportedWorkspace(user: user, onSignOut: onSignOut);
  }
}

class _ManagementWorkspace extends StatefulWidget {
  const _ManagementWorkspace({
    required this.api,
    required this.user,
    required this.onSignOut,
  });
  final HousekeepingApi api;
  final AppUserProfile user;
  final AsyncCallback onSignOut;

  @override
  State<_ManagementWorkspace> createState() => _ManagementWorkspaceState();
}

class _ManagementWorkspaceState extends State<_ManagementWorkspace> {
  int _index = 0;
  final Set<int> _visitedIndexes = {0};
  HousekeepingTaskTab _taskInitialTab = HousekeepingTaskTab.inProgress;
  int _taskListRevision = 0;

  void _selectIndex(int value) {
    if (_index == value) return;
    setState(() {
      _index = value;
      _visitedIndexes.add(value);
    });
  }

  void _openTaskList(HousekeepingTaskTab tab) {
    setState(() {
      _taskInitialTab = tab;
      _taskListRevision++;
      _index = 1;
      _visitedIndexes.add(1);
    });
  }

  Future<void> _openTask(String taskId) => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => OnlineTaskDetailScreen(taskId: taskId, api: widget.api),
    ),
  );

  Future<void> _openStaff() => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => StaffManagementScreen(api: widget.api),
    ),
  );

  @override
  Widget build(BuildContext context) {
    Widget pageAt(int index) => switch (index) {
      0 => ManagementDashboardScreen(
        key: const ValueKey('management-dashboard'),
        api: widget.api,
        user: widget.user,
        onOpenTasks: () => _openTaskList(HousekeepingTaskTab.inProgress),
        onOpenQc: () => _openTaskList(HousekeepingTaskTab.waitingQc),
        onOpenStaff: _openStaff,
        onSignOut: widget.onSignOut,
      ),
      1 => OnlineTaskListScreen(
        key: ValueKey('management-task-list-$_taskListRevision'),
        api: widget.api,
        onSignOut: widget.onSignOut,
        active: _index == 1,
        title: 'Điều phối công việc',
        initialTab: _taskInitialTab,
        availableTabs: const [
          HousekeepingTaskTab.available,
          HousekeepingTaskTab.inProgress,
          HousekeepingTaskTab.support,
          HousekeepingTaskTab.waitingQc,
          HousekeepingTaskTab.rework,
          HousekeepingTaskTab.done,
        ],
      ),
      2 => RoomReadinessScreen(
        key: const ValueKey('management-room-readiness'),
        api: widget.api,
      ),
      3 => GuestRequestScreen(
        key: const ValueKey('management-guest-requests'),
        api: widget.api,
        user: widget.user,
        active: _index == 3,
      ),
      4 => NotificationScreen(
        key: const ValueKey('management-notifications'),
        api: widget.api,
        onTaskSelected: _openTask,
      ),
      _ => const SizedBox.shrink(),
    };
    final pages = List<Widget>.generate(
      5,
      (index) => _visitedIndexes.contains(index)
          ? pageAt(index)
          : const SizedBox.shrink(),
    );
    return Scaffold(
      body: IndexedStack(index: _index, children: pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: _selectIndex,
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
            icon: Icon(Icons.room_service_outlined),
            selectedIcon: Icon(Icons.room_service),
            label: 'Yêu cầu',
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

class _HousekeepingWorkspace extends StatefulWidget {
  const _HousekeepingWorkspace({
    required this.api,
    required this.user,
    required this.onSignOut,
  });
  final HousekeepingApi api;
  final AppUserProfile user;
  final AsyncCallback onSignOut;

  @override
  State<_HousekeepingWorkspace> createState() => _HousekeepingWorkspaceState();
}

class _HousekeepingWorkspaceState extends State<_HousekeepingWorkspace> {
  int _index = 0;

  @override
  Widget build(BuildContext context) => Scaffold(
    body: IndexedStack(
      index: _index,
      children: [
        OnlineTaskListScreen(
          api: widget.api,
          onSignOut: widget.onSignOut,
          title: 'Công việc buồng phòng',
          active: _index == 0,
        ),
        GuestRequestScreen(
          api: widget.api,
          user: widget.user,
          onSignOut: widget.onSignOut,
          active: _index == 1,
        ),
      ],
    ),
    bottomNavigationBar: NavigationBar(
      selectedIndex: _index,
      onDestinationSelected: (value) => setState(() => _index = value),
      destinations: const [
        NavigationDestination(
          icon: Icon(Icons.cleaning_services_outlined),
          selectedIcon: Icon(Icons.cleaning_services),
          label: 'Dọn phòng',
        ),
        NavigationDestination(
          icon: Icon(Icons.room_service_outlined),
          selectedIcon: Icon(Icons.room_service),
          label: 'Khách gọi',
        ),
      ],
    ),
  );
}

class _CustomerServiceWorkspace extends StatefulWidget {
  const _CustomerServiceWorkspace({
    required this.api,
    required this.user,
    required this.onSignOut,
  });
  final HousekeepingApi api;
  final AppUserProfile user;
  final AsyncCallback onSignOut;

  @override
  State<_CustomerServiceWorkspace> createState() =>
      _CustomerServiceWorkspaceState();
}

class _CustomerServiceWorkspaceState extends State<_CustomerServiceWorkspace> {
  int _index = 0;

  @override
  Widget build(BuildContext context) => Scaffold(
    body: IndexedStack(
      index: _index,
      children: [
        GuestRequestScreen(
          api: widget.api,
          user: widget.user,
          onSignOut: widget.onSignOut,
          active: _index == 0,
        ),
        RoomReadinessScreen(
          api: widget.api,
        ),
        NotificationScreen(api: widget.api),
      ],
    ),
    bottomNavigationBar: NavigationBar(
      selectedIndex: _index,
      onDestinationSelected: (value) => setState(() => _index = value),
      destinations: const [
        NavigationDestination(
          icon: Icon(Icons.room_service_outlined),
          selectedIcon: Icon(Icons.room_service),
          label: 'Yêu cầu',
        ),
        NavigationDestination(
          icon: Icon(Icons.meeting_room_outlined),
          selectedIcon: Icon(Icons.meeting_room),
          label: 'Phòng',
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

class _UnsupportedWorkspace extends StatelessWidget {
  const _UnsupportedWorkspace({required this.user, required this.onSignOut});
  final AppUserProfile user;
  final AsyncCallback onSignOut;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Bliss Home')),
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
