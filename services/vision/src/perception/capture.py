"""카메라 -> MediaPipe Hand Landmarker -> LandmarkFrame.

TODO(이동혁):
- cv2.VideoCapture로 프레임 읽기 (해상도/FPS는 03_인터페이스계약서_v1 §2 확정값 반영)
- mediapipe.solutions.hands 로 21 keypoints 추출
- shared/schemas/landmark_frame.schema.json 형식으로 반환
"""
