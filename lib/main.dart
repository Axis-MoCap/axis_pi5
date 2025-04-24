import 'package:flutter/material.dart';
import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'dart:math' as math;
import 'dart:async';
import 'package:intl/intl.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'recording_service.dart';
import 'camera_service.dart';
import 'authentication/register_page.dart';
import 'authentication/login_page.dart';
import 'pages/on_boarding.dart';
import 'dart:typed_data';
import 'package:path/path.dart' as path;
import 'dart:ui' as ui;
import 'Backend/script_runner.dart';

void main() {
  runApp(const AxisMocapApp());
}

class AxisMocapApp extends StatelessWidget {
  const AxisMocapApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Axis Advanced Motion Capture System',
      theme: ThemeData(
        colorScheme: ColorScheme.dark(
          primary: Colors.red.shade400,
          secondary: Colors.redAccent,
          surface: const Color(0xFF222222),
          background: const Color(0xFF121212),
        ),
        appBarTheme: const AppBarTheme(
          elevation: 0,
        ),
        useMaterial3: true,
      ),
      // Start with the onboarding/login flow instead of going directly to home
      home: const Onboarding(),
    );
  }
}

class MocapSession {
  String id;
  String name;
  Duration recordingDuration;
  String date;
  bool hasPklFile;
  bool hasRawVideo;
  String? folderPath;

  MocapSession({
    required this.name,
    required this.recordingDuration,
    required this.date,
    this.hasPklFile = true,
    this.hasRawVideo = true,
    this.folderPath,
  }) : id = DateTime.now().millisecondsSinceEpoch.toString() +
            math.Random().nextInt(10000).toString();

  // Format the duration as mm:ss
  String get formattedDuration {
    return '${recordingDuration.inMinutes.toString().padLeft(2, '0')}:${(recordingDuration.inSeconds % 60).toString().padLeft(2, '0')}';
  }

  // Create a session folder with .pkl and raw video files
  Future<void> createSessionFolder() async {
    try {
      final appDir = await getApplicationDocumentsDirectory();
      final sessionDir = Directory('${appDir.path}/axis_mocap_sessions/$id');

      if (!await sessionDir.exists()) {
        await sessionDir.create(recursive: true);
      }

      folderPath = sessionDir.path;

      // Create placeholder files for demo purposes
      if (hasPklFile) {
        final pklFile = File('$folderPath/$name.pkl');
        await pklFile.writeAsString('Motion capture data placeholder');
      }

      if (hasRawVideo) {
        final videoFile = File('$folderPath/$name.mp4');
        await videoFile.writeAsString('Raw video placeholder');
      }
    } catch (e) {
      debugPrint('Error creating session folder: $e');
    }
  }

  // Delete the session folder and all its contents
  Future<bool> deleteSession() async {
    try {
      if (folderPath != null) {
        final dir = Directory(folderPath!);
        if (await dir.exists()) {
          await dir.delete(recursive: true);
          return true;
        }
      }
      return false;
    } catch (e) {
      debugPrint('Error deleting session: $e');
      return false;
    }
  }

  // Rename the session and update folder contents
  Future<bool> renameSession(String newName) async {
    try {
      if (folderPath != null) {
        // Rename pkl file if exists
        if (hasPklFile) {
          final oldPklFile = File('$folderPath/$name.pkl');
          if (await oldPklFile.exists()) {
            final newPklFile = File('$folderPath/$newName.pkl');
            await oldPklFile.rename(newPklFile.path);
          }
        }

        // Rename video file if exists
        if (hasRawVideo) {
          final oldVideoFile = File('$folderPath/$name.mp4');
          if (await oldVideoFile.exists()) {
            final newVideoFile = File('$folderPath/$newName.mp4');
            await oldVideoFile.rename(newVideoFile.path);
          }
        }

        name = newName;
        return true;
      }
      return false;
    } catch (e) {
      debugPrint('Error renaming session: $e');
      return false;
    }
  }
}

class MocapHomePage extends StatefulWidget {
  const MocapHomePage({super.key, required this.title});

  final String title;

  @override
  State<MocapHomePage> createState() => _MocapHomePageState();
}

