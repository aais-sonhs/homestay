import 'package:flutter/material.dart';

import '../device/device_evidence.dart';
import '../presentation/task_presentation.dart';

final class ChecklistEditResult {
  const ChecklistEditResult({
    required this.status,
    required this.value,
    required this.note,
    required this.failureReason,
    this.capturePhoto = false,
  });

  final String status;
  final Object? value;
  final String note;
  final String failureReason;
  final bool capturePhoto;
}

Future<ChecklistEditResult?> showChecklistEditor(
  BuildContext context,
  Map<String, Object?> item,
) => showModalBottomSheet<ChecklistEditResult>(
  context: context,
  isScrollControlled: true,
  useSafeArea: true,
  builder: (context) => _ChecklistEditor(item: item),
);

class _ChecklistEditor extends StatefulWidget {
  const _ChecklistEditor({required this.item});
  final Map<String, Object?> item;

  @override
  State<_ChecklistEditor> createState() => _ChecklistEditorState();
}

class _ChecklistEditorState extends State<_ChecklistEditor> {
  late String _status = widget.item['status'] as String? ?? 'PENDING';
  late Object? _value = widget.item['value'];
  late final TextEditingController _text = TextEditingController(
    text: _initialText,
  );
  late final TextEditingController _note = TextEditingController(
    text: widget.item['note'] as String? ?? '',
  );
  late final TextEditingController _failure = TextEditingController(
    text: widget.item['failureReason'] as String? ?? '',
  );
  String? _error;

  String get _type => widget.item['type'] as String? ?? 'CHECKBOX';
  String get _initialText => switch (_type) {
    'NUMBER' || 'TEXT' || 'QR_SCAN' => _value?.toString() ?? '',
    _ => '',
  };

  List<Map<String, Object?>> get _options =>
      (widget.item['options'] as List? ?? const [])
          .map((raw) {
            if (raw is Map) return Map<String, Object?>.from(raw);
            return {'value': raw, 'label': raw.toString()};
          })
          .toList(growable: false);

  Map get _rules => widget.item['validationRules'] as Map? ?? const {};

  @override
  void initState() {
    super.initState();
    if (_value == null) {
      if (_type == 'CHECKBOX' || _type == 'YES_NO' || _type == 'DEVICE_CHECK') {
        _value = true;
      } else if (_type == 'MULTI_SELECT') {
        _value = <Object?>[];
      }
    }
  }

  void _save() {
    Object? value = _value;
    if (_status == 'PENDING') value = null;
    if (_status != 'PENDING') {
      if (_type == 'NUMBER') {
        value = num.tryParse(_text.text.trim());
        if (value == null) {
          setState(() => _error = 'Vui lòng nhập một số hợp lệ.');
          return;
        }
        if (_rules['integer'] == true && value is double && value % 1 != 0) {
          setState(() => _error = 'Giá trị phải là số nguyên.');
          return;
        }
      } else if (_type == 'TEXT' || _type == 'QR_SCAN') {
        value = _text.text.trim();
        if ((value as String).isEmpty) {
          setState(() => _error = 'Nội dung không được để trống.');
          return;
        }
      }
    }
    if (_status == 'FAILED' && _failure.text.trim().isEmpty) {
      setState(() => _error = 'Mục Không đạt phải có lý do.');
      return;
    }
    Navigator.pop(
      context,
      ChecklistEditResult(
        status: _status,
        value: value,
        note: _note.text.trim(),
        failureReason: _failure.text.trim(),
        capturePhoto: _type == 'PHOTO' && _status == 'COMPLETED',
      ),
    );
  }

