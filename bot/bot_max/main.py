import asyncio
import json
import logging
import os
import re
from datetime import datetime, time, timedelta, timezone
from secrets import token_hex
from types import SimpleNamespace
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from maxapi import Bot, Dispatcher, F
from maxapi.filters.command import CommandStart
from maxapi.filters.middleware import BaseMiddleware
from maxapi.enums.message_link_type import MessageLinkType
from maxapi.enums.chat_type import ChatType
from maxapi.enums.attachment import AttachmentType
from maxapi.enums.parse_mode import ParseMode
from maxapi.types import BotAdded, BotStarted, BotStopped, CallbackButton, ClipboardButton, LinkButton, MessageCallback, MessageCreated, MessageButton, OpenAppButton
from maxapi.types.input_media import InputMediaBuffer
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder


from core import files as filestore
from core import speech
from core.dates import is_no_deadline, parse_when
from core.format import (FILTERS, filter_tasks, format_due, full_when, h, render_task_list, task_block, task_line,
                         when_label)
from core.gigachat_parser import GigaChatParser
from core.import_tasks import MAX_IMPORT_BYTES, document_text, is_http_link, looks_like_list, parse_list
from core import gigachat
from core.parser import DEFAULT_TZ, ParserUnavailable, TaskParser, find_subject
from core.reminders import REMINDER_HEAD, tick
from core.repo import Repo, remind_ok
from core.schedule import evening_remind, shift_out_of_quiet
from core.task_updates import match_change


load_dotenv()
logging.basicConfig(level=logging.INFO)
bot = Bot(auto_requests=False, format=ParseMode.HTML)
dp = Dispatcher()


#====================================[Переменные]====================================

HELLO = "<b>Привет! Я Учебрик</b> - сервис умных напоминаний"
MENU = "Выберите действие:"
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")
ALICE_SECRET = os.getenv("ALICE_SECRET", "")
DUE_STATE = "due:"
SUBJECT_STATE = "subject:"
MATERIAL_STATE = "materials:"
IMPORT_STATE = "import"
OLYMPIAD_IMPORT_STATE = "import_olympiads"
CHANGE_STATE = "change:"
TASK_KINDS = {"homework": "📚 Домашка", "event": "🏆 Событие", "todo": "📌 Дело", "project": "⌛ Период"}


REPEAT_PRESETS = (30, 60, 120)
REPEAT_TIMES = {1: "Один раз", 2: "2 раза", 3: "3 раза", 5: "5 раз"}
WORK_PRESETS = {"classic": "Как обычно", "school": "После школы", "evening": "Вечером"}
REMIND_MODES = {"all": "По всем заданиям", "selected": "Только по выбранным", "none": "Ни по каким"}
QUIET_STATE = "quiet_input"
MORNING_STATE = "morning_input"
ON = "✅ "


repo: Repo
parser: TaskParser


class DumpUpdates(BaseMiddleware):

    async def __call__(self, handler, event, data):
        logging.info("UPDATE %s", event.model_dump_json(indent=2, exclude_none=True))
        return await handler(event, data)

if os.getenv("DEBUG_UPDATES") == "1":
    dp.register_outer_middleware(DumpUpdates())


GIGACHAT_DOWN = "GigaChat сейчас не ответил, и я не смог разобрать задание. Пришли его ещё раз через минуту 🙏"


async def parse_or_sorry(answer, text, tz):
    """Задания разбирает только GigaChat. Не ответил — говорим об этом тем же answer
    (Reply заменит «⏳ Записываю…») и возвращаем None, ничего не записывая."""
    try:
        return await parser.parse(text, datetime.now(timezone.utc), tz)
    except ParserUnavailable as e:
        logging.warning("Задание не разобрано: %s", e)
        await answer(GIGACHAT_DOWN, attachments=[menu()])
        return None


#====================================[Кнопки]====================================

def menu_row():
    me = getattr(bot, "me", None)
    if me and me.username:
        map_btn = OpenAppButton(text="🗺️ Карта", web_app=me.username)
    else:
        map_btn = CallbackButton(text="🗺️ Карта", payload="map")
    return [CallbackButton(text="⚙️ Настройки", payload="settings"), map_btn]


def menu():
    kb = InlineKeyboardBuilder()
    kb.row(*menu_row())
    return kb.as_markup()


def back_to_list():
    return CallbackButton(text="↩ К заданиям", payload="list")


def after_task(*task_ids: int, titles: list[str] | None = None, remind_mode: str = "all"):
    kb = InlineKeyboardBuilder()
    if len(task_ids) == 1:
        row = [CallbackButton(text="✏️ Изменить", payload=f"card:{task_ids[0]}")]
        if remind_mode == "selected":
            row.append(CallbackButton(text="🔔 Напоминать", payload=f"pick:{task_ids[0]}:1"))
        kb.row(*row)
    else:
        for task_id, title in zip(task_ids[:5], titles or []):
            kb.row(CallbackButton(text=f"✏️ {title[:36]}", payload=f"card:{task_id}"))
    kb.row(
        CallbackButton(text="❌ Не записывать", payload="unwrite:" + ",".join(map(str, task_ids))),
        back_to_list(),
    )
    return kb.as_markup()


def draft_keyboard(task_id: int):
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="✏️ Изменить", payload=f"card:{task_id}"))
    kb.row(
        CallbackButton(text="❌ Не записывать", payload=f"cancel:{task_id}"),
        CallbackButton(text="✅ Записать", payload=f"confirm:{task_id}"),
    )
    return kb.as_markup()


def reminder_keyboard(task_id: int, checkin: bool = False):
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="Через час", payload=f"snooze:{task_id}:60"),
        CallbackButton(text="Вечером", payload=f"snooze:{task_id}:evening"),
        CallbackButton(text="Завтра", payload=f"snooze:{task_id}:1440"),
    )
    if checkin:
        second = CallbackButton(text='Ещё 20 минут', payload=f'progress:{task_id}:more')
    else:
        second = CallbackButton(text='▶️ Начинаю', payload=f'progress:{task_id}:start')
    kb.row(CallbackButton(text="✏️", payload=f"card:{task_id}"), second,
           CallbackButton(text="✅ Сделано", payload=f"done:{task_id}"))
    return kb.as_markup()


def group_reminder_keyboard(tasks):
    ids = ",".join(str(t["id"]) for t in tasks)
    kb = InlineKeyboardBuilder()
    for t in tasks:
        if t["status"] == "active":
            kb.row(CallbackButton(text=f"✅ {t['title'][:36]}", payload=f"rd:{t['id']}:{ids}"))
    if any(t["status"] == "active" for t in tasks):
        kb.row(CallbackButton(text="Через час", payload=f"snz:60:{ids}"),
               CallbackButton(text="Вечером", payload=f"snz:evening:{ids}"))
    kb.row(back_to_list())
    return kb.as_markup()


def group_reminder_text(tasks, tz: str) -> str:
    now = datetime.now(timezone.utc)
    blocks = []
    for t in tasks:
        done = t["status"] != "active"
        blocks.append(task_block(when_label(t["due_at"], tz, now, t["kind"]), t["subject"], t["title"][:200],
                                 head="✅ " if done else "", done=done))
    return REMINDER_HEAD + "\n" + "\n".join(blocks)


class MaxSender:
    async def send_reminder(self, user_id: int, text: str, task_id: int):
        return sent_mid(await bot.send_message(user_id=user_id, text=text,
                                               attachments=[reminder_keyboard(task_id, checkin=text.startswith("✍️"))]))

    async def send_reminders(self, user_id: int, text: str, task_ids: list[int]):
        tasks = await repo.tasks_by_ids(user_id, task_ids)
        return sent_mid(await bot.send_message(user_id=user_id, text=text, attachments=[group_reminder_keyboard(tasks)]))

    async def delete_message(self, mid: str):
        await bot.delete_message(mid)

    async def send_morning(self, user_id: int, text: str):
        kb = InlineKeyboardBuilder()
        kb.row(*menu_row())
        kb.row(back_to_list())
        await bot.send_message(user_id=user_id, text=text, attachments=[kb.as_markup()])

    async def send_olympiad(self, user_id: int, text: str, olympiad_id: int, registration: bool):
        kb = InlineKeyboardBuilder()
        if registration:
            kb.row(CallbackButton(text="✅ Зарегистрировался", payload=f"oly_register:{olympiad_id}"))
        kb.row(CallbackButton(text="🔕 Не напоминать", payload=f"oly_mute:{olympiad_id}"))
        kb.row(*menu_row())
        await bot.send_message(user_id=user_id, text=text, attachments=[kb.as_markup()])


@dp.message_callback(F.callback.payload.regexp(r"^oly_(register|mute):[0-9]{1,18}$"))
async def on_olympiad_notice(event: MessageCallback):
    action, raw = event.callback.payload.split(":")
    registered = action == "oly_register"
    updated = await repo.update_olympiad_notice_settings(event.callback.user.user_id, int(raw), registered=registered)
    if updated:
        if registered:
            text = '✅ Регистрация отмечена'
        else:
            text = '🔕 Напоминания отключены'
        await event.answer(new_text=text, attachments=[menu()])
    else:
        await event.answer(notification="Олимпиада недоступна")


#====================================[События]====================================

@dp.bot_stopped()
async def on_bot_stopped(event: BotStopped):
    await repo.set_bot_active(event.user.user_id, False)

@dp.bot_started()
async def on_bot_started(event: BotStarted):
    tz = await repo.ensure_user(event.user.user_id, event.user.first_name)
    if event.payload and LIST_LINK.match(event.payload):
        async def answer(text, attachments=None):
            return await bot.send_message(chat_id=event.chat_id, text=text, attachments=attachments)
        await apply_list_link(event.user.user_id, tz, event.payload, answer)
        return
    await bot.send_message(chat_id=event.chat_id, text=HELLO)
    await bot.send_message(chat_id=event.chat_id, text="<b>Я помогу тебе:</b> \n ◦ Записать домашнее задание, дело или событие\n ◦ Контролировать сроки выполнения задач\n ◦ Держать все файлы, ссылки и заметки в одном месте\n ◦ Контролировать твои олимпиады")
    await bot.send_message(chat_id=event.chat_id, text="Напиши первое задание или нажми на кнопки ниже:", attachments=[menu()])


GROUP_HELLO = ("👋 Привет! Я Учебрик. Буду замечать в чате задания и сроки и присылать их в личку каждому, "
               "кто мне писал. В чат ничего писать не буду.\n\n"
               "<blockquote>Чтобы я видел все сообщения, сделайте меня администратором чата. "
               "Чтобы задания приходили вам, один раз напишите мне /start.</blockquote>")

def in_group(event) -> bool:
    r = getattr(getattr(event, "message", None), "recipient", None)
    return getattr(r, "chat_type", None) == ChatType.CHAT