class _MocapHomePageState extends State<MocapHomePage>
    with SingleTickerProviderStateMixin {
  bool _isRecording = false;
  List<MocapSession> _sessions = [];
  List<MocapSession> _filteredSessions = [];
  final TextEditingController _searchController = TextEditingController();

  // Recording settings
  bool _limitRecordingDuration = false;
  int _recordingDurationMinutes = 1;
  int _recordingDurationSeconds = 0;
  bool _delayedStart = false;
  int _delayedStartSeconds = 3;
  Timer? _delayTimer;

  late TabController _tabController;

  // Timer related properties
  Stopwatch _recordingStopwatch = Stopwatch();
  Timer? _recordingTimer;
  Duration _currentDuration = Duration.zero;

  // Recording service
  late RecordingService _recordingService;
  late CameraService _cameraService;
  StreamSubscription? _statusSubscription;
  StreamSubscription? _outputSubscription;
  String _lastOutput = '';
  String _mocapOutput = '';

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);

    // Initialize recording service
    _recordingService = RecordingService();
    _setupRecordingListeners();

    // Initialize camera service
    _cameraService = CameraService();

    // Create initial demo sessions
    _initDemoSessions();

    // Add listener to search controller
    _searchController.addListener(_filterSessions);
  }

  void _setupRecordingListeners() {
    // Listen for status changes
    _statusSubscription = _recordingService.statusStream.listen((status) {
      setState(() {
        // Update recording status based on Python script status
        _isRecording = status == RecordingStatus.recording;

        // If recording has stopped, add new session
        if (status == RecordingStatus.idle && _isRecording) {
          _isRecording = false;
          // Reset the timer if it's running
          if (_recordingStopwatch.isRunning) {
            _recordingStopwatch.stop();
            _recordingTimer?.cancel();
            _recordingTimer = null;

            // Add the session with the elapsed duration
            _addNewSession(_recordingStopwatch.elapsed);
          }
        }
      });
    });

    // Listen for output from Python scripts
    _outputSubscription = _recordingService.outputStream.listen((output) {
      setState(() {
        _lastOutput = output;
      });

      debugPrint('Recording output: $output');
    });
  }

  Future<void> _initDemoSessions() async {
    final now = DateTime.now();
    final dateFormat = DateFormat('MMM d, yyyy - h:mm a');

    // Create dates for demo sessions (current time, 1 hour ago, yesterday)
    final currentTime = dateFormat.format(now);
    final oneHourAgo =
        dateFormat.format(now.subtract(const Duration(hours: 1)));
    final yesterday = dateFormat.format(now.subtract(const Duration(days: 1)));

    final demoSessions = [
      MocapSession(
          name: 'Walking Sequence',
          recordingDuration: const Duration(seconds: 32),
          date: currentTime),
      MocapSession(
          name: 'Jump Animation',
          recordingDuration: const Duration(seconds: 15),
          date: oneHourAgo),
      MocapSession(
          name: 'Run Cycle',
          recordingDuration: const Duration(seconds: 45),
          date: yesterday),
    ];

    setState(() {
      _filteredSessions = List.from(_sessions);
    });
  }

  void _filterSessions() {
    final query = _searchController.text.toLowerCase();

    setState(() {
      if (query.isEmpty) {
        _filteredSessions = List.from(_sessions);
      } else {
        _filteredSessions = _sessions
            .where((session) =>
                session.name.toLowerCase().contains(query) ||
                session.date.toLowerCase().contains(query))
            .toList();
      }
    });
  }

  @override
  void dispose() {
    _tabController.dispose();
    _searchController.dispose();
    _recordingTimer?.cancel();
    _statusSubscription?.cancel();
    _outputSubscription?.cancel();
    _recordingService.dispose();
    _cameraService.dispose();
    super.dispose();
  }

  // Start/stop recording using Python scripts
  Future<void> _toggleRecording() async {
    if (!_isRecording) {
      // Check if camera is available before starting recording
      if (!await _checkCameraAvailable()) {
        return; // Don't proceed if no camera is available
      }

      if (_delayedStart) {
        // Show countdown dialog
        int remainingSeconds = _delayedStartSeconds;

        showDialog(
            context: context,
            barrierDismissible: false,
            builder: (context) {
              return StatefulBuilder(builder: (context, setState) {
                _delayTimer =
                    Timer.periodic(const Duration(seconds: 1), (timer) {
                  setState(() {
                    remainingSeconds--;
                  });

                  if (remainingSeconds <= 0) {
                    timer.cancel();
                    Navigator.of(context).pop();
                    _startRecording();
                  }
                });

                return AlertDialog(
                  title: const Text('Recording Starting Soon'),
                  content:
                      Text('Recording will begin in $remainingSeconds seconds'),
                  actions: [
                    TextButton(
                        onPressed: () {
                          _delayTimer?.cancel();
                          Navigator.of(context).pop();
                        },
                        child: const Text('Cancel')),
                  ],
                );
              });
            });
      } else {
        // Start recording immediately
        _startRecording();
      }
    } else {
      // Stop recording
      _recordingStopwatch.stop();
      _recordingTimer?.cancel();
      _recordingTimer = null;

      // Keep the final duration
      final finalDuration = _recordingStopwatch.elapsed;

      // Stop the Python recording script
      final success = await _recordingService.stopRecording();

      if (!success) {
        // Show error message
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Failed to stop recording'),
            backgroundColor: Colors.red,
          ),
        );
      } else {
        // Add the session with the elapsed duration
        _addNewSession(finalDuration);
      }

      setState(() {
        _isRecording = false;
      });
    }
  }

  // Add a new method to start the recording
  Future<void> _startRecording() async {
    // Start recording
    _recordingStopwatch.reset();
    _recordingStopwatch.start();
    _currentDuration = Duration.zero;

    // Setup a timer to update the UI
    _recordingTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      setState(() {
        _currentDuration = _recordingStopwatch.elapsed;
      });

      // Check if we need to stop recording after a set duration
      if (_limitRecordingDuration) {
        final durationLimit = Duration(
            minutes: _recordingDurationMinutes,
            seconds: _recordingDurationSeconds);

        if (_currentDuration >= durationLimit) {
          _toggleRecording(); // Stop recording when time limit is reached
        }
      }
    });

    // Get a unique session name
    final sessionName = 'Capture_${DateTime.now().millisecondsSinceEpoch}';

    // Start the Python recording script
    final success = await _recordingService.startRecording(
      sessionName: sessionName,
      params: {
        'fps': '60',
        'quality': 'high',
        // Add any additional parameters needed by your recording script
      },
    );

    if (!success) {
      // If Python script failed to start, reset UI
      _recordingStopwatch.stop();
      _recordingTimer?.cancel();
      _recordingTimer = null;

      // Show error message
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to start recording: $_lastOutput'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  // Format duration as mm:ss
  String get formattedDuration {
    return '${_currentDuration.inMinutes.toString().padLeft(2, '0')}:${(_currentDuration.inSeconds % 60).toString().padLeft(2, '0')}';
  }

  Future<void> _addNewSession([Duration? duration]) async {
    final newSession = MocapSession(
        name: 'New Capture ${_sessions.length + 1}',
        recordingDuration: duration ?? const Duration(seconds: 10 + (50 % 50)),
        date: _getCurrentFormattedDate());

    await newSession.createSessionFolder();

    setState(() {
      _sessions.insert(0, newSession);
      _filterSessions(); // Re-apply any active filters
    });
  }

  Future<void> _deleteSession(MocapSession session) async {
    final bool deleted = await session.deleteSession();

    if (deleted) {
      setState(() {
        _sessions.remove(session);
        _filterSessions(); // Re-apply any active filters
      });
    }
  }

  // Process a recording using the Python processing script
  Future<void> _processRecording(MocapSession session) async {
    try {
      // Show processing indicator
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Processing recording...'),
          duration: Duration(seconds: 1),
        ),
      );

      // Call Python processing script
      final success = await _recordingService.processRecording(
        sessionName: session.name,
        outputFormat: 'fbx', // Change as needed
      );

      if (success) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Processing completed successfully'),
            backgroundColor: Colors.green,
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Processing failed: $_lastOutput'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error processing recording: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  Future<void> _renameSession(MocapSession session) async {
    final TextEditingController nameController =
        TextEditingController(text: session.name);

    return showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Rename Session'),
          content: TextField(
            controller: nameController,
            decoration: const InputDecoration(
              labelText: 'Session Name',
            ),
            autofocus: true,
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
            TextButton(
              onPressed: () async {
                final newName = nameController.text.trim();
                if (newName.isNotEmpty && newName != session.name) {
                  final renamed = await session.renameSession(newName);
                  if (renamed) {
                    setState(() {
                      // Session name updated in the object, just trigger a UI refresh
                      _filterSessions();
                    });
                  }
                }
                Navigator.pop(context);
              },
              child: const Text('Rename'),
            ),
          ],
        );
      },
    );
  }

  void _viewSessionDetails(MocapSession session) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) {
        return DraggableScrollableSheet(
          initialChildSize: 0.7,
          minChildSize: 0.5,
          maxChildSize: 0.9,
          expand: false,
          builder: (context, scrollController) {
            return Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Header with drag handle
                  Center(
                    child: Container(
                      width: 40,
                      height: 4,
                      margin: const EdgeInsets.only(bottom: 20),
                      decoration: BoxDecoration(
                        color: Colors.grey.shade600,
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                  ),

                  // Session title
                  Text(
                    session.name,
                    style: const TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                    ),
                  ),

                  const SizedBox(height: 16),

                  // Session details
                  Row(
                    children: [
                      Icon(Icons.timer, size: 16, color: Colors.grey.shade400),
                      const SizedBox(width: 8),
                      Text(
                        'Duration: ${session.formattedDuration}',
                        style: TextStyle(color: Colors.grey.shade300),
                      ),
                    ],
                  ),

                  const SizedBox(height: 8),

                  Row(
                    children: [
                      Icon(Icons.calendar_today,
                          size: 16, color: Colors.grey.shade400),
                      const SizedBox(width: 8),
                      Text(
                        'Captured: ${session.date}',
                        style: TextStyle(color: Colors.grey.shade300),
                      ),
                    ],
                  ),

                  const SizedBox(height: 8),

                  Row(
                    children: [
                      Icon(Icons.folder, size: 16, color: Colors.grey.shade400),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Path: ${session.folderPath ?? "Not saved"}',
                          style: TextStyle(color: Colors.grey.shade300),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: 24),

                  // Files in session
                  const Text(
                    'Session Files',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),

                  const SizedBox(height: 16),

                  // PKL file
                  _buildFileItem(
                    title: '${session.name}.pkl',
                    icon: Icons.data_object,
                    exists: session.hasPklFile,
                    fileType: 'Motion Data',
                  ),

                  const SizedBox(height: 12),

                  // Raw video file
                  _buildFileItem(
                    title: '${session.name}.mp4',
                    icon: Icons.video_file,
                    exists: session.hasRawVideo,
                    fileType: 'Raw Video',
                  ),

                  const Spacer(),

                  // Action buttons
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: [
                      OutlinedButton.icon(
                        onPressed: () {
                          Navigator.pop(context);
                          _renameSession(session);
                        },
                        icon: const Icon(Icons.edit),
                        label: const Text('Rename'),
                      ),
                      ElevatedButton.icon(
                        onPressed: () {
                          Navigator.pop(context);
                          _processRecording(session);
                        },
                        icon: const Icon(Icons.upload),
                        label: const Text('Export'),
                        style: ElevatedButton.styleFrom(
                          backgroundColor:
                              Theme.of(context).colorScheme.primary,
                        ),
                      ),
                      OutlinedButton.icon(
                        onPressed: () {
                          Navigator.pop(context);
                          _confirmDeleteSession(session);
                        },
                        icon: const Icon(Icons.delete, color: Colors.red),
                        label: const Text('Delete',
                            style: TextStyle(color: Colors.red)),
                      ),
                    ],
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  // Helper method for building file item in session details
  Widget _buildFileItem({
    required String title,
    required IconData icon,
    required bool exists,
    required String fileType,
  }) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.background,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: exists
                  ? Theme.of(context).colorScheme.primary.withOpacity(0.2)
                  : Colors.grey.shade800,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              icon,
              color:
                  exists ? Theme.of(context).colorScheme.primary : Colors.grey,
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                Text(
                  fileType,
                  style: TextStyle(
                    fontSize: 12,
                    color: Colors.grey.shade400,
                  ),
                ),
              ],
            ),
          ),
          exists
              ? Icon(Icons.check_circle, color: Colors.green.shade400, size: 20)
              : Icon(Icons.error_outline,
                  color: Colors.grey.shade600, size: 20),
        ],
      ),
    );
  }

  // Confirmation dialog for deleting a session
  Future<void> _confirmDeleteSession(MocapSession session) async {
    return showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Delete Session'),
          content: Text(
              'Are you sure you want to delete "${session.name}"? This action cannot be undone.'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
            TextButton(
              onPressed: () {
                Navigator.pop(context);
                _deleteSession(session);
              },
              child: const Text('Delete', style: TextStyle(color: Colors.red)),
            ),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.background,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.surface,
        centerTitle: true,
        title: Text(widget.title),
        actions: [
          IconButton(
            icon: const Icon(Icons.science),
            tooltip: 'Run Mocap Script',
            onPressed: () async {
              await _runMocapScript();
              showDialog(
                context: context,
                builder: (context) => AlertDialog(
                  title: const Text('Mocap Script Output'),
                  content: SingleChildScrollView(
                    child: Text(_mocapOutput),
                  ),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.of(context).pop(),
                      child: const Text('Close'),
                    ),
                  ],
                ),
              );
            },
          ),
          // Profile menu
          Padding(
            padding: const EdgeInsets.only(right: 8.0),
            child: Row(
              children: [
                Text(
                  _getGreeting() + ", Alex",
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(width: 8),
                CircleAvatar(
                  radius: 18,
                  backgroundColor:
                      Theme.of(context).colorScheme.primary.withOpacity(0.2),
                  child: const Icon(
                    Icons.person,
                    size: 22,
                    color: Colors.white,
                  ),
                ),
                PopupMenuButton(
                  icon: const Icon(Icons.arrow_drop_down),
                  itemBuilder: (context) => [
                    const PopupMenuItem(
                      value: 'profile',
                      child: Row(
                        children: [
                          Icon(Icons.account_circle, size: 18),
                          SizedBox(width: 8),
                          Text('My Profile'),
                        ],
                      ),
                    ),
                    const PopupMenuItem(
                      value: 'settings',
                      child: Row(
                        children: [
                          Icon(Icons.settings, size: 18),
                          SizedBox(width: 8),
                          Text('Settings'),
                        ],
                      ),
                    ),
                    const PopupMenuItem(
                      value: 'help',
                      child: Row(
                        children: [
                          Icon(Icons.help_outline, size: 18),
                          SizedBox(width: 8),
                          Text('Help & Support'),
                        ],
                      ),
                    ),
                    const PopupMenuItem(
                      value: 'logout',
                      child: Row(
                        children: [
                          Icon(Icons.logout, size: 18),
                          SizedBox(width: 8),
                          Text('Logout'),
                        ],
                      ),
                    ),
                  ],
                  onSelected: (value) {
                    if (value == 'settings') {
                      _showSettingsModal(context);
                    }
                  },
                ),
              ],
            ),
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(icon: Icon(Icons.camera_alt), text: 'Capture'),
            Tab(icon: Icon(Icons.list), text: 'Sessions'),
          ],
        ),
      ),
      body: SafeArea(
        child: TabBarView(
          controller: _tabController,
          children: [
            // Capture Tab
            ScrollConfiguration(
              behavior: ScrollConfiguration.of(context).copyWith(
                physics:
                    const ClampingScrollPhysics(), // Prevents overscroll glow
              ),
              child: SingleChildScrollView(
                padding: EdgeInsets.zero,
                child: Column(
                  children: [
                    // Camera/Skeleton container
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                      child: LayoutBuilder(
                        builder: (context, constraints) {
                          // Get screen height and width for calculations
                          final screenHeight =
                              MediaQuery.of(context).size.height;
                          final screenWidth = MediaQuery.of(context).size.width;
                          final devicePixelRatio =
                              MediaQuery.of(context).devicePixelRatio;

                          // Determine if we're on a narrow screen (like mobile portrait)
                          final isNarrow = constraints.maxWidth < 600;

                          // Calculate feed height based on screen size and device pixel ratio
                          // Adjust for different device pixel ratios (more compact on high DPI screens)
                          final heightFactor = isNarrow ? 0.22 : 0.38;
                          final adjustedHeight = screenHeight *
                              heightFactor /
                              (devicePixelRatio > 2 ? 1.1 : 1.0);

                          // Minimum and maximum heights to ensure usability
                          final feedHeight = adjustedHeight.clamp(160.0, 350.0);

                          if (isNarrow) {
                            // Stack vertically on narrow screens
                            return Column(
                              children: [
                                // Front camera
                                AspectRatio(
                                  aspectRatio: 4 / 3,
                                  child: CameraFeedView(),
                                ),
                                const SizedBox(height: 16),
                                // Side camera
                                AspectRatio(
                                  aspectRatio: 4 / 3,
                                  child: LiveView(
                                    title: 'Live View',
                                    isRecording: _isRecording,
                                  ),
                                ),
                              ],
                            );
                          } else {
                            // Side by side for wider screens
                            return SizedBox(
                              height: feedHeight,
                              child: Row(
                                children: [
                                  // Front camera
                                  Expanded(
                                    child: CameraFeedView(),
                                  ),
                                  const SizedBox(width: 16),
                                  // Side view
                                  Expanded(
                                    child: LiveView(
                                      title: 'Live View',
                                      isRecording: _isRecording,
                                    ),
                                  ),
                                ],
                              ),
                            );
                          }
                        },
                      ),
                    ),

                    // Recording indicator
                    if (_isRecording)
                      Container(
                        margin: const EdgeInsets.only(bottom: 12),
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 6),
                        decoration: BoxDecoration(
                          color: Colors.red,
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              width: 10,
                              height: 10,
                              decoration: const BoxDecoration(
                                color: Colors.white,
                                shape: BoxShape.circle,
                              ),
                            ),
                            const SizedBox(width: 6),
                            Text('RECORDING ${formattedDuration}',
                                style: const TextStyle(
                                    fontWeight: FontWeight.bold, fontSize: 13)),
                          ],
                        ),
                      ),

                    // Capture info and stats
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Capture Information',
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              fontSize: 16,
                            ),
                          ),

                          const SizedBox(height: 8),

                          // Stats grid
                          Row(
                            children: [
                              Expanded(
                                child: _buildCaptureInfoCard(
                                  title: 'FPS',
                                  value: '60',
                                  icon: Icons.speed,
                                  color: Colors.blue.shade400,
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: _buildCaptureInfoCard(
                                  title: 'Tracking',
                                  value: '34 Joints',
                                  icon: Icons.track_changes,
                                  color: Colors.green.shade400,
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: _buildCaptureInfoCard(
                                  title: 'Picture quality',
                                  value: '86%',
                                  icon: Icons.hd,
                                  color: Colors.yellow.shade400,
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: _buildCaptureInfoCard(
                                  title: 'Duration',
                                  value: _isRecording
                                      ? formattedDuration
                                      : '--:--',
                                  icon: Icons.timer,
                                  color: Colors.amber.shade400,
                                ),
                              ),
                            ],
                          ),

                          const SizedBox(height: 12),

                          // Capture controls
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                            children: [
                              ElevatedButton.icon(
                                onPressed: () {},
                                icon: const Icon(Icons.refresh, size: 18),
                                label: const Text('Reset'),
                                style: ElevatedButton.styleFrom(
                                  foregroundColor: Colors.white,
                                  backgroundColor: Colors.blueGrey.shade700,
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 12, vertical: 8),
                                ),
                              ),
                              FloatingActionButton(
                                onPressed: _toggleRecording,
                                backgroundColor: _isRecording
                                    ? Colors.red
                                    : Theme.of(context).colorScheme.primary,
                                tooltip: _isRecording
                                    ? 'Stop capturing'
                                    : 'Start capturing',
                                child: Icon(
                                    _isRecording
                                        ? Icons.stop
                                        : Icons.play_arrow,
                                    size: 24),
                              ),
                              ElevatedButton.icon(
                                onPressed: () {},
                                icon: const Icon(Icons.save, size: 18),
                                label: const Text('Save'),
                                style: ElevatedButton.styleFrom(
                                  foregroundColor: Colors.white,
                                  backgroundColor: Colors.blueGrey.shade700,
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 12, vertical: 8),
                                ),
                              ),
                            ],
                          ),

                          const SizedBox(height: 16),

                          // Recording Settings
                          Card(
                            color: Theme.of(context).colorScheme.surface,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Padding(
                              padding: const EdgeInsets.all(12.0),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Text(
                                    'Recording Settings',
                                    style: TextStyle(
                                      fontWeight: FontWeight.bold,
                                      fontSize: 16,
                                    ),
                                  ),

                                  const SizedBox(height: 12),

                                  // Recording Duration Limit
                                  Row(
                                    children: [
                                      Expanded(
                                        child: Row(
                                          children: [
                                            Switch(
                                              value: _limitRecordingDuration,
                                              onChanged: (value) {
                                                setState(() {
                                                  _limitRecordingDuration =
                                                      value;
                                                });
                                              },
                                              activeColor: Theme.of(context)
                                                  .colorScheme
                                                  .primary,
                                            ),
                                            const Text('Limit Duration'),
                                          ],
                                        ),
                                      ),
                                      if (_limitRecordingDuration) ...[
                                        DropdownButton<int>(
                                          value: _recordingDurationMinutes,
                                          items: List.generate(
                                                  10, (index) => index)
                                              .map((mins) =>
                                                  DropdownMenuItem<int>(
                                                    value: mins,
                                                    child: Text('$mins min'),
                                                  ))
                                              .toList(),
                                          onChanged: (value) {
                                            if (value != null) {
                                              setState(() {
                                                _recordingDurationMinutes =
                                                    value;
                                              });
                                            }
                                          },
                                        ),
                                        const SizedBox(width: 8),
                                        DropdownButton<int>(
                                          value: _recordingDurationSeconds,
                                          items: [0, 15, 30, 45]
                                              .map((secs) =>
                                                  DropdownMenuItem<int>(
                                                    value: secs,
                                                    child: Text('$secs sec'),
                                                  ))
                                              .toList(),
                                          onChanged: (value) {
                                            if (value != null) {
                                              setState(() {
                                                _recordingDurationSeconds =
                                                    value;
                                              });
                                            }
                                          },
                                        ),
                                      ],
                                    ],
                                  ),

                                  const SizedBox(height: 8),

                                  // Delayed Start
                                  Row(
                                    children: [
                                      Expanded(
                                        child: Row(
                                          children: [
                                            Switch(
                                              value: _delayedStart,
                                              onChanged: (value) {
                                                setState(() {
                                                  _delayedStart = value;
                                                });
                                              },
                                              activeColor: Theme.of(context)
                                                  .colorScheme
                                                  .primary,
                                            ),
                                            const Text('Delayed Start'),
                                          ],
                                        ),
                                      ),
                                      if (_delayedStart) ...[
                                        DropdownButton<int>(
                                          value: _delayedStartSeconds,
                                          items: [3, 5, 10, 15, 30]
                                              .map((secs) =>
                                                  DropdownMenuItem<int>(
                                                    value: secs,
                                                    child: Text('$secs sec'),
                                                  ))
                                              .toList(),
                                          onChanged: (value) {
                                            if (value != null) {
                                              setState(() {
                                                _delayedStartSeconds = value;
                                              });
                                            }
                                          },
                                        ),
                                      ],
                                    ],
                                  ),
                                ],
                              ),
                            ),
                          ),

                          // Add a smaller bottom padding to save space
                          const SizedBox(height: 10),
                          // Run Mocap Script button
                          Padding(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 16.0, vertical: 8.0),
                            child: ElevatedButton.icon(
                              onPressed: () async {
                                await _runMocapScript();
                                showDialog(
                                  context: context,
                                  builder: (context) => AlertDialog(
                                    title: const Text('Mocap Script Output'),
                                    content: SingleChildScrollView(
                                      child: Text(_mocapOutput),
                                    ),
                                    actions: [
                                      TextButton(
                                        onPressed: () =>
                                            Navigator.of(context).pop(),
                                        child: const Text('Close'),
                                      ),
                                    ],
                                  ),
                                );
                              },
                              icon: const Icon(Icons.science),
                              label: const Text('Run Mocap Script'),
                              style: ElevatedButton.styleFrom(
                                backgroundColor:
                                    Theme.of(context).colorScheme.primary,
                                foregroundColor: Colors.white,
                              ),
                            ),
                          ),
                          // Record Video button
                          Padding(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 16.0, vertical: 8.0),
                            child: ElevatedButton.icon(
                              onPressed: _recordVideo,
                              icon: const Icon(Icons.videocam),
                              label: const Text('Record video'),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // Sessions Tab
            Padding(
              padding: const EdgeInsets.only(top: 8.0),
              child: Column(
                children: [
                  // Search and filter
                  Padding(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 16.0, vertical: 8.0),
                    child: TextField(
                      controller: _searchController,
                      decoration: InputDecoration(
                        hintText: 'Search sessions',
                        prefixIcon: const Icon(Icons.search),
                        suffixIcon: _searchController.text.isNotEmpty
                            ? IconButton(
                                icon: const Icon(Icons.clear),
                                onPressed: () {
                                  _searchController.clear();
                                },
                              )
                            : null,
                        filled: true,
                        fillColor: Theme.of(context).colorScheme.surface,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: BorderSide.none,
                        ),
                      ),
                    ),
                  ),

                  // Sessions list
                  Expanded(
                    child: _filteredSessions.isEmpty
                        ? Center(
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(Icons.search_off,
                                    size: 64, color: Colors.grey.shade700),
                                const SizedBox(height: 16),
                                Text(
                                  _sessions.isEmpty
                                      ? "No sessions available"
                                      : "No sessions match your search",
                                  style: TextStyle(color: Colors.grey.shade500),
                                ),
                              ],
                            ),
                          )
                        : ListView.builder(
                            itemCount: _filteredSessions.length,
                            itemBuilder: (context, index) {
                              final session = _filteredSessions[index];
                              return Card(
                                margin: const EdgeInsets.symmetric(
                                    horizontal: 16, vertical: 6),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                color: Theme.of(context).colorScheme.surface,
                                elevation: 0,
                                child: ListTile(
                                  contentPadding: const EdgeInsets.symmetric(
                                      horizontal: 16, vertical: 8),
                                  leading: Container(
                                    width: 50,
                                    height: 50,
                                    decoration: BoxDecoration(
                                      color: Theme.of(context)
                                          .colorScheme
                                          .primary
                                          .withOpacity(0.2),
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    child: const Icon(Icons.motion_photos_on,
                                        color: Colors.white),
                                  ),
                                  title: Text(
                                    session.name,
                                    style: const TextStyle(
                                        fontWeight: FontWeight.bold),
                                  ),
                                  subtitle: Padding(
                                    padding: const EdgeInsets.only(top: 4.0),
                                    child: Row(
                                      children: [
                                        Icon(Icons.timer,
                                            size: 14,
                                            color: Colors.grey.shade400),
                                        const SizedBox(width: 4),
                                        Text(session.formattedDuration,
                                            style: TextStyle(
                                                color: Colors.grey.shade400)),
                                        const SizedBox(width: 16),
                                        Icon(Icons.calendar_today,
                                            size: 14,
                                            color: Colors.grey.shade400),
                                        const SizedBox(width: 4),
                                        Text(session.date,
                                            style: TextStyle(
                                                color: Colors.grey.shade400)),
                                      ],
                                    ),
                                  ),
                                  trailing: PopupMenuButton(
                                    icon: const Icon(Icons.more_vert),
                                    onSelected: (value) {
                                      switch (value) {
                                        case 'view':
                                          _viewSessionDetails(session);
                                          break;
                                        case 'rename':
                                          _renameSession(session);
                                          break;
                                        case 'export':
                                          _processRecording(session);
                                          break;
                                        case 'delete':
                                          _confirmDeleteSession(session);
                                          break;
                                      }
                                    },
                                    itemBuilder: (context) => [
                                      const PopupMenuItem(
                                        value: 'view',
                                        child: Row(
                                          children: [
                                            Icon(Icons.info_outline, size: 18),
                                            SizedBox(width: 8),
                                            Text('View Details'),
                                          ],
                                        ),
                                      ),
                                      const PopupMenuItem(
                                        value: 'rename',
                                        child: Row(
                                          children: [
                                            Icon(Icons.edit, size: 18),
                                            SizedBox(width: 8),
                                            Text('Rename'),
                                          ],
                                        ),
                                      ),
                                      const PopupMenuItem(
                                        value: 'export',
                                        child: Row(
                                          children: [
                                            Icon(Icons.upload, size: 18),
                                            SizedBox(width: 8),
                                            Text('Export'),
                                          ],
                                        ),
                                      ),
                                      const PopupMenuItem(
                                        value: 'delete',
                                        child: Row(
                                          children: [
                                            Icon(Icons.delete_outline,
                                                size: 18, color: Colors.red),
                                            SizedBox(width: 8),
                                            Text('Delete',
                                                style: TextStyle(
                                                    color: Colors.red)),
                                          ],
                                        ),
                                      ),
                                    ],
                                  ),
                                  onTap: () => _viewSessionDetails(session),
                                ),
                              );
                            },
                          ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
      floatingActionButton: _tabController.index == 1
          ? FloatingActionButton(
              onPressed: _addNewSession,
              tooltip: 'Import session',
              child: const Icon(Icons.add),
            )
          : null,
    );
  }

  // Builds a capture statistic item with progress indicator
  Widget _buildCaptureStat(String label, double value, Color color,
      {IconData? icon}) {
    return Row(
      children: [
        if (icon != null) ...[
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 6),
        ],
        Text(label,
            style: const TextStyle(fontWeight: FontWeight.w500, fontSize: 13)),
        const SizedBox(width: 8),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: value,
              backgroundColor: Colors.grey.shade800,
              color: color,
              minHeight: 6,
            ),
          ),
        ),
        const SizedBox(width: 6),
        Text(
          '${(value * 100).toInt()}%',
          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
        ),
      ],
    );
  }

  // Settings modal
  void _showSettingsModal(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) {
        return DraggableScrollableSheet(
          initialChildSize: 0.7,
          minChildSize: 0.5,
          maxChildSize: 0.9,
          expand: false,
          builder: (context, scrollController) {
            return ListView(
              controller: scrollController,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
              children: [
                // Handle
                Center(
                  child: Container(
                    width: 40,
                    height: 4,
                    margin: const EdgeInsets.only(bottom: 20),
                    decoration: BoxDecoration(
                      color: Colors.grey.shade600,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                ),

                // Title
                const Text(
                  'Settings',
                  style: TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                  ),
                  textAlign: TextAlign.center,
                ),

                const SizedBox(height: 24),

                // Categories
                ..._buildSettingsCategory('Capture Settings', [
                  _buildSettingsSwitch('High Quality Capture',
                      'Increased data points and precision', true),
                  _buildSettingsTile('Capture Rate', '60 fps'),
                  _buildSettingsTile('Skeleton Model', 'Full Body (34 joints)'),
                ]),

                ..._buildSettingsCategory('Export Settings', [
                  _buildSettingsTile('Export Format', 'FBX, BVH, CSV'),
                  _buildSettingsSwitch('Auto-Export',
                      'Automatically export after capture', false),
                  _buildSettingsTile(
                      'Export Location', '/downloads/axis_mocap'),
                ]),

                ..._buildSettingsCategory('Device Settings', [
                  _buildSettingsTile('Connected Device', 'Axis Pico 3 Pro'),
                  _buildSettingsTile('Firmware Version', 'v2.1.4'),
                  _buildSettingsTile('Calibrate Sensors', ''),
                ]),

                ..._buildSettingsCategory('System', [
                  _buildSettingsTile(
                    'Clear All Data',
                    'Remove all motion capture data',
                    icon: Icons.delete_outline,
                    iconColor: Colors.red,
                    onTap: () => _confirmClearAllData(context),
                  ),
                  _buildSettingsTile('About', 'Version 1.0.0'),
                ]),
              ],
            );
          },
        );
      },
    );
  }

  // Builds a settings category with title and items
  List<Widget> _buildSettingsCategory(String title, List<Widget> items) {
    return [
      Text(
        title,
        style: const TextStyle(
            fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white70),
      ),
      const SizedBox(height: 12),
      ...items,
      const Divider(height: 32),
    ];
  }

  // Builds a settings switch item
  Widget _buildSettingsSwitch(String title, String subtitle, bool value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8.0),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(fontSize: 16)),
                if (subtitle.isNotEmpty)
                  Text(
                    subtitle,
                    style: TextStyle(
                      fontSize: 14,
                      color: Colors.grey.shade400,
                    ),
                  ),
              ],
            ),
          ),
          Switch(
            value: value,
            onChanged: (newValue) {},
            activeColor: Theme.of(context).colorScheme.primary,
          ),
        ],
      ),
    );
  }

  // Builds a settings tile item
  Widget _buildSettingsTile(String title, String subtitle,
      {IconData? icon, Color? iconColor, VoidCallback? onTap}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12.0),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: const TextStyle(fontSize: 16)),
                  if (subtitle.isNotEmpty)
                    Text(
                      subtitle,
                      style: TextStyle(
                        fontSize: 14,
                        color: Colors.grey.shade400,
                      ),
                    ),
                ],
              ),
            ),
            if (icon != null)
              Icon(icon, color: iconColor ?? Colors.grey)
            else
              const Icon(Icons.chevron_right, color: Colors.grey),
          ],
        ),
      ),
    );
  }

  // Build a capture info card
  Widget _buildCaptureInfoCard({
    required String title,
    required String value,
    required IconData icon,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 14, color: color),
              const SizedBox(width: 4),
              Text(
                title,
                style: TextStyle(
                  fontSize: 11,
                  color: Colors.grey.shade400,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            value,
            style: const TextStyle(
              fontWeight: FontWeight.bold,
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }

  // Function to handle clearing all data
  Future<void> _clearAllData() async {
    try {
      // Clear all session files
      for (var session in _sessions) {
        await session.deleteSession();
      }

      // Clear in-memory sessions list
      setState(() {
        _sessions.clear();
        _filteredSessions.clear();
      });

      // Close settings dialog
      Navigator.pop(context);

      // Switch to capture tab
      _tabController.animateTo(0);

      // Show success message
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Data Cleared'),
          backgroundColor: Colors.green,
          duration: Duration(seconds: 2),
        ),
      );
    } catch (e) {
      // Show error message
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error clearing data: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  // Function to confirm deletion
  void _confirmClearAllData(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Clear All Data'),
        content: const Text(
          'This will permanently delete all motion capture sessions and their files. This action cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(context); // Close the dialog
              _clearAllData();
            },
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('Delete All'),
          ),
        ],
      ),
    );
  }

  // Check if camera is available and show alert if not
  Future<bool> _checkCameraAvailable() async {
    if (_cameraService.cameraType == CameraType.none) {
      await showDialog(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Camera Not Found'),
          content: const Text(
              'Please check your camera connection. Recording requires a connected camera.'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('OK'),
            ),
            TextButton(
              onPressed: () async {
                Navigator.pop(context);
                // Try to detect camera again
                final cameraType = await _cameraService.detectCamera();
                if (cameraType == CameraType.none) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text(
                          'No camera detected. Please connect a camera and try again.'),
                      backgroundColor: Colors.red,
                    ),
                  );
                }
              },
              child: const Text('Retry'),
            ),
          ],
        ),
      );
      return false;
    }
    return true;
  }

  // Get appropriate greeting based on time of day
  String _getGreeting() {
    final hour = DateTime.now().hour;
    if (hour < 12) {
      return "Good morning";
    } else if (hour < 17) {
      return "Good afternoon";
    } else {
      return "Good evening";
    }
  }

  // Format current date and time for session timestamps
  String _getCurrentFormattedDate() {
    final now = DateTime.now();
    final formatter = DateFormat('MMM d, yyyy - h:mm a');
    return formatter.format(now);
  }

  // Run the mocap.py Python script
  Future<void> _runMocapScript() async {
    setState(() {
      _mocapOutput = 'Running mocap script...';
    });
    try {
      final scriptPath =
          path.join(Directory.current.path, 'lib/Backend/mocap.py');
      final inputPath =
          path.join(Directory.current.path, 'lib/Backend/Video.mp4');
      final result =
          await Process.run('python3', [scriptPath, '--input', inputPath]);
      String output = result.stdout.toString().trim();
      if (output.isEmpty && result.stderr.toString().isNotEmpty) {
        output = 'Error: ${result.stderr}';
      }
      setState(() {
        _mocapOutput = output;
      });
    } catch (e) {
      setState(() {
        _mocapOutput = 'Error: $e';
      });
    }
  }

  Future<void> _recordVideo() async {
    try {
      // Start the rpicam-vid command without awaiting
      final processFuture = Process.run(
        'rpicam-vid',
        ['-t', '10s', '-o', 'test.mp4'],
        runInShell: true,
      );

      // Notify that the command has been executed
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Command executed')),
      );

      // Schedule a notification for when the command is expected to finish
      Timer(const Duration(seconds: 11), () {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Command finished running')),
        );
      });

      // Log outputs when the process completes
      processFuture.then((result) {
        debugPrint('rpicam-vid stdout: ${result.stdout}');
        debugPrint('rpicam-vid stderr: ${result.stderr}');
      }).catchError((e) {
        debugPrint('Error running rpicam-vid: $e');
      });
    } catch (e) {
      debugPrint('Error starting rpicam-vid: $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: $e')),
      );
    }
  }
}

