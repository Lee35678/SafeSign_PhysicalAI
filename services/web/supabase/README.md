# 회원 DB 준비 (Supabase)

web(`backend/members.py`)은 회원 정보와 학습 결과를 Supabase에 저장합니다. 브라우저는 Supabase에 직접 접근하지 않고,
키는 RPi5의 `.env`에만 둡니다. Supabase를 쓰지 않으면 RPi5에 로컬로 저장합니다(4절).

## 1. 새 프로젝트 준비 (한 번)

1. Supabase에서 새 프로젝트를 만듭니다. 리전은 Northeast Asia (Seoul)를 권장합니다.
2. **SQL Editor** → New query → 이 폴더의 [`schema.sql`](schema.sql) 전체를 붙여 넣고 **Run** 합니다.
   다음이 만들어집니다.
   - 테이블 `members`, `training_sessions`, `training_results`
   - 저장 함수 `save_training_session`, 조회용 뷰 `member_signal_status`, 사원 코드 번호표 `member_code_seq`
   - 권한: 모든 테이블에 RLS를 켜고 `anon`·`authenticated`의 권한을 뺍니다. web 서버(`service_role`)만 접근합니다.
3. **Project Settings → API**에서 두 값을 복사합니다.
   - Project URL
   - `service_role` 키(secret)

`schema.sql`은 다시 실행해도 안전합니다(`if not exists` / `or replace`). 예전 버전을 적용한 프로젝트도 다시 Run 하면
빠진 열과 뷰가 추가되고 기존 데이터는 남습니다.

이메일 인증 메일 설정은 필요 없습니다. web이 관리자 API로 인증을 마친 계정을 만듭니다.

### 비밀번호 찾기 메일

비밀번호 찾기는 메일로 받은 **6자리 코드**를 교육장 화면에 입력하는 방식입니다.

1. **Authentication → Email Templates → Reset Password** 본문에 `{{ .Token }}`을 넣습니다.
   예: `인증 코드: {{ .Token }} (10분 안에 입력)`
2. Supabase 기본 메일은 시간당 보낼 수 있는 수가 적습니다. 운영할 때는 **Project Settings → Authentication → SMTP**에
   메일 서버를 연결합니다.
3. (선택) **Authentication → Providers → Email**에서 코드 만료 시간을 확인합니다. 10분 정도를 권장합니다.

## 2. 키 넣기

저장소 루트 `.env`에 두 줄을 넣습니다([`.env.example`](../../../.env.example) 참고).

```bash
SUPABASE_URL=<Project URL>
SUPABASE_SERVICE_ROLE_KEY=<service_role 키>
```

- `SUPABASE_SERVICE_ROLE_KEY`는 모든 권한이 있는 **서버 전용 키**입니다. 브라우저·git·메신저·화면에 노출하지 않습니다.
  `.env`는 git에 올라가지 않으므로 RPi5에는 파일을 직접 복사합니다
  (`scp .env <사용자>@<RPi5>:~/git/SafeSign_PhysicalAI/.env`).
- 공개(publishable·anon) 키를 넣으면 가입·저장이 막힙니다. 이때 web이 시작할 때 오류 로그로 알려 줍니다.
- 셸이나 systemd에서 준 값이 있으면 그 값이 `.env`보다 우선합니다.
- 키를 넣은 뒤 web을 다시 시작하고 확인합니다:
  `curl http://localhost:8000/api/auth/me` → `"store": {"backend": "supabase", ...}`. `"local"`이면 키가 들어가지 않은 것입니다.

## 3. 저장되는 내용

| 테이블 | 한 행 | 주요 열 |
| --- | --- | --- |
| `members` | 회원 1명 | `member_code`(SS-00001, 자동 부여), `email`, `name`, `org`, `created_at` |
| `training_sessions` | 7종을 끝까지 마친 교육 1회 | `member_code`, `started_at`, `completed_at`, `total_attempts`, `first_try_correct`, `passed_count`, `all_passed` |
| `training_results` | 그 회차의 수신호 1종 | `order_no`, `signal`, `attempts`, `match_score`(일치율), `given_up`, `passed`(합격), `first_try`, `last_outcome`(correct·wrong·timeout), `last_predicted`(마지막 시도에 인식된 수신호) |
| `member_signal_status` (뷰) | 회원 × 수신호 | 합격·불합격 회차 수, 최근 합격 여부 `last_passed`, 합격 때 최고 일치율 |

합격 = 시도 3회 안에 정답, 불합격 = 3회를 넘겨 다음으로 넘어감(`given_up`). 비밀번호는 Supabase Auth가 보관하며
위 테이블에는 없습니다.

회원별 기록 보기(SQL Editor):

```sql
select m.member_code, m.name, s.completed_at, s.total_attempts, s.first_try_correct
from public.training_sessions s join public.members m using (user_id)
order by s.completed_at desc;
```

## 4. 로컬 모드 (Supabase 없이)

`.env`에 두 키가 없으면 RPi5에 저장합니다.

- 회원: `services/web/data/members_local.json` (비밀번호는 scrypt 해시, POSIX에서 파일 권한 600)
- 결과: `services/web/data/results_local.jsonl`
- 비밀번호 찾기 코드는 메일 대신 web 서버 로그에 찍힙니다.
- 로컬 모드 회원은 나중에 Supabase로 옮겨지지 않습니다.

## 5. 인터넷이 끊겼을 때 (Supabase 사용 중)

| 상황 | 동작 |
| --- | --- |
| 가입·로그인 중 끊김 | "인터넷에 연결되지 않아…" 안내 → 게스트로 교육 가능. 게스트 결과는 `data/results_local.jsonl`에만 남깁니다 |
| 결과 저장 중 끊김 | `data/results_pending.jsonl`에 쌓고 30초마다 자동으로 다시 보냅니다. 같은 결과가 두 번 저장되지 않습니다 |
| Supabase가 저장을 거부 | `data/results_rejected.jsonl`에 오류와 함께 남깁니다. 보통 `schema.sql`을 실행하지 않은 경우입니다 |

`services/web/data/`는 git에 올라가지 않습니다(개인정보).

## 6. 개인정보

이메일·이름·소속은 개인정보입니다. 필요 없어진 회원·기록은 Supabase에서 지웁니다.
`service_role` 키가 유출되면 **Project Settings → API**에서 바로 새 키로 바꾸고 RPi5의 `.env`도 고칩니다.
