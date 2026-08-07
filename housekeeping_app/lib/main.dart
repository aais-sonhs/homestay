import 'package:flutter/material.dart';

import 'src/api/housekeeping_api.dart';
import 'src/screens/internal_workspace_screen.dart';
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
  String? _error;

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

  @override
  void dispose() {
    _identifier.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(20),
                      child: Image.asset(
                        'assets/branding/app_icon.png',
                        width: 72,
                        height: 72,
                      ),
                    ),
                    const SizedBox(height: 24),
                    Text(
                      'Bliss Home',
                      style: Theme.of(context).textTheme.headlineMedium
                          ?.copyWith(fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      'Một ứng dụng cho Chủ chi nhánh, Tạp vụ và QC.',
                      style: TextStyle(color: Color(0xff6b7280)),
                    ),
                    const SizedBox(height: 28),
                    TextField(
                      controller: _identifier,
                      decoration: const InputDecoration(
                        labelText: 'Tài khoản / email / số điện thoại',
                        prefixIcon: Icon(Icons.person_outline),
                      ),
                      autofillHints: const [AutofillHints.username],
                    ),
                    const SizedBox(height: 14),
                    TextField(
                      controller: _password,
                      obscureText: true,
                      decoration: const InputDecoration(
                        labelText: 'Mật khẩu',
                        prefixIcon: Icon(Icons.lock_outline),
                      ),
                      autofillHints: const [AutofillHints.password],
                      onSubmitted: (_) => _submit(),
                    ),
                    if (_error != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: Text(
                          _error!,
                          style: TextStyle(
                            color: Theme.of(context).colorScheme.error,
                          ),
                        ),
                      ),
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
                          : const Icon(Icons.login),
                      label: Text(
                        _submitting ? 'Đang đăng nhập…' : 'Đăng nhập',
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  );
}
