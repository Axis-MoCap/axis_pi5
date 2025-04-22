import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'python_bridge.dart';
import 'dart:convert';

enum CameraType {
  raspberryPi,
  raspberryPi5,  // Added new camera type for Raspberry Pi 5
  webCamera,
  none,
}

class CameraService {
  // Singleton pattern
  static final CameraService _instance = CameraService._internal();
  factory CameraService() => _instance;

  CameraService._internal() {
    _pythonBridge = PythonBridge();
    _init();
  }

  // Python bridge for camera access
  late final PythonBridge _pythonBridge;

  // Camera state
  CameraType _cameraType = CameraType.none;
  CameraType get cameraType => _cameraType;
  bool _isCameraInitialized = false;
  bool get isCameraInitialized => _isCameraInitialized;

  // Camera configuration
  int _frameWidth = 640;
  int _frameHeight = 480;
  int _frameRate = 30;

  // Stream controllers for camera status
  final _cameraStatusController = StreamController<CameraType>.broadcast();
  Stream<CameraType> get cameraStatusStream => _cameraStatusController.stream;

  // Camera detection process
  StreamSubscription? _detectionSubscription;
  String? _cameraPath;

  // Initialize and detect available cameras
  Future<void> _init() async {
    await detectCamera();
  }

  // Detect available cameras
  Future<CameraType> detectCamera() async {
    try {
      // First try to detect Raspberry Pi 5 camera (uses different interface)
      final pi5CameraStream = await _pythonBridge.runPythonScript(
        scriptName: 'detect_camera.py',
        args: ['--type=raspberry5'],
        processId: 'detect_pi5_camera',
      );

      if (pi5CameraStream != null) {
        bool found = false;
        await for (final output in pi5CameraStream) {
          if (output.contains('CAMERA_FOUND:')) {
            _cameraPath = output.split('CAMERA_FOUND:')[1].trim();
            _cameraType = CameraType.raspberryPi5;
            found = true;
            break;
          }
        }

        if (found) {
          _isCameraInitialized = true;
          _cameraStatusController.add(_cameraType);
          debugPrint('Raspberry Pi 5 camera found at: $_cameraPath');
          return _cameraType;
        }
      }

      // Try to detect older Raspberry Pi camera
      final piCameraStream = await _pythonBridge.runPythonScript(
        scriptName: 'detect_camera.py',
        args: ['--type=raspberry'],
        processId: 'detect_pi_camera',
      );

      if (piCameraStream != null) {
        bool found = false;
        await for (final output in piCameraStream) {
          if (output.contains('CAMERA_FOUND:')) {
            _cameraPath = output.split('CAMERA_FOUND:')[1].trim();
            _cameraType = CameraType.raspberryPi;
            found = true;
            break;
          }
        }

        if (found) {
          _isCameraInitialized = true;
          _cameraStatusController.add(_cameraType);
          debugPrint('Raspberry Pi camera found at: $_cameraPath');
          return _cameraType;
        }
      }

      // If Pi camera not found, try to detect web camera
      final webCameraStream = await _pythonBridge.runPythonScript(
        scriptName: 'detect_camera.py',
        args: ['--type=webcam'],
        processId: 'detect_web_camera',
      );

      if (webCameraStream != null) {
        bool found = false;
        await for (final output in webCameraStream) {
          if (output.contains('CAMERA_FOUND:')) {
            _cameraPath = output.split('CAMERA_FOUND:')[1].trim();
            _cameraType = CameraType.webCamera;
            found = true;
            break;
          }
        }

        if (found) {
          _isCameraInitialized = true;
          _cameraStatusController.add(_cameraType);
          debugPrint('Web camera found at: $_cameraPath');
          return _cameraType;
        }
      }

      // No camera found
      _cameraType = CameraType.none;
      _isCameraInitialized = false;
      _cameraStatusController.add(_cameraType);
      debugPrint('No camera found');
      return _cameraType;
    } catch (e) {
      debugPrint('Error detecting camera: $e');
      _cameraType = CameraType.none;
      _isCameraInitialized = false;
      _cameraStatusController.add(_cameraType);
      return _cameraType;
    }
  }

  // Configure camera settings
  void configureCameraSettings({
    int? frameWidth,
    int? frameHeight,
    int? frameRate,
  }) {
    if (frameWidth != null) _frameWidth = frameWidth;
    if (frameHeight != null) _frameHeight = frameHeight;
    if (frameRate != null) _frameRate = frameRate;
  }

  // Get camera type string for Python script
  String _getCameraTypeString() {
    switch (_cameraType) {
      case CameraType.raspberryPi5:
        return "raspberry5";
      case CameraType.raspberryPi:
        return "raspberry";
      case CameraType.webCamera:
        return "webcam";
      default:
        return "unknown";
    }
  }

  // Start camera stream
  Future<Stream<Image>?> startCameraStream() async {
    if (_cameraType == CameraType.none) {
      await detectCamera();
      if (_cameraType == CameraType.none) {
        return null;
      }
    }

    try {
      final streamController = StreamController<Image>.broadcast();

      // Start the camera streaming script with updated parameters
      final cameraStream = await _pythonBridge.runPythonScript(
        scriptName: 'stream_camera.py',
        args: [
          '--camera_path=$_cameraPath',
          '--type=${_getCameraTypeString()}',
          '--width=$_frameWidth',
          '--height=$_frameHeight',
          '--fps=$_frameRate',
        ],
        processId: 'camera_stream',
        captureOutput: true,
      );

      if (cameraStream == null) {
        return null;
      }

      // Process the frame data from the script
      _detectionSubscription = cameraStream.listen(
        (data) {
          // Decode base64-encoded frames sent from Python script
          try {
            final trimmed = data.trim();
            if (trimmed.startsWith('FRAME:')) {
              final base64Str = trimmed.substring('FRAME:'.length);
              final bytes = base64Decode(base64Str);
              streamController.add(Image.memory(
                bytes,
                gaplessPlayback: true, // Prevents flickering
              ));
            }
          } catch (e) {
            debugPrint('Error decoding frame: $e');
          }
        },
        onError: (error) {
          debugPrint('Camera stream error: $error');
        },
        onDone: () {
          streamController.close();
        },
      );

      return streamController.stream;
    } catch (e) {
      debugPrint('Error starting camera stream: $e');
      return null;
    }
  }

  // Stop camera stream
  Future<void> stopCameraStream() async {
    await _pythonBridge.killProcess('camera_stream');
    await _detectionSubscription?.cancel();
    _detectionSubscription = null;
  }

  // Dispose
  void dispose() {
    stopCameraStream();
    _cameraStatusController.close();
  }
}

// Placeholder component for camera not found
class CameraNotFound extends StatelessWidget {
  const CameraNotFound({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.black,
      child: const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.videocam_off,
              color: Colors.red,
              size: 48,
            ),
            SizedBox(height: 16),
            Text(
              'Camera Not Found',
              style: TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
            SizedBox(height: 8),
            Text(
              'Please connect a camera and restart the app',
              style: TextStyle(
                color: Colors.grey,
                fontSize: 14,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
