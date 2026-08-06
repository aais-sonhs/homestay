import 'dart:convert';
import 'dart:math';

import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite_sqlcipher/sqflite.dart';

import '../security/secure_store.dart';

final class EncryptedHousekeepingDatabase {
  EncryptedHousekeepingDatabase._(this.database);

  static const _databaseSecretKey = 'housekeeping.sqlcipher_key.v1';
  final Database database;

  static Future<EncryptedHousekeepingDatabase> open(SecretStore secrets) async {
    var password = await secrets.read(_databaseSecretKey);
    if (password == null || password.isEmpty) {
      final random = Random.secure();
      password = base64UrlEncode(
        List<int>.generate(32, (_) => random.nextInt(256)),
      );
      await secrets.write(_databaseSecretKey, password);
    }
    final support = await getApplicationSupportDirectory();
    final db = await openDatabase(
      path.join(support.path, 'housekeeping_offline_v1.db'),
      password: password,
      version: 3,
      onConfigure: (database) async {
        await database.execute('PRAGMA foreign_keys = ON');
        await database.execute('PRAGMA secure_delete = ON');
      },
      onCreate: (database, version) async {
        await database.execute('''
          CREATE TABLE cached_tasks (
            task_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            server_version INTEGER NOT NULL,
            cached_at TEXT NOT NULL
          )
        ''');
        await database.execute('''
          CREATE TABLE cached_task_details (
            task_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            server_version INTEGER NOT NULL,
            cached_at TEXT NOT NULL
          )
        ''');
        await _createTaskViewsTable(database);
        await _createMetadataTable(database);
        await database.execute('''
          CREATE TABLE mutation_queue (
            client_mutation_id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            task_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            base_version INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            base_snapshot_json TEXT NOT NULL,
            depends_on_json TEXT NOT NULL,
            sync_state TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            receipt_id TEXT,
            error_code TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
          )
        ''');
        await database.execute(
          'CREATE INDEX mutation_task_state_idx ON mutation_queue(task_id, sync_state, created_at)',
        );
        await database.execute('''
          CREATE TABLE media_queue (
            client_media_id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            task_id TEXT NOT NULL,
            base_version INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            encrypted_blob BLOB NOT NULL,
            checksum TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            depends_on_json TEXT NOT NULL,
            sync_state TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            server_photo_id TEXT,
            error_code TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
          )
        ''');
        await database.execute('''
          CREATE TABLE sync_conflicts (
            receipt_id TEXT PRIMARY KEY,
            client_mutation_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            conflict_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            resolved_at TEXT
          )
        ''');
      },
      onUpgrade: (database, oldVersion, newVersion) async {
        if (oldVersion < 2) await _createTaskViewsTable(database);
        if (oldVersion < 3) await _createMetadataTable(database);
      },
    );
    return EncryptedHousekeepingDatabase._(db);
  }

  Future<void> close() => database.close();

  static Future<void> _createTaskViewsTable(Database database) async {
    await database.execute('''
      CREATE TABLE cached_task_views (
        view_key TEXT NOT NULL,
        task_id TEXT NOT NULL,
        sort_order INTEGER NOT NULL,
        PRIMARY KEY (view_key, task_id),
        FOREIGN KEY (task_id) REFERENCES cached_tasks(task_id) ON DELETE CASCADE
      )
    ''');
    await database.execute(
      'CREATE INDEX cached_task_view_order_idx '
      'ON cached_task_views(view_key, sort_order)',
    );
  }

  static Future<void> _createMetadataTable(Database database) async {
    await database.execute('''
      CREATE TABLE local_metadata (
        metadata_key TEXT PRIMARY KEY,
        metadata_value TEXT NOT NULL
      )
    ''');
  }
}
