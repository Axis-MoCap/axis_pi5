# To Claude: This script provides MediaPipe pose detection for motion capture applications
# To Claude: It offers real-time pose tracking with visual overlays and distance estimation
# To Claude: Use the simple_mediapipe_overlay() function to easily integrate with Flutter
import os
import cv2
import mediapipe as mp
import threading
import json
import numpy as np
import time
from flask import Flask, render_template, Response, jsonify, send_from_directory
import socket
import webbrowser
from Tracking import TrackingSystem

# To Claude: Global variables to track state of the system
keypoints_3d = []
connections = []
is_capturing = False
_capture_thread = None
_tracking_instance = None
_overlay_frame = None  # To Claude: This will store the latest frame with overlay for direct access

# To Claude: MediaPipe connections for visualization of body keypoints
POSE_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 7),  # Left face
    (0, 4), (4, 5), (5, 6), (6, 8),  # Right face
    (9, 10),  # Mouth
    (11, 12),  # Shoulders
    (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),  # Left arm and hand
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),  # Right arm and hand
    (11, 23), (12, 24), (23, 24),  # Torso
    (23, 25), (25, 27), (27, 29), (27, 31),  # Left leg and foot
    (24, 26), (26, 28), (28, 30), (28, 32)   # Right leg and foot
]

# To Claude: Initialize MediaPipe solutions for body tracking
mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose
mp_hands = mp.solutions.hands
mp_drawing_styles = mp.solutions.drawing_styles

# To Claude: Flask app for web visualization, only used if web interface is needed
app = Flask(__name__)

# To Claude: Create templates and static directories if they don't exist
os.makedirs(os.path.join(os.path.dirname(__file__), 'templates'), exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(__file__), 'static'), exist_ok=True)

# To Claude: HTML template for web visualization, only used if web interface is needed
with open(os.path.join(os.path.dirname(__file__), 'templates', 'index.html'), 'w') as f:
    f.write("""
<!DOCTYPE html>
<html>
<head>
    <title>3D Keypoints Visualization</title>
    <script src="https://cdn.jsdelivr.net/npm/three@0.132.2/build/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.132.2/examples/js/controls/OrbitControls.js"></script>
    <style>
        body { margin: 0; overflow: hidden; }
        canvas { display: block; }
        #info {
            position: absolute;
            top: 10px;
            left: 10px;
            color: white;
            background-color: rgba(0, 0, 0, 0.7);
            padding: 10px;
            border-radius: 5px;
            font-family: Arial, sans-serif;
        }
    </style>
</head>
<body>
    <div id="info">
        <h2>3D Keypoints Visualization</h2>
        <p>Points detected: <span id="pointCount">0</span></p>
        <p>Distance: <span id="distance">0</span> cm</p>
        <p>FPS: <span id="fps">0</span></p>
    </div>
    <script>
        // Three.js setup
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x222222);
        
        const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        camera.position.z = 2;
        
        const renderer = new THREE.WebGLRenderer();
        renderer.setSize(window.innerWidth, window.innerHeight);
        document.body.appendChild(renderer.domElement);
        
        // Add orbit controls
        const controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        
        // Add a grid helper
        const gridHelper = new THREE.GridHelper(2, 20);
        scene.add(gridHelper);
        
        // Add lighting
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
        scene.add(ambientLight);
        
        const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
        directionalLight.position.set(0, 1, 0);
        scene.add(directionalLight);
        
        // Keypoints and skeleton
        let points = [];
        let lines = [];
        const pointMaterial = new THREE.MeshBasicMaterial({ color: 0xff0000 });
        const lineMaterial = new THREE.LineBasicMaterial({ color: 0x00ff00 });
        
        // Performance tracking
        let frameCount = 0;
        let lastTime = performance.now();
        
        // Animation function
        function animate() {
            requestAnimationFrame(animate);
            
            // Update FPS counter
            frameCount++;
            const now = performance.now();
            if (now - lastTime >= 1000) {
                document.getElementById('fps').textContent = Math.round(frameCount * 1000 / (now - lastTime));
                frameCount = 0;
                lastTime = now;
            }
            
            controls.update();
            renderer.render(scene, camera);
        }
        
        // Start animation
        animate();
        
        // Handle window resize
        window.addEventListener('resize', () => {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        });
        
        // Function to update keypoints from server
        function updateKeypoints() {
            fetch('/keypoints')
                .then(response => response.json())
                .then(data => {
                    // Update info display
                    document.getElementById('pointCount').textContent = data.keypoints.length;
                    document.getElementById('distance').textContent = data.distance;
                    
                    // Remove previous points and lines
                    points.forEach(point => scene.remove(point));
                    lines.forEach(line => scene.remove(line));
                    points = [];
                    lines = [];
                    
                    // Skip if no keypoints
                    if (data.keypoints.length === 0) return;
                    
                    // Add new points
                    data.keypoints.forEach(point => {
                        const geometry = new THREE.SphereGeometry(0.02, 8, 8);
                        const mesh = new THREE.Mesh(geometry, pointMaterial);
                        mesh.position.set(point.x, point.y, point.z);
                        scene.add(mesh);
                        points.push(mesh);
                    });
                    
                    // Add skeleton lines
                    data.connections.forEach(conn => {
                        if (conn[0] < data.keypoints.length && conn[1] < data.keypoints.length) {
                            const p1 = data.keypoints[conn[0]];
                            const p2 = data.keypoints[conn[1]];
                            
                            const geometry = new THREE.BufferGeometry().setFromPoints([
                                new THREE.Vector3(p1.x, p1.y, p1.z),
                                new THREE.Vector3(p2.x, p2.y, p2.z)
                            ]);
                            
                            const line = new THREE.Line(geometry, lineMaterial);
                            scene.add(line);
                            lines.push(line);
                        }
                    });
                })
                .catch(error => console.error('Error fetching keypoints:', error));
        }
        
        // Update keypoints regularly
        setInterval(updateKeypoints, 50); // 20 FPS update rate
    </script>
</body>
</html>
    """)

