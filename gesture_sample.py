import cv2
import mediapipe as mp
import serial
import math

# Set up serial communication with the microcontroller (adjust the COM port and baud rate)
ser = serial.Serial('COM3', 9600)  # Replace 'COM3' with the correct COM port

# Set up MediaPipe Hands for gesture recognition
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(min_detection_confidence=0.8, min_tracking_confidence=0.8)
mp_draw = mp.solutions.drawing_utils

# Open the webcam
cap = cv2.VideoCapture(0)

def calculate_distance(point1, point2):
    """Calculate Euclidean distance between two points."""
    return math.dist(point1, point2)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break
    
    # Flip the frame for a mirror effect
    frame = cv2.flip(frame, 1)
    
    # Convert the image to RGB (MediaPipe works in RGB)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    # Process the image and detect hands
    results = hands.process(rgb_frame)
    
    gesture = "UNKNOWN"
    action = "NONE"
    
    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            # Get the positions of key points
            thumb_tip = hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP]
            index_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
            wrist = hand_landmarks.landmark[mp_hands.HandLandmark.WRIST]
            
            # Calculate distances
            thumb_index_distance = calculate_distance((thumb_tip.x, thumb_tip.y), (index_tip.x, index_tip.y))
            hand_depth = wrist.z  # Depth of the hand (relative to the camera)
            
            # Determine gesture based on thumb-index distance
            if thumb_index_distance < 0.08:
                gesture = "FIST"
                ser.write(b'A1')  # Close the claw (servo A)
                action = "Claw Closed"
            else:
                gesture = "OPEN"
                ser.write(b'A0')  # Open the claw (servo A)
                action = "Claw Opened"
            
            # Determine up/down motion based on hand depth
            if  thumb_index_distance >  0.15:
                ser.write(b'X0')  # Move arm down (servo X, Y)
                ser.write(b'Y0')
                action = "Arm Moving Down"
            elif thumb_index_distance < 0.15:
                ser.write(b'X1')  # Lift arm up (servo X, Y)
                ser.write(b'Y1')
                action = "Arm Lifting Up"
            
            # Determine left/right motion based on hand x-coordinate
            if wrist.x < 0.4:  # Left
                ser.write(b'Z0')  # Rotate arm left (servo Z)
                action = "Base Rotating Left"
            elif wrist.x > 0.6:  # Right
                ser.write(b'Z1')  # Rotate arm right (servo Z)
                action = "Base Rotating Right"
            
            # Draw hand landmarks
            mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
            
            # Display the detected action on the frame
            cv2.putText(frame, f"Gesture: {gesture}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(frame, f"Action: {action}", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
            # Print values to the terminal
            print(f"Gesture: {gesture}, Action: {action}, Distance: {thumb_index_distance:.2f}, Depth: {hand_depth:.2f}")

    # Display the frame
    cv2.imshow("Gesture Controlled Robotic Arm", frame)

    # Exit condition (press 'q' to quit)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release the webcam and close all windows
cap.release()
cv2.destroyAllWindows()
ser.close()
