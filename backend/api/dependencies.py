from functools import lru_cache
from ..core.config import Settings, get_settings as _get_settings


@lru_cache
def get_settings() -> Settings:
    """Cached singleton for settings — reads .env once at startup."""
    return _get_settings()
