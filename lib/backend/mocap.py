#!/usr/bin/env python3
# mocap.py - Motion Capture Processing Script for Axis Motion Capture System

import sys
import os
import argparse
import cv2
import mediapipe as mp
import pickle
import numpy as np
import time
from pathlib import Path

class MotionCaptureProcessor:
    def __init__(self):
        # Initialize MediaPipe Pose
        self.mp_pose = mp.solutions.pose
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles
        
        # Initialize the pose detector with tracking
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
    def process_video(self, video_path, output_path=None):
        """Process a video file and extract pose data"""
        if not os.path.exists(video_path):
            print(f"Error: Video file {video_path} does not exist", file=sys.stderr)
            return False
            
        # Get output path for pickle file
        if output_path is None:
            output_path = os.path.splitext(video_path)[0] + ".pkl"
            
        print(f"Processing video: {video_path}", file=sys.stderr)
        print(f"Output will be saved to: {output_path}", file=sys.stderr)
        
        # Open the video file
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            print(f"Error: Could not open video file {video_path}", file=sys.stderr)
            return False
            
        # Get video properties
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        print(f"Video resolution: {frame_width}x{frame_height}, FPS: {fps}, Total frames: {total_frames}", file=sys.stderr)
        
        # Data structure to store pose landmarks for each frame
        frames_data = []
        frame_count = 0
        start_time = time.time()
        
        # Process video frame by frame
        while cap.isOpened():
            ret, frame = cap.read()
            
            if not ret:
                break
                
            # Convert the BGR image to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Process the frame with MediaPipe
            results = self.pose.process(rgb_frame)
            
            # Extract landmarks if detected
            frame_data = {}
            if results.pose_landmarks:
                # Convert landmarks to a more manageable format
                landmarks = []
                for landmark in results.pose_landmarks.landmark:
                    landmarks.append({
                        'x': landmark.x,
                        'y': landmark.y,
                        'z': landmark.z,
                        'visibility': landmark.visibility
                    })
                
                frame_data['landmarks'] = landmarks
            else:
                frame_data['landmarks'] = None
                
            frames_data.append(frame_data)
            
            # Update progress
            frame_count += 1
            if frame_count % 30 == 0:
                elapsed_time = time.time() - start_time
                frames_per_second = frame_count / elapsed_time
                remaining_frames = total_frames - frame_count
                remaining_time = remaining_frames / frames_per_second if frames_per_second > 0 else 0
                
                print(f"Processed {frame_count}/{total_frames} frames ({frame_count/total_frames*100:.1f}%) - ETA: {remaining_time:.1f}s", file=sys.stderr)
        
        cap.release()
        
        # Save the data to a pickle file
        with open(output_path, 'wb') as f:
            pickle.dump({
                'video_path': video_path,
                'frame_width': frame_width,
                'frame_height': frame_height,
                'fps': fps,
                'total_frames': total_frames,
                'frames_data': frames_data
            }, f)
        
        print(f"Processing complete. Data saved to {output_path}", file=sys.stderr)
        return True
        
    def process_live_frame(self, frame):
        """Process a single frame for live display"""
        if frame is None:
            return None
            
        # Convert the BGR image to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Process the frame with MediaPipe
        results = self.pose.process(rgb_frame)
        
        # Convert RGB back to BGR for OpenCV display
        overlay_frame = cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2BGR)
        
        # Draw the pose landmarks on the frame
        if results.pose_landmarks:
            self.mp_drawing.draw_landmarks(
                overlay_frame,
                results.pose_landmarks,
                self.mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=self.mp_drawing_styles.get_default_pose_landmarks_style()
            )
            
        return overlay_frame
        
    def close(self):
        """Clean up resources"""
        self.pose.close()

def create_recorder(output_dir, width=640, height=480, fps=30):
    """Create a video recorder for the Pi 5 camera"""
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate unique filename based on timestamp
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    video_path = os.path.join(output_dir, f"mocap_{timestamp}.mp4")
    
    # Create VideoWriter
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # or 'avc1' for h264 (might need hardware acceleration)
    recorder = cv2.VideoWriter(video_path, fourcc, fps, (width, height))
    
    if not recorder.isOpened():
        print(f"Error: Could not create video writer for {video_path}", file=sys.stderr)
        return None, None
        
    return recorder, video_path

def main():
    parser = argparse.ArgumentParser(description='Process video for motion capture')
    parser.add_argument('--input', required=True, help='Input video file')
    parser.add_argument('--output', help='Output pickle file')
    
    args = parser.parse_args()
    
    processor = MotionCaptureProcessor()
    processor.process_video(args.input, args.output)
    processor.close()

if __name__ == "__main__":
    main() 