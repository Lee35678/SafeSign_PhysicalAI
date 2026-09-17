# data — 데이터 수집 + 수신호 템플릿 DB (담당: 김지훈)

RACI: 데이터수집 **R**, 요구사항·범위 **R**

`document/04_데이터셋명세서_v1.md` 기준 담당 범위:

- 클래스당 ~300장 촬영 데이터 수집 (팀원 4명 = train/val, 외부인 1~2명 = test, subject-wise split 필수)
- 원본 → 랜드마크 시퀀스 전처리
- 수신호 템플릿 DB(등록 기능, `document/03_인터페이스계약서_v1.md` §6) 스키마/시드 관리

## 디렉터리

```
datasets/
├── raw/{class_name}/{subject_id}_{index}.jpg      # 원본 촬영 (04_데이터셋명세서_v1 §6 폴더 구조안)
└── processed/{class_name}/{subject_id}_{index}.json  # 랜드마크 21keypoint 시퀀스
```

`datasets/`는 `.gitignore`에 등록되어 있습니다 (용량 문제로 git 대신 별도 공유 스토리지 사용 권장).

- `src/collect.py` — 웹캠으로 촬영 + MediaPipe 랜드마크 추출 스크립트 (**호스트에서 직접 실행 권장**,
  Docker/Windows에서는 카메라 접근이 제한적)
- `src/init_db.py` — 수신호 템플릿 DB(SQLite) 초기 스키마 생성

## 아직 확정 안 된 것 (04_데이터셋명세서_v1 참고)

- [ ] 최종 채택 5종 클래스명 (§1, 02_설계문서_v1 §4와 동기화 필요)
- [ ] 촬영 환경/변인 (조명, 거리, 각도 범위) (§3)
- [ ] 담당자별 촬영 분량 배분 (§4)

## 실행

```bash
# DB 초기화 (docker-compose tools 프로필)
docker compose --profile tools run --rm data-tools python src/init_db.py

# 촬영 스크립트는 호스트에서 직접 실행 (웹캠 필요)
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python src/collect.py --class-name <수신호명> --subject-id <촬영자ID>
```
