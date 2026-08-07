import 'package:flutter/material.dart';

import 'src/api/housekeeping_api.dart';
import 'src/screens/internal_workspace_screen.dart';
import 'src/screens/register_screen.dart';
import 'src/security/secure_store.dart';
import 'src/theme/app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const BlissHomeApp());
}

class BlissHomeApp extends StatefulWidget {
  const BlissHomeApp({super.key});

  @override
  State<BlissHomeApp> createState() => _BlissHomeAppState();
}

class _BlissHomeAppState extends State<BlissHomeApp> {
  late final FlutterSecretStore _secrets;
  late final SecureTokenStore _tokens;
  late final HousekeepingApi _api;
  AppUserProfile? _user;

  @override
  void initState() {
    super.initState();
    _secrets = FlutterSecretStore();
    _tokens = SecureTokenStore(_secrets);
    _api = HousekeepingApi(
      baseUri: Uri.parse(
        const String.fromEnvironment(
          'API_BASE_URL',
          defaultValue: 'https://homestay.aaistech.com',
        ),
      ),
      tokens: _tokens,
    );
  }

  Future<void> _signedIn(AppUserProfile user) async {
    if (mounted) setState(() => _user = user);
  }

  Future<void> _signedOut() async {
    await _api.logout();
    if (mounted) setState(() => _user = null);
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Bliss Home',
    debugShowCheckedModeBanner: false,
    theme: BlissAppTheme.light(),
    home: _user == null
        ? _LoginScreen(api: _api, onSignedIn: _signedIn)
        : InternalWorkspaceScreen(
            api: _api,
            user: _user!,
            onSignOut: _signedOut,
          ),
  );
}

class _LoginScreen extends StatefulWidget {
  const _LoginScreen({required this.api, required this.onSignedIn});

  final HousekeepingApi api;
  final Future<void> Function(AppUserProfile user) onSignedIn;

