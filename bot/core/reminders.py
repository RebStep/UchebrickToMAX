import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

from core.format import h, task_block, task_line, when_label
from core.repo import Repo
from core.schedule import in_quiet

log = logging.getLogger(__name__)
RETRY_AFTER_ERROR_MIN = 2
GROUP_SIZE = 8


class ReminderSender(Protocol):
    async def send_reminder(self, user_id: int, text: str, task_id: int) -> str | None: ...
    async def send_reminders(self, user_id: int, text: str, task_ids: list[int]) -> str | None: ...
    async def delete_message(self, mid: str) -> None: ...
    async def send_morning(self, user_id: int, text: str) -> None: ...
    async def send_olympiad(self, user_id: int, text: str, olympiad_id: int, registration: bool) -> None: ...


REMINDER_HEAD = "🔔 <b>Не забудь</b>"


def reminder_text(items, tz: str, now: datetime) -> str:
    blocks = [task_block(when_label(due, tz, now, kind), subject, title[:200]) for subject, title, due, kind in items]
    return REMINDER_HEAD + "\n" + "\n".join(blocks)


def morning_text(tasks, now: datetime, tz: str) -> str | None:
    zone = ZoneInfo(tz)
    today = now.astimezone(zone).date()
    blocks = []
    for task in tasks:
        deadline = task["due_at"]
        reminder = task["next_remind_at"]
        if not task['registered']:
            reg = task['reg_deadline']
        else:
            reg = None
        if deadline and deadline.astimezone(zone).date() <= today:
            label = when_label(deadline, tz, now, task["kind"])
        elif reminder and reminder.astimezone(zone).date() == today:
            label = f"начать в {reminder.astimezone(zone):%H:%M}"
        elif reg and reg >= now and reg.astimezone(zone).date() == today:
            label = f"регистрация до {reg.astimezone(zone):%H:%M}"
        else:
            continue
        blocks.append(task_block(label, task["subject"], task["title"][:90]))
        if len(blocks) == 10:
            break
    if blocks:
        return '☀️ <b>План на сегодня</b>\n' + '\n'.join(blocks)
    return None


def olympiad_notices(olympiad, now: datetime):
    zone = ZoneInfo(olympiad["tz"])
    local_now = now.astimezone(zone)
    if in_quiet(local_now.time(), olympiad["quiet_from"], olympiad["quiet_to"]):
        return
    if not olympiad["registered"]:
        opens = olympiad["reg_opens"]
        deadline = olympiad["reg_deadline"]
        if opens and opens <= now and opens.astimezone(zone).date() == local_now.date() and (not deadline or deadline > now):
            yield f"open:{opens.isoformat()}", "Открылась регистрация", opens, True
        if deadline and now < deadline <= now + timedelta(days=1):
            yield f"reg:{deadline.isoformat()}", "Скоро закрывается регистрация", deadline, True
    for tour in json.loads(olympiad["tours"]):
        if tour.get("done"):
            continue
        raw = tour.get("deadline") or tour.get("starts_at")
        if not raw:
            continue
        at = datetime.fromisoformat(raw)
        if not now < at <= now + timedelta(days=1):
            continue
        event = tour.get("starts_at") == tour.get("deadline")
        title = tour.get("title") or "Тур"
        if event and at - now <= timedelta(hours=1):
            phase = 'hour'
        else:
            phase = 'day'
        if event:
            label = f'Скоро начнётся: {title}'
        else:
            label = f'Скоро закончится: {title}'
        yield f"{phase}:{title}:{at.astimezone(timezone.utc).isoformat()}", label, at, False


async def tick(repo: Repo, sender: ReminderSender, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    sent = 0
    await repo.archive_events(now)
    await repo.schedule_pending(now)
    await repo.plan_ignored_homework(now)
    groups: dict[int, list] = {}
    for c in await repo.claim_due(now):
        if not await repo.reminder_current(c):
            continue
        if c.checkin:
            sent += await _send(repo, sender, now, [c], sender.send_reminder(
                c.user_id, f"✍️ <b>Как успехи?</b>\n<blockquote>{task_line(c.subject, c.title)}</blockquote>", c.task_id))
            continue
        groups.setdefault(c.user_id, []).append(c)
    batches = [(user_id, items[i:i + GROUP_SIZE])
               for user_id, items in groups.items() for i in range(0, len(items), GROUP_SIZE)]
    for user_id, items in batches:
        text = reminder_text([(c.subject, c.title, c.due_at, c.kind) for c in items], items[0].prefs.tz, now)
        if len(items) == 1:
            send = sender.send_reminder(user_id, text, items[0].task_id)
        else:
            send = sender.send_reminders(user_id, text, [c.task_id for c in items])
        sent += await _send(repo, sender, now, items, send)
    for user in await repo.claim_mornings(now):
        text = morning_text(await repo.list_active(user["id"]), now, user["tz"])
        if text:
            try:
                await sender.send_morning(user["id"], text)
            except Exception:
                log.warning("Утренний план не отправлен пользователю %s", user["id"])
    for olympiad in await repo.upcoming_olympiads(now):
        for key, label, at, registration in olympiad_notices(olympiad, now):
            if not await repo.claim_olympiad_notice(olympiad["id"], key, registration):
                continue
            when = when_label(at, olympiad["tz"], now, "event" if label.startswith("Скоро начнётся") else "homework")
            text = f"🏅 <b>{h(label)}</b>\n" + task_block(when, olympiad["subject"], olympiad["name"])
            try:
                await sender.send_olympiad(olympiad["user_id"], text, olympiad["id"], registration)
            except Exception:
                log.warning("Напоминание об олимпиаде %s не отправлено", olympiad["id"])
    return sent


async def _send(repo: Repo, sender: ReminderSender, now: datetime, items, send) -> int:
    try:
        mid = await send
    except Exception as e:
        log.warning("Напоминание по заданиям %s не отправлено: %s", [c.task_id for c in items], e)
        for c in items:
            await repo.reschedule_failed(c, str(e), RETRY_AFTER_ERROR_MIN, now)
        return 0
    if mid:
        for old in await repo.swap_reminder_mid(items[0].user_id, [c.task_id for c in items], mid):
            try:
                await sender.delete_message(old)
            except Exception as e:
                log.info("Прошлое напоминание %s не удалено: %s", old, e)
    return len(items)
