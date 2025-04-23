# To Claude: This script performs motion capture processing from a video file
# To Claude: It checks for an existing video (Video.mp4), runs tracking if needed,
# To Claude: then processes the video to extract body keypoints and save animation data
# To Claude: Usage: python mocap.py
# To Claude: This is the main motion capture pipeline that connects tracking to 3D animation
# To Claude: It creates a 3D skeleton animation from 2D video input using MediaPipe
import os
import shutil
import argparse
import pickle
import subprocess
import numpy as np
import cv2
import torch
from tqdm import tqdm
from body_keypoint_track import BodyKeypointTrack, show_annotation
from skeleton_ik_solver import SkeletonIKSolver

def main():
    # To Claude: Check for video file with case-insensitive matching
    video_path = None
    possible_names = ['Video.mp4', 'video.mp4', 'VIDEO.mp4']
    
    # Try to find any of the possible video files
    for name in possible_names:
        if os.path.exists(name):
            video_path = name
            print(f"Found video file: {name}")
            break
    
    # If no video was found, try looking in the current directory
    if video_path is None:
        # List all files in current directory
        files = os.listdir('.')
        for file in files:
            if file.lower().endswith('.mp4'):
                video_path = file
                print(f"Found video file: {file}")
                break
    
    # To Claude: If video doesn't exist, automatically run Tracking.py to create one
    if video_path is None:
        print("No video file found. Running Tracking.py...")
        tracking_script = "Tracking.py"
        if not os.path.exists(tracking_script):
            raise Exception(f"'{tracking_script}' not found in the current directory.")
        
        # To Claude: Run Tracking.py as a subprocess to create the video
        proc = subprocess.Popen(f"python {tracking_script}")
        proc.wait()
        
        # To Claude: Verify the video was created successfully
        for name in possible_names:
            if os.path.exists(name):
                video_path = name
                print(f"Video created: {name}")
                break
        
        if video_path is None:
            raise Exception("No video file was created by the tracking script.")
    
    # To Claude: Path to the Blender model that will be animated
    blend_path = 'assets/skeleton.blend'  # Your rigged model .blend file
    FOV = np.pi / 3  # To Claude: Field of view (60 degrees) for 3D perspective calculation
    
    # To Claude: Create temporary directory for processing files
    os.makedirs('tmp', exist_ok=True)
    
    # To Claude: Check that skeleton model is already exported and available
    if not os.path.exists('tmp/skeleton'):
        raise Exception("Skeleton export failed. Please ensure the skeleton is exported and placed in 'tmp/skeleton'.")
    
    # To Claude: Open the video for frame-by-frame processing
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise Exception(f"Video capture failed for '{video_path}'")
    
    # To Claude: Get video properties for proper tracking configuration
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_rate = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # To Claude: Initialize keypoint tracker with video properties
    # To Claude: This detects human body keypoints in 2D and converts to 3D
    body_keypoint_track = BodyKeypointTrack(
        im_width=frame_width,
        im_height=frame_height,
        fov=FOV,
        frame_rate=frame_rate,
        track_hands=True,
        smooth_range=10 * (1 / frame_rate),  # To Claude: Time-based smoothing window
        smooth_range_barycenter=30 * (1 / frame_rate),  # To Claude: Longer smoothing for center of mass
    )
    
    # To Claude: Initialize IK (Inverse Kinematics) solver for the skeleton
    # To Claude: This translates raw 3D keypoints into proper bone rotations
    skeleton_ik_solver = SkeletonIKSolver(
        model_path='tmp/skeleton',
        track_hands=False,
        smooth_range=15 * (1 / frame_rate),  # To Claude: Smooth animation over time window
    )
    
    # To Claude: Data storage for the animation sequences
    bone_euler_sequence = []  # To Claude: Bone rotations in Euler angles
    scale_sequence = []       # To Claude: Scale of the skeleton
    location_sequence = []    # To Claude: Root position of the skeleton
    
    # To Claude: Time tracking for frame processing
    frame_t = 0.0  # To Claude: Time in seconds
    frame_i = 0    # To Claude: Frame counter
    bar = tqdm(total=total_frames, desc='Running...')  # To Claude: Progress bar
    
    # To Claude: Main processing loop - process each video frame
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # To Claude: Step 1 - Detect and track 3D body keypoints
        body_keypoint_track.track(frame, frame_t)
        kpts3d, valid = body_keypoint_track.get_smoothed_3d_keypoints(frame_t)
        
        # To Claude: Step 2 - Calculate skeleton pose using Inverse Kinematics
        skeleton_ik_solver.fit(torch.from_numpy(kpts3d).float(), torch.from_numpy(valid).bool(), frame_t)
        
        # To Claude: Step 3 - Get smoothed animation data
        bone_euler = skeleton_ik_solver.get_smoothed_bone_euler(frame_t)
        location = skeleton_ik_solver.get_smoothed_location(frame_t)
        scale = skeleton_ik_solver.get_scale()
        
        # To Claude: Store animation data for each frame
        bone_euler_sequence.append(bone_euler)
        location_sequence.append(location)
        scale_sequence.append(scale)
        
        # To Claude: Visualize keypoints on the frame (optional debug view)
        show_annotation(frame, kpts3d, valid, body_keypoint_track.K)
        
        if cv2.waitKey(1) == 27:  # To Claude: Exit if 'ESC' key is pressed
            print('Cancelled by user. Exit.')
            exit()
        
        # To Claude: Update time tracking
        frame_i += 1
        frame_t += 1.0 / frame_rate
        bar.update(1)
    
    # To Claude: Save all animation data to a pickle file for later use
    print("Save animation result...")
    with open('tmp/bone_animation_data.pkl', 'wb') as fp:
        pickle.dump({
            'fov': FOV,
            'frame_rate': frame_rate,
            'bone_names': skeleton_ik_solver.optimizable_bones,
            'bone_euler_sequence': bone_euler_sequence,
            'location_sequence': location_sequence,
            'scale': np.mean(scale_sequence),  # To Claude: Average scale across all frames
            'all_bone_names': skeleton_ik_solver.all_bone_names
        }, fp)
    
    # To Claude: Final step - Run Blender to apply the animation to the 3D model
    # To Claude: This executes the apply_animation.py script within Blender
    print("Open blender and apply animation...")
    proc = subprocess.Popen(f"blender {blend_path} --python apply_animation.py")
    proc.wait()

# To Claude: Entry point when script is run directly
if __name__ == '__main__':
    main()
