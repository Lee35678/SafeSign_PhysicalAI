-- SafeSign 회원·학습 결과 스키마 (Supabase SQL Editor에 그대로 붙여 넣고 Run)
-- 설계 설명: document/18_DB설계서.md
--
-- 접근 구조: 브라우저는 Supabase에 직접 접근하지 않는다. web 백엔드(services/web/backend/members.py)만
-- service_role 키로 접근하므로 RLS를 켜고 anon·authenticated에는 아무 권한도 주지 않는다.
-- (service_role은 RLS를 우회한다.) 키는 교육장 RPi5의 환경변수에만 둔다.
--
-- 다시 실행해도 안전하다(if not exists / or replace) — 예전 버전을 이미 돌린 프로젝트도 이 파일을 다시 Run 하면 된다.

-- ── 회원 ──────────────────────────────────────────────────────────────────────
create sequence if not exists public.member_code_seq start 1;

create table if not exists public.members (
  user_id     uuid primary key references auth.users (id) on delete cascade,
  -- 회원코드: 가입 순서대로 SS-00001, SS-00002 … (DB가 부여 — 동시에 가입해도 겹치지 않는다)
  member_code text not null unique
              default ('SS-' || lpad(nextval('public.member_code_seq')::text, 5, '0')),
  email       text not null unique,
  name        text not null,
  org         text,                        -- 소속 (선택)
  created_at  timestamptz not null default now()
);

-- ── 학습 결과: 한 번 끝까지 학습한 기록 = 회차 1행 + 수신호 7행 ──────────────────
create table if not exists public.training_sessions (
  id                uuid primary key,      -- web이 만든 ID — 재전송해도 한 번만 저장된다
  user_id           uuid not null references public.members (user_id) on delete cascade,
  member_code       text not null,
  started_at        timestamptz,
  completed_at      timestamptz not null,
  total_attempts    integer not null,
  first_try_correct integer not null,      -- 첫 시도에 맞힌 수신호 수 (SC-05 "첫 시도 정답")
  passed_count      integer not null default 0,     -- 합격한 수신호 수 (0~7)
  all_passed        boolean not null default false, -- 7종 모두 합격
  created_at        timestamptz not null default now()
);
alter table public.training_sessions add column if not exists passed_count integer not null default 0;
alter table public.training_sessions add column if not exists all_passed boolean not null default false;

create table if not exists public.training_results (
  session_id  uuid not null references public.training_sessions (id) on delete cascade,
  order_no    smallint not null,           -- 커리큘럼 순서 1~7
  signal      text not null,               -- 정지 · 서행 · 좌회전_유도 · 우회전_유도 · 확인_완료 · 후진 · 주의
  attempts    integer not null,
  match_score integer not null,            -- 일치율 0~100 = 목표 수신호 확률 × 100 (불합격이면 마지막 시도의 값)
  given_up    boolean not null default false,  -- 재시도 상한(기본 3회)을 넘겨 다음으로 넘어간 수신호
  -- 마지막 시도가 어떻게 끝났는지. given_up만으로는 "3회 오답"과 "시간 초과"가 구분되지 않는다.
  last_outcome   text,                       -- correct · wrong · timeout
  last_predicted text,                       -- 마지막 시도에 인식된 수신호 (틀린 경우 무엇으로 읽혔는가)
  -- 합격 = 시도 상한 안에 정답 / 불합격 = 상한을 넘겨 넘어감. given_up에서 DB가 계산한다(따로 어긋날 수 없게)
  passed      boolean generated always as (not given_up) stored,
  first_try   boolean generated always as (attempts = 1 and not given_up) stored,
  primary key (session_id, order_no)
);
alter table public.training_results add column if not exists given_up boolean not null default false;
alter table public.training_results add column if not exists passed boolean generated always as (not given_up) stored;
alter table public.training_results add column if not exists first_try boolean generated always as (attempts = 1 and not given_up) stored;
alter table public.training_results add column if not exists last_outcome text;
alter table public.training_results add column if not exists last_predicted text;

create index if not exists training_sessions_member_idx
  on public.training_sessions (member_code, completed_at desc);
create index if not exists training_results_signal_idx
  on public.training_results (signal, passed);

