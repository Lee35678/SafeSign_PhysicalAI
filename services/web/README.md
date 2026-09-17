# web — 프론트엔드 + 교육 상태머신 (담당: 조은수)

RACI: 웹 **R**, 성능측정 **R**

`document/09_화면목록_v1.md`의 SC-01~SC-10 화면 흐름을 상태머신으로 구현하고,
vision(`/predict`)·actuation(`/command`, `/result`) 서비스를 호출해 화면에 반영합니다.

## 담당 범위

- `backend/` — FastAPI. 교육 상태머신(현재 화면/세션 상태), vision·actuation 호출, DB(수신호 템플릿/학습 기록) 조회
- `frontend/` — 정적 HTML/CSS/JS (SC-01~SC-10 화면). 프레임워크 도입은 팀 논의 후 결정

## 화면 ↔ 상태 매핑 (초안, 09_화면목록_v1.md 참고)

| 화면ID | 상태머신 state | 비고 |
| --- | --- | --- |
| SC-01 | `landing` | |
| SC-02 | `field_select` | micro:bit 버튼 순환 or 화면 클릭 |
| SC-03 | `curriculum_confirm` | |
| SC-04 / SC-04a / SC-04b | `training` (하위 상태: `correct` / `incorrect`) | 핵심 화면, vision 결과 폴링/스트리밍 |
| SC-05 | `camera_fail` | 손 미검출 지속 시 |
| SC-06 | `field_summary` | |
| SC-07 | `certificate` | |
| SC-08 | `resume_or_restart` | ⚠️ 세션 이어하기 여부 팀 미확정 |
| SC-09 | `admin_register` | 신규 수신호 등록, data 서비스와 연동 |
| SC-10 | (부가 기능, 1차 범위 제외) | |

## 아직 확정 안 된 것

- [ ] SC-04 화면 분할 단위 (시범/인식 동시 표시 여부) — vision 담당과 협의
- [ ] SC-08 세션 이어하기 구현 여부
- [ ] SC-09 관리자 메뉴 진입 방식

## 로컬 실행

```bash
docker compose up --build web
# http://localhost:8000
```
