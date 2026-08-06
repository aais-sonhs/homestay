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
  final SecretStore _secrets;

  Future<String?> get accessToken => _secrets.read(_accessTokenKey);

  Future<String?> get refreshToken => _secrets.read(_refreshTokenKey);

  Future<String?> get userId => _secrets.read(_userIdKey);

  Future<void> save({
    required String accessToken,
    required String refreshToken,
    required String userId,
  }) async {
    await _secrets.write(_accessTokenKey, accessToken);
    await _secrets.write(_refreshTokenKey, refreshToken);
    await _secrets.write(_userIdKey, userId);
  }

  Future<void> clear() async {
    await _secrets.delete(_accessTokenKey);
    await _secrets.delete(_refreshTokenKey);
    await _secrets.delete(_userIdKey);
  }
}
