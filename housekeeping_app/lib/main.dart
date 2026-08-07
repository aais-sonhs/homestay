import 'package:flutter/material.dart';

import 'src/api/housekeeping_api.dart';
import 'src/offline/offline_repository.dart';
import 'src/offline/sync_engine.dart';
import 'src/screens/internal_workspace_screen.dart';
import 'src/security/secure_store.dart';
import 'src/storage/encrypted_database.dart';
import 'src/theme/app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const BlissHomeBootstrapApp());
}

final class _AppDependencies {
  const _AppDependencies({
    required this.tokens,
    required this.api,
    required this.repository,
    required this.syncEngine,
  });

  final SecureTokenStore tokens;
  final HousekeepingApi api;
  final OfflineRepository repository;
  final OfflineSyncEngine syncEngine;
}

class BlissHomeBootstrapApp extends StatefulWidget {
  const BlissHomeBootstrapApp({super.key});

  @override
  State<BlissHomeBootstrapApp> createState() => _BlissHomeBootstrapAppState();
}

class _BlissHomeBootstrapAppState extends State<BlissHomeBootstrapApp> {
  late Future<_AppDependencies> _startup;

  @override
  void initState() {
    super.initState();
    _startup = _initialize();
  }

  Future<_AppDependencies> _initialize() async {
    final secrets = FlutterSecretStore();
    final tokens = SecureTokenStore(secrets);
    final database = await EncryptedHousekeepingDatabase.open(secrets);
    final repository = OfflineRepository(database);
    final api = HousekeepingApi(
      baseUri: Uri.parse(
        const String.fromEnvironment(
          'API_BASE_URL',
          defaultValue: 'https://homestay.aaistech.com',
        ),
      ),
      tokens: tokens,
    );
    final syncEngine = OfflineSyncEngine(repository: repository, api: api)
      ..startAutomaticSync();
    return _AppDependencies(
      tokens: tokens,
      api: api,
      repository: repository,
      syncEngine: syncEngine,
    );
  }

  void _retry() => setState(() => _startup = _initialize());

  @override
  Widget build(BuildContext context) => FutureBuilder<_AppDependencies>(
    future: _startup,
    builder: (context, snapshot) {
      final dependencies = snapshot.data;
      if (dependencies != null) {
        return HousekeepingFieldApp(
          tokens: dependencies.tokens,
          api: dependencies.api,
          repository: dependencies.repository,
          syncEngine: dependencies.syncEngine,
        );
      }
      return MaterialApp(
        title: 'Bliss Home',
        debugShowCheckedModeBanner: false,
        theme: BlissAppTheme.light(),
        home: _StartupScreen(error: snapshot.error, onRetry: _retry),
      );
    },
  );
}

class _StartupScreen extends StatelessWidget {
  const _StartupScreen({required this.error, required this.onRetry});

  final Object? error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(32),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(28),
                  child: Image.asset(
                    'assets/branding/app_icon.png',
                    width: 112,
                    height: 112,
                  ),
                ),
                const SizedBox(height: 24),
                Text(
                  'Bliss Home',
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 12),
                if (error == null) ...[
                  const CircularProgressIndicator(),
                  const SizedBox(height: 16),
                  const Text('Đang khởi động ứng dụng…'),
                ] else ...[
                  Text(
                    'Không thể khởi động ứng dụng',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: Theme.of(context).colorScheme.error,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '$error',
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Color(0xff6b7280)),
                  ),
                  const SizedBox(height: 20),
                  FilledButton.icon(
                    onPressed: onRetry,
                    icon: const Icon(Icons.refresh),
                    label: const Text('Thử lại'),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    ),
  );
}

class HousekeepingFieldApp extends StatefulWidget {
  const HousekeepingFieldApp({
    required this.tokens,
    required this.api,
    required this.repository,
    required this.syncEngine,
    super.key,
  });

  final SecureTokenStore tokens;
  final HousekeepingApi api;
  final OfflineRepository repository;
  final OfflineSyncEngine syncEngine;

  @override
  State<HousekeepingFieldApp> createState() => _HousekeepingFieldAppState();
}

class _HousekeepingFieldAppState extends State<HousekeepingFieldApp> {
  late Future<AppUserProfile?> _session;

  @override
  void initState() {
    super.initState();
    _session = _restoreSession();
  }

  Future<AppUserProfile?> _restoreSession() async {
    final values = await Future.wait([
      widget.tokens.accessToken,
      widget.tokens.userProfile,
    ]);
    if (values[0] == null || values[1] is! AppUserProfile) return null;
    return values[1]! as AppUserProfile;
  }

  Future<void> _signedIn(AppUserProfile user) async {
    try {
      await widget.repository.bindUser(user.id);
    } on Object {
      await widget.api.logout();
      rethrow;
    }
    if (mounted) setState(() => _session = Future.value(user));
  }

  Future<void> _signedOut() async {
    final pending = await widget.repository.unresolvedCount();
    if (pending > 0) {
      throw StateError(
        'Thiết bị còn $pending thay đổi chưa đồng bộ. Hãy đồng bộ trước khi đăng xuất.',
      );
    }
    await widget.repository.clearUserData();
    await widget.api.logout();
    if (mounted) setState(() => _session = Future<AppUserProfile?>.value());
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Bliss Home',
    debugShowCheckedModeBanner: false,
    theme: BlissAppTheme.light(),
    home: FutureBuilder<AppUserProfile?>(
      future: _session,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }
        final user = snapshot.data;
        if (user == null) {
          return _LoginScreen(api: widget.api, onSignedIn: _signedIn);
        }
        return InternalWorkspaceScreen(
          api: widget.api,
          repository: widget.repository,
          syncEngine: widget.syncEngine,
          user: user,
          onSignOut: _signedOut,
        );
      },
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
                    Container(
                      width: 64,
                      height: 64,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(20),
                        gradient: const LinearGradient(
                          colors: [Color(0xff4f46e5), Color(0xff8b5cf6)],
                        ),
                      ),
                      child: const Icon(
                        Icons.hotel_class_outlined,
                        color: Colors.white,
                        size: 32,
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
