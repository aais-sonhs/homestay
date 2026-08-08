import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';

import '../api/housekeeping_api.dart';
import '../presentation/task_presentation.dart';
import '../security/secure_store.dart';
import '../theme/app_theme.dart';
import 'guest_request_screen.dart';
import 'housekeeping_home_screen.dart';
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
  final Set<int> _visitedIndexes = {0};

  void _selectIndex(int value) {
    if (_index == value) return;
    setState(() {
      _index = value;
      _visitedIndexes.add(value);
    });
  }

  Future<void> _openTask(String taskId) => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => OnlineTaskDetailScreen(taskId: taskId, api: widget.api),
    ),
  );

  Future<void> _openRequests() => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => GuestRequestScreen(
        api: widget.api,
        user: widget.user,
        onSignOut: widget.onSignOut,
      ),
    ),
  );

  Future<void> _openIssuePicker() => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => OnlineTaskListScreen(
        api: widget.api,
        onSignOut: widget.onSignOut,
        title: 'Chọn công việc để báo vấn đề',
        availableTabs: const [
          HousekeepingTaskTab.mine,
          HousekeepingTaskTab.inProgress,
          HousekeepingTaskTab.support,
        ],
      ),
    ),
  );

  @override
  Widget build(BuildContext context) {
    Widget pageAt(int index) => switch (index) {
      0 => HousekeepingHomeScreen(
        key: const ValueKey('housekeeping-home'),
        api: widget.api,
        user: widget.user,
        active: _index == 0,
        onOpenTasks: () => _selectIndex(1),
        onOpenRequests: _openRequests,
        onReportIssue: _openIssuePicker,
        onOpenNotifications: () => _selectIndex(2),
        onOpenProfile: () => _selectIndex(3),
      ),
      1 => OnlineTaskListScreen(
        key: const ValueKey('housekeeping-task-list'),
        api: widget.api,
        onSignOut: widget.onSignOut,
        title: 'Công việc buồng phòng',
        active: _index == 1,
      ),
      2 => NotificationScreen(
        key: const ValueKey('housekeeping-messages'),
        api: widget.api,
        onTaskSelected: _openTask,
      ),
      3 => _HousekeepingProfileScreen(
        key: const ValueKey('housekeeping-profile'),
        user: widget.user,
        onSignOut: widget.onSignOut,
      ),
      _ => const SizedBox.shrink(),
    };
    final pages = List<Widget>.generate(
      4,
      (index) => _visitedIndexes.contains(index)
          ? pageAt(index)
          : const SizedBox.shrink(),
    );
    return Scaffold(
      body: IndexedStack(index: _index, children: pages),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerDocked,
      floatingActionButton: SizedBox.square(
        dimension: 62,
        child: FloatingActionButton(
          tooltip: 'Báo vấn đề',
          onPressed: _openIssuePicker,
          backgroundColor: BlissAppTheme.brandDark,
          foregroundColor: Colors.white,
          elevation: 5,
          shape: const CircleBorder(),
          child: const Icon(Icons.add_rounded, size: 34),
        ),
      ),
      bottomNavigationBar: BottomAppBar(
        height: 76,
        padding: const EdgeInsets.symmetric(horizontal: 8),
        color: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 10,
        shadowColor: const Color(0x260f172a),
        shape: const CircularNotchedRectangle(),
        notchMargin: 8,
        child: Row(
          children: [
            _HousekeepingNavItem(
              icon: Icons.home_outlined,
              selectedIcon: Icons.home_rounded,
              label: 'Trang chủ',
              selected: _index == 0,
              onTap: () => _selectIndex(0),
            ),
            _HousekeepingNavItem(
              icon: Icons.assignment_outlined,
              selectedIcon: Icons.assignment_rounded,
              label: 'Công việc',
              selected: _index == 1,
              onTap: () => _selectIndex(1),
            ),
            const SizedBox(width: 68),
            _HousekeepingNavItem(
              icon: Icons.chat_bubble_outline_rounded,
              selectedIcon: Icons.chat_bubble_rounded,
              label: 'Tin nhắn',
              selected: _index == 2,
              onTap: () => _selectIndex(2),
            ),
            _HousekeepingNavItem(
              icon: Icons.person_outline_rounded,
              selectedIcon: Icons.person_rounded,
              label: 'Cá nhân',
              selected: _index == 3,
              onTap: () => _selectIndex(3),
            ),
          ],
        ),
      ),
    );
  }
}

class _HousekeepingNavItem extends StatelessWidget {
  const _HousekeepingNavItem({
    required this.icon,
    required this.selectedIcon,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final IconData icon;
  final IconData selectedIcon;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Expanded(
    child: InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 7),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              selected ? selectedIcon : icon,
              size: 25,
              color: selected ? BlissAppTheme.brandDark : BlissAppTheme.muted,
            ),
            const SizedBox(height: 3),
            Text(
              label,
              maxLines: 1,
              style: TextStyle(
                color: selected ? BlissAppTheme.brandDark : BlissAppTheme.muted,
                fontSize: 10,
                fontWeight: selected ? FontWeight.w900 : FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

class _HousekeepingProfileScreen extends StatelessWidget {
  const _HousekeepingProfileScreen({
    required this.user,
    required this.onSignOut,
    super.key,
  });

  final AppUserProfile user;
  final AsyncCallback onSignOut;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Cá nhân')),
    body: ListView(
      padding: const EdgeInsets.all(18),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(22),
            child: Column(
              children: [
                const CircleAvatar(
                  radius: 39,
                  backgroundColor: BlissAppTheme.brandSoft,
                  child: Icon(
                    Icons.person_rounded,
                    size: 42,
                    color: BlissAppTheme.brandDark,
                  ),
                ),
                const SizedBox(height: 14),
                Text(user.name, style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 4),
                Text(
                  user.roleLabel,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: 3),
                Text(
                  user.username,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 14),
        OutlinedButton.icon(
          onPressed: onSignOut,
          icon: const Icon(Icons.logout_rounded),
          label: const Text('Đăng xuất'),
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
        RoomReadinessScreen(api: widget.api),
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
