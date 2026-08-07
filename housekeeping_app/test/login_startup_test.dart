import 'package:bliss_housekeeping_app/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('opens directly on login without initializing SQLite', (
    tester,
  ) async {
    await tester.pumpWidget(const BlissHomeApp());
    await tester.pump();

    expect(find.text('Bliss Home'), findsOneWidget);
    expect(find.text('Đăng nhập'), findsOneWidget);
    expect(find.text('Tạo tài khoản mới'), findsOneWidget);
    expect(find.text('Đang khởi động ứng dụng…'), findsNothing);
  });

  testWidgets('opens account registration from login', (tester) async {
    tester.view.physicalSize = const Size(360, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const BlissHomeApp());
    await tester.pump();

    await tester.tap(find.text('Tạo tài khoản mới'));
    await tester.pumpAndSettle();

    expect(find.text('Thông tin tài khoản'), findsOneWidget);
    expect(find.text('Họ và tên'), findsOneWidget);
    expect(find.text('Thư điện tử'), findsOneWidget);
    expect(find.text('Số điện thoại'), findsOneWidget);
    expect(find.text('Xác nhận mật khẩu'), findsOneWidget);
  });
}
