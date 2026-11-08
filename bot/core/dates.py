import re
from datetime import date, datetime, time, timedelta

WEEKDAY_STEMS = ["понедельник", "вторник", "сред", "четверг", "пятниц", "суббот", "воскресен"]
MONTH_STEMS = ["январ", "феврал", "март", "апрел", "ма", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"]
NUMBER_WORDS = {"один": 1, "одну": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7}
NO_DEADLINE = re.compile(r"^\s*(без срока|нет|никогда|убрать срок|без даты)\s*[.!]?\s*$", re.IGNORECASE)

_TIME_COLON = re.compile(r"(?<![\d.])([01]?\d|2[0-3]):([0-5]\d)(?!\d)")
_TIME_WORDS = re.compile(r"\b(?:в|к|до|на)\s+([01]?\d|2[0-3])(?:[.:]([0-5]\d))?(?:\s*ч(?:ас(?:а|ов|ам)?)?\.?)?"
                         r"(?:\s+(утра|дня|вечера|ночи))?(?![\d./])")
_DATE_NUM = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?![\d:])")
_DAY_WORD = re.compile(r"(?<!\d)(\d{1,2})\s+([а-я]{3,})")
MONTH_FORMS = [("января", "январь"), ("февраля", "февраль"), ("марта", "март"), ("апреля", "апрель"), ("мая", "май"),
               ("июня", "июнь"), ("июля", "июль"), ("августа", "август"), ("сентября", "сентябрь"),
               ("октября", "октябрь"), ("ноября", "ноябрь"), ("декабря", "декабрь")]


def _distance(a: str, b: str) -> int:
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def month_of(word: str) -> int | None:
    if word in ("май", "мая", "мае"):
        return 5
    for i, stem in enumerate(MONTH_STEMS):
        if stem != "ма" and word.startswith(stem):
            return i + 1
    for i, forms in enumerate(MONTH_FORMS):
        if len(word) >= 3 and i != 4 and forms[1].startswith(word):
            return i + 1
    if len(word) <= 3:
        limit = 0
    elif len(word) <= 5:
        limit = 1
    else:
        limit = 2
    scored = sorted((min(_distance(word, f) for f in forms), i) for i, forms in enumerate(MONTH_FORMS))
    if scored[0][0] <= limit and scored[0][0] < scored[1][0]:
        return scored[0][1] + 1
    return None


class _DayMonth:
    def __init__(self, m: re.Match, month: int):
        self.match, self.day, self.month = m, int(m[1]), month

    def start(self):
        return self.match.start()

    def end(self):
        return self.match.end()


class _DateWords:

    @staticmethod
    def search(text: str):
        for m in _DAY_WORD.finditer(text):
            month = month_of(m[2])
            if month:
                return _DayMonth(m, month)
        return None


_DATE_WORDS = _DateWords()
_IN_DAYS = re.compile(r"через\s+(\d+|" + "|".join(NUMBER_WORDS) + r")?\s*(дн|день|недел)[а-я]*")
_WEEKDAY = re.compile(r"(следующ[а-я]*\s+)?(" + "|".join(WEEKDAY_STEMS) + r")[а-я]*")
_DOTTED_CLOCK = re.compile(r"\bв\s+(?:[01]?\d|2[0-3])\.[0-5]\d(?![\d./])")


def _date_number(text: str):
    clock = _DOTTED_CLOCK.search(text)
    return next((match for match in _DATE_NUM.finditer(text)
                 if not clock or not clock.start() <= match.start() < clock.end()), None)


def is_no_deadline(text: str) -> bool:
    return bool(NO_DEADLINE.match(text))


def _time_from(text: str) -> time | None:
    m = _TIME_COLON.search(text)
    if m:
        return time(int(m[1]), int(m[2]))
    m = _TIME_WORDS.search(text)
    if m:
        hour, minute, part = int(m[1]), int(m[2] or 0), m[3]
        if part in ("дня", "вечера") and hour < 12:
            hour += 12
        return time(hour, minute)
    return None


def _date_from(text: str, today: date) -> tuple[date | None, bool]:
    if "послезавтра" in text:
        return today + timedelta(days=2), False
    if "завтра" in text:
        return today + timedelta(days=1), False
    if "сегодня" in text:
        return today, False
    m = _IN_DAYS.search(text)
    if m:
        n = m[1]
        try:
            if n is None:
                n = 1
            elif n.isdecimal():
                n = int(n)
            else:
                n = NUMBER_WORDS[n]
            return today + timedelta(days=n * (7 if m[2].startswith("недел") else 1)), False
        except (ValueError, OverflowError):
            return None, False
    m = _date_number(text)
    words = _DATE_WORDS.search(text)
    if m and not words:
        day, month = int(m[1]), int(m[2])
        if m[3]:
            year = int(m[3])
        else:
            year = today.year
        if year < 100:
            year += 2000
        try:
            d = date(year, month, day)
        except ValueError:
            return None, False
        if not m[3] and d < today:
            try:
                d = d.replace(year=d.year + 1)
            except ValueError:
                return None, False
        return d, False
    if words:
        try:
            d = date(today.year, words.month, words.day)
        except ValueError:
            return None, False
        try:
            return (d.replace(year=d.year + 1) if d < today else d), False
        except ValueError:
            return None, False
    m = _WEEKDAY.search(text)
    if m:
        target = next(i for i, stem in enumerate(WEEKDAY_STEMS) if m[2].startswith(stem))
        days = (target - today.weekday()) % 7
        if m[1]:
            days = 7 - today.weekday() + target
        return today + timedelta(days=days), not m[1]
    return None, False


def parse_when(text: str, now: datetime, default_time: time = time(23, 59)) -> datetime | None:
    t = text.lower().replace("ё", "е")
    day, is_weekday = _date_from(t, now.date())
    relative = any(word in t for word in ("сегодня", "завтра")) or _IN_DAYS.search(t)
    date_match = _DATE_WORDS.search(t) or (None if relative else _date_number(t))
    if day is None and (relative or date_match):
        return None
    if day and date_match:
        time_text = t[:date_match.start()] + ' ' + t[date_match.end():]
    else:
        time_text = t
    at = _time_from(time_text)
    if day is None:
        if at is None:
            return None
        result = datetime.combine(now.date(), at)
        if result > now:
            return result
        return result + timedelta(days=1)
    result = datetime.combine(day, at or default_time)
    if is_weekday and result <= now:
        result += timedelta(days=7) 
    return result
