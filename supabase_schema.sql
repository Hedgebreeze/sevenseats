-- SevenSeats Supabase schema
-- Run this once in the Supabase SQL editor.

create extension if not exists pgcrypto;

create table if not exists watcher_runs (
    id uuid primary key default gen_random_uuid(),
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    status text not null default 'running',
    error_message text,
    restaurants_checked integer default 0,
    dates_checked integer default 0,
    matches_seen integer default 0,
    notifications_sent integer default 0,
    suppressed integer default 0,
    api_calls_made integer default 0,
    api_calls_failed integer default 0,
    config jsonb default '{}'::jsonb,
    github_run_id text,
    github_run_url text,
    source text not null default 'sevenrooms'
);

create index if not exists idx_watcher_runs_started_at
    on watcher_runs(started_at desc);

create index if not exists idx_watcher_runs_status
    on watcher_runs(status);

create table if not exists availability_logs (
    id bigserial primary key,
    run_id uuid references watcher_runs(id) on delete set null,
    seen_at_iso timestamptz not null,
    slot_at_iso timestamptz not null,
    restaurant_name text not null,
    venue text not null,
    party_size integer not null,
    shift_category text,
    shift_name text,
    public_time_slot_description text,
    reservation_url text,
    notification_action text not null,
    notification_reason text,
    slot_key text not null,
    lead_days integer,
    lead_hours numeric(6, 1),
    weekday_slot text,
    weekday_seen text,
    hour_slot integer,
    source text not null default 'sevenrooms',
    created_at timestamptz not null default now()
);

create index if not exists idx_availability_logs_seen_at
    on availability_logs(seen_at_iso desc);

create index if not exists idx_availability_logs_slot_at
    on availability_logs(slot_at_iso);

create index if not exists idx_availability_logs_restaurant
    on availability_logs(restaurant_name);

create index if not exists idx_availability_logs_action
    on availability_logs(notification_action);

create index if not exists idx_availability_logs_slot_key
    on availability_logs(slot_key);

create or replace view unique_slots as
select distinct on (slot_key)
    seen_at_iso,
    slot_at_iso,
    restaurant_name,
    venue,
    party_size,
    shift_category,
    shift_name,
    public_time_slot_description,
    reservation_url,
    notification_action,
    notification_reason,
    slot_key,
    lead_days,
    lead_hours,
    weekday_slot,
    weekday_seen,
    hour_slot,
    run_id,
    source,
    created_at
from availability_logs
order by slot_key, seen_at_iso asc;

create or replace view recent_runs as
select
    r.*,
    coalesce(events.total_events, 0) as total_events
from watcher_runs r
left join lateral (
    select count(*) as total_events
    from availability_logs l
    where l.run_id = r.id
) events on true
order by r.started_at desc
limit 200;

alter table watcher_runs enable row level security;
alter table availability_logs enable row level security;

drop policy if exists "Public read watcher_runs" on watcher_runs;
create policy "Public read watcher_runs"
    on watcher_runs
    for select
    to anon
    using (true);

drop policy if exists "Public read availability_logs" on availability_logs;
create policy "Public read availability_logs"
    on availability_logs
    for select
    to anon
    using (true);

grant select on watcher_runs to anon;
grant select on availability_logs to anon;
grant select on unique_slots to anon;
grant select on recent_runs to anon;
