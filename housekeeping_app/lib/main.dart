import 'package:flutter/material.dart';

import 'src/api/housekeeping_api.dart';
import 'src/offline/offline_repository.dart';
import 'src/offline/sync_engine.dart';
import 'src/screens/offline_home_screen.dart';
import 'src/security/secure_store.dart';
import 'src/storage/encrypted_database.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
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
  runApp(
    HousekeepingFieldApp(
      tokens: tokens,
      api: api,
      repository: repository,
      syncEngine: syncEngine,
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
  late Future<bool> _authenticated;

  @override
  void initState() {
    super.initState();
    _authenticated = Future.wait([
      widget.tokens.accessToken,
      widget.tokens.userId,
    ]).then((values) => values.every((value) => value != null));
  }

  Future<void> _signedIn(String userId) async {
    try {
      await widget.repository.bindUser(userId);
    } on Object {
      await widget.api.logout();
      rethrow;
    }
    if (mounted) setState(() => _authenticated = Future.value(true));
  }

  Future<void> _signedOut() async {
    await widget.repository.clearUserData();
    await widget.api.logout();
    if (mounted) setState(() => _authenticated = Future.value(false));
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Bliss Home Buồng phòng',
    theme: ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff126b5b)),
      useMaterial3: true,
    ),
    home: FutureBuilder<bool>(
      future: _authenticated,
      builder: (context, snapshot) {
        if (!snapshot.hasData) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }
        if (!snapshot.data!) {
          return _LoginScreen(api: widget.api, onSignedIn: _signedIn);
        }
        return OfflineHomeScreen(
          api: widget.api,
          repository: widget.repository,
          syncEngine: widget.syncEngine,
          onSignOut: _signedOut,
        );
      },
    ),
  );
}

class _LoginScreen extends StatefulWidget {
  const _LoginScreen({required this.api, required this.onSignedIn});

  final HousekeepingApi api;
  final Future<void> Function(String userId) onSignedIn;

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
        deviceName: 'Ứng dụng buồng phòng hiện trường',
      );
      await widget.onSignedIn((data['user']! as Map)['id']! as String);
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
    appBar: AppBar(title: const Text('Đăng nhập buồng phòng')),
    body: ListView(
      padding: const EdgeInsets.all(24),
      children: [
        TextField(
          controller: _identifier,
          decoration: const InputDecoration(
            labelText: 'Tài khoản / thư điện tử / số điện thoại',
          ),
          autofillHints: const [AutofillHints.username],
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _password,
          obscureText: true,
          decoration: const InputDecoration(labelText: 'Mật khẩu'),
          autofillHints: const [AutofillHints.password],
          onSubmitted: (_) => _submit(),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        const SizedBox(height: 20),
        FilledButton(
          onPressed: _submitting ? null : _submit,
          child: Text(_submitting ? 'Đang đăng nhập…' : 'Đăng nhập'),
        ),
      ],
    ),
  );
}