@dp.bot_added()
async def on_bot_added(event: BotAdded):
    if not getattr(event, "is_channel", False):
        await bot.send_message(chat_id=event.chat_id, text=GROUP_HELLO)


def message_content(msg) -> tuple[str, list]:
    if getattr(msg, 'link', None):
        linked = msg.link.message
    else:
        linked = None
    texts, atts = [], []
    for part in (linked, msg.body):
        if part is None:
            continue
        if getattr(part, "text", None) and part.text.strip():
            texts.append(part.text.strip())
        atts += list(getattr(part, "attachments", None) or [])
    files = filestore.incoming_attachments(atts)
    texts += [filestore.file_title(f.name) for f in files if f.kind == "doc"]
    return "\n".join(texts), files


def message_caption(msg) -> str:
    parts = [msg.link.message if getattr(msg, "link", None) else None, msg.body]
    return "\n".join(p.text.strip() for p in parts if p is not None and getattr(p, "text", None) and p.text.strip())


@dp.message_created(F.message.recipient.chat_type == ChatType.CHAT)
async def on_group_message(event: MessageCreated):
    msg = event.message
    chat_id = msg.recipient.chat_id
    if msg.sender and not getattr(msg.sender, "is_bot", False):
        await repo.remember_member(chat_id, msg.sender.user_id)
    text, files = message_content(msg)
    if not text or text.startswith("/") or getattr(msg.sender, "is_bot", False) or len(text) < 6:
        return
    try:
        parsed = await parser.parse(text, datetime.now(timezone.utc), DEFAULT_TZ)
    except ParserUnavailable:
        return
    items = [p for p in [parsed, *parsed.more] if p.is_task and (p.due_at or p.subject)]
    fresh = []
    for i, p in enumerate(items[:5]):
        if await repo.add_candidate(chat_id, p, [f.to_dict() for f in files] if i == 0 else []) is not None:
            fresh.append(p)
    if not fresh:
        return
    title = ""
    try:
        title = (await bot.get_chat_by_id(chat_id)).title or ""
    except Exception as e:
        logging.info("Не узнал название чата %s: %s", chat_id, e)
    if title:
        head = f'📥 Из чата «{h(title)}»'
    else:
        head = '📥 Из группового чата'
    for user in await repo.bot_users(await group_members(chat_id)):
        async def answer(text, attachments=None, _uid=user["id"]):
            return await bot.send_message(user_id=_uid, text=text, attachments=attachments)
        try:
            await post_draft_items(answer, user["id"], fresh, user["tz"], head, source="group", files=files, raw_head=True)
        except Exception as e:
            logging.info("Черновик из чата не отправлен %s: %s", user["id"], e)


async def group_members(chat_id: int) -> list[int]:
    ids = set(await repo.known_members(chat_id))
    marker = None
    try:
        for _ in range(10):
            page = await bot.get_chat_members(chat_id=chat_id, marker=marker, count=100)
            ids.update(m.user_id for m in page.members if not m.is_bot)
            marker = page.marker
            if not marker:
                break
    except Exception as e:
        logging.info("Не получил участников чата %s: %s", chat_id, e)
    return list(ids)


@dp.message_callback(F.callback.payload.regexp(r"^grab:[0-9]{1,18}$"))
async def on_grab(event: MessageCallback):
    user = event.callback.user
    raw = event.callback.payload.split(":", 1)[1]
    c = await repo.get_candidate(int(raw))
    if c is None or not in_group(event) or event.message.recipient.chat_id != c["chat_id"]:
        await event.answer(notification="Это задание уже недоступно")
        return
    tz = await repo.ensure_user(user.user_id, user.first_name)
    task_id = await repo.grab_candidate(user.user_id, c["id"], c["chat_id"])
    if task_id is None:
        await event.answer(notification="Задание уже записано")
        return
    if isinstance(c['files'], list):
        files = c['files']
    else:
        files = json.loads(c['files'] or '[]')
    saved = await save_files(user.user_id, task_id, [filestore.Incoming(**f) for f in files])
    if saved:
        clip = f'\n📎 Файлов прикреплено: {saved}'
    else:
        clip = ''
    try:
        mode = (await repo.get_prefs(user.user_id)).remind_mode
        await bot.send_message(user_id=user.user_id, attachments=[after_task(task_id, remind_mode=mode)],
                               text="📥 <b>Записал из чата</b>\n"
                                    + task_block(full_when(c["due_at"], tz, c["kind"]), c["subject"], c["title"]) + clip)
        await event.answer(notification="Записал — подробности в личке ✅")
    except Exception as e:
        logging.info("Не написать в личку %s: %s", user.user_id, e)
        await event.answer(notification="Записал ✅ Чтобы приходили напоминания, напиши мне /start в личке")


async def save_files(user_id: int, task_id: int, items) -> int:
    saved = 0
    for item in items:
        try:
            stored, size, mime = await filestore.download(item.url)
        except Exception as e:
            logging.warning("Не скачалось вложение %s: %s", item.name, e)
            continue
        if await save_attachment(user_id, task_id, item, stored, size, mime):
            saved += 1
    return saved


async def save_loose(user_id, item, stored, size, mime):
    saved = None
    try:
        saved = await repo.add_loose_attachment(user_id, item.kind, item.name, mime, size, stored)
        return saved
    finally:
        if saved is None:
            (filestore.FILES_DIR / stored).unlink(missing_ok=True)


async def save_attachment(user_id, task_id, item, stored, size, mime):
    saved = False
    try:
        saved = await repo.add_attachment(user_id, task_id, item.kind, item.name, mime, size, stored) is not None
        return saved
    finally:
        if not saved:
            (filestore.FILES_DIR / stored).unlink(missing_ok=True)


@dp.message_created(CommandStart())
async def on_start(event: MessageCreated):
    sender = event.message.sender
    tz = await repo.ensure_user(sender.user_id, sender.first_name)
    arg = (event.message.body.text or "").partition(" ")[2].strip()
    if LIST_LINK.match(arg):
        await apply_list_link(sender.user_id, tz, arg, event.message.answer)
        try:
            await bot.delete_message(event.message.body.mid)
        except Exception as e:
            logging.info("Не удалось удалить /start: %s", e)
        return
    await event.message.answer(HELLO)
    await post_list(sender.user_id, tz, event.message.answer)


def every_text(minutes: int) -> str:
    if minutes < 60:
        return f'{minutes} мин'
    return f'{minutes // 60} ч'


def repeat_text(prefs) -> str:
    if prefs.repeat_max <= 1:
        return "один раз, без повторов"
    return f"{REPEAT_TIMES.get(prefs.repeat_max, f'{prefs.repeat_max} раз')}, раз в {every_text(prefs.repeat_min)}"


#====================================[Настройки]====================================

def settings_view(prefs):
    off = prefs.quiet_from == prefs.quiet_to
    if off:
        quiet = 'выключены'
    else:
        quiet = f'{prefs.quiet_from:%H:%M}–{prefs.quiet_to:%H:%M}'
    if prefs.morning_at:
        morning = f'{prefs.morning_at:%H:%M}'
    else:
        morning = 'выключен'
    lines = ["⚙️ <b>Настройки</b>\n", f"🔔 Напоминания: <b>{REMIND_MODES[prefs.remind_mode].lower()}</b>"]
    if prefs.remind_mode != "none":
        lines.append(f"🔁 Повтор: <b>{repeat_text(prefs)}</b>")
        lines.append(f"📚 Планирование: <b>{WORK_PRESETS[prefs.work_schedule].lower()}</b>")
    lines += [f"🌙 Тихие часы: <b>{quiet}</b>", f"☀️ Утренний план: <b>{morning}</b>"]
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="🔔 Напоминания", payload="set:remind"))
    if prefs.remind_mode != "none":
        kb.row(CallbackButton(text="🔁 Повтор", payload="set:repeat"),
               CallbackButton(text="📚 Планирование", payload="set:work"))
    kb.row(CallbackButton(text=(ON if off else "") + "Без тихих часов", payload="quiet:off"),
           CallbackButton(text="✏️ 🌙 Задать" if off else f"✏️ 🌙 {quiet}", payload="quiet:edit"))
    kb.row(CallbackButton(text=("" if prefs.morning_at else ON) + "Без плана", payload="morning:off"),
           CallbackButton(text=f"✏️ ☀️ {morning}" if prefs.morning_at else "✏️ ☀️ Задать", payload="morning:edit"))
    kb.row(CallbackButton(text="📅 Календарь", payload="ics"), CallbackButton(text="💻 Карта в браузере", payload="map"))
    kb.row(CallbackButton(text="Выйти из браузеров", payload="browser_logout:ask"))
    if ALICE_SECRET:
        kb.row(CallbackButton(text="Отвязать Алису", payload="alice:unlink"),
               CallbackButton(text="🎙 Привязать Алису", payload="alice:link"))
    kb.row(back_to_list())
    return "\n".join(lines), kb.as_markup()


def settings_page(prefs, page: str):
    kb = InlineKeyboardBuilder()
    mark = lambda on, label: ON + label if on else label  # noqa: E731
    if page == "remind":
        text = ("🔔 <b>По каким заданиям напоминать</b>\n\n"
                "<b>По всем</b>: напоминаю о каждом задании. Отдельные можно выключить кнопкой 🔕 в карточке.\n"
                "<b>Только по выбранным</b>: напоминаю только там, где в карточке включён 🔔.\n"
                "<b>Ни по каким</b>: ничего не присылаю, список дел смотришь сам.")
        for key, label in REMIND_MODES.items():
            kb.row(CallbackButton(text=mark(prefs.remind_mode == key, label), payload=f"rmode:{key}"))
    elif page == "repeat":
        text = ("🔁 <b>Повтор напоминаний</b>\n\n"
                f"Сейчас: <b>{repeat_text(prefs)}</b>. Повтор приходит, пока не нажмёшь «Сделано» или «Начинаю».")
        kb.row(*[CallbackButton(text=mark(prefs.repeat_max == n, label), payload=f"rmax:{n}")
                 for n, label in list(REPEAT_TIMES.items())[:2]])
        kb.row(*[CallbackButton(text=mark(prefs.repeat_max == n, label), payload=f"rmax:{n}")
                 for n, label in list(REPEAT_TIMES.items())[2:]])
        if prefs.repeat_max > 1:
            kb.row(*[CallbackButton(text=mark(prefs.repeat_min == m, f"раз в {every_text(m)}"), payload=f"repeat:{m}")
                     for m in REPEAT_PRESETS])
    else:
        text = ("📚 <b>Когда напоминать о домашке</b>\n\n"
                "<b>Как обычно</b>: за сутки до срока.\n"
                "<b>После школы</b> и <b>Вечером</b>: подбираю время, когда ты обычно садишься за уроки.")
        for key, label in WORK_PRESETS.items():
            kb.row(CallbackButton(text=mark(prefs.work_schedule == key, label), payload=f"work:{key}"))
    kb.row(CallbackButton(text="↩ Назад", payload="set:main"))
    return text, kb.as_markup()


