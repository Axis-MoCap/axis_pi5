import 'package:flutter/material.dart';
import 'dart:io';

class ScriptRunner extends StatefulWidget {
  const ScriptRunner({super.key});

  @override
  State<ScriptRunner> createState() => _ScriptRunnerState();
}

class _ScriptRunnerState extends State<ScriptRunner> {
  String _output = '';

  Future<void> _runPythonScript() async {
    setState(() {
      _output = 'Running script...';
    });

    try {
      final result = await Process.run('python3',
          ['${Directory.current.path}/python_scripts/hello_world.py']);

      setState(() {
        _output = result.stdout.toString().trim();
        if (_output.isEmpty && result.stderr.toString().isNotEmpty) {
          _output = 'Error: ${result.stderr}';
        }
      });
    } catch (e) {
      setState(() {
        _output = 'Error: $e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        ElevatedButton(
          onPressed: _runPythonScript,
          child: const Text('Run Python Script'),
        ),
        const SizedBox(height: 20),
        Text(
          _output,
          style: const TextStyle(fontSize: 16),
        ),
      ],
    );
  }
}
