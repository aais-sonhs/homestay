enum HousekeepingTaskTab {
  mine('Việc của tôi'),
  available('Chờ nhận'),
  inProgress('Đang làm'),
  support('Chờ hỗ trợ'),
  waitingQc('Chờ kiểm tra'),
  rework('Làm lại'),
  done('Hoàn thành');

  const HousekeepingTaskTab(this.label);
  final String label;

  Map<String, String> get apiFilters => switch (this) {
    HousekeepingTaskTab.mine => const {'assignee': 'me'},
    HousekeepingTaskTab.available => const {'tab': 'open'},
    HousekeepingTaskTab.inProgress => const {'status': 'IN_PROGRESS'},
    HousekeepingTaskTab.support => const {'status': 'PAUSED,WAITING_SUPPORT'},
    HousekeepingTaskTab.waitingQc => const {'status': 'WAITING_QC'},
    HousekeepingTaskTab.rework => const {'status': 'QC_REJECTED'},
    HousekeepingTaskTab.done => const {'status': 'COMPLETED,QC_APPROVED'},
  };

  bool matches(TaskViewData task) => switch (this) {
    HousekeepingTaskTab.mine => task.assigneeName.isNotEmpty,
    HousekeepingTaskTab.available =>
      task.assigneeName.isEmpty &&
          {'UNASSIGNED', 'PENDING_ACCEPTANCE'}.contains(task.status),
    HousekeepingTaskTab.inProgress => task.status == 'IN_PROGRESS',
    HousekeepingTaskTab.support => {
      'PAUSED',
      'WAITING_SUPPORT',
    }.contains(task.status),
    HousekeepingTaskTab.waitingQc => task.status == 'WAITING_QC',
    HousekeepingTaskTab.rework => task.status == 'QC_REJECTED',
    HousekeepingTaskTab.done => {
      'COMPLETED',
      'QC_APPROVED',
    }.contains(task.status),
  };
}