@dp.message_callback(F.callback.payload == "settings")
async def on_settings(event: MessageCallback):
    user = event.callback.user
    await repo.ensure_user(user.user_id, user.first_name)
    text, kb = settings_view(await repo.get_prefs(user.user_id))
    await event.message.answer(text, attachments=[kb])


@dp.message_callback(F.callback.payload.in_({"set:main", "set:remind", "set:repeat", "set:work"}))
async def on_settings_page(event: MessageCallback):
    user = event.callback.user
    await repo.ensure_user(user.user_id, user.first_name)
    prefs = await repo.get_prefs(user.user_id)
    page = event.callback.payload.partition(":")[2]
    text, kb = settings_view(prefs) if page == "main" else settings_page(prefs, page)
    await event.answer(new_text=text, attachments=[kb], format=ParseMode.HTML)


@dp.message_callback(F.callback.payload.in_({"browser_logout:ask", "browser_logout:confirm"}))
async def on_browser_logout(event: MessageCallback):
    if event.callback.payload.endswith(":ask"):
        kb = InlineKeyboardBuilder()
        kb.row(CallbackButton(text="Выйти из всех браузеров", payload="browser_logout:confirm"),
               CallbackButton(text="Отмена", payload="settings"))
        await event.answer(new_text="Завершить все открытые сессии карты и отключить старые ссылки?",
                           attachments=[kb.as_markup()])
        return
    await repo.revoke_browser_sessions(event.callback.user.user_id)
    await event.answer(new_text="Сессии завершены. Для входа снова открой карту из бота.", attachments=[menu()])


async def alice_link(user, answer, unlink=False):
    if not ALICE_SECRET:
        await answer("Навык Алисы пока не настроен.")
        return
    await repo.ensure_user(user.user_id, user.first_name)
    if unlink:
        await repo.unlink_alice(user.user_id)
        await answer("Алиса отвязана.")
        return
    code = await repo.create_alice_code(user.user_id, ALICE_SECRET)
    await answer(f"В навыке «Учебрик» скажи «привяжи {code}». Код действует 5 минут.")


@dp.message_callback(F.callback.payload.in_({"alice:link", "alice:unlink"}))
async def on_alice_settings(event: MessageCallback):
    await alice_link(event.callback.user, event.message.answer, event.callback.payload == "alice:unlink")


@dp.message_callback(F.callback.payload.startswith(("quiet:", "repeat:", "work:", "morning:", "rmode:", "rmax:")))
async def on_settings_change(event: MessageCallback):
    user = event.callback.user
    await repo.ensure_user(user.user_id, user.first_name)
    kind, _, value = event.callback.payload.partition(":")
    page = "main"
    if value == "edit" and kind in ("quiet", "morning"):
        await repo.set_state(user.user_id, QUIET_STATE if kind == "quiet" else MORNING_STATE)
        await event.message.answer("Напиши тихие часы, например «23-7» или «22:30–6:30»." if kind == "quiet"
                                   else "Напиши, во сколько присылать план на день, например «7:30».")
        return
    if kind == "quiet" and value == "off":
        await repo.set_quiet(user.user_id, time(0, 0), time(0, 0))
    elif kind == "morning" and value == "off":
        await repo.set_morning(user.user_id, None)
    elif kind == "rmode" and value in REMIND_MODES:
        await repo.set_remind_mode(user.user_id, value)
        page = "remind"
    elif kind == "rmax" and value.isdigit() and int(value) in REPEAT_TIMES:
        await repo.set_repeat_max(user.user_id, int(value))
        page = "repeat"
    elif kind == "repeat" and value.isdigit() and int(value) in REPEAT_PRESETS:
        await repo.set_repeat(user.user_id, int(value))
        page = "repeat"
    elif kind == "work" and value in WORK_PRESETS:
        await repo.set_work_schedule(user.user_id, value)
        page = "work"
    else:
        await event.answer(notification="Этот вариант устарел")
        return
    prefs = await repo.get_prefs(user.user_id)
    text, kb = settings_view(prefs) if page == "main" else settings_page(prefs, page)
    await event.answer(notification="Сохранено", new_text=text, attachments=[kb], format=ParseMode.HTML)


CLOCK = re.compile(r"(?<!\d)([01]?\d|2[0-3])(?:[:.]([0-5]\d))?(?!\d)")


def parse_clock(text: str, count: int) -> list[time] | None:
    found = [time(int(hh), int(mm or 0)) for hh, mm in CLOCK.findall(text)]
    if len(found) == count:
        return found
    return None


async def save_clock_setting(answer, user_id: int, state: str, text: str) -> None:
    times = parse_clock(text, 2 if state == QUIET_STATE else 1)
    if times is not None and state == MORNING_STATE and times[0] >= time(12):
        await repo.set_state(user_id, state)
        await answer('Для утреннего плана выбери время до 12:00, например «7:30».')
        return
    if times is None:
        await repo.set_state(user_id, state)
        await answer("Не понял время. Напиши, например, «23-7»." if state == QUIET_STATE
                     else "Не понял время. Напиши, например, «7:30».")
        return
    if state == QUIET_STATE:
        await repo.set_quiet(user_id, *times)
    else:
        await repo.set_morning(user_id, times[0])
    view, kb = settings_view(await repo.get_prefs(user_id))
    await answer("Сохранено ✅\n\n" + view, attachments=[kb])


@dp.message_callback(F.callback.payload == "map")
async def on_map(event: MessageCallback):
    if not PUBLIC_URL:
        await event.answer(notification="Адрес карты ещё не настроен")
        return
    user = event.callback.user
    await repo.ensure_user(user.user_id, user.first_name)
    token = await repo.create_login_token(user.user_id)
    kb = InlineKeyboardBuilder()
    url = f"{PUBLIC_URL}/?t={token}"
    kb.row(ClipboardButton(text="Скопировать ссылку", payload=url), LinkButton(text="🗺️ Открыть карту", url=url))
    kb.row(CallbackButton(text="↩ К заданиям", payload="list"), CallbackButton(text="⚙️ Настройки", payload="settings"))
    note = "Ссылка действует 10 минут и работает один раз. Никому её не отправляйте."
    try:
        await event.message.answer(note, attachments=[kb.as_markup()])
    except Exception as e:
        logging.warning("MAX не принял кнопку-ссылку (%s), отправляю ссылку текстом", e)
        await event.message.answer(f"{note}\n{h(url)}")


def deeplink(payload: str) -> str | None:
    me = getattr(bot, "me", None)
    if me and me.username:
        return f'https://max.ru/{me.username}?start={payload}'
    return None

def list_link():
    if deeplink('x'):
        return deeplink
    return None

def list_keyboard(flt: str = "today"):
    kb = InlineKeyboardBuilder()
    kb.row(*[CallbackButton(text=f"> {name} <" if key == flt else name, payload=f"lf:{key}") for key, name in FILTERS.items()])
    kb.row(CallbackButton(text="🔄 Обновить", payload=f"lr:{flt}"))
    kb.row(*menu_row())
    return kb.as_markup()


async def build_list(user_id: int, tz: str, flt: str):
    now = datetime.now(timezone.utc)
    tasks = filter_tasks(await repo.list_active(user_id), tz, now, flt)
    limit = min(30, len(tasks))
    link = list_link()
    text = render_task_list(tasks, tz, now, limit=limit, link=link, flt=flt)
    while limit > 1 and len(text) > 3900:
        limit -= 1
        text = render_task_list(tasks, tz, now, limit=limit, link=link, flt=flt)
    return text, list_keyboard(flt), [t["id"] for t in tasks[:limit]]


def sent_mid(sent) -> str | None:
    return getattr(getattr(getattr(sent, "message", None), "body", None), "mid", None)


EMPTY_LIST = "Заданий пока нет. Напишите задание одним сообщением, например: алгебра, №24 к пятнице"


async def post_list(user_id: int, tz: str, answer, flt: str = "today") -> bool:
    if not await repo.list_active(user_id):
        await answer(EMPTY_LIST, attachments=[menu()])
        return False
    text, kb, ids = await build_list(user_id, tz, flt)
    sent = await answer(text, attachments=[kb])
    await repo.save_list(user_id, sent_mid(sent), ids, flt)
    return True


@dp.message_callback(F.callback.payload == "list")
async def on_list(event: MessageCallback):
    user = event.callback.user
    tz = await repo.ensure_user(user.user_id, user.first_name)
    await post_list(user.user_id, tz, event.message.answer)


def payload_filter(payload: str) -> str:
    flt = payload.partition(":")[2]
    if flt in FILTERS:
        return flt
    return 'today'


@dp.message_callback(F.callback.payload.startswith("lf:"))
async def on_list_filter(event: MessageCallback):
    user = event.callback.user
    tz = await repo.ensure_user(user.user_id, user.first_name)
    flt = payload_filter(event.callback.payload)
    text, kb, ids = await build_list(user.user_id, tz, flt)
    await event.answer(new_text=text, attachments=[kb], format=ParseMode.HTML)
    await repo.save_list(user.user_id, event.message.body.mid if event.message else None, ids, flt)


@dp.message_callback(F.callback.payload.startswith("lr"))
async def on_list_refresh(event: MessageCallback):
    user = event.callback.user
    tz = await repo.ensure_user(user.user_id, user.first_name)
    await post_list(user.user_id, tz, event.message.answer, payload_filter(event.callback.payload))
    if event.message and event.message.body:
        old = event.message.body.mid
    else:
        old = None
    if old:
        try:
            await bot.delete_message(old)
        except Exception as e:
            logging.info("Не удалось удалить старый список %s: %s", old, e)


LIST_LINK = re.compile(r"^(ld|lu|le)_([0-9]{1,18})$")
TITLE_STATE = "title:"


