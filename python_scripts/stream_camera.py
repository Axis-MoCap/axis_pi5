#!/usr/bin/env python3
# stream_camera.py - Camera streaming script for Axis Motion Capture System

import sys
import argparse
import subprocess
import base64
import time
import os
import io
from threading import Thread
import numpy as np
import queue
import signal
import glob

# Global flag to control the streaming loop
running = True

def signal_handler(sig, frame):
    global running
    running = False
    print("Stopping camera stream...", file=sys.stderr)

# Register signal handler for graceful termination
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

class RaspberryPi5Camera:
    """Camera interface for Raspberry Pi 5 using libcamera"""
    
    def __init__(self, camera_path, width=640, height=480, fps=30):
        self.camera_path = camera_path
        self.width = width
        self.height = height
        self.fps = fps
        self.process = None
        self.frame_queue = queue.Queue(maxsize=5)  # Increase queue size for smoother streaming
        self.mode = 'libcamera-vid'  # Default mode
        
    def start(self):
        try:
            print(f"DEBUG: Starting Raspberry Pi 5 camera at {self.camera_path}", file=sys.stderr)
            print(f"DEBUG: Width: {self.width}, Height: {self.height}, FPS: {self.fps}", file=sys.stderr)
            
            # Check camera path exists
            if not os.path.exists(self.camera_path):
                print(f"DEBUG: Camera path {self.camera_path} does not exist", file=sys.stderr)
                # Try to find an alternative video device
                video_devices = glob.glob('/dev/video*')
                if video_devices:
                    self.camera_path = video_devices[0]
                    print(f"DEBUG: Using alternative camera: {self.camera_path}", file=sys.stderr)
                else:
                    print("DEBUG: No video devices found", file=sys.stderr)
                    return False
            
            # Try to determine the best available method
            if self._check_command_exists('libcamera-vid'):
                self.mode = 'libcamera-vid'
            elif self._check_command_exists('ffmpeg'):
                self.mode = 'ffmpeg'
            else:
                print("DEBUG: Neither libcamera-vid nor ffmpeg are available", file=sys.stderr)
                return False
                
            print(f"DEBUG: Using {self.mode} mode", file=sys.stderr)
            
            if self.mode == 'libcamera-vid':
                # Use libcamera-vid for streaming
                cmd = [
                    'libcamera-vid',
                    '--camera', '0',  # Use camera index 0 by default
                    '--width', str(self.width),
                    '--height', str(self.height),
                    '--framerate', str(self.fps),
                    '--codec', 'mjpeg',  # Use MJPEG for better performance
                    '--output', '-',  # Stream to stdout
                    '--timeout', '0',  # Run continuously
                    '--nopreview',    # No preview window
                ]
            else:  # ffmpeg mode
                # Use ffmpeg as fallback
                cmd = [
                    'ffmpeg',
                    '-f', 'v4l2',
                    '-input_format', 'mjpeg',  # Try MJPEG format first
                    '-video_size', f"{self.width}x{self.height}",
                    '-framerate', str(self.fps),
                    '-i', self.camera_path,
                    '-f', 'image2pipe',
                    '-vcodec', 'mjpeg',
                    '-q:v', '3',  # Better quality (lower is better quality in ffmpeg)
                    '-'
                ]
            
            print(f"DEBUG: Running command: {' '.join(cmd)}", file=sys.stderr)
            
            # Start the process
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=10**7  # Use a large buffer
            )
            
            # Start a thread to read frames
            self.thread = Thread(target=self._read_frames)
            self.thread.daemon = True
            self.thread.start()
            
            # Start a thread to monitor stderr for debugging
            self.error_thread = Thread(target=self._monitor_stderr)
            self.error_thread.daemon = True
            self.error_thread.start()
            
            # Give it a moment to start up and check if it's running
            time.sleep(1)
            if self.process.poll() is not None:
                print(f"DEBUG: Process exited with code {self.process.poll()}", file=sys.stderr)
                return False
                
            return True
        except Exception as e:
            print(f"Error starting Raspberry Pi 5 camera: {e}", file=sys.stderr)
            return False
            
    def _check_command_exists(self, command):
        """Check if a command exists on the system"""
        try:
            subprocess.run(['which', command], 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE,
                          check=True)
            return True
        except subprocess.SubprocessError:
            return False
            
    def _monitor_stderr(self):
        """Monitor stderr for debugging info"""
        try:
            while running and self.process and self.process.poll() is None:
                line = self.process.stderr.readline()
                if line:
                    print(f"DEBUG: Camera stderr: {line.decode('utf-8', errors='replace').strip()}", file=sys.stderr)
        except Exception as e:
            print(f"Error in stderr monitor: {e}", file=sys.stderr)
    
    def _read_frames(self):
        # This function runs in a separate thread
        try:
            # Buffer for reading JPEG data
            buffer = io.BytesIO()
            start_marker_found = False
            
            print("DEBUG: Starting frame reading thread", file=sys.stderr)
            frame_count = 0
            last_report_time = time.time()
            
            while running and self.process and self.process.poll() is None:
                data = self.process.stdout.read(4096)  # Read in chunks
                
                if not data:
                    print("DEBUG: End of stream reached", file=sys.stderr)
                    break
                
                # Look for JPEG markers in the data
                i = 0
                while i < len(data):
                    # Check for JPEG start marker (0xFF 0xD8)
                    if not start_marker_found and i < len(data) - 1 and data[i] == 0xFF and data[i+1] == 0xD8:
                        buffer = io.BytesIO()
                        buffer.write(data[i:i+2])
                        start_marker_found = True
                        i += 2
                    # Check for JPEG end marker (0xFF 0xD9)
                    elif start_marker_found and i < len(data) - 1 and data[i] == 0xFF and data[i+1] == 0xD9:
                        buffer.write(data[i:i+2])
                        
                        # Complete JPEG image - encode and add to queue
                        jpeg_data = buffer.getvalue()
                        try:
                            # Only add to queue if not full (dropping frames if necessary)
                            if not self.frame_queue.full():
                                b64_frame = base64.b64encode(jpeg_data).decode('utf-8')
                                self.frame_queue.put(b64_frame, block=False)
                                frame_count += 1
                                
                                # Report frames processed every 5 seconds
                                current_time = time.time()
                                if current_time - last_report_time >= 5:
                                    print(f"DEBUG: Processed {frame_count} frames in last {current_time - last_report_time:.1f} seconds", file=sys.stderr)
                                    frame_count = 0
                                    last_report_time = current_time
                        except queue.Full:
                            pass  # Skip frame if queue is full
                            
                        start_marker_found = False
                        i += 2
                    # Continue building the current JPEG
                    elif start_marker_found:
                        buffer.write(bytes([data[i]]))
                        i += 1
                    else:
                        i += 1
        except Exception as e:
            print(f"Error in frame reading thread: {e}", file=sys.stderr)
        finally:
            if self.process:
                print("DEBUG: Frame reading thread terminated", file=sys.stderr)
                self.process.terminate()
    
    def get_frame(self):
        try:
            # Non-blocking get with timeout
            return self.frame_queue.get(timeout=0.5)  # Reduced timeout for more responsive streaming
        except queue.Empty:
            return None
    
    def release(self):
        global running
        running = False
        
        if self.process:
            self.process.terminate()
            self.process = None
            
        # Wait for reading thread to finish
        if hasattr(self, 'thread') and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        
        # Wait for error thread to finish
        if hasattr(self, 'error_thread') and self.error_thread.is_alive():
            self.error_thread.join(timeout=1.0)

