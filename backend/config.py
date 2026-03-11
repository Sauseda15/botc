from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
for env_path in (ROOT_DIR / '.env', ROOT_DIR.parent / '.env'):
    if env_path.exists():
        load_dotenv(env_path)


def _parse_csv(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(',') if part.strip())


@dataclass(frozen=True)
class Settings:
    discord_token: str | None
    discord_client_id: str | None
    discord_client_secret: str | None
    discord_redirect_uri: str
    frontend_base_url: str
    session_cookie_name: str
    session_duration_hours: int
    storyteller_ids: frozenset[str]
    enable_discord_bot: bool
    database_url: str | None

    @property
    def discord_oauth_ready(self) -> bool:
        return bool(
            self.discord_client_id
            and self.discord_client_secret
            and self.discord_redirect_uri
        )

    @property
    def bot_ready(self) -> bool:
        token = (self.discord_token or '').strip()
        return self.enable_discord_bot and bool(token) and token != 'rotate-this-token-before-use'

    @property
    def database_ready(self) -> bool:
        return bool((self.database_url or '').strip())


settings = Settings(
    discord_token=os.getenv('DISCORD_TOKEN'),
    discord_client_id=os.getenv('DISCORD_CLIENT_ID'),
    discord_client_secret=os.getenv('DISCORD_CLIENT_SECRET'),
    discord_redirect_uri=os.getenv('DISCORD_REDIRECT_URI', 'http://localhost:8000/api/auth/callback'),
    frontend_base_url=os.getenv('FRONTEND_BASE_URL', 'http://localhost:5173'),
    session_cookie_name=os.getenv('SESSION_COOKIE_NAME', 'botc_session'),
    session_duration_hours=int(os.getenv('SESSION_DURATION_HOURS', '12')),
    storyteller_ids=_parse_csv(os.getenv('STORYTELLER_DISCORD_IDS')),
    enable_discord_bot=os.getenv('ENABLE_DISCORD_BOT', 'false').lower() == 'true',
    database_url=os.getenv('DATABASE_URL'),
)