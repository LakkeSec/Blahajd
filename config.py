"""Reads all configuration from the environment (.env file).

Fails fast with a clear message when something is missing — better than
discovering it halfway through a rollout.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

import roles

# role key -> the env var that holds its ID. The keys themselves live in
# roles.ROLE_KEYS, and _check_role_keys() keeps the two in sync.
ROLE_ENV_KEYS = {
    "itf": "ROLE_ITF",
    "app_ai": "ROLE_APP_AI",
    "digital_innovation": "ROLE_DIGITAL_INNOVATION",
    "it_graduaten": "ROLE_IT_GRADUATEN",
    "year_2": "ROLE_YEAR_2",
    "year_3": "ROLE_YEAR_3",
    "alumni": "ROLE_ALUMNI",
    "docent": "ROLE_DOCENT",
    "ethical_hacking": "ROLE_ETHICAL_HACKING",
    "cloud_defence": "ROLE_CLOUD_AUTOMATION_DEFENCE",
    "blahaj": "ROLE_BLAHAJ",
    "sin": "ROLE_SIN",
    "student_council": "ROLE_STUDENT_COUNCIL",
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
        raise SystemExit(f"Missing {name} in .env — copy .env.example to .env and fill it in.")
    return value


def _check_role_keys() -> None:
    """Fail fast if the role list in roles.py drifts from the config mapping.

    Both sides claim to know the authoritative set of roles; keeping them in
    sync by hand is exactly the kind of thing a rollout breaks on.
    """
    mapped = set(ROLE_ENV_KEYS)
    expected = set(roles.ROLE_KEYS)
    if mapped != expected:
        missing = sorted(expected - mapped)
        extra = sorted(mapped - expected)
        raise SystemExit(
            f"role config drift: {roles.ROLE_KEYS=} vs {ROLE_ENV_KEYS=}. "
            f"Fix roles.py/config.py: missing={missing}, extra={extra}"
        )


def _load() -> Config:
    load_dotenv(Path(__file__).parent / ".env")
    _check_role_keys()

    try:
        guild_id = int(_env_or_exit("GUILD_ID"))
        role_ids = {key: int(_env_or_exit(env)) for key, env in ROLE_ENV_KEYS.items()}
        request_channel_id = int(_env_or_exit("REQUEST_CHANNEL_ID"))
        maintainer_role_id = int(_env_or_exit("MAINTAINER_ROLE_ID"))
    except ValueError:
        raise SystemExit(
            "GUILD_ID, REQUEST_CHANNEL_ID, MAINTAINER_ROLE_ID and all ROLE_* "
            "values in .env must be numbers (role IDs, not names)."
        ) from None

    return Config(
        token=_env_or_exit("DISCORD_TOKEN"),
        guild_id=guild_id,
        role_ids=role_ids,
        request_channel_id=request_channel_id,
        maintainer_role_id=maintainer_role_id,
        db_path=os.getenv("DB_PATH", str(Path(__file__).parent / "blahajd.db")),
    )


CONFIG = _load()
