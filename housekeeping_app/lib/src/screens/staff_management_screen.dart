import 'package:flutter/material.dart';

import '../api/housekeeping_api.dart';

class StaffManagementScreen extends StatefulWidget {
  const StaffManagementScreen({required this.api, super.key});

  final HousekeepingApi api;

  @override
  State<StaffManagementScreen> createState() => _StaffManagementScreenState();
}

class _StaffManagementScreenState extends State<StaffManagementScreen> {
  final _query = TextEditingController();
  List<_StaffBranch> _branches = const [];
  List<_StaffRole> _roles = const [];
  List<_StaffMember> _members = const [];
  String? _selectedBranchId;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (mounted) setState(() => _loading = true);
    try {
      final data = await widget.api.staff(
        branchId: _selectedBranchId,
        query: _query.text,
      );
      final branches = (data['branches'] as List? ?? const [])
          .whereType<Map>()
          .map(_StaffBranch.fromMap)
          .toList(growable: false);
      if (_selectedBranchId != null &&
          !branches.any((branch) => branch.id == _selectedBranchId)) {
        _selectedBranchId = null;
      }
      _branches = branches;
      _roles = (data['roleOptions'] as List? ?? const [])
          .whereType<Map>()
          .map(_StaffRole.fromMap)
          .toList(growable: false);
      _members = (data['items'] as List? ?? const [])
          .whereType<Map>()
          .map(_StaffMember.fromMap)
          .toList(growable: false);
      _error = null;
    } on Object catch (error) {
      _error = error.toString();
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openCreate() async {
    if (_branches.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Bạn chưa có chi nhánh nào để tạo nhân viên.'),
        ),
      );
      return;
    }
    final created = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => _CreateStaffScreen(
          api: widget.api,
          branches: _branches,
          roles: _roles,
          initialBranchId: _selectedBranchId,
        ),
      ),
    );
    if (created != true || !mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Đã tạo tài khoản và gán chi nhánh.')),
    );
    await _load();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Nhân sự chi nhánh'),
          Text(
            'Tài khoản và quyền làm việc',
            style: TextStyle(
              color: Color(0xff94a3b8),
              fontSize: 10,
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
      ],
      bottom: _loading
          ? const PreferredSize(
              preferredSize: Size.fromHeight(3),
              child: LinearProgressIndicator(),
            )
          : null,
    ),
    floatingActionButton: _branches.isEmpty
        ? null
        : FloatingActionButton.extended(
            onPressed: _openCreate,
            icon: const Icon(Icons.person_add_alt_1_rounded),
            label: const Text('Tạo nhân viên'),
          ),
    body: RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 104),
        children: [
          _StaffHero(
            total: _members.length,
            branchCount: _branches.length,
            onCreate: _openCreate,
            canCreate: _branches.isNotEmpty,
          ),
          const SizedBox(height: 14),
          _FiltersCard(
            query: _query,
            branches: _branches,
            selectedBranchId: _selectedBranchId,
            onBranchChanged: (value) {
              setState(() => _selectedBranchId = value);
              _load();
            },
            onSearch: _load,
          ),
          if (_error != null) ...[
            const SizedBox(height: 14),
            _StaffError(message: _error!, onRetry: _load),
          ],
          const SizedBox(height: 20),
          Row(
            children: [
              Expanded(
                child: Text(
                  'Danh sách nhân sự',
                  style: Theme.of(
                    context,
                  ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
                ),
              ),
              Text(
                '${_members.length} người',
                style: const TextStyle(
                  color: Color(0xff64748b),
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if (!_loading && _branches.isEmpty)
            const _StaffEmpty(
              icon: Icons.apartment_rounded,
              title: 'Chưa có chi nhánh được quản lý',
              message:
                  'Tài khoản này cần được gán quyền quản lý chi nhánh trước.',
            )
          else if (!_loading && _members.isEmpty)
            _StaffEmpty(
              icon: Icons.groups_2_outlined,
              title: 'Chưa có nhân sự phù hợp',
              message: _query.text.trim().isEmpty
                  ? 'Tạo tài khoản đầu tiên và gán thẳng vào chi nhánh.'
                  : 'Hãy đổi từ khóa hoặc bộ lọc chi nhánh.',
            )
          else
            for (final member in _members) ...[
              _StaffCard(member: member),
              const SizedBox(height: 10),
            ],
        ],
      ),
    ),
  );
}

class _CreateStaffScreen extends StatefulWidget {
  const _CreateStaffScreen({
    required this.api,
    required this.branches,
    required this.roles,
    this.initialBranchId,
  });

  final HousekeepingApi api;
  final List<_StaffBranch> branches;
  final List<_StaffRole> roles;
  final String? initialBranchId;

  @override
  State<_CreateStaffScreen> createState() => _CreateStaffScreenState();
}

class _CreateStaffScreenState extends State<_CreateStaffScreen> {
  final _formKey = GlobalKey<FormState>();
  final _fullName = TextEditingController();
  final _email = TextEditingController();
  final _phone = TextEditingController();
  final _password = TextEditingController();
  final _confirmPassword = TextEditingController();
  late String _branchId;
  late String _roleKey;
  bool _submitting = false;
  bool _hidePassword = true;
  bool _hideConfirmation = true;
  String? _error;

  _StaffBranch get _branch =>
      widget.branches.firstWhere((branch) => branch.id == _branchId);

  List<_StaffRole> get _availableRoles => widget.roles
      .where((role) => role.key != 'manager' || _branch.canCreateManager)
      .toList(growable: false);

  @override
  void initState() {
    super.initState();
    _branchId =
        widget.branches.any((branch) => branch.id == widget.initialBranchId)
        ? widget.initialBranchId!
        : widget.branches.first.id;
    final available = _availableRoles;
    _roleKey = available.any((role) => role.key == 'housekeeping')
        ? 'housekeeping'
        : available.first.key;
  }

  @override
  void dispose() {
    _fullName.dispose();
    _email.dispose();
    _phone.dispose();
    _password.dispose();
    _confirmPassword.dispose();
    super.dispose();
  }

  String? _required(String? value, String label) {
    if ((value ?? '').trim().isEmpty) return 'Vui lòng nhập $label.';
    return null;
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.api.createStaff(
        fullName: _fullName.text.trim(),
        email: _email.text.trim(),
        phoneNumber: _phone.text.trim(),
        branchId: _branchId,
        roleKey: _roleKey,
        password: _password.text,
        confirmPassword: _confirmPassword.text,
      );
      if (mounted) Navigator.pop(context, true);
    } on Object catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Tạo tài khoản nhân viên'),
      bottom: _submitting
          ? const PreferredSize(
              preferredSize: Size.fromHeight(3),
              child: LinearProgressIndicator(),
            )
          : null,
    ),
    body: SafeArea(
      child: SingleChildScrollView(
        keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 560),
            child: Form(
              key: _formKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const _CreateStaffHero(),
                  const SizedBox(height: 14),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text(
                            'Phạm vi làm việc',
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                          const SizedBox(height: 16),
                          DropdownButtonFormField<String>(
                            initialValue: _branchId,
                            decoration: const InputDecoration(
                              labelText: 'Chi nhánh',
                              prefixIcon: Icon(Icons.apartment_rounded),
                            ),
                            items: [
                              for (final branch in widget.branches)
                                DropdownMenuItem(
                                  value: branch.id,
                                  child: Text(branch.name),
                                ),
                            ],
                            onChanged: _submitting
                                ? null
                                : (value) {
                                    if (value == null) return;
                                    setState(() {
                                      _branchId = value;
                                      if (!_availableRoles.any(
                                        (role) => role.key == _roleKey,
                                      )) {
                                        _roleKey = _availableRoles.first.key;
                                      }
                                    });
                                  },
                          ),
                          const SizedBox(height: 14),
                          DropdownButtonFormField<String>(
                            key: ValueKey('role-$_branchId-$_roleKey'),
                            initialValue: _roleKey,
                            decoration: const InputDecoration(
                              labelText: 'Vai trò',
                              prefixIcon: Icon(
                                Icons.admin_panel_settings_outlined,
                              ),
                            ),
                            items: [
                              for (final role in _availableRoles)
                                DropdownMenuItem(
                                  value: role.key,
                                  child: Text(role.label),
                                ),
                            ],
                            onChanged: _submitting
                                ? null
                                : (value) {
                                    if (value != null) {
                                      setState(() => _roleKey = value);
                                    }
                                  },
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: AutofillGroup(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Text(
                              'Thông tin đăng nhập',
                              style: Theme.of(context).textTheme.titleLarge,
                            ),
                            const SizedBox(height: 16),
                            TextFormField(
                              controller: _fullName,
                              enabled: !_submitting,
                              textCapitalization: TextCapitalization.words,
                              textInputAction: TextInputAction.next,
                              autofillHints: const [AutofillHints.name],
                              decoration: const InputDecoration(
                                labelText: 'Họ và tên',
                                prefixIcon: Icon(Icons.badge_outlined),
                              ),
                              validator: (value) =>
                                  _required(value, 'họ và tên'),
                            ),
                            const SizedBox(height: 14),
                            TextFormField(
                              controller: _email,
                              enabled: !_submitting,
                              keyboardType: TextInputType.emailAddress,
                              textInputAction: TextInputAction.next,
                              autofillHints: const [AutofillHints.email],
                              decoration: const InputDecoration(
                                labelText: 'Email đăng nhập',
                                prefixIcon: Icon(Icons.alternate_email_rounded),
                              ),
                              validator: (value) {
                                final required = _required(value, 'email');
                                if (required != null) return required;
                                if (!value!.contains('@')) {
                                  return 'Email chưa đúng định dạng.';
                                }
                                return null;
                              },
                            ),
                            const SizedBox(height: 14),
                            TextFormField(
                              controller: _phone,
                              enabled: !_submitting,
                              keyboardType: TextInputType.phone,
                              textInputAction: TextInputAction.next,
                              autofillHints: const [
                                AutofillHints.telephoneNumber,
                              ],
                              decoration: const InputDecoration(
                                labelText: 'Số điện thoại',
                                prefixIcon: Icon(Icons.phone_outlined),
                              ),
                              validator: (value) =>
                                  _required(value, 'số điện thoại'),
                            ),
                            const SizedBox(height: 14),
                            TextFormField(
                              controller: _password,
                              enabled: !_submitting,
                              obscureText: _hidePassword,
                              textInputAction: TextInputAction.next,
                              autofillHints: const [AutofillHints.newPassword],
                              decoration: InputDecoration(
                                labelText: 'Mật khẩu tạm thời',
                                prefixIcon: const Icon(Icons.lock_outline),
                                suffixIcon: IconButton(
                                  onPressed: () => setState(
                                    () => _hidePassword = !_hidePassword,
                                  ),
                                  icon: Icon(
                                    _hidePassword
                                        ? Icons.visibility_outlined
                                        : Icons.visibility_off_outlined,
                                  ),
                                ),
                              ),
                              validator: (value) {
                                final required = _required(value, 'mật khẩu');
                                if (required != null) return required;
                                if (value!.length < 8) {
                                  return 'Mật khẩu phải có ít nhất 8 ký tự.';
                                }
                                return null;
                              },
                            ),
                            const SizedBox(height: 14),
                            TextFormField(
                              controller: _confirmPassword,
                              enabled: !_submitting,
                              obscureText: _hideConfirmation,
                              textInputAction: TextInputAction.done,
                              onFieldSubmitted: (_) => _submit(),
                              decoration: InputDecoration(
                                labelText: 'Nhập lại mật khẩu',
                                prefixIcon: const Icon(
                                  Icons.verified_user_outlined,
                                ),
                                suffixIcon: IconButton(
                                  onPressed: () => setState(
                                    () =>
                                        _hideConfirmation = !_hideConfirmation,
                                  ),
                                  icon: Icon(
                                    _hideConfirmation
                                        ? Icons.visibility_outlined
                                        : Icons.visibility_off_outlined,
                                  ),
                                ),
                              ),
                              validator: (value) {
                                if (value != _password.text) {
                                  return 'Xác nhận mật khẩu chưa khớp.';
                                }
                                return null;
                              },
                            ),
                            const SizedBox(height: 12),
                            const Text(
                              'Mật khẩu cần có chữ hoa, chữ thường, số và ký tự đặc biệt.',
                              style: TextStyle(
                                color: Color(0xff64748b),
                                fontSize: 12,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    _StaffError(message: _error!, onRetry: _submit),
                  ],
                  const SizedBox(height: 20),
                  FilledButton.icon(
                    onPressed: _submitting ? null : _submit,
                    icon: _submitting
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.person_add_alt_1_rounded),
                    label: Text(
                      _submitting
                          ? 'Đang tạo tài khoản...'
                          : 'Tạo và gán chi nhánh',
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    ),
  );
}

class _StaffBranch {
  const _StaffBranch({
    required this.id,
    required this.code,
    required this.name,
    required this.staffCount,
    required this.canCreateManager,
  });

  factory _StaffBranch.fromMap(Map data) => _StaffBranch(
    id: '${data['id'] ?? ''}',
    code: '${data['code'] ?? ''}',
    name: '${data['name'] ?? ''}',
    staffCount: (data['staffCount'] as num?)?.toInt() ?? 0,
    canCreateManager: data['canCreateManager'] == true,
  );

  final String id;
  final String code;
  final String name;
  final int staffCount;
  final bool canCreateManager;
}

class _StaffRole {
  const _StaffRole({required this.key, required this.label});

  factory _StaffRole.fromMap(Map data) =>
      _StaffRole(key: '${data['key'] ?? ''}', label: '${data['label'] ?? ''}');

  final String key;
  final String label;
}

class _StaffMember {
  const _StaffMember({
    required this.name,
    required this.email,
    required this.phoneNumber,
    required this.roleLabel,
    required this.isActive,
    required this.branchName,
    required this.branchCode,
  });

  factory _StaffMember.fromMap(Map data) {
    final branch = data['branch'] as Map? ?? const {};
    return _StaffMember(
      name: '${data['name'] ?? ''}',
      email: '${data['email'] ?? ''}',
      phoneNumber: '${data['phoneNumber'] ?? ''}',
      roleLabel: '${data['roleLabel'] ?? ''}',
      isActive: data['isActive'] == true,
      branchName: '${branch['name'] ?? ''}',
      branchCode: '${branch['code'] ?? ''}',
    );
  }

  final String name;
  final String email;
  final String phoneNumber;
  final String roleLabel;
  final bool isActive;
  final String branchName;
  final String branchCode;
}

class _StaffHero extends StatelessWidget {
  const _StaffHero({
    required this.total,
    required this.branchCount,
    required this.onCreate,
    required this.canCreate,
  });

  final int total;
  final int branchCount;
  final VoidCallback onCreate;
  final bool canCreate;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(23),
      gradient: const LinearGradient(
        colors: [Color(0xff0f766e), Color(0xff0d9488), Color(0xff14b8a6)],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
      boxShadow: const [
        BoxShadow(
          color: Color(0x330d9488),
          blurRadius: 28,
          offset: Offset(0, 14),
        ),
      ],
    ),
    child: Row(
      children: [
        Container(
          width: 54,
          height: 54,
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: .16),
            borderRadius: BorderRadius.circular(18),
          ),
          child: const Icon(
            Icons.groups_2_rounded,
            color: Colors.white,
            size: 30,
          ),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '$total nhân sự',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 21,
                  fontWeight: FontWeight.w800,
                ),
              ),
              Text(
                'trên $branchCount chi nhánh được quản lý',
                style: const TextStyle(
                  color: Color(0xffccfbf1),
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
        IconButton.filledTonal(
          tooltip: 'Tạo nhân viên',
          onPressed: canCreate ? onCreate : null,
          icon: const Icon(Icons.person_add_alt_1_rounded),
        ),
      ],
    ),
  );
}

class _FiltersCard extends StatelessWidget {
  const _FiltersCard({
    required this.query,
    required this.branches,
    required this.selectedBranchId,
    required this.onBranchChanged,
    required this.onSearch,
  });

  final TextEditingController query;
  final List<_StaffBranch> branches;
  final String? selectedBranchId;
  final ValueChanged<String?> onBranchChanged;
  final VoidCallback onSearch;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          TextField(
            controller: query,
            textInputAction: TextInputAction.search,
            onSubmitted: (_) => onSearch(),
            decoration: InputDecoration(
              labelText: 'Tìm tên, email hoặc số điện thoại',
              prefixIcon: const Icon(Icons.search_rounded),
              suffixIcon: IconButton(
                tooltip: 'Tìm kiếm',
                onPressed: onSearch,
                icon: const Icon(Icons.arrow_forward_rounded),
              ),
            ),
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            initialValue: selectedBranchId ?? '',
            decoration: const InputDecoration(
              labelText: 'Lọc theo chi nhánh',
              prefixIcon: Icon(Icons.apartment_rounded),
            ),
            items: [
              const DropdownMenuItem<String>(
                value: '',
                child: Text('Tất cả chi nhánh'),
              ),
              for (final branch in branches)
                DropdownMenuItem<String>(
                  value: branch.id,
                  child: Text('${branch.name} · ${branch.staffCount}'),
                ),
            ],
            onChanged: (value) =>
                onBranchChanged(value == null || value.isEmpty ? null : value),
          ),
        ],
      ),
    ),
  );
}

