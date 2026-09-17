"""촬영 -> MediaPipe 랜드마크 추출 -> datasets/ 저장 (오프라인 학습 데이터 수집 전용).

담당: 김지훈
04_데이터셋명세서_v2.md §6 폴더 구조안(datasets/raw/{class_name}/{subject_id}_{index}.jpg) 기준.
이 스크립트로 모은 데이터는 seed_templates.py가 DB 템플릿을 만드는 데도 재사용된다 —
수신호 등록(실시간 추가) 기능은 범위에서 제외되었으므로(03_인터페이스계약서_v2 §6), 촬영은
항상 이 오프라인 스크립트로만 이루어진다.

TODO(김지훈):
- argparse로 --class-name(7종+negative 중 하나), --subject-id 입력받기
- 촬영 장비는 Raspberry Pi Camera Module 3(CSI) 사용 권장 — 02_설계문서_v2 §1-1, 실제 인식에 쓰일
  장비와 동일해야 학습/추론 조건이 일치함 (04_데이터셋명세서_v2 §3)
- mediapipe로 21 keypoints(hand_world_landmarks) 추출
- 원본은 datasets/raw/, 랜드마크 시퀀스는 datasets/processed/ 에 저장
- subject-wise split을 위해 subject_id를 파일명에 항상 포함
"""

if __name__ == "__main__":
    raise NotImplementedError("촬영 스크립트 구현 예정 - 04_데이터셋명세서_v2 §3 촬영 프로토콜 확정 후 작성")
