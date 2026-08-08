import 'dart:convert';

import 'package:bliss_housekeeping_app/src/api/housekeeping_api.dart';
import 'package:bliss_housekeeping_app/src/screens/housekeeping_home_screen.dart';
import 'package:bliss_housekeeping_app/src/security/secure_store.dart';
import 'package:bliss_housekeeping_app/src/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

final class _MemorySecretStore implements SecretStore {
  final values = <String, String>{};

  @override
  Future<void> delete(String key) async => values.remove(key);

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String value) async => values[key] = value;
}

http.Response _response(Object? data, {Map<String, Object?>? pagination}) =>
    http.Response(
      jsonEncode({
        'success': true,
        'code': 'OK',
        'message': 'Thành công.',
        'data': data,
        'pagination': ?pagination,
      }),
      200,
      headers: const {'content-type': 'application/json; charset=utf-8'},
    );

Map<String, Object?> _task({
  required String id,
  required String room,
  required String status,
  required int income,
  required DateTime dueAt,
}) => {
  'id': id,
  'code': 'HK-$id',
  'status': status,
  'taskType': status == 'QC_APPROVED'
      ? 'CHECKOUT_CLEANING'
      : 'CHECKIN_PREPARATION',
  'priority': status == 'QC_APPROVED' ? 'NORMAL' : 'HIGH',
  'progressPercent': status == 'QC_APPROVED' ? 100 : 40,
  'dueAt': dueAt.toIso8601String(),
  'nextCheckinAt': dueAt.add(const Duration(hours: 1)).toIso8601String(),
  'estimatedIncome': income,
  'note': status == 'QC_APPROVED' ? '' : 'Ưu tiên khăn không mùi',
  'room': {'code': room, 'floor': 'Tầng 2'},
  'branch': {'name': 'Bliss Đà Lạt'},
  'assignee': {'id': 'hk-1', 'name': 'Hương'},
  'shift': {
    'name': 'Ca sáng',
    'startsAt': DateTime.now()
        .subtract(const Duration(hours: 2))
        .toIso8601String(),
    'endsAt': DateTime.now().add(const Duration(hours: 6)).toIso8601String(),
  },
  'checklistSummary': {
    'totalRequired': 5,
    'completedRequired': status == 'QC_APPROVED' ? 5 : 2,
  },
};

const _user = AppUserProfile(
  id: 'hk-1',
  username: 'huong',
  name: 'Nguyễn Hương',
  role: 'housekeeping',
);

Future<HousekeepingApi> _createApi() async {
  final secrets = _MemorySecretStore();
  final tokens = SecureTokenStore(secrets);
  await tokens.save(
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    user: _user,
  );
  final now = DateTime.now();
  return HousekeepingApi(
    baseUri: Uri.parse('https://homestay.aaistech.com'),
    tokens: tokens,
    client: MockClient((request) async {
      if (request.url.path == '/api/v1/housekeeping/notifications') {
        return _response({'items': const [], 'unreadCount': 3});
      }
      expect(request.url.path, '/api/v1/housekeeping/tasks');
      expect(request.url.queryParameters['assignee'], 'me');
      expect(request.url.queryParameters['date'], isNotEmpty);
      return _response(
        [
          _task(
            id: '1',
            room: 'A202',
            status: 'IN_PROGRESS',
            income: 160000,
            dueAt: now.add(const Duration(hours: 1)),
          ),
          _task(
            id: '2',
            room: 'S201',
            status: 'QC_APPROVED',
            income: 160000,
            dueAt: now.subtract(const Duration(hours: 1)),
          ),
        ],
        pagination: const {
          'page': 1,
          'limit': 100,
          'total': 2,
          'totalPages': 1,
          'hasNext': false,
        },
      );
    }),
  );
}

void main() {
  for (final size in [const Size(390, 844), const Size(360, 640)]) {
    testWidgets('housekeeping home follows the approved mobile dashboard at '
        '${size.width.toInt()}px', (tester) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final api = await _createApi();
      addTearDown(api.close);
      await tester.pumpWidget(
        MaterialApp(
          theme: BlissAppTheme.light(),
          home: HousekeepingHomeScreen(
            api: api,
            user: _user,
            onOpenTasks: () {},
            onOpenRequests: () {},
            onReportIssue: () {},
            onOpenNotifications: () {},
            onOpenProfile: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Bliss Home'), findsOneWidget);
      expect(find.text('Công việc hôm nay'), findsOneWidget);
      expect(find.text('2 việc'), findsOneWidget);
      expect(find.text('320.000đ'), findsOneWidget);
      expect(find.text('Tất cả việc'), findsOneWidget);
      expect(find.text('Báo vấn đề'), findsOneWidget);
      expect(find.text('A202 · Tầng 2'), findsOneWidget);
      expect(tester.takeException(), isNull);

      await tester.tap(find.text('Đã xong (1)'));
      await tester.pumpAndSettle();
      expect(find.text('A202 · Tầng 2'), findsNothing);
      expect(find.text('S201 · Tầng 2'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }
}
