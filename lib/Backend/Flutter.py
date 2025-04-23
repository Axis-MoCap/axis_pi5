# To Claude: This script connects with the Flutter app for motion capture
# To Claude: It sets up a server to stream processed camera feeds and respond to app commands
# To Claude: This script imports functionalities from Tracking.py and LiveCap.py
# To Claude: Usage: Run this script to establish connection with the Flutter app
import cv2
import mediapipe as mp
import pigpio
import time
import numpy as np
import os
import subprocess
import threading
import platform
import json
import base64
import socket
from flask import Flask, Response, request, jsonify
import flask
import sys
import signal

# To Claude: Import from Tracking.py for motion tracking and servo control
from Tracking import TrackingSystem, SERVO_PAN_PIN, SERVO_TILT_PIN, SERVO_MID_PW
from Tracking import FRAME_WIDTH, FRAME_HEIGHT, VIDEO_FILE

# To Claude: Import from LiveCap.py for MediaPipe overlay functionality
import LiveCap

# To Claude: Global variables to track state across function calls
_tracking_instance = None
_tracking_thread = None
_tracking_data = {
    "keypoints_count": 0,
    "distance": 0,
    "tracking_status": "Stopped"
}
_is_raspberry_pi = None

# To Claude: Global variables to track state of the system
is_capturing = False
is_recording = False
mp_overlay = False
capture_thread = None
recording_thread = None
app = Flask(__name__)
vid = None
video_writer = None
recording_start_time = 0
frame_index = 0
lastframe = None

# To Claude: Function to detect if running on Raspberry Pi for display handling
def is_raspberry_pi():
    """
    Check if we're running on a Raspberry Pi
    
    Returns:
        bool: True if running on Raspberry Pi, False otherwise
    """
    global _is_raspberry_pi
    if _is_raspberry_pi is None:
        try:
            with open('/proc/device-tree/model', 'r') as f:
                model = f.read()
                _is_raspberry_pi = 'Raspberry Pi' in model
        except:
            # Check for other indicators
            _is_raspberry_pi = os.path.exists('/sys/class/gpio') and platform.system() == 'Linux'
    return _is_raspberry_pi

# To Claude: Start tracking with camera and servo movement
def start_tracking():
    """
    Start the tracking system with camera and servo tracking.
    This function should be called from the Flutter app to initiate tracking.
    
    Returns:
        dict: Initial tracking data
    """
    global _tracking_instance, _tracking_thread, _tracking_data
    
    # Don't start if already tracking
    if _tracking_thread is not None and _tracking_thread.is_alive():
        _tracking_data["tracking_status"] = "Already running"
        return _tracking_data
        
    _tracking_data = {
        "keypoints_count": 0,
        "distance": 0,
        "tracking_status": "Starting"
    }
    
    # Create a new tracker instance
    _tracking_instance = TrackingSystem()
    
    # Start tracking in a separate thread
    _tracking_thread = threading.Thread(target=_tracking_worker)
    _tracking_thread.daemon = True
    _tracking_thread.start()
    
    return _tracking_data