def task_card(t, tz: str, mode: str = "all"):
    task_id = t["id"]
    draft = t["status"] == "draft"
    if draft:
        head = '📝 <b>Черновик</b>'
    else:
        head = '✏️ <b>Задание</b>'
    lines = [head, f"<blockquote>{task_line(t['subject'], t['title'][:250])}</blockquote>",
             f"Срок: <b>{full_when(t['due_at'], tz, t['kind'])}</b>",
             f"Тип: {TASK_KINDS.get(t['kind'], '🏅 Олимпиада')}"]
    if t["location"]:
        lines.append(f"Место: {h(t['location'][:150])}")
    if t["note"]:
        lines.append(h(t["note"][:250]))
    if t["reg_deadline"]:
        lines.append("✅ Зарегистрирован" if t["registered"] else f"Регистрация до: {format_due(t['reg_deadline'], tz)}")
    if t["duration_min"]:
        lines.append(f"Длительность: {t['duration_min']} мин")
    reminding = remind_ok(mode, t["reminders_muted"], t["remind_on"])
    if t["status"] == "active":
        if mode == "none":
            reminder = "выключены в настройках"
        elif not reminding:
            reminder = "не напоминаю"
        else:
            if t['next_remind_at']:
                reminder = format_due(t['next_remind_at'], tz)
            else:
                reminder = 'назначу в ближайшую минуту'
        lines.append(f"Напоминание: {reminder}")
    kb = InlineKeyboardBuilder()
    if t["status"] == "done":
        lines.append("✅ Выполнено")
    else:
        kb.row(CallbackButton(text="📅 Срок", payload=f"due:{task_id}"),
               CallbackButton(text="💬 Текст", payload=f"rename:{task_id}"),
               CallbackButton(text="📘 Предмет", payload=f"subject:{task_id}"))
        kinds = list(TASK_KINDS)
        if t['kind'] in kinds:
            next_kind = kinds[(kinds.index(t['kind']) + 1) % len(kinds)]
        else:
            next_kind = kinds[0]
        type_row = [CallbackButton(text=f"Тип → {TASK_KINDS[next_kind]}", payload=f"kind:{task_id}:{t['kind']}:{next_kind}")]
        if t["status"] == "active" and mode == "all":
            type_row.append(CallbackButton(text="🔔 Напоминать" if t["reminders_muted"] else "🔕 Не напоминать",
                                           payload=f"mute:{task_id}:{int(not t['reminders_muted'])}"))
        elif t["status"] == "active" and mode == "selected":
            type_row.append(CallbackButton(text="🔕 Не напоминать" if reminding else "🔔 Напоминать",
                                           payload=f"pick:{task_id}:{int(not reminding)}"))
        kb.row(*type_row)
    if draft:
        kb.row(CallbackButton(text="📂 Материалы", payload=f"materials:{task_id}:0"))
    else:
        kb.row(CallbackButton(text="📂 Материалы", payload=f"materials:{task_id}:0"),
               CallbackButton(text="📎 Прикрепить", payload=f"material_add:{task_id}"))
    if t["kind"] == "event" and t["due_at"]:
        query = {"action": "TEMPLATE", "text": t["title"]}
        end = t["due_at"] + timedelta(minutes=t["duration_min"] or 30)
        query["dates"] = "/".join(d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ") for d in (t["due_at"], end))
        if t["location"]:
            query["location"] = t["location"]
        if t["note"]:
            query["details"] = t["note"][:300]
        url = "https://calendar.google.com/calendar/render?" + urlencode(query)
        if len(url) <= 2048:
            kb.row(LinkButton(text="📅 В Google Календарь", url=url))
    if draft:
        kb.row(CallbackButton(text="❌ Не записывать", payload=f"cancel:{task_id}"),
               CallbackButton(text="✅ Записать", payload=f"confirm:{task_id}"))
        return "\n".join(lines), kb.as_markup()
    if t["status"] == "active":
        if t["reg_deadline"] and not t["registered"]:
            kb.row(CallbackButton(text="✅ Зарегистрировался", payload=f"registered:{task_id}"))
        bottom = [CallbackButton(text="🗑 Удалить", payload=f"askdel:{task_id}")]
        if reminding and t["kind"] != "event":
            bottom.append(CallbackButton(text="▶️ Начинаю", payload=f"progress:{task_id}:start"))
        bottom.append(CallbackButton(text="✅ Сделано", payload=f"done:{task_id}"))
        kb.row(*bottom)
    else:
        kb.row(CallbackButton(text="🗑 Удалить", payload=f"askdel:{task_id}"),
               CallbackButton(text="↩️ Вернуть", payload=f"undo:{task_id}"))
    kb.row(back_to_list())
    return "\n".join(lines), kb.as_markup()


async def card_for(user_id: int, task_id: int, tz: str):
    t = await repo.get_task(user_id, task_id)
    if t is None or t["status"] not in ("active", "draft", "done"):
        return None
    return task_card(t, tz, (await repo.get_prefs(user_id)).remind_mode)


async def apply_list_link(user_id: int, tz: str, payload: str, answer) -> None:
    action, raw = LIST_LINK.match(payload).groups()
    task_id = int(raw)
    if action == "le":
        card = await card_for(user_id, task_id, tz)
        if card is None:
            await answer("Это задание уже удалено.", attachments=[menu()])
            return
        await answer(card[0], attachments=[card[1]])
        return
    await (repo.mark_done if action == "ld" else repo.mark_undone)(user_id, task_id)
    mid, ids, flt = await repo.get_list(user_id)
    if mid and task_id in ids:
        tasks = await repo.tasks_by_ids(user_id, ids)
        text = render_task_list(tasks, tz, datetime.now(timezone.utc), link=list_link(), flt=flt)
        try:
            await bot.edit_message(message_id=mid, text=text, attachments=[list_keyboard(flt)], format=ParseMode.HTML)
            return
        except Exception as e:
            logging.warning("Не удалось обновить список %s: %s", mid, e)
    await post_list(user_id, tz, answer, flt)


@dp.message_callback(F.callback.payload.regexp(r"^unwrite:[0-9]{1,18}(,[0-9]{1,18}){0,9}$"))
async def on_unwrite(event: MessageCallback):
    user = event.callback.user
    _, _, raw = event.callback.payload.partition(":")
    rows = [await repo.delete_task(user.user_id, int(i)) for i in raw.split(",")]
    rows = [r for r in rows if r is not None]
    if not rows:
        await event.answer(notification="Это задание уже удалено")
        return
    gone = "\n".join(f"<s>{task_line(r['subject'], r['title'])}</s>" for r in rows)
    await event.answer(new_text=f"❌ Не записал:\n{gone}", attachments=[menu()], format=ParseMode.HTML)


@dp.message_callback(F.callback.payload.regexp(r"^(rename|subject):[0-9]{1,18}$"))
async def on_rename(event: MessageCallback):
    user = event.callback.user
    action, raw = event.callback.payload.split(":")
    task = await repo.get_task(user.user_id, int(raw))
    if task is None or task["status"] not in ("active", "draft"):
        await event.answer(notification="Задание недоступно")
        return
    await repo.set_state(user.user_id, (TITLE_STATE if action == "rename" else SUBJECT_STATE) + raw)
    if action == 'rename':
        prompt = 'Напиши новый текст задания одним сообщением.'
    else:
        prompt = 'Напиши предмет или «без предмета».'
    await event.message.answer(prompt)


@dp.message_callback(F.callback.payload.regexp(r"^kind:[0-9]{1,18}:[a-z]+:[a-z]+$"))
async def on_kind(event: MessageCallback):
    _, raw, old, kind = event.callback.payload.split(":")
    user = event.callback.user
    tz = await repo.ensure_user(user.user_id, user.first_name)
    task = await repo.get_task(user.user_id, int(raw))
    if task is None or task["status"] not in ("active", "draft") or kind not in TASK_KINDS:
        await event.answer(notification="Задание недоступно")
        return
    previous = task["due_at"]
    due = previous
    if due:
        local = due.astimezone(ZoneInfo(tz))
        if kind == "event" and old != "event" and local.time() == time(23, 59):
            due = local.replace(hour=9, minute=0).astimezone(timezone.utc)
        elif old == "event" and kind != "event" and local.time() == time(9):
            due = local.replace(hour=23, minute=59).astimezone(timezone.utc)
    if not await repo.set_kind(user.user_id, int(raw), kind, due, old, previous):
        await event.answer(notification="Карточка устарела. Открой её снова.")
        return
    card = await card_for(user.user_id, int(raw), tz)
    if card:
        await event.answer(new_text=card[0], attachments=[card[1]], format=ParseMode.HTML)


@dp.message_callback(F.callback.payload.regexp(r"^askdel:[0-9]{1,18}$"))
async def on_ask_delete(event: MessageCallback):
    user = event.callback.user
    raw = event.callback.payload.split(":")[1]
    task = await repo.get_task(user.user_id, int(raw))
    if task is None:
        await event.answer(notification="Задание уже удалено")
        return
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="Удалить", payload=f"del:{raw}"),
           CallbackButton(text="Отмена", payload=f"card:{raw}"))
    await event.answer(new_text=f"Удалить задание «{h(task['title'])}»?", attachments=[kb.as_markup()],
                       format=ParseMode.HTML)


@dp.message_callback(F.callback.payload.regexp(r"^(card|undo|mute|pick|registered):[0-9]{1,18}(:[01])?$"))
async def on_card_action(event: MessageCallback):
    action, raw, *value = event.callback.payload.split(":")
    user = event.callback.user
    tz = await repo.ensure_user(user.user_id, user.first_name)
    task_id = int(raw)
    if action == "undo":
        await repo.mark_undone(user.user_id, task_id)
    elif action == "mute" and value:
        await repo.set_reminders_muted(user.user_id, task_id, value[0] == "1")
    elif action == "pick" and value:
        await repo.set_remind_on(user.user_id, task_id, value[0] == "1")
    elif action == "registered":
        await repo.mark_registered(user.user_id, task_id)
    card = await card_for(user.user_id, task_id, tz)
    if card is None:
        await event.answer(notification="Задание не найдено")
        return
    await event.answer(new_text=card[0], attachments=[card[1]], format=ParseMode.HTML)


@dp.message_callback(F.callback.payload.regexp(r"^del:[0-9]{1,18}$"))
async def on_delete(event: MessageCallback):
    user = event.callback.user
    raw = event.callback.payload.split(":", 1)[1]
    row = await repo.delete_task(user.user_id, int(raw))
    if row is None:
        await event.answer(notification="Это задание уже удалено")
        return
    await event.answer(new_text=f"🗑 Удалено: <s>{task_line(row['subject'], row['title'])}</s>", attachments=[menu()],
                       format=ParseMode.HTML)


@dp.message_callback(F.callback.payload.regexp(r"^done:[0-9]{1,18}$"))
async def on_done(event: MessageCallback):
    user = event.callback.user
    tz = await repo.ensure_user(user.user_id, user.first_name)
    task_id = int(event.callback.payload.split(":", 1)[1])
    if not await repo.mark_done(user.user_id, task_id):
        await event.answer(notification="Это задание уже отмечено")
        return
    t = await repo.get_task(user.user_id, task_id)
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="↩️ Вернуть", payload=f"undo:{task_id}"), back_to_list())
    text = "✅ <b>Сделано</b>\n" + task_block(full_when(t["due_at"], tz, t["kind"]), t["subject"], t["title"][:200], done=True)
    await event.answer(notification="Отмечено ✅", new_text=text, attachments=[kb.as_markup()], format=ParseMode.HTML)


