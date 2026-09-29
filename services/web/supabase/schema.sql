-- SafeSign 회원·학습 결과 스키마 (Supabase SQL Editor에 그대로 붙여 넣고 Run)
--
-- 접근 구조: 브라우저는 Supabase에 직접 접근하지 않는다. web 백엔드(services/web/backend/members.py)만
-- service_role 키로 접근하므로 RLS를 켜고 anon·authenticated에는 아무 권한도 주지 않는다.
-- (service_role은 RLS를 우회한다.) 키는 교육장 RPi5의 환경변수에만 둔다.
--
-- 다시 실행해도 안전하다(if not exists / or replace).

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

-- ── 학습 결과: 한 번 끝까지 학습한 기록 = 세션 1행 + 수신호 7행 ──────────────────
create table if not exists public.training_sessions (
  id                uuid primary key,      -- web이 만든 ID — 재전송해도 한 번만 저장된다
  user_id           uuid not null references public.members (user_id) on delete cascade,
  member_code       text not null,
  started_at        timestamptz,
  completed_at      timestamptz not null,
  total_attempts    integer not null,
  first_try_correct integer not null,      -- 첫 시도에 맞힌 수신호 수 (SC-05 "첫 시도 정답")
  created_at        timestamptz not null default now()
);

create table if not exists public.training_results (
  session_id  uuid not null references public.training_sessions (id) on delete cascade,
  order_no    smallint not null,           -- 커리큘럼 순서 1~7
  signal      text not null,               -- 정지 · 서행 · 좌회전_유도 · 우회전_유도 · 확인_완료 · 후진 · 주의
  attempts    integer not null,
  match_score integer not null,            -- 정답 시 일치율 0~100 (미완주면 마지막 오답의 일치율)
  given_up    boolean not null default false,  -- 재시도 상한(기본 3회)을 넘겨 다음으로 넘어간 수신호
  primary key (session_id, order_no)
);
alter table public.training_results add column if not exists given_up boolean not null default false;

create index if not exists training_sessions_member_idx
  on public.training_sessions (member_code, completed_at desc);

-- 세션과 수신호 결과를 한 트랜잭션으로 저장한다 (중간에 끊겨 반쪽만 남지 않게).
-- 같은 id로 다시 오면 아무것도 하지 않는다 — 오프라인 대기열 재전송이 중복을 만들지 않는다.
create or replace function public.save_training_session(payload jsonb)
returns uuid
language plpgsql
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
    insert into public.training_results (session_id, order_no, signal, attempts, match_score, given_up)
    select sid, (r->>'order_no')::smallint, r->>'signal', (r->>'attempts')::int, (r->>'match_score')::int,
           coalesce((r->>'given_up')::boolean, false)
    from jsonb_array_elements(payload->'results') as r;
  end if;
  return sid;
end;
$$;

-- ── 권한: 백엔드(service_role) 전용 ────────────────────────────────────────────
alter table public.members           enable row level security;
alter table public.training_sessions enable row level security;
alter table public.training_results  enable row level security;

revoke all on public.members, public.training_sessions, public.training_results from anon, authenticated;
revoke all on function public.save_training_session(jsonb) from public, anon, authenticated;
grant execute on function public.save_training_session(jsonb) to service_role;
grant usage, select on sequence public.member_code_seq to service_role;

-- 확인용: 회원별 학습 기록 (Table Editor 대신 SQL로 볼 때)
--   select m.member_code, m.name, s.completed_at, s.total_attempts, s.first_try_correct
--   from public.training_sessions s join public.members m using (user_id)
--   order by s.completed_at desc;
