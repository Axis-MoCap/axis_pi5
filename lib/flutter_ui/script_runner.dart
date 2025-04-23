import 'package:flutter/material.dart';
import 'dart:io';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:flutter/services.dart' show rootBundle, Clipboard, ClipboardData;

class ScriptRunner extends StatefulWidget {
  const ScriptRunner({super.key});

  @override
  State<ScriptRunner> createState() => _ScriptRunnerState();
}

class _ScriptRunnerState extends State<ScriptRunner> {
  String _output = '';
  bool _isLoading = false;
  String? _pythonScriptsDir;
  final TextEditingController _pathController = TextEditingController();

  @override
  void initState() {
    super.initState();
    // Initialize the Python scripts directory
    _findPythonScriptsDir();
  }

  @override
  void dispose() {
    _pathController.dispose();
    super.dispose();
  }

  Future<void> _findPythonScriptsDir() async {
    try {
      // Try to find the Python scripts directory using various approaches
      final possiblePaths = [
        // Check for script in the current directory
        p.join(Directory.current.path, 'python_scripts'),
        
        // Check one level up (useful in some Flutter configurations)
        p.join(Directory.current.path, '..', 'python_scripts'),
        
        // Check for app bundle path
        p.join(p.dirname(Platform.resolvedExecutable), 'python_scripts'),
        
        // Check for absolute path
        r'C:\Users\Yvonne\flutterpytest\python_scripts',
      ];
      
      // Test each path and use the first one that exists
      for (final path in possiblePaths) {
        final dir = Directory(path);
        if (dir.existsSync()) {
          debugPrint('Found Python scripts directory at: $path');
          setState(() {
            _pythonScriptsDir = path;
            _pathController.text = path;
          });
          return;
        }
      }
      
      debugPrint('WARNING: Could not find Python scripts directory in any of the expected locations');
    } catch (e) {
      debugPrint('Error finding Python scripts directory: $e');
    }
  }

  // Update the Python scripts directory based on user input
  void _updatePythonScriptsDir(String path) {
    if (path.isEmpty) return;
    
    final dir = Directory(path);
    if (dir.existsSync()) {
      setState(() {
        _pythonScriptsDir = path;
        _output = 'Python scripts directory updated to: $path';
      });
    } else {
      setState(() {
        _output = 'Error: Directory does not exist: $path';
      });
    }
  }

  Future<void> _runPythonScript({String scriptName = 'mocap.py'}) async {
    if (_pythonScriptsDir == null) {
      await _findPythonScriptsDir();
      if (_pythonScriptsDir == null) {
        setState(() {
          _output = '''
ERROR: Failed to find Python scripts directory.
Expected locations:
- ${p.join(Directory.current.path, 'python_scripts')}
- ${p.join(Directory.current.path, '..', 'python_scripts')}
- ${p.join(p.dirname(Platform.resolvedExecutable), 'python_scripts')}
- C:\\Users\\Yvonne\\flutterpytest\\python_scripts

Current directory: ${Directory.current.path}
''';
        });
        return;
      }
    }

    setState(() {
      _output = 'Running script: $scriptName...';
      _isLoading = true;
    });

    try {
      final scriptPath = p.join(_pythonScriptsDir!, scriptName);
      
      // Check if script exists
      if (!File(scriptPath).existsSync()) {
        setState(() {
          _output = 'ERROR: Script not found at: $scriptPath';
          _isLoading = false;
        });
        return;
      }
      
      // Print the path for debugging
      debugPrint('Running script at: $scriptPath');
      
      // Use python on Windows, python3 on other platforms
      final pythonExecutable = Platform.isWindows ? 'python' : 'python3';
      
      // Run the Python script with the working directory set to the scripts folder
      final result = await Process.run(
        pythonExecutable, 
        [scriptPath],
        workingDirectory: _pythonScriptsDir,
      );

      setState(() {
        _output = result.stdout.toString().trim();
        if (_output.isEmpty && result.stderr.toString().trim().isNotEmpty) {
          _output = 'Error: ${result.stderr}';
        }
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _output = 'Error: $e';
        _isLoading = false;
      });
    }
  }

  Future<void> _runTestScript() async {
    await _runPythonScript(scriptName: 'test_script.py');
  }

  Future<void> _runSimpleTest() async {
    await _runPythonScript(scriptName: 'simple_test.py');
  }

  Future<void> _runMocapScript() async {
    await _runPythonScript(scriptName: 'mocap.py');
  }

  Future<void> _runHelloWorld() async {
    await _runPythonScript(scriptName: 'hello_world.py');
  }