  @override
  void dispose() {
    _text.dispose();
    _note.dispose();
    _failure.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.fromLTRB(
      16,
      12,
      16,
      20 + MediaQuery.viewInsetsOf(context).bottom,
    ),
    child: ListView(
      shrinkWrap: true,
      children: [
        Text(
          '${widget.item['title']}',
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 4),
        Text(
          [
            widget.item['group'],
            viCodeLabel(_type),
            if (widget.item['required'] == true) 'Bắt buộc',
            if (widget.item['requiresPhoto'] == true) 'Cần ảnh',
          ].where((value) => value != null && '$value'.isNotEmpty).join(' · '),
        ),
        const SizedBox(height: 14),
        SegmentedButton<String>(
          segments: const [
            ButtonSegment(
              value: 'COMPLETED',
              icon: Icon(Icons.check_circle_outline),
              label: Text('Đạt'),
            ),
            ButtonSegment(
              value: 'FAILED',
              icon: Icon(Icons.error_outline),
              label: Text('Không đạt'),
            ),
            ButtonSegment(
              value: 'PENDING',
              icon: Icon(Icons.hourglass_empty),
              label: Text('Chưa xử lý'),
            ),
          ],
          selected: {_status},
          showSelectedIcon: false,
          onSelectionChanged: (values) => setState(() {
            _status = values.single;
            if (_status == 'COMPLETED' &&
                {'CHECKBOX', 'DEVICE_CHECK'}.contains(_type)) {
              _value = true;
            }
          }),
        ),
        const SizedBox(height: 14),
        if (_status != 'PENDING') _valueEditor(context),
        if (_status == 'FAILED') ...[
          const SizedBox(height: 12),
          TextField(
            controller: _failure,
            minLines: 2,
            maxLines: 4,
            decoration: const InputDecoration(
              labelText: 'Lý do không đạt *',
              hintText: 'Mô tả để tạo phiếu sự cố hoặc xin chấp thuận ngoại lệ',
            ),
          ),
        ],
        const SizedBox(height: 12),
        TextField(
          controller: _note,
          minLines: 2,
          maxLines: 4,
          decoration: const InputDecoration(labelText: 'Ghi chú'),
        ),
        if (_error != null) ...[
          const SizedBox(height: 10),
          Text(
            _error!,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ],
        const SizedBox(height: 18),
        FilledButton.icon(
          onPressed: _save,
          icon: Icon(_type == 'PHOTO' ? Icons.camera_alt : Icons.save),
          label: Text(
            _type == 'PHOTO' && _status == 'COMPLETED'
                ? 'Chụp ảnh và lưu'
                : 'Lưu lên máy chủ',
          ),
        ),
      ],
    ),
  );

  Widget _valueEditor(BuildContext context) => switch (_type) {
    'CHECKBOX' => SwitchListTile(
      contentPadding: EdgeInsets.zero,
      title: const Text('Đã kiểm tra và đạt yêu cầu'),
      value: _value == true,
      onChanged: _status == 'COMPLETED'
          ? (value) => setState(() => _value = value)
          : null,
    ),
    'YES_NO' => SegmentedButton<bool>(
      segments: const [
        ButtonSegment(value: true, label: Text('Có')),
        ButtonSegment(value: false, label: Text('Không')),
      ],
      selected: {_value == true},
      onSelectionChanged: (values) => setState(() => _value = values.single),
    ),
    'DEVICE_CHECK' => SegmentedButton<bool>(
      segments: const [
        ButtonSegment(value: true, label: Text('Hoạt động')),
        ButtonSegment(value: false, label: Text('Không hoạt động')),
      ],
      selected: {_value == true},
      onSelectionChanged: (values) => setState(() => _value = values.single),
    ),
    'NUMBER' => TextField(
      controller: _text,
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      decoration: InputDecoration(
        labelText: 'Số lượng',
        helperText: [
          if (_rules['min'] != null) 'Tối thiểu ${_rules['min']}',
          if (_rules['max'] != null) 'Tối đa ${_rules['max']}',
        ].join(' · '),
      ),
    ),
    'TEXT' => TextField(
      controller: _text,
      minLines: 2,
      maxLines: 5,
      decoration: const InputDecoration(labelText: 'Nội dung'),
    ),
    'QR_SCAN' => TextField(
      controller: _text,
      readOnly: true,
      decoration: InputDecoration(
        labelText: 'Giá trị mã QR/mã vạch',
        prefixIcon: const Icon(Icons.qr_code_scanner),
        helperText: 'Giá trị chỉ được lấy trực tiếp từ máy ảnh.',
        suffixIcon: IconButton(
          tooltip: 'Mở máy quét',
          onPressed: () async {
            final value = await scanRoomQr(context);
            if (value != null && mounted) setState(() => _text.text = value);
          },
          icon: const Icon(Icons.center_focus_strong),
        ),
      ),
    ),
    'SINGLE_SELECT' => DropdownButtonFormField<Object?>(
      initialValue: _options.any((option) => option['value'] == _value)
          ? _value
          : null,
      decoration: const InputDecoration(labelText: 'Chọn một giá trị'),
      items: [
        for (final option in _options)
          DropdownMenuItem(
            value: option['value'],
            child: Text('${option['label'] ?? option['value']}'),
          ),
      ],
      onChanged: (value) => setState(() => _value = value),
    ),
    'MULTI_SELECT' => Column(
      children: [
        for (final option in _options)
          CheckboxListTile(
            contentPadding: EdgeInsets.zero,
            title: Text('${option['label'] ?? option['value']}'),
            value: (_value as List? ?? const []).contains(option['value']),
            onChanged: (selected) {
              final values = List<Object?>.from(_value as List? ?? const []);
              if (selected == true) {
                if (!values.contains(option['value'])) {
                  values.add(option['value']);
                }
              } else {
                values.remove(option['value']);
              }
              setState(() => _value = values);
            },
          ),
      ],
    ),
    'PHOTO' => const ListTile(
      contentPadding: EdgeInsets.zero,
      leading: Icon(Icons.camera_alt),
      title: Text('Ứng dụng sẽ mở máy ảnh'),
      subtitle: Text('Ảnh sẽ được tải trực tiếp lên máy chủ.'),
    ),
    _ => const Text('Loại hạng mục kiểm tra chưa được hỗ trợ trên ứng dụng.'),
  };
}
