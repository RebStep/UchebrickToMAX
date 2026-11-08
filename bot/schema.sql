

CREATE TABLE IF NOT EXISTS users (
    id          bigint PRIMARY KEY,
    first_name  text,
    tz          text NOT NULL DEFAULT 'Europe/Samara',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tasks (
    id              bigserial PRIMARY KEY,
    user_id         bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           text NOT NULL,
    subject         text,
    due_at          timestamptz,
    source          text NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','forward','group')),
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('draft','active','done','cancelled')),
    done_at         timestamptz,

    next_remind_at  timestamptz,
    remind_count    int NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tasks_user_status ON tasks (user_id, status, due_at);


CREATE TABLE IF NOT EXISTS dialog_state (
    user_id     bigint PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    state       text NOT NULL,
    expires_at  timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS import_batches (
    user_id     bigint PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    token       text NOT NULL,
    items       jsonb NOT NULL,
    expires_at  timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS alice_link_codes (
    user_id bigint PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    code_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS alice_links (
    identity_hash text PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS alice_inbox (
    event_key text PRIMARY KEY,
    identity_hash text NOT NULL REFERENCES alice_links(identity_hash) ON DELETE CASCADE,
    text text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    claimed_at timestamptz
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS quiet_from time NOT NULL DEFAULT '22:00';
ALTER TABLE users ADD COLUMN IF NOT EXISTS quiet_to time NOT NULL DEFAULT '07:00';
ALTER TABLE users ADD COLUMN IF NOT EXISTS repeat_min int NOT NULL DEFAULT 60 CHECK (repeat_min >= 1);
ALTER TABLE users ADD COLUMN IF NOT EXISTS repeat_max int NOT NULL DEFAULT 5 CHECK (repeat_max BETWEEN 1 AND 20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS bot_active boolean NOT NULL DEFAULT true;
ALTER TABLE users ADD COLUMN IF NOT EXISTS work_schedule text NOT NULL DEFAULT 'classic'
    CHECK (work_schedule IN ('classic', 'school', 'evening'));
ALTER TABLE users ADD COLUMN IF NOT EXISTS morning_at time;
ALTER TABLE users ADD COLUMN IF NOT EXISTS morning_sent_on date;
ALTER TABLE users ADD COLUMN IF NOT EXISTS browser_revoked_at timestamptz;

CREATE TABLE IF NOT EXISTS reminder_log (
    task_id     bigint NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    attempt_no  int NOT NULL,
    planned_for timestamptz NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    error       text,
    PRIMARY KEY (task_id, attempt_no)
);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS reminder_generation bigint NOT NULL DEFAULT 0;
ALTER TABLE reminder_log ADD COLUMN IF NOT EXISTS generation bigint NOT NULL DEFAULT 0;
ALTER TABLE reminder_log ADD COLUMN IF NOT EXISTS reacted boolean NOT NULL DEFAULT false;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'reminder_log'::regclass
                   AND conname = 'reminder_log_generation_pkey') THEN
        ALTER TABLE reminder_log DROP CONSTRAINT reminder_log_pkey,
            ADD CONSTRAINT reminder_log_generation_pkey PRIMARY KEY (task_id, generation, attempt_no);
    END IF;
END $$;
CREATE TABLE IF NOT EXISTS hour_stats (
    user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    hour_of_week integer NOT NULL CHECK (hour_of_week BETWEEN 0 AND 167),
    score double precision NOT NULL,
    touched_at timestamptz NOT NULL,
    PRIMARY KEY (user_id, hour_of_week)
);
CREATE INDEX IF NOT EXISTS tasks_due_remind ON tasks (next_remind_at) WHERE status = 'active' AND next_remind_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS login_tokens (
    token_hash  text PRIMARY KEY,
    user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at  timestamptz NOT NULL,
    used_at     timestamptz
);


ALTER TABLE tasks ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'homework';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS location text;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS note text;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS reg_deadline timestamptz;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS duration_min integer CHECK (duration_min BETWEEN 1 AND 1440);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS pos_x double precision;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS pos_y double precision;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS needs_schedule boolean NOT NULL DEFAULT false;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS reminders_muted boolean NOT NULL DEFAULT false;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS reminder_checkin boolean NOT NULL DEFAULT false;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS registered boolean NOT NULL DEFAULT false;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS group_candidate_id bigint;
CREATE UNIQUE INDEX IF NOT EXISTS tasks_group_candidate ON tasks (user_id, group_candidate_id);
CREATE INDEX IF NOT EXISTS tasks_needs_schedule ON tasks (id) WHERE needs_schedule;


ALTER TABLE users ADD COLUMN IF NOT EXISTS ics_token text UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS alice_private_token text UNIQUE;


CREATE TABLE IF NOT EXISTS task_links (
    id          bigserial PRIMARY KEY,
    task_id     bigint NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    url         text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS task_links_task ON task_links (task_id);


CREATE TABLE IF NOT EXISTS attachments (
    id          bigserial PRIMARY KEY,
    task_id     bigint NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('photo', 'doc')),
    name        text NOT NULL,
    mime        text,
    size_bytes  bigint NOT NULL,
    path        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS attachments_task ON attachments (task_id);


CREATE TABLE IF NOT EXISTS olympiads (
    id            bigserial PRIMARY KEY,
    user_id       bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name          text NOT NULL,
    level         text,
    subject       text,
    location      text,
    note          text,
    registered    boolean NOT NULL DEFAULT false,
    reg_opens     timestamptz,
    reg_deadline  timestamptz,
    tours         jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS olympiads_user ON olympiads (user_id);
ALTER TABLE olympiads ADD COLUMN IF NOT EXISTS links text[] NOT NULL DEFAULT '{}';
ALTER TABLE olympiads ADD COLUMN IF NOT EXISTS reminders_muted boolean NOT NULL DEFAULT false;
CREATE TABLE IF NOT EXISTS olympiad_notices (
    olympiad_id bigint NOT NULL REFERENCES olympiads(id) ON DELETE CASCADE,
    notice_key text NOT NULL,
    PRIMARY KEY (olympiad_id, notice_key)
);


ALTER TABLE task_links ADD COLUMN IF NOT EXISTS pos_x double precision;
ALTER TABLE task_links ADD COLUMN IF NOT EXISTS pos_y double precision;
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS pos_x double precision;
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS pos_y double precision;


ALTER TABLE users ADD COLUMN IF NOT EXISTS list_mid text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS list_ids bigint[];

ALTER TABLE users ADD COLUMN IF NOT EXISTS list_filter text NOT NULL DEFAULT 'today';


ALTER TABLE attachments ADD COLUMN IF NOT EXISTS user_id bigint REFERENCES users(id) ON DELETE CASCADE;
UPDATE attachments a SET user_id = t.user_id FROM tasks t WHERE a.task_id = t.id AND a.user_id IS NULL;
ALTER TABLE attachments ALTER COLUMN task_id DROP NOT NULL;
CREATE INDEX IF NOT EXISTS attachments_user ON attachments (user_id);
CREATE TABLE IF NOT EXISTS attachment_deliveries (
    attachment_id bigint PRIMARY KEY REFERENCES attachments(id) ON DELETE CASCADE,
    queued_at timestamptz NOT NULL DEFAULT now(),
    claimed_at timestamptz,
    sent_at timestamptz,
    failed boolean NOT NULL DEFAULT false
);


CREATE TABLE IF NOT EXISTS notes (
    id          bigserial PRIMARY KEY,
    user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    task_id     bigint REFERENCES tasks(id) ON DELETE SET NULL,
    text        text NOT NULL,
    pos_x       double precision,
    pos_y       double precision,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS notes_user ON notes (user_id);


CREATE TABLE IF NOT EXISTS chat_candidates (
    id            bigserial PRIMARY KEY,
    chat_id       bigint NOT NULL,
    title         text NOT NULL,
    subject       text,
    due_at        timestamptz,
    kind          text NOT NULL DEFAULT 'homework',
    location      text,
    reg_deadline  timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE chat_candidates ADD COLUMN IF NOT EXISTS files jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE chat_candidates ADD COLUMN IF NOT EXISTS duration_min integer CHECK (duration_min BETWEEN 1 AND 1440);
CREATE INDEX IF NOT EXISTS chat_candidates_chat ON chat_candidates (chat_id, created_at);

CREATE TABLE IF NOT EXISTS chat_members (
    chat_id bigint NOT NULL,
    user_id bigint NOT NULL,
    seen_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (chat_id, user_id)
);



CREATE TABLE IF NOT EXISTS attachment_tasks (
    attachment_id  bigint NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
    task_id        bigint NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (attachment_id, task_id)
);
CREATE INDEX IF NOT EXISTS attachment_tasks_task ON attachment_tasks (task_id);
INSERT INTO attachment_tasks (attachment_id, task_id)
    SELECT id, task_id FROM attachments WHERE task_id IS NOT NULL ON CONFLICT DO NOTHING;
UPDATE attachments SET task_id = NULL WHERE task_id IS NOT NULL;



ALTER TABLE users ADD COLUMN IF NOT EXISTS remind_mode text NOT NULL DEFAULT 'all'
    CHECK (remind_mode IN ('all', 'selected', 'none'));
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS remind_on boolean NOT NULL DEFAULT false;

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS reminder_mid text;

ALTER TABLE users ALTER COLUMN repeat_max SET DEFAULT 2;



CREATE TABLE IF NOT EXISTS voice_jobs (
    id          bigserial PRIMARY KEY,
    user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    path        text,
    status      text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'working', 'done', 'error')),
    result      jsonb,
    error       text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    claimed_at  timestamptz
);
CREATE INDEX IF NOT EXISTS voice_jobs_pending ON voice_jobs (created_at) WHERE status = 'pending';
