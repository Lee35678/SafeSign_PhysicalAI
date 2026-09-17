# shared/

4개 서비스(vision / actuation / web / data)가 공통으로 참조하는 인터페이스 정의입니다.
출처는 `document/03_인터페이스계약서_v2.md`이며, 그 문서가 원본(source of truth)입니다.
여기 있는 JSON Schema는 문서 내용을 코드에서 검증/자동완성하기 쉽게 옮겨둔 것이므로,
**계약서 문서를 고치면 이 폴더도 같이 고치고, 반대도 마찬가지입니다.**

| 파일 | 대응 문서 절 | 사용처 |
| --- | --- | --- |
| `schemas/landmark_frame.schema.json` | §3 Perception → Cognition | vision 내부(LIVE_STREAM 콜백 출력) |
| `schemas/judgment_result.schema.json` | §4 Cognition → 교육 상태머신 | vision → web |
| `schemas/aihand_command.schema.json` | §5-1 AI Hand 제어 명령 | web → actuation |
| `schemas/picar_command.schema.json` | §5-2 picar 제어 명령 | web → actuation (RPi5 GPIO 직결이므로 실제로는 같은 프로세스 내 호출) |
| `schemas/microbit_protocol.md` | §5-3 micro:bit 시리얼 프로토콜 | actuation ↔ micro:bit |

> **범위 제외**: 수신호 등록(신규 수신호 실시간 추가) 기능은 03_인터페이스계약서_v2 §6에 따라 구현하지
> 않습니다 — 이 폴더에도 그에 대응하는 스키마를 두지 않습니다. DB 템플릿은 `services/data/src/seed_templates.py`로
> 오프라인 시드됩니다.

## 규칙

1. 필드명은 계약서 문서와 100% 동일하게 유지 (예: `predicted_class`, `match_score`, `is_reject`).
2. 스키마 변경 시 버전을 올리고 (`_v1` → `_v2` 파일 접미사 또는 파일 내 `"version"` 필드),
   `document/03_인터페이스계약서_v2.md` 하단 변경 이력에도 기록.
3. ⚠️ 표시된 값(서행 속도 등)은 실물 테스트 후 확정되므로, 확정 전까지는 스키마에 타입/범위만 정의하고
   목업(mock) 값을 사용합니다. τ, N프레임, 서보 각도는 05_모델카드_v3 §8-0 초기 기본값이 이미 코드
   기본값으로 반영되어 있습니다 (실물 도착 후 재검증 예정).
