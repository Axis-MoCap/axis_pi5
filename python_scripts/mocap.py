import os
import shutil
import argparse
import pickle
import subprocess
import numpy as np
import cv2
import torch
import glob
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
    
    # Path to the blender model
    blend_path = os.path.join(script_dir, 'assets/skeleton.blend')
    FOV = np.pi / 3  # Field of view, set to 60 degrees
    
    # Create temporary directory for processing files
    tmp_dir = os.path.join(current_dir, 'tmp')
    os.makedirs(tmp_dir, exist_ok=True)
    
    # Ensure that the skeleton folder is already present
    skeleton_path = os.path.join(tmp_dir, 'skeleton')
    if not os.path.exists(skeleton_path):
        raise Exception(f"Skeleton export failed. Please ensure the skeleton is exported and placed in '{skeleton_path}'")
    
    # Open the video for frame-by-frame processing
    print(f"Opening video file: {video_path}")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise Exception(f"Video capture failed for '{video_path}'")
    
    # Get video properties
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_rate = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # Initialize body keypoint tracker
    body_keypoint_track = BodyKeypointTrack(
        im_width=frame_width,
        im_height=frame_height,
        fov=FOV,
        frame_rate=frame_rate,
        track_hands=True,
        smooth_range=10 * (1 / frame_rate),
        smooth_range_barycenter=30 * (1 / frame_rate),
    )
    
    # Initialize the skeleton IK solver
    skeleton_ik_solver = SkeletonIKSolver(
        model_path=skeleton_path,
        track_hands=False,
        smooth_range=15 * (1 / frame_rate),
    )
    
    # Data lists to store bone data
    bone_euler_sequence, scale_sequence, location_sequence = [], [], []
    
    # Time tracking
    frame_t = 0.0
    frame_i = 0
    bar = tqdm(total=total_frames, desc='Running...')
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Get 3D body keypoints
        body_keypoint_track.track(frame, frame_t)
        kpts3d, valid = body_keypoint_track.get_smoothed_3d_keypoints(frame_t)
        
        # Solve for the skeleton pose using IK
        skeleton_ik_solver.fit(torch.from_numpy(kpts3d).float(), torch.from_numpy(valid).bool(), frame_t)
        
        # Get smoothed pose data
        bone_euler = skeleton_ik_solver.get_smoothed_bone_euler(frame_t)
        location = skeleton_ik_solver.get_smoothed_location(frame_t)
        scale = skeleton_ik_solver.get_scale()
        
        # Append the data to the sequences
        bone_euler_sequence.append(bone_euler)
        location_sequence.append(location)
        scale_sequence.append(scale)
        
        # Show the keypoints on the frame (optional)
        show_annotation(frame, kpts3d, valid, body_keypoint_track.K)
        
        if cv2.waitKey(1) == 27:  # Exit if 'ESC' is pressed
            print('Cancelled by user. Exit.')
            exit()
        
        # Increment frame time
        frame_i += 1
        frame_t += 1.0 / frame_rate
        bar.update(1)
    
    # Save animation result as a pickle file
    print("Save animation result...")
    animation_data_path = os.path.join(tmp_dir, 'bone_animation_data.pkl')
    with open(animation_data_path, 'wb') as fp:
        pickle.dump({
            'fov': FOV,
            'frame_rate': frame_rate,
            'bone_names': skeleton_ik_solver.optimizable_bones,
            'bone_euler_sequence': bone_euler_sequence,
            'location_sequence': location_sequence,
            'scale': np.mean(scale_sequence),
            'all_bone_names': skeleton_ik_solver.all_bone_names
        }, fp)
    
    # Open Blender and apply the animation to the rigged model
    print("Open blender and apply animation...")
    apply_animation_script = os.path.join(script_dir, "apply_animation.py")
    if not os.path.exists(apply_animation_script):
        apply_animation_script = "apply_animation.py"
    proc = subprocess.Popen(f"blender {blend_path} --python {apply_animation_script}")
    proc.wait()

if __name__ == '__main__':
    main()
