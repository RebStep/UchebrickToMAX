import html
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
           "ноября", "декабря"]


def h(text: str | None) -> str:
    return html.escape(text or "", quote=False)


def task_line(subject: str | None, title: str) -> str:
    if subject:
        return f'<b>{h(subject)}</b>: {h(title)}'
    return h(title)


def format_due(due: datetime | None, tz: str) -> str:
    if due is None:
        return "без срока"
    d = due.astimezone(ZoneInfo(tz))
    return f"{_WEEKDAYS[d.weekday()]}, {d.day} {_MONTHS[d.month - 1]}, {d:%H:%M}"


def _day_title(d, today) -> str:
    delta = (d - today).days
    if delta == 0:
        return "Сегодня"
    if delta == 1:
        return "Завтра"
    return f"{_WEEKDAYS[d.weekday()]}, {d.day} {_MONTHS[d.month - 1]}"


_TITLE_WIDTH = len("Без срока") + 2 * 5


def section_title(key: str) -> str:
    dashes = max(4, _TITLE_WIDTH - len(key))
    left = dashes // 2
    return f"• {'─' * left} [ {key} ] {'─' * (dashes - left)} •"


FILTERS = {"today": "Сегодня", "week": "Неделя", "all": "Все"}


def filter_tasks(tasks, tz: str, now: datetime, flt: str) -> list:
    if flt not in ("today", "week"):
        return list(tasks)
    zone = ZoneInfo(tz)
    last = now.astimezone(zone).date()
    if flt != "today":
        last += timedelta(days=6)
    result = []
    for task in tasks:
        due = task["due_at"]
        if due is None or due.astimezone(zone).date() <= last:
            result.append(task)
    return result


def _date(d) -> str:
    return f"{_WEEKDAYS[d.weekday()]}, {d.day} {_MONTHS[d.month - 1]}"


def when_label(due: datetime | None, tz: str, now: datetime, kind: str = "homework", *, with_day: bool = True) -> str:
    if due is None:
        return "без срока"
    zone = ZoneInfo(tz)
    local = due.astimezone(zone)
    delta = (local.date() - now.astimezone(zone).date()).days
    if not with_day or delta == 0:
        day = ''
    elif delta == 1:
        day = 'завтра'
    else:
        day = _date(local)
    if (local.hour, local.minute) == (23, 59):
        if not day:
            if kind == 'event':
                return 'весь день'
            return 'до конца дня'
        if kind == 'event':
            return day
        return f"до {('завтра' if delta == 1 else _date(local))}"
    if kind == 'event':
        clock = f'в {local:%H:%M}'
    else:
        clock = f'до {local:%H:%M}'
    if day:
        return f'{day} {clock}'
    return clock


def full_when(due: datetime | None, tz: str, kind: str = "homework") -> str:
    if due is None:
        return "без срока"
    return f"{_date(due.astimezone(ZoneInfo(tz)))}, {when_label(due, tz, due, kind, with_day=False)}"


def task_block(label: str, subject: str | None, title: str, *, head: str = "", tail: str = "", done: bool = False) -> str:
    what = task_line(subject, title)
    if done:
        return f"{head}<s>{h(label)}</s>{tail}\n<blockquote><s>{what}</s></blockquote>"
    return f"{head}<b>{h(label)}</b>{tail}\n<blockquote>{what}</blockquote>"


def render_task_list(tasks, tz: str, now: datetime, limit: int = 30, link=None,
                     flt: str = "all") -> str:
    def mark(icon: str, payload: str) -> str:
        if link:
            return f'<a href="{h(link(payload))}">{icon}</a>'
        return icon

    zone = ZoneInfo(tz)
    today = now.astimezone(zone).date()
    sections: dict[str, list] = {}
    order: list[tuple[int, object, str]] = []
    for t in tasks[:limit]:
        due = t["due_at"]
        if due is None:
            key, rank = "Без срока", (3, None)
        elif due < now and t.get("status", "active") == "active":
            key, rank = "Просрочено", (0, None)
        else:
            d = due.astimezone(zone).date()
            key, rank = _day_title(d, today), (1 if d <= today else 2, d)
        if key not in sections:
            sections[key] = []
            order.append((rank[0], rank[1] or today, key))
        sections[key].append(t)

    period = {"today": f"на {today.day} {_MONTHS[today.month - 1]}", "week": "на неделю"}.get(flt, "— все")
    lines = [f"🎓 <b>Мои дела</b> {period}"]
    for _, _, key in sorted(order, key=lambda r: (r[0], r[1])):
        lines.append(f"\n<b>{section_title(key)}</b>")
        for t in sections[key]:
            tid = t["id"]
            title = t["title"][:120] + ("…" if len(t["title"]) > 120 else "")
            label = when_label(t["due_at"], tz, now, t.get("kind") or "homework", with_day=key == "Просрочено")
            if key == "Без срока":
                label = "когда удобно"
            if t.get("status") == "done":
                lines.append(task_block(label, t["subject"], title, head=mark("✅", f"lu_{tid}") + " ", done=True))
            else:
                if link:
                    pencil = f" {mark('✏️', f'le_{tid}')}"
                else:
                    pencil = ''
                lines.append(task_block(label, t["subject"], title, head=mark("🔲", f"ld_{tid}") + " ", tail=pencil))
    if not tasks:
        lines.append("\n" + {"today": "На сегодня ничего нет 🎉", "week": "На неделю ничего нет 🎉"}.get(flt, "Всё сделано 🎉"))
    if len(tasks) > limit:
        lines.append(f"\n…и ещё {len(tasks) - limit}: все задания на карте.")
    return "\n".join(lines)
