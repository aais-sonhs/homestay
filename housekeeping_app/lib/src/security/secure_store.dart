import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract interface class SecretStore {
  Future<String?> read(String key);

  Future<void> write(String key, String value);

  Future<void> delete(String key);
}

final class FlutterSecretStore implements SecretStore {
  FlutterSecretStore({FlutterSecureStorage? storage})
    : _storage =
          storage ??
          const FlutterSecureStorage(
            aOptions: AndroidOptions(migrateWithBackup: true),
          );

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);

  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

final class SecureTokenStore {
  SecureTokenStore(this._secrets);

  static const _accessTokenKey = 'housekeeping.access_token';
  static const _refreshTokenKey = 'housekeeping.refresh_token';
  static const _userIdKey = 'housekeeping.user_id';
  static const _usernameKey = 'housekeeping.username';
  static const _userNameKey = 'housekeeping.user_name';
  static const _userRoleKey = 'housekeeping.user_role';
  final SecretStore _secrets;

  Future<String?> get accessToken => _secrets.read(_accessTokenKey);

  Future<String?> get refreshToken => _secrets.read(_refreshTokenKey);

  Future<String?> get userId => _secrets.read(_userIdKey);

  Future<AppUserProfile?> get userProfile async {
    final values = await Future.wait([
      _secrets.read(_userIdKey),
      _secrets.read(_usernameKey),
      _secrets.read(_userNameKey),
      _secrets.read(_userRoleKey),
    ]);
    if (values.any((value) => value == null || value.isEmpty)) return null;
    return AppUserProfile(
      id: values[0]!,
      username: values[1]!,
      name: values[2]!,
      role: values[3]!,
    );
  }

  Future<void> save({
    required String accessToken,
    required String refreshToken,
    required AppUserProfile user,
  }) async {
    await _secrets.write(_accessTokenKey, accessToken);
    await _secrets.write(_refreshTokenKey, refreshToken);
    await _secrets.write(_userIdKey, user.id);
    await _secrets.write(_usernameKey, user.username);
    await _secrets.write(_userNameKey, user.name);
    await _secrets.write(_userRoleKey, user.role);
  }

  Future<void> clear() async {
    await _secrets.delete(_accessTokenKey);
    await _secrets.delete(_refreshTokenKey);
    await _secrets.delete(_userIdKey);
    await _secrets.delete(_usernameKey);
    await _secrets.delete(_userNameKey);
    await _secrets.delete(_userRoleKey);
  }
}

final class AppUserProfile {
  const AppUserProfile({
    required this.id,
    required this.username,
    required this.name,
    required this.role,
  });

  factory AppUserProfile.fromMap(Map<Object?, Object?> data) => AppUserProfile(
    id: '${data['id'] ?? ''}',
    username: '${data['username'] ?? ''}',
    name: '${data['name'] ?? data['username'] ?? ''}',
    role: '${data['role'] ?? ''}',
  );

  final String id;
  final String username;
  final String name;
  final String role;

  bool get isManagement =>
      const {'founder', 'branch_owner', 'manager'}.contains(role);

  bool get isQc => role == 'qc';

  String get roleLabel => switch (role) {
    'founder' => 'Quản trị hệ thống',
    'branch_owner' => 'Chủ chi nhánh',
    'manager' => 'Quản lý',
    'housekeeping' => 'Nhân viên buồng phòng',
    'qc' => 'Kiểm tra chất lượng',
    'technician' => 'Kỹ thuật',
    'warehouse' => 'Kho',
    'customer_service' => 'Chăm sóc khách hàng',
    'sales' => 'Kinh doanh',
    _ => role,
  };
}