@dp.message_callback(F.callback.payload.regexp(r"^rd:[0-9]{1,18}:[0-9]{1,18}(,[0-9]{1,18}){0,9}$"))
async def on_group_done(event: MessageCallback):
    user = event.callback.user
    tz = await repo.ensure_user(user.user_id, user.first_name)
    _, raw, ids = event.callback.payload.split(":")
    await repo.mark_done(user.user_id, int(raw))
    tasks = await repo.tasks_by_ids(user.user_id, [int(i) for i in ids.split(",")])
    if not tasks:
        await event.answer(notification="Задания уже удалены")
        return
    await event.answer(notification="Отмечено ✅", new_text=group_reminder_text(tasks, tz),
                       attachments=[group_reminder_keyboard(tasks)], format=ParseMode.HTML)


def snooze_until(minutes: str, prefs) -> datetime:
    now = datetime.now(timezone.utc)
    if minutes == 'evening':
        return evening_remind(now, prefs)
    return shift_out_of_quiet(now + timedelta(minutes=int(minutes)), prefs)


@dp.message_callback(F.callback.payload.regexp(r"^snooze:[0-9]{1,18}:(60|1440|evening)$"))
async def on_snooze(event: MessageCallback):
    user = event.callback.user
    _, task_id, minutes = event.callback.payload.split(":")
    prefs = await repo.get_prefs(user.user_id)
    now = datetime.now(timezone.utc)
    until = snooze_until(minutes, prefs)
    t = await repo.get_task(user.user_id, int(task_id))
    if t and await repo.snooze(user.user_id, int(task_id), until):
        await repo.learn_response(user.user_id, int(task_id), now, -0.5)
        kb = InlineKeyboardBuilder()
        kb.row(CallbackButton(text="✏️", payload=f"card:{task_id}"), back_to_list(),
               CallbackButton(text="✅ Сделано", payload=f"done:{task_id}"))
        text = (f"⏰ <b>Напомню {when_label(until, prefs.tz, now, 'event')}</b>\n"
                + task_block(full_when(t["due_at"], prefs.tz, t["kind"]), t["subject"], t["title"][:200]))
        await event.answer(notification="Напомню позже", new_text=text, attachments=[kb.as_markup()],
                           format=ParseMode.HTML)
    else:
        await event.answer(notification="Это задание уже не активно")


@dp.message_callback(F.callback.payload.regexp(r"^snz:(60|evening):[0-9]{1,18}(,[0-9]{1,18}){0,9}$"))
async def on_group_snooze(event: MessageCallback):
    user = event.callback.user
    _, minutes, ids = event.callback.payload.split(":")
    prefs = await repo.get_prefs(user.user_id)
    until = snooze_until(minutes, prefs)
    tasks = await repo.tasks_by_ids(user.user_id, [int(i) for i in ids.split(",")])
    for t in tasks:
        if t["status"] == "active":
            await repo.snooze(user.user_id, t["id"], until)
    now = datetime.now(timezone.utc)
    text = group_reminder_text(tasks, prefs.tz).replace(
        REMINDER_HEAD, f"⏰ <b>Напомню {when_label(until, prefs.tz, now, 'event')}</b>", 1)
    kb = InlineKeyboardBuilder()
    kb.row(back_to_list())
    await event.answer(notification="Напомню позже", new_text=text, attachments=[kb.as_markup()], format=ParseMode.HTML)


@dp.message_callback(F.callback.payload.regexp(r"^progress:[0-9]{1,18}:(start|more)$"))
async def on_progress(event: MessageCallback):
    _, raw, action = event.callback.payload.split(":")
    user_id = event.callback.user.user_id
    task = await repo.get_task(user_id, int(raw))
    if not task or task["status"] != "active" or task["reminders_muted"]:
        await event.answer(notification="Напоминание недоступно")
        return
    if action == 'more':
        minutes = 20
    else:
        minutes = task['duration_min'] or 30
    prefs = await repo.get_prefs(user_id)
    now = datetime.now(timezone.utc)
    at = shift_out_of_quiet(now + timedelta(minutes=minutes), prefs)
    if action == "start":
        await repo.learn_response(user_id, task["id"], now, 1.0)
    if await repo.snooze(user_id, task["id"], at, checkin=True):
        await event.answer(notification=f"Спрошу об успехах: {format_due(at, prefs.tz)}")
    else:
        await event.answer(notification="Напоминание недоступно")


#====================================[Сообщения и файлы]====================================

@dp.message_created(F.message.link.type == MessageLinkType.FORWARD)
async def on_forward(event: MessageCreated):
    sender = event.message.sender
    tz = await repo.ensure_user(sender.user_id, sender.first_name)
    text, files = message_content(event.message)
    if files and not message_caption(event.message):
        await put_files_on_map(event.message.answer, sender.user_id, files)
        return
    if not text:
        linked = event.message.link.message
        if await handle_speech(event, [*(linked.attachments or []), *(event.message.body.attachments or [])], tz,
                               source="forward"):
            return
        await event.message.answer("В пересланном сообщении нет текста. Перешлите сообщение с заданием или напишите его сами.",
                                   attachments=[menu()])
        return
    reply = await Reply.start(event.message.answer)
    parsed = await parse_or_sorry(reply, text, tz)
    if parsed is None:
        return
    if parsed.subject or parsed.due_at:
        head = 'Нашёл задание'
    else:
        head = 'Не уверен, что это задание, но могу записать'
    await post_drafts(reply, sender.user_id, parsed, tz, head, source="forward", files=files)


FILE_TO_TASK = re.compile(r"^file2task:([0-9]{1,18}(?:,[0-9]{1,18}){0,9})$")


async def put_files_on_map(answer, user_id, files):
    saved, problems = [], []
    for item in files[:10]:
        try:
            stored, size, mime = await filestore.download(item.url)
        except filestore.FileTooLarge:
            problems.append(f"{h(item.name)}: больше 20 МБ")
            continue
        except Exception as e:
            logging.warning("Не скачалось вложение %s: %s", item.name, e)
            problems.append(f"{h(item.name)}: не скачалось")
            continue
        file_id = await save_loose(user_id, item, stored, size, mime)
        if file_id is None:
            problems.append(f"{h(item.name)}: не сохранился")
        else:
            saved.append((file_id, item))
    if not saved:
        await answer("Не получилось добавить на карту:\n" + "\n".join(problems), attachments=[menu()], format=ParseMode.HTML)
        return
    names = "\n".join(f"• {h(item.name)}" for _, item in saved)
    text = f"📎 <b>Добавил на карту</b>\n{names}"
    if problems:
        text += "\n\nНе добавил:\n" + "\n".join(problems)
    kb = InlineKeyboardBuilder()
    docs = [file_id for file_id, item in saved if item.kind == "doc"]
    if docs:
        kb.row(CallbackButton(text="📝 Распознать как задание", payload="file2task:" + ",".join(map(str, docs))))
    kb.row(CallbackButton(text="📎 Прикрепить к заданию", payload="fileto:" + ",".join(str(file_id) for file_id, _ in saved)))
    kb.row(*menu_row())
    await answer(text, attachments=[kb.as_markup()], format=ParseMode.HTML)


@dp.message_callback(F.callback.payload.regexp(FILE_TO_TASK))
async def on_file_to_new_task(event: MessageCallback):
    user = event.callback.user
    tz = await repo.ensure_user(user.user_id, user.first_name)
    ids = [int(x) for x in FILE_TO_TASK.match(event.callback.payload).group(1).split(",")]
    files = await repo.loose_attachments(user.user_id, ids)
    if not files:
        await event.answer(notification="Файл уже прикреплён к заданию или удалён")
        return
    text = "\n".join(filestore.file_title(f["name"]) for f in files if f["kind"] == "doc") or files[0]["name"]
    parsed = await parse_or_sorry(event.message.answer, text, tz)
    if parsed is None:
        return
    task_ids, blocks = [], []
    for item in [parsed, *parsed.more]:
        task_id = await repo.add_task(user.user_id, item.title, item.subject, item.due_at, source="forward",
                                      kind=item.kind, location=item.location, reg_deadline=item.reg_deadline,
                                      duration_min=item.duration_min)
        task_ids.append(task_id)
        blocks.append(task_block(full_when(item.due_at, tz, item.kind), item.subject, item.title))
    await repo.link_attachments(user.user_id, task_ids[0], ids)
    kb = InlineKeyboardBuilder()
    row = [CallbackButton(text="✏️ Изменить", payload=f"card:{task_ids[0]}")]
    if (await repo.get_prefs(user.user_id)).remind_mode == "selected":
        row.append(CallbackButton(text="🔔 Напоминать", payload=f"pick:{task_ids[0]}:1"))
    kb.row(*row)
    kb.row(back_to_list())
    await event.answer(new_text="✅ <b>Записал, файл на карте соединён с заданием</b>\n" + "\n".join(blocks),
                       attachments=[kb.as_markup()], format=ParseMode.HTML)


async def post_drafts(answer, user_id, parsed, tz, head, *, source="manual", files=()):
    await post_draft_items(answer, user_id, [parsed, *parsed.more], tz, head, source=source, files=files)


async def post_draft_items(answer, user_id, items, tz, head, *, source="manual", files=(), raw_head=False):
    for index, item in enumerate(items):
        task_id = await repo.add_task(user_id, item.title, item.subject, item.due_at, source=source, draft=True,
                                      kind=item.kind, location=item.location, reg_deadline=item.reg_deadline,
                                      duration_min=item.duration_min)
        if index == 0 and files:
            await save_files(user_id, task_id, files)
        await answer(("" if raw_head else "📝 ") + f"<b>{head}</b>\n" + task_block(full_when(item.due_at, tz, item.kind), item.subject, item.title)
                     + "\nЗаписать?", attachments=[draft_keyboard(task_id)])


