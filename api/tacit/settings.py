from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from the environment (TACIT_*) or a .env file. Secrets never live in the DB."""
    model_config = SettingsConfigDict(env_prefix="TACIT_", env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "sqlite:///./tacit.db"
    secret_key: str = Field(default="change-me-in-production", description="Signs session cookies")
    host: str = "127.0.0.1"
    port: int = 4800
    org_name: str = "My Company"
    handle: str = "tacit"                      # @handle people use to summon it
    workspace: str = "."                       # directory file/shell tools are jailed to
    web_dist: str = "../web/dist"

    brain_provider: str = "auto"               # auto | anthropic | claude-cli | openai-compatible | local
    brain_model: str = "claude-opus-5"
    brain_effort: str = "medium"
    brain_base_url: str = ""
    anthropic_api_key: str = ""

    github_token: str = ""
    github_repos: str = ""                     # comma-separated owner/name
    github_webhook_secret: str = ""
    slack_bot_token: str = ""
    slack_channels: str = ""
    slack_signing_secret: str = ""
    linear_api_key: str = ""
    mcp_servers: str = ""                      # JSON list [{"name":..,"command":[..]}]

    default_read: str = "allow"
    default_write: str = "ask"
    default_exec: str = "ask"
    shadow_window_minutes: int = 240           # how long a draft waits for the human's real action
    graduate_min_scored: int = 10
    graduate_min_trust: float = 0.60
    scheduler_tick: int = 15

    def list(self, v: str) -> list[str]:
        return [x.strip() for x in v.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
