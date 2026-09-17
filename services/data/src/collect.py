"""웹캠 촬영 -> MediaPipe 랜드마크 추출 -> datasets/ 저장.

담당: 김지훈
04_데이터셋명세서_v1.md §6 폴더 구조안(datasets/raw/{class_name}/{subject_id}_{index}.jpg) 기준.

TODO(김지훈):
- argparse로 --class-name, --subject-id 입력받기
- cv2.VideoCapture로 촬영, mediapipe로 21 keypoints 추출
- 원본은 datasets/raw/, 랜드마크 시퀀스는 datasets/processed/ 에 저장
- subject-wise split을 위해 subject_id를 파일명에 항상 포함
"""

if __name__ == "__main__":
    raise NotImplementedError("촬영 스크립트 구현 예정 - 04_데이터셋명세서_v1 §3 촬영 프로토콜 확정 후 작성")
