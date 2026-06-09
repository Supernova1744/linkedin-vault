from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from linkedin_vault.config import LLMProvider, Settings, load_settings, save_settings_to_file


def test_settings_defaults(tmp_path: Path) -> None:
    # _USER_ENV is frozen into model_config at import time as the literal path
    # to ~/,linkedin-vault/.env, so patching Path.home at runtime has no effect
    # on Settings(). Instead we redirect env_file to a nonexistent tmp path so
    # neither the project-local .env nor the real user .env is loaded.
    with patch.dict(
        "linkedin_vault.config.Settings.model_config",
        {"env_file": str(tmp_path / ".env")},
    ):
        s = Settings()
    assert s.app_name == "LinkedIn Vault"
    assert s.llm_provider == LLMProvider.ZAI
    assert s.dashboard_port == 8765
    assert s.dashboard_host == "127.0.0.1"


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "llama3.2")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11435")
    s = Settings()
    assert s.llm_provider == LLMProvider.OLLAMA
    assert s.llm_model == "llama3.2"
    assert s.ollama_base_url == "http://localhost:11435"


def test_settings_invalid_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(ValidationError):
        Settings()


def test_get_db_path_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    s = Settings(data_dir=tmp_path)
    db_path = s.get_db_path()
    assert db_path == tmp_path / "vault.db"
    assert db_path.parent.exists()


def test_get_db_path_custom() -> None:
    custom = Path("/tmp/custom_vault.db")
    s = Settings(db_path=custom)
    assert s.get_db_path() == custom


def test_save_settings_creates_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    save_settings_to_file({"LLM_PROVIDER": "ollama", "LLM_MODEL": "llama3.2"})
    env_file = tmp_path / ".linkedin-vault" / ".env"
    assert env_file.exists()
    content = env_file.read_text()
    assert "LLM_PROVIDER=ollama" in content
    assert "LLM_MODEL=llama3.2" in content


def test_save_settings_merges_existing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    env_dir = tmp_path / ".linkedin-vault"
    env_dir.mkdir(parents=True)
    (env_dir / ".env").write_text("ZAI_API_KEY=old_key\n")
    save_settings_to_file({"LLM_MODEL": "glm-4"})
    content = (env_dir / ".env").read_text()
    assert "ZAI_API_KEY=old_key" in content
    assert "LLM_MODEL=glm-4" in content


def test_load_settings_returns_settings_instance() -> None:
    s = load_settings()
    assert isinstance(s, Settings)
