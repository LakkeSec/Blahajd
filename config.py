"""Reads all configuration from the environment (.env file).

Fails fast with a clear message when something is missing — better than
discovering it halfway through a rollout.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROLE_ENV_KEYS = {
    "itf": "ROLE_ITF",
    "app_ai": "ROLE_APP_AI",
    "digital_innovation": "ROLE_DIGITAL_INNOVATION",
    "year_2": "ROLE_YEAR_2",
    "year_3": "ROLE_YEAR_3",
    "alumni": "ROLE_ALUMNI",
    "docent": "ROLE_DOCENT",
    "ethical_hacking": "ROLE_ETHICAL_HACKING",
    "cloud_defence": "ROLE_CLOUD_AUTOMATION_DEFENCE",
}


@dataclass(frozen=True)
class Config:
    token: str
    guild_id: int
    role_ids: dict[str, int]
    request_channel_id: int
    maintainer_role_id: int
    db_path: str


def _env_or_exit(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(
            f"Missing {name} in .env — copy .env.example to .env and fill it in."
        )
    return value


def _load() -> Config:
    load_dotenv(Path(__file__).parent / ".env")

    try:
        guild_id = int(_env_or_exit("GUILD_ID"))
        role_ids = {key: int(_env_or_exit(env)) for key, env in ROLE_ENV_KEYS.items()}
    except ValueError:
        raise SystemExit(
            "GUILD_ID and all ROLE_* values in .env must be numbers (role IDs, not names)."
        ) from None

    return Config(
        token=_env_or_exit("DISCORD_TOKEN"),
        guild_id=guild_id,
        role_ids=role_ids,
        request_channel_id=int(_env_or_exit("REQUEST_CHANNEL_ID")),
        maintainer_role_id=int(_env_or_exit("MAINTAINER_ROLE_ID")),
        db_path=os.getenv("DB_PATH", str(Path(__file__).parent / "blahajd.db")),
    )


CONFIG = _load()