// Camera feed widget
class CameraFeedView extends StatefulWidget {
  const CameraFeedView({Key? key}) : super(key: key);

  @override
  State<CameraFeedView> createState() => _CameraFeedViewState();
}

class _CameraFeedViewState extends State<CameraFeedView> {
  final CameraService _cameraService = CameraService();
  Stream<Image>? _cameraStream;
  bool _isConnecting = true;
  String _errorMessage = '';
  int _reconnectAttempts = 0;
  final int _maxReconnectAttempts = 3;
  Timer? _reconnectTimer;
  bool _isRecording = false;
  String? _lastRecordingPath;
  String? _lastProcessedFilePath;

  @override
  void initState() {
    super.initState();
    _initializeCamera();
  }

  @override
  void dispose() {
    _reconnectTimer?.cancel();
    super.dispose();
  }

  void _initializeCamera() async {
    setState(() {
      _isConnecting = true;
      _errorMessage = '';
    });
    try {
      _cameraStream = await _cameraService.startCameraStream();
      if (_cameraStream != null) {
        _reconnectAttempts = 0;

        setState(() {
          _isConnecting = false;
        });
      } else {
        throw Exception("Failed to initialize camera");
      }
    } catch (e) {
      setState(() {
        _isConnecting = false;
        _errorMessage = 'Failed to initialize camera: $e';
      });
    }
  }

