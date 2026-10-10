# 통합 테스트 · KPI 측정 · CI 계획서 (v1.1 — 제출본 이후 갱신)

**팀명**: 심기일전 · **작성자**: 송승호 (하드웨어·로봇동작 R, 팀장)
**최초 작성**: 2026-09-28(월) · **기준 커밋**: `dev` `b5e83a5`(버튼 A) — 줄번호는 이 커밋 기준. **v0.8**: web 백엔드 병합(`c8f1fd3` → `dev` `1da641b`) 상태만 갱신. **v0.10 상태 기준**: `dev` `41ef97c` + `feature/picar` `edb5da9`(①-b 화면, `dev` 병합 전) — 줄번호는 갱신하지 않음. **v0.12**: ①-b `dev` 병합 완료(`db4cd41`, fast-forward, `origin/dev` 반영) — 전체 158 · web 49 회귀 재확인. **v0.15**: ⑥ 전 구간 실물 재시험 통과(쿨러 없이) — 재시험 중 발견한 결함 2건 당일 수정, 전체 162 통과 (14 §7). **v0.17**: 재수정(`cb8a25b`, 전체 170 통과) 실물 재검증 통과 — web 전 구간 실물 검증 종료. **v0.18**(2026-09-30, 이동혁): 오프라인 최종 KPI(팀원 3명 210시도) 반영 — 판정 성능 5개 달성. **v1.0**(2026-10-04, 송승호): 제출 시점 상태로 정리 — 상태 기준 `dev` `60231a6`, 단위 테스트 320개 통과(§0.1), §6을 완료 / 제출 후 과제 / 폐기로 분류. **v1.1**(2026-10-10, 송승호): 단위 테스트 수를 `feature/picar` `996b67b` 기준 **331개 통과**로 갱신(§0·§0.1·§1.1), `.gitignore` 줄번호 인용을 규칙 문구로 바꿈, §3.2 파일 구성을 실제(`requirements-test.txt`는 있음, `requirements-hw.txt`·`jsonschema`는 계획만)와 맞춤
**일정**: W4 테스트·보완 마감 2026-10-04(일, 종료) · 제출 2026-10-08(목) · 최종 발표 2026-10-12(월)

> **이 문서의 범위**: 서비스 4개(web·vision·actuation·picar)를 **엮어서** 검증하는 방법과, 그 결과로
> KPI를 **어떻게 잴지**, 그리고 이를 GitHub에서 **자동으로 돌리는 방법(CI)**을 한 곳에 정리한다.
> 서비스 하나 안의 단위 테스트는 각 서비스 `tests/`, 시행 원본 로그·혼동행렬은
> [06_테스트·평가리포트](06_테스트·평가리포트.md), picar 하드웨어 실측은 [13](13_picar_하드웨어_검증리포트.md),
> 하드웨어 설계 수치는 [11](11_하드웨어설계서.md), 실물 실행 명령은 [루트 README §4](../README.md),
> 실물 기동·종료 스크립트는 [17](17_실물실행_스크립트_사용법.md)이 각각 다룬다 — 중복해서 적지 않고 링크한다.
>
> 📝 **표기**: 이 문서 안의 `§n`은 이 문서의 절이다. 수치 옆의 표시는 다음 뜻이다.
> **실측**(측정값) · **코드값**(현재 코드 기본값) · **잠정**(문서상 임시값) · **추정**(계산·추론, 측정 안 함).
>
> 📌 **결정은 이 문서에서 하지 않는다.** 측정 방법의 미결 사항은
> [proposals/회의안건_KPI측정방법](proposals/회의안건_KPI측정방법.md)에서 결정하고, 결정되면 이 문서에 반영한다.
>
> 🔎 **검토**: v0.2는 `sw-tester`(테스트 수·줄번호·재시도 로직·CI 초안), `hw-tester`(하드웨어 수치 출처·실물 절차),
> `evaluator`(KPI 정의·표본 계산·데모 CSV) 관점의 검토를 반영했다. 수치·줄번호는 검토 때 원본과 다시 대조했다.

---

## 0. 한 장 요약