class RaspberryPiCamera:
    """Camera interface for Raspberry Pi (legacy)"""
    
    def __init__(self, camera_path, width=640, height=480, fps=30):
        self.camera_path = camera_path
        self.width = width
        self.height = height
        self.fps = fps
        self.process = None
        self.frame_queue = queue.Queue(maxsize=5)  # Add a queue for continuous streaming
        
    def start(self):
        try:
            # First try raspistill for still images (older Pi cameras)
            self.mode = self._check_camera_mode()
            
            if self.mode == 'raspivid':
                # Use raspivid for video streaming
                cmd = [
                    'raspivid',
                    '-t', '0',  # Run indefinitely
                    '-w', str(self.width),
                    '-h', str(self.height),
                    '-fps', str(self.fps),
                    '-o', '-',  # Output to stdout
                    '-pf', 'baseline'  # Use baseline profile for compatibility
                ]
                
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            elif self.mode == 'v4l2':
                # Use v4l2-ctl for streaming
                cmd = [
                    'ffmpeg',
                    '-f', 'v4l2',
                    '-input_format', 'mjpeg',  # Request MJPEG from camera
                    '-video_size', f"{self.width}x{self.height}",
                    '-framerate', str(self.fps),
                    '-i', self.camera_path,
                    '-f', 'image2pipe',  # Output individual images
                    '-vcodec', 'mjpeg',  # Output MJPEG
                    '-q:v', '5',  # Quality setting (1-31, lower is better)
                    '-'  # Output to stdout
                ]
                
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            else:
                print("Could not determine Raspberry Pi camera mode", file=sys.stderr)
                return False
            
            # Start a thread to read frames
            self.thread = Thread(target=self._read_frames)
            self.thread.daemon = True
            self.thread.start()
                
            return True
        except Exception as e:
            print(f"Error starting Raspberry Pi camera: {e}", file=sys.stderr)
            return False
    
    def _check_camera_mode(self):
        """Check whether to use raspivid or v4l2 interface"""
        try:
            # Check if raspivid is available
            result = subprocess.run(['which', 'raspivid'], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE,
                                   text=True)
            if result.returncode == 0:
                return 'raspivid'
            else:
                return 'v4l2'
        except:
            return 'v4l2'  # Default to v4l2 interface

    def _read_frames(self):
        # Similar implementation as RaspberryPi5Camera
        try:
            buffer = io.BytesIO()
            start_marker_found = False
            
            print("DEBUG: Starting legacy Pi camera reading thread", file=sys.stderr)
            frame_count = 0
            last_report_time = time.time()
            
            while running and self.process and self.process.poll() is None:
                data = self.process.stdout.read(4096)
                
                if not data:
                    print("DEBUG: End of stream reached", file=sys.stderr)
                    break
                
                # Look for JPEG markers
                i = 0
                while i < len(data):
                    # Start marker
                    if not start_marker_found and i < len(data) - 1 and data[i] == 0xFF and data[i+1] == 0xD8:
                        buffer = io.BytesIO()
                        buffer.write(data[i:i+2])
                        start_marker_found = True
                        i += 2
                    # End marker
                    elif start_marker_found and i < len(data) - 1 and data[i] == 0xFF and data[i+1] == 0xD9:
                        buffer.write(data[i:i+2])
                        
                        # Complete JPEG - add to queue
                        jpeg_data = buffer.getvalue()
                        try:
                            if not self.frame_queue.full():
                                b64_frame = base64.b64encode(jpeg_data).decode('utf-8')
                                self.frame_queue.put(b64_frame, block=False)
                                frame_count += 1
                        except queue.Full:
                            pass
                            
                        start_marker_found = False
                        i += 2
                    elif start_marker_found:
                        buffer.write(bytes([data[i]]))
                        i += 1
                    else:
                        i += 1
                        
                # Report frames
                current_time = time.time()
                if current_time - last_report_time >= 5:
                    print(f"DEBUG: Legacy Pi camera processed {frame_count} frames", file=sys.stderr)
                    frame_count = 0
                    last_report_time = current_time
        except Exception as e:
            print(f"Error in legacy Pi camera frame reading: {e}", file=sys.stderr)
    
    def get_frame(self):
        try:
            return self.frame_queue.get(timeout=0.5)
        except queue.Empty:
            return None
    
    def release(self):
        if self.process:
            self.process.terminate()
            self.process = None
            
        if hasattr(self, 'thread') and self.thread.is_alive():
            self.thread.join(timeout=1.0)

