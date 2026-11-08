import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


DEFAULT_TZ = "Europe/Samara"
_DURATION_WORDS = {"один": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5,
                   "десять": 10, "пятнадцать": 15, "двадцать": 20, "тридцать": 30, "сорок": 40,
                   "сорок пять": 45}
_NUMBER = "|".join(sorted(_DURATION_WORDS, key=len, reverse=True))
_DURATION = re.compile(rf"(?<!\w)(?:(\d{{1,2}}|{_NUMBER})(\s+с половиной)?\s*час(?:а|ов)?\b)?"
                       rf"(?:\s*(\d{{1,3}}|{_NUMBER})\s*минут(?:а|ы)?\b)?")


def duration_from_text(text: str) -> int | None:
    low = text.lower().replace("ё", "е")
    if re.search(r"\bполчаса\b", low):
        return 30
    if re.search(r"\bполтора часа\b", low):
        return 90
    for match in _DURATION.finditer(low):
        hours, half, minutes = match.groups()
        if not (hours or minutes):
            continue
        if hours and re.search(r"\b(?:в|к|до)\s*$", low[:match.start()]):
            continue
        if hours and hours.isdecimal():
            h = int(hours)
        else:
            h = _DURATION_WORDS.get(hours, 0)
        if minutes and minutes.isdecimal():
            m = int(minutes)
        else:
            m = _DURATION_WORDS.get(minutes, 0)
        total = h * 60 + (30 if half else 0) + m
        if 1 <= total <= 1440:
            return total
    return None

SUBJECT_PATTERNS = [
    ("Алгебра", r"алгеб\w*"),
    ("Геометрия", r"геом\w*"),
    ("Математика", r"матем\w*|\bмат\b"),
    ("Русский язык", r"русск\w*|\bрус\b"),
    ("Литература", r"литер\w*|\bлит\b"),
    ("Английский язык", r"англ\w*"),
    ("Немецкий язык", r"немецк\w*"),
    ("Французский язык", r"француз\w*|франц\w*"),
    ("Физика", r"физик\w*"),
    ("Физкультура", r"физр\w*|физкульт\w*"),
    ("Химия", r"\bхим\b|хими\w*"),
    ("Биология", r"биолог\w*|\bбио\b"),
    ("География", r"географ\w*|\bгеогр\b"),
    ("История", r"истори\w*"),
    ("Обществознание", r"обществ\w*|\bобщ\b"),
    ("Информатика", r"информат\w*|\bинф\b"),
    ("Астрономия", r"астроном\w*"),
    ("ОБЖ", r"\bобж\b"),
    ("Технология", r"технолог\w*|\bтруд\b"),
    ("ИЗО", r"\bизо\b"),
    ("Музыка", r"музык\w*"),
    ("Экономика", r"эконом\w*"),
    ("Право", r"\bправо\b|\bправа\b"),
]
_COMPILED = [(name, re.compile(p)) for name, p in SUBJECT_PATTERNS]


def find_subject(text: str) -> str | None:
    low = text.lower().replace("ё", "е")
    best = None
    for name, rx in _COMPILED:
        m = rx.search(low)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), name)
    if best:
        return best[1]
    return None


@dataclass
class ParsedTask:
    title: str
    subject: str | None
    due_at: datetime | None
    kind: str = "homework"
    location: str | None = None
    reg_deadline: datetime | None = None
    is_task: bool = True
    more: list["ParsedTask"] = field(default_factory=list)
    duration_min: int | None = None


class TaskParser(Protocol):
    async def parse(self, text: str, now: datetime, tz: str = DEFAULT_TZ) -> ParsedTask: ...


class ParserUnavailable(Exception):
    """GigaChat не ответил или ответил непонятно — задание не разобрано, человека просим прислать ещё раз."""
