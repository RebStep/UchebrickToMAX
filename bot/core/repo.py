import json
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg

from core.schedule import Prefs, first_remind, homework_slot, shift_out_of_quiet, task_repeat

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"
WAITING_TASK = "waiting_task"
STATE_TTL = timedelta(hours=1)


@dataclass
class Claimed:
    task_id: int
    user_id: int
    title: str
    subject: str | None
    due_at: datetime | None
    attempt: int
    prefs: Prefs
    generation: int
    next_at: datetime | None
    checkin: bool
    kind: str = "homework"


def _prefs(r) -> Prefs:
    return Prefs(r["tz"], r["quiet_from"], r["quiet_to"], r["repeat_min"], r["repeat_max"],
                 r["work_schedule"], r["morning_at"], r.get("remind_mode") or "all")


REMIND_OK = "(NOT t.reminders_muted AND (u.remind_mode = 'all' OR (u.remind_mode = 'selected' AND t.remind_on)))"


def remind_ok(mode: str, muted: bool, remind_on: bool) -> bool:
    return not muted and (mode == "all" or (mode == "selected" and remind_on))


class Repo:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> "Repo":
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        async with pool.acquire() as con:
            await con.execute(SCHEMA.read_text(encoding="utf-8"))
        return cls(pool)

    async def close(self):
        await self.pool.close()

    async def ensure_user(self, user_id: int, first_name: str | None) -> str:
        return await self.pool.fetchval(
            """INSERT INTO users (id, first_name) VALUES ($1, $2)
               ON CONFLICT (id) DO UPDATE SET first_name = EXCLUDED.first_name, bot_active = true
               RETURNING tz""",
            user_id, first_name,
        )

    async def get_prefs(self, user_id: int) -> Prefs:
        row = await self.pool.fetchrow(
            """SELECT tz, quiet_from, quiet_to, repeat_min, repeat_max, work_schedule, morning_at, remind_mode
               FROM users WHERE id = $1""", user_id)
        if row:
            return _prefs(row)
        return Prefs()

    async def set_quiet(self, user_id: int, quiet_from, quiet_to) -> None:
        await self.pool.execute("UPDATE users SET quiet_from = $2, quiet_to = $3 WHERE id = $1", user_id, quiet_from, quiet_to)

    async def set_repeat(self, user_id: int, minutes: int) -> None:
        await self.pool.execute("UPDATE users SET repeat_min = $2 WHERE id = $1", user_id, minutes)

    async def set_repeat_max(self, user_id: int, times: int) -> None:
        await self.pool.execute("UPDATE users SET repeat_max = $2 WHERE id = $1", user_id, times)

    async def set_remind_mode(self, user_id: int, mode: str) -> None:
        await self.pool.execute(
            """WITH changed AS (UPDATE users SET remind_mode = $2 WHERE id = $1 AND remind_mode <> $2 RETURNING id)
               UPDATE tasks SET needs_schedule = true FROM changed
               WHERE tasks.user_id = changed.id AND tasks.status = 'active'""", user_id, mode)

    async def set_remind_on(self, user_id: int, task_id: int, on: bool) -> bool:
        return await self.pool.fetchval(
            """UPDATE tasks SET remind_on = $3, reminders_muted = false, needs_schedule = true, next_remind_at = NULL,
                                reminder_generation = reminder_generation + 1
               WHERE id = $1 AND user_id = $2 AND status = 'active' RETURNING true""", task_id, user_id, on) is True

    async def set_work_schedule(self, user_id: int, value: str) -> None:
        await self.pool.execute(
            """WITH changed AS (UPDATE users SET work_schedule = $2 WHERE id = $1 AND work_schedule <> $2 RETURNING id)
               UPDATE tasks SET needs_schedule = true FROM changed WHERE tasks.user_id = changed.id
                 AND tasks.status = 'active' AND NOT tasks.reminders_muted""", user_id, value)

    async def set_morning(self, user_id: int, value) -> None:
        await self.pool.execute("UPDATE users SET morning_at = $2 WHERE id = $1", user_id, value)

    async def claim_mornings(self, now: datetime) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            """WITH ready AS (
                   SELECT id, ($1::timestamptz AT TIME ZONE tz)::date AS local_day
                   FROM users CROSS JOIN LATERAL (SELECT ($1::timestamptz AT TIME ZONE tz)::time AS local_time) AS lt
                   WHERE bot_active AND morning_at IS NOT NULL AND local_time >= morning_at AND local_time < '12:00'
                     AND (morning_sent_on IS NULL OR morning_sent_on < ($1::timestamptz AT TIME ZONE tz)::date)
                     AND CASE WHEN quiet_from < quiet_to THEN local_time < quiet_from OR local_time >= quiet_to
                              WHEN quiet_from > quiet_to THEN local_time >= quiet_to AND local_time < quiet_from
                              ELSE true END
                   ORDER BY id LIMIT 50 FOR UPDATE OF users SKIP LOCKED
               )
               UPDATE users u SET morning_sent_on = ready.local_day FROM ready WHERE u.id = ready.id RETURNING u.id, u.tz""",
            now)

    async def set_bot_active(self, user_id: int, active: bool):
        await self.pool.execute("UPDATE users SET bot_active = $2 WHERE id = $1", user_id, active)

    async def set_state(self, user_id: int, state: str):
        await self.pool.execute(
            """INSERT INTO dialog_state (user_id, state, expires_at) VALUES ($1, $2, $3)
               ON CONFLICT (user_id) DO UPDATE SET state = EXCLUDED.state, expires_at = EXCLUDED.expires_at""",
            user_id, state, datetime.now(timezone.utc) + STATE_TTL,
        )

    async def get_state(self, user_id: int) -> str | None:
        return await self.pool.fetchval(
            "SELECT state FROM dialog_state WHERE user_id = $1 AND expires_at > now()", user_id)

    async def clear_state(self, user_id: int, state: str) -> None:
        await self.pool.execute("DELETE FROM dialog_state WHERE user_id = $1 AND state = $2", user_id, state)

    async def take_state(self, user_id: int, state: str) -> bool:
        return await self.pool.fetchval(
            "DELETE FROM dialog_state WHERE user_id = $1 AND state = $2 AND expires_at > now() RETURNING true",
            user_id, state) is True

    async def pop_state(self, user_id: int, *, except_prefix: str = "", only_prefix: str = "") -> str | None:
        return await self.pool.fetchval(
            """DELETE FROM dialog_state WHERE user_id = $1 AND expires_at > now()
                 AND ($2 = '' OR NOT starts_with(state, $2)) AND starts_with(state, $3) RETURNING state""",
            user_id, except_prefix, only_prefix
        )

    async def save_import(self, user_id: int, items: list[dict]) -> str:
        token = secrets.token_hex(16)
        await self.pool.execute(
            """INSERT INTO import_batches (user_id, token, items, expires_at)
               VALUES ($1, $2, $3::jsonb, now() + interval '1 hour')
               ON CONFLICT (user_id) DO UPDATE
               SET token = EXCLUDED.token, items = EXCLUDED.items, expires_at = EXCLUDED.expires_at""",
            user_id, token, json.dumps(items, ensure_ascii=False))
        return token

    async def get_import(self, user_id: int, token: str) -> list[dict] | None:
        items = await self.pool.fetchval(
            "SELECT items FROM import_batches WHERE user_id = $1 AND token = $2 AND expires_at > now()", user_id, token)
        if items:
            return json.loads(items)
        return None

    async def cancel_import(self, user_id: int, token: str) -> bool:
        return await self.pool.fetchval(
            "DELETE FROM import_batches WHERE user_id = $1 AND token = $2 RETURNING true", user_id, token) is True

    async def confirm_import(self, user_id: int, token: str, now: datetime) -> tuple[int, int] | None:
        async with self.pool.acquire() as con, con.transaction():
            await con.fetchval("SELECT id FROM users WHERE id = $1 FOR UPDATE", user_id)
            stored = await con.fetchval(
                """DELETE FROM import_batches WHERE user_id = $1 AND token = $2 AND expires_at > now()
                   RETURNING items""", user_id, token)
            if stored is None:
                return None
            items = json.loads(stored)
            added = 0
            for item in items:
                if "olympiad" in item:
                    added += await self._import_tour(con, user_id, item, now)
                    continue
                if item['due_at']:
                    due = datetime.fromisoformat(item['due_at'])
                else:
                    due = None
                duration = item["duration_min"]
                if due and item['kind'] == 'event':
                    end = due + timedelta(minutes=duration or 30)
                else:
                    end = due
                if end and end < now:
                    continue
                if item['reg_deadline']:
                    reg = datetime.fromisoformat(item['reg_deadline'])
                else:
                    reg = None
                task_id = await con.fetchval(
                    """INSERT INTO tasks (user_id, title, subject, kind, due_at, reg_deadline, location,
                                          duration_min, needs_schedule)
                       SELECT $1, $2, $3, $4, $5, $6, $7, $8, true
                       WHERE NOT EXISTS (SELECT 1 FROM tasks WHERE user_id = $1 AND lower(title) = lower($2)
                                         AND subject IS NOT DISTINCT FROM $3 AND due_at IS NOT DISTINCT FROM $5
                                         AND status IN ('active', 'done'))
                       RETURNING id""", user_id, item["title"], item["subject"], item["kind"], due, reg,
                    item["location"], duration)
                if task_id is not None:
                    await con.execute(
                        "INSERT INTO task_links (task_id, url) SELECT $1, unnest($2::text[])",
                        task_id, item["links"])
                    added += 1
            return added, len(items) - added

    async def _import_tour(self, con, user_id: int, item: dict, now: datetime) -> bool:
        meta = item["olympiad"]
        due = meta["end_at"] or item["due_at"]
        start = meta["starts_at"] or (due if item["kind"] == "event" else None)
        if due and datetime.fromisoformat(due) < now:
            return False
        tour = {"title": meta["tour"], "starts_at": start, "deadline": due, "done": False}
        if item["kind"] == "event" and item["duration_min"]:
            tour["duration_min"] = item["duration_min"]
        if item['reg_deadline']:
            reg = datetime.fromisoformat(item['reg_deadline'])
        else:
            reg = None
        row = await con.fetchrow(
            """SELECT id, tours, links FROM olympiads WHERE user_id = $1 AND lower(name) = lower($2)
                 AND subject IS NOT DISTINCT FROM $3 ORDER BY id LIMIT 1 FOR UPDATE""",
            user_id, meta["name"], item["subject"])
        if row is None:
            await con.execute(
                """INSERT INTO olympiads (user_id, name, level, subject, location, reg_deadline, tours, links)
                   VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)""",
                user_id, meta["name"], meta["level"], item["subject"], item["location"], reg,
                json.dumps([tour], ensure_ascii=False), item["links"])
            return True
        tours = json.loads(row["tours"])
        def same_date(a, b):
            if a and b:
                return datetime.fromisoformat(a) == datetime.fromisoformat(b)
            return a == b

        if len(tours) >= 20 or any(
            saved["title"].casefold() == tour["title"].casefold()
            and same_date(saved["starts_at"], start) and same_date(saved["deadline"], due)
            for saved in tours
        ):
            return False
        tours.append(tour)
        links = list(dict.fromkeys([*row["links"], *item["links"]]))[:20]
        await con.execute(
            """UPDATE olympiads SET tours = $2::jsonb, links = $3, reg_deadline = COALESCE(reg_deadline, $4),
                                    level = COALESCE(level, $5), location = COALESCE(location, $6)
               WHERE id = $1""",
            row["id"], json.dumps(tours, ensure_ascii=False), links, reg, meta["level"], item["location"])
        return True

    async def add_task(self, user_id: int, title: str, subject: str | None, due_at: datetime | None,
                       source: str = "manual", now: datetime | None = None, draft: bool = False,
                       kind: str = "homework", location: str | None = None, reg_deadline: datetime | None = None,
                       duration_min: int | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        remind_at = None
        if not draft:
            prefs = await self.get_prefs(user_id)
            scores, occupied = await self.work_context(self.pool, user_id, now) if prefs.work_schedule != "classic" and kind == "homework" else ({}, [])
            if remind_ok(prefs.remind_mode, False, False):
                remind_at = first_remind(due_at, now, prefs, kind=kind, duration=duration_min, reg=reg_deadline, scores=scores, occupied=occupied)
            else:
                remind_at = None
        return await self.pool.fetchval(
            """INSERT INTO tasks (user_id, title, subject, due_at, source, next_remind_at, status, kind, location,
                                  reg_deadline, duration_min)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) RETURNING id""",
            user_id, title, subject, due_at, source, remind_at, "draft" if draft else "active", kind, location,
            reg_deadline, duration_min,
        )

    async def add_candidate(self, chat_id: int, p, files: list[dict] | None = None) -> int | None:
        return await self.pool.fetchval(
            """INSERT INTO chat_candidates (chat_id, title, subject, due_at, kind, location, reg_deadline, files, duration_min)
               SELECT $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9
               WHERE NOT EXISTS (SELECT 1 FROM chat_candidates WHERE chat_id = $1 AND title = $2
                                 AND due_at IS NOT DISTINCT FROM $4 AND created_at > now() - interval '10 minutes')
               RETURNING id""",
            chat_id, p.title, p.subject, p.due_at, p.kind, p.location, p.reg_deadline,
            json.dumps(files or [], ensure_ascii=False), p.duration_min)

    async def set_title(self, user_id: int, task_id: int, title: str) -> bool:
        row = await self.pool.fetchval(
            "UPDATE tasks SET title = $3 WHERE id = $1 AND user_id = $2 AND status IN ('active', 'draft') RETURNING id",
            task_id, user_id, title)
        return row is not None

    async def set_subject(self, user_id: int, task_id: int, subject: str | None) -> bool:
        return await self.pool.fetchval(
            """UPDATE tasks SET subject = $3 WHERE id = $1 AND user_id = $2 AND status IN ('active', 'draft')
               RETURNING true""", task_id, user_id, subject) is True

    async def set_kind(self, user_id: int, task_id: int, kind: str, due_at: datetime | None,
                       previous_kind: str, previous_due: datetime | None) -> bool:
        return await self.pool.fetchval(
            """UPDATE tasks SET kind = $3, due_at = $4, needs_schedule = true
               WHERE id = $1 AND user_id = $2 AND kind = $5 AND status IN ('active', 'draft')
                 AND due_at IS NOT DISTINCT FROM $6
               RETURNING true""", task_id, user_id, kind, due_at, previous_kind, previous_due) is True

    async def set_reminders_muted(self, user_id: int, task_id: int, muted: bool) -> bool:
        return await self.pool.fetchval(
            """UPDATE tasks SET reminders_muted = $3, next_remind_at = NULL, needs_schedule = NOT $3,
                                reminder_generation = reminder_generation + 1
               WHERE id = $1 AND user_id = $2 AND status = 'active' AND reminders_muted <> $3
               RETURNING true""", task_id, user_id, muted) is True

    async def remember_member(self, chat_id: int, user_id: int) -> None:
        await self.pool.execute(
            """INSERT INTO chat_members (chat_id, user_id) VALUES ($1, $2)
               ON CONFLICT (chat_id, user_id) DO UPDATE SET seen_at = now()""", chat_id, user_id)

    async def known_members(self, chat_id: int) -> list[int]:
        return [r["user_id"] for r in await self.pool.fetch("SELECT user_id FROM chat_members WHERE chat_id = $1", chat_id)]

    async def bot_users(self, ids: list[int]) -> list[asyncpg.Record]:
        return await self.pool.fetch("SELECT id, tz FROM users WHERE id = ANY($1::bigint[]) AND bot_active", ids)

    async def get_candidate(self, cid: int) -> asyncpg.Record | None:
        return await self.pool.fetchrow("SELECT * FROM chat_candidates WHERE id = $1", cid)

    async def grab_candidate(self, user_id: int, candidate_id: int, chat_id: int) -> int | None:
        return await self.pool.fetchval(
            """INSERT INTO tasks (user_id, title, subject, due_at, source, kind, location, reg_deadline,
                                  duration_min, group_candidate_id, needs_schedule)
               SELECT $1, title, subject, due_at, 'group', kind, location, reg_deadline, duration_min, id, true
               FROM chat_candidates WHERE id = $2 AND chat_id = $3
               ON CONFLICT (user_id, group_candidate_id) DO NOTHING RETURNING id""", user_id, candidate_id, chat_id)

    async def get_task(self, user_id: int, task_id: int) -> asyncpg.Record | None:
        return await self.pool.fetchrow(
            """SELECT id, title, subject, due_at, status, kind, location, note, reg_deadline, duration_min, next_remind_at,
                      reminders_muted, remind_on, registered FROM tasks WHERE id = $1 AND user_id = $2""", task_id, user_id)

    async def mark_registered(self, user_id: int, task_id: int) -> bool:
        return await self.pool.fetchval(
            """UPDATE tasks SET registered = true, needs_schedule = true
               WHERE user_id = $1 AND id = $2 AND status = 'active' AND reg_deadline IS NOT NULL
                 AND NOT registered RETURNING true""", user_id, task_id) is True

    async def confirm_draft(self, user_id: int, task_id: int) -> bool:
        row = await self.pool.fetchval(
            """UPDATE tasks SET status = 'active', needs_schedule = true
               WHERE id = $1 AND user_id = $2 AND status = 'draft' RETURNING id""",
            task_id, user_id,
        )
        return row is not None

    async def cancel_draft(self, user_id: int, task_id: int) -> bool:
        row = await self.pool.fetchval(
            "DELETE FROM tasks WHERE id = $1 AND user_id = $2 AND status = 'draft' RETURNING id", task_id, user_id)
        return row is not None

    async def set_due(self, user_id: int, task_id: int, due_at: datetime | None) -> bool:
        row = await self.pool.fetchval(
            """UPDATE tasks SET due_at = $3, needs_schedule = true
               WHERE id = $1 AND user_id = $2 AND status IN ('active', 'draft') RETURNING id""",
            task_id, user_id, due_at,
        )
        return row is not None

    async def reschedule(self, user_id: int, task_id: int, old: datetime, new: datetime) -> bool:
        return await self.pool.fetchval(
            """UPDATE tasks SET due_at = $4, needs_schedule = true
               WHERE user_id = $1 AND id = $2 AND due_at = $3 AND status = 'active' RETURNING true""",
            user_id, task_id, old, new) is True

    async def ics_token(self, user_id: int) -> str:
        return await self.pool.fetchval(
            """UPDATE users SET ics_token = COALESCE(ics_token, $2) WHERE id = $1 RETURNING ics_token""",
            user_id, secrets.token_urlsafe(24),
        )

    async def list_active(self, user_id: int) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            """SELECT id, title, subject, due_at, kind, reg_deadline, registered, next_remind_at FROM tasks
               WHERE user_id = $1 AND status = 'active'
               ORDER BY due_at NULLS LAST, id""",
            user_id,
        )

    async def mark_done(self, user_id: int, task_id: int) -> bool:
        row = await self.pool.fetchval(
            """UPDATE tasks SET status = 'done', done_at = now(), next_remind_at = NULL
               WHERE id = $1 AND user_id = $2 AND status = 'active' RETURNING id""",
            task_id, user_id,
        )
        return row is not None

    async def mark_undone(self, user_id: int, task_id: int) -> bool:
        row = await self.pool.fetchval(
            """UPDATE tasks SET status = 'active', done_at = NULL, needs_schedule = true
               WHERE id = $1 AND user_id = $2 AND status = 'done' RETURNING id""",
            task_id, user_id,
        )
        return row is not None

    async def save_list(self, user_id: int, mid: str | None, ids: list[int], flt: str = "today") -> None:
        await self.pool.execute(
            "UPDATE users SET list_mid = $2, list_ids = $3::bigint[], list_filter = $4 WHERE id = $1", user_id, mid, ids, flt)

    async def get_list(self, user_id: int) -> tuple[str | None, list[int], str]:
        row = await self.pool.fetchrow("SELECT list_mid, list_ids, list_filter FROM users WHERE id = $1", user_id)
        if row:
            return (row['list_mid'], list(row['list_ids'] or []), row['list_filter'])
        return (None, [], 'today')

    async def delete_task(self, user_id: int, task_id: int) -> asyncpg.Record | None:
        async with self.pool.acquire() as con, con.transaction():
            ids = [r["attachment_id"] for r in await con.fetch(
                "SELECT attachment_id FROM attachment_tasks WHERE task_id = $1", task_id)]
            row = await con.fetchrow(
                "DELETE FROM tasks WHERE id = $1 AND user_id = $2 RETURNING title, subject", task_id, user_id)
            if row is None:
                return None
            paths = await con.fetch(
                """DELETE FROM attachments a WHERE a.id = ANY($1::bigint[])
                   AND NOT EXISTS (SELECT 1 FROM attachment_tasks l WHERE l.attachment_id = a.id) RETURNING path""", ids)
        from core import files as filestore
        for p in paths:
            if len(p["path"]) == 32:
                (filestore.FILES_DIR / p["path"]).unlink(missing_ok=True)
        return row

    async def tasks_by_ids(self, user_id: int, ids: list[int]) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            """SELECT id, title, subject, due_at, status, kind FROM tasks
               WHERE user_id = $1 AND id = ANY($2::bigint[]) AND status IN ('active', 'done')
               ORDER BY due_at NULLS LAST, id""",
            user_id, ids,
        )

    async def reminder_current(self, c: Claimed) -> bool:
        return bool(await self.pool.fetchval(
            f"""SELECT t.status = 'active' AND {REMIND_OK} AND NOT t.needs_schedule AND u.bot_active
                      AND t.reminder_generation = $2 AND t.remind_count = $3
                      AND t.next_remind_at IS NOT DISTINCT FROM $4
               FROM tasks t JOIN users u ON u.id = t.user_id WHERE t.id = $1""",
            c.task_id, c.generation, c.attempt, c.next_at))

    async def snooze(self, user_id: int, task_id: int, until: datetime, *, checkin: bool = False) -> bool:
        row = await self.pool.fetchval(
            """UPDATE tasks SET next_remind_at = $3, needs_schedule = false, reminder_checkin = $4,
                                remind_count = CASE WHEN $4 THEN 0 ELSE remind_count END,
                                reminder_generation = reminder_generation + CASE WHEN $4 THEN 1 ELSE 0 END
               WHERE id = $1 AND user_id = $2 AND status = 'active' AND NOT reminders_muted RETURNING id""",
            task_id, user_id, until, checkin,
        )
        return row is not None

    async def archive_events(self, now: datetime) -> None:
        await self.pool.execute(
            """UPDATE tasks SET status = 'done', done_at = due_at + make_interval(mins => COALESCE(duration_min, 30)),
                                next_remind_at = NULL
               WHERE status = 'active' AND kind = 'event'
                 AND due_at + make_interval(mins => COALESCE(duration_min, 30)) <= $1""", now)

    async def work_context(self, con, user_id: int, now: datetime) -> tuple[dict, list]:
        rows = await con.fetch(
            "SELECT hour_of_week, score, touched_at FROM hour_stats WHERE user_id = $1", user_id)
        scores = {r["hour_of_week"]: r["score"] * 0.9 ** max(0, (now - r["touched_at"]).days) for r in rows}
        occupied = await con.fetch(
            """SELECT next_remind_at FROM tasks WHERE user_id = $1 AND status = 'active' AND kind = 'homework'
                 AND NOT needs_schedule AND next_remind_at >= $2""", user_id, now)
        return scores, [r["next_remind_at"] for r in occupied]

    async def learn_response(self, user_id: int, task_id: int, now: datetime, score: float) -> None:
        await self._learn_response(self.pool, user_id, task_id, now, score)

    async def _learn_response(self, con, user_id: int, task_id: int, now: datetime, score: float) -> None:
        await con.execute(
            """WITH chosen AS (
                   SELECT l.task_id, l.generation, l.attempt_no, (l.planned_for AT TIME ZONE u.tz) AS local_at
                   FROM reminder_log l JOIN tasks t ON t.id = l.task_id JOIN users u ON u.id = t.user_id
                   WHERE t.id = $2 AND t.user_id = $1 AND t.kind = 'homework' AND u.work_schedule <> 'classic'
                     AND l.generation = t.reminder_generation AND l.created_at >= $3::timestamptz - interval '6 hours'
                     AND l.error IS NULL ORDER BY l.attempt_no DESC LIMIT 1 FOR UPDATE OF l
               ), updated AS (
                   UPDATE reminder_log l SET reacted = true FROM chosen c
                   WHERE l.task_id = c.task_id AND l.generation = c.generation AND l.attempt_no = c.attempt_no
                     AND NOT l.reacted RETURNING c.local_at
               )
               INSERT INTO hour_stats (user_id, hour_of_week, score, touched_at)
               SELECT $1, (extract(isodow FROM local_at)::int - 1) * 24 + extract(hour FROM local_at)::int, $4, $3
               FROM updated
               ON CONFLICT (user_id, hour_of_week) DO UPDATE
               SET score = greatest(-5, least(5, hour_stats.score * 0.9 + EXCLUDED.score)), touched_at = EXCLUDED.touched_at""",
            user_id, task_id, now, score)

    async def plan_ignored_homework(self, now: datetime) -> None:
        async with self.pool.acquire() as con, con.transaction():
            rows = await con.fetch(
                f"""SELECT t.id, t.user_id, t.due_at, t.duration_min, u.tz, u.quiet_from, u.quiet_to, u.repeat_min,
                          u.repeat_max, u.work_schedule, u.morning_at
                   FROM tasks t JOIN users u ON u.id = t.user_id
                   JOIN reminder_log l ON (l.task_id, l.generation, l.attempt_no)
                                          = (t.id, t.reminder_generation, t.remind_count)
                   WHERE t.kind = 'homework' AND t.status = 'active' AND {REMIND_OK} AND NOT t.needs_schedule
                     AND t.next_remind_at IS NULL AND t.due_at > $1 AND t.remind_count < LEAST(3, u.repeat_max)
                     AND u.bot_active AND u.work_schedule <> 'classic' AND l.error IS NULL AND NOT l.reacted
                     AND l.created_at BETWEEN $1 - interval '6 hours' AND $1 - interval '3 hours'
                   ORDER BY l.created_at LIMIT 50 FOR UPDATE OF t, l SKIP LOCKED""", now)
            for row in rows:
                owner = row["user_id"]
                await self._learn_response(con, owner, row["id"], now, -1.0)
                scores, occupied = await self.work_context(con, owner, now)
                slot = homework_slot(row["due_at"], now, _prefs(row), row["duration_min"], scores, occupied)
                if slot:
                    await con.execute("UPDATE tasks SET next_remind_at = $2 WHERE id = $1", row["id"], slot)

    async def upcoming_olympiads(self, now: datetime) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            """SELECT o.*, u.tz, u.quiet_from, u.quiet_to FROM olympiads o JOIN users u ON u.id = o.user_id
               WHERE u.bot_active AND NOT o.reminders_muted
                 AND ((NOT o.registered AND (o.reg_deadline >= $1 OR o.reg_opens >= $1 - interval '1 day'))
                   OR EXISTS (SELECT 1 FROM jsonb_array_elements(o.tours) AS tour
                              WHERE NOT COALESCE((tour->>'done')::boolean, false)
                                AND COALESCE((tour->>'deadline')::timestamptz, (tour->>'starts_at')::timestamptz) >= $1))""",
            now)

    async def claim_olympiad_notice(self, olympiad_id: int, key: str, registration: bool) -> bool:
        return await self.pool.fetchval(
            """INSERT INTO olympiad_notices (olympiad_id, notice_key)
               SELECT o.id, $2 FROM olympiads o JOIN users u ON u.id = o.user_id
               WHERE o.id = $1 AND u.bot_active AND NOT o.reminders_muted AND (NOT $3 OR NOT o.registered)
               ON CONFLICT DO NOTHING RETURNING true""", olympiad_id, key, registration) is True

    async def update_olympiad_notice_settings(self, user_id: int, olympiad_id: int, *, registered: bool) -> bool:
        return await self.pool.fetchval(
            """UPDATE olympiads SET registered = registered OR $3, reminders_muted = reminders_muted OR NOT $3
               WHERE user_id = $1 AND id = $2 RETURNING true""", user_id, olympiad_id, registered) is True

    async def claim_due(self, now: datetime, limit: int = 50) -> list[Claimed]:
        claimed = []
        async with self.pool.acquire() as con, con.transaction():
            rows = await con.fetch(
                f"""SELECT t.id, t.user_id, t.title, t.subject, t.due_at, t.remind_count, t.next_remind_at,
                          t.reminder_generation, t.reminder_checkin, t.kind, t.reg_deadline, t.registered,
                          u.tz, u.quiet_from, u.quiet_to, u.repeat_min, u.repeat_max, u.work_schedule, u.morning_at,
                          u.remind_mode
                   FROM tasks t JOIN users u ON u.id = t.user_id
                   WHERE t.status = 'active' AND {REMIND_OK} AND NOT t.needs_schedule
                     AND u.bot_active AND t.next_remind_at <= $1
                   ORDER BY t.next_remind_at LIMIT $2
                   FOR UPDATE OF t SKIP LOCKED""",
                now, limit,
            )
            for r in rows:
                attempt = r["remind_count"] + 1
                prefs = _prefs(r)
                awake = shift_out_of_quiet(now, prefs)
                if awake > now:
                    await con.execute("UPDATE tasks SET next_remind_at = $2 WHERE id = $1", r["id"], awake)
                    continue
                generation = r["reminder_generation"]
                fresh = await con.fetchval(
                    """INSERT INTO reminder_log (task_id, generation, attempt_no, planned_for, created_at)
                       VALUES ($1, $2, $3, $4, $5)
                       ON CONFLICT DO NOTHING RETURNING 1""",
                    r["id"], generation, attempt, r["next_remind_at"], now,
                )
                checkin = r["reminder_checkin"]
                nxt = task_repeat(now, attempt, prefs, r["due_at"], r["kind"],
                                  None if r["registered"] else r["reg_deadline"], checkin=checkin)
                await con.execute(
                    "UPDATE tasks SET remind_count = $2, next_remind_at = $3, reminder_checkin = false WHERE id = $1",
                    r["id"], attempt, nxt)
                if fresh:
                    claimed.append(Claimed(r["id"], r["user_id"], r["title"], r["subject"], r["due_at"], attempt, prefs,
                                           generation, nxt, checkin, r["kind"]))
        return claimed

    async def swap_reminder_mid(self, user_id: int, task_ids: list[int], mid: str) -> list[str]:
        async with self.pool.acquire() as con, con.transaction():
            old = [r["reminder_mid"] for r in await con.fetch(
                """SELECT DISTINCT reminder_mid FROM tasks WHERE user_id = $1 AND id = ANY($2::bigint[])
                     AND reminder_mid IS NOT NULL AND reminder_mid <> $3""", user_id, task_ids, mid)]
            await con.execute("UPDATE tasks SET reminder_mid = $3 WHERE user_id = $1 AND id = ANY($2::bigint[])",
                              user_id, task_ids, mid)
            busy = {r["reminder_mid"] for r in await con.fetch(
                """SELECT DISTINCT reminder_mid FROM tasks WHERE user_id = $1 AND status = 'active'
                     AND reminder_mid = ANY($2::text[])""", user_id, old)}
        return [m for m in old if m not in busy]

    async def reschedule_failed(self, c: Claimed, error: str, retry_min: int, now: datetime):
        await self.pool.execute(
            "UPDATE reminder_log SET error = $4 WHERE task_id = $1 AND generation = $2 AND attempt_no = $3",
            c.task_id, c.generation, c.attempt, error[:500])
        if c.attempt < c.prefs.repeat_max:
            await self.pool.execute(
                """UPDATE tasks SET next_remind_at = $4, reminder_checkin = $6
                   WHERE id = $1 AND reminder_generation = $2 AND remind_count = $3
                     AND status = 'active' AND NOT needs_schedule AND NOT reminders_muted
                     AND next_remind_at IS NOT DISTINCT FROM $5""",
                c.task_id, c.generation, c.attempt, shift_out_of_quiet(now + timedelta(minutes=retry_min), c.prefs),
                c.next_at, c.checkin,
            )

    async def create_login_token(self, user_id: int, ttl: timedelta = timedelta(minutes=10)) -> str:
        token = secrets.token_urlsafe(32)
        await self.pool.execute(
            "INSERT INTO login_tokens (token_hash, user_id, expires_at) VALUES ($1, $2, $3)",
            hashlib.sha256(token.encode()).hexdigest(), user_id, datetime.now(timezone.utc) + ttl,
        )
        return token

    async def revoke_browser_sessions(self, user_id: int) -> None:
        await self.pool.execute(
            """WITH changed AS (UPDATE users SET browser_revoked_at = clock_timestamp() WHERE id = $1 RETURNING id)
               DELETE FROM login_tokens WHERE user_id IN (SELECT id FROM changed)""", user_id)

    async def create_alice_code(self, user_id: int, secret: str) -> str:
        for _ in range(5):
            code = f"{secrets.randbelow(1_000_000):06d}"
            digest = hmac.new(secret.encode(), code.encode(), hashlib.sha256).hexdigest()
            try:
                await self.pool.execute(
                    """INSERT INTO alice_link_codes (user_id, code_hash, expires_at)
                       VALUES ($1, $2, now() + interval '5 minutes') ON CONFLICT (user_id) DO UPDATE
                       SET code_hash = EXCLUDED.code_hash, expires_at = EXCLUDED.expires_at""", user_id, digest)
            except asyncpg.UniqueViolationError:
                continue
            return code
        raise RuntimeError("Не удалось выпустить код")

    async def unlink_alice(self, user_id: int) -> None:
        async with self.pool.acquire() as con, con.transaction():
            await con.execute("DELETE FROM alice_link_codes WHERE user_id = $1", user_id)
            await con.execute("DELETE FROM alice_links WHERE user_id = $1", user_id)

    async def claim_alice_messages(self):
        return await self.pool.fetch(
            """WITH ready AS (
                   SELECT i.event_key, l.user_id, u.tz, i.text FROM alice_inbox i
                   JOIN alice_links l ON l.identity_hash = i.identity_hash JOIN users u ON u.id = l.user_id
                   WHERE i.claimed_at IS NULL AND i.created_at > now() - interval '1 hour' AND u.bot_active
                   ORDER BY i.created_at LIMIT 4 FOR UPDATE OF i SKIP LOCKED
               )
               UPDATE alice_inbox i SET claimed_at = now() FROM ready
               WHERE i.event_key = ready.event_key RETURNING ready.*""")

    async def claim_voice_jobs(self) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            """WITH ready AS (
                   SELECT v.id FROM voice_jobs v
                   WHERE v.status = 'pending' AND v.created_at > now() - interval '10 minutes'
                   ORDER BY v.created_at LIMIT 2 FOR UPDATE SKIP LOCKED
               )
               UPDATE voice_jobs v SET status = 'working', claimed_at = now() FROM ready, users u
               WHERE v.id = ready.id AND u.id = v.user_id
               RETURNING v.id, v.user_id, v.path, u.tz""")

    async def finish_voice_job(self, job_id: int, result: dict | None, error: str | None) -> None:
        await self.pool.execute(
            """UPDATE voice_jobs SET status = CASE WHEN $3::text IS NULL THEN 'done' ELSE 'error' END,
                                     result = $2::jsonb, error = $3, path = NULL WHERE id = $1""",
            job_id, json.dumps(result, ensure_ascii=False) if result is not None else None, error)

    async def old_voice_files(self) -> list[str]:
        rows = await self.pool.fetch(
            "DELETE FROM voice_jobs WHERE created_at < now() - interval '1 day' RETURNING path")
        return [r["path"] for r in rows if r["path"]]

    async def clear_alice_message(self, event_key: str) -> None:
        await self.pool.execute("UPDATE alice_inbox SET text = '' WHERE event_key = $1", event_key)

    async def schedule_pending(self, now: datetime) -> int:
        async with self.pool.acquire() as con, con.transaction():
            rows = await con.fetch(
                """SELECT t.id, t.user_id, t.status, t.due_at, t.reminders_muted, t.remind_on, t.kind, t.duration_min,
                          t.reg_deadline, t.registered,
                          u.tz, u.quiet_from, u.quiet_to, u.repeat_min, u.repeat_max, u.work_schedule, u.morning_at,
                          u.remind_mode
                   FROM tasks t JOIN users u ON u.id = t.user_id
                   WHERE t.needs_schedule ORDER BY t.due_at NULLS LAST, t.id
                   FOR UPDATE OF t SKIP LOCKED""",
            )
            context = {}
            for r in rows:
                prefs = _prefs(r)
                owner = r["user_id"]
                if prefs.work_schedule != "classic" and r["kind"] == "homework" and owner not in context:
                    context[owner] = await self.work_context(con, owner, now)
                scores, occupied = context.get(owner, ({}, []))
                if r['status'] == 'active' and remind_ok(prefs.remind_mode, r['reminders_muted'], r['remind_on']):
                    remind_at = first_remind(r['due_at'], now, prefs, kind=r['kind'], duration=r['duration_min'], reg=None if r['registered'] else r['reg_deadline'], scores=scores, occupied=occupied)
                else:
                    remind_at = None
                if remind_at and r["kind"] == "homework":
                    occupied.append(remind_at)
                await con.execute(
                    """UPDATE tasks SET next_remind_at = $2, remind_count = 0, needs_schedule = false,
                                        reminder_generation = reminder_generation + 1, reminder_checkin = false
                       WHERE id = $1""",
                    r["id"], remind_at,
                )
        return len(rows)

    async def add_attachment(self, user_id: int, task_id: int, kind: str, name: str, mime: str | None,
                             size: int, path: str) -> int | None:
        return await self.pool.fetchval(
            """WITH t AS (SELECT id, user_id FROM tasks WHERE id = $1 AND user_id = $2),
                    a AS (INSERT INTO attachments (user_id, kind, name, mime, size_bytes, path)
                          SELECT user_id, $3, $4, $5, $6, $7 FROM t RETURNING id),
                    l AS (INSERT INTO attachment_tasks (attachment_id, task_id) SELECT a.id, t.id FROM a, t)
               SELECT id FROM a""",
            task_id, user_id, kind, name, mime, size, path,
        )

    async def add_loose_attachment(self, user_id: int, kind: str, name: str, mime: str | None,
                                   size: int, path: str) -> int:
        return await self.pool.fetchval(
            """INSERT INTO attachments (user_id, kind, name, mime, size_bytes, path)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""", user_id, kind, name, mime, size, path)

    async def loose_attachments(self, user_id: int, ids: list[int]) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            """SELECT a.id, a.kind, a.name FROM attachments a
               WHERE a.user_id = $1 AND a.id = ANY($2::bigint[])
                 AND NOT EXISTS (SELECT 1 FROM attachment_tasks l WHERE l.attachment_id = a.id)
               ORDER BY a.id""", user_id, ids)

    async def link_attachments(self, user_id: int, task_id: int, ids: list[int]) -> int:
        rows = await self.pool.fetch(
            """INSERT INTO attachment_tasks (attachment_id, task_id)
               SELECT a.id, t.id FROM attachments a, tasks t
               WHERE a.id = ANY($3::bigint[]) AND a.user_id = $1 AND t.id = $2 AND t.user_id = $1
               ON CONFLICT DO NOTHING RETURNING attachment_id""", user_id, task_id, ids)
        return len(rows)

    async def task_materials(self, user_id: int, task_id: int) -> tuple[list, list]:
        links = await self.pool.fetch(
            """SELECT l.url FROM task_links l JOIN tasks t ON t.id = l.task_id
               WHERE t.id = $1 AND t.user_id = $2 ORDER BY l.id""", task_id, user_id)
        files = await self.pool.fetch(
            """SELECT a.id, a.kind, a.name FROM attachments a JOIN attachment_tasks l ON l.attachment_id = a.id
               JOIN tasks t ON t.id = l.task_id WHERE t.id = $1 AND t.user_id = $2 AND a.user_id = $2 ORDER BY a.id""",
            task_id, user_id)
        return links, files

    async def get_attachment(self, user_id: int, attachment_id: int):
        return await self.pool.fetchrow(
            "SELECT kind, name, path FROM attachments WHERE user_id = $1 AND id = $2", user_id, attachment_id)

    async def claim_attachment_deliveries(self) -> list[asyncpg.Record]:
        return await self.pool.fetch(
            """WITH next AS (
                   SELECT q.attachment_id, a.user_id, a.kind, a.name, a.path FROM attachment_deliveries q
                   JOIN attachments a ON a.id = q.attachment_id JOIN users u ON u.id = a.user_id
                   WHERE q.claimed_at IS NULL AND u.bot_active ORDER BY q.queued_at LIMIT 4
                   FOR UPDATE OF q SKIP LOCKED
               )
               UPDATE attachment_deliveries q SET claimed_at = now() FROM next
               WHERE q.attachment_id = next.attachment_id RETURNING next.*""")

    async def finish_attachment_delivery(self, attachment_id: int, *, sent: bool) -> None:
        await self.pool.execute(
            """UPDATE attachment_deliveries SET sent_at = CASE WHEN $2 THEN now() END, failed = NOT $2
               WHERE attachment_id = $1""", attachment_id, sent)

    async def add_link(self, user_id: int, task_id: int, url: str) -> bool:
        return await self.pool.fetchval(
            """INSERT INTO task_links (task_id, url)
               SELECT id, $3 FROM tasks WHERE id = $1 AND user_id = $2 AND status = 'active'
               RETURNING true""", task_id, user_id, url) is True