class _StaffCard extends StatelessWidget {
  const _StaffCard({required this.member});

  final _StaffMember member;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 48,
            height: 48,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: const Color(0xffeef2ff),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Text(
              member.name.isEmpty
                  ? 'N'
                  : member.name.characters.first.toUpperCase(),
              style: const TextStyle(
                color: Color(0xff4338ca),
                fontSize: 19,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
          const SizedBox(width: 13),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        member.name,
                        style: Theme.of(context).textTheme.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w800),
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: member.isActive
                            ? const Color(0xffecfdf5)
                            : const Color(0xfff1f5f9),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: Text(
                        member.isActive ? 'Hoạt động' : 'Tạm khóa',
                        style: TextStyle(
                          color: member.isActive
                              ? const Color(0xff047857)
                              : const Color(0xff64748b),
                          fontSize: 10,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  member.roleLabel,
                  style: const TextStyle(
                    color: Color(0xff4f46e5),
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 10),
                _StaffLine(
                  icon: Icons.apartment_rounded,
                  text: '${member.branchName} · ${member.branchCode}',
                ),
                if (member.email.isNotEmpty)
                  _StaffLine(
                    icon: Icons.mail_outline_rounded,
                    text: member.email,
                  ),
                if (member.phoneNumber.isNotEmpty)
                  _StaffLine(
                    icon: Icons.phone_outlined,
                    text: member.phoneNumber,
                  ),
              ],
            ),
          ),
        ],
      ),
    ),
  );
}

