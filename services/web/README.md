# web — 프론트엔드 + 교육 상태머신 (담당: 조은수)

RACI: 웹 **R**, 성능측정 **R**

`document/09_화면목록_v2.md`의 SC-01~SC-07 화면 흐름을 상태머신으로 구현하고,
vision(`GET /latest`)·actuation(`POST /command`, `/picar`, `/result`, `/progress`) 서비스를
호출해 화면에 반영합니다.

> **현재 우선순위 (10_PRD_v1.md §1 갱신 로그 참고)**: 지금은 인식→판정→Actuation 입력-출력
> 파이프라인이 정상 동작하는지 확인하는 단계입니다. 이 서비스는 그 흐름을 눈으로 확인할 수 있는
> 최소 골격이면 충분하며, 화면 디자인/레이아웃은 파이프라인 검증 이후에 다듬습니다.

## 담당 범위

- `backend/` — FastAPI. 교육 상태머신(현재 화면/세션 상태), vision·actuation 호출
- `frontend/` — 정적 HTML/CSS/JS (SC-01~SC-07 화면). 프레임워크 도입은 팀 논의 후 결정

## 화면 ↔ 상태 매핑 (09_화면목록_v2.md 참고, 2026-09-18 갱신)

| 화면ID | 상태머신 state | 비고 |
| --- | --- | --- |
| SC-01 | `landing` | |
| SC-02 | `curriculum_confirm` | 수신호 7종 안내 (구 SC-02 분야선택은 폐지) |
| SC-03 (+03a/03b) | `training` (하위 상태: 정답/오답) | 핵심 화면, vision `GET /latest` 폴링 |
| SC-04 | `camera_fail` | 손 미검출 지속 시 |
| SC-05 | `summary` | |
| SC-06 | `certificate` | |
| SC-07 | `reentry` | 세션 이어하기 미구현 — 항상 처음부터 재시작 |

관리자 화면(구 SC-08 신규 수신호 등록)은 없습니다 — 경량 분류기(SVM) 채택으로 해당 기능 자체가
범위에서 제외되었습니다 (03_인터페이스계약서_v2 §6).

## 아직 확정 안 된 것

- [ ] SC-03 화면 분할 단위 (시범/인식 동시 표시 여부) — vision 담당과 협의
- [ ] vision `/latest` 폴링 주기 (또는 WebSocket 전환 시점)

## 로컬 실행

```bash
docker compose up --build web
# http://localhost:8000
```
