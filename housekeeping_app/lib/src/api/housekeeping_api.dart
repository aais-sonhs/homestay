import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:uuid/uuid.dart';

import '../offline/models.dart';
import '../security/secure_store.dart';

final class ApiFailure implements Exception {
  const ApiFailure({
    required this.statusCode,
    required this.code,
    required this.message,
    this.details = const {},
  });

  final int statusCode;
  final String code;
  final String message;
  final Map<String, Object?> details;

  bool get isConflict => statusCode == 409 || code == 'OFFLINE_SYNC_CONFLICT';

  @override
  String toString() => message;
}

final class HousekeepingApi {
  HousekeepingApi({
    required Uri baseUri,
    required SecureTokenStore tokens,
    http.Client? client,
  }) : _baseUri = baseUri,
       _tokens = tokens,
       _client = client ?? http.Client();

  final Uri _baseUri;
  final SecureTokenStore _tokens;
  final http.Client _client;

  Uri _uri(String path, [Map<String, String>? query]) =>
      _baseUri.resolve(path).replace(queryParameters: query);

  Future<Map<String, Object?>> login({
    required String identifier,
    required String password,
    required String deviceName,
  }) async {
    final data = await _jsonRequest(
      'POST',
      '/api/v1/auth/login',
      authenticated: false,
      body: {
        'identifier': identifier,
        'password': password,
        'deviceName': deviceName,
      },
    );
    final user = AppUserProfile.fromMap(data['user']! as Map);
    await _tokens.save(
      accessToken: data['accessToken']! as String,
      refreshToken: data['refreshToken']! as String,
      user: user,
    );
    return data;
  }

  Future<Map<String, Object?>> slaDashboard({String? date, String? branchId}) =>
      _jsonRequest(
        'GET',
        '/api/v1/housekeeping/dashboard/sla',
        query: {
          if (date != null && date.isNotEmpty) 'date': date,
          if (branchId != null && branchId.isNotEmpty) 'branchId': branchId,
        },
      );

  Future<Map<String, Object?>> performanceDashboard({
    String? date,
    String? branchId,
  }) => _jsonRequest(
    'GET',
    '/api/v1/housekeeping/dashboard/performance',
    query: {
      if (date != null && date.isNotEmpty) 'date': date,
      if (branchId != null && branchId.isNotEmpty) 'branchId': branchId,
    },
  );

  Future<Map<String, Object?>> roomReadiness({
    String? query,
    String? state,
    String? branchId,
  }) => _jsonRequest(
    'GET',
    '/api/v1/room-operations/rooms',
    query: {
      if (query != null && query.trim().isNotEmpty) 'q': query.trim(),
      if (state != null && state.isNotEmpty) 'state': state,
      if (branchId != null && branchId.isNotEmpty) 'branchId': branchId,
    },
  );

  Future<List<Map<String, Object?>>> tasks({
    Map<String, String>? filters,
  }) async {
    final data = await _jsonRequest(
      'GET',
      '/api/v1/housekeeping/tasks',
      query: filters,
    );
    return (data['items'] as List? ?? data['_list'] as List? ?? const [])
        .map((item) => Map<String, Object?>.from(item as Map))
        .toList(growable: false);
  }

  Future<Map<String, Object?>> taskDetail(String taskId) =>
      _jsonRequest('GET', '/api/v1/housekeeping/tasks/$taskId');

  Future<Map<String, Object?>> completionSummary(String taskId) => _jsonRequest(
    'GET',
    '/api/v1/housekeeping/tasks/$taskId/completion-summary',
  );

  Future<Map<String, Object?>> notifications({bool? unread}) => _jsonRequest(
    'GET',
    '/api/v1/housekeeping/notifications',
    query: {'limit': '100', if (unread != null) 'unread': unread.toString()},
  );

  Future<void> markNotificationRead(String recipientId) async {
    await _jsonRequest(
      'POST',
      '/api/v1/housekeeping/notifications/$recipientId/read',
      idempotencyKey: const Uuid().v4(),
      body: const {},
    );
  }

  Future<void> logout() async {
    final refreshToken = await _tokens.refreshToken;
    try {
      await _jsonRequest(
        'POST',
        '/api/v1/auth/logout',
        body: {'refreshToken': ?refreshToken},
        allowRefresh: false,
      );
    } on Object {
      // Local logout must still complete when the device is offline. Access
      // tokens are short-lived; the refresh secret is removed immediately.
    } finally {
      await _tokens.clear();
    }
  }

  Future<Map<String, Object?>> syncBatch(List<QueuedMutation> mutations) =>
      _jsonRequest(
        'POST',
        '/api/v1/housekeeping/sync/batch',
        body: {
          'mutations': mutations
              .map((mutation) => mutation.toBatchJson())
              .toList(),
        },
      );

  Future<Map<String, Object?>> conflict(String receiptId) =>
      _jsonRequest('GET', '/api/v1/housekeeping/sync/conflicts/$receiptId');

  Future<Map<String, Object?>> resolveConflict({
    required String receiptId,
    required String action,
    required String resolutionIdempotencyKey,
    String? newIdempotencyKey,
    String? clientMutationId,
  }) => _jsonRequest(
    'POST',
    '/api/v1/housekeeping/sync/conflicts/$receiptId/resolve',
    idempotencyKey: resolutionIdempotencyKey,
    body: {
      'action': action,
      'newIdempotencyKey': ?newIdempotencyKey,
      'clientMutationId': ?clientMutationId,
    },
  );