async def handle_speech(event, attachments, tz, *, source="manual") -> bool:
    media = next((a for a in attachments or () if a.type in (AttachmentType.AUDIO, AttachmentType.VIDEO)), None)
    if media is None:
        return False
    answer = event.message.answer
    transcript = getattr(media, "transcription", None)
    if not transcript and not speech.enabled():
        await answer("Распознавание этой записи недоступно. Пришли задание текстом.", attachments=[menu()])
        return True
    if not transcript:
        path = None
        try:
            payload = media.payload
            url = getattr(payload, "url", None)
            token = getattr(media, "token", None) or getattr(payload, "token", None)
            if media.type == AttachmentType.VIDEO and not url and token:
                video = await event.bot.get_video(token)
                if video.duration and video.duration > speech.MAX_SECONDS:
                    await answer("Пришли запись не длиннее пяти минут.", attachments=[menu()])
                    return True
                if video.urls:
                    url = next((value for name, value in video.urls.model_dump().items()
                                if name.startswith("mp4_") and value), None)
            if not url:
                raise ValueError("Нет ссылки на запись")
            key, _, _ = await filestore.download(url)
            path = filestore.FILES_DIR / key
            transcript = await speech.recognize(path)
        except Exception:
            logging.warning("Не удалось распознать запись")
            await answer("Не удалось распознать запись. Пришли задание текстом или более короткой записью.",
                         attachments=[menu()])
            return True
        finally:
            if path:
                path.unlink(missing_ok=True)
    transcript = transcript.strip()[:2000]
    if not transcript:
        await answer("Не удалось разобрать речь в записи.", attachments=[menu()])
        return True
    await answer(f"Распознал: {h(transcript[:500])}")
    parsed = await parse_or_sorry(answer, transcript, tz)
    if parsed is None:
        return True
    if parsed.is_task:
        head = 'Нашёл задание'
    else:
        head = 'Не уверен, что это задание, но могу записать'
    await post_drafts(answer, event.message.sender.user_id, parsed, tz, head, source=source)
    return True


@dp.message_callback(F.callback.payload.regexp(r"^confirm:[0-9]{1,18}$"))
async def on_confirm(event: MessageCallback):
    user = event.callback.user
    tz = await repo.ensure_user(user.user_id, user.first_name)
    task_id = int(event.callback.payload.split(":", 1)[1])
    if not await repo.confirm_draft(user.user_id, task_id):
        await event.answer(notification="Это задание уже записано или отменено")
        return
    t = await repo.get_task(user.user_id, task_id)
    mode = (await repo.get_prefs(user.user_id)).remind_mode
    await event.answer(new_text="✅ <b>Записал</b>\n" + task_block(full_when(t["due_at"], tz, t["kind"]), t["subject"], t["title"]),
                       attachments=[after_task(task_id, remind_mode=mode)], format=ParseMode.HTML)


@dp.message_callback(F.callback.payload.regexp(r"^cancel:[0-9]{1,18}$"))
async def on_cancel(event: MessageCallback):
    user = event.callback.user
    task_id = int(event.callback.payload.split(":", 1)[1])
    t = await repo.get_task(user.user_id, task_id)
    if t is None or not await repo.cancel_draft(user.user_id, task_id):
        await event.answer(notification="Это задание уже записано или отменено")
        return
    await event.answer(new_text=f"❌ Не записал\n<blockquote><s>{task_line(t['subject'], t['title'])}</s></blockquote>",
                       attachments=[menu()], format=ParseMode.HTML)


@dp.message_callback(F.callback.payload.regexp(r"^due:[0-9]{1,18}$"))
async def on_due(event: MessageCallback):
    user = event.callback.user
    task_id = int(event.callback.payload.split(":", 1)[1])
    if not await repo.get_task(user.user_id, task_id):
        await event.message.answer("Задание не найдено.", attachments=[menu()])
        return
    await repo.set_state(user.user_id, f"{DUE_STATE}{task_id}")
    await event.message.answer("Напишите новый срок: например «к пятнице», «12.11 в 9:00» или «без срока».")


@dp.message_callback(F.callback.payload == "ics")
async def on_ics(event: MessageCallback):
    if not PUBLIC_URL:
        await event.answer(notification="Адрес календаря ещё не настроен")
        return
    user = event.callback.user
    await repo.ensure_user(user.user_id, user.first_name)
    url = f"{PUBLIC_URL}/ics/{await repo.ics_token(user.user_id)}.ics"
    kb = InlineKeyboardBuilder()
    kb.row(ClipboardButton(text="Скопировать ссылку", payload=url))
    kb.row(CallbackButton(text="↩ К заданиям", payload="list"), CallbackButton(text="⚙️ Настройки", payload="settings"))
    await event.message.answer(
        "Подписка на календарь со сроками заданий:\n"
        f"{h(url)}\n\n"
        "<blockquote>Яндекс Календарь: «Добавить» → «Подписаться на календарь» → вставить ссылку</blockquote>\n"
        "<blockquote>Google Календарь (на компьютере): «Другие календари» → «+» → «Добавить по URL»</blockquote>\n"
        "Календари обновляют подписку раз в несколько часов. Ссылка личная, никому её не отправляйте.",
        attachments=[kb.as_markup()],
    )


ATTACH_STATE = "attach:"


def material_mode_keyboard(task_id):
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="Готово", payload=f"material_stop:{task_id}"))
    return kb.as_markup()


@dp.message_callback(F.callback.payload.regexp(r"^material_(add|stop):[0-9]{1,18}$"))
async def on_material_mode(event: MessageCallback):
    action, raw = event.callback.payload.split(":")
    user = event.callback.user
    state = MATERIAL_STATE + raw
    if action == "material_stop":
        await repo.clear_state(user.user_id, state)
        await event.answer(notification="Прикрепление завершено")
        return
    task = await repo.get_task(user.user_id, int(raw))
    if task is None or task["status"] != "active":
        await event.answer(notification="Задание недоступно")
        return
    await repo.set_state(user.user_id, state)
    await event.message.answer("Присылай фото, документы или ссылки. Когда закончишь, нажми «Готово».",
                               attachments=[material_mode_keyboard(int(raw))])


@dp.message_callback(F.callback.payload.regexp(r"^materials:[0-9]{1,18}:[0-9]{1,6}$"))
async def on_materials(event: MessageCallback):
    _, raw, offset = event.callback.payload.split(":")
    user_id = event.callback.user.user_id
    task_id, offset = int(raw), int(offset)
    links, files = await repo.task_materials(user_id, task_id)
    buttons = [LinkButton(text=f"🔗 {row['url'][:40]}", url=row["url"]) for row in links if is_http_link(row["url"])]
    buttons += [CallbackButton(text=f"📎 {row['name'][:40]}", payload=f"material_file:{row['id']}") for row in files]
    kb = InlineKeyboardBuilder()
    page_size = 8
    for btn in buttons[offset:offset + page_size]:
        kb.row(btn)
    if offset:
        kb.row(CallbackButton(text="← Назад", payload=f"materials:{task_id}:{max(0, offset - page_size)}"))
    if offset + page_size < len(buttons):
        kb.row(CallbackButton(text="Дальше →", payload=f"materials:{task_id}:{offset + page_size}"))
    kb.row(CallbackButton(text="К заданию", payload=f"card:{task_id}"))
    await event.message.answer("Материалы задания" if buttons else "Материалов пока нет.",
                               attachments=[kb.as_markup()])


@dp.message_callback(F.callback.payload.regexp(r"^material_file:[0-9]{1,18}$"))
async def on_material_file(event: MessageCallback):
    user = event.callback.user
    file = await repo.get_attachment(user.user_id, int(event.callback.payload.split(":")[1]))
    if file is None:
        await event.answer(notification="Файл недоступен")
        return
    try:
        await send_stored_file(event.message.answer, file)
    except Exception:
        logging.warning("Не удалось отправить материал задания")
        await event.answer(notification="Не удалось отправить файл")


async def send_stored_file(answer, file):
    if not re.fullmatch(r"[0-9a-f]{32}", file["path"]):
        raise ValueError("Файл недоступен")

    def read():
        with (filestore.FILES_DIR / file["path"]).open("rb") as stream:
            return stream.read(filestore.MAX_BYTES + 1)

    data = await asyncio.to_thread(read)
    if not data or len(data) > filestore.MAX_BYTES:
        raise ValueError("Файл недоступен")
    media = InputMediaBuffer(data, filename=file["name"], type="image" if file["kind"] == "photo" else "file")
    return await answer(h(file["name"]), attachments=[media])


async def offer_import(answer, user_id, text, tz, *, olympiads=False):
    try:
        items = await parse_list(text, parser, datetime.now(timezone.utc), tz, olympiads=olympiads)
    except ParserUnavailable:
        await answer(GIGACHAT_DOWN, attachments=[menu()])
        return
    except ValueError as exc:
        await answer(h(str(exc)), attachments=[menu()])
        return
    if not items:
        await answer("В списке не нашёл заданий.", attachments=[menu()])
        return
    token = await repo.save_import(user_id, items)
    text, kb = import_page(token, items, 0, tz)
    await answer(text, attachments=[kb])


def import_page(token, items, offset, tz):
    kb = InlineKeyboardBuilder()
    page_size = 6
    lines = [f"<b>Импорт заданий: {len(items)}</b>"]
    for i, item in enumerate(items[offset:offset + page_size], offset + 1):
        date = (item.get("olympiad") or {}).get("end_at") or item["due_at"]
        if date:
            due = datetime.fromisoformat(date)
        else:
            due = None
        if 'olympiad' in item:
            mark = '🏅 '
        else:
            mark = ''
        lines.append(f"<b>{i}. {format_due(due, tz)}</b>\n<blockquote>{mark}{task_line(item['subject'], item['title'][:140])}</blockquote>")
    navigation = []
    if offset:
        navigation.append(CallbackButton(text="← Назад", payload=f"bulk_view:{token}:{max(0, offset - page_size)}"))
    if offset + page_size < len(items):
        navigation.append(CallbackButton(text="Дальше →", payload=f"bulk_view:{token}:{offset + page_size}"))
    if navigation:
        kb.row(*navigation)
    kb.row(CallbackButton(text="✅ Добавить все", payload=f"bulk_add:{token}"),
           CallbackButton(text="Отмена", payload=f"bulk_cancel:{token}"))
    return "\n".join(lines), kb.as_markup()


