#!/usr/bin/env python3
# camera_controller.py - Camera control script for Axis Motion Capture System

import os
import sys
import time
import threading
import queue
import json
import cv2
import numpy as np
from pathlib import Path
import argparse
import asyncio
import signal
import subprocess
from datetime import datetime

# Import our mocap processor
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.append(script_dir)

from mocap import MotionCaptureProcessor, create_recorder

# Assume stream_camera.py is in the parent directory
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

try:
    from stream_camera import RaspberryPi5Camera
except ImportError:
    print("Error: Could not import RaspberryPi5Camera from stream_camera.py", file=sys.stderr)
    print("Please ensure stream_camera.py is in the parent directory", file=sys.stderr)
    sys.exit(1)

# Detect if we're running on a Raspberry Pi
try:
    with open('/proc/device-tree/model', 'r') as f:
        if 'Raspberry Pi' in f.read():
            ON_RASPBERRY_PI = True
        else:
            ON_RASPBERRY_PI = False
except:
    ON_RASPBERRY_PI = False

# Path configuration
VIDEOS_DIR = os.path.expanduser("~/Videos/axis_mocap")
os.makedirs(VIDEOS_DIR, exist_ok=True)

class CameraController:
    def __init__(self):
        self.stop_event = threading.Event()
        self.frame_queue = queue.Queue(maxsize=10)
        self.recording = False
        self.video_writer = None
        self.current_video_path = None
        self.current_processed_path = None
        self.camera = None
        
    def initialize_camera(self):
        if ON_RASPBERRY_PI:
            try:
                # Try to use PiCamera2 first
                self.camera = RaspberryPi5Camera()
            except Exception as e:
                print(f"Error initializing Pi 5 camera: {e}", file=sys.stderr)
                try:
                    # Fall back to older PiCamera
                    self.camera = RaspberryPiCamera()
                except Exception as e:
                    print(f"Error initializing Pi camera: {e}", file=sys.stderr)
                    # Fall back to webcam
                    self.camera = WebCamera()
        else:
            # Use webcam on non-Pi systems
            self.camera = WebCamera()
            
        # Start the camera
        self.camera.start(self.frame_queue, self.stop_event)
    
    def start_recording(self, filename=None):
        if self.recording:
            return
            
        # Generate filename if not provided
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"mocap_{timestamp}"
            
        # Ensure the filename doesn't have an extension
        filename = os.path.splitext(filename)[0]
        
        # Set up video path
        self.current_video_path = os.path.join(VIDEOS_DIR, f"{filename}.mp4")
        os.makedirs(os.path.dirname(self.current_video_path), exist_ok=True)
        
        # Initialize video writer
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.video_writer = cv2.VideoWriter(
            self.current_video_path, 
            fourcc, 
            30.0, 
            (640, 480)
        )
        
        self.recording = True
        print(f"Recording started: {self.current_video_path}", file=sys.stderr)
    
    def stop_recording(self):
        if not self.recording:
            return
            
        # Stop recording
        self.recording = False
        
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
            
            # Send status update
            print(f"STATUS:RECORDING_SAVED:{self.current_video_path}")
            sys.stdout.flush()
            
            # Process the video file
            self.process_video(self.current_video_path)
    
    def process_video(self, video_path):
        """Process the recorded video with the mocap.py script"""
        try:
            # Get the path to the mocap.py script
            script_dir = os.path.dirname(os.path.realpath(__file__))
            parent_dir = os.path.dirname(script_dir)
            mocap_script = os.path.join(parent_dir, "mocap.py")
            
            if not os.path.exists(mocap_script):
                print(f"Mocap script not found at: {mocap_script}", file=sys.stderr)
                return
                
            # Start the processing in a separate thread
            processing_thread = threading.Thread(
                target=self._run_processing,
                args=(mocap_script, video_path),
                daemon=True
            )
            processing_thread.start()
            
        except Exception as e:
            print(f"Error starting video processing: {e}", file=sys.stderr)
    
    def _run_processing(self, script_path, video_path):
        """Run the mocap processing script as a separate process"""
        try:
            # Run the mocap script
            cmd = [sys.executable, script_path, "--input", video_path]
            print(f"Running: {' '.join(cmd)}", file=sys.stderr)
            
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Monitor the process
            stdout, stderr = proc.communicate()
            
            if proc.returncode != 0:
                print(f"Mocap processing failed: {stderr}", file=sys.stderr)
                return
                
            # Parse the output to find the processed file path
            processed_file = None
            for line in stdout.splitlines():
                if line.strip().startswith("Saved to:"):
                    processed_file = line.split("Saved to:")[1].strip()
                    break
            
            if processed_file and os.path.exists(processed_file):
                self.current_processed_path = processed_file
                print(f"STATUS:PROCESSED_FILE:{processed_file}")
                sys.stdout.flush()
                print(f"Processed file: {processed_file}", file=sys.stderr)
            else:
                print("Processing completed but no output file found", file=sys.stderr)
                
        except Exception as e:
            print(f"Error during video processing: {e}", file=sys.stderr)
    
    def process_frame(self, frame):
        """Process a frame and handle recording"""
        if self.recording and self.video_writer:
            self.video_writer.write(frame)
            
        # Add MediaPipe skeletal overlay if available
        try:
            # Call the frame processor here if implemented
            # This would be where you integrate with MediaPipe
            pass
        except Exception as e:
            # Just log errors, don't fail on processing errors
            print(f"Frame processing error: {e}", file=sys.stderr)
            
        return frame
    
    def run_stream_mode(self):
        """Run the controller in streaming mode, reading from stdin and sending frames to stdout"""
        print("Starting camera stream mode", file=sys.stderr)
        self.initialize_camera()
        
        # Start processing thread
        processing_thread = threading.Thread(target=self._stream_processor, daemon=True)
        processing_thread.start()
        
        # Start stdin reader thread
        stdin_thread = threading.Thread(target=self._stdin_reader, daemon=True)
        stdin_thread.start()
        
        try:
            # Keep the main thread alive
            while not self.stop_event.is_set():
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Keyboard interrupt received", file=sys.stderr)
        finally:
            self.cleanup()
    
    def _stream_processor(self):
        """Process frames from the camera and send to stdout"""
        frame_count = 0
        while not self.stop_event.is_set():
            try:
                # Get frame from queue with timeout
                frame = self.frame_queue.get(timeout=0.5)
                
                # Process the frame
                processed_frame = self.process_frame(frame)
                
                # Encode frame as JPEG
                ret, jpeg_data = cv2.imencode('.jpg', processed_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ret:
                    # Write the JPEG data to stdout
                    sys.stdout.buffer.write(jpeg_data.tobytes())
                    sys.stdout.buffer.flush()
                    
                    frame_count += 1
                    if frame_count % 30 == 0:  # Log every 30 frames
                        print(f"Processed {frame_count} frames", file=sys.stderr)
                
                self.frame_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in stream processor: {e}", file=sys.stderr)
                time.sleep(0.1)  # Avoid tight loop on error
    
    def _stdin_reader(self):
        """Read commands from stdin"""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
                
            try:
                if line == "EXIT":
                    print("Exit command received", file=sys.stderr)
                    self.stop_event.set()
                    break
                    
                elif line.startswith("START_RECORDING"):
                    # Parse filename if provided
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        filename = parts[1]
                        self.start_recording(filename)
                    else:
                        self.start_recording()
                        
                elif line == "STOP_RECORDING":
                    self.stop_recording()
                    
                elif line == "STATUS":
                    # Send current status
                    status = {
                        "recording": self.recording,
                        "video_path": self.current_video_path,
                        "processed_path": self.current_processed_path
                    }
                    print(f"STATUS:{json.dumps(status)}")
                    sys.stdout.flush()
                    
            except Exception as e:
                print(f"Error processing command '{line}': {e}", file=sys.stderr)
    
    def cleanup(self):
        """Clean up resources"""
        print("Cleaning up", file=sys.stderr)
        if self.recording:
            self.stop_recording()
            
        # Stop the camera
        if self.camera:
            self.camera.stop()
            
        self.stop_event.set()


class RaspberryPi5Camera:
    """Camera implementation for Raspberry Pi 5 using libcamera"""
    def __init__(self):
        self.process = None
        self.thread = None
        self.stop_event = None
    
    def start(self, frame_queue, stop_event):
        self.stop_event = stop_event
        
        # Start libcamera-vid process for continuous streaming
        cmd = [
            "libcamera-vid",
            "--width", "640",
            "--height", "480",
            "--framerate", "30",
            "--codec", "mjpeg",
            "--output", "-",  # Output to stdout
            "--timeout", "0",  # Run continuously
            "--nopreview"      # Don't display preview window
        ]
        
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10*1024*1024  # 10MB buffer
        )
        
        # Start frame reading thread
        self.thread = threading.Thread(
            target=self._frame_reader,
            args=(self.process.stdout, frame_queue),
            daemon=True
        )
        self.thread.start()
        
        # Start stderr reader for debugging
        stderr_thread = threading.Thread(
            target=self._stderr_reader,
            args=(self.process.stderr,),
            daemon=True
        )
        stderr_thread.start()
    
    def _frame_reader(self, stdout, frame_queue):
        """Read JPEG frames from libcamera-vid stdout"""
        buffer = bytearray()
        start_marker = b'\xff\xd8'  # JPEG start marker
        end_marker = b'\xff\xd9'    # JPEG end marker
        
        while not self.stop_event.is_set():
            try:
                # Read data chunk
                chunk = stdout.read(4096)
                if not chunk:
                    break
                    
                # Add to buffer
                buffer.extend(chunk)
                
                # Process any complete frames in the buffer
                while True:
                    start_idx = buffer.find(start_marker)
                    if start_idx == -1:
                        buffer.clear()
                        break
                        
                    # Find end marker after start marker
                    end_idx = buffer.find(end_marker, start_idx)
                    if end_idx == -1:
                        # Incomplete frame, keep buffer
                        if start_idx > 0:
                            # Remove junk before start marker
                            buffer = buffer[start_idx:]
                        break
                    
                    # Extract complete frame
                    end_idx += 2  # Include end marker
                    frame_data = buffer[start_idx:end_idx]
                    
                    # Decode the JPEG frame
                    try:
                        img = cv2.imdecode(np.frombuffer(frame_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if img is not None and not frame_queue.full():
                            frame_queue.put(img)
                    except Exception as e:
                        print(f"Error decoding frame: {e}", file=sys.stderr)
                    
                    # Remove processed frame from buffer
                    buffer = buffer[end_idx:]
                    
            except Exception as e:
                print(f"Error reading frames: {e}", file=sys.stderr)
                time.sleep(0.1)  # Avoid tight loop on error
    
    def _stderr_reader(self, stderr):
        """Read and log stderr from libcamera process"""
        while not self.stop_event.is_set():
            line = stderr.readline()
            if not line:
                break
            print(f"libcamera: {line.decode().strip()}", file=sys.stderr)
    
    def stop(self):
        """Stop the camera"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except:
                self.process.kill()
            self.process = None


class RaspberryPiCamera:
    """Fallback camera implementation for older Raspberry Pi models"""
    def __init__(self):
        self.process = None
        self.thread = None
        self.stop_event = None
    
    def start(self, frame_queue, stop_event):
        self.stop_event = stop_event
        
        # Start raspivid process
        cmd = [
            "raspivid",
            "-w", "640",
            "-h", "480",
            "-fps", "30",
            "-t", "0",       # Run indefinitely
            "-o", "-",       # Output to stdout
            "-pf", "mjpeg"   # Use MJPEG format
        ]
        
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Start frame reading thread similar to Pi 5 camera
        self.thread = threading.Thread(
            target=self._frame_reader,
            args=(self.process.stdout, frame_queue),
            daemon=True
        )
        self.thread.start()
    
    # Frame reader is the same as RaspberryPi5Camera
    _frame_reader = RaspberryPi5Camera._frame_reader
    _stderr_reader = RaspberryPi5Camera._stderr_reader
    
    def stop(self):
        """Stop the camera"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except:
                self.process.kill()
            self.process = None


class WebCamera:
    """Generic webcam implementation using OpenCV"""
    def __init__(self):
        self.cap = None
        self.thread = None
        self.stop_event = None
    
    def start(self, frame_queue, stop_event):
        self.stop_event = stop_event
        
        # Open webcam
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            raise Exception("Failed to open webcam")
            
        # Set resolution
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        # Start frame capture thread
        self.thread = threading.Thread(
            target=self._capture_frames,
            args=(frame_queue,),
            daemon=True
        )
        self.thread.start()
    
    def _capture_frames(self, frame_queue):
        """Capture frames from webcam"""
        while not self.stop_event.is_set():
            try:
                ret, frame = self.cap.read()
                if not ret:
                    print("Failed to read frame from webcam", file=sys.stderr)
                    time.sleep(0.1)
                    continue
                
                if not frame_queue.full():
                    frame_queue.put(frame)
                
                # Small delay to avoid consuming too much CPU
                time.sleep(0.01)
                
            except Exception as e:
                print(f"Error capturing frame: {e}", file=sys.stderr)
                time.sleep(0.1)
    
    def stop(self):
        """Stop the webcam"""
        if self.cap:
            self.cap.release()
            self.cap = None


def main():
    parser = argparse.ArgumentParser(description="Camera controller for Axis Mocap")
    parser.add_argument("--mode", choices=["stream", "interactive"], default="stream",
                       help="Operating mode: stream (default) or interactive")
    args = parser.parse_args()
    
    # Set up signal handler
    def signal_handler(sig, frame):
        print("Signal received, shutting down", file=sys.stderr)
        controller.stop_event.set()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and run controller
    controller = CameraController()
    
    if args.mode == "stream":
        controller.run_stream_mode()
    else:
        # Interactive mode would have a local UI or command handling
        print("Interactive mode not implemented yet", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main() 