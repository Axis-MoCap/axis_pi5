import 'dart:io';
import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

class PythonBridge {
  // Singleton pattern
  static final PythonBridge _instance = PythonBridge._internal();
  factory PythonBridge() => _instance;
  PythonBridge._internal() {
    _initScriptsPath();
  }

  // Scripts directory (will be initialized properly)
  String _scriptsPath = 'python_scripts';
  bool _initialized = false;

  Future<void> _initScriptsPath() async {
    try {
      List<String> possiblePaths = [];

      if (Platform.isLinux) {
        // Try to detect if we're on a Raspberry Pi
        bool isRaspberryPi = false;
        try {
          // Try to read the model from /proc/cpuinfo
          final cpuInfo = File('/proc/cpuinfo').readAsStringSync();
          isRaspberryPi =
              cpuInfo.contains('Raspberry Pi') || cpuInfo.contains('BCM');
          debugPrint('CPU Info check: isRaspberryPi = $isRaspberryPi');
        } catch (e) {
          debugPrint('Error reading CPU info: $e');
          // Ignore errors, assume not a Raspberry Pi
        }

        // Add possible paths based on platform
        if (isRaspberryPi) {
          possiblePaths.add('/home/pi/axis_mocap/python_scripts');
        }

        // Add current directory and standardized locations
        possiblePaths.add(path.join(Directory.current.path, 'python_scripts'));
        possiblePaths.add('/usr/local/share/axis_mocap/python_scripts');
        possiblePaths.add('/opt/axis_mocap/python_scripts');
      } else {
        // For other platforms, use the app documents directory and current directory
        final appDir = await getApplicationDocumentsDirectory();
        possiblePaths.add(path.join(appDir.path, 'python_scripts'));
        possiblePaths.add(path.join(Directory.current.path, 'python_scripts'));
      }

      debugPrint('Possible Python script paths: $possiblePaths');

      // Try each path and use the first one that exists
      for (final scriptPath in possiblePaths) {
        final dir = Directory(scriptPath);
        if (await dir.exists()) {
          _scriptsPath = scriptPath;
          debugPrint('Using Python scripts path: $_scriptsPath');

          // Make scripts executable
          await _makeScriptsExecutable();
          _initialized = true;
          return;
        }
      }

      // If no existing directory is found, use the first path but print a warning
      _scriptsPath = possiblePaths.first;
      debugPrint(
          'WARNING: No existing scripts directory found. Using: $_scriptsPath');

      // Create the directory if it doesn't exist
      await Directory(_scriptsPath).create(recursive: true);
      _initialized = true;
    } catch (e) {
      debugPrint('Error initializing scripts path: $e');
      // Keep the default path as fallback
      _initialized = true; // Still mark as initialized to avoid hanging
    }
  }

  // Make Python scripts executable
  Future<void> _makeScriptsExecutable() async {
    if (!Platform.isWindows) {
      try {
        final dir = Directory(_scriptsPath);
        if (await dir.exists()) {
          final entities = await dir.list().toList();
          for (final entity in entities) {
            if (entity is File && entity.path.endsWith('.py')) {
              // chmod +x on the script
              final result = await Process.run('chmod', ['+x', entity.path]);
              if (result.exitCode != 0) {
                debugPrint('Warning: Failed to make ${entity.path} executable');
              } else {
                debugPrint('Made ${entity.path} executable');
              }
            }
          }
        }
      } catch (e) {
        debugPrint('Error making scripts executable: $e');
      }
    }
  }

  // Wait for initialization to complete
  Future<void> ensureInitialized() async {
    // If initialization is still in progress, wait for it to complete
    int attempts = 0;
    while (!_initialized && attempts < 10) {
      await Future.delayed(const Duration(milliseconds: 100));
      attempts++;
    }

    if (!_initialized) {
      debugPrint('WARNING: PythonBridge initialization timed out');
    }
  }

  // Active processes
  final Map<String, Process> _activeProcesses = {};

  // Stream controllers for process output
  final Map<String, StreamController<String>> _outputControllers = {};

  // Get stream for a specific process
  Stream<String>? getProcessStream(String processId) {
    return _outputControllers[processId]?.stream;
  }

  // Check if a process is running
  bool isProcessRunning(String processId) {
    return _activeProcesses.containsKey(processId);
  }