@dp.message_callback(F.callback.payload.regexp(r"^bulk_(view|add|cancel):[0-9a-f]{32}(:[0-9]{1,2})?$"))
async def on_import_action(event: MessageCallback):
    action, token, *page = event.callback.payload.split(":")
    user = event.callback.user
    if action == "bulk_add":
        result = await repo.confirm_import(user.user_id, token, datetime.now(timezone.utc))
        if result is not None:
            await event.answer(new_text=f"Записано: {result[0]}. Уже добавлено или прошло: {result[1]}.",
                               attachments=[menu()])
            return
    elif action == "bulk_cancel":
        if await repo.cancel_import(user.user_id, token):
            await event.answer(new_text="Импорт отменён.", attachments=[menu()])
            return
    else:
        items = await repo.get_import(user.user_id, token)
        if items:
            tz = await repo.ensure_user(user.user_id, user.first_name)
            offset = min(int(page[0]) if page else 0, ((len(items) - 1) // 6) * 6)
            text, kb = import_page(token, items, offset, tz)
            await event.answer(new_text=text, attachments=[kb], format=ParseMode.HTML)
            return
    await event.answer(notification="Список уже обработан или устарел")


@dp.message_created(F.message.body.attachments)
async def on_attachments(event: MessageCreated):
    sender = event.message.sender
    tz = await repo.ensure_user(sender.user_id, sender.first_name)
    state = await repo.get_state(sender.user_id)
    items = filestore.incoming_attachments(event.message.body.attachments)
    if state in (IMPORT_STATE, OLYMPIAD_IMPORT_STATE):
        doc = next((item for item in items if item.kind == "doc" and item.name.lower().endswith((".txt", ".docx"))), None)
        if doc is None:
            await event.message.answer("Для импорта нужен файл TXT или DOCX, либо список текстом.")
            return
        path = None
        try:
            if doc.size and doc.size > MAX_IMPORT_BYTES:
                raise filestore.FileTooLarge()
            key, _, _ = await filestore.download(doc.url, limit=MAX_IMPORT_BYTES)
            path = filestore.FILES_DIR / key
            text = await asyncio.to_thread(lambda: document_text(path.read_bytes(), doc.name))
        except filestore.FileTooLarge:
            await event.message.answer("Для импорта нужен файл до 2 МБ.")
            return
        except Exception:
            await event.message.answer("Не удалось прочитать файл для импорта.")
            return
        finally:
            if path:
                path.unlink(missing_ok=True)
        await repo.clear_state(sender.user_id, state)
        await offer_import(event.message.answer, sender.user_id, text, tz, olympiads=state == OLYMPIAD_IMPORT_STATE)
        return
    if not items:
        if await handle_speech(event, event.message.body.attachments, tz):
            return
        await event.message.answer("Такое я пока не сохраняю. Пришлите фото или файл, или напишите задание текстом.",
                                   attachments=[menu()])
        return
    if state and state.startswith(MATERIAL_STATE):
        task_id = int(state[len(MATERIAL_STATE):])
        task = await repo.get_task(sender.user_id, task_id)
        if task is None or task["status"] != "active":
            await repo.clear_state(sender.user_id, state)
            await event.message.answer("Задание недоступно.", attachments=[menu()])
            return
        await attach_files(event.message.answer, sender.user_id, task_id, items, material_mode_keyboard(task_id))
        return
    await put_on_map(event.message.answer, sender.user_id, items)


async def put_on_map(answer, user_id, items):
    ids, problems = [], []
    for item in items[:10]:
        try:
            stored, size, mime = await filestore.download(item.url)
        except filestore.FileTooLarge:
            problems.append(f"{h(item.name)}: больше 20 МБ")
            continue
        except Exception as e:
            logging.warning("Не скачалось вложение %s: %s", item.name, e)
            problems.append(f"{h(item.name)}: не скачалось")
            continue
        ids.append(await repo.add_loose_attachment(user_id, item.kind, item.name, mime, size, stored))
    if not ids:
        await answer("Ничего не сохранил.\n" + "\n".join(problems), attachments=[menu()])
        return
    if all((i.kind == 'photo' for i in items)):
        what = 'Фото'
    else:
        what = 'Файл'
    if len(ids) == 1:
        text = f'🗺 {what} на карте'
    else:
        text = f'🗺 На карте: {len(ids)} шт.'
    if problems:
        text += "\n" + "\n".join(problems)
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="📎 Прикрепить к заданию", payload="fileto:" + ",".join(map(str, ids))))
    kb.row(*menu_row())
    await answer(text, attachments=[kb.as_markup()])


FILE_IDS = r"[0-9]{1,18}(,[0-9]{1,18}){0,9}"


@dp.message_callback(F.callback.payload.regexp(rf"^fileto:{FILE_IDS}$"))
async def on_file_to_task(event: MessageCallback):
    user = event.callback.user
    ids = event.callback.payload.split(":", 1)[1]
    tasks = (await repo.list_active(user.user_id))[:8]
    if not tasks:
        await event.answer(notification="Заданий пока нет — файл останется на карте")
        return
    kb = InlineKeyboardBuilder()
    for t in tasks:
        if t['subject']:
            title = f"{t['subject']}: {t['title']}"
        else:
            title = t['title']
        kb.row(CallbackButton(text=f"📎 {title[:40]}", payload=f"filelink:{t['id']}:{ids}"))
    kb.row(*menu_row())
    await event.answer(new_text="К какому заданию прикрепить?", attachments=[kb.as_markup()], format=ParseMode.HTML)


@dp.message_callback(F.callback.payload.regexp(rf"^filelink:[0-9]{{1,18}}:{FILE_IDS}$"))
async def on_file_link(event: MessageCallback):
    user = event.callback.user
    _, task_id, ids = event.callback.payload.split(":")
    added = await repo.link_attachments(user.user_id, int(task_id), [int(i) for i in ids.split(",")])
    t = await repo.get_task(user.user_id, int(task_id))
    if not added or t is None:
        await event.answer(notification="Файл или задание уже недоступны")
        return
    kb = InlineKeyboardBuilder()
    kb.row(*menu_row())
    await event.answer(new_text=f"📎 Прикрепил к заданию\n<blockquote>{task_line(t['subject'], t['title'])}</blockquote>",
                       attachments=[kb.as_markup()], format=ParseMode.HTML)


@dp.message_callback(F.callback.payload.regexp(r"^attach:[0-9]{1,18}$"))
async def on_attach(event: MessageCallback):
    user = event.callback.user
    task_id = int(event.callback.payload.split(":", 1)[1])
    state = await repo.pop_state(user.user_id, only_prefix=ATTACH_STATE)
    if not state or not state.startswith(ATTACH_STATE):
        await event.message.answer("Не нашёл файлы. Пришлите их ещё раз.", attachments=[menu()])
        return
    items = [filestore.Incoming(**d) for d in json.loads(state[len(ATTACH_STATE):])]
    await attach_files(event.message.answer, user.user_id, task_id, items, menu())


async def attach_files(answer, user_id, task_id, items, keyboard):
    saved, problems = 0, []
    for item in items:
        try:
            stored, size, mime = await filestore.download(item.url)
        except filestore.FileTooLarge:
            problems.append(f"{h(item.name)}: больше 20 МБ")
            continue
        except Exception as e:
            logging.warning("Не скачалось вложение %s: %s", item.name, e)
            problems.append(f"{h(item.name)}: не скачалось")
            continue
        if await save_attachment(user_id, task_id, item, stored, size, mime):
            saved += 1
        else:
            problems.append(f"{h(item.name)}: задание не найдено")
    if saved:
        text = f'Прикрепил: {saved}. Файлы видно в «Карте документов».'
    else:
        text = 'Ничего не прикрепил.'
    if problems:
        text += "\n" + "\n".join(problems)
    await answer(text, attachments=[keyboard])


async def change_due(event: MessageCreated, task_id: int, tz: str):
    text = event.message.body.text
    user_id = event.message.sender.user_id
    if is_no_deadline(text):
        due = None
    else:
        task = await repo.get_task(user_id, task_id)
        if not task or task["status"] not in ("active", "draft"):
            await event.message.answer("Это задание уже не активно.", attachments=[menu()])
            return
        zone = ZoneInfo(tz)
        local_now = datetime.now(zone).replace(tzinfo=None)
        if task['kind'] == 'event':
            default = time(9)
        else:
            default = time(23, 59)
        local_due = parse_when(text, local_now, default_time=default)
        if local_due:
            due = local_due.replace(tzinfo=zone).astimezone(timezone.utc)
        else:
            due = None
        if due is None:
            await repo.set_state(user_id, f"{DUE_STATE}{task_id}")
            await event.message.answer("Не понял срок. Напишите, например, «завтра», «к пятнице в 18:00» или «15.11».")
            return
    if await repo.set_due(user_id, task_id, due):
        await answer_card(event.message.answer, user_id, task_id, tz, "Новый срок сохранён ✅")
    else:
        await event.message.answer("Это задание уже не активно.", attachments=[menu()])


async def answer_card(answer, user_id: int, task_id: int, tz: str, note: str):
    card = await card_for(user_id, task_id, tz)
    if card is None:
        await answer("Это задание уже не активно.", attachments=[menu()])
        return
    await answer(f"{note}\n\n{card[0]}", attachments=[card[1]])


@dp.message_callback(F.callback.payload.regexp(r"^change_(apply|new|cancel):[0-9a-f]{24}$"))
async def on_change(event: MessageCallback):
    action, token = event.callback.payload.split(":")
    user = event.callback.user
    state = await repo.get_state(user.user_id)
    prefix = f"{CHANGE_STATE}{token}:"
    if not state or not state.startswith(prefix) or not await repo.take_state(user.user_id, state):
        await event.answer(notification="Предложение устарело")
        return
    task_id, old, new, original = json.loads(state[len(prefix):])
    if action == "change_new":
        tz = await repo.ensure_user(user.user_id, user.first_name)
        await record_text(event.message.answer, user.user_id, original, tz)
        return
    if action == "change_cancel":
        text = "Срок оставил без изменений."
    elif await repo.reschedule(user.user_id, task_id, datetime.fromisoformat(old), datetime.fromisoformat(new)):
        text = "Срок задания изменён."
    else:
        text = "Задание уже изменилось. Открой карточку, чтобы проверить срок."
    await event.answer(new_text=text, attachments=[menu()])


async def offer_change(answer, user_id, text, tz):
    if not re.search(r"перен[её]с|перенос|сдвин|теперь|передвин", text, re.IGNORECASE):
        return False
    change = match_change(text, await repo.list_active(user_id), datetime.now(timezone.utc), tz)
    if change is None:
        return False
    task, new = change
    token = token_hex(12)
    old = task["due_at"]
    state = json.dumps([task["id"], old.isoformat(), new.isoformat(), text], ensure_ascii=False)
    await repo.set_state(user_id, f"{CHANGE_STATE}{token}:{state}")
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="Изменить", payload=f"change_apply:{token}"),
           CallbackButton(text="Это новое дело", payload=f"change_new:{token}"))
    kb.row(CallbackButton(text="Отмена", payload=f"change_cancel:{token}"))
    await answer(f"Перенести «{h(task['title'])}»?\nБыло: {format_due(old, tz)}\nСтало: {format_due(new, tz)}",
                 attachments=[kb.as_markup()])
    return True


