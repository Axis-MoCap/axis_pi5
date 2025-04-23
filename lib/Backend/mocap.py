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
import glob
import sys
from tqdm import tqdm
from body_keypoint_track import BodyKeypointTrack, show_annotation
from skeleton_ik_solver import SkeletonIKSolver

def main():
    # Print the current working directory to help with debugging
    current_dir = os.getcwd()
    print(f"Current working directory: {current_dir}")
    
    # Get the directory where the script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"Script directory: {script_dir}")
    
    # Look for video files in both current directory and script directory
    video_path = None
    possible_names = ['Video.mp4', 'video.mp4', 'VIDEO.mp4']
    
    # List all MP4 files in current directory and script directory
    print("Listing all MP4 files in current directory:")
    all_mp4_files = glob.glob(os.path.join(current_dir, "*.mp4"))
    for mp4_file in all_mp4_files:
        print(f"  Found MP4: {mp4_file}")
    
    if script_dir != current_dir:
        print("Listing all MP4 files in script directory:")
        script_mp4_files = glob.glob(os.path.join(script_dir, "*.mp4"))
        for mp4_file in script_mp4_files:
            print(f"  Found MP4: {mp4_file}")
        all_mp4_files.extend(script_mp4_files)
    
    # Try to find any of the possible video files in current directory
    for name in possible_names:
        # Check in current directory
        if os.path.exists(os.path.join(current_dir, name)):
            video_path = os.path.join(current_dir, name)
            print(f"Found video file in current directory: {video_path}")
            break
        
        # Check in script directory if different
        if script_dir != current_dir and os.path.exists(os.path.join(script_dir, name)):
            video_path = os.path.join(script_dir, name)
            print(f"Found video file in script directory: {video_path}")
            break
    
    # If still no video found, use the first MP4 file found
    if video_path is None and all_mp4_files:
        video_path = all_mp4_files[0]
        print(f"Using first available MP4 file: {video_path}")
    
    # If still no video, run Tracking.py
    if video_path is None:
        print("No video file found. Running Tracking.py...")
        tracking_script = os.path.join(script_dir, "Tracking.py")
        if not os.path.exists(tracking_script):
            tracking_script = "Tracking.py"
            if not os.path.exists(tracking_script):
                raise Exception(f"Tracking.py not found in either {script_dir} or {current_dir}")
        
        print(f"Running tracking script: {tracking_script}")
        proc = subprocess.Popen(f"python {tracking_script}")
        proc.wait()
        
        # Check again for video files after running Tracking.py
        for name in possible_names:
            if os.path.exists(os.path.join(current_dir, name)):
                video_path = os.path.join(current_dir, name)
                print(f"Video created in current directory: {video_path}")
                break
            elif script_dir != current_dir and os.path.exists(os.path.join(script_dir, name)):
                video_path = os.path.join(script_dir, name)
                print(f"Video created in script directory: {video_path}")
                break
        
        if video_path is None:
            # Final attempt - check for any new MP4 files
            new_mp4_files = glob.glob(os.path.join(current_dir, "*.mp4"))
            if script_dir != current_dir:
                new_mp4_files.extend(glob.glob(os.path.join(script_dir, "*.mp4")))
            
            for mp4_file in new_mp4_files:
                if mp4_file not in all_mp4_files:
                    video_path = mp4_file
                    print(f"Found newly created video file: {video_path}")
                    break
        
        if video_path is None:
            raise Exception("No video file was created by the tracking script.")
    
    # Confirm video was found
    print(f"CONFIRMED: Using video file: {video_path}")
    print(f"Video exists check: {os.path.exists(video_path)}")
    
    # Path to the blender model
    blend_path = os.path.join(script_dir, 'assets/skeleton.blend')
    print(f"Blender model path: {blend_path}")
    FOV = np.pi / 3
    
    # Create temporary directory for processing files
    tmp_dir = os.path.join(current_dir, 'tmp')
    os.makedirs(tmp_dir, exist_ok=True)
    print(f"Created tmp directory: {tmp_dir}")
    
    # Check that skeleton model is already exported and available
    skeleton_path = os.path.join(tmp_dir, 'skeleton')
    if not os.path.exists(skeleton_path):
        print(f"ERROR: Skeleton directory not found at {skeleton_path}")
        print(f"Creating skeleton directory...")
        os.makedirs(skeleton_path, exist_ok=True)
        print(f"Please ensure skeleton model files are copied to this directory before proceeding.")
        sys.stdout.flush()
    else:
        print(f"Found skeleton directory: {skeleton_path}")
    
    # Open the video for frame-by-frame processing
    print(f"Opening video file: {video_path}")
    sys.stdout.flush()
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"ERROR: Failed to open video: {video_path}")
        # Try with VideoCapture(0) as fallback for webcam
        print("Attempting to open default camera...")
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            raise Exception(f"Video capture failed for '{video_path}' and no webcam available.")
    
    # Get video properties
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_rate = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    print(f"Video properties: {frame_width}x{frame_height} @ {frame_rate}fps, {total_frames} frames")
    sys.stdout.flush()
    
    try:
        # Initialize body keypoint tracker
        print("Initializing body keypoint tracker...")
        sys.stdout.flush()
        body_keypoint_track = BodyKeypointTrack(
            im_width=frame_width,
            im_height=frame_height,
            fov=FOV,
            frame_rate=frame_rate,
            track_hands=True,
            smooth_range=10 * (1 / frame_rate),  # Time-based smoothing window
            smooth_range_barycenter=30 * (1 / frame_rate),  # Longer smoothing for center of mass
        )
        
        # Initialize IK (Inverse Kinematics) solver for the skeleton
        print("Initializing skeleton IK solver...")
        sys.stdout.flush()
        skeleton_ik_solver = SkeletonIKSolver(
            model_path=skeleton_path,
            track_hands=False,
            smooth_range=15 * (1 / frame_rate),  # Smooth animation over time window
        )
        
        # Data storage for the animation sequences
        bone_euler_sequence = []  # Bone rotations in Euler angles
        scale_sequence = []       # Scale of the skeleton
        location_sequence = []    # Root position of the skeleton
        
        # Time tracking for frame processing
        frame_t = 0.0  # Time in seconds
        frame_i = 0    # Frame counter
        print("Beginning motion capture processing...")
        sys.stdout.flush()
        bar = tqdm(total=total_frames, desc='Processing frames')
        
        # Main processing loop - process each video frame
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print(f"End of video reached after {frame_i} frames")
                break
            
            if frame_i % 10 == 0:  # Update progress less frequently
                print(f"Processing frame {frame_i}/{total_frames}")
                sys.stdout.flush()
            
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Step 1 - Detect and track 3D body keypoints
            body_keypoint_track.track(frame, frame_t)
            kpts3d, valid = body_keypoint_track.get_smoothed_3d_keypoints(frame_t)
            
            # Step 2 - Calculate skeleton pose using Inverse Kinematics
            skeleton_ik_solver.fit(torch.from_numpy(kpts3d).float(), torch.from_numpy(valid).bool(), frame_t)
            
            # Step 3 - Get smoothed animation data
            bone_euler = skeleton_ik_solver.get_smoothed_bone_euler(frame_t)
            location = skeleton_ik_solver.get_smoothed_location(frame_t)
            scale = skeleton_ik_solver.get_scale()
            
            # Store animation data for each frame
            bone_euler_sequence.append(bone_euler)
            location_sequence.append(location)
            scale_sequence.append(scale)
            
            # Visualize keypoints on the frame (optional debug view)
            show_annotation(frame, kpts3d, valid, body_keypoint_track.K)
            
            if cv2.waitKey(1) == 27:  # Exit if 'ESC' key is pressed
                print('Cancelled by user. Exit.')
                break
            
            # Update time tracking
            frame_i += 1
            frame_t += 1.0 / frame_rate
            bar.update(1)
        
        cap.release()
        print(f"Video processing complete. Processed {frame_i} frames.")
        
        # Save all animation data to a pickle file for later use
        print("Saving animation result...")
        sys.stdout.flush()
        animation_data_path = os.path.join(tmp_dir, 'bone_animation_data.pkl')
        with open(animation_data_path, 'wb') as fp:
            pickle.dump({
                'fov': FOV,
                'frame_rate': frame_rate,
                'bone_names': skeleton_ik_solver.optimizable_bones,
                'bone_euler_sequence': bone_euler_sequence,
                'location_sequence': location_sequence,
                'scale': np.mean(scale_sequence),  # Average scale across all frames
                'all_bone_names': skeleton_ik_solver.all_bone_names
            }, fp)
        print(f"Animation data saved to {animation_data_path}")
        
        # Final step - Run Blender to apply the animation to the 3D model
        # This executes the apply_animation.py script within Blender
        print("Opening Blender to apply animation...")
        sys.stdout.flush()
        apply_animation_script = os.path.join(script_dir, "apply_animation.py")
        if not os.path.exists(apply_animation_script):
            apply_animation_script = "apply_animation.py"
            if not os.path.exists(apply_animation_script):
                print(f"WARNING: Could not find apply_animation.py script in {script_dir} or {current_dir}")
        
        print(f"Running: blender {blend_path} --python {apply_animation_script}")
        proc = subprocess.Popen(f"blender {blend_path} --python {apply_animation_script}")
        proc.wait()
        print("Blender process completed.")
    
    except Exception as e:
        print(f"ERROR in motion capture processing: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if cap.isOpened():
            cap.release()
        cv2.destroyAllWindows()
        print("Motion capture process finished.")

# To Claude: Entry point when script is run directly
if __name__ == '__main__':
    main()