  // Execute Python script and return a stream of its output
  Future<Stream<String>?> runPythonScript({
    required String scriptName,
    List<String> args = const [],
    String processId = '',
    bool captureOutput = true,
  }) async {
    try {
      // Ensure the bridge is initialized
      await ensureInitialized();

      final id = processId.isEmpty ? scriptName : processId;

      // Check if we already have this process running
      if (_activeProcesses.containsKey(id)) {
        return _outputControllers[id]?.stream;
      }

      // Create stream controller for process output
      if (captureOutput) {
        _outputControllers[id] = StreamController<String>.broadcast();
      }

      // Handle absolute paths in scriptName
      String fullScriptPath;
      if (scriptName.startsWith('lib/')) {
        // This is an absolute path from the project root
        fullScriptPath = scriptName;
      } else {
        // This is a relative path to the scripts directory
        fullScriptPath = path.join(_scriptsPath, scriptName);
      }

      // Make sure the script exists
      final scriptFile = File(fullScriptPath);
      if (!await scriptFile.exists()) {
        final error = 'ERROR: Script not found: $fullScriptPath';
        debugPrint('### PYTHON ERROR: $error ###');

        if (captureOutput) {
          _outputControllers[id]?.add(error);
          _outputControllers[id]?.close();
          _outputControllers.remove(id);
        }
        return null;
      }

      // Choose the command based on platform
      String command;
      List<String> commandArgs;

      if (Platform.isWindows) {
        command = 'python';
        commandArgs = [fullScriptPath, ...args];
      } else {
        // On Unix platforms, try to run the script directly if it's executable
        try {
          // Make the script executable
          await Process.run('chmod', ['+x', fullScriptPath]);

          command = fullScriptPath;
          commandArgs = args;
        } catch (e) {
          // If making the script executable fails, fall back to python3
          debugPrint(
              '### PYTHON WARNING: Failed to make script executable: $e, falling back to python3 ###');
          command = 'python3';
          commandArgs = [fullScriptPath, ...args];
        }
      }

      debugPrint('### PYTHON: Running: $command ${commandArgs.join(' ')} ###');

      // Start the process
      final process = await Process.start(
        command,
        commandArgs,
        workingDirectory: path.dirname(fullScriptPath),
        includeParentEnvironment: true,
      );
      _activeProcesses[id] = process;

      // Handle process output
      if (captureOutput) {
        // Handle stdout
        process.stdout.transform(const SystemEncoding().decoder).listen((data) {
          _outputControllers[id]?.add(data);
          // Only print important messages to reduce noise
          if (data.contains('Error') ||
              data.contains('Recording') ||
              data.contains('Processing') ||
              data.contains('STATUS:')) {
            debugPrint('### PYTHON [$id]: $data ###');
          }
        });

        // Handle stderr
        process.stderr.transform(const SystemEncoding().decoder).listen((data) {
          _outputControllers[id]?.add('ERROR: $data');
          // Only print real errors, not noise
          if (data.trim().isNotEmpty &&
              !data.contains('WARNING:') &&
              !data.contains('DEBUG:')) {
            debugPrint('### PYTHON ERROR [$id]: $data ###');
          }
        });
      }

      // Handle process exit
      process.exitCode.then((exitCode) {
        debugPrint('### PYTHON [$id]: Process exited with code $exitCode ###');
        _activeProcesses.remove(id);

        if (captureOutput) {
          _outputControllers[id]
              ?.add('Process completed with exit code: $exitCode');
          _outputControllers[id]?.close();
          _outputControllers.remove(id);
        }
      });

      return captureOutput ? _outputControllers[id]?.stream : null;
    } catch (e) {
      debugPrint('### PYTHON ERROR: Failed to run Python script: $e ###');
      return null;
    }
  }

  // Kill a running process
  Future<bool> killProcess(String processId) async {
    if (_activeProcesses.containsKey(processId)) {
      try {
        _activeProcesses[processId]?.kill();
        _activeProcesses.remove(processId);

        if (_outputControllers.containsKey(processId)) {
          _outputControllers[processId]?.add('Process terminated by user');
          _outputControllers[processId]?.close();
          _outputControllers.remove(processId);
        }

        return true;
      } catch (e) {
        debugPrint('Error killing process: $e');
        return false;
      }
    }
    return false;
  }

  // Kill all running processes
  Future<void> killAllProcesses() async {
    final processes = List<String>.from(_activeProcesses.keys);
    for (final id in processes) {
      await killProcess(id);
    }
  }
}
