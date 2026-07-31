from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from engine.config import Config
from engine.providers.base import Message
from engine.providers.registry import build_provider


def _fake_anthropic_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


def test_anthropic_provider_generate_parses_response() -> None:
    with patch("engine.providers.anthropic_provider.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_anthropic_response("hello world")
        MockAnthropic.return_value = mock_client

        from engine.providers.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider(api_key="fake-key")
        result = provider.generate(
            messages=[Message(role="user", content="hi")], model="claude-sonnet-5"
        )

        assert result.text == "hello world"
        assert result.provider == "anthropic"
        assert result.input_tokens == 10
        assert result.output_tokens == 5


def test_build_provider_missing_key_raises() -> None:
    config = Config(
        anthropic_api_key=None,
        openai_api_key=None,
        google_api_key=None,
        max_retries=3,
        db_path="unused",
    )
    with pytest.raises(ValueError):
        build_provider("anthropic", config)


def test_build_provider_unknown_name_raises() -> None:
    config = Config(
        anthropic_api_key="key",
        openai_api_key=None,
        google_api_key=None,
        max_retries=3,
        db_path="unused",
    )
    with pytest.raises(ValueError):
        build_provider("does-not-exist", config)
