from enum import StrEnum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(StrEnum):
    ZAI = "zai"
    OLLAMA = "ollama"


_USER_ENV = str(Path.home() / ".linkedin-vault" / ".env")


class Settings(BaseSettings):
    # pydantic-settings resolves env files left-to-right; later files override earlier.
    # The user-global .env (~/.linkedin-vault/.env) is loaded after the local .env so
    # settings saved by the TUI wizard take effect regardless of the working directory.
    model_config = SettingsConfigDict(
        env_file=(".env", _USER_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "LinkedIn Vault"
    data_dir: Path = Path.home() / ".linkedin-vault"
    db_path: Path | None = None
    log_level: str = "INFO"

    # LLM Provider
    llm_provider: LLMProvider = LLMProvider.ZAI
    llm_model: str = ""

    # z.ai
    zai_api_key: str = ""
    zai_base_url: str = "https://api.z.ai/v1"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"

    # Enrichment
    enrich_delay_seconds: float = 0.5  # Rate-limit pause between posts

    # Dashboard
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8765

    # Chat
    chat_provider: LLMProvider | None = None  # falls back to llm_provider
    chat_model: str = ""                       # falls back to llm_model
    chat_top_k: int = 8

    def get_db_path(self) -> Path:
        if self.db_path:
            return self.db_path
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "vault.db"

    def get_chat_provider(self) -> LLMProvider:
        return self.chat_provider or self.llm_provider

    def get_chat_model(self) -> str:
        return self.chat_model or self.llm_model


def load_settings() -> Settings:
    return Settings()


def save_settings_to_file(settings_dict: dict[str, str]) -> None:
    import os

    env_path = Path.home() / ".linkedin-vault" / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                existing[key.strip()] = value.strip()

    existing.update(settings_dict)

    lines = [f"{k}={v}" for k, v in existing.items()]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(env_path, 0o600)
