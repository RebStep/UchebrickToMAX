import json
import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


from core import gigachat
from core.parser import DEFAULT_TZ, ParsedTask, ParserUnavailable, find_subject

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — помощник-ежедневник школьника. Разбираешь его сообщение: текст из чата класса,
пересланное объявление или то, что он сам написал, — и превращаешь в запись для планировщика.
Сейчас: {now}.

Календарь на ближайшие две недели — даты для «в среду», «к пятнице», «через неделю» бери ТОЛЬКО отсюда,
не вычисляй день недели сам. «В среду» — ближайшая среда из списка (если сегодня среда — сегодня, если время
ещё не прошло, иначе следующая):
{calendar}

Ответь СТРОГО в формате JSON, без markdown и пояснений. Если в сообщении НЕСКОЛЬКО отдельных дел, этапов или
туров (у каждого своя дата) — верни МАССИВ таких объектов, по одному на каждое; одно дело — один объект:
{{
  "is_task": true/false,
  "kind": "homework" | "event" | "todo" | "project",
  "subject": "предмет или null",
  "text": "краткая суть своими словами, без воды",
  "deadline": "ISO 8601 дата-время или null",
  "reg_deadline": "ISO 8601 дата-время или null",
  "duration_minutes": "длительность события в минутах или null",
  "effort_minutes": "примерно сколько займёт дело или домашка в минутах, или null",
  "location": "место или ссылка, или null"
}}

is_task — почти всегда true: человек прислал это боту, чтобы записать. false ТОЛЬКО если там нет ни дела,
ни события, ни срока: приветствие, вопрос к боту, болтовня, шутка. Школьные мероприятия (педсовет, собрание,
линейка, день самоуправления, экскурсия, концерт) — это event, даже если в тексте «для учителей»: раз человек
прислал, значит он участвует. Если человек сам говорит «это событие», «это дело», «это домашка» — слушайся его.

kind — выбери один:
- "homework" — учебное задание к сроку: номера, упражнения, параграф, конспект, сочинение, выучить стих.
- "event" — то, что УСТРАИВАЮТ ДРУГИЕ и что идёт в назначенное время, куда нужно прийти или подключиться:
  урок, урок у репетитора, консультация, контрольная, экзамен, пробник, тур олимпиады из объявления
  (с названием и этапом), педсовет, собрание, линейка, мероприятие в школе, концерт, экскурсия, врач.
- "todo" — СВОИ планы и дела человека, даже если названо время: сходить в зал или на тренировку, погулять,
  сделать или порешать олимпиаду самому, доделать что-то, купить, принести, взять с собой, отдать справку,
  позвонить, записаться, оплатить. «Иду в зал в 9», «в 11 сделать олимпиаду» — todo (deadline — это время).
  Сомневаешься между event и todo — выбирай todo.
- "event" также то, что САМО случится в назначенное время без участия человека: обновятся токены, откроется
  регистрация, начнётся трансляция, выйдут результаты, закроется приём. deadline — когда это случится,
  а не «сделать до».
- "project" — большое дело, которое можно сделать в ЛЮБОЙ день до срока: заочный или онлайн этап олимпиады
  (решить до даты), проект, доклад или реферат к далёкой дате, исследовательская работа, подготовка к экзамену
  без конкретного времени, «до конца месяца прочитать книгу». Объёмная домашка больше чем на неделю — тоже project.

deadline:
- homework, todo, project — к какому моменту сделать; event — дата и время начала.
- Только дата без времени — 23:59 этого дня (для event без времени — 09:00).
- «завтра», «к понедельнику», «через неделю» — считай относительно сегодняшней даты. Срок не упомянут — null.

reg_deadline (только event и project): ТОЛЬКО если в сообщении прямо сказано про регистрацию, заявку или запись
(«регистрация до 20 октября»). Если слов «регистрация», «заявка», «записаться» нет — ВСЕГДА null.
location (только event): адрес, кабинет или ссылка, если есть; иначе null.

subject: школьный предмет, если он назван («Предмет: Русский язык», «по русскому») или понятен из контекста
(«решить уравнения» → «Алгебра»); иначе null. Пиши название ТОЛЬКО из этого списка, полностью и без сокращений:
{subjects}. Если предмета в списке нет или он не понятен — null (не выдумывай).
text: для события — название («Педсовет дублёров ко дню самоуправления»), для дела — что сделать.
Пиши как человек сказал, коротко, с большой буквы, без «надо», «нужно», «будет»: «Репетиция концерта в школе»,
«Пробник по русскому языку», «Тренировка». Дату и время в text не повторяй.

Олимпиады. Слово «олимпиада» и название («Физтех», «Росатом», «ВсОШ») оставляй в text.
- Тур в точное время (дата и время начала, «очный тур», «онлайн в 10:00») — event: deadline — время НАЧАЛА.
- Несколько этапов или туров с разными датами — отдельный объект на каждый («Олимпиада X, 1 этап», …).
- «Решить до даты», «с … по …», заочный этап в любые дни — project.

