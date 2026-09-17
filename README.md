# SafeSign PhysicalAI — 심기일전

산업 안전 수신호 교육용 피지컬 AI (AI Hand + micro:bit + Raspberry Pi 5)

관련 문서: [document/](document/) 폴더의 01~09번 문서, 역할 및 책임표.md

---

## 1. 디렉터리 구조 (담당자별 컨테이너 분리)

`document/` 문서의 시스템 구성도(카메라 → Perception → Cognition → 교육 상태머신 → Actuation)와
`역할 및 책임표.md`의 RACI를 기준으로 4개 서비스로 나눴습니다. 각자 자기 서비스 폴더 안에서만
작업하면 다른 사람 코드와 충돌 없이 개발할 수 있고, 마지막에 `docker compose up`으로 전부 합쳐서
로컬 통합 구동을 확인합니다.

```
SafeSign_PhysicalAI/
├── document/              # 기획/설계/계약 문서 (기존)
├── services/
│   ├── vision/             ← 이동혁 담당 (Perception + Cognition, 판정로직 R)
│   ├── actuation/          ← 송승호 담당 (AI Hand 서보 + micro:bit 시리얼, 하드웨어 R)
│   ├── web/                ← 조은수 담당 (프론트엔드 + 교육 상태머신 백엔드, 웹 R)
│   └── data/               ← 김지훈 담당 (데이터 수집 스크립트 + 수신호 템플릿 DB, 데이터수집 R)
├── shared/                 # 4명 공통: 03_인터페이스계약서_v1 기반 스키마 (여기 필드명 그대로 코드 변수명에 사용)
├── docker-compose.yml      # 4개 서비스 통합 실행
├── .env.example
└── .gitignore
```

담당 외 서비스도 A/C/I 역할로 참고는 하되, 실제 코드 작업은 본인 폴더 위주로 진행하고
인터페이스는 `shared/schemas/`에 정의된 스키마로만 주고받으세요. 스키마를 바꿔야 하면
`shared/schemas/` 파일과 `document/03_인터페이스계약서_v1.md`를 함께 갱신하고 팀에 공유합니다.

## 2. 로컬 실행

```bash
docker compose up --build
```

- vision  → http://localhost:8001/health
- actuation → http://localhost:8002/health
- web     → http://localhost:8000

데이터 수집/DB 초기화 도구는 상시 구동 서비스가 아니라 필요할 때만 실행합니다.

```bash
docker compose --profile tools run --rm data-tools python src/init_db.py
```

> ⚠️ 카메라(vision)와 micro:bit/서보(actuation)는 실제 하드웨어 장치 접근이 필요합니다.
> Windows Docker Desktop은 USB 카메라/시리얼 장치 직접 전달을 지원하지 않으므로,
> 로컬 PC에서는 `MOCK_HARDWARE=true`(기본값)로 목업 응답을 받으며 개발하고,
> 실제 장치 연동 테스트는 Raspberry Pi 5(Linux) 환경에서 `devices:` 항목을 주석 해제해 진행하세요.

## 3. Git / 브랜치 전략 (제안)

- 각자 자기 서비스 폴더(`services/<본인담당>/`)를 중심으로 작업 브랜치를 나눕니다.
  예: `feat/vision-classifier`, `feat/actuation-servo`, `feat/web-sc04`, `feat/data-collection`
- `shared/schemas/`를 변경하는 PR은 반드시 관련자 전원 리뷰(C) 후 머지합니다.
- 통합 확인은 `main`에 머지 후 `docker compose up --build`로 4개 서비스가 함께 뜨는지 확인합니다.

## 4. 문서 연동 체크

- 서비스 간 메시지 필드/스키마 변경 시 → `document/03_인터페이스계약서_v1.md` 갱신
- 최종 채택 5종 수신호 확정 시 → `document/02_설계문서_v1.md` §4, `document/04_데이터셋명세서_v1.md` §1,
  `shared/schemas/aihand_command.schema.json` 동시 반영
