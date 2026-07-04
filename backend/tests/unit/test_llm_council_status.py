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


def test_llm_council_status_accepts_two_response_models_and_separate_evaluator() -> None:
    status = llm_council_status(
        _settings(),
        requested_models=[
            "anthropic/claude-haiku-4.5",
            "openai/gpt-4.1-mini",
            "anthropic/claude-haiku-4.5",
        ],
        requested_chair_model="google/gemini-2.5-flash",
    )

    assert status.configured is True
    assert status.models == ["anthropic/claude-haiku-4.5", "openai/gpt-4.1-mini"]
    assert status.chair_model == "google/gemini-2.5-flash"


def test_llm_council_status_rejects_unallowed_ui_model() -> None:
    status = llm_council_status(
        _settings(),
        requested_models=["anthropic/claude-haiku-4.5", "unknown/model"],
        requested_chair_model="anthropic/claude-haiku-4.5",
    )

    assert status.configured is False
    assert "not allowed" in status.reason


def test_llm_council_status_rejects_three_response_models() -> None:
    status = llm_council_status(
        _settings(),
        requested_models=[
            "anthropic/claude-haiku-4.5",
            "openai/gpt-4.1-mini",
            "google/gemini-2.5-flash",
        ],
        requested_chair_model="anthropic/claude-haiku-4.5",
    )

    assert status.configured is False
    assert "exactly two" in status.reason


def test_llm_council_status_rejects_evaluator_from_response_models() -> None:
    status = llm_council_status(
        _settings(),
        requested_models=["openai/gpt-4.1-mini", "google/gemini-2.5-flash"],
        requested_chair_model="openai/gpt-4.1-mini",
    )

    assert status.configured is False
    assert "different" in status.reason


def test_llm_council_status_rejects_unallowed_evaluator_model() -> None:
    status = llm_council_status(
        _settings(),
        requested_models=["openai/gpt-4.1-mini", "google/gemini-2.5-flash"],
        requested_chair_model="unknown/model",
    )

    assert status.configured is False
    assert "evaluator" in status.reason


def test_llm_council_status_defaults_to_two_responders_and_one_evaluator() -> None:
    status = llm_council_status(_settings(llm_council_models=""))

    assert status.configured is True
    assert len(status.models) == 2
    assert status.chair_model is not None
    assert status.chair_model not in status.models