const Map<String, String> _vietnameseLabels = {
  'UNASSIGNED': 'Chờ phân công',
  'ASSIGNED': 'Đã phân công',
  'PENDING_ACCEPTANCE': 'Chờ nhận việc',
  'ACCEPTED': 'Đã nhận việc',
  'IN_PROGRESS': 'Đang thực hiện',
  'PAUSED': 'Tạm dừng',
  'WAITING_SUPPORT': 'Chờ hỗ trợ',
  'COMPLETED': 'Đã hoàn thành',
  'WAITING_QC': 'Chờ kiểm tra chất lượng',
  'QC_REJECTED': 'Kiểm tra không đạt',
  'QC_APPROVED': 'Kiểm tra đạt',
  'CANCELLED': 'Đã hủy',
  'BOOKED': 'Đã đặt',
  'CHECKED_IN': 'Đã nhận phòng',
  'CHECKED_OUT': 'Đã trả phòng',
  'DRAFT': 'Nháp',
  'PUBLISHED': 'Đã phát hành',
  'RETIRED': 'Ngừng sử dụng',
  'PENDING': 'Chờ xử lý',
  'APPROVED': 'Đạt',
  'REJECTED': 'Không đạt',
  'RETURNED': 'Đã trả lại',
  'REASSIGNED': 'Đã điều chuyển',
  'ENDED': 'Đã kết thúc',
  'OPEN': 'Đang mở',
  'ACKNOWLEDGED': 'Đã tiếp nhận',
  'FULFILLED': 'Đã cấp',
  'RESOLVED': 'Đã xử lý',
  'SENT_TO_QC': 'Đã gửi kiểm tra chất lượng',
  'READY': 'Sẵn sàng',
  'DIRTY': 'Bẩn',
  'WAITING_CLEANING': 'Chờ dọn',
  'CLEANING': 'Đang dọn',
  'CLEANING_BLOCKED': 'Dọn phòng bị chặn',
  'REWORK_REQUIRED': 'Cần làm lại',
  'OUT_OF_SERVICE': 'Ngừng phục vụ',
  'LOW': 'Thấp',
  'NORMAL': 'Bình thường',
  'HIGH': 'Cao',
  'URGENT': 'Khẩn cấp',
  'CRITICAL': 'Nghiêm trọng',
  'CHECKOUT_CLEANING': 'Dọn phòng sau khi khách trả phòng',
  'STAYOVER_CLEANING': 'Dọn phòng đang có khách',
  'CHECKIN_PREPARATION': 'Chuẩn bị phòng đón khách',
  'DEEP_CLEANING': 'Vệ sinh chuyên sâu',
  'QC_REWORK': 'Dọn lại sau kiểm tra chất lượng',
  'QC': 'Kiểm tra chất lượng',
  'PERIODIC_CLEANING': 'Vệ sinh định kỳ',
  'CHECKBOX': 'Ô đánh dấu',
  'YES_NO': 'Có hoặc không',
  'NUMBER': 'Số lượng',
  'TEXT': 'Văn bản',
  'PHOTO': 'Chụp ảnh',
  'SINGLE_SELECT': 'Chọn một',
  'MULTI_SELECT': 'Chọn nhiều',
  'DEVICE_CHECK': 'Kiểm tra thiết bị',
  'QR_SCAN': 'Quét mã QR',
  'BEFORE': 'Trước khi dọn',
  'AFTER': 'Sau khi dọn',
  'ISSUE': 'Sự cố',
  'SUPPLY': 'Thiếu vật tư',
  'AREA': 'Khu vực',
  'EVIDENCE': 'Bằng chứng hoàn thành',
  'CAMERA': 'Máy ảnh',
  'GALLERY': 'Thư viện ảnh',
  'OFFLINE_CAMERA': 'Máy ảnh ngoại tuyến',
  'RECEIVED': 'Đã nhận',
  'SUCCEEDED': 'Thành công',
  'FAILED': 'Thất bại',
  'CONFLICT': 'Xung đột',
  'DISCARDED': 'Đã bỏ thay đổi trên thiết bị',
  'SYNCED': 'Đã đồng bộ',
  'SYNCING': 'Đang đồng bộ',
  'WAITING_SUPPLIES': 'Chờ vật tư',
  'DEVICE_BROKEN': 'Thiết bị hỏng',
  'GUEST_IN_ROOM': 'Khách đang trong phòng',
  'GUEST_REQUEST_LATER': 'Khách yêu cầu quay lại sau',
  'WAITING_TECHNICIAN': 'Chờ kỹ thuật',
  'WAITING_MANAGER': 'Chờ quản lý',
  'HIGHER_PRIORITY_TASK': 'Có công việc ưu tiên hơn',
  'BREAK': 'Nghỉ giữa ca',
  'OTHER': 'Khác',
  'MANUAL': 'Tạo thủ công',
  'MANUAL_BACKOFFICE': 'Thao tác thủ công trên trang quản trị',
  'QR_CODE': 'Mã QR phòng',
  'GPS': 'Vị trí GPS',
  'WIFI': 'Mạng Wi-Fi',
  'MANAGER_OVERRIDE': 'Quản lý xác nhận',
  'GUEST_CONSENT': 'Khách đồng ý',
  'ACCEPT': 'Nhận việc',
  'START': 'Bắt đầu',
  'PAUSE': 'Tạm dừng',
  'RESUME': 'Tiếp tục',
  'COMPLETE': 'Hoàn thành',
  'RETURN': 'Trả lại',
  'REJECT': 'Từ chối',
  'REASSIGN': 'Điều chuyển',
  'SEND_TO_QC': 'Gửi kiểm tra chất lượng',
  'QC_APPROVE': 'Duyệt đạt',
  'QC_REJECT': 'Đánh giá không đạt',
  'START_REWORK': 'Bắt đầu làm lại',
  'WAIT_SUPPORT': 'Chờ hỗ trợ',
  'CREATE_SUPPLY_REQUEST': 'Tạo yêu cầu vật tư',
  'REPORT_ISSUE': 'Báo sự cố',
  'UPDATE_CHECKLIST_ITEM': 'Cập nhật hạng mục kiểm tra',
  'UPDATE_TASK_NOTE': 'Cập nhật ghi chú công việc',
  'UPLOAD_MEDIA': 'Tải ảnh lên',
  'RETRY_WITH_SERVER_VERSION': 'Thử lại theo phiên bản trên máy chủ',
  'DISCARD_LOCAL': 'Bỏ thay đổi trên thiết bị',
  'DEVICE_NOT_WORKING': 'Thiết bị không hoạt động',
  'DAMAGE': 'Hư hỏng',
  'SAFETY': 'An toàn',
  'CHECKLIST_REQUIRED_INCOMPLETE': 'Còn hạng mục bắt buộc chưa hoàn tất',
  'FAILED_ITEM_UNRESOLVED': 'Hạng mục không đạt chưa được xử lý',
  'REQUIRED_PHOTO_MISSING': 'Thiếu ảnh bắt buộc',
  'BLOCKING_ISSUE_EXISTS': 'Còn sự cố chặn phòng',
  'SUPPLY_REQUEST_PENDING': 'Còn yêu cầu vật tư đang chờ',
  'PENDING_SYNC_EXISTS': 'Còn dữ liệu chưa đồng bộ',
  'STANDARD': 'Tiêu chuẩn',
  'DELUXE': 'Cao cấp',
  'Deluxe': 'Cao cấp',
  'SUITE': 'Phòng hạng sang',
  'Suite': 'Phòng hạng sang',
};

