import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:network_info_plus/network_info_plus.dart';

Future<bool> ensureLocationPermission() async {
  if (!await Geolocator.isLocationServiceEnabled()) return false;
  var permission = await Geolocator.checkPermission();
  if (permission == LocationPermission.denied) {
    permission = await Geolocator.requestPermission();
  }
  return permission == LocationPermission.always ||
      permission == LocationPermission.whileInUse;
}

Future<Map<String, Object?>?> captureLocationEvidence() async {
  if (!await ensureLocationPermission()) return null;
  final position = await Geolocator.getCurrentPosition(
    locationSettings: const LocationSettings(
      accuracy: LocationAccuracy.high,
      timeLimit: Duration(seconds: 20),
    ),
  );
  return {
    'latitude': position.latitude,
    'longitude': position.longitude,
    'accuracyMeters': position.accuracy,
    'capturedAt': position.timestamp.toUtc().toIso8601String(),
  };
}

Future<String?> captureWifiEvidence() async {
  // Android and iOS protect Wi-Fi identifiers behind location permission.
  if (!await ensureLocationPermission()) return null;
  final info = NetworkInfo();
  final bssid = (await info.getWifiBSSID())?.trim();
  if (bssid != null && bssid.isNotEmpty) return bssid;
  final ssid = (await info.getWifiName())?.replaceAll('"', '').trim();
  return ssid == null || ssid.isEmpty ? null : ssid;
}

Future<String?> scanRoomQr(BuildContext context) => Navigator.of(
  context,
).push(MaterialPageRoute<String>(builder: (_) => const _RoomQrScanner()));

class _RoomQrScanner extends StatefulWidget {
  const _RoomQrScanner();

  @override
  State<_RoomQrScanner> createState() => _RoomQrScannerState();
}

class _RoomQrScannerState extends State<_RoomQrScanner> {
  final _controller = MobileScannerController(
    formats: const [BarcodeFormat.qrCode],
  );
  bool _resolved = false;

  void _detected(BarcodeCapture capture) {
    if (_resolved) return;
    for (final barcode in capture.barcodes) {
      final value = barcode.rawValue?.trim();
      if (value == null || value.isEmpty) continue;
      _resolved = true;
      Navigator.pop(context, value);
      return;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Quét QR phòng')),
    body: Stack(
      fit: StackFit.expand,
      children: [
        MobileScanner(controller: _controller, onDetect: _detected),
        Center(
          child: Container(
            width: 240,
            height: 240,
            decoration: BoxDecoration(
              border: Border.all(color: Colors.white, width: 3),
              borderRadius: BorderRadius.circular(20),
            ),
          ),
        ),
        const Positioned(
          left: 24,
          right: 24,
          bottom: 36,
          child: Card(
            child: Padding(
              padding: EdgeInsets.all(12),
              child: Text(
                'Đưa mã QR gắn tại phòng vào giữa khung.',
                textAlign: TextAlign.center,
              ),
            ),
          ),
        ),
      ],
    ),
  );
}
