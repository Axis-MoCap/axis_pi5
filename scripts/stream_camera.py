#!/usr/bin/env python3
import argparse
import sys
import os
import time
import signal
import json

# Global flag for handling termination
running = True

def signal_handler(sig, frame):
    """Handle termination signals."""
    global running
    running = False
    print("Camera stream stopped by user")
    sys.stdout.flush()

def stream_raspberry_pi_camera(camera_path):
    """Stream from Raspberry Pi camera."""
    try:
        print(f"Starting Raspberry Pi camera stream from {camera_path}")
        sys.stdout.flush()
        
        # In a real implementation, you would use picamera or similar
        # Here we simulate frames being sent
        frame_count = 0
        while running:
            # This would normally capture and process a frame
            frame_data = {
                "frame": frame_count,
                "timestamp": time.time()
            }
            
            # Send the frame data to stdout
            # In a real implementation, you would send binary frame data
            print(json.dumps(frame_data))
            sys.stdout.flush()
            
            frame_count += 1
            time.sleep(0.033)  # ~30 FPS
            
    except Exception as e:
        print(f"Error streaming from Raspberry Pi camera: {e}")
        sys.stdout.flush()

def stream_webcam(camera_path):
    """Stream from webcam."""
    try:
        print(f"Starting webcam stream from {camera_path}")
        sys.stdout.flush()
        
        # In a real implementation, you would use OpenCV or similar
        # Here we simulate frames being sent
        frame_count = 0
        while running:
            # This would normally capture and process a frame
            frame_data = {
                "frame": frame_count,
                "timestamp": time.time()
            }
            
            # Send the frame data to stdout
            # In a real implementation, you would send binary frame data
            print(json.dumps(frame_data))
            sys.stdout.flush()
            
            frame_count += 1
            time.sleep(0.033)  # ~30 FPS
            
    except Exception as e:
        print(f"Error streaming from webcam: {e}")
        sys.stdout.flush()

def main():
    parser = argparse.ArgumentParser(description="Stream from camera")
    parser.add_argument("--camera_path", required=True, help="Path to camera device")
    parser.add_argument("--type", choices=["raspberry", "webcam"], required=True, 
                        help="Type of camera to use")
    
    args = parser.parse_args()
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    if args.type == "raspberry":
        stream_raspberry_pi_camera(args.camera_path)
    elif args.type == "webcam":
        stream_webcam(args.camera_path)

if __name__ == "__main__":
    main() 