Примеры (сообщение → ответ):
{examples}
"""

WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
SUBJECT_LIST = ("Алгебра", "Геометрия", "Математика", "Русский язык", "Литература", "Английский язык",
                "Немецкий язык", "Французский язык", "Физика", "Химия", "Биология", "География", "История",
                "Обществознание", "Информатика", "Астрономия", "Физкультура", "ОБЖ", "Технология", "ИЗО", "Музыка",
                "Экономика", "Право")
KINDS = ("homework", "event", "todo", "project")


def prompt_dates(now: datetime) -> dict:
    days = []
    for i in range(14):
        d = now.date() + timedelta(days=i)
        if i == 0:
            mark = ' (сегодня)'
        elif i == 1:
            mark = ' (завтра)'
        else:
            mark = ''
        days.append(f"- {WEEKDAYS[d.weekday()]} {d.isoformat()}{mark}")
    return {"now": f"{now:%Y-%m-%d %H:%M}, {WEEKDAYS[now.weekday()]}", "calendar": "\n".join(days)}


def _next_date(month: int, day: int, now: datetime) -> date:
    d = date(now.year, month, day)
    if d >= now.date():
        return d
    return date(now.year + 1, month, day)


def prompt_examples(now: datetime) -> str:
    tomorrow = (now + timedelta(days=1)).date()
    today = now.date()
    nov18, nov8, dec6 = _next_date(11, 18, now), _next_date(11, 8, now), _next_date(12, 6, now)
    friday = now.date() + timedelta(days=(4 - now.weekday()) % 7 or 7)
    oct_due, oct_reg = _next_date(10, 25, now), _next_date(10, 20, now)
    empty = {"reg_deadline": None, "location": None}
    cases = [
        ("Завтра в 12.20 надо будет в школе репетировать концерт.",
         {"is_task": True, "kind": "event", "subject": None, "text": "Репетиция концерта в школе",
          "deadline": f"{tomorrow}T12:20:00", **empty}),
        ("сегодня в 9 иду на тренировку",
         {"is_task": True, "kind": "todo", "subject": None, "text": "Тренировка",
          "deadline": f"{today}T21:00:00" if now.hour >= 9 else f"{today}T09:00:00", **empty}),
        ("завтра в 11 сделать олимпиаду",
         {"is_task": True, "kind": "todo", "subject": None, "text": "Сделать олимпиаду",
          "deadline": f"{tomorrow}T11:00:00", **empty}),
        ("18 ноября в 11.30 у меня будет пробник по русскому языку в каб. 214",
         {"is_task": True, "kind": "event", "subject": "Русский язык", "text": "Пробник по русскому языку",
          "deadline": f"{nov18}T11:30:00", "reg_deadline": None, "location": "каб. 214"}),
        ("сегодня в 19.05 обновятся токены ии",
         {"is_task": True, "kind": "event", "subject": None, "text": "Обновление токенов ИИ",
          "deadline": f"{today}T19:05:00", **empty}),
        ("по алгебре №5, 7 и 9 к пятнице",
         {"is_task": True, "kind": "homework", "subject": "Алгебра", "text": "№ 5, 7, 9",
          "deadline": f"{friday}T23:59:00", **empty}),
        ("Заочный этап олимпиады по физике до 25 октября, регистрация до 20 октября",
         {"is_task": True, "kind": "project", "subject": "Физика", "text": "Заочный этап олимпиады по физике",
          "deadline": f"{oct_due}T23:59:00", "reg_deadline": f"{oct_reg}T23:59:00", "location": None}),
        ("завтра принести справку в школу",
         {"is_task": True, "kind": "todo", "subject": None, "text": "Принести справку в школу",
          "deadline": f"{tomorrow}T23:59:00", **empty}),
        ("Олимпиада по информатике Технокубок: первый отборочный этап 8 ноября в 15.05, и второй этап 6 декабря в 11.05.",
         [{"is_task": True, "kind": "event", "subject": "Информатика", "text": "Олимпиада Технокубок, 1 этап",
           "deadline": f"{nov8}T15:05:00", **empty},
          {"is_task": True, "kind": "event", "subject": "Информатика", "text": "Олимпиада Технокубок, 2 этап",
           "deadline": f"{dec6}T11:05:00", **empty}]),
        ("привет, как дела?",
         {"is_task": False, "kind": "todo", "subject": None, "text": "", "deadline": None, **empty}),
    ]
    return "\n\n".join(f"Сообщение: {q}\nОтвет: {json.dumps(a, ensure_ascii=False)}" for q, a in cases)


def build_prompt(local_now: datetime) -> str:
    return SYSTEM_PROMPT.format(**prompt_dates(local_now), subjects=", ".join(SUBJECT_LIST), examples=prompt_examples(local_now))


def normalize_subject(value) -> str | None:
    if not value or not str(value).strip():
        return None
    raw = " ".join(str(value).split()).strip(" .")
    if not raw or raw.lower() in ("null", "none", "нет", "без предмета"):
        return None
    for name in SUBJECT_LIST:
        if raw.lower().replace("ё", "е") == name.lower().replace("ё", "е"):
            return name
    return find_subject(raw) or raw[:1].upper() + raw[1:]


_WEEKDAY_STEMS = ["понедельник", "вторник", "сред", "четверг", "пятниц", "суббот", "воскресен"]
_WEEKDAY_RE = re.compile(r"\b(?:в|во|к|ко|до|на)\s+(" + "|".join(_WEEKDAY_STEMS) + r")[а-я]*", re.IGNORECASE)
_EXPLICIT_DATE_RE = re.compile(r"\b\d{1,2}[./]\d{1,2}\b|\b\d{1,2}\s+(?:январ|феврал|март|апрел|ма[яй]|июн|июл|август|"
                               r"сентябр|октябр|ноябр|декабр)", re.IGNORECASE)
_REG_WORDS = re.compile(r"регистр|заявк|записат|записыва|запись на", re.IGNORECASE)


def fix_weekday(raw_text: str, local: datetime | None, now: datetime) -> datetime | None:
    if not local or _EXPLICIT_DATE_RE.search(raw_text) or re.search(r"следующ", raw_text, re.IGNORECASE):
        return local
    stems = {m.group(1).lower() for m in _WEEKDAY_RE.finditer(raw_text)}
    if len(stems) != 1:
        return local
    target = _WEEKDAY_STEMS.index(stems.pop())
    if local.weekday() == target and now <= local < now + timedelta(days=7):
        return local
    fixed = datetime.combine(now.date() + timedelta(days=(target - now.weekday()) % 7), local.time())
    if fixed <= now:
        return fixed + timedelta(days=7)
    return fixed


def _local(value, kind: str = "homework") -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip()
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    if not 2000 <= dt.year <= 2100:
        return None
    if len(v) <= 10:
        dt = datetime.combine(dt.date(), time(9, 0) if kind == "event" else time(23, 59))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=None)
    return dt


_HAPPENS = re.compile(r"\b(?:обновятся|обновится|начн[её]тся|начнутся|откроется|откроются|закроется|закроются|"
                      r"выйдет|выйдут|состоится|появятся|появится|сбросятся|сбросится|пройд[её]т|пройдут)\b", re.IGNORECASE)


def _item(data: dict, raw_text: str, local_now: datetime, zone: ZoneInfo) -> ParsedTask:
    if data.get('kind') in KINDS:
        kind = data.get('kind')
    else:
        kind = 'homework'
    deadline = str(data.get("deadline") or "")
    if kind in ("todo", "homework") and len(deadline) > 10 and not deadline.endswith("23:59:00") and _HAPPENS.search(raw_text):
        kind = "event"
    to_utc = lambda d: (d.replace(tzinfo=zone) if d.tzinfo is None else d).astimezone(timezone.utc) if d else None  # noqa: E731
    due = fix_weekday(raw_text, _local(data.get("deadline"), kind), local_now)
    due_utc = to_utc(due)
    if kind in ('event', 'project'):
        reg = to_utc(_local(data.get('reg_deadline')))
    else:
        reg = None
    if reg and (not _REG_WORDS.search(raw_text) or (kind == "event" and due_utc and reg > due_utc)):
        reg = None
    if isinstance(data.get('text'), str) and data['text'].strip():
        title = data.get('text')
    else:
        title = " ".join(raw_text.split())
    if kind == 'event' and data.get('location'):
        location = data.get('location')
    else:
        location = None
    minutes = data.get("duration_minutes" if kind == "event" else "effort_minutes")
    if type(minutes) is int and 1 <= minutes <= 1440:
        duration = minutes
    else:
        duration = None
    return ParsedTask(
        title=title.strip()[:500], subject=normalize_subject(data.get("subject")),
        due_at=due_utc, kind=kind, location=str(location)[:300] if location else None,
        reg_deadline=reg, is_task=bool(data.get("is_task", True)), duration_min=duration,
    )


class GigaChatParser:
    """Разбор задания только через GigaChat. Не ответил или ответил не JSON — ParserUnavailable."""

    async def parse(self, text: str, now: datetime, tz: str = DEFAULT_TZ) -> ParsedTask:
        if not gigachat.credentials():
            raise ParserUnavailable("не задан GIGACHAT_CREDENTIALS")
        zone = ZoneInfo(tz)
        local_now = now.astimezone(zone).replace(tzinfo=None)
        try:
            raw = await gigachat.complete(build_prompt(local_now), text, max_tokens=1200)
            raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            m = re.search(r"[\[{].*[\]}]", raw, re.S)
            data = json.loads(m.group(0)) if m else None
        except Exception as e:
            log.warning("GigaChat недоступен: %s", type(e).__name__)
            raise ParserUnavailable(type(e).__name__) from e
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            data = data["items"]
        raws = [d for d in (data if isinstance(data, list) else [data]) if isinstance(d, dict)][:10]
        if not raws:
            raise ParserUnavailable("GigaChat ответил без JSON")
        items = [_item(d, text, local_now, zone) for d in raws]
        real = [i for i in items if i.is_task]
        first = real[0] if real else items[0]
        first.more = real[1:]
        return first
