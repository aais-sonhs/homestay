import 'package:bliss_housekeeping_app/main.dart';
import 'package:bliss_housekeeping_app/src/security/secure_store.dart';
import 'package:flutter/material.dart';
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
  testWidgets('opens directly on login without initializing SQLite', (
    tester,
  ) async {
    await tester.pumpWidget(BlissHomeApp(secretStore: _MemorySecretStore()));
    await tester.pumpAndSettle();

    expect(find.text('Bliss Home'), findsOneWidget);
    expect(find.text('Đăng nhập'), findsOneWidget);
    expect(find.text('Ghi nhớ mật khẩu'), findsOneWidget);
    expect(find.text('Tạo tài khoản mới'), findsOneWidget);
    expect(find.text('Đang khởi động ứng dụng…'), findsNothing);
  });

  testWidgets('opens account registration from login', (tester) async {
    tester.view.physicalSize = const Size(360, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(BlissHomeApp(secretStore: _MemorySecretStore()));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Tạo tài khoản mới'));
    await tester.pumpAndSettle();

    expect(find.text('Thông tin tài khoản'), findsOneWidget);
    expect(find.text('Họ và tên'), findsOneWidget);
    expect(find.text('Thư điện tử'), findsOneWidget);
    expect(find.text('Số điện thoại'), findsOneWidget);
    expect(find.text('Xác nhận mật khẩu'), findsOneWidget);
  });

  testWidgets('loads remembered login from the secure credential store', (
    tester,
  ) async {
    final secrets = _MemorySecretStore();
    await RememberedLoginStore(
      secrets,
    ).save(identifier: 'housekeeper@example.com', password: 'Saved@2026Pass');

    await tester.pumpWidget(BlissHomeApp(secretStore: secrets));
    await tester.pumpAndSettle();

    final fields = tester
        .widgetList<TextField>(find.byType(TextField))
        .toList();
    expect(fields[0].controller?.text, 'housekeeper@example.com');
    expect(fields[1].controller?.text, 'Saved@2026Pass');
    expect(
      tester.widget<CheckboxListTile>(find.byType(CheckboxListTile)).value,
      isTrue,
    );
  });
}
