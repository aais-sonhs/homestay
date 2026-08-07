import 'package:flutter/material.dart';

import '../api/housekeeping_api.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({required this.api, super.key});

  final HousekeepingApi api;

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _fullName = TextEditingController();
  final _email = TextEditingController();
  final _phone = TextEditingController();
  final _password = TextEditingController();
  final _confirmPassword = TextEditingController();
  bool _submitting = false;
  bool _completed = false;
  bool _hidePassword = true;
  bool _hideConfirmation = true;
  String? _error;

  @override
  void dispose() {
    _fullName.dispose();
    _email.dispose();
    _phone.dispose();
    _password.dispose();
    _confirmPassword.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.api.register(
        fullName: _fullName.text.trim(),
        email: _email.text.trim(),
        phoneNumber: _phone.text.trim(),
        password: _password.text,
        confirmPassword: _confirmPassword.text,
      );
      if (mounted) setState(() => _completed = true);
    } on Object catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  String? _required(String? value, String label) {
    if ((value ?? '').trim().isEmpty) return 'Vui lòng nhập $label.';
    return null;
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Tạo tài khoản'),
          Text(
            'Bliss Home',
            style: TextStyle(
              color: Color(0xff94a3b8),
              fontSize: 10,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    ),
    body: SafeArea(child: _completed ? _success(context) : _form(context)),
  );

  Widget _success(BuildContext context) => Center(
    child: SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480),
        child: Column(
          children: [
            Container(
              width: 92,
              height: 92,
              alignment: Alignment.center,
              decoration: const BoxDecoration(
                color: Color(0xffecfdf5),
                shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.check_rounded,
                color: Color(0xff059669),
                size: 48,
              ),
            ),
            const SizedBox(height: 22),
            Text(
              'Tài khoản đã sẵn sàng',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 9),
            Text(
              'Bạn có thể đăng nhập bằng ${_email.text.trim()}.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 20),
            Container(
              padding: const EdgeInsets.all(15),
              decoration: BoxDecoration(
                color: const Color(0xfffffbeb),
                borderRadius: BorderRadius.circular(17),
                border: Border.all(color: const Color(0xfffde68a)),
              ),
              child: const Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    Icons.admin_panel_settings_outlined,
                    color: Color(0xffd97706),
                  ),
                  SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'Tài khoản mới chưa được gán chi nhánh. Hãy liên hệ quản trị viên để được cấp vai trò và phạm vi làm việc.',
                      style: TextStyle(
                        color: Color(0xff92400e),
                        fontSize: 12,
                        height: 1.5,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: () => Navigator.pop(context, _email.text.trim()),
                icon: const Icon(Icons.login_rounded),
                label: const Text('Đăng nhập ngay'),
              ),
            ),
          ],
        ),
      ),
    ),
  );

  Widget _form(BuildContext context) => SingleChildScrollView(
    keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
    padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
    child: Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520),
        child: Form(
          key: _formKey,
          child: AutofillGroup(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(23),
                    gradient: const LinearGradient(
                      colors: [
                        Color(0xff3730a3),
                        Color(0xff4f46e5),
                        Color(0xff7c3aed),
                      ],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    boxShadow: const [
                      BoxShadow(
                        color: Color(0x304f46e5),
                        blurRadius: 26,
                        offset: Offset(0, 13),
                      ),
                    ],
                  ),
                  child: const Row(
                    children: [
                      _RegistrationIcon(),
                      SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Tham gia Bliss Home',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 19,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                            SizedBox(height: 4),
                            Text(
                              'Tạo tài khoản an toàn trong vài bước.',
                              style: TextStyle(
                                color: Color(0xffddd6fe),
                                fontSize: 11,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          'Thông tin tài khoản',
                          style: Theme.of(context).textTheme.titleLarge,
                        ),
                        const SizedBox(height: 5),
                        Text(
                          'Dùng email hoặc số điện thoại này để đăng nhập.',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                        const SizedBox(height: 20),
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
                          validator: (value) {
                            final required = _required(value, 'họ và tên');
                            if (required != null) return required;
                            if (value!.trim().length < 2) {
                              return 'Họ và tên phải có ít nhất 2 ký tự.';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 13),
                        TextFormField(
                          controller: _email,
                          enabled: !_submitting,
                          keyboardType: TextInputType.emailAddress,
                          textInputAction: TextInputAction.next,
                          autofillHints: const [AutofillHints.email],
                          decoration: const InputDecoration(
                            labelText: 'Thư điện tử',
                            prefixIcon: Icon(Icons.mail_outline_rounded),
                          ),
                          validator: (value) {
                            final required = _required(value, 'thư điện tử');
                            if (required != null) return required;
                            final email = value!.trim();
                            if (!email.contains('@') ||
                                !email.split('@').last.contains('.')) {
                              return 'Thư điện tử không đúng định dạng.';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 13),
                        TextFormField(
                          controller: _phone,
                          enabled: !_submitting,
                          keyboardType: TextInputType.phone,
                          textInputAction: TextInputAction.next,
                          autofillHints: const [AutofillHints.telephoneNumber],
                          decoration: const InputDecoration(
                            labelText: 'Số điện thoại',
                            hintText: 'Ví dụ: 0901234567',
                            prefixIcon: Icon(Icons.phone_outlined),
                          ),
                          validator: (value) {
                            final required = _required(value, 'số điện thoại');
                            if (required != null) return required;
                            final digits = value!.replaceAll(
                              RegExp(r'[^0-9]'),
                              '',
                            );
                            if (digits.length < 9) {
                              return 'Số điện thoại không đúng định dạng.';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 13),
                        TextFormField(
                          controller: _password,
                          enabled: !_submitting,
                          obscureText: _hidePassword,
                          textInputAction: TextInputAction.next,
                          autofillHints: const [AutofillHints.newPassword],
                          decoration: InputDecoration(
                            labelText: 'Mật khẩu',
                            prefixIcon: const Icon(Icons.lock_outline_rounded),
                            suffixIcon: IconButton(
                              tooltip: _hidePassword
                                  ? 'Hiện mật khẩu'
                                  : 'Ẩn mật khẩu',
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
                        const SizedBox(height: 8),
                        const Text(
                          'Ít nhất 8 ký tự, gồm chữ hoa, chữ thường, số và ký tự đặc biệt.',
                          style: TextStyle(
                            color: Color(0xff64748b),
                            fontSize: 10,
                            height: 1.45,
                          ),
                        ),
                        const SizedBox(height: 13),
                        TextFormField(
                          controller: _confirmPassword,
                          enabled: !_submitting,
                          obscureText: _hideConfirmation,
                          textInputAction: TextInputAction.done,
                          autofillHints: const [AutofillHints.newPassword],
                          decoration: InputDecoration(
                            labelText: 'Xác nhận mật khẩu',
                            prefixIcon: const Icon(
                              Icons.verified_user_outlined,
                            ),
                            suffixIcon: IconButton(
                              tooltip: _hideConfirmation
                                  ? 'Hiện mật khẩu'
                                  : 'Ẩn mật khẩu',
                              onPressed: () => setState(
                                () => _hideConfirmation = !_hideConfirmation,
                              ),
                              icon: Icon(
                                _hideConfirmation
                                    ? Icons.visibility_outlined
                                    : Icons.visibility_off_outlined,
                              ),
                            ),
                          ),
                          validator: (value) {
                            final required = _required(
                              value,
                              'xác nhận mật khẩu',
                            );
                            if (required != null) return required;
                            if (value != _password.text) {
                              return 'Xác nhận mật khẩu không khớp.';
                            }
                            return null;
                          },
                          onFieldSubmitted: (_) {
                            if (!_submitting) _submit();
                          },
                        ),
                        if (_error != null) ...[
                          const SizedBox(height: 14),
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: const Color(0xfffef2f2),
                              borderRadius: BorderRadius.circular(14),
                              border: Border.all(
                                color: const Color(0xfffecaca),
                              ),
                            ),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Icon(
                                  Icons.error_outline_rounded,
                                  color: Color(0xffdc2626),
                                  size: 20,
                                ),
                                const SizedBox(width: 9),
                                Expanded(
                                  child: Text(
                                    _error!,
                                    style: const TextStyle(
                                      color: Color(0xff991b1b),
                                      fontSize: 11,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                        const SizedBox(height: 20),
                        FilledButton.icon(
                          onPressed: _submitting ? null : _submit,
                          icon: _submitting
                              ? const SizedBox.square(
                                  dimension: 18,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    color: Colors.white,
                                  ),
                                )
                              : const Icon(Icons.person_add_alt_1_rounded),
                          label: Text(
                            _submitting
                                ? 'Đang tạo tài khoản…'
                                : 'Tạo tài khoản',
                          ),
                        ),
                        const SizedBox(height: 9),
                        TextButton(
                          onPressed: _submitting
                              ? null
                              : () => Navigator.pop(context),
                          child: const Text('Đã có tài khoản? Đăng nhập'),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}

class _RegistrationIcon extends StatelessWidget {
  const _RegistrationIcon();

  @override
  Widget build(BuildContext context) => Container(
    width: 50,
    height: 50,
    alignment: Alignment.center,
    decoration: BoxDecoration(
      color: Colors.white.withValues(alpha: .14),
      borderRadius: BorderRadius.circular(17),
      border: Border.all(color: Colors.white.withValues(alpha: .16)),
    ),
    child: const Icon(
      Icons.person_add_alt_1_rounded,
      color: Colors.white,
      size: 27,
    ),
  );
}
