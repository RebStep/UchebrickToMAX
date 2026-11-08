import ssl
import time
import uuid
from pathlib import Path

import aiohttp

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

_CA_FILE = Path(__file__).resolve().parent.parent / "certs" / "russian_trusted_root_ca.pem"
SSL = ssl.create_default_context()
SSL.load_verify_locations(cafile=str(_CA_FILE))


class SberToken:

    def __init__(self, credentials: str, scope: str, name: str):
        self.credentials = credentials
        self.scope = scope
        self.name = name
        self._token: str | None = None
        self._expires_at = 0.0

    async def get(self, session: aiohttp.ClientSession) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        async with session.post(
            OAUTH_URL,
            headers={
                "Authorization": f"Basic {self.credentials}",
                "RqUID": str(uuid.uuid4()),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data={"scope": self.scope},
            ssl=SSL,
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"{self.name} OAuth: HTTP {resp.status}")
            body = await resp.json()
        self._token = body["access_token"]
        self._expires_at = body["expires_at"] / 1000
        return self._token
