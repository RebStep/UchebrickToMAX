import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.dates import _date_from, _time_from, parse_when
from core.parser import duration_from_text, find_subject

_CHANGE = re.compile(r"\b(?:перен[её]с\w*|перенос\w*|сдвин\w*|теперь|передвин\w*)\b", re.IGNORECASE)
_NAME = re.compile(r"[а-яё]{4,}", re.IGNORECASE)
_GENERIC = {"теперь", "позже", "раньше", "завтра", "сегодня", "послезавтра", "часов", "минут", "через", "полчаса"}


def match_change(text: str, tasks, now: datetime, tz: str):
    change = _CHANGE.search(text)
    if not change:
        return None
    low = text.lower()
    words = set(_NAME.findall(low)) - _GENERIC
    words.discard(change[0].lower())
    subject = find_subject(text)
    candidates = []
    for task in tasks:
        if not task["due_at"] or (subject and task["subject"] and task["subject"] != subject):
            continue
        title = task["title"].strip().lower()
        common = set(_NAME.findall(title)) & words
        if len(title) >= 4 and title in low:
            rank = 3
        elif common and subject and task["subject"] == subject:
            rank = 2
        elif common and task["kind"] == "event":
            rank = 1
        else:
            continue
        candidates.append((rank, task))
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    if not candidates or (len(candidates) > 1 and candidates[0][0] == candidates[1][0]):
        return None
    task = candidates[0][1]
    old = task["due_at"]
    if re.search(r"\b(?:позже|раньше)\b", low):
        minutes = duration_from_text(low)
        if minutes:
            return task, old + timedelta(minutes=-minutes if "раньше" in low else minutes)
    zone = ZoneInfo(tz)
    local_now = now.astimezone(zone).replace(tzinfo=None)
    local_old = old.astimezone(zone)
    day, _ = _date_from(low.replace("ё", "е"), local_now.date())
    if day is not None:
        new = parse_when(low, local_now, default_time=local_old.time())
    else:
        at = _time_from(low)
        if at is not None:
            new = datetime.combine(local_old.date(), at)
        else:
            new = None
    if new is None:
        return None
    new = new.replace(tzinfo=zone).astimezone(old.tzinfo)
    if new != old:
        return (task, new)
    return None