-- 회차와 수신호 결과를 한 트랜잭션으로 저장한다 (중간에 끊겨 반쪽만 남지 않게).
-- 같은 id로 다시 오면 아무것도 하지 않는다 — 오프라인 대기열 재전송이 중복을 만들지 않는다.
-- search_path를 고정해 다른 스키마의 같은 이름 객체로 바꿔치기되지 않게 한다(Supabase 보안 권고).
create or replace function public.save_training_session(payload jsonb)
returns uuid
language plpgsql
set search_path = public
as $$
declare
  sid uuid := (payload->>'id')::uuid;
begin
  insert into public.training_sessions
    (id, user_id, member_code, started_at, completed_at, total_attempts, first_try_correct)
  values (
    sid,
    (payload->>'user_id')::uuid,
    payload->>'member_code',
    (payload->>'started_at')::timestamptz,
    (payload->>'completed_at')::timestamptz,
    (payload->>'total_attempts')::int,
    (payload->>'first_try_correct')::int
  )
  on conflict (id) do nothing;

  if found then
    insert into public.training_results
      (session_id, order_no, signal, attempts, match_score, given_up, last_outcome, last_predicted)
    select sid, (r->>'order_no')::smallint, r->>'signal', (r->>'attempts')::int, (r->>'match_score')::int,
           coalesce((r->>'given_up')::boolean, false), r->>'last_outcome', r->>'last_predicted'
    from jsonb_array_elements(payload->'results') as r;

    update public.training_sessions s
       set passed_count = (select count(*) from public.training_results r where r.session_id = sid and r.passed),
           all_passed   = coalesce((select bool_and(r.passed) from public.training_results r where r.session_id = sid), false)
     where s.id = sid;
  end if;
  return sid;
end;
$$;

-- ── 회원별 · 수신호별 합격 현황 (조회용 뷰) ────────────────────────────────────
-- 회원 한 명이 수신호마다 몇 번 합격·불합격했고, 가장 최근 결과가 무엇인지.
-- security_invoker: 뷰를 부른 사람의 권한으로 읽는다 — anon이 뷰로 우회해 테이블을 보지 못하게.
create or replace view public.member_signal_status
with (security_invoker = true) as
select
  m.member_code,
  m.name,
  r.signal,
  count(*)                                               as sessions,          -- 이 수신호를 학습한 회차 수
  count(*) filter (where r.passed)                       as passed_sessions,   -- 합격 회차 수
  count(*) filter (where not r.passed)                   as failed_sessions,   -- 불합격 회차 수
  (array_agg(r.passed order by s.completed_at desc))[1]  as last_passed,       -- 가장 최근 회차의 합격 여부
  max(s.completed_at)                                    as last_completed_at,
  max(r.match_score) filter (where r.passed)             as best_match_score,  -- 합격했을 때의 최고 일치율
  bool_or(r.first_try)                                   as ever_first_try     -- 첫 시도에 맞힌 적이 있는가
from public.training_results r
join public.training_sessions s on s.id = r.session_id
join public.members m on m.user_id = s.user_id
group by m.member_code, m.name, r.signal;

-- ── 권한: 백엔드(service_role) 전용 ────────────────────────────────────────────
alter table public.members           enable row level security;
alter table public.training_sessions enable row level security;
alter table public.training_results  enable row level security;

revoke all on public.members, public.training_sessions, public.training_results from anon, authenticated;
revoke all on public.member_signal_status from anon, authenticated;
revoke all on function public.save_training_session(jsonb) from public, anon, authenticated;
grant execute on function public.save_training_session(jsonb) to service_role;
grant usage, select on sequence public.member_code_seq to service_role;
grant select on public.member_signal_status to service_role;

-- 확인용 (SQL Editor)
--   회원별 최근 회차:   select member_code, completed_at, passed_count, all_passed from training_sessions order by completed_at desc;
--   합격 현황:         select * from member_signal_status order by member_code, signal;
--   특정 회원:         select signal, attempts, match_score, passed from training_results r
--                      join training_sessions s on s.id = r.session_id where s.member_code = 'SS-00001' order by s.completed_at desc, order_no;
