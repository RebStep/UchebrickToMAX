import asyncio
import heapq
import itertools
import logging
import os

import aiohttp

from core.sber_auth import SSL, SberToken

GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS", "")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat")

log = logging.getLogger(__name__)

CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
RETRY_DELAYS = (2, 5, 10)

_token = None

PRIORITY_USER = 0
PRIORITY_BULK = 1


class _Queue:
    def __init__(self):
        self._busy = False
        self._waiting: list[tuple[int, int, asyncio.Future]] = []
        self._seq = itertools.count()

    async def acquire(self, priority: int):
        if not self._busy and not self._waiting:
            self._busy = True
            return
        fut = asyncio.get_running_loop().create_future()
        heapq.heappush(self._waiting, (priority, next(self._seq), fut))
        try:
            await fut
        except asyncio.CancelledError:
            if fut.done() and not fut.cancelled():
                self.release()
            else:
                self._waiting = [w for w in self._waiting if w[2] is not fut]
                heapq.heapify(self._waiting)
            raise

    def release(self):
        while self._waiting:
            _, _, fut = heapq.heappop(self._waiting)
            if not fut.done():
                fut.set_result(None)
                return
        self._busy = False

    def waiting(self) -> int:
        return len(self._waiting)


queue = _Queue()


def credentials() -> str:
    return os.getenv("GIGACHAT_CREDENTIALS", GIGACHAT_CREDENTIALS)


class _Retryable(Exception):
    pass


async def _request(system: str, user: str, max_tokens: int, model: str | None, timeout: float) -> str:
    global _token
    key, scope = credentials(), os.getenv("GIGACHAT_SCOPE", GIGACHAT_SCOPE)
    if _token is None or (_token.credentials, _token.scope) != (key, scope):
        _token = SberToken(key, scope, "GigaChat")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
        token = await _token.get(session)
        async with session.post(
            CHAT_URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            json={
                "model": model or os.getenv("GIGACHAT_MODEL", GIGACHAT_MODEL),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.1,
                "max_tokens": max_tokens,
            },
            ssl=SSL,
        ) as resp:
            if resp.status == 429 or resp.status >= 500:
                raise _Retryable(f"GigaChat: HTTP {resp.status}")
            if resp.status != 200:
                raise RuntimeError(f"GigaChat: HTTP {resp.status}")
            body = await resp.json()
    return body["choices"][0]["message"]["content"]


async def complete(system: str, user: str, max_tokens: int = 700, model: str | None = None,
                   timeout: float = 30, priority: int = PRIORITY_USER) -> str:
    await queue.acquire(priority)
    try:
        for attempt, delay in enumerate((*RETRY_DELAYS, None)):
            try:
                return await _request(system, user, max_tokens, model, timeout)
            except (_Retryable, aiohttp.ClientError, asyncio.TimeoutError) as e:
                if delay is None:
                    raise RuntimeError(str(e) or "GigaChat: timeout") from e
                log.info("GigaChat busy/failed (%s), retry %d in %ss", e or "timeout", attempt + 1, delay)
                await asyncio.sleep(delay)
    finally:
        queue.release()
