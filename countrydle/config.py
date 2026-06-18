import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _parse_ids(raw):
    """Parse a comma-separated string of Discord IDs into a set of ints."""
    return {int(part) for part in raw.split(",") if part.strip()}


@dataclass(frozen=True)
class Config:
    """Runtime configuration sourced from environment variables."""

    discord_token: str
    guild_id: int
    channel_id: int
    admin_ids: set
    timezone: str
    post_hour: int
    database_path: str

    @classmethod
    def from_env(cls):
        """Build a Config from the current environment, applying sensible defaults."""
        return cls(
            discord_token=os.getenv("DISCORD_TOKEN", ""),
            guild_id=int(os.getenv("GUILD_ID") or 0),
            channel_id=int(os.getenv("CHANNEL_ID") or 0),
            admin_ids=_parse_ids(os.getenv("ADMIN_IDS", "")),
            timezone=os.getenv("TIMEZONE", "Europe/London"),
            post_hour=int(os.getenv("POST_HOUR") or 9),
            database_path=os.getenv("DATABASE_PATH", "data/game.db"),
        )

    def require_token(self):
        """Return the Discord token, raising if it has not been configured."""
        if not self.discord_token:
            raise RuntimeError("DISCORD_TOKEN is not set; copy .env.example to .env and fill it in")
        return self.discord_token