const Map<String, String> _vietnameseFieldLabels = {
  'version': 'Phiên bản',
  'status': 'Trạng thái',
  'note': 'Ghi chú',
  'operation': 'Thao tác',
  'payload': 'Nội dung thay đổi',
  'baseVersion': 'Phiên bản dữ liệu gốc',
  'baseSnapshot': 'Dữ liệu gốc',
  'localOperation': 'Thay đổi trên thiết bị',
  'serverSnapshot': 'Dữ liệu trên máy chủ',
  'taskId': 'Mã công việc',
  'taskVersion': 'Phiên bản công việc',
  'roomStatus': 'Trạng thái phòng',
  'progressPercent': 'Tiến độ phần trăm',
  'updatedAt': 'Cập nhật lúc',
  'itemId': 'Mã hạng mục',
  'checklistItemId': 'Mã hạng mục kiểm tra',
  'checklistItem': 'Hạng mục kiểm tra',
  'itemVersion': 'Phiên bản hạng mục',
  'value': 'Giá trị',
  'failureReason': 'Lý do không đạt',
  'reason': 'Lý do',
  'reasonCode': 'Loại lý do',
  'category': 'Loại ảnh',
  'metadata': 'Thông tin bổ sung',
  'checksum': 'Mã kiểm tra tệp',
  'roomVerification': 'Xác minh phòng',
  'method': 'Phương thức',
  'capturedAt': 'Thời gian chụp',
  'latitude': 'Vĩ độ',
  'longitude': 'Kinh độ',
  'accuracyMeters': 'Độ chính xác (mét)',
  'confirmFinalInspection': 'Đã xác nhận kiểm tra cuối',
  'finalNote': 'Ghi chú hoàn thành',
  'clientMutationId': 'Mã thay đổi trên thiết bị',
  'idempotencyKey': 'Mã chống gửi trùng',
  'dependsOn': 'Thay đổi phụ thuộc',
  'completedAt': 'Hoàn thành lúc',
};

String viCodeLabel(Object? value) {
  if (value == null) return '—';
  final text = value.toString();
  return _vietnameseLabels[text] ?? text;
}

String viFieldLabel(Object? value) {
  if (value == null) return '—';
  final text = value.toString();
  return _vietnameseFieldLabels[text] ?? text;
}

Object? localizedPayload(Object? value) {
  if (value is Map) {
    return <String, Object?>{
      for (final entry in value.entries)
        viFieldLabel(entry.key): localizedPayload(entry.value),
    };
  }
  if (value is List) return value.map(localizedPayload).toList();
  if (value is String) return viCodeLabel(value);
  return value;
}

