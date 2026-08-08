import 'package:bliss_housekeeping_app/src/security/secure_store.dart';
import 'package:flutter_test/flutter_test.dart';

final class _MemorySecretStore implements SecretStore {
  final values = <String, String>{};

  @override
  Future<void> delete(String key) async => values.remove(key);

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String value) async => values[key] = value;
}

void main() {
  test('role profile routes management, QC and housekeeping distinctly', () {
    const owner = AppUserProfile(
      id: 'owner-1',
      username: 'owner',
      name: 'Chủ Đà Lạt',
      role: 'branch_owner',
    );
    const qc = AppUserProfile(
      id: 'qc-1',
      username: 'qc',
      name: 'QC Đà Lạt',
      role: 'qc',
    );
    const housekeeper = AppUserProfile(
      id: 'hk-1',
      username: 'housekeeping',
      name: 'Tạp vụ Đà Lạt',
      role: 'housekeeping',
    );
    const customerService = AppUserProfile(
      id: 'cskh-1',
      username: 'cskh',
      name: 'CSKH Đà Lạt',
      role: 'customer_service',
    );

    expect(owner.isManagement, isTrue);
    expect(owner.roleLabel, 'Chủ chi nhánh');
    expect(qc.isQc, isTrue);
    expect(qc.isManagement, isFalse);
    expect(housekeeper.isQc, isFalse);
    expect(housekeeper.isManagement, isFalse);
    expect(customerService.isCustomerService, isTrue);
    expect(customerService.roleLabel, 'Chăm sóc khách hàng');
  });

  test(
    'secure token store persists and clears the complete user session',
    () async {
      final secrets = _MemorySecretStore();
      final tokens = SecureTokenStore(secrets);
      const profile = AppUserProfile(
        id: 'manager-1',
        username: 'manager',
        name: 'Quản lý Bliss',
        role: 'manager',
      );

      await tokens.save(
        accessToken: 'access-secret',
        refreshToken: 'refresh-secret',
        user: profile,
      );

      expect(await tokens.accessToken, 'access-secret');
      expect(await tokens.refreshToken, 'refresh-secret');
      final restored = await tokens.userProfile;
      expect(restored?.id, profile.id);
      expect(restored?.name, profile.name);
      expect(restored?.role, profile.role);

      await tokens.clear();
      expect(await tokens.accessToken, isNull);
      expect(await tokens.userProfile, isNull);
    },
  );

  test(
    'remembered login store saves and removes credentials securely',
    () async {
      final secrets = _MemorySecretStore();
      final rememberedLogins = RememberedLoginStore(secrets);

      final initial = await rememberedLogins.load();
      expect(initial.enabled, isTrue);
      expect(initial.identifier, isNull);
      expect(initial.password, isNull);

      await rememberedLogins.save(
        identifier: 'owner@example.com',
        password: 'Saved@2026Pass',
      );
      final saved = await rememberedLogins.load();
      expect(saved.enabled, isTrue);
      expect(saved.identifier, 'owner@example.com');
      expect(saved.password, 'Saved@2026Pass');

      await rememberedLogins.clear();
      final cleared = await rememberedLogins.load();
      expect(cleared.enabled, isFalse);
      expect(cleared.identifier, isNull);
      expect(cleared.password, isNull);
    },
  );
}
