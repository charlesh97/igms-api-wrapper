from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


DEFAULT_ENV_PATH = Path(".env")


def load_env_file(path: str | Path = DEFAULT_ENV_PATH) -> None:
    """Load environment variables from a .env file (only if not already set)."""
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


@dataclass
class IGMSConfig:
    """Configuration for connecting to the iGMS API."""

    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = ""
    scope: str = "listings"
    access_token: str = ""
    auth_url: str = "https://igms.com/app/auth.html"
    token_url: str = "https://igms.com/auth/token"
    api_base: str = "https://www.igms.com"

    @classmethod
    def from_env(cls, env_path: str | Path = DEFAULT_ENV_PATH) -> IGMSConfig:
        """Load config from environment variables, optionally reading a .env file first."""
        load_env_file(env_path)
        return cls(
            client_id=os.getenv("IGMS_CLIENT_ID", ""),
            client_secret=os.getenv("IGMS_CLIENT_SECRET", ""),
            redirect_uri=os.getenv("IGMS_REDIRECT_URI", ""),
            scope=os.getenv("IGMS_SCOPE", "listings"),
            access_token=os.getenv("IGMS_ACCESS_TOKEN", ""),
        )
