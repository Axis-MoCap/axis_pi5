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

# Add the current directory to the Python path to ensure all modules can be found
current_dir = os.getcwd()
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from tqdm import tqdm
try:
    from body_keypoint_track import BodyKeypointTrack, show_annotation
    from skeleton_ik_solver import SkeletonIKSolver
except ImportError:
    # Try with full paths if modules not found
    module_path = os.path.join(script_dir)
    sys.path.insert(0, module_path)
    from body_keypoint_track import BodyKeypointTrack, show_annotation
    from skeleton_ik_solver import SkeletonIKSolver

def main():
    # Print the current working directory to help with debugging
    print(f"Current working directory: {current_dir}")
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
    FOV = np.pi / 3  # Field of view, set to 60 degrees
    
    # Create temporary directory for processing files
    tmp_dir = os.path.join(current_dir, 'tmp')
    os.makedirs(tmp_dir, exist_ok=True)
    print(f"Created tmp directory: {tmp_dir}")
    
    # Ensure that the skeleton folder is already present
    skeleton_path = os.path.join(tmp_dir, 'skeleton')
    if not os.path.exists(skeleton_path):
        print(f"ERROR: Skeleton directory not found at {skeleton_path}")
        print(f"Creating skeleton directory...")
        os.makedirs(skeleton_path, exist_ok=True)
        
        # Look for skeleton files in python_scripts/tmp/skeleton
        source_skeleton_dir = os.path.join(script_dir, 'tmp', 'skeleton')
        if os.path.exists(source_skeleton_dir):
            print(f"Copying skeleton files from {source_skeleton_dir}...")
            skeleton_files = ['skeleton.json', 'bone_matrix_rel.npy', 'bone_matrix_world.npy']
            for file in skeleton_files:
                src_file = os.path.join(source_skeleton_dir, file)
                if os.path.exists(src_file):
                    dst_file = os.path.join(skeleton_path, file)
                    shutil.copy2(src_file, dst_file)
                    print(f"Copied {file} to {skeleton_path}")
        else:
            print(f"WARNING: No skeleton files found in {source_skeleton_dir}")
            
        # Check if we have skeleton files in lib/Backend/tmp/skeleton
        backend_skeleton_dir = os.path.join(current_dir, 'lib', 'Backend', 'tmp', 'skeleton')
        if os.path.exists(backend_skeleton_dir):
            print(f"Copying skeleton files from {backend_skeleton_dir}...")
            skeleton_files = ['skeleton.json', 'bone_matrix_rel.npy', 'bone_matrix_world.npy']
            for file in skeleton_files:
                src_file = os.path.join(backend_skeleton_dir, file)
                if os.path.exists(src_file):
                    dst_file = os.path.join(skeleton_path, file)
                    shutil.copy2(src_file, dst_file)
                    print(f"Copied {file} to {skeleton_path}")
        
        # Check if we have skeleton files in lib/Backend/DuoRecord/tmp/skeleton or lib/Backend/TrioRecord/tmp/skeleton
        other_skeleton_dirs = [
            os.path.join(current_dir, 'lib', 'Backend', 'DuoRecord', 'tmp', 'skeleton'),
            os.path.join(current_dir, 'lib', 'Backend', 'TrioRecord', 'tmp', 'skeleton')
        ]
        
        for dir_path in other_skeleton_dirs:
            if os.path.exists(dir_path):
                print(f"Copying skeleton files from {dir_path}...")
                skeleton_files = ['skeleton.json', 'bone_matrix_rel.npy', 'bone_matrix_world.npy']
                for file in skeleton_files:
                    src_file = os.path.join(dir_path, file)
                    if os.path.exists(src_file):
                        dst_file = os.path.join(skeleton_path, file)
                        shutil.copy2(src_file, dst_file)
                        print(f"Copied {file} to {skeleton_path}")
                break
        
        # Check if we now have the skeleton files
        required_files = ['skeleton.json', 'bone_matrix_rel.npy', 'bone_matrix_world.npy']
        missing_files = [f for f in required_files if not os.path.exists(os.path.join(skeleton_path, f))]
        
        if missing_files:
            print(f"ERROR: Missing skeleton files: {missing_files}")
            print(f"Please ensure skeleton model files are copied to this directory before proceeding.")
            sys.stdout.flush()
        else:
            print(f"All skeleton files are in place.")
    else:
        print(f"Found skeleton directory: {skeleton_path}")
        
        # Verify skeleton files exist
        required_files = ['skeleton.json', 'bone_matrix_rel.npy', 'bone_matrix_world.npy']
        missing_files = [f for f in required_files if not os.path.exists(os.path.join(skeleton_path, f))]
        
        if missing_files:
            print(f"ERROR: Missing skeleton files: {missing_files}")
            print(f"Attempting to copy from other locations...")
            
            # Try copying from python_scripts/tmp/skeleton
            source_skeleton_dir = os.path.join(script_dir, 'tmp', 'skeleton')
            if os.path.exists(source_skeleton_dir):
                for file in missing_files:
                    src_file = os.path.join(source_skeleton_dir, file)
                    if os.path.exists(src_file):
                        dst_file = os.path.join(skeleton_path, file)
                        shutil.copy2(src_file, dst_file)
                        print(f"Copied {file} to {skeleton_path}")
            
            # Try other locations too
            other_dirs = [
                os.path.join(current_dir, 'lib', 'Backend', 'tmp', 'skeleton'),
                os.path.join(current_dir, 'lib', 'Backend', 'DuoRecord', 'tmp', 'skeleton'),
                os.path.join(current_dir, 'lib', 'Backend', 'TrioRecord', 'tmp', 'skeleton')
            ]
            
            for dir_path in other_dirs:
                if os.path.exists(dir_path):
                    for file in missing_files:
                        src_file = os.path.join(dir_path, file)
                        if os.path.exists(src_file):
                            dst_file = os.path.join(skeleton_path, file)
                            shutil.copy2(src_file, dst_file)
                            print(f"Copied {file} to {skeleton_path}")
            
            # Check if we still have missing files
            missing_files = [f for f in required_files if not os.path.exists(os.path.join(skeleton_path, f))]
            if missing_files:
                print(f"ERROR: Still missing skeleton files after copying attempt: {missing_files}")
            else:
                print(f"All skeleton files are now in place.")
    
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
            smooth_range=10 * (1 / frame_rate),
            smooth_range_barycenter=30 * (1 / frame_rate),
        )
        
        # Initialize the skeleton IK solver
        print("Initializing skeleton IK solver...")
        sys.stdout.flush()
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
        print("Beginning motion capture processing...")
        sys.stdout.flush()
        bar = tqdm(total=total_frames, desc='Processing frames')
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print(f"End of video reached after {frame_i} frames")
                break
            
            if frame_i % 10 == 0:  # Update progress less frequently
                print(f"Processing frame {frame_i}/{total_frames}")
                sys.stdout.flush()
            
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
                break
            
            # Increment frame time
            frame_i += 1
            frame_t += 1.0 / frame_rate
            bar.update(1)
        
        cap.release()
        print(f"Video processing complete. Processed {frame_i} frames.")
        
        # Save animation result as a pickle file
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
                'scale': np.mean(scale_sequence),
                'all_bone_names': skeleton_ik_solver.all_bone_names
            }, fp)
        print(f"Animation data saved to {animation_data_path}")
        
        # Open Blender and apply the animation to the rigged model
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

if __name__ == '__main__':
    main()