final class TaskFilters {
  const TaskFilters({
    this.query = '',
    this.date,
    this.branchId = '',
    this.floor = '',
    this.roomType = '',
    this.taskType = '',
    this.priority = '',
    this.areaId = '',
    this.shiftId = '',
    this.status = '',
    this.assignee = '',
    this.qcRework = false,
    this.overdue = false,
    this.checkinRisk = false,
  });

  final String query;
  final DateTime? date;
  final String branchId;
  final String floor;
  final String roomType;
  final String taskType;
  final String priority;
  final String areaId;
  final String shiftId;
  final String status;
  final String assignee;
  final bool qcRework;
  final bool overdue;
  final bool checkinRisk;

  bool get active =>
      query.isNotEmpty ||
      date != null ||
      branchId.isNotEmpty ||
      floor.isNotEmpty ||
      roomType.isNotEmpty ||
      taskType.isNotEmpty ||
      priority.isNotEmpty ||
      areaId.isNotEmpty ||
      shiftId.isNotEmpty ||
      status.isNotEmpty ||
      assignee.isNotEmpty ||
      qcRework ||
      overdue ||
      checkinRisk;

  Map<String, String> toApiQuery(HousekeepingTaskTab tab) => {
    ...tab.apiFilters,
    'limit': '100',
    if (query.trim().isNotEmpty) 'q': query.trim(),
    if (date != null) 'date': dateOnly(date!),
    if (branchId.isNotEmpty) 'branchId': branchId,
    if (floor.isNotEmpty) 'floor': floor,
    if (roomType.isNotEmpty) 'roomType': roomType,
    if (taskType.isNotEmpty) 'taskType': taskType,
    if (priority.isNotEmpty) 'priority': priority,
    if (areaId.isNotEmpty) 'areaId': areaId,
    if (shiftId.isNotEmpty) 'shiftId': shiftId,
    if (status.isNotEmpty) 'status': status,
    if (assignee.isNotEmpty) 'assignee': assignee,
    if (qcRework) 'qcRework': 'true',
    if (overdue) 'overdue': 'true',
    if (checkinRisk) 'checkinRisk': 'true',
  };

  TaskFilters copyWith({
    String? query,
    DateTime? date,
    bool clearDate = false,
    String? branchId,
    String? floor,
    String? roomType,
    String? taskType,
    String? priority,
    String? areaId,
    String? shiftId,
    String? status,
    String? assignee,
    bool? qcRework,
    bool? overdue,
    bool? checkinRisk,
  }) => TaskFilters(
    query: query ?? this.query,
    date: clearDate ? null : date ?? this.date,
    branchId: branchId ?? this.branchId,
    floor: floor ?? this.floor,
    roomType: roomType ?? this.roomType,
    taskType: taskType ?? this.taskType,
    priority: priority ?? this.priority,
    areaId: areaId ?? this.areaId,
    shiftId: shiftId ?? this.shiftId,
    status: status ?? this.status,
    assignee: assignee ?? this.assignee,
    qcRework: qcRework ?? this.qcRework,
    overdue: overdue ?? this.overdue,
    checkinRisk: checkinRisk ?? this.checkinRisk,
  );

  static String dateOnly(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-'
      '${value.month.toString().padLeft(2, '0')}-'
      '${value.day.toString().padLeft(2, '0')}';
}

final class TaskViewData {
  TaskViewData(this.raw);

  final Map<String, Object?> raw;

  Map get room => raw['room'] as Map? ?? const {};
  Map get branch => raw['branch'] as Map? ?? const {};
  Map get assignee => raw['assignee'] as Map? ?? const {};
  Map get shift => raw['shift'] as Map? ?? const {};
  Map get workArea => raw['area'] as Map? ?? const {};
  Map get checklist => raw['checklistSummary'] as Map? ?? const {};

