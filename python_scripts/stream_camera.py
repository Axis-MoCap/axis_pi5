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
        self.frame_queue = queue.Queue(maxsize=2)  # Limit queue size to prevent memory issues
        
    def start(self):
        try:
            # Use libcamera-vid for streaming
            cmd = [
                'libcamera-vid',
                '--camera', '0',  # Use camera index 0 by default
                '--width', str(self.width),
                '--height', str(self.height),
                '--framerate', str(self.fps),
                '--codec', 'mjpeg',  # Use MJPEG for better performance
                '--output', '-'  # Stream to stdout
            ]
            
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
            
            return True
        except Exception as e:
            print(f"Error starting Raspberry Pi 5 camera: {e}", file=sys.stderr)
            return False
    
    def _read_frames(self):
        # This function runs in a separate thread
        try:
            # Buffer for reading JPEG data
            buffer = io.BytesIO()
            start_marker_found = False
            
            while running and self.process.poll() is None:
                data = self.process.stdout.read(4096)  # Read in chunks
                
                if not data:
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
                self.process.terminate()
    
    def get_frame(self):
        try:
            # Non-blocking get with timeout
            return self.frame_queue.get(timeout=1.0)
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

class RaspberryPiCamera:
    """Camera interface for Raspberry Pi (legacy)"""
    
    def __init__(self, camera_path, width=640, height=480, fps=30):
        self.camera_path = camera_path
        self.width = width
        self.height = height
        self.fps = fps
        self.process = None
        
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
    
    def get_frame(self):
        """Read and encode a single frame"""
        try:
            # For simplicity, read a complete JPEG frame
            # This is a simplified implementation - in production, should properly parse video stream
            
            # Read data until JPEG end marker is found
            buffer = io.BytesIO()
            start_marker_found = False
            end_marker_found = False
            
            # Set a timeout to avoid blocking forever
            start_time = time.time()
            timeout = 1.0  # 1 second timeout
            
            while not end_marker_found and time.time() - start_time < timeout:
                data = self.process.stdout.read(1024)  # Read in chunks
                
                if not data:
                    break
                
                # Look for JPEG markers in the data
                for i in range(len(data)-1):
                    # Start marker (0xFF 0xD8)
                    if not start_marker_found and data[i] == 0xFF and data[i+1] == 0xD8:
                        buffer = io.BytesIO()  # Reset buffer
                        buffer.write(data[i:])
                        start_marker_found = True
                        break
                    # End marker (0xFF 0xD9)
                    elif start_marker_found and data[i] == 0xFF and data[i+1] == 0xD9:
                        buffer.write(data[:i+2])  # Include the end marker
                        end_marker_found = True
                        break
                
                if not start_marker_found:
                    buffer.write(data)
            
            if end_marker_found:
                jpeg_data = buffer.getvalue()
                return base64.b64encode(jpeg_data).decode('utf-8')
            
            return None
        except Exception as e:
            print(f"Error getting frame: {e}", file=sys.stderr)
            return None
    
    def release(self):
        if self.process:
            self.process.terminate()
            self.process = None

class WebCamera:
    """Camera interface for USB webcams or other V4L2 cameras"""
    
    def __init__(self, camera_path, width=640, height=480, fps=30):
        self.camera_path = camera_path
        self.width = width
        self.height = height
        self.fps = fps
        self.process = None
        
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
            
            # Wait a moment for process to start
            time.sleep(0.5)
            
            return self.process.poll() is None  # Check if process is still running
        except Exception as e:
            print(f"Error starting webcam: {e}", file=sys.stderr)
            return False
    
    def get_frame(self):
        """Read and encode a single frame"""
        try:
            # Similar approach to RaspberryPiCamera
            buffer = io.BytesIO()
            start_marker_found = False
            end_marker_found = False
            
            # Set a timeout to avoid blocking forever
            start_time = time.time()
            timeout = 1.0  # 1 second timeout
            
            while not end_marker_found and time.time() - start_time < timeout:
                data = self.process.stdout.read(4096)  # Read in larger chunks for efficiency
                
                if not data:
                    break
                
                # Look for JPEG markers
                i = 0
                while i < len(data) - 1:
                    # Start marker (0xFF 0xD8)
                    if not start_marker_found and data[i] == 0xFF and data[i+1] == 0xD8:
                        buffer = io.BytesIO()  # Reset buffer
                        buffer.write(data[i:])
                        start_marker_found = True
                        break
                    # End marker (0xFF 0xD9)
                    elif start_marker_found and data[i] == 0xFF and data[i+1] == 0xD9:
                        buffer.write(data[:i+2])  # Include the end marker
                        end_marker_found = True
                        break
                    i += 1
                
                if not start_marker_found and not end_marker_found:
                    buffer.write(data)
            
            if start_marker_found and end_marker_found:
                jpeg_data = buffer.getvalue()
                return base64.b64encode(jpeg_data).decode('utf-8')
            
            return None
        except Exception as e:
            print(f"Error getting webcam frame: {e}", file=sys.stderr)
            return None
    
    def release(self):
        if self.process:
            self.process.terminate()
            self.process = None

def main():
    parser = argparse.ArgumentParser(description='Stream camera feed')
    parser.add_argument('--camera_path', required=True, help='Path to camera device')
    parser.add_argument('--type', choices=['raspberry', 'raspberry5', 'webcam'],
                        required=True, help='Type of camera to stream')
    parser.add_argument('--width', type=int, default=640, help='Frame width')
    parser.add_argument('--height', type=int, default=480, help='Frame height')
    parser.add_argument('--fps', type=int, default=30, help='Frames per second')
    
    args = parser.parse_args()
    
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
        
        while running:
            frame = camera.get_frame()
            
            if frame:
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
            
            # Small sleep to avoid maxing out CPU
            time.sleep(0.001)
    except KeyboardInterrupt:
        print("Streaming stopped by user")
    finally:
        camera.release()

if __name__ == "__main__":
    main() 