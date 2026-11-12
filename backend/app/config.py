"""runtime configuration with sensible local-development defaults"""

from os import environ
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]


def _env_path(name: str, default: str) -> Path:
    """resolve an env path relative to the repository root"""
    value = Path(environ.get(name, default)).expanduser()
    if not value.is_absolute():
        value = BASE_DIR / value
    return value.resolve()


DATABASE_URL = environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://imdb-db:secret123@localhost:5432/imdb-db",
)
DATABASE_URL_SYNC = environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://imdb-db:secret123@localhost:5432/imdb-db",
)
CACHE_DIR = _env_path("CACHE_DIR", "data/cache")
FRONTEND_DIST = _env_path("FRONTEND_DIST", "frontend/dist")
API_TOKEN = environ.get("API_TOKEN", "")
DATASET_TO_KEEP = environ.get("DATASET_TO_KEEP")
