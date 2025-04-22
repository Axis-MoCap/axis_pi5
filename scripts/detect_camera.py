#!/usr/bin/env python3
import argparse
import sys
import os
import time

def detect_raspberry_pi_camera():
    """Detect if Raspberry Pi camera is connected and available."""
    try:
        # Check if the camera module is loaded
        if os.path.exists('/dev/video0'):
            # Try to access the camera
            print("CAMERA_FOUND:/dev/video0")
            sys.stdout.flush()
            return True
        elif os.path.exists('/dev/vchiq'):
            # Legacy camera interface
            print("CAMERA_FOUND:/dev/vchiq")
            sys.stdout.flush()
            return True
        else:
            print("Raspberry Pi camera not found")
            sys.stdout.flush()
            return False
    except Exception as e:
        print(f"Error detecting Raspberry Pi camera: {e}")
        sys.stdout.flush()
        return False

def detect_webcam():
    """Detect if a webcam is connected and available."""
    try:
        # Check common webcam device paths
        for i in range(10):  # Check /dev/video0 through /dev/video9
            device_path = f"/dev/video{i}"
            if os.path.exists(device_path):
                print(f"CAMERA_FOUND:{device_path}")
                sys.stdout.flush()
                return True
                
        # No webcam found
        print("No webcam found")
        sys.stdout.flush()
        return False
    except Exception as e:
        print(f"Error detecting webcam: {e}")
        sys.stdout.flush()
        return False

def main():
    parser = argparse.ArgumentParser(description="Detect camera devices")
    parser.add_argument("--type", choices=["raspberry", "webcam"], required=True, 
                        help="Type of camera to detect")
    
    args = parser.parse_args()
    
    if args.type == "raspberry":
        detect_raspberry_pi_camera()
    elif args.type == "webcam":
        detect_webcam()

if __name__ == "__main__":
    main() 