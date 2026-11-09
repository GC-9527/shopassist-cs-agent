from __future__ import annotations

from customer_service_app.core.config import Settings, _apply_shared_provider_credentials


def _settings_without_keys() -> Settings:
    settings = Settings()
    settings.llm_api_key = ""
    settings.embedding_api_key = ""
    settings.rerank_api_key = ""
    return settings


def test_shared_dashscope_key_fills_empty_credentials(monkeypatch) -> None:
    """应用装配时复用 DASHSCOPE_API_KEY，避免把密钥写进 .env。"""

    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-shared-test")
    settings = _apply_shared_provider_credentials(_settings_without_keys())

    assert settings.llm_api_key == "sk-shared-test"
    assert settings.embedding_api_key == "sk-shared-test"
    assert settings.rerank_api_key == "sk-shared-test"


def test_explicit_credentials_win_over_shared_key(monkeypatch) -> None:
    """显式配置的凭证优先，避免环境变量覆盖 .env 中的独立账号。"""

    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-shared-test")
    settings = Settings(llm_api_key="sk-explicit")
    settings.embedding_api_key = ""
    settings.rerank_api_key = ""

    settings = _apply_shared_provider_credentials(settings)

    assert settings.llm_api_key == "sk-explicit"
    assert settings.embedding_api_key == "sk-shared-test"


def test_no_env_key_leaves_credentials_untouched(monkeypatch) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)

    settings = _apply_shared_provider_credentials(_settings_without_keys())

    assert settings.llm_api_key == ""