  Future<Map<String, Object?>> discardReceipt({
    required String receiptId,
    required String idempotencyKey,
  }) => _jsonRequest(
    'POST',
    '/api/v1/housekeeping/sync/receipts/$receiptId/discard',
    idempotencyKey: idempotencyKey,
    body: const {},
  );

  Future<Map<String, Object?>> uploadMedia(QueuedMedia media) =>
      _uploadMedia(media, allowRefresh: true);

  Future<Map<String, Object?>> _uploadMedia(
    QueuedMedia media, {
    required bool allowRefresh,
  }) async {
    final token = await _tokens.accessToken;
    if (token == null) {
      throw const ApiFailure(
        statusCode: 401,
        code: 'AUTHENTICATION_REQUIRED',
        message: 'Chưa đăng nhập.',
      );
    }
    final request =
        http.MultipartRequest(
            'POST',
            _uri('/api/v1/housekeeping/tasks/${media.taskId}/media'),
          )
          ..headers['Authorization'] = 'Bearer $token'
          ..headers['Idempotency-Key'] = media.idempotencyKey
          ..fields.addAll({
            'version': media.baseVersion.toString(),
            'clientId': media.clientMediaId,
            'checksum': media.checksum,
            'source': 'OFFLINE_CAMERA',
            'metadata': jsonEncode(media.metadata),
            for (final entry in media.metadata.entries)
              if (entry.value != null && entry.key != 'metadata')
                entry.key: entry.value.toString(),
          })
          ..files.add(
            http.MultipartFile.fromBytes(
              'image',
              media.bytes,
              filename: media.fileName,
            ),
          );
    final streamed = await _client.send(request);
    final response = await http.Response.fromStream(streamed);
    if (response.statusCode == 401 && allowRefresh) {
      await _refreshSession();
      return _uploadMedia(media, allowRefresh: false);
    }
    return _decode(response);
  }

  Future<Map<String, Object?>> _jsonRequest(
    String method,
    String path, {
    Map<String, String>? query,
    Map<String, Object?>? body,
    String? idempotencyKey,
    bool authenticated = true,
    bool allowRefresh = true,
  }) async {
    final headers = <String, String>{'Content-Type': 'application/json'};
    if (authenticated) {
      final token = await _tokens.accessToken;
      if (token == null) {
        throw const ApiFailure(
          statusCode: 401,
          code: 'AUTHENTICATION_REQUIRED',
          message: 'Chưa đăng nhập.',
        );
      }
      headers['Authorization'] = 'Bearer $token';
    }
    if (idempotencyKey != null) headers['Idempotency-Key'] = idempotencyKey;
    final request = http.Request(method, _uri(path, query))
      ..headers.addAll(headers)
      ..body = body == null ? '' : jsonEncode(body);
    final streamed = await _client.send(request);
    final response = await http.Response.fromStream(streamed);
    if (response.statusCode == 401 && authenticated && allowRefresh) {
      await _refreshSession();
      return _jsonRequest(
        method,
        path,
        query: query,
        body: body,
        idempotencyKey: idempotencyKey,
        authenticated: authenticated,
        allowRefresh: false,
      );
    }
    return _decode(response);
  }

  Future<void> _refreshSession() async {
    final refreshToken = await _tokens.refreshToken;
    if (refreshToken == null) {
      await _tokens.clear();
      throw const ApiFailure(
        statusCode: 401,
        code: 'REFRESH_TOKEN_INVALID',
        message: 'Phiên đăng nhập đã hết hạn.',
      );
    }
    try {
      final data = await _jsonRequest(
        'POST',
        '/api/v1/auth/refresh',
        authenticated: false,
        allowRefresh: false,
        body: {
          'refreshToken': refreshToken,
          'deviceName': 'Ứng dụng Bliss Home',
        },
      );
      final user = AppUserProfile.fromMap(data['user']! as Map);
      await _tokens.save(
        accessToken: data['accessToken']! as String,
        refreshToken: data['refreshToken']! as String,
        user: user,
      );
    } on Object {
      await _tokens.clear();
      rethrow;
    }
  }

  Map<String, Object?> _decode(http.Response response) {
    final decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (decoded is! Map) {
      throw ApiFailure(
        statusCode: response.statusCode,
        code: 'INVALID_SERVER_RESPONSE',
        message: 'Máy chủ trả về dữ liệu không hợp lệ.',
      );
    }
    final envelope = Map<String, Object?>.from(decoded);
    if (response.statusCode < 200 ||
        response.statusCode >= 300 ||
        envelope['success'] != true) {
      throw ApiFailure(
        statusCode: response.statusCode,
        code: envelope['code'] as String? ?? 'SYSTEM_ERROR',
        message: envelope['message'] as String? ?? 'Không thể xử lý yêu cầu.',
        details: Map<String, Object?>.from(
          envelope['details'] as Map? ?? const {},
        ),
      );
    }
    final data = envelope['data'];
    if (data is Map) return Map<String, Object?>.from(data);
    if (data is List) return {'_list': data};
    return {'value': data};
  }

  void close() => _client.close();
}
