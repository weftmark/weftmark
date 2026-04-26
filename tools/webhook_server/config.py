from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_SECRET = "change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    webhook_secret: str
    port: int = 3001
    claude_bin: str = "claude"
    repo_path: str = "."
    gitea_base_url: str = "http://10.10.10.90:3000"
    gitea_repo: str = "gx1400/weaving_site"
    gitea_token: str

    @model_validator(mode="after")
    def _reject_default_secret(self) -> "Settings":
        if self.webhook_secret == _DEFAULT_SECRET:
            raise ValueError(
                "WEBHOOK_SECRET is still the insecure default 'change-me'. "
                "Set a strong random value in your .env file."
            )
        return self


settings = Settings()
