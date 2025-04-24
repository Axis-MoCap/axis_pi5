import cv2
import sys
import argparse
from picamera2 import Picamera2
from ultralytics import YOLO
import time
import os
import logging
import subprocess
import json
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("yolo_pose")

# Parse command line arguments
parser = argparse.ArgumentParser(description='YOLO Pose Detection Demo')
parser.add_argument('--video', type=str, help='Path to video file to use instead of camera')
parser.add_argument('--retry', type=int, default=3, help='Number of retries for camera setup')
parser.add_argument('--output', type=str, default=None, help='Path to save results json')
parser.add_argument('--debug', action='store_true', help='Enable debug logging')
args = parser.parse_args()

if args.debug:
    logger.setLevel(logging.DEBUG)
    logger.debug("Debug logging enabled")

def setup_camera(retries=3):
    """
    Setup camera with retry logic. Returns camera object or None if failed.
    """
    logger.info(f"Attempting to set up camera with {retries} retries")
    
    # Check if camera is already in use by other processes
    try:
        result = subprocess.run(['fuser', '/dev/video0'], capture_output=True, text=True)
        if result.stdout.strip():
            logger.warning(f"Camera appears to be in use by PIDs: {result.stdout.strip()}")
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.debug("Couldn't check camera usage with fuser command")
    
    for attempt in range(retries):
        try:
            logger.info(f"Camera setup attempt {attempt+1}/{retries}")
            cap = cv2.VideoCapture(0)
            
            if not cap.isOpened():
                raise RuntimeError("Failed to open camera")
                
            # Check if we can actually read a frame
            ret, _ = cap.read()
            if not ret:
                raise RuntimeError("Camera opened but couldn't read frame")
                
            logger.info("Camera setup successful")
            return cap
        except Exception as e:
            logger.error(f"Camera setup attempt {attempt+1} failed: {str(e)}")
            
            if attempt < retries - 1:
                logger.info(f"Waiting before retry {attempt+2}...")
                time.sleep(2)  # Wait before retrying
            else:
                logger.error(f"Failed to setup camera after {retries} attempts")
                return None

try:
    logger.info("Starting YOLO pose detection demo")
    
    # Track whether we're using video file or camera
    using_video_file = False
    cap = None
    
    if args.video and os.path.exists(args.video):
        logger.info(f"Using video file: {args.video}")
        cap = cv2.VideoCapture(args.video)
        using_video_file = True
        
        if not cap.isOpened():
            logger.error(f"Failed to open video file: {args.video}")
            print(f"Error: Could not open video file {args.video}", file=sys.stderr)
            sys.exit(1)
    else:
        if args.video:
            logger.warning(f"Video file not found: {args.video}")
            print(f"Warning: Video file {args.video} not found, trying camera instead", file=sys.stderr)
        
        logger.info("Setting up camera...")
        cap = setup_camera(retries=args.retry)
        
        if cap is None:
            logger.error("Camera setup failed, checking for fallback video")
            
            # Try to use an existing Video.mp4 as fallback
            fallback_video = os.path.join(os.path.dirname(__file__), "Video.mp4")
            if os.path.exists(fallback_video):
                logger.info(f"Using fallback video: {fallback_video}")
                cap = cv2.VideoCapture(fallback_video)
                using_video_file = True
                
                if not cap.isOpened():
                    logger.error("Failed to open fallback video")
                    print(f"Error: Camera unavailable and failed to open fallback video", file=sys.stderr)
                    sys.exit(1)
            else:
                logger.error("Camera unavailable and no fallback video found")
                print("Error: Camera is busy or unavailable. Please close any applications using the camera and try again.", file=sys.stderr)
                sys.exit(1)
    
    # Prepare results container
    results = {
        "source": args.video if using_video_file else "camera",
        "frames_processed": 0,
        "poses_detected": 0,
        "success": False
    }
    
    # YOLO model setup would go here
    logger.info("YOLO model setup would go here in a complete implementation")
    
    # Placeholder for pose detection results
    # In a real implementation, we would run the model here
    
    # Process frames
    frame_count = 0
    logger.info("Starting frame processing loop")
    
    while True:
        ret, frame = cap.read()
        
        if not ret:
            logger.info("End of video stream reached")
            break
            
        frame_count += 1
        results["frames_processed"] = frame_count
        
        # Here we would run pose detection on the frame
        # For this demonstration, we just display the frame
        cv2.imshow('YOLO Pose Detection', frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            logger.info("User quit the application")
            break
    
    # Cleanup
    logger.info(f"Processed {frame_count} frames")
    cap.release()
    cv2.destroyAllWindows()
    
    # Mark as successful
    results["success"] = True
    
    # Save results if output path specified
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(results, f)
        logger.info(f"Saved results to {args.output}")
    
    logger.info("YOLO pose detection completed successfully")
    print("YOLO pose detection completed successfully")
    
except KeyboardInterrupt:
    logger.info("Interrupted by user")
    print("Interrupted by user")
except Exception as e:
    logger.error(f"Error in YOLO pose detection: {str(e)}")
    print(f"Error in YOLO pose detection: {str(e)}", file=sys.stderr)
    sys.exit(1)
finally:
    # Ensure camera is released even if an exception occurs
    if 'cap' in locals() and cap is not None:
        logger.info("Releasing camera resources")
        cap.release()
        cv2.destroyAllWindows()