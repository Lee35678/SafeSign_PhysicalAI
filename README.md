# SafeSign PhysicalAI — 심기일전

산업 안전 수신호 교육용 피지컬 AI (AI Hand + picar + micro:bit + Raspberry Pi 5)

**개발 착수 시 반드시 먼저 읽을 문서**: [document/10_PRD_v1.md](document/10_PRD_v1.md) — 01~09번
문서를 종합한 최신 요구사항입니다. 개별 세부사항은 [document/](document/) 폴더의 각 문서를 참고하세요.

---

## 1. 디렉터리 구조 (담당자별 컨테이너 분리)

`document/10_PRD_v1.md` §4 시스템 아키텍처와 `역할 및 책임표.md`의 RACI를 기준으로 4개 서비스로
나눴습니다. 각자 자기 서비스 폴더 안에서만 작업하면 다른 사람 코드와 충돌 없이 개발할 수 있고,
마지막에 `docker compose up`으로 전부 합쳐서 로컬 통합 구동을 확인합니다.

```
SafeSign_PhysicalAI/
├── document/              # 기획/설계/계약 문서 (10_PRD_v1.md가 최신 종합본)
├── services/
│   ├── vision/             ← 이동혁 담당 (Perception + Cognition, 판정로직 R)
│   ├── actuation/          ← 송승호 담당 (AI Hand + picar + micro:bit, 하드웨어 R)
│   ├── web/                ← 조은수 담당 (프론트엔드 + 교육 상태머신 백엔드, 웹 R)
│   └── data/               ← 김지훈 담당 (데이터 수집 스크립트 + 수신호 템플릿 DB, 데이터수집 R)
├── shared/                 # 4명 공통: 03_인터페이스계약서_v2 기반 스키마 (필드명 그대로 코드 변수명에 사용)
├── docker-compose.yml      # 4개 서비스 통합 실행
├── .env.example
└── .gitignore
```

담당 외 서비스도 A/C/I 역할로 참고는 하되, 실제 코드 작업은 본인 폴더 위주로 진행하고
인터페이스는 `shared/schemas/`에 정의된 스키마로만 주고받으세요. 스키마를 바꿔야 하면
`shared/schemas/` 파일과 `document/03_인터페이스계약서_v2.md`를 함께 갱신하고 팀에 공유합니다.

## 2. 확정된 하드웨어/아키텍처 (2026-09-18, PRD §1.3·§11 기준)

- **카메라**: Raspberry Pi Camera Module 3, **CSI** 직결 (범용 USB 웹캠 아님) — RPi5가 이 카메라로
  Perception을 수행
- **picar**: RPi5가 **GPIO로 직접 구동** (별도 컨트롤러/통신 프로토콜 없음)
- **MediaPipe 실행 모드**: `LIVE_STREAM`(비동기 콜백) — 개발 편의보다 실시간 성능 우선
- **판정 임계값/프레임 수 초기값**: τ=0.75, N=3프레임 (하드웨어 제약 근거 초기값, 실물 도착 후 재검증)
- **서보 각도 초기값**: 펴짐=170°, 굽힘=10°, 손목중립=90°
- **수신호 등록(실시간 추가) 기능은 범위에서 제외** — 경량 분류기(SVM)는 고정 클래스만 예측 가능해
  재학습 없는 실시간 등록이 성립하지 않음. DB 템플릿은 `services/data/src/seed_templates.py`로
  오프라인 시드
- **RPi5 한 대가 vision(카메라 추론)과 actuation의 picar 제어를 실제로는 겸함** — 로컬 개발은
  컨테이너로 분리하되, 실물 배포 시 배치를 재검토할 것 (services/actuation/README.md 참고)

## 3. 로컬 실행

```bash
docker compose up --build
```

- vision  → http://localhost:8001/health , http://localhost:8001/latest
- actuation → http://localhost:8002/health
- web     → http://localhost:8000

데이터 수집/DB 초기화 도구는 상시 구동 서비스가 아니라 필요할 때만 실행합니다.

```bash
docker compose --profile tools run --rm data-tools python src/init_db.py
docker compose --profile tools run --rm data-tools python src/seed_templates.py
```

> ⚠️ 카메라(vision)와 picar/서보/micro:bit(actuation)는 실제 하드웨어 장치 접근이 필요하며, 아직
> 카메라·picar 실물이 팀에 도착하지 않았습니다. Windows Docker Desktop은 CSI 카메라/GPIO/시리얼
> 장치 직접 전달을 지원하지 않으므로, 로컬 PC에서는 `MOCK_CAMERA=true`, `MOCK_HARDWARE=true`
> (둘 다 기본값)로 목업 응답을 받으며 개발하고, 실제 장치 연동은 RPi5(Linux) 환경에서
> `devices:` 항목을 참고해 진행하세요.

## 4. Git / 브랜치 전략 (제안)

- 각자 자기 서비스 폴더(`services/<본인담당>/`)를 중심으로 작업 브랜치를 나눕니다.
  예: `feat/vision-classifier`, `feat/actuation-picar`, `feat/web-sc03`, `feat/data-collection`
- `shared/schemas/`를 변경하는 PR은 반드시 관련자 전원 리뷰(C) 후 머지합니다.
- 통합 확인은 `main`에 머지 후 `docker compose up --build`로 4개 서비스가 함께 뜨는지 확인합니다.

## 5. 문서 연동 체크

- 서비스 간 메시지 필드/스키마 변경 시 → `document/03_인터페이스계약서_v2.md` 갱신
- 아키텍처/범위가 바뀌면 → `document/10_PRD_v1.md`도 함께 갱신 (개별 문서만 고치고 PRD를 방치하지 않기)
- 통합 7종 수신호 목록은 `document/02_설계문서_v2.md` §4 · `document/04_데이터셋명세서_v2.md` §1 ·
  `shared/schemas/aihand_command.schema.json` · `shared/schemas/picar_command.schema.json`에서
  동일하게 유지