class WebCamera:
    """Camera interface for USB webcams or other V4L2 cameras"""
    
    def __init__(self, camera_path, width=640, height=480, fps=30):
        self.camera_path = camera_path
        self.width = width
        self.height = height
        self.fps = fps
        self.process = None
        self.frame_queue = queue.Queue(maxsize=5)  # Add a queue for continuous streaming
        
    def start(self):
        try:
            # Use ffmpeg to grab frames from webcam
            cmd = [
                'ffmpeg',
                '-f', 'v4l2',  # Use Video4Linux2 interface
                '-input_format', 'mjpeg',  # Request MJPEG from camera if supported
                '-video_size', f"{self.width}x{self.height}",
                '-framerate', str(self.fps),
                '-i', self.camera_path,
                '-f', 'image2pipe',  # Output individual images
                '-pix_fmt', 'yuvj420p',  # Use JPEG color space
                '-vcodec', 'mjpeg',  # Output MJPEG format
                '-q:v', '5',  # Quality setting (1-31, lower is better)
                '-'  # Output to stdout
            ]
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Start a thread to read frames
            self.thread = Thread(target=self._read_frames)
            self.thread.daemon = True
            self.thread.start()
            
            # Wait a moment for process to start
            time.sleep(0.5)
            
            return self.process.poll() is None  # Check if process is still running
        except Exception as e:
            print(f"Error starting webcam: {e}", file=sys.stderr)
            return False
    
    def _read_frames(self):
        # Similar implementation as RaspberryPi5Camera
        try:
            buffer = io.BytesIO()
            start_marker_found = False
            
            print("DEBUG: Starting webcam reading thread", file=sys.stderr)
            frame_count = 0
            last_report_time = time.time()
            
            while running and self.process and self.process.poll() is None:
                data = self.process.stdout.read(4096)
                
                if not data:
                    print("DEBUG: End of webcam stream reached", file=sys.stderr)
                    break
                
                # Look for JPEG markers
                i = 0
                while i < len(data):
                    # Start marker
                    if not start_marker_found and i < len(data) - 1 and data[i] == 0xFF and data[i+1] == 0xD8:
                        buffer = io.BytesIO()
                        buffer.write(data[i:i+2])
                        start_marker_found = True
                        i += 2
                    # End marker
                    elif start_marker_found and i < len(data) - 1 and data[i] == 0xFF and data[i+1] == 0xD9:
                        buffer.write(data[i:i+2])
                        
                        # Complete JPEG - add to queue
                        jpeg_data = buffer.getvalue()
                        try:
                            if not self.frame_queue.full():
                                b64_frame = base64.b64encode(jpeg_data).decode('utf-8')
                                self.frame_queue.put(b64_frame, block=False)
                                frame_count += 1
                        except queue.Full:
                            pass
                            
                        start_marker_found = False
                        i += 2
                    elif start_marker_found:
                        buffer.write(bytes([data[i]]))
                        i += 1
                    else:
                        i += 1
                        
                # Report frames
                current_time = time.time()
                if current_time - last_report_time >= 5:
                    print(f"DEBUG: Webcam processed {frame_count} frames", file=sys.stderr)
                    frame_count = 0
                    last_report_time = current_time
        except Exception as e:
            print(f"Error in webcam frame reading: {e}", file=sys.stderr)
    
    def get_frame(self):
        try:
            return self.frame_queue.get(timeout=0.5)
        except queue.Empty:
            return None
    
    def release(self):
        if self.process:
            self.process.terminate()
            self.process = None
            
        if hasattr(self, 'thread') and self.thread.is_alive():
            self.thread.join(timeout=1.0)

