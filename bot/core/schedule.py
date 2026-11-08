from collections import Counter
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

EVENING = time(18, 0)
FIRST_LEAD = timedelta(hours=24)
WORK_HOURS = {"school": ((16, 21), (11, 19)), "evening": ((18, 22), (14, 21))}


@dataclass
class Prefs:
    tz: str = "Europe/Samara"
    quiet_from: time = time(22, 0)
    quiet_to: time = time(7, 0)
    repeat_min: int = 60
    repeat_max: int = 5
    work_schedule: str = "classic"
    morning_at: time | None = None
    remind_mode: str = "all"


def in_quiet(local_time: time, quiet_from: time, quiet_to: time) -> bool:
    if quiet_from == quiet_to:
        return False
    if quiet_from < quiet_to:
        return quiet_from <= local_time < quiet_to
    return local_time >= quiet_from or local_time < quiet_to


def shift_out_of_quiet(moment: datetime, prefs: Prefs) -> datetime:
    zone = ZoneInfo(prefs.tz)
    local = moment.astimezone(zone)
    if not in_quiet(local.time(), prefs.quiet_from, prefs.quiet_to):
        return moment
    overnight = prefs.quiet_from > prefs.quiet_to
    if not overnight or local.time() < prefs.quiet_to:
        day = local.date()
    else:
        day = local.date() + timedelta(days=1)
    end = datetime.combine(day, prefs.quiet_to).replace(tzinfo=zone)
    return end.astimezone(timezone.utc)


def next_after_send(now: datetime, sent_count: int, prefs: Prefs) -> datetime | None:
    if sent_count >= prefs.repeat_max:
        return None
    return shift_out_of_quiet(now + timedelta(minutes=prefs.repeat_min), prefs)


def evening_remind(now: datetime, prefs: Prefs) -> datetime:
    local = now.astimezone(ZoneInfo(prefs.tz))
    day = local.date() + timedelta(days=local.time() >= EVENING)
    return shift_out_of_quiet(datetime.combine(day, EVENING, local.tzinfo).astimezone(timezone.utc), prefs)


def _smart_moments(due: datetime, prefs: Prefs, kind: str, reg: datetime | None) -> list[datetime]:
    local = due.astimezone(ZoneInfo(prefs.tz))
    earlier = datetime.combine(local.date() - timedelta(days=1), EVENING, local.tzinfo)
    day_only = (local.hour, local.minute) == (23, 59)
    if kind == 'todo' and day_only:
        final = datetime.combine(local.date(), time(8), local.tzinfo)
    else:
        final = due - timedelta(hours=1)
    moments = [earlier, final]
    if reg and kind in ("event", "project"):
        moments += [reg - timedelta(days=3), reg - timedelta(days=1)]
    return sorted({shift_out_of_quiet(moment.astimezone(timezone.utc), prefs) for moment in moments})


def homework_slot(due: datetime, now: datetime, prefs: Prefs, duration: int | None,
                  scores: dict[int, float], occupied: list[datetime]) -> datetime | None:
    zone = ZoneInfo(prefs.tz)
    local_due, local_now = due.astimezone(zone), now.astimezone(zone)
    if (local_due.hour, local_due.minute) == (23, 59):
        local_due = local_due.replace(hour=8, minute=0)
    budget = timedelta(minutes=duration or 45)
    work = WORK_HOURS[prefs.work_schedule]
    booked = Counter(at.astimezone(zone).replace(minute=0, second=0, microsecond=0) for at in occupied)
    candidates = []
    for offset in range(min(14, max(0, (local_due.date() - local_now.date()).days)) + 1):
        day = local_now.date() + timedelta(days=offset)
        start_hour, end_hour = work[day.weekday() >= 5]
        start = max(datetime.combine(day, time(start_hour), zone), local_now + timedelta(minutes=1))
        end = min(datetime.combine(day, time(end_hour), zone), local_due)
        while start + budget <= end:
            awake = shift_out_of_quiet(start, prefs).astimezone(zone)
            if awake + budget > end:
                break
            hour = awake.weekday() * 24 + awake.hour
            slot = awake.replace(minute=0, second=0, microsecond=0)
            score = scores.get(hour, 0) - booked[slot] * 0.8 - offset * 0.5
            candidates.append((-score, awake.astimezone(timezone.utc)))
            start = awake + timedelta(hours=1)
    if candidates:
        return min(candidates)[1]
    return None


def task_repeat(now: datetime, sent_count: int, prefs: Prefs, due: datetime | None, kind: str,
                reg: datetime | None = None, *, checkin: bool = False) -> datetime | None:
    if sent_count >= prefs.repeat_max:
        return None
    if prefs.work_schedule == "classic" or due is None or checkin:
        return next_after_send(now, sent_count, prefs)
    if kind == "homework":
        return None
    if kind in ("event", "todo"):
        for moment in _smart_moments(due, prefs, kind, reg):
            if now < moment < due:
                return moment
        return None
    if kind == "project" and now < due:
        at = shift_out_of_quiet(now + max(timedelta(hours=6), (due - now) / 2), prefs)
        if at < due:
            return at
        return None
    return next_after_send(now, sent_count, prefs)


def first_remind(due_at: datetime | None, now: datetime, prefs: Prefs, *, kind: str = "homework",
                 duration: int | None = None, reg: datetime | None = None,
                 scores: dict[int, float] | None = None, occupied: list[datetime] | None = None) -> datetime | None:
    if due_at and prefs.work_schedule in WORK_HOURS:
        if kind in ("event", "todo"):
            soon = shift_out_of_quiet(now + timedelta(minutes=1), prefs)
            for moment in _smart_moments(due_at, prefs, kind, reg):
                if now < moment < due_at:
                    return moment
            if soon < due_at:
                return soon
            return None
        if kind == "homework":
            slot = homework_slot(due_at, now, prefs, duration, scores or {}, occupied or [])
            if slot:
                return slot
        if kind == "project" and now < due_at:
            return shift_out_of_quiet(now + timedelta(minutes=10), prefs)
    if due_at is not None:
        moment = due_at - FIRST_LEAD
        if moment <= now:
            moment = now + timedelta(minutes=prefs.repeat_min)
    else:
        zone = ZoneInfo(prefs.tz)
        local = now.astimezone(zone)
        if local.time() < EVENING:
            day = local.date()
        else:
            day = local.date() + timedelta(days=1)
        moment = datetime.combine(day, EVENING).replace(tzinfo=zone).astimezone(timezone.utc)
    return shift_out_of_quiet(moment, prefs)