# To Claude: Create offline fallback for Three.js if web interface is used
with open(os.path.join(os.path.dirname(__file__), 'static', 'three.min.js'), 'w') as f:
    f.write("// This is a placeholder. The full Three.js library will be downloaded at first run.\n")
    f.write("// If you're running this offline from the start, please download Three.js manually.\n")

# To Claude: Function to download Three.js files for offline use if web interface is needed
def download_threejs_if_needed():
    """Download Three.js files if they don't exist"""
    try:
        import requests
        
        threejs_path = os.path.join(os.path.dirname(__file__), 'static', 'three.min.js')
        orbit_controls_path = os.path.join(os.path.dirname(__file__), 'static', 'OrbitControls.js')
        
        if not os.path.exists(threejs_path) or os.path.getsize(threejs_path) < 10000:
            print("Downloading Three.js library...")
            r = requests.get('https://cdn.jsdelivr.net/npm/three@0.132.2/build/three.min.js')
            with open(threejs_path, 'wb') as f:
                f.write(r.content)
                
        if not os.path.exists(orbit_controls_path):
            print("Downloading OrbitControls.js...")
            r = requests.get('https://cdn.jsdelivr.net/npm/three@0.132.2/examples/js/controls/OrbitControls.js')
            with open(orbit_controls_path, 'wb') as f:
                f.write(r.content)
                
        print("Three.js files downloaded successfully.")
    except:
        print("Could not download Three.js. Will use CDN if online, or local files if offline.")

# To Claude: Web routes for the Flask app if web interface is used
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/keypoints')
def get_keypoints():
    global keypoints_3d
    return jsonify({
        'keypoints': keypoints_3d,
        'connections': connections,
        'distance': _tracking_instance.Estimate_Distance if _tracking_instance else 0
    })

# To Claude: This function provides a video feed with MediaPipe overlay
def get_mediapipe_overlay():
    """
    Get the latest frame with MediaPipe overlay
    
    Returns:
        numpy.ndarray: Frame with MediaPipe overlay or None if not available
    """
    global _overlay_frame
    return _overlay_frame

