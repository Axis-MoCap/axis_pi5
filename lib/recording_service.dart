import 'dart:async';
import 'package:flutter/foundation.dart';
import 'python_bridge.dart';

enum RecordingStatus {
  idle,
  initializing,
  recording,
  processing,
  error,
}

class RecordingService {
  // Singleton pattern
  static final RecordingService _instance = RecordingService._internal();
  factory RecordingService() => _instance;
  RecordingService._internal() {
    _pythonBridge = PythonBridge();
  }

  // Python bridge instance
  late final PythonBridge _pythonBridge;

  // Recording state
  RecordingStatus _status = RecordingStatus.idle;
  RecordingStatus get status => _status;

  // Stream controllers
  final _recordingStatusController =
      StreamController<RecordingStatus>.broadcast();
  final _recordingOutputController = StreamController<String>.broadcast();

  // Streams
  Stream<RecordingStatus> get statusStream => _recordingStatusController.stream;
  Stream<String> get outputStream => _recordingOutputController.stream;

  // Recording parameters
  String? _sessionName;
  StreamSubscription? _recordingSubscription;

  // Start recording function
  Future<bool> startRecording({
    required String sessionName,
    Map<String, String> params = const {},
  }) async {
    if (_status == RecordingStatus.recording) {
      _recordingOutputController.add('Already recording');
      return false;
    }

    try {
      _sessionName = sessionName;

      // Update status
      _setStatus(RecordingStatus.initializing);

      // Build arguments list from parameters
      final args = <String>[];
      args.add('--session=$sessionName');

      // Add any additional parameters
      params.forEach((key, value) {
        args.add('--$key=$value');
      });

      // Call the recording Python script
      final outputStream = await _pythonBridge.runPythonScript(
        scriptName: 'record.py',
        args: args,
        processId: 'recording',
      );

      if (outputStream == null) {
        _setStatus(RecordingStatus.error);
        _recordingOutputController.add('Failed to start recording process');
        return false;
      }

      // Subscribe to the output
      _recordingSubscription = outputStream.listen(
        (data) {
          _recordingOutputController.add(data);

          // You can parse the output to update status based on script responses
          if (data.contains('Recording started')) {
            _setStatus(RecordingStatus.recording);
          } else if (data.contains('Processing')) {
            _setStatus(RecordingStatus.processing);
          } else if (data.contains('Error')) {
            _setStatus(RecordingStatus.error);
          }
        },
        onError: (error) {
          _recordingOutputController.add('Error: $error');
          _setStatus(RecordingStatus.error);
        },
        onDone: () {
          _setStatus(RecordingStatus.idle);
          _recordingSubscription = null;
        },
      );

      _setStatus(RecordingStatus.recording);
      return true;
    } catch (e) {
      _recordingOutputController.add('Error starting recording: $e');
      _setStatus(RecordingStatus.error);
      return false;
    }
  }

  // Stop recording function
  Future<bool> stopRecording() async {
    if (_status != RecordingStatus.recording) {
      return false;
    }

    try {
      // Kill the recording process
      final result = await _pythonBridge.killProcess('recording');

      // Clean up
      await _recordingSubscription?.cancel();
      _recordingSubscription = null;
      _sessionName = null;

      _setStatus(RecordingStatus.idle);
      return result;
    } catch (e) {
      _recordingOutputController.add('Error stopping recording: $e');
      return false;
    }
  }

  // Update the status and notify listeners
  void _setStatus(RecordingStatus newStatus) {
    _status = newStatus;
    _recordingStatusController.add(newStatus);
  }

  // Method to run post-processing scripts
  Future<bool> processRecording({
    required String sessionName,
    String outputFormat = 'fbx',
  }) async {
    try {
      _setStatus(RecordingStatus.processing);

      final outputStream = await _pythonBridge.runPythonScript(
        scriptName: 'process.py',
        args: ['--session=$sessionName', '--format=$outputFormat'],
        processId: 'processing',
      );

      if (outputStream == null) {
        _setStatus(RecordingStatus.error);
        _recordingOutputController.add('Failed to start processing');
        return false;
      }

      // Listen for completion
      await for (final data in outputStream) {
        _recordingOutputController.add(data);
        if (data.contains('Process completed with exit code: 0')) {
          _setStatus(RecordingStatus.idle);
          return true;
        }
      }

      return true;
    } catch (e) {
      _recordingOutputController.add('Error processing recording: $e');
      _setStatus(RecordingStatus.error);
      return false;
    }
  }

  // Method to get available sessions from Python script
  Future<List<String>> getAvailableSessions() async {
    try {
      final sessions = <String>[];
      final outputStream = await _pythonBridge.runPythonScript(
        scriptName: 'list_sessions.py',
        processId: 'list_sessions',
      );

      if (outputStream != null) {
        await for (final data in outputStream) {
          // Assuming the Python script outputs one session name per line
          if (!data.startsWith('ERROR:') &&
              !data.contains('Process completed')) {
            sessions.add(data.trim());
          }
        }
      }

      return sessions;
    } catch (e) {
      debugPrint('Error getting sessions: $e');
      return [];
    }
  }

  // Dispose method
  void dispose() {
    _recordingSubscription?.cancel();
    _recordingStatusController.close();
    _recordingOutputController.close();
    _pythonBridge.killAllProcesses();
  }
}