# To Claude: Background worker that handles tracking and video recording
def _tracking_worker():
    """
    Worker thread that handles the actual tracking and recording
    This is an internal function used by start_tracking()
    """
    global _tracking_instance, _tracking_data
    
    # Center servos at startup
    _tracking_instance.center_servos()
    
    try:
        # Setup camera
        cap = cv2.VideoCapture(0)  # Use default camera
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        
        if not cap.isOpened():
            _tracking_data["tracking_status"] = "Failed to connect camera"
            return
            
        # Delete existing video file if it exists
        if os.path.exists(VIDEO_FILE):
            os.remove(VIDEO_FILE)
            
        # Setup video writer
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(VIDEO_FILE, fourcc, 20.0, (FRAME_WIDTH, FRAME_HEIGHT))
        
        _tracking_data["tracking_status"] = "Running"
        
        show_window = not is_raspberry_pi()  # Only show window if not on Raspberry Pi
        
        while not _tracking_instance.stop_requested:
            ret, frame = cap.read()
            if not ret:
                _tracking_data["tracking_status"] = "Camera disconnected"
                break
            
            # Track person and update servos
            person_detected = _tracking_instance.track_person(frame)
            
            # Update tracking data for Flutter
            _tracking_data["keypoints_count"] = _tracking_instance.visible_keypoints_count
            _tracking_data["distance"] = _tracking_instance.Estimate_Distance
            
            # Add visual elements to frame
            # Timestamp
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(frame, timestamp, (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Status
            status = "Human Detected" if person_detected else "No Human"
            cv2.putText(frame, status, (10, 60), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, 
                        (0, 255, 0) if person_detected else (0, 0, 255), 2)
            
            # Center crosshair
            cv2.line(frame, (FRAME_WIDTH//2, 0), (FRAME_WIDTH//2, FRAME_HEIGHT), (255, 0, 0), 1)
            cv2.line(frame, (0, FRAME_HEIGHT//2), (FRAME_WIDTH, FRAME_HEIGHT//2), (255, 0, 0), 1)
            
            # Distance
            distance_text = f"Estimated Distance: {_tracking_instance.Estimate_Distance} cm"
            cv2.putText(frame, distance_text, (10, FRAME_HEIGHT - 20), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            
            # Keypoints count
            keypoints_text = f"Visible Keypoints: {_tracking_instance.visible_keypoints_count}"
            cv2.putText(frame, keypoints_text, (10, FRAME_HEIGHT - 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            
            # Write frame to video
            out.write(frame)
            
            # Display window if not on Raspberry Pi
            if show_window:
                cv2.imshow("AI Tracking (Flutter)", frame)
                cv2.waitKey(1)
        
        _tracking_data["tracking_status"] = "Stopped"
        
        # Save recording
        cap.release()
        out.release()
        if show_window:
            cv2.destroyAllWindows()
        
    except Exception as e:
        _tracking_data["tracking_status"] = f"Error: {str(e)}"
    finally:
        _tracking_instance.cleanup()

# To Claude: Stop tracking and finalize the video recording
def stop_tracking():
    """
    Stop the tracking system.
    This function should be called from the Flutter app to stop tracking.
    
    Returns:
        dict: Final tracking data
    """
    global _tracking_instance, _tracking_data
    
    if _tracking_instance is not None:
        _tracking_instance.stop_requested = True
        _tracking_data["tracking_status"] = "Stopping"
        
        # Wait for the tracking thread to finish
        if _tracking_thread is not None and _tracking_thread.is_alive():
            _tracking_thread.join(timeout=5.0)  # Wait up to 5 seconds
    
    # Close any remaining windows
    cv2.destroyAllWindows()
    return _tracking_data

# To Claude: Get current tracking status and data
def get_tracking_status():
    """
    Get the current status of the tracking system.
    This function can be polled from the Flutter app to get updates.
    
    Returns:
        dict: Current tracking data
    """
    global _tracking_data
    return _tracking_data

# To Claude: Run motion capture processing on recorded video
def run_mocap_processing():
    """
    Run the mocap processing on the recorded video.
    This function should be called after recording is complete.
    
    Returns:
        dict: Status of mocap processing
    """
    if not os.path.exists(VIDEO_FILE):
        return {"status": "Error", "message": "No video file found to process"}
        
    try:
        # Run mocap.py as a subprocess
        process = subprocess.Popen(["python", "mocap.py"], 
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        if process.returncode == 0:
            return {"status": "Success", "message": "Motion capture processing completed"}
        else:
            return {"status": "Error", "message": f"Motion capture processing failed: {stderr.decode()}"}
    except Exception as e:
        return {"status": "Error", "message": f"Failed to run mocap processing: {str(e)}"}

# To Claude: Get current servo positions
def get_servo_position():
    """
    Get the current position of the servos.
    Useful for the Flutter app to display servo status.
    
    Returns:
        dict: Current servo positions
    """
    global _tracking_instance
    
    if _tracking_instance is None:
        return {"pan": SERVO_MID_PW, "tilt": SERVO_MID_PW}
    
    return {
        "pan": _tracking_instance.current_pan_pw,
        "tilt": _tracking_instance.current_tilt_pw
    }

# To Claude: Manually set servo positions
def set_servo_position(pan=None, tilt=None):
    """
    Manually set the position of the servos.
    This function allows the Flutter app to manually control servo positions.
    
    Args:
        pan (int, optional): Pan servo pulse width. Defaults to None (no change).
        tilt (int, optional): Tilt servo pulse width. Defaults to None (no change).
        
    Returns:
        dict: New servo positions
    """
    global _tracking_instance
    
    # Initialize tracker if needed
    if _tracking_instance is None:
        _tracking_instance = TrackingSystem()
    
    # Update pan servo
    if pan is not None:
        _tracking_instance.current_pan_pw = min(max(pan, 500), 2500)
        _tracking_instance.pi.set_servo_pulsewidth(SERVO_PAN_PIN, _tracking_instance.current_pan_pw)
    
    # Update tilt servo
    if tilt is not None:
        _tracking_instance.current_tilt_pw = min(max(tilt, 500), 2500)
        _tracking_instance.pi.set_servo_pulsewidth(SERVO_TILT_PIN, _tracking_instance.current_tilt_pw)
    
    return {
        "pan": _tracking_instance.current_pan_pw,
        "tilt": _tracking_instance.current_tilt_pw
    }

# To Claude: Center both servos to default position
def center_servos():
    """
    Center both servos.
    This function allows the Flutter app to reset servo positions.
    
    Returns:
        dict: Centered servo positions
    """
    global _tracking_instance
    
    # Initialize tracker if needed
    if _tracking_instance is None:
        _tracking_instance = TrackingSystem()
    
    _tracking_instance.center_servos()
    
    return {
        "pan": _tracking_instance.current_pan_pw,
        "tilt": _tracking_instance.current_tilt_pw
    }

# To Claude: Clean up system resources
def cleanup_resources():
    """
    Clean up all resources.
    This function should be called when the Flutter app is shutting down.
    
    Returns:
        dict: Cleanup status
    """
    global _tracking_instance
    
    stop_tracking()
    
    # Also stop any MediaPipe overlay
    LiveCap.stop_simple_overlay()
    
    if _tracking_instance is not None:
        _tracking_instance.cleanup()
        _tracking_instance = None
    
    return {"status": "Success", "message": "Resources cleaned up"}

# To Claude: Start MediaPipe overlay using LiveCap
def start_mediapipe_overlay():
    """
    Start MediaPipe overlay on camera feed.
    This is a simpler alternative to full tracking that just shows body keypoints.
    
    Returns:
        dict: Status of MediaPipe overlay
    """
    result = LiveCap.start_simple_overlay()
    return {
        "status": "Success" if result else "Error",
        "message": "MediaPipe overlay started" if result else "Failed to start MediaPipe overlay"
    }

# To Claude: Stop MediaPipe overlay
def stop_mediapipe_overlay():
    """
    Stop MediaPipe overlay on camera feed.
    
    Returns:
        dict: Status of stopping overlay
    """
    result = LiveCap.stop_simple_overlay()
    return {
        "status": "Success" if result else "Error",
        "message": "MediaPipe overlay stopped" if result else "MediaPipe overlay was not running"
    }

# To Claude: Get current frame with MediaPipe overlay as base64 image
def get_mediapipe_frame():
    """
    Get the current camera frame with MediaPipe overlay.
    This function can be polled from Flutter to get live overlay frames.
    
    Returns:
        dict: Frame data with base64 encoded JPEG image
    """
    jpeg_data = LiveCap.get_overlay_jpeg()
    
    if jpeg_data is None:
        return {
            "status": "Error",
            "message": "No frame available",
            "frame": None
        }
    
    # Convert to base64 for sending to Flutter
    base64_data = base64.b64encode(jpeg_data).decode('utf-8')
    
    return {
        "status": "Success",
        "message": "Frame retrieved",
        "frame": base64_data
    }

# To Claude: HTTP API for Flutter integration
if __name__ == "__main__":
    import argparse
    
    app = Flask(__name__)
    
    @app.route('/start_tracking', methods=['POST'])
    def api_start_tracking():
        """Start tracking with camera and servos, saving to video file"""
        return jsonify(start_tracking())
    
    @app.route('/stop_tracking', methods=['POST'])
    def api_stop_tracking():
        """Stop tracking and finalize the video recording"""
        return jsonify(stop_tracking())
    
    @app.route('/status', methods=['GET'])
    def api_get_status():
        """Get current status of tracking system"""
        return jsonify(get_tracking_status())
    
    @app.route('/run_mocap', methods=['POST'])
    def api_run_mocap():
        """Run motion capture processing on the recorded video"""
        return jsonify(run_mocap_processing())
    
    @app.route('/servo_position', methods=['GET'])
    def api_get_servo_position():
        """Get current servo positions"""
        return jsonify(get_servo_position())
    
    @app.route('/servo_position', methods=['POST'])
    def api_set_servo_position():
        """Set servo positions manually"""
        data = request.json
        pan = data.get('pan')
        tilt = data.get('tilt')
        return jsonify(set_servo_position(pan, tilt))
    
    @app.route('/center_servos', methods=['POST'])
    def api_center_servos():
        """Center both servos to default position"""
        return jsonify(center_servos())
    
    @app.route('/cleanup', methods=['POST'])
    def api_cleanup():
        """Clean up all resources when app is shutting down"""
        return jsonify(cleanup_resources())
        
    @app.route('/start_mediapipe_overlay', methods=['POST'])
    def api_start_mediapipe_overlay():
        """Start MediaPipe overlay on camera feed (simpler than full tracking)"""
        return jsonify(start_mediapipe_overlay())
    
    @app.route('/stop_mediapipe_overlay', methods=['POST'])
    def api_stop_mediapipe_overlay():
        """Stop MediaPipe overlay"""
        return jsonify(stop_mediapipe_overlay())
    
    @app.route('/mediapipe_frame', methods=['GET'])
    def api_get_mediapipe_frame():
        """Get current frame with MediaPipe overlay"""
        return jsonify(get_mediapipe_frame())
        
    @app.route('/video_feed')
    def video_feed():
        """Provide MJPEG stream for Flutter WebView"""
        def generate():
            while True:
                frame_data = LiveCap.get_overlay_jpeg()
                if frame_data is not None:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
                time.sleep(0.033)  # ~30 FPS
                
        return Response(generate(),
                        mimetype='multipart/x-mixed-replace; boundary=frame')
    
    parser = argparse.ArgumentParser(description='Flutter integration server for motion tracking')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Server host')
    parser.add_argument('--port', type=int, default=5000, help='Server port')
    
    args = parser.parse_args()
    print(f"Starting Flask server on {args.host}:{args.port}")
    print(f"Running on Raspberry Pi: {is_raspberry_pi()}")
    app.run(host=args.host, port=args.port)
