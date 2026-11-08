import io
import re
import zipfile
from dataclasses import asdict
from datetime import datetime, time
from urllib.parse import urlsplit
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from core.dates import parse_when
from core.parser import SUBJECT_PATTERNS, TaskParser, find_subject

MAX_IMPORT_BYTES = 2 * 1024 * 1024
MAX_ITEMS = 40
_BULLET = re.compile(r"^\s*(?:[•●*-]|\d{1,3}[.)])\s+")
_LINK = re.compile(r"https?://[^\s<>«»]+", re.IGNORECASE)
_WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_OLYMPIAD = re.compile(r"\bолимпиад[а-яё]*\b", re.IGNORECASE)
_LEVEL = re.compile(r"\s*\(?\b(IV|I{1,3})\s*ур(?:ов(?:ень|ня)|\.)?\)?", re.IGNORECASE)
_TOUR = re.compile(r"(?:\d+|перв\w*|втор\w*|трет\w*)\s+(?:[а-яё]+\s+)?(?:тур|этап)\b|(?:тур|этап)\s+\d+", re.IGNORECASE)
_RANGE = re.compile(r"(?:с\s+)?(\d{1,2}(?:[./]\d{1,2}(?:[./]\d{2,4})?)?)\s*(?:по|[-–—])\s*(\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?)")
_DATE_WORD = re.compile(r"\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?.*$")


def is_http_link(text: str) -> bool:
    if not text or len(text) > 2000 or any(char.isspace() or ord(char) < 32 for char in text):
        return False
    try:
        url = urlsplit(text)
        return url.scheme in ("http", "https") and bool(url.hostname) and url.username is None
    except ValueError:
        return False


def _docx_xml(archive: zipfile.ZipFile, name: str):
    with archive.open(name) as stream:
        data = stream.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES or b"<!DOCTYPE" in data.upper():
        raise ValueError("Содержимое DOCX слишком большое или повреждено")
    return ElementTree.fromstring(data)


def document_text(data: bytes, filename: str) -> str:
    if len(data) > MAX_IMPORT_BYTES:
        raise ValueError("Документ больше 2 МБ")
    if filename.lower().endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                root = _docx_xml(archive, "word/document.xml")
                try:
                    refs = _docx_xml(archive, "word/_rels/document.xml.rels")
                except KeyError:
                    refs = ()
                urls = {ref.get("Id"): ref.get("Target", "") for ref in refs if ref.get("TargetMode") == "External"}
            lines = []
            for paragraph in root.iter(_WORD + "p"):
                text = "".join(node.text or "" if node.tag == _WORD + "t" else "\n" if node.tag in (_WORD + "br", _WORD + "cr") else ""
                               for node in paragraph.iter())
                links = [urls.get(node.get(_REL + "id"), "") for node in paragraph.iter(_WORD + "hyperlink")]
                lines.append(text + "".join(" " + link for link in links if is_http_link(link) and link not in text))
            return "\n".join(lines)
        except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
            raise ValueError("Не удалось открыть DOCX") from exc
    if filename.lower().endswith(".txt"):
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return data.decode("cp1251", errors="replace")
    raise ValueError("Нужен файл TXT или DOCX")


def looks_like_list(text: str) -> bool:
    return sum(bool(_BULLET.match(line)) for line in text.splitlines()) >= 3


def olympiad_fields(title: str, raw: str, now: datetime, tz: str) -> dict:
    level_match = _LEVEL.search(title) or _LEVEL.search(raw)
    base = re.sub(r"^(?:Узнать дату:\s*|Олимпиада\s+)+", "", title, flags=re.IGNORECASE)
    base = _LEVEL.sub("", base).replace("«", "").replace("»", "")
    tour = _TOUR.search(base) or _TOUR.search(raw)
    name = _TOUR.sub("", _DATE_WORD.sub("", base)).strip(" ,—-:")
    name = re.sub(r"\s+с$", "", name, flags=re.IGNORECASE) or base.strip() or title
    data = {"name": name[:300], "level": level_match[1].upper() if level_match else None,
            "tour": tour[0] if tour else "Тур", "starts_at": None, "end_at": None}
    zone = ZoneInfo("Europe/Moscow" if re.search(r"\bмск\b", raw, re.IGNORECASE) else tz)
    local = now.astimezone(zone).replace(tzinfo=None)
    if match := _RANGE.search(raw):
        left, right = match.groups()
        if "." not in left and "/" not in left:
            left += right[len(re.match(r"\d+", right)[0]):]
        start = parse_when(left, local, time())
        end = parse_when(right, start or local)
        if start and end and start <= end:
            data["starts_at"] = start.replace(tzinfo=zone).isoformat()
            data["end_at"] = end.replace(tzinfo=zone).isoformat()
    return data


async def parse_list(text: str, parser: TaskParser, now: datetime, tz: str, *, olympiads=False) -> list[dict]:
    entries, subject = [], None
    names = {name.casefold() for name, _ in SUBJECT_PATTERNS}
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > MAX_ITEMS + len(names):
        raise ValueError(f"Пришли не больше {MAX_ITEMS} заданий за раз")
    item_count = 0
    for line in lines:
        heading = line.removesuffix(":").strip()
        if heading.casefold() in names:
            subject = find_subject(heading)
            continue
        item_count += 1
        if item_count > MAX_ITEMS:
            raise ValueError(f"Пришли не больше {MAX_ITEMS} заданий за раз")
        line = _BULLET.sub("", line)[:2000]
        urls = [match.rstrip(".,;)") for match in _LINK.findall(line)]
        plain = _LINK.sub("", line).strip()
        if not plain:
            continue
        if re.search('\\bмск\\b', plain, re.IGNORECASE):
            item_tz = 'Europe/Moscow'
        else:
            item_tz = tz
        first = await parser.parse(plain, now, item_tz)
        for item in [first, *first.more]:
            if not item.is_task or not item.title:
                continue
            entry = asdict(item)
            entry.pop("more")
            entry.pop("is_task")
            entry["subject"] = item.subject or subject
            entry["links"] = list(dict.fromkeys(url for url in urls if is_http_link(url)))[:10]
            for field in ("due_at", "reg_deadline"):
                entry[field] = entry[field].isoformat() if entry[field] else None
            if olympiads or _OLYMPIAD.search(plain):
                entry["olympiad"] = olympiad_fields(item.title, plain, now, tz)
            entries.append(entry)
            if len(entries) > MAX_ITEMS:
                raise ValueError(f"В списке получилось больше {MAX_ITEMS} заданий")
    return entries