  Future<String> _copyPythonScriptsToDocuments(String destinationDir) async {
    // Create a List of files to copy from the python_scripts directory
    // These should be added to your assets in pubspec.yaml
    final scriptFiles = [
      'mocap.py',
      'body_keypoint_track.py',
      'skeleton_ik_solver.py',
      'skeleton_config.py',
      'Tracking.py',
      'hello_world.py',
      'test_script.py',
      // Add any other required Python files or modules here
    ];
    
    // Copy each file from assets to documents directory
    final mocapPath = p.join(destinationDir, 'mocap.py');
    
    try {
      // Try both asset paths for redundancy
      for (final scriptFile in scriptFiles) {
        bool copied = false;
        
        // Try asset path first
        try {
          final assetData = await rootBundle.load('assets/python_scripts/$scriptFile');
          final bytes = assetData.buffer.asUint8List();
          
          await File(p.join(destinationDir, scriptFile)).writeAsBytes(bytes);
          debugPrint('Copied $scriptFile from assets/python_scripts/');
          copied = true;
        } catch (e) {
          debugPrint('Asset method failed for assets/python_scripts/$scriptFile: $e');
        }
        
        // If first method failed, try the second asset path
        if (!copied) {
          try {
            final assetData = await rootBundle.load('python_scripts/$scriptFile');
            final bytes = assetData.buffer.asUint8List();
            
            await File(p.join(destinationDir, scriptFile)).writeAsBytes(bytes);
            debugPrint('Copied $scriptFile from python_scripts/');
            copied = true;
          } catch (e) {
            debugPrint('Asset method failed for python_scripts/$scriptFile: $e');
          }
        }
        
        // If both asset methods failed, try direct file copy
        if (!copied) {
          try {
            final sourceFile = File(p.join(Directory.current.path, 'python_scripts', scriptFile));
            if (sourceFile.existsSync()) {
              await sourceFile.copy(p.join(destinationDir, scriptFile));
              debugPrint('Copied $scriptFile from current directory');
              copied = true;
            }
          } catch (e) {
            debugPrint('File copy method failed for $scriptFile: $e');
          }
        }
        
        if (!copied) {
          debugPrint('WARNING: Failed to copy $scriptFile');
        }
      }
    } catch (e) {
      debugPrint('Error copying Python scripts: $e');
      setState(() {
        _output += '\nFailed to copy Python scripts: $e';
      });
    }
    
    return mocapPath;
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        // Python Scripts Path Input
        Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Python Scripts Directory:', style: TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(height: 4),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _pathController,
                      decoration: const InputDecoration(
                        border: OutlineInputBorder(),
                        contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        isDense: true,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  ElevatedButton(
                    onPressed: () => _updatePythonScriptsDir(_pathController.text),
                    child: const Text('Update'),
                  ),
                  const SizedBox(width: 8),
                  IconButton(
                    icon: const Icon(Icons.content_copy),
                    tooltip: 'Copy current directory',
                    onPressed: () {
                      Clipboard.setData(ClipboardData(text: Directory.current.path));
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Current directory copied to clipboard')),
                      );
                    },
                  ),
                ],
              ),
            ],
          ),
        ),
        
        // Simple Hello World Button
        ElevatedButton(
          onPressed: _isLoading ? null : _runHelloWorld,
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.blue,
            foregroundColor: Colors.white,
          ),
          child: const Text('Run Hello World'),
        ),
        const SizedBox(height: 16),
        
        // Simple Test Script Button
        ElevatedButton(
          onPressed: _isLoading ? null : _runSimpleTest,
          child: const Text('Run Simple Test'),
        ),
        const SizedBox(height: 16),
        
        // Test Script Button
        ElevatedButton(
          onPressed: _isLoading ? null : _runTestScript,
          child: const Text('Run Full Test Script'),
        ),
        const SizedBox(height: 16),
        
        // MoCap Script Button
        ElevatedButton(
          onPressed: _isLoading ? null : _runMocapScript,
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.green,
            foregroundColor: Colors.white,
          ),
          child: _isLoading 
              ? const CircularProgressIndicator(strokeWidth: 2, color: Colors.white)
              : const Text('Run MoCap Script'),
        ),
        
        const SizedBox(height: 20),
        Expanded(
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.black.withOpacity(0.05),
              borderRadius: BorderRadius.circular(8),
            ),
            child: SingleChildScrollView(
              child: Text(
                _output.isEmpty ? 'Output will appear here...' : _output,
                style: const TextStyle(fontSize: 14, fontFamily: 'monospace'),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
