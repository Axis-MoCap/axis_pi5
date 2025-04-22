#!/usr/bin/env python3
# detect_camera.py - Camera detection script for Axis Motion Capture System

import sys
import argparse
import subprocess
import json
import os

def detect_raspberry_pi5_camera():
    """
    Detect cameras using the Raspberry Pi 5 camera interface (libcamera)
    """
    try:
        # Run the libcamera-hello command to check for cameras
        result = subprocess.run(['libcamera-hello', '--list-cameras'], 
                               stdout=subprocess.PIPE, 
                               stderr=subprocess.PIPE,
                               text=True)
        
        if "Available cameras" in result.stdout or "Available cameras" in result.stderr:
            # Extract camera information
            for line in (result.stdout + result.stderr).split('\n'):
                if "Available cameras" in line or "* " in line:
                    # Found a camera, usually identified with format: * 0: Camera_Name
                    if line.strip().startswith('*'):
                        camera_id = line.split(':')[0].strip('* ')
                        print(f"CAMERA_FOUND:/dev/video{camera_id}")
                        return True
        
        # Try direct device detection if libcamera-hello approach fails
        if os.path.exists('/dev/video0'):
            print("CAMERA_FOUND:/dev/video0")
            return True
            
        return False
    except Exception as e:
        print(f"Error detecting Raspberry Pi 5 camera: {e}", file=sys.stderr)
        return False

def detect_raspberry_pi_camera():
    """
    Detect legacy Raspberry Pi camera module (using raspistill or v4l2)
    """
    try:
        # First try with raspistill (works on older Raspberry Pi OS)
        try:
            result = subprocess.run(['raspistill', '-v'], 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE,
                                  text=True, 
                                  timeout=2)
            
            if "Camera found" in result.stderr or "Camera detected" in result.stderr:
                print("CAMERA_FOUND:/dev/video0")
                return True
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        
        # Fallback to v4l2 detection
        result = subprocess.run(['v4l2-ctl', '--list-devices'], 
                               stdout=subprocess.PIPE, 
                               stderr=subprocess.PIPE,
                               text=True)
        
        lines = result.stdout.split('\n')
        for i, line in enumerate(lines):
            if "mmal" in line or "bcm2835" in line or "Raspberry Pi Camera" in line:
                # Next line typically contains the device path
                if i + 1 < len(lines) and "/dev/video" in lines[i+1]:
                    device_path = lines[i+1].strip()
                    print(f"CAMERA_FOUND:{device_path}")
                    return True
        
        return False
    except Exception as e:
        print(f"Error detecting Raspberry Pi camera: {e}", file=sys.stderr)
        return False

def detect_webcam():
    """
    Detect USB webcams or other V4L2 cameras
    """
    try:
        # List video devices
        result = subprocess.run(['v4l2-ctl', '--list-devices'], 
                               stdout=subprocess.PIPE, 
                               stderr=subprocess.PIPE,
                               text=True)
        
        lines = result.stdout.split('\n')
        for i, line in enumerate(lines):
            # Skip Raspberry Pi specific cameras
            if "mmal" in line or "bcm2835" in line or "Raspberry Pi Camera" in line:
                continue
                
            # Look for USB webcams or other camera devices
            if "camera" in line.lower() or "webcam" in line.lower() or "cam" in line.lower():
                # Next line typically contains the device path
                if i + 1 < len(lines) and "/dev/video" in lines[i+1]:
                    device_path = lines[i+1].strip()
                    print(f"CAMERA_FOUND:{device_path}")
                    return True
        
        # If no specific camera found but video devices exist
        for line in lines:
            if "/dev/video" in line:
                device_path = line.strip()
                print(f"CAMERA_FOUND:{device_path}")
                return True
                
        return False
    except Exception as e:
        print(f"Error detecting webcam: {e}", file=sys.stderr)
        return False

def main():
    parser = argparse.ArgumentParser(description='Detect camera devices')
    parser.add_argument('--type', choices=['raspberry', 'raspberry5', 'webcam'],
                        required=True, help='Type of camera to detect')
    
    args = parser.parse_args()
    
    if args.type == 'raspberry5':
        if detect_raspberry_pi5_camera():
            sys.exit(0)
        else:
            print("No Raspberry Pi 5 camera found")
            sys.exit(1)
    elif args.type == 'raspberry':
        if detect_raspberry_pi_camera():
            sys.exit(0)
        else:
            print("No Raspberry Pi camera found")
            sys.exit(1)
    elif args.type == 'webcam':
        if detect_webcam():
            sys.exit(0)
        else:
            print("No webcam found")
            sys.exit(1)

if __name__ == "__main__":
    main() 