  @override
  State<_LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<_LoginScreen> {
  final _identifier = TextEditingController();
  final _password = TextEditingController();
  bool _submitting = false;
  bool _obscurePassword = true;
  String? _error;
  String? _registrationNotice;

  Future<void> _submit() async {
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final data = await widget.api.login(
        identifier: _identifier.text,
        password: _password.text,
        deviceName: 'Ứng dụng Bliss Home',
      );
      await widget.onSignedIn(AppUserProfile.fromMap(data['user']! as Map));
    } on Object catch (error) {
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _openRegistration() async {
    final identifier = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(
        builder: (_) => RegisterScreen(api: widget.api),
      ),
    );
    if (identifier == null || !mounted) return;
    setState(() {
      _identifier.text = identifier;
      _registrationNotice =
          'Tài khoản đã được tạo. Nhập mật khẩu để đăng nhập.';
      _error = null;
    });
  }

  @override
  void dispose() {
    _identifier.dispose();
    _password.dispose();
    super.dispose();
  }

  String get _friendlyError {
    final raw = _error ?? '';
    if (raw.contains('401') || raw.toLowerCase().contains('credential')) {
      return 'Tài khoản hoặc mật khẩu chưa đúng. Vui lòng kiểm tra lại.';
    }
    if (raw.toLowerCase().contains('socket') ||
        raw.toLowerCase().contains('connection')) {
      return 'Không kết nối được máy chủ. Hãy kiểm tra Internet và thử lại.';
    }
    return raw.replaceFirst('Exception: ', '');
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    resizeToAvoidBottomInset: true,
    body: Stack(
      children: [
        const Positioned.fill(child: ColoredBox(color: Color(0xfff5f7fc))),
        Positioned(
          top: -150,
          left: -90,
          right: -90,
          child: Container(
            height: 490,
            decoration: const BoxDecoration(
              borderRadius: BorderRadius.vertical(
                bottom: Radius.elliptical(360, 90),
              ),
              gradient: LinearGradient(
                colors: [
                  Color(0xff172554),
                  Color(0xff4338ca),
                  Color(0xff7c3aed),
                ],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
            ),
          ),
        ),
        const Positioned(
          top: 76,
          right: -34,
          child: _LoginOrb(size: 124, opacity: .08),
        ),
        const Positioned(
          top: 196,
          left: -28,
          child: _LoginOrb(size: 82, opacity: .1),
        ),
        SafeArea(
          child: Center(
            child: SingleChildScrollView(
              keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
              padding: const EdgeInsets.fromLTRB(20, 30, 20, 30),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 480),
                child: Column(
                  children: [
                    Container(
                      width: 86,
                      height: 86,
                      padding: const EdgeInsets.all(7),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(25),
                        boxShadow: const [
                          BoxShadow(
                            color: Color(0x44312e81),
                            blurRadius: 30,
                            offset: Offset(0, 14),
                          ),
                        ],
                      ),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(19),
                        child: Image.asset(
                          'assets/branding/app_icon.png',
                          fit: BoxFit.cover,
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      'Bliss Home',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 30,
                        height: 1,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -.8,
                      ),
                    ),
                    const SizedBox(height: 9),
                    const Text(
                      'Vận hành nhẹ nhàng · Chăm sóc trọn vẹn',
                      style: TextStyle(
                        color: Color(0xffddd6fe),
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 30),
                    Container(
                      padding: const EdgeInsets.fromLTRB(23, 25, 23, 22),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(28),
                        border: Border.all(color: const Color(0xffeef0f6)),
                        boxShadow: const [
                          BoxShadow(
                            color: Color(0x1f0f172a),
                            blurRadius: 38,
                            offset: Offset(0, 18),
                          ),
                        ],
                      ),
                      child: AutofillGroup(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Text(
                              'Chào mừng trở lại',
                              style: Theme.of(context).textTheme.headlineSmall,
                            ),
                            const SizedBox(height: 7),
                            Text(
                              'Đăng nhập để xem công việc và tình hình vận hành hôm nay.',
                              style: Theme.of(context).textTheme.bodyMedium,
                            ),
                            if (_registrationNotice != null) ...[
                              const SizedBox(height: 14),
                              Container(
                                padding: const EdgeInsets.all(12),
                                decoration: BoxDecoration(
                                  color: const Color(0xffecfdf5),
                                  borderRadius: BorderRadius.circular(14),
                                  border: Border.all(
                                    color: const Color(0xffa7f3d0),
                                  ),
                                ),
                                child: Row(
                                  children: [
                                    const Icon(
                                      Icons.check_circle_outline_rounded,
                                      color: Color(0xff059669),
                                      size: 20,
                                    ),
                                    const SizedBox(width: 9),
                                    Expanded(
                                      child: Text(
                                        _registrationNotice!,
                                        style: const TextStyle(
                                          color: Color(0xff065f46),
                                          fontSize: 11,
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                            const SizedBox(height: 24),
                            TextField(
                              controller: _identifier,
                              enabled: !_submitting,
                              textInputAction: TextInputAction.next,
                              keyboardType: TextInputType.emailAddress,
                              decoration: const InputDecoration(
                                labelText:
                                    'Tài khoản, email hoặc số điện thoại',
                                prefixIcon: Icon(Icons.person_outline_rounded),
                              ),
                              autofillHints: const [AutofillHints.username],
                            ),
                            const SizedBox(height: 14),
                            TextField(
                              controller: _password,
                              enabled: !_submitting,
                              obscureText: _obscurePassword,
                              textInputAction: TextInputAction.done,
                              decoration: InputDecoration(
                                labelText: 'Mật khẩu',
                                prefixIcon: const Icon(
                                  Icons.lock_outline_rounded,
                                ),
                                suffixIcon: IconButton(
                                  tooltip: _obscurePassword
                                      ? 'Hiện mật khẩu'
                                      : 'Ẩn mật khẩu',
                                  onPressed: () => setState(
                                    () => _obscurePassword = !_obscurePassword,
                                  ),
                                  icon: Icon(
                                    _obscurePassword
                                        ? Icons.visibility_outlined
                                        : Icons.visibility_off_outlined,
                                  ),
                                ),
                              ),
                              autofillHints: const [AutofillHints.password],
                              onSubmitted: (_) {
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
                                        _friendlyError,
                                        style: const TextStyle(
                                          color: Color(0xff991b1b),
                                          fontSize: 12,
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                            const SizedBox(height: 20),
                            DecoratedBox(
                              decoration: BoxDecoration(
                                gradient: const LinearGradient(
                                  colors: [
                                    Color(0xff4f46e5),
                                    Color(0xff7c3aed),
                                  ],
                                ),
                                borderRadius: BorderRadius.circular(16),
                                boxShadow: const [
                                  BoxShadow(
                                    color: Color(0x394f46e5),
                                    blurRadius: 18,
                                    offset: Offset(0, 9),
                                  ),
                                ],
                              ),
                              child: FilledButton.icon(
                                style: FilledButton.styleFrom(
                                  backgroundColor: Colors.transparent,
                                  shadowColor: Colors.transparent,
                                ),
                                onPressed: _submitting ? null : _submit,
                                icon: _submitting
                                    ? const SizedBox.square(
                                        dimension: 19,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                          color: Colors.white,
                                        ),
                                      )
                                    : const Icon(Icons.arrow_forward_rounded),
                                label: Text(
                                  _submitting ? 'Đang đăng nhập…' : 'Đăng nhập',
                                ),
                              ),
                            ),
                            const SizedBox(height: 11),
                            OutlinedButton.icon(
                              onPressed: _submitting ? null : _openRegistration,
                              icon: const Icon(Icons.person_add_alt_1_rounded),
                              label: const Text('Tạo tài khoản mới'),
                            ),
                            const SizedBox(height: 18),
                            const Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(
                                  Icons.shield_outlined,
                                  size: 16,
                                  color: Color(0xff0d9488),
                                ),
                                SizedBox(width: 6),
                                Flexible(
                                  child: Text(
                                    'Kết nối bảo mật tới hệ thống Bliss Home',
                                    textAlign: TextAlign.center,
                                    style: TextStyle(
                                      color: Color(0xff64748b),
                                      fontSize: 11,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 18),
                    const Text(
                      '© 2026 Bliss Home',
                      style: TextStyle(
                        color: Color(0xff94a3b8),
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    ),
  );
}

class _LoginOrb extends StatelessWidget {
  const _LoginOrb({required this.size, required this.opacity});

  final double size;
  final double opacity;

  @override
  Widget build(BuildContext context) => Container(
    width: size,
    height: size,
    decoration: BoxDecoration(
      shape: BoxShape.circle,
      color: Colors.white.withValues(alpha: opacity),
      border: Border.all(color: Colors.white.withValues(alpha: opacity + .04)),
    ),
  );
}