def main():
    parser = argparse.ArgumentParser(description='Stream camera feed')
    parser.add_argument('--camera_path', required=True, help='Path to camera device')
    parser.add_argument('--type', choices=['raspberry', 'raspberry5', 'webcam'],
                        required=True, help='Type of camera to stream')
    parser.add_argument('--width', type=int, default=640, help='Frame width')
    parser.add_argument('--height', type=int, default=480, help='Frame height')
    parser.add_argument('--fps', type=int, default=30, help='Frames per second')
    
    args = parser.parse_args()
    
    # Print starting message
    print(f"DEBUG: Starting camera stream of type {args.type} from {args.camera_path}", file=sys.stderr)
    print(f"DEBUG: Resolution: {args.width}x{args.height} @ {args.fps} fps", file=sys.stderr)
    
    # Create camera object based on type
    if args.type == 'raspberry5':
        camera = RaspberryPi5Camera(args.camera_path, args.width, args.height, args.fps)
    elif args.type == 'raspberry':
        camera = RaspberryPiCamera(args.camera_path, args.width, args.height, args.fps)
    elif args.type == 'webcam':
        camera = WebCamera(args.camera_path, args.width, args.height, args.fps)
    else:
        print(f"Unknown camera type: {args.type}")
        sys.exit(1)
    
    # Start camera
    if not camera.start():
        print(f"Failed to start {args.type} camera")
        sys.exit(1)
    
    try:
        # Stream frames
        frame_count = 0
        last_time = time.time()
        
        print("DEBUG: Entering main streaming loop", file=sys.stderr)
        
        while running:
            frame = camera.get_frame()
            
            if frame:
                # Check frame size
                frame_size = len(frame)
                if frame_count == 0:
                    print(f"DEBUG: First frame size: {frame_size} bytes", file=sys.stderr)
                    
                # Print frame data in format that Flutter app expects
                print(f"FRAME:{frame}")
                sys.stdout.flush()  # Ensure data is sent immediately
                
                # Simple FPS counter
                frame_count += 1
                current_time = time.time()
                elapsed = current_time - last_time
                
                if elapsed >= 5.0:  # Report FPS every 5 seconds
                    fps = frame_count / elapsed
                    print(f"FPS: {fps:.2f}", file=sys.stderr)
                    frame_count = 0
                    last_time = current_time
            else:
                # No frame received
                current_time = time.time()
                if current_time - last_time >= 5.0 and frame_count == 0:
                    print("DEBUG: No frames received in the last 5 seconds", file=sys.stderr)
                    last_time = current_time
            
            # Small sleep to avoid maxing out CPU
            time.sleep(0.001)
    except KeyboardInterrupt:
        print("Streaming stopped by user")
    finally:
        camera.release()

if __name__ == "__main__":
    main() 