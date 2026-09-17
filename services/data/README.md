# data — 데이터 수집 + 수신호 템플릿 DB (담당: 김지훈)

RACI: 데이터수집 **R**, 요구사항·범위 **R**

`document/04_데이터셋명세서_v2.md` 기준 담당 범위:

- 클래스당 ~300장 촬영 데이터 수집 (8클래스 = 7종+negative, 팀원 4명 = train/val, 외부인 1~2명 = test,
  subject-wise split 필수)
- 원본 → 랜드마크 시퀀스 전처리
- 수신호 템플릿 DB 스키마/오프라인 시드 관리

> ⚠️ **수신호 등록(실시간 추가) 기능은 범위에서 제외되었습니다** (경량 분류기 SVM 채택,
> `document/03_인터페이스계약서_v2.md` §6). DB 템플릿은 학습자가 아니라 **이 서비스가 학습 데이터로
> 오프라인 시드**합니다 — 런타임에 새 수신호를 추가하는 흐름은 없습니다.

## 디렉터리

```
datasets/
├── raw/{class_name}/{subject_id}_{index}.jpg      # 원본 촬영 (04_데이터셋명세서_v2 §6 폴더 구조안)
└── processed/{class_name}/{subject_id}_{index}.json  # 랜드마크 21keypoint 시퀀스
```

`datasets/`는 `.gitignore`에 등록되어 있습니다 (용량 문제로 git 대신 별도 공유 스토리지 사용 권장).

- `src/collect.py` — 촬영 + MediaPipe 랜드마크 추출 스크립트 (**호스트에서 직접 실행 권장**, 실제 인식과
  동일한 장비인 Raspberry Pi Camera Module 3 사용 권장)
- `src/init_db.py` — 수신호 템플릿 DB(SQLite) 초기 스키마 생성 (`sign_name`, `vector`만 — field_id 없음)
- `src/seed_templates.py` — `datasets/processed/`의 클래스별 데이터로 DB 템플릿을 채우는 오프라인 배치 스크립트 (신규)

## 아직 확정 안 된 것 (04_데이터셋명세서_v2 참고)

- [ ] 촬영 환경/변인 (조명, 거리, 각도 범위) (§3)
- [ ] 담당자별 촬영 분량 배분 (§4)
- [ ] processed 파일 포맷 세부 스펙 (§6) — seed_templates.py 구현과 함께 확정

## 실행

```bash
# DB 초기화 (docker-compose tools 프로필)
docker compose --profile tools run --rm data-tools python src/init_db.py

# 촬영 스크립트는 호스트에서 직접 실행 (카메라 필요)
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python src/collect.py --class-name <수신호명> --subject-id <촬영자ID>

# 촬영/전처리 완료 후 템플릿 시드
docker compose --profile tools run --rm data-tools python src/seed_templates.py
```
