from core.config import Settings
from services.chat_service import llm_council_status


def _settings(**overrides: object) -> Settings:
    values = {
        "llm_council_enabled": True,
        "llm_provider": "openrouter",
        "llm_model": "anthropic/claude-haiku-4.5",
        "openrouter_api_key": "test-key",
        "llm_council_available_models": (
            "anthropic/claude-haiku-4.5,"
            "openai/gpt-4.1-mini,"
            "google/gemini-2.5-flash"
        ),
    }
    values.update(overrides)
    return Settings(**values)


def test_llm_council_status_accepts_ui_selected_models_and_chair() -> None:
    status = llm_council_status(
        _settings(),
        requested_models=[
            "anthropic/claude-haiku-4.5",
            "openai/gpt-4.1-mini",
            "anthropic/claude-haiku-4.5",
        ],
        requested_chair_model="openai/gpt-4.1-mini",
    )

    assert status.configured is True
    assert status.models == ["anthropic/claude-haiku-4.5", "openai/gpt-4.1-mini"]
    assert status.chair_model == "openai/gpt-4.1-mini"


def test_llm_council_status_rejects_unallowed_ui_model() -> None:
    status = llm_council_status(
        _settings(),
        requested_models=["anthropic/claude-haiku-4.5", "unknown/model"],
        requested_chair_model="anthropic/claude-haiku-4.5",
    )

    assert status.configured is False
    assert "not allowed" in status.reason


def test_llm_council_status_requires_chair_from_selected_models() -> None:
    status = llm_council_status(
        _settings(),
        requested_models=["openai/gpt-4.1-mini", "google/gemini-2.5-flash"],
        requested_chair_model="anthropic/claude-haiku-4.5",
    )

    assert status.configured is False
    assert "chair model" in status.reason
