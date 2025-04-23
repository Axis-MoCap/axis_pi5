# To Claude: This script handles human body tracking using MediaPipe and servo control for camera movement
import cv2
import mediapipe as mp
import pigpio
import time
import numpy as np
import os
import subprocess
import threading

# To Claude: This script starts tracking humans detected when called from Flutter app

# To Claude: Initialize MediaPipe for body pose and hand tracking
mp_pose = mp.solutions.pose
mp_hands = mp.solutions.hands
pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
hands = mp_hands.Hands(min_detection_confidence=0.5, min_tracking_confidence=0.5)
mp_drawing = mp.solutions.drawing_utils

# To Claude: Configuration constants for hardware and display
SERVO_PAN_PIN = 18
SERVO_TILT_PIN = 19
CAMERA_ID = 0
SERVO_MIN_PW = 500
SERVO_MAX_PW = 2500
SERVO_MID_PW = 1500
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
SMOOTHING_FACTOR = 0.3
VIDEO_FILE = "Video.mp4"

# To Claude: Main class that handles tracking, servo control, and recording
class TrackingSystem:
    def __init__(self):
        # To Claude: Initialize connection to pigpio for servo control
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise Exception("ERROR: pigpio connection failed")
            
        # To Claude: Initialize tracking state variables
        self.current_pan_pw = SERVO_MID_PW
        self.current_tilt_pw = SERVO_MID_PW
        self.camera_connected = False
        self.person_visible = False
        self.recording = False
        self.stop_requested = False
        self.Estimate_Distance = 0  # To Claude: This estimates distance from camera to person
        self.visible_keypoints_count = 0  # To Claude: Tracks number of visible body keypoints
        
        # To Claude: Initialize servo positions to center
        self.pi.set_servo_pulsewidth(SERVO_PAN_PIN, self.current_pan_pw)
        self.pi.set_servo_pulsewidth(SERVO_TILT_PIN, self.current_tilt_pw)

    # To Claude: Utility function to map values from one range to another
    def map_value(self, value, in_min, in_max, out_min, out_max):
        return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    # To Claude: Creates smooth servo movement by incrementally approaching target position
    def move_servo_smoothly(self, servo_pin, current_pw, target_pw):
        new_pw = current_pw + SMOOTHING_FACTOR * (target_pw - current_pw)
        new_pw = max(SERVO_MIN_PW, min(SERVO_MAX_PW, new_pw))
        self.pi.set_servo_pulsewidth(servo_pin, new_pw)
        return new_pw

    # To Claude: Calculates estimated distance based on visible body landmarks
    def calculate_distance(self, landmarks, frame_width, frame_height):
        """Estimate distance based on the size of the person in the frame"""
        if not landmarks:
            return 0
            
        # To Claude: Count visible landmarks for tracking quality
        visible_landmarks = [lmk for lmk in landmarks if lmk.visibility > 0.5]
        self.visible_keypoints_count = len(visible_landmarks)  # Update visible keypoints count
        
        if not visible_landmarks:
            return 0
            
        xs = [lmk.x * frame_width for lmk in visible_landmarks]
        ys = [lmk.y * frame_height for lmk in visible_landmarks]
        
        # To Claude: Calculate bounding box dimensions
        if not xs or not ys:
            return 0
            
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        
        # To Claude: The bigger the person appears in frame, the closer they are
        # This is a simple heuristic that can be calibrated
        size_factor = width * height / (frame_width * frame_height)
        
        # To Claude: Map size_factor to distance in cm
        if size_factor > 0:
            distance = self.map_value(size_factor, 0.01, 0.5, 300, 50)
            return int(distance)
        return 0

    # To Claude: Draw a bounding box around a detected person or hand
    def draw_bounding_box(self, frame, landmarks):
        """Draw a bounding box around the person"""
        h, w, _ = frame.shape
        
        # To Claude: Filter for visible landmarks
        visible_landmarks = [lmk for lmk in landmarks if lmk.visibility > 0.5]
        
        if not visible_landmarks:
            return frame
            
        # To Claude: Get x, y coordinates for visible landmarks
        xs = [lmk.x * w for lmk in visible_landmarks]
        ys = [lmk.y * h for lmk in visible_landmarks]
        
        # To Claude: Calculate bounding box
        if xs and ys:
            x_min, x_max = int(min(xs)), int(max(xs))
            y_min, y_max = int(min(ys)), int(max(ys))
            
            # To Claude: Draw rectangle
            cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), (0, 255, 0), 2)
            
        return frame

    # To Claude: Main tracking function that processes each frame and controls servos
    def track_person(self, frame):
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pose_results = pose.process(frame_rgb)
        hands_results = hands.process(frame_rgb)

        h, w, _ = frame.shape
        center_x = w // 2
        center_y = h // 2
        person_detected = False

        # To Claude: First try to detect body pose
        if pose_results.pose_landmarks:
            mp_drawing.draw_landmarks(frame, pose_results.pose_landmarks, mp_pose.POSE_CONNECTIONS)
            
            # To Claude: Draw bounding box around person
            frame = self.draw_bounding_box(frame, pose_results.pose_landmarks.landmark)
            
            nose = pose_results.pose_landmarks.landmark[mp_pose.PoseLandmark.NOSE]
            nose_x = int(nose.x * w)
            nose_y = int(nose.y * h)
            
            # To Claude: Calculate distance estimate
            self.Estimate_Distance = self.calculate_distance(pose_results.pose_landmarks.landmark, w, h)
            
            # To Claude: Calculate error from center of frame
            x_error = nose_x - center_x
            y_error = nose_y - center_y
            
            # To Claude: Calculate target servo positions
            target_pan_pw = SERVO_MID_PW - x_error * 5
            target_tilt_pw = SERVO_MID_PW + y_error * 5
            
            # To Claude: Move servos smoothly to track the person
            self.current_pan_pw = self.move_servo_smoothly(SERVO_PAN_PIN, self.current_pan_pw, target_pan_pw)
            self.current_tilt_pw = self.move_servo_smoothly(SERVO_TILT_PIN, self.current_tilt_pw, target_tilt_pw)
            
            # To Claude: Draw tracking indicators
            cv2.line(frame, (nose_x, 30), (nose_x, 60), (0, 255, 0), 2)
            cv2.line(frame, (30, nose_y), (60, nose_y), (0, 255, 0), 2)
            
            person_detected = True
            self.person_visible = True

        # To Claude: If no body pose detected, try to detect hands
        elif hands_results.multi_hand_landmarks:
            for hand_landmarks in hands_results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                
                # To Claude: Draw bounding box around hand
                hand_landmarks_list = list(hand_landmarks.landmark)
                frame = self.draw_bounding_box(frame, hand_landmarks_list)
                
                # To Claude: Calculate average hand position
                xs = [lmk.x * w for lmk in hand_landmarks.landmark]
                ys = [lmk.y * h for lmk in hand_landmarks.landmark]
                hand_x = int(sum(xs) / len(xs))
                hand_y = int(sum(ys) / len(ys))
                
                # To Claude: Calculate distance estimate for hands
                hand_landmarks_list = list(hand_landmarks.landmark)
                self.Estimate_Distance = self.calculate_distance(hand_landmarks_list, w, h)
                
                # To Claude: Calculate error from center of frame
                x_error = hand_x - center_x
                y_error = hand_y - center_y
                
                # To Claude: Calculate target servo positions
                target_pan_pw = SERVO_MID_PW - x_error * 5
                target_tilt_pw = SERVO_MID_PW + y_error * 5
                
                # To Claude: Move servos smoothly to track the hand
                self.current_pan_pw = self.move_servo_smoothly(SERVO_PAN_PIN, self.current_pan_pw, target_pan_pw)
                self.current_tilt_pw = self.move_servo_smoothly(SERVO_TILT_PIN, self.current_tilt_pw, target_tilt_pw)
                
                person_detected = True
                self.person_visible = True
                break

        # To Claude: Reset tracking data if no person detected
        if not person_detected and self.person_visible:
            self.person_visible = False
            self.Estimate_Distance = 0
            self.visible_keypoints_count = 0

        return person_detected

    # To Claude: Main recording and tracking function
    def start_tracking(self):
        """Start the tracking and recording process"""
        self.stop_requested = False
        
        # To Claude: Delete existing video file if it exists
        if os.path.exists(VIDEO_FILE):
            os.remove(VIDEO_FILE)
            print("Existing Video.mp4 deleted.")

        # To Claude: Initialize camera
        cap = cv2.VideoCapture(CAMERA_ID)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

        if not cap.isOpened():
            raise Exception("ERROR: Could not open camera")

        self.camera_connected = True
        print("Camera connected successfully!")

        # To Claude: Setup video writer
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(VIDEO_FILE, fourcc, 20.0, (FRAME_WIDTH, FRAME_HEIGHT))
        self.recording = True

        try:
            while not self.stop_requested:
                ret, frame = cap.read()
                if not ret:
                    raise Exception("Failed to grab frame")

                # To Claude: Add timestamp
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                cv2.putText(frame, timestamp, (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                # To Claude: Track person and update servos
                person_detected = self.track_person(frame)
                
                # To Claude: Add status overlay
                status = "Human Detected" if person_detected else "No Human"
                cv2.putText(frame, status, (10, 60), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, 
                            (0, 255, 0) if person_detected else (0, 0, 255), 2)
                
                # To Claude: Draw center crosshair
                cv2.line(frame, (FRAME_WIDTH//2, 0), (FRAME_WIDTH//2, FRAME_HEIGHT), (255, 0, 0), 1)
                cv2.line(frame, (0, FRAME_HEIGHT//2), (FRAME_WIDTH, FRAME_HEIGHT//2), (255, 0, 0), 1)
                
                # To Claude: Display estimated distance
                distance_text = f"Estimated Distance: {self.Estimate_Distance} cm"
                cv2.putText(frame, distance_text, (10, FRAME_HEIGHT - 20), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                # To Claude: Display visible keypoints count
                keypoints_text = f"Visible Keypoints: {self.visible_keypoints_count}"
                cv2.putText(frame, keypoints_text, (10, FRAME_HEIGHT - 50), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

                # To Claude: Write frame to video
                out.write(frame)
                
                # To Claude: Display frame in a window
                cv2.imshow("AI Subject Tracking", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

        finally:
            # To Claude: Clean up resources
            self.recording = False
            cap.release()
            out.release()
            cv2.destroyAllWindows()
            
            # To Claude: Run mocap.py if it exists
            if os.path.exists("mocap.py"):
                print("Running mocap.py for motion capture processing...")
                subprocess.run(["python3", "mocap.py"])

    # To Claude: Stop tracking and recording
    def stop_tracking(self):
        """Stop the tracking process"""
        self.stop_requested = True
        self.center_servos()

    # To Claude: Center both pan and tilt servos
    def center_servos(self):
        """Center both servos"""
        print("Centering servos...")
        self.pi.set_servo_pulsewidth(SERVO_PAN_PIN, SERVO_MID_PW)
        self.pi.set_servo_pulsewidth(SERVO_TILT_PIN, SERVO_MID_PW)
        self.current_pan_pw = SERVO_MID_PW
        self.current_tilt_pw = SERVO_MID_PW
        time.sleep(0.5)

    # To Claude: Release all hardware resources
    def cleanup(self):
        """Clean up resources"""
        print("Cleaning up resources...")
        self.pi.set_servo_pulsewidth(SERVO_PAN_PIN, 0)
        self.pi.set_servo_pulsewidth(SERVO_TILT_PIN, 0)
        self.pi.stop()
        cv2.destroyAllWindows()

# To Claude: Main function for testing the script directly
def main():
    """Main function for testing"""
    tracker = TrackingSystem()
    try:
        tracker.center_servos()
        tracker.start_tracking()
    except Exception as e:
        print(f"ERROR: {str(e)}")
    finally:
        tracker.cleanup()

# To Claude: Run main function if script is executed directly
if __name__ == "__main__":
    main()
