import 'dart:async';
import 'dart:convert';

import 'package:bliss_housekeeping_app/src/api/housekeeping_api.dart';
import 'package:bliss_housekeeping_app/src/security/secure_store.dart';
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

http.Response _jsonResponse(
  Object? data, {
  int statusCode = 200,
  Map<String, Object?>? pagination,
}) => http.Response(
  jsonEncode({
    'success': statusCode >= 200 && statusCode < 300,
    'code': statusCode >= 200 && statusCode < 300 ? 'OK' : 'UNAUTHORIZED',
    'message': statusCode >= 200 && statusCode < 300
        ? 'Thành công.'
        : 'Phiên đăng nhập không hợp lệ.',
    'data': data,
    'pagination': ?pagination,
  }),
  statusCode,
  headers: const {'content-type': 'application/json; charset=utf-8'},
);

Future<SecureTokenStore> _authenticatedTokens() async {
  final tokens = SecureTokenStore(_MemorySecretStore());
  await tokens.save(
    accessToken: 'old-access',
    refreshToken: 'old-refresh',
    user: const AppUserProfile(
      id: 'user-1',
      username: 'owner',
      name: 'Chủ chi nhánh',
      role: 'branch_owner',
    ),
  );
  return tokens;
}

void main() {
  test('task list follows server pagination through the final page', () async {
    final tokens = await _authenticatedTokens();
    var calls = 0;
    final client = MockClient((request) async {
      calls++;
      final page = int.parse(request.url.queryParameters['page']!);
      expect(request.url.queryParameters['limit'], '100');
      final isLastPage = page == 21;
      final rows = List.generate(
        isLastPage ? 1 : 100,
        (index) => <String, Object?>{'id': 'task-$page-$index'},
      );
      return _jsonResponse(
        rows,
        pagination: {
          'page': page,
          'limit': 100,
          'total': 2001,
          'totalPages': 21,
          'hasNext': !isLastPage,
        },
      );
    });
    final api = HousekeepingApi(
      baseUri: Uri.parse('https://homestay.aaistech.com'),
      tokens: tokens,
      client: client,
    );

    final tasks = await api.tasks(filters: const {'status': 'WAITING_QC'});

    expect(tasks, hasLength(2001));
    expect(calls, 21);
    expect(tasks.last['id'], 'task-21-0');
    api.close();
  });

  test('guest request creation targets the production API contract', () async {
    final tokens = await _authenticatedTokens();
    late http.Request captured;
    final api = HousekeepingApi(
      baseUri: Uri.parse('https://homestay.aaistech.com'),
      tokens: tokens,
      client: MockClient((request) async {
        captured = request;
        return _jsonResponse({'id': 'guest-request-1', 'version': 1}, statusCode: 201);
      }),
    );

    final result = await api.createGuestRequest(
      bookingId: 'booking-1',
      branchId: 'branch-1',
      roomId: 'room-1',
      requestType: 'WATER',
      description: 'Thêm hai chai nước',
      quantity: 2,
      unit: 'chai',
      source: 'ZALO',
      priority: 'HIGH',
    );

    expect(captured.url.path, '/api/v1/housekeeping/guest-requests');
    expect(captured.method, 'POST');
    expect(captured.headers['Idempotency-Key'], isNotEmpty);
    expect(jsonDecode(captured.body)['bookingId'], 'booking-1');
    expect(result['id'], 'guest-request-1');
    api.close();
  });

  test(
    'concurrent unauthorized requests share one refresh operation',
    () async {
      final tokens = await _authenticatedTokens();
      final bothOldRequestsStarted = Completer<void>();
      var oldRequestCount = 0;
      var refreshCount = 0;
      final client = MockClient((request) async {
        if (request.url.path == '/api/v1/auth/refresh') {
          refreshCount++;
          return _jsonResponse({
            'accessToken': 'new-access',
            'refreshToken': 'new-refresh',
            'user': {
              'id': 'user-1',
              'username': 'owner',
              'name': 'Chủ chi nhánh',
              'role': 'branch_owner',
            },
          });
        }
        if (request.headers['Authorization'] == 'Bearer old-access') {
          oldRequestCount++;
          if (oldRequestCount == 2) bothOldRequestsStarted.complete();
          await bothOldRequestsStarted.future;
          return _jsonResponse(const {}, statusCode: 401);
        }
        expect(request.headers['Authorization'], 'Bearer new-access');
        return _jsonResponse(const <String, Object?>{});
      });
      final api = HousekeepingApi(
        baseUri: Uri.parse('https://homestay.aaistech.com'),
        tokens: tokens,
        client: client,
      );

      await Future.wait([api.slaDashboard(), api.performanceDashboard()]);

      expect(oldRequestCount, 2);
      expect(refreshCount, 1);
      expect(await tokens.accessToken, 'new-access');
      expect(await tokens.refreshToken, 'new-refresh');
      api.close();
    },
  );

  test('invalid HTML server response becomes a readable API failure', () async {
    final tokens = await _authenticatedTokens();
    final api = HousekeepingApi(
      baseUri: Uri.parse('https://homestay.aaistech.com'),
      tokens: tokens,
      client: MockClient(
        (_) async => http.Response('<html>Bad gateway</html>', 502),
      ),
    );

    await expectLater(
      api.slaDashboard(),
      throwsA(
        isA<ApiFailure>()
            .having((error) => error.code, 'code', 'INVALID_SERVER_RESPONSE')
            .having(
              (error) => error.message,
              'message',
              'Máy chủ đang gặp sự cố. Vui lòng thử lại sau.',
            ),
      ),
    );
    api.close();
  });
}
