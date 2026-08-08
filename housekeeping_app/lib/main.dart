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
  const BlissHomeApp({super.key, this.secretStore});

  final SecretStore? secretStore;

  @override
  State<BlissHomeApp> createState() => _BlissHomeAppState();
}

class _BlissHomeAppState extends State<BlissHomeApp> {
  late final SecretStore _secrets;
  late final RememberedLoginStore _rememberedLogin;
  late final SecureTokenStore _tokens;
  late final HousekeepingApi _api;
  AppUserProfile? _user;

  @override
  void initState() {
    super.initState();
    _secrets = widget.secretStore ?? FlutterSecretStore();
    _rememberedLogin = RememberedLoginStore(_secrets);
    _tokens = SecureTokenStore(_secrets);
    _api = HousekeepingApi(
      baseUri: Uri.parse(
        const String.fromEnvironment(
          'API_BASE_URL',
          defaultValue: 'https://homestay.aaistech.com',
        ),
      ),
      tokens: _tokens,
      onAuthenticationLost: _authenticationLost,
    );
  }

  Future<void> _authenticationLost() async {
    if (mounted) setState(() => _user = null);
  }

  Future<void> _signedIn(AppUserProfile user) async {
    if (mounted) setState(() => _user = user);
  }

  Future<void> _signedOut() async {
    await _api.logout();
    if (mounted) setState(() => _user = null);
  }

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Bliss Home',
    debugShowCheckedModeBanner: false,
    theme: BlissAppTheme.light(),
    home: _user == null
        ? _LoginScreen(
            api: _api,
            rememberedLogin: _rememberedLogin,
            onSignedIn: _signedIn,
          )
        : InternalWorkspaceScreen(
            api: _api,
            user: _user!,
            onSignOut: _signedOut,
          ),
  );
}

class _LoginScreen extends StatefulWidget {
  const _LoginScreen({
    required this.api,
    required this.rememberedLogin,
    required this.onSignedIn,
  });

  final HousekeepingApi api;
  final RememberedLoginStore rememberedLogin;
  final Future<void> Function(AppUserProfile user) onSignedIn;

  @override
  State<_LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<_LoginScreen> {
  final _identifier = TextEditingController();
  final _password = TextEditingController();
  bool _submitting = false;
  bool _obscurePassword = true;
  bool _rememberLogin = true;
  String? _error;
  String? _registrationNotice;

  @override
  void initState() {
    super.initState();
    _loadRememberedLogin();
  }

  Future<void> _loadRememberedLogin() async {
    try {
      final remembered = await widget.rememberedLogin.load();
      if (!mounted) return;
      setState(() {
        _rememberLogin = remembered.enabled;
        if (_identifier.text.isEmpty && remembered.identifier != null) {
          _identifier.text = remembered.identifier!;
        }
        if (_password.text.isEmpty && remembered.password != null) {
          _password.text = remembered.password!;
        }
      });
    } on Object {
      // Login remains usable if the platform credential vault is unavailable.
    }
  }

  Future<void> _persistRememberedLogin({
    required String identifier,
    required String password,
  }) async {
    try {
      if (_rememberLogin) {
        await widget.rememberedLogin.save(
          identifier: identifier,
          password: password,
        );
      } else {
        await widget.rememberedLogin.clear();
      }
    } on Object {
      // A credential-vault failure must not turn a valid login into a failure.
    }
  }

  Future<void> _submit() async {
    if (_submitting) return;
    FocusScope.of(context).unfocus();
    if (_identifier.text.trim().isEmpty || _password.text.isEmpty) {
      setState(() {
        _error = 'Vui lòng nhập đầy đủ tài khoản và mật khẩu.';
      });
      return;
    }
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final identifier = _identifier.text.trim();
      final password = _password.text;
      final data = await widget.api.login(
        identifier: identifier,
        password: password,
        deviceName: 'Ứng dụng Bliss Home',
      );
      await _persistRememberedLogin(identifier: identifier, password: password);
      await widget.onSignedIn(AppUserProfile.fromMap(data['user']! as Map));
    } on Object catch (error) {
      if (mounted) setState(() => _error = error.toString());
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
        const Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [BlissAppTheme.brandDark, BlissAppTheme.brand],
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
              ),
            ),
          ),
        ),
        SafeArea(
          child: Center(
            child: SingleChildScrollView(
              keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
              padding: const EdgeInsets.fromLTRB(18, 10, 18, 10),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 480),
                child: Column(
                  children: [
                    Container(
                      width: 64,
                      height: 64,
                      padding: const EdgeInsets.all(5),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(color: BlissAppTheme.line, width: 2),
                      ),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(14),
                        child: Image.asset(
                          'assets/branding/app_icon.png',
                          fit: BoxFit.cover,
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Bliss Home',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 24,
                        height: 1,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -.8,
                      ),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      'Vận hành nhẹ nhàng · Chăm sóc trọn vẹn',
                      style: TextStyle(
                        color: Color(0xffccfbf1),
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 14),
                    Container(
                      padding: const EdgeInsets.fromLTRB(18, 18, 18, 16),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(24),
                        border: Border.all(color: BlissAppTheme.line),
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
                              'Xem công việc được giao trong hôm nay.',
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
                                          fontSize: 14,
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                            const SizedBox(height: 16),
                            TextField(
                              controller: _identifier,
                              enabled: !_submitting,
                              textInputAction: TextInputAction.next,
                              keyboardType: TextInputType.emailAddress,
                              decoration: const InputDecoration(
                                labelText: 'Email hoặc số điện thoại',
                                prefixIcon: Icon(Icons.person_outline_rounded),
                              ),
                              autofillHints: const [AutofillHints.username],
                            ),
                            const SizedBox(height: 10),
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
                            CheckboxListTile(
                              value: _rememberLogin,
                              onChanged: _submitting
                                  ? null
                                  : (value) => setState(
                                      () => _rememberLogin = value ?? true,
                                    ),
                              title: const Text('Ghi nhớ mật khẩu'),
                              controlAffinity: ListTileControlAffinity.leading,
                              contentPadding: EdgeInsets.zero,
                              dense: true,
                              visualDensity: VisualDensity.compact,
                              activeColor: BlissAppTheme.brand,
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
                                          fontSize: 14,
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                            const SizedBox(height: 16),
                            DecoratedBox(
                              decoration: BoxDecoration(
                                gradient: const LinearGradient(
                                  colors: [
                                    BlissAppTheme.brand,
                                    Color(0xff0d9488),
                                  ],
                                ),
                                borderRadius: BorderRadius.circular(18),
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
                            const SizedBox(height: 8),
                            OutlinedButton.icon(
                              onPressed: _submitting ? null : _openRegistration,
                              icon: const Icon(Icons.person_add_alt_1_rounded),
                              label: const Text('Tạo tài khoản mới'),
                            ),
                            const SizedBox(height: 12),
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
                                      color: BlissAppTheme.muted,
                                      fontSize: 13,
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
