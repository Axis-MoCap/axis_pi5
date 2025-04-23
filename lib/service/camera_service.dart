import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

class CameraService {
  static const MethodChannel _channel = MethodChannel('axis_mocap/camera');
  static const EventChannel _eventChannel =
      EventChannel('axis_mocap/camera_stream');

  // Singleton instance
  static final CameraService _instance = CameraService._internal();
  factory CameraService() => _instance;
  CameraService._internal();

  // Python process
  Process? _process;
  StreamSubscription? _stdoutSubscription;
  StreamSubscription? _stderrSubscription;
  final StreamController<ui.Image> _frameStreamController =
      StreamController<ui.Image>.broadcast();

  // Service state
  bool _isInitialized = false;
  bool _isRecording = false;
  String? _currentVideoPath;
  String? _currentProcessedPath;

  // Public getters
  Stream<ui.Image> get cameraStream => _frameStreamController.stream;
  bool get isInitialized => _isInitialized;
  bool get isRecording => _isRecording;

  // Initialize the camera service
  Future<bool> initialize() async {
    if (_isInitialized) {
      return true;
    }

    try {
      // Get the path to the Python script
      final String appDir = (await getApplicationDocumentsDirectory()).path;
      final String scriptPath =
          path.join(appDir, 'backend', 'camera_controller.py');

      // Check if script exists, if not copy from assets
      if (!await File(scriptPath).exists()) {
        print('Camera controller script not found at $scriptPath');
        return false;
      }

      // Create directory structure if needed
      final videoDir = Directory(path.join(
          Platform.environment['HOME'] ?? '', 'Videos', 'axis_mocap'));
      if (!await videoDir.exists()) {
        await videoDir.create(recursive: true);
      }

      // Start the Python process
      print('Starting camera controller process...');
      _process = await Process.start(
        'python3',
        [scriptPath, '--mode', 'stream'],
        workingDirectory: path.dirname(scriptPath),
      );

      // Set up stderr handler for debugging
      _process!.stderr.transform(utf8.decoder).listen((data) {
        print('Camera stderr: $data');
      });

      // Set up stdout handler for frames and status messages
      _processStdout(_process!.stdout);

      // Set up stdin for sending commands
      _process!.stdin.writeln('STATUS');

      _isInitialized = true;
      return true;
    } catch (e) {
      print('Error initializing camera: $e');
      return false;
    }
  }

  // Process stdout from Python script
  void _processStdout(Stream<List<int>> stdout) {
    // Buffer for accumulating bytes
    List<int> buffer = [];
    // JPEG start and end markers
    final startMarker = [0xFF, 0xD8];
    final endMarker = [0xFF, 0xD9];

    stdout.listen((data) {
      try {
        // Check if this is a status message
        String dataStr = utf8.decode(data, allowMalformed: true);
        if (dataStr.startsWith('STATUS:')) {
          _handleStatusMessage(dataStr.substring(7));
          return;
        }

        // Otherwise, treat as binary frame data
        buffer.addAll(data);

        // Check if we have a complete JPEG frame
        int startIdx = _findSequence(buffer, startMarker);
        if (startIdx >= 0) {
          int endIdx = _findSequence(buffer, endMarker, startIdx + 2);
          if (endIdx >= 0) {
            // We have a complete frame
            endIdx += 2; // Include the end marker
            List<int> frameData = buffer.sublist(startIdx, endIdx);

            // Create an image from the JPEG data
            _createImageFromJpeg(Uint8List.fromList(frameData));

            // Remove the processed frame from buffer
            buffer = buffer.sublist(endIdx);
          }
        }
      } catch (e) {
        print('Error processing camera output: $e');
      }
    }, onError: (error) {
      print('Error from camera stream: $error');
    });
  }

  // Find a byte sequence in a buffer
  int _findSequence(List<int> buffer, List<int> sequence, [int startFrom = 0]) {
    for (int i = startFrom; i <= buffer.length - sequence.length; i++) {
      bool found = true;
      for (int j = 0; j < sequence.length; j++) {
        if (buffer[i + j] != sequence[j]) {
          found = false;
          break;
        }
      }
      if (found) return i;
    }
    return -1;
  }

  // Create an Image from JPEG data
  void _createImageFromJpeg(Uint8List jpegData) {
    ui.decodeImageFromList(jpegData, (ui.Image image) {
      if (!_frameStreamController.isClosed) {
        _frameStreamController.add(image);
      }
    });
  }

  // Handle status messages from Python script
  void _handleStatusMessage(String message) {
    try {
      if (message.startsWith('RECORDING_SAVED:')) {
        _currentVideoPath = message.substring('RECORDING_SAVED:'.length);
        print('Recording saved: $_currentVideoPath');
      } else if (message.startsWith('PROCESSED_FILE:')) {
        _currentProcessedPath = message.substring('PROCESSED_FILE:'.length);
        print('Processed file: $_currentProcessedPath');
      } else {
        // Try to parse as JSON status
        final status = json.decode(message);
        _isRecording = status['recording'] ?? false;
        _currentVideoPath = status['video_path'];
        _currentProcessedPath = status['processed_path'];
      }
    } catch (e) {
      print('Error handling status message: $e');
    }
  }

  // Start recording
  Future<bool> startRecording() async {
    if (!_isInitialized) {
      return false;
    }

    if (_isRecording) {
      return true; // Already recording
    }

    try {
      final timestamp = DateFormat('yyyyMMdd_HHmmss').format(DateTime.now());
      final filename = 'mocap_$timestamp';

      _process?.stdin.writeln('START_RECORDING:$filename');
      _isRecording = true;
      return true;
    } catch (e) {
      print('Error starting recording: $e');
      return false;
    }
  }

  // Stop recording
  Future<bool> stopRecording() async {
    if (!_isInitialized || !_isRecording) {
      return false;
    }

    try {
      _process?.stdin.writeln('STOP_RECORDING');
      _isRecording = false;
      return true;
    } catch (e) {
      print('Error stopping recording: $e');
      return false;
    }
  }

  // Get information about the latest recording
  Map<String, String?> getLatestRecordingInfo() {
    return {
      'videoPath': _currentVideoPath,
      'processedPath': _currentProcessedPath,
    };
  }

  // Clean up resources
  void dispose() {
    if (_isRecording) {
      stopRecording();
    }

    _frameStreamController.close();

    if (_process != null) {
      _process!.stdin.writeln('EXIT');
      _process!.kill();
      _process = null;
    }

    _isInitialized = false;
  }
}
