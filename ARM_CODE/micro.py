import cv2
import mediapipe as mp
import numpy as np
import time
import serial

SIMULATE_SERIAL = False  # Set to True for testing without the microcontroller or set to false

if not SIMULATE_SERIAL:
    ser = serial.Serial('COM7', 19200)  # Replace with your actual port
    ser.flushInput()
else:
    class DummySerial:
        def write(self, data):
            print("Simulated write:", data.decode('utf-8').strip())
        def flush(self):
            pass
        def flushInput(self):
            pass
    ser = DummySerial()

#############################################
# MediaPipe and Global Variables set-up     #
#############################################
mp_drawing = mp.solutions.drawing_utils
mp_hands = mp.solutions.hands

# Servo activation flags and time tracker
left_servo_active = False
right_servo_active = False
last_hand_time = time.time()

# Initial calibrated servo angles
servo_angles = {
    'gripper': 40,  # This initial value will be updated based on hand gestures.
    'base': 90,
    'right_arm': 0,
    'left_arm': 150
}
last_servo_angles = servo_angles.copy()

# Gripper angles calibration 
GRIPPER_OPEN_ANGLE = 130
GRIPPER_CLOSED_ANGLE = 0

# State variable for gripper
gripper_state = 'open'

#########################################
# Helper Functions                      #
#########################################
def send_servo_angles():
    global last_servo_angles
    if servo_angles != last_servo_angles:
        # Prepare the angle string (order: gripper, base, right_arm, left_arm)
        angles = f"{servo_angles['gripper']},{servo_angles['base']},{servo_angles['right_arm']},{servo_angles['left_arm']}\n"
        ser.write(angles.encode('utf-8'))
        ser.flush()
        last_servo_angles = servo_angles.copy()

def smooth_movement(current_angle, target_angle, step=5):
    """
    Smoothly move a servo from the current angle toward the target angle.
    """
    if current_angle < target_angle:
        current_angle += step
        if current_angle > target_angle:
            current_angle = target_angle
    elif current_angle > target_angle:
        current_angle -= step
        if current_angle < target_angle:
            current_angle = target_angle
    return current_angle

def is_hand_closed(landmarks):
    """
    Original method for detecting a closed hand (not used in the new gripper logic).
    """
    folded_fingers = 0
    tips_ids = [
        mp_hands.HandLandmark.THUMB_TIP,
        mp_hands.HandLandmark.INDEX_FINGER_TIP,
        mp_hands.HandLandmark.MIDDLE_FINGER_TIP,
        mp_hands.HandLandmark.RING_FINGER_TIP,
        mp_hands.HandLandmark.PINKY_TIP
    ]
    mcp_ids = [
        mp_hands.HandLandmark.THUMB_MCP,
        mp_hands.HandLandmark.INDEX_FINGER_MCP,
        mp_hands.HandLandmark.MIDDLE_FINGER_MCP,
        mp_hands.HandLandmark.RING_FINGER_MCP,
        mp_hands.HandLandmark.PINKY_MCP
    ]
    for tip_id, mcp_id in zip(tips_ids, mcp_ids):
        if landmarks[tip_id].y > landmarks[mcp_id].y:
            folded_fingers += 1
    return folded_fingers >= 3

def fingers_up(landmarks):
    """
    Determine which fingers are up.
    """
    fingers = []
    tips_ids = [mp_hands.HandLandmark.THUMB_TIP,
                mp_hands.HandLandmark.INDEX_FINGER_TIP,
                mp_hands.HandLandmark.MIDDLE_FINGER_TIP,
                mp_hands.HandLandmark.RING_FINGER_TIP,
                mp_hands.HandLandmark.PINKY_TIP]

    # Thumb check (using x-coordinate as reference)
    if landmarks[tips_ids[0]].x < landmarks[mp_hands.HandLandmark.WRIST].x:
        fingers.append(1)
    else:
        fingers.append(0)

    # Other fingers (using y-coordinate comparisons)
    for id in range(1, 5):
        if landmarks[tips_ids[id]].y < landmarks[tips_ids[id] - 2].y:
            fingers.append(1)
        else:
            fingers.append(0)
    return fingers

