from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    webhook_secret: str
    port: int = 3001
    claude_bin: str = "claude"
    repo_path: str = "."
    gitea_base_url: str = "http://10.10.10.90:3000"
    gitea_repo: str = "gx1400/weaving_site"
    gitea_token: str


settings = Settings()
