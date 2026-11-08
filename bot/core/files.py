import ipaddress
import os
import socket
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp

FILES_DIR = Path(os.getenv("FILES_DIR", "/data/files"))
MAX_BYTES = 20 * 1024 * 1024
TIMEOUT = aiohttp.ClientTimeout(total=60)


class FileTooLarge(Exception):
    pass


def public_address(value: str) -> bool:
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    addr = getattr(addr, "ipv4_mapped", None) or addr
    return addr.is_global and not addr.is_multicast


def validate_download_url(url: str) -> None:
    target = urlsplit(url)
    host = target.hostname
    if target.scheme != "https" or not host or target.username is not None or target.fragment or target.port not in (None, 443):
        raise ValueError("Недопустимый адрес вложения")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return
    if not public_address(host):
        raise ValueError("Недопустимый адрес вложения")


class PublicResolver(aiohttp.ThreadedResolver):
    async def resolve(self, host, port=0, family=socket.AF_INET):
        addresses = await super().resolve(host, port, family)
        if not addresses or any(not public_address(row["host"]) for row in addresses):
            raise ValueError("Недопустимый адрес вложения")
        return addresses


@dataclass
class Incoming:
    kind: str
    url: str
    name: str
    size: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def incoming_attachments(attachments) -> list[Incoming]:
    out = []
    for i, a in enumerate(attachments or []):
        kind = getattr(a, "type", None)
        kind = getattr(kind, "value", kind)
        url = getattr(getattr(a, "payload", None), "url", None)
        if not url:
            continue
        if kind == "image":
            out.append(Incoming("photo", url, f"Фото {i + 1}.jpg"))
        elif kind == "file":
            name = (getattr(a, "filename", None) or f"Файл {i + 1}").strip()[:200]
            out.append(Incoming("doc", url, name, getattr(a, "size", None)))
    return out


def file_title(name: str) -> str:
    if '.' in name[-6:]:
        stem = name.rsplit('.', 1)[0]
    else:
        stem = name
    return " ".join(stem.replace("_", " ").split())


async def download(url: str, files_dir: Path | None = None, limit: int | None = None) -> tuple[str, int, str | None]:
    validate_download_url(url)
    files_dir = files_dir or FILES_DIR
    limit = limit or MAX_BYTES
    files_dir.mkdir(parents=True, exist_ok=True)
    stored = uuid.uuid4().hex
    target = files_dir / stored
    size = 0
    resolver = PublicResolver()
    try:
        connector = aiohttp.TCPConnector(resolver=resolver)
        async with aiohttp.ClientSession(timeout=TIMEOUT, connector=connector) as session:
            async with session.get(url, allow_redirects=False) as resp:
                if not 200 <= resp.status < 300:
                    raise ValueError(f"Файл недоступен (HTTP {resp.status})")
                if resp.content_length is not None and resp.content_length > limit:
                    raise FileTooLarge()
                mime = resp.headers.get("Content-Type", "").split(";")[0].strip() or None
                with target.open("wb") as fh:
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        size += len(chunk)
                        if size > limit:
                            raise FileTooLarge()
                        fh.write(chunk)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    finally:
        await resolver.close()
    return stored, size, mime
