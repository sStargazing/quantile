from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables or a local .env file."""

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    fx_api_base_url: str = "https://api.frankfurter.dev/v2"
    cpi_api_base_url: str = "https://api.imf.org/external/sdmx/2.1"

    # Neither current provider needs a key. If a keyed provider is added, read
    # its key from here, never from source code or the frontend.
    exchange_rate_api_key: str | None = None
    inflation_api_key: str | None = None

    cache_dir: Path = ROOT_DIR / ".cache" / "quantile"
    http_timeout_seconds: float = 90.0

    # Cache lifetimes (seconds).
    fx_current_ttl: int = 60 * 60  # current-month FX chunk
    fx_recent_ttl: int = 7 * 24 * 60 * 60  # earlier months of the current year
    fx_history_ttl: int = 90 * 24 * 60 * 60  # completed calendar years
    cpi_ttl: int = 7 * 24 * 60 * 60
    analysis_ttl: int = 10 * 60  # computed leaderboards / country analyses

    # Fetch the default leaderboard's data in the background at startup.
    prewarm_on_startup: bool = True


settings = Settings()
