from core.config import Settings
from llm.anthropic import AnthropicLLM
from llm.base import LLMProvider
from llm.fake import FakeLLM
from llm.openai_compat import OpenAICompatLLM


def build_llm_provider(settings: Settings) -> LLMProvider:
    match settings.llm_provider:
        case "anthropic":
            return AnthropicLLM(model=settings.llm_model, api_key=settings.anthropic_api_key)
        case "openai":
            return OpenAICompatLLM(
                name="openai",
                model=settings.llm_model,
                api_key=settings.openai_api_key,
                base_url=settings.llm_base_url or "https://api.openai.com/v1",
            )
        case "openrouter":
            return OpenAICompatLLM(
                name="openrouter",
                model=settings.llm_model,
                api_key=settings.openrouter_api_key,
                base_url=settings.llm_base_url or "https://openrouter.ai/api/v1",
            )
        case "fake":
            return FakeLLM()
        case other:
            raise ValueError(f"Unknown LLM provider: {other}")
