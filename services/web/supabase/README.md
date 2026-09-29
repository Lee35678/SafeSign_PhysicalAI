# Supabase 설정 — 회원가입·로그인·회원별 학습 결과

web 백엔드(`backend/members.py`)가 회원 정보와 학습 결과를 Supabase에 저장한다. 브라우저는 Supabase에 직접
접근하지 않고, 키는 교육장 RPi5의 환경변수에만 둔다.

**키가 없으면 로컬 모드로 동작한다** — 회원은 `services/web/data/members_local.json`(비밀번호는 scrypt 해시),
결과는 `data/results_local.jsonl`. 개발·리허설은 키 없이 해도 된다. 로컬 모드 회원은 Supabase로 옮겨지지 않는다.

## 1. 프로젝트 만들기 (한 번)

1. <https://supabase.com> → New project. 리전은 **Northeast Asia (Seoul)**.
2. **SQL Editor** → New query → [`schema.sql`](schema.sql) 전체를 붙여 넣고 **Run**.
   `members` · `training_sessions` · `training_results` 테이블과 `save_training_session` 함수가 생긴다.
3. **Project Settings → API** 에서 두 값을 복사한다.
   - Project URL — `https://<프로젝트ID>.supabase.co`
   - `service_role` 키 (secret) — ⚠️ 모든 권한이 있는 키다. git·채팅·화면에 올리지 않는다.

이메일 인증 메일 설정은 필요 없다. 백엔드가 관리자 API로 **인증을 마친 계정**을 만든다(교육장에서 메일을 확인할 수 없으므로).

## 2. web에 키 넣기

RPi5에서 web을 띄우는 셸(또는 `scripts/rpi/common.sh`를 쓰는 경우 그 환경)에:

```bash
export SUPABASE_URL=https://<프로젝트ID>.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=<service_role 키>
```

Docker로 띄울 때는 저장소 루트 `.env`(git에 올리지 않는다)에 같은 두 줄을 넣으면 `docker-compose.yml`이 넘긴다.

확인: `curl http://localhost:8000/api/auth/me` → `"store": {"backend": "supabase", ...}`. `"local"`이면 키가 안 들어간 것이다.

## 3. 인터넷이 끊겼을 때

| 상황 | 동작 |
| --- | --- |
| 가입·로그인 중 끊김 | "인터넷에 연결되지 않아…" 안내 → **게스트로 학습** 가능. 게스트 결과는 회원 DB에 올리지 않고 `data/results_local.jsonl`에만 남긴다 |
| 학습 결과 저장 중 끊김 | `data/results_pending.jsonl`에 쌓고 **30초마다 자동 재전송**. 화면에는 "연결되면 자동 저장"으로 표시. 같은 결과가 두 번 저장되지 않는다(세션 ID) |
| Supabase가 저장을 거부(4xx) | `data/results_rejected.jsonl`에 오류와 함께 남긴다 — 보통 `schema.sql`을 안 돌린 경우 |

`services/web/data/`는 `.gitignore`에 들어 있다(개인정보).

## 4. 저장되는 것

| 테이블 | 한 행 | 주요 열 |
| --- | --- | --- |
| `members` | 회원 1명 | `member_code`(SS-00001, 자동), `email`, `name`, `org`, `created_at` |
| `training_sessions` | 7종을 끝까지 학습한 1회 | `member_code`, `started_at`, `completed_at`, `total_attempts`, `first_try_correct` |
| `training_results` | 그 회차의 수신호 1종 | `order_no`, `signal`, `attempts`, `match_score`(정답 시 일치율) |

비밀번호는 Supabase Auth(`auth.users`)가 보관한다 — 우리 테이블에는 없다.

회원별 기록 보기 (SQL Editor):

```sql
select m.member_code, m.name, s.completed_at, s.total_attempts, s.first_try_correct
from public.training_sessions s join public.members m using (user_id)
order by s.completed_at desc;
```

## 5. KPI 시행 로그와의 관계

KPI 측정용 시행 로그 CSV(`services/web/logs/web_trials_*.csv`, 판정 타이밍 스펙 §7)는 **그대로 CSV로 남긴다**
(KPI 원본 데이터). 그 `subject` 열에는 로그인한 회원의 회원코드가 들어간다. `LOG_SUBJECT` 환경변수를 주면
그 값이 우선한다(외부인 KPI 시행 때 ext04 같은 ID를 쓰려면).

## 6. 개인정보

이메일·이름·소속은 개인정보다. 시연·평가가 끝나면 Supabase 프로젝트의 회원·기록을 지우거나 프로젝트를 삭제한다.
`service_role` 키가 유출되면 **Project Settings → API → Reset** 으로 즉시 바꾼다.