#########################################
# Main Function                         #
#########################################
def main():
    global left_servo_active, right_servo_active, last_hand_time
    global gripper_state
    cap = cv2.VideoCapture(0)
    
    # Set the camera resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    with mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.7) as hands:
        # Initialize each servo by sending starting positions
        for servo in ['gripper', 'base', 'right_arm', 'left_arm']:
            send_servo_angles()
            time.sleep(0.01)
    
        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                print("Ignoring empty camera frame.")
                continue
            
            frame = cv2.flip(frame, 1)  # Mirror the frame
            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            gray_image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            gray_image_bgr = cv2.cvtColor(gray_image, cv2.COLOR_GRAY2BGR)
    
            # Process the image to detect hand landmarks
            results = hands.process(image)
            current_time = time.time()
    
            if results.multi_hand_landmarks:
                last_hand_time = current_time  # Reset timer when a hand is detected
                
                for hand_landmarks, hand_classification in zip(results.multi_hand_landmarks, results.multi_handedness):
                    hand_label = hand_classification.classification[0].label  # 'Left' or 'Right'
                    mp_drawing.draw_landmarks(gray_image_bgr, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                    
                    landmarks = hand_landmarks.landmark
                    h, w, _ = frame.shape
    
                    # Normalize coordinates for center position using wrist and index finger MCP
                    wrist = landmarks[mp_hands.HandLandmark.WRIST]
                    index_finger_mcp = landmarks[mp_hands.HandLandmark.INDEX_FINGER_MCP]
                    hand_center_x = int((wrist.x + index_finger_mcp.x) * w / 2)
                    hand_center_y = int((wrist.y + index_finger_mcp.y) * h / 2)
    
                    # Process right-hand gestures only
                    if hand_label == 'Right':
                        # --- Draw blue triangle connecting thumb landmark #1 (THUMB_CMC), index finger tip, and pinky tip ---
                        thumb_cmc = landmarks[mp_hands.HandLandmark.THUMB_CMC]  # landmark #1
                        index_tip = landmarks[mp_hands.HandLandmark.INDEX_FINGER_TIP]
                        pinky_tip = landmarks[mp_hands.HandLandmark.PINKY_TIP]
    
                        thumb_coords = (int(thumb_cmc.x * w), int(thumb_cmc.y * h))
                        index_coords = (int(index_tip.x * w), int(index_tip.y * h))
                        pinky_coords = (int(pinky_tip.x * w), int(pinky_tip.y * h))
    
                        pts = np.array([thumb_coords, index_coords, pinky_coords], np.int32)
                        pts = pts.reshape((-1, 1, 2))
                        cv2.polylines(gray_image_bgr, [pts], isClosed=True, color=(255, 0, 0), thickness=2)
    
                        # --- Calculate the area of the triangle using the shoelace formula ---
                        x1, y1 = thumb_coords
                        x2, y2 = index_coords
                        x3, y3 = pinky_coords
                        triangle_area = abs(x1*(y2 - y3) + x2*(y3 - y1) + x3*(y1 - y2)) / 2
                        
                        # Compute the centroid to display the area text near the triangle
                        cx = int((x1 + x2 + x3) / 3)
                        cy = int((y1 + y2 + y3) / 3)
                        cv2.putText(gray_image_bgr, f"Area: {triangle_area:.1f}", (cx, cy),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
                        # --- New Gripper Control Logic Based on Triangle Area ---
                        # If the area is above 8000 set the gripper to 130 (open)
                        # If the area is below 3000 set the gripper to 0 (closed)
                        if triangle_area > 8000:
                            if gripper_state != 'open':
                                servo_angles['gripper'] = GRIPPER_OPEN_ANGLE
                                gripper_state = 'open'
                                print("Gripper opened at angle", GRIPPER_OPEN_ANGLE)
                        elif triangle_area < 3000:
                            if gripper_state != 'closed':
                                servo_angles['gripper'] = GRIPPER_CLOSED_ANGLE
                                gripper_state = 'closed'
                                print("Gripper closed at angle", GRIPPER_CLOSED_ANGLE)
    
                        # --- Base Rotation based on horizontal hand position ---
                        if hand_center_x < w * 0.3:
                            servo_angles['base'] = smooth_movement(servo_angles['base'], 1)
                        elif hand_center_x > w * 0.7:
                            servo_angles['base'] = smooth_movement(servo_angles['base'], 179)
    
                        # --- Arm Joint Control based on vertical hand position ---
                        if right_servo_active:
                            if hand_center_y < h * 0.4:
                                servo_angles['right_arm'] = smooth_movement(servo_angles['right_arm'], 90)
                            elif hand_center_y > h * 0.6:
                                servo_angles['right_arm'] = smooth_movement(servo_angles['right_arm'], 0)
                        elif left_servo_active:
                            if hand_center_y < h * 0.4:
                                servo_angles['left_arm'] = smooth_movement(servo_angles['left_arm'], 95)
                            elif hand_center_y > h * 0.6:
                                servo_angles['left_arm'] = smooth_movement(servo_angles['left_arm'], 180)
    
                        send_servo_angles()
                        print(f"Current servo angles: {servo_angles}")
    
                    # Process left-hand gestures (no triangle drawn here)
                    elif hand_label == 'Left':
                        up_fingers = fingers_up(landmarks)
                        if up_fingers[1] == 1 and up_fingers[2] == 0:
                            left_servo_active = True
                            right_servo_active = False
                        elif up_fingers[1] == 1 and up_fingers[2] == 1:
                            right_servo_active = True
                            left_servo_active = False
    
                # Display which servo is active
                if left_servo_active:
                    cv2.putText(gray_image_bgr, "Left Servo Active", (10, h - 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
                elif right_servo_active:
                    cv2.putText(gray_image_bgr, "Right Servo Active", (10, h - 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
            else:
                if current_time - last_hand_time > 20:
                    default_positions = {
                        'gripper': 40,
                        'base': 90,
                        'right_arm': 0,
                        'left_arm': 150
                    }
                    for servo in default_positions:
                        while servo_angles[servo] != default_positions[servo]:
                            servo_angles[servo] = smooth_movement(servo_angles[servo], default_positions[servo], step=1)
                            send_servo_angles()
                            time.sleep(0.05)
    
            # Display servo angles on the frame
            cv2.putText(gray_image_bgr, f"Gripper Angle: {servo_angles['gripper']}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(gray_image_bgr, f"Base Angle: {servo_angles['base']}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(gray_image_bgr, f"Right Arm Angle: {servo_angles['right_arm']}", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(gray_image_bgr, f"Left Arm Angle: {servo_angles['left_arm']}", (10, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    
            cv2.imshow('Gesture Controlled Robotic Arm', gray_image_bgr)
    
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