| 영역 | 상태 | 막는 것 |
| --- | --- | --- |
| 단위 테스트 | ✅ **331개 통과 · 실패 0** — web 129 · vision 80 · actuation 56 · picar 53 · portal 13 · data 0 (2026-10-10 `feature/picar` `996b67b`, 저장소 루트 `python -m pytest`, 호스트 Python 3.13). 고정 버전 3.11 서비스별 가상환경 통과는 2026-10-03(`c55ea15`, 15 10-03). 이전 기록: 09-29 170개 → 10-03 320개 → 10-10 331개(재점검 버그 수정 회귀 테스트, 15 10-10) | 없음 |
| 계약 테스트 | ⬜ **수행 안 함 → 제출 후 과제**(§0.1) | `jsonschema` 테스트 의존성 없음(`httpx`는 2026-10-03 `c560bbd`에서 `requirements-test.txt`에 추가) |
| mock 통합 테스트 | ⬜ **수행 안 함 → 제출 후 과제**(§0.1) — 단, **docker compose(mock) 빌드·기동은 2026-09-28 확인**(§2.3) | mock 카메라가 손 미검출만 발행 → **판정이 한 번도 안 일어남** (실행으로 확인). 판정 주입 방식 미결(§6.2) |
| 실물 E2E — web 없는 전 구간 | ✅ 2026-09-25 **7/7 성공** (데모 스크립트, 반응 시작 25~47ms) | — |
| 실물 E2E — web 전 구간 | ✅ **⑥ 전 구간 재시험 통과 · 재시험 중 나온 결함 2건 재검증까지 완료**(2026-09-29, `cb8a25b`) | ~~①-b `dev` 미병합~~ → ✅ **2026-09-29 병합 완료**(`db4cd41`). ~~실물 스크립트(17) 미검증~~ → ✅ **2026-09-29 통과**(17 §6·§9). ~~버튼 A 실물 확인~~ → ✅ **2026-09-29 완료**(08, 11 §9.1 v1.24). ✅ **2026-09-29 ⑥ 전 구간 실물 재시험 통과**(쿨러 없이 진행, 사용자 결정) — 스펙 §6 체크리스트 6개 전부·모터/LED·AI Hand·micro:bit O/X·종료 시 LED 소등·"다시 학습하기" 재진입까지 확인(14 §6.2). 재시험 중 신규 결함 2건 발견·당일 수정: (1) SC-04 카메라 미검출 시 "재시도" 버튼 무동작 → 재시도 = 시범 단계 복귀 + 재시범(버튼·Space·micro:bit A), (2) 시도 횟수 무제한 → `MAX_ATTEMPTS_PER_SIGNAL=3` + 판정 제한시간 10초(`timeout`도 시도로 셈). 1차 수정은 커밋 전이라 실물에 없었고 설계도 부족해 재작성(14 §2·§7, 회귀 테스트 11건, 전체 170 통과). ✅ **2건 모두 실물 재검증 통과**(`cb8a25b`) — 남은 선행 조건 없음. ~~RPi5 쿨러(#11)는 KPI 실측·장시간 시연 전 장착 여부만 결정~~ (→ 2026-10-04 정정: 2026-10-03 쿨러 없이 **선풍기 운용 확정** — #11) |
| 회원 DB (Supabase) | ✅ **2026-09-30 연결**(키 루트 `.env`) · `schema.sql`을 실제 PostgreSQL 16에서 실행 검증(업그레이드·재실행·저장·중복·권한 전부 통과 — 18 §0) | ~~RPi5에 `.env` 복사 후 교육장 실물 저장 확인~~ → ✅ 2026-10-04 확인(아래 행) |
| 회사 사이트 (`services/portal`) | ✅ 단위 **12개** 통과(2026-10-04) · 화면 1440/390 콘솔 오류 0 (19 §8). 테스트는 루트 `.env`를 읽지 않는다. ✅ **교육장 ↔ 회사 사이트 실제 연동 확인**(2026-10-04 송승호 — 회사 사이트 가입 계정으로 교육장 7종 완료 → 내 정보 회차 기록·수료증 정상, 19 §8) | ~~CI에 portal 테스트 추가~~ → ✅ `ci.yml` matrix에 portal 포함(`c55ea15`) |
| CI (GitHub Actions) | 🟡 `ci.yml` 작성(unit job, 서비스별 Python 3.11 — 2026-10-03 `c55ea15`), GitHub 첫 실행 전 | 저장소 관리자의 Actions 허용, integration job(§3.2) |
| KPI 판정 성능 5개 | ✅ **오프라인 최종 측정 완료(2026-09-30)** — 팀원 3명 210시도(RPi5 CSI), 공식 3연속: 정답 95.2%(하한 91.5%, 잠정 달성) · 오분류 0.0%(상한 1.8%, 달성) · 미판정 4.8%(상한 8.5%, 잠정 달성) · F1 0.974 · 치명 0(상한 11.4%, 잠정 달성) → **5개 전부 점추정 달성**(정답률·미판정률·치명 오분류는 잠정) | 결과보고서에 신뢰구간 병기 (05 §7-3, 06 §2-1) |
| KPI 지연 2개 | ✅ **온라인 최종 측정 완료(2026-10-02, 송승호)** — 정답 91시도(13회차): 판정 지연 P95 **0.046초**(95% 상한 0.065초) · 물리 피드백(반응 시작) P95 **0.089초**(95% 상한 0.262초, 완료 기준 1.089초, 손 기준 상한 0.335초) → **2개 모두 달성** | 기록값은 KPI 정의보다 좁은 구간 — 한계 명시. 슬로모션 교차 확인 ✅(손 정지 → 반응 시작 0.14~0.24초, 완료 추정 약 1.1~1.2초) (06 §2-3, 원본 [`results/kpi_online_20261002/`](results/kpi_online_20261002/)) |

**핵심 결론**

1. ~~**단위 테스트와 CI unit job은 이번 주 안에 된다.**~~ → ✅ 단위 테스트 **320개 통과**(2026-10-04 → 2026-10-10 **331개**), `ci.yml` unit job 작성(2026-10-03 `c55ea15`). **GitHub 첫 실행만** 저장소 관리자의 Actions 허용을 기다린다(§3.1).
2. **mock 통합은 "판정 주입" 수단이 먼저다.** 추천은 가짜 vision 서버(stub)다(§2.3). vision 코드를 건드리지 않는다. → 제출 전에는 하지 않았다 — **제출 후 과제**(§0.1).
3. ~~**지연의 가장 큰 문제는 호출 순서와 재시도다.**~~ → ✅ **2026-09-28 `c8f1fd3`로 해소** — 호출 순서가 `/picar` → `/result` → `/command` → `/progress`로 바뀌어 micro:bit·picar가 0.85초 늦던 문제가 없어졌고, 읽기 타임아웃 재시도 금지로 이중 동작도 막혔다(§4). 실물에서는 ⑥ 재시험(09-29)과 KPI 온라인 측정(10-02, 물리 피드백 시작 P95 0.089초)으로 확인했다.
4. ~~**KPI는 재는 방법에 구멍이 있다.**~~ → ✅ **09-30 회의 + 10-01 결정 D1~D6으로 확정하고 10-02 측정 완료**(§5.6). 판정 지연이 실제보다 작게 기록되는
   한계는 그대로라 **한계를 명시하고 손 기준 보수적 상한을 병기**한다(06 §2-3).
5. **실물 운영·시연은 네이티브로 확정했다**(2026-09-28, 송승호 — §2.4). Docker는 개발 PC mock 실행·통합 테스트·CI에만 쓰고,
   실물은 `scripts/rpi/` 스크립트(tmux)로 띄운다([17](17_실물실행_스크립트_사용법.md)). `docker-compose.hw.yml`은 미검증·선택 사항이다.

### 0.1 제출 시점 결론 (2026-10-04)

**한 줄 요약**: 서비스별 단위 테스트, 실물 전 구간 시험, KPI 7개 측정은 끝났다. 계약 테스트, mock 통합 테스트, CI 첫 실행은 하지 않았다.
장애 경로(장치 끊김·카메라 고장)는 대부분 코드와 단위 테스트로만 확인했다. 아래 표에 범위와 대응을 적는다.

**수행한 것**

| 항목 | 결과 | 근거 |
| --- | --- | --- |
| 단위 테스트 | **331개 통과**, 실패 0 — web 129 · vision 80 · actuation 56 · picar 53 · portal 13 (data는 테스트 없음). 2026-10-10 `feature/picar` `996b67b`에서 저장소 루트 `python -m pytest`(호스트 Python 3.13. 제출 시점 2026-10-04 `60231a6`은 320개). 고정 버전 Python 3.11 서비스별 가상환경 통과는 2026-10-03 | §1.1, 15 10-03 |
| 실물 E2E — web 없는 전 구간 | 2026-09-25 7/7 성공 (데모 스크립트) | §0 표 |
| 실물 E2E — web 전 구간 ⑥ | 2026-09-29 재시험 통과. 재시험 중 나온 결함 2건(SC-04 재시도, 시도 횟수 상한)도 같은 날 고쳐 실물 재검증(`cb8a25b`) | 14 §6.2·§7 |
| KPI 판정 성능 5개 (오프라인) | 2026-09-30, 팀원 3명 **210시도**(RPi5 CSI·카메라 거치대) — 5개 모두 점추정 달성(정답률·미판정률·치명 오분류는 신뢰구간 기준 잠정 달성) | 05 §7-3, [`results/kpi_offline_final_20260930.json`](results/kpi_offline_final_20260930.json) |
| KPI 지연 2개 (온라인) | 2026-10-02, 정답 **91시도** — 판정 지연 P95 0.046초, 물리 피드백(반응 시작) P95 0.089초, 둘 다 달성. RPi5 PLA 케이스·카메라 거치대 설치, 선풍기 켬 | 06 §2-3, [`results/kpi_online_20261002/`](results/kpi_online_20261002/) |
| 10-03 수정분 실물 확인 (2026-10-04) | vision `/reset` 5/5, BLE 회신 대조 11건 짝 일치, picar LED 2초 뒤 소등, 자동 정지 타이머 경쟁(동시 10회) 재현 안 됨, **Ctrl+C 종료 시 약 0.5초 만에 정지**, **주행 중 `stop_all.sh`로 정지** | 15 10-04, 11 §9, 13 §5 #4, 17 §9 |
| 그 밖의 실물 확인 (2026-10-04) | RPi5 Wi-Fi 5GHz 대역 있음, 차체 배터리 팩 11~12V, 교육장 ↔ 회사 사이트 연동(가입 계정으로 7종 완료 → 내 정보·수료증 정상) | 07 §9.3, 13 §4.4, 19 §8 |

**수행하지 않은 것과 사유**

| 항목 | 사유 |
| --- | --- |
| 계약 테스트 (§2.2) | 실물 재시험·KPI 측정을 먼저 했다. 15 TODO에 "W5로 미뤄도 됨"으로 적어 둔 항목이다. `jsonschema` 테스트 의존성도 아직 없다 |
| mock 통합 테스트 S1·S5·S7 (§2.3) | 판정 주입 방식(stub vision 대 vision 훅, §6.2)을 정하지 못했다. 같은 이유로 S2~S4·S6도 쓰지 않았다. docker compose(mock) 빌드·기동만 09-28에 확인했다 |
| CI 첫 실행 (§3) | `ci.yml`은 작성했지만(10-03 `c55ea15`) 저장소 관리자(Lee35678)의 Actions 허용을 기다린다. 고정 버전 3.11 통과는 로컬 가상환경으로 대신 확인했다 |
| 장애 경로 — 오답·timeout·재시도 | KPI 온라인 91시도가 전부 정답이었다(제외 0행). 그래서 **오답·`timeout`·재시도 경로는 KPI 시행에서 0회**다. 동작은 단위 테스트와 09-29 ⑥ 재검증(일부러 3회 틀리기·10초 넘기기, §6.1 #17)에서만 확인했다 |
| 장애 경로 — Wi-Fi 끊김·BLE 끊김·운영 중 카메라 고장 | 실물에서 일부러 일으켜 본 적이 없다. BLE 재연결은 단위 테스트만(`d81948b`), 운영 중 카메라 고장은 가짜 카메라 재현만 했다(09-28, §2.4) |

**미시험 범위와 대응** — 장애별 화면·흐름·복구의 기준은 [03 §7 장애 대응표](03_인터페이스계약서.md), 위험 등급은 [08](08_리스크레지스터.md)이다.

| 항목 | 이유 | 위험 | 대응 |
| --- | --- | --- | --- |
| picar Wi-Fi 끊김 (RPi5 AP ↔ RPi4B) | 실물에서 끊어 보지 않음 | picar만 반응 없음. `/picar` 타임아웃 때문에 micro:bit O/X가 최대 약 1초 늦을 수 있음 | 학습은 계속된다. 링크가 돌아오면 다음 정답부터 자동 복구, 주행 중 끊겨도 2초 뒤 자동 정지(03 §7). 링크 점검은 [07](07_네트워크설정법.md) |
| micro:bit BLE 끊김·재연결 | 재연결과 늦은 회신을 버리는 경로는 단위 테스트만(15 10-04) | 재연결이 web 타임아웃(1.5초)을 넘기면 그 명령은 실패로 기록되고 AI Hand가 늦게 움직일 수 있음 | 학습은 계속된다(화면·Space로 확인). §2.4 "안전·복구"대로 `/progress`로 재연결 유도 → micro:bit 리셋·`bluetoothctl disconnect`(03 §7, 08) |
| 운영 중 카메라 고장 | 가짜 카메라 재현만. 고치는 코드(vision `degraded`·`/latest` 고정 해소)는 미착수(§6.3) | 장치 표시줄은 정상으로 보이고, 화면 멈춤·오답 1회·SC-04 중 하나가 됨 | 운영자가 `status.sh`의 `camera=error`를 보고 vision 재기동(03 §7). 기동 시 고장은 `start_all.sh`가 잡는다 |
| 오답·`timeout`·재시도 경로의 장치 지연 | KPI 온라인 시행이 전부 정답 | 오답 경로의 지연 수치가 없음. KPI 모수는 정답 행만이라(§5.6 #2) KPI 판정에는 영향 없음 | 동작은 ⑥ 재검증(09-29)·단위 테스트로 확인. 수치가 필요하면 제출 후 별도 측정 |
| 장치 호출 실패를 web이 처리하는 경로 (picar `partial`, actuation `timeout`) | mock 장애 주입이 없음(§6.1 #6). 단위 테스트(③)만 | 실패가 기록만 되고 흐름이 이어지는지 실물로 본 적 없음 | 03 §5-5 판정 기준대로 구현(`c8f1fd3`). mock 장애 주입은 제출 후 과제 |
| picar 형식 오류 처리 (`{"led":"on"}` 등) | 단위 테스트만(`899f6ba`) | 낮음 — web은 이런 요청을 보내지 않음 | 13 §5 #9 |
| 여러 시간 연속 운용 | 선풍기 측정은 각 17분 두 번뿐(17 §10) | 열 스로틀링으로 판정 fps가 떨어질 수 있음 | 시연·측정 때 선풍기 필수, `status.sh`·`monitor.py`로 온도 확인(§4.6) |
| 차체 배터리 BMS·LVC(저전압 차단) 유무 | 확인 안 함 | 배터리 과방전 | 시연·리허설 전마다 팩 전압을 다시 잰다(13 §4.4, 15 TODO `picar`) |

---

## 1. 테스트 현황 (기준선)

### 1.1 서비스별 테스트 수

**현재 (2026-10-10, `feature/picar` `996b67b`)** — 서비스별 `python -m pytest services/<svc> --collect-only -q`로 센 수. 저장소 루트 전체 실행은 **331개 통과**(호스트 Python 3.13). 2026-10-04 `60231a6`(320개) 대비 +11 — 재점검 버그·비ASCII 입력 500 수정의 회귀 테스트와 상수 대조 추가(15 10-10).

| 서비스 | 수 | 테스트 파일 (파일별 수) |
| --- | --- | --- |
| web | 129 | `test_members.py` 29 · `test_judging_timing_spec.py` 27 · `test_state_machine.py` 24 · `test_microbit_button_confirm.py` 17 · `test_aggregate_kpi.py` 16 · `test_constants_sync.py` 10 · `test_target_score.py` 4 · `test_camera_proxy.py` 2 |
| vision | 80 | `test_normalize.py` 21 · `test_evaluate_kpi.py` 15 · `test_gate.py` 7 · `test_model_store_swap.py` 7 · `test_classify.py`·`test_class_probabilities.py`·`test_constants_sync.py`·`test_match_score.py`·`test_preview.py`·`test_reset.py` 각 4 · `test_capture.py`·`test_http.py` 각 3 |
| actuation | 56 | `test_controller.py` 52 · `test_http.py` 4 |
| picar | 53 | `test_controller.py` 49 · `test_http.py` 4 |
| portal | 13 | `test_portal.py` 13 |
| data | 0 | — |
| **합계** | **331** | |

**2026-09-29 기준선 (기록 — 무엇을 검증하는지 설명)**

| 서비스 | 테스트 파일 | 수 | 이미 검증하는 것 (새로 쓰지 않음) |
| --- | --- | --- | --- |
| web | `test_state_machine.py`, `test_judging_timing_spec.py`, `test_microbit_button_confirm.py`(2026-09-29) | 9 + 26 + 14 | `_post_with_retry`, `_poll_once`, 수료증 발급 / 판정 타이밍 ①-a·③·②-a 인수 테스트(xfail 22개 → 2026-09-28 병합 후 전부 통과) |
| vision | `test_normalize.py`, `test_gate.py`, `test_classify.py`, `test_capture.py` | 21 + 7 + 4 + 3 | 정규화 불변성, 소속 게이트 분기, no_hand 경로, 캡처 루프 |
| actuation | `test_controller.py` | 29 | GESTURE_MAP ↔ 스키마, mock execute, BLE 연결 실패, 동시 전송 직렬화, **버튼 A**(`BTN:A`가 회신으로 잡히지 않음, 한 알림에 회신+버튼이 붙어 와도 분리, 시범 중 눌러도 진짜 `OK{n}` 유지, seq·시각, `GET /button`·`POST /button/simulate` — 엔드포인트 함수 직접 호출) |
| picar | `test_controller.py` | 45 | 속도 변환, I²C 바이트, LED 상태·소등, 정지 순서·재시도 |
| data | — | 0 | — |

**테스트가 없는 곳** (09-29 기준): 전 서비스의 `app.py` 엔드포인트(actuation `/button` 두 개만 있음), vision `model_store`·`templates`·`smoothing`,
actuation BLE 전송 실패 경로(`timeout`·`write_failed`·`microbit_unreachable`), picar `/health` degraded·자동 정지 타이머 실동작, data 전체, 통합 테스트 전부.
(→ 2026-10-04 정정: vision·actuation·picar `app.py` HTTP 테스트(TestClient, `c560bbd`), vision `model_store` 바꿔 끼우기(`860734f`), picar 자동 정지 타이머 경쟁·종료 시 정지(`899f6ba`)는 생겼다.
**남은 곳**: picar `/health` degraded, actuation BLE `write_failed`·`microbit_unreachable`, 스키마 대조(§6.1 #13-a), data 전체, 통합 테스트 전부)

**web 테스트가 앱 startup을 피하는 방식**: 폴링 스레드는 `app.py`의 startup 이벤트에서만 시작된다. 기존 테스트는
`backend.state_machine`을 직접 import하거나, 새 `FastAPI()`에 라우터만 붙여 startup을 트리거하지 않는다
(`test_judging_timing_spec.py:119-122`). 새 web 테스트도 이 방식을 따른다.

### 1.2 2026-09-28에 정리한 불안정 원인 (테스트 파일만 수정)

| 원인 | 조치 |
| --- | --- |
| vision `test_capture.py`가 import 시점에 테스트를 한 번 더 실행 | `__main__` 가드 |
| 고정 `sleep(0.15)` | 상태가 바뀔 때까지 폴링(최대 2초) |
| 셸 `CAMERA_MIRROR` 값에 따라 결과가 달라짐 | 테스트 안에서 고정 후 원복 |
| `test_gate.py`가 가짜 게이트를 원복하지 않음 | 원래 함수까지 복원 + `teardown_function` |
| `test_classify.py`의 `VALID_REASONS` 누락 2개 | 계약서 스키마 enum을 읽도록 변경 |
| picar `sys.modules` 단언이 실행 순서에 의존 | 검사 구간에서만 모듈을 빼고 되돌림 |
| `*_test.py` 수동 스크립트 3개가 수집됨 | `pytest.ini` `python_files = test_*.py` |
| strict 빠진 xfail이 구현 뒤 조용히 XPASS | `pytest.ini` `xfail_strict = true` |

검증: 전체 통과, 파일 순서 역순 실행 통과, `CAMERA_MIRROR=false` 통과, 스크립트 직접 실행 통과.

### 1.3 테스트를 쓰면 드러날 구현 결함 (미조치)

담당은 [14 §8](14_web_구현보고서.md) 분담을 따른다 — web 백엔드 `state_machine.py`는 **이동혁** 전담이다.

| 서비스 | 결함 | 근거 | 담당 |
| --- | --- | --- | --- |
| web | `/latest`가 JSON이 아니면 `ValueError`를 못 잡아 **폴링 스레드가 죽음** (14 §3의 "폴링 건너뜀"과 다름) | `state_machine.py:242-243` | 이동혁 ✅ (2026-09-28 `c8f1fd3` 병합으로 해소) |
| web | 본문 `status`를 보지 않고 HTTP 200이면 성공으로 셈 | `state_machine.py:177-201`, 03 §5-5 | 이동혁 (③) ✅ (2026-09-28 `c8f1fd3` 병합으로 해소) |
| web·actuation | `/command` web 타임아웃 1.5초 < actuation ACK 대기 2.0초 → 재시도 시 **이중 전송**. `_post_with_retry`는 읽기 타임아웃·5xx·4xx·연결 실패를 구분하지 않고 2회까지 보낸다 | `state_machine.py:177-201`, `ble_bridge.py:44` | 이동혁 (③) ✅ (2026-09-28 `c8f1fd3` 병합으로 해소) |
| actuation | BLE 회신을 보낸 명령과 대조하지 않음 → 늦게 온 이전 `OK{n}`을 다음 명령의 회신으로 받을 수 있음. (버튼 A 구현으로 `BTN:` 줄은 회신에서 분리됐다 — `_on_notify` `:74-89`. 명령 회신끼리의 대조 문제는 그대로) | `ble_bridge.py:193-195` | 송승호 ✅ (2026-10-03 `d81948b` — 기대 회신만 ACK로 인정) |
| picar | `{"led":"on"}`처럼 형식이 틀린 요청에 **500** | `controller.py:398` | 송승호 ✅ (2026-10-03 `899f6ba` — 객체가 아니면 없음으로 처리) |
| vision | landmark에 `x` 키가 빠지면 `KeyError`가 그대로 올라옴 | `normalize.py:113` | 이동혁 — 🟡 미해결(15 알려진 이슈), 제출 후 과제 |

---

## 2. 통합 테스트 계획

### 2.1 세 층 구조

| 층 | 무엇을 검증 | 어디서 | 실행 | 담당 에이전트 |
| --- | --- | --- | --- | --- |
| ① 계약 테스트 | 각 서비스 요청·응답이 `shared/schemas/*.json`과 03을 지키는가 | 프로세스 안(TestClient) | 개발 PC · CI | `sw-tester` |
| ② mock 통합 | docker compose로 4개 서비스를 띄워 web → actuation·picar 흐름이 도는가 | 컨테이너 | 개발 PC · CI | `sw-tester` |
| ③ 실물 E2E | RPi5·RPi4B에서 BLE·모터·LED로 시연 흐름이 도는가 | 실물 보드 (네이티브) | **수동 + 기존 스크립트** (pytest 아님) | `hw-tester` |

> **actuation·picar의 pytest 사용 범위 (2026-09-28 결정, 송승호)**: pytest는 **① 단위 테스트 확장(개발 PC·CI)**과
> ~~**워치독 조종 모드(09-29 구현 예정) 단위 테스트**~~(→ 2026-09-30 회의 **불채택**, 해당 없음)에만 쓴다. 실물 검증은 pytest `hw` 테스트를 만들지 않고
> `status.sh`·`aihand_test.py`·`load_test.py`와 육안 확인으로 한다(§2.4). 이유: 기존 스크립트가 이미 측정값과 기준 초과 표시를 내고,
> 반복 구동은 정격 초과 전압 서보를 닳게 한다. 보드 venv에 pytest를 설치해 단위 테스트를 돌리는 것도 하지 않는다 — 버전 확인은 CI(Python 3.11 고정 버전)가 맡는다.

### 2.2 ① 계약 테스트

- **호출하는 쪽**(web): 보내는 본문을 스키마로 검증한다.
- **호출받는 쪽**(vision·actuation·picar): 자기 `app.py` 응답을 스키마로 검증한다.
- **각 서비스의 `tests/` 안에서만** 검증한다. vision·actuation·picar는 `src/app.py`를 최상위 모듈 `app`으로 import해서, 한 프로세스에서 같이 import하면 서로 덮어쓴다.
- 03에 **없는** 인터페이스(`/latest`, `/reset`, `/health` 필드, `/result`·`/progress` 본문 형식, vision 호출 타임아웃)는 문서화가 먼저다. 문서가 없는 채로 테스트를 쓰면 현재 코드를 옮겨 적는 테스트가 된다.

| 서비스 | 엔드포인트 | 대조할 스키마·문서 |
| --- | --- | --- |
| vision | `GET /latest`, `POST /predict` | `judgment_result.schema.json` (03 §4) |
| actuation | `POST /command` | `aihand_command.schema.json` 요청, 03 §5-1·§5-5 응답 `status` |
| actuation | `POST /result`, `POST /progress` | 03 §5-3 (HTTP 본문 형식은 03에 없음 — 문서화 먼저) |
| actuation | `GET /button`, `POST /button/simulate` (버튼 A, 2026-09-28) | 03 §5-3 "actuation 버튼 조회 API" 표 |
| picar | `POST /picar` | `picar_command.schema.json` 요청, 03 §5-2 응답 |
| 전체 | `GET /health` | 03에 없음 — 문서화 먼저 |

### 2.3 ② mock 통합 테스트

#### 지금 막혀 있는 이유

| 이유 | 근거 |
| --- | --- |
| `MOCK_CAMERA=true`면 **손 미검출 프레임만** 발행 → 판정 단계에서 손 미검출 25회 연속(약 5초 — 09-28 점검 당시는 15회·3초) 뒤 SC-04로 넘어갈 뿐 판정이 없음 | `capture.py:191-207` |
| `/predict`는 `/latest`를 갱신하지 않음 → 밖에서 판정을 넣을 방법이 없음 | vision `app.py:96-99` |
| 모델 번들 `svm_classifier.joblib`이 저장소에 없음(gitignore) | `.gitignore`의 `services/vision/models/*.joblib` 규칙 |
| actuation·picar mock은 `mocked`만 돌려주고 **호출을 받았는지 확인할 수단이 없음** | `ble_bridge.py:203`, picar `controller.py` |
| compose에 healthcheck가 없음 → `docker compose up --wait`가 "실행됨"만 확인하고 "준비됨"은 보장하지 않음 | `docker-compose.yml` |

#### docker compose(mock) 점검 결과 (2026-09-28, 개발 PC Docker Desktop)

| 항목 | 결과 |
| --- | --- |
| 이미지 빌드 | ✅ web 259MB · actuation 260MB · picar 258MB · vision 1.53GB · data-tools 1.88GB |
| 기동·`/health` | ✅ 4개 running, 포트 8000~8003, web `/api/state` devices 3개 ok |
| 장치 호출(mock) | ✅ `/command` → `G1`, `/result` → `correct`, `/progress` → `P17` 모두 `mocked`(14~20ms), `/picar` → `ok` |
| 세션 흐름 | ✅ `/api/start` → `training` → 손 미검출로 **3.0초에 `camera_fail`(SC-04)** — 설계값(15회 × 0.2초)과 일치. `last_dispatch`는 끝까지 `null`(판정 없음) |
| pip 의존성 (Python 3.11, x86_64·aarch64) | ✅ 5개 서비스 전부 바이너리 휠로 설치 가능(lgpio는 `manylinux_2_34`, bleak의 Linux 의존성 dbus-fast 포함) |
| 발견 1 | picar 빌드 폴더에 SD 카드 이미지(`reference/`, 14.9GB, gitignore 대상)가 있어 빌드마다 전송됐다 → `services/picar/.dockerignore` 추가로 해결 |
| 발견 2 | `python:3.11-slim`의 기반이 **Debian 13(trixie)**로 바뀌어 있다. RPi 호스트는 Bookworm(Debian 12). 태그를 `python:3.11-slim-bookworm`으로 고정할지 검토(§6.3) |
| 발견 3 | 고정 버전과 실제 설치 버전이 다르다 — data-tools OpenCV 4.11.0(고정 4.10), vision 이미지 OpenCV 5.0.0(mediapipe가 끌어옴) |

#### web 통합(①-a·①-b·버튼 A) 뒤 재점검 (2026-09-29, `edb5da9` 기준)

| 확인 | 결과 |
| --- | --- |
| 단위 테스트 | ✅ 전체 158 통과 · xfail 0 (web 49, 2.2초) — 인수 테스트 22개가 구현 감지로 실제 테스트가 돼 전부 통과 |
| 프론트↔백엔드 계약 (sw-tester 코드 대조) | ✅ 불일치 없음 — `/api/state`·`/start`·`/confirm`·`/certificate`, 화면 id 30개, 예시 사진 7장 경로, 버튼 A가 읽는 장치 필드 |
| 스펙 대비 구현 | ✅ `phase`·`/api/confirm`(스페이스바·버튼 A 같은 경로), 호출 순서, 재시도 규칙(03 §5-5), CSV 17열 = 데모 CSV, below_tau/OOD 화면 안내만 |
| docker mock 실행 | ✅ 화면·사진 200, 시범 `/command`(G1) 17ms, **시범 단계에서는 3.5초 손 미검출에도 SC-04 안 감**, 버튼 A(`/button/simulate`) → **0.3초 안에 `judging`**, `/api/confirm` → `judging`, 판정 단계 손 미검출 **3.0초에 SC-04**, 중복 확인 무시, 로그 에러 없음 |
| mock에서 못 보는 것 | 정답·오답 뒤 장치 호출·시행 로그 CSV(판정이 없어 `logs/` 미생성) → 판정 주입 필요. 프론트 JS(⑨ CSV 내보내기·수료증·성공률)는 수동 확인 |
| 환경 요인 | web은 `services/web`에서 띄워야 한다(`StaticFiles(directory="frontend")` 상대경로) — `start_all.sh`·README §4.2 모두 그 폴더에서 기동 ✅ |

#### 새로 필요한 기능

| 기능 | 내용 | 담당 |
| --- | --- | --- |
| **판정 주입 (추천: stub vision)** | `/latest`·`/reset`·`/health` + 테스트용 `POST /_test/judgment`만 있는 작은 FastAPI를 `tests/integration/stubs/`에 둔다. CI용 compose에서 vision을 이것으로 바꾼다. vision 코드 무수정, mediapipe 이미지 빌드도 빠져 CI가 빨라진다. **대안**: vision에 `MOCK_CAMERA=true`일 때만 켜지는 주입 엔드포인트(vision 코드 수정) | 방식 결정 이동혁(R) · 승인 송승호(A) |
| **mock 호출 기록** | `MOCK_HARDWARE=true`일 때만 `GET /_mock/history`로 받은 명령 목록 반환 | 송승호 |
| **mock 장애 주입** | `MOCK_DELAY_MS`, `MOCK_FAIL=timeout\|error`로 지연·실패 흉내. ③ 재시도 규칙과 이중 전송 검증용. ⚠️ mock 경로는 BLE 전송 전에 반환하므로(`ble_bridge.py:202-204`) **BLE 잠금·재스캔 문제는 이것으로 검증할 수 없다** | 송승호 |
| **healthcheck** | `docker-compose.ci.yml`에서 **4개 서비스 전부**에 `python -c "urllib.request.urlopen('http://localhost:8000/health')"` (slim 이미지엔 curl 없음). 하나라도 빠지면 `--wait`가 그 서비스의 준비를 기다리지 않는다 | 공통 |
| **실행 스위치** | 루트 `conftest.py`에 `--run-integration` 추가 (`--run-hw`와 같은 방식). 없으면 compose를 안 띄운 PC에서 `pytest`만 쳐도 실패 | 공통 |

#### stub vision 인터페이스 (제안)

| 엔드포인트 | 동작 |
| --- | --- |
| `GET /health` | `{"status": "ok", "service": "vision-stub"}` |
| `GET /latest` | 마지막으로 주입된 판정(`judgment_result.schema.json` 형식). 주입 전에는 `{"is_reject": true, "reason": "no_hand", ...}` |
| `POST /reset` | `{"status": "ok"}` + 호출 횟수 기록 |
| `POST /_test/judgment` | 본문을 그대로 다음 `/latest` 응답으로 설정. 스키마 검증 후 저장 |
| `GET /_test/calls` | `/reset` 호출 횟수·시각 (S2 검증용) |

#### 시나리오

| # | 시나리오 | 판정 기준 | 선행 조건 | 파일 (제안) |
| --- | --- | --- | --- | --- |
| S1 | 기동 | 4개 서비스 `/health` 정상, web `/api/state` devices 연결됨 | healthcheck | `tests/integration/test_s1_boot.py` |
| S5 | 장치 장애·복구 | picar 컨테이너 정지 → web 계속 진행·devices unreachable → 재기동 → 복구 | 없음 | `test_s5_device_outage.py` |
| S7 | 계약 | 모든 응답이 스키마 통과 | jsonschema | `test_s7_contract.py` |
| S2 | 정답 1회 | 시작 → (①-a 시범·확인) → 정답 주입 → actuation·picar 호출 기록 확인 → 진행도 +1 → vision `/reset` 호출 | 판정 주입 · 호출 기록 · **①-a** | `test_s2_correct.py` |
| S3 | 오답·미판정 | 오답(1초 유지)·below_tau·OOD 주입 / 손 미검출 25회(약 5초) → SC-04 | 판정 주입 · ①-a | `test_s3_wrong_reject.py` |
| S4 | 완주 | 7종 → summary → 수료증 발급 | S2 | `test_s4_complete.py` |
| S6 | 지연·장애 | actuation 2초 지연 → `/command` **1회만** 전송 / picar 읽기 타임아웃 → **재시도 없음** | 장애 주입 · **③** | `test_s6_timeout_no_retry.py` |

S1·S5·S7은 web 구현과 무관하게 **지금 쓴다.**(→ 2026-10-04: 제출 전에는 쓰지 않았다 — **제출 후 과제**, §0.1) S2·S3·S4·S6은 명세 기준으로 미리 쓰되,
[test_judging_timing_spec.py](../services/web/tests/test_judging_timing_spec.py)처럼 **구현 감지 조건부 strict xfail**로 건다(§3.4 #5).
모든 통합 테스트에는 `@pytest.mark.integration`을 붙인다.

### 2.4 ③ 실물 E2E

#### 실행 방식

- 📌 **결정 (2026-09-28, 송승호)**: **실물 운영·시연은 네이티브 4개 프로세스**([README §1·§4](../README.md)), **Docker는 개발 PC mock 통합·CI 전용**. 2026-09-25 전 구간 통합도 네이티브로 했다.
- `docker-compose.hw.yml`(actuation·picar)은 **미검증·선택 사항**으로 남겨 두고 **시연 전에는 검증하지 않는다**(컨테이너 BLE 검증 항목은 보류). web의 `PICAR_URL`(`http://picar:8000`)을 덮어쓰지 않고, vision 이미지에는 picamera2가 없어서 compose로는 전 구간을 띄울 수 없다.
- 매번 실행의 번거로움은 **`scripts/rpi/` 스크립트(tmux)**로 줄인다 — 명령 하나로 기동·종료, SSH가 끊겨도 서비스 유지([17](17_실물실행_스크립트_사용법.md)).
- **운영에 Docker를 쓰지 않는 이유**:
  1. **보드가 2대로 나뉘어 compose 이점이 없다** — compose는 한 호스트의 여러 서비스를 한 번에 띄울 때 값을 한다. RPi4B는 picar 하나뿐이고, 보드마다 따로 띄워야 하는 건 네이티브와 같다
  2. **vision이 컨테이너로 못 간다**(아래 전제조건) — RPi5가 "vision 네이티브 + actuation·web Docker" 혼합이 되어 전부 네이티브보다 관리가 복잡해진다
  3. **검증된 경로가 네이티브뿐**이고, W4 마감(10-04)·시연영상 촬영(W5)까지 새 실행 방식을 검증할 시간이 없으며, KPI·지연에 이득이 없다
  - 포기하는 것은 **보드 환경의 재현성**이다. requirements 고정 버전과 보드 venv 절차(각 서비스 README)로 대신한다
- **2026-09-28 확인 — vision Docker는 CSI를 쓸 수 없다**: `MOCK_CAMERA=false CAMERA_SOURCE=csi`로 띄우면 `ModuleNotFoundError: picamera2` → `camera.state=error`, 손 미검출만 발행 → web은 판정 단계에서 손 미검출 25회 연속(약 5초) 뒤 SC-04(09-28 확인 당시는 15회·3초). 이때 **`/health` 최상위 `status`는 `ok`**라 web 장치 표시로는 카메라 고장이 안 보인다(네이티브도 동일 — §6.3 이동혁).
- **카메라 고장은 두 가지이고, 드러나는 방식이 다르다** (2026-09-28, 가짜 카메라로 재현 — 정상 40프레임 뒤 `read()`가 `None`만 반환 / 예외 발생 두 방식):

  | 경우 | vision 동작 | `/health` | web | 잡는 수단 |
  | --- | --- | --- | --- | --- |
  | ① **기동 시** 카메라 안 열림 (Docker의 picamera2 없음, 네이티브의 케이블·다른 프로세스 점유) | "손 미검출" 프레임을 계속 발행 (`capture.py:231-236`) | `status: ok`, `camera.state=error` | 판정 단계에서 손 미검출 **25회 연속(약 5초)** 뒤 SC-04 — 2026-09-29 조은수 결정(이전 15회·3초), 환경변수 `CAMERA_FAIL_STREAK_THRESHOLD`로 조정(03 §7, 14 D5) | 네이티브 `start_all.sh`가 기동 때 `camera.state=running` 확인 → 아니면 중단 |
  | ② **운영 중** 카메라 멈춤 (네이티브에서 현실적) | 새 프레임을 발행하지 않음 — 30회 연속 실패는 상태만 기록(`capture.py:251-255`), 예외면 캡처 스레드 종료(`:284-287`). 판정 루프는 새 프레임이 없으면 건너뛰어(`app.py:49-51`) **`/latest`가 마지막 판정에 고정** | `status: ok`, `camera.state=error`, `last_frame_age_ms`만 계속 증가(재현: 3초 뒤 2785 → 6초 뒤 5786) | web은 판정의 신선도를 보지 않고 고정된 값을 매 폴링 새 판정처럼 처리 — 마지막 값이 손 미검출이면 SC-04, 과도기·미판정 값이면 **화면이 멈춘 듯 보이고**, 이전 수신호의 확정 판정이면 다음 단계에서 **오답 1회** | `start_all.sh`로는 못 잡는다. `status.sh`의 `camera=error` 또는 `/health`의 `last_frame_age_ms` 증가로만 알 수 있음 |
- vision을 컨테이너로 돌리려면 다음이 **모두** 필요하다(시연 뒤 과제, vision 담당 이동혁과 협의):
  1. 기반 이미지 교체 — `debian:bookworm`(arm64) + Raspberry Pi apt 저장소·키링 → `python3-picamera2`(RPi판 libcamera). 시스템 Python용 패키지라 `python:3.11-slim`의 Python으로는 불러올 수 없다
  2. 카메라 장치 권한 — `/dev/video*`·`/dev/media*`·`/dev/v4l-subdev*`·`/dev/dma_heap`, `/run/udev`(읽기 전용). 현실적으로 `privileged: true`가 필요할 것으로 추정
  3. numpy 충돌 해결 — apt picamera2 계열(simplejpeg)은 시스템 numpy 1.x 기준, requirements는 `numpy>=2` (vision README의 `numpy.dtype size changed`)
  4. 모델 파일 2개를 보드에 복사, `MOCK_CAMERA=false`·`CAMERA_SOURCE=csi`, 보드에서 직접 빌드(인터넷 필요)
  5. 네이티브와 같은 성능 확인 — `camera.state=running`, 판정 약 26fps, 판정 지연 39~72ms 수준
  - USB 웹캠이면 지금 이미지(OpenCV 포함)에 `/dev/video0`만 넘겨도 될 가능성이 높지만(추정), 평가 데이터를 CSI로 찍었으므로 KPI를 다시 재야 한다

#### 자동 판정과 육안 확인

| 구분 | 항목 |
| --- | --- |
| 자동 판정 (스크립트 — 아래 표) | actuation `/health` `microbit_connected`, picar `/health` `hardware.i2c.reachable`, `/command` 7종 회신 `OK{n}`과 지연, `OK:CORRECT`·`OKP37` 회신, 주행 뒤 `motion_active=false` + `last_stop_error=null` |
| 사람이 확인 | AI Hand 손모양(펌웨어는 각도와 무관하게 OK 회신), micro:bit O/X, LED 색·동시 점멸·2초 소등(결선이 없어도 `ok`), **바퀴가 실제로 멈췄는지**(`motion_active`는 타이머 상태일 뿐이라 바퀴가 돌아도 false일 수 있음, 13 §4), 바퀴 방향, 전원 차단 후 재연결 |
| 알려진 한계 (실패로 판정 안 함) | micro:bit `music` 사용 금지(패닉 070) |

#### 실물 점검 도구 (pytest `hw` 테스트는 만들지 않음 — §2.1 결정)

| 확인할 것 | 도구 | 움직이나 |
| --- | --- | --- |
| 네 서비스 `/health`, 카메라 fps, BLE 연결, i2c, 온도·스로틀링 | `bash scripts/rpi/status.sh` ([17](17_실물실행_스크립트_사용법.md)) | 아니오 |
| AI Hand 7종 `OK{n}` 회신·지연, `/result`·`/progress` ACK(300ms 초과 🔴 표시) | `services/actuation/scripts/aihand_test.py --auto --repeat 1` | 서보 (7동작) |
| picar 주행·자동 정지·왕복 지연·실패 건수 | `services/picar/scripts/load_test.py` — **RPi5에서** `--url http://192.168.50.10:8000` | 바퀴 |
| web 없이 전 구간 (판정 → picar·micro:bit 반응) | `services/actuation/scripts/aihand_vision_picar_demo.py` | 전부 |

- 서보를 움직이는 점검은 **`--repeat 1`**로 최소화한다(정격 초과 전압, §2.4 안전·복구).
- 점검이 끝나면 picar는 stop + LED off 상태로 둔다. AI Hand는 별도 중립 명령이 없다(G5 주먹이 초기 자세 — 펌웨어 기준, hw 검토).
- 결과 수치는 11 §4.5·13 §4에 이미 쓰는 형식 그대로 기록한다.

#### 시행 당일 절차 (제안 — 기동 순서는 README §4.2)

**역할**: 학습자(카메라 앞) · 관찰자(AI Hand·LED·바퀴 육안 확인, **배터리 스위치 담당**) · 기록자(콘솔·육안 기록 양식)

1. RPi5·RPi4B 재부팅 → 양쪽 `vcgencmd get_throttled`가 `0x0`인지 확인. 이 값은 한 번 선 비트가 부팅 전까지 남으므로 **재부팅 직후** 기록한다(13 §2). ~~쿨러 장착 여부도 기록.~~ (→ 2026-10-04 정정: 쿨러 없이 선풍기 운용 확정(10-03) — **RPi5 선풍기를 켰는지** 기록, 17 §3.1)
2. micro:bit 펌웨어: 저장소 `aihand_control.ts`를 **통째로** 플래시했는지와 일자를 기록(08 펌웨어 불일치, README §4.1).
3. picar: 1회차는 바퀴를 띄우고, 이후 주행 공간 확보. **USB-C 어댑터 동시 연결 금지**(헤더 5V 역류 방지 없음). 배터리 스위치를 손 닿는 곳에 두고 누적 구동 시간 기록 시작(~~배터리 전압 측정 수단 없음~~ → 2026-10-04 팩 전압 11~12V 실측, 13 §4.4. 시연·리허설 전마다 다시 잰다).
4. 기동: **`bash scripts/rpi/start_all.sh`** — RPi4B picar → RPi5 actuation → vision → web을 tmux로 띄우고 1·4·5번 점검 일부(남은 uvicorn, `Discovering`, 모델 파일, 두 보드 커밋, `get_throttled`, `/health`)를 자동으로 한다([17](17_실물실행_스크립트_사용법.md)). 수동이면 터미널 1 RPi4B picar → 2 RPi5 actuation(먼저 `bluetoothctl show | grep Discovering` → `no`) → 3 vision `bash scripts/run_rpi5.sh` → 4 web(`PICAR_URL=http://192.168.50.10:8000`, `services/web` 폴더에서).
5. README §4.3 health 4종 확인: vision `model.loaded: true`·`camera.state: running`, actuation `microbit_connected: true`, picar `hardware.i2c.reachable: true`·`max_speed_pct: 50`, web devices 3개 ok. 실물 모드 확인(`MOCK_HARDWARE=false`로 띄웠는지, 응답에 `mocked`가 없는지).
6. AI Hand 화각 확인: 손을 치우고 AI Hand를 '정지' 자세로 둔 채 손 미검출이 나오는지(데모 스크립트의 화각 점검과 같은 방법).
7. 모니터링: RPi5 `watch -n2 'vcgencmd measure_temp; vcgencmd get_throttled'`, RPi4B `watch -n1 vcgencmd get_throttled`.
8. 종료: **`bash scripts/rpi/stop_all.sh`** — picar 정지 명령을 먼저 보낸 뒤 **역순 Ctrl+C**(web → vision → actuation → picar). 수동이면 같은 순서로 Ctrl+C. picar는 **정지 상태에서만** 끈 뒤 배터리 스위치 OFF.
9. 실행 환경 기록: `start_all.sh`가 남긴 `~/safesign_logs/<시각>/env.txt`(커밋·온도·`get_throttled`·`/health` 원문)를 06 §1-1에 옮긴다.

**육안 기록 양식** (시도마다 1행, 06 §1-2에 첨부)

| 시각 | 수신호 | AI Hand 손모양 (정상 / 알려진 한계 / 실패) | micro:bit O·X | LED 색·점멸·2초 소등 | 바퀴 방향·2초 뒤 정지 | 특이사항 |
| --- | --- | --- | --- | --- | --- | --- |

#### 안전·복구

| 상황 | 조치 |
| --- | --- |
| **비상정지** | 관찰자가 **배터리 스위치 OFF**(RPi4B도 꺼짐, SD 손상 가능성 감수 — 08, README §4.2). 프로세스가 살아 있으면 RPi5에서 `/picar` stop 전송 |
| 주행 중 프로세스 종료 | ~~Ctrl+C·`docker stop`·`kill -9` **어떤 방식이든** 모터는 마지막 명령을 유지한다. 종료 시 정지 처리가 없고~~ 자동 정지 타이머는 daemon 스레드다(picar `controller.py:193-195`, 11 §9) (→ 2026-10-04 정정: 2026-10-03 `899f6ba`부터 Ctrl+C·SIGTERM(`docker stop` 포함)이면 lifespan에서 정지를 쓰고 LED를 끈 뒤 종료 — ~~**실물 미검증**~~ → **2026-10-04 실물 확인**: Ctrl+C 약 0.5초 만에 정지, 주행 중 `stop_all.sh`로도 정지(17 §9). `kill -9`·전원 차단이면 여전히 마지막 명령 유지, 13 §5 #4) → 정지 상태에서만 끈다 |
| 바퀴가 안 멈춤 | 배터리 OFF → `/health` `last_stop_error` 기록 → 해당 회차 중단 (08 I²C 정지 유실) |
| micro:bit 끊김·리셋 | web 진행을 멈추고 `curl -X POST localhost:8002/progress -H 'Content-Type: application/json' -d '{"current":1,"total":7}'`로 재연결을 먼저 유도 → `microbit_connected: true` 확인 후 재개. 첫 명령이 재스캔으로 web 1.5초를 넘겨 이중 전송될 수 있다. 그래도 안 보이면 README §4.5·§4.6(`bluetoothctl disconnect <MAC>`, micro:bit 리셋) |
| actuation을 `kill -9`로 끔 | BlueZ에 연결이 남아 다음 실행 때 micro:bit가 안 보인다 → micro:bit 리셋 또는 `bluetoothctl disconnect` (README §4.5) |
| 서보 과부하 | 서보가 정격 초과(실측 7.46V, 11 §4.4)로 돈다. ~~**반복 상한 수치는 어느 문서에도 없다.**~~ 제안값: 세션당 연속 35동작 이하(2026-09-23 연속 검증 범위), 세션 사이 휴지 — ~~§6.4 결정 대기~~ → 2026-10-01 D4로 **연속 35동작 이하·2회차마다 휴식** 확정(§6.4). 10-02 측정은 휴식 기준을 지키지 못했다(06 §1-3) |

#### CI 연결

**하지 않는다.** RPi에 self-hosted runner를 붙이면 push마다 모터·서보가 움직이고, 공개 저장소라면 fork PR 코드가 보드에서 실행될 수 있다.

### 2.5 pytest 규칙

| 규칙 | 설정 위치 |
| --- | --- |
| `--import-mode=importlib` (actuation·picar의 같은 이름 `test_controller.py` 충돌 방지) | `pytest.ini` |
| `python_files = test_*.py` — 수동 스크립트는 `test_` 접두어를 쓰지 않는다 | `pytest.ini` |
| `xfail_strict = true` — 미구현 명세는 구현 감지 조건과 `raises=`로 좁혀 건다 | `pytest.ini` |
| 마커 `unit` / `integration` / `hw` — ⚠️ **현재 마커가 붙은 테스트는 0개**다. 그래서 `-m "not integration"`은 지금은 아무것도 거르지 않는다. 계약·통합 테스트를 쓸 때부터 붙인다. `hw`는 actuation·picar에서 쓰지 않기로 했다(§2.1) | `pytest.ini` |
| `--run-hw` (구현돼 있으나 **현재 사용처 없음**), `--run-integration` (예정) | 루트 `conftest.py` |
| 환경변수는 import 시점에 읽힌다 → `setenv`가 아니라 **모듈 속성을 monkeypatch** | 각 테스트 |
| 모듈 전역을 바꾸면 반드시 원복, 고정 sleep 대신 마감시간 있는 폴링 | 각 테스트 |
| web 테스트는 앱 startup(폴링 스레드)을 띄우지 않는다 (§1.1) | 각 테스트 |

### 2.6 로컬 실행 명령

| 목적 | 명령 (저장소 루트에서) |
| --- | --- |
| 전체 | `python -m pytest` |
| 서비스 하나 | `python -m pytest services/web` |
| 마지막 실패만 다시 | `python -m pytest --lf` |
| 실물 기동·종료·상태 (RPi5에서) | `bash scripts/rpi/start_all.sh` · `stop_all.sh` · `status.sh` ([17](17_실물실행_스크립트_사용법.md)) |
| 실물 장치 점검 (보드에서) | `python3 scripts/aihand_test.py --auto --repeat 1`(actuation) · `load_test.py`(picar, RPi5에서) — §2.4 표 |
| mock 스택만 띄워 보기 (개발 PC) | Docker Desktop 실행 → `docker compose up -d --build` → `docker compose ps` → `docker compose down` |
| mock 통합 (예정) | `docker compose -f docker-compose.yml -f docker-compose.ci.yml up -d --build --wait` 후 `python -m pytest tests/integration --run-integration` |
| CI 실패 재현 | CI와 같은 Python 3.11 가상환경을 만들고 `pip install -r services/<svc>/requirements-test.txt` 후 같은 명령 (§3.4 #1) |

---

## 3. CI 계획 (GitHub Actions)

저장소: `github.com/Lee35678/SafeSign_PhysicalAI` · `.github/workflows/ci.yml`(unit job만) 2026-10-03 `c55ea15` 추가 — 첫 실행은 Actions 허용 뒤(§3.1). integration job은 아직 없다.

### 3.1 사전 조건

| 조건 | 누가 |
| --- | --- |
| Settings → Actions 허용 | 저장소 관리자(Lee35678) |
| 브랜치 보호: `dev`·`main` PR 머지 전 unit job 통과 필수 | 저장소 관리자 |
| 비공개 저장소면 무료 한도 월 2,000분 → integration job은 PR·수동 실행 때만 | 팀 합의 |
| ✅ ~~미커밋 파일 커밋~~ → `conftest.py`·`pytest.ini`·`test_judging_timing_spec.py`·이 문서는 `dev`에 반영(2026-09-28 `67ef27b`·`a8f7640`·`d2503de`). `.claude/agents/`는 `.gitignore`의 `.claude/` 규칙에 걸려 **공유되지 않는다** — 공유하려면 `.gitignore`를 `.claude/*` + `!.claude/agents/`로 바꿀지 팀이 정한다 | 송승호 |
| `.pytest_cache/`는 조치 불필요 — 폴더 안의 자체 `.gitignore`가 스스로를 무시한다(v0.2의 "`.gitignore`에 추가" 항목은 틀린 내용이었다) | — |

### 3.2 파일 구성

```
.github/workflows/ci.yml            # unit job + integration job
docker-compose.ci.yml               # vision → stub 교체 + 4개 서비스 전부 healthcheck
tests/integration/                  # S1~S7, stubs/vision_stub.py
services/*/requirements-test.txt    # -r requirements.txt + pytest (+ httpx: actuation·picar·vision — web·portal은 requirements.txt에 이미 있음) — ✅ 5개 있음(2026-10-03 c55ea15). jsonschema는 계획(미추가, 계약 테스트와 함께)
services/picar/requirements-hw.txt  # 계획(미생성) — picar는 requirements-test.txt에서 gpiozero·lgpio를 빼고 적는 방식으로 대신
```

- 이름을 `requirements-test.txt`로 하는 이유: vision에 웹캠 스크립트용 `requirements-dev.txt`(opencv, pillow)가 이미 있다.
- ~~현재 pytest는 어느 requirements에도 없고, httpx는 web에만 있다. `requirements-test.txt`가 없으면 워크플로가 돌지 않으므로 **워크플로보다 먼저** 만든다.~~ → ✅ 해결(2026-10-03 `c55ea15`): 서비스별 `requirements-test.txt` 5개(actuation·picar·portal·vision·web)에 `pytest`, TestClient용 `httpx==0.27.2`는 actuation·picar·vision에 추가(web·portal은 `requirements.txt`에 이미 있음). `jsonschema`는 아직 어디에도 없다(계약 테스트 §2.2와 함께 추가할 계획).
- 루트 `tests/integration/`을 수집하려면 `pytest.ini` `testpaths`에 `tests`를 추가한다.

### 3.3 워크플로 초안

```yaml
name: ci
on:
  pull_request:
    branches: [dev, main]
  push:
    branches: [dev, main]
  workflow_dispatch:

jobs:
  unit:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false            # 한 서비스가 실패해도 나머지 결과는 보이게
      matrix:
        service: [web, actuation, picar, vision]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"  # Dockerfile(python:3.11-slim)과 같게
          cache: pip
      - run: pip install -r services/${{ matrix.service }}/requirements-test.txt
      - run: pytest services/${{ matrix.service }} -m "not integration" --junitxml=report.xml
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: report-${{ matrix.service }}
          path: report.xml

  integration:
    needs: unit
    if: github.event_name != 'push'   # PR·수동 실행 때만
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install pytest httpx jsonschema
      - run: docker compose -f docker-compose.yml -f docker-compose.ci.yml up -d --build --wait
      - run: pytest tests/integration -m integration --run-integration
      - if: failure()
        run: docker compose logs --no-color > compose.log
      - if: failure()
        uses: actions/upload-artifact@v4
        with: { name: compose-log, path: compose.log }
      - if: always()
        run: docker compose down -v
```

- 저장소 루트에서 `pytest services/<svc>`로 돌리므로 루트 `pytest.ini`·`conftest.py`가 그대로 적용된다.
- 서비스별로 job을 나누는 이유는 의존성 충돌이다(data `numpy==1.26.4` 대 vision `numpy>=2`). data는 테스트가 생기면 matrix에 추가한다.

### 3.4 첫 실행에서 실패할 가능성이 높은 곳

| # | 원인 | 확인 상태 | 대응 |
| --- | --- | --- | --- |
| 1 | **고정 버전으로 한 번도 돌려 본 적 없음.** 지금까지는 호스트 Python 3.13·fastapi 0.141·bleak 3.0으로만 통과. CI는 3.11·fastapi 0.115·httpx 0.27·bleak 0.22 | 실측 (버전 차이). 3.12 전용 문법은 코드에 없음 | 드러나는 실패를 고친다 — CI의 목적 ✅ 2026-10-03 서비스별 3.11 가상환경(Windows)에서 전부 통과. JPEG 인코더가 없으면 vision `test_preview`가 끝없이 기다리던 것을 건너뛰게 고침 |
| 2 | picar `lgpio==0.2.2.0`이 x86 러너에서 빌드 실패 | 추정 | `requirements-hw.txt`로 분리 (테스트는 mock 경로라 불필요) ✅ picar `requirements-test.txt`에서 gpiozero·lgpio 제외 |
| 3 | vision mediapipe·opencv가 CI **러너 호스트**에서 `libGL.so.1`을 못 찾을 수 있음. Docker 이미지는 Dockerfile이 `libgl1`을 설치해 문제없음을 확인했다(2026-09-28, 이미지 안 mediapipe 1.0.1·cv2 5.0.0 import 정상). mediapipe 1.x의 3.11용 휠(x86_64·aarch64)도 있음 | 추정 (러너만) | unit job에 `apt-get install -y libgl1 libglib2.0-0` 단계 추가 ✅ `ci.yml`의 vision job에 `libgl1 libglib2.0-0` 설치 단계 반영(러너에서 확인 전) |
| 4 | ✅ ~~미커밋 파일을 CI가 못 봄~~ → 커밋 완료 (§3.1) | 확인 | — |
| 5 | 스펙 인수 테스트의 xfail은 **구현 감지 조건부**다(`xfail(not PHASE_READY, strict=True)` 등, `test_judging_timing_spec.py:126-152`). 스펙 §8 이름대로 구현하면 조건이 바뀌어 **자동으로 일반 테스트가 된다 — 마커를 지울 필요 없음**. 빨간불이 나는 경우는 두 가지다: ① 감지는 됐는데 동작이 스펙과 다를 때(정상적인 실패), ② 이름이 스펙 §8과 달라 감지가 안 됐는데 동작은 맞을 때(strict XPASS) | 확인 (코드) | 구현 PR을 `dev`에 병합할 때(송승호, 14 §8 ⑪) 스펙 §8 이름과 대조한다 |

### 3.5 운영 규칙 (제안)

- unit job은 모든 PR·push에서, integration job은 PR·수동 실행에서만 돈다.
- 실패하면 머지하지 않는다. 고칠 수 없으면 xfail(strict, 사유·`raises=` 명시)로 걸고 이슈로 남긴다.
- 실물 E2E 결과는 CI가 아니라 06·13 리포트에 남긴다.
- `dev` 병합은 송승호가 단위 테스트를 붙이며 한다(14 §8). 병합 순서는 이동혁 백엔드 → 조은수 프론트엔드 → 김지훈.

---

## 4. 지연 분석

### 4.1 KPI 목표 (10_PRD §2.1)

| 지표 | 목표 | 정의 |
| --- | --- | --- |
| 판정 지연 (P95) | ≤ 1.0초 | 손 정지 시점 → 시스템 판정 확정 (기록값은 **현행(마지막 프레임) + 한계 명시** — 09-30 회의, §5.6 #1) |
| 물리 피드백 지연 (P95) | ≤ 2.0초 | ~~손 정지 시점 → AI Hand + picar + micro:bit 중 가장 늦게 완료되는 시점~~ → **web 판정 확정 → picar·micro:bit 반응 시작**(09-30 회의, "완료" 병기 — §5.6 #3, 03 §5-4) |

### 4.2 정답 한 번의 흐름 지연

| # | 구간 | 값 | 구분 · 근거 (측정 조건) | 담당 |
| --- | --- | --- | --- | --- |
| 1 | 카메라 프레임 간격 | 최대 33ms (30fps) | 실측 · 11 §3 | 이동혁 |
| 2 | 캡처 → 한 프레임 판정 (MediaPipe + SVM) | **39~72ms** | 실측 · 2026-09-25 web 없는 데모 7건, 쿨러 없음 (11 §9.3, 15) | 이동혁 |
| 3 | N=3 연속 프레임 확정 | 약 75ms (판정 26.6fps 기준) | N 잠정(05 §8-0), 시간 추정 | 이동혁 |
| 4 | web 폴링 대기 | 0~200ms (`VISION_POLL_INTERVAL_S=0.2`) | 코드값 | 이동혁 |
| 5 | `/command` → 제스처 후 회신 | **0.79~0.83초** (49건 794~825ms, 중앙 806) — web은 그동안 대기 | 실측 · 2026-09-23 RPi5 네이티브 `aihand_test.py` (11 §4.5). 펌웨어는 마지막 손가락 명령 150ms 뒤 회신하므로 서보 이동이 끝나기 약 50ms 전일 수 있다(펌웨어 코드 기준, 육안 완료는 별도) | 송승호 |
| 6 | `/result` → micro:bit ACK | 26~42ms (09-23) · 36~37ms (09-25 재검증). ACK를 먼저 보내고 O/X 1초는 백그라운드 표시 | 실측 · 11 §4.5 | 송승호 |
| 7 | `/progress` → micro:bit ACK | **32~38ms** (09-23) · 38~39ms (09-25 재검증) | 실측 · 11 §4.5 | 송승호 |
| 8 | `/picar` 왕복 (Wi-Fi + I²C 쓰기) | 13~21ms (09-24 AP 경유, 바퀴 띄운 벤치) · 19~21ms (09-25 AP 경유 데모) · P95 43~49ms (09-23 **공유기 경유** 바닥 주행 부하 시험). 응답은 I²C 쓰기가 끝난 뒤 온다 → "모터 명령 전달 시점"이며 바퀴 가속은 포함하지 않는다 | 실측 · 07, 11 §6·§9.3, 13 §4.1 · `controller.py:265-268` | 송승호 |
| 9 | picar 주행 | 2.0초 뒤 자동 정지 | 잠정 | 송승호 |

> ✅ **2026-09-28 `c8f1fd3`에서 권장 순서(`/picar` → `/result` → `/command` → `/progress`)로 바뀌었다**(sw-tester 코드 확인, `_dispatch_feedback`). 아래 문단과 §4.3의 "현재 순서" 열은 변경 전 기록이다.

**호출 순서 문제 (변경 전)**: web `_dispatch_feedback`은 5 → 6 → 7 → 8을 **차례대로** 보냈다. 그래서 `/command`의 0.8초가 끝나야
micro:bit·picar가 반응을 시작한다(판정 후 약 0.85초). web 없는 데모에서는 판정 확정 → 마지막 장치 반응 시작이
**25~47ms**였다(picar 19~21ms · micro:bit 25~47ms, 7건). 권장 순서는 **`/picar` → `/result` → `/command` → `/progress`**이고
결정은 이동혁 몫이다(스펙 §7.3). → **2026-09-28 이 순서로 반영**(`c8f1fd3`, 14 D11). 아래 표·계산은 변경 전 기준이다.

### 4.3 합계 (추정)

| 기준 | 변경 전 순서 | 권장 순서 (**2026-09-28부터 적용**) | KPI |
| --- | --- | --- | --- |
| 판정 확정 (1~4) | 약 0.15~0.35초 | 같음 | ≤ 1.0초 ✅ |
| 반응 **시작** | 약 1.2초 | 약 0.4초 | ≤ 2.0초 ✅ |
| 반응 **완료** — picar 제외 (시행 로그 `feedback_done_ms` 정의) | 약 2.0~2.2초 (판정 + 손 0.8 + ACK + LED 1.0) | 약 1.2~1.4초 (LED와 손 동작이 겹침) | 변경 전 ❌ · 권장 ✅ (→ 10-02 실측 P95 **1.089초**, 06 §2-3) |
| 반응 **완료** — picar 주행 포함 (10_PRD 정의 그대로) | 2.0초 초과 | 2.0초 초과 | ❌ picar 주행 2초만으로 초과 |
| 참고: 11 §8 계산 | 약 3.0초 — 판정을 KPI 예산 1.0초로 넣은 값 | — | — |

- 권장 순서의 1.2~1.4초는 **LED 백그라운드 표시 중에 `G` 명령 지연이 늘지 않는다는 가정**이다. 실측한 적이 없다.
- "완료" 기준이어도 **picar를 빼고 호출 순서를 바꾸면 달성 가능성이 있다.** 회의안건 안건 3의 판단 근거로 쓴다.

### 4.4 타임아웃·재시도로 늘어나는 최악 지연

변경 전 web `_post_with_retry`는 모든 장치 호출을 실패 원인과 상관없이 **최대 2회** 보냈다(`state_machine.py:177-201`).
> **2026-09-28 `c8f1fd3`**: `/command`·`/picar`의 읽기 타임아웃과 본문 실패는 재시도하지 않고, vision `/latest`는 0.5초 타임아웃이다.
> 그래서 아래 표의 `/command` 최악은 1.5초, `/picar`는 0.5초, `/latest`는 0.5초로 줄었다(연결 실패·4xx/5xx는 여전히 2회).

| 호출 | 1회 타임아웃 | 최악 | 문제 |
| --- | --- | --- | --- |
| `/command` | 1.5초 | **3.0초** | actuation ACK 대기 2.0초 > web 1.5초 → 재시도 시 **같은 동작 두 번** → ✅ ③ 읽기 타임아웃 재시도 금지 구현(2026-09-28 `c8f1fd3`) — 최악 1.5초 |
| `/result`, `/progress` | 0.5초 | 1.0초씩 | `/command`가 BLE 잠금을 최대 2초 쥐면 연쇄 타임아웃 가능 (추측) |
| `/picar` (정답일 때만 호출) | 0.5초 | 1.0초 | 읽기 타임아웃 뒤 재시도 → **주행 두 번** |
| 판정 1회의 장치 호출 합계 | — | **정답 약 6초 · 오답 약 5초** | 그동안 폴링 스레드가 멈춤 |
| vision `/latest` | **지정 안 됨** (httpx 기본 5초) | 5초 | vision이 멈추면 폴링도 5초씩 멈춤 |
| 장치 `/health` 점검 | 1.5초 × 3개, 5초 간격 | 화면 장치 상태가 최대 약 5초 늦음 | 표시 지연 |

### 4.5 설계상 대기 (일부러 둔 지연)

| 대기 | 값 | KPI와의 관계 |
| --- | --- | --- |
| 오답 확정 전 유지 `WRONG_CONFIRM_S` | 1.0초 (스펙 §4, 2026-09-28 구현) | ⚠️ 오답을 판정 지연에 넣으면 P95가 반드시 1.0초 초과 |
| SC-04 진입 (손 미검출) | 판정 단계 25회 연속 × 0.2초 ≈ 5초 (2026-09-29 결정, 이전 15회/3초 — 14 D5) | 화면 전환 기준, KPI 무관 |
| micro:bit O/X 표시 | 1.0초 | "완료" 기준 KPI의 구성 요소 |
| AI Hand 손가락 간격 | 150ms × 5 | 100ms 이하는 서보 3개가 겹친다 — **전류 재계산·연속 검증 전에는 쓰지 않는다**(11 §4.4) |
| picar 주행 · LED 유지 | 2.0초 (잠정) | picar를 "완료"에 넣으면 KPI 초과 |
| vision `/reset` 뒤 N프레임 재누적 | 약 75ms (추정) | 작음 |

### 4.6 기동·복구 지연

| 상황 | 지연 | 근거 |
| --- | --- | --- |
| actuation 기동 시 BLE 연결 | 스캔 최대 5초(`SCAN_TIMEOUT_S`) + `BleakClient.connect()`(타임아웃 미지정, bleak 기본값 10초로 추정) | `ble_bridge.py:43·94·106-108` |
| BLE가 끊긴 상태에서 명령 도착 | **잠금을 쥔 채** 스캔 + 연결 → **15초 이상 걸릴 수 있음**(추정). 쓰기가 실패하면 한 번 더 연결. web 1.5초 타임아웃을 크게 넘김 | `ble_bridge.py:165-191` |
| 다른 창의 `bluetoothctl scan on` | BLE 연결 자체가 타임아웃 | 08 |
| compose 기동 순서 | healthcheck 없음 → 처음 몇 초 web이 장치를 미연결로 봄 | `docker-compose.yml` |
| RPi5 열 스로틀링 (86.2°C, `0xe0008`, 09-25 web 전 구간 중) | 판정 fps 저하 → §4.2의 1~3 증가 | 11 §2.1, 08, 쿨러 미장착. → **선풍기 실측**(17 §10, 각 17분, RPi5 PLA 케이스 장착): 10-01 최대 76.3°C·판정 평균 29.7fps, 10-02 KPI 시행 구간 최대 68.6°C·평균 29.9fps, 둘 다 `0x0` — 2026-10-03 **쿨러 없이 선풍기 운용 확정**(시연·측정 때 필수). 여러 시간 연속 운용은 미측정 |

### 4.7 해결 우선순위

| 순위 | 문제 | 해결 | 담당 | 검증 |
| --- | --- | --- | --- | --- |
| 1 ✅ | `/command` 이중 전송 · `/picar` 이중 주행 | ③ 구현 (읽기 타임아웃 재시도 금지) — 2026-09-28 `c8f1fd3` | 이동혁 | 스펙 인수 테스트 + S6 (mock 장애 주입) |
| 2 ✅ | micro:bit·picar 0.85초 늦은 반응 | 호출 순서 변경 — 2026-09-28 `c8f1fd3` | 이동혁 | 시행 로그 `feedback_ms` |
| 3 ✅ | 판정 지연 측정 기준점 | §5.6 #1 결정 → 현행(마지막 프레임) + 한계 명시(09-30) | 팀 | — |
| 4 ✅ | 물리 피드백 시작 대 완료 | §5.6 #3 결정 → 시작으로 판정, 완료 병기(09-30) | 팀 | — |
| 5 ⬜ | BLE 끊김 시 잠금을 쥔 채 스캔·연결 — **미해결, 제출 후 과제**(15 TODO `actuation`) | 재연결을 요청 경로 밖으로, 또는 잠금 전 빠른 실패 | 송승호 | **가짜 bleak 단위 테스트** + 실물 확인(micro:bit 리셋 뒤 첫 명령 시간을 `aihand_test.py`로). mock 경로로는 검증 불가 |
| 6 ✅ | vision `/latest` 타임아웃 미지정 · 비JSON 미처리 | 타임아웃 0.5초, `ValueError` 처리 — 2026-09-28 `c8f1fd3` | 이동혁 | 단위 테스트 |
| 7 ✅ | 열 스로틀링 | ~~액티브 쿨러 장착~~ → 선풍기 운용 확정(2026-10-03) | 송승호 | 10-01·10-02 선풍기 측정 `0x0`·판정 평균 29.7·29.9fps(§4.6, 17 §10) |

---

## 5. KPI 측정 방법

### 5.1 정의와 계산

| KPI | 목표 | 계산 | 필요한 데이터 |
| --- | --- | --- | --- |
| 정답률 | ≥ 92% | 정답 / 전체 시도 | 시도마다 정답 클래스 · 예측 클래스 |
| 오분류율 | ≤ 3% | 다른 수신호로 판정 / 전체 시도 | 같음 |
| 미판정률 | ≤ 5% | 미판정(τ 미달·OOD) / 전체 시도 | 같음 |
| Macro F1 | ≥ 0.90 | 신호 7종 F1 평균 (negative 제외, 05 §7-1) | 혼동행렬 7 × 8 (예측 7종 + negative 열) |
| 치명 오분류 | 0건 | "정지"가 다른 판정으로 간 건수 — ~~**정의가 세 갈래로 나뉨**~~ (→ 2026-10-04 정정: 09-30 회의 A안 — **신호 7종으로 간 것만**, 미판정 제외(코드 유지), §5.6 #4) | 혼동행렬 "정지" 행 |
| 판정 지연 | P95 ≤ 1.0초 | 값을 모아 95번째 백분위수 (`numpy.percentile(x, 95)`) | 시도마다 시각 |
| 물리 피드백 지연 | P95 ≤ 2.0초 | 같음 — **반응 시작(`feedback_ms`)으로 판정**, 완료·손 기준 상한 병기(D1, 안건 3) | 시도마다 장치별 응답 시각 |

앞의 세 비율은 **배타적이라 합이 100%**다. 시행 로그 `outcome`과의 대응: `correct` → 정답, `wrong` → 오분류, `below_tau`·`out_of_distribution` → 미판정.

> ⚠️ **(2026-09-28) web 시행 로그에는 미판정 행이 없다.** 이동혁 결정(스펙 §5, 14 D10)으로 `below_tau`/OOD는 화면 안내만 하고
> CSV에 쓰지 않는다. 그래서 **온라인 경로(B)에서는 미판정률을 CSV만으로 계산할 수 없다**(데모 CSV와 같은 한계, §5.2 아래 표).
> ~~집계 방법은 §6.4 결정 대기에 올렸다.~~ → 2026-09-30 회의: **미판정률은 오프라인 경로만 쓴다**(§5.6 #5).

### 5.2 측정 경로 두 가지

| | A. 오프라인 (vision 단독) | B. 온라인 (실물 전 구간) |
| --- | --- | --- |
| 방법 | `record_dataset.py` 촬영(테이크마다 3프레임 JSON) → `evaluate_kpi.py` | 학습자가 web에서 7종 수행 → 판정 확정마다 CSV 1행 (스펙 §7) → 06 1부·2부 |
| 잴 수 있는 것 | 판정 성능 5개 | 7개 전부 |
| 현황 | ✅ **최종(2026-09-30)**: 팀원 3명(ext01~03) **210시도**(RPi5 CSI·PLA 카메라 거치대, 9/29 촬영), 공식 3연속 — 정답 95.2% · 오분류 0% · 미판정 4.8% · F1 0.974 · 치명 0 (05 §7-3, 원본 `document/results/kpi_offline_final_20260930.json`). ~~팀원 2명 105시도 잠정~~(JH·me01 파일은 `355f5e1`에서 제거), ~~ext03 9/22~~ 폐기 | ✅ **최종(2026-10-02)**: 팀원 1명(`SS-00003`) 13회차 **91시도**, 실행 코드 `fa3720f`, RPi5 PLA 케이스·카메라 거치대 설치·선풍기·영상 켬·바퀴 띄움 — 지연 2개 달성(§0, 06 §2-1·§2-3, 원본 [`results/kpi_online_20261002/`](results/kpi_online_20261002/)). 판정 성능은 참고치(정답 91/91) |
| 한계 | 지연 측정 불가(JSON에 캡처 시각 없음). ~~결과를 화면에 출력만 함(혼동행렬·CSV 파일 없음)~~ → `evaluate_kpi.py --out`으로 결과 JSON 저장(2026-09-29, `results/kpi_offline_final_20260930.json`). 온라인 쪽 `aggregate_kpi.py`도 `--out`으로 보고서·그림을 쓴다(§5.5). **판정 규칙이 운영과 다름**(§5.6 #7). 모델 번들이 저장소에 없어 다른 PC에서 재계산하려면 번들을 따로 받아야 함 | 과도 자세·손 미검출·SC-04·**`below_tau`/OOD**는 기록 안 함 → 오프라인과 모수가 다르고 미판정률은 CSV로 못 셈 |

**web 없는 데모 CSV로 대신 쓸 수 있는 범위** — [aihand_vision_picar_demo.py](../services/actuation/scripts/aihand_vision_picar_demo.py)의
`RECORD_FIELDS`(`:244-246`, 17개)는 스펙 §7.2 앞쪽 17열과 **이름이 같다.** 하지만 다음이 다르다.

| 차이 | 영향 |
| --- | --- |
| `outcome`이 `correct`·`wrong`·`timeout`·`skip` 네 가지뿐이다. `below_tau`·OOD는 안내만 하고 계속 기다리다 `timeout`으로 접힌다 | **미판정률을 데모 CSV로 계산할 수 없다**(`timeout`에 진짜 미판정과 단순 시간 초과가 섞임) |
| `aihand_ok`·`aihand_ms`, `feedback_done_ms`, `*_status`, `picar_led_ok`, `mocked`, `subject` 열이 없다 | 완료 기준 지연, 실물 여부 판별, 인물 단위 비교 불가 |
| 데모는 판정을 기다리는 동안 picar가 순항한다 | 데모의 `picar_ms`는 "동작 시작"이 아니라 "수신호 동작으로 전환한 시점" |
| 저장소에 있는 `services/actuation/aihand_vision_picar_20260925_215425.csv`(7행)는 `observe_ms` 열이 없는 **옛 형식**이다 | 병합할 때 열을 맞춰야 함 |

→ 데모 CSV는 **공통 지연 열(`vision_latency_ms`·`picar_ms`·`microbit_ms`·`feedback_ms`)을 web 결과와 비교하는 용도**로만 쓴다.

### 5.3 시행 로그의 지연 열 (요약, 원본은 [스펙 §7.2](proposals/web_판정_타이밍_스펙.md))

원점은 `t_dec`(판정 확정 시각)다.

| 열 | 계산 | 의미 |
| --- | --- | --- |
| `vision_latency_ms` | vision 응답 `latency_ms` | 판정 지연으로 쓰는 값 (**마지막 프레임 기준 — §5.6 #1**) |
| `picar_ms` | `t_dec` → `/picar` 응답 | picar 반응 시작 (모터 명령 전달 시점) |
| `microbit_ms` | `t_dec` → `/result` 응답 | micro:bit 반응 시작 |
| `aihand_ms` | `t_dec` → `/command` 응답 | AI Hand 동작 완료 (펌웨어 기준). ⚠️ 정답 자세는 시범과 같은 제스처라 손이 실제로는 움직이지 않는다 — 펌웨어가 손가락 5개를 150ms 간격으로 지시하는 시간(약 0.75초)이다(2026-10-02 슬로모션, 06 §2-3) |
| `feedback_ms` | `max(picar_ms, microbit_ms)` | 물리 피드백 **시작** 기준 |
| `feedback_done_ms` | `max(aihand_ms, microbit_ms + 1000)` | 물리 피드백 **완료** 기준 (picar 주행 제외) |
| `mocked` | 장치 응답에 `mocked`가 하나라도 있으면 `true` | `true` 행은 **실물 KPI에서 제외** |
| `subject` | `LOG_SUBJECT`, 없으면 로그인한 학습자의 사원 코드 | 대상자별 비교. **온라인 측정은 `LOG_SUBJECT` 없이 사원 코드로 구분**(10-01 D5) — 게스트 회차는 빈 값 |

시작·완료를 둘 다 기록하므로 "완료" 정의가 나중에 정해져도 **다시 잴 필요가 없다.**

### 5.4 시행 규모 (05 §7-2 — 검산 완료)

| 목적 | 필요 시행 | 계산 |
| --- | --- | --- |
| 정답률 ±5%p 오차(95% 신뢰) | 최소 **113회** | 1.96² × 0.92 × 0.08 / 0.05² ≈ 113.1 |
| "오분류율 ≤ 3%" 주장 (오분류 0건 유지, Wilson 95% 상한) | **125회** | 상한 z²/(n+z²): n=105 → 3.53%, 120 → 3.10%, 125 → 2.98% |
| "치명 오분류 0건" 주장 | 정지만 **30회 이상** | 05 §7-2 권장 |
| 팀 계획(초안) | 팀원 4명 × 7종 × 5회 + 외부인 1~2명 × 7종 × 10회 = **210~280회** | — (→ 실제: 오프라인 팀원 3명 **210시도**, 외부인 없음 — 09-30, §5.6 #5) |
| **지연 P95 ≤ 목표를 95% 신뢰로 주장** (10-01 D4) | 정답 **59회 이상** | 59개가 모두 목표 이하면 진짜 P95도 목표 이하(0.95^59 < 0.05). 그 이상은 순서통계량으로 상한 계산 → 10-02에 91회 |

⚠️ **온라인으로 210~280회를 시행하면 서보가 420~560동작 이상 움직인다**(시도마다 시범 `/command` + 판정 뒤 `/command`).
서보는 정격 초과 전압으로 돌고 있어(11 §4.4) 고장 위험이 크다. 판정 성능은 오프라인으로 확정하고 온라인은 지연 측정용 소규모로 하는 안(회의안건 안건 5)의 근거가 된다.

### 5.5 실물 측정 절차 (온라인)

1. **사전 점검** — §2.4 "시행 당일 절차" 1~7을 그대로 따른다. 추가로 기록할 것:
   - `curl :8001/health`의 모델 번들 메타데이터(`trained_at`, `sklearn_version`, `best_params`)를 06 §1-1에 기록. `repo_commit`은 Colab 노트북으로 학습한 번들에만 있다.
   - 기준 커밋, 호출 순서, τ·N 값, ~~쿨러 여부~~ 선풍기 켬 여부(10-03 선풍기 운용 확정), 재부팅 직후 `get_throttled`
   - 실물 모드 확인: actuation·picar를 `MOCK_HARDWARE=false`로 띄웠는지, vision `camera.state: running`. web CSV에서는 `mocked` 열이 전부 `false`여야 한다(데모 CSV에는 이 열이 없다)
2. **시행**: **측정용 계정으로 로그인**해 교육 시작(대상자 = 사원 코드, `LOG_SUBJECT` 미사용 — D5) → 7종 × n회(정답 59회 이상 — D4) → 2회차마다 휴식,
   서보 연속 35동작 이하 → 특이사항은 06 §1-3에 즉시 기록. 조건(D6): **선풍기·라이브 영상·`monitor.py` 켬**(17 §10), picar 바퀴 띄움 권장. 중간에 web을 재기동하지 않는다(CSV가 나뉨)
3. **집계**: §5.7 규칙대로 → 혼동행렬(`sklearn.metrics.confusion_matrix`) → F1 · 치명 오분류 → 지연 열 P95 · 히스토그램 → 대상자별 정답률
4. **집계**: `cd services/web && python scripts/aggregate_kpi.py <web_trials_*.csv> --out <폴더>` → 원본 CSV·보고서·그림을 `document/results/kpi_online_<날짜>/`에 보관
   (10-02 실행 기록: 06 §1-1·§1-2, [`results/kpi_online_20261002/`](results/kpi_online_20261002/))

### 5.6 측정 방법 결정 사항 → [회의안건_KPI측정방법](proposals/회의안건_KPI측정방법.md)

> ✅ **2026-09-30 회의 + 2026-10-01 지연 측정 결정(D1~D6, 송승호)으로 전부 확정**했다. 아래 "결정" 열이 최종이다. 미결로 남은 것 없음.

| # | 문제 | 영향 | 결정 |
| --- | --- | --- | --- |
| 1 | `latency_ms`는 **한 프레임**의 캡처→판정 시간이다(`classify.py:120-130`). vision `_cognition_loop`가 매 프레임 이 값을 그대로 `/latest`에 담고, N프레임 연속 확인은 별도로 한다(vision `app.py:44-65`). 그래서 N프레임 채우는 시간·폴링 대기가 빠진다. "손 정지 시점"은 시스템이 모른다 | KPI가 실제보다 좋게 나옴 | ✅ **현행(마지막 프레임) + 한계 명시**, 스키마 필드 추가 안 함(09-30). 물리 피드백에는 손 기준 보수적 상한(판정 지연 + 200ms + 반응 시작) 병기(D1). 첫 프레임 캡처 시각 필드는 향후 과제 |
| 2 | 오답은 1초 유지해야 확정 | 오답을 넣으면 P95가 반드시 1초 초과 | ✅ 판정 지연 모수 = **정답만**(D3, 10-01). 물리 피드백 모수도 정답만 — 오답 행은 picar를 부르지 않는다(D2) |
| 3 | 물리 피드백 시작 대 완료 | picar 주행을 넣으면 불가. picar를 빼고 권장 순서면 약 1.2~1.4초(추정, §4.3) | ✅ **시작으로 판정 + 완료 병기**(09-30). 10-02 실측 완료 P95 1.089초 |
| 4 | 치명 오분류 정의가 **세 갈래**: 01·10_PRD "정지를 다른 신호/클래스로 판정"(negative 포함 여부 불명) · 05 §7-1 "negative 포함"(근거로 01을 인용하지만 01에는 그 문구가 없음) · `evaluate_kpi.py:110-111` **미판정 제외**(= A안). `evaluator` 정의도 코드와 같다 | 정지→미판정을 치명으로 셀지 | ✅ **신호 7종만**(09-30) — 코드는 이미 이 방식, 05 §7-1 문구 정정 (결과는 어느 쪽이든 0건) |
| 5 | KPI를 어느 경로로 확정하나 · SC-04 처리 | 두 경로의 수치를 섞으면 안 됨 | ✅ 판정 성능 5개 = **오프라인**(팀원 3명 ext01~03 — 외부인 없음), 지연 2개 = **온라인**, 미판정률은 오프라인만(09-30). SC-04는 별도 집계 |
| 6 | 06 §2-4 "팀원(train/val) 대 외부인(test)" 틀이 04 §4와 다름 | 틀린 설명 | ✅ 표 틀은 고치지 않음(09-30) — 06 v3.8이 실제 분할 기준으로 행 이름만 취소선 처리 |
| 7 | ~~`evaluate_kpi.py`는 최빈값, 운영은 3연속~~ → ✅ **2026-09-29 결정: 공식 3연속, 최빈값 참고.** 비교(이동혁): 175테이크 중 7개가 갈림(전부 최빈값 정답 → 3연속 미판정), 오분류·치명 동일 | 팀원 105시도 미판정 2.9% → 6.7% | `evaluate_kpi.py` 두 규칙 병기·`--out` JSON 구현 |

### 5.7 집계 규칙 (`evaluator` 정의와 같게 — 2026-10-02 측정에 적용)

| 항목 | 규칙 |
| --- | --- |
| 제외 | `mocked=true` 행 전체 제외. 데모 CSV의 `timeout`·`skip`과 web `timeout`(판정 제한시간 10초 초과)은 분모에서 빼고 건수만 따로 적는다. web은 과도 자세를 원래 기록하지 않는다(스펙 §7.1). **행을 지우지 않고** 제외 기준과 건수를 보고서에 적는다 |
| 합계 확인 | 정답률 + 오분류율 + 미판정률 = 100%인지 확인 |
| 표본 수 표기 | 세부 구간(촬영자별·클래스별 등)이 n<30이면 수치 옆에 "(n=…)"를 붙인다 |
| 신뢰구간 | 오분류·치명 오분류처럼 **"0건" 주장에는 Wilson 95% 상한을 항상 병기**한다 |
| 달성 판정 | 점추정이 목표를 만족해도 Wilson 상한이 목표를 넘으면 **"잠정 달성"**으로 표기한다(05 §7-3 방식을 06에도 적용). **지연**은 P95의 95% 신뢰 상한(순서통계량)이 목표 이하일 때 "달성", n<59면 상한을 낼 수 없어 "잠정 달성"(10-01 D4) |
| subject 값 | ~~오프라인 `subject_id`와 온라인 `LOG_SUBJECT`를 같은 ID 체계로~~ → **온라인은 사원 코드**(10-01 D5, `LOG_SUBJECT` 미사용). 오프라인 ext01~03과 체계가 달라 06 §2-4에서 두 경로를 사람 단위로 잇지 않는다(온라인은 지연 측정용 참고) |
| 경로 병기 | 06 §2-1 표에 "경로"(오프라인/온라인) 열을 추가한다. 판정 성능 5개는 오프라인, 지연 2개는 온라인 값을 채우고, 온라인 판정 성능은 참고치로 병기한다 |
| 12 §0과의 관계 | 06 최종 수치가 12 §0과 다르면 12 §0은 "1차(잠정)"로 두고 06이 최신본임을 각주로 적는다. 두 결과를 합치지 않는다 |
| 재현성 | 숫자마다 입력 CSV 경로 · 행 수 · 필터 조건 · 스크립트를 남긴다 |

### 5.8 집계 스크립트 명세 — ✅ 2026-09-29 작성(`services/web/scripts/aggregate_kpi.py`, 조은수) · 2026-10-01 D1~D5 반영(송승호)

| 항목 | 내용 |
| --- | --- |
| 위치 | `services/web/scripts/aggregate_kpi.py` (오프라인 `evaluate_kpi.py`와 짝을 이루는 온라인용) |
| 입력 | `services/web/logs/web_trials_*.csv`(UTF-8 BOM), 비교용 데모 CSV `services/actuation/aihand_vision_picar_*.csv` |
| 출력 | 콘솔 요약표(§5.7 규칙 적용, 제외 건수 포함), 06 §2-1 요약표 · §2-2 혼동행렬 PNG(정지 행 강조) · §2-3 지연 히스토그램 PNG(`vision_latency_ms`·`feedback_ms`·`feedback_done_ms`) · §2-4 대상자별 표 |
| 10-01 변경 | 물리 피드백 모수 정답 행만(`--feedback-include-wrong`로 전체), 손 기준 보수적 상한 열, P95의 95% 신뢰 상한(`p95_upper`)과 그에 따른 달성 판정, 대상자 빈 행(게스트) 알림 — 테스트 `tests/test_aggregate_kpi.py` 15개 |
| 담당 | 작성 조은수 → ②-b KPI 집계는 **송승호**(09-30 회의 재배정) |
| 함께 고칠 것 | ~~`evaluate_kpi.py`도 결과를 화면 출력만 한다~~ → ✅ `--out` 결과 JSON(KPI 표·촬영자별·테이크별 판정, 2026-09-29 이동혁). 혼동행렬 PNG는 06 작성 때 |

---

## 6. 할 일

담당 구분은 [01 RACI](01_프로젝트계획서.md)와 [14 §8](14_web_구현보고서.md) 분담을 따른다. 다른 사람 몫은 **제안**이다.
목표일은 14 §8 일정(10-01까지 전부 `dev`, 10-02 재시험 ⑥, 10-03~04 KPI 실측·06 집계)에 맞춘 제안값이었다. W4 마감(10-04)이 지나 **끝나지 않은 항목의 목표일은 "제출 후 과제"로 바꿨다.**

**제출 시점 분류 (2026-10-04)** — 항목은 지우지 않고 분류만 한다. 아래 표의 각 행에도 같은 표시를 달았다.

| 분류 | §6.1 송승호 | §6.2 승인 대기 | §6.3 다른 사람 | §6.4 결정 대기 |
| --- | --- | --- | --- | --- |
| ✅ **완료** | #1 · 1-a · 2 · 4-a · 5 · 9 · 11 · 13 · 14 · 15 · 16 · 17 (#13-a는 일부) | KPI 확정 경로 · 판정 지연 모수 · 오프라인 판정 규칙 · 집계 규칙 | 이동혁 ①-a·②-a·③·호출 순서·오프라인 KPI · 조은수(①-b 대행·②-b·⑥ 재배정 완료) · 06 담당 정정 · 김지훈 ⑨⑩ | 호출 순서 · 온라인 미판정률 · 물리 피드백 시작/완료 · 판정 지연 기준점 · 치명 오분류 · 서보 반복 상한 · BLE 회신 대조 · web 재배정 · `MOTION_DURATION_S` 2초(13 §1) · SC-05 성공률·SC-04 임계값(현행 운용 — 웹 A 확인 기록 없음) |
| ⬜ **제출 후 과제** | #3 CI 첫 실행 · #4 60ms 여유 · #6 mock 호출 기록·장애 주입 · #7 계약 테스트 · #8 mock 통합·integration job · #10 BLE 잠금 · #12 AP 경유 부하 주행 반복 · #13-a 남은 것 | mock 판정 주입 방식 | 이동혁 normalize `KeyError`·vision 카메라 고장 표면화·문서 불일치 · 김지훈 data 테스트 · 저장소 관리자 Actions 허용 · 03 빠진 인터페이스(vision 엔드포인트는 03 §4-1에 정리됨, 10-04) · 기반 이미지 고정 · `.claude/agents/` 공유 | picar 주행 쓰기 재시도 |
| ✖ **폐기** | #13-b 워치독 조종 모드 단위 테스트 | — | — | 워치독 조종 모드(09-30 불채택) |

### 6.1 송승호 담당

| # | 할 일 | 목표 | 선행 | 에이전트 |
| --- | --- | --- | --- | --- |
| 1 | ✅ ~~테스트 정리분·이 문서·회의안건 커밋~~ → 완료(2026-09-28). `.claude/agents/` 공유 여부는 팀 결정(§3.1) | 09-28(월) | — | 직접 |
| 1-a ✅ | ~~**실물 스크립트 첫 검증**~~ → **완료(2026-09-29)** — RPi5+RPi4B, 바퀴 띄운 상태로 [17 §6](17_실물실행_스크립트_사용법.md) 체크리스트 전부 통과(SSH 끊김 내성·종료 뒤 BLE 연결 잔류 없음·재기동 정상 포함). 결과는 17 §9. 진행 중 RPi4B picar venv가 pip 없이 생성된 문제를 발견·해결(17 §8) | ⑥ 재시험(10-02) 전 | 두 보드 tmux 설치 | `hw-tester` |
| 2 | 서비스별 `requirements-test.txt`, picar `requirements-hw.txt` 분리 (Dockerfile 반영). 3.11 가상환경에서 먼저 설치해 본다 | ✅ 2026-10-03 `c55ea15` — `requirements-test.txt` 5개, 서비스별 3.11 가상환경에서 전부 통과. picar는 `requirements-hw.txt` 대신 테스트 파일에 gpiozero·lgpio를 빼고 적었다(Dockerfile·RPi4B 설치 절차 그대로) | — | 송승호 |
| 3 ⬜ | `.github/workflows/ci.yml` unit job → 초록불 (§3.4 #1~#3 해결) | 🟡 2026-10-03 `c55ea15` 작성 — GitHub 첫 실행(초록불)은 Actions 허용 뒤 → **제출 후 과제** | 2, 관리자 Actions 허용 | 송승호 |
| 4 ⬜ | [test_judging_timing_spec.py](../services/web/tests/test_judging_timing_spec.py) 보완: `test_changing_wrong_class_restarts_the_hold`의 시간 여유 60ms 확대, xfail에 `raises=` 지정(→ 2026-09-28 병합 후 xfail이 모두 풀려 해당 없음, 60ms 여유만 남음) | ~~09-29(화)~~ 미착수 → **제출 후 과제** | — | `sw-tester` |
| 4-a ✅ | **web ①-b 판정 타이밍 프론트엔드**(조은수 몫, 2026-09-29 송승호 대행) → `edb5da9` 구현(headless Chrome mock E2E 31/31), **`dev` 병합 완료**(2026-09-29, `db4cd41`, fast-forward) — 병합 후 전체 158 · web 49 회귀 재확인 통과 | ~~10-01(목)~~ **완료(09-29)** | — | 직접 |
| 5 ✅ | web 단위 테스트 ⑪: 구현 브랜치가 올라오면 병합 전에 붙이고 스펙 §8 이름과 대조 (§3.4 #5) → 백엔드 병합 완료(2026-09-28, 당시 web 35개 통과 → 2026-09-29 버튼 A web 연동 후 **web 49 / 전체 158 통과**, xfail 0). ⑨(`41ef97c`)·①-b(`db4cd41`) 병합 모두 반영, 회귀 재확인 완료. (→ 2026-10-03 현재 전체 **320** — web 124 · vision 78 · actuation 54 · picar 52 · portal 12) | 이동혁 백엔드 9/30 → 10-01 | 이동혁 ①-a·②-a·③ | `sw-tester` |
| 6 ⬜ | actuation·picar mock에 호출 기록(`/_mock/history`)·장애 주입(`MOCK_DELAY_MS`, `MOCK_FAIL`) | ~~09-30(수)~~ → **제출 후 과제** | — | 직접 |
| 7 ⬜ | actuation·picar 계약 테스트 (TestClient + jsonschema) | ~~09-30(수)~~ → **제출 후 과제** | 2 | `sw-tester` |
| 8 ⬜ | `docker-compose.ci.yml`(4개 healthcheck), vision stub(§2.3 인터페이스), `--run-integration`, S1·S5·S7 → integration job 추가 | ~~10-01(목)~~ → **제출 후 과제** | 판정 주입 방식 결정 | `sw-tester` |
| 9 ✅ | ~~picar 형식 오류 500 수정, BLE 회신 대조 여부 결정 (§1.3)~~ → **완료(2026-10-03)** — picar `899f6ba`(객체가 아니면 없음으로 처리, 200), BLE 회신 대조 고침 `d81948b`(기대 ACK만 인정, 나머지는 `ignored`). 둘 다 단위 테스트만 — 실물 미검증 | 완료(10-03) | — | 직접 |
| 10 ⬜ | BLE 끊김 시 잠금을 쥔 채 스캔·연결하는 문제 (§4.7 #5) — 가짜 bleak 단위 테스트로 검증 | ~~10-01(목)~~ → **제출 후 과제** | — | 직접 + `sw-tester` |
| 11 ✅ | ~~RPi5 액티브 쿨러 장착 → 재부팅 뒤 `get_throttled`·판정 fps 재측정 — **2026-09-29 ⑥ 재시험은 쿨러 없이 먼저 진행하기로 결정(보류), 장착 자체를 철회한 것은 아니다**~~ → **선풍기 운용 확정(2026-10-03 송승호 결정)** — 쿨러는 달지 않는다. 선풍기로 10-01 최대 76.3°C, 10-02 KPI 시행 구간 최대 68.6°C, 둘 다 `get_throttled=0x0`([17 §10](17_실물실행_스크립트_사용법.md)). 쿨러·선풍기 없이는 09-25 86.2°C·`0xe0008`. **시연·측정 때 선풍기 필수**(17 §3.1) | ~~결정 대기(보류)~~ 확정(10-03) | — | `hw-tester` |
| 12 ⬜ | **AP 경유 부하 주행 반복 측정** — `load_test.py`를 **RPi5에서** `--url http://192.168.50.10:8000`으로 실행(PC에서는 50번 대역에 닿지 않음, 07). AP 경유 왕복은 13~21·19~21ms로 이미 쟀고, 안 잰 것은 부하 주행 반복뿐이다 | ~~10-01(목)~~ → **제출 후 과제**(15 TODO `테스트·CI`) | — | `hw-tester` |
| 13 ✅ | 실물 점검(§2.4 도구 표)·당일 절차·비상정지 절차 준비. web ①-a와 무관한 장치 점검이라 먼저 한다 → §2.4에 정리했고, 이 절차로 ⑥ 재시험(09-29)·KPI 온라인 측정(10-02)을 했다 | 완료 | — | `hw-tester` |
| 13-a | **actuation·picar 단위 테스트 확장**(pytest, 개발 PC·CI): ~~picar 잘못된 요청 → 500(알려진 결함, strict xfail)~~, `/health` degraded, 자동 정지 타이머 발동, 주행 쓰기 실패 → `partial` / actuation BLE `timeout`·`write_failed`·`microbit_unreachable`, 끊긴 상태의 잠금 보유 재스캔, 늦은 회신 오귀속, `app.py` TestClient + 스키마 대조 (→ 2026-10-04 정정: 🟡 **일부 진행**(10-03) — `899f6ba` picar 자동 정지 타이머 경쟁·종료 시 정지·null 입력 테스트, `d81948b` BLE 늦은 회신 오귀속·재연결 테스트, `c560bbd` actuation·picar HTTP 테스트(TestClient). picar 500 결함은 `899f6ba`로 해결돼 xfail 항목 없음. **남은 것: `/health` degraded, BLE `write_failed`·`microbit_unreachable`, 스키마 대조** — 15 TODO) | ~~09-30(수)~~ 일부 진행(10-03) → 남은 것은 **제출 후 과제** | — | `sw-tester` |
| 13-b ✖ | ~~**워치독 조종 모드 단위 테스트** — 구현 계획서 §5 목록(타이머 재무장, `decide()` 표, 데모 표 ↔ web 표 일치, 기존 테스트 전부 통과)~~ (→ 2026-10-04 정정: **해당 없음** — 조종 모드 09-30 회의 불채택, §6.4) | ~~09-29(화) 구현과 함께~~ — | ~~조종 모드 회의 결정~~ — | `sw-tester` |
| 14 ✅ | ~~web 전 구간 재시험 ⑥~~ → **완료(2026-09-29)** — 쿨러 없이 진행(위 #11), §2.4 당일 절차로 스펙 §6 체크리스트 6개·모터·LED·AI Hand·O/X·종료 소등·"다시 학습하기" 재진입 전부 확인(14 §6.2). 재시험 중 결함 2건 발견·당일 수정·✅ 실물 재검증 통과(`cb8a25b`, 14 §7) | 완료(09-29) | ~~①-a·①-b 병합~~ ✅ 완료(09-29) | `hw-tester` |
| 15 ✅ | KPI 측정방법 회의 진행 (안건 5·2 결정권자) → 2026-09-30 회의, 안건 2는 10-01 D3(§5.6) | 완료(09-30) | 회의 전 준비 | `pm` |
| 16 | ✅ ~~08 리스크 레지스터에 새 리스크 후보 반영 (§6.5)~~ → 완료(2026-09-28, 08 신규 행). 이후 상태 갱신은 회의 때 08에서 | 회의 후 | 15 | `pm` |
| 17 ✅ | **완료(2026-09-29, `cb8a25b`)** — ⑥ 재시험 중 발견한 2건의 **실물 재검증** — 먼저 RPi5에 새 코드가 올라갔는지 `curl -s localhost:8000/api/state`에 `max_attempts` 확인. SC-04를 유발해 재시도(버튼·Space·A) → 시범 단계 + 재시범이 되는지, 한 수신호에서 일부러 3회 틀리거나(오답 1초 유지) 10초 넘게 버텨 3회째에 다음 수신호로 넘어가는지(14 §7) | ⑥ 최종 재시험 전 | 코드 수정·단위 테스트 완료(14 §7) | `hw-tester` |

### 6.2 승인 대기 (송승호가 A)

| 항목 | R | 필요 시점 | 늦어지면 막히는 것 |
| --- | --- | --- | --- |
| ⬜ mock 통합의 판정 주입 방식 (stub 대 vision 훅) — **제출 후 과제** | 이동혁 | 6.1 #8 전 | S2~S4 |
| ~~KPI 확정 경로·시도 범위 (§5.6 #5)~~ ✅ 판정 성능 오프라인·지연 온라인(09-30) | 송승호(재배정) | — | — |
| ~~판정 지연 모수 (§5.6 #2)~~ ✅ 정답만(10-01 D3) | 송승호(재배정) | — | — |
| ~~오프라인 판정 규칙 (§5.6 #7)~~ ✅ 3연속(2026-09-29) | 이동혁 | — | — |
| ~~집계 규칙 (§5.7)~~ ✅ 10-02 측정에 적용 | 송승호(재배정) | — | — |

### 6.3 다른 사람 담당 (제안 / 확인 필요)

| 담당 | 할 일 | 근거 |
| --- | --- | --- |
| **이동혁** (vision R · web 백엔드 전담) | ✅ ~~①-a 판정 타이밍 · ②-a 시행 로그 CSV · ③ 본문 status 판정·재시도 규칙~~ → 2026-09-28 `c8f1fd3` 병합 | 14 §8 |
| 이동혁 | ✅ ~~호출 순서 결정·반영(스펙 §7.3), `/latest` 비JSON 처리·vision 호출 타임아웃 지정~~ → 2026-09-28 `c8f1fd3` | §4.7 #2·#6 |
| 이동혁 | 판정 주입 방식 의견, ~~ext03 반영 오프라인 KPI 재계산~~(✅ 결과 → ext03 폐기), ~~두 판정 규칙 비교~~(✅), ~~`evaluate_kpi.py` 결과 파일 출력~~(✅ `--out`) · ~~팀원 3명 210시도 최종 측정~~(✅ 2026-09-30 — 5개 달성, 05 §7-3) | §2.3, §5.6 #7, §5.8 |
| 이동혁 | ⬜ normalize `KeyError` 처리(제출 후 과제), ~~vision `requirements-test.txt`~~(✅ 10-03 `c55ea15`, 송승호), ~~(결정 시) 스키마 필드 추가~~(09-30 추가 안 함으로 결정), 05 §7-1 치명 오분류 문구 정정 | §1.3, §5.6 #1·#4 |
| 이동혁 | ⬜ (제출 후 과제) 문서 불일치 정리: data 8종(negative 포함) 대 vision 7종, 특징 차원 설명(63차원 대 joint23), `train_svm.py` 게이트 기본값 주석 | vision·data 점검 결과 |
| 이동혁 | ⬜ (제출 후 과제 — 03 §7 "미해결") vision 카메라 고장 표면화 — 제안: ① `/health`: `camera.state=error`이거나 `last_frame_age_ms`가 기준(예: 2초)을 넘으면 최상위 `status`를 `degraded`로(picar의 I²C 불통 처리와 같은 방식) ② 운영 중 카메라가 멈추면 `/latest`를 마지막 판정에 고정하지 말고 명시적 상태(예: `no_hand` 또는 새 reason — 스키마 enum 변경이면 03 갱신)로 바꾼다 ③ (web 백엔드) 장치 패널에 vision `camera.state` 표시 | §2.4 카메라 고장 표 (2026-09-28 재현) |
| **조은수** (web 프론트 · 성능측정 R) — ~~2026-09-29부터 조은수 사정으로 프론트엔드는 송승호 대행, 나머지는 담당 재배정 대기~~ (→ **2026-09-30 회의 재배정 확정**: ②-b KPI 집계·06 2부·⑥ web 재시험 = **송승호**(완료), ⑦ 14 보고서·⑧ 화면 캡처 = **조은수** — 09-30부터 web 다시 담당) | ✅ ~~①-b 판정 타이밍 화면~~ → 2026-09-29 송승호 대행 `edb5da9`, **`dev` 병합 완료**(`db4cd41`). ✅ ~~②-b 로그 검증·KPI 집계(§5.7·§5.8), ⑥ 재시험~~ → 송승호 완료(⑥ 09-29, KPI 10-02). **⑦ 14 보고서, ⑧ 화면 캡처 — 조은수** | 14 §8 |
| ~~조은수 → (재배정 대기)~~ → 송승호(06 2부, 09-30 재배정) | ~~06 §2-4 표 틀 수정~~(→ 09-30 회의: 수정 안 함, §5.6 #6), 06 §2-1에 "경로" 열 추가, 06 §1-1 환경 기록에 온도·호출 순서·커밋 추가 | §5.6 #6, §5.7 |
| 조은수 | ✅ ~~06 §1-3 이슈 표의 담당 표기 갱신~~ → 06 v3.2에서 정정 완료(2026-09-28, 백엔드 = 이동혁) | 06 §1-3, 14 §8 |
| **김지훈** (data R · web ⑨⑩) | ✅ ~~⑩ 수신호 예시 사진 7장, ⑨ 결과 내보내기~~ → 완료: ⑩ `c2260a8`·⑨ SC-05 결과 저장 CSV `679aeb9` → `dev` `41ef97c` 병합 | 14 §8 |
| 김지훈 | ⬜ (제출 후 과제 — data 테스트 0개, 2026-10-04) data 테스트(데이터셋 JSON 스키마 검증) · 자체 촬영 데이터 확인: 좌표 6자리 반올림 안 됨, ext03 210건 `variant` 누락, ext03 `정지_t09` handedness 혼재 | 04 §2-4·§6 |
| **저장소 관리자 (Lee35678)** | ⬜ (제출 후 과제 — 2026-10-04 허용 대기, 15 TODO) Settings → Actions 허용, `dev`·`main` 브랜치 보호 | §3.1 |
| 전원 | ⬜ (제출 후 과제) 03에 빠진 인터페이스(`/latest`, `/reset`, `/health`, `/result`·`/progress` 본문) 문서화 여부 — 문서 대조는 `spec-keeper`. vision `/health`·`/latest`·`/reset`은 2026-10-04 03 §4-1에 정리됨 | §2.2 |
| 서비스별 담당 (web 이동혁·조은수(~~프론트 → 송승호 대행~~ 09-30부터 다시 조은수), vision 이동혁, data 김지훈, actuation·picar 송승호) | ⬜ (제출 후 과제 — 15 기술 부채 "의존성 잠금") Dockerfile 기반 이미지를 `python:3.11-slim-bookworm`으로 고정할지, requirements 고정 버전과 실제 설치 버전 차이(OpenCV) 정리 — 제안 | §2.3 점검 결과 |
| 전원 | ⬜ (제출 후 과제 — `.gitignore`는 아직 `.claude/`) `.claude/agents/`(테스트·PM 에이전트)를 저장소로 공유할지 — 공유하면 `.gitignore` 수정 | §3.1 |

### 6.4 결정 대기 (2026-10-04: 남은 것은 picar 주행 쓰기 재시도, SC-05 성공률·SC-04 임계값의 웹 A 재확인 — 둘 다 현행 값으로 운용 중. 나머지는 결정 완료·폐기)

| 안건 | 결정권자 | 필요 시점 | 늦어지면 막히는 것 |
| --- | --- | --- | --- |
| ✅ ~~장치 호출 순서 변경 (스펙 §7.3)~~ → `/picar` → `/result` → `/command` → `/progress`로 결정·반영(2026-09-28) | 이동혁 | — | — |
| ✅ ~~**(신규) 온라인 미판정률 집계 방법**~~ → **미판정률은 오프라인만**(09-30 회의). 아래는 당시 기록 — web CSV에 `below_tau`/OOD 행이 없음(14 D10). 예: 시도 제한시간을 두고 넘기면 `timeout` 행을 쓰기 / 미판정률은 오프라인(A)만 쓰기 (§5.1 주의). 2026-09-29: web `timeout` 행 생김(판정 제한시간 10초) — `aggregate_kpi.py`는 기본 제외, `--timeout-as-reject`로 미판정 계산(둘 다 가능, 결정만 남음) | 조은수(성능측정 R — ~~2026-09-29~ 재배정 대기~~ → 09-30 KPI 집계는 송승호) ↔ 이동혁 | 10-03 KPI 실측 전 | 01 KPI 미판정률, 06 §2-1 |
| ✅ ~~물리 피드백 "시작" 대 "완료"~~ → **시작으로 판정, 완료 병기**(09-30) (picar 변경안 안건 2 · KPI 측정방법 안건 3) | 이동혁(요구사항 A — 11 §10 #4·14 §9와 같게), 회의에서 전원 확인 | 10-03 전 | KPI 달성 여부 판정 |
| ✅ ~~판정 지연 기준점 · 스키마 필드 추가~~ → **현행 + 한계 명시, 필드 추가 안 함**(09-30) (§5.6 #1) | 전원 | 10-03 KPI 실측 전 (②-a는 2026-09-28 구현됨) | 판정 지연 KPI 신뢰성 |
| ✅ ~~치명 오분류 정의 통일~~ → **신호 7종만**(09-30) (§5.6 #4) | 이동혁 | 10-03 전 | 06 §2-2 |
| ✅ ~~**서보 반복 상한 수치와 온라인 시행 규모**~~ → 연속 35동작 이하·2회차마다 휴식, 정답 59회 이상(10-01 D4). ⚠️ 10-02 측정은 휴식 기준 미준수(06 §1-3) (§2.4, §5.4) | 송승호 | ⑥ 재시험(10-02) 전 | 서보 고장, 온라인 시행 계획 |
| ✅ ~~BLE 회신 대조를 고칠지, 알려진 한계로 둘지~~ → **고침**(2026-10-03 `d81948b`, 정상 경로는 10-04 실물 확인 — 11건 짝 일치, 재연결·늦은 회신 경로는 미확인) | 송승호 | — | — |
| ⬜ picar 주행 쓰기 재시도 — **제출 후 과제**(13 §5 #7 확인 중, 주행 I²C 실패 1.4%). ✅ `MOTION_DURATION_S` 2.0초는 스키마 `duration_ms` 미채택(09-27)으로 자동 정지 기본 2초 운용(13 §1) | 송승호 | — | 13 §5 #7 |
| ✅ ~~**(신규 2026-09-29) web 조은수 몫 재배정** — ②-b 로그 검증·KPI 집계, ⑥ 재시험(공동), ⑦ 14 보고서, ⑧ 화면 캡처 (프론트엔드는 송승호 대행 중)~~ → **2026-09-30 회의 확정**: ②-b KPI 집계·06 2부·⑥ web 재시험 = 송승호(완료), ⑦ 14 보고서·⑧ 화면 캡처 = 조은수 | 팀(회의) | ⑥ 재시험(10-02) 전 | ⑥·06 2부 KPI 수치·⑦⑧ 제출물 ([08](08_리스크레지스터.md) 신규 행) |
| 🟡 **(신규 2026-09-29) SC-05·SC-06 "성공률" 이름·정의** → **"첫 시도 정답"(O/X, 전체 k/7)로 조은수 결정·반영(2026-09-29, 14 §9)** — `firstTry()` 한 곳. (→ 2026-10-04: 이 정의로 운용 중, 웹 A 확인 기록은 찾지 못함 — 사람 확인 필요) | 결정권자 재확인 필요(웹 A 이동혁) — 원래 조은수 | 결과보고서·⑧ 캡처 전 | KPI 정답률과 혼동 |
| 🟡 **(신규 2026-09-29) SC-04 임계값** → **25회(약 5초)로 조은수 결정·반영(2026-09-29, 14 D5)**, 환경변수 `CAMERA_FAIL_STREAK_THRESHOLD`. (→ 2026-10-04: 코드 기본 25, 03 §7 장애 대응표도 이 값 기준. 웹 A 확인 기록은 찾지 못함 — 사람 확인 필요) | 결정권자 재확인 필요(웹 A 이동혁) — 원래 조은수 | ⑥ 재시험에서 조정 | 시연 중 SC-04 오진입 |
| ✅ ~~**(신규 2026-09-29) picar 워치독 조종 모드 채택 여부** — `/drive` 미구현(회의 결정 먼저)~~ (→ 2026-10-04 정정: **2026-09-30 회의 불채택** — `/drive`는 구현하지 않고 향후 과제, 15 TODO `picar` 절·[구현 계획](proposals/picar_워치독_조종모드_구현계획.md)) | 회의(범위 해석 이동혁 — 01 제외 범위 "연속 제스처·동작 추적") | — | ~~6.1 #13-b, 조종 모드 시연 편입~~ — |

**회의 전 준비 (제안)**: ext03 반영 KPI·두 판정 규칙 비교(이동혁), 호출 순서 의견·②-a 구현 일정(이동혁), 집계 규칙 초안(조은수 → ~~2026-09-29~ 재배정 대기~~ 09-30 송승호 재배정, 10-02 측정에 적용 — §5.7).

### 6.5 08 리스크 레지스터 반영 후보 — ✅ 2026-09-28 08에 반영 완료

> 아래 표는 발견 당시의 기록이다. **현재 가능성·상태는 [08](08_리스크레지스터.md)이 기준**이고, 회의 때 08에서 갱신한다.

| 리스크 | 가능성 | 영향 | 대응 | 상태 |
| --- | --- | --- | --- | --- |
| 고정 버전(Docker Python 3.11)으로 테스트를 돌린 적 없음 | 중간 | 시연 보드에서만 드러나는 실패 | CI unit job (§3) | 해결 (2026-10-03 서비스별 3.11 가상환경에서 320개 통과, CI 첫 실행 전) |
| mock과 실물의 동작 괴리 (mock은 `mocked`만 반환, 지연·실패 없음) | 높음 | mock 통과가 실물 동작을 보장 못 함 | mock 장애 주입 + 실물 E2E (§2.3·§2.4) | 미착수 |
| 판정 지연이 실제보다 작게 기록됨 | 확정(코드) | KPI 근거 신뢰성 | §5.6 #1 결정 | 확인 중 |
| 오프라인 판정 규칙이 운영보다 느슨 | 확정(코드) | 오프라인 KPI 과대평가 가능 | §5.6 #7 비교 | 확인 중 |
| `/command`·`/picar` 재시도로 이중 동작 | 확정(코드) | 시연 중 AI Hand·picar 오동작 | ③ 구현 | 해결 (2026-09-28 `c8f1fd3`, 단위 테스트 — 실물 미검증) — 08 |
| **온라인 KPI 시행의 서보 누적 구동** — 시도당 `/command` 2회 이상 × 210~280회 = 420~560동작 | 높음 | 정격 초과(124%) 서보 고장 → 시연 불가 | 판정 성능은 오프라인, 온라인은 지연 측정용 소규모, 세션 상한 | 미착수 |
| **실물 E2E 실행 방식 미통일** — hw.yml은 실물 전 구간 미검증, web `PICAR_URL` 오버라이드 없음 | 중간 | 시행 당일 기동 실패 | 네이티브로 통일(§2.4) — 2026-09-28 운영 방식으로 결정. 스크립트(17) 실물 첫 검증 대기 | 방침 확정 · 대응 중 — 08 |
| 카메라 고장이 `/health`에 드러나지 않음 (`camera.state=error`여도 `status: ok`), **운영 중 고장이면 `/latest`가 마지막 판정에 고정** | 중간 | 시연 중 카메라가 죽어도 web은 정상 표시 — 화면 멈춤·오답 1회·SC-04 중 무엇이 될지 마지막 값에 달림, 원인 파악·복구 지연 | vision `degraded`·`/latest` 고정 해소 + web 장치 패널 표시(§6.3). 그 전까지 기동 시는 `start_all.sh`, 운영 중은 `status.sh` | 미착수 |
| 주행 중 프로세스 종료 시 모터 계속 회전 (종료 시 정지 처리 없음) | 낮음 (08 기존 행에 통합) | 차체 돌진·낙하 | 정지 상태에서만 종료, 관찰자가 배터리 스위치 담당 (§2.4), `stop_all.sh`가 정지 명령 먼저 | 절차 보강 · 코드 해결 (2026-10-03 `899f6ba` — picar 종료 시 정지·LED 소등, 실물 미검증) — 08 |

---

## 7. 변경 이력

| 버전 | 일자 | 내용 |
| --- | --- | --- |
| v1.1 | 2026-10-10 | 송승호 — 재점검 버그 수정·리팩토링(15 10-10) 뒤 단위 테스트 수 갱신: **331개 통과**(web 129 · vision 80 · actuation 56 · picar 53 · portal 13, `feature/picar` `996b67b`) — §0·§0.1·§1.1. §2.3·§3.1의 `.gitignore:42`·`:54` 줄번호 인용을 규칙 문구로(줄번호가 바뀌어 틀린 줄을 가리켰다). §3.2: `requirements-test.txt` 해결 반영, `requirements-hw.txt`·`jsonschema`는 계획(미생성)으로 표시 |
| v1.0 | 2026-10-04 | 송승호 — **제출 시점 정리.** 머리말 "초안"·D-day 표기 정리. **§0.1 제출 시점 결론** 신설(수행한 것 / 수행하지 않은 것과 사유 / 미시험 범위와 대응 — 03 §7·08 연결). 단위 테스트 수를 2026-10-04 `60231a6` 실행 결과(**320개 통과** — web 124 · vision 78 · actuation 54 · picar 52 · portal 12)로 §0·§1.1에 반영(파일별 수 표 추가, 09-29 표는 기준선 기록으로 유지), §1.1 "테스트가 없는 곳" 정정. §0 portal 행(12개·CI matrix 포함·교육장 연동 10-04 확인)·회원 DB 행·계약/mock 통합 행(제출 후 과제)·결론 1~3. §2.1 조종 모드 불채택 표시. §2.3·§2.4 SC-04 진입을 현행 25회(약 5초, `CAMERA_FAIL_STREAK_THRESHOLD`, 09-29 조은수 결정)로. §2.4 종료 시 정지 10-04 실물 확인·배터리 11~12V·서보 반복 상한 D4. §4.3 완료 기준 실측 1.089초, §4.7 #5 미해결 표시. §5.1 미판정률 집계 결정, §5.2 `--out` 반영, §5.4 실제 시행 규모. **§6을 완료 / 제출 후 과제 / 폐기로 분류**(분류표 + 행 표시, 경과한 목표일 → 제출 후 과제). 수치(KPI·지연) 변경 없음 |
| v0.22 | 2026-10-04 | 송승호 — **RPi5 선풍기 운용 확정(10-03)** 반영: §0 실물 E2E(web) 행, §2.4 당일 절차 1번(선풍기 기록), §4.6 열 행에 10-01·10-02 선풍기 측정(17 §10 인용), §4.7 #7, §6.1 #11. 물리 피드백 "시작" 판정·"완료" 병기, 판정 지연 "현행(마지막 프레임) + 한계"를 §4.1·§4.7 #3·#4에 반영(09-30 회의). §2.4 안전·복구 "주행 중 프로세스 종료" — picar 종료 신호 시 정지·LED 소등(`899f6ba`, 실물 미검증, `kill -9`·전원 차단 제외). §6.1 #9 완료(`899f6ba`·`d81948b`), §0 단위 테스트·#5에 현재 320개. §6.3·§6.4 담당 표기를 09-30 재배정 확정으로(②-b·06 2부·⑥ 송승호, ⑦·⑧ 조은수), §6.4 BLE 회신 대조 결정 완료. §5.1 치명 오분류 정의 09-30 A안, §6.4 조종 모드 09-30 불채택(#13-b 해당 없음), §6.1 #13-a 일부 진행(`899f6ba`·`d81948b`·`c560bbd`)·남은 항목 정리 |
| v0.21 | 2026-10-03 | 기술 부채 정리 반영(송승호) — CI `ci.yml`·`requirements-test.txt` 작성(§0·§3·§3.4·§6 할 일 #2·#3), 고정 버전(3.11) 첫 통과(320개), §1.3 BLE 회신 대조·picar 형식 오류 해결, §6 리스크 2행 상태 갱신 |
| v0.20 | 2026-10-02 | 실물 점검 "알려진 한계" 칸 정리 |
| v0.19 | 2026-10-02 | **KPI 지연 2개 온라인 측정 완료**(송승호) — §0 KPI 두 행·결론 4, §5.1 물리 피드백 판정 기준, §5.2 B 현황, §5.3 subject(사원 코드), §5.4 지연 59회, §5.5 절차(로그인·휴식·조건·집계), §5.6 결정 열(09-30 회의 + 10-01 D1~D6), §5.7 timeout 제외·지연 달성 규칙·subject, §5.8 10-01 변경·담당, §6.2·§6.4 결정 반영. 원본 `document/results/kpi_online_20261002/`. (머리말 v0.18은 이력 행 없이 올라가 있었음) |
| v0.17 | 2026-09-29 | ⑥ 재시험 결함 2건 **실물 재검증 통과**(`cb8a25b`) — SC-04 재시도·시도 횟수 상한. §0 실물 E2E(web) ✅, §6.1 #17 완료. web 전 구간 실물 검증 종료 — 다음은 KPI 실측(§5)·CI(#2·#3) |
| v0.16 | 2026-09-29 | ⑥ 재시험 결함 2건 **재수정** — 1차 수정이 실물에서 해결되지 않음(커밋 전이라 RPi에 없었고, SC-04 재시도가 판정으로 돌려 다시 튕기며, below_tau/OOD만 나오면 판정이 안 끝나 상한이 무의미). SC-04 재시도 → 시범 단계, 판정 제한시간 10초. §0 170 통과, §6.1 #17 확인 절차 갱신 |
| v0.15 | 2026-09-29 | **⑥ web 전 구간 실물 재시험 통과** — 쿨러 없이 진행(#11 보류, 철회 아님). 스펙 §6 체크리스트 6개·모터/LED·AI Hand·micro:bit O/X·종료 시 LED 소등·"다시 학습하기" 재진입까지 전부 확인(14 §6.2). 재시험 중 결함 2건 발견·당일 수정: (1) SC-04 "재시도" 버튼 무동작(카메라가 계속 손을 못 잡으면 못 빠져나옴) → `POST /api/camera_retry` 신설, (2) 시도 횟수 무제한 → `MAX_ATTEMPTS_PER_SIGNAL=3` 도입(14 §2·§4.1·§7). 회귀 테스트 3건 추가, 전체 162 통과. §0·§6.1 #11·#14·신규 #17에 반영. **남은 것: 이 2건의 실물 재검증뿐** |
| v0.14 | 2026-09-29 | **R3 완료** — 버튼 A 실물 확인 4항목(정상 경로·시범 도중 무시·판정 중 무시·seq/G동작 중/O·X 표시) 전부 통과. 도중 시범 응답 전 폴링이 확인을 조기 확정하던 타이밍 결함을 발견해 당일 수정(`_poll_button` 게이트)·회귀 테스트 추가(전체 159 통과)·실물 재검증까지 완료(08, 11 §9.1 v1.24). §0 실물 E2E(web) 행에서 남은 선행 조건을 쿨러(R2)뿐으로 정리 |
| v0.13 | 2026-09-29 | **R1(1-a) 완료** — RPi5+RPi4B 실물에서 [17 §6](17_실물실행_스크립트_사용법.md) 체크리스트 전부 통과(기동·SSH 끊김 내성·종료·BLE 연결 잔류 없음·재기동). 진행 중 picar venv가 `python3-venv` 없이 pip 없는 상태로 생성된 문제 발견·해결(17 §8). §0·§6.1 #1-a에 완료 반영. 남은 실물 선행 조건은 쿨러(R2)·버튼 A 실물 확인(R3)뿐 |
| v0.12 | 2026-09-29 | **U1 완료** — ①-b(`edb5da9`) `dev` 병합 fast-forward(`db4cd41`), `origin/dev`까지 반영 확인. 병합 뒤 회귀 재실행(전체 158·web 49 통과, xfail 0). §0 실물 E2E(web) 행·§6.1 #4-a·#5·#14·§6.3 조은수 행에 병합 완료 표시 |
| v0.11 | 2026-09-29 | web 통합(`edb5da9`) 뒤 재점검 결과를 §2.3에 추가(sw-tester 계약·스펙 대조 + docker mock 흐름 확인). §0 결론 3·§4.2·§4.3·§4.4에 호출 순서·재시도 규칙 해소(`c8f1fd3`) 표시. 본인 할 일 스냅샷: archive/할일_송승호_2026-09-29.md (→ 2026-10-01 `dcceee6`에서 삭제됨 — 저장소에 없음) |
| v0.10 | 2026-09-29 | 산출물 갱신(pm 점검) — 머리말 상태 기준(`dev` `41ef97c` + `feature/picar` `edb5da9`)·D-day(D-5·D-9). `edb5da9`(①-b 화면, 송승호 대행, mock E2E 31/31)에서 고친 §0 실물 E2E(web) 행에 "①-b `dev` 미병합·실물 스크립트 미검증" 추가. §1.1 날짜, §6.1 #4-a(①-b) 신설·#5 web 49 / 전체 158·#2~#4 목표일(09-29) 경과 → 재조정 필요, §6.2 조은수 R 3건 → 재배정 대기·필요 시점 10-03 전, §6.3 ①-b·⑨⑩ 완료, 조은수 몫 재배정 대기, §6.4 신규 4행(web 재배정·성공률 정의·SC-04 임계값·조종 모드), §5.8 담당 |
| v0.9 | 2026-09-29 | micro:bit 버튼 A web 연동(스펙 §9) — §0 단위 테스트 158개, §1.1 web 테스트 파일 추가 |
| v0.8 | 2026-09-29 | web 백엔드 병합(`c8f1fd3` → `dev` `1da641b`) 반영(송승호) — §0 단위 테스트 144 통과·xfail 0, 실물 E2E·KPI 지연 막는 것 갱신, §1.3 web 결함 3건·§4.7 #1·#2·#6·§6.1 #5·§6.3 이동혁 할 일·§6.4 호출 순서·§6 리스크 해소 표시, §4.3·§4.4에 변경 후 상태 주석, §4.5 `WRONG_CONFIRM_S` 구현. **신규 결정 대기**: `below_tau`/OOD를 CSV에 쓰지 않아 온라인 미판정률을 CSV로 못 셈(§5.1 주의·§6.4) |
| v0.7 | 2026-09-28 | 문서 간 일관성 점검(`spec-keeper`) 반영 — §6.1 #16(08 반영)·§6.3 06 담당 정정을 완료 처리, §6.4 물리 피드백 "완료" 정의 결정권자를 이동혁(요구사항 A, 11 §10 #4·14 §9와 같게)으로 통일, §6.5를 "08 반영 완료 — 현재 상태는 08 기준"으로 닫고 상태 3건을 08 값에 맞춤 |
| v0.6 | 2026-09-28 | **결정 반영**: 실물 운영·시연은 네이티브, Docker는 개발 PC mock 통합·CI 전용(송승호) — §0 결론 5, §2.4 실행 방식에 결정·근거 3가지(보드 2대로 compose 이점 없음, vision 컨테이너 불가로 혼합 운영, 검증 경로·일정)·포기하는 것(보드 재현성), `docker-compose.hw.yml` 미검증·선택 사항·시연 전 검증 안 함. **추가**: vision Docker CSI 불가 재현 결과와 `/health`가 카메라 고장에도 `ok`인 문제(§2.4), **카메라 고장 두 경우 표(기동 시 / 운영 중 — 운영 중이면 `/latest`가 마지막 판정에 고정, 가짜 카메라로 재현)**, §6.3 이동혁 행(제안 3가지), §6.5 리스크 후보 1행·실행 방식 행 "방침 확정" |
| v0.5 | 2026-09-28 | 버튼 A(`b5e83a5`) 반영 — 테스트 144개(122 통과 · 22 xfail), actuation 29개(버튼 9개), §2.2 계약 대상에 `GET /button`·`POST /button/simulate`, §1.3 BLE 회신 행에 "버튼 줄은 분리됨, 명령 회신 대조는 남음". `ble_bridge.py` 인용 줄번호 6곳을 새 위치로(`:44`·`:193-195`·`:203`·`:202-204`·`:43·94·106-108`·`:165-191`). 이 문서의 발견 사항을 산출물에 반영: 08 신규 8행, 06 §1-3 6행·담당 정정, 13 §5 #9·#10·#4 보강, 14 §7 2건, 15 개발로그 항목·TODO |
| v0.4 | 2026-09-28 | **결정 반영**: actuation·picar의 pytest는 단위 테스트 확장(개발 PC·CI)과 워치독 조종 모드에만 쓴다(송승호). §2.4 "hw 테스트 목록"을 "실물 점검 도구"(`status.sh`·`aihand_test.py`·`load_test.py`·데모 스크립트) 표로 교체, §2.5 `hw` 마커·`--run-hw` 사용처 없음 표시, §2.6·§4.7 #5 검증 방법 변경, 할 일 13-a(단위 테스트 확장)·13-b(워치독 단위 테스트) 추가 |
| v0.3 | 2026-09-28 | **정정**: `.pytest_cache/`는 자체 `.gitignore`로 이미 무시되므로 조치 불필요(§3.1·§6.1 #1), `.claude/agents/`는 `.gitignore:54`로 공유되지 않음을 명시, 커밋 완료 반영(`67ef27b`·`a8f7640`·`d2503de`). **추가**: docker compose(mock) 빌드·기동·장치 호출·SC-04 전환 점검 결과와 발견 3건(§2.3 — picar 빌드 폴더 14.9GB → `.dockerignore`, 기반 이미지 trixie, OpenCV 버전 차이), 시연에 Docker를 쓰지 않는 이유와 vision 컨테이너화 전제조건(§2.4), 실물 스크립트 `scripts/rpi/` 연결(§0·§2.4 당일 절차 4·8·9·§2.6, [17](17_실물실행_스크립트_사용법.md)), 할 일 1-a 스크립트 실물 첫 검증, §6.3 기반 이미지 고정·에이전트 공유 여부 |
| v0.2 | 2026-09-28 | `sw-tester`·`hw-tester`·`evaluator` 검토 반영. **정정**: web 백엔드 담당을 14 §8대로 이동혁으로(①-a·②-a·③), `/progress` 실측 32~38·38~39ms, web 없는 데모 반응 시작 25~47ms(마지막 장치 기준), `/command` 회신 시점 단서, 완료 기준 합계 재계산(picar 제외 현재 2.0~2.2 · 권장 1.2~1.4초), 100ms 간격 문구, BLE 재연결 시간(스캔 + 연결), 실물 실행 방식을 네이티브로, `motion_active` 판정에 육안 정지 확인 추가, 장치 호출 합계(정답 6·오답 5초), 스펙 xfail은 구현 감지 조건부라 마커 제거 불필요(§3.4 #5), 데모 CSV는 공통 지연 열만 비교 가능, 치명 오분류 정의 3갈래(코드는 이미 A안), 측정 절차의 `get_throttled`·`repo_commit`·`mocked` 확인 방법, AP 경유 측정 범위. **추가**: 계약 테스트 대상표, stub vision 인터페이스, 시나리오별 파일명, 실물 hw 테스트 목록, 시행 당일 절차·역할·육안 기록 양식·안전·복구, 로컬 실행 명령(§2.6), 마커 사용 현황, 표본 계산 검산, 온라인 시행의 서보 누적 위험, 집계 규칙(§5.7)·집계 스크립트 명세(§5.8), 할 일 일정을 14 §8에 맞춤, 결정 대기·리스크 후보 추가 |
| v0.1 | 2026-09-28 | 최초 작성. 테스트 준비 상태 점검(서비스 4개 병렬 조사), 테스트 불안정 원인 정리 결과, 통합 테스트 3층 구조·시나리오 S1~S7, GitHub Actions 계획, 지연 분석, KPI 측정 방법과 미결 사항 7건(회의안건 연계), 담당별 할 일 |