  void _toggleRecording() async {
    if (_isRecording) {
      // Stop recording
      setState(() {
        _isRecording = false;
      });

      // TODO: Implement stopRecording in CameraService
      // final recordingInfo = await _cameraService.stopRecording();
      // if (recordingInfo != null) {
      //   setState(() {
      //     _lastRecordingPath = recordingInfo.videoPath;
      //     _lastProcessedFilePath = recordingInfo.processedDataPath;
      //   });
      // }
    } else {
      // Start recording
      setState(() {
        _isRecording = true;
      });

      // TODO: Implement startRecording in CameraService
      // await _cameraService.startRecording();
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isConnecting) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_errorMessage.isNotEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(_errorMessage, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _initializeCamera,
              child: const Text('Retry'),
            ),
          ],
        ),
      );
    }

    return Column(
      children: [
        // Camera feed - takes most of the space
        Expanded(
          child: Container(
            decoration: BoxDecoration(
              border: Border.all(
                color: _isRecording ? Colors.red : Colors.grey.shade800,
                width: 1,
              ),
              borderRadius: BorderRadius.circular(8),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(7),
              child: StreamBuilder<Image>(
                stream: _cameraStream,
                builder: (context, snapshot) {
                  if (snapshot.hasError) {
                    return Center(child: Text('Error: ${snapshot.error}'));
                  }

                  if (!snapshot.hasData) {
                    return const Center(child: CircularProgressIndicator());
                  }

                  // Display the image widget directly
                  return snapshot.data!;
                },
              ),
            ),
          ),
        ),

        // Controls
        Padding(
          padding: const EdgeInsets.only(top: 16.0, bottom: 16.0),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              // Record Button
              ElevatedButton.icon(
                onPressed: _toggleRecording,
                icon:
                    Icon(_isRecording ? Icons.stop : Icons.fiber_manual_record),
                label: Text(_isRecording ? 'Stop' : 'Record'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: _isRecording ? Colors.red : Colors.green,
                  foregroundColor: Colors.white,
                ),
              ),

              // Retry Button
              ElevatedButton.icon(
                onPressed: _initializeCamera,
                icon: const Icon(Icons.refresh),
                label: const Text('Retry'),
              ),
            ],
          ),
        ),

        // Recording Info
        if (_lastRecordingPath != null)
          Padding(
            padding: const EdgeInsets.only(top: 8.0, bottom: 4.0),
            child: Text(
              'Last Recording: ${path.basename(_lastRecordingPath!)}',
              style: const TextStyle(fontSize: 12),
            ),
          ),

        if (_lastProcessedFilePath != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 8.0),
            child: Text(
              'Processed Data: ${path.basename(_lastProcessedFilePath!)}',
              style: const TextStyle(fontSize: 12),
            ),
          ),
      ],
    );
  }
}

// Live view (renamed from SkeletonView)
class LiveView extends StatelessWidget {
  final String title;
  final bool isRecording;

  const LiveView({
    Key? key,
    required this.title,
    this.isRecording = false,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.black54,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: isRecording ? Colors.redAccent : Colors.grey.shade800,
          width: 1,
        ),
      ),
      child: Column(
        children: [
          // View title
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8.0),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.primary.withOpacity(0.2),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Text(
                title,
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 12,
                ),
              ),
            ),
          ),

          // Live view content
          Expanded(
            child: Container(
              margin: const EdgeInsets.all(4),
              decoration: BoxDecoration(
                color: Colors.black38,
                borderRadius: BorderRadius.circular(4),
              ),
              child: FittedBox(
                fit: BoxFit.contain,
                child: SizedBox(
                  width: 300, // Base reference width
                  height: 225, // Base reference height (4:3 aspect ratio)
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      // Skeleton visualization
                      Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(Icons.person_outline,
                              size: 48, color: Colors.grey),
                          const SizedBox(height: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 2),
                            decoration: BoxDecoration(
                              color: Colors.blue.shade900.withOpacity(0.6),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: const Text(
                              "Motion Tracking",
                              style: TextStyle(fontSize: 10),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