  String get id => (raw['id'] ?? raw['taskId'])! as String;
  String get code => raw['code'] as String? ?? '';
  String get roomCode => room['code'] as String? ?? '';
  String get roomName => room['name'] as String? ?? '';
  String get floor => room['floor'] as String? ?? '';
  String get area => room['area'] as String? ?? '';
  String get roomType => room['roomType'] as String? ?? '';
  String get roomStatus =>
      raw['roomStatus'] as String? ?? room['status'] as String? ?? '';
  String get branchName => branch['name'] as String? ?? '';
  String get taskType => raw['taskType'] as String? ?? '';
  String get taskTypeLabel {
    final translated = viCodeLabel(taskType);
    return translated != taskType
        ? translated
        : raw['taskTypeLabel'] as String? ?? translated;
  }
  String get status => raw['status'] as String? ?? '';
  String get statusLabel {
    final translated = viCodeLabel(status);
    return translated != status
        ? translated
        : raw['statusLabel'] as String? ?? translated;
  }
  String get priority => raw['priority'] as String? ?? 'NORMAL';
  String get priorityLabel => viCodeLabel(priority);
  String get roomStatusLabel => viCodeLabel(roomStatus);
  String get assigneeName => assignee['name'] as String? ?? '';
  String get assigneeId => assignee['id'] as String? ?? '';
  String get shiftId => shift['id'] as String? ?? '';
  String get shiftName => shift['name'] as String? ?? '';
  String get areaId => workArea['id'] as String? ?? '';
  String get areaName => workArea['name'] as String? ?? area;
  String get note => raw['note'] as String? ?? '';
  String get specialRequest => raw['specialRequest'] as String? ?? '';
  bool get guestInRoom => raw['guestInRoom'] == true;
  bool get isOverdue =>
      raw['isOverdue'] == true || (dueAt != null && dueDelta.isNegative);
  bool get isCheckinRisk => raw['isCheckinRisk'] == true;
  int get progress => raw['progressPercent'] as int? ?? 0;
  int get photos => raw['photoCount'] as int? ?? 0;
  int get checklistDone => checklist['completedRequired'] as int? ?? 0;
  int get checklistTotal => checklist['totalRequired'] as int? ?? 0;
  DateTime? get scheduledStart => _parseDate(raw['scheduledStartAt']);
  DateTime? get dueAt => _parseDate(raw['dueAt']);
  DateTime? get nextCheckin => _parseDate(raw['nextCheckinAt']);

  Duration get dueDelta => (dueAt ?? DateTime.now()).difference(DateTime.now());

  String dueLabel({DateTime? now}) {
    final due = dueAt;
    if (due == null) return 'Chưa có hạn';
    final difference = due.difference(now ?? DateTime.now());
    final overdue = difference.isNegative;
    final minutes = difference.inMinutes.abs();
    final hours = minutes ~/ 60;
    final remainder = minutes % 60;
    final value = hours > 0 ? '${hours}g ${remainder}p' : '${minutes}p';
    return overdue ? 'Quá hạn $value' : 'Còn $value';
  }

  bool matchesText(String query) {
    final normalized = query.trim().toLowerCase();
    if (normalized.isEmpty) return true;
    return [
      code,
      roomCode,
      roomName,
      branchName,
      raw['bookingCode'] as String? ?? '',
    ].any((value) => value.toLowerCase().contains(normalized));
  }

  static DateTime? _parseDate(Object? value) =>
      value is String && value.isNotEmpty
      ? DateTime.tryParse(value)?.toLocal()
      : null;
}

String shortDateTime(Object? value) {
  if (value is! String || value.isEmpty) return '—';
  final parsed = DateTime.tryParse(value)?.toLocal();
  if (parsed == null) return '—';
  String two(int number) => number.toString().padLeft(2, '0');
  return '${two(parsed.hour)}:${two(parsed.minute)} '
      '${two(parsed.day)}/${two(parsed.month)}';
}

String durationLabel(Object? seconds) {
  final value = seconds is int ? seconds : 0;
  final hours = value ~/ 3600;
  final minutes = (value % 3600) ~/ 60;
  return hours > 0 ? '${hours}g ${minutes}p' : '${minutes}p';
}
