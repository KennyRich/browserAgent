"""Factory for creating pydantic_ai Model instances from application settings."""

from pydantic_ai.models import Model

from browser_agent.config import Settings

DEFAULT_MODELS: dict[str, str] = {
    "ollama": "qwen3.5:35b-a3b-coding-nvfp4",
    "openai": "gpt-4o",
    "anthropic": "claude-opus-4-7",
    "google": "gemini-2.0-flash",
}


def create_model(settings: Settings) -> Model:
    """Create a pydantic_ai Model from the current application settings."""
    match settings.provider:
        case "ollama":
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.ollama import OllamaProvider

            return OpenAIChatModel(
                model_name=settings.model_name,
                provider=OllamaProvider(base_url=settings.ollama_base_url),
            )

        case "openai":
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            kwargs: dict = {}
            if settings.openai_api_key:
                kwargs["api_key"] = settings.openai_api_key
            if settings.openai_base_url:
                kwargs["base_url"] = settings.openai_base_url

            return OpenAIChatModel(
                model_name=settings.model_name,
                provider=OpenAIProvider(**kwargs),
            )

        case "anthropic":
            from pydantic_ai.models.anthropic import AnthropicModel
            from pydantic_ai.providers.anthropic import AnthropicProvider

            kwargs: dict = {}
            if settings.anthropic_api_key:
                kwargs["api_key"] = settings.anthropic_api_key

            return AnthropicModel(
                model_name=settings.model_name,
                provider=AnthropicProvider(**kwargs),
            )

        case "google":
            from pydantic_ai.models.google import GoogleModel
            from pydantic_ai.providers.google import GoogleProvider

            kwargs: dict = {}
            if settings.google_api_key:
                kwargs["api_key"] = settings.google_api_key

            return GoogleModel(
                model_name=settings.model_name,
                provider=GoogleProvider(**kwargs),
            )

        case _:
            raise ValueError(
                f"Unsupported provider: {settings.provider!r}. "
                f"Supported: ollama, openai, anthropic, google"
            )
