import 'package:bliss_housekeeping_app/main.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('opens directly on login without initializing SQLite', (
    tester,
  ) async {
    await tester.pumpWidget(const BlissHomeApp());
    await tester.pump();

    expect(find.text('Bliss Home'), findsOneWidget);
    expect(find.text('Đăng nhập'), findsOneWidget);
    expect(find.text('Đang khởi động ứng dụng…'), findsNothing);
  });
}
