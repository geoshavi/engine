from engine.config import Config
from engine.providers.anthropic_provider import AnthropicProvider
from engine.providers.base import Provider
from engine.providers.google_provider import GoogleProvider
from engine.providers.ollama_provider import OllamaProvider
from engine.providers.openai_provider import OpenAIProvider

# Default model per task-class, used until the M2 routing/experimentation
# system learns per-task-class choices from real verification outcomes.
DEFAULT_MODELS = {
    "anthropic": {
        "coding": "claude-sonnet-5",
        "research": "claude-sonnet-5",
        "testing": "claude-sonnet-5",
        "refactoring": "claude-sonnet-5",
        "judge": "claude-haiku-4-5-20251001",
        "planner": "claude-sonnet-5",
    },
}


def build_provider(name: str, config: Config) -> Provider:
    if name == "anthropic":
        if not config.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        return AnthropicProvider(api_key=config.anthropic_api_key)
    if name == "openai":
        if not config.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        return OpenAIProvider(api_key=config.openai_api_key)
    if name == "google":
        if not config.google_api_key:
            raise ValueError("GOOGLE_API_KEY is not set")
        return GoogleProvider(api_key=config.google_api_key)
    if name == "ollama":
        return OllamaProvider()
    raise ValueError(f"Unknown provider: {name}")
