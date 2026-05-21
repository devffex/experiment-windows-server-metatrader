from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Centralized orchestrator configuration with environment variable overrides."""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    admin_api_key: str | None = None
    base_domain: str = "savisor.com"

    # Paths
    base_dir: Path = Path("C:/savisor")
    master_terminal_dir: Path = Path("C:/savisor/terminal")
    scripts_dir: Path = Path("scripts")
    rdp_profiles_dir: Path = Path("rdp_profiles")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/savisor"

    # Port allocation
    port_range_start: int = 8001
    port_range_end: int = 8050

    # Gateway proxy
    proxy_timeout: float = 30.0
    proxy_max_retries: int = 2
    health_check_timeout: float = 5.0
    health_check_interval: float = 30.0

    # RDP profile generation
    rdp_server_address: str = "127.0.0.1"

    model_config = {
        "env_prefix": "ORCHESTRATOR_",
        "env_file": ("C:/savisor/.env", ".env")
    }


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