class _StaffLine extends StatelessWidget {
  const _StaffLine({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 4),
    child: Row(
      children: [
        Icon(icon, size: 15, color: const Color(0xff94a3b8)),
        const SizedBox(width: 7),
        Expanded(
          child: Text(
            text,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Color(0xff64748b), fontSize: 12),
          ),
        ),
      ],
    ),
  );
}

class _CreateStaffHero extends StatelessWidget {
  const _CreateStaffHero();

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(23),
      gradient: const LinearGradient(
        colors: [Color(0xff3730a3), Color(0xff4f46e5), Color(0xff7c3aed)],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
    ),
    child: const Row(
      children: [
        Icon(Icons.person_add_alt_1_rounded, color: Colors.white, size: 34),
        SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Nhân sự mới',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                ),
              ),
              SizedBox(height: 3),
              Text(
                'Tài khoản sẽ dùng được ngay sau khi tạo.',
                style: TextStyle(color: Color(0xffe0e7ff), fontSize: 12),
              ),
            ],
          ),
        ),
      ],
    ),
  );
}

class _StaffError extends StatelessWidget {
  const _StaffError({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(15),
    decoration: BoxDecoration(
      color: const Color(0xfffef2f2),
      borderRadius: BorderRadius.circular(17),
      border: Border.all(color: const Color(0xfffecaca)),
    ),
    child: Row(
      children: [
        const Icon(Icons.error_outline_rounded, color: Color(0xffdc2626)),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            message,
            style: const TextStyle(color: Color(0xff991b1b), fontSize: 12),
          ),
        ),
        TextButton(onPressed: onRetry, child: const Text('Thử lại')),
      ],
    ),
  );
}

class _StaffEmpty extends StatelessWidget {
  const _StaffEmpty({
    required this.icon,
    required this.title,
    required this.message,
  });

  final IconData icon;
  final String title;
  final String message;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(26),
      child: Column(
        children: [
          Icon(icon, size: 44, color: const Color(0xff94a3b8)),
          const SizedBox(height: 12),
          Text(
            title,
            textAlign: TextAlign.center,
            style: Theme.of(
              context,
            ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 5),
          Text(
            message,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Color(0xff64748b)),
          ),
        ],
      ),
    ),
  );
}
