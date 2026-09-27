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

    # getting a human's attention
    public_url: str = ""                          # what links in notifications should point at
    notify_slack_channel: str = ""                # channel id for approvals + digests
    notify_webhook: str = ""                      # any HTTPS endpoint; also fine for PagerDuty/Teams
    notify_after_minutes: int = 45                # chase an approval once, after this long

    # verified-work pricing: you are billed only for work a human approved or did not reverse
    price_per_verified_action_usd: float = 0.30
    dispute_window_hours: int = 24
    loaded_hourly_cost_usd: float = 65.0          # for the value/ROI line; set it to your own number
    comparison_seat_price_usd: float = 30.0       # what per-seat tools would charge the same team

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