@dp.message_created(F.message.body.text)
async def on_text(event: MessageCreated):
    sender = event.message.sender
    tz = await repo.ensure_user(sender.user_id, sender.first_name)
    text = event.message.body.text.strip()
    if text in ("/link", "/unlink"):
        await alice_link(sender, event.message.answer, text == "/unlink")
        return
    if text in ("/import", "/import_olympiads"):
        await repo.set_state(sender.user_id, text[1:])
        await event.message.answer("Пришли список, где каждое задание на новой строке, или файл TXT/DOCX до 2 МБ. /cancel — отменить.")
        return
    if text == "/cancel":
        await repo.pop_state(sender.user_id)
        await event.message.answer("Действие отменено.", attachments=[menu()])
        return
    if text == "/tasks":
        await post_list(sender.user_id, tz, event.message.answer)
        return
    if text == "/settings":
        view, kb = settings_view(await repo.get_prefs(sender.user_id))
        await event.message.answer(view, attachments=[kb])
        return
    if text == "/add":
        await repo.set_state(sender.user_id, "new_draft")
        await event.message.answer("Пришли задание одним сообщением. Покажу, что получилось, перед записью.")
        return
    if text.startswith("/"):
        await event.message.answer("Пришли задание сообщением. /tasks — дела, /settings — настройки, /import — список, /import_olympiads — олимпиады.",
                                   attachments=[menu()])
        return
    if not text:
        return
    state = await repo.pop_state(sender.user_id, except_prefix=MATERIAL_STATE)
    if state is None:
        mode = await repo.get_state(sender.user_id)
        if mode and mode.startswith(MATERIAL_STATE):
            task_id = int(mode[len(MATERIAL_STATE):])
            if not is_http_link(text):
                await event.message.answer("Пришли одну ссылку, фото или документ. Чтобы закончить, нажми «Готово».",
                                           attachments=[material_mode_keyboard(task_id)])
            elif await repo.add_link(sender.user_id, task_id, text):
                await event.message.answer("Ссылка прикреплена.", attachments=[material_mode_keyboard(task_id)])
            else:
                await repo.clear_state(sender.user_id, mode)
                await event.message.answer("Задание недоступно.", attachments=[menu()])
            return
    if state in (IMPORT_STATE, OLYMPIAD_IMPORT_STATE) or (state is None and looks_like_list(text)):
        await offer_import(event.message.answer, sender.user_id, text, tz, olympiads=state == OLYMPIAD_IMPORT_STATE)
        return
    if state == "new_draft":
        reply = await Reply.start(event.message.answer)
        parsed = await parse_or_sorry(reply, text, tz)
        if parsed is not None:
            await post_drafts(reply, sender.user_id, parsed, tz, "Задание")
        return
    if state and state.startswith(DUE_STATE):
        await change_due(event, int(state[len(DUE_STATE):]), tz)
        return
    if state and state.startswith(TITLE_STATE):
        title = " ".join(event.message.body.text.split())[:500]
        task_id = int(state[len(TITLE_STATE):])
        if await repo.set_title(sender.user_id, task_id, title):
            await answer_card(event.message.answer, sender.user_id, task_id, tz, "Новый текст сохранён ✅")
        else:
            await event.message.answer("Это задание уже не активно.", attachments=[menu()])
        return
    if state and state.startswith(SUBJECT_STATE):
        raw = " ".join(text.split()).strip(" .")[:60]
        if raw.lower() in ('', 'без предмета', 'нет', '-', '—', 'убрать'):
            subject = None
        else:
            subject = find_subject(raw) or raw[0].upper() + raw[1:]
        task_id = int(state[len(SUBJECT_STATE):])
        if await repo.set_subject(sender.user_id, task_id, subject):
            await answer_card(event.message.answer, sender.user_id, task_id, tz, f"Предмет: <b>{h(subject or 'без предмета')}</b> ✅")
        else:
            await event.message.answer("Это задание уже не активно.", attachments=[menu()])
        return
    if state in (QUIET_STATE, MORNING_STATE):
        await save_clock_setting(event.message.answer, sender.user_id, state, text)
        return
    reply = await Reply.start(event.message.answer)
    if await offer_change(reply, sender.user_id, text, tz):
        return
    await record_text(reply, sender.user_id, text, tz)


class Reply:

    def __init__(self, answer):
        self.answer = answer
        self.mid = None

    @classmethod
    async def start(cls, answer, text: str = "⏳ Записываю…"):
        reply = cls(answer)
        try:
            reply.mid = sent_mid(await answer(text))
        except Exception as e:
            logging.info("Не отправилось «Записываю»: %s", e)
        return reply

    async def __call__(self, text, attachments=None):
        mid, self.mid = self.mid, None
        if mid:
            try:
                await bot.edit_message(message_id=mid, text=text, attachments=attachments or [], format=ParseMode.HTML)
                return SimpleNamespace(message=SimpleNamespace(body=SimpleNamespace(mid=mid)))
            except Exception as e:
                logging.info("Не удалось заменить «Записываю» (%s), отвечаю новым сообщением", e)
        return await self.answer(text, attachments=attachments)


async def record_text(answer, user_id, text, tz):
    parsed = await parse_or_sorry(answer, text, tz)
    if parsed is None:
        return
    if not parsed.is_task:
        await answer("Не похоже на задание 🙂 Напиши, что нужно сделать и к какому сроку, например: "
                     "алгебра №24 к пятнице.", attachments=[menu()])
        return
    ids, titles, blocks = [], [], []
    for p in [parsed, *parsed.more]:
        ids.append(await repo.add_task(user_id, p.title, p.subject, p.due_at,
                                       kind=p.kind, location=p.location, reg_deadline=p.reg_deadline, duration_min=p.duration_min))
        titles.append(p.title)
        if p.location:
            where = f'\n📍 {h(p.location)}'
        else:
            where = ''
        blocks.append(task_block(full_when(p.due_at, tz, p.kind), p.subject, p.title) + where)
    if len(ids) == 1:
        head = '✅ <b>Записал</b>'
    else:
        head = f'✅ <b>Записал {len(ids)} дела</b>'
    text = head
    mode = (await repo.get_prefs(user_id)).remind_mode
    for block in blocks:
        if len(text) + len(block) > 3900:
            await answer(text, attachments=[after_task(*ids, titles=titles, remind_mode=mode)])
            text = "<b>Остальные записанные дела</b>"
        text += "\n" + block
    await answer(text, attachments=[after_task(*ids, titles=titles, remind_mode=mode)])


async def process_voice_jobs():
    for path in await repo.old_voice_files():
        if re.fullmatch(r"[0-9a-f]{32}", path):
            (filestore.FILES_DIR / path).unlink(missing_ok=True)
    for job in await repo.claim_voice_jobs():
        if job['path'] and re.fullmatch('[0-9a-f]{32}', job['path']):
            file = filestore.FILES_DIR / job['path']
        else:
            file = None
        result, error = None, None
        try:
            if file is None:
                raise ValueError("Запись не найдена")
            if not speech.enabled():
                error = "Распознавание голоса на сервере не настроено"
            else:
                transcript = (await speech.recognize(file)).strip()[:2000]
                if not transcript:
                    error = "Не удалось разобрать речь. Скажи ещё раз чуть громче"
                else:
                    parsed = await parser.parse(transcript, datetime.now(timezone.utc), job["tz"])
                    result = {"transcript": transcript, "tasks": [{
                        "title": p.title, "subject": p.subject, "kind": p.kind, "location": p.location,
                        "duration_min": p.duration_min,
                        "due_at": p.due_at.isoformat() if p.due_at else None,
                        "reg_deadline": p.reg_deadline.isoformat() if p.reg_deadline else None,
                    } for p in [parsed, *parsed.more]]}
        except ValueError as e:
            error = str(e)
        except ParserUnavailable:
            error = "Речь распознал, а GigaChat не ответил. Попробуй ещё раз через минуту"
        except Exception:
            logging.warning("Не удалось распознать запись из мини-приложения")
            error = "Не удалось распознать запись"
        finally:
            if file:
                file.unlink(missing_ok=True)
        await repo.finish_voice_job(job["id"], result, error)


#====================================[Запуск]====================================

async def subscribe_when_ready(url: str, secret: str | None):
    for delay in (2, 5, 15, 30, 60):
        await asyncio.sleep(delay)
        try:
            await bot.subscribe_webhook(url=url, secret=secret)
            logging.info("Webhook подписан: %s", url)
            return
        except Exception as e:
            logging.warning("Подписка на webhook не удалась (%s), повтор", e)
    logging.error("Не удалось подписаться на webhook: бот не получит события")


async def main():
    global repo, parser
    repo = await Repo.connect(os.environ["DATABASE_URL"])
    if not gigachat.credentials():
        raise SystemExit("Не задан GIGACHAT_CREDENTIALS в .env: без GigaChat бот не разбирает задания "
                         "(как получить ключ — instructions/tokens.md)")
    parser = GigaChatParser()
    webhook_url = os.getenv("WEBHOOK_URL")
    sender = MaxSender()

    async def reminders_job():
        try:
            await tick(repo, sender)
        except Exception:
            logging.exception("Сбой цикла напоминаний, повтор через 30 секунд")

    async def file_delivery_job():
        for file in await repo.claim_attachment_deliveries():
            async def answer(text, attachments):
                return await bot.send_message(user_id=file["user_id"], text=text, attachments=attachments)

            sent = False
            try:
                sent = sent_mid(await send_stored_file(answer, file)) is not None
            except Exception:
                logging.warning("Копия файла %s не отправлена", file["attachment_id"])
            finally:
                await repo.finish_attachment_delivery(file["attachment_id"], sent=sent)

    async def alice_job():
        for entry in await repo.claim_alice_messages():
            async def answer(text, attachments):
                return await bot.send_message(user_id=entry["user_id"], text=text, attachments=attachments)

            try:
                parsed = await parser.parse(entry["text"], datetime.now(timezone.utc), entry["tz"])
                await post_drafts(answer, entry["user_id"], parsed, entry["tz"], "🎙 Из Алисы")
            except ParserUnavailable:
                await answer(f"🎙 Из Алисы: «{h(entry['text'][:200])}». {GIGACHAT_DOWN}", None)
            except Exception:
                logging.warning("Не удалось отправить черновик из Алисы")
            finally:
                await repo.clear_alice_message(entry["event_key"])

    scheduler = AsyncIOScheduler()
    scheduler.add_job(reminders_job, "interval", seconds=30, max_instances=1, coalesce=True)
    scheduler.add_job(file_delivery_job, "interval", seconds=15, max_instances=1, coalesce=True)
    scheduler.add_job(process_voice_jobs, "interval", seconds=2, max_instances=1, coalesce=True)
    if ALICE_SECRET:
        scheduler.add_job(alice_job, "interval", seconds=5, max_instances=1, coalesce=True)
    if speech.enabled():
        scheduler.add_job(speech.unload_idle, "interval", minutes=5, max_instances=1, coalesce=True)
    scheduler.start()
    try:
        if webhook_url:
            secret = os.getenv("WEBHOOK_SECRET") or None
            subscription = asyncio.create_task(subscribe_when_ready(webhook_url, secret))
            await dp.handle_webhook(bot, host="0.0.0.0", port=8080, path=urlparse(webhook_url).path or "/",
                                    secret=secret)
            subscription.cancel()
        else:
            await bot.delete_webhook()
            await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await repo.close()


if __name__ == "__main__":
    asyncio.run(main())