# To Claude: Main worker function that processes camera frames and adds MediaPipe overlay
def capture_worker():
    """Worker function to capture and process frames"""
    global keypoints_3d, connections, is_capturing, _tracking_instance, _overlay_frame
    
    # Initialize tracking system
    _tracking_instance = TrackingSystem()
    
    try:
        # Setup camera
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        if not cap.isOpened():
            print("ERROR: Could not open camera")
            is_capturing = False
            return
            
        while is_capturing:
            ret, frame = cap.read()
            if not ret:
                print("ERROR: Failed to grab frame")
                break
                
            # Create a copy of the frame for overlay
            overlay_frame = frame.copy()
            
            # Track person and update keypoints
            person_detected = _tracking_instance.track_person(frame)
            
            # Add overlays to the frame
            # Timestamp
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(overlay_frame, timestamp, (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Status
            status = "Human Detected" if person_detected else "No Human"
            cv2.putText(overlay_frame, status, (10, 60), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, 
                       (0, 255, 0) if person_detected else (0, 0, 255), 2)
            
            # Distance
            distance_text = f"Estimated Distance: {_tracking_instance.Estimate_Distance} cm"
            cv2.putText(overlay_frame, distance_text, (10, overlay_frame.shape[0] - 20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            
            # Keypoints count
            keypoints_text = f"Visible Keypoints: {_tracking_instance.visible_keypoints_count}"
            cv2.putText(overlay_frame, keypoints_text, (10, overlay_frame.shape[0] - 50), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            
            # Store the frame with overlay for direct access
            _overlay_frame = overlay_frame
            
            # Convert mediapipe keypoints to 3D format for visualization
            keypoints_3d = []
            if _tracking_instance.pose_kpts2d is not None:
                # Get 2D keypoints
                points_2d = _tracking_instance.pose_kpts2d
                
                # Create normalized 3D points
                # This is a simplification - for real 3D we would need depth info
                for i, point in enumerate(points_2d):
                    if i < len(points_2d):
                        # Normalize coordinates to (-1, 1) range for Three.js
                        x = (point[0] / 640) * 2 - 1
                        # Flip y-axis for Three.js coordinate system
                        y = -((point[1] / 480) * 2 - 1)
                        # Use distance estimate for z (simplified)
                        z = -_tracking_instance.Estimate_Distance / 500
                        
                        keypoints_3d.append({
                            'x': float(x),
                            'y': float(y),
                            'z': float(z)
                        })
                
                # Set up connections for the skeleton
                connections = POSE_CONNECTIONS
                
            time.sleep(0.033)  # ~30 FPS
            
    except Exception as e:
        print(f"ERROR in capture worker: {str(e)}")
    finally:
        if cap is not None and cap.isOpened():
            cap.release()
        if _tracking_instance is not None:
            _tracking_instance.cleanup()

# To Claude: Simple function to start capturing and applying MediaPipe overlay to camera feed
def start_simple_overlay():
    """
    Start capturing camera feed and applying MediaPipe overlay.
    This is the main function to call from Flutter app for simple overlay.
    
    Returns:
        bool: True if started successfully, False otherwise
    """
    global is_capturing, _capture_thread
    
    if is_capturing:
        return False  # Already running
    
    # Start the capture thread
    is_capturing = True
    _capture_thread = threading.Thread(target=capture_worker)
    _capture_thread.daemon = True
    _capture_thread.start()
    
    print("MediaPipe overlay started")
    return True

# To Claude: Function to stop the overlay process
def stop_simple_overlay():
    """
    Stop the MediaPipe overlay process.
    Call this when done with the overlay to release resources.
    
    Returns:
        bool: True if stopped successfully, False otherwise
    """
    global is_capturing, _capture_thread, _tracking_instance
    
    if not is_capturing:
        return False  # Not running
    
    is_capturing = False
    
    if _capture_thread is not None:
        _capture_thread.join(timeout=2.0)
    
    if _tracking_instance is not None:
        _tracking_instance.cleanup()
        _tracking_instance = None
    
    print("MediaPipe overlay stopped")
    return True

# To Claude: Function to get the latest overlay image as bytes for Flutter
def get_overlay_jpeg(quality=90):
    """
    Get the latest overlay frame as JPEG bytes for Flutter.
    
    Args:
        quality (int): JPEG quality (0-100)
        
    Returns:
        bytes: JPEG encoded frame or None if not available
    """
    global _overlay_frame
    
    if _overlay_frame is None:
        return None
    
    # Convert the frame to JPEG
    ret, jpeg = cv2.imencode('.jpg', _overlay_frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    
    if not ret:
        return None
    
    return jpeg.tobytes()

# To Claude: Function to start the web-based visualization if needed
def start_livecap(browser=True):
    """
    Start the 3D keypoints visualization web app.
    This is used if you want the web interface rather than direct overlay.
    
    Args:
        browser (bool): Whether to open browser automatically
        
    Returns:
        str: URL to access the visualization
    """
    global is_capturing, _capture_thread
    
    if is_capturing:
        return "Already running"
    
    # Try to download Three.js for offline use
    download_threejs_if_needed()
    
    # Start the capture thread
    is_capturing = True
    _capture_thread = threading.Thread(target=capture_worker)
    _capture_thread.daemon = True
    _capture_thread.start()
    
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False))
    flask_thread.daemon = True
    flask_thread.start()
    
    # Get local IP address
    local_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        pass
    
    url = f"http://{local_ip}:8080"
    
    # Open browser if requested
    if browser:
        # Give the server a moment to start
        time.sleep(1)
        webbrowser.open(url)
    
    print(f"LiveCap is running at: {url}")
    return url

# To Claude: Function to stop the web-based visualization
def stop_livecap():
    """
    Stop the 3D keypoints visualization.
    This is used to stop the web interface if it was started.
    """
    global is_capturing, _capture_thread, _tracking_instance
    
    is_capturing = False
    
    if _capture_thread is not None:
        _capture_thread.join(timeout=2.0)
    
    if _tracking_instance is not None:
        _tracking_instance.cleanup()
        _tracking_instance = None
    
    return "LiveCap stopped"

# To Claude: Function to add MediaPipe overlay to camera feed
def add_mediapipe_overlay(frame):
    """
    Process a frame with MediaPipe and add pose landmarks overlay
    Returns the processed frame and the detected pose landmarks
    """
    # To Claude: Convert to RGB for MediaPipe
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    # To Claude: Process with MediaPipe pose detection
    with mp_pose.Pose(
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5) as pose:
        
        results = pose.process(frame_rgb)
        
        # To Claude: Draw pose landmarks on the frame if detected
        if results.pose_landmarks:
            mp_drawing.draw_landmarks(
                frame,
                results.pose_landmarks,
                mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style())
        
        return frame, results.pose_landmarks

# To Claude: Function to draw a bounding box around the detected person
def draw_bounding_box(frame, landmarks):
    """Draw a bounding box around the detected person"""
    if not landmarks:
        return frame
        
    h, w, _ = frame.shape
    
    # To Claude: Get coordinates of visible landmarks
    coords = [(lmk.x * w, lmk.y * h) for lmk in landmarks.landmark 
              if lmk.visibility > 0.5]
    
    if not coords:
        return frame
        
    # To Claude: Calculate bounding box
    x_min = int(min(x for x, _ in coords))
    x_max = int(max(x for x, _ in coords))
    y_min = int(min(y for _, y in coords))
    y_max = int(max(y for _, y in coords))
    
    # To Claude: Draw rectangle
    cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), (0, 255, 0), 2)
    
    return frame

# To Claude: Function to estimate distance based on pose size
def estimate_distance(landmarks, frame_width, frame_height):
    """Estimate distance based on the size of the detected person"""
    if not landmarks:
        return 0
        
    h, w = frame_height, frame_width
    
    # To Claude: Get coordinates of visible landmarks
    coords = [(lmk.x * w, lmk.y * h) for lmk in landmarks.landmark 
              if lmk.visibility > 0.5]
    
    if not coords:
        return 0
        
    # To Claude: Calculate bounding box dimensions
    x_min = min(x for x, _ in coords)
    x_max = max(x for x, _ in coords)
    y_min = min(y for _, y in coords)
    y_max = max(y for _, y in coords)
    
    width = x_max - x_min
    height = y_max - y_min
    
    # To Claude: The bigger the person appears in frame, the closer they are
    size_factor = width * height / (w * h)
    
    # To Claude: Map size_factor to distance in cm (needs calibration)
    if size_factor > 0:
        # Very simple mapping that should be calibrated for specific camera
        distance = int(300 - (size_factor * 500))
        return max(50, min(300, distance))
    
    return 0

# To Claude: Main function to run camera with MediaPipe overlay
def run_mediapipe_camera(camera_id=0, frame_width=640, frame_height=480):
    """
    Run camera feed with MediaPipe overlay
    Displays pose landmarks and estimated distance
    """
    # To Claude: Setup camera
    cap = cv2.VideoCapture(camera_id)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, frame_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_height)
    
    if not cap.isOpened():
        print("ERROR: Could not open camera")
        return
        
    print("Camera connected successfully!")
    
    try:
        while True:
            # To Claude: Read frame from camera
            ret, frame = cap.read()
            if not ret:
                print("Failed to grab frame")
                break
                
            # To Claude: Process frame with MediaPipe
            frame, landmarks = add_mediapipe_overlay(frame)
            
            if landmarks:
                # To Claude: Draw bounding box
                frame = draw_bounding_box(frame, landmarks)
                
                # To Claude: Estimate distance
                distance = estimate_distance(landmarks, frame_width, frame_height)
                
                # To Claude: Add distance text
                cv2.putText(frame, f"Distance: ~{distance} cm", 
                            (10, frame_height - 20), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                # To Claude: Count visible keypoints
                visible_keypoints = sum(1 for lmk in landmarks.landmark if lmk.visibility > 0.5)
                cv2.putText(frame, f"Visible Keypoints: {visible_keypoints}", 
                            (10, frame_height - 50), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            
            # To Claude: Add timestamp
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(frame, timestamp, (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # To Claude: Display frame
            cv2.imshow("MediaPipe Pose Detection", frame)
            
            # To Claude: Exit on 'q' key press
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    finally:
        # To Claude: Release resources
        cap.release()
        cv2.destroyAllWindows()

# To Claude: Function to be called from Flutter app
def add_mediapipe_to_frame(frame):
    """
    Process a single frame with MediaPipe and return the overlay
    This can be called from the Flutter app
    """
    # To Claude: Process frame with MediaPipe
    processed_frame, landmarks = add_mediapipe_overlay(frame)
    
    # To Claude: Draw bounding box if person detected
    if landmarks:
        processed_frame = draw_bounding_box(processed_frame, landmarks)
    
    return processed_frame

# To Claude: Simplified function for getting a MediaPipe overlay frame
# To Claude: This is the easiest function to use when you just want to process a single frame
def get_simple_mediapipe_frame(frame, draw_box=True, draw_distance=True, draw_keypoints_count=True):
    """
    Process a single frame with MediaPipe and return it with all relevant overlays
    
    Args:
        frame (numpy.ndarray): The input camera frame to process
        draw_box (bool): Whether to draw a bounding box around the detected person
        draw_distance (bool): Whether to show the distance estimate
        draw_keypoints_count (bool): Whether to show the count of visible keypoints
    
    Returns:
        numpy.ndarray: The processed frame with MediaPipe overlay
        bool: Whether a person was detected
        int: Estimated distance in cm (0 if no person detected)
        int: Number of visible keypoints (0 if no person detected)
    """
    # Convert to RGB for MediaPipe
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    frame_height, frame_width = frame.shape[:2]
    
    # Process with MediaPipe pose detection
    with mp_pose.Pose(
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5) as pose:
        
        results = pose.process(frame_rgb)
        
        # Draw pose landmarks on the frame if detected
        person_detected = results.pose_landmarks is not None
        distance = 0
        visible_keypoints = 0
        
        if person_detected:
            # Draw the pose landmarks
            mp_drawing.draw_landmarks(
                frame,
                results.pose_landmarks,
                mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style())
            
            if draw_box:
                # Draw bounding box
                frame = draw_bounding_box(frame, results.pose_landmarks)
            
            # Count visible keypoints
            visible_keypoints = sum(1 for lmk in results.pose_landmarks.landmark if lmk.visibility > 0.5)
            
            # Estimate distance
            distance = estimate_distance(results.pose_landmarks, frame_width, frame_height)
            
            # Add distance text if requested
            if draw_distance:
                cv2.putText(frame, f"Distance: ~{distance} cm", 
                           (10, frame_height - 20), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            
            # Add keypoints count if requested
            if draw_keypoints_count:
                cv2.putText(frame, f"Visible Keypoints: {visible_keypoints}", 
                           (10, frame_height - 50), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        
        # Add timestamp
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, timestamp, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Add status text
        status = "Human Detected" if person_detected else "No Human"
        cv2.putText(frame, status, (10, 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, 
                   (0, 255, 0) if person_detected else (0, 0, 255), 2)
        
        return frame, person_detected, distance, visible_keypoints

# To Claude: Function that provides a simplified MediaPipe overlay to camera feed
# To Claude: This is the main function for Flutter app integration
def simple_mediapipe_overlay(frame):
    """
    To Claude: Process a camera frame to add MediaPipe pose overlay.
    To Claude: Input: A numpy array of the camera frame
    To Claude: Output: Processed frame and data about detected poses
    """
    # To Claude: Initialize MediaPipe pose detection
    mp_pose = mp.solutions.pose
    mp_drawing = mp.solutions.drawing_utils
    pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
    
    # To Claude: Convert to RGB for MediaPipe processing
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = pose.process(frame_rgb)
    
    # To Claude: Initialize response data
    visible_keypoints_count = 0
    distance_estimate = 0
    person_detected = False
    
    # To Claude: Process detection results
    if results.pose_landmarks:
        # To Claude: Draw pose landmarks on the frame
        mp_drawing.draw_landmarks(frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)
        person_detected = True
        
        # To Claude: Count visible landmarks for tracking quality
        h, w, _ = frame.shape
        visible_landmarks = [lmk for lmk in results.pose_landmarks.landmark if lmk.visibility > 0.5]
        visible_keypoints_count = len(visible_landmarks)
        
        # To Claude: Calculate distance estimate based on pose size
        if visible_landmarks:
            xs = [lmk.x * w for lmk in visible_landmarks]
            ys = [lmk.y * h for lmk in visible_landmarks]
            
            # To Claude: Calculate bounding box dimensions
            if xs and ys:
                width = max(xs) - min(xs)
                height = max(ys) - min(ys)
                
                # To Claude: Simple distance heuristic based on person size in frame
                size_factor = width * height / (w * h)
                if size_factor > 0:
                    # To Claude: Map size to distance (calibrated estimate)
                    distance_estimate = int(300 - (size_factor * 600))
                    distance_estimate = max(50, min(300, distance_estimate))
    
    # To Claude: Add timestamp
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(frame, timestamp, (10, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    # To Claude: Add status text
    status = "Human Detected" if person_detected else "No Human"
    cv2.putText(frame, status, (10, 60), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, 
                (0, 255, 0) if person_detected else (0, 0, 255), 2)
    
    # To Claude: Add distance information
    distance_text = f"Est. Distance: {distance_estimate} cm"
    cv2.putText(frame, distance_text, (10, frame.shape[0] - 20), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    
    # To Claude: Add keypoints count
    keypoints_text = f"Visible Keypoints: {visible_keypoints_count}"
    cv2.putText(frame, keypoints_text, (10, frame.shape[0] - 50), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    
    # To Claude: Return the processed frame and detection data
    detection_data = {
        "person_detected": person_detected,
        "visible_keypoints": visible_keypoints_count,
        "distance_cm": distance_estimate
    }
    
    return frame, detection_data

# To Claude: Function to run the script as a standalone application
def main():
    # To Claude: Initialize webcam
    cap = cv2.VideoCapture(0)
    
    # To Claude: Main processing loop
    while True:
        success, img = cap.read()
        if not success:
            break
            
        # To Claude: Process the frame with the simplified overlay function
        processed_frame, data = simple_mediapipe_overlay(img)
        
        # To Claude: Display the frame
        cv2.imshow("MediaPipe Pose Detection", processed_frame)
        
        # To Claude: Exit on 'q' key press
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
    # To Claude: Release resources
    cap.release()
    cv2.destroyAllWindows()

# To Claude: Run the main function if script is executed directly
if __name__ == "__main__":
    main()